import pytest

from songbird.theory import chord_tones, degree_semitones, parse_chord


def test_degrees_wrap_octaves():
    assert degree_semitones(1, "ionian") == 0
    assert degree_semitones(8, "ionian") == 12
    assert degree_semitones(0, "ionian") == -1  # leading tone below
    assert degree_semitones(-2, "dorian") == -5  # the fifth below
    assert degree_semitones(3, "dorian") == 3
    assert degree_semitones(7, "mixolydian") == 10
    assert degree_semitones(4, "lydian", alter=-1) == 5


def test_chord_quality_comes_from_the_mode():
    assert chord_tones("IV", "ionian") == (5, 9, 12)  # major
    assert chord_tones("iv", "dorian") == (5, 9, 12)  # the dorian major IV
    assert chord_tones("v", "mixolydian") == (7, 10, 14)  # minor v
    assert chord_tones("bVII", "ionian") == (10, 14, 17)  # borrowed, major


def test_bad_chord_raises():
    assert parse_chord("vii") == (7, 0)
    with pytest.raises(ValueError):
        parse_chord("X")
