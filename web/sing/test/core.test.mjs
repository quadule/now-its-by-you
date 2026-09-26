// The sing-along core shared by the karaoke and this page (tools/karaoke.js): how a take is cut,
// synced and written, and how a guide that came through an MP3 decoder is put back in time.
// npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CLICKS, TAIL, assemble, autoSync, autoSyncWindow, closingTime, countIn, cutTake, decodeOffset, envelope, firstFrame, firstWords,
  inWindow, keyLabel, moment, nearestSpec, parseSpec, pitchAt, reelLines, restAt, sectionLabel, shifted, slug, specId, specText,
  speedLabel, sungSections, tapLags, wavBytes, yin,
} from "../../../tools/karaoke.js";

const RATE = 48000;

// a song's words as the lyrics JSON gives them (tools/karaoke.py lyrics(), per version): 96 bpm,
// an intro, a verse of two lines, a turn, a refrain of one line, a turn and a second verse
const BEAT = 0.625;
const beats = Array.from({ length: 80 }, (_, k) => 0.3 + BEAT * k);
function line(section, start, words) {
  const syllables = words.split(" ").map((text, k) => ({ text, start: start + BEAT * k, end: start + BEAT * k + 0.5, pitch: 60 + k, word_end: true }));
  return { section, start, end: syllables[syllables.length - 1].end, syllables };
}
const LYRICS = {
  title: "Test", tempo: 96, duration: 49.0, beats,
  lines: [line("verse", 5.3, "They saved it as numbers"), line("verse", 10.3, "a flicker of light"),
          line("refrain", 20.3, "Who made this song? Nobody knows."), line("verse", 35.3, "The whole world was watching")],
  sections: [
    { index: 0, name: "intro", start: 0.3, end: 5.3, sung: false },
    { index: 1, name: "verse", start: 5.3, end: 15.3, sung: true, nth: 1, label: "They saved it as numbers and sent it by wire,", window: [0.3, 14.3] },
    { index: 2, name: "turn", start: 15.3, end: 20.3, sung: false },
    { index: 3, name: "refrain", start: 20.3, end: 25.3, sung: true, nth: 1, label: "Who made this song? Nobody knows.", window: [15.3, 24.93] },
    { index: 4, name: "turn", start: 25.3, end: 30.3, sung: false },
    { index: 5, name: "verse", start: 35.3, end: 45.3, sung: true, nth: 2, label: "The whole world was watching it all in a day,", window: [30.3, 39.93] },
  ],
  guide: "abcdefabcdef", spec: { id: "a.k0.t100", set: "a", key: 0, tempo: 100 },
};

test("a take starts on the frame the guide reached the ears, plus the way back in", () => {
  // the guide started at t0 = 2 s on the context clock; 30 ms out, 10 ms in, 20 ms more unsaid
  const first = firstFrame(2.0, 0.03, 0.01, 0.02, RATE);
  assert.equal(first, Math.round(2.06 * RATE));
  const chunks = [];
  for (let f = first - 5000; f < first + 20000; f += 2048) {
    chunks.push({ frame: f, samples: Float32Array.from({ length: 2048 }, (_, i) => (f + i) % 1000 / 1000) });
  }
  chunks.splice(3, 1); // a block the device dropped
  const take = assemble(chunks, first);
  const at = f => Math.fround((f % 1000) / 1000); // what the recorder's frame f held
  assert.equal(take[0], at(first)); // the first sample is the recorder's frame `first`
  assert.equal(take[1000], at(first + 1000));
  const gap = chunks[3].frame - 2048 - first; // where the dropped block was: silence, and nothing moved
  assert.equal(take[gap + 10], 0);
  assert.equal(take[gap + 2048 + 10], at(first + gap + 2048 + 10));
});

test("a take slides earlier by dropping its start, later by silence in front", () => {
  const x = Float32Array.from({ length: 100 }, (_, i) => i);
  assert.equal(shifted(x, 1000, 0.01)[0], 10);
  const later = shifted(x, 1000, -0.01);
  assert.equal(later.length, 110);
  assert.equal(later[9], 0);
  assert.equal(later[10], 0);
  assert.equal(later[11], 1);
});

test("the WAV is 16-bit mono PCM at the device's rate", () => {
  const buf = wavBytes(Float32Array.from([0, 0.5, -0.5, 1, -1, 2]), 44100);
  const v = new DataView(buf);
  assert.equal(buf.byteLength, 44 + 12);
  assert.equal(v.getUint32(24, true), 44100);
  assert.equal(v.getUint16(22, true), 1);
  assert.equal(v.getUint16(34, true), 16);
  assert.deepEqual([0, 1, 2, 3, 4, 5].map(i => v.getInt16(44 + 2 * i, true)), [0, 16384, -16383, 32767, -32767, 32767]);
});

test("auto-sync finds how late a take runs against the song", () => {
  const notes = [];
  for (let k = 0; k < 40; k++) notes.push({ start: 10 + 0.5 * k, end: 10 + 0.5 * k + 0.45, pitch: 60 + (k % 5) });
  for (const lag of [0.0, 0.08, 0.25, -0.1]) {
    const trail = [];
    for (let t = 9; t < 31; t += 1 / 60) {
      const n = notes.find(n => t - lag >= n.start && t - lag < n.end);
      trail.push({ t, m: n ? n.pitch - 12 : null }); // sung an octave down
    }
    assert.ok(Math.abs(autoSync(trail, notes) - (Math.abs(lag) >= 0.01 ? lag : 0)) <= 0.025, `lag ${lag}`);
  }
  assert.equal(autoSync([{ t: 1, m: 60 }], notes), 0); // too little sung to tell
});

function guideLike(rate, seconds = 3) {
  // silence, then tones and clicks from 0.6 s, as a guide's opening sounds
  const x = new Float32Array(Math.round(rate * seconds));
  for (let k = 0; k < 8; k++) {
    const a = Math.round((0.6 + 0.3 * k) * rate);
    for (let i = 0; i < 0.25 * rate; i++) x[a + i] += 0.3 * Math.sin(2 * Math.PI * (220 + 30 * k) * i / rate) * Math.exp(-i / (0.1 * rate));
  }
  return x;
}

test("a decoder's silence in front of the guide is found and measured", () => {
  const original = guideLike(44100);
  const reference = Array.from(envelope(original, 44100, 2.5));
  for (const rate of [44100, 48000]) {
    const at = guideLike(rate);
    assert.equal(decodeOffset(at, rate, reference), 0); // a decoder that honours the encoder's delay
    const late = new Float32Array(at.length + 2257);
    late.set(at, Math.round(1105 * rate / 44100)); // one that doesn't: LAME's 1105 samples of delay
    assert.ok(Math.abs(decodeOffset(late, rate, reference) - 1105 / 44100) < 0.0005, `at ${rate}`);
  }
  assert.equal(decodeOffset(new Float32Array(48000 * 3).map(() => Math.random() - 0.5), 48000, reference), 0); // no match: trust it
});

test("a calibration hears the taps after the count-in", () => {
  const when = 1.0, lag = 0.07, chunks = [];
  const total = Math.round((when + CLICKS.count * CLICKS.beat + 1) * RATE);
  const x = new Float32Array(total).map(() => (Math.random() - 0.5) * 0.002);
  for (let k = 0; k < CLICKS.count; k++) {
    const a = Math.round((when + k * CLICKS.beat + lag) * RATE);
    for (let i = 0; i < 0.03 * RATE; i++) x[a + i] += 0.5 * Math.exp(-i / (0.005 * RATE)) * (i % 2 ? 1 : -1);
  }
  for (let f = 0; f < total; f += 2048) chunks.push({ frame: f, samples: x.slice(f, f + 2048) });
  const lags = tapLags(chunks, RATE, when);
  assert.equal(lags.length, CLICKS.count - CLICKS.lead);
  assert.ok(lags.every(l => Math.abs(l - lag) < 0.006));
});

test("a line is counted in on the beats the pulse plays, not between them", () => {
  const beats = Array.from({ length: 11 }, (_, k) => 0.5 * k); // 120 bpm
  assert.deepEqual(countIn(beats, 3.75, 120), [2.0, 2.5, 3.0, 3.5]); // a pickup: in on the "and" of four
  assert.deepEqual(countIn(beats, 4.003, 120), [2.0, 2.5, 3.0, 3.5]); // on the downbeat, a hair late: that beat is the entry
  assert.deepEqual(countIn(beats, 0.8, 120), [-Infinity, -Infinity, 0.0, 0.5]); // too early for four: the rest lit at once
  assert.deepEqual(countIn([], 3.75, 120), [1.75, 2.25, 2.75, 3.25]); // words from before the beats: the tempo
});

test("the singer's pitch, and none when there's only quiet", () => {
  const n = 2048;
  const tone = Float32Array.from({ length: n }, (_, i) => 0.3 * Math.sin(2 * Math.PI * 220 * i / RATE));
  assert.ok(Math.abs(yin(tone, RATE) - 220) < 1);
  assert.ok(Math.abs(pitchAt(tone, RATE) - 57) < 0.05); // A3
  assert.equal(pitchAt(new Float32Array(n), RATE), null);
});

test("a version's id and its words: the set, how many steps lower or higher, how much slower", () => {
  assert.equal(specId({ set: "a", key: -2, tempo: 90 }), "a.k-2.t90");
  assert.deepEqual(parseSpec("b.k2.t80"), { id: "b.k2.t80", set: "b", key: 2, tempo: 80 });
  for (const bad of ["a.k+2.t90", "A.k0.t100", "a.k0", "../a.k0.t100", "", null]) assert.equal(parseSpec(bad), null, String(bad));
  assert.deepEqual([-4, -2, -1, 0, 2].map(keyLabel), ["4 steps lower", "2 steps lower", "1 step lower", "as written", "2 steps higher"]);
  assert.deepEqual([100, 90, 80].map(speedLabel), ["as written", "a little slower", "slower"]);
  assert.equal(specText("a.k-2.t90", [{ id: "a", name: "Set A" }]), "Set A, 2 steps lower, a little slower");
  assert.equal(specText("song.k0.t100"), ""); // the song's own words, as written: nothing to say
  assert.equal(specText("b.k0.t80"), "Set B, slower");
});

test("a version not on offer gives way to the nearest that keeps what was just chosen", () => {
  const offered = ["a.k0.t100", "a.k-2.t100", "a.k-2.t90", "b.k0.t100"];
  assert.equal(nearestSpec(offered, { set: "a", key: -2, tempo: 90 }, "key"), "a.k-2.t90"); // on offer: itself
  assert.equal(nearestSpec(offered, { set: "a", key: 0, tempo: 80 }, "tempo"), "a.k0.t100"); // no 80 at all: the nearest
  assert.equal(nearestSpec(offered, { set: "b", key: -2, tempo: 90 }, "set"), "b.k0.t100"); // the set chosen, as near as it goes
  assert.equal(nearestSpec(offered, { set: "a", key: -4, tempo: 90 }, "key"), "a.k-2.t90");
  assert.equal(nearestSpec([], { set: "a", key: 0, tempo: 100 }), null);
});

test("the sections a singer can sing alone, with their windows and their names as a singer says them", () => {
  const sung = sungSections(LYRICS);
  assert.deepEqual(sung.map(s => [s.index, s.title, s.from, s.to]),
                   [[1, "Verse 1", 0.3, 14.3], [3, "Refrain", 15.3, 24.93], [5, "Verse 2", 30.3, 39.93]]); // one refrain: no number
  assert.equal(sectionLabel(sung[0]), "Verse 1 · They saved it as numbers…");
  assert.equal(sectionLabel(sung[1]), "Refrain · Who made this song?");
  assert.deepEqual(sungSections({ lines: [], sections: [{ name: "verse", start: 0, end: 9 }] }), []); // the old words: whole songs only
  assert.equal(firstWords("a flicker of light, and as quick as a fire."), "a flicker of light…");
  assert.equal(firstWords("Each copy was perfect in every last part,"), "Each copy was perfect…"); // never ending on "in"
  assert.equal(firstWords("Nobody knows,"), "Nobody knows");
});

test("a section's notes are those starting in its window, and the lane waits a second before the first", () => {
  const notes = LYRICS.lines.flatMap(l => l.syllables);
  const refrain = inWindow(notes, 15.3, 24.93);
  assert.deepEqual(refrain.map(n => n.text), ["Who", "made", "this", "song?", "Nobody", "knows."]);
  assert.equal(inWindow(notes).length, notes.length); // the whole song: every note
  assert.equal(restAt(notes, 15.3), 20.3 - 1.0);
  assert.equal(restAt(notes), 5.3 - 1.0); // as the whole song always rested
});

test("a section's reel holds only its own lines, counted in from where playback starts", () => {
  const whole = reelLines(LYRICS);
  assert.equal(whole.length, 4);
  assert.equal(whole[0].gapStart, 0); // the whole song, as always: the first line's rest runs from 0
  assert.equal(whole[1].gapStart, whole[0].line.end);
  const verse2 = reelLines(LYRICS, { from: 30.3, to: 39.93, name: "verse" });
  assert.deepEqual(verse2.map(r => r.line.start), [35.3]);
  assert.equal(verse2[0].before, null);
  assert.equal(verse2[0].gapStart, 30.3); // its lead-in bar fills from the window's start, not from the last verse
  assert.ok(Math.abs(verse2[0].gap - 5.0) < 1e-9);
  assert.deepEqual(verse2[0].count, beats.filter(t => t < 35.3 - 0.05).slice(-4)); // the four beats before it
  // a line of another kind starting inside the window (a pickup into what comes next) isn't this section's
  assert.deepEqual(reelLines(LYRICS, { from: 0.3, to: 21, name: "verse" }).map(r => r.line.section), ["verse", "verse"]);
});

test("a one-section take starts at its window: its first sample is the guide at `from`", () => {
  // the guide's time 0 was at t0 = 2 s on the context clock (so playback began at t0 + from);
  // 30 ms out, 10 ms in, 20 ms more unsaid
  const t0 = 2.0, from = 15.3, to = 24.93;
  const first = firstFrame(t0, 0.03, 0.01, 0.02, RATE, from);
  assert.equal(first, Math.round((2.0 + 15.3 + 0.06) * RATE));
  assert.equal(firstFrame(t0, 0.03, 0.01, 0.02, RATE, 0), firstFrame(t0, 0.03, 0.01, 0.02, RATE)); // a whole take, as before
  const at = f => Math.fround((f % 1000) / 1000);
  const chunks = [];
  for (let f = Math.round((t0 + from) * RATE) - 4096; f < Math.round((t0 + to + 3) * RATE); f += 2048) {
    chunks.push({ frame: f, samples: Float32Array.from({ length: 2048 }, (_, i) => ((f + i) % 1000) / 1000) });
  }
  const take = cutTake(chunks, first, RATE, to - from + TAIL);
  assert.equal(take[0], at(first)); // sample 0 is guide time `from`, heard and sung back
  assert.equal(take[RATE], at(first + RATE));
  assert.equal(take.length, Math.round((to - from + TAIL) * RATE)); // stopped late, it still holds only its window and the tail
  assert.equal(cutTake(chunks, first, RATE).length, assemble(chunks, first).length); // a whole take isn't cut short
});

test("auto-sync for one section listens only to that section's notes", () => {
  const notes = [];
  for (let k = 0; k < 40; k++) notes.push({ start: 10 + 0.5 * k, end: 10 + 0.5 * k + 0.45, pitch: 60 + (k % 5) });
  const from = 18, to = 26; // notes 16 to 31
  for (const lag of [0.0, 0.08, 0.2]) {
    const trail = [];
    for (let t = from; t < to + 0.5; t += 1 / 60) {
      const n = notes.find(n => t - lag >= n.start && t - lag < n.end && n.start >= from && n.start < to);
      trail.push({ t, m: n ? n.pitch + 12 : null }); // sung an octave up
    }
    const found = autoSyncWindow(trail, notes, from, to);
    assert.ok(Math.abs(found - (Math.abs(lag) >= 0.01 ? lag : 0)) <= 0.025, `lag ${lag}: ${found}`);
    assert.equal(found, autoSync(trail, inWindow(notes, from, to)));
  }
  const whole = [];
  for (let t = 9; t < 31; t += 1 / 60) {
    const n = notes.find(n => t - 0.1 >= n.start && t - 0.1 < n.end);
    whole.push({ t, m: n ? n.pitch : null });
  }
  assert.equal(autoSyncWindow(whole, notes), autoSync(whole, notes)); // the whole song's window: as before
});

test("names go where the karaoke keeps them, as tools/takes.py slug() does", () => {
  assert.equal(slug("Zoë Ann"), "zoe-ann");
  assert.equal(slug("  Ana María "), "ana-maria");
  assert.equal(slug("Jo_Jo!"), "jo-jo");
  assert.equal(slug("李 小龙"), "李-小龙");
  assert.equal(slug("__"), "someone");
});

test("when singing closes, on the artist's clock and the singer's", () => {
  const closes = "2026-09-27T22:00:00-07:00";
  assert.equal(moment(closes, "America/Los_Angeles"), "Sunday 27 September at 10 PM");
  assert.equal(closingTime(closes, "America/Los_Angeles"), "Sunday 27 September at 10 PM Pacific");
  assert.equal(closingTime(closes, "America/Vancouver"), "Sunday 27 September at 10 PM Pacific"); // the same clock: said once
  assert.equal(closingTime(closes, "Europe/Lisbon"), "Sunday 27 September at 10 PM Pacific (Monday 28 September at 6 AM your time)");
  assert.equal(closingTime(closes, "Asia/Kolkata"), "Sunday 27 September at 10 PM Pacific (Monday 28 September at 10:30 AM your time)");
  assert.equal(closingTime(undefined), "");
});
