"""Struck things: a bank of decaying modes, struck again and again (skins, plates, jingles, boxes).

A struck object rings in its modes, each a damped sinusoid with its own
frequency and decay. A strike excites each mode by an amount that depends on
where it lands and how long the stick stays in contact, so a bank is driven by
a list of hits, each with its own amplitude for every mode: no two hits need
sound alike. The object is (nearly) linear, so a new hit adds to what is still
ringing, with its phase: a roll builds up, a re-strike can partly cancel.

Two things act on all the modes at once, as tracks in time: a bend (tension
modulation: a hard hit stretches a skin and every mode goes sharp in
proportion to how much the skin is moving, then relaxes as it rings down) and
a damping (a hand on the skin, a hi-hat pedal closing, a choke), which each
mode feels by its own weight.

Each mode is a complex phasor, z <- z * exp((-a + i w) / rate) plus the hits,
whose imaginary part is the sound (a sine phase: a struck mode starts from
rest, so nothing clicks). The bank runs block by block, and a mode that has
died away and isn't struck again in a block is skipped; modes low enough run
at a half, a quarter or an eighth of the sample rate and are upsampled, which
makes a few hundred modes affordable for a whole song. The output may be
several channels, each hearing its own mix of the modes (two microphones).
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import firwin, resample_poly

BLOCK = 1024  # samples a block, at the bank's own rate
CONTROL = 32  # samples between updates of the bend and the damping
QUIET = 1e-5  # a mode is dropped once it is this far (-100 dB) under the loudest mode's strike


@njit(cache=True, nogil=True)
def _bank(freqs, decay, phase, pos, amps, mix, bend, damp, dweight, rate, length, floor):
    """The bank at `rate` Hz for `length` samples. freqs (K,) Hz; decay (K,)
    nepers per second; phase (K,) each mode's starting phase; pos (H,) hit
    positions in samples (sorted, fractional); amps (H, K); mix (K, C); bend: a
    per-sample track or an empty array; damp (D, length): D damping tracks
    (D may be 0); dweight (D, K) each mode's share of each; floor: the squared
    level under which a mode is dropped."""
    n_modes = freqs.shape[0]
    n_hits = pos.shape[0]
    channels = mix.shape[1]
    out = np.zeros((length, channels))
    z = np.zeros(n_modes, dtype=np.complex128)
    alive = np.zeros(n_modes, dtype=np.bool_)
    omega = 2.0 * np.pi * freqs / rate
    fixed = np.empty(n_modes, dtype=np.complex128)
    for k in range(n_modes):
        fixed[k] = np.exp(complex(-decay[k] / rate, omega[k]))
    moving = bend.shape[0] > 0 or damp.shape[0] > 0
    first = 0  # the first hit not yet reached
    for b0 in range(0, length, BLOCK):
        b1 = min(length, b0 + BLOCK)
        last = first
        while last < n_hits and pos[last] <= b1 - 1:  # hits landing on a sample of this block
            last += 1
        for k in range(n_modes):
            if not alive[k] and last == first:
                continue
            gain = 0.0
            for c in range(channels):
                gain = max(gain, abs(mix[k, c]))
            if gain == 0.0:
                continue
            zk = z[k]
            m = fixed[k]
            h = first
            for s0 in range(b0, b1, CONTROL):
                s1 = min(b1, s0 + CONTROL)
                if moving:
                    w = omega[k]
                    if bend.shape[0] > 0:
                        w = w * (1.0 + bend[s0])
                    a = decay[k]
                    for d in range(damp.shape[0]):
                        a = a + damp[d, s0] * dweight[d, k]
                    m = np.exp(complex(-a / rate, w))
                for n in range(s0, s1):
                    zk = zk * m
                    while h < last and pos[h] <= n:
                        ahead = n - pos[h]  # the strike came this much before the sample: it has turned a little
                        zk += amps[h, k] * np.exp(complex(-decay[k] * ahead / rate, phase[k] + omega[k] * ahead))
                        h += 1
                    v = zk.imag
                    for c in range(channels):
                        out[n, c] += v * mix[k, c]
            z[k] = zk
            alive[k] = (zk.real * zk.real + zk.imag * zk.imag) * gain * gain > floor
            if not alive[k]:
                z[k] = 0.0
        first = last
    return out


# The lowpass for each doubling of the rate: flat to 0.8 of the lower rate's Nyquist, about 75 dB down from 1.2.
# It is a half-band filter (every other tap zero but the middle one), so a doubled signal keeps its old samples
# and only the new ones between them are filtered: 24 taps for every other sample.
HALFBAND = firwin(47, 0.5, window=("kaiser", 7.5))
_ODD = np.ascontiguousarray(2.0 * HALFBAND[0::2][::-1])  # the taps between old samples, reversed for the sum below
_MIDDLE = 2.0 * HALFBAND[23]


@njit(cache=True, nogil=True)
def _up2(x, taps, middle):
    """One channel at twice the rate, as resample_poly(x, 2, 1) with HALFBAND would give it."""
    n = x.shape[0]
    m = taps.shape[0]
    half = m // 2
    padded = np.zeros(n + m)
    padded[half - 1: half - 1 + n] = x
    y = np.empty(2 * n)
    for i in range(n):
        y[2 * i] = middle * x[i]
        acc = 0.0
        for t in range(m):
            acc += taps[t] * padded[i + t]
        y[2 * i + 1] = acc
    return y


def _double(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=np.float64)
    if y.ndim == 1:
        return _up2(np.ascontiguousarray(y), _ODD, _MIDDLE)
    return np.stack([_up2(np.ascontiguousarray(y[:, c]), _ODD, _MIDDLE) for c in range(y.shape[1])], axis=1)


def _factor(freq: float, sr: int) -> int:
    for factor, top in ((8, 0.05), (4, 0.1), (2, 0.2)):
        if freq < top * sr:
            return factor
    return 1


def ring(freqs, t60s, times, amps, sr: int, length: int, *, mix=None, bend=None, damp=None, dweight=None,
         damp2=None, dweight2=None, phase=None, multirate: bool = True) -> np.ndarray:
    """Modes at `freqs` Hz, each falling 60 dB in its t60 seconds, struck at
    `times` (seconds) with amps[h, k] for hit h and mode k, rendered
    `length` samples long.

    mix: (K, C) how much of each mode each of C channels hears (default one
    channel hearing all alike); returns (length,) for one channel, else
    (length, C). bend: a per-sample track of the relative pitch offset every
    mode shares (0.02 is 2% sharp). damp: a per-sample track of extra decay,
    in nepers per second, that mode k feels times dweight[k] (default 1);
    damp2 and dweight2 a second such track (a hand's, beside a cymbal's own
    loud-phase drain). phase: each mode's starting phase (default 0, a sine:
    no click)."""
    freqs = np.asarray(freqs, dtype=np.float64)
    k = len(freqs)
    t60s = np.broadcast_to(np.asarray(t60s, dtype=np.float64), (k,))
    times = np.asarray(times, dtype=np.float64)
    amps = np.asarray(amps, dtype=np.float64).reshape(len(times), k)
    order = np.argsort(times, kind="stable")
    times, amps = times[order], amps[order]
    mono = mix is None
    mix = np.ones((k, 1)) if mono else np.asarray(mix, dtype=np.float64).reshape(k, -1)
    phase = np.zeros(k) if phase is None else np.broadcast_to(np.asarray(phase, dtype=np.float64), (k,))
    tracks, weights = [], []
    for track_, weight in ((damp, dweight), (damp2, dweight2)):
        if track_ is not None:
            tracks.append(np.asarray(track_, dtype=np.float64))
            weights.append(np.ones(k) if weight is None else np.broadcast_to(np.asarray(weight, dtype=np.float64), (k,)))
    out = np.zeros((length, mix.shape[1]))
    if k == 0 or len(times) == 0 or length == 0:
        return out[:, 0] if mono else out
    decay = 6.907755 / t60s
    loudest = np.max(np.abs(amps), axis=0) * np.max(np.abs(mix), axis=1)
    floor = float((QUIET * loudest.max()) ** 2)
    audible = (freqs < 0.47 * sr) & (freqs > 0.0) & (loudest > 0.0)
    factors = np.array([_factor(f, sr) if multirate else 1 for f in freqs])
    # The slowest modes first; their sum is doubled in rate and joined by the next, and so on: one short
    # filter a doubling, whatever the number of groups or channels.
    base = -(-length // 8) + 16
    acc, at = None, 8
    for factor in (8, 4, 2, 1):
        while acc is not None and at > factor:
            acc, at = _double(acc), at // 2
        sel = np.flatnonzero(audible & (factors == factor))
        if not len(sel):
            continue
        rate = sr / factor
        n = base * (8 // factor)
        track = lambda x: np.zeros(0) if x is None else np.ascontiguousarray(  # noqa: E731
            np.pad(np.asarray(x, dtype=np.float64)[::factor], (0, n)))[:n]
        damps = np.stack([track(t) for t in tracks]) if tracks else np.zeros((0, n))
        dweights = np.stack([w[sel] for w in weights]) if weights else np.zeros((0, len(sel)))
        y = _bank(freqs[sel], decay[sel], np.ascontiguousarray(phase[sel]), times * rate,
                  np.ascontiguousarray(amps[:, sel]), np.ascontiguousarray(mix[sel]), track(bend),
                  np.ascontiguousarray(damps), np.ascontiguousarray(dweights), float(rate), n, floor)
        acc, at = (y if acc is None else acc + y), factor
    while acc is not None and at > 1:
        acc, at = _double(acc), at // 2
    if acc is not None:
        out += acc[:length]
    return out[:, 0] if mono else out
