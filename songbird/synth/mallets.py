"""Mallets: struck bars and a plucked comb (vibraphone, marimba, glockenspiel, celesta, music box).

A bar rings in bending modes. A free bar of even section has them at
1 : 2.756 : 5.404 : 8.933 (a glockenspiel's steel bars, a celesta's
plates), a little lower in a short thick bar, where shear and rotary
inertia soften it (Timoshenko): a glockenspiel's G5 bar measures
1 : 2.74 : 5.31, its C8 1 : 2.67 : 4.97. A marimba's and a vibraphone's
bars are undercut, thinned beneath their middles until the second mode sits
two octaves over the first and the third three octaves and a third
(1 : 4 : 10); a marimba's top bars are too short to tune the third, which
falls toward 9.2. Where a mallet lands decides which modes speak: the
second is antisymmetric, silent at the centre, so players strike 5 to 15%
off it (each stroke somewhere in that range, the modes' shapes weighting
them); the third has an antinode there. Off the bar's axis a stroke also
twists it (a torsional mode, a few times the fundamental, weak).

The mallet pushes for a few milliseconds. Its force is a smooth pulse,
(t/b)^a e^(-t/b) with b = τ/π, whose spectrum is flat to about 1/2τ and
falls 6(a + 1) dB an octave above, without the deep notches of a perfectly
springy contact (a covering gives back less than it takes). Yarn on a
marimba touches 5 ms at A2 to 1.1 ms at C7 at mf, cord on a vibraphone 2 to
1 ms, felt on a celesta 2 to 0.9 ms, brass or hard plastic on a
glockenspiel 0.5 to 0.25 ms. A harder stroke squeezes the stiffening
covering further: the contact shortens as speed^-0.5 (a covering
stiffening as x^3; a glockenspiel's hard head, a Hertzian contact, only as
speed^-0.2), and its packed fibres make the force rise more sharply
(a from 1.6 at pp to 0.2 at ff for yarn). So louder is shorter and
brighter: from pp to ff a marimba's fourth partial gains 8 to 9 dB on its
fundamental and its tenth 13 to 20. brightness is the mallet's hardness:
the contact 1.5 times longer at 0 (soft yarn), 0.6 times at 1 (hard). The
force drives every mode through modal.ring, so each builds up from rest; a
mode far above the pulse's reach follows the push and gives it back, and
since what radiates is the bar's acceleration (F - ω² x), that share is
taken out while the mallet touches. Each mode is heard as fast as it moves
(a push J leaves mode k moving at J φk / m), and radiated as a dipole below
a corner set by the bar's width (2 kHz for a marimba's), fully above it.
Loudness follows touch.gain, 20 dB from pp to ff, set on each stroke's
first 0.2 s. A chord's mallets land up to 3 ms apart.

Under a marimba's and a vibraphone's bars hang tubes tuned to the
fundamental, and under a celesta's plates wooden boxes. A resonator is a
second mode coupled to the bar's first: the coupling shortens the bar's
ring (a marimba's A2 from 3.2 s bare to 2.0 s), and the air column
radiates what the bar, a poor dipole, cannot: it lifts the fundamental 26
dB at A2 and 11 at C7. The tube starts at rest, so the fundamental blooms:
A2 reaches its peak about 0.2 s after the stroke, C5 in 40 ms, while the
upper partials sound at once. A mode k rings T60_1 (f1 / fk)^1.2 (the
marimba's A#4: fundamental 1.06 s, fourth partial 0.32 s, tenth 0.11 s).

marimba: rosewood bars, A2 to C7; the fundamental rings 2.0 s at A2, 1.1 at
A4, 0.3 at C7. At mf the attack's fourth partial sits 11 dB under the
fundamental's peak at A2, 16 at D4, 19 at G5, 25 at C7; the tenth 16, 26,
35 dB under. No damper: "dead" holds the mallet on the bar (the fundamental
falls 40 dB in 0.1 s); "roll" spells out a two-mallet roll, 8.7 strokes a
second in the bass to 15.6 at the top (faster when louder), the hands
alternating sides of the centre, each stroke lighter the more the bar
builds up, so a roll sounds at its note's loudness.

vibraphone: aluminium bars, F3 to F6, rings 13 s at F3 to 3.5 s at F6. The
pedal: a note's length is how long before the damper lands, then it dies
with T60 0.2 s at F3 to 0.1 s at F6. The motor turns one shaft of discs
across every tube's mouth, so its phase runs through the whole part; each
disc opens and closes its tube twice a turn: what the tube adds to the
fundamental swings 11 dB, the note 9 dB (the bar's own sound, a quarter
cycle apart, fills the dips and turns part of the swing into pitch, ±2 to 3
cents). Its speed: 2.5 + 4 × ornament Hz (4.5 at 0.5), off at 0, the discs'
swing growing to its full depth by 0.2, so a drifting ornament never flips
it on and off; "motor-slow" (3.5 Hz), "motor-fast" (6.5 Hz), "motor-off"
from a note on, the motor taking 0.4 s to change speed; each machine's
motor runs a few per cent fast or slow.

glockenspiel: steel bars 25 × 7 mm, G5 to C8 sounding, no resonators (the
case baffles them: corner 1.5 kHz), no damper: they ring 5 s at G5 to 3 s
at C8 whatever the written length, unless "choke" (the hand, at the note's
end). The torsional mode falls from 4.7 times the fundamental at G5 to 2.1
at C8, where the bars are short and thick against their width.

celesta: steel plates 30 × 4 mm over tuned wooden boxes (26 dB at C4, 12 at
C8), C4 to C8, felt hammers from a keyboard striking each plate 13% off
centre, where its third mode is nearly silent: a strong, soft fundamental
ringing 2.0 s at C4 to 1.0 s at C8, the 2.75 partial 17 to 23 dB under it
at mf. Dampers like a piano's (T60 0.25 s at C4 to 0.12 s at C8); "ped"
lets a plate ring on. The action knocks, and the cabinet is a small body.

music-box: a steel comb, C5 to C8, its teeth cantilevers (1 : 6.27 :
17.55). The bass teeth, below C6, carry lead lumps under their tips, up to
twice the tooth's mass: a lump that rocks brings the second mode down to
about 4.7 (a point mass alone would raise it; see weighted_tooth). A pin
bends a tooth and lets go: released from a bend, mode k holds φk(tip)/ωk²
of it (the second mode's swing 32 dB under the first's), but what the box hears is the
tooth's root, its moment and shear, which gives the second mode 11 dB under
the first and the third 17; the tip snaps off in 25 µs (no contact filter)
with a tick of the pin. Teeth ring 4 s at C5 to 2 s at C8. When a tooth
still sounding is plucked again, its damper (in the bass, 25 ms ahead of
the pin) or the pin itself (above, 6 ms) stops it with a short buzz, its
swing slapping the damper. The comb is screwed to a small wooden box
(body.Body) whose thin panels radiate little below 300 Hz and give it a
narrow stereo image. The pins pluck alike: velocity moves it 4 dB at most.

make gives each machine its instrument: each bar's tuning (within 1 cent at
wear 0), its tuned modes within 3 cents of 4 and 10, the untuned ones
wider, where each resonator is tuned, which few bars sit loose, the motor's
speed and the discs' fit, the boxes' modes. wear pulls bars and teeth off
pitch (8 cents at wear 1 for metal, 20 for wood and an old comb), detunes the
resonators (up to 40 cents: less lift, a different ring), loosens the dampers,
and makes the loose bars buzz on their posts (35 dB under the note at wear
0.25, 25 at 1). body sizes the music box's and the celesta's boxes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.signal import lfilter, oaconvolve, sosfilt

from . import body, modal, touch
from .iir import butter

SPEC = {
    "vibraphone": dict(
        family="mallets",
        role="comping",
        register=(53, 89),
        place=(-0.25, 0.7),
        level=0.87,
        poly=True,
        articulations={
            "": "struck with a cord mallet, the pedal down while the note lasts: the damper lands at its end "
                "(write long notes to let them ring)",
            "dead": "a dead stroke: the mallet stays pressed on the bar, short and muffled",
            "roll": "a two-mallet roll for the note's length",
            "motor-off": "stop the motor from this note on (the discs are left open); joins others with +",
            "motor-slow": "the motor on, slow (about 3.5 Hz), from this note on",
            "motor-fast": "the motor on, fast (about 6.5 Hz), from this note on",
        },
        about="a vibraphone: aluminium bars tuned 1:4:10 over tube resonators whose motor-driven discs "
              "make its tremolo (from ornament: off at 0, 4.5 Hz at 0.5), a damper pedal, cord mallets",
        brighter=0.3,  # its upper partials ring for seconds, so the centroid of 0.1-0.4 s moves (0.39 octave)
    ),
    "marimba": dict(
        family="mallets",
        role="comping",
        register=(45, 96),
        place=(0.2, 0.8),
        level=0.97,
        poly=True,
        articulations={
            "": "struck with a yarn mallet and left to ring (a marimba has no damper)",
            "dead": "a dead stroke: the mallet stays pressed on the bar, short and muffled",
            "roll": "a two-mallet roll for the note's length, as long notes are played",
        },
        about="a concert marimba: rosewood bars undercut to 1:4:10 over tube resonators, yarn mallets",
        # no brighter: a hard stroke's fourth and tenth partials gain 8 and 15 dB on the fundamental, but they
        # die within 0.1-0.3 s, so the centroid of 0.1-0.4 s after the stroke barely moves (0.003 octave)
    ),
    "glockenspiel": dict(
        family="mallets",
        role="colour",
        register=(79, 108),
        place=(0.4, 0.3),
        level=0.76,
        poly=True,
        articulations={
            "": "struck and left to ring (a glockenspiel has no damper: the written length doesn't matter)",
            "choke": "stopped by the hand at the note's end",
            "roll": "a roll for the note's length",
        },
        about="orchestral bells: steel bars (sounding G5 to C8), brass (bright) to plastic (soft) mallets",
        brighter=0.03,  # a hard mallet's contact barely shortens when struck harder (0.04 octave)
    ),
    "celesta": dict(
        family="mallets",
        role="colour",
        register=(60, 108),
        place=(-0.4, 0.4),
        level=1.19,
        poly=True,
        articulations={
            "": "a key held for the note's length: the damper lands at its end",
            "ped": "with the sustain pedal: the plate rings on whatever the written length",
        },
        about="a celesta: steel plates over tuned wooden resonators, struck by felt hammers from a keyboard",
        # no brighter: its partials sit 17-23 dB under a resonated fundamental; the centroid moves 0.001 octave
    ),
    "music-box": dict(
        family="mallets",
        role="colour",
        register=(72, 108),
        place=(0.3, 0.3),
        level=0.58,
        poly=True,
        articulations={"": "a pin plucks the tooth, which rings until it is plucked again"},
        about="a music box: a steel comb plucked by a cylinder's pins, in a small wooden box; mechanical, "
              "so velocity moves it only a little",
        dynamic=False,
    ),
}


def _interp(m, table):
    xs, ys = zip(*table)
    return float(np.interp(m, xs, ys))


def _log_interp(m, table):
    xs, ys = zip(*table)
    return float(np.exp(np.interp(m, xs, np.log(ys))))


def _hz(m: float) -> float:
    return 440.0 * 2.0 ** ((m - 69.0) / 12.0)


# --- beams ---------------------------------------------------------------------------------------

FREE_FREE = (4.730040745, 7.853204624, 10.995607838, 14.137165491)  # βL of a free-free bar's bending modes


def free_free(k: int, x: float) -> float:
    """A free-free bar's k-th bending mode (k from 0) at x (0..1 along it): 2 at the ends, unit mean square.
    At the centre the first is -1.22, the second 0 (a node), the third 1.42."""
    b = FREE_FREE[k]
    s = (np.cosh(b) - np.cos(b)) / (np.sinh(b) - np.sin(b))
    return float(np.cosh(b * x) + np.cos(b * x) - s * (np.sinh(b * x) + np.sin(b * x)))


def thick_bar(f1: float, thick: float, wide: float, c_long: float = 5050.0, c_shear: float = 3170.0):
    """A rectangular bar of steel (by default) whose fundamental is f1: its bending modes' ratios, lowered from the
    thin bar's 1 : 2.756 : 5.404 : 8.933 by shear and rotary inertia (Timoshenko, to first order), and its first two
    torsional modes' ratios. thick, wide: the section (m)."""
    length = np.sqrt(FREE_FREE[0] ** 2 * thick * c_long / (2.0 * np.pi * np.sqrt(12.0) * f1))
    r = thick / np.sqrt(12.0) / length  # radius of gyration over length
    shear = 3.12  # E / (κ G) for steel, κ = 5/6

    def lowered(b):
        return 1.0 / np.sqrt(1.0 + (b * r) ** 2 * (1.0 + shear))

    bend = [(b / FREE_FREE[0]) ** 2 * lowered(b) / lowered(FREE_FREE[0]) for b in FREE_FREE]
    # torsion: f = n c_T / 2L, c_T = c_shear sqrt(J / I_p) (Roark's J for a rectangle)
    q = thick / wide
    j = wide * thick**3 * (1.0 / 3.0 - 0.21 * q * (1.0 - q**4 / 12.0))
    ip = wide * thick * (wide**2 + thick**2) / 12.0
    c_t = c_shear * np.sqrt(j / ip)
    twist = [n * c_t / (2.0 * length) / f1 for n in (1, 2)]  # the tuner cuts the bar to f1
    return np.array(bend), np.array(twist)


@lru_cache(maxsize=64)
def weighted_tooth(mass: float, inertia: float) -> tuple[float, float, float]:
    """βL of the first three modes of a cantilever with a lump at its tip: mass (times the tooth's) and rotary
    inertia (times the tooth's mass times its length squared). A point mass alone raises the second mode's ratio
    (1 : 10.4 with the tooth's own mass); a lump that rocks, as a music box's lead weight does, lowers it."""
    def det(b):
        ch, sh, c, s = np.cosh(b), np.sinh(b), np.cos(b), np.sin(b)
        a11 = (sh - s) + mass * b * (ch - c)
        a12 = (ch + c) + mass * b * (sh - s)
        a21 = (ch + c) - inertia * b**3 * (sh + s)
        a22 = (sh + s) - inertia * b**3 * (ch - c)
        return (a11 * a22 - a12 * a21) / np.cosh(b) ** 2

    grid = np.linspace(0.05, 14.0, 14000)
    d = det(grid)
    found = []
    for i in np.flatnonzero(np.sign(d[:-1]) != np.sign(d[1:])):
        lo, hi = grid[i], grid[i + 1]
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if np.sign(det(lo)) == np.sign(det(mid)):
                lo = mid
            else:
                hi = mid
        found.append(0.5 * (lo + hi))
        if len(found) == 3:
            break
    return tuple(found)


# --- mallets -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Mallet:
    """A mallet or hammer: how long it touches the bar, and how that changes with the stroke and the mallet."""
    tau: tuple  # the contact time (s) of a stroke at mf, by pitch (the knee of its spectrum is near 1/2τ)
    stiffening: float  # p: the covering stiffens as x^p, so the contact time goes as speed^((1 - p) / (1 + p))
    onset: tuple  # the force's rise, t^a, for the softest stroke and the hardest (packed covering: sharper)
    soft: float  # the contact time at brightness 0 against 0.5 (the softest mallets the player owns)
    hard: float  # and at brightness 1 (the hardest)


FINE = 16  # the pulse is drawn at 16 times the sample rate and averaged down


def _gamma(tau: float, a: float, sr: int) -> np.ndarray:
    """(t/b)^a e^(-t/b), b = τ/π, averaged to sr and summing to 1."""
    b = tau / np.pi
    n = int(np.ceil((a + 12.0) * b * sr)) + 1
    t = (np.arange(n * FINE) + 0.5) / (sr * FINE)
    coarse = ((t / b) ** a * np.exp(-t / b)).reshape(n, FINE).mean(axis=1)
    return coarse / coarse.sum()


def pulse(mallet: Mallet, m: float, vel: float, brightness: float, sr: int, span: float,
          scale: float = 1.0) -> tuple[np.ndarray, float]:
    """The mallet's force on the bar, one value per sample at sr summing to 1, and its contact time τ (s).

    A covered mallet's force rises quickly as the covering meets the bar and falls away more slowly as it
    lets go (it gives back less than it took), so its spectrum has no deep notches: the pulse is
    (t/b)^a e^(-t/b) with b = τ/π, flat to about 1/2τ and falling 6(a + 1) dB an octave above. The stroke's
    speed goes with its loudness (touch.gain); a faster stroke squeezes the stiffening covering harder and
    leaves sooner, and packs its fibres onto the core, so its force rises more sharply (a smaller a) and
    reaches further up: louder is shorter and brighter, and it is what sounds the upper modes, the click."""
    hard = mallet.soft ** (1.0 - 2.0 * brightness) if brightness < 0.5 else mallet.hard ** (2.0 * brightness - 1.0)
    speed = touch.gain(vel, span) / touch.gain(0.6, span)
    p = mallet.stiffening
    tau = _log_interp(m, mallet.tau) * hard * scale * speed ** ((1.0 - p) / (1.0 + p))
    a = mallet.onset[0] + (mallet.onset[1] - mallet.onset[0]) * float(np.clip(vel, 0.0, 1.0))
    return _gamma(tau, max(a * hard**0.5, 0.2), sr), tau


# --- bars ----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Bars:
    """One kind of struck-bar instrument: its compass, its bars' modes and decays, its resonators and mallets."""
    low: int
    high: int
    upper: tuple  # per bending mode above the first: a table of its ratio to the fundamental, by pitch
    twist: tuple  # the first torsional mode's ratio, by pitch
    tuned: int  # how many of the upper modes the tuner tunes (the rest vary bar to bar)
    t60: tuple  # the fundamental's T60 (s), with its resonator where it has one
    bare: float  # how much longer the bar's fundamental would ring without its resonator
    loss: float  # a mode rings T60_1 (f1 / f)^loss: the upper ones die fast
    corner: float  # Hz: below it the bar radiates as a dipole, 12 dB an octave weaker
    tube_q: tuple | None  # the resonators' Q by pitch (None: none)
    boost: tuple | None  # dB the resonator adds to the fundamental, by pitch
    mallet: Mallet
    strike: tuple  # the strike's distance from the bar's centre, as a fraction of its length: (least, most)
    lateral: float  # the strike's spread across the bar (fraction of its half width): what twists it
    damped: tuple | None  # T60 (s) of the fundamental under the damper, by pitch
    span: float  # dB from pp to ff (touch.gain)
    spread: float  # how far the compass spreads across the stereo image
    tuning: tuple  # cents: a bar's tuning error at wear 0, and added at wear 1
    roll: tuple  # a roll's strokes per second, by pitch
    voicing: tuple = (0.0, 0.0, 0.0, 0.0)  # dB: the maker's voicing of the upper bending modes and the twist


def _table(pitches, values):
    return tuple(zip([float(p) for p in pitches], [float(v) for v in values]))


def _steel_tables(low, high, thick, wide):
    """Upper bending-mode and torsion tables for uncut steel bars of one section across a compass."""
    grid = np.arange(low, high + 1, 3)
    rows = [thick_bar(_hz(m), thick, wide) for m in grid]
    upper = tuple(_table(grid, [r[0][k] for r in rows]) for k in (1, 2, 3))
    twist = _table(grid, [r[1][0] for r in rows])
    return upper, twist


MARIMBA = Bars(
    low=45, high=96,
    # undercut to 1:4:10; the top bars are too short to tune the third mode, which falls toward 9.2
    upper=(((45, 4.0), (96, 4.0)), ((45, 10.0), (74, 10.0), (84, 9.6), (96, 9.2)), ((45, 19.0), (96, 16.0))),
    twist=((45, 6.3), (96, 4.9)),
    tuned=2,
    t60=((45, 2.0), (57, 1.6), (69, 1.1), (81, 0.65), (96, 0.3)),
    bare=1.6, loss=1.2, corner=2000.0,
    tube_q=((45, 35.0), (96, 15.0)),
    boost=((45, 26.0), (57, 25.0), (69, 20.0), (81, 15.0), (96, 11.0)),
    mallet=Mallet(tau=((45, 5.0e-3), (60, 3.5e-3), (72, 2.5e-3), (84, 1.6e-3), (96, 1.1e-3)), stiffening=3.0,
                  onset=(1.6, 0.2), soft=1.5, hard=0.6),
    strike=(0.05, 0.15), lateral=0.15,
    damped=((45, 0.12), (96, 0.08)),
    span=20.0, spread=0.6, tuning=(0.4, 8.0),
    roll=((45, 8.0), (96, 16.0)),
    voicing=(0.0, -2.0, -12.0, 0.0),
)

VIBRAPHONE = Bars(
    low=53, high=89,
    upper=(((53, 4.0), (89, 4.0)), ((53, 10.0), (77, 10.0), (89, 9.5)), ((53, 19.0), (89, 16.5))),
    twist=((53, 7.3), (89, 5.4)),
    tuned=2,
    t60=((53, 13.0), (65, 9.5), (77, 6.0), (89, 3.5)),
    bare=1.4, loss=1.2, corner=2200.0,
    tube_q=((53, 40.0), (89, 20.0)),
    boost=((53, 20.0), (65, 18.5), (77, 14.0), (89, 12.4)),
    mallet=Mallet(tau=((53, 2.0e-3), (71, 1.5e-3), (89, 1.0e-3)), stiffening=3.0, onset=(1.5, 0.1),
                  soft=1.5, hard=0.6),
    strike=(0.05, 0.15), lateral=0.15,
    damped=((53, 0.2), (89, 0.1)),
    span=20.0, spread=0.5, tuning=(0.3, 3.0),
    roll=((53, 7.0), (89, 11.0)),
    voicing=(0.0, 0.0, -10.0, 0.0),
)

_GLOCK_UPPER, _GLOCK_TWIST = _steel_tables(79, 108, 0.007, 0.025)
GLOCKENSPIEL = Bars(
    low=79, high=108,
    upper=_GLOCK_UPPER, twist=_GLOCK_TWIST, tuned=0,
    t60=((79, 5.0), (91, 4.2), (103, 3.3), (108, 3.0)),
    bare=1.0, loss=0.8, corner=1500.0,
    tube_q=None, boost=None,
    mallet=Mallet(tau=((79, 0.5e-3), (108, 0.25e-3)), stiffening=1.5, onset=(1.2, 0.7),
                  soft=1.6, hard=0.6),
    strike=(0.0, 0.08), lateral=0.2,
    damped=((79, 0.08), (108, 0.06)),
    span=20.0, spread=0.3, tuning=(0.3, 3.0),
    roll=((79, 14.0), (108, 18.0)),
)

_CELESTA_UPPER, _CELESTA_TWIST = _steel_tables(60, 108, 0.004, 0.03)
CELESTA = Bars(
    low=60, high=108,
    upper=_CELESTA_UPPER, twist=_CELESTA_TWIST, tuned=0,
    t60=((60, 2.0), (84, 1.5), (108, 1.0)),
    bare=1.8, loss=1.0, corner=3600.0,
    tube_q=((60, 20.0), (108, 10.0)),
    boost=((60, 26.0), (84, 20.0), (108, 12.0)),
    mallet=Mallet(tau=((60, 2.0e-3), (84, 1.4e-3), (108, 0.9e-3)), stiffening=3.0, onset=(1.9, 0.5),
                  soft=1.5, hard=0.65),
    strike=(0.12, 0.14), lateral=0.1,
    damped=((60, 0.25), (108, 0.12)),
    span=20.0, spread=0.25, tuning=(0.3, 4.0),
    roll=((60, 12.0), (108, 16.0)),
    voicing=(0.0, 0.0, -10.0, 0.0),
)

BARS = {"vibraphone": VIBRAPHONE, "marimba": MARIMBA, "glockenspiel": GLOCKENSPIEL, "celesta": CELESTA}

CELESTA_CASE = body.Body(  # a celesta's cabinet: a small upright's case, a little wood around the plates
    modes=((180.0, 10.0, 2.0), (310.0, 14.0, 3.0), (520.0, 16.0, 2.5), (870.0, 18.0, 1.5)),
    dense=(900.0, 9000.0, 70), tilt=-1.5, q=(26.0, 16.0), direct=0.5, lowcut=150.0, highcut=9000.0, length=0.3,
)


def _radiation(f, corner):
    """How well a bar radiates at f: as a dipole (rising 12 dB an octave) below the corner, fully above."""
    x = (f / corner) ** 2
    return x / (1.0 + x)


def resonated(f1: float, t60: float, bare: float, tube_t60: float, detune: float, boost: float):
    """A bar's fundamental over its resonator: two coupled modes, the bar's and the air column's. At exact tuning
    the coupling is what shortens the bar's T60 from t60 × bare to t60; the tube radiates what boosts the
    fundamental by `boost` dB. Returns frequencies (Hz), T60s (s), and per unit push on the bar the complex
    amplitudes of what the bar radiates and what the tube does."""
    ab = modal.LN1000 / (t60 * bare)
    ae = modal.LN1000 / t60
    at = max(modal.LN1000 / tube_t60, ae * 1.05)
    kappa = np.sqrt(max((ae - ab) * (at - ae), 1e-9))
    wb = 2.0 * np.pi * f1
    wt = wb * 2.0 ** (detune / 1200.0)
    matrix = np.array([[1j * wb - ab, 1j * kappa], [1j * kappa, 1j * wt - at]])
    lam, vec = np.linalg.eig(matrix)
    coeff = np.linalg.solve(vec, np.array([1.0, 0.0], dtype=complex))
    r_tube = np.sqrt(10.0 ** (boost / 10.0) - 1.0) * (at - ae) / kappa
    from_bar = vec[0, :] * coeff
    from_tube = r_tube * vec[1, :] * coeff
    rate = -lam.real
    freqs = lam.imag / (2.0 * np.pi)
    slow = int(np.argmin(rate))
    freqs = freqs + (f1 - freqs[slow])  # the tuner tuned the bar over its resonator
    return freqs, modal.LN1000 / np.maximum(rate, 1e-6), from_bar, from_tube


class Kit:
    """One machine's instrument (from `make`): each bar's tuning, its modes' tolerances, its resonator's tuning,
    which bars are loose, the motor; set up by the band's settings."""

    def __init__(self, bars: Bars, make: np.random.Generator, settings: dict):
        self.brightness = float(np.clip(settings.get("brightness", 0.5), 0.0, 1.0))
        self.wear = float(np.clip(settings.get("wear", 0.25), 0.0, 1.0))
        self.ornament = float(np.clip(settings.get("ornament", 0.5), 0.0, 1.0))
        self.size = float(np.clip(settings.get("body", 1.0), 0.7, 1.35))
        base, worn = bars.tuning
        self.cents = np.clip(make.standard_normal(128), -3.0, 3.0) * (base + worn * self.wear)
        # the tuned modes within a few cents of 4 and 10 on a new instrument; untuned ones vary more
        self.mode_cents = make.standard_normal((128, 3)) * np.array([3.0, 3.0, 20.0]) * (1.0 + 3.0 * self.wear)
        if bars.tuned == 0:
            self.mode_cents = self.mode_cents * np.array([0.7, 0.7, 0.2])
        self.twist_cents = make.standard_normal(128) * 60.0
        self.tube_cents = make.standard_normal(128) * (6.0 + 40.0 * self.wear)
        self.loose = np.maximum(make.uniform(0.0, 1.0, 128) - 0.93, 0.0) / 0.07  # a few bars sit loose
        self.habit = make.normal(0.0, 1.0, 128)
        self.motor_rate = float(np.exp(make.normal(0.0, 0.06)))
        self.motor_phase = float(make.uniform(0.0, 2.0 * np.pi))
        self.disc_depth = float(make.normal(0.0, 1.0))
        self.seed = int(make.integers(1 << 30))


@dataclass
class Stroke:
    start: float  # s
    pitch: float
    vel: float
    until: float | None  # s after the start when the damper (or hand) lands; None: never
    dead: bool = False
    hand: int = -1  # in a roll, which mallet (each lands on its own side of the centre)


def _tokens(art: str) -> set[str]:
    return set(str(art).replace("+", " ").split())


def _within(m: float, low: float, high: float) -> float:
    """A pitch outside the compass, brought within an octave of it by octaves (a part-writer's slip)."""
    while m > high + 12.0:
        m -= 12.0
    while m < low - 12.0:
        m += 12.0
    return m


def _strokes(name: str, bars: Bars, notes, rng: np.random.Generator) -> list[Stroke]:
    """Every stroke the notes ask for: rolls spelled out, chords spread by a few milliseconds (the mallets
    don't land together), dampers where the instrument has them."""
    out = []
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    for note in ordered:
        if note.dur <= 0:
            continue
        art = _tokens(note.art)
        vel = float(np.clip(note.vel, 0.0, 1.0))
        m = _within(float(note.pitch), bars.low, bars.high)
        if name == "vibraphone":
            until = note.dur
        elif name == "celesta":
            until = None if "ped" in art else note.dur
        elif name == "glockenspiel":
            until = note.dur if "choke" in art else None
        else:
            until = None
        dead = "dead" in art
        lag = float(rng.uniform(0.0, 0.003))
        if "roll" in art and name != "celesta":
            rate = _interp(m, bars.roll) * (0.85 + 0.3 * vel)
            # a roll on a bar that rings builds up (powers add: each stroke leaves T60 / 13.8 s of its first
            # moment's power, and its attack about 35 ms more), so it is played lighter, to sound at the
            # note's loudness
            build = max(1.0, rate * (_log_interp(m, bars.t60) / (2.0 * modal.LN1000) + 0.035))
            lighter = build ** (-0.5 / touch.exponent(bars.span))
            t, i = 0.0, 0
            while t < note.dur - 0.3 / rate or i < 2:
                v = vel * lighter * (1.0 if i == 0 else 0.88 + (0.05 if i % 2 == 0 else 0.0) + rng.normal(0.0, 0.03))
                out.append(Stroke(note.start + lag + t, m, float(np.clip(v, 0.02, 1.0)),
                                  None if until is None else max(until - t, 0.01), dead, i % 2))
                t += (1.0 / rate) * (1.0 + rng.normal(0.0, 0.05))
                i += 1
        else:
            out.append(Stroke(note.start + lag, m, vel, until, dead))
    return out


def _bar_modes(bars: Bars, kit: Kit, stroke: Stroke, rng: np.random.Generator, sr: int):
    """One stroke's modes: the force, frequencies, complex gains (the bar's and the tube's), T60s, damped T60s,
    when the damper lands (samples after the strike, -1 never), and the level scale."""
    m = stroke.pitch
    key = int(np.clip(round(m), 0, 127))
    f1 = _hz(m + kit.cents[key] / 100.0)
    # where it is struck: along the bar (off the centre, where the second mode has its node) and across
    side = (1.0 if rng.uniform() < 0.5 else -1.0) if stroke.hand < 0 else (1.0 if stroke.hand == 0 else -1.0)
    along = side * rng.uniform(*bars.strike)
    if bars is CELESTA:  # a hammer strikes each plate where the action puts it
        along = float(np.clip(0.5 * sum(bars.strike) + 0.01 * kit.habit[key], *bars.strike))
    across = rng.normal(0.0, bars.lateral)
    ratios = [1.0]
    for k, table in enumerate(bars.upper):
        ratios.append(_interp(m, table) * 2.0 ** (kit.mode_cents[key, k] / 1200.0))
    freqs = f1 * np.array(ratios)
    shapes = np.array([free_free(k, 0.5 + along) for k in range(len(ratios))])
    twist = f1 * _interp(m, bars.twist) * 2.0 ** (kit.twist_cents[key] / 1200.0)
    freqs = np.append(freqs, twist)
    shapes = np.append(shapes, 1.2 * across)  # a torsional mode is excited by striking off the bar's axis
    # what reaches the listener per unit push: each mode moves as fast as its shape at the strike (a push J
    # leaves mode k moving at J φk / m), and the bar radiates that as a dipole below the corner
    weights = shapes * _radiation(freqs, bars.corner) / _radiation(f1, bars.corner)
    weights[1:] *= 10.0 ** (np.array(bars.voicing[: len(weights) - 2] + bars.voicing[-1:]) / 20.0)
    t60_1 = _log_interp(m, bars.t60)
    bare = t60_1 * bars.bare
    t60 = bare * (f1 / freqs) ** bars.loss
    t60[0] = bare
    # the mallet
    force, contact = pulse(bars.mallet, m, stroke.vel, kit.brightness, sr, bars.span,
                           scale=1.3 if stroke.dead else 1.0)
    # the fundamental over its resonator
    tube_part = None
    if bars.tube_q is not None:
        tube_t60 = 2.2 * _interp(m, bars.tube_q) / f1
        rf, rt, from_bar, from_tube = resonated(f1, t60_1, bars.bare, tube_t60, kit.tube_cents[key],
                                                _interp(m, bars.boost))
        freqs = np.concatenate([rf, freqs[1:]])
        t60 = np.concatenate([rt, t60[1:]])
        g_bar = np.concatenate([weights[0] * from_bar, weights[1:].astype(complex)])
        g_tube = np.concatenate([weights[0] * from_tube, np.zeros(len(weights) - 1, dtype=complex)])
        tube_part = g_tube
    else:
        g_bar = weights.astype(complex)
    keep = freqs < 0.45 * sr
    # each mode takes up the push by the force's spectrum there (the sampled force is a boxcar-average)
    t = np.arange(len(force)) / sr
    drive = (force[None, :] * np.exp(-2j * np.pi * freqs[:, None] * t[None, :])).sum(axis=1)
    drive = drive / np.sinc(np.minimum(freqs / sr, 0.49))
    total = g_bar if tube_part is None else g_bar + tube_part
    reach = np.abs(total * drive) * keep
    # loudness: the mean power of the first 0.2 s, set by the touch
    rate = modal.LN1000 / t60
    power = 0.5 * reach**2 * (1.0 - np.exp(-2.0 * rate * 0.2)) / (2.0 * rate * 0.2)
    if tube_part is not None:  # the resonated fundamental: what rings on once the tube has filled
        slow = int(np.argmin(rate[:2]))
        fund = abs((g_bar[slow] + tube_part[slow]) * drive[slow])
        power[:2] = 0.0
        power[slow] = 0.5 * fund**2 * (1.0 - np.exp(-2.0 * rate[slow] * 0.2)) / (2.0 * rate[slow] * 0.2)
    level = 0.1 * touch.gain(stroke.vel, bars.span) / np.sqrt(power.sum() + 1e-30)
    # sine phase: a bar starts from rest
    gains = -1j * g_bar * level / np.sinc(np.minimum(freqs / sr, 0.49))
    tube_gains = None if tube_part is None else -1j * tube_part * level / np.sinc(np.minimum(freqs / sr, 0.49))
    # the damper, the hand or the mallet held on the bar
    damped = t60.copy()
    damp_at = -1
    if stroke.dead:
        damped = np.minimum(t60, _interp(m, bars.damped) * (f1 / freqs) ** 0.5)
        damp_at = int(round((contact + 0.004) * sr))
    elif stroke.until is not None and bars.damped is not None:
        damped = np.minimum(t60, _interp(m, bars.damped) * (1.0 + 1.5 * kit.wear) * (f1 / freqs) ** 0.5)
        damp_at = int(round(stroke.until * sr))
    peak = float(np.max(np.abs(total * drive * level)))
    quasi = _quasi(gains[keep], freqs[keep], t60[keep], force, sr)
    tube_quasi = None if tube_gains is None else _quasi(tube_gains[keep], freqs[keep], t60[keep], force, sr)
    return (force, freqs[keep], gains[keep], None if tube_gains is None else tube_gains[keep], t60[keep],
            damped[keep], damp_at, peak, f1, quasi, tube_quasi)


def _quasi(gains, freqs, t60, force, sr):
    """What to take out of the ring while the mallet touches, as weights of the force and its first two
    differences. What radiates is the bar's acceleration, F - ω² x: a mode far above the contact's reach follows
    the push while it lasts and gives it back, and its acceleration stays near zero, but the ring's output is
    ω x. A one-pole driven by F is g/(1 - m) Σj (-m/(1 - m))^j Δ^j F plus its free ring. The first term is the
    push itself, taken out of every mode; the next two are the one-pole's own error off resonance, taken out
    only where the series converges fast (the force smooth on the scale of the mode's period)."""
    pole = np.exp(-modal.LN1000 / (t60 * sr) + 2j * np.pi * freqs / sr)
    c0 = gains / (1.0 - pole)
    r = -pole / (1.0 - pole)
    smooth = np.max(np.abs(np.diff(force, prepend=0.0))) / max(np.max(force), 1e-30)
    far = np.abs(r) * smooth < 0.35
    # (the second difference is left out: a pulse rising as t^a with a under 2 has no second derivative at
    # its start, and taking out its sampled stand-in put a spike of a sixth of the peak on soft strokes)
    return np.array([np.sum(c0.real), np.sum((c0 * r * far).real), 0.0])


def _take_out(buf: np.ndarray, start: int, force: np.ndarray, quasi: np.ndarray, chan: np.ndarray) -> None:
    """Subtract the push's share (weights of F, ΔF, Δ²F) from a stroke's channels while the mallet touches."""
    f = np.concatenate([force, np.zeros(2)])
    d1 = np.diff(f, prepend=0.0)
    d2 = np.diff(d1, prepend=0.0)
    corr = quasi[0] * f + quasi[1] * d1 + quasi[2] * d2
    n = min(len(corr), buf.shape[1] - start)
    if n > 0:
        buf[:, start:start + n] -= corr[None, :n] * chan[:, None]


def _pan(bars: Bars, m: float) -> np.ndarray:
    """A player's image: the low bars to the left, the high to the right."""
    middle = 0.5 * (bars.low + bars.high)
    pan = float(np.clip((m - middle) / (0.5 * (bars.high - bars.low)), -1.0, 1.0)) * bars.spread
    return np.array([np.cos((pan + 1.0) * np.pi / 4.0), np.sin((pan + 1.0) * np.pi / 4.0)]) * np.sqrt(2.0)


RATTLE = 2.0  # a loose bar's buzz at wear 1, against its note's peak (before its band-pass)


def _rattle(f1: float, amp: float, n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    """A loose bar buzzing on its post or cord: the tips of its swing slapping the stop, a train of little
    knocks at its own frequency, bright (1 to 6 kHz), for the few hundredths of a second the swing is large."""
    t = np.arange(n) / sr
    swing = np.exp(-t / 0.03) * np.sin(2.0 * np.pi * f1 * t + rng.uniform(0.0, 2.0 * np.pi))
    hits = np.maximum(swing - 0.55, 0.0)
    band = butter(2, [1000.0, min(6000.0, 0.45 * sr)], btype="bandpass", fs=sr, output="sos")
    return sosfilt(band, hits) * amp


def _motor_track(notes, sr: int, length: int, kit: Kit) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The vibraphone's motor: one shaft turning the discs in every resonator, so one phase for the whole part.
    Its rate (the tremolo's, Hz) from ornament, 2.5 + 4 × ornament, off at 0 (and the discs' swing growing to
    its full depth by 0.2, so a drifting ornament never flips it on and off), or from the art tokens, each from
    its note on; the motor takes about 0.4 s to change speed. Returns the phase, how far the discs are in play
    (0 when stopped: they are left open) and the rate."""
    base = 2.5 + 4.0 * kit.ornament if kit.ornament > 0.0 else 0.0
    target = np.full(length, base * kit.motor_rate)
    depth = np.full(length, min(kit.ornament / 0.2, 1.0))
    for note in sorted(notes, key=lambda n: n.start):
        art = _tokens(note.art)
        rate = None
        if "motor-off" in art:
            rate = 0.0
        elif "motor-slow" in art:
            rate = 3.5
        elif "motor-fast" in art:
            rate = 6.5
        if rate is not None:
            i = int(round(note.start * sr))
            if i < length:
                target[i:] = rate * kit.motor_rate
                depth[i:] = 1.0
    a = np.exp(-1.0 / (0.4 * sr))
    rate = lfilter([1.0 - a], [1.0, -a], target, zi=[a * target[0]])[0]
    depth = lfilter([1.0 - a], [1.0, -a], depth, zi=[a * depth[0]])[0]
    phase = kit.motor_phase + 2.0 * np.pi * np.cumsum(rate) / sr
    return phase, np.clip(rate / 1.5, 0.0, 1.0) * depth, rate


def _tremolo(tube: np.ndarray, sr: int, phase: np.ndarray, engaged: np.ndarray, rate: np.ndarray,
             kit: Kit) -> np.ndarray:
    """The discs at work on what the resonators radiate: as each disc turns, the tube's mouth opens and closes
    twice a turn, so what the tube adds to the fundamental swings by 11 dB (the bar's own sound, a quarter
    cycle apart, keeps the note's swing to about 9 dB and turns part of it into a swing of pitch, ±2 to 3
    cents); the disc also moves the tube's effective length a little, another cent."""
    depth_db = 11.0 + 1.0 * kit.disc_depth - 3.0 * kit.wear
    floor = 10.0 ** (-depth_db / 20.0)
    opening = 0.5 + 0.5 * np.cos(phase)
    gain = 1.0 - engaged * (1.0 - floor) * (1.0 - opening)
    cents = 1.0
    wobble = (cents / 1731.2) / (2.0 * np.pi * np.maximum(rate, 0.5)) * sr * engaged  # samples of delay swing
    delay = 3.0 + wobble * np.sin(phase)
    idx = np.arange(tube.shape[1]) - delay
    out = np.empty_like(tube)
    for ch in range(tube.shape[0]):
        out[ch] = np.interp(idx, np.arange(tube.shape[1]), tube[ch], left=0.0) * gain
    return out


def _bars(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
          settings: dict) -> np.ndarray:
    bars = BARS[name]
    kit = Kit(bars, make, settings)
    out = np.zeros((2, length))
    tube = np.zeros((2, length)) if name == "vibraphone" else None
    for stroke in _strokes(name, bars, notes, rng):
        start = int(round(stroke.start * sr))
        if start >= length:
            continue
        force, freqs, gains, tube_gains, t60, damped, damp_at, peak, f1, quasi, tube_quasi = _bar_modes(
            bars, kit, stroke, rng, sr)
        chan = _pan(bars, stroke.pitch)
        floor = peak * 1e-4
        _take_out(out, start, force, quasi, chan)
        if tube is not None:
            _take_out(tube, start, force, tube_quasi, chan)
        elif tube_quasi is not None:
            _take_out(out, start, force, tube_quasi, chan)
        if tube is not None:
            modal.ring(out, start, force, freqs, np.ascontiguousarray(gains.real), np.ascontiguousarray(gains.imag),
                       t60, damped, damp_at, float(0.01 * sr), chan, float(sr), floor)
            modal.ring(tube, start, force, freqs, np.ascontiguousarray(tube_gains.real),
                       np.ascontiguousarray(tube_gains.imag), t60, damped, damp_at, float(0.01 * sr), chan,
                       float(sr), floor)
        else:
            if tube_gains is not None:
                gains = gains + tube_gains
            modal.ring(out, start, force, freqs, np.ascontiguousarray(gains.real), np.ascontiguousarray(gains.imag),
                       t60, damped, damp_at, float(0.01 * sr), chan, float(sr), floor)
        key = int(np.clip(round(stroke.pitch), 0, 127))
        loose = kit.loose[key] * kit.wear
        if loose > 0.0 and stroke.vel > 0.25:
            n = min(length - start, int(0.08 * sr))
            if n > 32:
                out[:, start:start + n] += _rattle(f1, peak * RATTLE * loose * stroke.vel, n, sr, rng)[None, :] \
                    * chan[:, None]
        if name == "celesta":  # the key and hammer knocking in the action
            n = min(length - start, int(0.025 * sr))
            if n > 16:
                thud = sosfilt(butter(2, [100.0, 1500.0], btype="bandpass", fs=sr, output="sos"),
                               rng.standard_normal(n + 64))[64:]
                env = np.exp(-np.arange(n) / (0.004 * sr)) * (1.0 - np.exp(-np.arange(n) / (0.0006 * sr)))
                thud *= env / (np.sqrt(np.mean((thud * env) ** 2)) + 1e-12)
                out[:, start:start + n] += thud[None, :] * chan[:, None] * peak * 0.04 * (0.5 + stroke.vel)
    if tube is not None:
        phase, engaged, rate = _motor_track(notes, sr, length, kit)
        if np.any(engaged > 0.0):
            tube = _tremolo(tube, sr, phase, engaged, rate, kit)
        out += tube
    if name == "celesta":
        case = body.impulse_response(CELESTA_CASE, sr, seed=kit.seed, size=kit.size)
        for ch in range(2):
            out[ch] = oaconvolve(out[ch], case[:, ch])[:length]
    y = out.T.copy()
    return sosfilt(butter(1, 20.0, btype="highpass", fs=sr, output="sos"), y, axis=0)


# --- the music box -------------------------------------------------------------------------------

MUSIC_BOX = body.Body(  # a small wooden box: thin panels whose lowest modes sit near 300 Hz, little below
    modes=((330.0, 12.0, 2.0), (560.0, 14.0, 3.0)),
    dense=(400.0, 12000.0, 110), tilt=-1.0, q=(30.0, 20.0), direct=0.25, lowcut=300.0, highcut=11000.0,
    length=0.3,
)
COMB_T60 = ((72, 4.0), (90, 3.0), (108, 2.0))
LUMP = 0.08  # a bass tooth's lead lump: rotary inertia over mass, in tooth lengths squared


def tooth(m: float) -> tuple[np.ndarray, np.ndarray]:
    """A comb tooth's first three mode ratios and what each gives the comb's base when released from a bend:
    the treble teeth are plain cantilevers (1 : 6.27 : 17.55); the bass teeth carry lead lumps under their tips
    (up to twice the tooth's mass by C5), which rock, and bring the second mode down to 4-5."""
    lump = 2.0 * float(np.clip((84.0 - m) / 12.0, 0.0, 1.0)) ** 1.5
    b = np.array(weighted_tooth(round(lump, 3), round(LUMP * lump, 4)))
    ratios = (b / b[0]) ** 2
    # released from a tip load, mode k holds φk(tip)/ωk² of the bend; what it puts into the base is its root's
    # moment (and a little shear force): 1.14, -0.18, 0.065 (moment) and 1.57, -0.87, 0.51 (shear) for a plain tooth
    part = np.array([1.1377, -0.1815, 0.0648]) + 0.3 * np.array([1.5660, -0.8679, 0.5089])
    return ratios, part


def _music_box(notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
               settings: dict) -> np.ndarray:
    brightness = float(np.clip(settings.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(settings.get("wear", 0.25), 0.0, 1.0))
    size = float(np.clip(settings.get("body", 1.0), 0.7, 1.35))
    cents = np.clip(make.standard_normal(128), -3.0, 3.0) * (0.5 + 12.0 * wear)
    mode_cents = make.standard_normal((128, 3)) * 4.0 * (1.0 + 2.0 * wear)
    seed = int(make.integers(1 << 30))
    comb = np.zeros((1, length))
    ordered = sorted([n for n in notes if n.dur > 0], key=lambda n: (n.start, n.pitch))
    pitches = [_within(float(n.pitch), 72, 108) for n in ordered]
    # when each tooth is plucked again: its damper (or the pin) stops what is still ringing, with a buzz
    later = {}
    again = [None] * len(ordered)
    for i in range(len(ordered) - 1, -1, -1):
        key = int(round(pitches[i]))
        if key in later:
            again[i] = later[key] - ordered[i].start
        later[key] = ordered[i].start
    release = 25e-6 * 2.0 ** (1.0 - 2.0 * brightness) * (1.0 + wear)  # s: the tip snapping off the pin
    buzzes = []
    for i, note in enumerate(ordered):
        start = int(round((note.start + rng.uniform(0.0, 0.001)) * sr))
        if start >= length:
            continue
        m = pitches[i]
        key = int(np.clip(round(m), 0, 127))
        f1 = _hz(m + cents[key] / 100.0)
        ratios, part = tooth(m)
        freqs = f1 * ratios * 2.0 ** (np.concatenate([[0.0], mode_cents[key, :2]]) / 1200.0)
        t60 = _log_interp(m, COMB_T60) * (1.0 - 0.3 * wear) * (f1 / freqs) ** 0.9
        keep = freqs < 0.45 * sr
        if not keep[0]:
            continue
        force = _gamma(release, 1.5, sr)
        t = np.arange(len(force)) / sr
        drive = np.abs((force[None, :] * np.exp(-2j * np.pi * freqs[:, None] * t[None, :])).sum(axis=1))
        vel = float(np.clip(note.vel, 0.0, 1.0))
        rate = modal.LN1000 / t60
        power = 0.5 * (part * drive * keep) ** 2 * (1.0 - np.exp(-2.0 * rate * 0.2)) / (2.0 * rate * 0.2)
        level = 0.1 * touch.gain(vel, 4.0) / np.sqrt(power.sum())
        gains = part * level  # cosine phase: a tooth released from a bend
        damp_at, damped = -1, t60.copy()
        guard = 0.025 if m < 84 else 0.006  # the bass teeth's dampers touch well before the pin; above, the pin
        if again[i] is not None:
            damp_at = int(round(max(again[i] - guard, 0.0) * sr))
            damped = np.minimum(t60, guard / 3.0)
            left = abs(gains[0]) * np.exp(-rate[0] * max(again[i] - guard, 0.0))
            if left > 1e-3 * abs(gains[0]):
                buzzes.append((start + damp_at, f1, left, guard, again[i] - guard))
        modal.ring(comb, start, force, freqs[keep], np.ascontiguousarray(gains[keep]), np.zeros(int(keep.sum())),
                   t60[keep], damped[keep], damp_at, float(0.002 * sr), np.ones(1), float(sr),
                   abs(gains[0]) * 1e-4)
        # the pin's tick as it snaps off the tip
        n = min(length - start, int(0.0015 * sr))
        if n > 8:
            tick = sosfilt(butter(2, 2000.0, btype="highpass", fs=sr, output="sos"), rng.standard_normal(n + 64))[64:]
            comb[0, start:start + n] += tick * np.exp(-np.arange(n) / (0.0003 * sr)) * abs(gains[0]) \
                * 0.4 * (0.5 + brightness)
    for at, f1, left, guard, since in buzzes:
        n = min(length - at, int(guard * sr))
        if n > 8:
            t = np.arange(n) / sr
            swing = left * np.exp(-t / (guard / 3.0)) * np.cos(2.0 * np.pi * f1 * (t + since))
            hits = np.maximum(swing - 0.5 * left, 0.0)
            hits = hits - np.linspace(hits[0], hits[-1], n)
            comb[0, at:at + n] += hits * (0.6 + 0.8 * wear)
    ir = body.impulse_response(MUSIC_BOX, sr, seed=seed, size=size)
    out = body.resonate(comb[0], ir)
    return sosfilt(butter(1, 20.0, btype="highpass", fs=sr, output="sos"), out, axis=0)


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A mallet part: stereo, dry, `length` samples, before placement and level."""
    if name not in SPEC:
        raise ValueError(f"no such instrument: {name}")
    if length <= 0:
        return np.zeros((0, 2))
    if name == "music-box":
        return _music_box(notes, sr, length, rng, make, settings)
    return _bars(name, notes, sr, length, rng, make, settings)
