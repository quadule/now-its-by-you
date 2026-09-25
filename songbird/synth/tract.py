"""The vocal tract: time-varying formant resonators after Klatt (1980).

Formants move every block (a few milliseconds). Each resonator is the
two-pole y[n] = A x[n] + B y[n-1] + C y[n-2] with unity gain at DC, so a
cascade of them gives the correct relative formant levels. Coefficients
change between blocks; the filter state handed to each block is rebuilt from
the true previous outputs, so a coefficient change never produces a jump.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, sosfilt
from scipy.special import j1, struve

SPEED_OF_SOUND = 35000.0  # cm/s


def resonator(freq: np.ndarray, bw: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    c = -np.exp(-2.0 * np.pi * bw / sr)
    b = 2.0 * np.exp(-np.pi * bw / sr) * np.cos(2.0 * np.pi * freq / sr)
    return 1.0 - b - c, b, c


def cascade(x: np.ndarray, freqs: np.ndarray, bws: np.ndarray, block: int, sr: int) -> np.ndarray:
    """Pass x through len(freqs[0]) resonators in series.

    freqs and bws are (blocks, resonators); block b covers samples
    [b*block, (b+1)*block).
    """
    a, b, c = resonator(freqs, bws, sr)
    y = x.copy()
    for k in range(freqs.shape[1]):
        out = np.empty_like(y)
        y1 = y2 = 0.0
        for i in range(freqs.shape[0]):
            s = slice(i * block, min((i + 1) * block, len(y)))
            if s.start >= len(y):
                break
            bi, ci = b[i, k], c[i, k]
            zi = [bi * y1 + ci * y2, ci * y1]
            seg, _ = lfilter([a[i, k]], [1.0, -bi, -ci], y[s], zi=zi)
            out[s] = seg
            y1 = seg[-1]
            y2 = seg[-2] if len(seg) > 1 else y1
        y = out
    return y


def antiresonator(x: np.ndarray, freq: np.ndarray, bw: np.ndarray, block: int, sr: int) -> np.ndarray:
    """Klatt's antiresonator (a zero pair), the inverse of the resonator."""
    a, b, c = resonator(freq, bw, sr)
    b0, b1, b2 = 1.0 / a, -b / a, -c / a
    out = np.empty_like(x)
    x1 = x2 = 0.0
    for i in range(len(freq)):
        s = slice(i * block, min((i + 1) * block, len(x)))
        if s.start >= len(x):
            break
        zi = [b1[i] * x1 + b2[i] * x2, b2[i] * x1]
        out[s], _ = lfilter([b0[i], b1[i], b2[i]], [1.0], x[s], zi=zi)
        x1 = x[s][-1]
        x2 = x[s][-2] if s.stop - s.start > 1 else x1
    return out


def noise_band(noise: np.ndarray, shape: list[tuple[float, float, float]], sr: int) -> np.ndarray:
    """Shape noise by a sum of band-pass regions (centre Hz, bandwidth Hz, gain dB)."""
    out = np.zeros_like(noise)
    for centre, bw, gain_db in shape:
        lo = max(centre - bw / 2.0, 100.0)
        hi = min(centre + bw / 2.0, 0.47 * sr)
        sos = butter(2, [lo, hi], btype="bandpass", fs=sr, output="sos")
        out += 10.0 ** (gain_db / 20.0) * sosfilt(sos, noise)
    return out


def tube_magnitude(f: np.ndarray, length_cm: float, mouth_cm: float = 1.0) -> np.ndarray:
    """|volume-velocity transfer| of a uniform lossy tube radiating from a mouth.

    Wall and viscous losses enter as a frequency-dependent attenuation; the
    mouth radiates like a piston in a baffle (the 2ka Bessel/Struve impedance).
    """
    alpha = np.pi * (40.0 + 0.03 * f) / SPEED_OF_SOUND
    g = (alpha + 2j * np.pi * f / SPEED_OF_SOUND) * length_cm
    z = np.maximum(2.0 * (2.0 * np.pi * f / SPEED_OF_SOUND) * mouth_cm, 1e-9)
    zeta = (1.0 - 2.0 * j1(z) / z) + 1j * (2.0 * struve(1, z) / z)
    return 1.0 / np.abs(np.cosh(g) + zeta * np.sinh(g))


def upper_branch(sr: int, scale: float = 1.0, mouth_cm: float = 1.0, crossover: float = 4400.0,
                 n_fft: int = 16384, taps: int = 1024) -> np.ndarray:
    """A fixed minimum-phase FIR for the tract above the moving formants.

    A Klatt cascade can only model the resonances it has tracks for: each one
    pulls everything above it down 12 dB an octave, so with five formants the
    spectrum collapses past about 5 kHz. The real tube's upper resonances are
    nearly fixed, so they run in parallel as one time-invariant filter: the
    lossy tube's response, high-passed where the cascade takes over. Kept
    parallel (not after the cascade) so the cascade's block-wise coefficient
    updates stay buried under its own roll-off instead of being lifted into
    audible hiss. Design and measurements by the Fable voice review.
    """
    f = np.linspace(0.0, sr / 2.0, n_fft // 2 + 1)
    u = tube_magnitude(np.maximum(f, 1.0), 16.64 / scale, mouth_cm)  # 16.64 cm puts F1 at 500 Hz
    u /= np.sqrt(1.0 + (crossover * scale / np.maximum(f, 1.0)) ** 8)  # 4th-order high-pass
    w = np.clip((f - 12000.0) / 6000.0, 0.0, 1.0)
    u *= 10.0 ** (-1.5 * 0.5 * (1.0 - np.cos(np.pi * w)))
    cepstrum = np.fft.irfft(np.log(np.maximum(u, 1e-12)), n_fft)  # minimum phase by folding the cepstrum
    fold = np.zeros(n_fft)
    fold[0] = cepstrum[0]
    fold[1 : n_fft // 2] = 2.0 * cepstrum[1 : n_fft // 2]
    fold[n_fft // 2] = cepstrum[n_fft // 2]
    h = np.fft.irfft(np.exp(np.fft.rfft(fold)), n_fft)[:taps]
    fade = taps // 5
    h[-fade:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fade)))
    return h


def high_shelf(freq: float, gain_db: float, sr: int, slope: float = 0.8) -> np.ndarray:
    """An RBJ high-shelf biquad as one second-order section."""
    a = 10.0 ** (gain_db / 40.0)
    w = 2.0 * np.pi * freq / sr
    alpha = np.sin(w) / 2.0 * np.sqrt((a + 1.0 / a) * (1.0 / slope - 1.0) + 2.0)
    cw, sq = np.cos(w), 2.0 * np.sqrt(a) * alpha
    b = [a * ((a + 1) + (a - 1) * cw + sq), -2 * a * ((a - 1) + (a + 1) * cw), a * ((a + 1) + (a - 1) * cw - sq)]
    den = [(a + 1) - (a - 1) * cw + sq, 2 * ((a - 1) - (a + 1) * cw), (a + 1) - (a - 1) * cw - sq]
    return np.array([b + den]) / den[0]
