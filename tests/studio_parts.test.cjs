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
