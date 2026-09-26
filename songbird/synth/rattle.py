"""What the hand percussion shares: how a stroke is levelled, how a contact
filters it, and the things in it that rattle.

Every stroke of hand percussion is levelled as the frame drum's are (drum.py):
by the loudness of its first 30 ms, not its peak, which a click or a crack
would set. Here the loudness is K-weighted (ITU-R BS.1770, as the stems are
measured), so a bright clap and a dull stomp of the same velocity sit at the
same level, and a maker's brighter shaker isn't a louder one. Struck modes
are levelled from their amplitudes (each mode's energy over the window, in
closed form), without rendering the stroke first.

A contact of duration tau (a palm, a heel, a fingertip, a jingle meeting its
pair) passes what it strikes as a half-sine force does: flat below 1/(2 tau),
falling 12 dB an octave above. A harder stroke is a shorter contact, so a
brighter one (Fletcher and Rossing, The Physics of Musical Instruments, 2nd
ed., 1998, section 2.18; Rossing, Science of Percussion Instruments, 2000).

The rattles (a shaker's beads, a tambourine's jingles, a cajon's snares) are
collisions: many small impacts whose rate and strength follow the energy put
in (Cook, "Physically informed sonic modeling (PhISM): synthesis of
percussive sounds", Computer Music Journal 21(3), 1997). Their noise comes
from a small generator of their own (xorshift), seeded from the part's
random stream, so a three-minute part needs no noise buffer and replays
exactly.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import freqz, lfilter

from .master import _k_weighting

WINDOW = 0.03  # seconds of a stroke that set its level, as the frame drum's


def vel_gain(vel) -> np.ndarray | float:
    """How much louder a harder stroke is, as the frame drum plays: 7 dB from
    vel 0.6 to 1, 16 dB from 0.3."""
    v = np.clip(vel, 0.0, 1.0)
    return v * (0.35 + 0.65 * v)


def contact(freqs, tau) -> np.ndarray:
    """What a contact lasting tau seconds passes at freqs: a half-sine force's
    envelope, flat below 1/(2 tau), -12 dB an octave above."""
    return 1.0 / (1.0 + (2.0 * np.asarray(freqs) * tau) ** 2)


@lru_cache(maxsize=4)
def _kw(sr: int):
    return tuple((np.asarray(b), np.asarray(a)) for b, a in _k_weighting(sr))


def k_power(freqs, sr: int) -> np.ndarray:
    """The K-weighting's power gain at freqs (BS.1770: +4 dB above about 2
    kHz, falling away under 60 Hz)."""
    freqs = np.atleast_1d(np.asarray(freqs, dtype=np.float64))
    g = np.ones(len(freqs))
    for b, a in _kw(sr):
        _, h = freqz(b, a, worN=np.minimum(freqs, 0.4999 * sr), fs=sr)
        g = g * np.abs(h) ** 2
    return g


def early_power(y: np.ndarray, sr: int, window: float = WINDOW) -> float:
    """K-weighted mean square of a stroke's first `window` seconds (channels summed)."""
    x = np.asarray(y[: max(1, int(window * sr))], dtype=np.float64)
    for b, a in _kw(sr):
        x = lfilter(b, a, x, axis=0)
    return float(np.sum(x**2) / max(1, int(window * sr)))


def modal_weights(freqs, t60s, sr: int, window: float = WINDOW, weight=None) -> np.ndarray:
    """What each struck mode, struck with unit amplitude (a sine starting at
    the strike, falling 60 dB in its t60), adds to the K-weighted mean square
    over the stroke's first `window` seconds. weight[k]: how much of mode k
    the listener hears (its mix). A stroke's early power is then amps**2 @
    these, as if its modes didn't beat."""
    freqs = np.asarray(freqs, dtype=np.float64)
    alpha = 6.907755 / np.asarray(t60s, dtype=np.float64)
    w = 2.0 * np.pi * freqs
    # the integral of exp(-2 a t) sin^2(w t) from 0 to T
    decay = (1.0 - np.exp(-2.0 * alpha * window)) / (2.0 * alpha)
    z = 2.0 * alpha - 2j * w
    beat = np.real((1.0 - np.exp(-z * window)) / z)
    energy = 0.5 * (decay - beat)
    return k_power(freqs, sr) * energy * (1.0 if weight is None else np.asarray(weight) ** 2) / window


def modal_power(amps: np.ndarray, freqs, t60s, sr: int, window: float = WINDOW, weight=None) -> np.ndarray:
    """Each hit's early power from its mode amplitudes amps[h, k] (see modal_weights)."""
    return np.abs(np.asarray(amps)) ** 2 @ modal_weights(freqs, t60s, sr, window, weight)


def burst(rng: np.random.Generator, tau: float, sr: int, n: int | None = None) -> np.ndarray:
    """A burst of noise falling e-fold every tau seconds, `n` samples (default 7 tau)."""
    n = int(7.0 * tau * sr) + 1 if n is None else n
    return rng.standard_normal(n) * np.exp(-np.arange(n) / (tau * sr))


def pan(position: float) -> np.ndarray:
    """Constant-power gains (left, right) for a source at position -1..1, as instruments.place() pans."""
    theta = (position + 1.0) * np.pi / 4.0
    return np.array([np.cos(theta), np.sin(theta)]) * np.sqrt(2.0)


def onsets(rng: np.random.Generator, habits, jitter: float) -> np.ndarray:
    """When each of a group plays a note, in seconds after it: each person's habit (early or late) and a
    scatter of their own, the whole shifted so the first lands on the note. Nothing sounds before a
    note's time: the notes carry the part's own timing."""
    t = np.asarray(habits, dtype=np.float64) + rng.normal(0.0, jitter, len(habits))
    return t - t.min() if len(t) else t


def late(rng: np.random.Generator, jitter: float) -> float:
    """A single player's wobble about a note's time, never early (see onsets)."""
    return abs(float(rng.normal(0.0, jitter)))


def add(out: np.ndarray, y: np.ndarray, start: int) -> None:
    """Lay y onto out from sample `start`, clipped to out's length (either may start before 0)."""
    if start >= len(out):
        return
    lo = max(0, -start)
    hi = min(len(y), len(out) - start)
    if hi > lo:
        out[start + lo: start + hi] += y[lo:hi]


# --- the noise the rattles are made of -----------------------------------------------------


@njit(cache=True)
def _next(state):
    """xorshift64*: the next state and a uniform number in [0, 1)."""
    x = state
    x ^= x >> np.uint64(12)
    x ^= x << np.uint64(25)
    x ^= x >> np.uint64(27)
    out = (x * np.uint64(2685821657736338717)) >> np.uint64(11)
    return x, float(out) * (1.0 / 9007199254740992.0)


def seed_of(rng: np.random.Generator) -> np.uint64:
    """A nonzero xorshift state drawn from a numpy stream."""
    return np.uint64(int(rng.integers(1, 1 << 62)) | 1)


# --- particles: beads in a shell, jingles on their pins ------------------------------------------


HOP = 32  # samples between values of the energy track


@njit(cache=True)
def _collide(energy, hop, rate, gamma, decay, lp_lo, lp_hi, sb, sa1, sa2, sgain, click,
             ma1, ma2, mgain, mtilt, mstart, kick, state, out):
    """Collisions driven by an energy track, sample by sample (PhISEM).

    energy (C,): the particles' kinetic energy every `hop` samples, 0..1. At
    energy e a collision happens in a sample with probability rate*sqrt(e)
    (the particles move faster, and more of them move), with strength
    sqrt(e)*u**gamma (u uniform): each adds to a noise level that falls by
    `decay` a sample (the impact's own click, a fraction of a millisecond).
    The noise, lowpassed at lp_lo..lp_hi (cycles a sample, rising with the
    energy: harder impacts are brighter), rings the shell's two-pole
    resonances (sb, sa1, sa2, sgain; zeros at DC and Nyquist) and is heard
    directly (click). Modes (ma1, ma2, mgain), grouped by object (mstart:
    object j owns modes mstart[j]..mstart[j+1]), are each kicked by a
    collision on their object (one object a collision, chosen at random) with
    a random share of kick*strength, times sqrt(e)**mtilt[k]: a softer impact
    is a longer contact, which reaches the higher modes less. Jingles, each
    pair its own modes. Adds to out; returns the generator's state."""
    n = out.shape[0]
    nb = sa1.shape[0]
    nk = ma1.shape[0]
    objects = mstart.shape[0] - 1
    s1 = np.zeros(nb)
    s2 = np.zeros(nb)
    m1 = np.zeros(nk)
    m2 = np.zeros(nk)
    y = np.zeros(nk)
    level = 0.0
    lp = 0.0
    lp1 = 0.0
    lp2 = 0.0
    last = 0.0
    for c in range(energy.shape[0]):
        i0 = c * hop
        if i0 >= n:
            break
        i1 = min(n, i0 + hop)
        e = energy[c]
        if e <= 1e-9 and level < 1e-12 and last < 1e-9:
            if lp != 0.0 or last != 0.0:
                s1[:] = 0.0
                s2[:] = 0.0
                m1[:] = 0.0
                m2[:] = 0.0
                lp = 0.0
                lp1 = 0.0
                lp2 = 0.0
                last = 0.0
            continue
        root = np.sqrt(max(e, 0.0))
        p = min(1.0, rate * root)
        cut = lp_lo + (lp_hi - lp_lo) * root
        a_lp = np.exp(-2.0 * np.pi * cut)
        peak = 0.0
        for i in range(i0, i1):
            state, u = _next(state)
            hit = u < p
            strength = 0.0
            if hit:
                state, v = _next(state)
                strength = root * v**gamma
                level += strength
            state, w = _next(state)
            x = level * (2.0 * w - 1.0)
            level *= decay
            lp = (1.0 - a_lp) * x + a_lp * lp
            sound = click * lp
            for b in range(nb):
                yb = sb[b] * (lp - lp2) + sa1[b] * s1[b] - sa2[b] * s2[b]
                s2[b] = s1[b]
                s1[b] = yb
                sound += sgain[b] * yb
            lp2 = lp1
            lp1 = lp
            if nk > 0:
                for k in range(nk):
                    y[k] = ma1[k] * m1[k] - ma2[k] * m2[k]
                if hit and objects > 0:
                    state, w = _next(state)
                    j = min(objects - 1, int(w * objects))
                    for k in range(mstart[j], mstart[j + 1]):
                        state, w = _next(state)
                        y[k] += kick * strength * (2.0 * w - 1.0) * root ** mtilt[k]
                for k in range(nk):
                    sound += mgain[k] * y[k]
                    m2[k] = m1[k]
                    m1[k] = y[k]
            out[i] += sound
            peak = max(peak, abs(sound))
        last = peak
    return state


def two_pole(freqs, qs, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Coefficients (b, a1, a2) of two-pole resonances with zeros at DC and Nyquist, unity at their peaks:
    y[n] = b (x[n] - x[n-2]) + a1 y[n-1] - a2 y[n-2]."""
    freqs = np.minimum(np.asarray(freqs, dtype=np.float64), 0.45 * sr)
    r = np.exp(-np.pi * freqs / np.asarray(qs, dtype=np.float64) / sr)
    return 0.5 * (1.0 - r * r), 2.0 * r * np.cos(2.0 * np.pi * freqs / sr), r * r


def ringing(freqs, t60s, sr: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Coefficients (a1, a2) of free two-pole modes (y[n] = a1 y[n-1] - a2 y[n-2] + kick), and the gain
    that makes a unit kick ring at unit amplitude."""
    freqs = np.asarray(freqs, dtype=np.float64)
    r = np.exp(-6.907755 / (np.asarray(t60s, dtype=np.float64) * sr))
    theta = 2.0 * np.pi * freqs / sr
    return 2.0 * r * np.cos(theta), r * r, np.sin(theta)


def collide(energy: np.ndarray, length: int, rng: np.random.Generator, *, rate: float, gamma: float, click_ms: float,
            bright: tuple[float, float], shell: tuple = ((), (), ()), direct: float = 0.0,
            modes: tuple = ((), (), (), (), [0]), kick: float = 0.0, sr: int = 44100) -> np.ndarray:
    """A rattle's sound, mono, `length` samples, from its energy track (one value every HOP samples).

    rate: collisions a second at full energy; gamma: how the impacts' strengths spread (1 uniform, more:
    mostly small); click_ms: an impact's click, e-fold time; bright: the clicks' lowpass (Hz) at no energy
    and at full; shell: (freqs, qs, gains) of the resonances the clicks ring; direct: the clicks heard as
    they are; modes: (freqs, t60s, gains, tilts, starts), the modes of each object (object j owns modes
    starts[j]..starts[j+1]), kicked by kick times an impact's strength (times sqrt(energy)**tilt)."""
    out = np.zeros(length)
    freqs, qs, gains = (np.asarray(v, dtype=np.float64) for v in shell)
    sb, sa1, sa2 = two_pole(freqs, qs, sr) if len(freqs) else (np.zeros(0),) * 3
    mf, mt, mg, tilt, starts = modes
    mf = np.asarray(mf, dtype=np.float64)
    ok = mf < 0.45 * sr
    if len(mf):
        ma1, ma2, unit = ringing(mf, mt, sr)
        mg = np.where(ok, np.asarray(mg, dtype=np.float64) * unit, 0.0)
    else:
        ma1 = ma2 = mg = tilt = np.zeros(0)
    _collide(np.ascontiguousarray(energy, dtype=np.float64), HOP, rate / sr, gamma,
             float(np.exp(-1.0 / (click_ms * 1e-3 * sr))), bright[0] / sr, min(bright[1], 0.45 * sr) / sr,
             sb, sa1, sa2, np.ascontiguousarray(gains), direct, ma1, ma2, np.ascontiguousarray(mg),
             np.ascontiguousarray(tilt, dtype=np.float64), np.asarray(starts, dtype=np.int64), kick, seed_of(rng), out)
    return out
