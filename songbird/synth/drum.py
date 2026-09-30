"""Struck skin: a frame drum (bodhran-like), by modal synthesis.

A circular membrane rings in modes at the zeros of Bessel functions: the
fundamental (0,1), then (1,1) at 1.59 times it, (2,1) at 2.14, (0,2) at 2.30
and so on, ever more crowded, nothing like a harmonic series, which is why a drum has a pitch
you can feel but not quite sing. Where the stick lands decides which modes
speak: a stroke near the middle excites mostly the round modes (a boom),
one near the rim the ones with nodal diameters (a drier, higher knock). The
stick is in contact for a millisecond or so, which filters off the highest
modes, less so for a harder hit, and the knock of wood on skin is a click of
its own. A hard hit stretches the skin: the pitch starts high and falls in a
few hundredths of a second. The player's other hand behind the skin raises
the pitch and damps the ring (the tipped and muted strokes).

Strokes (Note.art): "bass" open, near the centre; "tip" lighter, off-centre,
hand on the skin; "mute" hand pressed, short; "rim" the stick on the frame's
edge, mostly click.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import sosfilt
from scipy.special import jn_zeros, jv

from .iir import butter

STROKE_GAIN = {"bass": 1.0, "tip": 0.55, "mute": 0.5, "rim": 0.45}


def _modes(top: float = 40.0) -> tuple[tuple[int, int, float], ...]:
    """(m, n, Bessel zero j_mn) of every mode of an ideal membrane up to j = top
    (about sixteen times the fundamental): the first few are (0,1) 2.405,
    (1,1) 3.832, (2,1) 5.136, (0,2) 5.520."""
    modes = []
    for m in range(0, 40):
        for n, j in enumerate(jn_zeros(m, 20), start=1):
            if j < top:
                modes.append((m, n, float(j)))
    return tuple(sorted(modes, key=lambda x: x[2]))


MODES = _modes()
_M = np.array([m for m, _, _ in MODES])
_J = np.array([j for _, _, j in MODES], dtype=float)
_EDGE = np.array([max(abs(jv(m + 1, j)), 1e-3) for m, _, j in MODES])  # each mode's normalization, as it was made
_TWO = np.full(len(MODES), 2.0)
_SEVEN_TENTHS = np.full(len(MODES), 0.7)

STROKES = {
    # radius (0 centre, 1 rim), pitch factor (the hand behind the skin), ring (seconds, the fundamental's T60),
    # contact (ms), click level
    "bass": (0.22, 1.00, 0.35, 1.6, 0.25),
    "tip": (0.72, 1.12, 0.22, 0.9, 0.45),
    "mute": (0.45, 1.25, 0.08, 1.1, 0.35),
    "rim": (0.95, 1.15, 0.05, 0.5, 1.0),
}


@njit(cache=True, nogil=True)
def _ring(freqs, amps, t60s, glide, glide_time, n, sr):
    """Sum of decaying modes; the two lowest start `glide` higher and fall back
    over `glide_time` seconds (the skin's tension after a hard hit)."""
    out = np.zeros(n)
    for k in range(freqs.shape[0]):
        f = freqs[k]
        if f >= 0.45 * sr:
            continue
        decay = np.exp(-6.9078 / (t60s[k] * sr))
        a = amps[k]
        if k < 2 and glide > 0.0:
            phase = 0.0
            g = 1.0
            fall = np.exp(-1.0 / (glide_time * sr))
            bend = glide
            for i in range(n):
                phase += 2.0 * np.pi * f * (1.0 + bend) / sr
                bend *= fall
                out[i] += a * g * np.sin(phase)
                g *= decay
                if g < 1e-5:
                    break
        else:
            w = 2.0 * np.pi * f / sr
            c = 2.0 * decay * np.cos(w)
            d = decay * decay
            y1 = a * decay * np.sin(w)
            y2 = 0.0
            out[0] += y2
            if n > 1:
                out[1] += y1
            for i in range(2, n):
                y0 = c * y1 - d * y2
                out[i] += y0
                y2 = y1
                y1 = y0
                if i % 256 == 0 and abs(y0) < 1e-6 * abs(a) and abs(y1) < 1e-6 * abs(a):
                    break
    return out


def hit(stroke: str, vel: float, sr: int, rng: np.random.Generator, *, pitch: float = 82.0,
        brightness: float = 0.5, wear: float = 0.0) -> np.ndarray:
    """One stroke on the drum. pitch is the open skin's fundamental in Hz."""
    radius, lift, ring, contact_ms, click = STROKES.get(stroke, STROKES["tip"])
    radius = float(np.clip(radius + rng.normal(0.0, 0.06), 0.0, 0.98))
    theta = rng.uniform(0.0, np.pi)
    f0 = pitch * lift * (1.0 - 0.06 * wear) * np.exp(rng.normal(0.0, 0.01))  # a worn skin sits lower
    contact = contact_ms * 1e-3 * (1.4 - 0.6 * vel) * (1.3 - 0.6 * brightness)  # harder: shorter, brighter
    # every mode at once, each value by the same operations as one at a time: the powers through np.power with an
    # array of exponents (the C library's pow, as a scalar ** uses; an array ** 2 would square instead), the
    # modes' random spread drawn together (the same draws in the same order)
    m, j = _M, _J
    freqs = f0 * j / MODES[0][2]
    shape = jv(m, j * radius) / _EDGE
    radiate = np.where(m == 0, 1.0, 0.45)  # modes with nodal diameters radiate worse
    spectrum = 1.0 / (1.0 + np.power(2.0 * freqs * contact, _TWO))  # a half-sine contact's envelope: -12 dB/octave past 1/2τ
    amps = shape * np.cos(m * theta) * radiate * spectrum * rng.uniform(0.8, 1.2, len(MODES))
    t60s = ring * np.power(f0 / freqs, _SEVEN_TENTHS) * (1.0 + 0.3 * wear)
    length = int((max(t60s) + 0.05) * sr)
    y = _ring(freqs, amps, t60s, 0.06 * vel ** 2, 0.03, length, float(sr))
    level = np.max(np.abs(y[: int(0.01 * sr)])) + 1e-9
    # above the modes listed the skin's modes crowd into a band of noise, the slap, gone in a few hundredths
    n = min(length, int(0.06 * sr))
    slap = sosfilt(butter(2, [16.0 * f0, min(5000.0, 0.45 * sr)], btype="bandpass", fs=sr, output="sos"),
                   rng.standard_normal(n + 64))[64:]
    y[:n] += slap * np.exp(-np.arange(n) / (ring * 0.035 * sr)) * (0.08 + 0.12 * brightness) * radius * level
    # the knock of the stick itself: a millisecond or two of bright noise
    n = int(0.004 * sr)
    burst = sosfilt(butter(2, [900.0, 6000.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n + 64))[64:]
    y[:n] += burst * np.exp(-np.arange(n) / (0.0008 * sr)) * click * (0.3 + 0.5 * brightness) * level
    # scaled by the loudness of its first 30 ms, not its peak (a click would set the level), and a tipped
    # stroke well under the open boom, as a player plays them
    body = np.sqrt(np.mean(y[: int(0.03 * sr)] ** 2)) + 1e-12
    return y * vel * 0.25 / body * (0.35 + 0.65 * vel) * STROKE_GAIN.get(stroke, 0.6)


def play(notes, sr: int, length: int, rng: np.random.Generator, *, pitch: float = 82.0, brightness: float = 0.5,
         wear: float = 0.0) -> np.ndarray:
    """A drum part: every stroke laid onto one track, `length` samples long.

    A frame drum has no back: at its lowest modes the air just sloshes round
    the rim from one face to the other, so it radiates them as a dipole, 12 dB
    an octave weaker below about 1.3 times its fundamental than a closed drum
    would. Felt more than heard, as a bodhran's boom is."""
    out = np.zeros(length)
    for note in notes:
        y = hit(note.art or "tip", note.vel, sr, rng, pitch=pitch, brightness=brightness, wear=wear)
        i = int(round(note.start * sr))
        j = min(length, i + len(y))
        if i < length:
            out[i:j] += y[: j - i]
    return sosfilt(butter(2, 1.3 * pitch, btype="highpass", fs=sr, output="sos"), out)
