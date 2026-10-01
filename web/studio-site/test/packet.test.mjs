// A shared version checked as data: what a rendition is (the seed itself, if it's built), and every way a file
// isn't one, each refused with its sentence; only the head, the tail and manifest.json are ever read.
// npm test
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { MANIFEST, packet, streaminfo } from "./fixture.mjs";
import { MAX_BYTES, Refused, checkVersion } from "../src/packet.js";

function readers(bytes) {
  const reads = [];
  return {
    reads,
    read: async (offset, length) => { reads.push([offset, length]); return bytes.slice(offset, offset + length); },
    tail: async length => { reads.push([bytes.length - length, length]); return bytes.slice(bytes.length - length); },
  };
}

async function check(bytes) {
  const r = readers(bytes);
  return checkVersion(bytes.length, r.read, r.tail);
}

async function refused(bytes, pattern) {
  await assert.rejects(check(bytes), e => e instanceof Refused && pattern.test(e.message), String(pattern));
}

test("a rendition is a version: its record's id, title and place in the line", async () => {
  assert.deepEqual(await check(packet()), { id: "a".repeat(64), title: "Now It's by You", generation: 1, parent_id: "b".repeat(64) });
  assert.equal((await check(packet({ manifest: { ...MANIFEST, generation: 0, parent_id: null, ancestry: [] } }))).generation, 0);
  assert.equal((await check(packet({ comment: "a comment ends it" }))).id, "a".repeat(64)); // the end record's comment
  // a directory too far from the end to be in the tail is read by itself
  const long = packet({ entries: [...Array(200)].map((_, i) => ({ name: `program/f${i}-${"x".repeat(180)}.py`, data: "" }))
    .concat([{ name: "manifest.json", data: JSON.stringify(MANIFEST) }, { name: "genome.json", data: "{}" }]) });
  assert.equal((await check(long)).id, "a".repeat(64));
});

// the seed as tools/sing_site.py builds it (or any rendition: SONGBIRD_SEED=path/to/a.flac npm test)
const SEED = process.env.SONGBIRD_SEED || new URL("../../sing/public/seed/now-its-by-you.flac", import.meta.url).pathname;
test("the seed rendition, as built for now.itsby.you", { skip: !existsSync(SEED) && "the seed site isn't built" }, async () => {
  const bytes = new Uint8Array(readFileSync(SEED));
  const got = await check(bytes);
  assert.equal(got.generation, 0);
  assert.match(got.id, /^[0-9a-f]{64}$/);
});

test("only the head, the end and manifest.json are read: nothing else in the packet, never its program", async () => {
  const bytes = packet();
  const r = readers(bytes);
  await checkVersion(bytes.length, r.read, r.tail);
  const text = new TextDecoder("latin1").decode(bytes);
  const main = text.indexOf("__main__.py"), program = text.indexOf("program/songbird/__init__.py");
  const manifest = text.indexOf("manifest.json") - 30;
  assert.deepEqual(r.reads[0], [0, 42]);
  for (const [offset, length] of r.reads.slice(2)) assert.equal(offset, manifest); // the manifest's own entry
  // the tail is the file's last 64 KB (here the whole packet, which is small); the program is never read by itself
  assert.ok(!r.reads.slice(2).some(([o]) => o === main - 30 || o === program - 30));
  assert.equal(r.reads.length, 3);
});

test("not a rendition: refused, in a sentence, for each way", async () => {
  await refused(new Uint8Array(5000), /isn't a FLAC/);
  await refused(packet({ head: new TextEncoder().encode("ID3\x04".padEnd(42, "\0")) }), /isn't a FLAC/);
  await refused(packet({ head: streaminfo({ rate: 48000 }) }), /44\.1 kHz, stereo/);
  await refused(packet({ head: streaminfo({ channels: 1 }) }), /44\.1 kHz, stereo/);
  await refused(packet().slice(0, 4096), /carries no packet/); // a FLAC without its packet
  await refused(new Uint8Array([...packet(), 1, 2, 3]), /doesn't end where/); // something after the archive
  await refused(packet({ tweak: { cdStart: 100 } }), /directory isn't where/);
  await refused(packet({ tweak: { total: 0 } }), /ZIP64, or empty/);
  await refused(packet({ tweak: { cdSize: 0xffffffff } }), /ZIP64/);
  await refused(packet({ tweak: { total: 600 } }), /lists 600 files/);
  const entries = n => [{ name: "manifest.json", data: JSON.stringify(MANIFEST) }, { name: "genome.json", data: "{}" }, ...n];
  await refused(packet({ entries: entries([{ name: "../escape.py", data: "x" }]) }), /named "\.\.\/escape\.py"/);
  await refused(packet({ entries: entries([{ name: "/etc/passwd", data: "x" }]) }), /named "\/etc\/passwd"/);
  await refused(packet({ entries: entries([{ name: "a\\b.py", data: "x" }]) }), /named/);
  await refused(packet({ entries: entries([{ name: "a//b.py", data: "x" }]) }), /named/);
  await refused(packet({ entries: entries([{ name: "genome.json", data: "{}" }]) }), /same file twice/);
  await refused(packet({ entries: entries([{ name: "x", data: "x", central: { flags: 1 } }]) }), /encrypted/);
  await refused(packet({ entries: entries([{ name: "x", data: "x", central: { flags: 8 } }]) }), /data descriptors/);
  await refused(packet({ entries: entries([{ name: "x", data: "x", method: 12 }]) }), /compressed in a way/);
  await refused(packet({ entries: entries([{ name: "bomb", data: "x", central: { size: 2 ** 21 } }]) }), /grow \d+ times over/);
  await refused(packet({ entries: entries([{ name: "big", data: new Uint8Array(110 * 1024), method: 0, central: { size: 101 * 2 ** 20 } }]) }), /larger than a whole/);
  await refused(packet({ entries: entries([{ name: "x", data: "x", central: { offset: 10 } }]) }), /aren't where a rendition keeps/);
  await refused(packet({ entries: [{ name: "genome.json", data: "{}" }] }), /carries no packet/);
  await refused(packet({ entries: [{ name: "manifest.json", data: JSON.stringify(MANIFEST) }] }), /no song/);
});

test("its record: read through a bounded stream, and held to a rendition's", async () => {
  const one = (manifest, extra = {}) => packet({ entries: [{ name: "manifest.json", data: manifest, ...extra }, { name: "genome.json", data: "{}" }] });
  let x = 1;
  const noise = Array.from({ length: 2 ** 20 + 1 }, () => String.fromCharCode(33 + ((x = (x * 48271) % 2147483647) % 90))).join("");
  await refused(one(noise), /manifest\.json is 1024 KB/); // declared too large
  await refused(one(JSON.stringify(MANIFEST), { central: { size: 10 } }), /damaged|larger than it says/); // inflates past what it says
  await refused(one(JSON.stringify(MANIFEST), { central: { crc: 1 } }), /damaged/);
  await refused(one("not json"), /isn't JSON/);
  await refused(one("[1, 2]"), /isn't a record/);
  await refused(one(JSON.stringify({ ...MANIFEST, id: "nope" })), /has no id/);
  await refused(one(JSON.stringify({ ...MANIFEST, program_sha256: undefined })), /which program made it/);
  await refused(one(JSON.stringify({ ...MANIFEST, title: "" })), /no title/);
  await refused(one(JSON.stringify({ ...MANIFEST, generation: "1" })), /generation/);
  await refused(one(JSON.stringify({ ...MANIFEST, generation: -1 })), /generation/);
  await refused(one(JSON.stringify({ ...MANIFEST, parent_id: 7 })), /parent isn't an id/);
  await refused(one(JSON.stringify({ ...MANIFEST, ancestry: ["x"] })), /ancestry/);
  await refused(one("[".repeat(100000) + "]".repeat(100000)), /isn't JSON|isn't a record/); // deep nesting
  // its local header must name it and sit where the directory says
  await refused(one(JSON.stringify(MANIFEST), { central: { offset: 42 + 20000 + 1 } }), /aren't where its directory says/);
});

test("the size bounds", async () => {
  assert.equal(MAX_BYTES, 64 * 2 ** 20); // as songbird/received.py's UPLOAD, so the page and the host agree
  await refused(new Uint8Array(100), /too small/);
});
