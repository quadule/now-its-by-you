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
fourth above the key; a blues player's, who takes it unless it bends more
than half a semitone a note beyond the straight harp) and third (a tone
below the key: dorian, only for a minor tune with no major third). Each note
then takes the hole that plays it with the least bending (a reed that bends
for a note to be bent, slid into or shaped by the hands, and on the cross
harp), nearest the hole before.

The reed. A free reed chops the air into pulses, so its tone is rich in odd
and even harmonics, within 20 dB to 5-8 kHz in the middle holes; blown
harder, the pulse sharpens and the tone brightens (the slope over the first
twelve harmonics from about -10 dB an octave soft to -5 hard: reed.tables,
cross-faded by the breath's pressure). The mouth's resonance follows the
note (near its third harmonic, a little lower drawing, so blow and draw
notes are alike), a small source radiates its low harmonics weakly, and the
cover plates add a hump near 3 kHz. A reed speaks in 15-25 ms at a
mezzo-forte breath in the middle holes, twice that soft or an octave lower,
10 ms hard, starting a few cents sharp. Harps are tuned sharp and sag as the
breath presses them (a soft note sharp, a hard one flat, the long low reeds
most), each maker's in equal temperament or a compromise one (the blow
chord's third 5 cents low), a blues player's sometimes the old Marine
Band's, nearer just intonation. The throat's vibrato pulses the breath (3-6 dB) and dips the
pitch only on a reed that bends. A bent note is attacked a little above and
held by ear, a few cents off and wavering; weaker and darker. The breath
itself hisses, about as loud however hard it blows, most as a note is
tongued.

Joins. Notes that follow straight on are joined as the mouth joins them:
across holes on one breath the lips slide (the old reed dying away as the
new speaks, a hole passed on the way sounding for a moment), a breath that
turns round (blow to draw) dips, and the same reed again is tongued, the air
stopped for 15-25 ms. A singer-songwriter's harp is held in a neck rack
(the style "songwriter"): no hands on it.

Articulations: "" (joined as above: tongued after a rest, slid on across
the holes straight after a note; a note the harp can't play natural is bent
into), "slur" (the breath carries on, even over the same reed), "bend" (a blues bend: a natural note
scooped up from a semitone under, a bent one drawn down slowly from the
unbent reed), "slide" (a reed that bends scooped into, any
other slid onto across the next hole), "slap" (tongue-blocked: the hole and
the three to its left burst together, then the tongue leaves the one note),
"chord" (the note with the two holes to its left, the same breath: a vamp;
notes written together are played so too), "octave" (the tongue split: the
note and its octave three or four holes down, where there is one), "wah"
(the cupped hands open over the note), "trem" (the hands flutter open and
shut).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from ..theory import midi_to_hz
from . import body, oa, reed
from .iir import butter

BLOW = (0, 4, 7, 12, 16, 19, 24, 28, 31, 36)  # semitones above hole 1's blow note, holes 1 to 10
DRAW = (2, 7, 11, 14, 17, 21, 23, 26, 29, 33)
DRAW_BENDS = (1, 2, 3, 1, 0, 1, 0, 0, 0, 0)  # whole semitones a draw note bends (hole 5's is half a semitone)
BLOW_BENDS = (0, 0, 0, 0, 0, 0, 0, 1, 1, 2)
OVERBLOWS = (0, 3, 4, 5)  # holes (from 0) whose overblow sounds a semitone over the draw note
OVERDRAWS = (6, 8, 9)  # holes whose overdraw sounds a semitone over the blow note
KEYS = range(55, 67)  # hole 1's blow note: a G harp (G3) to an F# harp (F#4)
COSTS = dict(natural=0.0, over=4.0, moved=3.0, missing=20.0)  # a bend costs its semitones

ARTICULATIONS = {
    "": "tongued after a rest; straight after a note, slid on across the holes on one breath (the breath turning "
        "round with a dip, the same reed tongued); a note the harp can't play natural is bent into (or overblown)",
    "slur": "the breath carries on from the note before (a dip if its direction turns; the same reed keeps "
            "swinging)",
    "bend": "a blues bend: a natural note scooped up from a semitone under; a bent one drawn down slowly",
    "slide": "slid into: a reed that bends scooped up from a little under the note, any other reached across the "
             "next hole on the same breath",
    "slap": "tongue-blocked: the hole and the three to its left burst together, then the tongue leaves the one note",
    "chord": "the note with the two holes to its left on the same breath: a tongue-blocked vamp (notes written "
             "together are one breath over their holes)",
    "octave": "the tongue split: the note and its octave, three holes down blowing, 4 over 1 and 7-10 over the "
              "hole four down drawing (none on 2, 3, 5 or 6 draw)",
    "wah": "the cupped hands open over the note: a resonance sweeping up from muffled to bright",
    "trem": "hand tremolo: the hands flutter open and shut, five or six times a second",
}

SPEC = {
    "harmonica": dict(
        family="reed", role="lead", register=(60, 96), place=(-0.3, 0.1), level=0.328, poly=False,
        articulations=ARTICULATIONS,
        about="a ten-hole diatonic harmonica (Richter), its key chosen for the part (first position, or cross harp "
              "when it bends less, and in the blues); every scale note natural only in the middle octave (holes "
              "4-7), gaps below bent into; notes outside its three octaves are moved by octaves; joined notes slide "
              "across the holes on one breath; in a neck rack for the songwriter style",
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


CROSS = 0.5  # in the blues, the cross harp's bending forgiven per note: it's the blues player's harp


def harp(notes, tonic: int, style: str = "") -> tuple[int, int]:
    """The harp for a part: (its key as MIDI of hole 1 blow, its position 1, 2 or 3). A blues player reaches for
    the cross harp unless it bends more than half a semitone a note beyond the straight harp."""
    pcs = {(int(round(n.pitch)) - tonic) % 12 for n in notes}
    blues = style == "blues"
    candidates = [(1, tonic % 12)]
    if 10 in pcs or blues:  # the flat seventh (or the blues): cross harp
        candidates.append((2, (tonic + 5) % 12))
    if 3 in pcs and 4 not in pcs:  # minor: a harp a tone below plays dorian
        candidates.append((3, (tonic + 10) % 12))
    best = None
    for position, pc in candidates:
        key = next(k for k in KEYS if k % 12 == pc)
        where = layout(key)
        cost = -CROSS * len(notes) if blues and position == 2 else 0.0
        for n in notes:
            moved, extra = _fit(int(round(n.pitch)), key)
            cost += extra + (min(c for c, _ in where[moved]) if moved in where else COSTS["missing"])
        if best is None or cost < best[0] - 1e-9:
            best = (cost, key, position)
    return best[1], best[2]


def fingering(notes, key: int, position: int = 1) -> list[Reed | None]:
    """Each note's hole, breath and bend on this harp: the least bending; for a note to be bent, slid into or
    shaped by the hands (and any note on the cross harp), a reed that bends; then the nearest hole to the last, and
    the same breath (drawing, on the cross harp, whose player lives on the draw notes)."""
    where = layout(key)
    out: list[Reed | None] = []
    last = None
    for n in notes:
        moved, _ = _fit(int(round(n.pitch)), key)
        choices = where.get(moved)
        if not choices:
            out.append(None)
            continue
        scoop = n.art in ("bend", "slide", "wah", "trem") or position == 2
        cost, chosen = min(choices, key=lambda c: (c[0], scoop and not _bendable(c[1]),
                                                    abs(c[1].hole - last.hole) if last else 0,
                                                    c[1].breath != (last.breath if last else
                                                                    ("draw" if position == 2 else "blow"))))
        out.append(chosen)
        last = chosen
    return out


# --- the sound ----------------------------------------------------------------------------------------

SLOPES = (1.7, 0.85)  # harmonic k's amplitude as k**-slope: a gentle breath, a hard one
SPEAK = 0.008  # the reed's build-up time constant (s) at F#5 and a mezzo-forte breath, doubling every 14 semitones
# down (a heavier reed) and with a breath half as strong (its drive barely over its losses): 10-90% in 15-25 ms
# in the middle holes at mezzo-forte, 30-45 soft, 8-12 hard; 30-40 ms in holes 1 and 2
SAG = (8.0, 4.0, 5.0)  # cents a reed sags at a mezzo-forte breath (more, harder): holes 1-3; blow 4-10; draw 4-10
NOISE = 0.0069  # the breath's hiss: it grows only a little with the breath, so a soft note is the breathiest
PULSE = 0.5  # the throat vibrato's swing of the breath, at ornament 1
BENT_DB = 2.5  # dB a bent note's reed loses per semitone of bend (the mouth's resonance on its fundamental gives
# one of them back: about 1.5 dB a semitone in all)
HANDS = (1000.0, 4500.0, 0.16, 0.3)  # the cupped hands: low-pass corner shut and open (Hz), the leak between the
# fingers, and how much of the sound they soak up when shut (3 dB)
# A maker's temperament, cents per hole from 1 to 10 against equal temperament: a harp tuned for its chords
# (the blow chord's third a little low, as Hohner's compromise tunings, Pat Missin's measures), and the old Marine
# Band's, nearer just intonation (the thirds and the draw sevenths 11-12 cents low: a sweet blues chord, sour
# against a piano) that only a blues player carries
TEMPERAMENTS = {
    "equal": ((0,) * 10, (0,) * 10),
    "compromise": ((0, -5, 1, 0, -5, 1, 0, -5, 1, 0), (2, 4, 0, 5, 2, 6, 0, 5, 2, 6)),
    "classic": ((0, -12, 1, 0, -12, 1, 0, -12, 1, 0), (2, 1, -11, 2, -12, 3, -11, 2, -12, 3)),
}


def _mouth(f0: float, breath: str, bent: float, size: float):
    """The tone as it leaves the harp: the player's mouth and throat, a broad resonance tuned near the note's
    third harmonic (2.5 f0, a tenth lower drawing), pulled down between the first two when bending (and darker
    above, half a dB an octave for each semitone bent); a small source's radiation, rising 4 dB an octave up to
    1.3 kHz; the cover plates' hump, 3 dB near 3 kHz."""
    centre = (2.5 if not bent else 1.5) * (1.0 if breath == "blow" else 0.9) * f0 * size
    boost = 10.0 ** (3.0 / 20.0) - 1.0
    plates = 10.0 ** (3.0 / 20.0) - 1.0

    def shape(f):
        g = 1.0 + boost * np.exp(-0.5 * (np.log2(f / centre) / 0.6) ** 2)
        g *= 1.0 + plates * np.exp(-0.5 * (np.log2(f / 3000.0) / 0.35) ** 2)
        g *= np.minimum(f / 1300.0, 1.0) ** (4.0 / 6.02)
        if bent:
            g *= np.maximum(f / f0, 1.0) ** (-0.5 * min(bent, 2.0) / 6.02)
        return g

    return shape


@njit(cache=True, nogil=True)
def _hands(x, opening, sr, shut, wide, leak, absorb):
    """The cupped hands over the harp: a gentle low-pass (a topology-preserving state-variable filter) whose
    corner rises from `shut` Hz to `wide` Hz as they open, blended with the open sound by how open they are and
    never quite shut (`leak`: what still gets out between the fingers); shut, they also soak up `absorb` of it."""
    n = x.shape[0]
    y = np.zeros(n)
    ic1 = 0.0
    ic2 = 0.0
    for i in range(n):
        o = opening[i]
        fc = shut * (wide / shut) ** o
        g = np.tan(np.pi * fc / sr)
        k = 1.41
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = x[i] - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        w = leak + (1.0 - leak) * o * o
        y[i] = (1.0 - absorb * (1.0 - o)) * (w * x[i] + (1.0 - w) * v2)
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


def _joins(notes, reeds) -> list[str]:
    """How each note follows the one before, as a player's mouth and breath make it: "fresh" (a new breath, 150 ms
    or more after the last), "tongued" (after a short rest), and for notes that follow straight on (within 25
    ms): "moved" (the lips slide to another hole on the same breath, or a slur carries it), "turned" (the breath
    turns round, blow to draw or back) and "repeat" (the same reed again: the tongue stops the air)."""
    out, last, last_reed = [], None, None
    for note, played in zip(notes, reeds):
        if played is None:
            out.append("")
            continue
        gap = note.start - (last.start + last.dur) if last is not None else 1e9
        if gap >= 0.15:
            kind = "fresh"
        elif gap >= 0.025:
            kind = "tongued"
        elif last_reed.breath != played.breath:
            kind = "turned"
        elif last_reed.hole == played.hole and last_reed.bend == played.bend and note.art != "slur":
            kind = "repeat"
        else:
            kind = "moved"
        out.append(kind)
        last, last_reed = note, played
    return out


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The harmonica's dry mono stem, `length` samples (before its place and level)."""
    s = {"brightness": 0.5, "wear": 0.25, "ornament": 0.5, "body": 1.0, "tonic": 62, **settings}
    bright, wear, ornament = float(s["brightness"]), float(s["wear"]), float(s["ornament"])
    style = str(s.get("style") or "")
    racked = style == "songwriter"  # a singer-songwriter's harp sits in a neck rack: no hands on it
    # the maker's harp and its player: the body's seed, every reed's own tuning (worn draw reeds 1-4, the ones
    # bent most, sag flat), the player's mouth and vibrato, then the harp's temperament and how sharp it is
    # tuned (so that played at a mezzo-forte breath it sits 0 to 2 cents over the band), drawn in a fixed order
    seed = int(make.integers(1 << 30))
    tuning = {(h, b): float(make.normal(0.0, 0.5 + 3.0 * wear)) - (3.0 * wear if b == "draw" and h < 4 else 0.0)
              for h in range(10) for b in ("blow", "draw")}
    mouth = float(make.uniform(0.95, 1.05))
    rate = float(make.uniform(4.6, 5.8))
    kind = float(make.uniform())
    temper = s.get("temperament") or ("equal" if kind < 0.45 else
                                      "compromise" if kind < 0.85 or style != "blues" else "classic")
    over_band = float(make.uniform(0.0, 2.0))
    for (h, b) in tuning:  # (never more than 8 cents over the band at a mezzo-forte breath)
        tuning[(h, b)] = min(tuning[(h, b)] + TEMPERAMENTS[temper][b == "draw"][h] + over_band, 8.0) + _sag(h, b)
    notes = sorted((n for n in notes if n.start * sr < length and n.dur > 0), key=lambda n: (n.start, -n.pitch))
    out = np.zeros(length)
    if not notes:
        return out
    key, position = harp(notes, int(s["tonic"]), style)
    notes, under = _chords(notes)
    reeds = fingering(notes, key, position)
    joins = _joins(notes, reeds)
    cache: dict = {}

    def waves(pitch: float, breath: str, bent: float, over: bool, top: float):
        k = (round(pitch, 2), breath, bent, over)
        if k not in cache:
            slopes = (SLOPES[0] + (0.25 if over else 0.0), SLOPES[1] + (0.25 if over else 0.0))
            f0 = midi_to_hz(pitch)
            cache[k] = reed.tables(f0, sr, rng, slopes, even=0.8 if breath == "blow" else 0.9,
                                   shape=_mouth(f0, breath, bent, mouth), top=top)
        return cache[k]

    hiss_sos = butter(2, (900.0, 6000.0), btype="bandpass", fs=sr, output="sos")
    last_reed = None
    for k, (note, played) in enumerate(zip(notes, reeds)):
        if played is None:
            continue
        join = joins[k]
        after = next((j for j in range(k + 1, len(notes)) if reeds[j] is not None), None)
        then = joins[after] if after is not None else "fresh"
        i0 = int(round(note.start * sr))
        m = max(1, min(length - i0, int(round(note.dur * sr))))
        # how the note gives way to the next: the old reed dies away as the lips slide on (both sound a moment),
        # stops short as the breath turns, is cut by the tongue before the same reed again
        if then in ("moved", "turned"):  # the breath carries on (the lips sliding, or turning it round) until the
            # new note starts, over the part's few milliseconds of gap
            m = max(m, min(length - i0, int(round((notes[after].start - note.start) * sr))))
        if then in ("repeat", "turned"):  # the tongue stops the air, or the breath stops before turning round
            stop = rng.uniform(0.015, 0.025) if then == "repeat" else rng.uniform(0.002, 0.006)
            m = max(min(m, int(0.02 * sr)), m - int(stop * sr))  # never below 20 ms, nor longer than written
        tail = int({"moved": 0.03, "turned": 0.015, "repeat": 0.008}.get(then, 0.035) * sr)
        tail = max(0, min(tail, length - i0 - m))
        n = m + tail
        t = np.arange(n) / sr
        vel = float(np.clip(note.vel, 0.0, 1.0))
        carried = join == "moved"
        attack = {"moved": 0.01, "turned": 0.03, "repeat": 0.008}.get(join, 0.012)
        pressure = _envelope(m, sr, vel, attack, 0.8 if carried else 0.0, tail)
        # pitch against the reed as it sounds
        cents = np.zeros(n)
        bent = max(0.0, float(played.bend))
        over = played.bend < 0
        art = note.art
        if bent and art == "bend":  # a blues bend: held on the unbent reed a moment, then drawn down into the note
            hold = float(rng.uniform(0.03, 0.06))
            glide = float(rng.uniform(0.12, 0.25))
            x = np.clip((t - hold) / glide, 0.0, 1.0)
            cents += 100.0 * bent * (1.0 - x * x * (3.0 - 2.0 * x))
        elif bent and not carried:  # a bent note is attacked a little above and settles
            glide = min(n, int(rng.uniform(0.08, 0.14) * sr))
            cents[:glide] += rng.uniform(20.0, 45.0) * (1.0 - np.linspace(0.0, 1.0, glide)) ** 2
        elif art in ("bend", "slide") and _bends(played):  # scooped up from under, as deep as the reed bends
            deep = min(1.0, _depth(played))
            depth = rng.uniform(60.0, 100.0) if art == "bend" else rng.uniform(40.0, 70.0)
            glide = min(n, int((rng.uniform(0.08, 0.16) if art == "bend" else rng.uniform(0.1, 0.2)) * sr))
            cents[:glide] -= deep * depth * (1.0 - np.linspace(0.0, 1.0, glide)) ** 1.5
        if bent:  # the mouth holds a bent note by ear: a little off, and wavering
            cents += rng.normal(-3.0, 8.0) if bent >= 2 else rng.normal(0.0, 5.0)
            size = rng.uniform(5.0, 8.0) / 2.0
            cents += size * np.clip(t / 0.1, 0.0, 1.0) * (
                np.sin(2 * np.pi * rng.uniform(0.5, 2.0) * t + rng.uniform(0, 6.28)) +
                0.6 * np.sin(2 * np.pi * rng.uniform(0.5, 2.0) * t + rng.uniform(0, 6.28)))
        elif join not in ("moved",):  # a fresh reed starts a little sharp and settles
            cents += rng.uniform(5.0, 12.0) * np.exp(-t / 0.02)
        if note.dur > 0.5 and ornament > 0:
            # the throat's vibrato pulses the breath (louder and brighter, softer and darker); where the reed
            # bends, each trough also pulls its pitch down a little; where it can't, the pitch hardly moves
            ramp = np.clip((t - 0.2) / 0.3, 0.0, 1.0)
            knots = rng.uniform(-1.0, 1.0, int(n / sr / 0.3) + 2)  # the rate wanders 8% either way
            wobble = np.interp(t, np.arange(len(knots)) * 0.3, knots)
            wave = np.sin(2 * np.pi * np.cumsum(rate * (1.0 + 0.08 * wobble)) / sr + rng.uniform(0, 6.28))
            pressure *= 1.0 + PULSE * ornament * ramp * wave
            if _bendable(played):
                cents -= (8.0 + 16.0 * ornament) * ramp * (0.5 * (1.0 - wave)) ** 1.5
        if not bent:  # the reed as tuned (sharp at rest), sagging as the breath presses it; a bent note is
            # wherever the mouth puts it
            cents += tuning[(played.hole, played.breath)] - _sag(played.hole, played.breath) * \
                (np.maximum(pressure, 0.0) / 0.6) ** 1.5
        pitch = played.pitch + (note.pitch - round(note.pitch))
        freq = midi_to_hz(pitch) * 2.0 ** (cents / 1200.0)
        # the reed builds up (low reeds and soft breaths slower), and the tone brightens with the breath; bent
        # notes are darker and weaker, overblows thin
        speak = SPEAK * 2.0 ** ((78.0 - pitch) / 14.0) * (0.6 / max(vel, 0.15)) ** 1.2
        speak = min(speak * (1.15 if played.breath == "draw" else 1.0), 0.028)
        build = 1.0 if carried and last_reed is not None and (last_reed.hole, last_reed.breath) == \
            (played.hole, played.breath) else 1.0 - np.exp(-t / speak)  # a slur on the same reed: still swinging
        # companions on the same breath, the holes the mouth has open besides the note's, which the breath is
        # shared among: each reed of a three-hole chord gets 1/sqrt(3) of a single note's drive
        others: dict[int, np.ndarray] = {}  # hole -> how much of the breath reaches it over the note
        own = np.ones(n)
        table = BLOW if played.breath == "blow" else DRAW
        if art in ("slap", "chord"):  # tongue-blocked: a slap's burst until the tongue lands, a vamp's chord
            held = np.ones(n)
            if art == "slap":
                cut = min(n, int(rng.uniform(0.035, 0.06) * sr))
                fade = min(n - cut, int(0.008 * sr))
                held[cut:] = 0.0
                held[cut: cut + fade] = np.linspace(1.0, 0.0, fade)
            others = {h: held for h in range(played.hole - (3 if art == "slap" else 2), played.hole) if h >= 0}
        for p in under[k]:  # a chord written out: its notes on the holes to the left that sound them on this breath
            moved, _ = _fit(p, key)
            others.update({h: np.ones(n) for h in range(max(0, played.hole - 4), played.hole)
                           if key + table[h] == moved})
        if not others and art == "octave" and played.bend == 0:
            # the tongue split: an octave only, three holes down on the blow notes, drawing 4 over 1 and 7-10 over
            # the hole four down
            split = [h for h in (played.hole - 3, played.hole - 4) if h >= 0 and played.pitch - key - table[h] == 12]
            if split:
                others = {split[0]: np.ones(n)}
        elif not others and (art == "slide" or art == "bend") and played.bend == 0 and not _bendable(played):
            # slid onto from the next hole on the same breath (from the side the tune comes from): the lips pass
            # over it for 40-80 ms, both holes sounding for 20-30 ms
            step = 1 if last_reed is not None and last_reed.hole > played.hole else -1
            passing, overlap = float(rng.uniform(0.04, 0.08)), float(rng.uniform(0.02, 0.03))
            own = np.clip((t - passing + overlap) / overlap, 0.0, 1.0)
            others = {played.hole + step if 0 <= played.hole + step <= 9 else played.hole - step:
                      rng.uniform(0.5, 0.7) * np.clip((passing - t) / overlap, 0.0, 1.0)}
        elif not others and carried and last_reed is not None and abs(last_reed.hole - played.hole) >= 2:
            # the lips cross a hole on their way: it speaks for a moment, 10-15 dB down (more in a rack)
            h = played.hole + (1 if last_reed.hole > played.hole else -1)
            passing = float(rng.uniform(0.015, 0.03))
            others = {h: (0.4 if racked else 0.25) * np.clip((passing - t) / 0.01, 0.0, 1.0)}
        share = 1.0 / np.sqrt(np.maximum(own + sum(others.values(), np.zeros(n)), 1.0))
        drive = pressure * share
        mix = np.clip(0.2 + 0.5 * bright + 1.1 * (drive - 0.6), 0.0, 1.0)
        dark, brightw = waves(pitch, played.breath, bent, over, freq.max())
        sound = np.zeros(n)
        level = 10.0 ** (-BENT_DB * bent / 20.0) if bent else (0.6 if over else 1.0)
        reed._read_mix(dark, brightw, freq / sr, drive * build * own * level, mix, sound, 0, rng.random())
        for h, opening in sorted(others.items()):
            p = key + table[h]
            f = midi_to_hz(p) * 2.0 ** ((tuning[(h, played.breath)] - _sag(h, played.breath) * (vel / 0.6) ** 1.5)
                                        / 1200.0)
            d2, b2 = waves(float(p), played.breath, 0.0, False, f)
            reed._read_mix(d2, b2, np.full(n, f / sr), drive * build * opening, mix, sound, 0, rng.random())
        # the breath's hiss, about as loud however hard the breath (so strongest against a soft note), and
        # strongest as the note is tongued: a chuff on a new breath, a puff as the breath turns, hardly any as
        # the lips slide on
        hiss = sosfilt(hiss_sos, rng.standard_normal(n + 64))[64:]
        burst = 1.0 + {"moved": 0.2, "turned": 0.5, "repeat": 2.0}.get(join, 1.5) * np.exp(-t / 0.015)
        sound += hiss * (pressure / max(vel, 0.05)) * (vel / 0.6) ** 0.15 * burst * NOISE * \
            (1.12 if played.breath == "draw" else 1.0) * (1.0 + 1.5 * wear)
        if art in ("wah", "trem") and not racked:
            if art == "wah":
                opening = np.clip(t / max(0.12, min(0.3, 0.5 * note.dur)), 0.0, 1.0) ** 1.5 * 0.95 + 0.05
            else:
                opening = 0.55 + 0.4 * np.sin(2 * np.pi * rng.uniform(5.0, 6.5) * t - 0.5 * np.pi)
            sound = _hands(sound, opening, float(sr), HANDS[0], HANDS[1], HANDS[2], HANDS[3])
        end = min(length, i0 + n)
        out[i0:end] += sound[: end - i0]
        last_reed = played
    ir = body.impulse_response(body.HARMONICA, sr, seed=seed, size=float(s["body"]), channels=1)[:, 0]
    y = oa.convolve(out, ir, length)  # (oaconvolve's, a few blocks at a time)
    del out
    # a reed's pulses of air aren't zero-mean: no DC leaves the harp
    return sosfilt(butter(1, 20.0, btype="highpass", fs=sr, output="sos"), y)


def _sag(hole: int, breath: str) -> float:
    """Cents a reed sags at a mezzo-forte breath: the long low reeds most."""
    return SAG[0] if hole < 3 else (SAG[1] if breath == "blow" else SAG[2])


def _chords(notes) -> tuple[list, list[list[int]]]:
    """Notes starting together (within 15 ms) are one breath over several holes: the top note leads, the
    others (their pitches returned alongside) sound on the holes to its left; the chord takes a slap or a
    chord articulation from any of its notes."""
    lead, under = [], []
    for n in notes:  # sorted by start, the highest first among notes starting together
        if lead and n.start - lead[-1].start < 0.015:
            under[-1].append(int(round(n.pitch)))
            if n.art in ("slap", "chord") and lead[-1].art != "slap":
                lead[-1] = replace(lead[-1], art=n.art)
        else:
            lead.append(n)
            under.append([])
    return lead, under


def _bendable(played: Reed) -> bool:
    """Whether a reed's note bends down (bent already or not): a draw note in holes 1-6, a blow note in 8-10."""
    return played.bend >= 0 and ((played.breath == "draw" and played.hole < 6)
                                 or (played.breath == "blow" and played.hole >= 7))


def _bends(played: Reed) -> bool:
    """Whether a natural note can be bent."""
    return played.bend == 0 and _bendable(played)


def _depth(played: Reed) -> float:
    """Semitones the reed bends at most (hole 5 draw half a semitone)."""
    if played.breath == "draw":
        return 0.5 if played.hole == 4 else float(DRAW_BENDS[played.hole])
    return float(BLOW_BENDS[played.hole])
