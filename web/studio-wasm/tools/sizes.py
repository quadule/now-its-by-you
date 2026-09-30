"""What a first visit downloads: Pyodide, numpy, scipy, the program and the kernels, raw and compressed
(gzip -9, and brotli if the module is installed), as a static host or CDN would send them.

usage: uv run python web/studio-wasm/tools/sizes.py"""

import gzip
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY = HERE / "node_modules" / "pyodide"
FILES = [PY / "pyodide.mjs", PY / "pyodide.asm.mjs", PY / "pyodide.asm.wasm", PY / "python_stdlib.zip",
         PY / "pyodide-lock.json", *sorted(PY.glob("numpy-*.whl")), *sorted(PY.glob("scipy-*.whl")),
         HERE / "dist" / "songbird.zip", HERE / "kernels" / "kernels.gen.mjs", HERE / "kernels" / "rt.mjs",
         HERE / "kernels" / "hand.mjs", HERE / "wasm" / "kernels.wasm"]

try:
    import brotli
except ImportError:
    brotli = None

tot = [0, 0, 0]
print(f"{'file':52s} {'raw MiB':>8s} {'gzip':>8s} {'brotli':>8s}")
for f in FILES:
    data = f.read_bytes()
    g = len(gzip.compress(data, 9))
    b = len(brotli.compress(data, quality=11)) if brotli else 0
    tot = [tot[0] + len(data), tot[1] + g, tot[2] + b]
    print(f"{str(f.relative_to(HERE)):52s} {len(data) / 2**20:8.2f} {g / 2**20:8.2f} {b / 2**20:8.2f}")
print(f"{'total':52s} {tot[0] / 2**20:8.2f} {tot[1] / 2**20:8.2f} {tot[2] / 2**20:8.2f}")
