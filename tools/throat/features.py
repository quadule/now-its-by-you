"""WORLD analysis of the learned throat's corpus (dev only).

    uv run python tools/throat/features.py [renders/throat/corpus] [--jobs 8]

For every rendered segment (a .wav with its .json label from tools/throat/soulx_batch.py), every
5 ms: f0 (Hz, 0 where unvoiced; WORLD's Harvest, searched within a fifth of the notes the segment
sings), the spectral envelope (CheapTrick) as natural-log power on a mel-spaced grid of MEL points,
the aperiodicity (D4C) on a coarser mel grid, and the frame's level in dB. Written as
renders/throat/features/<singer>/<segment>.npz; segments already analysed are skipped.

The mel grids keep what the ear resolves (about 30 Hz apart at F1, 100 Hz at 3 kHz) in a few
hundred bytes a frame; the synthesizer interpolates them back to its FFT bins.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FRAME = 0.005  # seconds
MEL = 128  # envelope points
AP_MEL = 32  # aperiodicity points
F_LO, F_HI = 40.0, 11800.0


def mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def unmel(m):
    return 700.0 * (10.0 ** (np.asarray(m) / 2595.0) - 1.0)


def grid(n: int) -> np.ndarray:
    """n frequencies (Hz), evenly spaced in mel from F_LO to F_HI."""
    return unmel(np.linspace(mel(F_LO), mel(F_HI), n))


def to_grid(spec: np.ndarray, sr: int, n: int) -> np.ndarray:
    """(frames, bins) on a linear FFT grid to (frames, n) on the mel grid, by linear interpolation."""
    bins = np.linspace(0.0, sr / 2, spec.shape[1])
    at = grid(n)
    return np.stack([np.interp(at, bins, row) for row in spec])


def analyse(wav: Path, out: Path) -> str:
    import pyworld as pw
    import soundfile as sf

    label = json.loads(wav.with_suffix(".json").read_text())
    x, sr = sf.read(str(wav), dtype="float64")
    pitches = [n["pitch"] for n in label["notes"]]
    lo = 440.0 * 2 ** ((min(pitches) - 7 - 69) / 12)
    hi = 440.0 * 2 ** ((max(pitches) + 7 - 69) / 12)
    f0, t = pw.harvest(x, sr, f0_floor=max(lo, 50.0), f0_ceil=min(hi, 1100.0), frame_period=FRAME * 1000)
    fft = pw.get_cheaptrick_fft_size(sr, max(lo, 50.0))
    sp = pw.cheaptrick(x, f0, t, sr, fft_size=fft)
    ap = pw.d4c(x, f0, t, sr, fft_size=fft)
    hop = int(round(FRAME * sr))
    frames = len(f0)
    padded = np.pad(x, (hop, hop + hop * frames))
    level = np.array([np.sqrt(np.mean(padded[i * hop: i * hop + 2 * hop] ** 2)) for i in range(frames)])
    np.savez_compressed(
        out,
        f0=f0.astype(np.float32),
        sp=np.log(np.maximum(to_grid(sp, sr, MEL), 1e-12)).astype(np.float16),
        ap=to_grid(ap, sr, AP_MEL).astype(np.float16),
        level=(20.0 * np.log10(np.maximum(level, 1e-6))).astype(np.float32),
        sr=sr, frame=FRAME, fft=fft,
    )
    return f"{wav.stem}: {frames} frames"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", type=Path, nargs="?", default=ROOT / "renders/throat/corpus")
    ap.add_argument("--out", type=Path, default=None, help="default: features/ beside the corpus")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    out_dir = args.out or args.corpus.parent / "features"
    todo = []
    for wav in sorted(args.corpus.glob("*/*.wav")):
        if not wav.with_suffix(".json").exists():
            continue
        out = out_dir / wav.parent.name / f"{wav.stem}.npz"
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            todo.append((wav, out))
    with ProcessPoolExecutor(args.jobs) as pool:
        for msg in pool.map(analyse, *zip(*todo)) if todo else []:
            print(msg, flush=True)
    print(f"{len(todo)} segments analysed into {out_dir}")


if __name__ == "__main__":
    main()
