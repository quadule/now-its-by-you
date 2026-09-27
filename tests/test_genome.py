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
    own = choose_params(g)  # the seed's own arrangement sings thirds behind the last refrains: not here
    score = realize(g, replace(own, choir=2, style=replace(own.style, backing="")))
    choir = [n for n in score.notes if n.part.startswith("choir")]
    assert {n.part for n in choir} == {"choir1", "choir2"}
    assert {n.section for n in choir} == {"bridge", "tag"}
    lead = {(n.start, n.syllable) for n in score.part("voice") if n.section in ("bridge", "tag")}
    assert {(n.start, n.syllable) for n in score.part("choir1")} == lead  # same words, same time


def test_a_fixed_line_can_turn_one_word_each_time_round():
    line = "Who {made|sang|heard|owns} this song?"
    assert [G.turn(line, i, 3) for i in range(3)] == ["Who made this song?", "Who sang this song?", "Who owns this song?"]
    assert [G.turn(line, i, 4) for i in range(4)] == [f"Who {w} this song?" for w in ("made", "sang", "heard", "owns")]
    assert G.turn(line, 0, 1) == "Who made this song?"
    assert G.turn(line, 0, 2) == "Who made this song?" and G.turn(line, 1, 2) == "Who owns this song?"
    assert G.turns(line) == [f"Who {w} this song?" for w in ("made", "sang", "heard", "owns")]
    assert G.turns("no choices") == ["no choices"]


def test_a_numbered_section_is_its_section_again():
    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    again = g.section("bridge2")
    assert again.name == "bridge2" and again.lyrics == "bridge" and again.choir
    assert again.phrases == g.sections["bridge"].phrases and g.section("bridge") is g.sections["bridge"]
    for missing in ("chorus", "chorus2", "2"):
        with pytest.raises(KeyError):
            g.section(missing)


def test_phrasing_moves_only_the_voice():
    from dataclasses import replace

    from songbird import phrasing as P
    from songbird.realize import choose_params, realize

    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    params = choose_params(g)
    plain = realize(g, params)
    late = {pid: tuple(P.Gesture(early=-0.125, hold=0.9, level=2.0) for _ in ph.sung) for pid, ph in g.phrases.items()}
    phrased = realize(g, params, phrasing=late)
    assert phrased.duration == plain.duration
    assert [n for n in phrased.notes if n.part != "voice"] == [n for n in plain.notes if n.part != "voice"]
    beat = 60.0 / params.tempo
    for a, b in zip(plain.part("voice"), phrased.part("voice")):
        assert abs(b.start - (a.start + 0.125 * beat)) < 1e-9 and b.gesture.level == 2.0


def test_choir_voices_sing_their_own_phrasings():
    from dataclasses import replace

    from songbird import phrasing as P
    from songbird.realize import choose_params, realize

    g = G.load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
    own = choose_params(g)
    params = replace(own, choir=2, style=replace(own.style, backing=""))
    late = {pid: tuple(P.Gesture(early=-0.25) for _ in ph.sung) for pid, ph in g.phrases.items()}
    score = realize(g, params, choir=[late, None])
    lead, first, second = score.part("voice"), score.part("choir1"), score.part("choir2")
    assert first and len(first) == len(second)
    # the first choir voice sings a quarter beat behind the lead, its own way; the second keeps with the lead
    lead_at = {(n.phrase, n.syllable, round(n.start, 6)) for n in lead}
    assert all((n.phrase, n.syllable, round(n.start, 6)) in lead_at for n in second)
    behind = sorted(a.start - b.start for a, b in zip(sorted(first, key=lambda n: n.start), sorted(second, key=lambda n: n.start)))
    assert abs(behind[0] - 0.25 * 60.0 / params.tempo) < 1e-6 and abs(behind[-1] - behind[0]) < 1e-6
    assert all(n.gesture is not None for n in first) and all(n.gesture is None for n in second)
