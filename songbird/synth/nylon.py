"""Nylon strings plucked with the fingers: a classical (Spanish) guitar and a ukulele.

Nylon is slack and lossy beside steel: at the same pitch a nylon string
carries about two thirds of a steel one's tension, and its own internal
friction takes the upper harmonics away within a second or so, so a note
starts round and grows rounder (the plain trebles most, the metal-wound
basses least: their zing lasts). The pluck is the player's fingertip and
nail: a free stroke (the finger passing clear of the next string), a rest
stroke (coming to rest on it, pushing the string toward the top, so more of
the pluck goes into the plane that drives the body: fuller and louder), the
thumb's flesh (round), over the fingerboard (sul tasto: sweet) or near the
bridge (sul ponticello: thin, metallic).

A classical guitar's top is lighter and fan-braced: its air mode near 98 Hz
and its first top modes near 190 and 240 Hz carry the bass, and it radiates
less of the top than a steel-string does (Rossing and Fletcher; Christensen
and Vistisen's measurements). Its open strings ring in sympathy with what is
played, a large part of its bloom. A ukulele is a small guitar with four
nylon strings tuned G4 C4 E4 A4 (the fourth re-entrant, above the third): a
small body (its air near 270 Hz) and a short, bright sustain, strummed with
the fingers.

Chords whose notes share a start are spread by the fingers: a few
milliseconds low to high for a pinch or a down-strum, high to low for an
up-strum ("up"), a flamenco rasgueado's fingers flicking out one after
another over most of a tenth of a second.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import butter, sosfilt

from ..theory import midi_to_hz
from . import body, pluck, stringloop

CLASSICAL = body.Body(  # a fan-braced classical guitar: the air near 98 Hz, the top's first modes near 190 and 240
    modes=((98.0, 18.0, 5.0), (190.0, 26.0, 7.0), (240.0, 24.0, 3.5), (390.0, 30.0, 3.0), (560.0, 32.0, 2.5),
           (720.0, 28.0, 1.0)),
    dense=(700.0, 7000.0, 90), tilt=-1.5, q=(30.0, 20.0), direct=0.25, lowcut=70.0, highcut=7500.0,
)
UKULELE = body.Body(  # a concert ukulele: its air near 270 Hz, a small top ringing up to 10 kHz
    modes=((270.0, 16.0, 5.0), (430.0, 24.0, 6.0), (560.0, 26.0, 3.0), (820.0, 28.0, 2.5), (1150.0, 26.0, 1.5)),
    dense=(1000.0, 10000.0, 70), tilt=-1.5, q=(30.0, 20.0), direct=0.3, lowcut=200.0, highcut=10000.0,
)

GUITAR_STRINGS = (40, 45, 50, 55, 59, 64)  # E2 A2 D3 G3 B3 E4: the lower three metal-wound
UKE_STRINGS = (67, 60, 64, 69)  # G4 C4 E4 A4, as they lie across the neck

# How each stroke plucks: (where, as a fraction of the string from the bridge; the finger's hardness, 0 a
# fleshy fingertip to 1 a nail; loudness; into the body's plane)
STROKES = {
    "": (0.17, 0.45, 1.0, 1.0),
    "free": (0.17, 0.45, 1.0, 1.0),
    "rest": (0.17, 0.5, 1.25, 1.3),
    "thumb": (0.2, 0.15, 1.0, 1.1),
    "tasto": (0.32, 0.25, 0.9, 1.0),
    "pont": (0.06, 0.6, 0.9, 1.0),
    "down": (0.2, 0.55, 1.0, 1.0),
    "up": (0.2, 0.5, 0.8, 1.0),
    "rasgueado": (0.2, 0.75, 1.2, 1.0),
    "slur": (0.17, 0.2, 0.6, 1.0),
    "harmonic": (0.5, 0.1, 0.7, 1.0),
    "tremolo": (0.17, 0.5, 0.85, 1.0),
    "mute": (0.15, 0.4, 0.8, 1.0),
    "chop": (0.15, 0.4, 0.8, 1.0),
    "golpe": (0.15, 0.4, 0.0, 1.0),
}


def _string_of(pitch: float, strings) -> int:
    """The string a note is fingered on: the highest open string at or under it."""
    best = 0
    for k, s in enumerate(strings):
        if s <= pitch + 0.5 and s >= strings[best]:
            best = k
    return best


def _spread(notes, rng: np.random.Generator):
    """Notes sharing a start spread as the fingers strike them: (note, delay) pairs."""
    out = []
    groups = {}
    for n in notes:
        groups.setdefault(round(n.start, 3), []).append(n)
    for start, group in groups.items():
        if len(group) == 1:
            out.append((group[0], 0.0))
            continue
        arts = {n.art for n in group}
        up = "up" in arts
        step = 0.018 if "rasgueado" in arts else 0.012 if arts & {"down", "up", "chop"} else 0.004
        for k, n in enumerate(sorted(group, key=lambda m: m.pitch, reverse=up)):
            out.append((n, k * step * rng.uniform(0.7, 1.3)))
    return out


def render(name, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A nylon-string part, stereo, before its place and level."""
    uke = name == "ukulele"
    bright = float(settings.get("brightness", 0.5))
    wear = float(settings.get("wear", 0.25))
    size = float(settings.get("body", 1.0))
    ornament = float(settings.get("ornament", 0.5))
    strings = UKE_STRINGS if uke else GUITAR_STRINGS
    offsets = make.normal(0.0, 0.5 + 3.5 * wear, len(strings))  # each string a few cents off, the same all song
    nails = make.uniform(-0.1, 0.1)  # this player's nails: a little longer or shorter than most
    force = np.zeros(length)
    for note, delay in _spread([n for n in notes if 0.0 <= n.start < length / sr], rng):
        art = note.art if note.art in STROKES else ""
        where, hardness, loud, plane = STROKES[art]
        k = _string_of(note.pitch, strings)
        wound = not uke and k < 3
        start = note.start + delay
        i = int(round(start * sr))
        if i >= length:
            continue
        vel = float(np.clip(note.vel, 0.0, 1.0))
        if art == "golpe":  # the fingers' tap on the top: a knock of the body alone
            n = min(int(0.01 * sr), length - i)
            tap = sosfilt(butter(2, [150.0, 2500.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n + 64))
            force[i:i + n] += tap[64:] * np.exp(-np.arange(n) / (0.0015 * sr)) * vel * 0.6
            continue
        # Nylon's own friction takes a note's upper partials within a few tenths of a second (the plain trebles
        # most; a wound bass keeps some of its zing): a lowpass in the string's loop, set for each note so its
        # fundamental still rings as long as it should.
        hard = float(np.clip(hardness + nails + 0.3 * (bright - 0.5), 0.05, 0.95))
        decay = (1.6 if uke else 3.6 if wound else 2.8) * (1.0 - 0.15 * wear)
        freq = midi_to_hz(note.pitch + offsets[k] / 100.0)
        friction = (0.0015 if uke else 0.0008 if wound else 0.002) * (1.3 - 0.6 * bright)
        pole = _pole(freq, sr, 2.0 * decay * (220.0 / freq) ** 0.4, friction)
        dur = max(note.dur, 0.01)
        common = dict(vel=vel * loud, brightness=0.35 + 0.3 * bright, decay=decay, hardness=hard, damp=0.08, pole=pole)
        if art in ("mute", "chop"):  # stopped almost at once: its friction hardly matters
            y = pluck.pluck(freq, dur, sr, rng, vel=vel * loud, brightness=0.3, decay=decay, pick=where, hardness=hard,
                            planes=0.3, mute=True)
        elif art == "tremolo":  # the note's length filled with repeated strokes, a-m-i, about 13 a second
            count = max(1, int(dur * 13.0))
            picks = tuple((j / 13.0 + rng.normal(0.0, 0.004), (0.85 + 0.15 * (j % 3 == 0)) * rng.uniform(0.9, 1.05))
                          for j in range(count))
            y = stringloop.note(freq, dur, sr, rng, picks=picks, pick=where, planes=0.3, touch=0.2, **common)
        elif art == "slur" or (art == "" and ornament > 0.7 and note.dur > 0.6 and rng.random() < 0.15):
            # a hammer-on or a slide from a semitone under: the left hand, no pluck
            track = np.zeros(int(0.05 * sr))
            track[: int(0.03 * sr)] = -100.0 * (1.0 - np.linspace(0.0, 1.0, int(0.03 * sr))) ** 2
            y = stringloop.note(freq, dur, sr, rng, cents=track if art == "" else None, pick=where, planes=0.3,
                                click=False, **common)
        elif art == "harmonic":  # the finger at a node leaves a pure, bell-like tone
            y = stringloop.note(freq, dur, sr, rng, pick=0.5, planes=0.3, touch=0.1,
                                **{**common, "brightness": 0.1, "decay": decay * 1.4, "hardness": 0.05})
        else:
            y = stringloop.note(freq, dur, sr, rng, pick=where * rng.uniform(0.9, 1.1), planes=0.3 / plane, touch=0.2,
                                **common)
        end = min(length, i + len(y))
        force[i:end] += y[: end - i]
    if not np.any(force):
        return np.zeros((length, 2))
    # the open strings answer what shares their harmonics
    opens = list(strings)
    force = force + pluck.sympathetic(force, sr, opens, coupling=0.0008 if uke else 0.0012, decay=2.5,
                                      brightness=0.2)
    ir = body.impulse_response(UKULELE if uke else CLASSICAL, sr, seed=int(make.integers(1 << 30)), size=size)
    return body.resonate(force, ir * _steady(ir, sr, (250.0, 1200.0) if uke else (80.0, 700.0)))


@lru_cache(maxsize=512)
def _pole_cached(freq: float, sr: int, t60: float, friction: float) -> float:
    return stringloop.pole_for(freq, sr, t60, friction)


def _pole(freq: float, sr: int, t60: float, friction: float) -> float:
    return _pole_cached(round(freq, 1), sr, round(t60, 2), round(friction, 5))


def _steady(ir: np.ndarray, sr: int, band: tuple[float, float]) -> float:
    """What brings a body's gain over its strings' fundamentals to one: each maker's body colours the notes its
    own way, but no maker's is louder than another's where the fundamentals lie."""
    freqs, response = body.response(ir, sr, n=1 << 15)
    grid = np.exp(np.linspace(np.log(band[0]), np.log(band[1]), 64))
    return float(1.0 / np.sqrt(np.mean(10.0 ** (np.interp(grid, freqs, response) / 10.0))))


ARTICULATIONS = {
    "": "a free stroke: the finger passing clear, nail and flesh (alias free)",
    "rest": "a rest stroke: the finger coming to rest on the next string, fuller and louder",
    "thumb": "the thumb's flesh: round (the bass of a bossa or a waltz)",
    "tasto": "plucked over the fingerboard: sweet and round",
    "pont": "plucked near the bridge: thin and metallic",
    "down": "a down-strum with the fingers' backs (notes sharing a start spread low to high)",
    "up": "an up-strum (notes sharing a start spread high to low)",
    "rasgueado": "a flamenco rasgueado: the fingers flicking out one after another",
    "golpe": "a tap of the fingers on the top: a knock, no pitch",
    "slur": "a hammer-on or pull-off: the left hand sounds the note, no pluck",
    "harmonic": "a natural harmonic: a pure, bell-like tone",
    "tremolo": "the note's length filled with repeated strokes, about 13 a second",
    "mute": "a note stopped almost at once", "chop": "a muted strum: the ukulele's chnk",
}

SPEC = {
    "nylon": dict(
        family="plucked", role="comping", register=(40, 83), place=(-0.25, 0.6), level=0.125, poly=True,
        articulations=ARTICULATIONS,
        about="a classical (Spanish) guitar: nylon strings plucked with the fingertips and nails, "
              "for bossa nova, flamenco, a waltz or a classical line",
    ),
    "ukulele": dict(
        family="plucked", role="comping", register=(60, 84), place=(0.3, 0.4), level=0.21, poly=True,
        articulations=ARTICULATIONS,
        about="a concert ukulele tuned G4 C4 E4 A4, strummed or picked with the fingers",
    ),
}
