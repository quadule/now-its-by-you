"""An acoustic drum kit, played with sticks, brushes, rods or mallets.

The drums are membranes rung as modes (struck.py). A drum has two heads, the
batter the stick strikes and a resonant head underneath, joined by the air in
the shell: the air pushes their round modes apart (a snare's lowest pair sits
near 180 and 330 Hz though neither head alone is tuned there) and barely
touches the others, which ring at each head's own tuning a little apart and
beat as they die, which is what makes a tom sing. The air also loads the
heads, so their modes crowd closer than an ideal membrane's (1 : 1.52 : 1.98
: 2.11 rather than 1 : 1.59 : 2.14 : 2.30). Where the stick lands decides
which modes speak (the centre the round ones, a boom; off-centre the ones
with nodal diameters, a drier ring), and how long it stays on the head
filters off the highest (a hard hit is shorter, so brighter: about an octave
of difference between a ghost note and a rim shot). A hard hit stretches the
head, so every mode starts sharp and falls back as the ring dies (the tension
follows the energy, so a roll bends further). The stick's click and the
skin's slap are short noises of their own.

    kick    a 22-inch bass drum and its felt (or plastic) beater, a pillow inside, a port in the front head
    snare   a 14-inch snare. Its wires are strands pressed against the snare-side head: while the head
            moves gently they ride on it; when it pulls away faster than their tension can follow, they
            fly free and slap back into it, and every collision is a grain of rattle, so the wires buzz
            at the head's own rate, a ghost note gets a thin buzz or none, and the kick and toms set
            them going too (the room's air pushing that head), as on any kit. A rim shot hits the head
            and the hoop at once (louder, the hoop ringing); a cross-stick is the stick's own knock on
            the hoop with its butt on the head.
    toms    three: a high and a middle rack tom and a floor tom
    hats, ride and crash   cymbals.py: modes and a reverberant wash; the hi-hat pedal is a damping track

Brushes: a tap is a cloud of bristle strikes spread over a few milliseconds
(softer, smeared, the wires answering); a sweep is the bristles catching and
slipping on the coated head, a stream of tiny catches, more and harder the
faster the brush moves round its arc. Rods are a bundle of dowels, a few
strikes a fraction of a millisecond apart. Mallets stay long on the head:
dark, no click; a roll with them swells.

The kit is heard from the drummer's seat: hi-hat on the left, ride and floor
tom on the right, kick and snare in the middle. Each piece is levelled by the
loudness of its first tenth of a second at a medium stroke, so a machine's
own tunings change its kit's colour but not its balance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
from numba import njit
from scipy.signal import lfilter, sosfilt
from scipy.special import jn_zeros, jv

from . import cymbals, struck
from .cymbals import Hit
from .iir import butter
from .master import _k_weighting

# --- the drums -----------------------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _membrane(top: float) -> tuple[tuple[int, int, float], ...]:
    """(m, n, Bessel zero j_mn) of a membrane's modes up to j = top x 2.405, lowest first."""
    found = []
    for m in range(0, 30):
        for n, j in enumerate(jn_zeros(m, 12), start=1):
            if j < top * 2.404826:
                found.append((m, n, float(j)))
    return tuple(sorted(found, key=lambda x: x[2]))


def _ratio(m: int, j: float) -> float:
    """A loaded head's mode against its lowest: the air's mass crowds the modes with nodal diameters closer."""
    return j / 2.404826 if m == 0 else (j / 2.404826) ** 0.9


@dataclass(frozen=True)
class Drum:
    f0: float  # Hz: the batter's lowest mode, before the air couples it to the other head
    reso0: float  # the resonant head's round modes against the batter's
    reso: float  # its other modes against the batter's
    coupling: float  # how strongly the air joins the two heads' lowest modes (0..1)
    t60: float  # s: the lowest mode's ring
    slope: float  # higher modes ring shorter: T60 ~ (f / f0)^-slope
    top: float  # the batter's modes up to this multiple of f0; the skin's slap above
    radius: float  # where the stick usually lands (0 centre, 1 rim)
    contact: float  # s the stick (or beater) stays on the head at full force
    glide: float  # how far a full-force hit bends the pitch up (a fraction)
    click: float  # the stick's or beater's click, against the head
    click_band: tuple[float, float]  # Hz
    slap: float  # the skin's slap: a noise band above the modes
    shell: tuple[tuple[float, float, float], ...] = ()  # the shell's own modes: (Hz, T60 s, level)


KICK = Drum(f0=68.0, reso0=1.12, reso=1.08, coupling=0.8, t60=0.45, slope=0.5, top=16.0, radius=0.12,
            contact=0.004, glide=0.1, click=0.6, click_band=(700.0, 4500.0), slap=0.12,
            shell=((190.0, 0.12, 0.05), (410.0, 0.08, 0.04)))
SNARE = Drum(f0=205.0, reso0=1.54, reso=1.2, coupling=0.75, t60=0.3, slope=0.45, top=12.0, radius=0.3,
             contact=0.0006, glide=0.02, click=0.25, click_band=(1800.0, 8000.0), slap=0.2,
             shell=((520.0, 0.07, 0.05), (910.0, 0.05, 0.04)))
TOM = Drum(f0=130.0, reso0=1.06, reso=1.06, coupling=0.6, t60=0.9, slope=0.5, top=9.0, radius=0.32,
           contact=0.0012, glide=0.09, click=1.0, click_band=(1500.0, 6000.0), slap=0.15,
           shell=((330.0, 0.1, 0.04), (700.0, 0.07, 0.03)))
CLICK = 1.0  # a click's level against the strike's own strength (the sum of what it gives every mode)

# The hoop of a snare: a ring's bending modes (ratios n(n^2-1)/sqrt(n^2+1) for n = 2..6), metal, short.
HOOP = 560.0 * np.array([1.0, 2.83, 5.43, 8.78, 12.9])
# A hickory stick, free at both ends: a bar's modes (1, 2.76, 5.40, 8.93), damped by the hand holding it.
STICK = 380.0 * np.array([1.0, 2.756, 5.404, 8.933])


@dataclass
class Stroke:
    time: float
    vel: float
    implement: str = "stick"
    kind: str = ""  # "", "rim" (head and hoop at once), "cross" (the stick's butt on the head, knocked on the
    # hoop), "dead" (the beater left buried in the head, damping it)
    knock: float = 0.0  # a cross-stick's force on the hoop


def _modes(drum: Drum, f0: float, reso0: float, reso: float, coupling: float):
    """The drum's modes: the batter's to `top`, then the resonant head's (driven through the air: its round
    modes most). The two heads' lowest modes are pushed apart by the air between them, and every other mode
    sits against the lower of that pair, the drum's sounding fundamental (a snare's batter (1,1) near 1.5
    times it: Rossing et al.'s 278 against 182 Hz). Returns frequencies, each mode's (m, n, j), whether it is
    the batter's, and its share of a strike."""
    fb, fr = f0, f0 * reso0
    k = 0.5 * coupling
    mid, half = (fb * fb + fr * fr) / 2.0, np.sqrt(((fb * fb - fr * fr) / 2.0) ** 2 + (k * fb * fr) ** 2)
    low, high = np.sqrt(mid - half), np.sqrt(mid + half)
    freqs, which, batter, share = [], [], [], []
    for m, n, j in _membrane(drum.top):
        freqs.append(low * _ratio(m, j))
        which.append((m, n, j))
        batter.append(True)
        share.append(1.0)
    first = len(freqs)
    for m, n, j in _membrane(min(drum.top / max(reso0, reso), 6.0)):
        freqs.append(high if (m, n) == (0, 1) else low * (reso0 if m == 0 else reso) * _ratio(m, j))
        which.append((m, n, j))
        batter.append(False)
        share.append((0.5 if m == 0 else 0.15) / n)
    share[first] = 0.6  # the upper of the pair: both heads moving against each other, squeezing the air
    return np.array(freqs), which, np.array(batter), np.array(share), first


def _strike_amps(which, batter, share, freqs, radius: float, theta: float, contact: float, vel: float) -> np.ndarray:
    """How much one strike excites each mode: the mode's shape where it lands, the stick's contact, its radiation."""
    m = np.array([w[0] for w in which])
    j = np.array([w[2] for w in which])
    r = np.where(batter, radius, 0.0)  # the resonant head is driven through the air, as a whole
    shape = jv(m, j * r) / np.maximum(np.abs(jv(m + 1, j)), 1e-3)
    angle = np.where(batter, np.cos(m * theta), 1.0)
    radiate = np.where(m == 0, 1.0, 0.7)  # modes with nodal diameters radiate worse (less so to close microphones)
    return shape * angle * radiate * share * vel / (1.0 + (2.0 * freqs * contact) ** 2)


@lru_cache(maxsize=64)
def _sos(order: int, edges, btype: str, sr: int) -> np.ndarray:
    """A Butterworth filter's sections, designed once."""
    return butter(order, list(edges) if isinstance(edges, tuple) else edges, btype=btype, fs=sr, output="sos")


def _noise_burst(rng: np.random.Generator, sr: int, n: int, band: tuple[float, float], tau: float) -> np.ndarray:
    lo, hi = band
    y = sosfilt(_sos(2, (float(lo), float(min(hi, 0.45 * sr))), "bandpass", sr), rng.standard_normal(n + 64))[64:]
    y = y * np.exp(-np.arange(n) / (tau * sr))
    fade = max(1, n // 5)  # it ends gently, whatever is left of it
    y[n - fade:] *= np.linspace(1.0, 0.0, fade)
    return y


def drum_part(drum: Drum, strokes: list[Stroke], sr: int, length: int, rng: np.random.Generator, *,
              f0: float, reso0: float, reso: float, t60: float, brightness: float = 0.5,
              wear: float = 0.0, motion: bool = False, hoop: float = 1.0, stick: float = 1.0
              ) -> tuple[np.ndarray, np.ndarray]:
    """A drum's strokes as one mono track, and (if asked) its resonant head's motion, for a snare's wires
    (else None; the two, if asked, are the channels of one array, each where it lies). The shell's modes ring
    in the same bank, and a snare's hoop and a stick knocked on it (hoop, stick: their makers' tunings) when a
    stroke is a rim shot or a cross-stick."""
    if not strokes:
        out = np.zeros(length)
        return out, out
    freqs, which, batter, share, first = _modes(drum, f0, reso0, reso, drum.coupling)
    t60s = t60 * (freqs / freqs[0]) ** -drum.slope
    t60s[first:] *= 0.75  # the resonant head carries the wires, or a port: it dies a little sooner
    n_drum = len(freqs)
    shell_f = np.array([hz for hz, _, _ in drum.shell]) * rng.uniform(0.98, 1.02)
    shell_t = np.array([t for _, t, _ in drum.shell])
    shell_lv = np.array([lv for _, _, lv in drum.shell]) * 3.0
    knocks = any(s.kind in ("rim", "cross") for s in strokes)
    hoop_f, stick_f = (HOOP * hoop, STICK * stick) if knocks else (np.zeros(0), np.zeros(0))
    hoop_t = np.array([0.35, 0.3, 0.25, 0.2, 0.15])[: len(hoop_f)]
    stick_t = np.array([0.06, 0.045, 0.03, 0.02])[: len(stick_f)]
    all_f = np.concatenate([freqs, shell_f, hoop_f, stick_f])
    all_t = np.concatenate([t60s, shell_t, hoop_t, stick_t])
    n_shell, n_hoop = len(shell_f), len(hoop_f)
    times, amps, extra, energy_times, energy_levels, dead = [], [], [], [], [], []
    for s in strokes:
        contact = (drum.contact + 3.5 * drum.contact * (1.0 - s.vel) ** 2) * (1.25 - 0.5 * brightness)
        radius, click, slap = drum.radius, drum.click, drum.slap
        sub = [(0.0, 1.0)]  # the strikes that make up this stroke: (delay s, share of its force)
        if s.implement == "brush":
            contact *= 3.0
            click *= 0.08
            slap *= 0.5
            n = int(rng.integers(18, 30))  # the bristles: together a third of a stick's force, spread out
            sub = [(float(d), 0.4 / n) for d in np.sort(rng.gamma(2.0, 0.0018, n))]
        elif s.implement == "rod":
            contact *= 0.7  # each dowel light and quick; the bundle lighter than a stick, its strikes spread
            click *= 0.6
            n = int(rng.integers(5, 9))
            sub = [(float(d), 0.65 / n) for d in np.sort(rng.gamma(1.5, 0.0005, n))]
        elif s.implement == "mallet":
            contact = 0.004 + 0.004 * (1.0 - s.vel)
            click, slap = 0.0, 0.1
        elif s.implement == "tick":  # a bristle or a resting stick: the faintest touch, no click
            contact *= 2.0
            click, slap = 0.0, 0.0
        force = 1.35 if s.kind == "rim" else 1.0
        if s.kind == "rim":  # the stick strikes head and hoop at once, the head near its middle, hard
            contact *= 0.6
            radius = 0.45
            click *= 1.8
            slap *= 1.6
        strength = 0.0  # what the stroke gives the head's modes in all: its click and slap are measured by it
        for delay, part in sub:
            r = float(np.clip(radius + rng.normal(0.0, 0.05), 0.0, 0.95))
            times.append(s.time + delay)
            row = np.zeros(len(all_f))
            row[:n_drum] = _strike_amps(which, batter, share, freqs, r, rng.uniform(0.0, np.pi),
                                        contact * rng.uniform(0.9, 1.1), s.vel * part * force) * rng.uniform(0.9, 1.1)
            row[n_drum:n_drum + n_shell] = s.vel * part * force * shell_lv
            strength += float(np.sum(np.abs(row[:n_drum])))
            amps.append(row)
        if s.kind in ("rim", "cross"):  # the hoop rings; a cross-stick is mostly the stick's own knock
            row = np.zeros(len(all_f))
            ring = np.array([1.0, 0.8, 0.6, 0.45, 0.3]) * rng.uniform(0.7, 1.0, 5)
            if s.kind == "rim":
                row[n_drum + n_shell:n_drum + n_shell + n_hoop] = s.vel * ring * 0.45
            else:
                row[n_drum + n_shell:n_drum + n_shell + n_hoop] = s.knock * ring * 0.28
                row[n_drum + n_shell + n_hoop:] = s.knock * np.array([1.0, 0.7, 0.35, 0.15]) * rng.uniform(0.8, 1.0, 4) * 0.8
                extra.append((s.time, 0.96 * s.knock, (1200.0, 6000.0), 0.0007))  # wood on metal
            times.append(s.time)
            amps.append(row)
        energy_times.append(s.time)
        energy_levels.append((s.vel * force) ** 2)
        if click > 0.0:  # the stick's (or beater's) click, as strong as the strike, brighter the harder
            extra.append((s.time, click * CLICK * strength * s.vel ** 0.5, drum.click_band,
                          0.0005 + 0.0006 * (1.0 - brightness)))
        if slap > 0.0:  # the skin's slap: its crowded upper modes, a band of noise from about a kilohertz
            extra.append((s.time, slap * CLICK * strength * (0.5 + radius), (max(1000.0, 5.0 * freqs[0]), 9000.0),
                          0.012))
        if s.kind == "dead":  # the beater left buried in the head: it damps it for a moment
            dead.append(s.time)
    times_arr, amps_arr = np.array(times), np.array(amps)
    damp = None
    if dead:
        damp = np.zeros(length)
        for t in dead:
            i = max(0, int(round(t * sr)))
            damp[i:i + int(0.3 * sr)] += 25.0
    bend = None
    if drum.glide > 0.0:  # the tension follows the head's energy: a hard hit starts sharp, a roll bends further
        tau = t60 / 6.9 / 2.0
        hop = 64
        frames = length // hop + 2
        impulses = np.zeros(frames)
        np.add.at(impulses, np.clip((np.array(energy_times) * sr / hop).astype(int), 0, frames - 1), energy_levels)
        energy = lfilter([1.0], [1.0, -np.exp(-hop / (tau * sr))], impulses)
        bend_frames = drum.glide * (1.0 - np.exp(-energy)) / (1.0 - np.exp(-1.0)) * (1.0 - 0.3 * wear)
        bend = struck.per_sample(bend_frames, hop, length)
    # (the shell, hoop and stick share the head's bend: they are small and short, and a bank of their own
    # would cost a whole upsampling)
    if motion:  # a second channel hears the resonant head's modes alone: its motion, for the wires to ride on
        heard = np.arange(len(all_f))
        both = struck.ring(all_f, all_t, times_arr, amps_arr, sr, length, bend=bend, damp=damp,
                           mix=np.stack([np.ones(len(all_f)), (heard >= first) & (heard < n_drum)], axis=1))
        mono, head = both[:, 0], both[:, 1]
        del both
    else:
        mono, head = struck.ring(all_f, all_t, times_arr, amps_arr, sr, length, bend=bend, damp=damp), None
    del bend, damp
    for t, level, band, tau_click in extra:
        i = max(0, int(round(t * sr)))
        n = min(int(0.03 * sr), length - i)
        if n > 8:
            mono[i:i + n] += _noise_burst(rng, sr, n, band, tau_click) * level
    return mono, head


# --- the snare's wires, hoop and a stick on its rim --------------------------------------------------------


@njit(cache=True, nogil=True)
def _contacts(d, sr, omegas, preloads, damping):
    """Snare wire strands against the snare-side head. d: the head's displacement (down, toward the
    wires, positive; the strands below it can't pass it). A strand in contact rides with the head until
    the head pulls up and away faster than the strand's tension can pull it after (its free acceleration
    toward its preloaded rest, above the head); then it flies free, springs back and meets the head: a
    collision, as strong as they meet. Returns the collisions' strengths, one value a sample."""
    n = d.shape[0]
    out = np.zeros(n)
    dt = 1.0 / sr
    for s in range(omegas.shape[0]):
        w2 = omegas[s] * omegas[s]
        rest = -preloads[s]
        zeta = damping * omegas[s]
        w = d[0]
        v = 0.0
        touching = True
        prev_v = 0.0
        for t in range(1, n):
            vd = (d[t] - d[t - 1]) * sr
            ad = (vd - prev_v) * sr
            prev_v = vd
            if touching:
                w = d[t]
                v = vd
                if ad < -w2 * (w - rest):  # the head accelerates away faster than the strand can follow
                    touching = False
            else:
                a = -w2 * (w - rest) - 2.0 * zeta * v
                v += a * dt
                w += v * dt
                if w <= d[t]:  # it meets the head again
                    out[t] += vd - v if vd > v else 0.0
                    w = d[t]
                    v = vd
                    touching = True
    return out


@njit(cache=True, nogil=True)
def _grains(strengths, noise, offsets, length, tau):
    """Each nonzero strength a grain of noise decaying over tau samples, laid onto one track."""
    n = strengths.shape[0]
    out = np.zeros(n)
    size = noise.shape[0]
    k = 0
    decay = np.exp(-1.0 / tau)
    for t in range(n):
        a = strengths[t]
        if a == 0.0:
            continue
        o = offsets[k % offsets.shape[0]]
        k += 1
        g = a
        for j in range(length):
            if t + j >= n:
                break
            out[t + j] += g * noise[(o + j) % size]
            g *= decay
    return out


def wires(motion: np.ndarray, sr: int, rng: np.random.Generator, *, reference: float, sensitivity: float,
          strands: np.ndarray, brightness: float = 0.5, inplace: bool = False) -> np.ndarray:
    """The snare wires' rattle from the snare-side head's motion. sensitivity 0..1: loose wires (1) rattle
    at a touch, tight ones (0) need a firm stroke. strands: the coiled strands' own ringing partials (Hz),
    this maker's; every collision is a grain of rattle and a blow to them, so after the head settles the
    wires ring on a moment as themselves. inplace: the motion is scaled where it lies (it is used up)."""
    if not np.any(motion):
        return np.zeros_like(motion)
    if inplace:  # a full-force stroke moves the head about 1
        motion /= reference
        d = motion
    else:
        d = motion / reference
    f_head = 330.0
    count = 8
    # the head's acceleration at full force is about (2 pi f)^2; a strand lets go at a small fraction of it
    omegas = 2.0 * np.pi * rng.uniform(60.0, 140.0, count)
    let_go = (2.0 * np.pi * f_head) ** 2 * (0.0003 + 0.03 * (1.0 - sensitivity) ** 2) * rng.uniform(0.7, 1.3, count)
    preloads = let_go / omegas ** 2
    n = len(motion)
    hits = _contacts(np.ascontiguousarray(d), float(sr), omegas, preloads, 0.3)
    del d, motion  # (handed over whole, it goes now)
    hits /= 2.0 * np.pi * f_head  # in units of the head's speed at full force
    noise = rng.standard_normal(1 << 14)
    offsets = rng.integers(0, 1 << 14, 4096)
    rattle = _grains(hits, noise, offsets, int(0.002 * sr), 0.00035 * sr)
    lo, hi = 2000.0 + 600.0 * brightness, min(9000.0 + 3000.0 * brightness, 0.45 * sr)
    band = sosfilt(_sos(2, (lo, hi), "bandpass", sr), rattle)
    del rattle
    at = np.flatnonzero(hits)
    if not len(at):
        return band
    # each collision strikes the strands' partials, a little differently each time
    blows = hits[at][:, None] * rng.uniform(0.3, 1.0, (len(at), len(strands)))
    del hits
    ring = struck.ring(strands, 0.35 + 0.2 * rng.random(len(strands)), at / sr, blows, sr, n)
    ring *= 0.25  # (band + 0.25 * ring, where they lie)
    band += ring
    return band


def splat(times, vels, sr: int, length: int, rng: np.random.Generator) -> np.ndarray:
    """A brush landing: its bristles' own brief spray of noise."""
    out = np.zeros(length)
    for t, v in zip(times, vels):
        i = int(round(t * sr))
        n = min(int(0.04 * sr), length - i)
        if n > 8:
            out[i:i + n] += _noise_burst(rng, sr, n, (1500.0, 10000.0), 0.009) * v * 0.35
    return out


def sweep(start: float, dur: float, vel: float, sr: int, length: int, rng: np.random.Generator,
          circling: bool = False, into: np.ndarray | None = None) -> tuple[np.ndarray, list[float], list[float]]:
    """A brush swept across the coated head for `dur` seconds: its bristles catching and slipping, a dense
    stream of tiny catches, more of them and harder the faster the brush moves round its arc (fastest a
    little past the middle of the sweep). circling: sweeps follow one another, the brush never stopping, so
    it slows between them but not to rest. Returns the catches' sound, and the times and strengths of the
    few that shake the head enough to count as strikes. into: the sound added to it (a sum begun from 0.0,
    so the silence around the sweep adds nothing), and it returned."""
    i0 = int(round(start * sr))
    n = min(int(round(dur * sr)), length - i0)
    out = np.zeros(length) if into is None else into
    if n < 64:
        return out, [], []
    step = 0.0005
    t = np.arange(0.0, n / sr, step)
    x = t / (n / sr)
    speed = np.clip(np.sin(np.pi * x ** 0.8), 0.0, 1.0) ** 0.9
    if circling:
        speed = 0.35 + 0.65 * speed
    speed *= 1.0 + 0.2 * np.sin(2.0 * np.pi * rng.uniform(1.5, 3.0) * x + rng.uniform(0.0, 6.28))
    counts = rng.poisson(8000.0 * speed * step)
    total = int(counts.sum())
    at = ((np.repeat(t, counts) + rng.uniform(0.0, step, total)) * sr).astype(np.int64)
    blows = np.repeat(speed ** 1.75, counts) * rng.exponential(1.0, total) / 2.5
    keep = at < n
    strengths = np.zeros(n)
    np.add.at(strengths, at[keep], blows[keep])
    shake = keep & (rng.random(total) < 0.0045)  # the few that shake the head
    head_t = (start + at[shake] / sr).tolist()
    head_v = (vel * 0.25 * np.minimum(blows[shake], 1.0)).tolist()
    noise = rng.standard_normal(1 << 13)
    grains = _grains(strengths, noise, rng.integers(0, 1 << 13, 4096), int(0.002 * sr), 0.0004 * sr)
    shaped = sosfilt(_sos(2, (900.0, 9000.0), "bandpass", sr), grains)
    shaped += 0.7 * sosfilt(_sos(1, (2500.0, 5000.0), "bandpass", sr), grains)
    ramp = 0.03 if circling else 0.004  # a lone sweep starts and stops; a circling one flows on
    edge = np.minimum(1.0, np.minimum(np.arange(n), n - np.arange(n)) / (ramp * sr))
    if into is None:
        out[i0:i0 + n] = shaped * edge * vel * 0.06
    else:
        out[i0:i0 + n] += shaped * edge * vel * 0.06
    return out, head_t, head_v


# --- reading the part ------------------------------------------------------------------------------------

ALIASES = {
    "bass-drum": "kick", "bd": "kick", "bass": "kick", "kick-drum": "kick", "bassdrum": "kick", "sd": "snare",
    "rim": "snare-rim", "rimshot": "snare-rim", "rim-shot": "snare-rim", "cross": "snare-cross",
    "cross-stick": "snare-cross", "side-stick": "snare-cross", "sidestick": "snare-cross", "rim-click": "snare-cross",
    "ghost": "snare-ghost", "hh": "hat", "hat-closed": "hat", "closed-hat": "hat", "hh-closed": "hat", "hi-hat": "hat",
    "hihat": "hat", "open-hat": "hat-open", "hh-open": "hat-open", "hat-opened": "hat-open", "openhat": "hat-open",
    "hat-pedal": "hat-foot", "foot": "hat-foot", "hh-foot": "hat-foot", "hh-pedal": "hat-foot", "pedal": "hat-foot",
    "bell": "ride-bell", "cowbell": "ride-bell", "tom1": "tom-hi", "tom2": "tom-mid", "tom3": "tom-lo",
    "floor": "tom-lo", "floor-tom": "tom-lo", "floortom": "tom-lo", "low-tom": "tom-lo", "tom": "tom-mid",
    "mid-tom": "tom-mid", "rack-tom": "tom-hi", "high-tom": "tom-hi", "hi-tom": "tom-hi", "cymbal": "crash",
    "splash": "crash", "china": "crash", "choke": "crash-choke", "roll": "snare-roll", "brush": "brush-tap",
    "sweep": "brush-sweep", "dead": "kick-dead", "clap": "snare", "handclap": "snare",
}
PIECES = ("kick", "kick-dead", "snare", "snare-rim", "snare-cross", "snare-ghost", "snare-roll", "brush-tap",
          "brush-sweep", "hat", "hat-open", "hat-half", "hat-foot", "ride", "ride-bell", "ride-crash", "ride-roll",
          "crash", "crash-choke", "crash-roll", "tom-hi", "tom-mid", "tom-lo", "tom-hi-roll", "tom-mid-roll",
          "tom-lo-roll")
IMPLEMENTS = ("stick", "brush", "rod", "mallet")
# General MIDI's percussion keys, for a part that names its pieces by pitch alone (others play a closed hat)
GM = {35: "kick", 36: "kick", 37: "snare-cross", 38: "snare", 39: "snare-rim", 40: "snare-rim", 41: "tom-lo",
      42: "hat", 43: "tom-lo", 44: "hat-foot", 45: "tom-mid", 46: "hat-open", 47: "tom-mid", 48: "tom-hi",
      49: "crash", 50: "tom-hi", 51: "ride", 52: "crash", 53: "ride-bell", 55: "crash", 56: "ride-bell", 57: "crash",
      59: "ride", 31: "snare-cross", 33: "snare-cross", 34: "ride-bell"}


def parse(art: str, pitch: float | None = None) -> tuple[str, str]:
    """An art as (piece, implement): "snare", "ride:brush", "tom-lo:mallet", "rim", "brush-tap"... With no
    art, or one it doesn't know, the piece General MIDI gives the note's pitch; failing that, the nearest
    piece by name (a hat, a ride, a tom), or a closed hat."""
    name = "-".join((art or "").strip().lower().replace("_", " ").split())
    piece, _, implement = name.partition(":")
    piece = ALIASES.get(piece, piece)
    known_pitch = pitch is not None and int(round(pitch)) in GM
    if not piece or (piece not in PIECES and known_pitch):
        piece = GM.get(int(round(pitch)), "hat") if pitch is not None else "snare"
    implement = implement if implement in IMPLEMENTS else ""
    if piece.startswith("brush"):
        implement = "brush"
    if piece not in PIECES:
        for word, fallback in (("hat", "hat"), ("ride", "ride"), ("crash", "crash"), ("floor", "tom-lo"),
                               ("tom", "tom-mid"), ("kick", "kick"), ("snare", "snare"), ("rim", "snare-rim")):
            if word in piece:
                piece = fallback
                break
        else:
            piece = "hat"
    if piece in ("ride-roll", "crash-roll") and not implement:
        implement = "mallet"
    return piece, implement or "stick"


def _roll(note, rate: float, rng: np.random.Generator, swell: bool) -> list[tuple[float, float]]:
    """Strokes of a roll filling a note: (time, vel), alternating hands, swelling if asked (never before the
    note starts)."""
    n = max(2, int(note.dur * rate))
    out = []
    for i in range(n):
        x = i / max(n - 1, 1)
        v = note.vel * ((0.35 + 0.65 * x) if swell else 1.0) * (0.92 if i % 2 else 1.0) * rng.uniform(0.9, 1.08)
        out.append((max(note.start, note.start + (i + rng.normal(0.0, 0.08)) / rate), float(np.clip(v, 0.02, 1.0))))
    return out


# --- the kit --------------------------------------------------------------------------------------------

PAN = {"kick": 0.0, "snare": -0.08, "hat": -0.45, "ride": 0.45, "crash": -0.3, "tom-hi": -0.22, "tom-mid": 0.08,
       "tom-lo": 0.42}
# Each piece's early loudness (dB, first 0.1 s of a medium stroke) in the kit: a drummer's balance, the
# backbeat and the kick up front, toms nearly with them, the cymbals under them.
BALANCE = {"kick": 0.0, "snare": 0.0, "tom": -1.5, "hat": -9.0, "ride": -8.0, "crash": -3.0}


@dataclass(frozen=True)
class Build:
    """How this maker's kit is built and tuned (drawn once from make)."""

    kick: float
    kick_ring: float
    beater: str
    snare: float
    snare_ring: float
    sensitivity: float
    toms: tuple[float, float, float]
    tom_reso: tuple[float, float, float]
    tom_ring: tuple[float, float, float]
    hoop: float
    stick: float
    strands: tuple[float, ...] = ()  # the snare wires' ringing partials, Hz


def build(make: np.random.Generator, size: float = 1.0, wear: float = 0.0) -> Build:
    slack = 1.0 - 0.04 * wear  # a worn kit's heads have stretched a little
    kick = KICK.f0 * 2.0 ** make.uniform(-0.2, 0.15) / size * slack
    snare = SNARE.f0 * 2.0 ** make.uniform(-0.15, 0.2) / size * slack
    hi = 185.0 * 2.0 ** make.uniform(-0.15, 0.15) / size * slack  # a 10-12 inch rack tom
    mid = hi / 2.0 ** make.uniform(0.3, 0.5)
    lo = mid / 2.0 ** make.uniform(0.45, 0.65)  # a 14-16 inch floor tom
    detune = lambda: 2.0 ** make.normal(0.0, 0.05 + 0.1 * wear)  # noqa: E731  a resonant head, tuned by ear
    return Build(
        kick=kick, kick_ring=float(make.uniform(0.3, 0.6)), beater="felt" if make.random() < 0.7 else "plastic",
        snare=snare, snare_ring=float(make.uniform(0.16, 0.26)),
        sensitivity=float(np.clip(make.uniform(0.45, 0.85) + 0.15 * wear, 0.0, 1.0)),
        toms=(hi, mid, lo), tom_reso=(1.05 * detune(), 1.06 * detune(), 1.07 * detune()),
        tom_ring=(float(make.uniform(0.55, 0.85)), float(make.uniform(0.7, 1.05)), float(make.uniform(0.9, 1.35))),
        hoop=float(make.uniform(0.9, 1.1)), stick=float(make.uniform(0.85, 1.15)),
        strands=tuple(float(f) for f in np.sort(np.exp(make.uniform(np.log(1500.0), np.log(7000.0), 16)))),
    )


def _pan(y: np.ndarray, position: float) -> np.ndarray:
    theta = (position + 1.0) * np.pi / 4.0
    return np.stack([y * np.cos(theta), y * np.sin(theta)], axis=1) * np.sqrt(2.0)


def _placed(y: np.ndarray, position: float, width: float) -> np.ndarray:
    """A stereo cymbal at `position` in the kit, keeping `width` of its two microphones' difference."""
    mid, side = 0.5 * (y[:, 0] + y[:, 1]), 0.5 * (y[:, 0] - y[:, 1]) * width
    theta = (position + 1.0) * np.pi / 4.0
    return np.stack([mid * np.cos(theta) * np.sqrt(2.0) + side, mid * np.sin(theta) * np.sqrt(2.0) - side], axis=1)


BLOCK = 1 << 16  # samples a stretch, where every operation is on each sample alone


def _add(out: np.ndarray, place, y: np.ndarray, *args) -> None:
    """out += place(y, *args) (_pan, _placed), a stretch at a time: the same operations on each sample, without
    the song-long copies they make."""
    for a in range(0, len(y), BLOCK):
        out[a:a + BLOCK] += place(y[a:a + BLOCK], *args)


def early(y: np.ndarray, sr: int, seconds: float = 0.1) -> float:
    """The K-weighted RMS of a stroke's first `seconds` (its loudness as the ear takes a hit)."""
    seg = y[: int(seconds * sr)]
    seg = seg.mean(axis=1) if seg.ndim == 2 else seg
    for b, a in _k_weighting(sr):
        seg = lfilter(b, a, seg)
    return float(np.sqrt(np.mean(seg ** 2))) + 1e-12


def _hat_track(hat_notes, sr: int, length: int) -> tuple[np.ndarray, list[Hit], list[tuple[float, float, float]]]:
    """The hi-hat pedal from the hat's notes (time, dur, piece, vel), in time order: its damping track (closed
    unless opened), the chicks its plates make when the foot brings them together, and the half-open
    stretches. An open hat closes at the next hat note, or at its own end if its length is more than a
    nominal 0.3 s and comes first; with nothing after it, at its end (at least 0.6 s on, at most 2 s)."""
    closed = 75.0  # nepers a second: the clamped plates ring about 90 ms
    openness = np.zeros(length)
    chicks, halves = [], []
    for k, (t, dur, piece, vel) in enumerate(hat_notes):
        nxt = hat_notes[k + 1] if k + 1 < len(hat_notes) else None
        i0 = int(round(max(0.0, t - 0.012) * sr))  # the foot lifts just before the stick lands
        if piece in ("hat-open", "hat-half"):
            amount = 1.0 if piece == "hat-open" else 0.6
            end = (nxt[0] - 0.003) if nxt is not None else t + min(max(dur, 0.6), 2.0)
            if dur > 0.3:
                end = min(end, t + dur)
            end = min(end, t + 2.0)
            i1 = min(length, int(round(end * sr)))
            openness[i0:i1] = np.maximum(openness[i0:i1], amount)
            reopened = nxt is not None and nxt[2] in ("hat-open", "hat-half") and nxt[0] - end < 0.02
            if piece == "hat-half":
                halves.append((t, end, amount))
            elif end < length / sr and not reopened and not (nxt is not None and nxt[2] == "hat-foot"):
                chicks.append(Hit(end + 0.003, 0.3 + 0.35 * vel, "chick"))  # the foot closing it
        elif piece == "hat-foot":  # the foot lifts the top plate a little and brings it down: the chick
            j0 = int(round(max(0.0, t - 0.05) * sr))
            j1 = int(round(t * sr))
            openness[j0:j1] = np.maximum(openness[j0:j1], 0.25)
            chicks.append(Hit(t, vel, "chick"))
    smooth = np.exp(-1.0 / (0.004 * sr))  # the pedal moves in a few milliseconds, not at once
    openness = lfilter([1.0 - smooth], [1.0, -smooth], openness)
    # closed * (1 - clip(openness, 0, 1)) ** 2, where it lies (an array's ** 2 is its square)
    np.clip(openness, 0.0, 1.0, out=openness)
    np.subtract(1.0, openness, out=openness)
    np.square(openness, out=openness)
    openness *= closed
    return openness, chicks, halves


def render(name, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A kit part: every stroke, stereo, from the drummer's seat, before its place and level."""
    bright = float(settings.get("brightness", 0.5))
    wear = float(settings.get("wear", 0.25))
    size = float(settings.get("body", 1.0))
    kit = build(make, size, wear)
    cymbal_seeds = {k: int(make.integers(1 << 62)) for k in ("hat", "ride", "crash")}
    drums = {k: [] for k in ("kick", "snare", "tom-hi", "tom-mid", "tom-lo")}
    sweeps, taps, hat_notes = [], [], []
    hits = {"hat": [], "ride": [], "crash": []}
    chokes = []
    for note in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if note.start >= length / sr or note.start < 0.0:
            continue
        piece, implement = parse(note.art, note.pitch)
        vel = float(np.clip(note.vel, 0.0, 1.0))
        if piece == "snare-ghost":
            piece, vel = "snare", 0.1 + 0.22 * vel
        if piece in ("kick", "kick-dead"):
            drums["kick"].append(Stroke(note.start, vel, "beater", "dead" if piece == "kick-dead" else ""))
        elif piece in ("snare", "brush-tap"):
            drums["snare"].append(Stroke(note.start, vel, implement))
            if implement == "brush":
                taps.append((note.start, vel))
        elif piece == "snare-rim":
            drums["snare"].append(Stroke(note.start, vel, implement, "rim"))
        elif piece == "snare-cross":  # the butt resting on the head, the stick knocked on the hoop
            drums["snare"].append(Stroke(note.start, vel * 0.12, "tick", "cross", knock=vel))
        elif piece == "snare-roll":  # a press roll: each stroke buzzing into bounces that run to the next
            for t, v in _roll(note, 10.0, rng, swell=False):
                for b in range(5):
                    drums["snare"].append(Stroke(t + b * rng.uniform(0.018, 0.022), v * 0.72 ** b * 0.8, implement))
        elif piece == "brush-sweep":
            sweeps.append((note.start, note.dur, vel))
        elif piece.startswith("tom"):
            drum_name = piece[:-5] if piece.endswith("-roll") else piece
            if piece.endswith("-roll"):  # steady: a swell is written with rising velocities, or on a cymbal
                drums[drum_name] += [Stroke(t, v, implement) for t, v in _roll(note, 14.0, rng, swell=False)]
            else:
                drums[drum_name].append(Stroke(note.start, vel, implement))
        elif piece.startswith("hat"):
            hat_notes.append((note.start, note.dur, piece, vel))
            if piece != "hat-foot":
                hits["hat"].append(Hit(note.start, vel, "bow", implement))
        elif piece.startswith("ride"):
            if piece == "ride-roll":
                hits["ride"] += [Hit(t, v, "bow", implement) for t, v in _roll(note, 12.0, rng, swell=True)]
            else:
                zone = {"ride": "bow", "ride-bell": "bell", "ride-crash": "edge"}[piece]
                hits["ride"].append(Hit(note.start, vel, zone, implement))
        else:  # crash, crash-choke, crash-roll
            if piece == "crash-roll":
                hits["crash"] += [Hit(t, v, "bow", implement) for t, v in _roll(note, 12.0, rng, swell=True)]
            else:
                hits["crash"].append(Hit(note.start, vel, "edge", implement))
                if piece == "crash-choke":
                    chokes.append(note.start + max(note.dur, 0.05))
    # Every song-long signal is let go as soon as what follows has used it, and treated where it lies: the same
    # operations on the same values as ever (a drum that isn't played is silence, None, and adding silence to a
    # sum begun from 0.0 changes nothing).
    swept = None
    for k, (start, dur, vel) in enumerate(sweeps):
        # sweeps that follow on one another within a few hundredths of a second are one brush circling
        joined = any(abs(o_start + o_dur - start) < 0.05 or abs(start + dur - o_start) < 0.05
                     for j, (o_start, o_dur, _) in enumerate(sweeps) if j != k)
        swept = np.zeros(length) if swept is None else swept
        swept, head_t, head_v = sweep(start, dur, vel, sr, length, rng, circling=joined, into=swept)
        drums["snare"] += [Stroke(t, v, "tick") for t, v in zip(head_t, head_v)]
    drums["snare"].sort(key=lambda s: s.time)
    # --- drums ---
    plastic = kit.beater == "plastic"
    kick_drum = replace(KICK, click=KICK.click * (1.6 if plastic else 1.0),
                        click_band=(2000.0, 5500.0) if plastic else KICK.click_band,
                        contact=KICK.contact * (0.55 if plastic else 1.0))
    tunings = {"kick": (kick_drum, kit.kick, KICK.reso0, KICK.reso, kit.kick_ring),
               "snare": (SNARE, kit.snare, SNARE.reso0, SNARE.reso, kit.snare_ring)}
    for k, piece in enumerate(("tom-hi", "tom-mid", "tom-lo")):
        tunings[piece] = (TOM, kit.toms[k], kit.tom_reso[k], kit.tom_reso[k], kit.tom_ring[k])
    played = [piece for piece in tunings if drums[piece]]
    tracks, head = dict.fromkeys(tunings), None  # each drum's track (None: silent), the snare-side head's motion
    gains = {}
    for piece in played + (["snare"] if played and "snare" not in played else []):
        drum, f0, reso0, reso, ring = tunings[piece]
        gains[piece] = _gain(piece, drum, f0, reso0, reso, ring, sr, bright)
    for piece in played:
        drum, f0, reso0, reso, ring = tunings[piece]
        y, motion = drum_part(drum, drums[piece], sr, length, rng, f0=f0, reso0=reso0, reso=reso, t60=ring,
                              brightness=bright, wear=wear, motion=piece == "snare", hoop=kit.hoop, stick=kit.stick)
        y *= gains[piece]  # (y * its gain, where it lies)
        tracks[piece] = y
        if piece == "snare":
            motion *= gains[piece]
            head = motion
        del y, motion
    # the toms answer the kick and the snare, faintly, through the air (a kit rings as one instrument): their
    # lowest few modes, driven by every firm stroke, one channel a tom
    loud = [st for st in drums["kick"] + drums["snare"] if st.implement != "tick" and st.vel > 0.2]
    if loud:
        low, rings, mix = [], [], np.zeros((12, 3))
        for k, piece in enumerate(("tom-hi", "tom-mid", "tom-lo")):
            drum, f0, reso0, reso, ring = tunings[piece]
            lowest = np.sort(_modes(drum, f0, reso0, reso, drum.coupling)[0])[:4]
            low += list(lowest)
            rings += list(ring * (lowest / lowest[0]) ** -drum.slope)
            mix[4 * k: 4 * k + 4, k] = gains.get(piece) or _gain(piece, drum, f0, reso0, reso, ring, sr, bright)
        amps = np.array([st.vel for st in loud])[:, None] * np.tile([1.0, 0.6, 0.4, 0.3], 3)[None, :] * 0.03
        ringing = struck.ring(low, rings, np.array([st.time + 0.001 for st in loud]), amps, sr, length, mix=mix)
        for k, piece in enumerate(("tom-hi", "tom-mid", "tom-lo")):
            if tracks[piece] is None:  # silence and its ringing: the ringing's own channel, + 0.0
                tracks[piece] = ringing[:, k]
                tracks[piece] += 0.0
            else:
                tracks[piece] += ringing[:, k]
        del ringing
    if played:
        # the wires ride on the snare-side head, which also answers the kick and the toms (the air pushing
        # it): the sympathetic buzz of any kit
        g = gains["snare"]
        reference = _reference_motion(sr, kit) * g
        others = np.empty(length)
        for a in range(0, length, BLOCK):  # kick * 0.5 + (the toms) * 0.8, a stretch at a time
            part = {p: np.zeros(min(length, a + BLOCK) - a) if tracks[p] is None else tracks[p][a:a + BLOCK]
                    for p in ("kick", "tom-hi", "tom-mid", "tom-lo")}
            others[a:a + BLOCK] = part["kick"] * 0.5 + (part["tom-hi"] + part["tom-mid"] + part["tom-lo"]) * 0.8
            del part  # (its views would keep the tracks alive)
        reso_hz = kit.snare * SNARE.reso0
        band = butter(2, [reso_hz * 0.7, reso_hz * 1.4], btype="bandpass", fs=sr, output="sos")
        sympathy = sosfilt(band, others)
        del others
        sympathy *= 0.25 + 0.4 * wear
        sympathy *= reference
        # the head's own motion and what the others give it (head + sympathy), in the sympathy's own array; the
        # snare's track then copied out of the channel it shared with its head, and that let go
        sympathy += 0.0 if head is None else head  # (a snare not played: its head moves only as the others push it)
        head = sympathy
        del sympathy
        if tracks["snare"] is not None:
            tracks["snare"] = np.ascontiguousarray(tracks["snare"])
        held = [head]  # handed over whole (wires scales it where it lies, and lets it go once heard)
        del head
        rattle = wires(held.pop(), sr, rng, reference=reference, sensitivity=kit.sensitivity,
                       strands=np.array(kit.strands), brightness=bright, inplace=True)
        rattle *= g
        rattle *= 0.35
        snare = tracks["snare"]
        if snare is None:  # (silence + the rattle)
            snare = rattle
            snare += 0.0
        else:
            snare += rattle
        del rattle
        if taps:
            tapped = splat([t for t, _ in taps], [v for _, v in taps], sr, length, rng)
            tapped *= g
            snare += tapped
            del tapped
        if swept is None:
            snare += 0.0  # (+ silence * g)
        else:
            swept *= g
            snare += swept
        tracks["snare"] = snare
        del snare
    del swept
    out = np.zeros((length, 2))
    for piece in ("kick", "snare", "tom-hi", "tom-mid", "tom-lo"):
        if tracks[piece] is not None:  # (a drum never heard would add 0.0 to a sum begun from 0.0: nothing)
            _add(out, _pan, tracks[piece], PAN[piece])
        tracks[piece] = None
    # --- cymbals ---
    if hits["hat"] or hat_notes:
        damp, chicks, halves = _hat_track(sorted(hat_notes), sr, length)
        cymbal = _cymbal(cymbals.HAT, cymbal_seeds["hat"], sr, size)
        rattles = cymbals.sizzle(halves, hits["hat"], sr, rng)
        y = cymbals.play(cymbals.HAT, hits["hat"] + chicks + rattles, sr, length, rng, cymbal, brightness=bright,
                         wear=wear, damp=damp)
        del damp
        y *= _cymbal_gain("hat", cymbals.HAT, cymbal_seeds["hat"], sr, size, bright, closed=True)
        _add(out, _placed, y, PAN["hat"], 0.5)
        del y
    if hits["ride"]:
        cymbal = _cymbal(cymbals.RIDE, cymbal_seeds["ride"], sr, size)
        y = cymbals.play(cymbals.RIDE, hits["ride"], sr, length, rng, cymbal, brightness=bright, wear=wear)
        y *= _cymbal_gain("ride", cymbals.RIDE, cymbal_seeds["ride"], sr, size, bright)
        _add(out, _placed, y, PAN["ride"], 0.6)
        del y
    if hits["crash"]:
        damp = None
        if chokes:
            damp = np.zeros(length)
            for t in chokes:
                later = [h.time for h in hits["crash"] if h.time > t]
                damp[int(round(t * sr)):int(round(min(later) * sr)) if later else length] = 60.0  # the hand grabs it
        cymbal = _cymbal(cymbals.CRASH, cymbal_seeds["crash"], sr, size)
        y = cymbals.play(cymbals.CRASH, hits["crash"], sr, length, rng, cymbal, brightness=bright, wear=wear,
                         damp=damp)
        del damp
        y *= _cymbal_gain("crash", cymbals.CRASH, cymbal_seeds["crash"], sr, size, bright)
        _add(out, _placed, y, PAN["crash"], 0.7)
        del y
    # A struck head's ring swings about its rest a little off centre, which the impact's own pulse balances in
    # the air; the modes leave that pulse out, so a gentle high-pass under the kick takes the offset away. The
    # kit comes out 6 dB under its balance's own scale, so even coincident accents stay under full scale dry.
    # (A channel at a time, where it lies: a channel filtered alone is filtered as along axis 0.)
    sos = butter(2, 22.0, btype="highpass", fs=sr, output="sos")
    for c in range(2):
        out[:, c] = sosfilt(sos, out[:, c])
    out *= 0.5
    return out


@lru_cache(maxsize=32)
def _reference_motion(sr: int, kit: Build) -> float:
    """The snare-side head's peak motion after a full-force stroke (before levelling): what the wires'
    tension is measured against."""
    _, motion = drum_part(SNARE, [Stroke(0.01, 1.0)], sr, int(0.15 * sr), np.random.default_rng(0), f0=kit.snare,
                          reso0=SNARE.reso0, reso=SNARE.reso, t60=kit.snare_ring, motion=True)
    return float(np.max(np.abs(motion))) + 1e-12


@lru_cache(maxsize=256)
def _gain(piece: str, drum: Drum, f0: float, reso0: float, reso: float, ring: float, sr: int,
          brightness: float) -> float:
    """What brings a drum's medium stroke to its place in the kit's balance, whatever its maker's tuning: the
    early loudness of four medium strokes (each lands somewhere a little different), brought to the balance."""
    energy = 0.0
    for seed in range(1, 5):
        y, _ = drum_part(drum, [Stroke(0.0, 0.6)], sr, int(0.12 * sr), np.random.default_rng(seed), f0=f0,
                         reso0=reso0, reso=reso, t60=ring, brightness=brightness)
        energy += early(y, sr) ** 2 / 4.0
    balance = BALANCE["tom"] if piece.startswith("tom") else BALANCE[piece]
    return 10.0 ** (balance / 20.0) * 0.1 / np.sqrt(energy)


@lru_cache(maxsize=64)
def _cymbal(plate, seed: int, sr: int, size: float):
    """A maker's cymbal, hammered once (its modes, its lines, its reference stroke)."""
    return cymbals.make_cymbal(plate, np.random.default_rng(seed), sr, size)


@lru_cache(maxsize=128)
def _cymbal_gain(piece: str, plate, seed: int, sr: int, size: float, brightness: float, closed: bool = False) -> float:
    damp = np.full(int(0.12 * sr), 75.0) if closed else None
    energy = 0.0
    for trial in range(1, 5):
        y = cymbals.play(plate, [Hit(0.0, 0.6)], sr, int(0.12 * sr), np.random.default_rng(trial),
                         _cymbal(plate, seed, sr, size), brightness=brightness, damp=damp)
        energy += early(y, sr) ** 2 / 4.0
    return 10.0 ** (BALANCE[piece] / 20.0) * 0.1 / np.sqrt(energy)


ARTICULATIONS = {
    "kick": "the bass drum, its beater near the middle of the head",
    "snare": "a stroke on the snare; vel under about 0.3 is a ghost note (soft, dull, a thin buzz of the wires)",
    "snare-rim": "a rim shot: head and hoop at once, louder and ringing (alias rim)",
    "snare-cross": "a cross-stick: the stick's butt on the head, struck on the hoop: a woody knock (alias cross)",
    "snare-ghost": "a ghost note whatever the vel (alias ghost)",
    "snare-roll": "a press roll filling the note's length",
    "hat": "the closed hi-hat, the stick's tip on its top",
    "hat-open": "the hi-hat open: it rings until the next hi-hat note closes it (its own length if none follows)",
    "hat-half": "the hi-hat half open: its plates sizzle against each other",
    "hat-foot": "the foot closing the hi-hat: its chick",
    "ride": "the ride's bow: a ping over a wash that builds",
    "ride-bell": "the ride's bell: a clear, long ding (alias bell)",
    "ride-crash": "the ride struck on its edge with the stick's shoulder: a big wash",
    "ride-roll": "a mallet roll on the ride, swelling through the note",
    "crash": "the crash, on its edge",
    "crash-choke": "the crash, grabbed at the note's end (alias choke)",
    "crash-roll": "a mallet roll on the crash, swelling through the note: a cymbal swell",
    "tom-hi": "the high rack tom", "tom-mid": "the middle rack tom", "tom-lo": "the floor tom",
    "tom-hi-roll": "a roll on the high tom, swelling", "tom-mid-roll": "a roll on the middle tom, swelling",
    "tom-lo-roll": "a roll on the floor tom, swelling (with mallets, tom-lo-roll:mallet, timpani-like)",
    "brush-tap": "a brush tapped on the snare: soft, smeared, the wires answering",
    "brush-sweep": "a brush swept across the snare for the note's length: the swish, fastest a little past its middle",
    "ride:brush": "any piece followed by :brush, :rod or :mallet is played with it (sticks otherwise)",
    "hat:rod": "the closed hi-hat played with rods", "snare-cross:rod": "a cross-stick with rods",
    "tom-lo:mallet": "the floor tom with a soft mallet: dark, no click",
    "": "no art: the piece General MIDI gives the note's pitch (36 kick, 38 snare, 42 hat, 46 open hat, 49 crash, "
        "51 ride, 53 ride bell, 41/43 floor tom, 45/47 middle tom, 48/50 high tom, 37 cross-stick, 39/40 rim shot)",
}

SPEC = {
    "kit": dict(
        family="drums", role="percussion", register=None, place=(0.05, 0.8), level=0.97, poly=True,
        articulations=ARTICULATIONS,
        about="an acoustic drum kit (kick, snare, three toms, hi-hat, ride, crash) played with sticks, brushes, "
              "rods or mallets, heard from the drummer's seat",
    ),
}
