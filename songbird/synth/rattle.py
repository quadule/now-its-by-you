"""What the hand percussion shares: how a stroke is levelled, how a contact
filters it, and the things in it that rattle.

Every stroke of hand percussion is levelled as the frame drum's are (drum.py):
by the loudness of its first 30 ms, not its peak, which a click or a crack
would set. Here the loudness is K-weighted (ITU-R BS.1770, as the stems are
measured), so a bright clap and a dull stomp of the same velocity sit at the
same level, and a maker's brighter shaker isn't a louder one. Struck modes
are levelled from their amplitudes (each mode's energy over the window, in
closed form), without rendering the stroke first.

A contact of duration tau (a palm, a heel, a fingertip, a jingle meeting its
pair) passes what it strikes as a half-sine force does: flat below 1/(2 tau),
falling 12 dB an octave above. A harder stroke is a shorter contact, so a
brighter one (Fletcher and Rossing, The Physics of Musical Instruments, 2nd
ed., 1998, section 2.18; Rossing, Science of Percussion Instruments, 2000).

The rattles (a shaker's beads, a tambourine's jingles, a cajon's snares) are
collisions: many small impacts whose rate and strength follow the energy put
in (Cook, "Physically informed sonic modeling (PhISM): synthesis of
percussive sounds", Computer Music Journal 21(3), 1997). Their noise comes
from a small generator of their own (xorshift), seeded from the part's
random stream, so a three-minute part needs no noise buffer and replays
exactly.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import freqz, lfilter

from .master import _k_weighting

WINDOW = 0.03  # seconds of a stroke that set its level, as the frame drum's


def vel_gain(vel) -> np.ndarray | float:
    """How much louder a harder stroke is, as the frame drum plays: 7 dB from
    vel 0.6 to 1, 16 dB from 0.3."""
    v = np.clip(vel, 0.0, 1.0)
    return v * (0.35 + 0.65 * v)


def contact(freqs, tau) -> np.ndarray:
    """What a contact lasting tau seconds passes at freqs: a half-sine force's
    envelope, flat below 1/(2 tau), -12 dB an octave above."""
    return 1.0 / (1.0 + (2.0 * np.asarray(freqs) * tau) ** 2)


@lru_cache(maxsize=4)
def _kw(sr: int):
    return tuple((np.asarray(b), np.asarray(a)) for b, a in _k_weighting(sr))


def k_power(freqs, sr: int) -> np.ndarray:
    """The K-weighting's power gain at freqs (BS.1770: +4 dB above about 2
    kHz, falling away under 60 Hz)."""
    freqs = np.atleast_1d(np.asarray(freqs, dtype=np.float64))
    g = np.ones(len(freqs))
    for b, a in _kw(sr):
        _, h = freqz(b, a, worN=np.minimum(freqs, 0.4999 * sr), fs=sr)
        g = g * np.abs(h) ** 2
    return g


def early_power(y: np.ndarray, sr: int, window: float = WINDOW) -> float:
    """K-weighted mean square of a stroke's first `window` seconds (channels summed)."""
    x = np.asarray(y[: max(1, int(window * sr))], dtype=np.float64)
    for b, a in _kw(sr):
        x = lfilter(b, a, x, axis=0)
    return float(np.sum(x**2) / max(1, int(window * sr)))


def modal_weights(freqs, t60s, sr: int, window: float = WINDOW, weight=None) -> np.ndarray:
    """What each struck mode, struck with unit amplitude (a sine starting at
    the strike, falling 60 dB in its t60), adds to the K-weighted mean square
    over the stroke's first `window` seconds. weight[k]: how much of mode k
    the listener hears (its mix). A stroke's early power is then amps**2 @
    these, as if its modes didn't beat."""
    freqs = np.asarray(freqs, dtype=np.float64)
    alpha = 6.907755 / np.asarray(t60s, dtype=np.float64)
    w = 2.0 * np.pi * freqs
    # the integral of exp(-2 a t) sin^2(w t) from 0 to T
    decay = (1.0 - np.exp(-2.0 * alpha * window)) / (2.0 * alpha)
    z = 2.0 * alpha - 2j * w
    beat = np.real((1.0 - np.exp(-z * window)) / z)
    energy = 0.5 * (decay - beat)
    return k_power(freqs, sr) * energy * (1.0 if weight is None else np.asarray(weight) ** 2) / window


def modal_power(amps: np.ndarray, freqs, t60s, sr: int, window: float = WINDOW, weight=None) -> np.ndarray:
    """Each hit's early power from its mode amplitudes amps[h, k] (see modal_weights)."""
    return np.abs(np.asarray(amps)) ** 2 @ modal_weights(freqs, t60s, sr, window, weight)


def burst(rng: np.random.Generator, tau: float, sr: int, n: int | None = None) -> np.ndarray:
    """A burst of noise falling e-fold every tau seconds, `n` samples (default 7 tau)."""
    n = int(7.0 * tau * sr) + 1 if n is None else n
    return rng.standard_normal(n) * np.exp(-np.arange(n) / (tau * sr))


def pan(position: float) -> np.ndarray:
    """Constant-power gains (left, right) for a source at position -1..1, as instruments.place() pans."""
    theta = (position + 1.0) * np.pi / 4.0
    return np.array([np.cos(theta), np.sin(theta)]) * np.sqrt(2.0)


def add(out: np.ndarray, y: np.ndarray, start: int) -> None:
    """Lay y onto out from sample `start`, clipped to out's length (either may start before 0)."""
    if start >= len(out):
        return
    lo = max(0, -start)
    hi = min(len(y), len(out) - start)
    if hi > lo:
        out[start + lo: start + hi] += y[lo:hi]


# --- the noise the rattles are made of -----------------------------------------------------


@njit(cache=True)
def _next(state):
    """xorshift64*: the next state and a uniform number in [0, 1)."""
    x = state
    x ^= x >> np.uint64(12)
    x ^= x << np.uint64(25)
    x ^= x >> np.uint64(27)
    out = (x * np.uint64(2685821657736338717)) >> np.uint64(11)
    return x, float(out) * (1.0 / 9007199254740992.0)


def seed_of(rng: np.random.Generator) -> np.uint64:
    """A nonzero xorshift state drawn from a numpy stream."""
    return np.uint64(int(rng.integers(1, 1 << 62)) | 1)
