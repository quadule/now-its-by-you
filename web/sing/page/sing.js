// The sing-along page for singers anywhere (web/sing): the karaoke's way of recording
// (tools/karaoke.js, shared with tools/karaoke.html), behind an invitation. A take is
// cut from the frame the guide started on, in the same audio clock as the playback,
// synced against the song, and sent as a 16-bit mono WAV at the device's rate with a
// small sidecar: the name to credit (if any), when the release was agreed to, the
// device's delays, and which guide was heard.

import * as K from "./karaoke.js";

const $ = id => document.getElementById(id);
const S = { token: "", song: null, invite: null, notes: [], lo: 0, hi: 0, reel: null, ctx: null, guides: {}, mode: "idle",
            t0: 0, out: 0, inn: 0, chunks: [], trail: [], showTrail: null, take: null, shift: 0, consentAt: null,
            sent: 0, wake: null, interrupted: false, src: [] };
const MIXES = {
  melody: ["The tune alone", "on a soft whistle, with a quiet pulse on the beats"],
  full: ["The whole song", "the machine's singer and its band"],
  voice: ["The machine's singer alone", "no band"],
};

const saved = (key, fallback) => { try { return localStorage.getItem(key) ?? fallback; } catch (e) { return fallback; } };
const save = (key, value) => { try { localStorage.setItem(key, value); } catch (e) {} };

/* ---------- starting up ---------- */

async function init() {
  S.token = decodeURIComponent(location.pathname.split("/")[2] || "");
  try {
    S.invite = await api("GET", "invite");
    if (S.invite.state !== "open") return closed(S.invite.state);
    S.song = await api("GET", "song");
  } catch (e) {
    if (!e.code) return closed("error", "The page couldn't reach the server. Check your connection and reload it.");
    return closed(e.code, e.message);
  }
  S.sent = S.invite.takes;
  $("title").textContent = S.song.title;
  document.title = `Sing ${S.song.title}`;
  S.notes = K.notesOf(S.song);
  ({ lo: S.lo, hi: S.hi } = K.range(S.notes));
  S.reel = new K.Reel($("reel"), S.song);
  drawMixes();
  $("name").value = saved("songbird-sing-name", "");
  const credit = saved("songbird-sing-credit", "yes");
  document.querySelectorAll('input[name="credit"]').forEach(r => { r.checked = r.value === credit; });
  $("loading").hidden = true;
  $("steps").hidden = false;
  gate();
  resting();
  drawTakes();
  status("Put your headphones on and allow the microphone above, then listen first or record when you're ready.");
}

function closed(state, message) {
  $("loading").hidden = true;
  $("steps").hidden = true;
  $("closed").hidden = false;
  $("closedWhy").textContent = state === "done" ? "You've finished singing on this invitation. Thank you!"
    : state === "expired" ? "This invitation has expired. If you'd still like to sing, ask the person who sent it for a new one."
    : state === "error" ? message
    : "This invitation isn't open. Ask the person who sent it for a new one.";
}

async function api(method, kind, extra = "", body, headers = {}) {
  const r = await fetch(`/api/${kind}/${encodeURIComponent(S.token)}${extra}`, { method, body, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.message || `The server said ${r.status}.`); e.code = data.error; throw e; }
  return data;
}

function status(html) { $("status").innerHTML = html; }

function gate() {
  // the steps after the release wait for it to be agreed to, and the singing for the microphone
  const have = { agree: $("agree").checked, mic: !!S.recorder && $("agree").checked };
  document.querySelectorAll(".step[data-needs]").forEach(step => {
    const ok = have[step.dataset.needs];
    step.classList.toggle("waiting", !ok);
    step.querySelectorAll("button, input").forEach(el => { if (!ok) el.disabled = true; else if (!el.dataset.busy) el.disabled = false; });
  });
  if (have.mic) $("stop").disabled = S.mode === "idle";
  $("calibrateBox").hidden = !S.recorder;
}

$("agree").addEventListener("change", () => {
  S.consentAt = $("agree").checked ? new Date().toISOString() : null;
  gate();
});
$("name").addEventListener("input", () => save("songbird-sing-name", $("name").value.trim()));
document.querySelectorAll('input[name="credit"]').forEach(r => r.addEventListener("change", () => save("songbird-sing-credit", r.value)));

function drawMixes() {
  const box = $("mixes"), chosen = saved("songbird-sing-mix", S.song.default);
  box.innerHTML = "";
  for (const mix of Object.keys(S.song.mixes)) {
    const [name, about] = MIXES[mix] || [mix, ""];
    const label = document.createElement("label");
    label.innerHTML = `<input type="radio" name="mix"><span><strong></strong><small></small></span>`;
    label.querySelector("input").value = mix;
    label.querySelector("input").checked = mix === (S.song.mixes[chosen] ? chosen : S.song.default);
    label.querySelector("strong").textContent = name;
    label.querySelector("small").textContent = about;
    label.querySelector("input").addEventListener("change", () => save("songbird-sing-mix", mix));
    box.appendChild(label);
  }
}

function mix() {
  const on = document.querySelector('input[name="mix"]:checked');
  return on ? on.value : S.song.default;
}

/* ---------- the words and the notes ---------- */

function resting() {
  S.reel.show(0);
  drawLane(S.notes[0].start - 1.0);
  $("progress").style.width = "0";
}

function drawLane(pos) {
  K.drawLane($("lane"), S.notes, S.lo, S.hi, pos, S.showTrail);
}

function delay() { // what this device adds beyond what it reports, from a calibration or earlier takes
  return (parseFloat(saved("songbird-sing-nudge", "0")) || 0) / 1000;
}

function learn(ms) {
  save("songbird-sing-nudge", String(Math.round(ms)));
}

/* ---------- sound ---------- */

async function context() {
  if (!S.ctx) S.ctx = new AudioContext({ latencyHint: "interactive" });
  await S.ctx.resume();
}

async function guide(which) {
  // a guide, decoded, and how much silence the decoder put in front of it
  await context();
  if (!S.guides[which]) {
    status(`Loading the guide (${(S.song.mixes[which].bytes / 1e6).toFixed(1)} MB)…`);
    const r = await fetch(`/api/guide/${encodeURIComponent(S.token)}/${which}`);
    if (!r.ok) throw new Error("The guide didn't load. Check the connection and try again.");
    const buffer = await S.ctx.decodeAudioData(await r.arrayBuffer());
    const m = S.song.mixes[which];
    const n = Math.min(buffer.length, Math.ceil(buffer.sampleRate * 3));
    const mono = new Float32Array(n);
    for (let c = 0; c < buffer.numberOfChannels; c++) {
      const d = buffer.getChannelData(c);
      for (let i = 0; i < n; i++) mono[i] += d[i] / buffer.numberOfChannels;
    }
    S.guides[which] = { buffer, offset: K.decodeOffset(mono, buffer.sampleRate, m.env, m.frame) };
  }
  return S.guides[which];
}

async function microphone() {
  if (S.recorder) return;
  if (!window.isSecureContext || !navigator.mediaDevices) throw new Error("This page needs a secure (https) connection for the microphone.");
  await context();
  try {
    S.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    });
  } catch (e) {
    throw new Error(e.name === "NotAllowedError" ? "The browser didn't allow the microphone. Allow it for this page (in the address bar, or your phone's settings) and try again."
      : e.name === "NotFoundError" ? "No microphone was found." : `The microphone didn't start (${e.message}).`);
  }
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
    if (S.mode === "recording" || S.mode === "calibrating") S.chunks.push(e.data);
    $("level").style.width = Math.min(100, 140 * e.data.peak) + "%";
  };
}

$("mic").onclick = async () => {
  $("mic").disabled = true;
  try {
    await microphone();
    $("mic").textContent = "Microphone on";
    $("micNote").textContent = `Recording at ${S.ctx.sampleRate} Hz. If the level doesn't move when you sing, check the microphone.`;
  } catch (e) {
    $("micNote").innerHTML = `<span class="warn"></span>`;
    $("micNote").firstChild.textContent = e.message;
    $("mic").disabled = false;
  }
  gate();
};

function start(buffers, mode, from = 0, shifts = []) {
  const when = S.ctx.currentTime + 0.12;
  S.t0 = when - from;
  S.out = (S.ctx.outputLatency || 0) + (S.ctx.baseLatency || 0);
  S.inn = S.stream ? S.stream.getAudioTracks()[0].getSettings().latency || 0 : 0;
  S.src = buffers.map((buffer, i) => {
    const src = S.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(S.ctx.destination);
    const at = from + (shifts[i] || 0); // a positive shift plays the buffer that much earlier
    if (at >= 0) src.start(when, at); else src.start(when - at);
    return src;
  });
  S.src[0].onended = () => { if (S.mode !== "idle") stop(); };
  S.chunks = [];
  S.trail = [];
  S.showTrail = mode === "listening" ? S.take.trail.map(p => ({ t: p.t - S.shift, m: p.m })) : S.trail;
  S.mode = mode;
  S.interrupted = false;
  busy(true);
  $("review").hidden = true;
  status(mode === "recording" ? "Recording. Sing along; press Stop when you're finished." : mode === "listening" ? "Your take, with the guide." : "Listening. Sing along if you like.");
  requestAnimationFrame(tick);
}

function busy(on) {
  for (const id of ["record", "rehearse", "calibrate", "done", "keep", "listen", "discard"]) {
    $(id).dataset.busy = on ? "1" : "";
    $(id).disabled = on;
  }
  document.querySelectorAll('input[name="mix"]').forEach(r => { r.disabled = on; });
  $("stop").disabled = !on;
  if (!on) gate();
}

function stop() {
  const was = S.mode;
  S.mode = "idle";
  S.src.forEach(s => { s.onended = null; try { s.stop(); } catch (e) {} });
  S.src = [];
  if (S.wake) { S.wake.release().catch(() => {}); S.wake = null; }
  busy(false);
  if (was === "recording") finishTake();
  else if (was !== "calibrating") status("Record a take when you're ready.");
  resting();
}

function listen(pos) {
  if (!S.analyser) return;
  S.analyser.getFloatTimeDomainData(S.buf);
  S.trail.push({ t: pos - S.inn - delay() - 0.02, m: K.pitchAt(S.buf, S.ctx.sampleRate) });
}

function tick() {
  if (S.mode === "idle" || S.mode === "calibrating") return;
  const pos = S.ctx.currentTime - S.t0 - S.out;
  if (S.mode !== "listening") listen(pos);
  $("progress").style.width = Math.max(0, Math.min(100, (100 * pos) / S.song.duration)) + "%";
  S.reel.show(pos);
  drawLane(pos);
  requestAnimationFrame(tick);
}

document.addEventListener("visibilitychange", () => { if (document.hidden && S.mode === "recording") S.interrupted = true; });

/* ---------- a take ---------- */

$("rehearse").onclick = async () => {
  try {
    const g = await guide(mix());
    start([g.buffer], "rehearsing", 0, [g.offset]);
  } catch (e) { status(`<span class="warn">${escapeHtml(e.message)}</span>`); }
};

$("record").onclick = async () => {
  if (!$("agree").checked) { status('<span class="warn">Agree to the release first (step 2).</span>'); return; }
  if (S.sent >= S.invite.limit) { status("You've sent as many takes as this invitation takes. Thank you!"); return; }
  const which = mix();
  let g;
  try { g = await guide(which); await microphone(); } catch (e) { status(`<span class="warn">${escapeHtml(e.message)}</span>`); return; }
  try { S.wake = navigator.wakeLock ? await navigator.wakeLock.request("screen") : null; } catch (e) { S.wake = null; }
  S.recording = { mix: which, offset: g.offset };
  start([g.buffer], "recording", 0, [g.offset]);
};

$("stop").onclick = stop;
document.addEventListener("keydown", e => { if (e.code === "Space" && S.mode !== "idle" && e.target.tagName !== "INPUT") { e.preventDefault(); stop(); } });
window.addEventListener("resize", () => { if (S.mode === "idle" && S.song) resting(); });

function finishTake() {
  const rate = S.ctx.sampleRate;
  const samples = K.assemble(S.chunks, K.firstFrame(S.t0, S.out, S.inn, delay(), rate));
  S.chunks = [];
  S.take = { samples, rate, mix: S.recording.mix, offset: S.recording.offset, trail: S.trail.slice(), buffer: null,
             out: S.out, inn: S.inn, device: delay() };
  const long = samples.length / rate > 5;
  S.shift = S.take.auto = long ? K.autoSync(S.take.trail, S.notes) : 0;
  $("shift").value = String(Math.max(-400, Math.min(400, -S.shift * 1000)));
  $("shiftValue").textContent = S.shift ? `lined up automatically: ${Math.abs(Math.round(S.shift * 1000))} ms ${S.shift > 0 ? "earlier" : "later"}` : "as recorded";
  if (S.shift) learn(delay() * 1000 + S.shift * 1000); // so the next take starts closer
  const note = S.interrupted ? ' <span class="warn">The page went into the background while you sang, so this take may have gaps: listen before you keep it.</span>' : "";
  status(long ? `Got it. Listen back, then keep it or try again.${note}` : "That was short. Record again?");
  $("review").hidden = !long;
}

function takeBuffer() {
  if (!S.take.buffer) {
    S.take.buffer = S.ctx.createBuffer(1, S.take.samples.length, S.take.rate);
    S.take.buffer.copyToChannel(S.take.samples, 0);
  }
  return S.take.buffer;
}

function listenFrom(from) {
  S.src.forEach(s => { s.onended = null; try { s.stop(); } catch (e) {} });
  start([S.guides[S.take.mix].buffer, takeBuffer()], "listening", Math.max(0, from), [S.take.offset, S.shift]);
}

$("listen").onclick = () => listenFrom(0);
$("shift").oninput = () => {
  const ms = parseFloat($("shift").value);
  S.shift = -ms / 1000; // slid left, the voice comes earlier
  $("shiftValue").textContent = ms ? `${Math.abs(ms)} ms ${ms < 0 ? "earlier" : "later"}` : "as recorded";
};
$("shift").onchange = () => { if (S.mode === "listening") listenFrom(S.ctx.currentTime - S.t0 - S.out - 1.0); };
$("discard").onclick = () => { S.take = null; $("review").hidden = true; status("Ready when you are."); };

$("keep").onclick = () => {
  const t = S.take;
  if (!t) return;
  const info = {
    song: S.song.song, guide: S.song.guide, mix: t.mix, rate: t.rate,
    name: $("name").value.trim(), credit: document.querySelector('input[name="credit"]:checked').value === "yes",
    consent: { agreed: true, at: S.consentAt, text: $("consentText").dataset.digest },
    shift_ms: Math.round(S.shift * 1000), auto_ms: Math.round((t.auto || 0) * 1000), device_ms: Math.round(t.device * 1000),
    decode_ms: Math.round(t.offset * 10000) / 10, out_ms: Math.round(t.out * 1000), in_ms: Math.round(t.inn * 1000),
  };
  const byEar = S.shift - (t.auto || 0);
  if (Math.abs(byEar) >= 0.005) learn(t.device * 1000 + byEar * 1000); // their correction beyond the automatic one
  const wav = K.wavBytes(K.shifted(t.samples, t.rate, S.shift), t.rate);
  S.take = null;
  $("review").hidden = true;
  send({ wav, info, seconds: t.samples.length / t.rate });
};

/* ---------- sending ---------- */

const queue = [];

function b64url(text) {
  let s = "";
  for (const b of new TextEncoder().encode(text)) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function drawTakes() {
  const list = $("takes"), earlier = S.invite.takes;
  list.innerHTML = "";
  if (!queue.length && !earlier) list.innerHTML = '<li class="hint none">Nothing sent yet.</li>';
  if (earlier) {
    const li = document.createElement("li");
    li.className = "hint none";
    li.textContent = `${earlier} sent on an earlier visit.`;
    list.appendChild(li);
  }
  for (const q of queue) {
    const li = document.createElement("li");
    const text = document.createElement("span");
    text.className = q.state;
    text.textContent = `${Math.round(q.seconds)} s, ${MIXES[q.info.mix] ? MIXES[q.info.mix][0].toLowerCase() : q.info.mix}: `
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
  const left = S.invite.limit - S.sent;
  $("takesLeft").textContent = left > 0 ? `You can send ${left} more take${left === 1 ? "" : "s"} on this invitation.` : "That's every take this invitation holds. Thank you!";
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
  xhr.open("PUT", `/api/take/${encodeURIComponent(S.token)}`);
  xhr.setRequestHeader("Content-Type", "audio/wav");
  xhr.setRequestHeader("X-Take-Info", b64url(JSON.stringify(q.info)));
  xhr.upload.onprogress = e => { if (e.lengthComputable) { q.progress = Math.round((100 * e.loaded) / e.total); drawTakes(); } };
  xhr.onload = () => {
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch (e) {}
    if (xhr.status === 200 && data.ok) {
      q.state = "sent";
      q.wav = null; // a phone can't hold every take it has sent
      S.sent = data.take;
      status("Sent. Another take, or press I'm done below when you've finished.");
    } else {
      q.state = "failed";
      q.error = data.message || `the server said ${xhr.status}`;
      if (data.error === "limit") S.sent = S.invite.limit;
    }
    drawTakes();
  };
  xhr.onerror = () => { q.state = "failed"; q.error = "no connection"; drawTakes(); };
  xhr.send(q.wav);
}

/* ---------- measuring the device's delay ---------- */

$("calibrate").onclick = async () => {
  try { await microphone(); } catch (e) { $("calibration").textContent = e.message; return; }
  if (S.mode !== "idle") return;
  const when = S.ctx.currentTime + 0.6;
  K.scheduleClicks(S.ctx, when);
  S.chunks = [];
  S.mode = "calibrating";
  busy(true);
  $("stop").disabled = true;
  $("calibration").textContent = "Tap, clap or say \"ta\" on every click; the first four count you in.";
  await new Promise(r => setTimeout(r, (0.6 + K.CLICKS.count * K.CLICKS.beat + 0.8) * 1000));
  S.mode = "idle";
  busy(false);
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

/* ---------- done ---------- */

$("done").onclick = async () => {
  const waiting = queue.filter(q => q.state !== "sent").length + (S.take ? 1 : 0);
  const ask = waiting ? `${waiting} take${waiting === 1 ? " hasn't" : "s haven't"} been sent. Finish anyway? The link will stop working.`
    : "Finish now? The link will stop working, and you won't be able to send more takes.";
  if (!confirm(ask)) return;
  try {
    await api("POST", "done");
  } catch (e) {
    $("doneNote").textContent = e.message;
    return;
  }
  if (S.stream) S.stream.getTracks().forEach(t => t.stop());
  if (S.ctx) S.ctx.close();
  $("steps").hidden = true;
  $("thanks").hidden = false;
  if (!S.sent) $("thanksText").textContent = "The invitation is closed. Thank you for coming by.";
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

init();
