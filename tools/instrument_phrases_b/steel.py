"""The pedal steel's and the slide guitar's phrases, in D.

The steel's swells hold three-note grips (it finds its own bar, pedals and levers: D at the tenth fret, then
the A and B pedals down for G at the same fret, the classic move); its intro is the tune in single notes with
slides, glides, a pedal bend, vibrato and a fall. The slide is a country-blues lick in open D, played on each
of its three bodies.
"""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"steel": "steel", "slide": "steel"}

GRIPS = {"D": chord("A4", "D5", "F#5"), "G": chord("B4", "D5", "G5"), "A": chord("A4", "C#5", "E5"),
         "Bm": chord("B4", "D5", "F#5"), "D/A": chord("F#4", "A4", "D5")}


def _swells(vel: float = 0.6) -> list:
    """Swelled grips under a voice at 72: each bar's chord swelled in, and half way through the bar the next
    chord reached by the pedals alone (a slur) where the bar can stay: D to G on the A and B pedals and back."""
    c = Clock(72)
    notes = []
    for bar, (first, then) in enumerate((("D", "G"), ("D", "D"), ("G", "G"), ("A", "A"), ("D", "G"), ("D", "D"),
                                         ("A", "A"), ("D", "D"))):
        for p in GRIPS[first]:
            notes.append(c.note("steel", 4 * bar, 2.0 if then != first else 4.0, p, vel, "swell"))
        if then != first:
            for p in GRIPS[then]:
                notes.append(c.note("steel", 4 * bar + 2, 2.0, p, vel, "slur"))
    return notes


def _under(vel: float = 0.6) -> list:
    """The country style's part for it: an alto line under the singer, its long notes swelled, the moves slurred,
    a slide into a note now and then (as songbird.idioms.w_under writes it), four bars twice."""
    c = Clock(96)
    line = [("F#4", 4, "swell"), ("G4", 2, "slur"), ("A4", 2, ""), ("B4", 4, "swell"), ("A4", 4, "slide"),
            ("F#4", 4, "swell"), ("E4", 2, "slur"), ("D4", 2, ""), ("E4", 4, "swell"), ("F#4", 4, "swell")]
    notes, beat = [], 0.0
    for name, beats, art in line:
        notes.append(c.note("steel", beat, beats, pitch(name), vel, art))
        beat += beats
    return notes


def _intro() -> list:
    """A country intro: the tune on the steel, slid into, glided between, a pedal bend and a fall to end."""
    c = Clock(88)
    line = [("A4", 1, "slide"), ("B4", 1, "glide"), ("D5", 2, ""), ("E5", 1, "bend"), ("D5", 1, "glide"),
            ("B4", 2, "vibrato"), ("A4", 1, ""), ("F#4", 1, "glide"), ("A4", 2, "slide"), ("G4", 1, ""),
            ("F#4", 1, "glide"), ("E4", 2, "bend"), ("D4", 4, "vibrato")]
    notes, beat = [], 0.0
    for name, beats, art in line:
        notes.append(c.note("steel", beat, beats, pitch(name), 0.65, art))
        beat += beats
    for p in GRIPS["D/A"]:  # the last chord, swelled, fading as the bar falls away
        notes.append(c.note("steel", beat, 4.0, p, 0.6, "swell"))
    for p in GRIPS["D/A"]:
        notes.append(c.note("steel", beat + 4.0, 2.0, p, 0.55, "fall"))
    return notes


def _blues(part: str = "slide", vel: float = 0.65) -> list:
    """A country-blues lick in open D at a shuffle of 86: slid into the high notes, a glide down, the wide
    vibrato on the held ones, the open bass strings under it, a fall to finish."""
    c = Clock(86, swing=1.0)
    line = [("D2", 0.0, 1.0, ""), ("A4", 0.5, 1.5, "slide"), ("F#4", 2.0, 0.5, "glide"), ("D4", 2.5, 1.5, "vibrato"),
            ("D2", 4.0, 1.0, ""), ("C5", 4.5, 1.0, "slide"), ("A4", 5.5, 0.5, "glide"), ("F4", 6.0, 0.5, ""),
            ("D4", 6.5, 1.5, "vibrato"), ("A2", 8.0, 1.0, ""), ("E4", 8.5, 1.0, "slide"), ("G4", 9.5, 0.5, "glide"),
            ("A4", 10.0, 2.0, "vibrato"), ("D2", 12.0, 1.0, ""), ("D5", 12.5, 1.0, "slide"), ("C5", 13.5, 0.5, "glide"),
            ("A4", 14.0, 1.0, ""), ("F#4", 15.0, 1.0, "glide"), ("D4", 16.0, 2.5, "fall")]
    return [c.note(part, beat, beats, pitch(name), vel if name[-1] != "2" else vel * 0.8, art)
            for name, beat, beats, art in line]


def _fills(vel: float = 0.6) -> list:
    """The blues style's part for it: answers at the ends of the singer's lines (a run of three or four notes
    into the next line, above the tune) and a held tone swelling through a line, twice."""
    c = Clock(86, swing=1.0)
    notes = []
    for rep in range(2):
        b0 = 16.0 * rep
        for k, name in enumerate(("F#4", "A4", "B4", "D5")):
            notes.append(c.note("slide", b0 + 3.0 + 0.5 * k, 0.5 if k < 3 else 1.0, pitch(name), vel,
                                "slide" if k == 0 else ""))
        for k, name in enumerate(("A4", "G4", "F#4")):
            notes.append(c.note("slide", b0 + 7.0 + 0.5 * k, 0.5 if k < 2 else 1.0, pitch(name), vel,
                                "" if k else "slide"))
        notes.append(c.note("slide", b0 + 8.0, 7.0, pitch("A4"), vel, "swell"))
    return notes


PHRASES = {
    "steel-swells": dict(
        parts={"steel": _swells()}, settings={"tempo": 72},
        about="pedal steel: three-note grips swelled in with the volume pedal, D to G by pressing the A and B pedals "
              "at the same fret (the classic move), a bar vibrato on the held chords"),
    "steel-under": dict(
        parts={"steel": _under()}, settings={"tempo": 96},
        about="pedal steel: the country style's line under the singer, as the idioms write it: swells, slurs "
              "played by the bar and the pedals, a slide into a note"),
    "steel-intro": dict(
        parts={"steel": _intro()}, settings={"tempo": 88},
        about="pedal steel: a country intro, the tune in single notes slid into and glided between, two pedal "
              "bends, vibrato, a swelled last chord and the bar falling away"),
    "slide-acoustic": dict(
        parts={"slide": _blues()}, settings={"tempo": 86, "slide": "acoustic"},
        about="slide guitar, an acoustic flat-top in open D with a bottleneck: a country-blues lick, slid into, "
              "glided, the wide vibrato, open bass strings, a fall"),
    "slide-resonator": dict(
        parts={"slide": _blues()}, settings={"tempo": 86, "slide": "resonator"},
        about="the same lick on a resonator guitar (its spun cone's metallic, ringing midrange)"),
    "slide-electric": dict(
        parts={"slide": _blues()}, settings={"tempo": 86, "slide": "electric"},
        about="the same lick on an electric through a small valve amp pushed a little"),
    "slide-fills": dict(
        parts={"slide": _fills()}, settings={"tempo": 86},
        about="slide guitar: the blues style's answers at the ends of lines, and a held tone"),
}

LEVELS = {"steel": ("comping", _under()), "slide": ("lead", _fills())}
