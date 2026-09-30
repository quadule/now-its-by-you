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
        lines = np.zeros((n_strings, pad + len(x)))
        out = np.zeros(len(x))
        W.pluck_bank(P(x), len(x), P(w32), P(taps), n_strings, n_taps, P(gains), float(coupling), P(lines), pad, P(out))
        return out
    return call


def drum_ring(f):
    def call(freqs, amps, t60s, glide, glide_time, n, sr):
        freqs, amps, t60s = F(freqs), F(amps), F(t60s)
        out = np.zeros(int(n))
        W.drum_ring(P(freqs), P(amps), P(t60s), len(freqs), float(glide), float(glide_time), int(n), float(sr), P(out))
        return out
    return call


def fx_detect(f):
    def call(key, coef):
        key = F(key)
        n, chans = key.shape
        out = np.empty(n)
        W.fx_detect(P(key), n, chans, float(coef), P(out))
        return out
    return call


def fx_apply(f):
    def call(x, lin, step, band):
        x, lin, band = F(x), F(lin), F(band)
        n, chans = x.shape
        y = np.empty_like(x)
        W.fx_apply(P(x), n, chans, P(lin), len(lin), int(step), P(band), band.shape[1], P(y))
        return y
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
    def call(held, coef):
        held = F(held)
        out = np.empty_like(held)
        W.master_recover(P(held), len(held), float(coef), P(out))
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


PORTS = {
    "synth.pluck._loop": pluck_loop,
    "synth.pluck._bank": pluck_bank,
    "synth.fx._four": lambda f: _in_place(W.fx_four),
    "synth.fx._two": lambda f: _in_place(W.fx_two),
    "synth.fx._one": lambda f: _in_place(W.fx_one),
    "synth.drum._ring": drum_ring,
    "synth.fx._detect": fx_detect,
    "synth.fx._apply": fx_apply,
    "synth.fx._products": fx_products,
    "synth.fx._block_power": lambda f: _blocks(W.fx_block_power, True),
    "synth.master._hop_power": lambda f: _blocks(W.master_hop_power, False),
    "synth.master._recover": master_recover,
    "synth.bowed.run": bowed_run,
    "synth.pipe.run": pipe_run,
}


def install() -> None:
    import numba

    numba.OVERRIDES.update(PORTS)
