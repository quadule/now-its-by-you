"""A line with its own count: its words and notes kept together (docs/notes/OWN-COUNT-LINES.md)."""

import json

import pytest

from songbird import composition as C, drift as D, edits as E, harvest as H, pack
from songbird.cli import words
from songbird.genome import load, syllables
from songbird.realize import Params, choose_params, realize

from test_composition import G, SONG, ADA, DAY, sung, child_of

WORDS = "They saved it all as num-bers and sent it by wire,"  # wire's first line with "all": 12 syllables
PATH = "line.verse:wire.0"


def split(notes, i):
    """The notes with note i split in two, the second its own syllable."""
    n = notes[i]
    half = n["duration"] / 2
    return notes[:i] + [dict(n, duration=half), dict(n, onset=n["onset"] + half, duration=n["duration"] - half)] \
        + notes[i + 1:]


def twelve(params=None):
    return split(C.phrase_value(G, params or choose_params(G), "v1"), 1)


def test_a_line_sings_its_own_count_and_the_rest_of_the_song_is_unchanged():
    base = E.resolve(G, None, ADA, DAY, {})
    mine = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve(base.params)}})
    assert not mine.problems
    held = mine.params.composition
    assert set(held) == {"own"} and held["own"]["verse:wire"]["0"]["words"] == WORDS
    assert mine.params.words == base.params.words and mine.lyrics == base.lyrics  # the bank's words untouched
    score, plain = realize(G, mine.params, lyrics=mine.lyrics), realize(G, base.params, lyrics=base.lyrics)
    assert sung(score, "verse", 0)[:12] == syllables(WORDS)
    assert sung(score, "verse", 0)[12:] == sung(plain, "verse", 0)[11:]
    assert sung(score, "verse", 1) == sung(plain, "verse", 1)  # the other verses sing their tune line's 11
    assert len(score.part("voice")) == len(plain.part("voice")) + 1
    assert WORDS.replace("-", "") in pack.words_as_sung(score.to_dict())
    # the page shows the line as sung: twelve notes, each with its syllable
    verse = next(s for s in C.view(G, mine.params, mine.lyrics)["sections"] if s["name"] == "verse")
    line = verse["phrases"][0]
    assert line["syllable_count"] == 12 and [n["syllable"] for n in line["notes"]] == syllables(WORDS)
    assert line["own"] == "verse:wire.0" and line["own_path"] == PATH


def test_a_line_of_its_own_is_marked_replayed_and_kept_through_json():
    mine = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}})
    mark = mine.marks[PATH]
    assert mark["value"]["words"] == WORDS and mark["was"]["syllables"] == 11
    assert Params.from_dict(json.loads(json.dumps(mine.params.to_dict()))) == mine.params
    replay = E.resolve(G, None, ADA, DAY, E.from_record({"chosen_by_you": mine.marks}))
    assert replay.params == mine.params and not replay.problems


def test_a_line_of_its_own_goes_with_its_verse_to_a_child():
    parent = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}})
    child, lyrics, score = child_of(parent.params, "basil", "2029-03-14")
    assert child.composition["own"] == parent.params.composition["own"]
    wire = lyrics.verses.index("wire")
    assert sung(score, "verse", wire)[:12] == syllables(WORDS)


def test_without_one_nothing_changes():
    base = choose_params(G)
    assert C.form_phrases(G, base) == C.form_phrases(G, base, None)
    assert "own" not in base.composition and not C.own_places(G, base, None)


@pytest.mark.parametrize("value,why", [
    ({"words": WORDS, "notes": None}, "1 to 32"),
    ({"words": WORDS}, "its words and its notes"),
    ({"words": "They saved it as num-bers and sent it by wire,", "notes": "twelve"}, "1 to 32"),
    ("words", "its words and its notes"),
])
def test_a_line_of_its_own_is_checked_as_one(value, why):
    _, problems = E.check(G, {PATH: value})
    assert any(why in p["why"] for p in problems), problems


def test_its_words_count_against_its_own_notes():
    _, problems = E.check(G, {PATH: {"words": "They saved it as num-bers and sent it by wire,", "notes": twelve()}})
    assert any("needs 12 syllables" in p["why"] for p in problems)
    _, problems = E.check(G, {"line.verse:nowhere.0": {"words": WORDS, "notes": twelve()}})
    assert any("no verse called nowhere" in p["why"] for p in problems)


def test_a_line_written_to_the_tunes_count_takes_the_line_back():
    base = choose_params(G)
    mine = E.Overrides(G, {PATH: {"words": WORDS, "notes": twelve(base)}}).params(base)
    back = E.Overrides(G, {"lyrics.verse:wire.0": "They saved it as num-bers and sent it by wire,"}).params(mine)
    assert "own" not in back.composition and back.composition["lines"]["verse:wire"]["0"]


def test_released_it_sings_the_tune_lines_count_again():
    base = choose_params(G)
    mine = E.Overrides(G, {PATH: {"words": WORDS, "notes": twelve(base)}}).params(base)
    released = E.Overrides(G, {PATH: None}).params(mine)
    assert "own" not in released.composition
    assert released == base


def test_the_band_and_the_midi_file_hear_its_notes():
    from songbird import band, midi, variation as V

    resolved = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}})
    mine = resolved.params
    with band.overheard() as heard:
        score = V.lay(realize(G, mine, lyrics=resolved.lyrics), mine)
    verse = next(i for i, p in enumerate(heard["ctx"].phrase_ids) if p == "v1")
    s0, s1 = heard["ctx"].phrases[verse]
    kept_clear = [t for t in heard["ctx"].tune if t.phrase == "v1" and t.sung and s0 - 1e-9 <= t.u0 < s1 - 1e-9]
    assert len(kept_clear) == 11  # the band keeps clear of the notes sung: twelve, the pickup's before the bar line
    data, _ = midi.from_score(G, mine, score)
    voice = next(t for t in midi.parse(data)["tracks"] if t["name"] == "Voice")
    assert len(voice["notes"]) == len(score.part("voice"))
