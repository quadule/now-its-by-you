"""The browser's DTW (web/studio-wasm/py/sing_dtw.py) is librosa's, as tools/phrasing.py align_by_pitch calls it:
the same accumulated costs and the same warping path, bit for bit, on random costs (with many ties, and more rows
than columns, where librosa swaps the path's columns) and on the costs align_by_pitch itself makes from pitch
tracks sung on time, late, flat, an octave down and cut short at the take's edges (docs/WEB-SINGING.md, "On the
device"). Natively tools/phrasing.py keeps librosa; this is what holds the two together."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
librosa = pytest.importorskip("librosa")


def ours():
    spec = importlib.util.spec_from_file_location("sing_dtw", ROOT / "web" / "studio-wasm" / "py" / "sing_dtw.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


D = ours()
STEPS = np.array([[1, 1], [1, 2], [2, 1]])
CALL = dict(subseq=True, step_sizes_sigma=STEPS, weights_add=np.zeros(3), weights_mul=np.ones(3))


def same(C) -> None:
    want_D, want_wp = librosa.sequence.dtw(C=C, **CALL)
    got_D, got_wp = D.dtw(C=C, **CALL)
    assert got_wp.dtype == want_wp.dtype and got_wp.shape == want_wp.shape
    assert np.array_equal(got_wp, want_wp)
    assert np.array_equal(got_D, want_D)  # infinities and all


def test_random_costs_with_ties_and_every_shape():
    rng = np.random.default_rng(7)
    shapes = [(1, 1), (1, 5), (2, 2), (3, 2), (5, 3), (7, 4), (40, 30), (30, 40), (60, 200), (200, 60), (150, 151)]
    shapes += [tuple(int(v) for v in rng.integers(2, 120, 2)) for _ in range(150)]
    for k, shape in enumerate(shapes):
        if k % 3 == 0:  # a few levels only: ties everywhere, as in align_by_pitch's costs
            C = rng.choice([0.0, 0.05, 0.3, 0.55, 0.8, 1.0, 1.25], size=shape)
        elif k % 3 == 1:
            C = rng.random(shape)
        else:
            C = np.round(rng.random(shape) * 4) / 3.0
        try:
            want = librosa.sequence.dtw(C=C, **CALL)
        except librosa.util.exceptions.ParameterError as e:
            with pytest.raises(D.ParameterError, match=str(e)[:30]):
                D.dtw(C=C, **CALL)
            continue
        got = D.dtw(C=C, **CALL)
        assert np.array_equal(got[1], want[1]) and np.array_equal(got[0], want[0]), shape


def test_nan_is_refused_as_librosa_refuses_it():
    with pytest.raises(D.ParameterError):
        D.dtw(C=np.array([[0.0, np.nan], [1.0, 2.0]]), **CALL)


def tracks(rng, notes, knots, n_frames: int, late: float, cents: float, octave: int):
    """A pitch track (f0, Hz) and loudness (dB) per 5 ms frame, of someone singing these notes `late` seconds
    late and `cents` flat, an octave down if asked, with consonant dips and a little wobble; silence between."""
    f0, band = np.zeros(n_frames), np.full(n_frames, -60.0)
    for note, (_, v0, v1, c1, *_r) in zip(notes, knots):
        a, b = int((v0 + late) / 0.005), int((c1 + late) / 0.005)
        a, b = max(a, 0), min(b, n_frames)
        if b <= a:
            continue
        midi = note.pitch - 12 * octave - cents / 100 + rng.normal(0, 0.1, b - a)
        f0[a:b] = 440.0 * 2 ** ((midi - 69) / 12)
        band[a:b] = -20.0 + rng.normal(0, 1.5, b - a)
        band[a: a + 6] -= 14.0  # the consonant before the vowel
        f0[a:b][rng.random(b - a) < 0.03] = 0.0  # the tracker dropping a frame
    return f0, band


def test_the_costs_align_by_pitch_makes(monkeypatch):
    """align_by_pitch on made-up lines, sung in many ways, with librosa's dtw swapped for one that runs both."""
    sys.path.insert(0, str(ROOT / "tools"))
    import phrasing as T  # noqa: E402

    real = librosa.sequence.dtw
    calls, refused = [], []

    def both(*args, **kwargs):
        calls.append(kwargs["C"].shape)
        try:
            want = real(*args, **kwargs)
        except librosa.util.exceptions.ParameterError:
            with pytest.raises(D.ParameterError):
                D.dtw(*args, **kwargs)
            raise
        got = D.dtw(*args, **kwargs)
        assert np.array_equal(got[1], want[1]) and np.array_equal(got[0], want[0]), kwargs["C"].shape
        return want

    monkeypatch.setattr(librosa.sequence, "dtw", both)
    rng = np.random.default_rng(11)
    for case in range(24):
        n = int(rng.integers(3, 14))
        t, notes, knots = 1.0, [], []
        for _ in range(n):
            on, dur = t, float(rng.choice([0.25, 0.4, 0.5, 0.75, 1.0, 1.5]))
            v0 = on + float(rng.uniform(0.0, 0.12))
            notes.append(SimpleNamespace(pitch=float(rng.integers(55, 76))))
            knots.append((on, v0, on + dur * 0.85, on + dur, "a", ""))
            t = on + dur + float(rng.choice([0.0, 0.0, 0.1, 0.4]))
        end = t + 1.0
        late, cents, octave = float(rng.normal(0.0, 0.08)), float(rng.normal(0, 30)), int(rng.choice([0, 0, 1]))
        if case % 4 == 3:  # a take that starts or stops inside the line: its search window clipped at the edge
            cut = float(rng.uniform(0.5, 0.95)) * end
            n_frames = int(cut / 0.005)
        else:
            n_frames = int(end / 0.005) + 200
        f0, band = tracks(rng, notes, knots, n_frames, late, cents, octave)
        lag = int(round(late / 0.005)) if case % 2 else 0
        key = -12 * octave
        try:
            T.align_by_pitch(f0, band, notes, knots, lag, key)
        except librosa.util.exceptions.ParameterError:  # cut too short to sing the line: refused alike
            refused.append(case)
    assert len(calls) == 24 and len(refused) < 6
    assert any(r > c for r, c in calls)  # librosa's swapped columns were met, and matched
