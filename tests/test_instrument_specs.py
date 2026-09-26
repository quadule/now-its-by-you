"""Every new instrument, held to one standard through its SPEC.

Each module (piano, epiano, organ, mallets, analog, chip, drummachine) has
a SPEC and a render(); this checks every instrument in it the same way: the
contract's fields, that a typical part renders finite, deterministic, with
nothing before its first note and no DC, at its role's loudness, louder (and,
where the SPEC says, brighter) when played harder, in tune in the middle of
its compass, and cheaply. Modules not yet written are skipped.
"""

from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import instrument_levels as levels  # noqa: E402

from songbird.score import Note  # noqa: E402

SR = 44100


def _instruments():
    found = []
    for mod_name in levels.MODULES:
        try:
            module = importlib.import_module(f"songbird.synth.{mod_name}")
        except ModuleNotFoundError:
            continue
        for name in module.SPEC:
            found.append(pytest.param(module, name, id=name))
    return found


INSTRUMENTS = _instruments()
if not INSTRUMENTS:
    pytest.skip("no new instrument modules yet", allow_module_level=True)


def render(module, name, notes, secs, settings=None, seed=0, maker=0):
    rng = np.random.default_rng([seed, 17, 99])
    make = np.random.default_rng([maker, 29, 99])
    return module.render(name, tuple(notes), SR, int(secs * SR), rng, make, {**levels.SETTINGS, **(settings or {})})


def mono(y):
    return y if y.ndim == 1 else y.mean(axis=1)


def centroid(y):
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y)))) ** 2
    freqs = np.fft.rfftfreq(len(y), 1 / SR)
    return float((spec * freqs).sum() / (spec.sum() + 1e-30))


def probe(spec, vel, pitch=None, art=""):
    """One note (or, for percussion, one stroke of the first articulation) for a second."""
    if spec["register"] is None:
        piece = next(a for a in spec["articulations"] if a)
        return [Note("x", 0.1, 0.3, 60.0, vel, art=piece)]
    lo, hi = spec["register"]
    return [Note("x", 0.1, 0.9, float(pitch if pitch is not None else levels.centre(spec["register"])), vel, art=art)]


@pytest.mark.parametrize("module,name", INSTRUMENTS)
def test_the_spec_is_complete(module, name):
    spec = module.SPEC[name]
    assert isinstance(spec["family"], str) and spec["role"] in levels.TARGETS
    assert spec["register"] is None or (len(spec["register"]) == 2 and spec["register"][0] < spec["register"][1])
    position, width = spec["place"]
    assert -1.0 <= position <= 1.0 and 0.0 <= width <= 1.0
    assert spec["level"] > 0.0 and isinstance(spec["poly"], bool)
    assert isinstance(spec["articulations"], dict) and spec["articulations"] and isinstance(spec["about"], str)


@pytest.mark.parametrize("module,name", INSTRUMENTS)
def test_a_typical_part_is_clean_and_replays_exactly(module, name):
    spec = module.SPEC[name]
    notes = levels.typical_part(spec, bars=2)
    secs = max(n.start + n.dur for n in notes) + 2.0
    a = render(module, name, notes, secs)
    b = render(module, name, notes, secs)
    assert a.dtype == np.float64 and a.shape[0] == int(secs * SR) and a.ndim in (1, 2)
    assert np.all(np.isfinite(a)) and np.array_equal(a, b)
    first = min(n.start for n in notes)
    peak = np.max(np.abs(a))
    assert peak > 0.0
    assert np.max(np.abs(a[: int((first - 0.005) * SR)])) < 1e-4 * peak  # nothing before the first note
    x = a if a.ndim == 2 else a[:, None]
    rms = np.sqrt(np.mean(x**2, axis=0))
    assert np.all(np.abs(x.mean(axis=0)) < 1e-3 * rms + 1e-12)  # no DC: 60 dB under the signal


@pytest.mark.parametrize("module,name", INSTRUMENTS)
def test_a_typical_part_sits_at_its_roles_loudness(module, name):
    spec = module.SPEC[name]
    notes = levels.typical_part(spec)
    y = levels.render_placed(module, name, notes)
    assert abs(levels.loudness_while_playing(y, notes) - levels.target_of(spec)) < 1.0


@pytest.mark.parametrize("module,name", INSTRUMENTS)
def test_harder_is_louder_and_as_bright_as_the_spec_says(module, name):
    spec = module.SPEC[name]
    soft = mono(render(module, name, probe(spec, 0.3), 1.2))[int(0.1 * SR): int(0.4 * SR)]
    hard = mono(render(module, name, probe(spec, 0.9), 1.2))[int(0.1 * SR): int(0.4 * SR)]
    louder = 20 * np.log10(np.sqrt(np.mean(hard**2)) / np.sqrt(np.mean(soft**2)))
    assert louder > 4.0
    brighter = float(spec.get("brighter", 0.0))
    if brighter > 0.0:
        assert np.log2(centroid(hard) / centroid(soft)) > 0.8 * brighter


@pytest.mark.parametrize("module,name", INSTRUMENTS)
def test_in_tune_through_the_middle_of_its_compass(module, name):
    spec = module.SPEC[name]
    if spec["register"] is None:
        return
    lo, hi = spec["register"]
    middle = levels.centre(spec["register"])
    for pitch in sorted({max(lo + 3, middle - 7), middle, min(hi - 3, middle + 7)}):
        y = mono(render(module, name, [Note("x", 0.1, 1.2, float(pitch), 0.6)], 1.5, dict(wear=0.0, ornament=0.0)))
        f = 440.0 * 2 ** ((pitch - 69) / 12)
        seg = y[int(0.3 * SR): int(1.2 * SR)]
        spec_ = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 16 * SR))
        freqs = np.fft.rfftfreq(16 * SR, 1 / SR)
        band = (freqs > f * 0.97) & (freqs < f * 1.03)
        i = np.flatnonzero(band)[np.argmax(spec_[band])]
        a, b, c = np.log(spec_[i - 1: i + 2] + 1e-30)
        peak = freqs[i] + 0.5 * (a - c) / (a - 2 * b + c) * (freqs[1] - freqs[0])
        assert abs(1200 * np.log2(peak / f)) < 2.0, (pitch, 1200 * np.log2(peak / f))


@pytest.mark.parametrize("module,name", INSTRUMENTS)
def test_cheap_enough_for_a_whole_song(module, name):
    spec = module.SPEC[name]
    notes = levels.typical_part(spec, bars=2)
    levels.render_placed(module, name, notes)  # compile first
    notes = levels.typical_part(spec, bars=16)  # 40 s of music
    t = time.perf_counter()
    levels.render_placed(module, name, notes)
    assert time.perf_counter() - t < 4.0  # a three-minute part well under 20 s
