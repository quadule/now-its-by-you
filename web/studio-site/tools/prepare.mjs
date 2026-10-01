// Readies a built studio site (uv run python web/studio-wasm/tools/build_site.py DIR) for Workers Static Assets:
// writes DIR/_headers (each file's headers: the page's policy and security headers everywhere, immutable for a
// hashed folder's files, no-cache for the page and the bundle's manifest) and DIR/.assetsignore (the .gz copies,
// which the static assets wouldn't send as gzip anyway: Cloudflare compresses text and wasm itself; and
// site.json), and refuses a site the static assets can't serve: a file over 25 MiB, more than 20,000 files, a
// cache policy in site.json that the rules below would serve differently.
//
// usage: node tools/prepare.mjs DIR      (wrangler.toml's [build] runs it before every deploy and dev)

import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { PAGE } from "../src/policy.js";

export const IMMUTABLE = "public, max-age=31536000, immutable";
export const NO_CACHE = "no-cache";
export const HASHED = /^[a-z][a-z0-9]*-[0-9a-f]{8,}$/; // a folder named by a hash of its files: render/py-1a2b3c4d…
export const MAX_FILE = 25 * 2 ** 20; // Workers Static Assets' limit for one file
export const MAX_FILES = 20000; // ... and for one version's files, on the free plan
export const IGNORED = ["*.gz", "site.json", ".DS_Store", "_headers", ".assetsignore"];
const NO_CACHE_PATHS = ["/", "/index.html", "/render/bundle.json"]; // the names that say which hashed folders are current

export function ignored(path) {
  const name = path.split("/").pop();
  return name.endsWith(".gz") || ["site.json", ".DS_Store", "_headers", ".assetsignore"].includes(name);
}

export function hashedFolder(path) {
  // the hashed folder a file lies in ("/render/app-1a2b3c4d"), or null: the folder nearest the root
  const parts = path.split("/").filter(Boolean);
  for (let i = 0; i < parts.length - 1; i++) if (HASHED.test(parts[i])) return "/" + parts.slice(0, i + 1).join("/");
  return null;
}

export function cacheOf(path) {
  // what the rules below serve a file with: immutable in a hashed folder, else no-cache (Workers Static Assets'
  // own default, public, max-age=0, must-revalidate, is the same thing: kept, checked each time by its ETag)
  return hashedFolder(path) ? IMMUTABLE : NO_CACHE;
}

export function siteFiles(site) {
  // site.json's files as [path, {cache, type}]: {"files": {path: {...}}}, {"files": [{path, ...}]} or {path: {...}}
  const files = site && (site.files ?? site.paths ?? site);
  const entries = Array.isArray(files) ? files.map(f => [f.path, f]) : Object.entries(files || {});
  return entries.filter(([p, f]) => typeof p === "string" && f && typeof f === "object")
    .map(([p, f]) => ["/" + p.replace(/^\/+/, ""), { cache: String(f.cache ?? f.cache_control ?? f["Cache-Control"] ?? ""), type: f.type ?? f.content_type }]);
}

export function disagreements(site) {
  // site.json's policies the rules would serve otherwise: "immutable" must be in a hashed folder, anything else not
  const out = [];
  for (const [path, f] of siteFiles(site)) {
    if (!f.cache || ignored(path)) continue;
    const wants = /immutable/.test(f.cache) ? IMMUTABLE : NO_CACHE;
    if (wants !== cacheOf(path)) out.push(`${path}: site.json says "${f.cache}", the rules would serve "${cacheOf(path)}"`);
  }
  return out;
}

export function headersFile(paths) {
  // _headers: one rule for everything (no other rule sets these, so nothing is joined), one per hashed folder, and
  // no-cache for the page and the bundle's manifest (Workers Static Assets allows 100 rules)
  const folders = [...new Set(paths.map(hashedFolder).filter(Boolean))].sort();
  const lines = ["# Written by web/studio-site/tools/prepare.mjs from the built site: don't edit (build it again).", "/*"];
  for (const [k, v] of Object.entries(PAGE)) lines.push(`  ${k}: ${v}`);
  for (const folder of folders) lines.push(`${folder}/*`, `  Cache-Control: ${IMMUTABLE}`);
  for (const path of NO_CACHE_PATHS) lines.push(path, `  Cache-Control: ${NO_CACHE}`);
  if (folders.length + NO_CACHE_PATHS.length + 1 > 100) throw new Error(`${folders.length} hashed folders: more rules than _headers allows`);
  return lines.join("\n") + "\n";
}

function walk(dir, root = dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name), st = statSync(full);
    if (st.isDirectory()) walk(full, root, out);
    else out.push({ path: "/" + relative(root, full).split(sep).join("/"), size: st.size });
  }
  return out;
}

export function prepare(dir) {
  if (!existsSync(join(dir, "index.html"))) {
    throw new Error(`${dir} has no index.html: build the site first (uv run python web/studio-wasm/tools/build_site.py ${dir})`);
  }
  const files = walk(dir).filter(f => !ignored(f.path));
  const big = files.filter(f => f.size > MAX_FILE);
  if (big.length) throw new Error(`over the static assets' 25 MiB a file: ${big.map(f => `${f.path} (${(f.size / 2 ** 20).toFixed(1)} MiB)`).join(", ")}`);
  if (files.length > MAX_FILES) throw new Error(`${files.length} files: the static assets serve at most ${MAX_FILES}`);
  if (files.some(f => f.path === "/robots.txt")) console.warn("prepare: the site has a robots.txt; the artist wants none on the public site");
  if (existsSync(join(dir, "site.json"))) {
    const wrong = disagreements(JSON.parse(readFileSync(join(dir, "site.json"), "utf8")));
    if (wrong.length) throw new Error(`site.json and the header rules disagree:\n  ${wrong.join("\n  ")}`);
  }
  writeFileSync(join(dir, "_headers"), headersFile(files.map(f => f.path)));
  writeFileSync(join(dir, ".assetsignore"), IGNORED.join("\n") + "\n");
  const bytes = files.reduce((a, f) => a + f.size, 0);
  return { files: files.length, bytes };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const dir = process.argv[2];
  if (!dir) {
    console.error("usage: node tools/prepare.mjs DIR");
    process.exit(2);
  }
  try {
    const { files, bytes } = prepare(dir);
    console.log(`prepare: ${dir}: ${files} files, ${(bytes / 2 ** 20).toFixed(1)} MiB; _headers and .assetsignore written`);
  } catch (e) {
    console.error(`prepare: ${e.message}`);
    process.exit(1);
  }
}
