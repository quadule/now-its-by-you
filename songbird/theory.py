"""Scales, modes and chords. Pure functions over small integers."""

from __future__ import annotations

import math
import re

# Semitone offsets of the seven degrees of each mode, from its tonic.
MODES: dict[str, tuple[int, ...]] = {
    "ionian": (0, 2, 4, 5, 7, 9, 11),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
}

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7}
_CHORD = re.compile(r"([#b]?)(i{1,3}|iv|vi{0,2}|v)", re.IGNORECASE)


def degree_semitones(degree: int, mode: str, alter: int = 0) -> int:
    """Semitones above the tonic for an absolute scale degree.

    Degree 1 is the tonic, 8 the octave above, 0 the seventh below.
    """
    steps = MODES[mode]
    octave, index = divmod(degree - 1, len(steps))
    return 12 * octave + steps[index] + alter


def parse_chord(symbol: str) -> tuple[int, int]:
    """A roman numeral to (degree 1-7, alteration in semitones).

    Case is ignored: a chord's quality comes from the mode it is realized in,
    so the genome stores functions, not chords.
    """
    match = _CHORD.fullmatch(symbol.strip())
    if not match:
        raise ValueError(f"not a chord function: {symbol!r}")
    accidental, numeral = match.groups()
    alter = {"": 0, "#": 1, "b": -1}[accidental]
    return _ROMAN[numeral.lower()], alter


def chord_tones(symbol: str, mode: str) -> tuple[int, int, int]:
    """Semitone offsets from the tonic of the chord's root, third and fifth.

    A plain numeral is the diatonic triad on that degree of the mode. A numeral
    with an accidental (bVII, bVI) is borrowed and always major.
    """
    degree, alter = parse_chord(symbol)
    if alter:
        root = degree_semitones(degree, mode) + alter
        return root, root + 4, root + 7
    return (
        degree_semitones(degree, mode),
        degree_semitones(degree + 2, mode),
        degree_semitones(degree + 4, mode),
    )


def harmony(melody: int, chord: str, tonic: int, mode: str, role: int) -> int:
    """A choir voice's pitch (MIDI) against one melody note. Role 0 takes the
    nearest chord tone a third or more below the melody, role 1 the nearest a
    third or more above, role 2 the chord's root beneath both; further roles
    repeat those an octave lower. Chord tones keep every voice consonant with
    the accompaniment whatever the melody passes through."""
    tones = chord_tones(chord, mode)
    pcs = {(tonic + t) % 12 for t in tones}
    kind, octave = role % 3, role // 3
    if kind == 0:
        pitch = next(p for p in range(melody - 3, melody - 15, -1) if p % 12 in pcs)
    elif kind == 1:
        pitch = next(p for p in range(melody + 3, melody + 15) if p % 12 in pcs)
    else:
        pitch = next(p for p in range(melody - 5, melody - 17, -1) if p % 12 == (tonic + tones[0]) % 12)
    return pitch - 12 * octave


def midi_to_hz(pitch: float) -> float:
    return 440.0 * 2.0 ** ((pitch - 69.0) / 12.0)


def hz_to_midi(freq: float) -> float:
    return 69.0 + 12.0 * math.log2(freq / 440.0)
