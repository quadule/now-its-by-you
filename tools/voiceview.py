"""Spectrogram of a rendered voice with its phoneme schedule overlaid.

    uv run python tools/voiceview.py renders/b-refrain [--start 0 --end 6]

Reads <stem>.voice.wav and <stem>.score.json; writes <stem>.voice.png.
"""

from __future__ import annotations

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf
from scipy.signal import stft

from songbird.score import Note
from songbird.synth.voice import VoiceParams, schedule

ap = argparse.ArgumentParser()
ap.add_argument("stem")
ap.add_argument("--start", type=float, default=0.0)
ap.add_argument("--end", type=float, default=None)
ap.add_argument("--fmax", type=float, default=9000.0)
args = ap.parse_args()

x, sr = sf.read(f"{args.stem}.voice.wav")
mono = x.mean(axis=1) if x.ndim == 2 else x
end = args.end or len(mono) / sr
seg = mono[int(args.start * sr): int(end * sr)]
f, t, Z = stft(seg, sr, nperseg=1024, noverlap=896)
db = 20 * np.log10(np.abs(Z) + 1e-9)

score = json.load(open(f"{args.stem}.score.json"))
lexicon = score.get("lexicon", {})
notes = [Note(**n) for n in score["notes"] if n["part"] == "voice"]
segs = schedule(sorted(notes, key=lambda n: n.start), VoiceParams(), lexicon)

fig, ax = plt.subplots(figsize=(18, 6))
ax.pcolormesh(t + args.start, f, db, vmin=db.max() - 75, vmax=db.max(), cmap="magma", shading="auto")
ax.set_ylim(0, args.fmax)
for s in segs:
    if s.t1 < args.start or s.t0 > end:
        continue
    colour = {"vowel": "cyan", "onset": "lime", "coda": "orange", "breath": "white"}.get(s.role, "white")
    ax.axvline(s.t0, color=colour, lw=0.5, alpha=0.6)
    ax.text((s.t0 + s.t1) / 2, args.fmax * (0.93 if s.role == "vowel" else 0.86), s.phone,
            color=colour, fontsize=8, ha="center")
for n in notes:
    if args.start <= n.start <= end and n.syllable:
        ax.text(n.start, args.fmax * 0.79, n.syllable, color="white", fontsize=8)
ax.set_xlim(args.start, end)
ax.set_xlabel("seconds")
ax.set_ylabel("Hz")
ax.set_title(f"{args.stem} voice: cyan vowels, green onsets, orange codas")
fig.tight_layout()
fig.savefig(f"{args.stem}.voice.png", dpi=100)
print(f"wrote {args.stem}.voice.png")
