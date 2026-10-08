"""Modes: a struck or plucked thing as a bank of damped resonances.

A piano string, a marimba bar, a tine or a comb's tooth rings in modes: each
a frequency, a decay and an amplitude. Whatever strikes it (a hammer, a
mallet, a pin) pushes for a millisecond or a few; each mode takes up that
push by how well the push's spectrum reaches its frequency and how far the
strike is from the mode's nodes, then rings on by itself. A mode here is a
complex one-pole resonator, z[t] = m z[t-1] + g F[t], with |m| its decay and
arg(m) its frequency; the sound is the real part of the sum. Driven by the
contact's force, sample by sample, every mode builds up as it really would,
so an onset never clicks.

A damper (a felt landing on a string or a bar) raises each mode's decay rate
from `damp_at` on, gliding over `ramp` samples as the felt settles. A mode
stops being computed once it has fallen below `floor`.

ring() renders one note's modes into a (channels, samples) buffer at a start
sample, each channel with its own gain (a note's place in the stereo image).
Samples run in the outer loop and modes in the inner one, so the modes of a
note are summed in registers and dropped from the loop as they die.
"""

from __future__ import annotations

import numpy as np
from numba import njit

LN1000 = 6.907755278982137  # a T60 is the time to fall by a factor of 1000


@njit(cache=True, nogil=True)
def ring(out, start, force, freqs, gain_re, gain_im, t60, t60_damped, damp_at, ramp, gains, sr, floor):
    """Add one note's modes into out[channel, start:], each channel scaled by gains[channel].

    force: the contact force, one value a sample from `start` (may be empty: then
    gain_re/gain_im are the modes' initial complex amplitudes instead);
    freqs, t60 (s): each mode's frequency and decay; t60_damped (s): its decay once
    the damper is down; damp_at: samples after start where the damper lands (-1:
    never); ramp: samples the damper takes to settle; floor: a mode is dropped once
    its magnitude falls below it (after the force has ended). Modes at or above
    0.49 sr are skipped. Returns the number of samples written after start."""
    channels, length = out.shape
    n = freqs.shape[0]
    if start >= length or n == 0:
        return 0
    span = length - start
    # compact per-mode state
    zr = np.zeros(n)
    zi = np.zeros(n)
    cw = np.zeros(n)
    sw = np.zeros(n)
    r0 = np.zeros(n)
    r1 = np.zeros(n)
    gr = np.zeros(n)
    gi = np.zeros(n)
    mr = np.zeros(n)
    mi = np.zeros(n)
    if force.shape[0] == 0:  # initial amplitudes: a unit push on the first sample
        force = np.ones(1)
    driven = force.shape[0]
    count = 0
    for k in range(n):
        if freqs[k] <= 0.0 or freqs[k] >= 0.49 * sr:
            continue
        w = 2.0 * np.pi * freqs[k] / sr
        cw[count] = np.cos(w)
        sw[count] = np.sin(w)
        r0[count] = np.exp(-LN1000 / (max(t60[k], 1e-4) * sr))
        r1[count] = np.exp(-LN1000 / (max(t60_damped[k], 1e-4) * sr))
        gr[count] = gain_re[k]
        gi[count] = gain_im[k]
        count += 1
    block = 32
    i = 0
    written = 0
    while i < span and count > 0:
        # this block's multipliers: the damper glides each mode's decay toward its damped rate
        for j in range(count):
            r = r0[j]
            if damp_at >= 0 and i + block // 2 >= damp_at:
                u = (i + block // 2 - damp_at) / max(ramp, 1.0)
                if u > 1.0:
                    u = 1.0
                r = r0[j] ** (1.0 - u) * r1[j] ** u
            mr[j] = r * cw[j]
            mi[j] = r * sw[j]
        end = min(i + block, span)
        for t in range(i, end):
            s = 0.0
            if t < driven:
                f = force[t]
                for j in range(count):
                    a = zr[j] * mr[j] - zi[j] * mi[j] + gr[j] * f
                    b = zr[j] * mi[j] + zi[j] * mr[j] + gi[j] * f
                    zr[j] = a
                    zi[j] = b
                    s += a
            else:
                for j in range(count):
                    a = zr[j] * mr[j] - zi[j] * mi[j]
                    b = zr[j] * mi[j] + zi[j] * mr[j]
                    zr[j] = a
                    zi[j] = b
                    s += a
            for c in range(channels):
                out[c, start + t] += gains[c] * s
        written = end
        i = end
        if i >= driven:  # drop the modes that have died away
            j = 0
            while j < count:
                if zr[j] * zr[j] + zi[j] * zi[j] < floor * floor:
                    last = count - 1
                    zr[j] = zr[last]
                    zi[j] = zi[last]
                    cw[j] = cw[last]
                    sw[j] = sw[last]
                    r0[j] = r0[last]
                    r1[j] = r1[last]
                    gr[j] = gr[last]
                    gi[j] = gi[last]
                    count -= 1
                else:
                    j += 1
    return written
