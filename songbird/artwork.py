"""The song's cover, in every FLAC the program writes: a PICTURE metadata block (front cover, image/jpeg).

The cover (cover.jpg beside this file: the album art, 600 by 600) travels with the program, so every version
sung anywhere carries it too. libsndfile writes a FLAC's STREAMINFO and Vorbis comments but no pictures, so the
block is written here, with the standard library, between the file's other metadata and its first audio frame
(docs/PACKET.md). Metadata never touches the samples, so a rendition's id (their hash) is the same with the
cover or without it. The FLAC format: https://xiph.org/flac/format.html#metadata_block_picture
"""

from __future__ import annotations

import struct
from pathlib import Path

COVER = Path(__file__).with_name("cover.jpg")
TITLE = "Now It's by You"  # what the cover shows, and its description when a file names no title of its own
FRONT = 3  # the PICTURE block's picture type: the front cover
STREAMINFO, PADDING, VORBIS_COMMENT, PICTURE = 0, 1, 4, 6
MOST = 2**24 - 1  # a metadata block's length is 24 bits


def _jpeg_size(jpeg: bytes) -> tuple[int, int, int]:
    """(width, height, bits per pixel) from a JPEG's start-of-frame marker."""
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("the cover isn't a JPEG")
    at = 2
    while at + 4 <= len(jpeg):
        if jpeg[at] != 0xFF:
            raise ValueError("the cover's JPEG markers are damaged")
        marker = jpeg[at + 1]
        if marker == 0xFF:  # fill bytes before a marker
            at += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # markers with no length
            at += 2
            continue
        length = struct.unpack(">H", jpeg[at + 2:at + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # a start of frame
            precision, height, width, components = struct.unpack(">BHHB", jpeg[at + 4:at + 10])
            return width, height, precision * components
        at += 2 + length
    raise ValueError("the cover's JPEG has no frame")


def picture(jpeg: bytes | None = None, description: str | None = None) -> bytes:
    """A PICTURE block's body: the front cover, image/jpeg, its size, and a description (the song's title)."""
    jpeg = COVER.read_bytes() if jpeg is None else jpeg
    width, height, depth = _jpeg_size(jpeg)
    mime, words = b"image/jpeg", (description or TITLE).encode("utf-8")
    body = (struct.pack(">II", FRONT, len(mime)) + mime + struct.pack(">I", len(words)) + words
            + struct.pack(">IIIII", width, height, depth, 0, len(jpeg)) + jpeg)
    if len(body) > MOST:
        raise ValueError("the cover is too large for a FLAC metadata block")
    return body


def blocks(flac: bytes) -> tuple[list[tuple[int, bytes]], int]:
    """A FLAC's metadata blocks, as (type, body), and where its first audio frame begins."""
    if flac[:4] != b"fLaC":
        raise ValueError("not a FLAC file")
    out, at, last = [], 4, False
    while not last:
        if at + 4 > len(flac):
            raise ValueError("the FLAC's metadata runs past its end")
        head = flac[at]
        last, kind = bool(head & 0x80), head & 0x7F
        length = int.from_bytes(flac[at + 1:at + 4], "big")
        if kind == 127 or at + 4 + length > len(flac):
            raise ValueError("the FLAC's metadata is damaged")
        out.append((kind, flac[at + 4:at + 4 + length]))
        at += 4 + length
    if not out or out[0][0] != STREAMINFO:
        raise ValueError("the FLAC doesn't begin with its STREAMINFO")
    return out, at


def pictures(flac: bytes) -> list[dict]:
    """The pictures a FLAC carries: each one's type, mime type, description, size and image bytes."""
    found = []
    for kind, body in blocks(flac)[0]:
        if kind != PICTURE:
            continue
        ptype, n = struct.unpack(">II", body[:8])
        mime = body[8:8 + n].decode("ascii", "replace")
        at = 8 + n
        (m,) = struct.unpack(">I", body[at:at + 4])
        words = body[at + 4:at + 4 + m].decode("utf-8", "replace")
        at += 4 + m
        width, height, depth, colours, size = struct.unpack(">IIIII", body[at:at + 20])
        found.append({"type": ptype, "mime": mime, "description": words, "width": width, "height": height,
                      "depth": depth, "colours": colours, "data": body[at + 20:at + 20 + size]})
    return found


def embed(flac: bytes, description: str | None = None, jpeg: bytes | None = None) -> bytes:
    """The FLAC with the cover as its front cover: after its STREAMINFO, seek table and Vorbis comments (kept as
    they were), before any padding, replacing a front cover it had (so embedding twice changes nothing). The
    audio frames, and anything after them, follow byte for byte. `flac` must be the audio alone: bytes after
    it move with it (an attached packet's absolute offsets would not; pack.with_cover moves one)."""
    kept, audio_at = blocks(flac)
    kept = [(k, b) for k, b in kept if not (k == PICTURE and b[:4] == struct.pack(">I", FRONT))]
    body = picture(jpeg, description)
    at = max(i for i, (k, _) in enumerate(kept) if k != PADDING) + 1
    kept.insert(at, (PICTURE, body))
    out = bytearray(b"fLaC")
    for i, (kind, data) in enumerate(kept):
        out += bytes([kind | (0x80 if i == len(kept) - 1 else 0)]) + len(data).to_bytes(3, "big") + data
    return bytes(out) + flac[audio_at:]


def embed_file(path: str | Path, description: str | None = None) -> None:
    """A FLAC file (the audio alone, no packet) given the cover, in place."""
    path = Path(path)
    path.write_bytes(embed(path.read_bytes(), description))
