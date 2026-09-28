"""Plucked strings: extended Karplus-Strong, in two planes, single or in pairs.

A pluck leaves the string bent into a triangle; the force it then puts on the
bridge is a rectangular wave whose duty is the plucking point, which is what
notches out the harmonics with a node there. The finger or pick softens its
edges (a fingertip is wide, a pick is sharp), and a little noise roughens it
so no two plucks are alike. That one period circulates in a delay line; each
trip passes a one-zero loss filter (high harmonics die first) and a Lagrange
fractional delay (exact tuning).

A string vibrates in two planes. Across the top it drives the body hard and
dies quickly; along the top the body hardly moves, so that plane rings on,
quieter: a loud start and a long soft tail, and because the two planes differ
by a fraction of a cent the tail beats slowly. A paired course (a cittern's
double strings) is two such strings a few cents apart, which the pick meets a
moment apart. When a note ends a finger lands on the string: the loop loses
its energy in a few hundredths of a second and the touch makes a small noise.

Open strings nobody is playing still answer the ones that are (sympathetic
resonance): see sympathetic().
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import lfilter, sosfilt

from .iir import butter

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


@lru_cache(maxsize=4096)
def _cached_loop(period: float, loss: float) -> tuple[int, tuple[float, ...]]:
    whole, taps = loop_filter(period, loss)
    return whole, tuple(taps)


@njit(cache=True)
def _loop(x, whole, taps, gain, release_at, release_gain, length, smooth):
    """One string plane, sample by sample: y[n] = x[n] + g[n] * sum_k taps[k] y[n - whole - k].
    The loop gain glides from `gain` to `release_gain` from sample `release_at`
    on (the finger landing), with a one-pole smoother `smooth`."""
    n_taps = taps.shape[0]
    pad = whole + n_taps
    y = np.zeros(pad + length)
    g = gain
    for n in range(length):
        if n >= release_at:
            g = release_gain + (g - release_gain) * smooth
        acc = 0.0
        if n < x.shape[0]:
            acc = x[n]
        base = pad + n - whole
        fb = 0.0
        for k in range(n_taps):
            fb += taps[k] * y[base - k]
        y[pad + n] = acc + g * fb
    return y[pad:]


def _excitation(period: float, pick: float, hardness: float, vel: float, rng: np.random.Generator, sr: int,
                roughness: float = 0.3, cutoff_hz: float | None = None) -> np.ndarray:
    """One period of bridge force from a pluck at `pick` (fraction of the string
    from the bridge), softened by the plucker's `hardness` (0 a fleshy
    fingertip, 1 a sharp pick) and by how hard it was played; or, where the
    plucker is known better (a metal fingerpick lets a steel string go at
    once), softened above `cutoff_hz` itself."""
    n = max(4, int(round(period)))
    k = min(n - 1, max(1, int(round(pick * n))))
    shape = np.full(n, -k / n)
    shape[:k] += 1.0  # a rectangular wave of duty `pick`, zero mean
    noise = rng.uniform(-1.0, 1.0, n)
    x = shape + roughness * (noise - noise.mean()) * np.sqrt(np.mean(shape**2))
    # Soften it circularly (the period repeats), so no transient enters the loop:
    # a fingertip rounds the corner off above a kilohertz or two, a pick above six.
    spectrum = np.fft.rfft(x)
    harmonic = np.arange(len(spectrum))
    if cutoff_hz is None:
        cutoff_hz = 1200.0 + 9000.0 * hardness**1.5 * (0.6 + 0.4 * vel)
    cutoff = max(1.5, cutoff_hz * period / sr)  # in harmonics
    spectrum /= np.sqrt(1.0 + (harmonic / cutoff) ** 4)
    x = np.fft.irfft(spectrum, n)
    # scaled by its RMS, not its peak: a pluck near the bridge is a narrow, spiky
    # pulse, and peak scaling would leave it a third as loud as one in the middle
    return x * 0.5 * vel / (np.sqrt(np.mean(x**2)) + 1e-12)


def _plane(freq: float, excitation: np.ndarray, sr: int, loss: float, t60: float, held: int, length: int,
           release_t60: float) -> np.ndarray:
    whole, taps = _cached_loop(round(sr / freq, 6), round(loss, 4))
    gain = 10.0 ** (-3.0 / (t60 * freq))
    release_gain = 10.0 ** (-3.0 / (release_t60 * freq))
    smooth = float(np.exp(-1.0 / (0.004 * sr)))
    return _loop(excitation, whole, np.array(taps), gain, held, release_gain, length, smooth)


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
    hardness: float = 0.5,
    planes: float = 0.3,
    course: float = 0.0,
    spread: float = 0.0,
    touch: float = 0.0,
    mute: bool = False,
) -> np.ndarray:
    """One plucked note: the bridge force for `dur` seconds, then a `damp`-second stop.

    brightness 0..1 sets the loop's loss (how fast the upper harmonics die);
    decay is the loud plane's T60 at 220 Hz in seconds (higher strings ring
    shorter); pick is the plucking point as a fraction of the string;
    hardness 0..1 is fingertip to pick. planes is how much of the pluck goes
    into the quiet, long-ringing plane (0..1). course is the detune in cents
    of a paired string (0: a single string) and spread the seconds between the
    pick meeting its two strings. touch is the level of the finger's noise
    when it stops the string; mute stops it almost at once (a muted strum).
    """
    period = sr / freq
    loss = 0.5 - 0.35 * brightness
    t60 = decay * (220.0 / freq) ** 0.4
    length = int(round((dur + damp) * sr))
    held = min(int(round(dur * sr)), length)
    release_t60 = 0.08
    if mute:
        held = min(int(0.006 * sr), length)
        release_t60 = 0.05
    strings = [(0.0, 0, vel)] if course <= 0.0 else [
        (-course / 2.0, 0, vel * 0.72),
        (course / 2.0, int(round(spread * sr)), vel * 0.72 * rng.uniform(0.75, 1.0)),
    ]
    y = np.zeros(length)
    for cents, lag, v in strings:
        f = freq * 2.0 ** (cents / 1200.0)
        x = _excitation(sr / f, pick * rng.uniform(0.9, 1.1), hardness, v, rng, sr)
        split = rng.uniform(0.2, 0.8)  # the second plane sits a fraction of a cent away
        across = _plane(f, x, sr, loss, 0.8 * t60, held - lag, length - lag, release_t60)
        along = _plane(f * 2.0 ** (split / 1200.0), x * planes, sr, loss, 2.0 * t60, held - lag, length - lag,
                       release_t60)
        y[lag:] += across + along
    y += _attack(sr, hardness, vel, length, rng)
    if mute:  # a chop: the pick's scrape across strings the hand has already deadened
        n = min(length, int(0.02 * sr))
        scrape = sosfilt(butter(2, [700.0, 5000.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n + 64))
        y[:n] += scrape[64:] * np.exp(-np.arange(n) / (0.004 * sr)) * 0.25 * vel * (0.4 + 0.6 * hardness)
    if touch > 0.0 and held < length and not mute:
        y += _touch(sr, held, length, freq, touch * vel, rng)
    tail = min(length, int(0.004 * sr))
    y[length - tail:] *= np.linspace(1.0, 0.0, tail)
    return lfilter([1.0, -1.0], [1.0, -0.995], y)  # remove the pluck's DC


def _attack(sr: int, hardness: float, vel: float, length: int, rng: np.random.Generator) -> np.ndarray:
    """The pick or nail leaving the string: a click of a few milliseconds, bright
    and longer for a pick, which scrapes as it goes; a fingertip barely clicks."""
    n = min(length, int((0.002 + 0.006 * hardness) * sr))
    burst = np.zeros(length)
    if n < 8:
        return burst
    noise = rng.standard_normal(n + 64)
    noise = sosfilt(butter(2, 1500.0 + 4000.0 * hardness, btype="highpass", fs=sr, output="sos"), noise)[64:]
    burst[:n] = noise * np.exp(-np.arange(n) / ((0.0005 + 0.0015 * hardness) * sr)) * 0.1 * hardness**1.5 * vel
    return burst


def _touch(sr: int, at: int, length: int, freq: float, level: float, rng: np.random.Generator) -> np.ndarray:
    """A finger landing on a sounding string: a soft, low buzz of a few hundredths of a second."""
    n = min(length - at, int(0.03 * sr))
    y = np.zeros(length)
    if n < 8:
        return y
    noise = rng.standard_normal(n + 64)
    noise = sosfilt(butter(2, [max(80.0, 0.8 * freq), min(3000.0, 6.0 * freq)], btype="bandpass", fs=sr,
                           output="sos"), noise)[64:]
    env = np.sin(np.pi * np.arange(n) / n) ** 2
    y[at : at + n] = noise * env * 0.05 * level
    return y


@njit(cache=True)
def _bank(x, wholes, taps, gains, coupling):
    """Undamped open strings driven by the bridge: each a loop fed a little of x."""
    n_strings, n_taps = taps.shape
    length = x.shape[0]
    pad = 0
    for s in range(n_strings):
        pad = max(pad, wholes[s] + n_taps)
    lines = np.zeros((n_strings, pad + length))
    out = np.zeros(length)
    for n in range(length):
        drive = coupling * x[n]
        total = 0.0
        for s in range(n_strings):
            base = pad + n - wholes[s]
            fb = 0.0
            for k in range(n_taps):
                fb += taps[s, k] * lines[s, base - k]
            v = drive + gains[s] * fb
            lines[s, pad + n] = v
            total += v
        out[n] = total
    return out


def sympathetic(force: np.ndarray, sr: int, pitches, coupling: float = 0.0015, decay: float = 3.0,
                brightness: float = 0.3) -> np.ndarray:
    """What an instrument's open strings add when the rest of it plays: each
    string is a loop the bridge force drives a little; it builds up only where
    the playing shares its harmonics. Returns the ring alone, to add to force."""
    if len(pitches) == 0 or not len(force):
        return np.zeros_like(force)
    loss = 0.5 - 0.35 * brightness
    wholes, rows, gains = [], [], []
    for p in pitches:
        freq = 440.0 * 2.0 ** ((p - 69.0) / 12.0)
        whole, taps = _cached_loop(round(sr / freq, 6), round(loss, 4))
        wholes.append(whole)
        rows.append(taps)
        gains.append(10.0 ** (-3.0 / (decay * (220.0 / freq) ** 0.4 * freq)))
    return _bank(np.ascontiguousarray(force, dtype=np.float64), np.array(wholes, dtype=np.int64),
                 np.array(rows, dtype=np.float64), np.array(gains, dtype=np.float64), float(coupling))
