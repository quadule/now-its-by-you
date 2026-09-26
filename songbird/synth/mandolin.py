"""A mandolin: four courses of paired steel strings, G3 D4 A4 E5, on a small carved box.

Each course is two strings in unison that are never quite: 1 to 6 cents apart as the instrument
wears, so a held note beats and shimmers, and the flat pick meets them up to two milliseconds
apart, one first on a down stroke and the other on an up (a note's two strings then partly cancel
or reinforce, differently each stroke, and drift through each other as they beat). The strings
(fretwork.py) are short (a 13 7/8-inch scale) and tight, and a small stiff box takes their energy
fast: the open G course falls 60 dB in about a second and a half, the E course's high notes in
half a second. That short ring is why mandolinists tremolo: a long note is filled with picks, down
and up, nine to fourteen a second, each landing on the course still ringing (fretwork.Stroke.picks).

The box follows Cohen and Rossing's measurements of four mandolins ("The acoustics of mandolins",
Acoust. Sci. & Tech. 24(1), 2003): the lowest body mode, where top and back breathe through the
sound hole, at 209 to 313 Hz (the air mode A0 between 214 and 293), a second (0,0) mode 130 to 270 Hz
higher, the top's (1,0) at 450 to 575 Hz, its (2,0) and (3,0) near 900 and 1100 Hz, and a broad
maximum of the response near 3.5 kHz; what it radiates is fairly even up to 5 kHz, falling from
about 2.5 kHz. A maker builds either an oval-hole mandolin (style "A", as an A-style's hole; the
modes of their oval-hole Gibson, the lowest at 209 Hz: warmer) or an f-hole one (style "F", as
an F-style's; their f-hole Gibson's, the lowest at 313 Hz: higher and drier, the bluegrass chop's
bark), each maker's modes a few percent from those. Below its lowest mode the box barely radiates,
so the G course's fundamental is weak, as on a real mandolin.

A chop (the bluegrass backbeat) is a chord struck down hard and choked at once by the fretting
hand: 30 to 60 ms of chord, the pick's scrape across the deadened strings, and the knock of the
hand and pick on the box. Chords are strummed a few milliseconds a course, low to high down and
high to low up, unless the part has already spread them.
"""

from __future__ import annotations

import numpy as np

from . import body, fretwork

SCALE_MM = 350.0  # 13 7/8 inches
OPENS = (55, 62, 69, 76)  # G3 D4 A4 E5
DECAY = 1.05  # s: an open course's decay at 220 Hz as pluck.py's (fretwork.Strings.decay)
GLIDE = 5.0  # cents a pick at velocity 1 starts sharp: short, tight strings stretch less
PULL = 0.3  # the break angle's pull over the bridge, weaker than a banjo's on its stiff top
FORCE = 1.0

ARTICULATIONS = {
    "": "a flat pick: down, or in a quick run down and up in turn",
    "down": "a down stroke of the flat pick (a chord spread from the G course to the E)",
    "up": "an up stroke: a little lighter, a chord spread from the E course back to the G",
    "tremolo": "the note's length filled with alternate picks, 9 to 14 a second (a subdivision of the beat when "
               "the tempo is known), each landing on the ringing course",
    "chop": "the bluegrass backbeat: a chord struck and choked at once by the fretting hand (30 to 60 ms of "
            "chord, the pick's scrape, the box's knock)",
    "hammer": "hammer-on: a left finger comes down on the ringing course, no pick",
    "pull": "pull-off: the left finger plucks the course as it leaves it",
    "slide": "picked two frets below the note and slid up to it",
    "mute": "a note struck and damped at once by the hand: a percussive, pitched tick",
}

SPEC = {
    "mandolin": dict(
        family="plucked",
        role="comping",
        register=(55, 88),
        place=(-0.35, 0.5),
        level=0.35,
        poly=True,
        articulations=ARTICULATIONS,
        about="a mandolin: four paired steel courses G3 D4 A4 E5 and a flat pick, on an A-style (oval hole) or "
              "F-style (f-holes) carved box; chops, strums, tremolo",
    )
}


def box(style: str, low: float, spread: np.ndarray, q: float, bright: float) -> body.Body:
    """The mandolin's body: its measured low modes for the style, moved by the maker (low: the lowest
    mode, Hz; spread: a factor for each of the others), and the dense top modes above."""
    # Ratios to the lowest mode (Q, dB) of the modes Cohen and Rossing measured (their Table 1): the (0,0)
    # triplet or pair, the top's (1,0), (1,1), the air's A1, (2,0) and (3,0). The modes stand only a
    # little above the rest: the measured sound spectra show small peaks at them.
    if style == "A":  # oval sound hole (their Gibson oval hole: 209, 398, 482, 575, 728, 805, 918, 1149 Hz)
        named = ((1.0, 14.0, 3.0), (1.90, 18.0, 2.0), (2.31, 20.0, 2.5), (2.75, 22.0, 3.0), (3.48, 20.0, 1.5),
                 (3.85, 18.0, 1.0), (4.39, 24.0, 2.5), (5.50, 24.0, 2.0))
        lowcut, highcut, tilt, hill = 0.8 * low, 10000.0, -1.2, (3500.0, 1.3, 3.5 + 2.0 * (bright - 0.5))
    else:  # f-holes (their f-hole Gibson: 313, 464, 570, 821, 886, 895, 1117 Hz): higher, drier, the bark
        named = ((1.0, 13.0, 3.0), (1.48, 18.0, 2.5), (1.82, 22.0, 3.5), (2.62, 20.0, 1.5), (2.83, 24.0, 2.5),
                 (2.86, 18.0, 1.0), (3.57, 24.0, 2.0))
        lowcut, highcut, tilt, hill = 0.7 * low, 11000.0, -0.8, (3500.0, 1.3, 4.5 + 2.0 * (bright - 0.5))
    modes = tuple((low * r * (spread[k % len(spread)] if k else 1.0), qq * q, db)
                  for k, (r, qq, db) in enumerate(named))
    return body.Body(modes=modes, dense=(1100.0, highcut, 120), tilt=tilt, q=(34.0, 22.0), direct=0.25,
                     lowcut=lowcut, highcut=highcut, hill=hill, length=0.3)


def _maker(make: np.random.Generator) -> dict:
    """This machine's mandolin: every draw in a fixed order, whatever the part."""
    seed = int(make.integers(1 << 30))
    style = "A" if make.random() < 0.5 else "F"
    low = float(make.uniform(200.0, 235.0) if style == "A" else make.uniform(295.0, 325.0))
    return dict(
        seed=seed, style=style, low=low,
        spread=make.uniform(0.96, 1.04, 8),
        q=float(make.uniform(0.85, 1.15)),
        pairs=make.uniform(0.6, 1.4, 4) * make.choice([-1.0, 1.0], 4),  # how far apart each course's strings sit
        offsets=make.normal(0.0, 1.0, 4),
        splits=make.uniform(0.2, 0.8, 4),
        twang=float(make.uniform(0.8, 1.2)),
        decay=float(make.uniform(0.9, 1.1)),
        near=float(make.uniform(45.0, 70.0)),  # mm from the bridge where the pick meets the strings
        rate=float(make.uniform(10.5, 12.5)),  # tremolo picks a second, unmeasured
        gap=float(make.uniform(0.5, 1.5)),  # ms between the pick meeting a course's two strings
    )


def tremolo_rate(settings: dict, own: float) -> float:
    """Picks a second: the subdivision of the beat (sixteenths, sixteenth triplets or thirty-seconds)
    nearest 11.5 within 9 to 14 when the tempo is known, else the player's own rate."""
    tempo = settings.get("tempo")
    if tempo:
        rates = [float(tempo) / 60.0 * m for m in (4, 6, 8)]
        inside = [r for r in rates if 9.0 <= r <= 14.0]
        if inside:
            return min(inside, key=lambda r: abs(r - 11.5))
    return own


def render(name: str, notes, sr: int, length: int, rng: np.random.Generator, make: np.random.Generator,
           settings: dict) -> np.ndarray:
    """The mandolin's part: dry stereo (the box heard by two microphones), `length` samples."""
    quirks = _maker(make)
    out = np.zeros((length, 2))
    notes = [n for n in notes if 0.0 <= n.start and int(round(n.start * sr)) < length and n.dur > 0.0]
    if not notes:
        return out
    bright = float(np.clip(settings.get("brightness", 0.5), 0.0, 1.0))
    wear = float(np.clip(settings.get("wear", 0.25), 0.0, 1.0))
    size = float(np.clip(settings.get("body", 1.0), 0.5, 2.0))
    rate = tremolo_rate(settings, quirks["rate"])

    board = fretwork.Board(opens=tuple(float(p) for p in OPENS), top=(17,) * 4, fretted=(True,) * 4,
                           order=(0, 1, 2, 3))
    fingered = fretwork.assign(notes, board)
    fretwork.spread(fingered, board, lambda art: {"chop": 0.009, "mute": 0.006, "tremolo": 0.006}.get(art, 0.016), rng)

    detune = (1.0 + 5.0 * wear) * quirks["pairs"]  # 1 to 6 cents between a course's strings
    loss = tuple(0.14 - 0.08 * bright + (0.05 if k < 2 else 0.0) for k in range(4))  # G and D courses wound
    strings = fretwork.Strings(
        loss=loss, decay=DECAY * quirks["decay"] * (1.0 - 0.15 * wear),
        offsets=tuple(quirks["offsets"] * (0.5 + 3.0 * wear)), splits=tuple(quirks["splits"]),
        members=tuple(((-d / 2.0, 1.0), (d / 2.0, 1.0)) for d in detune),
        glide=GLIDE * quirks["twang"], pull=PULL * quirks["twang"], level=FORCE, fretted_decay=0.85, along=2.0,
        touch_band=(200.0, 3000.0))

    spec = box(quirks["style"], quirks["low"], quirks["spread"], quirks["q"], bright)
    ir = body.impulse_response(spec, sr, seed=quirks["seed"], size=size)
    freqs, power = fretwork.body_power(ir, sr, place=SPEC["mandolin"]["place"])
    together: dict[float, int] = {}
    for f in fingered:
        together[round(f.note.start, 3)] = together.get(round(f.note.start, 3), 0) + 1
    strokes = []
    last = (-1.0, -1.0)  # the last single note's start and pick direction, for alternate picking
    for f in fingered:
        chord = together[round(f.note.start, 3)] > 1
        stroke, last = _stroke(f, chord, sr, quirks, bright, wear, rate, last, rng)
        strokes.append(stroke)
    # (no open courses ringing in sympathy: a chop's fretting hand lies across all four)
    force = fretwork.play(strokes, strings, sr, length, rng, freqs, power)
    return body.resonate(force, ir)


def _stroke(f: fretwork.Fingered, chord: bool, sr: int, q: dict, bright: float, wear: float, rate: float,
            last: tuple, rng: np.random.Generator) -> tuple[fretwork.Stroke, tuple]:
    """What the hands do for one fingered note, alone or in a chord (and the pick's last direction)."""
    note = f.note
    art = note.art if note.art in ARTICULATIONS else ""
    sounding = SCALE_MM * 2.0 ** (-f.fret / 12.0)
    at = int(round(f.start * sr))
    until = int(round((note.start + note.dur) * sr))
    vel = float(np.clip(note.vel, 0.0, 1.0))
    edge = 0.3 + 0.7 * vel  # a harder stroke meets the string with a sharper edge
    direction = 1.0
    if art == "up":
        direction = -1.0
    elif art == "" and not chord:
        # a run of quick notes is picked down and up in turn
        if note.start - last[0] < 0.26 and last[1] > 0:
            direction = -1.0
    if not chord:
        last = (note.start, direction)
    s = fretwork.Stroke(string=f.string, at=at, until=until, pitch=f.pitch, fret=f.fret, vel=vel,
                        roughness=0.3 + 0.3 * wear, touch=0.25, pair=q["gap"] * 1e-3)
    s.beta = q["near"] * (1.1 - 0.2 * bright) / sounding
    s.hardness = (0.88 + 0.1 * bright) * edge
    s.planes = 0.3
    s.click = ((0.25 + 0.1 * bright) * (0.4 + vel), 3000.0, 2.5)
    s.picks = ((0, 1.0 if direction > 0 else 0.88, direction),)
    if art == "tremolo":
        step = sr / rate
        count = max(1, int((note.dur * rate) + 0.5))
        picks = []
        for k in range(count):
            jitter = rng.normal(0.0, 0.003) * sr if k else 0.0
            down = k % 2 == 0
            picks.append((int(k * step + jitter), (0.78 if down else 0.68) * (1.0 + 0.06 * rng.standard_normal()),
                          1.0 if down else -1.0))
        s.picks = tuple(picks)
    elif art == "chop":
        s.until = min(s.until, at + int((0.03 + 0.03 * rng.random()) * sr))
        s.damp, s.scrape, s.knock, s.touch = 0.02, 0.35, 0.3, 0.0
    elif art == "mute":
        s.until = min(s.until, at + int((0.012 + 0.008 * rng.random()) * sr))
        s.damp, s.scrape, s.knock, s.gain, s.touch = 0.02, 0.12, 0.1, 0.8, 0.0
    elif art == "hammer":
        s.kind, s.picks = "hammer", ((0, 0.3, 1.0),)
        s.beta, s.hardness, s.planes, s.click, s.twang = 0.03, 0.1, 0.2, (0.04, 1500.0, 2.5), 0.0
    elif art == "pull":
        s.kind, s.picks = "pull", ((0, 0.6, -1.0),)
        s.beta, s.hardness, s.planes, s.click, s.twang = 0.1, 0.25, 0.4, (0.0, 2000.0, 1.0), 0.0
    elif art == "slide":
        s.slide, s.slide_time = float(min(2, f.fret)), 0.06 + 0.02 * rng.random()  # from two frets below, if it can
    s.beta = float(np.clip(s.beta, 0.02, 0.5))
    return s, last
