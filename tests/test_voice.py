from dataclasses import replace
from pathlib import Path

import numpy as np

from songbird import genome as G
from songbird.realize import choose_params, realize
from songbird.synth.voice import VoiceParams, schedule, sing

SKETCH = Path(__file__).parent.parent / "songs" / "b-coal-from-the-fire.json"


def refrain_notes():
    g = G.load(SKETCH)
    score = realize(g, replace(choose_params(g), form=("refrain",)))
    return sorted(score.part("voice"), key=lambda n: n.start)


def test_vowels_land_on_the_beat_and_nothing_overlaps():
    notes = refrain_notes()
    segs = schedule(notes, VoiceParams())
    vowels = [s for s in segs if s.role == "vowel"]
    assert [round(v.t0, 9) for v in vowels] == [round(n.start, 9) for n in notes]
    for a, b in zip(segs, segs[1:]):
        assert b.t0 >= a.t1 - 1e-9, (a, b)
        assert a.t1 > a.t0


def test_onset_consonants_come_before_the_beat():
    notes = refrain_notes()
    segs = schedule(notes, VoiceParams())
    first_k = next(s for s in segs if s.phone == "K" and s.role == "onset")
    assert first_k.t1 <= notes[0].start + 1e-9


def test_sing_is_finite_and_deterministic():
    notes = refrain_notes()[:6]
    a = sing(notes, 44100, VoiceParams(), seed=3)
    b = sing(notes, 44100, VoiceParams(), seed=3)
    assert np.all(np.isfinite(a)) and np.array_equal(a, b)
    assert 0.05 < np.sqrt(np.mean(a**2)) < 0.5
