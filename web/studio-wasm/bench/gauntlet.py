"""Every instrument the band can play, one short part each (4 bars, chords and a line, or a groove), so
every kernel runs: natively it keeps the stems (and times) as the reference, in Pyodide it renders the
same parts and compares bit for bit (float64, the stems before any mix).

  native:  SONGBIRD_THREADS=1 uv run python web/studio-wasm/bench/gauntlet.py OUT.npz
  pyodide: node web/studio-wasm/node/run.mjs --mount DIR:/ref --exec web/studio-wasm/bench/gauntlet.py
           (reads /ref/gauntlet.npz; set GAUNTLET_ONLY=name,name to run a few)"""

from __future__ import annotations

import os
import sys
import time

import numpy as np

from songbird.score import Note
from songbird.synth import instruments as I

SR = 44100
BEAT = 60.0 / 96.0
SETTINGS = dict(brightness=0.5, wear=0.25, ornament=0.5, body=1.0, maker=0, tonic=62)
CHORDS = ((0, 4, 7), (7, 11, 14), (9, 12, 16), (5, 9, 12))
TUNE = (0, 2, 4, 7, 9, 7, 4, 2)
KIT = (36, 42, 38, 42, 36, 46, 38, 49)


def part(name: str) -> tuple[Note, ...]:
    spec = I.spec(name)
    reg = spec.get("register")
    notes = []
    if reg is None:  # percussion: General MIDI pieces, eighths
        for k in range(32):
            notes.append(Note("x", 0.2 + k * BEAT / 2, 0.2 * BEAT, float(KIT[k % len(KIT)]), 0.5 + 0.3 * (k % 2 == 0)))
        return tuple(notes)
    lo, hi = reg
    mid = (lo + hi) // 2
    base = 60 + 12 * round((mid - 66) / 12)
    for bar in range(4):
        for p in CHORDS[bar]:
            q = base + p
            while q > hi:
                q -= 12
            while q < lo:
                q += 12
            notes.append(Note("x", 0.2 + bar * 4 * BEAT, 2 * BEAT, float(q), 0.55))
        for k, d in enumerate(TUNE[: 4]):
            q = base + 12 + d
            while q > hi:
                q -= 12
            notes.append(Note("x", 0.2 + (bar * 4 + k) * BEAT, 0.9 * BEAT, float(q), 0.6))
    return tuple(notes)


def render(name: str) -> np.ndarray:
    notes = part(name)
    length = int((max(n.start + n.dur for n in notes) + 2.0) * SR)
    return I.render_part(name, notes, SR, length, SETTINGS, seed=1)


def main():
    names = I.known()
    only = os.environ.get("GAUNTLET_ONLY")
    if only:
        names = [n for n in names if n in only.split(",")]
    web = sys.platform == "emscripten"
    ref = np.load("/ref/gauntlet.npz") if web else None
    out, rows = {}, []
    total = 0.0
    for name in names:
        t = time.perf_counter()
        try:
            y = render(name)
        except Exception as err:  # noqa: BLE001
            rows.append(f"{name:18s} error {type(err).__name__}: {err}")
            continue
        dt = time.perf_counter() - t
        total += dt
        if not web:
            out[name] = y
            out[f"{name}.time"] = np.array(dt)
            rows.append(f"{name:18s} {dt:7.3f}s  {y.shape}")
            continue
        want = ref[name]
        native = float(ref[f"{name}.time"])
        same = y.shape == want.shape and np.array_equal(y.view(np.int64), want.view(np.int64))
        if same:
            verdict = "same"
        elif y.shape != want.shape:
            verdict = f"SHAPE {y.shape} vs {want.shape}"
        else:
            d = np.abs(y - want).max()
            verdict = f"differs: max |diff| {d:.3g} ({20 * np.log10(d / (np.abs(want).max() + 1e-30) + 1e-30):.0f} dB re peak)"
        rows.append(f"{name:18s} {dt:7.3f}s  native {native:6.3f}s  x{dt / max(native, 1e-6):5.1f}  {verdict}")
    print("\n".join(rows))
    print(f"total {total:.2f}s")
    if not web:
        np.savez(sys.argv[1], **out)


if __name__ == "__main__":
    main()
