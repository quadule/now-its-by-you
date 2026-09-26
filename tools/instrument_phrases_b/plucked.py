"""The banjo's and the mandolin's phrases, in D, and their calibration parts.

The banjo is tuned for D as open D with its fifth string on A (D3 F#3 A3 D4, the fifth string A4): its
open strings are the D chord, so a roll over D is all open strings and the drone rings through the rest.
The mandolin is tuned G3 D4 A4 E5 whatever the key. Written as a part-writer would: every note's
duration is how long its string should ring (in a roll, until that string is picked again or the chord
changes), and a chord's notes start together (the instrument spreads them itself).

LEVELS: each instrument's comping part (forward rolls; strums and chops), whose placed loudness should
meet the comping target. LEADS: each one's break, the tune stated in its own idiom at the velocity a
style's lead is played at (about 0.75), measured against the lead target by --levels.
"""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"banjo": "banjo", "mandolin": "mandolin"}

# --- the banjo -----------------------------------------------------------------------------------

# A forward roll (thumb, index, middle; thumb, index, middle; thumb, middle) through a chord's shape on
# the banjo tuned for D: the thumb on the third string, then the fifth string's drone.
ROLL_SHAPES = {
    "D": ["F#3", "A3", "D4", "A4", "A3", "D4", "A4", "D4"],
    "G": ["G3", "B3", "D4", "A4", "B3", "D4", "A4", "D4"],
    "A": ["A3", "C#4", "E4", "A4", "C#4", "E4", "A4", "E4"],
    "Bm": ["F#3", "B3", "D4", "A4", "B3", "D4", "A4", "D4"],
}


def forward_roll(clock: Clock, chords, vel: float = 0.6, start: float = 0.0, art: str = "pick") -> list:
    """Eighth-note forward rolls, a bar a chord; each string rings until it is picked again or the chord changes."""
    notes = []
    for bar, name in enumerate(chords):
        shape = ROLL_SHAPES[name]
        for k, n in enumerate(shape):
            beat = start + 4.0 * bar + 0.5 * k
            again = next((j for j in range(k + 1, 8) if shape[j] == n), 8)  # the same string picked again
            accent = 1.1 if k in (0, 3, 6) else 1.0  # the thumb's beats of the 3-3-2
            notes.append(clock.note("banjo", beat, 0.5 * (again - k), pitch(n), min(1.0, vel * accent), art))
    return notes


def _scruggs() -> list:
    """Two bars of forward rolls, then a break: the tune's notes on the beat inside rolls, a slide into
    the third string, a hammer-on, a pull-off, and the D chord pinched to end."""
    c = Clock(112)
    notes = forward_roll(c, ["D", "D"], vel=0.55)
    melody = [  # (beat, pitch, art) of the tune inside the rolls: the melody on the beat, fills between
        (8.0, "F#4", "pick"), (8.5, "A3", "pick"), (9.0, "D4", "pick"), (9.5, "A4", "thumb"),
        (10.0, "A4", "pick"), (10.5, "D4", "pick"), (11.0, "F#4", "pick"), (11.5, "A4", "thumb"),
        (12.0, "F#3", "slide"), (12.5, "A3", "pick"), (13.0, "D4", "pick"),
        (13.5, "A4", "thumb"), (14.0, "E4", "pick"), (14.25, "F#4", "hammer"), (14.5, "A3", "pick"),
        (15.0, "E4", "pick"), (15.25, "D4", "pull"), (15.5, "A4", "thumb"),
    ]
    tune = {"F#4", "A4", "E4", "D4"}
    for k, (beat, name, art) in enumerate(melody):
        nxt = melody[k + 1][0] if k + 1 < len(melody) else beat + 1.0
        vel = 0.68 if (beat % 1.0 == 0.0 and name in tune) else 0.52
        notes.append(c.note("banjo", beat, max(0.25, nxt - beat + 0.25), pitch(name), vel, art))
    notes += [c.note("banjo", 16.0, 2.0, p, 0.72, "pick") for p in chord("D3", "A3", "D4")]  # the pinch
    notes.append(c.note("banjo", 16.0, 2.0, pitch("A4"), 0.6, "thumb"))
    return notes


def bum_ditty(clock: Clock, bars, vel: float = 0.6, start: float = 0.0) -> list:
    """Clawhammer: each beat a melody note struck down with the nail (bum), or a brush across the chord
    on the beat and the thumb catching the drone on the off-beat (di-ty)."""
    notes = []
    for b, (bum1, bum2, brush) in enumerate(bars):
        for half, bum in enumerate((bum1, bum2)):
            beat = start + 4.0 * b + 2.0 * half
            notes.append(clock.note("banjo", beat, 1.0, pitch(bum), vel * 1.05, "claw"))
            notes += [clock.note("banjo", beat + 1.0, 0.5, p, vel * 0.8, "brush") for p in chord(*brush)]
            notes.append(clock.note("banjo", beat + 1.5, 0.5, pitch("A4"), vel * 0.75, "thumb"))
    return notes


def _clawhammer() -> list:
    """Old-time clawhammer in D: bum-ditty through a tune, a hammer-on and a pull-off in the melody."""
    c = Clock(104)
    bars = [("D4", "F#4", ("D4", "A3", "F#3")), ("A3", "F#3", ("D4", "A3", "F#3")),
            ("G3", "B3", ("D4", "B3", "G3")), ("E4", "C#4", ("E4", "C#4", "A3")),
            ("D4", "F#4", ("D4", "A3", "F#3")), ("E4", "A3", ("E4", "C#4", "A3"))]
    notes = bum_ditty(c, bars, vel=0.6)
    # a hammer-on from the open third string, a pull-off on the first
    for beat, beats, name, vel, art in ((24.0, 0.5, "F#3", 0.62, "claw"), (24.5, 0.5, "G3", 0.6, "hammer"),
                                        (25.0, 0.5, "E4", 0.62, "claw"), (25.5, 1.5, "D4", 0.6, "pull"),
                                        (27.0, 1.0, "A4", 0.5, "thumb")):
        notes.append(c.note("banjo", beat, beats, pitch(name), vel, art))
    notes += [c.note("banjo", 28.0, 2.5, p, 0.66, "brush") for p in chord("D4", "A3", "F#3", "D3")]
    return notes


def _backup() -> list:
    """Bluegrass backup: a vamp, choked chords on the backbeat, under a singer."""
    c = Clock(120)
    shapes = {"D": ("A3", "D4", "F#4"), "G": ("B3", "D4", "G4"), "A": ("C#4", "E4", "A4")}  # closed: frets 3-5, 5, 7
    notes = []
    for bar, name in enumerate(["D", "D", "G", "G", "A", "A", "D", "D"]):
        for beat in (1.0, 3.0):
            notes += [c.note("banjo", 4.0 * bar + beat, 0.25, p, 0.6, "chop") for p in chord(*shapes[name])]
        notes.append(c.note("banjo", 4.0 * bar, 1.0, pitch({"D": "D3", "G": "G3", "A": "A3"}[name]), 0.55, "thumb"))
    return notes


# --- the mandolin --------------------------------------------------------------------------------

STRUMS = {"D": ("A3", "D4", "A4", "F#5"), "G": ("G3", "D4", "B4", "G5"), "A": ("A3", "E4", "C#5", "A5")}
CHOPS = {"D": ("A3", "F#4", "D5", "F#5"), "G": ("B3", "G4", "D5", "G5"), "A": ("C#4", "A4", "E5", "A5")}


def chop_comping(clock: Clock, chords, vel: float = 0.6, start: float = 0.0) -> list:
    """Bluegrass comping: an open chord strummed down on 1 and 3 (and up on 3's off-beat), a closed
    chord chopped on the backbeat, 2 and 4."""
    notes = []
    for bar, name in enumerate(chords):
        at = start + 4.0 * bar
        notes += [clock.note("mandolin", at, 1.0, pitch(p), vel, "down") for p in STRUMS[name]]
        notes += [clock.note("mandolin", at + 2.0, 0.5, pitch(p), vel, "down") for p in STRUMS[name]]
        notes += [clock.note("mandolin", at + 2.5, 0.5, pitch(p), vel * 0.8, "up") for p in STRUMS[name][1:]]
        for beat in (1.0, 3.0):
            notes += [clock.note("mandolin", at + beat, 0.25, pitch(p), vel, "chop") for p in CHOPS[name]]
    return notes


def _chop() -> list:
    """Backup: strums and backbeat chops through D, G, A, D."""
    return chop_comping(Clock(116), ["D", "D", "G", "G", "A", "A", "D", "D"])


TUNE = [  # a tune in D, (beats, note): a waltz-like air for the tremolo, three to the bar
    (2, "A4"), (1, "D5"), (3, "F#5"), (2, "E5"), (1, "D5"), (3, "B4"),
    (2, "A4"), (1, "B4"), (2, "D5"), (1, "E5"), (3, "F#5"), (3, "E5"),
]


def _tremolo() -> list:
    """A slow air: long notes tremoloed, short ones picked, and a strummed D to end."""
    c = Clock(84)
    notes, beat = [], 0.0
    for beats, name in TUNE:
        art = "tremolo" if beats >= 2 else ""
        notes.append(c.note("mandolin", beat, beats - 0.05, pitch(name), 0.62, art))
        beat += beats
    notes += [c.note("mandolin", beat, 3.0, pitch(p), 0.62, "tremolo") for p in ("A4", "D5")]  # a double stop
    notes += [c.note("mandolin", beat + 3.0, 3.0, pitch(p), 0.66, "down") for p in STRUMS["D"]]
    return notes


REEL = ["D4", "F#4", "A4", "F#4", "D5", "A4", "F#4", "A4", "G4", "B4", "D5", "B4", "A4", "F#4", "E4", "D4",
        "E4", "F#4", "G4", "E4", "F#4", "A4", "D5", "C#5", "B4", "G4", "E4", "G4", "F#4", "D4", "D4", "D4"]


def _reel() -> list:
    """A fiddle tune's eighth notes, picked down and up in turn, a hammer-on, a slide into a long note."""
    c = Clock(112)
    notes = []
    for k, name in enumerate(REEL):
        art = ""
        if k in (9,):
            art = "hammer"
        if k == 21:
            art = "slide"
        notes.append(c.note("mandolin", 0.5 * k, 0.5, pitch(name), 0.64 if k % 2 == 0 else 0.56, art))
    notes[-1] = c.note("mandolin", 15.5, 2.0, pitch("D4"), 0.66, "tremolo")
    return notes


PHRASES = {
    "banjo-scruggs": dict(parts={"banjo": _scruggs()},
                          about="three-finger (Scruggs) style with metal picks on a resonator: forward rolls on the "
                                "open D chord, a break with the tune inside the rolls, a slide, a hammer-on, a "
                                "pull-off, a pinch to end"),
    "banjo-clawhammer": dict(parts={"banjo": _clawhammer()},
                             about="old-time clawhammer on an open back: bum-ditty (the nail on the tune, a brush, "
                                   "the thumb on the drone), a hammer-on and a pull-off, a last brush"),
    "banjo-backup": dict(parts={"banjo": _backup()},
                         about="bluegrass backup: the thumb on the beat, chords choked on 2 and 4"),
    "mandolin-chop": dict(parts={"mandolin": _chop()},
                          about="bluegrass comping: strummed open chords, the backbeat chop"),
    "mandolin-tremolo": dict(parts={"mandolin": _tremolo()},
                             about="a slow air, long notes tremoloed, a double stop, a strum to end"),
    "mandolin-reel": dict(parts={"mandolin": _reel()},
                          about="a fiddle tune's eighths, alternate picking, a hammer-on, a slide, a tremolo to end"),
    "bluegrass": dict(parts={"banjo": forward_roll(Clock(116), ["D", "D", "G", "G", "A", "A", "D", "D"]),
                             "mandolin": chop_comping(Clock(116), ["D", "D", "G", "G", "A", "A", "D", "D"])},
                      about="the two together as a bluegrass band's rhythm: the banjo's forward rolls over the "
                            "mandolin's strums and backbeat chops"),
}


def _banjo_lead() -> list:
    """The tune stated Scruggs-style: its notes on the beats inside forward rolls, brought out."""
    c = Clock(112)
    notes = []
    tune = [("D4", "D"), ("F#4", "D"), ("G4", "G"), ("B4", "G"), ("A4", "A"), ("E4", "A"), ("F#4", "D"), ("D4", "D")]
    for bar in range(4):
        for half in range(2):
            melody, name = tune[2 * bar + half]
            shape = ROLL_SHAPES[name]
            beat = 4.0 * bar + 2.0 * half
            notes.append(c.note("banjo", beat, 1.0, pitch(melody), 0.82, "pick"))
            for k, n in enumerate(shape[1:4]):
                art = "thumb" if n == "A4" else "pick"
                notes.append(c.note("banjo", beat + 0.5 * (k + 1), 0.75, pitch(n), 0.72, art))
    return notes


def _mandolin_lead() -> list:
    """The air's tune: long notes tremoloed, the rest picked, as a mandolin states a melody."""
    c = Clock(96)
    notes, beat = [], 0.0
    for beats, name in TUNE * 2:
        art = "tremolo" if beats >= 2 else ""
        notes.append(c.note("mandolin", beat, beats - 0.05, pitch(name), 0.75, art))
        beat += beats
    return notes


LEVELS = {
    "banjo": ("comping", forward_roll(Clock(110), ["D", "D", "G", "A", "D", "D", "G", "A"])),
    "mandolin": ("comping", chop_comping(Clock(110), ["D", "D", "G", "A", "D", "D", "G", "A"])),
}

LEADS = {"banjo": _banjo_lead(), "mandolin": _mandolin_lead()}
