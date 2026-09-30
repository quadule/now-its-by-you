"""A rendition as MIDI: read back, it is the score the rendition is rendered from. Every note of every part
at the time it sounds (the tempo map follows the clock: the ending's slowing, a count-in, a waltz's re-barring),
the singer's syllables as lyrics, the chords named, the key, the bars and the sections."""

from dataclasses import replace
from pathlib import Path

import pytest

from songbird import idioms, midi, variation
from songbird.genome import load
from songbird.realize import Params, realize
from songbird.style import Style
from songbird.theory import chord_name

ROOT = Path(__file__).resolve().parents[1]
H = load(ROOT / "songs" / "h-now-its-by-you.json")
B = load(ROOT / "songs" / "b-coal-from-the-fire.json")


def score_of(genome, params):
    return variation.lay(realize(genome, params), params)


def seconds(tempos, tick):
    """A tick as seconds, through a file's tempo map."""
    out, last_tick, us = 0.0, 0, 500000
    for at, value in tempos:
        if at >= tick:
            break
        out += (at - last_tick) * us / midi.TPQ / 1e6
        last_tick, us = at, value
    return out + (tick - last_tick) * us / midi.TPQ / 1e6


def parsed(genome, params):
    score = score_of(genome, params)
    data, lead_in = midi.from_score(genome, params, score)
    read = midi.read(data)
    head = read["tracks"][0]
    tempos = [(t, int.from_bytes(e["data"], "big")) for t, e in head if e.get("meta") == 0x51]
    names = [next(e["data"].decode() for _, e in t if e.get("meta") == 0x03) for t in read["tracks"]]
    return score, read, tempos, names, lead_in


def test_every_note_is_where_it_sounds():
    params = Params.from_dict(H.seed_params)
    score, read, tempos, names, lead_in = parsed(H, params)
    assert read["format"] == 1 and read["tpq"] == midi.TPQ and lead_in <= 0
    assert names[0] == H.title and names[1] == "Voice" and names[-1] == "Chords"
    for track, name in zip(read["tracks"][1:-1], names[1:-1]):
        part = next(p for p in {n.part for n in score.notes} if midi.part_name(p) == name)
        notes = score.part(part)
        ons = [(t, e) for t, e in track if e.get("status") == 0x90]
        assert len(ons) == len(notes)
        for (tick, e), n in zip(ons, notes):
            assert abs(seconds(tempos, tick) + lead_in - n.start) < 0.004  # a tick is about a millisecond
            if part != "drum":
                assert e["args"][0] == round(n.pitch)
    assert score.duration - 0.01 < seconds(tempos, max(t for tr in read["tracks"] for t, _ in tr)) + lead_in


def test_the_words_are_lyrics_and_the_bars_the_songs():
    params = Params.from_dict(H.seed_params)
    score, read, tempos, _, lead_in = parsed(H, params)
    lyrics = "".join(e["data"].decode() for _, e in read["tracks"][1] if e.get("meta") == 0x05)
    assert lyrics.startswith("They saved it as num-bers and sent it by wire")
    assert lyrics.count(" ") + lyrics.count("-") == len(score.part("voice"))
    head = read["tracks"][0]
    assert next(e["data"] for _, e in head if e.get("meta") == 0x58)[:2] == bytes([4, 2])  # 4/4
    assert next(e["data"] for _, e in head if e.get("meta") == 0x59) == bytes([2, 0])  # D major
    markers = [(t, e["data"].decode()) for t, e in head if e.get("meta") == 0x06]
    assert [m for _, m in markers][:3] == ["Intro", "Verse 1", "Refrain 1"] and len(markers) == len(params.form)
    bar = 4 * midi.TPQ
    assert all(t % bar == 0 for t, _ in markers)  # every section starts on a bar line
    assert tempos[0] == (0, round(60e6 / params.tempo)) and tempos[-1][1] > tempos[0][1]  # it slows at the end


def test_the_chords_are_named_as_played():
    params = Params.from_dict(H.seed_params)
    _, read, _, _, _ = parsed(H, params)
    said = [e["data"].decode() for _, e in read["tracks"][-1] if e.get("meta") == 0x01]
    played = idioms.chord_times(H, params)
    assert said == [chord_name(s, params.tonic, params.mode) for _, _, s in played]
    assert said[:3] == ["Bm", "G", "D"]


def test_a_persons_key_tempo_and_mode_follow():
    params = replace(Params.from_dict(H.seed_params), tonic=57, mode="aeolian", tempo=120.0)
    score, read, tempos, _, _ = parsed(H, params)
    assert tempos[0] == (0, 500000)
    assert next(e["data"] for _, e in read["tracks"][0] if e.get("meta") == 0x59) == bytes([0, 1])  # A minor
    voice = [e["args"][0] for _, e in read["tracks"][1] if e.get("status") == 0x90]
    assert voice == [round(n.pitch) for n in score.part("voice")]


@pytest.mark.parametrize("feel", ["waltz", "swing"])
def test_a_styles_feel_keeps_the_bars(feel):
    params = replace(Params.from_dict(H.seed_params), style=Style(name="ballad", feel=feel))
    score, read, tempos, _, lead_in = parsed(H, params)
    voice = [t for t, e in read["tracks"][1] if e.get("status") == 0x90]
    assert all(abs(seconds(tempos, t) + lead_in - n.start) < 0.004 for t, n in zip(voice, score.part("voice")))
    bar = 3 * midi.TPQ if feel == "waltz" else 4 * midi.TPQ  # re-barred in three: a foot is a bar of 3/4
    assert midi.clock_map(H, params, 1.0)[1] == ((3, 4) if feel == "waltz" else (4, 4))
    assert all(t % bar == 0 for t, e in read["tracks"][0] if e.get("meta") == 0x06)


def test_a_compound_meter_and_drums_on_channel_ten():
    params = Params.from_dict(B.seed_params)
    score, read, _, names, _ = parsed(B, params)
    top, bottom = (int(x) for x in B.meter.signature.split("/"))
    assert next(e["data"] for _, e in read["tracks"][0] if e.get("meta") == 0x58)[:2] == bytes(
        [top, bottom.bit_length() - 1])
    for track, name in zip(read["tracks"][1:-1], names[1:-1]):
        channels = {e["channel"] for _, e in track if e.get("status") == 0x90}
        assert channels == ({9} if name == "Drum" else channels - {9}) and channels


def test_long_lengths_are_written_as_midi_counts_them():
    for n in (0, 1, 127, 128, 16383, 16384, 2**21 - 1, 2**27):
        track = midi.write([[(n, 0, midi.text(0x01, "x"))]])
        assert midi.read(track)["tracks"][0][0][0] == n
