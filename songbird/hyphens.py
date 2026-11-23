"""Where a word's sung syllables fall, as a person would hyphenate it: "father" is fa-ther, "evening" eve-ning.

A person writing their own lines writes words; the singer sings one syllable a note, and a line's syllables are
its words split at hyphens (genome.syllables). So a word written whole is split here: into as many syllables as the
pronouncing dictionary says (songbird.phonetics), at the places its spelling suggests. A word a person hyphenated
stays as they wrote it, and so does a word said their own way (bass{base}).

A word the dictionary reads more than one way ("every", "evening", "fire") takes the count that fits the line's
notes, if one does (line()).
"""

from __future__ import annotations

import re
from itertools import pairwise

from . import phonetics

VOWEL = "aeiouy"
# consonant pairs that begin a syllable together: a-sleep, ma-chine, fa-ther
ONSETS = {"bl", "br", "ch", "cl", "cr", "dr", "fl", "fr", "gl", "gr", "ph", "pl", "pr", "sc", "sh", "sk", "sl", "sm",
          "sn", "sp", "st", "sw", "th", "tr", "tw", "wh", "wr", "qu", "kn", "gh"}
# pairs that end the syllable before: flick-er, laugh-ing
CODAS = {"ck", "gh"}
# a short vowel, stressed, keeps the consonant after it: ev-er, sev-en, cop-y (but o-ver, ba-by)
SHORT = {"IH1", "EH1", "AE1", "AA1", "AH1", "UH1"}
# the second half of a word made of two (some-one, news-pa-pers), whose first half is a word too
TAILS = ("one", "body", "thing", "where", "side", "self", "selves", "time", "times", "day", "days", "way", "ways",
         "light", "night", "land", "out", "how", "more", "ever", "paper", "papers", "parents", "father", "mother",
         "man", "men", "wood", "ward", "wards", "song", "songs", "bird", "birds", "home", "town", "less", "ness")
SUFFIXES = ("ing", "ed", "es")
_WORD = re.compile(r"^([^A-Za-z']*)([A-Za-z][A-Za-z']*?)([^A-Za-z']*)$")


def counts(word: str) -> list[int]:
    """How many syllables the dictionary sings a word in, each reading's (the most usual first); by its spelling
    where the dictionary hasn't the word."""
    readings = phonetics.pronunciations(word)
    found = list(dict.fromkeys(phonetics._vowel_count(r) for r in readings if phonetics._vowel_count(r)))
    return found or [max(1, len(_groups(word.lower())))]


def _groups(w: str) -> list[tuple[int, int]]:
    """The spelling's vowel groups, (start, end), a final silent e left out (stone, but not the): 'y' is a vowel
    but at a word's start, and the u of 'qu' isn't one."""
    out, i = [], 0
    while i < len(w):
        c = w[i]
        vowel = c in VOWEL and not (c == "y" and i == 0) and not (c == "u" and i > 0 and w[i - 1] == "q")
        if vowel:
            j = i
            while j + 1 < len(w) and w[j + 1] in VOWEL and not (w[j + 1] == "y" and j + 2 < len(w) and w[j + 2] in VOWEL):
                j += 1
            out.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    if len(out) > 1 and out[-1] == (len(w) - 1, len(w)) and w[-1] == "e" and not w.endswith(("le", "ee", "ye")):
        out.pop()  # a silent e: stone, alone
    elif len(out) > 1 and w.endswith("es") and out[-1] == (len(w) - 2, len(w) - 1) and w[-3:-2] not in ("s", "x", "z", "h", "c", "g", "l"):
        out.pop()  # stones, but not kisses or faces
    elif len(out) > 1 and w.endswith("ed") and out[-1] == (len(w) - 2, len(w) - 1) and w[-3:-2] not in ("t", "d"):
        out.pop()  # hummed, but not wanted
    return out


def _cut(cluster: str) -> int:
    """Where a run of consonants between two vowels is split: how many go with the syllable before."""
    if len(cluster) <= 1:
        return 1 if cluster == "x" else 0  # ta-ble, but tax-i
    if cluster[:2] in CODAS and (len(cluster) == 2 or cluster[2:] in ONSETS or len(cluster) == 3):
        return 2
    if cluster[-2:] in ONSETS and len(cluster) >= 3:
        return len(cluster) - 2  # mon-ster? no: con-trol, chil-dren
    if cluster in ONSETS:
        return 0  # fa-ther, a-sleep
    return len(cluster) - 1  # let-ter, win-dow, num-bers


def _vowels(w: str, n: int) -> list[str]:
    """The vowel sounds of the dictionary's reading of w in n syllables, if it has one."""
    for reading in phonetics.pronunciations(w):
        vowels = [p for p in reading if p.rstrip("012") in phonetics.VOWELS]
        if len(vowels) == n:
            return vowels
    return []


def _suffixed(w: str, n: int) -> list[str] | None:
    """A word that is a dictionary word and a sung ending, the ending its own syllable: mak-ing, fold-ed,
    pass-es, hop-ping."""
    d = phonetics._dictionary()
    for suffix in SUFFIXES:
        if not w.endswith(suffix) or len(w) <= len(suffix) + 1:
            continue
        base = w[: -len(suffix)]
        if suffix == "ed" and base[-1] not in "td":
            continue
        if suffix == "es" and not base.endswith(("s", "x", "z", "ch", "sh", "c", "g")):
            continue
        stems = [(base, base), (base + "e", base)]
        if len(base) > 2 and base[-1] == base[-2] and base[-1] not in "sl":
            stems.insert(0, (base[:-1], base[:-1]))  # hop-ping, hum-ming: the doubled letter begins the ending
        if base.endswith("i"):
            stems.append((base[:-1] + "y", base))  # bur-ied
        for stem, spelled in stems:
            if stem in d:
                k = counts(stem)[0]
                if k + 1 == n:
                    return _spelled(spelled, k) + [w[len(spelled):]]
    return None


def _spelled(w: str, n: int) -> list[str]:
    """A word's spelling cut into n pieces at its vowel groups."""
    if n <= 1 or len(w) < 2:
        return [w]
    if w.endswith("n't") and n >= 2 and len(w) > 3:  # does-n't, could-n't, as the song writes them
        return _spelled(w[:-3], n - 1) + ["n't"]
    suffixed = _suffixed(w, n)
    if suffixed:
        return suffixed
    groups = _groups(w)
    sounds = _vowels(w, n)
    while len(groups) > n:  # too many: join the two groups with the least between them (eve-ning, ev-ery): the
        # first such pair after a long vowel, the last after a short one
        gaps = [groups[k + 1][0] - groups[k][1] for k in range(len(groups) - 1)]
        least = [k for k, g in enumerate(gaps) if g == min(gaps)]
        k = least[-1] if sounds and sounds[0] in SHORT else least[0]
        groups[k:k + 2] = [(groups[k][0], groups[k + 1][1])]
    while len(groups) < n:  # too few: split the longest group of vowels (li-on, be-ing)
        k = max(range(len(groups)), key=lambda k: groups[k][1] - groups[k][0])
        a, b = groups[k]
        if b - a < 2:
            break
        groups[k:k + 1] = [(a, a + 1), (a + 1, b)]
    vowels = _vowels(w, len(groups))
    cuts = []
    for k, ((a, end), (start, _)) in enumerate(pairwise(groups)):
        cluster = w[end:start]
        short = end - a == 1 and k < len(vowels) and vowels[k] in SHORT and not (vowels[k] == "AA1" and w[a] == "a")
        if start == len(w) - (2 if w.endswith("les") else 1) and w.endswith(("le", "les")) and cluster:
            cut = max(end, start - 2)  # can-dle, whis-tle, cou-ples
        elif short and cluster in ("th", "sh", "ch", "ph", "ck"):
            cut = start  # moth-er, noth-ing
        elif (len(cluster) == 1 and end - a == 1 and k < len(vowels) and vowels[k] in SHORT and cluster not in "wy"
              and w[start:] != "y" and not (vowels[k] == "AA1" and w[a] == "a")):
            cut = end + 1  # ev-er, sev-en, rob-in (but bo-dy, wa-ter)
        else:
            cut = end + _cut(cluster)
        cuts.append(cut)
    pieces, last = [], 0
    for cut in cuts:
        pieces.append(w[last:cut])
        last = cut
    pieces.append(w[last:])
    return [p for p in pieces if p] if all(pieces) else [w]


def _compound(w: str, n: int) -> list[str] | None:
    """A word made of two the dictionary has (some-one, in-side, no-where), each split as it is alone: the
    second one of TAILS, or the first a word of two letters or more and the second a word of four."""
    d = phonetics._dictionary()
    w = w.removesuffix("'s")
    for k in range(2, len(w) - 1):
        a, b = w[:k], w[k:]
        head = len(a) >= 3 or a in ("no", "in", "up", "on")
        if head and a in d and b in d and (b in TAILS or a in ("in", "out", "over", "under", "news", "grand", "with")):
            nb = counts(b)[0]
            na = next((k for k in counts(a) if k + nb == n), None)
            if na is not None:
                return _spelled(a, na) + _spelled(b, nb)
    return None


def split(word: str, n: int | None = None) -> str:
    """A word written whole, hyphenated into n sung syllables (its dictionary count if n is None); its stars,
    punctuation and a say in braces kept where they are. A word already hyphenated, or one syllable, comes back
    as it is."""
    if "-" in word or "{" in word:
        return word
    m = _WORD.match(word)
    if not m:
        return word
    head, core, tail = m.groups()
    n = counts(core)[0] if n is None else n
    if n <= 1:
        return word
    low = core.lower()
    pieces = None if low.endswith("n't") else _compound(low, n)
    if pieces and low.endswith("'s"):
        pieces[-1] += "'s"
    pieces = pieces or _spelled(low, n)
    if len(pieces) != n:
        return word
    out, at = [], 0
    for piece in pieces:  # the person's own capitals and apostrophes, back in each piece
        out.append(core[at:at + len(piece)])
        at += len(piece)
    return head + "-".join(out) + tail


def _sung(word: str) -> int:
    from .heteronyms import bare

    return len([p for p in bare(word).split("-") if p])


def line(text: str, want: int | None = None) -> tuple[str, int]:
    """A lyric line with every word written whole hyphenated into its syllables, and how many it then sings. Where
    a word can be sung more than one way (ev-ery, ev-er-y), the ways that bring the line to want syllables, if
    want is given and any do; else each word's usual count."""
    words = text.split()
    options = []
    for word in words:
        if "-" in word or "{" in word:
            options.append([_sung(word)])
            continue
        m = _WORD.match(word)
        options.append(counts(m.group(2)) if m else [1])
    chosen = [o[0] for o in options]
    if want is not None and sum(chosen) != want:
        for k, o in enumerate(options):  # one word at a time, toward want
            for alt in o[1:]:
                if abs(sum(chosen) - chosen[k] + alt - want) < abs(sum(chosen) - want):
                    chosen[k] = alt
            if sum(chosen) == want:
                break
    out = [w if ("-" in w or "{" in w) else split(w, n) for w, n in zip(words, chosen)]
    return " ".join(out), sum(_sung(w) for w in out)
