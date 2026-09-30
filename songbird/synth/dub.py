"""The dub desk: a tape echo thrown a moment at a time, and a spring tank splashed (docs/STYLES.md, "House and dub").

A dub engineer plays the mixing desk as an instrument: a fader on the echo send pushed up for a moment, so the
singer's last word, a cross-stick or the skank's chop goes round the tape again and again, each time darker and a
little more worn, fading into the gap the band left; or a snare kicked hard into the spring reverb, its crash and
boing coming back. The arranger (songbird.idioms, the style's desk) chooses the moments; songbird.sound spells
them into the score's `sound["throws"]` (each its part, its window in seconds, the echo's time, feedback and
level); the mix (mixing.Design) cuts each window from its part's channel while it is in hand and adds what comes
back to the band (the singer's to the record, beside its bus).

The echo is a Roland Space Echo's shape: a delay (a dotted eighth, say) fed back on itself, every pass through the
tape's and heads' narrowing band (a low-pass whose corner falls pass by pass) and the tape's soft saturation;
here each repeat is the window again, filtered once more, until it is 50 dB down. The spring is the electric
guitar amp's own tank (amp.spring_ir: two springs, their chirps), two of them a little apart for the two sides.
Everything is numpy and scipy (a filter per repeat, oa.convolve for the spring), over the window and its tail
only: no compiled kernel, nothing the length of the song.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from . import oa
from .iir import butter

FADE = 0.004  # s: the send's fader comes up and goes down over this much
ECHO_HP = 220.0  # Hz: the send's high-pass: a kick thrown with the cross-stick doesn't boom round the tape
ECHO_LP = 3600.0  # Hz: the first repeat's low-pass corner...
DARKER = 0.84  # ...and each next one's, this much lower (the tape and heads narrowing the band pass by pass)
TAPE = 1.6  # the tape's saturation: gentle at a channel's level, rounding the loud repeats' peaks
FLOOR = -50.0  # dB: the echo stops once a repeat would be this far down
WANDER = 0.0015  # the tape's speed: each repeat's time wanders this fraction either way (wow)
SPREAD = 0.35  # each repeat a little to one side, then the other: the desk's echo returns across the pair
SPRING_HP = 300.0  # Hz: what's sent to the spring (its transducers pass little bass; no boom)
TANKS = ((0.031, 0.037), (0.029, 0.041))  # two tanks' springs (one-way traversal times, s), left and right


def _window(source: np.ndarray, offset: int, sr: int, start: float, end: float) -> tuple[int, np.ndarray] | None:
    """The mono window [start, end) seconds of a part whose samples `source` begin at song sample `offset`, its
    ends faded as the fader moves: (its first song sample, the samples), or None where the part has none."""
    a, b = int(round(start * sr)), int(round(end * sr))
    a0, b0 = max(a, offset), min(b, offset + len(source))
    if b0 - a0 < int(0.01 * sr):
        return None
    x = source[a0 - offset: b0 - offset]
    x = x.mean(axis=1) if x.ndim == 2 else np.array(x, dtype=np.float64)
    x = np.array(x, dtype=np.float64)
    k = min(len(x) // 2, int(FADE * sr))
    if k:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, k))
        x[:k] *= ramp
        x[len(x) - k:] *= ramp[::-1]
    return a0, x


def echo(x: np.ndarray, sr: int, delay: float, feedback: float, level: float, key: int) -> np.ndarray:
    """What the tape echo returns for a window x (mono): its repeats, the first `delay` s after the window's start
    at `level`, each next one `feedback` of the last, darker, saturated; stereo, from the window's start."""
    rng = np.random.default_rng([4099, 0xEC0, int(key)])
    feedback = float(min(max(feedback, 0.0), 0.9))
    repeats = max(1, int(np.ceil(FLOOR / 20.0 / np.log10(max(feedback, 1e-3)))) + 1) if feedback > 0 else 1
    hp = butter(2, ECHO_HP, btype="highpass", fs=sr, output="sos")
    r = sosfilt(hp, x)
    pad = int(0.02 * sr)
    r = np.concatenate([r, np.zeros(pad)])
    times = np.cumsum(delay * (1.0 + WANDER * rng.uniform(-1.0, 1.0, repeats)))
    n = int(round(times[-1] * sr)) + len(r)
    out = np.zeros((n, 2))
    gain = float(level)
    for k in range(repeats):
        corner = min(0.45 * sr, ECHO_LP * DARKER ** k)
        r = sosfilt(butter(2, corner, btype="lowpass", fs=sr, output="sos"), r)
        r = np.tanh(TAPE * r) / TAPE
        at = int(round(times[k] * sr))
        side = SPREAD * (1.0 if k % 2 == 0 else -1.0)
        out[at: at + len(r), 0] += r * (gain * np.sqrt(0.5) * (1.0 + side))
        out[at: at + len(r), 1] += r * (gain * np.sqrt(0.5) * (1.0 - side))
        gain *= feedback
    return out


def spring(x: np.ndarray, sr: int, level: float) -> np.ndarray:
    """What the spring tank returns for a window x (mono) kicked into it: stereo, from the window's start."""
    from .amp import Tank, spring_ir

    x = sosfilt(butter(2, SPRING_HP, btype="highpass", fs=sr, output="sos"), x)
    sides = [oa.convolve(x, spring_ir(Tank(traversals=t, seed=j + 1), sr)) for j, t in enumerate(TANKS)]
    n = max(len(s) for s in sides)
    out = np.zeros((n, 2))
    for j, s in enumerate(sides):
        out[: len(s), j] = s * level
    return out


def returned(t: dict, source: np.ndarray, offset: int, sr: int) -> tuple[int, np.ndarray] | None:
    """One throw (sound["throws"]'s entry) from its part's samples (`source`, from song sample `offset`): (the song
    sample its return starts at, the return, stereo), or None where the part has nothing there."""
    cut = _window(source, offset, sr, float(t["start"]), float(t["end"]))
    if cut is None:
        return None
    a, x = cut
    if t["kind"] == "spring":
        return a, spring(x, sr, float(t["level"]))
    return a, echo(x, sr, float(t["time"]), float(t["feedback"]), float(t["level"]), int(t["key"]))
