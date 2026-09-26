"""Cymbals: bronze plates struck by a stick, rung as modes and a wash (the kit's ride, crash and hi-hats).

A cymbal is a thin bronze plate, domed, with a thick cup (the bell) in the
middle. Struck, it rings in hundreds of modes. A thin plate's modes come
evenly spread in frequency, about one every 19 Hz on an 18-inch crash, 21 on
a 20-inch ride and 26 on a 14-inch hi-hat (from the plate's bending stiffness
and area), placed as a chaotic system's are (never two too close: their
spacings follow Wigner's surmise); below a kilohertz they come in nearly
equal pairs, a plate's two ways of bending with the same shape turned, whose
slow beating is a crash's wobble. A strike excites each mode by how the
plate moves where the stick lands, filtered by how long the stick stays on
the bronze. The plate radiates its high modes better than its low ones (it
is far below its coincidence frequency), so the sound tilts up.

Below about 3.5 kHz the modes ring explicitly (struck.py): the shimmer and
beating the ear can follow. Above, they crowd too densely to tell apart, and
the plate is a reverberator: the wash is a feedback delay network, eight
lines of a few milliseconds whose total length gives it a mode every ten
hertz or so, damped more at the top, driven by two things. The stick's
strike itself, a short burst whose brightness is the contact's; and the
plate's own nonlinearity: struck hard, a cymbal passes energy from its low
modes up into its high ones (the in-plane stretching of a thin shell goes as
the square of its bending), so the wash is fed with the low modes' motion
squared and cubed. That feed grows faster than the strike, so a hard hit
blooms, the top swelling after the strike and dying first, while a soft one
stays dark; and while it feeds the top, the low modes lose their energy
faster than they otherwise would (the cymbal's two-stage decay).

A damping track closes a hi-hat or chokes a crash; a hi-hat's two plates
clap together when the foot closes them (the chick), and rattle against each
other when half open (a stream of collisions).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.signal import bilinear, butter, lfilter, sosfilt

from . import struck


@dataclass(frozen=True)
class Plate:
    """One cymbal: its size and the numbers its sound is made from."""

    size: float  # inches
    lowest: float  # Hz: the lowest mode rung (lower ones barely radiate when struck)
    spacing: float  # Hz between neighbouring modes, on average
    top: float  # Hz: modes rung explicitly up to here; the wash above
    t60: float  # s: how long a mode near 1 kHz rings
    slope: float  # T60 falls as frequency^-slope
    wash_t60: tuple[float, float]  # s: the wash's ring near 3 kHz and near 16 kHz
    lines: tuple[float, float]  # s: the shortest and longest delay line of the wash
    stick: float  # the stick's burst into the wash, against the modes
    bloom: float  # the nonlinear feed's strength: how far a hard hit's energy climbs into the wash
    drain: float  # nepers a second the loud phase takes from the low modes at full force
    correlation: float  # how alike two hits in the same zone are (0..1)
    gain: float = 1.0  # the wash against the modes


RIDE = Plate(size=20.0, lowest=170.0, spacing=21.0, top=3500.0, t60=7.0, slope=0.4, wash_t60=(5.0, 1.8),
             lines=(0.004, 0.021), stick=0.5, bloom=0.5, drain=2.0, correlation=0.75, gain=1.5)
CRASH = Plate(size=18.0, lowest=200.0, spacing=19.0, top=3500.0, t60=4.5, slope=0.4, wash_t60=(3.2, 1.2),
              lines=(0.003, 0.017), stick=0.3, bloom=1.4, drain=5.0, correlation=0.6, gain=2.0)
HAT = Plate(size=14.0, lowest=300.0, spacing=26.0, top=3000.0, t60=2.8, slope=0.45, wash_t60=(2.0, 0.8),
            lines=(0.0015, 0.009), stick=0.9, bloom=0.4, drain=2.0, correlation=0.7, gain=1.4)

WASH = 12.0  # the wash's scale against the modes, for a plate with gain 1

# Where a stick lands: (modes' level, wash's level, nonlinear feed, bell partials' level, tick)
ZONES = {
    "bow": (1.0, 1.0, 1.0, 0.1, 1.0),
    "bell": (0.2, 0.4, 0.6, 1.0, 1.3),
    "edge": (1.4, 1.3, 1.6, 0.05, 0.5),  # the stick's shoulder on the edge: a crash's big wash
    "chick": (1.2, 0.5, 0.3, 0.0, 0.0),  # a hi-hat's plates clapping together: more body than sizzle
    "sizzle": (0.35, 0.8, 0.0, 0.0, 0.0),  # half-open plates rattling against each other
}
# What strikes it: (contact seconds at full force, extra contact at pianissimo, tick, stick burst)
IMPLEMENTS = {
    "stick": (0.00012, 0.0005, 1.0, 1.0),
    "rod": (0.0002, 0.0006, 0.6, 0.8),
    "brush": (0.0012, 0.002, 0.12, 0.35),
    "mallet": (0.003, 0.004, 0.0, 0.15),
}


@dataclass
class Hit:
    time: float  # s
    vel: float  # 0..1
    zone: str = "bow"
    implement: str = "stick"


def _spacings(rng: np.random.Generator, count: int) -> np.ndarray:
    """Spacings between neighbouring modes of a chaotic plate, mean 1: Wigner's surmise, p(s) = (pi s/2) exp(-pi s^2/4)."""
    return np.sqrt(-4.0 / np.pi * np.log(1.0 - rng.uniform(0.0, 1.0, count)))


@dataclass
class Cymbal:
    """A cymbal as its maker hammered it: modes, their decays and zone patterns, the bell, the wash's lines."""

    freqs: np.ndarray
    t60s: np.ndarray
    patterns: dict
    pair: np.ndarray  # for each mode, the index of its near twin (or -1)
    bell: np.ndarray
    lines: np.ndarray  # samples
    taps: np.ndarray  # (2, 8): each microphone's mix of the lines
    signs: np.ndarray  # (8,): how the feed enters each line
    mix: np.ndarray  # (K + bell, 2): each microphone's mix of the modes


def make_cymbal(plate: Plate, make: np.random.Generator, sr: int, size: float = 1.0) -> Cymbal:
    scale = 1.0 / size
    lo, hi = plate.lowest * scale, plate.top
    count = int((hi - lo) / (plate.spacing * scale)) + 1
    freqs = lo + np.cumsum(_spacings(make, count)) * plate.spacing * scale * make.uniform(0.94, 1.06)
    freqs = freqs[freqs < hi]
    # below a kilohertz the plate's modes come in near pairs, split by its asymmetry by 0.3-3%
    low = np.flatnonzero(freqs < 1000.0)
    twins = freqs[low] * (1.0 + np.exp(make.uniform(np.log(0.003), np.log(0.03), len(low))))
    pair = np.full(len(freqs) + len(low), -1)
    pair[low] = len(freqs) + np.arange(len(low))
    pair[len(freqs):] = low
    freqs = np.concatenate([freqs, twins])
    t60s = plate.t60 * (freqs / 1000.0) ** -plate.slope * np.exp(make.normal(0.0, 0.2, len(freqs)))
    patterns = {zone: make.standard_normal(len(freqs)) for zone in ZONES}
    # the bell: a thick cup whose few partials ring long and clear (a ride's "ding"), 0.8 to 3 kHz
    bell = 800.0 * scale ** 0.5 * make.uniform(0.85, 1.15) * np.array([1.0, 1.72, 2.51, 3.3])
    bell *= np.exp(make.normal(0.0, 0.02, len(bell)))
    lines = np.exp(np.linspace(np.log(plate.lines[0]), np.log(plate.lines[1]), 8)) * scale
    lines = np.round(lines * np.exp(make.uniform(-0.12, 0.12, 8)) * sr).astype(np.int64)
    lines = lines + np.arange(8)  # never two alike
    taps = make.uniform(0.5, 1.0, (2, 8)) * make.choice([-1.0, 1.0], (2, 8))
    signs = make.choice([-1.0, 1.0], 8)
    mix = make.uniform(0.4, 1.0, (len(freqs) + len(bell), 2)) * make.choice([-1.0, 1.0], (len(freqs) + len(bell), 2))
    return Cymbal(freqs, t60s, patterns, pair, bell, lines, taps, signs, mix)


def _contact(freqs: np.ndarray, contact: float) -> np.ndarray:
    """A half-sine force pulse's spectrum envelope: flat below 1/(2 contact), falling 12 dB an octave above."""
    return 1.0 / (1.0 + (2.0 * freqs * contact) ** 2)


def _contact_time(vel: float, implement: str) -> float:
    hard, soft, _, _ = IMPLEMENTS[implement]
    return hard + soft * (1.0 - vel) ** 2


def _one_pole_for(length: int, sr: int, t_lo: float, t_hi: float, f_lo: float = 3000.0, f_hi: float = 16000.0):
    """A delay line's loss: gain g and one-pole lowpass coefficient b so the line falls 60 dB in t_lo seconds
    near f_lo and t_hi near f_hi (Jot's absorbent delay line)."""
    a_lo = 10.0 ** (-3.0 * length / (sr * t_lo))
    a_hi = 10.0 ** (-3.0 * length / (sr * t_hi))
    w_lo, w_hi = 2 * np.pi * f_lo / sr, 2 * np.pi * f_hi / sr

    def mag(b, w):
        return (1.0 - b) / np.sqrt(1.0 - 2.0 * b * np.cos(w) + b * b)

    lo, hi = 0.0, 0.99
    for _ in range(60):  # the pole whose drop from f_lo to f_hi matches the decays' ratio
        b = 0.5 * (lo + hi)
        if mag(b, w_hi) / mag(b, w_lo) > a_hi / a_lo:
            lo = b
        else:
            hi = b
    b = 0.5 * (lo + hi)
    return a_lo / mag(b, w_lo), b


@njit(cache=True)
def _fdn(x, lines, gains, poles, taps, signs, damp, sr, size):
    """Eight absorbent delay lines mixed by a Hadamard matrix, fed x, heard by two microphones' taps.
    damp: extra decay (nepers per second) as a per-sample track, or empty."""
    n = x.shape[0]
    mask = size - 1
    bufs = np.zeros((8, size))
    lp = np.zeros(8)
    v = np.zeros(8)
    g = gains.copy()
    out = np.zeros((n, 2))
    scale = 1.0 / np.sqrt(8.0)
    varying = damp.shape[0] > 0
    for t in range(n):
        if varying and t % 32 == 0:
            for i in range(8):
                g[i] = gains[i] * np.exp(-damp[t] * lines[i] / sr)
        left = 0.0
        right = 0.0
        for i in range(8):
            r = bufs[i, (t - lines[i]) & mask]
            lp[i] = (1.0 - poles[i]) * r + poles[i] * lp[i]
            v[i] = g[i] * lp[i]
            left += taps[0, i] * v[i]
            right += taps[1, i] * v[i]
        out[t, 0] = left
        out[t, 1] = right
        # a fast Walsh-Hadamard transform: every line feeds every other, losslessly
        h = 1
        while h < 8:
            for i in range(0, 8, 2 * h):
                for j in range(i, i + h):
                    a = v[j]
                    b = v[j + h]
                    v[j] = a + b
                    v[j + h] = a - b
            h *= 2
        for i in range(8):
            bufs[i, t & mask] = v[i] * scale + signs[i] * x[t]
    return out


def play(plate: Plate, hits: list[Hit], sr: int, length: int, rng: np.random.Generator, cymbal: Cymbal, *,
         brightness: float = 0.5, wear: float = 0.0, damp: np.ndarray | None = None) -> np.ndarray:
    """A cymbal played: every hit, as stereo (length, 2), each channel a microphone hearing its own mix.
    damp: a per-sample track of extra damping (nepers per second): a hi-hat's pedal, a hand's choke."""
    out = np.zeros((length, 2))
    hits = sorted((h for h in hits if 0.0 <= h.time < length / sr), key=lambda h: h.time)
    if not hits:
        return out
    freqs, bell = cymbal.freqs, cymbal.bell
    k = len(freqs)
    all_freqs = np.concatenate([freqs, bell])
    # a cymbal a player has worn in rings a little shorter, and trashier (its wash up against its tone)
    all_t60 = np.concatenate([cymbal.t60s, 5.0 * (bell / 1000.0) ** -0.3]) * (1.0 - 0.15 * wear)
    radiation = (all_freqs / 1000.0) ** 0.75  # +4.5 dB an octave: a plate far below coincidence
    radiation[k:] = 1.0  # the bell is thick and small: it radiates its few partials alike
    amps = np.zeros((len(hits), len(all_freqs)))
    burst_levels = np.zeros(len(hits))
    for j, h in enumerate(hits):
        modes_level, wash_level, _, bell_level, _ = ZONES[h.zone]
        spectrum = _contact(all_freqs, _contact_time(h.vel, h.implement)) * radiation
        rho = plate.correlation
        pattern = rho * cymbal.patterns[h.zone] + np.sqrt(1.0 - rho * rho) * rng.standard_normal(k)
        # a near pair shares the strike, turned: cos and sin of where the stick lands
        turn = rng.uniform(0.0, np.pi, k)
        pattern = np.where(cymbal.pair >= 0, pattern * np.where(np.arange(k) < cymbal.pair, np.cos(turn), np.sin(turn)),
                           pattern)
        amps[j, :k] = h.vel * modes_level * spectrum[:k] * pattern / np.sqrt(k / 100.0)
        amps[j, k:] = h.vel * bell_level * spectrum[k:] * rng.uniform(0.7, 1.0, len(bell)) * 3.0
        burst_levels[j] = h.vel ** 1.6 * wash_level * IMPLEMENTS[h.implement][3]  # harder is brighter
    times = np.array([h.time for h in hits])
    # the loud phase drains the low modes into the high ones: extra damping that follows the plate's energy
    energy = _energy(times, np.array([h.vel * ZONES[h.zone][2] for h in hits]) ** 2, sr, length, 0.08)
    drain = plate.drain * energy
    total = drain if damp is None else drain + damp
    # three outputs: the two microphones, and the plate's motion as a whole (for the nonlinear feed)
    mix = np.concatenate([cymbal.mix, np.ones((len(all_freqs), 1))], axis=1)
    rung = struck.ring(all_freqs, all_t60, times, amps, sr, length, mix=mix, damp=total)
    out += rung[:, :2]
    feed = _feed(plate, hits, rung[:, 2], burst_levels, sr, length, rng, brightness)
    wash = _wash(plate, cymbal, feed, sr, length, damp, wear, brightness)
    out += wash
    out += _ticks(hits, sr, length, rng, brightness)
    return out


def _energy(times: np.ndarray, levels: np.ndarray, sr: int, length: int, tau: float) -> np.ndarray:
    """A running energy: each hit's level, falling with time constant tau, summed."""
    hop = 64
    frames = length // hop + 2
    impulses = np.zeros(frames)
    np.add.at(impulses, np.clip((times * sr / hop).astype(int), 0, frames - 1), levels)
    env = lfilter([1.0], [1.0, -np.exp(-hop / (tau * sr))], impulses)
    return np.interp(np.arange(length) / hop, np.arange(frames), env)


def _feed(plate: Plate, hits: list[Hit], motion: np.ndarray, burst_levels: np.ndarray, sr: int, length: int,
          rng: np.random.Generator, brightness: float) -> np.ndarray:
    """What drives the wash: each strike's burst (as bright as the contact is short), and the low modes'
    motion squared and cubed (the plate's nonlinearity passing their energy upward)."""
    feed = np.zeros(length)
    for h, level in zip(hits, burst_levels):
        if level <= 0.0:
            continue
        contact = _contact_time(h.vel, h.implement)
        n = max(16, int((4.0 * contact + 0.0006) * sr))
        i = int(round(h.time * sr))
        m = min(n, length - i)
        if m < 8:
            continue
        grain = rng.standard_normal(m) * np.sin(np.pi * (np.arange(m) + 0.5) / n) ** 2
        cut = min(0.45 * sr, 1.0 / (2.0 * contact))  # the contact's corner
        pole = np.exp(-2.0 * np.pi * cut / sr)
        feed[i:i + m] += lfilter([1.0 - pole], [1.0, -pole], grain) * level * plate.stick
    if plate.bloom > 0.0 and np.any(motion):
        reference = _reference(motion, hits, sr)
        u = motion / reference
        feed += plate.bloom * (0.6 * u * u + 0.4 * u * u * u) * 0.5
    # nothing below the modes' reach enters the wash
    sos = butter(2, 2500.0 + 1000.0 * brightness, btype="highpass", fs=sr, output="sos")
    return sosfilt(sos, feed)


def _reference(motion: np.ndarray, hits: list[Hit], sr: int) -> float:
    """The plate's motion a full-force strike would give: the loudest hit's early peak over its velocity."""
    best = 1e-9
    for h in hits:
        i = int(round(h.time * sr))
        seg = motion[i:i + int(0.02 * sr)]
        if len(seg) and h.vel > 0.05:
            best = max(best, float(np.max(np.abs(seg))) / h.vel)
    return best


def _wash(plate: Plate, cymbal: Cymbal, feed: np.ndarray, sr: int, length: int, damp: np.ndarray | None,
          wear: float, brightness: float = 0.5) -> np.ndarray:
    gains, poles = np.zeros(8), np.zeros(8)
    t_lo, t_hi = plate.wash_t60
    for i, line in enumerate(cymbal.lines):
        gains[i], poles[i] = _one_pole_for(int(line), sr, t_lo * (1.0 - 0.2 * wear), t_hi * (1.0 - 0.2 * wear))
    gains = np.minimum(gains, 0.999)  # never a loop gain of one, at any frequency
    size = 1 << int(np.ceil(np.log2(cymbal.lines.max() + 2)))
    track = np.zeros(0) if damp is None else np.ascontiguousarray(damp, dtype=np.float64)
    wet = _fdn(np.ascontiguousarray(feed), cymbal.lines, gains, poles, cymbal.taps, cymbal.signs, track, float(sr), size)
    # the strike's own burst is heard at once, the plate's reverberation after it
    wet += feed[:, None] * np.array([0.5, 0.5])
    wet = sosfilt(butter(2, 2200.0, btype="highpass", fs=sr, output="sos"), wet, axis=0)
    # the plate radiates its top better and better up to about 10 kHz: a shelf rising 6 dB an octave from 3.5 kHz
    upper = 6000.0 + 6000.0 * brightness
    b, a = bilinear([1.0 / (2 * np.pi * 3500.0), 1.0], [1.0 / (2 * np.pi * upper), 1.0], fs=sr)
    return lfilter(b, a, wet, axis=0) * plate.gain * WASH * (1.0 + 0.4 * wear)


def _ticks(hits: list[Hit], sr: int, length: int, rng: np.random.Generator, brightness: float) -> np.ndarray:
    """The stick's own tick on the bronze: a fraction of a millisecond of bright noise."""
    out = np.zeros((length, 2))
    n = int(0.003 * sr)
    sos = butter(2, 2500.0 + 2500.0 * brightness, btype="highpass", fs=sr, output="sos")
    for h in hits:
        level = ZONES[h.zone][4] * IMPLEMENTS[h.implement][2]
        if level <= 0.0:
            continue
        i = int(round(h.time * sr))
        m = min(n, length - i)
        if m < 8:
            continue
        burst = sosfilt(sos, rng.standard_normal(m + 32))[32:] * np.exp(-np.arange(m) / (0.0003 * sr))
        pan = rng.uniform(0.35, 0.65)
        out[i:i + m, 0] += burst * level * h.vel ** 1.5 * 0.2 * np.sqrt(2 * (1 - pan))
        out[i:i + m, 1] += burst * level * h.vel ** 1.5 * 0.2 * np.sqrt(2 * pan)
    return out


def sizzle(times_open: list[tuple[float, float, float]], strikes: list[Hit], sr: int, rng: np.random.Generator,
           damping: float = 30.0) -> list[Hit]:
    """Half-open hi-hat plates rattling: a stream of small collisions, most while the plates move most (after a
    strike), fewer the wider the pedal lets them apart. times_open: (start, end, openness) of each half-open
    stretch. Returns the collisions as hits."""
    out = []
    for start, end, openness in times_open:
        struck_here = [h for h in strikes if start - 0.02 <= h.time < end]
        if not struck_here:
            continue
        step = 0.001
        t = np.arange(start, end, step)
        energy = np.zeros(len(t))
        for h in struck_here:
            after = t >= h.time
            energy[after] += h.vel ** 2 * np.exp(-2.0 * damping * (t[after] - h.time))
        rate = 280.0 * (1.0 - openness) * np.clip(energy, 0.0, 1.5)
        counts = rng.poisson(rate * step)
        for i in np.flatnonzero(counts):
            for _ in range(int(counts[i])):
                out.append(Hit(float(t[i] + rng.uniform(0.0, step)), float(np.sqrt(energy[i]) * rng.exponential(0.3)),
                               "sizzle"))
    return out
