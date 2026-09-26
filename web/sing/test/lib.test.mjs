// The worker's pure parts (src/lib.js): tokens, the WAV a take must be, its sidecar, an invite's state.
// npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_TAKE_BYTES, TAKE_KEY, TOKEN, b64url, checkInfo, clampInt, cleanName, fromB64url, newToken, parseWav, parseWavHeader,
  sameSecret, stateOf,
  takeKey,
} from "../src/lib.js";
import { wavBytes } from "../../../tools/karaoke.js";

const SONG = { song: "h-now-its-by-you", guide: "86341ecd9a2a", consent: "896e20c8603e", max_seconds: 210,
               mixes: { melody: {}, full: {} } };

function info(extra = {}) {
  return { song: SONG.song, guide: SONG.guide, mix: "melody", rate: 48000, name: "Ana", credit: true,
           consent: { agreed: true, at: new Date().toISOString(), text: SONG.consent }, shift_ms: 12, sha256: "ab".repeat(32),
           ...extra };
}

test("a token is 144 random bits, URL-safe, never the same twice", () => {
  const seen = new Set();
  for (let i = 0; i < 500; i++) {
    const t = newToken();
    assert.match(t, TOKEN);
    assert.equal(fromB64url(t).length, 18);
    seen.add(t);
  }
  assert.equal(seen.size, 500);
  assert.doesNotMatch("../../etc/passwd", TOKEN);
  assert.doesNotMatch("abc", TOKEN);
});

test("base64url carries any text through a header", () => {
  const text = JSON.stringify({ name: "Zoë — ☃ 名前" });
  const round = new TextDecoder().decode(fromB64url(b64url(new TextEncoder().encode(text))));
  assert.equal(round, text);
});

test("the admin secret is compared whole, and never empty", () => {
  assert.ok(sameSecret("a".repeat(40), "a".repeat(40)));
  assert.ok(!sameSecret("a".repeat(40), "a".repeat(39) + "b"));
  assert.ok(!sameSecret("a".repeat(40), "a".repeat(41)));
  assert.ok(!sameSecret("", ""));
});

test("an invite is open until it expires, is done, or is revoked", () => {
  const now = Date.parse("2026-10-01T12:00:00Z");
  const open = { state: "open", expires: "2026-10-02T12:00:00Z" };
  assert.equal(stateOf(open, now), "open");
  assert.equal(stateOf({ ...open, expires: "2026-10-01T11:59:59Z" }, now), "expired");
  assert.equal(stateOf({ ...open, state: "done" }, now), "done");
  assert.equal(stateOf({ ...open, state: "revoked" }, now), "revoked");
  assert.equal(stateOf(null, now), "unknown");
});

test("a take must be the plain 16-bit mono WAV the page writes", () => {
  const samples = new Float32Array(48000 * 4).map((_, i) => Math.sin(i / 10) * 0.5);
  const good = wavBytes(samples, 48000);
  assert.deepEqual(parseWav(good), { rate: 48000, samples: samples.length, seconds: 4 });

  const broken = (edit) => { const b = good.slice(0); edit(new DataView(b)); return b; };
  assert.throws(() => parseWav(good.slice(0, 40)), /too short/);
  assert.throws(() => parseWav(good.slice(0, good.byteLength - 2)), /RIFF size/);
  assert.throws(() => parseWav(broken(v => v.setUint16(22, 2, true))), /16-bit mono/); // stereo
  assert.throws(() => parseWav(broken(v => v.setUint16(34, 24, true))), /16-bit mono/);
  assert.throws(() => parseWav(broken(v => v.setUint16(20, 3, true))), /16-bit mono/); // float
  assert.throws(() => parseWav(broken(v => { v.setUint32(24, 12345, true); v.setUint32(28, 24690, true); })), /sample rate/);
  assert.throws(() => parseWav(broken(v => v.setUint32(40, 10, true))), /data size/);
  assert.throws(() => parseWav(broken(v => v.setUint8(0, 0x58))), /plain WAV/);
  // the first 44 bytes and the length it declares are enough: the rest streams past
  assert.deepEqual(parseWavHeader(new Uint8Array(good, 0, 64), good.byteLength), parseWav(good));
  assert.throws(() => parseWavHeader(new Uint8Array(good, 0, 44), good.byteLength + 2), /RIFF size/); // declares more than it is
  assert.throws(() => parseWavHeader(new Uint8Array(good, 0, 30), good.byteLength), /too short/);
  assert.ok(MAX_TAKE_BYTES > 96000 * 2 * 200);
});

test("a take's sidecar is checked against the song it was sung to", () => {
  const wav = { rate: 48000, samples: 48000 * 60, seconds: 60 };
  const out = checkInfo({ ...info(), extra: "dropped", ua: "Mozilla" }, SONG, wav);
  assert.equal(out.mix, "melody");
  assert.equal(out.name, "Ana");
  assert.equal(out.credit, true);
  assert.equal(out.shift_ms, 12);
  assert.equal(out.extra, undefined);
  assert.equal(out.ua, undefined);
  assert.equal(out.sha256, "ab".repeat(32));
  assert.throws(() => checkInfo(info({ sha256: undefined }), SONG, wav), /checksum/);
  assert.throws(() => checkInfo(info({ sha256: "AB".repeat(32) }), SONG, wav), /checksum/);

  assert.throws(() => checkInfo({ ...info(), consent: { agreed: false } }, SONG, wav), /release/);
  assert.throws(() => checkInfo(info({ consent: { agreed: true, at: new Date().toISOString(), text: "000000000000" } }), SONG, wav), /release has changed/);
  assert.throws(() => checkInfo(info({ consent: { agreed: true, at: "yesterday-ish", text: SONG.consent } }), SONG, wav), /clock/);
  const early = new Date(Date.now() - 90 * 86400e3).toISOString();
  assert.throws(() => checkInfo(info({ consent: { agreed: true, at: early, text: SONG.consent } }), SONG, wav), /clock/);
  assert.throws(() => checkInfo(info({ guide: "000000000000" }), SONG, wav), /song has changed/);
  assert.throws(() => checkInfo(info({ mix: "kazoo" }), SONG, wav), /no such guide/);
  assert.throws(() => checkInfo(info({ mix: "__proto__" }), SONG, wav), /no such guide/);
  assert.throws(() => checkInfo(info({ rate: 44100 }), SONG, wav), /sample rate/);
  assert.throws(() => checkInfo(info(), SONG, { ...wav, seconds: 2 }), /too short/);
  assert.throws(() => checkInfo(info(), SONG, { ...wav, seconds: 300 }), /longer than the song/);
  assert.throws(() => checkInfo(info({ shift_ms: 1e9 }), SONG, wav), /out of range/);
  assert.throws(() => checkInfo(info({ shift_ms: "NaN" }), SONG, wav), /out of range/);
  assert.throws(() => checkInfo([], SONG, wav), /missing/);
});

test("names are printable text, trimmed and short", () => {
  assert.equal(cleanName("  Ana\u0000 María\u202e "), "Ana María");
  assert.equal(cleanName("Jo\u200b\u2066e\u2069"), "Joe"); // invisible and direction marks go too
  assert.equal(cleanName("x".repeat(200)).length, 80);
  assert.equal(cleanName(undefined), "");
  assert.equal(cleanName("<b>Jo</b>"), "<b>Jo</b>"); // kept as text: nothing renders it as HTML
});

test("a take's key is its invite, its time and a little chance, and nothing else", () => {
  const token = newToken();
  const key = takeKey(token, new Date("2026-10-01T12:34:56.789Z"));
  assert.match(`${key}.wav`, TAKE_KEY);
  assert.ok(key.startsWith(`takes/${token}/20261001T123456Z-`));
  assert.doesNotMatch(`takes/${token}/../../secret.wav`, TAKE_KEY);
  assert.doesNotMatch(`takes/${token}/20261001T123456Z-abcdef.exe`, TAKE_KEY);
});

test("numbers from a request are held to their range", () => {
  assert.equal(clampInt("7", 1, 60, 3), 7);
  assert.equal(clampInt(1000, 1, 60, 3), 60);
  assert.equal(clampInt("x", 1, 60, 3), 3);
  assert.equal(clampInt(2.5, 1, 60, 3), 3);
});
