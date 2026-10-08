"""Run YingMusic-Singer over a job list from tools/throat/ying.py (dev only; in YingMusic-Singer's venv).

    YING=/Users/milo/Code/svs/YingMusic-Singer
    cd $YING && .venv/bin/python -I /path/to/songbird/tools/throat/ying_batch.py JOBS.json [--device mps]

Each job sings melody_audio's tune and timing to target_text in the timbre of ref_audio (which sings
ref_text), with the job's seed, and writes 44.1 kHz audio to out. Jobs already written are skipped. It must
run from the checkout (the model's code imports src.*); its venv is Python 3.10 with the requirements less
the Linux-only packages (bitsandbytes and friends), scipy 1.13.1, and espeak-ng from Homebrew.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", "/opt/homebrew/lib/libespeak-ng.dylib")
sys.path.insert(0, os.getcwd())

import torch  # noqa: E402
import torchaudio  # noqa: E402

from initialization import download_files  # noqa: E402
from src.YingMusicSinger.infer.YingMusicSinger import YingMusicSinger  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs")
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--steps", type=int, default=32)
    ap.add_argument("--cfg", type=float, default=3.0)
    args = ap.parse_args()
    jobs = [j for j in json.load(open(args.jobs)) if not os.path.exists(j["out"])]
    if not jobs:
        return
    download_files(task="infer")
    model = YingMusicSinger.from_pretrained("ASLP-lab/YingMusic-Singer").to(args.device).eval()
    for j in jobs:
        t = time.time()
        audio, sr = model(ref_audio_path=j["ref_audio"], melody_audio_path=j["melody_audio"],
                          ref_text=j["ref_text"], target_text=j["target_text"],
                          nfe_step=args.steps, cfg_strength=args.cfg, seed=j["seed"])
        os.makedirs(os.path.dirname(j["out"]), exist_ok=True)
        torchaudio.save(j["out"], audio, sr)
        print(f"{j['out']}: {audio.shape[-1] / sr:.1f} s in {time.time() - t:.1f} s", flush=True)


if __name__ == "__main__":
    main()
