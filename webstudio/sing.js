// Singing in the web studio (webstudio/, docs/WEB-SINGING.md): the Sing view. A visitor sings the version on the page
// (or the released one) along with its tune, the take is measured (in the studio on the visitor's device, in their
// own browser, never sent: the offer says `device`; from a server's studio, on that server, its audio deleted there),
// and the song is sung their way.
//
// A module the studio adds to its page only when it takes singing (--web-singing, or the site built for the device).
// It reaches the studio's page through window.songbirdStudio (studio.js's last section) and window.SongbirdScore (the
// views), and reuses the karaoke's timing, drawing and take recorder (tools/karaoke.js, tools/karaoke-recorder.js)
// rather than its own: a take here is cut, synced and written exactly as one sung in the karaoke or on the online
// page, so it is measured the same way.
//
// The guide is made from the version as the page has it each time the view is opened or the version changes (POST
// /api/sing/guide: its words, tune, key and tempo, at the speed and in the key chosen here), and its melody a section
// at a time (GET /api/sing/melody), so what is sung is always what the Page shows.
//
// What stays in this browser (localStorage, under STORE): whether the consent was read (its version), the speed and
// key chosen, the device's extra delay, the numbers measured from each take, and the way of singing made from them.
// The take's audio is only ever in this page's memory, until it is measured (sent to be, from a server's page) or
// sung again.
import * as K from "/karaoke.js";

const ST = window.songbirdStudio;
const TOKEN = document.querySelector('meta[name="studio-token"]').content;
const STORE = "songbird-web-singing";
const MAX_TAKES = 12;
const RING = 1.0;  // seconds of a section's guide past its window's end (webstudio/guide.py RING: a server makes no other stretch)
const $ = (id) => document.getElementById(id);
const h = ST.h;

const S = {
  offer: null, which: "page", lyrics: null, sections: [], part: null, view: null, reel: null, words: new Map(),
  guides: new Map(), ctx: null, stream: null, recorder: null, analyser: null, buf: null, opening: null, asked: null,
  mode: "idle", starting: false, src: [], t0: 0, out: 0, inn: 0, stopAt: null, chunks: [], trail: [], showTrail: null,
  recording: null, take: null, takeTrail: [], shift: 0, autoShift: 0, measuring: false, run: 0, shown: false,
};

// ------------------------------------------------------------------ what this browser keeps

function kept() {
  try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { return {}; }
}

function keep(patch) {
  const next = { ...kept(), ...patch };
  for (const [k, v] of Object.entries(next)) if (v === null || v === undefined) delete next[k];
  try { localStorage.setItem(STORE, JSON.stringify(next)); } catch (e) { /* a private window: this visit only */ }
  return next;
}

function delay() { return (Number(kept().nudge) || 0) / 1000; }  // what the device adds beyond what it reports

// ------------------------------------------------------------------ the words (the simplest true thing; the rest in
// tooltips and docs/WEB-SINGING.md)

const WORDS = {
  device: [  // measured in this browser: the consent's own version (studio_device.py DEVICE_CONSENT)
    ["Your singing is recorded and measured on this device, then deleted. It is not sent anywhere.",
      "It is not saved, played to anyone or used to copy a voice. A take waits in this page's memory until you use it or record again."],
    ["What is kept, in this browser, is a set of numbers for each note: when you came in, how long you held it, how loud it was and how you slid into it.",
      "They stay in this browser until you choose Forget my singing."],
    ["A version you share contains those numbers and no recording of you. Forget my singing deletes them from this browser.",
      "It can't remove them from a version you already exported or shared."],
  ],
  server: [  // measured on the computer serving the studio (webstudio/singing.py CONSENT)
    ["Your take is sent to the computer that runs this studio, measured there, then deleted.",
      "It is not saved, played to anyone or used to copy a voice."],
    ["What is kept is a set of numbers for each note: when you came in, how long you held it, how loud it was and how you slid into it.",
      "They are stored in this browser and on the computer that runs this studio, with no name or address attached. That copy is deleted {days} days after its last use."],
    ["A version you export contains those numbers and no recording of you. Forget my singing deletes them.",
      "From this browser and from the computer that runs this studio. It can't remove them from a file you already exported."],
  ],
};

// ------------------------------------------------------------------ the view

function build() {
  // the Tools sheet's way in: one line, and the button opens the Sing view
  const tool = $("singTitle").closest("section");
  const line = tool.querySelector("p");
  line.textContent = "The song learns your timing.";
  line.removeAttribute("title");
  const old = $("sing"), button = old.cloneNode(true);  // the studio's own listener (the karaoke page) stays with the old one
  button.textContent = "Sing";
  old.replaceWith(button);
  button.addEventListener("click", () => {
    $("finishPanel").querySelector("[data-close]")?.click();
    window.SongbirdScore?.showView("sing", true);
  });

  const choice = (id, label, title, options) => h("label", { class: "sing-choice", title },
    h("span", {}, label), h("select", { id, "aria-label": label }, ...options));
  const work = h("div", { id: "singWork", hidden: true },
    h("div", { class: "sing-choices" },
      h("span", { class: "switch", role: "group", "aria-label": "What to sing", id: "singWhich", hidden: true },
        h("button", { type: "button", "data-which": "page", "aria-pressed": "true", title: "The version on the Page: its words, key and tempo" }, "This version"),
        h("button", { type: "button", "data-which": "released", "aria-pressed": "false", title: "The song as it was released" }, "Released")),
      choice("singSpeed", "Speed", "A slower guide to learn it by; your timing is measured against it", []),
      choice("singKey", "Key", "Too high or too low? Choose another key; a man and a woman can sing an octave apart.", []),
      h("label", { class: "check hint", title: "Headphones keep the guide out of the microphone. Without them, the browser takes the guide out of what it hears (echo cancellation)." },
        h("input", { type: "checkbox", id: "singSpeaker" }), " No headphones")),
    h("div", { class: "chips", id: "singParts", role: "group", "aria-label": "What to sing" }),
    h("div", { class: "sing-stage", id: "singStage" },
      h("button", { class: "sing-full", type: "button", id: "singFull" }, "Full screen"),
      h("canvas", { class: "lane", id: "singLane", "aria-hidden": "true" }),
      h("div", { class: "scroller" }, h("div", { class: "reel", id: "singReel" })),
      h("div", { class: "sing-bar" }, h("div", { id: "singProgress" }))),
    h("div", { class: "actions" },
      h("button", { class: "btn", type: "button", id: "singRehearse" }, "▶ Rehearse"),
      h("button", { class: "btn primary", type: "button", id: "singRecord" }, "● Record"),
      h("button", { class: "btn", type: "button", id: "singStop", disabled: true }, "■ Stop"),
      h("span", { class: "hint sing-meter", title: "your microphone" }, "mic ", h("span", { class: "meter" }, h("span", { id: "singLevel" })))),
    h("p", { class: "sing-status", id: "singStatus", "aria-live": "polite" }),
    h("div", { class: "sing-review", id: "singReview", hidden: true },
      h("h3", { id: "singReviewTitle" }, "Your take"),
      h("div", { class: "actions" },
        h("button", { class: "btn", type: "button", id: "singListen" }, "▶ Listen back"),
        h("button", { class: "btn primary", type: "button", id: "singMeasure", title: "The song measures your timing in this take, then deletes it" }, "Use this take"),
        h("button", { class: "btn quiet", type: "button", id: "singDiscard" }, "Record again")),
      h("div", { class: "sing-sync", title: "If your voice sits late or early against the guide, slide it while you listen." },
        h("span", { class: "hint" }, "earlier"),
        h("input", { type: "range", id: "singShift", min: "-400", max: "400", step: "5", value: "0", "aria-label": "Slide your take earlier or later" }),
        h("span", { class: "hint" }, "later"),
        h("span", { class: "hint", id: "singShiftValue" }, "as recorded"))),
    h("div", { class: "sing-yours", id: "singYours", hidden: true },
      h("h3", {}, "Your way"),
      h("p", { class: "sing-portrait", id: "singPortrait" }),
      h("p", { class: "hint", id: "singTakes" }),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", type: "button", id: "singHear" }, "▶ Hear it"),
        h("button", { class: "btn", type: "button", id: "singToRecord" }, "Export"),
        h("button", { class: "link small", type: "button", id: "singForget" }, "Forget my singing"))));

  const consent = h("div", { id: "singConsent", hidden: true },
    h("ul", { class: "sing-promises", id: "singPromises" }),
    h("label", { class: "check" }, h("input", { type: "checkbox", id: "singAgree" }), " I understand."),
    h("div", { class: "actions" }, h("button", { class: "btn primary", type: "button", id: "singBegin", disabled: true }, "Start")));

  $("view-sing").append(h("section", { class: "websing", id: "webSing", "aria-labelledby": "webSingTitle" },
    h("h2", { class: "sr-only", id: "webSingTitle" }, "Sing"),
    h("p", { class: "hint", id: "singWhy" }), consent, work));

  $("singAgree").addEventListener("change", () => { $("singBegin").disabled = !$("singAgree").checked; });
  $("singBegin").addEventListener("click", () => { keep({ consent: S.offer.consent }); showWork(); });
  for (const b of $("singWhich").querySelectorAll("button")) b.addEventListener("click", () => chooseWhich(b.dataset.which));
  $("singSpeed").addEventListener("change", () => { keep({ speed: Number($("singSpeed").value) }); guideWords(); });
  $("singKey").addEventListener("change", () => { keep({ key: Number($("singKey").value) }); guideWords(); });
  $("singSpeaker").checked = !!kept().speaker;
  $("singSpeaker").addEventListener("change", () => {
    keep({ speaker: $("singSpeaker").checked || null });
    if (S.mode !== "idle" || S.starting) return;
    closeMicrophone();  // opened again as now asked, the next time it's wanted
  });
  $("singRehearse").addEventListener("click", rehearse);
  $("singRecord").addEventListener("click", record);
  $("singStop").addEventListener("click", stop);
  $("singListen").addEventListener("click", () => listenFrom(0));
  $("singDiscard").addEventListener("click", discard);
  $("singMeasure").addEventListener("click", measure);
  $("singShift").addEventListener("input", () => {
    const ms = Number($("singShift").value);
    S.shift = -ms / 1000;  // slid left, the voice comes earlier
    $("singShiftValue").textContent = ms ? `${Math.abs(ms)} ms ${ms < 0 ? "earlier" : "later"}${S.shift === S.autoShift ? " (auto)" : ""}` : "as recorded";
  });
  $("singShift").addEventListener("change", () => {
    if (S.mode === "listening" && S.take) listenFrom(S.ctx.currentTime - S.t0 - S.out - 1.0);
  });
  $("singHear").addEventListener("click", () => ST.listen("you", null));
  $("singToRecord").addEventListener("click", () => ST.revealRecording(true));
  $("singForget").addEventListener("click", forget);
  K.fullScreen($("singStage"), $("singFull"), () => { if (S.mode === "idle" && S.view) resting(); });
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && S.mode !== "idle" && !["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) {
      e.preventDefault();
      e.stopPropagation();
      stop();
    }
  }, true);
  window.addEventListener("resize", () => { if (S.mode === "idle" && S.view && S.shown) resting(); });
  document.addEventListener("studio:view", (e) => {
    S.shown = e.detail.view === "sing";
    if (S.shown) enter();
    else if (S.mode === "rehearsing" || S.mode === "listening") stop();
  });
  document.addEventListener("studio:render", () => { if (S.shown) guideWords(); });  // the version changed
}

function say(text, warn = false) {
  const el = $("singStatus");
  el.textContent = text;
  el.classList.toggle("warn", warn);
}

function enter() {
  if (!S.offer || !S.offer.available) return;
  if (kept().consent === S.offer.consent) showWork();
  else { $("singConsent").hidden = false; $("singWork").hidden = true; }
  if (S.view) requestAnimationFrame(resting);  // the lane's size is known now it's shown
}

function showWork() {
  $("singConsent").hidden = true;
  $("singWork").hidden = false;
  if (!window.isSecureContext || !navigator.mediaDevices) {
    say("The microphone needs the studio opened over https.", true);
  }
  guideWords();
}

// ------------------------------------------------------------------ what to sing: the version (or the released one),
// a speed, a key, a section or the whole song

function chooseWhich(which) {
  S.which = which === "released" && S.offer.released ? "released" : "page";
  for (const b of $("singWhich").querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.which === S.which));
  guideWords();
}

function asking() {
  // the version's edits but the way it's sung (a phrasing moves no note of the tune: the guide is on its grid)
  const edits = { ...ST.state.edits };
  delete edits.phrasing;
  return { which: S.which, speed: Number($("singSpeed").value), key: Number($("singKey").value),
           edits: S.which === "page" ? edits : {} };
}

async function guideWords() {
  // the guide's words for the version as it is now: asked again when it changed (a choice here, or an edit)
  if ($("singWork").hidden || S.mode !== "idle" || S.starting || S.take || S.measuring) return;
  const want = asking(), sig = JSON.stringify(want);
  if (sig === S.asked) return;
  S.asked = sig;
  controls();
  if (!S.words.has(sig)) {
    const p = ST.api("/api/sing/guide", want);
    p.catch(() => S.words.delete(sig));
    S.words.set(sig, p);
  }
  if (!S.lyrics) say("Setting out the words…");
  let lyrics;
  try { lyrics = await S.words.get(sig); } catch (e) { S.asked = null; say(e.message, true); return; }
  if (S.asked !== sig) return;
  const was = S.part;
  S.lyrics = lyrics;
  S.sections = K.sungSections(lyrics);
  const same = was && was.index !== null ? S.sections.find((s) => s.name === was.name && s.title === was.title) : null;
  choosePart(was && was.index === null ? null : same ? same.index : S.sections.length ? S.sections[0].index : null, !!was);
  controls();
}

function choosePart(index, quiet = false) {
  S.part = K.part(S.lyrics, index) || K.part(S.lyrics);
  view(S.lyrics, S.part);
  drawParts();
  resting();
  if (!quiet) say("");
  guide(S.part).catch(() => {});  // made ahead, so it's ready when you are
}

function drawParts() {
  const box = $("singParts"), locked = S.mode !== "idle" || !!S.take || S.starting || S.measuring;
  box.replaceChildren();
  if (!S.lyrics) return;
  const chip = (index, title, label) => {
    const b = h("button", { class: `chip${S.part.index === index ? " on" : ""}`, type: "button", title: label,
                            "aria-pressed": String(S.part.index === index), disabled: locked }, title);
    b.addEventListener("click", () => choosePart(index));
    box.append(b);
  };
  for (const s of S.sections) chip(s.index, s.title, K.sectionLabel(s));
  chip(null, K.WHOLE, "From the top");
  $("singRecord").textContent = S.part.index === null ? "● Record the whole song" : `● Record ${S.part.title}`;
}

function view(lyrics, part) {
  const notes = K.notesOf(lyrics);
  S.view = { lyrics, part, notes: part.index === null ? notes : K.inWindow(notes, part.from, part.to), ...K.range(notes) };
  S.reel = new K.Reel($("singReel"), lyrics, part.index === null ? {} : { from: part.from, to: part.to, name: part.name, end: "That's the section." });
}

function resting() {
  if (!S.view) return;
  S.reel.show(S.view.part.from);
  drawLane(K.restAt(S.view.notes, S.view.part.from));
  $("singProgress").style.width = "0";
}

function drawLane(pos) {
  K.drawLane($("singLane"), S.view.notes, S.view.lo, S.view.hi, pos, S.showTrail);
}

function controls() {
  const idle = S.mode === "idle" && !S.starting, loading = !S.lyrics;
  const busy = !idle || !!S.take || S.measuring;
  $("singStop").disabled = S.mode === "idle";
  $("singRehearse").disabled = !idle || loading;
  $("singRecord").disabled = busy || loading;
  for (const id of ["singSpeed", "singKey"]) $(id).disabled = busy;
  for (const b of $("singWhich").querySelectorAll("button")) b.disabled = busy;
  $("singMeasure").disabled = S.measuring;
  $("singDiscard").disabled = S.measuring;
  drawParts();
}

// ------------------------------------------------------------------ the guide, the microphone, the clock

async function context() {
  if (!S.ctx) S.ctx = new AudioContext({ latencyHint: "interactive" });
  await S.ctx.resume();
}

function guide(part) {  // a part's melody guide, made (or kept) by the studio, decoded once: {buffer, at}
  const lyrics = S.lyrics, at = part.from, to = part.index === null ? lyrics.duration : Math.min(lyrics.duration, part.to + RING);
  const name = `${lyrics.guide}|${at}|${to}`;
  if (!S.guides.has(name)) {
    const last = (kept().measurements || []).slice(-1)[0];
    const query = new URLSearchParams({ guide: lyrics.guide, from: at.toFixed(3), to: to.toFixed(3),
                                        ahead: String(last && Number.isInteger(last.key) ? last.key : 0), until: part.to.toFixed(3) });
    const p = (async () => {
      const r = await fetch(`/api/sing/melody?${query}`, { headers: { "X-Studio": TOKEN } });
      if (!r.ok) throw new Error(((await r.json().catch(() => ({}))).error) || "The guide couldn't be made: reload the page.");
      const bytes = await r.arrayBuffer();
      await context();
      return { buffer: await S.ctx.decodeAudioData(bytes), at };
    })();
    p.catch(() => S.guides.delete(name));
    S.guides.set(name, p);
  }
  return S.guides.get(name);
}

async function chosenGuide() {
  const p = guide(S.part);
  let ready = false;
  p.then(() => { ready = true; }, () => {});
  await Promise.resolve();
  if (!ready) say(S.part.index === null ? "Making the guide for the whole song (about a minute)…" : "Making the guide…");
  return p;
}

function microphone() {  // opened once: a second tap waits for the first
  if (!S.opening) S.opening = openMicrophone().catch((e) => { S.opening = null; throw e; });
  return S.opening;
}

async function openMicrophone() {
  S.stream = await navigator.mediaDevices.getUserMedia({ audio: K.micOptions($("singSpeaker").checked) });
  if (K.bluetoothMic((S.stream.getAudioTracks()[0] || {}).label)) say(K.BLUETOOTH, true);
  const mic = S.ctx.createMediaStreamSource(S.stream);
  await S.ctx.audioWorklet.addModule("/recorder.js");
  S.recorder = new AudioWorkletNode(S.ctx, "take-recorder", { numberOfOutputs: 1, outputChannelCount: [1] });
  const silent = S.ctx.createGain();
  silent.gain.value = 0;
  mic.connect(S.recorder).connect(silent).connect(S.ctx.destination);
  S.analyser = S.ctx.createAnalyser();
  S.analyser.fftSize = 2048;
  S.buf = new Float32Array(S.analyser.fftSize);
  mic.connect(S.analyser);
  S.recorder.port.onmessage = (e) => {
    if (S.mode === "recording" || S.mode === "finishing") S.chunks.push(e.data);
    $("singLevel").style.width = Math.min(100, 140 * e.data.peak) + "%";
  };
}

function closeMicrophone() {
  if (S.stream) S.stream.getTracks().forEach((t) => t.stop());
  if (S.recorder) { try { S.recorder.disconnect(); } catch (e) { /* gone */ } }
  S.stream = S.recorder = S.analyser = S.opening = null;
}

async function starting(go) {
  if (S.starting || S.mode !== "idle") return;
  S.starting = true;
  controls();
  try { await go(); } catch (e) { say(e.message, true); } finally { S.starting = false; controls(); }
}

function start(sources, mode, from = 0, until = null) {
  // play from guide time `from` until guide time `until`: each source a buffer whose first sample is guide time `at`
  // (the guide's stretch; a take, slid), at its gain
  const when = S.ctx.currentTime + 0.12;
  S.t0 = when - from;
  S.stopAt = until;
  S.out = (S.ctx.outputLatency || 0) + (S.ctx.baseLatency || 0);
  S.inn = S.stream ? S.stream.getAudioTracks()[0].getSettings().latency || 0 : 0;
  const out = mode === "listening" ? K.listenOut(S.ctx) : S.ctx.destination;
  S.src = sources.map((s, i) => {
    const src = S.ctx.createBufferSource(), fader = S.ctx.createGain();
    src.buffer = s.buffer;
    (mode === "listening" && i > 0 ? src.connect(K.takeFilter(S.ctx)) : src).connect(fader).connect(out);
    const at = from - s.at, level = s.gain ?? 1;
    if (from > s.at) { fader.gain.setValueAtTime(0, when); fader.gain.linearRampToValueAtTime(level, when + 0.03); }
    else fader.gain.value = level;
    if (at >= 0) src.start(when, at); else src.start(when - at);
    src.fader = fader;
    return src;
  });
  S.src[0].onended = () => {
    if (S.mode === "recording" && S.stopAt !== null) windowEnds();
    else if (S.mode !== "idle") stop();
  };
  S.chunks = [];
  S.trail = [];
  S.showTrail = mode === "listening" ? S.takeTrail.map((p) => ({ t: p.t - S.shift, m: p.m })) : S.trail;
  S.mode = mode;
  controls();
  $("singReview").hidden = true;
  const section = S.view.part.index !== null;
  say(mode === "recording" ? (section ? `Recording ${S.view.part.title}.` : "Recording. Space or Stop to finish.")
    : "");
  const run = S.run = S.run + 1;
  const tick = () => {
    if (run !== S.run || S.mode === "idle" || S.mode === "finishing") return;
    const pos = S.ctx.currentTime - S.t0 - S.out;
    if (S.stopAt !== null && pos >= S.stopAt) return windowEnds();
    if (S.mode !== "listening" && S.analyser) {
      S.analyser.getFloatTimeDomainData(S.buf);
      S.trail.push({ t: pos - S.inn - delay() - 0.02, m: K.pitchAt(S.buf, S.ctx.sampleRate) });
    }
    const { from: a, to: b } = S.view.part;
    $("singProgress").style.width = Math.max(0, Math.min(100, (100 * (pos - a)) / (b - a))) + "%";
    S.reel.show(pos);
    drawLane(pos);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function silence(sources) {
  const now = S.ctx.currentTime;
  for (const s of sources) {
    s.onended = null;
    try {
      s.fader.gain.cancelScheduledValues(now);
      s.fader.gain.setValueAtTime(s.fader.gain.value, now);
      s.fader.gain.linearRampToValueAtTime(0, now + 0.08);
      s.stop(now + 0.1);
    } catch (e) { /* already stopped */ }
  }
}

function stop() {
  const was = S.mode;
  if (was === "idle") return;
  const pos = S.ctx.currentTime - S.t0 - S.out;
  S.mode = "idle";
  clearTimeout(S.finishing);
  silence(S.src);
  S.src = [];
  if (was === "recording" || was === "finishing") finishTake(was === "finishing" ? S.stopAt : pos);
  else say("");
  $("singReview").hidden = !S.take;
  S.showTrail = null;
  controls();
  resting();
  if (!S.take) guideWords();  // the version may have changed meanwhile
}

function windowEnds() {
  // the end of a section: the guide stops; a take records a moment longer, for your last note
  if (S.mode !== "recording") return stop();
  S.mode = "finishing";
  silence(S.src);
  S.src = [];
  say("");
  S.finishing = setTimeout(stop, (K.TAIL + Math.max(0, S.inn + delay()) + 0.15) * 1000);
}

function finishTake(stoppedAt) {
  const rate = S.ctx.sampleRate, r = S.recording, part = r.part, whole = part.index === null;
  const first = K.firstFrame(S.t0, S.out, S.inn, delay(), rate, part.from);
  const samples = whole ? K.assemble(S.chunks, first) : K.cutTake(S.chunks, first, rate, part.to - part.from + K.TAIL);
  S.chunks = [];
  const to = Math.round(Math.max(part.from, Math.min(part.to, stoppedAt)) * 1000) / 1000;
  const long = samples.length / rate > 5;
  S.take = long ? { ...r, samples, rate, to, device: delay(), buffer: null } : null;
  S.takeTrail = S.trail.slice();
  const notes = K.notesOf(r.lyrics);
  S.shift = S.autoShift = long ? (whole ? K.autoSync(S.takeTrail, notes) : K.autoSyncWindow(S.takeTrail, notes, part.from, part.to)) : 0;
  $("singShift").value = String(Math.max(-400, Math.min(400, -S.shift * 1000)));
  $("singShiftValue").textContent = S.shift ? `auto, ${Math.abs(Math.round(S.shift * 1000))} ms ${S.shift > 0 ? "earlier" : "later"}` : "as recorded";
  if (S.shift) keep({ nudge: Math.round(delay() * 1000 + S.shift * 1000) });  // the next take starts closer
  $("singReviewTitle").textContent = whole ? "Your take" : `Your take: ${part.title}`;
  say(long ? "" : "Too short. Record again.");
}

function rehearse() {
  return starting(async () => {
    await context();
    const g = await chosenGuide();
    try { await microphone(); } catch (e) { /* rehearsing works without it: no pitch line */ }
    start([g], "rehearsing", S.part.from, S.part.index === null ? null : S.part.to);
  });
}

function record() {
  return starting(async () => {
    await context();
    const g = await chosenGuide();
    try { await microphone(); } catch (e) { throw new Error(`The page couldn't use your microphone (${e.message}). Allow it in the browser, then record again.`); }
    S.recording = { lyrics: S.lyrics, part: S.part, digest: S.lyrics.guide, guide: g };
    start([g], "recording", S.part.from, S.part.index === null ? null : S.part.to);
  });
}

function takeBuffer() {
  if (!S.take.buffer) {
    S.take.buffer = S.ctx.createBuffer(1, S.take.samples.length, S.take.rate);
    S.take.buffer.copyToChannel(S.take.samples, 0);
  }
  return S.take.buffer;
}

function listenFrom(from) {
  const t = S.take, p = t.part;
  if (S.mode !== "idle") { silence(S.src); S.mode = "idle"; }
  t.gain = t.gain || K.takeGain(t.samples, t.rate);  // lifted to be heard over the guide (what's measured stays as sung)
  start([{ ...t.guide, gain: K.UNDER }, { buffer: takeBuffer(), at: p.from - S.shift, gain: t.gain }], "listening",
        Math.max(p.from, from), p.index === null ? null : t.to + 0.3);
}

function discard() {
  if (S.mode === "listening") stop();
  S.take = null;  // the audio goes with it
  $("singReview").hidden = true;
  controls();
  say("");
  guideWords();
}

// ------------------------------------------------------------------ measuring: the take measured, its numbers back

async function measure() {
  const t = S.take;
  if (!t || S.measuring) return;
  if (S.mode === "listening") stop();
  const earlier = (kept().measurements || []).slice(-(MAX_TAKES - 1));
  const meta = new TextEncoder().encode(JSON.stringify({
    guide: t.digest, section: t.part.index, from_s: t.part.from, to_s: t.to,
    shift_ms: Math.round(S.shift * 1000), auto_ms: Math.round((S.autoShift || 0) * 1000), device_ms: Math.round(t.device * 1000),
    earlier,
  }));
  const body = new Blob([meta, K.wavBytes(K.shifted(t.samples, t.rate, S.shift), t.rate)]);
  S.measuring = true;
  controls();
  say("Measuring it…");
  let job;
  try {
    const r = await fetch("/api/sing/take", { method: "POST", body,
      headers: { "Content-Type": "application/x-songbird-take", "X-Studio": TOKEN, "X-Sing-Meta": String(meta.length) } });
    job = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok) throw new Error(job.error || r.statusText);
  } catch (e) {
    S.measuring = false;
    controls();
    say(`The take couldn't be used: ${e.message}`, true);
    return;
  }
  const estimate = job.estimate || 10;
  S.take = null;  // handed over: this page lets go of the recording
  $("singReview").hidden = true;
  for (;;) {
    if (job.state === "queued" && job.ahead) {
      say(`Waiting (${job.ahead} ahead), then about ${estimate} s.`);
    } else if (job.state === "queued" || job.state === "running") {
      say(`Measuring your timing (about ${estimate} s)…`);
    } else break;
    await new Promise((r) => setTimeout(r, 1000));
    try { job = await ST.api(`/api/job/${job.id}`); } catch (e) { job = { state: "failed", error: e.message }; }
  }
  S.measuring = false;
  controls();
  const result = job.result || {};
  if (job.state !== "done") {
    say(`The take couldn't be used: ${String(job.error || "the studio stopped").replace(/^\w+(Error|Exception): /, "")}. Record again.`, true);
    return;
  }
  if (result.refused) { say(result.refused, true); return; }
  const measurements = [...earlier, result.measurement];
  keep({ measurements, phrasing: { name: result.name, json: result.phrasing, portrait: result.portrait } });
  own(result.name, result.phrasing);
  ST.setEdit("phrasing", result.name, "Sing it your way");
  showYours();
  say("The song follows your timing now.");
}

function own(name, json) {
  // the singer's card offers "your way" beside everyone's (studio.js keeps it in ownPhrasings)
  const list = ST.ownPhrasings;
  list.splice(0, list.length, { id: name, label: "you", way: "your way", detail: (json && json.source_detail) || "" });
  ST.renderCards();
}

function showYours() {
  const k = kept(), n = (k.measurements || []).length;
  $("singYours").hidden = !k.phrasing;
  if (!k.phrasing) return;
  // the latest take's sentences (each take has its own); every take's in the tooltip
  const portrait = String(k.phrasing.portrait || "");
  $("singPortrait").textContent = portrait.split(/\n(?=Take \d+:)/).pop();
  $("singPortrait").title = portrait.includes("\nTake ") ? portrait : "";
  $("singTakes").textContent = `From ${n} take${n === 1 ? "" : "s"}.`;
  $("singTakes").title = `Each take you use joins it, up to ${MAX_TAKES}.`;
}

async function forget() {
  const button = $("singForget");
  if (!button.dataset.sure) {
    button.dataset.sure = "1";
    button.textContent = "Forget it? Press again";
    setTimeout(() => { delete button.dataset.sure; button.textContent = "Forget my singing"; }, 5000);
    return;
  }
  delete button.dataset.sure;
  button.textContent = "Forget my singing";
  const name = (kept().phrasing || {}).name;
  try { if (name) await ST.api("/api/sing/forget", { name }); } catch (e) { say(`It couldn't be forgotten: ${e.message}`, true); return; }
  keep({ measurements: null, phrasing: null });
  ST.ownPhrasings.splice(0, ST.ownPhrasings.length);
  if (ST.state.edits.phrasing === name) ST.setEdit("phrasing", null, "Forget my singing");
  else ST.renderCards();
  showYours();
  say("Forgotten.");
}

// ------------------------------------------------------------------ starting

async function restore() {
  // a way of singing made on an earlier visit: offered again, and kept again there (a server keeps it by its
  // fingerprint for a while after it was last used; this browser is where it lives)
  const k = kept();
  if (!k.phrasing || !k.phrasing.json) return;
  own(k.phrasing.name, k.phrasing.json);
  try {
    const r = await ST.api("/api/sing/keep", { phrasing: k.phrasing.json });
    if (r.name !== k.phrasing.name) {
      keep({ phrasing: { ...k.phrasing, name: r.name, json: r.phrasing } });
      own(r.name, r.phrasing);
      if (ST.state.edits.phrasing === k.phrasing.name) ST.setEdit("phrasing", r.name, "Sing it your way");
    } else if (ST.state.edits.phrasing === r.name) {
      ST.refresh();
    }
  } catch (e) { /* the studio says why on its card */ }
}

function offered() {
  // the view's choices and words, once the offer says where the singing is measured (never before: a device's page
  // must not show a server's words, even for a moment)
  const o = S.offer, k = kept();
  const days = String(o.keep_days || 30);
  $("singPromises").replaceChildren(...WORDS[o.device ? "device" : "server"].map(([line, more]) =>
    h("li", { title: more.replace("{days}", days) }, line)));
  for (const speed of o.speeds) $("singSpeed").append(h("option", { value: String(speed) }, speed === 100 ? "as written" : `${speed}%`));
  for (const key of o.keys) $("singKey").append(h("option", { value: String(key) }, key ? K.keyLabel(key) : "as written"));
  $("singSpeed").value = String(o.speeds.includes(k.speed) ? k.speed : o.speed);
  $("singKey").value = String(o.keys.includes(k.key) ? k.key : 0);
  $("singWhich").hidden = !o.released;
}

async function init() {
  build();
  try { S.offer = await ST.api("/api/sing/offer"); } catch (e) { S.offer = { available: false, why: e.message }; }
  // the Sing view and its ways in: its tab, the phone's bar, the keyboard's 4
  $("tab-sing").hidden = false;
  document.querySelector('#bottombar [data-view="sing"]')?.removeAttribute("hidden");
  if ($("viewKeys")) { $("viewKeys").textContent = "1 · 2 · 3 · 4"; $("viewNames").textContent = "Page · Arrange · Mix · Sing"; }
  // an address that names the view (#view=sing) was read before the view was here
  if (new URLSearchParams(location.hash.slice(1)).get("view") === "sing") window.SongbirdScore?.showView("sing");
  if (!S.offer.available) {
    $("singWhy").textContent = S.offer.why || "Singing isn't available here.";
    $("singNote").textContent = $("singWhy").textContent;
    return;
  }
  $("singWhy").hidden = true;
  offered();
  showYours();
  restore();
  if (S.shown) enter();
}

init();
