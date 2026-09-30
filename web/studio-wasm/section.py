"""One section preview, as the studio makes it (songbird/studio.py Studio._section), without the studio:
the seed of a song, its seed phrasing, no parent, the plain singer. The same code runs natively (numba)
and in Pyodide (numba shimmed, web/studio-wasm/shim/numba.py). Returns int16 PCM (n, 2)."""

from __future__ import annotations

import time

import numpy as np

from songbird import genome as genome_mod, phrasing as phrasing_mod, synth, variation
from songbird.cli import _singer, choir_of
from songbird.realize import choose_params, realize
from songbird.studio import PREVIEW_GAIN_DB, cut, faded, window
from songbird.synth import master
from songbird.synth.mixing import MixParams


def score_of(genome_path: str):
    g = genome_mod.load(genome_path)
    params = choose_params(g)
    seed_phrasing = g.source.get("seed_phrasing")
    phrasing = phrasing_mod.from_json(seed_phrasing) if seed_phrasing else None
    score = variation.lay(realize(g, params, phrasing=phrasing), params)
    return g, params, score


def section(genome_path: str, index: int, progress=None) -> tuple[np.ndarray, dict]:
    t = time.perf_counter()
    g, params, score = score_of(genome_path)
    t0, t1 = window(g, params, score, params.form, index)
    part, lead_in = cut(score, t0, t1)
    singer = _singer(params, [])
    ancestors = choir_of(None, singer)[1]
    t_score = time.perf_counter() - t
    mix = synth.render(part, seed=params.seed, voice=singer, mix_params=MixParams.from_dict(params.mix or {}),
                       ancestors=ancestors, progress=progress)
    ceiling = master.CEILING_DB - master.MARGIN_DB
    loud = master.limit(master.clip(mix * 10.0 ** (PREVIEW_GAIN_DB / 20.0), ceiling), synth.SR, ceiling)
    pcm = master.to_pcm16(faded(loud, synth.SR, lead_in), seed=params.seed)
    return pcm, {"name": params.form[index], "score_s": round(t_score, 3),
                 "total_s": round(time.perf_counter() - t, 3), "seconds": round(len(pcm) / synth.SR, 2)}


def whole(genome_path: str, progress=None) -> tuple[np.ndarray, dict]:
    """The whole song mastered as render_one does (no packet, no FLAC)."""
    t = time.perf_counter()
    g, params, score = score_of(genome_path)
    singer = _singer(params, [])
    ancestors = choir_of(None, singer)[1]
    mix = synth.render(score, seed=params.seed, voice=singer, mix_params=MixParams.from_dict(params.mix or {}),
                       ancestors=ancestors, progress=progress)
    mastered = master.master(mix, synth.SR, target=float(getattr(params, "loudness", master.TARGET_LUFS)))
    pcm = master.to_pcm16(mastered, seed=params.seed)
    return pcm, {"total_s": round(time.perf_counter() - t, 3), "seconds": round(len(pcm) / synth.SR, 2)}


def wav_bytes(pcm: np.ndarray, sr: int = synth.SR) -> bytes:
    """16-bit stereo WAV with the standard library (no libsndfile in the browser)."""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.ascontiguousarray(pcm, dtype="<i2").tobytes())
    return buf.getvalue()
