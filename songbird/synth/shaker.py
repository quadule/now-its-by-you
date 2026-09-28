"""Shaken things: a shaker, and a tambourine.

Both are particles in collision (Cook, "Physically informed sonic modeling
(PhISM): synthesis of percussive sounds", Computer Music Journal 21(3),
1997, and STK's Shakers.cpp). A shake puts energy into the particles, which
bleeds away in a few hundredths of a second (friction, the shell's give);
while it lasts they collide, more often and harder the more there is, and
each collision is a click of a fraction of a millisecond that rings the
shell. What comes out is not a smooth hiss but a crowd of small impacts,
dense at the stroke and thinning as the beads settle, and harder impacts
are brighter ones (a shorter contact: rattle.py).

The shaker is one of three kinds, by maker: an egg (plastic, shot inside,
its shell ringing near 5 kHz and 9.5 kHz, bright and tight), a gourd maraca
(Cook's: about 64 seeds in a shell ringing near 3.2 kHz with a Q of about
5.5, woody) or a tube of sand or rice (hundreds of grains, resonances near
2.4, 6.2 and 11 kHz, a smoother grain, and a swish as the grains slide
before they hit the end). A shaker played in eighths or sixteenths goes
forward and back: the forward stroke, on the eighths, throws the beads
against the far end all at once (accented, a sharp attack); the back stroke
is softer and more diffuse. Without a tempo the strokes alternate, starting
forward after a rest. A roll is a fast shake held for the note's length.

The tambourine's jingles are pairs of thin cupped discs on pins in the
frame. Each disc rings in its own inharmonic modes (a free circular plate's,
1, 1.73, 2.33, 3.91 and 6.30 times the lowest, near 2 to 4 kHz here, so its
energy sits between about 3 and 12 kHz, as Cook's jingle resonances at 5.6
and 8.1 kHz do), the two discs of a pair a few percent apart; a collision
kicks one pair's modes by a random amount each (where the discs meet) and
clicks against the frame, whose hoop rings near 2.3 kHz (Cook's shell). The
jingles ring down in a few tenths of a second. A headed tambourine (half of
them, by maker) has a skin about 25 cm across whose lowest mode sits near
300 Hz; the palm's stroke on it thumps (a membrane's Bessel modes, a soft
contact of a few milliseconds) and knocks the wooden frame. Strokes: struck
with the palm (the thump, a knock and a crash of jingles), shaken (one flick
for a short note, a shake at nine to eleven flicks a second for a long one),
a light finger tap (jingles only) and a thumb roll (the thumb's skid along
the head, 22 to 28 bursts a second, for the note's length).

Levels: each instrument is calibrated as its maker built it, by rendering a
reference stroke with a generator of its own and measuring its early
loudness, so a stroke's first 30 ms sit at the same K-weighted loudness
whatever the kind, the beads or the jingles.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import sosfilt
from scipy.special import jv

from . import struck
from .drum import MODES as MEMBRANE
from .iir import butter
from .rattle import HOP, collide, contact, early_power, late, modal_weights, vel_gain

SPEC = {
    "shaker": dict(
        family="percussion", role="percussion", register=None, place=(0.35, 0.2), level=0.193, poly=True,
        loudness=-31.4,  # a texture over the pulse: 3 dB under the frame drum's full pattern
        articulations={
            "shaker": "one stroke: forward (on the eighths, or after a rest) accented, back strokes softer",
            "shaker-roll": "shaken fast and steadily for the note's length",
        },
        about="a shaker: an egg, a gourd maraca or a tube of sand (by maker), beads colliding in a shell (PhISEM)",
    ),
    "tambourine": dict(
        family="percussion", role="percussion", register=None, place=(-0.35, 0.2), level=0.30, poly=True,
        loudness=-30.4,  # bright and cutting: 2 dB under the frame drum's full pattern
        articulations={
            "tambourine": "struck with the palm: the head's thump (if headed) and a crash of jingles",
            "tambourine-shake": "shaken: one flick for a short note, a shake (9 to 11 flicks a second) for a long one",
            "tambourine-tap": "a light finger tap: jingles only",
            "tambourine-roll": "a thumb roll for the note's length",
        },
        about="a tambourine: four to eight pairs of jingles, each with its own modes, headed or not (by maker)",
    ),
}

EARLY = 0.25  # a stroke's early RMS (K-weighted, first 30 ms) at full velocity, before the stem's level


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A part's dry stem, mono (length,): see SPEC."""
    s = dict(settings or {})
    if name == "shaker":
        return shaker(notes, sr, length, rng, make, s)
    if name == "tambourine":
        return tambourine(notes, sr, length, rng, make, s)
    raise ValueError(f"shaker.py plays the shaker and the tambourine, not {name}")


def _knobs(s: dict) -> tuple[float, float, float]:
    return (float(np.clip(s.get("brightness", 0.5), 0.0, 1.0)), float(np.clip(s.get("wear", 0.25), 0.0, 1.0)),
            float(np.clip(s.get("body", 1.0), 0.5, 2.0)))


def _playing(notes, length: int, sr: int):
    return [n for n in notes if 0 <= int(round(n.start * sr)) < length]


def _rise(attack: float, tau: float) -> float:
    """The peak of (1 - exp(-t/attack)) exp(-t/tau), to scale a stroke's energy to its peak."""
    t = attack * np.log1p(tau / attack)
    return (1.0 - np.exp(-t / attack)) * np.exp(-t / tau)


def _energy(events, length: int, sr: int) -> np.ndarray:
    """The particles' energy, one value every HOP samples, from strokes (start s, peak, attack s, tau s, swish)
    and held shakes (start s, end s, level, tau s)."""
    n = length // HOP + 2
    e = np.zeros(n)
    dt = HOP / sr
    for t0, peak, attack, tau, swish in events[0]:
        i0 = int(np.ceil(t0 / dt))
        i1 = min(n, i0 + int(9.0 * tau / dt) + 2)
        if i0 < n and i1 > 0:
            t = np.arange(max(i0, 0), i1) * dt - t0
            e[max(i0, 0):i1] += peak * (1.0 - np.exp(-t / attack)) * np.exp(-t / tau) / _rise(attack, tau)
        if swish > 0.0:  # grains sliding along the tube before they hit its end
            j0 = max(0, int(np.ceil((t0 - 0.1) / dt)))
            j1 = min(n, max(0, i0))
            if j1 > j0:
                e[j0:j1] += swish * peak * np.exp((np.arange(j0, j1) * dt - t0) / 0.03)
    for t0, t1, level, tau in events[1]:
        i0, i1 = max(0, int(np.ceil(t0 / dt))), min(n, int(np.ceil(t1 / dt)))
        if i1 > i0:
            ramp = np.minimum(1.0, (np.arange(i0, i1) * dt - t0) / 0.015)
            e[i0:i1] += level * ramp
        j1 = min(n, i1 + int(9.0 * tau / dt) + 2)
        if j1 > i1:
            e[i1:j1] += level * np.exp(-(np.arange(i1, j1) * dt - t1) / tau)
    return e


def _forward(notes, s: dict) -> list[bool]:
    """Which strokes go forward: those on the eighths when the tempo is known, else every other one,
    starting forward after a rest."""
    tempo = float(s.get("tempo") or 0.0)
    out, last, prev = [], -1.0, True
    for note in notes:
        if tempo > 0.0:
            fwd = round(note.start * tempo / 60.0 * 4.0) % 2 == 0
        else:
            fwd = True if note.start - last > 0.45 else not prev
        out.append(fwd)
        last, prev = note.start, fwd
    return out


# --- the shaker -------------------------------------------------------------------------------


# the kinds: shell (Hz, Q, gain), particles and collisions a second each, impact click (ms), clicks heard directly,
# the energy's e-fold time (s), attack (s), how the impacts spread (gamma), the clicks' lowpass (Hz) with no energy
# and full, the tube's swish before a stroke
KINDS = {
    "egg": dict(shell=((5000.0, 3.5, 1.0), (9500.0, 4.0, 0.5)), count=(60, 120), each=50.0, click=0.35, direct=0.35,
                tau=0.022, attack=0.002, gamma=1.5, bright=(3000.0, 14000.0), swish=0.01),
    "gourd": dict(shell=((3200.0, 5.5, 1.0), (6800.0, 3.0, 0.3)), count=(25, 70), each=40.0, click=0.45,
                  direct=0.2, tau=0.025, attack=0.003, gamma=1.5, bright=(2000.0, 10000.0), swish=0.02),
    "tube": dict(shell=((2400.0, 4.0, 0.7), (6200.0, 3.0, 1.0), (11000.0, 3.0, 0.5)), count=(200, 500), each=25.0,
                 click=0.2, direct=0.4, tau=0.045, attack=0.006, gamma=2.0, bright=(2500.0, 12000.0), swish=0.06),
}


def _shaker(make: np.random.Generator, size: float, bright: float, wear: float) -> dict:
    kind = ("egg", "gourd", "tube")[int(make.choice(3, p=[0.4, 0.3, 0.3]))]
    k = KINDS[kind]
    lo, hi = k["count"]
    tune = 2.0 ** make.uniform(-0.25, 0.25) / size
    shell = np.array(k["shell"])
    return dict(
        kind=kind,
        shell=(shell[:, 0] * tune * np.exp(make.normal(0.0, 0.05, len(shell))),
               shell[:, 1] * (1.0 - 0.3 * wear) * np.exp(make.normal(0.0, 0.1, len(shell))), shell[:, 2]),
        rate=float(make.integers(lo, hi + 1)) * k["each"], click=k["click"] * np.exp(make.normal(0.0, 0.1)),
        direct=k["direct"], tau=k["tau"] * np.exp(make.normal(0.0, 0.1)) * (1.0 + 0.4 * wear),
        attack=k["attack"], gamma=k["gamma"], swish=k["swish"],
        bright=(k["bright"][0] * (0.7 + 0.6 * bright), k["bright"][1] * (0.6 + 0.8 * bright)),
        seed=int(make.integers(1 << 62)),
    )


def _shake(sh: dict, energy: np.ndarray, length: int, rng: np.random.Generator, sr: int) -> np.ndarray:
    return collide(energy, length, rng, rate=sh["rate"], gamma=sh["gamma"], click_ms=sh["click"],
                   bright=sh["bright"], shell=sh["shell"], direct=sh["direct"], sr=sr)


def _strokes(sh: dict, t0: float, fwd: bool, peak: float, rng: np.random.Generator, moving: bool = False) -> tuple:
    """One stroke: forward, the beads thrown at the far end at once (accented, sharp; if the shaker was
    already moving, the grains' swish leads into it); back, softer and slower to gather."""
    if fwd:
        return (t0, peak * np.exp(rng.normal(0.0, 0.1)), sh["attack"], sh["tau"] * np.exp(rng.normal(0.0, 0.1)),
                sh["swish"] if moving else 0.0)
    return (t0, 0.45 * peak * np.exp(rng.normal(0.0, 0.1)), 2.0 * sh["attack"], 1.2 * sh["tau"], 0.0)


def _unit(sh: dict, sr: int) -> float:
    """The gain that puts a steady sixteenth-note part at full velocity (100 BPM, forward and back) at the
    K-weighted loudness a stroke's first 30 ms would have at unit level, whatever the kind: played with the
    instrument's own generator, as its maker would try it."""
    rng = np.random.default_rng(sh["seed"])
    strokes = [_strokes(sh, 0.05 + 0.15 * i, i % 2 == 0, 1.0, rng, i > 0) for i in range(16)]
    length = int(2.8 * sr)
    y = _shake(sh, _energy((strokes, []), length, sr), length, rng, sr)
    return 1.0 / np.sqrt(early_power(y[int(0.05 * sr):], sr, 2.4) + 1e-30)


def shaker(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator, s: dict) -> np.ndarray:
    bright, wear, size = _knobs(s)
    sh = _shaker(make, size, bright, wear)
    unit = _unit(sh, sr)
    notes = _playing(notes, length, sr)
    strokes, held, last = [], [], -1.0
    jitter = 0.0015 + 0.005 * wear
    for note, fwd in zip(notes, _forward(notes, s)):
        peak = vel_gain(note.vel)  # the impacts' power grows as the energy**1.5
        t0 = note.start + late(rng, jitter)
        if note.art == "shaker-roll":  # shaken fast and steadily: the beads never settle
            count = max(1, int(note.dur * 13.0))
            for i in range(count):
                t = t0 + i * note.dur / count + late(rng, 0.004)
                strokes.append((t, 0.35 * peak * (1.0 if i % 2 == 0 else 0.75), 1.5 * sh["attack"], 0.8 * sh["tau"],
                                0.0))
            held.append((t0, t0 + note.dur, 0.35 * peak, sh["tau"]))
        else:
            strokes.append(_strokes(sh, t0, fwd, peak, rng, note.start - last < 0.45))
        last = note.start
    if not strokes:
        return np.zeros(length)
    y = _shake(sh, _energy((strokes, held), length, sr), length, rng, sr) * unit * EARLY
    return sosfilt(_below(sr), y)


@lru_cache(maxsize=4)
def _below(sr: int) -> np.ndarray:
    """Nothing a shaker or a tambourine makes lies under 150 Hz but a drift of the noise's mean."""
    return butter(2, 150.0, btype="highpass", fs=sr, output="sos")


# --- the tambourine ---------------------------------------------------------------------------


DISC = np.array([1.0, 1.73, 2.33, 3.91, 6.30])  # a free circular plate's modes against its lowest
CRASH = 0.25  # seconds of a palm stroke that set its level: the jingles' crash, the thump and the knock alike


def _tambourine(make: np.random.Generator, size: float, bright: float, wear: float) -> dict:
    across = 0.254 * 2.0 ** make.uniform(-0.2, 0.2) * size  # metres
    headed = bool(make.random() < 0.5)
    pairs = int(make.integers(4, 9))
    base = 3200.0 * 2.0 ** make.uniform(-0.3, 0.3)  # a disc's lowest mode
    metal = (60.0 - 30.0 * bright) * 1e-6  # seconds: a jingle meeting its pair, brass or steel
    freqs, t60s, gains, tilts, starts = [], [], [], [], [0]
    for _ in range(pairs):
        f_pair = base * np.exp(make.normal(0.0, 0.05))
        for _disc in range(2):
            f = f_pair * np.exp(make.normal(0.0, 0.02 + 0.03 * wear)) * DISC * np.exp(make.normal(0.0, 0.02, len(DISC)))
            freqs.extend(f)
            t60s.extend(0.35 * (base / f) ** 0.6 * np.exp(make.normal(0.0, 0.2, len(DISC))) * (1.0 - 0.3 * wear))
            # a small disc radiates its low bending modes poorly (rising 12 dB an octave to about 5 kHz), and the
            # metal contact passes little past 1/(2 tau)
            x = f / 5000.0
            gains.extend(x**2 / (1.0 + x**2) * contact(f, metal) * make.uniform(0.5, 1.0, len(DISC)))
            tilts.extend(0.5 * np.log2(DISC))  # a softer collision reaches the higher modes less
        starts.append(len(freqs))
    # the skin: an ideal membrane's modes up to about six times its lowest
    skin = 300.0 * 2.0 ** make.uniform(-0.3, 0.3) * 0.254 / across
    membrane = [(m, j) for m, n, j in MEMBRANE if j < 6.0 * MEMBRANE[0][2]]
    # the frame's hoop, knocked: a few heavily damped modes
    hoop = np.array([420.0, 1100.0, 2300.0]) * 2.0 ** make.uniform(-0.2, 0.2, 3) * 0.254 / across
    return dict(
        headed=headed, pairs=pairs,
        jingles=(np.array(freqs), np.array(t60s), np.array(gains), np.array(tilts), starts),
        shell=((2300.0 * 2.0 ** make.uniform(-0.2, 0.2) * 0.254 / across,), (4.0,), (0.3,)),
        rate=pairs * make.uniform(200.0, 300.0), tau=make.uniform(0.07, 0.1) * (1.0 + 0.5 * wear),
        skin=np.array([skin * j / MEMBRANE[0][2] for m, j in membrane]),
        skin_m=np.array([m for m, j in membrane]), skin_j=np.array([j for m, j in membrane]),
        skin_t60=0.18 * np.exp(make.normal(0.0, 0.1)),
        hoop=hoop, hoop_t60=np.array([0.07, 0.05, 0.04]) * np.exp(make.normal(0.0, 0.15, 3)),
        thump=float(make.uniform(0.4, 0.6)) if headed else 0.0, knock=float(make.uniform(0.25, 0.4)),
        seed=int(make.integers(1 << 62)),
    )


def _jingle(tb: dict, energy: np.ndarray, length: int, rng: np.random.Generator, sr: int, bright: float) -> np.ndarray:
    return collide(energy, length, rng, rate=tb["rate"], gamma=1.5, click_ms=0.15,
                   bright=(4000.0, 9000.0 + 8000.0 * bright), shell=tb["shell"], direct=0.15,
                   modes=tb["jingles"], kick=1.0, sr=sr)


PALM = 0.0005  # seconds: a palm's stroke throws the jingles at once
# a drummer's strokes, as a tambourine player would take them: a hi-hat's are shaken, a ghost's tapped
KIT = {"hat": "tambourine-shake", "hat-open": "tambourine-shake", "shaker": "tambourine-shake",
       "ghost": "tambourine-tap", "brush-tap": "tambourine-tap"}


def _crash(tb: dict, sr: int, bright: float) -> float:
    """The gain that puts a full-velocity palm stroke's crash of jingles at unit K-weighted loudness over
    its first quarter second, whatever the maker's jingles: measured by playing six strokes on the
    instrument with its own generator."""
    reference = [(0.05 + 0.4 * i, 1.0, PALM, tb["tau"], 0.0) for i in range(6)]
    probe = int(2.6 * sr)
    y = _jingle(tb, _energy((reference, []), probe, sr), probe, np.random.default_rng(tb["seed"]), sr, bright)
    return 1.0 / np.sqrt(np.mean([early_power(y[int(t * sr):], sr, CRASH) for t, *_ in reference]) + 1e-30)


def tambourine(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
               s: dict) -> np.ndarray:
    bright, wear, size = _knobs(s)
    tb = _tambourine(make, size, bright, wear)
    unit = _crash(tb, sr, bright)
    # the struck part: the skin (if any) and the hoop, levelled against the jingles' crash
    freqs = np.concatenate([tb["skin"] if tb["headed"] else np.zeros(0), tb["hoop"]])
    t60s = np.concatenate([tb["skin_t60"] * (tb["skin"][0] / tb["skin"]) ** 0.7 if tb["headed"] else np.zeros(0),
                           tb["hoop_t60"]])
    heard = modal_weights(freqs, t60s, sr, CRASH)
    ks = len(tb["skin"]) if tb["headed"] else 0
    share = 1.0 / np.sqrt(1.0 + tb["thump"] ** 2 + tb["knock"] ** 2)  # the jingles' part of a palm stroke
    strokes, held, times, rows = [], [], [], []
    jitter = 0.002 + 0.006 * wear
    for note in _playing(notes, length, sr):
        art = note.art if note.art in SPEC["tambourine"]["articulations"] else KIT.get(note.art, "tambourine")
        peak = vel_gain(note.vel)  # the jingles' power grows as the energy**1.5
        t0 = note.start + late(rng, jitter)
        if art == "tambourine":
            strokes.append((t0, peak * share ** (4.0 / 3.0) * np.exp(rng.normal(0.0, 0.1)), PALM, tb["tau"], 0.0))
            loud = EARLY * share * peak**0.75  # as loud as the jingles' crash grows
            palm = (4.0 - 2.0 * note.vel) * 1e-3 * (1.2 - 0.4 * bright)  # a soft, broad contact
            amp = np.zeros(len(freqs))
            if tb["headed"]:  # where the palm lands: off the middle, at some angle
                r, theta = rng.uniform(0.3, 0.7), rng.uniform(0.0, np.pi)
                amp[:ks] = jv(tb["skin_m"], tb["skin_j"] * r) * np.cos(tb["skin_m"] * theta) \
                    * contact(freqs[:ks], palm) * rng.uniform(0.8, 1.2, ks)
                amp[:ks] *= tb["thump"] * loud / np.sqrt(float(amp[:ks] ** 2 @ heard[:ks]) + 1e-30)
            knock = rng.uniform(0.6, 1.0, 3) * contact(freqs[ks:], 0.6e-3)
            amp[ks:] = knock * tb["knock"] * loud / np.sqrt(float(knock**2 @ heard[ks:]) + 1e-30)
            times.append(t0)
            rows.append(amp)
        elif art == "tambourine-tap":  # a fingertip: a few jingles stir
            strokes.append((t0, 0.25 * peak * np.exp(rng.normal(0.0, 0.1)), 0.001, 0.5 * tb["tau"], 0.0))
        elif art == "tambourine-roll":  # the thumb skidding round the head
            count = max(1, int(note.dur * rng.uniform(22.0, 28.0)))
            for i in range(count):
                strokes.append((t0 + i * note.dur / count, 0.3 * peak * rng.uniform(0.7, 1.0), 0.001, 0.02, 0.0))
            held.append((t0, t0 + note.dur, 0.25 * peak, 0.5 * tb["tau"]))
        else:  # shaken: one flick, or a shake held for the note
            rate = rng.uniform(9.0, 11.0)
            count = max(1, int(round(note.dur * rate))) if note.dur > 0.2 else 1
            for i in range(count):
                strokes.append((t0 + i / rate + late(rng, 0.004), peak * (1.0 if i % 2 == 0 else 0.7),
                                0.003, 0.45 * tb["tau"], 0.0))
            if count > 1:
                held.append((t0, t0 + count / rate, 0.1 * peak, 0.5 * tb["tau"]))
    out = np.zeros(length)
    if strokes:
        out += _jingle(tb, _energy((strokes, held), length, sr), length, rng, sr, bright) * unit * EARLY
    if times:
        out += struck.ring(freqs, t60s, times, np.array(rows), sr, length)
    return sosfilt(_skin_floor(sr), out)


@lru_cache(maxsize=4)
def _skin_floor(sr: int) -> np.ndarray:
    """Under the skin's lowest mode there is nothing but the drift of its strokes' mean."""
    return butter(2, 80.0, btype="highpass", fs=sr, output="sos")
