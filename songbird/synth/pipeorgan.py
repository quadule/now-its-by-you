"""A pipe organ: flue pipes in ranks, a stop to a rank, blown steadily from a wind chest.

A flue pipe sounds as a whistle does (pipe.py): an air jet flips across the mouth's upper lip in step with the
air column inside. Once speaking, its tone is as steady as anything acoustic, a fixed set of harmonics, which is
why an organ is the instrument additive synthesis was invented for. The character is in which pipes, how they
speak, and the wind:

- **Ranks.** An open diapason (the organ's own sound: the harmonics falling about 6 dB an octave, the second
  strong), its octave (4') and fifteenth (2') the same pipes an octave and two up, a mixture of high ranks
  (1 1/3' and 1', the 6th and 8th harmonics of the key, each breaking back an octave where its pipes would be
  too small to make), a stopped flute (a pipe closed at the top: odd harmonics, the third about 15 dB down, the
  even ones faint) and an open flute 4'. The pedal has a bourdon 16' (stopped, an octave under the key) and an
  octave 8'. Each pipe of each rank is its own: voiced a little louder or softer, a little brighter or darker,
  and tuned a few cents off, by the machine that built it (more for a worn one); so the ranks beat gently
  against each other, the organ's chorus.
- **Speech.** A pipe's upper harmonics come first: the jet starts in its higher modes before the air column
  takes over, and the fundamental builds over 25 to 90 ms (longer for a bigger pipe); a breath of noise at the
  mouth, the chiff, sounds while it settles (more for a flute). The pallet closes and the pipe stops in a few
  hundredths of a second; the room carries it from there.
- **Wind.** A hiss of air at the mouths under every pipe that speaks, about 45 dB under it.
- **No touch.** A key opens its pallet or doesn't; velocity is the swell box instead, the division's level
  (12 dB from 0.2 to 1).

Registrations are named by articulation, held from the note that carries them (as organ.py's drawbars are):

    ""        diapason 8' and octave 4': the plain sound for singing to
    flutes    stopped flute 8' and open flute 4': soft and round
    full      diapason 8', octave 4', fifteenth 2' and the mixture: the full chorus
    pedal     (a pedal note) bourdon 16' and octave 8'

Each pipe's tone is a period read at its pitch (reed._read_mix, the harmonium's kernel, which cross-fades the
period it speaks with into the one it settles on, sample by sample): no kernel of its own.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from . import reed, touch
from .iir import butter

SPEC = {
    "pipeorgan": dict(
        family="organ",
        role="comping",
        register=(24, 96),
        place=(0.0, 0.9),
        level=0.18,
        poly=True,
        articulations={
            "": "diapason 8' and octave 4' (the plain sound), or whatever was last named",
            "flutes": "from this note on: stopped flute 8' and open flute 4', soft",
            "full": "from this note on: diapason 8', octave 4', fifteenth 2' and a mixture",
            "pedal": "a pedal note: bourdon 16' and octave 8'",
        },
        about="a pipe organ: diapasons, flutes and a mixture in ranks, a pedal with a 16' bourdon; each pipe its "
              "own, speaking upper harmonics first with a little chiff; velocity is the swell box",
        dynamic=True,
    ),
}

DEFAULTS = dict(brightness=0.5, wear=0.25)

# A rank: (feet, spectrum, gain). The feet give its pitch against the key (8' the key's own, 4' an octave up,
# 16' an octave down, 1 1/3' the 6th harmonic); the spectrum its pipes' tone (SPECTRA)
REGISTRATIONS = {
    "": ((8.0, "diapason", 1.0), (4.0, "diapason", 0.5)),
    "flutes": ((8.0, "stopped", 0.9), (4.0, "flute", 0.35)),
    "full": ((8.0, "diapason", 1.0), (4.0, "diapason", 0.6), (2.0, "diapason", 0.42), (4.0 / 3.0, "mixture", 0.26),
             (1.0, "mixture", 0.2)),
    "pedal": ((16.0, "bourdon", 1.0), (8.0, "diapason", 0.45)),
}
# A spectrum: (slope: harmonic k at k**-slope, even harmonics' scale, chiff's level, speech's length factor)
SPECTRA = {
    "diapason": (1.0, 1.15, 0.05, 1.0),
    "mixture": (1.3, 1.0, 0.03, 0.7),
    "stopped": (1.6, 0.08, 0.1, 1.2),
    "flute": (2.0, 0.5, 0.08, 1.0),
    "bourdon": (1.7, 0.1, 0.04, 1.4),
}
BRIGHTER = 0.7  # the period a pipe speaks with: its harmonics fall this much less steeply
SWELL = 12.0  # dB from velocity 0.2 to 1
RELEASE = 0.045  # s: the pallet closes, the pipe stops
WIND = 0.006  # the hiss at the mouths, against a speaking pipe
BREAK = 2100.0  # Hz: a mixture's pipe above this breaks back an octave


def _hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


def speech(f: float, factor: float) -> float:
    """How long a pipe takes to speak (to its steady tone), in seconds: 90 ms for a 16' C, 25 ms for a small one."""
    return float(np.clip(0.09 * (65.4 / max(f, 1.0)) ** 0.35, 0.025, 0.09)) * factor


class PipeOrgan:
    """One machine's organ: each pipe's voicing and tuning (from `make`), its wind."""

    def __init__(self, sr: int, make: np.random.Generator, settings: dict):
        self.sr = sr
        s = {**DEFAULTS, **(settings or {})}
        self.brightness = float(np.clip(s["brightness"], 0.0, 1.0))
        self.wear = float(np.clip(s["wear"], 0.0, 1.0))
        self.seed = int(make.integers(1 << 30))
        # each pipe (rank's spectrum and feet, key): its tuning (cents), level and brightness, drawn when first played
        self.pipes: dict = {}
        self.tables: dict = {}

    def pipe(self, kind: str, feet: float, key: int) -> tuple[float, float, float]:
        k = (kind, feet, key)
        if k not in self.pipes:
            rng = np.random.default_rng([self.seed, key, int(round(feet * 12)), sum(map(ord, kind))])
            self.pipes[k] = (float(rng.normal(0.0, 0.7 + 3.0 * self.wear)), float(np.exp(rng.normal(0.0, 0.06))),
                             float(rng.normal(0.0, 0.06)))
        return self.pipes[k]

    def periods(self, kind: str, feet: float, key: int, f: float, tilt: float) -> tuple[np.ndarray, np.ndarray]:
        """A pipe's two periods, the one it settles on and the brighter one it speaks with, sharing their phases."""
        k = (kind, feet, key)
        if k not in self.tables:
            slope, even, _chiff, _speak = SPECTRA[kind]
            slope = max(0.6, slope + tilt - 0.25 * (self.brightness - 0.5))
            rng = np.random.default_rng([self.seed, key, int(round(feet * 12)), sum(map(ord, kind)), 7])
            rows = reed.tables(f, self.sr, rng, (slope, slope - BRIGHTER), even=even)
            self.tables[k] = (np.ascontiguousarray(rows[0]), np.ascontiguousarray(rows[1]))
        return self.tables[k]

    def render(self, notes, length: int, rng: np.random.Generator) -> np.ndarray:
        sr = self.sr
        out = np.zeros(length)  # (the only array as long as the song: memory is the studio's limit)
        wind = butter(2, [400.0, 3500.0], btype="bandpass", fs=sr, output="sos")
        current = ""
        for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
            words = str(note.art).split()
            for word in words:
                if word in REGISTRATIONS and word != "pedal":
                    current = word
                elif word == "default":
                    current = ""
            if note.dur <= 0.0 or note.start * sr >= length:
                continue
            ranks = REGISTRATIONS["pedal" if "pedal" in words else current]
            i0 = max(0, int(round(note.start * sr)))
            i1 = min(length, i0 + int(round((note.dur + 5.0 * RELEASE) * sr)))
            n = i1 - i0
            if n < 8:
                continue
            t = np.arange(n) / sr
            swell = touch.gain(float(np.clip(note.vel, 0.0, 1.0)), SWELL)
            off = np.where(t < note.dur, 1.0, np.exp(-(t - note.dur) / RELEASE))
            m = float(note.pitch)
            key = int(round(m))
            for feet, kind, gain in ranks:
                slope, _even, chiff, factor = SPECTRA[kind]
                f0 = _hz(m) * 8.0 / feet
                if kind == "mixture":
                    while f0 > BREAK:
                        f0 /= 2.0
                if f0 >= 0.4 * sr or f0 < 15.0:
                    continue
                cents, level, tilt = self.pipe(kind, feet, key)
                f = f0 * 2.0 ** (cents / 1200.0)
                steady, bright = self.periods(kind, feet, key, f0, tilt)
                speak = speech(f0, factor)
                rise = 1.0 - np.exp(-t / (0.35 * speak))  # the fundamental building as the air column takes over
                env = rise * off * (swell * gain * level * (f0 / 262.0) ** -0.08)  # the treble voiced a little softer
                mix = np.exp(-t / (0.5 * speak))  # the brighter period it speaks with, giving way
                reed._read_mix(steady, bright, np.full(n, f / sr), env, mix, out, i0, float(rng.random()))
                # the chiff: a breath of noise at the mouth while it speaks, around its 2nd to 4th harmonics
                c = min(n, int(0.05 * sr))
                if chiff > 0.0 and c > 8:
                    lo, hi = min(2.0 * f, 0.4 * sr), min(4.5 * f, 0.45 * sr)
                    if hi > lo * 1.1:
                        noise = sosfilt(butter(2, [lo, hi], btype="bandpass", fs=sr, output="sos"),
                                        rng.standard_normal(c))
                        out[i0:i0 + c] += noise * np.exp(-t[:c] / (0.4 * speak)) * (chiff * swell * gain)
            # the wind at the mouths, while the pallet is open
            out[i0:i1] += sosfilt(wind, rng.standard_normal(n)) * off * (swell * WIND * (1.0 + self.wear))
        return out


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A pipe organ's part: mono, dry, `length` samples, before placement and level."""
    if name != "pipeorgan":
        raise ValueError(f"no such instrument: {name}")
    return PipeOrgan(sr, make, settings or {}).render(notes, length, rng)
