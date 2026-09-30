"""The browser's kernels keep step with songbird's (docs/BROWSER-RENDER.md): web/studio-wasm/kernels is the
numba kernels translated to JavaScript, typed as numba typed them, and a few ported to C by hand. A change to a
kernel's source that isn't carried there would make the web studio sing an older program. This asks
tools/transpile.py --check, which writes nothing: it translates again in memory and compares, and compares
each kernel's source digest with the one its types and C port were made from. No Pyodide needed."""

import importlib.util
import json
from pathlib import Path

WASM = Path(__file__).resolve().parents[1] / "web" / "studio-wasm"


def transpile():
    spec = importlib.util.spec_from_file_location("transpile", WASM / "tools" / "transpile.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_browsers_kernels_are_current():
    t = transpile()
    problems = t.stale()
    assert not problems, "web/studio-wasm's kernels are stale:\n  " + "\n  ".join(problems) + "\n" + t.REGENERATE


def test_the_check_writes_nothing():
    kernels = [WASM / "kernels" / n for n in ("kernels.gen.mjs", "manifest.json", "types.json")]
    before = [(p.stat().st_mtime_ns, p.read_bytes()) for p in kernels]
    transpile().stale()
    assert [(p.stat().st_mtime_ns, p.read_bytes()) for p in kernels] == before


def test_every_kernel_is_translated_or_ported_by_hand():
    manifest = json.loads((WASM / "kernels" / "manifest.json").read_text())
    assert {k: m["why"] for k, m in manifest.items() if not m["ok"]} == {}
