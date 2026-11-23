import sys
from pathlib import Path

import pytest

pytest.importorskip("faster_whisper")
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import blend_trial as B  # noqa: E402


def note(start, word, section, word_len=1, dur=0.4, end=False):
    return {"part": "voice", "start": start, "dur": dur, "word": word, "word_len": word_len, "section": section,
            "line_end": end}


def test_the_song_is_heard_a_section_at_a_time_in_the_words_it_is_sung_to():
    score = {"notes": [
        note(0.0, "Now", "verse"), note(0.5, "it's", "verse"), note(1.0, "by{bye}", "verse"),
        note(1.5, "you-", "verse", word_len=2), note(2.0, "", "verse", word_len=0, end=True),
        note(4.0, "La", "refrain"), note(4.5, "la", "refrain"),
        note(9.0, "Now", "refrain"),  # a gap of more than three seconds: another time round
        {"part": "choir1", "start": 0.0, "dur": 1, "word": "Oh", "word_len": 1, "section": "verse"},
    ]}
    parts = B.sections(score)
    assert [(p["name"], p["words"]) for p in parts] == [
        ("verse", ["now", "it's", "by", "you"]), ("refrain", ["la", "la"]), ("refrain", ["now"])]
    assert parts[0]["from"] == 0.0 and parts[0]["to"] == pytest.approx(2.4)
    assert parts[0]["lines"] == [False, False, False, True]


def test_whisper_is_told_the_words_as_it_writes_a_lyric_down():
    assert B.written(["who", "made", "this", "song", "nobody", "knows", "i'm"], [False] * 3 + [True] + [False] * 3) == [
        (" Who", ""), (" made", ""), (" this", ""), (" song", ","), (" Nobody", ""), (" knows", ""), (" I'm", "")]
