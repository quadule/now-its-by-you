"""Scales, modes and chords. Pure functions over small integers."""

from __future__ import annotations

from functools import lru_cache
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
# A quality a person names, over the chord's root; case never carries one (a genome's "v" and "V" are one function).
# The triads, then the chords a lead sheet writes with a fourth tone (docs/STUDIO.md, "Looser harmony and melody"):
# each a fixed chord over its root whatever the mode, root, third (or the sus chord's second or fourth), fifth,
# then the added tone: the seventh, the sixth, or the ninth (14, a ninth above the root)
QUALITIES = {"maj": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8), "sus2": (0, 2, 7), "sus4": (0, 5, 7),
             "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "m7b5": (0, 3, 6, 10),
             "dim7": (0, 3, 6, 9), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9), "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14),
             "7sus4": (0, 5, 7, 10), "7sus2": (0, 2, 7, 10)}
SEVENTHS = frozenset(q for q, tones in QUALITIES.items() if len(tones) == 4 and tones[3] in (9, 10, 11)
                     and q not in ("6", "m6"))  # the chords with a seventh, which may stand in the bass (/7)
_CHORD = re.compile(r"([#b]?)(?i:(i{1,3}|iv|vi{0,2}|v))("
                    + "|".join(sorted(QUALITIES, key=len, reverse=True)) + r")?(?:/([357]))?")


@lru_cache(maxsize=1024)
def degree_semitones(degree: int, mode: str, alter: int = 0) -> int:
    """Semitones above the tonic for an absolute scale degree.

    Degree 1 is the tonic, 8 the octave above, 0 the seventh below.
    """
    steps = MODES[mode]
    octave, index = divmod(degree - 1, len(steps))
    return 12 * octave + steps[index] + alter


@lru_cache(maxsize=512)
def parse_symbol(symbol: str) -> tuple[int, int, str, int]:
    """A chord function in full: (degree 1-7, alteration in semitones, quality, bass).

    The genome writes roman numerals (vi, bVII) whose case is ignored: a chord's
    quality comes from the mode it is realized in, so the genome stores
    functions, not chords. A person may name a quality after the numeral (maj,
    m, dim, aug, sus2, sus4, or a chord with a fourth tone: 7, maj7, m7, m7b5,
    dim7, 6, m6, add9, madd9, 7sus4, 7sus2; lower case, "" for the mode's own)
    and a bass other than the root (/3 its third, /5 its fifth, /7 the seventh
    of a chord that has one; 1 for the root): Vmaj, ivm/5, V7/7.
    """
    match = _CHORD.fullmatch(symbol.strip())
    if not match:
        raise ValueError(f"not a chord function: {symbol!r}")
    accidental, numeral, quality, bass = match.groups()
    if bass == "7" and quality not in SEVENTHS:
        raise ValueError(f"only a chord with a seventh has a seventh to put in the bass: {symbol!r}")
    return _ROMAN[numeral.lower()], {"": 0, "#": 1, "b": -1}[accidental], quality or "", int(bass or 1)


def parse_chord(symbol: str) -> tuple[int, int]:
    """A roman numeral to (degree 1-7, alteration in semitones), whatever quality or bass it names."""
    degree, alter, _, _ = parse_symbol(symbol)
    return degree, alter


@lru_cache(maxsize=1024)
def chord_tones(symbol: str, mode: str) -> tuple[int, ...]:
    """Semitone offsets from the tonic of the chord's root, third and fifth, and
    its added tone if it has one (a seventh, a sixth, a ninth).

    A plain numeral is the diatonic triad on that degree of the mode. A numeral
    with an accidental (bVII, bVI) is borrowed and always major. A quality named
    (Vmaj, iim, IVsus4, V7, iim7, IVmaj7) is that chord over the root, whatever
    the mode; the sus chords' second or fourth stands where the third would.
    Three tones for a triad, as ever; four for a chord with an added tone.
    """
    degree, alter, quality, _ = parse_symbol(symbol)
    if quality:
        root = degree_semitones(degree, mode) + alter
        return tuple(root + t for t in QUALITIES[quality])
    if alter:
        root = degree_semitones(degree, mode) + alter
        return root, root + 4, root + 7
    return (
        degree_semitones(degree, mode),
        degree_semitones(degree + 2, mode),
        degree_semitones(degree + 4, mode),
    )


# the degree whose letter a major key writes each semitone above the tonic on: I, bII, II, bIII, III, IV, #IV...
_MAJOR_DEGREES = (1, 2, 2, 3, 3, 4, 4, 5, 6, 6, 7, 7)
_NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII")


@lru_cache(maxsize=16)
def chromatic_roots(mode: str) -> tuple[str, ...]:
    """A numeral for each of the twelve roots a chord can have, a semitone apart from the tonic up. A numeral's
    sharp or flat moves the mode's own degree (chord_tones), so each root is the mode's own degree where it is one,
    and otherwise keeps the letter a major key gives it, with whatever sign puts that letter on it in this mode:
    in a minor key the third, sixth and seventh are III, VI and VII, and the semitones above them #III, #VI and
    #VII (in A minor C, F, G and C♯, F♯, G♯)."""
    out = []
    for pc, degree in enumerate(_MAJOR_DEGREES):
        if pc in MODES[mode]:  # the mode's own degree is plain, wherever a major key puts it (Locrian's V on E♭)
            degree = MODES[mode].index(pc) + 1
        alter = pc - degree_semitones(degree, mode)
        out.append({-1: "b", 0: "", 1: "#"}[alter] + _NUMERALS[degree - 1])
    return tuple(out)


NOTE_NAMES = ("C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")  # a tonic's name, out of any key

# Spelling in a key (its signature): each degree of the scale on its own letter, so C♯ minor has G♯ and D♯, not
# A♭ and E♭, and a chord's root is spelt by its numeral's degree (VII in C♯ minor is B, bVII in C major B♭).
LETTERS = "CDEFGAB"
_NATURAL = (0, 2, 4, 5, 7, 9, 11)
_SIGN = {-2: "𝄫", -1: "♭", 0: "", 1: "♯", 2: "𝄪"}


def _alter(pc: int, letter: int) -> int:
    """The accidental (semitones, -6..5) that puts this letter on this pitch class."""
    return (pc - _NATURAL[letter % 7] + 6) % 12 - 6


def _spelt(letter: int, alter: int) -> str:
    return LETTERS[letter % 7] + _SIGN[alter]


@lru_cache(maxsize=256)
def tonic_letter(tonic: int, mode: str) -> tuple[int, int]:
    """The tonic's letter and accidental: the name a musician writes the key by, the one of its two names with the
    fewer sharps or flats (D♭ major's five flats, not C♯ major's seven sharps; G♯ minor's five sharps, not A♭
    minor's seven flats), its usual name (NOTE_NAMES) when they tie (F♯ major, E♭ minor)
    or it has only one."""
    pc = tonic % 12
    name = NOTE_NAMES[pc]
    letter = LETTERS.index(name[0])
    alter = _alter(pc, letter)
    if alter:
        other = (letter + (1 if alter > 0 else -1)) % 7
        if abs(signature_of(pc, other, mode)) < abs(signature_of(pc, letter, mode)):
            letter, alter = other, _alter(pc, other)
    return letter, alter


def signature_of(pc: int, letter: int, mode: str) -> int:
    """Sharps (positive) or flats (negative) in the key signature of a tonic spelt on this letter."""
    return sum(_alter(pc + MODES[mode][d], letter + d) for d in range(7))


def key_signature(tonic: int, mode: str) -> int:
    """The key's signature: its sharps (positive) or flats (negative), -7..7."""
    letter, _ = tonic_letter(tonic, mode)
    return signature_of(tonic % 12, letter, mode)


def scale_names(tonic: int, mode: str) -> tuple[str, ...]:
    """The key's seven notes, from its tonic, each on its own letter: C♯ minor is C♯ D♯ E F♯ G♯ A B."""
    letter, _ = tonic_letter(tonic, mode)
    pc = tonic % 12
    return tuple(_spelt(letter + d, _alter(pc + MODES[mode][d], letter + d)) for d in range(7))


@lru_cache(maxsize=256)
def spelling(tonic: int, mode: str) -> tuple[str, ...]:
    """The twelve pitch classes (C first) as this key writes them: its own seven on their letters; a note outside
    it natural if a natural is that note, else sharp in a sharp key and flat in a flat one (NOTE_NAMES' own in a
    key with neither)."""
    letter, _ = tonic_letter(tonic, mode)
    pc0, sig = tonic % 12, key_signature(tonic, mode)
    out = list(NOTE_NAMES)
    for pc in range(12):
        if pc in _NATURAL and not any((pc0 + MODES[mode][d]) % 12 == pc for d in range(7)):
            out[pc] = LETTERS[_NATURAL.index(pc)]
        elif sig > 0:
            out[pc] = _spelt(_NATURAL.index((pc - 1) % 12), 1) if (pc - 1) % 12 in _NATURAL else out[pc]
        elif sig < 0:
            out[pc] = _spelt(_NATURAL.index((pc + 1) % 12), -1) if (pc + 1) % 12 in _NATURAL else out[pc]
    for d in range(7):  # the key's own last, on their letters (E♯ in C♯ major, C♭ in A♭ minor)
        out[(pc0 + MODES[mode][d]) % 12] = _spelt(letter + d, _alter(pc0 + MODES[mode][d], letter + d))
    return tuple(out)


def note_name(pitch: int, tonic: int, mode: str, octave: bool = True) -> str:
    """A MIDI pitch as this key writes it, with its octave (C4 is 60): G♯4 in C♯ minor. B♯ and C♭ keep the
    octave of their letter (B♯3 sounds as C4)."""
    name = spelling(tonic, mode)[pitch % 12]
    if not octave:
        return name
    n = pitch // 12 - 1
    n += -1 if name[0] == "B" and pitch % 12 == 0 else 1 if name[0] == "C" and pitch % 12 == 11 else 0
    return f"{name}{n}"


def _root_letter(symbol: str, tonic: int, mode: str) -> tuple[int, int]:
    """A chord's root spelt by its numeral: the degree's letter, with the accidental that puts it on the root."""
    degree, alter, _, _ = parse_symbol(symbol)
    letter, _ = tonic_letter(tonic, mode)
    root = (tonic + degree_semitones(degree, mode) + alter) % 12
    return letter + degree - 1, _alter(root, letter + degree - 1)


def root_name(symbol: str, tonic: int, mode: str) -> str:
    """A chord's root named by its numeral in this key: bVII in C♯ minor is B♭, #IV in F major B."""
    letter, _ = _root_letter(symbol, tonic, mode)
    return _chord_note(tonic + chord_tones(symbol, mode)[0], letter, tonic, mode)


# how many letters above the root each of a chord's tones is written (its third a third, a sus4's fourth a fourth)
_TONE_LETTER = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 4, 9: 5, 10: 6, 11: 6, 14: 1}


def _chord_note(pc: int, letter: int, tonic: int, mode: str) -> str:
    """A chord's note: one of the key's own on the key's letter; another on the letter its numeral or its place in
    the chord gives it (bVII in C♯ minor B♭, V7/7 in C A7/G), unless that takes a double sharp or flat."""
    alter = _alter(pc, letter)
    if abs(alter) > 1 or any((tonic + MODES[mode][d] - pc) % 12 == 0 for d in range(7)):
        return spelling(tonic, mode)[pc % 12]
    return _spelt(letter, alter)


@lru_cache(maxsize=1024)
def chord_bass(symbol: str, mode: str) -> int:
    """Semitone offset from the tonic of the chord's lowest note: its root, or the third or fifth a person
    put in the bass (I/3, V/5)."""
    tones = chord_tones(symbol, mode)
    return tones[{1: 0, 3: 1, 5: 2, 7: 3}[parse_symbol(symbol)[3]]]


# A chord's kind by its tones above the root (pitch classes), as a lead sheet writes it after the root's name
KINDS = {(4, 7): "", (3, 7): "m", (3, 6): "°", (4, 8): "+", (5, 7): "sus4", (2, 7): "sus2",
         (4, 7, 10): "7", (4, 7, 11): "maj7", (3, 7, 10): "m7", (3, 6, 10): "m7♭5", (3, 6, 9): "°7",
         (4, 7, 9): "6", (3, 7, 9): "m6", (4, 7, 2): "add9", (3, 7, 2): "m(add9)", (5, 7, 10): "7sus4",
         (2, 7, 10): "7sus2"}


@lru_cache(maxsize=2048)
def chord_name(symbol: str, tonic: int, mode: str) -> str:
    """A chord function as a musician reads it in this key: vi in D major is Bm, bVII is C, V in D is A, V7 A7,
    viim7b5 C♯m7♭5, V7/7 A7/G."""
    tones = chord_tones(symbol, mode)
    root = tones[0]
    kind = KINDS.get(tuple((t - root) % 12 for t in tones[1:]), "")
    letter, alter = _root_letter(symbol, tonic, mode)
    name = _chord_note(tonic + root, letter, tonic, mode) + kind
    bass = chord_bass(symbol, mode)
    if bass == root:
        return name
    step = (bass - root) % 12
    up = 6 if step == 9 and parse_symbol(symbol)[2] == "dim7" else _TONE_LETTER[step]  # a °7's seventh, diminished
    return f"{name}/{_chord_note(tonic + bass, letter + up, tonic, mode)}"


FLOOR = 52  # E3: below about 160 Hz the learned throat's pulses are heard one by one (a "tapping" through the
# bridge: 35 thumps a second at E2, 10 at D3, 2 at E3, none from A3 up); real basses sing to E2 (40),
# and the bass instrument has that register


def harmony(melody: int, chord: str, tonic: int, mode: str, role: int, previous: int | None = None) -> int:
    """A choir voice's pitch (MIDI) against one melody note. Role 0 takes a
    chord tone a third or more below the melody, role 1 one a third or more
    above, role 2 the chord's root beneath both; further roles repeat those an
    octave lower. Chord tones keep every voice consonant with the accompaniment
    whatever the melody passes through. Alone, a voice takes the chord tone
    nearest the melody; given where it just was (previous), it moves as little
    as it can, holding a note the new chord shares (common-tone voice leading),
    so the voices beneath a moving tune sing lines, not leaps."""
    tones = chord_tones(chord, mode)
    pcs = {(tonic + t) % 12 for t in tones}
    kind, octave = role % 3, role // 3
    if kind == 0:
        fits = [p for p in range(melody - 3, melody - 15, -1) if p % 12 in pcs]
    elif kind == 1:
        fits = [p for p in range(melody + 3, melody + 15) if p % 12 in pcs]
    else:  # the root: within two octaves, so it can hold its note while the tune moves
        fits = [p for p in range(melody - 5, melody - 29, -1) if p % 12 == (tonic + tones[0]) % 12]
    fits = [p - 12 * octave for p in fits]  # nearest the melody first, so a tie goes that way
    # but never below a voice the throat can sing (FLOOR): where the tune is so low that nothing fits above the
    # floor, the lowest chord tone at or above it under the tune (the root voice taking a fifth or a third
    # rather than a note it can't sing), else the lowest up to the tune's own note
    above = [p for p in fits if p >= FLOOR]
    if not above:
        avoid = harmony(melody, chord, tonic, mode, 0) if kind == 2 else None  # not the note the low voice takes
        room = [p for p in range(FLOOR, melody + 1) if p % 12 in pcs]
        above = ([p for p in room if p < melody and p != avoid][:1] or [p for p in room if p != avoid][:1]
                 or room[:1] or fits[:1])
    fits = above
    return fits[0] if previous is None else min(fits, key=lambda p: abs(p - previous))


def choir_voicing(melody: list[dict], voices: int, tonic: int, mode: str) -> list[tuple[int, ...]]:
    """The lineage choir's pitches for every note of a tune (dicts with its pitch, chord, syllable and
    whether the choir sings there, in time order): one per voice where the choir sings words, none
    elsewhere. Each voice is led from where it was (harmony's previous), and starts afresh each time the
    choir comes in again. realize() sings these and the band keeps clear of them (songbird.band), from
    this one place, so the two always agree."""
    out: list[tuple[int, ...]] = []
    voiced: dict[int, int] = {}
    for m in melody:
        if not m["syllable"] or voices <= 0:
            out.append(())
            continue
        if not m.get("choir"):
            voiced.clear()
            out.append(())
            continue
        for v in range(voices):
            voiced[v] = harmony(int(m["pitch"]), m["chord"], tonic, mode, v, voiced.get(v))
        out.append(tuple(voiced[v] for v in range(voices)))
    return out


def midi_to_hz(pitch: float) -> float:
    return 440.0 * 2.0 ** ((pitch - 69.0) / 12.0)


def hz_to_midi(freq: float) -> float:
    return 69.0 + 12.0 * math.log2(freq / 440.0)
