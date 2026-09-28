"""Mastering and export: loudness (ITU-R BS.1770-4), a true-peak limiter, dither, FLAC.

The mix arrives already glued and tilted (mixing.py); mastering only brings
it to -14 LUFS integrated without letting it swing past -1 dBTP, measured
with 4x oversampling as BS.1770-4 annex 2 asks, since a player's
reconstruction filter (or a lossy decoder) swings between the samples. A
soft clip rounds off the sharpest peaks (the top 2 dB, a fraction of a
percent of samples), then a limiter that looks ahead 5 ms and lets go over
about 80 ms catches the rest, so the song is never squashed: its loudness
range stays that of the mix.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache, partial
from pathlib import Path

import numpy as np
import soundfile as sf
from numpy.lib.stride_tricks import sliding_window_view
from numba import njit
from scipy.ndimage import minimum_filter1d
from scipy.signal import firwin

from . import threads
from .fx import _biquads

TARGET_LUFS = -14.0
CEILING_DB = -1.0  # dBTP
MARGIN_DB = 0.05  # the limiter aims this far under the ceiling, for dither and rounding


def _k_weighting(sr: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """The BS.1770 pre-filter (high shelf, then high pass) at any sample rate."""
    f0, gain_db, q = 1681.974450955533, 3.999843853973347, 0.7071752369554196
    k = np.tan(np.pi * f0 / sr)
    vh = 10.0 ** (gain_db / 20.0)
    vb = vh**0.4996667741545416
    a0 = 1.0 + k / q + k * k
    shelf = (
        np.array([(vh + vb * k / q + k * k) / a0, 2.0 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0]),
        np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0]),
    )
    f0, q = 38.13547087602444, 0.5003270373238773
    k = np.tan(np.pi * f0 / sr)
    a0 = 1.0 + k / q + k * k
    highpass = (np.array([1.0, -2.0, 1.0]), np.array([1.0, 2.0 * (k * k - 1.0) / a0, (1.0 - k / q + k * k) / a0]))
    return [shelf, highpass]


@njit(cache=True, nogil=True)
def _hop_power(y: np.ndarray, hop: int) -> np.ndarray:
    """Power summed over channels, averaged over each hop."""
    n, chans = y.shape
    k = n // hop
    out = np.zeros(k)
    for j in range(k):
        s = 0.0
        for i in range(j * hop, (j + 1) * hop):
            for c in range(chans):
                s += y[i, c] * y[i, c]
        out[j] = s / hop
    return out


def _powers(x: np.ndarray, sr: int, window: float, step: float = 0.1) -> np.ndarray:
    """K-weighted power, summed over channels, of every `window`-second block starting each `step`."""
    sos = np.array([np.concatenate([b, a]) for b, a in _k_weighting(sr)])
    hops = _hop_power(_biquads(np.ascontiguousarray(x.reshape(len(x), -1), dtype=np.float64), sos), int(step * sr))
    per = int(round(window / step))
    if len(hops) < per:
        return np.zeros(0)
    c = np.concatenate([[0.0], np.cumsum(hops)])
    return (c[per:] - c[:-per]) / per


def loudness(x: np.ndarray, sr: int) -> float:
    """Integrated loudness in LUFS of a (samples, channels) signal."""
    energy = _powers(x, sr, 0.4)
    if not len(energy):
        return -np.inf
    with np.errstate(divide="ignore"):
        levels = -0.691 + 10.0 * np.log10(energy)
    gated = energy[levels > -70.0]
    if not len(gated):
        return -np.inf
    relative = -0.691 + 10.0 * np.log10(gated.mean()) - 10.0
    gated = energy[(levels > -70.0) & (levels > relative)]
    return float(-0.691 + 10.0 * np.log10(gated.mean()))


def short_term(x: np.ndarray, sr: int, window: float = 3.0, step: float = 0.1) -> np.ndarray:
    """Loudness in LUFS of each `window`-second stretch, every `step` seconds
    (EBU Tech 3341: 3 s is short-term loudness, 0.4 s momentary)."""
    energy = _powers(x, sr, window, step)
    if not len(energy):
        return np.full(1, -np.inf)
    with np.errstate(divide="ignore"):
        return -0.691 + 10.0 * np.log10(energy)


def loudness_range(x: np.ndarray, sr: int) -> float:
    """Loudness range in LU (EBU Tech 3342): the spread between the 10th and
    95th percentiles of short-term loudness, gated at -70 LUFS and at 20 LU
    below the level of what passed."""
    levels = short_term(x, sr)
    levels = levels[levels > -70.0]
    if not len(levels):
        return 0.0
    relative = 10.0 * np.log10(np.mean(10.0 ** (levels / 10.0))) - 20.0
    levels = levels[levels > relative]
    return float(np.percentile(levels, 95) - np.percentile(levels, 10))


OVERSAMPLE = 4  # BS.1770-4 annex 2
REACH = 32  # interpolator taps on either side of a point


@lru_cache(maxsize=None)
def _interpolator() -> np.ndarray:
    """Taps that interpolate the points a quarter, half and three quarters of
    the way from each sample to the next: a windowed sinc flat to 0.1 dB up to
    19 kHz at 44.1 kHz. Row p, column REACH + k weighs sample n - k for the
    point n + p/4."""
    h = OVERSAMPLE * firwin(2 * OVERSAMPLE * REACH + 1, 0.98 / OVERSAMPLE, window=("kaiser", 8.0))
    centre = OVERSAMPLE * REACH
    taps = np.zeros((OVERSAMPLE, 2 * REACH + 1))
    for p in range(OVERSAMPLE):
        for k in range(-REACH, REACH + 1):
            i = OVERSAMPLE * k + p + centre
            if 0 <= i < len(h):
                taps[p, k + REACH] = h[i]
    return taps


def true_peak_envelope(x: np.ndarray, floor: float = 0.0) -> np.ndarray:
    """For each sample, the largest magnitude the signal swings to, over every
    channel, at it or between it and its neighbours, oversampled 4x: what a
    reconstruction filter (a DAC, a lossy decoder) will actually reach.
    Samples quieter than `floor` whose neighbours are too are left at their
    own magnitude: music never swings 6 dB between samples, so with a floor
    6 dB under what matters the envelope is exact where it counts."""
    y = x.reshape(len(x), -1)
    env = np.abs(y).max(axis=1)
    near = env >= floor
    near[:-1] |= near[1:]  # the stretch on either side of each loud sample
    near[-1] = False
    loud = np.flatnonzero(near)
    if not len(loud):
        return env
    taps = _interpolator()
    padded = np.pad(y, ((REACH, REACH), (0, 0)))
    between = np.zeros(len(loud))
    # sample n - k for k = -REACH..REACH sits at padded[n + REACH - k]: the window around n is a run of padded
    # read backwards, a row of a sliding view over it reversed (copied out as the rows are picked)
    last = len(padded) - 1
    runs = [sliding_window_view(padded[::-1, ch], 2 * REACH + 1) for ch in range(y.shape[1])]

    def swing(start: int) -> None:
        part = loud[start : start + (1 << 16)]
        rows = last - (part + 2 * REACH)
        for ch in range(y.shape[1]):
            points = runs[ch][rows] @ taps.T  # n, n + 1/4, n + 1/2, n + 3/4
            between[start : start + len(part)] = np.maximum(between[start : start + len(part)], np.abs(points).max(axis=1))

    # a bounded amount of memory at a time, each stretch its own (so they are made at once, threads.in_order)
    for _ in threads.in_order([(start, partial(swing, start)) for start in range(0, len(loud), 1 << 16)]):
        pass
    env[loud] = np.maximum(env[loud], between)
    env[loud + 1] = np.maximum(env[loud + 1], between)
    return env


def true_peak(x: np.ndarray) -> float:
    """True peak in dBTP, measured with 4x oversampling."""
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    return float(20.0 * np.log10(np.max(true_peak_envelope(x, 0.5 * peak), initial=0.0) + 1e-12))


@njit(cache=True, nogil=True)
def _recover(held: np.ndarray, coef: float) -> np.ndarray:
    """Follow a gain down at once and back up toward 1 exponentially."""
    out = np.empty_like(held)
    g = 1.0
    for i in range(len(held)):
        g = 1.0 - (1.0 - g) * coef
        if held[i] < g:
            g = held[i]
        out[i] = g
    return out


def limit(x: np.ndarray, sr: int, ceiling_db: float = CEILING_DB, lookahead: float = 0.005, release: float = 0.08,
          envelope: np.ndarray | None = None) -> np.ndarray:
    """A look-ahead limiter that keeps the true peak under the ceiling.

    Each sample's need (the gain that brings its true-peak envelope to the
    ceiling) is held over the `lookahead` seconds before it, recovered from
    exponentially over `release`, then averaged over the look-ahead. Every
    value averaged at a peak was held at or under that peak's need, so the
    peak comes out at the ceiling, reached by a smooth 5 ms fade. envelope:
    x's true-peak envelope, if already known.
    """
    ceiling = 10.0 ** (ceiling_db / 20.0)
    env = true_peak_envelope(x, 0.5 * ceiling) if envelope is None else envelope
    need = np.minimum(1.0, ceiling / np.maximum(env, 1e-12))
    if need.min() >= 1.0:
        return x
    ahead = max(1, int(lookahead * sr))
    held = minimum_filter1d(need, size=ahead + 1, origin=-((ahead + 1) // 2))  # min of need[n .. n + ahead]
    recovered = _recover(held, float(np.exp(-1.0 / (release * sr))))
    c = np.concatenate([[0.0], np.cumsum(np.concatenate([np.full(ahead, recovered[0]), recovered]))])
    gain = (c[ahead + 1 :] - c[: -ahead - 1]) / (ahead + 1)  # mean of recovered[n - ahead .. n]
    gain = np.minimum(gain, need)  # never above it, not even by rounding
    return x * gain[:, None]


CLIP = (2.0, 1.0)  # the soft clip's knee starts this many dB under the ceiling and flattens this many over it


def clip(x: np.ndarray, ceiling_db: float, below: float = CLIP[0], above: float = CLIP[1]) -> np.ndarray:
    """Round off only the sharpest peaks: samples within `below` dB of the
    ceiling bend smoothly toward `above` dB past it (a tanh knee); everything
    quieter passes untouched. On H it touches under 0.2% of samples, and
    spares the limiter the few peaks that would have made it duck the whole
    band for a moment."""
    a = 10.0 ** ((ceiling_db - below) / 20.0)
    b = 10.0 ** ((ceiling_db + above) / 20.0)
    out = x.copy()
    mag = np.abs(x)
    over = mag > a
    out[over] = np.sign(x[over]) * (a + (b - a) * np.tanh((mag[over] - a) / (b - a)))
    return out


def master(x: np.ndarray, sr: int, target: float = TARGET_LUFS, ceiling_db: float = CEILING_DB,
           taps: dict | None = None) -> np.ndarray:
    """Bring a mix to the target loudness without its true peak passing the
    ceiling: gain, the soft clip, then the limiter, the gain found again until
    the loudness is on target.
    taps: a dict to receive the gain applied ("gain_db") and what the clip and
    limiter took together ("limited_db", per sample)."""
    level = loudness(x, sr)
    if not np.isfinite(level):
        return x
    ceiling = ceiling_db - MARGIN_DB
    gain = 10.0 ** ((target - level) / 20.0)
    y = x * gain
    for _ in range(8):
        y = limit(clip(x * gain, ceiling), sr, ceiling)
        level = loudness(y, sr)
        if abs(level - target) < 0.05:
            break
        gain *= 10.0 ** ((target - level) / 20.0)
    over = true_peak(y) - ceiling
    if over > 0:  # the limiter's own gain changes can swing a little past: once more, lower
        y = limit(y, sr, ceiling - over)
    if taps is not None:
        taps["gain_db"] = 20.0 * np.log10(gain)
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.abs(y).max(axis=1) / (np.abs(x).max(axis=1) * gain)
        taps["limited_db"] = 20.0 * np.log10(np.where(np.isfinite(ratio) & (ratio > 0), np.minimum(ratio, 1.0), 1.0))
    return y


def to_pcm16(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """Quantize to 16-bit with seeded TPDF dither."""
    rng = np.random.default_rng(seed)
    dither = rng.uniform(-0.5, 0.5, x.shape) + rng.uniform(-0.5, 0.5, x.shape)
    return np.clip(np.round(x * 32767.0 + dither), -32768, 32767).astype("<i2")


def pcm_sha256(pcm: np.ndarray) -> str:
    """The identity of a rendition: a hash of its decoded samples, not of the file."""
    return hashlib.sha256(np.ascontiguousarray(pcm, dtype="<i2").tobytes()).hexdigest()


def write_flac(path: str | Path, pcm: np.ndarray, sr: int, tags: dict | None = None) -> None:
    """16-bit FLAC; with tags (title, artist, date, comment, album...), as Vorbis comments players show.
    Tags never touch the samples, so a rendition's id (their hash) is the same with or without them."""
    if not tags:
        sf.write(str(path), pcm, sr, format="FLAC", subtype="PCM_16")
        return
    channels = pcm.shape[1] if pcm.ndim > 1 else 1
    with sf.SoundFile(str(path), "w", samplerate=sr, channels=channels, format="FLAC", subtype="PCM_16") as f:
        for key, value in tags.items():
            if value:
                setattr(f, key, str(value))
        f.write(pcm)
