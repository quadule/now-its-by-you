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

from .bank import MOODS, expansions, fill, head_ids, refrain_rules_problem, slot_names, unmarked, width
from .genome import Genome, load, syllables, turn, turns
from .phonetics import FUNCTION_WORDS, clean

RARE = 1 / 3  # a rare verse comes a third as often as a common one
SPAN = 3.0  # a full leaning, +1 or -1, makes a choice up to this many times likelier or less likely
VOCAB = 1.5  # added to a choice's weight for a word of the person's that no other choice has, twice at most
ANSWER = 0.5  # once one verse of a pair is drawn, how often its partner answers it next (less if leaned away from)
MOOD_WEIGHTS = (0.05, 20.0)  # a mood's weight is held in this range: leanings steer, they never forbid
ATTEMPTS = 2000  # sets of verses drawn before searching the bank for one instead
_STREAM = 0x5EED  # the words draw from their own stream of a seed, apart from the rest of a rendition
# and each part of the song from its own, so one can't shift another
_VERSES, _REFRAIN, _BRIDGE, _TAG, _HEADS, _QUESTIONS, _DISTINCT = range(7)

_BRACES = re.compile(r"\{[^{}]*\}")

# Every rule the bank can state that arrange keeps; a rule it doesn't know is an error, not a silence.
_RULES = {
    "verses": {"count", "first", "max_variants", "max_rare", "order", "never_adjacent", "max_mood", "pairs", "note"},
    "refrain": {"question", "question_first", "first", "last", "once_per_song", "distinct", "couplet_last", "couplet_repeat",
                "head_first", "head_last", "head_repeat", "note"},
    "bridge": {"always", "extra", "once_per_song", "note"},
    "tag": {"once_per_song", "note"},
}
_RULE_VALUES = {
    ("verses", "order"): ("era",),
    ("verses", "pairs"): ("adjacent",),
    ("refrain", "question"): ("turn", "draw"),
    ("refrain", "couplet_repeat"): (False,),
    ("refrain", "head_repeat"): (False,),
    ("tag", "once_per_song"): ("syllable",),
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
    head: str | None = None  # a refrain sung with another of its heads: that head's id (None: its own lines)

    @property
    def name(self) -> str:
        """What it sings, for reading: an id, or a refrain's other head and its couplet ("so + true")."""
        return f"{self.head} + {self.id}" if self.head else self.id

    def to_dict(self) -> dict:
        out = {"section": self.section, "block": self.block, "id": self.id, "slots": self.slots,
               "lines": list(self.lines)}
        if self.head is not None:
            out["head"] = self.head
        return out

    @classmethod
    def from_dict(cls, data: dict) -> Sung:
        return cls(data["section"], data["block"], data["id"], dict(data.get("slots", {})), tuple(data["lines"]),
                   data.get("head"))


@dataclass(frozen=True)
class Lyrics:
    """A rendition's words: what each sung section of its form sings, and
    which verses, couplets, stanzas, slot words and tag syllable they are."""

    form: tuple[str, ...]  # the form they were drawn for
    seed: int | None  # the seed they were drawn with; None for the seed's own words and for held words
    sections: tuple[Sung, ...]  # one for each sung section of the form, in order
    leanings: Leanings | None = None  # as they bore on the draw: a person's words only where the bank has them
    held: bool = False  # the words a lineage holds (sing()), handed down and changed a little at a time

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
    def heads(self) -> tuple[str | None, ...]:
        """Each refrain's head: None where it sings its own lines, else the other head's id."""
        return tuple(s.head for s in self.sections if s.block == "refrain")

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
        how = ("the words this lineage holds" if self.held else
               f"words drawn with seed {self.seed}" if self.seed is not None else "the seed's own words")
        out = ([title] if title else []) + [f"{how}; form: {' '.join(self.form)}"]
        for sung in self.sections:
            out += ["", f"[{sung.section}: {sung.name}]"] + [_readable(line) for line in sung.lines]
        return "\n".join(out) + "\n"

    def choices(self) -> str:
        """What was chosen for each sung section, one to a line."""
        rows = []
        for sung in self.sections:
            words = ", ".join(f"{name} {_slot_text(value)}" for name, value in sung.slots.items())
            rows.append(f"{sung.section:<8} {sung.name}" + (f"  ({words})" if words else ""))
        return "\n".join(rows) + "\n"

    def __str__(self) -> str:
        return self.sheet()

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "form": list(self.form),
            "leanings": self.leanings.to_dict() if self.leanings is not None else None,
            "sections": [s.to_dict() for s in self.sections],
            **({"held": True} if self.held else {}),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Lyrics:
        leanings = data.get("leanings")
        return cls(
            form=tuple(data["form"]),
            seed=data.get("seed"),
            sections=tuple(Sung.from_dict(s) for s in data["sections"]),
            leanings=Leanings.from_dict(leanings) if leanings is not None else None,
            held=bool(data.get("held", False)),
        )


def _readable(line: str) -> str:
    """A line as a person reads it: no focus marks, no syllable hyphens, no says (bass{fish}: songbird.heteronyms)."""
    from .heteronyms import bare

    return bare(unmarked(line)).replace("-", "")


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
    for (block, key), values in _RULE_VALUES.items():
        if key in rules[block] and rules[block][key] not in values:
            raise ArrangeError(f"arrange keeps the {block} rule {key} only as {' or '.join(map(repr, values))}, "
                               f"not {rules[block][key]!r}")
    # and every entry or slot a rule names is in the bank
    rr, br = rules["refrain"], rules["bridge"]
    couplets = [c["id"] for c in bank["refrain"]["couplets"]]
    stanzas = {b["id"]: b for b in bank.get("bridges", [])}
    always = stanzas.get(br["always"], {"lines": []})
    missing = {
        "refrain couplet_last": [c for c in [rr["couplet_last"]] if c not in couplets],
        "refrain once_per_song": [s for s in rr.get("once_per_song", ()) if s not in slot_names(bank["refrain"]["lines"])],
        "refrain head_first and head_last": [h for h in (rr.get("head_first"), rr.get("head_last"))
                                             if h is not None and h not in head_ids(bank["refrain"])],
        "bridge always and extra": [b for b in [br["always"], *br.get("extra", ())] if b not in stanzas],
        "bridge once_per_song": [s for s in br.get("once_per_song", ()) if s not in slot_names(always["lines"])],
    }
    for rule, names in missing.items():
        if names:
            raise ArrangeError(f"the bank's {rule} rule names {names}, which the bank doesn't have")
    why = refrain_rules_problem(bank["refrain"], rr)
    if why:
        raise ArrangeError(why)
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
        # every head a refrain can sing, by id, its own lines first: each sings the refrain's slots by name,
        # and fixed holds the option each of its fixed slots is held to
        shared = refrain.get("slots", {})
        self.head_id = head_ids(refrain)[0]
        self.heads = {self.head_id: refrain}
        self.fixed: dict[str, dict[str, int]] = {self.head_id: {}}
        for other in refrain.get("heads", []):
            names = slot_names(other["lines"])
            if len(other["lines"]) != head or not set(names) <= set(shared):
                raise ArrangeError(f"the refrain's {other['id']} head doesn't sing on the refrain's lines and slots")
            fixed = {name: _index(shared[name], word) for name, word in other.get("fixed", {}).items()}
            if None in fixed.values() or not set(fixed) <= set(names):
                raise ArrangeError(f"the refrain's {other['id']} head fixes words its slots don't have")
            self.heads[other["id"]] = {"id": other["id"], "lines": other["lines"], "slots": {n: shared[n] for n in names}}
            self.fixed[other["id"]] = fixed
        seeds = {id(v): genome.seed_verses for v in bank["verses"]}
        seeds |= {id(h): [genome.refrain[:head]] for h in self.heads.values()}
        seeds |= {id(c): [genome.refrain[head:]] for c in refrain["couplets"]}
        seeds |= {id(b): [genome.fixed["bridge"]] if "bridge" in genome.fixed else [] for b in bank.get("bridges", [])}
        entries = bank["verses"] + list(self.heads.values()) + refrain["couplets"] + bank.get("bridges", [])
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


def _head_rule(song: _Song, i: int, n: int) -> str | None:
    """The head the rules give the i-th of n refrains, if they give one: the first's, the last's (a lone
    refrain is the first)."""
    rr = song.rules["refrain"]
    if i == 0 and rr.get("head_first"):
        return rr["head_first"]
    if n > 1 and i == n - 1 and rr.get("head_last"):
        return rr["head_last"]
    return None


def _question_rule(song: _Song, i: int, n: int, head: str) -> int | None:
    """The question the rules give the i-th of n refrains sung with this head, if they give one: the word
    its head fixes; else, turning (as the fixed refrain turns), the i-th word; else the first refrain's
    (_firsts: the first word, unless the rules give it several to draw among) and the last word for the
    last (a lone refrain asks as a first one does). None: the refrain's own to ask (or, for a first
    refrain with several words, drawn among them)."""
    if head in song.fixed and "question" in song.fixed[head]:
        return song.fixed[head]["question"]
    k = width(song.bank["refrain"]["slots"], "question")
    if song.rules["refrain"].get("question", "turn") == "turn" or k < 3:
        return _turned(i, n, k)
    if i == 0:
        firsts = _firsts(song)
        return firsts[0] if len(firsts) == 1 else None
    return k - 1 if i == n - 1 else None


def _firsts(song: _Song) -> list[int]:
    """The questions the first refrain may ask: the rules' question_first words, in the bank's order, or
    else the first word only, as the fixed refrain asks it."""
    slots = song.bank["refrain"]["slots"]
    words = song.rules["refrain"].get("question_first")
    if not words:
        return [0]
    return [v for v in range(width(slots, "question")) if _label(_value(slots["question"], v)).replace("-", "") in words]


def _ends_fixed(song: _Song, i: int, n: int, head: str) -> dict[str, int]:
    """The slot words the rules give the i-th of n refrains for being first or last (rules "first" and
    "last": {slot: word}), as slot -> index: H's first and last refrains say "this song", the ones between
    may say "that song" or "the song". A word the head fixes, or the question, isn't among them."""
    rr, slots = song.rules["refrain"], song.bank["refrain"].get("slots", {})
    words = {**(rr.get("first", {}) if i == 0 else {}), **(rr.get("last", {}) if n and i == n - 1 else {})}
    out = {}
    for slot, word in words.items():
        if slot == "question" or slot in song.fixed.get(head, {}) or slot not in slots:
            continue
        v = _index(slots[slot], word)
        if v is not None:
            out[slot] = v
    return out


def _ends_say(song: _Song, i: int, n: int, slot: str, v: int) -> str:
    slots = song.bank["refrain"].get("slots", {})
    return f"{_nth_refrain(i, n)} sings its {slot} as {_label(_value(slots[slot], v)).replace('-', '')}"


def _firsts_say(song: _Song) -> str:
    """'asks who made, wrote or sang': the first refrain's questions, for a sentence."""
    slots = song.bank["refrain"]["slots"]
    said = [_label(_value(slots["question"], v)).replace("-", "") for v in _firsts(song)]
    return "asks who " + (", ".join(said[:-1]) + " or " + said[-1] if len(said) > 1 else said[0])


def _asks(song: _Song, head: str) -> bool:
    return "question" in slot_names(song.heads[head]["lines"])


def _head_order(song: _Song, n: int, rng: np.random.Generator, vocabulary: frozenset[str]) -> list[str]:
    """The head each of n refrains sings: where the rules give one (the first's and the last's), that;
    between them, drawn among the heads, the refrain's own as likely as any other (the person's words
    favoured), and another head at most once a song where the rules say so."""
    out: list = [_head_rule(song, i, n) for i in range(n)]
    once = song.rules["refrain"].get("head_repeat", True) is False
    for i in range(n):
        if out[i] is None:
            asked = {_asks_as_written(song, h) for h in out if h is not None} - {None}
            free = [h for h in song.heads if h == song.head_id or not (once and h in out)]
            # never two heads that ask the same question as written (swear and grew: who made it)
            free = [h for h in free if h in out or _asks_as_written(song, h) not in asked]
            out[i] = free[_draw(rng, _affinity([song.heads[h] for h in free], song.words, vocabulary))]
    return out


def _asks_as_written(song: _Song, head: str) -> int | None:
    """The question a head fixes (asks as written), as the option's index; None where it asks whatever
    its refrain draws."""
    return song.fixed.get(head, {}).get("question")


def _twins_problem(song: _Song, heads: list[str]) -> str | None:
    """Why some heads can't be sung in one song for asking the same question as written, in one plain
    sentence; None if no two do."""
    asked: dict[int, str] = {}
    for h in heads:
        q = _asks_as_written(song, h)
        if q is None:
            continue
        if asked.get(q, h) != h:
            word = _label(_value(song.bank["refrain"]["slots"]["question"], q)).replace("-", "")
            return f"the {asked[q]} and {h} heads both ask who {word} it, as written"
        asked[q] = h
    return None


def _shared(song: _Song) -> tuple[str, ...]:
    """The refrain's slots in which each refrain sings a word no other sings while the words last: the
    question where the rules draw it (between the first refrain's and the last's), and any the rules keep
    distinct."""
    rr = song.rules["refrain"]
    drawn = ("question",) if rr.get("question", "turn") == "draw" else ()
    return drawn + tuple(s for s in rr.get("distinct", ()) if s != "question")


def _allowed(song: _Song, slot: str) -> list[int]:
    """The options a refrain may take in a shared slot: for the question, all but the last's word, and but
    the first's where the first refrain has only one (where it draws among several, whichever it didn't
    ask are anyone's); for any other, all."""
    k = width(song.bank["refrain"]["slots"], slot)
    if slot != "question":
        return list(range(k))
    firsts = _firsts(song)
    return [v for v in range(k - 1) if len(firsts) > 1 or v not in firsts]


def _say(song: _Song, slot: str, v: int) -> str:
    """A refrain singing an option of a slot, for a sentence: 'asks who wrote', 'sings "who knows"'."""
    word = _label(_value(song.bank["refrain"]["slots"][slot], v)).replace("-", "")
    return f"asks who {word}" if slot == "question" else f'sings "{word}"'


def _ends(song: _Song, slot: str) -> str:
    slots = song.bank["refrain"]["slots"]
    first, last = (_label(_value(slots[slot], v)).replace("-", "") for v in (0, width(slots, slot) - 1))
    if len(_firsts(song)) > 1:
        return f"only the last refrain asks who {last}"
    return f"only the first refrain asks who {first}, and only the last who {last}"


def _round_words(song: _Song, heads: list[str], pick, chosen: Mapping | None = None,
                 now: Mapping | None = None) -> list[dict[str, int]]:
    """The option each refrain sings in each of its head's slots, by refrain (slot -> option), as the rules
    have them, in this order:

    - a slot its head fixes: the head's word;
    - the question the rules give a refrain (the first's and the last's, or each one's turn);
    - a slot kept once a song: one word in every refrain that sings it (a person's, else what the first of
      them sings now, else picked);
    - a shared slot (_shared): a word no other refrain sings while the words last, the words the rules or
      a head give aside (a person's, else what it sings now where no other does, else picked among those
      left);
    - any other: the refrain's own (a person's, else what it sings now, else picked).

    chosen: {refrain: {slot: option}}, a person's choices, each kept or refused in one sentence
    (ArrangeError). now: {refrain: {slot: option}}, what each sings now, kept wherever the rules allow.
    pick(refrain, slot, options) picks one of some options for the rest."""
    chosen, now = chosen or {}, now or {}
    rr = song.rules["refrain"]
    slots = song.bank["refrain"].get("slots", {})
    n = len(heads)
    names = [slot_names(song.heads[h]["lines"]) for h in heads]
    out: list[dict[str, int]] = [dict(song.fixed[h]) for h in heads]
    for i, words in chosen.items():
        for slot, v in words.items():
            if slot not in names[i]:
                raise ArrangeError(f"{_nth_refrain(i, n)} has no {slot} to choose")
            if slot in out[i] and v != out[i][slot]:
                raise ArrangeError(f"the {heads[i]} head sings its {slot} as "
                                   f"{_label(_value(slots[slot], out[i][slot])).replace('-', '')}")
    for i, h in enumerate(heads):  # what the first and last refrains sing for being first and last
        for slot, v in _ends_fixed(song, i, n, h).items():
            if slot not in names[i]:
                continue
            c = chosen.get(i, {}).get(slot)
            if c is not None and c != v:
                raise ArrangeError(_ends_say(song, i, n, slot, v))
            out[i][slot] = v
    for i, h in enumerate(heads):
        if "question" in names[i] and "question" not in out[i]:
            q = _question_rule(song, i, n, h)
            if q is not None:
                c = chosen.get(i, {}).get("question")
                if c is not None and c != q:
                    raise ArrangeError(f"{_nth_refrain(i, n)} {_say(song, 'question', q)}")
                out[i]["question"] = q
    if n and "question" in names[0] and "question" not in out[0]:  # the first refrain's, drawn among its own
        firsts = _firsts(song)
        c = chosen.get(0, {}).get("question")
        if c is not None and c not in firsts:
            raise ArrangeError(f"the first refrain {_firsts_say(song)}")
        asked = {w["question"] for w in out[1:] if "question" in w}  # what heads that fix it, and the last, ask
        fresh = [q for q in firsts if q not in asked] or firsts  # so it isn't asked twice where it can help it
        was = now.get(0, {}).get("question")
        out[0]["question"] = c if c is not None else was if was in fresh else pick(0, "question", fresh)
    for slot in [s for s in rr.get("once_per_song", ()) if s != "question"]:
        singers = [i for i in range(n) if slot in names[i] and slot not in out[i]]
        if not singers:
            continue
        picked = {chosen[i][slot] for i in singers if slot in chosen.get(i, {})}
        if len(picked) > 1:
            raise ArrangeError(f"the refrain's {slot} is sung once a song, the same in every refrain")
        v = next(iter(picked), None)
        if v is None:
            v = next((now[i][slot] for i in singers if now.get(i, {}).get(slot) is not None), None)
        if v is None:
            v = pick(singers[0], slot, list(range(width(slots, slot))))
        for i in singers:
            out[i][slot] = v
    for slot in _shared(song):
        singers = [i for i in range(n) if slot in names[i]]
        allowed = _allowed(song, slot)
        given = {i: out[i][slot] for i in singers if slot in out[i]}  # a head's own word, or the rules'
        free = [i for i in singers if i not in given]
        left = [v for v in allowed if v not in given.values()]
        room = len(free) <= len(left)  # every free refrain can sing a word of its own
        taken = dict(given)
        for i in free:
            c = chosen.get(i, {}).get(slot)
            if c is None:
                continue
            if c not in allowed:
                raise ArrangeError(_ends(song, slot))
            j = next((j for j, v in taken.items() if v == c), None)
            if j is not None and (room or j in given):
                raise ArrangeError(f"{_nth_refrain(j, n)} {_say(song, slot, c)} already")
            taken[i] = c
        for i in free:  # what each sings now, where no other does
            v = now.get(i, {}).get(slot)
            if i not in taken and v in allowed and v not in taken.values():
                taken[i] = v
        for i in free:
            if i in taken:
                continue
            unsung = [v for v in allowed if v not in taken.values()]
            v = now.get(i, {}).get(slot)
            if not unsung and v in allowed:  # every word is sung: it may keep its own, though another sings it too
                taken[i] = v
            else:
                taken[i] = pick(i, slot, unsung or left or allowed)
        for i, v in taken.items():
            out[i][slot] = v
    for i in range(n):
        for slot in names[i]:
            if slot in out[i]:
                continue
            k = width(slots, slot)
            v = chosen.get(i, {}).get(slot, now.get(i, {}).get(slot))
            out[i][slot] = v if v is not None and 0 <= v < k else pick(i, slot, list(range(k)))
    return out


def _round_words_problem(song: _Song, heads: list[str], words: list[dict[str, int]]) -> str | None:
    """Why the words some refrains sing in their heads' slots break the rules, in one plain sentence; None
    if they keep them (as _round_words gives them)."""
    rr = song.rules["refrain"]
    slots = song.bank["refrain"].get("slots", {})
    n = len(heads)
    for i, (h, w) in enumerate(zip(heads, words)):
        for slot, v in song.fixed[h].items():
            if w.get(slot) != v:
                return f"the {h} head sings its {slot} as {_label(_value(slots[slot], v)).replace('-', '')}"
        for slot, v in _ends_fixed(song, i, n, h).items():
            if slot in w and w[slot] != v:
                return _ends_say(song, i, n, slot, v)
        if "question" in w and "question" not in song.fixed[h]:
            q = _question_rule(song, i, n, h)
            if q is not None and w["question"] != q:
                return f"{_nth_refrain(i, n)} {_say(song, 'question', q)}"
            if q is None and i == 0 and w["question"] not in _firsts(song):
                return f"the first refrain {_firsts_say(song)}"
    for slot in [s for s in rr.get("once_per_song", ()) if s != "question"]:
        if len({w[slot] for w in words if slot in w}) > 1:
            return f"the refrain's {slot} is sung once a song, the same in every refrain"
    for slot in _shared(song):
        allowed = _allowed(song, slot)
        singers = [i for i in range(n) if slot in words[i]]
        given = {i: words[i][slot] for i in singers if slot in song.fixed[heads[i]]
                 or (slot == "question" and (_question_rule(song, i, n, heads[i]) is not None or i == 0))}
        free = [words[i][slot] for i in singers if i not in given]
        left = [v for v in allowed if v not in given.values()]
        if any(v not in allowed for v in free):
            return _ends(song, slot) if slot == "question" else f"the refrain's {slot} is sung as one of its words"
        if len(free) <= len(left) and (len(set(free)) < len(free) or set(free) & set(given.values())):
            return ("a question is asked twice while there are others left to ask" if slot == "question" else
                    f"the refrain's {slot} is sung the same twice while there are others left to sing")
        if len(free) > len(left) and not set(left or allowed) <= set(free):
            return f"the refrain's {slot} sings one of its words twice while another is left unsung"
    return None


def _refrains(song: _Song, n: int, seed: int,
              vocabulary: frozenset[str]) -> list[tuple[str, dict, tuple[str, ...], str | None]]:
    """Each refrain round: its head (the rules' first and last, now and then another between), the
    question it asks, the rest of its head's words drawn afresh each time round (but any the bank keeps
    once a song and any the head fixes), then a couplet, none twice, canon last."""
    rng = _rng(seed, _REFRAIN)
    spec, rr = song.bank["refrain"], song.rules["refrain"]
    slots = spec.get("slots", {})
    once = _pick([s for s in slot_names(spec["lines"]) if s in rr.get("once_per_song", ()) and s != "question"],
                 slots, rng, vocabulary)
    last = next(c for c in spec["couplets"] if c["id"] == rr["couplet_last"])
    others = [c for c in spec["couplets"] if c["id"] != last["id"]]
    order = _sample(rng, _affinity(others, song.words, vocabulary), n - 1)
    heads = _head_order(song, n, _rng(seed, _HEADS), vocabulary)
    streams = {"question": _rng(seed, _QUESTIONS)} | {s: _rng(seed, _DISTINCT) for s in rr.get("distinct", ())}

    def pick(i: int, slot: str, options: list[int]) -> int:
        return options[_draw(streams.get(slot, rng), _affinity(options, lambda o: _option_words(slots[slot], o),
                                                               vocabulary))]

    words = _round_words(song, heads, pick, now={i: dict(once) for i in range(n)})
    out = []
    for i, hid in enumerate(heads):
        head = song.heads[hid]
        picks = words[i]
        couplet = others[order[i]] if i < n - 1 else last
        cpicks = _pick(slot_names(couplet["lines"]), couplet.get("slots", {}), rng, vocabulary)
        lines = song.sing(head, picks) + song.sing(couplet, cpicks)
        out.append((couplet["id"], _chosen(head, picks) | _chosen(couplet, cpicks), lines,
                    None if hid == song.head_id else hid))
    return out


def _bridges(song: _Song, n: int, rng: np.random.Generator,
             vocabulary: frozenset[str]) -> list[tuple[str, dict, tuple[str, ...], None]]:
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
        out.append((stanza["id"], _chosen(stanza, picks), song.sing(stanza, picks), None))
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
    - refrains, one per refrain section, each with words of its own: its
      head (the first and last refrains sing the ones the rules give them;
      one between may sing another, each other head at most once a song),
      the question it asks (turning in order, or for H drawn: the first asks
      who made, wrote or sang it (the rules' question_first; one no head the
      song sings asks, where it can), the last who owns it, those between each
      something else; a lone refrain asks as a first does; a head that fixes
      its question asks that), the rest of its head's words drawn
      afresh each time round (any the rules keep once a song, the same every
      time; any its head fixes, as written), and a couplet each time, none
      twice, canon last;
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
    place; each refrain's couplet, head and words, and words for every
    refrain; the bridge's once-a-song words, the second bridge's stanza, the
    tag's syllable. Everything not
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
        verses.append((v.id, _chosen(v.entry, picks), song.sing(v.entry, picks), None))
    drawn = {
        "verse": iter(verses),
        "refrain": iter(_refrains(song, blocks["refrain"], int(seed), vocabulary)),
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
        head = None
        if block in drawn:
            key, slots, lines, head = next(drawn[block])
        elif block == "tag":
            key, slots = tag, {}
            lines = tuple(" ".join([tag] * len(genome.phrases[pid].sung)) + "." for pid in section.phrases)
        elif block in genome.fixed:
            key, slots = block, {}
            lines = tuple(turn(line, heard[block], rounds[block]) for line in genome.fixed[block])
            heard[block] += 1
        else:
            raise ArrangeError(f"the {name} section sings {block!r}, which neither the bank nor the genome has")
        sections.append(Sung(name, block, key, slots, tuple(lines), head))

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


# The words a lineage holds
#
# A rendition hands its words down, not its form: the verses it sang in order with their slot words, each
# refrain as it sang it (a round: its head, the words it sang in the head's slots, its couplet and the
# couplet's own slot words; the last always the canon's), the bridge's stanzas with their slot words, and the
# tag's syllable. As a dict, JSON as it stands:
#
#     {"verses": [{"id": "wire", "slots": {}}, {"id": "screen", "slots": {"many": "mil-lion"}}],
#      "refrain": {"rounds": [
#          {"head": "knows", "words": {"question": "made", "while": "when", "then": "it grows"}, "id": "true", "slots": {}},
#          {"head": "so", "words": {"question": "wrote", "while": "if"}, "id": "blue", "slots": {}},
#          {"head": "knows", "words": {"question": "owns", "while": "while", "then": "it goes"}, "id": "canon", "slots": {}}]},
#      "bridge": [{"id": "canon", "slots": {"place": "wa-ter", "ember": "coal", "where": "dark"}}],
#      "tag": "la"}
#
# Slot words are kept as sung (a coupled slot's by column), so a record reads plainly. A form with fewer
# refrains sings the first rounds and the last; a lone refrain asks what the first asks. Held words that
# give the refrains none of their own ({"slots": the once-a-song words, "couplets": each refrain's but the
# last's, "last": the canon's own slot words}, the question turning in order) are read as the rounds they
# sing (rounds()). sing() fits held words to a form, held_problem() says why it can't, and songbird.evolve
# changes them a little at a time down a lineage and over time.


def hold(genome: Genome, lyrics: Lyrics) -> dict:
    """What a rendition hands down of its words: everything it sang, but not its form."""
    song = _song(genome)
    sung = [s for s in lyrics.sections if s.lines]
    held = {
        "verses": [{"id": s.id, "slots": dict(s.slots)} for s in sung if s.block == "verse"],
        "refrain": {"rounds": [_round(song, s) for s in sung if s.block == "refrain"]},
        "bridge": [{"id": s.id, "slots": dict(s.slots)} for s in sung if s.block == "bridge"],
    }
    tag = next((s.id for s in sung if s.block == "tag"), None)
    if tag is not None:
        held["tag"] = tag
    return held


def _round(song: _Song, s: Sung) -> dict:
    """A sung refrain as held words keep it: its head, the words it sang in the head's slots, its couplet
    and the couplet's own words."""
    head = s.head or song.head_id
    names = set(slot_names(song.heads[head]["lines"])) if head in song.heads else set()
    return {"head": head, "words": {k: v for k, v in s.slots.items() if k in names},
            "id": s.id, "slots": {k: v for k, v in s.slots.items() if k not in names}}


def rounds(genome: Genome, held: dict) -> list[dict]:
    """The refrains some held words sing, one round each, the last the canon's (copies): as held, or, for
    held words that give the refrains none of their own, as those are sung: the once-a-song words in every
    refrain, a couplet for each but the last, the question turning in order."""
    refrain = held.get("refrain") or {}
    if "rounds" in refrain:
        return [{"head": r.get("head"), "words": dict(r.get("words") or {}), "id": r.get("id"),
                 "slots": dict(r.get("slots") or {})} for r in refrain["rounds"] or () if isinstance(r, dict)]
    song = _song(genome)
    spec = song.bank["refrain"].get("slots", {})
    asked = _options(spec["question"]) if "question" in spec else []
    k = len(asked)
    once = dict(refrain.get("slots") or {})
    couplets = list(refrain.get("couplets") or [])
    n = len(couplets) + 1
    out = [{"head": song.head_id, "words": once | ({"question": asked[_turned(i, n, k)]} if k else {}),
            "id": c.get("id"), "slots": dict(c.get("slots") or {})} for i, c in enumerate(couplets)]
    last = refrain.get("last") or {}
    out.append({"head": song.head_id, "words": once | ({"question": asked[_turned(n - 1, n, k)]} if k else {}),
                "id": last.get("id", song.rules["refrain"]["couplet_last"]), "slots": dict(last.get("slots") or {})})
    return out


def _placed(song: _Song, held_rounds: list[dict], n: int) -> list[dict]:
    """The rounds a form with n refrains sings: the first n - 1 and the last; a lone refrain asks what the
    rules have the first refrain ask."""
    if n == 0 or not held_rounds:
        return []
    out = [dict(r) for r in held_rounds[: n - 1]] + [dict(held_rounds[-1])]
    if n == 1:
        head = out[0].get("head") or song.head_id
        if head in song.heads and _asks(song, head) and "question" not in song.fixed[head]:
            asked = _options(song.bank["refrain"]["slots"]["question"])
            question = _question_rule(song, 0, 1, head)
            if question is None:
                # A first refrain can choose among several questions. When
                # shortening a song, keep the question its first refrain asked;
                # the last refrain supplies the canon couplet, not its question.
                firsts = _firsts(song)
                held = held_rounds[0].get("words", {}).get("question")
                question = next((i for i in firsts if asked[i] == held), firsts[0])
            out[0]["words"] = {**out[0].get("words", {}), "question": asked[question]}
    return out


def _nth_refrain(i: int, n: int) -> str:
    return "the first refrain" if i == 0 else "the last refrain" if i == n - 1 else f"refrain {i + 1}"


def _rounds_problem(song: _Song, placed: list[dict]) -> str | None:
    """Why some refrains, as a form sings them, break the bank's rules, in one plain sentence; None if
    they keep them."""
    spec, rr = song.bank["refrain"], song.rules["refrain"]
    couplets = {c["id"]: c for c in spec["couplets"]}
    last = rr["couplet_last"]
    n = len(placed)
    heads, words = [], []
    for i, r in enumerate(placed):
        where = _nth_refrain(i, n)
        head = r.get("head") or song.head_id
        if head not in song.heads:
            return f"the refrain has no head called {head!r}"
        want = _head_rule(song, i, n)
        if want is not None and head != want:
            return f"{where} sings the {want} head, not {head}"
        entry = song.heads[head]
        held = r.get("words") or {}
        stray = sorted(set(held) - set(slot_names(entry["lines"])))
        if stray:
            return f"{where}'s {head} head has no {_and(stray)} to sing"
        try:
            words.append(_held_picks(entry, held, where, first_if_missing=True))  # words from before a slot
        except ArrangeError as e:
            return str(e)
        heads.append(head)
        cid = r.get("id")
        if cid not in couplets:
            return f"the bank has no refrain couplet {cid!r}"
        if i < n - 1 and cid == last:
            return f"the {last} couplet is sung by the last refrain only"
        if i == n - 1 and cid != last:
            return f"the last refrain sings the {last} couplet, not {cid!r}"
        try:
            _held_picks(couplets[cid], r.get("slots") or {}, f"couplet {cid}")
        except ArrangeError as e:
            return str(e)
    ids = [r.get("id") for r in placed]
    if len(set(ids)) != len(ids):
        return "a refrain couplet is sung twice"
    if rr.get("head_repeat") is False:
        others = [h for h in heads if h != song.head_id]
        if len(set(others)) != len(others):
            return f"the {next(h for h in others if others.count(h) > 1)} head is sung twice"
    return _twins_problem(song, heads) or _round_words_problem(song, heads, words)


def _index(spec, value) -> int | None:
    """Which option of a slot some sung words are; None if none."""
    for i in range(width({"s": spec}, "s")):
        if _value(spec, i) == value:
            return i
    return None


# A person's choices, kept in their places

_PLACED = 16  # the streams the words drawn around a person's choices come from, apart from the draw's own
CHOSEN = ("verses", "couplets", "refrains", "refrain", "bridge", "bridge2", "tag")


def _options(spec) -> list:
    """A slot's options as written: its words, or a coupled slot's by column."""
    n = len(next(iter(spec.values()))) if isinstance(spec, dict) else len(spec)
    return [_value(spec, i) for i in range(n)]


def _label(value) -> str:
    """An option by its words as written (syllables hyphenated), a coupled slot by its noun (else its first
    column)."""
    if isinstance(value, dict):
        value = value.get("noun", next(iter(value.values())))
    return str(value)


def _option(spec, value) -> int | None:
    """Which option of a slot these words are: as written, or as they read (hyphens and case aside)."""
    for i, option in enumerate(_options(spec)):
        if option == value or (isinstance(value, str) and
                               _label(option).replace("-", "").lower() == value.replace("-", "").lower()):
            return i
    return None


def _held_picks(entry: dict, slots: dict, what: str, first_if_missing: bool = False) -> dict[str, int]:
    """The option index for each slot an entry sings, from the words held for it. first_if_missing: a slot
    the words don't name sings its first word (a refrain's words held by a record made without that slot, as
    the earliest records are without "this" song's: the bank lists the word they sing first)."""
    spec = entry.get("slots", {})
    picks = {}
    for name in slot_names(entry["lines"]):
        if first_if_missing and slots.get(name) is None:
            picks[name] = 0
            continue
        i = _index(spec[name], slots.get(name))
        if i is None:
            raise ArrangeError(f"{what}: {slots.get(name)!r} isn't one of the {name} slot's words")
        picks[name] = i
    return picks


def _shape_problem(held) -> str | None:
    """Why some held words aren't in the shape a record keeps them, in one plain sentence; None if they are."""
    def entries(value, keys):
        return isinstance(value, list) and all(isinstance(e, dict) and all(
            isinstance(e.get(k), t) or (k in ("slots", "words", "head") and e.get(k) is None) for k, t in keys.items())
            for e in value)

    if not isinstance(held, dict):
        return "held words are a record's words, not " + type(held).__name__
    refrain = held.get("refrain", {})
    shaped = (entries(held.get("verses", []), {"id": str, "slots": dict})
              and entries(held.get("bridge", []), {"id": str, "slots": dict})
              and isinstance(refrain, dict)
              and (entries(refrain["rounds"], {"id": str, "slots": dict, "words": dict, "head": str})
                   if "rounds" in refrain else
                   entries(refrain.get("couplets", []), {"id": str, "slots": dict})
                   and isinstance(refrain.get("slots", {}), dict) and isinstance(refrain.get("last", {}), dict))
              and isinstance(held.get("tag", ""), str))
    return None if shaped else "these held words aren't in the shape a record keeps them"


def held_counts(held: dict) -> dict[str, int]:
    """How many verses, refrains and bridge sections some held words can sing."""
    refrain = held.get("refrain", {})
    n = len(refrain["rounds"]) if "rounds" in refrain else len(refrain.get("couplets", ())) + 1
    return {"verse": len(held.get("verses", ())), "refrain": n, "bridge": len(held.get("bridge", ()))}


def held_problem(genome: Genome, form: Iterable[str], held: dict) -> str | None:
    """Why some held words can't be sung in a form within the bank's rules, in one plain sentence; None if
    they can. Words held for more verses or bridges than the form has sing the first of them; for more
    refrains, the first rounds and the last."""
    form = _form(form)
    try:
        song = _song(genome)
        blocks = _blocks(genome, form)
    except ArrangeError as e:
        return str(e)
    why = _problem(song.supported, blocks)
    if why:
        return why
    why = _shape_problem(held)
    if why:
        return why
    bank, rules = song.bank, song.rules
    have = held_counts(held)
    for block in ("verse", "bridge"):
        if blocks[block] > have[block]:
            return f"these words hold {have[block]} {block}{'s' if have[block] != 1 else ''}; the form sings {blocks[block]}"
    if blocks["refrain"] > have["refrain"]:
        return f"these words hold {have['refrain']} refrains; the form sings {blocks['refrain']}"
    why = verse_problem(genome, held.get("verses", ())[: blocks["verse"]])
    if why:
        return why
    why = _rounds_problem(song, _placed(song, rounds(genome, held), blocks["refrain"]))
    if why:
        return why
    stanzas = {b["id"]: b for b in bank.get("bridges", [])}
    for j, b in enumerate(held.get("bridge", ())[: blocks["bridge"]]):
        want = [rules["bridge"]["always"]] if j == 0 else list(rules["bridge"].get("extra", ()))
        if b.get("id") not in want:
            return f"bridge {j + 1} holds {b.get('id')!r}; it sings {' or '.join(want)}"
        try:
            _held_picks(stanzas[b["id"]], {**held["bridge"][0].get("slots", {}), **b.get("slots", {})},
                        f"bridge {b['id']}")
        except ArrangeError as e:
            return str(e)
    if blocks["tag"] and held.get("tag") not in bank["tag"]["syllables"]:
        return f"the tag holds {held.get('tag')!r}; it sings one of {', '.join(bank['tag']['syllables'])}"
    return None


def sing(genome: Genome, form: Iterable[str], held: dict) -> Lyrics:
    """Held words sung in a form: its verses in order, each refrain as its round holds it (the first rounds
    and the last, canon), the bridge's held stanzas and the tag's syllable, every slot as held. Raises
    ArrangeError when they can't be sung in that form within the rules (held_problem says why)."""
    form = _form(form)
    why = held_problem(genome, form, held)
    if why:
        raise ArrangeError(why)
    song = _song(genome)
    bank, rules = song.bank, song.rules
    by_id = {v.id: v.entry for v in song.verses}
    verses = iter(held.get("verses", ()))
    couplets = {c["id"]: c for c in bank["refrain"]["couplets"]}
    stanzas = {b["id"]: b for b in bank.get("bridges", [])}
    bridges = iter(held.get("bridge", ()))
    once: dict[str, int] = {}  # a bridge slot sung once a song keeps its word in a stanza after
    rounds_, heard = Counter(), Counter()
    for name in form:
        rounds_[genome.section(name).lyrics] += 1
    placed = iter(_placed(song, rounds(genome, held), rounds_["refrain"]))
    sections = []
    for name in form:
        section = genome.section(name)
        block = section.lyrics
        if not block:
            continue
        if block == "verse":
            v = next(verses)
            entry = by_id[v["id"]]
            picks = _held_picks(entry, v.get("slots", {}), f"verse {v['id']}")
            sections.append(Sung(name, block, v["id"], _chosen(entry, picks), song.sing(entry, picks)))
        elif block == "refrain":
            r = next(placed)
            head_id = r.get("head") or song.head_id
            head = song.heads[head_id]
            picks = _held_picks(head, r.get("words", {}), f"refrain {heard[block] + 1}", first_if_missing=True)
            entry = couplets[r["id"]]
            cpicks = _held_picks(entry, r.get("slots", {}), f"couplet {entry['id']}")
            lines = song.sing(head, picks) + song.sing(entry, cpicks)
            sections.append(Sung(name, block, entry["id"], _chosen(head, picks) | _chosen(entry, cpicks), lines,
                                 None if head_id == song.head_id else head_id))
        elif block == "bridge":
            b = next(bridges)
            stanza = stanzas[b["id"]]
            picks = {k: once[k] if k in once else _index(stanza["slots"][k], b.get("slots", {}).get(k))
                     for k in slot_names(stanza["lines"])}
            once.update({k: picks[k] for k in picks if k in rules["bridge"].get("once_per_song", ())})
            sections.append(Sung(name, block, stanza["id"], _chosen(stanza, picks), song.sing(stanza, picks)))
        elif block == "tag":
            tag = held["tag"]
            lines = tuple(" ".join([tag] * len(genome.phrases[pid].sung)) + "." for pid in section.phrases)
            sections.append(Sung(name, block, tag, {}, lines))
        elif block in genome.fixed:
            lines = tuple(turn(line, heard[block], rounds_[block]) for line in genome.fixed[block])
            sections.append(Sung(name, block, block, {}, lines))
        else:
            raise ArrangeError(f"the {name} section sings {block!r}, which neither the bank nor the genome has")
        heard[block] += 1
    return Lyrics(form, None, tuple(sections), held=True)


# What held words could become, one change at a time (for songbird.evolve, and a studio offering choices)


def bank_entry(genome: Genome, kind: str, entry_id: str) -> dict:
    """A bank entry by kind (verse, couplet, bridge, head) and id: a refrain's head with the slots it sings."""
    song = _song(genome)
    if kind == "head":
        return song.heads[entry_id]
    bank = song.bank
    entries = {"verse": bank["verses"], "couplet": bank["refrain"]["couplets"], "bridge": bank.get("bridges", [])}[kind]
    return next(e for e in entries if e["id"] == entry_id)


def slot_words(entry: dict) -> dict[str, list]:
    """Every slot a bank entry sings and the words each can take, as held words keep them."""
    spec = entry.get("slots", {})
    return {name: [_value(spec[name], i) for i in range(width(spec, name))] for name in slot_names(entry["lines"])}


def verse_ids(genome: Genome) -> tuple[str, ...]:
    return tuple(v.id for v in _song(genome).verses)


def verse_problem(genome: Genome, verses) -> str | None:
    """Why some held verses (in order, with their slot words) can't be sung together as they stand; None
    if they can: every verse the bank's, every slot word one of its slot's, and the verse rules kept."""
    song = _song(genome)
    by_id = {v.id: v for v in song.verses}
    for v in verses:
        if v.get("id") not in by_id:
            return f"the bank has no verse {v.get('id')!r}"
        try:
            _held_picks(by_id[v["id"]].entry, v.get("slots", {}), f"verse {v['id']}")
        except ArrangeError as e:
            return str(e)
    chosen = [by_id[v["id"]] for v in verses]
    if len({v.id for v in chosen}) != len(chosen):
        return "a verse is held twice"
    if chosen and not (song.checks.together(chosen) and song.checks.in_order(chosen)):
        return f"the verses {', '.join(v.id for v in chosen)} can't be sung together in that order"
    return None


def check(genome: Genome, form: Iterable[str], held: dict) -> list[str]:
    """Everything that keeps held words from being sung in a form within the rules ([] if nothing): what a
    person's edit is checked against, exactly as the drift's changes are."""
    why = held_problem(genome, form, held)
    return [why] if why else []


def verse_weights(genome: Genome, leanings: Leanings | None = None) -> dict[str, float]:
    """How likely each verse of the bank is to be drawn on its own, as arrange() weighs it with these leanings."""
    song = _song(genome)
    weights, _ = _verse_weights(song, leanings if leanings is not None else Leanings())
    return {v.id: float(w) for v, w in zip(song.verses, weights)}


def verse_order(genome: Genome, ids, keep=()) -> tuple[str, ...] | None:
    """An order the rules let these verses be sung in that keeps the verses named in `keep` in the order
    given there (the first such order); None if there is none."""
    song = _song(genome)
    by_id = {v.id: v for v in song.verses}
    ids = list(ids)
    if any(i not in by_id for i in ids) or len(set(ids)) != len(ids):
        return None
    rank = {vid: k for k, vid in enumerate(keep)}
    for order in song.checks.orders([by_id[i] for i in ids]):
        kept = [v.id for v in order if v.id in rank]
        if kept == sorted(kept, key=rank.get):
            return tuple(v.id for v in order)
    return None


def refrain_heads(genome: Genome) -> tuple[str, ...]:
    """The heads a refrain can sing, by id: the refrain's own lines first."""
    return tuple(_song(genome).heads)


def refrain_once(genome: Genome) -> tuple[str, ...]:
    """The refrain's slots the rules keep the same in every refrain (once a song); the others are each
    refrain's own."""
    rr = _song(genome).rules["refrain"]
    return tuple(s for s in rr.get("once_per_song", ()) if s != "question")


def head_repeats(genome: Genome) -> bool:
    """Whether another head may be sung more than once a song."""
    return _song(genome).rules["refrain"].get("head_repeat", True) is not False


def head_words(genome: Genome, head: str) -> dict[str, list]:
    """Every slot a refrain's head sings and the words each can take, as held words keep them: a word the
    head fixes is the only one its slot can take."""
    song = _song(genome)
    entry = song.heads[head]
    return {name: ([_value(entry["slots"][name], song.fixed[head][name])] if name in song.fixed[head] else words)
            for name, words in slot_words(entry).items()}


def refrain_place(genome: Genome, i: int, n: int, head: str | None = None) -> dict:
    """What the rules give the i-th of n refrains: "head", the head they give it (None: it may sing any),
    and for that head (or the one given), "question", the word it asks by rule or as its head fixes it
    (None: its own to ask, among free_questions())."""
    song = _song(genome)
    want = _head_rule(song, i, n)
    h = want or head or song.head_id
    question = None
    if h in song.heads and _asks(song, h):
        q = _question_rule(song, i, n, h)
        question = _value(song.bank["refrain"]["slots"]["question"], q) if q is not None else None
    return {"head": want, "question": question}


def head_fixed(genome: Genome, head: str) -> dict:
    """The words a refrain's head fixes, as written, by slot."""
    song = _song(genome)
    return {name: _value(song.heads[head]["slots"][name], at) for name, at in song.fixed[head].items()}


def refrain_words(genome: Genome, heads: list[str], held: list[dict], pick) -> list[dict]:
    """The words each of some refrains (their heads in order, a form's) sings in its head's slots, as the
    rules have them (_round_words): what's held kept wherever the rules allow, and pick(refrain, slot,
    words) choosing among some words as written for the rest. By refrain: slot -> words as written."""
    song = _song(genome)
    slots = song.bank["refrain"].get("slots", {})
    now = {}
    for i, h in enumerate(heads):
        spec = song.heads[h]["slots"]
        now[i] = {name: at for name, w in (held[i] if i < len(held) else {}).items()
                  if name in spec and (at := _index(spec[name], w)) is not None}

    def pick_option(i: int, slot: str, options: list[int]) -> int:
        words = [_value(slots[slot], o) for o in options]
        return options[words.index(pick(i, slot, words))]

    out = _round_words(song, heads, pick_option, now=now)
    return [{name: _value(slots[name], at) for name, at in w.items()} for w in out]


def shared_slots(genome: Genome) -> tuple[str, ...]:
    """The refrain's slots in which each refrain sings a word no other sings while the words last."""
    return _shared(_song(genome))


def free_questions(genome: Genome) -> tuple[str, ...]:
    """The words a refrain between the first and the last may ask where the rules leave it its own to ask:
    all but the first and the last."""
    song = _song(genome)
    spec = song.bank["refrain"].get("slots", {}).get("question")
    if spec is None or song.rules["refrain"].get("question", "turn") == "turn":
        return ()
    return tuple(_options(spec)[1:-1])


def couplet_ids(genome: Genome) -> tuple[str, ...]:
    """The couplets a refrain before the last may sing (all but the canon)."""
    song = _song(genome)
    last = song.rules["refrain"]["couplet_last"]
    return tuple(c["id"] for c in song.bank["refrain"]["couplets"] if c["id"] != last)


def last_couplet(genome: Genome) -> str:
    """The couplet the last refrain always sings (the canon)."""
    return _song(genome).rules["refrain"]["couplet_last"]


def bridge_ids(genome: Genome) -> tuple[str, tuple[str, ...]]:
    """The bridge stanza always sung first, and the extra stanzas a second bridge section may sing."""
    rules = _song(genome).rules["bridge"]
    return rules["always"], tuple(rules.get("extra", ()))


def tag_syllables(genome: Genome) -> tuple[str, ...]:
    return tuple(_song(genome).bank["tag"]["syllables"])


def affinity(genome: Genome, kind: str, ids, vocabulary) -> list[float]:
    """How much a person's words favour each of some bank entries (1 for none), as arrange() weighs them."""
    song = _song(genome)
    entries = [bank_entry(genome, kind, i) for i in ids]
    return _affinity(entries, song.words, frozenset(vocabulary or ()))


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
            raise ArrangeError(f"{what}'s {name} can be {_and([_label(o).replace('-', '') for o in _options(spec[name])])}, "
                               f"not {_label(value).replace('-', '')}")
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


def _refrain_pins_problem(song: _Song, pins: dict[int, dict], every: dict, n: int) -> None:
    """Raises ArrangeError, in one plain sentence, for a person's refrain choices the rules refuse whatever
    else is sung: a refrain the form hasn't, a couplet or head that can't go there or is chosen twice."""
    rr = song.rules["refrain"]
    couplets = {c["id"] for c in song.bank["refrain"]["couplets"]}
    last = rr["couplet_last"]
    for i, pin in sorted(pins.items()):
        if not 0 <= i < n:
            raise ArrangeError(f"this form sings {_number(n)} refrains, so it has no refrain {i + 1}")
        unknown = sorted(set(pin) - {"id", "head", "slots"})
        if unknown:
            raise ArrangeError(f"a refrain's choices are its couplet (id), its head and its slots, not {_and(unknown)}")
        cid, hid = pin.get("id"), pin.get("head")
        if cid is not None:
            if cid not in couplets:
                raise ArrangeError(f"the refrain has no couplet called {cid!r}")
            if i == n - 1 and cid != last:
                raise ArrangeError(f"the last refrain always sings the {last} couplet")
            if cid == last and i != n - 1:
                raise ArrangeError(f"the {last} couplet is the last refrain's, and only the last's")
        if hid is not None:
            if hid not in song.heads:
                raise ArrangeError(f"the refrain has no head called {hid!r}")
            want = _head_rule(song, i, n)
            if want is not None and hid != want:
                raise ArrangeError(f"{_nth_refrain(i, n)} always sings the {want} head")
    for key, what in (("id", "couplet"), ("head", "head")):
        picked = [p[key] for p in pins.values() if p.get(key) and not (key == "head" and p[key] == song.head_id)]
        twice = next((c for c in picked if picked.count(c) > 1), None)
        if twice and (key == "id" or rr.get("head_repeat") is False):
            raise ArrangeError(f"the {twice} {what} is chosen for two refrains, and it's sung once a song")
    twins = _twins_problem(song, [p["head"] for _i, p in sorted(pins.items()) if p.get("head")])
    if twins:
        raise ArrangeError(twins)
    if "question" in every:
        raise ArrangeError("each refrain asks its own question, so it's chosen refrain by refrain")
    own = sorted(set(every) & set(_shared(song)))
    if own:
        raise ArrangeError(f"each refrain sings its own {_and(own)}, so it's chosen refrain by refrain")


def _traded(song: _Song, ids: list[str], heads: list[str], pins: dict[int, dict]) -> None:
    """Each refrain's couplet and head as chosen, in place: a couplet (or another head) another refrain was
    singing moves there from a refrain whose own was chosen away, as a trade; failing that, the refrain
    takes the first couplet no refrain sings (or the song's own head)."""
    def trade(values: list, chosen: dict[int, str], repeats=lambda v: False) -> None:
        taken = set(chosen.values())
        freed = [values[i] for i in sorted(chosen) if values[i] not in taken and not repeats(values[i])]
        for i, v in chosen.items():
            values[i] = v
        for j in range(len(values)):
            if j not in chosen and values[j] in taken and not repeats(values[j]):
                values[j] = freed.pop(0) if freed else None

    trade(ids, {i: p["id"] for i, p in pins.items() if p.get("id")})
    spare = [c["id"] for c in song.bank["refrain"]["couplets"]
             if c["id"] not in ids and c["id"] != song.rules["refrain"]["couplet_last"]]
    for j, v in enumerate(ids):
        if v is None:
            ids[j] = spare.pop(0)
    once = song.rules["refrain"].get("head_repeat") is False
    trade(heads, {i: p["head"] for i, p in pins.items() if p.get("head")},
          lambda h: h == song.head_id or not once)
    for j, v in enumerate(heads):
        if v is None:
            heads[j] = song.head_id


def _keep_refrains(song: _Song, sections: list, places: list[int], pins: dict[int, dict], every: dict,
                   seed: int, vocabulary: frozenset[str]) -> None:
    """The refrains with a person's choices kept in their places (keep()), in sections, in place. Each
    refrain's words: its own choices, else the ones for every refrain, else as sung, else drawn, all as
    _round_words has the rules keep them."""
    spec = song.bank["refrain"]
    couplets = {c["id"]: c for c in spec["couplets"]}
    n = len(places)
    _refrain_pins_problem(song, pins, every, n)
    ids = [sections[k].id for k in places]
    heads = [sections[k].head or song.head_id for k in places]
    _traded(song, ids, heads, pins)
    # a head chosen where another refrain sings its twin (a head asking the same question as written): the
    # twin makes way for it and that refrain sings the song's own head
    pinned = {r for r, p in pins.items() if p.get("head")}
    for r in range(n):
        q = _asks_as_written(song, heads[r])
        if r not in pinned and q is not None and any(_asks_as_written(song, heads[k]) == q and heads[k] != heads[r]
                                                     for k in pinned):
            heads[r] = song.head_id

    chosen, theirs = {}, {}
    for r in range(n):
        head, couplet = song.heads[heads[r]], couplets[ids[r]]
        hnames, cnames = slot_names(head["lines"]), slot_names(couplet["lines"])
        own = dict((pins.get(r) or {}).get("slots") or {})
        stray = sorted(set(own) - set(hnames) - set(cnames))
        if stray:
            raise ArrangeError(f"{_nth_refrain(r, n)} has no {_and(stray)} to choose")
        mine = {name: w for name, w in every.items() if name in hnames and name not in song.fixed[heads[r]]}
        mine |= {name: w for name, w in own.items() if name in hnames}
        question = mine.pop("question", None)
        chosen[r] = _chosen_slots(head, mine, _nth_refrain(r, n))
        if question is not None:
            at = _option(spec["slots"]["question"], question)
            if at is None:
                raise ArrangeError(f"a refrain can ask who {_and([_label(o) for o in _options(spec['slots']['question'])])}, "
                                   f"not who {question}")
            chosen[r]["question"] = at
        theirs[r] = {name: w for name, w in own.items() if name in cnames and name not in hnames}
    stray = sorted(set(every) - {name for h in heads for name in slot_names(song.heads[h]["lines"])})
    if stray:
        raise ArrangeError(f"the refrain has no {_and(stray)} to choose")

    def pick(r: int, slot: str, options: list[int]) -> int:
        rng = _rng(seed, _PLACED + 32 + r) if slot in _shared(song) else _rng(seed, _PLACED + 8 + r)
        return options[_draw(rng, _affinity(options, lambda o: _option_words(spec["slots"][slot], o), vocabulary))]

    now = {r: _picks(song.heads[heads[r]], sections[k].slots) for r, k in enumerate(places)}
    words = _round_words(song, heads, pick, chosen, now)
    why = _twins_problem(song, heads) or _round_words_problem(song, heads, words)
    if why:  # choices that keep each rule alone but not all of them together (a word chosen twice too often)
        raise ArrangeError(why)
    for r, place in enumerate(places):
        s = sections[place]
        head, couplet = song.heads[heads[r]], couplets[ids[r]]
        picks = words[r]
        cpicks = (_picks(couplet, s.slots) if ids[r] == s.id else {}) | _chosen_slots(couplet, theirs[r], f"the {ids[r]} couplet")
        rest = [name for name in slot_names(couplet["lines"]) if name not in cpicks]
        if rest:
            cpicks |= _pick(rest, couplet.get("slots", {}), _rng(seed, _PLACED + 8 + r), vocabulary)
        sung = _chosen(head, picks) | _chosen(couplet, cpicks)
        sung_head = None if heads[r] == song.head_id else heads[r]
        if sung == s.slots and couplet["id"] == s.id and sung_head == s.head:
            continue
        sections[place] = Sung(s.section, "refrain", couplet["id"], sung,
                               song.sing(head, picks) + song.sing(couplet, cpicks), sung_head)


def keep(genome: Genome, lyrics: Lyrics, chosen: Mapping, leanings: Leanings | None = None) -> Lyrics:
    """Some drawn words with a person's choices kept in their places:

    - "verses": {place: {"id": verse, "slots": {slot: words}}} (or just the
      verse's id), by its place among the form's verses from 0. A chosen
      verse is sung there; the verses around it stay as drawn wherever the
      rules allow them beside it, and where they don't, as few as need to be
      are drawn again, by weight, until the rules hold. Its slots are the
      ones chosen, else as drawn if it was drawn there, else drawn.
    - "refrains": {place: {"id": couplet, "head": head, "slots": {slot:
      words}}}, any of the three, by refrain from 0: its couplet, never the
      canon but in the last refrain, which always sings it; its head, where
      the rules don't give it one (the first and last sing the refrain's
      own); its words, the head's (the question too, where the rules leave
      it the refrain's own to ask) and the couplet's. A couplet or another
      head that another refrain was singing trades places with the one it
      replaces; a question another refrain was asking is asked afresh there.
      "couplets": {place: couplet} is the same as {"id": couplet}.
    - "refrain": {slot: words}: words for every refrain whose head sings that
      slot (while, then), unless a refrain's own choice says otherwise. The
      question is each refrain's own and can't be chosen for all of them.
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
    pins: dict[int, dict] = {}
    for i, c in (chosen.get("couplets") or {}).items():
        pins.setdefault(int(i), {})["id"] = c
    for i, c in (chosen.get("refrains") or {}).items():
        pins.setdefault(int(i), {}).update(dict(c) if isinstance(c, Mapping) else {"id": c})
    every = dict(chosen.get("refrain") or {})
    if pins or every:
        _keep_refrains(song, sections, at["refrain"], pins, every, seed, vocabulary)

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


def _readable_lines(entry: dict, picks: Mapping | None = None) -> list[str]:
    """An entry's lines as they read with each slot's first option (or the option picked)."""
    names = slot_names(entry["lines"])
    chosen = {name: (picks or {}).get(name, 0) for name in names}
    return [_readable(line) for line in fill(entry["lines"], entry.get("slots", {}), chosen)]


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
            already = next((k for k, x in enumerate(current) if k != index and x is not None and x.id == v.id), None)
            why = f"the {v.id} verse is sung already, as verse {already + 1}" if already is not None \
                else song.checks.why(seq)
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
                "id": v.id, "lines": [_readable(x) for x in here.lines] if v.id == here.id else _readable_lines(v.entry),
                "mood": v.mood, "era": v.era, "rare": v.rare, "variant": v.variant, "allowed": why is None,
                "why": why, "elsewhere": elsewhere, "reorder": reorder})
        entry = by_id.get(here.id)
        out["words"] = _slot_choices(entry.entry, here.slots) if entry else []
    elif block == "refrain":
        spec, rr = song.bank["refrain"], song.rules["refrain"]
        last = rr["couplet_last"]
        others = {s.id: i for i, s in enumerate(sections)}
        n = len(sections)
        where = _nth_refrain(index, n)
        for c in spec["couplets"]:
            why = None
            if index == n - 1 and c["id"] != last:
                why = f"the last refrain always sings the {last} couplet"
            elif c["id"] == last and index != n - 1:
                why = f"the {last} couplet is the last refrain's, and only the last's"
            out["choices"].append({"id": c["id"], "lines": _readable_lines(c), "allowed": why is None, "why": why,
                                   "trades": others.get(c["id"]) if why is None and c["id"] != here.id else None})
        head = here.head or song.head_id
        want = _head_rule(song, index, n)
        sung_heads = [s.head or song.head_id for s in sections]
        out["head"] = head
        out["heads"] = []
        for hid, entry in song.heads.items():
            why = f"{where} always sings the {want} head" if want is not None and hid != want else None
            trades = None
            if why is None and hid != head and hid != song.head_id and hid in sung_heads:
                trades = sung_heads.index(hid)
            if why is None and hid != head and _asks_as_written(song, hid) is not None:
                # another refrain's head asks the same question as written: the two are never sung together
                twin = next((h for j, h in enumerate(sung_heads) if j != index and h != hid
                             and _asks_as_written(song, h) == _asks_as_written(song, hid)), None)
                if twin is not None:
                    why = _twins_problem(song, [twin, hid])
            out["heads"].append({"id": hid, "lines": _readable_lines(entry, song.fixed[hid]),
                                 "by": entry.get("by") if entry is not spec else None,
                                 "allowed": why is None, "why": why, "trades": trades})
        if want is not None:
            out["fixed"].append({"what": "head", "sung": want,
                                 "why": "the first and last refrains sing the song's own head, so the hook is heard "
                                        "first and last"})
        fixed = song.fixed.get(head, {})
        rule = _question_rule(song, index, n, head) if head in song.heads and _asks(song, head) else None
        ends = _ends_fixed(song, index, n, head) if head in song.heads else {}
        skip = set(fixed) | ({"question"} if rule is not None else set()) | set(ends)
        entry = song.heads.get(head, spec)
        words = _slot_choices(entry, here.slots, skip=skip)
        for slot, v in ends.items():
            if slot in here.slots:
                out["fixed"].append({"what": slot, "sung": _label(_value(spec["slots"][slot], v)),
                                     "why": f"the {'first' if index == 0 else 'last'} refrain sings it so, as the rules say"})
        heads_sung = [s.head or song.head_id for s in sections]
        for w in words:
            if w["slot"] in _shared(song):  # never a word the rules or a head give another refrain
                spec_ = spec["slots"][w["slot"]]
                given = {_index(spec_, s.slots.get(w["slot"])) for j, s in enumerate(sections) if j != index and (
                    w["slot"] in song.fixed.get(heads_sung[j], {})
                    or (w["slot"] == "question" and (_question_rule(song, j, n, heads_sung[j]) is not None or j == 0)))}
                allowed = _firsts(song) if w["slot"] == "question" and index == 0 else \
                    [v for v in _allowed(song, w["slot"]) if v not in given]  # the first asks among its own
                w["options"] = [_label(_value(spec_, v)) for v in allowed]
            if w["slot"] in rr.get("once_per_song", ()):
                w["once"] = True  # chosen once for every refrain
        couplet = next((c for c in spec["couplets"] if c["id"] == here.id), None)
        if couplet is not None:
            words += [dict(w, part="couplet") for w in _slot_choices(couplet, here.slots)]
        out["words"] = words
        question = here.slots.get("question")
        if question is not None and rule is not None:
            why = (f"the {head} head asks it as written" if "question" in fixed else
                   "the question turns each time the refrain comes round, and the last refrain asks who owns it"
                   if rr.get("question", "turn") == "turn" else
                   f"the first refrain {_firsts_say(song)}, and the last who owns it" if index in (0, n - 1) else "")
            out["fixed"].append({"what": "question", "sung": _label(question), "why": why})
        for name, at in fixed.items():
            if name != "question":
                out["fixed"].append({"what": name, "sung": _label(_value(entry["slots"][name], at)),
                                     "why": f"the {head} head sings it as written"})
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
