"""Shared by the banjo's and the mandolin's tests: a part rendered as the registry would, and the
measures a note is judged by (its pitch, its decay, its brightness)."""

from __future__ import annotations

import numpy as np
from _levels_b import SETTINGS, streams

SR = 44100


def render(module, name: str, notes, seconds: float, *, maker: int = 0, seed: int = 0, **settings) -> np.ndarray:
    """The dry stereo part, as module.render gives it the registry's streams."""
    rng, make = streams(name, seed, maker)
    return module.render(name, tuple(notes), SR, int(seconds * SR), rng, make, {**SETTINGS, "maker": maker, **settings})


def mono(y: np.ndarray) -> np.ndarray:
    return y.mean(axis=1) if y.ndim == 2 else y


def peak_hz(y: np.ndarray, guess: float, t0: float, t1: float, width: float = 0.03) -> float:
    """The strongest peak within `width` of guess, by zero-padded FFT and parabolic interpolation."""
    seg = mono(y)[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    n = 16 * SR
    spec = np.abs(np.fft.rfft(seg, n))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    band = (freqs > guess * (1 - width)) & (freqs < guess * (1 + width))
    i = np.flatnonzero(band)[np.argmax(spec[band])]
    a, b, c = np.log(spec[i - 1: i + 2] + 1e-30)
    return freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])


def cents(y: np.ndarray, midi: float, t0: float, t1: float, harmonic: int = 1) -> float:
    """How far the note's `harmonic` sits from where it should, in cents."""
    f = 440.0 * 2 ** ((midi - 69) / 12) * harmonic
    return 1200 * np.log2(peak_hz(y, f, t0, t1) / f)


def env_db(y: np.ndarray, hop: float = 0.01) -> np.ndarray:
    h = int(hop * SR)
    x = mono(y)
    n = len(x) // h
    return 20 * np.log10(np.sqrt(np.mean(x[: n * h].reshape(n, h) ** 2, axis=1)) + 1e-12)


def t60(y: np.ndarray, start: float = 0.0, lo: float = 5.0, hi: float = 35.0) -> float:
    """Seconds to fall 60 dB, from the slope of the envelope between lo and hi dB under its peak."""
    env = env_db(y[int(start * SR):])
    k = int(np.argmax(env))
    after = env[k:]
    i0 = k + int(np.argmax(after < env[k] - lo))
    below = np.flatnonzero(after < env[k] - hi)
    i1 = k + (int(below[0]) if len(below) else len(after) - 1)
    return -60.0 / np.polyfit(np.arange(i0, i1) * 0.01, env[i0:i1], 1)[0]


def spectrum(y: np.ndarray, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
    seg = mono(y)[int(t0 * SR): int(t1 * SR)]
    seg = seg * np.hanning(len(seg))
    return np.fft.rfftfreq(len(seg), 1 / SR), np.abs(np.fft.rfft(seg)) ** 2


def centroid(y: np.ndarray, t0: float, t1: float) -> float:
    freqs, power = spectrum(y, t0, t1)
    return float(np.sum(freqs * power) / np.sum(power))


def share_db(y: np.ndarray, lo: float, hi: float, t0: float, t1: float) -> float:
    """dB of the energy between lo and hi Hz against the whole."""
    freqs, power = spectrum(y, t0, t1)
    return float(10 * np.log10(np.sum(power[(freqs >= lo) & (freqs < hi)]) / np.sum(power) + 1e-30))


def early_db(y: np.ndarray, t0: float, span: float = 0.1) -> float:
    x = mono(y)[int(t0 * SR): int((t0 + span) * SR)]
    return float(20 * np.log10(np.sqrt(np.mean(x**2)) + 1e-12))
