"""How the singer says a song's words, and which it may stress wrongly (dev-only).

    uv run python tools/pronounce.py                        # every word H can sing that may be stressed wrongly
    uv run python tools/pronounce.py no-bo-dy per-fect      # how the singer says these now
    uv run python tools/pronounce.py --song songs/b-....json
    uv run python tools/pronounce.py --heteronyms            # its own lines with a word said two ways, sung
                                                             # as the rules for a person's line wouldn't
    uv run python tools/pronounce.py "bass{fish}"            # a word with a say (songbird/heteronyms.py)

The singer reads each word from the song's own lexicon ("lexicon" in its genome: the word without
hyphens, then ARPAbet with a stress digit on every vowel), else the CMU dictionary, taking the first
reading with as many vowels as the word has notes (songbird/phonetics.py fit). A vowel marked 1 or 2 is
sung stressed: leaned on a little (voice.lean), and an AH not reduced to a schwa. So a word goes wrong
two ways: the dictionary gives it secondary stresses where English has none (no-bo-dy came out
NO-BO-DY), or reads it two ways and the first is the wrong one (per-fect as the verb, per-FECT).
Compounds keep their second stress (church-yard, rail-way): only the lists below are suspects.

A line a person writes in the studio is read differently: a word said two ways (bass, wind, live,
read...) is said as the words beside it say, and a word with a say in braces (bass{fish}, bass{base},
bass{B.EY1.S}) as its say tells (songbird/heteronyms.py). The song's own lines aren't (a say in one
is the song's, the wind{air}): --heteronyms lists those the rules would say another way.

To fix a word, give the song its own reading, stressing only what English does:
"nobody": "N OW1 B AA0 D IY0". Then check the words are still heard (tools/wer_suite.py --sketch h
--seeds 6), and build the site again (tools/sing_site.py; docs/SING-ONLINE.md says why that's safe
while people sing).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from songbird import phonetics as ph  # noqa: E402

H = ROOT / "songs" / "h-now-its-by-you.json"


def vowels(reading: list[str]) -> list[str]:
    return [p for p in reading if p.rstrip("012") in ph.VOWELS]


def said(word: str, lexicon: dict | None) -> str:
    """The word as the singer says it: its syllables, the stressed ones in capitals, and where the
    reading came from."""
    n = len([p for p in ph.shown(word).split("-") if p]) or 1
    syllables = ph.fit(word, n, lexicon)
    parts = [p for p in ph.shown(word).split("-") if p] if len(syllables) == n else [s.nucleus for s in syllables]
    shown = "-".join(p.upper() if s.stressed else p.lower() for p, s in zip(parts, syllables))
    own = lexicon and ph.clean(word.replace("-", "")) in {ph.clean(k.replace("-", "")) for k in lexicon}
    reading = " ".join(ph.pronunciations(word, lexicon)[0])
    return f"{shown:22s} {reading:30s} {'its say' if '{' in word else 'the song' if own else 'the dictionary'}"


def words(genome) -> dict[str, set[str]]:
    """Every word the song can sing (its seed verses and phrases, and every way the bank's lines can be
    sung), and where."""
    from songbird.bank import unmarked

    where: dict[str, set[str]] = defaultdict(set)
    for what, line in sung_lines(genome):
        for w in unmarked(line).split():
            w = w.strip('.,;:!?"()—“”').lower()
            if re.search(r"[a-z]", w):
                where[w].add(what)
    return where


def heteronyms(genome) -> list[tuple[str, str, str, str | None, str]]:
    """The song's own lines with a word said two ways that the rules for a person's line would say another
    way (songbird/heteronyms.py): (where, line, word, as the song sings it, as the rules would)."""
    from songbird import heteronyms as het

    out, seen = [], set()
    for what, line in sung_lines(genome):
        for c in het.as_sung(line, genome.lexicon, authored=False):
            rules = next(x for x in het.choices(line) if x["index"] == c["index"])["chosen"]
            if rules != c["chosen"] and (line, c["index"]) not in seen:
                seen.add((line, c["index"]))
                out.append((what, line, c["word"], c["chosen"], rules))
    return out


def sung_lines(genome) -> list[tuple[str, str]]:
    """Every line the song can sing, and where: its seed verses and phrases, and every way the bank's lines
    can be sung."""
    from songbird.bank import expansions, head_slots

    lines = []
    bank = genome.source.get("bank") or {}
    for v in bank.get("verses", []):
        lines += [(f"verse {v['id']}", line) for sung in expansions(v["lines"], v.get("slots", {})) for line in sung]
    r = bank.get("refrain")
    if r:
        lines += [("refrain", line) for sung in expansions(r["lines"], r.get("slots", {})) for line in sung]
        for h in r.get("heads", []):
            lines += [(f"head {h['id']}", line) for sung in expansions(h["lines"], head_slots(h, r.get("slots", {})))
                      for line in sung]
        for c in r.get("couplets", []):
            lines += [(f"couplet {c['id']}", line) for sung in expansions(c["lines"], c.get("slots", {})) for line in sung]
    for b in bank.get("bridges", []):
        lines += [(f"bridge {b['id']}", line) for sung in expansions(b["lines"], b.get("slots", {})) for line in sung]
    for i, v in enumerate(genome.seed_verses):
        lines += [(f"seed verse {i + 1}", line) for line in v]
    for name, block in genome.fixed.items():
        lines += [(name, line) for line in block]
    for name, section in genome.sections.items():
        for pid in section.phrases:
            if getattr(genome.phrases[pid], "lyric", None):
                lines.append((f"{name} {pid}", genome.phrases[pid].lyric))
    return lines


def suspects(genome) -> tuple[list[str], list[str]]:
    """Words the song can sing that the singer may stress wrongly, the song's own readings aside: those
    given more than one stressed syllable by a secondary stress, and those the dictionary reads with the
    stress in more than one place."""
    lexicon = genome.lexicon or {}
    own = {ph.clean(k.replace("-", "")) for k in lexicon}
    several, two_ways = [], []
    for w in sorted(words(genome)):
        n = len([p for p in w.split("-") if p])
        if n < 2 or ph.clean(w.replace("-", "")) in own:
            continue
        exact = [r for r in ph.pronunciations(w, None) if len(vowels(r)) == n]
        if not exact:
            continue
        marks = [v[-1] for v in vowels(exact[0])]
        if sum(m in "12" for m in marks) > 1 and "2" in marks:
            several.append(w)
        if len({tuple(i for i, v in enumerate(vowels(r)) if v.endswith("1")) for r in exact}) > 1:
            two_ways.append(w)
    return several, two_ways


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("words", nargs="*", help="words as the lyrics hyphenate them (no-bo-dy); none: the suspects")
    ap.add_argument("--song", default=str(H), help="the genome (default H)")
    ap.add_argument("--heteronyms", action="store_true",
                    help="the song's own lines with a word said two ways the rules for a person's line would say "
                         "another way (songbird/heteronyms.py)")
    args = ap.parse_args()

    from songbird import genome as G

    genome = G.load(args.song)
    if args.heteronyms:
        found = heteronyms(genome)
        print(f"{len(found)} of the song's own lines sing a word said two ways as the rules wouldn't "
              "(the song's way is kept: a say in braces changes it, bass{fish}):")
        for what, line, word, song, rules in found:
            print(f"  {word:8s} sung {song or 'neither sense'}, the rules: {rules}   {what}: {line}")
        return
    if args.words:
        for w in args.words:
            print(f"{w:18s} {said(w, genome.lexicon)}")
        return
    where = words(genome)
    several, two_ways = suspects(genome)
    print(f"{len(where)} words; the song says {len(genome.lexicon or {})} its own way.\n")
    print("More than one stressed syllable (a compound's second stress is right; a word's often isn't):")
    for w in several:
        print(f"  {w:18s} {said(w, genome.lexicon)}  {', '.join(sorted(where[w])[:3])}")
    print("\nRead with the stress in more than one place (the first is sung):")
    for w in two_ways:
        readings = " | ".join(" ".join(r) for r in ph.pronunciations(w, None))
        print(f"  {w:18s} {readings:48s} {', '.join(sorted(where[w])[:3])}")


if __name__ == "__main__":
    main()
