"""Ask numba itself what every kernel's arguments, locals and result are, after real renders, so a port can
be typed exactly as numba typed it; and keep a few real calls (arguments and results) of each kernel, to
check a port against numba bit for bit.

usage: uv run python web/studio-wasm/tools/kernel_types.py SONG TYPES.json [CALLS_DIR] [--whole] [--gauntlet]
  TYPES.json: {kernel: {"file", "line", "fastmath", "signatures": [{"args", "return", "locals"}]}}
  CALLS_DIR:  kernel.N.npz with a0..ak (the arguments, before the call), r (the result, or r0..rk for a
              tuple), and after_a0.. for arrays the kernel changed in place.
Renders the section at index 2 (and with --whole the whole song, for types only)."""

import inspect
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SONGBIRD_THREADS", "1")
import numba  # noqa: E402
import numpy as np  # noqa: E402

KERNELS = {}
_njit = numba.njit


def njit(*args, **kw):
    def deco(f):
        d = _njit(**kw)(f)
        if f.__module__.startswith("songbird."):
            KERNELS[f"{f.__module__.removeprefix('songbird.')}.{f.__name__}"] = (d, f, kw)
        return d
    if args and callable(args[0]):
        return deco(args[0])
    return deco


numba.njit = njit
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import section as S  # noqa: E402

song, types_path = sys.argv[1], sys.argv[2]
calls_dir = Path(sys.argv[3]) if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else None

S.section(song, 2)
if "--whole" in sys.argv:
    S.whole(song)
if "--gauntlet" in sys.argv:  # every instrument, so every kernel is typed
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
    import gauntlet  # noqa: E402

    for name in gauntlet.I.known():
        try:
            gauntlet.render(name)
        except Exception as err:  # noqa: BLE001
            print(f"gauntlet {name}: {type(err).__name__}: {err}")

# import every module with kernels, so the ones this song doesn't play are listed (untyped)
import importlib  # noqa: E402
import pkgutil  # noqa: E402

import songbird.synth  # noqa: E402

for m in pkgutil.iter_modules(songbird.synth.__path__):
    importlib.import_module(f"songbird.synth.{m.name}")


def base(name: str) -> str | None:
    if name.startswith("$") or name.startswith("arg."):
        return None
    return name.split(".")[0]


out = {}
for key, (d, f, kw) in sorted(KERNELS.items()):
    sigs = []
    for sig, cres in d.overloads.items():
        locs = {}
        for name, t in cres.type_annotation.typemap.items():
            b = base(name)
            if b is not None:
                locs.setdefault(b, set()).add(str(t))
        sigs.append({"args": [str(a) for a in sig], "return": str(cres.signature.return_type),
                     "locals": {k: sorted(v) for k, v in sorted(locs.items())}})
    out[key] = {"file": inspect.getsourcefile(f).split("songbird/", 1)[1], "line": f.__code__.co_firstlineno,
                "fastmath": bool(kw.get("fastmath")), "params": list(inspect.signature(f).parameters),
                "signatures": sigs}
Path(types_path).write_text(json.dumps(out, indent=1) + "\n")
print(f"{len(out)} kernels, {sum(1 for v in out.values() if v['signatures'])} typed by these renders")

if calls_dir is not None:
    calls_dir.mkdir(parents=True, exist_ok=True)
    LIMIT = 48 * 2**20
    seen = {}

    def capture(key, d):
        def run(*a):
            k = seen.get(key, 0)
            size = sum(x.nbytes for x in a if isinstance(x, np.ndarray))
            if k >= 3 or size > LIMIT:
                return d(*a)
            before = [x.copy() if isinstance(x, np.ndarray) else x for x in a]
            r = d(*a)
            seen[key] = k + 1
            arrays = {f"a{i}": np.asarray(x) for i, x in enumerate(before)}
            arrays.update({f"after_a{i}": x for i, x in enumerate(a)
                           if isinstance(x, np.ndarray) and not np.array_equal(x, before[i], equal_nan=True)})
            if isinstance(r, tuple):
                arrays.update({f"r{i}": np.asarray(v) for i, v in enumerate(r)})
            elif r is not None:
                arrays["r"] = np.asarray(r)
            np.savez(calls_dir / f"{key}.{k}.npz", **arrays)
            return r
        return run

    by_id = {id(d): key for key, (d, f, kw) in KERNELS.items()}
    for name, mod in list(sys.modules.items()):
        if name.startswith("songbird") and mod is not None:
            for attr, val in list(vars(mod).items()):
                if id(val) in by_id:
                    setattr(mod, attr, capture(by_id[id(val)], val))
    S.section(song, 2)
    print(f"captured {sum(seen.values())} calls of {len(seen)} kernels into {calls_dir}")
