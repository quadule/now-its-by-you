"""The classical guitar's and the ukulele's phrases: a bossa, an arpeggio, a rasgueado, an island strum."""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"nylon": "nylon", "ukulele": "nylon"}


def _bossa(vel: float = 0.6, bars: int = 8) -> list:
    """A bossa nova in D: the thumb on the bass (root and fifth), the fingers pinching the chord against it."""
    c = Clock(132)
    changes = [("D2", "A2", chord("F#3", "A3", "C#4", "E4")), ("E2", "B2", chord("D3", "G3", "B3", "E4")),
               ("A2", "E2", chord("G3", "B3", "C#4", "E4")), ("D2", "A2", chord("F#3", "A3", "C#4", "E4"))]
    notes = []
    for bar in range(bars):
        root, fifth, voicing = changes[(bar // 2) % 4]
        b0 = 4 * bar
        notes.append(c.note("nylon", b0, 1.9, pitch(root), vel, "thumb"))
        notes.append(c.note("nylon", b0 + 2, 1.9, pitch(fifth), vel * 0.9, "thumb"))
        hits = (0.0, 1.5, 3.0) if bar % 2 == 0 else (0.5, 2.0, 3.5)
        for h in hits:
            for p in voicing:
                notes.append(c.note("nylon", b0 + h, 0.45, p, vel * 0.8, ""))
    return notes


def _arpeggio() -> list:
    """A classical arpeggio, thumb on the bass and a melody on top (rest strokes), in D."""
    c = Clock(72)
    notes = []
    tune = ["F#4", "F#4", "F#4", "F#4", "E4", "D4", "D4", "C#4", "B3", "B3", "D4", "F#4", "A4", "A4", "A4", "A4"]
    basses = ["D2", "D2", "B2", "B2", "G2", "G2", "A2", "A2"]
    inner = [("A3", "D4"), ("A3", "D4"), ("F#3", "B3"), ("F#3", "B3"), ("G3", "B3"), ("G3", "B3"), ("G3", "C#4"),
             ("G3", "C#4")]
    for half in range(8):
        b0 = 2 * half
        notes.append(c.note("nylon", b0, 2.0, pitch(basses[half]), 0.6, "thumb"))
        for k in range(6):  # triplets: melody, inner, inner
            beat = b0 + k / 3.0
            if k % 3 == 0:
                notes.append(c.note("nylon", beat, 1.0 / 3.0, pitch(tune[2 * half + k // 3]), 0.7, "rest"))
            else:
                notes.append(c.note("nylon", beat, 1.0 / 3.0, pitch(inner[half][k % 3 - 1]), 0.45, ""))
    notes.append(c.note("nylon", 16, 3.0, pitch("D2"), 0.6, "thumb"))
    notes += [c.note("nylon", 16, 3.0, pitch(p), 0.55, "") for p in ("A3", "D4", "F#4")]
    notes.append(c.note("nylon", 17, 2.0, pitch("D5"), 0.5, "harmonic"))
    return notes


def _rasgueado() -> list:
    """The Andalusian cadence in D (Gm F Eb D) strummed, rasgueados on the accents, a golpe on the offbeats."""
    c = Clock(100)
    shapes = [chord("G2", "D3", "G3", "A#3", "D4", "G4"), chord("F2", "C3", "F3", "A3", "C4", "F4"),
              chord("D#2", "A#2", "D#3", "G3", "A#3", "D#4"), chord("D3", "A3", "D4", "F#4")]
    notes = []
    for bar, shape in enumerate(shapes * 2):
        b0 = 4 * bar
        for beat, art, v in ((0, "rasgueado", 0.85), (1, "down", 0.6), (1.5, "up", 0.5), (2, "rasgueado", 0.75),
                             (3, "down", 0.6), (3.5, "up", 0.5)):
            notes += [c.note("nylon", b0 + beat, 0.45 if art != "rasgueado" else 0.9, p, v, art) for p in shape]
        notes.append(c.note("nylon", b0 + 1, 0.1, 60, 0.6, "golpe"))
        notes.append(c.note("nylon", b0 + 3, 0.1, 60, 0.6, "golpe"))
    notes += [c.note("nylon", 32, 3.0, p, 0.9, "rasgueado") for p in shapes[3]]
    return notes


def _island(vel: float = 0.6, bars: int = 8) -> list:
    """The island strum on the ukulele: down, down-up, up-down-up, D G A D."""
    c = Clock(104)
    shapes = [chord("A4", "D4", "F#4", "A4"), chord("G4", "D4", "G4", "B4"), chord("A4", "C#4", "E4", "A4"),
              chord("A4", "D4", "F#4", "A4")]
    notes = []
    for bar in range(bars):
        shape = shapes[(bar // 2) % 4]
        for beat, art, v in ((0, "down", 1.0), (1, "down", 0.8), (1.5, "up", 0.7), (2.5, "up", 0.7),
                             (3, "down", 0.85), (3.5, "up", 0.7)):
            notes += [c.note("ukulele", 4 * bar + beat, 0.45, p, vel * v, art) for p in shape]
    return notes


def _uke_pick() -> list:
    """A picked ukulele line over the re-entrant G: the melody in D with a campanella shimmer."""
    c = Clock(96)
    line = ["D4", "F#4", "A4", "G4", "F#4", "E4", "D4", "E4", "F#4", "A4", "B4", "A4", "G4", "F#4", "E4", "D4"]
    return [c.note("ukulele", k * 0.5, 0.9, pitch(p), 0.6 if k % 2 == 0 else 0.5, "") for k, p in enumerate(line)] + \
        [c.note("ukulele", 8, 2.0, p, 0.6, "down") for p in chord("A4", "D4", "F#4", "A4")]


PHRASES = {
    "nylon-bossa": dict(parts={"nylon": _bossa()}, about="a bossa nova in D: the thumb's bass against pinched chords",
                        mix_as={"nylon": "guitar"}),
    "nylon-arpeggio": dict(parts={"nylon": _arpeggio()}, about="a classical arpeggio in triplets, the tune in rest "
                                                               "strokes, a harmonic to end", mix_as={"nylon": "guitar"}),
    "nylon-rasgueado": dict(parts={"nylon": _rasgueado()}, about="the Andalusian cadence in D, rasgueados and golpes",
                            mix_as={"nylon": "guitar"}),
    "ukulele-strum": dict(parts={"ukulele": _island()}, about="the island strum on D, G and A",
                          mix_as={"ukulele": "guitar"}),
    "ukulele-pick": dict(parts={"ukulele": _uke_pick()}, about="a picked line over the re-entrant G string",
                         mix_as={"ukulele": "guitar"}),
}

def _strummed(vel: float = 0.6, bars: int = 8) -> list:
    """Full chords strummed with the fingers, down on the beats and up between (as the band's guitar strums):
    the classical guitar's level is set by this, like the band's guitar and the other new instruments'."""
    c = Clock(96)
    shapes = [chord("D3", "A3", "D4", "F#4"), chord("B2", "F#3", "B3", "D4", "F#4"), chord("G2", "B2", "D3", "G3", "B3"),
              chord("A2", "E3", "A3", "C#4", "E4")]
    notes = []
    for bar in range(bars):
        shape = shapes[(bar // 2) % 4]
        for beat, art, v in ((0, "down", 1.0), (1, "down", 0.8), (1.5, "up", 0.7), (2, "down", 0.9), (3, "down", 0.8),
                             (3.5, "up", 0.7)):
            notes += [c.note("nylon", 4 * bar + beat, 0.45, p, vel * v, art) for p in shape]
    return notes


LEVELS = {"nylon": ("comping", _strummed()), "ukulele": ("comping", _island())}
