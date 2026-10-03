"""Blown pipe: a flue pipe (a wooden flute or low whistle), physically inspired.

A flute sounds because the player's air jet flips in and out of the pipe at
the labium, in step with the air moving in the bore. The jet's split is a
saturating function of its deflection, so a sinusoidal flip becomes a flow
with a few harmonics: more when the player blows harder (the jet swings
further into saturation), even ones too when the jet is aimed off the edge's
centre. The jet is also turbulent: breath noise, loudest while the jet is
going in. Everything that enters the bore rings in it: the bore is a
resonator tuned to the fingered note, which gathers the noise into harmonic
bands, as a real flute's breathiness is.

Tonguing starts a note with a puff (a chiff of noise) and a short climb in
breath; fingers change a slurred note almost at once, with a dip where the
bore's old standing wave gives way to the new. Ornaments (cuts, taps, rolls)
are short notes in the score. A player's own tuning wanders a few cents, more
for a worn one, and long notes carry a slow breath vibrato.
"""

from __future__ import annotations

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from ..theory import midi_to_hz
from .fx import hold
from .iir import butter


@njit(cache=True, nogil=True)
def run(freq, breath, chiff, drive, aim, noise, feedback, damping, sr):
    """The pipe's sound, sample by sample, from control tracks: freq (Hz),
    breath (the jet's strength, 0 silent), chiff (extra turbulence at a
    tongued start), drive (how far the jet swings into saturation), aim (the
    jet's offset from the edge), noise (white noise), and the bore's
    feedback and damping (a one-pole in the loop)."""
    n = freq.shape[0]
    size = 8192
    bore = np.zeros(size)
    out = np.zeros(n)
    phase = 0.0
    lp = 0.0
    turb_lp = 0.0
    for t in range(n):
        f = freq[t]
        phase += f / sr
        if phase > 1.0:
            phase -= 1.0
        jet = np.sin(2.0 * np.pi * phase)
        k = drive[t]
        flow = np.tanh(k * jet + aim[t]) - np.tanh(aim[t])
        turb_lp = 0.35 * noise[t] + 0.65 * turb_lp  # turbulence: noise that is mostly below a few kHz
        turb = turb_lp * (0.6 + 0.4 * jet) * (0.1 * breath[t] + chiff[t])
        x = flow * breath[t] / (k + 0.3) + turb
        # the bore: a resonator one period long, read with linear interpolation
        period = sr / f - damping / (1.0 - damping)  # the loop filter's own delay comes off
        pos = t - period
        i = int(np.floor(pos))
        frac = pos - i
        back = (1.0 - frac) * bore[i % size] + frac * bore[(i + 1) % size]
        lp = (1.0 - damping) * back + damping * lp
        y = x + feedback * lp
        bore[t % size] = y
        out[t] = y
    return out


def tracks(notes, sr: int, length: int, rng: np.random.Generator, *, brightness: float = 0.5, wear: float = 0.0,
           vibrato: float = 0.5):
    """Control tracks for a pipe part from its notes (start, dur, pitch, vel,
    art). art "slur", "cut" and "tap" are fingered without tonguing; anything
    else is tongued."""
    freq = np.full(length, 440.0)
    breath = np.zeros(length)
    chiff = np.zeros(length)
    drive = np.full(length, 1.0)
    aim = np.full(length, 0.15)
    ordered = sorted(notes, key=lambda n: n.start)
    tuning = 0.0
    for k, note in enumerate(ordered):
        i0 = max(0, int(round(note.start * sr)))
        i1 = min(length, int(round((note.start + note.dur) * sr)))
        m = i1 - i0
        if m < 8:
            continue
        t = np.arange(m) / sr
        tuning = 0.7 * tuning + rng.normal(0.0, 2.0 + 6.0 * wear)  # the player's tuning, wandering
        fingered = note.art in ("slur", "cut", "tap")
        follows = k + 1 < len(ordered) and ordered[k + 1].art in ("slur", "cut", "tap") and \
            ordered[k + 1].start - (note.start + note.dur) < 0.02
        cents = tuning + np.zeros(m)
        if not fingered:  # a tongued note starts a touch sharp and settles as the jet steadies
            settle = min(m, int(0.04 * sr))
            cents[:settle] += 12.0 * (1.0 - np.linspace(0.0, 1.0, settle)) ** 2
        if note.dur > 0.5 and vibrato > 0 and note.art not in ("cut", "tap"):
            onset = min(0.3, 0.4 * note.dur)
            ramp = np.clip((t - onset) / 0.3, 0.0, 1.0)
            wobble = np.sin(2 * np.pi * rng.uniform(4.6, 5.4) * t + rng.uniform(0, 6.28))
            cents += 6.0 * vibrato * ramp * wobble
            level = 1.0 + 0.08 * vibrato * ramp * wobble
        else:
            level = np.ones(m)
        freq[i0:i1] = midi_to_hz(note.pitch) * 2.0 ** (cents / 1200.0)
        env = np.ones(m)
        if fingered:  # the old standing wave gives way: a short dip
            dip = min(m, int(0.012 * sr))
            env[:dip] *= 1.0 - 0.3 * np.sin(np.pi * np.linspace(0.0, 1.0, dip))
        else:
            rise = min(m, int(rng.uniform(0.012, 0.022) * sr))
            env[:rise] = np.linspace(0.0, 1.0, rise) ** 1.5
            puff = min(m, int(0.035 * sr))
            chiff[i0:i0 + puff] += 0.5 * note.vel * np.exp(-np.arange(puff) / (0.008 * sr))
        if not follows:  # the breath stops (or the tongue stops it)
            fall = min(m, int(0.03 * sr))
            env[-fall:] *= np.linspace(1.0, 0.0, fall) ** 1.2
        if note.art == "swell":
            env *= 0.7 + 0.3 * np.sin(np.pi * np.linspace(0.0, 1.0, m))
        # the breath is never quite steady: a slow wander of a decibel or so
        wander = np.interp(t, np.linspace(0.0, t[-1] + 1e-9, max(2, int(note.dur * 6) + 2)),
                           rng.normal(0.0, 0.08, max(2, int(note.dur * 6) + 2)))
        breath[i0:i1] = note.vel * env * level * (1.0 + wander)
        # A louder note pushes the jet further into saturation: brighter. Higher
        # notes are blown with a faster, narrower jet: a little purer.
        drive[i0:i1] = 0.7 + 2.0 * brightness * (0.3 + note.vel) - 0.006 * (note.pitch - 72)
        aim[i0:i1] = 0.15 + 0.35 * brightness
    # hold the last pitch through rests so the bore rings down in tune
    sounding = breath > 0.0
    if sounding.any():
        hold(sounding, freq, drive, aim)  # each where it lies: track[the last sounding sample]
    return freq, breath, chiff, drive, aim


def blow(notes, sr: int, length: int, rng: np.random.Generator, *, brightness: float = 0.5, wear: float = 0.0,
         breathiness: float = 1.0, vibrato: float = 0.5) -> np.ndarray:
    """A pipe part, `length` samples long."""
    if not notes:
        return np.zeros(length)
    freq, breath, chiff, drive, aim = tracks(notes, sr, length, rng, brightness=brightness, wear=wear, vibrato=vibrato)
    # turbulence at the lip is a hiss, not a rumble: nothing much below a few hundred hertz
    sos = butter(2, 350.0, btype="highpass", fs=sr, output="sos")
    noise = np.empty(length)
    state = np.zeros((len(sos), 2))
    for a in range(0, length, 1 << 16):
        b = min(length, a + (1 << 16))
        filtered, state = sosfilt(sos, rng.standard_normal(b - a), zi=state)
        filtered *= 1.6 * breathiness * (1.0 + 0.5 * wear)
        noise[a:b] = filtered
    y = run(freq, breath, chiff, drive, aim, noise, 0.65, 0.35, float(sr))
    del freq, breath, chiff, drive, aim, noise
    # radiation from the open holes and the embouchure favours the highs a little; no DC leaves the pipe
    sos = butter(1, 180.0, btype="highpass", fs=sr, output="sos")
    state = np.zeros((len(sos), 2))
    for a in range(0, length, 1 << 16):
        b = min(length, a + (1 << 16))
        filtered, state = sosfilt(sos, y[a:b], zi=state)
        y[a:b] = filtered
    return y
