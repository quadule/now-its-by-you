// Learning "Now It's by You" at the piano: falling notes over a keyboard, from a score.json (songbird/piano.py):
// the released rendition's (web/piano/, by tools/piano_score.py), or, opened from the studio, the version on the
// studio's page (?score=score/KEY.json, which songbird/studio.py makes). Web MIDI in and out, the screen's keys and the computer's; speed, key, hands,
// loops, count-in, metronome, "wait for me", and a small Web Audio piano (sound.js). No libraries, no build.
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const S = window.PianoSound;

  // the player's own keyboard: its keys and, for a C-to-C one, its lowest C as it usually starts (a learned one
  // keeps the two notes pressed)
  const KEYBOARDS = { any: null, 25: [25, 48], 37: [37, 48], 49: [49, 36], 61: [61, 36], 88: [88, 21], mine: null };

  // ------------------------------------------------------------------ settings, remembered in localStorage
  const DEFAULTS = {
    speed: 100, transpose: 0, rit: true, hands: "right", leftpart: "fifths", volRight: 80, volLeft: 65,
    muteRight: false, muteLeft: false, along: true, guide: false, wait: false, countin: true, metro: false,
    loop: "off", lastLoop: "custom", loopA: 1, loopB: 4, theme: "auto", names: true, midiIn: "*", midiOut: "",
    echo: true, octave: 0,
    kb: "any", kbLo: 48, kbHi: 84, octR: 0, octL: 0, anyOct: false,
    madeFor: 0, // the score's key (its tonic, a MIDI note) that the key and the hands' octaves were set against
  };
  const set = Object.assign({}, DEFAULTS);
  try {
    const saved = JSON.parse(localStorage.getItem("songbird.piano") || "{}");
    for (const k of Object.keys(DEFAULTS)) {
      if (saved && typeof saved[k] === typeof DEFAULTS[k]) set[k] = saved[k];
    }
  } catch (e) { /* no storage here: the defaults */ }
  let saveTimer = 0;
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem("songbird.piano", JSON.stringify(set)); } catch (e) { /* private window */ }
    }, 200);
  }
  set.speed = clamp(Math.round(set.speed / 5) * 5, 25, 125);
  set.transpose = clamp(Math.round(set.transpose), -6, 6);
  set.octave = clamp(Math.round(set.octave), -3, 3);
  if (!["right", "left", "both", "none"].includes(set.hands)) set.hands = "right";
  if (!["auto", "light", "dark"].includes(set.theme)) set.theme = "auto";
  if (!Object.prototype.hasOwnProperty.call(KEYBOARDS, set.kb)) set.kb = "any";
  set.kbLo = clamp(Math.round(set.kbLo), 21, 96); set.kbHi = clamp(Math.round(set.kbHi), set.kbLo + 12, 108);
  set.octR = clamp(Math.round(set.octR), -3, 3); set.octL = clamp(Math.round(set.octL), -3, 3);

  function clamp(x, lo, hi) { return Math.max(lo, Math.min(hi, x)); }

  // ------------------------------------------------------------------ names
  // spelt by the key's signature, as the studio spells (songbird/theory.py spelling): each of the key's notes on its
  // own letter (G# in C# minor, E# in F# major), another natural if it can be, else sharp or flat as the key is
  const LETTERS = "CDEFGAB", NATURAL = [0, 2, 4, 5, 7, 9, 11];
  const MODES = { major: [0, 2, 4, 5, 7, 9, 11], ionian: [0, 2, 4, 5, 7, 9, 11], dorian: [0, 2, 3, 5, 7, 9, 10],
    phrygian: [0, 1, 3, 5, 7, 8, 10], lydian: [0, 2, 4, 6, 7, 9, 11], mixolydian: [0, 2, 4, 5, 7, 9, 10],
    minor: [0, 2, 3, 5, 7, 8, 10], aeolian: [0, 2, 3, 5, 7, 8, 10], locrian: [0, 1, 3, 5, 6, 8, 10] };
  const ACC = { "-2": "bb", "-1": "b", 0: "", 1: "#", 2: "x" };
  const alter = (pc, letter) => ((((pc - NATURAL[letter % 7]) % 12) + 18) % 12) - 6;
  function spelling(pc0, mode) {
    const steps = MODES[mode] || MODES.major, base = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
    const sig = (l) => steps.reduce((n, s, d) => n + alter(pc0 + s, l + d), 0);
    let l = LETTERS.indexOf(base[pc0][0]);
    if (alter(pc0, l)) {  // of the key's two names the one with the fewer sharps or flats: Db major, G# minor
      const other = (l + (alter(pc0, l) > 0 ? 1 : 6)) % 7;
      if (Math.abs(sig(other)) < Math.abs(sig(l))) l = other;
    }
    const s = sig(l), own = new Set(steps.map((x) => (pc0 + x) % 12)), out = base.slice();
    for (let pc = 0; pc < 12; pc++) {
      if (NATURAL.includes(pc) && !own.has(pc)) out[pc] = LETTERS[NATURAL.indexOf(pc)];
      else if (s > 0 && NATURAL.includes((pc + 11) % 12)) out[pc] = LETTERS[NATURAL.indexOf((pc + 11) % 12)] + "#";
      else if (s < 0 && NATURAL.includes((pc + 1) % 12)) out[pc] = LETTERS[NATURAL.indexOf((pc + 1) % 12)] + "b";
    }
    steps.forEach((x, d) => { out[(pc0 + x) % 12] = LETTERS[(l + d) % 7] + ACC[alter(pc0 + x, l + d)]; });
    return out;
  }
  const WHITE = new Set([0, 2, 4, 5, 7, 9, 11]);
  const QUAL = { maj: "", min: "m", dim: "dim", aug: "+", sus2: "sus2", sus4: "sus4", 7: "7", maj7: "maj7", m7: "m7",
    m7b5: "m7b5", dim7: "dim7", 6: "6", m6: "m6", add9: "add9", madd9: "m(add9)", "7sus4": "7sus4", "7sus2": "7sus2" };

  let score = null;
  const keyPc = () => (((score.key.tonicPc + set.transpose) % 12) + 12) % 12;
  const spell = (pc) => spelling(keyPc(), score.key.mode)[((pc % 12) + 12) % 12];
  const noteName = (p, octave) => { const n = spell(p); return n + (octave ? Math.floor(p / 12) - 1 + (n[0] === "B" && p % 12 === 0 ? -1 : n[0] === "C" && p % 12 === 11 ? 1 : 0) : ""); };
  const keyName = () => `${spell(keyPc())} ${score.key.mode}`;
  const chordName = (c) => spell(c.root + set.transpose) + (QUAL[c.quality] || "") +
    (c.bass !== undefined && c.bass !== c.root ? "/" + spell(c.bass + set.transpose) : ""); // a person's inversion

  // ------------------------------------------------------------------ the song's clock
  // Beats from the song's first bar line; the rendition's last phrase slows down (score.ritardando):
  // seconds(b) = 60/bpm * (b + amount * x^2 / (2 * span)), x the beats past its start.
  let SPB = 0.625;
  function secOf(b) {
    const r = score.ritardando;
    if (!set.rit || !r || b <= r.from) return b * SPB;
    const x = b - r.from;
    return (b + r.amount * x * x / (2 * (r.to - r.from))) * SPB;
  }
  function beatOf(sec) {
    const r = score.ritardando, u = sec / SPB;
    if (!set.rit || !r || u <= r.from || r.amount <= 0) return u;
    const a = r.amount / (2 * (r.to - r.from)), c = u - r.from;
    return r.from + (-1 + Math.sqrt(1 + 4 * a * c)) / (2 * a);
  }
  const speed = () => set.speed / 100;

  // ------------------------------------------------------------------ the notes being learned
  let notes = [];      // {p, s, d, h: "R"|"L", lyric, first, by, state: 0 | 1 hit | 2 missed}
  let maxDur = 4;
  let songStart = 0, songEnd = 0;
  let range = [48, 76]; // the keyboard drawn: lowest and highest MIDI note

  function build() {
    const left = (score.left[set.leftpart] || score.left.fifths).notes;
    notes = [];
    for (const n of score.melody) {
      notes.push({ p: n.pitch, s: n.start, d: n.dur, h: "R", lyric: n.lyric || "", first: !!n.phraseStart, by: n.by || "", state: 0 });
    }
    for (const n of left) notes.push({ p: n.pitch, s: n.start, d: n.dur, h: "L", state: 0 });
    notes.sort((a, b) => a.s - b.s || a.p - b.p);
    folded = 0;
    const kb = keyboard();
    for (const n of notes) { // q: the key it's played on, in the key chosen, each hand moved by its octaves
      n.q = n.p + set.transpose + 12 * (n.h === "R" ? set.octR : set.octL);
      n.folded = false;
      if (kb) { // a note still off the player's keyboard goes an octave (or two) in, marked
        while (n.q < kb[0]) { n.q += 12; n.folded = true; }
        while (n.q > kb[1]) { n.q -= 12; n.folded = true; }
        if (n.folded) folded++;
      }
    }
    maxDur = Math.max(...notes.map((n) => n.d));
    songStart = Math.min(0, notes[0].s);
    songEnd = score.end;
    fitRange();
  }

  // the keys the player has, if they said: [lowest, highest]
  function keyboard() {
    if (set.kb === "any") return null;
    if (set.kb === "mine") return [set.kbLo, set.kbHi];
    const [count, lo] = KEYBOARDS[set.kb];
    const from = set.kbLo % 12 === lo % 12 ? set.kbLo : lo; // a C-to-C board keeps where it was moved to
    return [from, from + count - 1];
  }
  let folded = 0; // notes moved an octave in to fit the player's keyboard

  // each hand's octaves so the song fits the player's keyboard: fewest notes off it, then the hands apart
  // (the left below the right), then as near as written
  function fitHands() {
    const kb = keyboard();
    if (!kb) { set.octR = 0; set.octL = 0; return; }
    const left = (score.left[set.leftpart] || score.left.fifths).notes.map((n) => n.pitch + set.transpose);
    const right = score.melody.map((n) => n.pitch + set.transpose);
    const off = (ps, o) => ps.reduce((k, p) => k + (p + 12 * o < kb[0] || p + 12 * o > kb[1] ? 1 : 0), 0);
    let best = null;
    for (let r = -3; r <= 3; r++) for (let l = -3; l <= 3; l++) {
      const clash = Math.max(0, Math.max(...left) + 12 * l - (Math.min(...right) + 12 * r));
      const cost = 1000 * (off(right, r) + off(left, l)) + 10 * clash + Math.abs(r) + Math.abs(l);
      if (!best || cost < best.cost) best = { cost, r, l };
    }
    set.octR = best.r; set.octL = best.l;
  }

  function fitRange() {
    const kb = keyboard();
    if (kb) { range = kb.slice(); return; }
    let lo = Infinity, hi = -Infinity;
    for (const n of notes) { lo = Math.min(lo, n.q); hi = Math.max(hi, n.q); }
    lo -= 2; hi += 2;
    while (!(lo % 12 === 0 || lo % 12 === 5)) lo--;   // from a C or an F
    while (!(hi % 12 === 4 || hi % 12 === 11)) hi++;  // to an E or a B
    if (hi - lo < 24) hi += 12;
    range = [lo, hi];
  }

  const practised = (h) => set.hands === "both" || (set.hands === "right" && h === "R") || (set.hands === "left" && h === "L");
  const judging = () => set.hands !== "none";

  // the first index whose start is >= b (notes sorted by start)
  function firstFrom(b) {
    let lo = 0, hi = notes.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (notes[m].s < b - 1e-9) lo = m + 1; else hi = m; }
    return lo;
  }

  // where a bar's music begins: its bar line, or the pickup before it
  function barStart(bar) { return (bar - 1) * score.timeSignature[0]; }
  function pickupBefore(beat) {
    for (const n of score.melody) {
      if (n.phraseStart && n.start < beat - 1e-9 && n.start >= beat - 2) return n.start;
    }
    return beat;
  }
  function loopRange() {
    if (set.loop === "off") return null;
    let a, b;
    if (set.loop === "custom") {
      const A = clamp(Math.min(set.loopA, set.loopB), 1, score.bars), B = clamp(Math.max(set.loopA, set.loopB), 1, score.bars);
      a = barStart(A); b = barStart(B + 1);
    } else {
      const sec = score.sections[+set.loop];
      if (!sec) return null;
      a = sec.start; b = sec.end;
    }
    return [pickupBefore(a), b >= songEnd - 1e-9 ? songEnd : pickupBefore(b)];
  }

  // ------------------------------------------------------------------ the transport
  // While playing, beats follow the audio clock from an anchor (an audio time and the beat there). A loop's
  // wrap is scheduled ahead of time as a second anchor, which the display takes up when its time comes.
  const T = {
    playing: false, beat: 0, anchors: [], schedBeat: 0, songFrom: 0, countFrom: 0,
    gate: null, gateFrom: 0, judgeFrom: Infinity, gateDone: false, waiting: false, need: new Set(), got: new Set(),
    tally: { right: 0, missed: 0, wrong: 0 }, pass: 1,
  };
  const beatAt = (t, a) => beatOf(secOf(a.beat) + (t - a.audio) * speed());
  const audioAt = (b, a) => a.audio + (secOf(b) - secOf(a.beat)) / speed();

  function beatNow() {
    if (!T.playing) return T.beat;
    const now = S.now();
    while (T.anchors.length > 1 && T.anchors[1].audio <= now) { T.anchors.shift(); wrapped(); }
    let b = beatAt(now, T.anchors[0]);
    if (T.gate !== null && T.anchors.length === 1 && b >= T.gate) {
      b = T.gate;
      if (!T.waiting) arrive();
    }
    return b;
  }

  function resetStates(from, to) {
    for (const n of notes) if (n.s >= from - 1e-9 && n.s < to - 1e-9) n.state = 0;
  }

  function play() {
    if (!S.start()) { status("This browser can't make sound (no Web Audio)."); }
    if (T.playing) return;
    const loop = loopRange();
    let from = T.beat;
    if (loop && (from < loop[0] - 1e-9 || from >= loop[1] - 1e-9)) from = loop[0];
    if (from >= songEnd - 1e-9) from = songStart;
    const count = set.countin ? (Number.isInteger(from) ? from : Math.floor(from)) - score.timeSignature[0] : from;
    T.songFrom = from; T.countFrom = count;
    T.anchors = [{ audio: S.now() + 0.08, beat: count }];
    T.schedBeat = count;
    T.gate = null; T.gateFrom = from; T.gateDone = false; T.waiting = false;
    T.playing = true; T.judgeFrom = Infinity; // misses count from the first key played
    resetStates(from, loop ? loop[1] : songEnd);
    tick();
    ui.playing();
  }

  function pause() {
    if (!T.playing) return;
    T.beat = Math.max(songStart, beatNow());
    T.playing = false; T.waiting = false; T.gate = null;
    S.silence(); midiOutOff();
    ui.playing();
  }

  function seek(b) {
    b = clamp(b, songStart, songEnd);
    if (T.playing) {
      S.silence(); midiOutOff();
      T.anchors = [{ audio: S.now() + 0.05, beat: b }];
      T.schedBeat = b; T.songFrom = b; T.countFrom = b; T.judgeFrom = Infinity;
      T.gate = null; T.gateFrom = b; T.gateDone = false; T.waiting = false;
      resetStates(b, songEnd);
    } else {
      T.beat = b;
    }
    draw();
  }

  // Something about the playing changed (speed, key, hands): carry on from here with it.
  function resync() {
    if (!T.playing) return;
    const b = beatNow();
    S.silence(); midiOutOff();
    const waitingAt = T.waiting ? T.gate : null;
    T.anchors = [{ audio: S.now() + 0.05, beat: b }];
    T.schedBeat = b;
    T.waiting = false; T.gate = null; T.gateDone = false;
    T.gateFrom = waitingAt !== null ? waitingAt : b;
  }

  function restart() {
    const loop = loopRange();
    const to = loop ? loop[0] : songStart;
    T.tally = { right: 0, missed: 0, wrong: 0 }; T.pass = 1;
    resetStates(songStart, songEnd);
    if (T.playing) { pause(); T.beat = to; play(); } else seek(to);
    ui.tally();
  }

  // a loop came round: its notes are fresh again
  function wrapped() {
    const loop = loopRange();
    if (loop) resetStates(loop[0], loop[1]);
    if (T.judgeFrom !== Infinity) T.judgeFrom = -Infinity; // playing along: the whole loop counts now
    T.pass += 1;
  }

  // ------------------------------------------------------------------ wait for me
  // The next beat where the practised hand has a note to strike. The clock stops there until every note
  // struck at that beat has been played (a note played a moment early counts).
  function nextGate(from, to) {
    for (let i = firstFrom(from); i < notes.length && notes[i].s < to - 1e-9; i++) {
      if (practised(notes[i].h) && notes[i].s >= T.songFrom - 1e-9) return notes[i].s;
    }
    return null;
  }
  function ensureGate(end) {
    if (!set.wait || !judging() || T.gate !== null || T.gateDone) return;
    T.gate = nextGate(T.gateFrom, end);
    if (T.gate === null) T.gateDone = true;
  }
  function gateNotes() {
    const out = [];
    for (let i = firstFrom(T.gate); i < notes.length && notes[i].s < T.gate + 1e-6; i++) if (practised(notes[i].h)) out.push(notes[i]);
    return out;
  }
  function arrive() {
    T.waiting = true;
    const here = gateNotes();
    T.need = new Set(here.map((n) => n.q));
    T.got = new Set(here.filter((n) => n.state === 1).map((n) => n.q));
    if ([...T.need].every((p) => T.got.has(p))) release();
  }
  function release() {
    const at = T.gate;
    T.waiting = false; T.gate = null; T.gateFrom = at + 1e-6;
    T.anchors = [{ audio: S.now() + 0.01, beat: at }];
    tick();
  }

  // ------------------------------------------------------------------ the scheduler: a little ahead of the clock
  const AHEAD = 0.18;
  function tick() {
    if (!T.playing) return;
    const horizon = S.now() + AHEAD;
    for (let guard = 0; guard < 4; guard++) {
      const a = T.anchors[T.anchors.length - 1];
      const loop = loopRange();
      const end = loop ? loop[1] : songEnd + 3;
      ensureGate(loop ? loop[1] : songEnd);
      let upto = Math.min(beatAt(horizon, a), end);
      if (T.gate !== null) upto = Math.min(upto, T.gate); // the gate is always the latest pass's
      if (upto > T.schedBeat) { schedule(T.schedBeat, upto, a); T.schedBeat = upto; }
      if (loop && T.schedBeat >= loop[1] - 1e-9 && T.gate === null) {
        const at = audioAt(loop[1], a);
        T.anchors.push({ audio: at, beat: loop[0] });
        T.schedBeat = loop[0]; T.songFrom = loop[0]; T.gateFrom = loop[0]; T.gateDone = false;
        continue;
      }
      break;
    }
  }

  function heard(h) {
    const vol = h === "R" ? (set.muteRight ? 0 : set.volRight / 100) : (set.muteLeft ? 0 : set.volLeft / 100);
    if (practised(h)) return set.guide ? vol : 0;
    return set.hands === "none" || set.along ? vol : 0;
  }

  function schedule(from, to, a) {
    const loop = loopRange();
    for (let i = firstFrom(from); i < notes.length && notes[i].s < to - 1e-9; i++) {
      const n = notes[i];
      if (n.s < T.songFrom - 1e-9 || (loop && n.s < loop[0] - 1e-9)) continue;
      const gain = heard(n.h);
      if (gain <= 0) continue;
      const t0 = audioAt(n.s, a), t1 = audioAt(Math.min(n.s + n.d, loop ? loop[1] : n.s + n.d), a);
      const p = n.q, vel = n.h === "R" ? 0.72 : 0.6;
      if (midi.out) midiOutNote(p, vel * gain, t0, t1, n.h === "R" ? 0 : 1);
      else S.note(p, vel, t0, t1 - t0 + (n.h === "L" ? 0.15 : 0.05), gain);
    }
    // the count-in's clicks, and the metronome's
    const bar = score.timeSignature[0];
    for (let k = Math.ceil(from - 1e-9); k < to - 1e-9; k++) {
      const counting = k < T.songFrom - 1e-9 && k >= T.countFrom - 1e-9;
      if (counting || (set.metro && k >= T.songFrom - 1e-9 && k < songEnd)) {
        S.click(audioAt(k, a), ((k % bar) + bar) % bar === 0, counting ? 1 : 0.8);
      }
    }
  }
  setInterval(tick, 25);

  // ------------------------------------------------------------------ playing along: right, missed, wrong
  const down = new Map();   // sounding pitch -> how many sources hold it
  const flash = new Map();  // pitch -> {good, until}
  function tolerance() { return clamp(0.2 * speed() / SPB, 0.12, 0.5); } // beats either side of a note

  // a key played for a note: the same key, or with "any octave counts" the same note in any octave
  const same = (q, p) => (set.anyOct ? ((q - p) % 12 + 12) % 12 === 0 : q === p);

  function judge(p) {
    if (!judging()) return;
    const key = p, good = (ok) => flash.set(key, { good: ok, until: performance.now() + 260 });
    if (T.waiting) {
      const q = [...T.need].find((q) => same(q, p)); // the note it stands for (itself, or in any octave)
      if (q !== undefined) {
        p = q;
        T.got.add(p);
        for (const n of gateNotes()) if (n.q === p && n.state !== 1) { n.state = 1; T.tally.right++; }
        good(true);
        if ([...T.need].every((q) => T.got.has(q))) release();
      } else { T.tally.wrong++; good(false); }
      ui.tally();
      return;
    }
    if (!T.playing) { // stopped: say whether it's a note the practised hand plays here
      const here = notes.some((n) => practised(n.h) && same(n.q, p) && n.s <= T.beat + 0.01 && n.s + n.d > T.beat);
      good(here);
      return;
    }
    const b = beatNow(), tol = tolerance();
    if (T.judgeFrom === Infinity) T.judgeFrom = b - tol;
    let best = null;
    for (let i = firstFrom(b - tol); i < notes.length && notes[i].s <= b + tol + (set.wait ? 0.35 : 0); i++) {
      const n = notes[i];
      if (n.state === 0 && practised(n.h) && same(n.q, p) && n.s >= T.songFrom - 1e-9) {
        if (!best || Math.abs(n.s - b) < Math.abs(best.s - b)) best = n;
      }
    }
    if (best) { best.state = 1; T.tally.right++; good(true); } else { T.tally.wrong++; good(false); }
    ui.tally();
  }

  function sweepMissed(b) { // notes whose moment has passed unplayed
    if (!T.playing || !judging() || set.wait) return;
    const tol = tolerance(), loop = loopRange();
    let changed = false;
    for (let i = firstFrom(Math.max(T.songFrom, b - maxDur - 2)); i < notes.length && notes[i].s < b - tol; i++) {
      const n = notes[i];
      if (n.state === 0 && practised(n.h) && n.s >= T.songFrom - 1e-9 && n.s >= T.judgeFrom && (!loop || n.s >= loop[0] - 1e-9)) {
        n.state = 2; T.tally.missed++; changed = true;
      }
    }
    if (changed) ui.tally();
  }

  // learning the player's keyboard: the lowest key pressed first, then the highest
  let learning = null; // null, "low", or the lowest key's pitch while waiting for the highest
  function learn(p) {
    if (learning === "low") { learning = p; status("Now press its highest key."); return; }
    const lo = Math.min(learning, p), hi = Math.max(learning, p);
    learning = null;
    if (hi - lo < 12) { status("That's less than an octave: press Learn and try again."); ui.settings(); return; }
    change(() => { set.kb = "mine"; set.kbLo = lo; set.kbHi = hi; fitHands(); }, "build");
    status(`Your keyboard: ${noteName(lo, true)} to ${noteName(hi, true)}, ${hi - lo + 1} keys.`);
  }

  function noteOn(p, vel, source) {
    S.start();
    if (learning !== null) { learn(p); return; }
    const k = source + ":" + p;
    if (source !== "midi" || set.echo) S.down(k, p, vel, 0.9);
    down.set(p, (down.get(p) || 0) + 1);
    judge(p);
    draw();
  }
  let pedal = false;
  const pedalled = new Set();
  function noteOff(p, source) {
    const k = source + ":" + p;
    if (source === "midi" && pedal) pedalled.add(k); else S.up(k);
    const c = (down.get(p) || 1) - 1;
    if (c <= 0) down.delete(p); else down.set(p, c);
    draw();
  }
  function setPedal(on) {
    pedal = on;
    if (!on) { pedalled.forEach((k) => S.up(k)); pedalled.clear(); }
  }

  // ------------------------------------------------------------------ the roll and the keyboard
  const canvas = $("roll"), g = canvas.getContext("2d");
  let W = 0, H = 0, dpr = 1, keys = [];  // keys: {p, x, w, black}
  const C = {};
  function colours() {
    const cs = getComputedStyle(document.documentElement), v = (n) => cs.getPropertyValue(n).trim();
    Object.assign(C, {
      stage: v("--stage") || "#1b1611", panel: v("--stage-panel") || "#221c16", ink: v("--stage-ink") || "#efe6da",
      dim: v("--stage-dim") || "#9a8d7f", red: v("--stage-red") || "#e0664d", R: v("--right") || "#f2b25c",
      L: v("--left") || "#8fb3e8", good: v("--good") || "#8ccf7e", bad: v("--bad") || "#e0664d",
      serif: v("--serif") || "Georgia, serif", sans: v("--sans") || "system-ui, sans-serif",
    });
  }
  function resize() {
    dpr = window.devicePixelRatio || 1;
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    layoutKeys();
    draw();
  }
  function layoutKeys() {
    const [lo, hi] = range;
    let whites = 0;
    for (let p = lo; p <= hi; p++) if (WHITE.has(p % 12)) whites++;
    const ww = W / whites;
    keys = [];
    let x = 0;
    for (let p = lo; p <= hi; p++) {
      if (WHITE.has(p % 12)) { keys.push({ p, x, w: ww, black: false }); x += ww; }
      else keys.push({ p, x: x - ww * 0.31, w: ww * 0.62, black: true });
    }
  }
  const keyOf = (p) => keys[p - range[0]];
  const kbH = () => clamp(H * 0.22, 64, 140);

  function roundRect(x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    g.beginPath();
    g.moveTo(x + r, y); g.lineTo(x + w - r, y); g.quadraticCurveTo(x + w, y, x + w, y + r);
    g.lineTo(x + w, y + h - r); g.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    g.lineTo(x + r, y + h); g.quadraticCurveTo(x, y + h, x, y + h - r);
    g.lineTo(x, y + r); g.quadraticCurveTo(x, y, x + r, y);
    g.closePath();
  }
  function alpha(hex, a) {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
    return m ? `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})` : hex;
  }

  let drawQueued = false;
  function draw() {
    if (drawQueued || !score) return;
    drawQueued = true;
    requestAnimationFrame(() => { drawQueued = false; paint(beatNow()); });
  }

  function paint(b) {
    if (!W || !H) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const kh = kbH(), top = H - kh, look = clamp(top / 46, 5, 10); // beats in view above the keyboard
    const ppb = top / look;
    const y = (beat) => top - (beat - b) * ppb;
    const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 160);
    g.fillStyle = C.stage; g.fillRect(0, 0, W, H);

    // lanes: the black keys' a shade darker, a line at every C
    for (const k of keys) {
      if (k.black) { g.fillStyle = "rgba(0,0,0,.22)"; g.fillRect(k.x, 0, k.w, top); }
      else if (k.p % 12 === 0) { g.fillStyle = "rgba(239,230,218,.09)"; g.fillRect(k.x, 0, 1, top); }
    }
    // a loop's span, shaded
    const loop = loopRange();
    if (loop) {
      g.fillStyle = "rgba(242,178,92,.05)";
      const y0 = clamp(y(loop[1]), 0, top), y1 = clamp(y(loop[0]), 0, top);
      if (y1 > y0) g.fillRect(0, y0, W, y1 - y0);
    }
    // bar lines, bar numbers, sections, chords
    g.textBaseline = "bottom";
    const beatsPerBar = score.timeSignature[0];
    for (let bar = Math.max(1, Math.floor(b / beatsPerBar)); bar <= score.bars + 1; bar++) {
      const at = barStart(bar), yy = y(at);
      if (yy < -20) break;
      if (yy > top) continue;
      g.fillStyle = "rgba(239,230,218,.16)"; g.fillRect(0, Math.round(yy), W, 1);
      g.fillStyle = C.dim; g.font = `12px ${C.sans}`; g.textAlign = "left";
      if (bar <= score.bars) g.fillText(String(bar), 5, yy - 2);
      for (let k = 1; k < beatsPerBar; k++) {
        const yb = y(at + k);
        if (yb >= 0 && yb <= top) { g.fillStyle = "rgba(239,230,218,.05)"; g.fillRect(0, Math.round(yb), W, 1); }
      }
    }
    for (const [i, sec] of score.sections.entries()) {
      const yy = y(sec.start);
      if (yy < 0 || yy > top + 30) continue;
      g.fillStyle = C.red; g.font = `600 14px ${C.serif}`; g.textAlign = "left";
      g.fillText(sectionLabel(i).toUpperCase(), 26, yy - 2);
    }
    g.textAlign = "right";
    for (const c of score.chords) {
      const yy = y(c.start);
      if (yy < 0 || yy > top + 0.5) continue; // the chord now is in the head above
      g.fillStyle = c.start <= b && b < c.end ? C.ink : C.dim;
      g.font = `600 16px ${C.serif}`;
      g.fillText(chordName(c), W - 6, yy - 2);
    }

    // the notes
    const i0 = firstFrom(b - maxDur - 0.01);
    g.textAlign = "center"; g.textBaseline = "middle";
    for (let i = i0; i < notes.length; i++) {
      const n = notes[i];
      if (n.s > b + look + 0.1) break;
      if (n.s + n.d < b - 0.001) continue;
      const k = keyOf(n.q);
      if (!k) continue;
      const y1 = y(n.s), y0 = y(n.s + n.d), hgt = Math.max(3, y1 - y0 - 2);
      const col = n.h === "R" ? C.R : C.L, mine = practised(n.h);
      const x = k.x + 1.5, w = k.w - 3;
      roundRect(x, y1 - hgt, w, hgt, 3);
      if (n.state === 1) g.fillStyle = C.good;
      else if (n.state === 2) g.fillStyle = alpha(col, 0.25);
      else g.fillStyle = mine || !judging() ? col : alpha(col, 0.45);
      g.fill();
      if (n.state === 2) { g.strokeStyle = C.bad; g.lineWidth = 2; g.stroke(); }
      else if (n.folded) { g.setLineDash([3, 2]); g.strokeStyle = C.ink; g.lineWidth = 1.5; g.stroke(); g.setLineDash([]); }
      if (T.waiting && mine && Math.abs(n.s - T.gate) < 1e-6 && !T.got.has(n.q)) {
        g.strokeStyle = alpha("#ffffff", 0.4 + 0.5 * pulse); g.lineWidth = 2.5; g.stroke();
      }
      if (set.names && hgt >= 14 && w >= 13) {
        g.fillStyle = "rgba(27,22,17,.85)"; g.font = `600 ${w >= 20 ? 11 : 9}px ${C.sans}`;
        g.fillText(noteName(n.q), x + w / 2, y1 - Math.min(hgt / 2, 9));
      }
      if (n.lyric && hgt >= 10) {
        g.fillStyle = mine || !judging() ? C.ink : C.dim; g.font = `italic 13px ${C.serif}`; g.textAlign = "left";
        g.fillText(n.lyric, x + w + 4, y1 - Math.min(hgt / 2, 9));
        g.textAlign = "center";
      }
    }

    // the keyboard
    const sounding = new Map(); // pitch -> hand sounding in the score now
    for (let i = i0; i < notes.length && notes[i].s <= b + 1e-6; i++) {
      const n = notes[i];
      if (n.s <= b + 1e-6 && n.s + n.d > b + 1e-6) sounding.set(n.q, n);
    }
    if (T.waiting) for (const p of T.need) { const n = gateNotes().find((m) => m.q === p); if (n) sounding.set(p, n); }
    const now = performance.now();
    g.fillStyle = C.panel; g.fillRect(0, top, W, kh);
    const keyFill = (k) => {
      const f = flash.get(k.p), n = sounding.get(k.p), held = down.has(k.p);
      if (f && f.until > now) return f.good ? C.good : C.bad;
      if (held) return k.black ? "#6d6154" : "#cbbba3";
      if (n) return practised(n.h) || !judging() ? (n.h === "R" ? C.R : C.L) : alpha(n.h === "R" ? C.R : C.L, k.black ? 0.7 : 0.55);
      return k.black ? "#1b1611" : "#efe6da";
    };
    for (const k of keys) {
      if (k.black) continue;
      g.fillStyle = keyFill(k);
      g.fillRect(k.x + 0.5, top + 2, k.w - 1, kh - 3);
      if (k.p % 12 === 0) {
        g.fillStyle = "rgba(43,35,29,.6)"; g.font = `10px ${C.sans}`; g.textBaseline = "bottom";
        g.fillText("C" + (Math.floor(k.p / 12) - 1), k.x + k.w / 2, top + kh - 4);
      }
    }
    for (const k of keys) {
      if (!k.black) continue;
      g.fillStyle = keyFill(k);
      roundRect(k.x, top + 2, k.w, kh * 0.6, 2); g.fill();
    }
    if (T.waiting) { // the keys wanted, outlined
      for (const p of T.need) {
        const k = keyOf(p);
        if (!k || T.got.has(p)) continue;
        g.strokeStyle = alpha("#ffffff", 0.5 + 0.5 * pulse); g.lineWidth = 3;
        g.strokeRect(k.x + 2, top + 4, k.w - 4, (k.black ? kh * 0.6 : kh) - 7);
      }
    }
    // the now line
    g.fillStyle = alpha(C.R, 0.8); g.fillRect(0, top - 1, W, 2);
    g.textBaseline = "alphabetic";
  }

  function sectionLabel(i) {
    const sec = score.sections[i], same = score.sections.filter((s) => s.name === sec.name);
    return same.length > 1 ? `${sec.name} ${same.indexOf(sec) + 1}` : sec.name;
  }

  // pointer: the keys on the screen
  const pointers = new Map(); // pointerId -> pitch
  function keyAt(px, py) {
    const kh = kbH(), top = H - kh;
    if (py < top) return null;
    for (const k of keys) if (k.black && px >= k.x && px < k.x + k.w && py < top + kh * 0.6) return { k, vel: 0.4 + 0.55 * (py - top) / (kh * 0.6) };
    for (const k of keys) if (!k.black && px >= k.x && px < k.x + k.w) return { k, vel: 0.4 + 0.55 * (py - top) / kh };
    return null;
  }
  function pos(e) { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  canvas.addEventListener("pointerdown", (e) => {
    const hit = keyAt(...pos(e));
    if (!hit) return;
    e.preventDefault();
    try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* fine */ }
    pointers.set(e.pointerId, hit.k.p);
    noteOn(hit.k.p, clamp(hit.vel, 0.2, 1), "ptr" + e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!pointers.has(e.pointerId)) return;
    const hit = keyAt(...pos(e)), was = pointers.get(e.pointerId);
    if (hit && hit.k.p !== was) {
      noteOff(was, "ptr" + e.pointerId);
      pointers.set(e.pointerId, hit.k.p);
      noteOn(hit.k.p, clamp(hit.vel, 0.2, 1), "ptr" + e.pointerId);
    }
  });
  const lift = (e) => {
    if (!pointers.has(e.pointerId)) return;
    noteOff(pointers.get(e.pointerId), "ptr" + e.pointerId);
    pointers.delete(e.pointerId);
  };
  canvas.addEventListener("pointerup", lift);
  canvas.addEventListener("pointercancel", lift);
  canvas.addEventListener("lostpointercapture", lift);

  // ------------------------------------------------------------------ MIDI: a keyboard in, and optionally out
  const midi = { access: null, out: null, pending: [] };
  function midiNote(text) { $("midi-note").textContent = text; }
  async function connectMidi(quiet) {
    if (!navigator.requestMIDIAccess) {
      if (!quiet) midiNote("This browser has no Web MIDI (Chrome, Edge, Opera and Firefox have it; Safari doesn't). The screen's keys and the computer's still play.");
      return;
    }
    try {
      midi.access = await navigator.requestMIDIAccess({ sysex: false });
    } catch (e) {
      if (!quiet) midiNote("The browser didn't allow MIDI (" + (e && e.name ? e.name : "refused") + "). Allow it in the site's settings and press Connect again.");
      return;
    }
    midi.access.onstatechange = () => devices();
    devices();
  }
  function devices() {
    if (!midi.access) return;
    const ins = [...midi.access.inputs.values()], outs = [...midi.access.outputs.values()];
    const inSel = $("midi-in"), outSel = $("midi-out");
    inSel.innerHTML = "";
    inSel.append(new Option(ins.length ? "every keyboard" : "no keyboard found", "*"));
    for (const i of ins) inSel.append(new Option(i.name || i.id, i.id));
    inSel.value = [...inSel.options].some((o) => o.value === set.midiIn) ? set.midiIn : "*";
    outSel.innerHTML = "";
    outSel.append(new Option("none: this page sounds", ""));
    for (const o of outs) outSel.append(new Option(o.name || o.id, o.id));
    outSel.value = [...outSel.options].some((o) => o.value === set.midiOut) ? set.midiOut : "";
    for (const i of ins) i.onmidimessage = inSel.value === "*" || inSel.value === i.id ? midiIn : null;
    midi.out = outSel.value ? midi.access.outputs.get(outSel.value) || null : null;
    $("midi-connect").textContent = "Look again";
    midiNote(ins.length ? `${ins.length} MIDI input${ins.length > 1 ? "s" : ""} found. Play!` :
      "MIDI is on, but no keyboard is plugged in. Plug one in: it appears here by itself.");
  }
  function midiIn(e) {
    const [st, d1, d2] = e.data;
    const cmd = st & 0xf0;
    if (cmd === 0x90 && d2 > 0) noteOn(d1, d2 / 127, "midi");
    else if (cmd === 0x80 || (cmd === 0x90 && d2 === 0)) noteOff(d1, "midi");
    else if (cmd === 0xb0 && d1 === 64) setPedal(d2 >= 64);
  }
  function midiStamp(t) { return performance.now() + Math.max(0, t - S.now()) * 1000; }
  function midiOutNote(p, vel, t0, t1, ch) {
    if (!midi.out || p < 0 || p > 127) return;
    try {
      midi.out.send([0x90 | ch, p, clamp(Math.round(vel * 127), 1, 127)], midiStamp(t0));
      midi.out.send([0x80 | ch, p, 0], midiStamp(t1));
    } catch (e) { midi.out = null; }
  }
  function midiOutOff() {
    if (!midi.out) return;
    try {
      if (midi.out.clear) midi.out.clear(); // drop what was scheduled ahead (where the browser can)
      for (const ch of [0, 1]) midi.out.send([0xb0 | ch, 123, 0]);
    } catch (e) { /* the device went away */ }
  }

  // ------------------------------------------------------------------ the page's words and readouts
  const ui = {
    playing() {
      $("play").textContent = T.playing ? "Pause" : "Play";
      $("play").setAttribute("aria-pressed", String(T.playing));
    },
    tally() {
      const t = T.tally, total = t.right + t.missed;
      $("tally").innerHTML = !judging() ? "" : total + t.wrong === 0 ? "" :
        `<span class="ok">${t.right} right</span> &middot; <span class="miss">${t.missed} missed</span> &middot; ${t.wrong} wrong` +
        (total ? ` &middot; ${Math.round(100 * t.right / total)}%` : "");
    },
    settings() {
      $("speed").value = set.speed; $("speed-out").textContent = set.speed + "%";
      $("bpm").textContent = `${Math.round(score.tempo * speed())} bpm` + (set.speed !== 100 ? ` (sung at ${Math.round(score.tempo)})` : "");
      $("keyname").textContent = keyName() + (set.transpose ? ` (${set.transpose > 0 ? "+" : ""}${set.transpose})` : "");
      $("rit").checked = set.rit;
      for (const r of document.querySelectorAll("input[name=hands]")) r.checked = r.value === set.hands;
      for (const r of document.querySelectorAll("input[name=theme]")) r.checked = r.value === set.theme;
      $("leftpart").value = set.leftpart;
      $("vol-right").value = set.volRight; $("vol-left").value = set.volLeft;
      for (const [id, on] of [["mute-right", set.muteRight], ["mute-left", set.muteLeft]]) {
        $(id).setAttribute("aria-pressed", String(on)); $(id).textContent = on ? "Unmute" : "Mute";
        $(id).classList.toggle("primary", on);
      }
      for (const id of ["along", "guide", "wait", "countin", "metro", "echo", "names"]) $(id).checked = set[id];
      const kb = keyboard();
      $("kb").value = set.kb;
      $("kb-range").textContent = kb ? `${noteName(kb[0], true)} to ${noteName(kb[1], true)}` : "whatever the song needs";
      $("kb-down").disabled = $("kb-up").disabled = !kb || set.kb === "mine";
      const oct = (o) => (o === 0 ? "as written" : `${Math.abs(o)} octave${Math.abs(o) > 1 ? "s" : ""} ${o > 0 ? "up" : "down"}`);
      $("oct-r").textContent = oct(set.octR); $("oct-l").textContent = oct(set.octL);
      $("anyoct").checked = set.anyOct;
      $("fit-note").textContent = !kb ? "" : folded ? `${folded} note${folded > 1 ? "s" : ""} of the song moved an octave to stay on your keys (outlined).` :
        "Every note of the song is on your keys.";
      $("kb-learn").textContent = learning === null ? "Learn it" : "Cancel";
      $("loopsel").value = set.loop;
      $("loop-a").value = set.loopA; $("loop-b").value = set.loopB;
      if (set.theme === "auto") delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = set.theme;
      colours();
      ui.tally();
      draw();
    },
  };
  function status(text, waiting) {
    const el = $("status");
    if (el.textContent !== text) el.textContent = text;
    el.classList.toggle("waiting", !!waiting);
  }

  let shown = { bar: -1, sec: -1, chord: null, line: -2, syl: -2 };
  function readouts(b) {
    const beatsPerBar = score.timeSignature[0];
    const bar = clamp(Math.floor(b / beatsPerBar) + 1, 1, score.bars);
    let si = score.sections.findIndex((s) => b >= s.start - 1e-6 && b < s.end - 1e-6);
    if (si < 0) si = b < 0 ? 0 : score.sections.length - 1;
    if (bar !== shown.bar || si !== shown.sec) {
      $("where").innerHTML = `Bar <b>${bar}</b> of ${score.bars} &middot; ${sectionLabel(si)}`;
      $("section").textContent = sectionLabel(si);
      shown.bar = bar; shown.sec = si;
    }
    if (!scrubbing) $("scrub").value = String(Math.max(0, b));
    const ci = score.chords.findIndex((c) => b >= c.start - 1e-6 && b < c.end - 1e-6);
    const c = score.chords[ci >= 0 ? ci : b < 0 ? 0 : score.chords.length - 1], nx = score.chords[(ci >= 0 ? ci : 0) + 1];
    const key = chordName(c) + "|" + (nx ? chordName(nx) : "") + "|" + c.roman;
    if (key !== shown.chord) {
      $("chord").innerHTML = `${chordName(c)}<small>${c.roman}</small>`;
      $("then").innerHTML = nx ? `then <b>${chordName(nx)}</b>` : "";
      shown.chord = key;
    }
    // the words: the line being sung (or about to be), its syllables lit as they come
    const lines = score.lines;
    let li = -1;
    for (let i = 0; i < lines.length; i++) if (lines[i].start <= b + 1.5) li = i;
    if (li >= 0 && b > lines[li].end + 1.5 && (li + 1 >= lines.length || lines[li + 1].start > b + 1.5)) li = -1;
    const cur = li >= 0 ? lines[li] : null;
    const upcoming = lines[li + 1] || (li < 0 ? lines.find((l) => l.start > b) : null);
    const sylls = cur ? score.melody.filter((n) => n.lyric && n.start >= cur.start - 1e-6 && n.start < cur.end - 1e-6) : [];
    let si2 = -1;
    for (let i = 0; i < sylls.length; i++) if (sylls[i].start <= b + 1e-6) si2 = i;
    if (li !== shown.line || si2 !== shown.syl) {
      const now = $("now");
      if (!cur) now.innerHTML = "&nbsp;";
      else {
        now.innerHTML = "";
        sylls.forEach((n, i) => {
          const span = document.createElement("span");
          span.textContent = n.lyric.replace(/-$/, "") + (n.wordEnd ? " " : "");
          if (i < si2) span.className = "sung";
          else if (i === si2) span.className = "here";
          now.append(span);
        });
      }
      $("next").textContent = upcoming && upcoming !== cur ? upcoming.text : " ";
      shown.line = li; shown.syl = si2;
    }
  }

  // ------------------------------------------------------------------ every frame
  function frame() {
    if (score) {
      let b = beatNow();
      if (T.playing) {
        sweepMissed(b);
        if (!loopRange() && b >= songEnd + 2) { pause(); T.beat = songStart; b = songStart; }
      }
      paint(b);
      readouts(b);
      if (T.playing && b < T.songFrom - 1e-6) status(`count-in: ${Math.floor(b - T.countFrom) + 1}`);
      else if (T.waiting) {
        const left = [...T.need].filter((p) => !T.got.has(p)).map((p) => noteName(p, true));
        status(`waiting for ${left.join(" + ")}`, true);
      } else if (T.playing) {
        const loop = loopRange();
        status(loop ? `looping, time ${T.pass}` : "");
      } else status(T.beat > songStart ? "paused" : "");
    }
    requestAnimationFrame(frame);
  }

  // ------------------------------------------------------------------ controls
  function change(fn, how) { // how: "resync" (the playing must follow), "build" (the notes change)
    fn(); save();
    if (how === "build") { build(); layoutKeys(); }
    if (how === "resync" || how === "build") resync();
    ui.settings();
  }
  let scrubbing = false;
  $("play").addEventListener("click", () => (T.playing ? pause() : play()));
  $("restart").addEventListener("click", restart);
  $("back").addEventListener("click", () => stepBar(-1));
  $("fwd").addEventListener("click", () => stepBar(1));
  function stepBar(d) {
    const bpb = score.timeSignature[0], b = beatNow();
    const bar = Math.floor((b + 0.01) / bpb) + 1 + d;
    seek(barStart(clamp(bar, 1, score.bars)));
  }
  const scrub = $("scrub");
  scrub.addEventListener("pointerdown", () => { scrubbing = true; });
  scrub.addEventListener("input", () => { const bpb = score.timeSignature[0]; seek(Math.floor(+scrub.value / bpb) * bpb); });
  scrub.addEventListener("change", () => { scrubbing = false; });
  window.addEventListener("pointerup", () => { scrubbing = false; });

  $("speed").addEventListener("input", (e) => change(() => { set.speed = +e.target.value; }, "resync"));
  $("rit").addEventListener("change", (e) => change(() => { set.rit = e.target.checked; }, "resync"));
  const refit = () => { if (keyboard()) fitHands(); };
  const transpose = (d) => change(() => { set.transpose = clamp(set.transpose + d, -6, 6); refit(); }, "build");
  $("down").addEventListener("click", () => transpose(-1));
  $("up").addEventListener("click", () => transpose(1));
  $("home-key").addEventListener("click", () => change(() => { set.transpose = 0; refit(); }, "build"));
  $("kb").addEventListener("change", (e) => change(() => {
    set.kb = e.target.value;
    if (KEYBOARDS[set.kb]) set.kbLo = KEYBOARDS[set.kb][1];
    fitHands();
  }, "build"));
  const moveKb = (d) => change(() => { set.kbLo = clamp(set.kbLo + 12 * d, 12, 96); fitHands(); }, "build");
  $("kb-down").addEventListener("click", () => moveKb(-1));
  $("kb-up").addEventListener("click", () => moveKb(1));
  $("kb-learn").addEventListener("click", () => {
    learning = learning === null ? "low" : null;
    status(learning ? "Press your keyboard's lowest key." : "");
    ui.settings();
  });
  const nudge = (h, d) => change(() => { if (h === "R") set.octR = clamp(set.octR + d, -3, 3); else set.octL = clamp(set.octL + d, -3, 3); }, "build");
  $("oct-r-down").addEventListener("click", () => nudge("R", -1));
  $("oct-r-up").addEventListener("click", () => nudge("R", 1));
  $("oct-l-down").addEventListener("click", () => nudge("L", -1));
  $("oct-l-up").addEventListener("click", () => nudge("L", 1));
  $("fit").addEventListener("click", () => change(fitHands, "build"));
  $("anyoct").addEventListener("change", (e) => change(() => { set.anyOct = e.target.checked; }));
  const setHands = (v) => change(() => { set.hands = v; T.tally = { right: 0, missed: 0, wrong: 0 }; }, "build");
  for (const r of document.querySelectorAll("input[name=hands]")) r.addEventListener("change", () => setHands(r.value));
  for (const r of document.querySelectorAll("input[name=theme]")) r.addEventListener("change", () => change(() => { set.theme = r.value; }));
  $("leftpart").addEventListener("change", (e) => change(() => { set.leftpart = e.target.value; refit(); }, "build"));
  $("vol-right").addEventListener("input", (e) => change(() => { set.volRight = +e.target.value; set.muteRight = false; }));
  $("vol-left").addEventListener("input", (e) => change(() => { set.volLeft = +e.target.value; set.muteLeft = false; }));
  $("vol-right").addEventListener("change", () => resync());
  $("vol-left").addEventListener("change", () => resync());
  $("mute-right").addEventListener("click", () => change(() => { set.muteRight = !set.muteRight; }, "resync"));
  $("mute-left").addEventListener("click", () => change(() => { set.muteLeft = !set.muteLeft; }, "resync"));
  for (const id of ["along", "guide", "countin", "metro", "echo", "names"]) {
    $(id).addEventListener("change", (e) => change(() => { set[id] = e.target.checked; }, id === "along" || id === "guide" || id === "metro" ? "resync" : null));
  }
  $("wait").addEventListener("change", (e) => change(() => { set.wait = e.target.checked; }, "resync"));
  $("loopsel").addEventListener("change", (e) => change(() => {
    set.loop = e.target.value;
    if (set.loop !== "off") set.lastLoop = set.loop;
    const r = loopRange();
    if (r && !T.playing) T.beat = r[0];
  }, "resync"));
  const loopBars = () => change(() => {
    set.loopA = clamp(Math.round(+$("loop-a").value || 1), 1, score.bars);
    set.loopB = clamp(Math.round(+$("loop-b").value || set.loopA), 1, score.bars);
    set.loop = set.lastLoop = "custom";
  }, "resync");
  $("loop-a").addEventListener("change", loopBars);
  $("loop-b").addEventListener("change", loopBars);
  const hereBar = () => clamp(Math.floor((beatNow() + 0.01) / score.timeSignature[0]) + 1, 1, score.bars);
  $("set-a").addEventListener("click", () => { $("loop-a").value = hereBar(); if (+$("loop-b").value < hereBar()) $("loop-b").value = hereBar(); loopBars(); });
  $("set-b").addEventListener("click", () => { $("loop-b").value = hereBar(); if (+$("loop-a").value > hereBar()) $("loop-a").value = hereBar(); loopBars(); });
  $("midi-connect").addEventListener("click", () => connectMidi(false));
  $("midi-in").addEventListener("change", (e) => { set.midiIn = e.target.value; save(); devices(); });
  $("midi-out").addEventListener("change", (e) => { midiOutOff(); set.midiOut = e.target.value; save(); devices(); resync(); });

  // the computer's keys: a piano's row (A is C), and the shortcuts
  const ROW = { KeyA: 0, KeyW: 1, KeyS: 2, KeyE: 3, KeyD: 4, KeyF: 5, KeyT: 6, KeyG: 7, KeyY: 8, KeyH: 9, KeyU: 10, KeyJ: 11,
    KeyK: 12, KeyO: 13, KeyL: 14, KeyP: 15, Semicolon: 16, Quote: 17 };
  const typed = new Map(); // code -> pitch, so a key lifts the note it struck even after an octave change
  function typing(e) {
    const t = e.target;
    return t && (t.tagName === "SELECT" || t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && !["checkbox", "radio", "range", "button"].includes(t.type)));
  }
  // e.code names the key's place on the keyboard; some synthetic events leave it empty, so read e.key then
  const KEYS = { "[": "BracketLeft", "]": "BracketRight", ";": "Semicolon", "'": "Quote", " ": "Space" };
  function codeOf(e) {
    if (e.code) return e.code;
    const k = e.key || "";
    if (KEYS[k]) return KEYS[k];
    if (/^[a-z]$/i.test(k)) return "Key" + k.toUpperCase();
    if (/^[0-9]$/.test(k)) return "Digit" + k;
    return k;
  }
  window.addEventListener("keydown", (e) => {
    if (!score || e.metaKey || e.ctrlKey || e.altKey || typing(e)) return;
    const code = codeOf(e);
    if (code in ROW) {
      e.preventDefault();
      if (e.repeat || typed.has(code)) return;
      const p = 60 + 12 * set.octave + ROW[code];
      typed.set(code, p);
      noteOn(p, 0.75, "key");
      return;
    }
    const act = {
      Space: () => (T.playing ? pause() : play()),
      KeyR: restart, Home: restart,
      ArrowLeft: () => stepBar(-1), ArrowRight: () => stepBar(1),
      ArrowUp: () => change(() => { set.speed = clamp(set.speed + 5, 25, 125); }, "resync"),
      ArrowDown: () => change(() => { set.speed = clamp(set.speed - 5, 25, 125); }, "resync"),
      BracketLeft: () => transpose(-1), BracketRight: () => transpose(1),
      Digit1: () => setHands("right"), Digit2: () => setHands("left"), Digit3: () => setHands("both"), Digit0: () => setHands("none"),
      KeyN: () => change(() => { set.wait = !set.wait; }, "resync"),
      KeyM: () => change(() => { set.metro = !set.metro; }, "resync"),
      KeyC: () => change(() => { set.countin = !set.countin; }),
      KeyB: () => change(() => { set.loop = set.loop === "off" ? (set.lastLoop || "custom") : "off"; }, "resync"),
      KeyZ: () => change(() => { set.octave = clamp(set.octave - 1, -3, 3); status(`computer keys: from C${4 + set.octave}`); }),
      KeyX: () => change(() => { set.octave = clamp(set.octave + 1, -3, 3); status(`computer keys: from C${4 + set.octave}`); }),
    }[code];
    if (act) {
      e.preventDefault();
      if (e.repeat && !code.startsWith("Arrow")) return;
      if (e.target && e.target.blur && e.target !== document.body && code === "Space") e.target.blur();
      act();
    }
  });
  window.addEventListener("keyup", (e) => {
    const code = codeOf(e);
    if (typed.has(code)) { noteOff(typed.get(code), "key"); typed.delete(code); }
  });
  window.addEventListener("blur", () => { for (const [code, p] of typed) noteOff(p, "key"); typed.clear(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) pause(); });
  document.addEventListener("pointerdown", () => S.start(), { once: true });
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  if (media && media.addEventListener) media.addEventListener("change", () => { colours(); draw(); });

  // ------------------------------------------------------------------ start
  // Which score: score.json beside the page, or the one ?score= names (a path on this site, beside the page)
  function scoreUrl() {
    let asked = null;
    try { asked = new URLSearchParams(location.search).get("score"); } catch (e) { /* no query */ }
    return asked && /^[A-Za-z0-9][A-Za-z0-9._/-]*\.json$/.test(asked) && !asked.includes("..") && !asked.includes("//")
      ? asked : "score.json";
  }
  const studioScore = () => !!(score && score.source && score.source.kind === "studio");

  async function init() {
    try {
      // device/KEY.json: a score the studio on the visitor's device made, kept in this browser (web/studio-wasm/device.js)
      const kept = /^device\/([0-9a-f]{16,64})\.json$/.exec(scoreUrl());
      if (kept) {
        const text = localStorage.getItem("songbird-piano-score:" + kept[1]);
        if (!text) throw new Error("not kept");
        score = JSON.parse(text);
      } else {
        const res = await fetch(scoreUrl(), { cache: "no-cache" });
        if (!res.ok) throw new Error(res.status + " " + res.statusText);
        score = await res.json();
      }
    } catch (e) {
      $("lead").textContent = scoreUrl() !== "score.json"
        ? "This version's score isn't here any more (the studio keeps what it makes for a while). Open it again from the studio with Learn it at the piano."
        : "The score (score.json) didn't load: " + e.message + ". Make it with `uv run python tools/piano_score.py`, and serve this folder over http.";
      if (scoreUrl() !== "score.json") $("back-to-studio").hidden = false;
      return;
    }
    SPB = 60 / score.tempo;
    if (!score.left[set.leftpart]) set.leftpart = "fifths";
    // a score in another key than the settings were made for (the studio's version after a key change): the
    // page's own key change starts again from the song's, and the hands are fitted to the keyboard again
    if (set.madeFor !== score.key.tonicMidi) {
      if (set.madeFor) { set.transpose = 0; if (keyboard()) fitHands(); }
      set.madeFor = score.key.tonicMidi;
      save();
    }
    const sel = $("leftpart");
    for (const [k, v] of Object.entries(score.left)) sel.append(new Option(v.label, k));
    const loops = $("loopsel");
    score.sections.forEach((s, i) => loops.append(new Option(`${sectionLabel(i)} (bars ${s.bars[0]}–${s.bars[1]})`, String(i))));
    loops.append(new Option("bars, from A to B (below)", "custom"));
    if (![...loops.options].some((o) => o.value === set.loop)) set.loop = "off";
    $("title").textContent = score.title;
    document.title = `${score.title}, at the piano`;
    $("scrub").min = String(0); $("scrub").max = String(score.end);
    $("loop-a").max = $("loop-b").max = String(score.bars);
    const form = [];
    for (const s of score.sections) if (form[form.length - 1] !== s.name) form.push(s.name);
    $("lead").textContent = `${studioScore() ? "Your version from the studio" : "The released version"}, note for note: ` +
      `in ${score.key.tonic} ${score.key.mode}, ` +
      `${score.timeSignature[0]}/${score.timeSignature[1]} at ${Math.round(score.tempo)} to the quarter, ${score.bars} bars ` +
      `(${form.join(", ")}). The right hand plays the tune, the left an accompaniment made from the band's chords. ` +
      `Slow it down, move it to a key that suits you, loop the hard bars.`;
    if (studioScore()) { // opened from the studio: what this is, said plainly, and the way back
      $("back-to-studio").hidden = false;
      const about = document.createElement("p");
      about.textContent = "This is the version on the studio's page when you opened it here: its key, tempo, chords, " +
        "words, form and tune, your changes among them. Change something in the studio and press Learn it at the piano " +
        "again for the new one. The tune is as written, not as the singer phrases it; where nobody sings, it's the " +
        "instrument playing it, written at the sung pitch." +
        (score.lift ? " The last refrain goes up a whole step, as this style sings it." : "") +
        ' The last phrase slows as it\'s sung (uncheck "slow down at the end" to keep time).';
      $("about").replaceChildren(about);
    } else {
      $("about").innerHTML = `<p>The score was laid again from the released file itself (<code>${score.source.file}</code>, ` +
        `id ${String(score.source.id).slice(0, 12)}) with the program it carries, by <code>${score.source.exporter}</code>; ` +
        `see docs/PIANO.md. The intro's tune is the whistle's and the turns' the fiddle's and the lute's, all an octave ` +
        `above where they're written here. The last phrase slows as it's sung (uncheck "slow down at the end" to keep time).</p>`;
    }
    build();
    T.beat = songStart;
    colours();
    ui.settings();
    ui.playing();
    new ResizeObserver(resize).observe(canvas);
    resize();
    requestAnimationFrame(frame);
    try { // a keyboard already allowed: connect without asking
      if (navigator.permissions && navigator.requestMIDIAccess) {
        const perm = await navigator.permissions.query({ name: "midi", sysex: false });
        if (perm.state === "granted") connectMidi(true);
      }
    } catch (e) { /* the browser doesn't say: wait for Connect */ }
    if (!navigator.requestMIDIAccess) {
      $("midi-connect").disabled = true;
      midiNote("This browser has no Web MIDI (Chrome, Edge and Firefox have it; Safari doesn't). Click or touch the keys on the screen, or play the computer's keys (A W S E D ... K is the next C; Z and X move them an octave).");
    }
  }

  // for testing from a console: the state, and notes as if played
  window.pianoPage = { T, set, get notes() { return notes; }, get keys() { return keys; }, kbH, noteOn, noteOff, play, pause, seek, beatNow };
  init();
})();
