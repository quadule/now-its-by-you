"""A person's singing after the song is rewritten (docs/notes/SINGING-AFTER-REWRITING.md): a take of a line of its
own or a blank clip's line keeps its gestures under that line's key and never under the tune line it stands in for;
a line edited since keeps the gestures of the notes that still correspond; a singer's habits sing the notes nobody
sang; old phrasings sing exactly as they did; everyone's way takes none of one person's lines or habits."""

import json
import sys
from pathlib import Path

import pytest

from songbird import edits as E, phrasing as P
from songbird.realize import realize

sys.path.insert(0, str(Path(__file__).parent))
from test_clips import G, new_song, version  # noqa: E402
from test_composition import ADA, DAY, SONG  # noqa: E402
from test_own_lines import PATH, WORDS, twelve  # noqa: E402

KEY = PATH.removeprefix("line.")  # verse:wire.0
LATE = P.Gesture(early=-0.125, hold=0.8, scoop=-40.0)
HABIT = P.Gesture(early=0.0625, level=2.0)


def own_line():
    return E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}})


def told(r, phrasing=None):
    out = []
    realize(G, r.params, phrasing=phrasing, lyrics=r.lyrics, told=out)
    return out


def a_way(r, habits=True):
    """A way with every note of the own line sung LATE, as its take sang it, and (habits) the singer's habit."""
    notes = told(r)
    shapes = next(t["of"] for t in notes if t["line"] == KEY)
    return P.Way({"v1": (P.Gesture(level=-1.0),) * 11}, {KEY: P.Line(shapes, (LATE,) * len(shapes))},
                 {"*": HABIT} if habits else {})


# ---------------------------------------------------------------- the format


def test_a_plain_phrasing_stays_plain_and_a_way_round_trips():
    plain = P.from_json(P.to_json({"v1": (P.Gesture(early=0.0625),)}))
    assert type(plain) is dict and not hasattr(plain, "lines")
    way = a_way(own_line())
    data = json.loads(json.dumps(P.to_json(way, source="song")))
    back = P.from_json(data)
    assert isinstance(back, P.Way) and back == way and back.lines == way.lines and back.habits == way.habits
    assert set(data) == {"fields", "source", "phrases", "lines", "habits"}
    assert type(P.from_json({**data, "lines": {}, "habits": {}})) is dict  # empty: the plain phrasing


@pytest.mark.parametrize("change", [
    lambda d: d["lines"].update({"no key": d["lines"][KEY]}),
    lambda d: d["lines"][KEY]["notes"].append([1.0, 1.0, 0]),  # a note more than its gestures
    lambda d: d["lines"][KEY]["notes"][0].__setitem__(1, 99.0),  # a note longer than any
    lambda d: d["lines"][KEY]["notes"][0].__setitem__(2, 1.5),  # a pitch between semitones
    lambda d: d["habits"].update({"loud": [0.0]}),
    lambda d: d["habits"].update({"*": "early"}),
    lambda d: d["lines"].update({f"verse:x{i}.0": d["lines"][KEY] for i in range(P.MAX_LINES)}),
])
def test_lines_and_habits_are_held_to_their_shape(change):
    data = json.loads(json.dumps(P.to_json(a_way(own_line()))))
    change(data)
    with pytest.raises(ValueError):
        P.from_json(data)


def test_every_gesture_of_a_way_is_rounded_and_bounded_on_the_way_in():
    data = P.to_json(a_way(own_line()))
    data["lines"][KEY]["gestures"][0] = [5.0, 0.1, 99.0, 0, 999, 0, 0, -1, 0]
    data["habits"]["*"] = [-3.0, 1.0, 0.26, 0, 0, 0, 0, -1, 0]
    back = P.from_json(data)
    assert back.lines[KEY].gestures[0] == P.Gesture(early=0.25, hold=0.6, level=8.0, scoop=150.0)
    assert back.habits["*"] == P.Gesture(early=-0.25, level=0.5)


def test_habit_kinds_are_few_and_named():
    assert len(P.HABITS) == 22 and P.HABITS[0] == "*"
    shapes = [(0.0, 0.5, 0), (0.5, 1.0, 1), (1.5, 2.0, 5), (3.5, 0.5, 0)]
    assert [P.kind(shapes, k) for k in range(4)] == ["first.short", "inside.medium.step", "inside.long.up", "last.short.down"]
    assert all(P.kind(shapes, k) in P.HABITS for k in range(4))


# ---------------------------------------------------------------- the lookup order


def test_the_lookup_order():
    shapes = [(0.0, 1.0, 0), (1.0, 1.0, 2), (2.0, 2.0, 4)]
    way = P.Way({"v1": (P.Gesture(level=3.0),)}, {"verse:a.0": P.Line(tuple(shapes), (LATE, None, LATE))},
                {"*": HABIT, "inside.medium.step": P.Gesture(level=-2.0)})
    assert P.sung_gesture(way, "v1", None, 0, shapes) == (P.Gesture(level=3.0), "sung")  # a tune line's, by place
    assert P.sung_gesture(way, "v1", None, 1, shapes) == (P.Gesture(level=-2.0), "habit")  # past its row: a habit
    assert P.sung_gesture(way, "v1", "verse:a.0", 0, shapes) == (LATE, "sung")  # the line as it was sung
    assert P.sung_gesture(way, "v1", "verse:a.0", 1, shapes) == (P.Gesture(level=-2.0), "habit")  # never sung
    # the line rewritten: a note put in front, the second one's pitch moved; the notes sung then at the same
    # onset for the same length keep their gestures (the moved one without its tuning), the new one a habit
    now = [(-1.0, 1.0, 0), (0.0, 1.0, 0), (1.0, 1.0, 2), (2.0, 2.0, 7)]
    tuned = P.Way({}, {"verse:a.0": P.Line(tuple(shapes), (LATE, None, P.Gesture(tune=10.0, scoop=-20.0)))}, {"*": HABIT})
    assert P.sung_gesture(tuned, "v1", "verse:a.0", 0, now) == (HABIT, "habit")
    assert P.sung_gesture(tuned, "v1", "verse:a.0", 1, now) == (LATE, "matched")
    assert P.sung_gesture(tuned, "v1", "verse:a.0", 3, now) == (P.Gesture(scoop=-20.0), "matched")
    assert P.sung_gesture(P.without_habits(tuned), "v1", "verse:a.0", 0, now) == (None, "none")
    # a note at the same onset held for another length is another note
    assert P.sung_gesture(tuned, "v1", "verse:a.0", 1, [(0.0, 0.5, 0), (0.5, 0.5, 0)])[1] == "habit"
    # a plain phrasing gives a line of its own nothing, and a tune line its row, as ever
    plain = {"v1": (P.Gesture(level=3.0),)}
    assert P.sung_gesture(plain, "v1", "verse:a.0", 0, shapes) == (None, "none")
    assert P.sung_gesture(plain, "v1", None, 0, shapes) == (P.Gesture(level=3.0), "sung")
    assert P.sung_gesture(plain, "v2", None, 0, shapes) == (None, "none")


def test_a_line_of_its_own_is_sung_its_way_and_the_rest_by_habit():
    r = own_line()
    way = a_way(r)
    notes = told(r, way)
    own = [t for t in notes if t["line"] == KEY]
    assert len(own) == 12 and {t["how"] for t in own} == {"sung"}
    assert {t["how"] for t in notes if t["phrase"] == "v1" and t["line"] is None} == {"sung"}
    assert {t["how"] for t in notes if t["phrase"].startswith("r")} == {"habit"}
    score = realize(G, r.params, phrasing=way, lyrics=r.lyrics)
    voice = sorted(score.part("voice"), key=lambda n: n.start)
    assert [n.gesture for n, t in zip(voice, notes) if t["line"] == KEY] == [LATE] * 12
    assert {n.gesture for n, t in zip(voice, notes) if t["phrase"].startswith("r")} == {HABIT}
    # without habits a note nobody sang has the singer's own timing, as with no phrasing at all
    bare = realize(G, r.params, phrasing=P.without_habits(way), lyrics=r.lyrics)
    assert {n.gesture for n in bare.part("voice") if n.phrase.startswith("r")} == {None}


def test_a_way_without_lines_or_habits_sings_as_the_plain_phrasing_does():
    r = own_line()
    plain = {"v1": (P.Gesture(level=-1.0, early=0.0625),) * 11, "r1": (P.Gesture(scoop=-30.0),) * 4}
    a, b = realize(G, r.params, phrasing=plain, lyrics=r.lyrics), realize(G, r.params, phrasing=P.Way(plain), lyrics=r.lyrics)
    assert a == b
    assert all(n.gesture is None for n, t in zip(sorted(a.part("voice"), key=lambda n: n.start), told(r, plain))
               if t["line"] == KEY)  # a line of its own takes nothing from a plain phrasing


def test_a_blank_clips_line_is_sung_its_way():
    edits, (_, verse, _) = new_song()
    r, problems = version(edits)
    assert not problems
    key = f"{verse}:0.0"
    notes = []
    realize(G, r.params, lyrics=r.lyrics, told=notes)
    mine = [t for t in notes if t["line"] == key]
    assert len(mine) == 5 and mine[0]["phrase"] == f"{verse}-0"
    way = P.Way({}, {key: P.Line(mine[0]["of"], (LATE,) * 5)})
    score = realize(G, r.params, phrasing=way, lyrics=r.lyrics)
    assert [n.gesture for n in sorted(score.part("voice"), key=lambda n: n.start)] == [LATE] * 5


def test_a_stage_edition_scales_lines_and_habits_too():
    from songbird import stage

    way = a_way(own_line())
    half = stage.phrased(way, 0.5)
    assert half.lines[KEY].gestures[0].early == P.reduce(P.Gesture(early=LATE.early / 2)).early
    assert half.habits["*"].level == 1.0 and type(stage.phrased({"v1": (LATE,)}, 0.5)) is dict


# ---------------------------------------------------------------- everyone's way


def test_everyones_way_takes_no_ones_lines_or_habits():
    a, b = a_way(own_line()), P.Way({"v1": (P.Gesture(level=1.0),) * 11}, {}, {"*": P.Gesture(early=-0.0625)})
    both = P.blend([a, b])
    assert type(both) is dict and set(both) == {"v1"} and both["v1"][0] == P.Gesture()
    assert P.to_json(both).keys() == {"fields", "phrases"}


# ---------------------------------------------------------------- records


def test_a_record_carries_lines_and_habits_checked():
    from songbird import received

    data = P.to_json(a_way(own_line()), source="song", source_detail="1 sung take(s)")
    assert received._phrasing(data, "phrasing") == P.to_json(P.from_json(data))
    data["habits"]["nonsense"] = [0.0]
    with pytest.raises(received.Refused):
        received._phrasing(data, "phrasing")


# ---------------------------------------------------------------- measuring (numbers made up, no audio)

FIELDS = [f.name for f in P.fields(P.Gesture)] if hasattr(P, "fields") else None


@pytest.fixture
def tools(tmp_path, monkeypatch):
    """webstudio/worker.py's Tools over a kit of its own, the measuring modules' settings put back after."""
    from webstudio import worker
    from webstudio.kit import Kit

    sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
    import guides as M
    import phrasing as T
    import takes as K

    monkeypatch.setenv("MFA", "off")
    for mod, name in ((K, "GUIDES"), (M, "GUIDES"), (T, "MEASURED")):
        monkeypatch.setattr(mod, name, getattr(mod, name))
    kit = Kit(tmp_path / "kit")
    kit.keep_song(SONG.stem, SONG.read_bytes())
    return worker.Tools(kit)


def guide_of(tools, r):
    from webstudio import guide as GD

    data = GD.score_for(G, r.params, r.lyrics, 90, 0)
    digest = GD.digest(data)
    tools.kit.keep_guide(SONG.stem, digest, GD.text(data))
    return data, digest, tools.guide(SONG.stem, digest)


def measurement(tools, digest, g, early, sung=lambda k, n: True):
    """A take's measurement as webstudio/worker.py measure() gives it: every note early(k, note) beats ahead,
    held fully, on pitch; the notes not sung(k, note) unmeasured."""
    T = tools.T
    names = [f.name for f in __import__("dataclasses").fields(P.Gesture)]
    notes = []
    for k, n in enumerate(g.notes):
        yes = sung(k, n)
        notes.append({"phrase": n.phrase, "index": T.index_in_phrase(g.notes, k), "start": round(n.start, 4),
                      "onset": round(n.start, 4) if yes else None, "off": 0.0 if yes else None,
                      "gesture": [early(k, n), 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0, 0.0] if yes else None})
    from webstudio import worker

    notes = worker.fitted(tools, SONG.stem, notes, digest)
    return {"take": "a take", "stamp": {"guide": digest}, "lag": 0.0, "key": 0, "fields": names, "notes": notes}


def made(tools, digest, *measurements):
    from webstudio import worker

    return worker.phrasing(tools, {"song": SONG.stem, "offered": [digest], "measurements": list(measurements)})


def test_a_take_of_a_line_of_its_own_never_stands_in_for_its_tune_line(tools):
    """Sung alone, a line of its own (twelve notes on v1's eleven) once gave v1 eleven of its gestures, each on
    the wrong syllable after the split; it gives v1 nothing, and its own line all twelve."""
    r = own_line()
    _, digest, g = guide_of(tools, r)
    lines = tools.T.guide_lines(tools.genome(SONG.stem)[0], digest, len(g.notes))
    own = {k for k, t in enumerate(lines["notes"]) if t[0] == KEY}
    assert len(own) == 12 and {g.notes[k].phrase for k in own} == {"v1"}
    m = measurement(tools, digest, g, lambda k, n: 0.125, lambda k, n: k in own)
    assert sum(n["gesture"] is not None for n in m["notes"]) == 12  # kept, the twelfth too
    way = made(tools, digest, m)["phrasing"]
    assert way["phrases"] == {}
    assert list(way["lines"]) == [KEY] and len(way["lines"][KEY]["gestures"]) == 12
    assert all(row[0] == 0.125 for row in way["lines"][KEY]["gestures"])
    assert way["lines"][KEY]["notes"] == [list(s) for s in next(t["of"] for t in told(r) if t["line"] == KEY)]


def test_a_take_of_the_whole_verse_keeps_the_tune_lines_clean(tools):
    """The verse's own line sung early and the rest on time: v1 is v1's (its other verses, on time), the line its
    own; the page's way is kept, read back and sings both."""
    r = own_line()
    data, digest, g = guide_of(tools, r)
    lines = tools.T.guide_lines(tools.genome(SONG.stem)[0], digest, len(g.notes))
    own = {k for k, t in enumerate(lines["notes"]) if t[0] == KEY}
    m = measurement(tools, digest, g, lambda k, n: 0.125 if k in own else 0.0)
    result = made(tools, digest, m)
    way = result["phrasing"]
    assert all(row[0] == 0.0 for rows in way["phrases"].values() for row in rows)  # none of it on the tune's lines
    # each of the line's notes heard once leans toward what the singer does with notes like it (tools/phrasing.py
    # ruled, shrunk), but every one of them early
    assert all(row[0] > 0.0 for row in way["lines"][KEY]["gestures"][:6])
    assert sum(row[0] > 0.0 for row in way["lines"][KEY]["gestures"]) >= 10
    from webstudio import guide as GD

    assert GD.applies(data, way) == {"sung": len(g.notes), "matched": 0, "habit": 0, "none": 0}


def test_a_blank_clips_line_is_measured_and_kept_by_its_key(tools):
    edits, (_, verse, _) = new_song()
    r, _ = version(edits)
    data, digest, g = guide_of(tools, r)
    m = measurement(tools, digest, g, lambda k, n: -0.0625)
    assert all(n["gesture"] is not None for n in m["notes"])  # its tune line isn't the song's: kept all the same
    way = made(tools, digest, m)["phrasing"]
    assert way["phrases"] == {} and list(way["lines"]) == [f"{verse}:0.0"]
    from webstudio import guide as GD

    assert GD.applies(data, way)["sung"] == 5


def test_habits_need_evidence_and_sing_what_was_never_sung(tools):
    """A take of the first verse, every note 0.125 beats late: the singer's habits show it, kind by kind where
    a kind was heard often enough; a refrain nobody sang is sung late by them, and a single note heard once
    makes no habit."""
    r = own_line()
    data, digest, g = guide_of(tools, r)
    verse = {k for k, n in enumerate(g.notes) if n.section == "verse"}
    first = min(verse)
    first_verse = {k for k in verse if k < first + 44}
    way = made(tools, digest, measurement(tools, digest, g, lambda k, n: -0.125, lambda k, n: k in first_verse))["phrasing"]
    assert way["habits"]["*"][0] < -0.1 and set(way["habits"]) <= set(P.HABITS) and len(way["habits"]) >= 2
    from webstudio import guide as GD

    counted = GD.applies(data, way)
    assert counted["habit"] > 100 and counted["none"] == 0
    score_way = P.from_json(way)
    notes = told(r, score_way)
    assert {t["how"] for t in notes if t["phrase"].startswith("r")} == {"habit"}
    one = made(tools, digest, measurement(tools, digest, g, lambda k, n: -0.125, lambda k, n: k == first))["phrasing"]
    assert "habits" not in one


def test_a_way_is_kept_with_and_without_its_habits(tmp_path):
    from webstudio import singing as W

    store = W.Store(tmp_path, G)
    data = P.to_json(a_way(own_line()), source="song", source_detail="1 sung take(s)")
    name, kept, exact = store.keep_both(data)
    assert kept["lines"] and kept["habits"] and W.NAME.match(exact) and exact != name
    bare = json.loads(store.path(exact).read_text())
    assert "habits" not in bare and bare["lines"] == kept["lines"]
    assert store.keep_both(P.to_json({"v1": (P.Gesture(),)}))[2] is None
    with pytest.raises(W.Refused):
        store.keep({**data, "habits": {"*": [0.0], "everything": [1.0]}})


# ---------------------------------------------------------------- a take, sung


def test_a_take_over_a_line_of_its_own_comes_back_on_that_line(tmp_path):
    """The template singer sings the first verse of a version whose first line has twelve syllables, that line's
    notes 80 ms late: measured as the web studio measures a take, the line's gestures come back under its key,
    later than the verse's other lines; v1 holds none of them; the singer's habits are made; and the version's
    refrains, never sung, are sung by those habits."""
    import subprocess

    kit, out = tmp_path / "kit", tmp_path / "out"
    run = subprocess.run([sys.executable, str(Path(__file__).parent / "_singing_rewritten_take.py"), str(kit), str(out)],
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stderr[-2000:]
    got = json.loads((out / "result.json").read_text())
    result, own = got["result"], set(got["own"])
    assert len(own) == 12 and own <= set(got["measured"])
    way = result["phrasing"]
    assert list(way["lines"]) == [KEY] and "v1" not in way["phrases"]
    line = [row[0] for row in way["lines"][KEY]["gestures"] if row is not None]
    rest = [row[0] for pid, rows in way["phrases"].items() for row in rows]
    assert len(line) == 12 and len(rest) >= 20
    assert sorted(line)[6] < sorted(rest)[len(rest) // 2] - 0.02  # the line's median is later than the rest's
    assert way["habits"] and result["applies"]["sung"] == len(got["phrases"])
    notes = told(own_line(), P.from_json(way))
    unsung = [t["how"] for t in notes if t["phrase"] not in way["phrases"] and t["line"] is None]
    assert len(unsung) > 100 and set(unsung) == {"habit"}
