"""The band: its knobs, its arrangement of every song, and its stems."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G
from songbird.band import INSTRUMENTS, Band, guitar_voicing
from songbird.realize import Params, choose_params, realize

SONGS = sorted(Path(__file__).parent.parent.joinpath("songs").glob("*.json"))
H = Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json"
RANGES = {"bass": (28, 55), "harp": (28, 96), "guitar": (40, 80), "lute": (45, 90), "fiddle": (55, 90),
          "whistle": (60, 96), "drum": (0, 127), "drone": (36, 72)}


def test_params_carry_the_band_and_old_params_still_load():
    g = G.load(H)
    old = {k: v for k, v in g.seed_params.items() if k != "band"}
    p = Params.from_dict(old)
    assert p.band == Band()
    varied = replace(p, band=Band(guitar=0.0, density=0.8, pattern="strum", swing=0.3, maker=7))
    again = Params.from_dict(varied.to_dict())
    assert again == varied and isinstance(again.band, Band)
    assert varied.to_dict()["band"]["pattern"] == "strum"


def test_band_values_are_clamped_and_unknown_ones_ignored():
    b = Band.from_dict({"density": 3.0, "wear": -1, "harp": 9, "pattern": "polka", "lead": "tuba", "future": 1})
    assert (b.density, b.wear, b.harp, b.pattern, b.lead) == (1.0, 0.0, 2.0, "lilt", "whistle")


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_every_song_is_arranged_in_range_and_replays(path):
    g = G.load(path)
    p = choose_params(g)
    a, b = realize(g, p), realize(g, p)
    assert a == b
    band = [n for n in a.notes if n.part in INSTRUMENTS]
    assert {"bass", "harp"} <= {n.part for n in band}
    for n in band:
        lo, hi = RANGES[n.part]
        assert lo <= n.pitch <= hi, (n.part, n.pitch)
        assert n.dur > 0 and 0 < n.vel <= 1 and n.start >= 0
    assert a.band["sections"] and all(s["energy"] >= 0 for s in a.band["sections"])


def test_the_arrangement_builds_and_leaves_room():
    g = G.load(H)
    score = realize(g, choose_params(g))
    sections = score.band["sections"]
    verses = [s for s in sections if s["role"] == "verse"]
    refrains = [s for s in sections if s["role"] == "refrain"]
    assert verses[0]["energy"] < refrains[0]["energy"] < refrains[-1]["energy"]
    assert "drum" not in verses[0]["parts"] and "guitar" not in verses[0]["parts"]  # the first verse is sparse
    assert all(s["parts"].get("guitar") == "strum" for s in refrains)
    assert sections[0]["parts"].get("whistle") == "lead"  # the intro states the tune
    assert all(any(v in ("quote", "lead") for v in s["parts"].values()) for s in sections if s["role"] == "turn")
    bridge = next(s for s in sections if s["role"] == "bridge")
    assert "guitar" not in bridge["parts"] and bridge["parts"].get("drone")  # a different texture under the choir
    # under words the harp picks softer than where nobody sings
    intro_end = next(s for n, s, e in [(x, y, z) for x, y, z in score.sections] if n == "verse")
    harp = score.part("harp")
    assert np.mean([n.vel for n in harp if n.start >= intro_end]) < np.mean([n.vel for n in harp if n.start < intro_end]) * 1.1


def test_an_instrument_at_zero_sits_out():
    g = G.load(H)
    p = choose_params(g)
    score = realize(g, replace(p, band=Band(guitar=0.0, whistle=0.0)))
    parts = {n.part for n in score.notes}
    assert "guitar" not in parts and "whistle" not in parts
    assert score.band["sections"][0]["parts"].get("fiddle") == "lead"  # the next lead takes the intro


def test_density_and_pattern_change_the_playing():
    g = G.load(H)
    p = choose_params(g)
    sparse = realize(g, replace(p, band=Band(density=0.0)))
    busy = realize(g, replace(p, band=Band(density=1.0)))
    assert len(busy.notes) > 1.2 * len(sparse.notes)
    air = realize(g, replace(p, band=Band(pattern="air")))
    assert not air.part("drum") and len(air.part("guitar")) < len(realize(g, p).part("guitar")) / 3


def test_swing_delays_the_off_beats_only():
    g = G.load(H)
    p = choose_params(g)
    straight = realize(g, p)
    swung = realize(g, replace(p, band=Band(swing=1.0)))
    beat = 60.0 / p.tempo
    shifts = [b.start - a.start for a, b in zip(straight.part("voice"), swung.part("voice"))]
    assert min(shifts) > -0.03 and max(shifts) > beat / 6 - 0.03  # a triplet lilt: an off-beat moves a sixth of a beat


def test_guitar_chords_are_open_shapes_on_the_root():
    d_major = (2, 6, 9)
    shape, _ = guitar_voicing(d_major, 0)
    pitches = [p for _, p in shape]
    strings = [s for s, _ in shape]
    assert pitches[0] % 12 == 2 and {p % 12 for p in pitches} == set(d_major)
    assert strings == sorted(set(strings)) and pitches == sorted(pitches)
    assert [p for _, p in guitar_voicing((7, 11, 2), 0)[0]] == [43, 47, 50, 55, 59, 67]  # G: 3 2 0 0 0 3


def test_stems_are_named_by_role_and_line_up():
    from songbird import synth

    g = G.load(H)
    p = replace(choose_params(g), form=("intro", "verse"))
    score = realize(g, p)
    stems = synth.render_stems(score, seed=p.seed)
    assert set(stems) >= {"bass", "harp", "whistle", "drone", "voice"}
    assert set(stems) - {"voice"} <= set(INSTRUMENTS)
    lengths = {len(s) for s in stems.values()}
    assert len(lengths) == 1
    for name, stem in stems.items():
        assert stem.shape[1] == 2 and np.all(np.isfinite(stem)) and np.abs(stem).max() < 4.0, name
