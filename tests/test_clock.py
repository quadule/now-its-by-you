"""A rendition's clock (realize.timeline): the beats its notes were placed on."""

from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G
from songbird.realize import choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


def test_beats_are_the_clock_the_notes_were_placed_on():
    g = G.load(H)
    p = choose_params(g)
    score, clock = realize(g, p), timeline(g, p)
    beats = clock.beats()
    bars = [t for t, bar in beats if bar]
    assert all(min(abs(b - a) for b in bars) < 1e-9 for _, a, _ in score.sections)  # every section on a bar line
    assert sum(bar for _, bar in beats) * 4 == len(beats)  # 4/4: a bar line every four beats
    gaps = np.diff([t for t, _ in beats])
    beat = 60.0 / p.tempo
    assert np.allclose(gaps[: len(gaps) - 8], beat)  # steady until the last phrase...
    assert gaps[-1] > gaps[-8] > beat - 1e-9  # ...which slows (the ritardando)
    # the first beat is the first bar line, after the song's eighth-note pickup
    assert beats[0] == (pytest.approx(clock.seconds(clock.lead)), True)


def test_a_pickup_of_a_whole_beat_has_a_beat_of_its_own():
    g = G.load(ROOT / "songs" / "c-somebody-sang-it.json")
    clock = timeline(g, choose_params(g))
    assert clock.lead == g.meter.beat  # a quarter-note pickup
    first = clock.beats()[0]
    assert first == (pytest.approx(clock.seconds(0)), False)
