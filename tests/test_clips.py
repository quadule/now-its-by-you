"""Independent clips (docs/notes/STUDIO-CLIPS.md): a song of a person's own form, through edits alone."""

import hashlib
import json
from pathlib import Path

import pytest

from songbird import clips, composition as C, drift as D, edits as E, harvest as H, midi, stage
from songbird.genome import load
from songbird.realize import choose_params

ROOT = Path(__file__).resolve().parents[1]
G = load(ROOT / "songs/h-now-its-by-you.json")
WORDS = {"words": "here is a new song", "notes": [{"degree": 5, "onset": 0, "duration": 1},
                                                   {"degree": 6, "onset": 1, "duration": 1},
                                                   {"degree": 5, "onset": 2, "duration": 1},
                                                   {"degree": 3, "onset": 3, "duration": 1},
                                                   {"degree": 1, "onset": 4, "duration": 2}]}


def digest(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=str).encode()).hexdigest()


def version(edits, genome=G, parent=None, voice=None, drift=None):
    clean, problems = E.check(genome, edits)
    r = E.resolve(genome, parent, voice, drift, clean)
    return r, problems + r.problems


def op(edits, **operation):
    r, _ = version(edits)
    return clips.operate(G, r.params, r.lyrics, edits, operation)


def sung(r):
    score = stage.laid(G, r.params, lyrics=r.lyrics)
    return score, [n.syllable for n in score.notes if n.part == "voice"]


def new_song():
    """An entirely new song of three sections: a blank intro of 4 bars, a blank verse of 8 bars and 4 lines with
    words and notes, a blank refrain of 8 bars; the song's own sections all deleted."""
    edits = op({}, op="blank", role="intro", sung=False, bars=4, lines=1, at=0)["edits"]
    value = edits["clips"]
    edits = op(edits, op="blank", role="verse", bars=8, lines=4, at=1)["edits"]
    edits = op(edits, op="blank", role="refrain", bars=8, lines=2, at=2)["edits"]
    while len(edits["clips"]["order"]) > 3:
        edits = op(edits, op="delete", at=3)["edits"]
    intro, verse, refrain = edits["clips"]["order"]
    assert value["order"][0] == intro
    edits[f"line.{verse}:0.0"] = WORDS
    edits[f"chords.{verse}-0"] = [["I"], ["IV"]]
    edits[f"part.harp.{intro}:0.0"] = [[0, 96, 0, 100], [192, 96, 4, 90]]
    return edits, (intro, verse, refrain)


# ---------------------------------------------------------------- old records


@pytest.mark.parametrize("song,style", [("h-now-its-by-you", None), ("h-now-its-by-you", "jazz"),
                                        ("h-now-its-by-you", "house"), ("a-nobody-knows", None),
                                        ("g-hweelonalay", "jig")])
def test_a_record_without_clips_is_resolved_to_the_very_same_song(song, style):
    g = load(ROOT / f"songs/{song}.json")
    voice = H.fictional("ada")
    d = D.drift(D.parse("2026-11-01"), voice.hash)
    p = choose_params(g, None, voice, d, style=style)
    from songbird.cli import words

    lyrics = words(g, p, sung_by_a_machine=True, voice=voice, drift=d)
    got = clips.resolved(g, p, lyrics)
    assert got[0] is g and got[1] is p and got[2] is lyrics
    assert "clips" not in p.composition and "clips" not in p.to_dict().get("composition", {})
    view = C.view(g, p, lyrics)
    assert not view["clips"]["stored"] and all("clip" not in s for s in view["sections"])
    assert [c["source"] for c in view["clips"]["clips"]] == view["order"]


def test_implicit_clips_are_the_form_s_sections_and_store_nothing():
    p = E.song_params(G)
    value = clips.arrangement(p)
    assert clips.stored(p) is None
    assert value["form"] == list(p.form) and value["next"] == 101 + len(p.form)
    assert value["order"][:3] == ["intro101", "verse102", "refrain103"]
    assert value["clips"]["verse105"] == {"from": "verse:1"}
    assert clips.check(G, value) == value


# ---------------------------------------------------------------- the operations


def test_the_first_operation_stores_the_implicit_clips_and_moves_place_edits_to_them():
    edits = {"tune.refrain:last.1": None,
             "arrange.verse:1.harp.level": "hard", "transition.refrain:1": {"riser": 2}, "form.intro": True}
    out = op(edits, op="move", **{"from": 1, "to": 1})
    assert "form.intro" not in out["edits"]
    assert set(out["edits"]) == {"tune.refrain109:0.1", "arrange.verse105:0.harp.level", "transition.refrain106:0",
                                 "clips"}
    r, problems = version(out["edits"])
    assert not problems
    assert r.params.composition["arrange"] == {"verse105:0": {"players": {"harp": {"level": "hard"}}}}
    # a path naming a section of the source form is refused once the song is in clips
    r, problems = version({**out["edits"], "arrange.verse:1.harp.level": "soft"})
    assert {"path": "arrange.verse:1.harp.level", "why": "the song is in clips: name its clip, verse105"} in problems


def test_delete_any_clip_the_last_refrain_too():
    edits = op({}, op="delete", at=len(E.song_params(G).form) - 2)["edits"]  # the last refrain (the tag follows)
    assert "refrain109" not in edits["clips"]["order"] and "refrain109" not in edits["clips"]["clips"]
    r, problems = version(edits)
    assert not problems
    view = C.view(G, r.params, r.lyrics)
    assert [s["clip"] for s in view["sections"]][-2:] == ["bridge108", "tag110"]
    score, _ = sung(r)
    assert len(score.sections) == len(view["sections"])


def test_a_duplicate_is_independent_and_a_repeat_is_linked():
    edits = op({}, op="move", **{"from": 0, "to": 0})["edits"]
    edits["lyrics.verse102:0.0"] = "here is a line we wrote for you to sing now"
    out = op(edits, op="duplicate", clip="verse102")
    copy = out["clip"]
    assert copy == "verse111" and out["edits"][f"lyrics.{copy}:0.0"] == "here is a line we wrote for you to sing now"
    edits = out["edits"]
    edits[f"lyrics.{copy}:0.0"] = "the copy sings its own words, and they are all new"
    edits = op(edits, op="repeat", clip="verse102")["edits"]
    r, problems = version(edits)
    assert not problems
    view = C.view(G, r.params, r.lyrics)
    by = {}
    for s in view["sections"]:
        by.setdefault(s["clip"], []).append(s)
    assert by["verse102"][0]["phrases"][0]["lyric_text"] == "here is a line we wrote for you to sing now"
    assert by["verse102"][1]["phrases"][0]["lyric_text"] == "here is a line we wrote for you to sing now"  # the linked repeat
    assert by["verse102"][1]["label"] == "Verse 1 again"
    assert by[copy][0]["phrases"][0]["lyric_text"] == "the copy sings its own words, and they are all new"
    # a linked repeat's paths are its clip's first instance's: an edit on it edits the clip
    assert by["verse102"][1]["phrases"][1]["part_key"] == "verse102:0.1"
    assert by["verse102"][1]["phrases"][1]["place"] == "verse102:0.1"
    chords = [["IV"]] * len(by["verse102"][0]["phrases"][1]["chords"])
    r, _ = version({**edits, "chords.verse102:0.1": chords})
    view = C.view(G, r.params, r.lyrics)
    heard = [s["phrases"][1]["chords"] for s in view["sections"] if s.get("clip") in ("verse102", copy)]
    assert heard == [chords, chords, by[copy][0]["phrases"][1]["chords"]] and heard[2] != chords


def test_a_blank_clip_takes_words_notes_chords_and_parts_and_draws_no_bank_words():
    edits, (intro, verse, refrain) = new_song()
    r, problems = version(edits)
    assert not problems
    assert r.params.form == E.song_params(G).form  # the source form the bank draws for
    view = C.view(G, r.params, r.lyrics)
    assert [s["clip"] for s in view["sections"]] == [intro, verse, refrain]
    assert [s["duration_beats"] / view["beats_per_bar"] for s in view["sections"]] == [4, 8, 8]
    line = view["sections"][1]["phrases"][0]
    assert line["lyric_text"] == WORDS["words"] and line["own_path"] == f"line.{verse}:0.0"
    assert line["chords"] == [["I"], ["IV"]] and line["chords_path"] == f"chords.{verse}-0"
    assert [n["degree"] for n in line["notes"]] == [5, 6, 5, 3, 1]
    assert view["sections"][1]["phrases"][1]["notes"] == [] and view["sections"][1]["phrases"][1]["lyric_text"] == ""
    assert view["sections"][0]["phrases"][0]["part_notes"]["harp"] == edits[f"part.harp.{intro}:0.0"]
    score, words = sung(r)
    assert words == ["here", "is", "a", "new", "song"]
    harp = [n for n in score.notes if n.part == "harp" and n.section == intro]
    assert [n.pitch - r.params.tonic for n in harp] == [0, 4]  # the person's two, in place of the harp's own there
    # a line with no notes takes its words with its notes
    r, problems = version({**edits, f"lyrics.{verse}:0.1": "words alone"})
    assert problems == [{"path": f"lyrics.{verse}:0.1", "why": "this line has no notes yet; write its words with its notes"}]


def test_lines_and_length_change_within_bounds():
    edits = op({}, op="lines", clip="refrain103", lines=[{"of": 0}, {"of": 3}, {"bars": 4}])["edits"]
    r, problems = version(edits)
    assert not problems
    view = C.view(G, r.params, r.lyrics)
    refrain = next(s for s in view["sections"] if s["clip"] == "refrain103")
    assert [p["id"] for p in refrain["phrases"]] == ["r1", "r4", "refrain103-2"]
    assert refrain["phrases"][1]["lyric_text"] == next(
        s for s in C.view(G, E.song_params(G), None)["sections"] if s["id"] == "refrain:0")["phrases"][3]["lyric_text"]
    for bad, why in [([], "a clip has 1 to 16 lines"), ([{"of": 9}], "line 1's line of its section is a whole "
                                                                       "number from 0 to 3"),
                     ([{"bars": 9}], "line 1's bars is a whole number from 1 to 8")]:
        with pytest.raises(ValueError, match=why.replace("(", r"\(")):
            op({}, op="lines", clip="refrain103", lines=bad)


@pytest.mark.parametrize("change,why", [
    (lambda v: v.update(order=[]), "a song has 1 to 48 clips in its order"),
    (lambda v: v.update(order=v["order"] * 5), "a song has 1 to 48 clips in its order"),
    (lambda v: v["order"].append("verse999"), "the order names a clip the arrangement hasn't got"),
    (lambda v: v["clips"].update(verse102={"from": "refrain:0"}), "a clip from the refrain is named refrain"),
    (lambda v: v["clips"].update(verse102={"from": "verse:9"}), "which the source form hasn't got"),
    (lambda v: v["clips"].update(verse102={"role": "chorus", "sung": True, "lines": [{"bars": 2}]}),
     "a blank clip is an intro"),
    (lambda v: v["clips"].update(verse102={"role": "verse", "sung": True}), "a blank clip needs its lines"),
    (lambda v: v["clips"].update(verse102={"from": "verse:0", "role": "verse"}), "only a blank clip has a role"),
    (lambda v: v.update(form=["verse"] * 9), "the clips' source form can't be sung"),
    (lambda v: v["clips"].update(verse102={"role": "verse", "sung": True, "lines": [{"bars": 8}] * 9}),
     "a clip is at most 64 bars"),
])
def test_an_arrangement_that_can_t_be_sung_is_refused_with_why(change, why):
    value = clips.implicit(E.song_params(G).form)
    change(value)
    with pytest.raises(ValueError, match=why):
        clips.check(G, value)
    _, problems = version({"clips": value})
    assert problems and problems[0]["path"] == "clips" and why in problems[0]["why"]


def test_the_song_is_held_to_its_bars():
    value = clips.implicit(E.song_params(G).form)
    value["clips"]["verse150"] = {"role": "verse", "sung": False, "lines": [{"bars": 8}] * 8}
    value["order"] = ["verse150"] * 13
    value["next"] = 151
    with pytest.raises(ValueError, match="a song is at most 768 bars; these clips make 832"):
        clips.check(G, value)


# ---------------------------------------------------------------- one timeline


def test_a_rewritten_form_renders_the_same_twice_and_replays_from_its_record():
    edits, _ = new_song()
    first, problems = version(edits)
    assert not problems
    a = stage.laid(G, first.params, lyrics=first.lyrics).to_dict()
    second, _ = version(json.loads(json.dumps(edits)))
    assert digest(stage.laid(G, second.params, lyrics=second.lyrics).to_dict()) == digest(a)
    # the record's marks, replayed as edits (songbird render --replay), give the same parameters
    record = {"chosen_by_you": first.marks, "params": first.params.to_dict()}
    replayed, problems = version(E.from_record(json.loads(json.dumps(record))))
    assert not problems and replayed.params.to_dict() == first.params.to_dict()
    assert first.marks["clips"]["was"] == clips.implicit(first.generated.form)


def test_midi_follows_the_clips_order_and_the_view_s_clock():
    edits = op({}, op="move", **{"from": 0, "to": 3})["edits"]
    edits = op(edits, op="blank", role="break", sung=False, bars=4, lines=2, at=0)["edits"]
    r, problems = version(edits)
    assert not problems
    score = stage.laid(G, r.params, lyrics=r.lyrics)
    data, _ = midi.from_score(G, r.params, score, lyrics=r.lyrics)
    view = C.view(G, r.params, r.lyrics)
    labels = [s["label"] for s in view["sections"]]
    assert labels[:5] == ["Break", "Verse 1", "Refrain 1", "Turn 1", "Intro"]
    assert all(label.encode() in data for label in labels)
    order = [data.index(label.encode()) for label in labels[:5]]
    assert order == sorted(order)
    assert abs(view["duration_seconds"] - score.sections[-1][2]) < 1e-6


def test_a_child_keeps_the_clips_and_the_words_written_on_them():
    edits, _ = new_song()
    parent, _ = version(edits)
    voice = H.fictional("basil")
    for day in ("2026-12-01", "2027-03-01"):
        d = D.drift(D.parse(day), voice.hash)
        child = choose_params(G, parent.params, voice, d)
        assert child.composition["clips"] == parent.params.composition["clips"]
        assert child.form == parent.params.form
        from songbird.cli import words

        lyrics = words(G, child, sung_by_a_machine=True, voice=voice, drift=d)
        score = stage.laid(G, child, lyrics=lyrics)
        assert [n.syllable for n in score.notes if n.part == "voice"] == ["here", "is", "a", "new", "song"]
    # a child of the version with the song's own sections in clips: words written on a clip, whatever verses its
    # bank draws
    edits = op({}, op="move", **{"from": 0, "to": 0})["edits"]
    edits["lyrics.verse105:0.2"] = "this line stays with its clip wher-ev-er it goes"
    parent, _ = version(edits)
    d = D.drift(D.parse("2027-06-01"), voice.hash)
    child = choose_params(G, parent.params, voice, d)
    from songbird.cli import words

    view = C.view(G, child, words(G, child, sung_by_a_machine=True, voice=voice, drift=d))
    clip = next(s for s in view["sections"] if s["clip"] == "verse105")
    assert clip["phrases"][2]["lyric_text"] == "this line stays with its clip wher-ev-er it goes"


def test_the_view_says_what_each_clip_can_do():
    view = C.view(G, E.song_params(G), None)["clips"]
    assert view["clips"][0] == {**view["clips"][0], "id": "intro101", "role": "intro", "source": "intro:0",
                                "sung": False, "instances": [0], "authored": False}
    assert all(c["can"] == {"delete": True, "duplicate": True, "repeat": True} for c in view["clips"])
    edits, _ = new_song()
    while len(edits["clips"]["order"]) > 1:
        edits = op(edits, op="delete", at=1)["edits"]
    r, _ = version(edits)
    only = C.view(G, r.params, r.lyrics)["clips"]
    assert only["stored"] and only["clips"][0]["can"]["delete"] == "a song needs one clip"
    with pytest.raises(ValueError, match="a song needs one clip"):
        op(edits, op="delete", at=0)


@pytest.mark.parametrize("style", ["ballad", "jazz", "house", "hymn", "dub", "jig", "acappella"])
def test_every_style_plays_a_song_of_clips(style):
    """A style's own form (house's drop, a dub's version, the jig's rounds), a round, a build and a length of a
    clip's own, over clips duplicated, deleted and repeated."""
    edits = op({}, op="duplicate", clip="refrain103", at=0)["edits"]
    edits = op(edits, op="delete", at=len(edits["clips"]["order"]) - 2)["edits"]
    edits = op(edits, op="repeat", clip="verse102", at=3)["edits"]
    edits.update({"arrange.refrain103:0.round": True, "arrange.verse105:0.build": True,
                  "arrange.bridge108:0.bars": 8, "style.name": style})
    r, problems = version(edits)
    assert [p for p in problems if p["path"] != "style.name"] == []
    score = stage.laid(G, r.params, lyrics=r.lyrics)
    view = C.view(G, r.params, r.lyrics)
    assert [s["clip"] for s in view["sections"]] == r.params.composition["clips"]["order"]
    assert score.part("voice") or style == "dub"
    midi.from_score(G, r.params, score, lyrics=r.lyrics)


def test_the_design_note_s_new_song_is_what_the_operations_make_and_is_sung():
    """docs/notes/STUDIO-CLIPS.md, "For the editor": the worked example, as written there."""
    note = (ROOT / "docs/notes/STUDIO-CLIPS.md").read_text()
    text = note.split("it is written by hand):\n\n", 1)[1].split("\n\n## ", 1)[0]
    example = json.loads(text)
    edits, ids = new_song()
    assert example["clips"] == edits["clips"] and tuple(example["clips"]["order"]) == ids
    r, problems = version(example)
    assert not problems
    assert sung(r)[1] == ["here", "is", "a", "new", "song"]


def test_with_clips_the_shape_is_theirs_and_null_gives_the_song_its_form_back():
    edits, (_, verse, _) = new_song()
    r, problems = version({**edits, "form.verses": 3, "form.order": None})
    assert {"path": "form.verses", "why": E.CLIPPED} in problems and {"path": "form.order", "why": E.CLIPPED} in problems
    r, problems = version({**edits, "clips": None})
    assert "clips" not in r.params.composition and r.params.form == E.song_params(G).form
    assert {"path": f"line.{verse}:0.0", "why": f"there is no section called {verse}"} in problems
    score, _ = sung(r)
    assert score.sections[0][0] == "intro"


# ---------------------------------------------------------------- the editor's own operations


def test_the_view_gives_each_line_its_bars():
    edits = op({}, op="lines", clip="refrain103", lines=[{"of": 0}, {"bars": 3}])["edits"]
    r, _ = version(edits)
    view = C.view(G, r.params, r.lyrics)["clips"]
    refrain = next(c for c in view["clips"] if c["id"] == "refrain103")
    own = G.phrases[G.section("refrain").phrases[0]].bars
    assert refrain["lines"] == [{"phrase": G.section("refrain").phrases[0], "of": 0, "bars": own},
                                {"phrase": "refrain103-1", "of": None, "bars": 3}]
    assert refrain["bars"] == own + 3


def test_a_clip_takes_a_label_of_its_own_and_gives_it_back():
    edits = op({}, op="label", clip="verse102", label="  The  wire ")["edits"]
    r, problems = version(edits)
    assert not problems and edits["clips"]["clips"]["verse102"]["label"] == "The wire"
    sections = C.view(G, r.params, r.lyrics)["sections"]
    assert next(s for s in sections if s["clip"] == "verse102")["label"] == "The wire"
    edits = op(edits, op="label", clip="verse102", label="")["edits"]
    assert "label" not in edits["clips"]["clips"]["verse102"]
    blank = op({}, op="blank", role="break", sung=False, bars=2, lines=1, at=0)
    named = op(blank["edits"], op="label", clip=blank["clip"], label="Breath")["edits"]
    r, problems = version(named)
    assert not problems and C.view(G, r.params, r.lyrics)["sections"][0]["label"] == "Breath"
    with pytest.raises(ValueError, match="a clip's label is plain text of at most 24 characters"):
        op({}, op="label", clip="verse102", label="x" * 25)


def test_an_empty_song_is_one_blank_clip_the_rest_of_the_record_kept():
    edits = {"tempo": 90, "tonic": 2, "part.harp.intro:0.0": [[0, 96, 0, 100]], "arrange.verse:1.bars": 16}
    made = op(edits, op="empty", role="verse", bars=8, lines=4)
    out, clip = made["edits"], made["clip"]
    assert out["clips"]["order"] == [clip] and list(out["clips"]["clips"]) == [clip]
    assert out["clips"]["clips"][clip] == {"role": "verse", "sung": True, "lines": [{"bars": 2}] * 4}
    assert out["tempo"] == 90 and out["tonic"] == 2
    assert not any(clips.clip_of(p) for p in out if p != "clips")
    r, problems = version(out)
    assert not problems
    view = C.view(G, r.params, r.lyrics)
    assert [s["clip"] for s in view["sections"]] == [clip]
    assert all(p["notes"] == [] and p["own_path"] for p in view["sections"][0]["phrases"])


def test_an_empty_song_written_as_the_page_writes_it_is_sung_and_exported():
    """The editor's Empty song, then a line's words with the notes the page fits to a blank line (model.js blankTune:
    a syllable a beat, 3 5 4 3 1, the last held two beats) and one of its own drawn (a quarter-beat step)."""
    made = op({}, op="empty", role="verse", bars=8, lines=4)
    edits, clip = made["edits"], made["clip"]
    edits[f"line.{clip}:0.0"] = {"words": "here is a new song", "notes": [
        {"degree": d, "onset": k, "duration": 2 if k == 4 else 1} for k, d in enumerate([3, 5, 4, 3, 1])]}
    edits[f"line.{clip}:0.2"] = {"words": "and on", "notes": [{"degree": 5, "onset": 0, "duration": 0.25},
                                                                {"degree": 1, "onset": 0.25, "duration": 2}]}
    r, problems = version(edits)
    assert not problems
    score, syllables = sung(r)
    assert syllables == ["here", "is", "a", "new", "song", "and", "on"]
    assert midi.from_score(G, r.params, score, lyrics=r.lyrics)
