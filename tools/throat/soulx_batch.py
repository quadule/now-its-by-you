"""Render the learned throat's corpus plan with SoulX-Singer (dev only; run in SoulX-Singer's venv).

    SOULX=/Users/milo/Code/svs/SoulX-Singer
    $SOULX/.venv/bin/python -B tools/throat/soulx_batch.py renders/throat/plan.json [--out renders/throat/corpus]

Every segment of every item in the plan (tools/throat/corpus.py) is sung in its singer's timbre
(score control: note pitches, no f0) and written as 24 kHz 16-bit mono, the model's own rate, with
a .json beside it: the segment's notes (relative to the audio's start), phones, singer, key and the
seed. Segments already rendered are skipped, so a run can stop and resume. Whole songs go first,
then the rest round-robin across singers, so a partial corpus is balanced.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

SOULX = Path(os.environ.get("SOULX", "/Users/milo/Code/svs/SoulX-Singer"))
sys.path.insert(0, str(SOULX))

from cli.inference import build_model  # noqa: E402
from soulxsinger.utils.data_processor import DataProcessor  # noqa: E402
from soulxsinger.utils.file_utils import load_config  # noqa: E402

SR = 24000


def order(items: list[dict]) -> list[dict]:
    songs = [it for it in items if it["kind"] == "song"]
    rest = [it for it in items if it["kind"] != "song"]
    by_singer: dict[str, list[dict]] = {}
    for it in rest:
        by_singer.setdefault(it["singer"], []).append(it)
    interleaved = []
    while any(by_singer.values()):
        for name in sorted(by_singer):
            if by_singer[name]:
                interleaved.append(by_singer[name].pop(0))
    return songs + interleaved


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="default: corpus/ beside the plan")
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--cfg", type=float, default=3.0)
    ap.add_argument("--only", nargs="*", default=None, help="only these singers")
    ap.add_argument("--limit", type=float, default=None, help="stop after this many minutes of audio")
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text())
    out_dir = args.out or args.plan.parent / "corpus"

    config = load_config(str(SOULX / "soulxsinger/config/soulxsinger.yaml"))
    model = build_model(str(SOULX / "pretrained_models/SoulX-Singer/model.pt"), config, device=args.device)
    dp = DataProcessor(hop_size=config.audio.hop_size, sample_rate=SR,
                       phoneset_path=str(SOULX / "soulxsinger/utils/phoneme/phone_set.json"), device=args.device)
    prompts = {}
    done_audio = done_compute = 0.0
    for it in order(plan["items"]):
        if args.only and it["singer"] not in args.only:
            continue
        for k, seg in enumerate(it["segments"]):
            wav = out_dir / it["singer"] / f"{seg['index']}.wav"
            if wav.exists():
                continue
            if it["singer"] not in prompts:
                meta = plan["singers"][it["singer"]]["meta"]
                prompts[it["singer"]] = dp.process(copy.deepcopy(meta), meta["wav"])
            target = dp.process(copy.deepcopy(seg), None)
            seed = it["seed"] + k
            torch.manual_seed(seed)
            t = time.time()
            with torch.no_grad():
                y = model.infer({"prompt": prompts[it["singer"]], "target": target}, auto_shift=False, pitch_shift=0,
                                n_steps=args.steps, cfg=args.cfg, control="score", use_fp16=False)
            if args.device == "mps":
                torch.mps.synchronize()
            took = time.time() - t
            y = y.squeeze().float().cpu().numpy()
            wav.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(wav), np.clip(y, -1.0, 1.0), SR, subtype="PCM_16")
            label = {k2: v for k2, v in seg.items() if k2 not in ("duration", "text", "phoneme", "note_pitch", "note_type")}
            label.update(singer=it["singer"], source=it.get("source", "eleven-music"), item=it["item"], kind=it["kind"],
                         shift=it["shift"], seed=seed,
                         steps=args.steps, cfg=args.cfg, sr=SR, audio_s=round(len(y) / SR, 3), compute_s=round(took, 2),
                         soulx=dict(duration=seg["duration"], phoneme=seg["phoneme"], note_pitch=seg["note_pitch"],
                                    note_type=seg["note_type"]))
            wav.with_suffix(".json").write_text(json.dumps(label, indent=1))
            done_audio += len(y) / SR
            done_compute += took
            print(f"{seg['index']}: {len(y) / SR:.1f} s in {took:.1f} s; {done_audio / 60:.1f} min so far "
                  f"({done_audio / max(done_compute, 1e-6):.2f}x)", flush=True)
            if args.limit and done_audio / 60 >= args.limit:
                return


if __name__ == "__main__":
    main()
