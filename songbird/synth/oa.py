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
from functools import partial

import numpy as np
from scipy import fft as sp_fft
from scipy.signal import oaconvolve
from scipy.signal._signaltools import _calc_oa_lens

from . import threads

GROUP = 8  # blocks at a time come in multiples of this: a multiple of any SIMD width the FFT groups rows by
CALL = 1 << 22  # bytes of blocks a call works on, roughly (at least one GROUP)


def convolve(x: np.ndarray, h: np.ndarray, n: int | None = None, out: np.ndarray | None = None,
             workers: int = 1) -> np.ndarray:
    """oaconvolve(x, h)[:n] (mode "full") as scipy makes it with `workers` FFT threads (inside
    scipy.fft.set_workers(workers)), for 1-D real float64 x and h, made a few blocks at a time; into `out` (a
    float64 array of that length, which may be a column of a wider one) if given."""
    x = np.asarray(x)
    h = np.asarray(h)
    s1, s2 = len(x), len(h)
    full = s1 + s2 - 1
    n = full if n is None else min(n, full)

    def scipys() -> np.ndarray:
        with sp_fft.set_workers(workers):
            return _into(oaconvolve(x, h)[:n], out)

    if sp_fft.get_workers() != 1:  # inside a caller's own set_workers: scipy's, as it asks
        return _into(oaconvolve(x, h)[:n], out)
    if (x.ndim != 1 or h.ndim != 1 or x.dtype != np.float64 or h.dtype != np.float64 or s1 == 0 or s2 == 0
            or s1 == s2):
        return scipys()
    block, overlap, step1, step2 = _calc_oa_lens(s1, s2)
    if overlap is None or step2 != s2 or s1 <= step1:  # one block, or the response cut up too: scipy's own way
        return scipys()
    # oaconvolve's block count and padding
    steps = math.ceil((s1 + 1) / step1)
    if (block - overlap) * steps < full:
        steps += 1
    spectrum = sp_fft.rfftn(h.reshape(1, s2), [block], axes=[1])  # one row: the same on any number of threads
    out = np.empty(n) if out is None else out
    # scipy's FFT threads take the blocks as np.array_split divides them, each thread its stretch from its first
    # block; each stretch is made here a whole number of groups at a time from its start (the last call of a
    # stretch ending where it ends), until the blocks reach past the first n samples. The stretches are made
    # on up to threads.workers() threads, as scipy's own threads made them side by side; each block's tail goes
    # into the next block's head, within a stretch as it is made, across stretches once both are.
    per = GROUP * max(1, CALL // (8 * block * GROUP))
    needed = math.ceil(n / step1)
    stretches = []
    lo = 0
    for size in (len(part) for part in np.array_split(np.arange(steps), max(1, int(workers)))):
        if size and lo < needed:
            stretches.append((lo, lo + size))
        lo += size

    def stretch(lo: int, hi: int) -> np.ndarray:
        """Blocks lo..hi into out; returns the last one's tail."""
        carry = None
        a = lo
        while a < hi and a < needed:
            b = min(a + per, hi)
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
            start = a * step1
            if start < n:
                out[start: min(n, start + len(flat))] = flat[: n - start]
            a = b
        return carry

    tails = [tail for _, tail in threads.in_order([(k, partial(stretch, *bounds)) for k, bounds in enumerate(stretches)])]
    for (lo, _), tail in zip(stretches[1:], tails[:-1]):  # the tail of each stretch's last block into the next's first
        start = lo * step1
        if start < n:
            out[start: min(n, start + overlap)] += tail[: n - start]
    return out


def _into(y: np.ndarray, out: np.ndarray | None) -> np.ndarray:
    if out is None:
        return y
    out[...] = y
    return out


def convolve_shared(x: np.ndarray, h: np.ndarray, n: int | None = None, workers: int = 1) -> np.ndarray:
    """Each column's convolve(x, h[:, ch], workers=workers)[:n], sharing the input FFTs.

    The response and inverse FFTs keep convolve's two-dimensional row layout and stretch grouping for each
    channel: transforming all channels together uses another SIMD grouping and can change the last bits.
    Only the identical input transforms are shared. The output is fresh; callers may place and scale it in place.
    """
    x, h = np.asarray(x), np.asarray(h)
    s1, s2 = len(x), len(h)
    if s1 == 0 or s2 == 0:
        return np.empty((0, h.shape[1]))
    full = s1 + s2 - 1
    n = full if n is None else min(n, full)
    channels = h.shape[1]

    def separately():
        out = np.empty((n, channels))
        for ch in range(channels):
            convolve(x, h[:, ch], n, out=out[:, ch], workers=workers)
        return out

    if (sp_fft.get_workers() != 1 or x.ndim != 1 or h.ndim != 2 or x.dtype != np.float64
            or h.dtype != np.float64 or s1 == 0 or s2 == 0 or s1 == s2 or channels < 2):
        return separately()
    block, overlap, step1, step2 = _calc_oa_lens(s1, s2)
    if overlap is None or step2 != s2 or s1 <= step1:
        return separately()
    steps = math.ceil((s1 + 1) / step1)
    if (block - overlap) * steps < full:
        steps += 1
    spectra_h = [sp_fft.rfftn(h[:, ch].reshape(1, s2), [block], axes=[1]) for ch in range(channels)]
    out = np.empty((n, channels))
    per = GROUP * max(1, CALL // (8 * block * GROUP))
    needed = min(steps, math.ceil(n / step1))
    stretches = []
    lo = 0
    for size in (len(part) for part in np.array_split(np.arange(steps), max(1, int(workers)))):
        if size and lo < needed:
            stretches.append((lo, lo + size))
        lo += size

    def stretch(lo: int, hi: int) -> list[np.ndarray | None]:
        carries: list[np.ndarray | None] = [None] * channels
        a = lo
        while a < hi and a < needed:
            b = min(a + per, hi)
            blocks = np.zeros((b - a, step1))
            take = x[a * step1: min(b * step1, s1)]
            blocks.reshape(-1)[:len(take)] = take
            spectra = sp_fft.rfftn(blocks, [block], axes=[1])
            del blocks
            for ch in range(channels):
                if ch == channels - 1:
                    spectra *= spectra_h[ch]
                    prod = spectra
                else:
                    prod = spectra * spectra_h[ch]
                y = sp_fft.irfftn(prod, [block], axes=[1])
                del prod
                if carries[ch] is not None:
                    y[0, :overlap] += carries[ch]
                y[1:, :overlap] += y[:-1, step1:]
                carries[ch] = y[-1, step1:].copy()
                flat = y[:, :step1].reshape(-1)
                start = a * step1
                if start < n:
                    out[start:min(n, start + len(flat)), ch] = flat[:n - start]
                del y, flat
            del spectra
            a = b
        return carries

    tails = [tail for _, tail in threads.in_order([(k, partial(stretch, *bounds)) for k, bounds in enumerate(stretches)])]
    for (lo, _), tail in zip(stretches[1:], tails[:-1]):
        start = lo * step1
        if start < n:
            for ch in range(channels):
                out[start:min(n, start + overlap), ch] += tail[ch][:n - start]
    return out


def convolve_columns(x: np.ndarray, h: np.ndarray, n: int | None = None, out: np.ndarray | None = None) -> np.ndarray:
    """oaconvolve(x[:, None], h, axes=0)[:n] (mode "full"), one FFT worker, for a 1-D real float64 x and a
    (samples, channels) h: one signal through a response with a column for each channel (a body's two
    microphones), each block of it transformed once for them all, as scipy does it: its blocks shaped as
    scipy shapes them ((blocks, step, 1) against (1, samples, channels)), a whole number of GROUPs of them at a
    time, so each of the inverse transforms' rows, a block's channel, is made beside the same neighbours as in
    scipy's single call; into `out` (float64, (n, channels)) if given."""
    x = np.asarray(x)
    h = np.asarray(h)
    s1, s2 = len(x), len(h)
    full = s1 + s2 - 1
    n = full if n is None else min(n, full)

    def scipys() -> np.ndarray:
        return _into(oaconvolve(x[:, None], h, axes=0)[:n], out)

    if (sp_fft.get_workers() != 1 or x.ndim != 1 or h.ndim != 2 or x.dtype != np.float64 or h.dtype != np.float64
            or s1 == 0 or s2 == 0 or h.shape[1] == 1):
        return scipys()
    block, overlap, step1, step2 = _calc_oa_lens(s1, s2)
    if overlap is None or step2 != s2 or s1 <= step1:  # one block, or the response cut up too: scipy's own way
        return scipys()
    steps = math.ceil((s1 + 1) / step1)
    if (block - overlap) * steps < full:
        steps += 1
    channels = h.shape[1]
    spectrum = sp_fft.rfftn(h.reshape(1, s2, channels), [block], axes=[1])
    out = np.empty((n, channels)) if out is None else out
    per = GROUP * max(1, CALL // (8 * block * channels * GROUP))
    needed = min(steps, math.ceil(n / step1))
    carry = None
    for a in range(0, needed, per):
        b = min(a + per, steps)
        blocks = np.zeros((b - a, step1, 1))
        take = x[a * step1: min(b * step1, s1)]
        blocks.reshape(-1)[: len(take)] = take
        spectra = sp_fft.rfftn(blocks, [block], axes=[1])
        del blocks
        y = sp_fft.irfftn(spectra * spectrum, [block], axes=[1])
        del spectra
        if carry is not None:
            y[0, :overlap] += carry
        y[1:, :overlap] += y[:-1, step1:]
        carry = y[-1, step1:].copy()
        flat = y[:, :step1].reshape(-1, channels)
        start = a * step1
        out[start: min(n, start + len(flat))] = flat[: n - start]
    return out
