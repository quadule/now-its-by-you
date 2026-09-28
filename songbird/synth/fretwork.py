"""Fretted strings played by hand (the banjo and the mandolin): which string plays each note, and
every string of the instrument ringing through the whole part.

The left hand (assign). A player chooses where each note is played: on an open string if one
sounds it, else on the string whose fret lies nearest where the hand already is; never on a string
another note of the same chord needs, and not on one still ringing a note that should go on ringing
if another string will do. A hammer-on or pull-off stays on the string it moves from. A note out of
the instrument's reach is played an octave in.

The strings (play). Each string is one loop that rings for the whole part, as stringloop.py's: its
length follows the fretted pitch while it rings (a new fret, a slide, a hammer-on, the finger
lifting off in a pull-off), its loop gain follows the hand (ringing; a finger or the pick's edge
resting on it; a chord choked at once), and every pick of it lands on whatever is still ringing. It
vibrates in two planes, as in pluck.py: across the top it drives the bridge and dies fast; along
the top it barely moves the bridge and rings on, quieter, a fraction of a cent away.

A string's tension rises as it swings (the string must stretch to bend), in proportion to its mean
squared slope, which is the power of its force on the bridge. Two things follow. The pitch goes
sharp at a hard pick and relaxes as the swing dies: most of the stretch is in the high harmonics,
which die first, so the glide falls in about a tenth of a second and then lingers with the
fundamental. And the rising and falling tension pulls the bridge down through the angle at which
the strings break over it, at twice the frequency of each harmonic (each harmonic's own swing,
squared); the pull is quadratic, so a loud pick has more of it than a soft one. The glide is worked
out from each pick's harmonics and their decay (below); the pull from the string's first three
harmonics as it rings, each picked out by a resonator that follows the pitch and squared.

The level. Each pick is scaled so that its first tenth of a second, heard through the body and
weighted as BS.1770 weights loudness, is the same for every note at the same velocity, whichever
string and fret, whichever maker's body: worked out from the pick's harmonics, how fast each dies
in the loop, and the body's response at each (early_power), then scaled by the velocity.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import freqz, sosfilt

from . import master
from . import pluck as _pluck
from .iir import butter

CONTROL = 32  # samples between the points of a string's pitch and gain tracks
EARLY = 0.1  # seconds of a pick whose loudness sets its level
GLIDE_HARMONICS = 40  # harmonics a pick's tension glide is worked out from


# --- the left hand ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Board:
    """An instrument's strings: each one's open pitch (MIDI), the highest fret it reaches, whether it
    can be fretted at all (a banjo's short fifth string is played open), and the order a down stroke
    meets them, from the top of the neck to the bottom."""

    opens: tuple[float, ...]
    top: tuple[int, ...]
    fretted: tuple[bool, ...]
    order: tuple[int, ...]
    drone: int | None = None  # a string that plays every note of its own open pitch

    def reach(self) -> tuple[float, float]:
        low = min(self.opens)
        high = max(o + (t if f else 0) for o, t, f in zip(self.opens, self.top, self.fretted))
        return low, high


@dataclass
class Fingered:
    """A note as the hand plays it: on which string, at which fret, and the pitch that sounds (the
    note's own, or an octave in)."""

    note: object
    string: int
    fret: int
    pitch: float
    start: float  # seconds (a chord's strings are spread from here)


def fold(pitch: float, low: float, high: float) -> float:
    """A pitch moved by octaves into [low, high]."""
    while pitch < low - 0.5 and pitch + 12 <= high + 0.5:
        pitch += 12.0
    while pitch > high + 0.5 and pitch - 12 >= low - 0.5:
        pitch -= 12.0
    return pitch


def assign(notes, board: Board, *, legato=("hammer", "pull"), closed=("chop", "mute"), slide=("slide",),
           chord_gap: float = 0.002) -> list[Fingered]:
    """Where each note is played (see the module's docstring), in time order. Notes starting within
    chord_gap seconds of each other are one chord: each on its own string. A note that finds no string
    (a chord with more notes than strings) is left out. A choked note (closed) wants a fretted string,
    since only a finger can let go of one; a slide wants two frets below it to start from."""
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    low, high = board.reach()
    strings = range(len(board.opens))
    ring_end = [-1.0] * len(board.opens)  # when the note on each string is meant to stop
    ring_pitch = [None] * len(board.opens)
    hand = 2.0  # the fret the hand sits near
    out: list[Fingered] = []
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j].start - ordered[i].start <= chord_gap:
            j += 1
        group = ordered[i:j]
        i = j
        start = group[0].start
        options = []
        for note in group:
            p = fold(float(note.pitch), low, high)
            here = []
            for s in strings:
                fret = int(round(p - board.opens[s]))
                if fret < 0 or fret > board.top[s] or (fret > 0 and not board.fretted[s]):
                    continue
                if not board.fretted[s] and abs(p - board.opens[s]) > 0.5:
                    continue
                cost = 0.0 if fret == 0 else 1.0 + 0.25 * max(0.0, abs(fret - hand) - 1.5) + 0.03 * fret
                if ring_end[s] > start + 0.01:  # it would cut a note still meant to ring
                    cost += 0.4 + 0.8 * min(ring_end[s] - start, 2.0) + (0.3 if ring_pitch[s] != p else 0.0)
                if board.drone is not None and s == board.drone:
                    cost -= 2.0  # the drone plays its own note
                if note.art in closed and fret == 0:
                    cost += 6.0
                if note.art in slide and fret < 2:
                    cost += 3.0
                if note.art in legato:
                    held = ring_pitch[s] is not None and ring_end[s] > start - 0.06
                    rising = held and note.art == "hammer" and 0 < p - ring_pitch[s] <= 7
                    falling = held and note.art == "pull" and 0 < ring_pitch[s] - p <= 7
                    cost += -1.5 if (rising or falling) else 1.5
                here.append((cost, s, fret, p))
            options.append(here)
        best = _fingering(options)
        if best is None:
            continue
        frets = []
        for note, opt in zip(group, best):
            if opt is None:
                continue
            _, s, fret, p = opt
            out.append(Fingered(note, s, fret, p, float(note.start)))
            ring_end[s] = float(note.start + note.dur)
            ring_pitch[s] = p
            if fret > 0:
                frets.append(fret)
        if frets:
            hand = float(np.mean(frets))
    return out


def _fingering(options: list[list[tuple]]) -> list | None:
    """The cheapest way of giving a chord's notes distinct strings, each note's options being
    (cost, string, fret, pitch); a note may be left out, at a price, and the fretted notes should
    lie within a hand's span (four frets)."""
    best: list = [None, np.inf]

    def go(k: int, used: frozenset, total: float, picked: list) -> None:
        if k == len(options):
            frets = [o[2] for o in picked if o is not None and o[2] > 0]
            if frets and max(frets) - min(frets) > 4:
                total += 2.0 * (max(frets) - min(frets) - 4)
            if total < best[1] - 1e-9:
                best[0], best[1] = list(picked), total
            return
        for opt in options[k]:
            if opt[1] not in used:
                go(k + 1, used | {opt[1]}, total + opt[0], picked + [opt])
        go(k + 1, used, total + 10.0, picked + [None])

    go(0, frozenset(), 0.0, [])
    return best[0]


def spread(fingered: list[Fingered], board: Board, span, rng: np.random.Generator) -> None:
    """Chords whose notes all start together are strummed: each string a moment after the one above
    it (a down stroke, from the top of the neck) or below it (an up stroke). span(art) is the seconds
    the whole stroke takes. Chords the part already spreads are left as written."""
    by_start: dict[float, list[Fingered]] = {}
    for f in fingered:
        by_start.setdefault(round(f.start, 4), []).append(f)
    rank = {s: k for k, s in enumerate(board.order)}
    for group in by_start.values():
        if len(group) < 2:
            continue
        up = sum(1 for f in group if f.note.art == "up") > len(group) / 2
        group.sort(key=lambda f: rank[f.string], reverse=up)
        total = span(group[0].note.art) * rng.uniform(0.8, 1.2)
        for k, f in enumerate(group[1:], start=1):
            f.start += total * k / (len(group) - 1) * rng.uniform(0.85, 1.15)


# --- what happens to a string -------------------------------------------------------------------


@dataclass
class Stroke:
    """One thing the hands do to one string: a pick (or several, a tremolo), or a hammer-on or pull-off
    of the left hand. Times are in samples."""

    string: int
    at: int  # the first pick, or the finger landing or leaving
    until: int  # where the note's own damping begins (the finger lifts; a chop's choke)
    pitch: float  # MIDI: the pitch the string settles on
    fret: int
    vel: float
    kind: str = "pick"  # "pick": a new excitation; "hammer", "pull": the ringing string changes pitch
    slide: float = 0.0  # semitones under the pitch where it is picked before sliding up
    slide_time: float = 0.08  # seconds the slide takes
    picks: tuple = ((0, 1.0, 1.0),)  # each pick: samples after `at`, velocity factor, direction (+1 down, -1 up)
    beta: float = 0.1  # where the pick meets the string: a fraction of its sounding length from the bridge
    hardness: float = 0.8  # a fingertip (0) to a sharp pick (1)
    cutoff: float = 0.0  # Hz above which the pick softens the string's corner (0: as its hardness says)
    roughness: float = 0.3
    planes: float = 0.3  # how much goes into the plane along the top
    damp: float = 0.08  # T60 of the string once stopped
    gain: float = 1.0  # the articulation's level against a plain pick
    click: tuple = (0.1, 3000.0, 2.5)  # the pick leaving the string: level, high-pass Hz, milliseconds
    scrape: float = 0.0  # a pick dragged across muted strings (a chop's): level
    knock: float = 0.0  # a thump on the body (a chop's hand, a clawhammer nail): level
    twang: float = 1.0  # the tension glide's depth against the instrument's
    touch: float = 0.0  # the finger's small noise when it stops the string
    pair: float = 0.0  # seconds between the pick meeting a course's two strings
    norm: float = 0.0  # set by play(): the factor its picks were scaled by


@dataclass
class Strings:
    """How an instrument's strings ring: the settings play() needs beyond the strokes."""

    loss: tuple[float, ...]  # each string's one-zero loss (brightness)
    decay: float  # an open string's decay at 220 Hz as pluck.py's: the loud plane's T60 is 0.8 of it
    offsets: tuple[float, ...]  # each string's own tuning, cents
    splits: tuple[float, ...]  # cents between each string's two planes
    members: tuple = ((0.0, 1.0),)  # a course's strings: (cents from its pitch, level), or such a tuple a course
    fretted_decay: float = 0.85  # a stopped string rings this much shorter than an open one
    along: float = 2.0  # the quiet plane's T60 against `decay` (pluck.py's: 2)
    glide: float = 12.0  # cents sharp at the start of a pick at velocity 1
    pull: float = 0.0  # the break angle's pull against the string's own force at velocity 1
    touch_band: tuple = (150.0, 2000.0)
    level: float = 1.0  # overall force scale


# --- the string itself ---------------------------------------------------------------------------


@njit(cache=True)
def _string(n, ctrl, delay, gain_a, gain_b, omega, pull, ratio_b, loss, at, first, count, amount, pool, size,
            hp):
    """One string for n samples: the plane across the top (per-trip gain gain_a) and the one along it
    (gain_b, its delay ratio_b of the other's), both fed the picks in pool (pick k enters at sample
    at[k], count[k] samples from pool[first[k]:], the along plane amount[k] of it). delay, gain_a,
    gain_b, omega (the fundamental, radians a sample) and pull (the break angle's gain on the tension)
    are control tracks, a value every ctrl samples, read linearly between. The read is cubic Lagrange,
    the loss one-zero, as stringloop's. Returns the force on the bridge: both planes, plus the tension's
    pull, each of the string's first three harmonics (picked out by resonators a third of the
    fundamental wide that follow the pitch) squared, high-passed by the biquad hp (b0, b1, b2, a1, a2)
    to leave only the swing at twice their frequencies."""
    mask = size - 1
    buf_a = np.zeros(size)
    buf_b = np.zeros(size)
    y = np.zeros(n)
    prev_a = 0.0
    prev_b = 0.0
    s1 = np.zeros(3)
    s2 = np.zeros(3)
    c1 = np.zeros(3)
    live = np.zeros(3)  # a harmonic whose doubled swing would pass Nyquist is left out
    c2 = 0.0
    b0 = 0.0
    x1 = 0.0
    x2 = 0.0
    h1 = 0.0
    h2 = 0.0
    g1 = 0.0
    g2 = 0.0
    n_exc = at.shape[0]
    k = 0
    for t in range(n):
        c = t // ctrl
        o = t - c * ctrl
        frac = o / ctrl
        if o == 0:
            w = omega[c]
            r = np.exp(-0.5 * w / 3.0)  # a resonator a third of the fundamental wide
            c2 = r * r
            b0 = 0.5 * (1.0 - c2)
            for h in range(3):
                c1[h] = 2.0 * r * np.cos((h + 1) * w)
                live[h] = 1.0 if 2.0 * (h + 1) * w < 0.9 * np.pi else 0.0
        d = delay[c] + (delay[c + 1] - delay[c]) * frac
        ga = gain_a[c] + (gain_a[c + 1] - gain_a[c]) * frac
        gb = gain_b[c] + (gain_b[c + 1] - gain_b[c]) * frac
        q = pull[c] + (pull[c + 1] - pull[c]) * frac
        xa = 0.0
        xb = 0.0
        while k < n_exc and at[k] + count[k] <= t:
            k += 1
        j = k
        while j < n_exc and at[j] <= t:
            e = t - at[j]
            if e < count[j]:
                v = pool[first[j] + e]
                xa += v
                xb += v * amount[j]
            j += 1
        # across the top
        pos = t - d
        i = int(np.floor(pos))
        f = pos - i
        ra = (-f * (f - 1.0) * (f - 2.0) / 6.0) * buf_a[(i - 1) & mask] \
            + ((f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0) * buf_a[i & mask] \
            + (-(f + 1.0) * f * (f - 2.0) / 2.0) * buf_a[(i + 1) & mask] \
            + ((f + 1.0) * f * (f - 1.0) / 6.0) * buf_a[(i + 2) & mask]
        va = (1.0 - loss) * ra + loss * prev_a
        prev_a = ra
        oa = xa + ga * va
        buf_a[t & mask] = oa
        # along the top
        pos = t - d * ratio_b
        i = int(np.floor(pos))
        f = pos - i
        rb = (-f * (f - 1.0) * (f - 2.0) / 6.0) * buf_b[(i - 1) & mask] \
            + ((f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0) * buf_b[i & mask] \
            + (-(f + 1.0) * f * (f - 2.0) / 2.0) * buf_b[(i + 1) & mask] \
            + ((f + 1.0) * f * (f - 1.0) / 6.0) * buf_b[(i + 2) & mask]
        vb = (1.0 - loss) * rb + loss * prev_b
        prev_b = rb
        ob = xb + gb * vb
        buf_b[t & mask] = ob
        s = oa + ob
        # the tension's pull through the break angle
        tension = 0.0
        for h in range(3):
            v = b0 * (s - x2) + c1[h] * s1[h] - c2 * s2[h]
            s2[h] = s1[h]
            s1[h] = v
            tension += live[h] * v * v
        x2 = x1
        x1 = s
        hv = hp[0] * tension + hp[1] * h1 + hp[2] * h2 - hp[3] * g1 - hp[4] * g2
        h2 = h1
        h1 = tension
        g2 = g1
        g1 = hv
        y[t] = s + q * hv
    return y


def loop_delay(period: np.ndarray, loss: float) -> np.ndarray:
    """The read delay that makes a loop with the one-zero loss filter exactly `period` samples long at
    its fundamental (the filter's phase delay taken off; the cubic read's own is under 1e-4 samples)."""
    w = 2.0 * np.pi / period
    return period - np.arctan2(loss * np.sin(w), (1.0 - loss) + loss * np.cos(w)) / w


@lru_cache(maxsize=16)
def _highpass(sr: int, hz: float) -> np.ndarray:
    b, a = butter(2, hz, btype="highpass", fs=sr)
    return np.array([b[0], b[1], b[2], a[1], a[2]])


@lru_cache(maxsize=64)
def _band(sr: int, lo: float, hi: float, order: int = 2) -> np.ndarray:
    if hi >= 0.45 * sr:
        return butter(order, lo, btype="highpass", fs=sr, output="sos")
    return butter(order, [lo, hi], btype="bandpass", fs=sr, output="sos")


class _Noise:
    """Band-limited noise for the hands' small sounds: half a second of each band, drawn once a part,
    from which each burst takes its own stretch (peaks about 1)."""

    def __init__(self, sr: int, rng: np.random.Generator):
        self.sr, self.rng, self.banks = sr, rng, {}

    def burst(self, ms: float, lo: float, hi: float, tau_ms: float) -> np.ndarray:
        if (lo, hi) not in self.banks:
            x = sosfilt(_band(self.sr, lo, hi), self.rng.standard_normal(self.sr // 2 + 64))[64:]
            self.banks[(lo, hi)] = x / (3.0 * np.sqrt(np.mean(x**2)) + 1e-12)
        bank = self.banks[(lo, hi)]
        n = min(len(bank) - 1, max(8, int(ms * 1e-3 * self.sr)))
        start = int(self.rng.integers(0, len(bank) - n))
        return bank[start:start + n] * np.exp(-np.arange(n) / (tau_ms * 1e-3 * self.sr))


def _knock(sr: int, ms: float) -> np.ndarray:
    """A thump on the body: a raised-cosine push `ms` long (the body's modes do the rest)."""
    n = max(4, int(ms * 1e-3 * sr))
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n) / n)


# --- the level of a pick -------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _k_power(sr: int, n: int) -> np.ndarray:
    """BS.1770's K-weighting, as power, on the rfft grid of n points."""
    grid = np.fft.rfftfreq(n, 1.0 / sr)
    out = np.ones(len(grid))
    for b, a in master._k_weighting(sr):
        _, h = freqz(b, a, worN=grid, fs=sr)
        out *= np.abs(h) ** 2
    return out


def body_power(ir: np.ndarray, sr: int, extra=None, n: int = 1 << 15, place=None) -> tuple[np.ndarray, np.ndarray]:
    """What a body passes at each frequency, as loudness hears it: the power of its response summed
    over its microphones as the band will place them (place: (position, width), see
    instruments.place; the two microphones hear the upper modes differently, so how much of their
    difference is kept changes the loudness), K-weighted, times `extra` (a further filter's power) if
    given. Returns (frequencies, power) on an rfft grid fine enough to resolve the body's modes."""
    n = max(n, 1 << int(np.ceil(np.log2(len(ir) + 1))))
    if place is not None and ir.ndim == 2:
        from .instruments import place as placed

        ir = placed(ir, *place)
    spectrum = np.abs(np.fft.rfft(ir, n, axis=0)) ** 2
    power = spectrum.sum(axis=1) if spectrum.ndim == 2 else spectrum
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    power = power * _k_power(sr, n)
    if extra is not None:
        power = power * extra(freqs)
    return freqs, power


def dynamics(vel: float) -> float:
    """How far a pick of velocity vel swings the string, against velocity 1: a player's soft notes are
    softer still (the house frame drum's curve, vel * (0.35 + 0.65 vel)): 0.3 to 0.9 is 16 dB."""
    return vel * (0.35 + 0.65 * vel)


def _decays(f0: float, sr: int, loss: float, t60: float, count: int) -> np.ndarray:
    """Each of the first `count` harmonics of a loop at f0: the factor its amplitude falls by in a
    second (the loop gain for t60, and the loss filter's reach at that harmonic)."""
    h = np.arange(1, count + 1)
    w = 2.0 * np.pi * h * f0 / sr
    filt = np.sqrt((1.0 - loss) ** 2 + loss**2 + 2.0 * loss * (1.0 - loss) * np.cos(w))
    return (10.0 ** (-3.0 / (t60 * f0)) * filt) ** f0


def early_power(harmonics: np.ndarray, f0: float, rho: np.ndarray, planes: float, freqs: np.ndarray,
                power: np.ndarray) -> float:
    """The power of a pick's first EARLY seconds through the body: its harmonics' power, each at the body's
    (K-weighted) response and averaged over the time it takes to decay (rho: per-second factors)."""
    count = min(len(harmonics), len(rho))
    at = np.interp(f0 * np.arange(1, count + 1), freqs, power)
    r = np.minimum(rho[:count], 1.0 - 1e-9)
    fall = r ** (2.0 * EARLY)
    mean = (1.0 - fall) / (-2.0 * EARLY * np.log(r))
    return float(np.sum(harmonics[:count] * at * mean) * (1.0 + planes) ** 2)


# --- playing the strings -------------------------------------------------------------------------


def _segments(strokes: list[Stroke], sr: int) -> list[list[Stroke]]:
    """A string's strokes in stretches separated by silence (a stopped string is silent 0.4 s later)."""
    out, current, quiet = [], [], -1
    for s in strokes:
        if current and s.at > quiet:
            out.append(current)
            current = []
        current.append(s)
        quiet = max(quiet, s.until + int(0.4 * sr))
    if current:
        out.append(current)
    return out


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    """A control track whose steps are spread over `width` control points."""
    if width <= 1 or len(values) <= width:
        return values
    padded = np.concatenate([np.full(width, values[0]), values, np.full(width, values[-1])])
    return np.convolve(padded, np.ones(width) / width, mode="same")[width:-width]


def _hz(pitch):
    return 440.0 * 2.0 ** ((np.asarray(pitch, dtype=np.float64) - 69.0) / 12.0)


def play(strokes: list[Stroke], strings: Strings, sr: int, length: int, rng: np.random.Generator,
         freqs: np.ndarray, power: np.ndarray, *, hp_hz: float = 70.0) -> np.ndarray:
    """Every stroke played on its string: the strings' force on the bridge, `length` samples.

    Each note's first pick is scaled (Stroke.norm) so that its early loudness through the body
    (freqs, power: see body_power) is the same for every note at the same velocity, times its
    articulation's gain; a tremolo's later picks keep that scale."""
    force = np.zeros(length)
    strokes = sorted((s for s in strokes if 0 <= s.at < length), key=lambda s: (s.at, s.string))
    if not strokes:
        return force
    hp = _highpass(sr, hp_hz)
    noise = _Noise(sr, rng)
    for string in sorted({s.string for s in strokes}):
        mine = [s for s in strokes if s.string == string]
        for k, s in enumerate(mine):
            nxt = mine[k + 1] if k + 1 < len(mine) else None
            if nxt is not None and nxt.kind != "pick":
                s.until = nxt.at  # a hammer-on or a pull-off keeps the note ringing into the next
            elif nxt is not None:
                s.until = min(s.until, nxt.at)
            s.until = int(min(max(s.until, s.at + 1), length))
        for segment in _segments(mine, sr):
            _segment(segment, strings, string, sr, length, rng, freqs, power, hp, force, noise)
    return force


def _segment(strokes, strings: Strings, string: int, sr: int, length: int, rng, freqs, power, hp, force, noise):
    """One stretch of one string's playing: its tracks, its picks, its loops."""
    a = strokes[0].at
    b = min(length, max(s.until for s in strokes) + int(0.4 * sr))
    n = b - a
    ctrl = CONTROL
    points = n // ctrl + 2
    times = a + np.arange(points) * ctrl

    def at_point(sample: int) -> int:
        return min(points, max(0, (int(sample) - a) // ctrl))

    loss = strings.loss[string]
    offset = strings.offsets[string]
    nexts = [s.at for s in strokes[1:]] + [b]
    move = int(0.012 * sr)  # a finger moving to a new fret
    touch = int(0.003 * sr)  # the pick meeting a string still ringing

    # --- the pitch the fingers set, and where the pick or a moving finger damps the string a moment
    bp_t, bp_p = [a - move - 1], [strokes[0].pitch - strokes[0].slide]
    current = bp_p[0]
    dips = []
    for k, s in enumerate(strokes):
        begin = s.pitch - s.slide
        if s.kind == "pick":
            moved = abs(begin - current) > 1e-6
            if k and strokes[k - 1].until >= s.at - touch:
                dips.append((s.at - (move if moved else touch), s.at))
            if moved:
                bp_t += [s.at - move, s.at - 1]
                bp_p += [current, begin]
            if s.slide > 0.0:
                span = min(s.slide_time * sr, 0.8 * (nexts[k] - s.at))
                for x in np.linspace(0.0, 1.0, 9)[1:]:
                    bp_t.append(s.at + int(span * x))
                    bp_p.append(begin + s.slide * (3.0 * x * x - 2.0 * x**3))
        else:  # a hammer-on or a pull-off: the finger lands or leaves and the string rings on
            bp_t += [s.at, s.at + touch]
            bp_p += [current, begin]
        current = s.pitch
    order = np.argsort(np.array(bp_t), kind="stable")
    pitch = np.interp(times, np.array(bp_t, dtype=np.float64)[order], np.array(bp_p)[order])

    # --- each pick: its excitation, its level, the glide its stretch puts on the pitch
    glide = np.zeros(points)
    pull = np.zeros(points)
    members = strings.members if np.ndim(strings.members[0]) == 1 else strings.members[string]
    course = sum(level**2 for _, level in members)
    member_picks = [[] for _ in members]
    t60_open = strings.decay * 0.8
    for k, s in enumerate(strokes):
        f0 = float(_hz(s.pitch - s.slide + offset / 100.0))
        period = sr / f0
        t60 = t60_open * (220.0 / f0) ** 0.4 * (strings.fretted_decay if s.fret > 0 else 1.0)
        rho = _decays(f0, sr, loss, t60, 4 * GLIDE_HARMONICS)
        norm = None
        for offset_samples, factor, direction in s.picks:
            at = s.at + int(offset_samples)
            if at >= b:
                continue
            vel = float(np.clip(s.vel * factor, 0.0, 1.0))
            if vel <= 0.0:
                continue
            first_met = 0 if direction > 0 else len(members) - 1
            beta = s.beta * rng.uniform(0.92, 1.08)
            harmonics = None
            for m, (cents, level) in enumerate(members):
                exc = _pluck._excitation(period * 2.0 ** (-cents / 1200.0), beta, s.hardness, vel, rng, sr,
                                         roughness=s.roughness, cutoff_hz=s.cutoff or None) / (0.5 * vel)
                if harmonics is None:  # the power of each harmonic
                    harmonics = 2.0 * np.abs(np.fft.rfft(exc)[1:]) ** 2 / len(exc) ** 2
                if norm is None:  # the note's first pick sets its level, the course's other string counted
                    e = early_power(harmonics, f0, rho, s.planes, freqs, power) * course
                    norm = 1.0 / np.sqrt(max(e, 1e-20))
                    s.norm = norm
                lag, lv = 0, level
                if m != first_met:
                    lag = int(round(s.pair * sr * rng.uniform(0.5, 1.5)))
                    lv = level * rng.uniform(0.75, 1.0)
                scale = norm * dynamics(vel) * s.gain * strings.level
                member_picks[m].append((at + lag - a, direction * exc * (scale * lv * 0.5), s.planes))
            scale = norm * dynamics(vel) * s.gain * strings.level
            if s.kind == "pick" and strings.glide > 0.0 and s.twang > 0.0:
                j0 = at_point(at)
                j1 = min(points, at_point(nexts[k]) + 2)
                if j1 > j0:
                    t = np.maximum((times[j0:j1] - at) / sr, 0.0)
                    count = min(GLIDE_HARMONICS, len(harmonics))
                    lam = -np.log(np.minimum(rho[:count], 1.0 - 1e-9))
                    energy = harmonics[:count] @ np.exp(-2.0 * np.outer(lam, t))
                    depth = strings.glide * s.twang * dynamics(vel) ** 2
                    glide[j0:j1] = np.maximum(glide[j0:j1], depth * energy / max(energy[0], 1e-20))
            _extras(s, at, scale, noise, strings, force, length)
        if norm is not None:
            pull[at_point(s.at):] = strings.pull / norm

    # --- the loop gain: ringing, or stopped by a finger (a chop's choke) or a moment's touch
    f_track = _hz(pitch + offset / 100.0)
    t60 = np.full(points, strokes[0].damp)
    ring = np.zeros(points, dtype=bool)
    for k, s in enumerate(strokes):
        j0, j1, j2 = at_point(s.at), at_point(s.until), at_point(nexts[k])
        factor = strings.fretted_decay if s.fret > 0 else 1.0
        t60[j0:j1] = t60_open * (220.0 / f_track[j0:j1]) ** 0.4 * factor
        ring[j0:j1] = True
        t60[j1:j2] = s.damp
        ring[j1:j2] = False
    for t0, t1 in dips:
        j0, j1 = at_point(t0), at_point(t1)
        t60[j0:j1] = np.minimum(t60[j0:j1], 0.03)
        ring[j0:j1] = False
    t60_b = np.where(ring, t60 * strings.along / 0.8, t60)
    width = max(1, int(round(0.003 * sr / ctrl)))

    split = strings.splits[string]
    for m, (cents, _) in enumerate(members):
        picks = sorted(member_picks[m], key=lambda p: p[0])
        if not picks:
            continue
        # the two planes sit either side of the pitch, `split` cents apart
        period = sr / _hz(pitch + (offset + cents + glide - split / 2.0) / 100.0)
        delay = loop_delay(period, loss)
        gain_a = _smooth(10.0 ** (-3.0 * period / (sr * t60)), width)
        gain_b = _smooth(10.0 ** (-3.0 * period / (sr * t60_b)), width)
        omega = 2.0 * np.pi / period
        at = np.array([p[0] for p in picks], dtype=np.int64)
        count = np.array([len(p[1]) for p in picks], dtype=np.int64)
        first = np.concatenate([[0], np.cumsum(count)[:-1]]).astype(np.int64)
        pool = np.ascontiguousarray(np.concatenate([p[1] for p in picks]), dtype=np.float64)
        amount = np.array([p[2] for p in picks], dtype=np.float64)
        size = 1 << int(np.ceil(np.log2(delay.max() + 16)))
        y = _string(n, ctrl, np.ascontiguousarray(delay), np.ascontiguousarray(gain_a),
                    np.ascontiguousarray(gain_b), np.ascontiguousarray(omega), np.ascontiguousarray(pull),
                    2.0 ** (-split / 1200.0), float(loss), at, first, count, amount, pool, size, hp)
        force[a:b] += y


def _extras(s: Stroke, at: int, scale: float, noise: _Noise, strings: Strings, force: np.ndarray, length: int):
    """The sounds of the hands themselves, at the note's own level: the pick leaving the string, a
    chop's scrape and knock, a finger's touch as it stops the string."""
    def add(burst: np.ndarray, where: int) -> None:
        j = min(length, where + len(burst))
        if where < j:
            force[where:j] += burst[: j - where]

    level, hp_hz, ms = s.click
    if level > 0.0:
        add(noise.burst(ms * 3.0, hp_hz, 0.47 * noise.sr, ms / 3.0) * (level * 0.5 * scale), at)
    if s.scrape > 0.0:
        add(noise.burst(25.0, 700.0, 5000.0, 5.0) * (s.scrape * 0.5 * scale), at)
    if s.knock > 0.0:
        add(_knock(noise.sr, 2.0) * (s.knock * 0.5 * scale), at)
    if s.touch > 0.0 and s.until < length and at == s.at:
        lo, hi = strings.touch_band
        burst = noise.burst(30.0, lo, hi, 12.0)
        add(burst * np.sin(np.pi * np.arange(len(burst)) / len(burst)) * (s.touch * 0.05 * scale), s.until)
