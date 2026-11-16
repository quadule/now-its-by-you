// The studio's live sound (songbird/studio/live.js; docs/notes/STUDIO-LIVE-SOUND.md): where it may make what nobody
// pressed for, the coalescing of edits to the latest, which audio is heard for which edits, the loop's clock and its
// swaps, and the single notes' memory. Run with node --test.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const L = require("../songbird/studio/live.js");

test("only a studio on this computer makes renders nobody pressed for; single notes there and in a shared one", () => {
  assert.deepEqual(L.mayRenderAhead({}), { auto: true, notes: true, why: "" });
  assert.equal(L.mayRenderAhead({ device: true }).auto, false);
  assert.equal(L.mayRenderAhead({ device: true }).notes, false);
  assert.equal(L.mayRenderAhead({ public: true }).auto, false);
  assert.equal(L.mayRenderAhead({ public: true, shared: true }).notes, false);
  assert.deepEqual(L.mayRenderAhead({ shared: true }), { auto: false, notes: true, why: "shared" });
  assert.equal(L.mayRenderAhead({ device: true, shared: true }).why, "device");
});

// H's first verse, as studio.loop_of says it
const VERSE = { start: 1.1397, length: 20.4691, head: 0.3198, bars: [0, 2.5586, 5.1176, 7.6756, 10.2346, 12.7936, 15.3516, 17.9106] };

test("the loop's clock: the first time round from the file's start, each later one from its pickup", () => {
  const s = L.shape(VERSE, 24);
  assert.equal(L.roundAt(0, 10, s), 0);
  assert.equal(L.roundAt(10 + 20.4691 - 0.31, 10, s), 1);  // the next one's pickup has begun
  assert.equal(L.roundAt(10 + 20.4691 - 0.33, 10, s), 0);
  const { k, offset } = L.offsetAt(10 + 20.4691 + 1, 10, s);
  assert.equal(k, 1);
  assert.ok(Math.abs(offset - (1.1397 + 1)) < 1e-9);
  assert.ok(Math.abs(L.fraction(10 + 20.4691 * 1.5, 10, s) - 0.5) < 1e-9);
  assert.equal(L.fraction(5, 10, s), 0);
  // a file without a loop loops as it is
  assert.deepEqual(L.shape(null, 12.5), { start: 0, length: 12.5, head: 0, bars: [0] });
  assert.equal(L.shape({ start: 1, length: 8, head: 3 }, 10).head, 1, "a pickup is never before the file's start");
});

test("new audio takes over at the next bar line, never one too near to schedule, never inside the next pickup", () => {
  const s = L.shape(VERSE, 24), b0 = 10;
  assert.ok(Math.abs(L.swapTime(b0 + 1, b0, s) - (b0 + 2.5586)) < 1e-9);
  assert.ok(Math.abs(L.swapTime(b0 + 2.5586 - 0.03, b0, s) - (b0 + 5.1176)) < 1e-9, "30 ms is too near");
  // after the last bar line: the start of the next time round (its pickup), not a bar line inside it
  const last = L.swapTime(b0 + 18.5, b0, s);
  assert.ok(Math.abs(last - (b0 + 20.4691 - 0.3198)) < 1e-9, last);
  // before the first bar line (the breath and pickup of the first time round): the first bar line
  assert.ok(Math.abs(L.swapTime(b0 - 1, b0, s) - b0) < 1e-9);
  // a later time round
  assert.ok(Math.abs(L.swapTime(b0 + 20.4691 + 3, b0, s) - (b0 + 20.4691 + 5.1176)) < 1e-9);
});

// a keeper with its renders held by the test: start() gives a task whose done the test settles
function harness(options = {}) {
  const started = [], offered = [], cancelled = [], timers = [];
  const k = L.keeper({
    start: (target) => {
      let settle;
      const task = { target, job: { state: options.queued ? "queued" : "running" }, done: new Promise((r) => { settle = r; }) };
      task.settle = settle;
      started.push(task);
      return task;
    },
    cancel: (task) => cancelled.push(task.target.key),
    offer: (job, target) => offered.push([job.key, target.key]),
    schedule: (f) => { timers.push(f); return timers.length; },
    unschedule: (id) => { timers[id - 1] = null; },
    auto: options.auto ?? true,
  });
  const run = () => { for (let i = 0; i < timers.length; i++) { const f = timers[i]; timers[i] = null; f?.(); } };
  const flush = () => new Promise((r) => setImmediate(r));
  return { k, started, offered, cancelled, run, flush };
}

test("a burst of edits is made once, as the last of them leaves the song", async () => {
  const h = harness();
  h.k.begin();
  for (const key of ["a", "b", "c"]) h.k.want({ key });
  assert.equal(h.k.status(), "updating");
  h.run();
  assert.deepEqual(h.started.map((t) => t.target.key), ["c"]);
  h.started[0].settle({ state: "done", key: "c" });
  await h.flush();
  assert.deepEqual(h.offered, [["c", "c"]]);
  assert.equal(h.k.status(), "current");
});

test("an edit while one is being made waits for it, never plays it, and then makes the latest", async () => {
  const h = harness();
  h.k.begin(); h.k.want({ key: "a" }); h.run();
  h.k.want({ key: "b" }); h.k.want({ key: "c" });
  assert.deepEqual(h.cancelled, [], "one being made isn't dropped (the renderer makes one thing at a time)");
  assert.equal(h.k.status(), "updating");
  h.started[0].settle({ state: "done", key: "a" });
  await h.flush();
  assert.deepEqual(h.offered, [], "a finished for edits since replaced is not heard");
  h.run();
  assert.deepEqual(h.started.map((t) => t.target.key), ["a", "c"]);
  h.started[1].settle({ state: "done", key: "c" });
  await h.flush();
  assert.deepEqual(h.offered, [["c", "c"]]);
});

test("an edit while one still waits its turn drops it and asks for the latest", async () => {
  const h = harness({ queued: true });
  h.k.begin(); h.k.want({ key: "a" }); h.run();
  h.k.want({ key: "b" }); h.run();
  assert.deepEqual(h.cancelled, ["a"]);
  assert.deepEqual(h.started.map((t) => t.target.key), ["a", "b"]);
  h.started[0].settle({ state: "failed", error: "cancelled" });
  h.started[1].settle({ state: "done", key: "b" });
  await h.flush();
  assert.deepEqual(h.offered, [["b", "b"]]);
});

test("audio whose key isn't the one asked for is never heard", async () => {
  const h = harness();
  h.k.begin(); h.k.want({ key: "a" }); h.run();
  h.started[0].settle({ state: "done", key: "zzz" });
  await h.flush();
  assert.deepEqual(h.offered, []);
  assert.notEqual(h.k.status(), "current");
});

test("back to what plays (an undo) is current at once, and makes nothing", async () => {
  const h = harness();
  h.k.begin(); h.k.want({ key: "a" }); h.run();
  h.started[0].settle({ state: "done", key: "a" }); await h.flush();
  h.k.want({ key: "b" });
  h.k.want({ key: "a" });
  h.run();
  assert.equal(h.started.length, 1);
  assert.equal(h.k.status(), "current");
});

test("stopped, nothing more is asked for and what was in flight is not heard", async () => {
  const h = harness();
  h.k.begin(); h.k.want({ key: "a" }); h.run();
  h.k.stop();
  assert.deepEqual(h.cancelled, ["a"]);
  h.started[0].settle({ state: "done", key: "a" }); await h.flush();
  h.k.want({ key: "b" }); h.run();
  assert.deepEqual(h.offered, []);
  assert.equal(h.started.length, 1);
  assert.equal(h.k.status(), "off");
});

test("where it isn't kept up to date by itself, an edit leaves the loop an earlier version until asked", async () => {
  const h = harness({ auto: false });
  h.k.begin(); h.k.want({ key: "a" }); h.k.now(); h.run();
  h.started[0].settle({ state: "done", key: "a" }); await h.flush();
  h.k.want({ key: "b" }); h.run();
  assert.equal(h.started.length, 1);
  assert.equal(h.k.status(), "earlier");
  h.k.auto = true;  // turned on: the next edit is made
  h.k.want({ key: "c" }); h.run();
  assert.deepEqual(h.started.map((t) => t.target.key), ["a", "c"]);
});

test("one that couldn't be made says so, is not asked for again by itself, and the next edit tries", async () => {
  const h = harness();
  h.k.begin(); h.k.want({ key: "a" }); h.run();
  h.started[0].settle({ state: "failed", error: "busy" }); await h.flush();
  h.run();
  assert.equal(h.k.status(), "failed");
  assert.equal(h.started.length, 1);
  h.k.want({ key: "b" }); h.run();
  assert.equal(h.started.length, 2);
});

// a WebAudio context's stand-in: what was started where, faded and stopped when
function fakeContext() {
  const ctx = { currentTime: 0, destination: {}, sources: [] };
  ctx.createGain = () => {
    const events = [];
    return { gain: { value: 1, events, setValueAtTime: (v, t) => events.push(["set", v, t]), linearRampToValueAtTime: (v, t) => events.push(["ramp", v, t]),
      cancelScheduledValues: () => {} }, connect() {}, disconnect() {} };
  };
  ctx.createBufferSource = () => {
    const s = { buffer: null, started: null, stopped: null, connect() {}, start(t, o) { s.started = [t, o]; }, stop(t) { s.stopped = t; } };
    ctx.sources.push(s);
    return s;
  };
  return ctx;
}
const buf = (name, duration = 24) => ({ name, duration });

test("the loop plays the file from its beginning, then each time round from its pickup, the one before faded there", () => {
  const ctx = fakeContext();
  let tick = null;
  const loop = L.looper(ctx, { tick: (f) => { tick = f; return 1; }, untick: () => {} });
  loop.play(buf("a"), VERSE, "a", 1);
  assert.deepEqual(ctx.sources[0].started, [1, 0]);
  const b0 = 1 + VERSE.start, seam = b0 + VERSE.length - VERSE.head;
  ctx.currentTime = seam - 0.3; tick();
  const second = ctx.sources[1];
  assert.ok(Math.abs(second.started[0] - seam) < 1e-9 && Math.abs(second.started[1] - (VERSE.start - VERSE.head)) < 1e-9, second.started);
  assert.ok(Math.abs(ctx.sources[0].stopped - (seam + L.SEAM_FADE + 0.02)) < 1e-9, "the first time round fades at the seam");
  assert.equal(loop.key, "a");
  assert.ok(Math.abs(loop.where().fraction - (VERSE.length - VERSE.head - 0.3) / VERSE.length) < 1e-9);
});

test("new audio takes over at the next bar line where it is in its file; what was to start after is made again", () => {
  const ctx = fakeContext();
  let tick = null;
  const loop = L.looper(ctx, { tick: (f) => { tick = f; return 1; }, untick: () => {} });
  loop.play(buf("a"), VERSE, "a", 0);
  const b0 = VERSE.start;
  ctx.currentTime = b0 + 3; tick();
  const at = loop.swap(buf("b"), VERSE, "b");
  assert.ok(Math.abs(at - (b0 + 5.1176)) < 1e-9);
  const fresh = ctx.sources.at(-1);
  assert.equal(fresh.buffer.name, "b");
  assert.ok(Math.abs(fresh.started[1] - (VERSE.start + 5.1176)) < 1e-9, "the same place in the new file");
  assert.ok(Math.abs(ctx.sources[0].stopped - (at + L.SWAP_FADE + 0.02)) < 1e-9, "the old fades out there");
  assert.equal(loop.key, "a", "until the bar line, the old is what sounds");
  assert.equal(loop.coming, "b");
  ctx.currentTime = at + 0.01; tick();
  assert.equal(loop.key, "b");
  assert.equal(loop.coming, null);
  // the next time round is the new audio's
  ctx.currentTime = b0 + VERSE.length - VERSE.head - 0.2; tick();
  assert.equal(ctx.sources.at(-1).buffer.name, "b");
  // a second swap while one is on its way waits for it
  ctx.currentTime = b0 + VERSE.length + 1; tick();
  const third = loop.swap(buf("c"), VERSE, "c");
  assert.equal(loop.swap(buf("d"), VERSE, "d"), null);
  ctx.currentTime = third + 0.01; tick();
  assert.equal(loop.key, "c");
  assert.equal(loop.coming, "d");
});

test("a time round already scheduled with the old audio is let go when new audio comes first", () => {
  const ctx = fakeContext();
  let tick = null;
  const loop = L.looper(ctx, { tick: (f) => { tick = f; return 1; }, untick: () => {} });
  loop.play(buf("a"), VERSE, "a", 0);
  const seam = VERSE.start + VERSE.length - VERSE.head;
  ctx.currentTime = seam - 0.3; tick();  // the second time round is scheduled
  const scheduled = ctx.sources[1];
  const at = loop.swap(buf("b"), VERSE, "b");
  assert.ok(Math.abs(at - seam) < 1e-9, "the seam is the next place it can take over");
  assert.equal(scheduled.stopped, 0, "the old second time round never starts");
  assert.equal(ctx.sources.at(-1).buffer.name, "b");
  assert.ok(Math.abs(ctx.sources.at(-1).started[0] - seam) < 1e-9);
});

test("a new length (a tempo changed) takes over at the next time round, on its own clock", () => {
  const ctx = fakeContext();
  let tick = null;
  const loop = L.looper(ctx, { tick: (f) => { tick = f; return 1; }, untick: () => {} });
  loop.play(buf("a"), VERSE, "a", 0);
  ctx.currentTime = 4; tick();
  const slower = { ...VERSE, length: 24, bars: [0, 3, 6, 9, 12, 15, 18, 21] };
  const at = loop.swap(buf("b"), slower, "b");
  assert.ok(Math.abs(at - (VERSE.start + VERSE.length - VERSE.head)) < 1e-9);
  ctx.currentTime = at + 0.01; tick();
  assert.equal(loop.where().length, 24);
});

test("loop off: the time round playing plays out, no other starts, and it ends", () => {
  const ctx = fakeContext();
  let tick = null, ended = 0;
  const loop = L.looper(ctx, { tick: (f) => { tick = f; return 1; }, untick: () => {}, ended: () => { ended++; } });
  loop.play(buf("a"), VERSE, "a", 0);
  ctx.currentTime = 2; tick();
  loop.finish();
  const before = ctx.sources.length;
  ctx.currentTime = 30; tick();
  assert.equal(ctx.sources.length, before);
  ctx.sources[0].onended?.();  // its file played out
  tick();
  assert.equal(ended, 1);
  assert.equal(loop.playing, false);
});

test("the notes' memory is bounded by bytes, the least recently used going first", () => {
  const m = L.lru(100);
  m.put("a", 1, 40); m.put("b", 2, 40);
  assert.equal(m.get("a"), 1);  // a is newer than b now
  m.put("c", 3, 40);
  assert.deepEqual(m.keys(), ["a", "c"]);
  assert.equal(m.bytes, 80);
  assert.equal(m.put("huge", 4, 101), false);
  assert.equal(m.has("huge"), false);
  m.put("a", 5, 10);
  assert.equal(m.bytes, 50);
});

test("a velocity goes to its class; a roll's octave is around its notes", () => {
  assert.deepEqual([1, 56, 57, 90, 110, 127].map(L.velocityClass), [40, 40, 72, 96, 120, 120]);
  assert.deepEqual(L.octaveAround([]), [-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5]);
  assert.equal(L.octaveAround([7, 9, 12]).length, 12);
  assert.ok(L.octaveAround([7, 9, 12]).includes(9));
});

test("a note sounds the sketch until the instrument's own is here, is asked again after an edit, and never where it isn't made", async () => {
  const asked = [];
  let revision = 0, allowed = true;
  const ctx = fakeContext();
  ctx.decodeAudioData = async (bytes) => ({ length: 44100, numberOfChannels: 2, bytes });
  const s = L.samples({ ask: async (path, body) => { asked.push([path, body]); return { key: `k${body.pitch}`, url: `/audio/k${body.pitch}.flac` }; },
    bytes: async (url) => url, context: () => ctx, allowed: () => allowed, revision: () => revision, edits: () => ({ tempo: 90 }) });
  assert.equal(s.play("guitar", 4, 90), false, "not here yet: the caller sounds the sketch's tone");
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(asked[0], ["/api/note", { edits: { tempo: 90 }, player: "guitar", pitch: 4, velocity: 96 }]);
  assert.equal(s.play("guitar", 4, 100), true, "the same velocity class: the same note");
  revision = 1;  // an edit: asked again (the studio answers the same file if nothing the guitar reads changed)
  assert.equal(s.play("guitar", 4, 96), false);
  await new Promise((r) => setImmediate(r));
  assert.equal(asked.length, 2);
  assert.equal(s.decoded.size, 1, "the same key is decoded once");
  assert.equal(await s.prefetch("guitar", [0, 1]), 2);
  allowed = false;
  assert.equal(s.play("guitar", 4, 96), false);
  assert.equal(await s.prefetch("guitar", [5]), 0);
  assert.equal(asked.length, 4);
});

test("the first audio is made when the loop is played, wherever; its view may come after the press", async () => {
  const h = harness({ auto: false });
  h.k.begin();  // pressed while the view for the latest edits is on its way: nothing to want yet
  h.run();
  assert.equal(h.started.length, 0);
  h.k.want({ key: "a" }); h.run();
  assert.deepEqual(h.started.map((t) => t.target.key), ["a"]);
});
