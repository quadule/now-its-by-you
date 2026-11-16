"""The studio's live sound (docs/notes/STUDIO-LIVE-SOUND.md): a section's preview made again after an edit,
through the stems kept from before, is the same samples as one made cold; it ends with its loop; a single note
of a player is made as its maker makes it, the same every time, and is the sketch's in an open studio."""

import io
import json
from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

from songbird import public as P, studio as S, synth
from songbird.synth.cache import keys
from songbird.synth.instruments import INSTRUMENTS, render_part

from test_studio import LEAD


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


def made(studio, edits, index):
    """A section's preview made now (its file gone if it was there), as its samples, and its job's result."""
    v = studio.version(edits)
    key = studio.key(v, index)
    (studio.cache / f"{key}.flac").unlink(missing_ok=True)
    result = studio._section(S.Job("t", key, "preview", "t", None), v, key, index)
    pcm, _ = sf.read(studio.cache / f"{key}.flac", dtype="int16")
    return pcm, result


def test_a_section_made_again_through_the_kept_stems_is_the_same_as_one_made_cold(home):
    """Each kind of edit makes again only what it changes, and what it keeps is exactly what it would make."""
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    verse = next(s for s in studio.song({})["composition"]["sections"] if s["name"] == "verse")
    line = verse["phrases"][0]
    tune = [{"degree": n["degree"], "onset": n["onset"], "duration": n["duration"]} for n in line["notes"]]
    tune[2]["degree"] += 1
    steps = [{"mix.guitar.pan": 0.6}, {"band.guitar": 1.0}, {f"part.guitar.{line['part_key']}": [[0, 96, 0, 80], [96, 96, 4, 90]]},
             {f"part.drum.{line['part_key']}": [[0, 24, 0, 100], [96, 24, 1, 60]]}, {f"tune.{line['place']}": tune}]
    edits = {}
    made(studio, edits, verse["index"])
    misses = []
    for step in steps:
        edits = {**edits, **step}
        before = studio._stem_cache.misses
        warm, result = made(studio, edits, verse["index"])
        misses.append(studio._stem_cache.misses - before)
    # a pan, a level, a line of notes or of hits: that player alone made again; a sung note: the voice alone
    assert misses == [1, 1, 1, 1, 1], misses
    cold, _ = made(S.Studio(None, str(LEAD), "fictional:ada", out=home / "cold"), edits, verse["index"])
    np.testing.assert_array_equal(warm, cold)
    assert result["key"] == studio.key(studio.version(edits), verse["index"])


def test_a_stem_is_the_same_whatever_another_player_s_level_or_sound(home):
    """What the narrower keys rest on: an instrument's maker reads its own level and sound, no one else's."""
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    v = studio.version({})
    score = studio._score(v)
    t0, t1 = S.window(studio.genome, v.params, score, v.params.form, 1)
    part, _ = S.cut(score, t0, t1)
    sr, length = synth.SR, int(np.ceil(part.duration * synth.SR))
    playing = [n for n in INSTRUMENTS if part.part(n)]
    assert len(playing) >= 4
    for name in playing:
        others = {k: (v * 0.5 if k in INSTRUMENTS and k != name else v) for k, v in part.band.items()}
        sound = {"players": {o: {"pan": 0.9} for o in playing if o != name}}
        a = render_part(name, part.part(name), sr, length, part.band, v.params.seed, None)
        b = render_part(name, part.part(name), sr, length, others, v.params.seed, sound["players"].get(name))
        np.testing.assert_array_equal(a, b)
        names = [name, "voice"]
        base = keys(part, sr, v.params.seed, synth.VoiceParams(), [], names)
        moved = keys(replace(part, band=others, sound=sound), sr, v.params.seed, synth.VoiceParams(), [], names)
        assert moved == base
        own = keys(replace(part, band={**part.band, name: 0.5}, sound={"players": {name: {"pan": 0.9}}}), sr,
                   v.params.seed, synth.VoiceParams(), [], names)
        assert own[name] != base[name] and own["voice"] == base["voice"]
    voices = keys(replace(part, band={**part.band, "parts": "voices"}), sr, 1, synth.VoiceParams(), [], ["voice"])
    assert voices["voice"] != keys(part, sr, 1, synth.VoiceParams(), [], ["voice"])["voice"]


def test_a_section_ends_with_its_loop_and_says_it_again_when_it_was_made_before(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    v = studio.version({})
    score = studio._score(v)
    _, result = made(studio, {}, 1)
    loop = result["loop"]
    _, s0, s1 = S.spans(score, v.params.form)[1]
    t0, _ = S.window(studio.genome, v.params, score, v.params.form, 1)
    assert loop["start"] == pytest.approx(s0 - t0, abs=1e-3) and loop["length"] == pytest.approx(s1 - s0, abs=1e-3)
    assert 0 <= loop["head"] <= loop["start"] and loop["bars"][0] == 0.0
    steps = np.diff(loop["bars"])
    assert len(loop["bars"]) >= 4 and np.allclose(steps, steps[0], atol=0.01), loop["bars"]  # bar lines evenly apart
    assert loop["bars"][-1] < loop["length"]
    again = studio.listen({}, "you", 1)
    assert again["state"] == "done" and again["result"] == {"key": again["key"], "loop": loop}
    # a job's view names its key (the page checks it against the view's before it plays it)
    job = studio.jobs.submit("abc", "preview", "t", lambda job: {})
    assert studio.jobs.view(job)["key"] == "abc"


def test_a_single_note_is_made_as_its_maker_makes_it_the_same_every_time_and_kept_small(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    first = studio.note({}, {"player": "guitar", "pitch": 4, "velocity": 90})
    assert first["velocity"] == 96 and first["url"] == f"/audio/{first['key']}.flac"
    data = (studio.cache / f"{first['key']}.flac").read_bytes()
    y, sr = sf.read(io.BytesIO(data))
    assert sr == synth.SR and len(y) == int(S.NOTE_SECONDS * sr) and 0.3 < np.abs(y).max() <= 0.36
    assert len(data) < 200_000
    # the same note asked again, or of another studio: the same file; a velocity of the same class: the same note
    assert studio.note({}, {"player": "guitar", "pitch": 4, "velocity": 100}) == first
    other = S.Studio(None, str(LEAD), "fictional:ada", out=home / "other")
    assert (other.cache / f"{other.note({}, {'player': 'guitar', 'pitch': 4, 'velocity': 96})['key']}.flac").read_bytes() == data
    # what the guitar's maker reads changes it; another player's level doesn't
    assert studio.note({"band.guitar": 0.9}, {"player": "guitar", "pitch": 4})["key"] != first["key"]
    assert studio.note({"mix.guitar.pan": 0.7}, {"player": "guitar", "pitch": 4})["key"] != first["key"]
    assert studio.note({"band.harp": 0.9}, {"player": "guitar", "pitch": 4})["key"] == first["key"]
    assert studio.note({}, {"player": "guitar", "pitch": 5})["key"] != first["key"]
    soft = studio.note({}, {"player": "guitar", "pitch": 4, "velocity": 20})
    assert soft["velocity"] == 40 and soft["key"] != first["key"]
    hit = studio.note({}, {"player": "drum", "pitch": 1, "velocity": 120})  # a drum's piece: its place in its pieces
    assert hit["key"] != studio.note({}, {"player": "drum", "pitch": 0, "velocity": 120})["key"]
    for wrong in ({"player": "voice"}, {"player": "nobody"}, {"player": "drum", "pitch": 99}):
        with pytest.raises(ValueError):
            studio.note({}, wrong)
    assert S.answer(studio, "/api/note", {"edits": {}, "player": "guitar", "pitch": 4, "velocity": 96}) == first


def test_an_open_studio_sounds_a_note_with_the_sketch(home):
    studio = S.Studio(None, str(LEAD), "fictional:wren", out=home / "out", public=P.Limits())
    with pytest.raises(ValueError, match="sketch"):
        studio.note({}, {"player": "guitar", "pitch": 0})
    assert studio._stem_cache.budget == 64 * 2**20
    assert S.Studio(None, str(LEAD), "fictional:ada", out=home / "local")._stem_cache.budget == S.STEM_CACHE_MB * 2**20
