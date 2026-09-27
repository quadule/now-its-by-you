import pytest

from songbird.theory import chord_tones, degree_semitones, harmony, parse_chord


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


def test_harmony_takes_chord_tones_around_the_melody():
    d = 62  # D major; the melody's B over vi (B D F#)
    assert harmony(71, "vi", d, "ionian", 0) == 66  # F# below
    assert harmony(71, "vi", d, "ionian", 1) == 74  # D above
    assert harmony(71, "vi", d, "ionian", 2) == 59  # the root, B, beneath
    assert harmony(71, "vi", d, "ionian", 3) == 54  # role 0 an octave down
    # a passing tone still gets a chord tone: E over I lands on A below
    assert harmony(64, "I", d, "ionian", 0) == 57


def test_a_choir_voice_led_from_where_it_was_holds_what_the_next_chord_shares():
    d = 62
    assert harmony(71, "I", d, "ionian", 0) == 66  # alone: the chord tone nearest the melody
    assert harmony(71, "I", d, "ionian", 0, previous=62) == 62  # led: it stays on D, a tone of this chord too
    assert harmony(71, "I", d, "ionian", 2) == 62
    assert harmony(71, "I", d, "ionian", 2, previous=50) == 50  # the root holds low rather than leap up an octave
    assert harmony(57, "I", d, "ionian", 2, previous=38) == 50  # but never below a bass's E2
