// The worker's routes against fake bindings (KV, R2 and the built site in memory, R2 listing three keys
// a page so every listing turns pages): joining, takes, words, a singer's own page, deleting and
// withdrawing, singing closing, the artist's API and the hourly purge.
// npm test
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";

import { wavBytes } from "../../../tools/karaoke.js";

let isolates = 0;
async function load() {
  // the worker as a new isolate runs it: nothing kept from another test's site or bucket
  return (await import(`../src/worker.js?isolate=${++isolates}`)).default;
}

globalThis.FixedLengthStream ??= class FixedLengthStream {
  // workerd's: a stream that must carry exactly `length` bytes
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

class KV {
  constructor() { this.data = new Map(); }
  async get(key, kind) {
    const e = this.data.get(key);
    return e === undefined ? null : kind === "json" ? JSON.parse(e.value) : e.value;
  }
  async put(key, value, opts = {}) { this.data.set(key, { value: String(value), metadata: opts.metadata ?? null }); }
  async delete(key) { this.data.delete(key); }
  async list({ prefix = "", cursor, limit = 1000 } = {}) {
    const names = [...this.data.keys()].filter(k => k.startsWith(prefix)).sort();
    const start = Number(cursor || 0), more = start + limit < names.length;
    return { keys: names.slice(start, start + limit).map(name => ({ name, ...(this.data.get(name).metadata ? { metadata: this.data.get(name).metadata } : {}) })),
             list_complete: !more, cursor: more ? String(start + limit) : undefined };
  }
}

class Bucket {
  constructor(page = 3) { this.objects = new Map(); this.page = page; }
  info(key) {
    const o = this.objects.get(key);
    return { key, size: o.bytes.byteLength, uploaded: o.uploaded, customMetadata: { ...o.customMetadata }, httpMetadata: { ...o.httpMetadata } };
  }
  async head(key) { return this.objects.has(key) ? this.info(key) : null; }
  async get(key, opts = {}) {
    if (!this.objects.has(key)) return null;
    let bytes = this.objects.get(key).bytes;
    if (opts.range) bytes = bytes.slice(opts.range.offset, opts.range.offset + opts.range.length);
    return { ...this.info(key), body: new Blob([bytes]).stream(), text: async () => new TextDecoder().decode(bytes),
             json: async () => JSON.parse(new TextDecoder().decode(bytes)) };
  }
  async put(key, value, opts = {}) {
    const bytes = value instanceof ReadableStream ? new Uint8Array(await new Response(value).arrayBuffer())
      : typeof value === "string" ? new TextEncoder().encode(value) : new Uint8Array(value ?? 0);
    if (opts.sha256 && createHash("sha256").update(bytes).digest("hex") !== opts.sha256) throw new Error("put: the SHA-256 doesn't match");
    this.objects.set(key, { bytes, uploaded: new Date(), customMetadata: opts.customMetadata || {}, httpMetadata: opts.httpMetadata || {} });
    return this.info(key);
  }
  async delete(keys) { for (const k of [].concat(keys)) this.objects.delete(k); }
  async list({ prefix = "", cursor, include = [] } = {}) {
    const keys = this.keys(prefix), start = Number(cursor || 0), truncated = start + this.page < keys.length;
    return { objects: keys.slice(start, start + this.page).map(k => {
      const o = this.info(k);
      if (!include.includes("customMetadata")) delete o.customMetadata;
      return o;
    }), truncated, cursor: truncated ? String(start + this.page) : undefined };
  }
  keys(prefix = "") { return [...this.objects.keys()].filter(k => k.startsWith(prefix)).sort(); }
}

const section = (index, name, start, end, extra = {}) => ({ index, name, start, end, sung: false, ...extra });
const LYRICS_A = {
  guide: "aaaaaaaaaaaa", spec: { id: "a.k0.t100", set: "a", key: 0, tempo: 100 }, duration: 60, lines: [],
  sections: [section(0, "intro", 0, 5), section(1, "verse", 5, 20, { sung: true, nth: 1, label: "They saved it as numbers and sent it by wire,", window: [2.5, 21] }),
             section(2, "turn", 20, 25), section(3, "refrain", 25, 40, { sung: true, nth: 1, label: "Now it’s by you — Zoë’s 名前", window: [22.5, 41] }),
             section(4, "tag", 40, 60, { sung: true, nth: 1, label: "By you", window: [37.5, 60] })],
};
const LYRICS_B = { ...LYRICS_A, guide: "bbbbbbbbbbbb", spec: { id: "b.k0.t100", set: "b", key: 0, tempo: 100 } };
const SONG = {
  v: 2, title: "Now It's By You", song: "h-now-its-by-you", consent: "c0c0c0c0c0c0", words_release: "d1d1d1d1d1d1",
  sets: [{ id: "a", name: "Set A", about: "" }, { id: "b", name: "Set B", about: "" }], keys: [0], tempos: [100], mixes: ["melody", "full"],
  default: { set: "a", key: 0, tempo: 100, mix: "melody" },
  guides: {
    "a.k0.t100": { guide: "aaaaaaaaaaaa", lyrics: "a.k0.t100.json", duration: 60,
                   mixes: { melody: { file: "a.k0.t100.melody.mp3", env: [0, 0.1] }, full: { file: "a.k0.t100.full.mp3", env: [0, 0.2] } } },
    "b.k0.t100": { guide: "bbbbbbbbbbbb", lyrics: "b.k0.t100.json", duration: 60, mixes: { melody: { file: "b.k0.t100.melody.mp3", env: [] } } },
  },
  max_seconds: 120, built: "2026-09-26T20:00:00+00:00",
};
const SITE = {
  "/song/song.json": JSON.stringify(SONG), "/song/a.k0.t100.json": JSON.stringify(LYRICS_A), "/song/b.k0.t100.json": JSON.stringify(LYRICS_B),
  "/song/a.k0.t100.melody.mp3": "mp3: a melody", "/song/a.k0.t100.full.mp3": "mp3: a full", "/song/b.k0.t100.melody.mp3": "mp3: b melody",
  "/index.html": "<!doctype html><title>sing</title>", "/yours.html": "<!doctype html><title>yours</title>", "/yours.js": "// yours",
};

const ADMIN = "x".repeat(40);
const LATER = "2099-01-01T00:00:00-07:00", EARLIER = "2001-01-01T00:00:00-07:00";

class Limiter {
  // the ratelimit binding's shape: at most `limit` a key (for a test, never a minute passes)
  constructor(limit) { this.max = limit; this.seen = new Map(); }
  async limit({ key }) {
    this.seen.set(key, (this.seen.get(key) || 0) + 1);
    return { success: this.seen.get(key) <= this.max };
  }
}

function env(extra = {}) {
  const files = extra.files || SITE;
  return {
    INVITES: new KV(), TAKES: new Bucket(), ADMIN_TOKEN: ADMIN, CLOSES_AT: LATER, DELETE_BY: LATER,
    UPLOADS: new Limiter(6), REQUESTS: new Limiter(10000), UNKNOWN: new Limiter(10),
    ASSETS: { fetch: async req => {
      const path = new URL(req.url).pathname;
      return Object.hasOwn(files, path) ? new Response(files[path]) : new Response("no", { status: 404 });
    } },
    ...extra,
  };
}

async function call(w, e, path, init = {}) {
  return w.fetch(new Request(`https://songbird.test${path}`, init), e);
}

async function admin(w, e, method, path, body) {
  const r = await call(w, e, `/api/admin/${path}`, { method, headers: { Authorization: `Bearer ${ADMIN}` },
                                                     body: body === undefined ? undefined : JSON.stringify(body) });
  return { status: r.status, data: await r.json() };
}

async function invitation(w, e, extra = {}) {
  return (await admin(w, e, "POST", "invites", { count: 1, ...extra })).data.invites[0].token;
}

async function join(w, e, token, extra = {}, headers = {}) {
  const body = { email: "ana@example.org", name: "Ana María", credit: true, notify: false,
                 consent: { agreed: true, at: new Date().toISOString(), text: SONG.consent }, ...extra };
  const r = await call(w, e, `/api/join/${token}`, { method: "POST", body: JSON.stringify(body), headers });
  return { status: r.status, data: await r.json() };
}

function wav(seconds, rate = 8000) {
  const samples = new Float32Array(Math.round(seconds * rate)).map((_, i) => Math.sin(i / 7) * 0.3);
  const bytes = new Uint8Array(wavBytes(samples, rate));
  return { bytes, sha256: createHash("sha256").update(bytes).digest("hex"), rate };
}

async function send(w, e, sid, { seconds = 40, rate = 8000, headers = {}, ...extra } = {}) {
  const take = wav(seconds, rate);
  const info = { song: SONG.song, spec: "a.k0.t100", guide: "aaaaaaaaaaaa", mix: "melody", rate, from_s: 0, to_s: 60,
                 shift_ms: 12, device_ms: 40, sha256: take.sha256, ...extra };
  const r = await call(w, e, `/api/take/${sid}`, {
    method: "PUT", body: take.bytes,
    headers: { "Content-Type": "audio/wav", "Content-Length": String(take.bytes.byteLength),
               "X-Take-Info": Buffer.from(JSON.stringify(info)).toString("base64url"), ...headers },
  });
  return { status: r.status, data: await r.json(), take };
}

async function page(w, e, sid) {
  const r = await call(w, e, `/api/yours/${sid}`);
  return { status: r.status, data: await r.json() };
}

test("an invitation closed in R2 is closed, whatever KV still says", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e);
  await e.TAKES.put(`closed/${token}`, "", { customMetadata: { state: "revoked", at: "2026-09-26T10:00:00.000Z" } });
  assert.equal(JSON.parse((await e.INVITES.get(`invite:${token}`))).state, "open"); // KV hasn't heard yet
  assert.equal((await (await call(w, e, `/api/invite/${token}`)).json()).state, "revoked");
  assert.equal((await call(w, e, `/i/${token}`)).status, 410);
  assert.equal((await call(w, e, `/api/guide/${token}/a.k0.t100/melody`)).status, 410);
  assert.equal((await join(w, e, token)).status, 410);

  const open = await invitation(w, e);
  const state = await (await call(w, e, `/api/invite/${open}`)).json();
  // people: how many can join with it (a personal link: one person, on up to three devices)
  assert.deepEqual(state, { state: "open", expires: state.expires, limit: 30, closes: LATER, people: 3, personal: true, joined: 0, room: 3,
                            full: false });
  const sing = await call(w, e, `/i/${open}`);
  assert.equal(sing.status, 200);
  assert.match(sing.headers.get("Content-Security-Policy"), /script-src 'self'/);
  assert.equal(sing.headers.get("Strict-Transport-Security"), "max-age=15552000");
  assert.equal((await call(w, e, `/i/${open}`, { method: "HEAD" })).status, 200); // link previews look first
  // the song, one guide's words, one guide: only to an open invitation, and only what's in the song
  assert.equal((await (await call(w, e, `/api/song/${open}`)).json()).v, 2);
  assert.equal((await (await call(w, e, `/api/lyrics/${open}/a.k0.t100`)).json()).guide, "aaaaaaaaaaaa");
  const mp3 = await call(w, e, `/api/guide/${open}/a.k0.t100/full`);
  assert.equal(mp3.headers.get("Content-Type"), "audio/mpeg");
  assert.equal(await mp3.text(), "mp3: a full");
  for (const path of [`/api/guide/${open}/b.k0.t100/full`, `/api/guide/${open}/c.k0.t100/melody`, `/api/lyrics/${open}/__proto__`,
                      `/api/guide/${open}/a.k0.t100/constructor`]) {
    assert.equal((await call(w, e, path)).status, 404, path);
  }
});

test("unknown invitations and pages, the song's files and the admin API give nothing away", async () => {
  const w = await load(), none = env();
  assert.equal((await call(w, none, `/i/${"Z".repeat(24)}`)).status, 404);
  assert.equal((await call(w, none, "/i/../../etc/passwd")).status, 404);
  assert.equal((await call(w, none, `/y/${"Z".repeat(24)}`)).status, 404);
  assert.equal((await call(w, none, `/api/yours/${"Z".repeat(24)}`)).status, 404);
  assert.equal((await call(w, none, `/api/take/${"Z".repeat(24)}`, { method: "PUT" })).status, 404);
  for (const path of ["/song/song.json", "/song/worker.json", "/yours.html", "/index.html", "/api/song/x"]) {
    assert.equal((await call(w, none, path)).status, 404, path);
  }
  assert.equal((await call(w, none, "/yours.js")).status, 200); // the pages' own scripts are public
  assert.equal((await call(w, none, "/api/admin/invites", { headers: { Authorization: `Bearer ${"y".repeat(40)}` } })).status, 401);
  assert.equal((await call(w, { ...none, ADMIN_TOKEN: undefined }, "/api/admin/invites")).status, 503); // no secret set yet
});

test("joining: a personal link admits three joins, the same email is the same person, and the email is kept apart", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e);
  const first = await join(w, e, token);
  assert.equal(first.status, 200);
  const sid = first.data.singer;
  assert.deepEqual(first.data, { singer: sid, page: `/y/${sid}`, set: "a", limit: 30 });
  const record = await e.INVITES.get(`singer:${sid}`, "json");
  assert.equal(record.person, sid);
  assert.equal(record.name, "Ana María");
  assert.deepEqual(record.consent.text, SONG.consent);
  assert.ok(!JSON.stringify([...e.INVITES.data]).includes("ana@example.org")); // never in KV
  assert.equal(await (await e.TAKES.get(`emails/${sid}`)).text(), "ana@example.org");
  // the same person on their phone, with the email in capitals: another page, the same person
  const phone = await join(w, e, token, { email: "ANA@example.org " });
  assert.notEqual(phone.data.singer, sid);
  assert.equal((await e.INVITES.get(`singer:${phone.data.singer}`, "json")).person, sid);
  const other = await join(w, e, token, { email: "jo@example.org", name: "" });
  assert.equal((await e.INVITES.get(`singer:${other.data.singer}`, "json")).person, other.data.singer);
  const full = await join(w, e, token, { email: "ana@example.org" });
  assert.equal(full.status, 403);
  assert.equal(full.data.error, "full");
  assert.deepEqual(await (await call(w, e, `/api/invite/${token}`)).json(),
                   { ...(await (await call(w, e, `/api/invite/${token}`)).json()), joined: 3, room: 0, full: true });

  const fresh = await invitation(w, e);
  assert.equal((await join(w, e, fresh, { email: "ana at example.org" })).status, 400);
  assert.equal((await join(w, e, fresh, { consent: { agreed: true, at: new Date().toISOString(), text: "000000000000" } })).data.error, "join");
  assert.equal((await join(w, e, fresh, { consent: undefined })).status, 400);
  const bad = await call(w, e, `/api/join/${fresh}`, { method: "POST", body: "{not json" });
  assert.equal(bad.status, 400);
  const huge = await call(w, e, `/api/join/${fresh}`, { method: "POST", body: JSON.stringify({ name: "x".repeat(10000) }) });
  assert.equal(huge.status, 400);
  assert.equal((await join(w, e, fresh)).status, 200); // none of that used up a join
});

test("a group link admits its people, and one address joins only so often", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 2 });
  assert.equal((await join(w, e, token, { email: "a@example.org" })).status, 200);
  assert.equal((await join(w, e, token, { email: "b@example.org" })).status, 200);
  assert.equal((await join(w, e, token, { email: "c@example.org" })).data.error, "full");

  const big = await invitation(w, e, { people: 100 });
  const from = { "CF-Connecting-IP": "203.0.113.9" };
  for (let i = 0; i < 20; i++) assert.equal((await join(w, e, big, { email: `p${i}@example.org` }, from)).status, 200);
  const more = await join(w, e, big, { email: "late@example.org" }, from);
  assert.equal(more.status, 429);
  assert.equal((await join(w, e, big, { email: "late@example.org" }, { "CF-Connecting-IP": "198.51.100.7" })).status, 200);
  // what's kept to count them: a digest of the address, never the address
  assert.ok(e.TAKES.keys("limits/").length > 0);
  assert.ok(!e.TAKES.keys().some(k => k.includes("203.0.113.9")));
  // a choir on one Wi-Fi: the artist raises the limit (JOINS_AN_HOUR in [vars])
  const choir = { ...e, JOINS_AN_HOUR: "25" };
  assert.equal((await join(w, choir, big, { email: "p20@example.org" }, from)).status, 200);
});

test("a new singer is given the set with the least singing so far", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 50 });
  const sets = [];
  for (let i = 0; i < 4; i++) sets.push((await join(w, e, token, { email: `s${i}@example.org` })).data.set);
  assert.deepEqual(sets, ["a", "b", "a", "b"]); // nothing sung yet: in turn
  // set a has been sung a lot (the takes' seconds, as their page lists them), set b not at all
  for (let i = 0; i < 5; i++) {
    await e.TAKES.put(`takes/${"S".repeat(24)}/20260926T20000${i}Z-abcdef.wav`, "", { customMetadata: { spec: "a.k0.t100", seconds: "150" } });
  }
  const w2 = await load(); // an isolate that hasn't counted yet
  const later = [];
  for (let i = 0; i < 3; i++) later.push((await join(w2, e, token, { email: `t${i}@example.org` })).data.set);
  assert.deepEqual(later, ["b", "b", "b"]);
});

test("only the pages themselves join, send takes or words, or delete and withdraw", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 5 });
  const cross = { "Sec-Fetch-Site": "cross-site" };
  assert.equal((await join(w, e, token, {}, cross)).status, 403);
  const sid = (await join(w, e, token, {}, { "Sec-Fetch-Site": "same-origin" })).data.singer;
  assert.equal((await send(w, e, sid, { headers: cross })).status, 403);
  for (const [method, path] of [["POST", `/api/words/${sid}`], ["POST", `/api/done/${sid}`], ["POST", `/api/yours/${sid}/delete`],
                                ["POST", `/api/yours/${sid}/withdraw`], ["DELETE", `/api/yours/${sid}/take/20260926T200000Z-abcdef`]]) {
    assert.equal((await call(w, e, path, { method, headers: cross, body: method === "POST" ? "{}" : undefined })).status, 403, path);
  }
  assert.equal((await page(w, e, sid)).data.state, "open"); // nothing happened
});

test("a whole-song take and a one-section take, kept with their sidecars; a bad window is refused", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 3, limit: 5 });
  const sid = (await join(w, e, token)).data.singer;
  const whole = await send(w, e, sid, { seconds: 58 });
  assert.equal(whole.status, 200);
  assert.deepEqual(whole.data, { ok: true, take: 1, limit: 5 });
  const verse = await send(w, e, sid, { seconds: 18.5, section: 1, from_s: 2.5, to_s: 21, mix: "full" });
  assert.equal(verse.status, 200);
  assert.equal(verse.data.take, 2);

  const keys = e.TAKES.keys(`takes/${sid}/`);
  assert.equal(keys.length, 4);
  const sidecars = {};
  for (const k of keys.filter(k => k.endsWith(".json"))) sidecars[k.slice(0, -5)] = JSON.parse(await (await e.TAKES.get(k)).text());
  const [id, sidecar] = Object.entries(sidecars).find(([, s]) => s.section === 1);
  assert.equal(Object.values(sidecars).find(s => s.section === null).seconds, 58);
  const { received, consent, ...rest } = sidecar;
  assert.deepEqual(rest, { song: "h-now-its-by-you", spec: "a.k0.t100", guide: "aaaaaaaaaaaa", mix: "full", rate: 8000, seconds: 18.5,
                           from_s: 2.5, to_s: 21, section: 1, part: "Verse 1", label: "They saved it as numbers and sent it by wire,",
                           sha256: verse.take.sha256, shift_ms: 12, device_ms: 40, sid, person: sid, invite: token, name: "Ana María",
                           credit: true, bytes: verse.take.bytes.byteLength, take: 2 });
  assert.equal(consent.text, SONG.consent); // the release they agreed to on joining
  assert.ok(!JSON.stringify(sidecar).includes("example.org")); // never their email
  const bytes = (await e.TAKES.get(`${id}.wav`)).body;
  assert.deepEqual(new Uint8Array(await new Response(bytes).arrayBuffer()), verse.take.bytes);

  // refused, each with a reason the page can show, and nothing kept
  const refusals = [
    [{ seconds: 18.5, section: 1, from_s: 10, to_s: 21 }, /doesn't match/],
    [{ seconds: 18.5, section: 2, from_s: 20, to_s: 25 }, /no such part/],
    [{ seconds: 30, section: 1, from_s: 2.5, to_s: 21 }, /longer than its part/],
    [{ seconds: 40, from_s: 12 }, /out of range/],
    [{ seconds: 40, spec: "b.k0.t100" }, /reload/], // b's guide isn't a's score
    [{ seconds: 40, spec: "b.k0.t100", guide: "bbbbbbbbbbbb", mix: "full" }, /no such guide/],
  ];
  const other = (await join(w, e, token, { email: "jo@example.org" })).data.singer; // six tries a minute each
  for (const [extra, reason] of refusals) {
    const r = await send(w, e, other, extra);
    assert.equal(r.status, 400, JSON.stringify(extra));
    assert.match(r.data.message, reason);
  }
  assert.equal(e.TAKES.keys(`takes/${other}/`).length, 0);
  assert.equal((await send(w, e, other)).status, 429); // a seventh within the minute
});

test("a take must say how long it is, arrive whole, and fit in its singer's limit", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { limit: 1 });
  const sid = (await join(w, e, token)).data.singer;
  const r = await call(w, e, `/api/take/${sid}`, { method: "PUT", body: new ReadableStream(), duplex: "half",
                                                   headers: { "Content-Type": "audio/wav", "X-Take-Info": "e30" } });
  assert.equal(r.status, 411);
  const damaged = await send(w, e, sid, { sha256: "0".repeat(64) });
  assert.equal(damaged.status, 400);
  assert.equal(damaged.data.error, "damaged"); // R2 checks it against the page's checksum
  assert.equal((await send(w, e, sid, { headers: { "Content-Type": "text/plain" } })).status, 415);
  assert.equal((await send(w, e, sid, { headers: { "X-Take-Info": "not-json" } })).status, 400);
  assert.equal((await send(w, e, sid)).status, 200);
  const over = await send(w, e, sid);
  assert.equal(over.status, 403);
  assert.equal(over.data.error, "limit");
});

test("words for the song, under their own release", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e);
  const sid = (await join(w, e, token)).data.singer;
  const words = async (text, release = { agreed: true, at: new Date().toISOString(), text: SONG.words_release }) => {
    const r = await call(w, e, `/api/words/${sid}`, { method: "POST", body: JSON.stringify({ text, release }) });
    return { status: r.status, data: await r.json() };
  };
  assert.deepEqual((await words("A verse about the wire,\nand the river.")).data, { ok: true, words: 1 });
  assert.equal((await words("again", { agreed: true, at: new Date().toISOString(), text: SONG.consent })).status, 400); // the other release
  assert.equal((await words("again", { agreed: false })).status, 400);
  assert.equal((await words("x".repeat(4001))).status, 400);
  assert.equal((await words("   ")).status, 400);
  const kept = JSON.parse(await (await e.TAKES.get(e.TAKES.keys(`words/${sid}/`)[0])).text());
  assert.deepEqual({ ...kept, at: null, release: null }, { sid, person: sid, at: null, text: "A verse about the wire,\nand the river.",
                                                          release: null, name: "Ana María", credit: true });
  for (let i = 1; i < 20; i++) await e.TAKES.put(`words/${sid}/2026092${i % 10}T00000${i % 10}Z-aaaa${String.fromCharCode(97 + i)}a.json`, "{}");
  assert.equal((await words("one too many")).status, 403); // twenty at most
  assert.equal((await words("and another")).status, 429); // and six tries a minute
});

test("a singer's own page: what they sent, played in ranges and downloaded, and downloading deletes nothing", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e);
  const sid = (await join(w, e, token)).data.singer;
  const html = await call(w, e, `/y/${sid}`);
  assert.equal(html.status, 200);
  assert.equal(await html.text(), SITE["/yours.html"]);
  assert.match(html.headers.get("Content-Security-Policy"), /default-src 'none'/);
  assert.equal(html.headers.get("X-Robots-Tag"), "noindex");
  assert.equal(html.headers.get("Referrer-Policy"), "no-referrer");
  assert.equal(html.headers.get("Cache-Control"), "no-store");

  const empty = (await page(w, e, sid)).data;
  assert.equal(empty.state, "open");
  assert.deepEqual([empty.takes, empty.files, empty.words], [[], [], []]);
  assert.equal(empty.sing_more, `/i/${token}#s=${sid}`);
  const verse = await send(w, e, sid, { seconds: 18.5, section: 1, from_s: 2.5, to_s: 21 });
  await send(w, e, sid, { seconds: 50 });
  await call(w, e, `/api/words/${sid}`, { method: "POST", body: JSON.stringify({ text: "A line", release: { agreed: true, at: new Date().toISOString(), text: SONG.words_release } }) });
  await admin(w, e, "PUT", `file/${sid}/a.k0.t100.version.mp3`); // (a body-less upload is refused: see below)
  const up = await call(w, e, `/api/admin/file/${sid}/a.k0.t100.version.mp3?spec=a.k0.t100`, {
    method: "PUT", body: "mp3 bytes", headers: { Authorization: `Bearer ${ADMIN}`, "Content-Length": "9", "Content-Type": "audio/mpeg" } });
  assert.deepEqual(await up.json(), { ok: true, name: "a.k0.t100.version.mp3", bytes: 9 });

  const mine = (await page(w, e, sid)).data;
  assert.deepEqual(Object.keys(mine).sort(), ["can_withdraw", "closes", "created", "credit", "delete_by", "done", "files", "limit", "name",
                                              "notify", "sing_more", "state", "takes", "words"]);
  assert.deepEqual([mine.name, mine.credit, mine.notify, mine.can_withdraw, mine.done, mine.closes], ["Ana María", true, false, true, null, LATER]);
  assert.equal(mine.takes.length, 2);
  const t1 = mine.takes.find(t => t.section === 1), t2 = mine.takes.find(t => t !== t1); // (two in one second: either order)
  assert.deepEqual({ ...t1, received: null, id: null }, { id: null, seconds: 18.5, section: 1, name: "Verse 1",
                                                          label: "They saved it as numbers and sent it by wire,", spec: "a.k0.t100",
                                                          mix: "melody", received: null, bytes: verse.take.bytes.byteLength });
  assert.equal(t2.section, null);
  assert.equal(t2.name, null);
  assert.deepEqual(mine.files.map(f => [f.name, f.kind, f.about, f.bytes]), [["a.k0.t100.version.mp3", "version", "Your version of the song", 9]]);
  assert.deepEqual(mine.words.map(x => x.text), ["A line"]);
  // a lyric's line in any script comes back as it was (R2's metadata holds it percent-encoded)
  assert.equal((await send(w, e, sid, { seconds: 18, section: 3, from_s: 22.5, to_s: 41 })).status, 200);
  assert.equal((await page(w, e, sid)).data.takes.find(t => t.section === 3).label, "Now it’s by you — Zoë’s 名前");

  // play it (Safari asks for two bytes first), download it, and it's still there
  const first = await call(w, e, `/api/yours/${sid}/take/${t1.id}`, { headers: { Range: "bytes=0-1" } });
  assert.equal(first.status, 206);
  assert.equal(first.headers.get("Content-Range"), `bytes 0-1/${verse.take.bytes.byteLength}`);
  assert.deepEqual(new Uint8Array(await first.arrayBuffer()), verse.take.bytes.slice(0, 2));
  const all = await call(w, e, `/api/yours/${sid}/take/${t1.id}?download=1`);
  assert.equal(all.status, 200);
  assert.equal(all.headers.get("Content-Type"), "audio/wav");
  assert.match(all.headers.get("Content-Disposition"), /^attachment; filename="songbird-take-/);
  assert.deepEqual(new Uint8Array(await all.arrayBuffer()), verse.take.bytes);
  assert.equal((await call(w, e, `/api/yours/${sid}/take/${t1.id}`, { headers: { Range: "bytes=99999999-" } })).status, 416);
  const file = await call(w, e, `/api/yours/${sid}/file/a.k0.t100.version.mp3`);
  assert.equal(await file.text(), "mp3 bytes");
  assert.equal(file.headers.get("Content-Type"), "audio/mpeg");
  const adminCopy = await call(w, e, `/api/admin/take/takes/${sid}/${t1.id}.wav`, { headers: { Authorization: `Bearer ${ADMIN}` } });
  assert.deepEqual(new Uint8Array(await adminCopy.arrayBuffer()), verse.take.bytes);
  assert.equal((await page(w, e, sid)).data.takes.length, 3); // no download deleted anything
  assert.equal((await call(w, e, `/api/yours/${sid}/take/../../x`)).status, 404);
  assert.equal((await call(w, e, `/api/yours/${sid}/file/..%2Fx.mp3`)).status, 404);
});

test("deleting a take, or all of them, leaves word for the artist's copies and keeps their words", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e);
  const sid = (await join(w, e, token)).data.singer;
  await send(w, e, sid, { seconds: 18.5, section: 1, from_s: 2.5, to_s: 21 });
  await send(w, e, sid, { seconds: 50 });
  await call(w, e, `/api/words/${sid}`, { method: "POST", body: JSON.stringify({ text: "A line", release: { agreed: true, at: new Date().toISOString(), text: SONG.words_release } }) });
  await e.TAKES.put(`files/${sid}/a.k0.t100.version.mp3`, "mp3");
  const [one, two] = (await page(w, e, sid)).data.takes;

  const del = await call(w, e, `/api/yours/${sid}/take/${one.id}`, { method: "DELETE" });
  assert.deepEqual(await del.json(), { deleted: one.id });
  const after = (await page(w, e, sid)).data;
  assert.deepEqual(after.takes.map(t => t.id), [two.id]);
  assert.deepEqual(after.files, []); // a version made with it would still hold it
  assert.equal((await call(w, e, `/api/yours/${sid}/take/${one.id}`, { method: "DELETE" })).status, 404);
  let gone = (await admin(w, e, "GET", "gone")).data.gone;
  assert.deepEqual(gone.map(g => [g.singer, g.what, g.take]), [[sid, "deleted", `takes/${sid}/${one.id}`]]);

  const all = await call(w, e, `/api/yours/${sid}/delete`, { method: "POST" });
  assert.deepEqual(await all.json(), { deleted: 1 });
  const none = (await page(w, e, sid)).data;
  assert.deepEqual([none.takes, none.files, none.state, none.words.length], [[], [], "open", 1]); // they may still sing, and their words stay
  gone = (await admin(w, e, "GET", "gone")).data.gone;
  // (two within a millisecond may list either way round: applying them never depends on the order)
  assert.deepEqual(gone.map(g => [g.what, g.take]).sort(), [["deleted", `takes/${sid}/${one.id}`], ["deleted", null]].sort());
  assert.ok(gone.every(g => Date.parse(g.at) > 0));
  assert.equal((await send(w, e, sid)).status, 200); // and sing again
});

test("withdrawing deletes everything, and is only possible until singing closes", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 5 });
  const sid = (await join(w, e, token, { notify: true })).data.singer;
  const stays = (await join(w, e, token, { email: "jo@example.org", name: "Jo" })).data.singer;
  await send(w, e, sid);
  await send(w, e, stays);
  await call(w, e, `/api/words/${sid}`, { method: "POST", body: JSON.stringify({ text: "A line", release: { agreed: true, at: new Date().toISOString(), text: SONG.words_release } }) });
  await e.TAKES.put(`files/${sid}/a.k0.t100.version.mp3`, "mp3");

  const r = await call(w, e, `/api/yours/${sid}/withdraw`, { method: "POST" });
  assert.deepEqual(await r.json(), { state: "withdrawn" });
  for (const prefix of [`takes/${sid}/`, `files/${sid}/`, `words/${sid}/`, `emails/${sid}`, `joined/${token}/${sid}`]) {
    assert.deepEqual(e.TAKES.keys(prefix), [], prefix);
  }
  assert.equal(e.TAKES.keys(`takes/${stays}/`).length, 2); // someone else's stay
  const record = await e.INVITES.get(`singer:${sid}`, "json");
  assert.equal(record.name, undefined);
  assert.ok(record.withdrawn);
  const mine = (await page(w, e, sid)).data;
  assert.deepEqual([mine.state, mine.can_withdraw, mine.sing_more, mine.name, mine.takes, mine.words], ["withdrawn", false, null, "", [], []]);
  assert.equal((await send(w, e, sid)).status, 410);
  assert.equal((await call(w, e, `/api/yours/${sid}/withdraw`, { method: "POST" })).status, 409);
  const gone = (await admin(w, e, "GET", "gone")).data.gone;
  assert.deepEqual(gone.map(g => [g.singer, g.what, g.take]), [[sid, "withdrawn", null]]);
  const singers = (await admin(w, e, "GET", "singers?emails=1")).data.singers;
  assert.deepEqual(singers.map(s => [s.sid, s.state, s.email]), [[sid, "withdrawn", null], [stays, "open", "jo@example.org"]]);

  e.CLOSES_AT = EARLIER; // singing has closed: what Jo gave is part of the song now
  const late = await call(w, e, `/api/yours/${stays}/withdraw`, { method: "POST" });
  assert.equal(late.status, 410);
  assert.match((await late.json()).message, /part of it now/);
  assert.equal((await page(w, e, stays)).data.can_withdraw, false);
  assert.equal(e.TAKES.keys(`takes/${stays}/`).length, 2);
});

test("once singing has closed: no joining, takes, words or withdrawing, but own pages and deleting still work", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 5 });
  const sid = (await join(w, e, token)).data.singer;
  await send(w, e, sid);
  e.CLOSES_AT = EARLIER;
  assert.equal((await call(w, e, `/i/${token}`)).status, 410);
  assert.match(await (await call(w, e, `/i/${token}`)).text(), /Singing has closed/);
  assert.equal((await (await call(w, e, `/api/invite/${token}`)).json()).state, "closed");
  assert.equal((await call(w, e, `/api/song/${token}`)).status, 410);
  const joining = await join(w, e, token, { email: "late@example.org" });
  assert.deepEqual([joining.status, joining.data.error], [410, "closed"]);
  const late = await send(w, e, sid);
  assert.deepEqual([late.status, late.data.error], [410, "closed"]);
  const words = await call(w, e, `/api/words/${sid}`, { method: "POST", body: JSON.stringify({ text: "late", release: { agreed: true, at: new Date().toISOString(), text: SONG.words_release } }) });
  assert.equal(words.status, 410);
  const mine = (await page(w, e, sid)).data;
  assert.deepEqual([mine.state, mine.sing_more, mine.can_withdraw, mine.takes.length], ["closed", null, false, 1]);
  assert.equal((await call(w, e, `/y/${sid}`)).status, 200);
  assert.equal((await call(w, e, `/api/yours/${sid}/take/${mine.takes[0].id}`)).status, 200);
  assert.equal((await call(w, e, `/api/yours/${sid}/delete`, { method: "POST" })).status, 200);
  assert.equal((await (await admin(w, e, "GET", "status")).data).closed, true);
});

test("\"I'm done\" is a note for the artist, and closes nothing", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e);
  const sid = (await join(w, e, token)).data.singer;
  const done = await call(w, e, `/api/done/${sid}`, { method: "POST" });
  const { state, done: at } = await done.json();
  assert.equal(state, "done");
  assert.equal((await (await call(w, e, `/api/invite/${token}`)).json()).state, "open");
  assert.equal((await call(w, e, `/i/${token}`)).status, 200);
  assert.equal((await send(w, e, sid)).status, 200); // they came back for one more
  const mine = (await page(w, e, sid)).data;
  assert.deepEqual([mine.state, mine.done, mine.sing_more !== null], ["open", at, true]);
  assert.equal((await admin(w, e, "GET", "singers")).data.singers[0].done, at);
});

test("the artist's API: invitations, singers (emails only when asked), takes, words, files and emails sent", async () => {
  const w = await load(), e = env();
  const made = (await admin(w, e, "POST", "invites", { count: 2, people: 4, note: "choir", limit: 7, days: 3 })).data.invites;
  assert.equal(made.length, 2);
  assert.deepEqual(Object.keys(made[0]).sort(), ["created", "expires", "limit", "note", "people", "state", "token", "url", "v"]);
  assert.deepEqual([made[0].people, made[0].limit, made[0].note, made[0].v], [4, 7, "choir", 2]);
  assert.equal(made[0].url, `https://songbird.test/i/${made[0].token}`);
  const a = (await join(w, e, made[0].token, { email: "a@example.org", name: "A", notify: true })).data.singer;
  const b = (await join(w, e, made[0].token, { email: "b@example.org", name: "B" })).data.singer;
  await send(w, e, a);
  const listed = Object.fromEntries((await admin(w, e, "GET", "invites")).data.invites.map(i => [i.token, i]));
  assert.deepEqual([listed[made[0].token].joined, listed[made[0].token].takes, listed[made[1].token].joined], [2, 1, 0]);

  const plain = (await admin(w, e, "GET", "singers")).data;
  assert.equal(plain.cursor, null);
  assert.deepEqual(plain.dates, { closes: LATER, delete_by: LATER });
  assert.ok(!JSON.stringify(plain).includes("@example.org")); // no emails unless asked
  const [sa, sb] = plain.singers;
  assert.deepEqual([sa.sid, sa.person, sa.name, sa.notify, sa.takes, sa.set, sa.state, sa.page], [a, a, "A", true, 1, "a", "open", `https://songbird.test/y/${a}`]);
  assert.deepEqual(sa.sent, { link: null, ready: null });
  assert.equal(sb.set, "b");
  const withEmails = (await admin(w, e, "GET", "singers?emails=1")).data.singers;
  assert.deepEqual(withEmails.map(s => s.email), ["a@example.org", "b@example.org"]);

  const sent = await admin(w, e, "POST", `sent/${a}`, { kind: "link" });
  assert.ok(sent.data.sent.link);
  assert.equal(sent.data.sent.ready, null);
  assert.equal((await admin(w, e, "POST", `sent/${a}`, { kind: "ready" })).data.sent.link, sent.data.sent.link);
  assert.equal((await admin(w, e, "POST", `sent/${a}`, { kind: "other" })).status, 400);
  assert.equal((await admin(w, e, "GET", "singers")).data.singers[0].sent.link, sent.data.sent.link);

  const takes = (await admin(w, e, "GET", `takes?singer=${a}`)).data.takes;
  assert.equal(takes.length, 1);
  assert.deepEqual(Object.keys(takes[0]).sort(), ["id", "json", "singer", "wav"]);
  assert.equal(takes[0].singer, a);
  const side = await call(w, e, `/api/admin/take/${takes[0].json.key}`, { headers: { Authorization: `Bearer ${ADMIN}` } });
  assert.equal((await side.json()).sid, a);
  assert.equal((await admin(w, e, "GET", `takes?singer=${a}`)).data.takes.length, 1); // still there
  assert.equal((await admin(w, e, "GET", "take/takes/../x.wav")).status, 400);

  await call(w, e, `/api/words/${b}`, { method: "POST", body: JSON.stringify({ text: "B's line", release: { agreed: true, at: new Date().toISOString(), text: SONG.words_release } }) });
  const words = (await admin(w, e, "GET", "words")).data.words;
  assert.deepEqual(words.map(x => x.singer), [b]);
  assert.equal((await admin(w, e, "GET", `word/${words[0].key}`)).data.text, "B's line");
  assert.equal((await admin(w, e, "GET", "word/words/../x.json")).status, 400);

  const put = (name, body = "abc", headers = {}) => call(w, e, `/api/admin/file/${a}/${name}?about=Your%20version`, {
    method: "PUT", body, headers: { Authorization: `Bearer ${ADMIN}`, "Content-Length": String(body.length), ...headers } });
  assert.equal((await put("a.k0.t100.version.mp3")).status, 200);
  assert.equal((await put("..%2Fx.mp3")).status, 400);
  assert.notEqual((await put("../x.mp3")).status, 200);
  assert.equal((await put("x.exe")).status, 400);
  assert.equal((await call(w, e, `/api/admin/file/${"Q".repeat(24)}/x.mp3`, { method: "PUT", body: "abc", headers: { Authorization: `Bearer ${ADMIN}`, "Content-Length": "3" } })).status, 404);
  assert.deepEqual((await page(w, e, a)).data.files.map(f => f.about), ["Your version"]);
  assert.deepEqual((await admin(w, e, "DELETE", `file/${a}/a.k0.t100.version.mp3`)).data, { deleted: "a.k0.t100.version.mp3" });

  const status = (await admin(w, e, "GET", "status")).data;
  assert.deepEqual([status.closes, status.delete_by, status.closed, status.deleting], [LATER, LATER, false, false]);
  assert.equal((await admin(w, e, "POST", "purge")).status, 409); // nothing is deleted before DELETE_BY
  assert.equal((await admin(w, e, "POST", `revoke/${made[1].token}`)).data.state, "revoked");
});

test("the hourly cron forgets addresses; after DELETE_BY it deletes every take and file, and emails not asked to be kept", async () => {
  const w = await load(), e = env();
  const token = await invitation(w, e, { people: 5 });
  const keeps = (await join(w, e, token, { email: "keep@example.org", notify: true })).data.singer;
  const drops = (await join(w, e, token, { email: "drop@example.org" })).data.singer;
  await send(w, e, keeps);
  await send(w, e, drops);
  await call(w, e, `/api/words/${drops}`, { method: "POST", body: JSON.stringify({ text: "A line", release: { agreed: true, at: new Date().toISOString(), text: SONG.words_release } }) });
  await e.TAKES.put(`files/${keeps}/a.k0.t100.version.mp3`, "mp3");
  await e.TAKES.put("limits/20010101T00/0123456789abcdef-aaaaaaaa", "");
  const cron = async () => {
    const waits = [];
    await w.scheduled({ scheduledTime: Date.now(), cron: "0 * * * *" }, e, { waitUntil: p => waits.push(p) });
    await Promise.all(waits);
  };

  await cron(); // before DELETE_BY: only the hours gone by are forgotten
  assert.deepEqual(e.TAKES.keys("limits/20010101T00/"), []);
  assert.equal(e.TAKES.keys("limits/").length, 2); // this hour's two joins
  assert.equal(e.TAKES.keys("takes/").length, 4);

  e.DELETE_BY = EARLIER;
  await cron();
  assert.deepEqual(e.TAKES.keys("takes/"), []);
  assert.deepEqual(e.TAKES.keys("files/"), []);
  assert.deepEqual(e.TAKES.keys("emails/"), [`emails/${keeps}`]); // kept for one message: the song is out
  assert.deepEqual(e.TAKES.keys("joined/"), []);
  assert.equal(e.TAKES.keys("words/").length, 1); // words given to the song stay
  const mine = (await page(w, e, drops)).data;
  assert.deepEqual([mine.state, mine.takes, mine.files, mine.words.length, mine.sing_more], ["deleted", [], [], 1, null]);
  assert.equal((await call(w, e, `/api/yours/${drops}/delete`, { method: "POST" })).status, 410);
  const purge = (await admin(w, e, "POST", "purge")).data; // again, now: nothing left
  assert.deepEqual(purge, { takes: 0, files: 0, emails: 0, more: false });
  assert.equal((await admin(w, e, "GET", "status")).data.deleting, true);
  assert.equal((await call(w, e, `/api/admin/file/${keeps}/a.mp3`, { method: "PUT", body: "abc", headers: { Authorization: `Bearer ${ADMIN}`, "Content-Length": "3" } })).status, 410);
});

test("a cold start reads song/worker.json when the site has one, song.json when not", async () => {
  const small = {
    song: SONG.song, consent: SONG.consent, words_release: SONG.words_release, sets: ["a"],
    guides: { "a.k0.t100": { guide: "aaaaaaaaaaaa", lyrics: "a.k0.t100.json", duration: 60, mixes: { melody: "a.k0.t100.melody.mp3" } } },
    max_seconds: 120,
  };
  const w = await load(), e = env({ files: { ...SITE, "/song/worker.json": JSON.stringify(small), "/song/song.json": "not read" } });
  const token = await invitation(w, e, { people: 3 });
  const sid = (await join(w, e, token)).data.singer;
  assert.equal((await send(w, e, sid)).status, 200);
  assert.equal((await send(w, e, sid, { mix: "full" })).data.message, "no such guide"); // as worker.json says
  const broken = await load(), none = env({ files: { ...SITE, "/song/song.json": JSON.stringify({ song: "h", guide: "x", mixes: {} }) } });
  const t2 = await invitation(broken, none);
  assert.equal((await join(broken, none, t2)).status, 500); // an old site: build it again
});
