"""The palette gathers every new instrument by name, and its stems are the calibrated ones."""

import numpy as np
import pytest

from songbird.score import Note
from songbird.synth import instruments, palette
from songbird.synth.mixing import role_of

SR = 44100


def test_every_name_is_unique_and_owned():
    names = [name for module in palette.MODULES for name in module.SPEC]
    assert len(names) == len(set(names)) == len(palette.SPEC)
    assert not set(names) & set(instruments.INSTRUMENTS)  # nothing shadows the folk band's eight
    assert all(palette.OWNER[name].SPEC[name] is palette.SPEC[name] for name in names)


def test_no_name_lands_on_the_voice_or_choir_bus():
    assert all(role_of(name) not in ("voice", "choir") for name in palette.SPEC)


def test_a_stem_is_the_render_placed_at_its_level():
    name = "piano"
    notes = (Note("piano", 0.1, 0.5, 60.0, 0.6),)
    args = (SR, SR, np.random.default_rng(1), np.random.default_rng(2), {})
    dry = palette.render(name, notes, *args)
    args = (SR, SR, np.random.default_rng(1), np.random.default_rng(2), {})
    stem = palette.stem(name, notes, *args, gain=0.5)
    position, width = palette.SPEC[name]["place"]
    assert np.allclose(stem, instruments.place(dry, position, width) * palette.SPEC[name]["level"] * 0.5)
    with pytest.raises(ValueError):
        palette.render("kazoo", notes, SR, SR, np.random.default_rng(1), np.random.default_rng(2), {})
