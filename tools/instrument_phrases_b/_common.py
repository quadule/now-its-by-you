"""Helpers for writing the instrument phrases: time in beats at a tempo, pitches by name."""

from __future__ import annotations

from songbird.score import Note

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch(name: str) -> int:
    """MIDI number of a note name: "D4" is 62, "F#3" 54, "Bb2" 46."""
    letter, rest = name[0].upper(), name[1:]
    shift = 0
    while rest and rest[0] in "#b":
        shift += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + STEPS[letter] + shift


def chord(*names: str) -> list[int]:
    return [pitch(n) for n in names]


class Clock:
    """Beats to seconds at a tempo, with an optional swing of the off-beat eighths (0 straight, 1 triplet)."""

    def __init__(self, tempo: float, swing: float = 0.0):
        self.tempo, self.swing = tempo, swing

    def s(self, beat: float) -> float:
        whole, frac = divmod(beat, 1.0)
        if self.swing and abs(frac - 0.5) < 1e-9:
            frac = 0.5 + self.swing / 6.0
        return (whole + frac) * 60.0 / self.tempo

    def note(self, part: str, beat: float, beats: float, pitch: float, vel: float = 0.6, art: str = "") -> Note:
        start = self.s(beat)
        return Note(part=part, start=start, dur=max(0.02, self.s(beat + beats) - start), pitch=float(pitch),
                    vel=vel, art=art)
