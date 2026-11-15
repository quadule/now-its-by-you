// The studio at studio.itsby.you: a static site (the studio's page and its render bundle, made by
// web/studio-wasm/tools/build_site.py and served by Workers Static Assets, with tools/prepare.mjs's _headers) where
// everything is made on the visitor's own device, and this Worker for the few things a static site can't do:
//
//   POST /api/versions          share a version: the body is a rendition (a FLAC with its packet appended); it is
//                               checked as data (src/packet.js: never unpacked, never run), kept in R2 under its
//                               content address, and answered 201 {"id": "<32 hex>", "url": "/v/<id>"}
//   GET  /api/versions/<id>     that file (audio/flac, immutable), whole or in ranges; every fetch of it, a HEAD and
//                               a 304 among them, is an open, which keeps it (the page sends an uncached HEAD when
//                               it opens a version it already keeps, so the link stays alive for the next person)
//   GET  /v/<id>                the studio's page, which fetches the file and opens it on the device
//   anything else under /api/   404
//
// Errors are {"error": "<a sentence>"} with a 4xx status (5xx if something broke here).
//
// The id is the first 32 hex digits of the file's SHA-256. The page may send the whole digest
// (X-Content-SHA256), and then R2 itself checks the bytes against it as they are written, and the Worker never
// hashes 20-60 MB (the free plan allows 10 ms of CPU a request); without it, the Worker hashes as it stores.
//
// In R2 (VERSIONS, private): versions/<id>.flac, the files; opened/<id>, when one was last opened (written at most
// once in REFRESH_DAYS); keys/address, the key an address is counted under; incoming/<random>, a file on its way
// in, checked there before it goes to its place. Every hour (the cron) a version not opened for KEEP_DAYS is
// deleted (at most REFRESH_DAYS later), and so is anything left incoming (and any marks under limits/).
//
// The hourly limits are counted by one Durable Object (SHARES, the Shares class below), which admits a share or
// refuses it in one step, so shares arriving together can't all pass the same count: this hour's tries from each
// address (an address only as 64 bits of an HMAC under keys/address, forgotten when the hour is over) and the
// versions kept from everywhere (a place taken before the file is read, given back if it isn't kept). Nothing
// personal is logged.

import { MAX_BYTES, MIN_BYTES, Refused, checkVersion } from "./packet.js";
import { PAGE, SECURITY } from "./policy.js";

const KEEP_DAYS = 30; // a version is kept this long after it was last shared or opened (KEEP_DAYS in [vars])
const REFRESH_DAYS = 7; // "last opened" is noted at most this often, so most opens cost no write
const UPLOADS_AN_HOUR = 10; // versions shared from one address in a clock hour (UPLOADS_AN_HOUR)
const ALL_AN_HOUR = 60; // versions shared from everywhere in a clock hour (ALL_AN_HOUR): a ceiling on storage
const VERSION = /^[0-9a-f]{32}$/;
const DIGEST = /^[0-9a-f]{64}$/;

const FILE_POLICY = "default-src 'none'; sandbox"; // a shared file, opened by itself, can do nothing

/* ---------- responses ---------- */

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status, headers: { ...SECURITY, "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extra },
  });
}

const fail = (status, error, extra) => json({ error }, status, extra);
const busy = () => fail(429, "Too many requests from here just now: wait a minute and try again.", { "Retry-After": "60" });

/* ---------- limits ---------- */

function setting(env, name, fallback) {
  const n = Number(env[name]);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export function addressOf(ip) {
  // the address requests are counted by: an IPv6 address by its /64 (one connection's many addresses)
  if (!ip.includes(":")) return ip;
  const [head, tail = ""] = ip.toLowerCase().split("::");
  const left = head ? head.split(":") : [], right = tail ? tail.split(":") : [];
  const full = [...left, ...Array(Math.max(0, 8 - left.length - right.length)).fill("0"), ...right];
  return full.slice(0, 4).map(h => h.replace(/^0+(?=.)/, "")).join(":") + "::/64";
}

const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, "0")).join("");

async function addressMark(env, address, hour) {
  // 64 bits of HMAC-SHA-256(a key of this site's own, the hour and the address): enough to count an address apart
  // from others within the hour, and, without the key, nothing to work it back from (a plain digest of an IPv4
  // address is undone by trying all four billion). The key is made on first use and kept in R2 (keys/address);
  // read on every share, so two isolates that both made one agree within moments
  let key = await env.VERSIONS.get("keys/address");
  if (!key) {
    await env.VERSIONS.put("keys/address", hex(crypto.getRandomValues(new Uint8Array(32))));
    key = await env.VERSIONS.get("keys/address");
  }
  const secret = await crypto.subtle.importKey("raw", new TextEncoder().encode(await key.text()), { name: "HMAC", hash: "SHA-256" },
                                               false, ["sign"]);
  const mac = await crypto.subtle.sign("HMAC", secret, new TextEncoder().encode(`${hour} ${address}`));
  return hex(new Uint8Array(mac).slice(0, 8));
}

async function limited(limiter, key) {
  if (!limiter) return false; // no binding (an old local wrangler): no limit
  try {
    return !(await limiter.limit({ key })).success;
  } catch (e) {
    console.error("songbird-studio: limiter", e && e.name); // counted nothing: let it through
    return false;
  }
}

const hourOf = now => new Date(now).toISOString().slice(0, 13); // 2026-09-30T21

async function listed(bucket, prefix, include) {
  const out = [];
  let cursor;
  do {
    const page = await bucket.list({ prefix, cursor, ...(include ? { include } : {}) });
    out.push(...page.objects);
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return out;
}

async function deleteKeys(bucket, keys) {
  for (let i = 0; i < keys.length; i += 1000) await bucket.delete(keys.slice(i, i + 1000));
}

function sameSite(request, url) {
  // a share comes from the studio's own page (or a tool, which says nothing), never from a page elsewhere
  const site = request.headers.get("Sec-Fetch-Site"), origin = request.headers.get("Origin");
  return (site === null || site === "same-origin") && (origin === null || origin === url.origin);
}

/* ---------- sharing a version ---------- */

async function share(request, env, url, ip, now) {
  if (!sameSite(request, url)) return fail(403, "Only the studio's own page can share a version.");
  if (await limited(env.UPLOADS, `up:${addressOf(ip)}`)) return busy();
  const said = request.headers.get("Content-Length");
  if (said === null || !/^\d{1,12}$/.test(said)) return fail(411, "Send the file's length (Content-Length) with it.");
  const size = Number(said);
  if (size > MAX_BYTES) {
    return fail(413, `It's ${Math.round(size / 2 ** 20)} MB; a version shared here can be at most ${MAX_BYTES / 2 ** 20} MB (a rendition is about 15 to 25).`);
  }
  if (size < MIN_BYTES || !request.body) return fail(400, "That's too small to be a Songbird version.");
  const claimed = (request.headers.get("X-Content-SHA256") || "").toLowerCase();
  if (claimed && !DIGEST.test(claimed)) return fail(400, "X-Content-SHA256 must be the file's SHA-256, in 64 hex digits.");

  // this hour's shares, before a byte of the file is read: every attempt from here counts (so a flood of bad files
  // is held back too), but only versions kept count against everyone's ceiling (so junk can't shut sharing for all)
  if (!env.SHARES) return fail(503, "Sharing isn't set up on this site.");
  const hour = hourOf(now), me = await addressMark(env, addressOf(ip), hour);
  const shares = env.SHARES.get(env.SHARES.idFromName("shares"));
  const ask = async (what, body) => (await (await shares.fetch(`https://shares/${what}`, { method: "POST", body: JSON.stringify(body) })).json()).said;
  const admitted = await ask("admit", { hour, me, mine: setting(env, "UPLOADS_AN_HOUR", UPLOADS_AN_HOUR), all: setting(env, "ALL_AN_HOUR", ALL_AN_HOUR) });
  if (admitted === "mine") {
    return fail(429, "You've shared as many versions as can be shared from one place in an hour: try again next hour.", { "Retry-After": "3600" });
  }
  if (admitted === "all") return fail(429, "Many versions are being shared just now: try again in an hour.", { "Retry-After": "3600" });
  if (admitted !== "ok") throw new Error("the count didn't answer");

  let kept;
  try {
    kept = await keep(env, request, size, claimed, hour);
  } finally {
    if (!kept || kept.error) await ask("release", { hour }).catch(e => console.error("songbird-studio: release", e && e.name));
  }
  if (kept.error) return fail(kept.status || 400, kept.error);
  return json({ id: kept.id, url: `/v/${kept.id}` }, 201);
}

/* ---------- the hour's count ---------- */

export class Shares {
  // The one place the hour's shares are counted (a Durable Object: one instance, one request at a time, its storage
  // its own). "admit" {hour, me, mine, all}: "mine" when this address has tried `mine` times this hour, "all" when
  // `all` places are taken, else "ok", the try counted and a place taken. "release" {hour}: a place given back (a
  // file refused, or broken off). A new hour starts the count again.
  constructor(state) {
    this.storage = state.storage;
    this.turn = Promise.resolve();
  }

  async fetch(request) {
    const body = await request.json(), what = new URL(request.url).pathname.slice(1);
    const run = this.turn.then(() => (what === "admit" ? this.admit(body) : what === "release" ? this.release(body) : "unknown"));
    this.turn = run.catch(() => {});
    return new Response(JSON.stringify({ said: await run }), { headers: { "Content-Type": "application/json" } });
  }

  async counted(hour) {
    if ((await this.storage.get("hour")) !== hour) {
      await this.storage.deleteAll();
      await this.storage.put("hour", hour);
    }
  }

  async admit({ hour, me, mine, all }) {
    await this.counted(hour);
    const tried = (await this.storage.get(`by:${me}`)) || 0, taken = (await this.storage.get("all")) || 0;
    if (tried >= mine) return "mine";
    if (taken >= all) return "all";
    await this.storage.put({ [`by:${me}`]: tried + 1, all: taken + 1 });
    return "ok";
  }

  async release({ hour }) {
    if ((await this.storage.get("hour")) !== hour) return "ok"; // that hour's count is over
    await this.storage.put("all", Math.max(0, ((await this.storage.get("all")) || 0) - 1));
    return "ok";
  }
}

const ARRIVED = "The file didn't arrive whole: send it again.";
const GONE = "There's no version here: the link may be mistyped, or the version wasn't opened for a long while and is gone.";
const keyOf = id => `versions/${id}.flac`;
const FILE_META = { httpMetadata: { contentType: "audio/flac" } };

async function checked(env, key, size) {
  // the stored file, checked from a few ranged reads; null if it's a version, or why it isn't
  try {
    await checkVersion(size, async (offset, length) => bytesOf(await env.VERSIONS.get(key, { range: { offset, length } })),
                       async length => bytesOf(await env.VERSIONS.get(key, { range: { suffix: length } })));
    return null;
  } catch (e) {
    if (e instanceof Refused) return e.message;
    throw e;
  }
}

async function bytesOf(object) {
  if (!object) throw new Refused(ARRIVED);
  return new Uint8Array(await object.arrayBuffer());
}

async function keep(env, request, size, claimed, hour) {
  // the file goes to incoming/ first, and to its place only once it has been checked, so nothing unchecked is ever
  // under a version's name, whatever stops this Worker half way (incoming/ is swept within the hour). With the
  // page's digest, R2 checks the bytes against it as they're written; without, the Worker hashes them on the way,
  // in one pipeline, each chunk hashed before it goes on, so R2's pace holds the whole of it (a tee would buffer
  // what its slower side hadn't taken yet: up to the whole file, in a Worker allowed 128 MB)
  const incoming = `incoming/${hour}-${crypto.randomUUID()}`;
  let sha = claimed, hashing = null, body = request.body;
  if (!claimed) {
    hashing = new crypto.DigestStream("SHA-256");
    const hasher = hashing.getWriter(), fixed = new FixedLengthStream(size);
    request.body.pipeThrough(new TransformStream({
      async transform(chunk, ctl) { await hasher.write(chunk); ctl.enqueue(chunk); },
      async flush() { await hasher.close(); },
    })).pipeTo(fixed.writable).catch(() => {}); // a short or long body fails the put below
    body = fixed.readable;
  }
  try {
    try {
      const put = await env.VERSIONS.put(incoming, body, claimed ? { sha256: claimed } : {});
      if (!put || put.size !== size) throw new Error("short");
      if (hashing) sha = hex(new Uint8Array(await hashing.digest));
    } catch (e) {
      return { status: 400, error: claimed ? "The file didn't arrive whole, or isn't the one its SHA-256 names: send it again." : ARRIVED };
    }
    const why = await checked(env, incoming, size);
    if (why) return { status: 422, error: why };
    const id = sha.slice(0, 32), from = await env.VERSIONS.get(incoming);
    if (!from) return { status: 400, error: ARRIVED };
    // the same bytes, under the same name, are the same version: writing them again changes only the date
    await env.VERSIONS.put(keyOf(id), from.body, { ...FILE_META, sha256: sha });
    return { id };
  } finally {
    await env.VERSIONS.delete(incoming);
  }
}

/* ---------- a shared version ---------- */

export function parseRange(header, size) {
  // one range of bytes=a-b, a- or -n: {offset, length}; null: the whole file; false: unsatisfiable
  const m = /^bytes=(\d*)-(\d*)$/.exec((header || "").trim());
  if (!m || (m[1] === "" && m[2] === "")) return null;
  const start = m[1] === "" ? Math.max(0, size - Number(m[2])) : Number(m[1]);
  const end = m[1] === "" || m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  if (m[1] === "" && Number(m[2]) === 0) return false;
  return start > end || start >= size ? false : { offset: start, length: end - start + 1 };
}

async function version(request, env, ctx, id, ip, now) {
  if (!["GET", "HEAD"].includes(request.method)) return fail(405, "A shared version can only be fetched.", { Allow: "GET, HEAD" });
  const tag = `"${id}"`;
  const fileHeaders = {
    ...SECURITY, "Content-Type": "audio/flac", "Cache-Control": "public, max-age=31536000, immutable", ETag: tag,
    "Accept-Ranges": "bytes", "Content-Security-Policy": FILE_POLICY,
    "Content-Disposition": `attachment; filename="songbird-${id}.flac"`,
  };
  // the same name is always the same bytes: a browser that has them needn't be sent them again, but it is an open
  // all the same, and only while the version is still here
  const same = (request.headers.get("If-None-Match") || "").split(",").map(s => s.trim().replace(/^W\//, "")).includes(tag);
  // one read for the usual whole file; a range, HEAD, or a browser that has it asks its size first
  const ranged = same || request.method === "HEAD" || request.headers.get("Range") !== null;
  const found = ranged ? await env.VERSIONS.head(keyOf(id)) : await env.VERSIONS.get(keyOf(id));
  if (!found) {
    if (await limited(env.UNKNOWN, `unknown:${addressOf(ip)}`)) return busy();
    return fail(404, GONE);
  }
  ctx.waitUntil(opened(env, id, found, now).catch(e => console.error("songbird-studio: opened", e && e.name)));
  if (same) return new Response(null, { status: 304, headers: fileHeaders });
  if (!ranged) return new Response(found.body, { headers: { ...fileHeaders, "Content-Length": String(found.size) } });
  const range = parseRange(request.headers.get("Range"), found.size);
  if (range === false) {
    return new Response(null, { status: 416, headers: { ...fileHeaders, "Content-Range": `bytes */${found.size}` } });
  }
  if (request.method === "HEAD") return new Response(null, { headers: { ...fileHeaders, "Content-Length": String(found.size) } });
  const object = await env.VERSIONS.get(keyOf(id), range ? { range } : {});
  if (!object) return fail(404, GONE);
  if (!range) return new Response(object.body, { headers: { ...fileHeaders, "Content-Length": String(found.size) } });
  return new Response(object.body, {
    status: 206,
    headers: { ...fileHeaders, "Content-Length": String(range.length),
               "Content-Range": `bytes ${range.offset}-${range.offset + range.length - 1}/${found.size}` },
  });
}

async function opened(env, id, head, now) {
  // note that it was opened, at most once in REFRESH_DAYS since it was shared or last noted (tidy keeps it
  // KEEP_DAYS + REFRESH_DAYS after the later of the two, so at least KEEP_DAYS after any open)
  const refresh = setting(env, "REFRESH_DAYS", REFRESH_DAYS) * 86400e3;
  if (now - new Date(head.uploaded).getTime() < refresh) return;
  const mark = await env.VERSIONS.head(`opened/${id}`);
  if (mark && now - new Date(mark.uploaded).getTime() < refresh) return;
  await env.VERSIONS.put(`opened/${id}`, "");
}

async function page(request, env) {
  // the studio's own page, whatever the path: it reads the version's id from its address
  if (!["GET", "HEAD"].includes(request.method)) return fail(405, "Not here.", { Allow: "GET, HEAD" });
  const pass = {};
  for (const h of ["If-None-Match", "If-Modified-Since"]) if (request.headers.get(h)) pass[h] = request.headers.get(h);
  const r = await env.ASSETS.fetch(new Request(new URL("/", request.url), { method: request.method, headers: pass }));
  const out = new Response(r.body, r);
  for (const [k, v] of Object.entries({ ...PAGE, "Cache-Control": "no-cache" })) {
    out.headers.set(k, v);
  }
  return out;
}

/* ---------- every hour ---------- */

export async function tidy(env, now) {
  // versions neither shared nor opened for KEEP_DAYS (an open is noted up to REFRESH_DAYS late, so the wait is
  // KEEP_DAYS + REFRESH_DAYS after the later of the share and the last open noted), past hours' marks, anything
  // left incoming for an hour
  const keep = (setting(env, "KEEP_DAYS", KEEP_DAYS) + setting(env, "REFRESH_DAYS", REFRESH_DAYS)) * 86400e3, hour = hourOf(now);
  const latest = new Map();
  for (const o of await listed(env.VERSIONS, "opened/")) latest.set(o.key.slice(7), new Date(o.uploaded).getTime());
  const gone = [], ids = new Set();
  for (const o of await listed(env.VERSIONS, "versions/")) {
    const id = o.key.slice(9, -5);
    ids.add(id);
    if (now - Math.max(new Date(o.uploaded).getTime(), latest.get(id) || 0) <= keep) continue;
    const again = await env.VERSIONS.head(o.key); // shared again since the listing: it stays
    if (again && now - new Date(again.uploaded).getTime() <= keep) continue;
    gone.push(o.key, `opened/${id}`);
  }
  const orphans = [...latest.keys()].filter(id => !ids.has(id)).map(id => `opened/${id}`); // an open racing a delete
  const marks = (await listed(env.VERSIONS, "limits/")).map(o => o.key).filter(k => k.slice(7, 20) < hour);
  const incoming = (await listed(env.VERSIONS, "incoming/")).filter(o => now - new Date(o.uploaded).getTime() > 3600e3).map(o => o.key);
  await deleteKeys(env.VERSIONS, [...gone, ...orphans, ...marks, ...incoming]);
  return { versions: gone.length / 2, marks: marks.length, incoming: incoming.length };
}

/* ---------- the way in ---------- */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url), path = url.pathname, now = Date.now();
    const ip = request.headers.get("CF-Connecting-IP") || "local"; // only ever a key for counting requests
    try {
      if (path.startsWith("/api/") || path.startsWith("/v/")) {
        if (await limited(env.REQUESTS, `ip:${addressOf(ip)}`)) return busy();
      }
      if (path === "/api/versions") {
        if (request.method !== "POST") return fail(405, "Share a version with POST.", { Allow: "POST" });
        return await share(request, env, url, ip, now);
      }
      const asked = /^\/api\/versions\/([^/]+)$/.exec(path);
      if (asked && VERSION.test(asked[1])) return await version(request, env, ctx, asked[1], ip, now);
      if (path.startsWith("/api/")) return fail(404, "There's nothing here.");
      const v = /^\/v\/([^/]+)$/.exec(path);
      if (v && VERSION.test(v[1])) return await page(request, env);
      if (path.startsWith("/v/")) {
        return new Response("There's no version here: check the link.\n",
                            { status: 404, headers: { ...SECURITY, "Content-Type": "text/plain; charset=utf-8" } });
      }
      return await env.ASSETS.fetch(request); // what the static assets didn't have: their 404
    } catch (e) {
      console.error("songbird-studio:", e && e.name); // never the request, the address or the version
      return fail(500, "Something went wrong on our side. Try again in a moment.");
    }
  },

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(tidy(env, controller.scheduledTime || Date.now()).catch(e => console.error("songbird-studio: tidy", e && e.name)));
  },
};
