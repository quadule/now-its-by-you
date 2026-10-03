"""The browser accelerates every learned-voice matrix product, including residual layers."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from songbird.synth import throat


def web_patches():
    path = Path(__file__).resolve().parents[1] / "web/studio-wasm/py/web_patches.py"
    spec = importlib.util.spec_from_file_location("web_patches_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("rows", [0, 1, 63, 64, 131])
@pytest.mark.parametrize("layout", ["C", "F", "strided"])
def test_browser_blas_handles_short_and_strided_matrix_products(rows, layout):
    rng = np.random.default_rng(3)
    x = rng.standard_normal((rows, 48))[:, ::2] if layout == "strided" else np.array(
        rng.standard_normal((rows, 24)), order=layout)
    weight = rng.standard_normal((11, 24))
    got = web_patches()._dgemm_matmul(x, weight)
    np.testing.assert_allclose(got, x @ weight.T, rtol=1e-13, atol=1e-13)
    assert got.shape == (rows, 11)


def test_browser_small_or_float32_products_keep_their_original_arithmetic():
    rng = np.random.default_rng(4)
    for rows, dtype in [(20, np.float64), (200, np.float32)]:
        x = rng.standard_normal((rows, 24)).astype(dtype)
        weight = rng.standard_normal((11, 24)).astype(dtype)
        got = web_patches()._dgemm_matmul(x, weight)
        assert got.dtype == dtype
        assert got.tobytes() == (x @ weight.T).tobytes()


def test_browser_patch_covers_the_convolution_and_residual_products(monkeypatch):
    model = throat.load()
    timeline = throat.timeline([("AA", 0.0, 0.5, True, 0.0, "vowel")], 120)
    lf0 = np.full(120, np.log(180.0))
    singer = throat.timbre(model, None)
    expected = throat.predict(model, timeline, lf0, singer)
    patches = web_patches()
    calls = []
    accelerated = patches._dgemm_matmul

    def matmul(x, weight):
        calls.append(weight)
        return accelerated(x, weight)

    monkeypatch.setattr(patches, "_dgemm_matmul", matmul)
    monkeypatch.setattr(throat, "_matmul", throat._matmul)
    patches.install()
    got = throat.predict(model, timeline, lf0, singer)
    for i in range(len(model.config["dilations"])):
        assert any(w is model.w[f"convs.{i}.weight"] for w in calls)
        assert any(w is model.w[f"mixes.{i}.weight"] for w in calls)
    for a, b in zip(got, expected):
        np.testing.assert_allclose(a, b, rtol=1e-12, atol=1e-12)
