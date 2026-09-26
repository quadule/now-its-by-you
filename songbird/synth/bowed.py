"""Bowed string: a digital waveguide driven by bow friction (the fiddle).

The string is two delay lines meeting at the bow: one the round trip from
the bow to the bridge and back, one from the bow to the stopping finger and
back. Velocity waves arriving at the bow add up to the string's velocity
there; the bow hair grips the string while the two move nearly together and
lets it slip when they don't (a friction curve, after Smith and the STK's bow
table). Stick, slip, stick again: the Helmholtz motion, a corner running round
the string once a period, emerges from that alone, and so do the scratch of a
new stroke, the catch after a bow change, and the free ring when the bow
lifts. The bridge end loses a little of each trip through a one-pole filter
(high harmonics lose most); what arrives there is the force that drives the
body.

A part is played as one continuous line: the finger's place (the pitch, with
vibrato and slides), the bow's speed and direction, and its weight on the
string are control tracks, one value a sample, drawn from the notes.
"""

from __future__ import annotations

import numpy as np
from numba import njit

from ..theory import midi_to_hz


@njit(cache=True)
def _read(buf, pos, delay):
    """Cubic Lagrange read `delay` samples behind write position `pos` in a circular buffer."""
    size = buf.shape[0]
    x = pos - delay
    i = int(np.floor(x))
    f = x - i
    a = buf[(i - 1) % size]
    b = buf[i % size]
    c = buf[(i + 1) % size]
    d = buf[(i + 2) % size]
    # Lagrange weights for points at -1, 0, 1, 2 evaluated at f
    wa = -f * (f - 1.0) * (f - 2.0) / 6.0
    wb = (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0
    wc = -(f + 1.0) * f * (f - 2.0) / 2.0
    wd = (f + 1.0) * f * (f - 1.0) / 6.0
    return wa * a + wb * b + wc * c + wd * d


@njit(cache=True)
def run(period, bridge_len, bow_v, grip, noise, pole, gain):
    """The string's bridge force, sample by sample.

    period: loop length in samples (the pitch, after the filter's delay is
    taken off); bridge_len: bow-to-bridge round trip in samples; bow_v: bow
    velocity (signed; 0 lifts the bow); grip: the widest velocity difference
    the hair still holds the string through (the bow's weight: it must grow
    with the bow's speed, or the string slips twice a period and jumps to its
    octave); noise: hair and rosin noise added to the velocity difference;
    pole, gain: the bridge's one-pole loss filter.
    """
    n = period.shape[0]
    size = 4096
    to_nut = np.zeros(size)
    to_bridge = np.zeros(size)
    out = np.zeros(n)
    lp = 0.0
    for t in range(n):
        lb = bridge_len[t]
        ln = period[t] - lb
        arriving = _read(to_bridge, t, lb)  # at the bridge
        lp = (1.0 - pole) * arriving + pole * lp
        from_bridge = -gain * lp
        from_nut = -_read(to_nut, t, ln)
        v_string = from_bridge + from_nut
        v = 0.0
        if bow_v[t] != 0.0:
            dv = bow_v[t] - v_string + noise[t]
            # the STK bow table: 1 (stick) inside the grip, falling as the string slips
            r = np.abs(0.25 * dv / grip[t]) + 0.75
            r = r**-4.0
            if r > 1.0:
                r = 1.0
            v = dv * r
        to_nut[t % size] = from_bridge + v
        to_bridge[t % size] = from_nut + v
        out[t] = arriving
    return out


@njit(cache=True)
def _read_masked(buf, pos, delay):
    """_read for a buffer whose length is a power of two (a mask instead of a modulo: the same values, quicker)."""
    mask = buf.shape[0] - 1
    x = pos - delay
    i = int(np.floor(x))
    f = x - i
    a = buf[(i - 1) & mask]
    b = buf[i & mask]
    c = buf[(i + 1) & mask]
    d = buf[(i + 2) & mask]
    wa = -f * (f - 1.0) * (f - 2.0) / 6.0
    wb = (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0
    wc = -(f + 1.0) * f * (f - 2.0) / 2.0
    wd = (f + 1.0) * f * (f - 1.0) / 6.0
    return wa * a + wb * b + wc * c + wd * d


@njit(cache=True)
def run_primed(period, bridge_len, bow_v, grip, noise, pole, gain, at, velocity):
    """run(), but at each sample at[k] (ascending) the string is set moving as
    in Helmholtz motion for bow velocity velocity[k]: a player's clean attack.

    Helmholtz motion is a free vibration of the string (the bow only makes up
    its losses), so it can be laid down whole: the waves arriving at the bow
    from the bridge side and from the nut side are sawtooths V/beta high, the
    corner leaving the bow toward the nut just as the stick begins. Left to the
    friction alone the motion takes 15 to 40 periods to organize itself, which
    on a violin's short periods is a fine détaché but on a cello's C string is
    a quarter of a second (a player's is under a tenth: Guettler and Askenfelt,
    JASA 1997). What was on the string before is replaced.

    pole here is a track, one value a sample: how round the corner is kept
    (the bridge's loss, standing in for the bow's own rounding: a heavy bow
    near the bridge keeps it sharp, a light one over the fingerboard rounds it).
    The caller keeps the pitch by taking pole/(1 - pole) off the period.
    """
    n = period.shape[0]
    size = 4096
    mask = size - 1
    to_nut = np.zeros(size)
    to_bridge = np.zeros(size)
    out = np.zeros(n)
    lp = 0.0
    e = 0
    for t in range(n):
        lb = bridge_len[t]
        ln = period[t] - lb
        pl = pole[t]
        while e < at.shape[0] and at[e] < t:
            e += 1
        if e < at.shape[0] and at[e] == t:
            p = period[t] + pl / (1.0 - pl)
            height = velocity[e] * p / lb
            # from_bridge(t + s) = height (1/2 - frac(s / p)), from_nut(t + s) = height (frac((s - ln) / p) - 1/2):
            # write into each line what its reads will find over the next trip
            for j in range(t - int(lb) - 3, t):
                x = (j + lb - t) / p
                to_bridge[j & mask] = -height * (0.5 - (x - np.floor(x))) / gain
            for j in range(t - int(ln) - 3, t):
                x = (j - t) / p
                to_nut[j & mask] = -height * ((x - np.floor(x)) - 0.5)
            lp = -0.5 * height / gain
            e += 1
        arriving = _read_masked(to_bridge, t, lb)
        lp = (1.0 - pl) * arriving + pl * lp
        from_bridge = -gain * lp
        from_nut = -_read_masked(to_nut, t, ln)
        v_string = from_bridge + from_nut
        v = 0.0
        if bow_v[t] != 0.0:
            dv = bow_v[t] - v_string + noise[t]
            r = np.abs(0.25 * dv / grip[t]) + 0.75
            r = r * r
            r = 1.0 / (r * r)
            if r > 1.0:
                r = 1.0
            v = dv * r
        to_nut[t & mask] = from_bridge + v
        to_bridge[t & mask] = from_nut + v
        out[t] = arriving
    return out


def tracks(notes, sr: int, length: int, rng: np.random.Generator, *, vibrato: float = 18.0,
           rate: float = 5.6, wear: float = 0.0, rise: float = 0.03, turn: float = 0.01, bite: float = 0.06,
           catch: float = 0.3, slide: tuple[float, float] = (-150.0, 0.09), bowing=None, intonation: float = 0.04):
    """Control tracks for a bowed part from its notes (each with start, dur,
    pitch, vel and art): the period, the bow's velocity and force, and where
    the bow sits. art "slur" continues the previous note's bow; "slide" comes
    up into the note from a tone below; anything else is a new stroke, the bow
    changing direction.

    The defaults are a violinist's: a fresh stroke's bow gathers speed in
    `rise` seconds (twice that when played softly), a bow change turns round in
    `turn`; the stroke starts with extra weight that eases off over `bite`
    seconds, and the hair's catch is `catch` of a Helmholtz corner (half that at
    a bow change); a slide comes up `slide` = (cents, seconds), or with cents
    None slides from the note before when no rest parts them. bowing, if
    given, is a function of a note returning (bow position as a fraction of the
    string from the bridge, its spread from note to note, a factor on the bow's
    speed, a factor on its weight): the fiddle's is (0.085, 0.02, 1, 1).
    intonation is the spread (semitones) of the player's own tuning from note
    to note on a new instrument; wear adds to it."""
    period = np.full(length, sr / 196.0)
    bridge_len = np.full(length, 0.1 * sr / 196.0)
    bow_v = np.zeros(length)
    bow_f = np.zeros(length)
    jolt = np.zeros(length)
    direction = 1.0
    last_end = -1.0
    last_pitch = None
    ordered = [n for n in sorted(notes, key=lambda n: n.start) if n.dur * sr >= 16]
    for k, note in enumerate(ordered):
        i0 = max(0, int(round(note.start * sr)))
        i1 = min(length, int(round((note.start + note.dur) * sr)))
        if i1 - i0 < 16:
            continue
        m = i1 - i0
        t = np.arange(m) / sr
        pitch = note.pitch + rng.normal(0.0, intonation + 0.08 * wear)  # a player's own intonation
        cents = np.zeros(m)
        joined = last_pitch is not None and note.start - last_end < 0.02  # no rest before it
        legato = note.art == "slur" and joined
        after = ordered[k + 1] if k + 1 < len(ordered) else None
        if after is not None and after.start - (note.start + note.dur) >= 0.02:
            after = None  # a rest follows
        if legato:  # the finger moves; the bow carries on
            glide = min(m, int(0.012 * sr))
            cents[:glide] = (last_pitch - pitch) * 100.0 * (1.0 - np.linspace(0.0, 1.0, glide)) ** 2
        elif note.art == "slide":
            glide = min(m, int(slide[1] * sr))
            depth = slide[0]
            if depth is None:  # a shift: the finger slides from the note before, or from a tone and a half below
                depth = (last_pitch - pitch) * 100.0 if joined else -150.0
            cents[:glide] = depth * (1.0 - np.linspace(0.0, 1.0, glide)) ** 1.5
        if note.dur > 0.35 and vibrato > 0:
            onset = min(0.25, 0.4 * note.dur)
            depth = vibrato * (0.8 + 0.4 * rng.random()) * np.clip((t - onset) / 0.25, 0.0, 1.0)
            wobble = rate * (1.0 + 0.04 * np.sin(2 * np.pi * 0.7 * t + rng.uniform(0, 6.28)))
            cents += depth * np.sin(2 * np.pi * np.cumsum(wobble) / sr + rng.uniform(0, 6.28))
        freq = midi_to_hz(pitch) * 2.0 ** (cents / 1200.0)
        p = sr / freq
        # The loss filter delays the loop by about pole/(1-pole) samples, and the
        # slip starts a little before the corner's middle arrives (it is
        # rounded), which shortens each period by about 0.28 samples: measured
        # across G3 to B5 and both ends of the dynamics.
        period[i0:i1] = p - _FILTER_DELAY + _SLIP_EARLY
        where, spread, faster, heavier = (0.085, 0.02, 1.0, 1.0) if bowing is None else bowing(note)
        beta = max(where + spread * rng.standard_normal(), 3.5 / p.min())
        bridge_len[i0:i1] = beta * p.mean()
        # The bow: speed and weight rise together at a stroke's start (from
        # the string, after a rest; through a quick reversal, at a bow change);
        # a slurred note keeps the stroke going; at a stroke's end the bow
        # turns round quickly if another stroke follows, or eases and lifts
        # before a rest.
        speed = (0.02 + 0.25 * note.vel) * faster
        envelope = np.ones(m)
        if not legato:
            direction = -direction
            gather = min(m, int((turn if joined else rise + rise * (1.0 - note.vel)) * sr))
            envelope[:gather] = np.linspace(0.0, 1.0, gather) ** 0.7
        if after is None:
            fall = min(m, int(0.03 * sr))
            envelope[-fall:] *= np.linspace(1.0, 0.25, fall)
        elif after.art != "slur":
            fall = min(m, int(0.01 * sr))
            envelope[-fall:] *= np.linspace(1.0, 0.0, fall)
        if note.art == "swell":
            envelope *= 0.7 + 0.3 * np.sin(np.pi * np.linspace(0.0, 1.0, m))
        wander = 1.0 + 0.04 * np.convolve(rng.standard_normal(m // 256 + 2), np.ones(2) / 2, mode="same")
        wander = np.interp(np.arange(m), np.linspace(0, m, len(wander)), wander)
        bow_v[i0:i1] = direction * speed * envelope * wander
        # Weight in proportion to speed, inside Schelleng's window for this
        # bow position; a worn player presses a little harder (grittier).
        grip = speed * (1.1 + 0.6 * note.vel + 0.4 * wear) * np.ones(m) * heavier
        if not legato:  # a stroke starts with a little extra bite, so the string speaks at once
            eases = min(m, int(bite * sr))
            grip[:eases] *= 1.0 + 0.8 * (1.0 - np.linspace(0.0, 1.0, eases))
            # and the hair catches the string as it lands: a jolt, a third of a Helmholtz corner, one trip
            # to the bridge wide, which the stick and slip lock onto (the build-up drops from 60-80 periods to 15-20)
            width = max(1, int(round(beta * p.mean())))
            jolt[i0 : i0 + width] += direction * (0.5 * catch if joined else catch) * speed / beta
        bow_f[i0:i1] = grip
        last_end = note.start + note.dur
        last_pitch = pitch
    # Between notes the bow is off the string; hold the finger where it was so
    # the free string rings on at its last pitch.
    playing = bow_v != 0.0
    if playing.any():
        idx = np.maximum.accumulate(np.where(playing, np.arange(length), 0))
        period = period[idx]
        bridge_len = bridge_len[idx]
    return period, bridge_len, bow_v, bow_f, jolt


POLE = 0.45  # the bridge's loss filter: a higher pole is a darker string
GAIN = 0.985  # loss per round trip at low frequencies
_FILTER_DELAY = POLE / (1.0 - POLE)
_SLIP_EARLY = 0.28


def bow(notes, sr: int, length: int, rng: np.random.Generator, *, vibrato: float = 18.0, wear: float = 0.0,
        noise: float = 0.3) -> np.ndarray:
    """A bowed part's bridge force, `length` samples long."""
    if not notes:
        return np.zeros(length)
    period, bridge_len, bow_v, grip, catch = tracks(notes, sr, length, rng, vibrato=vibrato, wear=wear)
    hair = rng.standard_normal(length) * noise * 0.02 * np.abs(bow_v) + catch
    return run(period, bridge_len, bow_v, np.maximum(grip, 1e-4), hair, POLE, GAIN)
