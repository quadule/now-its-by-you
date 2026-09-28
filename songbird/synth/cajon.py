"""A cajon: a plywood box played with the hands, with snares behind its face.

The box (about 30 by 30 by 48 cm, by maker) has a sound hole in its back, so
the air inside is a Helmholtz resonator: a volume V breathing through a hole
of radius a in a back of thickness t, at f = c/(2 pi) sqrt(pi a^2 / (V (t +
1.7 a))), 83 to 92 Hz for a hole 10 to 12 cm across. The face (the tapa, 3 to
4 mm birch plywood screwed along three sides, its top corners loose) is a
thin plate whose first mode lies near 120 to 160 Hz; it and the air push on
each other, so they split, as a guitar's air mode and top plate do (Fletcher
and Rossing, The Physics of Musical Instruments, chapter 9), into a lower
mode where the air rings through the hole (the boom, near 70 to 85 Hz) and a
higher one where the face does. Above them the face rings in its own modes,
a simply supported plate's (Leissa, Vibration of Plates, NASA SP-160, 1969),
up to 3.5 kHz; the ones that change the box's volume radiate best, and all
radiate better toward the plate's coincidence frequency (about 4.6 kHz for
3.5 mm plywood). The other walls knock faintly.

Where the hand lands decides what speaks, as on the frame drum. The palm in
the upper middle (cajon-bass) pushes the whole face in, a soft contact of a
few milliseconds: the boom. The fingers at the top edge (cajon-slap), where
only the higher modes move much, land briefly: a crack, and the loose
corners slap the frame a fraction of a millisecond later (more when struck
toward a corner). Behind the face, snare wires (or, by maker, two to four
guitar strings, or nothing) are pressed against its upper part: a wire rides
the face until the face pulls away faster than the wire's spring can follow,
flies, lands with a click, bounces, and settles again once the face's motion
has died under its press (rattle.py). So a slap rattles for a tenth of a
second or two and stops, a bass stroke barely lifts them, a ghost tap
(cajon-tap, the fingertips) just stirs them. cajon-mid is the hand between.

Each stroke is levelled by its K-weighted loudness over its first 100 ms
(the boom is slow to speak): the bass and the slap alike at a given
velocity, the tap about 9 dB under; a slap's energy is shared between the
face, the snares and the crack by maker. The snares' press and loudness are
set by striking the maker's cajon with a reference slap.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.signal import lfilter, sosfilt

from . import struck
from .iir import butter
from .rattle import burst, comb, contact, early_power, late, modal_weights, vel_gain, wires

SPEC = {
    "cajon": dict(
        family="percussion", role="percussion", register=None, place=(0.1, 0.2), level=0.6, poly=True,
        articulations={
            "cajon-bass": "the palm in the upper middle of the face: the boom through the hole",
            "cajon-slap": "the fingers at the top edge: a crack, the corners on the frame, the snares",
            "cajon-tap": "a ghost: the fingertips near the top, about 9 dB under, a stir of the snares",
            "cajon-mid": "the hand between the middle and the top: some boom and some crack",
        },
        about="a cajon: a plywood box with a hole in its back (its air a Helmholtz resonator near 85 Hz) and a "
              "thin birch face, with snare wires or guitar strings behind it (by maker)",
    ),
}

EARLY = 0.25  # a stroke's early RMS (K-weighted, first 100 ms) at full velocity, before the stem's level
PLATE = 0.2  # the face's bending modes' radiation against its breathing (1,1) mode's and the hole's
BOOM = 0.1  # seconds of a stroke that set its level

# where the hand lands (across and up the face, as fractions; their scatter), its contact at vel 0 and at 1
# (ms), and the stroke's loudness against the others
STROKES = {
    "cajon-bass": (0.5, 0.5, 0.04, 0.04, 6.0, 3.0, 1.0),
    "cajon-mid": (0.5, 0.76, 0.06, 0.03, 2.8, 1.4, 0.85),
    "cajon-slap": (0.5, 0.92, 0.15, 0.015, 1.0, 0.45, 1.0),
    "cajon-tap": (0.5, 0.9, 0.2, 0.03, 1.2, 0.8, 0.28),
}
# a drummer's strokes as a cajon player takes them
KIT = {"kick": "cajon-bass", "stomp": "cajon-bass", "tom-lo": "cajon-bass", "tom-mid": "cajon-mid",
       "tom-hi": "cajon-mid", "snare": "cajon-slap", "rim": "cajon-slap", "clap": "cajon-slap",
       "cross": "cajon-slap", "crash": "cajon-slap", "hat": "cajon-tap", "hat-open": "cajon-tap",
       "ride": "cajon-tap", "ghost": "cajon-tap", "brush-tap": "cajon-tap", "shaker": "cajon-tap"}


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """A part's dry stem, mono (length,): see SPEC."""
    if name != "cajon":
        raise ValueError(f"cajon.py plays the cajon, not {name}")
    s = dict(settings or {})
    bright = float(np.clip(s.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(s.get("wear", 0.25), 0.0, 1.0))
    size = float(np.clip(s.get("body", 1.0), 0.5, 2.0))
    return play(notes, sr, length, rng, _cajon(make, size, bright, wear, sr), bright, wear)


def _cajon(make: np.random.Generator, size: float, bright: float, wear: float, sr: int) -> dict:
    """The maker's cajon: its box, face, snares and how a slap shares itself."""
    width, depth, height = np.array([0.30, 0.30, 0.48]) * np.exp(make.normal(0.0, 0.03, 3)) * size
    hole = make.uniform(0.05, 0.06) * size  # radius, metres
    air = (width - 0.024) * (depth - 0.024) * (height - 0.024)
    helmholtz = 343.0 / (2.0 * np.pi) * np.sqrt(np.pi * hole**2 / (air * (0.012 + 1.7 * hole)))
    face = make.uniform(120.0, 160.0) / size  # the face's first mode, alone
    kappa = make.uniform(0.3, 0.45)  # how hard the air and the face push on each other
    a, b = helmholtz**2, face**2
    root = np.sqrt(((b - a) / 2.0) ** 2 + kappa**2 * a * b)
    pair = np.sqrt([(a + b) / 2.0 - root, (a + b) / 2.0 + root])
    # how much the face moves in each: the lower is mostly the air, the upper mostly the face
    mixing = 0.5 * np.arctan2(2.0 * kappa * helmholtz * face, abs(b - a))
    moves = np.array([np.sin(mixing), np.cos(mixing)])
    ply = make.uniform(3.0, 4.0)  # mm
    coincidence = 4600.0 * 3.5 / ply
    m_, n_, f_ = [], [], []
    unit = 1.0 / width**2 + 1.0 / height**2
    for m in range(1, 9):
        for n in range(1, 13):
            f = face * ((m / width) ** 2 + (n / height) ** 2) / unit
            if (m, n) != (1, 1) and f < 3500.0:
                m_.append(m)
                n_.append(n)
                f_.append(f)
    m_, n_ = np.array(m_), np.array(n_)
    plate = np.array(f_) * np.exp(make.normal(0.0, 0.04, len(f_)))
    # below coincidence a plate radiates its bending modes poorly, mostly from its edges (Maidanik: about
    # 0.08 sqrt(f / fc) for a face this size), the ones that change the box's volume better
    radiate = np.where((m_ % 2 == 1) & (n_ % 2 == 1), 1.0, np.where((m_ % 2 == 1) | (n_ % 2 == 1), 0.3, 0.1))
    radiate = PLATE * radiate * np.minimum(1.0, plate / coincidence) ** 0.5
    walls = np.exp(make.uniform(np.log(220.0), np.log(900.0), 5)) / size
    kind = ("wires", "strings", "none")[int(make.choice(3, p=[0.55, 0.35, 0.10]))]
    if kind == "wires":  # a bundle of wires across the top fifth of the face: three places they touch
        spots = np.column_stack([np.array([0.25, 0.5, 0.75]) + make.normal(0.0, 0.03, 3),
                                 make.uniform(0.82, 0.93, 3)])
        spring = make.uniform(250.0, 400.0, 3)
    elif kind == "strings":  # strings running up the face, pressed against its upper part
        count = int(make.integers(2, 5))
        spots = np.column_stack([np.linspace(0.3, 0.7, count) + make.normal(0.0, 0.02, count),
                                 make.uniform(0.86, 0.95, count)])
        spring = make.uniform(120.0, 200.0, count)
    else:
        spots, spring = np.zeros((0, 2)), np.zeros(0)
    shares = {"wires": (0.45, 0.35, 0.2), "strings": (0.5, 0.3, 0.2), "none": (0.75, 0.0, 0.25)}[kind]
    shares = np.array(shares) * np.exp(make.normal(0.0, 0.15, 3))
    return dict(
        helmholtz=helmholtz, face=face, pair=pair, moves=moves, plate=plate, m=m_, n=n_, radiate=radiate,
        pair_t60=np.array([make.uniform(0.35, 0.5), make.uniform(0.2, 0.28)]) * (1.0 + 0.2 * wear),
        boom=float(make.uniform(5.0, 7.0)),  # the air ringing through the hole: the boom's radiation
        # plywood's own loss (a loss factor near 0.015) and the air's load: 0.2 s at 500 Hz, 0.08 at 3 kHz
        plate_t60=0.35 * (face / plate) ** 0.5 * np.exp(make.normal(0.0, 0.15, len(plate))),
        walls=walls, walls_t60=make.uniform(0.06, 0.12, 5), walls_gain=float(make.uniform(0.15, 0.3)),
        kind=kind, spots=spots, spring=spring, hold=make.uniform(0.003, 0.006, len(spring)) * (1.0 - 0.4 * wear),
        string=float(make.uniform(170.0, 260.0)), shares=shares / shares.sum(),
        frame=float(make.uniform(2000.0, 3200.0)), seed=int(make.integers(1 << 62)),
    )


def _shape(cj: dict, x: float, y: float) -> np.ndarray:
    """Each of the face's moving modes (the pair, then the plate's) at (x, y), as fractions across and up."""
    first = np.sin(np.pi * x) * np.sin(np.pi * y)
    return np.concatenate([first * cj["moves"], np.sin(cj["m"] * np.pi * x) * np.sin(cj["n"] * np.pi * y)])


def _strike(cj: dict, art: str, vel: float, rng: np.random.Generator, bright: float) -> tuple:
    """Where and how a stroke lands, and the face's modes' displacements and radiated amplitudes from it
    (before levelling), and the walls' knock."""
    x0, y0, dx, dy, soft, hard, gain = STROKES[art]
    x = float(np.clip(x0 + rng.normal(0.0, dx), 0.05, 0.95))
    y = float(np.clip(y0 + rng.normal(0.0, dy), 0.3, 0.97))
    tau = (soft + (hard - soft) * vel) * 1e-3 * (1.2 - 0.4 * bright)
    freqs = np.concatenate([cj["pair"], cj["plate"]])
    omega = 2.0 * np.pi * freqs
    disp = _shape(cj, x, y) * contact(freqs, tau) / omega * rng.uniform(0.9, 1.1, len(freqs))
    radiate = np.concatenate([[cj["boom"], 0.6], cj["radiate"]])
    walls = cj["walls_gain"] * rng.standard_normal(len(cj["walls"])) * contact(cj["walls"], tau) \
        * 2.0 * np.pi * cj["walls"] / omega[0]
    return x, y, gain, disp, np.concatenate([disp * omega**2 * radiate / omega[0], walls])


@lru_cache(maxsize=8)
def _bands(sr: int, bright: float) -> tuple:
    wire = np.vstack([butter(2, 1800.0, btype="highpass", fs=sr, output="sos"),
                      butter(2, min(8000.0 + 4000.0 * bright, 0.45 * sr), fs=sr, output="sos")])
    crack = butter(2, [1200.0, min(7000.0 + 3000.0 * bright, 0.45 * sr)], btype="bandpass", fs=sr, output="sos")
    low = butter(2, 25.0, btype="highpass", fs=sr, output="sos")
    string = np.vstack([butter(2, 400.0, btype="highpass", fs=sr, output="sos"),
                        butter(2, min(6000.0 + 4000.0 * bright, 0.45 * sr), fs=sr, output="sos")])
    return wire, crack, low, string


def _rattle(cj: dict, clicks: np.ndarray, sr: int, bright: float) -> np.ndarray:
    """The snares' clicks as they sound: wires buzz from 2 to 10 kHz; strings ring their own pitch."""
    wire, _, _, string = _bands(sr, round(bright, 3))
    if cj["kind"] == "strings":  # the string's own ring, pressed against the face: a tenth of a second or so
        return sosfilt(string, comb(clicks, int(round(sr / cj["string"])), 0.85))
    return sosfilt(wire, clicks)


def _contacts(cj: dict) -> np.ndarray:
    """Each snare's share of each of the face's moving modes, where it touches."""
    return np.array([_shape(cj, x, y) for x, y in cj["spots"]]).reshape(len(cj["spots"]), -1)


def _calibrate(cj: dict, sr: int, bright: float) -> tuple[np.ndarray, float]:
    """Strike the maker's cajon with a reference slap at full velocity: set the snares' press (a share of
    the face's pull under them) and the gain that gives the snares their share of the slap."""
    rng = np.random.default_rng(cj["seed"])
    freqs = np.concatenate([cj["pair"], cj["plate"], cj["walls"]])
    t60s = np.concatenate([cj["pair_t60"], cj["plate_t60"], cj["walls_t60"]])
    heard = modal_weights(freqs, t60s, sr, BOOM)
    x, y, gain, disp, rad = _strike(cj, "cajon-slap", 1.0, rng, bright)
    scale = np.sqrt(cj["shares"][0]) * EARLY / np.sqrt(float(rad**2 @ heard) + 1e-30)
    if cj["kind"] == "none":
        return np.zeros(0), 0.0
    shapes = _contacts(cj)
    moving = np.concatenate([cj["pair"], cj["plate"]])
    pull = np.abs(shapes * (disp * scale * (2.0 * np.pi * moving) ** 2)[None, :]).sum(axis=1)
    press = cj["hold"] * pull / (2.0 * np.pi * cj["spring"]) ** 2
    probe = np.zeros(int(0.3 * sr))
    wires(moving, t60s[:len(moving)], disp * scale, shapes, cj["spring"], press, out=probe, start=0, rng=rng, sr=sr)
    power = early_power(_rattle(cj, probe, sr, bright), sr, BOOM)
    return press, float(np.sqrt(cj["shares"][1] * EARLY**2 / power)) if power > 0 else 0.0


def play(notes, sr: int, length: int, rng: np.random.Generator, cj: dict, bright: float, wear: float) -> np.ndarray:
    wire_band, crack_band, low, _ = _bands(sr, round(bright, 3))
    freqs = np.concatenate([cj["pair"], cj["plate"], cj["walls"]])
    t60s = np.concatenate([cj["pair_t60"], cj["plate_t60"], cj["walls_t60"]])
    heard = modal_weights(freqs, t60s, sr, BOOM)
    moving = len(cj["pair"]) + len(cj["plate"])
    press, snare_gain = _calibrate(cj, sr, bright)
    shapes = _contacts(cj) if len(press) else None
    clicks = np.zeros(length)
    out = np.zeros(length)
    times, rows = [], []
    jitter = 0.0015 + 0.005 * wear
    for note in notes:
        start = int(round(note.start * sr))
        if not 0 <= start < length:
            continue
        art = note.art if note.art in STROKES else KIT.get(note.art, "cajon-slap")
        vel = float(np.clip(note.vel, 0.0, 1.0))
        t0 = note.start + late(rng, jitter)
        x, y, gain, disp, rad = _strike(cj, art, vel, rng, bright)
        loud = EARLY * vel_gain(vel) * gain
        slap = art == "cajon-slap"
        share = cj["shares"][0] if slap else 1.0
        scale = np.sqrt(share) * loud / np.sqrt(float(rad**2 @ heard) + 1e-30)
        times.append(t0)
        rows.append(rad * scale)
        at = int(round(t0 * sr))
        if shapes is not None and loud > 0.0:
            wires(freqs[:moving], t60s[:moving], disp * scale, shapes, cj["spring"], press, out=clicks, start=at,
                  rng=rng, sr=sr)
        if slap and loud > 0.0:  # the loose corners slap the frame
            near = np.clip((y - 0.8) / 0.12, 0.0, 1.0) * (0.6 + 0.8 * abs(x - 0.5) * 2.0)
            n = int(0.02 * sr)
            knock = sosfilt(crack_band, burst(rng, (0.25 - 0.1 * vel) * 1e-3, sr, n))
            r = np.exp(-np.pi * cj["frame"] / 6.0 / sr)
            knock += 0.5 * lfilter([1.0 - r], [1.0, -2.0 * r * np.cos(2.0 * np.pi * cj["frame"] / sr), r * r], knock)
            knock *= np.sqrt(cj["shares"][2]) * loud * near / np.sqrt(early_power(knock, sr, BOOM) + 1e-30)
            knock *= min(1.0, 2.5 * loud / (np.abs(knock).max() + 1e-30))  # a knock, not a gunshot: 8 dB over the stroke
            delay = int(rng.uniform(0.3, 1.2) * 1e-3 * sr)
            end = min(length, at + delay + n)
            if at + delay < length:
                out[at + delay:end] += knock[: end - at - delay]
    if times:
        out += struck.ring(freqs, t60s, times, np.array(rows), sr, length)
    if shapes is not None and np.any(clicks):
        out += _rattle(cj, clicks, sr, bright) * snare_gain
    return sosfilt(low, out)
