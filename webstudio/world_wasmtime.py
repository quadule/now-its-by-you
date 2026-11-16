"""pyworld, for a computer without it: `harvest` and `cheaptrick` as pyworld 0.3.5 has them (the same signatures and
defaults), computed by the same world.wasm the browser runs (web/studio-wasm/world/: WORLD's own C++ compiled to
wasm), under wasmtime, which comes ready-made for Windows, macOS and Linux and needs no compiler. Only what measuring
a sung take uses (tools/phrasing.py analyze_take); webstudio/standins.py puts this module in pyworld's place when
pyworld isn't installed. web/studio-wasm/py/world_wasm.py is the same over the browser's WebAssembly.

The module is compiled once; every analysis gets an instance of its own, with its own memory, let go when it is
done (inside `with session():` one instance serves every call, as in the browser). CheapTrick's spectrogram is made
CHUNK frames at a time and copied out into the numpy array returned."""

from __future__ import annotations

import contextlib
import ctypes
import functools
from pathlib import Path

import numpy as np

WASM = Path(__file__).resolve().parent.parent / "web" / "studio-wasm" / "world" / "world.wasm"

default_f0_floor = 71.0
default_f0_ceil = 800.0
default_frame_period = 5.0
CHUNK = 256  # CheapTrick frames made at once (2 MB of spectrogram at an FFT of 2048)

PEAK = {"bytes": 0, "arrays": 0}  # as world_wasm's: the largest memory an instance held, and WORLD's arrays in it
_session: list = []


@functools.cache
def _module():
    import wasmtime

    engine = wasmtime.Engine()
    return engine, wasmtime.Module(engine, WASM.read_bytes())


def _c_doubles(name: str, a) -> np.ndarray:
    """pyworld's own check: a C-ordered float64 vector, as its Cython signature demands."""
    if not isinstance(a, np.ndarray) or a.dtype != np.float64 or a.ndim != 1 or not a.flags.c_contiguous:
        raise ValueError(f"{name} must be a C-contiguous float64 vector (as pyworld requires)")
    return a


class _Instance:
    """One instance of world.wasm: its store, its exports, its memory and what has been allocated in it."""

    def __init__(self):
        import wasmtime

        engine, module = _module()
        self.store = wasmtime.Store(engine)
        instance = wasmtime.Instance(self.store, module, [])
        self.x = instance.exports(self.store)
        self.memory = self.x["memory"]
        self.x["_initialize"](self.store)
        self.held: list[int] = []

    def call(self, name: str, *args):
        return self.x[name](self.store, *args)

    def alloc(self, n_doubles: int) -> int:
        p = int(self.call("world_alloc", 8 * max(int(n_doubles), 1)))
        if not p:
            raise MemoryError("WORLD's analysis ran out of memory")
        self.held.append(p)
        return p

    def view(self, p: int, n: int) -> np.ndarray:
        """n doubles of the instance's memory at p (a fresh view: a grown memory moves)."""
        base = ctypes.addressof(self.memory.data_ptr(self.store).contents)
        return np.ctypeslib.as_array((ctypes.c_double * n).from_address(base + p))

    def put(self, p: int, a: np.ndarray) -> None:
        self.view(p, len(a))[:] = a

    def get(self, p: int, out: np.ndarray) -> np.ndarray:
        out.reshape(-1)[:] = self.view(p, out.size)
        return out

    def release(self) -> None:
        PEAK["bytes"] = max(PEAK["bytes"], int(self.memory.data_len(self.store)))
        PEAK["arrays"] = max(PEAK["arrays"], int(self.call("world_peak_bytes")))
        for p in self.held:
            self.call("world_free", p)
        self.held = []

    def done(self) -> None:
        self.release()
        self.x = self.memory = self.store = None


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
        m = int(w.call("world_harvest_length", fs, n, float(frame_period)))
        px, pt, pf = w.alloc(n), w.alloc(m), w.alloc(m)
        w.put(px, x)
        w.call("world_harvest", px, n, fs, float(f0_floor), float(f0_ceil), float(frame_period), pt, pf)
        f0, t = w.get(pf, np.zeros(m)), w.get(pt, np.zeros(m))
    return f0, t


def cheaptrick(x, f0, temporal_positions, fs, q1=-0.15, f0_floor=default_f0_floor, fft_size=None):
    """CheapTrick spectral envelope: the spectrogram (frames, fft_size // 2 + 1), as pyworld.cheaptrick."""
    x, f0 = _c_doubles("x", x), _c_doubles("f0", f0)
    temporal_positions = _c_doubles("temporal_positions", temporal_positions)
    fs = int(fs)
    with _instance() as w:
        size = int(fft_size) if fft_size is not None else int(w.call("world_cheaptrick_fft_size", fs, float(f0_floor)))
        bins, n, m = size // 2 + 1, len(x), len(f0)
        out = np.zeros((m, bins))
        px, pt, pf, ps = w.alloc(n), w.alloc(m), w.alloc(m), w.alloc(CHUNK * bins)
        w.put(px, x)
        w.put(pt, temporal_positions)
        w.put(pf, f0)
        if not w.call("world_cheaptrick_begin", fs, size, float(q1)):
            raise RuntimeError("CheapTrick is already running in this instance")
        try:
            for i in range(0, m, CHUNK):
                k = min(CHUNK, m - i)
                w.call("world_cheaptrick_frames", px, n, fs, pt + 8 * i, pf + 8 * i, k, ps)
                w.get(ps, out[i : i + k])
        finally:
            w.call("world_cheaptrick_end")
    return out
