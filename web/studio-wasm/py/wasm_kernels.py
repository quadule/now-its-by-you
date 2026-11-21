"""The C/wasm kernels (wasm/kernels.c) as numba kernels: `install()` (before songbird is imported) sets
numba's shim to hand these kernels to wasm instead of their JS translations. Each adapter allocates what
the kernel would have (with numpy, in Pyodide's memory) and passes data addresses: zero copy."""

from __future__ import annotations

import numpy as np

import songbird_wasm as W  # registered by the loader: the instance's exports


def P(a: np.ndarray) -> int:
    return a.__array_interface__["data"][0]


def F(a) -> np.ndarray:
    return np.ascontiguousarray(a, dtype=np.float64)


def _in_place(kernel):
    """For the biquads, which change y in place: a C-order float64 y is worked on directly."""
    def call(y, *coefs):
        work = y if (y.dtype == np.float64 and y.flags.c_contiguous) else F(y)
        n, chans = work.shape
        kernel(P(work), n, chans, *[P(F(c)) for c in coefs])
        if work is not y:
            y[...] = work
    return call


def pluck_loop(f):
    def call(x, whole, taps, gain, release_at, release_gain, length, smooth):
        x, taps = F(x), F(taps)
        pad = int(whole) + len(taps)
        y = np.zeros(pad + int(length))
        W.pluck_loop(P(x), len(x), int(whole), P(taps), len(taps), float(gain), int(release_at),
                     float(release_gain), int(length), float(smooth), P(y))
        return y[pad:]
    return call


def pluck_bank(f):
    def call(x, wholes, taps, gains, coupling):
        x, taps, gains = F(x), F(taps), F(gains)
        n_strings, n_taps = taps.shape
        w32 = np.ascontiguousarray(wholes, dtype=np.int32)
        pad = 0
        for s in range(n_strings):
            pad = max(pad, int(wholes[s]) + n_taps)
        ring = 1
        while ring < pad:
            ring *= 2
        lines = np.zeros((n_strings, ring))
        out = np.zeros(len(x))
        W.pluck_bank(P(x), len(x), P(w32), P(taps), n_strings, n_taps, P(gains), float(coupling), P(lines), pad,
                     ring, P(out))
        return out
    return call


def _into(out: np.ndarray, like: np.ndarray, write) -> np.ndarray:
    """Have write(address) fill out (the kernel's own output argument, which may be one of its inputs): in
    place when out is C-ordered float64, else through a copy put back."""
    if out.dtype == np.float64 and out.flags.c_contiguous and out.shape == like.shape:
        write(P(out))
        return out
    work = np.empty(like.shape)
    write(P(work))
    out[...] = work.reshape(out.shape)
    return out


def drum_ring(f):
    def call(freqs, amps, t60s, glide, glide_time, n, sr):
        freqs, amps, t60s = F(freqs), F(amps), F(t60s)
        out = np.zeros(int(n))
        W.drum_ring(P(freqs), P(amps), P(t60s), len(freqs), float(glide), float(glide_time), int(n), float(sr), P(out))
        return out
    return call


def fx_detect_every(f):
    def call(key, coef, step):
        key = F(key)
        n, chans = key.shape
        out = np.empty((n + int(step) - 1) // int(step))
        W.fx_detect_every(P(key), n, chans, float(coef), int(step), P(out))
        return out
    return call


def fx_apply(f):
    def call(x, lin, step, band, y):
        x, lin, band = F(x), F(lin), F(band)
        n, chans = x.shape
        return _into(y, x, lambda at: W.fx_apply(P(x), n, chans, P(lin), len(lin), int(step), P(band), band.shape[1], at))
    return call


def fx_products(f):
    def call(x):
        x = F(x)
        out = np.empty(3)
        W.fx_products(P(x), x.shape[0], x.shape[1], P(out))
        return float(out[0]), float(out[1]), float(out[2])
    return call


def _blocks(kernel, divide):
    def call(x, block):
        x = F(x)
        n, chans = x.shape
        out = np.zeros(n // int(block))
        kernel(P(x), n, chans, int(block), P(out))
        return out
    return call


def master_recover(f):
    def call(held, coef, out):
        held = F(held)
        return _into(out, held, lambda at: W.master_recover(P(held), len(held), float(coef), at))
    return call


def master_weighted_hop_power(f):
    def call(x, p, q, hop):
        x, p, q = F(x), F(p), F(q)
        n, chans = x.shape
        state, out = np.zeros(4 * chans), np.zeros(n // int(hop))
        W.master_weighted_hop_power(P(x), n, chans, P(p), P(q), int(hop), P(state), P(out))
        return out
    return call


def bowed_run(f):
    def call(period, bridge_len, bow_v, grip, noise, pole, gain):
        a = [F(v) for v in (period, bridge_len, bow_v, grip, noise)]
        n = len(a[0])
        to_nut, to_bridge, out = np.zeros(4096), np.zeros(4096), np.zeros(n)
        W.bowed_run(*[P(v) for v in a], n, float(pole), float(gain), P(to_nut), P(to_bridge), P(out))
        return out
    return call


def pipe_run(f):
    def call(freq, breath, chiff, drive, aim, noise, feedback, damping, sr):
        a = [F(v) for v in (freq, breath, chiff, drive, aim, noise)]
        n = len(a[0])
        bore, out = np.zeros(8192), np.zeros(n)
        W.pipe_run(*[P(v) for v in a], n, float(feedback), float(damping), float(sr), P(bore), P(out))
        return out
    return call


def instruments_placed(f):
    def call(y, cos, sin, root2, width, out):
        y2 = F(y)
        n, chans = y2.shape
        if out.dtype == np.float64 and out.flags.c_contiguous and out.shape == (n, 2):
            W.instruments_placed(P(y2), n, chans, float(cos), float(sin), float(root2), float(width), P(out))
            return
        work = np.empty((n, 2))
        W.instruments_placed(P(y2), n, chans, float(cos), float(sin), float(root2), float(width), P(work))
        out[...] = work
    return call


def fx_sliding_min(f):
    def call(x, before, after, reflect, out):
        x = F(x)
        cap = int(before) + int(after) + 2
        qi, qv = np.empty(cap, dtype=np.int32), np.empty(cap)
        return _into(out, x, lambda at: W.fx_sliding_min(P(x), len(x), int(before), int(after),
                                                         1 if reflect else 0, P(qi), P(qv), at))
    return call


def fx_running_mean(f):
    def call(x, size, out):
        x = F(x)
        ring = np.empty(int(size))
        return _into(out, x, lambda at: W.fx_running_mean(P(x), len(x), int(size), P(ring), at))
    return call


def fx_follow(f):
    def call(x, detect, rise, fall, floor_db, span_db):
        x = F(x)
        n, chans = x.shape
        out = np.empty(n)
        W.fx_follow(P(x), n, chans, float(detect), float(rise), float(fall), float(floor_db), float(span_db), P(out))
        return out
    return call


def fx_saturate(f):
    def call(x, k, bias, dc, y):
        x = F(x)
        n, chans = x.shape
        return _into(y, x, lambda at: W.fx_saturate(P(x), n, chans, float(k), float(bias), float(dc), at))
    return call


def fx_hold(f):
    def call(playing, track):
        playing = np.ascontiguousarray(playing, dtype=np.bool_)
        work = track if (track.dtype == np.float64 and track.flags.c_contiguous) else F(track)
        W.fx_hold(P(playing), P(work), len(playing))
        if work is not track:
            track[...] = work
    return call


def fx_span(f):
    def call(x, floor):
        x = F(x)
        out2 = np.empty(2, dtype=np.int32)
        W.fx_span(P(x), x.shape[0], x.shape[1], float(floor), P(out2))
        return int(out2[0]), int(out2[1])
    return call


def fx_ballistics(f):
    def call(target, attack, release):
        target = F(target)
        out = np.empty_like(target)
        W.fx_ballistics(P(target), len(target), float(attack), float(release), P(out))
        return out
    return call


def master_windows(f):
    def call(y, ch, points, reach):
        y = F(y)
        n, chans = y.shape
        pts = np.ascontiguousarray(points, dtype=np.int32)
        out = np.empty((len(pts), 2 * int(reach) + 1))
        W.master_windows(P(y), n, chans, int(ch), P(pts), len(pts), int(reach), P(out))
        return out
    return call


def master_mean_ahead(f):
    def call(recovered, ahead, need, out):
        recovered, need = F(recovered), F(need)
        ring = np.empty(int(ahead) + 2)
        return _into(out, recovered, lambda at: W.master_mean_ahead(P(recovered), len(recovered), int(ahead),
                                                                    P(need), P(ring), at))
    return call


def master_abs_max(f):
    def call(y):
        y = F(y)
        n, chans = y.shape
        out = np.empty(n)
        W.master_abs_max(P(y), n, chans, P(out))
        return out
    return call


def master_over(f):
    def call(x, a):
        flat = F(x).reshape(-1)
        out = np.empty(len(flat), dtype=np.bool_)
        W.master_over(P(flat), len(flat), float(a), P(out))
        return out
    return call


def reed_read(f):
    def call(wave, increments, amplitude, out, offset, phase):
        wave, increments, amplitude = F(wave), F(increments), F(amplitude)
        work = out if (out.dtype == np.float64 and out.flags.c_contiguous) else F(out)
        ph = W.reed_read(P(wave), len(wave), P(increments), P(amplitude), len(increments), P(work), int(offset),
                         float(phase))
        if work is not out:
            out[...] = work
        return float(ph)
    return call


PORTS = {
    "synth.pluck._loop": pluck_loop,
    "synth.pluck._bank": pluck_bank,
    "synth.fx._four": lambda f: _in_place(W.fx_four),
    "synth.fx._two": lambda f: _in_place(W.fx_two),
    "synth.fx._one": lambda f: _in_place(W.fx_one),
    "synth.drum._ring": drum_ring,
    "synth.fx._detect_every": fx_detect_every,
    "synth.fx._apply": fx_apply,
    "synth.fx._products": fx_products,
    "synth.fx._block_power": lambda f: _blocks(W.fx_block_power, True),
    "synth.fx._block_peaks": lambda f: _blocks(W.fx_block_peaks, False),
    "synth.fx._sliding_min": fx_sliding_min,
    "synth.fx._running_mean": fx_running_mean,
    "synth.fx._follow": fx_follow,
    "synth.fx._saturate": fx_saturate,
    "synth.fx._hold": fx_hold,
    "synth.fx._span": fx_span,
    "synth.fx._ballistics": fx_ballistics,
    "synth.instruments._placed": instruments_placed,
    "synth.master._weighted_hop_power": master_weighted_hop_power,
    "synth.master._recover": master_recover,
    "synth.master._windows": master_windows,
    "synth.master._mean_ahead": master_mean_ahead,
    "synth.master._abs_max": master_abs_max,
    "synth.master._over": master_over,
    "synth.bowed.run": bowed_run,
    "synth.pipe.run": pipe_run,
    "synth.reed._read": reed_read,
}


def install() -> None:
    import numba

    numba.OVERRIDES.update(PORTS)
