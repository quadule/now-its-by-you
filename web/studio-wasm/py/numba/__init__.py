"""numba, for the browser: `njit` hands each kernel to its JavaScript translation (kernels.gen.mjs, made by
tools/transpile.py from the same source) when there is one, and otherwise leaves it plain Python (right, but
slow). Only on the web path: songbird imports this in place of numba because web/studio-wasm/py comes first
on sys.path in Pyodide; natively nothing changes.

The JS side is registered by the loader as the module `songbird_kernels` with `kernels` (the translated
functions), `rt` (kernels/rt.mjs) and `manifest` (kernels/manifest.json as a JSON string). Arrays go to JS
as views of Pyodide's memory (no copy); the kernels write in place into them as numba does; results made
in JS are copied into new numpy arrays."""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict

import numpy as np

try:
    import songbird_kernels as _js  # registered by the loader (web/studio-wasm/node/run.mjs, web/.../index.html)
    _MANIFEST = json.loads(_js.manifest)
except ImportError:  # no JS: every kernel stays Python
    _js, _MANIFEST = None, {}

__version__ = "0.0-shim"
PORTED: dict[str, str] = {}  # kernel -> "js" | "wasm" | "python"
TIME = defaultdict(float)
CALLS = defaultdict(int)
TIMING = os.environ.get("SONGBIRD_KERNEL_TIMES") == "1"
OVERRIDES: dict[str, object] = {}  # kernel -> a callable taking the Python function (e.g. a wasm port)
DISABLED = set(filter(None, os.environ.get("SONGBIRD_JS_DISABLE", "").split(",")))

_DT = {"f8": np.float64, "i8": np.int64, "b1": np.bool_}


def _view(a: np.ndarray, back: list, layout: str | None):
    """A JS descriptor over a (float64, in place) or over a float64 copy of it (copied back after)."""
    work = a
    if a.dtype != np.float64 or (layout == "C" and not a.flags.c_contiguous) or a.ndim > 2 \
            or any(s % 8 for s in a.strides):
        work = np.ascontiguousarray(a, dtype=np.float64)
        if a.flags.writeable:
            back.append((a, work))
    if work.ndim == 0:
        work = work.reshape(1)
    addr = work.__array_interface__["data"][0]
    s = [x // 8 for x in work.strides]
    t = "f8" if a.dtype == np.float64 else ("b1" if a.dtype == np.bool_ else "i8")
    if work.ndim == 1:
        return _js.rt.view(addr, 1, work.shape[0], 0, s[0], 0, t)
    return _js.rt.view(addr, 2, work.shape[0], work.shape[1], s[0], s[1], t)


_ARRAY = re.compile(r"array\((\w+), (\d)d")


def _result(r, t: str | None):
    """A JS result as numba would have returned it (by the type numba gave it, when known)."""
    if r is None:
        return None
    if isinstance(r, (int, float, bool)):
        if t is None:
            return r
        if t.startswith(("float", "Literal[float]")):
            return float(r)
        if t.startswith(("int", "uint", "Literal[int]")):
            return int(r)
        if t == "bool":
            return bool(r)
        return r
    if hasattr(r, "d") and hasattr(r, "nd"):  # an array descriptor
        m = _ARRAY.match(t or "")
        dtype = {"float64": np.float64, "int64": np.int64, "bool": np.bool_}.get(m.group(1), np.float64) if m \
            else _DT.get(r.t, np.float64)
        shape = (int(r.n0),) if r.nd == 1 else (int(r.n0), int(r.n1))
        out = np.empty(shape, dtype=np.float64)
        if out.size:  # copied by JS into a view of out (Pyodide's assign_to fails past 2 GiB of heap)
            _js.rt.store(out.__array_interface__["data"][0], r)
        return out if dtype is np.float64 else out.astype(dtype)
    # a tuple (a JS array)
    items = list(r)
    inner = _tuple_types(t, len(items))
    return tuple(_result(x, it) for x, it in zip(items, inner))


def _tuple_types(t: str | None, n: int) -> list:
    if not t:
        return [None] * n
    m = re.match(r"UniTuple\((.+) x (\d+)\)$", t)
    if m:
        return [m.group(1)] * n
    m = re.match(r"Tuple\((.*)\)$", t)
    if m:
        parts, depth, cur = [], 0, ""
        for ch in m.group(1):
            if ch == "," and depth == 0:
                parts.append(cur.strip())
                cur = ""
                continue
            depth += ch in "(["
            depth -= ch in ")]"
            cur += ch
        parts.append(cur.strip())
        return parts
    return [None] * n


def _js_kernel(key: str, f, spec: dict):
    fn = getattr(_js.kernels, spec["js"])
    ret = spec.get("ret")
    arrays = spec.get("arrays", {})
    params = spec["params"]

    def call(*args):
        back = []
        jsargs = []
        for p, a in zip(params, args):
            if isinstance(a, np.ndarray):
                jsargs.append(_view(a, back, arrays.get(p, [None, None, None])[2]))
            elif isinstance(a, np.generic):
                jsargs.append(a.item())
            else:
                jsargs.append(a)
        r = fn(*jsargs)
        out = _result(r, ret)
        for orig, work in back:
            orig[...] = work
        return out

    call.__name__ = f.__name__
    call.py_func = f
    return call


def _timed(key, fn):
    def run(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            TIME[key] += time.perf_counter() - t
            CALLS[key] += 1
    run.__name__ = fn.__name__
    run.py_func = getattr(fn, "py_func", fn)
    return run


def njit(*args, **kw):
    def deco(f):
        key = f"{f.__module__.removeprefix('songbird.')}.{f.__name__}"
        spec = _MANIFEST.get(key)
        if key in OVERRIDES:
            fn, PORTED[key] = OVERRIDES[key](f), "wasm"
        elif spec and spec.get("ok") and key not in DISABLED:
            fn, PORTED[key] = _js_kernel(key, f, spec), "js"
        else:
            fn, PORTED[key] = f, "python"
        return _timed(key, fn) if TIMING else fn
    if args and callable(args[0]):
        return deco(args[0])
    return deco


jit = njit
