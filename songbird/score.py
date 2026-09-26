"""A realized score: timed notes ready for synthesis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .phrasing import Gesture


@dataclass(frozen=True)
class Note:
    part: str  # "voice", "choir1".., or an instrument: "lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone"
    start: float  # seconds
    dur: float  # seconds the note sounds before it is damped
    pitch: float  # MIDI note number
    vel: float  # 0..1
    syllable: str | None = None
    word: str | None = None  # the whole word this syllable belongs to, as written
    word_len: int = 1  # syllables in that word
    line_end: bool = False  # last syllable of a lyric line
    section: str = ""
    phrase: str = ""
    gesture: Gesture | None = None  # a person's way with this note, if the rendition has a phrasing
    art: str = ""  # how an instrument plays it: a strum's "down", "up" or "mute", a bow's "slur", a pipe's "cut", a drum's "tip"...
    # an ornament sung inside the note (songbird.variants): ((fraction of the sung note, semitones from it), ...),
    # each the pitch the voice turns to at that point; () for a plain note
    ornament: tuple = ()


def _note_dict(note: Note) -> dict:
    data = asdict(note)
    if not note.ornament:  # a plain note's record is as it always was
        del data["ornament"]
    return data


@dataclass(frozen=True)
class Score:
    notes: tuple[Note, ...]
    duration: float  # seconds, including the final ring
    sections: tuple[tuple[str, float, float], ...]  # (name, start, end) in seconds
    lexicon: dict = field(default_factory=dict)  # the song's own pronunciations
    band: dict = field(default_factory=dict)  # how the instruments are built and set up (see songbird.band)

    def part(self, name: str) -> tuple[Note, ...]:
        return tuple(n for n in self.notes if n.part == name)

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "sections": [list(s) for s in self.sections],
            "notes": [_note_dict(n) for n in self.notes],
            "lexicon": self.lexicon,
            "band": self.band,
        }
