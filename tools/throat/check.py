"""How well each corpus segment was sung: notes on pitch and vowels where the notes are (dev only).

    uv run python tools/throat/check.py [renders/throat] [--min-tune 0.85] [--min-align 0.85]

Per segment: the share of notes whose middle sits within 50 cents of the note (WORLD's f0, from
tools/throat/features.py) and the share of notes whose vowel MFA found where the note is sung
(tools/throat/phones.py). Writes renders/throat/quality.json, which training reads to leave out the
segments SoulX sang badly (below either threshold).
"""
import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def tune(label: dict, f0: np.ndarray, frame: float, within: float = 50.0) -> tuple[float, float]:
    errs = []
    for n in label["notes"]:
        a = int((n["sung_start"] + 0.3 * (n["sung_end"] - n["sung_start"])) / frame)
        b = int((n["sung_start"] + 0.8 * (n["sung_end"] - n["sung_start"])) / frame)
        seg = f0[a:b]
        seg = seg[seg > 0]
        errs.append(1200 * np.log2(np.median(seg) / (440 * 2 ** ((n["pitch"] - 69) / 12))) if len(seg) > 3 else np.inf)
    errs = np.array(errs)
    return float(np.mean(np.abs(errs) < within)), float(np.median(errs[np.isfinite(errs)])) if np.isfinite(errs).any() else np.nan


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, nargs="?", default=ROOT / "renders/throat")
    ap.add_argument("--min-tune", type=float, default=0.85)
    ap.add_argument("--min-align", type=float, default=0.6)
    # added for human takes (tools/throat/volunteers.py): people aren't score-controlled, and the network is
    # given the f0 they sang, not the note, so their tune only needs to show the voice was tracked in its key
    ap.add_argument("--cents", type=float, default=50.0, help="how near the note a note's middle must be to count as on tune")
    args = ap.parse_args()
    out = {}
    for lab_path in sorted((args.root / "corpus").glob("*/*.json")):
        singer, seg = lab_path.parent.name, lab_path.stem
        feats = args.root / "features" / singer / f"{seg}.npz"
        al = args.root / "align" / singer / f"{seg}.json"
        if not feats.exists():
            continue
        label = json.loads(lab_path.read_text())
        f = np.load(feats)
        on_tune, cents = tune(label, f["f0"], float(f["frame"]), args.cents)
        aligned = None
        if al.exists():
            notes = json.loads(al.read_text())["notes"]
            aligned = float(np.mean([bool(n.get("plausible")) for n in notes]))
        keep = on_tune >= args.min_tune and (aligned is None or aligned >= args.min_align)
        out[f"{singer}/{seg}"] = dict(on_tune=round(on_tune, 3), cents=round(cents, 1),
                                      aligned=None if aligned is None else round(aligned, 3), keep=bool(keep and aligned is not None))
    (args.root / "quality.json").write_text(json.dumps(out, indent=1))
    kept = [k for k, v in out.items() if v["keep"]]
    print(f"{len(out)} segments checked, {len(kept)} kept")
    for k, v in out.items():
        if not v["keep"]:
            print(f"  left out {k}: on tune {v['on_tune']:.2f}, aligned {v['aligned']}")


if __name__ == "__main__":
    main()
