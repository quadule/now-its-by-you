"""The room every rendition on a machine lives in.

The voice harvest reduces a real room to an RT60 and a five-band tonal
profile; this module regenerates an impulse response from exactly those few
numbers, so the room travels as parameters, never as a recording.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

BANDS = ((40.0, 250.0), (250.0, 700.0), (700.0, 2000.0), (2000.0, 5600.0), (5600.0, 16000.0))
AIR = (1.2, 1.1, 1.0, 0.8, 0.55)  # relative decay time per band: highs die first


def impulse_response(
    sr: int,
    rt60: float = 1.1,
    tone: tuple[float, ...] = (1.0, 1.0, 1.0, 0.9, 0.7),
    predelay: float = 0.012,
    seed: int = 0,
) -> np.ndarray:
    """A stereo impulse response, energy-normalized, shape (samples, 2)."""
    rng = np.random.default_rng(seed)
    length = int(sr * (predelay + rt60 * max(AIR)))
    t = np.arange(length) / sr
    ir = np.zeros((length, 2))
    for ch in range(2):
        for (lo, hi), air, gain in zip(BANDS, AIR, tone):
            sos = butter(2, [lo, min(hi, 0.45 * sr)], btype="bandpass", fs=sr, output="sos")
            band = sosfilt(sos, rng.standard_normal(length))
            ir[:, ch] += gain * band * np.exp(-6.908 * t / (rt60 * air))
        ir[:, ch] *= 1.0 - np.exp(-t / 0.02)  # diffuse field builds up
        for _ in range(8):  # a few distinct early reflections
            at = rng.uniform(0.003, 0.04)
            ir[int(at * sr), ch] += rng.choice([-1.0, 1.0]) * rng.uniform(0.5, 1.2) * np.exp(-at / 0.03)
    shift = int(predelay * sr)
    ir = np.concatenate([np.zeros((shift, 2)), ir[: length - shift]])
    return ir / np.sqrt(np.sum(ir**2) / 2.0)


def apply(dry: np.ndarray, ir: np.ndarray, send: np.ndarray | None = None, wet: float = 0.3) -> np.ndarray:
    """Dry signal plus the room's response to `send` (by default the dry signal).

    Sources at different distances share one room: each stem's send level says
    how much of it reaches the room relative to the listener.
    """
    send = dry if send is None else send
    out = np.zeros((len(dry) + len(ir) - 1, 2))
    out[: len(dry)] = dry
    for ch in range(2):
        out[:, ch] += wet * fftconvolve(send[:, ch], ir[:, ch])
    return out
