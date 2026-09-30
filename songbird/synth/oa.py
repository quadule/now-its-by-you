"""scipy.signal.oaconvolve for a long 1-D signal and a short response, a few blocks at a time.

oaconvolve cuts the signal into blocks, transforms them all at once (one row each), multiplies by the
response's transform, transforms back and overlap-adds: for a whole song that is several copies of the
song in memory at once (the padded blocks, their spectra, the product, the blocks back). This makes the
same blocks in the same way, a few of them at a time, and adds each block's tail into the next exactly as
oaconvolve does, so the result is the same to the bit, holding only the output and a few blocks (about CALL bytes of them).

What keeps it the same: every step works along a row alone (the FFTs, the product, the overlap-add), and
the FFT library transforms rows two (or four, or eight: its vector width) at a time from the first row of
a call, with a leftover row done alone. So every call here starts on a row whose index is a multiple of
GROUP (a multiple of any vector width) and the last call takes every row that is left: each row is
transformed alongside the same neighbour as in oaconvolve's single call. tests/test_oa.py holds this
against scipy's own on the lengths and responses a render uses. Only one FFT worker (the default): with
more, scipy divides the rows among its threads differently.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import fft as sp_fft
from scipy.signal import oaconvolve
from scipy.signal._signaltools import _calc_oa_lens

GROUP = 8  # blocks at a time come in multiples of this: a multiple of any SIMD width the FFT groups rows by
CALL = 1 << 22  # bytes of blocks a call works on, roughly (at least one GROUP)


def convolve(x: np.ndarray, h: np.ndarray, n: int | None = None, out: np.ndarray | None = None) -> np.ndarray:
    """oaconvolve(x, h)[:n] (mode "full"), for 1-D real float64 x and h, made a few blocks at a time; into
    `out` (a float64 array of that length, which may be a column of a wider one) if given."""
    x = np.asarray(x)
    h = np.asarray(h)
    s1, s2 = len(x), len(h)
    full = s1 + s2 - 1
    n = full if n is None else min(n, full)
    if (x.ndim != 1 or h.ndim != 1 or x.dtype != np.float64 or h.dtype != np.float64 or s1 == 0 or s2 == 0
            or s1 == s2 or sp_fft.get_workers() != 1):
        return _into(oaconvolve(x, h)[:n], out)
    block, overlap, step1, step2 = _calc_oa_lens(s1, s2)
    if overlap is None or step2 != s2 or s1 <= step1:  # one block, or the response cut up too: scipy's own way
        return _into(oaconvolve(x, h)[:n], out)
    # oaconvolve's block count and padding
    steps = math.ceil((s1 + 1) / step1)
    if (block - overlap) * steps < full:
        steps += 1
    spectrum = sp_fft.rfftn(h.reshape(1, s2), [block], axes=[1])
    out = np.empty(n) if out is None else out
    carry = None  # the last block's tail, into the next block's head
    # the blocks that reach into the first n samples, to a whole number of groups (or every block)
    per = GROUP * max(1, CALL // (8 * block * GROUP))
    rows = min(steps, math.ceil(math.ceil(n / step1) / GROUP) * GROUP)
    bounds = [(a, min(a + per, rows)) for a in range(0, rows, per)]
    for a, b in bounds:
        blocks = np.zeros((b - a, step1))
        take = x[a * step1: min(b * step1, s1)]
        blocks.reshape(-1)[: len(take)] = take
        spectra = sp_fft.rfftn(blocks, [block], axes=[1])
        del blocks
        spectra *= spectrum  # the same products, where they lie
        y = sp_fft.irfftn(spectra, [block], axes=[1])
        del spectra
        if carry is not None:
            y[0, :overlap] += carry
        y[1:, :overlap] += y[:-1, step1:]
        carry = y[-1, step1:].copy()
        flat = y[:, :step1].reshape(-1)
        lo = a * step1
        if lo < n:
            out[lo: min(n, lo + len(flat))] = flat[: n - lo]
    return out


def _into(y: np.ndarray, out: np.ndarray | None) -> np.ndarray:
    if out is None:
        return y
    out[...] = y
    return out
