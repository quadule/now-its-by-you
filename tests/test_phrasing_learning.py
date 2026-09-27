"""Learning from a growing, uneven collection of volunteers' takes."""

import sys
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import phrasing as T
import takes as K

from songbird import genome as G, phrasing as P

H = Path(__file__).resolve().parents[1] / "songs/h-now-its-by-you.json"


def only(**values):
    return P.Gesture(**{**dict.fromkeys([f.name for f in fields(P.Gesture)], float("nan")), **values})


def test_partial_measurements_can_learn_timing_without_pitch():
    genome = G.load(H)
    seen = {("v1", k): [only(early=-0.06, hold=0.8 if k == 0 else float("nan"))]
            for k in range(len(genome.phrases["v1"].sung))}
    made = T.ruled(genome, seen)
    assert all(v[0].early == pytest.approx(-0.06) for v in made.values())
    assert made[("v1", 0)][0].hold == pytest.approx(0.8)
    assert all(P.reduce(v[0]).vibrato == -1 for v in made.values())


def test_many_takes_do_not_outvote_other_singers_on_vibrato():
    seen = {("r1", k): [only(vibrato=24)] * 10 + [only(vibrato=-1)] * 2 for k in range(8)}
    weights = {k: [0.1] * 10 + [1, 1] for k in seen}
    for make in (lambda: T.shrunk(seen, weights=weights), lambda: T.ruled(G.load(H), seen, weights=weights)):
        assert all(row[0].vibrato == -1 for row in make().values())
    assert T.vibrato_vote([only(vibrato=24), only(vibrato=-1)], [1, 1]) == -1
    assert T.vibrato_vote([only(vibrato=24), only()], [1, 10]) == 24


def test_machine_vibrato_sentinel_never_drags_down_learned_depth():
    seen = {("r1", k): [only(vibrato=24)] * 2 + [only(vibrato=-1)] for k in range(8)}
    made = T.ruled(G.load(H), seen)
    assert all(row[0].vibrato == pytest.approx(24) for row in made.values())


def test_whole_takes_of_different_forms_count_only_where_they_sang(monkeypatch, tmp_path):
    """A whole short guide has no vote in an extra verse of a longer guide."""
    names = [f.name for f in fields(P.Gesture)]
    note = {"phrase": "v1", "index": 0, "off": 0, "gesture": list(P.Gesture().__dict__.values())}
    short = {"take": "short", "stamp": {"guide": "short"}, "lag": 0, "key": 0, "fields": names, "notes": [note]}
    long = {**short, "take": "long", "stamp": {"guide": "long"}, "notes": [note, note]}
    data = [short, long]
    monkeypatch.setattr(T, "measured", lambda *args: data.pop(0))
    monkeypatch.setattr(T, "guide", lambda *args: SimpleNamespace(
        notes=[SimpleNamespace(syllable="la", pitch=62)] * (1 if args[-1] == "short" else 2)))
    takes = [K.Take(tmp_path / "ana" / name, "Ana", H.stem) for name in ("short.wav", "long.wav")]
    _, (_, weights), _ = T.sung_phrasing(H, G.load(H), takes)
    assert weights[("v1", 0)] == [0.5, 0.5, 1.0]


def test_independent_takes_improve_known_timing():
    """An end-to-end learning check with a known intent, not a fitted take."""
    genome = G.load(H)
    keys = [(pid, j) for pid, phrase in genome.phrases.items() for j in range(len(phrase.sung))]
    rng = np.random.default_rng(72)
    truth = rng.normal(-0.03, 0.06, len(keys))
    performances = truth[:, None] + rng.normal(0, 0.05, (len(keys), 8))
    errors = []
    for count in (1, 2, 4, 8):
        seen = {key: [only(early=v) for v in row[:count]] for key, row in zip(keys, performances)}
        learned = T.ruled(genome, seen)
        errors.append(np.mean([(learned[key][0].early - want) ** 2 for key, want in zip(keys, truth)]))
    assert errors[-1] < errors[0] * 0.5
    assert errors[-1] < errors[1] and errors[-1] < errors[2]
