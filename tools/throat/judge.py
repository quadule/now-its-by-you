"""How well SoulX sang some renders: on pitch, and understood (dev only).

    uv run python tools/throat/judge.py renders/throat/house-test [--by singer]

For each rendered segment (a .wav with its label .json, as soulx_batch.py writes them): the share of
notes whose middle is within 50 cents (WORLD Harvest), and the words Whisper (base.en) hears against
the words sung. Totals per singer, to compare timbre prompts before rendering hours with one.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from intelligibility import align, normalize  # noqa: E402


def on_pitch(x: np.ndarray, sr: int, notes: list[dict]) -> tuple[int, int]:
    import pyworld as pw

    lo = 440.0 * 2 ** ((min(n["pitch"] for n in notes) - 7 - 69) / 12)
    hi = 440.0 * 2 ** ((max(n["pitch"] for n in notes) + 7 - 69) / 12)
    f0, _ = pw.harvest(x.astype(np.float64), sr, f0_floor=max(lo, 50.0), f0_ceil=min(hi, 1100.0), frame_period=5.0)
    good = 0
    for n in notes:
        a = int((n["sung_start"] + 0.3 * (n["sung_end"] - n["sung_start"])) / 0.005)
        b = int((n["sung_start"] + 0.8 * (n["sung_end"] - n["sung_start"])) / 0.005)
        v = f0[a:b]
        v = v[v > 0]
        if len(v) > 3 and abs(1200 * np.log2(np.median(v) / (440 * 2 ** ((n["pitch"] - 69) / 12)))) < 50:
            good += 1
    return good, len(notes)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", type=Path)
    args = ap.parse_args()
    from faster_whisper import WhisperModel

    whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    totals = defaultdict(lambda: np.zeros(4, dtype=int))  # notes on pitch, notes, word errors, words
    for wav in sorted(args.folder.glob("*/*.wav")):
        label = json.loads(wav.with_suffix(".json").read_text())
        x, sr = sf.read(str(wav))
        good, n = on_pitch(x, sr, label["notes"])
        words, k = [], 0
        while k < len(label["notes"]):
            words.append(label["notes"][k]["word"].replace("-", "").replace("*", ""))
            k += max(1, label["notes"][k]["word_len"])
        ref = normalize(" ".join(words))
        audio = resample_poly(x, 2, 3).astype(np.float32)
        parts, _ = whisper.transcribe(audio / (np.abs(audio).max() + 1e-9), language="en", beam_size=5, temperature=0.0,
                                      condition_on_previous_text=False, vad_filter=False, no_repeat_ngram_size=5)
        _, pairs = align(ref, normalize(" ".join(p.text for p in parts)))
        while pairs and not pairs[-1][0]:
            pairs.pop()
        errors = sum(r != h for r, h in pairs)
        totals[label["singer"]] += [good, n, errors, len(ref)]
        print(f"{wav.stem}: {good}/{n} notes on pitch, {errors}/{len(ref)} words missed", flush=True)
    print()
    for singer, (good, n, errors, words) in sorted(totals.items()):
        print(f"{singer:16} on pitch {good / n:5.1%}   words misheard {errors / words:5.1%}")


if __name__ == "__main__":
    main()
