"""The drift field: smooth, no calendar edges, small day to day and large year to year, deterministic."""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from songbird import drift as D

VOICE = "0123456789abcdef"


def midnights(start: datetime, n: int) -> np.ndarray:
    return np.array([D.days(start + timedelta(days=k)) for k in range(n)])


def test_no_jump_at_any_day_month_or_year_boundary():
    # every midnight UTC for three years: every day, every first of the month, every new year
    edges = midnights(datetime(2025, 1, 1, tzinfo=timezone.utc), 3 * 366)
    eps = 1e-6  # days, about a tenth of a second
    before, after = D.series(edges - eps, VOICE), D.series(edges + eps, VOICE)
    daily = D.series(edges + 1.0, VOICE)
    for dim in D.DIMENSIONS:
        for view in D.VIEWS:
            jump = np.abs(after[dim][view] - before[dim][view]).max()
            assert jump < 1e-3, (dim, view, jump)
    # and the full view does move from one day to the next, so the test above means something
    change = np.mean([np.abs(daily[d]["full"] - after[d]["full"]).mean() for d in D.DIMENSIONS])
    assert change > 0.05


def test_noise_is_continuous_at_its_lattice_points():
    i = np.arange(-50, 50, dtype=float)
    for seed in (1, 2**63 + 5, 12345):
        assert np.abs(D.noise(i + 1e-9, seed) - D.noise(i - 1e-9, seed)).max() < 1e-6
        slope_left = (D.noise(i, seed) - D.noise(i - 1e-6, seed)) / 1e-6
        slope_right = (D.noise(i + 1e-6, seed) - D.noise(i, seed)) / 1e-6
        assert np.abs(slope_left - slope_right).max() < 1e-3  # smooth, not just continuous
    assert np.abs(D.noise(i, 7)).mean() > 0.2  # never pinned to zero at the lattice


def test_change_grows_with_the_horizon():
    rng = np.random.default_rng(0)
    t = rng.uniform(19000, 23000, 3000)
    now = D.series(t, VOICE, ["tempo", "key", "intro"])

    def moved(dt: float, view: str) -> float:
        later = D.series(t + dt, VOICE, ["tempo", "key", "intro"])
        return float(np.mean([np.abs(later[d][view] - now[d][view]).mean() for d in now]))

    full = [moved(dt, "full") for dt in (1, 7, 30, 365)]
    assert full == sorted(full) and full[0] < 0.2 and full[-1] > 0.4, full
    assert moved(1, "slow") < 0.03  # the form holds from day to day
    assert moved(1, "year") < 0.01 and moved(30, "year") < moved(30, "slow")  # the key holds longer still


def test_views_span_about_minus_one_to_one():
    t = np.linspace(19000, 26000, 20000)
    for view in D.VIEWS:
        values = np.concatenate([D.series(t, h, ["tempo"])["tempo"][view] for h in ("a", "b", "c")])
        assert values.min() >= -1 and values.max() <= 1
        assert 0.35 < values.std() < 0.55, (view, values.std())


def test_deterministic_and_the_same_in_another_process():
    t = D.parse("2027-03-14")
    a, b = D.drift(t, VOICE), D.drift(t, VOICE)
    assert a == b
    code = f"import json; from songbird import drift as D; print(json.dumps(D.drift({t!r}, {VOICE!r}).to_dict()))"
    env = {**os.environ, "PYTHONHASHSEED": "123"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True,
                         cwd=Path(__file__).parent.parent)
    assert json.loads(out.stdout) == json.loads(json.dumps(a.to_dict()))


def test_two_machines_drift_apart_and_a_new_dimension_moves_nothing():
    t = np.linspace(20000, 21000, 2000)
    a, b = D.series(t, "machine-a"), D.series(t, "machine-b")
    assert abs(np.corrcoef(a["tempo"]["full"], b["tempo"]["full"])[0, 1]) < 0.5
    assert np.array_equal(D.series(t, "machine-a", ["key"])["key"]["full"], a["key"]["full"])


def test_dates():
    assert D.when(D.parse("2026-09-25")).isoformat() == "2026-09-25T12:00:00+00:00"
    assert D.parse("2026-09-25T18:30:00Z") == D.parse("2026-09-25T18:30:00")
    t = D.now()
    assert abs(t * D.DAY - round(t * D.DAY)) < 1e-3  # to the second
    assert D.parse(D.when(t).isoformat()) == t  # a record's timestamp replays the instant
    record = D.drift(t, VOICE).to_dict()
    assert D.Drift.from_dict(record).full == {k: v for k, v in record["full"].items()}
