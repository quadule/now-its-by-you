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
    # the harp never picks the note being sung, and no pad or counter-line sits in the singer's register
    voice = score.part("voice")
    for n in score.part("harp"):
        sung = [v for v in voice if v.start - 0.02 <= n.start < v.start + v.dur - 0.03]
        assert all(v.pitch != n.pitch for v in sung)
    singer_top = max(v.pitch for v in voice)
    assert all(n.pitch > singer_top for n in score.part("fiddle") if n.section in ("verse", "bridge", "refrain"))


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


def test_a_small_change_changes_only_what_it_touches():
    """Each part draws from its own stream, bar by bar, and its timing from
    where a note is: dropping the lute leaves the bass, guitar and drum note for
    note as they were, and nudging the density keeps most of what was played
    (the drift is meant to be subtle day to day)."""
    g = G.load(H)
    p = choose_params(g)

    def notes(band, parts=INSTRUMENTS):
        return {(n.part, round(n.start, 6), n.pitch, round(n.vel, 6)) for n in realize(g, replace(p, band=band)).notes
                if n.part in parts}

    base = notes(Band(), ("bass", "guitar", "drum"))
    assert notes(Band(lute=0.0), ("bass", "guitar", "drum")) == base
    everyone, nudged = notes(Band()), notes(Band(density=0.55))
    assert len(everyone & nudged) > 0.6 * len(everyone)


def turn_quotes(g, params, monkeypatch) -> list[list[tuple[float, int]]]:
    """What each turn's quote plays, (units from the turn's start, pitch) a note, before the
    instrument's own way with it: the band's Context caught as realize() lays the song out."""
    from songbird import band as B, idioms  # noqa: F401 (idioms subclasses the Context being caught)

    caught = []
    real = B.Context
    with monkeypatch.context() as m:
        m.setattr(B, "Context", lambda *a: caught.append(real(*a)) or caught[-1])
        realize(g, params)
    ctx = caught[-1]
    with monkeypatch.context() as m:
        m.setattr(B, "statement", lambda ctx, part, notes, *a, **k: notes)
        return [[(round(t.u0 - s.u0, 6), t.pitch) for t in B.quote(ctx, i, "fiddle")]
                for i, s in enumerate(ctx.sections) if s.role == "turn"]


def test_a_turn_quotes_a_composed_tune_as_it_is_sung(monkeypatch):
    from songbird import composition as C
    from songbird.theory import degree_semitones

    g = G.load(H)
    plain = choose_params(g)
    before = turn_quotes(g, plain, monkeypatch)
    r3 = g.phrases["r3"]
    pitch = lambda d, k: plain.tonic + degree_semitones(d, plain.mode, r3.sung[k].alter)  # noqa: E731
    as_written = [(round(n.onset, 6), pitch(n.degree, k)) for k, n in enumerate(r3.sung) if n.onset >= 0]
    assert before and all(q == as_written for q in before)  # H's turns quote the refrain's third line

    def composing(notes):
        return replace(plain, composition={"tune": {"r3": C.pack_phrase(g, C.check_phrase(g, "r3", notes))}})

    notes = C.phrase_value(g, plain, "r3")
    assert turn_quotes(g, composing(notes), monkeypatch) == before  # composed as it was written, quoted as before
    # a person lifts one of its notes to the next chord tone up and moves another later in its beat
    notes[5]["degree"] += 2
    later = notes[7]["duration"] / 2
    notes[7]["onset"] += later
    notes[7]["duration"] -= later
    sung = [(round(n["onset"] * g.meter.beat, 6), pitch(n["degree"], k)) for k, n in enumerate(notes)
            if n["onset"] >= 0]
    assert sung != as_written
    assert all(q == sung for q in turn_quotes(g, composing(notes), monkeypatch))  # the turns play it as it's sung
