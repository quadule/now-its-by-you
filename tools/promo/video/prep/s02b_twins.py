"""s02b_twins' data: breath 1's two synth twins of the whistle, what each is made of and what it sounds.

whistle~ is the analog synth (its oscillators and ladder are in physics/analog.json and analog-traces); epiano~ is
the tine piano (songbird/synth/epiano.py), struck modes heard through an electromagnetic pickup. This writes:

  s02b/stem-whistle~, s02b/stem-epiano~  each twin's own stem samples (stems/<part>.wav, 16-bit mono 44.1 kHz, the
                                         shared gain) from a bar before breath 1 to a bar after, int16 (1/32768)
  s02b/tine.json + s02b/tine.bin         every epiano~ tine struck in that span, exactly as the model rang it: the
                                         tip's swing (in heights over the pickup's pole) at the model's own rate
                                         (twice 44.1 kHz), float32, each note's run of samples in turn; per note
                                         its start, u0 (the tine's rest off the pole's axis) and the pickup scale

The tines are captured by rendering the stage version again (`songbird render performance/genome.json --replay
performance/record-live-A.json`, as replay.py does, its stems tagged by replay.install_stems) with a wrapper around
epiano._magnetic, the pickup, which is handed each tine's whole swing. The render goes to scratch/s02b/replay/; the
audio id it prints must be the stage version's (8660c5b6af71): the wrapper changes nothing.

    uv run python tools/promo/video/prep/s02b_twins.py           # stems and tines
    uv run python tools/promo/video/prep/s02b_twins.py --stems   # the stem excerpts only
"""
from __future__ import annotations

import os
import sys
import threading
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ROOT, SCRATCH, guard, read_json, say, write_array, write_json  # noqa: E402

SR = 44100
SR2 = 2 * SR
TWINS = ["whistle~", "epiano~"]
AFTER = 0.35  # s of each tine kept past its note's end: the damper's fall


def span() -> tuple[float, float]:
    tl = read_json(DATA / "timeline.json")
    sec = next(s for s in tl["sections"] if s["id"] == "breath1")
    return sec["t0"] - tl["bar"], sec["t1"] + tl["bar"]


def stems(t0: float, t1: float) -> None:
    for part in TWINS:
        with wave.open(str(guard(DATA / "stems" / f"{part}.wav")), "rb") as w:
            assert w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == SR
            a0 = int(round(t0 * SR))
            w.setpos(a0)
            a = np.frombuffer(w.readframes(int(round((t1 - t0) * SR))), dtype="<i2").copy()
        write_array(f"s02b/stem-{part}", a, f"{part}'s stem samples (stems/{part}.wav) over breath 1, a bar either side",
                    rate=SR, t0=a0 / SR, scale=1 / 32768, part=part)
        say(f"{part}: {len(a)} samples from {a0 / SR:.4f} s")


def tines(t0: float, t1: float) -> None:
    import replay
    from songbird.synth import epiano

    replay.install_stems()
    kept, lock = [], threading.Lock()
    magnetic = epiano._magnetic

    def magnetic_kept(x, u0, scale, out, start):
        s = start / SR2
        if replay.stem() == "epiano~" and t0 <= s < t1:
            # the note's run: its tine was rendered to (end + 0.45) s; keep the swing up to the damper's fall
            with lock:
                kept.append({"t": s, "start": int(start), "u0": float(u0), "scale": float(scale),
                             "x": np.array(x, dtype=np.float64, copy=True)})
        return magnetic(x, u0, scale, out, start)

    epiano._magnetic = magnetic_kept
    os.chdir(ROOT)
    os.environ.setdefault("SONGBIRD_THREADS", "2")
    out = guard(SCRATCH / "s02b" / "replay" / "render.flac")
    out.parent.mkdir(parents=True, exist_ok=True)
    from songbird.cli import main as cli

    sys.argv = ["songbird", "render", "performance/genome.json", "--replay", "performance/record-live-A.json",
                "--out", str(out.relative_to(ROOT))]
    try:
        cli()
    except SystemExit as e:
        if e.code not in (None, 0):
            raise
    kept.sort(key=lambda k: k["t"])
    score = read_json(DATA / "score.json")["parts"]["epiano~"]
    notes, runs, at = [], [], 0
    for k in kept:
        n = min(score, key=lambda q: abs(q["t"] - k["t"]))
        assert abs(n["t"] - k["t"]) < 0.002, (n["t"], k["t"])
        keep = min(len(k["x"]), int(round((n["d"] + AFTER) * SR2)))
        x = k["x"][:keep].astype(np.float32)
        runs.append(x)
        notes.append({"t": k["t"], "p": n["p"], "d": n["d"], "v": n["v"], "art": n["art"], "u0": k["u0"],
                      "scale": k["scale"], "x0": at, "n": len(x), "peak": float(np.max(np.abs(x)))})
        at += len(x)
    a = np.concatenate(runs) if runs else np.zeros(0, np.float32)
    write_array("s02b/tine", a, "every epiano~ tine struck over breath 1 (a bar either side): its tip's swing in heights "
                "over the pickup's pole, as the model rang it, at twice 44.1 kHz; note i is x0..x0+n (s02b/tine-notes.json)",
                rate=SR2)
    write_json("s02b/tine-notes.json", {"rate": SR2, "pickup": "flux ~ (1 + (u0 + x)^2)^-3/2, voltage = scale x its "
                                        "change a sample", "notes": notes}, indent=1)
    say(f"tines: {len(notes)} notes, {len(a)} samples")


def main(argv) -> None:
    t0, t1 = span()
    stems(t0, t1)
    if "--stems" not in argv:
        tines(t0, t1)


if __name__ == "__main__":
    main(sys.argv[1:])
