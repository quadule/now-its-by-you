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


REFRAIN = "Who sang it, this song? No-bo-dy knows."  # r1's eight syllables and one more: "sang" split


def nine(degree=5):
    from songbird.realize import Params

    n = split(C.phrase_value(G, Params.from_dict(G.seed_params), "r1"), 1)
    n[4]["degree"], n[5]["degree"] = degree, 6 if degree == 5 else degree
    return n


def test_a_round_is_judged_on_the_lines_own_notes_and_its_voices_sing_them():
    from songbird import canon
    from songbird.realize import Params

    seed = Params.from_dict(G.seed_params)
    round_ = {"arrange.refrain:0.round": True}
    k = seed.form.index("refrain")
    plain = E.Overrides(G, round_).params(seed)
    same = E.Overrides(G, {**round_, "line.refrain:0.0": {"words": REFRAIN, "notes": nine()}}).params(seed)
    sour = E.Overrides(G, {**round_, "line.refrain:0.0": {"words": REFRAIN, "notes": nine(4)}}).params(seed)
    whole = canon.plans(G, plain)[k]
    assert canon.plans(G, same)[k] == whole  # the same tune, a syllable more: the round it was
    assert canon.plans(G, sour)[k].voices < whole.voices  # a line that rubs against the next: fewer voices
    # every voice sings the line's nine syllables
    score = realize(G, same)
    for part in ("voice", "choir1", "choir2"):
        line = [n.syllable for n in score.part(part) if n.section == "refrain"][:9]
        assert line == syllables(REFRAIN), part


def test_a_section_played_rather_than_sung_plays_the_tune_lines_notes():
    resolved = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()},
                                             "arrange.verse:0.sung": False})
    assert not resolved.problems, resolved.problems
    phrases = C.form_phrases(G, resolved.params, resolved.lyrics)
    first = next(p for p in phrases if p.id == "v1")
    assert first.own is None and len(first.sung) == 11
    # sung again, it sings its own
    sung = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}})
    assert next(p for p in C.form_phrases(G, sung.params, sung.lyrics) if p.id == "v1").own == "verse:wire.0"


def test_a_hymn_sets_its_chords_to_the_line_where_its_words_are_sung():
    from songbird import idioms

    raised = [dict(n, degree=n["degree"] + 3) if 1 <= i <= 6 else n for i, n in enumerate(twelve())]
    mine = E.resolve(G, None, ADA, DAY, {"line.verse:deaf.0": {"words": "And deaf to the wire, it went all the way "
                                                                         "to town,", "notes": raised},
                                         "style.name": "hymn"})
    assert not mine.problems and "deaf" in mine.lyrics.verses
    song = C.harmonized(G, mine.params)
    sung = idioms.chord_times(song, mine.params, mine.lyrics)
    assert idioms.chord_times(song, mine.params) == sung  # the words the version holds are the ones it sang
    assert idioms.chord_times(song, mine.params, None) != sung  # the seed's words don't sing deaf: the song's line


def test_the_trio_keeps_the_songs_chords_under_a_line_of_its_own():
    mine = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}, "style.name": "jazz"})
    v1 = [p for p in C.form_phrases(C.harmonized(G, mine.params), mine.params, mine.lyrics) if p.id == "v1"]
    assert v1[0].own and v1[0].chords == G.phrases["v1"].chords  # the trio's changes fit the song's tune, not this
    assert v1[1].chords != G.phrases["v1"].chords  # its other verses take the changes
