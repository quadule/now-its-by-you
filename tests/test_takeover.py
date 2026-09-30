"""Taking over the arrangement (docs/ARRANGE.md, "Taking over the arrangement"): a person's choices, section by
section and player by player, over the program's. With none, nothing changes (the goldens say so too). Each is
checked and refused with why; a player sits out, plays soft or hard, plays another pattern, comes in late, has
a fill or none; a section is played rather than sung (a drop), made longer or shorter, or builds; what was chosen
is marked, made again from the record, replayed the same and handed down; silent and said where a version can't
play it; the tempo follows the style; the page's grid shows the program's and the person's."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np

from songbird import band as B, composition as C, drift as D, edits as E, harvest as H, takeover as T
from songbird.genome import load
from songbird.realize import Params, choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-29"), ADA.hash)
# the seed's shape with a break before the bridge and verses in a pair
FORM = ["intro", "verse", "refrain", "turn", "verse", "refrain", "turn", "break", "bridge", "refrain", "tag"]
PAIRS = ["intro", "verse", "verse", "refrain", "turn", "verse", "refrain", "bridge", "refrain", "tag"]


def seed():
    return Params.from_dict(G.seed_params)


def synthfolk(form=FORM):
    return replace(choose_params(G, None, None, None, style="synthfolk"), form=tuple(form))


def taken(edits, params=None):
    """A version with these edits over params (the seed's): the parameters, and the edits' Overrides."""
    clean, problems = E.check(G, edits)
    assert not problems, problems
    overrides = E.Overrides(G, clean)
    return overrides.params(params if params is not None else seed()), overrides


def span(params, sid):
    """A section of the form's first and last bar lines, in seconds."""
    clock = timeline(G, params)
    _, _, a, b = next(o for o in T.spans(G, params, clock.lead) if o[0] == sid)
    return clock.seconds(a), clock.seconds(b)


def notes_in(score, params, sid, part=None):
    """The notes starting in a section of the form (a strum or a stroke a moment early at its bar line with it)."""
    a, b = span(params, sid)
    return [n for n in score.notes if a - 0.03 <= n.start < b - 0.03 and (part is None or n.part == part)]


def test_nothing_arranged_is_the_same_song():
    for params in (seed(), synthfolk(), synthfolk(PAIRS)):
        assert T.arranged(params) == {} and T.arranged_plan(G, params) == [None] * len(params.form)
        assert T.phrase_plan(G, params) == [[(pid, G.section(n).lyrics is not None) for pid in G.section(n).phrases]
                                            for n in params.form]
        empty = replace(params, composition={**params.composition, "arrange": {}})
        assert realize(G, params) == realize(G, empty)
    assert choose_params(G, None, ADA, DAY, overrides={}) == choose_params(G, None, ADA, DAY)


def test_choices_are_checked_and_refused_with_why():
    bad = {
        "arrange.chorus:0.kit.level": "hard",  # no such section
        "arrange.verse:0.kit.level": "loud",
        "arrange.verse:0.kazoo.level": "hard",
        "arrange.verse:0.drummachine.pattern": "polka",
        "arrange.verse:0.fiddle.fill": True,  # a fiddle plays no fills
        "arrange.verse:0.kit.from": -1,
        "arrange.verse:0.bars": 12,
        "arrange.turn:0.bars": 8,  # its quote fits its two bars
        "arrange.intro:0.sung": False,  # nothing to sing there
        "arrange.verse:0.build": "yes",
        "arrange.verse:0.level": "hard",  # a player's, not the section's
        "arrange.verse:0.kit.bars": 8,
        "arrange.verse.kit.level": "hard",
    }
    clean, problems = E.check(G, bad)
    assert clean == {} and {p["path"] for p in problems} == set(bad)
    said = {p["path"]: p["why"] for p in problems}
    assert "no section called chorus" in said["arrange.chorus:0.kit.level"]
    assert "out, soft, plays or hard" in said["arrange.verse:0.kit.level"]
    assert "four" in said["arrange.verse:0.drummachine.pattern"]  # it says what it can play
    assert "quoted" in said["arrange.turn:0.bars"] and "played already" in said["arrange.intro:0.sung"]
    # a sung section can't be shorter than its lines, unless it's played
    params, o = taken({"arrange.refrain:0.bars": 4})
    assert T.arranged(params) == {} and "as long as its lines" in o.problems[0]["why"]
    params, o = taken({"arrange.refrain:0.bars": 4, "arrange.refrain:0.sung": False})
    assert T.arranged(params) == {"refrain:0": {"bars": 4, "sung": False}} and not o.problems
    # releasing: null gives it back; sung true and build false are the section's own
    params, _ = taken({"arrange.refrain:0.sung": True, "arrange.refrain:0.build": False,
                       "arrange.refrain:0.kit.level": None})
    assert T.arranged(params) == {}


def test_four_on_the_floor_in_a_refrain():
    base = synthfolk()
    params, o = taken({"arrange.verse:0.drummachine.pattern": "four"}, base)
    assert o.applied == ["arrange.verse:0.drummachine.pattern"]
    before, after = realize(G, base), realize(G, params)
    a, b = span(params, "verse:0")
    beats = [t for t, _ in timeline(G, params).beats() if a - 1e-6 <= t < b - 1e-6]
    kicks = [n.start for n in after.notes if n.part == "drummachine" and n.art == "kick" and a - 0.1 <= n.start < b]
    # a kick on every beat, but the last: the fill into the refrain
    assert len(beats) == 32 and all(min(abs(k - t) for k in kicks) < 0.06 for t in beats[:-1])
    was = [n.start for n in before.notes if n.part == "drummachine" and n.art == "kick" and a - 0.1 <= n.start < b]
    assert len(was) < len(beats) - 1  # the style's own first verse was half time, or none
    # nobody else moved, and the drums elsewhere are as they were
    assert [n for n in after.notes if n.part != "drummachine"] == [n for n in before.notes if n.part != "drummachine"]
    outside = lambda s: [n for n in s.notes if n.part == "drummachine" and not a - 0.2 <= n.start < b]  # noqa: E731
    assert outside(after) == outside(before)


def test_a_player_sits_out_plays_soft_or_hard():
    base = synthfolk()
    score = realize(G, base)
    own = notes_in(score, base, "refrain:0", "guitar")
    rest, _ = taken({"arrange.refrain:0.guitar.level": "out"}, base)
    assert own and not notes_in(realize(G, rest), rest, "refrain:0", "guitar")
    sparse, _ = taken({"arrange.refrain:0.guitar.level": "soft"}, base)
    thin = notes_in(realize(G, sparse), sparse, "refrain:0", "guitar")
    assert 0 < len(thin) < len(own) and np.mean([n.vel for n in thin]) < np.mean([n.vel for n in own])
    full, _ = taken({"arrange.refrain:0.guitar.level": "hard"}, base)
    loud = notes_in(realize(G, full), full, "refrain:0", "guitar")
    assert np.mean([n.vel for n in loud]) > np.mean([n.vel for n in own])
    # the ballad's players step down and up from what the program has them play
    ballad, _ = taken({"arrange.refrain:0.bass.level": "soft", "arrange.refrain:2.drum.level": "out"})
    with B.overheard() as heard:
        realize(G, ballad)
    ctx = heard["ctx"]
    i = next(k for k, s in enumerate(ctx.sections) if s.name == "refrain")
    assert ctx.taken["program"][i]["bass"] == "walk" and ctx.sections[i].parts["bass"] == "roots"
    last = [k for k, s in enumerate(ctx.sections) if s.name == "refrain"][-1]
    assert "drum" in ctx.taken["program"][last] and "drum" not in ctx.sections[last].parts


def test_a_player_sat_out_after_its_cells_were_set_is_silent_and_nothing_is_wrong():
    """docs/STUDIO-EDM-TEST.md, second attempt, bug 5: everyone hard in refrain 2, then the guitar sat out
    everywhere; the guitar is silent and the page isn't told "this version's band has no guitar"."""
    edits = {"style.name": "synthfolk", "arrange.refrain:1.guitar.level": "hard", "band.guitar": 0}
    r = E.resolve(G, None, ADA, DAY, E.check(G, edits)[0])
    assert not r.problems and set(edits) <= set(r.applied)
    assert not [n for n in realize(G, r.params).notes if n.part == "guitar"]  # silent everywhere
    assert T.silent(G, r.params, "arrange.refrain:1.guitar.level", edits) is None
    # a player the band hasn't got still waits, said
    assert "has no fiddle" in T.silent(G, r.params, "arrange.refrain:1.fiddle.level", {"band.fiddle": 0})
    back = E.resolve(G, None, ADA, DAY, E.check(G, {**edits, "band.guitar": 1.0})[0])  # back in: hard there, as set
    assert T.arranged(back.params)["refrain:1"]["players"]["guitar"]["level"] == "hard" and not back.problems


def test_a_played_refrain_is_a_drop():
    base = synthfolk()
    r0 = E.resolve(G, base, None, None, {})
    r = E.resolve(G, base, None, None, E.check(G, {"arrange.refrain:1.sung": False})[0])
    assert r.applied == ["arrange.refrain:1.sung"] and not r.problems
    assert r.lyrics == r0.lyrics  # its words are still drawn, so no other section's move
    score = realize(G, r.params, lyrics=r.lyrics)
    drop = notes_in(score, r.params, "refrain:1")
    assert not [n for n in drop if n.part == "voice" or n.part.startswith("choir")]
    lead = [n for n in drop if n.part == "synthlead"]
    assert len(lead) >= 20  # the lead plays the tune
    sung = realize(G, base, lyrics=r0.lyrics)
    # the band keeps its weight under the lead (a drop, not a break)
    band = lambda notes: np.mean([n.vel for n in notes if n.part in ("guitar", "synthbass", "synthpad")])  # noqa: E731
    assert band(drop) >= band(notes_in(sung, base, "refrain:1")) - 0.02
    a, b = span(base, "refrain:1")
    outside = lambda s: [n for n in s.notes if n.part == "voice" and not a - 1 <= n.start < b]  # noqa: E731
    assert outside(score) == outside(sung)  # the singer elsewhere as sung


def test_section_lengths():
    base = replace(seed(), form=tuple(FORM))
    params, o = taken({"arrange.break:0.bars": 16, "arrange.intro:0.bars": 8, "arrange.refrain:2.bars": 16}, base)
    assert not o.problems
    clock0, clock = timeline(G, base), timeline(G, params)
    bar = G.meter.bar
    assert clock.end - clock0.end == (8 + 4 + 8) * bar
    plan = T.phrase_plan(G, params)
    assert [p for p, _ in plan[FORM.index("break")]] == ["v1", "v2", "v3", "v2"] * 2
    assert [p for p, _ in plan[0]] == ["r3", "r4", "r3", "r4"]
    last = plan[FORM.index("refrain", 9)]
    assert [(p, s) for p, s in last] == [(p, True) for p in ("r1", "r2", "r3", "r4")] + \
           [(p, False) for p in ("r1", "r2", "r3", "r4")]
    score = realize(G, params)
    view = C.view(G, params, None)
    assert abs(view["duration_seconds"] - clock.seconds(clock.end)) < 1e-9
    assert [s["id"] for s in view["sections"]] == C.section_ids(params.form)
    for s in view["sections"]:
        a, b = span(params, s["id"])
        assert abs(s["start_seconds"] - a) < 1e-9 and abs(s["end_seconds"] - b) < 1e-9
    # the lengthened last refrain: sung for its lines, then the lead plays them again
    a, b = span(params, "refrain:2")
    middle = a + (b - a) / 2
    voice = [n for n in score.notes if n.part == "voice" and a <= n.start < b and n.section == "refrain"]
    assert voice and max(n.start for n in voice) < middle
    assert [n for n in score.notes if n.part == "whistle" and middle <= n.start < b]
    # a played break made short keeps its last lines, its cadence
    short, _ = taken({"arrange.break:0.bars": 4}, base)
    assert [p for p, _ in T.phrase_plan(G, short)[FORM.index("break")]] == ["v3", "v2"]
    assert realize(G, short).duration < realize(G, base).duration


def test_a_build_fills_in_toward_the_next_section():
    base = synthfolk()
    params, o = taken({"arrange.break:0.bars": 16, "arrange.break:0.build": True}, base)
    assert not o.problems
    score = realize(G, params)
    a, b = span(params, "break:0")
    bar = (b - a) / 16
    snares = [n for n in notes_in(score, params, "break:0", "drummachine") if n.art == "snare"]
    per_bar = [sum(1 for n in snares if a + k * bar - 0.05 <= n.start < a + (k + 1) * bar - 0.05) for k in range(16)]
    assert per_bar[0] < per_bar[9] < per_bar[15] and per_bar[15] >= 12
    assert not [n for n in snares if n.start > b - bar / 4 - 0.05]  # the last beat left empty
    band = [n for n in notes_in(score, params, "break:0") if n.part not in ("drummachine", "synthlead", "arp")]
    early = [n for n in band if n.start < a + 4 * bar]
    late = [n for n in band if n.start >= b - 4 * bar]
    assert {n.part for n in early} < {n.part for n in late}  # the players come in one after another
    assert np.mean([n.vel for n in early]) < np.mean([n.vel for n in late])
    # a build leads into something: at the end of the song it is said, not kept
    r = E.resolve(G, base, None, None, E.check(G, {"arrange.tag:0.build": True})[0])
    assert "ends the song" in r.problems[0]["why"] and not T.arranged(r.params)


def test_a_player_comes_in_late_and_a_fill_is_chosen():
    base = synthfolk()
    params, _ = taken({"arrange.refrain:1.guitar.from": 2}, base)
    score = realize(G, params)
    clock = timeline(G, params)
    line = [p0 for p0, _ in _lines(params)["refrain:1"]][2]
    first = min(n.start for n in notes_in(score, params, "refrain:1", "guitar"))
    assert first >= clock.seconds(line) - 0.05
    # the drum machine's fill into the next section, taken away, and asked for where the band has none
    last_bar = lambda p, sid: (span(p, sid)[1] - (span(p, sid)[1] - span(p, sid)[0]) / 8, span(p, sid)[1])  # noqa: E731
    toms = lambda s, p, sid: [n for n in s.notes if n.part == "drummachine" and n.art.startswith("tom")  # noqa: E731
                              and last_bar(p, sid)[0] - 0.05 <= n.start < last_bar(p, sid)[1]]
    assert toms(realize(G, base), base, "verse:1")  # the style fills into the refrain
    off, _ = taken({"arrange.verse:1.drummachine.fill": False}, base)
    assert not toms(realize(G, off), off, "verse:1")
    assert not toms(realize(G, base), base, "refrain:1")
    on, _ = taken({"arrange.refrain:1.drummachine.fill": True}, base)
    assert toms(realize(G, on), on, "refrain:1")


def _lines(params):
    out = {}
    clock = timeline(G, params)
    for (sid, _, a, _b), lines in zip(T.spans(G, params, clock.lead), T.phrase_plan(G, params)):
        u = a
        out[sid] = []
        for pid, _ in lines:
            out[sid].append((u, u + G.phrases[pid].bars * G.meter.bar))
            u += G.phrases[pid].bars * G.meter.bar
    return out


def test_a_pair_is_split_only_where_a_person_arranged_it():
    base = synthfolk(PAIRS)
    params, _ = taken({"arrange.verse:1.synthbass.level": "out"}, base)
    before, after = realize(G, base), realize(G, params)
    a, b = span(params, "verse:1")
    assert notes_in(before, base, "verse:1", "synthbass") and not notes_in(after, params, "verse:1", "synthbass")
    assert [n for n in after.notes if not a - 0.3 <= n.start < b] == [n for n in before.notes if not a - 0.3 <= n.start < b]


def test_marked_made_again_from_the_record_replayed_and_handed_down():
    edits = {"arrange.refrain:0.guitar.level": "hard", "arrange.refrain:1.sung": False,
             "arrange.refrain:1.bars": 16, "arrange.verse:0.bass.from": 1}
    r = E.resolve(G, None, ADA, DAY, E.check(G, edits)[0])
    assert set(edits) <= set(r.applied), r.problems
    assert r.marks["arrange.refrain:0.guitar.level"] == {"value": "hard", "was": "plays"}
    assert r.marks["arrange.refrain:1.sung"] == {"value": False, "was": True}
    assert r.marks["arrange.refrain:1.bars"] == {"value": 16, "was": 8}
    record = json.loads(json.dumps({"params": r.params.to_dict(), "chosen_by_you": r.marks}))
    again = E.resolve(G, None, ADA, DAY, E.from_record(record))
    assert again.params == r.params
    replayed = Params.from_dict(record["params"])  # as --replay reads it: the same score, so the same samples
    assert realize(G, replayed, lyrics=r.lyrics) == realize(G, r.params, lyrics=r.lyrics)
    child = choose_params(G, replayed, H.fictional("basil"), DAY)
    assert T.arranged(child) == T.arranged(r.params)  # a person's arrangement passes on
    # a lock keeps what chance drew: the same version, marked locked
    plain = E.resolve(G, None, ADA, DAY, {})
    lock = {"style.entrances": plain.params.style.entrances, "style.breakdown": plain.params.style.breakdown}
    kept = E.resolve(G, None, ADA, DAY, lock)
    assert kept.params == plain.params and all(kept.marks[p]["locked"] for p in lock)
    released = E.resolve(G, child, None, None, {"arrange.refrain:1.sung": None, "arrange.refrain:1.bars": None})
    assert "refrain:1" not in T.arranged(released.params)
    assert released.marks["arrange.refrain:1.bars"] == {"value": None, "was": 16}


def test_silent_where_this_version_cant_play_it_and_said():
    base = replace(seed(), form=tuple(FORM))
    edits = {"arrange.verse:3.guitar.level": "out", "arrange.refrain:0.kit.level": "hard",
             "arrange.refrain:0.guitar.pattern": "travis"}
    r = E.resolve(G, base, None, None, E.check(G, edits)[0])
    said = {p["path"]: p["why"] for p in r.problems}
    assert set(said) == set(edits)
    assert "doesn't play that section" in said["arrange.verse:3.guitar.level"]
    assert "no kit" in said["arrange.refrain:0.kit.level"]
    assert "doesn't play Travis-picked" in said["arrange.refrain:0.guitar.pattern"]
    assert T.arranged(r.params) == {} and not set(edits) & set(r.applied)
    # one inherited waits, silent, for a version that plays it
    held = replace(base, composition={"arrange": {"verse:3": {"players": {"guitar": {"level": "out"}}}}})
    assert realize(G, held) == realize(G, base)


def test_the_tempo_follows_the_style():
    assert E.tempo_range(G) == (72.0, 124.8) and E.tempo_range(G, {"name": "ballad"}) == (72.0, 124.8)
    lo, hi = E.tempo_range(G, {"name": "synthfolk"})
    assert 130 <= hi <= 135 and lo == 72.0
    assert E.tempo_range(G, {"name": "lullaby", "feel": "waltz"})[0] < 45
    assert E.tempo_range(G, {"name": "stringband"})[1] <= 1.6 * 96
    assert E.bounds(G)["tempo"]["max"] == 153.6
    fast, o = taken({"tempo": 132}, synthfolk())
    assert fast.tempo == 132 and not o.problems
    held, o = taken({"tempo": 132})
    assert held.tempo == 124.8 and o.problems[0]["path"] == "tempo"
    r = E.resolve(G, None, None, None, {"tempo": 132})
    assert r.marks["tempo"]["value"] == 124.8  # marked as sung, so it replays


def test_the_styles_options_can_be_chosen_whole():
    base = synthfolk()
    chosen = {"style.stops": 2, "style.intro": "pad", "style.bridge": "half"}
    r = E.resolve(G, base, None, None, E.check(G, chosen)[0])
    params = r.params
    assert (params.style.stops, params.style.intro, params.style.bridge) == (2, "pad", "half")
    assert not r.problems and set(chosen) <= set(r.applied)
    # with no machine, choosing one leaves the others as they were
    others = lambda s: {k: v for k, v in s.to_dict().items() if k not in ("stops", "intro", "bridge", "lineage")}  # noqa: E731
    assert others(params.style) == others(base.style)
    r = E.resolve(G, base, None, None, {"style.alone": 6})
    assert "verses" in r.problems[0]["why"]


def test_a_breakdown_keeps_the_drum_machine_as_it_keeps_a_kit():
    """The style's breakdown brings the band in on the last refrain's third line, the rhythm playing from the
    start: a drum machine is the rhythm as a kit is (its module's family is "drum machine"; the arranger
    counted only "drums", so half the last refrain went without its kick; the artist, 2026-09-30)."""
    from songbird import idioms

    assert {"drums", "drum machine"} <= set(idioms.PERCUSSION) and idioms.family("drummachine") in idioms.DRUMS
    for style in ("synthfolk", "lofi"):
        base = choose_params(G, None, None, None, style=style)
        params = replace(base, form=tuple(FORM), style=replace(base.style, breakdown=True, entrances=False))
        a, b = span(params, "refrain:2")
        kicks = [n.start for n in realize(G, params).notes if n.part == "drummachine" and n.art == "kick" and a - 0.1 <= n.start < b]
        first, second = sum(k < (a + b) / 2 for k in kicks), sum(k >= (a + b) / 2 for k in kicks)
        assert first >= 0.8 * second > 0, (style, first, second)


def test_the_drum_machines_four_on_the_floor_is_one_choice_and_the_old_name_still_reads():
    """"four" and "machine" (four on the floor, the machine's own) played the same bars (idioms.w_machine is
    w_four): offered once since 2026-09-30, as four; a record, a draft or a lock made with "machine" reads as it."""
    offered = T.patterns("drummachine", False)
    assert "four" in offered and "machine" not in offered
    labels = [T.label("drummachine", x) for x in offered]
    assert labels.count("four on the floor") == 1 and not any("machine's own" in x for x in labels)
    old = "arrange.refrain:0.drummachine.pattern"
    clean, problems = E.check(G, {old: "machine"})
    assert not problems and clean[old] == "four"
    base = synthfolk()
    # yesterday's record, its parameters saying "machine", replays as it did
    said_old = replace(base, composition={"arrange": {"verse:1": {"players": {"drummachine": {"pattern": "machine"}}}}})
    said_new = replace(base, composition={"arrange": {"verse:1": {"players": {"drummachine": {"pattern": "four"}}}}})
    assert realize(G, said_old) == realize(G, said_new)
    assert not T.silent(G, said_old, "arrange.verse:1.drummachine.pattern")
    # a lock made yesterday (the program's own then was "machine") is still a lock of the program's own
    style = {"style.name": "synthfolk"}
    plain = E.resolve(G, None, ADA, DAY, E.check(G, style)[0])
    kept = E.resolve(G, None, ADA, DAY, E.check(G, {**style, old: "machine"})[0])
    assert kept.marks[old] == {"value": "four", "was": "four", "locked": True}, kept.marks[old]
    assert realize(G, kept.params, lyrics=kept.lyrics) == realize(G, plain.params, lyrics=plain.lyrics)  # the same song


def test_a_breakdown_keeps_the_synth_bass_as_it_keeps_a_bass():
    """The synth bass is registered with the synths (family "synth"), so the arranger left it out of the rhythm
    and it sat out the first half of a breakdown's last refrain; it is the bass as the bass is (the artist,
    2026-09-30: fix the bugs)."""
    from songbird import idioms

    assert idioms.is_bass("synthbass") and idioms.rhythmic("synthbass") and idioms.rhythmic("drummachine")
    assert not idioms.rhythmic("synthlead") and not idioms.rhythmic("arp")
    for style in ("synthfolk", "lofi"):
        base = choose_params(G, None, None, None, style=style)
        params = replace(base, form=tuple(FORM), style=replace(base.style, breakdown=True, entrances=False))
        a, b = span(params, "refrain:2")
        notes = [n.start for n in realize(G, params).notes if n.part == "synthbass" and a - 0.1 <= n.start < b]
        if not notes:
            continue  # this style's band has no synth bass
        first, second = sum(t < (a + b) / 2 for t in notes), sum(t >= (a + b) / 2 for t in notes)
        assert first >= 0.5 * second > 0, (style, first, second)
