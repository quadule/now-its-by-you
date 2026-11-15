"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm"), fs = require("node:fs"), path = require("node:path");
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../songbird/studio/parts.js"), "utf8"), { window });
const { limits, normalize } = window.SongbirdParts.core;
const clone = (x) => JSON.parse(JSON.stringify(x));

test("instrument bounds use the seed key for portable relative pitches", () => {
  const b = limits({ tonic: 65, part_seed_tonic: 62 }, { pickup_beats: 0.5, duration_beats: 8 }, { low: 48, high: 84 });
  assert.deepEqual(clone(b), { low: -19, high: 27, start: -48, end: 768 });
});
test("monophonic parts trim overlaps and reject simultaneous different notes", () => {
  const b = { low: -24, high: 24, start: -48, end: 768 };
  const notes = [[96, 192, 7, 100], [0, 192, 0, 90]];
  assert.deepEqual(clone(normalize(notes, { poly: false }, b)), [[0, 96, 0, 90], [96, 192, 7, 100]]);
  assert.equal(notes[1][1], 192, "the source stays intact");
  assert.throws(() => normalize([[0, 96, 0, 90], [0, 96, 7, 90]], { poly: false }, b), /one note at a time/);
  assert.deepEqual(clone(normalize([], { poly: false }, b)), []);
});
test("polyphonic parts preserve chords, velocities and rests within the renderer's limits", () => {
  const b = { low: -24, high: 24, start: -48, end: 768 }, player = { poly: true };
  assert.deepEqual(clone(normalize([[0, 96, 0, 50], [0, 96, 4, 120], [0, 96, 0, 50]], player, b)), [[0, 96, 0, 50], [0, 96, 4, 120]]);
  assert.throws(() => normalize(Array.from({ length: 11 }, (_, i) => [0, 96, i, 90]), player, b), /ten notes/);
  assert.throws(() => normalize([[0, 96, NaN, 90]], player, b), /inside/);
  assert.throws(() => normalize([[768, 96, 0, 90]], player, b), /inside/);
});
test("several instrument notes at once: moved together inside the phrase, copied, pasted beside the others and put on the grid", () => {
  const { shifted, clipOf, pasted, quantized } = window.SongbirdParts.core;
  const b = { low: -12, high: 12, start: -48, end: 384 };
  const notes = [[0, 96, 0, 90], [96, 48, 4, 90], [200, 40, 7, 80]];
  assert.deepEqual(clone(shifted(notes, [1, 2], 500, 2, b)), [[0, 96, 0, 90], [279, 48, 6, 90], [383, 40, 9, 80]], "held at the phrase's end");
  assert.deepEqual(clone(shifted(notes, [0, 2], -100, 20, b)), [[-48, 96, 5, 90], [96, 48, 4, 90], [152, 40, 12, 80]], "and its pickup and the range");
  const clip = clipOf(notes, [1, 2]);
  assert.deepEqual(clone(clip), { start: 96, notes: [[0, 48, 4, 90], [104, 40, 7, 80]] });
  assert.deepEqual(clone(pasted(notes, clip, 192, b).put), [[192, 48, 4, 90], [296, 40, 7, 80]]);
  assert.throws(() => pasted(notes, clip, 300, b), /don't fit here/);
  assert.deepEqual(clone(pasted(notes, clip, 0, b, true).notes), [[200, 40, 7, 80], [0, 48, 4, 90], [104, 40, 7, 80]], "one note at a time: in place of what they overlap");
  assert.deepEqual(clone(quantized(notes, [2], 48, b)), [[0, 96, 0, 90], [96, 48, 4, 90], [192, 48, 7, 80]]);
  assert.equal(notes[2][0], 200, "the source stays intact");
});
