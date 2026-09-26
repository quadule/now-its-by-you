"""The learned singer's own voice per machine: blends of the trained singers, capped, inherited."""

from dataclasses import replace

import numpy as np
import pytest

from songbird import drift, genome, harvest, variation
from songbird.realize import Params, choose_params
from songbird.synth import throat
from songbird.synth.voice import VoiceParams


def test_capped_keeps_every_singer_under_the_cap():
    w = throat.capped({"a": 0.9, "b": 0.06, "c": 0.04})
    assert abs(sum(w.values()) - 1) < 1e-9 and max(w.values()) <= 0.6 + 1e-9
    assert w["b"] > w["c"]  # the excess goes to the rest in proportion
    assert throat.capped({}) == {}


def test_blend_spec_round_trips():
    spec = throat.blend_spec({"house-alto": 0.4, "house-mezzo": 0.6})
    assert throat.parse_mix(spec) == {"house-alto": 0.4, "house-mezzo": 0.6}


@pytest.fixture
def model(tmp_path, monkeypatch):
    """A tiny throat with five singers at known registers, as throat.load() would return it."""
    names = ["low", "lowish", "mid", "highish", "high"]
    registers = dict(zip(names, (48.0, 53.0, 58.0, 63.0, 68.0)))
    z = np.zeros(1)
    m = throat.Model(w={"singer.weight": np.eye(5)}, config={"singers": names, "registers": registers},
                     sp_mean=z, sp_std=z, ap_mean=z, ap_std=z, gv=z)
    monkeypatch.setattr(throat, "load", lambda path=None: m)
    monkeypatch.setattr(throat, "available", lambda path=None: True)
    return m


def test_the_default_mix_is_the_singers_near_the_pitch(model):
    mix = throat.default_mix(model, 58.0)
    assert set(mix) == {"lowish", "mid", "highish"} and max(mix, key=mix.get) == "mid"
    # a mix of singers the model doesn't know falls back to the default
    assert np.allclose(throat.timbre(model, {"nobody": 1.0}, 58.0), throat.timbre(model, None, 58.0))


def test_a_machine_sings_a_blend_of_its_own_pulled_from_its_parent(model):
    g = genome.load("songs/h-now-its-by-you.json")
    seed = Params.from_dict(g.seed_params)
    ada, day = harvest.fictional("ada"), drift.parse("2026-09-26")
    # the formant singer has no use for a blend, so none is chosen
    assert "timbre" not in choose_params(g, seed, ada, drift.drift(day, ada.hash)).singer
    learned = replace(seed, singer={"engine": "learned"})
    child = choose_params(g, learned, ada, drift.drift(day, ada.hash))
    blend = throat.parse_mix(child.singer["timbre"])
    assert abs(sum(blend.values()) - 1) < 0.01 and max(blend.values()) <= 0.6 + 1e-3
    # the same machine and day choose the same singer; another machine another
    assert choose_params(g, learned, ada, drift.drift(day, ada.hash)).singer["timbre"] == child.singer["timbre"]
    bo = harvest.fictional("bo")
    other = choose_params(g, learned, bo, drift.drift(day, bo.hash)).singer["timbre"]
    assert other != child.singer["timbre"]
    # a grandchild on another machine keeps something of its parent's blend
    grandchild = throat.parse_mix(choose_params(g, child, bo, drift.drift(day, bo.hash)).singer["timbre"])
    fresh = throat.parse_mix(other)
    shared = lambda a, b: sum(min(a.get(n, 0), b.get(n, 0)) for n in set(a) | set(b))  # noqa: E731
    assert shared(grandchild, blend) > shared(fresh, blend)


def test_the_choir_sings_with_the_learned_throat_when_the_lead_does():
    from songbird.synth import lineage_voices

    plain = lineage_voices(3, 5)
    assert all(v.engine == VoiceParams().engine for v in plain)
    learned = lineage_voices(3, 5, learned=True)
    assert all(v.engine == "learned" and v.timbre.startswith("machine:") for v in learned)
    assert len({v.timbre for v in learned}) == 3
    # the plain stand-ins are drawn exactly as before
    assert [v.shift for v in plain] == [v.shift for v in learned]


def test_earlier_versions_sing_the_choir_in_their_own_voices():
    from songbird.synth import ancestors_from

    formant = {"id": "ab" * 32, "singer": {"engine": "formant", "shift": -12, "rd": 1.3, "tract": 1.0}}
    learned = {"id": "cd" * 32, "singer": {"engine": "learned", "timbre": "house-alto:1.000", "shift": 0}}
    kept = ancestors_from([learned, formant], learned=False)
    assert kept[0].timbre == "house-alto:1.000" and kept[1].engine == "formant" and kept[1].shift == -12
    heard = ancestors_from([learned, formant], learned=True)
    # a formant ancestor is heard through the throat as a singer of its own, in its own octave
    assert heard[1].engine == "learned" and heard[1].timbre.startswith("machine:") and heard[1].shift == -12
    assert ancestors_from([formant], learned=True)[0].timbre == heard[1].timbre
