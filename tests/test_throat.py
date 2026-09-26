import json

import numpy as np
import pytest

from songbird.synth import throat as T


def flat(frames: int, level: float = -6.0) -> np.ndarray:
    return np.full((frames, 128), level)


def test_the_vocoder_lasts_as_long_as_its_frames_and_repeats_itself():
    f0 = np.full(200, 220.0)
    ap = np.full((200, 32), 0.1)
    a = T.synthesize(f0, flat(200), ap, 24000, np.random.default_rng(0))
    b = T.synthesize(f0, flat(200), ap, 24000, np.random.default_rng(0))
    assert len(a) == round(200 * T.FRAME * 24000)
    assert np.array_equal(a, b)


def test_voiced_frames_ring_at_their_pitch_and_unvoiced_ones_are_noise():
    sr = 24000
    f0 = np.full(400, 200.0)
    y = T.synthesize(f0, flat(400), np.full((400, 32), 0.01), sr, np.random.default_rng(0))
    spec = np.abs(np.fft.rfft(y[sr // 4 : sr // 4 + sr]))
    freqs = np.fft.rfftfreq(sr, 1 / sr)
    band = (freqs > 150) & (freqs < 450)
    assert abs(freqs[band][np.argmax(spec[band])] - 200.0) < 3.0
    noise = T.synthesize(np.zeros(400), flat(400), np.full((400, 32), 0.01), sr, np.random.default_rng(0))
    s = np.abs(np.fft.rfft(noise[sr // 4 : sr // 4 + sr]))
    peak = s[band].max() / np.median(s[band])
    assert peak < 6.0  # no harmonic lines in noise


def test_a_pulses_dc_is_taken_away_around_it_not_after_it():
    sr = 24000
    f0 = np.where((np.arange(300) >= 100) & (np.arange(300) < 200), 180.0, 0.0)
    sp = np.where(f0[:, None] > 0, -6.0, -40.0) * np.ones((300, 128))  # silent where unvoiced
    y = T.synthesize(f0, sp, np.full((300, 32), 0.001), sr, np.random.default_rng(0))
    voiced = y[int(0.5 * sr): int(1.0 * sr)]
    assert abs(voiced.mean()) < 1e-3 * np.abs(voiced).max()
    after = y[int(1.03 * sr): int(1.2 * sr)]  # WORLD's remover reaches half a window (21 ms) past the last pulse
    assert np.abs(after).max() < 1e-3 * np.abs(voiced).max()


def steady_voice(texture, seed=0, f0=200.0, frames=400):
    """A second or two of one steady vowel-ish envelope through the vocoder, at 24 kHz."""
    g = T.grid(128)
    sp = -6.0 - 1.5 * np.log2(g / 500.0).clip(0) + 2.0 * np.exp(-0.5 * ((g - 700) / 120) ** 2)
    return T.synthesize(np.full(frames, f0), np.tile(sp, (frames, 1)), np.full((frames, 32), 0.05), 24000,
                        np.random.default_rng(seed), texture=texture)


def band(y, lo, hi, sr=24000):
    from scipy.signal import butter, sosfiltfilt

    return sosfiltfilt(butter(6, [lo, hi], btype="bandpass", fs=sr, output="sos"), y)


def test_texture_follows_the_seed():
    busy = T.Texture(spread=0.15, jitter=0.005, scatter=0.5)
    assert np.array_equal(steady_voice(busy, seed=3), steady_voice(busy, seed=3))
    assert not np.array_equal(steady_voice(busy, seed=3), steady_voice(busy, seed=4))


def test_spread_softens_the_click_but_keeps_the_spectrum_and_the_period():
    plain = steady_voice(T.PLAIN)[4800:-4800]
    spread = steady_voice(T.Texture(spread=0.2, jitter=0.0, scatter=0.0))[4800:-4800]
    hf_plain, hf_spread = band(plain, 5000, 9000), band(spread, 5000, 9000)
    crest = lambda y: np.abs(y).max() / np.sqrt(np.mean(y**2))  # noqa: E731
    assert crest(hf_spread) < 0.75 * crest(hf_plain)
    for lo, hi in ((300, 1000), (1000, 3000), (3000, 6000), (6000, 10000)):
        assert abs(20 * np.log10(np.std(band(spread, lo, hi)) / np.std(band(plain, lo, hi)))) < 0.5
    period = 24000 // 200  # still the same every period (the noise aside)
    hf = hf_spread
    r = np.dot(hf[:-period], hf[period:]) / np.dot(hf, hf)
    assert r > 0.8


def test_scatter_unlocks_the_upper_harmonics_from_one_period_to_the_next_but_not_the_lower():
    y = steady_voice(T.Texture(spread=0.0, jitter=0.0, scatter=1.5))[4800:-4800]
    period = 24000 // 200

    def alike(x):
        return np.dot(x[:-period], x[period:]) / np.dot(x, x)

    assert alike(band(y, 200, 1000)) > 0.95
    assert alike(band(y, 5000, 9000)) < 0.6


def test_jitter_unsettles_the_upper_harmonics_more_than_the_lower():
    y = steady_voice(T.Texture(spread=0.0, jitter=0.005, jitter_corr=0.0, scatter=0.0), frames=800)[4800:-4800]
    z = steady_voice(T.PLAIN, frames=800)[4800:-4800]
    period = 24000 // 200
    # a period against the next: 25 us of jitter barely moves 0.1-1 kHz, and 3-6 kHz noticeably
    lo = [np.corrcoef(band(s, 100, 1000)[:-period], band(s, 100, 1000)[period:])[0, 1] for s in (y, z)]
    hi = [np.corrcoef(band(s, 3000, 6000)[:-period], band(s, 3000, 6000)[period:])[0, 1] for s in (y, z)]
    assert lo[1] - lo[0] < 0.03 and hi[1] - hi[0] > 0.1


def test_sharpening_deepens_the_formants_and_keeps_the_power():
    g = T.grid(128)
    sp = (-6.0 - 0.3 * np.log2(g / 500.0).clip(0) + 1.5 * np.exp(-0.5 * ((g - 700) / 150) ** 2)
          + 1.0 * np.exp(-0.5 * ((g - 1800) / 250) ** 2))[None]
    assert np.array_equal(T.sharpen(sp, 1.0), sp)
    out = T.sharpen(sp, 1.5)
    at = np.searchsorted(g, [700.0, 1200.0, 1800.0])
    peaks = lambda s: (s[0, at[0]] - s[0, at[1]], s[0, at[2]] - s[0, at[1]])  # noqa: E731
    assert all(b > 1.1 * a > 0 for a, b in zip(peaks(sp), peaks(out)))
    k = np.hanning(19)[1:-1]
    detrended = lambda s: s[0] - np.convolve(np.pad(s[0], 8, mode="edge"), k / k.sum(), mode="valid")  # noqa: E731
    assert np.std(detrended(out)[10:-10]) > 1.15 * np.std(detrended(sp)[10:-10])
    df = np.gradient(g)
    assert abs(np.log(np.exp(out[0]) @ df) - np.log(np.exp(sp[0]) @ df)) < 1e-9


def test_a_louder_envelope_is_louder_by_as_much():
    f0 = np.full(300, 180.0)
    ap = np.full((300, 32), 0.05)
    quiet = T.synthesize(f0, flat(300, -8.0), ap, 24000, np.random.default_rng(0))
    loud = T.synthesize(f0, flat(300, -8.0 + np.log(10.0)), ap, 24000, np.random.default_rng(0))  # +10 dB in power
    gain = 20 * np.log10(np.std(loud[2000:-2000]) / np.std(quiet[2000:-2000]))
    assert abs(gain - 10.0) < 0.2


def test_the_timeline_says_what_is_sung_in_every_frame():
    segs = [("M", 0.10, 0.16, True, 0.0, "onset"), ("AA", 0.16, 0.50, True, 2.0, "vowel"), ("breath", 0.6, 0.7, False, 0.0, "breath")]
    t = T.timeline(segs, 160)
    idx = {p: i for i, p in enumerate(T.PHONES)}
    assert t["phone"][5] == idx["sil"] and t["next"][5] == idx["M"]
    assert t["phone"][20] == idx["M"] and t["next"][20] == idx["AA"] and t["next2"][20] == idx["sil"]
    assert t["phone"][40] == idx["AA"] and t["prev"][40] == idx["M"] and t["level"][40] == 2.0
    assert T.ROLES[t["role"][40]] == "vowel" and T.ROLES[t["role"][130]] == "breath"
    assert 0.0 <= t["pos"][40] <= 1.0 and t["pos"][33] < t["pos"][40]


def test_a_silence_longer_than_any_it_heard_is_told_as_one_it_knows():
    """The network never heard a silence of a second; a choir waiting 220 s for its entry was told of one that
    long and whispered through it. A long silence is told as SILENCE long: its ends at their own pace, its
    middle held; a short one is told as it is."""
    idx = {p: i for i, p in enumerate(T.PHONES)}
    short = T.timeline([("AA", 0.4, 0.8, True, 0.0, "vowel")], 200)
    assert np.isclose(short["dur"][40], np.log(0.4)) and np.isclose(short["pos"][40], 0.5)
    wait = 220.0
    long = T.timeline([("AA", wait, wait + 0.4, True, 0.0, "vowel")], int((wait + 1.0) / T.FRAME))
    sil = long["phone"] == idx["sil"]
    assert np.allclose(long["dur"][sil], np.log(T.SILENCE))
    assert 0.0 <= long["pos"][sil].min() and long["pos"][sil].max() <= 1.0
    frame = lambda t: int(round(t / T.FRAME))  # noqa: E731
    assert np.isclose(long["pos"][frame(0.1)], 0.1 / T.SILENCE, atol=1e-3)  # just after it starts, at its pace
    assert np.isclose(long["pos"][frame(wait / 2)], 0.5)  # held
    assert np.isclose(long["pos"][frame(wait - 0.1)], 1.0 - 0.1 / T.SILENCE, atol=0.01)  # just before the note


def test_the_throat_is_hushed_where_nothing_is_sung():
    idx = {p: i for i, p in enumerate(T.PHONES)}
    phones = np.full(1000, idx["sil"], dtype=np.int16)
    phones[400:500] = idx["AA"]  # sung from 2.0 to 2.5 s
    g = T.hush(phones, 1000, 5000)
    before, after, fade = T.HUSH
    assert g[2000:2500].min() == 1.0 and g[int(1000 * (2.0 - before)) + 20] == 1.0
    assert g[int(1000 * (2.5 + after)) - 20] == 1.0
    assert g[: int(1000 * (2.0 - before - fade))].max() == 0.0 and g[int(1000 * (2.5 + after + fade)) + 1:].max() == 0.0
    assert np.all(np.diff(g[1000:2000]) >= 0)  # a fade, never a step back
    assert not T.hush(np.full(10, idx["sil"], dtype=np.int16), 1000, 50).any()


@pytest.mark.skipif(not T.MODEL.exists(), reason="no trained throat shipped yet")
def test_a_voice_waiting_for_its_entry_is_silent_and_then_sings_as_after_a_short_wait():
    """A choir voice waits minutes for its entry: that wait is silence (but for the breath before it sings),
    and the note after it sounds as it would after a moment's rest."""
    from songbird.score import Note
    from songbird.synth.voice import VoiceParams

    sr = 44100
    heard = {}
    for wait in (1.0, 60.0):
        y = T.sing([Note("voice", wait, 0.8, 62.0, 0.8, syllable="home", word="home", line_end=True)], sr,
                   VoiceParams(), seed=1)
        heard[wait] = 10 * np.log10(np.mean(y[int(wait * sr): int((wait + 0.6) * sr)] ** 2))
        if wait > 1.0:
            assert not y[: int((wait - 1.0) * sr)].any()  # silent until its breath
    assert abs(heard[60.0] - heard[1.0]) < 1.0


def test_a_source_at_the_reference_changes_nothing_and_a_pressed_one_brightens():
    f0 = np.full(3, 220.0)
    assert not T.source_change(f0, T.RD_REF, T.TILT_REF, 128).any()
    pressed = T.source_change(f0, 0.5, T.TILT_REF, 128)[0]
    at = np.searchsorted(T.grid(128), [300.0, 4000.0])
    assert pressed[at[1]] > 0 > pressed[at[0]]


def test_warping_the_tract_moves_the_envelope_along_frequency():
    g = T.grid(128)
    peak = np.exp(-0.5 * ((g - 1000.0) / 80.0) ** 2)[None]
    up = T.warp(peak, 1.2)
    assert abs(g[np.argmax(up[0])] - 1200.0) < 60.0


def tiny_model(tmp_path, singers=("a", "b")) -> str:
    """A random throat with the trained model's shapes, to test inference without the real weights."""
    rng = np.random.default_rng(0)
    c, e, r, s, cont = 16, 16, 4, 8, 8
    dil = [1, 2]
    w = {"phone.weight": rng.normal(size=(len(T.PHONES), e)), "role.weight": rng.normal(size=(len(T.ROLES), r)),
         "singer.weight": rng.normal(size=(len(singers), s)), "inp.weight": rng.normal(size=(c, 5 * e + r + cont)) * 0.1,
         "inp.bias": np.zeros(c), "out.weight": rng.normal(size=(160, c)) * 0.1, "out.bias": np.zeros(160)}
    for i in range(len(dil)):
        w |= {f"convs.{i}.weight": rng.normal(size=(c, 3 * c)) * 0.1, f"convs.{i}.bias": np.zeros(c),
              f"films.{i}.weight": np.zeros((2 * c, s)), f"films.{i}.bias": np.zeros(2 * c),
              f"mixes.{i}.weight": rng.normal(size=(c, c)) * 0.1, f"mixes.{i}.bias": np.zeros(c)}
    config = dict(dilations=dil, singers=list(singers), phones=list(T.PHONES))
    path = tmp_path / "tiny.npz"
    np.savez(path, config=json.dumps(config), sp_mean=np.full(128, -6.0), sp_std=np.ones(128), ap_mean=np.full(32, 0.2),
             ap_std=np.full(32, 0.1), gv=np.ones(160), **{f"w.{k}": v.astype(np.float32) for k, v in w.items()})
    return str(path)


def test_the_network_gives_an_envelope_for_every_frame_and_a_mix_of_singers_between_them(tmp_path):
    model = T.load(tiny_model(tmp_path))
    t = T.timeline([("AA", 0.1, 0.4, True, 0.0, "vowel")], 100)
    lf0 = np.log(np.full(100, 220.0))
    sp, ap = T.predict(model, t, lf0, T.timbre(model, None))
    assert sp.shape == (100, 128) and ap.shape == (100, 32) and np.all((ap >= 0) & (ap <= 1))
    a = T.timbre(model, {"a": 1.0})
    b = T.timbre(model, {"b": 1.0})
    assert np.allclose(T.timbre(model, None), 0.5 * (a + b))
    assert T.parse_mix("a:2, b") == {"a": 2.0, "b": 1.0}


@pytest.mark.skipif(not T.MODEL.exists(), reason="no trained throat shipped yet")
def test_the_shipped_throat_sings_a_note():
    from songbird.score import Note
    from songbird.synth.voice import VoiceParams

    notes = [Note("voice", 0.3, 0.8, 62.0, 0.8, syllable="home", word="home", line_end=True)]
    y = T.sing(notes, 44100, VoiceParams(), seed=1)
    assert np.isfinite(y).all() and np.abs(y).max() > 0.05


def test_a_machines_singer_is_a_blend_never_one_of_the_trained_singers(tmp_path):
    model = T.load(tiny_model(tmp_path, singers=("a", "b", "c")))
    for seed in range(20):
        mix = T.parse_mix(T.machine_mix(seed, 62.0, model))
        weights = np.array(list(mix.values()))
        assert abs(weights.sum() - 1.0) < 0.01 and weights.max() <= 0.6 + 1e-6
    assert T.machine_mix(3, 62.0, model) == T.machine_mix(3, 62.0, model)
