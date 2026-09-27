// Run with: node --test tests/test_studio_drafts.cjs
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const {resolve} = require("node:path");
const vm = require("node:vm");
const context = {module: {exports: {}}, document: {getElementById: () => null}, TextEncoder};
vm.runInNewContext(readFileSync(resolve(__dirname, "../songbird/studio/drafts.js"), "utf8"), context);
const {readDraft} = context.module.exports;
const make = (edits = {}) => ({format: "songbird-studio-draft", version: 1, song: "song-hash", edits});

test("portable drafts round trip lyrics, timing, pitch, and deliberate resets", () => {
  const edits = {tempo: 90, "tune.v1": [{degree: 2, onset: -0.5, duration: 0.5}], "words.verse.0": {id: "wire"}, "form.order": null};
  assert.equal(JSON.stringify(readDraft(JSON.stringify(make(edits)), "song-hash")), JSON.stringify(edits));
});

test("foreign songs and future formats cannot overwrite the open draft", () => {
  assert.throws(() => readDraft(JSON.stringify(make()), "different-song"), /different song/);
  assert.throws(() => readDraft(JSON.stringify({...make(), version: 2}), "song-hash"), /supported/);
  assert.throws(() => readDraft("not json", "song-hash"), /JSON/);
  assert.throws(() => readDraft(JSON.stringify(make([])), "song-hash"), /map/);
});

test("untrusted drafts are bounded and reject prototype keys", () => {
  assert.throws(() => readDraft(JSON.stringify(make({text: "x".repeat(512 * 1024)})), "song-hash"), /too large/);
  const polluted = JSON.parse('{"__proto__":{"polluted":true}}');
  assert.throws(() => readDraft(JSON.stringify(make(polluted)), "song-hash"), /invalid choice/);
  assert.equal({}.polluted, undefined);
});
