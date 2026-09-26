"""Strings stopped by a bar: a pedal steel guitar, and a bottleneck slide guitar.

The pedal steel. Ten strings tuned to E9 (from the nearest the player:
F#4 D#4 G#4 E4 B3 G#3 F#3 E3 D3 B2), stopped by a steel bar rather than
fretted, with the standard three pedals and four knee levers: pedal A raises
strings 5 and 10 a tone (B to C#), B raises 3 and 6 a semitone (G# to A), C
raises 4 and 5 a tone (E to F#, B to C#); the left knee raises (LKL) or lowers
(LKR) strings 4 and 8 a semitone, the right knee raises 1 and 7 (RKL) or
lowers 2 and 9 (RKR). Each chord is found as a player finds it: the bar at a
fret, the pedals and levers that make the notes, the fewest of them and the
tightest grip, the bar near where it was. A "glide" is the steel's own move:
no pick, the bar slides to the new fret and every string still sounding
slides with it by the same interval, while the pedals and levers take the
strings that must move by other intervals (up to a tone) with their own
travel. Every sustained chord gets the bar's vibrato (5.5 to 6.5 Hz, 10 to
30 cents peak to peak with the ornament), all held strings together; the bar
scrapes along the wound strings as it moves. "swell" is the volume pedal:
picked with the pedal down and swelled in over 0.2 to 0.6 s, so the attack
vanishes. The strings (metal finger picks, a thumb pick on the low ones) ring
very long on a rigid steel body: 8 to 15 s in the middle register, until
the player blocks them; a loop that has died 80 dB is not computed further.
Some players tune their thirds flat so the major chords ring pure (the
Newman chart: the G# strings 12 cents low, D# 10, the A pedal's C# 12): the
maker decides. It plays through a clean amp with plenty of headroom, its
spring reverb and a 12- or 15-inch speaker (amp.py). Articulations: ""
(picked; notes together are pinched, not strummed), "glide", "swell",
"vibrato" (a deeper bar vibrato), "mute" (blocked right after the pick).

The slide. An acoustic flat-top or a resonator guitar (by the maker), tuned
open to the song's key (open D or open G, retuned up to three semitones or
capoed), played with a glass or brass bottleneck: the slide stops every
string at once at any pitch, so the same glide machinery moves it, notes land
a touch flat and settle (a slide player's intonation), long notes get a slide
vibrato, the slide hisses and whirs along the wound strings as it moves, and a
string not pressed quite hard enough rattles against it as a note starts.
Articulations: "" (picked, landing a little flat), "slide" (picked two or
three semitones below and slid up), "glide" (no pick: the slide moves from the
last note), "vibrato" (a wide slide vibrato), "fall" (slides away down as it
ends), "mute" (damped right after the pick).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import combinations, product

import numpy as np
from scipy.signal import butter, oaconvolve, sosfilt

from ..score import Note
from ..theory import midi_to_hz
from . import amp, body, fretboard
from .fretboard import Segment, Strings
from .master import loudness

STEEL_ARTS = {
    "": "picked (notes together are pinched by thumb and fingers)",
    "glide": "no pick: the bar (and pedals) move from the last notes to these; every held string moves with the bar",
    "swell": "picked with the volume pedal down and swelled in over 0.2-0.6 s: no attack",
    "vibrato": "a deeper bar vibrato",
    "mute": "blocked right after the pick",
}
SLIDE_ARTS = {
    "": "picked with the slide already there, landing a touch flat and settling",
    "slide": "picked two or three semitones below and slid up to the note",
    "glide": "no pick: the slide moves from the last note to this one",
    "vibrato": "a wide slide vibrato",
    "fall": "slides away down as the note ends",
    "mute": "damped right after the pick",
}

SPEC = {
    "steel": dict(
        family="bowed", role="comping", register=(45, 88), place=(0.45, 0.5), level=0.2, poly=True,
        articulations=STEEL_ARTS,
        about="a pedal steel guitar (E9, ten strings, three pedals and four knee levers) through a clean amp "
              "with spring reverb: swells, bar glides, pedal moves, bar vibrato"),
    "slide": dict(
        family="plucked", role="comping", register=(40, 84), place=(0.4, 0.5), level=0.2, poly=True,
        articulations=SLIDE_ARTS,
        about="a bottleneck slide guitar (an acoustic flat-top or a resonator, open-tuned to the key)"),
}

# --- the pedal steel's neck -----------------------------------------------------------------------

E9 = {1: 66, 2: 63, 3: 68, 4: 64, 5: 59, 6: 56, 7: 54, 8: 52, 9: 50, 10: 47}  # string number: MIDI
ORDER = (10, 9, 8, 7, 6, 5, 4, 3, 2, 1)  # the Strings' order, lowest first
OPEN = tuple(float(E9[k]) for k in ORDER)
PEDALS = {"A": {5: 2, 10: 2}, "B": {3: 1, 6: 1}, "C": {4: 2, 5: 2}, "LKL": {4: 1, 8: 1}, "LKR": {4: -1, 8: -1},
          "RKL": {1: 1, 7: 1}, "RKR": {2: -1, 9: -1}}
WOUND = {6, 7, 8, 9, 10}
BARS = 23  # frets the bar may sit at (0 is the open strings)


@lru_cache(maxsize=1)
def copedant() -> tuple[tuple[tuple[str, ...], np.ndarray], ...]:
    """Every combination of up to three pedals and levers a foot and two knees can hold (a knee lever is
    pushed one way at a time), with the semitones it moves each string (in ORDER)."""
    out = []
    for k in range(4):
        for chosen in combinations(PEDALS, k):
            if {"LKL", "LKR"} <= set(chosen) or {"RKL", "RKR"} <= set(chosen):
                continue
            change = dict.fromkeys(E9, 0)
            fine = True
            for name in chosen:
                for string, d in PEDALS[name].items():
                    if change[string] and np.sign(change[string]) != np.sign(d):
                        fine = False
                    change[string] = max(change[string], d) if d > 0 else min(change[string], d)
            if fine:
                out.append((chosen, np.array([change[s] for s in ORDER], dtype=np.int64)))
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


@lru_cache(maxsize=4096)
def grip(pitches: tuple[int, ...], bar: int, sounding: frozenset, glide: bool) -> Grip:
    """How a steel player makes these notes: the bar's fret, the pedals and levers, a string for each note.
    Fewest pedals, tightest grip, the bar near where it was; for a glide, the notes on strings that are
    already sounding."""
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
            if best is None or cost < best.cost:
                best = Grip(int(f), names, tuple(int(v) for v in change), tuple(int(s) for s in strings), cost)
    if best is not None:
        return best
    # beyond the copedant: each note on the string nearest it, moved up to a tone by a lever of its own
    for f in sorted(range(BARS), key=lambda x: abs(x - bar)):
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
    raise ValueError(f"no grip for {pitches}")


def just_offset(string: int, change: int, just: bool) -> float:
    """Cents a string sits off equal temperament in a pure-thirds tuning (Jeff Newman's chart): the G#
    strings 12 low, the D# 10 low, the A pedal's C# 12 low; the other pedal stops are tuned equal."""
    if not just:
        return 0.0
    number = ORDER[string]
    if number in (3, 6) and change == 0:
        return -12.0
    if number == 2 and change == 0:
        return -10.0
    if number in (5, 10) and change == 2:
        return -12.0
    return 0.0


# --- tracks over a whole part ----------------------------------------------------------------------


class Track:
    """A value over a part (the bar's fret, a pedal's semitones) that moves now and then: each move from
    wherever it is to a target, over some samples, along a raised cosine (a glide) or faster (a step)."""

    def __init__(self, value: float = 0.0):
        self.value = float(value)
        self.moves: list[tuple[int, float, int]] = []  # (at, target, over), in order

    def move(self, at: int, target: float, over: int) -> None:
        self.moves.append((int(at), float(target), max(1, int(over))))

    def at(self, t: int) -> float:
        value = self.value
        for at, target, over in self.moves:
            if at >= t:
                break
            k = min(t - at, over)
            ramp = 0.5 - 0.5 * np.cos(np.pi * k / over)
            value = value + (target - value) * ramp
        return float(value)

    def window(self, t0: int, n: int) -> np.ndarray:
        out = np.full(n, self.at(t0))
        for at, target, over in self.moves:
            if at + over <= t0 or at >= t0 + n:
                continue
            start = self.at(at)
            k = np.arange(max(at, t0), min(at + over, t0 + n))
            ramp = 0.5 - 0.5 * np.cos(np.pi * (k - at) / over)
            out[k - t0] = start + (target - start) * ramp
            out[min(at + over, t0 + n) - t0:] = target
        return out

    def moving(self, t0: int, n: int) -> bool:
        return any(at < t0 + n and at + over > t0 for at, _, over in self.moves)


class Vibrato:
    """A bar's (or slide's) vibrato: episodes of a sine in cents, each fading in and out."""

    def __init__(self):
        self.episodes: list[tuple[int, int, float, float]] = []  # (start, end, Hz, depth in cents)

    def add(self, start: int, end: int, hz: float, depth: float) -> None:
        if end > start:
            self.episodes.append((int(start), int(end), float(hz), float(depth)))

    def window(self, t0: int, n: int, sr: int) -> np.ndarray | None:
        out = None
        for start, end, hz, depth in self.episodes:
            if end <= t0 or start >= t0 + n:
                continue
            if out is None:
                out = np.zeros(n)
            k = np.arange(max(start, t0), min(end, t0 + n))
            t = (k - start) / sr
            grow = np.clip(t / 0.3, 0.0, 1.0) * np.clip((end - k) / (0.1 * sr), 0.0, 1.0)
            out[k - t0] += depth * grow * np.sin(2.0 * np.pi * hz * t)
        return out


def _groups(notes: list[Note], within: float = 0.03) -> list[list[Note]]:
    groups: list[list[Note]] = []
    for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if groups and note.start - groups[-1][0].start < within:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def _scrape(n: int, speed: np.ndarray, sr: int, rng: np.random.Generator, pitch_m: float = 0.0004,
            fret_m: float = 0.02) -> np.ndarray:
    """A bar or slide dragged along wound strings: a whir at the rate it crosses the winding's ridges
    (its speed over their pitch) and a hiss above, both as loud as it moves fast."""
    rate = np.abs(speed) * fret_m / pitch_m  # ridges a second: speed in frets a second
    phase = 2.0 * np.pi * np.cumsum(rate) / sr
    whir = np.sign(np.sin(phase)) * 0.5 + 0.5 * np.sin(phase)
    hiss = sosfilt(butter(2, [1500.0, 6000.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n))
    level = np.clip(np.abs(speed) / 20.0, 0.0, 1.0)
    return (0.6 * sosfilt(butter(2, [200.0, 3000.0], btype="bandpass", fs=sr, output="sos"), whir) + 0.4 * hiss) * level


# --- the pedal steel ------------------------------------------------------------------------------


@lru_cache(maxsize=32)
def _steel_built(seed: int) -> dict:
    g = np.random.default_rng(seed)
    d: dict = {}
    d["humbucker"] = bool(g.random() < 0.5)
    d["just"] = bool(g.random() < 0.5)
    d["t60"] = float(g.uniform(9.0, 12.0))  # s at 220 Hz: a steel's rigid body and a steel bar
    d["pickup"] = float(g.uniform(0.038, 0.05))  # m from the bridge, on a 0.622 m (24.5 inch) scale
    d["pick"] = float(g.uniform(0.08, 0.12))
    d["poles"] = tuple(g.normal(0.0, 0.8, 10))
    d["detune"] = tuple(g.standard_normal(10))
    d["vibrato"] = float(g.uniform(5.5, 6.5))
    d["glide"] = float(g.uniform(0.8, 1.2))  # how slowly this player glides
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
        coil, circuit = amp.HUMBUCKER, dict(pot=500e3, tone=None, tone_cap=22e-9, cable=500e-12)
    else:
        comb = ((d["pickup"] / scale, 1.0),)
        coil, circuit = amp.SINGLE, dict(pot=500e3, tone=None, tone_cap=22e-9, cable=500e-12)
    strings = Strings(
        open=OPEN, comb=comb, offsets=tuple(z * (0.3 + 3.0 * wear) for z in d["detune"]),
        gains=tuple(10.0 ** (p / 20.0) for p in d["poles"]),
        damping=(4e-6 + 4e-6 * wear) * (1.4 - 0.8 * bright), t60=d["t60"] * (1.0 - 0.25 * wear), along=1.2,
        heard=0.45, driven=0.6, pick=d["pick"], hardness=0.95, click=0.35, frets=BARS - 1,
        kinds=(("thumb", (1.0, 0.85, 1.0, 0.7)),))
    return strings, coil, circuit


def _bar_tracks(groups, strings: Strings, sr: int, rng: np.random.Generator, d: dict, ornament: float,
                length: int, allow_pedals: bool = True):
    """Walk the part as a steel player does: grips, bar moves and pedal moves, blocks, swells, vibrato.
    Returns the segments (tracks still to be cut from the part's), the bar, the pedals, the vibrato, the
    volume pedal and the bar's moves (for its scrape)."""
    bar = Track(0.0)
    pedals = [Track(0.0) for _ in OPEN]
    vib = Vibrato()
    volume: list[tuple[int, int]] = []  # (pick sample, swell samples)
    current: dict[int, Segment] = {}
    segs: list[Segment] = []
    where = 0
    state = [0] * len(OPEN)
    for k, group in enumerate(groups):
        t0 = int(round(group[0].start * sr))
        if t0 >= length:
            break
        pitches = tuple(int(round(n.pitch)) for n in group)
        glide = any(n.art == "glide" for n in group)
        sounding = frozenset(i for i, seg in current.items() if seg.start + seg.held > t0 - int(0.03 * sr))
        g = grip(pitches, where, sounding, glide)
        dur = max(n.dur for n in group)
        moved = [i for i in range(len(OPEN)) if g.change[i] != state[i]]
        if glide:
            over = int(np.clip(0.35 * dur, 0.08, 0.35) * d["glide"] * sr)
            if g.bar != where:
                bar.move(t0, g.bar, over)
            for i in moved:  # a pedal's travel is quicker than a glide
                pedals[i].move(t0, g.change[i], int(0.7 * over))
        else:
            # the player blocks what still rings before moving the bar or the pedals under it
            for i, seg in current.items():
                if i in sounding and (g.bar != where or i in moved) and seg.start + seg.held > t0:
                    seg.held = max(1, t0 - seg.start - int(0.02 * sr))
                    seg.release = 0.03
            if g.bar != where:
                bar.move(t0 - int(0.015 * sr), g.bar, int(0.01 * sr))
            for i in moved:
                pedals[i].move(t0 - int(0.015 * sr), g.change[i], int(0.01 * sr))
        spread = 0.0
        for note, i in sorted(zip(group, g.strings), key=lambda x: x[0].pitch):
            start = t0 + (int(spread * sr) if not glide else 0)  # thumb and fingers pinch, a few ms apart
            spread += rng.uniform(0.0, 0.004)
            held = max(1, int(round(note.dur * sr)))
            if note.art == "mute":
                held = min(held, int(0.1 * sr))
            seg = current.get(i)
            if glide and seg is not None and i in sounding:
                seg.held = max(seg.held, start - seg.start + held)
                continue
            if seg is not None and seg.start + seg.held > start:
                seg.held = max(1, start - seg.start - int(0.002 * sr))
                seg.release = 0.02
            kind = "thumb" if ORDER[i] >= 7 else "pick"
            # a glide onto a string that wasn't ringing is picked, a little softer, and rides the bar in
            seg = Segment(string=i, start=start, base=OPEN[i], held=held,
                          picks=[(0, note.vel * (0.8 if glide else 1.0), kind)], hand=float(g.bar))
            current[i] = seg
            segs.append(seg)
        if any(n.art == "swell" for n in group):
            volume.append((t0, int(np.clip(0.45 * dur, 0.2, 0.6) * sr)))
        # the bar's vibrato on anything held long enough, deeper where asked
        after = int(round(groups[k + 1][0].start * sr)) if k + 1 < len(groups) else t0 + int(dur * sr)
        hold = min(after, t0 + int(dur * sr))
        if g.bar > 0 and (hold - t0 > 0.7 * sr or any(n.art == "vibrato" for n in group)):
            depth = (5.0 + 10.0 * ornament) * (1.6 if any(n.art == "vibrato" for n in group) else 1.0)
            begin = t0 + int((0.35 if not glide else 0.5) * sr)
            vib.add(begin, hold, d["vibrato"] * rng.uniform(0.95, 1.05), depth)
        where, state = g.bar, list(g.change)
    return segs, bar, pedals, vib, volume


def _finish(segs, strings: Strings, sr: int, length: int, bar: Track, pedals, vib: Vibrato, just: bool = False,
            ring_db: float = 80.0) -> None:
    """Each segment's end (the block's tail, or 80 dB down), its pitch where it starts, and its length and
    tension tracks, cut from the part's bar (or slide), pedals and vibrato. A segment with hand 0 is an
    open string, which the bar doesn't touch."""
    for seg in segs:
        i = seg.string
        stopped = seg.hand > 0
        pedal = pedals[i] if pedals is not None else None
        semis = pedal.at(seg.start) if pedal is not None else 0.0
        seg.base = strings.open[i] + (bar.at(seg.start) if stopped else 0.0) + semis \
            + just_offset(i, int(round(semis)), just) / 100.0
        stop = seg.held + int(max(0.02, 1.4 * seg.release) * sr)
        dies = int(fretboard.ring_time(strings, seg.base, ring_db) * sr)
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
            if just:  # a pedal's stop is tuned to its own pitch: the string's offset changes as it moves
                marks = np.arange(0, n, 64)
                offsets = np.array([just_offset(i, int(round(v)), True) for v in moved[marks]])
                cents = cents + np.interp(np.arange(n), marks, offsets) - just_offset(i, int(round(semis)), True)
            seg.tension = cents


def _swell_track(volume, length: int, sr: int) -> np.ndarray | None:
    """The volume pedal: down (30 dB) just before each swelled pick, then up over the swell along a raised
    cosine in decibels."""
    if not volume:
        return None
    gain_db = np.zeros(length)
    for at, over in volume:
        down = int(0.03 * sr)
        a = max(0, at - down)
        k = np.arange(a, min(length, at))
        gain_db[k] = np.minimum(gain_db[k], -30.0 * (k - a + 1) / max(1, at - a))
        k = np.arange(at, min(length, at + over))
        rise = -30.0 * (0.5 + 0.5 * np.cos(np.pi * (k - at) / over))
        gain_db[k] = np.minimum(gain_db[k], rise)
    return 10.0 ** (gain_db / 20.0)


def _bar_scrape(bar: Track, segs, length: int, sr: int, rng: np.random.Generator, wound, level: float) -> np.ndarray:
    """The bar's scrape as it moves under wound strings that are sounding."""
    out = np.zeros(length)
    for at, target, over in bar.moves:
        if over < int(0.03 * sr) or at >= length:
            continue
        n = min(over, length - at)
        under = sum(1 for s in segs if s.string in wound and s.start <= at < s.start + s.end)
        if not under:
            continue
        track = bar.window(at, n)
        speed = np.gradient(track) * sr  # frets a second
        out[at: at + n] += _scrape(n, speed, sr, rng) * level * np.sqrt(under)
    return out


def steel(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator, s: dict) -> np.ndarray:
    """The pedal steel's stem: (length, 2), as its amp's two microphones hear it."""
    notes = [replace(n, pitch=fretboard.in_range(n.pitch, 45.0, 88.0)) for n in _prepare(notes, sr, length)]
    if not notes:
        return np.zeros((length, 2))
    seed = int(make.integers(1 << 31))
    d = _steel_built(seed)
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
    strings, coil, circuit = _steel_strings(d, bright, wear)
    segs, bar, pedals, vib, volume = _bar_tracks(_groups(notes), strings, sr, rng, d, ornament, length)
    _finish(segs, strings, sr, length, bar, pedals, vib, d["just"])
    emf = _voltage(segs, strings, coil, circuit, sr, length, rng)
    emf += _bar_scrape(bar, segs, length, sr, rng, [ORDER.index(w) for w in WOUND], 0.004 * coil.sensitivity)
    swell = _swell_track(volume, length, sr)
    if swell is not None:
        emf *= swell
    chain = amp.Chain(d["amp"], sr, os_=2)
    chain.p[21] = _steel_master(seed, bright, wear, sr)
    return amp.play(chain, emf) * STEEL_OUT


STEEL_OUT = 2.5
EMF = 0.055  # volts per unit of string velocity for a single coil (as electric.py's)


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
    segs, bar, pedals, vib, volume = _bar_tracks(_groups(notes), strings, sr, rng, d, 0.5, int(3.0 * sr))
    _finish(segs, strings, sr, int(3.0 * sr), bar, pedals, vib, d["just"])
    emf = _voltage(segs, strings, coil, circuit, sr, int(3.0 * sr), rng)
    chain = amp.Chain(d["amp"], sr, os_=2)
    return float(10.0 ** ((-20.0 - loudness(amp.play(chain, emf), sr)) / 20.0))


# --- the slide guitar -----------------------------------------------------------------------------

OPEN_D = (38, 45, 50, 54, 57, 62)  # D A D F# A D, lowest first
OPEN_G = (38, 43, 50, 55, 59, 62)  # D G D G B D
SHAPES = {"open D": (OPEN_D, 2), "open G": (OPEN_G, 7)}  # the tuning and its root's pitch class

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
    d["resonator"] = bool(g.random() < 0.45)
    d["prefer"] = "open D" if g.random() < 0.5 else "open G"
    d["brass"] = bool(g.random() < 0.5)  # a brass slide rings brighter and longer than glass
    d["t60"] = float(g.uniform(1.6, 2.2) if d["resonator"] else g.uniform(2.0, 2.8))  # the plane driving the top
    d["pick"] = float(g.uniform(0.1, 0.16))
    d["detune"] = tuple(g.standard_normal(6))
    d["flat"] = float(g.uniform(15.0, 35.0))  # cents a note lands under its pitch before it settles
    d["vibrato"] = float(g.uniform(4.8, 6.0))
    d["glide"] = float(g.uniform(0.8, 1.2))
    d["rattle"] = float(g.uniform(0.3, 1.0))
    d["body_seed"] = int(g.integers(1 << 30))
    return d


def _slide_strings(d: dict, tuning, bright: float, wear: float) -> Strings:
    return Strings(
        open=tuning, comb=(), offsets=tuple(z * (0.5 + 4.0 * wear) for z in d["detune"]),
        damping=(1.6e-5 + 1e-5 * wear) * (1.3 - 0.6 * bright) * (0.75 if d["brass"] else 1.0),
        t60=d["t60"] * (1.15 if d["brass"] else 1.0) * (1.0 - 0.25 * wear), along=2.5, heard=0.35, driven=1.0,
        pick=d["pick"], hardness=0.7, click=0.6, touch=0.2, frets=20)


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
    """The slide guitar's stem: (length, 2), its body as two microphones hear it."""
    notes = _prepare(notes, sr, length)
    if not notes:
        return np.zeros((length, 2))
    seed = int(make.integers(1 << 31))
    d = _slide_built(seed)
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    ornament = float(np.clip(s.get("ornament", 0.5), 0.0, 1.0))
    size = float(np.clip(s.get("body", 1.0), 0.8, 1.25))
    tuning, _, _, _ = open_tuning(int(s.get("tonic", 62)), d["prefer"])
    strings = _slide_strings(d, tuning, bright, wear)
    lo, hi = min(tuning), max(tuning) + 20.0
    notes = [replace(n, pitch=fretboard.in_range(n.pitch, lo, hi)) for n in notes]
    segs, position, vib = _slide_tracks(_groups(notes, 0.02), tuning, strings, sr, rng, d, ornament, length)
    _finish(segs, strings, sr, length, position, None, vib, False, ring_db=70.0)
    force = np.zeros(length)
    for seg in segs:
        y = fretboard.sound(seg, strings, sr, rng)
        y = y + _rattle(y, sr, d["rattle"] * (0.5 + wear))
        end = min(length, seg.start + len(y))
        force[seg.start:end] += y[: end - seg.start]
    wound = [0, 1, 2]
    force += _bar_scrape(position, segs, length, sr, rng, wound, 0.02 * (1.5 if d["brass"] else 1.0))
    box = RESONATOR if d["resonator"] else body.GUITAR
    ir = body.impulse_response(box, sr, seed=d["body_seed"], size=size)
    return body.resonate(force, ir) * SLIDE_OUT


SLIDE_OUT = 0.5


def _slide_tracks(groups, tuning, strings: Strings, sr: int, rng: np.random.Generator, d: dict, ornament: float,
                  length: int):
    """Walk the part with a slide: where it sits for each note, its moves (glides, slides in, falls, the small
    correction after landing flat), blocks, and its vibrato."""
    position = Track(0.0)
    vib = Vibrato()
    current: dict[int, Segment] = {}
    segs: list[Segment] = []
    where, previous = 0.0, None
    for k, group in enumerate(groups):
        t0 = int(round(group[0].start * sr))
        if t0 >= length:
            break
        glide = any(n.art == "glide" for n in group)
        placed = place_slide(tuple(n.pitch for n in group), tuning, where, previous, glide)
        if placed is None:
            continue
        x, chosen = placed
        stopped = any(abs(n.pitch - tuning[i]) > 1e-6 for n, i in zip(group, chosen))
        dur = max(n.dur for n in group)
        sounding = {i for i, seg in current.items() if seg.start + seg.held > t0 - int(0.03 * sr)}
        art = group[0].art if len(group) == 1 else ""
        if stopped:
            if glide and sounding & set(chosen):
                over = int(np.clip(0.35 * dur, 0.06, 0.3) * d["glide"] * sr)
                position.move(t0, x, over)
            else:
                for i in sounding:  # the picking hand damps what rings before the slide jumps
                    seg = current[i]
                    if seg.start + seg.held > t0 and abs(x - where) > 0.05:
                        seg.held = max(1, t0 - seg.start - int(0.015 * sr))
                        seg.release = 0.03
                if art == "slide":  # from two or three semitones below
                    k_from = float(rng.integers(2, 4))
                    position.move(t0 - int(0.01 * sr), x - k_from, int(0.008 * sr))
                    position.move(t0 + int(0.01 * sr), x, int(np.clip(0.3 * dur, 0.06, 0.15) * sr))
                else:  # landing a touch flat and settling onto the note
                    flat = d["flat"] / 100.0 * (0.4 + 0.6 * ornament)
                    position.move(t0 - int(0.01 * sr), x - flat, int(0.008 * sr))
                    position.move(t0 + int(0.005 * sr), x, int(rng.uniform(0.05, 0.1) * sr))
            where = x
        for note, i in sorted(zip(group, chosen), key=lambda z: z[0].pitch):
            held = max(1, int(round(note.dur * sr)))
            if note.art == "mute":
                held = min(held, int(0.12 * sr))
            seg = current.get(i)
            if glide and seg is not None and i in sounding:
                seg.held = max(seg.held, t0 - seg.start + held)
                continue
            if seg is not None and seg.start + seg.held > t0:
                seg.held = max(1, t0 - seg.start - int(0.002 * sr))
                seg.release = 0.02
            is_open = abs(note.pitch - tuning[i]) < 1e-6
            seg = Segment(string=i, start=t0, base=tuning[i], held=held, picks=[(0, note.vel, "pick")],
                          hand=0.0 if is_open else 1.0)
            current[i] = seg
            segs.append(seg)
            if note.art == "fall":  # the slide leaves the note downward as it ends
                fall_at = t0 + int(0.65 * held)
                position.move(fall_at, x - float(rng.uniform(3.0, 6.0)), int(0.35 * held))
                where = x
        previous = chosen[-1] if len(chosen) == 1 else previous
        after = int(round(groups[k + 1][0].start * sr)) if k + 1 < len(groups) else t0 + int(dur * sr)
        hold = min(after, t0 + int(dur * sr))
        wide = any(n.art == "vibrato" for n in group)
        if stopped and (hold - t0 > 0.6 * sr or wide):
            depth = (6.0 + 10.0 * ornament) * (2.2 if wide else 1.0)
            vib.add(t0 + int(0.2 * sr), hold, d["vibrato"] * rng.uniform(0.95, 1.05), depth)
    return segs, position, vib


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


def _prepare(notes, sr: int, length: int) -> list[Note]:
    last = length / sr
    return sorted((n for n in notes if 0.0 <= n.start < last and n.dur > 0), key=lambda n: (n.start, n.pitch))


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A part's dry stem, (length, 2): the steel's through its amp, the slide's through its body."""
    s = dict(settings or {})
    if name == "slide":
        return slide(notes, sr, length, rng, make, s)
    return steel(notes, sr, length, rng, make, s)
