"""Hear and score the learned throat against the formant singer on a song's own words (dev only).

    uv run python tools/throat/listen.py [--song h] [--model renders/throat/model.npz] [--mix bright:1,alto:1]
        [--voice field=value ...] [--gv 1.0] [--out renders/throat/listen]

Sings the song's refrain and seed verses dry (as tools/wer_suite.py does), once with the formant
singer and once with the learned throat, both from the same schedule, pitch track and seed, writes
both, and scores them with Whisper the way the WER suite does.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from wer_suite import score_sections  # noqa: E402

from songbird import genome as G  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402
from songbird.synth import throat  # noqa: E402
from songbird.synth.voice import VoiceParams, schedule, sing  # noqa: E402

SR = 44100


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--song", default="h")
    ap.add_argument("--model", default=str(ROOT / "renders/throat/model.npz"))
    ap.add_argument("--mix", default="", help="singer weights, e.g. bright:1,alto:1 (default: all evenly)")
    ap.add_argument("--voice", nargs="*", default=[], metavar="FIELD=VALUE")
    ap.add_argument("--gv", type=float, default=1.0)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--skip-formant", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "renders/throat/listen")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    from faster_whisper import WhisperModel

    voice = replace(VoiceParams(), **{k: type(getattr(VoiceParams(), k))(v) for k, v in (kv.split("=") for kv in args.voice)})
    path = next((ROOT / "songs").glob(f"{args.song}*.json"))
    g = G.load(path)
    form = ("refrain",) + ("verse",) * len(g.seed_verses)
    score = realize(g, replace(choose_params(g), form=form))
    notes = sorted(score.part("voice"), key=lambda n: n.start)
    segs = schedule(notes, voice, g.lexicon)
    whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    args.out.mkdir(parents=True, exist_ok=True)
    engines = {"learned": lambda seed: throat.sing(notes, SR, voice, seed, g.lexicon, mix=args.mix, gv=args.gv, model=args.model)}
    if not args.skip_formant:
        engines["formant"] = lambda seed: sing(notes, SR, voice, seed=seed, lexicon=g.lexicon)
    for name, render in engines.items():
        edits = words = 0
        misses = []
        for seed in range(1, args.seeds + 1):
            y = render(seed)
            if seed == 1:
                sf.write(str(args.out / f"{path.stem}.{name}{args.tag}.wav"), (0.9 * y / np.abs(y).max()).astype(np.float32), SR)
            e, w, m, _ = score_sections(whisper, y, notes, segs, False)
            edits, words, misses = edits + e, words + w, misses + m
        print(f"{name:8} WER {edits / words:5.1%} ({edits}/{words})  " + ", ".join(misses[:12]), flush=True)


if __name__ == "__main__":
    main()
