// The worker's pure parts: ids, the WAV a take must be, a take's sidecar checked against the song,
// what a singer sends when joining or sending words, invitations' states and the dates singing keeps
// (web/sing/src/worker.js uses them; test/lib.test.mjs tests them).

export const TOKEN = /^[A-Za-z0-9_-]{24}$/; // 18 random bytes, base64url: 144 bits (invitations and singers)
// a word the artist chooses for an invitation instead, short enough to say and type (songbird.quadule.com/i/family):
// 4 to 24 lowercase letters, digits and hyphens, a letter first; guessable, so for links to family and friends
export const WORD = /^[a-z][a-z0-9-]{2,22}[a-z0-9]$/;
export const isInvite = token => TOKEN.test(token) || WORD.test(token);
export const TAKE_ID = /^\d{8}T\d{6}Z-[a-z2-7]{6}$/;
export const TAKE_KEY = /^takes\/[A-Za-z0-9_-]{24}\/\d{8}T\d{6}Z-[a-z2-7]{6}\.(wav|json)$/;
export const WORDS_KEY = /^words\/[A-Za-z0-9_-]{24}\/\d{8}T\d{6}Z-[a-z2-7]{6}\.json$/;
export const FILE_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.(mp3|wav)$/;
export const SPEC = /^[a-z0-9]{1,8}\.k-?\d{1,2}\.t\d{2,3}$/;
export const MAX_TAKE_BYTES = 40 * 1024 * 1024; // 96 kHz for 3.5 minutes
export const MAX_FILE_BYTES = 95 * 1024 * 1024; // a singer's version or vocals (a Worker takes 100 MB at most)
export const MIN_TAKE_SECONDS = 3;
export const SECTION_SLACK = 10; // seconds a one-section take may run past its window
export const WINDOW_SLACK = 0.25; // seconds a take's from_s and to_s may differ from the window the page was given
export const RATES = [8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000];
export const DEFAULTS = { days: 7, limit: 30, people: 1 };
export const PERSONAL_JOINS = 3; // a personal link: people move from laptop to phone before their email comes
export const MAX_WORDS = 20;
export const MAX_WORDS_CHARS = 4000;

export function newToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(18));
  return b64url(bytes);
}

export function b64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromB64url(text) {
  const s = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4));
  return Uint8Array.from(s, c => c.charCodeAt(0));
}

export function sameSecret(a, b) {
  // constant-time comparison of two strings (of the same length; a length mismatch is simply false)
  const x = new TextEncoder().encode(String(a)), y = new TextEncoder().encode(String(b));
  if (x.length !== y.length || x.length === 0) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

export function own(object, key) {
  return !!object && typeof object === "object" && Object.prototype.hasOwnProperty.call(object, key);
}

export function moment(value) {
  // one of the worker's dates (CLOSES_AT, DELETE_BY) in ms, or null if it isn't set
  const t = Date.parse(String(value ?? ""));
  return Number.isFinite(t) ? t : null;
}

export function stateOf(invite, now = Date.now(), closes = null) {
  // closes (CLOSES_AT) is when singing for the first release ends: withdrawal closes with it, but an
  // invitation stays open, so people can go on singing for later versions
  if (!invite) return "unknown";
  if (invite.state !== "open") return invite.state; // done (an old invitation) or revoked
  void closes;
  return Date.parse(invite.expires) <= now ? "expired" : "open";
}

export function joinsAllowed(invite) {
  const people = Number(invite && invite.people) || 1;
  return people > 1 ? people : PERSONAL_JOINS;
}

export function parseWavHeader(head, total) {
  // a take must be exactly what the page writes: RIFF/WAVE, a 16-byte fmt chunk of 16-bit mono PCM,
  // then one data chunk running to the end of the file, `total` bytes in all; its first 44 bytes are
  // enough to tell, so the rest can stream on to the bucket
  if (head.byteLength < 44 || total < 44) throw new Error("too short to be a WAV");
  const v = new DataView(head.buffer, head.byteOffset, 44);
  const tag = at => String.fromCharCode(v.getUint8(at), v.getUint8(at + 1), v.getUint8(at + 2), v.getUint8(at + 3));
  if (tag(0) !== "RIFF" || tag(8) !== "WAVE" || tag(12) !== "fmt " || tag(36) !== "data") throw new Error("not a plain WAV");
  if (v.getUint32(4, true) !== total - 8) throw new Error("the RIFF size is wrong");
  if (v.getUint32(16, true) !== 16) throw new Error("the fmt chunk is not plain PCM");
  const format = v.getUint16(20, true), channels = v.getUint16(22, true), rate = v.getUint32(24, true);
  const byteRate = v.getUint32(28, true), align = v.getUint16(32, true), bits = v.getUint16(34, true);
  if (format !== 1 || channels !== 1 || bits !== 16 || align !== 2 || byteRate !== rate * 2) throw new Error("not 16-bit mono PCM");
  if (!RATES.includes(rate)) throw new Error("an unusual sample rate");
  const size = v.getUint32(40, true);
  if (size !== total - 44 || size % 2) throw new Error("the data size is wrong");
  return { rate, samples: size / 2, seconds: size / 2 / rate };
}

export function parseWav(buffer) {
  // the same, for a whole take in hand
  return parseWavHeader(new Uint8Array(buffer, 0, Math.min(44, buffer.byteLength)), buffer.byteLength);
}

const INVISIBLE = /[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿]/g;

export function cleanName(name) {
  // printable text only, trimmed, at most 80 characters
  return String(name ?? "").replace(INVISIBLE, "").trim().slice(0, 80);
}

export function cleanEmail(email) {
  // one @, nothing blank or invisible, at most 200 characters: enough to write to, and no more checking
  const e = String(email ?? "").trim();
  if (!e || e.length > 200 || !/^[^\s@]+@[^\s@]+$/u.test(e) || /[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿]/.test(e)) {
    throw new Error("That email address doesn't look right: check it and try again.");
  }
  return e;
}

export function cleanWords(text) {
  // what someone writes for the song: their line breaks kept, invisible and control characters dropped
  const t = String(text ?? "").replace(/\r\n?/g, "\n").replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩﻿]/g, "").trim();
  if (!t) throw new Error("Write something first.");
  if (Array.from(t).length > MAX_WORDS_CHARS) throw new Error(`That's longer than ${MAX_WORDS_CHARS} characters: send it in parts.`);
  return t;
}

export function checkConsent(consent, digest, now = Date.now(), what = "release") {
  // an agreement the page made (to the release for recordings, or the one for words): ticked, at a
  // sane time, to the text this site shows now
  if (!consent || typeof consent !== "object" || consent.agreed !== true) throw new Error(`Agree to the ${what} first.`);
  const at = Date.parse(consent.at);
  if (!Number.isFinite(at) || at > now + 86400e3 || at < now - 60 * 86400e3) {
    throw new Error(`The time the ${what} was agreed to is out by more than a day: check this device's clock and date.`);
  }
  if (!digest || consent.text !== digest) throw new Error(`The ${what} has changed since the page was loaded: reload it.`);
  return { agreed: true, at: new Date(at).toISOString(), text: digest };
}

export function songIndex(song) {
  // what the worker needs of song.json v2 (tools/sing_site.py writes the same as song/worker.json, so a
  // cold start needn't read every guide's loudness curve)
  if (!song || typeof song !== "object" || !song.guides || typeof song.guides !== "object") {
    throw new Error("the site's song.json isn't version 2: build it again with tools/sing_site.py");
  }
  const guides = {};
  for (const [spec, g] of Object.entries(song.guides)) {
    const mixes = {};
    for (const [mix, m] of Object.entries(g.mixes || {})) mixes[mix] = typeof m === "string" ? m : m.file;
    const was = Array.isArray(g.was) ? g.was.filter(d => typeof d === "string") : []; // its earlier guides, timed the same
    guides[spec] = { guide: g.guide, lyrics: g.lyrics, duration: Number(g.duration), mixes, was };
  }
  const sets = (song.sets || []).map(s => (typeof s === "string" ? s : s.id)).filter(Boolean);
  // the song as it stands, for singers to hear before they sing (sing_site.py --preview), when the site has one
  const preview = song.preview && typeof song.preview.file === "string" ? { file: song.preview.file } : null;
  return { song: song.song, consent: song.consent, words_release: song.words_release ?? null, sets,
           guides, max_seconds: song.max_seconds ?? null, preview };
}

export function sectionsOf(lyrics) {
  // a spec's lyrics JSON, cut down to what a take is checked against
  const sections = (lyrics.sections || []).map(x => ({
    index: x.index, name: String(x.name ?? ""), nth: x.nth ?? null, sung: x.sung === true,
    label: x.label ?? null, window: Array.isArray(x.window) ? x.window.map(Number) : null,
  }));
  return { duration: Number(lyrics.duration), guide: lyrics.guide, sections };
}

export function partName(section) {
  // "Verse 2", "Refrain 1", "Tag": what a one-section take is called on the singer's page
  const name = section.name ? section.name[0].toUpperCase() + section.name.slice(1) : "Part";
  return section.nth ? `${name} ${section.nth}` : name;
}

export function heard(g, digest) {
  // was a take sung to this guide? Its score now, or an earlier one that places a take exactly where it
  // does (the words or the voice changed since the page was loaded, not the timing: tools/sing_site.py)
  return typeof digest === "string" && (g.guide === digest || (Array.isArray(g.was) && g.was.includes(digest)));
}

export function specOf(info, song) {
  // which of the song's guides a take was sung to: the spec it names, whose score must be the one heard
  if (!info || typeof info !== "object" || Array.isArray(info)) throw new Error("the take's details are missing");
  let spec = info.spec;
  if (spec === undefined || spec === null) spec = Object.keys(song.guides).find(k => heard(song.guides[k], info.guide));
  if (typeof spec !== "string" || !own(song.guides, spec) || !heard(song.guides[spec], info.guide)) {
    throw new Error("the song has changed since the page was loaded: reload it");
  }
  return spec;
}

const NUMBERS = ["shift_ms", "auto_ms", "device_ms", "decode_ms", "out_ms", "in_ms", "leak_ms", "leak_db"];
const round3 = x => Math.round(x * 1000) / 1000;

export function checkTake(info, song, spec, lyric, wav) {
  // the sidecar a take arrives with, checked field by field against the guide it was sung to (its spec's
  // lyrics say where each sung section's window is); anything unknown is dropped, and who sang it comes
  // from their own record, not from here. Throws with a reason the page can show.
  const g = song.guides[spec];
  if (info.song !== undefined && info.song !== song.song) throw new Error("the song has changed since the page was loaded: reload it");
  if (!own(g.mixes, info.mix)) throw new Error("no such guide");
  if (info.rate !== wav.rate) throw new Error("the sample rate doesn't match the recording");
  if (wav.seconds < MIN_TAKE_SECONDS) throw new Error("the take is too short");
  if (!/^[0-9a-f]{64}$/.test(String(info.sha256))) throw new Error("the take's checksum is missing");
  const duration = Number.isFinite(lyric.duration) ? lyric.duration : g.duration;
  const from = Number(info.from_s ?? 0), to = Number(info.to_s ?? duration);
  if (!Number.isFinite(from) || !Number.isFinite(to) || from < 0 || to <= from || to > duration + 1) {
    throw new Error("the take's place in the song is out of range");
  }
  // to_s is where the take stopped: its window's end (or the song's), or earlier, when Stop was pressed
  let section = info.section ?? null, part = null, label = null;
  if (section === null) {
    // the whole song: from the top
    if (from > WINDOW_SLACK) throw new Error("the take's place in the song is out of range");
    if (wav.seconds > duration + 60) throw new Error("the take is longer than the song");
  } else {
    const s = Number.isInteger(section) ? lyric.sections.find(x => x.index === section && x.sung && x.window) : null;
    if (!s) throw new Error("no such part of the song");
    if (Math.abs(from - s.window[0]) > WINDOW_SLACK || to > s.window[1] + WINDOW_SLACK) {
      throw new Error("the take's place in the song doesn't match its part: reload the page");
    }
    if (wav.seconds > s.window[1] - s.window[0] + SECTION_SLACK) throw new Error("the take is longer than its part of the song");
    part = partName(s);
    label = s.label ? String(s.label).slice(0, 200) : null;
  }
  const out = {
    song: song.song, spec, guide: heard(g, info.guide) ? info.guide : g.guide, // the score it's measured against
    mix: info.mix, rate: wav.rate, seconds: round3(wav.seconds),
    from_s: round3(from), to_s: round3(to), section, part, label, sha256: info.sha256,
  };
  for (const k of NUMBERS) {
    if (info[k] === undefined || info[k] === null) continue;
    const x = Number(info[k]);
    if (!Number.isFinite(x) || Math.abs(x) > 10000) throw new Error(`${k} is out of range`);
    out[k] = Math.round(x * 10) / 10;
  }
  if (typeof info.aec === "boolean") out.aec = info.aec; // sung without headphones, the guide taken out of the microphone
  return out;
}

export function leastSung(sets, seconds) {
  // the set with the fewest seconds sung to it so far (the first of them, if several tie)
  let best = sets[0];
  for (const s of sets) if ((seconds.get(s) || 0) < (seconds.get(best) || 0)) best = s;
  return best;
}

export function stamp(when = new Date()) {
  return when.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
}

export function stampedKey(prefix, id, when = new Date()) {
  // <prefix>/<id>/<time>-<a little chance>: sorts by time, and two at once don't collide
  const alphabet = "abcdefghijklmnopqrstuvwxyz234567";
  const rand = Array.from(crypto.getRandomValues(new Uint8Array(6)), b => alphabet[b & 31]).join("");
  return `${prefix}/${id}/${stamp(when)}-${rand}`;
}

export function takeKey(sid, when = new Date()) {
  return stampedKey("takes", sid, when);
}

export function fileKind(name) {
  return /(^|[._-])version([._-]|$)/.test(name) ? "version" : /(^|[._-])vocals([._-]|$)/.test(name) ? "vocals" : "other";
}

export function fileAbout(name) {
  const kind = fileKind(name);
  return kind === "version" ? "Your version of the song" : kind === "vocals" ? "Your vocals, on their own" : name;
}

export function parseRange(header, size) {
  // a single "bytes=a-b", "bytes=a-" or "bytes=-n" range of an object of `size` bytes, as [first, last];
  // null if there's none (or it's not one we serve: the whole object then), "bad" if it can't be met
  const m = /^bytes=(\d*)-(\d*)$/.exec(String(header ?? "").trim());
  if (!m || (m[1] === "" && m[2] === "")) return null;
  let first, last;
  if (m[1] === "") {
    const n = Number(m[2]);
    if (n === 0) return "bad";
    first = Math.max(0, size - n);
    last = size - 1;
  } else {
    first = Number(m[1]);
    last = m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
  }
  if (!Number.isSafeInteger(first) || first >= size || last < first) return "bad";
  return [first, last];
}

export function clampInt(value, lo, hi, fallback) {
  const x = Number(value);
  return Number.isInteger(x) ? Math.min(hi, Math.max(lo, x)) : fallback;
}
