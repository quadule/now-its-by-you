"""Arrangement: a rendition's words, drawn from its song's lyric bank.

A song's bank, under "bank" in its genome (songs/<song>-bank.md for reading),
holds every verse, refrain couplet, bridge stanza and tag syllable the song
can sing, with named slots for the words that swap and the rules for putting
them together. arrange() fills every sung section of a concrete form from it,
within those rules, and records what it chose in a Lyrics; realize() sings a
Lyrics in place of the seed's own words.

Chance comes from a seed. Leanings, which other parts of the program set (the
drift of time, a person's harvest), tilt the draw toward some moods, eras,
rare verses or the words a person uses, but never past a rule: they change
how likely a choice is, never whether it is allowed. The same genome, form,
seed and leanings always give the same words, with no network and no model.

    python -m songbird.arrange songs/h-now-its-by-you.json --seed 7
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

import numpy as np

from .bank import MOODS, expansions, fill, slot_names, unmarked, width
from .genome import Genome, load, syllables, turn, turns
from .phonetics import FUNCTION_WORDS, clean

RARE = 1 / 3  # a rare verse comes a third as often as a common one
SPAN = 3.0  # a full leaning, +1 or -1, makes a choice up to this many times likelier or less likely
VOCAB = 1.5  # added to a choice's weight for a word of the person's that no other choice has, twice at most
ANSWER = 0.5  # once one verse of a pair is drawn, how often its partner answers it next (less if leaned away from)
MOOD_WEIGHTS = (0.05, 20.0)  # a mood's weight is held in this range: leanings steer, they never forbid
ATTEMPTS = 2000  # sets of verses drawn before searching the bank for one instead
_STREAM = 0x5EED  # the words draw from their own stream of a seed, apart from the rest of a rendition
_VERSES, _REFRAIN, _BRIDGE, _TAG = range(4)  # and each part of the song from its own, so one can't shift another

_BRACES = re.compile(r"\{[^{}]*\}")

# Every rule the bank can state that arrange keeps; a rule it doesn't know is an error, not a silence.
_RULES = {
    "verses": {"count", "first", "max_variants", "max_rare", "order", "never_adjacent", "max_mood", "pairs", "note"},
    "refrain": {"question", "once_per_song", "couplet_last", "couplet_repeat", "note"},
    "bridge": {"always", "extra", "once_per_song", "note"},
    "tag": {"once_per_song", "note"},
}
_RULE_VALUES = {
    ("verses", "order"): "era",
    ("verses", "pairs"): "adjacent",
    ("refrain", "question"): "turn",
    ("refrain", "couplet_repeat"): False,
    ("tag", "once_per_song"): "syllable",
}


class ArrangeError(ValueError):
    """A form the bank can't fill within its rules."""


@dataclass(frozen=True)
class Leanings:
    """How a rendition would like its words, where the bank's rules leave a
    choice. Each is neutral by default, and none can break a rule.

    mood_weights: plain, light, dark, tender -> how much likelier a verse of
        that mood is than the bank has it (1; held between 0.05 and 20)
    era_bias: -1 leans to older verses, +1 to newer ones (a verse with no year
        stays as likely as it was; held between -1 and 1)
    rarity_appetite: -1 shuns rare verses, +1 seeks them out (at 0 a rare
        verse comes a third as often as a common one, at +1 as often; held
        between -1 and 1)
    vocabulary: common words a person uses; the verses, couplets, stanzas and
        slot words that use them are preferred, the more so the fewer of the
        other choices share them. Only the words that mean count, not the
        little ones between them.

    Values past their range are held at its ends, and kept that way, so a
    Leanings says what bore on the draw. None for a field means neutral.
    """

    mood_weights: Mapping[str, float] = field(default_factory=dict)
    era_bias: float = 0.0
    rarity_appetite: float = 0.0
    vocabulary: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        moods = dict(self.mood_weights or {})
        unknown = sorted(set(moods) - set(MOODS))
        if unknown:
            raise ValueError(f"leanings name moods {unknown}; a verse's mood is one of {MOODS}")
        for mood, weight in moods.items():
            if not (isinstance(weight, (int, float)) and math.isfinite(weight) and weight >= 0):
                raise ValueError(f"the weight for {mood} verses must be a number at least 0, not {weight!r}")
        for name in ("era_bias", "rarity_appetite"):
            value = getattr(self, name)
            if value is None:
                value = 0.0
            if not (isinstance(value, (int, float)) and math.isfinite(value)):
                raise ValueError(f"{name} must be a number (held between -1 and 1), not {value!r}")
            object.__setattr__(self, name, max(-1.0, min(1.0, float(value))))
        if isinstance(self.vocabulary, str):
            raise TypeError("vocabulary is a collection of words, not one string")
        lo, hi = MOOD_WEIGHTS
        object.__setattr__(self, "mood_weights", {m: max(lo, min(hi, float(moods[m]))) for m in MOODS if m in moods})
        object.__setattr__(self, "vocabulary", frozenset(w for w in map(clean, self.vocabulary or ()) if w))

    def to_dict(self) -> dict:
        return {
            "mood_weights": dict(self.mood_weights),
            "era_bias": self.era_bias,
            "rarity_appetite": self.rarity_appetite,
            "vocabulary": sorted(self.vocabulary),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Leanings:
        return cls(
            mood_weights=data.get("mood_weights", {}),
            era_bias=data.get("era_bias", 0.0),
            rarity_appetite=data.get("rarity_appetite", 0.0),
            vocabulary=data.get("vocabulary", ()),
        )


@dataclass(frozen=True)
class Sung:
    """One sung section of a form: what it draws on and the lines it sings."""

    section: str  # the form's name for it: verse, refrain, bridge, bridge2, tag
    block: str  # the lyric block it sings: verse, refrain, bridge, tag
    id: str  # the verse, the refrain's couplet, the bridge stanza, or the tag's syllable
    slots: dict  # the words chosen for its slots, by slot name; a coupled slot's by column
    lines: tuple[str, ...]  # as sung: syllable hyphens, focus marks and all

    def to_dict(self) -> dict:
        return {"section": self.section, "block": self.block, "id": self.id, "slots": self.slots,
                "lines": list(self.lines)}

    @classmethod
    def from_dict(cls, data: dict) -> Sung:
        return cls(data["section"], data["block"], data["id"], dict(data.get("slots", {})), tuple(data["lines"]))


@dataclass(frozen=True)
class Lyrics:
    """A rendition's words: what each sung section of its form sings, and
    which verses, couplets, stanzas, slot words and tag syllable they are."""

    form: tuple[str, ...]  # the form they were drawn for
    seed: int | None  # the seed they were drawn with; None for the seed's own words
    sections: tuple[Sung, ...]  # one for each sung section of the form, in order
    leanings: Leanings | None = None  # as they bore on the draw: a person's words only where the bank has them

    @property
    def verses(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.sections if s.block == "verse")

    @property
    def couplets(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.sections if s.block == "refrain")

    @property
    def questions(self) -> tuple[str, ...]:
        return tuple(s.slots.get("question", "") for s in self.sections if s.block == "refrain")

    @property
    def bridges(self) -> tuple[str, ...]:
        return tuple(s.id for s in self.sections if s.block == "bridge")

    @property
    def tag(self) -> str | None:
        return next((s.id for s in self.sections if s.block == "tag"), None)

    def lines_for(self, genome: Genome, form: Iterable[str]) -> list[tuple[str, ...] | None]:
        """The lines each section of the form sings, None where it sings no
        words, checked against the form they were drawn for and the tune."""
        form = _form(form)
        if form != self.form:
            raise ValueError(f"these words were drawn for the form {' '.join(self.form)}, not {' '.join(form)}")
        drawn = iter(self.sections)
        out: list[tuple[str, ...] | None] = []
        for name in form:
            section = genome.section(name)
            if not section.lyrics:
                out.append(None)
                continue
            sung = next(drawn, None)
            if sung is None or sung.section != name:
                raise ValueError(f"these words have nothing for the {name} where the form sings it")
            if not sung.lines:
                out.append(None)
                continue
            if len(sung.lines) != len(section.phrases):
                raise ValueError(f"{name}: {len(sung.lines)} lines for {len(section.phrases)} phrases")
            for line, pid in zip(sung.lines, section.phrases):
                want, got = len(genome.phrases[pid].sung), len(syllables(line))
                if want != got:
                    raise ValueError(f"{name}: {line!r} has {got} syllables, phrase {pid} has {want} notes")
            out.append(sung.lines)
        if next(drawn, None) is not None:
            raise ValueError("these words have more sections than the form sings")
        return out

    def sheet(self, title: str | None = None) -> str:
        """The words as sung, for reading."""
        how = f"words drawn with seed {self.seed}" if self.seed is not None else "the seed's own words"
        out = ([title] if title else []) + [f"{how}; form: {' '.join(self.form)}"]
        for sung in self.sections:
            out += ["", f"[{sung.section}: {sung.id}]"] + [_readable(line) for line in sung.lines]
        return "\n".join(out) + "\n"

    def choices(self) -> str:
        """What was chosen for each sung section, one to a line."""
        rows = []
        for sung in self.sections:
            words = ", ".join(f"{name} {_slot_text(value)}" for name, value in sung.slots.items())
            rows.append(f"{sung.section:<8} {sung.id}" + (f"  ({words})" if words else ""))
        return "\n".join(rows) + "\n"

    def __str__(self) -> str:
        return self.sheet()

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "form": list(self.form),
            "leanings": self.leanings.to_dict() if self.leanings is not None else None,
            "sections": [s.to_dict() for s in self.sections],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Lyrics:
        leanings = data.get("leanings")
        return cls(
            form=tuple(data["form"]),
            seed=data.get("seed"),
            sections=tuple(Sung.from_dict(s) for s in data["sections"]),
            leanings=Leanings.from_dict(leanings) if leanings is not None else None,
        )


def _readable(line: str) -> str:
    return unmarked(line).replace("-", "")


def _slot_text(value) -> str:
    return "/".join(value.values()).replace("-", "") if isinstance(value, dict) else str(value).replace("-", "")




# The bank and its rules


def _bank(genome: Genome) -> tuple[dict, dict]:
    """The genome's bank and its rules, every rule one arrange knows how to keep."""
    bank = genome.source.get("bank")
    if not bank:
        raise ArrangeError(f"{genome.title} has no lyric bank to draw its words from")
    rules = bank.get("rules") or {}
    unknown = sorted(set(rules) - set(_RULES))
    if unknown:
        raise ArrangeError(f"the bank has rules for {unknown}, which arrange doesn't know how to keep")
    for block, known in _RULES.items():
        if block not in rules:
            raise ArrangeError(f"the bank's rules say nothing about the {block}")
        unknown = sorted(set(rules[block]) - known)
        if unknown:
            raise ArrangeError(f"the bank has {block} rules arrange doesn't know how to keep: {unknown}")
    for (block, key), value in _RULE_VALUES.items():
        if key in rules[block] and rules[block][key] != value:
            raise ArrangeError(f"arrange keeps the {block} rule {key} only as {value!r}, not {rules[block][key]!r}")
    # and every entry or slot a rule names is in the bank
    rr, br = rules["refrain"], rules["bridge"]
    couplets = [c["id"] for c in bank["refrain"]["couplets"]]
    stanzas = {b["id"]: b for b in bank.get("bridges", [])}
    always = stanzas.get(br["always"], {"lines": []})
    missing = {
        "refrain couplet_last": [c for c in [rr["couplet_last"]] if c not in couplets],
        "refrain once_per_song": [s for s in rr.get("once_per_song", ()) if s not in slot_names(bank["refrain"]["lines"])],
        "bridge always and extra": [b for b in [br["always"], *br.get("extra", ())] if b not in stanzas],
        "bridge once_per_song": [s for s in br.get("once_per_song", ()) if s not in slot_names(always["lines"])],
    }
    for rule, names in missing.items():
        if names:
            raise ArrangeError(f"the bank's {rule} rule names {names}, which the bank doesn't have")
    return bank, rules


@dataclass(frozen=True)
class _Verse:
    index: int
    id: str
    era: int | None
    mood: str
    rare: bool
    variant: bool  # rhymes other than the plain scheme, or runs a phrase over a line break
    opens: bool  # can be a song's first verse
    partners: tuple[str, ...]
    entry: dict


def _verses(bank: dict, rules: dict) -> list[_Verse]:
    first = dict(rules["verses"].get("first", {}))
    plain = first.get("scheme", "AABB")

    def attr(v: dict, key: str):
        return v.get(key, False if key == "enjambed" else None)

    return [
        _Verse(i, v["id"], v.get("era"), v["mood"], v.get("rarity") == "rare",
               v["scheme"] != plain or bool(v.get("enjambed", False)),
               all(attr(v, key) == want for key, want in first.items()),
               tuple(v.get("pairs_with", ())), v)
        for i, v in enumerate(bank["verses"])
    ]


class _VerseRules:
    """The bank's verse rules, as checks on a set of verses and on their order."""

    def __init__(self, rules: dict):
        vr = rules["verses"]
        self.first = dict(vr.get("first", {}))
        self.max_variants = vr.get("max_variants")
        self.max_rare = vr.get("max_rare")
        self.max_mood = dict(vr.get("max_mood", {}))
        self.apart = tuple(vr.get("never_adjacent", ()))
        self.era_order = vr.get("order") == "era"
        self.pairs_adjacent = vr.get("pairs") == "adjacent"

    def together(self, verses) -> bool:
        """At most so many variants, rare verses and verses of a mood in one song."""
        if self.max_variants is not None and sum(v.variant for v in verses) > self.max_variants:
            return False
        if self.max_rare is not None and sum(v.rare for v in verses) > self.max_rare:
            return False
        return all(sum(v.mood == mood for v in verses) <= most for mood, most in self.max_mood.items())

    def in_order(self, verses) -> bool:
        """The first can open a song; dated verses earliest first; no two of a
        mood kept apart side by side; a pair side by side."""
        if not verses[0].opens:
            return False
        if self.era_order:
            eras = [v.era for v in verses if v.era is not None]
            if any(a > b for a, b in zip(eras, eras[1:])):
                return False
        if any(a.mood == b.mood and a.mood in self.apart for a, b in zip(verses, verses[1:])):
            return False
        if self.pairs_adjacent:
            at = {v.id: i for i, v in enumerate(verses)}
            if any(abs(at[p] - i) != 1 for i, v in enumerate(verses) for p in v.partners if p in at):
                return False
        return True

    def orders(self, verses) -> list[tuple[_Verse, ...]]:
        """Every order the rules let these verses be sung in; none if they can't go together."""
        if not verses or not self.together(verses):
            return []
        return [p for p in itertools.permutations(verses) if self.in_order(p)]

    def why(self, verses) -> str | None:
        """Why these verses can't be sung in this order, in one plain sentence;
        None if they can. For different verses, None exactly when together()
        and in_order() both hold; a verse sung twice is refused first."""
        verses = list(verses)
        seen: dict[str, int] = {}
        for i, v in enumerate(verses):
            if v.id in seen:
                return f"the {v.id} verse is sung already, as verse {seen[v.id] + 1}"
            seen[v.id] = i
        if not verses:
            return None
        if not verses[0].opens:
            return self._opener(verses[0])
        return self._counts(verses) or self._years(verses) or self._placed(dict(enumerate(verses)))

    def pinned(self, fixed: dict[int, _Verse]) -> str | None:
        """Why verses fixed in these places (by index from 0) can't all be sung, whatever is sung around them;
        None if nothing about them alone rules it out."""
        if 0 in fixed and not fixed[0].opens:
            return self._opener(fixed[0])
        verses = [fixed[i] for i in sorted(fixed)]
        return self._counts(verses) or self._years(verses) or self._placed(fixed)

    def _opener(self, v: _Verse) -> str:
        return f"the first verse teaches the song's shape, so it is a plain one, and the {v.id} verse {_and(self._unplain(v))}"

    def _counts(self, verses) -> str | None:
        """At most so many variants, rare verses and verses of a mood in one song."""
        variants = [v for v in verses if v.variant]
        if self.max_variants is not None and len(variants) > self.max_variants:
            return (f"a song sings {_at_most(self.max_variants, 'verse')} that rhymes another way or runs a line "
                    f"on, and {_these(variants)} {_all(variants)} do")
        rare = [v for v in verses if v.rare]
        if self.max_rare is not None and len(rare) > self.max_rare:
            return f"a song sings {_at_most(self.max_rare, 'rare verse')}, and {_these(rare)} are {_all(rare)} rare"
        for mood, most in self.max_mood.items():
            same = [v for v in verses if v.mood == mood]
            if len(same) > most:
                return f"a song sings {_at_most(most, f'{mood} verse')}, and {_these(same)} are {_all(same)} {mood}"
        return None

    def _years(self, verses) -> str | None:
        """Dated verses, in the order they're sung, go earliest first."""
        if self.era_order:
            dated = [v for v in verses if v.era is not None]
            for a, b in zip(dated, dated[1:]):
                if a.era > b.era:
                    return (f"the verses are sung in the order of their years, so the {b.id} verse ({b.era}) "
                            f"can't come after the {a.id} verse ({a.era})")
        return None

    def _placed(self, at: dict[int, _Verse]) -> str | None:
        """No two of a mood kept apart in neighbouring places, and a pair in neighbouring places."""
        for i in sorted(at):
            a, b = at[i], at.get(i + 1)
            if b is not None and a.mood == b.mood and a.mood in self.apart:
                return f"two {a.mood} verses never come side by side, as the {a.id} and {b.id} verses would"
        if self.pairs_adjacent:
            where = {v.id: i for i, v in at.items()}
            for i in sorted(at):
                for p in at[i].partners:
                    if p in where and abs(where[p] - i) != 1:
                        return f"the {at[i].id} and {p} verses are a pair, and a pair is sung side by side"
        return None

    def _unplain(self, v: _Verse) -> list[str]:
        """What keeps a verse from opening a song, in words."""
        out = []
        for key, want in self.first.items():
            got = v.entry.get(key, False if key == "enjambed" else None)
            if got == want:
                continue
            if key == "scheme":
                out.append(f"rhymes {got} (not {want})")
            elif key == "rarity":
                out.append(f"is {got}")
            elif key == "enjambed":
                out.append("runs a line on" if got else "doesn't run a line on")
            else:
                out.append(f"has {key} {got}, not {want}")
        return out or ["can't open a song"]


_NUMBERS = ("no", "one", "two", "three", "four", "five", "six")


def _number(n: int) -> str:
    return _NUMBERS[n] if 0 <= n < len(_NUMBERS) else str(n)


def _at_most(n: int, noun: str) -> str:
    """'at most one light verse', 'at most two rare verses', 'no rare verse'."""
    return f"no {noun}" if n == 0 else f"at most {_number(n)} {noun}{'s' if n > 1 else ''}"


def _and(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def _these(verses) -> str:
    """'the hold and ring verses'."""
    return f"the {_and([v.id for v in verses])} verse{'s' if len(verses) > 1 else ''}"


def _all(items) -> str:
    return "both" if len(items) == 2 else "all"


def _search(verses: list[_Verse], rules: _VerseRules, k: int, order) -> list[tuple[_Verse, ...]] | None:
    """The orders of the first k verses, taken in the given order of
    preference, that the rules let a song sing together; None if no k can."""
    for combo in itertools.combinations(order, k):
        found = rules.orders([verses[i] for i in sorted(combo)])
        if found:
            return found
    return None


class _Song:
    """A genome's bank made ready to draw from: its verses and their rules,
    how many of each section it can fill, the words of every entry, and for
    each entry that is one of the seed's own blocks, the seed's lines to lend
    it their focus marks. Worked out once for each genome."""

    def __init__(self, genome: Genome):
        self.bank, self.rules = bank, rules = _bank(genome)
        self.verses = verses = _verses(bank, rules)
        self.checks = _VerseRules(rules)
        at = {v.id: v.index for v in verses}
        # a pair's partner, where the rules would let the two be sung together
        self.partners = [tuple(at[p] for p in v.partners if p in at and self.checks.orders([v, verses[at[p]]]))
                         for v in verses]
        eras = [v.era for v in verses if v.era is not None]
        self.eras = (min(eras), max(eras)) if eras else (0, 0)
        # what the rules as data allow: the verses they count, a couplet for
        # each refrain and never one twice, the canon and at most one extra stanza
        lo, hi = rules["verses"].get("count", (0, len(verses)))
        self.supported = {
            "verse": tuple(k for k in range(max(lo, 0), min(hi, len(verses)) + 1)
                           if k == 0 or _search(verses, self.checks, k, range(len(verses))) is not None),
            "refrain": tuple(range(len(bank["refrain"]["couplets"]) + 1)),
            "bridge": (0, 1, 2) if rules["bridge"].get("extra") else (0, 1),
        }
        refrain = bank["refrain"]
        head = len(refrain["lines"])
        seeds = {id(v): genome.seed_verses for v in bank["verses"]}
        seeds[id(refrain)] = [genome.refrain[:head]]
        seeds |= {id(c): [genome.refrain[head:]] for c in refrain["couplets"]}
        seeds |= {id(b): [genome.fixed["bridge"]] if "bridge" in genome.fixed else [] for b in bank.get("bridges", [])}
        entries = bank["verses"] + [refrain] + refrain["couplets"] + bank.get("bridges", [])
        self.marks = {id(e): _lender(e["lines"], e.get("slots", {}), seeds[id(e)]) for e in entries}
        self.entry_words = {id(e): _entry_words(e) for e in entries}
        self.known = frozenset().union(*self.entry_words.values(), *(_words(s) for s in bank["tag"]["syllables"]))

    def words(self, entry: dict) -> frozenset[str]:
        return self.entry_words[id(entry)]

    def sing(self, entry: dict, picks: dict[str, int]) -> tuple[str, ...]:
        """An entry's lines with its slots filled, and the seed's marks where it has them to lend."""
        return _lend(fill(entry["lines"], entry.get("slots", {}), picks), self.marks[id(entry)])


_SONGS: dict[int, tuple[Genome, _Song]] = {}


def _song(genome: Genome) -> _Song:
    """The genome's bank made ready, once for each genome: a genome doesn't change once loaded."""
    hit = _SONGS.get(id(genome))
    if hit is not None and hit[0] is genome:
        return hit[1]
    song = _Song(genome)
    if len(_SONGS) >= 8:
        _SONGS.clear()
    _SONGS[id(genome)] = (genome, song)
    return song


def forms(genome: Genome) -> dict[str, tuple[int, ...]]:
    """How many sections of each lyric block a form may have for the bank to
    fill it within its rules: for H, {"verse": (2, 3, 4), "refrain": (0, 1, 2,
    3, 4, 5, 6), "bridge": (0, 1, 2)}. Verses: as many as the rules count and
    the bank can sing together. Refrains: one couplet each, none twice, canon
    last. Bridge sections: the canon, then at most one extra stanza. A tag may
    come any number of times, always on its one syllable. (The genome's form
    template asks for more: three refrains and a bridge.)"""
    return dict(_song(genome).supported)


def problem(genome: Genome, form: Iterable[str], chosen: Mapping | None = None) -> str | None:
    """Why the bank can't fill a form within its rules, in one plain
    sentence; None if it can. With chosen (a person's choices, as arrange()
    takes them), also why those choices can't be sung in their places."""
    try:
        why = _problem(_song(genome).supported, _blocks(genome, _form(form)))
        if why is None and chosen:
            arrange(genome, form, 0, None, chosen)
        return why
    except ArrangeError as e:
        return str(e)


def _form(form: Iterable[str]) -> tuple[str, ...]:
    if isinstance(form, str):
        raise TypeError(f"a form is a sequence of section names, not one string: {form!r}")
    return tuple(form)


def _either(counts: tuple[int, ...]) -> str:
    """(2, 3, 4) as '2, 3 or 4'; a longer run as '1 to 6'."""
    if not counts:
        return "no"
    if len(counts) > 3 and counts == tuple(range(counts[0], counts[-1] + 1)):
        return f"{counts[0]} to {counts[-1]}"
    return f"{', '.join(map(str, counts[:-1]))} or {counts[-1]}" if len(counts) > 1 else str(counts[0])


def _problem(supported: dict[str, tuple[int, ...]], blocks: Counter) -> str | None:
    why = {
        "verse": "verses to a song",
        "refrain": "refrains to a song, each with its own couplet and canon last",
        "bridge": "bridge sections: the canon, and at most one extra stanza after it",
    }
    for block, allowed in supported.items():
        n = blocks[block]
        if n not in allowed:
            has = f"{n} {block} section{'' if n == 1 else 's'}"
            return f"this form has {has}; the bank's rules sing {_either(allowed)} {why[block]}"
    return None


# Weights: chance, tilted by the leanings


def _words(*texts: str) -> frozenset[str]:
    """The words that mean in some lines, not the little ones between them;
    a possessive also counts as its noun."""
    out = set()
    for text in texts:
        for token in _BRACES.sub(" ", text).split():
            word = clean(token)
            if word and word not in FUNCTION_WORDS:
                out.add(word)
                if word.endswith("'s"):
                    out.add(word[:-2])
    return frozenset(out)


def _entry_words(entry: dict) -> frozenset[str]:
    """Every word an entry can sing: its lines and every option of its slots."""
    texts = list(entry["lines"])
    for spec in entry.get("slots", {}).values():
        for column in spec.values() if isinstance(spec, dict) else [spec]:
            texts += column
    return _words(*texts)


def _option_words(spec, i: int) -> frozenset[str]:
    return _words(*(column[i] for column in spec.values())) if isinstance(spec, dict) else _words(spec[i])


def _affinity(choices, words, vocabulary: frozenset[str]) -> list[float]:
    """How much a person's words favor each of some choices: VOCAB more for
    each word they share with it, weighed by how few of the other choices
    have that word too, twice at most. words(choice) gives a choice's words."""
    n = len(choices)
    if not vocabulary or n < 2:
        return [1.0] * n
    sets = [words(c) for c in choices]
    have = Counter(w for s in sets for w in s)
    return [1.0 + VOCAB * min(sum(math.log(n / have[w]) / math.log(n) for w in sorted(s & vocabulary)), 2.0)
            for s in sets]


def _verse_weights(song: _Song, leanings: Leanings) -> tuple[np.ndarray, np.ndarray]:
    """Each verse's weight in the draw, and how far the leanings tilt it from
    where the bank has it (1 for no tilt)."""
    lo, hi = song.eras
    fondness = _affinity([v.entry for v in song.verses], song.words, leanings.vocabulary)
    weights, tilts = [], []
    for v, fond in zip(song.verses, fondness):
        tilt = fond * leanings.mood_weights.get(v.mood, 1.0)
        if v.rare:
            tilt *= SPAN ** leanings.rarity_appetite
        if v.era is not None and hi > lo:
            tilt *= SPAN ** (leanings.era_bias * (2.0 * (v.era - lo) / (hi - lo) - 1.0))
        weights.append((RARE if v.rare else 1.0) * tilt)
        tilts.append(tilt)
    # A verse that also comes as its partner's answer is drawn on its own less
    # often, by as much as its partner calls it (as often as it's drawn, up to
    # as often as the verse itself) and it answers: having a partner doesn't
    # make a verse commoner. A pair of equals: each two thirds as often alone.
    alone = [w / (1.0 + ANSWER * min(1.0, tilt) * sum(min(1.0, weights[j] / w) for j in partners))
             for w, tilt, partners in zip(weights, tilts, song.partners)]
    return np.array(alone, dtype=float), np.array(tilts, dtype=float)


def _rng(seed: int, part: int) -> np.random.Generator:
    return np.random.default_rng([_STREAM, int(seed), part])


def _draw(rng: np.random.Generator, weights) -> int:
    """One index, as likely as its weight."""
    total = np.cumsum(np.asarray(weights, dtype=float))
    return int(np.searchsorted(total, rng.random() * total[-1], side="right"))


def _sample(rng: np.random.Generator, weights, k: int) -> list[int]:
    """k different indices, each drawn as likely as its weight among those left."""
    left = np.array(weights, dtype=float)
    out = []
    for _ in range(k):
        i = _draw(rng, left)
        out.append(i)
        left[i] = 0.0
    return out


def _pick(names, slots: dict, rng: np.random.Generator, vocabulary: frozenset[str]) -> dict[str, int]:
    """An option for each named slot, the person's words favored."""
    return {name: _draw(rng, _affinity(range(width(slots, name)), lambda i, s=slots[name]: _option_words(s, i),
                                       vocabulary))
            for name in names}


def _value(spec, i: int):
    """A slot's chosen option as written: its words, or a coupled slot's by column."""
    return {column: options[i] for column, options in spec.items()} if isinstance(spec, dict) else spec[i]


def _chosen(entry: dict, picks: dict[str, int]) -> dict:
    """The words chosen for an entry's slots, in the order its lines use them."""
    slots = entry.get("slots", {})
    return {name: _value(slots[name], picks[name]) for name in slot_names(entry["lines"]) if name in picks}


def _turned(i: int, n: int, k: int) -> int:
    """Which of k turning words the i-th of n refrains asks, as genome.turn does:
    in order, and the last time round always the last word."""
    return k - 1 if n > 1 and i == n - 1 else i % max(k - 1, 1)


# Focus marks, lent by the seed


def _lender(lines, slots: dict, seed_blocks) -> list[list[str]] | None:
    """Where some way of singing a bank entry is one of the seed's own blocks,
    that block's lines, every way each can turn, to lend their focus marks."""
    ways = [[unmarked(line) for line in way] for way in expansions(lines, slots)]
    for block in seed_blocks:
        if len(block) != len(lines):
            continue
        options = [turns(line) for line in block]
        plain = [{unmarked(t) for t in o} for o in options]
        if any(all(w in p for w, p in zip(way, plain)) for way in ways):
            return options
    return None


def _lend(lines, options: list[list[str]] | None) -> tuple[str, ...]:
    """The lines with the seed's focus marks wherever a word is the seed's
    word in the same place; a line the bank marks itself keeps its own."""
    if options is None:
        return tuple(lines)
    out = []
    for line, candidates in zip(lines, options):
        best, agree = line, 0
        if "*" not in line:
            words = line.split()
            for ref in candidates:
                theirs = ref.split()
                if len(theirs) != len(words):
                    continue
                same = sum(unmarked(r) == w for r, w in zip(theirs, words))
                if same > agree:
                    best, agree = " ".join(r if unmarked(r) == w else w for r, w in zip(theirs, words)), same
        out.append(best)
    return tuple(out)


# The draw


def _draw_verses(song: _Song, k: int, weights: np.ndarray, tilts: np.ndarray,
                 rng: np.random.Generator) -> tuple[_Verse, ...]:
    """k verses the rules let a song sing together, in an order they allow:
    drawn one at a time as likely as their weights, except that once one of
    a pair is drawn its partner answers it next, ANSWER of the time (less if
    the leanings turn away from the partner; its rarity doesn't count
    against it, since it comes as an answer); drawn again until the rules
    can sing them."""
    if k == 0:
        return ()
    verses = song.verses
    for _ in range(ATTEMPTS):
        left = weights.copy()
        chosen: list[int] = []
        partner = None
        while len(chosen) < k:
            if partner is not None and rng.random() < ANSWER * min(1.0, tilts[partner]):
                i = partner
            else:
                i = _draw(rng, left)
            chosen.append(i)
            left[i] = 0.0
            partner = next((j for j in song.partners[i] if left[j] > 0), None)
        orders = song.checks.orders([verses[i] for i in sorted(chosen)])
        if orders:
            return orders[int(rng.integers(len(orders)))]
    # The leanings push hard against the rules: take the verses in a weighted
    # random order of preference and search for the first set that fits.
    keys = np.log(rng.random(len(verses))) / np.maximum(weights, 1e-300)
    found = _search(verses, song.checks, k, [int(i) for i in np.argsort(-keys, kind="stable")])
    if found is None:
        raise ArrangeError(f"the bank has no {k} verses its rules let a song sing together")
    return found[int(rng.integers(len(found)))]


def _refrains(song: _Song, n: int, rng: np.random.Generator,
              vocabulary: frozenset[str]) -> list[tuple[str, dict, tuple[str, ...]]]:
    """Each refrain round: its head with the question turning and the
    once-per-song slots chosen once, then a couplet, none twice, canon last."""
    spec, rr = song.bank["refrain"], song.rules["refrain"]
    slots = spec.get("slots", {})
    names = slot_names(spec["lines"])
    once = _pick([s for s in names if s in rr.get("once_per_song", ()) and s != "question"], slots, rng, vocabulary)
    last = next(c for c in spec["couplets"] if c["id"] == rr["couplet_last"])
    others = [c for c in spec["couplets"] if c["id"] != last["id"]]
    order = _sample(rng, _affinity(others, song.words, vocabulary), n - 1)
    out = []
    for i in range(n):
        picks = dict(once)
        if "question" in slots:
            picks["question"] = _turned(i, n, width(slots, "question"))
        picks.update(_pick([s for s in names if s not in picks], slots, rng, vocabulary))
        couplet = others[order[i]] if i < n - 1 else last
        cpicks = _pick(slot_names(couplet["lines"]), couplet.get("slots", {}), rng, vocabulary)
        lines = song.sing(spec, picks) + song.sing(couplet, cpicks)
        out.append((couplet["id"], _chosen(spec, picks) | _chosen(couplet, cpicks), lines))
    return out


def _bridges(song: _Song, n: int, rng: np.random.Generator,
             vocabulary: frozenset[str]) -> list[tuple[str, dict, tuple[str, ...]]]:
    """The canon stanza, its slots chosen once, and in a form that sings the
    bridge twice, one extra stanza after it."""
    if n == 0:
        return []
    stanzas = {b["id"]: b for b in song.bank["bridges"]}
    br = song.rules["bridge"]
    sung = [stanzas[br["always"]]]
    if n > 1:
        extras = [stanzas[e] for e in br.get("extra", ())]
        sung.append(extras[_draw(rng, _affinity(extras, song.words, vocabulary))])
    once: dict[str, int] = {}  # a once-per-song slot keeps its pick in any stanza that sings it
    out = []
    for stanza in sung:
        names = slot_names(stanza["lines"])
        picks = {s: once[s] for s in names if s in once}
        picks.update(_pick([s for s in names if s not in picks], stanza.get("slots", {}), rng, vocabulary))
        once.update({s: picks[s] for s in names if s in br.get("once_per_song", ())})
        out.append((stanza["id"], _chosen(stanza, picks), song.sing(stanza, picks)))
    return out


def _blocks(genome: Genome, form: tuple[str, ...]) -> Counter:
    blocks = Counter()
    for name in form:
        try:
            section = genome.section(name)
        except KeyError as e:
            raise ArrangeError(e.args[0]) from None
        if section.lyrics:
            blocks[section.lyrics] += 1
    return blocks


def arrange(genome: Genome, form: Iterable[str], seed: int, leanings: Leanings | None = None,
            chosen: Mapping | None = None) -> Lyrics:
    """The words for a concrete form (the section order a rendition sings,
    as in Params.form), drawn from the genome's bank within its rules:

    - verses, one per verse section: as many as the rules allow, the first a
      plain one that teaches the shape, at most one variant and one rare verse,
      dated verses earliest first, a pair side by side, no two dark verses
      side by side, at most one light one; each verse's slots chosen once;
    - refrains, one per refrain section: the question word turning in order
      and the last time asking who owns it (a lone refrain asks who made it,
      as the fixed refrain does), the once-per-song slots the same every
      time, and a couplet each time, none twice, canon last;
    - the bridge: the canon in the first bridge section, its slots chosen
      once, and if the form sings the bridge twice (bridge, bridge or bridge,
      bridge2) one extra stanza in the second;
    - the tag: one syllable for every note, the same in every tag section.

    A fixed block the bank doesn't hold is sung as the genome has it. Where a
    bank entry is one of the seed's own blocks, the seed's focus marks come
    with it. seed: a whole number at least 0. leanings tilt every choice and
    break no rule. The same genome, form, seed and leanings always give the
    same words. Raises ArrangeError when the form can't be filled within the
    rules; forms() says what can.

    chosen: a person's choices, kept in their places (see keep()): verses by
    place, refrain couplets, the refrain's and the bridge's once-a-song
    words, the second bridge's stanza, the tag's syllable. Everything not
    chosen is drawn as without them, and stays as drawn wherever the rules
    allow it beside the choices. Raises ArrangeError, saying why, when the
    choices themselves can't be sung together within the rules."""
    form = _form(form)
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError(f"the seed must be a whole number at least 0, not {seed!r}")
    song = _song(genome)
    blocks = _blocks(genome, form)
    why = _problem(song.supported, blocks)
    if why:
        raise ArrangeError(why)
    lean = leanings if leanings is not None else Leanings()
    vocabulary = lean.vocabulary

    rng = _rng(seed, _VERSES)
    verses = []
    for v in _draw_verses(song, blocks["verse"], *_verse_weights(song, lean), rng):
        picks = _pick(slot_names(v.entry["lines"]), v.entry.get("slots", {}), rng, vocabulary)
        verses.append((v.id, _chosen(v.entry, picks), song.sing(v.entry, picks)))
    drawn = {
        "verse": iter(verses),
        "refrain": iter(_refrains(song, blocks["refrain"], _rng(seed, _REFRAIN), vocabulary)),
        "bridge": iter(_bridges(song, blocks["bridge"], _rng(seed, _BRIDGE), vocabulary)),
    }
    tag = None
    if blocks["tag"]:
        options = song.bank["tag"]["syllables"]
        tag = options[_draw(_rng(seed, _TAG), _affinity(options, _words, vocabulary))]

    rounds, heard = Counter(), Counter()  # a fixed block the bank doesn't hold turns as realize turns it
    for name in form:
        rounds[genome.section(name).lyrics] += 1
    sections = []
    for name in form:
        section = genome.section(name)
        block = section.lyrics
        if not block:
            continue
        if block in drawn:
            key, slots, lines = next(drawn[block])
        elif block == "tag":
            key, slots = tag, {}
            lines = tuple(" ".join([tag] * len(genome.phrases[pid].sung)) + "." for pid in section.phrases)
        elif block in genome.fixed:
            key, slots = block, {}
            lines = tuple(turn(line, heard[block], rounds[block]) for line in genome.fixed[block])
            heard[block] += 1
        else:
            raise ArrangeError(f"the {name} section sings {block!r}, which neither the bank nor the genome has")
        sections.append(Sung(name, block, key, slots, tuple(lines)))

    # Only the person's words the bank has can bear on the draw, so only they
    # are kept: nothing more of them leaves the machine, and drawing again
    # with what is kept gives the same words.
    kept = Leanings(lean.mood_weights, lean.era_bias, lean.rarity_appetite, vocabulary & song.known)
    lyrics = Lyrics(form, int(seed), tuple(sections), kept)
    return keep(genome, lyrics, chosen, lean) if chosen else lyrics


def seed_lyrics(genome: Genome, form: Iterable[str]) -> Lyrics:
    """The seed's own words for a form, just as realize() sings them without a
    Lyrics: the seed verses in turn, and each fixed block as written, its
    turning word turning. Where the genome has a bank, each is named for the
    bank entry it is, with the slot words it uses."""
    form = _form(form)
    bank = genome.source.get("bank") or {}
    rounds, heard = Counter(), Counter()
    for name in form:
        rounds[genome.section(name).lyrics] += 1
    sections = []
    for name in form:
        block = genome.section(name).lyrics
        if not block:
            continue
        if block == "verse" and genome.seed_verses:
            n = heard[block] % len(genome.seed_verses)
            lines = genome.seed_verses[n]
            key, slots = _named(bank.get("verses", []), lines, f"seed{n + 1}")
        elif block in genome.fixed and block != "verse":
            lines = tuple(turn(line, heard[block], rounds[block]) for line in genome.fixed[block])
            key, slots = block, {}
            if block == "refrain" and bank.get("refrain"):
                spec = bank["refrain"]
                head = len(spec["lines"])
                key, slots = _named(spec["couplets"], lines[head:], block)
                picks = _match(spec["lines"], spec.get("slots", {}), lines[:head])
                slots = (_chosen(spec, picks) if picks is not None else {}) | slots
            elif block == "bridge":
                key, slots = _named(bank.get("bridges", []), lines, block)
            elif block == "tag":
                sung = {unmarked(s).strip(".,;:!?") for line in lines for s in syllables(line)}
                key = sung.pop() if len(sung) == 1 else block
        else:  # realize sings it without words
            sections.append(Sung(name, block, "", {}, ()))
            continue
        heard[block] += 1
        sections.append(Sung(name, block, key, slots, tuple(lines)))
    return Lyrics(form, None, tuple(sections))


def _match(lines, slots: dict, sung) -> dict[str, int] | None:
    """The slot options that make some lines the ones sung, marks aside; None if none do."""
    want = [unmarked(line) for line in sung]
    names = slot_names(lines)
    for combo in itertools.product(*(range(width(slots, n)) for n in names)):
        picks = dict(zip(names, combo))
        if fill(lines, slots, picks) == want:
            return picks
    return None


def _named(entries: list[dict], sung, fallback: str) -> tuple[str, dict]:
    """The bank entry some sung lines are, and its slot words; else the fallback name."""
    for entry in entries:
        if len(entry["lines"]) == len(sung):
            picks = _match(entry["lines"], entry.get("slots", {}), sung)
            if picks is not None:
                return entry["id"], _chosen(entry, picks)
    return fallback, {}


# A person's choices, kept in their places

_PLACED = 16  # the streams the words drawn around a person's choices come from, apart from the draw's own
CHOSEN = ("verses", "couplets", "refrain", "bridge", "bridge2", "tag")


def _options(spec) -> list:
    """A slot's options as written: its words, or a coupled slot's by column."""
    n = len(next(iter(spec.values()))) if isinstance(spec, dict) else len(spec)
    return [_value(spec, i) for i in range(n)]


def _label(value) -> str:
    """How an option reads: its words, a coupled slot by its noun (else its first column)."""
    if isinstance(value, dict):
        value = value.get("noun", next(iter(value.values())))
    return str(value).replace("-", "")


def _option(spec, value) -> int | None:
    """Which option of a slot these words are: as written, or as they read (hyphens and case aside)."""
    for i, option in enumerate(_options(spec)):
        if option == value or (isinstance(value, str) and _label(option).lower() == value.replace("-", "").lower()):
            return i
    return None


def _picks(entry: dict, slots: Mapping) -> dict[str, int]:
    """The option each of an entry's slots was given, from the words a Sung records for them."""
    spec = entry.get("slots", {})
    out = {}
    for name in slot_names(entry["lines"]):
        if name in slots:
            i = _option(spec[name], slots[name])
            if i is not None:
                out[name] = i
    return out


def _chosen_slots(entry: dict, wanted: Mapping, what: str) -> dict[str, int]:
    """The options a person chose for an entry's slots, every one checked."""
    spec = entry.get("slots", {})
    names = slot_names(entry["lines"])
    out = {}
    for name, value in (wanted or {}).items():
        if name not in names:
            raise ArrangeError(f"{what} has no {name} to choose")
        i = _option(spec[name], value)
        if i is None:
            raise ArrangeError(f"{what}'s {name} can be {_and([_label(o) for o in _options(spec[name])])}, "
                               f"not {_label(value)}")
        out[name] = i
    return out


def _ordered(song: _Song, lean: Leanings, seed: int) -> list[_Verse]:
    """Every verse, in an order drawn by weight: the ones to try first when some must be drawn again."""
    weights, _ = _verse_weights(song, lean)
    rng = _rng(seed, _PLACED)
    keys = np.log(rng.random(len(song.verses))) / np.maximum(weights, 1e-300)
    return [song.verses[int(i)] for i in np.argsort(-keys, kind="stable")]


def _place(song: _Song, current: list[_Verse], fixed: dict[int, _Verse], lean: Leanings, seed: int) -> list[_Verse]:
    """The verses with each chosen one in its place and the rest as they were wherever the rules allow;
    where they don't, as few of the rest as need to be are drawn again, by weight, to make the rules hold."""
    n = len(current)
    ids = [v.id for v in fixed.values()]
    twice = next((i for i in ids if ids.count(i) > 1), None)
    if twice:
        raise ArrangeError(f"the {twice} verse is chosen for two places, and a verse is sung once")
    why = song.checks.pinned(fixed)
    if why:  # the chosen verses rule themselves out, whatever is sung around them
        raise ArrangeError(why)
    base = [fixed.get(i, v) for i, v in enumerate(current)]
    taken = {v.id for v in fixed.values()}
    must = [i for i in range(n) if i not in fixed and base[i].id in taken]  # it is sung in a chosen place now
    others = [i for i in range(n) if i not in fixed and i not in must]
    order = _ordered(song, lean, seed)
    for r in range(len(others) + 1):
        for extra in itertools.combinations(others, r):
            free = set(must) | set(extra)
            found = _fill(song, base, free, order)
            if found is not None:
                return found
    raise ArrangeError("no verse in the bank can go between the verses chosen within the rules")


def _fill(song: _Song, base: list[_Verse], free: set[int], order: list[_Verse]) -> list[_Verse] | None:
    """base with a verse drawn for each free place (first in order that the rules allow), or None."""
    seq = list(base)
    held = {v.id for i, v in enumerate(base) if i not in free}

    def walk(i: int) -> bool:
        if i == len(seq):
            return song.checks.why(seq) is None
        if i not in free:
            return song.checks.why(seq[: i + 1]) is None and walk(i + 1)
        for v in order:
            if v.id in held or any(seq[j].id == v.id for j in range(i) if j in free):
                continue
            seq[i] = v
            if song.checks.why(seq[: i + 1]) is None and walk(i + 1):
                return True
        return False

    return seq if walk(0) else None


def keep(genome: Genome, lyrics: Lyrics, chosen: Mapping, leanings: Leanings | None = None) -> Lyrics:
    """Some drawn words with a person's choices kept in their places:

    - "verses": {place: {"id": verse, "slots": {slot: words}}} (or just the
      verse's id), by its place among the form's verses from 0. A chosen
      verse is sung there; the verses around it stay as drawn wherever the
      rules allow them beside it, and where they don't, as few as need to be
      are drawn again, by weight, until the rules hold. Its slots are the
      ones chosen, else as drawn if it was drawn there, else drawn.
    - "couplets": {place: couplet}, by refrain from 0: never the canon but in
      the last refrain, which always sings it; a couplet another refrain was
      singing trades places with the one it replaces.
    - "refrain": {slot: words}: the refrain's once-a-song words (while, then),
      in every refrain. The question turns by rule and can't be chosen.
    - "bridge": {slot: words}: the bridge's once-a-song words, in every
      stanza that sings them. "bridge2": the second bridge section's stanza.
    - "tag": the tag's syllable, in every tag.

    Words for anything drawn again come from their own streams of the
    seed, so the same choices give the same words. Raises ArrangeError, in
    one plain sentence, when a choice isn't in the bank or can't be kept
    within the rules."""
    unknown = sorted(set(chosen) - set(CHOSEN))
    if unknown:
        raise ArrangeError(f"words can be chosen for the {_and(list(CHOSEN))}, not {_and(unknown)}")
    song = _song(genome)
    lean = leanings if leanings is not None else (lyrics.leanings or Leanings())
    vocabulary = lean.vocabulary
    seed = int(lyrics.seed or 0)
    sections = list(lyrics.sections)
    at = {block: [k for k, s in enumerate(sections) if s.block == block] for block in ("verse", "refrain", "bridge", "tag")}

    # ---- verses
    pins = {int(i): (p if isinstance(p, Mapping) else {"id": p}) for i, p in (chosen.get("verses") or {}).items()}
    if pins:
        places = at["verse"]
        by_id = {v.id: v for v in song.verses}
        for i, pin in sorted(pins.items()):
            if not 0 <= i < len(places):
                raise ArrangeError(f"this form sings {_number(len(places))} verses, so it has no verse {i + 1}")
            if pin.get("id") not in by_id:
                raise ArrangeError(f"the bank has no verse called {pin.get('id')!r}")
        current = [by_id.get(sections[k].id) for k in places]
        if any(v is None for v in current):
            raise ArrangeError("these words' verses aren't all from the bank, so they can't be chosen among")
        order = _place(song, current, {i: by_id[p["id"]] for i, p in pins.items()}, lean, seed)
        for i, v in enumerate(order):
            k = places[i]
            wanted = pins.get(i, {}).get("slots") or {}
            if v.id == sections[k].id and not wanted:
                continue
            entry = v.entry
            picks = _picks(entry, sections[k].slots) if v.id == sections[k].id else {}
            picks |= _chosen_slots(entry, wanted, f"the {v.id} verse")
            names = [n for n in slot_names(entry["lines"]) if n not in picks]
            if names:
                picks |= _pick(names, entry.get("slots", {}), _rng(seed, _PLACED + 1 + i), vocabulary)
            sections[k] = Sung(sections[k].section, "verse", v.id, _chosen(entry, picks), song.sing(entry, picks))

    # ---- refrains
    couplet_pins = {int(i): c for i, c in (chosen.get("couplets") or {}).items()}
    head_pins = dict(chosen.get("refrain") or {})
    if couplet_pins or head_pins:
        spec, rr = song.bank["refrain"], song.rules["refrain"]
        couplets = {c["id"]: c for c in spec["couplets"]}
        last, places = rr["couplet_last"], at["refrain"]
        n = len(places)
        for i, cid in sorted(couplet_pins.items()):
            if not 0 <= i < n:
                raise ArrangeError(f"this form sings {_number(n)} refrains, so it has no refrain {i + 1}")
            if cid not in couplets:
                raise ArrangeError(f"the refrain has no couplet called {cid!r}")
            if i == n - 1 and cid != last:
                raise ArrangeError(f"the last refrain always sings the {last} couplet")
            if cid == last and i != n - 1:
                raise ArrangeError(f"the {last} couplet is the last refrain's, and only the last's")
        chosen_ids = list(couplet_pins.values())
        twice = next((c for c in chosen_ids if chosen_ids.count(c) > 1), None)
        if twice:
            raise ArrangeError(f"the {twice} couplet is chosen for two refrains, and each refrain sings its own")
        if "question" in head_pins:
            raise ArrangeError("the refrain's question turns by the song's rule, and the last refrain asks who owns it")
        head = _chosen_slots(spec, head_pins, "the refrain")
        ids = [sections[k].id for k in places]
        for i, cid in couplet_pins.items():
            if ids[i] != cid:
                if cid in ids and ids.index(cid) not in couplet_pins:
                    ids[ids.index(cid)] = ids[i]  # the couplet it replaces moves to where this one was
                ids[i] = cid
        for r, k in enumerate(places):
            s = sections[k]
            if ids[r] == s.id and not head:
                continue
            couplet = couplets[ids[r]]
            picks = _picks(spec, s.slots) | head
            if ids[r] == s.id:
                cpicks = _picks(couplet, s.slots)
            else:
                cpicks = _pick(slot_names(couplet["lines"]), couplet.get("slots", {}), _rng(seed, _PLACED + 8 + r),
                               vocabulary)
            sections[k] = Sung(s.section, "refrain", couplet["id"], _chosen(spec, picks) | _chosen(couplet, cpicks),
                               song.sing(spec, picks) + song.sing(couplet, cpicks))

    # ---- the bridge
    bridge_pins = dict(chosen.get("bridge") or {})
    second = chosen.get("bridge2")
    if bridge_pins or second is not None:
        stanzas = {b["id"]: b for b in song.bank.get("bridges", [])}
        places = at["bridge"]
        extra = tuple(song.rules["bridge"].get("extra", ()))
        if second is not None:
            if len(places) < 2:
                raise ArrangeError("this form sings the bridge once, so it has no second stanza to choose")
            if second not in extra:
                raise ArrangeError(f"the second bridge sings the {_and(list(extra))} stanza, not {second!r}")
        sung = [stanzas.get(sections[k].id) for k in places]
        if second is not None:
            sung[1] = stanzas[second]
        names = {n for st in sung if st for n in slot_names(st["lines"])}
        stray = sorted(set(bridge_pins) - names)
        if stray:
            raise ArrangeError(f"the bridge has no {_and(stray)} to choose")
        for r, (k, stanza) in enumerate(zip(places, sung)):
            if stanza is None:
                continue
            s = sections[k]
            own = {n: v for n, v in bridge_pins.items() if n in slot_names(stanza["lines"])}
            if stanza["id"] == s.id and not own:
                continue
            picks = (_picks(stanza, s.slots) if stanza["id"] == s.id else {}) | _chosen_slots(stanza, own, "the bridge")
            rest = [n for n in slot_names(stanza["lines"]) if n not in picks]
            if rest:
                picks |= _pick(rest, stanza.get("slots", {}), _rng(seed, _PLACED + 12 + r), vocabulary)
            sections[k] = Sung(s.section, "bridge", stanza["id"], _chosen(stanza, picks), song.sing(stanza, picks))

    # ---- the tag
    tag = chosen.get("tag")
    if tag is not None:
        options = list(song.bank["tag"]["syllables"])
        if tag not in options:
            raise ArrangeError(f"the tag sings {_and(options)}, not {tag!r}")
        if not at["tag"]:
            raise ArrangeError("this form has no tag to sing it on")
        for k in at["tag"]:
            s = sections[k]
            lines = tuple(" ".join([tag] * len(genome.phrases[pid].sung)) + "." for pid in genome.section(s.section).phrases)
            sections[k] = Sung(s.section, "tag", tag, {}, lines)

    return Lyrics(lyrics.form, lyrics.seed, tuple(sections), lyrics.leanings)


def _readable_lines(entry: dict) -> list[str]:
    """An entry's lines as they read with each slot's first option."""
    names = slot_names(entry["lines"])
    return [_readable(line) for line in fill(entry["lines"], entry.get("slots", {}), dict.fromkeys(names, 0))]


def _slot_choices(entry: dict, slots: Mapping, skip=()) -> list[dict]:
    """An entry's swappable words: each slot's options as they read, and which is sung."""
    spec = entry.get("slots", {})
    out = []
    for name in slot_names(entry["lines"]):
        if name in skip:
            continue
        options = _options(spec[name])
        at = _option(spec[name], slots[name]) if name in slots else None
        out.append({"slot": name, "options": [_label(o) for o in options],
                    "sung": _label(options[at]) if at is not None else None})
    return out


def options(genome: Genome, lyrics: Lyrics, block: str, index: int = 0) -> dict:
    """Every choice for one sung section of some words: the index-th verse or refrain (from 0), the bridge
    (0 the first bridge section, 1 the second) or the tag. Each choice is allowed or refused, with the reason
    problem() would give; a verse refused here says where else it could go. Also the section's swappable
    words, and anything the song's rules fix, with why."""
    song = _song(genome)
    sections = [s for s in lyrics.sections if s.block == block]
    if not 0 <= index < len(sections):
        raise ArrangeError(f"these words have no {block} {index + 1}")
    here = sections[index]
    out: dict = {"block": block, "index": index, "sung": here.id, "choices": [], "words": [], "fixed": []}
    if block == "verse":
        by_id = {v.id: v for v in song.verses}
        current = [by_id.get(s.id) for s in sections]
        whole = None not in current
        for v in song.verses:
            seq = [x for x in (current[:index] + [v] + current[index + 1:]) if x is not None]
            why = song.checks.why(seq)
            elsewhere, reorder = [], None
            if why and whole:
                # where else it could go: in place of another verse; or here, the verses reordered as the
                # rules ask (moving as few as can be), if only their order is in the way
                for j in range(len(current)):
                    if j != index and v.id != current[j].id:
                        if song.checks.why(current[:j] + [v] + current[j + 1:]) is None:
                            elsewhere.append(j)
                if v.id not in {x.id for k, x in enumerate(current) if k != index}:
                    orders = song.checks.orders(seq)
                    if orders:
                        best = min(orders, key=lambda o: sum(a.id != b.id for a, b in zip(o, seq)))
                        reorder = [x.id for x in best]
            out["choices"].append({
                "id": v.id, "lines": list(here.lines) if v.id == here.id else _readable_lines(v.entry),
                "mood": v.mood, "era": v.era, "rare": v.rare, "variant": v.variant, "allowed": why is None,
                "why": why, "elsewhere": elsewhere, "reorder": reorder})
        entry = by_id.get(here.id)
        out["words"] = _slot_choices(entry.entry, here.slots) if entry else []
    elif block == "refrain":
        spec, rr = song.bank["refrain"], song.rules["refrain"]
        last = rr["couplet_last"]
        others = {s.id: i for i, s in enumerate(sections)}
        n = len(sections)
        for c in spec["couplets"]:
            why = None
            if index == n - 1 and c["id"] != last:
                why = f"the last refrain always sings the {last} couplet"
            elif c["id"] == last and index != n - 1:
                why = f"the {last} couplet is the last refrain's, and only the last's"
            out["choices"].append({"id": c["id"], "lines": _readable_lines(c), "allowed": why is None, "why": why,
                                   "trades": others.get(c["id"]) if why is None and c["id"] != here.id else None})
        out["words"] = _slot_choices(spec, here.slots, skip=("question",))
        question = here.slots.get("question")
        if question is not None:
            out["fixed"].append({"what": "question", "sung": _label(question),
                                 "why": "the question turns each time the refrain comes round, and the last "
                                        "refrain asks who owns it"})
        if index == n - 1:
            out["fixed"].append({"what": "couplet", "sung": last, "why": f"the last refrain always sings the {last} couplet"})
    elif block == "bridge":
        stanzas = {b["id"]: b for b in song.bank.get("bridges", [])}
        br = song.rules["bridge"]
        if index == 0:
            out["fixed"].append({"what": "stanza", "sung": here.id,
                                 "why": f"the bridge always sings its {br['always']} stanza first"})
        else:
            for sid in br.get("extra", ()):
                out["choices"].append({"id": sid, "lines": _readable_lines(stanzas[sid]), "allowed": True, "why": None})
        if here.id in stanzas:
            out["words"] = _slot_choices(stanzas[here.id], here.slots)
    elif block == "tag":
        for syllable in song.bank["tag"]["syllables"]:
            out["choices"].append({"id": syllable, "lines": [], "allowed": True, "why": None})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m songbird.arrange",
                                     description="Draw a song's words from its lyric bank and print them.")
    parser.add_argument("genome", help="path to a genome JSON file with a bank")
    parser.add_argument("--seed", type=int, default=0, help="the seed to draw with (default 0)")
    parser.add_argument("--form", nargs="+", help="the section order to fill (default: the seed's form)")
    parser.add_argument("--json", action="store_true", help="print the record as JSON instead")
    parser.add_argument("--forms", action="store_true", help="print how many of each sung section the bank can fill")
    args = parser.parse_args(argv)

    genome = load(args.genome)
    try:
        if args.forms:
            for block, counts in forms(genome).items():
                print(f"{block}: {_either(counts)}")
            print("tag: any number, one syllable")
            return 0
        form = tuple(args.form) if args.form else tuple(genome.seed_params["form"])
        lyrics = arrange(genome, form, args.seed)
    except (ArrangeError, ValueError) as e:
        print(f"can't fill that form: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(lyrics.to_dict(), indent=2))
        return 0
    print(lyrics.sheet(genome.title))
    print(lyrics.choices(), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
