"""A five-string banjo: four long steel strings and the short fifth, the drone, over a drum.

The tuning is open-G style moved to the song's key: the four long strings sound the key's major
chord, as open G does (gDGBD: the fifth below, the root, the third, the fifth) with its lowest string
kept near D3 by a capo of up to five frets; keys from C# to F take open D's shape instead (f#DF#AD
with its fifth string tuned to the key: the root, third, fifth and root), which is how banjo players
play in D. The fifth string, which starts at the fifth fret and is played by the thumb, is tuned to
the key's tonic or fifth, whichever lies nearer G4 (from E4 to B4): G4 in G, A4 in D and A. Every
note of the drone's pitch is played on it.

The strings (fretwork.py) are steel, picked near the bridge, and ring on a light bridge standing on
a drumhead, which takes their energy fast: an open string falls 60 dB in one to two seconds, a
fretted one sooner, high notes sooner still. A hard pick stretches the string: the pitch starts up
to 15 cents sharp and falls back in about a tenth of a second (the twang), and the swinging tension
pulls the bridge down through the strings' break angle at twice the frequency of each harmonic, more
for a loud pick than a soft one (Politzer, "Banjo timbre from string stretching and frequency
modulation", Acta Acustica 2015).

The head is an 11-inch Mylar membrane: its modes lie at the ratios of an ideal membrane's (the (0,1)
at 380-430 Hz on a bluegrass player's tight head, 290-360 on an old-time player's slacker open back,
by maker, brightness and wear, then (1,1) at 1.59 times it, (2,1) at 2.14, (0,2)
at 2.30 and so on; Q 20 to 40), each driven by the bridge as far as the bridge stands on its moving
parts, and radiating well from about 400 Hz up (a head is as wide as the sound's wavelength there),
then a scatter of the head's crowded upper modes to 12 kHz: most of what a banjo radiates lies
between 400 and 1800 Hz and above (Rae and Rossing; Stephey and Moore, JASA 2008; Politzer, "Banjo
drum physics", 2018). A resonator (a bluegrass banjo) closes the back: an air resonance of the pot
near 200 Hz and all its lows kept, brighter and louder. An open back (old time) lets the back of the
head cancel the front below its first mode, 12 dB an octave, and is mellower above. Which one plays
follows the part's style (mostly clawhammer: an open back; picks: a resonator) and, for a few makers,
the other way round.

The hands: see ARTICULATIONS. One banjo may be played both ways in a song (the string band's
clawhammer verses and rolled refrains): a clawhammer passage's plain notes and thumb are the nail's
and the thumb's flesh; a picked passage's the fingerpicks' and a thumbpick's.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, sosfreqz
from scipy.special import jv

from . import body, fretwork, pluck

SCALE_MM = 667.0  # the long strings' scale: 26 1/4 inches
HEAD_RADIUS = 0.1397  # m: an 11-inch head
DECAY = 1.35  # s: an open string's decay at 220 Hz as pluck.py's (fretwork.Strings.decay)
GLIDE = 15.0  # cents a pick at velocity 1 starts sharp
PULL = 0.6  # the break angle's pull: its 2f at velocity 1 about 21 dB under the fundamental
FORCE = 1.0  # the strings' force scale

ARTICULATIONS = {
    "": "the passage's plain stroke: the nail where it is clawhammer, a fingerpick where it is picked",
    "pick": "three-finger style: a metal fingerpick near the bridge, very bright and clicky",
    "claw": "clawhammer: the nail strikes down over the end of the neck: rounder, with a knock",
    "brush": "clawhammer brush: the nail down across the strings of a chord, low to high",
    "thumb": "the thumb: on the fifth string's drone (or whichever string holds the note)",
    "hammer": "hammer-on: a left finger comes down on the ringing string, no pick",
    "pull": "pull-off: the left finger plucks the string as it leaves it",
    "slide": "picked two frets below the note and slid up to it",
    "mute": "a muted strike: the left hand damps the string as it is struck",
    "chop": "a chord struck and choked at once by the left hand (the backbeat)",
}

SPEC = {
    "banjo": dict(
        family="plucked",
        role="comping",
        register=(50, 84),
        place=(0.3, 0.5),
        level=0.41,
        poly=True,
        articulations=ARTICULATIONS,
        about="a five-string banjo, open-G style tuning moved to the key with the fifth string on the tonic "
              "or fifth; steel strings on an 11-inch head, with a resonator (picked) or open back (clawhammer)",
    )
}

# An ideal membrane's modes: (m, n, the Bessel zero j_mn)
MEMBRANE = ((0, 1, 2.4048), (1, 1, 3.8317), (2, 1, 5.1356), (0, 2, 5.5201), (3, 1, 6.3802), (1, 2, 7.0156),
            (4, 1, 7.5883), (2, 2, 8.4172), (0, 3, 8.6537), (5, 1, 8.7715))


def tuning(tonic: int) -> tuple[tuple[int, int, int, int], int, int]:
    """The open strings for a key: (first, second, third, fourth), the fifth string, and the capo."""
    t = int(tonic) % 12
    if t in (1, 2, 3, 4, 5):  # open D's shape: root, third, fifth, root
        k = t - 2
        fourth = 50 + k
        longs = (fourth + 12, fourth + 7, fourth + 4, fourth)
    else:  # open G's: the fifth below, root, third, fifth
        k = (t - 7) % 12
        k = k - 12 if k > 6 else k
        fourth = 50 + k
        longs = (fourth + 12, fourth + 9, fourth + 5, fourth)
    return longs, fifth_string(tonic), max(k, 0)


def long_strings(tonic: int) -> tuple[int, int, int, int]:
    """The four long strings' open pitches for a key, the first (highest) to the fourth, capo included: a
    part-writer's chord shapes near the nut (idioms.first_position) are made on them."""
    return tuning(tonic)[0]


def fifth_string(tonic: int) -> int:
    """The short fifth string's pitch for a key: its tonic or fifth, whichever lies nearer G4 (from E4 to
    B4; the tonic if both are as near). A part-writer's drone (idioms.roll_notes) asks for it here."""
    t = int(tonic) % 12
    pcs = (t, (t + 7) % 12)
    return min((p for p in range(64, 72) if p % 12 in pcs), key=lambda p: (abs(p - 67), p % 12 != t))


def head(f1: float, q: float, bridge: float, resonator: bool, helm: float, bright: float) -> body.Body:
    """The drumhead as a body: its membrane modes from (0,1) at f1, each as strongly as the bridge
    (at `bridge` of the radius from the centre) drives it and the head radiates it, the pot's air
    resonance at `helm`, and the head's crowded upper modes."""
    modes = []
    for m, n, j in MEMBRANE:
        f = f1 * j / MEMBRANE[0][2]
        drive = abs(jv(m, j * bridge) / jv(m + 1, j))
        ka = 2.0 * np.pi * f * HEAD_RADIUS / 343.0
        # every mode radiates poorly while the head is small against the wavelength (ka under 1: below
        # about 390 Hz); a round mode pushes air as a whole (less with more nodal circles), one with
        # nodal diameters only once the head is about as wide as the wavelength
        radiate = ka / np.sqrt(1.0 + ka * ka) * (MEMBRANE[0][2] / j if m == 0 else ka**m / (1.0 + ka**m))
        modes.append((f, q * (1.0 + 0.05 * (n - 1)), 20.0 * np.log10(drive * radiate + 1e-6)))
    top = max(db for _, _, db in modes)
    modes = [(f, qq, db - top + 4.0) for f, qq, db in modes]
    modes.append((helm, 10.0, 1.0) if resonator else (helm * 0.85, 8.0, -4.0))
    bright_db = 2.0 * (bright - 0.5)
    # above the named modes the head's modes crowd together and a light, tight membrane radiates them
    # all well: the banjo's bright presence, strongest from about 1.5 to 5 kHz
    if resonator:
        return body.Body(modes=tuple(modes), dense=(3.5 * f1, 12000.0, 130), tilt=0.0, q=(35.0, 24.0),
                         direct=0.3, lowcut=90.0, highcut=12000.0, hill=(2800.0, 2.0, 6.0 + bright_db), length=0.3)
    return body.Body(modes=tuple(modes), dense=(3.5 * f1, 10000.0, 120), tilt=-0.8, q=(32.0, 22.0),
                     direct=0.25, lowcut=120.0, highcut=10000.0, hill=(2500.0, 2.0, 4.0 + bright_db), length=0.3)


def head_mode(tension: float, resonator: bool) -> float:
    """The head's (0,1) mode, Hz, for a player's tension (0 to 1): bluegrass players tune a resonator
    banjo's head tight, its tap tone G#4 to A4 (380 to 430 Hz); old-time players keep an open back's
    slacker and warmer (290 to 360 Hz)."""
    return 380.0 + 50.0 * tension if resonator else 290.0 + 70.0 * tension


def neck(tonic: int) -> fretwork.Board:
    """The strings as the left hand sees them: the first to fourth, then the fifth (index 4), which is
    played open only and plays every note of its pitch; a down stroke meets the fifth first."""
    longs, drone, capo = tuning(tonic)
    return fretwork.Board(opens=(*map(float, longs), float(drone)), top=(22 - capo,) * 4 + (0,),
                          fretted=(True, True, True, True, False), order=(4, 3, 2, 1, 0), drone=4)


def style(notes, back: float) -> tuple[bool, bool]:
    """(clawhammer, resonator): a part mostly struck with the nail is clawhammer, and is played on an
    open back; a picked one on a resonator; a maker whose `back` draw is under 0.12 plays the other."""
    struck = sum(1 for n in notes if n.art in ("claw", "brush"))
    picked = sum(1 for n in notes if n.art == "pick")
    clawhammer = struck > picked
    return clawhammer, (not clawhammer) if back > 0.12 else clawhammer


def hands(notes, clawhammer: bool, reach: float = 2.0) -> list[bool]:
    """For each note, whether its passage is clawhammer (True) or picked (False): a song whose verses are
    clawhammer and refrains rolls is played so, on the one banjo. A note that names the nail (claw,
    brush) or a pick is played so; any other (the thumb, a plain note, a hammer-on) as the nearest note
    that does, within `reach` seconds, or as the part mostly is."""
    marked = [(n.start, n.art in ("claw", "brush")) for n in notes if n.art in ("claw", "brush", "pick")]
    if not marked:
        return [clawhammer] * len(notes)
    at = np.array([t for t, _ in marked])
    nail = np.array([m for _, m in marked])
    out = []
    for n in notes:
        if n.art in ("claw", "brush", "pick"):
            out.append(n.art != "pick")
            continue
        k = int(np.argmin(np.abs(at - n.start)))
        out.append(bool(nail[k]) if abs(at[k] - n.start) <= reach else clawhammer)
    return out


def _maker(make: np.random.Generator) -> dict:
    """This machine's banjo: every draw in a fixed order, whatever the part."""
    return dict(
        seed=int(make.integers(1 << 30)),
        back=float(make.random()),  # under 0.12: this player chose the other back for their style
        tension=float(make.random()),  # how tight this player keeps the head, 0 to 1 (see head_mode)
        q=float(make.uniform(22.0, 36.0)),
        bridge=float(make.uniform(0.28, 0.4)),
        helm=float(make.uniform(170.0, 230.0)),
        offsets=make.normal(0.0, 1.0, 5),
        splits=make.uniform(0.2, 0.8, 5),
        twang=float(make.uniform(0.8, 1.25)),  # the break angle over the bridge, the tailpiece's setting
        decay=float(make.uniform(0.9, 1.1)),
        near=float(make.uniform(40.0, 60.0)),  # mm from the bridge where the fingerpicks meet the strings
        over=float(make.uniform(170.0, 230.0)),  # mm from the bridge where the nail strikes
    )


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The banjo's part: dry stereo (the head heard by two microphones), `length` samples."""
    quirks = _maker(make)
    out = np.zeros((length, 2))
    notes = [n for n in notes if 0.0 <= n.start and int(round(n.start * sr)) < length and n.dur > 0.0]
    if not notes:
        return out
    bright = float(np.clip(settings.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(settings.get("wear", 0.25), 0.0, 1.0))
    size = float(np.clip(settings.get("body", 1.0), 0.5, 2.0))
    tonic = int(settings.get("tonic", 62))

    clawhammer, resonator = style(notes, quirks["back"])
    nail = {id(n): m for n, m in zip(notes, hands(notes, clawhammer))}

    longs, drone, capo = tuning(tonic)
    fingered = fretwork.assign(notes, board := neck(tonic))
    fretwork.spread(fingered, board, lambda art: {"brush": 0.022, "up": 0.016, "chop": 0.008, "mute": 0.008}.get(
        art, 0.003), rng)

    # steel strings losing little in the loop: the head takes their energy, not the string itself
    loss = tuple(0.15 - 0.1 * bright + (0.06 if k == 3 else 0.0) for k in range(5))  # the wound fourth duller
    strings = fretwork.Strings(
        loss=loss, decay=DECAY * quirks["decay"] * (1.0 - 0.15 * wear),
        offsets=tuple(quirks["offsets"] * (0.5 + 4.0 * wear)),  # each string a little off, more when worn
        splits=tuple(quirks["splits"]), glide=GLIDE * quirks["twang"], pull=PULL * quirks["twang"], level=FORCE,
        fretted_decay=0.85, along=2.0, touch_band=(150.0, 2500.0))

    # the head: tighter is higher and brighter, a worn one slacker and duller
    f1 = head_mode(quirks["tension"], resonator) * 2.0 ** ((bright - 0.5) * 0.2) * (1.0 - 0.08 * wear)
    spec = head(f1, quirks["q"] * (1.0 - 0.2 * wear), quirks["bridge"], resonator, quirks["helm"], bright)
    ir = body.impulse_response(spec, sr, seed=quirks["seed"], size=size)
    back = None if resonator else butter(2, 0.75 * f1 / size, btype="highpass", fs=sr, output="sos")

    def behind(freqs: np.ndarray) -> np.ndarray:
        if back is None:
            return np.ones(len(freqs))
        return np.abs(sosfreqz(back, worN=freqs, fs=sr)[1]) ** 2

    freqs, power = fretwork.body_power(ir, sr, behind, place=SPEC["banjo"]["place"])
    strokes = [_stroke(f, sr, quirks, bright, wear, nail[id(f.note)], capo, drone, rng) for f in fingered]
    force = fretwork.play(strokes, strings, sr, length, rng, freqs, power)
    # the drone, never fretted, answers what shares its harmonics (a D string's third harmonic is the A
    # drone's second): the sympathetic ring Politzer counts among the banjo's brightness
    force = force + pluck.sympathetic(force, sr, [drone], coupling=0.0015, decay=1.5, brightness=0.4)
    out = body.resonate(force, ir)
    if back is not None:
        out = sosfilt(back, out, axis=0)
    return out


def _stroke(f: fretwork.Fingered, sr: int, q: dict, bright: float, wear: float, clawhammer: bool, capo: int,
            drone: int, rng: np.random.Generator) -> fretwork.Stroke:
    """What the hands do for one fingered note (clawhammer: whether its passage is played with the nail)."""
    note = f.note
    art = note.art if note.art in ARTICULATIONS else ""
    plain = "claw" if clawhammer else "pick"
    if art == "":
        art = plain
    if f.string == 4 and art in ("pick", "claw"):
        art = "thumb"  # the fifth string is the thumb's
    if f.string == 4:
        sounding = SCALE_MM * 2.0 ** (-5.0 / 12.0) * 2.0 ** (-(drone - 67) / 12.0)
    else:
        sounding = SCALE_MM * 2.0 ** (-(capo + f.fret) / 12.0)
    at = int(round(f.start * sr))
    until = int(round((note.start + note.dur) * sr))
    vel = float(np.clip(note.vel, 0.0, 1.0))
    rough = 0.3 + 0.3 * wear
    edge = 0.3 + 0.7 * vel  # a harder stroke meets the string with a sharper edge: brighter as well as louder
    s = fretwork.Stroke(string=f.string, at=at, until=until, pitch=f.pitch, fret=f.fret, vel=vel, roughness=rough,
                        touch=0.3)

    def picker(stroke: fretwork.Stroke) -> None:
        stroke.beta = q["near"] * (1.15 - 0.3 * bright) / sounding
        stroke.hardness = (0.9 + 0.08 * bright) * edge
        # a metal fingerpick lets a steel string go at once, the more sharply the harder it is played: its corner
        # is kept to 9-12 kHz as a roll is played (vel 0.6-0.75), 4 kHz in the softest touch
        stroke.cutoff = max(2500.0, 16700.0 * vel - 1000.0) * (0.9 + 0.2 * bright)
        stroke.planes = 0.3
        stroke.click = ((0.3 + 0.1 * bright) * (0.4 + vel), 4000.0, 2.0)

    def nail(stroke: fretwork.Stroke, soft: float = 1.0) -> None:
        stroke.beta = q["over"] / sounding
        stroke.hardness = (0.7 + 0.1 * bright) * soft * edge
        stroke.planes = 0.12
        stroke.click = (0.2 * soft * (0.4 + vel), 2000.0, 1.5)
        stroke.knock = 0.12 * soft
        stroke.twang = 0.9

    base = art
    if art in ("slide", "mute", "chop"):
        base = plain
    if base == "pick":
        picker(s)
    elif base == "claw":
        nail(s)
    elif base == "brush":
        nail(s, 0.85)
        s.gain = 0.85
    elif base == "thumb":
        if clawhammer:  # the thumb's flesh catches the drone and lets it go
            s.beta, s.hardness, s.planes, s.gain = q["over"] / sounding, 0.4 * edge, 0.3, 0.85
            s.click = (0.03 * (0.4 + vel), 2000.0, 1.0)
        else:  # a plastic thumbpick: a little rounder than the metal ones
            picker(s)
            s.beta *= 1.2
            s.hardness, s.click, s.gain = 0.8 * edge, (0.2 * (0.4 + vel), 3500.0, 2.0), 1.0
            s.cutoff = (7500.0 + 2500.0 * vel) * (0.9 + 0.2 * bright)
    elif base == "hammer":
        s.kind, s.picks = "hammer", ((0, 0.3, 1.0),)
        s.beta, s.hardness, s.planes, s.click, s.twang = 0.03, 0.1, 0.2, (0.04, 1500.0, 2.5), 0.0
    elif base == "pull":
        s.kind, s.picks = "pull", ((0, 0.6, -1.0),)
        s.beta, s.hardness, s.planes, s.click, s.twang = 0.1, 0.25, 0.4, (0.0, 2000.0, 1.0), 0.0
    if art == "slide":
        s.slide, s.slide_time = float(min(2, f.fret)), 0.07 + 0.02 * rng.random()  # from two frets below, if it can
    elif art == "mute":
        s.until = min(s.until, at + int((0.015 + 0.01 * rng.random()) * sr))
        s.damp, s.scrape, s.knock, s.gain, s.touch = 0.02, 0.15, max(s.knock, 0.1), 0.8, 0.0
    elif art == "chop":
        s.until = min(s.until, at + int((0.03 + 0.03 * rng.random()) * sr))
        s.damp, s.scrape, s.knock, s.gain, s.touch = 0.02, 0.3, max(s.knock, 0.25), 0.9, 0.0
    s.beta = float(np.clip(s.beta, 0.02, 0.5))
    return s
