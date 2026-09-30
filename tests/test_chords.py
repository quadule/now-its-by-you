"""A person's chords (docs/STUDIO.md, "Changing the chords"): a tune line's chords changed bar by bar, with a
quality and a bass if named. With none, nothing changes (the same song, byte for byte; the goldens say so too).
Checked whole and refused with why; everything that sounds from the chords follows (the band, the bass on an
inversion's bass note, the choir's harmony, the MIDI file), the melody doesn't; a note against the new chord is
allowed and shown; marked in the record with what the program had, made again from it, and handed down."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from songbird import composition as C, drift as D, edits as E, harvest as H, idioms, variation as V
from songbird.genome import load
from songbird.realize import Params, choose_params, realize
from songbird.theory import chord_bass, chord_name, chord_tones, parse_chord, parse_symbol

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-26"), ADA.hash)
MINE = {"chords.v1": [["vi"], ["IV/3", "Vsus4"]]}  # was I | I V


def seed():
    return Params.from_dict(G.seed_params)


def score_of(params):
    return V.lay(realize(G, params), params)


def test_a_chord_names_a_quality_and_a_bass_and_a_plain_numeral_means_what_it_did():
    assert parse_symbol("vi") == (6, 0, "", 1) and parse_chord("Vmaj/3") == (5, 0)
    assert chord_tones("v", "aeolian") == (7, 10, 14)  # the mode's own: minor
    assert chord_tones("Vmaj", "aeolian") == (7, 11, 14)  # a dominant in a minor song
    assert chord_tones("ivm", "ionian") == (5, 8, 12) and chord_tones("IVsus4", "ionian") == (5, 10, 12)
    assert chord_tones("bVIImaj", "ionian") == chord_tones("bVII", "ionian") == (10, 14, 17)
    assert chord_bass("I/3", "ionian") == 4 and chord_bass("V/5", "ionian") == 14 and chord_bass("vi", "ionian") == 9
    assert [chord_name(s, 62, "ionian") for s in ("I/3", "viidim", "Vsus4", "bVII", "iiim")] == [
        "D/F♯", "C♯°", "Asus4", "C", "F♯m"]
    for bad in ("IM", "Vmin", "V7", "I/4", "VIII", "V/V"):  # case never carries a quality; no sevenths yet
        with pytest.raises(ValueError):
            parse_symbol(bad)


def test_no_chords_changed_is_the_same_song():
    params = seed()
    assert C.harmonized(G, params) is G
    same = C.harmonized(G, replace(params, composition={"chords": MINE_BARS()}))
    assert same is C.harmonized(G, replace(params, composition={"chords": MINE_BARS()}))  # made once, kept
    assert choose_params(G, None, ADA, DAY, overrides={}) == choose_params(G, None, ADA, DAY)


def MINE_BARS():
    return {"v1": [list(b) for b in MINE["chords.v1"]]}


def test_chords_are_checked_whole_and_refused_with_why():
    clean, problems = E.check(G, {**MINE, "chords.v2": [["I"]], "chords.nope": [["I"]],
                                  "chords.v3": [["I"], ["IV", "V", "I"]], "chords.r1": [["I"], ["V7"]],
                                  "chords.r2": "I V"})
    assert clean == MINE
    why = {p["path"]: p["why"] for p in problems}
    assert why["chords.v2"] == "this line is 2 bars long: give chords for each"
    assert why["chords.nope"] == "there is no tune line called nope"
    assert "1, 2 or 4 chords" in why["chords.v3"] and "'V7' isn't a chord" in why["chords.r1"]
    assert "chords.r2" in why
    assert E.check(G, {"chords.v1": None}) == ({"chords.v1": None}, [])


def test_the_band_and_the_voices_follow_the_melody_doesnt():
    plain = seed()
    mine = E.Overrides(G, MINE).params(plain)
    assert mine.composition == {"chords": MINE_BARS()}
    before, after = score_of(plain), score_of(mine)
    assert [(n.start, n.pitch) for n in before.part("voice")] == [(n.start, n.pitch) for n in after.part("voice")]
    assert [n.pitch for n in before.part("bass")] != [n.pitch for n in after.part("bass")]
    # every chord the MIDI file names is the person's where they chose, the song's elsewhere
    names = [chord_name(s, plain.tonic, plain.mode) for _, _, s in idioms.chord_times(C.harmonized(G, mine), mine)]
    assert "Bm" in names and "G/B" in names and "Asus4" in names
    # the bass takes an inversion's bass note: G/B puts a B under the band where the song had I (D)
    spans = [(a, z, s) for a, z, s in idioms.chord_times(C.harmonized(G, mine), mine) if s == "IV/3"]
    firsts = [next((n for n in after.part("bass") if a - 0.05 <= n.start < z - 0.05), None) for a, z, _ in spans]
    firsts = [n for n in firsts if n is not None]  # where the bass plays (not in the first verse)
    assert firsts and all(round(n.pitch) % 12 == (plain.tonic + 5 + 4) % 12 for n in firsts)  # B, the third of G


def test_the_choir_sings_the_new_chords_tones():
    plain = replace(seed(), choir=2)
    mine = E.Overrides(G, {"chords.b1": [["IV"], ["bVII"]]}).params(plain)  # the bridge, where the choir sings
    score = score_of(mine)
    for symbol in ("IV", "bVII"):
        tones = {(mine.tonic + t) % 12 for t in chord_tones(symbol, mine.mode)}
        spans = [(a, z) for a, z, s in idioms.chord_times(C.harmonized(G, mine), mine) if s == symbol]
        sung = [n for n in score.notes if n.part.startswith("choir") and any(a - 0.3 <= n.start < z - 0.3 for a, z in spans)
                and not any(z - 0.3 <= n.start < z for a, z in spans)]
        assert sung and all(round(n.pitch) % 12 in tones for n in sung), symbol


def test_a_note_against_the_new_chord_is_allowed_and_shown():
    mine = E.Overrides(G, MINE).params(seed())
    view = C.view(G, mine, None)
    v1 = next(p for s in view["sections"] for p in s["phrases"] if p["id"] == "v1")
    assert v1["chords_edited"] and v1["song_chords"] == [["I"], ["I", "V"]] and v1["chords"] == MINE["chords.v1"]
    assert [h["name"] for h in v1["harmony"]] == ["Bm", "G/B", "Asus4"]
    for h in v1["harmony"]:
        pcs = set(h["pcs"])
        assert all(round(v1["notes"][i]["pitch"]) % 12 not in pcs for i in h["rubs"])
        assert all(round(n["pitch"]) % 12 in pcs for i, n in enumerate(v1["notes"])
                   if i not in h["rubs"] and h["start"] <= max(n["onset"], 0) < h["start"] + h["beats"])
    assert any(h["hard"] for h in v1["harmony"])
    assert view["edited_chords"] == ["v1"] and view["chords_per_bar"] == [1, 2, 4]


def test_marked_as_yours_made_again_from_the_record_and_handed_down():
    r = E.resolve(G, None, ADA, DAY, dict(MINE))
    assert "chords.v1" in r.applied and not r.problems
    assert r.marks["chords.v1"] == {"value": MINE["chords.v1"], "was": [["I"], ["I", "V"]]}
    record = {"params": r.params.to_dict(), "chosen_by_you": r.marks}
    again = E.resolve(G, None, ADA, DAY, E.from_record(json.loads(json.dumps(record))))
    assert again.params == r.params
    child = choose_params(G, Params.from_dict(json.loads(json.dumps(r.params.to_dict()))), H.fictional("basil"), DAY)
    assert child.composition.get("chords") == MINE_BARS()  # a person's chords pass on, as a person's melody does
    released = E.resolve(G, child, None, None, {"chords.v1": None})
    assert "chords" not in released.params.composition and released.marks["chords.v1"]["was"] == MINE["chords.v1"]
