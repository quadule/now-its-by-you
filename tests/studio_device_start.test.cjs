// The page's first questions on the device (web/studio-wasm/device.js; docs/WEB-STUDIO.md, "On the device", "A
// quicker start"): answered from the day's file (bundle.json "first") while the studio's worker gets ready, by the
// same key studio_device.question makes; anything else waits for the worker, and the page is told; what changes the
// studio's answers ends the first answers; the worker is given the page's day; once it's ready it answers everything;
// a version's page, another day or a browser that can't unpack the file wait for the worker as before. Run with node
// --test.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const zlib = require("node:zlib");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "web", "studio-wasm", "device.js"), "utf8");
const pad = (n) => String(n).padStart(2, "0");
const now = new Date();
const TODAY = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
const FOLDER = "first-0123456789abcdef/";
const ANSWERS = {
  "GET /api/start ": [200, { day: TODAY, names: ["Ada"], from: "the file" }],
  'POST /api/song {"edits":{}}': [200, { words: [], listen: { whole: "w", sections: ["a"] }, from: "the file" }],
  'POST /api/options {"block":"verse","edits":{},"index":1}': [200, { options: ["x"], from: "the file" }],
  "GET /api/sing/offer ": [404, { error: "not found" }],
};
const tick = () => new Promise((resolve) => setImmediate(resolve));

function page({ pathname = "/", first = { folder: FOLDER, from: "2000-01-01", to: "2999-12-31" }, decompress = true,
                day = TODAY } = {}) {
  const fetched = [];
  const workers = [];
  const toasts = [];
  let release = null;  // the studio's worker gets ready when this is called
  const ready = new Promise((resolve) => { release = resolve; });
  class FakeWorker {
    constructor(url) { this.url = url; this.posted = []; workers.push(this); }
    postMessage(m) {
      this.posted.push(m);
      const say = (d) => setImmediate(() => this.onmessage?.({ data: d }));
      if (m.cmd === "init") ready.then(() => say({ kind: "ready", seconds: 1 }));
      else if (m.cmd === "studio") say({ kind: "studio", program: "p", song: "s", machine: "none", day: m.config.day, title: "T" });
      else if (m.cmd === "request") say({ kind: "answer", id: m.id, status: 200, json: JSON.stringify({ from: "the worker", path: m.path }) });
    }
    terminate() {}
  }
  const meta = { 'meta[name="studio-render"]': { content: "device" }, 'meta[name="studio-token"]': { content: "" } };
  const store = new Map();
  const sandbox = {
    document: { querySelector: (q) => meta[q] || null, getElementById: () => null, readyState: "complete",
                addEventListener() {} },
    location: { pathname, hash: "", href: `http://studio.test${pathname}`, origin: "http://studio.test" },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    Worker: FakeWorker, WebAssembly, URL, URLSearchParams, Response, Headers, Request, TextDecoder, TextEncoder, Blob,
    DecompressionStream: decompress ? DecompressionStream : undefined, structuredClone, clearTimeout,
    setTimeout: (f, ms) => { const t = setTimeout(f, ms); t.unref?.(); return t; },  // (a deadline never holds node open)
    setImmediate, console, crypto,
  };
  sandbox.window = sandbox;
  sandbox.songbirdStudio = { toast: (text) => toasts.push(text) };
  sandbox.fetch = async (input) => {
    const url = new URL(String(input), "http://studio.test");
    fetched.push(url.pathname);
    if (url.pathname === "/render/bundle.json") {
      return new Response(JSON.stringify({ v: 1, base: "/render/", pyodide: "py-0123456789abcdef", app: "app-0123456789abcdef",
        bytes: 35e6, studio_bytes: 20e6, studio: { song: "/app/songs/h.json", machine: "none" }, ...(first ? { first } : {}) }));
    }
    if (url.pathname === `/render/${FOLDER}${day}.gzip`) {
      return new Response(zlib.gzipSync(JSON.stringify({ v: 1, day, answers: ANSWERS })));
    }
    return new Response("not found", { status: 404 });
  };
  vm.createContext(sandbox);
  vm.runInContext(SOURCE, sandbox);
  const ask = async (p, body) => {
    const r = await sandbox.fetch(p, body === undefined ? { headers: { "X-Studio": "device" } }
      : { method: "POST", headers: { "Content-Type": "application/json", "X-Studio": "device" }, body: JSON.stringify(body) });
    return { status: r.status, data: await r.json() };
  };
  const asked = () => workers.flatMap((w) => w.posted.filter((m) => m.cmd === "request").map((m) => m.path));
  return { ask, asked, workers, fetched, toasts, release, sandbox };
}

test("before the worker is ready, the page's first questions are answered from the day's file", async () => {
  const p = page();
  assert.deepEqual(await p.ask("/api/start"), { status: 200, data: ANSWERS["GET /api/start "][1] });
  // the same key however the page orders its JSON
  assert.deepEqual((await p.ask("/api/options", { index: 1, edits: {}, block: "verse" })).data.from, "the file");
  assert.deepEqual(await p.ask("/api/sing/offer"), { status: 404, data: { error: "not found" } });
  const song = await p.ask("/api/song", { edits: {} });
  assert.equal(song.data.from, "the file");
  assert.deepEqual(song.data.listen.ready, []);  // as the worker's answer is given: what this page made already
  assert.deepEqual(p.asked(), []);
  assert.ok(p.fetched.includes(`/render/${FOLDER}${TODAY}.gzip`));
  // the worker is started all the same, at once, and told the page's day
  await tick();
  assert.equal(p.workers.length, 1);
  assert.equal(p.workers[0].posted[0].cmd, "init");
  assert.equal(p.workers[0].posted[0].bytes, 20e6);  // what the studio's worker fetches, for its progress
  p.release();
  await p.sandbox.SongbirdDevice.ready();
  assert.equal(p.workers[0].posted.find((m) => m.cmd === "studio").config.day, TODAY);
  // once it's ready, it answers everything, the first questions too
  assert.equal((await p.ask("/api/start")).data.from, "the worker");
  assert.equal((await p.ask("/api/song", { edits: {} })).data.from, "the worker");
});

test("anything else waits for the worker, and the page is told where it asked", async () => {
  const p = page();
  await p.ask("/api/start");
  let answered = null;
  const edit = p.ask("/api/song", { edits: { tempo: 92 } }).then((r) => { answered = r; });
  for (let i = 0; i < 5; i++) await tick();
  assert.equal(answered, null);
  assert.deepEqual(p.toasts, ["The studio is still getting ready: one moment."]);
  p.release();
  await edit;
  assert.deepEqual(answered.data, { from: "the worker", path: "/api/song" });
  // first questions asked afterwards are still the file's until the worker is ready, but here it is
  assert.equal((await p.ask("/api/start")).data.from, "the worker");
});

test("what changes the studio's answers ends the first answers: from then on the worker answers, in order", async () => {
  const p = page();
  await p.ask("/api/start");
  const kept = p.ask("/api/sing/keep", { phrasing: "{}" });
  await tick();
  const start = p.ask("/api/start");
  for (let i = 0; i < 5; i++) await tick();
  assert.deepEqual(p.asked(), []);  // both waiting for the worker
  p.release();
  assert.equal((await kept).data.path, "/api/sing/keep");
  assert.equal((await start).data.from, "the worker");
  assert.deepEqual(p.asked(), ["/api/sing/keep", "/api/start"]);
});

test("a version's page, a day the build didn't make, or no way to unpack the file: the worker answers everything", async () => {
  for (const options of [{ pathname: `/v/${"a".repeat(32)}` }, { first: { folder: FOLDER, from: "2000-01-01", to: "2000-12-31" } },
                         { first: null }, { decompress: false }, { day: "1999-01-01" }]) {
    const p = page(options);
    const start = p.ask("/api/start");
    for (let i = 0; i < 5; i++) await tick();
    assert.ok(!p.fetched.some((f) => f.endsWith(".gzip") && f.includes(TODAY)) || options.day, JSON.stringify(options));
    if (options.pathname) continue;  // the version's own reading is device.js's as before (not faked here)
    p.release();
    assert.equal((await start).data.from, "the worker", JSON.stringify(options));
    assert.deepEqual(p.toasts, []);
  }
});
