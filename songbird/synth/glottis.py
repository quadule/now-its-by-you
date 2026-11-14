"""The glottal source: Liljencrants-Fant pulses, shaped by one parameter.

Fant's Rd runs from pressed (0.3, bright, short open phase) through modal
(about 1) to breathy (2.7, soft, long open phase). For each Rd on a grid we
solve the LF model once, store a period of the flow derivative, and keep
band-limited copies per pitch band so high notes don't alias. Synthesis is
then a table lookup driven by a phase accumulator, vectorized over the whole
signal.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.optimize import brentq

TABLE = 2048
RD_GRID = np.round(np.arange(0.3, 2.71, 0.1), 2)
# Pitch bands (upper edge Hz); a band's tables keep harmonics below Nyquist at its top.
BAND_EDGES = 60.0 * 2.0 ** (np.arange(1, 12) / 2.0)


def lf_timing(rd: float, tilt: float = 1.0) -> tuple[float, float, float]:
    """Fant (1995): Rd -> (tp, te, ta) as fractions of the period.

    tilt scales the return phase on its own (Klatt's TL does the same): below
    1 the folds close faster and the voice brightens without pressing harder.
    """
    ra = (-1.0 + 4.8 * rd) / 100.0
    rk = (22.4 + 11.8 * rd) / 100.0
    rg = 0.25 * rk / (0.11 * rd / (0.5 + 1.2 * rk) - ra)
    tp = 1.0 / (2.0 * rg)
    return tp, tp * (1.0 + rk), ra * tilt  # the open phase keeps Rd's timing; only the closing speeds up


def lf_period(rd: float, n: int = TABLE, tilt: float = 1.0) -> np.ndarray:
    """One period of the LF flow derivative, negative peak -1, zero net flow."""
    tp, te, ta = lf_timing(rd, tilt)
    tc = 1.0
    wg = np.pi / tp
    # Return phase: eps * ta = 1 - exp(-eps * (tc - te))
    eps = 1.0 / ta
    for _ in range(50):
        eps = (1.0 - np.exp(-eps * (tc - te))) / ta
    closing_area = -(1.0 / (eps * ta)) * ((1.0 - np.exp(-eps * (tc - te))) / eps - (tc - te) * np.exp(-eps * (tc - te)))

    def net_flow(alpha: float) -> float:
        e0 = -1.0 / (np.exp(alpha * te) * np.sin(wg * te))
        opening = e0 * (np.exp(alpha * te) * (alpha * np.sin(wg * te) - wg * np.cos(wg * te)) + wg) / (alpha**2 + wg**2)
        return opening + closing_area

    grid = np.linspace(-20.0, 200.0, 2201)
    values = np.array([net_flow(a) for a in grid])
    k = np.flatnonzero(np.sign(values[:-1]) != np.sign(values[1:]))[0]
    alpha = brentq(net_flow, grid[k], grid[k + 1])
    e0 = -1.0 / (np.exp(alpha * te) * np.sin(wg * te))

    t = np.arange(n) / n
    opening = e0 * np.exp(alpha * t) * np.sin(wg * t)
    closing = -(1.0 / (eps * ta)) * (np.exp(-eps * (t - te)) - np.exp(-eps * (tc - te)))
    return np.where(t <= te, opening, closing)


@lru_cache(maxsize=4)
def tables(sr: int, tilt: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Band-limited derivative tables [rd, band, TABLE] and flow tables [rd, TABLE]."""
    derivative = np.zeros((len(RD_GRID), len(BAND_EDGES), TABLE))
    flow = np.zeros((len(RD_GRID), TABLE))
    for i, rd in enumerate(RD_GRID):
        period = lf_period(rd, tilt=tilt)
        spectrum = np.fft.rfft(period)
        spectrum[0] = 0.0
        for j, top in enumerate(BAND_EDGES):
            keep = int(0.45 * sr / top)
            limited = spectrum.copy()
            limited[keep + 1 :] = 0.0
            derivative[i, j] = np.fft.irfft(limited, TABLE)
        u = np.cumsum(period)
        u -= u.min()
        flow[i] = u / u.max()
    # Every shape at the same power as a modal one: how pressed the folds are changes how bright the
    # voice is, not how loud; loudness is the amplitude's. (Peak-normalized, a pressed pulse has
    # 0.17 of the power of a breathy one, so the syllables sung hardest would come out quietest.)
    modal = int(np.argmin(np.abs(RD_GRID - 1.0)))
    for j in range(len(BAND_EDGES)):
        want = np.sqrt(np.mean(derivative[modal, j] ** 2))
        for i in range(len(RD_GRID)):
            derivative[i, j] *= want / (np.sqrt(np.mean(derivative[i, j] ** 2)) + 1e-12)
    return derivative, flow


def source(f0: np.ndarray, rd: np.ndarray, sr: int, tilt: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Glottal flow derivative and normalized flow (for pulsing noise), per sample.

    f0 and rd are per-sample arrays; the phase accumulates so pitch glides and
    vibrato stay continuous.
    """
    derivative, flow = tables(sr, round(float(tilt), 3))
    phase = np.cumsum(f0 / sr)
    phase -= np.floor(phase)
    pos = phase * TABLE
    i0 = pos.astype(np.int64) % TABLE
    i1 = (i0 + 1) % TABLE
    frac = pos - np.floor(pos)

    r = np.clip((rd - RD_GRID[0]) / 0.1, 0.0, len(RD_GRID) - 1.001)
    r0 = r.astype(np.int64)
    rw = r - r0
    band = np.searchsorted(BAND_EDGES, f0).clip(0, len(BAND_EDGES) - 1)

    def read(table: np.ndarray, ri: np.ndarray) -> np.ndarray:
        a = table[ri, band, i0] if table.ndim == 3 else table[ri, i0]
        b = table[ri, band, i1] if table.ndim == 3 else table[ri, i1]
        return a + frac * (b - a)

    d = (1.0 - rw) * read(derivative, r0) + rw * read(derivative, r0 + 1)
    u = (1.0 - rw) * read(flow, r0) + rw * read(flow, r0 + 1)
    return d, u
