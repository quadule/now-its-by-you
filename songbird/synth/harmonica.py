"""A ten-hole diatonic harmonica in Richter tuning: its key chosen for the part, bends, tongue-blocking, the hands.

Each hole has two reeds, one sounding on the breath out (blow) and one in
(draw). Richter tuning puts the major chord on every blow hole and the scale
in the middle octave only: holes 4 to 7 play every note of the key; below
them the draw notes skip the fourth and sixth, above them the seventh, and
those gaps are filled by bending. A draw note in holes 1 to 6 bends down by
1, 2, 3, 1, 1/2 and 1 semitones and a blow note in holes 8 to 10 by 1, 1 and 2
(hole 7 not at all): the player's mouth and throat, tuned just above the
reed, pull its pitch toward the other reed's (Bahnson, Antaki and Beery,
JASA 1998). An overblow (holes 1, 4, 5, 6) or overdraw (7, 9, 10) sounds a
semitone above the other reed and fills the rest.

The harp. Harps come in twelve keys, their hole 1 blow note from G3 to F#4.
For a part, the harp is the one that plays its notes with the fewest bends
(a semitone of bend costs 1, an overblow 4, a note moved an octave into the
harp's range 3), among first position (the harp in the song's key: every
tune that has the major seventh), second position ("cross harp": the harp a
fourth above the key, the blues harp, only when the tune has the flat
seventh) and third (a tone below the key: dorian, only for a minor tune
with no major third). Each note then takes the hole that plays it with the
least bending, nearest the hole before.

The reed. A free reed chops the air into pulses, so its tone is rich in
harmonics; blown harder, the pulse sharpens and the tone brightens (the
spectrum's slope rises from harmonic k**-1.6 toward k**-0.85 with the
breath: reed.tables, cross-faded by the breath's pressure). A reed speaks in
10 to 30 ms, the low ones slowest; blow and draw notes differ in the
player's mouth (a lower, rounder resonance drawing, and lower still when
bending). A bent note is approached from the unbent reed (a semitone of
bend in about 80 ms), darker and weaker. The breath itself hisses, most as
a note is tongued.

Articulations: "" (tongued; a note the harp can't play natural is bent
into), "slur" (the breath carries on), "bend" (a blues bend: a natural note
scooped up from a semitone under, a bent one drawn down slowly from the
unbent reed), "slap" (tongue-blocked: the hole and the three to its left
burst together, then the tongue leaves the one note), "chord" (the note with
the two holes to its left, the same breath: a vamp), "octave" (the tongue
split: the note and the hole three to its left), "wah" (the cupped hands
open over the note), "trem" (the hands flutter open and shut).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numba import njit
from scipy.signal import butter, oaconvolve, sosfilt

from ..theory import midi_to_hz
from . import body, reed

BLOW = (0, 4, 7, 12, 16, 19, 24, 28, 31, 36)  # semitones above hole 1's blow note, holes 1 to 10
DRAW = (2, 7, 11, 14, 17, 21, 23, 26, 29, 33)
DRAW_BENDS = (1, 2, 3, 1, 0, 1, 0, 0, 0, 0)  # whole semitones a draw note bends (hole 5's is half a semitone)
BLOW_BENDS = (0, 0, 0, 0, 0, 0, 0, 1, 1, 2)
OVERBLOWS = (0, 3, 4, 5)  # holes (from 0) whose overblow sounds a semitone over the draw note
OVERDRAWS = (6, 8, 9)  # holes whose overdraw sounds a semitone over the blow note
KEYS = range(55, 67)  # hole 1's blow note: a G harp (G3) to an F# harp (F#4)
COSTS = dict(natural=0.0, over=4.0, moved=3.0, missing=20.0)  # a bend costs its semitones

ARTICULATIONS = {
    "": "tongued; a note the harp can't play natural is bent into (or overblown), from the unbent reed",
    "slur": "the breath carries on from the note before (a dip if its direction turns)",
    "bend": "a blues bend: a natural note scooped up from a semitone under; a bent one drawn down slowly",
    "slap": "tongue-blocked: the hole and the three to its left burst together, then the tongue leaves the one note",
    "chord": "the note with the two holes to its left on the same breath: a tongue-blocked vamp",
    "octave": "the tongue split: the note and the hole three to its left (an octave on the blow notes)",
    "wah": "the cupped hands open over the note: a resonance sweeping up from muffled to bright",
    "trem": "hand tremolo: the hands flutter open and shut, five or six times a second",
}

SPEC = {
    "harmonica": dict(
        family="reed", role="lead", register=(60, 96), place=(-0.3, 0.1), level=0.306, poly=False,
        articulations=ARTICULATIONS,
        about="a ten-hole diatonic harmonica (Richter), its key chosen for the part (first position, or cross harp "
              "when the tune has the flat seventh); every scale note natural only in the middle octave (holes 4-7), "
              "gaps below bent into; notes outside its three octaves are moved by octaves",
    ),
}


@dataclass(frozen=True)
class Reed:
    """How one note is played: the hole (0-9), the breath ("blow" or "draw"), semitones bent (0: natural; -1: an
    overblow or overdraw), and the pitch it sounds."""

    hole: int
    breath: str
    bend: float
    pitch: int


def layout(key: int) -> dict[int, list[tuple[float, Reed]]]:
    """Every pitch a harp in `key` (MIDI of hole 1 blow) plays, and how: pitch -> [(cost, Reed), ...]."""
    out: dict[int, list] = {}

    def add(pitch, cost, hole, breath, bend):
        out.setdefault(pitch, []).append((cost, Reed(hole, breath, bend, pitch)))

    for h in range(10):
        add(key + BLOW[h], 0.0, h, "blow", 0)
        add(key + DRAW[h], 0.0, h, "draw", 0)
        for b in range(1, DRAW_BENDS[h] + 1):
            add(key + DRAW[h] - b, float(b), h, "draw", b)
        for b in range(1, BLOW_BENDS[h] + 1):
            add(key + BLOW[h] - b, float(b), h, "blow", b)
        if h in OVERBLOWS:
            add(key + DRAW[h] + 1, COSTS["over"], h, "blow", -1)
        if h in OVERDRAWS:
            add(key + BLOW[h] + 1, COSTS["over"], h, "draw", -1)
    return out


def _fit(pitch: int, key: int) -> tuple[int, float]:
    """The pitch moved by octaves into a harp's range (hole 1 blow to hole 10 blow), and what the move costs."""
    moved = pitch
    while moved < key:
        moved += 12
    while moved > key + 36:
        moved -= 12
    return moved, (COSTS["moved"] if moved != pitch else 0.0)


def harp(notes, tonic: int) -> tuple[int, int]:
    """The harp for a part: (its key as MIDI of hole 1 blow, its position 1, 2 or 3)."""
    pcs = {(int(round(n.pitch)) - tonic) % 12 for n in notes}
    candidates = [(1, tonic % 12)]
    if 10 in pcs:  # the flat seventh: cross harp
        candidates.append((2, (tonic + 5) % 12))
    if 3 in pcs and 4 not in pcs:  # minor: a harp a tone below plays dorian
        candidates.append((3, (tonic + 10) % 12))
    best = None
    for position, pc in candidates:
        key = next(k for k in KEYS if k % 12 == pc)
        where = layout(key)
        cost = 0.0
        for n in notes:
            moved, extra = _fit(int(round(n.pitch)), key)
            cost += extra + (min(c for c, _ in where[moved]) if moved in where else COSTS["missing"])
        if best is None or cost < best[0] - 1e-9:
            best = (cost, key, position)
    return best[1], best[2]


def fingering(notes, key: int) -> list[Reed | None]:
    """Each note's hole, breath and bend on this harp: the least bending, then the nearest hole to the last."""
    where = layout(key)
    out: list[Reed | None] = []
    last = None
    for n in notes:
        moved, _ = _fit(int(round(n.pitch)), key)
        choices = where.get(moved)
        if not choices:
            out.append(None)
            continue
        cost, chosen = min(choices, key=lambda c: (c[0], abs(c[1].hole - last.hole) if last else 0,
                                                    c[1].breath != (last.breath if last else "blow")))
        out.append(chosen)
        last = chosen
    return out


# --- the sound ----------------------------------------------------------------------------------------

SLOPES = (1.6, 0.85)  # harmonic k's amplitude as k**-slope: a gentle breath, a hard one
SPEAK = (0.004, 0.011)  # the reed's build-up time constant (s) at C5 and at C4 and below: speaks in 10-30 ms
BREATH = 0.035  # breath hiss against the tone


def _mouth(breath: str, bent: bool, size: float):
    """The player's mouth and throat over the reed: a resonance near 1.2 kHz blowing, lower and rounder drawing,
    lower still with the tongue pulled back to bend; and the cover plates' bright hump."""
    first = (1200.0 if breath == "blow" else 850.0) * (0.7 if bent else 1.0) / size

    def shape(f):
        g = 1.0 + 1.2 * np.exp(-0.5 * (np.log2(f / first) / 0.5) ** 2)
        g += 0.8 * np.exp(-0.5 * (np.log2(f / 2900.0) / 0.4) ** 2)
        return g

    return shape


@njit(cache=True)
def _hands(x, opening, sr):
    """The cupped hands over the harp: a resonant low-pass (a topology-preserving state-variable filter) whose
    corner rises from 350 Hz shut to 2.8 kHz open, blended with the open sound by how open they are."""
    n = x.shape[0]
    y = np.zeros(n)
    ic1 = 0.0
    ic2 = 0.0
    for i in range(n):
        o = opening[i]
        fc = 350.0 * 2.0 ** (3.0 * o)
        g = np.tan(np.pi * fc / sr)
        k = 1.0 / (2.5 - 1.8 * o)
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        w = o * o
        y[i] = w * x[i] + (1.0 - w) * v2
    return y


def _envelope(m: int, sr: int, vel: float, attack: float, start: float, tail: int) -> np.ndarray:
    """The breath's pressure over a note of m samples plus a `tail` of samples it eases off over: rising from
    `start` (0 fresh, near 1 carried on) in `attack` s."""
    n = m + tail
    env = np.ones(n) * vel
    a = max(1, min(m, int(attack * sr)))
    env[:a] = vel * (start + (1.0 - start) * np.sin(0.5 * np.pi * np.linspace(0.0, 1.0, a)))
    r = max(1, tail)
    env[m:] = vel * np.cos(0.5 * np.pi * np.linspace(0.0, 1.0, r)) ** 2
    return env


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The harmonica's dry mono stem, `length` samples (before its place and level)."""
    s = {"brightness": 0.5, "wear": 0.25, "ornament": 0.5, "body": 1.0, "tonic": 62, **settings}
    bright, wear, ornament = float(s["brightness"]), float(s["wear"]), float(s["ornament"])
    # the maker's harp and its player: the comb's ring, every reed's own tuning (worn draw reeds 1-4, the ones
    # bent most, sag flat), the player's mouth and vibrato, drawn in a fixed order
    seed = int(make.integers(1 << 30))
    tuning = {(h, b): float(make.normal(0.0, 0.5 + 3.0 * wear)) - (3.0 * wear if b == "draw" and h < 4 else 0.0)
              for h in range(10) for b in ("blow", "draw")}
    mouth = float(make.uniform(0.9, 1.12))
    rate = float(make.uniform(4.6, 5.8))
    notes = sorted((n for n in notes if n.start * sr < length and n.dur > 0), key=lambda n: n.start)
    out = np.zeros(length)
    if not notes:
        return out
    key, _ = harp(notes, int(s["tonic"]))
    reeds = fingering(notes, key)
    cache: dict = {}

    def waves(pitch: float, breath: str, bent: bool, over: bool, top: float):
        k = (round(pitch, 2), breath, bent, over)
        if k not in cache:
            slopes = (SLOPES[0] + (0.25 if over else 0.0), SLOPES[1] + (0.25 if bent else 0.0))
            cache[k] = reed.tables(midi_to_hz(pitch), sr, rng, slopes, even=0.8 if breath == "blow" else 0.9,
                                   shape=_mouth(breath, bent, mouth), top=top)
        return cache[k]

    hiss_sos = butter(2, (900.0, 6000.0), btype="bandpass", fs=sr, output="sos")
    last_end, last_reed = -1.0, None
    for k, (note, played) in enumerate(zip(notes, reeds)):
        if played is None:
            continue
        i0 = int(round(note.start * sr))
        m = max(1, min(length - i0, int(round(note.dur * sr))))
        after = notes[k + 1] if k + 1 < len(notes) else None
        joined = note.start - last_end < 0.02 and last_reed is not None
        carried = joined and note.art == "slur"
        turned = carried and last_reed.breath != played.breath
        tail = int((0.012 if after is not None and after.start - (note.start + note.dur) < 0.02 else 0.035) * sr)
        tail = min(tail, length - i0 - m)
        n = m + max(0, tail)
        t = np.arange(n) / sr
        vel = float(np.clip(note.vel, 0.0, 1.0))
        attack = 0.018 if turned else (0.008 if carried else 0.012)
        pressure = _envelope(m, sr, vel, attack, 0.0 if not carried or turned else 0.8, max(0, tail))
        if turned:  # the breath turns round: a dip
            pressure[: int(0.012 * sr)] *= np.linspace(0.3, 1.0, min(n, int(0.012 * sr)))
        # pitch against the reed as it sounds: a bend approached from the unbent reed, a blues scoop, the throat's
        # vibrato on long notes, a hard breath a little flat
        cents = np.zeros(n)
        bent = played.bend > 0
        over = played.bend < 0
        if bent:
            glide = min(n, int((0.05 + 0.03 * played.bend + (0.08 if note.art == "bend" else 0.0)) * sr))
            cents[:glide] += 100.0 * played.bend * (1.0 - np.linspace(0.0, 1.0, glide)) ** 2
        elif note.art == "bend" and _bends(played):
            glide = min(n, int(0.14 * sr))
            cents[:glide] -= 100.0 * (1.0 - np.linspace(0.0, 1.0, glide)) ** 1.5
        if note.dur > 0.5 and ornament > 0:
            depth = (4.0 + 14.0 * ornament) * np.clip((t - 0.2) / 0.3, 0.0, 1.0)
            cents += depth * np.sin(2 * np.pi * rate * t + rng.uniform(0, 6.28))
            pressure *= 1.0 + 0.12 * ornament * np.clip((t - 0.2) / 0.3, 0.0, 1.0) * \
                np.sin(2 * np.pi * rate * t + 1.2)
        cents += tuning[(played.hole, played.breath)] - 6.0 * (vel - 0.6)
        pitch = played.pitch + (note.pitch - round(note.pitch))
        freq = midi_to_hz(pitch) * 2.0 ** (cents / 1200.0)
        # the reed builds up (low reeds slower), and the tone brightens with the breath; bent notes are darker and
        # weaker, overblows thin
        speak = SPEAK[0] + (SPEAK[1] - SPEAK[0]) * np.clip((72.0 - pitch) / 12.0, 0.0, 1.0)
        speak *= 1.15 if played.breath == "draw" else 1.0
        build = 1.0 if carried and not turned else 1.0 - np.exp(-t / speak)
        # tongue-blocked companions on the same breath, which the breath is shared among: each reed of a three-hole
        # chord gets 1/sqrt(3) of a single note's drive (a slap's burst, until the tongue lands, 1/2)
        others = []
        if note.art in ("slap", "chord"):
            others = [h for h in range(played.hole - (3 if note.art == "slap" else 2), played.hole) if h >= 0]
        elif note.art == "octave" and played.hole >= 3:
            others = [played.hole - 3]
        together = np.full(n, 1.0 if others else 0.0)
        if note.art == "slap" and others:
            cut = min(n, int(rng.uniform(0.035, 0.06) * sr))
            fade = min(n - cut, int(0.008 * sr))
            together[cut:] = 0.0
            together[cut: cut + fade] = np.linspace(1.0, 0.0, fade)
        share = 1.0 / np.sqrt(1.0 + len(others) * together)
        drive = pressure * share
        mix = np.clip(0.2 + 0.5 * bright + 1.1 * (drive - 0.6) - (0.3 if bent else 0.0), 0.0, 1.0)
        dark, brightw = waves(pitch, played.breath, bent, over, freq.max())
        sound = np.zeros(n)
        reed._read_mix(dark, brightw, freq / sr, drive * build * (0.4 if bent else 0.6 if over else 1.0), mix,
                       sound, 0, rng.random())
        for h in others:
            p = key + (BLOW if played.breath == "blow" else DRAW)[h]
            f = midi_to_hz(p) * 2.0 ** ((tuning[(h, played.breath)] - 6.0 * (vel - 0.6)) / 1200.0)
            d2, b2 = waves(float(p), played.breath, False, False, f)
            reed._read_mix(d2, b2, np.full(n, f / sr), drive * build * together, mix, sound, 0, rng.random())
        # the breath's hiss, strongest as the note is tongued
        hiss = sosfilt(hiss_sos, rng.standard_normal(n + 64))[64:]
        burst = 1.0 + (2.5 if not carried else 0.5) * np.exp(-t / 0.015)
        sound += hiss * pressure * burst * BREATH * (1.2 if played.breath == "draw" else 1.0) * (1.0 + 1.5 * wear)
        if note.art in ("wah", "trem"):
            if note.art == "wah":
                opening = np.clip(t / max(0.12, min(0.3, 0.5 * note.dur)), 0.0, 1.0) ** 1.5 * 0.95 + 0.05
            else:
                opening = 0.55 + 0.4 * np.sin(2 * np.pi * rng.uniform(5.0, 6.5) * t - 0.5 * np.pi)
            sound = _hands(sound, opening, float(sr))
        end = min(length, i0 + n)
        out[i0:end] += sound[: end - i0]
        last_end, last_reed = note.start + note.dur, played
    ir = body.impulse_response(body.HARMONICA, sr, seed=seed, size=float(s["body"]), channels=1)[:, 0]
    y = oaconvolve(out, ir)[:length]
    # a reed's pulses of air aren't zero-mean: no DC leaves the harp
    return sosfilt(butter(1, 20.0, btype="highpass", fs=sr, output="sos"), y)


def _bends(played: Reed) -> bool:
    """Whether a natural note can be bent: a draw note in holes 1-6, a blow note in holes 8-10."""
    return played.bend == 0 and ((played.breath == "draw" and played.hole < 6)
                                 or (played.breath == "blow" and played.hole >= 7))
