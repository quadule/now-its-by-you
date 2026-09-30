"""The accordion and the concertina: free reeds in a box, a bellows and two hands.

A free reed is a steel tongue riveted over a slot in a plate: the air through
the slot sets it swinging and it chops the stream into pulses, so its tone is
rich in harmonics, and richer the harder the bellows press (reed.py's tables:
a dark and a bright period cross-faded by the pressure). Every note has two
reeds, one on each face of its plate: the one outside the reed block speaks
as the bellows close (push), the one inside, in the block's small chamber,
as they open (pull). Each is tuned by hand, so the two directions differ by
a cent or two, and a shade in tone.

- The attack. A reed at rest is started by the puff of air as its pallet
  lifts (heard, rushing through the slot until the tongue chokes it), and its
  swing grows exponentially until the slot limits it: a note swells in, a few
  cents sharp, its fundamental first and its buzz as the swing reaches through
  the slot. To nine tenths of full, a small treble reed takes about 15 ms, a
  middle one 25 to 40, the long weighted bass reeds 60 to 100; pressed harder,
  all of them quicker. When the pallet shuts the flow stops and the note is
  gone in a few tens of milliseconds, with the pad's soft thud. A low reed's
  pulses are heard as pulses (the growl of the bass buttons): its harmonics
  start in phase below D3, scattering by D4, where the ear no longer hears
  their phase.
- The bellows. One bellows drives every reed that sounds, so the pressure,
  and with it the loudness (as the pressure to the power 1.3: 20 dB from
  velocity 0.2 to 1), the brightness and a hair of flatness (a free reed
  sounds a few cents lower pressed hard: Cottingham), follows the player's
  arm, not the keys. The bellows run one way until the player turns them: at
  a rest once the stroke has run a few seconds (an accordion's 3 to 6, a
  concertina's 1.2 to 2.8), on a strong note if one comes soon (the oom of an
  oom-pah, so the new stroke accents it), at a note's start once most of the
  stroke's air is used, and wherever they must once all of it is (a chord
  drinks air faster than a single note, the big bass reeds fastest; the first
  stroke opens them). A turn takes 40 to 70 ms with the pressure dipping to a
  quarter, and a note held through it hands over to its other reed, which
  must speak again. 'shake' is the bellows shaken: turned 5 to 8 times a
  second (a subdivision of the beat when the band gives a tempo).
- The accordion's treble, F3 to A6. The maker's reed ranks: the middle reeds
  (8'), a bassoon an octave down (16'), a piccolo an octave up (4'). A
  tremolo box has a second middle reed tuned sharp and a musette box a third
  tuned as far flat, by the maker's tremolo (Liberty Bellows' table at A4:
  dry 0 cents, swing 4, Irish 7, Cajun 10, Alpine 12, German and Italian 15,
  French 18, old French 22, Scottish 25) and its curve across the keyboard
  (1.3 times the cents at A3 and below, 2/3 at A5, 4/9 at A6: the beats
  quicken toward the top, but less than the pitch does). The player's
  register: ornament sounds one middle reed (clarinet), two (violin) or
  three (musette); brightness under 0.4 adds the bassoon, over 0.6 the
  piccolo. Some makers put the middle and bassoon reeds in a tone chamber
  (cassotto): darker.
- The accordion's left hand, the Stradella buttons. A bass button sounds its
  note's pitch class on the bass (C2-B2) and tenor (C3-B3) ranks and, lighter,
  the contralto (F#3-F4), wherever it was written, so a bass line breaks
  between B and C as an accordion's does; a chord button's notes sound in the
  contralto's octave and the one above. 'bass' and 'chord' name them; a plain
  note below the treble keyboard is a bass button alone, a chord button with
  others struck with it.
- The concertina: an English one (a button sounds the same note pushed or
  pulled), a tenor-treble, chromatic from C3 to C7, one reed a note each way:
  concertina reeds (quicker and more cutting than an accordion's) or, on some
  makers' hybrids, accordion reeds. The scale alternates between the hands (the notes on the
  staff's lines at the left end, those in its spaces at the right), each end
  a small box of its own.
- The boxes: the accordion's treble reed blocks behind the grille and its
  bigger bass box (body.ACCORDION), the concertina's hexagonal ends
  (body.CONCERTINA). The accordion's treble sits a little left and its bass
  right, as an audience hears them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numba import njit
from scipy.signal import sosfilt

from ..theory import midi_to_hz
from . import body, oa, reed
from .iir import butter

BLOCK = 1 << 16  # samples a stretch, where what is worked sample by sample is worked a stretch at a time

ACCORDION_ARTS = {
    "": "a key or a button, as the note lies: the treble's keys from F3 up; below them the left hand, a lone note "
        "a bass button, notes struck together chord buttons",
    "slur": "legato: the key goes down as the last comes up",
    "bass": "a Stradella bass button: the note's pitch class on the bass (C2-B2) and tenor (C3-B3) ranks, wherever "
            "it is written",
    "chord": "a chord button's note: in the chord reeds' octave (F#3-F4) and the one above",
    "shake": "bellows shake: the bellows turned 5 to 8 times a second through the note, each stroke a pulse",
    "swell": "the bellows pressed harder into the note's middle, and eased off",
}
CONCERTINA_ARTS = {
    "": "a button: the reed speaks at once (C3 to C7; notes outside it moved by octaves)",
    "slur": ACCORDION_ARTS["slur"],
    "shake": ACCORDION_ARTS["shake"],
    "swell": ACCORDION_ARTS["swell"],
}

SPEC = {
    "accordion": dict(
        family="reed", role="comping", register=(41, 93), place=(-0.25, 0.8), level=0.316, poly=True,
        articulations=ACCORDION_ARTS,
        about="a piano accordion: its treble F3-A6 on the maker's reed ranks (a tremolo or musette box, dry to "
              "Scottish-wet) in the player's register, the Stradella bass and chord buttons below; one bellows "
              "for everything, turned as the air runs out",
    ),
    "concertina": dict(
        family="reed", role="comping", register=(48, 96), place=(-0.25, 0.6), level=0.339, poly=True,
        articulations=CONCERTINA_ARTS,
        about="an English concertina, C3-C7: one reed a note each way, quick and bright, the scale shared between "
              "two small hexagonal ends; its small bellows turned every second or two",
    ),
}

TREBLE = (53, 93)  # the accordion's keyboard, F3 to A6
COMPASS = (48, 96)  # the concertina's buttons, C3 to C7
# a bass button: the bass (C2-B2), tenor (C3-B3), contralto (F#3-F4) and, lightest, the chord reeds' octave (F#4-F5)
BASS_RANKS = ((36, 1.0), (48, 0.8), (54, 0.45), (66, 0.25))
CHORD_RANKS = ((54, 0.6), (66, 0.35))  # a chord button: the contralto (F#3-F4) and its octave
# The maker's tremolo, cents the tremolo reeds lie from the true one at A4 (Liberty Bellows' table), and how often
TUNINGS = (("dry", 0.0, 0.1), ("swing", 4.0, 0.1), ("irish", 7.0, 0.14), ("cajun", 10.0, 0.14),
           ("alpine", 12.0, 0.12), ("italian", 15.0, 0.18), ("french", 18.0, 0.11), ("old french", 22.0, 0.07),
           ("scottish", 25.0, 0.04))
CURVE = ((57.0, 1.3), (69.0, 1.0), (81.0, 2.0 / 3.0), (93.0, 4.0 / 9.0))  # the tremolo's cents across the keyboard
# The treble's reed ranks, by maker: L the bassoon (16'), M the middle reeds (8'), H the piccolo (4'); how often
BOXES = (("MM", 0.1), ("LMM", 0.25), ("LMMH", 0.35), ("MMM", 0.12), ("LMMM", 0.18))
# Seconds a reed takes to reach nine tenths of its swing at a middling pressure, by its own pitch (MIDI)
SPEAK = ((24.0, 0.13), (36.0, 0.085), (48.0, 0.055), (60.0, 0.035), (72.0, 0.024), (84.0, 0.017), (96.0, 0.013),
         (108.0, 0.011))
START = 0.02  # a reed's swing as its pallet lifts, against its full swing (a legato note's, 0.06)
DIP = 0.25  # the pressure at the bottom of a bellows turn
CLICK = 0.012  # a key's click against a note
HISS = 0.013  # the air through the slots (the pallet's puff, then past the tongue): -40 dB under a mezzo-forte note


@dataclass(frozen=True)
class Kind:
    """What sets one kind of squeezebox apart."""

    speak: float  # its reeds' speaking times against SPEAK
    slopes: tuple[float, float]  # harmonic k's amplitude as k**-slope, pressed lightly and hard
    stroke: tuple[float, float]  # litres of air one stroke of the bellows gives, by maker
    habit: tuple[float, float]  # seconds a stroke runs before the player turns the bellows at a rest
    turn: tuple[float, float]  # seconds a turn takes
    flow: float  # litres a second a middle reed drinks at full pressure
    box: body.Body


ACCORDION = Kind(speak=1.0, slopes=(0.95, 0.4), stroke=(6.0, 9.0), habit=(3.0, 6.0), turn=(0.04, 0.07), flow=0.2,
                 box=body.ACCORDION)
CONCERTINA = Kind(speak=0.6, slopes=(0.7, 0.25), stroke=(2.0, 3.2), habit=(1.2, 2.8), turn=(0.03, 0.05), flow=0.2,
                  box=body.CONCERTINA)
BASS_SLOPES, CHORD_SLOPES = (0.9, 0.4), (1.0, 0.45)  # the left hand's reeds: the big bass reeds buzz most
HYBRID = (0.95, 0.4)  # a hybrid concertina's accordion reeds: a little buzzier, less cutting


@dataclass(frozen=True)
class Voice:
    """One reed pair a note sounds: its pitch (MIDI, with the maker's tremolo), gain, side ("treble" or "bass"; the
    concertina's "left" or "right"), rank (for its tuning and table), key, air it drinks (litres a second at full
    pressure) and its spectrum's slopes."""

    pitch: float
    gain: float
    side: str
    rank: int
    key: int
    flow: float
    slopes: tuple[float, float]


def speaking(pitch: float) -> float:
    """Seconds an accordion reed of this pitch takes to reach nine tenths of its swing at a middling pressure."""
    x, y = zip(*SPEAK)
    return float(np.exp(np.interp(pitch, x, np.log(y))))


def tremolo(pitch: float) -> float:
    """The tremolo curve: a key's tremolo in cents against A4's."""
    x, y = zip(*CURVE)
    return float(np.exp(np.interp(pitch, x, np.log(y))))


def _fold(pitch: float, lo: int, hi: int) -> float:
    while pitch < lo:
        pitch += 12.0
    while pitch > hi:
        pitch -= 12.0
    return pitch


def _octave_of(pc: int, low: int) -> int:
    """The pitch of pitch class pc in the octave that starts at `low`."""
    return low + (pc - low) % 12


def maker(name: str, make: np.random.Generator, wear: float) -> dict:
    """One machine's instrument, drawn in a fixed order: its reeds (the accordion's box of ranks, its tremolo and
    tone chamber; the concertina's kind of reed), every reed's own tuning, its bellows' stroke, and the seeds of
    its reeds' tones and its boxes."""
    out: dict = {}
    if name == "accordion":
        names, weights = zip(*BOXES)
        out["box"] = names[int(make.choice(len(names), p=np.array(weights) / sum(weights)))]
        musette = out["box"].count("M") == 3
        rows = [t for t in TUNINGS if not musette or t[1] >= 10.0]  # a musette box is tuned wet
        p = np.array([t[2] for t in rows])
        out["tuning"] = rows[int(make.choice(len(rows), p=p / p.sum()))][0]
        cents = dict((t[0], t[1]) for t in TUNINGS)[out["tuning"]]
        out["tremolo"] = cents * float(np.exp(make.normal(0.0, 0.1)))
        out["cassotto"] = "L" in out["box"] and make.random() < 0.3
        out["slopes"] = ACCORDION.slopes
    else:
        out["box"] = "M"
        out["tuning"], out["tremolo"], out["cassotto"] = "dry", 0.0, False
        out["hybrid"] = make.random() < 0.25
        out["slopes"] = HYBRID if out["hybrid"] else CONCERTINA.slopes
    # every reed its own few cents (more on an old box): [key, rank, push or pull]; each key's tremolo a little off
    out["errors"] = make.normal(0.0, 1.0, (128, 10, 2)) * (0.4 + 3.0 * wear)
    out["uneven"] = 1.0 + make.normal(0.0, 1.0, 128) * (0.06 + 0.3 * wear)
    kind = CONCERTINA if name == "concertina" else ACCORDION
    out["stroke"] = float(make.uniform(*kind.stroke))
    out["seeds"] = [int(make.integers(1 << 30)) for _ in range(3)]
    return out


def register(box: str, ornament: float, bright: float) -> list[str]:
    """The treble ranks a player's register sounds on this box: one, two or three middle reeds as ornament asks
    (clarinet, violin, musette), the bassoon when dark, the piccolo when bright."""
    middles = min(box.count("M"), 1 + int(ornament >= 0.3) + int(ornament >= 0.7))
    ranks = ["M", "M+", "M-"][:middles]
    if "L" in box and bright < 0.4:
        ranks.append("L")
    if "H" in box and bright > 0.6:
        ranks.append("H")
    return ranks


# Each rank's reeds are reeds of their own (their own tuning, their own tone): the treble's middle, tremolo, bassoon
# and piccolo reeds; the left hand's bass, tenor, contralto (a bass button's and a chord button's alike) and the
# chords' octave; the concertina's
RANK = {"M": 0, "M+": 1, "M-": 2, "L": 3, "H": 4, 36: 5, 48: 6, 54: 7, 66: 8, "concertina": 9}


def hands(notes, name: str) -> list[str]:
    """Who plays each note: "treble" (the right hand's keys), "bass" or "chord" (the left hand's buttons); a
    concertina's notes are all its buttons ("treble")."""
    if name == "concertina":
        return ["treble"] * len(notes)
    low = [n.pitch < TREBLE[0] - 0.5 and n.art not in ("bass", "chord") for n in notes]
    starts = np.array([n.start for n in notes])
    out = []
    for k, n in enumerate(notes):
        if n.art in ("bass", "chord"):
            out.append(n.art)
        elif low[k]:
            a, b = np.searchsorted(starts, n.start - 0.02), np.searchsorted(starts, n.start + 0.02)
            out.append("chord" if sum(low[a:b]) >= 2 else "bass")
        else:
            out.append("treble")
    return out


def voices(note, hand: str, name: str, made: dict, ranks: list[str], bright: float) -> list[Voice]:
    """The reeds a note sounds."""
    frac = note.pitch - round(note.pitch)
    pc = int(round(note.pitch)) % 12
    if name == "concertina":
        pitch = _fold(float(note.pitch), *COMPASS)
        key = int(round(pitch))
        side = "left" if _staff_line(key) else "right"
        return [Voice(pitch, 1.0, side, RANK["concertina"], key, CONCERTINA.flow * _thirst(pitch), made["slopes"])]
    if hand == "bass":
        return [Voice(_octave_of(pc, low) + frac, g, "bass", RANK[low], _octave_of(pc, low), 3.0 * g * ACCORDION.flow,
                      BASS_SLOPES) for low, g in BASS_RANKS]
    if hand == "chord":
        return [Voice(_octave_of(pc, low) + frac, g + (0.25 * bright if low > 60 else 0.0), "bass", RANK[low],
                      _octave_of(pc, low), 1.2 * ACCORDION.flow, CHORD_SLOPES) for low, g in CHORD_RANKS]
    pitch = _fold(float(note.pitch), *TREBLE)
    key = int(round(pitch))
    spread = made["tremolo"] * tremolo(pitch) * made["uneven"][key] / 100.0
    dark = 0.35 if made["cassotto"] else 0.0  # the tone chamber: the fundamental kept, the overtones taken down
    slopes = made["slopes"]
    table = {"M": (0.0, 1.0, dark), "M+": (spread, 1.0, dark), "M-": (-spread, 1.0, dark), "L": (-12.0, 0.75, dark),
             "H": (12.0, 0.5, 0.15)}
    out = []
    for r in ranks:
        shift, g, darker = table[r]
        p = pitch + shift
        out.append(Voice(p, g, "treble", RANK[r], key, ACCORDION.flow * _thirst(p) * (1.4 if r == "L" else 1.0),
                         (slopes[0] + darker, slopes[1] + darker)))
    # a register changes the colour more than the loudness: its reeds' power levelled, a fuller one a little louder
    total = np.sqrt(sum(v.gain**2 for v in out))
    scale = len(out) ** 0.25 / total
    return [Voice(v.pitch, v.gain * scale, v.side, v.rank, v.key, v.flow, v.slopes) for v in out]


def _thirst(pitch: float) -> float:
    """How much more air a lower reed drinks than a middle one (a longer, wider slot)."""
    return 1.0 + float(np.clip((72.0 - pitch) / 24.0, 0.0, 1.5))


def _staff_line(key: int) -> bool:
    """Whether an English concertina plays this pitch with the left hand: the naturals on the treble staff's lines
    (and every other one on, C4 E4 G4 B4 D5 F5...) are at the left end, those in its spaces at the right; an
    accidental at the end of the natural below it."""
    octave, pc = divmod(key, 12)
    letter = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4, 9: 5, 10: 5, 11: 6}[pc]
    return (7 * (octave - 1) + letter) % 2 == 0  # C4 (60) is 28 steps above C0: even, a line


# --- the bellows ------------------------------------------------------------------------------------


@njit(cache=True, nogil=True)
def _arm(x, up, down):
    """The player's arm on the bellows: the pressure follows what the playing asks, quickly as it rises and more
    slowly as it eases."""
    y = np.zeros(x.shape[0])
    v = 0.0
    for i in range(x.shape[0]):
        a = up if x[i] > v else down
        v = a * v + (1.0 - a) * x[i]
        y[i] = v
    return y


def _swell(m: int) -> np.ndarray:
    """A swell through a note: in at a third, up to full a little before its middle, easing to 0.6 at its end."""
    x = np.linspace(0.0, 1.0, m)
    return np.where(x < 0.45, 0.35 + 0.65 * np.sin(0.5 * np.pi * x / 0.45), 1.0 - 0.4 * ((x - 0.45) / 0.55) ** 2)


def _asked(notes, sr: int, length: int) -> np.ndarray:
    """The pressure the playing asks for: each note's velocity while it sounds (a swell shaped through it), held
    over rests shorter than a second (the arm keeps squeezing with no key down) and let go over longer ones."""
    want = np.zeros(length)
    for n in notes:
        i0, i1 = int(round(n.start * sr)), min(length, int(round((n.start + n.dur) * sr)))
        if i1 > i0:
            v = float(np.clip(n.vel, 0.0, 1.0)) * (_swell(i1 - i0) if n.art == "swell" else 1.0)
            want[i0:i1] = np.maximum(want[i0:i1], v)
    sounding = want > 0
    edges = np.flatnonzero(np.diff(sounding.astype(np.int8)))
    for k in range(len(edges)):
        a = edges[k] + 1
        if sounding[a]:
            continue
        b = edges[k + 1] + 1 if k + 1 < len(edges) else length
        if b < length and b - a < sr:
            want[a:b] = want[a - 1]
    return want


def bellows(notes, reeds: list[list[Voice]], sr: int, length: int, kind: Kind, stroke: float,
            rng: np.random.Generator, tempo: float | None = None):
    """The bellows through the part: the pressure (0..1, the turns' dips in it), and the samples where they turn
    (the first stroke pulls them open; they push after the first turn, pull after the second...)."""
    pressure = _arm(_asked(notes, sr, length), float(np.exp(-1.0 / (0.01 * sr))), float(np.exp(-1.0 / (0.06 * sr))))
    load = np.zeros(length)  # litres a second the sounding reeds drink at full pressure
    busy = np.zeros(length, dtype=bool)
    for n, vs in zip(notes, reeds):
        i0, i1 = int(round(n.start * sr)), min(length, int(round((n.start + n.dur) * sr)))
        load[i0:i1] += sum(v.flow for v in vs)
        busy[i0:i1] = True
    used = np.concatenate([[0.0], np.cumsum(load * np.sqrt(pressure) / sr)])  # litres drawn by each sample
    starts = sorted({int(round(n.start * sr)) for n in notes if n.start * sr < length})
    shakes = {int(round(n.start * sr)): n for n in notes if n.art == "shake"}
    # where a player would rather turn: on a strong note (a bass button, or the loudest start within a second
    # either side: the oom of an oom-pah, a bar's first note), so the new stroke's push accents it
    loudest: dict[int, float] = {}
    for n in notes:
        i = int(round(n.start * sr))
        loudest[i] = max(loudest.get(i, 0.0), float(n.vel) + (1.0 if n.art == "bass" else 0.0))
    at = np.array(starts)
    strong = {i: loudest[i] >= 0.97 * max(loudest[j] for j in at[(at >= i - sr) & (at <= i + sr)])
              for i in starts}
    turns: list[int] = []
    last = starts[0] if starts else 0
    fill, habit = rng.uniform(0.55, 0.8), rng.uniform(*kind.habit)
    rest, room = int(0.1 * sr), int(0.2 * sr)

    def turn(at: int) -> None:
        nonlocal last, fill, habit
        turns.append(at)
        last = at
        fill, habit = rng.uniform(0.55, 0.8), rng.uniform(*kind.habit)

    def forced(until: int) -> None:  # the stroke's air is all used before `until`: the bellows must turn there
        while used[until] - used[last] > stroke:
            at = int(np.searchsorted(used, used[last] + stroke))
            if at <= last or at >= until:
                break
            turn(at)

    ahead = starts[1:] + [length]
    for k, i in enumerate(starts + [length]):
        forced(i)
        if i >= length:
            break
        drawn, ran = used[i] - used[last], (i - last) / sr
        clear = i > 0 and not busy[i - 1]
        rested = i > 0 and not busy[max(0, i - rest): i].any()
        short = used[ahead[k]] - used[last] > stroke  # the air would run out before the next note: turn now
        due = (rested and (drawn > 0.3 * stroke or ran > habit)) or (clear and drawn > fill * stroke)
        must = drawn > 0.92 * stroke or (short and drawn > 0.3 * stroke)
        if i > starts[0] and (must or (due and (strong[i] or drawn > 0.8 * stroke))):
            gap = busy[max(0, i - room): i][::-1]
            back = int(np.argmax(gap)) if gap.any() else len(gap)
            turn(i - back // 2 if clear else i)  # a practised player turns in the rest before the note
        if i in shakes:
            n = shakes[i]
            if tempo:  # the shake's pulse: the subdivision of the beat nearest six and a half a second
                rate = min((tempo / 60.0 * k for k in (2, 3, 4, 6)), key=lambda r: abs(np.log(r / 6.5)))
            else:
                rate = rng.uniform(5.0, 8.0)
            k = 1
            while n.start + k / rate < n.start + n.dur - 0.02:
                turn(int(round((n.start + k / rate) * sr)))
                k += 1
    turns = sorted(set(t for t in turns if 0 < t < length))
    dip = np.ones(length)
    for t in turns:
        w = max(4, int(rng.uniform(*kind.turn) * sr))
        lo, hi = max(0, t - w // 2), min(length, t + w // 2)
        x = (np.arange(lo, hi) - (t - w // 2)) / w
        dip[lo:hi] = np.minimum(dip[lo:hi], 1.0 - (1.0 - DIP) * np.sin(np.pi * x) ** 2)
    dip *= pressure  # (pressure * dip, where it lies)
    return dip, turns


# --- the sound -----------------------------------------------------------------------------------------


def _sounded(v: Voice, pulling: bool, pressure: np.ndarray, a: int, on: int, tail: int, sr: int, start: float,
             t90: float, release: float, bright: float, error: float, cache: dict, seed: int, phase: float,
             out: np.ndarray, air: np.ndarray, offset: int) -> None:
    """One reed speaking for `on` samples from sample `a` of its note, and dying away over `tail` more: its swing
    grows as a logistic whose rate follows the pressure, its tone brightens as the swing reaches through the slot,
    its pitch sags a hair as the pressure rises."""
    n = on + tail
    p = pressure[offset + a: offset + a + n]
    if len(p) < n:
        n = len(p)
        on = min(on, n)
    if n <= 0 or on <= 0:
        return
    rate = np.log(9.0 * (1.0 - start) / start) / t90 * np.maximum(p[:on] / 0.6, 0.05) ** 0.6
    swing = 1.0 / (1.0 + (1.0 - start) / start * np.exp(-np.cumsum(rate) / sr))
    open_ = np.ones(n)  # the pallet: open while the key is down, shut within a few milliseconds of its rising
    if n > on:
        swing = np.concatenate([swing, swing[-1] * np.exp(-np.arange(1, n - on + 1) / (release * sr))])
        open_[on:] = np.exp(-np.arange(1, n - on + 1) / (0.004 * sr))
    key = (int(round(v.pitch * 4)), v.rank, pulling)
    if key not in cache:
        f = midi_to_hz(round(v.pitch * 4) / 4.0)
        slopes = (v.slopes[0] + 0.08, v.slopes[1] + 0.08) if pulling else v.slopes
        # a low reed's pulses are heard as pulses (its harmonics too close for the ear to part): in phase below D3
        # (150 Hz), scattering by D4
        cache[key] = reed.tables(f, sr, np.random.default_rng([seed, key[0], v.rank, int(pulling)]), slopes,
                                 even=0.75 if pulling else 0.85, top=f * 1.03,
                                 pulse=float(np.clip((62.0 - v.pitch) / 12.0, 0.0, 1.0)))
    dark, brightw = cache[key]
    low = 1.0 + float(np.clip((60.0 - v.pitch) / 12.0, 0.0, 2.0))  # low reeds sag more
    # flatter pressed harder; a few cents sharp while the swing is small (near the reed's own frequency)
    cents = error - 2.5 * low * (p - 0.6) / 0.4 + 3.0 * (1.0 - swing)
    freq = midi_to_hz(v.pitch) * 2.0 ** (cents / 1200.0)
    mix = np.clip(0.25 + 0.5 * bright + 1.2 * (p - 0.6), 0.0, 1.0) * swing**1.5
    amp = v.gain * swing * 0.6 * (p / 0.6) ** 1.3
    reed._read_mix(dark, brightw, freq / sr, amp, mix, out, offset + a, phase)
    # the air through the slot: a puff as the pallet lifts, rushing through the slot until the tongue swings and
    # chokes it, then the flow past the swinging tongue
    puff = 2.5 * open_ * (1.0 - swing) ** 2
    air[offset + a: offset + a + n] += v.flow * np.sqrt(p) * (0.4 * open_ + 0.6 * swing + puff)


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The instrument's dry stereo stem, `length` samples (before its place and level)."""
    s = {"brightness": 0.5, "wear": 0.25, "ornament": 0.5, "body": 1.0, **settings}
    bright, wear = float(np.clip(s["brightness"], 0.0, 1.0)), float(np.clip(s["wear"], 0.0, 1.0))
    ornament, size = float(np.clip(s["ornament"], 0.0, 1.0)), float(s["body"])
    kind = CONCERTINA if name == "concertina" else ACCORDION
    made = maker(name, make, wear)
    notes = sorted((n for n in notes if n.start * sr < length and n.dur > 0 and np.isfinite(n.pitch)),
                   key=lambda n: (n.start, n.pitch))
    if not notes:
        return np.zeros((length, 2))
    ranks = register(made["box"], ornament, bright)
    who = hands(notes, name)
    reeds = [voices(n, h, name, made, ranks, bright) for n, h in zip(notes, who)]
    tempo = s.get("tempo")
    pressure, turns = bellows(notes, reeds, sr, length, kind, made["stroke"], rng,
                              float(tempo) if tempo else None)
    turn_at = np.array(turns, dtype=np.int64)
    sides = ("left", "right") if name == "concertina" else ("treble", "bass")
    out = {side: np.zeros(length) for side in sides}
    air = {side: np.zeros(length) for side in sides}
    clicks = {side: [] for side in sides}  # (sample, burst) in the order they were made: short, and far apart
    cache: dict = {}
    seed = made["seeds"][0]
    down_sos = butter(2, (1500.0, 5000.0), btype="bandpass", fs=sr, output="sos")
    up_sos = butter(2, (300.0, 1500.0), btype="bandpass", fs=sr, output="sos")
    clicked: set = set()
    last_end = -1.0
    for note, vs in zip(notes, reeds):
        i0 = int(round(note.start * sr))
        m = max(1, min(length - i0, int(round(note.dur * sr))))
        legato = note.art == "slur" and note.start - last_end < 0.02
        last_end = max(last_end, note.start + note.dur)
        inside = turn_at[(turn_at > i0) & (turn_at < i0 + m)] - i0
        bounds = [0] + [int(x) for x in inside] + [m]
        # which way the bellows run in each piece: pulling until the first turn, then pushing, then pulling...
        before = int(np.searchsorted(turn_at, i0, side="right"))
        for v in vs:
            t90 = speaking(v.pitch) * kind.speak
            release = min(0.025, max(0.006, 0.25 * t90))  # the pad shuts, the flow stops, the reed is gone
            for j, (a, b) in enumerate(zip(bounds[:-1], bounds[1:])):
                if b <= a:
                    continue
                pulling = (before + j) % 2 == 0
                tail = max(0, min(length - i0 - b, int(5.0 * release * sr)))
                error = float(made["errors"][v.key % 128, v.rank, int(pulling)])
                _sounded(v, pulling, pressure, a, b - a, tail, sr, 0.06 if legato and j == 0 else START, t90, release,
                         bright, error, cache, seed, float(rng.random()), out[v.side], air[v.side], i0)
        # the key goes down with a click (a bass button's mechanism clacks louder) and its pad shuts with a thud
        for side in {v.side for v in vs}:
            if (i0, side) in clicked:
                continue
            clicked.add((i0, side))
            c = min(length - i0, int(0.004 * sr))
            loud = CLICK * (1.0 + 2.0 * wear) * (1.6 if side == "bass" else 0.6 if name == "concertina" else 1.0)
            burst = sosfilt(down_sos, rng.standard_normal(c + 32))[32:] * np.exp(-np.arange(c) / (0.0008 * sr))
            if not legato:
                clicks[side].append((i0, burst * loud))
            j = i0 + m
            c = min(length - j, int(0.008 * sr))
            if c > 0:
                thud = sosfilt(up_sos, rng.standard_normal(c + 32))[32:] * np.exp(-np.arange(c) / (0.002 * sr))
                clicks[side].append((j, 0.7 * thud * loud))
    del pressure
    stereo = np.zeros((length, 2))
    hiss_sos = butter(2, (800.0, 8000.0), btype="bandpass", fs=sr, output="sos")
    dc = butter(1, 20.0, btype="highpass", fs=sr, output="sos")
    places = {"treble": (-0.3, 1.0), "bass": (0.3, 1.3), "left": (-0.25, 1.0), "right": (0.25, 1.0)}
    # Each side's dry sound, out + clicks + the hiss (the filtered noise * air * HISS * (1 + 3 wear)), made where the
    # reeds lie: the clicks a touching run at a time (each run summed from 0.0 in the order they were made, as a
    # whole track of them was; between runs that track is 0.0, which adds nothing to a sum begun from 0.0), the hiss
    # a stretch at a time (the noise drawn and filtered a stretch at a time, in order, the filter's state carried).
    for k, side in enumerate(sides):
        dry, air_side, bursts = out[side], air[side], clicks[side]
        out[side] = air[side] = clicks[side] = None
        if not dry.any():
            continue
        _lay_runs(dry, bursts)
        noise_rng = np.random.default_rng([made["seeds"][1], k])
        state = np.zeros((hiss_sos.shape[0], 2))
        for a in range(0, length, BLOCK):
            b = min(length, a + BLOCK)
            hiss, state = sosfilt(hiss_sos, noise_rng.standard_normal(b - a), zi=state)
            dry[a:b] += hiss * air_side[a:b] * HISS * (1.0 + 3.0 * wear)
        del air_side
        position, bigger = places[side]
        ir = body.impulse_response(kind.box, sr, seed=made["seeds"][2] + k, size=size * bigger, channels=1)[:, 0]
        # oaconvolve(dry, ir)[:length], a few blocks at a time; a reed's pulses of air carry DC: none leaves the box
        y = sosfilt(dc, oa.convolve(dry, ir, length))
        del dry
        theta = (position + 1.0) * np.pi / 4.0
        for a in range(0, length, BLOCK):
            stereo[a:a + BLOCK, 0] += y[a:a + BLOCK] * np.cos(theta) * np.sqrt(2.0)
            stereo[a:a + BLOCK, 1] += y[a:a + BLOCK] * np.sin(theta) * np.sqrt(2.0)
        del y
    return stereo


def _lay_runs(into: np.ndarray, bursts: list) -> None:
    """Short bursts (start, values), in the order they were made, added into `into` as a whole track of them would
    have been: each run of touching bursts summed from 0.0 in that order, then added."""
    spans = sorted(range(len(bursts)), key=lambda k: bursts[k][0])
    run, hi = [], -1
    for k in spans + [None]:
        start = None if k is None else bursts[k][0]
        if run and (k is None or start >= hi):
            lo = min(bursts[j][0] for j in run)
            local = np.zeros(hi - lo)
            for j in sorted(run):  # in the order they were made
                at, values = bursts[j]
                local[at - lo: at - lo + len(values)] += values
            into[lo:hi] += local
            run, hi = [], -1
        if k is not None:
            run.append(k)
            hi = max(hi, start + len(bursts[k][1]))
