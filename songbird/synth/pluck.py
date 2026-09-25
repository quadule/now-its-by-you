"""Plucked string: extended Karplus-Strong.

A noise burst, shaped by pick position and plucking force, circulates in a
delay line one period long. Each trip through the loop passes a one-zero loss
filter (high harmonics die first) and a Lagrange fractional delay (exact
tuning). All feedback lags are at least one period, so a whole period of
output is computed per numpy step instead of one sample per Python step.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

LAGRANGE_ORDER = 3


def _lagrange(delay: float) -> np.ndarray:
    """FIR taps of a Lagrange interpolator delaying by `delay` samples."""
    taps = np.ones(LAGRANGE_ORDER + 1)
    for k in range(LAGRANGE_ORDER + 1):
        for j in range(LAGRANGE_ORDER + 1):
            if j != k:
                taps[k] *= (delay - j) / (k - j)
    return taps


def _phase_delay(taps: np.ndarray, omega: float) -> float:
    response = np.sum(taps * np.exp(-1j * omega * np.arange(len(taps))))
    return -np.angle(response) / omega


def loop_filter(period: float, loss: float) -> tuple[int, np.ndarray]:
    """Integer delay and FIR taps whose combined delay at the fundamental is `period`.

    `loss` is the one-zero loss coefficient: 0 keeps every harmonic, 0.5 is the
    classic two-point average.
    """
    omega = 2.0 * np.pi / period
    whole = int(np.floor(period - loss - 1.0))
    fraction = period - whole - loss
    for _ in range(4):
        taps = np.convolve([1.0 - loss, loss], _lagrange(fraction))
        fraction += (period - whole) - _phase_delay(taps, omega)
    return whole, np.convolve([1.0 - loss, loss], _lagrange(fraction))


def string_loop(excitation: np.ndarray, delay: int, taps: np.ndarray, length: int) -> np.ndarray:
    """y[n] = x[n] + sum_k taps[k] * y[n - delay - k], one period per step."""
    pad = delay + len(taps)
    y = np.zeros(pad + length)
    x = np.zeros(length)
    x[: min(len(excitation), length)] = excitation[:length]
    for start in range(0, length, delay):
        m = min(delay, length - start)
        acc = x[start : start + m].copy()
        base = pad + start - delay
        for k, tap in enumerate(taps):
            acc += tap * y[base - k : base - k + m]
        y[pad + start : pad + start + m] = acc
    return y[pad:]


def pluck(
    freq: float,
    dur: float,
    sr: int,
    rng: np.random.Generator,
    *,
    vel: float = 0.8,
    brightness: float = 0.5,
    decay: float = 3.0,
    pick: float = 0.15,
    damp: float = 0.08,
) -> np.ndarray:
    """One plucked note, `dur` seconds long plus a `damp`-second mute.

    brightness 0..1 sets the loss filter; decay is the fundamental's T60 at
    220 Hz in seconds (higher strings ring shorter); pick is the plucking
    point as a fraction of the string length.
    """
    period = sr / freq
    loss = 0.5 - 0.35 * brightness
    t60 = decay * (220.0 / freq) ** 0.4
    gain = 10.0 ** (-3.0 / (t60 * freq))
    delay, taps = loop_filter(period, loss)

    # Excitation: noise low-passed by how hard and how bright the pluck is
    # (a fingertip, not a spark), then a comb for the pick point, which
    # removes the harmonics that have a node there.
    burst = rng.uniform(-1.0, 1.0, delay + 64)
    cutoff = min(700.0 + 5000.0 * vel * brightness, 0.4 * sr)
    burst = sosfilt(butter(2, cutoff, fs=sr, output="sos"), burst)[64:]
    notch = max(1, int(round(pick * delay)))
    burst = burst - np.concatenate([np.zeros(notch), burst[:-notch]])
    burst -= burst.mean()
    burst *= vel / (np.max(np.abs(burst)) + 1e-12)

    length = int(round((dur + damp) * sr))
    y = string_loop(burst, delay, gain * taps, length)

    # The player's hand mutes the string after `dur`.
    held = min(int(round(dur * sr)), length)
    tail = length - held
    if tail > 0:
        y[held:] *= np.exp(-6.9 * np.arange(tail) / tail)
    return lfilter([1.0, -1.0], [1.0, -0.995], y)  # remove the burst's DC
