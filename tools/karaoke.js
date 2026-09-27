// Songbird's sing-along core, shared by the karaoke on this computer (tools/karaoke.html)
// and the page singers use anywhere (web/sing): the words and notes as they come, the
// singer's pitch, and a take cut, synced and written the same way wherever it was sung.
//
// The clock: the guide starts at t0 on the AudioContext's clock and reaches the singer's
// ears `out` later (the output latency the device reports). Their voice reaches the
// recorder `inn` after that (the input latency), plus whatever the device adds without
// saying (`extra`, learned from a calibration or from earlier takes). So the take's first
// sample is the recorder's frame (t0 + out + inn + extra) * rate, and every sample after
// it lines up with the guide's timeline. autoSync() then finds any lag left by sliding the
// pitch sung against the song's notes.
//
// One section at a time: playback starts at the section's window (two bars before its first
// sung note, from the words' JSON) and stops at the window's end, and the take is cut so its
// sample 0 is guide time `from`: the frame (t0 + from + out + inn + extra) * rate. Everything
// else is as for the whole song, which is the window [0, the song's end).

export const NAMES = { intro: "Intro", verse: "Verse", refrain: "Refrain", turn: "Turn", bridge: "Bridge", tag: "Tag",
                       break: "Break", outro: "Outro" };
export const PAST = 2.0, FUTURE = 5.0; // seconds of the lane either side of the playhead, on a wide screen
export const PX_PER_SECOND = 100; // at least this: a fifth of a second is then 20 px, room for its syllable
export const TAIL = 0.6; // seconds a one-section take runs past its window's end, for the last note to die away

/* ---------- the version sung: a set of words, a key and a speed ---------- */

export function specId({ set, key, tempo }) {
  // "a.k-2.t90": set a, two steps lower, at 90% of the song's speed (no "+": it breaks query strings)
  return `${set}.k${key}.t${tempo}`;
}

export function parseSpec(id) {
  const m = /^([a-z0-9]{1,8})\.k(-?\d{1,2})\.t(\d{2,3})$/.exec(String(id ?? ""));
  return m ? { id: String(id), set: m[1], key: Number(m[2]), tempo: Number(m[3]) } : null;
}

export function keyLabel(key) {
  // semitones from the song's own key, in words a singer uses
  if (!key) return "as written";
  const n = Math.abs(key);
  return `${n} step${n === 1 ? "" : "s"} ${key < 0 ? "lower" : "higher"}`;
}

export function speedLabel(tempo) {
  // percent of the song's own speed
  return tempo === 100 ? "as written" : tempo > 100 ? "faster" : tempo >= 90 ? "a little slower" : "slower";
}

export function specText(id, sets = []) {
  // a version in words, what's as written left out: "Set A, 2 steps lower, a little slower"
  const s = parseSpec(id);
  if (!s) return "";
  const set = sets.find(x => x.id === s.set);
  const out = [set ? set.name : s.set === "song" ? "" : `Set ${s.set.toUpperCase()}`];
  if (s.key) out.push(keyLabel(s.key));
  if (s.tempo !== 100) out.push(speedLabel(s.tempo));
  return out.filter(Boolean).join(", ");
}

export function nearestSpec(ids, want, keep) {
  // the version on offer nearest the one wanted: the same set if it can be, then the nearest key,
  // then the nearest speed; `keep` ("set", "key" or "tempo") holds what was just chosen, if any offer it
  const all = ids.map(parseSpec).filter(Boolean);
  const same = keep ? all.filter(s => s[keep] === want[keep]) : [];
  const cost = s => (s.set === want.set ? 0 : 1000) + 10 * Math.abs(s.key - want.key) + Math.abs(s.tempo - want.tempo);
  let best = null;
  for (const s of same.length ? same : all) if (!best || cost(s) < cost(best)) best = s;
  return best ? best.id : null;
}

/* ---------- the sections a singer can sing on their own ---------- */

const LITTLE = new Set(["a", "an", "and", "as", "at", "but", "by", "for", "from", "if", "in", "nor", "of", "on", "or", "so", "that",
                        "the", "to", "while", "with"]);

export function firstWords(line, max = 28) {
  // the start of a line for a label, at most `max` characters: whole if it fits, else its first
  // sentence, or its first clause, or its first words (not ending on a little one like "and"), with "…"
  const text = String(line ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= max) return text.replace(/[,;:]$/, "");
  const sentence = /^.{11,}?[.?!](?= )/.exec(text.slice(0, max + 1));
  if (sentence) return sentence[0];
  let clause = -1;
  for (const m of text.matchAll(/[,;:] /g)) if (m.index >= 12 && m.index <= max) clause = m.index;
  if (clause > 0) return text.slice(0, clause) + "…";
  const words = text.slice(0, max + 1).split(" ").slice(0, -1); // whole words only
  while (words.length > 1 && LITTLE.has(words[words.length - 1].toLowerCase())) words.pop();
  return (words.length ? words.join(" ") : text.slice(0, max)).replace(/[,;:.]$/, "") + "…";
}

export function sungSections(lyrics) {
  // the sung sections, in order, each with its window [from, to) and its name as a singer would
  // say it ("Verse 2"; "Bridge" when there's only one)
  const sung = (lyrics.sections || []).filter(s => s.sung && Array.isArray(s.window));
  const kinds = {};
  for (const s of sung) kinds[s.name] = (kinds[s.name] || 0) + 1;
  return sung.map(s => {
    const name = NAMES[s.name] || s.name;
    return { ...s, from: s.window[0], to: s.window[1], title: kinds[s.name] > 1 && s.nth ? `${name} ${s.nth}` : name };
  });
}

export function sectionLabel(s) {
  // "Verse 2 · They saved it as numbers…"
  const words = firstWords(s.label);
  return words ? `${s.title} · ${words}` : s.title;
}

export const WHOLE = "The whole song";

export function part(lyrics, index = null) {
  // what's sung: one sung section, by its index, from its window's start to its end; or, with no
  // index, the whole song, from 0 to its end; null for a section this version doesn't have
  if (index === null || index === undefined) return { index: null, name: null, from: 0, to: lyrics.duration, title: WHOLE, label: WHOLE };
  const s = sungSections(lyrics).find(s => s.index === index);
  return s ? { index: s.index, name: s.name, from: s.from, to: s.to, title: s.title, label: sectionLabel(s) } : null;
}

export function nextSection(sections, current, done = new Set()) {
  // after a section is kept, the one to offer next: the first not yet sung after it, else the
  // first not yet sung from the top; null when every section has been sung
  const i = sections.findIndex(s => s.index === current);
  return [...sections.slice(i + 1), ...sections.slice(0, i + 1)].find(s => s.index !== current && !done.has(s.index)) || null;
}

export function inWindow(notes, from = 0, to = Infinity) {
  // the notes a one-section take is measured by: those that start inside its window
  return notes.filter(n => n.start >= from && n.start < to);
}

export function restAt(notes, from = 0) {
  // where the lane waits before playing: a second before the first note to sing
  const n = notes.find(n => n.start >= from);
  return (n ? n.start : from) - 1.0;
}

/* ---------- the notes ---------- */

export function notesOf(lyrics) {
  return lyrics.lines.flatMap(l => l.syllables);
}

export function range(notes) {
  const pitches = notes.map(n => n.pitch);
  return { lo: Math.min(...pitches) - 2, hi: Math.max(...pitches) + 2 };
}

export function target(notes, t) {
  // the pitch the song wants at t: the note sounding, else the nearest within 0.35 s, else null
  const n = notes.find(n => t >= n.start && t < n.end);
  if (n) return n.pitch;
  let best = null, gap = 0.35;
  for (const m of notes) {
    const d = Math.min(Math.abs(t - m.start), Math.abs(t - m.end));
    if (d < gap) { gap = d; best = m.pitch; }
  }
  return best;
}

export function laneFont(height) {
  // the size of the lane's words: grows with the lane, so a tall one (full screen, a big window) reads from a distance
  return Math.round(Math.max(12, Math.min(28, height * 0.075)));
}

export function laneSpan(width, font = 12) {
  // the seconds the lane shows either side of the playhead: PAST and FUTURE where the screen is wide
  // enough, else fewer in the same proportion, so a short syllable still has room for its word (a phone
  // held upright shows about three and a half seconds, turned sideways all seven); bigger words, fewer seconds
  const span = Math.min(PAST + FUTURE, Math.max(3, width / Math.max(PX_PER_SECOND, font * 8.5)));
  return { past: (span * PAST) / (PAST + FUTURE), future: (span * FUTURE) / (PAST + FUTURE), span };
}

export function drawLane(c, notes, lo, hi, pos, trail) {
  // the notes to come as bars at their pitch, the playhead, and the pitch sung as a line
  // (green on the note, amber off it), folded into the song's octave
  const g = c.getContext("2d");
  const dpr = globalThis.devicePixelRatio || 1, W = c.clientWidth, H = c.clientHeight;
  if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) { c.width = Math.round(W * dpr); c.height = Math.round(H * dpr); }
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  const font = laneFont(H), under = font + 10; // room under the lowest note for its word
  const { past: PAST, future: FUTURE, span } = laneSpan(W, font), px = (W * PAST) / span;
  const x = t => px + ((t - pos) * W) / span;
  const y = m => H - under - ((m - lo) / (hi - lo)) * (H - under - 18);
  const h = Math.max(7, ((H - under - 18) / (hi - lo)) * 0.72);

  g.strokeStyle = "rgba(239,230,218,0.05)";
  g.lineWidth = 1;
  for (let m = Math.ceil(lo); m <= hi; m++) { g.beginPath(); g.moveTo(0, y(m)); g.lineTo(W, y(m)); g.stroke(); }

  g.font = `${font}px -apple-system, system-ui, sans-serif`;
  notes.forEach((n, i) => {
    if (n.end < pos - PAST - 1 || n.start > pos + FUTURE + 1) return;
    const x0 = x(n.start), x1 = Math.max(x(n.end) - 3, x0 + 5), yy = y(n.pitch);
    const now = pos >= n.start && pos < n.end, done = pos >= n.end;
    g.fillStyle = now ? "#f2b25c" : done ? "rgba(242,178,92,0.32)" : "rgba(239,230,218,0.5)";
    g.beginPath();
    if (g.roundRect) g.roundRect(x0, yy - h / 2, x1 - x0, h, 4); else g.rect(x0, yy - h / 2, x1 - x0, h);
    g.fill();
    // its syllable, where it fits before the next note begins (not only under its own bar)
    const room = (notes[i + 1] ? x(notes[i + 1].start) : W) - x0 - 2;
    if (g.measureText(n.text).width <= room || x1 - x0 > 12) {
      g.fillStyle = done ? "rgba(239,230,218,0.35)" : "rgba(239,230,218,0.75)";
      g.fillText(n.text, x0 + 1, yy + h / 2 + font + 1);
    }
  });

  if (trail && trail.length) {
    g.lineWidth = Math.max(3, font / 5);
    g.lineCap = "round";
    for (let i = 1; i < trail.length; i++) {
      const a = trail[i - 1], b = trail[i];
      if (a.m === null || b.m === null || b.t - a.t > 0.12 || b.t < pos - PAST || a.t > pos) continue;
      const want = target(notes, b.t);
      const fb = want === null ? b.m : b.m + 12 * Math.round((want - b.m) / 12);
      const fa = want === null ? a.m : a.m + 12 * Math.round((want - a.m) / 12);
      g.strokeStyle = want === null ? "rgba(239,230,218,0.6)" : Math.abs(fb - want) <= 0.5 ? "#8cc084" : "#e0a04d";
      g.beginPath(); g.moveTo(x(a.t), y(fa)); g.lineTo(x(b.t), y(fb)); g.stroke();
    }
  }

  g.strokeStyle = "#e0664d";
  g.lineWidth = 2;
  g.beginPath(); g.moveTo(px, 8); g.lineTo(px, H - 8); g.stroke();
}

/* ---------- full screen ---------- */

export function fullScreen(el, button, changed) {
  // el fills the screen while singing: the browser's own full screen where it gives one to any element,
  // else (an iPhone) the page's own, el laid over everything (class "fs"); the button goes in and out,
  // Escape leaves the page's own; changed(on) after each change, to draw again at the new size
  const real = () => (document.fullscreenElement || document.webkitFullscreenElement) === el;
  const faked = () => el.classList.contains("fs");
  const show = () => {
    if (real()) el.classList.remove("fs"); // the browser's own came, if late: the page's own isn't needed
    const on = real() || faked();
    button.textContent = on ? "✕ Exit full screen" : "⛶ Full screen";
    button.setAttribute("aria-pressed", String(on));
    document.body.classList.toggle("fs-on", faked());
    if (changed) requestAnimationFrame(() => changed(on));
  };
  const leave = () => { el.classList.remove("fs"); show(); };
  button.addEventListener("click", async () => {
    if (real()) return void (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    if (faked()) return leave();
    const ask = el.requestFullscreen || el.webkitRequestFullscreen;
    if (ask && (document.fullscreenEnabled || document.webkitFullscreenEnabled)) {
      // some browsers never answer (an app's embedded view): wait a moment, then use the page's own
      const moment = new Promise((_, no) => setTimeout(() => no(new Error("no answer")), 700));
      try { await Promise.race([Promise.resolve(ask.call(el, { navigationUI: "hide" })), moment]); } catch (e) { /* below */ }
      if (real()) return;
    }
    el.classList.add("fs");
    el.scrollTop = 0;
    show();
  });
  document.addEventListener("fullscreenchange", show);
  document.addEventListener("webkitfullscreenchange", show);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && faked()) leave(); });
  show();
}

/* ---------- the words ---------- */

export function countIn(beats, start, tempo, n = 4) {
  // the times a line is counted in on: the last n beats before its first syllable (before it by
  // more than the players' timing), so a line that starts on a pickup is counted on the beats the
  // pulse plays, not between them; without the beats, n beats of the tempo back from the syllable
  if (!beats || !beats.length) return Array.from({ length: n }, (_, k) => start - (n - k) * (60 / tempo));
  const before = beats.filter(t => t < start - 0.05).slice(-n);
  return [...Array(n - before.length).fill(-Infinity), ...before];
}

function escape(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function reelLines(lyrics, { from = 0, to = Infinity, name = null } = {}) {
  // the lines a reel shows (for one section, only its own: those of its kind starting in its
  // window), each with the rest before it, from the line before or from where playback starts,
  // and the beats that count it in
  const lines = lyrics.lines.filter(l => l.syllables[0].start >= from && l.syllables[0].start < to && (!name || l.section === name));
  return lines.map((line, i) => {
    const before = i ? lines[i - 1] : null;
    const gapStart = before ? before.end : from;
    return { line, before, gapStart, gap: line.syllables[0].start - gapStart,
             count: countIn(lyrics.beats, line.syllables[0].start, lyrics.tempo) };
  });
}

export class Reel {
  // the words line by line in a scrolling window: the current line large, each syllable
  // filling in as it's sung; before a line after a rest, a bar and four dots count it in.
  // `part` is {from, to, name, end} for one section; without it, the whole song
  constructor(el, lyrics, part = {}) {
    this.el = el;
    this.tempo = lyrics.tempo;
    this.focus = -2;
    el.innerHTML = "";
    this.items = reelLines(lyrics, part).map(({ line, before, gapStart, gap, count }) => {
      const item = document.createElement("div");
      item.className = "item";
      let html = "";
      if (!before || before.section !== line.section || gap > 3) html += `<div class="label">${escape(NAMES[line.section] || line.section)}</div>`;
      if (gap >= 1.2) {
        html += `<div class="gap"><span class="track"><span class="fill"></span></span>`
              + `<span class="dots"><i></i><i></i><i></i><i></i></span>${gap >= 3 && before ? "<span>breathe</span>" : ""}</div>`;
      }
      html += `<div class="words">` + line.syllables.map(s => `<span class="syl">${escape(s.text)}</span>${s.word_end ? " " : ""}`).join("") + `</div>`;
      item.innerHTML = html;
      el.appendChild(item);
      return { el: item, line, gapStart, gap, syls: [...item.querySelectorAll(".syl")], fill: item.querySelector(".fill"),
               dots: [...item.querySelectorAll(".dots i")], lead: item.querySelector(".gap"), count };
    });
    const end = document.createElement("div");
    end.className = "item done";
    end.textContent = part.end || "That's the song.";
    el.appendChild(end);
    this.items.push({ el: end, line: null });
  }

  focusOn(f) {
    if (f === this.focus) return;
    this.items.forEach((it, i) => {
      it.el.classList.toggle("current", i === f);
      it.el.classList.toggle("past", i < f);
      if (it.syls) it.syls.forEach(s => s.style.setProperty("--p", i < f ? "100%" : "0%"));
    });
    const anchor = 64; // where the current line sits in the window
    this.el.style.transform = `translateY(${anchor - this.items[f].el.offsetTop}px)`;
    this.focus = f;
  }

  show(pos) {
    let f = this.items.findIndex(it => it.line && pos < it.line.end + 0.15);
    if (f < 0) f = this.items.length - 1;
    this.focusOn(f);
    const it = this.items[f];
    if (!it.line) return;
    const first = it.line.syllables[0].start;
    if (it.fill) it.fill.style.width = Math.max(0, Math.min(100, (100 * (pos - it.gapStart)) / it.gap)) + "%";
    if (it.lead) it.lead.classList.toggle("spent", pos > first + 0.4); // the count-in has done its job
    it.dots.forEach((d, k) => d.classList.toggle("on", pos >= it.count[k]));
    it.line.syllables.forEach((s, k) => {
      const next = it.line.syllables[k + 1];
      const until = next ? Math.min(s.end, next.start) : s.end;
      const p = Math.max(0, Math.min(1, (pos - s.start) / Math.max(until - s.start, 0.05)));
      it.syls[k].style.setProperty("--p", (100 * p).toFixed(1) + "%");
    });
  }
}

/* ---------- listening to the singer ---------- */

export function yin(buf, rate) {
  // the pitch of a block of the mic, by YIN at half the rate; null when there is none
  const n = buf.length >> 1, x = new Float32Array(n);
  for (let i = 0; i < n; i++) x[i] = 0.5 * (buf[2 * i] + buf[2 * i + 1]);
  const r = rate / 2, lo = Math.floor(r / 1000), hi = Math.min(Math.floor(r / 65), (n >> 1) - 1), w = n - hi;
  const d = new Float32Array(hi + 2);
  for (let tau = 1; tau <= hi + 1; tau++) {
    let s = 0;
    for (let i = 0; i < w; i++) { const e = x[i] - x[i + tau]; s += e * e; }
    d[tau] = s;
  }
  let sum = 0;
  for (let tau = 1; tau <= hi + 1; tau++) { sum += d[tau]; d[tau] = (d[tau] * tau) / (sum || 1); }
  for (let tau = Math.max(lo, 2); tau <= hi; tau++) {
    if (d[tau] < 0.15) {
      while (tau + 1 <= hi && d[tau + 1] < d[tau]) tau++;
      const a = d[tau - 1], b = d[tau], c = d[tau + 1], den = a - 2 * b + c;
      return r / (tau + (den ? (a - c) / (2 * den) : 0));
    }
  }
  return null;
}

export function pitchAt(buf, rate) {
  // a block's pitch as a MIDI number, or null if it's too quiet or unpitched
  let e = 0;
  for (let i = 0; i < buf.length; i++) e += buf[i] * buf[i];
  const hz = Math.sqrt(e / buf.length) > 0.008 ? yin(buf, rate) : null;
  return hz ? 69 + 12 * Math.log2(hz / 440) : null;
}

export function autoSync(trail, notes) {
  /* How late the take runs against the guide: slide the pitch you sang against
     the song's notes and rests, and keep the slide where they agree best (your
     voice inside a note, better still on its pitch; your voice in a rest counts
     against). Returns seconds to move the take earlier, or 0 if nothing clearly
     beats leaving it as recorded. */
  const pts = trail.filter(p => p.m !== null);
  if (pts.length < 100) return 0;
  const starts = notes.map(n => n.start);
  const noteAt = u => {
    let lo = 0, hi = starts.length - 1, k = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (starts[mid] <= u) { k = mid; lo = mid + 1; } else hi = mid - 1; }
    return k >= 0 && u < notes[k].end ? notes[k] : null;
  };
  const score = lag => {
    let s = 0;
    for (const p of pts) {
      const n = noteAt(p.t - lag);
      if (!n) { s -= 0.5; continue; }
      const m = p.m + 12 * Math.round((n.pitch - p.m) / 12);
      s += Math.abs(m - n.pitch) <= 1 ? 2 : 1;
    }
    return s;
  };
  const lags = [], scores = [];
  for (let k = -30; k <= 120; k++) { lags.push(k * 0.005); scores.push(score(k * 0.005)); }
  // the gaps between syllables let a slide of a few tens of ms go unpunished, so the best
  // score is a plateau: take its middle, not its first edge
  const top = Math.max(...scores);
  const flat = lags.filter((lag, i) => scores[i] >= top - 0.002 * pts.length);
  const best = flat[Math.floor(flat.length / 2)];
  return Math.abs(best) >= 0.01 ? Math.round(best * 1000) / 1000 : 0;
}

export function autoSyncWindow(trail, notes, from = 0, to = Infinity) {
  // autoSync for a one-section take, against only the notes it's measured by (those starting in
  // its window): singing along to the guide's lead-in, or past the end, can't pull it off
  return autoSync(trail, inWindow(notes, from, to));
}

/* ---------- a take ---------- */

export const UNDER = 0.5; // the guide's level while you listen back to a take, so your voice sits on top

export function takeGain(samples, rate) {
  // how much to lift a take to hear it back over the guide (only to hear it: what's sent stays as sung).
  // A phone's microphone, its own gain turned off, can sit 30 dB under the mastered guide, so a take
  // played beside it vanishes. The loud part of its singing (the loudest fifth of its 20 ms windows)
  // goes to about a fifth of full scale, its peaks (bar a stray click) stay under full scale, and it's
  // never quieter than as recorded or lifted more than 20 times
  const w = Math.max(1, Math.round(0.02 * rate)), levels = [], peaks = [];
  for (let i = 0; i + w <= samples.length; i += w) {
    let e = 0, m = 0;
    for (let j = i; j < i + w; j++) { const x = samples[j]; e += x * x; if (Math.abs(x) > m) m = Math.abs(x); }
    levels.push(Math.sqrt(e / w));
    peaks.push(m);
  }
  if (!levels.length) return 1;
  levels.sort((a, b) => b - a);
  peaks.sort((a, b) => b - a);
  const top = levels.slice(0, Math.max(1, Math.floor(levels.length / 5)));
  // the peak bar the loudest window or two (a stray click, a bump of the microphone)
  const loud = top.reduce((a, b) => a + b, 0) / top.length, peak = peaks[Math.min(peaks.length - 1, Math.max(1, Math.floor(peaks.length * 0.01)))];
  if (!(loud > 0) || !(peak > 0)) return 1;
  return Math.max(1, Math.min(10, 0.15 / loud, 0.7 / peak));
}

export function listenOut(ctx) {
  // where a take and its guide play when you listen back: a limiter before the speakers, so the two
  // together never pass full scale (a lifted phone take over a mastered guide can, and clipping buzzes)
  const limit = ctx.createDynamicsCompressor();
  limit.threshold.value = -6;
  limit.knee.value = 3;
  limit.ratio.value = 20;
  limit.attack.value = 0.002;
  limit.release.value = 0.15;
  limit.connect(ctx.destination);
  return limit;
}

export function takeFilter(ctx) {
  // a take's rumble and hum, lifted with it, left out when you listen back (only then: what's sent stays as sung)
  const hp = ctx.createBiquadFilter();
  hp.type = "highpass";
  hp.frequency.value = 90;
  hp.Q.value = 0.7;
  return hp;
}

export function firstFrame(t0, out, inn, extra, rate, from = 0) {
  // the recorder frame the take starts on: when the guide's first sample (for one section, the
  // guide at `from` seconds) reached the singer's ears (t0 + from + out), plus the way back in
  // (inn) and what the device doesn't say (extra)
  return Math.round((t0 + from + out + inn + extra) * rate);
}

export function cutTake(chunks, first, rate, seconds = Infinity) {
  // a take from the recorder's blocks: from frame `first` (see firstFrame) for at most `seconds`,
  // so a one-section take holds its window and a little after, however late it was stopped
  const samples = assemble(chunks, first);
  const most = Math.round(seconds * rate);
  return samples.length > most ? samples.slice(0, most) : samples;
}

export function assemble(chunks, first) {
  // the recorder's blocks laid out from frame `first` on: anything earlier is dropped, a gap stays silent
  const tail = chunks[chunks.length - 1];
  const last = tail ? tail.frame + tail.samples.length : first;
  const samples = new Float32Array(Math.max(last - first, 0));
  for (const c of chunks) {
    const at = c.frame - first;
    for (let i = 0; i < c.samples.length; i++) if (at + i >= 0 && at + i < samples.length) samples[at + i] = c.samples[i];
  }
  return samples;
}

export function shifted(samples, rate, earlier) {
  // the take moved `earlier` seconds earlier (its start dropped), or later (silence in front)
  const n = Math.round(earlier * rate);
  if (n >= 0) return samples.subarray(Math.min(n, samples.length));
  const out = new Float32Array(samples.length - n);
  out.set(samples, -n);
  return out;
}

export function wavBytes(samples, rate) {
  // 16-bit mono PCM WAV with the plain 44-byte header
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const put = (at, s) => { for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i)); };
  put(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); put(8, "WAVE"); put(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  put(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) v.setInt16(44 + 2 * i, Math.round(Math.max(-1, Math.min(1, samples[i])) * 32767), true);
  return buf;
}

export function wav(samples, rate) {
  return new Blob([wavBytes(samples, rate)], { type: "audio/wav" });
}

/* ---------- calibration ---------- */

export const CLICKS = { beat: 0.6, count: 12, lead: 4 }; // a click every 0.6 s, the first four to count you in

export function scheduleClicks(ctx, when) {
  // short blips from `when`, the count-in a little lower
  for (let k = 0; k < CLICKS.count; k++) {
    const osc = ctx.createOscillator(), env = ctx.createGain();
    osc.frequency.value = k < CLICKS.lead ? 880 : 1320;
    env.gain.setValueAtTime(0, when + k * CLICKS.beat);
    env.gain.linearRampToValueAtTime(0.5, when + k * CLICKS.beat + 0.002);
    env.gain.exponentialRampToValueAtTime(0.001, when + k * CLICKS.beat + 0.06);
    osc.connect(env).connect(ctx.destination);
    osc.start(when + k * CLICKS.beat);
    osc.stop(when + k * CLICKS.beat + 0.08);
  }
}

export function tapLags(chunks, rate, when) {
  // how long after each click (past the count-in) a tap began: where the loudness of
  // 5 ms windows first jumps well above the quiet, near the click
  const win = Math.round(0.005 * rate);
  const energy = [];
  for (const c of chunks) for (let i = 0; i < c.samples.length; i += win) {
    let e = 0;
    for (let j = i; j < Math.min(i + win, c.samples.length); j++) e += c.samples[j] * c.samples[j];
    energy.push({ t: (c.frame + i) / rate, e });
  }
  const sorted = energy.map(x => x.e).sort((a, b) => a - b);
  const floor = sorted[Math.floor(sorted.length * 0.3)] || 0, loud = sorted[Math.floor(sorted.length * 0.99)] || 0;
  const threshold = Math.max(floor * 8, loud * 0.15);
  const onsets = [];
  let quiet = 0;
  for (const x of energy) {
    if (x.e < threshold) { quiet++; continue; }
    if (quiet >= 12) onsets.push(x.t);
    quiet = 0;
  }
  const lags = [];
  for (let k = CLICKS.lead; k < CLICKS.count; k++) {
    const click = when + k * CLICKS.beat;
    const near = onsets.filter(t => t > click - 0.2 && t < click + 0.5);
    if (near.length) lags.push(near.reduce((a, b) => (Math.abs(a - click - 0.1) < Math.abs(b - click - 0.1) ? a : b)) - click);
  }
  return lags.sort((a, b) => a - b);
}

/* ---------- a guide that came through a compressed file ---------- */

export function envelope(data, rate, seconds, frame = 0.001) {
  // RMS in `frame`-second windows over the first `seconds` of a mono signal
  const n = Math.floor(seconds / frame), out = new Float32Array(n);
  for (let k = 0; k < n; k++) {
    const a = Math.floor(k * frame * rate), b = Math.min(Math.floor((k + 1) * frame * rate), data.length);
    let e = 0;
    for (let i = a; i < b; i++) e += data[i] * data[i];
    out[k] = b > a ? Math.sqrt(e / (b - a)) : 0;
  }
  return out;
}

export function decodeOffset(decoded, rate, reference, frame = 0.001, reach = 0.08) {
  /* Seconds of silence a decoder put in front of the guide (an MP3 decoder that
     ignores the encoder's delay adds about 25 to 50 ms), found by sliding the
     decoded guide's opening loudness against `reference`, the same measured on
     the original before it was encoded; 0 if nothing is clearly better. */
  const ref = Float32Array.from(reference);
  const env = envelope(decoded, rate, ref.length * frame + reach + 0.01, frame);
  const norm = a => { const m = a.reduce((s, v) => s + v, 0) / a.length; const d = a.map(v => v - m); const l = Math.hypot(...d) || 1; return d.map(v => v / l); };
  const r = norm(Array.from(ref));
  const corr = [];
  const steps = Math.round(reach / frame);
  for (let lag = -5; lag <= steps; lag++) {
    const seg = [];
    for (let k = 0; k < r.length; k++) { const j = k + lag; seg.push(j >= 0 && j < env.length ? env[j] : 0); }
    const s = norm(seg);
    let c = 0;
    for (let k = 0; k < r.length; k++) c += r[k] * s[k];
    corr.push({ lag, c });
  }
  const best = corr.reduce((a, b) => (b.c > a.c ? b : a));
  if (best.c < 0.8) return 0; // no clear match: trust the decoder
  const i = corr.indexOf(best);
  const a = corr[i - 1], b = corr[i + 1];
  let lag = best.lag;
  if (a && b) { const den = a.c - 2 * best.c + b.c; if (den < 0) lag += 0.5 * (a.c - b.c) / den; }
  const seconds = lag * frame;
  return Math.abs(seconds) < 0.002 ? 0 : seconds;
}

/* ---------- names and times, as the pages show them ---------- */

export function slug(name) {
  // the folder a singer's takes go in (slug() in tools/takes.py): lowercase letters and digits
  // joined by hyphens, accents dropped, other scripts kept
  const plain = String(name ?? "").normalize("NFKD").replace(/\p{M}/gu, "");
  return plain.trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "") || "someone";
}

export const ARTIST_ZONE = "America/Los_Angeles";

export function moment(iso, zone) {
  // "Sunday, September 27 at 10 PM" on the clock of `zone` (an IANA name; the device's own if none)
  const d = new Date(iso);
  if (!iso || isNaN(d)) return "";
  const p = {};
  const format = new Intl.DateTimeFormat("en-US", { timeZone: zone, weekday: "long", day: "numeric", month: "long",
                                                    hour: "numeric", minute: "2-digit", hour12: true });
  for (const { type, value } of format.formatToParts(d)) p[type] = value;
  const time = p.minute === "00" ? `${p.hour} ${p.dayPeriod}` : `${p.hour}:${p.minute} ${p.dayPeriod}`;
  return `${p.weekday}, ${p.month} ${p.day} at ${time}`;
}

export function closingTime(iso, zone) {
  // when singing closes, on the artist's clock, and on the singer's too when it reads differently
  const there = moment(iso, ARTIST_ZONE), here = moment(iso, zone);
  if (!there) return "";
  return here === there ? `${there} Pacific` : `${there} Pacific (${here} your time)`;
}
