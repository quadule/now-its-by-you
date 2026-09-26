"""The banjo's and the mandolin's phrases: a forward roll, a clawhammer bum-ditty, the chop and the tremolo."""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"banjo": "banjo", "mandolin": "mandolin"}


def _roll(vel: float = 0.6, bars: int = 8) -> list:
    """Scruggs's forward roll in eighths (thumb, index, middle), D, G, A, D, the fifth string's drone (A4) in it."""
    c = Clock(120)
    shapes = [("D3", "F#3", "D4"), ("G3", "B3", "D4"), ("E3", "A3", "C#4"), ("D3", "F#3", "D4")]
    notes = []
    for bar in range(bars):
        low, mid, high = (pitch(p) for p in shapes[(bar // 2) % 4])
        # T I M T I M T M: the thumb's notes the low and the drone
        for k, (p, art) in enumerate(((low, "thumb"), (mid, ""), (high, ""), (pitch("A4"), "thumb"),
                                      (mid, ""), (high, ""), (low, "thumb"), (high, ""))):
            notes.append(c.note("banjo", 4 * bar + 0.5 * k, 1.0, p, vel * (1.0 if k % 3 == 0 else 0.85), art))
    return notes


def _clawhammer() -> list:
    """Old-time clawhammer in D: bum (the nail on the tune), di (a brush across the strings), tty (the thumb
    on the drone), the tune on each beat's strike."""
    c = Clock(112)
    tune = ["F#4", "E4", "D4", "E4", "F#4", "A4", "F#4", "E4", "D4", "D4", "E4", "F#4", "E4", "D4", "B3", "D4"]
    brush = chord("D4", "F#4", "A4")
    notes = []
    for k, p in enumerate(tune):
        beat = float(k)
        notes.append(c.note("banjo", beat, 0.5, pitch(p), 0.7, "claw"))
        notes += [c.note("banjo", beat + 0.5, 0.25, q, 0.5, "brush") for q in brush]
        notes.append(c.note("banjo", beat + 0.75, 0.25, pitch("A4"), 0.5, "thumb"))
    return notes


def _chop(vel: float = 0.6, bars: int = 8) -> list:
    """The bluegrass mandolin's backbeat: a chop on 2 and 4 (the chord struck and at once let go)."""
    c = Clock(120)
    shapes = [chord("A3", "F#4", "D5", "A5"), chord("G3", "D4", "B4", "G5"), chord("A3", "E4", "C#5", "A5"),
              chord("A3", "F#4", "D5", "A5")]
    notes = []
    for bar in range(bars):
        for beat in (1, 3):
            notes += [c.note("mandolin", 4 * bar + beat, 0.2, p, vel, "chop") for p in shapes[(bar // 2) % 4]]
    return notes


def _tremolo() -> list:
    """A slow air on the mandolin, its long notes tremolo-picked, the quick ones picked down and up."""
    c = Clock(76)
    line = [("F#5", 2, "tremolo"), ("E5", 1, "down"), ("D5", 1, "up"), ("E5", 2, "tremolo"), ("A4", 2, "tremolo"),
            ("B4", 1, "down"), ("D5", 1, "up"), ("F#5", 1, "down"), ("A5", 1, "up"), ("G5", 2, "tremolo"),
            ("F#5", 1, "down"), ("E5", 1, "up"), ("D5", 4, "tremolo")]
    notes, beat = [], 0.0
    for p, beats, art in line:
        notes.append(c.note("mandolin", beat, beats, pitch(p), 0.65, art))
        beat += beats
    return notes


PHRASES = {
    "banjo-roll": dict(parts={"banjo": _roll()}, about="Scruggs's forward roll over D, G and A, the drone string in it",
                       mix_as={"banjo": "guitar"}),
    "banjo-clawhammer": dict(parts={"banjo": _clawhammer()}, about="old-time clawhammer: the tune struck, a brush, "
                                                                   "the thumb on the drone", mix_as={"banjo": "guitar"}),
    "mandolin-chop": dict(parts={"mandolin": _chop()}, about="the bluegrass chop on 2 and 4",
                          mix_as={"mandolin": "guitar"}),
    "mandolin-tremolo": dict(parts={"mandolin": _tremolo()}, about="a slow air, its long notes tremolo-picked",
                             mix_as={"mandolin": "guitar"}),
    "bluegrass": dict(parts={"banjo": _roll(), "mandolin": _chop()}, about="the banjo's roll over the mandolin's chop",
                      mix_as={"banjo": "guitar", "mandolin": "harp"}),
}

LEVELS = {"banjo": ("comping", _roll()), "mandolin": ("comping", _chop())}
