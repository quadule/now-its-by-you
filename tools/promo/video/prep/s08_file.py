"""The file as s07_gather and s08_lineage draw it: where each FLAC frame lies, every zip entry's header and opening
text, the turn's stems and mix as fine envelopes, the whole mix's level in a few bands, and the voice's weights as
a picture. Writes renders/promo/video/data/s08/ (README beside the scenes: web/scenes/s08_lineage/DATA.md).

    uv run python tools/promo/video/prep/s08_file.py
"""
from __future__ import annotations

import io
import json
import struct
import zipfile

import numpy as np

import common

TEXT_CHARS = 2400          # characters of each text entry kept
_SEC = {x["id"]: x for x in common.read_json(common.DATA / "timeline.json")["sections"]}
# s: the window of the turn's envelopes (turn 2, from 4.5 s before it, as far back as the strand shows, to 3.5 s after)
TURN = (round(_SEC["turn2"]["t0"] - 4.5125, 4), round(_SEC["turn2"]["t1"] + 3.4875, 4))
ENV_RATE = 240             # envelope frames a second
# s: the window of the voices' envelopes (the bridge, from half a second before to half a second after)
BRIDGE = (round(_SEC["bridge"]["t0"] - 0.5125, 4), round(_SEC["bridge"]["t1"] + 0.4875, 4))
VOICES = ["voice", "choir1", "choir2", "choir3"]
TEXT_EXT = {"py", "txt", "json", "md", "toml", "js", "css", "html", ""}


def crc8(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
    return c


def utf8_number(b: bytes, i: int) -> tuple[int, int]:
    """FLAC's UTF-8-like coded frame number at b[i:]: (value, length)."""
    x = b[i]
    if x < 0x80:
        return x, 1
    n = 2 if x & 0xE0 == 0xC0 else 3 if x & 0xF0 == 0xE0 else 4 if x & 0xF8 == 0xF0 else 5 if x & 0xFC == 0xF8 else 6 if x & 0xFE == 0xFC else 7
    v = x & (0x7F >> n) if n < 7 else 0
    for k in range(1, n):
        v = (v << 6) | (b[i + k] & 0x3F)
    return v, n


def frame_header(b: bytes, i: int) -> int | None:
    """The frame number of a valid FLAC frame header at i (fixed block size, CRC-8 checked), or None."""
    if b[i] != 0xFF or b[i + 1] != 0xF8:
        return None
    bs, sr = b[i + 2] >> 4, b[i + 2] & 15
    if bs == 0 or sr == 15 or (b[i + 3] & 1):
        return None
    num, n = utf8_number(b, i + 4)
    j = i + 4 + n
    j += {6: 1, 7: 2}.get(bs, 0)
    j += {12: 1, 13: 2, 14: 2}.get(sr, 0)
    return num if crc8(b[i:j]) == b[j] else None


def frames(b: bytes, start: int, end: int, count: int) -> list[int]:
    """Each audio frame's byte offset, found in order by its header (frame numbers 0, 1, 2 ...)."""
    out, i, want = [], start, 0
    while want < count:
        i = b.find(b"\xff\xf8", i, end)
        if i < 0:
            raise ValueError(f"frame {want} not found")
        if frame_header(b, i) == want:
            out.append(i)
            want += 1
        i += 1
    return out


def envelope(x: np.ndarray, sr: int, t0: float, t1: float):
    """Peak |x| and RMS per 1/ENV_RATE s over [t0, t1), in dBFS (floor -100)."""
    hop = sr // ENV_RATE
    a, n = int(round(t0 * sr)), int(round((t1 - t0) * ENV_RATE))
    seg = np.zeros(n * hop)
    have = x[a: a + n * hop]
    seg[: len(have)] = have
    seg = seg.reshape(n, hop)
    pk = np.abs(seg).max(axis=1)
    rms = np.sqrt((seg ** 2).mean(axis=1) + 1e-30)
    db = lambda v: np.maximum(20 * np.log10(np.maximum(v, 1e-12)), -100)
    return db(pk), db(rms)


def main() -> None:
    import soundfile as sf

    pk = common.read_json(common.DATA / "packet.json")
    b = common.read_bytes(common.guard(common.RELEASE))
    audio = pk["flac"]["audio"]
    info = next(x["streaminfo"] for x in pk["flac"]["blocks"] if x["type"] == "STREAMINFO")
    count = -(-info["samples"] // info["max_block"])
    offs = frames(b, audio["offset"], audio["end"], count)
    assert offs[0] == audio["offset"], offs[0]

    # every entry: its header's bytes, and the opening of its text as the zip holds it
    z = zipfile.ZipFile(io.BytesIO(b))
    entries = []
    for e in pk["zip"]["entries"]:
        name = e["name"]
        leaf = name.rsplit("/", 1)[-1]
        ext = leaf.rsplit(".", 1)[-1] if "." in leaf else ""
        text = None
        if ext in TEXT_EXT:
            try:
                text = z.read(name).decode("utf-8")[:TEXT_CHARS]
            except UnicodeDecodeError:
                text = None
        entries.append({**{k: e[k] for k in ("name", "offset", "data_offset", "compressed", "size", "method")},
                        "header": b[e["offset"]: e["data_offset"]].hex(), "text": text})

    # the whole mix's level per video frame: RMS and eight bands (power summed over 12 of mix.env's 96 bands each)
    env = np.fromfile(common.guard(common.DATA / "stems/mix.env.bin"), np.uint8).reshape(-1, 99)
    db = env.astype(np.float64) * (100 / 255) - 100
    bands = 10 * np.log10((10 ** (db[:, 3:] / 10)).reshape(len(db), 8, 12).sum(axis=2) + 1e-30)
    lev = np.concatenate([db[:, :1], bands], axis=1)
    common.write_array("s08/mix-bands", np.clip(np.round((lev + 100) * 2.55), 0, 255).astype(np.uint8),
                       about="the release mix per video frame (frame i centred on i / 60 s): column 0 RMS dBFS, 1..8 "
                             "eight bands from 40 Hz to 16 kHz (each the power sum of 12 of stems/mix.env's 96), dB",
                       rate=60.0, t0=0.0, scale=1 / 2.55, offset=-100.0)

    # the turn: each stem's and the mix's peak and RMS at 240 a second
    parts = json.loads(common.read_text(common.DATA / "timeline.json"))["stems"]
    rows = []
    for p in parts:
        x, sr = sf.read(str(common.guard(common.DATA / f"stems/{p}.wav")), dtype="float64")
        rows += list(envelope(x, sr, *TURN))
    x, sr = sf.read(io.BytesIO(b[: audio["end"]]), dtype="float64")
    rows += list(envelope(x.mean(axis=1), sr, *TURN))
    turn = np.stack(rows).reshape(len(parts) + 1, 2, -1)
    common.write_array("s08/turn", np.clip(np.round((turn + 100) * 2.55), 0, 255).astype(np.uint8),
                       about="the turn's sound at 240 a second from t0: [part, (peak, rms), frame] dBFS; parts in "
                             "timeline.json's stem order (the stems' shared gain, stems/gain.json), then the release "
                             "mix itself ((left + right) / 2 of the FLAC)",
                       rate=float(ENV_RATE), t0=TURN[0], scale=1 / 2.55, offset=-100.0, parts=parts + ["mix"])

    # the bridge: the lead's and the choir's stems, peak and RMS at 240 a second
    rows = []
    for p in VOICES:
        x, sr = sf.read(str(common.guard(common.DATA / f"stems/{p}.wav")), dtype="float64")
        rows += list(envelope(x, sr, *BRIDGE))
    bridge = np.stack(rows).reshape(len(VOICES), 2, -1)
    common.write_array("s08/bridge", np.clip(np.round((bridge + 100) * 2.55), 0, 255).astype(np.uint8),
                       about="the bridge's voices at 240 a second from t0: [part, (peak, rms), frame] dBFS (the stems' "
                             "shared gain, stems/gain.json)", rate=float(ENV_RATE), t0=BRIDGE[0], scale=1 / 2.55,
                       offset=-100.0, parts=VOICES)

    # the voice's weights as a picture: |w| over its tile's 99.5th percentile, ** 0.8, max over 2 x 2
    wj = common.read_json(common.DATA / "throat/weights.json")
    w = np.fromfile(common.guard(common.DATA / "throat/weights.bin"), np.float16).astype(np.float32).reshape(wj["shape"])
    a = np.abs(w)
    pic = np.zeros_like(a)
    for rc in wj["rects"]:
        tile = a[rc["y"]: rc["y"] + rc["h"], rc["x"]: rc["x"] + rc["w"]]
        s = np.nanpercentile(tile, 99.5) if np.isfinite(tile).any() else 1
        pic[rc["y"]: rc["y"] + rc["h"], rc["x"]: rc["x"] + rc["w"]] = np.clip(np.nan_to_num(tile) / max(s, 1e-12), 0, 1) ** 0.8
    h, wd = (pic.shape[0] // 2) * 2, (pic.shape[1] // 2) * 2
    small = pic[:h, :wd].reshape(h // 2, 2, wd // 2, 2).max(axis=(1, 3))
    common.write_array("s08/weights", np.round(small * 255).astype(np.uint8),
                       about="the throat's 886,372 weights (throat/weights) as ink: |w| / its tile's 99.5th percentile, "
                             "clipped, ** 0.8, the max of each 2 x 2; 0 where no weight is")

    common.write_json("s08/file.json", {
        "about": "the release file for s07_gather and s08_lineage: each FLAC frame's byte offset (found by its header, "
                 "frame numbers in order, CRC-8 checked), samples per frame; every zip entry with its header's bytes "
                 f"(hex) and the first {TEXT_CHARS} characters of its text (null for binary entries)",
        "bytes": len(b), "audio": audio, "zip": pk["zip"]["offset"], "block": info["max_block"],
        "samples": info["samples"], "rate": info["sample_rate"], "frames": offs, "entries": entries,
        "manifest": pk["manifest"],
    })
    sizes = np.diff(offs + [audio["end"]])
    common.say(f"s08: {len(offs)} frames ({sizes.min()}-{sizes.max()} bytes), {len(entries)} entries, "
               f"{sum(1 for e in entries if e['text'])} with text, turn {turn.shape}, weights {small.shape}")


if __name__ == "__main__":
    main()
