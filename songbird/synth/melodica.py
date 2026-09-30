"""The melodica: free reeds under a small keyboard, blown through a mouthpiece, in a plastic case.

An alto melodica (a Hohner Melodica, a pianica; the one Augustus Pablo played
in dub), 37 keys from F3 to F6. Each key opens a valve over one brass reed,
tuned to its note and nothing else: chromatic, no bends, and chords where the
fingers find them. The player's breath fills one air chamber under the reed
plate, so every key down shares it.

The reed. A free reed chops the air into pulses, so its tone is rich in odd
and even harmonics; blown harder, the pulse sharpens and the tone brightens
(reed.tables, a dark and a bright period cross-faded by the breath's
pressure, as harmonica.py does), and the loudness follows the pressure. Its
chamber and valve hole give it the melodica's slightly nasal colour, a broad
hump near 1.3 kHz; the reed plate is a small source, weak in its lowest
harmonics. Unlike a harmonica's there are no cover plates and no mouth
shaping each note: it is fuller and more even across its range. A reed speaks
in 15-30 ms at a mezzo-forte breath in the middle, slower low and soft,
quicker hard, starting a few cents sharp and settling; a free reed sags a few
cents flat as the breath presses it (the low reeds most), so reeds are tuned
to be true at a mezzo-forte breath. A chord shares the breath: the
chamber's pressure falls as the fourth root of the keys down, so each reed is
a little softer and darker (a three-note triad about 1 dB over one note).

The breath. Velocity is the breath's pressure. Each note (or chord written
together) is tongued: a quick rise of the pressure and a chuff of breath hiss
as the tongue lets the air go; a new tongued note straight after another
stops the air for 15-25 ms first (and dips any note held through it). The
breath hisses softly throughout, about as loud however hard it blows. On long
notes (ornament) a gentle breath vibrato pulses the pressure (and with it the
pitch, a cent or two, through the reed's sag).

The case: a hollow plastic box, a couple of broad resonances (body.Body,
MELODICA here) and not much ring.

Articulations: "" (tongued; notes written together sound together), "slur"
(the breath carries on from the note before: no new attack, no chuff),
"stab" (short and punchy, a staccato chord: a hard puff, cut short),
"swell" (the breath swelling in through the note).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from ..theory import midi_to_hz
from . import body, oa, reed
from .iir import butter

COMPASS = (53, 89)  # F3 to F6: a 37-key alto melodica

ARTICULATIONS = {
    "": "tongued: the breath let go with a chuff, the reed speaking in 15-30 ms (notes written together are one "
        "chord on one breath)",
    "slur": "the breath carries on from the note before: no new attack, the next key's reed speaks on the "
            "breath already there",
    "stab": "short and punchy: a hard puff cut off quickly (a staccato chord)",
    "swell": "the breath swelling in: the note starts soft and dark and grows louder and brighter",
}

SPEC = {
    "melodica": dict(
        family="reed", role="lead", register=COMPASS, place=(-0.25, 0.2), level=0.4313, poly=True,
        brighter=0.35, articulations=ARTICULATIONS,
        about="an alto melodica (a pianica), F3-F6: one brass free reed a key, blown through a mouthpiece in a "
              "plastic case; bright, reedy and a little nasal, the breath hissing as a note is tongued; chords "
              "where the fingers find them, notes outside its keys moved by octaves",
    ),
}

MELODICA = body.Body(  # the plastic case: a hollow box's broad low hump, the reed chamber's nasal hump near 1.3 kHz
    # and a little presence near 3 kHz; hardly any ring (thin plastic, a small box)
    modes=((380.0, 3.0, 2.0), (1300.0, 2.5, 2.5), (3000.0, 3.0, 1.5)),
    dense=(600.0, 9000.0, 28), tilt=-0.5, q=(10.0, 7.0), direct=0.7, lowcut=140.0, highcut=10000.0,
    hill=(2400.0, 1.6, 2.0), length=0.08, coherent=True,
)

SLOPES = (1.45, 0.7)  # harmonic k's amplitude as k**-slope: a gentle breath, a hard one
SPEAK = 0.009  # the reed's build-up time constant (s) at A4 and a mezzo-forte breath (10-90% in 20 ms), doubling
# every 18 semitones down and with a breath half as strong
SAG = (6.0, 3.0)  # cents a reed sags at a mezzo-forte breath: F3's, F6's
NOISE = 0.006  # the breath's hiss against a mezzo-forte note
PULSE = 0.25  # the breath vibrato's swing of the pressure, at ornament 1
GROUP = 0.015  # notes starting within this of each other are one chord
JOIN = 0.025  # a note starting within this of another's end follows straight on


def _shape(f0: float):
    """The tone as it leaves the reed chamber: a nasal hump (5 dB near 1.3 kHz) and a small source's weak low
    harmonics (rising 4 dB an octave up to 1 kHz)."""
    nasal = 10.0 ** (5.0 / 20.0) - 1.0

    def shape(f):
        g = 1.0 + nasal * np.exp(-0.5 * (np.log2(f / 1300.0) / 0.5) ** 2)
        return g * np.minimum(f / 1000.0, 1.0) ** (4.0 / 6.02)

    return shape


def _fit(pitch: float) -> float:
    """A pitch moved by octaves onto the keyboard."""
    while pitch < COMPASS[0] - 0.5:
        pitch += 12.0
    while pitch > COMPASS[1] + 0.5:
        pitch -= 12.0
    return pitch


def _sag(pitch: float) -> float:
    x = float(np.clip((pitch - COMPASS[0]) / (COMPASS[1] - COMPASS[0]), 0.0, 1.0))
    return SAG[0] + (SAG[1] - SAG[0]) * x


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The melodica's dry mono stem, `length` samples (before its place and level)."""
    s = {"brightness": 0.5, "wear": 0.25, "ornament": 0.5, "body": 1.0, **settings}
    bright, wear, ornament = float(s["brightness"]), float(s["wear"]), float(s["ornament"])
    # the maker's melodica and its player, drawn in a fixed order: the case's seed, every reed's own tuning (a worn
    # one further off), how far over the band it sits at a mezzo-forte breath, the player's vibrato rate
    seed = int(make.integers(1 << 30))
    over_band = float(make.uniform(0.0, 0.8))
    tuning = {p: float(make.normal(0.0, 0.4 + 3.0 * wear)) + over_band for p in range(COMPASS[0], COMPASS[1] + 1)}
    rate = float(make.uniform(4.5, 5.5))
    out = np.zeros(length)
    notes = sorted((n for n in notes if 0 <= n.start * sr < length and n.dur > 0),
                   key=lambda n: (n.start, -n.pitch))
    if not notes:
        return out
    # chords: notes starting together are one breath over several keys
    groups: list[list] = []
    for n in notes:
        if groups and n.start - groups[-1][0].start < GROUP:
            groups[-1].append(n)
        else:
            groups.append([n])
    starts = [g[0].start for g in groups]
    slurred = [any(n.art == "slur" for n in g) for g in groups]
    cache: dict = {}

    def waves(pitch: float):
        k = round(pitch, 2)
        if k not in cache:
            f0 = midi_to_hz(pitch)
            cache[k] = reed.tables(f0, sr, rng, SLOPES, even=0.85, shape=_shape(f0), top=f0 * 1.01)
        return cache[k]

    hiss_sos = butter(2, (1000.0, 7000.0), btype="bandpass", fs=sr, output="sos")
    ends = np.array([max(n.start + n.dur for n in g) for g in groups])
    for gi, group in enumerate(groups):
        g0 = starts[gi]
        # how this breath begins: fresh after a rest, carried on (a slur straight after or over a sounding note),
        # or tongued
        sounding = gi > 0 and float(np.max(ends[:gi])) > g0 - JOIN
        carried = slurred[gi] and sounding
        share = len(group) ** -0.25  # the chamber's pressure falls a little as more valves open
        for j, note in enumerate(group):
            art = note.art
            vel = float(np.clip(note.vel, 0.0, 1.0))
            dur = float(note.dur)
            if art == "stab":
                dur = min(dur, max(0.05, min(0.14, 0.5 * dur)))
                vel = min(1.0, 1.1 * vel)
            i0 = int(round(note.start * sr))
            end = note.start + dur
            # the tongue: a tongued group starting as this note ends stops the air first; one starting while it is
            # held dips it
            dips = []
            for k in range(gi + 1, len(groups)):
                sk = starts[k]
                if sk > end + JOIN:
                    break
                if slurred[k] or sk <= note.start + 0.02:
                    continue
                stop = float(rng.uniform(0.015, 0.025))
                if sk >= end - JOIN:
                    end = max(note.start + 0.02, min(end, sk - stop))
                    break
                dips.append((sk - note.start, stop))
            m = max(1, min(length - i0, int(round((end - note.start) * sr))))
            tail = int((0.012 if art == "stab" else 0.03) * sr)
            tail = max(0, min(tail, length - i0 - m))
            n = m + tail
            t = np.arange(n) / sr
            # the breath's pressure: its attack, its release, a swell's growth
            attack = 0.006 if art == "stab" else (0.02 if carried else 0.012)
            a = max(1, min(m, int(attack * sr)))
            pressure = np.full(n, vel)
            start = 0.85 if carried else 0.0
            pressure[:a] = vel * (start + (1.0 - start) * np.sin(0.5 * np.pi * np.linspace(0.0, 1.0, a)))
            if tail:
                pressure[m:] = vel * np.cos(0.5 * np.pi * np.linspace(0.0, 1.0, tail)) ** 2
            if art == "swell":
                rise = max(0.05, 0.6 * dur)
                pressure *= 0.3 + 0.8 * np.clip(t / rise, 0.0, 1.0) ** 1.5
            elif art == "stab":
                pressure *= 1.0 + 0.3 * np.exp(-t / 0.03)  # the hard puff
            for at, stop in dips:
                dip = np.clip(np.abs(t - at) / stop, 0.0, 1.0)
                pressure *= 0.1 + 0.9 * dip * dip
            if dur > 0.6 and ornament > 0 and art != "stab":
                # the breath vibrato, easing in after the note has settled; its rate wanders a little
                ramp = np.clip((t - 0.25) / 0.35, 0.0, 1.0)
                knots = rng.uniform(-1.0, 1.0, int(n / sr / 0.3) + 2)
                wobble = np.interp(t, np.arange(len(knots)) * 0.3, knots)
                wave = np.sin(2 * np.pi * np.cumsum(rate * (1.0 + 0.06 * wobble)) / sr + rng.uniform(0, 6.28))
                pressure *= 1.0 + PULSE * ornament * ramp * wave
            # the pitch: the key's reed, tuned true at a mezzo-forte breath, sharp softer and flat harder, starting
            # a few cents sharp as it speaks
            played = _fit(float(note.pitch))
            key = int(np.clip(round(played), COMPASS[0], COMPASS[1]))
            sag = _sag(played)
            cents = tuning[key] + sag * (1.0 - (np.maximum(pressure, 0.0) / 0.6) ** 1.5)
            if not carried:
                cents += rng.uniform(4.0, 10.0) * np.exp(-t / 0.02)
            freq = midi_to_hz(played) * 2.0 ** (cents / 1200.0)
            # the reed builds up, low and soft slower, hard quicker; carried on, the breath is already there
            speak = SPEAK * 2.0 ** ((69.0 - played) / 18.0) * (0.6 / max(vel, 0.15))
            if art == "stab":
                speak *= 0.7
            elif carried:
                speak *= 0.6
            speak = float(np.clip(speak, 0.004, 0.03))
            build = 1.0 - np.exp(-t / speak)
            drive = pressure * share
            mix = np.clip(0.2 + 0.5 * bright + 1.1 * (drive - 0.6), 0.0, 1.0)
            dark, brightw = waves(played)
            sound = np.zeros(n)
            reed._read_mix(dark, brightw, freq / sr, np.maximum(drive, 0.0) ** 1.2 * build, mix, sound, 0,
                           rng.random())
            # the breath's hiss, one for the group (on its top note), about as loud however hard the breath, and a
            # chuff as the tongue lets it go
            if j == 0:
                hiss = sosfilt(hiss_sos, rng.standard_normal(n + 64))[64:]
                chuff = 0.2 if carried else (2.5 if art == "stab" else 1.6)
                burst = 1.0 + chuff * np.exp(-t / 0.015)
                sound += hiss * (pressure / max(vel, 0.05)) * (max(vel, 0.05) / 0.6) ** 0.2 * burst * NOISE * \
                    (1.0 + 1.5 * wear)
            end_i = min(length, i0 + n)
            out[i0:end_i] += sound[: end_i - i0]
    ir = body.impulse_response(MELODICA, sr, seed=seed, size=float(s["body"]), channels=1)[:, 0]
    y = oa.convolve(out, ir, length)
    del out
    # a reed's pulses of air aren't zero-mean: no DC leaves the case
    return sosfilt(butter(1, 20.0, btype="highpass", fs=sr, output="sos"), y)
