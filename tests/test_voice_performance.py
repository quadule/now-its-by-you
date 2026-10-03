"""Voice work bounded to audible spans keeps the previous control tracks and vocoder bytes."""

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from songbird.phrasing import Gesture
from songbird.score import Note
from songbird.synth import throat as T, voice as V


def digest(*arrays):
    return hashlib.sha256(b"".join(np.ascontiguousarray(x).tobytes() for x in arrays)).hexdigest()


def pitch_inputs():
    rng = np.random.default_rng(5)
    notes, start = [], -0.08
    for k in range(20):
        dur = float(rng.uniform(0.06, 2.0))
        word = ("sad", "bland", "shade", "tide")[k % 4]
        notes.append(Note("voice", start, dur, float(rng.uniform(45, 85)), 0.8, syllable=word, word=word,
                          line_end=k % 7 == 6,
                          gesture=Gesture(scoop=float(rng.uniform(-30, 30)), bend=float(rng.uniform(-50, 50)),
                                          fall=float(rng.uniform(-50, 50)), tune=float(rng.uniform(-10, 10)),
                                          vibrato=20 if k % 3 == 0 else -1),
                          ornament=((0.0, 2.0), (0.2, 0.0), (0.7, -1.0)) if k % 5 == 0 else (),
                          melisma=((0.0, 1.0), (0.05, -2.0), (0.1, 0.0)) if k % 9 == 0 else ()))
        start += dur + float(rng.uniform(-0.025, 0.6))
    # A long wait exposes settled transitions and the next phrase's rise, including their
    # old rounding, while the earlier notes exercise ornaments, overlaps, vowels and consonants.
    notes.append(replace(notes[-1], start=start + 40.0, dur=0.08, melisma=(), ornament=(), line_end=True))
    lexicon = {"sad": "S AE D", "bland": "B L AE N D", "shade": "SH EY D", "tide": "T AY D"}
    return notes, lexicon


def pitch_output(sr, engine, spread, seed):
    notes, lexicon = pitch_inputs()
    voice = V.VoiceParams(engine=engine, spread=spread)
    segs = V.schedule(notes, voice, lexicon, T.DURATIONS, seed=seed)
    sounding = [s.t1 for s in segs if s.role == "vowel"]
    blocks = int(np.ceil((notes[-1].start + notes[-1].dur + 0.5) * sr / V.BLOCK))
    parts = {}
    f0 = V.pitch_track(notes, blocks, sr, voice, np.random.default_rng(seed), sounding,
                       [12.0 if k % 3 else 0.0 for k in range(len(notes))], segs, parts)
    return f0, parts["tremolo"]


# Captured from voice.pitch_track before this optimization; both pitch and tremolo must
# keep every bit, including the nonzero tails of transitions and the random streams.
PITCH = {(24000, 'learned', 0.7, 0): 'd19740eef60f15195cc10b6ae93f93ea3c6375010b562eb9fbde01e2d971467e',
 (24000, 'formant', 0.0, 1): '304d5048a3af137e24c438f8525a142c4e40b5c62186b1ae96f71529e3bdaacf',
 (44100, 'formant', 2.0, 3): '8681ac380cf3bf75c879a2e4676a5be96fed8c7c0c4f7958d3f20c958725684f',
 (44100, 'tube', 0.7, 5): '8f81802d44b194f4e03b6f2f491ad3e89cf0726c455a7e31e9a92d0a8749573e',
 (24000, 'learned', 2.0, 7): '5e1e06d45f6e24dbb91a478937c2bd948a3f1d46a3cfd1ac746450f6c60e8b59',
 (44100, 'learned', 0.0, 9): 'ad957c0b6c7ff5a03233d89ccd49aee456ed47210d05e40822451d9898c1176e'}


@pytest.mark.parametrize("case", list(PITCH))
def test_bounded_pitch_tracks_keep_the_previous_bytes(case):
    assert digest(*pitch_output(*case)) == PITCH[case]


def _consonants_whole(segs, tb):
    """The previous whole-track expressions, before bounding each consonant's contribution."""
    from songbird import phonetics as ph

    out = np.zeros_like(tb)
    sounds = [s for s in segs if s.role != "breath"]
    voiced_sound = lambda s: s is not None and (s.role == "vowel" or ph.CONSONANTS[s.phone][2])
    for i, s in enumerate(sounds):
        if s.role not in ("onset", "coda"):
            continue
        manner, _, voiced = ph.CONSONANTS[s.phone]
        before = sounds[i - 1] if i and sounds[i - 1].t1 > s.t0 - 0.02 else None
        after = sounds[i + 1] if i + 1 < len(sounds) and sounds[i + 1].t0 < s.t1 + 0.02 else None
        if voiced and manner in ("stop", "fricative", "affricate") and voiced_sound(before):
            mid, half = 0.5 * (s.t0 + s.t1), 0.5 * (s.t1 - s.t0) + 0.03
            out += V.SAG * (0.5 + 0.5 * np.cos(np.pi * np.clip((tb - mid) / half, -1.0, 1.0)))
            out += V.SAG_REBOUND * np.clip((tb - s.t1 + 0.01) / 0.03, 0.0, 1.0) * np.clip((s.t1 + 0.1 - tb) / 0.07, 0.0, 1.0)
        elif not voiced:
            if voiced_sound(before):
                out += V.STOP_FALL * np.clip((tb - s.t0 + 0.06) / 0.06, 0.0, 1.0) * np.clip((s.t1 - tb) / max(s.t1 - s.t0, 0.02), 0.0, 1.0)
            if voiced_sound(after):
                out += V.RESTART * np.clip((tb - s.t1 + 0.03) / 0.03, 0.0, 1.0) * np.clip((s.t1 + 0.08 - tb) / 0.08, 0.0, 1.0)
    return out


def test_consonant_pitch_is_exact_at_the_bounds_and_in_long_rests():
    segs = [V.Segment(-0.1, 0.2, "AA", "vowel", 0.8), V.Segment(0.2, 0.24, "D", "coda", 0.8),
            V.Segment(0.24, 0.6, "AE", "vowel", 0.8), V.Segment(0.6, 0.66, "T", "onset", 0.8),
            V.Segment(0.66, 1.0, "IY", "vowel", 0.8)]
    edges = np.array([0.17, 0.27, 0.23, 0.34, 0.54, 0.66, 0.63, 0.74])
    tb = np.unique(np.concatenate([np.arange(-0.2, 60.0, 0.001), edges, np.nextafter(edges, -np.inf),
                                   np.nextafter(edges, np.inf)]))
    assert V.consonant_pitch(segs, tb).tobytes() == _consonants_whole(segs, tb).tobytes()


def vocoder_output(sr, frames, texture):
    rng = np.random.default_rng(frames)
    f0 = np.where(rng.random(frames) > 0.35, rng.uniform(110, 420, frames), 0.0)
    sp, ap = rng.normal(-6.0, 1.0, (frames, 128)), rng.uniform(0.0, 1.0, (frames, 32))
    source = rng.normal(0.0, 0.3, (frames, 128))
    tx = (T.PLAIN, T.TEXTURE, T.Texture(jitter=0.005, jitter_corr=0.6))[texture]
    return T.synthesize(f0, sp, ap, sr, np.random.default_rng(8), source=source, texture=tx)


# Captured while the periodic buffer was still made by an inverse FFT of complex zeros.
VOCODER = {(24000, 1, 0): 'dd11a53a7f02fa4f256fb2404459a563b8a980834725970af610d7ebab9274d4',
 (24000, 2, 1): 'a57e5cc6f2d99928f9104c14d6ab3e154070926940c255dda709442fe42cb97e',
 (24000, 100, 2): 'f7acd800238b4fa216cf7e85970b9d617391fd38c6a94e583b1f9d1d6157b54e',
 (44100, 40, 1): '26a5143f374aa2fdf51edeff3ad63546da4a0458ce4c54e1dd8e42ff317613ef',
 (16000, 100, 0): '3019aa0be76cf2e8075dc4a77e7f84ed290c3bb200ada81864b8785d4cdbaa12',
 (24000, 400, 1): '1359a787ab62aa0dd44faaca8eefdf05410ddfe7d365dd187e4b2e3a115a7ec3'}


@pytest.mark.parametrize("case", list(VOCODER))
def test_the_vocoder_keeps_the_previous_bytes_without_the_zero_fft(case, monkeypatch):
    monkeypatch.setenv("SONGBIRD_THREADS", "1")
    assert digest(vocoder_output(*case)) == VOCODER[case]


def test_all_network_matrix_products_use_the_shared_blas_hook(tmp_path, monkeypatch):
    from tests.test_throat import tiny_model

    model = T.load(tiny_model(tmp_path))
    timeline = T.timeline([("AA", 0.1, 0.4, True, 0.0, "vowel")], 100)
    lf0, singer = np.log(np.full(100, 220.0)), T.timbre(model, None)
    want = T.predict(model, timeline, lf0, singer)
    seen = []

    def matmul(x, weight):
        seen.append(weight)
        return x @ weight.T

    monkeypatch.setattr(T, "_matmul", matmul)
    got = T.predict(model, timeline, lf0, singer)
    assert all(a.tobytes() == b.tobytes() for a, b in zip(got, want))
    expected = [model.w["inp.weight"]]
    for i in range(len(model.config["dilations"])):
        expected.extend(model.w[f"{name}.{i}.weight"] for name in ("films", "convs", "mixes"))
    expected.append(model.w["out.weight"])
    assert len(seen) == len(expected) and all(a is b for a, b in zip(seen, expected))


@pytest.mark.parametrize("matrix_dtype,bias_dtype", [(np.float64, np.float64), (np.float32, np.float32),
                                                     (np.float32, np.float64), (np.float64, np.float32)])
def test_inplace_network_bias_keeps_the_previous_values_and_dtype(matrix_dtype, bias_dtype):
    rng = np.random.default_rng(3)
    x = rng.normal(size=(10, 4)).astype(matrix_dtype)
    weight = rng.normal(size=(3, 4)).astype(matrix_dtype)
    bias = rng.normal(size=3).astype(bias_dtype)
    expected = x @ weight.T + bias
    got = T._linear(x, {"layer.weight": weight, "layer.bias": bias}, "layer")
    assert got.dtype == expected.dtype and got.tobytes() == expected.tobytes()
