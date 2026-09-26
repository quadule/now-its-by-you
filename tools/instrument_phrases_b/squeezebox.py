"""The accordion's and the concertina's phrases."""

from __future__ import annotations

from _common import Clock, chord, pitch

MODULE = {"accordion": "accordion", "concertina": "accordion"}

# D, G, D, A: the oom-pah's chords, two bars each (root, fifth)
CHANGES = [("D", "A"), ("G", "D"), ("D", "A"), ("A", "E")]
TRIADS = {"D": ("F#3", "A3", "D4"), "G": ("G3", "B3", "D4"), "A": ("E3", "A3", "C#4")}


def _oompah(part: str, vel: float = 0.6, bars: int = 8, tempo: float = 112, low: int = 3, hands: bool = True) -> list:
    """Oom-pah in D: a bass note on one and three (root, then fifth), the chord on two and four, as the shanty's
    oompah idiom writes it; on the accordion, its left hand's bass and chord buttons ('bass' and 'chord')."""
    c = Clock(tempo)
    notes = []
    for bar in range(bars):
        root, fifth = CHANGES[(bar // 2) % 4]
        triad = TRIADS[root]
        for beat in range(4):
            if beat % 2 == 0:
                name = (root if beat == 0 else fifth) + str(low)
                p = pitch(name)
                while p < pitch("C3"):
                    p += 12
                notes.append(c.note(part, 4 * bar + beat, 0.7, p, vel * (1.1 if beat == 0 else 1.0),
                                    "bass" if hands else ""))
            else:
                notes += [c.note(part, 4 * bar + beat, 0.55, q, vel * 0.9, "chord" if hands else "")
                          for q in chord(*triad)]
    return notes


def _line(part: str, names, clock: Clock, vel: float = 0.65) -> list:
    notes, beat = [], 0.0
    for name, beats, art in names:
        if name:
            notes.append(clock.note(part, beat, beats, pitch(name), vel, art))
        beat += beats
    return notes


def _waltz() -> list:
    """A musette waltz in D: the right hand's tune over the left hand's bass on one and chords on two and three."""
    c = Clock(168)
    tune = [("F#5", 1, ""), ("E5", 1, "slur"), ("D5", 1, "slur"), ("A4", 1, ""), ("D5", 1, ""), ("F#5", 1, ""),
            ("A5", 2, "swell"), ("G5", 1, ""), ("F#5", 3, ""), ("E5", 1, ""), ("F#5", 1, "slur"), ("G5", 1, "slur"),
            ("E5", 1, ""), ("C#5", 1, ""), ("A4", 1, ""), ("E5", 3, "swell"), ("D5", 1, ""), ("C#5", 1, "slur"),
            ("B4", 1, "slur"), ("A4", 1, ""), ("D5", 1, ""), ("F#5", 1, ""), ("A5", 2, ""), ("G5", 1, ""),
            ("F#5", 1, ""), ("E5", 1, ""), ("C#5", 1, ""), ("D5", 3, "shake")]
    notes = _line("accordion", tune, c, 0.62)
    harmony = ["D", "D", "D", "D", "A", "A", "A", "A", "D", "D", "D", "A", "D"]
    bass = {"D": ("D3", "A2"), "A": ("A2", "E3")}
    triads = {"D": ("F#3", "A3", "D4"), "A": ("E3", "G3", "C#4")}
    for bar, h in enumerate(harmony):
        root = bass[h][bar % 2]
        notes.append(c.note("accordion", 3 * bar, 0.8, pitch(root), 0.62, "bass"))
        for beat in (1, 2):
            notes += [c.note("accordion", 3 * bar + beat, 0.5, q, 0.5, "chord") for q in chord(*triads[h])]
    return notes


def _air(part: str) -> list:
    """A slow air in D: breathed phrases (the bellows turn in the rests), a swell on the long notes, a shake to end."""
    c = Clock(76)
    return _line(part, [("A4", 1, ""), ("D5", 1, ""), ("E5", 1, "slur"), ("F#5", 2, "swell"), ("E5", 1, ""),
                        ("D5", 1, "slur"), ("B4", 1, ""), ("A4", 3, "swell"), ("", 1, ""), ("F#4", 1, ""),
                        ("A4", 1, ""), ("B4", 1, "slur"), ("D5", 2, ""), ("E5", 1, ""), ("F#5", 1, "slur"),
                        ("E5", 1, ""), ("D5", 4, "shake")], c, 0.6)


def _hornpipe() -> list:
    """A hornpipe's first strain on the concertina: quick notes, the bellows turned where the tune breathes."""
    c = Clock(92, swing=0.5)
    names = ["A4", "F#4", "A4", "D5", "F#5", "E5", "D5", "C#5", "B4", "G5", "F#5", "E5", "D5", "B4", "A4", "F#4",
             "G4", "B4", "D5", "G5", "F#5", "D5", "A4", "F#4", "E4", "G4", "B4", "E5", "C#5", "A4", "E4", "C#4",
             "D4", "F#4", "A4", "D5", "F#5", "A5", "F#5", "D5", "E5", "C#5", "A4", "E4", "D4", "", "D5", ""]
    return _line("concertina", [(n, 0.5, "") for n in names], c, 0.62)


def _pad(part: str) -> list:
    """The shanty's bridge: held chords, swelling at each phrase, the bellows turning through them."""
    c = Clock(100)
    shapes = [chord("F#3", "A3", "D4"), chord("G3", "B3", "D4"), chord("F#3", "A3", "D4"), chord("E3", "A3", "C#4")]
    notes = []
    for k, shape in enumerate(shapes * 2):
        notes += [c.note(part, 4 * k, 4, p, 0.55, "swell" if k % 2 == 0 else "") for p in shape]
    return notes


PHRASES = {
    "accordion-oompah": dict(parts={"accordion": _oompah("accordion", 0.62)},
                             about="the left hand's oom-pah in D: Stradella bass buttons on one and three (the bass "
                                   "and tenor reeds, the break between B and C), chord buttons on two and four"),
    "accordion-musette-waltz": dict(parts={"accordion": _waltz()}, settings={"maker": 1, "ornament": 0.85},
                                    about="a musette waltz in D on a French-tuned musette box (three middle reeds, "
                                          "17 cents apart at A4): the tune over the left hand's bass and chords, a "
                                          "bellows shake to end"),
    "accordion-air": dict(parts={"accordion": _air("accordion")},
                          about="a slow air on the treble in the violin register (two middle reeds, this maker's "
                                "Cajun tremolo), swells on the long notes, the bellows turned in the rests, a shake"),
    "concertina-oompah": dict(parts={"concertina": _oompah("concertina", 0.62, hands=False)},
                              about="the shanty's oom-pah in D on an English concertina: bass notes on one and "
                                    "three, three-note chords on two and four, the small bellows turning every "
                                    "second or two"),
    "concertina-air": dict(parts={"concertina": _air("concertina")},
                           about="the slow air on the concertina: one bright reed a note, the ends answering each "
                                 "other, a shake to end"),
    "concertina-hornpipe": dict(parts={"concertina": _hornpipe()},
                                about="a hornpipe strain: quick notes, how fast a concertina reed speaks"),
    "concertina-pad": dict(parts={"concertina": _pad("concertina")},
                           about="the shanty's bridge: held chords swelling in, the bellows turning through them"),
}

LEVELS = {"accordion": ("comping", _oompah("accordion")), "concertina": ("comping", _oompah("concertina", hands=False))}
