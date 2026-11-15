// The renderer on the visitor's device (songbird/studio/renderer.js, the static site: docs/WEB-STUDIO.md, "On the
// device"): every song made in this browser, phones included, never a server; a failure said plainly, with what may
// help; a long whole song warned of and made all the same; a whole song marked while it's made, so a page the browser
// stopped can say so next time; the recording's file kept for sharing. Run with node --test.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const R = require("../songbird/studio/renderer.js");

const now = () => Promise.resolve();
const PHONE = { wasm: true, worker: true, mobile: true, memory: 2 };
const BUNDLE = { v: 1, base: "/render/", pyodide: "py-0123456789abcdef", app: "app-0123456789abcdef", bytes: 36e6, transfer: 29e6 };

function fakeWorkers(fate) {
  const made = [];
  const spawn = (url) => {
    const w = { url, terminated: false, posted: [],
      postMessage(m) {
        this.posted.push(m);
        const say = (d) => setImmediate(() => { if (!w.terminated) w.onmessage?.({ data: d }); });
        if (m.cmd === "init") return say({ kind: "ready", seconds: 5 });
        const what = JSON.parse(m.spec);
        if (fate === "memory") return say({ kind: "error", message: "MemoryError", memory: true });
        if (fate === "crash") return setImmediate(() => w.onerror?.({ message: "the worker stopped" }));
        if (fate === "oops") return say({ kind: "error", message: "ValueError: something", memory: false });
        if (m.cmd === "stems") {  // two parts, the first made again quieter, each moved here as it's made
          const file = (text) => new TextEncoder().encode(text).buffer;
          say({ kind: "progress", progress: 0.1, stage: "singing" });
          say({ kind: "part", index: 1, name: "x/01-voice.flac", crc: 1, bytes: file("loud voice"), heap: 400 });
          say({ kind: "part", index: 2, name: "x/02-guitar.flac", crc: 2, bytes: file("guitar"), heap: 420 });
          say({ kind: "part", index: 1, name: "x/01-voice.flac", crc: 3, bytes: file("voice"), heap: 410 });
          return say({ kind: "done", made: "stems", name: m.recording ? "rec" : "x", parts: ["voice", "guitar"], gain: 0.5,
            again: ["voice"], midi: { name: "x/x.mid", crc: 4, bytes: file("MThd") },
            readme: { name: "x/README.txt", crc: 5, bytes: file("hello") }, seconds: 3, heap: 430 });
        }
        say({ kind: "progress", progress: 0.5, stage: "singing" });
        say({ kind: "done", made: what.kind, key: what.key, id: `id-${what.key}`, duration: 9.2, seconds: 4.8, heap: 300,
          flac: new ArrayBuffer(8), record: what.kind === "whole" ? { generation: 1, rendered_at: "2026-09-30T12:00:00+00:00", yours: 1, program_sha256: "p" } : null });
      },
      terminate() { this.terminated = true; } };
    made.push(w);
    return w;
  };
  return { spawn, made };
}

function storage() {
  const kept = new Map();
  const log = [];
  return { kept, log, getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => { log.push(["set", k]); kept.set(k, String(v)); },
    removeItem: (k) => { log.push(["remove", k]); kept.delete(k); } };
}

function device(fate, extra = {}) {
  R.reset();
  const fake = fakeWorkers(fate);
  const asked = [];
  const ask = async (path, body) => {
    asked.push(path);
    if (path === "/render/bundle.json") return BUNDLE;
    if (path === "/api/render/spec") {
      const whole = body.section === null;
      const key = whole ? "w" : `s${body.section}`;
      // the device's studio never says "made", "server" or "too long"; if anything did, it's made here regardless
      return { key, label: key, kind: whole ? "whole" : "section", spec: `{"v":1,"kind":"${whole ? "whole" : "section"}","key":"${key}"}`,
        ...(whole ? { name: { song: "now-its-by-you", day: "2026-09-30" }, ...(extra.warn ? { warn: extra.warn } : {}) } : {}),
        ...(extra.server ? { server: true } : {}) };
    }
    throw new Error(`a server was asked: ${path}`);
  };
  const store = storage();
  const r = R.create(ask, { wait: now, env: extra.env || PHONE, spawn: fake.spawn, storage: store, device: true });
  return { r, fake, asked, store };
}

test("a phone makes the song itself: no gating, never the server", async () => {
  const { r, asked, fake } = device();
  const job = await r.preview({ edits: {}, section: 1 }).done;
  assert.equal(job.state, "done");
  assert.equal(job.where, "browser");
  assert.equal(job.heap, 300);
  assert.equal(fake.made[0].posted[0].stemCacheBytes, 32 * 2 ** 20);
  assert.ok(!asked.some((p) => p === "/api/listen" || p === "/api/record" || p.startsWith("/api/job")));
});

test("a server's word in the spec changes nothing: it's made here", async () => {
  const { r } = device(undefined, { server: true });
  const job = await r.record({ edits: {} }).done;
  assert.equal(job.state, "done");
  assert.equal(job.where, "browser");
});

test("a recording keeps its file, for sharing, and is marked while it's made", async () => {
  const { r, store } = device();
  const job = await r.record({ edits: {} }).done;
  const rec = job.result.recorded;
  assert.equal(rec.device, true);
  assert.equal(rec.name, "now-its-by-you.2026-09-30.id-w.flac");
  assert.ok(rec.file instanceof Blob);
  assert.deepEqual(store.log.filter(([, k]) => k === R.MAKING), [["set", R.MAKING], ["remove", R.MAKING]]);
  assert.equal(store.kept.has(R.MAKING), false);
});

test("failures are said plainly, with what may help, and never sent to a server", async () => {
  for (const [fate, said] of [["memory", /ran out of memory in this browser. A shorter version .* or a computer/],
    ["crash", /the browser stopped it, perhaps for want of memory/], ["oops", /went wrong in this browser \(ValueError: something\)\. Try again/]]) {
    const { r, asked, store } = device(fate);
    const job = await r.record({ edits: {} }).done;
    assert.equal(job.state, "failed", fate);
    assert.match(job.error, said);
    assert.ok(!asked.includes("/api/record"));
    assert.equal(store.kept.has(R.MAKING), false);  // a failure it heard of isn't a crash to say next time
  }
});

test("a long whole song is warned of, and made", async () => {
  const { r } = device(undefined, { warn: "a long version (6.1 minutes), which may need more memory than a browser has" });
  const heard = [];
  const job = await r.record({ edits: {} }, (j) => heard.push(j.stage)).done;
  assert.equal(job.state, "done");
  assert.ok(heard.some((s) => /a long version \(6\.1 minutes\)/.test(s)));
});

test("a browser without workers is told so, plainly", async () => {
  const { r } = device(undefined, { env: { wasm: true, worker: false, mobile: true, memory: null } });
  const job = await r.preview({ edits: {}, section: 0 }).done;
  assert.equal(job.state, "failed");
  assert.match(job.error, /can't run the singer.*Another browser, or a computer, may/);
});

// a stored zip's entries, read back as any unzipper reads them (the central directory, then each local header)
async function unzipped(blob) {
  const buf = Buffer.from(await blob.arrayBuffer());
  const end = buf.length - 22;
  assert.equal(buf.readUInt32LE(end), 0x06054b50);
  const count = buf.readUInt16LE(end + 10);
  let at = buf.readUInt32LE(end + 16);
  const out = [];
  for (let i = 0; i < count; i++) {
    assert.equal(buf.readUInt32LE(at), 0x02014b50);
    const crc = buf.readUInt32LE(at + 16), size = buf.readUInt32LE(at + 20), n = buf.readUInt16LE(at + 28);
    const name = buf.toString("utf8", at + 46, at + 46 + n);
    const local = buf.readUInt32LE(at + 42);
    assert.equal(buf.readUInt32LE(local), 0x04034b50);
    assert.equal(buf.readUInt32LE(local + 14), crc);
    const start = local + 30 + buf.readUInt16LE(local + 26);
    out.push({ name, crc, text: buf.toString("utf8", start, start + size) });
    at += 46 + n;
  }
  return out;
}

test("the stems are made a part at a time in a worker of their own, and zipped here", async () => {
  const { r, fake, store, asked } = device();
  const heard = [];
  const answer = { state: "device", key: "w", name: "x.stems.zip", spec: '{"v":1,"kind":"stems","key":"w"}' };
  const job = await r.stems(answer, (j) => heard.push(j.stage)).done;
  assert.equal(job.state, "done", job.error);
  assert.equal(job.name, "x.stems.zip");
  assert.deepEqual(job.parts, ["voice", "guitar"]);
  assert.equal(job.heap, 430);
  const worker = fake.made[0];
  assert.equal(worker.terminated, true);  // its heap goes with it
  assert.equal(worker.posted[1].cmd, "stems");
  assert.equal(worker.posted[1].recording, null);
  assert.ok(heard.includes("singing"));
  assert.deepEqual(store.log.filter(([, k]) => k === R.MAKING), [["set", R.MAKING], ["remove", R.MAKING]]);
  assert.ok(!asked.some((p) => p.startsWith("/api/")));
  const blob = await (await fetch(job.url)).blob();
  assert.deepEqual(await unzipped(blob), [
    { name: "x/01-voice.flac", crc: 3, text: "voice" }, { name: "x/02-guitar.flac", crc: 2, text: "guitar" },
    { name: "x/x.mid", crc: 4, text: "MThd" }, { name: "x/README.txt", crc: 5, text: "hello" }]);
});

test("the stems name the recording the page made of the same version", async () => {
  const { r, fake } = device();
  const made = await r.record({ edits: {} }).done;
  const job = await r.stems({ state: "device", key: made.key, spec: '{"v":1,"kind":"stems","key":"w"}' }).done;
  assert.equal(job.state, "done");
  assert.deepEqual(fake.made[1].posted[1].recording, [made.result.recorded.name, made.result.recorded.id]);
  assert.equal(job.name, "rec.stems.zip");
});

test("stems that run out of memory are said plainly", async () => {
  const { r } = device("memory");
  const job = await r.stems({ state: "device", key: "w", spec: '{"v":1,"kind":"stems","key":"w"}' }).done;
  assert.equal(job.state, "failed");
  assert.match(job.error, /ran out of memory in this browser/);
});
