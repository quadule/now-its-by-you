"""Strings stopped by a bar: a pedal steel guitar, and a bottleneck slide guitar.

The pedal steel. Ten strings tuned to E9 (from the nearest the player:
F#4 D#4 G#4 E4 B3 G#3 F#3 E3 D3 B2), stopped by a steel bar rather than
fretted, with the standard three pedals and four knee levers: pedal A raises
strings 5 and 10 a tone (B to C#), B raises 3 and 6 a semitone (G# to A), C
raises 4 and 5 a tone (E to F#, B to C#); the left knee raises (LKL) or lowers
(LKR) strings 4 and 8 a semitone, the right knee raises 1 and 7 (RKL) or
lowers 2 and 9 (RKR). Each chord is found as a player finds it: the bar at a
fret, the pedals and levers that make the notes, the fewest of them and the
tightest grip, the bar near where it was. A "glide" (or a bowed line's
"slur") is the steel's own move: no pick, the bar slides to the new fret and
every string still sounding slides with it by the same interval, while the
pedals and levers take the strings that must move by other intervals (up to
a tone) with their own travel; half the glide comes before the beat, so it
lands near it. A pedal bend ("bend") picks the note with its pedal up, a tone
or a semitone under, and presses it into the note, as B to C# on the A pedal
does. The bar's vibrato rolls both ways about the fret (5 to 6.5 Hz, about
10 cents either way, deeper with the ornament) on anything held. The bar
whirs and hisses along the wound strings as it moves. The volume pedal rests
about half way down (14 dB under the top) while the player picks; "swell" pulls it
back 45 dB for the pick and pushes it to the top over a quarter of a second
to nearly a second, so the attack vanishes; the pedal is the whole
instrument's, so it takes whatever else is ringing with it. The strings
(metal finger picks, a thumb pick on the low ones, notes together pinched a
few milliseconds apart) ring very long on a rigid steel body: the
fundamental falls 60 dB in 11 to 15 s at 220 Hz, until the player blocks the
string with the palm, as a player does before the bar or a pedal moves under
a ringing string; a slur onto a string that has rung for more than two and a
half seconds is picked again as the bar carries it. Some players
tune their major thirds a little flat so the chords ring purer (the G#
strings and the A pedal's C# 5 to 12 cents, D# a little less): the maker
decides. It plays through a clean amp with plenty of headroom, its spring
reverb and a 12- or 15-inch speaker (amp.py).

The slide. An acoustic flat-top, a resonator or an electric (by the maker,
or settings["slide"]), tuned open to the song's key (open D or open G,
retuned up to three semitones or capoed), played with a glass or brass
bottleneck: the slide stops every string at once at any pitch, so the same
glide machinery moves it; notes land a touch flat and settle (a slide
player's intonation); long notes get a wide vibrato, even either side of the
note; the slide hisses and whirs along the wound strings as it moves; a
string not pressed quite hard enough rattles against it as a note starts.
The slide is a soft stop, so its notes die sooner than fretted ones, and the
string behind it, between the slide and the nut, rings too: a faint, high
tone that falls as the slide climbs, which the player's trailing finger
damps within a tenth of a second or two (some players more carefully than
others). The electric plays through the maker's small valve amp (electric.py,
amp.py), pushed a little.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import combinations, product

import numpy as np
from scipy.signal import butter, sosfilt

from ..score import Note
from ..theory import midi_to_hz
from . import amp, body, electric, fretboard
from .fretboard import Segment, Strings
from .master import loudness

STEEL_ARTS = {
    "": "picked (notes together are pinched by thumb and fingers)",
    "glide": "no pick: the bar (and pedals) move from the last notes to these; every held string moves with the bar",
    "slur": "the same as a glide (a bowed line's slur, played with the bar)",
    "slide": "picked a fret or two below and slid up into the note with the bar",
    "bend": "a pedal bend: picked with its pedal or lever up, a tone or a semitone under, and pushed into the note",
    "swell": "picked with the volume pedal back and swelled in: no attack",
    "vibrato": "a deeper bar vibrato",
    "fall": "the bar slides down off the note as it ends",
    "mute": "blocked right after the pick",
}
SLIDE_ARTS = {
    "": "picked with the slide already there, landing a touch flat and settling",
    "slide": "picked two or three semitones below and slid up to the note",
    "bend": "picked a tone below and slid slowly up to the note",
    "glide": "no pick: the slide moves from the last note to this one",
    "slur": "the same as a glide",
    "swell": "picked softly and let ring, its vibrato growing (an electric's swelled in with the volume knob)",
    "vibrato": "a wide slide vibrato",
    "fall": "slides away down as the note ends",
    "mute": "damped right after the pick",
}
LEGATO = ("glide", "slur")

SPEC = {
    "steel": dict(
        family="bowed", role="comping", register=(47, 88), place=(0.45, 0.5), level=0.25, poly=True,
        articulations=STEEL_ARTS,
        about="a pedal steel guitar (E9, ten strings, three pedals and four knee levers) through a clean amp "
              "with spring reverb: swells, bar glides, pedal bends, bar vibrato"),
    "slide": dict(
        family="plucked", role="lead", register=(38, 84), place=(0.4, 0.5), level=0.25, poly=False,
        articulations=SLIDE_ARTS,
        about="a bottleneck slide guitar, open-tuned to the key: an acoustic flat-top, a resonator, or an electric "
              "through a small amp"),
}

# --- the pedal steel's neck -----------------------------------------------------------------------

E9 = {1: 66, 2: 63, 3: 68, 4: 64, 5: 59, 6: 56, 7: 54, 8: 52, 9: 50, 10: 47}  # string number: MIDI
ORDER = (10, 9, 8, 7, 6, 5, 4, 3, 2, 1)  # the Strings' order, lowest first
OPEN = tuple(float(E9[k]) for k in ORDER)
PEDALS = {"A": {5: 2, 10: 2}, "B": {3: 1, 6: 1}, "C": {4: 2, 5: 2}, "LKL": {4: 1, 8: 1}, "LKR": {4: -1, 8: -1},
          "RKL": {1: 1, 7: 1}, "RKR": {2: -1, 9: -1}}
WOUND = {6, 7, 8, 9, 10}
BARS = 23  # frets the bar may sit at (0 is the open strings)
LOW, HIGH = 47.0, 88.0


def change_of(names) -> np.ndarray | None:
    """The semitones a set of pedals and levers moves each string (in ORDER), or None if two of them pull one
    string opposite ways. Two that raise one string raise it as far as the further one's stop."""
    change = dict.fromkeys(E9, 0)
    for name in names:
        for string, d in PEDALS[name].items():
            if change[string] and np.sign(change[string]) != np.sign(d):
                return None
            change[string] = max(change[string], d) if d > 0 else min(change[string], d)
    return np.array([change[s] for s in ORDER], dtype=np.int64)


@lru_cache(maxsize=1)
def copedant() -> tuple[tuple[tuple[str, ...], np.ndarray], ...]:
    """Every combination of up to three pedals and levers a foot and two knees can hold (a knee lever is
    pushed one way at a time), with the semitones it moves each string (in ORDER)."""
    out = []
    for k in range(4):
        for chosen in combinations(PEDALS, k):
            if {"LKL", "LKR"} <= set(chosen) or {"RKL", "RKR"} <= set(chosen):
                continue
            change = change_of(chosen)
            if change is not None:
                out.append((chosen, change))
    return tuple(out)


@lru_cache(maxsize=1)
def _tuned() -> np.ndarray:
    """(combinations, bar frets, strings): the pitch each string sounds."""
    changes = np.stack([c for _, c in copedant()])
    return np.array(OPEN, dtype=np.int64)[None, None, :] + np.arange(BARS)[None, :, None] + changes[:, None, :]


@dataclass(frozen=True)
class Grip:
    bar: int  # the fret the bar sits at
    pedals: tuple[str, ...]  # what the feet and knees hold ("~" for a string moved by a lever beyond the copedant)
    change: tuple[int, ...]  # semitones each string (in ORDER) is moved
    strings: tuple[int, ...]  # the string (index in ORDER) of each note, in the notes' order
    cost: float


@lru_cache(maxsize=8192)
def grip(pitches: tuple[int, ...], bar: int, sounding: frozenset = frozenset(), glide: bool = False,
         bend: frozenset = frozenset()) -> Grip:
    """How a steel player makes these notes: the bar's fret, the pedals and levers, a string for each note.
    Fewest pedals, tightest grip, the bar near where it was; for a glide, the notes on strings already
    sounding; for a pedal bend, the notes whose index is in `bend` on strings a pedal or lever raises."""
    tuned = _tuned()
    feasible = np.ones(tuned.shape[:2], dtype=bool)
    for p in pitches:
        feasible &= np.any(tuned == p, axis=2)
    best = None
    for c, f in zip(*np.nonzero(feasible)):
        names, change = copedant()[c]
        options = [np.flatnonzero(tuned[c, f] == p).tolist() for p in pitches]
        # the feet and knees are quicker than the bar: a pedal or lever costs about a fret of travel, and the
        # A and B pedals, side by side, go down together under one foot
        motions = len(names) - (1 if {"A", "B"} <= set(names) else 0)
        for strings in product(*options):
            if len(set(strings)) < len(strings):
                continue
            cost = 0.35 * motions + 0.3 * abs(f - bar) + 0.4 * (max(strings) - min(strings) - len(strings) + 1) \
                + 0.02 * f + (0.5 if f == 0 else 0.0)
            if glide:
                cost += 6.0 * sum(s not in sounding for s in strings)
            if bend:
                cost += 8.0 * sum(change[s] <= 0 for j, s in enumerate(strings) if j in bend)
            if best is None or cost < best.cost:
                best = Grip(int(f), names, tuple(int(v) for v in change), tuple(int(s) for s in strings), cost)
    if best is not None:
        return best
    # beyond the copedant: each note on the string nearest it, moved up to a tone by a lever of its own
    for f in sorted(range(1, BARS), key=lambda x: abs(x - bar)):
        taken, strings, change = set(), [], [0] * len(OPEN)
        for p in pitches:
            options = sorted((abs(p - OPEN[i] - f), i) for i in range(len(OPEN))
                             if i not in taken and abs(p - OPEN[i] - f) <= 2)
            if not options:
                break
            i = options[0][1]
            taken.add(i)
            strings.append(i)
            change[i] = int(round(p - OPEN[i] - f))
        else:
            return Grip(f, ("~",), tuple(change), tuple(strings), 50.0)
    # more notes than the strings can make at one bar: the lowest ten, each where it can be
    raise ValueError(f"no grip for {pitches}")


def reachable(pitches: tuple[int, ...], bar: int, sounding: frozenset = frozenset(), glide: bool = False,
              bend: frozenset = frozenset()) -> tuple[tuple[int, ...], Grip]:
    """The grip for as many of these notes as one bar position can hold: all of them if it can, else the
    player leaves out what is out of reach, keeping the lowest notes first. Returns the kept notes' indices."""
    try:
        return tuple(range(len(pitches))), grip(pitches, bar, sounding, glide, bend)
    except ValueError:
        pass
    for n in range(len(pitches) - 1, 0, -1):
        for keep in combinations(range(len(pitches)), n):
            try:
                return keep, grip(tuple(pitches[k] for k in keep), bar, sounding, glide)
            except ValueError:
                continue
    raise ValueError(f"no grip for any of {pitches}")


def thirds_offset(string: int, change: int, thirds: float) -> float:
    """Cents a string sits off equal temperament when the player tunes the major thirds `thirds` cents flat
    (toward pure thirds, as Jeff Newman's chart has them: the G# strings, the A pedal's C#, the D# a little
    less); the other strings and pedal stops are tuned equal."""
    if not thirds:
        return 0.0
    number = ORDER[string]
    if number in (3, 6) and change == 0:  # G#: the third of the open E chord
        return -thirds
    if number == 2 and change == 0:  # D#: the third of the B chord
        return -0.85 * thirds
    if number in (5, 10) and change == 2:  # C#: the third of the A chord (the A pedal)
        return -thirds
    return 0.0


# --- moves over a whole part -----------------------------------------------------------------------


class Track:
    """A value over a part (the bar's fret, a pedal's semitones, a slide's place) that moves now and then:
    each move from wherever it is to a target, over some samples, along a raised cosine."""

    def __init__(self, value: float = 0.0):
        self.value = float(value)
        self.moves: list[tuple[int, float, int]] = []  # (at, target, over)
        self._sorted = True

    def move(self, at: int, target: float, over: int) -> None:
        at = int(at)
        if self.moves and at < self.moves[-1][0]:
            self._sorted = False
        self.moves.append((at, float(target), max(1, int(over))))

    def _in_order(self) -> list[tuple[int, float, int]]:
        if not self._sorted:
            self.moves.sort(key=lambda m: m[0])
            self._sorted = True
        return self.moves

    def at(self, t: int) -> float:
        value = self.value
        for at, target, over in self._in_order():
            if at >= t:
                break
            k = min(t - at, over)
            value = value + (target - value) * (0.5 - 0.5 * np.cos(np.pi * k / over))
        return float(value)

    def window(self, t0: int, n: int) -> np.ndarray:
        out = np.full(n, self.at(t0))
        for at, target, over in self._in_order():
            if at + over <= t0 or at >= t0 + n:
                continue
            start = self.at(at)
            k = np.arange(max(at, t0), min(at + over, t0 + n))
            out[k - t0] = start + (target - start) * (0.5 - 0.5 * np.cos(np.pi * (k - at) / over))
            out[min(at + over, t0 + n) - t0:] = target
        return out

    def moving(self, t0: int, n: int) -> bool:
        return any(at < t0 + n and at + over > t0 for at, _, over in self.moves)


class Vibrato:
    """A bar's (or slide's) vibrato: episodes of a sine in cents, even either side of the note, each growing in
    over a third of a second and fading at its end."""

    def __init__(self):
        self.episodes: list[tuple[int, int, float, float, float]] = []  # (start, end, Hz, depth, grow s)

    def add(self, start: int, end: int, hz: float, depth: float, grow: float = 0.3) -> None:
        if end > start:
            self.episodes.append((int(start), int(end), float(hz), float(depth), float(grow)))

    def window(self, t0: int, n: int, sr: int) -> np.ndarray | None:
        out = None
        for start, end, hz, depth, grow in self.episodes:
            if end <= t0 or start >= t0 + n:
                continue
            if out is None:
                out = np.zeros(n)
            k = np.arange(max(start, t0), min(end, t0 + n))
            t = (k - start) / sr
            env = np.clip(t / grow, 0.0, 1.0) * np.clip((end - k) / (0.1 * sr), 0.0, 1.0)
            out[k - t0] += depth * env * np.sin(2.0 * np.pi * hz * t)
        return out


def _groups(notes: list[Note], within: float = 0.03) -> list[list[Note]]:
    groups: list[list[Note]] = []
    for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if groups and note.start - groups[-1][0].start < within and len(groups[-1]) < 10:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


@lru_cache(maxsize=8)
def _bands(sr: int) -> tuple[np.ndarray, np.ndarray]:
    return (butter(2, [200.0, 3000.0], btype="bandpass", fs=sr, output="sos"),
            butter(2, [1500.0, 6000.0], btype="bandpass", fs=sr, output="sos"))


def _scrape(n: int, speed: np.ndarray, sr: int, rng: np.random.Generator, pitch_m: float = 0.0004,
            fret_m: float = 0.025) -> np.ndarray:
    """A bar or slide dragged along wound strings: a whir at the rate it crosses the winding's ridges
    (its speed over their pitch, 0.4 mm) and a hiss above, both as loud as it moves fast."""
    rate = np.abs(speed) * fret_m / pitch_m  # ridges a second: speed in frets a second
    phase = 2.0 * np.pi * np.cumsum(rate) / sr
    whir = np.sign(np.sin(phase)) * 0.5 + 0.5 * np.sin(phase)
    low, high = _bands(sr)
    hiss = sosfilt(high, rng.standard_normal(n))
    level = np.clip(np.abs(speed) / 20.0, 0.0, 1.0)
    return (0.6 * sosfilt(low, whir) + 0.4 * hiss) * level


def _finish(segs, strings: Strings, sr: int, length: int, bar: Track, pedals, vib: Vibrato, thirds: float = 0.0,
            ring_db: float = 80.0) -> None:
    """Each segment's end (the block's tail, or ring_db down), its pitch where it starts, and its length and
    tension tracks, cut from the part's bar (or slide), pedals and vibrato. A segment with hand 0 is an
    open string, which the bar doesn't touch."""
    for seg in segs:
        i = seg.string
        stopped = seg.hand > 0
        pedal = pedals[i] if pedals is not None else None
        semis = pedal.at(seg.start) if pedal is not None else 0.0
        seg.base = strings.open[i] + (bar.at(seg.start) if stopped else 0.0) + semis \
            + thirds_offset(i, int(round(semis)), thirds) / 100.0
        stop = seg.held + int(max(0.02, 1.4 * seg.release) * sr)
        dies = int(fretboard.ring_time(strings, seg.base, ring_db) * seg.decay * sr)
        seg.end = max(1, min(stop, dies, length - seg.start))
        seg.held = min(seg.held, seg.end)
        n = seg.end
        if stopped:
            track = 100.0 * (bar.window(seg.start, n) - bar.at(seg.start))
            wobble = vib.window(seg.start, n, sr)
            if wobble is not None:
                track = track + wobble
            if np.any(track != 0.0):
                seg.bar = track
        if pedal is not None and pedal.moving(seg.start, n):
            moved = pedal.window(seg.start, n)
            cents = 100.0 * (moved - semis)
            if thirds:  # a pedal's stop is tuned to its own pitch: the string's offset changes as it moves
                marks = np.arange(0, n, 64)
                offsets = np.array([thirds_offset(i, int(round(v)), thirds) for v in moved[marks]])
                cents = cents + np.interp(np.arange(n), marks, offsets) - thirds_offset(i, int(round(semis)), thirds)
            seg.tension = cents


def _bar_scrape(bar: Track, segs, length: int, sr: int, rng: np.random.Generator, wound, level: float) -> np.ndarray:
    """The bar's scrape as it moves along the strings: it lies across them all, so it rubs the wound ones
    whether the palm is damping them or not, louder for each one ringing (it shakes what rings). Only while
    the bar is on the strings (something it stops is sounding)."""
    out = np.zeros(length)
    for at, target, over in bar.moves:
        if over < int(0.03 * sr) or at >= length or at < 0:
            continue
        n = min(over, length - at)
        on = [s for s in segs if s.hand > 0 and s.start <= at < s.start + s.end]
        if not on:
            continue
        under = sum(1 for s in on if s.string in wound)
        speed = np.gradient(bar.window(at, n)) * sr  # frets a second
        out[at: at + n] += _scrape(n, speed, sr, rng) * level * (0.4 + 0.6 * np.sqrt(under))
    return out


def _prepare(notes, sr: int, length: int) -> list[Note]:
    last = length / sr
    return sorted((n for n in notes if 0.0 <= n.start < last and n.dur > 0), key=lambda n: (n.start, n.pitch))


# --- the pedal steel ------------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _steel_built(seed: int) -> dict:
    """Everything about a maker's steel, amp and player that doesn't change from song to song."""
    g = np.random.default_rng(seed)
    d: dict = {}
    d["humbucker"] = bool(g.random() < 0.5)
    d["thirds"] = 0.0 if g.random() < 0.55 else float(g.uniform(5.0, 12.0))  # cents the thirds are tuned flat
    d["t60"] = float(g.uniform(11.0, 15.0))  # s at 220 Hz: a steel's rigid body and a steel bar
    d["pickup"] = float(g.uniform(0.038, 0.05))  # m from the bridge, on a 0.622 m (24.5 inch) scale
    d["pick"] = float(g.uniform(0.08, 0.12))
    d["poles"] = tuple(g.normal(0.0, 0.8, 10))
    d["detune"] = tuple(g.standard_normal(10))
    d["vibrato"] = float(g.uniform(5.0, 6.5))  # Hz
    d["depth"] = float(g.uniform(0.7, 1.3))  # this player's vibrato against the usual
    d["glide"] = float(g.uniform(0.8, 1.25))  # how slowly this player glides
    d["pedal"] = float(g.uniform(0.08, 0.15))  # s: a pedal pressed or let up
    d["bend"] = float(g.uniform(0.15, 0.3))  # s: a pedal pressed slowly into a note
    d["swell"] = float(g.uniform(0.8, 1.25))  # how slowly this player swells
    d["home"] = int(g.integers(5, 10))  # where the bar sits before the first note
    fifteen = g.random() < 0.5
    d["amp"] = amp.Amp(
        voicing="fender", treble=float(g.uniform(0.5, 0.7)), middle=float(g.uniform(0.3, 0.5)),
        bass=float(g.uniform(0.35, 0.55)), volume=float(g.uniform(-27.0, -24.0)), headroom=float(g.uniform(55.0, 70.0)),
        knee=2, tilt=0.01, sag=float(g.uniform(0.02, 0.06)), reverb=float(g.uniform(0.18, 0.3)),
        tank=amp.Tank(traversals=(float(g.uniform(0.03, 0.034)), float(g.uniform(0.038, 0.043))),
                      t60=float(g.uniform(2.6, 3.4)), coef=float(g.uniform(0.6, 0.68)), seed=int(g.integers(1 << 30))),
        cabinet=amp.Cabinet(
            fs=float(g.uniform(48.0, 60.0) if fifteen else g.uniform(75.0, 88.0)), q=float(g.uniform(0.9, 1.3)),
            presence=(float(g.uniform(3000.0, 4200.0)), float(g.uniform(3.0, 6.0)), 1.2),
            rolloff=float(g.uniform(6200.0, 7500.0)), order=2, back=float(g.uniform(2.0, 4.0)),
            mics=((float(g.uniform(0.00015, 0.0003)), 0.2, 0.0), (float(g.uniform(0.0008, 0.0014)), 0.35, -4.0)),
            seed=int(g.integers(1 << 30))))
    return d


def _steel_strings(d: dict, bright: float, wear: float) -> tuple[Strings, amp.Coil, dict]:
    scale = 0.622
    if d["humbucker"]:
        comb = (((d["pickup"] - 0.009) / scale, 0.5), ((d["pickup"] + 0.009) / scale, 0.5))
        coil = amp.HUMBUCKER
    else:
        comb = ((d["pickup"] / scale, 1.0),)
        coil = amp.SINGLE
    circuit = dict(pot=500e3, tone=None, tone_cap=22e-9, cable=500e-12)
    strings = Strings(
        open=OPEN, comb=comb, offsets=tuple(z * (0.3 + 3.0 * wear) for z in d["detune"]),
        gains=tuple(10.0 ** (p / 20.0) for p in d["poles"]),
        damping=(4e-6 + 4e-6 * wear) * (1.4 - 0.8 * bright), t60=d["t60"] * (1.0 - 0.25 * wear), along=1.2,
        heard=0.45, driven=0.6, pick=d["pick"], hardness=0.95, click=0.2, frets=BARS - 1,
        kinds=(("thumb", (1.0, 0.85, 1.0, 0.7)),))
    return strings, coil, circuit


def _glide_time(frets: float, d: dict) -> float:
    """Seconds a steel player's bar takes to glide `frets` frets."""
    return float(np.clip((0.06 + 0.03 * abs(frets)) * d["glide"], 0.05, 0.4))


def _bar_tracks(groups, sr: int, rng: np.random.Generator, d: dict, ornament: float, length: int):
    """Walk the part as a steel player does: grips, bar moves and pedal moves, blocks, swells, vibrato.
    Returns the segments (tracks still to be cut from the part's), the bar, the pedals, the vibrato and the
    volume pedal (dB)."""
    bar = Track(float(d["home"]))
    pedals = [Track(0.0) for _ in OPEN]
    vib = Vibrato()
    volume = Track(REST)  # the volume pedal, dB: resting part way down, pushed to the top for a swell
    current: dict[int, Segment] = {}
    segs: list[Segment] = []
    where = int(d["home"])
    state = [0] * len(OPEN)
    last = -sr
    ms = sr / 1000.0
    for k, group in enumerate(groups):
        t0 = int(round(group[0].start * sr))
        if t0 >= length:
            break
        sounding = frozenset(i for i, seg in current.items() if seg.start + seg.held > t0 - int(0.03 * sr))
        legato = bool({n.art for n in group} & set(LEGATO)) and bool(sounding)
        bending = frozenset(j for j, n in enumerate(group) if n.art == "bend")
        keep, g = reachable(tuple(int(round(n.pitch)) for n in group), where, sounding if legato else frozenset(),
                            legato, bending)
        if len(keep) < len(group):  # a chord no bar position can hold: what is out of reach is left out
            group = [group[k] for k in keep]
            bending = frozenset()
        arts = {n.art for n in group}
        dur = max(n.dur for n in group)
        target = list(g.change)
        moved = [i for i in range(len(OPEN)) if target[i] != state[i]]
        bent = {g.strings[j] for j in bending if g.change[g.strings[j]] > 0}
        # a note no pedal or lever can bend into is slid into with the bar instead
        slide_in = ("slide" in arts or (bending and not bent)) and g.bar > 0
        # a slur onto strings that have rung a while (fallen 20 dB or more) is picked again, and the bar and
        # pedals carry it from where they are: a player's pick and glide
        repick = legato and min(t0 - current[i].start for i in sounding) > STALE * sr
        if repick:
            legato = False
        if "swell" in arts:  # the pedal back just before the pick
            volume.move(t0 - int(30 * ms), FLOOR, int(25 * ms))
        elif not legato and abs(volume.at(t0) - REST) > 0.1:  # back to where it rests, easing off a swell
            volume.move(t0 - int(150 * ms), REST, int(140 * ms))
        if legato:
            # half the glide before the beat, so it lands near it; never longer than most of either note
            over = int(_glide_time(g.bar - bar.at(t0), d) * sr)
            over = max(int(0.03 * sr), min(over, int(0.6 * dur * sr), int(0.6 * max(t0 - last, 1))))
            begin = t0 - over // 2
            if g.bar != where:
                bar.move(begin, g.bar, over)
            travel = max(int(0.05 * sr), min(over, int(d["pedal"] * sr)))
            for i in moved:
                pedals[i].move(begin, target[i], travel)
        else:
            released = list(target)
            if bent:  # the bending notes' pedals and levers up at the pick, then pressed into the notes
                names = [p for p in g.pedals if p in PEDALS and not (set(PEDALS[p]) & {ORDER[s] for s in bent})]
                rest = change_of(names)
                if rest is not None:
                    released = [int(v) for v in rest]
            moving_bar = g.bar != where or slide_in
            for i, seg in current.items():  # the palm blocks what would sound the bar or a pedal moving
                if seg.start + seg.held > t0 - int(0.03 * sr) and ((moving_bar and seg.hand > 0) or released[i] != state[i]):
                    seg.held = max(1, min(seg.held, t0 - seg.start - int(0.03 * sr)))
                    seg.release = 0.025
            pre = t0 - int(10 * ms)
            first = g.bar - (min(g.bar, int(rng.integers(1, 3))) if slide_in else 0)
            if repick:  # picked where the bar and pedals are, then carried to the new grip
                first, released = bar.at(pre), list(state)
            if abs(bar.at(pre) - first) > 1e-9:
                bar.move(pre, first, int(6 * ms))
            for i in range(len(OPEN)):
                if released[i] != state[i]:
                    pedals[i].move(pre, released[i], int(6 * ms))
            if slide_in:
                bar.move(t0 + int(10 * ms), g.bar, int(rng.uniform(0.08, 0.15) * sr))
            elif repick and abs(first - g.bar) > 1e-9:
                bar.move(t0 + int(10 * ms), g.bar, int(_glide_time(g.bar - first, d) * sr))
            for i in range(len(OPEN)):
                if released[i] != target[i]:
                    travel = d["pedal"] if repick else d["bend"]
                    pedals[i].move(t0 + int(rng.uniform(0.02, 0.05) * sr), target[i], int(travel * sr))
        spread = 0.0
        for note, i in sorted(zip(group, g.strings), key=lambda x: x[0].pitch):
            start = t0 + (int(spread * sr) if not legato else 0)  # thumb and fingers pinch, a few ms apart
            spread += rng.uniform(0.0, 0.004)
            held = max(1, int(round(note.dur * sr)))
            if note.art == "mute":
                held = min(held, int(0.1 * sr))
            seg = current.get(i)
            if legato and seg is not None and i in sounding:
                seg.held = max(seg.held, start - seg.start + held)  # no pick: the string sounds on
                continue
            if seg is not None and seg.start + seg.held > start:
                seg.held = max(1, start - seg.start - int(0.002 * sr))
                seg.release = 0.02
            kind = "thumb" if ORDER[i] >= 7 else "pick"
            # a glide onto a string that wasn't ringing is picked, a little softer, and rides the bar in
            seg = Segment(string=i, start=start, base=OPEN[i], held=held,
                          picks=[(0, note.vel * (0.8 if legato else 1.0), kind)], hand=float(g.bar))
            if note.art == "fall":
                seg.release = 0.12
            current[i] = seg
            segs.append(seg)
        where, state = g.bar, list(target)
        swell = 0
        if "swell" in arts:  # pushed to the top along a raised cosine in decibels: the attack vanishes
            swell = int(np.clip(0.35 * dur, 0.25, 0.9) * d["swell"] * sr)
            volume.move(t0, 0.0, swell)
        if "fall" in arts and g.bar > 1:  # the bar slides off down the neck as the note ends, the pedal easing
            at = t0 + int(0.6 * dur * sr)
            drop = float(min(g.bar - 0.5, rng.uniform(2.0, 5.0)))
            bar.move(at, g.bar - drop, int(min(0.4 * dur, 0.5) * sr))
            volume.move(at, REST - 14.0, int(min(0.4 * dur, 0.5) * sr))
            where = int(round(g.bar - drop))
        # the bar's vibrato on anything held long enough, deeper where asked
        after = int(round(groups[k + 1][0].start * sr)) if k + 1 < len(groups) else t0 + int(dur * sr)
        hold = min(after, t0 + int(dur * sr))
        wide = "vibrato" in arts
        if g.bar > 0 and "fall" not in arts and (hold - t0 > 0.7 * sr or wide):
            depth = d["depth"] * (4.0 + 10.0 * ornament) * (1.8 if wide else 1.0)
            begin = t0 + (swell + int(0.1 * sr) if swell else int((0.4 if legato else 0.3) * sr))
            if wide:
                begin = min(begin, t0 + int(0.15 * sr))
            vib.add(begin, hold, d["vibrato"] * rng.uniform(0.95, 1.05), depth)
        last = t0
    return segs, bar, pedals, vib, volume


REST = -14.0  # dB: where the volume pedal rests while the player picks, leaving the top of its travel for swells
FLOOR = -45.0  # dB: the pedal back, for a swell's pick
STALE = 2.5  # s: how long a string rings before a slur onto it is picked again


def _swell_track(volume, length: int, sr: int, floor: float = FLOOR) -> np.ndarray | None:
    """The volume pedal: back (floor dB) just before each swelled pick, then pushed in over the swell along a
    raised cosine in decibels."""
    if not volume:
        return None
    gain_db = np.zeros(length, dtype=np.float32)
    for at, over in volume:
        down = int(0.03 * sr)
        a = max(0, at - down)
        k = np.arange(a, min(length, at))
        gain_db[k] = np.minimum(gain_db[k], floor * (k - a + 1) / max(1, at - a))
        k = np.arange(at, min(length, at + over))
        rise = floor * (0.5 + 0.5 * np.cos(np.pi * (k - at) / over))
        gain_db[k] = np.minimum(gain_db[k], rise)
    return 10.0 ** (gain_db.astype(np.float64) / 20.0)


def steel(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator, s: dict) -> np.ndarray:
    """The pedal steel's stem: (length, 2), as its amp's two microphones hear it."""
    notes = [replace(n, pitch=fretboard.in_range(n.pitch, LOW, HIGH)) for n in _prepare(notes, sr, length)]
    if not notes:
        return np.zeros((length, 2))
    seed = int(make.integers(1 << 31))
    d = _steel_built(seed)
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
    strings, coil, circuit = _steel_strings(d, bright, wear)
    segs, bar, pedals, vib, volume = _bar_tracks(_groups(notes), sr, rng, d, ornament, length)
    _finish(segs, strings, sr, length, bar, pedals, vib, d["thirds"])
    emf = _voltage(segs, strings, coil, circuit, sr, length, rng)
    emf += _bar_scrape(bar, segs, length, sr, rng, [ORDER.index(w) for w in WOUND], SCRAPE * EMF * coil.sensitivity)
    emf *= 10.0 ** (volume.window(0, length) / 20.0)
    chain = amp.Chain(d["amp"], sr, os_=2)
    chain.p[21] = _steel_master(seed, bright, wear, sr)
    return _warmed(chain, emf, sr) * STEEL_OUT


def _warmed(chain: amp.Chain, emf: np.ndarray, sr: int) -> np.ndarray:
    """The amp's two microphones, the amp switched on a quarter of a second before (its valves settle)."""
    pre = int(0.25 * sr)
    return amp.play(chain, np.concatenate([np.zeros(pre), emf]))[pre:]


STEEL_OUT = 17.6  # the stem's scale: the country style's line under the singer, as written, sits as a comping part
EMF = 0.055  # volts per unit of string velocity for a single coil (as electric.py's)
SCRAPE = 0.009  # the bar's scrape at full speed, against a string's velocity: 25 dB under a note on a wound string


def _voltage(segs, strings: Strings, coil: amp.Coil, circuit: dict, sr: int, length: int,
             rng: np.random.Generator) -> np.ndarray:
    emf = np.zeros(length)
    for seg in segs:
        y = fretboard.sound(seg, strings, sr, rng)
        end = min(length, seg.start + len(y))
        emf[seg.start:end] += y[: end - seg.start]
    b, a = amp.pickup_ba(coil, **circuit)
    return sosfilt(amp.digital(b, a, sr, amp.resonance(b, a)[0]), emf * EMF * coil.sensitivity)


@lru_cache(maxsize=32)
def _steel_master(seed: int, bright: float, wear: float, sr: int) -> float:
    """The amp's master volume, set so this steel's A chord (bar at 5), held, comes out at a fixed loudness."""
    d = _steel_built(seed)
    strings, coil, circuit = _steel_strings(d, bright, wear)
    notes = [Note("steel", 0.0, 2.5, float(p), 0.6) for p in (69.0, 73.0, 76.0)]
    rng = np.random.default_rng([seed, 71])
    segs, bar, pedals, vib, _ = _bar_tracks(_groups(notes), sr, rng, d, 0.5, int(3.0 * sr))
    _finish(segs, strings, sr, int(3.0 * sr), bar, pedals, vib, d["thirds"])
    emf = _voltage(segs, strings, coil, circuit, sr, int(3.0 * sr), rng)
    chain = amp.Chain(d["amp"], sr, os_=2)
    return float(10.0 ** ((-20.0 - loudness(amp.play(chain, emf), sr)) / 20.0))


# --- the slide guitar -----------------------------------------------------------------------------

OPEN_D = (38, 45, 50, 54, 57, 62)  # D A D F# A D, lowest first
OPEN_G = (38, 43, 50, 55, 59, 62)  # D G D G B D
SHAPES = {"open D": (OPEN_D, 2), "open G": (OPEN_G, 7)}  # the tuning and its root's pitch class
KINDS = ("acoustic", "resonator", "electric")

RESONATOR = body.Body(  # a spun aluminium cone under the bridge: a few strong, ringing midrange modes, little bass
    modes=((190.0, 14.0, 2.0), (420.0, 16.0, 6.0), (780.0, 20.0, 7.0), (1350.0, 22.0, 5.0), (2300.0, 24.0, 4.0)),
    dense=(900.0, 9000.0, 90), tilt=-1.5, q=(45.0, 30.0), direct=0.3, lowcut=140.0, highcut=9000.0, length=0.5)


def open_tuning(tonic: int, prefer: str) -> tuple[tuple[float, ...], str, int, int]:
    """The open tuning a slide player would use for a key: open D or open G retuned by at most three
    semitones (open E, open A, open C...), else capoed. Returns the strings' pitches, the shape, the retuning
    and the capo."""
    pc = int(tonic) % 12
    best = None
    for name, (shape, root) in SHAPES.items():
        shift = (pc - root + 6) % 12 - 6
        cost = abs(shift) + (0.5 if name != prefer else 0.0)
        if best is None or cost < best[0]:
            best = (cost, name, shape, shift)
    _, name, shape, shift = best
    capo = 0
    if shift > 3:
        capo, shift = shift, 0
    elif shift < -3:
        capo, shift = shift + 12, 0
    return tuple(float(p + shift + capo) for p in shape), name, shift, capo


@lru_cache(maxsize=32)
def _slide_built(seed: int) -> dict:
    g = np.random.default_rng(seed)
    d: dict = {}
    d["kind"] = KINDS[int(np.searchsorted(np.cumsum([0.4, 0.35, 0.25]), g.random(), side="right"))]
    d["prefer"] = "open D" if g.random() < 0.5 else "open G"
    d["brass"] = bool(g.random() < 0.5)  # a brass slide rings brighter and longer than glass
    d["t60"] = float(g.uniform(1.6, 2.2) if d["kind"] == "resonator" else g.uniform(2.0, 2.8))  # s at 220 Hz
    d["pick"] = float(g.uniform(0.1, 0.16))
    d["detune"] = tuple(g.standard_normal(6))
    d["flat"] = float(g.uniform(15.0, 35.0))  # cents a note lands under its pitch before it settles
    d["vibrato"] = float(g.uniform(4.8, 6.0))
    d["glide"] = float(g.uniform(0.8, 1.2))
    d["rattle"] = float(g.uniform(0.3, 1.0))
    d["behind"] = (float(g.uniform(0.015, 0.05)), float(g.uniform(0.06, 0.25)))  # the ring behind: level, T60 s
    d["drive"] = float(g.uniform(0.45, 0.7))  # the electric's amp, pushed a little
    d["body_seed"] = int(g.integers(1 << 30))
    return d


def _slide_strings(d: dict, tuning, bright: float, wear: float, s: dict, sr: int, kind: str):
    """The slide's strings, and for the electric its pickup, circuit and amp (None for the others)."""
    offsets = tuple(z * (0.5 + 4.0 * wear) for z in d["detune"])
    damping = (1.6e-5 + 1e-5 * wear) * (1.3 - 0.6 * bright) * (0.75 if d["brass"] else 1.0)
    t60 = d["t60"] * (1.15 if d["brass"] else 1.0) * (1.0 - 0.25 * wear)
    if kind != "electric":
        strings = Strings(open=tuning, comb=(), offsets=offsets, damping=damping, t60=t60, along=2.5, heard=0.35,
                          driven=1.0, pick=d["pick"], hardness=0.7, click=0.6, touch=0.2, frets=20,
                          kinds=(("behind", (0.15, 1.0, 1.0, 0.0)),))
        return strings, None
    rig_s = _electric_settings(d, s)
    strings, coil, circuit, rig_amp = electric.rig("electric", rig_s, sr)
    strings = replace(strings, open=tuning, offsets=offsets, damping=0.6 * damping, t60=1.6 * t60, frets=22,
                      kinds=(("behind", (0.15, 1.0, 1.0, 0.0)),))
    return strings, (coil, circuit, rig_amp, rig_s)


def _electric_settings(d: dict, s: dict) -> dict:
    return {**s, "amp": {"setting": "clean", "drive": d["drive"], "reverb": 0.45}}


def place_slide(pitches: tuple[float, ...], tuning, where: float, previous: int | None, glide: bool):
    """Strings for notes under a slide: every stopped note at one slide position (pitch minus its open
    string), or an open string; near where the slide was; a glide on the string it moves along."""
    best = None
    positions = {round(p - t, 3) for p in pitches for t in tuning if 0.0 <= p - t <= 20.0}
    for x in sorted(positions) or [0.0]:
        options = []
        for p in pitches:
            opts = [i for i, t in enumerate(tuning) if abs(p - t - x) < 1e-6 or abs(p - t) < 1e-6]
            options.append(opts)
        if any(not o for o in options):
            continue
        for strings in product(*options):
            if len(set(strings)) < len(strings):
                continue
            cost = 0.3 * abs(x - where) + 0.3 * (max(strings) - min(strings)) + 0.02 * x
            if glide and previous is not None and len(strings) == 1 and strings[0] != previous:
                cost += 4.0
            if best is None or cost < best[0]:
                best = (cost, x, strings)
    if best is None:
        return None
    return best[1], best[2]


def slide(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator, s: dict) -> np.ndarray:
    """The slide guitar's stem: (length, 2), its body as two microphones hear it, or its amp; levelled so a
    reference lick comes out as loud whatever the maker's guitar, body, slide and amp."""
    notes = _prepare(notes, sr, length)
    if not notes:
        return np.zeros((length, 2))
    seed = int(make.integers(1 << 31))
    d = _slide_built(seed)
    kind = s.get("slide") if s.get("slide") in KINDS else d["kind"]
    keys = ("brightness", "wear", "ornament", "body", "tonic", "maker")
    trim = _slide_trim(seed, kind, tuple(round(float(s.get(k, v)), 6) for k, v in zip(keys, (0.5, 0.25, 0.5, 1.0, 62, 0))),
                       sr)
    return _slide_sound(notes, sr, length, rng, d, kind, s) * trim


@lru_cache(maxsize=64)
def _slide_trim(seed: int, kind: str, key: tuple, sr: int) -> float:
    """The gain that brings this maker's slide, played this way, to a fixed loudness on a reference lick (three
    notes slid into and held with vibrato on the D and A strings)."""
    s = dict(zip(("brightness", "wear", "ornament", "body", "tonic", "maker"), key))
    tonic = int(s["tonic"])
    lick = [Note("slide", 0.05, 0.9, float(tonic + 7), 0.6, art="slide"), Note("slide", 1.0, 0.5, float(tonic + 4), 0.6),
            Note("slide", 1.5, 1.4, float(tonic), 0.6, art="vibrato")]
    y = _slide_sound(lick, sr, int(3.2 * sr), np.random.default_rng([seed, 83]), _slide_built(seed), kind, s)
    return float(10.0 ** ((SLIDE_REFERENCE - loudness(y, sr)) / 20.0))


SLIDE_REFERENCE = -9.9  # LUFS of the reference lick, unplaced: so the fills at vel 0.6 sit as a lead (-20.7)


def _slide_sound(notes, sr: int, length: int, rng: np.random.Generator, d: dict, kind: str, s: dict) -> np.ndarray:
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
    size = float(np.clip(s.get("body", 1.0), 0.8, 1.25))
    tuning, _, _, _ = open_tuning(int(s.get("tonic", 62)), d["prefer"])
    strings, rig = _slide_strings(d, tuning, bright, wear, s, sr, kind)
    lo, hi = min(tuning), max(tuning) + 20.0
    notes = [replace(n, pitch=fretboard.in_range(n.pitch, lo, hi)) for n in notes]
    segs, position, vib, swells = _slide_tracks(_groups(notes, 0.02), tuning, sr, rng, d, ornament, length,
                                                 kind == "electric")
    _finish(segs, strings, sr, length, position, None, vib, ring_db=70.0)
    segs = segs + _behind(segs, strings, position, vib, sr, length, d)
    wound = [0, 1, 2] if kind == "electric" else [0, 1, 2, 3]
    if rig is not None:
        coil, circuit, rig_amp, rig_s = rig
        emf = electric._pickup_voltage(segs, strings, coil, circuit, sr, length, rng)
        emf += _bar_scrape(position, segs, length, sr, rng, wound, SLIDE_SCRAPE * electric.EMF * coil.sensitivity)
        volume = _swell_track(swells, length, sr, floor=-30.0)
        if volume is not None:
            emf *= volume
        chain = electric._chain(rig_amp, rig_s, sr)
        chain.p[21] = electric.master_volume("electric", rig_s, sr)
        return _warmed(chain, emf, sr)
    force = np.zeros(length)
    for seg in segs:
        y = fretboard.sound(seg, strings, sr, rng)
        if seg.picks and seg.picks[0][2] != "behind":
            y = y + _rattle(y, sr, d["rattle"] * (0.5 + wear))
        end = min(length, seg.start + len(y))
        force[seg.start:end] += y[: end - seg.start]
    force += _bar_scrape(position, segs, length, sr, rng, wound, SLIDE_SCRAPE * (1.5 if d["brass"] else 1.0))
    box = RESONATOR if kind == "resonator" else body.GUITAR
    ir = body.impulse_response(box, sr, seed=d["body_seed"], size=size)
    return body.resonate(force, ir)


SLIDE_SCRAPE = 0.005  # the slide's scrape at full speed: 20 dB under a note on a wound string, 30 on a plain one


def _slide_tracks(groups, tuning, sr: int, rng: np.random.Generator, d: dict, ornament: float, length: int,
                  electric_: bool = False):
    """Walk the part with a slide: where it sits for each note, its moves (glides, slides in, falls, the small
    correction after landing flat), the damping of what rings before the slide jumps, and its vibrato."""
    position = Track(0.0)
    vib = Vibrato()
    swells: list[tuple[int, int]] = []
    current: dict[int, Segment] = {}
    segs: list[Segment] = []
    where, previous = 0.0, None
    last = -sr
    ms = sr / 1000.0
    for k, group in enumerate(groups):
        t0 = int(round(group[0].start * sr))
        if t0 >= length:
            break
        arts = {n.art for n in group}
        dur = max(n.dur for n in group)
        sounding = {i for i, seg in current.items() if seg.start + seg.held > t0 - int(0.03 * sr)}
        glide = bool(arts & set(LEGATO))
        placed = place_slide(tuple(n.pitch for n in group), tuning, where, previous, glide)
        if placed is None and len(group) > 1:  # a chord no one slide position holds: its top note alone
            group = [max(group, key=lambda n: n.pitch)]
            placed = place_slide((group[0].pitch,), tuning, where, previous, glide)
        if placed is None:
            continue
        x, chosen = placed
        stopped = any(abs(n.pitch - tuning[i]) > 1e-6 for n, i in zip(group, chosen))
        legato = glide and stopped and bool(sounding & set(chosen))
        art = group[0].art if len(group) == 1 else ""
        if stopped:
            if legato:  # half the glide before the beat, so it lands near it
                over = int(np.clip((0.06 + 0.025 * abs(x - position.at(t0))) * d["glide"], 0.05, 0.3) * sr)
                over = max(int(0.03 * sr), min(over, int(0.6 * dur * sr), int(0.6 * max(t0 - last, 1))))
                position.move(t0 - over // 2, x, over)
            else:
                for i in sounding:  # the picking hand damps what rings before the slide jumps
                    seg = current[i]
                    if seg.start + seg.held > t0 - int(0.03 * sr) and abs(x - where) > 0.05:
                        seg.held = max(1, min(seg.held, t0 - seg.start - int(0.03 * sr)))
                        seg.release = 0.025
                pre = t0 - int(8 * ms)
                if art in ("slide", "bend"):  # from two or three semitones below (a bend: a tone, slower)
                    under = 2.0 if art == "bend" else float(rng.integers(2, 4))
                    position.move(pre, x - min(under, x), int(6 * ms))
                    over = np.clip((0.5 if art == "bend" else 0.3) * dur, 0.06, 0.3 if art == "bend" else 0.15)
                    position.move(t0 + int(10 * ms), x, int(over * sr))
                else:  # landing a touch flat and settling onto the note
                    flat = d["flat"] / 100.0 * (0.4 + 0.6 * ornament)
                    position.move(pre, x - min(flat, x), int(6 * ms))
                    position.move(t0 + int(5 * ms), x, int(rng.uniform(0.05, 0.1) * sr))
            where = x
        for note, i in sorted(zip(group, chosen), key=lambda z: z[0].pitch):
            held = max(1, int(round(note.dur * sr)))
            if note.art == "mute":
                held = min(held, int(0.12 * sr))
            seg = current.get(i)
            if legato and seg is not None and i in sounding:
                seg.held = max(seg.held, t0 - seg.start + held)
                continue
            if seg is not None and seg.start + seg.held > t0:
                seg.held = max(1, t0 - seg.start - int(0.002 * sr))
                seg.release = 0.02
            is_open = abs(note.pitch - tuning[i]) < 1e-6
            vel = note.vel * (0.7 if note.art == "swell" and not electric_ else 1.0)
            seg = Segment(string=i, start=t0, base=tuning[i], held=held, picks=[(0, vel, "pick")],
                          hand=0.0 if is_open else 1.0)
            current[i] = seg
            segs.append(seg)
            if note.art == "fall" and not is_open:  # the slide leaves the note downward as it ends
                position.move(t0 + int(0.65 * held), x - float(min(x, rng.uniform(3.0, 6.0))), int(0.35 * held))
                seg.release = 0.12
        previous = chosen[-1] if len(chosen) == 1 else previous
        swell = 0
        if "swell" in arts and electric_:  # the volume knob under the little finger
            swell = int(np.clip(0.35 * dur, 0.2, 0.7) * sr)
            swells.append((t0, swell))
        after = int(round(groups[k + 1][0].start * sr)) if k + 1 < len(groups) else t0 + int(dur * sr)
        hold = min(after, t0 + int(dur * sr))
        wide = "vibrato" in arts
        if stopped and "fall" not in arts and (hold - t0 > 0.6 * sr or wide):
            depth = (6.0 + 10.0 * ornament) * (2.2 if wide else 1.0)
            grow = 0.3 if "swell" not in arts else max(0.3, 0.6 * (hold - t0) / sr)
            vib.add(t0 + int(0.2 * sr) + swell, hold, d["vibrato"] * rng.uniform(0.95, 1.05), depth, grow)
        last = t0
    return segs, position, vib, swells


def behind_semitones(x):
    """How far above the open string the part behind the slide sounds, the slide `x` semitones up the neck:
    that part is 1 - 2^(-x/12) of the string."""
    return -12.0 * np.log2(np.maximum(1.0 - 2.0 ** (-np.asarray(x, dtype=np.float64) / 12.0), 1e-6))


def _behind(segs, strings: Strings, position: Track, vib: Vibrato, sr: int, length: int, d: dict) -> list[Segment]:
    """The string between the slide and the nut: each picked note's energy leaks past the slide into it, and it
    rings high and faint, falling as the slide climbs, until the trailing finger damps it."""
    level, t60 = d["behind"]
    out = []
    for seg in segs:
        if seg.hand <= 0 or not seg.picks:
            continue
        x0 = position.at(seg.start)
        if x0 < 1.5:
            continue
        up = float(behind_semitones(x0))
        pitch = strings.open[seg.string] + up
        if pitch > 105.0:
            continue
        n = min(int(1.3 * t60 * sr), seg.end, length - seg.start)
        if n < int(0.01 * sr):
            continue
        x = position.window(seg.start, n)
        wobble = vib.window(seg.start, n, sr)
        if wobble is not None:
            x = x + wobble / 100.0
        f = midi_to_hz(pitch)
        ring = t60 / (strings.t60 * (220.0 / f) ** 0.4)  # its own decay: the finger's, not the string's
        _, vel, _ = seg.picks[0]
        b = Segment(string=seg.string, start=seg.start, base=pitch, held=n, picks=[(0, vel * level, "behind")],
                    hand=1.0, release=0.02, end=n, decay=ring)
        track = 100.0 * (behind_semitones(x) - up)
        if np.any(np.abs(track) > 1e-6):
            b.bar = track
        out.append(b)
    return out


def _rattle(y: np.ndarray, sr: int, amount: float) -> np.ndarray:
    """A string pressed too lightly slaps the slide on its big swings as the note starts: the tops of its
    own waveform, clipped off smoothly and high-passed, fading in a fifth of a second."""
    n = min(len(y), int(0.2 * sr))
    if n < 64 or amount <= 0:
        return np.zeros_like(y)
    head = y[:n]
    edge = 0.5 * np.max(np.abs(head)) + 1e-12
    k = 8.0 / edge
    over = np.logaddexp(0.0, k * (head - edge)) / k  # softplus: smooth, so its harmonics fall fast
    buzz = sosfilt(butter(2, 1200.0, btype="highpass", fs=sr, output="sos"), over)
    out = np.zeros_like(y)
    out[:n] = buzz * np.linspace(1.0, 0.0, n) ** 2 * 0.6 * amount
    return out


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A part's dry stem, (length, 2): the steel's through its amp, the slide's through its body or amp."""
    s = dict(settings or {})
    if name == "slide":
        return slide(notes, sr, length, rng, make, s)
    return steel(notes, sr, length, rng, make, s)
