// The studio's Worker against bindings in memory: sharing a version (checked, kept under its content address, with
// or without the page's digest), its limits (size, the page only, per minute, per hour, from everywhere), fetching
// it (whole, in ranges, unchanged), /v/<id>, the rest of /api/, and the hourly tidy that keeps versions 30 days
// after they were last opened.
// npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { Limiter, MANIFEST, PAGE_HTML, context, env, packet, sha256 } from "./fixture.mjs";
import { PAGE_POLICY } from "../src/policy.js";

let isolates = 0;
async function load() {
  return (await import(`../src/worker.js?isolate=${++isolates}`)).default;
}

async function call(w, e, path, init = {}, ctx = context()) {
  const r = await w.fetch(new Request(`https://studio.test${path}`, init), e, ctx);
  await Promise.all(ctx.waits);
  return r;
}

async function share(w, e, bytes, { digest = true, headers = {}, ip = "203.0.113.5" } = {}) {
  const r = await call(w, e, "/api/versions", {
    method: "POST", body: bytes,
    headers: { "Content-Type": "audio/flac", "Content-Length": String(bytes.length), "CF-Connecting-IP": ip,
               "Sec-Fetch-Site": "same-origin", Origin: "https://studio.test", ...(digest ? { "X-Content-SHA256": sha256(bytes) } : {}), ...headers },
  });
  return { status: r.status, data: await r.json(), headers: r.headers };
}

const unread = () => new ReadableStream({ pull() { throw new Error("the body was read"); } });

test("a version shared with its digest: kept under its content address, R2 checking the bytes, and served back", async () => {
  const w = await load(), e = env();
  const bytes = packet();
  const r = await share(w, e, bytes);
  const id = sha256(bytes).slice(0, 32);
  assert.equal(r.status, 201);
  assert.deepEqual(r.data, { id, url: `/v/${id}` });
  assert.equal(r.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(e.VERSIONS.keys("versions/"), [`versions/${id}.flac`]);
  assert.deepEqual(e.VERSIONS.objects.get(`versions/${id}.flac`).bytes, bytes);
  assert.equal(e.VERSIONS.objects.get(`versions/${id}.flac`).httpMetadata.contentType, "audio/flac");

  const got = await call(w, e, `/api/versions/${id}`);
  assert.equal(got.status, 200);
  assert.deepEqual(new Uint8Array(await got.arrayBuffer()), bytes);
  assert.equal(got.headers.get("Content-Type"), "audio/flac");
  assert.equal(got.headers.get("Content-Length"), String(bytes.length));
  assert.equal(got.headers.get("Cache-Control"), "public, max-age=31536000, immutable");
  assert.equal(got.headers.get("ETag"), `"${id}"`);
  assert.equal(got.headers.get("X-Content-Type-Options"), "nosniff");
  assert.equal(got.headers.get("Content-Security-Policy"), "default-src 'none'; sandbox");
  assert.equal(got.headers.get("Content-Disposition"), `attachment; filename="songbird-${id}.flac"`);
  assert.equal(got.headers.get("Access-Control-Allow-Origin"), null); // no other site's page reads it

  // the same file again is the same version
  assert.deepEqual((await share(w, e, bytes)).data, { id, url: `/v/${id}` });
  assert.equal(e.VERSIONS.keys("versions/").length, 1);
});

test("without the page's digest the Worker hashes it: the same id, and nothing left incoming", async () => {
  const w = await load(), e = env();
  const bytes = packet({ audio: 300000 });
  const r = await share(w, e, bytes, { digest: false });
  assert.equal(r.status, 201);
  assert.equal(r.data.id, sha256(bytes).slice(0, 32));
  assert.deepEqual(e.VERSIONS.keys("versions/"), [`versions/${r.data.id}.flac`]);
  assert.deepEqual(e.VERSIONS.keys("incoming/"), []);
  const bad = await share(w, e, packet({ manifest: "nope" }), { digest: false });
  assert.equal(bad.status, 422);
  assert.deepEqual(e.VERSIONS.keys("incoming/"), []);
  assert.equal(e.VERSIONS.keys("versions/").length, 1);
});

test("what isn't a version is refused with a sentence, and not kept", async () => {
  const w = await load(), e = env();
  for (const [bytes, pattern] of [[packet({ manifest: { ...MANIFEST, id: "x" } }), /has no id/], [new Uint8Array(5000).fill(1), /isn't a FLAC/],
                                  [packet().slice(0, 9000), /carries no packet/]]) {
    const r = await share(w, e, bytes);
    assert.equal(r.status, 422);
    assert.deepEqual(Object.keys(r.data), ["error"]);
    assert.match(r.data.error, pattern);
  }
  assert.deepEqual(e.VERSIONS.keys("versions/"), []);
  // a digest that isn't the file's: R2 refuses the bytes, and whatever was there stays
  const bytes = packet();
  await share(w, e, bytes);
  const other = packet({ audio: 30000 });
  const r = await share(w, e, other, { headers: { "X-Content-SHA256": sha256(bytes) } });
  assert.equal(r.status, 400);
  assert.match(r.data.error, /didn't arrive whole, or isn't the one/);
  assert.deepEqual(e.VERSIONS.objects.get(`versions/${sha256(bytes).slice(0, 32)}.flac`).bytes, bytes);
  assert.equal((await share(w, e, bytes, { headers: { "X-Content-SHA256": "abc" } })).status, 400);
});

test("nothing unchecked is ever under a version's name: checked in incoming/, whatever stops the Worker", async () => {
  const w = await load(), e = env();
  const bytes = packet();
  const get = e.VERSIONS.get.bind(e.VERSIONS);
  let seen = null;
  e.VERSIONS.get = async (key, opts) => { // R2 failing in the middle of the check
    if (key.startsWith("incoming/") && opts && opts.range) {
      seen = e.VERSIONS.keys("versions/");
      throw new Error("R2 down");
    }
    return get(key, opts);
  };
  const r = await share(w, e, bytes);
  assert.equal(r.status, 500);
  assert.deepEqual(seen, []); // while it was being checked, nothing under versions/
  assert.deepEqual(e.VERSIONS.keys("versions/"), []);
  assert.deepEqual(e.VERSIONS.keys("incoming/"), []);
  assert.equal(e.VERSIONS.keys("limits/").filter(k => k.includes("/kept-")).length, 0);
});

test("its size is asked before a byte is read: too big, too small, unsaid", async () => {
  const w = await load(), e = env();
  const post = headers => call(w, e, "/api/versions", { method: "POST", body: unread(), duplex: "half", headers: { "Sec-Fetch-Site": "same-origin", ...headers } });
  const big = await post({ "Content-Length": String(64 * 2 ** 20 + 1) });
  assert.equal(big.status, 413);
  assert.match((await big.json()).error, /at most 64 MB/);
  assert.equal((await post({ "Content-Length": "100" })).status, 400);
  assert.equal((await post({})).status, 411);
  assert.equal((await post({ "Content-Length": "1e9" })).status, 411);
  assert.equal(e.VERSIONS.puts, 0);
});

test("only the studio's own page shares: another site's is refused before anything", async () => {
  const w = await load(), e = env();
  const bytes = packet();
  assert.equal((await share(w, e, bytes, { headers: { "Sec-Fetch-Site": "cross-site" } })).status, 403);
  assert.equal((await share(w, e, bytes, { headers: { "Sec-Fetch-Site": "same-site" } })).status, 403);
  assert.equal((await share(w, e, bytes, { headers: { Origin: "https://elsewhere.example" } })).status, 403);
  assert.equal(e.VERSIONS.puts, 0);
  const tool = await call(w, e, "/api/versions", { method: "POST", body: bytes, headers: { "Content-Length": String(bytes.length) } });
  assert.equal(tool.status, 201); // a tool says neither
});

test("the limits: a few a minute and so many tries an hour from one address (an IPv6 one by its /64), so many kept from everywhere", async () => {
  const w = await load(), mod = await import(`../src/worker.js?isolate=${++isolates}`);
  let e = env({ UPLOADS: new Limiter(3) });
  for (let i = 0; i < 3; i++) assert.equal((await share(w, e, packet({ audio: 20000 + i }))).status, 201);
  const minute = await share(w, e, packet({ audio: 20010 }));
  assert.equal(minute.status, 429);
  assert.match(minute.data.error, /wait a minute/);

  e = env({ UPLOADS_AN_HOUR: "2", ALL_AN_HOUR: "3" });
  const a = "2001:db8:1:2:aaaa::1", b = "2001:db8:1:2:bbbb::2", c = "2001:db8:9:9::1";
  assert.equal((await share(w, e, packet({ audio: 20001 }), { ip: a })).status, 201);
  assert.equal((await share(w, e, new Uint8Array(5000), { ip: b })).status, 422); // a refused file counts too
  const hour = await share(w, e, packet({ audio: 20002 }), { ip: a });
  assert.equal(hour.status, 429); // the same /64
  assert.match(hour.data.error, /in an hour/);
  assert.equal(hour.headers.get("Retry-After"), "3600");
  for (let i = 0; i < 6; i++) { // junk from many places doesn't close sharing for everyone
    assert.equal((await share(w, e, new Uint8Array(5000), { ip: `198.51.100.${100 + i}` })).status, 422);
  }
  assert.equal((await share(w, e, packet({ audio: 20003 }), { ip: c })).status, 201);
  assert.equal((await share(w, e, packet({ audio: 20004 }), { ip: "198.51.100.7" })).status, 201);
  const all = await share(w, e, packet({ audio: 20005 }), { ip: "198.51.100.8" }); // three kept this hour
  assert.equal(all.status, 429);
  assert.match(all.data.error, /Many versions/);
  // what's counted: 64 bits of an HMAC of the address under the site's own key, never the address
  const marks = e.VERSIONS.keys("limits/");
  assert.equal(marks.filter(k => k.includes("/kept-")).length, 3);
  assert.equal(marks.filter(k => !k.includes("/kept-")).length, 10); // a, b, six junk, c, and one more
  for (const k of marks) assert.match(k, /^limits\/\d{4}-\d\d-\d\dT\d\d\/([0-9a-f]{16}|kept)-[0-9a-f]{8}$/);
  assert.ok(!marks.join().includes("2001") && !marks.join().includes("198.51"));
  assert.match(new TextDecoder().decode(e.VERSIONS.objects.get("keys/address").bytes), /^[0-9a-f]{64}$/);
  assert.equal((await mod.tidy(e, Date.now())).marks, 0); // this hour's stay; the key is never tidied
  assert.ok(e.VERSIONS.objects.has("keys/address"));
});

test("a shared version: in ranges, unchanged, HEAD, and nothing to find by guessing", async () => {
  const w = await load(), e = env();
  const bytes = packet();
  const { id } = (await share(w, e, bytes)).data;
  const part = await call(w, e, `/api/versions/${id}`, { headers: { Range: "bytes=4-11" } });
  assert.equal(part.status, 206);
  assert.equal(part.headers.get("Content-Range"), `bytes 4-11/${bytes.length}`);
  assert.deepEqual(new Uint8Array(await part.arrayBuffer()), bytes.slice(4, 12));
  const last = await call(w, e, `/api/versions/${id}`, { headers: { Range: "bytes=-10" } });
  assert.deepEqual(new Uint8Array(await last.arrayBuffer()), bytes.slice(-10));
  assert.equal((await call(w, e, `/api/versions/${id}`, { headers: { Range: `bytes=${bytes.length}-` } })).status, 416);
  const head = await call(w, e, `/api/versions/${id}`, { method: "HEAD" });
  assert.equal(head.status, 200);
  assert.equal(head.headers.get("Content-Length"), String(bytes.length));
  const same = await call(w, e, `/api/versions/${id}`, { headers: { "If-None-Match": `"${id}"` } });
  assert.equal(same.status, 304);
  assert.equal((await call(w, e, `/api/versions/${id}`, { method: "DELETE" })).status, 405);

  const gone = "0".repeat(32);
  assert.equal((await call(w, e, `/api/versions/${gone}`, { headers: { "If-None-Match": `"${gone}"` } })).status, 404); // a copy kept is no proof it's here
  const missing = await call(w, e, `/api/versions/${"0".repeat(32)}`);
  assert.equal(missing.status, 404);
  assert.match((await missing.json()).error, /no version here/);
  for (const path of [`/api/versions/${id.toUpperCase()}`, `/api/versions/${id}0`, `/api/versions/${id}/x`, "/api/versions/../wrangler.toml",
                      "/api/versions/", "/api/open", "/api/admin/status", "/api/"]) {
    const r = await call(w, e, path);
    assert.equal(r.status, 404, path);
    assert.ok((await r.json()).error, path);
  }
  assert.equal((await call(w, e, "/api/versions")).status, 405); // nothing lists them
  // asking after versions that aren't there, again and again, is held back
  const guess = env({ UNKNOWN: new Limiter(2) });
  const asks = [];
  for (let i = 0; i < 3; i++) asks.push((await call(w, guess, `/api/versions/${String(i).repeat(32)}`)).status);
  assert.deepEqual(asks, [404, 404, 429]);
});

test("/v/<id> is the studio's page, with its policy; anything else under /v/ isn't", async () => {
  const w = await load(), e = env();
  const id = "0123456789abcdef0123456789abcdef";
  const r = await call(w, e, `/v/${id}`);
  assert.equal(r.status, 200);
  assert.equal(await r.text(), PAGE_HTML);
  assert.equal(r.headers.get("Content-Security-Policy"), PAGE_POLICY);
  assert.match(PAGE_POLICY, /script-src 'self' 'wasm-unsafe-eval' https:\/\/static\.cloudflareinsights\.com;/);
  // Cloudflare Web Analytics, the zone's beacon: its script and its report, those two hosts and no other
  assert.match(PAGE_POLICY, /connect-src 'self' https:\/\/cloudflareinsights\.com;/);
  assert.deepEqual(PAGE_POLICY.match(/https:\/\/[^ ;]+/g), ["https://static.cloudflareinsights.com", "https://cloudflareinsights.com"]);
  assert.match(PAGE_POLICY, /media-src 'self' blob:;/);
  assert.doesNotMatch(PAGE_POLICY, /'unsafe-eval'|'unsafe-inline'|\*/);
  assert.equal(r.headers.get("Cache-Control"), "no-cache");
  assert.equal(r.headers.get("X-Frame-Options"), "DENY");
  assert.equal(r.headers.get("X-Robots-Tag"), null); // the public studio may be found
  assert.equal((await call(w, e, `/v/${id}`, { method: "HEAD" })).status, 200);
  let asked = null;
  const assets = e.ASSETS.fetch;
  e.ASSETS.fetch = async req => { asked = req.headers.get("If-None-Match"); return assets(req); };
  await call(w, e, `/v/${id}`, { headers: { "If-None-Match": '"page"' } }); // revalidated as / is
  assert.equal(asked, '"page"');
  e.ASSETS.fetch = assets;
  assert.equal((await call(w, e, `/v/${id}`, { method: "POST" })).status, 405);
  for (const path of ["/v/nope", `/v/${id}/`, `/v/${id}/studio.js`, "/v/"]) assert.equal((await call(w, e, path)).status, 404, path);
  assert.equal((await call(w, e, "/robots.txt")).status, 404); // no robots.txt (the static assets have none)
});

test("kept 30 days after it was last shared or opened (an open noted at most weekly, so up to a week more), and the hour's counts forgotten", async () => {
  const w = await load(), e = env();
  const mod = await import(`../src/worker.js?isolate=${++isolates}`);
  const fresh = (await share(w, e, packet({ audio: 20001 }))).data.id;
  const old = (await share(w, e, packet({ audio: 20002 }))).data.id;
  const opened = (await share(w, e, packet({ audio: 20003 }))).data.id;
  const now = Date.now();
  e.VERSIONS.age(`versions/${fresh}.flac`, 36); // shared 36 days ago: within 30 + 7
  e.VERSIONS.age(`versions/${old}.flac`, 38);
  e.VERSIONS.age(`versions/${opened}.flac`, 40);
  const same = await call(w, e, `/api/versions/${opened}`, { headers: { "If-None-Match": `"${opened}"` } }); // a browser that has it
  assert.equal(same.status, 304);
  assert.deepEqual(e.VERSIONS.keys("opened/"), [`opened/${opened}`]); // it isn't sent the bytes, but it is an open
  e.VERSIONS.objects.delete(`opened/${opened}`);
  await call(w, e, `/api/versions/${opened}`, { method: "HEAD" }); // the page opening the one it keeps: noted
  assert.deepEqual(e.VERSIONS.keys("opened/"), [`opened/${opened}`]);
  const puts = e.VERSIONS.puts;
  await call(w, e, `/api/versions/${opened}`, { headers: { Range: "bytes=0-3" } }); // again this week: no write
  assert.equal(e.VERSIONS.puts, puts);

  await e.VERSIONS.put("limits/2001-01-01T00/abc-1", "");
  await e.VERSIONS.put("incoming/stale", "x");
  e.VERSIONS.age("incoming/stale", 1);
  await e.VERSIONS.put("incoming/now", "x");
  const marksNow = e.VERSIONS.keys("limits/").filter(k => !k.startsWith("limits/2001"));
  const done = await mod.tidy(e, now);
  assert.deepEqual(done, { versions: 1, marks: 1, incoming: 1 });
  assert.deepEqual(e.VERSIONS.keys("versions/").sort(), [`versions/${fresh}.flac`, `versions/${opened}.flac`].sort());
  assert.deepEqual(e.VERSIONS.keys("limits/"), marksNow); // this hour's stay
  assert.deepEqual(e.VERSIONS.keys("incoming/"), ["incoming/now"]);
  e.VERSIONS.age(`opened/${opened}`, 38);
  await mod.tidy(e, now);
  assert.deepEqual(e.VERSIONS.keys("versions/"), [`versions/${fresh}.flac`]);
  assert.deepEqual(e.VERSIONS.keys("opened/"), []);
  assert.equal((await call(w, e, `/api/versions/${old}`)).status, 404);

  // shared again between the tidy's listing and its deleting: it stays; an open noted for a version gone, goes
  const again = (await share(w, e, packet({ audio: 20004 }))).data.id;
  e.VERSIONS.age(`versions/${again}.flac`, 40);
  const list = e.VERSIONS.list.bind(e.VERSIONS);
  e.VERSIONS.list = async opts => {
    const out = await list(opts);
    if (opts.prefix === "versions/") e.VERSIONS.objects.get(`versions/${again}.flac`).uploaded = new Date(now);
    return out;
  };
  await e.VERSIONS.put(`opened/${"9".repeat(32)}`, "");
  assert.equal((await mod.tidy(e, now)).versions, 0);
  e.VERSIONS.list = list;
  assert.ok(e.VERSIONS.objects.has(`versions/${again}.flac`));
  assert.ok(!e.VERSIONS.objects.has(`opened/${"9".repeat(32)}`));
  await e.VERSIONS.delete(`versions/${again}.flac`);

  // the cron runs it
  const ctx = context();
  await w.scheduled({ scheduledTime: now + 2 * 86400e3 }, e, ctx);
  await Promise.all(ctx.waits);
  assert.deepEqual(e.VERSIONS.keys("versions/"), []);
});

test("the rest is the static site's, untouched; something broken says so plainly", async () => {
  const w = await load(), e = env();
  assert.equal(await (await call(w, e, "/")).text(), PAGE_HTML); // (the static assets answer this before the Worker)
  assert.equal((await call(w, e, "/nothing.js")).status, 404);
  const broken = env({ VERSIONS: { list: async () => { throw new Error("down"); }, head: async () => { throw new Error("down"); } } });
  const r = await call(w, broken, `/api/versions/${"a".repeat(32)}`);
  assert.equal(r.status, 500);
  assert.deepEqual(await r.json(), { error: "Something went wrong on our side. Try again in a moment." });
  assert.equal((await share(w, broken, packet())).status, 500);
});

test("an address counted by its /64", async () => {
  const { addressOf } = await import(`../src/worker.js?isolate=${++isolates}`);
  assert.equal(addressOf("203.0.113.5"), "203.0.113.5");
  assert.equal(addressOf("2001:db8:1:2:aaaa::1"), "2001:db8:1:2::/64");
  assert.equal(addressOf("2001:0DB8:0001:0002:0:0:0:1"), "2001:db8:1:2::/64");
  assert.equal(addressOf("2001:db8::1"), "2001:db8:0:0::/64");
  assert.equal(addressOf("::1"), "0:0:0:0::/64");
});
