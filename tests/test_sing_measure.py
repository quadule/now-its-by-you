"""Measuring a sung take on the visitor's device (web/studio-wasm/py/sing_measure.py; docs/WEB-SINGING.md, "On the
device"): the browser carries every module the measuring imports, names the kit's files a take needs, and, where
Pyodide is installed (npm ci in web/studio-wasm, its packages fetched once), measures the machine singer's planted
verse in Pyodide under node with exactly the numbers, phrasing and portrait the server's measuring process gives
the same take, leaving nothing behind in its file system."""

import ast
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WASM = ROOT / "web" / "studio-wasm"
sys.path.insert(0, str(ROOT))
from webstudio import kit as KIT, singing as W  # noqa: E402


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_bundle_carries_every_module_the_measuring_imports():
    bundle = load("sing_bundle", WASM / "tools" / "sing_bundle.py")
    carried = {Path(n).stem for n in bundle.TOOLS}
    todo, seen = ["phrasing"], set()
    while todo:  # tools/ modules imported at the top of each, from tools/phrasing.py on
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        tree = ast.parse((ROOT / "tools" / f"{name}.py").read_text())
        for node in tree.body:
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.module and not node.level else []
            todo += [n for n in names if (ROOT / "tools" / f"{n}.py").exists()]
    assert seen <= carried, seen - carried
    files = bundle.files()
    assert {"webstudio/worker.py", "webstudio/kit.py", "sing_measure.py", "world_wasm.py", "sing_dtw.py"} <= set(files)
    for name, data in files.items():  # byte for byte: tools/phrasing.py version() hashes their source
        source = ROOT / name if name.startswith(("tools/", "webstudio/")) else WASM / "py" / name
        assert source.read_bytes() == data, name


def test_kit_files_names_what_a_take_needs():
    sing_measure = load("sing_measure", WASM / "py" / "sing_measure.py")  # (py/ itself not on the path: its
    # soundfile.py is the renders' stub)
    offer = {"song": "s", "extractor": "abc", "specs": [{"guide": "g1", "templates": [-12, 0, 12]},
                                                         {"guide": "g2", "templates": [0]}]}
    assert sing_measure.kit_files(offer, "g1", [{"stamp": {"guide": "g2"}}, {"stamp": {"guide": "gone"}}]) == [
        "offer.json", "song/s.json", "guides/s.g1.score.json", "guides/s.g2.score.json",
        "measured/templates/g1.-12.abc.npz", "measured/templates/g1.+0.abc.npz", "measured/templates/g1.+12.abc.npz"]
    with pytest.raises(ValueError):
        sing_measure.kit_files(offer, "g3")


def pyodide_ready() -> bool:
    pyodide = WASM / "node_modules" / "pyodide"
    if shutil.which("node") is None or not (pyodide / "pyodide-lock.json").exists():
        return False
    lock = json.loads((pyodide / "pyodide-lock.json").read_text())["packages"]
    return all((pyodide / lock[n]["file_name"]).exists() for n in ("numpy", "scipy", "soundfile"))


BROWSER = """
import json, os
import sing_measure
where = json.load(open("/t/out/take.json"))
request = {"song": where["song"], "guide": where["guide"], "from_s": where["from_s"], "to_s": where["to_s"],
           "earlier": [], "offered": [where["guide"]], "kit": "/t/kit"}
offer = json.load(open("/t/kit/offer.json"))
needs = sing_measure.kit_files(offer, where["guide"])
said = sing_measure.answer(open("/t/out/take.wav", "rb").read(), request)
wrong = sing_measure.answer(open("/t/out/take.wav", "rb").read(), {**request, "guide": "000000000000"})
json.dump({"said": said, "wrong": wrong, "needs": [os.path.exists("/t/kit/" + n) for n in needs],
           "left": [f for f in os.listdir("/tmp") if f.startswith("songbird-take-")]}, open("/t/web.json", "w"))
"""


@pytest.mark.skipif(not pyodide_ready(), reason="Pyodide isn't installed in web/studio-wasm (npm ci)")
def test_a_take_measured_in_pyodide_is_measured_as_the_server_measures_it(tmp_path):
    kit, out = tmp_path / "kit", tmp_path / "out"
    made = subprocess.run([sys.executable, str(ROOT / "tests" / "_web_singing_take.py"), str(kit), str(out)],
                          capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stderr[-2000:]
    where = json.loads((out / "take.json").read_text())
    measurer = W.Measurer(KIT.Kit(kit), idle=60)
    try:
        native = measurer.call("take", {"song": where["song"], "guide": where["guide"], "from_s": where["from_s"],
                                        "to_s": where["to_s"], "earlier": [], "offered": [where["guide"]],
                                        "audio": (out / "take.wav").read_bytes()})
    finally:
        measurer.stop()

    dist = tmp_path / "dist"
    for tool in ("bundle.py", "sing_bundle.py"):
        zipped = "songbird.zip" if tool == "bundle.py" else "singing.zip"
        subprocess.run([sys.executable, str(WASM / "tools" / tool), str(dist / zipped)], check=True,
                       capture_output=True, timeout=300)
    (tmp_path / "browser.py").write_text(BROWSER)
    ran = subprocess.run(["node", str(WASM / "node" / "sing_run.mjs"), "--dist", str(dist), "--exec",
                          str(tmp_path / "browser.py"), "--mount", f"{tmp_path}:/t"],
                         capture_output=True, text=True, timeout=900, cwd=WASM)
    assert ran.returncode == 0, (ran.stdout + ran.stderr)[-3000:]
    web = json.loads((tmp_path / "web.json").read_text())
    assert "ok" in web["said"], web["said"]
    got = web["said"]["ok"]
    for k in ("measurement", "phrasing", "portrait", "skipped", "audio_seconds"):
        assert got[k] == native[k], k
    assert "refused" in web["wrong"]  # a guide the kit doesn't offer: the singer's to act on, not a fault
    assert all(web["needs"]) and web["left"] == []
    assert 0 < got["peak_mb"] < 1500
