"""The recording sets (tools/sets/h-now-its-by-you.json, made by tools/recording_sets.py): the file is in
the shape the guides read, every set is a song the bank's rules allow, as written and as singers hear it
with turns, and the sets hold what docs/RECORDING-SETS.md says they do. No Whisper here: what the learned
voice was heard to say worst is kept below as tools/recording_sets.py measured it on 2026-09-26."""

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import recording_sets as R  # noqa: E402  (tools/recording_sets.py)

from songbird import arrange as A  # noqa: E402
from songbird import genome as G  # noqa: E402
from songbird import variation as V  # noqa: E402

ROOT = Path(__file__).parent.parent
FILE = ROOT / "tools" / "sets" / "h-now-its-by-you.json"

# The words the voice surely says wrong (misheard nine times in ten or more, over six hearings or more) and
# the verses it gets clearly wrong (a word error rate 1.5 times the verses' median or more), as measured.
SURELY_MISHEARD = ("hummed", "put", "grow", "hum", "ink", "who'd", "low", "record", "dies", "lit", "wept", "disc",
                   "cannon", "ruined", "hiss", "counting", "rope", "grave", "woke", "belfry", "peas", "repeat",
                   "ale", "parrot", "coal")
CLEARLY_HIGH = ("trench", "screen", "milk", "kids", "hall", "ink", "probe", "lullaby", "bell", "box")


@pytest.fixture(scope="module")
def genome():
    return G.load(R.SONG)


@pytest.fixture(scope="module")
def data():
    return json.loads(FILE.read_text())


def test_the_file_is_in_the_contracts_shape(genome, data):
    assert data["song"] == "h-now-its-by-you" and data["made_by"] == "tools/recording_sets.py"
    assert data["about"].strip()
    ids = [s["id"] for s in data["sets"]]
    assert 4 <= len(ids) <= 6 and len(set(ids)) == len(ids)
    for s in data["sets"]:
        assert re.fullmatch(r"[a-z0-9]{1,8}", s["id"])
        assert s["name"] == f"Set {s['id'].upper()}"
        assert s["about"].strip()
        for name in s["form"]:
            genome.section(name)  # a section the song has
        assert "turn" not in s["form"]  # the plain form: the singer's arrangement adds the turns
        w = s["words"]
        assert set(w) == {"verses", "refrain", "bridge", "tag"} and set(w["refrain"]) == {"rounds"}
    assert ids[0] == "a"


def test_nothing_tells_singers_the_words_are_hard(data):
    for text in [data["about"]] + [s["about"] for s in data["sets"]]:
        assert not re.search(r"hard|misheard|legib|clear|difficult|wrong", text, re.I), text


def test_every_set_is_a_song_the_rules_allow_with_and_without_turns(genome, data):
    for s in data["sets"]:
        turned = R.singers_form(genome, s["form"])
        assert A.held_problem(genome, s["form"], s["words"]) is None, s["id"]
        assert A.held_problem(genome, turned, s["words"]) is None, s["id"]
        assert V.fits(genome, s["form"]), s["id"]  # one of the song's own shapes
        lyrics = A.sing(genome, turned, s["words"])
        assert [x.id for x in lyrics.sections if x.block == "verse"] == [v["id"] for v in s["words"]["verses"]]
        assert A.hold(genome, lyrics) == s["words"]  # held as hold() writes them


def test_a_turn_comes_between_every_two_sung_sections(genome):
    form = R.singers_form(genome, R.FOUR)
    sung = [bool(genome.section(n).lyrics) for n in form]
    assert not any(a and b for a, b in zip(sung, sung[1:]))
    assert form[:3] == ("intro", "verse", "turn") and form[-2:] == ("turn", "tag")
    assert "turn turn" not in " ".join(R.singers_form(genome, ("intro", "verse", "turn", "refrain")))


def test_each_set_has_three_or_four_verses_the_first_a_plain_one(genome, data):
    song = A._song(genome)
    by_id = {v.id: v for v in song.verses}
    for s in data["sets"]:
        verses = s["words"]["verses"]
        assert 3 <= len(verses) <= 4
        assert by_id[verses[0]["id"]].opens  # AABB, common, no line run on
        assert A.verse_problem(genome, verses) is None


def test_the_sets_are_balanced_about_three_and_a_half_minutes(genome, data):
    lengths = [R.seconds(genome, R.singers_form(genome, s["form"])) for s in data["sets"]]
    assert all(180 <= x <= 225 for x in lengths), lengths
    assert max(lengths) - min(lengths) < 10


def test_every_head_bridge_couplet_and_tag_is_sung(genome, data):
    heads, bridges, couplets, tags, questions = Counter(), Counter(), Counter(), Counter(), Counter()
    for s in data["sets"]:
        rounds = s["words"]["refrain"]["rounds"]
        assert rounds[0]["head"] == rounds[-1]["head"] == "knows"
        for r in rounds:
            heads[r["head"]] += 1
            couplets[r["id"]] += 1
            questions[r["words"].get("question")] += 1
        assert len({r["head"] for r in rounds[1:-1]}) == len(rounds) - 2  # varied: none twice in a set
        bridges.update(b["id"] for b in s["words"]["bridge"])
        tags[s["words"]["tag"]] += 1
    assert set(heads) == set(A.refrain_heads(genome))
    assert heads["so"] >= 2
    assert set(bridges) == {"canon", "coat", "given"}
    assert set(couplets) == set(A.couplet_ids(genome)) | {A.last_couplet(genome)}
    assert set(tags) == set(A.tag_syllables(genome))
    assert set(questions) == {"made", "sang", "heard", "kept", "wrote", "owns"}


def test_the_sets_hold_every_word_surely_misheard_and_every_verse_clearly_high(genome, data):
    have = R.coverage(genome, data["sets"])
    missing = [w for w in SURELY_MISHEARD if have[f"word:{R.word_token(w)}"] < 1]
    assert not missing, missing
    assert not [v for v in CLEARLY_HIGH if have[f"verse:{v}"] < 1]


def test_set_a_holds_the_most(genome, data):
    """Set a, which new singers get first, holds at least as many of the clearly high verses and surely
    misheard words as any other set."""
    wanted = {f"word:{R.word_token(w)}" for w in SURELY_MISHEARD} | {f"verse:{v}" for v in CLEARLY_HIGH}
    held = [len(wanted & set(R.held_targets(genome, s["words"], s["form"]))) for s in data["sets"]]
    assert held[0] == max(held), held


def test_heard_words_are_compared_as_a_listener_would():
    assert R.tokens("The 8:15 train, 10 feet tall") == ["the", "eight", "fifteen", "train", "ten", "feet", "tall"]
    assert R.tokens("by the key; it's new") == R.tokens("by the quay, its knew")
    assert R.joined(R.tokens("no body knew it, half invented"), {"nobody", "halfinvented"}) == \
        ["nobody", "new", "it", "halfinvented"]
    assert R.word_token("No-bo-dy's") == "nobodys"
    assert R._number(1916) == "nineteen sixteen" and R._number(115) == "one hundred fifteen"


def test_a_hearing_is_scored_word_by_word():
    record = {"key": "x", "seed": 1, "heard": "A kid with a camp sprayed the words",
              "words": [["A", 1], ["kid", 1], ["with", 1], ["a", 1], ["can", 1], ["sprayed", 1], ["the", 1],
                        ["words", 1]]}
    scored = R.score(record)
    assert scored["edits"] == 1
    assert [w[3] for w in scored["words"]] == ["a", "kid", "with", "a", "camp", "sprayed", "the", "words"]
