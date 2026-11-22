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
from dataclasses import dataclass, replace
from functools import lru_cache, partial
from pathlib import Path

import numpy as np
from numba import njit

from . import fx
from .fx import running_mean
from .threads import in_order, workers

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


@lru_cache(maxsize=32)
def _bin_geometry(points: int, fft: int, sr: int) -> tuple[np.ndarray, ...]:
    """Immutable interpolation geometry shared by every pulse block at these dimensions."""
    at = grid(points)
    bins = np.arange(fft // 2 + 1) * sr / fft
    # interpolate each row along mel, all rows at once
    pos = np.interp(mel(np.clip(bins, F_LO, F_HI)), mel(at), np.arange(len(at)))
    lo = np.floor(pos).astype(np.int64)
    hi = np.minimum(lo + 1, len(at) - 1)
    w = pos - lo
    above = bins > F_HI
    rolloff = (ROLLOFF / 10.0 * np.log(10.0)) * np.log2(bins[above] / F_HI)
    rolloff_full = np.zeros(len(bins), dtype=np.float64)
    rolloff_full[above] = rolloff
    arrays = (lo, hi, 1 - w, w, above, rolloff, rolloff_full)
    for a in arrays:
        a.flags.writeable = False
    return arrays


@njit(cache=True, nogil=True)
def _to_bins(values: np.ndarray, lo: np.ndarray, hi: np.ndarray, before: np.ndarray, after: np.ndarray,
             above: np.ndarray, rolloff: np.ndarray, log_power: bool) -> np.ndarray:
    rows = values.shape[0]
    nbins = lo.shape[0]
    out_t = np.empty((nbins, rows))
    for c in range(nbins):
        l = lo[c]
        h = hi[c]
        b = before[c]
        a = after[c]
        sub = rolloff[c] if (log_power and above[c]) else 0.0
        do_sub = log_power and above[c]
        for r in range(rows):
            v = values[r, l] * b + values[r, h] * a
            if do_sub:
                v -= sub
            out_t[c, r] = v
    return out_t


def to_bins(values: np.ndarray, fft: int, sr: int, log_power: bool) -> np.ndarray:
    """(frames, n) on the mel grid to (frames, fft // 2 + 1) linear FFT bins.

    Log power continues above the grid at ROLLOFF dB per octave; aperiodicity holds its last value."""
    lo, hi, before, after, above, rolloff, rolloff_full = _bin_geometry(values.shape[1], fft, sr)
    if fx.JIT:
        out_t = _to_bins(np.ascontiguousarray(values, dtype=np.float64), lo, hi, before, after, above, rolloff_full,
                         bool(log_power))
        return out_t.reshape(1, -1) if values.shape[0] == 1 else out_t.T
    out = values[:, lo] * before + values[:, hi] * after
    if log_power:
        out[:, above] -= rolloff
    return out


@lru_cache(maxsize=8)
def _cepstrum_fold(fft: int) -> np.ndarray:
    fold = np.zeros(fft)
    fold[0] = 1.0
    fold[1 : fft // 2] = 2.0
    fold[fft // 2] = 1.0
    fold.flags.writeable = False
    return fold


@njit(cache=True, nogil=True)
def _polar_turn(spec_f: np.ndarray, amp: np.ndarray, turn: np.ndarray) -> None:
    """In-place: spec[i] = amp[i] * exp(1j * (spec[i].imag + turn[i])), with spec viewed as flat float64."""
    for i in range(amp.shape[0]):
        phi = spec_f[2 * i + 1] + turn[i]
        a = amp[i]
        spec_f[2 * i] = a * np.cos(phi)
        spec_f[2 * i + 1] = a * np.sin(phi)


@njit(cache=True, nogil=True)
def _polar_mul(spec_f: np.ndarray, amp: np.ndarray, other_f: np.ndarray) -> None:
    """In-place: spec[i] = amp[i] * exp(1j * spec[i].imag) * other[i], both viewed as flat float64."""
    for i in range(amp.shape[0]):
        phi = spec_f[2 * i + 1]
        a = amp[i]
        re = a * np.cos(phi)
        im = a * np.sin(phi)
        ore = other_f[2 * i]
        oim = other_f[2 * i + 1]
        spec_f[2 * i] = re * ore - im * oim
        spec_f[2 * i + 1] = re * oim + im * ore


def _min_phase_raw(log_mag: np.ndarray) -> np.ndarray:
    """Minimum-phase complex log-spectrum (rows, fft // 2 + 1), before exp()."""
    fft = 2 * (log_mag.shape[-1] - 1)
    cep = np.fft.irfft(log_mag, n=fft, axis=-1)
    cep *= _cepstrum_fold(fft)
    return np.fft.rfft(cep, n=fft, axis=-1)


def min_phase(log_mag: np.ndarray) -> np.ndarray:
    """Minimum-phase spectra (rows, fft // 2 + 1) from natural-log magnitudes, by folding the real cepstrum."""
    return np.exp(_min_phase_raw(log_mag))


def pulse_times(f0: np.ndarray, sr: int, n: int, block: int = 1 << 16) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Where the pulses go: the sample each starts in, its fractional delay past that sample, and
    the local period (samples). f0 per 5 ms frame, 0 where unvoiced; unvoiced stretches are paced
    at UNVOICED_RATE. (A stretch of samples at a time: the running phase carried from one to the next and added
    on in order, as np.cumsum adds, each turn found against the sample before it: the same pulses as the whole
    song's tracks gave, without them.)"""
    paced = np.where(f0 > 0, f0, UNVOICED_RATE)
    known = np.arange(len(f0))
    ats, fracs, periods = [], [], []
    carry = before = None
    for a in range(0, n, block):
        frames = np.arange(a, min(n, a + block)) / sr / FRAME
        f = np.interp(frames, known, paced)
        steps = f / sr
        phase = np.cumsum(steps) if carry is None else np.cumsum(np.concatenate([[carry], steps]))[1:]  # periods
        whole = np.floor(phase)
        turned = (np.flatnonzero(np.diff(whole) > 0) + 1 if before is None
                  else np.flatnonzero(np.diff(np.concatenate([[before], whole])) > 0))
        at = a + turned
        exact = at - (phase[turned] - whole[turned]) / np.maximum(f[turned] / sr, 1e-9)  # where the period turned over
        start = np.floor(exact).astype(int)
        ats.append(np.maximum(start, 0))
        fracs.append(exact - start)
        periods.append(sr / f[turned])
        carry, before = phase[-1], whole[-1]
    if not ats:
        return np.zeros(0, dtype=int), np.zeros(0), np.zeros(0)
    return np.concatenate(ats), np.concatenate(fracs), np.concatenate(periods)


@dataclass(frozen=True)
class Texture:
    """What the vocoder adds to WORLD's perfectly regular pulses (docs/THROAT.md, "Vocoder").

    Against the voice it resynthesizes, a WORLD-style vocoder repeats every period exactly and lets
    each pulse's upper harmonics arrive together: a click every period, where a voice's spread
    through it. Each of these undoes part of that; the random ones draw on the rng synthesize() is
    given, so a seed still gives one voice.

    - spread: a fixed all-pass above spread_from Hz (full from twice that), the same for every pulse
      and every song, whose group delay wanders along frequency (a smooth random curve, RMS this
      fraction of the pulse's period): each pulse's upper harmonics arrive spread through part of
      the period, still periodic.
    - jitter: each voiced pulse moved by this fraction of its period (RMS), correlated jitter_corr
      from one pulse to the next: the cycle-to-cycle irregularity that voice.pitch_track's slow
      wobble can't give.
    - scatter: a fresh random phase on every pulse (radians RMS, smooth over SCATTER_BW Hz), rising
      in from harmonic scatter_from to scatter_to: upper harmonics that don't lock from one period to
      the next. By harmonic, because what matters is where harmonics stop being heard one by one.
    """

    spread: float = 0.25  # the teacher's upper harmonics are about this spread (docs/THROAT.md)
    spread_from: float = 1500.0
    jitter: float = 0.0
    jitter_corr: float = 0.5
    scatter: float = 0.5  # radians: upper harmonics nearer the teacher's steadiness (docs/THROAT.md; at
    # 0.4 steady vowels' 4-8 kHz still bunch at the pulse, excess kurtosis 2.8 to the teacher's 1.3, and a low
    # voice buzzes with it; 0.25/0.5 lands on the teacher, 0.3/0.6 overshoots)
    scatter_from: float = 8.0
    scatter_to: float = 20.0


TEXTURE = Texture()  # what the throat sings with
PLAIN = Texture(spread=0.0, jitter=0.0, scatter=0.0)  # none: WORLD's own synthesis
SPREAD_SEED, SPREAD_KNOT = 1, 500.0  # the fixed all-pass's curve: a random value every 500 Hz, linear between
SCATTER_BW = 300.0  # Hz over which a pulse's random phase is smooth


@lru_cache(maxsize=16)
def _spread_curve(fft: int, sr: int, start: float) -> np.ndarray:
    """The all-pass's phase per FFT bin, for a group delay of RMS one second above 2 x start Hz,
    ramping in from start; zero mean above start, so the upper harmonics stay centred on the pulse.
    The same curve at every sample rate."""
    knots = np.arange(0.0, 24000.0 + SPREAD_KNOT, SPREAD_KNOT)
    values = np.random.default_rng(SPREAD_SEED).standard_normal(len(knots))
    hz = np.arange(fft // 2 + 1) * sr / fft
    ramp = np.clip((hz - start) / start, 0.0, 1.0)
    delay = np.interp(hz, knots, values)
    full = (hz >= 2 * start) & (hz <= 12000.0)
    delay = ramp * (delay - delay[full].mean()) / delay[full].std()
    return -2.0 * np.pi * np.cumsum(delay) * (sr / fft)


def _knots(sr: int) -> int:
    """How many random values a row of scatter holds: one a knot, SCATTER_BW Hz apart up to Nyquist."""
    return len(np.arange(0.0, sr / 2 + SCATTER_BW, SCATTER_BW))


@lru_cache(maxsize=16)
def _scatter_geometry(fft: int, sr: int, knots: int) -> tuple[np.ndarray, ...]:
    hz = np.arange(fft // 2 + 1) * sr / fft
    pos = hz / SCATTER_BW
    lo = np.minimum(pos.astype(np.int64), knots - 2)
    w = pos - lo
    arrays = (lo, lo + 1, 1 - w, w)
    for a in arrays:
        a.flags.writeable = False
    return arrays


def _smooth(r: np.ndarray, fft: int, sr: int) -> np.ndarray:
    """Rows of values r at knots SCATTER_BW Hz apart, linear between them, per FFT bin."""
    lo, hi, before, after = _scatter_geometry(fft, sr, r.shape[1])
    return r[:, lo] * before + r[:, hi] * after


@njit(cache=True, nogil=True)
def _turn_phase(bins: np.ndarray, hz: np.ndarray, frac: np.ndarray, period: np.ndarray,
                spread: np.ndarray, has_spread: bool, scatter: np.ndarray, has_scatter: bool,
                lo: np.ndarray, hi: np.ndarray, before: np.ndarray, after: np.ndarray,
                sr: float, fft: float, tx_spread: float, tx_scatter: float,
                scatter_from: float, scatter_span: float) -> np.ndarray:
    rows = frac.shape[0]
    nbins = bins.shape[0]
    out = np.empty((rows, nbins))
    neg_two_pi = -2.0 * np.pi
    for r in range(rows):
        fr = frac[r]
        per = period[r]
        sp_scale = (tx_spread * per) / sr
        for c in range(nbins):
            t = ((neg_two_pi * bins[c]) * fr) / fft
            if has_spread:
                t += sp_scale * spread[c]
            if has_scatter:
                h = (hz[c] * per) / sr
                h -= scatter_from
                h /= scatter_span
                if h < 0.0:
                    h = 0.0
                elif h > 1.0:
                    h = 1.0
                h *= tx_scatter
                sm = scatter[r, lo[c]] * before[c] + scatter[r, hi[c]] * after[c]
                h *= sm
                t += h
            out[r, c] = t
    return out


@njit(cache=True, nogil=True)
def _noise_mask(noise: np.ndarray, m: np.ndarray) -> None:
    rows, cols = noise.shape
    for r in range(rows):
        mr = m[r]
        for c in range(mr, cols):
            noise[r, c] = 0.0


@njit(cache=True, nogil=True)
def _noise_sub_dc(noise: np.ndarray, m: np.ndarray, dc: np.ndarray) -> None:
    rows, cols = noise.shape
    for r in range(rows):
        mr = m[r]
        if mr > cols:
            mr = cols
        d = dc[r]
        for c in range(mr):
            noise[r, c] -= d


@njit(cache=True, nogil=True)
def _assemble(periodic: np.ndarray, aperiodic: np.ndarray, hann: np.ndarray, lead: int) -> np.ndarray:
    rows, fft = periodic.shape
    half = fft // 2
    out = np.empty((rows, fft + half))
    pre = half - lead
    post = fft - lead
    for r in range(rows):
        dc = 0.0
        for c in range(fft):
            dc += periodic[r, c]
        for k in range(pre):
            out[r, k] = 0.0 - dc * hann[k]
        for k in range(pre, half):
            out[r, k] = periodic[r, k + half] - dc * hann[k]
        for k in range(half, fft):
            out[r, k] = (periodic[r, k - half] + aperiodic[r, k - half]) - dc * hann[k]
        for k in range(fft, half + post):
            out[r, k] = periodic[r, k - half] + aperiodic[r, k - half]
        for k in range(half + post, fft + half):
            out[r, k] = 0.0 + aperiodic[r, k - half]
    return out


@njit(cache=True, nogil=True)
def _lay(y: np.ndarray, at: np.ndarray, response: np.ndarray) -> None:
    rows, width = response.shape
    for r in range(rows):
        start = at[r]
        for k in range(width):
            y[start + k] += response[r, k]


@njit(cache=True, nogil=True)
def _assemble_lay(y: np.ndarray, at: np.ndarray, periodic: np.ndarray, aperiodic: np.ndarray,
                  hann: np.ndarray, lead: int) -> None:
    rows, fft = periodic.shape
    half = fft // 2
    pre = half - lead
    post = fft - lead
    for r in range(rows):
        start = at[r]
        dc = 0.0
        for c in range(fft):
            dc += periodic[r, c]
        for k in range(pre):
            y[start + k] += 0.0 - dc * hann[k]
        for k in range(pre, half):
            y[start + k] += periodic[r, k + half] - dc * hann[k]
        for k in range(half, fft):
            y[start + k] += (periodic[r, k - half] + aperiodic[r, k - half]) - dc * hann[k]
        for k in range(fft, half + post):
            y[start + k] += periodic[r, k - half] + aperiodic[r, k - half]
        for k in range(half + post, fft + half):
            y[start + k] += 0.0 + aperiodic[r, k - half]


BLOCK = 512  # pulses synthesize() hands a thread at a time: a few tens of MB of spectra each


def synthesize(f0: np.ndarray, sp: np.ndarray, ap: np.ndarray, sr: int, rng: np.random.Generator,
               fft: int | None = None, chunk: int = 2048, source: np.ndarray | None = None,
               texture: Texture | None = None, active: np.ndarray | None = None) -> np.ndarray:
    """A voice from per-frame f0 (Hz, 0 unvoiced), log-power envelope (frames, MEL) and
    aperiodicity (frames, AP_MEL), all on FRAME steps. source: an optional log-power change to the
    voiced (periodic) part alone, on the envelope's grid: a different glottal source from the one
    the envelope was learned with (see source_change). texture: what breaks the pulses' regularity
    (TEXTURE if None; PLAIN for none, WORLD's own synthesis).

    The random values are drawn `chunk` pulses at a time, in order (so a seed gives one voice); the pulses'
    responses are then made BLOCK at a time, on as many threads as workers() gives, each pulse's the same
    whichever block or thread makes it, and laid into the output in order."""
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    from scipy.signal import lfilter

    tx = TEXTURE if texture is None else texture
    fft = fft or (1024 if sr <= 24000 else 2048)
    frames = len(f0)
    n = int(round(frames * FRAME * sr))
    half, lead = fft // 2, fft // 4
    y = np.zeros(n + fft + half)  # runs `half` samples ahead of the output: room for what comes before a pulse
    at, frac, period = pulse_times(f0, sr, n)
    # each pulse's frame position, for interpolating the envelope and deciding voicing
    pos = np.clip(at / sr / FRAME, 0, frames - 1)
    k0 = np.floor(pos).astype(int)
    k1 = np.minimum(k0 + 1, frames - 1)
    w = (pos - k0)[:, None]
    voiced = np.where(w[:, 0] < 0.5, f0[k0] > 0, f0[k1] > 0)
    if tx.jitter > 0 and len(at):  # voiced pulses moved, AR(1) from one to the next
        c = tx.jitter_corr
        steps = lfilter([np.sqrt(1.0 - c * c)], [1.0, -c], rng.standard_normal(len(at) + 32))[32:]
        exact = at + frac + tx.jitter * period * steps * voiced
        at = np.maximum(np.floor(exact).astype(int), 0)
        frac = np.clip(exact - at, 0.0, None)
    bins = np.arange(fft // 2 + 1)
    bins_f = bins.astype(np.float64)
    hz = bins * sr / fft
    spread = _spread_curve(fft, sr, tx.spread_from) if tx.spread > 0 else None
    spread_arg = np.ascontiguousarray(spread, dtype=np.float64) if spread is not None else np.empty(0, dtype=np.float64)
    scat_geom = _scatter_geometry(fft, sr, _knots(sr)) if tx.scatter > 0 else (
        np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64),
        np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64),
    )
    empty_scatter = np.empty((0, 0), dtype=np.float64)
    scatter_span = max(tx.scatter_to - tx.scatter_from, 1e-9)
    hann = 0.5 - 0.5 * np.cos(2 * np.pi * (np.arange(fft) + 1.0) / (fft + 1.0))
    hann /= hann.sum()  # takes a pulse's DC away smoothly over a window centred on it, as WORLD's DC remover does

    threads = workers()
    use_jit = fx.JIT
    direct_lay = threads <= 1 and use_jit
    keep_pulse = None if active is None else (active[k0] | active[k1])

    def responses(sl: slice | np.ndarray, scatter: np.ndarray | None, noise: np.ndarray):
        """The responses of pulses sl, each laid out from `half` samples before its pulse. scatter, noise: their
        rows of the random values drawn for them."""
        env = to_bins(sp[k0[sl]] * (1 - w[sl]) + sp[k1[sl]] * w[sl], fft, sr, log_power=True)
        aper = to_bins(ap[k0[sl]] * (1 - w[sl]) + ap[k1[sl]] * w[sl], fft, sr, log_power=False)
        # (worked out in place where the arrays are this block's own: each product and sum as written out, in the same
        # order, so the same bits with a fifth of the temporaries, which in the browser are most of the time)
        ratio = np.clip(aper, 0.001, 0.999, out=aper)
        np.square(ratio, out=ratio)
        v = voiced[sl]
        ratio[~v] = 1.0
        power = np.exp(env, out=env)
        # periodic: a minimum-phase pulse, delayed by its fraction of a sample, scaled for its period. Made for
        # the voiced pulses only (an unvoiced pulse's is nothing). When _assemble/_assemble_lay sums each row
        # sequentially in compiled code (len(v) > 1), periodic can stay C-contiguous for fast row copies.
        use_fast_asm = use_jit and len(v) > 1
        periodic = np.zeros((len(v), fft)) if use_fast_asm else np.zeros((fft, len(v))).T
        on = np.flatnonzero(v)
        if len(on):
            g = sl.start + on if isinstance(sl, slice) else sl[on]  # the voiced pulses, by their index among all
            voiced_power = power[on]
            if source is not None:
                voiced_power = voiced_power * np.exp(to_bins(source[k0[g]] * (1 - w[g]) + source[k1[g]] * w[g], fft,
                                                             sr, log_power=False))
            mag = ratio[on]
            np.subtract(1.0, mag, out=mag)
            mag *= voiced_power
            mag += 1e-16
            if use_jit:
                amp = np.sqrt(mag, out=mag)
                log_mag = np.log(amp)
                pulse = _min_phase_raw(log_mag)
                del log_mag
                scat_on = np.ascontiguousarray(scatter[on], dtype=np.float64) if scatter is not None else empty_scatter
                turn = _turn_phase(bins_f, hz, np.ascontiguousarray(frac[g], dtype=np.float64),
                                   np.ascontiguousarray(period[g], dtype=np.float64),
                                   spread_arg, spread is not None, scat_on, scatter is not None,
                                   scat_geom[0], scat_geom[1], scat_geom[2], scat_geom[3],
                                   float(sr), float(fft), float(tx.spread), float(tx.scatter),
                                   float(tx.scatter_from), float(scatter_span))
                del scat_on
                pulse = np.ascontiguousarray(pulse)
                _polar_turn(pulse.view(np.float64).reshape(-1), np.ascontiguousarray(amp).reshape(-1), turn.reshape(-1))
                del amp, turn
            else:
                np.log(mag, out=mag)
                mag *= 0.5
                pulse = min_phase(mag)
                del mag
                turn = (-2 * np.pi * bins) * frac[g, None]
                turn /= fft
                if spread is not None:
                    turn += (tx.spread * period[g, None] / sr) * spread[None, :]
                if scatter is not None:
                    harmonic = hz[None, :] * period[g, None]
                    harmonic /= sr
                    harmonic -= tx.scatter_from
                    harmonic /= scatter_span
                    np.clip(harmonic, 0.0, 1.0, out=harmonic)
                    harmonic *= tx.scatter
                    harmonic *= _smooth(scatter[on], fft, sr)
                    turn += harmonic
                    del harmonic
                pulse *= np.exp(1j * turn)
                del turn
            made = np.fft.irfft(pulse, n=fft, axis=-1)
            del pulse
            made *= np.sqrt(period[g, None])
            periodic[on] = made
            del made
        # aperiodic: a period's worth of white noise through the aperiodic part of the envelope
        m = np.maximum(np.round(period[sl]).astype(np.int64), 1)
        if use_jit:
            _noise_mask(noise, m)
            dc = noise.sum(axis=1)
            dc /= m
            _noise_sub_dc(noise, m, dc)
            del dc
        else:
            inside = np.arange(fft)[None, :] < m[:, None]
            noise[~inside] = 0.0
            dc = noise.sum(axis=1, keepdims=True)
            dc /= m[:, None]
            noise -= inside * dc  # no DC, as WORLD
        ratio *= power
        ratio += 1e-16
        if use_jit:
            amp_a = np.empty(ratio.shape, dtype=np.float64)
            np.sqrt(ratio, out=amp_a)
            del ratio
            log_a = np.log(amp_a)
            shaped = np.ascontiguousarray(_min_phase_raw(log_a))
            del log_a
            n_spec = np.ascontiguousarray(np.fft.rfft(noise, axis=-1))
            _polar_mul(shaped.view(np.float64).reshape(-1), amp_a.reshape(-1), n_spec.view(np.float64).reshape(-1))
            del amp_a, n_spec
        else:
            np.log(ratio, out=ratio)
            ratio *= 0.5
            shaped = min_phase(ratio)
            shaped *= np.fft.rfft(noise, axis=-1)
        aperiodic = np.fft.irfft(shaped, n=fft, axis=-1)
        del shaped
        # each response laid out from `half` samples before its pulse: the part of a delayed pulse that
        # rings before it (which the FFT wraps to the end) back where it belongs, then the pulse's DC
        # taken away over the window centred on it
        if use_fast_asm:
            if direct_lay:
                _assemble_lay(y, np.ascontiguousarray(at[sl], dtype=np.int64), periodic,
                              np.ascontiguousarray(aperiodic, dtype=np.float64), hann, lead)
                return None
            return _assemble(periodic, np.ascontiguousarray(aperiodic, dtype=np.float64), hann, lead)
        response = np.zeros((len(m), fft + half))
        response[:, half - lead: half] = periodic[:, fft - lead:]  # np.roll's wrapped tail
        response[:, half: half - lead + fft] = periodic[:, : fft - lead]
        response[:, half:] += aperiodic
        del aperiodic
        response[:, :fft] -= periodic.sum(axis=1, keepdims=True) * hann
        return response

    def lay(sl: slice | np.ndarray, response: np.ndarray | None) -> None:
        if response is None:
            return
        if use_jit:
            _lay(y, np.ascontiguousarray(at[sl], dtype=np.int64), np.ascontiguousarray(response, dtype=np.float64))
            return
        for j, start in enumerate(at[sl]):
            y[start : start + fft + half] += response[j]

    pool = ThreadPoolExecutor(threads) if threads > 1 else None
    pending: deque = deque()
    try:
        for c0 in range(0, len(at), chunk):
            rows = len(at[c0: c0 + chunk])
            # the chunk's random values, always drawn in this order: its scatter, then its noise
            scatter = rng.standard_normal((rows, _knots(sr))) if tx.scatter > 0 else None
            noise = rng.standard_normal((rows, fft))
            if keep_pulse is not None:
                kp = keep_pulse[c0: c0 + rows]
                if not kp.any():
                    continue
                if not kp.all():
                    act_local = np.flatnonzero(kp)
                    starts = list(range(0, len(act_local), BLOCK))
                    if len(starts) > 1 and len(act_local) - starts[-1] == 1:
                        starts.pop()
                    for b0, b1 in zip(starts, starts[1:] + [len(act_local)]):
                        loc = act_local[b0:b1]
                        idx = c0 + loc
                        args = (idx, None if scatter is None else scatter[loc], noise[loc])
                        if pool is None:
                            lay(idx, responses(*args))
                            continue
                        pending.append((idx, pool.submit(responses, *args)))
                        while len(pending) > 2 * threads:
                            done, future = pending.popleft()
                            lay(done, future.result())
                    continue
            # blocks of BLOCK pulses, the last taking one left over (a single row is summed in another order)
            starts = list(range(0, rows, BLOCK))
            if len(starts) > 1 and rows - starts[-1] == 1:
                starts.pop()
            for b0, b1 in zip(starts, starts[1:] + [rows]):
                sl = slice(c0 + b0, c0 + b1)
                args = (sl, None if scatter is None else scatter[b0:b1], noise[b0:b1])
                if pool is None:
                    lay(sl, responses(*args))
                    continue
                pending.append((sl, pool.submit(responses, *args)))
                while len(pending) > 2 * threads:
                    done, future = pending.popleft()
                    lay(done, future.result())
        while pending:
            done, future = pending.popleft()
            lay(done, future.result())
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)
    return y[half : half + n]


ROLES = ("sil", "breath", "onset", "vowel", "coda")

# The longest silence the network is told of. It learned from phrases whose silences were short (half of
# them under 0.07 s, 99% under 0.51 s, none as long as 1 s). Told of a longer one (a rest between sections,
# a choir waiting minutes for its entry) it guessed an envelope far louder than silence, and the vocoder
# murmured through it: up to 8 dB under the singing at the start of a 220 s wait (docs/MIX.md, "The
# hiss"). A longer silence is told as one this long: its first and last halves at their own pace, held
# between. (33 of the training set's 5,959 silences are longer, up to 0.97 s: a retrain would hear them so.)
SILENCE = 0.6
# Where nothing is sung the vocoder is silent: it sounds from HUSH[0] s before a sung phone to HUSH[1] s
# after one (a phone's own ring), fading over HUSH[2] s beyond. Breaths are voice.breaths', added after.
HUSH = (0.06, 0.15, 0.03)
# LAST_SILENCE: the silence after a singer's last phone is told (predict()) as a silence before a breath. The
# training's labels name a breath only just before the singing starts again (tools/throat/dataset.py), so a
# silence with nothing after it holds whatever its recording had after the last phrase (a breath out, the room),
# and the network told of one sings that: a hiss rising to 20 dB over the last note's own tail 0.03-0.13 s after
# it, louder the larger the people's share. A silence before a breath is quiet.


def timeline(segments: list[tuple], n: int) -> dict[str, np.ndarray]:
    """What is being sung in each of n frames, from (phone, start, end, stressed, level dB, role)
    segments in time order; the gaps between them are silence, as loud as what follows. Per frame:
    the phone and the two before and after it (indices into PHONES), its role (ROLES), how far
    through the phone it is, the phone's length (log seconds), its syllable's stress and its note's
    level. A silence longer than SILENCE is given as one SILENCE long: its ends at their own pace,
    its middle held."""
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
        if role == "sil" and b - a > SILENCE:  # longer than any it heard: its two ends at their pace, held between
            since, until = times[i0:i1] - a, b - times[i0:i1]
            out["pos"][i0:i1] = np.where(since < SILENCE / 2, since / SILENCE,
                                         np.where(until < SILENCE / 2, 1.0 - until / SILENCE, 0.5))
            out["dur"][i0:i1] = np.log(SILENCE)
        else:
            out["pos"][i0:i1] = (times[i0:i1] - a) / max(b - a, 1e-3)
            out["dur"][i0:i1] = np.log(max(b - a, 1e-3))
        out["stress"][i0:i1] = float(stressed)
        out["level"][i0:i1] = level
    return out


def _hush_keep(phones: np.ndarray, pad: float = 0.0) -> np.ndarray:
    """Per frame, whether the throat is kept audible (within HUSH + pad of any sung phone)."""
    before, after, _ = HUSH
    sung = phones != PHONES.index("sil")
    if not sung.any():
        return np.zeros(len(sung), dtype=bool)
    idx = np.arange(len(sung))
    last = np.maximum.accumulate(np.where(sung, idx, -len(sung) - 1))  # the latest sung frame at or before each
    ahead = np.minimum.accumulate(np.where(sung, idx, 2 * len(sung) + 1)[::-1])[::-1]  # the next one at or after
    return ((idx - last) * FRAME <= after + pad) | ((ahead - idx) * FRAME <= before + pad)


def hush(phones: np.ndarray, sr: int, n: int) -> np.ndarray:
    """Per sample (n of them), 1 where something is sung and HUSH's margins around it, 0 in the silence
    between, with a raised-cosine fade: the throat is quiet where nothing is sung. phones: the timeline's
    phone for every frame."""
    _, _, fade = HUSH
    keep = _hush_keep(phones)
    if not keep.any():
        return np.zeros(n)
    # (each step where the last left it: the same values, without a second copy of the song's length)
    frame = (np.arange(n) / (FRAME * sr)).astype(np.int64)
    np.minimum(frame, len(keep) - 1, out=frame)
    ramp = keep[frame].astype(np.float64)
    del frame
    running_mean(ramp, max(1, int(fade * sr)), out=ramp)  # uniform_filter1d's, where it lies
    np.clip(ramp, 0.0, 1.0, out=ramp)
    ramp *= np.pi
    np.cos(ramp, out=ramp)
    ramp *= 0.5
    return np.subtract(0.5, ramp, out=ramp)


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


def arrays(path: str | Path) -> dict[str, np.ndarray]:
    """A throat file's arrays as training wrote them: its config, normalisations and weights (float32).

    The shipped file (save) keeps each float32 array as its bytes in four planes, every value's first byte, then
    every value's second, and so on: the planes holding the sign and exponent repeat a great deal and deflate well,
    the mantissas' hardly at all, so the file is 0.3 MB smaller and the values are the same bit for bit. Its
    "planes" entry names the arrays kept so. A file without one (as training writes it) reads as it is."""
    with np.load(path) as z:
        planed = {str(k) for k in z["planes"]} if "planes" in z.files else set()
        out = {}
        for k in z.files:
            if k == "planes":
                continue
            a = z[k]
            if k in planed:  # (4, *shape) bytes -> (*shape,) little-endian float32
                a = np.ascontiguousarray(np.moveaxis(a, 0, -1)).view("<f4").reshape(a.shape[1:])
            out[k] = a
    return out


def save(path: str | Path, model: dict[str, np.ndarray]) -> None:
    """A throat file as it ships (arrays reads it): each float32 array's bytes in planes, compressed."""
    planed = sorted(k for k, a in model.items() if a.dtype == np.float32)
    stored = {k: np.moveaxis(np.ascontiguousarray(a, dtype="<f4").reshape(*a.shape, 1).view(np.uint8), -1, 0)
              if k in planed else a for k, a in model.items()}
    np.savez_compressed(path, planes=np.array(planed), **stored)


@lru_cache(maxsize=4)
def load(path: str | None = None) -> Model:
    path = path or os.environ.get("SONGBIRD_THROAT") or str(MODEL)
    z = arrays(path)
    w = {k[2:]: z[k].astype(np.float64) for k in z if k.startswith("w.")}
    return Model(json.loads(str(z["config"])), w, z["sp_mean"].astype(np.float64), z["sp_std"].astype(np.float64),
                 z["ap_mean"].astype(np.float64), z["ap_std"].astype(np.float64), z["gv"].astype(np.float64))


def continuous(t: dict, lf0: np.ndarray) -> np.ndarray:
    """The continuous inputs, normalised as training normalised them (tools/throat/train.py)."""
    pos = t["pos"].astype(np.float64)
    slope = np.diff(lf0, prepend=lf0[:1]) * 100.0
    return np.stack([pos, np.sin(np.pi * pos), np.cos(np.pi * pos), t["dur"] + 2.5, t["stress"], t["level"] / 10.0,
                     (lf0 - np.log(220.0)) / 0.6, slope], axis=-1)


@njit(cache=True, nogil=True)
def _gelu_flat(x: np.ndarray, out: np.ndarray) -> None:
    for i in range(x.shape[0]):
        v = x[i]
        t = 0.7978845608028654 * (v + 0.044715 * (v * v * v))
        out[i] = 0.5 * v * (1.0 + np.tanh(t))


def _gelu(x: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
    """0.5 x (1 + tanh(0.7978845608028654 (x + 0.044715 x^3))), elementwise: fused in place across
    threads (threads.in_order). out may be x itself."""
    out = np.empty_like(x) if out is None else out
    if fx.JIT and x.dtype == np.float64 and out.dtype == np.float64 and x.flags.c_contiguous and out.flags.c_contiguous:
        xf, of = x.reshape(-1), out.reshape(-1)
        cols = x.shape[1] if x.ndim == 2 else 1
        step = 4096 * cols
        if workers() <= 1 or len(xf) <= step:
            _gelu_flat(xf, of)
            return out
        for _ in in_order([(a, partial(_gelu_flat, xf[a: a + step], of[a: a + step]))
                           for a in range(0, len(xf), step)]):
            pass
        return out
    rows = 4096

    def part(r0: int) -> None:
        v, o = x[r0: r0 + rows], out[r0: r0 + rows]
        t = v * v
        t *= v
        t *= 0.044715
        t += v
        t *= 0.7978845608028654
        np.tanh(t, out=t)
        t += 1.0
        np.multiply(0.5, v, out=o)
        o *= t

    for _ in in_order([(r0, partial(part, r0)) for r0 in range(0, len(x), rows)]):
        pass
    return out


def _matmul(x: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """The network's matrix product, also shared by the browser's BLAS implementation."""
    return x @ weight.T


def _linear(x: np.ndarray, w: dict, name: str) -> np.ndarray:
    y = _matmul(x, w[f"{name}.weight"])
    bias = w[f"{name}.bias"]
    if y.dtype == bias.dtype:
        y += bias
        return y
    return y + bias


# The people's share of every voice: the singer trained on everyone's takes together (source "human", one
# embedding for all of them; docs/THROAT.md "Everyone's voice") is this much of the machine's default blend and
# of every machine's own, the rest the synthetic singers'. The consent promises a voice trained on
# everyone's takes at once and never set to sound like one person (web/sing/consent.md); 0.3 is our choice,
# not the consent's: 70% synthetic by construction. The artist allows 0.3-0.6.
HUMAN_SHARE = 0.3


def drawn(model: Model) -> list[str]:
    """The singers a voice is mixed from by default: every trained singer the model hasn't retired. A retired
    singer (config "retired") keeps its row, so a version whose timbre names it still sings as it did, but no
    default or machine's own blend draws it."""
    retired = set(model.config.get("retired") or [])
    return [n for n in model.config["singers"] if n not in retired]


def humans(model: Model) -> list[str]:
    """The model's singers learned from people (source "human") that it still draws, if any."""
    sources = model.config.get("sources") or {}
    return [n for n in drawn(model) if sources.get(n) == "human"]


def default_mix(model: Model, pitch: float | None = None, share: float | None = None) -> dict[str, float]:
    """The trained singers blended by default: every synthetic one who sings near this pitch (MIDI; within a
    fifth of their register, the nearer the more), or all of them evenly when the model doesn't know
    their registers; and the people's singer, where the model has one, at HUMAN_SHARE (or `share`)."""
    share = HUMAN_SHARE if share is None else share
    people = humans(model)
    names = [n for n in drawn(model) if n not in people]
    if pitch is not None and model.config.get("registers"):
        away = np.array([abs(pitch - model.config["registers"][n]) for n in names])
        weights = np.clip(1.0 - away / 7.0, 0.0, None)
        if weights.sum() == 0:
            weights = (away == away.min()).astype(float)
    else:
        weights = np.ones(len(names))
    weights = weights / weights.sum() * (1.0 - share if people else 1.0)
    mix = {n: float(w) for n, w in zip(names, weights) if w > 0}
    mix.update({n: share / len(people) for n in people})
    return mix


def timbre(model: Model, mix: dict[str, float] | None, pitch: float | None = None,
           share: float | None = None) -> np.ndarray:
    """A singer embedding: the weighted mean of the trained singers' (default_mix unless a mix is
    given, the people's singer at `share` of it, HUMAN_SHARE if None; singers this model doesn't know are left
    out, and a mix of none it knows is the default)."""
    names = model.config["singers"]
    weights = np.array([float((mix or {}).get(n, 0.0)) for n in names])
    if weights.sum() <= 0:
        chosen = default_mix(model, pitch, share)
        weights = np.array([chosen.get(n, 0.0) for n in names])
    weights = weights / weights.sum()
    return weights @ model.w["singer.weight"]


def available(path: str | None = None) -> bool:
    """Whether a learned throat is there to sing (its weights ship as throat.npz beside this file)."""
    return Path(path or os.environ.get("SONGBIRD_THROAT") or MODEL).exists()


def capped(mix: dict[str, float], most: float = 0.6) -> dict[str, float]:
    """A blend normalized to 1 with no singer above `most` (the excess shared among the rest in
    proportion), so no voice is ever mostly one of the synthetic singers it learned from."""
    w = {n: max(float(x), 0.0) for n, x in mix.items() if x > 0}
    total = sum(w.values())
    if not w or total <= 0:
        return {}
    w = {n: x / total for n, x in w.items()}
    if len(w) * most < 1.0:  # too few singers to keep any under the cap: share evenly
        return {n: 1.0 / len(w) for n in w}
    for _ in range(len(w)):
        over = {n for n, x in w.items() if x > most + 1e-9}
        if not over:
            break
        excess = sum(w[n] - most for n in over)
        rest = sum(x for n, x in w.items() if n not in over)
        w = {n: most if n in over else x + excess * x / rest for n, x in w.items()}
    return w


def blend_spec(mix: dict[str, float]) -> str:
    """A blend as VoiceParams.timbre writes it: 'house-alto:0.412,house-mezzo:0.588'."""
    return ",".join(f"{n}:{x:.3f}" for n, x in sorted(mix.items()) if x >= 0.0005)


def machine_mix(seed: int, pitch: float, model: Model | None = None, most: float = 0.6,
                share: float | None = None) -> str:
    """A machine's own singer, as a timbre spec for VoiceParams.timbre: a random blend (from seed) of
    the trained singers who sing near this pitch (MIDI), never more than `most` of any one of them,
    so no machine is ever one of the synthetic singers it learned from."""
    model = model or load()
    people = humans(model)
    names = [n for n in drawn(model) if n not in people]
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
    share = HUMAN_SHARE if share is None else share
    w = w * (1.0 - share if people else 1.0)  # the people's share first, the machine's own draw in the rest
    return ",".join([f"{n}:{x:.3f}" for n, x in zip(near, w)] + [f"{n}:{share / len(people):.3f}" for n in people])


PREDICT_BLOCK = 4096  # frames, plus the network's temporal context on either side


def _predict_raw(model: Model, t: dict, cont: np.ndarray, singer: np.ndarray) -> np.ndarray:
    """The network's unscaled outputs for these frames, before whole-song global variance."""
    w = model.w
    phones = np.stack([t["prev2"], t["prev"], t["phone"], t["next"], t["next2"]], axis=-1).astype(int)
    e = w["phone.weight"][phones].reshape(len(cont), -1)
    x = _linear(np.concatenate([e, w["role.weight"][t["role"].astype(int)], cont], axis=1), w, "inp")
    del phones, e
    for i, d in enumerate(model.config["dilations"]):
        gamma, beta = np.split(_linear(singer[None], w, f"films.{i}"), 2, axis=1)
        # [x d frames back, x, x d frames on] side by side, zeros past either end: what concatenating the three
        # windows of x padded by d each side made, laid out straight
        stacked = np.zeros((len(x), 3 * x.shape[1]))
        width = x.shape[1]
        stacked[:, width: 2 * width] = x
        if d < len(x):
            stacked[d:, :width] = x[: len(x) - d]
            stacked[: len(x) - d, 2 * width:] = x[d:]
        # _linear(stacked) * (1 + gamma) + beta, then x + _linear(gelu(h)): the same products and sums, each where
        # the last left it (the same matrices into the same products), each input let go once used
        h = _matmul(stacked, w[f"convs.{i}.weight"])
        del stacked
        h += w[f"convs.{i}.bias"]
        h *= 1.0 + gamma
        h += beta
        h = _gelu(h, out=h)
        m = _matmul(h, w[f"mixes.{i}.weight"])
        del h
        m += w[f"mixes.{i}.bias"]
        x += m
        del m
    y = _linear(x, w, "out")
    del x
    return y


def predict(model: Model, t: dict, lf0: np.ndarray, singer: np.ndarray, gv: float = 1.0,
            last: int | None = None, active: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Envelope (log power, MEL points) and aperiodicity for every frame of a timeline.

    Long timelines are inferred a bounded stretch at a time, with the network's complete temporal
    context on each side. Continuous inputs are formed before slicing so log-f0 slopes stay whole;
    global variance is applied to the assembled output, with the full song's mean. last: the frame where
    the silence after the last phone begins; its frames are told of it as a silence before a breath
    (LAST_SILENCE), the frames before it as the timeline has them. active: optional per-frame boolean mask;
    frames outside it (beyond context) are skipped."""
    cont = continuous(t, lf0)
    context = sum(model.config["dilations"])
    n_frames = len(lf0)
    if active is None:
        if n_frames <= PREDICT_BLOCK:
            y = _predict_raw(model, t, cont, singer)
        else:
            y = np.empty((n_frames, len(model.w["out.bias"])))
            starts = list(range(0, n_frames, PREDICT_BLOCK))
            # Keep a tiny final tail with its preceding block: the browser uses a different
            # matrix-product implementation below 64 rows, with another rounding order.
            if len(starts) > 1 and n_frames - starts[-1] < 64:
                starts.pop()
            for a, b in zip(starts, starts[1:] + [n_frames]):
                lo, hi = max(0, a - context), min(n_frames, b + context)
                raw = _predict_raw(model, {k: v[lo:hi] for k, v in t.items()}, cont[lo:hi], singer)
                y[a:b] = raw[a - lo: b - lo]
                del raw
    else:
        y = np.zeros((n_frames, len(model.w["out.bias"])))
        on = np.flatnonzero(active)
        if len(on):
            cuts = np.flatnonzero(np.diff(on) > 2 * context)
            span_starts = np.concatenate(([on[0]], on[cuts + 1]))
            span_ends = np.concatenate((on[cuts] + 1, [on[-1] + 1]))
            for s0, s1 in zip(span_starts, span_ends):
                s0, s1 = int(s0), int(s1)
                starts = list(range(s0, s1, PREDICT_BLOCK))
                if len(starts) > 1 and s1 - starts[-1] < 64:
                    starts.pop()
                for a, b in zip(starts, starts[1:] + [s1]):
                    lo, hi = max(0, a - context), min(n_frames, b + context)
                    if hi - lo < 64 and n_frames >= 64:
                        lo = max(0, lo - (64 - (hi - lo)))
                        hi = min(n_frames, lo + 64)
                    raw = _predict_raw(model, {k: v[lo:hi] for k, v in t.items()}, cont[lo:hi], singer)
                    y[a:b] = raw[a - lo: b - lo]
                    del raw
    if last is not None and last < n_frames:
        end = n_frames
        if active is not None:
            on_tail = np.flatnonzero(active[last:])
            end = last + int(on_tail[-1]) + 1 if len(on_tail) else last
        if end > last:
            hi = min(n_frames, end + context) if active is not None else n_frames
            lo = max(0, min(last - context, hi - 64))
            if hi - lo < 64 and n_frames >= 64:
                hi = min(n_frames, lo + 64)
            tail = {k: v[lo:hi] for k, v in t.items()}
            tail["next"] = tail["next"].copy()
            tail["next"][last - lo:] = PHONES.index("breath")
            y[last:end] = _predict_raw(model, tail, cont[lo:hi], singer)[last - lo: end - lo]
            del tail
    del cont
    n_sp = len(model.sp_mean)
    sp, ap = y[:, :n_sp], y[:, n_sp:]
    if gv != 0.0:  # global variance: give back the contrast a small model averages away
        sung = t["role"] >= 2
        mu = sp[sung].mean(axis=0) if sung.any() else sp.mean(axis=0)
        scale = np.clip(np.sqrt(model.gv[:n_sp]), 1.0, 1.6) ** gv
        sp = sp - mu
        sp *= scale
        np.add(mu, sp, out=sp)
    # Preserve the multiply, add and clip order while reusing each newly owned result.
    if gv != 0.0:  # the variance calculation already made sp an owned contiguous array
        sp *= model.sp_std
    else:
        sp = sp * model.sp_std
    sp += model.sp_mean
    ap = ap * model.ap_std
    del y
    ap += model.ap_mean
    np.clip(ap, 0.0, 1.0, out=ap)
    return sp, ap


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


SHARPEN = 1.5  # how far sing() pushes a predicted envelope's formants from its trend (1 leaves it; docs/THROAT.md)


def sharpen(sp: np.ndarray, amount: float, width: int = 17) -> np.ndarray:
    """A log-power envelope on the mel grid with its peaks and valleys pushed `amount` times as far
    from its own trend (a Hann over `width` grid points), each frame's power kept. A network's
    envelope is an average, and averages flatten the formants a voice has."""
    if abs(amount - 1.0) < 1e-6:
        return sp
    from scipy.ndimage import convolve1d

    k = np.hanning(width + 2)[1:-1]
    trend = convolve1d(sp, k / k.sum(), axis=1, mode="nearest")
    out = trend + amount * (sp - trend)
    df = np.gradient(grid(sp.shape[1]))  # Hz each point stands for
    top = sp.max(axis=1, keepdims=True)
    before = np.log(np.exp(sp - top) @ df)
    after = np.log(np.exp(out - top) @ df)
    return out + (before - after)[:, None]


# ---- singing: our schedule, pitch and dynamics through the learned throat ---------------------------

RATE = 24000  # the throat sings at its training data's rate; the result is resampled to the mix's

# How long its teacher held each consonant (median seconds, by phone and place in the syllable,
# measured by forced alignment over the SoulX corpus). SoulX's sonorants run about
# twice the formant singer's (a coda n 120 ms against 49): sung under those lengths, the throat
# hears what it learned instead of consonants squeezed into half the time.
DURATIONS = {
    "B onset": 0.09, "CH onset": 0.155, "D coda": 0.05, "D coda cluster": 0.05, "D onset": 0.09, "DH onset": 0.03,
    "F coda": 0.11, "F coda cluster": 0.08, "F onset": 0.13, "F onset cluster": 0.1, "G onset": 0.06, "HH onset": 0.07,
    "HH onset cluster": 0.06, "JH coda": 0.14, "K coda": 0.09, "K coda cluster": 0.05, "K onset": 0.09,
    "K onset cluster": 0.09, "L coda": 0.13, "L coda cluster": 0.135, "L onset": 0.12, "L onset cluster": 0.08,
    "M coda": 0.13, "M onset": 0.09, "N coda": 0.12, "N coda cluster": 0.09, "N onset": 0.09, "NG coda": 0.13,
    "P coda cluster": 0.07, "P onset": 0.05, "P onset cluster": 0.09, "R coda": 0.11, "R coda cluster": 0.13,
    "R onset": 0.11, "R onset cluster": 0.07, "S coda": 0.095, "S coda cluster": 0.1, "S onset": 0.16,
    "S onset cluster": 0.11, "SH onset": 0.17, "T coda": 0.05, "T coda cluster": 0.06, "T onset": 0.1,
    "T onset cluster": 0.08, "TH onset": 0.15, "TH onset cluster": 0.07, "V coda": 0.08, "V onset": 0.08,
    "W onset": 0.09, "W onset cluster": 0.07, "Y onset": 0.11, "Z coda": 0.1, "Z coda cluster": 0.1,
}
TRACT = 1.12  # VoiceParams.tract that leaves the learned envelope where it is

# A diphthong's second half before a nasal coda, sung in the vowel. The network's AW before n, m or ng
# holds its first target (F1 800-900 Hz, F2 1700-1800) almost to the nasal and closes toward [ʊ] only in
# the nasal's own frames, where its murmur hides it: the vowel heard ends on AH (its last third 3.6 dB
# from the throat's own "sund", 8.3 dB from its open AW) and "sound" comes out "sund".
# So the last fraction of such a vowel is told as the phone given here: UW, which the throat
# sings before a nasal as [ʊ] (F1 about 450, F2 1150-1300), where its UH there is AH-like (F1 800). The
# vowel's own timing, pitch and loudness are the schedule's as ever; only what the network is told
# changes. docs/THROAT.md, "Sound, not sund".
GLIDE_TAILS = {"AW": (0.2, "UW")}
NASAL_CODAS = frozenset({"M", "N", "NG"})


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


# ---- the consonants the throat sings too softly -----------------------------------------------------

# The teacher's word-final consonants are soft and the network's softer: on H sung everyone's way
# a coda t or k comes out 22 to 48 dB under its vowel with nothing above 3 kHz (no release at
# all), a coda d 8 to 18 dB under and no different from the nasal before it, and an f a low rumble; the
# words go with them ("lit" heard "only", "laughed" "luck", "hummed" "harmed", "part" "board", "saved"
# "seh"). What tells a listener a stop is its closure and its release, and a weak fricative its hiss. So
# the formant singer's bursts and frication (songbird.phonetics BURSTS, FRICATION, as voice.sing lays them)
# go over the throat's own, its output dipped through each stop's closure and each weak fricative, and a
# coda nasal comes up a little. voice.crisp scales all of it; 0 leaves the throat's own.
# The blend: the throat's own consonant (the teacher's, as measured) stays under the rule-made one. Deeper dips and
# louder bursts (0.3/0.06, +0 dB) read the same to Whisper (7.3% against 7.1% of H's words misheard, dry) and
# sound made; these keep more of the sung consonant, softened and blended with the measured one.
CLOSURE_DIP = {True: 0.5, False: 0.2}  # what is left of the throat's output through a voiced / voiceless stop's closure
BURST = -9.0  # dB against the formant singer's burst levels (phonetics.BURSTS); subtle enough not to read as noise bursts
BURST_SPREAD = (1.5, 0.15)  # dB of level and log length one burst differs from the next, at voice.spread 1 (no two alike)
ASPIRATION = -8.0  # dB under its burst the aspiration after a voiceless stop's release starts, fading to the stop's end
WEAK_FRICATIVES = {"F": 2.0, "TH": 2.0, "V": 2.0, "DH": 0.0}  # dB over the formant singer's frication levels
FRICATIVE_DIP = 0.5  # what is left of the throat's output through a voiceless weak fricative
NASAL_LIFT = 2.0  # dB a coda nasal comes up
# A t's release on its own (the stop heard as harsh). Scylla's Band's t's, on the same notes and
# timing, have almost nothing under 4 kHz (2-3 kHz 22-27 dB under their vowels there); ours 20-27 dB more, from the
# alveolar burst's band (centred 4.7 kHz at the default tract; its 6.5 kHz band, summed in phase, mostly cancels), which
# the lead's de-esser (split 4.5 kHz) leaves while turning down what's above it (docs/THROAT.md). Turning the burst down
# only makes it quieter. The keys: the noise's shape (band-pass regions as phonetics.BURSTS writes them; None, the
# alveolar burst's); dB added to the burst; its rise and fall (s); how many times as long it lasts; `decay` (s; None, a
# flat burst), a release that falls away from its first instant as a real one does; dB added to the aspiration after it
# (which doesn't follow the burst's level); the aspiration's own shape (None, the burst's) and when it starts after the
# release (s); what is left of the throat's own t from the release to its end (1, all of it); and what is left of it
# through the closure before the release (None, CLOSURE_DIP's), the silence a coda t ("part", "heart") is heard by.
# T_AS_WAS leaves the t plain: the alveolar burst as articulate makes every stop's.
T_AS_WAS = {"shape": None, "burst": 0.0, "ramp": 0.002, "longer": 1.0, "decay": None, "aspiration": 0.0,
            "aspiration_shape": None, "aspiration_from": 0.008, "own": 1.0, "closure": None}  # every t plain
# The t chosen by ear on the performance voice: mostly 6-10 kHz with a little 3-4
# kHz 12 dB under, a release falling away over 10 ms and lasting about 30, loud enough that the lead's de-esser leaves
# "part" and "heart" a t (after the lead chain, 13-17 dB under the word, 22-25 ms long, where Scylla's heard t's are
# 11-17 dB under for 15-40 ms). Sung when STOP_RELEASE["T"] is None (by default);
# T_RELEASE.update(T_AS_WAS) sings the plain t.
T_CHOSEN = {"shape": [(8000.0, 4000.0, 0.0), (3500.0, 1500.0, -12.0)], "ramp": 0.0005, "burst": 5.0, "longer": 2.5,
            "decay": 0.01, "aspiration": -6.0, "own": 0.3}
T_RELEASE = {**T_AS_WAS, **T_CHOSEN}
# A t sung straight into the next word ("that you", "wrote this"): T_RELEASE's keys as they are there, and `rise`,
# the seconds the throat's own sound takes to come back after the stop. T_CHOSEN's t is a phrase's last ("part",
# "heart"), heard against the silence after it; between two sung sounds its 30 ms of 6-10 kHz is heard as a burst of
# noise, and the next word starts at once at full level. Here the release is darker (3.4 kHz, a little at 5.2), 5 dB
# softer and 18 ms long, and the voice returns over 30 ms: chosen by ear over one as bright and softer, and a 7 ms
# tap. voice.linked 0 sings every t as T_RELEASE has it.
T_LINKED = {"shape": [(3400.0, 1600.0, 0.0), (5200.0, 2500.0, -8.0)], "burst": 0.0, "longer": 1.5, "decay": 0.008,
            "aspiration": -6.0, "rise": 0.03}
# A d sung straight into the next word's vowel ("old and", "saved it") is carried over as singers carry it ("ol
# dand"): the network is told it begins that syllable (its word-final consonants are soft, a d there a gap with no
# hum under it), its closure and release are an onset's, and it is given time from the l or n before it. `least`:
# the seconds it lasts, taken from a longer sound before it, which keeps `keeps` of its own length; `burst`: dB
# added to the release; `longer`: how many times as long it lasts; `closure`: what is left of the throat's own sound
# through the closure, held as given (None: an onset d's, CLOSURE_DIP's).
D_LINKED = {"closure": None, "burst": -3.0, "longer": 1.0, "least": 0.07, "keeps": 0.6}
LINKED = 0.08  # s: the next word's sound begins within this of the t's end (a rest or a breath is longer)

# A release made as an airway makes one (as Chimera's physical model does, jamesondh/chimera-vocal-synth), for a
# voiceless stop's phone: the pressure behind the closure lets go in a spike (`spike` dB re the vowels, lasting
# `spike_len` s and falling away over `spike_decay`, in `spike_shape`, None for the place's own burst), there is a
# gap while the opening is still too wide for the air to hiss (`breath_from` s), and then the breath through the
# folds as they close again, coloured by the tract it passes: the formants of the vowel the mouth is at (the next
# one for an onset, the last one for a coda; F1 `f1` dB, F2 and F3 at 0 and `f3`) with `extra` regions of the
# place's own (a t's alveolar hiss, say), at `breath` dB, to the vowel (an onset, `into` s into it) or for
# `breath_len` s (a coda), falling away over `breath_decay` s (a coda; an onset fades into its vowel). `own` is
# what is left of the throat's own sound from the release to the stop's end. Measured against Scylla's 3,400
# stops on H: a broadband spike, ~10 dB down 5 ms later in 1.5-4.5 kHz, then an even breath 27 dB
# under the vowel for 30-40 ms in a coda, and a t's onset hiss above 4.5 kHz about 10 dB under it until the vowel.
# A voiced stop (B D G) is the same with `breath` None for none (its folds go on voicing), and an affricate (CH JH)
# has its fricative's own hiss (SH's, ZH's, or `fric_shape`) from `breath_from` after the spike to its end, at
# `breath` dB, in place of the breath. `closure` (None, CLOSURE_DIP's) is what is left of the throat's own sound
# through the closure: the throat starts its own ch hiss ~25 ms before the release, which a closure held silent keeps
# for the release (held as given: voice.crisp scales every other dip, and at its 0.6 a closure "5% left" kept 45%).
# None leaves a phone's release as articulate makes it (T_RELEASE's t), as STOP_AS_WAS does for every phone, by
# default: the physical releases are heard as harsh, more an artifact than a voice, on the machine's consonants.
STOP_AS_WAS: dict[str, dict | None] = {p: None for p in ("T", "K", "P", "CH", "B", "D", "G", "JH")}
STOP_RELEASE_DEFAULT = {"spike": -24.0, "spike_len": 0.003, "spike_decay": 0.0012, "spike_shape": None,
                        "breath_from": 0.006, "breath": -27.0, "f1": -12.0, "f3": -3.0, "extra": (),
                        "breath_len": 0.04, "breath_decay": 0.03, "into": 0.01, "own": 0.3, "closure": None,
                        "fric_shape": None}
# The physical stops: t, k and p tuned to Scylla's releases on H (tools/throat/stop_release.py), 3.7 dB off
# Scylla's coda t's envelope where T_CHOSEN's t is 10.9; and ch, j, b, d and g.
_SPIKE_T = [(2100.0, 1200.0, 0.0), (3600.0, 1800.0, 0.0), (6500.0, 5000.0, -6.0)]
_SPIKE_CH = [(3600.0, 1800.0, -6.0), (6500.0, 5000.0, 0.0)]
_FRIC_CH = [(3800.0, 1400.0, -4.0), (6500.0, 5000.0, 0.0)]
STOP_PHYSICAL: dict[str, dict] = {
    "T": {"spike": -6.0, "spike_shape": _SPIKE_T, "breath_from": 0.004,
          "coda": {"breath": -10.0, "extra": [(6500.0, 5000.0, -8.0)]},
          "onset": {"breath": 0.0, "extra": [(6500.0, 5000.0, 16.0)], "f1": -20.0}},
    "K": {"spike": -2.0, "breath": -11.0, "breath_from": 0.004, "extra": [(6500.0, 5000.0, -14.0)]},
    "P": {"spike": -7.0, "f1": -6.0, "breath_from": 0.004,
          "onset": {"breath": -15.0, "extra": [(6500.0, 5000.0, -16.0)]},
          "coda": {"breath": -13.0, "extra": [(6500.0, 5000.0, -12.0)]}},
    # ch and j: a closure held shut (the throat's own hiss starts 25 ms early, so its release is
    # lost: ch's 4.5-9 kHz 10 dB under Scylla's for 30 ms), a spike above 3 kHz and a hiss brighter than SH's.
    "CH": {"spike": -10.0, "spike_shape": _SPIKE_CH, "breath_from": 0.001, "breath": -9.0, "fric_shape": _FRIC_CH,
           "own": 0.15, "closure": 0.05},
    "JH": {"spike": -12.0, "spike_shape": _SPIKE_CH, "breath_from": 0.001, "breath": -15.0, "fric_shape": _FRIC_CH,
           "own": 0.6, "closure": 0.3},
    # b, d and g: their spikes 5-10 dB under Scylla's, raised, and a short breath after (a d's hiss to 30 ms into
    # its vowel); the folds go on voicing (own 1). What is left, 10-15 dB less 1.5-4.5 kHz in the 10-60 ms after the
    # release, is the throat's own voiced onset of the vowel, not the release.
    "B": {"spike": -4.0, "breath": -18.0, "f1": -6.0, "own": 1.0, "breath_from": 0.003, "into": 0.01,
          "coda": {"breath_len": 0.02, "breath_decay": 0.015}},
    "D": {"spike": 1.0, "spike_shape": _SPIKE_T, "breath": -11.0, "extra": [(6500.0, 5000.0, 4.0)], "own": 1.0,
          "breath_from": 0.003, "into": 0.03, "coda": {"breath_len": 0.03, "breath_decay": 0.02}},
    "G": {"spike": -4.0, "breath": -18.0, "extra": [(6500.0, 5000.0, -6.0)], "own": 1.0, "breath_from": 0.003,
          "into": 0.015, "coda": {"breath_len": 0.02, "breath_decay": 0.015}},
}
STOP_RELEASE: dict[str, dict | None] = dict(STOP_AS_WAS)  # STOP_RELEASE.update(STOP_PHYSICAL) sings those


def _vowel_colour(vowel: str | None, f1: float, f3: float, coda: bool) -> list[tuple[float, float, float]]:
    """Band-pass regions for breath through the tract at a vowel: its F1, F2 and F3 (a diphthong's first
    quality for an onset, its last for a coda), broad as an open glottis leaves them."""
    from .. import phonetics as ph
    v = (vowel or "AX").rstrip("012")
    if v in ph.DIPHTHONGS:
        v = ph.DIPHTHONGS[v][-1 if coda else 0]
    F = ph.VOWEL_FORMANTS.get(v, ph.VOWEL_FORMANTS["AX"])
    return [(float(F[0]), 300.0, f1), (float(F[1]), 450.0, 0.0), (float(F[2]), 700.0, f3)]


def articulate(y: np.ndarray, segs: list, sr: int, voice, rng: np.random.Generator, ref: float) -> np.ndarray:
    """The throat's output (vowels at RMS ref) with its stops given a closure and a release, its weak
    fricatives their hiss and its coda nasals a lift (see above), scaled by voice.crisp."""
    from .. import phonetics as ph
    from . import tract
    from .voice import _locus, _stop_times

    crisp = float(getattr(voice, "crisp", 1.0))
    if crisp <= 0:
        return y
    n = len(y)
    gain = np.ones(n)
    added = np.zeros(n)
    noise = rng.standard_normal(n)

    def dip(t0: float, t1: float, left: float) -> None:
        i0, i1 = max(int(t0 * sr), 0), min(int(t1 * sr), n)
        if i1 > i0:
            gain[i0:i1] = np.minimum(gain[i0:i1], 1.0 - crisp * (1.0 - left))

    def hiss(t0: float, t1: float, shape, level_db: float, ramp: float, amp: float, fading: bool = False,
             decay: float | None = None) -> None:
        i0, i1 = max(int(t0 * sr), 0), min(int(t1 * sr), n)
        if i1 <= i0:
            return
        pad = int(0.01 * sr)
        lo, hi = max(i0 - pad, 0), min(i1 + pad, n)
        shaped = tract.noise_band(noise[lo:hi], [(c * voice.tract, b, g) for c, b, g in shape], sr)
        shaped /= np.sqrt(np.mean(shaped[i0 - lo: i1 - lo] ** 2)) + 1e-12
        t = (np.arange(lo, hi) + 0.5) / sr  # the samples' times, as (np.arange(n) + 0.5) / sr gives them
        env = np.clip(np.minimum((t - t0) / ramp, (t1 - t) / ramp), 0.0, 1.0)
        if fading:
            env = env * np.clip((t1 - t) / max(t1 - t0, 1e-3), 0.0, 1.0)
        if decay is not None:  # a release: at its loudest as it opens, falling away from there
            env = env * np.exp(-np.maximum(t - t0, 0.0) / decay)
        added[lo:hi] += crisp * ref * 10.0 ** (level_db / 20.0) * amp * env * shaped

    def rise(t0: float, over: float, left: float) -> None:
        i0, i1 = max(int(t0 * sr), 0), min(int((t0 + over) * sr), n)
        if i1 > i0:
            floor = 1.0 - crisp * (1.0 - left)
            gain[i0:i1] = np.minimum(gain[i0:i1], floor + (1.0 - floor) * np.arange(i1 - i0) / (i1 - i0))

    spread = float(getattr(voice, "spread", 0.0))
    for k, s in enumerate(segs):
        if s.role not in ("onset", "coda"):
            continue
        manner, place, voiced = ph.CONSONANTS[s.phone]
        if manner in ("stop", "affricate"):
            over = float(getattr(voice, "linked", 0.0)) > 0 and carried(segs, k)
            release, _ = _stop_times(replace(s, role="onset") if over else s, voiced)
            dip(s.t0, release, CLOSURE_DIP[voiced])
            shape, level = ph.BURSTS[place]
            if place == "velar":
                f2 = _locus(s.phone, s)[1]
                shape = [(f2, 900.0, 0.0), (3600.0, 1500.0, -8.0)]
            z = rng.standard_normal(2) * spread  # each burst its own, a little louder or softer, longer or shorter
            level = level + BURST - (3.0 if voiced else 0.0) + BURST_SPREAD[0] * float(z[0])
            length = (0.008 if voiced else 0.012) * float(np.exp(BURST_SPREAD[1] * z[1]))
            aspiration = level + ASPIRATION
            ramp, decay, breath_shape, breath_from = 0.002, None, None, 0.008
            R = STOP_RELEASE.get(s.phone)
            if R is not None:  # a release as an airway makes one (STOP_RELEASE)
                R = {**STOP_RELEASE_DEFAULT, **R, **R.get(s.role, {})}  # an "onset" or "coda" dict: its own
                jitter = BURST_SPREAD[0] * float(z[0])
                if R["own"] < 1.0:
                    dip(release, s.t1, R["own"])
                if R["closure"] is not None:  # held as given, not by voice.crisp: a closure is shut
                    i0, i1 = max(int(s.t0 * sr), 0), min(int(release * sr), n)
                    gain[i0:i1] = np.minimum(gain[i0:i1], R["closure"])
                hiss(release, release + R["spike_len"], R["spike_shape"] or shape, R["spike"] + jitter, 0.0003,
                     s.amp, decay=R["spike_decay"])
                coda = s.role == "coda"
                extra = [tuple(e) for e in R["extra"]]
                if R["breath"] is None:
                    pass
                elif manner == "affricate":  # the tongue lets go slowly: its fricative's hiss, to the stop's end
                    fr_shape = R["fric_shape"] or ph.FRICATION["ZH" if voiced else "SH"][0]
                    hiss(release + R["breath_from"], s.t1 + (0.0 if coda else R["into"]), list(fr_shape) + extra,
                         R["breath"] + jitter, 0.006, s.amp, decay=R["breath_decay"] if coda else None)
                else:
                    colour = _vowel_colour(s.prev_vowel if coda and s.prev_vowel else s.next_vowel or s.prev_vowel,
                                           R["f1"], R["f3"], coda) + extra
                    end = release + R["breath_len"] if coda or not s.next_vowel else s.t1 + R["into"]
                    hiss(release + R["breath_from"], end, colour, R["breath"] + jitter, 0.003, s.amp,
                         fading=not coda, decay=R["breath_decay"] if coda else None)
                continue
            if s.phone == "T":
                T = T_RELEASE
                after = segs[k + 1] if k + 1 < len(segs) else None
                if float(getattr(voice, "linked", 0.0)) > 0 and s.role == "coda" and after is not None \
                        and after.role in ("onset", "vowel") and after.t0 - s.t1 < LINKED:
                    T = {**T_RELEASE, **T_LINKED}
                shape = T["shape"] or shape
                aspiration += T["aspiration"]
                level += T["burst"]
                length *= T["longer"]
                ramp, decay = T["ramp"], T["decay"]
                breath_shape, breath_from = T["aspiration_shape"], T["aspiration_from"]
                if T["own"] < 1.0:
                    dip(release, s.t1, T["own"])
                    if T.get("rise"):
                        rise(s.t1, T["rise"], T["own"])
                if T["closure"] is not None:
                    dip(s.t0, release, T["closure"])
            elif over:
                level += D_LINKED["burst"]
                length *= D_LINKED["longer"]
                if D_LINKED["closure"] is not None:
                    i0, i1 = max(int(s.t0 * sr), 0), min(int(release * sr), n)
                    gain[i0:i1] = np.minimum(gain[i0:i1], D_LINKED["closure"])
            hiss(release, release + length, shape, level, ramp, s.amp, decay=decay)
            if manner == "affricate":
                sh_shape, sh_level = ph.FRICATION["ZH" if voiced else "SH"]
                hiss(release, s.t1, sh_shape, sh_level, 0.01, s.amp)
            elif not voiced:
                hiss(release + breath_from, max(s.t1, release + 0.03), breath_shape or shape, aspiration, 0.004, s.amp,
                     fading=True)
        elif manner == "fricative" and s.phone in WEAK_FRICATIVES:
            if not voiced:
                dip(s.t0, s.t1, FRICATIVE_DIP)
            shape, level = ph.FRICATION[s.phone]
            hiss(s.t0, s.t1, shape, level + WEAK_FRICATIVES[s.phone], 0.03 if voiced else 0.02, s.amp)
        elif manner == "nasal" and s.role == "coda":
            i0, i1 = max(int(s.t0 * sr), 0), min(int(s.t1 * sr), n)
            gain[i0:i1] *= 10.0 ** (crisp * NASAL_LIFT / 20.0)
    noise = None  # (let go: the hisses are made)
    running_mean(gain, max(int(0.004 * sr), 1), out=gain)  # no step in the gain: a step is a click (uniform_filter1d's)
    gain *= y  # y * gain + added, made where the gain lies: the same products and sums
    gain += added
    return gain


# A real voice is part noise at the top: in the natural reference's vowels the aperiodicity runs 0.32 to 0.65 from
# 2 to 8 kHz, the throat's 0.18 to 0.48, and its harmonics stand as clean lines to 10 kHz (a buzz heard as
# robotic). voice.air sets a floor the aperiodicity never falls under, rising from AIR_FROM to AIR_TO Hz.
AIR_FROM, AIR_TO = 2500.0, 8000.0


def air_floor(air: float, points: int) -> np.ndarray:
    """The aperiodicity floor per grid point: 0 below AIR_FROM Hz, `air` from AIR_TO Hz up, linear in mel between."""
    f = grid(points)
    return air * np.clip((mel(f) - mel(AIR_FROM)) / (mel(AIR_TO) - mel(AIR_FROM)), 0.0, 1.0)


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


def carried(segs: list, k: int) -> bool:
    """Whether the k-th segment is a word's last d sung straight into the next word's vowel ("old and"): it is
    sung as that syllable's first sound ("ol dand"), as singers carry it over."""
    s, after = segs[k], segs[k + 1] if k + 1 < len(segs) else None
    return (s.role == "coda" and s.phone == "D" and after is not None and after.role == "vowel"
            and after.t0 - s.t1 < LINKED)


def carry(segs: list) -> list:
    """The schedule with each carried d (carried()) given its time: at least D_LINKED["least"] seconds, the
    sound before it ending that much sooner (never under D_LINKED["keeps"] of its own length)."""
    out = list(segs)
    for k in range(1, len(out)):
        if carried(out, k):
            s, before = out[k], out[k - 1]
            want = D_LINKED["least"] - (s.t1 - s.t0)
            if want > 0 and before.role in ("vowel", "coda") and before.t1 == s.t0:
                t0 = s.t0 - min(want, (1.0 - D_LINKED["keeps"]) * (before.t1 - before.t0))
                out[k - 1], out[k] = replace(before, t1=t0), replace(s, t0=t0)
    return out


def told(segs: list, stressed: list[bool], linked: bool = False) -> list[tuple]:
    """What the network is told is sung: (phone, start, end, stressed, level dB, role) for each of the schedule's
    segments but breaths (added after: voice.breaths), each note's onsets, its vowel and its codas, an AW
    before a nasal coda ending in its second target (GLIDE_TAILS)."""
    rows, k = [], -1
    for i, s in enumerate(segs):
        if s.role == "breath":
            continue
        role = "onset" if linked and carried(segs, i) else s.role
        note = k + 1 if role == "onset" else k
        if s.role == "vowel":
            k += 1
            note = k
        row = (s.phone, s.t0, s.t1, stressed[min(max(note, 0), len(stressed) - 1)],
               float(20.0 * np.log10(max(s.amp, 1e-6) / 0.9)), role)
        after = segs[i + 1] if i + 1 < len(segs) else None
        if s.role == "vowel" and s.phone in GLIDE_TAILS and after is not None and after.role == "coda" \
                and after.phone in NASAL_CODAS:  # sound, down: the glide's end sung in the vowel, not left to the nasal
            tail, end = GLIDE_TAILS[s.phone]
            turn = s.t1 - tail * (s.t1 - s.t0)
            rows += [(s.phone, s.t0, turn, *row[3:]), (end, turn, s.t1, *row[3:])]
            continue
        rows.append(row)
    return rows


def sing(notes, sr: int, voice, seed: int = 0, lexicon: dict | None = None, mix: str | dict | None = None,
         gv: float = 1.0, model: str | None = None, durations: dict | None = DURATIONS,
         share: float | None = None) -> np.ndarray:
    """Sung notes as a mono signal, vowels near the formant singer's level: our schedule (when each
    phone is sung), our pitch track and our dynamics, through the learned throat. share: the people's share of
    a default or a machine's own timbre (HUMAN_SHARE if None; songbird.stage sings a lead at its own)."""
    from scipy.signal import butter, resample_poly, sosfilt

    from .voice import BLOCK, breaths, pitch_track, schedule, sway

    net = load(model)
    notes = sorted(notes, key=lambda n: n.start)
    rng = np.random.default_rng(seed)
    segs = schedule(notes, voice, lexicon, durations, seed=seed)
    stressed = stresses(notes, lexicon)
    linked = float(getattr(voice, "linked", 0.0)) > 0
    if linked:
        segs = carry(segs)
    rows = told(segs, stressed, linked)
    duration = max(s.t1 for s in segs) + 0.5
    n = int(np.ceil(duration / FRAME))
    t = timeline(rows, n)
    last = int(np.searchsorted(np.arange(n) * FRAME, rows[-1][2])) if rows else None  # the silence after them all

    vowels = [s for s in segs if s.role == "vowel"]
    n_blocks = int(np.ceil(duration * RATE / BLOCK))
    accents = [voice.accent * float(np.clip(20 * np.log10(s.amp / 0.9) / 3.0, 0.0, 1.0)) for s in vowels]
    parts: dict = {}
    f0b = pitch_track(notes, n_blocks, RATE, voice, rng, [s.t1 for s in vowels], accents, segs, parts)
    f0 = np.interp(np.arange(n) * FRAME, (np.arange(n_blocks) + 0.5) * BLOCK / RATE, f0b)
    sung = np.median([n.pitch + voice.shift for n in notes])
    if isinstance(mix, str) and mix.startswith("machine:"):  # a singer of its own, drawn for this pitch
        mix = machine_mix(int(mix.split(":", 1)[1]), float(sung), net, share=share)
    active = _hush_keep(t["phone"], pad=HUSH[2] * 0.5 + 0.10)
    sp, ap = predict(net, t, np.log(f0), timbre(net, parse_mix(mix), sung, share), gv=gv, last=last, active=active)
    sp = sharpen(sp, SHARPEN)
    factor = voice.tract / TRACT
    sp, ap = warp(sp, factor), warp(ap, factor)
    if getattr(voice, "air", 0.0) > 0:  # the top of a real voice is part breath: the aperiodicity never below a floor that
        ap = np.maximum(ap, air_floor(voice.air, ap.shape[1]))  # rises from AIR_FROM Hz to voice.air at AIR_TO Hz and above
    times = np.arange(n) * FRAME
    # the vibrato's swing in loudness (the network's own envelope already moves as slowly as a singer's)
    trem = np.interp(times, (np.arange(n_blocks) + 0.5) * BLOCK / RATE, parts["tremolo"])
    sp += (sway(n, 1.0 / FRAME, voice, seed, trem) * np.log(10.0) / 10.0)[:, None]
    for s in vowels:  # a phrasing's swell grows or fades the vowel from its start to its end
        if s.swell:
            i0, i1 = np.searchsorted(times, [s.t0, s.t1])
            sp[i0:i1] += (s.swell * np.linspace(0.0, 1.0, max(i1 - i0, 1)))[:, None] * np.log(10.0) / 10.0
    voiced = np.array([PHONES[p] not in UNVOICED for p in t["phone"]])
    source = source_change(f0, voice.rd, voice.tilt, sp.shape[1])
    y = synthesize(np.where(voiced, f0, 0.0), sp, ap, RATE, rng, source=source, active=active)
    del sp, ap, source  # (the envelopes sung, they go)
    y = resample_poly(y, sr // np.gcd(sr, RATE), RATE // np.gcd(sr, RATE)) if sr != RATE else y
    # the high-pass where the song lies, a stretch at a time (its state carried: the same samples as the whole)
    high = butter(1, 60.0, btype="highpass", fs=sr, output="sos")
    state = np.zeros((high.shape[0], 2))
    for a in range(0, len(y), 1 << 16):
        y[a:a + (1 << 16)], state = sosfilt(high, y[a:a + (1 << 16)], zi=state)
    if len(y) < int(np.ceil(duration * sr)):
        y = np.concatenate([y, np.zeros(int(np.ceil(duration * sr)) - len(y))])
    y = y[: int(np.ceil(duration * sr))]
    mask = np.zeros(len(y), dtype=bool)
    for s in vowels:
        mask[int(s.t0 * sr): int(s.t1 * sr)] = True
    ref = np.sqrt(np.mean(y[mask] ** 2)) if mask.any() else 1.0
    y = articulate(y, segs, sr, voice, rng, ref)
    # y * hush, + ref * breaths, then 0.3 y / ref / sqrt 2: each where y lies (the same products, in the same order)
    y *= hush(t["phone"], sr, len(y))
    inhaled = breaths(segs, len(y), sr, voice, seed)
    inhaled *= ref
    y += inhaled
    del inhaled
    y *= 0.3
    y /= ref
    y /= np.sqrt(2.0)
    return y
