"""The view of a song in clips (docs/notes/STUDIO-CLIPS.md) describes the clips: the Page's words are each clip's
own as they read, and the shape and words cards say what the clips are. A song in its own form reads as it does
without them."""

import hashlib
import json
from pathlib import Path

import pytest
from _golden import pinned

from songbird import studio as S

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-11-15"
NOTES = [{"degree": d, "onset": k, "duration": 1} for k, d in enumerate([5, 3, 2, 1])]


@pytest.fixture(scope="module")
def st(tmp_path_factory):
    return S.Studio(None, str(ROOT / "songs" / "h-now-its-by-you.json"), "none", home=tmp_path_factory.mktemp("clips-view"))


def op(st, edits, **operation):
    return S.answer(st, "/api/clips", {"edits": {"date": DAY, **edits}, **operation})


def card(view, id):
    return next(c for c in view["cards"] if c["id"] == id)


def test_a_clip_s_lines_read_as_words_and_its_source_s_keep_their_choices(st):
    made = op(st, {}, op="blank", role="verse", sung=True, bars=8, lines=2, at=1)
    edits, clip = made["edits"], made["clip"]
    edits[f"line.{clip}:0.0"] = {"words": "morn-ing bass{base} in", "notes": NOTES}
    view = st.song({"date": DAY, **edits})
    assert not view["problems"]
    assert [w["index"] for w in view["words"]] == [s["index"] for s in view["composition"]["sections"]]
    assert [w["label"] for w in view["words"]] == [s["label"] for s in view["composition"]["sections"]]
    blank = view["words"][1]
    assert blank["clip"] == clip and blank["blank"] and blank["lines"] == ["morning bass in", ""]
    assert blank["block"] is None and blank["authored"] == [0] and blank["mine"]
    assert view["composition"]["sections"][1]["phrases"][0]["lyric_text"] == "morn-ing bass{base} in"  # as written
    first = view["words"][0]
    assert first["block"] == "verse" and first["nth"] == 0 and first["changeable"], "its source's lines, as they are"


def test_the_cards_say_what_the_clips_are(st):
    own = op(st, {}, op="move", **{"from": 0, "to": 0})["edits"]  # the song's own sections, as clips
    view = st.song({"date": DAY, **own})
    labels = [s["label"] for s in view["composition"]["sections"]]
    shape = card(view, "shape")
    assert shape["value"] == f"{len(labels)} sections" and shape["detail"] == " · ".join(labels)
    assert shape["parts"] == {} and shape["choices"] == [], "the order and the parts are the clips' (Arrange)"
    assert card(view, "words")["value"] == "the song's words"
    made = op(st, {}, op="empty", role="verse", sung=True, bars=8, lines=4)
    empty, clip = made["edits"], made["clip"]
    view = st.song({"date": DAY, **empty})
    assert (card(view, "shape")["value"], card(view, "shape")["detail"]) == ("1 section", "Verse")
    assert card(view, "words")["value"] == "no words"
    view = st.song({"date": DAY, **empty, f"line.{clip}:0.0": {"words": "here we go now", "notes": NOTES}})
    assert card(view, "words")["value"] == "your own words"
    blank = op(st, own, op="blank", role="verse", sung=True, bars=8, lines=2, at=0)
    view = st.song({"date": DAY, **blank["edits"], f"line.{blank['clip']}:0.0": {"words": "here we go now", "notes": NOTES}})
    assert card(view, "words")["value"] == "the song's words, with lines of yours"
    assert not any("intro" in c["value"] or "verses" in c["value"] for c in view["cards"] if c["id"] in ("shape", "words"))


# each song's words and its shape and words cards, in its own form: as they read without clips, byte for byte, pinned
# per platform (golden/clips-own-form.<platform>.json: the view reads differently on the artist's Mac and on Linux)
OWN_FORM = [("h-now-its-by-you", None), ("h-now-its-by-you", "jazz"), ("a-nobody-knows", None),
            ("a-nobody-knows", "jazz"), ("g-hweelonalay", None), ("g-hweelonalay", "jazz")]


@pytest.mark.parametrize("song,style", OWN_FORM)
def test_a_song_in_its_own_form_reads_as_it_does_without_clips(tmp_path, song, style):
    st = S.Studio(None, str(ROOT / "songs" / f"{song}.json"), "none", home=tmp_path)
    edits = {"date": DAY, **({"form.order": None, "style": {"name": style}} if style else {})}
    view = st.song(edits)
    got = {"words": view["words"], "cards": [c for c in view["cards"] if c["id"] in ("shape", "words")]}
    pinned("clips-own-form", (song, style or "None"), hashlib.sha256(json.dumps(got, sort_keys=True).encode()).hexdigest(), None)
