/* Run with: node --test tests/studio_perform.test.cjs
 * Notes in, the page's side (songbird/studio/perform.js): a take's timing, its capture from MIDI messages and its
 * quantizing, the lines it covers and what it plays along with, and a preview applied as one undoable step. Web
 * MIDI can't be played into here, so the events are synthetic: what a keyboard sends, at the moments it sends. */
"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const applied = [];
global.window = { StudioBridge: { setEdits: (patch, label) => { applied.push({ patch, label }); return true; }, toast: () => {} } };
const P = require("../songbird/studio/perform.js");

test("a key's moment is the beat that was heard then", () => {
  // the take's beat 7.5 sounds at audio time 10.0; a beat is half a second; the audio comes out 20 ms late
  const clock = { origin: 7.5, started: 10.0, secondsPerBeat: 0.5, latency: 0.02, ctxNow: 12.0, perfNow: 50000 };
  // pressed 980 ms before performance.now() was read with the audio clock at 12.0: audio time 11.02, heard 11.00
  assert.equal(P.beatOf(49020, clock), 7.5 + 2);
  assert.equal(P.beatOf(50000, { ...clock, latency: 0 }), 7.5 + 4);
});

test("notes are paired as a keyboard sends them", () => {
  const c = new P.Capture();
  c.message([0x90, 60, 100], 1.0);
  c.message([0x90, 64, 80], 1.5);
  c.message([0x90, 60, 90], 2.0);  // the same key struck again before it was let go
  c.message([0x80, 60, 0], 2.5);  // ends the earliest
  c.message([0x90, 64, 0], 3.0);  // a note-on at velocity 0 is a note-off
  c.message([0xb0, 64, 127], 3.1);  // a pedal: not a note
  c.message([0x80, 62, 0], 3.2);  // let go of a key never struck: nothing
  c.message([0x91, 67, 70], 3.5);  // another channel, still held when the take ends
  assert.deepEqual(c.finish(4.0), [[1.0, 1.5, 60, 100], [1.5, 1.5, 64, 80], [2.0, 2.0, 60, 90], [3.5, 0.5, 67, 70]]);
});

test("timing is kept as played, or tidied to the grid from a bar line", () => {
  const played = [[0.52, 0.47, 60, 90], [0.98, 0.2, 62, 90], [1.9, 1.07, 64, 90]];
  assert.deepEqual(P.quantize(played, 0), played);
  assert.deepEqual(P.quantize(played, 0.5, 0.5), [[0.5, 0.5, 60, 90], [1.0, 0.5, 62, 90], [2.0, 1.0, 64, 90]]);
  assert.deepEqual(P.quantize([[0.4, 0.3, 60, 90]], 0.25, 0.5), [[0.5, 0.25, 60, 90]]);
  const triplets = P.quantize([[1.3, 0.3, 60, 90], [1.7, 0.4, 62, 90]], 1 / 3, 0);
  assert.ok(Math.abs(triplets[0][0] - 4 / 3) < 1e-9 && Math.abs(triplets[1][0] - 5 / 3) < 1e-9);
});

const composition = {
  tempo: 120, beats_per_bar: 4,
  sections: [
    { label: "Verse 1", phrases: [
      { part_key: "verse:0.0", start_beat: 0.5, duration_beats: 8, pickup_beats: 0.5,
        notes: [{ onset: -0.5, duration: 0.5, pitch: 62 }, { onset: 0, duration: 2, pitch: 66 }],
        harmony: [{ start: 0, beats: 4, pcs: [2, 6, 9] }, { start: 4, beats: 4, pcs: [7, 11, 2] }] },
      { part_key: "verse:0.1", start_beat: 8.5, duration_beats: 8, pickup_beats: 0.5, notes: [{ onset: 0, duration: 4, pitch: 69 }],
        harmony: [{ start: 0, beats: 8, pcs: [9, 1, 4] }] }] },
    { label: "Refrain 1", phrases: [
      { part_key: "refrain:0.0", start_beat: 16.5, duration_beats: 8, pickup_beats: 0, notes: [], harmony: [] }] },
  ],
};

test("a take covers the whole song, a section, or a line of it", () => {
  assert.deepEqual(P.linesFor(composition, "song", "all").map((l) => l.key), ["verse:0.0", "verse:0.1", "refrain:0.0"]);
  assert.deepEqual(P.linesFor(composition, "0", "all").map((l) => l.key), ["verse:0.0", "verse:0.1"]);
  assert.deepEqual(P.linesFor(composition, "0", "1").map((l) => l.key), ["verse:0.1"]);
  assert.deepEqual(P.linesFor(composition, "5", "all"), []);
});

test("it plays along with the tune and chords after a bar's count-in; the tune leaves room when it's the tune played", () => {
  const lines = P.linesFor(composition, "0", "all");
  const band = P.backingFor(composition, lines, "fiddle");
  assert.equal(band.origin, 0.5 - 4);  // a bar of clicks before the first bar line
  assert.equal(band.end, 16.5);
  assert.deepEqual(band.tune.map((n) => [n.beat, n.pitch]), [[0, 62], [0.5, 66], [8.5, 69]]);  // the pickup too
  assert.deepEqual(band.chords.map((c) => c.beat), [0.5, 4.5, 8.5]);
  // the clicks on the bars' beats (the bar lines here fall half a beat in, after the pickup), the downbeats marked
  assert.deepEqual(band.clicks.slice(0, 5).map((c) => [c.beat, c.down]), [[-3.5, true], [-2.5, false], [-1.5, false], [-0.5, false], [0.5, true]]);
  assert.equal(band.clicks.length, 20);
  assert.deepEqual(P.backingFor(composition, lines, "voice").tune, []);
});

test("a preview is applied as one undoable step, with what it changes", () => {
  const preview = { changes: [
    { path: "part.fiddle.verse:0.0", value: [[0, 96, 7, 90]], where: "Verse 1, line 1", what: "the fiddle: 1 note" },
    { path: "part.fiddle.verse:0.1", value: [], where: "Verse 1, line 2", what: "the fiddle rests" }], refused: [], said: [] };
  assert.deepEqual(P.patchOf(preview), { "part.fiddle.verse:0.0": [[0, 96, 7, 90]], "part.fiddle.verse:0.1": [] });
  P.state.take = { player: "fiddle" };
  P.show(preview, "take");
  P.apply();
  assert.equal(applied.length, 1);
  assert.deepEqual(applied[0].patch, P.patchOf(preview));
  assert.equal(applied[0].label, "Play the fiddle in");
  assert.equal(P.state.preview, null);
  P.show({ changes: [], refused: [{ where: "Verse 1, line 1 (Voice)", why: "the line needs 11 notes" }], said: [] }, "file");
  P.apply();  // nothing to apply: nothing changes
  assert.equal(applied.length, 1);
});
