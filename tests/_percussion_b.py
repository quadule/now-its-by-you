"""Shared by the hand percussion's tests: the registry's contract, as the band's test of every
instrument plays it, and each instrument's level target."""

from __future__ import annotations

import time

import numpy as np

from _levels_b import SETTINGS, TARGETS, streams
from songbird.score import Note

SR = 44100


def target(module, name: str) -> float:
    """The instrument's own level target if its SPEC names one, else percussion's."""
    return float(module.SPEC[name].get("loudness", TARGETS["percussion"]))


def play(module, name: str, notes, seconds: float, maker: int = 0, seed: int = 0, **settings) -> np.ndarray:
    rng, make = streams(name, seed, maker)
    return module.render(name, tuple(notes), SR, int(seconds * SR), rng, make, {**SETTINGS, "maker": maker, **settings})


def groove(name: str, start: float = 0.5) -> list[Note]:
    """Two bars of a drummer's groove at 100 BPM: kick on 1 and 3, snare on 2 and 4, hats on the eighths, a
    clap on the last beat and an open hat on its and."""
    beat, out = 0.6, []
    for bar in range(2):
        for eighth in range(8):
            t = start + (4 * bar + eighth / 2) * beat
            art = "hat-open" if (bar, eighth) == (1, 7) else "hat"
            out.append(Note(name, t, 0.3 if art == "hat-open" else 0.1, 60.0, 0.5, art=art))
            if eighth in (0, 4):
                out.append(Note(name, t, 0.1, 60.0, 0.8, art="kick"))
            if eighth in (2, 6):
                out.append(Note(name, t, 0.1, 60.0, 0.8, art="clap" if (bar, eighth) == (1, 6) else "snare"))
    return sorted(out, key=lambda n: n.start)


def contract(module, name: str, plain: str, typical: list[Note]) -> None:
    """What every instrument must do: see instruments.py's registry."""
    notes = groove(name)
    y = play(module, name, notes, 6.0)
    y2 = y.reshape(len(y), -1)
    assert y.shape[0] == 6 * SR and y.ndim in (1, 2) and np.all(np.isfinite(y)) and np.abs(y).max() > 0
    first = int((notes[0].start - 0.005) * SR)
    assert np.abs(y2[:first]).max() < 1e-4 * np.abs(y2).max()  # nothing before the first note
    for ch in range(y2.shape[1]):
        assert abs(y2[:, ch].mean()) < 1e-3 * np.sqrt(np.mean(y2[:, ch] ** 2))  # no DC
    # a note a millisecond long, the softest and the hardest, an art nobody knows
    short = play(module, name, [Note(name, 0.2, 0.001, 60.0, 0.7, art=plain)], 2.0)
    assert np.all(np.isfinite(short)) and np.abs(short).max() > 0
    silent = play(module, name, [Note(name, 0.2, 0.1, 60.0, 0.0, art=plain)], 1.0)
    full = play(module, name, [Note(name, 0.2, 0.1, 60.0, 1.0, art=plain)], 1.0)
    assert np.all(np.isfinite(silent)) and np.all(np.isfinite(full)) and np.abs(silent).max() < 1e-3 * np.abs(full).max()
    known = play(module, name, [Note(name, 0.2, 0.1, 60.0, 0.7, art=plain)], 1.0)
    assert np.array_equal(play(module, name, [Note(name, 0.2, 0.1, 60.0, 0.7, art="no-such-stroke")], 1.0), known)
    # a typical part forty seconds long, in well under four seconds
    period = max(n.start for n in typical) + 0.6
    long = [Note(name, n.start + k * period, n.dur, n.pitch, n.vel, art=n.art) for k in range(int(40 / period))
            for n in typical]
    play(module, name, typical[:2], 1.0)  # compiled
    t = time.process_time()
    play(module, name, long, 41.0)
    assert time.process_time() - t < 4.0
