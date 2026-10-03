// The renderer's choice of where a song is made (songbird/studio/renderer.js, songbird studio --browser-render):
// in the visitor's browser, by a worker running the program (web/studio-wasm/studio-worker.mjs, stood in for here),
// or by the server, which is also the fallback for anything the browser can't do. Run with node --test.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const R = require("../songbird/studio/renderer.js");

const now = () => Promise.resolve();
const DESKTOP = { wasm: true, worker: true, mobile: false, memory: 8 };
const BUNDLE = { v: 1, base: "/render/", pyodide: "py-0123456789abcdef", app: "app-0123456789abcdef", bytes: 36e6, transfer: 29e6 };
const SPEC = (key, kind, extra = {}) => ({ key, label: `label ${key}`, kind, spec: `{"v":1,"kind":"${kind}","key":"${key}"}`, ...extra });
const CLOCK = [0.911, 3.395, 5.88, 8.364];  // a whole song's bar lines in seconds (the studio's bar_seconds)
const tick = () => new Promise((resolve) => setImmediate(resolve));

// A stand-in for the worker: answers init with loading then ready, and a render with its progress then the file,
// unless told to fail, go silent, or crash
function fakeWorkers(script = {}) {
  const made = [];
  const spawn = (url) => {
    const w = { url, terminated: false, renders: 0, posted: [],
      postMessage(m) {
        this.posted.push(m);
        const say = (d) => setImmediate(() => { if (!w.terminated) w.onmessage?.({ data: d }); });
        if (m.cmd === "init") {
          say({ kind: "loading", received: 1e6, bytes: m.bytes });
          say({ kind: "ready", seconds: 5 });
        } else if (m.cmd === "render") {
          w.renders += 1;
          const what = JSON.parse(m.spec);
          const fate = typeof script.render === "function" ? script.render(what, w) : script.render;
          if (fate === "silent") return;
          if (fate === "memory") return say({ kind: "error", message: "MemoryError", memory: true });
          if (fate === "crash") return setImmediate(() => w.onerror?.({ message: "the worker crashed" }));
          say({ kind: "progress", progress: 0.5, stage: "singing" });
          say({ kind: "done", made: what.kind, key: what.key, id: `id-${what.key}`, duration: 9.2, seconds: 4.8,
            heap: script.heap,
            flac: new ArrayBuffer(8),
            record: what.kind === "whole" ? { generation: 1, rendered_at: "2026-09-30T12:00:00+00:00", yours: 3, program_sha256: "p" } : null });
        }
      },
      terminate() { this.terminated = true; } };
    made.push(w);
    return w;
  };
  return { spawn, made };
}

// A stand-in for the studio: the bundle, the render spec, and its own queue (every job made at once)
function studioServer(extra = {}) {
  const asked = [];
  let jobs = 0;
  const ask = async (path, body) => {
    asked.push([path, body]);
    if (path === "/render/bundle.json") return extra.bundle === undefined ? BUNDLE : extra.bundle;
    if (path === "/api/render/spec") {
      if (extra.made) return { key: "k", label: "made", made: true };
      if (extra.server && body.section === null) return { key: "k", label: "long", server: true };
      if (extra.tooLong && body.section === null) return { key: "k", label: "long", too_long: extra.tooLong };
      const whole = body.section === null;
      const key = whole ? `w${body.edits.tempo || 0}` : `s${body.section}-${body.edits.tempo || 0}`;
      return SPEC(key, whole ? "whole" : "section", whole ? { name: { song: "now-its-by-you", day: "2026-09-30" }, bar_seconds: CLOCK } : {});
    }
    if (path === "/api/listen" || path === "/api/record") {
      jobs += 1;
      return { id: `j${jobs}`, state: "done", url: `/audio/server-${jobs}.flac`, key: "sk",
        result: path === "/api/record" ? { recorded: { name: "server.flac" } } : null };
    }
    throw new Error(`unexpected ${path}`);
  };
  return { ask, asked };
}

function browser(script, options = {}, extra = {}) {
  R.reset();
  const fake = fakeWorkers(script);
  const server = studioServer(extra);
  let blobs = 0;
  const r = R.create(server.ask, { wait: now, env: options.env || DESKTOP, spawn: fake.spawn, storage: null,
    blob: () => `blob:${++blobs}`, workers: options.workers, cacheBytes: options.cacheBytes });
  return { r, fake, server };
}

test("which browsers make the song: a desktop with the bundle; not a phone, a small memory, or without workers", () => {
  assert.equal(R.capable(DESKTOP, BUNDLE).ok, true);
  assert.equal(R.capable({ ...DESKTOP, memory: null }, BUNDLE).ok, true);  // Firefox and Safari don't say
  assert.match(R.capable({ ...DESKTOP, mobile: true }, BUNDLE).why, /phones/);
  assert.equal(R.capable({ ...DESKTOP, memory: 2 }, BUNDLE).ok, false);
  assert.equal(R.capable({ ...DESKTOP, worker: false }, BUNDLE).ok, false);
  assert.equal(R.capable(DESKTOP, null).ok, false);
});

test("the setting, and what went wrong earlier in the visit, choose the server", () => {
  const none = { count: 0, whole: false, visit: false };
  assert.equal(R.choose("auto", DESKTOP, BUNDLE, none, "section").where, "browser");
  assert.equal(R.choose("server", DESKTOP, BUNDLE, none, "section").where, "server");
  assert.equal(R.choose("auto", { ...DESKTOP, mobile: true }, BUNDLE, none, "section").where, "server");
  assert.equal(R.choose("browser", { ...DESKTOP, mobile: true }, BUNDLE, none, "section").where, "browser");  // asked for
  assert.equal(R.choose("browser", DESKTOP, null, none, "section").where, "server");  // no bundle served
  assert.equal(R.choose("auto", DESKTOP, BUNDLE, { ...none, whole: true }, "whole").where, "server");
  assert.equal(R.choose("auto", DESKTOP, BUNDLE, { ...none, whole: true }, "section").where, "browser");
  assert.equal(R.choose("browser", DESKTOP, BUNDLE, { ...none, visit: true }, "section").where, "server");
});

test("a section made in this browser: the spec from the server, the worker's file as a blob, and where it was made", async () => {
  const { r, fake, server } = browser({});
  const heard = [];
  const job = await r.preview({ edits: { tempo: 92 }, section: 2 }, (j) => heard.push(j.stage)).done;
  assert.equal(job.state, "done");
  assert.equal(job.where, "browser");
  assert.equal(job.url, "blob:1");
  assert.equal(job.id, "id-s2-92");
  assert.deepEqual(server.asked.map((a) => a[0]), ["/render/bundle.json", "/api/render/spec"]);
  assert.deepEqual(server.asked[1][1], { edits: { tempo: 92 }, who: "you", section: 2 });
  assert.equal(fake.made.length, 1);
  assert.equal(fake.made[0].url, "http://localhost/render/app-0123456789abcdef/studio-worker.mjs");
  assert.deepEqual(fake.made[0].posted[0], { cmd: "init", pyodide: "http://localhost/render/py-0123456789abcdef/",
    app: "http://localhost/render/app-0123456789abcdef/", bytes: 36e6, stemCacheBytes: 128 * 2 ** 20 });
  assert.ok(heard.some((s) => /getting the singer ready \(once: 1 of 34 MB\)/.test(s)), heard.join(" | "));
  assert.ok(heard.includes("singing"));
  assert.deepEqual(R.made.map((m) => [m.where, m.size, m.key]), [["browser", "section", "s2-92"]]);
  // asked again: kept here, it plays at once, and nothing is made
  const again = await r.preview({ edits: { tempo: 92 }, section: 2 }).done;
  assert.equal(again.url, "blob:1");
  assert.equal(fake.made[0].renders, 1);
});

test("a section's worker makes a few, then is replaced; a whole song gets its own, terminated after", async () => {
  const { r, fake } = browser({}, { workers: { uses: 2 } });
  for (const tempo of [90, 91, 92]) await r.preview({ edits: { tempo }, section: 1 }).done;
  assert.equal(fake.made.length, 2);
  assert.equal(fake.made[0].terminated, true);
  assert.deepEqual(fake.made.map((w) => w.renders), [2, 1]);
  const job = await r.record({ edits: { tempo: 92 } }).done;
  assert.equal(job.where, "browser");
  assert.equal(fake.made.length, 3);
  assert.equal(fake.made[1].terminated, true, "the section's worker goes first");
  assert.equal(fake.made[2].terminated, true, "and the whole song's after it");
  const rec = job.result.recorded;
  assert.equal(rec.name, "now-its-by-you.2026-09-30.id-w92.flac");
  assert.equal(rec.download, job.url);
  assert.equal(rec.browser, true);
  assert.equal(rec.yours, 3);
  assert.equal(rec.next, "python3 now-its-by-you.2026-09-30.id-w92.flac studio");
});

test("a large section's heap is released after success, while a smaller worker is reused", async () => {
  const { r, fake } = browser({ heap: 700 }, { workers: { maxHeap: 512 } });
  const job = await r.preview({ edits: {}, section: 1 }).done;
  assert.equal(job.state, "done");
  assert.equal(fake.made[0].terminated, true);
  await r.preview({ edits: {}, section: 2 }).done;
  assert.equal(fake.made.length, 2);
  const small = browser({ heap: 400 }, { workers: { maxHeap: 512 } });
  await small.r.preview({ edits: {}, section: 1 }).done;
  await small.r.preview({ edits: {}, section: 2 }).done;
  assert.equal(small.fake.made.length, 1);
  assert.equal(small.fake.made[0].terminated, false);
});

test("cached files share a byte budget and a recently heard file stays cached", async () => {
  const { r, fake } = browser({}, { cacheBytes: 16 });
  await r.preview({ edits: {}, section: 1 }).done;
  await r.preview({ edits: {}, section: 2 }).done;
  await r.preview({ edits: {}, section: 1 }).done;
  assert.equal(fake.made[0].renders, 2);
  await r.record({ edits: {} }).done;
  assert.deepEqual([...R.shared.cache.keys()], ["s1-0", "w0"]);
  assert.equal([...R.shared.cache.values()].reduce((n, j) => n + j.bytes, 0), 16);
});

test("an oversized file remains usable and evicted or reset blob URLs are released", async () => {
  const revoke = URL.revokeObjectURL;
  const gone = [];
  URL.revokeObjectURL = (url) => gone.push(url);
  try {
    const { r } = browser({}, { cacheBytes: 1 });
    const first = await r.preview({ edits: {}, section: 1 }).done;
    const second = await r.preview({ edits: {}, section: 2 }).done;
    assert.deepEqual([...R.shared.cache.keys()], [second.key]);
    assert.ok(gone.includes(first.url));
    assert.ok(!gone.includes(second.url));
    R.reset();
    assert.ok(gone.includes(second.url));
  } finally {
    URL.revokeObjectURL = revoke;
  }
});

test("preview eviction preserves the displayed recording until a new recording replaces it", async () => {
  const revoke = URL.revokeObjectURL;
  const gone = [];
  URL.revokeObjectURL = (url) => gone.push(url);
  try {
    const { r } = browser({}, { cacheBytes: 8 });
    const recording = await r.record({ edits: {} }).done;
    for (const section of [1, 2, 3]) await r.preview({ edits: {}, section }).done;
    assert.ok(R.shared.cache.has(recording.key));
    assert.ok(!gone.includes(recording.url));
    const next = await r.record({ edits: { tempo: 100 } }).done;
    assert.equal(R.shared.recording, next);
    assert.ok(gone.includes(recording.url));
    assert.ok(!gone.includes(next.url));
  } finally {
    R.reset();
    URL.revokeObjectURL = revoke;
  }
});

test("a cached whole preview promoted to recording releases the previous recording's cache exception", async () => {
  const { r, fake } = browser({}, { cacheBytes: 8 });
  const old = await r.record({ edits: {} }).done;
  const preview = await r.preview({ edits: { tempo: 100 }, section: null }).done;
  assert.equal(R.shared.cache.size, 2);
  const recording = await r.record({ edits: { tempo: 100 } }).done;
  assert.equal(recording, preview);
  assert.equal(R.shared.recording, recording);
  assert.ok(!R.shared.cache.has(old.key));
  assert.equal(fake.made.length, 2);
  R.setMode("server", null);
  await r.record({ edits: {} }).done;
  assert.equal(R.shared.recording, null);
  assert.ok(!R.shared.cache.has(recording.key));
});

test("a whole song made here ends with its clock, as the server's job does: the page starts it at the playhead's bar", async () => {
  const { r } = browser({});
  const heard = await r.preview({ edits: { tempo: 93 }, section: null }).done;
  assert.equal(heard.where, "browser");
  assert.deepEqual(heard.result.bar_seconds, CLOCK);
  const recorded = await r.record({ edits: { tempo: 94 } }).done;
  assert.deepEqual(recorded.result.bar_seconds, CLOCK);
  assert.equal(recorded.result.recorded.browser, true);
  assert.equal((await r.preview({ edits: { tempo: 93 }, section: 2 }).done).result.bar_seconds, undefined);
});

test("what the server has made already is asked of it, and plays from there", async () => {
  const { r, fake, server } = browser({}, {}, { made: true });
  const job = await r.preview({ edits: {}, section: 3 }).done;
  assert.equal(job.where, "server");
  assert.equal(job.url, "/audio/server-1.flac");
  assert.equal(fake.made.length, 0);
  assert.deepEqual(server.asked.map((a) => a[0]), ["/render/bundle.json", "/api/render/spec", "/api/listen"]);
});

test("a whole song too long for a browser's memory: the server's if it fits there, else said, and made nowhere", async () => {
  let { r, fake, server } = browser({}, {}, { server: true });
  let job = await r.record({ edits: {} }).done;
  assert.equal(job.where, "server");
  assert.equal(fake.made.length, 0);
  assert.deepEqual(server.asked.map((a) => a[0]), ["/render/bundle.json", "/api/render/spec", "/api/record"]);
  const why = "This version is 8.5 minutes long, too long for this small server or a browser to make in one go";
  ({ r, fake, server } = browser({}, {}, { tooLong: why }));
  job = await r.preview({ edits: {}, section: null }).done;
  assert.equal(job.state, "failed");
  assert.equal(job.error, why);
  assert.equal(fake.made.length, 0);
  assert.ok(!server.asked.some((a) => a[0] === "/api/listen"));  // never sent to the server to fail there
  assert.equal(R.shared.failures.count, 0);  // not the browser's failure: nothing moves to the server
  job = await r.record({ edits: {} }).done;
  assert.equal(job.state, "failed");
  assert.ok(!server.asked.some((a) => a[0] === "/api/record"));
  job = await r.preview({ edits: {}, section: 2 }).done;  // a section of it is made in the browser as ever
  assert.equal(job.where, "browser");
});

test("a render the browser can't make is made by the server, said quietly; after two, the server for the visit", async () => {
  const { r, fake, server } = browser({ render: "crash" });
  const heard = [];
  const job = await r.preview({ edits: {}, section: 1 }, (j) => heard.push(j.stage)).done;
  assert.equal(job.where, "server");
  assert.equal(job.url, "/audio/server-1.flac");
  assert.ok(heard.includes("this browser couldn't make it, so the server is"));
  assert.equal(fake.made[0].terminated, true);
  assert.deepEqual(server.asked.at(-1), ["/api/listen", { edits: {}, who: "you", section: 1 }]);
  assert.equal(R.made[0].failed, "the worker crashed");
  const second = await r.record({ edits: {} }).done;  // a second failure (a new worker, crashing too)
  assert.equal(second.where, "server");
  assert.deepEqual(server.asked.at(-1), ["/api/record", { edits: {} }]);
  assert.equal(R.shared.failures.visit, true);
  const third = await r.preview({ edits: {}, section: 4 }).done;  // not tried here again
  assert.equal(third.where, "server");
  assert.equal(fake.made.length, 2);
});

test("a whole song that runs out of memory sends whole songs to the server; sections stay here", async () => {
  const { r, fake } = browser({ render: (spec) => (spec.kind === "whole" ? "memory" : "ok") });
  assert.equal((await r.record({ edits: {} }).done).where, "server");
  assert.equal(R.shared.failures.whole, true);
  assert.equal((await r.record({ edits: { tempo: 80 } }).done).where, "server");
  assert.equal(fake.made.length, 1, "a whole song isn't tried here again");
  assert.equal((await r.preview({ edits: {}, section: 2 }).done).where, "browser");
});

test("a worker that goes silent is given up on, and the server makes it", async () => {
  const { r } = browser({ render: "silent" }, { workers: { timeouts: { ready: 1000, section: 30, whole: 30 } } });
  const job = await r.preview({ edits: {}, section: 2 }).done;
  assert.equal(job.where, "server");
  assert.match(R.made[0].failed, /took too long/);
});

test("the worker killed mid-render: the server makes it", async () => {
  const { r, fake } = browser({ render: "silent" });
  const task = r.record({ edits: {} });
  while (!R.debug.busy()) await tick();
  assert.equal(R.debug.kill(), true);
  const job = await task.done;
  assert.equal(job.where, "server");
  assert.equal(fake.made[0].terminated, true);
});

test("cancelling a whole song being made here stops its worker; nothing more is asked", async () => {
  const { r, fake, server } = browser({ render: "silent" });
  const task = r.preview({ edits: {}, section: null });
  while (!R.debug.busy()) await tick();
  r.cancel(task);
  const job = await task.done;
  assert.notEqual(job.state, "done");
  assert.equal(fake.made[0].terminated, true);
  assert.equal(server.asked.filter((a) => a[0] === "/api/listen").length, 0);
  assert.equal(R.made.length, 0);
});

test("chosen: the server; a studio without the bundle; a phone: the server's queue as ever", async () => {
  for (const [options, extra, mode] of [[{}, {}, "server"], [{}, { bundle: null }, null],
    [{ env: { ...DESKTOP, mobile: true } }, {}, null]]) {
    const { r, fake, server } = browser({}, options, extra);
    if (mode) R.setMode(mode, null);
    const job = await r.preview({ edits: {}, section: 2 }).done;
    assert.equal(job.where, "server");
    assert.equal(fake.made.length, 0);
    assert.ok(!server.asked.some((a) => a[0] === "/api/render/spec"));
  }
});
