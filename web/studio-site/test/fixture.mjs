// What the tests share: a rendition made by hand (a FLAC's head, some "audio", a packet as pack.py writes it), the
// bindings in memory (R2 with ranges, suffixes and SHA-256 checks; the rate limiter; the static assets), and
// workerd's FixedLengthStream and crypto.DigestStream for Node.
import { createHash } from "node:crypto";
import { deflateRawSync } from "node:zlib";

import { crc32 } from "../src/packet.js";
import { Shares } from "../src/worker.js";

globalThis.FixedLengthStream ??= class FixedLengthStream {
  constructor(length) {
    let seen = 0;
    const t = new TransformStream({
      transform(chunk, ctl) {
        seen += chunk.byteLength;
        if (seen > length) ctl.error(new TypeError("too long"));
        else ctl.enqueue(chunk);
      },
      flush(ctl) { if (seen !== length) ctl.error(new TypeError("too short")); },
    });
    this.readable = t.readable;
    this.writable = t.writable;
  }
};

if (!crypto.DigestStream) {
  crypto.DigestStream = class DigestStream extends WritableStream {
    constructor(algorithm) {
      const hash = createHash(algorithm.replace("-", "").toLowerCase());
      let done;
      const digest = new Promise(r => { done = r; });
      super({ write(chunk) { hash.update(chunk); }, close() { done(new Uint8Array(hash.digest()).buffer); } });
      this.digest = digest;
    }
  };
}

const le = (n, bytes) => Array.from({ length: bytes }, (_, i) => (n >>> (8 * i)) & 0xff);

export function streaminfo({ rate = 44100, channels = 2 } = {}) {
  // "fLaC" and a last-block STREAMINFO: 4096-sample blocks, 16 bits
  const info = new Uint8Array(34);
  info.set([0x10, 0x00, 0x10, 0x00], 0);
  info[10] = (rate >> 12) & 0xff;
  info[11] = (rate >> 4) & 0xff;
  info[12] = ((rate & 0xf) << 4) | ((channels - 1) << 1) | 0;
  info[13] = 0xf0;
  return new Uint8Array([0x66, 0x4c, 0x61, 0x43, 0x80, 0, 0, 34, ...info]);
}

export const MANIFEST = {
  id: "a".repeat(64), title: "Now It's by You", generation: 1, parent_id: "b".repeat(64), ancestry: ["b".repeat(64)],
  program_sha256: "c".repeat(64), python: "3.12", path: "record", name: null,
};

export function packet({ head = streaminfo(), audio = 20000, manifest = MANIFEST, entries = null, comment = "", tweak = null } = {}) {
  // the file: head, audio, then a zip whose offsets are the file's own (as pack.py appends one)
  const files = entries ?? [
    { name: "__main__.py", data: "import os; os.system('echo pwned')\n" },
    { name: "README.txt", data: "Songbird\n" },
    { name: "manifest.json", data: typeof manifest === "string" ? manifest : JSON.stringify(manifest, null, 2) + "\n" },
    { name: "genome.json", data: JSON.stringify({ title: "Now It's by You" }) },
    { name: "program/songbird/__init__.py", data: "raise SystemExit('never run')\n" },
  ];
  const body = new Uint8Array(audio).map((_, i) => (i * 7919) & 0xff);
  const out = [];
  const add = bytes => { for (const b of bytes) out.push(b); }; // (spreading a megabyte would overflow the stack)
  add(head);
  add(body);
  const central = [];
  for (const f of files) {
    const raw = typeof f.data === "string" ? new TextEncoder().encode(f.data) : f.data;
    const method = f.method ?? 8;
    const packed = method === 8 ? new Uint8Array(deflateRawSync(raw, { level: 9 })) : raw;
    const name = new TextEncoder().encode(f.name);
    const e = { flags: 0, method, crc: crc32(raw), packed: packed.length, size: raw.length, offset: out.length, name, ...(f.central || {}) };
    out.push(0x50, 0x4b, 0x03, 0x04, ...le(20, 2), ...le(e.flags, 2), ...le(method, 2), 0, 0, 0x21, 0, ...le(e.crc, 4),
             ...le(packed.length, 4), ...le(raw.length, 4), ...le(name.length, 2), ...le(0, 2), ...name);
    add(packed);
    central.push(e);
  }
  const cdStart = out.length;
  for (const e of central) {
    out.push(0x50, 0x4b, 0x01, 0x02, ...le(20, 2), ...le(20, 2), ...le(e.flags, 2), ...le(e.method, 2), 0, 0, 0x21, 0,
             ...le(e.crc, 4), ...le(e.packed, 4), ...le(e.size, 4), ...le(e.name.length, 2), 0, 0, 0, 0, 0, 0, 0, 0,
             0, 0, 0, 0, ...le(e.offset, 4), ...e.name);
  }
  const cdSize = out.length - cdStart, c = new TextEncoder().encode(comment);
  const eocd = { total: central.length, cdSize, cdStart, ...(tweak || {}) };
  out.push(0x50, 0x4b, 0x05, 0x06, 0, 0, 0, 0, ...le(eocd.total, 2), ...le(eocd.total, 2), ...le(eocd.cdSize, 4),
           ...le(eocd.cdStart, 4), ...le(c.length, 2), ...c);
  return new Uint8Array(out);
}

export const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

export class Bucket {
  // R2 as the Worker uses it: ranges ({offset, length} or {suffix}), SHA-256 checked on put, lists a page at a time
  constructor(page = 1000) { this.objects = new Map(); this.page = page; this.reads = []; this.puts = 0; }
  info(key) {
    const o = this.objects.get(key);
    return { key, size: o.bytes.byteLength, uploaded: o.uploaded, httpMetadata: { ...o.httpMetadata } };
  }
  async head(key) { return this.objects.has(key) ? this.info(key) : null; }
  async get(key, opts = {}) {
    if (!this.objects.has(key)) return null;
    let bytes = this.objects.get(key).bytes;
    const r = opts.range;
    if (r) bytes = r.suffix !== undefined ? bytes.slice(Math.max(0, bytes.length - r.suffix)) : bytes.slice(r.offset, r.offset + r.length);
    this.reads.push({ key, ...(r || {}) });
    return { ...this.info(key), body: new Blob([bytes]).stream(), arrayBuffer: async () => bytes.slice().buffer,
             text: async () => new TextDecoder().decode(bytes) };
  }
  async put(key, value, opts = {}) {
    this.puts += 1;
    const bytes = value instanceof ReadableStream ? new Uint8Array(await new Response(value).arrayBuffer())
      : typeof value === "string" ? new TextEncoder().encode(value) : new Uint8Array(value ?? 0);
    if (opts.sha256 && sha256(bytes) !== opts.sha256) throw new Error("put: the SHA-256 doesn't match");
    this.objects.set(key, { bytes, uploaded: opts.uploaded || new Date(), httpMetadata: opts.httpMetadata || {} });
    return this.info(key);
  }
  async delete(keys) { for (const k of [].concat(keys)) this.objects.delete(k); }
  async list({ prefix = "", cursor, limit } = {}) {
    const keys = this.keys(prefix), start = Number(cursor || 0), n = Math.min(limit || this.page, this.page);
    const truncated = start + n < keys.length;
    return { objects: keys.slice(start, start + n).map(k => this.info(k)), truncated, cursor: truncated ? String(start + n) : undefined };
  }
  keys(prefix = "") { return [...this.objects.keys()].filter(k => k.startsWith(prefix)).sort(); }
  age(key, days, now = Date.now()) { this.objects.get(key).uploaded = new Date(now - days * 86400e3); }
}

export class Limiter {
  // the ratelimit binding's shape: at most `max` a key (in a test, no minute ever passes)
  constructor(max) { this.max = max; this.seen = new Map(); }
  async limit({ key }) {
    this.seen.set(key, (this.seen.get(key) || 0) + 1);
    return { success: this.seen.get(key) <= this.max };
  }
}

export class Storage {
  // a Durable Object's storage, as Shares uses it; every call waits a turn, as the real one goes to disk
  constructor() { this.map = new Map(); }
  async get(key) { await null; return this.map.get(key); }
  async put(key, value) {
    await null;
    for (const [k, v] of Object.entries(typeof key === "string" ? { [key]: value } : key)) this.map.set(k, v);
  }
  async deleteAll() { await null; this.map.clear(); }
}

export function namespace(Class) {
  // a Durable Object namespace with one instance a name
  const made = new Map();
  return {
    made,
    idFromName: name => name,
    get: name => {
      if (!made.has(name)) made.set(name, new Class({ storage: new Storage() }));
      const object = made.get(name);
      return { fetch: (url, init) => object.fetch(new Request(url, init)) };
    },
  };
}

export const PAGE_HTML = "<!doctype html><title>Songbird studio</title>";

export function env(extra = {}) {
  return {
    VERSIONS: new Bucket(), UPLOADS: new Limiter(1000), REQUESTS: new Limiter(100000), UNKNOWN: new Limiter(20),
    SHARES: namespace(Shares),
    ASSETS: { fetch: async req => {
      const path = new URL(req.url).pathname;
      if (path === "/") return new Response(req.method === "HEAD" ? null : PAGE_HTML, { headers: { "Content-Type": "text/html", ETag: '"page"' } });
      return new Response("not found", { status: 404 });
    } },
    ...extra,
  };
}

export function context() {
  const waits = [];
  return { waits, waitUntil: p => waits.push(p), passThroughOnException() {} };
}
