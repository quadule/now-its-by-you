/* Run with: node --test tests/studio_players.test.cjs
 * The sketch's players on a musician's own instruments (songbird/studio/players.js): when each note goes out,
 * that every note-on gets its note-off (at the end, at a stop, at a loop's turn, when a key sounds again), the
 * program changes, the fallbacks without Web MIDI or without an output, and Panic. No browser: small doubles. */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../songbird/studio/players.js"), "utf8");
const same = (actual, expected, message) => assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected, message); // across the sandbox

function load({ navigator = {}, storage = {} } = {}) {
  const intervals = [];
  const document = { readyState: "complete", querySelector: () => null, getElementById: () => null, addEventListener() {} };
  const window = { addEventListener() {} };
  const localStorage = { getItem: (k) => storage[k] ?? null, setItem: (k, v) => { storage[k] = v; } };
  let clock = 1000;
  const performance = { now: () => clock };
  vm.runInNewContext(source, { window, document, navigator, localStorage, performance, console,
    setInterval: (fn) => { intervals.push(fn); return intervals.length; }, clearInterval: (id) => { intervals[id - 1] = null; },
    fetch: async () => { throw new Error("no server here"); } });
  return { P: window.SongbirdPlayers, core: window.SongbirdPlayers._core, intervals, storage, setClock: (t) => { clock = t; } };
}

function output() {
  const sent = [];
  return { sent, id: "out", name: "Out", send(bytes, when) { sent.push({ bytes: [...bytes], when }); } };
}

// every note-on has a note-off after it, on the same channel and key
function balanced(messages) {
  const open = new Map();
  for (const { bytes: [status, key, vel], when } of messages) {
    const id = `${status & 15}:${key}`, kind = status & 0xf0;
    if (kind === 0x90 && vel > 0) { assert(!open.has(id), `note ${id} on twice without an off`); open.set(id, when ?? 0); }
    if (kind === 0x80 && open.has(id)) { assert((when ?? Infinity) >= open.get(id), `the off of ${id} comes after its on`); open.delete(id); }
  }
  return open.size;
}

test("occurrences: a playback's notes in a window, across a loop's turns, in order", () => {
  const { core } = load();
  const notes = [{ t: 0 }, { t: 0.5 }, { t: 1.5 }].map((n, i) => ({ ...n, i }));
  const at = (from, to, loop) => core.occurrences(notes, 2, loop, from, to).map((o) => [o.note.i, o.at]);
  same(at(0, 0.6, false), [[0, 0], [1, 0.5]]);
  same(at(0.6, 2.6, true), [[2, 1.5], [0, 2], [1, 2.5]], "the next cycle follows the loop's turn");
  same(at(0.6, 2.6, false), [[2, 1.5]], "without a loop, one cycle");
  same(at(1, 1, true), [], "an empty window");
  same(at(0, 0.5, true), [[0, 0]], "a window ends before its end");
});

test("the band's notes within a playback: from its origin, a moment early counts, each kept inside the cycle", () => {
  const { core } = load();
  const players = [{ part: "bass", drums: false, notes: [[3.95, 1, 40, 90], [4, 1, 43, 90], [7.5, 2, 45, 90], [8, 1, 47, 90], [2, 1, 38, 90]] },
    { part: "drum", drums: true, notes: [[5, 0.1, 36, 100]] }, { part: "harp", drums: false, notes: [[4, 1, 60, 50]] }];
  const notes = core.bandNotes(players, 4, 4, 0.5, (p) => (p === "harp" ? "off" : 3));
  same(notes.map((n) => [n.player, n.key, n.t]), [["bass", 40, 0], ["bass", 43, 0], ["bass", 45, 1.75], ["drum", 36, 0.5]]);
  assert(Math.abs(notes[2].d - (2 - 1.75 - 0.005)) < 1e-9, "a note ringing past the cycle's end is cut at it");
  assert.equal(notes[3].drums, true);
});

test("the scheduler sends notes a moment ahead, each note-off in turn, and a stop ends them all", () => {
  const { core } = load();
  const sent = [];
  let now = 10;
  const notes = [
    { player: "tune", t: 0, d: 0.5, key: 60, vel: 96 },
    { player: "tune", t: 0.3, d: 0.1, key: 62, vel: 96 },
    { player: "chords", t: 0.4, d: 2, key: 64, vel: 64 },
    { player: "tune", t: 0.6, d: 0.5, key: 60, vel: 96 }, // the same key again before the first one ends
    { player: "page-band", t: 0.05, d: 0.2, key: 50, vel: 90 },
  ];
  const heard = [];
  const routes = { tune: 0, chords: 15, "page-band": "page" };
  const s = core.scheduler({ notes, cycle: 4, loop: () => false, started: 10, now: () => now,
    send: (bytes, when) => sent.push({ bytes, when }), sound: (n, when) => heard.push([n.key, when]), routeOf: (p) => routes[p] });
  s.tick();
  same(sent.map((m) => m.bytes), [[0x90, 60, 96]], "only what begins in the next 0.2 s");
  same(heard, [[50, 10.05]], "a player routed here is played here, on time");
  now = 10.25; s.tick();
  now = 10.45; s.tick();
  const offFirst = sent.find((m) => m.bytes[0] === 0x80 && m.bytes[1] === 60);
  assert(offFirst && Math.abs(offFirst.when - 10.5) < 1e-9, "the first C's note-off at its end");
  now = 10.55; s.tick();
  const cs = sent.filter((m) => m.bytes[1] === 60).map((m) => [m.bytes[0], +m.when.toFixed(3)]);
  same(cs, [[0x90, 10], [0x80, 10.5], [0x90, 10.6]]);
  assert.equal(s.open.size, 2, "the chord and the second C are still sounding");
  now = 10.7; s.stop();
  assert.equal(balanced(sent), 0, "a stop ends every note sent");
  const tail = sent.slice(-4).map((m) => m.bytes);
  same(tail.filter((b) => (b[0] & 0xf0) === 0xb0).map((b) => [b[0] & 15, b[1]]).sort(),
    [[0, 123], [0, 64], [15, 123], [15, 64]].sort(), "and each channel used hears all-notes-off and the pedal let go");
  for (const m of sent.filter((x) => x.bytes[0] === 0x80)) assert(m.when >= 10, "never an off before the playback");
});

test("a note-on still ahead when the sketch stops gets its note-off after it", () => {
  const { core } = load();
  const sent = [];
  let now = 0;
  const s = core.scheduler({ notes: [{ player: "tune", t: 0.15, d: 1, key: 67, vel: 90 }], cycle: 2, loop: () => false,
    started: 0, now: () => now, send: (bytes, when) => sent.push({ bytes, when }), sound() {}, routeOf: () => 2 });
  s.tick(); // sent for 0.15 s, which hasn't come yet
  now = 0.05; s.stop();
  const on = sent.find((m) => m.bytes[0] === 0x92), off = sent.find((m) => m.bytes[0] === 0x82);
  assert(on && off && off.when > on.when, "the off is timed after the on it ends");
  const cc = sent.filter((m) => m.bytes[0] === 0xb2);
  assert(cc.every((m) => m.when > on.when), "and so is all-notes-off");
});

test("a loop sends its notes again each turn, and ends each note before the turn", () => {
  const { core } = load();
  const sent = [];
  let now = 0;
  const s = core.scheduler({ notes: [{ player: "tune", t: 0, d: 0.9, key: 60, vel: 90 }, { player: "tune", t: 0.5, d: 0.49, key: 64, vel: 90 }],
    cycle: 1, loop: () => true, started: 0, now: () => now, send: (bytes, when) => sent.push({ bytes, when }), sound() {}, routeOf: () => 0 });
  for (now = 0; now < 3.05; now += 0.025) s.tick();
  const ons = sent.filter((m) => m.bytes[0] === 0x90).map((m) => [m.bytes[1], +m.when.toFixed(3)]);
  same(ons.slice(0, 6), [[60, 0], [64, 0.5], [60, 1], [64, 1.5], [60, 2], [64, 2.5]]);
  s.stop();
  assert.equal(balanced(sent), 0);
});

test("a player sent to MIDI plays here while there's no output; the sketch's own players default here", () => {
  const { P, core } = load();
  core.set.routes = { tune: 0, chords: "off", guitar: 3 };
  assert.equal(P.route("tune"), "page", "no output: here instead of silent");
  assert.equal(P.route("chords"), "off");
  assert.equal(P.route("bass"), "page");
  assert.equal(core.routeOf("guitar"), "page");
  assert.equal(core.routeOf("fiddle"), "off", "the band's parts sit out until asked for");
  core.midi.output = output();
  assert.equal(P.route("tune"), "midi");
  assert.equal(core.routeOf("guitar"), 3);
});

test("start and stop: the sketch's notes and the band's go out on their channels with their programs, and all end", () => {
  const { P, core, intervals, setClock } = load();
  const out = output();
  core.midi.output = out;
  core.set.routes = { tune: 0, chords: 15, "bass-sketch": "page", guitar: 2, drum: 9, harp: "page" };
  core.band = { key: null, tune: { channel: 0, program: 52 }, chords: { channel: 15, program: 0 }, players: [
    { part: "guitar", channel: 2, program: 25, drums: false, notes: [[0, 1, 52, 80], [1, 1, 55, 80]] },
    { part: "drum", channel: 9, program: null, drums: true, notes: [[0, 0.1, 36, 100], [0.5, 0.1, 42, 60]] },
    { part: "harp", channel: 4, program: 46, drums: false, notes: [[0.25, 1, 67, 60]] },
  ] };
  const ctx = { currentTime: 5 };
  const sounds = [];
  P.start({ ctx, started: 5.04, cycle: 2 * 0.6, loop: () => false, seconds: 0.6, origin: 0, span: 2,
    notes: [{ player: "tune", t: 0, d: 0.5, key: 72, vel: 96 }, { player: "chords", t: 0, d: 0.5, key: 60, vel: 84 },
      { player: "bass", t: 0, d: 0.5, key: 36, vel: 96 }],
    sound: (n, when) => sounds.push([n.player, n.key, when]) });
  const programs = out.sent.filter((m) => (m.bytes[0] & 0xf0) === 0xc0).map((m) => [m.bytes[0] & 15, m.bytes[1]]);
  same(programs.sort(), [[0, 52], [15, 0], [2, 25]].sort(), "each channel its General MIDI sound; none for drums");
  for (ctx.currentTime = 5; ctx.currentTime < 6.4; ctx.currentTime += 0.025) { // the two clocks run together
    setClock(1000 + (ctx.currentTime - 5) * 1000);
    intervals.filter(Boolean).forEach((fn) => fn());
  }
  const ons = out.sent.filter((m) => (m.bytes[0] & 0xf0) === 0x90).map((m) => [m.bytes[0] & 15, m.bytes[1]]);
  same(ons, [[0, 72], [15, 60], [2, 52], [9, 36], [9, 42], [2, 55]]);
  same(sounds.map((s) => s.slice(0, 2)), [["harp", 67]], "the harp plays here; the sketch's bass is the sketch's to play");
  assert(out.sent.every((m) => m.when === undefined || m.when > 1000), "timestamps on the MIDI clock");
  P.stop();
  assert.equal(balanced(out.sent), 0, "every note-on has its note-off");
  assert.equal(intervals.filter(Boolean).length, 0, "the look-ahead stops with the sketch");
});

test("without Web MIDI, or with it refused, nothing breaks and the sketch plays here", async () => {
  const safari = load();
  await safari.P.connect(false);
  assert.equal(safari.core.midi.state, "none");
  assert.equal(safari.P.route("tune"), "page");
  safari.P.panic(); // nothing to quiet
  const refused = load({ navigator: { requestMIDIAccess: () => Promise.reject(Object.assign(new Error("no"), { name: "SecurityError" })) } });
  await refused.P.connect(false);
  assert.equal(refused.core.midi.state, "refused");
  refused.P.start({ ctx: { currentTime: 0 }, started: 0, cycle: 1, loop: () => false, seconds: 0.5, origin: 0, span: 2,
    notes: [{ player: "tune", t: 0, d: 0.5, key: 60, vel: 90 }] });
  refused.intervals.filter(Boolean).forEach((fn) => fn());
  refused.P.stop();
});

test("an output that vanishes mid-song is let go, and the rest carries on", () => {
  const { P, core, intervals } = load();
  let calls = 0;
  core.midi.output = { id: "x", send() { calls++; if (calls > 2) throw Object.assign(new Error("gone"), { name: "InvalidStateError" }); } };
  core.set.routes = { tune: 0 };
  const ctx = { currentTime: 0 };
  P.start({ ctx, started: 0, cycle: 4, loop: () => false, seconds: 0.5, origin: 0, span: 8,
    notes: [0, 0.1, 0.15, 0.3].map((t, i) => ({ player: "tune", t, d: 0.05, key: 60 + i, vel: 90 })) });
  for (ctx.currentTime = 0; ctx.currentTime < 1; ctx.currentTime += 0.025) intervals.filter(Boolean).forEach((fn) => fn());
  assert.equal(core.midi.output, null);
  assert.equal(P.route("tune"), "page");
  P.stop();
});

test("Panic tells every channel to stop, and the settings are kept in this browser", () => {
  const storage = {};
  const { P, core } = load({ storage });
  const out = output();
  core.midi.output = out;
  P.panic();
  const cc = out.sent.filter((m) => (m.bytes[0] & 0xf0) === 0xb0);
  assert.equal(new Set(cc.map((m) => m.bytes[0] & 15)).size, 16);
  assert(cc.some((m) => m.bytes[1] === 120) && cc.some((m) => m.bytes[1] === 123));
  assert.equal(out.sent.filter((m) => (m.bytes[0] & 0xf0) === 0x80).length, 16 * 128);
  storage["songbird.studio.players"] = JSON.stringify({ routes: { tune: 3, chords: "off", evil: "x", bass: 99 }, programs: false });
  const again = load({ storage });
  same({ ...again.core.set.routes }, { tune: 3, chords: "off" }, "only routes that make sense are taken back");
  assert.equal(again.core.set.programs, false);
});
