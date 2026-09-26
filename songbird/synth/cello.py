"""The cello, the viola and a string section: bowed strings on bowed.py's waveguide, through their own bodies.

Every player is bowed.py's string (two delay lines meeting at the bow, the STK
friction curve between) driven by control tracks from bowed.tracks(), with
what a cellist does differently from a fiddler:

- The attack. Left to the friction alone the Helmholtz motion takes 15 to 40
  periods to organize itself: fine on a violin's E string, a quarter of a
  second on a cello's C string, where a player's is under a tenth (Guettler
  and Askenfelt 1997). A good player's bow grips the string and it speaks, so
  here, once the bow has gathered speed (in 15 to 25 ms), the string is set
  into Helmholtz motion at 0.6 to 0.9 of the size that speed sustains
  (bowed.run_primed), less at a bow change and for a worn player; the hair's
  catch and the few milliseconds before are the stroke's scratch.
- The bow's place. Brightness moves it from over the end of the fingerboard
  (0.13 of the string from the bridge) toward the bridge (0.06); "tasto"
  plays at 0.2, "pont" at 0.04. The bow's weight follows Schelleng's window
  (its maximum falls as 1/beta, its minimum as 1/beta^2: the weight goes as
  beta^-1.5, between them) and its speed as beta, so the level holds while
  the tone moves: a heavy bow near the bridge keeps the Helmholtz corner
  sharp, a light one over the fingerboard rounds it (the loop's loss pole,
  0.25 to 0.62, its delay taken off the period so the pitch holds).
- A cellist's vibrato: 5 to 6 Hz, 20 to 35 cents (a violist's 5.5 to 6.3,
  14 to 26), wider with ornament, on notes longer than a third of a second.
- Shifts: "slide" glides from the note before (or from a tone and a half
  below after a rest), slower than a fiddler's.
- "trem": the bow reversing 11 to 15 times a second; "pizz": the string
  plucked with the fingertip over the end of the fingerboard (pluck.py),
  through the same body.

Double stops (overlapping notes) go to a second string. The string section
("strings") is violins, violas and cellos, each line of the part taken by the
section whose register its middle sits in and played by two or three players,
each a few cents off, a few tens of milliseconds early or late, with a vibrato
and a bow of their own; each section is heard through two bodies (a desk
each), seated violins left, violas in the middle, cellos right.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, oaconvolve, sosfilt

from ..theory import midi_to_hz
from . import body, bowed, fx, pluck

ARTICULATIONS = {
    "": "détaché: each note a new bow stroke",
    "slur": "legato: the bow carries on from the note before, the finger moves",
    "slide": "a shift: the finger slides into the note from the one before (after a rest, from a tone and a half below)",
    "swell": "the bow's weight swells and eases through the note",
    "pizz": "pizzicato: plucked with the fingertip over the end of the fingerboard, left to ring",
    "tasto": "sul tasto: the bow over the fingerboard, light and slow; soft and dark",
    "pont": "sul ponticello: the bow near the bridge, heavy; glassy, the upper harmonics strong",
    "trem": "tremolo: the bow reversing 11 to 15 times a second through the note",
}

SPEC = {
    "cello": dict(family="bowed", role="comping", register=(36, 76), place=(0.3, 0.5), level=0.098, poly=False,
                  articulations=ARTICULATIONS,
                  about="a cello: bowed, slid, plucked; overlapping notes are double stops on a second string"),
    "viola": dict(family="bowed", role="comping", register=(48, 88), place=(0.2, 0.45), level=0.076, poly=False,
                  articulations=ARTICULATIONS,
                  about="a viola: darker than the fiddle, its C string weak; bowed, slid, plucked"),
    "strings": dict(family="bowed", role="comping", register=(36, 96), place=(0.0, 0.9), level=0.0265, poly=True,
                    articulations=ARTICULATIONS,
                    about="a string section: each line of the part taken by violins (left), violas or cellos (right) "
                          "by its register, two or three players to a line"),
}


@dataclass(frozen=True)
class Kind:
    """What one size of bowed instrument is like, and how its player plays it."""

    strings: tuple[int, ...]  # the open strings, MIDI
    box: body.Body
    rate: float  # vibrato, Hz
    depth: tuple[float, float]  # vibrato's peak cents with no ornament and with the most
    rise: float  # seconds the bow takes to gather speed at a fresh stroke (half again when played softly)
    turn: float  # seconds it takes to turn round at a bow change
    bite: float  # seconds the stroke's extra weight takes to ease off
    shift: float  # seconds a slide takes
    dark: float  # bow position (fraction of the string from the bridge) at brightness 0
    bright: float  # and at 1
    fingerboard: float  # where the fingerboard ends, as a fraction of the open string from the bridge
    ring: float  # a stopped pizzicato's T60 at 220 Hz, s


CELLO = Kind(strings=(36, 43, 50, 57), box=body.CELLO, rate=5.5, depth=(20.0, 35.0), rise=0.015, turn=0.012,
             bite=0.08, shift=0.14, dark=0.13, bright=0.06, fingerboard=0.2, ring=1.6)
VIOLA = Kind(strings=(48, 55, 62, 69), box=body.VIOLA, rate=5.9, depth=(14.0, 26.0), rise=0.013, turn=0.01,
             bite=0.07, shift=0.11, dark=0.12, bright=0.06, fingerboard=0.22, ring=1.2)
VIOLIN = Kind(strings=(55, 62, 69, 76), box=body.FIDDLE, rate=6.0, depth=(12.0, 25.0), rise=0.012, turn=0.01,
              bite=0.06, shift=0.09, dark=0.12, bright=0.06, fingerboard=0.24, ring=1.0)
KINDS = {"cello": CELLO, "viola": VIOLA}

REF = 0.1  # the bow position the speeds and weights are reckoned from
TASTO, PONT = 0.2, 0.04  # bow positions
POLES = (0.55, 0.35, 0.62, 0.25)  # the corner's rounding: at brightness 0 and 1, sul tasto, sul ponticello
INTONATION = 0.005  # semitones a new player's notes spread by (wear adds 0.08 a unit: bowed.tracks)
LOUDER = 0.4  # the pole falls this much per unit of velocity: a heavier, faster bow keeps the corner sharper
GLASS = (("low", 400.0, -6.0), ("high", 1500.0, 10.0))  # sul ponticello's tilt of the bridge force
BRIGHTER = (8.0, 10.0, -6.0)  # dB above 1 kHz per unit of brightness and of velocity, and for sul tasto's light bow
PIZZ = 0.55  # a pizzicato's force against a bowed note's

# How much longer than asked the loop runs (samples), measured over bow positions 0.04 to 0.2, poles 0.25 to 0.62
# and velocities 0.35 to 0.9 at D4 to E5 (scratchpad calibration: rms error 0.009 samples, worst 0.033): the slip
# comes early by an amount that grows with the corner's rounding, the bow's weight and its distance from the bridge.
SLIP_FIT = (0.13994, -0.51846, -0.00748, -0.05092, -0.01802, -0.8355, 0.0002, -0.19965)


def _delay(pole: np.ndarray, freq: np.ndarray, sr: int) -> np.ndarray:
    """Phase delay in samples of the one-pole loss filter at freq."""
    w = 2.0 * np.pi * freq / sr
    return np.arctan2(pole * np.sin(w), 1.0 - pole * np.cos(w)) / w


def _excess(pole: np.ndarray, beta: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """The loop's measured excess length in samples (SLIP_FIT), for pole, bow position and weight (the note's
    velocity, with wear counted as bowed.tracks counts it: 0.4 of wear presses like 0.6 of velocity)."""
    c = SLIP_FIT
    p, b, v = pole - 0.45, 1.0 / beta - 10.0, weight - 0.6
    return c[0] + c[1] * p + c[2] * b + c[3] * v + c[4] * p * b + c[5] * p * p + c[6] * b * b + c[7] * p * v


def vibrato(kind: Kind, ornament: float) -> float:
    """Peak cents of a player's vibrato on a long note: nearly none played plain, the kind's widest at ornament 1."""
    return 0.15 * kind.depth[0] + (kind.depth[1] - 0.15 * kind.depth[0]) * max(0.0, ornament) ** 0.5


def lines(notes, overlap: float = 0.08) -> list[list]:
    """A part's notes as monophonic lines. A note joins the line that is free when it starts (a note still sounding
    up to `overlap` s, or half its length, into it is cut there) whose last pitch is nearest; notes starting
    together (a chord, a double stop) take a line each."""
    out: list[list] = []
    for note in sorted(notes, key=lambda n: (n.start, -n.pitch)):
        best = None
        for k, line in enumerate(out):
            last = line[-1]
            if last.start + last.dur <= note.start + min(overlap, 0.5 * last.dur) and last.start < note.start - 1e-3:
                d = abs(last.pitch - note.pitch)
                if best is None or d < best[0]:
                    best = (d, k)
        if best is None:
            out.append([note])
            continue
        line = out[best[1]]
        last = line[-1]
        if last.start + last.dur > note.start:
            line[-1] = replace(last, dur=note.start - last.start)
        line.append(note)
    return out


def _segments(notes, sr: int, length: int, gap: float = 2.5, tail: float = 3.0):
    """Stretches of a line to run the string over: notes grouped where rests are shorter than `gap`, each
    stretch from just before its first note to `tail` s after its last (or the next stretch)."""
    groups: list[list] = []
    for note in notes:
        if groups and note.start - max(n.start + n.dur for n in groups[-1]) < gap:
            groups[-1].append(note)
        else:
            groups.append([note])
    out = []
    for k, group in enumerate(groups):
        s0 = max(0, int((group[0].start - 0.02) * sr))
        end = max(n.start + n.dur for n in group) + tail
        if k + 1 < len(groups):
            end = min(end, groups[k + 1][0].start - 0.02)
        s1 = min(length, int(end * sr))
        if s1 - s0 > 16:
            out.append((group, s0, s1))
    return out


def _tremolo(notes, bow_v, sr: int, rng: np.random.Generator) -> list[tuple[int, float]]:
    """Turn each "trem" note's stroke into fast reversals (in place on bow_v); where each new stroke is up to speed."""
    starts = []
    for note in notes:
        if note.art != "trem":
            continue
        i0, i1 = int(round(note.start * sr)), min(len(bow_v), int(round((note.start + note.dur) * sr)))
        if i1 - i0 < 64:
            continue
        seg = bow_v[i0:i1]
        base = np.abs(seg)
        sign = np.sign(seg[np.argmax(base)]) or 1.0
        rate = rng.uniform(11.0, 15.0) * (0.9 + 0.2 * note.vel)  # strokes a second
        length = sr / rate
        turn = 0.006 * sr
        k = np.arange(i1 - i0) / length
        stroke = np.floor(k)
        frac = (k - stroke) * length
        speed = np.minimum(1.0, np.minimum(frac, length - frac) / turn)
        bow_v[i0:i1] = sign * (-1.0) ** stroke * speed * base
        for j in range(1, int(stroke[-1]) + 1):
            at = i0 + int(round(j * length + turn))
            if at < i1:
                starts.append((at, 0.45 * bow_v[at]))
    return starts


def _bowed(kind: Kind, notes, sr: int, length: int, rng: np.random.Generator, s: dict, q: dict) -> np.ndarray:
    """One player's bowed notes: the bridge force over `length` samples (notes in seconds from 0)."""
    wear, bright = float(s["wear"]), float(s["brightness"])
    home = kind.dark * (kind.bright / kind.dark) ** bright * q["position"]
    home_pole = POLES[0] + (POLES[1] - POLES[0]) * bright

    def place(note):
        return {"tasto": (TASTO, 0.65), "pont": (PONT, 0.8)}.get(note.art, (home, 1.0))

    def bowing(note):
        where, level = place(note)
        return where, 0.08 * where, where / REF * level, (REF / where) ** 1.5

    depth = vibrato(kind, float(s["ornament"])) * q["depth"]
    period, bridge_len, bow_v, grip, catch = bowed.tracks(
        notes, sr, length, rng, vibrato=depth, rate=kind.rate * q["rate"], wear=wear, rise=kind.rise,
        turn=kind.turn, bite=kind.bite, slide=(None, kind.shift), bowing=bowing, intonation=INTONATION)
    # The corner's rounding, the bow's weight and how far toward sul ponticello's surface sound, note by note
    # (each held from its note's start to the next's): a heavier, faster bow keeps the corner sharper, so louder
    # is brighter.
    ordered = sorted(notes, key=lambda n: n.start)
    starts = [min(length, max(0, int(round(n.start * sr)))) for n in ordered]
    runs = np.diff([0] + starts + [length])
    corners = [np.clip({"tasto": POLES[2], "pont": POLES[3]}.get(n.art, home_pole + LOUDER * (0.6 - n.vel)),
                       POLES[3], POLES[2]) for n in ordered]
    pole = np.repeat([home_pole] + corners, runs)
    weight = np.repeat([0.6] + [n.vel + 0.4 / 0.6 * wear for n in ordered], runs)
    shelf = np.repeat([0.0] + [10.0 ** ((BRIGHTER[0] * (bright - 0.5) + BRIGHTER[1] * (n.vel - 0.6)
                                         + (BRIGHTER[2] if n.art == "tasto" else 0.0)) / 20.0) - 1.0
                               for n in ordered], runs)
    glass = np.repeat([0.0] + [float(n.art == "pont") for n in ordered], runs)
    # the pitch kept: the loss filter's delay at the note's frequency and the early slip taken off (worked out every
    # 32 samples: they move with the vibrato, slowly)
    loop = period + bowed._FILTER_DELAY - bowed._SLIP_EARLY
    beta = bridge_len / loop
    grid = np.arange(0, length, 32)
    fix = _delay(pole[grid], sr / loop[grid], sr) + _excess(pole[grid], beta[grid], weight[grid])
    period = loop + bowed._SLIP_EARLY - np.interp(np.arange(length), grid, fix)
    # where each stroke is up to speed, the string is set moving
    primes = _tremolo(notes, bow_v, sr, rng)
    last_end, last = -1.0, None
    for note in sorted(notes, key=lambda n: n.start):
        if note.dur * sr < 16:
            continue
        joined = last is not None and note.start - last_end < 0.02
        last_end, last = note.start + note.dur, note
        if note.art == "slur" and joined:
            continue
        i0, i1 = int(round(note.start * sr)), min(length, int(round((note.start + note.dur) * sr)))
        if i1 - i0 < 16:
            continue
        seg = bow_v[i0:i1]
        full = np.abs(seg[len(seg) // 2]) if note.art != "trem" else np.abs(seg).max()
        up = np.abs(seg) >= 0.9 * full
        size = (0.6 if joined else 0.85) * (1.0 - 0.35 * wear) * rng.uniform(0.9, 1.1)
        if full > 0 and up.any():
            k = int(np.argmax(up))
            primes.append((i0 + k, size * seg[k]))
    primes.sort()
    at = np.array([p[0] for p in primes], dtype=np.int64)
    velocity = np.array([p[1] for p in primes], dtype=np.float64)
    # the hair's noise in proportion to the motion it rides on (speed over bow position), not to the speed alone
    hair = np.zeros(length)
    on = np.flatnonzero(bow_v)
    hair[on] = rng.standard_normal(len(on)) * (0.3 + 0.8 * wear) * 0.02 * np.abs(bow_v[on]) * REF / beta[on]
    force = bowed.run_primed(period, bridge_len, bow_v, np.maximum(grip, 1e-4), hair + catch, pole, bowed.GAIN,
                             at, velocity)
    # The friction re-sharpens the corner every period, so the loop's rounding moves the tone only a little (about
    # 1 dB at 2 kHz over its whole range). What makes a heavier bow brighter is the corner's rounding at the bow,
    # which shrinks as the force grows (Cremer): stood in for by a shelf on the force above 1 kHz, a few dB up
    # for a loud note or a bright player, down for a soft one; eased from note to note over 20 ms.
    ease = int(0.02 * sr)
    shelf = uniform_filter1d(shelf, ease)
    force = force + shelf * fx.equalize(force, fx.design((("hp", 1000.0, 1),), sr))
    if glass.any():
        # Sul ponticello is brighter than any Helmholtz motion: a light bow near the bridge sets the string's upper
        # modes going too (Schelleng's surface sound), which one waveguide can't. Stood in for by tilting the
        # force: the fundamental region down, the upper partials up.
        glass = uniform_filter1d(glass, ease)
        force = force + glass * (fx.equalize(force, fx.design(GLASS, sr)) - force)
    return force


def _pizz(kind: Kind, note, sr: int, rng: np.random.Generator, s: dict, ring: float) -> np.ndarray:
    """A pizzicato: the fingertip over the end of the fingerboard, the note left to ring `ring` s at most."""
    opens = [o for o in kind.strings if o <= note.pitch + 0.3]
    string = opens[-1] if opens else kind.strings[0]
    stopped = note.pitch - string > 0.3
    point = min(0.45, kind.fingerboard * 2.0 ** ((note.pitch - string) / 12.0))
    y = pluck.pluck(midi_to_hz(note.pitch), max(note.dur, ring), sr, rng, vel=note.vel,
                    brightness=0.25 + 0.3 * float(s["brightness"]) * (0.8 + 0.4 * note.vel),
                    decay=kind.ring * (1.0 if stopped else 1.8), pick=point * rng.uniform(0.9, 1.1),
                    hardness=0.1 + 0.1 * note.vel, planes=0.3, touch=0.15, damp=0.1)
    return y * PIZZ


def player(kind: Kind, notes, sr: int, length: int, rng: np.random.Generator, s: dict, q: dict | None = None,
           ) -> np.ndarray:
    """One player's line (bowed and plucked notes, one at a time): the string's force on the bridge."""
    q = {"position": 1.0, "depth": 1.0, "rate": 1.0, **(q or {})}
    force = np.zeros(length)
    notes = [n for n in sorted(notes, key=lambda n: n.start) if n.start * sr < length and n.dur > 0]
    bows = [n for n in notes if n.art != "pizz"]
    for group, s0, s1 in _segments(bows, sr, length):
        local = [replace(n, start=n.start - s0 / sr) for n in group]
        y = _bowed(kind, local, sr, s1 - s0, rng, s, q)
        fade = min(len(y), int(0.25 * sr))
        y[len(y) - fade:] *= np.linspace(1.0, 0.0, fade) ** 2
        force[s0:s1] += y
    plucks = [n for n in notes if n.art == "pizz"]
    for k, note in enumerate(plucks):
        i0 = int(round(note.start * sr))
        after = [n.start for n in notes if n.start > note.start + 0.02]
        ring = min(1.2, (after[0] - note.start) if after else 1.2)
        y = _pizz(kind, note, sr, rng, s, ring)
        end = min(length, i0 + len(y))
        force[i0:end] += y[: end - i0]
    return force


def _settings(settings: dict) -> dict:
    return {"brightness": 0.5, "wear": 0.25, "ornament": 0.5, "body": 1.0, **settings}


def _solo(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
          s: dict) -> np.ndarray:
    kind = KINDS[name]
    wear = float(s["wear"])
    # the maker's instrument and its player: the body, the player's vibrato and bow placement, and the open
    # strings' own tuning (stopped notes the player puts right by ear; the open strings stay where they are)
    seed = int(make.integers(1 << 30))
    q = {"rate": float(make.uniform(0.92, 1.08)), "depth": float(make.uniform(0.85, 1.15)),
         "position": float(make.uniform(0.9, 1.1))}
    tuning = {o: float(make.normal(0.0, 0.5 + 3.0 * wear)) for o in kind.strings}
    notes = [replace(n, pitch=n.pitch + tuning[int(round(n.pitch))] / 100.0)
             if abs(n.pitch - round(n.pitch)) < 0.01 and int(round(n.pitch)) in tuning else n for n in notes]
    force = np.zeros(length)
    for line in lines(notes):
        force += player(kind, line, sr, length, rng, s, q)
    force = sosfilt(butter(1, 25.0, btype="highpass", fs=sr, output="sos"), force)
    ir = voiced(body.impulse_response(kind.box, sr, seed=seed, size=float(s["body"])), sr)
    return body.resonate(force, ir)


# The string section: who sits where, how many to a line, and the register each takes (a line's median pitch).
SECTIONS = (("violins", VIOLIN, -0.6, 3), ("violas", VIOLA, 0.1, 2), ("cellos", CELLO, 0.55, 2))
CROWD = 2  # a part of more lines than this has two players to every line (the cost of a chord stays in bounds)
SPLITS = (62.0, 52.0)  # a line whose median pitch is at or above the first goes to the violins, above the second
SEAT_SPREAD = 0.12  # the two desks of a section either side of its seat
SECTION_IR = 0.35  # seconds of each section body kept


def voiced(ir: np.ndarray, sr: int, lo: float = 80.0, hi: float = 3000.0) -> np.ndarray:
    """A body's response scaled so a bowed string sounds as loud through any maker's box: its power gain averaged
    over lo..hi on a log grid, each frequency weighted as a sawtooth's harmonics are (1/f), is 1. (The box is
    normalized over its whole band; where the modes fall under a cello's low fundamentals moves its loudness
    by 2 to 3 dB from maker to maker.)"""
    n = 1 << 16
    spectrum = np.abs(np.fft.rfft(ir.mean(axis=1) if ir.ndim == 2 else ir, n)) ** 2
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    grid = np.exp(np.linspace(np.log(lo), np.log(hi), 256))
    weight = 1.0 / grid
    gain = np.sum(np.interp(grid, freqs, spectrum) * weight) / np.sum(weight)
    return ir / np.sqrt(max(gain, 1e-12))


def _pan(y: np.ndarray, position: float) -> np.ndarray:
    theta = (position + 1.0) * np.pi / 4.0
    return np.stack([y * np.cos(theta), y * np.sin(theta)], axis=1) * np.sqrt(2.0)


def _section(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
             s: dict) -> np.ndarray:
    wear, size = float(s["wear"]), float(s["body"])
    # the maker's section, drawn in a fixed order whatever the part: two bodies a section, sixteen players' ways
    seeds = {name: [int(make.integers(1 << 30)) for _ in range(2)] for name, *_ in SECTIONS}
    ways = {name: [dict(detune=float(make.choice([-1.0, 1.0]) * make.uniform(3.0, 8.0)),
                        late=float(make.uniform(0.0, 0.015)), rate=float(make.uniform(0.9, 1.1)),
                        depth=float(make.uniform(0.7, 1.2)), position=float(make.uniform(0.85, 1.15)))
                   for _ in range(16)] for name, *_ in SECTIONS}
    # how far apart the players' tunings sit: 3 to 8 cents at the default wear, a quarter of that new, twice worn
    spread = min(2.0, 0.25 + 3.0 * wear)
    groups: dict[str, list] = {name: [] for name, *_ in SECTIONS}
    for line in lines(notes):
        middle = float(np.median([n.pitch for n in line]))
        name = "violins" if middle >= SPLITS[0] else "violas" if middle >= SPLITS[1] else "cellos"
        low = dict((n, k.strings[0]) for n, k, *_ in SECTIONS)[name]
        groups[name].append([replace(n, pitch=n.pitch + 12.0 * np.ceil((low - n.pitch) / 12.0)) if n.pitch < low
                             else n for n in line])
    out = np.zeros((length, 2))
    looseness = 0.012 + 0.02 * wear
    crowd = sum(len(g) for g in groups.values())
    for name, kind, seat, most in SECTIONS:
        players = most if crowd <= CROWD else 2
        if not groups[name]:
            continue
        desks = [np.zeros(length), np.zeros(length)]
        k = 0
        for line in groups[name]:
            desk = [ways[name][(k + j) % 16] for j in range(players)]
            centre = np.mean([way["detune"] for way in desk])  # the line's players agree on its pitch on average
            for way in desk:
                way = {**way, "detune": (way["detune"] - centre) * spread}
                played = _loosen(line, way, looseness, rng)
                desks[k % 2] += player(kind, played, sr, length, rng, s, way)
                k += 1
        box = replace(kind.box, length=SECTION_IR)
        for d, force in enumerate(desks):
            if not force.any():
                continue
            force = sosfilt(butter(1, 25.0, btype="highpass", fs=sr, output="sos"), force)
            ir = voiced(body.impulse_response(box, sr, seed=seeds[name][d], size=size, channels=1)[:, 0], sr)
            y = oaconvolve(force, ir)[:length]
            out += _pan(y, seat + (SEAT_SPREAD if d else -SEAT_SPREAD))
    return out


def _loosen(line, way: dict, looseness: float, rng: np.random.Generator) -> list:
    """A section player's own reading of a line: a few cents off, each note a little early or late where the line
    moves on (a note tied into the next still meets it), and up to 40 ms late where it comes in after a rest (a
    section's entry spreads; nobody speaks before the beat)."""
    out = []
    shifts = np.clip(way["late"] + rng.normal(0.0, looseness, len(line) + 1), -0.04, 0.04)
    for k, note in enumerate(line):
        end = note.start + note.dur
        joined = k + 1 < len(line) and line[k + 1].start - end < 0.02
        entry = k == 0 or note.start - (line[k - 1].start + line[k - 1].dur) >= 0.02
        start = note.start + (abs(shifts[k]) if entry else shifts[k])
        stop = (line[k + 1].start + shifts[k + 1]) if joined else end + shifts[-1] * 0.5
        if joined and k + 1 < len(line):
            stop = max(stop, start + 0.02)
        out.append(replace(note, start=max(0.0, start), dur=max(0.02, stop - start),
                           pitch=note.pitch + way["detune"] / 100.0))
    return out


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The instrument's dry stereo stem, `length` samples (before its place and level)."""
    s = _settings(settings)
    notes = tuple(n for n in notes if n.start * sr < length and n.dur > 0)
    if not notes:
        return np.zeros((length, 2))
    if name == "strings":
        return _section(notes, sr, length, rng, make, s)
    if name in KINDS:
        return _solo(name, notes, sr, length, rng, make, s)
    raise ValueError(f"no such instrument: {name}")
