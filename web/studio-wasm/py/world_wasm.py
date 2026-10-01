"""pyworld, for the browser: `harvest` and `cheaptrick` as pyworld 0.3.5 has them (the same signatures and
defaults), computed by WORLD's own C++ compiled to wasm (world/world.wasm; docs/WEB-SINGING.md, "On the
device"). Only what measuring a sung take uses (tools/phrasing.py analyze_take); py/sing_measure.py puts this
module in pyworld's place, in the browser only.

The loader registers the JS module `songbird_world` (world/world.mjs): `instance()` makes a fresh instance of
the compiled module, with a memory of its own. Inside `with session():` (py/sing_measure.py holds one for each
take) every call uses one instance and frees what it allocated, so its allocator reuses the same memory piece
after piece and the memory peaks at what the largest piece needs (Harvest: about 3.5 MB for every second
analysed at once); the instance and its memory are let go when the session ends. Outside a session each call
has an instance of its own. CheapTrick's spectrogram is made CHUNK frames at a time and copied out into the
numpy array returned, so it is never whole in the module's memory too."""

from __future__ import annotations

import contextlib

import numpy as np
from js import Float64Array

import songbird_world as _js  # registered by the loader (world/world.mjs)

default_f0_floor = 71.0
default_f0_ceil = 800.0
default_frame_period = 5.0
CHUNK = 256  # CheapTrick frames made at once (2 MB of spectrogram at an FFT of 2048)

# the largest memory an instance has held, and the most WORLD's own arrays filled of it at once (the rest is
# what its allocator couldn't reuse), for the measuring's own report
PEAK = {"bytes": 0, "arrays": 0}
_session: list = []  # the instance of the session open, if one is


def _c_doubles(name: str, a) -> np.ndarray:
    """pyworld's own check: a C-ordered float64 vector, as its Cython signature demands."""
    if not isinstance(a, np.ndarray) or a.dtype != np.float64 or a.ndim != 1 or not a.flags.c_contiguous:
        raise ValueError(f"{name} must be a C-contiguous float64 vector (as pyworld requires)")
    return a


class _Instance:
    """One instance of world.wasm: its exports, its memory and what has been allocated in it."""

    def __init__(self):
        self.w = _js.instance()
        self.held: list[int] = []

    def alloc(self, n_doubles: int) -> int:
        p = int(self.w.world_alloc(8 * max(int(n_doubles), 1)))
        if not p:
            raise MemoryError("WORLD's analysis ran out of memory")
        self.held.append(p)
        return p

    def view(self, p: int, n: int):
        return Float64Array.new(self.w.memory.buffer, p, n)  # a fresh view: a grown memory detaches the old ones

    def put(self, p: int, a: np.ndarray) -> None:
        self.view(p, len(a)).assign(a)

    def get(self, p: int, out: np.ndarray) -> np.ndarray:
        self.view(p, out.size).assign_to(out.reshape(-1))
        return out

    def release(self) -> None:
        """What this call allocated freed (the memory itself stays the instance's, for the next call)."""
        PEAK["bytes"] = max(PEAK["bytes"], int(self.w.memory.buffer.byteLength))
        PEAK["arrays"] = max(PEAK["arrays"], int(self.w.world_peak_bytes()))
        for p in self.held:
            self.w.world_free(p)
        self.held = []

    def done(self) -> None:
        self.release()
        self.w = None


@contextlib.contextmanager
def session():
    """One instance for every call inside (a session inside a session shares the outer one's), let go at the end."""
    if _session:
        yield
        return
    _session.append(_Instance())
    try:
        yield
    finally:
        _session.pop().done()


@contextlib.contextmanager
def _instance():
    if _session:
        w = _session[0]
        try:
            yield w
        finally:
            w.release()
    else:
        w = _Instance()
        try:
            yield w
        finally:
            w.done()


def harvest(x, fs, f0_floor=default_f0_floor, f0_ceil=default_f0_ceil, frame_period=default_frame_period):
    """Harvest F0 extraction: (f0, temporal_positions), as pyworld.harvest."""
    x = _c_doubles("x", x)
    fs = int(fs)
    with _instance() as w:
        n = len(x)
        m = int(w.w.world_harvest_length(fs, n, float(frame_period)))
        px, pt, pf = w.alloc(n), w.alloc(m), w.alloc(m)
        w.put(px, x)
        w.w.world_harvest(px, n, fs, float(f0_floor), float(f0_ceil), float(frame_period), pt, pf)
        f0, t = w.get(pf, np.zeros(m)), w.get(pt, np.zeros(m))
    return f0, t


def cheaptrick(x, f0, temporal_positions, fs, q1=-0.15, f0_floor=default_f0_floor, fft_size=None):
    """CheapTrick spectral envelope: the spectrogram (frames, fft_size // 2 + 1), as pyworld.cheaptrick."""
    x, f0 = _c_doubles("x", x), _c_doubles("f0", f0)
    temporal_positions = _c_doubles("temporal_positions", temporal_positions)
    fs = int(fs)
    with _instance() as w:
        size = int(fft_size) if fft_size is not None else int(w.w.world_cheaptrick_fft_size(fs, float(f0_floor)))
        bins, n, m = size // 2 + 1, len(x), len(f0)
        out = np.zeros((m, bins))
        px, pt, pf, ps = w.alloc(n), w.alloc(m), w.alloc(m), w.alloc(CHUNK * bins)
        w.put(px, x)
        w.put(pt, temporal_positions)
        w.put(pf, f0)
        if not w.w.world_cheaptrick_begin(fs, size, float(q1)):
            raise RuntimeError("CheapTrick is already running in this instance")
        try:
            for i in range(0, m, CHUNK):
                k = min(CHUNK, m - i)
                w.w.world_cheaptrick_frames(px, n, fs, pt + 8 * i, pf + 8 * i, k, ps)
                w.get(ps, out[i : i + k])
        finally:
            w.w.world_cheaptrick_end()
    return out
