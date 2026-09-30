"""How much of a rendition's time each numba kernel takes (docs/PORTABILITY.md).

    SONGBIRD_THREADS=1 uv run python tools/kernel_time.py                        # H's seed, compiled
    SONGBIRD_THREADS=1 NUMBA_DISABLE_JIT=1 uv run python tools/kernel_time.py --form refrain   # interpreted

Every numba kernel in songbird.synth.* is wrapped with a timer before the render (a kernel called from inside
another counts in its caller). Compiled, the rendition is made twice and the second timed (the kernels
compiled or loaded from numba's cache the first time); with NUMBA_DISABLE_JIT=1, once."""

from __future__ import annotations

import argparse
import importlib
import inspect
import os
import pkgutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JIT = os.environ.get("NUMBA_DISABLE_JIT", "0") != "1"


def _decorated(mod) -> set[str]:
    """The functions a module's source compiles with numba (with the compiler off, njit hands them back)."""
    try:
        lines = inspect.getsource(mod).splitlines()
    except (OSError, TypeError):
        return set()
    out = set()
    for i, line in enumerate(lines):
        if line.startswith(("@njit", "@numba.njit", "@jit")):
            for follow in lines[i + 1: i + 4]:
                if follow.startswith("def "):
                    out.add(follow[4:].split("(")[0])
                    break
    return out


def wrap_kernels() -> dict:
    """Replace every kernel in songbird's modules with a timed wrapper; returns name -> [seconds, calls, where]."""
    from songbird import synth

    for info in pkgutil.iter_modules(synth.__path__):
        importlib.import_module(f"songbird.synth.{info.name}")
    stats: dict = {}
    wrapped: dict = {}
    busy = [0]
    for name, mod in list(sys.modules.items()):
        if not name.startswith("songbird"):
            continue
        marked = _decorated(mod)
        for attr, obj in list(vars(mod).items()):
            if JIT and type(obj).__name__ != "CPUDispatcher":
                continue
            if not JIT and not (callable(obj) and attr in marked and getattr(obj, "__module__", None) == name):
                continue
            if id(obj) not in wrapped:
                py = obj.py_func if JIT else obj
                code = py.__code__
                where = f"songbird/{code.co_filename.rsplit('songbird/', 1)[-1]}:{code.co_firstlineno + 1}"
                label = f"{obj.__module__.split('.')[-1]}.{py.__name__}"
                stats[label] = [0.0, 0, where]

                def timed(*a, obj=obj, label=label, **k):
                    if busy[0]:
                        return obj(*a, **k)
                    busy[0] += 1
                    t = time.perf_counter()
                    try:
                        return obj(*a, **k)
                    finally:
                        busy[0] -= 1
                        stats[label][0] += time.perf_counter() - t
                        stats[label][1] += 1

                wrapped[id(obj)] = timed
            setattr(mod, attr, wrapped[id(obj)])
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome", nargs="?", default=str(ROOT / "songs" / "h-now-its-by-you.json"))
    ap.add_argument("--form", nargs="+", help="render only these sections")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()
    stats = wrap_kernels()

    from songbird import cli, genome
    from songbird.realize import choose_params

    g = genome.load(args.genome)
    params = choose_params(g)
    if args.form:
        params = replace(params, form=tuple(args.form))
    with tempfile.TemporaryDirectory() as d:
        render = lambda: cli.render_one(g, params, Path(d) / "out.flac", phrasing_json=g.source.get("seed_phrasing"))
        if JIT:
            render()
            for s in stats.values():
                s[0], s[1] = 0.0, 0
        t0 = time.perf_counter()
        record = render()
        total = time.perf_counter() - t0
    rows = sorted(((k, *v) for k, v in stats.items() if v[1]), key=lambda r: -r[1])
    inside = sum(r[1] for r in rows)
    print(f"id {record['id'][:12]}  {'compiled' if JIT else 'interpreted'}  {total:.2f} s, "
          f"{inside:.2f} s ({100 * inside / total:.0f}%) in the kernels")
    for label, sec, calls, where in rows[: args.top]:
        print(f"{label:30s} {sec:8.3f} s {100 * sec / total:5.1f}%  {calls:6d} calls  {where}")


if __name__ == "__main__":
    main()
