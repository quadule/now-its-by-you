"""A round (docs/ARRANGE.md, "A round"): a section sung by voices coming in one after another on the same tune,
a person's choice (arrange.<section>:<n>.round). Where H's tune takes one, measured; checked and refused with
why; laid out with its tail (the later voices finishing, the band under them following the voice furthest along);
the later voices singing the singer's own notes and words, each a part of its own, the oldest first; nothing
else singing over them; marked, replayed and handed down; silent where a version's mode won't take it. With
nobody asking, nothing moves (the goldens say so too)."""

import json
from dataclasses import replace
from pathlib import Path

from songbird import canon, drift as D, edits as E, harvest as H, takeover as T
from songbird.genome import load
from songbird.realize import Params, choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-27"), ADA.hash)
LINE = 2 * G.meter.bar  # H's lines are two bars


def seed():
    return Params.from_dict(G.seed_params)


def arranged(params, edits):
    clean, problems = E.check(G, edits)
    assert not problems, problems
    overrides = E.Overrides(G, clean)
    return overrides.params(params), overrides


def span(params, sid):
    clock = timeline(G, params)
    _, _, a, b = next(o for o in T.spans(G, params, clock.lead) if o[0] == sid)
    return clock.seconds(a), clock.seconds(b)


def test_where_the_tune_takes_a_round():
    # in a major mode H's tune is pentatonic: its refrain and bridge go round with nothing a semitone or a
    # tritone apart, three voices a line apart, the band under the tail on the last line twice
    for name in ("refrain", "bridge"):
        plan = canon.choose(G, name, True, "ionian")
        assert (plan.voices, plan.distance, plan.first) == (3, LINE, 0)
        assert plan.under == (G.section(name).phrases[-1],) * 2
        assert canon.clash(G, name, plan, "ionian")["voices"] == 0.0
    assert canon.choose(G, "refrain", 4, "ionian").voices == 4
    assert canon.choose(G, "verse", True, "ionian").voices == 2  # the verse takes two
    # in a minor mode the tune has semitones in it: the refrain's last line only, three voices a bar apart
    tag = canon.choose(G, "refrain", True, "aeolian")
    assert not tag.whole and (tag.voices, tag.distance, tag.first, tag.under) == (3, G.meter.bar, 3, ("r4",))
    assert canon.choose(G, "refrain", 2, "aeolian") == tag
    assert canon.choose(G, "bridge", True, "aeolian") is None
    whole = next(p for p in canon.candidates(G, "refrain") if p.whole and p.voices == 3 and p.distance == LINE)
    assert canon.clash(G, "refrain", whole, "aeolian")["voices"] > 5
    # a section with no words, or one line, takes none
    assert not canon.fit(G, "intro") and not canon.fit(G, "turn") and not canon.fit(G, "tag")
    # the tail: the line the voice furthest along sings
    assert canon.under(G, "refrain", 2, 2) == ("r3", "r4") and canon.under(G, "refrain", 4, 1) == ("r4",) * 3


def test_asked_for_and_refused_with_why():
    bad = {"arrange.intro:0.round": True, "arrange.turn:0.round": True, "arrange.tag:0.round": True,
           "arrange.refrain:0.round": 5, "arrange.verse:0.round": "yes", "arrange.refrain:0.kit.round": True}
    for path, value in bad.items():
        clean, problems = E.check(G, {path: value})
        assert problems and path not in clean, (path, value)
    assert not canon.choose(G, "verse", 3, "ionian").whole  # three don't fit the whole verse: its last line goes round
    other = load(ROOT / "songs" / "c-somebody-sang-it.json")  # a tune that takes no round anywhere
    assert "doesn't sit over itself" in E.check(other, {"arrange.refrain:0.round": True})[1][0]["why"]
    clean, problems = E.check(G, {"arrange.refrain:2.round": True, "arrange.bridge:0.round": 4,
                                  "arrange.verse:1.round": 2, "arrange.refrain:0.round": False})
    assert not problems and clean["arrange.refrain:0.round"] is None
    # not with a length of its own, nor played: said, and the round left out
    for other in ({"arrange.refrain:2.bars": 16}, {"arrange.refrain:2.sung": False}):
        r = E.resolve(G, seed(), None, None, E.check(G, {"arrange.refrain:2.round": True, **other})[0])
        said = {p["path"]: p["why"] for p in r.problems}
        assert "a round is sung" in said["arrange.refrain:2.round"]
        assert "round" not in T.arranged(r.params).get("refrain:2", {})


def test_nobody_asking_moves_nothing():
    for params in (seed(), choose_params(G, None, ADA, DAY), choose_params(G, None, None, None, style="acappella")):
        assert canon.plans(G, params) == [None] * len(params.form)
        held = replace(params, composition={**params.composition, "arrange": {"refrain:0": {"build": True}}})
        assert canon.plans(G, held) == [None] * len(params.form)


def test_the_last_refrain_as_a_round():
    base = seed()  # the seed's own ballad: no backing voices, no choir
    params, _ = arranged(base, {"arrange.refrain:2.round": True})
    sid = "refrain:2"
    plan = T.phrase_plan(G, params)[8]
    assert plan == [(p, True) for p in ("r1", "r2", "r3", "r4")] + [("r4", False)] * 2
    a, b = span(params, sid)
    a0, b0 = span(base, sid)
    assert abs((b - a) - 1.5 * (b0 - a0)) < 1e-6  # twelve bars where it had eight
    before, after = realize(G, base), realize(G, params)
    assert after.duration > before.duration
    voice = [n for n in after.notes if n.part == "voice" and a - 1 <= n.start < b]
    entries = {p: [n for n in after.notes if n.part == p] for p in ("choir1", "choir2")}
    assert all(all(n.art == "round" for n in ns) and ns for ns in entries.values())
    mine = [n for n in voice if n.section == "refrain"]
    # each later voice sings the singer's syllables on the singer's pitches, the oldest (choir2) a line after the
    # singer and the parent (choir1) a line after that
    clock = timeline(G, params)
    line_s = clock.seconds(clock.lead + LINE) - clock.seconds(clock.lead)
    for part, lines in (("choir2", 1), ("choir1", 2)):
        got = entries[part]
        assert [n.syllable for n in got] == [n.syllable for n in mine]
        assert [n.pitch for n in got] == [n.pitch for n in mine]
        assert abs(got[0].start - (mine[0].start + lines * line_s)) < 0.1
    # the singer sings nothing in the tail; the last voice ends the section
    assert max(n.start + n.dur for n in mine) < b - 2 * line_s + 0.3
    assert abs(max(n.start + n.dur for n in entries["choir1"]) - b) < 0.3
    # nobody plays a line of its own there, nor answers between the lines
    lines = {"lead", "quote", "counter", "descant", "fills", "double"}
    last = next(s for s in after.band["sections"][::-1] if s["name"] == "refrain")
    was = next(s for s in before.band["sections"][::-1] if s["name"] == "refrain")
    assert not lines & set(last["parts"].values()), last["parts"]
    assert set(last["parts"]) <= set(was["parts"])
    # the rest of the song before it is as it was
    assert [n for n in after.notes if n.start + n.dur < a0 - 2] == [n for n in before.notes if n.start + n.dur < a0 - 2]


def test_a_bridge_round_is_the_lineage_passing_its_tune():
    base = replace(seed(), choir=2)  # the bridge's own harmony, two voices
    params, _ = arranged(base, {"arrange.bridge:0.round": True})
    a, b = span(params, "bridge:0")
    score = realize(G, params)
    there = [n for n in score.notes if n.part.startswith("choir") and a - 1 <= n.start < b - 0.1]
    assert there and all(n.art == "round" for n in there)  # no harmony under the round, only its voices
    elsewhere = [n for n in score.notes if n.part.startswith("choir") and n.start >= b]
    assert elsewhere and not any(n.art == "round" for n in elsewhere)  # the tag's harmony, as it was


def test_in_a_minor_mode_its_last_line_goes_round():
    base = replace(seed(), mode="aeolian")
    params, _ = arranged(base, {"arrange.refrain:2.round": True})
    a, b = span(params, "refrain:2")
    a0, b0 = span(base, "refrain:2")
    assert abs((b - a) - (b0 - a0) * 10 / 8) < 1e-6  # one line more: the third voice ends a line after the singer
    score = realize(G, params)
    for part in ("choir1", "choir2"):
        got = [n for n in score.notes if n.part == part]
        assert got and all(n.art == "round" and n.phrase == "r4" for n in got)  # the last line only
    # where the mode takes nothing (its bridge), the choice waits, said, and the version is as it was
    r = E.resolve(G, base, None, None, E.check(G, {"arrange.bridge:0.round": True})[0])
    assert any(p["path"] == "arrange.bridge:0.round" and "mode" in p["why"] for p in r.problems)
    held = replace(base, composition={"arrange": {"bridge:0": {"round": True}}})
    assert realize(G, held) == realize(G, base)


def test_an_a_cappella_round_is_its_voices_alone():
    base = choose_params(G, None, None, None, style="acappella")
    sid = f"refrain:{list(base.form).count('refrain') - 1}"
    params, _ = arranged(base, {f"arrange.{sid}.round": True})
    a, b = span(params, sid)
    score = realize(G, params)
    group = [n for n in score.notes if n.part.startswith("choir") and a <= n.start < b - 0.1]
    assert group and all(n.art == "round" for n in group)  # the parts make way for the round's voices
    assert {n.part for n in group} == {"choir1", "choir2"}
    assert any(n.part.startswith("choir") and n.art != "round" for n in score.notes)  # the parts elsewhere


def test_marked_replayed_and_handed_down():
    edits = {"arrange.refrain:3.round": True}
    r = E.resolve(G, None, ADA, DAY, E.check(G, edits)[0])
    assert "arrange.refrain:3.round" in r.applied, r.problems
    assert r.marks["arrange.refrain:3.round"] == {"value": True, "was": False}
    record = json.loads(json.dumps({"params": r.params.to_dict(), "chosen_by_you": r.marks}))
    again = E.resolve(G, None, ADA, DAY, E.from_record(record))
    assert again.params == r.params
    replayed = Params.from_dict(record["params"])
    assert realize(G, replayed, lyrics=r.lyrics) == realize(G, r.params, lyrics=r.lyrics)
    child = choose_params(G, replayed, H.fictional("basil"), DAY)
    assert T.arranged(child).get("refrain:3", {}).get("round") is True
    released = E.resolve(G, child, None, None, {"arrange.refrain:3.round": None})
    assert "refrain:3" not in T.arranged(released.params)
