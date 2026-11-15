"""Notes in (docs/STUDIO.md, "Notes in"): a person's own notes for a band player in one line of the form, played
on a keyboard or brought back from a MIDI file. With none, nothing changes (the goldens say so too). Checked
whole and refused with why; the player's own notes in those lines make room (a note ringing in stops where
theirs begin), nobody else's move; the notes follow the key and the tempo; marked in the record by their count,
made again from its parameters, replayed the same, handed down; silent and said where this version can't play
them."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from songbird import composition as C, drift as D, edits as E, harvest as H, variation as V
from songbird.genome import load
from songbird.realize import Params, choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
G = load(ROOT / "songs" / "h-now-its-by-you.json")
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-26"), ADA.hash)
# the fiddle in the first line of the first verse: a pickup, then a rising line held into the second bar
TUNE = [[-48, 48, 4, 70], [0, 96, 7, 90], [96, 48, 9, 80], [144, 48, 11, 80], [192, 192, 12, 100]]
MINE = {"part.fiddle.verse:0.0": TUNE, "part.bass.verse:0.1": []}


def seed():
    return Params.from_dict(G.seed_params)


def score_of(params):
    return V.lay(realize(G, params), params)


def with_edits(edits, params=None):
    clean, problems = E.check(G, edits)
    assert not problems, problems
    overrides = E.Overrides(G, clean)
    return overrides.params(params or seed()), overrides


def window(params, key):
    """A line's window and first bar line in seconds, on the rendition's clock."""
    clock = timeline(G, params)
    k = [f"{sid}.{j}" for sid, name in zip(C.section_ids(params.form), params.form)
         for j, _ in enumerate(G.section(name).phrases)].index(key)
    u, lines = clock.lead, []
    for name in params.form:
        for pid in G.section(name).phrases:
            lines.append((u, u + G.phrases[pid].bars * G.meter.bar, G.phrases[pid].pickup))
            u += G.phrases[pid].bars * G.meter.bar
    u0, u1, pickup = lines[k]
    after = lines[k + 1][2] if k + 1 < len(lines) else 0
    at = C.beat_clock(clock)
    return at(u0 - pickup), at(u1 - after), at(u0)


def test_none_played_in_is_the_same_song():
    params = seed()
    assert C.performed_parts(params) == {}
    assert score_of(params) == score_of(replace(params, composition={"parts": {}}))
    assert choose_params(G, None, ADA, DAY, overrides={}) == choose_params(G, None, ADA, DAY)


def test_a_part_is_checked_whole_and_refused_with_why():
    bad = {
        "part.fiddle.verse:0.9": TUNE,  # the verse has four lines
        "part.drum.verse:0.0": [[0, 24, 7, 90]],  # the frame drum has five pieces
        "part.chip-drums.verse:0.0": [],  # strokes it can't yet be written
        "part.voice.verse:0.0": [],  # the tune is changed as the tune
        "part.choir1.verse:0.0": [],
        "part.fiddle.chorus:0.0": [],
        "part.fiddle.verse:0.1": [[0, 96, 7]],
        "part.fiddle.verse:0.2": [[0, 96, 7.5, 90]],
        "part.fiddle.verse:0.3": [[-200, 96, 7, 90]],  # before the line's pickup
        "part.lute.verse:1.0": [[0, 96, 60, 90]],  # far above the lute
        "part.harp.verse:1.1": [[0, 96, 7, 0]],
        "part.harp.verse:1.2": [[0, 96 * 40, 7, 90]],
        "part.harp.verse:1.3": [[0, 24, p, 90] for p in range(-12, 0)],  # twelve at once
        "part.fiddle.refrain:0.0": [[0, 96, 7, 90], [0, 96, 11, 90]],  # the fiddle plays one note at a time
        "part.guitar.refrain:0.1": [[k * 2, 2, 0, 90] for k in range(40)],  # 40 in one beat
        "part.guitar.refrain:0.2": [[k, 1, 0, 90] for k in range(600)],
    }
    clean, problems = E.check(G, bad)
    assert clean == {} and {p["path"] for p in problems} == set(bad)
    said = {p["path"]: p["why"] for p in problems}
    assert "four lines" not in said["part.fiddle.verse:0.9"] and "has 4 lines" in said["part.fiddle.verse:0.9"]
    assert "5 pieces" in said["part.drum.verse:0.0"] and "tune" in said["part.voice.verse:0.0"]
    assert "strokes" in said["part.chip-drums.verse:0.0"]
    assert "outside what the lute plays" in said["part.lute.verse:1.0"]
    assert "one note at a time" in said["part.fiddle.refrain:0.0"]
    assert "10 notes sound at once" in said["part.harp.verse:1.3"]


def test_a_part_is_kept_as_played_sorted_and_a_one_note_player_ends_each_note_at_the_next():
    played = [[96, 200, 9, 80], [0, 150, 7, 90], [0, 150, 7, 64]]  # overlapping, one struck twice at once
    clean, _ = E.check(G, {"part.fiddle.verse:0.0": played, "part.harp.verse:0.0": played})
    assert clean["part.fiddle.verse:0.0"] == [[0, 96, 7, 90], [96, 200, 9, 80]]  # trimmed; the repeat dropped
    assert clean["part.harp.verse:0.0"] == [[0, 150, 7, 90], [96, 200, 9, 80]]  # a harp rings on
    too_many = {f"part.guitar.{s}:{n}.{j}": [[k * 3, 3, 0, 90] for k in range(250)]
                for s, n in (("verse", 0), ("verse", 1), ("refrain", 0), ("refrain", 1), ("refrain", 2))
                for j in range(4)}
    clean, problems = E.check(G, too_many)
    assert sum(len(v) for v in clean.values()) <= C.PART_NOTES
    assert problems and all("4,096" in p["why"] for p in problems)


def test_the_player_makes_room_and_nobody_else_moves():
    before = score_of(seed())
    params, overrides = with_edits(MINE)
    assert set(overrides.applied) == set(MINE) and not overrides.problems
    after = score_of(params)
    assert [n for n in after.notes if n.part not in ("fiddle", "bass")] == \
           [n for n in before.notes if n.part not in ("fiddle", "bass")]
    w0, w1, bar = window(params, "verse:0.0")
    mine = [n for n in after.part("fiddle") if w0 - 1e-6 <= n.start < w1]
    assert [round(n.pitch) for n in mine] == [params.tonic + p for *_, p, _ in TUNE]
    assert [round(n.vel * 127) for n in mine] == [v for *_, v in TUNE]
    beat = 60 / params.tempo
    assert abs(mine[1].start - bar) < 1e-9 and abs(mine[0].start - (bar - beat / 2)) < 1e-9  # the pickup
    assert all(n.art == "" for n in mine)  # the fiddle plays them as its own plain notes
    # the program's fiddle notes elsewhere are as they were
    assert [n for n in after.part("fiddle") if n not in mine] == [n for n in before.part("fiddle")
                                                                   if not (w0 - 0.05 <= n.start < w1)]
    w0, w1, _ = window(params, "verse:0.1")
    assert not [n for n in after.part("bass") if w0 - 0.05 <= n.start < w1]  # the bass rests there
    assert [n for n in before.part("bass") if w0 - 0.05 <= n.start < w1]
    for n in after.part("bass"):  # and nothing of its own rings into its rest
        assert not (n.start < w0 - 0.05 and n.start + n.dur > w0 + 0.05)


def test_a_held_note_rings_to_the_end_of_the_run_and_no_further():
    held = {"part.harp.verse:0.0": [[0, 96 * 20, 7, 90]], "part.harp.verse:0.1": [[0, 96, 9, 90]]}
    params, _ = with_edits(held)
    score = score_of(params)
    _, _, bar0 = window(params, "verse:0.0")
    _, end1, bar1 = window(params, "verse:0.1")
    long = next(n for n in score.part("harp") if abs(n.start - bar0) < 1e-9)
    assert abs(long.start + long.dur - end1) < 1e-6  # across the two lines played, stopped where the harp resumes
    assert any(abs(n.start - bar1) < 1e-9 and round(n.pitch) == params.tonic + 9 for n in score.part("harp"))


def test_the_notes_follow_the_key_and_the_tempo():
    params, _ = with_edits(MINE)
    moved = replace(params, tonic=params.tonic - 3, tempo=params.tempo * 1.25)
    a, b = score_of(params), score_of(moved)
    w = window(params, "verse:0.0")
    v = window(moved, "verse:0.0")
    mine_a = [n for n in a.part("fiddle") if w[0] - 1e-6 <= n.start < w[1]]
    mine_b = [n for n in b.part("fiddle") if v[0] - 1e-6 <= n.start < v[1]]
    assert [n.pitch - 3 for n in mine_a] == [n.pitch for n in mine_b]
    assert [round((n.start - w[2]) / 1.25, 6) for n in mine_a] == [round(n.start - v[2], 6) for n in mine_b]


def test_marked_by_count_made_again_from_the_record_replayed_and_handed_down():
    r = E.resolve(G, None, ADA, DAY, dict(MINE))
    assert set(MINE) <= set(r.applied) and not r.problems
    assert r.marks["part.fiddle.verse:0.0"] == {"value": {"notes": 5}, "was": "the program's own part"}
    assert r.marks["part.bass.verse:0.1"] == {"value": {"notes": 0}, "was": "the program's own part"}
    record = json.loads(json.dumps({"params": r.params.to_dict(), "chosen_by_you": r.marks}))
    again = E.resolve(G, None, ADA, DAY, E.from_record(record))
    assert again.params == r.params
    replayed = Params.from_dict(record["params"])  # as --replay reads it: the same score, so the same samples
    assert score_of(replayed) == score_of(r.params)
    child = choose_params(G, Params.from_dict(record["params"]), H.fictional("basil"), DAY)
    assert C.performed_parts(child) == C.performed_parts(r.params)  # a person's part passes on
    released = E.resolve(G, child, None, None, {"part.fiddle.verse:0.0": None})
    assert "fiddle" not in C.performed_parts(released.params)
    assert released.marks["part.fiddle.verse:0.0"] == {"value": None, "was": {"notes": 5}}


def test_silent_where_this_version_cant_play_them_and_said():
    edits = {"band.fiddle": 0, "part.fiddle.verse:0.0": TUNE, "part.harp.verse:3.0": TUNE}
    r = E.resolve(G, None, None, None, E.check(G, edits)[0])
    said = {p["path"]: p["why"] for p in r.problems}
    assert "no fiddle" in said["part.fiddle.verse:0.0"] and "doesn't play that section" in said["part.harp.verse:3.0"]
    assert "part.fiddle.verse:0.0" not in r.applied and C.performed_parts(r.params) == {}
    assert not score_of(r.params).part("fiddle")


@pytest.mark.parametrize("style", ["country", "gospel"])
def test_a_styles_player_can_be_played_in(style):
    params = choose_params(G, None, None, None, style=style)
    player = next(p for p in params.band.lineup if params.band.plays(p) and _pitched(p))
    lo, hi = C.part_player(player)["register"]
    pitch = (lo + hi) // 2 - params.tonic
    key = f"part.{player}.verse:0.0"
    clean, problems = E.check(G, {key: [[0, 96, pitch, 90]]})
    assert not problems
    params2 = E.Overrides(G, clean).params(params)
    w0, w1, bar = window(params2, "verse:0.0")
    mine = [n for n in score_of(params2).part(player) if w0 - 1e-6 <= n.start < w1]
    assert [(round(n.pitch), round(n.start - bar, 9)) for n in mine] == [(params2.tonic + pitch, 0.0)]


def _pitched(player):
    try:
        return C.part_player(player)["register"] is not None
    except ValueError:
        return False
