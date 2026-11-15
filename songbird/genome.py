"""The song's skeleton: what persists across generations.

A genome is authored once for the seed and carried forward unchanged; only the
ear path may mutate its contour. It holds the seed's tune as scale degrees on a
rhythmic grid, which a person can read and edit. Everything the lineage gate
compares (coarse contour, stress pattern, phrase-final targets) is derived
from that tune rather than stored beside it, so the two can never disagree.

Tune notation, one token per grid unit:

    5      scale degree, 1 = tonic; ' raises an octave, , lowers one (5, 1 1')
    #4 b7  chromatic alteration
    -      hold the previous note one more unit
    .      rest
    |      bar line; tokens before the first bar line are a pickup
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .theory import parse_chord

_DEGREE = re.compile(r"([#b]?)([1-7])([',]*)")


@dataclass(frozen=True)
class Meter:
    signature: str
    unit: int  # note value of one grid unit: 4 = quarter, 8 = eighth
    bar: int  # grid units per bar
    beat: int  # grid units per beat; tempo counts beats
    foot: int  # grid units per metrical foot; each stressed syllable starts one


@dataclass(frozen=True)
class TuneNote:
    degree: int | None  # absolute scale degree, None for a rest
    alter: int
    onset: int  # grid units from the phrase's first bar line, negative in a pickup
    dur: int


@dataclass(frozen=True)
class Phrase:
    id: str
    tune: str
    notes: tuple[TuneNote, ...]
    bars: int
    chords: tuple[tuple[str, ...], ...]  # one tuple of functions per bar
    # a line as one place in the form sings it (songbird.composition.form_phrases): the key its own tune is kept
    # under there ("refrain:last.1"), None where it sings the line's everywhere tune; its id stays the line's
    place: str | None = None
    # a line with its own count (docs/notes/OWN-COUNT-LINES.md): the lyric key and line its words and notes are
    # kept under ("verse:wire.2"), its notes the person's; None for the tune line's own
    own: str | None = None

    @property
    def sung(self) -> tuple[TuneNote, ...]:
        return tuple(n for n in self.notes if n.degree is not None)

    @property
    def pickup(self) -> int:
        return max(0, -min(n.onset for n in self.notes))

    @property
    def target(self) -> int:
        """Phrase-final scale degree, folded into one octave (1-7)."""
        return (self.sung[-1].degree - 1) % 7 + 1

    def stress(self, meter: Meter) -> str:
        return " ".join("S" if n.onset % meter.foot == 0 else "w" for n in self.sung)

    def contour(self) -> str:
        """Relative moves between sung notes: h hold, u/d step, U/D leap."""
        moves = []
        for a, b in zip(self.sung, self.sung[1:]):
            step = b.degree - a.degree
            moves.append("h" if step == 0 else ("u" if step == 1 else "d" if step == -1 else "U" if step > 0 else "D"))
        return " ".join(moves)


@dataclass(frozen=True)
class Section:
    name: str
    phrases: tuple[str, ...]
    lyrics: str | None  # "verse", a fixed block ("refrain", "bridge", ...), or None for an instrumental section
    choir: bool = False  # voices from the lineage join in harmony here


@dataclass(frozen=True)
class Genome:
    title: str
    meter: Meter
    phrases: dict[str, Phrase]
    sections: dict[str, Section]
    form: tuple[str, ...]  # template; "?" marks optional sections, "*" repeatable ones
    refrain: tuple[str, ...]
    verse_template: dict
    hooks: tuple[dict, ...]
    seed_verses: tuple[tuple[str, ...], ...]
    seed_params: dict
    source: dict  # the JSON as authored, carried forward verbatim
    lexicon: dict  # the song's own words: spelling -> ARPAbet, for words no dictionary has
    fixed: dict = field(default_factory=dict)  # every fixed lyric block by name, the refrain among them
    # a line of an older song, on the song's grid in its own notation, never sung: the lead instrument may
    # play it alone before the song (style.intro "quote"); source["quote"]["about"] says what it is and why
    quote: Phrase | None = None

    def section(self, name: str) -> Section:
        """A section of a concrete form by name. A name the genome doesn't
        define that is a section's name with a number after it, bridge2, is
        that section sung again as a section of its own: the same phrases,
        the same lyric block and the same choir."""
        if name in self.sections:
            return self.sections[name]
        base = name.rstrip("0123456789")
        if base != name and base in self.sections:
            return replace(self.sections[base], name=name)
        raise KeyError(f"the genome has no section {name!r}")


# a turning word starts a word, {made|sang}; braces right after a word are its say, live{verb}
_TURN = re.compile(r"(?<![A-Za-z0-9'’-])\{([^{}]*)\}")


def turn(line: str, i: int, n: int) -> str:
    """A fixed line as sung the i-th of n times its block comes round. A line
    can turn one word each time, written {made|sang|heard|owns}: the choices
    go in order, and the last time round always takes the last one."""

    def pick(match: re.Match) -> str:
        options = match.group(1).split("|")
        if n > 1 and i == n - 1:
            return options[-1]
        return options[i % max(len(options) - 1, 1)]

    return _TURN.sub(pick, line)


def turns(line: str) -> list[str]:
    """Every way a fixed line can be sung."""
    match = _TURN.search(line)
    options = match.group(1).split("|") if match else [""]
    return [line[: match.start()] + o + line[match.end() :] for o in options] if match else [line]


_SAY = re.compile(r"\{[^{}]*\}")  # a word's say, bass{fish} (songbird.heteronyms): never sung or shown


def syllables(line: str) -> list[str]:
    """Sung syllables of a lyric line; hyphens split words into syllables."""
    return [piece for word in _SAY.sub("", line).split() for piece in word.split("-") if piece]


def sung_words(line: str) -> list[tuple[str, str, int]]:
    """(syllable, whole word, syllables in the word) for each sung syllable. A word's say stays with the whole
    word, for the singer (bass{fish}), and never with its syllables, which are shown."""
    out = []
    for word in line.split():
        pieces = [p for p in _SAY.sub("", word).split("-") if p]
        out += [(piece, word, len(pieces)) for piece in pieces]
    return out


def parse_tune(tune: str, meter: Meter) -> tuple[tuple[TuneNote, ...], int]:
    """Parse tune notation into notes and a bar count."""
    segments = tune.split("|")
    pickup, bars = segments[0].split(), [s.split() for s in segments[1:]]
    for i, bar in enumerate(bars):
        if len(bar) != meter.bar:
            raise ValueError(f"bar {i + 1} of {tune!r} has {len(bar)} units, meter needs {meter.bar}")
    notes: list[list] = []  # [degree, alter, onset, dur], mutable while holds extend them
    t = -len(pickup)
    for token in pickup + [tok for bar in bars for tok in bar]:
        if token == "-":
            if not notes:
                raise ValueError(f"{tune!r} starts with a hold")
            notes[-1][3] += 1
        elif token == ".":
            if notes and notes[-1][0] is None:
                notes[-1][3] += 1
            else:
                notes.append([None, 0, t, 1])
        else:
            match = _DEGREE.fullmatch(token)
            if not match:
                raise ValueError(f"bad token {token!r} in {tune!r}")
            accidental, digit, octaves = match.groups()
            degree = int(digit) + 7 * (octaves.count("'") - octaves.count(","))
            notes.append([degree, {"": 0, "#": 1, "b": -1}[accidental], t, 1])
        t += 1
    return tuple(TuneNote(*n) for n in notes), len(bars)


def _parse_chords(text: str, bars: int, phrase_id: str) -> tuple[tuple[str, ...], ...]:
    per_bar = tuple(tuple(bar.split()) for bar in text.split("|"))
    if len(per_bar) != bars:
        raise ValueError(f"phrase {phrase_id}: {len(per_bar)} bars of chords for {bars} bars of tune")
    for bar in per_bar:
        if not bar:
            raise ValueError(f"phrase {phrase_id}: empty chord bar")
        for symbol in bar:
            parse_chord(symbol)
    return per_bar


def _check_lines(lines, section: Section, phrases: dict[str, Phrase], what: str) -> None:
    if len(lines) != len(section.phrases):
        raise ValueError(f"{what}: {len(lines)} lines for {len(section.phrases)} phrases")
    for line, pid in zip(lines, section.phrases):
        for sung in turns(line):
            want, got = len(phrases[pid].sung), len(syllables(sung))
            if want != got:
                raise ValueError(f"{what}: {sung!r} has {got} syllables, phrase {pid} has {want} notes")


def from_dict(data: dict) -> Genome:
    meter = Meter(**data["meter"])
    phrases = {}
    for pid, spec in data["phrases"].items():
        notes, bars = parse_tune(spec["tune"], meter)
        phrases[pid] = Phrase(pid, spec["tune"], notes, bars, _parse_chords(spec["chords"], bars, pid))
    sections = {}
    for name, spec in data["sections"].items():
        missing = [p for p in spec["phrases"] if p not in phrases]
        if missing:
            raise ValueError(f"section {name} names unknown phrases {missing}")
        sections[name] = Section(name, tuple(spec["phrases"]), spec.get("lyrics"), bool(spec.get("choir", False)))
    for token in data["form"]:
        if token.rstrip("?*") not in sections:
            raise ValueError(f"form names unknown section {token!r}")
    quote = None
    if data.get("quote"):
        spec = data["quote"]
        notes, bars = parse_tune(spec["tune"], meter)
        if not notes or not bars or any(n.onset < 0 for n in notes):
            raise ValueError("the quote is whole bars on the grid, with no pickup")
        chords = spec.get("chords") or " | ".join(["I"] * bars)
        quote = Phrase("quote", spec["tune"], notes, bars, _parse_chords(chords, bars, "quote"))

    genome = Genome(
        title=data["title"],
        meter=meter,
        phrases=phrases,
        sections=sections,
        form=tuple(data["form"]),
        refrain=tuple(data["refrain"]),
        verse_template=data.get("verse_template", {}),
        hooks=tuple(data.get("hooks", [])),
        seed_verses=tuple(tuple(v) for v in data.get("seed_verses", [])),
        seed_params=data.get("seed_params", {}),
        source=data,
        lexicon=dict(data.get("lexicon", {})),
        fixed={
            s.lyrics: tuple(data[s.lyrics]) for s in sections.values() if s.lyrics not in (None, "verse") and s.lyrics in data
        } | {"refrain": tuple(data["refrain"])},
        quote=quote,
    )
    for section in sections.values():
        if section.lyrics == "verse":
            for i, verse in enumerate(genome.seed_verses):
                _check_lines(verse, section, phrases, f"seed verse {i + 1}")
        elif section.lyrics is not None:
            if section.lyrics not in genome.fixed:
                raise ValueError(f"section {section.name} sings {section.lyrics!r}, which the genome doesn't have")
            _check_lines(genome.fixed[section.lyrics], section, phrases, section.lyrics)
    return genome


def load(path: str | Path) -> Genome:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
