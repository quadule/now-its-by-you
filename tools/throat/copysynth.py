"""Copy synthesis: how much a corpus segment loses going through our features and our vocoder (dev only).

    uv run python tools/throat/copysynth.py SINGER SEGMENT [--out DIR]

Writes, side by side at 24 kHz: the SoulX original, WORLD's own resynthesis from full-resolution
features, and songbird.synth.throat's resynthesis from the corpus's mel-grid features. Prints each
one's level and its log-mel spectral distance from the original (dB, frames where the original is
within 40 dB of its peak). This is the ceiling for anything the learned throat predicts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from songbird.synth import throat  # noqa: E402


def logmel(x: np.ndarray, sr: int, n: int = 80) -> np.ndarray:
    import librosa

    m = librosa.feature.melspectrogram(y=x.astype(np.float32), sr=sr, n_fft=1024, hop_length=120, n_mels=n, fmax=sr / 2)
    return 10 * np.log10(np.maximum(m, 1e-10)).T


def distance(ref: np.ndarray, other: np.ndarray, sr: int) -> float:
    a, b = logmel(ref, sr), logmel(other, sr)
    k = min(len(a), len(b))
    a, b = a[:k], b[:k]
    loud = a.max(axis=1) > a.max() - 40
    return float(np.sqrt(np.mean((a[loud] - b[loud]) ** 2)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("singer")
    ap.add_argument("segment")
    ap.add_argument("--out", type=Path, default=ROOT / "renders/throat/copysynth")
    args = ap.parse_args()
    import pyworld as pw

    wav = ROOT / "renders/throat/corpus" / args.singer / f"{args.segment}.wav"
    feats = np.load(ROOT / "renders/throat/features" / args.singer / f"{args.segment}.npz")
    x, sr = sf.read(str(wav), dtype="float64")
    f0 = feats["f0"].astype(np.float64)
    t = np.arange(len(f0)) * throat.FRAME
    fft = int(feats["fft"])
    sp_full = pw.cheaptrick(x, f0, t, sr, fft_size=fft)
    ap_full = pw.d4c(x, f0, t, sr, fft_size=fft)
    world = pw.synthesize(f0, sp_full, ap_full, sr, frame_period=throat.FRAME * 1000)
    ours = throat.synthesize(f0, feats["sp"].astype(np.float64), feats["ap"].astype(np.float64), sr,
                             np.random.default_rng(0), fft=fft)
    args.out.mkdir(parents=True, exist_ok=True)
    rms = lambda y: 20 * np.log10(np.sqrt(np.mean(y**2)) + 1e-12)  # noqa: E731
    for name, y in (("original", x), ("world", world), ("ours", ours)):
        sf.write(str(args.out / f"{args.segment}.{name}.wav"), (0.9 * y / max(np.max(np.abs(y)), 1e-9)).astype(np.float32), sr)
        d = 0.0 if name == "original" else distance(x, y, sr)
        print(f"{name:9} {rms(y):6.1f} dB   {d:5.2f} dB from the original")


if __name__ == "__main__":
    main()
