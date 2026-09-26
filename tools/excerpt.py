"""Cut a rendition's first verse and refrain out of its full render, for listening side by side.

    uv run python tools/excerpt.py renders/x.flac [--out renders/x.verse-refrain.flac] [--from verse] [--to refrain]

Reads the rendition's score (x.score.json, written beside every render) for where its sections fall, and
writes the stretch from the first `--from` section's start (a beat early, for its pickup) to the end of the
first `--to` section after it (plus a second of its ring), with short fades, as FLAC. The audio is the
mastered render's own, not re-mastered.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf


def cut(path: Path, out: Path, first: str = "verse", last: str = "refrain") -> tuple[float, float]:
    score = json.loads(path.with_suffix(".score.json").read_text())
    sections = score["sections"]
    start = next(s for s in sections if s[0] == first)
    after = [s for s in sections if s[1] >= start[1]]
    end = next((s for s in after if s[0] == last), after[-1])
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    a = max(0, int((start[1] - 1.0) * sr))
    b = min(len(x), int((end[2] + 1.0) * sr))
    y = x[a:b].copy()
    fade = int(0.25 * sr)
    y[:fade] *= np.linspace(0.0, 1.0, fade)[:, None]
    y[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
    sf.write(str(out), y, sr, subtype="PCM_16")
    return a / sr, b / sr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("render")
    ap.add_argument("--out")
    ap.add_argument("--from", dest="first", default="verse")
    ap.add_argument("--to", dest="last", default="refrain")
    args = ap.parse_args()
    path = Path(args.render)
    out = Path(args.out) if args.out else path.with_name(path.stem + ".verse-refrain.flac")
    a, b = cut(path, out, args.first, args.last)
    print(f"{out}  {a:.1f}-{b:.1f} s")


if __name__ == "__main__":
    main()
