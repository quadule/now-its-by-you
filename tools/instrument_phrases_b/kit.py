"""The drum kit's phrases: grooves written as step patterns, one line per piece.

A pattern has one character a step (sixteenths unless said otherwise), bars run on: "x" a stroke at the
line's velocity, "X" an accent, "g" a ghost, "." nothing.
"""

from __future__ import annotations

from _common import Clock

MODULE = {"kit": "kit"}

LEVELS_VEL = {"x": 1.0, "X": 1.35, "g": 0.35}


def groove(clock: Clock, lines: dict, steps_per_beat: int = 4, vel: float = 0.6, offset: float = 0.0) -> list:
    """Notes for every line: {art: pattern} or {art: (pattern, vel)}."""
    notes = []
    for art, spec in lines.items():
        pattern, v = spec if isinstance(spec, tuple) else (spec, vel)
        pattern = pattern.replace(" ", "").replace("|", "")
        for k, ch in enumerate(pattern):
            if ch in LEVELS_VEL:
                beat = offset + k / steps_per_beat
                notes.append(clock.note("kit", beat, 1.0 / steps_per_beat, 38, min(1.0, v * LEVELS_VEL[ch]), art))
    return sorted(notes, key=lambda n: n.start)


def _rock() -> list:
    c = Clock(100)
    bars = groove(c, {
        "kick": "x.......x.x.....|x.......x.x.....|x.......x.x.....|x.......x.......",
        "snare": "....X.......X...|....X.......X...|....X.......X...|....X...........",
        "hat": ("X.x.X.x.X.x.X.x.|X.x.X.x.X.x.X.x.|X.x.X.x.X.x.X.x.|X.x.X.x.........", 0.5),
        "crash": ("x...............|................|................|................", 0.8),
    })
    fill = groove(c, {"snare": "........", "tom-hi": "xx......", "tom-mid": "..xx....", "tom-lo": "....xxxx"},
                  offset=14.0, vel=0.7)
    end = groove(c, {"crash": "x", "kick": "x"}, offset=16.0, vel=0.85)
    return bars + fill + end


def _brushes() -> list:
    """A ballad on brushes: the left hand sweeping a beat at a time, the right tapping 2 and 4, a feathered
    kick on 1 and 3 and the hi-hat's foot on 2 and 4."""
    c = Clock(76)
    notes = []
    for beat in range(16):
        notes.append(c.note("kit", beat, 0.95, 38, 0.55, "brush-sweep"))
    notes += groove(c, {
        "brush-tap": ("....x.......x...|....x.......x...|....x.......x...|....x.......x...", 0.55),
        "kick": ("x.......x.......|x.......x.......|x.......x.......|x.......x.......", 0.3),
        "hat-foot": ("....x.......x...|....x.......x...|....x.......x...|....x.......x...", 0.55),
        "ride:brush": ("x.....x.x.....x.|x.....x.x.....x.|x.....x.x.....x.|x.....x.x.......", 0.4),
    })
    return sorted(notes, key=lambda n: n.start)


def _train() -> list:
    """A country train beat: sixteenths on the snare, accents on 2 and 4, ghosts between, kick on 1 and 3."""
    c = Clock(112)
    return groove(c, {
        "snare": "gxgxXgxggxgxXgxg|gxgxXgxggxgxXgxg|gxgxXgxggxgxXgxg|gxgxXgxggxgxXgxg",
        "kick": ("x.......x.......|x.......x.......|x.......x.......|x.......x.......", 0.65),
        "hat-foot": ("....x.......x...|....x.......x...|....x.......x...|....x.......x...", 0.45),
    }, vel=0.45)


def _ride() -> list:
    """A swung ride (spang-a-lang) with the hi-hat's foot on 2 and 4 and the bell to end."""
    c = Clock(120, swing=1.0)
    notes = groove(c, {
        "ride": ("x.xxx.xxx.xxx.xx|x.xxx.xxx.xxx.xx|x.xxx.xxx.xxx.xx|x.xxx.xx........", 0.55),
        "hat-foot": ("..x...x...x...x.|..x...x...x...x.|..x...x...x...x.|..x...x.........", 0.6),
        "kick": ("x.......x.......|x.......x.......|x.......x.......|x...............", 0.3),
        "snare": ("......g.......g.|..g...........g.|......g...g.....|................", 0.5),
    }, steps_per_beat=2)
    notes += groove(c, {"ride-bell": "X.x.X.x.X"}, steps_per_beat=2, offset=12.0, vel=0.6)
    return sorted(notes, key=lambda n: n.start)


def _rods() -> list:
    """A folk groove on rods: cross-stick on 2 and 4, the hi-hat in eighths, an open hat into each bar's end."""
    c = Clock(96)
    return groove(c, {
        "kick:rod": ("x.....x.x.......|x.....x.x.......|x.....x.x.......|x.....x.x.......", 0.6),
        "snare-cross": ("....x.......x...|....x.......x...|....x.......x...|....x.......x...", 0.65),
        "hat:rod": ("x.x.x.x.x.x.....|x.x.x.x.x.x.....|x.x.x.x.x.x.....|x.x.x.x.x.x.....", 0.5),
        "hat-open:rod": ("............x...|............x...|............x...|............x...", 0.55),
        "hat-foot": ("..............x.|..............x.|..............x.|..............x.", 0.5),
    })


def _ghosts() -> list:
    """Ghost notes around a backbeat, as a funk or soul drummer plays them."""
    c = Clock(92)
    return groove(c, {
        "kick": "x.....x...x..x..|x.....x...x.....|x.....x...x..x..|x.....x...x.....",
        "snare": "....X..g.g..X..g|.g..X..g.g..X...|....X..g.g..X..g|.g..X..g.g..X.g.",
        "hat": ("x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.", 0.45),
    }, vel=0.6)


def _swell() -> list:
    """A mallet roll swelling on the crash, into a floor-tom and crash hit, and a rim shot and choke."""
    c = Clock(80)
    notes = [c.note("kit", 0, 4, 49, 0.75, "crash-roll"), c.note("kit", 2, 2, 43, 0.5, "tom-lo-roll:mallet")]
    notes += groove(c, {"crash": "x", "kick": "x", "tom-lo": "x"}, offset=4.0, vel=0.85, steps_per_beat=1)
    notes += [c.note("kit", 6, 1.5, 38, 0.9, "rim"), c.note("kit", 6, 1.5, 49, 0.9, "crash-choke")]
    return sorted(notes, key=lambda n: n.start)


PHRASES = {
    "kit-rock": dict(parts={"kit": _rock()}, about="a rock beat on sticks, crash on the one, a tom fill"),
    "kit-brushes": dict(parts={"kit": _brushes()}, about="a brush ballad: sweeps, taps on 2 and 4, feathered kick, "
                                                      "the hi-hat's foot, a brushed ride"),
    "kit-train": dict(parts={"kit": _train()}, about="a country train beat: snare sixteenths, accents and ghosts"),
    "kit-ride": dict(parts={"kit": _ride()}, about="a swung ride cymbal, the hi-hat's foot, ghosted snare, the bell"),
    "kit-rods": dict(parts={"kit": _rods()}, about="rods: cross-stick backbeat, hi-hat eighths with an open hat"),
    "kit-ghosts": dict(parts={"kit": _ghosts()}, about="ghost notes around a backbeat"),
    "kit-swell": dict(parts={"kit": _swell()}, about="a mallet swell on the crash, a floor-tom roll, a rim shot "
                                                     "and a choked crash"),
}


def _level() -> list:
    c = Clock(100)
    return groove(c, {
        "kick": "x.......x.......|x.......x.......|x.......x.......|x.......x.......",
        "snare": "....x.......x...|....x.......x...|....x.......x...|....x.......x...",
        "hat": "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.x.",
    }, vel=0.6)


LEVELS = {"kit": ("percussion", _level())}
