// Songbird's singers, anywhere: a small Cloudflare Worker that serves the sing-along page
// to people the artist has invited, and keeps what they sing, privately, for the artist.
//
//   GET    /i/<token>                   the page, while the invite is open
//   GET    /api/invite/<token>          the invite: open or not, how many takes, until when
//   GET    /api/song/<token>            the song: its words and notes, the guides, the release's digest
//   GET    /api/guide/<token>/<mix>     a guide to sing along to (MP3)
//   PUT    /api/take/<token>            a take (16-bit mono WAV) with its sidecar (X-Take-Info)
//   POST   /api/done/<token>            "I'm done": closes the invite
//
// and for the artist, with Authorization: Bearer <ADMIN_TOKEN> (wrangler secret put ADMIN_TOKEN):
//
//   POST   /api/admin/invites           make invites: {count, days, limit, note}
//   GET    /api/admin/invites           every invite, its state and its takes
//   POST   /api/admin/revoke/<token>    close an invite
//   GET    /api/admin/takes[?invite=]   the takes waiting, each a WAV and its sidecar
//   GET    /api/admin/take/<key>        download one
//   DELETE /api/admin/take/<key>        delete one
//
// Invites live in KV (INVITES), takes in a private R2 bucket (TAKES) under takes/<token>/; closing
// an invite also leaves closed/<token> in the bucket, which every location reads at once.
// The page, its scripts and the guides are static assets (tools/sing_site.py builds them);
// the song's words and guides are served only to an open invite. Nothing personal is
// logged: no names, no tokens, no addresses. An address is used only as a rate-limit key.

import { DEFAULTS, MAX_TAKE_BYTES, TAKE_KEY, TOKEN, checkInfo, clampInt, cleanName, fromB64url, newToken, parseWavHeader,
         sameSecret, stateOf, takeKey } from "./lib.js";

const KEEP_AFTER_EXPIRY = 90 * 86400; // seconds an invite's record outlives it, for the artist's list
const PUBLIC = { "/sing.js": "text/javascript", "/sing.css": "text/css", "/karaoke.js": "text/javascript",
                 "/recorder.js": "text/javascript", "/robots.txt": "text/plain", "/favicon.svg": "image/svg+xml" };

const SECURITY = {
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "X-Frame-Options": "DENY",
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=(), usb=()",
  "Strict-Transport-Security": "max-age=15552000",
};
const PAGE_CSP = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; " +
                 "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

/* ---------- responses ---------- */

function headers(extra = {}) {
  return { ...SECURITY, ...extra };
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status, headers: headers({ "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...extra }),
  });
}

function fail(status, error, message) {
  return json({ error, message }, status);
}

function closedPage(state) {
  const why = state === "done" ? "You've finished singing on this invitation. Thank you!"
    : state === "expired" ? "This invitation has expired. If you'd still like to sing, ask the person who sent it for a new one."
    : "This invitation isn't open (it may have been closed, or the link is mistyped). Ask the person who sent it for a new one.";
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Songbird</title><link rel="stylesheet" href="/sing.css"></head><body><main class="closed"><h1>Songbird</h1><p>${why}</p></main></body></html>`;
  return new Response(html, {
    status: state === "unknown" ? 404 : 410,
    headers: headers({ "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Content-Security-Policy": PAGE_CSP,
                       "X-Robots-Tag": "noindex" }),
  });
}

async function asset(env, request, path, extra = {}) {
  // a static file from the built site, whatever the request's own path
  const url = new URL(request.url);
  url.pathname = path;
  url.search = "";
  const pass = {};
  for (const h of ["Range", "If-None-Match", "If-Modified-Since"]) if (request.headers.get(h)) pass[h] = request.headers.get(h);
  const r = await env.ASSETS.fetch(new Request(url.toString(), { headers: pass }));
  const out = new Response(r.body, r);
  for (const [k, v] of Object.entries(headers(extra))) out.headers.set(k, v);
  return out;
}

let SONG = null; // the built song's details, read once per isolate

async function song(env, request) {
  if (!SONG) {
    const r = await asset(env, request, "/song/song.json");
    if (!r.ok) throw new Error("the site has no song: build it with tools/sing_site.py");
    SONG = await r.json();
  }
  return SONG;
}

/* ---------- invites ---------- */

async function invite(env, token) {
  if (!TOKEN.test(token)) return null;
  const record = await env.INVITES.get(`invite:${token}`, "json");
  if (record && record.state === "open") {
    // closing is written to R2 too: KV can go on serving "open" elsewhere for a minute, R2 can't
    const closed = await env.TAKES.head(`closed/${token}`);
    if (closed) return { ...record, state: closed.customMetadata?.state || "done", closed: closed.customMetadata?.at };
  }
  return record;
}

async function close(env, token, inv, state) {
  const at = new Date().toISOString();
  await env.TAKES.put(`closed/${token}`, "", { customMetadata: { state, at } });
  await saveInvite(env, token, { ...inv, state, closed: at });
}

async function saveInvite(env, token, record) {
  const ttl = Math.max(60, Math.round((Date.parse(record.expires) - Date.now()) / 1000) + KEEP_AFTER_EXPIRY);
  const { note, ...meta } = record; // the list shows the note too, when it fits
  const metadata = JSON.stringify(record).length < 1000 ? record : meta;
  await env.INVITES.put(`invite:${token}`, JSON.stringify(record), { expirationTtl: ttl, metadata });
}

async function sentBy(env, token) {
  // how many takes an invite has sent: its own count (a key of its own, so an upload never rewrites
  // the invite and can't reopen one just closed), or the sidecars waiting in the bucket (written
  // last) if that is more; the artist fetching them never frees room for more
  const [count, waiting] = await Promise.all([env.INVITES.get(`sent:${token}`),
                                              allTakes(env, token).then(all => all.filter(o => o.key.endsWith(".json")).length)]);
  return Math.max(Number(count) || 0, waiting);
}

function sameSite(request) {
  // a browser says where a request comes from: a take or "I'm done" must come from the page itself,
  // never from a page elsewhere that learned the link (tools send no such header)
  const site = request.headers.get("Sec-Fetch-Site");
  return site === null || site === "same-origin";
}

async function limited(limiter, key) {
  if (!limiter) return false; // no binding (an old local wrangler): no limit
  try {
    const { success } = await limiter.limit({ key });
    return !success;
  } catch (e) {
    return false;
  }
}

/* ---------- the singer's routes ---------- */

async function singer(request, env, parts, ip) {
  const [kind, token, extra] = parts;
  const inv = await invite(env, token);
  const state = stateOf(inv);
  if (!inv && await limited(env.UNKNOWN, `unknown:${ip}`)) return fail(429, "busy", "Too many requests: wait a minute.");

  if (kind === "invite" && request.method === "GET") {
    if (!inv) return fail(404, "unknown", "No such invitation.");
    return json({ state, expires: inv.expires, limit: inv.limit, takes: await sentBy(env, token) });
  }
  if (state !== "open") return fail(state === "unknown" ? 404 : 410, state, "This invitation isn't open.");

  if (kind === "song" && request.method === "GET") {
    return asset(env, request, "/song/song.json", { "Cache-Control": "no-store", "Content-Type": "application/json; charset=utf-8" });
  }
  if (kind === "guide" && request.method === "GET") {
    const s = await song(env, request);
    if (!Object.prototype.hasOwnProperty.call(s.mixes, extra)) return fail(404, "unknown", "No such guide.");
    return asset(env, request, `/song/${s.mixes[extra].file}`, { "Cache-Control": "private, max-age=86400", "Content-Type": "audio/mpeg" });
  }
  if ((kind === "take" || kind === "done") && !sameSite(request)) return fail(403, "site", "Only the singing page can do that.");
  if (kind === "take" && request.method === "PUT") return take(request, env, token, inv);
  if (kind === "done" && request.method === "POST") {
    await close(env, token, inv, "done");
    return json({ state: "done" });
  }
  return fail(405, "method", "Not here.");
}

async function drained(reader, response) {
  // a take refused once its length is known to be sane is read to its end first (and dropped), so
  // the page, still sending, hears why rather than losing the connection
  try {
    for (;;) if ((await reader.read()).done) break;
  } catch (e) { /* gone already */ }
  return response;
}

async function take(request, env, token, inv) {
  const declared = request.headers.get("Content-Length"), length = Number(declared);
  if (declared === null || !Number.isInteger(length) || length < 44 || !request.body) return fail(411, "length", "A take must say how long it is.");
  if (length > MAX_TAKE_BYTES) return fail(413, "size", "That take is too big.");
  const reader = request.body.getReader();
  if (await limited(env.UPLOADS, `take:${token}`)) {
    return drained(reader, fail(429, "busy", "Too many takes at once: wait a minute and send it again."));
  }
  const type = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  if (!["audio/wav", "audio/x-wav", "audio/wave"].includes(type)) return drained(reader, fail(415, "type", "A take must be a WAV."));
  const header = request.headers.get("X-Take-Info") || "";
  if (!header || header.length > 4096) return drained(reader, fail(400, "info", "The take's details are missing."));

  const s = await song(env, request);
  const sent = await sentBy(env, token);
  if (sent >= inv.limit) {
    return drained(reader, fail(403, "limit", `This invitation takes up to ${inv.limit} takes, and they're all in. Thank you!`));
  }

  // its first 44 bytes say whether it's a take at all; the rest streams on to the bucket, so the
  // Worker never holds or hashes a whole take (the free plan allows it 10 ms of work a request)
  let head = new Uint8Array(0);
  while (head.byteLength < 44) {
    const { value, done } = await reader.read();
    if (done) break;
    const joined = new Uint8Array(head.byteLength + value.byteLength);
    joined.set(head);
    joined.set(value, head.byteLength);
    head = joined;
  }
  let info;
  try {
    const wav = parseWavHeader(head, length);
    info = checkInfo(JSON.parse(new TextDecoder().decode(fromB64url(header))), s, wav);
  } catch (e) {
    return drained(reader, fail(400, "take", e instanceof SyntaxError ? "The take's details can't be read." : e.message));
  }
  const received = new Date();
  const key = takeKey(token, received);
  // exactly the length it declared, and R2 checks it against the SHA-256 the page worked out: a take
  // cut short or changed on the way isn't kept
  const { readable, writable } = new FixedLengthStream(length);
  const pump = (async () => {
    const writer = writable.getWriter();
    try {
      await writer.write(head);
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        await writer.write(value);
      }
      await writer.close();
    } catch (e) {
      await writer.abort(e).catch(() => {});
      throw e;
    }
  })();
  try {
    await Promise.all([env.TAKES.put(`${key}.wav`, readable, { sha256: info.sha256, httpMetadata: { contentType: "audio/wav" } }), pump]);
  } catch (e) {
    return fail(400, "damaged", "The take arrived damaged or cut short: send it again.");
  }
  const sidecar = { ...info, received: received.toISOString(), bytes: length, take: sent + 1 };
  await env.TAKES.put(`${key}.json`, JSON.stringify(sidecar), { httpMetadata: { contentType: "application/json" } });
  const ttl = Math.max(60, Math.round((Date.parse(inv.expires) - Date.now()) / 1000) + KEEP_AFTER_EXPIRY);
  await env.INVITES.put(`sent:${token}`, String(sent + 1), { expirationTtl: ttl });
  return json({ ok: true, take: sent + 1, limit: inv.limit });
}

/* ---------- the artist's routes ---------- */

async function admin(request, env, parts) {
  const secret = env.ADMIN_TOKEN || "";
  if (secret.length < 32) return fail(503, "admin", "Set ADMIN_TOKEN (wrangler secret put ADMIN_TOKEN) to use the admin API.");
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ") || !sameSecret(auth.slice(7), secret)) return fail(401, "auth", "Not allowed.");
  const [what, rest] = [parts[0], parts.slice(1).join("/")];
  const url = new URL(request.url);

  if (what === "invites" && request.method === "POST") {
    let body = {};
    try { body = await request.json(); } catch (e) { /* defaults */ }
    const count = clampInt(body.count ?? 1, 1, 50, 1), days = clampInt(body.days ?? DEFAULTS.days, 1, 60, DEFAULTS.days);
    const limit = clampInt(body.limit ?? DEFAULTS.limit, 1, 200, DEFAULTS.limit);
    const note = cleanName(String(body.note ?? "")).slice(0, 80);
    const created = new Date(), expires = new Date(created.getTime() + days * 86400e3);
    const made = [];
    for (let i = 0; i < count; i++) {
      const token = newToken();
      const record = { v: 1, created: created.toISOString(), expires: expires.toISOString(), limit, note, state: "open" };
      await saveInvite(env, token, record);
      made.push({ token, url: `${url.origin}/i/${token}`, ...record });
    }
    return json({ invites: made });
  }
  if (what === "invites" && request.method === "GET") {
    const counts = {}, closed = {};
    for (const o of await allTakes(env)) if (o.key.endsWith(".json")) counts[o.key.split("/")[1]] = (counts[o.key.split("/")[1]] || 0) + 1;
    for (const o of await listed(env, "closed/", ["customMetadata"])) {
      closed[o.key.slice(7)] = { state: o.customMetadata?.state || "done", closed: o.customMetadata?.at };
    }
    const out = [];
    let cursor;
    do {
      const page = await env.INVITES.list({ prefix: "invite:", cursor });
      for (const k of page.keys) {
        const token = k.name.slice(7);
        let record = k.metadata && k.metadata.expires ? k.metadata : await env.INVITES.get(k.name, "json");
        if (record && record.state === "open" && closed[token]) record = { ...record, ...closed[token] };
        if (record) {
          const sent = Math.max(Number(await env.INVITES.get(`sent:${token}`)) || 0, counts[token] || 0);
          out.push({ token, url: `${url.origin}/i/${token}`, ...record, state: stateOf(record), takes: counts[token] || 0, sent });
        }
      }
      cursor = page.list_complete ? undefined : page.cursor;
    } while (cursor);
    out.sort((a, b) => a.created.localeCompare(b.created));
    return json({ invites: out });
  }
  if (what === "revoke" && request.method === "POST") {
    const inv = await invite(env, rest);
    if (!inv) return fail(404, "unknown", "No such invitation.");
    await close(env, rest, inv, "revoked");
    return json({ state: "revoked" });
  }
  if (what === "takes" && request.method === "GET") {
    const only = url.searchParams.get("invite");
    if (only && !TOKEN.test(only)) return fail(400, "invite", "Not an invitation.");
    const takes = {};
    for (const o of await allTakes(env, only)) {
      const id = o.key.replace(/\.(wav|json)$/, "");
      const t = takes[id] || (takes[id] = { id, invite: o.key.split("/")[1] });
      t[o.key.endsWith(".wav") ? "wav" : "json"] = { key: o.key, size: o.size, uploaded: o.uploaded };
    }
    return json({ takes: Object.values(takes).sort((a, b) => a.id.localeCompare(b.id)) });
  }
  if (what === "take" && (request.method === "GET" || request.method === "DELETE")) {
    if (!TAKE_KEY.test(rest)) return fail(400, "key", "Not a take.");
    if (request.method === "DELETE") {
      await env.TAKES.delete(rest);
      return json({ deleted: rest });
    }
    const o = await env.TAKES.get(rest);
    if (!o) return fail(404, "unknown", "No such take.");
    return new Response(o.body, { headers: headers({ "Content-Type": rest.endsWith(".wav") ? "audio/wav" : "application/json",
                                                     "Content-Length": String(o.size), "Cache-Control": "no-store" }) });
  }
  return fail(404, "unknown", "No such thing.");
}

async function allTakes(env, only) {
  return listed(env, only ? `takes/${only}/` : "takes/");
}

async function listed(env, prefix, include) {
  const out = [];
  let cursor;
  do {
    const page = await env.TAKES.list({ prefix, cursor, ...(include ? { include } : {}) });
    out.push(...page.objects);
    cursor = page.truncated ? page.cursor : undefined;
  } while (cursor);
  return out;
}

/* ---------- the way in ---------- */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const ip = request.headers.get("CF-Connecting-IP") || "local"; // only ever a key for counting requests
    try {
      if (path.startsWith("/api/") || path.startsWith("/i/")) {
        if (await limited(env.REQUESTS, `ip:${ip}`)) return fail(429, "busy", "Too many requests: wait a minute.");
      }
      if (path.startsWith("/i/")) {
        const token = path.slice(3);
        const inv = await invite(env, token);
        if (!inv && await limited(env.UNKNOWN, `unknown:${ip}`)) return fail(429, "busy", "Too many requests: wait a minute.");
        const state = stateOf(inv);
        if (state !== "open" || !["GET", "HEAD"].includes(request.method)) return closedPage(state);
        return asset(env, request, "/index.html", { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                                                  "Content-Security-Policy": PAGE_CSP, "X-Robots-Tag": "noindex" });
      }
      if (path.startsWith("/api/admin/")) return await admin(request, env, path.slice(11).split("/"));
      if (path.startsWith("/api/")) {
        const parts = path.slice(5).split("/");
        if (parts.length < 2 || parts.length > 3 || !["invite", "song", "guide", "take", "done"].includes(parts[0])) {
          return fail(404, "unknown", "No such thing.");
        }
        return await singer(request, env, parts, ip);
      }
      if (Object.prototype.hasOwnProperty.call(PUBLIC, path) && request.method === "GET") {
        return asset(env, request, path, { "Content-Type": `${PUBLIC[path]}; charset=utf-8`, "Cache-Control": "public, max-age=300" });
      }
      if (path === "/") {
        return new Response("Songbird: a folk song that passes itself on. Singers come here by invitation.\n",
                            { headers: headers({ "Content-Type": "text/plain; charset=utf-8" }) });
      }
      return fail(404, "unknown", "No such thing.");
    } catch (e) {
      console.error("songbird-sing:", e && e.name); // never the request, the invite or the singer
      return fail(500, "error", "Something went wrong on our side. Try again in a moment.");
    }
  },
};
