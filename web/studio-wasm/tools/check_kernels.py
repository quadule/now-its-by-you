"""Run in Pyodide (node/run.mjs --exec, with the captured calls mounted at /calls): every captured numba call
(tools/kernel_types.py CALLS_DIR) again through the browser's kernel (its JS translation or its wasm port,
whichever the shim chose) and, where small enough, through the plain Python function too; compare the
results with numba's bit for bit (float64 as it is, not rounded to 16 bits).

With --kernels wasm (the SIMD build, kernels-simd.wasm), the voice's matrix product too: matmul_blas against
scipy's blas.dgemm, which it must equal bit for bit (py/web_patches.py), on inputs of every magnitude in shapes
around OpenBLAS's blocks of k and on the network's own weights. Then tools/transpile.py --stamp-wasm.

  node web/studio-wasm/node/run.mjs [--kernels wasm] --mount CALLS_DIR:/calls --exec web/studio-wasm/tools/check_kernels.py
  (without --mount, the matrix product alone)"""

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
    for j, i in (z["alias"] if "alias" in z.files else ()):  # an out that was an input itself (in place)
        args[j] = args[i]
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


def matmul_rows() -> list[str]:
    """matmul_blas against blas.dgemm (as web_patches calls each), every bit: random inputs of every magnitude,
    with zero rows, for each k around OpenBLAS's blocks (Q 120: 120, 240, 241, 480, ...) and column counts that
    leave every remainder of the kernel's eight; then the network's own weights on such inputs."""
    import web_patches

    kernel = web_patches._kernel()
    if kernel is None:
        return ["matmul_blas                          -      not loaded (kernels.wasm, no SIMD): dgemm stays"]
    same = lambda a, b: a.shape == b.shape and np.array_equal(a.view(np.int64), b.view(np.int64))
    rng = np.random.default_rng(2026)
    rand = lambda *shape: rng.standard_normal(shape) * np.exp2(rng.integers(-30, 30, shape))
    cases = [(n, k, m) for k in (1, 2, 3, 7, 64, 119, 120, 121, 122, 123, 160, 161, 200, 239, 240, 241, 243, 250,
                                 300, 359, 360, 361, 479, 480, 481, 600, 1000)
             for n, m in ((64, 160), (65, 161), (67, 163), (130, 2), (101, 3), (66, 1), (99, 15), (4501, 160))]
    bad = []
    for n, k, m in cases:
        x, w = rand(n, k), rand(m, k)
        x[::7] = 0.0
        x[3::11] = -0.0
        if not same(web_patches._dgemm_matmul(x, w), web_patches._simd_product(kernel, x, w)):
            bad.append(f"{n}x{k}@{k}x{m}")
    rows = [f"{'matmul_blas, random':36s} simd   {'same' if not bad else 'DIFFERS ' + ', '.join(bad[:6]):40s}"
            f" ({len(cases) - len(bad)}/{len(cases)} shapes)"]
    from songbird.synth import throat

    weights = {k: v for k, v in throat.load().w.items() if k.endswith(".weight") and v.ndim == 2 and v.shape[1] > 1}
    bad = []
    for name, w in sorted(weights.items()):
        x = rng.standard_normal((4501, w.shape[1]))
        if not same(web_patches._dgemm_matmul(x, w), web_patches._simd_product(kernel, x, w)):
            bad.append(name)
    rows.append(f"{'matmul_blas, the network':36s} simd   {'same' if not bad else 'DIFFERS ' + ', '.join(bad[:6]):40s}"
                f" ({len(weights) - len(bad)}/{len(weights)} weights, {sorted({w.shape for w in weights.values()})})")
    return rows


rows += matmul_rows()
print("\n".join(rows))
