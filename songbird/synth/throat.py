"""The learned throat: a small network and a vocoder, driven by our singer's schedule and pitch.

Our singer (songbird.synth.voice) decides when each phone is sung, the pitch with its glides,
vibrato and gestures, and how hard each syllable is leaned on. The throat decides how that sounds:

- predict(): a small network (tools/throat/train.py; weights in throat.npz) reads, every 5 ms,
  what is being sung (the phone and its neighbours, its role, how far through it, stress, the
  note's level), log f0 and a singer, and gives the spectral envelope (natural-log power on a
  mel-spaced grid of points from F_LO to F_HI Hz) and aperiodicity (a coarser grid), as the
  WORLD vocoder analyses a voice. The singer is a mix of the synthetic singers it learned from.
- synthesize(): pitch pulses and noise, each shaped by the envelope at its moment, in the manner
  of Morise's WORLD vocoder, written here in numpy so the program carries it. Every pulse is the
  minimum-phase impulse response of the periodic part of the envelope (its power times 1 -
  aperiodicity squared) and brings a stretch of white noise shaped by the aperiodic part; where
  the voice is unvoiced, noise alone, shaped by the whole envelope. Above F_HI the envelope keeps
  falling, so a render at 44.1 kHz has a little air rather than a wall at 12 kHz.
- sing(): the two together, for VoiceParams(engine="learned"). The voice's rd and tilt change
  the glottal source relative to the one the envelopes were learned with; tract warps the
  envelope along frequency.

docs/THROAT.md tells how it was trained and checked.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

FRAME = 0.005  # seconds per envelope frame

# What the throat can sing: silence, a breath, and the phones of songbird.phonetics (vowels without
# stress, AX an unstressed AH, AYR/AWR/OYR a diphthong running into r as in fire and hour).
VOWELS = ("AA", "AE", "AH", "AX", "AO", "EH", "ER", "IH", "IY", "UH", "UW", "EY", "AY", "OW", "AW", "OY", "AYR", "AWR", "OYR")
CONSONANTS = ("B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N", "NG", "P", "R", "S", "SH", "T", "TH", "V",
              "W", "Y", "Z", "ZH")
PHONES = ("sil", "breath") + VOWELS + CONSONANTS
UNVOICED = frozenset({"sil", "breath", "CH", "F", "HH", "K", "P", "S", "SH", "T", "TH"})
F_LO, F_HI = 40.0, 11800.0
UNVOICED_RATE = 500.0  # Hz: how often noise segments are laid down where nothing is voiced (as WORLD)
ROLLOFF = 12.0  # dB per octave the envelope keeps falling above F_HI


def mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def grid(n: int) -> np.ndarray:
    """n frequencies (Hz), evenly spaced in mel from F_LO to F_HI."""
    m = np.linspace(mel(F_LO), mel(F_HI), n)
    return 700.0 * (10.0 ** (m / 2595.0) - 1.0)


def to_bins(values: np.ndarray, fft: int, sr: int, log_power: bool) -> np.ndarray:
    """(frames, n) on the mel grid to (frames, fft // 2 + 1) linear FFT bins.

    Log power continues above the grid at ROLLOFF dB per octave; aperiodicity holds its last value."""
    at = grid(values.shape[1])
    bins = np.arange(fft // 2 + 1) * sr / fft
    # interpolate each row along mel, all rows at once
    pos = np.interp(mel(np.clip(bins, F_LO, F_HI)), mel(at), np.arange(len(at)))
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, len(at) - 1)
    w = pos - lo
    out = values[:, lo] * (1 - w) + values[:, hi] * w
    if log_power:
        above = bins > F_HI
        out[:, above] -= (ROLLOFF / 10.0 * np.log(10.0)) * np.log2(bins[above] / F_HI)
    return out


def min_phase(log_mag: np.ndarray) -> np.ndarray:
    """Minimum-phase spectra (rows, fft // 2 + 1) from natural-log magnitudes, by folding the real cepstrum."""
    fft = 2 * (log_mag.shape[-1] - 1)
    cep = np.fft.irfft(log_mag, n=fft, axis=-1)
    fold = np.zeros(fft)
    fold[0] = 1.0
    fold[1 : fft // 2] = 2.0
    fold[fft // 2] = 1.0
    return np.exp(np.fft.rfft(cep * fold, n=fft, axis=-1))


def pulse_times(f0: np.ndarray, sr: int, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Where the pulses go: the sample each starts in, its fractional delay past that sample, and
    the local period (samples). f0 per 5 ms frame, 0 where unvoiced; unvoiced stretches are paced
    at UNVOICED_RATE."""
    frames = np.arange(n) / sr / FRAME
    f = np.interp(frames, np.arange(len(f0)), np.where(f0 > 0, f0, UNVOICED_RATE))
    phase = np.cumsum(f / sr)  # periods elapsed
    whole = np.floor(phase)
    at = np.flatnonzero(np.diff(whole) > 0) + 1
    exact = at - (phase[at] - whole[at]) / np.maximum(f[at] / sr, 1e-9)  # where the period turned over
    start = np.floor(exact).astype(int)
    return np.maximum(start, 0), exact - start, sr / f[at]


def synthesize(f0: np.ndarray, sp: np.ndarray, ap: np.ndarray, sr: int, rng: np.random.Generator,
               fft: int | None = None, chunk: int = 2048, source: np.ndarray | None = None) -> np.ndarray:
    """A voice from per-frame f0 (Hz, 0 unvoiced), log-power envelope (frames, MEL) and
    aperiodicity (frames, AP_MEL), all on FRAME steps. source: an optional log-power change to the
    voiced (periodic) part alone, on the envelope's grid: a different glottal source from the one
    the envelope was learned with (see source_change)."""
    fft = fft or (1024 if sr <= 24000 else 2048)
    frames = len(f0)
    n = int(round(frames * FRAME * sr))
    y = np.zeros(n + fft)
    at, frac, period = pulse_times(f0, sr, n)
    # each pulse's frame position, for interpolating the envelope and deciding voicing
    pos = np.clip(at / sr / FRAME, 0, frames - 1)
    k0 = np.floor(pos).astype(int)
    k1 = np.minimum(k0 + 1, frames - 1)
    w = (pos - k0)[:, None]
    voiced = np.where(w[:, 0] < 0.5, f0[k0] > 0, f0[k1] > 0)
    bins = np.arange(fft // 2 + 1)
    hann = 0.5 - 0.5 * np.cos(2 * np.pi * (np.arange(fft) + 1.0) / (fft + 1.0))
    hann /= hann.sum()  # takes a pulse's DC away smoothly, as WORLD's DC remover does
    for c0 in range(0, len(at), chunk):
        sl = slice(c0, c0 + chunk)
        env = to_bins(sp[k0[sl]] * (1 - w[sl]) + sp[k1[sl]] * w[sl], fft, sr, log_power=True)
        aper = to_bins(ap[k0[sl]] * (1 - w[sl]) + ap[k1[sl]] * w[sl], fft, sr, log_power=False)
        ratio = np.clip(aper, 0.001, 0.999) ** 2
        v = voiced[sl, None]
        ratio = np.where(v, ratio, 1.0)
        power = np.exp(env)
        voiced_power = power
        if source is not None:
            voiced_power = power * np.exp(to_bins(source[k0[sl]] * (1 - w[sl]) + source[k1[sl]] * w[sl], fft, sr,
                                                  log_power=False))
        # periodic: a minimum-phase pulse, delayed by its fraction of a sample, scaled for its period
        periodic = min_phase(0.5 * np.log(voiced_power * (1.0 - ratio) + 1e-16))
        periodic *= np.exp(-2j * np.pi * bins * frac[sl, None] / fft)
        periodic = np.fft.irfft(periodic, n=fft, axis=-1) * np.sqrt(period[sl, None]) * v
        periodic -= periodic.sum(axis=1, keepdims=True) * hann
        # aperiodic: a period's worth of white noise through the aperiodic part of the envelope
        m = np.maximum(np.round(period[sl]).astype(int), 1)
        noise = rng.standard_normal((len(m), fft))
        inside = np.arange(fft)[None, :] < m[:, None]
        noise = np.where(inside, noise, 0.0)
        noise -= inside * (noise.sum(axis=1, keepdims=True) / m[:, None])  # no DC, as WORLD
        shaped = min_phase(0.5 * np.log(power * ratio + 1e-16)) * np.fft.rfft(noise, axis=-1)
        aperiodic = np.fft.irfft(shaped, n=fft, axis=-1)
        response = periodic + aperiodic
        for j, start in enumerate(at[sl]):
            y[start : start + fft] += response[j]
    return y[:n]


ROLES = ("sil", "breath", "onset", "vowel", "coda")


def timeline(segments: list[tuple], n: int) -> dict[str, np.ndarray]:
    """What is being sung in each of n frames, from (phone, start, end, stressed, level dB, role)
    segments in time order; the gaps between them are silence, as loud as what follows. Per frame:
    the phone and the two before and after it (indices into PHONES), its role (ROLES), how far
    through the phone it is, the phone's length (log seconds), its syllable's stress and its note's
    level."""
    filled: list[tuple] = []
    t = 0.0
    end = n * FRAME
    for phone, a, b, stressed, level, role in segments:
        if a - t > 1e-4:
            filled.append(("sil", t, a, False, level, "sil"))
        a = max(a, t)
        if b > a:
            filled.append((phone, a, b, stressed, level, role))
            t = b
    if end - t > 1e-4:
        filled.append(("sil", t, end, False, filled[-1][4] if filled else 0.0, "sil"))
    index = {p: i for i, p in enumerate(PHONES)}
    ids = [index[f[0]] for f in filled]
    out = {k: np.zeros(n, dtype=np.int16) for k in ("phone", "prev", "next", "prev2", "next2", "role")}
    out |= {k: np.zeros(n, dtype=np.float32) for k in ("pos", "dur", "stress", "level")}
    times = np.arange(n) * FRAME
    for j, (phone, a, b, stressed, level, role) in enumerate(filled):
        i0, i1 = int(np.searchsorted(times, a)), int(np.searchsorted(times, b))
        if i1 <= i0:
            continue
        out["phone"][i0:i1] = ids[j]
        out["prev"][i0:i1] = ids[j - 1] if j >= 1 else 0
        out["prev2"][i0:i1] = ids[j - 2] if j >= 2 else 0
        out["next"][i0:i1] = ids[j + 1] if j + 1 < len(ids) else 0
        out["next2"][i0:i1] = ids[j + 2] if j + 2 < len(ids) else 0
        out["role"][i0:i1] = ROLES.index(role)
        out["pos"][i0:i1] = (times[i0:i1] - a) / max(b - a, 1e-3)
        out["dur"][i0:i1] = np.log(max(b - a, 1e-3))
        out["stress"][i0:i1] = float(stressed)
        out["level"][i0:i1] = level
    return out


# ---- the glottal source, relative to the one the throat learned -------------------------------------

RD_REF, TILT_REF = 0.8, 0.4  # the source the learned envelopes are taken to contain (our singer's usual one)


@lru_cache(maxsize=256)
def _harmonic_power(rd: float, tilt: float, n: int = 400) -> np.ndarray:
    """Power of harmonics 1..n of one LF period (flow derivative), smoothed over neighbours in power."""
    from .glottis import lf_period

    power = np.abs(np.fft.rfft(lf_period(rd, 8192, tilt)))[1 : n + 1] ** 2
    kernel = np.array([0.25, 0.5, 1.0, 0.5, 0.25])
    return np.convolve(np.pad(power, 2, mode="edge"), kernel / kernel.sum(), mode="valid")


def source_change(f0: np.ndarray, rd: float, tilt: float, points: int) -> np.ndarray:
    """Per frame, the log-power change on the envelope's grid from singing with our LF source at
    (rd, tilt) instead of the reference: pressed is brighter, breathy duller with a stronger
    fundamental. The learned envelope already holds a singer's source, so our knobs act relative
    to it rather than on top of it (which would double the glottal tilt)."""
    rd_q, tilt_q = round(float(rd), 2), round(float(tilt), 2)
    if abs(rd_q - RD_REF) < 1e-6 and abs(tilt_q - TILT_REF) < 1e-6:
        return np.zeros((len(f0), points))
    ratio = np.log(_harmonic_power(rd_q, tilt_q)) - np.log(_harmonic_power(RD_REF, TILT_REF))
    h = grid(points)[None, :] / np.maximum(f0, 30.0)[:, None]  # which harmonic each grid point is
    return np.interp(h, np.arange(1, len(ratio) + 1), ratio)


# ---- the network: what is being sung -> envelope and aperiodicity ----------------------------------

MODEL = Path(__file__).with_name("throat.npz")  # the shipped weights; SONGBIRD_THROAT names another file


@dataclass(frozen=True)
class Model:
    config: dict
    w: dict
    sp_mean: np.ndarray
    sp_std: np.ndarray
    ap_mean: np.ndarray
    ap_std: np.ndarray
    gv: np.ndarray


@lru_cache(maxsize=4)
def load(path: str | None = None) -> Model:
    path = path or os.environ.get("SONGBIRD_THROAT") or str(MODEL)
    z = np.load(path)
    w = {k[2:]: z[k].astype(np.float64) for k in z.files if k.startswith("w.")}
    return Model(json.loads(str(z["config"])), w, z["sp_mean"].astype(np.float64), z["sp_std"].astype(np.float64),
                 z["ap_mean"].astype(np.float64), z["ap_std"].astype(np.float64), z["gv"].astype(np.float64))


def continuous(t: dict, lf0: np.ndarray) -> np.ndarray:
    """The continuous inputs, normalised as training normalised them (tools/throat/train.py)."""
    pos = t["pos"].astype(np.float64)
    slope = np.diff(lf0, prepend=lf0[:1]) * 100.0
    return np.stack([pos, np.sin(np.pi * pos), np.cos(np.pi * pos), t["dur"] + 2.5, t["stress"], t["level"] / 10.0,
                     (lf0 - np.log(220.0)) / 0.6, slope], axis=-1)


def _gelu(x: np.ndarray) -> np.ndarray:
    return 0.5 * x * (1.0 + np.tanh(0.7978845608028654 * (x + 0.044715 * x**3)))


def _linear(x: np.ndarray, w: dict, name: str) -> np.ndarray:
    return x @ w[f"{name}.weight"].T + w[f"{name}.bias"]


def timbre(model: Model, mix: dict[str, float] | None, pitch: float | None = None) -> np.ndarray:
    """A singer embedding: the weighted mean of the trained singers'. By default, every singer who
    sings near this pitch (MIDI; within a fifth of their register, the nearer the more), or all of
    them evenly when the model doesn't know their registers."""
    names = model.config["singers"]
    if mix:
        weights = np.array([float(mix.get(n, 0.0)) for n in names])
    elif pitch is not None and model.config.get("registers"):
        away = np.array([abs(pitch - model.config["registers"][n]) for n in names])
        weights = np.clip(1.0 - away / 7.0, 0.0, None)
        if weights.sum() == 0:
            weights = (away == away.min()).astype(float)
    else:
        weights = np.ones(len(names))
    weights = weights / max(weights.sum(), 1e-9)
    return weights @ model.w["singer.weight"]


def machine_mix(seed: int, pitch: float, model: Model | None = None, most: float = 0.6) -> str:
    """A machine's own singer, as a timbre spec for VoiceParams.timbre: a random blend (from seed) of
    the trained singers who sing near this pitch (MIDI), never more than `most` of any one of them,
    so no machine is ever one of the synthetic singers it learned from."""
    model = model or load()
    names = model.config["singers"]
    registers = model.config.get("registers") or {}
    near = [n for n in names if abs(registers.get(n, pitch) - pitch) <= 7.0] or list(names)
    if len(near) < 2:
        near = sorted(names, key=lambda n: abs(registers.get(n, pitch) - pitch))[:2]
    rng = np.random.default_rng(seed)
    for _ in range(100):
        w = rng.dirichlet(np.full(len(near), 1.5))
        if w.max() <= most:
            break
    else:
        w = np.full(len(near), 1.0 / len(near))
    return ",".join(f"{n}:{x:.3f}" for n, x in zip(near, w))


def predict(model: Model, t: dict, lf0: np.ndarray, singer: np.ndarray, gv: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Envelope (log power, MEL points) and aperiodicity for every frame of a timeline."""
    w = model.w
    phones = np.stack([t["prev2"], t["prev"], t["phone"], t["next"], t["next2"]], axis=-1).astype(int)
    e = w["phone.weight"][phones].reshape(len(lf0), -1)
    x = _linear(np.concatenate([e, w["role.weight"][t["role"].astype(int)], continuous(t, lf0)], axis=1), w, "inp")
    for i, d in enumerate(model.config["dilations"]):
        gamma, beta = np.split(_linear(singer[None], w, f"films.{i}"), 2, axis=1)
        p = np.pad(x, ((d, d), (0, 0)))
        stacked = np.concatenate([p[: len(x)], p[d: d + len(x)], p[2 * d: 2 * d + len(x)]], axis=1)
        h = _linear(stacked, w, f"convs.{i}") * (1.0 + gamma) + beta
        x = x + _linear(_gelu(h), w, f"mixes.{i}")
    y = _linear(x, w, "out")
    n_sp = len(model.sp_mean)
    sp, ap = y[:, :n_sp], y[:, n_sp:]
    if gv != 0.0:  # global variance: give back the contrast a small model averages away
        sung = t["role"] >= 2
        mu = sp[sung].mean(axis=0) if sung.any() else sp.mean(axis=0)
        scale = np.clip(np.sqrt(model.gv[:n_sp]), 1.0, 1.6) ** gv
        sp = mu + (sp - mu) * scale
    return sp * model.sp_std + model.sp_mean, np.clip(ap * model.ap_std + model.ap_mean, 0.0, 1.0)


def warp(values: np.ndarray, factor: float) -> np.ndarray:
    """An envelope on the mel grid with every frequency scaled by factor (a longer tract is below 1)."""
    if abs(factor - 1.0) < 1e-6:
        return values
    at = grid(values.shape[1])
    src = mel(np.clip(at / factor, F_LO, F_HI))
    pos = np.interp(src, mel(at), np.arange(len(at)))
    lo = np.floor(pos).astype(int)
    hi = np.minimum(lo + 1, len(at) - 1)
    f = pos - lo
    return values[:, lo] * (1 - f) + values[:, hi] * f


# ---- singing: our schedule, pitch and dynamics through the learned throat ---------------------------

RATE = 24000  # the throat sings at its training data's rate; the result is resampled to the mix's
TRACT = 1.12  # VoiceParams.tract that leaves the learned envelope where it is


def parse_mix(spec: str | dict | None) -> dict[str, float] | None:
    """'bright:2,alto:1' (or a dict) as singer weights; empty for an even mix of every trained singer."""
    if not spec:
        return None
    if isinstance(spec, dict):
        return spec
    out = {}
    for part in spec.split(","):
        name, _, weight = part.partition(":")
        out[name.strip()] = float(weight or 1.0)
    return out


def stresses(notes, lexicon) -> list[bool]:
    """Whether each note's syllable carries dictionary stress (as the training labels do: the stress digit
    of the reading songbird.phonetics.fit chooses; little words like "the" and "a" have none)."""
    from .. import phonetics as ph

    out, i = [], 0
    while i < len(notes):
        n = notes[i].word_len
        out += [s.stressed for s in ph.fit(notes[i].word or notes[i].syllable or "ah", n, lexicon)]
        i += n
    return out


def sing(notes, sr: int, voice, seed: int = 0, lexicon: dict | None = None, mix: str | dict | None = None,
         gv: float = 1.0, model: str | None = None) -> np.ndarray:
    """Sung notes as a mono signal, vowels near the formant singer's level: our schedule (when each
    phone is sung), our pitch track and our dynamics, through the learned throat."""
    from scipy.signal import butter, resample_poly, sosfilt

    from .voice import BLOCK, pitch_track, schedule

    net = load(model)
    notes = sorted(notes, key=lambda n: n.start)
    rng = np.random.default_rng(seed)
    segs = schedule(notes, voice, lexicon)
    stressed = stresses(notes, lexicon)
    rows, k = [], -1
    for s in segs:  # each note sings its onsets, one vowel, its codas
        note = k + 1 if s.role in ("onset", "breath") else k
        if s.role == "vowel":
            k += 1
            note = k
        level = float(20.0 * np.log10(max(s.amp, 1e-6) / 0.9))
        rows.append((s.phone, s.t0, s.t1, stressed[min(max(note, 0), len(notes) - 1)], level, s.role))
    duration = max(s.t1 for s in segs) + 0.5
    n = int(np.ceil(duration / FRAME))
    t = timeline(rows, n)

    vowels = [s for s in segs if s.role == "vowel"]
    n_blocks = int(np.ceil(duration * RATE / BLOCK))
    accents = [voice.accent * float(np.clip(20 * np.log10(s.amp / 0.9) / 3.0, 0.0, 1.0)) for s in vowels]
    f0b = pitch_track(notes, n_blocks, RATE, voice, rng, [s.t1 for s in vowels], accents)
    f0 = np.interp(np.arange(n) * FRAME, (np.arange(n_blocks) + 0.5) * BLOCK / RATE, f0b)
    sung = np.median([n.pitch + voice.shift for n in notes])
    sp, ap = predict(net, t, np.log(f0), timbre(net, parse_mix(mix), sung), gv=gv)
    factor = voice.tract / TRACT
    sp, ap = warp(sp, factor), warp(ap, factor)
    times = np.arange(n) * FRAME
    for s in vowels:  # a phrasing's swell grows or fades the vowel from its start to its end
        if s.swell:
            i0, i1 = np.searchsorted(times, [s.t0, s.t1])
            sp[i0:i1] += (s.swell * np.linspace(0.0, 1.0, max(i1 - i0, 1)))[:, None] * np.log(10.0) / 10.0
    voiced = np.array([PHONES[p] not in UNVOICED for p in t["phone"]])
    source = source_change(f0, voice.rd, voice.tilt, sp.shape[1])
    y = synthesize(np.where(voiced, f0, 0.0), sp, ap, RATE, rng, source=source)
    y = resample_poly(y, sr // np.gcd(sr, RATE), RATE // np.gcd(sr, RATE)) if sr != RATE else y
    y = sosfilt(butter(1, 60.0, btype="highpass", fs=sr, output="sos"), y)
    y = np.concatenate([y, np.zeros(max(0, int(np.ceil(duration * sr)) - len(y)))])[: int(np.ceil(duration * sr))]
    mask = np.zeros(len(y), dtype=bool)
    for s in vowels:
        mask[int(s.t0 * sr): int(s.t1 * sr)] = True
    ref = np.sqrt(np.mean(y[mask] ** 2)) if mask.any() else 1.0
    return 0.3 * y / ref / np.sqrt(2.0)
