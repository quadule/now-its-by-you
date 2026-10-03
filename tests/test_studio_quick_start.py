"""The studio on the device, opened quickly (docs/WEB-STUDIO.md, "On the device", "A quicker start"): the page's first
questions answered ahead, a day at a time, by the studio's own code (studio_device.first_answers, which build_site.py
writes a file a day from); the studio's worker starting without scipy and soundfile (py/lazy_imports.py), which its
questions import but never run; and, with node and Pyodide, the answers the files hold being the worker's own, byte
for byte."""

import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "web" / "studio-wasm" / "py"
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
RUNS_WITH = {"python": "3.12", "requirements": "# the release's\nnumpy==2.0.0\n"}


def _load(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


D = _load("studio_device", PY / "studio_device.py")
SITE = _load("build_site", ROOT / "web" / "studio-wasm" / "tools" / "build_site.py")


def device(home: Path, day: str | None = None, **more) -> "D.Device":
    return D.Device({"song": str(LEAD), "machine": "none", "home": str(home), "runs_with": RUNS_WITH, "day": day,
                     **more})


def test_the_page_s_day_is_the_studio_s(tmp_path):
    """The page names the day (the visitor's own date, as device.js reads it), and the studio sings that day's
    version, whatever this computer's date: so what the page had before the worker was ready is the worker's too."""
    d = device(tmp_path / "a", "2027-02-14")
    assert d.studio.day == "2027-02-14" and d.view["day"] == "2027-02-14"
    start = d.handle("GET", "/api/start", {}, None, b"", {})["json"]
    assert start["day"] == "2027-02-14"
    assert device(tmp_path / "b").studio.day == date.today().isoformat()
    for bad in ("2027-2-14", "tomorrow", "2027-02-30"):
        with pytest.raises(ValueError):
            device(tmp_path / "c", bad)


def test_the_first_answers_are_the_studio_s_own(tmp_path):
    """first_answers asks what the page asks as it opens, as the page asks it, and keeps exactly what the studio
    answers: each key as device.js makes it from the request, the order the page asks."""
    day = "2026-11-02"
    answers = D.first_answers(device(tmp_path / "a", day))
    keys = list(answers)
    assert keys[:4] == ["GET /api/start ", "GET /api/sing/offer ", 'POST /api/song {"edits":{}}',
                        'POST /api/arrangement {"edits":{}}']
    assert answers["GET /api/sing/offer "][0] == 404  # no kit: as the worker answers it
    start = answers["GET /api/start "][1]
    assert start["day"] == day and start["device"] is True
    assert f'POST /api/compare {{"edits":{{}},"names":{json.dumps(start["names"], separators=(",", ":"))}}}' in answers
    song = answers['POST /api/song {"edits":{}}'][1]
    chosen = [w for w in song["words"] if w.get("sung") and w.get("changeable")]
    assert chosen and all(f'POST /api/options {{"block":"{w["block"]}","edits":{{}},"index":{w["nth"]}}}' in answers
                          for w in chosen)
    # each the same as a studio started on that day answers it, asked one at a time
    other = device(tmp_path / "b", day)
    for key, (status, said) in answers.items():
        method, path, body = key.split(" ", 2)
        out = other.handle(method, path, {}, None, body.encode(), {})
        assert (out["status"], json.dumps(out.get("json"))) == (status, json.dumps(said)), key
    # and another day's differ (the song is handed down day by day)
    assert D.first_answers(device(tmp_path / "c", "2026-11-03"))['POST /api/song {"edits":{}}'] != \
        answers['POST /api/song {"edits":{}}']


def test_the_key_is_the_one_device_js_makes():
    assert D.question("GET", "/api/start") == "GET /api/start "
    assert D.question("POST", "/api/options", {"index": 2, "edits": {}, "block": "verse"}) == \
        'POST /api/options {"block":"verse","edits":{},"index":2}'
    assert D.question("POST", "/api/compare", {"names": ["Zoë"], "edits": {}}) == \
        'POST /api/compare {"edits":{},"names":["Zoë"]}'
    shim = (ROOT / "web" / "studio-wasm" / "device.js").read_text()
    assert "function question(" in shim  # the same rule, in the page's shim (tests/studio_device_start.test.cjs)


CONTROL = r"""
import json, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[2])
import lazy_imports
lazy_imports.install(["scipy", "soundfile"])
import studio_device
d = studio_device.Device(json.loads(sys.argv[3]))
out = {}
for method, path, body in json.loads(sys.argv[4]):
    said = d.handle(method, path, {}, None, b"" if body is None else json.dumps(body).encode(), {})
    out[studio_device.question(method, path, body)] = [said["status"], said.get("json")]
real = sorted({m.split(".")[0] for m, mod in sys.modules.items()
               if m.split(".")[0] in ("scipy", "soundfile") and not isinstance(mod, lazy_imports._Module)})
from songbird.synth import fx, voice
import numpy as np
def smooth():
    return fx.uniform_filter1d(np.arange(6.0), 3).tolist()
try:
    smooth()
    needed = None
except lazy_imports.Needed as e:
    needed = e.package
lazy_imports.real("scipy")
lazy_imports.real("soundfile")
from scipy.ndimage import uniform_filter1d
from scipy.interpolate import PchipInterpolator
same = smooth() == uniform_filter1d(np.arange(6.0), 3).tolist()
tau = np.linspace(-2.0, 3.0, 41)
glide = PchipInterpolator(voice.GLIDE_TAU, [0.0, 0.0, 0.0, 0.012, 0.1, 0.265, 0.545, 0.812, 0.949, 0.99, 1.0,
                                            1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
same = same and voice.glide_shape(tau).tobytes() == glide(np.clip(tau, -1.5, 2.5)).tobytes()
print(json.dumps({"answers": out, "real": real, "needed": needed, "same": same, "lazy": lazy_imports.lazy()}))
"""

QUESTIONS = [
    ["GET", "/api/start", None], ["GET", "/api/timeline", None], ["GET", "/api/phrasings", None],
    ["POST", "/api/song", {"edits": {}}], ["POST", "/api/song", {"edits": {"tempo": 92, "roll": 1}}],
    ["POST", "/api/options", {"edits": {}, "block": "verse", "index": 0}],
    ["POST", "/api/keep-words", {"edits": {}}], ["POST", "/api/compare", {"edits": {}, "names": ["Ada", "Basil"]}],
    ["POST", "/api/arrangement", {"edits": {"tempo": 92}}], ["POST", "/api/sound", {"edits": {}}],
    ["POST", "/api/players", {"edits": {}}], ["POST", "/api/piano", {"edits": {}}],
    ["POST", "/api/export", {"edits": {}, "what": "midi"}], ["POST", "/api/export", {"edits": {}, "what": "stems"}],
    ["POST", "/api/render/spec", {"edits": {}, "section": 1}], ["POST", "/api/render/spec", {"edits": {}, "section": None}],
    ["POST", "/api/render/spec", {"edits": {"tempo": 92}, "who": "program", "section": 0}],
    ["POST", "/api/sing", {}],
]


def test_the_studio_s_questions_never_run_scipy_or_soundfile(tmp_path):
    """The studio's worker loads numpy alone: scipy and soundfile are stand-ins (lazy_imports), and every question
    the studio answers (the timeline, a render's spec, the MIDI file and the piano score among them) is answered as
    a studio with them answers it, never needing either. A stand-in used for real says which package it needs, and
    once that is loaded it is the package's own function."""
    config = {"song": str(LEAD), "machine": "none", "home": str(tmp_path / "lazy"), "runs_with": RUNS_WITH,
              "day": "2026-12-01"}
    ran = subprocess.run([sys.executable, "-c", CONTROL, str(ROOT), str(PY), json.dumps(config), json.dumps(QUESTIONS)],
                         cwd=ROOT, capture_output=True, text=True, env={**os.environ, "NUMBA_DISABLE_JIT": "1"},
                         timeout=600, check=False)
    assert ran.returncode == 0, ran.stderr[-3000:]
    got = json.loads(ran.stdout.strip().splitlines()[-1])
    assert got["real"] == [] and got["needed"] == "scipy" and got["same"] is True and got["lazy"] == []
    d = device(tmp_path / "eager", "2026-12-01")
    for method, path, body in QUESTIONS:
        said = d.handle(method, path, {}, None, b"" if body is None else json.dumps(body).encode(), {})
        key = D.question(method, path, body)
        assert got["answers"][key] == [said["status"], json.loads(json.dumps(said.get("json")))], key


def sing_kit(folder: Path) -> Path:
    """A singing kit's offer for the lead song (all the studio's worker reads of a kit)."""
    import hashlib

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "offer.json").write_text(json.dumps({
        "kit": 1, "song": LEAD.stem, "title": "Now It's By You", "genome": hashlib.sha256(LEAD.read_bytes()).hexdigest(),
        "extractor": "0123456789ab", "set": {"id": "a", "name": "Set A", "about": ""}, "default": "a.k0.t90",
        "specs": [{"id": "a.k0.t90", "set": "a", "key": 0, "tempo": 90, "guide": "523190fdf68a", "duration": 151.2,
                   "templates": [-12, 0, 12]}]}))
    return folder


def test_the_build_s_first_answers_are_the_worker_s_byte_for_byte(tmp_path):
    """build_site.py works the first answers out natively, in processes of its own; the page's worker works them out
    in Pyodide, with numpy alone. For the first day the build makes, a day well ahead and its last, with singing
    offered: the same questions, and each answer the page receives the same JSON, byte for byte."""
    pyodide = ROOT / "web" / "studio-wasm" / "node_modules" / "pyodide"
    if shutil.which("node") is None or not (pyodide / "pyodide.mjs").is_file():
        pytest.skip("needs node and Pyodide (npm ci in web/studio-wasm)")
    render = SITE._module(SITE.HERE / "tools" / "build_render.py", "build_render")
    py_files, _, _ = render.pyodide_files()
    (tmp_path / "py").mkdir()
    for name, data in py_files.items():
        (tmp_path / "py" / name).write_bytes(data)
    zipped, _ = render.program_zip()
    (tmp_path / "songbird.zip").write_bytes(zipped)
    kit = sing_kit(tmp_path / "kit")
    days = SITE.window(date.today())
    days = [days[0], days[len(days) // 3], days[-1]]
    native = {"song": str(LEAD), "machine": "none", "runs_with": SITE.runs_with(), "sing_kit": str(kit)}
    files = SITE.first_answers(native, days, jobs=2)
    assert sorted(files) == sorted(f"{d}.gzip" for d in days)
    worker = {"song": "/app/songs/h-now-its-by-you.json", "machine": "none", "runs_with": SITE.runs_with(),
              "sing_kit": "/kit"}
    ran = subprocess.run(["node", str(ROOT / "tests" / "_first_answers.mjs"), str(tmp_path / "py"),
                          str(tmp_path / "songbird.zip"), str(kit / "offer.json"), json.dumps(worker), *days],
                         capture_output=True, text=True, timeout=900, check=False)
    assert ran.returncode == 0, ran.stderr[-3000:]
    theirs = json.loads(ran.stdout.strip().splitlines()[-1])
    assert theirs.pop("lazy") == ["scipy", "soundfile"]  # never needed: neither was fetched
    for day in days:
        mine = json.loads(gzip.decompress(files[f"{day}.gzip"]))
        assert mine["v"] == 1 and mine["day"] == day
        assert list(mine["answers"]) == list(theirs[day])
        for key, (status, answer) in mine["answers"].items():
            assert [status, json.dumps(answer)] == theirs[day][key], (day, key)
        start = mine["answers"]["GET /api/start "][1]
        assert start["day"] == day and start["sing"]["available"] is True


def test_the_window_of_days():
    days = SITE.window(date(2026, 12, 30), 400)
    assert days[0] == "2026-12-28" and days[2] == "2026-12-30" and days[-1] == "2028-02-02" and len(days) == 402
    assert SITE.window(date(2026, 12, 30), 0) == []
