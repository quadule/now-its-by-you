"""The lyric bank: every verse, refrain couplet, bridge and tag syllable a song
can draw on, with named slots for the words that swap and the rules for
combining them. It lives under "bank" in the genome JSON. The seed's own
refrain, bridge, tag and seed_verses stay as they are; the bank is what a
procedural arrangement draws from, and songs/<song>-bank.md is the same bank
for reading.

A slot is written {name} in a line, or {name.column} for a coupled slot whose
columns are chosen together: a noun and its pronouns, say. A slot is chosen
once per block, so a name used twice in a verse agrees with itself. Options
are written syllabified like any lyric, and check() makes sure every way a
line can be sung fits its phrase's notes and can be pronounced.

A refrain's head (its lines before the couplet) may be sung other ways: each
of its "heads" is another set of lines on the same phrases, singing the
refrain's own slots by name, and fixing any it wants sung as written.

A line's focus word, the one the singer leans on, is marked *word* (whole
word, hyphens inside are fine: *num-bers*, punctuation outside: *heart*.);
the marks don't count as syllables and the singer, not the bank, reads them.

    python -m songbird.bank songs/h-now-its-by-you.json
"""

from __future__ import annotations

import itertools
import re
import sys
from collections import Counter

from . import phonetics
from .genome import Genome, load, syllables, turns

_SLOT = re.compile(r"\{([a-z_]+)(?:\.([a-z_]+))?\}")
_TURN = re.compile(r"\{([^{}]*)\}")

MOODS = ("plain", "light", "dark", "tender")
RARITIES = ("common", "rare")


def unmarked(line: str) -> str:
    """The line without its focus marks."""
    return line.replace("*", "")


def check_marks(line: str, what: str) -> None:
    """Every focus mark wraps one whole word: *word*, punctuation outside."""
    for token in line.split():
        if "*" not in token:
            continue
        core = token.strip(".,;:!?\"")
        if not (core.startswith("*") and core.endswith("*") and core.count("*") == 2 and len(core) > 2):
            raise ValueError(f"{what}: a focus mark must wrap a whole word, *word*, not {token!r} in {line!r}")


def slot_names(lines) -> list[str]:
    """The slots the lines use, in order of first appearance."""
    seen: list[str] = []
    for line in lines:
        for name, _ in _SLOT.findall(line):
            if name not in seen:
                seen.append(name)
    return seen


def width(slots: dict, name: str) -> int:
    """How many options a slot has; a coupled slot's columns must agree."""
    spec = slots[name]
    if isinstance(spec, dict):
        lengths = {len(column) for column in spec.values()}
        if len(lengths) != 1:
            raise ValueError(f"slot {name!r}: its columns have different lengths")
        return lengths.pop()
    return len(spec)


def fill(lines, slots: dict, choice: dict[str, int]) -> list[str]:
    """The lines with every slot filled by its chosen option."""

    def one(match: re.Match) -> str:
        name, column = match.groups()
        if name not in slots:
            raise ValueError(f"line uses slot {{{name}}}, which the block doesn't define")
        spec = slots[name]
        if isinstance(spec, dict):
            if not column or column not in spec:
                raise ValueError(f"slot {name!r} is coupled; write {{{name}.<column>}} with one of {sorted(spec)}")
            return spec[column][choice[name]]
        if column:
            raise ValueError(f"slot {name!r} has no columns; write {{{name}}}")
        return spec[choice[name]]

    return [_SLOT.sub(one, line) for line in lines]


def expansions(lines, slots: dict):
    """Every way the lines can be sung: one choice per slot, all combinations."""
    names = slot_names(lines)
    for name in names:
        if name not in slots:
            raise ValueError(f"line uses slot {{{name}}}, which the block doesn't define")
    for combo in itertools.product(*(range(width(slots, n)) for n in names)):
        yield fill(lines, slots, dict(zip(names, combo)))


def ways(lines, slots: dict) -> int:
    """How many ways the lines can be sung."""
    total = 1
    for name in slot_names(lines):
        total *= width(slots, name)
    return total


def head_slots(head: dict, shared: dict, what: str = "a refrain head") -> dict:
    """The slots one of a refrain's other heads sings: the refrain's own slots, by name, each held to its
    one word where the head fixes it (a head sings the words it fixes as written)."""
    names = slot_names(head["lines"])
    fixed = head.get("fixed", {})
    unknown = sorted(set(names) - set(shared))
    if unknown:
        raise ValueError(f"{what}: the refrain has no slots {unknown}")
    stray = sorted(set(fixed) - set(names))
    if stray:
        raise ValueError(f"{what}: fixes {stray}, which its lines don't sing")
    out = {}
    for name in names:
        spec = shared[name]
        if name not in fixed:
            out[name] = spec
            continue
        options = [{c: col[i] for c, col in spec.items()} if isinstance(spec, dict) else spec[i]
                   for i in range(width(shared, name))]
        if fixed[name] not in options:
            raise ValueError(f"{what}: {fixed[name]!r} isn't one of the {name} slot's words")
        i = options.index(fixed[name])
        out[name] = {c: [col[i]] for c, col in spec.items()} if isinstance(spec, dict) else [spec[i]]
    return out


def head_ids(refrain: dict) -> list[str]:
    """The refrain's heads by id: its own lines first, then its other heads."""
    return [refrain.get("id", "refrain")] + [h["id"] for h in refrain.get("heads", [])]


def refrain_rules_problem(refrain: dict, rr: dict) -> str | None:
    """Why a refrain's words and rules can't be kept together, in one plain sentence; None if they can: a
    slot the rules keep distinct in each refrain is one the refrain's own lines sing, other than the
    question, and isn't also kept once a song; no head fixes a slot kept once a song; and a head that asks
    its own question is sung at most once a song (head_repeat false), so no two refrains ask it."""
    own = set(slot_names(refrain["lines"])) - {"question"}
    once = set(rr.get("once_per_song", ())) - {"question"}
    distinct = set(rr.get("distinct", ()))
    if distinct - own or distinct & once:
        return ("the refrain's distinct slots must be ones its own lines sing, other than the question, and not "
                f"kept once a song: not {', '.join(sorted((distinct - own) | (distinct & once)))}")
    for head in refrain.get("heads", []):
        fixed = set(head.get("fixed", {}))
        if fixed & once:
            return f"the {head['id']} head fixes {', '.join(sorted(fixed & once))}, which the rules keep once a song"
        if "question" in fixed and rr.get("head_repeat", True) is not False:
            return f"the {head['id']} head asks its own question, so it can be sung only once a song (head_repeat false)"
    return None


def check_block(lines, slots: dict, phrase_ids, phrases: dict, lexicon: dict | None, what: str) -> None:
    """Every way the lines can be sung fits its phrase and can be pronounced."""
    if len(lines) != len(phrase_ids):
        raise ValueError(f"{what}: {len(lines)} lines for {len(phrase_ids)} phrases")
    unused = set(slots) - set(slot_names(lines))
    if unused:
        raise ValueError(f"{what}: slots {sorted(unused)} are never used")
    for sung in expansions(lines, slots):
        for line, pid in zip(sung, phrase_ids):
            check_marks(line, what)
            want, got = len(phrases[pid].sung), len(syllables(line))
            if want != got:
                raise ValueError(f"{what}: {line!r} has {got} syllables, phrase {pid} has {want} notes")
            for word in line.split():
                n = len([p for p in word.split("-") if p])
                try:
                    singable = len(phonetics.fit(word, n, lexicon)) == n
                except KeyError:
                    singable = False
                if not singable:
                    raise ValueError(f"{what}: can't sing {word!r} as {n} syllables in {line!r}")


def check(genome: Genome) -> dict:
    """Validate the genome's bank against its tune and dictionary; a summary comes back."""
    bank = genome.source.get("bank")
    if not bank:
        raise ValueError("the genome has no bank")
    blocks = {s.lyrics: s for s in genome.sections.values() if s.lyrics}
    lexicon = genome.lexicon or None
    rules = bank.get("rules") or {}
    for key in ("verses", "refrain", "bridge", "tag"):
        if key not in rules:
            raise ValueError(f"bank rules say nothing about the {key}")

    verses = bank.get("verses", [])
    ids = [v["id"] for v in verses]
    if len(set(ids)) != len(ids):
        raise ValueError(f"verse ids repeat: {[i for i, n in Counter(ids).items() if n > 1]}")
    total_ways = 0
    for v in verses:
        what = f"verse {v['id']}"
        if v.get("mood") not in MOODS:
            raise ValueError(f"{what}: mood must be one of {MOODS}")
        if v.get("rarity") not in RARITIES:
            raise ValueError(f"{what}: rarity must be one of {RARITIES}")
        if not (v.get("era") is None or isinstance(v["era"], int)):
            raise ValueError(f"{what}: era is a year or null")
        if not v.get("scheme"):
            raise ValueError(f"{what}: no rhyme scheme")
        for other in v.get("pairs_with", []):
            if other not in ids:
                raise ValueError(f"{what} pairs with {other!r}, which the bank doesn't have")
            if v["id"] not in next(o for o in verses if o["id"] == other).get("pairs_with", []):
                raise ValueError(f"{what} pairs with {other!r}, but not the other way round")
        check_block(v["lines"], v.get("slots", {}), blocks["verse"].phrases, genome.phrases, lexicon, what)
        total_ways += ways(v["lines"], v.get("slots", {}))

    refrain = bank["refrain"]
    r_phrases = blocks["refrain"].phrases
    head = refrain["lines"]
    check_block(head, refrain.get("slots", {}), r_phrases[: len(head)], genome.phrases, lexicon, "refrain")
    turning = _TURN.search(genome.refrain[0])
    fixed_question = [unmarked(o) for o in turning.group(1).split("|")] if turning else []
    if refrain.get("slots", {}).get("question") != fixed_question:
        raise ValueError("the bank's question words differ from the fixed refrain's turning line")
    heads = head_ids(refrain)
    if len(set(heads)) != len(heads):
        raise ValueError(f"refrain head ids repeat: {[i for i, n in Counter(heads).items() if n > 1]}")
    for h in refrain.get("heads", []):
        what = f"refrain head {h['id']}"
        if len(h["lines"]) != len(head):
            raise ValueError(f"{what}: {len(h['lines'])} lines where the refrain's head has {len(head)}")
        check_block(h["lines"], head_slots(h, refrain.get("slots", {}), what), r_phrases[: len(head)],
                    genome.phrases, lexicon, what)
    for rule in ("head_first", "head_last"):
        if rule in rules["refrain"] and rules["refrain"][rule] not in heads:
            raise ValueError(f"rules name a {rule.replace('_', ' ')} the bank doesn't have")
    why = refrain_rules_problem(refrain, rules["refrain"])
    if why:
        raise ValueError(why)
    couplet_ids = [c["id"] for c in refrain["couplets"]]
    for c in refrain["couplets"]:
        check_block(c["lines"], c.get("slots", {}), r_phrases[len(head):], genome.phrases, lexicon, f"couplet {c['id']}")
    if rules["refrain"].get("couplet_last") not in couplet_ids:
        raise ValueError("rules name a last couplet the bank doesn't have")

    bridge_ids = [b["id"] for b in bank.get("bridges", [])]
    for b in bank.get("bridges", []):
        check_block(b["lines"], b.get("slots", {}), blocks["bridge"].phrases, genome.phrases, lexicon, f"bridge {b['id']}")
    for named in [rules["bridge"].get("always")] + list(rules["bridge"].get("extra", [])):
        if named not in bridge_ids:
            raise ValueError(f"rules name bridge {named!r}, which the bank doesn't have")

    # the seed's own lines carry focus marks too; they must be well formed
    seed_lines = [(f"seed verse {i + 1}", l) for i, v in enumerate(genome.seed_verses) for l in v]
    seed_lines += [(name, sung) for name, block in genome.fixed.items() for line in block for sung in turns(line)]
    for what, line in seed_lines:
        check_marks(line, what)

    for syllable in bank["tag"]["syllables"]:
        try:
            singable = len(phonetics.fit(syllable, 1, lexicon)) == 1
        except KeyError:
            singable = False
        if not singable:
            raise ValueError(f"tag: can't sing {syllable!r} as one syllable")

    return {
        "verses": len(verses),
        "verse_ways": total_ways,
        "by_mood": dict(Counter(v["mood"] for v in verses)),
        "rare": sum(v["rarity"] == "rare" for v in verses),
        "variants": sum(v["scheme"] != "AABB" or v.get("enjambed", False) for v in verses),
        "dated": sum(v.get("era") is not None for v in verses),
        "refrain_heads": len(heads),
        "couplets": len(couplet_ids),
        "bridges": len(bridge_ids),
        "tag_syllables": len(bank["tag"]["syllables"]),
        "seed_lines_with_a_focus": sum("*" in line for _, line in seed_lines),
    }


def main(argv: list[str] | None = None) -> int:
    paths = argv if argv is not None else sys.argv[1:]
    if not paths:
        print(__doc__)
        return 2
    for path in paths:
        summary = check(load(path))
        print(f"{path}: ok")
        for key, value in summary.items():
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
