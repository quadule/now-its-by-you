"""A realized score: timed notes ready for synthesis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .phrasing import Gesture


@dataclass(frozen=True)
class Note:
    part: str  # "melody", "harp", "bass", later "voice"
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


@dataclass(frozen=True)
class Score:
    notes: tuple[Note, ...]
    duration: float  # seconds, including the final ring
    sections: tuple[tuple[str, float, float], ...]  # (name, start, end) in seconds
    lexicon: dict = field(default_factory=dict)  # the song's own pronunciations

    def part(self, name: str) -> tuple[Note, ...]:
        return tuple(n for n in self.notes if n.part == name)

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "sections": [list(s) for s in self.sections],
            "notes": [asdict(n) for n in self.notes],
            "lexicon": self.lexicon,
        }
