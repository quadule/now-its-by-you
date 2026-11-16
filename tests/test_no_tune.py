"""A song with no tune, or none in places (docs/notes/STUDIO-CLIPS.md, "A blank clip"): the editor's Empty song, blank
sections among the song's own, a song only of a person's played parts, one written line, and a song without its
refrains, its verses or anything sung. In every style the studio has, each studio route the editor calls answers,
the score is the same each time it is laid, and silence renders as silence. A part that follows or answers the tune
rests where there is none (the grid says so); the style card names only what the song has a place for.

SONGBIRD_SLOW=1 renders a wider sample of sections and whole songs."""

import os
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import midi, pack, stage, studio as S, style as style_mod, synth
from songbird.score import Note, Score
from songbird.synth import master, mixing

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
DAY = "2026-11-15"
STYLES = list(style_mod.STYLES)  # the ring, those beside it and the hidden ones a record may still play
SHAPES = ("empty", "instrumental", "blank first", "blank middle", "blank last", "parts only", "one line",
          "no refrain", "no verse", "nothing sung")
SLOW = bool(os.environ.get("SONGBIRD_SLOW"))
NOTES = [{"degree": 5, "onset": 0, "duration": 1}, {"degree": 3, "onset": 1, "duration": 1},
         {"degree": 1, "onset": 2, "duration": 2}]
PLAYERS = ("guitar", "piano", "bass", "fiddle", "harp", "whistle", "strings", "synthpad", "banjo", "organ")


@pytest.fixture(scope="module")
def st(tmp_path_factory):
    return S.Studio(None, str(LEAD), "none", home=tmp_path_factory.mktemp("no-tune"))


def op(st, edits, **operation):
    return S.answer(st, "/api/clips", {"edits": {"date": DAY, **edits}, **operation})


@pytest.fixture(scope="module")
def shapes(st) -> dict:
    """Each shape's edits, made as the editor makes them (POST /api/clips)."""
    out = {}
    made = op(st, {}, op="empty", role="verse", sung=True, bars=8, lines=4)
    empty, clip = made["edits"], made["clip"]
    out["empty"] = empty
    e = op(st, {}, op="empty", role="intro", sung=False, bars=4, lines=1)["edits"]
    e = op(st, e, op="blank", role="break", sung=False, bars=8, lines=2, at=1)["edits"]
    out["instrumental"] = op(st, e, op="blank", role="outro", sung=False, bars=4, lines=1, at=2)["edits"]
    own = op(st, {}, op="move", **{"from": 0, "to": 0})["edits"]  # the song's own sections, as clips
    n = len(own["clips"]["order"])
    for where, at in (("first", 0), ("middle", n // 2), ("last", n)):
        out[f"blank {where}"] = op(st, {}, op="blank", role="verse", sung=True, bars=8, lines=4, at=at)["edits"]
    parts = dict(empty)
    for p in PLAYERS:
        parts[f"part.{p}.{clip}:0.0"] = [[0, 96, 0, 80], [96, 96, 4, 110]]
        parts[f"part.{p}.{clip}:0.2"] = [[0, 192, 2, 80]]
    parts[f"part.drum.{clip}:0.1"] = [[0, 24, 0, 100], [96, 24, 1, 60]]
    out["parts only"] = parts
    out["one line"] = {**empty, f"line.{clip}:0.1": {"words": "here we go", "notes": NOTES}}
    for label, roles in (("no refrain", ("refrain",)), ("no verse", ("verse",)),
                         ("nothing sung", ("verse", "refrain", "bridge", "tag"))):
        e = own
        while (k := next((i for i, c in enumerate(e["clips"]["order"]) if c.rstrip("0123456789") in roles),
                         None)) is not None:
            e = op(st, e, op="delete", at=k)["edits"]
        out[label] = e
    return {k: {"date": DAY, **v} for k, v in out.items()}


def test_the_shapes_are_what_they_say(st, shapes):
    for name, edits in shapes.items():
        view = st.song(edits)
        # (parts for every player the styles have: a band without one says so)
        assert all(p["path"].startswith("part.") for p in view["problems"]) if name == "parts only" \
            else not view["problems"], name
        notes = [n for s in view["composition"]["sections"] for p in s["phrases"] for n in p["notes"]]
        if name in ("empty", "instrumental", "parts only"):
            assert not notes, name
    roles = {name: {c.rstrip("0123456789") for c in e["clips"]["order"]} for name, e in shapes.items()}
    assert "refrain" not in roles["no refrain"] and "verse" not in roles["no verse"]
    assert not roles["nothing sung"] & {"verse", "refrain", "bridge", "tag"}


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("shape", SHAPES)
def test_every_route_answers_in_every_style(st, shapes, shape, style):
    """Every route for the songs with no tune at all or one line of it; for a blank section among the song's own,
    the view, the grid and the score (the other routes read the same score)."""
    edits = {**shapes[shape], "style.name": style}
    view = S.answer(st, "/api/song", {"edits": edits})
    assert S.answer(st, "/api/arrangement", {"edits": edits})
    v = st.version(edits)
    score = st._score(v)
    assert all(np.isfinite([n.start, n.dur, n.pitch, n.vel]).all() for n in score.notes)
    if shape not in ("empty", "instrumental", "parts only", "one line", "nothing sung"):
        return
    for route in ("/api/sound", "/api/players"):
        assert S.answer(st, route, {"edits": edits})
    key = view["composition"]["sections"][0]["phrases"][0]["part_key"]
    S.answer(st, "/api/notes-in", {"edits": edits, "take": {"player": "guitar", "lines": [key],
                                                            "notes": [[0.0, 1.0, 60, 90]]}})
    data, _ = midi.from_score(st.genome, v.params, score, title=st.genome.title, lyrics=v.lyrics)
    assert data[:4] == b"MThd"
    pack.words_as_sung(score.to_dict(), st.genome.title)
    assert st.render_spec(edits, "you", 0)["kind"] == "section"
    again = stage.laid(st.genome, v.params, lyrics=v.lyrics)  # the same record, the same score
    assert again.to_dict() == stage.laid(st.genome, v.params, lyrics=v.lyrics).to_dict()


# each style option a style may draw, on a song with none of its tune (each against a few styles, in turn)
OPTIONS = [{"style.ending": x} for x in ("ring", "rit", "cold", "amen", "repeat", "version")] + \
          [{"style.intro": x} for x in ("lead", "pad", "count", "voice", "quote", "air")] + \
          [{"style.backing": x} for x in ("oohs", "echo", "thirds", "gang", "hum")] + \
          [{"style.coda": "quote"}, {"style.motif": "bridge"}, {"style.lift": True}, {"style.drop": 1},
           {"style.dissolve": 1}, {"style.alone": 1}, {"style.stops": 1}, {"style.breakdown": True},
           {"style.entrances": True}, {"style.bridge": "half"}, {"style.feel": "waltz"}]


@pytest.mark.parametrize("k", range(len(OPTIONS)))
@pytest.mark.parametrize("shape", ["empty", "no refrain", "parts only"])
def test_a_style_s_options_on_a_song_without_its_tune(st, shapes, shape, k):
    for style in STYLES[k % 5::5]:
        edits = {**shapes[shape], "style.name": style, **OPTIONS[k]}
        assert S.answer(st, "/api/arrangement", {"edits": edits})
        assert S.answer(st, "/api/song", {"edits": edits})


def test_a_round_a_build_and_the_voices_before_on_blank_lines(st, shapes):
    edits = shapes["blank middle"]
    clip = next(c for c in edits["clips"]["order"] if "from" not in edits["clips"]["clips"][c])
    for style in ("ballad", "house", "hymn", "acappella"):
        for extra in ({f"arrange.{clip}:0.build": True}, {f"arrange.{clip}:0.round": True},
                      {f"transition.{clip}:0": {"riser": 2, "impact": True}}):
            mine = {**edits, "style.name": style, **extra}
            assert S.answer(st, "/api/arrangement", {"edits": mine})
            v = st.version(mine)
            stage.laid(st.genome, replace(v.params, choir=3), lyrics=v.lyrics)


def test_where_nothing_is_written_the_register_is_the_key_s_own_note(st, shapes):
    """The band's register where nothing is sung (band.Context.pitches): the section's tune, else the song's, else
    the key's note in the melody's register."""
    v = st.version({**shapes["empty"], "style.name": "chamber"})
    ctx = st._score_and_heard(v)[1]["ctx"]
    assert not ctx.tune and ctx.pitches() == [v.params.tonic] and ctx.pitches(0, sung=True) == [v.params.tonic]
    v = st.version({**shapes["blank middle"], "style.name": "chamber"})
    ctx = st._score_and_heard(v)[1]["ctx"]
    blank = next(i for i in range(len(ctx.sections)) if ctx.blank(i))
    assert ctx.pitches(blank) == ([t.pitch for t in ctx.tune_in(blank)] or [t.pitch for t in ctx.tune])  # (a pickup)
    assert ctx.pitches(1) == [t.pitch for t in ctx.tune_in(1)]


def test_a_lead_or_answers_with_no_tune_rest_and_the_grid_says_so(st, shapes):
    grid = S.answer(st, "/api/arrangement", {"edits": {**shapes["instrumental"], "style.name": "ballad"}})
    whistle = next(c for c in grid["cells"] if c["player"] == "whistle" and c["value"]["pattern"] == "lead")
    assert whistle["why"][0]["text"].endswith("; with no tune here, it rests")
    v = st.version({**shapes["instrumental"], "style.name": "ballad"})
    assert not [n for n in st._score(v).notes if n.part == "whistle"]
    grid = S.answer(st, "/api/arrangement", {"edits": {"date": DAY, "style.name": "ballad"}})  # the song's own
    assert not any("no tune here" in w["text"] for c in grid["cells"] for w in c["why"])


def test_the_style_card_names_only_what_the_song_has(st, shapes):
    def detail(edits, style):
        view = st.song({**edits, "style.name": style, "style.lift": True, "style.alone": 2})
        return next(c for c in view["cards"] if "styles" in c)["detail"]

    empty = detail(shapes["empty"], "ballad")
    assert "whole step up" not in empty and "verse 2" not in empty
    own = detail({"date": DAY}, "ballad")
    assert "the last refrain a whole step up" in own and "verse 2 sung bare" in own
    assert "echo" not in detail({**shapes["empty"], "style.backing": "echo"}, "blues")
    choir = next(c for c in st.song(shapes["empty"])["cards"] if c["id"] == "choir")
    assert "bridge" not in choir["value"]


def test_with_nothing_sung_an_amen_and_a_version_follow_the_last_bar(st, shapes):
    """sung_end, where nothing is sung, is the last bar's end: an amen's IV and I come after it (the voices sing
    it there), and a dub's version plays."""
    v = st.version({**shapes["empty"], "style.name": "gospel", "style.ending": "amen"})
    score, heard = st._score_and_heard(v)
    amen = [n for n in score.notes if n.word == "a-men"]
    assert amen and min(n.start for n in amen) >= score.sections[-1][2] - 0.05
    assert [c.symbol for c in heard["ctx"].chords[-2:]] == ["IV", "I"]
    v = st.version({**shapes["empty"], "style.name": "dub", "style.ending": "version"})
    score, heard = st._score_and_heard(v)
    assert heard["ctx"].sections[-1].role == "version"
    assert max(n.start for n in score.notes) > score.sections[-1][2] + 5.0


def test_a_section_cut_never_splits_a_word():
    word = [Note("choir1", 9.9, 1.0, 60, 0.6, "a", "a-men", 2), Note("choir1", 11.0, 1.0, 59, 0.6, "men", "a-men", 2)]
    whole = [Note("voice", 1.0, 1.0, 60, 0.8, "here", "here", 1), *word]
    part, _ = S.cut(Score(tuple(whole), 13.0, (("verse", 0.0, 10.0),)), 0.5, 10.0)
    assert [n.syllable for n in part.notes] == ["here"]
    part, _ = S.cut(Score(tuple(whole), 13.0, (("verse", 0.0, 10.0),)), 0.5, 12.5)
    assert [n.syllable for n in part.notes] == ["here", "a", "men"]


# ---------------------------------------------------------------- silence


def test_silence_mixes_and_masters_as_silence():
    sr = synth.SR
    score = Score((), 2.0, (("verse", 0.0, 2.0),))
    mix = synth.render(score, sr=sr)
    assert mix.shape == (int(np.ceil(2.0 * sr)), 2) and not mix.any()
    assert mixing.mix_made([], 100, sr).shape == (100, 2)
    out = master.master(np.zeros((sr, 2)), sr)
    assert np.isfinite(out).all() and not out.any()
    ceiling = master.CEILING_DB - master.MARGIN_DB
    limited = master.limit(master.clip(np.zeros((sr, 2)), ceiling), sr, ceiling)
    assert np.isfinite(limited).all() and not limited.any()
    assert np.abs(master.to_pcm16(limited).astype(int)).max() <= 1  # the dither alone


class _Job:
    stage = plan = url = None

    def report(self, *_):
        pass


def test_an_empty_song_a_cappella_is_a_section_of_silence(st, shapes):
    import soundfile as sf

    v = st.version({**shapes["empty"], "style.name": "acappella"})
    assert not st._score(v).notes
    made = st._section(_Job(), v, "silence", 0)
    x, _ = sf.read(str(st.cache / "silence.flac"))
    assert made["duration"] > 10 and np.isfinite(x).all() and np.abs(x).max() < 1e-3


SAMPLE = [("empty", "songwriter"), ("empty", "gospel")] + ([
    ("empty", "dub"), ("empty", "hymn"), ("empty", "old78"), ("instrumental", "ballad"), ("parts only", "house"),
    ("one line", "jig"), ("nothing sung", "acappella")] if SLOW else [])


@pytest.mark.parametrize("shape,style", SAMPLE)
def test_a_section_with_no_tune_renders(st, shapes, shape, style):
    import soundfile as sf

    v = st.version({**shapes[shape], "style.name": style})
    key = f"render-{shape.replace(' ', '-')}-{style}"
    st._section(_Job(), v, key, 0)
    x, _ = sf.read(str(st.cache / f"{key}.flac"))
    (st.cache / f"{key}.flac").unlink()
    assert np.isfinite(x).all() and 0.0 < np.abs(x).max() < 1.0


@pytest.mark.skipif(not SLOW, reason="whole songs: SONGBIRD_SLOW=1")
@pytest.mark.parametrize("style", ["acappella", "gospel", "dub", "ballad"])
def test_an_empty_song_renders_whole(st, shapes, style, tmp_path):
    import contextlib
    import io

    import soundfile as sf

    from songbird import cli

    v = st.version({**shapes["empty"], "style.name": style})
    with contextlib.redirect_stdout(io.StringIO()):
        cli.render_one(st.genome, v.params, tmp_path / "x.flac", lyrics=v.lyrics, phrasing_json=v.phrasing_json)
    x, _ = sf.read(str(tmp_path / "x.flac"))
    assert np.isfinite(x).all() and len(x) > 0


def test_machines_compared_on_an_empty_song(st, shapes):
    for style in ("ballad", "acappella", "house"):
        rows = S.answer(st, "/api/compare", {"edits": {**shapes["empty"], "style.name": style}, "names": ["bo"]})
        assert len(rows["machines"]) == 2
    rows = S.answer(st, "/api/compare", {"edits": {"date": DAY, "style.name": "acappella"}, "names": []})
    assert "the voices leading" in rows["machines"][0]["rows"].values()
