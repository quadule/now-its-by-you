"""A plucked string whose length can change while it rings: slides, bends, a steel's bar, a banjo's twang.

pluck.py's strings hold their pitch: a fixed delay and a fixed fractional
filter, which is exact and cheap. Here the loop is read at a fractional delay
that may move every sample (a cubic Lagrange read of a circular buffer), so a
finger can slide, a bend can rise, a steel bar can glide from one chord to the
next, and a hard pluck's stretch can pull a string sharp before it relaxes.
Each trip round the loop passes the same one-zero loss filter as pluck.py's
(high harmonics die first), and the read delay is set so that the whole loop,
filter and interpolator included, is exactly one period long at the
fundamental: in tune within a fraction of a cent wherever the pitch goes.

The loop's gain may move too (a palm resting on the strings, a finger
lifting, a pick catching a ringing string), and anything may be fed in at any
time: a pick's new excitation into a string that is still sounding (tremolo
picking), a hammer-on's thump. A string rings in two planes, as in pluck.py:
note() runs two loops.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import lfilter

from . import pluck as _pluck


@njit(cache=True)
def _run(x, delay, gain, loss, size):
    """One string plane: y[t] = x[t] + gain[t] * onezero(read(y, t - delay[t])).

    The read is cubic Lagrange over the four samples around t - delay[t]
    (delay must stay above 3 samples and below size - 8)."""
    n = x.shape[0]
    mask = size - 1
    buf = np.zeros(size)
    y = np.zeros(n)
    prev = 0.0
    for t in range(n):
        pos = t - delay[t]
        i = int(np.floor(pos))
        f = pos - i
        a = buf[(i - 1) & mask]
        b = buf[i & mask]
        c = buf[(i + 1) & mask]
        d = buf[(i + 2) & mask]
        r = (-f * (f - 1.0) * (f - 2.0) / 6.0) * a + ((f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0) * b \
            + (-(f + 1.0) * f * (f - 2.0) / 2.0) * c + ((f + 1.0) * f * (f - 1.0) / 6.0) * d
        v = (1.0 - loss) * r + loss * prev
        prev = r
        out = x[t] + gain[t] * v
        buf[t & mask] = out
        y[t] = out
    return y


def _interp_phase_delay(delay: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """Phase delay, at omega, of the cubic Lagrange read at `delay` samples (what _run really delays by)."""
    f = np.mod(-delay, 1.0)  # the read position's fraction past its integer sample
    w = np.stack([-f * (f - 1.0) * (f - 2.0) / 6.0, (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0,
                  -(f + 1.0) * f * (f - 2.0) / 2.0, (f + 1.0) * f * (f - 1.0) / 6.0])
    j = np.arange(-1, 3)[:, None]
    extra = np.sum(w * np.exp(1j * omega[None, :] * j), axis=0) * np.exp(-1j * omega * f)
    return delay - np.angle(extra) / omega


def read_delay(period: np.ndarray, loss: float) -> np.ndarray:
    """The read delay that makes the whole loop (read and loss filter) one `period` long at the fundamental."""
    period = np.asarray(period, dtype=np.float64)
    omega = 2.0 * np.pi / period
    filt = np.arctan2(loss * np.sin(omega), (1.0 - loss) + loss * np.cos(omega)) / omega
    delay = period - filt
    for _ in range(3):
        delay = delay + (period - filt - _interp_phase_delay(delay, omega))
    return delay


def trip(period, sr: int, t60):
    """Loop gain for one trip round a loop `period` samples long that falls 60 dB in t60 seconds."""
    return 10.0 ** (-3.0 * np.asarray(period) / (sr * np.asarray(t60)))


def ring(freq: np.ndarray, x: np.ndarray, sr: int, *, loss: float = 0.3, t60: float | np.ndarray = 2.0,
         gain: np.ndarray | None = None, control: int = 32) -> np.ndarray:
    """One string plane driven by x, its pitch following freq (Hz, one value a sample, as long as x).

    loss is the one-zero loss coefficient (0 keeps every harmonic, 0.5 is the
    classic average); t60 the seconds the fundamental takes to fall 60 dB
    (a number or a track; inf leaves the loss to gain); gain a loop-gain
    track, a factor on each trip (1 leaves it alone: a palm or a finger lowers it). The delay is worked out at a control rate
    of `control` samples and interpolated between."""
    n = len(x)
    freq = np.broadcast_to(np.asarray(freq, dtype=np.float64), (n,))
    period = sr / freq
    if np.ptp(period) < 1e-9:
        delay = np.full(n, read_delay(period[:1], loss)[0])
    else:
        at = np.unique(np.append(np.arange(0, n, control), n - 1))
        delay = np.interp(np.arange(n), at, read_delay(period[at], loss))
    g = trip(period, sr, np.broadcast_to(np.asarray(t60, dtype=np.float64), (n,)))
    if gain is not None:
        g = g * gain
    size = 1 << int(np.ceil(np.log2(delay.max() + 16)))
    return _run(np.ascontiguousarray(x, dtype=np.float64), np.ascontiguousarray(delay),
                np.ascontiguousarray(g, dtype=np.float64), float(loss), size)


def excitation(freq: float, sr: int, rng: np.random.Generator, *, pick: float = 0.15, hardness: float = 0.5,
               vel: float = 0.8) -> np.ndarray:
    """One period of bridge force from a pluck (pluck.py's: a rectangular wave of duty `pick`,
    softened by the finger or pick and roughened), for feeding into ring() at any moment."""
    return _pluck._excitation(sr / freq, pick, hardness, vel, rng, sr)


def note(freq: float, dur: float, sr: int, rng: np.random.Generator, *, cents: np.ndarray | None = None,
         picks=((0.0, 1.0),), vel: float = 0.8, brightness: float = 0.5, decay: float = 3.0, pick: float = 0.15,
         hardness: float = 0.5, planes: float = 0.3, damp: float = 0.08, touch: float = 0.0,
         gain: np.ndarray | None = None, click: bool = True) -> np.ndarray:
    """One string's sound for `dur` seconds and then a `damp`-second stop, like pluck.pluck's,
    but its pitch may move and it may be picked more than once while it rings.

    cents: a track (one value a sample, (dur + damp) * sr long, or shorter and
    then held) of the pitch against freq: a slide, a bend, a bar's glide, a
    twang. picks: (seconds after the start, velocity factor) of each time the
    string is picked; later picks land on the ringing string. gain: an extra
    loop-gain track (a palm mute: under 1). The other arguments are pluck.pluck's."""
    length = int(round((dur + damp) * sr))
    held = min(int(round(dur * sr)), length)
    track = np.zeros(length)
    if cents is not None and len(cents):
        m = min(length, len(cents))
        track[:m] = cents[:m]
        track[m:] = cents[m - 1]
    f = freq * 2.0 ** (track / 1200.0)
    loss = 0.5 - 0.35 * brightness
    t60 = decay * (220.0 / f) ** 0.4
    x = np.zeros(length)
    for at, factor in picks:
        i = int(round(at * sr))
        if i >= length:
            continue
        period = excitation(f[i], sr, rng, pick=pick * rng.uniform(0.9, 1.1), hardness=hardness, vel=vel * factor)
        j = min(length, i + len(period))
        x[i:j] += period[: j - i]
    # the finger lands when the note ends: each plane's loop gain glides in 4 ms to one that loses the
    # string's energy in 80 ms (as pluck.py's does)
    period = sr / f
    split = rng.uniform(0.2, 0.8)  # the two planes sit a fraction of a cent apart, either side of the pitch
    y = np.zeros(length)
    for scale, detune, amount in ((0.8, -split / 2.0, 1.0), (2.0, split / 2.0, planes)):
        g = trip(period, sr, scale * t60)
        if held < length:
            stop = trip(period[held:], sr, 0.08)
            g[held:] = stop + (g[held:] - stop) * np.exp(-np.arange(length - held) / (0.004 * sr))
        if gain is not None:
            g = g * np.broadcast_to(gain, (length,))
        y += ring(f * 2.0 ** (detune / 1200.0), x * amount, sr, loss=loss, t60=np.inf, gain=g)
    if click:
        for at, factor in picks:
            i = int(round(at * sr))
            if i < length:
                y[i:] += _pluck._attack(sr, hardness, vel * factor, length - i, rng)
    if touch > 0.0 and held < length:
        y += _pluck._touch(sr, held, length, freq, touch * vel, rng)
    tail = min(length, int(0.004 * sr))
    y[length - tail:] *= np.linspace(1.0, 0.0, tail)
    return lfilter([1.0, -1.0], [1.0, -0.995], y)  # no DC leaves the string
