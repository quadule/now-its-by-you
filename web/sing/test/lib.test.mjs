// The worker's pure parts (src/lib.js): ids, the WAV a take must be, its sidecar, joining, words, dates.
// npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_TAKE_BYTES, PERSONAL_JOINS, TAKE_ID, TAKE_KEY, TOKEN, b64url, checkConsent, checkTake, clampInt, cleanEmail, cleanName,
  cleanWords, fileAbout, fileKind, fromB64url, joinsAllowed, leastSung, moment, newToken, parseRange, parseWav, parseWavHeader,
  partName, sameSecret, sectionsOf, songIndex, specOf, stateOf, takeKey,
} from "../src/lib.js";
import { wavBytes } from "../../../tools/karaoke.js";

const LYRICS = {
  guide: "aaaaaaaaaaaa", spec: { id: "a.k0.t100", set: "a", key: 0, tempo: 100 }, duration: 60, lines: [{ syllables: [] }],
  sections: [
    { index: 0, name: "intro", start: 0, end: 5, sung: false },
    { index: 1, name: "verse", start: 5, end: 20, sung: true, nth: 1, label: "They saved it as numbers and sent it by wire,", window: [2.5, 21] },
    { index: 2, name: "turn", start: 20, end: 25, sung: false },
    { index: 3, name: "refrain", start: 25, end: 40, sung: true, nth: 2, label: "Now it's by you", window: [22.5, 41] },
  ],
};
const SONG = songIndex({
  v: 2, title: "H", song: "h-now-its-by-you", consent: "896e20c8603e", words_release: "d1d1d1d1d1d1",
  sets: [{ id: "a", name: "Set A" }, { id: "b", name: "Set B" }],
  guides: {
    "a.k0.t100": { guide: "aaaaaaaaaaaa", lyrics: "a.k0.t100.json", duration: 60,
                   mixes: { melody: { file: "a.k0.t100.melody.mp3", env: [0, 0.1] }, full: { file: "a.k0.t100.full.mp3", env: [] } } },
    "b.k-2.t90": { guide: "bbbbbbbbbbbb", lyrics: "b.k-2.t90.json", duration: 66.7, mixes: { melody: { file: "b.k-2.t90.melody.mp3" } } },
  },
  max_seconds: 127,
});

function info(extra = {}) {
  return { song: SONG.song, spec: "a.k0.t100", guide: "aaaaaaaaaaaa", mix: "melody", rate: 48000, name: "ignored", from_s: 0, to_s: 60,
           shift_ms: 12, sha256: "ab".repeat(32), ...extra };
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

test("an invitation is open until it expires, is revoked, or singing closes", () => {
  const now = Date.parse("2026-09-27T12:00:00Z");
  const open = { state: "open", expires: "2026-10-02T12:00:00Z" };
  assert.equal(stateOf(open, now), "open");
  assert.equal(stateOf({ ...open, expires: "2026-09-27T11:59:59Z" }, now), "expired");
  assert.equal(stateOf({ ...open, state: "done" }, now), "done");
  assert.equal(stateOf({ ...open, state: "revoked" }, now), "revoked");
  assert.equal(stateOf(null, now), "unknown");
  const closes = moment("2026-09-27T22:00:00-07:00");
  assert.equal(closes, Date.parse("2026-09-28T05:00:00Z"));
  assert.equal(stateOf(open, now, closes), "open");
  assert.equal(stateOf(open, closes, closes), "closed");
  assert.equal(stateOf({ ...open, state: "revoked" }, closes + 1, closes), "revoked");
  assert.equal(moment(""), null); // a date not set: never
  assert.equal(moment(undefined), null);
});

test("a personal link admits three joins (laptop, then phone); a group link its people", () => {
  assert.equal(joinsAllowed({ people: 1 }), PERSONAL_JOINS);
  assert.equal(PERSONAL_JOINS, 3);
  assert.equal(joinsAllowed({}), 3); // an invitation from before there were groups
  assert.equal(joinsAllowed({ people: 40 }), 40);
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

test("song.json v2 is read down to what the worker needs", () => {
  assert.deepEqual(SONG.sets, ["a", "b"]);
  assert.deepEqual(SONG.guides["a.k0.t100"], { guide: "aaaaaaaaaaaa", lyrics: "a.k0.t100.json", duration: 60,
                                               mixes: { melody: "a.k0.t100.melody.mp3", full: "a.k0.t100.full.mp3" } });
  assert.deepEqual(songIndex(SONG), SONG); // song/worker.json is the same thing, already small
  assert.throws(() => songIndex({ song: "h", guide: "x", mixes: {} }), /version 2/); // an old site
  const lyric = sectionsOf(LYRICS);
  assert.equal(lyric.sections.length, 4);
  assert.deepEqual(lyric.sections[1].window, [2.5, 21]);
  assert.equal(partName(lyric.sections[1]), "Verse 1");
  assert.equal(partName(lyric.sections[3]), "Refrain 2");
  assert.equal(partName({ name: "tag", nth: null }), "Tag");
});

test("a take names the guide it was sung to, and that guide must be this site's", () => {
  assert.equal(specOf(info(), SONG), "a.k0.t100");
  assert.equal(specOf(info({ spec: undefined }), SONG), "a.k0.t100"); // found by its score's digest
  assert.equal(specOf(info({ spec: "b.k-2.t90", guide: "bbbbbbbbbbbb" }), SONG), "b.k-2.t90");
  assert.throws(() => specOf(info({ guide: "bbbbbbbbbbbb" }), SONG), /reload/); // a.k0.t100 isn't that score
  assert.throws(() => specOf(info({ guide: "000000000000" }), SONG), /reload/);
  assert.throws(() => specOf(info({ spec: "c.k0.t100" }), SONG), /reload/);
  assert.throws(() => specOf(info({ spec: "__proto__" }), SONG), /reload/);
  assert.throws(() => specOf([], SONG), /missing/);
  assert.throws(() => specOf(null, SONG), /missing/);
});

test("a take's sidecar is checked against its guide, down to the part of the song it holds", () => {
  const lyric = sectionsOf(LYRICS), wav = { rate: 48000, samples: 48000 * 60, seconds: 60 };
  const whole = checkTake({ ...info(), extra: "dropped", ua: "Mozilla", consent: { agreed: true } }, SONG, "a.k0.t100", lyric, wav);
  assert.deepEqual(whole, { song: "h-now-its-by-you", spec: "a.k0.t100", guide: "aaaaaaaaaaaa", mix: "melody", rate: 48000,
                            seconds: 60, from_s: 0, to_s: 60, section: null, part: null, label: null, sha256: "ab".repeat(32),
                            shift_ms: 12 });
  // who sang it (name, credit, consent) comes from their record, never from here
  assert.equal(whole.name, undefined);
  assert.equal(whole.consent, undefined);
  assert.deepEqual(checkTake(info({ from_s: undefined, to_s: undefined }), SONG, "a.k0.t100", lyric, wav).to_s, 60);

  // one section: its window, as the lyrics give it
  const verse = { rate: 48000, samples: 48000 * 18, seconds: 18.5 };
  const one = checkTake(info({ section: 1, from_s: 2.5, to_s: 21 }), SONG, "a.k0.t100", lyric, verse);
  assert.equal(one.section, 1);
  assert.equal(one.part, "Verse 1");
  assert.equal(one.label, "They saved it as numbers and sent it by wire,");
  assert.deepEqual([one.from_s, one.to_s], [2.5, 21]);
  assert.equal(checkTake(info({ section: 1, from_s: 2.52, to_s: 20.9 }), SONG, "a.k0.t100", lyric, verse).from_s, 2.52); // rounding
  // to_s is where it stopped: the window's end, or earlier when they pressed Stop
  const stopped = checkTake(info({ section: 1, from_s: 2.5, to_s: 12.25 }), SONG, "a.k0.t100", lyric, { ...verse, seconds: 10.2 });
  assert.deepEqual([stopped.from_s, stopped.to_s], [2.5, 12.25]);
  // a window that isn't the section's, a section that isn't sung or doesn't exist, too long for its window
  assert.throws(() => checkTake(info({ section: 1, from_s: 10, to_s: 21 }), SONG, "a.k0.t100", lyric, verse), /doesn't match/);
  assert.throws(() => checkTake(info({ section: 1, from_s: 2.5, to_s: 41 }), SONG, "a.k0.t100", lyric, verse), /doesn't match/);
  assert.throws(() => checkTake(info({ section: 2, from_s: 20, to_s: 25 }), SONG, "a.k0.t100", lyric, verse), /no such part/);
  assert.throws(() => checkTake(info({ section: 9, from_s: 2.5, to_s: 21 }), SONG, "a.k0.t100", lyric, verse), /no such part/);
  assert.throws(() => checkTake(info({ section: "1", from_s: 2.5, to_s: 21 }), SONG, "a.k0.t100", lyric, verse), /no such part/);
  assert.throws(() => checkTake(info({ section: 1, from_s: 2.5, to_s: 21 }), SONG, "a.k0.t100", lyric,
                                { ...verse, seconds: 18.5 + 10.1 }), /longer than its part/);
  assert.throws(() => checkTake(info({ section: 1, from_s: 2.5, to_s: 2.5 }), SONG, "a.k0.t100", lyric, verse), /out of range/);
  // a whole take from anywhere but the top, or out of the song
  assert.throws(() => checkTake(info({ from_s: 5 }), SONG, "a.k0.t100", lyric, wav), /out of range/);
  assert.throws(() => checkTake(info({ from_s: -1 }), SONG, "a.k0.t100", lyric, wav), /out of range/);
  assert.equal(checkTake(info({ to_s: 30 }), SONG, "a.k0.t100", lyric, { ...wav, seconds: 30.4 }).to_s, 30); // stopped at the bridge
  assert.throws(() => checkTake(info({ to_s: 99 }), SONG, "a.k0.t100", lyric, wav), /out of range/);
  assert.throws(() => checkTake(info({ from_s: "soon" }), SONG, "a.k0.t100", lyric, wav), /out of range/);
  assert.throws(() => checkTake(info(), SONG, "a.k0.t100", lyric, { ...wav, seconds: 121 }), /longer than the song/);

  assert.throws(() => checkTake(info({ sha256: undefined }), SONG, "a.k0.t100", lyric, wav), /checksum/);
  assert.throws(() => checkTake(info({ sha256: "AB".repeat(32) }), SONG, "a.k0.t100", lyric, wav), /checksum/);
  assert.throws(() => checkTake(info({ song: "another" }), SONG, "a.k0.t100", lyric, wav), /reload/);
  assert.throws(() => checkTake(info({ mix: "kazoo" }), SONG, "a.k0.t100", lyric, wav), /no such guide/);
  assert.throws(() => checkTake(info({ mix: "__proto__" }), SONG, "a.k0.t100", lyric, wav), /no such guide/);
  assert.throws(() => checkTake(info({ mix: "full" }), SONG, "b.k-2.t90", sectionsOf({ ...LYRICS, duration: 66.7 }), wav),
                /no such guide/); // that guide has no full mix
  assert.throws(() => checkTake(info({ rate: 44100 }), SONG, "a.k0.t100", lyric, wav), /sample rate/);
  assert.throws(() => checkTake(info(), SONG, "a.k0.t100", lyric, { ...wav, seconds: 2 }), /too short/);
  assert.throws(() => checkTake(info({ shift_ms: 1e9 }), SONG, "a.k0.t100", lyric, wav), /out of range/);
  assert.throws(() => checkTake(info({ shift_ms: "NaN" }), SONG, "a.k0.t100", lyric, wav), /out of range/);
});

test("joining: an email that can be written to, and a release agreed to now", () => {
  assert.equal(cleanEmail("  ana.maria+songs@example.org "), "ana.maria+songs@example.org");
  assert.equal(cleanEmail("zoë@例え.jp"), "zoë@例え.jp");
  for (const bad of ["", "ana", "ana@", "@example.org", "a@b@c", "ana maria@example.org", "ana@exa mple.org",
                     "ana‮@example.org", `${"a".repeat(195)}@b.org`, undefined, null]) {
    assert.throws(() => cleanEmail(bad), /doesn't look right/, String(bad));
  }
  const now = Date.parse("2026-09-27T12:00:00Z");
  assert.deepEqual(checkConsent({ agreed: true, at: "2026-09-27T11:59:00Z", text: "896e20c8603e", extra: 1 }, "896e20c8603e", now),
                   { agreed: true, at: "2026-09-27T11:59:00.000Z", text: "896e20c8603e" });
  assert.throws(() => checkConsent({ agreed: false, at: "2026-09-27T11:59:00Z", text: "896e20c8603e" }, "896e20c8603e", now), /Agree/);
  assert.throws(() => checkConsent(undefined, "896e20c8603e", now), /Agree/);
  assert.throws(() => checkConsent({ agreed: true, at: "2026-09-25T11:00:00Z", text: "896e20c8603e" }, "896e20c8603e", now + 90 * 86400e3), /clock/);
  assert.throws(() => checkConsent({ agreed: true, at: "yesterday-ish", text: "896e20c8603e" }, "896e20c8603e", now), /clock/);
  assert.throws(() => checkConsent({ agreed: true, at: "2026-09-27T11:59:00Z", text: "000000000000" }, "896e20c8603e", now), /changed/);
  assert.throws(() => checkConsent({ agreed: true, at: "2026-09-27T11:59:00Z", text: null }, null, now), /changed/); // a site with no such release
});

test("words for the song: plain text, their line breaks kept, and not too long", () => {
  assert.equal(cleanWords("  A verse\r\nabout the wire‮\n\tand the river \u0007"), "A verse\nabout the wire\n\tand the river");
  assert.equal(cleanWords("名前 ".repeat(1000)).length, 2999); // 4000 characters at most, not bytes
  assert.throws(() => cleanWords("   "), /Write something/);
  assert.throws(() => cleanWords(undefined), /Write something/);
  assert.throws(() => cleanWords("x".repeat(4001)), /longer than 4000/);
});

test("names are printable text, trimmed and short", () => {
  assert.equal(cleanName("  Ana\u0000 María‮ "), "Ana María");
  assert.equal(cleanName("Jo​⁦e⁩"), "Joe"); // invisible and direction marks go too
  assert.equal(cleanName("x".repeat(200)).length, 80);
  assert.equal(cleanName(undefined), "");
  assert.equal(cleanName("<b>Jo</b>"), "<b>Jo</b>"); // kept as text: nothing renders it as HTML
});

test("a new singer is given the set sung least so far", () => {
  const seconds = new Map([["a", 120], ["b", 30], ["c", 30]]);
  assert.equal(leastSung(["a", "b", "c"], seconds), "b"); // the first of those tied
  assert.equal(leastSung(["a", "b"], new Map()), "a");
  assert.equal(leastSung(["a", "b"], new Map([["a", 10]])), "b");
});

test("a take's key is its singer, its time and a little chance, and nothing else", () => {
  const sid = newToken();
  const key = takeKey(sid, new Date("2026-10-01T12:34:56.789Z"));
  assert.match(`${key}.wav`, TAKE_KEY);
  assert.ok(key.startsWith(`takes/${sid}/20261001T123456Z-`));
  assert.match(key.split("/")[2], TAKE_ID);
  assert.doesNotMatch(`takes/${sid}/../../secret.wav`, TAKE_KEY);
  assert.doesNotMatch(`takes/${sid}/20261001T123456Z-abcdef.exe`, TAKE_KEY);
});

test("a byte range is read the way browsers ask for audio", () => {
  assert.deepEqual(parseRange("bytes=0-1", 1000), [0, 1]); // Safari's first ask
  assert.deepEqual(parseRange("bytes=500-", 1000), [500, 999]);
  assert.deepEqual(parseRange("bytes=900-5000", 1000), [900, 999]);
  assert.deepEqual(parseRange("bytes=-100", 1000), [900, 999]);
  assert.deepEqual(parseRange("bytes=-5000", 1000), [0, 999]);
  assert.equal(parseRange(null, 1000), null);
  assert.equal(parseRange("bytes=0-1,5-9", 1000), null); // several: the whole thing instead
  assert.equal(parseRange("bytes=1000-", 1000), "bad");
  assert.equal(parseRange("bytes=5-2", 1000), "bad");
  assert.equal(parseRange("bytes=-0", 1000), "bad");
});

test("a singer's files say what they are", () => {
  assert.equal(fileKind("a.k0.t100.version.mp3"), "version");
  assert.equal(fileKind("a.k0.t100.vocals.wav"), "vocals");
  assert.equal(fileKind("notes.wav"), "other");
  assert.equal(fileAbout("a.k-2.t90.version.mp3"), "Your version of the song");
  assert.equal(fileAbout("b.k0.t100-vocals.wav"), "Your vocals, on their own");
});

test("numbers from a request are held to their range", () => {
  assert.equal(clampInt("7", 1, 60, 3), 7);
  assert.equal(clampInt(1000, 1, 60, 3), 60);
  assert.equal(clampInt("x", 1, 60, 3), 3);
  assert.equal(clampInt(2.5, 1, 60, 3), 3);
});

test("a take sung without headphones says so, and nothing else passes for it", () => {
  const lyric = sectionsOf(LYRICS), wav = { rate: 48000, samples: 48000 * 60, seconds: 60 };
  assert.equal(checkTake(info({ aec: true }), SONG, "a.k0.t100", lyric, wav).aec, true);
  assert.equal(checkTake(info({ aec: false }), SONG, "a.k0.t100", lyric, wav).aec, false);
  assert.ok(!("aec" in checkTake(info({ aec: "yes" }), SONG, "a.k0.t100", lyric, wav)));
  assert.ok(!("aec" in checkTake(info(), SONG, "a.k0.t100", lyric, wav)));
});
