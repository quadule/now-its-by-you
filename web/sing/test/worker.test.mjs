// The worker's routes against fake bindings: what wrangler dev can't show (KV is consistent there).
// npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import worker from "../src/worker.js";

const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWx";
const SONG = { song: "h", guide: "86341ecd9a2a", consent: "896e20c8603e", max_seconds: 210, mixes: { melody: { file: "melody.mp3" } } };

function env({ record, marker } = {}) {
  // KV that still says "open" (stale, as it can be elsewhere for a minute), and an R2 bucket that may
  // hold the marker closing it
  const kv = new Map(record ? [[`invite:${TOKEN}`, JSON.stringify(record)]] : []);
  return {
    INVITES: {
      get: async (key, kind) => (kv.has(key) ? (kind === "json" ? JSON.parse(kv.get(key)) : kv.get(key)) : null),
      put: async (key, value) => { kv.set(key, value); },
      list: async () => ({ keys: [], list_complete: true }),
    },
    TAKES: {
      head: async key => (marker && key === `closed/${TOKEN}` ? { customMetadata: marker } : null),
      put: async () => {},
      list: async () => ({ objects: [], truncated: false }),
    },
    ASSETS: {
      fetch: async req => {
        const path = new URL(req.url).pathname;
        if (path === "/song/song.json") return new Response(JSON.stringify(SONG));
        if (path === "/index.html") return new Response("<!doctype html><title>page</title>");
        return new Response("no", { status: 404 });
      },
    },
  };
}

const OPEN = { v: 1, created: "2026-09-01T00:00:00.000Z", expires: "2099-01-01T00:00:00.000Z", limit: 30, note: "", state: "open" };

async function call(path, bindings, init = {}) {
  return worker.fetch(new Request(`https://songbird.test${path}`, init), bindings);
}

test("an invitation closed in R2 is closed, whatever KV still says", async () => {
  const closed = env({ record: OPEN, marker: { state: "revoked", at: "2026-09-26T10:00:00.000Z" } });
  const r = await call(`/api/invite/${TOKEN}`, closed);
  assert.equal((await r.json()).state, "revoked");
  assert.equal((await call(`/i/${TOKEN}`, closed)).status, 410);
  assert.equal((await call(`/api/guide/${TOKEN}/melody`, closed)).status, 410);
  const open = env({ record: OPEN });
  assert.equal((await (await call(`/api/invite/${TOKEN}`, open)).json()).state, "open");
  const page = await call(`/i/${TOKEN}`, open);
  assert.equal(page.status, 200);
  assert.match(page.headers.get("Content-Security-Policy"), /script-src 'self'/);
  assert.equal(page.headers.get("Strict-Transport-Security"), "max-age=15552000");
  assert.equal((await call(`/i/${TOKEN}`, open, { method: "HEAD" })).status, 200); // link previews look first
});

test("only the page itself sends a take or closes its invitation", async () => {
  const open = env({ record: OPEN });
  for (const [method, kind] of [["PUT", "take"], ["POST", "done"]]) {
    const r = await call(`/api/${kind}/${TOKEN}`, open, { method, headers: { "Sec-Fetch-Site": "cross-site" } });
    assert.equal(r.status, 403, kind);
  }
  const done = await call(`/api/done/${TOKEN}`, open, { method: "POST", headers: { "Sec-Fetch-Site": "same-origin" } });
  assert.equal((await done.json()).state, "done");
});

test("a take must say how long it is", async () => {
  const r = await call(`/api/take/${TOKEN}`, env({ record: OPEN }), {
    method: "PUT", headers: { "Content-Type": "audio/wav", "X-Take-Info": "e30" }, body: new ReadableStream(), duplex: "half",
  });
  assert.equal(r.status, 411);
});

test("unknown invitations, the song's files and the admin API give nothing away", async () => {
  const none = env();
  assert.equal((await call(`/i/${"Z".repeat(24)}`, none)).status, 404);
  assert.equal((await call("/i/../../etc/passwd", none)).status, 404);
  assert.equal((await call("/song/song.json", none)).status, 404);
  assert.equal((await call("/api/admin/invites", { ...none, ADMIN_TOKEN: "x".repeat(40) })).status, 401);
  assert.equal((await call("/api/admin/invites", none)).status, 503); // no secret set yet
});
