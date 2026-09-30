// Singing in the web studio (webstudio/, docs/WEB-SINGING.md): a visitor sings along to the guide on the studio's
// own page, the take is measured on the server and its audio deleted there, and the song is sung their way.
//
// A module the studio adds to its page only when started with --web-singing. It reaches the studio's page through
// window.songbirdStudio alone (studio.js's last section), and reuses the karaoke's timing, drawing and take
// recorder (tools/karaoke.js, tools/karaoke-recorder.js) rather than its own: a take here is cut, synced and
// written exactly as one sung in the karaoke or on the online page, so it is measured the same way.
//
// What stays in this browser (localStorage, under STORE): whether the consent was read (its version), the
// device's extra delay, the numbers measured from each take, and the way of singing made from them. The take's
// audio is only ever in this page's memory, until it is sent to be measured or sung again.
import * as K from "/karaoke.js";

const ST = window.songbirdStudio;
const TOKEN = document.querySelector('meta[name="studio-token"]').content;
const STORE = "songbird-web-singing";
const MAX_TAKES = 12;
const $ = (id) => document.getElementById(id);
const h = ST.h;

const S = {
  offer: null, spec: null, lyrics: null, sections: [], part: null, view: null, reel: null, words: new Map(),
  guides: new Map(), ctx: null, stream: null, recorder: null, analyser: null, buf: null, opening: null,
  mode: "idle", starting: false, src: [], t0: 0, out: 0, inn: 0, stopAt: null, chunks: [], trail: [], showTrail: null,
  recording: null, take: null, takeTrail: [], shift: 0, autoShift: 0, measuring: false, run: 0,
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

// ------------------------------------------------------------------ the panel

function build() {
  // the studio's "Sing it" box says what singing here is, and opens the singing below it
  const box = $("singTitle").closest("section");
  box.querySelector("p").textContent = "Sing along in your browser, and the song learns a little of your timing and "
    + "inflection. Your singing is measured on the computer serving this studio and deleted there at once: only numbers "
    + "about how you sang are kept, never your voice.";
  const old = $("sing"), button = old.cloneNode(true);  // the studio's own listener (the karaoke page) stays with the old one
  button.textContent = "Sing it here";
  old.replaceWith(button);
  button.addEventListener("click", open);

  const consent = h("div", { id: "singConsent" },
    h("p", { class: "lead" }, "Before you sing, here is what happens to your singing."),
    h("ul", { class: "sing-promises" },
      h("li", {}, h("b", {}, "Your voice is not kept. "), "While you sing, your microphone is recorded in this browser only. "
        + "When you send a take to be measured, it goes to the computer serving this studio, which measures it and deletes "
        + "the recording straight away. It is never saved, played to anyone or used to copy your voice."),
      h("li", {}, h("b", {}, "What's kept is numbers. "), "For each note: how early or late you came in, how long you held "
        + "it, how loud it was, how you slid into it and off it. They stay in this browser, and on that computer under a "
        + "code, with no name or address, for ", h("span", { id: "singKeepDays" }, "30"), " days after they were last used, "
        + "so the studio can sing the song your way."),
      h("li", {}, h("b", {}, "Nothing is published unless you record. "), "If you record a version sung your way, the "
        + "recording carries those numbers (rounded) inside it, as every version carries its singer's way. Anyone with the "
        + "file hears the machine's voice sing it your way: never your voice."),
      h("li", {}, h("b", {}, "You can take it back. "), "Forget my singing removes the numbers from this browser and from "
        + "that computer (not from a recording you already made).")),
    h("p", { class: "hint" }, "Wear headphones if you can, so the guide stays out of the microphone. Wrong notes are fine."),
    h("label", { class: "check" }, h("input", { type: "checkbox", id: "singAgree" }), " I understand. Let me sing."),
    h("div", { class: "actions" }, h("button", { class: "btn primary", type: "button", id: "singBegin", disabled: true }, "Start singing")));

  const work = h("div", { id: "singWork", hidden: true },
    h("div", { class: "sing-choices" },
      h("label", {}, h("span", { class: "hint" }, "Key "), h("select", { id: "singSpec", "aria-label": "The key to sing in" })),
      h("span", { class: "hint" }, "Too high or too low? Choose another key; a man and a woman can sing an octave apart."),
      h("label", { class: "check hint", title: "the browser takes the guide out of the microphone (echo cancellation)" },
        h("input", { type: "checkbox", id: "singSpeaker" }), " no headphones")),
    h("div", { class: "chips", id: "singParts", role: "group", "aria-label": "What to sing" }),
    h("p", { class: "hint", id: "singPartLabel" }),
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
    h("p", { class: "sing-status", id: "singStatus", "aria-live": "polite" }, "Loading the words…"),
    h("div", { class: "sing-review", id: "singReview", hidden: true },
      h("h3", { id: "singReviewTitle" }, "That take"),
      h("div", { class: "actions" },
        h("button", { class: "btn", type: "button", id: "singListen" }, "▶ Listen back with the guide"),
        h("button", { class: "btn primary", type: "button", id: "singMeasure" }, "Measure it"),
        h("button", { class: "btn quiet", type: "button", id: "singDiscard" }, "Sing it again")),
      h("div", { class: "sing-sync" },
        h("span", { class: "hint" }, "If your voice sits late or early against the music, slide it while you listen: "),
        h("span", { class: "hint" }, "earlier"),
        h("input", { type: "range", id: "singShift", min: "-400", max: "400", step: "5", value: "0", "aria-label": "Slide your take earlier or later" }),
        h("span", { class: "hint" }, "later"),
        h("span", { class: "hint", id: "singShiftValue" }, "as recorded")),
      h("p", { class: "hint" }, "Measure it sends this take to be measured; the recording is deleted there as soon as it has been, "
        + "and from this page too.")),
    h("div", { class: "sing-yours", id: "singYours", hidden: true },
      h("h3", {}, "Your way of singing it"),
      h("p", { class: "sing-portrait", id: "singPortrait" }),
      h("p", { class: "hint", id: "singTakes" }),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", type: "button", id: "singHear" }, "▶ Hear the song your way"),
        h("button", { class: "btn", type: "button", id: "singToRecord" }, "Record it your way"),
        h("button", { class: "link small", type: "button", id: "singForget" }, "Forget my singing"))),
    h("details", { class: "sing-about" }, h("summary", { class: "hint" }, "What happens to your singing"),
      h("p", { class: "hint", id: "singAboutText" })));

  const panel = h("section", { class: "panel websing", id: "webSing", hidden: true, "aria-labelledby": "webSingTitle" },
    h("h2", { id: "webSingTitle" }, "Sing it here"), consent, work);
  $("finishPanel").querySelector(".two").after(panel);
  $("singAboutText").textContent = [...consent.querySelectorAll("li")].map((li) => li.textContent).join(" ");

  $("singAgree").addEventListener("change", () => { $("singBegin").disabled = !$("singAgree").checked; });
  $("singBegin").addEventListener("click", () => { keep({ consent: S.offer.consent }); showWork(); });
  $("singSpec").addEventListener("change", () => chooseSpec($("singSpec").value));
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
    if (e.code === "Space" && S.mode !== "idle" && !["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) { e.preventDefault(); stop(); }
  });
  window.addEventListener("resize", () => { if (S.mode === "idle" && S.view) resting(); });
}

function say(text, warn = false) {
  const el = $("singStatus");
  el.textContent = text;
  el.classList.toggle("warn", warn);
}

async function open() {
  $("webSing").hidden = false;
  $("webSing").scrollIntoView({ behavior: "smooth", block: "start" });
  if (!S.offer || !S.offer.available) return;
  if (kept().consent === S.offer.consent) showWork();
}

function showWork() {
  $("singConsent").hidden = true;
  $("singWork").hidden = false;
  if (!window.isSecureContext || !navigator.mediaDevices) {
    say("This browser won't lend the page its microphone here: the studio needs to be opened over https.", true);
  }
  if (!S.lyrics) chooseSpec(kept().spec || S.offer.default);
}

// ------------------------------------------------------------------ what to sing: a key, a section or the whole song

function specLabel(s) {
  const tempos = new Set(S.offer.specs.map((x) => x.tempo));
  return (s.key === 0 ? "the song's own key" : K.keyLabel(s.key)) + (tempos.size > 1 ? `, ${K.speedLabel(s.tempo)}` : "");
}

async function getJSON(url) {
  const r = await fetch(url);
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.error) throw new Error(data.error || `The studio said ${r.status}.`);
  return data;
}

function words(spec) {  // a version's words and notes, fetched once
  if (!S.words.has(spec)) {
    const p = getJSON(`/api/sing/lyrics?spec=${encodeURIComponent(spec)}`);
    p.catch(() => S.words.delete(spec));
    S.words.set(spec, p);
  }
  return S.words.get(spec);
}

async function chooseSpec(spec) {
  if (!S.offer.specs.some((s) => s.id === spec)) spec = S.offer.default;
  $("singSpec").value = spec;
  keep({ spec });
  S.wanted = spec;
  controls();
  say("Loading the words…");
  let lyrics;
  try { lyrics = await words(spec); } catch (e) { say(e.message, true); return; }
  if (S.wanted !== spec) return;
  const was = S.part;
  S.spec = spec;
  S.lyrics = lyrics;
  S.sections = K.sungSections(lyrics);
  const same = was && was.index !== null ? S.sections.find((s) => s.name === was.name && s.title === was.title) : null;
  choosePart(was && was.index === null ? null : same ? same.index : S.sections.length ? S.sections[0].index : null);
  controls();
  say("Rehearse to hear it through, or record when you're ready. Start with one section: it's quicker to measure.");
  guide(spec).catch(() => {});  // fetched ahead, so it's ready when you are
}

function choosePart(index) {
  S.part = K.part(S.lyrics, index) || K.part(S.lyrics);
  view(S.lyrics, S.part);
  drawParts();
  resting();
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
  chip(null, K.WHOLE, K.WHOLE);
  $("singPartLabel").textContent = S.part.index === null ? "The whole song, from the top: about four minutes, and a minute or so to measure."
    : S.part.label;
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
  const idle = S.mode === "idle" && !S.starting, loading = !S.lyrics || S.wanted !== S.spec;
  $("singStop").disabled = S.mode === "idle";
  $("singRehearse").disabled = !idle || loading;
  $("singRecord").disabled = !idle || loading || !!S.take || S.measuring;
  $("singSpec").disabled = !idle || !!S.take || S.measuring;
  $("singMeasure").disabled = S.measuring;
  $("singDiscard").disabled = S.measuring;
  drawParts();
}

// ------------------------------------------------------------------ the guide, the microphone, the clock

async function context() {
  if (!S.ctx) S.ctx = new AudioContext({ latencyHint: "interactive" });
  await S.ctx.resume();
}

function guide(spec) {  // the melody guide, fetched and decoded once
  if (!S.guides.has(spec)) {
    const p = (async () => {
      const r = await fetch(`/api/sing/guide?spec=${encodeURIComponent(spec)}`);
      if (!r.ok) throw new Error("The guide couldn't be loaded: reload the page.");
      const bytes = await r.arrayBuffer();
      await context();
      return S.ctx.decodeAudioData(bytes);
    })();
    p.catch(() => S.guides.delete(spec));
    S.guides.set(spec, p);
  }
  return S.guides.get(spec);
}

async function chosenGuide() {
  if (!S.guides.has(S.spec)) say("Loading the guide…");
  return guide(S.spec);
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

function start(buffers, mode, from = 0, shifts = [], until = null, gains = []) {
  // play from guide time `from` (a take's buffer `shifts` seconds earlier, at `gains`), until guide time `until`
  const when = S.ctx.currentTime + 0.12;
  S.t0 = when - from;
  S.stopAt = until;
  S.out = (S.ctx.outputLatency || 0) + (S.ctx.baseLatency || 0);
  S.inn = S.stream ? S.stream.getAudioTracks()[0].getSettings().latency || 0 : 0;
  const out = mode === "listening" ? K.listenOut(S.ctx) : S.ctx.destination;
  S.src = buffers.map((buffer, i) => {
    const src = S.ctx.createBufferSource(), fader = S.ctx.createGain();
    src.buffer = buffer;
    (mode === "listening" && i > 0 ? src.connect(K.takeFilter(S.ctx)) : src).connect(fader).connect(out);
    const at = from + (shifts[i] || 0), level = gains[i] ?? 1;
    if (from > 0) { fader.gain.setValueAtTime(0, when); fader.gain.linearRampToValueAtTime(level, when + 0.03); }
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
  say(mode === "recording" ? (section ? `Recording ${S.view.part.title}. It stops by itself at the end.` : "Recording. Space or Stop to finish.")
    : mode === "listening" ? "Your take, with the guide." : "Rehearsing.");
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
  else say(S.take ? "Measure it, or sing it again." : "Rehearse again, or record a take.");
  $("singReview").hidden = !S.take;
  S.showTrail = null;
  controls();
  resting();
}

function windowEnds() {
  // the end of a section: the guide stops; a take records a moment longer, for your last note
  if (S.mode !== "recording") return stop();
  S.mode = "finishing";
  silence(S.src);
  S.src = [];
  say("That's the section…");
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
  $("singShiftValue").textContent = S.shift ? `auto-synced, ${Math.abs(Math.round(S.shift * 1000))} ms ${S.shift > 0 ? "earlier" : "later"}` : "as recorded";
  if (S.shift) keep({ nudge: Math.round(delay() * 1000 + S.shift * 1000) });  // the next take starts closer
  $("singReviewTitle").textContent = whole ? "That take" : `That take of ${part.title}`;
  const synced = S.shift ? ` Synced: your device held the sound ${Math.round(Math.abs(S.shift) * 1000)} ms longer than it said.` : "";
  say(long ? `Got it.${synced} Listen back if you like, then measure it.` : "That was short. Record again?");
}

function rehearse() {
  return starting(async () => {
    await context();
    const g = await chosenGuide();
    try { await microphone(); } catch (e) { /* rehearsing works without it: no pitch line */ }
    start([g], "rehearsing", S.part.from, [], S.part.index === null ? null : S.part.to);
  });
}

function record() {
  return starting(async () => {
    await context();
    const g = await chosenGuide();
    try { await microphone(); } catch (e) { throw new Error(`The page couldn't use your microphone (${e.message}). Allow it in the browser, then record again.`); }
    S.recording = { spec: S.spec, lyrics: S.lyrics, part: S.part, digest: S.lyrics.guide, guide: g };
    start([g], "recording", S.part.from, [], S.part.index === null ? null : S.part.to);
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
  t.gain = t.gain || K.takeGain(t.samples, t.rate);  // lifted to be heard over the guide (what's sent stays as sung)
  start([t.guide, takeBuffer()], "listening", Math.max(p.from, from), [0, S.shift - p.from], p.index === null ? null : t.to + 0.3,
        [K.UNDER, t.gain]);
}

function discard() {
  if (S.mode === "listening") stop();
  S.take = null;  // the audio goes with it
  $("singReview").hidden = true;
  controls();
  say("Ready when you are.");
}

// ------------------------------------------------------------------ measuring: the take sent, its numbers back

async function measure() {
  const t = S.take;
  if (!t || S.measuring) return;
  if (S.mode === "listening") stop();
  const earlier = (kept().measurements || []).slice(-(MAX_TAKES - 1));
  const meta = new TextEncoder().encode(JSON.stringify({
    spec: t.spec, guide: t.digest, section: t.part.index, from_s: t.part.from, to_s: t.to,
    shift_ms: Math.round(S.shift * 1000), auto_ms: Math.round((S.autoShift || 0) * 1000), device_ms: Math.round(t.device * 1000),
    earlier,
  }));
  const body = new Blob([meta, K.wavBytes(K.shifted(t.samples, t.rate, S.shift), t.rate)]);
  S.measuring = true;
  controls();
  say("Sending your take…");
  let job;
  try {
    const r = await fetch("/api/sing/take", { method: "POST", body,
      headers: { "Content-Type": "application/x-songbird-take", "X-Studio": TOKEN, "X-Sing-Meta": String(meta.length) } });
    job = await r.json().catch(() => ({ error: r.statusText }));
    if (!r.ok) throw new Error(job.error || r.statusText);
  } catch (e) {
    S.measuring = false;
    controls();
    say(`It couldn't be sent: ${e.message}`, true);
    return;
  }
  const estimate = job.estimate || 10;
  S.take = null;  // sent: this page lets go of the recording too
  $("singReview").hidden = true;
  for (;;) {
    if (job.state === "queued") {
      const wait = job.eta ? `, about ${job.eta < 90 ? `${Math.max(5, Math.round(job.eta / 5) * 5)} s` : `${Math.round(job.eta / 60)} minutes`} in all` : "";
      say(job.ahead ? `Waiting its turn: ${job.ahead} ahead of it${wait} (this studio makes one thing at a time). Then about ${estimate} s.`
        : `Measuring starts in a moment, and takes about ${estimate} s.`);
    } else if (job.state === "running") {
      say(`Listening to how you sang (about ${estimate} s)…`);
    } else break;
    await new Promise((r) => setTimeout(r, 1000));
    try { job = await ST.api(`/api/job/${job.id}`); } catch (e) { job = { state: "failed", error: e.message }; }
  }
  S.measuring = false;
  controls();
  const result = job.result || {};
  if (job.state !== "done") { say(`It couldn't be measured: ${job.error || "the studio stopped"}. Sing it again?`, true); return; }
  if (result.refused) { say(result.refused, true); return; }
  const measurements = [...earlier, result.measurement];
  keep({ measurements, phrasing: { name: result.name, json: result.phrasing, portrait: result.portrait } });
  own(result.name, result.phrasing);
  ST.setEdit("phrasing", result.name, "Sing it your way");
  showYours();
  const skipped = (result.skipped || []).length ? " Some of it sat too far from the guide's key to measure." : "";
  say(`Measured, and deleted.${skipped} The song is sung your way now: hear it, sing another part, or record it.`);
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
  $("singPortrait").textContent = k.phrasing.portrait || "";
  $("singTakes").textContent = `Made from ${n} take${n === 1 ? "" : "s"}. Each take you measure joins it (up to ${MAX_TAKES}): `
    + "sing another section, or the same one again.";
}

async function forget() {
  const button = $("singForget");
  if (!button.dataset.sure) {
    button.dataset.sure = "1";
    button.textContent = "Forget it everywhere? Press again";
    setTimeout(() => { delete button.dataset.sure; button.textContent = "Forget my singing"; }, 5000);
    return;
  }
  delete button.dataset.sure;
  button.textContent = "Forget my singing";
  const name = (kept().phrasing || {}).name;
  try { if (name) await ST.api("/api/sing/forget", { name }); } catch (e) { say(`It couldn't be forgotten there: ${e.message}`, true); return; }
  keep({ measurements: null, phrasing: null });
  ST.ownPhrasings.splice(0, ST.ownPhrasings.length);
  if (ST.state.edits.phrasing === name) ST.setEdit("phrasing", null, "Forget my singing");
  else ST.renderCards();
  showYours();
  say("Forgotten: your numbers are gone from this browser and from the studio. A recording you made keeps its own copy.");
}

// ------------------------------------------------------------------ starting

async function restore() {
  // a way of singing made on an earlier visit: offered again, and kept again there (the studio keeps it by its
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

async function init() {
  build();
  try { S.offer = await ST.api("/api/sing/offer"); } catch (e) { S.offer = { available: false, why: e.message }; }
  if (!S.offer.available) {
    $("sing").disabled = true;
    $("singNote").textContent = S.offer.why || "Singing isn't available here.";
    return;
  }
  $("singKeepDays").textContent = String(S.offer.keep_days);
  $("singAboutText").textContent = [...$("singConsent").querySelectorAll("li")].map((li) => li.textContent).join(" ");
  for (const s of S.offer.specs) $("singSpec").append(h("option", { value: s.id }, specLabel(s)));
  showYours();
  restore();
}

init();
