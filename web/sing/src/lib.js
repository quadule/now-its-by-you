// The worker's pure parts: tokens, the WAV a take must be, a take's sidecar and an invite's
// state (web/sing/src/worker.js uses them; test/lib.test.mjs tests them).

export const TOKEN = /^[A-Za-z0-9_-]{24}$/; // 18 random bytes, base64url: 144 bits
export const TAKE_KEY = /^takes\/[A-Za-z0-9_-]{24}\/\d{8}T\d{6}Z-[a-z2-7]{6}\.(wav|json)$/;
export const MAX_TAKE_BYTES = 40 * 1024 * 1024; // 96 kHz for 3.5 minutes
export const MIN_TAKE_SECONDS = 3;
export const RATES = [8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000, 88200, 96000];
export const DEFAULTS = { days: 7, limit: 30 };

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

export function stateOf(invite, now = Date.now()) {
  if (!invite) return "unknown";
  if (invite.state !== "open") return invite.state; // done or revoked
  return Date.parse(invite.expires) <= now ? "expired" : "open";
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

const NUMBERS = ["shift_ms", "auto_ms", "device_ms", "decode_ms", "out_ms", "in_ms"];

export function cleanName(name) {
  // printable text only, trimmed, at most 80 characters
  return String(name ?? "").replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2066-\u2069]/g, "").trim().slice(0, 80);
}

export function checkInfo(info, song, wav, now = Date.now()) {
  // the sidecar a take arrives with, checked field by field against the song it was sung to;
  // anything unknown is dropped. Throws with a reason the page can show.
  if (!info || typeof info !== "object" || Array.isArray(info)) throw new Error("the take's details are missing");
  const consent = info.consent;
  if (!consent || consent.agreed !== true) throw new Error("the release must be agreed to first");
  const at = Date.parse(consent.at);
  if (!Number.isFinite(at) || at > now + 86400e3 || at < now - 60 * 86400e3) {
    throw new Error("the time the release was agreed to is out by more than a day: check this device's clock and date");
  }
  if (consent.text !== song.consent) throw new Error("the release has changed since the page was loaded: reload it");
  if (info.song !== song.song || info.guide !== song.guide) throw new Error("the song has changed since the page was loaded: reload it");
  if (!Object.prototype.hasOwnProperty.call(song.mixes, info.mix)) throw new Error("no such guide");
  if (info.rate !== wav.rate) throw new Error("the sample rate doesn't match the recording");
  if (wav.seconds < MIN_TAKE_SECONDS) throw new Error("the take is too short");
  if (wav.seconds > song.max_seconds) throw new Error("the take is longer than the song");
  if (!/^[0-9a-f]{64}$/.test(String(info.sha256))) throw new Error("the take's checksum is missing");
  const out = {
    song: song.song, guide: song.guide, mix: info.mix, rate: wav.rate, seconds: Math.round(wav.seconds * 1000) / 1000,
    name: cleanName(info.name), credit: info.credit === true, sha256: info.sha256,
    consent: { agreed: true, at: new Date(at).toISOString(), text: consent.text },
  };
  for (const k of NUMBERS) {
    if (info[k] === undefined || info[k] === null) continue;
    const x = Number(info[k]);
    if (!Number.isFinite(x) || Math.abs(x) > 10000) throw new Error(`${k} is out of range`);
    out[k] = Math.round(x * 10) / 10;
  }
  return out;
}

export function takeKey(token, when = new Date()) {
  const stamp = when.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
  const alphabet = "abcdefghijklmnopqrstuvwxyz234567";
  const rand = Array.from(crypto.getRandomValues(new Uint8Array(6)), b => alphabet[b & 31]).join("");
  return `takes/${token}/${stamp}-${rand}`;
}

export function clampInt(value, lo, hi, fallback) {
  const x = Number(value);
  return Number.isInteger(x) ? Math.min(hi, Math.max(lo, x)) : fallback;
}
