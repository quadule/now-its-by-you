"""Words written whole are split into the syllables the singer sings (songbird/hyphens.py)."""

import json
from pathlib import Path

from songbird import composition, genome as G, hyphens

ROOT = Path(__file__).parent.parent
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


def test_words_split_as_a_person_would_write_them():
    said = {w: hyphens.split(w) for w in ("father", "window", "someone", "inside", "evening", "letter", "carries",
                                          "harbor's", "doesn't", "nobody's", "making", "watching", "candle", "water",
                                          "asleep", "cannot", "something", "machine", "numbers", "every")}
    assert said == {"father": "fa-ther", "window": "win-dow", "someone": "some-one", "inside": "in-side",
                    "evening": "eve-ning", "letter": "let-ter", "carries": "car-ries", "harbor's": "har-bor's",
                    "doesn't": "does-n't", "nobody's": "no-bo-dy's", "making": "mak-ing", "watching": "watch-ing",
                    "candle": "can-dle", "water": "wa-ter", "asleep": "a-sleep", "cannot": "can-not",
                    "something": "some-thing", "machine": "ma-chine", "numbers": "num-bers", "every": "ev-e-ry"}
    assert hyphens.split("*asleep*.") == "*a-sleep*."  # marks and punctuation kept where they are
    assert hyphens.split("car-ry") == "car-ry" and hyphens.split("bass{base}") == "bass{base}"  # a person's own way


def test_a_line_takes_the_count_its_notes_want():
    assert hyphens.line("My father kept watch on the light on the hill,", 11) == (
        "My fa-ther kept watch on the light on the hill,", 11)
    assert hyphens.line("every road", 3) == ("ev-ery road", 3)  # a word said two ways: the way that fits
    assert hyphens.line("every road", 4) == ("ev-e-ry road", 4)


def test_the_songs_own_words_are_counted_as_the_song_counts_them():
    """Every word of the song's bank, written whole, comes back with the syllables the bank gives it."""
    words: set[str] = set()

    def walk(x):
        if isinstance(x, str):
            for w in x.split():
                w = w.strip("*.,;:!?\"()").replace("’", "'")
                if "-" in w and "{" not in w and all(p.isalpha() or (p and "'" in p) for p in w.split("-")):
                    words.add(w)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(json.loads(LEAD.read_text()))
    from songbird import phonetics

    words = {w for w in words if w.replace("-", "").lower() in phonetics._dictionary()}  # (not self-portrait)
    assert len(words) > 200
    wrong = [w for w in words if len(hyphens.split(w.replace("-", "")).split("-")) != len(w.split("-"))
             and len(w.split("-")) not in hyphens.counts(w.replace("-", ""))]
    assert not wrong, wrong


def test_a_line_written_whole_is_sung_split():
    g = G.load(LEAD)
    text = composition.check_lyric(g, "lyrics.verse:wire.0", "My father kept watch on the light on the hill,")
    assert text == "My fa-ther kept watch on the light on the hill,"


def test_the_page_asks_how_its_lines_split():
    from songbird import studio

    said = studio.syllable_counts([{"text": "came home by a window with someone inside.", "want": 11}, {"text": "every"}])
    assert said == [{"text": "came home by a win-dow with some-one in-side.", "count": 11}, {"text": "ev-e-ry", "count": 3}]
    import pytest

    with pytest.raises(ValueError):
        studio.syllable_counts([{"text": "x"}] * 65)
