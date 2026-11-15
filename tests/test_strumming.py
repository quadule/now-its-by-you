"""The strumming hand (songbird.strumming): its grooves keep the pendulum, a bar is the groove with a player's
variations, and a stroke crosses its strings as a hand does."""

import numpy as np

from songbird import strumming as S

SIMPLE = S.FOUR + S.FOUR_SIXTEENTHS + S.THREE + S.TWO


def test_simple_grooves_keep_the_pendulum():
    """Down strokes on the even slots, ups on the odd: the hand goes down and up whether it touches or not
    (the all-downs groove the one that breaks it, on purpose)."""
    for g in SIMPLE:
        if g.name == "downs":
            continue
        for k, ch in enumerate(g.slots):
            if ch != ".":
                assert (ch in "DdxBb") == (k % 2 == 0), (g.name, k, ch)


def test_grooves_fill_their_bars():
    lengths = {id(g): len(g.slots) for g in SIMPLE + S.COMPOUND}
    assert all(lengths[id(g)] in (8, 16) for g in S.FOUR + S.FOUR_SIXTEENTHS)
    assert all(lengths[id(g)] == 6 for g in S.THREE + S.COMPOUND)
    assert all(lengths[id(g)] == 4 for g in S.TWO)
    for style, names in S.STYLE_GROOVES.items():
        known = {g.name for g in SIMPLE + S.COMPOUND}
        assert set(names) <= known, style


def test_the_ladder_follows_the_tempo():
    names = lambda bpm: {g.name for g in S.ladder(4, False, bpm)}  # noqa: E731
    assert "slow-folk" in names(80) and "slow-folk" not in names(96)
    assert "eighths" in names(120) and "eighths" not in names(170)


def test_a_hand_is_its_own_and_repeats_its_groove():
    a = S.Hand(7, "guitar", beats=4, compound=False, bpm=110, density=0.6, style="indie")
    b = S.Hand(7, "guitar", beats=4, compound=False, bpm=110, density=0.6, style="indie")
    assert a.groove(2, 0.6) == b.groove(2, 0.6)
    groove, _ = a.groove(2, 0.6)
    bars = [a.bar(groove, np.random.default_rng(k)) for k in range(16)]
    shapes = [tuple((st.slot, st.kind in "Dd") for st in bar if st.kind not in "u") for bar in bars]
    # within a section the groove repeats: almost every bar the same downs and full ups
    assert max(shapes.count(s) for s in set(shapes)) >= 10


def test_energy_moves_the_span_before_the_groove():
    h = S.Hand(3, "guitar", beats=4, compound=False, bpm=110, density=0.5)
    quiet, quiet_span = h.groove(0, 0.45)
    loud, loud_span = h.groove(1, 0.65)
    assert loud_span > quiet_span
    assert abs(h.ladder.index(loud) - h.ladder.index(quiet)) <= 1


def test_the_up_before_a_change_lifts_or_rests():
    h = S.Hand(11, "guitar", beats=4, compound=False, bpm=100, density=0.6)
    h.lifts = 1.0
    g = next(g for g in S.FOUR if g.name == "faithful")
    for k in range(20):
        strokes = h.bar(g, np.random.default_rng(k), changes=(4.0,))
        last = [st for st in strokes if st.at > 3.0]
        assert all(st.flag == "open" for st in last if st.kind in "Uu")


def test_a_stroke_crosses_its_strings_in_order_and_in_time():
    h = S.Hand(5, "guitar", beats=4, compound=False, bpm=100, density=0.5)
    notes = [45.0, 52.0, 57.0, 61.0, 64.0]
    rng = np.random.default_rng(0)
    down = S.Stroke(0.0, "D", 1.0, slot=0)
    hit = h.strings(down, notes, 1.0, rng, first=True)
    assert hit == notes
    played = h.voiced(down, hit, 0.8, 0.3, rng)
    times = [t for _p, _v, t in played]
    assert times == sorted(times) and times[0] < 0.0  # it starts before the beat, so its weight lands on it
    assert 0.008 < times[-1] - times[0] < 0.04
    up = S.Stroke(0.5, "U", 0.5, slot=1)
    hit = h.strings(up, notes, 1.0, rng, first=False)
    assert hit[0] == 64.0 and len(hit) in (2, 3, 4)  # an up meets the top string first
    vels = [v for _p, v, _t in h.voiced(up, hit, 0.6, 0.3, rng)]
    assert vels[0] >= vels[-1] * 0.95
    fast = h.voiced(down, notes, 0.8, 0.02, rng)
    assert fast[-1][2] - fast[0][2] <= 0.3 * 0.02 + 1e-9  # never more than 30% of a slot


def test_open_strings_follow_the_capo():
    assert S.open_strings(0) == [55, 59, 64]
    assert S.open_strings(2) == [57, 61, 66]
