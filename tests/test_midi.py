"""A rendition as MIDI: read back, it is the score the rendition is rendered from. Every note of every part
at the time it sounds (the tempo map follows the clock: the ending's slowing, a count-in, a waltz's re-barring),
the singer's syllables as lyrics, the chords named, the key, the bars and the sections."""

import random
import time
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


# ---------------------------------------------------------------- reading any file back (notes in)


def test_parse_reads_the_export_as_written():
    params = Params.from_dict(H.seed_params)
    score = score_of(H, params)
    data, _ = midi.from_score(H, params, score)
    read = midi.parse(data)
    assert read["format"] == 1 and read["tpq"] == midi.TPQ
    by_name = {t["name"]: t for t in read["tracks"]}
    for part in {n.part for n in score.notes}:
        notes = by_name[midi.part_name(part)]["notes"]
        assert len(notes) == len(score.part(part))
    voice = by_name["Voice"]["notes"]
    assert [k for _, _, _, k, _ in voice] == [round(n.pitch) for n in score.part("voice")]
    assert all(off > on for on, off, *_ in voice)
    markers = [t for _, kind, t in read["tracks"][0]["texts"] if kind == 0x06]
    assert markers[:2] == ["Intro", "Verse 1"]
    assert read["tracks"][0]["tempos"][0] == (0, round(60e6 / params.tempo))


def test_parse_pairs_notes_as_sequencers_do():
    """Running status, a note-on at velocity 0 as its end, the same key struck twice before either ends (the
    first struck ends first), a note never ended (it ends with its track), an alien chunk passed over."""
    body = (midi.vlq(0) + bytes([0x90, 60, 100]) + midi.vlq(10) + bytes([60, 90])  # running status: struck again
            + midi.vlq(10) + bytes([60, 0]) + midi.vlq(10) + bytes([0x80, 60, 0])  # both end
            + midi.vlq(0) + bytes([0x91, 64, 80]) + midi.vlq(5) + midi.meta(0x2F, b""))
    track = b"MTrk" + len(body).to_bytes(4, "big") + body
    alien = b"XFIH" + (3).to_bytes(4, "big") + b"abc"
    data = HEAD(1) + alien + track
    notes = midi.parse(data)["tracks"][0]["notes"]
    assert notes == [(0, 20, 0, 60, 100), (10, 30, 0, 60, 90), (30, 35, 1, 64, 80)]


def HEAD(tracks: int, fmt: int = 1, division: int = 480) -> bytes:
    return b"MThd" + (6).to_bytes(4, "big") + fmt.to_bytes(2, "big") + tracks.to_bytes(2, "big") + division.to_bytes(2, "big")


def TRACK(body: bytes, length: int | None = None) -> bytes:
    return b"MTrk" + (len(body) if length is None else length).to_bytes(4, "big") + body


@pytest.mark.parametrize("data, why", [
    (b"", "isn't a Standard MIDI File"),
    (b"RIFF" + bytes(20), "isn't a Standard MIDI File"),
    (HEAD(1, fmt=2), "format 2"),
    (HEAD(1, division=0xE728), "frames"),
    (HEAD(256), "256 tracks"),
    (HEAD(2) + TRACK(bytes([0, 0xFF, 0x2F, 0])), "holds 1"),
    (HEAD(1) + TRACK(bytes(4), length=99), "cut short"),
    (HEAD(1) + TRACK(bytes([0xFF, 0xFF, 0xFF, 0xFF, 0x7F])), "longer than four bytes"),
    (HEAD(1) + TRACK(bytes([0, 60, 100])), "no status"),
    (HEAD(1) + TRACK(bytes([0, 0xFF, 0x01, 0x40, 65])), "longer than its track"),
    (HEAD(1) + TRACK(bytes([0, 0xF8])), "doesn't belong"),
    (HEAD(1) + TRACK(bytes([0, 0x90, 60, 200])), "out of range"),
])
def test_parse_refuses_with_why(data, why):
    with pytest.raises(midi.Unreadable, match=why):
        midi.parse(data)


def test_parse_holds_its_limits():
    with pytest.raises(midi.Unreadable, match="bigger"):
        midi.parse(HEAD(1) + bytes(midi.MAX_FILE))
    many = bytes([0, 0xC0, 1]) + bytes([0, 1]) * midi.MAX_EVENTS  # small events (running status), each counted
    with pytest.raises(midi.Unreadable, match="events"):
        midi.parse(HEAD(1) + TRACK(many))
    far = (midi.vlq(2**27) + bytes([0xC0, 1])) * 3
    with pytest.raises(midi.Unreadable, match="longer than a song"):
        midi.parse(HEAD(1) + TRACK(far))
    struck = bytes([0, 0x90, 60, 100]) + bytes([0, 60, 100]) * 39999 + bytes([1, 60, 0]) * 40000
    began = time.perf_counter()  # one key struck 40,000 times, then ended as often: linear, not quadratic
    assert len(midi.parse(HEAD(1) + TRACK(struck))["tracks"][0]["notes"]) == 40000
    assert time.perf_counter() - began < 2


def test_parse_of_damaged_files_says_why_and_only_that():
    """Fuzz: thousands of exports damaged at random (bytes changed, cut short, lengths lied about) are read or
    refused as Unreadable, never anything else, and quickly."""
    params = Params.from_dict(H.seed_params)
    data, _ = midi.from_score(H, params, score_of(H, params))
    rng = random.Random(7)
    began, read = time.perf_counter(), 0
    for _ in range(2000):
        b = bytearray(data)
        for _ in range(rng.randint(1, 12)):
            b[rng.randrange(len(b))] = rng.randrange(256)
        if rng.random() < 0.3:
            b = b[:rng.randrange(len(b))]
        if rng.random() < 0.2:  # a track's length made a lie
            at = b.find(b"MTrk", rng.randrange(max(1, len(b))))
            if at >= 0:
                b[at + 4:at + 8] = rng.randrange(2**32).to_bytes(4, "big")
        try:
            midi.parse(bytes(b))
            read += 1
        except midi.Unreadable:
            pass
    assert time.perf_counter() - began < 20
    assert read  # some damage leaves a readable file (a changed velocity, a changed key)
