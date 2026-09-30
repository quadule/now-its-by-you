"""Run in Pyodide (node/run.mjs --exec, with the captured calls mounted at /calls): every captured numba call
(tools/kernel_types.py CALLS_DIR) again through the browser's kernel (its JS translation or its wasm port,
whichever the shim chose) and, where small enough, through the plain Python function too; compare the
results with numba's bit for bit (float64 as it is, not rounded to 16 bits).

  node web/studio-wasm/node/run.mjs [--kernels wasm] --mount CALLS_DIR:/calls --exec web/studio-wasm/tools/check_kernels.py"""

import glob
import importlib
import os

import numpy as np

import numba

PY_LIMIT = 400_000  # elements: the plain Python kernel is run on calls this small only


def arg(v: np.ndarray):
    return v.item() if v.ndim == 0 else v.copy()


def ulps(a: np.ndarray, b: np.ndarray) -> int:
    a, b = np.asarray(a, dtype=np.float64).ravel(), np.asarray(b, dtype=np.float64).ravel()
    if a.shape != b.shape:
        return -1
    ia, ib = a.view(np.int64), b.view(np.int64)
    ia = np.where(ia < 0, np.int64(-2**63) - ia, ia)  # doubles as ordered integers
    ib = np.where(ib < 0, np.int64(-2**63) - ib, ib)
    return int(np.abs(ia - ib).max()) if a.size else 0


def compare(fn, z) -> tuple[bool, int]:
    n_args = len([k for k in z.files if k.startswith("a") and k[1:].isdigit()])
    args = [arg(z[f"a{i}"]) for i in range(n_args)]
    r = fn(*args)
    got, want = [], []
    if "r" in z.files:
        got.append(np.asarray(r)), want.append(z["r"])
    k = 0
    while f"r{k}" in z.files:
        got.append(np.asarray(r[k])), want.append(z[f"r{k}"])
        k += 1
    for i in range(n_args):
        if f"after_a{i}" in z.files:
            got.append(np.asarray(args[i])), want.append(z[f"after_a{i}"])
    same = all(np.array_equal(np.asarray(g, dtype=np.float64).view(np.int64), np.asarray(w, dtype=np.float64).view(np.int64))
               if np.asarray(g).shape == np.asarray(w).shape else False for g, w in zip(got, want))
    worst = max((ulps(g, w) for g, w in zip(got, want)), default=0)
    rel = max((float(np.abs(np.asarray(g, float) - np.asarray(w, float)).max() / (np.abs(np.asarray(w, float)).max() + 1e-300))
               for g, w in zip(got, want) if np.asarray(g).shape == np.asarray(w).shape and np.asarray(w).size), default=0.0)
    return same, (worst, rel)


rows = []
for path in sorted(glob.glob("/calls/*.npz")):
    name = os.path.basename(path)
    key = name.rsplit(".", 2)[0]
    mod, fn_name = key.rsplit(".", 1)
    fn = getattr(importlib.import_module(f"songbird.{mod}"), fn_name)
    z = np.load(path)
    port = numba.PORTED.get(key)
    same, worst = compare(fn, z)
    size = sum(z[f].size for f in z.files if f.startswith("a"))
    py = "-"
    if size <= PY_LIMIT:
        s2, w2 = compare(getattr(fn, "py_func", fn), z)
        py = "same" if s2 else f"{w2[0]} ulp, {w2[1]:.1e} of peak"
    rows.append(f"{name:36s} {port:6s} {'same' if same else f'DIFFERS max {worst[0]} ulp, {worst[1]:.1e} of peak':40s} python: {py}")
print("\n".join(rows))
