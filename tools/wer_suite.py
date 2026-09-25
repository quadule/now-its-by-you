"""Intelligibility over every lyric we have: each song's refrain and all its seed verses.

    uv run python tools/wer_suite.py [--sketch b] [--show]

Renders the dry voice only (no instruments, no room), transcribes it with
Whisper base.en, and reports the word error rate per sketch and overall. One
refrain is too few words to steer by; this is a few hundred.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).parent))
from intelligibility import align, normalize  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402
from songbird import synth  # noqa: E402
from songbird.synth import master  # noqa: E402
from songbird.synth.voice import VoiceParams, schedule, sing  # noqa: E402

ROOT = Path(__file__).parent.parent
SR = 44100


def words_of(notes) -> list[str]:
    out, i = [], 0
    while i < len(notes):
        out.append(notes[i].word.replace("-", ""))
        i += notes[i].word_len
    return normalize(" ".join(out))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sketch", help="only sketches whose file name starts with this")
    ap.add_argument("--show", action="store_true", help="print every alignment")
    ap.add_argument("--seeds", type=int, default=1, help="average over this many voice seeds")
    ap.add_argument("--set", nargs="*", default=[], metavar="FIELD=VALUE", help="override VoiceParams fields")
    ap.add_argument("--mix", action="store_true", help="judge the finished mix (instruments, room, mastering), not the dry voice")
    args = ap.parse_args()
    voice = replace(VoiceParams(), **{k: type(getattr(VoiceParams(), k))(v) for k, v in (kv.split("=") for kv in args.set)})

    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    out_dir = ROOT / "renders" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    total_edits = total_words = 0
    for path in sorted((ROOT / "songs").glob("*.json")):
        if args.sketch and not path.stem.startswith(args.sketch):
            continue
        g = G.load(path)
        form = ("refrain",) + ("verse",) * len(g.seed_verses)
        score = realize(g, replace(choose_params(g), form=form))
        notes = sorted(score.part("voice"), key=lambda n: n.start)
        segs = schedule(notes, voice, g.lexicon)
        edits = words = 0
        misses, record = [], []
        for seed in range(1, args.seeds + 1):
            if args.mix:
                y = master.master(synth.render(score, seed=seed, voice=voice), SR).mean(axis=1)
            else:
                y = sing(notes, SR, voice, seed=seed, lexicon=g.lexicon)
            if seed == 1:
                sf.write(out_dir / f"{path.stem}.voice.wav", y, SR, subtype="FLOAT")
            e, w, m, r = score_sections(model, y, notes, segs, args.show)
            edits, words, misses, record = edits + e, words + w, misses + m, record + r
        total_edits += edits
        total_words += words
        print(f"{path.stem:24} WER {edits / words:5.1%}  ({edits}/{words})  " + ", ".join(misses[:16]) + (" …" if len(misses) > 16 else ""))
        (out_dir / f"{path.stem}.json").write_text(json.dumps(record, indent=1))
    print(f"{'overall':24} WER {total_edits / max(total_words, 1):5.1%}  ({total_edits}/{total_words})")


def score_sections(model, y, notes, segs, show):
    """Transcribe each section of one rendering; (edits, words, misses, record)."""
    # One section (a verse or the refrain) at a time, cut exactly where its
    # first phoneme starts and its last one ends. Whole songs send Whisper
    # into repetition loops on long held notes; single lines are too short
    # for it and it invents words at their edges.
    sections, current = [], []
    for n in notes:
        # a new section starts when the name changes, or a verse comes round again
        if current and (n.section != current[-1].section or (n.phrase == current[0].phrase and current[-1].line_end)):
            sections.append(current)
            current = []
        current.append(n)
    sections.append(current)
    edits = words = 0
    misses, record = [], []
    for line in sections:
        # vowels land exactly on note starts: walk out from the first and
        # last vowels over their onset and coda consonants
        i = next(k for k, g in enumerate(segs) if g.role == "vowel" and abs(g.t0 - line[0].start) < 1e-9)
        while i > 0 and segs[i - 1].role == "onset":
            i -= 1
        j = next(k for k, g in enumerate(segs) if g.role == "vowel" and abs(g.t0 - line[-1].start) < 1e-9)
        while j + 1 < len(segs) and segs[j + 1].role == "coda":
            j += 1
        a = max(int((segs[i].t0 - 0.05) * SR), 0)
        b = int((segs[j].t1 + 0.05) * SR)
        audio = resample_poly(y[a:b], 16000, SR).astype(np.float32)
        audio /= np.abs(audio).max() + 1e-9
        # no_repeat_ngram_size stops runaway loops ("O'Reee-e-e-e...") while
        # still allowing the lyric's own repeats, which are never five words long
        segments, _ = model.transcribe(audio, language="en", beam_size=5, temperature=0.0,
                                       condition_on_previous_text=False, vad_filter=False,
                                       no_repeat_ngram_size=5)
        heard = " ".join(s.text for s in segments)
        ref = words_of(line)
        e, pairs = align(ref, normalize(heard))
        edits, words = edits + e, words + len(ref)
        misses += [f"{r or '-'}→{h or '-'}" for r, h in pairs if r != h]
        record.append({"sung": " ".join(ref), "heard": heard.strip(), "edits": e})
        if show and e:
            print("    " + "  ".join(r if r == h else f"[{r or '-'}→{h or '-'}]" for r, h in pairs))
    return edits, words, misses, record


if __name__ == "__main__":
    main()
