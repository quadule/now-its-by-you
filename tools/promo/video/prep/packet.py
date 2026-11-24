"""packet.json, packet-bytes.bin/.json and packet-text.json: the release file's byte layout read from its bytes
(FLAC metadata blocks, the audio frames, the zip appended after them: songbird/pack.py, docs/PACKET.md), a sample
of its real bytes, and the opening of a few files it carries.

    uv run python tools/promo/video/prep/packet.py"""
from __future__ import annotations

import io
import json
import struct
import zipfile

import numpy as np

import common

BLOCKS = {0: "STREAMINFO", 1: "PADDING", 2: "APPLICATION", 3: "SEEKTABLE", 4: "VORBIS_COMMENT", 5: "CUESHEET",
          6: "PICTURE"}
SAMPLE = 4096
TEXTS = ("program/songbird/pack.py", "program/songbird/synth/throat.py", "program/songbird/synth/pluck.py",
         "genome.json", "lyrics.txt")
CHARS = 2000


def flac_blocks(b: bytes) -> tuple[list[dict], int]:
    assert b[:4] == b"fLaC", "not a FLAC"
    pos, blocks = 4, []
    while True:
        head = b[pos]
        last, kind = head >> 7, head & 0x7F
        length = int.from_bytes(b[pos + 1: pos + 4], "big")
        blocks.append({"type": BLOCKS.get(kind, str(kind)), "code": kind, "offset": pos, "header": 4,
                       "length": length, "last": bool(last)})
        pos += 4 + length
        if last:
            return blocks, pos


def streaminfo(body: bytes) -> dict:
    x = int.from_bytes(body[10:18], "big")
    return {"min_block": struct.unpack(">H", body[0:2])[0], "max_block": struct.unpack(">H", body[2:4])[0],
            "sample_rate": x >> 44, "channels": ((x >> 41) & 7) + 1, "bits": ((x >> 36) & 31) + 1,
            "samples": x & ((1 << 36) - 1), "md5": body[18:34].hex()}


def vorbis(body: bytes) -> dict:
    n = struct.unpack("<I", body[:4])[0]
    vendor = body[4: 4 + n].decode("utf-8")
    pos = 4 + n
    count = struct.unpack("<I", body[pos: pos + 4])[0]
    pos += 4
    comments = []
    for _ in range(count):
        m = struct.unpack("<I", body[pos: pos + 4])[0]
        comments.append(body[pos + 4: pos + 4 + m].decode("utf-8"))
        pos += 4 + m
    return {"vendor": vendor, "comments": comments}


def picture(body: bytes) -> dict:
    kind, n = struct.unpack(">II", body[:8])
    mime = body[8: 8 + n].decode()
    pos = 8 + n
    m = struct.unpack(">I", body[pos: pos + 4])[0]
    desc = body[pos + 4: pos + 4 + m].decode("utf-8")
    pos += 4 + m
    w, h, depth, colours, size = struct.unpack(">IIIII", body[pos: pos + 20])
    return {"picture_type": kind, "mime": mime, "description": desc, "width": w, "height": h, "data_length": size}


def main() -> None:
    import soundfile as sf

    path = common.guard(common.RELEASE)
    b = common.read_bytes(path)
    blocks, audio0 = flac_blocks(b)
    for blk in blocks:
        body = b[blk["offset"] + 4: blk["offset"] + 4 + blk["length"]]
        if blk["code"] == 0:
            blk["streaminfo"] = streaminfo(body)
        elif blk["code"] == 4:
            blk["vorbis"] = vorbis(body)
        elif blk["code"] == 6:
            blk["picture"] = picture(body)

    z = zipfile.ZipFile(io.BytesIO(b))
    infos = z.infolist()
    zip0 = min(i.header_offset for i in infos)  # absolute: the archive is written onto the end of the audio
    eocd = b.rfind(b"PK\x05\x06")
    cd_size, cd_offset = struct.unpack("<II", b[eocd + 12: eocd + 20])
    assert b[zip0: zip0 + 4] == b"PK\x03\x04" and cd_offset + cd_size == eocd
    info = next(blk["streaminfo"] for blk in blocks if blk["code"] == 0)
    decoded = sf.info(io.BytesIO(b[:zip0]))
    assert decoded.frames == info["samples"], (decoded.frames, info["samples"])

    entries = []
    for i in infos:
        extra = struct.unpack("<H", b[i.header_offset + 28: i.header_offset + 30])[0]
        name_len = struct.unpack("<H", b[i.header_offset + 26: i.header_offset + 28])[0]
        entries.append({"name": i.filename, "offset": i.header_offset,
                        "data_offset": i.header_offset + 30 + name_len + extra,
                        "compressed": i.compress_size, "size": i.file_size,
                        "method": {0: "stored", 8: "deflate"}.get(i.compress_type, i.compress_type),
                        "crc": f"{i.CRC:08x}"})
    names = [e["name"] for e in entries]
    manifest = json.loads(z.read("manifest.json"))
    ext = {}
    for e in entries:
        k = e["name"].rsplit(".", 1)[-1] if "." in e["name"].rsplit("/", 1)[-1] else ""
        d = ext.setdefault(k, {"files": 0, "size": 0, "compressed": 0})
        d["files"] += 1
        d["size"] += e["size"]
        d["compressed"] += e["compressed"]

    out = {
        "file": str(path.relative_to(common.ROOT)), "bytes": len(b),
        "flac": {"magic": {"offset": 0, "length": 4, "text": "fLaC"}, "blocks": blocks,
                 "audio": {"offset": audio0, "end": zip0, "length": zip0 - audio0,
                           "seconds": info["samples"] / info["sample_rate"],
                           "check": "soundfile decodes bytes [0, zip.offset) to STREAMINFO's sample count"}},
        "zip": {"offset": zip0, "end": len(b), "length": len(b) - zip0, "entries_count": len(entries),
                "central_directory": {"offset": cd_offset, "length": cd_size},  # absolute, as pack.py writes it
                "end_record": {"offset": eocd, "length": len(b) - eocd},
                "share_of_file": (len(b) - zip0) / len(b),
                "uncompressed": sum(e["size"] for e in entries), "compressed": sum(e["compressed"] for e in entries),
                "by_extension": ext, "entries": entries},
        "vorbis": next((blk["vorbis"] for blk in blocks if blk["code"] == 4), None),
        "manifest": {k: manifest.get(k) for k in ("id", "generation", "parent_id", "ancestry", "program_sha256",
                                                    "record_format", "title", "name", "rendered_at", "duration")},
        "throat": next(({"name": e["name"], "size": e["size"], "offset": e["offset"]} for e in entries
                        if e["name"].endswith("synth/throat.npz")), None),
    }
    common.write_json("packet.json", out, indent=1)

    # real bytes: the first of the audio frames, and the stretch across the audio's end and the zip's start
    a = np.frombuffer(b[audio0: audio0 + SAMPLE], np.uint8)
    edge0 = zip0 - SAMPLE // 2
    e = np.frombuffer(b[edge0: edge0 + SAMPLE], np.uint8)
    common.write_array("packet-bytes", np.stack([a, e]), rate=None,
                       about="the release file's bytes: row 0 from the first audio frame, row 1 straddling the "
                             "audio's end and the zip's start (the zip begins at column 'zip_column' of row 1)",
                       rows=[{"offset": audio0, "length": SAMPLE, "what": "audio frames"},
                             {"offset": edge0, "length": SAMPLE, "what": "audio | zip"}],
                       zip_column=zip0 - edge0)
    texts = {}
    for name in TEXTS:
        if name in names:
            texts[name] = {"text": z.read(name).decode("utf-8")[:CHARS],
                           "offset": next(x["offset"] for x in entries if x["name"] == name)}
    common.write_json("packet-text.json", {"chars": CHARS, "source": out["file"] + " (read from its zip)",
                                           "files": texts}, indent=1)
    py = sum(1 for n in names if n.endswith(".py"))
    common.say(f"packet.json: {len(b):,} bytes, audio {audio0:,}-{zip0:,}, zip at {zip0:,}, {len(entries)} entries "
               f"({py} .py), throat {out['throat']}")


if __name__ == "__main__":
    main()
