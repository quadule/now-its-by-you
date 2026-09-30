"""How far a browser render is from the native one: int16 PCM (.npy) against int16 PCM.

usage: uv run python web/studio-wasm/tools/compare.py NATIVE.npy OTHER.npy
Prints: identical or not, samples that differ, max |diff| in LSB, the difference's level (dBFS RMS, and
under the music's own RMS), loudness (BS.1770, songbird.synth.master) of each, and the worst difference
between their spectra (1/3-octave bands, dB)."""

import sys

import numpy as np

from songbird.synth import SR, master


def bands(x: np.ndarray) -> np.ndarray:
    mono = x.mean(axis=1)
    spec = np.abs(np.fft.rfft(mono)) ** 2
    f = np.fft.rfftfreq(len(mono), 1.0 / SR)
    edges = 25.0 * 2.0 ** (np.arange(0, 30) / 3.0)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi > SR / 2:
            break
        out.append(10 * np.log10(spec[(f >= lo) & (f < hi)].sum() + 1e-20))
    return np.array(out)


def main():
    a, b = np.load(sys.argv[1]), np.load(sys.argv[2])
    print(f"shapes {a.shape} {b.shape}")
    n = min(len(a), len(b))
    a, b = a[:n].astype(np.int64), b[:n].astype(np.int64)
    d = b - a
    diff = np.count_nonzero(d)
    print(f"identical: {diff == 0 and a.shape == b.shape}")
    print(f"samples differing: {diff} of {d.size} ({100 * diff / d.size:.4f}%), max |diff| {np.abs(d).max()} LSB")
    if diff:
        rms_d = np.sqrt(np.mean(d.astype(float) ** 2)) / 32768
        rms_a = np.sqrt(np.mean(a.astype(float) ** 2)) / 32768
        print(f"difference RMS {20 * np.log10(rms_d + 1e-20):.1f} dBFS, {20 * np.log10(rms_d / rms_a):.1f} dB under the music")
    la, lb = master.loudness(a / 32768.0, SR), master.loudness(b / 32768.0, SR)
    print(f"loudness {la:.3f} / {lb:.3f} LUFS (diff {lb - la:+.4f} LU)")
    ba, bb = bands(a.astype(float)), bands(b.astype(float))
    print(f"1/3-octave bands: max |diff| {np.abs(ba - bb).max():.4f} dB")


if __name__ == "__main__":
    main()
