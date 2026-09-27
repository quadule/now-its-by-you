"""Learned expression must not scramble lyrics or overlap adjacent phonemes."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G, phrasing as P
from songbird.realize import choose_params, ordered_delivery, realize, sung_as
from songbird.score import Note
from songbird.synth import throat
from songbird.synth.voice import VoiceParams, schedule


def test_uncrowded_delivery_is_unchanged_including_phrase_lean():
    notes = [Note(part="voice", start=k * 0.5 + 1, dur=0.5, pitch=60, vel=0.7) for k in range(4)]
    requested = [sung_as(n, P.Gesture(early=-0.25), 0.5) for n in notes]
    assert ordered_delivery(list(zip(notes, requested))) == requested


@pytest.mark.parametrize("song", ["h-now-its-by-you", "b-coal-from-the-fire", "l-sticky-burr"])
@pytest.mark.parametrize("tempo", [1.0, 1.4])
def test_extreme_learned_timing_keeps_words_and_phonemes_in_order(song, tempo):
    genome = G.load(Path(__file__).resolve().parents[1] / "songs" / f"{song}.json")
    params = choose_params(genome)
    params = replace(params, tempo=params.tempo * tempo, choir=3)
    phrasing = {pid: tuple(P.Gesture(early=-0.25 if j % 2 == 0 else 0.25)
                          for j in range(len(p.sung))) for pid, p in genome.phrases.items()}
    plain = realize(genome, params)
    sung = realize(genome, params, phrasing=phrasing, choir=[phrasing] * 3)
    for part in ["voice", "choir1", "choir2", "choir3"]:
        notes = list(sung.part(part))
        assert [n.syllable for n in notes] == [n.syllable for n in plain.part(part)]
        assert all(b.start > a.start for a, b in zip(notes, notes[1:]))
        for durations in (None, throat.DURATIONS):
            segs = schedule(notes, VoiceParams(), genome.lexicon, durations, seed=1)
            assert all(s.t1 > s.t0 for s in segs)
            assert all(b.t0 >= a.t1 - 1e-8 for a, b in zip(segs, segs[1:]))
            vowels = [s for s in segs if s.role == "vowel"]
            assert np.allclose([s.t0 for s in vowels], [n.start for n in notes])
