"""Words to sung syllables to phonemes, and what each phoneme sounds like.

Pronunciations come from the CMU Pronouncing Dictionary (data, not a model).
A word is fitted to the number of notes the tune gives it: 'fire' has a
two-syllable and a one-syllable reading, and the tune picks. Consonants
between vowels go to the following syllable as far as English allows an
onset, which is also what singers do: hold the vowel, move the consonant late.

Acoustic targets are for an adult tract of average length; the voice scales
them. Formants are (F1, F2, F3) in Hz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}

VOWEL_FORMANTS = {
    "IY": (280, 2250, 2890),
    "IH": (400, 1920, 2560),
    "EH": (600, 1750, 2500),
    "AE": (690, 1660, 2490),
    "AA": (730, 1090, 2440),
    "AO": (590, 880, 2540),
    "OH": (500, 900, 2450),  # the /o/ that begins OW
    "AH": (620, 1200, 2550),
    "AX": (500, 1450, 2500),  # unstressed AH, schwa
    "UH": (450, 1030, 2380),
    "UW": (320, 900, 2250),
    "ER": (480, 1350, 1690),
}
# Diphthongs: sung on the first quality, turning to the second at the note's end.
DIPHTHONGS = {"EY": ("EH", "IY"), "AY": ("AA", "IH"), "OW": ("OH", "UH"), "AW": ("AA", "UH"), "OY": ("AO", "IY"),
              # fire, wire, hour, our: sung on one note the r is a third vowel quality, er, that rings at the end
              "AYR": ("AA", "IH", "ER"), "AWR": ("AA", "UH", "ER"), "OYR": ("AO", "IY", "ER")}

# manner, place, voiced
CONSONANTS = {
    "P": ("stop", "labial", False), "B": ("stop", "labial", True),
    "T": ("stop", "alveolar", False), "D": ("stop", "alveolar", True),
    "K": ("stop", "velar", False), "G": ("stop", "velar", True),
    "CH": ("affricate", "postalveolar", False), "JH": ("affricate", "postalveolar", True),
    "F": ("fricative", "labiodental", False), "V": ("fricative", "labiodental", True),
    "TH": ("fricative", "dental", False), "DH": ("fricative", "dental", True),
    "S": ("fricative", "alveolar", False), "Z": ("fricative", "alveolar", True),
    "SH": ("fricative", "postalveolar", False), "ZH": ("fricative", "postalveolar", True),
    "HH": ("aspirate", "glottal", False),
    "M": ("nasal", "labial", True), "N": ("nasal", "alveolar", True), "NG": ("nasal", "velar", True),
    "L": ("liquid", "alveolar", True), "R": ("liquid", "retroflex", True),
    "W": ("glide", "labial", True), "Y": ("glide", "palatal", True),
}

# Formants at the point of constriction, the targets transitions aim for.
LOCI = {
    "labial": (250, 850, 2200),
    "labiodental": (300, 1100, 2300),
    "dental": (300, 1450, 2600),
    "alveolar": (300, 1700, 2650),
    "postalveolar": (300, 1950, 2500),
    "retroflex": (330, 1150, 1450),
    "palatal": (270, 2100, 3000),
}
SONORANT_FORMANTS = {
    "L": (340, 1100, 2800),
    "R": (330, 1150, 1450),
    "W": (300, 650, 2200),
    "Y": (270, 2100, 3000),
    "M": (260, 1000, 2200),
    "N": (260, 1600, 2600),
    "NG": (260, 2000, 2500),
}
NASAL_ZERO = {"M": 1000.0, "N": 1600.0, "NG": 2600.0}

# Noise spectra as band-pass regions (centre Hz, bandwidth Hz, gain dB), plus a level in dB.
FRICATION = {
    "S": ([(5800, 2000, 0.0), (8200, 3000, -3.0)], -9.0),
    "SH": ([(2800, 900, 0.0), (4200, 1600, -4.0), (6500, 3000, -12.0)], -9.0),
    "F": ([(2500, 3000, -4.0), (7000, 6000, 0.0)], -22.0),
    "TH": ([(3500, 4000, 0.0), (7500, 6000, 0.0)], -24.0),
}
FRICATION.update({"Z": (FRICATION["S"][0], -17.0), "ZH": (FRICATION["SH"][0], -17.0),
                  "V": (FRICATION["F"][0], -28.0), "DH": (FRICATION["TH"][0], -30.0)})
BURSTS = {
    "labial": ([(1200, 2000, 0.0), (3000, 3000, -6.0)], -14.0),
    "alveolar": ([(4200, 3000, 0.0), (6500, 3000, -4.0)], -9.0),
    "postalveolar": ([(3000, 1500, 0.0), (5000, 2500, -6.0)], -9.0),
    "velar": ([(2000, 900, 0.0), (3600, 1500, -8.0)], -10.0),  # centre follows the vowel's F2
}

# Tube postures for the vowels, fitted to VOWEL_FORMANTS on a 17.5 cm tract by
# tools/fit_postures.py within each vowel's anatomical region: (tongue place
# cm from glottis, tongue radius cm, lip radius cm), plus an optional second
# constriction (place cm, radius cm).
POSTURES = {
    "IY": (14.50, 0.30, 0.85, None),
    "IH": (13.00, 0.55, 0.65, None),
    "EH": (9.50, 0.95, 1.05, None),
    "AE": (4.00, 0.80, 1.15, None),
    "AA": (3.75, 0.25, 0.75, None),
    "AO": (5.00, 0.25, 0.45, None),
    "OH": (6.75, 0.40, 0.35, None),
    "AH": (7.25, 0.45, 0.65, None),
    "AX": (9.00, 0.45, 0.65, None),
    "UH": (8.25, 0.55, 0.35, None),
    "UW": (10.25, 0.40, 0.25, None),
    "ER": (4.00, 0.45, 0.70, (12.5, 0.20)),  # the r colour: a narrow palatal constriction lowers F3
}
# Where each consonant narrows the tube (cm from the glottis) and how far
# (radius cm; 0 closes it). Velars follow the vowel beside them.
CONSTRICTIONS = {
    "labial": (17.25, 0.0),
    "labiodental": (17.0, 0.12),
    "dental": (16.4, 0.12),
    "alveolar": (15.6, 0.0),
    "postalveolar": (14.8, 0.0),
    "palatal": (13.5, 0.22),
    "retroflex": (12.5, 0.15),
    "velar": (None, 0.0),
}
FRICATIVE_RADIUS = {"S": 0.09, "Z": 0.09, "SH": 0.13, "ZH": 0.13, "F": 0.12, "V": 0.12, "TH": 0.12, "DH": 0.12}

# Aspiration after a voiceless stop's release (voice onset time), longest at the
# back of the mouth. Below about 35 ms a listener hears b/d/g instead of p/t/k.
VOICE_ONSET = {"labial": 0.05, "alveolar": 0.06, "velar": 0.07, "postalveolar": 0.06}

# Base durations in seconds when there is time; squeezed when notes are fast.
DURATIONS = {"stop": 0.06, "affricate": 0.11, "aspirate": 0.06, "nasal": 0.07, "liquid": 0.06, "glide": 0.055}
FRICATIVE_DURATIONS = {"S": 0.11, "SH": 0.11, "F": 0.09, "TH": 0.08, "Z": 0.07, "ZH": 0.07, "V": 0.06, "DH": 0.05}

def _legal_onsets() -> set[tuple[str, ...]]:
    singles = "P B T D K G CH JH F V TH DH S Z SH HH M N L R W Y".split()
    clusters = """P_R B_R T_R D_R K_R G_R F_R TH_R SH_R P_L B_L K_L G_L F_L S_L
    S_P S_T S_K S_M S_N S_W S_F T_W D_W K_W G_W TH_W P_Y B_Y K_Y F_Y M_Y HH_Y V_Y
    S_P_R S_T_R S_K_R S_P_L S_K_W S_K_Y""".split()
    return {(s,) for s in singles} | {tuple(c.split("_")) for c in clusters}


LEGAL_ONSETS = _legal_onsets()


@dataclass(frozen=True)
class Syllable:
    onset: tuple[str, ...]
    nucleus: str  # vowel without stress digit; AX for an unstressed AH
    coda: tuple[str, ...]
    stressed: bool


@lru_cache(maxsize=1)
def _dictionary() -> dict[str, list[list[str]]]:
    import cmudict

    return cmudict.dict()


def clean(word: str) -> str:
    return re.sub(r"[^a-z']", "", word.lower().replace("’", "'")).strip("'")


def pronunciations(word: str, lexicon: dict[str, str] | None = None) -> list[list[str]]:
    """Every dictionary reading of a word written with syllable hyphens.

    A song's own lexicon comes first, so it can carry words no dictionary
    has. 'Car-ry' is looked up as 'carry'. A real compound like 'hun-dred-odd'
    isn't in the dictionary whole, so its syllables are regrouped into the
    fewest dictionary words that cover them: 'hundred' + 'odd'.
    """
    d = _dictionary()
    w = clean(word.replace("-", ""))
    if lexicon and w in {clean(k.replace("-", "")) for k in lexicon}:
        entry = next(v for k, v in lexicon.items() if clean(k.replace("-", "")) == w)
        return [entry.split()]
    if w in d:
        return d[w]
    pieces = [clean(p) for p in word.split("-") if clean(p)]
    best: list[list[str] | None] = [[]] + [None] * len(pieces)
    for end in range(1, len(pieces) + 1):
        for start in range(end):
            chunk = "".join(pieces[start:end])
            if best[start] is not None and chunk in d:
                candidate = best[start] + [chunk]
                if best[end] is None or len(candidate) < len(best[end]):
                    best[end] = candidate
    if best[-1] is not None:
        return [sum((d[part][0] for part in best[-1]), [])]
    return _inflected(w)


_VOICELESS = {"P", "T", "K", "F", "TH", "S", "SH", "CH", "HH"}
_SIBILANT = {"S", "Z", "SH", "ZH", "CH", "JH"}


def _suffix_sound(suffix: str, stem: list[str]) -> list[str]:
    last = stem[-1].rstrip("012")
    if suffix == "ed":
        return ["IH0", "D"] if last in ("T", "D") else ["T"] if last in _VOICELESS else ["D"]
    if suffix in ("s", "es", "'s"):
        return ["IH0", "Z"] if last in _SIBILANT else ["S"] if last in _VOICELESS else ["Z"]
    return {"ing": ["IH0", "NG"], "er": ["ER0"], "est": ["AH0", "S", "T"], "ly": ["L", "IY0"]}[suffix]


def _inflected(w: str) -> list[list[str]]:
    """Regular inflections the dictionary leaves out: hummed = hum + /d/."""
    d = _dictionary()
    for suffix in ("'s", "ing", "est", "ed", "es", "er", "ly", "s"):
        if not w.endswith(suffix) or len(w) <= len(suffix) + 1:
            continue
        base = w[: -len(suffix)]
        stems = [base, base + "e"]
        if len(base) > 2 and base[-1] == base[-2]:
            stems.append(base[:-1])  # hummed, stopped
        if base.endswith("i"):
            stems.append(base[:-1] + "y")  # carried, cried
        for stem in stems:
            if stem in d:
                return [reading + _suffix_sound(suffix, reading) for reading in d[stem]]
    return []


def _vowel_count(phones: list[str]) -> int:
    return sum(p.rstrip("012") in VOWELS for p in phones)


def fit(word: str, n: int, lexicon: dict[str, str] | None = None) -> list[Syllable]:
    """Pronounce `word` as exactly `n` sung syllables."""
    readings = pronunciations(word, lexicon)
    if not readings:
        raise KeyError(f"no pronunciation for {word!r}")
    exact = [r for r in readings if _vowel_count(r) == n]
    phones = list(exact[0] if exact else readings[0])
    # Too many vowels for the notes: an unstressed ER after a vowel becomes R
    # (fi-er -> fire), then unstressed vowels merge into their neighbours.
    while _vowel_count(phones) > n:
        for i in range(1, len(phones)):
            if phones[i] == "ER0" and phones[i - 1].rstrip("012") in VOWELS:
                phones[i] = "R"
                break
        else:
            unstressed = [i for i, p in enumerate(phones) if p.endswith("0")]
            if not unstressed:
                break
            del phones[unstressed[-1]]
    return _syllabify(phones)


def _syllabify(phones: list[str]) -> list[Syllable]:
    nuclei = [i for i, p in enumerate(phones) if p.rstrip("012") in VOWELS]
    if not nuclei:
        raise ValueError(f"no vowel in {phones}")
    bounds = []  # index where each syllable after the first begins
    for left, right in zip(nuclei, nuclei[1:]):
        cluster = phones[left + 1 : right]
        split = len(cluster)
        for k in range(len(cluster) + 1):
            if not cluster[k:] or tuple(cluster[k:]) in LEGAL_ONSETS:
                split = k
                break
        bounds.append(left + 1 + split)
    starts = [0] + bounds
    ends = bounds + [len(phones)]
    out = []
    for start, end, nucleus_index in zip(starts, ends, nuclei):
        raw = phones[nucleus_index]
        vowel = raw.rstrip("012")
        stressed = raw.endswith(("1", "2"))
        if vowel == "AH" and not stressed:
            vowel = "AX"
        coda = tuple(phones[nucleus_index + 1 : end])
        if vowel in ("AY", "AW", "OY") and coda[:1] == ("R",):  # fire, hour: the r joins the vowel
            vowel, coda = vowel + "R", coda[1:]
        out.append(Syllable(tuple(phones[start:nucleus_index]), vowel, coda, stressed))
    return out
