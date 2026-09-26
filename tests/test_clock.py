"""A rendition's clock (realize.timeline): the beats its notes were placed on."""

from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G
from songbird.realize import PREROLL, choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


def test_beats_are_the_clock_the_notes_were_placed_on():
    g = G.load(H)
    p = choose_params(g)
    score, clock = realize(g, p), timeline(g, p)
    beats = clock.beats()
    times = [t for t, _ in beats]
    bars = [t for t, bar in beats if bar]
    assert all(min(abs(b - a) for b in bars) < 1e-9 for _, a, _ in score.sections)  # every section on a bar line
    beat = 60.0 / p.tempo
    # H's eighth-note pickup starts at the preroll: the beat before it is in the preroll, then the first bar line
    assert beats[0] == (pytest.approx(PREROLL - beat / 2), False) and beats[1] == (pytest.approx(clock.seconds(clock.lead)), True)
    # 4/4: a bar line every four beats, and one more where the song ends, when its last note does
    assert (len(bars) - 1) * 4 == len(beats) - 2
    assert times[-1] == pytest.approx(clock.seconds(clock.end)) and beats[-1][1]
    last = max(n.start + n.dur for n in score.part("voice"))
    assert times[-1] == pytest.approx(last, abs=0.05)
    gaps = np.diff(times)
    assert np.allclose(gaps[: len(gaps) - 8], beat)  # steady until the last phrase...
    assert gaps[-1] > gaps[-8] > beat - 1e-9  # ...which slows (the ritardando)


def test_a_pickup_of_a_whole_beat_has_a_beat_of_its_own():
    g = G.load(ROOT / "songs" / "c-somebody-sang-it.json")
    clock = timeline(g, choose_params(g))
    assert clock.lead == g.meter.beat  # a quarter-note pickup
    beats = dict(clock.beats())
    pickup = next(t for t in beats if abs(t - clock.seconds(0)) < 1e-9)
    assert beats[pickup] is False  # a beat, not a bar line
    assert all(t >= 0 for t in beats)


def test_compound_time_has_two_beats_a_bar():
    g = G.load(ROOT / "songs" / "b-coal-from-the-fire.json")  # 6/8
    beats = timeline(g, choose_params(g)).beats()
    marks = [bar for _, bar in beats if _ > 0.5]
    assert marks[:6] == [True, False, True, False, True, False]
