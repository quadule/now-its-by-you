// A version someone shares, checked as data before it is kept: a FLAC that begins as a rendition's does and ends
// in a packet (docs/PACKET.md) whose manifest is a rendition's record. The same rules songbird/received.py holds a
// file to before it reads one, as far as the Worker needs them: the packet is never unpacked, nothing in it is ever
// run, and the only member read is manifest.json (at most 1 MiB, inflated through a bounded stream, parsed as JSON).
// The studio's own reader, on the visitor's device, checks everything again when the version is opened.
//
// Everything here reads through `read(offset, length)` (a range of the stored file) or `tail(length)` (its last
// bytes), so the file is never held whole: a few ranged reads of R2, a few KB each, and the manifest's.

export const MAX_BYTES = 64 * 2 ** 20; // the most a version may be (received.UPLOAD): a rendition is about 15 to 25 MB
export const MIN_BYTES = 4096; // less is no rendition
export const ENTRIES = 512; // the most entries an archive may list: a packet has about 95
export const DIRECTORY = 2 ** 20; // the most its central directory may take
export const ARCHIVE = 100 * 2 ** 20; // the most its entries may declare, in all (as the bootstrap caps an unpacking)
export const RATIO = 1000; // the most any entry may declare it grows
export const RECORD = 2 ** 20; // manifest.json's cap (a record is about 100 KB)
export const LOCAL_EXTRA = 1024; // the most a local header's extra field may be (a packet's has none)
const ID = /^[0-9a-f]{64}$/;
const NAME = /^[A-Za-z0-9_][A-Za-z0-9._ +-]{0,199}(\/[A-Za-z0-9_][A-Za-z0-9._ +-]{0,199}){0,15}\/?$/;

export class Refused extends Error {} // why a file isn't kept, in a sentence for the person who shared it

const u16 = (b, at) => b[at] | (b[at + 1] << 8);
const u32 = (b, at) => (b[at] | (b[at + 1] << 8) | (b[at + 2] << 16) | (b[at + 3] << 24)) >>> 0;
const same = (b, at, sig) => sig.every((x, i) => b[at + i] === x);
const EOCD = [0x50, 0x4b, 0x05, 0x06], CENTRAL = [0x50, 0x4b, 0x01, 0x02], LOCAL = [0x50, 0x4b, 0x03, 0x04];
const LOCATOR = [0x50, 0x4b, 0x06, 0x07];

export function checkHead(head) {
  // "fLaC", then the STREAMINFO block a rendition's audio begins with: 44.1 kHz, stereo
  if (head.length < 42 || !same(head, 0, [0x66, 0x4c, 0x61, 0x43])) {
    throw new Refused("It isn't a FLAC file. Share the .flac file a Songbird rendition came as.");
  }
  const type = head[4] & 0x7f, length = (head[5] << 16) | (head[6] << 8) | head[7];
  if (type !== 0 || length !== 34) throw new Refused("It's a FLAC, but not one a rendition makes.");
  const rate = (head[18] << 12) | (head[19] << 4) | (head[20] >> 4), channels = ((head[20] >> 1) & 0x7) + 1;
  if (rate !== 44100 || channels !== 2) throw new Refused("It's a FLAC, but not one a rendition makes (44.1 kHz, stereo).");
}

export function directoryEnd(tail, size) {
  // the end record zipfile would take (the last in the file's last 64 KB), which must end the file; where the
  // directory starts, how long it is, how many entries it lists (offsets are the file's own: pack.py)
  const none = "It's a FLAC, but it carries no packet: only a Songbird rendition can be shared here.";
  let at = -1;
  for (let i = tail.length - 22; i >= 0; i--) if (same(tail, i, EOCD)) { at = i; break; }
  if (at < 0) throw new Refused(none);
  const disk = u16(tail, at + 4), cdDisk = u16(tail, at + 6), here = u16(tail, at + 8), total = u16(tail, at + 10);
  const cdSize = u32(tail, at + 12), cdStart = u32(tail, at + 16), comment = u16(tail, at + 20);
  if (at + 22 + comment !== tail.length) throw new Refused("Its packet doesn't end where a rendition's does.");
  if (disk || cdDisk || here !== total) throw new Refused("Its packet spans several disks, which no rendition does.");
  const zip64 = at >= 20 && same(tail, at - 20, LOCATOR);
  if (total === 0 || total === 0xffff || cdSize === 0xffffffff || cdStart === 0xffffffff || zip64) {
    throw new Refused("Its packet isn't one a rendition carries (ZIP64, or empty).");
  }
  if (total > ENTRIES || cdSize > DIRECTORY) throw new Refused(`Its packet lists ${total} files; a rendition's lists about 95.`);
  const end = size - tail.length + at;
  if (cdStart + cdSize !== end || cdStart < 42) throw new Refused("Its packet's directory isn't where a rendition's is.");
  return { cdStart, cdSize, total };
}

function badName(name) {
  return !NAME.test(name) || name.includes("\\") || name.includes("\0")
    || name.replace(/\/$/, "").split("/").some(p => p === "" || p === "." || p === "..");
}

export function readDirectory(cd, cdStart, total) {
  // the central directory's entries, each held to what a packet's are
  const decode = new TextDecoder("utf-8", { fatal: true });
  const entries = new Map();
  let at = 0, declared = 0;
  for (let n = 0; n < total; n++) {
    if (at + 46 > cd.length || !same(cd, at, CENTRAL)) throw new Refused("Its packet's directory doesn't agree with itself.");
    const flags = u16(cd, at + 8), method = u16(cd, at + 10), packed = u32(cd, at + 20), size = u32(cd, at + 24);
    const nameLen = u16(cd, at + 28), extraLen = u16(cd, at + 30), commentLen = u16(cd, at + 32), offset = u32(cd, at + 42);
    if (at + 46 + nameLen > cd.length) throw new Refused("Its packet's directory doesn't agree with itself.");
    let name;
    try {
      name = decode.decode(cd.subarray(at + 46, at + 46 + nameLen));
    } catch (e) {
      throw new Refused("Its packet holds a file whose name isn't text, which no rendition does.");
    }
    if (badName(name)) throw new Refused(`Its packet holds a file named ${JSON.stringify(name.slice(0, 60))}, which no rendition does.`);
    if (entries.has(name)) throw new Refused("Its packet lists the same file twice, which no rendition does.");
    if (flags & 0x1) throw new Refused("Its packet is encrypted, which no rendition is.");
    if (flags & 0x8) throw new Refused("Its packet was written in a way no rendition's is (data descriptors).");
    if (method !== 0 && method !== 8) throw new Refused("Its packet is compressed in a way no rendition is.");
    if (size > RATIO * Math.max(packed, 1) && size > 2 ** 20) {
      throw new Refused(`A file in its packet claims to grow ${Math.floor(size / Math.max(packed, 1))} times over: that's a trap, not a rendition.`);
    }
    if (!(offset >= 42 && offset < cdStart && offset + packed <= cdStart)) {
      throw new Refused("Its packet's files aren't where a rendition keeps them.");
    }
    if (size > ARCHIVE) throw new Refused("A file in its packet is larger than a whole rendition's program.");
    declared += size;
    entries.set(name, { name, method, packed, size, offset, crc: u32(cd, at + 16) });
    at += 46 + nameLen + extraLen + commentLen;
  }
  if (at !== cd.length) throw new Refused("Its packet's directory doesn't agree with itself.");
  if (declared > ARCHIVE) throw new Refused(`Its packet would unpack to ${Math.round(declared / 2 ** 20)} MB; a rendition's is about 6.`);
  if (!entries.has("manifest.json")) throw new Refused("It's a FLAC, but it carries no packet: only a Songbird rendition can be shared here.");
  if (!entries.has("genome.json")) throw new Refused("Its packet carries no song (genome.json).");
  return entries;
}

let CRC = null;
export function crc32(bytes) {
  if (!CRC) {
    CRC = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

async function inflated(data, cap) {
  // raw deflate, read no further than `cap` bytes out (whatever the entry's header claims)
  const reader = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw")).getReader();
  const parts = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > cap) throw new Refused("Its packet's manifest.json is larger than it says.");
      parts.push(value);
    }
  } catch (e) {
    if (e instanceof Refused) throw e;
    throw new Refused("Its packet's manifest.json is damaged.");
  } finally {
    reader.cancel().catch(() => {});
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const p of parts) { out.set(p, at); at += p.byteLength; }
  return out;
}

export async function readMember(entry, read, cdStart) {
  // one member's bytes: its local header must be where the directory says, name it, and hold its data
  if (entry.size > RECORD) throw new Refused(`Its packet's ${entry.name} is ${Math.round(entry.size / 1024)} KB; a rendition's is far smaller.`);
  // deflate never makes data much larger: a bigger entry is padding, and would be read into memory for nothing
  if (entry.packed > RECORD + 4096) throw new Refused(`Its packet's ${entry.name} is larger than it says.`);
  const nameLen = new TextEncoder().encode(entry.name).length;
  const want = Math.min(30 + nameLen + LOCAL_EXTRA + entry.packed, cdStart - entry.offset);
  const local = await read(entry.offset, want);
  if (local.length < 30 || !same(local, 0, LOCAL)) throw new Refused("Its packet's files aren't where its directory says.");
  const n = u16(local, 26), extra = u16(local, 28), start = 30 + n + extra;
  if (n !== nameLen || new TextDecoder().decode(local.subarray(30, 30 + n)) !== entry.name) {
    throw new Refused("Its packet's files aren't where its directory says.");
  }
  if (extra > LOCAL_EXTRA || start + entry.packed > local.length) throw new Refused("Its packet was written in a way no rendition's is.");
  const raw = local.subarray(start, start + entry.packed);
  const data = entry.method === 0 ? raw : await inflated(raw, RECORD);
  if (data.length !== entry.size || crc32(data) !== entry.crc) throw new Refused(`Its packet's ${entry.name} is damaged.`);
  return data;
}

export function checkManifest(bytes) {
  // a rendition's record, as far as sharing needs: what it is (its id, its program) and its place in the line
  let m;
  try {
    m = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch (e) {
    throw new Refused("Its packet's record isn't JSON.");
  }
  if (!m || typeof m !== "object" || Array.isArray(m)) throw new Refused("Its record isn't a record.");
  if (typeof m.id !== "string" || !ID.test(m.id)) throw new Refused("Its record has no id, so its place in the line can't be known.");
  if (typeof m.program_sha256 !== "string" || !ID.test(m.program_sha256)) {
    throw new Refused("Its record doesn't say which program made it, as every rendition's does.");
  }
  if (typeof m.title !== "string" || !m.title.trim() || m.title.length > 4096) throw new Refused("Its record has no title.");
  const generation = m.generation ?? 0;
  if (!Number.isInteger(generation) || generation < 0 || generation > 100000) throw new Refused("Its record's generation isn't a count.");
  if (m.parent_id != null && (typeof m.parent_id !== "string" || !ID.test(m.parent_id))) throw new Refused("Its record's parent isn't an id.");
  const ancestry = m.ancestry ?? [];
  if (!Array.isArray(ancestry) || ancestry.length > 4096 || !ancestry.every(a => typeof a === "string" && ID.test(a))) {
    throw new Refused("Its record's ancestry isn't a list of ids.");
  }
  return { id: m.id, title: m.title, generation, parent_id: m.parent_id ?? null };
}

export async function checkVersion(size, read, tail) {
  // the whole check, from a few ranged reads; the record's summary, or Refused
  if (size < MIN_BYTES) throw new Refused("That's too small to be a Songbird version.");
  checkHead(await read(0, 42));
  const span = Math.min(size, 22 + 65535);
  const end = await tail(span);
  const { cdStart, cdSize, total } = directoryEnd(end, size);
  const inTail = cdStart >= size - span;
  const cd = inTail ? end.subarray(cdStart - (size - span), cdStart - (size - span) + cdSize) : await read(cdStart, cdSize);
  const entries = readDirectory(cd, cdStart, total);
  return checkManifest(await readMember(entries.get("manifest.json"), read, cdStart));
}
