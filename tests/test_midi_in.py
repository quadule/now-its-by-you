"""A MIDI file brought back, and a take played in (docs/STUDIO.md, "Notes in"; songbird/notesin.py): the version's
own export brought back unchanged is no change at all, even saved again by a sequencer; changed, each changed line
becomes the edit a person could have made by hand (a band player's notes, the tune through its fences, the chords
in their grammar), what can't be taken is said with why, and the version made with the changes exports a file
that comes back unchanged. A take on a keyboard, likewise, line by line."""

from dataclasses import replace
from pathlib import Path

import pytest

from _midi_edit import rewrite

from songbird import composition as C, edits as E, midi, notesin, variation as V
from songbird.genome import load
from songbird.realize import Params, realize

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")


def seed():
    return Params.from_dict(G.seed_params)


def score_of(params):
    return V.lay(realize(G, params), params)


def export(params):
    return midi.from_score(G, params, score_of(params), title=G.title)[0]


def ticks_of(params, u: float) -> int:
    _, origin, step, per, _, _ = midi.tick_grid(G, params)
    return round((u - origin) / step * per)


def line(params, key):
    return next(ln for ln in notesin.layout(G, params) if ln["key"] == key)


def test_the_export_unchanged_is_no_change_even_saved_again():
    params = seed()
    data = export(params)
    for again in (data, rewrite(data), rewrite(data, tpq=960, offs_as_ons=True), rewrite(data, tpq=96)):
        r = notesin.from_file(G, params, score_of(params), again)
        assert r["changes"] == [] and r["refused"] == [] and r["unmatched"] == [] and not r["said"]


def changed_file(params):
    """The export with two chords changed (the first verse's first line: vi for its I, and IV/3 for the
    second bar's V) and the bass's line in the first line of the second verse played an octave up and slower."""
    data = export(params)
    v1 = line(params, "verse:0.0")
    bass_line = line(params, "verse:1.0")
    beat = midi.TPQ
    a, b = ticks_of(params, v1["u0"]), ticks_of(params, v1["u1"])
    w0, w1 = ticks_of(params, bass_line["w0"]) - beat // 8, ticks_of(params, bass_line["w1"]) - beat // 8
    root = params.tonic - 24

    def change(name, notes):
        if name == "Chords":
            keep = [n for n in notes if not a <= n[0] < b]
            vi = [47, 71, 74, 78]  # B under B D F#: Bm, vi in D
            one = [50, 62, 66, 69]  # D F# A: I, as it was
            iv3 = [47, 67, 71, 74]  # B under G B D: G/B, IV/3 in D
            bar = 4 * beat
            return keep + [[a, a + bar, 15, k, 64] for k in vi] + [[a + bar, a + bar + 2 * beat, 15, k, 64]
                                                                   for k in one] + \
                [[a + bar + 2 * beat, b, 15, k, 64] for k in iv3]
        if name == "Bass":
            keep = [n for n in notes if not w0 <= n[0] < w1]
            start = ticks_of(params, bass_line["u0"])
            return keep + [[start + k * 2 * beat, start + (k + 1) * 2 * beat, 1, root + 12 + step, 90]
                           for k, step in enumerate((0, 4, 7, 5))]
        return notes

    return rewrite(data, change), root


def test_two_chords_and_a_bass_line_come_back_as_edits():
    params = seed()
    data, root = changed_file(params)
    r = notesin.from_file(G, params, score_of(params), data)
    assert not r["refused"], r["refused"]
    changes = {c["path"]: c for c in r["changes"]}
    assert set(changes) == {"chords.v1", "part.bass.verse:1.0"}
    assert changes["chords.v1"]["value"] == [["vi"], ["I", "IV/3"]]  # was I | I V
    assert "Bm | D G/B" in changes["chords.v1"]["what"]
    beat = C.PPB
    assert changes["part.bass.verse:1.0"]["value"] == [[k * 2 * beat, 2 * beat, root + 12 + step - params.tonic, 90]
                                                        for k, step in enumerate((0, 4, 7, 5))]
    assert changes["part.bass.verse:1.0"]["where"] == "Verse 2, line 1"
    # applied, the version's own export comes back as no change at all
    clean, problems = E.check(G, {c["path"]: c["value"] for c in r["changes"]})
    assert not problems
    mine = E.Overrides(G, clean).params(params)
    again = notesin.from_file(G, mine, score_of(mine), export(mine))
    assert again["changes"] == [] and again["refused"] == []
    # and what it plays is what the file had
    score = score_of(mine)
    ln = line(mine, "verse:1.0")
    at = C.beat_clock(midi.tick_grid(G, mine)[0])
    heard = [n for n in score.part("bass") if at(ln["w0"]) - 0.05 <= n.start < at(ln["w1"])]
    assert [round(n.pitch) for n in heard] == [root + 12 + s for s in (0, 4, 7, 5)]


def test_the_tune_comes_back_through_its_fences():
    params = seed()
    data = export(params)
    v1 = line(params, "verse:0.0")
    a, b = ticks_of(params, v1["w0"]) - 60, ticks_of(params, v1["w1"]) - 60

    def moved(k_semitones, extra=False, chromatic=False):
        def change(name, notes):
            if name != "Voice":
                return notes
            inside = [n for n in notes if a <= n[0] < b]
            third = inside[2]
            third[3] += 1 if chromatic else k_semitones
            if extra:
                notes.append([third[0] + 10, third[0] + 30, third[2], third[3] + 2, 80])
            return notes
        return rewrite(data, change)

    r = notesin.from_file(G, params, score_of(params), moved(2))
    tune = {c["path"]: c for c in r["changes"]}
    written = C.phrase_value(G, params, "v1")
    assert set(tune) == {"tune.v1"} and "everywhere" in tune["tune.v1"]["what"]
    now = tune["tune.v1"]["value"]
    assert [n["degree"] for n in now] == [n["degree"] + (1 if i == 2 else 0) for i, n in enumerate(written)]
    assert [n["onset"] for n in now] == [n["onset"] for n in written]  # the written times, not the performed ones
    for data_, why in ((moved(0, extra=True), "needs 11 notes"),
                       (moved(0, chromatic=True), "isn't in the key's scale")):
        r = notesin.from_file(G, params, score_of(params), data_)
        assert not r["changes"] and why in r["refused"][0]["why"] and r["refused"][0]["where"].startswith("Verse 1")


def test_what_cant_be_taken_is_said():
    params = seed()
    data = export(params)
    v1 = line(params, "verse:0.0")
    a = ticks_of(params, v1["u0"])

    def seventh(name, notes):
        return notes + [[a, a + 480, 15, 72, 64]] if name == "Chords" else notes

    def ninth(name, notes):
        return notes + [[a, a + 480, 15, 72, 64], [a, a + 480, 15, 76, 64]] if name == "Chords" else notes

    def off_beat(name, notes):
        return notes + [[a + 240, a + 480, 15, 50, 64]] if name == "Chords" else notes

    def drums_and_choir(name, notes):
        if name == "Drum":
            return notes[1:]
        return notes

    r = notesin.from_file(G, params, score_of(params), rewrite(data, seventh))  # a seventh is taken: D7
    assert [c["value"] for c in r["changes"] if c["path"] == "chords.v1"][0][0][0] == "I7" and not r["refused"]
    r = notesin.from_file(G, params, score_of(params), rewrite(data, ninth))  # five notes aren't, yet
    assert "ninth chord" in r["refused"][0]["why"] and "bar 1" in r["refused"][0]["why"]
    r = notesin.from_file(G, params, score_of(params), rewrite(data, off_beat))
    assert "off the beat in bar 1" in r["refused"][0]["why"]
    r = notesin.from_file(G, params, score_of(params), rewrite(data, drums_and_choir))
    assert not r["changes"] and any("drums" in s for s in r["said"])


def test_a_file_from_another_version_or_key_is_refused_whole():
    params = seed()
    other = replace(params, form=tuple(n for n in params.form if n != "turn"))
    with pytest.raises(midi.Unreadable, match="another version"):
        notesin.from_file(G, params, score_of(params), export(other))
    with pytest.raises(midi.Unreadable, match="key"):
        notesin.from_file(G, params, score_of(params), export(replace(params, tonic=params.tonic + 2)))
    with pytest.raises(midi.Unreadable):
        notesin.from_file(G, params, score_of(params), b"MThd nonsense")


def test_a_track_it_cant_name_is_asked_about_then_taken():
    params = seed()
    data, _ = changed_file(params)
    renamed = data.replace(b"Bass", b"Bs 1")  # a sequencer's own name for the track
    r = notesin.from_file(G, params, score_of(params), renamed)
    assert [c["path"] for c in r["changes"]] == ["chords.v1"]
    assert r["unmatched"] and r["unmatched"][0]["name"] == "Bs 1" and "Bass" in r["tracks"]
    told = notesin.from_file(G, params, score_of(params), renamed, {r["unmatched"][0]["track"]: "Bass"})
    assert {c["path"] for c in told["changes"]} == {"chords.v1", "part.bass.verse:1.0"}
    left = notesin.from_file(G, params, score_of(params), renamed, {r["unmatched"][0]["track"]: ""})
    assert not left["unmatched"]


def test_a_chord_is_named_as_the_grammar_writes_it():
    name = lambda ps, mode="ionian": notesin.name_chord(ps, 62, mode)  # noqa: E731  in D
    assert name([62, 66, 69]) == "I" and name([59, 62, 66]) == "vi" and name([66, 69, 74]) == "I/3"
    assert name([57, 61, 64]) == "V" and name([60, 64, 67]) == "bVII"  # A; C, borrowed
    assert name([57, 61, 64], "aeolian") == "Vmaj"  # a dominant in a minor song
    assert name([62, 64, 69]) == "Isus2" and name([57, 62, 64]) == "Vsus4"
    # four notes: a seventh, a sixth, an added ninth, the seventh in the bass; the root in the bass named first
    assert name([62, 66, 69, 72]) == "I7" and name([61, 62, 66, 69]) == "Imaj7/7" and name([62, 66, 69, 73]) == "Imaj7"
    assert name([59, 62, 66, 69]) == "vim7" and name([62, 66, 69, 71]) == "I6" and name([62, 64, 66, 69]) == "Iadd9"
    assert name([55, 61, 64, 69]) == "V7/7" and name([61, 64, 67, 71]) == "viim7b5"
    assert name([57, 61, 64, 67], "aeolian") == "V7"  # the dominant seventh in a minor song
    for pitches, why in (([62, 66, 69, 72, 76], "ninth chord"), ([62, 69], "three"), ([], "no chord"),
                         ([62, 63, 66, 69], "a seventh .* a sixth"), ([60, 62, 66], "isn't a major")):
        with pytest.raises(ValueError, match=why):
            name(pitches)


# ---------------------------------------------------------------- a take played along with the sketch


def test_a_take_becomes_a_part_line_by_line_and_rests_where_nothing_was_played():
    params = seed()
    lines = [ln for ln in notesin.layout(G, params) if ln["sid"] == "verse:0"]
    beat = G.meter.beat
    start = lines[0]["u0"] / beat  # in the page's beats, from the song's first pickup
    notes = [[start - 0.5, 0.5, params.tonic + 4, 70], [start, 1.02, params.tonic + 7, 96],
             [start + 1.97, 2, params.tonic + 9, 88]]  # a pickup, then two a little off the beat
    r = notesin.take(G, params, "fiddle", notes, [ln["key"] for ln in lines])
    assert not r["refused"]
    got = {c["path"]: c["value"] for c in r["changes"]}
    assert got["part.fiddle.verse:0.0"] == [[-48, 48, 4, 70], [0, 98, 7, 96], [189, 192, 9, 88]]
    assert got["part.fiddle.verse:0.1"] == got["part.fiddle.verse:0.2"] == got["part.fiddle.verse:0.3"] == []
    too_low = notesin.take(G, params, "fiddle", [[start, 1, 30, 90]], [lines[0]["key"]])
    assert "outside what the fiddle plays" in too_low["refused"][0]["why"]
    with pytest.raises(ValueError):
        notesin.take(G, params, "drum", notes, [lines[0]["key"]])
    with pytest.raises(ValueError):
        notesin.take(G, params, "fiddle", notes, ["verse:9.0"])


def test_a_take_on_the_tune_keeps_its_fences():
    params = seed()
    ln = line(params, "verse:0.0")
    beat = G.meter.beat
    written = C.phrase_value(G, params, "v1")
    sung = [[ln["u0"] / beat + n["onset"], n["duration"], params.tonic + C.degree_semitones(n["degree"], params.mode),
             90] for n in written]
    sung[3][2] = params.tonic + C.degree_semitones(written[3]["degree"] + 1, params.mode)
    r = notesin.take(G, params, "voice", sung, [ln["key"]])
    assert [c["path"] for c in r["changes"]] == ["tune.v1"]
    assert r["changes"][0]["value"][3]["degree"] == written[3]["degree"] + 1
    r = notesin.take(G, params, "voice", sung[:-2], [ln["key"]])
    assert not r["changes"] and "needs 11 notes" in r["refused"][0]["why"]
