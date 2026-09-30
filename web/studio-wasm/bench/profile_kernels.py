"""Which numba kernels a render spends its time in (one thread).

usage: SONGBIRD_THREADS=1 profile_kernels.py SONG INDEX|whole [--nojit]

numba.njit is wrapped before songbird is imported, so every kernel is known by module and name. With the
JIT, one render compiles (or loads) everything, then every kernel called from Python is swapped (in every
songbird module that holds it) for a timer around it, and a second render is measured: a kernel's time
includes the kernels it calls inside numba. With --nojit (NUMBA_DISABLE_JIT=1 is set here) the kernels
are plain Python, as Pyodide would run them without a port: timed at the outermost kernel only."""

import os
import sys
import time
from collections import defaultdict
from pathlib import Path

NOJIT = "--nojit" in sys.argv
if NOJIT:
    os.environ["NUMBA_DISABLE_JIT"] = "1"
os.environ.setdefault("SONGBIRD_THREADS", "1")

import numba  # noqa: E402

KERNELS = {}  # (module, name) -> dispatcher
TIME = defaultdict(float)
CALLS = defaultdict(int)
DEPTH = [0]


def timed(key, fn):
    def run(*a, **k):
        if DEPTH[0]:
            return fn(*a, **k)
        DEPTH[0] += 1
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        finally:
            TIME[key] += time.perf_counter() - t
            CALLS[key] += 1
            DEPTH[0] -= 1
    run.__wrapped__ = fn
    return run


_njit = numba.njit


def njit(*args, **kw):
    def deco(f):
        d = _njit(**kw)(f)
        key = f"{f.__module__.removeprefix('songbird.')}.{f.__name__}"
        KERNELS[key] = d
        return timed(key, d) if NOJIT else d
    if args and callable(args[0]):
        return deco(args[0])
    return deco


numba.njit = njit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import section as S  # noqa: E402

song, which = sys.argv[1], sys.argv[2]


def render():
    return S.whole(song) if which == "whole" else S.section(song, int(which))


if not NOJIT:
    render()  # compile / load every kernel
    by_id = {id(d): key for key, d in KERNELS.items()}
    for name, mod in list(sys.modules.items()):
        if not name.startswith("songbird") or mod is None:
            continue
        for attr, val in list(vars(mod).items()):
            if id(val) in by_id:
                setattr(mod, attr, timed(by_id[id(val)], val))

t = time.perf_counter()
pcm, info = render()
total = time.perf_counter() - t
ktime = sum(TIME.values())
print(f"{'nojit' if NOJIT else 'jit'} {which}: total {total:.2f}s, kernels {ktime:.2f}s ({100 * ktime / total:.0f}%), "
      f"rest {total - ktime:.2f}s, {len(KERNELS)} kernels defined, {len(TIME)} called from Python")
acc = 0.0
for key, sec in sorted(TIME.items(), key=lambda kv: -kv[1]):
    acc += sec
    print(f"  {key:32s} {sec:8.3f}s {CALLS[key]:7d} calls  cum {100 * acc / ktime:5.1f}%")
