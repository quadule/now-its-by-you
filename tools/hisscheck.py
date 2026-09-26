"""Hiss in a finished render: bursts of highs, the highs' floor, and singers who sound where they don't sing.

    uv run python tools/hisscheck.py renders/x.flac [renders/y.flac | a/folder ...] [--list] [--limit -10]

For each render (its score, x.score.json, beside it says where the singers sing; a folder means every
render in it with a score beside it):

- bursts: 100 ms stretches where the band above 6 kHz comes within `--limit` dB (default 10) of the
  1-4 kHz band, and 1 s ones (what an ear hears as a hiss rather than a consonant), per minute, the
  worst, and how many fall where the texture is sparse (the mix 6 dB or more under its loud level).
  Each is called sibilant-like when nothing reaches over 12 kHz (the learned voice stops at 11.8 kHz)
  or broadband when it does (cymbals, brushes, noise). --list prints them;
- the floor: the highs' quietest tenth (their 10th percentile, 100 ms frames) where nobody sings and
  the band plays (within 20 dB of the loud level; 2 s of it at least), against the 1-4 kHz band
  there: a steady hiss raises it (a whisper in the rests mostly lies under 4 kHz: the singers' own
  check below is what finds one);
- the singers where they don't sing: if the render's stems lie beside it (`songbird render --stems`
  writes x.voice.wav, x.choir1.wav ...), each singer's level more than half a second from any of its
  notes, against its level while singing. A throat that whispers through its rests shows here (it
  did: docs/MIX.md, "The hiss").
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import stft

HOP, WIN = 0.05, 0.1


def _frames(x: np.ndarray, sr: int) -> tuple[np.ndarray, dict]:
    """Band levels (dB) of every 100 ms frame, 50 ms apart, and the frames' centre times."""
    nper = int(WIN * sr)
    f, t, z = stft(x.T, sr, nperseg=nper, noverlap=nper - int(HOP * sr), boundary=None, padded=False)
    p = (np.abs(z) ** 2).sum(axis=0)

    def band(lo, hi):
        return 10 * np.log10(p[(f >= lo) & (f < hi)].sum(0) + 1e-30)
    return t + WIN / 2, {"hi": band(6000, 16000), "mid": band(1000, 4000), "low6": band(6000, 12000),
                         "top": band(12000, 20000), "all": band(40, 20000)}


def _sung(score: dict, times: np.ndarray, margin: float = 0.5, parts=None) -> np.ndarray:
    """Whether any singer (or those in `parts`) has a note within `margin` s of each time."""
    near = np.zeros(len(times), dtype=bool)
    for n in score["notes"]:
        if (parts is None and (n["part"] == "voice" or n["part"].startswith("choir"))) or (parts and n["part"] in parts):
            a, b = np.searchsorted(times, [n["start"] - margin, n["start"] + n["dur"] + margin])
            near[a:b] = True
    return near


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    out, i = [], 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def check(path: Path, limit: float = -10.0, show: bool = False) -> dict:
    x, sr = sf.read(str(path), always_2d=True)
    score_path = path.with_suffix(".score.json")
    score = json.loads(score_path.read_text()) if score_path.exists() else None
    t, b = _frames(x, sr)
    ratio = b["hi"] - b["mid"]
    loud = np.percentile(b["all"], 90)
    sparse = b["all"] < loud - 6.0
    bursts = []
    for i, j in _runs(ratio > limit):
        k = i + int(np.argmax(ratio[i: j + 1]))
        kind = "sibilant-like" if b["top"][k] < b["low6"][k] - 25.0 else "broadband"
        bursts.append({"at": round(float(t[i] - WIN / 2), 2), "long": round(float((j - i) * HOP + WIN), 2),
                       "over": round(float(ratio[k]), 1), "sparse": bool(sparse[k]), "kind": kind})
    # 1 s windows (the band energies summed over 20 frames, 10 apart)
    lin = {k: 10 ** (v / 10) for k, v in b.items()}
    m = int(1.0 / HOP)
    second = [10 * np.log10(lin["hi"][i:i + m].sum() / lin["mid"][i:i + m].sum()) for i in range(0, len(t) - m, m // 2)]
    minutes = len(x) / sr / 60.0
    out = {
        "render": path.name, "minutes": round(minutes, 2),
        "bursts": len(bursts), "per_minute": round(len(bursts) / minutes, 1),
        "sparse": sum(e["sparse"] for e in bursts),
        "worst": max((e["over"] for e in bursts), default=None),
        "broadband": sum(e["kind"] == "broadband" for e in bursts),
        "seconds_over": sum(1 for v in second if v > limit),
        "worst_second": round(float(max(second)), 1) if second else None,
    }
    if score is not None:
        rests = ~_sung(score, t) & (b["all"] > loud - 20.0)  # nobody sings, and the band plays
        if rests.sum() > 40:
            out["floor_in_rests"] = round(float(np.percentile(b["hi"][rests], 10) - np.median(b["mid"][rests])), 1)
        stems = {}
        for part in sorted({n["part"] for n in score["notes"] if n["part"] == "voice" or n["part"].startswith("choir")}):
            stem = path.with_name(f"{path.stem}.{part}.wav")
            if not stem.exists():
                continue
            y, _ = sf.read(str(stem), always_2d=True)
            k = int(0.05 * sr)
            n = len(y) // k
            level = 10 * np.log10((y[: n * k] ** 2).reshape(n, k, -1).mean(axis=(1, 2)) + 1e-30)
            centres = (np.arange(n) + 0.5) * 0.05
            singing = _sung(score, centres, 0.0, {part})
            away = ~_sung(score, centres, 0.5, {part})
            if singing.any() and away.any():
                power = 10 ** (level / 10)
                sung = 10 * np.log10(np.mean(power[singing]))
                window = np.ones(20)  # a second
                whole = np.convolve(away.astype(float), window, "same") >= 20 - 1e-9  # seconds wholly away from its notes
                seconds = np.convolve(power * away, window, "same")[whole] / 20
                stems[part] = {"away": round(float(10 * np.log10(np.mean(power[away]) + 1e-30) - sung), 1),
                               "loudest_second_away": round(float(10 * np.log10(seconds.max() + 1e-30) - sung), 1)
                               if len(seconds) else None}
        if stems:
            out["singers_where_they_rest"] = stems
    if show:
        for e in bursts:
            print(f"   {e['at']:8.2f} s  {e['long']:.2f} s  {e['over']:+5.1f} dB  {e['kind']}{'  sparse' if e['sparse'] else ''}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("renders", nargs="+")
    ap.add_argument("--limit", type=float, default=-10.0, help="dB the highs may come to under 1-4 kHz (default -10)")
    ap.add_argument("--list", action="store_true", help="print every burst")
    ap.add_argument("--json", action="store_true", help="one JSON line per render")
    args = ap.parse_args()
    paths = []
    for p in map(Path, args.renders):
        paths += sorted(f for f in p.glob("*.flac") if f.with_suffix(".score.json").exists()) if p.is_dir() else [p]
    for p in paths:
        r = check(p, args.limit, args.list and not args.json)
        if args.json:
            print(json.dumps(r))
            continue
        line = (f"{r['render']:32} {r['bursts']:4d} bursts ({r['per_minute']:4.1f}/min, {r['sparse']} sparse, "
                f"{r['broadband']} broadband), worst {r['worst'] if r['worst'] is not None else '-':>5} dB; "
                f"1 s over: {r['seconds_over']}, worst {r['worst_second']:+.1f} dB")
        if "floor_in_rests" in r:
            line += f"; floor in rests {r['floor_in_rests']:+.1f} dB"
        print(line)
        for part, s in r.get("singers_where_they_rest", {}).items():
            loudest = f" (loudest second {s['loudest_second_away']:+.1f})" if s["loudest_second_away"] is not None else ""
            print(f"   {part:8} where it rests: {s['away']:+6.1f} dB against its singing{loudest}")


if __name__ == "__main__":
    main()
