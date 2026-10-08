"""tools/throat/folk.py: labelling recordings that have no score (dev tool), and dataset.py's bands."""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "throat"))

import dataset  # noqa: E402
import folk  # noqa: E402
from features import grid  # noqa: E402


def test_a_dropped_g_is_read_as_the_ing_word_ending_in_n():
    assert folk.reading("rolling")[-1] == "NG"
    assert folk.reading("rollin'") == folk.reading("rolling")[:-1] + ["N"]
    assert folk.reading("qzxv") is None


def test_a_diphthongs_er_is_sung_in_one_syllable_with_it():
    assert folk.reading("fire")[-2:] == ["AY1", "R"]  # not fi-er: the program sings it AYR on one note
    assert folk.reading("hour") == ["AW1", "R"]
    assert folk.reading("tired") == ["T", "AY1", "R", "D"]
    assert folk.reading("flower")[-2:] == ["AW1", "R"]
    assert folk.reading("mother")[-1] == "ER0"  # not after a diphthong: as it is


def test_a_word_heard_differently_between_matching_neighbours_is_taken_as_printed():
    heard = [dict(word=w, start=i, end=i + 0.5, p=0.9 if w != "shanandoah" else 0.2)
             for i, w in enumerate(["Oh", "shanandoah,", "I", "long", "to", "see", "you"])]
    out = folk.corrected(heard, "Oh Shenandoah, I long to see you")
    assert out[1]["word"] == "shenandoah" and out[1]["heard"] == "shanandoah," and out[1]["p"] >= 0.6
    assert all(w.get("printed") for w in out)
    assert folk.corrected(heard, None) is heard  # no printed words: Whisper's stand


def test_lines_end_at_pauses_in_the_audio_not_at_whispers_gaps():
    words = [dict(word=w, start=s, end=e, p=0.9) for w, s, e in
             [("one", 0.5, 0.8), ("two", 1.4, 1.7), ("three", 3.0, 3.3), ("four", 3.5, 3.8)]]
    # Whisper leaves a gap after "one" (a held note) but the voice goes on; the real pause is 2.4-2.9 s
    pauses = [(2.4, 2.9)]
    level = np.full(1000, -20.0)
    lines = folk.lines_from(words, pauses, level, 5.0)
    assert [[w["word"] for w in ln] for ln, _, _ in lines] == [["one", "two"], ["three", "four"]]
    (_, t0a, t1a), (_, t0b, t1b) = lines
    assert t0a == 0.25 and 2.4 < t1a <= 2.65 and 2.65 <= t0b < 2.9 and t1b <= 5.0


def test_a_band_keeps_the_grid_points_below_it():
    assert dataset.top(None, 128) == 128
    assert dataset.top(4000.0, 128) == int(np.sum(grid(128) <= 4000.0))
    assert 0 < dataset.top(4000.0, 128) < 128 and dataset.top(0, 32) == 0


def test_italian_and_latin_are_read_by_their_spelling_with_pure_vowels():
    assert folk.reading("languisce", "it") == ["L", "AA0", "N", "G", "W", "IY1", "SH", "EH0"]
    assert folk.reading("ben", "it") == ["B", "EH1", "N"]  # a word ending in a consonant: stressed last
    assert folk.reading("mio", "it") == ["M", "Y", "AO1"]  # one syllable on one note, as the aria sets it
    assert folk.reading("pacem", "la") == ["P", "AA1", "CH", "EH0", "M"]
    assert folk.reading("Jesu", "la")[0] == "Y"
    assert not any(p.startswith(("EY", "OW")) for p in folk.reading("credimi", "it") + folk.reading("dona", "la"))


def test_an_exercise_is_cut_into_notes_where_its_pitch_steps():
    # a scale, 60 62 64 at 0.4 s a note, with a 5.5 Hz vibrato of half a semitone on top
    t = np.arange(240) * folk.FRAME
    midi = np.repeat([60.0, 62.0, 64.0], 80) + 0.5 * np.sin(2 * np.pi * 5.5 * t)
    spans = folk.steps(midi)
    assert len(spans) == 3
    assert all(abs(a - b) <= 12 for (a, _), b in zip(spans, (0, 80, 160)))
