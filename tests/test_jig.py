"""The jig (docs/STYLES.md, "Two more", and "A cappella and the jig, revised": it was a Celtic session)."""

from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from songbird import genome as G, style as S
from songbird.realize import choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"
SONG = 96.0


def session(**arrange):
    g = G.load(H)
    p = replace(choose_params(g, style="jig", arrange=arrange or None), choir=0)
    return g, p, realize(g, p)


def spans(score):
    out = {}
    for name, a, b in score.sections:
        out.setdefault(name, []).append((a, b))
    return out


def test_always_a_jig():
    """Six-eight, re-barred; a song that can't be re-barred keeps its beats and plays each in three (its own six-eight
    in a song already in it); "celtic", the style's old name, is read as the jig everywhere."""
    g, p, _ = session()
    assert p.style.feel == "six" and set(S.JIG.feels) == {"six"}
    assert 1.35 * SONG - 0.1 <= p.tempo <= 1.6 * SONG + 0.1  # a sung jig: a dotted beat at 65 to 77
    assert set(p.band.lineup) == {"whistle", "fiddle", "guitar", "drum", "concertina", "drone"}
    assert "celtic" not in S.STYLES and choose_params(g, style="celtic").style.name == "jig"
    old = S.Style.from_dict({"name": "celtic", "lineage": ["ballad", "celtic"], "feel": "double"})
    assert (old.name, old.lineage) == ("jig", ("ballad", "jig"))
    assert S.feels_for(G.load(ROOT / "songs" / "f-the-long-count.json"), S.JIG) == {"twelve": 1.0}
    assert S.feels_for(G.load(ROOT / "songs" / "b-coal-from-the-fire.json"), S.JIG) == {"straight": 1.0}
    from songbird import edits as E

    clean, problems = E.check(g, {"style.name": "celtic"})
    assert clean == {"style.name": "jig"} and not problems


def test_the_tunes_go_round_twice_the_lead_first_then_everyone():
    """The intro's four bars are eight and a turn's two are four (the same line quoted both times), the break's
    eight once; the first time round the lead and the guitar, the second the rest; a person's length wins."""
    g, p, score = session(intro="lead")
    bar = 4 * 60.0 / p.tempo
    s = spans(score)
    (a, b), = s["intro"]
    assert abs((b - a) - 8 * bar) < 0.05
    a, b = s["turn"][0]
    assert abs((b - a) - 4 * bar) < 0.05
    turn = [n for n in score.notes if a - 0.05 <= n.start < b - 0.05]
    lead = next(n.part for n in sorted(turn, key=lambda n: n.start) if n.part in ("whistle", "fiddle", "concertina"))
    mine = [n for n in turn if n.part == lead and n.dur > 0.06]  # (not a cut: a flick before its note)
    first = [(round((n.start - a) / bar, 1), n.pitch) for n in mine if n.start < a + 2 * bar - 0.05]
    second = [(round((n.start - a) / bar - 2, 1), n.pitch) for n in mine if n.start >= a + 2 * bar - 0.05]
    assert [x[1] for x in first][:4] == [x[1] for x in second][:4]  # the same line again
    joined = {n.part for n in turn if n.start >= a + 2 * bar - 0.05} - {lead}
    early = {n.part for n in turn if n.start < a + 2 * bar - 0.1} - {lead, "guitar", "drone"}
    assert not early and {"drum"} <= joined
    # a person's length for the intro wins over the style's
    p2 = replace(p, composition={"arrange": {"intro:0": {"bars": 4}}})
    (a, b), = spans(realize(g, p2))["intro"]
    assert abs((b - a) - 4 * bar) < 0.05


def test_everyone_on_the_tune_together():
    """Where nobody sings, the melody players play the tune in unison (each in its own octave, ornamented its own
    way): at each of the lead's notes the others sound the same pitch class."""
    g, p, score = session(intro="lead")
    (a, b), = spans(score)["intro"]
    half = a + (b - a) / 2
    tune = {"whistle", "fiddle", "concertina"} & {n.part for n in score.notes}
    notes = [n for n in score.notes if n.part in tune and half <= n.start < b and n.art != "cut"]
    by_part = {q: [n for n in notes if n.part == q] for q in tune}
    assert all(by_part.values())
    lead = by_part["whistle"]
    for other in tune - {"whistle"}:
        same = sum(any(abs(o.start - n.start) < 0.08 and int(o.pitch - n.pitch) % 12 == 0 for o in by_part[other])
                   for n in lead)
        assert same >= 0.7 * len(lead), (other, same, len(lead))


def test_the_frame_drum_tipped():
    """Down-up-down on each dotted beat (the bar's first stroke open), in six-eight or, in a song that can't be
    re-barred, on each of its beats in three."""
    g, p, score = session()
    drum = [n for n in score.notes if n.part == "drum"]
    assert {n.art for n in drum} <= {"bass", "tip"}
    eighth = 2.0 / 3.0 * 60.0 / p.tempo
    gaps = np.diff(sorted({round(n.start, 3) for n in drum}))
    assert abs(np.median(gaps) / eighth - 1.0) < 0.1
    f = G.load(ROOT / "songs" / "f-the-long-count.json")
    q = replace(choose_params(f, style="jig"), choir=0)
    assert q.style.feel == "twelve"
    drum = [n for n in realize(f, q).notes if n.part == "drum"]
    arts = Counter(n.art for n in drum)
    assert set(arts) <= {"bass", "tip"} and arts["tip"] > arts["bass"]
    gaps = np.diff(sorted({round(n.start, 3) for n in drum}))
    assert abs(np.median(gaps) / (20.0 / q.tempo) - 1.0) < 0.15  # a third of a beat


def test_the_guitar_is_in_dadgad():
    from songbird.idioms import dadgad_strings

    g, p, score = session()
    assert score.band["tuning"] == [38, 45, 50, 55, 57, 62]  # D A D G A D, in H's key
    strings = score.band["tuning"]
    for n in score.notes:
        if n.part == "guitar":
            assert any(0 <= n.pitch - s <= 5 for s in strings), n
    pitches = Counter(int(n.pitch) for n in score.notes if n.part == "guitar")
    assert pitches[62] > 0 and pitches[57] > 0  # the open strings ring

    class Ctx:
        tonic = 57  # A: the strings tuned down, never under what a guitar has but a tone or two
    assert dadgad_strings(Ctx)[0] == 33 and dadgad_strings(type("C", (), {"tonic": 65}))[0] == 41


def test_a_slow_air_before_the_tune():
    """The intro's first time round out of time, the lead alone over the drones; the band comes in the second."""
    g, p, score = session(intro="air")
    q, _, plain = session(intro="lead", feel=p.style.feel)
    clock = timeline(g, p)
    assert clock.air and not timeline(q, plain.__class__ and replace(p, style=replace(p.style, intro="lead"))).air
    (a, b), = spans(score)["intro"]
    tempo_bar = (4 if p.style.feel != "waltz" else 1.5) * 60.0 / p.tempo
    first = b - a - 4 * tempo_bar  # the first time round, drawn out
    assert 1.7 * 4 * tempo_bar < first < 2.4 * 4 * tempo_bar
    early = {n.part for n in score.notes if a - 1.0 <= n.start < a + first - 0.3}
    assert early <= {"whistle", "drone"}, early
    assert {n.part for n in score.notes if a + first <= n.start < b} >= {"fiddle", "guitar", "drum"}


def test_the_singer_ornaments_some_notes_of_its_own():
    g, p, score = session()
    extra = S.sung_ornaments(g, p)
    assert extra and not p.variants  # the singer's own, never handed down
    for v in extra:
        note = g.phrases[v.phrase].sung[v.note]
        assert v.kind in ("grace", "mordent", "turn") and note.onset % g.meter.foot == 0 and note.dur >= g.meter.beat
    assert sum(1 for n in score.notes if n.part == "voice" and n.ornament) >= len(extra)
    assert not S.sung_ornaments(g, choose_params(g, style="shanty"))


def test_a_jigs_child_stays_or_steps_to_the_ballads_neighbours():
    from songbird import drift as D, harvest as HV, variation as V

    parent = S.Style(name="jig", lineage=("ballad", "jig"))
    seen = set()
    for k in range(6):
        voice = HV.fictional(f"m{k}")
        c = V.character(voice)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2027-01-01"), 7.0):
            seen.add(S.place(parent, c, D.drift(t, voice.hash)))
    assert seen <= {"jig", *S.neighbours("ballad")} and "jig" in seen
