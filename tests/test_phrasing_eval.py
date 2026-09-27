import json
import sys
from dataclasses import astuple, fields
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import phrasing_eval as E

from songbird import genome as G, phrasing as P


def take(early, phrase="v1"):
    return {"fields": [f.name for f in fields(P.Gesture)], "_words": ["la"] * 3,
            "notes": [{"phrase": phrase, "index": i, "off": 0, "gesture": list(astuple(P.Gesture(early=early)))}
                      for i in range(3)]}


def test_combinations_are_sampled_without_enumerating_the_space():
    a = E.subsets(range(1000), 500, 12, np.random.default_rng(0))
    assert len(a) == len(set(a)) == 12 and all(len(set(row)) == 500 for row in a)
    assert a == E.subsets(range(1000), 500, 12, np.random.default_rng(0))


def test_complete_held_out_take_cannot_train_its_own_prediction(monkeypatch):
    monkeypatch.setattr(E, "GENOME", G.load(Path(__file__).resolve().parents[1] / "songs/h-now-its-by-you.json"))
    report = E.take_curve([take(0.1), take(-0.1)])
    field = report["curve"][0]["fields"]["early"]
    assert field["r2"] == pytest.approx(-3) and field["predictions"] == 6
    assert json.loads(json.dumps(report, allow_nan=False)) == report


def test_disjoint_partial_takes_and_missing_fields_have_no_score(monkeypatch):
    monkeypatch.setattr(E, "GENOME", G.load(Path(__file__).resolve().parents[1] / "songs/h-now-its-by-you.json"))
    report = E.take_curve([take(0.1), take(-0.1, "r1")])
    assert report["curve"][0]["fields"]["early"] == {"r2": None, "predictions": 0}
    curve = E.learning_curve({}, 0)
    assert curve["held_out"] == 0 and curve[1] is None


def test_large_take_collection_has_bounded_fit_work(monkeypatch):
    calls = []
    monkeypatch.setattr(E, "phrasing_made", lambda rows, *a: calls.append(len(rows)) or {})
    report = E.take_curve([take(0.1) for _ in range(50)])
    assert len(calls) <= 12 * 6 * 6
    assert [row["training_takes"] for row in report["curve"]] == [1, 2, 4, 8, 16, 49]
