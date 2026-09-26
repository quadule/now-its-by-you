"""The electric instruments' phrases: an electric guitar through its amp (clean, crunch, tremolo), an electric
bass, a pedal steel and a slide guitar, each in D.

Chord shapes are written as pitches low to high; the instrument finds its own strings and frets.
"""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"electric": "electric", "electric-crunch": "electric", "electric-tremolo": "electric", "ebass": "electric"}

# open shapes a guitarist would grab in D
SHAPES = {
    "D": chord("D3", "A3", "D4", "F#4"),
    "G": chord("G2", "B2", "D3", "G3", "B3", "G4"),
    "A": chord("A2", "E3", "A3", "C#4", "E4"),
    "Bm": chord("B2", "F#3", "B3", "D4", "F#4"),
    "Em": chord("E2", "B2", "E3", "G3", "B3", "E4"),
}
POWER = {"D": chord("D3", "A3", "D4"), "G": chord("G2", "D3", "G3"), "A": chord("A2", "E3", "A3"),
         "C": chord("C3", "G3", "C4"), "B": chord("B2", "F#3", "B3")}


def strum_bar(c: Clock, part: str, bar: int, shape: list, vel: float = 0.6, beats: int = 4) -> list:
    """The folk-rock strum: down on 1, down-up on 2, up on 3&, down-up on 4 (the 'old faithful'); ups catch
    only the top strings."""
    notes = []
    b0 = bar * beats
    for beat, art in ((0.0, "down"), (1.0, "down"), (1.5, "up"), (2.5, "up"), (3.0, "down"), (3.5, "up")):
        until = {0.0: 1.0, 1.0: 0.5, 1.5: 1.0, 2.5: 0.5, 3.0: 0.5, 3.5: 0.5}[beat]
        strings = shape if art == "down" else shape[-3:]
        for p in strings:
            notes.append(c.note(part, b0 + beat, until, p, vel if art == "down" else vel * 0.9, art))
    return notes


def _electric_comping() -> list:
    c = Clock(100)
    notes = []
    for bar, name in enumerate(["D", "D", "G", "A", "D", "Bm", "G", "A"]):
        notes += strum_bar(c, "electric", bar, SHAPES[name])
    return notes


def _crunch_comping() -> list:
    """Power chords in eighths: each beat let ring, the off-beats palm-muted."""
    c = Clock(112)
    notes = []
    for bar, name in enumerate(["D", "D", "C", "G", "D", "D", "C", "A"]):
        for k in range(8):
            beat = bar * 4 + k * 0.5
            ring = k % 2 == 0
            for p in POWER[name]:
                notes.append(c.note("electric-crunch", beat, 0.5 if ring else 0.45, p, 0.6, "down" if ring else "mute"))
    return notes


def _tremolo_comping() -> list:
    c = Clock(80)
    notes = []
    for bar, name in enumerate(["D", "G", "D", "A", "Bm", "G", "A", "D"]):
        for half in (0, 2):
            for p in SHAPES[name]:
                notes.append(c.note("electric-tremolo", bar * 4 + half, 2.0, p, 0.6, "down"))
    return notes


def _bass_root_fifth() -> list:
    c = Clock(100)
    roots = {"D": pitch("D2"), "G": pitch("G1"), "A": pitch("A1"), "Bm": pitch("B1")}
    notes = []
    for bar, name in enumerate(["D", "D", "G", "A", "D", "Bm", "G", "A"]):
        r = roots[name]
        for beat, p in ((0, r), (1, r + 7), (2, r), (3, r + 7)):
            notes.append(c.note("ebass", bar * 4 + beat, 0.9, p, 0.6))
    return notes


def _clean_arpeggios() -> list:
    """A clean picked arpeggio over D, Bm, G, A with a slide, a hammer-on and a held vibrato to end."""
    c = Clock(92)
    notes = []
    patterns = {"D": ("D3", "A3", "D4", "F#4", "A4", "F#4", "D4", "A3"),
                "Bm": ("B2", "F#3", "B3", "D4", "F#4", "D4", "B3", "F#3"),
                "G": ("G2", "D3", "G3", "B3", "D4", "B3", "G3", "D3"),
                "A": ("A2", "E3", "A3", "C#4", "E4", "C#4", "A3", "E3")}
    for bar, name in enumerate(["D", "Bm", "G", "A", "D", "Bm", "G", "A"]):
        for k, p in enumerate(patterns[name]):
            art = "slide" if (bar == 2 and k == 4) else "hammer" if (bar == 5 and k == 3) else ""
            notes.append(c.note("electric", bar * 4 + k * 0.5, 1.5, pitch(p), 0.55 + 0.1 * (k % 4 == 0), art))
    notes.append(c.note("electric", 32, 3.0, pitch("D4"), 0.55))
    notes.append(c.note("electric", 32, 3.0, pitch("A4"), 0.55))
    notes.append(c.note("electric", 32, 3.5, pitch("F#5"), 0.65, "vibrato"))
    return notes


def _crunch_riff() -> list:
    """A crunch riff: palm-muted chugs on the low D, power-chord stabs, a bend and a pull-off to finish."""
    c = Clock(112)
    notes = []
    for rep in range(2):
        b0 = rep * 8
        for k in range(8):
            notes.append(c.note("electric-crunch", b0 + k * 0.5, 0.45, pitch("D3"), 0.65, "mute"))
        for beat, name in ((4.0, "G"), (5.0, "A"), (6.5, "D")):
            for p in POWER[name]:
                notes.append(c.note("electric-crunch", b0 + beat, 0.9 if beat < 6 else 1.4, p, 0.75, "down"))
    notes.append(c.note("electric-crunch", 16, 1.0, pitch("B4"), 0.75, "bend"))
    notes.append(c.note("electric-crunch", 17, 0.5, pitch("A4"), 0.7))
    notes.append(c.note("electric-crunch", 17.5, 0.5, pitch("F#4"), 0.7, "pull"))
    notes.append(c.note("electric-crunch", 18, 2.0, pitch("D4"), 0.75, "vibrato"))
    for p in POWER["D"]:
        notes.append(c.note("electric-crunch", 20, 3.0, p, 0.8, "down"))
    return notes


def _tremolo_chords() -> list:
    c = Clock(76)
    notes = []
    for bar, name in enumerate(["D", "G", "Bm", "A", "D"]):
        for p in SHAPES[name]:
            notes.append(c.note("electric-tremolo", bar * 4, 4.0 if bar < 4 else 6.0, p, 0.6, "down"))
    return notes


def _bass_walk() -> list:
    """Root-fifth in D with a walk up into G, a slide, a ghost note and a muted, picked turnaround."""
    c = Clock(100)
    notes = []
    line = [("D2", 0, 1, ""), ("A1", 1, 1, ""), ("D2", 2, 1, ""), ("A1", 3, 0.5, ""), ("A1", 3.5, 0.5, "ghost"),
            ("D2", 4, 1, ""), ("E2", 5, 1, ""), ("F#2", 6, 1, ""), ("F#2", 7, 1, ""),
            ("G2", 8, 1, "slide"), ("D2", 9, 1, ""), ("G1", 10, 1, ""), ("B1", 11, 1, ""),
            ("A1", 12, 1, ""), ("E2", 13, 1, ""), ("A1", 14, 1, ""), ("C#2", 15, 1, ""),
            ("D2", 16, 0.5, "pick"), ("D2", 16.5, 0.5, "mute"), ("D2", 17, 0.5, "mute"), ("A1", 17.5, 0.5, "mute"),
            ("D2", 18, 2.0, "")]
    for p, beat, beats, art in line:
        notes.append(c.note("ebass", beat, beats * 0.92, pitch(p), 0.6 if art != "ghost" else 0.4, art))
    return notes


PHRASES = {
    "electric-clean-arpeggios": dict(
        parts={"electric": _clean_arpeggios()}, settings={"tempo": 92}, mix_as={"electric": "guitar"},
        about="a clean electric: picked arpeggios with the spring reverb, a slide into a note, a hammer-on, "
              "a held chord with finger vibrato"),
    "electric-crunch-riff": dict(
        parts={"electric-crunch": _crunch_riff()}, settings={"tempo": 112}, mix_as={"electric-crunch": "guitar"},
        about="crunch: palm-muted chugs, power-chord stabs, a bend, a pull-off, a vibrato"),
    "electric-tremolo-chords": dict(
        parts={"electric-tremolo": _tremolo_chords()}, settings={"tempo": 76}, mix_as={"electric-tremolo": "guitar"},
        about="held chords through the amp's tremolo, locked to the tempo"),
    "electric-strum": dict(
        parts={"electric": _electric_comping()}, settings={"tempo": 100}, mix_as={"electric": "guitar"},
        about="the old faithful strum on a clean electric (the calibration part)"),
    "ebass-root-fifth": dict(
        parts={"ebass": _bass_walk()}, settings={"tempo": 100},
        about="an electric bass: root-fifth, a walk up, a slide, a ghost note, a picked and muted turnaround"),
}

LEVELS = {
    "electric": ("comping", _electric_comping()),
    "electric-crunch": ("comping", _crunch_comping()),
    "electric-tremolo": ("comping", _tremolo_comping()),
    "ebass": ("bass", _bass_root_fifth()),
}
