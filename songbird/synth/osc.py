"""Oscillators without aliasing: the waveforms of analog synthesizers and chips.

A sawtooth or a pulse jumps once or twice a period; drawn naively, sample by
sample, its harmonics above half the sample rate fold back down as tones that
have nothing to do with the note. A polyBLEP rounds each jump over the four
samples around it with the residual of a step band-limited by a cubic
B-spline (and a polyBLAMP rounds a triangle's corners with the residual of a
band-limited ramp), which takes most of that folding away. Run at twice the
sample rate and brought down with a steep low-pass (decimate2), what is left
folds above 20 kHz and is filtered off: a sawtooth's folded partials measure
91 dB under its fundamental at 440 Hz and 80 dB at 2 kHz (at the plain rate,
54 and 45). The price is a gentle fall at the very top: 1/n within 0.6 dB to
9 kHz, 2.3 dB under at 17.6 kHz.

Every oscillator takes a frequency track (Hz, one value a sample), so glides,
vibrato and drift are simply tracks; each returns the phase it ended on so a
voice can continue.
"""

from __future__ import annotations

import functools

import numpy as np
from numba import njit
from scipy.signal import firwin, resample_poly


@njit(cache=True, nogil=True)
def _blep(t, dt):
    """Residual of a band-limited unit-2 step at phase 0, for a sample at phase t (two-point)."""
    if t < dt:
        x = t / dt
        return x + x - x * x - 1.0
    if t > 1.0 - dt:
        x = (t - 1.0) / dt
        return x * x + x + x + 1.0
    return 0.0


@njit(cache=True, nogil=True)
def _blep4(t):
    """Residual of a unit step (0 to 1) band-limited by a cubic B-spline, for a
    sample `t` samples after the step (negative: before it). Four points: its
    folding falls 24 dB an octave, where the two-point residual's falls 12.

    No kernel that calls it may be compiled with fastmath: numba would compile
    and cache this one fastmath too, for every later caller, so a synth part's
    bits would depend on what the machine rendered first (analog.py's kernels
    were, until 2026-09-29; this note also retires any cache made then)."""
    if t <= -2.0 or t >= 2.0:
        return 0.0
    if t <= -1.0:
        u = 2.0 + t
        return u * u * u * u / 24.0
    if t < 0.0:
        return 1.0 / 24.0 + (4.0 * t - 2.0 * t * t * t - 0.75 * t * t * t * t) / 6.0 + 2.75 / 6.0
    if t < 1.0:
        s = -t
        return -(1.0 / 24.0 + (4.0 * s - 2.0 * s * s * s - 0.75 * s * s * s * s) / 6.0 + 2.75 / 6.0)
    u = 2.0 - t
    return -u * u * u * u / 24.0


@njit(cache=True, nogil=True)
def _edges(p, dt):
    """The four-point residual of a unit step at phase 0 (a wrap), for a sample at phase p."""
    r = 0.0
    after = p / dt
    if after < 2.0:
        r += _blep4(after)
    before = (1.0 - p) / dt
    if before <= 2.0:
        r += _blep4(-before)
    return r


@njit(cache=True, nogil=True)
def _blamp(t, dt):
    """Residual of a band-limited unit ramp corner at phase 0, in samples, for a sample at phase t."""
    if t < dt:
        x = 1.0 - t / dt
        return x * x * x / 6.0
    if t > 1.0 - dt:
        x = (t - 1.0) / dt + 1.0
        return x * x * x / 6.0
    return 0.0


@njit(cache=True, nogil=True)
def saw(freq, sr, phase=0.0):
    """A rising sawtooth, -1..1, from a frequency track. Returns (signal, final phase)."""
    n = freq.shape[0]
    y = np.empty(n)
    for i in range(n):
        dt = min(freq[i] / sr, 0.25)
        y[i] = 2.0 * phase - 1.0 - 2.0 * _edges(phase, dt)
        phase += dt
        if phase >= 1.0:
            phase -= 1.0
    return y, phase


@njit(cache=True, nogil=True)
def pulse(freq, duty, sr, phase=0.0):
    """A pulse wave, high for `duty` of each period (a track, 0.02..0.98), zero mean. Returns (signal, phase)."""
    n = freq.shape[0]
    y = np.empty(n)
    for i in range(n):
        dt = min(freq[i] / sr, 0.25)
        d = min(max(duty[i], 0.02), 0.98)
        v = 1.0 if phase < d else -1.0
        v += 2.0 * _edges(phase, dt)
        q = phase - d
        if q < 0.0:
            q += 1.0
        v -= 2.0 * _edges(q, dt)
        y[i] = v - (2.0 * d - 1.0)
        phase += dt
        if phase >= 1.0:
            phase -= 1.0
    return y, phase


@njit(cache=True, nogil=True)
def triangle(freq, sr, phase=0.0):
    """A triangle, -1..1, peak at phase 0, its corners rounded by polyBLAMP. Returns (signal, phase)."""
    n = freq.shape[0]
    y = np.empty(n)
    for i in range(n):
        dt = min(freq[i] / sr, 0.5)
        v = 2.0 * abs(2.0 * phase - 1.0) - 1.0
        q = phase + 0.5
        if q >= 1.0:
            q -= 1.0
        v += 8.0 * dt * (_blamp(q, dt) - _blamp(phase, dt))
        y[i] = v
        phase += dt
        if phase >= 1.0:
            phase -= 1.0
    return y, phase


@njit(cache=True, nogil=True)
def stepped(freq, table, sr, phase=0.0):
    """A wave read from `table` as a staircase, one step per entry (a chip's 4-bit
    triangle), each step's jump rounded by a polyBLEP. Returns (signal, phase)."""
    n = freq.shape[0]
    steps = table.shape[0]
    y = np.empty(n)
    for i in range(n):
        dt = min(freq[i] / sr, 0.5)
        pos = phase * steps
        k = int(pos)
        if k >= steps:
            k = steps - 1
        v = table[k]
        # the step just taken (or about to be): each step is a jump of (next - this)
        sdt = dt * steps  # phase of one step, in steps
        frac = pos - k
        if sdt < 1.0:
            if frac < sdt:  # just after the jump into step k
                jump = table[k] - table[k - 1 if k > 0 else steps - 1]
                x = frac / sdt
                v += 0.5 * jump * (x + x - x * x - 1.0)
            elif frac > 1.0 - sdt:  # just before the jump into step k + 1
                jump = table[(k + 1) % steps] - table[k]
                x = (frac - 1.0) / sdt
                v += 0.5 * jump * (x * x + x + x + 1.0)
        y[i] = v
        phase += dt
        if phase >= 1.0:
            phase -= 1.0
    return y, phase


@functools.cache
def _halfband() -> np.ndarray:  # made when first needed, not on import (the studio's own worker never plays)
    return firwin(95, 21000.0, fs=88200.0, window=("kaiser", 9.0))


def decimate2(x: np.ndarray) -> np.ndarray:
    """A signal at twice the sample rate brought down to it: flat to about 18 kHz,
    everything that would fold below 20 kHz at least 85 dB down."""
    return resample_poly(x, 1, 2, window=_halfband(), axis=0)


def drift(n: int, sr: float, rng: np.random.Generator, cents: float, rate: float = 0.3) -> np.ndarray:
    """A slow random wander in cents (an analog oscillator's tuning over time), `n`
    samples long: smooth noise with most of its motion slower than `rate` Hz."""
    if n <= 0 or cents <= 0.0:
        return np.zeros(max(n, 0))
    points = max(4, int(n / sr * rate * 2.0) + 4)
    knots = rng.standard_normal(points) * cents
    t = np.linspace(0.0, points - 1.0, n)
    for a in range(0, n, 1 << 16):
        part = t[a:a + (1 << 16)]
        i = np.minimum(part.astype(np.int64), points - 2)
        f = part - i
        s = f * f * (3.0 - 2.0 * f)  # smoothstep between knots: no corners in pitch
        part[:] = knots[i] * (1.0 - s) + knots[i + 1] * s
    return t
