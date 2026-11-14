"""A stage edition (songbird.stage, docs/ARRANGE.md "A stage edition"): the grid's stage fields are checked and
kept out of what the arrangers read; a child keeps them and never the edition's exact data; without either the
score is the program's own; the plan laid out from them (the lead's takes and where each is heard, the twins,
the levels) makes the stems as the stage mix made them."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import drift as D, harvest as H, stage as S, takeover as T, variation
from songbird.genome import load
from songbird.phrasing import Gesture
from songbird.realize import Params, choose_params, realize

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-11-14"), ADA.hash)


def seed():
    return Params.from_dict(G.seed_params)


def with_composition(params, **composition):
    return replace(params, composition={**params.composition, **composition})


GRID = {"verse:0": {"human": [0.0, 0.2], "players": {"harp": {"synth": "until:1"}, "bass": {"synth": "all"}}},
        "refrain:0": {"human": 0.5, "build": True, "players": {"bass": {"synth": "under"}, "drum": {"level": "hard"}}}}


def test_the_stage_fields_are_checked_and_refused_with_why():
    assert T.check(G, "arrange.verse:0.human", 0.25) == 0.25
    assert T.check(G, "arrange.verse:0.human", [0, 0.5, 1]) == [0.0, 0.5, 1.0]
    assert T.check(G, "arrange.verse:0.harp.synth", "until:2") == "until:2"
    assert T.check(G, "arrange.verse:0.harp.synth", "until:0") is None  # the player itself from the first line
    assert T.check(G, "arrange.verse:0.bass.synth", "under") == "under"
    for path, value in [("arrange.verse:0.human", 1.5), ("arrange.verse:0.human", True), ("arrange.verse:0.human", []),
                        ("arrange.verse:0.harp.synth", "half"), ("arrange.verse:0.lute.synth", "all"),
                        ("arrange.verse:0.synth", "all"), ("arrange.verse:0.harp.human", 0.5)]:
        with pytest.raises(ValueError):
            T.check(G, path, value)


def test_the_arrangers_never_see_the_stage_fields():
    params = with_composition(seed(), arrange=GRID)
    assert T.arranged(params) == {"refrain:0": {"build": True, "players": {"drum": {"level": "hard"}}}}
    assert T.arranged(params, stage=True) is GRID
    assert T.staged(params) == {"verse:0": {"human": [0.0, 0.2], "players": {"harp": {"synth": "until:1"},
                                                                             "bass": {"synth": "all"}}},
                                "refrain:0": {"human": 0.5, "players": {"bass": {"synth": "under"}}}}
    only = with_composition(seed(), arrange={"verse:0": GRID["verse:0"]})
    assert T.arranged(only) == {} and S.wanted(only)
    # the score the arrangers lay out is the one nobody arranged
    a = variation.lay(realize(G, only), only)
    b = variation.lay(realize(G, seed()), seed())
    assert a.notes == b.notes and a.sections == b.sections


def test_no_stage_fields_is_the_programs_own_score():
    params = seed()
    score = variation.lay(realize(G, params), params)
    assert not S.wanted(params)
    assert S.prepare(G, params, score) is score


def test_a_child_keeps_the_grid_and_never_the_exact_data():
    exact = {"release": 0.35, "levels": {"harp~": [["verse:0", 0]]}, "twins": {"harp~": ["harp", "arp"]}}
    parent = with_composition(seed(), arrange=GRID, exact=exact)
    for child in (choose_params(G, parent), choose_params(G, parent, ADA, DAY),
                  variation.choose(G, parent, ADA, DAY), choose_params(G, parent, style="synthfolk")):
        assert "exact" not in child.composition
        assert T.staged(child) == T.staged(parent)
    # the edition itself, replayed from its record, keeps it
    assert Params.from_dict(parent.to_dict()).composition["exact"] == exact


def test_the_lead_is_heard_from_each_take_where_its_lines_begin():
    secs = {"verse:0": (10.0, 30.0), "refrain:0": (30.0, 50.0), "turn:0": (50.0, 54.0), "verse:1": (54.0, 74.0)}
    starts = {h: [9.6 + d, 15.0 + d, 20.0 + d, 25.0 + d, 29.5 + d, 40.0 + d, 54.0 + d, 64.0 + d]
              for h, d in ((0.0, 0.0), (0.5, 0.01), (0.7, 0.02))}
    plan = S.arc_plan({"verse:0": [0.0, 0.0, 0.5], "verse:1": 0.7}, secs, starts)
    # the third line on is the list's last; the refrain, named nowhere, keeps the amount before it
    assert plan == [(9.6, 0.0), (20.01, 0.5), (54.02, 0.7)]


def test_the_grid_makes_twins_and_levels():
    twins, levels = S.grid_levels(T.staged(with_composition(seed(), arrange=GRID)), ["intro:0", "verse:0", "refrain:0", "tag:0"])
    assert twins == {"harp~": ("harp", "arp"), "bass~": ("bass", "synthbass")}
    assert levels["harp~"] == [["intro:0", None], ["verse:0", None], ["verse:0", 0.0], ["verse:0.1", 0.0],
                               ["verse:0.1", None]]
    assert levels["harp"] == [["intro:0", 0.0], ["verse:0", 0.0], ["verse:0", None], ["verse:0.1", None],
                              ["verse:0.1", 0.0]]
    assert levels["bass~"][-2:] == [["tag:0", S.UNDER], ["tag:0", None]]
    secs = {"intro:0": (0.0, 10.0), "verse:0": (10.0, 30.0), "refrain:0": (30.0, 50.0), "tag:0": (50.0, 60.0)}
    ts, gs = S.points(levels["harp"], secs, [9.6, 15.0, 20.0, 29.6])
    assert ts == [0.0, 10.0, 10.0 + S.EDGE, 15.0, 15.0 + S.EDGE] and gs == [1.0, 1.0, 0.0, 0.0, 1.0]
    assert S.when("verse:0.9", secs, [9.6, 15.0]) == 30.0 and S.when("tag:0.end", secs, []) == 60.0


def test_the_amount_scales_the_phrasing_and_the_timbre():
    assert S.amounts(0.0) == (0.0, 0.0) and S.amounts(0.5) == (1.0, 0.3) and S.amounts(1.0) == (1.0, 0.6)
    g = Gesture(early=0.1, hold=0.5, level=2.0, scoop=40.0, vibrato=-1.0)
    none = S.phrased({"v1": (g,)}, 0.0)["v1"][0]
    assert (none.early, none.hold, none.level, none.scoop, none.vibrato) == (0.0, 1.0, 0.0, 0.0, -1.0)


def test_the_plan_makes_the_stems(monkeypatch):
    """The stems from a plan, with the synthesis stood in for: the lead joined from its takes, the twin level with
    its player, each named part at its levels, the singers' last notes let go."""
    from songbird.synth import instruments, throat

    sr = 1000
    params = with_composition(seed(), arrange=GRID, exact={"release": 0.2})
    score = variation.lay(realize(G, params), params)
    score = S.prepare(G, params, score)
    plan = score.stage
    assert sorted(plan["takes"]) == [0.0, 0.2, 0.5] and plan["plan"][0][1] == 0.0
    assert set(plan["twins"]) == {"harp~", "bass~"} and set(plan["levels"]) >= {"harp~", "harp", "bass~", "bass"}
    assert S.touched(score) >= {"voice", "harp", "harp~", "bass", "bass~"}
    length = int(np.ceil(score.duration * sr))
    monkeypatch.setattr(throat, "available", lambda *a: True)
    monkeypatch.setattr(S, "sung", lambda notes, sr, singer, seed, lexicon, share: np.full(length, 1.0 + share))
    monkeypatch.setattr(instruments, "render_part", lambda *a, **k: np.full((length, 2), 0.25))
    jobs = [("harp", lambda: np.full((length, 2), 0.5)), ("bass", lambda: np.full((length, 2), 2.0)),
            ("lute", lambda: np.ones((length, 2))), ("voice", lambda: pytest.fail("the lead is sung from its takes")),
            ("choir1", lambda: np.ones((length, 2)))]
    from songbird.synth.voice import VoiceParams

    stems = {name: make() for name, make in S.jobs(score, sr, 1, VoiceParams(engine="learned"), jobs)}
    assert list(stems) == ["harp", "bass", "lute", "voice", "choir1", "bass~", "harp~"]
    np.testing.assert_array_equal(stems["lute"], 1.0)  # a part the plan doesn't name: as the program made it
    a, b = S.sections(score, params.form)["verse:0"]
    assert stems["harp~"][int((a + 1) * sr)] == pytest.approx([0.5, 0.5])  # level with the harp, in its place
    assert stems["harp"][int((a + 1) * sr)].max() == 0.0
    assert stems["bass~"].max() == pytest.approx(2.0)  # level with the bass
    assert stems["bass"][int((a + b) / 2 * sr)].max() == 0.0  # the twin plays all of the first verse
    assert stems["choir1"][-1].max() < 1e-3 and stems["choir1"][0].max() == 1.0  # its last note let go
    first = plan["plan"][1][0]
    assert stems["voice"][int(first * sr) - 100, 0] == pytest.approx(1.0 * 1.6 * np.cos(np.pi / 4))  # human 0
