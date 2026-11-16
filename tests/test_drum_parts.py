"""Written drum parts (docs/STUDIO.md, "Drum parts"): a percussion player's strokes in one line of the form, kept as
part.<player>.<line> notes whose pitch is a piece of that player's (composition.DRUM_PIECES). Checked whole and
refused with why; each piece is a stroke its synth plays; the program's strokes come back as pieces for the editor;
written strokes replace the player's own in their lines and nowhere else; with none, the same song; deterministic;
in the MIDI file on channel 10; handed down."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import composition as C
from songbird import drift as D
from songbird import edits as E
from songbird import harvest as H
from songbird import midi, notesin
from songbird import studio as S
from songbird.genome import load
from songbird.realize import Params, choose_params, realize, timeline
from songbird.score import Score
from songbird.synth import drum as frame_drum
from songbird.synth import instruments

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-27"), ADA.hash)
KIT = {name: k for k, (name, _) in enumerate(C.DRUM_PIECES["kit"])}
# a bar of the kit in the first line of the first verse: kick and hat, snare and hat, a brush's sweep held a beat
BAR = [[0, 24, KIT["kick"], 100], [0, 24, KIT["hat"], 70], [96, 24, KIT["snare"], 90], [96, 24, KIT["hat"], 70],
       [192, 24, KIT["kick"], 100], [288, 96, KIT["brush-sweep"], 60]]


def country():
    return choose_params(G, None, ADA, DAY, style="country")


def with_edits(edits, params):
    clean, problems = E.check(G, edits)
    assert not problems, problems
    return E.Overrides(G, clean).params(params)


def window(params, key):
    """A line's window (seconds, its pickup to the next line's) and first bar line, on the rendition's clock."""
    clock = timeline(G, params)
    line = next(ln for ln in notesin.layout(G, params) if ln["key"] == key)
    at = C.beat_clock(clock)
    return at(line["w0"]), at(line["w1"]), at(line["u0"])


def score_hash(params) -> str:
    return hashlib.sha256(json.dumps(realize(G, params).to_dict(), sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------- the pieces


def test_every_piece_is_a_stroke_its_synth_plays():
    for player, pieces in C.DRUM_PIECES.items():
        arts = [a for a, _ in pieces]
        assert len(set(arts)) == len(arts) and all(label for _, label in pieces)
        if player == "drum":
            known = set(frame_drum.STROKES)
        else:
            known = set(instruments.spec(player)["articulations"])
            if player == "kit":
                known.add("rim")  # the kit's own name for its rim shot (kit.ALIASES)
        assert set(arts) <= known, (player, set(arts) - known)


def test_the_players_say_their_pieces_and_a_pitched_player_its_range():
    seed = Params.from_dict(G.seed_params)
    players = {p["name"]: p for p in C.playable(seed)}
    assert players["drum"]["drums"] == [{"index": k, "name": a, "label": label}
                                        for k, (a, label) in enumerate(C.DRUM_PIECES["drum"])]
    assert "low" not in players["drum"] and "drums" not in players["fiddle"] and players["fiddle"]["low"] == 55
    kit = next(p for p in C.playable(country()) if p["name"] == "kit")
    assert [d["name"] for d in kit["drums"]][:3] == ["kick", "snare", "rim"] and kit["label"] == "Drum kit"
    with pytest.raises(ValueError, match="strokes"):
        C.part_player("chip-drums")  # its strokes aren't written yet


def test_a_drum_part_is_checked_whole_and_refused_with_why():
    bad = {
        "part.kit.verse:0.0": [[0, 24, len(C.DRUM_PIECES["kit"]), 90]],
        "part.kit.verse:0.1": [[0, 24, -1, 90]],
        "part.kit.verse:0.2": [[0, 24, 0.5, 90]],
        "part.kit.verse:0.3": [[-200, 24, 0, 90]],  # before the line's pickup
        "part.kit.verse:1.0": [[0, 0, 0, 90]],
        "part.kit.verse:1.1": [[0, 24, 0, 128]],
        "part.kit.verse:1.2": [[0, 24, 0]],
        "part.kit.verse:1.3": [[k * 2, 2, 0, 90] for k in range(40)],  # 40 in one beat
        "part.drum.verse:0.0": [[0, 24, 5, 90]],
        "part.drum.verse:0.1": "kick",
        "part.drum.verse:0.2": [[float("nan"), 24, 0, 90]],
    }
    clean, problems = E.check(G, bad)
    assert clean == {} and {p["path"] for p in problems} == set(bad)
    said = {p["path"]: p["why"] for p in problems}
    assert "isn't one of the kit's 15 pieces" in said["part.kit.verse:0.0"]
    assert "starts outside the line" in said["part.kit.verse:0.3"]
    assert "strokes start in beat 1" in said["part.kit.verse:1.3"]
    assert "5 pieces" in said["part.drum.verse:0.0"]


def test_a_drum_part_is_kept_sorted_a_piece_struck_twice_at_once_kept_once_and_any_number_together():
    together = [[0, 24, k, 90] for k in range(len(C.DRUM_PIECES["kit"]))]  # every piece at once (no ten-finger cap)
    clean, problems = E.check(G, {"part.kit.verse:0.0": [[96, 24, 1, 80], [0, 24, 0, 90], [0, 48, 0, 64]],
                                  "part.kit.verse:0.1": together, "part.kit.verse:0.2": []})
    assert not problems
    assert clean["part.kit.verse:0.0"] == [[0, 48, 0, 64], [96, 24, 1, 80]]
    assert clean["part.kit.verse:0.1"] == together and clean["part.kit.verse:0.2"] == []


# ---------------------------------------------------------------- the score


def test_none_written_is_the_same_song():
    for params in (Params.from_dict(G.seed_params), country()):
        assert score_hash(params) == score_hash(replace(params, composition={"parts": {}}))


def test_written_strokes_replace_the_players_own_in_their_line_and_nowhere_else():
    params = country()
    before = realize(G, params)
    mine = with_edits({"part.kit.verse:0.0": BAR, "part.kit.verse:0.1": []}, params)
    after = realize(G, mine)
    assert [n for n in after.notes if n.part != "kit"] == [n for n in before.notes if n.part != "kit"]
    w0, w1, bar = window(mine, "verse:0.0")
    written = [n for n in after.part("kit") if w0 - 1e-6 <= n.start < w1]
    assert [(n.art, round(n.vel * 127), round(n.start - bar, 6)) for n in written] == [
        (C.DRUM_PIECES["kit"][p][0], v, round(o / 96 * 60 / mine.tempo, 6)) for o, _, p, v in BAR]
    sweep = written[-1]
    assert abs(sweep.dur - 60 / mine.tempo) < 1e-6  # held a beat, as written
    v0, v1, _ = window(mine, "verse:0.1")
    assert not [n for n in after.part("kit") if v0 - 0.05 <= n.start < v1]  # the kit rests there
    assert [n for n in before.part("kit") if v0 - 0.05 <= n.start < v1]
    outside = lambda score: [n for n in score.part("kit") if not (w0 - 0.05 <= n.start < v1)]
    assert outside(after) == outside(before)
    released = E.resolve(G, mine, None, None, {"part.kit.verse:0.0": None, "part.kit.verse:0.1": None})
    assert realize(G, released.params) == before


def test_the_frame_drum_plays_its_own_strokes():
    params = Params.from_dict(G.seed_params)
    strokes = [[0, 24, 0, 100], [96, 24, 1, 60], [192, 24, 3, 90], [288, 24, 4, 110]]
    mine = with_edits({"part.drum.refrain:0.0": strokes}, params)
    w0, w1, _ = window(mine, "refrain:0.0")
    written = [n for n in realize(G, mine).part("drum") if w0 - 1e-6 <= n.start < w1]
    assert [n.art for n in written] == ["bass", "tip", "rim", "top"]
    assert all(n.pitch == mine.tonic - 24 for n in written)  # where the program's own strokes are


def test_a_written_part_changes_the_kit_s_sound_there_and_the_same_samples_each_time():
    params = country()
    mine = with_edits({"part.kit.verse:0.0": BAR}, params)
    w0, w1, _ = window(mine, "verse:0.0")

    def stem(p):
        score = realize(G, p)
        notes = tuple(replace(n, start=n.start - w0 + 0.05) for n in score.part("kit") if w0 - 1e-6 <= n.start < w1)
        short = Score(notes=notes, duration=w1 - w0 + 0.5, sections=(), band=score.band)
        (_, make), = [(n, f) for n, f in instruments.band_parts(short, 44100, p.seed) if n == "kit"]
        return make()

    a, b = stem(params), stem(mine)
    assert a.shape == b.shape and not np.allclose(a, b)
    assert np.array_equal(b, stem(mine))


# ---------------------------------------------------------------- the editor's starting part


@pytest.mark.parametrize("style,player", [("country", "kit"), ("lofi", "drummachine"), ("gospel", "tambourine"),
                                          (None, "drum")])
def test_the_programs_strokes_come_back_as_pieces_and_through_a_take_unchanged(style, player):
    params = choose_params(G, None, ADA, DAY, style=style) if style else Params.from_dict(G.seed_params)
    score = realize(G, params)
    track = next(t for t in midi.in_beats(G, params, score) if t["part"] == player)
    assert len(track["strokes"]) == len(score.part(player))  # every stroke the program plays is a piece
    line = next(ln for ln in notesin.layout(G, params)
                if any(ln["w0"] <= s[0] * G.meter.beat < ln["w1"] for s in track["strokes"]))
    taken = notesin.take(G, params, player, track["strokes"], [line["key"]])
    assert not taken["refused"]
    value = taken["changes"][0]["value"]
    assert value
    # written back, the line plays the same strokes where they were (swung as they were, the band's few
    # milliseconds of human timing set straight)
    mine = with_edits({f"part.{player}.{line['key']}": value}, params)
    clock = timeline(G, params)
    w0, w1 = clock.seconds(line["w0"]), clock.seconds(line["w1"])

    def heard(p):
        return sorted(((n.art, n.start) for n in realize(G, p).part(player) if w0 + 0.05 <= n.start < w1 - 0.05),
                      key=lambda x: (x[1], x[0]))

    a, b = heard(mine), heard(params)
    assert [x[0] for x in a] == [x[0] for x in b] and len(a) > 2
    assert max(abs(x[1] - y[1]) for x, y in zip(a, b)) < 0.03


# ---------------------------------------------------------------- the studio, the MIDI file, the record


def test_the_studio_s_players_carry_the_strokes(tmp_path):
    studio = S.Studio(machine="none", home=tmp_path)
    players = S.answer(studio, "/api/players", {"edits": {}})["players"]
    drum = next(p for p in players if p["part"] == "drum")
    assert drum["channel"] == midi.PERCUSSION_CHANNEL and len(drum["strokes"]) == len(drum["notes"])
    assert all(0 <= s[2] < len(C.DRUM_PIECES["drum"]) for s in drum["strokes"])
    assert not [p for p in players if p["part"] not in C.DRUM_PIECES and "strokes" in p]
    view = S.answer(studio, "/api/song", {"edits": {}})["composition"]
    assert next(p for p in view["players"] if p["name"] == "drum")["drums"][0] == {"index": 0, "name": "bass",
                                                                                 "label": "Bass"}


def test_the_midi_file_writes_the_strokes_on_channel_ten():
    params = country()
    mine = with_edits({"part.kit.verse:0.0": BAR}, params)
    score = realize(G, mine)
    data, _ = midi.from_score(G, mine, score)
    read = midi.parse(data)
    kit = next(t for t in read["tracks"] if t["name"] == "Drum kit")
    w0, w1, _ = window(mine, "verse:0.0")
    written = [n for n in score.part("kit") if w0 - 1e-6 <= n.start < w1]
    keys = {n[3] for n in kit["notes"]}
    assert {n[2] for n in kit["notes"]} == {midi.PERCUSSION_CHANNEL}
    assert {midi.DRUM_KEYS[n.art] for n in written} <= keys and {36, 38, 42, 40} <= keys
    assert midi.DRUM_KEYS["snare-cross"] == 37 and midi.DRUM_KEYS["hat-foot"] == 44


def test_marked_by_count_replayed_and_handed_down():
    params = country()
    r = E.resolve(G, params, None, None, {"part.kit.verse:0.0": BAR})
    assert r.marks["part.kit.verse:0.0"] == {"value": {"notes": len(BAR)}, "was": "the program's own part"}
    record = json.loads(json.dumps({"params": r.params.to_dict(), "chosen_by_you": r.marks}))
    assert E.from_record(record)["part.kit.verse:0.0"] == sorted(BAR, key=lambda n: (n[0], n[2]))
    replayed = Params.from_dict(record["params"])
    assert realize(G, replayed) == realize(G, r.params)
    child = choose_params(G, replayed, H.fictional("basil"), DAY)
    assert C.performed_parts(child)["kit"] == C.performed_parts(r.params)["kit"]
