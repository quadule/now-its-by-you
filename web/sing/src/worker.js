// Songbird's singers, anywhere: a small Cloudflare Worker that serves the sing-along page to people the
// artist has invited, keeps what they sing, privately, for the artist, and gives each singer a page of
// their own where they can hear, download or delete what they sent, or withdraw.
//
// By invitation (a personal link admits one person, on up to three devices; a group link, `people`):
//   GET    /i/<invite>                        the singing page, while the invitation is open
//   GET    /api/invite/<invite>               the invitation: open or not, until when, how many can join
//   GET    /api/song/<invite>                 song.json: the sets, keys, speeds and guides
//   GET    /api/lyrics/<invite>/<spec>        one guide's words and notes, and its sections
//   GET    /api/guide/<invite>/<spec>/<mix>   one guide to sing along to (MP3)
//   POST   /api/join/<invite>                 join: an email (kept only to write to them), a name, the release
// As a singer (<sid> is theirs alone, from joining):
//   PUT    /api/take/<sid>                    a take (16-bit mono WAV) with its sidecar (X-Take-Info)
//   POST   /api/words/<sid>                   words for the song, under the words release
//   POST   /api/done/<sid>                    "I'm done" (it closes nothing: they may come back)
//   GET    /y/<sid>                           their own page, and its API:
//   GET    /api/yours/<sid>                   what they sent, their files, the dates
//   GET    /api/yours/<sid>/take/<id>         one take (WAV); /file/<name> their version or vocals
//   DELETE /api/yours/<sid>/take/<id>         delete one take's audio (until DELETE_BY)
//   POST   /api/yours/<sid>/delete            delete all their audio and files (until DELETE_BY)
//   POST   /api/yours/<sid>/withdraw          withdraw: everything, numbers too (until singing closes)
//
// and for the artist, with Authorization: Bearer <ADMIN_TOKEN> (wrangler secret put ADMIN_TOKEN):
//   GET    /api/admin/status                  the dates, and where things stand
//   POST   /api/admin/invites                 make invitations: {count, days, limit, note, people}
//   GET    /api/admin/invites                 every invitation, who joined, their takes
//   POST   /api/admin/revoke/<invite>         close an invitation
//   GET    /api/admin/singers[?emails=1]      every singer (emails only if asked), a page at a time
//   GET    /api/admin/takes[?singer=]         the takes, each a WAV and its sidecar
//   GET    /api/admin/take/<key>              download one (downloading deletes nothing); DELETE deletes it
//   GET    /api/admin/words, /word/<key>      the words people sent
//   GET    /api/admin/gone                    what singers deleted or withdrew, for the artist's copies
//   PUT    /api/admin/file/<sid>/<name>       a singer's version or vocals, for their page; DELETE too
//   POST   /api/admin/sent/<sid>              an email was sent to them: {kind: "link" | "ready"}
//   POST   /api/admin/purge                   the purge below, now (only after DELETE_BY)
//
// Invitations and singers live in KV (INVITES: invite:<token>, singer:<sid>), everything else in a
// private R2 bucket (TAKES): takes/<sid>/, files/<sid>/, words/<sid>/, gone/<sid>/, and small marks
// (closed/<invite>, joined/<invite>/<sid>, emails/<sid>, sent/<sid>, done/<sid>, withdrawn/<sid>,
// limits/<hour>/). Marks go to R2 rather than KV: R2 is the same everywhere at once, and the free plan
// allows KV only 1,000 writes a day. Every hour (the cron in wrangler.toml) the addresses counted for
// joining are forgotten; once DELETE_BY has passed, every take and file is deleted, with the emails of
// everyone who didn't ask to hear when the song is released. Nothing personal is logged: no names,
// no emails, no tokens, no addresses. An address is used only to count requests and joins.

import {
  DEFAULTS, FILE_NAME, MAX_FILE_BYTES, MAX_TAKE_BYTES, MAX_WORDS, SPEC, TAKE_ID, TAKE_KEY, TOKEN, WORDS_KEY,
  checkConsent, checkTake, clampInt, cleanEmail, cleanName, cleanWords, fileAbout, fileKind, fromB64url,
  joinsAllowed, leastSung, moment, newToken, own, parseRange, parseWavHeader, sameSecret, sectionsOf, songIndex,
  specOf, stamp, stampedKey, stateOf, takeKey,
} from "./lib.js";

const KEEP_AFTER_EXPIRY = 90 * 86400; // seconds an invite's record outlives it, for the artist's list
const JOINS_AN_HOUR = 20; // joins from one address in a clock hour (a group link is as good as public); JOINS_AN_HOUR in [vars] changes it
const PUBLIC = { "/sing.js": "text/javascript", "/sing.css": "text/css", "/karaoke.js": "text/javascript",
                 "/recorder.js": "text/javascript", "/yours.js": "text/javascript", "/yours.css": "text/css",
                 "/robots.txt": "text/plain", "/favicon.svg": "image/svg+xml" };

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

function busy() {
  return fail(429, "busy", "Too many requests: wait a minute.");
}

function notice(status, text) {
  // a page with one thing to say: an invitation that isn't open, a private page that doesn't exist
  const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Songbird</title><link rel="stylesheet" href="/sing.css"></head><body><main class="closed"><h1>Songbird</h1><p>${text}</p></main></body></html>`;
  return new Response(html, {
    status,
    headers: headers({ "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Content-Security-Policy": PAGE_CSP,
                       "X-Robots-Tag": "noindex" }),
  });
}

function closedPage(state) {
  return notice(state === "unknown" ? 404 : 410,
    state === "closed" ? "Singing has closed. Thank you to everyone who sang! If you sang, your own page (the link you got when you joined) still works."
      : state === "done" ? "You've finished singing on this invitation. Thank you!"
      : state === "expired" ? "This invitation has expired. If you'd still like to sing, ask the person who sent it for a new one."
      : "This invitation isn't open (it may have been closed, or the link is mistyped). Ask the person who sent it for a new one.");
}

function shut(state) {
  // why an invitation-bound request is refused
  if (state === "closed") return fail(410, "closed", "Singing has closed. Thank you for coming by!");
  return fail(state === "unknown" ? 404 : 410, state, "This invitation isn't open.");
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

/* ---------- the song ---------- */

let SONG = null; // what the worker needs of the built song, read once per isolate
const LYRICS = new Map(); // each guide's sections, read once per isolate

async function song(env, request) {
  // song/worker.json is song.json without the guides' loudness curves: a cold start reads it in well
  // under a millisecond (the free plan allows 10 ms of work a request); song.json does if it's missing
  if (!SONG) {
    const small = await asset(env, request, "/song/worker.json");
    if (small.ok) SONG = songIndex(await small.json());
    else {
      const r = await asset(env, request, "/song/song.json");
      if (!r.ok) throw new Error("the site has no song: build it with tools/sing_site.py");
      SONG = songIndex(await r.json());
    }
  }
  return SONG;
}

async function lyricsOf(env, request, s, spec) {
  if (!LYRICS.has(spec)) {
    const file = String(s.guides[spec].lyrics || "");
    const r = /^[A-Za-z0-9._-]+\.json$/.test(file) ? await asset(env, request, `/song/${file}`) : null;
    if (!r || !r.ok) throw new Error("the site is missing a guide's words: build it again");
    LYRICS.set(spec, sectionsOf(await r.json()));
  }
  return LYRICS.get(spec);
}

let TALLY = null; // seconds sung to each set so far, counted at most once a minute in each isolate
const GUESS = 60; // seconds a singer just given a set counts for, until the next count

async function chooseSet(env, sets, now) {
  // the set with the least singing so far, so every set's words get sung (joins that come to nothing
  // don't count, as they would if sets went round in turn)
  if (sets.length < 2) return sets[0] || null;
  if (!TALLY || now - TALLY.at > 60e3 || !sets.every(s => TALLY.seconds.has(s))) {
    const seconds = new Map(sets.map(s => [s, 0]));
    for (const o of await listed(env, "takes/", ["customMetadata"])) {
      const m = o.customMetadata || {};
      const set = String(m.spec || "").split(".")[0];
      if (o.key.endsWith(".wav") && seconds.has(set)) seconds.set(set, seconds.get(set) + (Number(m.seconds) || 0));
    }
    TALLY = { at: now, seconds };
  }
  const set = leastSung(sets, TALLY.seconds);
  TALLY.seconds.set(set, TALLY.seconds.get(set) + GUESS);
  return set;
}

/* ---------- invitations and singers ---------- */

function dates(env) {
  return { closes: moment(env.CLOSES_AT), deleteBy: moment(env.DELETE_BY) };
}

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

async function singerOf(env, sid) {
  // a singer's record (never their email, which is kept apart), and whether they've withdrawn
  if (!TOKEN.test(sid)) return null;
  const record = await env.INVITES.get(`singer:${sid}`, "json");
  if (record && !record.withdrawn) {
    const gone = await env.TAKES.head(`withdrawn/${sid}`); // as closing, withdrawing is at once everywhere
    if (gone) return { ...record, withdrawn: gone.customMetadata?.at || true };
  }
  return record;
}

async function hashed(text) {
  // 64 bits of SHA-256: enough to tell two things apart, and nothing to read them back from
  const d = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
  return Array.from(d.slice(0, 8), b => b.toString(16).padStart(2, "0")).join("");
}

function plain(text) {
  // words kept in R2's metadata (a lyric's first line, what a file is): percent-encoded, as metadata
  // travels in headers, which carry ASCII safely and anything else less surely
  return encodeURIComponent(String(text ?? ""));
}

function unplain(text) {
  try {
    return decodeURIComponent(String(text ?? ""));
  } catch (e) {
    return String(text ?? "");
  }
}

function sameSite(request) {
  // a browser says where a request comes from: joining, a take, words, "I'm done" and deleting must
  // come from the pages themselves, never from a page elsewhere that learned a link (tools send no
  // such header)
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

async function readJson(request, max) {
  // a small JSON body, read no further than `max` bytes
  if (!request.body) throw new Error("empty");
  const reader = request.body.getReader();
  const chunks = [];
  let n = 0;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    n += value.byteLength;
    if (n > max) {
      reader.cancel().catch(() => {});
      throw new Error("too big");
    }
    chunks.push(value);
  }
  const all = new Uint8Array(n);
  let at = 0;
  for (const c of chunks) { all.set(c, at); at += c.byteLength; }
  const data = JSON.parse(new TextDecoder().decode(all));
  if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("not an object");
  return data;
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

async function deleteKeys(env, keys) {
  for (let i = 0; i < keys.length; i += 1000) await env.TAKES.delete(keys.slice(i, i + 1000));
}

async function event(env, sid, what, take, now) {
  // what a singer deleted or withdrew, for the artist's copies (tools/invite.py sync)
  const at = new Date(now).toISOString();
  await env.TAKES.put(`${stampedKey("gone", sid, new Date(now))}.json`, JSON.stringify({ sid, what, take, at }), {
    httpMetadata: { contentType: "application/json" }, customMetadata: { what, take: take || "", at },
  });
  return at;
}

/* ---------- by invitation ---------- */

async function byInvite(request, env, parts, ip, now) {
  const [kind, token] = parts;
  const inv = await invite(env, token);
  if (!inv && await limited(env.UNKNOWN, `unknown:${ip}`)) return busy();
  const state = stateOf(inv, now, dates(env).closes);

  if (kind === "invite" && request.method === "GET" && parts.length === 2) {
    if (!inv) return fail(404, "unknown", "No such invitation.");
    // people: how many can join with it (a personal link: one person, on up to three devices)
    const joined = (await listed(env, `joined/${token}/`)).length, allowed = joinsAllowed(inv);
    return json({ state, expires: inv.expires, limit: inv.limit, closes: env.CLOSES_AT || null, people: allowed,
                  personal: (inv.people || 1) === 1, joined, room: Math.max(0, allowed - joined), full: joined >= allowed });
  }
  if (state !== "open") return shut(state);

  if (kind === "song" && request.method === "GET" && parts.length === 2) {
    return asset(env, request, "/song/song.json", { "Cache-Control": "no-store", "Content-Type": "application/json; charset=utf-8" });
  }
  if (kind === "lyrics" && request.method === "GET" && parts.length === 3) {
    const s = await song(env, request);
    const file = own(s.guides, parts[2]) ? String(s.guides[parts[2]].lyrics || "") : "";
    if (!/^[A-Za-z0-9._-]+\.json$/.test(file)) return fail(404, "unknown", "No such guide.");
    return asset(env, request, `/song/${file}`, { "Cache-Control": "private, no-cache", "Content-Type": "application/json; charset=utf-8" });
  }
  if (kind === "guide" && request.method === "GET" && parts.length === 4) {
    const s = await song(env, request);
    const g = own(s.guides, parts[2]) ? s.guides[parts[2]] : null;
    const file = g && own(g.mixes, parts[3]) ? String(g.mixes[parts[3]] || "") : "";
    if (!/^[A-Za-z0-9._-]+\.mp3$/.test(file)) return fail(404, "unknown", "No such guide.");
    // no-cache: kept, but checked each time, so a guide made again is never heard stale
    return asset(env, request, `/song/${file}`, { "Cache-Control": "private, no-cache", "Content-Type": "audio/mpeg" });
  }
  if (kind === "join" && request.method === "POST" && parts.length === 2) return join(request, env, token, inv, ip, now);
  return fail(405, "method", "Not here.");
}

async function join(request, env, token, inv, ip, now) {
  if (!sameSite(request)) return fail(403, "site", "Only the singing page can do that.");
  let body;
  try {
    body = await readJson(request, 8192);
  } catch (e) {
    return fail(400, "join", "Your details didn't arrive whole: try again.");
  }
  const s = await song(env, request);
  let email, consent;
  try {
    email = cleanEmail(body.email);
    consent = checkConsent(body.consent, s.consent, now, "release");
  } catch (e) {
    return fail(400, "join", e.message);
  }
  // how often one address joins, per clock hour: a digest of it, forgotten within the hour (the cron)
  const hour = stamp(new Date(now)).slice(0, 11), address = await hashed(`${env.ADMIN_TOKEN || ""}:${ip}`);
  if ((await listed(env, `limits/${hour}/${address}`)).length >= (clampInt(env.JOINS_AN_HOUR, 1, 10000, 0) || JOINS_AN_HOUR)) {
    return fail(429, "busy", "A lot of people have joined from this connection in the last hour. Try again a little later.");
  }
  const joined = await listed(env, `joined/${token}/`, ["customMetadata"]);
  if (joined.length >= joinsAllowed(inv)) {
    return fail(403, "full", (inv.people || 1) > 1 ? "Everyone this link was for has joined. Ask the person who sent it for another."
      : "This link has been used to join three times already. If you've lost your page, ask the person who sent the link.");
  }
  // the same email on the same invitation is the same person (on another device): the artist keeps
  // their takes together; a digest is enough to tell, and the email itself is kept apart
  const mark = await hashed(`${token}:${email.toLowerCase()}`);
  const same = joined.find(o => o.customMetadata && o.customMetadata.h === mark);
  const sid = newToken();
  const person = same ? same.customMetadata.p || same.key.split("/")[2] : sid;
  const set = await chooseSet(env, s.sets, now);
  const record = { v: 2, invite: token, person, created: new Date(now).toISOString(), name: cleanName(body.name),
                   credit: body.credit === true, notify: body.notify === true, set, consent };
  await env.INVITES.put(`singer:${sid}`, JSON.stringify(record));
  await Promise.all([
    env.TAKES.put(`emails/${sid}`, email, { customMetadata: { notify: record.notify ? "1" : "0" } }),
    env.TAKES.put(`joined/${token}/${sid}`, "", { customMetadata: { h: mark, p: person, set: set || "" } }),
    env.TAKES.put(`limits/${hour}/${address}-${newToken().slice(0, 8)}`, ""),
  ]);
  return json({ singer: sid, page: `/y/${sid}`, set, limit: inv.limit });
}

/* ---------- as a singer ---------- */

async function bySinger(request, env, parts, ip, now) {
  const [kind, sid] = parts;
  const who = await singerOf(env, sid);
  if (!who) {
    if (await limited(env.UNKNOWN, `unknown:${ip}`)) return busy();
    return fail(404, "unknown", "No such singer: reload the page.");
  }
  if (!sameSite(request)) return fail(403, "site", "Only the singing page can do that.");
  if (kind === "take" && request.method === "PUT") return take(request, env, sid, who, now);
  if (who.withdrawn) return fail(410, "withdrawn", "You've withdrawn, so nothing more can be sent.");
  if (kind === "done" && request.method === "POST") {
    // only a note for the artist: it closes nothing, so they can still come back and sing more
    const at = new Date(now).toISOString();
    await env.TAKES.put(`done/${sid}`, "", { customMetadata: { at } });
    return json({ state: "done", done: at });
  }
  if (kind === "words" && request.method === "POST") {
    const state = stateOf(await invite(env, who.invite), now, dates(env).closes);
    if (state !== "open") return shut(state);
    return words(request, env, sid, who, now);
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

async function take(request, env, sid, who, now) {
  const declared = request.headers.get("Content-Length"), length = Number(declared);
  if (declared === null || !Number.isInteger(length) || length < 44 || !request.body) return fail(411, "length", "A take must say how long it is.");
  if (length > MAX_TAKE_BYTES) return fail(413, "size", "That take is too big.");
  const reader = request.body.getReader();
  if (await limited(env.UPLOADS, `take:${sid}`)) {
    return drained(reader, fail(429, "busy", "Too many takes at once: wait a minute and send it again."));
  }
  if (who.withdrawn) return drained(reader, fail(410, "withdrawn", "You've withdrawn, so nothing more can be sent."));
  const inv = await invite(env, who.invite);
  const state = stateOf(inv, now, dates(env).closes);
  if (state !== "open") return drained(reader, shut(state));
  const type = (request.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  if (!["audio/wav", "audio/x-wav", "audio/wave"].includes(type)) return drained(reader, fail(415, "type", "A take must be a WAV."));
  const header = request.headers.get("X-Take-Info") || "";
  if (!header || header.length > 4096) return drained(reader, fail(400, "info", "The take's details are missing."));

  const s = await song(env, request);
  let info, spec;
  try {
    info = JSON.parse(new TextDecoder().decode(fromB64url(header)));
    spec = specOf(info, s);
  } catch (e) {
    return drained(reader, fail(400, "take", e instanceof SyntaxError || e instanceof DOMException ? "The take's details can't be read." : e.message));
  }
  let lyric;
  try {
    lyric = await lyricsOf(env, request, s, spec);
  } catch (e) {
    return drained(reader, fail(500, "error", "Something went wrong on our side. Try again in a moment."));
  }
  const sent = (await listed(env, `takes/${sid}/`)).filter(o => o.key.endsWith(".json")).length;
  if (sent >= inv.limit) {
    return drained(reader, fail(403, "limit", `You can keep up to ${inv.limit} takes, and they're all in. Delete one on your page to send another.`));
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
  let checked;
  try {
    checked = checkTake(info, s, spec, lyric, parseWavHeader(head, length));
  } catch (e) {
    return drained(reader, fail(400, "take", e.message));
  }
  const received = new Date(now);
  const key = takeKey(sid, received);
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
  const about = { spec, mix: checked.mix, seconds: String(checked.seconds), section: checked.section === null ? "" : String(checked.section),
                  part: plain(checked.part), label: plain((checked.label || "").slice(0, 120)) }; // for their page and the sets' tally
  try {
    await Promise.all([env.TAKES.put(`${key}.wav`, readable, { sha256: checked.sha256, httpMetadata: { contentType: "audio/wav" },
                                                               customMetadata: about }), pump]);
  } catch (e) {
    return fail(400, "damaged", "The take arrived damaged or cut short: send it again.");
  }
  // who sang it comes from their record: the name they gave, whether to credit it, the release they
  // agreed to when they joined (never their email)
  const sidecar = { ...checked, sid, person: who.person || sid, invite: who.invite, name: who.name || "", credit: who.credit === true,
                    consent: who.consent, received: received.toISOString(), bytes: length, take: sent + 1 };
  await env.TAKES.put(`${key}.json`, JSON.stringify(sidecar), { httpMetadata: { contentType: "application/json" } });
  return json({ ok: true, take: sent + 1, limit: inv.limit });
}

async function words(request, env, sid, who, now) {
  if (await limited(env.UPLOADS, `words:${sid}`)) return fail(429, "busy", "Too many at once: wait a minute and send it again.");
  let body;
  try {
    body = await readJson(request, 32768);
  } catch (e) {
    return fail(400, "words", "Your words didn't arrive whole: try again.");
  }
  const s = await song(env, request);
  let text, release;
  try {
    text = cleanWords(body.text);
    release = checkConsent(body.release, s.words_release, now, "release for words");
  } catch (e) {
    return fail(400, "words", e.message);
  }
  const sent = (await listed(env, `words/${sid}/`)).length;
  if (sent >= MAX_WORDS) return fail(403, "limit", `That's ${MAX_WORDS} already, as many as one person can send. Thank you!`);
  const at = new Date(now).toISOString();
  await env.TAKES.put(`${stampedKey("words", sid, new Date(now))}.json`,
    JSON.stringify({ sid, person: who.person || sid, at, text, release, name: who.name || "", credit: who.credit === true }),
    { httpMetadata: { contentType: "application/json" } });
  return json({ ok: true, words: sent + 1 });
}

/* ---------- their own page ---------- */

async function yours(request, env, parts, ip, now) {
  const [, sid, what, id] = parts; // yours/<sid>[/take/<id> | /file/<name> | /delete | /withdraw]
  const who = await singerOf(env, sid);
  if (!who) {
    if (await limited(env.UNKNOWN, `unknown:${ip}`)) return busy();
    return fail(404, "unknown", "This page doesn't exist.");
  }
  const { closes, deleteBy } = dates(env);
  const deleted = deleteBy !== null && now >= deleteBy;
  const method = request.method;

  if (parts.length === 2 && method === "GET") return json(await summary(env, sid, who, now));
  if ((what === "take" || what === "file") && parts.length === 4 && (method === "GET" || method === "HEAD")) {
    if (who.withdrawn || deleted) return fail(404, "gone", "That's been deleted.");
    if (what === "take") {
      if (!TAKE_ID.test(id)) return fail(404, "unknown", "No such recording.");
      return serve(env, request, `takes/${sid}/${id}.wav`, "audio/wav", `songbird-take-${id.slice(0, 15)}.wav`);
    }
    if (!FILE_NAME.test(id)) return fail(404, "unknown", "No such file.");
    return serve(env, request, `files/${sid}/${id}`, id.endsWith(".mp3") ? "audio/mpeg" : "audio/wav", `songbird-${id}`);
  }
  const changing = (what === "take" && parts.length === 4 && method === "DELETE") ||
                   ((what === "delete" || what === "withdraw") && parts.length === 3 && method === "POST");
  if (!changing) return fail(405, "method", "Not here.");
  if (!sameSite(request)) return fail(403, "site", "Only your page can do that.");
  if (who.withdrawn) return fail(409, "withdrawn", "You've already withdrawn: everything you sent has been deleted.");

  if (what === "withdraw") {
    if (closes !== null && now >= closes) {
      return fail(410, "closed", "Singing has closed and the song has been made from everyone's singing, so what you gave is part of it now. You can still delete your recordings.");
    }
    // the event first: whatever happens next, the artist's copies and numbers go too
    const at = await event(env, sid, "withdrawn", null, now);
    await env.TAKES.put(`withdrawn/${sid}`, "", { customMetadata: { at } });
    const keys = [];
    for (const prefix of [`takes/${sid}/`, `files/${sid}/`, `words/${sid}/`]) keys.push(...(await listed(env, prefix)).map(o => o.key));
    await deleteKeys(env, [...keys, `emails/${sid}`, `sent/${sid}`, `done/${sid}`, `joined/${who.invite}/${sid}`]);
    const { name, credit, notify, consent, ...rest } = who; // what's left: when they came, and that they left
    await env.INVITES.put(`singer:${sid}`, JSON.stringify({ ...rest, withdrawn: at }));
    return json({ state: "withdrawn" });
  }
  if (deleted) return fail(410, "gone", "Your recordings have already been deleted.");
  const files = (await listed(env, `files/${sid}/`)).map(o => o.key);
  if (what === "take") {
    // a version made with this take would still hold it: their files go too, and are made again from
    // what's left
    if (!TAKE_ID.test(id)) return fail(404, "unknown", "No such recording.");
    const [wav, side] = await Promise.all([env.TAKES.head(`takes/${sid}/${id}.wav`), env.TAKES.head(`takes/${sid}/${id}.json`)]);
    if (!wav && !side) return fail(404, "unknown", "That recording has already been deleted.");
    await event(env, sid, "deleted", `takes/${sid}/${id}`, now);
    await deleteKeys(env, [`takes/${sid}/${id}.wav`, `takes/${sid}/${id}.json`, ...files]);
    return json({ deleted: id });
  }
  const takes = (await listed(env, `takes/${sid}/`)).map(o => o.key);
  await event(env, sid, "deleted", null, now);
  await deleteKeys(env, [...takes, ...files]);
  return json({ deleted: takes.filter(k => k.endsWith(".wav")).length + files.length });
}

async function summary(env, sid, who, now) {
  // everything their page shows
  const { closes, deleteBy } = dates(env);
  const [inv, done, takes, files, words] = await Promise.all([
    invite(env, who.invite), env.TAKES.head(`done/${sid}`), listed(env, `takes/${sid}/`, ["customMetadata"]),
    listed(env, `files/${sid}/`, ["customMetadata"]), listed(env, `words/${sid}/`),
  ]);
  const deleted = deleteBy !== null && now >= deleteBy;
  const state = who.withdrawn ? "withdrawn" : deleted ? "deleted" : stateOf(inv, now, closes) === "open" ? "open" : "closed";
  const out = {
    name: who.name || "", credit: who.credit === true, notify: who.notify === true, state,
    done: (done && done.customMetadata && done.customMetadata.at) || null, created: who.created,
    closes: env.CLOSES_AT || null, delete_by: env.DELETE_BY || null,
    can_withdraw: !who.withdrawn && !(closes !== null && now >= closes), limit: (inv && inv.limit) || DEFAULTS.limit,
    takes: [], files: [], words: [], sing_more: state === "open" ? `/i/${who.invite}#s=${sid}` : null,
  };
  if (state === "withdrawn") return out;
  if (!deleted) {
    const start = `takes/${sid}/`.length;
    for (const o of takes) {
      if (!o.key.endsWith(".wav")) continue;
      const m = o.customMetadata || {};
      out.takes.push({ id: o.key.slice(start, -4), seconds: Number(m.seconds) || null,
                       section: m.section === undefined || m.section === "" ? null : Number(m.section),
                       name: unplain(m.part) || null, label: unplain(m.label) || null, spec: m.spec || null, mix: m.mix || null,
                       received: new Date(o.uploaded).toISOString(), bytes: o.size });
    }
    out.takes.sort((a, b) => a.received.localeCompare(b.received) || a.id.localeCompare(b.id)); // two in one second, in the order they came
    for (const o of files) {
      const name = o.key.slice(`files/${sid}/`.length);
      out.files.push({ name, kind: fileKind(name), about: unplain(o.customMetadata && o.customMetadata.about) || fileAbout(name),
                       bytes: o.size, made: new Date(o.uploaded).toISOString() });
    }
  }
  const sent = await Promise.all(words.slice(0, MAX_WORDS).map(async o => {
    const w = await env.TAKES.get(o.key);
    return w ? w.json() : null;
  }));
  out.words = sent.filter(Boolean).map(w => ({ at: w.at, text: w.text }));
  return out;
}

async function serve(env, request, key, type, name) {
  // a take or file, whole or the range asked for (an audio element asks for ranges), to play or download
  const url = new URL(request.url);
  const extra = { "Content-Type": type, "Cache-Control": "private, no-store", "Accept-Ranges": "bytes" };
  if (url.searchParams.get("download") === "1") extra["Content-Disposition"] = `attachment; filename="${name}"`;
  const head = await env.TAKES.head(key);
  if (!head) return fail(404, "unknown", "That's been deleted.");
  const span = parseRange(request.headers.get("Range"), head.size);
  if (span === "bad") return new Response(null, { status: 416, headers: headers({ "Content-Range": `bytes */${head.size}` }) });
  if (request.method === "HEAD") return new Response(null, { headers: headers({ ...extra, "Content-Length": String(head.size) }) });
  const o = await env.TAKES.get(key, span ? { range: { offset: span[0], length: span[1] - span[0] + 1 } } : {});
  if (!o) return fail(404, "unknown", "That's been deleted.");
  if (!span) return new Response(o.body, { headers: headers({ ...extra, "Content-Length": String(head.size) }) });
  return new Response(o.body, {
    status: 206, headers: headers({ ...extra, "Content-Range": `bytes ${span[0]}-${span[1]}/${head.size}`,
                                    "Content-Length": String(span[1] - span[0] + 1) }),
  });
}

/* ---------- the artist's routes ---------- */

async function admin(request, env, parts, now) {
  const secret = env.ADMIN_TOKEN || "";
  if (secret.length < 32) return fail(503, "admin", "Set ADMIN_TOKEN (wrangler secret put ADMIN_TOKEN) to use the admin API.");
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ") || !sameSecret(auth.slice(7), secret)) return fail(401, "auth", "Not allowed.");
  const [what, rest] = [parts[0], parts.slice(1).join("/")];
  const url = new URL(request.url), method = request.method;
  const { closes, deleteBy } = dates(env);
  const deleted = deleteBy !== null && now >= deleteBy;

  if (what === "status" && method === "GET") {
    return json({ closes: env.CLOSES_AT || null, delete_by: env.DELETE_BY || null, now: new Date(now).toISOString(),
                  closed: closes !== null && now >= closes, deleting: deleted });
  }
  if (what === "invites" && method === "POST") {
    let body = {};
    try { body = await readJson(request, 8192); } catch (e) { /* defaults */ }
    const count = clampInt(body.count ?? 1, 1, 50, 1), days = clampInt(body.days ?? DEFAULTS.days, 1, 60, DEFAULTS.days);
    const limit = clampInt(body.limit ?? DEFAULTS.limit, 1, 200, DEFAULTS.limit);
    const people = clampInt(body.people ?? DEFAULTS.people, 1, 1000, DEFAULTS.people);
    const note = cleanName(String(body.note ?? "")).slice(0, 80);
    const created = new Date(now), expires = new Date(created.getTime() + days * 86400e3);
    const made = [];
    for (let i = 0; i < count; i++) {
      const token = newToken();
      const record = { v: 2, created: created.toISOString(), expires: expires.toISOString(), limit, note, state: "open", people };
      await saveInvite(env, token, record);
      made.push({ token, url: `${url.origin}/i/${token}`, ...record });
    }
    return json({ invites: made });
  }
  if (what === "invites" && method === "GET") {
    const closed = {}, joined = {}, takes = {};
    for (const o of await listed(env, "closed/", ["customMetadata"])) {
      closed[o.key.slice(7)] = { state: o.customMetadata?.state || "done", closed: o.customMetadata?.at };
    }
    for (const o of await listed(env, "takes/")) if (o.key.endsWith(".json")) takes[o.key.split("/")[1]] = (takes[o.key.split("/")[1]] || 0) + 1;
    for (const o of await listed(env, "joined/")) (joined[o.key.split("/")[1]] ||= []).push(o.key.split("/")[2]);
    const out = [];
    let cursor;
    do {
      const page = await env.INVITES.list({ prefix: "invite:", cursor });
      for (const k of page.keys) {
        const token = k.name.slice(7);
        let record = k.metadata && k.metadata.expires ? k.metadata : await env.INVITES.get(k.name, "json");
        if (record && record.state === "open" && closed[token]) record = { ...record, ...closed[token] };
        if (record) {
          const sids = joined[token] || [];
          out.push({ token, url: `${url.origin}/i/${token}`, ...record, people: record.people || 1, state: stateOf(record, now, closes),
                     joined: sids.length, takes: sids.reduce((n, sid) => n + (takes[sid] || 0), 0) });
        }
      }
      cursor = page.list_complete ? undefined : page.cursor;
    } while (cursor);
    out.sort((a, b) => a.created.localeCompare(b.created));
    return json({ invites: out });
  }
  if (what === "revoke" && method === "POST") {
    const inv = await invite(env, rest);
    if (!inv) return fail(404, "unknown", "No such invitation.");
    await close(env, rest, inv, "revoked");
    return json({ state: "revoked" });
  }
  if (what === "singers" && method === "GET") {
    // a page of singers at a time (their records are read one by one): follow "cursor" for the rest
    const emails = url.searchParams.get("emails") === "1";
    const page = await env.INVITES.list({ prefix: "singer:", cursor: url.searchParams.get("cursor") || undefined, limit: 100 });
    const counts = { takes: {}, words: {} }, files = {}, sent = {}, done = {}, left = {};
    for (const kind of ["takes", "words"]) {
      for (const o of await listed(env, `${kind}/`)) if (o.key.endsWith(".json")) counts[kind][o.key.split("/")[1]] = (counts[kind][o.key.split("/")[1]] || 0) + 1;
    }
    for (const o of await listed(env, "files/", ["customMetadata"])) {
      const [, sid, name] = o.key.split("/");
      (files[sid] ||= []).push({ name, kind: fileKind(name), about: unplain(o.customMetadata?.about) || fileAbout(name), bytes: o.size,
                                 made: new Date(o.uploaded).toISOString() });
    }
    for (const o of await listed(env, "sent/", ["customMetadata"])) sent[o.key.slice(5)] = o.customMetadata || {};
    for (const o of await listed(env, "done/", ["customMetadata"])) done[o.key.slice(5)] = o.customMetadata?.at || null;
    for (const o of await listed(env, "withdrawn/", ["customMetadata"])) left[o.key.slice(10)] = o.customMetadata?.at || true;
    const out = await Promise.all(page.keys.map(async k => {
      const sid = k.name.slice(7), rec = await env.INVITES.get(k.name, "json");
      if (!rec) return null;
      const withdrawn = rec.withdrawn || left[sid];
      const entry = { sid, person: rec.person || sid, page: `${url.origin}/y/${sid}`, invite: rec.invite, created: rec.created,
                      name: rec.name || "", credit: rec.credit === true, notify: rec.notify === true, set: rec.set || null,
                      state: withdrawn ? "withdrawn" : "open", done: done[sid] || null, takes: counts.takes[sid] || 0,
                      words: counts.words[sid] || 0, files: files[sid] || [],
                      sent: { link: sent[sid]?.link || null, ready: sent[sid]?.ready || null } };
      if (emails) {
        const o = withdrawn ? null : await env.TAKES.get(`emails/${sid}`);
        entry.email = o ? await o.text() : null;
      }
      return entry;
    }));
    return json({ singers: out.filter(Boolean).sort((a, b) => a.created.localeCompare(b.created)),
                  cursor: page.list_complete ? null : page.cursor, dates: { closes: env.CLOSES_AT || null, delete_by: env.DELETE_BY || null } });
  }
  if (what === "takes" && method === "GET") {
    const only = url.searchParams.get("singer");
    if (only && !TOKEN.test(only)) return fail(400, "singer", "Not a singer.");
    const takes = {};
    for (const o of await listed(env, only ? `takes/${only}/` : "takes/")) {
      const id = o.key.replace(/\.(wav|json)$/, "");
      const t = takes[id] || (takes[id] = { id, singer: o.key.split("/")[1] });
      t[o.key.endsWith(".wav") ? "wav" : "json"] = { key: o.key, size: o.size, uploaded: o.uploaded };
    }
    return json({ takes: Object.values(takes).sort((a, b) => a.id.localeCompare(b.id)) });
  }
  if (what === "take" && (method === "GET" || method === "DELETE")) {
    if (!TAKE_KEY.test(rest)) return fail(400, "key", "Not a take.");
    if (method === "DELETE") {
      await env.TAKES.delete(rest);
      return json({ deleted: rest });
    }
    const o = await env.TAKES.get(rest);
    if (!o) return fail(404, "unknown", "No such take.");
    return new Response(o.body, { headers: headers({ "Content-Type": rest.endsWith(".wav") ? "audio/wav" : "application/json",
                                                     "Content-Length": String(o.size), "Cache-Control": "no-store" }) });
  }
  if (what === "words" && method === "GET") {
    const out = (await listed(env, "words/")).map(o => ({ key: o.key, singer: o.key.split("/")[1], size: o.size, uploaded: o.uploaded }));
    return json({ words: out });
  }
  if (what === "word" && method === "GET") {
    if (!WORDS_KEY.test(rest)) return fail(400, "key", "Not someone's words.");
    const o = await env.TAKES.get(rest);
    if (!o) return fail(404, "unknown", "No such words.");
    return json(await o.json());
  }
  if (what === "gone" && method === "GET") {
    const out = (await listed(env, "gone/", ["customMetadata"])).map(o => ({
      key: o.key, singer: o.key.split("/")[1], what: o.customMetadata?.what || null, take: o.customMetadata?.take || null,
      at: o.customMetadata?.at || new Date(o.uploaded).toISOString(),
    }));
    return json({ gone: out.sort((a, b) => a.at.localeCompare(b.at) || a.key.localeCompare(b.key)) });
  }
  if (what === "file" && parts.length === 3 && (method === "PUT" || method === "DELETE")) {
    const [sid, name] = [parts[1], parts[2]];
    if (!TOKEN.test(sid) || !FILE_NAME.test(name)) return fail(400, "file", "Not a singer's file.");
    if (method === "DELETE") {
      await env.TAKES.delete(`files/${sid}/${name}`);
      return json({ deleted: name });
    }
    const who = await singerOf(env, sid);
    if (!who) return fail(404, "unknown", "No such singer.");
    if (who.withdrawn) return fail(409, "withdrawn", "They've withdrawn.");
    if (deleted) return fail(410, "gone", "It's past DELETE_BY: their recordings, and files made from them, are deleted.");
    const length = Number(request.headers.get("Content-Length"));
    if (!Number.isInteger(length) || length < 1 || !request.body) return fail(411, "length", "A file must say how long it is.");
    if (length > MAX_FILE_BYTES) return fail(413, "size", "That file is too big.");
    const spec = url.searchParams.get("spec") || "";
    if (spec && !SPEC.test(spec)) return fail(400, "spec", "Not a guide.");
    const about = cleanName(url.searchParams.get("about") || "") || fileAbout(name);
    const { readable, writable } = new FixedLengthStream(length);
    try {
      await Promise.all([env.TAKES.put(`files/${sid}/${name}`, readable, {
        httpMetadata: { contentType: name.endsWith(".mp3") ? "audio/mpeg" : "audio/wav" }, customMetadata: { about: plain(about), spec },
      }), request.body.pipeTo(writable)]);
    } catch (e) {
      return fail(400, "damaged", "The file arrived cut short: send it again.");
    }
    return json({ ok: true, name, bytes: length });
  }
  if (what === "sent" && method === "POST" && parts.length === 2) {
    const sid = parts[1];
    let body = {};
    try { body = await readJson(request, 1024); } catch (e) { /* refused below */ }
    if (!["link", "ready"].includes(body.kind)) return fail(400, "kind", "Say which email: link or ready.");
    if (!await singerOf(env, sid)) return fail(404, "unknown", "No such singer.");
    const o = await env.TAKES.head(`sent/${sid}`);
    const m = { link: o?.customMetadata?.link || "", ready: o?.customMetadata?.ready || "" };
    m[body.kind] = new Date(now).toISOString();
    await env.TAKES.put(`sent/${sid}`, "", { customMetadata: m });
    return json({ sent: { link: m.link || null, ready: m.ready || null } });
  }
  if (what === "purge" && method === "POST") {
    if (!deleted) return fail(409, "early", "It isn't DELETE_BY yet: nothing is deleted before then.");
    return json(await purge(env));
  }
  return fail(404, "unknown", "No such thing.");
}

/* ---------- every hour ---------- */

async function tidy(env, now) {
  // forget which addresses joined in hours gone by; once DELETE_BY has passed, the purge
  const hour = stamp(new Date(now)).slice(0, 11);
  await deleteKeys(env, (await listed(env, "limits/")).map(o => o.key).filter(k => k.slice(7, 18) < hour));
  const deleteBy = moment(env.DELETE_BY);
  return deleteBy !== null && now >= deleteBy ? purge(env) : null;
}

async function purge(env) {
  // every take and file, the emails of everyone who didn't ask to hear when the song is released, and
  // the marks that told one person's joins apart (each holds a digest of an email). What's left: their
  // records (a name to credit), the words they gave the song, and what they deleted or withdrew.
  const takes = (await listed(env, "takes/")).map(o => o.key);
  const files = (await listed(env, "files/")).map(o => o.key);
  const emails = (await listed(env, "emails/", ["customMetadata"])).filter(o => o.customMetadata?.notify !== "1").map(o => o.key);
  const joined = (await listed(env, "joined/")).map(o => o.key);
  await deleteKeys(env, [...takes, ...files, ...emails, ...joined]);
  return { takes: takes.filter(k => k.endsWith(".wav")).length, files: files.length, emails: emails.length, more: false };
}

/* ---------- the way in ---------- */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const ip = request.headers.get("CF-Connecting-IP") || "local"; // only ever a key for counting requests
    const now = Date.now();
    try {
      if (path.startsWith("/api/") || path.startsWith("/i/") || path.startsWith("/y/")) {
        if (await limited(env.REQUESTS, `ip:${ip}`)) return busy();
      }
      if (path.startsWith("/i/")) {
        const token = path.slice(3);
        const inv = await invite(env, token);
        if (!inv && await limited(env.UNKNOWN, `unknown:${ip}`)) return busy();
        const state = stateOf(inv, now, dates(env).closes);
        if (state !== "open" || !["GET", "HEAD"].includes(request.method)) return closedPage(state);
        return asset(env, request, "/index.html", { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                                                  "Content-Security-Policy": PAGE_CSP, "X-Robots-Tag": "noindex" });
      }
      if (path.startsWith("/y/")) {
        const sid = path.slice(3);
        const known = TOKEN.test(sid) && await env.INVITES.get(`singer:${sid}`) !== null;
        if (!known) {
          if (await limited(env.UNKNOWN, `unknown:${ip}`)) return busy();
          return notice(404, "This page doesn't exist. Check the link you were given when you joined.");
        }
        if (!["GET", "HEAD"].includes(request.method)) return fail(405, "method", "Not here.");
        return asset(env, request, "/yours.html", { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store",
                                                  "Content-Security-Policy": PAGE_CSP, "X-Robots-Tag": "noindex" });
      }
      if (path.startsWith("/api/admin/")) return await admin(request, env, path.slice(11).split("/"), now);
      if (path.startsWith("/api/")) {
        const parts = path.slice(5).split("/");
        if (["invite", "song", "lyrics", "guide", "join"].includes(parts[0]) && parts.length >= 2 && parts.length <= 4) {
          return await byInvite(request, env, parts, ip, now);
        }
        if (["take", "words", "done"].includes(parts[0]) && parts.length === 2) return await bySinger(request, env, parts, ip, now);
        if (parts[0] === "yours" && parts.length >= 2 && parts.length <= 4) return await yours(request, env, parts, ip, now);
        return fail(404, "unknown", "No such thing.");
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

  async scheduled(controller, env, ctx) {
    ctx.waitUntil(tidy(env, controller.scheduledTime || Date.now()).catch(e => console.error("songbird-sing: tidy", e && e.name)));
  },
};
