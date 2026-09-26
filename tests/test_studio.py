"""The studio: a page on this computer only that shows your version of the song, lets you change it and
records it. Its server answers only its own page; its words never use the code's names; its today is the
command line's; a packet opens as the parent; previews are made and served; a recording is a packet whose
marks say what a person chose (never who) and which renders again byte for byte."""

import http.client
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from songbird import drift as D, explain, harvest as H, pack, studio as S
from songbird.genome import load
from songbird.realize import choose_params
from songbird.synth import master

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
B = ROOT / "songs" / "b-coal-from-the-fire.json"
FORBIDDEN = re.compile(r"\b(genome|drift|harvest|hash|knob|params?|seed)\b", re.I)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def served(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    server = S.serve(studio, 18766)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1]
    server.shutdown()
    server.server_close()


def ask(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    head = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    c.request(method, path, body=data, headers=head)
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def post(port, studio, path, body, **headers):
    head = {"Content-Type": "application/json", "X-Studio": studio.token, **headers}
    status, _, data = ask(port, "POST", path, body, head)
    return status, json.loads(data)


def shown(view) -> list[str]:
    """Every piece of text the page shows a person."""
    out = [view["when"], view["from"], view["by"]]
    for card in view["cards"]:
        out += [card["title"], card["value"], card.get("detail") or "", card.get("today") or ""]
        out += [r["text"] for r in card["reasons"]] + [p["why"] for p in card["problems"]] + card.get("lines", [])
    for w in view["words"]:
        out += [w["label"], w.get("how", "")] + w.get("tags", []) + (w["lines"] if not w["sung"] else [])
    return out + [p["why"] for p in view["problems"]]


def test_the_server_answers_only_its_own_page(served):
    studio, port = served
    status, _, page = ask(port, "GET", "/")
    assert status == 200 and studio.token.encode() in page and b"{{token}}" not in page
    assert ask(port, "GET", "/studio.js")[0] == 200 and ask(port, "GET", "/studio.css")[0] == 200
    assert ask(port, "GET", "/", headers={"Host": "evil.example:80"})[0] == 403  # a renamed address
    assert ask(port, "GET", "/api/start", headers={"Host": f"songbird.local:{port}"})[0] == 403
    body = {"edits": {}}
    assert post(port, studio, "/api/song", body)[0] == 200
    assert post(port, studio, "/api/song", body, **{"X-Studio": "guess"})[0] == 403  # not its page's token
    assert post(port, studio, "/api/song", body, Origin="https://evil.example")[0] == 403
    assert ask(port, "POST", "/api/song", body, {"Content-Type": "text/plain", "X-Studio": studio.token})[0] == 415
    assert ask(port, "GET", "/audio/../../etc/passwd")[0] == 404
    assert ask(port, "GET", "/renders/x.flac")[0] == 404
    assert post(port, studio, "/api/listen", {"edits": {}, "who": "../../x"})[0] == 400


def test_the_page_gets_the_song_its_choices_and_their_bounds(served):
    studio, port = served
    status, _, data = ask(port, "GET", "/api/start")
    start = json.loads(data)
    assert status == 200 and start["title"] == "Now It's by You"
    assert start["bounds"]["mode"]["options"] == ["ionian", "mixolydian", "aeolian"]
    status, view = post(port, studio, "/api/song", {"edits": {"tempo": 88, "band.drum": 0, "nonsense": 1}})
    assert status == 200
    assert {c["id"] for c in view["cards"]} >= {"key", "tempo", "shape", "band", "mix", "singer", "words", "choir",
                                                "machine"}
    tempo = next(c for c in view["cards"] if c["id"] == "tempo")
    assert tempo["mine"] and tempo["value"].startswith("88") and tempo["reasons"][0]["kind"] == "you"
    assert any(p["path"] == "nonsense" for p in view["problems"])
    assert len(view["words"]) == len(view["form"]) and view["listen"]["whole"]
    status, options = post(port, studio, "/api/options", {"edits": {}, "block": "verse", "index": 1})
    assert status == 200 and any(c["allowed"] for c in options["choices"]) and options["path"] == "words.verse.1"
    status, compare = post(port, studio, "/api/compare", {"edits": {}, "names": ["Basil", "<script>"]})
    assert [m["name"] for m in compare["machines"]] == ["Yours", "Basil", "Script"]
    status, kept = post(port, studio, "/api/keep-words", {"edits": {"tempo": 90}})
    assert kept["edits"]["tempo"] == 90 and "words.verse.0" in kept["edits"]


def test_the_page_never_says_the_codes_words(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    for who in ("ada", "basil", "coral", "dmitri"):
        voice = H.fictional(who)
        for day in ("2026-09-26", "2027-03-01", "2025-06-15"):
            v = studio.context.version({"date": day, "mode": "aeolian", "band.whistle": 0}, voice=voice)
            for text in shown(explain.view(studio.context, v)):
                assert not FORBIDDEN.search(text), text


def test_today_is_the_command_lines_today(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    voice = H.fictional("ada")
    day = studio.day
    cli = choose_params(load(LEAD), None, voice, D.drift(D.parse(day), voice.hash))
    assert studio.version({}).params == cli


def test_a_packet_opens_as_the_parent(home):
    genome = load(LEAD)
    rng = np.random.default_rng(1)
    pcm = np.clip(rng.normal(0, 2000, (22050, 2)), -32768, 32767).astype("<i2")
    flac = home / "seed.flac"
    master.write_flac(flac, pcm, 44100)
    parent = choose_params(genome, None, H.fictional("basil"), D.drift(D.parse("2026-08-01"), H.fictional("basil").hash))
    record = {"id": master.pcm_sha256(pcm), "title": genome.title, "rendered_at": "2026-08-01T12:00:00+00:00",
              "params": parent.to_dict(), "program_version": "test", **pack.lineage(None),
              "chosen_by_you": {"tempo": {"value": parent.tempo, "was": 96.0}}}
    pack.pack(flac, record, LEAD)
    studio = S.Studio(str(flac), None, "fictional:ada", out=home / "out")
    assert studio.where == "packet" and studio.genome.title == genome.title
    assert studio.context.parent == parent
    assert studio.context.from_words() == "from the first version, made Saturday 1 August 2026"
    v = studio.version({})
    tempo = next(c for c in explain.view(studio.context, v)["cards"] if c["id"] == "tempo")
    if v.params.tempo == parent.tempo:
        assert any("where a person chose it" in r["text"] for r in tempo["reasons"])


def test_the_studio_runs_from_an_unpacked_packet_alone(home):
    """As the file's bootstrap runs it: the packet's own program (PYTHONPATH), in a folder with no checkout
    around it, opening the rendition the packet came from; the checkout's extras aren't there."""
    import os
    import socket

    genome = load(LEAD)
    rng = np.random.default_rng(2)
    pcm = np.clip(rng.normal(0, 2000, (22050, 2)), -32768, 32767).astype("<i2")
    flac = home / "song.flac"
    master.write_flac(flac, pcm, 44100)
    record = {"id": master.pcm_sha256(pcm), "title": genome.title, "rendered_at": "2026-09-01T12:00:00+00:00",
              "params": genome.seed_params, "program_version": "test", **pack.lineage(None)}
    pack.pack(flac, record, LEAD)
    unpacked = pack.unpack(flac, home / "unpacked")
    elsewhere = home / "elsewhere"
    elsewhere.mkdir()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PYTHONPATH": str(unpacked / "program"), "SONGBIRD_PACKET": str(flac)}
    server = subprocess.Popen([sys.executable, "-m", "songbird", "studio", "--packet", str(flac), "--machine",
                               "fictional:ada", "--no-open", "--port", str(port)], cwd=elsewhere, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        opened = server.stdout.readline()
        assert "from the first version, made Tuesday 1 September 2026" in opened, opened
        status, _, page = ask(port, "GET", "/")
        token = re.search(rb'name="studio-token" content="([^"]+)"', page).group(1).decode()
        start = json.loads(ask(port, "GET", "/api/start")[2])
        assert start["title"] == genome.title and not start["sing"]["available"] and start["phrasings"] == []
        assert start["out"] == "."  # recordings go where it was run from
        status, _, data = ask(port, "POST", "/api/song", {"edits": {"tempo": 90}},
                              {"Content-Type": "application/json", "X-Studio": token})
        assert status == 200 and json.loads(data)["cards"][1]["value"].startswith("90")
    finally:
        server.terminate()
        server.wait(timeout=20)


def test_a_replay_keeps_the_lineage_and_its_choir():
    """render --replay rebuilds a rendition's parent from its record: its place in the lineage and the earlier
    singers of its choir, so a child of a child sings again with the same voices."""
    from songbird import cli
    from songbird.synth.voice import VoiceParams

    grand = {"id": "a" * 64, "singer": {"shift": -12, "rd": 0.9}}
    parent = {"id": "b" * 64, "generation": 1, "ancestry": ["a" * 64], "singer": {"tract": 1.15, "rd": 0.7},
              "lineage_singers": [grand]}
    singer = VoiceParams()
    sang, voices = cli.choir_of(parent, singer)
    child = {"id": "c" * 64, **pack.lineage(parent), "lineage_singers": sang}
    rebuilt = cli.parent_of(child)
    assert cli.choir_of(rebuilt, singer) == (sang, voices)
    assert pack.lineage(rebuilt) == pack.lineage(parent)
    assert cli.parent_of({"id": "d" * 64, "generation": 0, "parent_id": None}) is None


def test_held_words_are_kept_not_changed_and_today_keeps_the_persons_choices(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    kept = studio.keep_words({})["edits"]
    view = explain.view(studio.context, studio.version(kept))
    assert view["changed"] == [] and len(view["held"]) == len(kept)
    assert all(w["how"] == "kept by you" for w in view["words"] if w["sung"])
    view = explain.view(studio.context, studio.version({"tempo": 88, "date": "2027-09-26"}))
    tempo = next(c for c in view["cards"] if c["id"] == "tempo")
    assert tempo["value"].startswith("88") and "today" not in tempo  # today it is 88 too: the person chose it
    problems = studio.version({"form.verses": 10**9}).problems
    assert problems[0]["path"] == "form.verses" and "2 to 4 verses" in problems[0]["why"]


def test_a_preview_never_begins_a_sung_syllable_halfway(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    v = studio.version({})
    score = studio._score(v)
    for index in range(len(v.params.form)):
        t0, t1 = S.window(studio.genome, v.params, score, v.params.form, index)
        part, lead_in = S.cut(score, t0, t1)
        sung = [n for n in part.notes if n.part == "voice" or n.part.startswith("choir")]
        assert all(n.start >= lead_in - 1e-9 for n in sung), (v.params.form[index], min(n.start for n in sung))


def test_a_refusal_keeps_the_connection_in_step(served):
    studio, port = served
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    head = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/json"}
    for extra, body, code in (({"X-Studio": "wrong"}, b'{"edits": {}}', 403),
                              ({"X-Studio": "café".encode().decode("latin-1")}, b'{"edits": {}}', 403),
                              ({"X-Studio": studio.token}, b"[1, 2]", 400),
                              ({"X-Studio": studio.token}, b'{"edits": {}}', 200)):
        c.request("POST", "/api/song", body=body, headers={**head, **extra})
        r = c.getresponse()
        r.read()
        assert r.status == code
    c.request("GET", "/api/start", headers={"Host": f"127.0.0.1:{port}"})
    assert c.getresponse().status == 200
    c.close()


def wait(studio, job):
    for _ in range(600):
        state = studio.jobs.get(job["id"]).view()
        if state["state"] in ("done", "failed"):
            return state
        time.sleep(0.5)
    raise TimeoutError


def test_a_section_is_made_on_demand_and_served_with_byte_ranges(served):
    studio, port = served
    status, job = post(port, studio, "/api/listen", {"edits": {}, "who": "you", "section": 3})
    assert status == 200 and job["kind"] == "preview"
    done = wait(studio, job) if job["state"] != "done" else job
    assert done["state"] == "done", done
    status, head, data = ask(port, "GET", done["url"], headers={"Range": "bytes=0-99"})
    assert status == 206 and len(data) == 100 and head["Content-Range"].endswith(f"/{(studio.cache / done['url'].split('/')[-1]).stat().st_size}")
    status, _, whole = ask(port, "GET", done["url"])
    assert status == 200 and whole[:4] == b"fLaC"
    # asked again, it's there at once
    status, again = post(port, studio, "/api/listen", {"edits": {}, "who": "you", "section": 3})
    assert again["state"] == "done" and again["url"] == done["url"]


def test_a_recording_is_a_packet_marked_with_a_persons_choices_and_replays(home):
    studio = S.Studio(None, str(B), "fictional:ada", out=home / "out")
    edits = {"tempo": 70, "band.pattern": "pick", "mix.space": 1.2, "form.verses": 2, "form.intro": False,
             "form.outro": False, "form.break": False, "roll": 1}
    job = studio.record(edits)
    done = job if job["state"] == "done" else wait(studio, job)
    assert done["state"] == "done", done
    recorded = done["result"]["recorded"]
    flac = home / "out" / Path(recorded["flac"]).name
    manifest = pack.read_manifest(flac)
    marks = manifest["chosen_by_you"]
    assert marks["tempo"] == {"value": 70.0, "was": studio.version({}).params.tempo}
    assert marks["roll"]["value"] == 1 and "form.verses" in marks
    assert manifest["generation"] == 0 and manifest["params"]["tempo"] == 70.0
    assert flac.name.startswith("coal-from-the-fire") and not (flac.with_suffix(".json")).exists()
    # the recording renders again, byte for byte, from its own record
    out = home / "again.flac"
    subprocess.run([sys.executable, "-m", "songbird", "render", str(B), "--replay", str(flac), "--out", str(out)],
                   check=True, cwd=ROOT, capture_output=True)
    assert json.loads(out.with_suffix(".json").read_text())["id"] == manifest["id"]
