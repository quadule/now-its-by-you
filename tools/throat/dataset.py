"""The learned throat's training set: what was sung, frame by frame, against how it sounded (dev only).

    uv run python tools/throat/dataset.py [renders/throat] [--out renders/throat/dataset.npz]

For every corpus segment that tools/throat/check.py kept, the inputs the throat will get when it
sings (songbird.synth.throat.timeline: the phone, its neighbours, how far through it, its length,
the syllable's stress, the note's level; plus log f0 and the singer) and what it should give back
(the WORLD envelope and aperiodicity on their mel grids), every 5 ms. The phones come from MFA's
alignment (tools/throat/phones.py) turned into songbird's inventory: stress dropped, an unstressed
AH is AX, a diphthong running into r (fire, hour) one phone. The quiet between phones is silence,
or a breath where it's loud enough just before the singing starts again. Notes whose alignment
MFA got wrong are masked out, with their consonants.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from songbird.synth import throat  # noqa: E402

CMU_VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
BREATH_DB = -32.0  # a gap this close to the singing's median level, just before a phrase, is a breath


def ours(aligned: list[dict], notes: list[dict]) -> list[dict]:
    """MFA's phones in songbird's inventory, merging a diphthong with the r after it."""
    out = []
    i = 0
    while i < len(aligned):
        p = dict(aligned[i])
        base, digit = p["phone"].rstrip("012"), p["phone"][len(p["phone"].rstrip("012")):]
        if base in CMU_VOWELS:
            p["stressed"] = digit in ("1", "2")
            if base == "AH" and digit == "0":
                base = "AX"
            nxt = aligned[i + 1] if i + 1 < len(aligned) else None
            if (base in ("AY", "AW", "OY") and nxt and nxt["phone"] == "R" and nxt["note"] == p["note"]
                    and abs(nxt["start"] - p["end"]) < 0.002):
                base, p["end"] = base + "R", nxt["end"]
                i += 1
        p["phone"] = base
        out.append(p)
        i += 1
    stress = {p["note"]: p["stressed"] for p in out if "stressed" in p}
    for p in out:
        p.setdefault("stressed", stress.get(p["note"], False))
    return out


def corrected(al: dict, notes: list[dict]) -> dict:
    """MFA's alignment with the score's help where it's weakest: a syllable that starts on its vowel
    ("it", "out", "I") after a sung vowel or liquid often has its start pulled back into the word
    before (MFA can't hear the join). SoulX starts such a vowel where its note starts, so the
    boundary goes back to the note (if both sides keep 30 ms). Then every note is judged again:
    plausible if its vowel starts within [-0.15, +0.25] s of its note and lasts a fifth of it."""
    phones = [dict(p) for p in al["phones"]]
    by_note: dict[int, list[int]] = {}
    for i, p in enumerate(phones):
        by_note.setdefault(p["note"], []).append(i)
    for k, idx in by_note.items():
        first = phones[idx[0]]
        if k == 0 or first["role"] != "vowel" or idx[0] == 0:
            continue
        target = notes[k]["sung_start"]
        before = phones[idx[0] - 1]
        if abs(first["start"] - target) > 0.06 and target - before["start"] >= 0.03 and first["end"] - target >= 0.03:
            before["end"] = first["start"] = round(target, 4)
    out = []
    for k, n in enumerate(notes):
        vowel = next((phones[i] for i in by_note.get(k, []) if phones[i]["role"] == "vowel"), None)
        if vowel is None:
            out.append(dict(found=False, plausible=False))
            continue
        off = vowel["start"] - n["sung_start"]
        ok = -0.15 <= off <= 0.25 and vowel["end"] - vowel["start"] >= 0.2 * (n["sung_end"] - n["sung_start"])
        out.append(dict(found=True, vowel_start=vowel["start"], vowel_end=vowel["end"], offset=round(off, 4), plausible=ok))
    return dict(al, phones=phones, notes=out)


def build(label: dict, al: dict, feats, singer: int):
    al = corrected(al, label["notes"])
    f0 = feats["f0"].astype(np.float64)
    level = feats["level"].astype(np.float64)
    n = len(f0)
    times = np.arange(n) * throat.FRAME
    phones = ours(al["phones"], label["notes"])
    # each note's level: its vowel's median frame level, against the segment's median vowel
    note_db = {}
    for p in phones:
        if p["role"] == "vowel":
            i0, i1 = np.searchsorted(times, [p["start"], p["end"]])
            if i1 > i0:
                note_db[p["note"]] = float(np.median(level[i0:i1]))
    if not note_db:
        return None
    mid = float(np.median(list(note_db.values())))
    segs = []
    for p in phones:
        lv = float(np.clip(note_db.get(p["note"], mid) - mid, -15.0, 10.0))
        segs.append((p["phone"], p["start"], p["end"], p["stressed"], lv, p["role"]))
    # breaths: the loud end of a long gap, just before the singing starts again
    with_breaths = []
    for k, s in enumerate(segs):
        gap_start = segs[k - 1][2] if k else 0.0
        if s[1] - gap_start > 0.12:
            a = max(gap_start + 0.03, s[1] - 0.45)
            i0, i1 = np.searchsorted(times, [a, s[1] - 0.01])
            loud = np.flatnonzero(level[i0:i1] > mid + BREATH_DB)
            if len(loud) >= 4:
                with_breaths.append(("breath", times[i0 + loud[0]], times[i0 + loud[-1]] + throat.FRAME, False, s[4],
                                     "breath"))
        with_breaths.append(s)
    x = throat.timeline(with_breaths, n)
    # log f0, continuous through unvoiced frames
    voiced = f0 > 0
    lf0 = np.log(np.where(voiced, f0, 1.0))
    lf0 = np.interp(np.arange(n), np.flatnonzero(voiced), lf0[voiced]) if voiced.any() else np.full(n, np.log(200.0))
    # masked: each note MFA put somewhere implausible, with the notes either side of it (a misplaced
    # word stretches its neighbours' labels over itself), from their first phone to their last
    mask = np.ones(n, dtype=bool)
    notes = label["notes"]
    for k, f in enumerate(al["notes"]):
        if f.get("plausible"):
            continue
        near = range(max(k - 1, 0), min(k + 2, len(notes)))
        spans = [(p["start"], p["end"]) for p in phones if p["note"] in near]
        a = min([s for s, _ in spans] + [notes[near[0]]["sung_start"]])
        b = max([e for _, e in spans] + [notes[near[-1]]["sung_end"]])
        i0, i1 = np.searchsorted(times, [a, b])
        mask[i0:i1] = False
    x.update(lf0=lf0.astype(np.float32), singer=np.full(n, singer, dtype=np.int8), mask=mask, voiced=voiced,
             sp=feats["sp"], ap=feats["ap"])
    return x


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, nargs="?", default=ROOT / "renders/throat")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    quality = json.loads((args.root / "quality.json").read_text())
    kept = sorted(k for k, v in quality.items() if v["keep"])
    singers = sorted({k.split("/")[0] for k in kept})
    parts, index = [], []
    for key in kept:
        singer, seg = key.split("/")
        label = json.loads((args.root / "corpus" / singer / f"{seg}.json").read_text())
        al = json.loads((args.root / "align" / singer / f"{seg}.json").read_text())
        feats = np.load(args.root / "features" / singer / f"{seg}.npz")
        x = build(label, al, feats, singers.index(singer))
        if x is None:
            continue
        index.append((key, sum(len(p["phone"]) for p in parts), len(x["phone"])))
        parts.append(x)
    data = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    out = args.out or args.root / "dataset.npz"
    np.savez(out, **data, singers=np.array(singers), phones=np.array(throat.PHONES), segments=np.array([i[0] for i in index]),
             offsets=np.array([i[1] for i in index]), lengths=np.array([i[2] for i in index]))
    n = len(data["phone"])
    print(f"{len(index)} segments, {n} frames ({n * throat.FRAME / 60:.1f} min), {data['mask'].mean():.1%} unmasked, "
          f"singers {singers} -> {out}")
    counts = np.bincount(data["phone"][data["mask"]], minlength=len(throat.PHONES))
    print("frames per phone:", ", ".join(f"{p} {c}" for p, c in zip(throat.PHONES, counts)))


if __name__ == "__main__":
    main()
