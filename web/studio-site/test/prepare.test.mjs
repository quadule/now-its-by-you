// tools/prepare.mjs: the built site's _headers (immutable for hashed folders, no-cache for the page and the bundle's
// manifest, the page's policy everywhere, no rule setting a header another sets), its .assetsignore, site.json
// checked against the rules, and a site the static assets can't serve refused.
// npm test
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, truncateSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { cacheOf, disagreements, hashedFolder, headersFile, ignored, prepare } from "../tools/prepare.mjs";
import { PAGE_POLICY } from "../src/policy.js";

const PATHS = ["/index.html", "/studio.js", "/render/bundle.json", "/render/py-0a1b2c3d4e5f/pyodide.asm.wasm",
               "/render/py-0a1b2c3d4e5f/numpy-2.whl", "/render/app-99887766aabb/studio-worker.mjs", "/render/app-99887766aabb/kernels/k.mjs"];

function rules(text) {
  // _headers as {pattern: {header: value}}, refusing a header set twice for one pattern
  const out = {};
  let at = null;
  for (const line of text.split("\n")) {
    if (!line.trim() || line.startsWith("#")) continue;
    if (!line.startsWith(" ")) { at = line; assert.ok(!out[at], `${at} twice`); out[at] = {}; continue; }
    const [k, ...v] = line.trim().split(": ");
    assert.ok(!(k in out[at]), `${at}: ${k} twice`);
    out[at][k] = v.join(": ");
  }
  return out;
}

test("which files are for good: those in a folder named by a hash", () => {
  assert.equal(hashedFolder("/render/py-0a1b2c3d4e5f/pyodide.asm.wasm"), "/render/py-0a1b2c3d4e5f");
  assert.equal(hashedFolder("/render/app-99887766aabb/kernels/k.mjs"), "/render/app-99887766aabb");
  assert.equal(hashedFolder("/render/bundle.json"), null);
  assert.equal(hashedFolder("/index.html"), null);
  assert.equal(hashedFolder("/render/py-latest/x.js"), null); // not a hash
  assert.equal(hashedFolder("/render/app-99887766aabb"), null); // a file named like one isn't in one
  assert.equal(cacheOf("/render/py-0a1b2c3d4e5f/a.zip"), "public, max-age=31536000, immutable");
  assert.equal(cacheOf("/render/bundle.json"), "no-cache");
  assert.ok(ignored("/render/py-0a1b2c3d4e5f/pyodide.asm.wasm.gz") && ignored("/site.json") && !ignored("/render/bundle.json"));
});

test("_headers: the page's policy everywhere, immutable hashed folders, no-cache for what names them", () => {
  const r = rules(headersFile(PATHS));
  assert.deepEqual(Object.keys(r), ["/*", "/render/app-99887766aabb/*", "/render/py-0a1b2c3d4e5f/*", "/", "/index.html", "/render/bundle.json"]);
  assert.equal(r["/*"]["Content-Security-Policy"], PAGE_POLICY);
  assert.equal(r["/*"]["X-Content-Type-Options"], "nosniff");
  assert.equal(r["/*"]["Strict-Transport-Security"], "max-age=15552000");
  assert.ok(!("Cache-Control" in r["/*"])); // so no Cache-Control is ever joined from two rules
  assert.ok(!("X-Robots-Tag" in r["/*"])); // the public studio may be found
  for (const folder of ["/render/app-99887766aabb/*", "/render/py-0a1b2c3d4e5f/*"]) {
    assert.deepEqual(r[folder], { "Cache-Control": "public, max-age=31536000, immutable" });
  }
  for (const page of ["/", "/index.html", "/render/bundle.json"]) assert.deepEqual(r[page], { "Cache-Control": "no-cache" });
});

test("site.json is held to the rules, whichever shape it takes", () => {
  const good = { files: { "index.html": { cache: "no-cache", type: "text/html" }, "render/py-0a1b2c3d4e5f/a.wasm": { cache: "public, max-age=31536000, immutable" } } };
  assert.deepEqual(disagreements(good), []);
  assert.deepEqual(disagreements({ files: [{ path: "/render/bundle.json", cache: "no-cache" }] }), []);
  const bad = disagreements({ "render/bundle.json": { cache_control: "public, max-age=31536000, immutable" }, "studio.js": { cache: "immutable" } });
  assert.equal(bad.length, 2);
  assert.match(bad[0], /\/render\/bundle\.json: site\.json says/);
});

test("a built site readied: _headers and .assetsignore written; refused when the static assets couldn't serve it", () => {
  const dir = mkdtempSync(join(tmpdir(), "studio-site-"));
  assert.throws(() => prepare(dir), /no index\.html: build the site first/);
  for (const p of PATHS) {
    mkdirSync(join(dir, p, ".."), { recursive: true });
    writeFileSync(join(dir, p), p);
  }
  writeFileSync(join(dir, "render/py-0a1b2c3d4e5f/pyodide.asm.wasm.gz"), "gz");
  writeFileSync(join(dir, "site.json"), JSON.stringify({ files: { "index.html": { cache: "no-cache" } } }));
  assert.deepEqual(prepare(dir), { files: PATHS.length, bytes: PATHS.join("").length });
  assert.equal(readFileSync(join(dir, "_headers"), "utf8"), headersFile(PATHS));
  assert.deepEqual(readFileSync(join(dir, ".assetsignore"), "utf8").trim().split("\n"), ["*.gz", "site.json", ".DS_Store", "_headers", ".assetsignore"]);
  assert.equal(prepare(dir).files, PATHS.length); // again: its own files aren't counted

  writeFileSync(join(dir, "site.json"), JSON.stringify({ files: { "studio.js": { cache: "immutable" } } }));
  assert.throws(() => prepare(dir), /site\.json and the header rules disagree/);
  writeFileSync(join(dir, "site.json"), "{}");
  writeFileSync(join(dir, "render/py-0a1b2c3d4e5f/huge.wasm"), "");
  truncateSync(join(dir, "render/py-0a1b2c3d4e5f/huge.wasm"), 26 * 2 ** 20); // sparse: 26 MiB that take no room
  assert.throws(() => prepare(dir), /over the static assets' 25 MiB a file: \/render\/py-0a1b2c3d4e5f\/huge\.wasm/);
});
