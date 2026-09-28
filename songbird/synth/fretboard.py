"""Strings under a hand, for the electric instruments: which string plays each note, how the hand moves its
pitch, and what a magnetic pickup hears of it.

A helper for electric.py and steel.py; it plays no notes of its own.

A note is played on one string, and a string plays one note at a time: a new
note on a ringing string stops it (the finger lifts), unless the hand moves
the pitch without picking (a hammer-on, a pull-off, a slide, a bar's glide),
in which case the same vibration carries on at the new length. Each run of a
string's sound is a Segment: its picks, its pitch track (the fretted length's
and the tension's parts kept apart, since they move the pickup's comb
differently), and where the finger lands.

The string is a loop whose delay may move every sample (stringloop.py's cubic
Lagrange read, and its exact tuning), in two planes a fraction of a cent
apart: the pick drives the plane along the fingerboard hardest, the pickup
hears the one toward it best, so a note blooms and beats as the two drift in
and out of phase. A real string loses its partials at a rate set by their
frequency, not by the note (sigma = b1 + b3 f^2: air and the string's own
internal friction), so each note's loss filter is designed for it: the
one-zero of pluck.py and stringloop.py where that is enough, with a one-pole
low-pass after it where it isn't (a bass string's zing is gone in a fifth of a
second, which a one-zero at 41 Hz cannot do). A string plucked wide is tauter
while it swings, so a hard pluck starts a few cents sharp (a bass's 10 to 20)
and settles as it rings down (glide()). A steel string is stiff, so its
partials run sharp of the harmonic series, the more for a thick core or a
short fretted length: first-order allpasses in the loop stretch them
(dispersion(), after Rauhala and Välimäki's tunable dispersion filters).

The pickup hears the string's velocity at its distance d from the bridge:
what is running toward the bridge minus what is coming back from it, 2d/c
later (c the string's wave speed). On a fretted string c is the open string's,
so the comb's delay is d / (L f_open) whatever the fret: its notch sits at the
harmonic L_fretted / d, which falls as the hand goes up the neck. A bend
raises c, shortening the delay with the period (the notch keeps its
harmonic); a slide or a bar changes only the length (the notch keeps its
frequency). For a string whose length never changes in a segment the comb is
applied to the pluck (the loop is linear, so this is exact and cheap);
otherwise to the sound.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from itertools import combinations

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from ..score import Note
from ..theory import midi_to_hz
from . import pluck, stringloop
from .iir import butter

LEGATO = ("hammer", "pull")
CONTROL = 32  # samples between the loop delay's exact values (linear between)


# --- the strings -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Strings:
    """An instrument's strings and the pickup under them."""

    open: tuple[float, ...]  # each open string's pitch (MIDI), lowest first
    comb: tuple[tuple[float, float], ...]  # the pickup's sensing points: (distance from the bridge / scale, weight)
    offsets: tuple[float, ...] = ()  # cents each string sits off (the maker's and the weather's)
    gains: tuple[float, ...] = ()  # how loud the pickup hears each string (its pole pieces)
    damping: float = 8e-6  # dB/s per Hz^2: how much faster a partial dies for its frequency (b3 f^2)
    t60: float = 7.0  # s: the fundamental's decay at 220 Hz in the plane the pickup hears best
    along: float = 1.3  # the other plane's T60 against it
    heard: float = 0.4  # how much of the other plane the pickup hears
    driven: float = 0.5  # how much of the pick goes into the plane the pickup hears best
    pick: float = 0.15  # where the pick meets the open string, as a fraction of its length from the bridge
    hardness: float = 0.8  # 0 a fleshy fingertip, 1 a sharp pick
    click: float = 0.3  # the pick's own click, as the pickup hears it
    touch: float = 0.0  # the finger's noise as it lands
    frets: int = 22
    kinds: tuple = ()  # (kind, (pick point factor, hardness factor, level, click)) overriding KINDS
    glide: float = 0.0  # cents a pluck at full velocity starts sharp by, its swing stretching the string
    glide_time: float = 0.1  # s: how fast that settles
    stiffness: tuple[float, ...] = ()  # each open string's inharmonicity B (partial k at k f0 sqrt(1 + B k^2))
    stiff_sections: int = 2  # allpasses in each loop to stretch its partials so

    def hz(self, string: int) -> float:
        cents = self.offsets[string] if self.offsets else 0.0
        return midi_to_hz(self.open[string] + cents / 100.0)


# how each kind of touch excites a string: (pick point factor, hardness factor, level, click)
KINDS = {
    "pick": (1.0, 1.0, 1.0, 1.0),
    "up": (1.0, 1.0, 0.85, 0.8),
    "finger": (1.1, 0.35, 0.9, 0.0),
    "hammer": (0.5, 0.25, 0.35, 0.0),  # the finger's blow at the fret, into a string that may be still
    "pull": (0.3, 0.45, 0.55, 0.0),  # the finger plucks the string as it lets go, right by the fret
}


@dataclass
class Segment:
    """One run of a string's sound, from its first pick (or touch) until the finger stops it."""

    string: int
    start: int  # sample
    base: float  # MIDI: the pitch the tracks are relative to
    held: int  # samples from the start until the finger lands
    picks: list = field(default_factory=list)  # (sample from the start, velocity, kind)
    frets: list = field(default_factory=list)  # (sample from the start, cents, samples to get there): the length's moves
    bends: list = field(default_factory=list)  # (sample from the start, cents, samples to get there): the tension's
    vibrato: list = field(default_factory=list)  # (sample from the start, depth cents, Hz, samples, up only)
    mute: float = 0.0  # 0 open; toward 1 a palm resting on it
    release: float = 0.08  # s: how fast the stop kills it
    end: int = 0  # samples of sound in all (held plus the stop's tail)
    hand: float = 0.0  # the fret of its first note
    bar: np.ndarray | None = None  # a whole track of the length's cents (a steel's bar), instead of frets
    tension: np.ndarray | None = None  # a whole track of the tension's cents (a steel's pedals), with bends added
    decay: float = 1.0  # its ring against the string's (a neck's dead spot drinks some notes' energy)

    def moves(self) -> bool:
        return bool(self.frets) or self.bar is not None


def _steps(n: int, moves: list, start_value: float = 0.0) -> np.ndarray:
    """A track of n samples moving to each (at, value, over) in turn, each move a smooth raised cosine."""
    track = np.full(n, start_value, dtype=np.float64)
    value = start_value
    for at, target, over in sorted(moves, key=lambda m: m[0]):
        if at >= n:
            break
        over = max(1, int(over))
        k = min(over, n - at)
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(1, k + 1) / over)
        track[at: at + k] = value + (target - value) * ramp
        track[at + k:] = target
        value = target
    return track


def _fit(track: np.ndarray, n: int) -> np.ndarray:
    return track[:n] if len(track) >= n else np.pad(track, (0, n - len(track)), mode="edge")


def tracks(seg: Segment, sr: int) -> tuple[np.ndarray | None, np.ndarray | None]:
    """The segment's length (cents from base) and tension (cents of bend, pedal and vibrato) tracks, or None
    where nothing moves."""
    n = seg.end
    length = None
    if seg.bar is not None:
        length = _fit(seg.bar, n)
    elif seg.frets:
        length = _steps(n, seg.frets)
    tension = None
    if seg.bends or seg.vibrato or seg.tension is not None:
        tension = _steps(n, seg.bends) if seg.bends else np.zeros(n)
        if seg.tension is not None:
            tension = tension + _fit(seg.tension, n)
        for at, depth, hz, lasts, up in seg.vibrato:
            if at >= n:
                continue
            k = min(n - at, lasts)
            t = np.arange(k) / sr
            grow = np.clip(t / 0.35, 0.0, 1.0) ** 1.5  # a vibrato grows in over a third of a second
            wave = 0.5 - 0.5 * np.cos(2.0 * np.pi * hz * t) if up else np.sin(2.0 * np.pi * hz * t)
            tension[at: at + k] += depth * grow * wave
    return length, tension


# --- the loop -------------------------------------------------------------------------------------


def loss_filter(f0: float, sr: int, damping: float, ref: float = 2000.0) -> tuple[float, float]:
    """The loop filter (one-zero loss a, then one-pole p) that makes the partial at `ref` Hz lose
    damping * ref^2 dB a second more than the fundamental, whatever the note: a one-zero alone while it can
    (a <= 0.5), with the one-pole taking the rest."""
    trips = f0
    need_db = damping * ref**2 / max(trips, 1.0)  # dB per trip round the loop at ref
    w = 2.0 * np.pi * min(ref, 0.4 * sr) / sr
    c = np.cos(w)
    need = (1.0 - 10.0 ** (-need_db / 10.0)) / (2.0 * (1.0 - c))  # a (1 - a) for a one-zero alone
    if need <= 0.24:
        return float((1.0 - np.sqrt(1.0 - 4.0 * need)) / 2.0), 0.0
    rest_db = need_db + 10.0 * np.log10((1.0 + c) / 2.0)  # a = 0.5 loses (1 + cos w) / 2 of the power
    r = 10.0 ** (-max(rest_db, 0.0) / 10.0)
    b = 1.0 - r * c
    p = (b - np.sqrt(max(b * b - (1.0 - r) ** 2, 0.0))) / max(1.0 - r, 1e-12)
    return 0.5, float(min(p, 0.95))


def _filter_delay(omega: np.ndarray, loss: float, pole: float, ad: float = 0.0, sections: int = 0) -> np.ndarray:
    """Phase delay (samples) of the loop filter at omega: the one-zero, the one-pole and the stiffness's
    allpasses."""
    zero = np.arctan2(loss * np.sin(omega), (1.0 - loss) + loss * np.cos(omega)) / omega
    one = np.arctan2(pole * np.sin(omega), 1.0 - pole * np.cos(omega)) / omega
    if sections:
        one = one + sections * _allpass_delay(omega, ad)
    return zero + one


def _allpass_delay(omega, a):
    """Phase delay (samples) of the first-order allpass (a + 1/z) / (1 + a/z)."""
    return 2.0 * np.arctan((1.0 - a) / (1.0 + a) * np.tan(omega / 2.0)) / omega


@lru_cache(maxsize=4096)
def dispersion(f0: float, b: float, sections: int, sr: int) -> float:
    """The coefficient of `sections` first-order allpasses in the loop that stretch a string's partials as
    its stiffness does (f_k = k f0 sqrt(1 + b k^2)): matched at the partial nearest 900 Hz (at most the
    10th), where a bass's growl and a wound string's shimmer are; those below come out within a fifth of
    the stiff string's stretch, those above short of it. 0 where there is nothing to stretch."""
    if b <= 0.0 or sections <= 0:
        return 0.0
    k = max(2, int(round(min(10.0, 900.0 / f0))))
    w1 = 2.0 * np.pi * f0 / sr
    wk = 2.0 * np.pi * k * f0 * np.sqrt(1.0 + b * k * k) / sr
    need = sr / f0 - 2.0 * np.pi * k / wk  # the loop's delay must be this much shorter at partial k
    lo, hi = -0.999, 0.0
    if sections * (_allpass_delay(w1, lo) - _allpass_delay(wk, lo)) < need:
        return lo
    for _ in range(60):  # bisection: the drop in delay grows as a goes toward -1
        mid = 0.5 * (lo + hi)
        if sections * (_allpass_delay(w1, mid) - _allpass_delay(wk, mid)) > need:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def read_delay(period: np.ndarray, loss: float, pole: float, ad: float = 0.0, sections: int = 0) -> np.ndarray:
    """The read delay that makes the whole loop (read, one-zero, one-pole and any stiffness allpasses) one
    `period` long at the fundamental (stringloop.read_delay, with the others' phase too)."""
    period = np.asarray(period, dtype=np.float64)
    omega = 2.0 * np.pi / period
    filt = _filter_delay(omega, loss, pole, ad, sections)
    delay = period - filt
    for _ in range(3):
        delay = delay + (period - filt - stringloop._interp_phase_delay(delay, omega))
    return delay


def filter_gain(omega: np.ndarray, loss: float, pole: float) -> np.ndarray:
    """|H| of the loop filter at omega: what it takes from the fundamental each trip (the gain makes up)."""
    zero = np.sqrt(1.0 - 2.0 * loss * (1.0 - loss) * (1.0 - np.cos(omega)))
    one = (1.0 - pole) / np.sqrt(1.0 - 2.0 * pole * np.cos(omega) + pole * pole)
    return zero * one


@njit(cache=True)
def _two_planes(xa, xb, da, db, ga, gb, loss, pole, size, heard, ad, sections):
    """Two string planes at once: y[t] = x[t] + g[t] * allpasses(lowpass(onezero(read(y, t - d[t])))), the
    read cubic Lagrange (as stringloop._run's), `sections` first-order allpasses of coefficient ad for the
    string's stiffness; returns the first plane plus `heard` times the second."""
    n = xa.shape[0]
    mask = size - 1
    ba = np.zeros(size)
    bb = np.zeros(size)
    out = np.zeros(n)
    xa1 = np.zeros(max(sections, 1))
    ya1 = np.zeros(max(sections, 1))
    xb1 = np.zeros(max(sections, 1))
    yb1 = np.zeros(max(sections, 1))
    pa = 0.0
    pb = 0.0
    la = 0.0
    lb = 0.0
    for t in range(n):
        # plane a
        pos = t - da[t]
        i = int(np.floor(pos))
        f = pos - i
        c0 = -f * (f - 1.0) * (f - 2.0) / 6.0
        c1 = (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0
        c2 = -(f + 1.0) * f * (f - 2.0) / 2.0
        c3 = (f + 1.0) * f * (f - 1.0) / 6.0
        r = c0 * ba[(i - 1) & mask] + c1 * ba[i & mask] + c2 * ba[(i + 1) & mask] + c3 * ba[(i + 2) & mask]
        v = (1.0 - loss) * r + loss * pa
        pa = r
        la = (1.0 - pole) * v + pole * la
        w = la
        for s in range(sections):
            o = ad * w + xa1[s] - ad * ya1[s]
            xa1[s] = w
            ya1[s] = o
            w = o
        ya = xa[t] + ga[t] * w
        ba[t & mask] = ya
        # plane b
        pos = t - db[t]
        i = int(np.floor(pos))
        f = pos - i
        c0 = -f * (f - 1.0) * (f - 2.0) / 6.0
        c1 = (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0
        c2 = -(f + 1.0) * f * (f - 2.0) / 2.0
        c3 = (f + 1.0) * f * (f - 1.0) / 6.0
        r = c0 * bb[(i - 1) & mask] + c1 * bb[i & mask] + c2 * bb[(i + 1) & mask] + c3 * bb[(i + 2) & mask]
        v = (1.0 - loss) * r + loss * pb
        pb = r
        lb = (1.0 - pole) * v + pole * lb
        w = lb
        for s in range(sections):
            o = ad * w + xb1[s] - ad * yb1[s]
            xb1[s] = w
            yb1[s] = o
            w = o
        yb = xb[t] + gb[t] * w
        bb[t & mask] = yb
        out[t] = ya + heard * yb
    return out


@lru_cache(maxsize=8192)
def _steady_delay(period: float, loss: float, pole: float, ad: float = 0.0, sections: int = 0) -> float:
    return float(read_delay(np.array([period]), loss, pole, ad, sections)[0])


def _delay_track(freq, n: int, sr: int, loss: float, pole: float, ad: float = 0.0, sections: int = 0) -> np.ndarray:
    """The read delay for each sample of a pitch track (or a steady pitch)."""
    if np.ndim(freq) == 0:
        return np.full(n, _steady_delay(round(sr / float(freq), 9), round(loss, 12), round(pole, 12), ad, sections))
    period = sr / freq
    at = np.unique(np.append(np.arange(0, n, CONTROL), n - 1))
    return np.interp(np.arange(n), at, read_delay(period[at], loss, pole, ad, sections))


@lru_cache(maxsize=64)
def _click_filter(hardness: float, sr: int) -> np.ndarray:
    return butter(2, 1500.0 + 4000.0 * hardness, btype="highpass", fs=sr, output="sos")


def click(sr: int, hardness: float, vel: float, rng: np.random.Generator) -> np.ndarray:
    """The pick or nail leaving the string (pluck._attack's click, its filter kept): a few milliseconds of
    bright noise, longer and brighter for a hard pick."""
    hardness = round(float(hardness), 2)
    n = int((0.002 + 0.006 * hardness) * sr)
    if n < 8:
        return np.zeros(0)
    noise = sosfilt(_click_filter(hardness, sr), rng.standard_normal(n + 64))[64:]
    return noise * np.exp(-np.arange(n) / ((0.0005 + 0.0015 * hardness) * sr)) * 0.1 * hardness**1.5 * vel


@njit(cache=True)
def _combed(y, delays, weights, scale):
    """What the pickup hears: sum_i w_i (y(t) - y(t - d_i scale(t))), read by cubic Lagrange interpolation."""
    n = y.shape[0]
    out = np.zeros(n)
    total = 0.0
    for k in range(weights.shape[0]):
        total += weights[k]
    for t in range(n):
        acc = total * y[t]
        for k in range(delays.shape[0]):
            pos = t - delays[k] * scale[t]
            i = int(np.floor(pos))
            f = pos - i
            c = (-f * (f - 1.0) * (f - 2.0) / 6.0, (f + 1.0) * (f - 1.0) * (f - 2.0) / 2.0,
                 -(f + 1.0) * f * (f - 2.0) / 2.0, (f + 1.0) * f * (f - 1.0) / 6.0)
            r = 0.0
            for j in range(4):
                m = i - 1 + j
                if 0 <= m < n:
                    r += c[j] * y[m]
            acc -= weights[k] * r
        out[t] = acc
    return out


def _comb_pluck(x: np.ndarray, delays: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """The pickup's comb applied to a short excitation (the loop is linear: the same as combing its sound)."""
    pad = int(np.ceil(delays.max())) + 4
    y = np.concatenate([x, np.zeros(pad)])
    return _combed(y, delays, weights, np.ones(len(y)))


def glide(seg: Segment, strings: Strings, kinds: dict, sr: int) -> np.ndarray | None:
    """A plucked string's pitch glide, in cents of tension: stretched further the harder it is plucked, the
    string is tauter while it swings wide, so each pluck starts sharp by strings.glide (vel level)^2 cents
    and settles as its swing dies down (strings.glide_time). The track runs as long as a glide lasts
    (not the segment's whole length); None where there is none to hear."""
    if strings.glide <= 0.0:
        return None
    n = seg.end
    out = None
    tau = strings.glide_time * sr
    for at, vel, kind in seg.picks:
        cents = strings.glide * (vel * kinds.get(kind, kinds["pick"])[2]) ** 2
        if at >= n or cents < 0.3:
            continue
        k = min(n - at, int(6.0 * tau))
        if out is None:
            out = np.zeros(n)
        out[at: at + k] += cents * np.exp(-np.arange(k) / tau)
    if out is None:
        return None
    return out[: int(np.flatnonzero(out)[-1]) + 1]  # as far as it lasts


def sound(seg: Segment, strings: Strings, sr: int, rng: np.random.Generator, *, vel_bright: float = 0.4) -> np.ndarray:
    """What the pickup hears of one segment: `seg.end` samples of the string's velocity at the pickup."""
    n = seg.end
    if n <= 0:
        return np.zeros(0)
    kinds = {**KINDS, **dict(strings.kinds)}
    open_hz = strings.hz(seg.string)
    base_hz = midi_to_hz(seg.base) * open_hz / midi_to_hz(strings.open[seg.string])  # the string's own offset
    length, tension = tracks(seg, sr)
    rise = glide(seg, strings, kinds, sr)
    if rise is not None and (length is not None or tension is not None):  # a moving note: it rides the tension
        tension = np.pad(rise, (0, n - len(rise))) + (tension if tension is not None else 0.0)
        rise = None
    steady = length is None and tension is None
    if steady:
        freq = base_hz
    else:
        cents = (length if length is not None else 0.0) + (tension if tension is not None else 0.0)
        freq = base_hz * 2.0 ** (np.broadcast_to(cents, (n,)) / 1200.0)
    loss, pole = loss_filter(base_hz, sr, strings.damping)
    # a stiff string's partials run sharp, the more so the shorter it is fretted (B grows as 1/L^2)
    b = strings.stiffness[seg.string] * (base_hz / open_hz) ** 2 if strings.stiffness else 0.0
    ad = dispersion(round(base_hz, 6), round(b, 9), strings.stiff_sections, sr)
    sections = strings.stiff_sections if ad != 0.0 else 0
    if sections and sections * _allpass_delay(2.0 * np.pi * base_hz / sr, ad) > 0.5 * sr / base_hz:
        sections = 0  # more stretch than a loop this short can hold: none (no string on these needs it)
    # the comb's delays: 2d/c, the same for any fret of this string; a bend (tension) shortens them
    delays = np.array([b * sr / open_hz for b, _ in strings.comb])
    weights = np.array([w for _, w in strings.comb])
    combed = bool(strings.comb)  # an acoustic instrument has no pickup: its string drives the bridge as it is
    comb_sound = combed and seg.moves()
    # the excitation: each pick one period of bridge force at the pitch of the moment
    x = np.zeros(n + 16)
    clicks = np.zeros(n)
    for at, vel, kind in seg.picks:
        if at >= n or vel <= 0.0:
            continue
        point, hard, level, loud = kinds.get(kind, kinds["pick"])
        f_now = base_hz if steady else float(freq[at])
        where = min(0.45, strings.pick * point * f_now / open_hz)  # the pick is a fixed distance from the bridge
        hardness = min(1.0, strings.hardness * hard * (1.0 - vel_bright + vel_bright * vel))
        e = stringloop.excitation(f_now, sr, rng, pick=where * rng.uniform(0.9, 1.1), hardness=hardness,
                                  vel=vel * level)
        if kind == "up":
            e = -e
        if combed and not comb_sound:
            e = _comb_pluck(e, delays * 2.0 ** (-(tension[at] if tension is not None else 0.0) / 1200.0), weights)
        j = min(n + 16, at + len(e))
        x[at:j] += e[: j - at]
        if loud > 0 and strings.click > 0:
            burst = click(sr, strings.hardness * hard, vel * level, rng) * loud * strings.click
            k = min(n, at + len(burst))
            clicks[at:k] += burst[: k - at]
    x = x[:n]
    # each plane's loop gain: its decay, the palm, the stop when the finger lands; the filter's own loss at
    # the fundamental made up, so the fundamental decays as asked
    period = sr / freq
    held = min(seg.held, n)
    # a palm by the bridge is a soft, lossy load: it takes the highs within a few trips (a strong low-pass in
    # the loop) and the fundamental in a third of a second (the chug); a dead string (mute 1) in 30 ms
    use_loss = min(0.5, loss + 0.35 * seg.mute) if seg.mute > 0 else loss
    use_pole = max(pole, 0.9 * seg.mute)
    make_up = 1.0 / filter_gain(2.0 * np.pi / period, use_loss, use_pole)
    split = rng.uniform(0.15, 0.6)  # cents between the planes
    planes = []
    for t60 in (strings.t60 * seg.decay, strings.t60 * strings.along * seg.decay):
        t = t60 * (220.0 / freq) ** 0.4
        if seg.mute > 0:
            t = 1.0 / (1.0 / t + 1.0 / (0.03 + 7.0 * (1.0 - seg.mute) ** 2))
        g = np.minimum(stringloop.trip(period, sr, t) * make_up, 0.99999)
        g = np.full(n, float(g)) if steady else np.array(g, dtype=np.float64)
        if held < n:
            stop = stringloop.trip(period if steady else period[held:], sr, seg.release)
            g[held:] = stop + (g[held:] - stop) * np.exp(-np.arange(n - held) / (0.004 * sr))
        planes.append(g)
    # the planes a fraction of a cent either side: the loop's own delay moves by the period's change (the
    # filters' phase delays hardly change over a third of a cent)
    delay = _delay_track(freq, n, sr, use_loss, use_pole, ad, sections)
    if rise is not None:  # a steady note's glide: only its loop's length follows (a few cents move nothing else)
        delay[: len(rise)] *= np.exp2(-rise / 1200.0)
    da = delay + period * (2.0 ** (split / 2400.0) - 1.0)
    db = delay + period * (2.0 ** (-split / 2400.0) - 1.0)
    size = 1 << int(np.ceil(np.log2(max(da.max(), db.max()) + 16)))
    out = _two_planes(x * strings.driven, x, da, db, planes[0], planes[1], use_loss, use_pole, size, strings.heard,
                      ad, sections)
    if comb_sound:
        scale = np.ones(n) if tension is None else 2.0 ** (-tension / 1200.0)
        out = _combed(out, delays, weights, scale)
    out += clicks
    if strings.touch > 0 and held < n:
        out += pluck._touch(sr, held, n, base_hz, strings.touch, rng)
    tail = min(n, int(0.004 * sr))
    out[n - tail:] *= np.linspace(1.0, 0.0, tail)
    return out * (strings.gains[seg.string] if strings.gains else 1.0)


def ring_time(strings: Strings, pitch: float, level_db: float = 80.0) -> float:
    """Seconds until a freely ringing string at `pitch` has fallen `level_db`: when to stop computing it."""
    t = strings.t60 * max(strings.along, 1.0) * (220.0 / midi_to_hz(pitch)) ** 0.4
    return t * level_db / 60.0


# --- strums ---------------------------------------------------------------------------------------


def strum(notes: list[Note], rng: np.random.Generator, *, gap: tuple[float, float] = (0.004, 0.007)) -> list[Note]:
    """Notes struck together, spread as a strum: low to high on a down stroke, high to low on an up; the
    harder the stroke, the quicker it crosses the strings. Notes already spread are left alone."""
    out: list[Note] = []
    groups: dict[float, list[Note]] = {}
    for note in notes:
        groups.setdefault(round(note.start, 4), []).append(note)
    for start in sorted(groups):
        group = groups[start]
        if len(group) < 2:
            out.extend(group)
            continue
        up = sum(n.art == "up" for n in group) > len(group) / 2
        order = sorted(group, key=lambda n: n.pitch, reverse=up)
        vel = float(np.mean([n.vel for n in order]))
        step = gap[1] - (gap[1] - gap[0]) * min(max(vel, 0.0), 1.0)
        t = 0.0
        for k, note in enumerate(order):
            if k:
                t += step * rng.uniform(0.75, 1.25)
            out.append(replace(note, start=note.start + t, dur=max(0.001, note.dur - t)))
    return sorted(out, key=lambda n: (n.start, n.pitch))


# --- fretted strings ----------------------------------------------------------------------------------


def _fits(pitch: float, open_: float, frets: int) -> int | None:
    fret = int(round(pitch - open_))
    return fret if 0 <= fret <= frets else None


def place_chord(pitches: list[float], strings: Strings, hand: float) -> list[tuple[int, int]] | None:
    """Strings and frets for notes played together: each on its own string, low notes on low strings, the
    hand stretching at most five frets, near where it is, open strings welcome."""
    k = len(pitches)
    if k > len(strings.open):
        return None
    order = np.argsort(pitches, kind="stable")
    best, best_cost = None, np.inf
    for chosen in combinations(range(len(strings.open)), k):
        frets = []
        for i, s in zip(order, chosen):
            fret = _fits(pitches[i], strings.open[s], strings.frets)
            if fret is None:
                break
            frets.append(fret)
        else:
            fretted = [f for f in frets if f > 0]
            span = (max(fretted) - min(fretted)) if fretted else 0
            if span > 5:
                continue
            centre = np.mean(fretted) if fretted else hand
            cost = 0.4 * abs(centre - hand) + 1.5 * max(0, span - 3) - 0.3 * (k - len(fretted)) \
                + 0.05 * sum(fretted) + 0.2 * (max(chosen) - min(chosen) - k + 1)
            if cost < best_cost:
                best_cost = cost
                best = [(0, 0)] * k
                for i, s, fret in zip(order, chosen, frets):
                    best[i] = (s, fret)
    return best


def place_note(pitch: float, strings: Strings, hand: float, previous: int | None = None, legato: bool = False,
               taken: set | None = None) -> tuple[int, int] | None:
    """A string and fret for a single note: near the hand, on the previous note's string for a legato move."""
    best, best_cost = None, np.inf
    for s, open_ in enumerate(strings.open):
        if taken and s in taken:
            continue
        fret = _fits(pitch, open_, strings.frets)
        if fret is None:
            continue
        cost = abs(fret - hand) if fret > 0 else 1.0 + 0.15 * hand
        if previous is not None and s == previous:
            cost -= 6.0 if legato else 0.5
        cost += 0.08 * fret
        if cost < best_cost:
            best, best_cost = (s, fret), cost
    return best


def in_range(pitch: float, lo: float, hi: float) -> float:
    """A pitch moved by octaves into lo..hi (what a player does with a note the instrument hasn't got)."""
    while pitch < lo - 0.5:
        pitch += 12.0
    while pitch > hi + 0.5:
        pitch -= 12.0
    return pitch


def fret(notes: list[Note], strings: Strings) -> list[tuple[Note, int, int]]:
    """Every note with the string and fret it is played on, chords together, the hand moving as little
    as it can; legato notes stay on the string they move from."""
    lo = min(strings.open)
    hi = max(strings.open) + strings.frets
    out: list[tuple[Note, int, int]] = []
    groups: list[list[Note]] = []
    for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if groups and note.start - groups[-1][0].start < 0.06 and note.art not in LEGATO \
                and len(groups[-1]) < len(strings.open):
            groups[-1].append(note)
        else:
            groups.append([note])
    hand = 2.0
    last: dict[int, float] = {}  # string -> the pitch it last played
    previous = None
    for group in groups:
        pitches = [in_range(n.pitch, lo, hi) for n in group]
        if len(group) == 1:
            legato = group[0].art in LEGATO + ("slide", "bend", "vibrato")
            prev = None
            if legato and previous is not None and _fits(pitches[0], strings.open[previous], strings.frets) is not None \
                    and abs(pitches[0] - last.get(previous, 1e9)) <= 7:
                prev = previous  # the string the previous note sounded on, if the move can be made on it
            spot = place_note(pitches[0], strings, hand, prev, legato=prev is not None)
            spots = [spot] if spot else None
        else:
            spots = place_chord(pitches, strings, hand)
            if spots is None:  # no shape holds them all: each where it fits, strings not shared
                spots, taken = [], set()
                for p in pitches:
                    spot = place_note(p, strings, hand, taken=taken)
                    if spot is None:
                        break
                    spots.append(spot)
                    taken.add(spot[0])
        if not spots:
            continue
        for note, p, (s, f) in zip(group, pitches, spots):
            out.append((replace(note, pitch=p), s, f))
            last[s] = p
        fretted = [f for _, f in spots if f > 0]
        if fretted:
            hand = float(np.mean(fretted))
        if len(spots) == 1:
            previous = spots[0][0]
    return out


def segments(placed: list[tuple[Note, int, int]], strings: Strings, sr: int, rng: np.random.Generator, *,
             ornament: float = 0.5) -> list[Segment]:
    """Each string's notes as segments: a legato note or a re-pick of the same pitch carries on the ringing
    segment; any other note stops it and starts a new one."""
    by_string: dict[int, list[tuple[Note, int]]] = {}
    for note, s, f in placed:
        by_string.setdefault(s, []).append((note, f))
    out: list[Segment] = []
    for s in sorted(by_string):
        current: Segment | None = None
        for note, f in sorted(by_string[s], key=lambda x: x[0].start):
            start = int(round(note.start * sr))
            if current is not None:
                at = start - current.start
                sounding = at < current.held + int(0.03 * sr)
                pitch_now = current.base + (current.frets[-1][1] / 100.0 if current.frets else 0.0)
                if sounding and note.art in LEGATO and current.mute == 0:
                    over = int(0.003 * sr)
                    current.frets.append((at, (note.pitch - current.base) * 100.0, over))
                    current.picks.append((at + over, note.vel, note.art))
                    current.held = at + max(1, int(round(note.dur * sr)))
                    _vibrato(current, note, sr, rng, ornament)
                    continue
                if sounding and abs(note.pitch - pitch_now) < 0.01 and not current.bends \
                        and _mute_of(note) == current.mute and note.art not in ("bend", "slide", "chop"):
                    current.picks.append((at, note.vel, "up" if note.art == "up" else "pick"))
                    current.held = at + max(1, int(round(note.dur * sr)))
                    _vibrato(current, note, sr, rng, ornament)
                    continue
                if at < current.held:  # the finger lifts as the pick comes back to the string
                    current.held = max(1, at - int(0.002 * sr))
                    current.release = 0.015
            current = _new(note, s, f, sr, rng, ornament)
            out.append(current)
    for seg in out:
        seg.end = seg.held + int(max(0.02, 1.4 * seg.release) * sr)
    return out


def _mute_of(note: Note) -> float:
    return {"mute": 0.8, "chop": 1.0, "ghost": 1.0}.get(note.art, 0.0)


def _new(note: Note, s: int, f: int, sr: int, rng: np.random.Generator, ornament: float) -> Segment:
    seg = Segment(string=s, start=int(round(note.start * sr)), base=note.pitch,
                  held=max(1, int(round(note.dur * sr))), hand=float(f))
    kind = "up" if note.art == "up" else "pick"
    seg.mute = _mute_of(note)
    if note.art in LEGATO:  # nothing was ringing on this string: the hammer or the pull sounds it alone
        kind = note.art
    if note.art == "chop":
        seg.held = min(seg.held, int(0.012 * sr))
        seg.release = 0.02
    if note.art == "bend":  # fretted a tone below and pushed up to the note
        over = min(int(rng.uniform(0.1, 0.2) * sr), max(int(0.05 * sr), seg.held // 2))
        seg.bends = [(0, -200.0, 1), (int(rng.uniform(0.0, 0.03) * sr), 0.0, over)]
    if note.art == "slide":  # picked two or three frets below; the finger slides up across the frets
        k = int(rng.integers(2, 4))
        per = min(int(rng.uniform(0.025, 0.04) * sr), max(int(0.01 * sr), seg.held // (2 * k)))
        seg.frets = [(0, -100.0 * k, 1)] + [(int(0.005 * sr) + i * per, -100.0 * (k - 1 - i), int(0.008 * sr))
                                            for i in range(k)]
    seg.picks.append((0, note.vel, kind))
    _vibrato(seg, note, sr, rng, ornament)
    return seg


def _vibrato(seg: Segment, note: Note, sr: int, rng: np.random.Generator, ornament: float) -> None:
    """A finger vibrato on a "vibrato" note long enough for one: bending up and back 5 to 6.5 times a
    second, 8 to 30 cents deep with the ornament (a folk or country player's, not a blues bend's), less on a
    shorter note. A fretted string can only be pushed sharp, so the note sits a little above its pitch."""
    if note.art != "vibrato" or note.dur < 0.25:
        return
    at = int(round(note.start * sr)) - seg.start + int(0.12 * sr)
    depth = (8.0 + 22.0 * ornament) * min(1.0, note.dur / 0.8)
    seg.vibrato.append((at, depth, rng.uniform(5.0, 6.5), int(note.dur * sr) - int(0.12 * sr), True))


def chop_noise(sr: int, rng: np.random.Generator, vel: float) -> np.ndarray:
    """The pick raking strings the hand has deadened: 25 ms of scratch, as the pickup hears the strings shiver."""
    n = int(0.025 * sr)
    noise = sosfilt(butter(2, [900.0, 4500.0], btype="bandpass", fs=sr, output="sos"), rng.standard_normal(n + 64))[64:]
    env = np.exp(-np.arange(n) / (0.006 * sr)) * (1.0 - np.exp(-np.arange(n) / (0.0008 * sr)))
    return noise * env * 0.35 * vel
