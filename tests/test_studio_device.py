"""The studio on the visitor's device (docs/WEB-STUDIO.md, "On the device"; web/studio-wasm/py/studio_device.py), run
natively here: the page's questions answered with the server's own JSON (studio.asked and studio.answer, the same
routes the Handler takes), the server's statuses for its refusals, a recording's packet naming the release's Python
and dependencies (never Pyodide's), a version's file read as data and kept by id, files handed to the page rather than
offered at an address, what a device can't do said in a sentence, singing absent until its measurement is here, and
the static site's page and headers (build_site.py)."""

import importlib.util
import json
import re
import sys
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


def test_a_job_taken_is_made_between_requests(device):
    calls = []
    job = device.studio.jobs.submit("x", "export", "a job", lambda job: calls.append(1) or {"ok": 1})
    assert job.state == "queued" and device.work() == 1 and calls == [1]
    assert ask(device, f"/api/job/{job.id}", method="GET")["json"]["result"] == {"ok": 1}


def test_singing_on_the_device_never_holds_the_take(tmp_path):
    """With singing, it is offered and says it is the device's (its own consent); a guide is made from the version on
    the page and its score handed to the page to keep; a take is checked and queued from where it was sung and its
    length alone; it isn't measured in this worker (work skips it) but handed out without audio to the page's
    measuring worker, whose answer finishes the job as the server's queue does: the way of singing made and kept, a
    refusal said as the singer's, a fault as a failure."""
    from webstudio import singing as W

    d = D.Device({"song": str(LEAD), "machine": "none", "home": str(tmp_path / "home"), "runs_with": RUNS_WITH,
                  "sing_kit": str(tmp_path / "kit")})
    offer = d.handle("GET", "/api/sing/offer", {}, None, b"", {})["json"]
    assert offer["available"] and offer["device"] is True and offer["consent"] == D.DEVICE_CONSENT != W.CONSENT
    assert "keep_days" not in offer and offer["speed"] == 90 and offer["released"]
    made = d.handle("POST", "/api/sing/guide", {}, None, json.dumps({"edits": {}, "speed": 90, "key": 0}).encode(), {})
    guide = made["json"]["guide"]
    assert made["status"] == 200 and made["json"]["song"] == LEAD.stem and made["json"]["lines"]
    assert made["file"]["type"] == "application/json" and Path(made["file"]["path"]).read_text().startswith("{")
    window = next(s["window"] for s in made["json"]["sections"] if s.get("window"))

    def take(meta, seconds="31.5"):
        body = json.dumps(meta).encode()
        return d.handle("POST", "/api/sing/take", {}, None, body,
                        {"x-sing-meta": str(len(body)), "x-sing-seconds": seconds})

    meta = {"guide": guide, "from_s": window[0], "to_s": window[1], "earlier": []}
    seconds = str(round(window[1] - window[0] + 0.6, 2))
    assert take(meta, "nan")["status"] == 400 and take(meta, "0")["status"] == 400
    assert "longer than" in take(meta, "60")["json"]["error"]
    assert "isn't one this studio made" in take({**meta, "guide": "000000000000"})["json"]["error"]
    queued = take(meta, seconds)
    assert queued["status"] == 200 and queued["json"]["state"] == "queued" and queued["json"]["estimate"] > 0
    job = queued["json"]["id"]
    assert d.work() == 0 and d.studio.jobs.get(job).state == "queued"  # never measured in this worker
    assert d.studio.singing.waiting[d.studio.jobs.get(job).key]["audio"] is None

    given = json.loads(d.handout_wire(job))
    request = json.loads(given["json"])["request"]
    assert given["status"] == 200 and d.studio.jobs.get(job).state == "running"
    assert request == {"song": LEAD.stem, "guide": guide, "from_s": window[0], "to_s": window[1], "earlier": [],
                       "seconds": float(seconds)}
    assert json.loads(d.handout_wire(job))["status"] == 404  # handed out once
    phrasing = {"phrases": {}, "source_detail": "1 sung take(s)"}
    answer = {"ok": {"measurement": {"notes": []}, "phrasing": phrasing, "portrait": "You sang.", "skipped": [],
                     "audio_seconds": 31.5, "seconds": 6.0, "peak_mb": 380}}
    done = json.loads(d.measured_wire(job, json.dumps(answer)))
    result = json.loads(done["json"])["result"]
    assert done["status"] == 200 and json.loads(done["json"])["state"] == "done"
    assert result["name"].startswith("sung-") and result["portrait"] == "You sang." and result["measurement"] == {"notes": []}
    assert d.studio.singing.store.path(result["name"]) is not None  # kept, as the server keeps a way
    assert json.loads(d.measured_wire(job, json.dumps(answer)))["status"] == 404  # finished once

    refused = take(meta, seconds)["json"]["id"]
    d.handout(refused)
    out = d.measured(refused, {"refused": "Your take sat 21 semitones above the guide's key."})["json"]
    assert out["state"] == "done" and out["result"] == {"refused": "Your take sat 21 semitones above the guide's key."}
    failed = take(meta, seconds)["json"]["id"]
    d.handout(failed)
    out = d.measured(failed, {"error": "this device ran out of memory measuring it"})["json"]
    assert out["state"] == "failed" and "ran out of memory" in out["error"]
    assert d.studio.singing.waiting == {}  # nothing of any take left waiting

    cancelled = take(meta, seconds)["json"]["id"]
    assert d.studio.jobs.cancel(cancelled)
    assert json.loads(d.handout_wire(cancelled))["status"] == 404  # let go before its turn: nothing to measure
    taken = take(meta, seconds)["json"]["id"]
    assert d.studio.singing.waiting.keys() == {d.studio.jobs.get(taken).key}  # the cancelled take's went with it
    d.handout(taken)
    assert json.loads(d.measured_wire(taken, "not json"))["status"] == 400
    assert d.studio.jobs.get(taken).state == "running"  # still the measuring worker's to answer
    assert json.loads(d.handout_wire("nope"))["status"] == 404
    # the melody is the page's singing worker's to make, never this worker's
    assert d.handle("GET", "/api/sing/melody", {"guide": guide, "from": "0", "to": "10"}, None, b"", {})["status"] == 404


def test_the_guide_is_the_version_the_page_is_on(tmp_path):
    """The guide is laid from the version as the page has it (its edits: a tempo chosen sings at that tempo), and the
    released version is offered beside it, at its own tempo."""
    d = D.Device({"song": str(LEAD), "machine": "none", "home": str(tmp_path / "home"), "runs_with": RUNS_WITH,
                  "sing_kit": str(tmp_path / "kit")})
    ours = d.handle("POST", "/api/sing/guide", {}, None, json.dumps({"speed": 100}).encode(), {})["json"]
    released = d.handle("POST", "/api/sing/guide", {}, None, json.dumps({"which": "released", "speed": 100}).encode(), {})
    assert released["status"] == 200 and released["json"]["tempo"] == 96.0 and released["json"]["guide"] != ours["guide"]
    assert ours["tempo"] == d.studio.version({}).params.tempo
    slower = d.handle("POST", "/api/sing/guide", {}, None, json.dumps({"edits": {"tempo": 70}, "speed": 100}).encode(), {})
    assert slower["status"] == 200 and slower["json"]["tempo"] == d.studio.version({"tempo": 70}).params.tempo != ours["tempo"]


def test_singing_without_its_measuring_says_why(tmp_path):
    """A site built without singing: the studio says singing isn't here, and works."""
    d = D.Device({"song": str(LEAD), "machine": "none", "home": str(tmp_path), "runs_with": RUNS_WITH})
    start = d.handle("GET", "/api/start", {}, None, b"", {})
    assert start["status"] == 200 and start["json"]["sing"]["why"] == "Singing here isn't available yet."


def test_the_static_page_and_its_headers():
    html = SITE.page(singing=False)
    assert '<meta name="studio-render" content="device">' in html and 'content="device">' in html
    assert html.index("/device.js") < html.index("/renderer.js") and "{{token}}" not in html
    assert "/sing.js" not in html and "/sing.js" in SITE.page(singing=True)
    # the hosting Worker's policy, to the letter (web/studio-site/src/policy.js), on the page and on the workers' scripts
    policy = re.search(r'PAGE_POLICY = ((?:"[^"]*"\s*\+?\s*)+);', (ROOT / "web" / "studio-site" / "src" / "policy.js").read_text())
    assert "".join(re.findall(r'"([^"]*)"', policy.group(1))) == SITE.POLICY
    assert SITE.describe("index.html")["csp"] == SITE.POLICY and "media-src 'self' blob:" in SITE.POLICY
    assert "'wasm-unsafe-eval'" in SITE.POLICY and "'unsafe-eval'" not in SITE.POLICY.replace("'wasm-unsafe-eval'", "")
    worker = SITE.describe("render/app-0123456789abcdef/studio-worker.mjs")
    assert worker["cache"] == SITE.IMMUTABLE and worker["csp"] == SITE.POLICY
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
    # every address from the root: the page is served at /v/<id> too, and its policy allows no <base>
    for name in ("index.html", "piano/index.html"):
        html = files[name].decode()
        for url in re.findall(r'\b(?:src|href)="([^"]*)"', html):
            assert url.startswith(("/", "#", "https:")), (name, url)
    assert 'href="/piano/piano.css"' in files["piano/index.html"].decode()
    assert 'href="/"' in files["piano/index.html"].decode()  # back to the studio
