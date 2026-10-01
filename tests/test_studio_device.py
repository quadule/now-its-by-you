"""The studio on the visitor's device (docs/WEB-STUDIO.md, "On the device"; web/studio-wasm/py/studio_device.py), run
natively here: the page's questions answered with the server's own JSON (studio.asked and studio.answer, the same
routes the Handler takes), the server's statuses for its refusals, a recording's packet naming the release's Python
and dependencies (never Pyodide's), a version's file read as data and kept by id, files handed to the page rather than
offered at an address, what a device can't do said in a sentence, singing absent until its measurement is here, and
the static site's page and headers (build_site.py)."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from songbird import studio as S

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / "web" / "studio-wasm" / "py"
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


D = _load("studio_device", PY / "studio_device.py")
SITE = _load("build_site", ROOT / "web" / "studio-wasm" / "tools" / "build_site.py")
RUNS_WITH = {"python": "3.12", "requirements": "# the release's\nnumpy==2.0.0\n"}


@pytest.fixture(scope="module")
def device(tmp_path_factory):
    home = tmp_path_factory.mktemp("device")
    return D.Device({"song": str(LEAD), "machine": "none", "home": str(home), "runs_with": RUNS_WITH})


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """This computer's own studio on the same song, machine and day: what a server answers."""
    return S.Studio(machine="none", home=tmp_path_factory.mktemp("server"))


def ask(device, path, body=None, method="POST", version=None, headers=None):
    data = b"" if body is None else json.dumps(body).encode()
    return device.handle(method, path, {}, version, data, headers or {})


def test_the_device_studio_has_no_thread_and_makes_every_song_in_the_browser(device):
    s = device.studio
    assert isinstance(s, S.Studio) and s.threads is False and s.makes_specs
    assert s.public is None and not s.shared
    assert s.jobs.pending == []


@pytest.mark.parametrize("path,body", [
    ("/api/song", {"edits": {"tempo": 92}}),
    ("/api/options", {"edits": {}, "block": "verse", "index": 0}),
    ("/api/keep-words", {"edits": {}}),
    ("/api/compare", {"edits": {}, "names": ["Ada", "Basil"]}),
    ("/api/arrangement", {"edits": {"tempo": 92}}),
    ("/api/sound", {"edits": {}}),
    ("/api/players", {"edits": {}}),
])
def test_the_page_s_questions_get_the_server_s_answers(device, server, path, body):
    out = ask(device, path, body)
    assert out["status"] == 200
    assert json.loads(json.dumps(out["json"])) == json.loads(json.dumps(S.answer(server, path, body)))


def test_start_says_the_device_and_what_it_can_t_do(device, server):
    out = ask(device, "/api/start", method="GET")
    start, theirs = out["json"], server.start_view()
    assert start["device"] is True and "device" not in theirs
    assert start["sing"] == {"available": False, "why": "Singing here isn't available yet."}
    assert start["out"] == "" and start["packet"] == "" and start["phrasings"] == []
    for k in ("title", "song_digest", "day", "bounds", "players", "machine", "from", "generation"):
        assert start[k] == theirs[k]


def test_the_timeline_and_a_job_asked_for(device, server):
    assert ask(device, "/api/timeline", method="GET")["json"] == server.timeline()
    assert ask(device, "/api/job/abc", method="GET") == {"status": 404, "json": {"error": "no such job"}}
    assert ask(device, "/api/nothing", {})["status"] == 404


def test_refusals_are_the_server_s_statuses(device):
    assert ask(device, "/api/song", {"edits": [1]})["status"] == 400
    assert ask(device, "/api/options", {"edits": {}, "index": "x"})["status"] == 400
    assert ask(device, "/api/render/spec", {"edits": {}, "who": "<script>"})["json"] == {"error": "no such machine"}
    assert device.handle("POST", "/api/song", {}, None, b"x" * (2**20 + 1), {})["status"] == 400
    # renders are the page's, here: never queued in the studio
    assert ask(device, "/api/listen", {"edits": {}})["status"] == 404
    assert ask(device, "/api/record", {"edits": {}})["status"] == 404
    stems = ask(device, "/api/export", {"edits": {}, "what": "stems"})
    assert stems["status"] == 400 and "can't be made in the browser yet" in stems["json"]["error"]
    assert ask(device, "/api/open/ready", {"size": 10**9})["json"] == {"ready": True}
    assert ask(device, "/api/sing", {})["json"] == {"error": "Singing here isn't available yet."}
    assert ask(device, "/api/sing/take", None, headers={"x-sing-meta": "2"})["status"] == 400


def test_a_render_spec_is_the_server_s_but_names_the_release_s_python(device, server):
    for section in (1, None):
        mine = ask(device, "/api/render/spec", {"edits": {"tempo": 92}, "section": section})["json"]
        theirs = server.render_spec({"tempo": 92}, "you", section)
        assert mine["key"] == theirs["key"] and mine["label"] == theirs["label"]
        a, b = json.loads(mine["spec"]), json.loads(theirs["spec"])
        if section is None:
            assert a.pop("packet") == RUNS_WITH and b.pop("packet") == S.Studio.runs_with(server)
        assert a == b
    # what the build records is what this studio's own recordings name
    assert SITE.runs_with() == server.runs_with()


def test_a_long_whole_song_is_warned_of_but_still_made(device):
    long = {"tempo": 60}
    answer = ask(device, "/api/render/spec", {"edits": long, "section": None})["json"]
    seconds, parts = device.studio.whole_cost(device.studio.version(long))
    assert "spec" in answer
    assert ("warn" in answer) == (not device.studio.fits_browser(seconds, parts))
    short = ask(device, "/api/render/spec", {"edits": {}, "section": None})["json"]
    assert "spec" in short and "warn" not in short


def test_files_are_handed_to_the_page(device):
    midi = ask(device, "/api/export", {"edits": {}, "what": "midi"})
    assert midi["json"]["url"].startswith("/export/") and midi["file"]["type"] == "audio/midi"
    assert Path(midi["file"]["path"]).read_bytes()[:4] == b"MThd" and midi["file"]["name"].endswith(".mid")
    piano = ask(device, "/api/piano", {"edits": {}})
    assert json.loads(Path(piano["file"]["path"]).read_text())["tempo"] > 0
    assert piano["file"]["name"] == f"{piano['json']['key']}.json"


def test_someone_s_version_is_read_as_data_and_kept_by_id(device, tmp_path):
    from test_studio_received import make_packet

    flac = make_packet(tmp_path)
    s = device.studio
    out = D.examine(flac, s.genome.title, s.machine, s.day)
    assert out["status"] == 200 and not flac.exists()  # the file read is let go
    v = out["json"]
    again = D.examine(make_packet(tmp_path), s.genome.title, s.machine, s.day)["json"]
    assert again["id"] == v["id"] and len(v["id"]) == 32  # the same file, the same id, any visit
    assert v["url"] == f"/#version={v['id']}" and v["shared"] is False and "voice" not in v["record"]
    assert device.restore(v["id"], v["record"], v["genome"], v["timeline"], False)
    start = ask(device, "/api/start", method="GET", version=v["id"])["json"]
    assert start["version"]["url"] == f"/#version={v['id']}" and start["version"]["shared"] is False
    assert start["generation"] == 3  # its child's
    song = ask(device, "/api/song", {"edits": {}}, version=v["id"])
    assert song["status"] == 200
    # a shared one keeps the site's id, and its link
    vid = "c" * 32
    shared = D.examine(make_packet(tmp_path), s.genome.title, s.machine, s.day, vid)["json"]
    assert shared["id"] == vid and shared["url"] == f"/v/{vid}"
    device.restore(vid, shared["record"], shared["genome"], shared["timeline"], True)
    assert ask(device, "/api/start", method="GET", version=vid)["json"]["version"]["url"] == f"/v/{vid}"
    # one not kept here, said; a file that isn't a version, refused with the reason
    assert ask(device, "/api/start", method="GET", version="d" * 32)["status"] == 404
    text = tmp_path / "x.flac"
    text.write_text("hello")
    refused = D.examine(text, s.genome.title, s.machine, s.day)
    assert refused["status"] == 422 and "isn't a FLAC" in refused["json"]["error"]
    assert D.examine(make_packet(tmp_path), s.genome.title, s.machine, s.day, "../x")["status"] == 404


def test_singing_measures_a_take_with_sing_measure_when_it_is_here(device, monkeypatch):
    """The measuring process's stand-in calls sing_measure.measure(take, request) and nothing else; a job taken is
    made between requests (Device.work)."""
    seen = {}
    fake = types.ModuleType("sing_measure")
    fake.measure = lambda take, request: seen.update(take=take, request=request) or {"measurement": 1}
    monkeypatch.setitem(sys.modules, "sing_measure", fake)
    m = D.Measuring()
    assert m.call("take", {"audio": b"RIFF", "guide": "g"}) == {"measurement": 1}
    assert seen == {"take": b"RIFF", "request": {"guide": "g"}}
    calls = []
    job = device.studio.jobs.submit("sing:x", "measure", "your singing", lambda job: calls.append(1) or {"ok": 1})
    assert job.state == "queued" and device.work() == 1 and calls == [1]
    assert ask(device, f"/api/job/{job.id}", method="GET")["json"]["result"] == {"ok": 1}


def test_the_static_page_and_its_headers():
    html = SITE.page(singing=False)
    assert '<meta name="studio-render" content="device">' in html and 'content="device">' in html
    assert html.index("/device.js") < html.index("/renderer.js") and "{{token}}" not in html
    assert "/sing.js" not in html and "/sing.js" in SITE.page(singing=True)
    assert SITE.describe("index.html")["csp"] == SITE.PAGE_POLICY and "blob:" in SITE.PAGE_POLICY
    assert "wasm-unsafe-eval" not in SITE.PAGE_POLICY and "wasm-unsafe-eval" in SITE.WORKER_POLICY
    worker = SITE.describe("render/app-0123456789abcdef/studio-worker.mjs")
    assert worker["cache"] == SITE.IMMUTABLE and worker["csp"] == SITE.WORKER_POLICY
    assert SITE.describe("render/py-0123456789abcdef/pyodide.asm.wasm")["type"] == "application/wasm"
    assert SITE.describe("render/bundle.json")["cache"] == "no-cache"
    assert SITE.describe("studio.js")["cache"] == "no-cache"
    files = SITE.page_files(singing=False)
    assert {"index.html", "device.js", "studio.js", "renderer.js", "notice.css", "piano/index.html", "piano/piano.js",
            "piano/identity.css"} <= set(files)
    # a shared version is anyone's bytes on the studio's origin: never served as anything that runs
    shared = SITE.NETWORK["GET /api/versions/*"]["headers"]
    assert shared["Content-Type"] == "audio/flac" and "attachment" in shared["Content-Disposition"]
    assert "sandbox" in shared["Content-Security-Policy"] and shared["X-Content-Type-Options"] == "nosniff"
    assert SITE.NETWORK["POST /api/versions"]["starts_with"] == "fLaC"
    headers = SITE.headers_file({"/index.html": SITE.describe("index.html")})
    assert headers.startswith("/index.html\n  Content-Type: text/html") and "X-Content-Type-Options: nosniff" in headers
