"""Measure finished mixes the way a mastering engineer would, and draw them against a reference.

    uv run python tools/mixmeter.py renders/a.flac [renders/b.flac ...] [--ref reference.wav] [--png out.png]

Per file: integrated loudness (BS.1770-4), true peak (4x oversampled),
loudness range (EBU Tech 3342), PLR (true peak over loudness), crest factor
(sample peak over RMS), spectral tilt (the slope of the long-term average
spectrum in third-octave band energy, 100 Hz to 10 kHz, in dB per octave:
pink noise is 0), and the stereo picture: correlation of left and right
(1 mono, 0 unrelated, below 0 out of phase) and width (side energy over mid,
in dB), overall and over 400 ms windows, and correlation in three bands.

The picture: long-term average spectra at equal loudness, short-term
loudness over time, correlation and width over time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, welch

sys.path.insert(0, str(Path(__file__).parent.parent))
from songbird.synth import master  # noqa: E402

THIRDS = 1000.0 * 2.0 ** (np.arange(-17, 14) / 3.0)  # 20 Hz .. 20 kHz


def ltas(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Third-octave band energies (dB) of the mid channel, and their centres."""
    mid = x.mean(axis=1)
    f, p = welch(mid, sr, nperseg=16384, noverlap=8192)
    bands = []
    for c in THIRDS:
        lo, hi = c * 2 ** (-1 / 6), c * 2 ** (1 / 6)
        sel = (f >= lo) & (f < hi)
        bands.append(10 * np.log10(np.sum(p[sel]) * (f[1] - f[0]) + 1e-20))
    return THIRDS, np.array(bands)


def tilt(centres: np.ndarray, levels: np.ndarray, lo: float = 100.0, hi: float = 10000.0) -> float:
    sel = (centres >= lo) & (centres <= hi)
    return float(np.polyfit(np.log2(centres[sel]), levels[sel], 1)[0])


def stereo(x: np.ndarray, sr: int, window: float = 0.4) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Correlation and width (dB) per window, and the window energies (to skip silence)."""
    n = int(window * sr)
    k = len(x) // n
    l, r = x[: k * n, 0].reshape(k, n), x[: k * n, 1].reshape(k, n)
    ll, rr, lr = (l * l).sum(1), (r * r).sum(1), (l * r).sum(1)
    corr = lr / np.sqrt(ll * rr + 1e-30)
    mid, side = ll + rr + 2 * lr, ll + rr - 2 * lr
    width = 10 * np.log10((side + 1e-30) / (mid + 1e-30))
    return corr, width, ll + rr


def band_correlation(x: np.ndarray, sr: int, lo: float | None, hi: float | None) -> float:
    if lo and hi:
        sos = butter(4, [lo, hi], btype="bandpass", fs=sr, output="sos")
    elif lo:
        sos = butter(4, lo, btype="highpass", fs=sr, output="sos")
    else:
        sos = butter(4, hi, btype="lowpass", fs=sr, output="sos")
    y = sosfilt(sos, x, axis=0)
    return float((y[:, 0] * y[:, 1]).sum() / np.sqrt((y[:, 0] ** 2).sum() * (y[:, 1] ** 2).sum() + 1e-30))


def measure(path: str, start: float = 0.0, end: float | None = None) -> dict:
    x, sr = sf.read(path, always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[int(start * sr): int(end * sr) if end else None]
    lufs = master.loudness(x, sr)
    tp = master.true_peak(x)
    peak = 20 * np.log10(np.abs(x).max() + 1e-12)
    rms = 10 * np.log10(np.mean(x**2) + 1e-20)  # both channels, the whole file
    centres, levels = ltas(x, sr)
    corr, width, energy = stereo(x, sr)
    live = energy > energy.max() * 1e-4  # skip windows 40 dB under the loudest
    return {
        "path": path, "sr": sr, "x": x, "lufs": lufs, "tp": tp, "peak": peak,
        "lra": master.loudness_range(x, sr), "plr": tp - lufs, "crest": peak - rms,
        "centres": centres, "levels": levels - lufs, "tilt": tilt(centres, levels),
        "corr": corr, "width": width, "live": live,
        "corr_all": float((x[:, 0] * x[:, 1]).sum() / np.sqrt((x[:, 0] ** 2).sum() * (x[:, 1] ** 2).sum() + 1e-30)),
        "corr_bands": [band_correlation(x, sr, None, 250.0), band_correlation(x, sr, 250.0, 2000.0),
                       band_correlation(x, sr, 2000.0, None)],
        "short": master.short_term(x, sr),
    }


def report(m: dict) -> str:
    c, w = m["corr"][m["live"]], m["width"][m["live"]]
    lows, mids, highs = m["corr_bands"]
    return (f"{Path(m['path']).name}\n"
            f"  loudness {m['lufs']:6.1f} LUFS   true peak {m['tp']:5.1f} dBTP   sample peak {m['peak']:5.1f} dBFS\n"
            f"  LRA {m['lra']:4.1f} LU   PLR {m['plr']:4.1f} dB   crest {m['crest']:4.1f} dB   tilt {m['tilt']:+.2f} dB/oct\n"
            f"  correlation {m['corr_all']:+.2f} (400 ms windows: 10% {np.percentile(c, 10):+.2f}, median {np.median(c):+.2f}, "
            f"90% {np.percentile(c, 90):+.2f}); by band <250 Hz {lows:+.2f}, 250-2k {mids:+.2f}, >2k {highs:+.2f}\n"
            f"  width (side/mid) median {np.median(w):+.1f} dB (10% {np.percentile(w, 10):+.1f}, 90% {np.percentile(w, 90):+.1f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--ref", help="a reference recording drawn in grey")
    ap.add_argument("--png", help="where to draw (default: beside the first file, .meter.png)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    ms = [measure(p, args.start, args.end) for p in args.paths]
    ref = measure(args.ref) if args.ref else None
    for m in ([ref] if ref else []) + ms:
        print(report(m))
    if ref:
        print("third-octave balance against the reference (dB, at equal loudness):")
        for m in ms:
            d = m["levels"] - ref["levels"]
            octaves = [(63, 125), (125, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)]
            cells = []
            for lo, hi in octaves:
                sel = (m["centres"] >= lo * 0.9) & (m["centres"] < hi * 0.9)
                cells.append(f"{lo if lo < 1000 else str(lo // 1000) + 'k'}:{np.mean(d[sel]):+5.1f}")
            print(f"  {Path(m['path']).name}: " + "  ".join(cells))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    a1, a2, a3, a4 = axes.ravel()
    if ref:
        a1.semilogx(ref["centres"], ref["levels"], color="0.6", lw=3, label=f"reference: {Path(ref['path']).name}")
    for m in ms:
        a1.semilogx(m["centres"], m["levels"], lw=1.4, label=Path(m["path"]).name)
        t = np.arange(len(m["short"])) * 0.1 + args.start
        a2.plot(t, m["short"], lw=1, label=Path(m["path"]).name)
        tw = (np.arange(len(m["corr"])) * 0.4 + args.start)
        a3.plot(tw[m["live"]], m["corr"][m["live"]], ".", ms=2)
        a4.plot(tw[m["live"]], m["width"][m["live"]], ".", ms=2)
    a1.set(xlim=(20, 20000), ylim=(-60, 0), xlabel="Hz", ylabel="third-octave energy, dB re loudness", title="long-term average spectrum")
    a1.grid(True, which="both", alpha=0.3)
    a1.legend(fontsize=8)
    a2.set(ylim=(-40, -5), xlabel="seconds", ylabel="LUFS (3 s)", title="short-term loudness")
    a2.grid(True, alpha=0.3)
    a3.set(ylim=(-0.2, 1.05), xlabel="seconds", ylabel="correlation", title="left/right correlation (400 ms)")
    a3.grid(True, alpha=0.3)
    a4.set(ylim=(-40, 0), xlabel="seconds", ylabel="side/mid dB", title="width (400 ms)")
    a4.grid(True, alpha=0.3)
    fig.tight_layout()
    out = args.png or str(Path(args.paths[0]).with_suffix("")) + ".meter.png"
    fig.savefig(out, dpi=90)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
