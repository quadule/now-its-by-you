"""The view of a song in clips (docs/notes/STUDIO-CLIPS.md) describes the clips: the Page's words are each clip's
own as they read. A song in its own form reads as it does without them."""

import hashlib
import json
from pathlib import Path

import pytest

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


# each song's words and its shape and words cards, in its own form: as they read without clips, byte for byte
OWN_FORM = {
    ("h-now-its-by-you", None): "6b479741b672aff8da93013c255b79931e4b9fa62b32c2f6db657c8c247e1f05",
    ("h-now-its-by-you", "jazz"): "24a03685797e7c2a53e1929b4858b9826b3186214939ae0b32b7bf10c00c586e",
    ("a-nobody-knows", None): "61b203cd1e4524ea24bb4cc21244bcfc725d5e5d4d6e6b341232a23b297117a0",
    ("a-nobody-knows", "jazz"): "2572798abb0a13f1c1031d18e45cbd292079f52296c6211f2fb157d084b57a52",
    ("g-hweelonalay", None): "16448faec2698a5e90706e605cd37739a86c74f19c98d87dbce490a6678a2f88",
    ("g-hweelonalay", "jazz"): "d4389604291be9b2f2c36b2e4a3fd10c6e0b80fe7ec465e18009d301632a1ac2",
}


@pytest.mark.parametrize("song,style", list(OWN_FORM))
def test_a_song_in_its_own_form_reads_as_it_does_without_clips(tmp_path, song, style):
    st = S.Studio(None, str(ROOT / "songs" / f"{song}.json"), "none", home=tmp_path)
    edits = {"date": DAY, **({"form.order": None, "style": {"name": style}} if style else {})}
    view = st.song(edits)
    got = {"words": view["words"], "cards": [c for c in view["cards"] if c["id"] in ("shape", "words")]}
    assert hashlib.sha256(json.dumps(got, sort_keys=True).encode()).hexdigest() == OWN_FORM[(song, style)]
