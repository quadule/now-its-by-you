"""Where the browser's render of a spec parts from the server's: every part alone and dry (studio_render.stems),
natively here, against the same made in Pyodide (node/spec_run.mjs SPEC --stems B.npz), each part's largest
difference in dB below its peak (float64: -300 dB is identical to the last bit or two).

usage: uv run python web/studio-wasm/bench/stems_diff.py SPEC.json BROWSER.npz"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("studio_render", ROOT / "web" / "studio-wasm" / "py" / "studio_render.py")
studio_render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(studio_render)


def main():
    answer = json.loads(Path(sys.argv[1]).read_text())
    native = Path(tempfile.mkdtemp()) / "native.npz"
    studio_render.stems(json.loads(answer["spec"]), native.parent, native)
    a, b = np.load(native), np.load(sys.argv[2])
    for name in a.files:
        x, y = a[name], b[name]
        peak = float(np.max(np.abs(x))) or 1.0
        d = float(np.max(np.abs(x - y))) if x.shape == y.shape else float("inf")
        same = int(np.count_nonzero(x == y))
        print(f"{name:>14}  {20 * np.log10(d / peak + 1e-300):8.1f} dB   {same / x.size:6.1%} of values bit-identical")


if __name__ == "__main__":
    main()
