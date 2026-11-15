"""Bounded learned-voice inference and cached vocoder geometry preserve the old arithmetic."""

import numpy as np
import pytest

from songbird.synth import throat as T


def _whole_predict(model, t, lf0, singer, gv):
    """The predictor before temporal chunking and buffer reuse, kept as an independent reference."""
    w = model.w
    phones = np.stack([t[k] for k in ("prev2", "prev", "phone", "next", "next2")], axis=-1).astype(int)
    e = w["phone.weight"][phones].reshape(len(lf0), -1)
    x = T._linear(np.concatenate([e, w["role.weight"][t["role"].astype(int)], T.continuous(t, lf0)], axis=1), w, "inp")
    for i, d in enumerate(model.config["dilations"]):
        gamma, beta = np.split(T._linear(singer[None], w, f"films.{i}"), 2, axis=1)
        stacked = np.zeros((len(x), 3 * x.shape[1]))
        width = x.shape[1]
        stacked[:, width: 2 * width] = x
        if d < len(x):
            stacked[d:, :width] = x[:len(x) - d]
            stacked[:len(x) - d, 2 * width:] = x[d:]
        h = T._matmul(stacked, w[f"convs.{i}.weight"])
        h += w[f"convs.{i}.bias"]
        h *= 1.0 + gamma
        h += beta
        h = T._gelu(h, out=h)
        m = T._matmul(h, w[f"mixes.{i}.weight"])
        m += w[f"mixes.{i}.bias"]
        x += m
    y = T._linear(x, w, "out")
    n_sp = len(model.sp_mean)
    sp, ap = y[:, :n_sp], y[:, n_sp:]
    if gv != 0.0:
        sung = t["role"] >= 2
        mu = sp[sung].mean(axis=0) if sung.any() else sp.mean(axis=0)
        scale = np.clip(np.sqrt(model.gv[:n_sp]), 1.0, 1.6) ** gv
        sp = mu + (sp - mu) * scale
    return sp * model.sp_std + model.sp_mean, np.clip(ap * model.ap_std + model.ap_mean, 0.0, 1.0)


def _rows_stand_alone(matmul) -> bool:
    """Whether this BLAS gives each row of a product the same bits however many rows go in with it: chunks of a
    timeline can only keep the whole's bytes where it does (Apple's Accelerate; OpenBLAS's kernels on some x86
    CPUs block the rows differently, a last bit apart)."""
    rng = np.random.default_rng(3)
    x, w = rng.standard_normal((300, 96)), rng.standard_normal((80, 96))
    whole = matmul(x, w)
    return all(np.array_equal(matmul(x[a:b], w).view(np.int64), whole[a:b].view(np.int64))
               for a, b in ((0, 128), (128, 256), (256, 300), (5, 42)))


def _unless_blas(got, want) -> None:
    """Skipped, saying why, where the chunks' bytes differ from the whole's only as this BLAS makes them (within a
    few units in the last place, its rows blocked by how many go in); asserted everywhere else."""
    if all(a.tobytes() == b.tobytes() for a, b in zip(got, want)) or _rows_stand_alone(T._matmul):
        return
    assert all(np.allclose(a, b, rtol=1e-12, atol=1e-12) for a, b in zip(got, want))
    pytest.skip("this BLAS's products differ by how many rows go in, so chunks can't keep the whole's bytes")


def _inputs(frames):
    t = T.timeline([("AA", 0.1, frames * 0.003, True, 0.0, "vowel"),
                    ("S", frames * 0.003, frames * 0.004, False, 1.0, "coda")], frames)
    lf0 = np.log(np.random.default_rng(2).uniform(150, 400, frames))
    return t, lf0


@pytest.mark.parametrize("frames,gv", [(4097, 0.0), (4159, 0.7), (8257, 1.0)])
def test_temporal_chunks_keep_the_full_network_and_global_variance_bytes(frames, gv):
    model = T.load()
    t, lf0 = _inputs(frames)
    singer = T.timbre(model, None)
    want = _whole_predict(model, t, lf0, singer, gv)
    got = T.predict(model, t, lf0, singer, gv)
    _unless_blas(got, want)
    for a, b in zip(got, want):
        assert a.dtype == b.dtype and a.tobytes() == b.tobytes()
        assert a.flags.c_contiguous == b.flags.c_contiguous


@pytest.mark.parametrize("silent", [False, True])
def test_chunks_use_the_loaded_models_context_and_full_pitch_slopes(tmp_path, monkeypatch, silent):
    from tests.test_throat import tiny_model
    from tests.test_web_synth_performance import web_patches

    model = T.load(tiny_model(tmp_path))  # dilations [1, 2], distinct from the shipped model's context
    t, lf0 = _inputs(547)
    if silent:
        t["role"][:] = 0
    lf0[128] += 0.7  # a discontinuity at the first chunk boundary
    monkeypatch.setattr(T, "PREDICT_BLOCK", 128)
    monkeypatch.setattr(T, "_matmul", web_patches()._dgemm_matmul)
    singer = T.timbre(model, None)
    want = _whole_predict(model, t, lf0, singer, 1.0)
    got = T.predict(model, t, lf0, singer, 1.0)
    _unless_blas(got, want)
    assert all(a.tobytes() == b.tobytes() for a, b in zip(got, want))


def test_a_long_predictor_bounds_each_inference_and_merges_a_tiny_tail(monkeypatch):
    model = T.load()
    frames = 2 * T.PREDICT_BLOCK + 17
    t, lf0 = _inputs(frames)
    seen = []
    raw = T._predict_raw

    def capture(model, told, cont, singer):
        seen.append(len(cont))
        assert len(told["phone"]) == len(cont)
        return raw(model, told, cont, singer)

    monkeypatch.setattr(T, "_predict_raw", capture)
    T.predict(model, t, lf0, T.timbre(model, None))
    assert len(seen) == 2
    assert max(seen) <= T.PREDICT_BLOCK + 2 * sum(model.config["dilations"]) + 63
    assert max(seen) < frames


def _bins_whole(values, fft, sr, log_power):
    at = T.grid(values.shape[1])
    bins = np.arange(fft // 2 + 1) * sr / fft
    pos = np.interp(T.mel(np.clip(bins, T.F_LO, T.F_HI)), T.mel(at), np.arange(len(at)))
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, len(at) - 1)
    w = pos - lo
    out = values[:, lo] * (1 - w) + values[:, hi] * w
    if log_power:
        above = bins > T.F_HI
        out[:, above] -= (T.ROLLOFF / 10.0 * np.log(10.0)) * np.log2(bins[above] / T.F_HI)
    return out


@pytest.mark.parametrize("points,fft,sr", [(32, 512, 16000), (128, 1024, 24000), (128, 2048, 44100)])
def test_cached_spectral_interpolation_and_cepstrum_are_the_previous_arithmetic(points, fft, sr):
    rng = np.random.default_rng(4)
    for rows in (1, 5):
        values = rng.normal(size=(rows, points))
        for log_power in (True, False):
            expected = _bins_whole(values, fft, sr, log_power)
            got = T.to_bins(values, fft, sr, log_power)
            assert got.tobytes() == expected.tobytes() and got.strides == expected.strides
            got[:] = 0.0  # a caller can mutate its result without affecting cached geometry
            assert T.to_bins(values, fft, sr, log_power).tobytes() == expected.tobytes()
        fold = np.zeros(fft)
        fold[0], fold[1:fft // 2], fold[fft // 2] = 1.0, 2.0, 1.0
        for order in ("C", "F"):
            log_mag = np.array(rng.normal(size=(rows, fft // 2 + 1)), order=order)
            cep = np.fft.irfft(log_mag, n=fft, axis=-1)
            expected = np.exp(np.fft.rfft(cep * fold, n=fft, axis=-1))
            assert T.min_phase(log_mag).tobytes() == expected.tobytes()
        r = rng.normal(size=(rows, T._knots(sr)))
        pos = (np.arange(fft // 2 + 1) * sr / fft) / T.SCATTER_BW
        lo = np.minimum(pos.astype(int), r.shape[1] - 2)
        w = pos - lo
        expected = r[:, lo] * (1 - w) + r[:, lo + 1] * w
        assert T._smooth(r, fft, sr).tobytes() == expected.tobytes()


def test_vocoder_geometry_caches_are_bounded_and_immutable():
    for cache, args in ((T._bin_geometry, (128, 1024, 24000)),
                        (T._cepstrum_fold, (1024,)), (T._scatter_geometry, (1024, 24000, 41))):
        cache.cache_clear()
        values = cache(*args)
        values = values if isinstance(values, tuple) else (values,)
        assert all(not value.flags.writeable for value in values)
        for i in range(cache.cache_info().maxsize + 2):
            varied = list(args)
            varied[0] += 2 * (i + 1)
            cache(*varied)
        assert cache.cache_info().currsize == cache.cache_info().maxsize
