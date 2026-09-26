"""Struck skin: a frame drum (bodhran-like), by modal synthesis.

A circular membrane rings in modes at the zeros of Bessel functions: the
fundamental (0,1), then (1,1) at 1.59 times it, (2,1) at 2.14, (0,2) at 2.30
and so on, nothing like a harmonic series, which is why a drum has a pitch
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
from scipy.signal import butter, sosfilt
from scipy.special import jv

# (m, n, Bessel zero j_mn) of the first twenty modes of an ideal membrane.
MODES = (
    (0, 1, 2.4048), (1, 1, 3.8317), (2, 1, 5.1356), (0, 2, 5.5201), (3, 1, 6.3802), (1, 2, 7.0156),
    (4, 1, 7.5883), (2, 2, 8.4172), (0, 3, 8.6537), (5, 1, 8.7715), (3, 2, 9.7610), (6, 1, 9.9361),
    (1, 3, 10.1735), (4, 2, 11.0647), (7, 1, 11.0864), (2, 3, 11.6198), (0, 4, 11.7915), (8, 1, 12.2251),
    (5, 2, 12.3386), (3, 3, 13.0152),
)

STROKES = {
    # radius (0 centre, 1 rim), pitch factor (the hand behind the skin), ring (seconds, the fundamental's T60),
    # contact (ms), click level
    "bass": (0.22, 1.00, 0.55, 1.6, 0.25),
    "tip": (0.72, 1.12, 0.22, 0.9, 0.45),
    "mute": (0.45, 1.25, 0.08, 1.1, 0.35),
    "rim": (0.95, 1.15, 0.05, 0.5, 1.0),
}


@njit(cache=True)
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
    freqs, amps, t60s = [], [], []
    for m, n, j in MODES:
        f = f0 * j / MODES[0][2]
        shape = jv(m, j * radius) / max(abs(jv(m + 1, j)), 1e-3)
        radiate = 1.0 if m == 0 else 0.45  # modes with nodal diameters radiate worse
        spectrum = 1.0 / (1.0 + (2.0 * f * contact) ** 2)  # a half-sine contact's envelope: -12 dB/octave past 1/2τ
        freqs.append(f)
        amps.append(shape * np.cos(m * theta) * radiate * spectrum * rng.uniform(0.8, 1.2))
        t60s.append(ring * (f0 / f) ** 0.7 * (1.0 + 0.3 * wear))
    length = int((max(t60s) + 0.05) * sr)
    y = _ring(np.array(freqs), np.array(amps), np.array(t60s), 0.06 * vel ** 2, 0.03, length, float(sr))
    # the knock of the stick itself: a millisecond or two of bright noise
    n = int(0.004 * sr)
    burst = sosfilt(butter(2, [900.0, 6000.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n + 64))[64:]
    y[:n] += burst * np.exp(-np.arange(n) / (0.0008 * sr)) * click * (0.6 + 1.0 * brightness) * np.max(np.abs(y[:n]) + 1e-9)
    peak = np.max(np.abs(y)) + 1e-12
    return y * vel / peak * (0.35 + 0.65 * vel)


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
