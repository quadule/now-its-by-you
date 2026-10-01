// The studio at studio.itsby.you: a static site (the studio's page and its render bundle, made by
// web/studio-wasm/tools/build_site.py and served by Workers Static Assets, with tools/prepare.mjs's _headers) where
// everything is made on the visitor's own device, and this Worker for the few things a static site can't do:
//
//   POST /api/versions          share a version: the body is a rendition (a FLAC with its packet appended); it is
//                               checked as data (src/packet.js: never unpacked, never run), kept in R2 under its
//                               content address, and answered 201 {"id": "<32 hex>", "url": "/v/<id>"}
//   GET  /api/versions/<id>     that file (audio/flac, immutable), whole or in ranges
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
// once in REFRESH_DAYS); limits/<hour>/<address digest>-<random>, one mark per upload this hour, for the hourly
// limits (an address is kept only as 64 bits of a digest, and only until the hour is over); incoming/<random>, a
// file on its way in (without a digest from the page). Every hour (the cron) a version not opened for KEEP_DAYS is
// deleted, and so are past hours' marks and anything left incoming. Nothing personal is logged.

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

async function digest64(text) {
  // 64 bits of SHA-256: enough to count an address apart from others, nothing to read it back from
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
  return Array.from(d.slice(0, 8), b => b.toString(16).padStart(2, "0")).join("");
}

async function limited(limiter, key) {
  if (!limiter) return false; // no binding (an old local wrangler): no limit
  try {
    return !(await limiter.limit({ key })).success;
  } catch (e) {
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

  // this hour's shares, from here and from everywhere, before a byte of the file is read; this one counts
  // whether or not it is kept, so a flood of bad files is held back as well
  const hour = hourOf(now), me = await digest64(addressOf(ip));
  const marks = (await env.VERSIONS.list({ prefix: `limits/${hour}/`, limit: 1000 })).objects.map(o => o.key);
  if (marks.filter(k => k.startsWith(`limits/${hour}/${me}-`)).length >= setting(env, "UPLOADS_AN_HOUR", UPLOADS_AN_HOUR)) {
    return fail(429, "You've shared as many versions as can be shared from one place in an hour: try again next hour.", { "Retry-After": "3600" });
  }
  if (marks.length >= setting(env, "ALL_AN_HOUR", ALL_AN_HOUR)) {
    return fail(429, "Many versions are being shared just now: try again in an hour.", { "Retry-After": "3600" });
  }
  await env.VERSIONS.put(`limits/${hour}/${me}-${crypto.randomUUID().slice(0, 8)}`, "");

  const kept = claimed ? await keepClaimed(env, request, size, claimed) : await keepHashed(env, request, size, now);
  if (kept.error) return fail(kept.status || 400, kept.error);
  return json({ id: kept.id, url: `/v/${kept.id}` }, 201);
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

async function keepClaimed(env, request, size, sha) {
  // the page said the file's SHA-256: R2 checks the bytes against it as they're written, straight to their place
  // (the same bytes, under the same name, are the same version: writing them again changes nothing but the date)
  const id = sha.slice(0, 32), key = keyOf(id);
  try {
    const put = await env.VERSIONS.put(key, request.body, { ...FILE_META, sha256: sha });
    if (!put || put.size !== size) throw new Error("short");
  } catch (e) {
    return { status: 400, error: "The file didn't arrive whole, or isn't the one its SHA-256 names: send it again." };
  }
  const why = await checked(env, key, size);
  if (why) {
    await env.VERSIONS.delete(key); // never served: only its sender knows its name, until now
    return { status: 422, error: why };
  }
  return { id };
}

async function keepHashed(env, request, size, now) {
  // no digest from the page: the Worker hashes the file as it stores it, aside, and then puts it in its place
  const incoming = `incoming/${hourOf(now)}-${crypto.randomUUID()}`;
  const [toStore, toHash] = request.body.tee();
  const fixed = new FixedLengthStream(size);
  const hashing = new crypto.DigestStream("SHA-256");
  let sha;
  try {
    const piped = toStore.pipeTo(fixed.writable);
    const [put] = await Promise.all([env.VERSIONS.put(incoming, fixed.readable), piped, toHash.pipeTo(hashing)]);
    if (!put || put.size !== size) throw new Error("short");
    sha = Array.from(new Uint8Array(await hashing.digest), b => b.toString(16).padStart(2, "0")).join("");
  } catch (e) {
    await env.VERSIONS.delete(incoming).catch(() => {});
    return { status: 400, error: ARRIVED };
  }
  try {
    const why = await checked(env, incoming, size);
    if (why) return { status: 422, error: why };
    const id = sha.slice(0, 32), from = await env.VERSIONS.get(incoming);
    if (!from) return { status: 400, error: ARRIVED };
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
  // the same name is always the same bytes: a browser that has them needn't be sent them again
  if ((request.headers.get("If-None-Match") || "").split(",").map(s => s.trim().replace(/^W\//, "")).includes(tag)) {
    return new Response(null, { status: 304, headers: fileHeaders });
  }
  // one read for the usual whole file; a range, or HEAD, asks its size first
  const ranged = request.method === "HEAD" || request.headers.get("Range") !== null;
  const found = ranged ? await env.VERSIONS.head(keyOf(id)) : await env.VERSIONS.get(keyOf(id));
  if (!found) {
    if (await limited(env.UNKNOWN, `unknown:${addressOf(ip)}`)) return busy();
    return fail(404, GONE);
  }
  ctx.waitUntil(opened(env, id, found, now).catch(e => console.error("songbird-studio: opened", e && e.name)));
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
  // note that it was opened, at most once in REFRESH_DAYS: it's kept KEEP_DAYS after the latest
  const refresh = setting(env, "REFRESH_DAYS", REFRESH_DAYS) * 86400e3;
  if (now - new Date(head.uploaded).getTime() < refresh) return;
  const mark = await env.VERSIONS.head(`opened/${id}`);
  if (mark && now - new Date(mark.uploaded).getTime() < refresh) return;
  await env.VERSIONS.put(`opened/${id}`, "");
}

async function page(request, env) {
  // the studio's own page, whatever the path: it reads the version's id from its address
  if (!["GET", "HEAD"].includes(request.method)) return fail(405, "Not here.", { Allow: "GET, HEAD" });
  const r = await env.ASSETS.fetch(new Request(new URL("/", request.url), { method: request.method }));
  const out = new Response(r.body, r);
  for (const [k, v] of Object.entries({ ...PAGE, "Cache-Control": "no-cache" })) {
    out.headers.set(k, v);
  }
  return out;
}

/* ---------- every hour ---------- */

export async function tidy(env, now) {
  // versions not opened for KEEP_DAYS, past hours' marks, anything left incoming for an hour
  const keep = setting(env, "KEEP_DAYS", KEEP_DAYS) * 86400e3, hour = hourOf(now);
  const latest = new Map();
  for (const o of await listed(env.VERSIONS, "opened/")) latest.set(o.key.slice(7), new Date(o.uploaded).getTime());
  const gone = [];
  for (const o of await listed(env.VERSIONS, "versions/")) {
    const id = o.key.slice(9, -5);
    if (now - Math.max(new Date(o.uploaded).getTime(), latest.get(id) || 0) > keep) gone.push(o.key, `opened/${id}`);
  }
  const marks = (await listed(env.VERSIONS, "limits/")).map(o => o.key).filter(k => k.slice(7, 20) < hour);
  const incoming = (await listed(env.VERSIONS, "incoming/")).filter(o => now - new Date(o.uploaded).getTime() > 3600e3).map(o => o.key);
  await deleteKeys(env.VERSIONS, [...gone, ...marks, ...incoming]);
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
