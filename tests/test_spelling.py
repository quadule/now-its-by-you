"""Notes and chords spelt by the key's signature (docs/history/STUDIO-EDM-TEST.md, second attempt, bug 6): C♯ minor has
G♯m, D♯° and G♯4, not A♭m, E♭° and A♭4. Every major and minor key: its seven notes on seven letters, its
signature the one its name has, its chords' roots its own notes, the page's twelve names, the MIDI file's key."""

import struct
from dataclasses import replace

import pytest

from songbird import composition as C, midi, piano
from songbird.explain import key_words
from songbird.genome import load
from songbird.realize import Params
from songbird.theory import (MODES, NOTE_NAMES, chord_name, key_signature, note_name, root_name, scale_names,
                             spelling)

from pathlib import Path

G = load(Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json")
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACC = {"": 0, "♯": 1, "♭": -1, "𝄪": 2, "𝄫": -2}
KEYS = [(t, m) for t in range(12) for m in ("ionian", "aeolian")]
# the name and signature a musician writes each key by: of its two names the one with the fewer sharps or flats
# (D♭ major's five flats, not C♯ major's seven sharps; G♯ minor's five sharps, not A♭ minor's seven flats), the
# usual name on a tie (F♯ major, E♭ minor); by the tonic's pitch class
MAJOR = {0: ("C", 0), 1: ("D♭", -5), 2: ("D", 2), 3: ("E♭", -3), 4: ("E", 4), 5: ("F", -1), 6: ("F♯", 6),
         7: ("G", 1), 8: ("A♭", -4), 9: ("A", 3), 10: ("B♭", -2), 11: ("B", 5)}
MINOR = {0: ("C", -3), 1: ("C♯", 4), 2: ("D", -1), 3: ("E♭", -6), 4: ("E", 1), 5: ("F", -4), 6: ("F♯", 3),
         7: ("G", -2), 8: ("G♯", 5), 9: ("A", 0), 10: ("B♭", -5), 11: ("B", 2)}


def pc_of(name: str) -> int:
    return (PC[name[0]] + ACC[name[1:]]) % 12


@pytest.mark.parametrize("tonic,mode", KEYS)
def test_every_major_and_minor_key_writes_its_notes_on_seven_letters(tonic, mode):
    names = scale_names(tonic, mode)
    assert names[0] == (MAJOR if mode == "ionian" else MINOR)[tonic][0]  # the name a musician writes it by
    assert [n[0] for n in names] == [("CDEFGAB" * 2)["CDEFGAB".index(names[0][0]) + d] for d in range(7)]
    assert [pc_of(n) for n in names] == [(tonic + s) % 12 for s in MODES[mode]]
    assert all(ACC[n[1:]] in (-1, 0, 1) for n in names)  # no double sharps or flats in a major or minor key
    signature = sum(ACC[n[1:]] for n in names)
    assert signature == key_signature(tonic, mode) == (MAJOR if mode == "ionian" else MINOR)[tonic][1]
    twelve = spelling(tonic, mode)
    assert [pc_of(n) for n in twelve] == list(range(12))
    for d, n in enumerate(names):  # the key's own notes as the scale has them
        assert twelve[(tonic + MODES[mode][d]) % 12] == n
    outside = [twelve[pc] for pc in range(12) if twelve[pc] not in names]  # the rest: natural, or the key's way
    assert all(len(n) == 1 or (n[1] == "♯") == (signature > 0) for n in outside) or signature == 0
    assert signature or spelling(tonic, mode) == NOTE_NAMES  # C major and A minor: the usual names
    for d, numeral in enumerate(("I", "II", "III", "IV", "V", "VI", "VII")):  # the chords' roots are the key's notes
        name = chord_name(numeral, tonic, mode)
        assert name.startswith(names[d]) and name[len(names[d]):len(names[d]) + 1] not in ("♯", "♭")
        assert root_name(numeral, tonic, mode) == names[d]
    words = key_words(tonic, mode)
    assert words.split()[0] == names[0] and midi.key_name(tonic, mode).split()[0] == names[0]
    sharps, minor = struct.unpack(">bB", midi.key_signature(tonic, mode)[-2:])
    assert (sharps, minor) == (signature, 1 if mode == "aeolian" else 0)


def test_c_sharp_minor_is_spelt_with_sharps_where_the_page_had_flats():
    assert [chord_name(s, 61, "aeolian") for s in ("i", "ii", "iii", "iv", "v", "VI", "VII")] == [
        "C♯m", "D♯°", "E", "F♯m", "G♯m", "A", "B"]
    assert chord_name("iim7b5", 61, "aeolian") == "D♯m7♭5" and chord_name("VII7sus4", 61, "aeolian") == "B7sus4"
    assert chord_name("V7/7", 61, "aeolian") == "G♯7/F♯"
    assert note_name(68, 61, "aeolian") == "G♯4" and note_name(63, 61, "aeolian") == "D♯4"
    assert note_name(59, 63, "aeolian") == "C♭4"  # E♭ minor's sixth: C♭, in the octave of its letter above B3
    assert note_name(60, 61, "ionian") == "C4" and chord_name("V", 61, "ionian") == "A♭"  # D♭ major, not C♯
    assert [n for n in spelling(61, "aeolian")] == ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"]
    assert root_name("bVII", 60, "ionian") == "B♭" and root_name("#IV", 65, "ionian") == "B"
    assert piano.ascii_spelling(61, "aeolian")[8] == "G#"


def test_a_key_past_seven_sharps_takes_its_other_name():
    assert scale_names(61, "lydian")[0] == "D♭" and key_words(61, "lydian").startswith("D♭ ")
    assert all(abs(key_signature(t, m)) <= 7 for t in range(12) for m in MODES)


def test_the_page_is_given_the_keys_names_with_the_composition():
    params = replace(Params.from_dict(G.seed_params), tonic=61, mode="aeolian")
    view = C.view(G, params, None)
    assert view["names"][8] == "G♯" and view["names"][3] == "D♯"
    roots = {r["numeral"]: r["note"] for r in C.chord_choices(params)["roots"]}
    assert roots["V"] == "G♯" and roots["II"] == "D♯" and roots["bVII"] == "B♭"
