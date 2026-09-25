"""Can a listener make out the words? A proxy: transcribe with Whisper, count word errors.

    uv run python tools/intelligibility.py renders/b-refrain            # the dry voice stem
    uv run python tools/intelligibility.py renders/b-refrain --mix      # the finished mix

Dev-only: needs faster-whisper and the base.en model (about 145 MB, downloaded on
first use). The lyric is never shown to the recognizer.
"""

from __future__ import annotations

import argparse
import json
import re

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import resample_poly


def normalize(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    return re.sub(r"[^a-z' ]+", " ", text).split()


def align(ref: list[str], hyp: list[str]) -> tuple[int, list[tuple[str, str]]]:
    """Levenshtein alignment: (edits, pairs) with '' marking insertions and deletions."""
    d = np.zeros((len(ref) + 1, len(hyp) + 1), dtype=int)
    d[:, 0] = np.arange(len(ref) + 1)
    d[0, :] = np.arange(len(hyp) + 1)
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]))
    pairs, i, j = [], len(ref), len(hyp)
    while i or j:
        if i and j and d[i, j] == d[i - 1, j - 1] + (ref[i - 1] != hyp[j - 1]):
            pairs.append((ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i and d[i, j] == d[i - 1, j] + 1:
            pairs.append((ref[i - 1], ""))
            i -= 1
        else:
            pairs.append(("", hyp[j - 1]))
            j -= 1
    return int(d[-1, -1]), pairs[::-1]


def lyric(score_path: str) -> list[str]:
    notes = sorted((n for n in json.load(open(score_path))["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    words, i = [], 0
    while i < len(notes):
        words.append(notes[i]["word"].replace("-", ""))
        i += notes[i]["word_len"]
    return normalize(" ".join(words))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("--mix", action="store_true", help="transcribe the finished FLAC instead of the dry voice")
    ap.add_argument("--model", default="base.en")
    args = ap.parse_args()

    path = f"{args.stem}.flac" if args.mix else f"{args.stem}.voice.wav"
    audio, sr = sf.read(path)
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = resample_poly(mono, 16000, sr).astype(np.float32)
    mono /= np.max(np.abs(mono)) + 1e-9

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(mono, language="en", beam_size=5, temperature=0.0,
                                   condition_on_previous_text=False, vad_filter=False)
    heard = " ".join(s.text for s in segments)

    ref = lyric(f"{args.stem}.score.json")
    edits, pairs = align(ref, normalize(heard))
    print(f"heard: {heard.strip()}")
    print(f"word error rate: {edits / max(len(ref), 1):.0%} ({edits} edits over {len(ref)} words)")
    print("  " + "  ".join(r if r == h else f"[{r or '-'}→{h or '-'}]" for r, h in pairs))


if __name__ == "__main__":
    main()
