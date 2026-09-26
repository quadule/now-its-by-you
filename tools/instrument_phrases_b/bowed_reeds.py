"""The cello's, viola's, string section's and harmonica's phrases."""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"cello": "cello", "viola": "cello", "strings": "cello", "harmonica": "harmonica"}


def _line(part: str, names, clock: Clock, vel: float = 0.65) -> list:
    notes, beat = [], 0.0
    for name, beats, art in names:
        if name:
            notes.append(clock.note(part, beat, beats, pitch(name), vel, art))
        beat += beats
    return notes


def _cello() -> list:
    """A cello line in D, down in its warm low strings: a slide into the long notes, slurred steps."""
    return _line("cello", [("D3", 2, ""), ("F#3", 1, "slur"), ("A3", 1, "slur"), ("B3", 2, "slide"), ("A3", 2, ""),
                           ("G3", 1, ""), ("F#3", 1, "slur"), ("E3", 2, "swell"), ("A2", 2, ""), ("D3", 4, "slide")],
                 Clock(72))


def _cello_bass(vel: float = 0.6, bars: int = 8) -> list:
    c = Clock(96)
    roots = ["D2", "B1", "G2", "A2"]
    notes = []
    for bar in range(bars):
        notes.append(c.note("cello", 4 * bar, 3.8, pitch(roots[(bar // 2) % 4]) + 12, vel, ""))
    return notes


def _viola() -> list:
    return _line("viola", [("A4", 1, ""), ("B4", 1, "slur"), ("D5", 2, ""), ("C#5", 1, ""), ("B4", 1, "slur"),
                           ("A4", 2, "swell"), ("F#4", 2, "slide"), ("E4", 2, ""), ("D4", 4, "")], Clock(80))


def _pad(vel: float = 0.6, bars: int = 8) -> list:
    """The section holding chords: D, Bm, G, A, each two bars, cellos to violins."""
    c = Clock(80)
    shapes = [chord("D3", "A3", "F#4", "D5"), chord("B2", "F#3", "D4", "B4"), chord("G2", "D3", "B3", "G4"),
              chord("A2", "E3", "C#4", "A4")]
    notes = []
    for bar in range(0, bars, 2):
        notes += [c.note("strings", 4 * bar, 8, p, vel, "swell" if bar == 0 else "") for p in shapes[(bar // 2) % 4]]
    return notes


def _pizz() -> list:
    c = Clock(100)
    pattern = ["D3", "A3", "F#4", "A3", "B2", "F#3", "D4", "F#3", "G2", "D3", "B3", "D3", "A2", "E3", "C#4", "A3"]
    return [c.note("strings", k, 0.5, pitch(p), 0.7, "pizz") for k, p in enumerate(pattern)]


def _harp_blues() -> list:
    """A blues lick in D on the harmonica: bent into the third and the fifth, a wah on the long note, a
    tongue-slap chord to end."""
    c = Clock(88)
    line = [("A4", 0.5, ""), ("C5", 0.5, "bend"), ("D5", 1, ""), ("F5", 0.5, "bend"), ("D5", 0.5, ""),
            ("A4", 2, "wah"), ("G4", 0.5, ""), ("F4", 0.5, "bend"), ("D4", 2, "trem"), ("", 1, "")]
    notes = _line("harmonica", line, c)
    notes += [c.note("harmonica", 9, 1, p, 0.7, "slap") for p in chord("D4", "F#4", "A4")]
    return notes


def _harp_vamp(vel: float = 0.65, bars: int = 8) -> list:
    """The harmonica's chord vamp, tongue-blocked: chords on the beat, a slap on each bar's first."""
    c = Clock(100)
    notes = []
    for bar in range(bars):
        for beat in range(4):
            art = "slap" if beat == 0 else "chord"
            notes += [c.note("harmonica", 4 * bar + beat, 0.45, p, vel, art) for p in chord("D4", "F#4", "A4")]
    return notes


def _melody() -> list:
    return _line("harmonica", [("F#4", 1, ""), ("A4", 1, ""), ("B4", 1, ""), ("A4", 1, ""), ("F#4", 2, ""),
                               ("E4", 1, ""), ("D4", 1, ""), ("E4", 2, ""), ("F#4", 1, ""), ("E4", 1, ""),
                               ("D4", 4, "")], Clock(96))


PHRASES = {
    "cello-line": dict(parts={"cello": _cello()}, about="a cello line down in its low strings, slides and slurs",
                       mix_as={"cello": "harp"}),
    "viola-line": dict(parts={"viola": _viola()}, about="a viola line, a swell and a slide", mix_as={"viola": "harp"}),
    "strings-pad": dict(parts={"strings": _pad()}, about="the section holding D, Bm, G and A, swelling in",
                        mix_as={"strings": "harp"}),
    "strings-pizz": dict(parts={"strings": _pizz()}, about="the section plucking an arpeggio", mix_as={"strings": "harp"}),
    "harmonica-blues": dict(parts={"harmonica": _harp_blues()}, about="a blues lick in D: bends, a wah, a slap"),
    "harmonica-vamp": dict(parts={"harmonica": _harp_vamp()}, about="tongue-blocked chords, a slap on each bar"),
}

LEVELS = {"cello": ("comping", _cello_bass()), "strings": ("comping", _pad()), "harmonica": ("lead", _melody())}
