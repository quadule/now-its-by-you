"""Spectrogram and level envelope of a finished render, for eyeballing balance and clicks.

    uv run python tools/mixview.py renders/b-coal-from-the-fire.flac [--start 0 --end 30]
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import stft

ap = argparse.ArgumentParser()
ap.add_argument("path")
ap.add_argument("--start", type=float, default=0.0)
ap.add_argument("--end", type=float, default=None)
args = ap.parse_args()

x, sr = sf.read(args.path)
end = args.end or len(x) / sr
seg = x[int(args.start * sr): int(end * sr)]
mono = seg.mean(axis=1)
f, t, Z = stft(mono, sr, nperseg=4096, noverlap=3072)
db = 20 * np.log10(np.abs(Z) + 1e-9)
fig, (a1, a2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
a1.pcolormesh(t + args.start, f, db, vmin=db.max() - 90, vmax=db.max(), cmap="magma", shading="auto")
a1.set_yscale("symlog", linthresh=200)
a1.set_ylim(40, sr / 2)
a1.set_ylabel("Hz")
a1.set_title(args.path)
# sample-to-sample jumps flag clicks; RMS in 20 ms windows shows the envelope
hop = int(0.02 * sr)
rms = np.sqrt(np.convolve(mono**2, np.ones(hop) / hop, mode="same"))
tt = np.arange(len(mono)) / sr + args.start
a2.plot(tt[::50], 20 * np.log10(rms[::50] + 1e-9), lw=0.7)
a2.plot(tt[::50], 20 * np.log10(np.abs(mono[::50]) + 1e-9), lw=0.3, alpha=0.4)
a2.set_ylim(-70, 0)
a2.set_ylabel("dBFS")
a2.set_xlabel("seconds")
fig.tight_layout()
out = args.path.rsplit(".", 1)[0] + ".mix.png"
fig.savefig(out, dpi=100)
jumps = np.abs(np.diff(seg, axis=0)).max(axis=1)
print(f"peak {20*np.log10(np.abs(x).max()):.2f} dBFS, largest sample step {jumps.max():.4f} at {args.start + jumps.argmax()/sr:.3f}s, wrote {out}")
