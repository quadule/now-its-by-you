"""Check a render against its score: pitch accuracy per note, and a picture.

    uv run python tools/analyze.py renders/b-coal-from-the-fire  [--part voice] [--start 0 --end 30]

Reads <stem>.<part>.wav (written by `songbird render --stems`) and
<stem>.score.json, tracks pitch with pYIN, and reports how far each sounded
note is from its intended pitch in cents. Writes <stem>.<part>.png.
"""

from __future__ import annotations

import argparse
import json

import librosa
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stem", help="render path without extension, e.g. renders/b-coal-from-the-fire")
    ap.add_argument("--part", default="voice")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    args = ap.parse_args()

    audio, sr = sf.read(f"{args.stem}.{args.part}.wav")
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    score = json.load(open(f"{args.stem}.score.json"))
    notes = [n for n in score["notes"] if n["part"] == args.part]

    pitches = [n["pitch"] for n in notes]
    fmin = librosa.midi_to_hz(min(pitches) - 3)
    fmax = librosa.midi_to_hz(max(pitches) + 3)
    hop = 256
    f0, voiced, _ = librosa.pyin(mono, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop, frame_length=2048)
    times = librosa.times_like(f0, sr=sr, hop_length=hop)

    errors = []
    for n in notes:
        # judge the steady middle of each note, away from attack and damping
        a, b = n["start"] + 0.25 * min(n["dur"], 0.4), n["start"] + min(n["dur"], 0.6) * 0.9
        sel = (times >= a) & (times <= b) & voiced
        if sel.sum() < 2:
            continue
        sounded = np.median(librosa.hz_to_midi(f0[sel]))
        errors.append(100.0 * (sounded - n["pitch"]))
    errors = np.array(errors)
    print(f"{args.part}: {len(notes)} notes, {len(errors)} tracked")
    if len(errors):
        print(f"  cents error: median {np.median(errors):+.1f}, mean |err| {np.mean(np.abs(errors)):.1f}, "
              f"max |err| {np.max(np.abs(errors)):.1f}, notes off by >25c: {(np.abs(errors) > 25).sum()}")

    # Picture: log-frequency spectrogram, score notes as boxes, pYIN track on top.
    end = args.end or len(mono) / sr
    seg = mono[int(args.start * sr) : int(end * sr)]
    spec = librosa.amplitude_to_db(np.abs(librosa.cqt(seg, sr=sr, hop_length=hop, fmin=librosa.midi_to_hz(36), n_bins=72)), ref=np.max)
    fig, ax = plt.subplots(figsize=(16, 6))
    ax.imshow(spec, origin="lower", aspect="auto", cmap="magma", vmin=-70,
              extent=[args.start, end, 36 - 0.5, 36 + 72 - 0.5])
    for n in notes:
        if n["start"] < end and n["start"] + n["dur"] > args.start:
            ax.add_patch(plt.Rectangle((n["start"], n["pitch"] - 0.45), n["dur"], 0.9, fill=False, ec="cyan", lw=0.8))
            if n.get("syllable"):
                ax.text(n["start"], n["pitch"] + 0.6, n["syllable"], color="white", fontsize=7)
    sel = (times >= args.start) & (times <= end)
    ax.plot(times[sel], librosa.hz_to_midi(f0[sel]), ".", color="lime", ms=1.5)
    ax.set_xlim(args.start, end)
    ax.set_ylim(min(pitches) - 14, max(pitches) + 5)
    ax.set_xlabel("seconds")
    ax.set_ylabel("MIDI pitch")
    ax.set_title(f"{args.stem} [{args.part}]  cyan = score, green = pYIN")
    fig.tight_layout()
    fig.savefig(f"{args.stem}.{args.part}.png", dpi=110)
    print(f"  wrote {args.stem}.{args.part}.png")


if __name__ == "__main__":
    main()
