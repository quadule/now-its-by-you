"""The mix's tools: equalizers, dynamics, saturation, stereo width, tape transport.

Pure functions of their input and settings, the same to the sample on every
run. Signals are (samples, channels) arrays unless a docstring says mono.
Levels a tool reacts to are measured on the signal itself (its loud
passages), so a quieter or brighter singer or instrument is treated the same
way: nothing is tuned to one voice's absolute level.

The sample loops are compiled with numba (cached on disk after the first
run); everything else is numpy.
"""

from __future__ import annotations

from functools import partial

import numpy as np
from numba import njit
from scipy.ndimage import uniform_filter1d

from . import threads
from .iir import butter

# --- equalizers: RBJ cookbook biquads as second-order sections -----------------


def _section(b: list[float], a: list[float]) -> np.ndarray:
    return np.array([b[0] / a[0], b[1] / a[0], b[2] / a[0], 1.0, a[1] / a[0], a[2] / a[0]])


def peaking(f: float, gain_db: float, q: float, sr: int) -> np.ndarray:
    a = 10.0 ** (gain_db / 40.0)
    w = 2.0 * np.pi * f / sr
    alpha = np.sin(w) / (2.0 * q)
    return _section([1 + alpha * a, -2 * np.cos(w), 1 - alpha * a], [1 + alpha / a, -2 * np.cos(w), 1 - alpha / a])


def shelf(kind: str, f: float, gain_db: float, sr: int, slope: float = 0.8) -> np.ndarray:
    """A low ("low") or high ("high") shelf, gain_db beyond f, gentler at slope < 1."""
    a = 10.0 ** (gain_db / 40.0)
    w = 2.0 * np.pi * f / sr
    cw, root = np.cos(w), np.sqrt(a)
    alpha = np.sin(w) / 2.0 * np.sqrt((a + 1.0 / a) * (1.0 / slope - 1.0) + 2.0)
    if kind == "low":
        b = [a * ((a + 1) - (a - 1) * cw + 2 * root * alpha), 2 * a * ((a - 1) - (a + 1) * cw),
             a * ((a + 1) - (a - 1) * cw - 2 * root * alpha)]
        den = [(a + 1) + (a - 1) * cw + 2 * root * alpha, -2 * ((a - 1) + (a + 1) * cw), (a + 1) + (a - 1) * cw - 2 * root * alpha]
    else:
        b = [a * ((a + 1) + (a - 1) * cw + 2 * root * alpha), -2 * a * ((a - 1) + (a + 1) * cw),
             a * ((a + 1) + (a - 1) * cw - 2 * root * alpha)]
        den = [(a + 1) - (a - 1) * cw + 2 * root * alpha, 2 * ((a - 1) - (a + 1) * cw), (a + 1) - (a - 1) * cw - 2 * root * alpha]
    return _section(b, den)


def bandpass(f: float, q: float, sr: int) -> np.ndarray:
    """0 dB at f, falling away either side: the band a dynamic equalizer works on."""
    w = 2.0 * np.pi * f / sr
    alpha = np.sin(w) / (2.0 * q)
    return _section([alpha, 0.0, -alpha], [1 + alpha, -2 * np.cos(w), 1 - alpha])


def design(spec, sr: int) -> np.ndarray:
    """An equalizer from a list of bands:
    ("hp", f[, order]), ("lp", f[, order]), ("peak", f, dB, q), ("low", f, dB), ("high", f, dB)."""
    sections = []
    for band in spec:
        kind, f = band[0], min(band[1], 0.45 * sr)
        if kind in ("hp", "lp"):
            order = band[2] if len(band) > 2 else 2
            sections.append(butter(order, f, btype="highpass" if kind == "hp" else "lowpass", fs=sr, output="sos"))
        elif kind == "peak":
            sections.append(peaking(f, band[2], band[3], sr)[None])
        else:
            sections.append(shelf(kind, f, band[2], sr)[None])
    return np.concatenate(sections) if sections else np.zeros((0, 6))


@njit(cache=True, nogil=True)
def _four(y: np.ndarray, p: np.ndarray, q: np.ndarray, r: np.ndarray, s: np.ndarray) -> None:
    """Four biquads in cascade (transposed direct form II) over every channel of
    y, in place. Run together, their state stays in registers and the four
    feedback chains overlap: three times as fast as one section at a time."""
    n, chans = y.shape
    for c in range(chans):
        z1 = z2 = w1 = w2 = u1 = u2 = t1 = t2 = 0.0
        for i in range(n):
            v = y[i, c]
            o = p[0] * v + z1
            z1 = p[1] * v - p[4] * o + z2
            z2 = p[2] * v - p[5] * o
            u = q[0] * o + w1
            w1 = q[1] * o - q[4] * u + w2
            w2 = q[2] * o - q[5] * u
            m = r[0] * u + u1
            u1 = r[1] * u - r[4] * m + u2
            u2 = r[2] * u - r[5] * m
            k = s[0] * m + t1
            t1 = s[1] * m - s[4] * k + t2
            t2 = s[2] * m - s[5] * k
            y[i, c] = k


@njit(cache=True, nogil=True)
def _two(y: np.ndarray, p: np.ndarray, q: np.ndarray) -> None:
    n, chans = y.shape
    for c in range(chans):
        z1 = z2 = w1 = w2 = 0.0
        for i in range(n):
            v = y[i, c]
            o = p[0] * v + z1
            z1 = p[1] * v - p[4] * o + z2
            z2 = p[2] * v - p[5] * o
            u = q[0] * o + w1
            w1 = q[1] * o - q[4] * u + w2
            w2 = q[2] * o - q[5] * u
            y[i, c] = u


@njit(cache=True, nogil=True)
def _one(y: np.ndarray, p: np.ndarray) -> None:
    n, chans = y.shape
    for c in range(chans):
        z1 = z2 = 0.0
        for i in range(n):
            v = y[i, c]
            o = p[0] * v + z1
            z1 = p[1] * v - p[4] * o + z2
            z2 = p[2] * v - p[5] * o
            y[i, c] = o


IDENTITY = np.array([1.0, 0.0, 0.0, 1.0, 0.0, 0.0])


def _biquads(x: np.ndarray, sos: np.ndarray, inplace: bool = False) -> np.ndarray:
    """Second-order sections in cascade along axis 0 of a (samples, channels) array. A long signal's channels
    are filtered at once, each on a thread of its own (each channel's filter is its own: the same samples
    either way). inplace: x (float64, C-contiguous) is filtered where it is, and returned."""
    if x.ndim == 2 and x.shape[1] > 1 and len(x) >= 1 << 16 and threads.workers() > 1:
        def column(c: int) -> np.ndarray:
            return _cascade(np.ascontiguousarray(x[:, c: c + 1]), sos, False)
        if inplace:
            for c, y in threads.in_order([(c, partial(column, c)) for c in range(x.shape[1])]):
                x[:, c: c + 1] = y
            return x
        return np.concatenate([y for _, y in threads.in_order([(c, partial(column, c)) for c in range(x.shape[1])])],
                              axis=1)
    return _cascade(x, sos, not inplace)


def _cascade(x: np.ndarray, sos: np.ndarray, copy: bool = True) -> np.ndarray:
    y = x.copy() if copy else x
    rows = [np.ascontiguousarray(row, dtype=np.float64) for row in np.asarray(sos, dtype=np.float64)]
    while rows:
        if len(rows) >= 3:
            group, rows = rows[:4], rows[4:]
            _four(y, *(group + [IDENTITY] * (4 - len(group))))
        elif len(rows) == 2:
            _two(y, *rows)
            rows = []
        else:
            _one(y, rows[0])
            rows = []
    return y


def equalize(x: np.ndarray, sos: np.ndarray, inplace: bool = False) -> np.ndarray:
    """x through the sections of `sos` (fx.design); x may be mono. inplace: x itself is filtered (when it is a
    float64, C-contiguous array; otherwise a copy is, as without) and returned: the same samples, without a
    second copy of a long signal held."""
    if not len(sos) or not len(x):
        return x
    y = np.ascontiguousarray(x.reshape(len(x), -1), dtype=np.float64)
    y = _biquads(y, np.ascontiguousarray(sos, dtype=np.float64), inplace=inplace and np.shares_memory(y, x))
    return y.reshape(x.shape)


# --- stems ---------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _span(x: np.ndarray, floor: float) -> tuple[int, int]:
    n, chans = x.shape
    first, last = -1, -1
    for i in range(n):
        for c in range(chans):
            if abs(x[i, c]) > floor:
                first = i
                break
        if first >= 0:
            break
    for i in range(n - 1, -1, -1):
        for c in range(chans):
            if abs(x[i, c]) > floor:
                last = i
                break
        if last >= 0:
            break
    return first, last


def span(x: np.ndarray, sr: int, pad: float = 0.5) -> slice:
    """The stretch of a stem that sounds, with `pad` seconds either side for filters to ring."""
    first, last = _span(np.ascontiguousarray(x.reshape(len(x), -1)), 1e-7)
    if first < 0:
        return slice(0, 0)
    return slice(max(0, first - int(pad * sr)), min(len(x), last + 1 + int(pad * sr)))


@njit(cache=True, nogil=True)
def _products(x: np.ndarray) -> tuple[float, float, float]:
    ll = rr = lr = 0.0
    for i in range(x.shape[0]):
        ll += x[i, 0] * x[i, 0]
        rr += x[i, 1] * x[i, 1]
        lr += x[i, 0] * x[i, 1]
    return ll, rr, lr


def as_mono(x: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """A stereo stem that is one mono sound panned (left and right in a fixed
    ratio), as that sound and its two channel gains: it can then be treated
    once instead of twice. None for anything truly stereo."""
    ll, rr, lr = _products(np.ascontiguousarray(x))
    if ll <= 0 or rr <= 0 or lr <= 0 or lr * lr < (1.0 - 1e-9) * ll * rr:
        return None
    gains = np.array([np.sqrt(ll), np.sqrt(rr)]) / np.sqrt(ll + rr)
    return x @ gains, gains


# --- running filters over a whole song ------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _running_mean(x: np.ndarray, size: int, out: np.ndarray) -> np.ndarray:
    """scipy.ndimage's uniform_filter1d, mode "nearest", as it computes it: a running sum over the extended
    line (each value in, the one `size` back out), divided by size at every sample. The values leaving the
    sum are kept in a ring, so out may be x itself."""
    n = x.shape[0]
    size1 = size // 2
    ring = np.empty(size)
    total = 0.0
    for j in range(size):
        v = x[min(max(j - size1, 0), n - 1)]
        ring[j] = v
        total += v
    fs = float(size)
    out[0] = total / fs
    for i in range(1, n):
        k = (i - 1) % size
        gone = ring[k]
        v = x[min(max(i - 1 + size - size1, 0), n - 1)]
        ring[k] = v
        total += v - gone
        out[i] = total / fs
    return out


def running_mean(x: np.ndarray, size: int, out: np.ndarray | None = None) -> np.ndarray:
    """uniform_filter1d(x, size, mode="nearest") of a 1-D float64 signal, to the bit, without the two copies
    of the line scipy makes; out may be x itself (the mean where it lies)."""
    x = np.ascontiguousarray(x, dtype=np.float64)
    if not len(x):
        return x.copy() if out is None else out
    return _running_mean(x, max(int(size), 1), np.empty_like(x) if out is None else out)


@njit(cache=True, nogil=True)
def _sliding_min(x: np.ndarray, before: int, after: int, out: np.ndarray) -> np.ndarray:
    """out[i] = the least of x[i - before .. i + after] (clipped to the signal, as mode "nearest" extends it),
    by a queue of the candidates (their values kept, so out may be x itself when after >= 0)."""
    n = x.shape[0]
    cap = before + after + 2
    qi = np.empty(cap, np.int64)
    qv = np.empty(cap)
    head = 0
    count = 0
    nxt = 0
    for i in range(n):
        hi = min(max(i + after, 0), n - 1)
        lo = min(max(i - before, 0), n - 1)
        while nxt <= hi:
            v = x[nxt]
            while count > 0 and qv[(head + count - 1) % cap] >= v:
                count -= 1
            qi[(head + count) % cap] = nxt
            qv[(head + count) % cap] = v
            count += 1
            nxt += 1
        while qi[head] < lo:
            head = (head + 1) % cap
            count -= 1
        out[i] = qv[head]
    return out


def sliding_min(x: np.ndarray, size: int, origin: int = 0, out: np.ndarray | None = None) -> np.ndarray:
    """minimum_filter1d(x, size, mode="nearest", origin=origin) of a 1-D float64 signal (a least value is the
    same value however it is found), without scipy's copies of the line; out may be x itself."""
    x = np.ascontiguousarray(x, dtype=np.float64)
    if not len(x):
        return x.copy() if out is None else out
    before = size // 2 + origin
    after = size - 1 - before
    if out is x and after < 0:
        out = None
    return _sliding_min(x, before, after, np.empty_like(x) if out is None else out)


@njit(cache=True, nogil=True)
def _hold(playing: np.ndarray, track: np.ndarray) -> None:
    last = 0
    for i in range(playing.shape[0]):
        if playing[i]:
            last = i
        else:
            track[i] = track[last]


def hold(playing: np.ndarray, *tracks: np.ndarray) -> None:
    """Each track, where `playing` is false, holds its value at the last sample that was (the first sample's
    before any): track[np.maximum.accumulate(np.where(playing, np.arange(n), 0))], made where it lies (a
    held sample is copied from one that never changes)."""
    playing = np.ascontiguousarray(playing, dtype=np.bool_)
    for track in tracks:
        _hold(playing, track)


# --- levels and dynamics ---------------------------------------------------------------


def db(p):
    return 10.0 * np.log10(p + 1e-12)


@njit(cache=True, nogil=True)
def _block_power(x: np.ndarray, block: int) -> np.ndarray:
    n, chans = x.shape
    k = n // block
    out = np.zeros(k)
    for b in range(k):
        s = 0.0
        for i in range(b * block, (b + 1) * block):
            for c in range(chans):
                s += x[i, c] * x[i, c]
        out[b] = s / (block * chans)
    return out


def loud_level(x: np.ndarray, sr: int, pct: float = 90.0, window: float = 0.05) -> float:
    """The level (dB of mean power) the signal reaches in its loud passages:
    this percentile of its `window`-second levels, among those within 40 dB
    of the loudest (silence doesn't count)."""
    levels = db(_block_power(np.ascontiguousarray(x.reshape(len(x), -1)), max(1, int(window * sr))))
    if not len(levels):
        return -120.0
    live = levels[levels > levels.max() - 40.0]
    return float(np.percentile(live, pct))


def _coef(seconds: float, rate: float) -> float:
    return float(np.exp(-1.0 / max(seconds * rate, 1.0)))


STEP = 16  # samples between a compressor's decisions (0.36 ms): its gain is interpolated between them


@njit(cache=True, nogil=True)
def _detect_every(key: np.ndarray, coef: float, step: int) -> np.ndarray:
    """Mean power over the channels, followed by a one-pole average: every step-th value of it (the average
    runs over every sample; only the values the compressors read are kept)."""
    n, chans = key.shape
    out = np.empty((n + step - 1) // step)
    p = 0.0
    for i in range(n):
        s = 0.0
        for c in range(chans):
            s += key[i, c] * key[i, c]
        p = coef * p + (1.0 - coef) * s / chans
        if i % step == 0:
            out[i // step] = p
    return out


@njit(cache=True, nogil=True)
def _ballistics(target: np.ndarray, attack: float, release: float) -> np.ndarray:
    """A one-pole follower of a gain in dB that falls at the attack rate and
    recovers at the release rate (coefficients per step)."""
    out = np.empty_like(target)
    g = 0.0
    for i in range(len(target)):
        t = target[i]
        c = attack if t < g else release
        g = c * g + (1.0 - c) * t
        out[i] = g
    return out


@njit(cache=True, nogil=True)
def _apply(x: np.ndarray, lin: np.ndarray, step: int, band: np.ndarray, y: np.ndarray) -> np.ndarray:
    """x with a gain given every `step` samples (linear between), into y (which may be x itself); where `band`
    has channels, only that part of x is scaled: x + band * (gain - 1)."""
    n, chans = x.shape
    split = band.shape[1] == chans
    for i in range(n):
        k = i // step
        f = (i - k * step) / step
        g = lin[k] if k + 1 >= len(lin) else lin[k] + f * (lin[k + 1] - lin[k])
        for c in range(chans):
            y[i, c] = x[i, c] + band[i, c] * (g - 1.0) if split else x[i, c] * g
    return y


def soften(x: np.ndarray, sr: int, over: float = 6.0, amount: float = 0.6, fast: float = 0.0005, slow: float = 0.03,
           release: float = 0.02, inplace: bool = False) -> np.ndarray:
    """A transient softener: what jumps more than `over` dB above the signal's own recent level (a `slow` s
    average) within `fast` s is turned down by `amount` of the excess, at once, and let go over `release` s.
    The opposite of what saturation does to a click: a consonant's burst or a plosive keeps its place but
    loses its edge. Nothing else is touched (a held vowel never rises that fast). amount 0 is the input."""
    if amount <= 0:
        return x
    x2 = _stereo(x)
    quick = db(_detect_every(x2, _coef(fast, sr), STEP))
    steady = db(_detect_every(x2, _coef(slow, sr), STEP))
    target = -amount * np.clip(quick - steady - over, 0.0, None)
    rate = sr / STEP
    gain = _ballistics(target, _coef(0.0002, rate), _coef(release, rate))
    out = x2 if inplace and np.shares_memory(x2, x) else np.empty_like(x2)
    return _apply(x2, 10.0 ** (gain / 20.0), STEP, np.zeros((len(x2), 0)), out).reshape(x.shape)


def gain_computer(level_db: np.ndarray, threshold: float, ratio: float, knee: float) -> np.ndarray:
    """Gain change in dB (<= 0) of a compressor with a soft knee `knee` dB wide."""
    over = level_db - threshold
    slope = 1.0 / ratio - 1.0
    g = np.where(over > knee / 2, slope * over, 0.0)
    inside = np.abs(over) <= knee / 2
    return np.where(inside, slope * (over + knee / 2) ** 2 / (2 * max(knee, 1e-9)), g)


def _stereo(x: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(x.reshape(len(x), -1), dtype=np.float64)


def compress(x: np.ndarray, sr: int, threshold: float, ratio: float, attack: float, release: float,
             knee: float = 6.0, window: float = 0.01, key: np.ndarray | None = None,
             ride: float = 0.0, above: float = 0.0, inplace: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """A feed-forward compressor, channels linked: it listens to the power of
    `key` (x itself by default) averaged over about `window` seconds, has a
    soft knee `knee` dB wide, and attack and release times in seconds.

    With `ride` (seconds), the threshold rides on the music: it is `above` dB
    over the level of the `ride` seconds around each moment, and never under
    `threshold`. Such a compressor evens a moment against its surroundings
    (a syllable against its phrase, a pluck against its bar) but leaves a
    quiet verse quiet and a full refrain full: the song's arc is kept.

    Returns the output and the gain it applied (dB, every STEP samples). inplace: the output is written over x
    (when x is a float64, C-contiguous array; otherwise it is new, as without)."""
    x2 = _stereo(x)
    power = _detect_every(x2 if key is None else _stereo(key), _coef(window, sr), STEP)
    level = db(power)
    if ride > 0:
        around = db(uniform_filter1d(power, max(1, int(ride * sr / STEP)), mode="nearest"))
        threshold = np.maximum(around + above, threshold)
    rate = sr / STEP
    gain = _ballistics(gain_computer(level, threshold, ratio, knee), _coef(attack, rate), _coef(release, rate))
    return apply_gain(x, gain, inplace), gain


def apply_gain(x: np.ndarray, gain_db: np.ndarray, inplace: bool = False) -> np.ndarray:
    """x through a gain given in dB every STEP samples (as compress returns it), linear in between. inplace: the
    result is written over x (when x is a float64, C-contiguous array; otherwise it is new, as without)."""
    x2 = _stereo(x)
    out = x2 if inplace and np.shares_memory(x2, x) else np.empty_like(x2)
    return _apply(x2, 10.0 ** (gain_db / 20.0), STEP, np.zeros((0, 0)), out).reshape(x.shape)


def _both_ways(x2: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """x through sos forward and then backward: the response's magnitude squared and no phase at all (a
    render has the whole signal at hand). (The backward pass filters its reversed copy where it lies.)"""
    back = np.ascontiguousarray(_biquads(x2, sos)[::-1])
    return np.ascontiguousarray(_biquads(back, sos, inplace=True)[::-1])


def deess(x: np.ndarray, sr: int, split: float = 4500.0, excess: float = 3.0, ratio: float = 3.0,
          most: float = 8.0, inplace: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Turn the highs down while they outweigh the voice's body: a split-band
    de-esser whose threshold is the voice's own balance, so it hears an "s"
    by its spectrum, not by how loud the singer is. It listens to the band
    above `split` against the body, the voice an octave under the split,
    where no sibilant reaches (so an "s" sitting across the split is heard
    whole), and turns down the voice above `split`. Both bands are split
    without phase (a low-pass run forward and back, and what it leaves): the
    two add back to the voice exactly, and the part turned down rises
    smoothly from -14 dB half an octave under the split (-6 dB at it) to all
    of the voice above it, so an "s" is turned down rather than tilted, and
    nothing is ever turned up.
    `excess`: how far (dB) the highs may rise over the body before they are
    reduced, by `ratio`, never by more than `most` dB. Highs 40 dB under the
    voice's loud passages are left alone, whatever their balance (breath, the
    start of a sound). Where nothing is reduced the output is the input."""
    x2 = _stereo(x)
    highs = x2 - _both_ways(x2, butter(2, split, btype="lowpass", fs=sr, output="sos"))
    body = _both_ways(x2, butter(2, split / 2.0, btype="lowpass", fs=sr, output="sos"))
    coef = _coef(0.004, sr)
    high = db(_detect_every(highs, coef, STEP))
    over = high - db(_detect_every(body, coef, STEP)) - excess
    del body
    target = np.clip(-over * (1.0 - 1.0 / ratio), -most, 0.0)
    target[high < loud_level(x2, sr) - 40.0] = 0.0
    rate = sr / STEP
    gain = _ballistics(target, _coef(0.001, rate), _coef(0.06, rate))
    out = x2 if inplace and np.shares_memory(x2, x) else np.empty_like(x2)
    y = _apply(x2, 10.0 ** (gain / 20.0), STEP, highs, out)
    return y.reshape(x.shape), gain


def dynamic_dip(x: np.ndarray, sr: int, f: float, q: float, depth_db: np.ndarray, inplace: bool = False) -> np.ndarray:
    """A peaking cut at f whose depth (dB, >= 0, per sample) moves: the band is
    taken out in proportion, x + (g - 1) * bandpass(x), which at g = 1 is x. inplace: written over x (when x
    is a float64, C-contiguous array)."""
    x2 = _stereo(x)
    band = _biquads(x2, bandpass(f, q, sr)[None])
    lin = np.exp(-np.maximum(depth_db[::STEP], 0.0) * (np.log(10.0) / 20.0))
    out = x2 if inplace and np.shares_memory(x2, x) else np.empty_like(x2)
    return _apply(x2, lin, STEP, band, out).reshape(x.shape)


@njit(cache=True, nogil=True)
def _follow(x, detect, rise, fall, floor_db, span_db):
    n, chans = x.shape
    out = np.empty(n)
    p = 0.0
    a = 0.0
    for i in range(n):
        s = 0.0
        for c in range(chans):
            s += x[i, c] * x[i, c]
        p = detect * p + (1.0 - detect) * s / chans
        t = (10.0 * np.log10(p + 1e-20) - floor_db) / span_db
        t = min(max(t, 0.0), 1.0)
        coef = rise if t > a else fall
        a = coef * a + (1.0 - coef) * t
        out[i] = a
    return out


def activity(x: np.ndarray, sr: int, floor: float = 24.0, span: float = 12.0,
             attack: float = 0.01, release: float = 0.25) -> np.ndarray:
    """Mono, 0..1: how much a part is sounding, against its own loud passages:
    1 within `floor - span` dB of them, 0 more than `floor` dB under; it
    rises in `attack` seconds and falls in `release`."""
    x2 = np.ascontiguousarray(x.reshape(len(x), -1), dtype=np.float64)
    loud = loud_level(x2, sr)
    return _follow(x2, _coef(0.02, sr), _coef(attack, sr), _coef(release, sr), loud - floor, span)


# --- colour and space ---------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _block_peaks(x: np.ndarray, block: int) -> np.ndarray:
    n, chans = x.shape
    k = n // block
    out = np.zeros(k)
    for b in range(k):
        m = 0.0
        for i in range(b * block, (b + 1) * block):
            for c in range(chans):
                v = abs(x[i, c])
                if v > m:
                    m = v
        out[b] = m
    return out


def loud_peak(x: np.ndarray, sr: int, pct: float = 90.0) -> float:
    """How high the signal's loud peaks reach: this percentile of its 20 ms
    peaks, among those within 40 dB of the highest."""
    peaks = _block_peaks(np.ascontiguousarray(x.reshape(len(x), -1)), max(1, int(0.02 * sr)))
    if not len(peaks) or peaks.max() <= 0:
        return 0.0
    live = peaks[peaks > peaks.max() * 0.01]
    return float(np.percentile(live, pct))


@njit(cache=True, nogil=True)
def _soft(v: float) -> float:
    """A soft clipper shaped like tanh: x(27 + x^2) / (27 + 9x^2), flat at +-1 beyond +-3."""
    if v >= 3.0:
        return 1.0
    if v <= -3.0:
        return -1.0
    w = v * v
    return v * (27.0 + w) / (27.0 + 9.0 * w)


@njit(cache=True, nogil=True)
def _saturate(x, k, bias, dc, y):
    """The curve over every sample of x, into y (which may be x: each sample is read before it is written)."""
    n, chans = x.shape
    th = _soft(bias)
    w = bias * bias
    slope = (729.0 - 162.0 * w + 9.0 * w * w) / (27.0 + 9.0 * w) ** 2  # the curve's slope at the bias
    norm = 1.0 / (k * slope)
    for c in range(chans):
        prev_in = 0.0
        prev_out = 0.0
        for i in range(n):
            v = (_soft(k * x[i, c] + bias) - th) * norm
            out = v - prev_in + dc * prev_out  # the tilt's slow offset, blocked
            prev_in = v
            prev_out = out
            y[i, c] = out
    return y


def saturate(x: np.ndarray, sr: int, drive: float, bias: float = 0.15, inplace: bool = False) -> np.ndarray:
    """Soft saturation that thickens rather than distorts: the signal's loud
    peaks reach `drive` on a tanh-like curve (0.25 a whisper, about 0.5%
    distortion on them; 1 plainly driven), whatever its level. `bias` tilts
    the curve for even harmonics, like a tube or tape. Small signals pass
    at unity gain; the offset the tilt makes is blocked below 8 Hz. inplace: written over x (when x is a
    float64, C-contiguous array)."""
    if drive <= 0:
        return x
    ref = loud_peak(x, sr) + 1e-12
    shape = x.shape
    x2 = np.ascontiguousarray(x.reshape(len(x), -1), dtype=np.float64)
    out = x2 if inplace and np.shares_memory(x2, x) else np.empty_like(x2)
    y = _saturate(x2, drive / ref, bias, float(np.exp(-2.0 * np.pi * 8.0 / sr)), out)
    return y.reshape(shape)


def width(x: np.ndarray, sr: int, amount: float, mono_below: float = 140.0) -> np.ndarray:
    """Scale the side (L - R) against the mid; below `mono_below` the side is
    never widened, so the low end stays centred."""
    if amount == 1.0:
        return x
    mid = (x[:, 0] + x[:, 1]) / 2.0
    side = (x[:, 0] - x[:, 1]) / 2.0
    low = equalize(side, butter(2, mono_below, btype="lowpass", fs=sr, output="sos"))
    side = low * min(amount, 1.0) + (side - low) * amount
    return np.stack([mid + side, mid - side], axis=1)


def delay(x: np.ndarray, samples: int) -> np.ndarray:
    """x later by whole samples, the same length."""
    if samples <= 0:
        return x
    out = np.zeros_like(x)
    out[samples:] = x[: len(x) - samples]
    return out


def warp(x: np.ndarray, offset: np.ndarray) -> np.ndarray:
    """Read x at n + offset[n] (a time-varying delay, in samples) by cubic
    Hermite interpolation: a tape transport's wow and flutter."""
    n = len(x)
    pos = np.clip(np.arange(n) + offset, 1.0, n - 3.0)
    i = np.floor(pos).astype(np.int64)
    t = (pos - i)[:, None] if x.ndim == 2 else pos - i
    p0, p1, p2, p3 = x[i - 1], x[i], x[i + 1], x[i + 2]
    return p1 + 0.5 * t * (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)))
