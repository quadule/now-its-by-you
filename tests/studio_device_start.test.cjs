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

// the page's storage, as much of IndexedDB as device.js asks of it: "songbird-studio" holding `kept` (store -> Map)
function fakeIndexedDB(kept) {
  const db = {
    transaction(name) {
      const t = {};
      const map = kept[name] || (kept[name] = new Map());
      t.objectStore = () => ({
        get: (k) => ({ result: map.get(k) }), put: (v, k) => { map.set(k, v); return { result: k }; },
        delete: (k) => { map.delete(k); return {}; }, getAll: () => ({ result: [...map.values()] }),
      });
      setImmediate(() => t.oncomplete?.());
      return t;
    },
  };
  return {
    open(name) {
      const r = {};
      setImmediate(() => { if (name === "songbird-studio") { r.result = db; r.onsuccess?.(); } else r.onerror?.(); });
      return r;
    },
  };
}

function page({ pathname = "/", first = { folder: FOLDER, from: "2000-01-01", to: "2999-12-31" }, decompress = true,
                day = TODAY, file = Promise.resolve(), machine = "none", store = new Map(), search = "", opens,
                navigator = { languages: ["en-GB", "fr"], hardwareConcurrency: 8, deviceMemory: 4 }, scheme = "dark", hash = "",
                kept = null } = {}) {
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
      else if (m.cmd === "restore") say({ kind: "answer", id: m.id, status: 200, json: JSON.stringify({ restored: true }) });
      else if (m.cmd === "request") say({ kind: "answer", id: m.id, status: 200, json: JSON.stringify({ from: "the worker", path: m.path }) });
    }
    terminate() {}
  }
  const meta = { 'meta[name="studio-render"]': { content: "device" }, 'meta[name="studio-token"]': { content: "" } };
  const listeners = {};
  const which = { textContent: "Making your version of the song…", firstElementChild: null };  // the header's line
  const bridge = { start: null };  // what the page has had of its start (StudioBridge.snapshot)
  const sandbox = {
    navigator, matchMedia: (q) => ({ matches: q === `(prefers-color-scheme: ${scheme})` }),
    document: { querySelector: (q) => meta[q] || null, getElementById: (id) => (id === "which" ? which : null),
                readyState: "complete", addEventListener: (kind, f) => { (listeners[kind] ||= []).push(f); },
                createElement: () => ({ append() {} }), head: { append() {} }, body: { replaceChildren() {} } },  // a notice
    location: { pathname, search, hash, href: `http://studio.test${pathname}${search}${hash}`, origin: "http://studio.test" },
    localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) },
    Worker: FakeWorker, WebAssembly, URL, URLSearchParams, Response, Headers, Request, TextDecoder, TextEncoder, Blob,
    DecompressionStream: decompress ? DecompressionStream : undefined, structuredClone, clearTimeout,
    setTimeout: (f, ms) => { const t = setTimeout(f, ms); t.unref?.(); return t; },  // (a deadline never holds node open)
    setImmediate, console, crypto,
  };
  if (kept) sandbox.indexedDB = fakeIndexedDB(kept);
  sandbox.window = sandbox;
  sandbox.songbirdStudio = { toast: (text) => toasts.push(text) };
  sandbox.StudioBridge = { snapshot: () => ({ start: bridge.start }) };
  sandbox.fetch = async (input) => {
    const url = new URL(String(input), "http://studio.test");
    fetched.push(url.pathname);
    if (url.pathname === "/render/bundle.json") {
      return new Response(JSON.stringify({ v: 1, base: "/render/", pyodide: "py-0123456789abcdef", app: "app-0123456789abcdef",
        bytes: 35e6, studio_bytes: 20e6, studio: { song: "/app/songs/h.json", machine, ...(opens ? { opens } : {}) }, ...(first ? { first } : {}) }));
    }
    if (url.pathname === `/render/${FOLDER}${day}.gzip`) {
      await file;
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
  const press = () => { for (const f of listeners.pointerdown || []) f({}); };  // someone did something
  const loading = (worker, received) => worker.onmessage?.({ data: { kind: "loading", received, bytes: 20e6 } });
  return { ask, asked, workers, fetched, toasts, release, sandbox, press, which, bridge, loading };
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
  p.press();  // a person did something (New performance, say)
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

test("what the page asks of its own accord (its song with edits saved here) isn't toasted: the header says how it's going", async () => {
  const p = page();
  const start = await p.ask("/api/start");
  assert.equal(start.data.from, "the file");
  p.bridge.start = start.data;
  const song = p.ask("/api/song", { edits: { tempo: 92 } });  // the page's refresh, with the saved edits
  for (let i = 0; i < 5; i++) await tick();
  assert.deepEqual(p.toasts, []);
  p.loading(p.workers[0], 5e6);
  assert.equal(p.which.textContent, "Getting the studio ready (25%)…");
  p.release();
  assert.equal((await song).data.from, "the worker");
  p.which.firstElementChild = {};  // the header drawn from the worker's song: nothing more said there
  p.loading(p.workers[0], 10e6);
  assert.equal(p.which.textContent, "Getting the studio ready (25%)…");
});

test("on the song as it began, the header isn't written over while the worker loads", async () => {
  const p = page();
  await p.ask("/api/start");
  await p.ask("/api/song", { edits: {} });
  await tick();
  p.loading(p.workers[0], 5e6);
  assert.equal(p.which.textContent, "Making your version of the song…");
});

test("a change asked while the day's file is still coming ends the file's answers for what follows it", async () => {
  let arrive = null;
  const p = page({ file: new Promise((resolve) => { arrive = resolve; }) });
  const kept = p.ask("/api/sing/keep", { phrasing: "{}" });
  await tick();
  const start = p.ask("/api/start");
  await tick();
  arrive();
  for (let i = 0; i < 10; i++) await tick();
  p.release();
  assert.equal((await kept).data.path, "/api/sing/keep");
  assert.equal((await start).data.from, "the worker");
  assert.deepEqual(p.asked(), ["/api/sing/keep", "/api/start"]);
});

test("where the build says browser, the worker is told what this browser says of itself, and its kept salt", async () => {
  const store = new Map();
  const studioConfig = async (opts) => {
    const p = page({ machine: "browser", first: null, store, ...opts });
    p.release();
    await p.sandbox.SongbirdDevice.ready();
    return p.workers[0].posted.find((m) => m.cmd === "studio").config;
  };
  const a = await studioConfig({});
  assert.deepEqual(JSON.parse(JSON.stringify(a.browser.facts)), { languages: ["en-GB", "fr"], cores: 8, memory: 4, dark: true });
  assert.match(a.browser.salt, /^[0-9a-f]{16}$/);
  assert.equal(store.get("songbird-machine-salt"), a.browser.salt);
  // the next visit: the same singer, its screen as it is now; nothing it can't say is guessed
  const b = await studioConfig({ scheme: "no-preference", navigator: { language: "ja" } });
  assert.equal(b.browser.salt, a.browser.salt);
  assert.deepEqual(JSON.parse(JSON.stringify(b.browser.facts)), { languages: ["ja"], cores: null, memory: null, dark: null });
  // a build that names its own machine: nothing of the browser is read
  const p = page({ machine: "none", first: null });
  p.release();
  await p.sandbox.SongbirdDevice.ready();
  assert.equal(p.workers[0].posted.find((m) => m.cmd === "studio").config.browser, undefined);
});

test("a build that opens on the published version: answered at once as it; ?new is this browser's, from the worker", async () => {
  const p = page({ machine: "browser", opens: "published" });
  assert.equal((await p.ask("/api/start")).data.from, "the file");  // the published version, answered ahead
  p.release();
  await p.sandbox.SongbirdDevice.ready();
  const config = p.workers[0].posted.find((m) => m.cmd === "studio").config;
  assert.equal(config.machine, "published");
  assert.equal(config.browser, undefined);  // nothing of the browser is read for the published version
  const q = page({ machine: "browser", opens: "published", search: "?new" });
  const asked = q.ask("/api/start");  // not from the file: it was made for the published version
  q.release();
  await q.sandbox.SongbirdDevice.ready();
  assert.equal((await asked).data.from, "the worker");
  assert.ok(!q.fetched.some((f) => f.endsWith(".gzip")));
  const c = q.workers[0].posted.find((m) => m.cmd === "studio").config;
  assert.equal(c.machine, "browser");
  assert.match(c.browser.salt, /^[0-9a-f]{16}$/);
});

test("a file brought from the published version opens again on its own page, which sings as this browser", async () => {
  // read on the page on the published version (machine "published"); its page, a version's, is this browser's (the
  // fake worker's "none"): no link to read it again, so what was kept is given back to the studio as it was
  const id = "b".repeat(32);
  const version = { id, record: {}, genome: "{}", program: "p", machine: "published", shared: false };
  const p = page({ hash: `#version=${id}`, opens: "published", kept: { versions: new Map([[id, version]]) } });
  const start = p.ask("/api/start");
  p.release();
  assert.equal((await start).data.from, "the worker");
  const restored = p.workers.flatMap((w) => w.posted.filter((m) => m.cmd === "restore"));
  assert.equal(restored.length, 1);
  assert.equal(restored[0].version.id, id);
  assert.ok(!p.fetched.some((f) => f.startsWith("/api/versions")));
});

test("a shared link kept as another machine read it is fetched and read again, not given back as it was", async () => {
  const id = "c".repeat(32);
  const version = { id, record: {}, genome: "{}", program: "p", machine: "published", shared: true };
  const p = page({ pathname: `/v/${id}`, opens: "published", kept: { versions: new Map([[id, version]]) } });
  p.ask("/api/start").catch(() => {});
  p.release();
  for (let i = 0; i < 40 && !p.fetched.includes(`/api/versions/${id}`); i++) await tick();
  assert.ok(p.fetched.includes(`/api/versions/${id}`));
  assert.ok(!p.workers.some((w) => w.posted.some((m) => m.cmd === "restore")));
});
