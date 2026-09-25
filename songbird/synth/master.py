"""Mastering and export: loudness (ITU-R BS.1770-4), limiting, dither, FLAC."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import lfilter

TARGET_LUFS = -14.0
CEILING_DB = -1.0


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


def loudness(x: np.ndarray, sr: int) -> float:
    """Integrated loudness in LUFS of a (samples, channels) signal."""
    y = x.reshape(len(x), -1)
    for b, a in _k_weighting(sr):
        y = lfilter(b, a, y, axis=0)
    block, step = int(0.4 * sr), int(0.1 * sr)
    if len(y) < block:
        return -np.inf
    power = np.cumsum(np.concatenate([np.zeros((1, y.shape[1])), y * y]), axis=0)
    starts = np.arange(0, len(y) - block + 1, step)
    energy = ((power[starts + block] - power[starts]) / block).sum(axis=1)
    with np.errstate(divide="ignore"):
        levels = -0.691 + 10.0 * np.log10(energy)
    gated = energy[levels > -70.0]
    if not len(gated):
        return -np.inf
    relative = -0.691 + 10.0 * np.log10(gated.mean()) - 10.0
    gated = energy[(levels > -70.0) & (levels > relative)]
    return float(-0.691 + 10.0 * np.log10(gated.mean()))


def limit(x: np.ndarray, sr: int, ceiling_db: float = CEILING_DB, hold: float = 0.05, attack: float = 0.004) -> np.ndarray:
    """A look-ahead peak limiter that never lets a sample past the ceiling.

    The required gain is min-filtered over +-hold, then smoothed over a
    narrower +-attack window; because every smoothed value averages minima
    whose windows contain the sample, the result never exceeds what that
    sample needs.
    """
    ceiling = 10.0 ** (ceiling_db / 20.0)
    peak = np.max(np.abs(x), axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-12))
    gain = minimum_filter1d(need, size=2 * int(hold * sr) + 1)
    gain = uniform_filter1d(gain, size=2 * int(attack * sr) + 1)
    return np.clip(x * gain[:, None], -ceiling, ceiling)


def master(x: np.ndarray, sr: int, target: float = TARGET_LUFS) -> np.ndarray:
    """Bring a mix to the target loudness without passing the ceiling."""
    y = limit(x, sr)
    for _ in range(4):
        level = loudness(y, sr)
        if not np.isfinite(level) or abs(level - target) < 0.1:
            break
        y = limit(y * 10.0 ** ((target - level) / 20.0), sr)
    return y


def to_pcm16(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """Quantize to 16-bit with seeded TPDF dither."""
    rng = np.random.default_rng(seed)
    dither = rng.uniform(-0.5, 0.5, x.shape) + rng.uniform(-0.5, 0.5, x.shape)
    return np.clip(np.round(x * 32767.0 + dither), -32768, 32767).astype("<i2")


def pcm_sha256(pcm: np.ndarray) -> str:
    """The identity of a rendition: a hash of its decoded samples, not of the file."""
    return hashlib.sha256(np.ascontiguousarray(pcm, dtype="<i2").tobytes()).hexdigest()


def write_flac(path: str | Path, pcm: np.ndarray, sr: int) -> None:
    sf.write(str(path), pcm, sr, format="FLAC", subtype="PCM_16")
