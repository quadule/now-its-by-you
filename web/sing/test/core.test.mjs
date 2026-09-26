// The sing-along core shared by the karaoke and this page (tools/karaoke.js): how a take is cut,
// synced and written, and how a guide that came through an MP3 decoder is put back in time.
// npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CLICKS, assemble, autoSync, decodeOffset, envelope, firstFrame, pitchAt, shifted, tapLags, wavBytes, yin,
} from "../../../tools/karaoke.js";

const RATE = 48000;

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

test("the singer's pitch, and none when there's only quiet", () => {
  const n = 2048;
  const tone = Float32Array.from({ length: n }, (_, i) => 0.3 * Math.sin(2 * Math.PI * 220 * i / RATE));
  assert.ok(Math.abs(yin(tone, RATE) - 220) < 1);
  assert.ok(Math.abs(pitchAt(tone, RATE) - 57) < 0.05); // A3
  assert.equal(pitchAt(new Float32Array(n), RATE), null);
});
