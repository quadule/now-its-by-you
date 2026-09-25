from pathlib import Path

import pytest

from songbird import genome as G

SKETCHES = sorted(Path(__file__).parent.parent.joinpath("songs").glob("*.json"))
WALTZ = G.Meter("3/4", unit=4, bar=3, beat=1, foot=3)


def test_pickup_holds_and_rests():
    notes, bars = G.parse_tune("5, | 1 - 2 | 3 . - | 5 - -", WALTZ)
    assert bars == 3
    assert [(n.degree, n.onset, n.dur) for n in notes] == [
        (-2, -1, 1), (1, 0, 2), (2, 2, 1), (3, 3, 1), (None, 4, 2), (5, 6, 3)
    ]


def test_accidentals_and_octaves():
    notes, _ = G.parse_tune("| #4 b7 1'' 2,,", G.Meter("4/4", unit=4, bar=4, beat=1, foot=4))
    assert [(n.degree, n.alter) for n in notes] == [(4, 1), (7, -1), (15, 0), (-12, 0)]


def test_bar_length_is_enforced():
    with pytest.raises(ValueError, match="bar 2"):
        G.parse_tune("| 1 2 3 | 4 5", WALTZ)


def test_derived_features():
    g = G.from_dict({
        "title": "t", "meter": WALTZ.__dict__,
        "phrases": {"a": {"tune": "5, | 1 1 2 | 3 - -", "chords": "i | i"}},
        "sections": {"s": {"phrases": ["a"], "lyrics": "refrain"}},
        "form": ["s"], "refrain": ["there once was a thought"],
    })
    p = g.phrases["a"]
    assert p.stress(g.meter) == "w S w w S"
    assert p.contour() == "U h u u"
    assert p.target == 3


def test_syllable_mismatch_is_caught():
    with pytest.raises(ValueError, match="syllables"):
        G.from_dict({
            "title": "t", "meter": WALTZ.__dict__,
            "phrases": {"a": {"tune": "| 1 1 2 | 3 - -", "chords": "i | i"}},
            "sections": {"s": {"phrases": ["a"], "lyrics": "refrain"}},
            "form": ["s"], "refrain": ["too many syl-la-bles here"],
        })


@pytest.mark.parametrize("path", SKETCHES, ids=lambda p: p.stem)
def test_sketches_load(path):
    g = G.load(path)  # validates refrain and every seed verse against the tune
    assert g.seed_verses and g.refrain
    verse = g.sections["verse"]
    for pid in verse.phrases:
        assert g.phrases[pid].stress(g.meter).count("S") >= 2


def test_fixed_blocks_and_choir():
    g = G.from_dict({
        "title": "t", "meter": WALTZ.__dict__,
        "phrases": {"a": {"tune": "| 1 1 2 | 3 - -", "chords": "i | i"}},
        "sections": {"s": {"phrases": ["a"], "lyrics": "refrain"},
                     "b": {"phrases": ["a"], "lyrics": "bridge", "choir": True}},
        "form": ["s", "b"], "refrain": ["one two three four"], "bridge": ["la la la la"],
    })
    assert g.fixed == {"refrain": ("one two three four",), "bridge": ("la la la la",)}
    assert g.sections["b"].choir and not g.sections["s"].choir
    with pytest.raises(ValueError, match="doesn't have"):
        G.from_dict({
            "title": "t", "meter": WALTZ.__dict__,
            "phrases": {"a": {"tune": "| 1 1 2 | 3 - -", "chords": "i | i"}},
            "sections": {"b": {"phrases": ["a"], "lyrics": "bridge"}},
            "form": ["b"], "refrain": ["one two three four"],
        })


def test_choir_sings_only_where_the_genome_allows():
    from dataclasses import replace

    from songbird.realize import choose_params, realize

    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    score = realize(g, replace(choose_params(g), choir=2))
    choir = [n for n in score.notes if n.part.startswith("choir")]
    assert {n.part for n in choir} == {"choir1", "choir2"}
    assert {n.section for n in choir} == {"bridge", "tag"}
    lead = {(n.start, n.syllable) for n in score.part("voice") if n.section in ("bridge", "tag")}
    assert {(n.start, n.syllable) for n in score.part("choir1")} == lead  # same words, same time
