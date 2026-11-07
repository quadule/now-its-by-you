"""Render tools/throat/scylla.py's plan with Scylla's Band, in its own venv (dev only).

    $SCYLLA/.venv/bin/python tools/throat/scylla_batch.py [renders/throat/scylla-plan.json] [--root renders/throat]
        [--only scylla-gwen.h-now-its-by-you ...] [--jobs 4]

Every phrase is sung with exactly the phones, frames and melody the plan gives (the singing mode, the bundle's
singing sampler and steps, its BigVGAN decoder), its lead-in and release gated as Scylla's own singing.py
gates them, and placed on its segment's clock. Writes renders/throat/corpus/scylla-<voice>/<segment>.wav
(24 kHz, 16-bit) beside the label scylla.py wrote; segments already rendered are skipped. Uses only the
standard library, numpy and soundfile beside scyllasband itself, so it runs in SCYLLA's venv.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
SCYLLA = Path(os.environ.get("SCYLLA", Path.home() / "Code/scyllasband"))
SR = 24000
_engine = None


def engine(threads: int):
    global _engine
    if _engine is None:
        from scyllasband.runtime import ScyllasBandRuntime

        _engine = ScyllasBandRuntime.from_bundle(SCYLLA / "scyllasband/models/litert", threads=threads).engine
    return _engine


def melody(spans: list[dict], total: int) -> np.ndarray:
    out = np.zeros((total, 3), np.float32)
    for m in spans:
        a, b = int(m["a"]), min(int(m["b"]), total)
        if b <= a:
            continue
        out[a:b, 0] = (m["pitch"] - 60) / 24
        out[a:b, 1] = (np.arange(b - a) + 0.5) / (b - a)
        out[a:b, 2] = 1.0
    return out


def render(job: tuple) -> str:
    item, seg, root, threads = job
    from scyllasband.engine import Sentence
    from scyllasband.singing import gate_phrase

    e = engine(threads)
    voice = item["voice"]
    dest = Path(root) / "corpus" / f"scylla-{voice}" / f"{seg['index']}.wav"
    if dest.exists():
        return f"{seg['index']}: kept"
    singing = e.singing
    mode = e.delivery_modes["sung"]
    song = np.zeros(int(np.ceil((seg["t1"] - seg["t0"]) * SR)), np.float32)
    delivery = (np.zeros((1, 5), np.float32), np.zeros((1, 5), bool))
    t = time.time()
    for i, p in enumerate(seg["phrases"]):
        rng = np.random.default_rng(int(item["seed"]) + i)
        result = e.synthesize_sentence(Sentence(phones=p["phones"], word_starts=p["word_starts"]), voice=voice, language="en_us",
                                       delivery=delivery, steps=int(singing.get("steps", 4)), sampler=str(singing.get("sampler", "euler")),
                                       rng=rng, durations=[int(f) for f in p["frames"]], melody=melody(p["melody"], int(p["total"])),
                                       delivery_mode=mode, guidance=float(singing.get("guidance", 1.0)))
        audio = e.decode(result.latents, voice=voice, language="en_us", decoder=str(singing.get("decoder", "bigvgan")))
        first = min(m["a"] for m in p["melody"]) * 512 / SR
        last = max(m["b"] for m in p["melody"]) * 512 / SR
        audio = gate_phrase(audio, SR, first=first, last=last)
        offset = int(round(p["start"] * SR))
        if offset < 0:
            audio, offset = audio[-offset:], 0
        n = min(audio.size, song.size - offset)
        if n > 0:
            song[offset:offset + n] += audio[:n]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.wav")
    sf.write(str(tmp), np.clip(song, -1, 1), SR, subtype="PCM_16")
    tmp.rename(dest)
    return f"{seg['index']}: {song.size / SR:.1f} s in {time.time() - t:.1f} s"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", type=Path, nargs="?", default=ROOT / "renders/throat/scylla-plan.json")
    ap.add_argument("--root", type=Path, default=ROOT / "renders/throat")
    ap.add_argument("--only", nargs="*", default=None, help="only these plan items (ids)")
    ap.add_argument("--jobs", type=int, default=4, help="processes, each with its own engine")
    ap.add_argument("--threads", type=int, default=4, help="CPU threads per engine")
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text())["items"]
    if args.only:
        plan = [p for p in plan if p["id"] in args.only]
    jobs = [(item, seg, str(args.root), args.threads) for item in plan for seg in item["segments"]]
    t = time.time()
    with ProcessPoolExecutor(args.jobs) as pool:
        for k, line in enumerate(pool.map(render, jobs, chunksize=1)):
            print(f"[{k + 1}/{len(jobs)}] {line}", flush=True)
    print(f"done in {(time.time() - t) / 60:.1f} min")


if __name__ == "__main__":
    main()
