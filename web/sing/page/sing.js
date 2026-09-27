// The sing-along page for singers anywhere (web/sing): the karaoke's way of recording
// (tools/karaoke.js, shared with tools/karaoke.html), behind an invitation. A singer agrees to
// the release and says who they are (an email, so they can be sent their own page), chooses
// what they'll hear (which verses, the key, the speed, the guide), and sings one section at a
// time or the whole song. A take is cut from the frame the guide reached them at its start, in
// the same audio clock as the playback, synced against that part's notes, and sent as a 16-bit
// mono WAV at the device's rate with a small sidecar: the version and section it was sung to
// and where it starts and ends in the guide, the name to credit (if any), when the release was
// agreed to, the device's delays, and which guide was heard.

import * as K from "./karaoke.js";

const $ = id => document.getElementById(id);
const TOKEN = /^[A-Za-z0-9_-]{24}$/; // an invitation, or a singer
const S = { invite: "", sid: null, info: null, song: null, yours: null, me: null, suggested: null, want: null, spec: null,
            lyrics: null, sections: [], part: null, view: null, reel: null, words: {}, ctx: null, guides: {}, loading: {},
            mode: "idle", t0: 0, out: 0, inn: 0, stopAt: null, chunks: [], trail: [], showTrail: null, recording: null, take: null,
            shift: 0, consentAt: null, wordsAt: null, busy: false, wake: null, interrupted: false, src: [], run: 0, sentWords: [] };
const MIXES = {
  melody: ["The tune alone", "on a soft whistle, with a quiet pulse on the beats"],
  full: ["The whole song", "the machine's singer and its band"],
  voice: ["The machine's singer alone", "no band"],
};

const saved = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback; } catch (e) { return fallback; } };
const save = (key, value) => { try { localStorage.setItem(key, value); return true; } catch (e) { return false; } };
const forget = key => { try { localStorage.removeItem(key); } catch (e) {} };
const mine = key => `songbird-sing-${key}:${S.invite}`; // per invitation: a phone may be passed round
const enc = encodeURIComponent;

/* ---------- starting up ---------- */

async function init() {
  S.invite = decodeURIComponent(location.pathname.split("/")[2] || "");
  const given = new URLSearchParams(location.hash.slice(1)).get("s"); // /i/<invite>#s=<singer>: back as that singer
  if (given && TOKEN.test(given)) {
    S.sid = given;
    if (save(mine("sid"), given)) history.replaceState(null, "", location.pathname); // kept here, not left in the address
  } else {
    const kept = saved(mine("sid"), "");
    S.sid = TOKEN.test(kept) ? kept : null;
  }
  try {
    S.info = await api("GET", `invite/${enc(S.invite)}`);
  } catch (e) {
    return closed(e.code ? e.code : "error", e.code ? e.message : "The page couldn't reach the server. Check your connection and reload it.");
  }
  if (isClosed()) return closed("closed");
  if (S.info.state !== "open") return closed(S.info.state);
  if (S.sid) {
    try {
      S.yours = await api("GET", `yours/${enc(S.sid)}`);
      S.me = { name: S.yours.name || "", credit: S.yours.credit !== false };
    } catch (e) {
      if (e.status === 404 || e.status === 410) { S.sid = null; forget(mine("sid")); } // withdrawn, or not this invitation's
    }
  }
  if (!S.sid && S.info.people && S.info.joined >= S.info.people) return closed("full");
  try {
    S.song = await api("GET", `song/${enc(S.invite)}`);
  } catch (e) {
    return closed(e.code || "error", e.code ? e.message : "The page couldn't reach the server. Check your connection and reload it.");
  }
  $("title").textContent = S.song.title;
  document.title = `Sing ${S.song.title}`;
  showCloses();

  // what you sang to last time on this invitation, if it's still on offer; else the set suggested
  // for you when you joined; else the song's own
  const d = S.song.default || {}, was = K.parseSpec(saved(mine("spec"), ""));
  S.suggested = saved(mine("set"), "") || null;
  S.want = was ? { set: was.set, key: was.key, tempo: was.tempo } : { set: S.suggested || d.set, key: d.key ?? 0, tempo: d.tempo ?? 100 };
  drawMixes();

  $("name").value = saved(mine("name"), "");
  $("email").value = saved(mine("email"), "");
  const credit = saved("songbird-sing-credit", "yes");
  document.querySelectorAll('input[name="credit"]').forEach(r => { r.checked = r.value === credit; });
  try { // the release, agreed to on this device before, if its text is still the same
    const agreed = JSON.parse(saved(mine("consent"), "null"));
    if (agreed && agreed.text === $("consentText").dataset.digest && agreed.at) { $("agree").checked = true; S.consentAt = agreed.at; }
  } catch (e) {}
  if (S.sid) showJoined();

  $("loading").hidden = true;
  $("steps").hidden = false;
  drawTakes();
  drawWords();
  controls();
  await chooseVersion(K.nearestSpec(offered(), S.want));
  if (S.mode === "idle" && !S.take) say(readyText());
}

function readyText() {
  if (!ready()) return "Agree to the release and say who you are (steps 1 and 2) to start.";
  return S.part && S.part.index !== null ? `Listen first, or record ${S.part.title} when you're ready.` : "Listen first, or record when you're ready.";
}

function closed(state, message) {
  $("loading").hidden = true;
  $("steps").hidden = true;
  $("closes").hidden = true;
  $("closed").hidden = false;
  const closes = S.info && S.info.closes ? ` (${K.closingTime(S.info.closes)})` : "";
  $("closedWhy").textContent = state === "closed" ? `Singing has closed${closes}. Thank you for coming by: the song is being made from everyone's singing now.`
    : state === "full" ? "Everyone this invitation was for has joined. If one of them is you, open your own page (the link you kept, or the one in your email) and press Sing more."
    : state === "done" ? "You've finished singing on this invitation. Thank you!"
    : state === "expired" ? "This invitation has expired. If you'd still like to sing, write to Milo (below)."
    : state === "error" ? message
    : "This invitation isn't open. If you'd still like to sing, write to Milo (below).";
  if (S.sid) {
    $("closedYours").hidden = false;
    $("closedLink").href = $("closedLink").textContent = pageUrl();
  }
}

function isClosed() {
  const at = S.info && Date.parse(S.info.closes);
  return Number.isFinite(at) && Date.now() >= at;
}

function showCloses() {
  // when singing closes, on the artist's clock and the singer's; and what that means for their page
  const at = S.info && S.info.closes, when = at ? `${K.moment(at, K.ARTIST_ZONE)} Pacific` : "Sunday at 10 PM Pacific";
  if (at) {
    $("closes").textContent = `Singing closes ${K.closingTime(at)}.`;
    $("closes").hidden = false;
    // a page left open past it says so, rather than failing at the next take (once nothing is being sung or sent)
    const left = Date.parse(at) - Date.now();
    const later = () => {
      if (!$("thanks").hidden) return;
      if (S.mode === "idle" && !S.take && !queue.some(q => q.state === "sending")) closed("closed");
      else setTimeout(later, 30000);
    };
    if (left > 0 && left < 2 ** 31) setTimeout(later, left + 1000);
  }
  const by = deleteBy();
  $("keepNote").textContent = `Keep this link: it's your own page. Your version will appear there in a few days, before ${by}, `
    + `and you can delete your recordings there. Until singing closes (${when}) you can also withdraw; after that, what you gave is part of the song.`;
  $("thanksNote").textContent = `There you can delete your recordings or withdraw until singing closes (${when}). After that, what you gave `
    + `is part of the song, though you can still delete the recordings until ${by}.`;
  $("thanksText").textContent = `Thank you for singing! Your version will appear on your own page in a few days, before ${by}.`;
}

function deleteBy() { // the day recordings are deleted by: the singer's own record says, else the contract's
  const at = S.yours && Date.parse(S.yours.delete_by);
  if (!Number.isFinite(at)) return "30 September";
  return new Intl.DateTimeFormat("en-GB", { timeZone: K.ARTIST_ZONE, day: "numeric", month: "long" }).format(new Date(at));
}

async function api(method, path, body) {
  const r = await fetch(`/api/${path}`, { method, body, headers: body ? { "Content-Type": "application/json" } : {} });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = new Error(data.message || `The server said ${r.status}.`);
    e.code = data.error;
    e.status = r.status;
    throw e;
  }
  return data;
}

function status(html) { $("status").innerHTML = html; }
function say(text) { $("status").textContent = text; }
function warn(text) { status('<span class="warn"></span>'); $("status").firstChild.textContent = text; }

/* ---------- 1 and 2: the release, and who you are ---------- */

function ready() { return !!S.sid && $("agree").checked && !!S.consentAt; }

$("agree").addEventListener("change", () => {
  S.consentAt = $("agree").checked ? new Date().toISOString() : null;
  if (S.consentAt) save(mine("consent"), JSON.stringify({ at: S.consentAt, text: $("consentText").dataset.digest }));
  else forget(mine("consent"));
  controls();
  if (S.mode === "idle" && !S.take) say(readyText());
});
$("name").addEventListener("input", () => save(mine("name"), $("name").value.trim()));
$("email").addEventListener("input", () => { $("email").classList.remove("missing"); save(mine("email"), $("email").value.trim()); });
document.querySelectorAll('input[name="credit"]').forEach(r => r.addEventListener("change", () => save("songbird-sing-credit", r.value)));

$("join").onclick = async () => {
  if (!$("agree").checked || !S.consentAt) { $("joinNote").textContent = "Tick the release first (step 1)."; return; }
  const email = $("email").value.trim();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    $("email").classList.add("missing");
    $("email").focus();
    $("joinNote").textContent = "Put in your email, so you can be sent your own page.";
    return;
  }
  const name = $("name").value.trim(), credit = document.querySelector('input[name="credit"]:checked').value === "yes";
  S.busy = true;
  controls();
  $("joinNote").textContent = "Just a moment…";
  try {
    const r = await api("POST", `join/${enc(S.invite)}`, JSON.stringify({
      email, name, credit, notify: $("notify").checked,
      consent: { agreed: true, at: S.consentAt, text: $("consentText").dataset.digest },
    }));
    if (!TOKEN.test(r.singer || "")) throw new Error("The server didn't say who you are. Try again.");
    S.sid = r.singer;
    if (typeof r.page === "string" && r.page.startsWith("/")) S.page = r.page;
    save(mine("sid"), r.singer);
    S.me = { name, credit };
    $("joinNote").textContent = "";
    if (r.set) {
      S.suggested = r.set;
      save(mine("set"), r.set);
      if (!saved(mine("spec"), "")) { S.want.set = r.set; chooseVersion(K.nearestSpec(offered(), S.want, "set")); } // not chosen yet: the one suggested
    }
    drawSets();
    showJoined(true);
  } catch (e) {
    $("joinNote").textContent = e.message;
    if (e.status === 410 && isClosed()) closed("closed");
  }
  S.busy = false;
  controls();
  if (S.mode === "idle" && !S.take) say(readyText());
};

function pageUrl() { return new URL(S.page || `/y/${S.sid}`, location.origin).href; } // their own page

function showJoined(now = false) {
  $("joinForm").hidden = true;
  $("joined").hidden = false;
  const name = S.me && S.me.name;
  $("joinedAs").textContent = now ? (name ? `Thank you, ${name}. You're in.` : "Thank you. You're in.")
    : name ? `Welcome back, ${name}.` : "Welcome back.";
  $("pageLink").href = $("pageLink").textContent = $("thanksLink").href = $("thanksLink").textContent = pageUrl();
  $("notYou").hidden = now; // a phone passed round: the next singer starts as themselves
  $("notYouName").textContent = name || "you";
}

$("restart").onclick = () => {
  for (const key of ["sid", "consent", "spec", "set", "name", "email"]) forget(mine(key));
  location.reload();
};

async function copy(button) {
  const url = pageUrl();
  try {
    await navigator.clipboard.writeText(url);
    button.textContent = "Copied ✓";
  } catch (e) { // no clipboard: select it, to copy by hand
    const range = document.createRange();
    range.selectNodeContents(button.previousElementSibling);
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    button.textContent = "Selected: copy it";
  }
  setTimeout(() => { button.textContent = "Copy"; }, 2500);
}
$("copyLink").onclick = () => copy($("copyLink"));
$("thanksCopy").onclick = () => copy($("thanksCopy"));

/* ---------- what can be pressed ---------- */

function controls() {
  // the steps after the release wait for it, and those after "You" for joining; nothing else while
  // playing; the version and section stay put while a take waits to be kept or redone
  const agreed = $("agree").checked, joined = ready(), idle = S.mode === "idle", locked = !joined || !idle || !!S.take;
  document.querySelectorAll(".step[data-needs]").forEach(step => step.classList.toggle("waiting", step.dataset.needs === "agree" ? !agreed : !joined));
  for (const id of ["email", "name", "notify", "join"]) $(id).disabled = !agreed || S.busy;
  document.querySelectorAll('input[name="credit"]').forEach(r => { r.disabled = !agreed || S.busy; });
  $("mic").disabled = !joined || !idle || !!S.recorder;
  $("calibrate").disabled = !joined || !idle;
  $("calibrateBox").hidden = !S.recorder;
  document.querySelectorAll('input[name="set"], input[name="speed"], input[name="mix"]').forEach(r => { r.disabled = locked; });
  const keys = [...((S.song && S.song.keys) || [])].sort((a, b) => a - b);
  $("lower").disabled = locked || !S.want || S.want.key <= keys[0];
  $("higher").disabled = locked || !S.want || S.want.key >= keys[keys.length - 1];
  $("rehearse").disabled = $("record").disabled = !joined || !idle || !S.lyrics || S.wanted !== S.spec;
  $("stop").disabled = idle || S.mode === "calibrating";
  $("listen").disabled = !idle;
  $("keep").disabled = $("discard").disabled = !(idle || S.mode === "listening");
  $("shift").disabled = !joined;
  $("wordsText").disabled = !joined;
  $("wordsAgree").disabled = !joined;
  $("wordsSend").disabled = !joined || S.busy || !$("wordsAgree").checked || !$("wordsText").value.trim();
  $("done").disabled = !joined || !idle;
  $("next").disabled = !joined || !idle;
  drawParts();
}

/* ---------- 4: what you'll hear ---------- */

function offered() { return Object.keys((S.song && S.song.guides) || {}); }

function mixes() { return Array.isArray(S.song.mixes) ? S.song.mixes : Object.keys(S.song.mixes || {}); }

function radio(box, name, value, title, about, checked, onchange) {
  const label = document.createElement("label");
  const input = document.createElement("input");
  input.type = "radio";
  input.name = name;
  input.value = value;
  input.checked = checked;
  input.addEventListener("change", onchange);
  const text = document.createElement("span");
  const strong = document.createElement("strong");
  strong.textContent = title;
  text.appendChild(strong);
  if (about) {
    const small = document.createElement("small");
    small.textContent = about;
    text.appendChild(small);
  }
  label.append(input, text);
  box.appendChild(label);
  return label;
}

function drawSets() {
  const sets = S.song.sets || [], box = $("sets");
  $("setBox").hidden = sets.length < 2;
  box.innerHTML = "";
  for (const set of sets) {
    const label = radio(box, "set", set.id, set.name, set.about, S.want.set === set.id, () => pick({ set: set.id }, "set"));
    if (set.id === S.suggested) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "suggested for you";
      label.querySelector("strong").append(" ", badge);
    }
  }
}

function drawSpeeds() {
  const tempos = S.song.tempos || [], box = $("speeds");
  $("speedBox").hidden = tempos.length < 2;
  box.innerHTML = "";
  for (const t of tempos) {
    const words = K.speedLabel(t);
    radio(box, "speed", t, words[0].toUpperCase() + words.slice(1), "", S.want.tempo === t, () => pick({ tempo: t }, "tempo"));
  }
}

function drawPickers() {
  drawSets();
  drawSpeeds();
  $("keyBox").hidden = (S.song.keys || []).length < 2;
  $("keyName").textContent = K.keyLabel(S.want.key);
  controls();
}

function drawMixes() {
  const box = $("mixes"), all = mixes(), fallback = (S.song.default && S.song.default.mix) || all[0], chosen = saved("songbird-sing-mix", fallback);
  box.innerHTML = "";
  for (const m of all) {
    const [name, about] = MIXES[m] || [m, ""];
    radio(box, "mix", m, name, about, m === (all.includes(chosen) ? chosen : fallback), () => { save("songbird-sing-mix", m); noteVersion(); });
  }
}

function mix() {
  const on = document.querySelector('input[name="mix"]:checked');
  return on ? on.value : mixes()[0];
}

function pick(change, keep) {
  // a new version chosen: the nearest on offer that keeps what was just changed, remembered for next time
  if (S.mode !== "idle" || S.take) return drawPickers();
  Object.assign(S.want, change);
  const spec = K.nearestSpec(offered(), S.want, keep), got = K.parseSpec(spec);
  if (spec) save(mine("spec"), spec);
  S.nearest = got && ["set", "key", "tempo"].some(k => got[k] !== S.want[k]); // not every mix of them is on offer
  chooseVersion(spec);
}

function stepKey(dir) {
  const keys = [...S.song.keys].sort((a, b) => a - b);
  const i = keys.indexOf(S.want.key);
  pick({ key: keys[Math.max(0, Math.min(keys.length - 1, (i < 0 ? keys.indexOf(0) : i) + dir))] }, "key");
}
$("lower").onclick = () => stepKey(-1);
$("higher").onclick = () => stepKey(1);

async function chooseVersion(spec) {
  // a version's words and notes (small, at once); its guide loads when you listen or record
  if (!spec) { warn("There's no guide to sing to yet. Try again later."); return; }
  const p = K.parseSpec(spec);
  S.wanted = spec; // until its words are here, nothing is sung (the display would change under the take)
  S.want = { set: p.set, key: p.key, tempo: p.tempo }; // what's shown is what's on offer
  drawPickers();
  let lyrics;
  try {
    lyrics = await lyricsFor(spec);
  } catch (e) {
    if (S.wanted !== spec) return;
    S.wanted = S.spec; // back to the one we have, if any
    const q = K.parseSpec(S.spec);
    if (q) { S.want = { set: q.set, key: q.key, tempo: q.tempo }; drawPickers(); }
    warn(e.message);
    return;
  }
  if (S.wanted !== spec) return; // chosen again since
  const was = S.part;
  S.spec = spec;
  S.lyrics = lyrics;
  S.sections = K.sungSections(lyrics);
  // the same section if this version has it (the second verse stays the second verse), else the first not yet sung
  const same = was && was.index !== null ? S.sections.find(s => s.name === was.name && s.title === was.title) : null;
  const first = K.nextSection(S.sections, null, sungHere());
  choosePart(was && was.index === null ? null : same ? same.index : first ? first.index : S.sections.length ? S.sections[0].index : null);
  noteVersion();
  controls();
  if (S.mode === "idle" && !S.take) say(readyText());
}

function lyricsFor(spec) { // a version's words and notes, fetched once
  if (!S.words[spec]) {
    S.words[spec] = api("GET", `lyrics/${enc(S.invite)}/${enc(spec)}`);
    S.words[spec].catch(() => { delete S.words[spec]; });
  }
  return S.words[spec];
}

function noteVersion() {
  // how much a new version's guide will take to fetch, before it's fetched
  const g = S.song.guides[S.spec], m = g && g.mixes && g.mixes[mix()];
  const nearest = S.nearest ? `Not every mix of these is ready, so here's the nearest: ${K.specText(S.spec, S.song.sets) || "as written"}. ` : "";
  $("versionNote").textContent = !m ? "" : nearest + (S.guides[`${S.spec}/${mix()}`] ? "This version is loaded and ready."
    : `This version's guide is ${(m.bytes / 1e6).toFixed(1)} MB; it loads when you listen or record.`);
}

/* ---------- 5: one section, or the whole song ---------- */

function choosePart(index) {
  S.part = K.part(S.lyrics, index) || K.part(S.lyrics);
  $("nextBox").hidden = true;
  view(S.lyrics, S.part);
  drawParts();
  resting();
}

function sungHere() {
  // what you've sent of this version, earlier or on this visit: section indices, and "all" for the whole song
  const done = new Set();
  for (const t of (S.yours && S.yours.takes) || []) if (t.spec === S.spec) done.add(t.section ?? "all");
  for (const q of queue) if (q.state === "sent" && q.info.spec === S.spec) done.add(q.info.section ?? "all");
  return done;
}

function drawParts() {
  const box = $("parts");
  box.innerHTML = "";
  if (!S.lyrics || !S.part) return;
  if (!S.sections.length) { $("partLabel").textContent = ""; $("record").textContent = "● Record"; return; } // the whole song only
  const done = sungHere(), locked = !ready() || S.mode !== "idle" || !!S.take;
  const chip = (index, title, label) => {
    const b = document.createElement("button");
    const sung = done.has(index ?? "all");
    b.type = "button";
    b.className = "chip";
    b.textContent = title + (sung ? " ✓" : "");
    b.title = label + (sung ? " (sent)" : "");
    b.setAttribute("aria-pressed", String(S.part.index === index));
    b.disabled = locked;
    b.onclick = () => choosePart(index);
    box.appendChild(b);
  };
  for (const s of S.sections) chip(s.index, s.title, K.sectionLabel(s));
  chip(null, K.WHOLE, K.WHOLE);
  $("partLabel").textContent = S.part.index === null ? "The whole song, from the top." : S.part.label;
  $("record").textContent = S.part.index === null ? "● Record the whole song" : `● Record ${S.part.title}`;
}

function view(lyrics, part) {
  // what the lane and the words show; one section shows only its own notes and lines
  const notes = K.notesOf(lyrics);
  S.view = { lyrics, part, notes: part.index === null ? notes : K.inWindow(notes, part.from, part.to), ...K.range(notes) };
  S.reel = new K.Reel($("reel"), lyrics, part.index === null ? {} : { from: part.from, to: part.to, name: part.name, end: "That's the section." });
}

function resting() {
  if (!S.view) return;
  S.reel.show(S.view.part.from);
  drawLane(K.restAt(S.view.notes, S.view.part.from));
  $("progress").style.width = "0";
}

function drawLane(pos) {
  K.drawLane($("lane"), S.view.notes, S.view.lo, S.view.hi, pos, S.showTrail);
}

function delay() { // what this device adds beyond what it reports, from a calibration or earlier takes
  return (parseFloat(saved("songbird-sing-nudge", "0")) || 0) / 1000;
}

function learn(ms) {
  save("songbird-sing-nudge", String(Math.round(ms)));
}

/* ---------- sound ---------- */

async function context() {
  // the audio clock everything is timed by, at the device's own rate; one running far above what a
  // voice needs (some desktop interfaces run at 176.4 or 192 kHz) is asked for 48 kHz instead
  if (!S.ctx) {
    S.ctx = new AudioContext({ latencyHint: "interactive" });
    if (S.ctx.sampleRate > 96000) {
      await S.ctx.close();
      S.ctx = new AudioContext({ latencyHint: "interactive", sampleRate: 48000 });
    }
  }
  if (S.ctx.state !== "running") await S.ctx.resume(); // after a call or the lock screen, too
}

async function guide(spec, which) {
  // a version's guide, decoded, and how much silence the decoder put in front of it; a phone holds
  // one decoded guide, and the one a take awaits
  const key = `${spec}/${which}`;
  await context();
  if (!S.guides[key]) {
    const m = S.song.guides[spec].mixes[which];
    status(`Loading the guide (${(m.bytes / 1e6).toFixed(1)} MB)…`);
    if (!S.loading[key]) {
      S.loading[key] = (async () => {
        const r = await fetch(`/api/guide/${enc(S.invite)}/${enc(spec)}/${enc(which)}`);
        if (!r.ok) throw new Error("The guide didn't load. Check the connection and try again.");
        const buffer = await S.ctx.decodeAudioData(await r.arrayBuffer());
        const n = Math.min(buffer.length, Math.ceil(buffer.sampleRate * 3));
        const mono = new Float32Array(n);
        for (let c = 0; c < buffer.numberOfChannels; c++) {
          const d = buffer.getChannelData(c);
          for (let i = 0; i < n; i++) mono[i] += d[i] / buffer.numberOfChannels;
        }
        return { buffer, offset: K.decodeOffset(mono, buffer.sampleRate, m.env, m.frame) };
      })();
      S.loading[key].finally(() => { delete S.loading[key]; }).catch(() => {});
    }
    S.guides[key] = await S.loading[key];
    for (const other of Object.keys(S.guides)) {
      if (other !== key && other !== (S.take && S.take.key)) delete S.guides[other];
    }
    noteVersion();
  }
  return S.guides[key];
}

async function microphone() {
  if (S.recorder) return;
  if (!window.isSecureContext || !navigator.mediaDevices) throw new Error("This page needs a secure (https) connection for the microphone.");
  try { // the microphone first: a phone reconfigures its audio when it opens, and the clock is made after
    S.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
  } catch (e) {
    throw new Error(e.name === "NotAllowedError" ? "The browser didn't allow the microphone. Allow it for this page (in the address bar, or your phone's settings) and try again."
      : e.name === "NotFoundError" ? "No microphone was found." : `The microphone didn't start (${e.message}).`);
  }
  if (S.ctx) { // made before the microphone (to listen first): make it again now it's open
    try { await S.ctx.close(); } catch (e) {}
    S.ctx = null;
  }
  await context();
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
  S.recorder.port.onmessage = e => {
    if (S.mode === "recording" || S.mode === "finishing" || S.mode === "calibrating") S.chunks.push(e.data);
    $("level").style.width = Math.min(100, 140 * e.data.peak) + "%";
  };
  $("mic").textContent = "Microphone on"; // however it was opened: this button, recording or measuring
  $("micNote").textContent = `Recording at ${S.ctx.sampleRate} Hz. If the level doesn't move when you sing, check the microphone.`;
  controls();
}

$("mic").onclick = async () => {
  $("mic").disabled = true;
  try {
    await microphone();
  } catch (e) {
    $("micNote").innerHTML = `<span class="warn"></span>`;
    $("micNote").firstChild.textContent = e.message;
  }
  controls();
};

async function start(buffers, mode, from = 0, shifts = [], until = null) {
  // play from guide time `from` (each buffer `shifts` seconds earlier), until guide time `until` if given
  await context();
  const when = S.ctx.currentTime + 0.12;
  S.t0 = when - from;
  S.stopAt = until;
  S.out = (S.ctx.outputLatency || 0) + (S.ctx.baseLatency || 0);
  S.inn = S.stream ? S.stream.getAudioTracks()[0].getSettings().latency || 0 : 0;
  S.src = buffers.map((buffer, i) => {
    const src = S.ctx.createBufferSource(), fader = S.ctx.createGain();
    src.buffer = buffer;
    src.connect(fader).connect(S.ctx.destination);
    const at = from + (shifts[i] || 0); // a positive shift plays the buffer that much earlier
    if (from > 0) { fader.gain.setValueAtTime(0, when); fader.gain.linearRampToValueAtTime(1, when + 0.03); } // in mid-song: no click
    if (at >= 0) src.start(when, at); else src.start(when - at);
    src.fader = fader;
    return src;
  });
  S.src[0].onended = () => { if (S.mode !== "idle") stop(); };
  S.chunks = [];
  S.trail = [];
  S.showTrail = mode === "listening" ? S.take.trail.map(p => ({ t: p.t - S.shift, m: p.m })) : S.trail;
  S.mode = mode;
  S.interrupted = false;
  $("review").hidden = true;
  $("nextBox").hidden = true;
  controls();
  const section = S.view.part.index !== null;
  say(mode === "recording" ? (section ? `Recording ${S.view.part.title}. It stops by itself at the end.` : "Recording. Sing along; press Stop when you're finished.")
    : mode === "listening" ? "Your take, with the guide." : "Listening. Sing along if you like.");
  const run = ++S.run; // one drawing loop per playback
  const tick = () => {
    if (run !== S.run || S.mode === "idle" || S.mode === "finishing" || S.mode === "calibrating") return;
    const pos = S.ctx.currentTime - S.t0 - S.out;
    if (S.stopAt !== null && pos >= S.stopAt) return windowEnds();
    if (S.mode !== "listening") listen(pos);
    const { from: a, to: b } = S.view.part;
    $("progress").style.width = Math.max(0, Math.min(100, (100 * (pos - a)) / (b - a))) + "%";
    S.reel.show(pos);
    drawLane(pos);
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function silence(sources) { // stop playing, with a short fade rather than a click
  const now = S.ctx.currentTime;
  for (const s of sources) {
    s.onended = null;
    try {
      s.fader.gain.cancelScheduledValues(now);
      s.fader.gain.setValueAtTime(s.fader.gain.value, now);
      s.fader.gain.linearRampToValueAtTime(0, now + 0.08);
      s.stop(now + 0.1);
    } catch (e) {}
  }
}

function stop() {
  const was = S.mode;
  if (was === "idle" || was === "calibrating") return;
  const pos = S.ctx.currentTime - S.t0 - S.out;
  S.mode = "idle";
  clearTimeout(S.finishing);
  silence(S.src);
  S.src = [];
  if (S.wake) { S.wake.release().catch(() => {}); S.wake = null; }
  if (was === "recording" || was === "finishing") finishTake(was === "finishing" ? S.stopAt : pos);
  else say(S.take ? "Keep it and send it, or redo it." : readyText());
  $("review").hidden = !S.take;
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

function listen(pos) {
  if (!S.analyser) return;
  S.analyser.getFloatTimeDomainData(S.buf);
  S.trail.push({ t: pos - S.inn - delay() - 0.02, m: K.pitchAt(S.buf, S.ctx.sampleRate) });
}

document.addEventListener("visibilitychange", () => { if (document.hidden && S.mode === "recording") S.interrupted = true; });

/* ---------- a take ---------- */

$("rehearse").onclick = async () => {
  if (!ready()) return;
  const p = S.part;
  try {
    const g = await guide(S.spec, mix());
    if (S.mode !== "idle") return;
    await start([g.buffer], "rehearsing", p.from, [g.offset], p.index === null ? null : p.to);
  } catch (e) { warn(e.message); }
};

$("record").onclick = async () => {
  if (!ready()) { warn("Agree to the release and say who you are first (steps 1 and 2)."); return; }
  if (isClosed()) return closed("closed");
  const spec = S.spec, which = mix(), p = S.part;
  let g;
  try { await microphone(); g = await guide(spec, which); } catch (e) { warn(e.message); return; }
  if (S.mode !== "idle") return;
  try { S.wake = navigator.wakeLock ? await navigator.wakeLock.request("screen") : null; } catch (e) { S.wake = null; }
  S.recording = { spec, mix: which, key: `${spec}/${which}`, offset: g.offset, lyrics: S.lyrics, part: p };
  await start([g.buffer], "recording", p.from, [g.offset], p.index === null ? null : p.to);
};

$("stop").onclick = stop;
document.addEventListener("keydown", e => {
  if (e.code === "Space" && S.mode !== "idle" && S.mode !== "calibrating" && !["INPUT", "TEXTAREA"].includes(e.target.tagName)) {
    e.preventDefault();
    stop();
  }
});
window.addEventListener("resize", () => { if (S.mode === "idle" && S.view) resting(); });

function finishTake(stoppedAt) {
  const rate = S.ctx.sampleRate, r = S.recording, part = r.part, whole = part.index === null;
  const first = K.firstFrame(S.t0, S.out, S.inn, delay(), rate, part.from); // sample 0 is guide time part.from
  const samples = whole ? K.assemble(S.chunks, first) : K.cutTake(S.chunks, first, rate, part.to - part.from + K.TAIL);
  S.chunks = [];
  // where the take ends, in guide time: the section's (or the song's) end, or wherever it was stopped before that
  const to = Math.round(Math.max(part.from, Math.min(part.to, stoppedAt)) * 1000) / 1000;
  const long = samples.length / rate > 5, trail = S.trail.slice(), notes = K.notesOf(r.lyrics);
  const auto = long ? (whole ? K.autoSync(trail, notes) : K.autoSyncWindow(trail, notes, part.from, part.to)) : 0;
  S.take = long ? { ...r, samples, rate, to, trail, buffer: null, out: S.out, inn: S.inn, device: delay(), auto } : null;
  S.shift = auto;
  $("shift").value = String(Math.max(-400, Math.min(400, -S.shift * 1000)));
  $("shiftValue").textContent = S.shift ? `lined up automatically: ${Math.abs(Math.round(S.shift * 1000))} ms ${S.shift > 0 ? "earlier" : "later"}` : "as recorded";
  if (S.shift) learn(delay() * 1000 + S.shift * 1000); // so the next take starts closer
  $("reviewTitle").textContent = whole ? "That take" : `That take of ${part.title}`;
  const note = S.interrupted ? ' <span class="warn">The page went into the background while you sang, so this take may have gaps: listen before you keep it.</span>' : "";
  status(long ? `Got it. Listen back, then keep it or try again.${note}` : "That was short. Record again?");
}

function takeBuffer() {
  if (!S.take.buffer) {
    S.take.buffer = S.ctx.createBuffer(1, S.take.samples.length, S.take.rate);
    S.take.buffer.copyToChannel(S.take.samples, 0);
  }
  return S.take.buffer;
}

async function listenFrom(from) {
  // the take as it would be sent, with the guide it was sung to: its sample 0 is guide time part.from
  const t = S.take, p = t.part;
  silence(S.src);
  S.src = [];
  try {
    const g = S.guides[t.key] || await guide(t.spec, t.mix);
    await start([g.buffer, takeBuffer()], "listening", Math.max(p.from, from), [t.offset, S.shift - p.from], p.index === null ? null : t.to + 0.3);
  } catch (e) { S.mode = "idle"; controls(); warn(e.message); }
}

$("listen").onclick = () => { if (S.take) listenFrom(0); };
$("shift").oninput = () => {
  const ms = parseFloat($("shift").value);
  S.shift = -ms / 1000; // slid left, the voice comes earlier
  $("shiftValue").textContent = ms ? `${Math.abs(ms)} ms ${ms < 0 ? "earlier" : "later"}` : "as recorded";
};
$("shift").onchange = () => { if (S.mode === "listening" && S.take) listenFrom(S.ctx.currentTime - S.t0 - S.out - 1.0); };
$("discard").onclick = () => {
  if (S.mode === "listening") stop();
  S.take = null;
  $("review").hidden = true;
  controls();
  say(S.part.index === null ? "Ready when you are." : `Ready when you are: ${S.part.title} again, or choose another.`);
};

$("keep").onclick = async () => {
  const t = S.take;
  if (!t) return;
  if (!ready()) { warn("Tick the release (step 1) to send a take."); return; }
  if (S.mode === "listening") stop();
  const me = S.me || { name: $("name").value.trim(), credit: document.querySelector('input[name="credit"]:checked').value === "yes" };
  const info = {
    song: S.song.song, guide: S.song.guides[t.spec].guide, spec: t.spec, mix: t.mix, rate: t.rate,
    from_s: t.part.from, to_s: t.to, section: t.part.index,
    name: me.name, credit: me.credit,
    consent: { agreed: true, at: S.consentAt, text: $("consentText").dataset.digest },
    shift_ms: Math.round(S.shift * 1000), auto_ms: Math.round((t.auto || 0) * 1000), device_ms: Math.round(t.device * 1000),
    decode_ms: Math.round(t.offset * 10000) / 10, out_ms: Math.round(t.out * 1000), in_ms: Math.round(t.inn * 1000),
  };
  const byEar = S.shift - (t.auto || 0);
  if (Math.abs(byEar) >= 0.005) learn(t.device * 1000 + byEar * 1000); // their correction beyond the automatic one
  const wav = K.wavBytes(K.shifted(t.samples, t.rate, S.shift), t.rate);
  S.take = null; // sent once, however many times it's tapped
  $("review").hidden = true;
  // its checksum travels with it, and the bucket keeps it only if what arrives matches
  info.sha256 = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", wav)), b => b.toString(16).padStart(2, "0")).join("");
  const said = t.part.index === null ? "the whole song" : t.part.title;
  send({ wav, info, seconds: t.samples.length / t.rate, title: t.part.title, said });
  controls();
  say(`Sending ${said}.` + (t.part.index === null ? " Another take, or you're done: see below." : offerNext(t)));
};

function offerNext(t) {
  // one section kept: the next, a tap away; returns what to add to the status
  if (t.part.index === null || t.spec !== S.spec) return "";
  const done = sungHere();
  done.add(t.part.index);
  const next = K.nextSection(S.sections, t.part.index, done);
  if (!next) return " That's every section in this version. Well sung!";
  $("next").textContent = `Next: ${next.title} →`;
  $("next").title = K.sectionLabel(next);
  $("next").onclick = () => { choosePart(next.index); say(readyText()); };
  $("nextBox").hidden = false;
  return "";
}

window.addEventListener("beforeunload", e => { // a take not yet sent lives only in this page
  if (S.take || S.mode === "recording" || S.mode === "finishing" || queue.some(q => q.state !== "sent")) { e.preventDefault(); e.returnValue = ""; }
});

/* ---------- 6: sending ---------- */

const queue = [];

function b64url(text) {
  let s = "";
  for (const b of new TextEncoder().encode(text)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function drawTakes() {
  const list = $("takes"), earlier = (S.yours && S.yours.takes) || [];
  list.innerHTML = "";
  if (!queue.length && !earlier.length) list.innerHTML = '<li class="hint none">Nothing sent yet.</li>';
  for (const t of earlier) {
    const li = document.createElement("li");
    li.className = "sent";
    li.textContent = `${t.label || (t.section == null ? K.WHOLE : "One section")}, ${Math.round(t.seconds || 0)} s: sent earlier ✓`;
    list.appendChild(li);
  }
  for (const q of queue) {
    const li = document.createElement("li");
    const text = document.createElement("span");
    text.className = q.state;
    text.textContent = `${q.title}, ${Math.round(q.seconds)} s, ${MIXES[q.info.mix] ? MIXES[q.info.mix][0].toLowerCase() : q.info.mix}: `
      + (q.state === "sending" ? `sending… ${q.progress}%` : q.state === "sent" ? "sent ✓" : `not sent (${q.error})`);
    li.appendChild(text);
    if (q.state === "failed") {
      const again = document.createElement("button");
      again.textContent = "Send again";
      again.onclick = () => upload(q);
      li.append(" ", again);
    }
    list.appendChild(li);
  }
}

function send(q) {
  q.state = "sending";
  q.progress = 0;
  queue.push(q);
  upload(q);
}

function upload(q) {
  q.state = "sending";
  q.progress = 0;
  drawTakes();
  const xhr = new XMLHttpRequest();
  xhr.open("PUT", `/api/take/${enc(S.sid)}`);
  xhr.setRequestHeader("Content-Type", "audio/wav");
  xhr.setRequestHeader("X-Take-Info", b64url(JSON.stringify(q.info)));
  xhr.upload.onprogress = e => { if (e.lengthComputable) { q.progress = Math.round((100 * e.loaded) / e.total); drawTakes(); } };
  xhr.onload = () => {
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch (e) {}
    if (xhr.status >= 200 && xhr.status < 300 && !data.error) {
      q.state = "sent";
      q.wav = null; // a phone can't hold every take it has sent
      drawParts(); // its tick
      const sending = `Sending ${q.said}.`, now = $("status").textContent; // still saying so: now it's sent
      if (S.mode === "idle" && !S.take && now.startsWith(sending)) say(`Sent ${q.said} ✓.` + now.slice(sending.length));
    } else {
      q.state = "failed";
      q.error = data.message || `the server said ${xhr.status}`;
    }
    drawTakes();
  };
  xhr.onerror = () => { q.state = "failed"; q.error = "no connection"; drawTakes(); };
  xhr.send(q.wav);
}

/* ---------- 3: measuring the device's delay ---------- */

$("calibrate").onclick = async () => {
  try { await microphone(); } catch (e) { $("calibration").textContent = e.message; return; }
  if (S.mode !== "idle") return;
  await context();
  const when = S.ctx.currentTime + 0.6;
  K.scheduleClicks(S.ctx, when);
  S.chunks = [];
  S.mode = "calibrating";
  controls();
  $("calibration").textContent = "Tap, clap or say \"ta\" on every click; the first four count you in.";
  await new Promise(r => setTimeout(r, (0.6 + K.CLICKS.count * K.CLICKS.beat + 0.8) * 1000));
  S.mode = "idle";
  controls();
  const out = (S.ctx.outputLatency || 0) + (S.ctx.baseLatency || 0);
  const inn = S.stream.getAudioTracks()[0].getSettings().latency || 0;
  const lags = K.tapLags(S.chunks, S.ctx.sampleRate, when);
  S.chunks = [];
  const heard = K.CLICKS.count - K.CLICKS.lead;
  if (lags.length < heard / 2) {
    $("calibration").textContent = `Heard ${lags.length} of ${heard} taps; try again, a little louder or nearer the microphone.`;
    return;
  }
  const total = lags[Math.floor(lags.length / 2)];
  learn((total - out - inn) * 1000);
  $("calibration").textContent = `Your device takes about ${Math.round(total * 1000)} ms from click to tap. Takes will be lined up by that.`;
};

/* ---------- 7: words for the song ---------- */

function drawWords() {
  const list = $("wordsSent");
  list.innerHTML = "";
  const all = [...((S.yours && S.yours.words) || []).map(w => w.text), ...S.sentWords];
  for (const text of all) {
    const li = document.createElement("li");
    li.textContent = text;
    list.appendChild(li);
  }
  const n = $("wordsText").value.length;
  $("wordsCount").textContent = n ? `${n} of 4000 characters` : "";
}

$("wordsText").addEventListener("input", () => { drawWords(); controls(); });
$("wordsAgree").addEventListener("change", () => {
  S.wordsAt = $("wordsAgree").checked ? new Date().toISOString() : null;
  controls();
});
$("wordsSend").onclick = async () => {
  const text = $("wordsText").value.trim();
  if (!text || !$("wordsAgree").checked || !S.wordsAt || !S.sid) return;
  S.busy = true;
  controls();
  $("wordsNote").textContent = "Sending…";
  try {
    await api("POST", `words/${enc(S.sid)}`, JSON.stringify({
      text, release: { agreed: true, at: S.wordsAt, text: $("wordsRelease").dataset.digest },
    }));
    S.sentWords.push(text);
    $("wordsText").value = "";
    $("wordsNote").textContent = "Sent. Thank you: they're with the artist now. More are welcome.";
  } catch (e) {
    $("wordsNote").textContent = e.message;
  }
  S.busy = false;
  drawWords();
  controls();
};

/* ---------- 8: done ---------- */

$("done").onclick = async () => {
  const waiting = queue.filter(q => q.state !== "sent").length + (S.take ? 1 : 0);
  if (waiting && !confirm(`${waiting} take${waiting === 1 ? " hasn't" : "s haven't"} been sent yet. Finish anyway?`)) return;
  $("done").disabled = true;
  try {
    await api("POST", `done/${enc(S.sid)}`);
  } catch (e) {
    $("doneNote").textContent = e.message;
    $("done").disabled = false;
    return;
  }
  if (S.stream) S.stream.getTracks().forEach(t => t.stop());
  if (S.ctx) S.ctx.close();
  $("steps").hidden = true;
  $("thanks").hidden = false;
  $("thanks").scrollIntoView({ behavior: "smooth", block: "start" });
};

init();
