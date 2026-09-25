from pathlib import Path

import pytest

from songbird import genome as G
from songbird import phonetics as P

SKETCHES = sorted(Path(__file__).parent.parent.joinpath("songs").glob("*.json"))


def spell(syllables):
    return " | ".join(f"{' '.join(s.onset)}[{s.nucleus}]{' '.join(s.coda)}".strip() for s in syllables)


def test_tune_chooses_the_reading():
    assert spell(P.fit("fire", 1)) == "F[AYR]"  # one note: the r rings as the vowel's last quality
    assert spell(P.fit("fire", 2)) == "F[AY] | [ER]"
    assert spell(P.fit("tired", 1)) == "T[AYR]D"


def test_consonants_move_late_within_english_onsets():
    assert spell(P.fit("Car-ry", 2)) == "K[AE] | R[IY]"
    assert spell(P.fit("con-fined", 2)) == "K[AX]N | F[AY]N D"
    assert spell(P.fit("sing-ing", 2)) == "S[IH]NG | [IH]NG"


def test_compound_words_regroup_into_dictionary_words():
    assert len(P.fit("hun-dred-odd", 3)) == 3


def test_unknown_word_raises():
    with pytest.raises(KeyError):
        P.fit("qzxv", 1)


@pytest.mark.parametrize("path", SKETCHES, ids=lambda p: p.stem)
def test_every_seed_lyric_is_singable(path):
    g = G.load(path)
    fixed = [sung for block in g.fixed.values() for line in block for sung in G.turns(line)]
    for line in fixed + [l for verse in g.seed_verses for l in verse]:
        for word in line.split():
            n = len([p for p in word.split("-") if p])
            assert len(P.fit(word, n, g.lexicon)) == n, (line, word)


def test_regular_inflections_missing_from_the_dictionary():
    assert P.pronunciations("hummed")[0] == ["HH", "AH1", "M", "D"]
    assert P.pronunciations("scrolled")[0][-1] == "D"
    assert P._suffix_sound("ed", ["W", "EY1", "T"]) == ["IH0", "D"]
    assert P._suffix_sound("s", ["K", "AE1", "T"]) == ["S"]


def test_a_song_can_bring_its_own_words():
    lexicon = {"hwaet": "HH W AE1 T", "lo-ra-lai": "L OW1 R AH0 L AY2"}
    assert spell(P.fit("hwaet", 1, lexicon)) == "HH W[AE]T"
    assert len(P.fit("lo-ra-lai", 3, lexicon)) == 3
