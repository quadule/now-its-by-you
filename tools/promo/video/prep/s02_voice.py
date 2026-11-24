"""s02/: what the voice scene (verse 1) needs beyond throat/ and stems/.

    uv run python tools/promo/video/prep/s02_voice.py

- phones-line1.json: the phones of verse 1's first line as the human-0 take sang them (throat/lead-0.00.phones.json's
  segments), each with the continuous numbers the throat was told for it (throat.continuous's raw inputs from the
  captured call sing-000.pkl): position through the phone at its first and last frame, log duration, stress,
  level, and log f0 at its middle frame.
- wave-arp, wave-synthpad: int16 samples of those stems (stems/<part>.wav) over verse 1 with a bar either side.
- weights-index (uint16 [984, 1020]) and weights-array (uint8 [984, 1020]): for each pixel of throat/weights, the
  column of act-verse1 its weight is multiplied by (BIAS: by 1, ZERO: by 0, NONE: no weight there) and which array
  it belongs to; weights-arrays.json: the arrays in that order with singer_picture's two scales for each (`light`,
  the 99.5th percentile of |weight x input| from act-verse1's light_scale, or of |bias| for a bias; `size`, the
  99.5th percentile of |weight|, which sets a pixel's ink at rest)."""
from __future__ import annotations

import json
import pickle

import numpy as np
import soundfile as sf

import common

BIAS, ZERO, NONE = 65535, 65534, 65533
LINE1 = (10.4, 15.7)
WAVE = (8.4125, 33.4125)
RATE = 200


def phones() -> None:
    seg = common.read_json(common.DATA / "throat/lead-0.00.phones.json")["segments"]
    takes = common.read_json(common.DATA / "throat/takes.json")
    call = next(c["call"] for c in takes["calls"] if c["id"] == "lead-0.00")
    with open(common.guard(common.CAPTURE / f"sing-{call:03d}.pkl"), "rb") as f:
        cap = pickle.load(f)
    t, lf0 = cap["t"], np.asarray(cap["lf0"], np.float64)
    out = []
    for name, a, b, note in seg:
        if not (LINE1[0] <= a < LINE1[1]):
            continue
        i0, i1 = int(round(a * RATE)), int(round(b * RATE)) - 1
        mid = (i0 + i1) // 2
        out.append({"phone": name, "t0": a, "t1": b, "note": note,
                    "pos0": common.r(t["pos"][i0], 3), "pos1": common.r(t["pos"][i1], 3),
                    "dur": common.r(t["dur"][mid], 3), "stress": common.r(t["stress"][mid], 2),
                    "level": common.r(t["level"][mid], 2), "lf0": common.r(lf0[mid], 3)})
    common.write_json("s02/phones-line1.json", {
        "about": "verse 1 line 1's phones (lead-0.00, the take heard there) with what the throat was told: pos "
                 "(0..1 through the phone, at its first and last 5 ms frame), dur (natural log of the phone's "
                 "seconds), stress, level, lf0 (natural log of Hz) at its middle frame; from sing-%03d.pkl" % call,
        "phones": out}, indent=1)
    print(len(out), "phones")


def waves() -> None:
    for part in ("arp", "synthpad"):
        y, sr = sf.read(common.guard(common.DATA / f"stems/{part}.wav"), dtype="int16")
        a, b = int(round(WAVE[0] * sr)), int(round(WAVE[1] * sr))
        common.write_array(f"s02/wave-{part}", y[a:b], rate=sr, t0=a / sr, scale=1 / 32768,
                           about=f"stems/{part}.wav's samples (mono, the shared gain) from t0, 16-bit")


def weights() -> None:
    head = common.read_json(common.DATA / "throat/weights.json")
    shape = head["shape"]
    w = np.frombuffer(common.read_bytes(common.DATA / "throat/weights.bin"), "<f2").reshape(shape).astype(np.float32)
    act = common.read_json(common.DATA / "throat/act-verse1.json")
    slices = {s["vector"]: s for s in act["layout"]}
    index = np.full(shape, NONE, np.uint16)
    which = np.full(shape, 255, np.uint8)
    names = []
    for r in head["rects"]:
        if r["name"] not in names:
            names.append(r["name"])
    assert len(names) < 255
    for r in head["rects"]:
        n, x, y, cw, ch = r["name"], r["x"], r["y"], r["w"], r["h"]
        ys, xs = np.mgrid[0:ch, 0:cw]
        if n.endswith(".bias"):
            col = np.full((ch, cw), BIAS)
        elif n == "singer.weight":
            col = np.full((ch, cw), ZERO)
        elif n in ("phone.weight", "role.weight"):
            s = slices[n.split(".")[0]]
            assert ch == s["to"] - s["from"], n
            col = s["from"] + ys
        elif n.startswith("films."):
            s = slices["singer"]
            assert cw == s["to"] - s["from"], n
            col = s["from"] + xs
        else:
            s = slices[n.rsplit(".", 1)[0]]
            col = s["from"] + r["tile"] * 160 + xs if n.startswith("convs.") else s["from"] + xs
            assert col.max() < s["to"], n
        assert np.isfinite(w[y:y + ch, x:x + cw]).all(), n
        index[y:y + ch, x:x + cw] = col
        which[y:y + ch, x:x + cw] = names.index(n)
    assert int((which != 255).sum()) == 886372 == int(np.isfinite(w).sum())
    arrays = []
    for k, n in enumerate(names):
        v = np.abs(w[which == k])
        light = act["light_scale"].get(n)
        if light is None:
            light = float(max(np.percentile(v, 99.5), 1e-9))
        arrays.append({"name": n, "light": light, "size": float(np.percentile(v, 99.5)), "count": int(v.size)})
    common.write_array("s02/weights-index", index, about=(
        "for each pixel of throat/weights: the column of act-verse1 its weight is multiplied by; 65535 a bias (times 1), "
        "65534 singer.weight (times 0), 65533 no weight"))
    common.write_array("s02/weights-array", which, about="for each pixel of throat/weights: its array in "
                                                          "weights-arrays.json (255: none)")
    common.write_json("s02/weights-arrays.json", {
        "about": "the arrays of throat/weights in weights-array's order: light (singer_picture's per-array scale of "
                 "|weight x input|; for a bias, of |bias|), size (99.5th percentile of |weight|), count",
        "arrays": arrays}, indent=1)
    print(len(names), "arrays")


def main() -> None:
    phones()
    waves()
    weights()


if __name__ == "__main__":
    main()
