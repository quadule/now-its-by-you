"""The studio: a page on this computer only that shows your version of the song, lets you change it and
records it. Its server answers only its own page; its words never use the code's names; its today is the
command line's; a packet opens as the parent; previews are made and served; a recording is a packet whose
marks say what a person chose (never who) and which renders again byte for byte."""

import dataclasses
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
    status, view = post(port, studio, "/api/song", {"edits": {"form.intro": False, "form.verses": 4}})
    shape = next(c for c in view["cards"] if c["id"] == "shape")
    said = [r["text"] for r in shape["reasons"] if r["kind"] == "you"]
    assert "without an intro: chosen by you" in said and "four verses: chosen by you" in said


def test_the_page_never_says_the_codes_words(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    styles = ("", "stringband", "synthfolk", "gospel")
    for k, who in enumerate(("ada", "basil", "coral", "dmitri")):
        voice = H.fictional(who)
        for day in ("2026-09-26", "2027-03-01", "2025-06-15"):
            edits = {"date": day, "mode": "aeolian", "band.whistle": 0}
            if styles[k]:
                edits = {"date": day, "style.name": styles[k], "style.lift": True}
            v = studio.context.version(edits, voice=voice)
            for text in shown(explain.view(studio.context, v)):
                assert not FORBIDDEN.search(text), text
                assert "lineup" not in text and "None" not in text, text


def test_a_chosen_style_brings_its_own_band_and_pace(home):
    from songbird import style as style_mod

    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    plain = studio.version({})
    v = studio.version({"style.name": "stringband", "style.feel": "straight", "band.banjo": 0})
    assert v.params.style.name == "stringband" and "style.name" in v.applied
    assert set(v.params.band.lineup) == set(style_mod.STYLES["stringband"].lineup)  # the style's band, not the old one
    assert v.params.band.lineup["banjo"] == 0 and "band.banjo" in v.applied
    assert v.params.tempo != plain.params.tempo  # a string band takes the song at its own pace
    view = explain.view(studio.context, v)
    style = next(c for c in view["cards"] if c["id"] == "style")
    assert style["value"].startswith("a string band") and style["mine"]
    assert any("chosen by you" in r["text"] for r in style["reasons"])
    band = next(c for c in view["cards"] if c["id"] == "band")
    assert "banjo" in band["players"] and "the banjo sitting out" in band["value"]
    assert v.marks["style.name"]["value"] == "stringband"
    # a feel the style can't play is said, not bent
    refused = studio.version({"style.name": "stringband", "style.feel": "twelve"})
    assert any(p["path"] == "style.feel" for p in refused.problems)


def test_a_word_chosen_keeps_the_words_handed_down(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    plain = studio.version({})
    held = plain.params.words
    options = studio.options({}, "verse", 1)["choices"]
    pick = next(c["id"] for c in options if c["allowed"] and c["id"] != held["verses"][1]["id"])
    v = studio.version({"words.verse.1": {"id": pick}})
    now = v.params.words
    assert now["verses"][1]["id"] == pick and "words.verse.1" in v.applied
    assert [x for i, x in enumerate(now["verses"]) if i != 1] == [x for i, x in enumerate(held["verses"]) if i != 1]
    assert now["refrain"] == held["refrain"] and now.get("bridge") == held.get("bridge") and now.get("tag") == held.get("tag")
    # what is sung is what the lineage holds, as a recording will hand it down
    from songbird import arrange

    assert arrange.hold(studio.genome, v.lyrics) == now
    words = {w["index"]: w for w in explain.view(studio.context, v)["words"]}
    verse2 = next(w for w in words.values() if w.get("block") == "verse" and w["nth"] == 1)
    assert verse2["how"] == "chosen by you"
    assert all(w["how"] in ("handed down", "new this time") for w in words.values() if w["sung"] and not w["mine"])


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
        tempo = next(c for c in json.loads(data)["cards"] if c["id"] == "tempo")
        assert status == 200 and tempo["value"].startswith("90")
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
    assert recorded["download"] == f"/audio/{Path(done['url']).stem}.flac?name={flac.name}"


# ---------------------------------------------------------------- shared for a preview (--host, --allow-host)


@pytest.fixture
def shared(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out", key="the-preview-key")
    server = S.serve(studio, 18790, names=["songbird.example.test", ".trycloudflare.com"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1]
    server.shutdown()
    server.server_close()


def test_a_shared_studio_admits_only_its_links_key(shared):
    studio, port = shared
    cookie = {"Cookie": f"songbird-studio-{port}=the-preview-key"}
    status, _, page = ask(port, "GET", "/")
    assert status == 403 and b"shared by link" in page and studio.token.encode() not in page
    assert ask(port, "GET", "/?key=wrong-key-here")[0] == 403
    status, head, page = ask(port, "GET", "/?key=the-preview-key")
    assert status == 200 and studio.token.encode() in page
    assert "the-preview-key" in head["Set-Cookie"] and "HttpOnly" in head["Set-Cookie"]
    assert ask(port, "GET", "/api/start")[0] == 403  # the key, or nothing
    start = json.loads(ask(port, "GET", "/api/start", headers=cookie)[2])
    assert start["shared"] and not start["sing"]["available"]
    assert all(p["id"] == "everyone" for p in start["phrasings"])  # never one singer's way, or name
    assert dataclasses.replace(studio.context, machine="here").machine_label() == "the computer serving this studio"
    # its names: a tunnel's (no port, https), a name under one given with a leading dot; not others
    for host, code in (("songbird.example.test", 200), (f"songbird.example.test:{port}", 200),
                       ("abc.trycloudflare.com", 200), ("trycloudflare.com", 403), ("evil.example", 403)):
        assert ask(port, "GET", "/api/start", headers={"Host": host, **cookie})[0] == code, host
    body, token = {"edits": {}}, {"X-Studio": studio.token}
    tunnel = {"Host": "abc.trycloudflare.com", "Origin": "https://abc.trycloudflare.com"}
    assert post(port, studio, "/api/song", body, **tunnel, **cookie)[0] == 200
    assert post(port, studio, "/api/song", body, **{**tunnel, "Origin": "https://evil.example"}, **cookie)[0] == 403
    assert post(port, studio, "/api/song", body, **token)[0] == 403  # the page's token alone isn't the key
    assert post(port, studio, "/api/sing", {}, **cookie)[1]["error"]


def test_the_page_draws_the_line_a_version_came_down():
    assert explain.generation_of(None) == 0  # from the song as it began
    assert explain.generation_of({"generation": 0}) == 1 and explain.generation_of({"generation": 4}) == 5
    assert explain.generation_of({"generation": "x"}) == 1  # a record that says nothing sensible: its child


def test_this_computers_own_studio_needs_no_key(served):
    studio, port = served
    start = json.loads(ask(port, "GET", "/api/start")[2])
    assert not start["shared"] and studio.share_key is None
    assert dataclasses.replace(studio.context, machine="here").machine_label() == "this machine"


def test_the_names_a_shared_studio_answers_to():
    assert S.share_names("127.0.0.1", []) == [] and S.share_names("localhost", None) == []
    assert S.share_names("192.168.5.5", []) == ["192.168.5.5"]
    assert S.share_names("127.0.0.1", ["Songbird.Example.test"]) == ["songbird.example.test"]
    every = S.share_names("0.0.0.0", [])
    assert every and not any(n.startswith("127.") for n in every)
    shares, here = S.links("127.0.0.1", 8790, [".trycloudflare.com"], [".trycloudflare.com"], "k" * 12)
    assert shares == ["https://NAME-THE-TUNNEL-PRINTED.trycloudflare.com/?key=kkkkkkkkkkkk"]
    assert here == "http://127.0.0.1:8790/?key=kkkkkkkkkkkk"
    shares, here = S.links("192.168.5.5", 8790, [], ["192.168.5.5"], "k" * 12)
    assert shares == [here] == ["http://192.168.5.5:8790/?key=kkkkkkkkkkkk"]
    assert S.allowed_host("[::1]:8790", 8790, ()) and not S.allowed_host("127.0.0.1:8791", 8790, ())


def test_the_command_line_shares_only_when_asked_and_checks_what_its_given():
    import argparse

    parser = argparse.ArgumentParser()
    S.add_arguments(parser)
    args = parser.parse_args([])
    assert args.host == "127.0.0.1" and args.allow_host == [] and args.key is None
    args = parser.parse_args(["--host", "0.0.0.0", "--allow-host", "a.test", "--allow-host", ".b.test",
                              "--key", "abcdefgh", "--no-open", "--port", "8790"])
    assert args.host == "0.0.0.0" and args.allow_host == ["a.test", ".b.test"] and args.key == "abcdefgh"
    with pytest.raises(SystemExit, match="--allow-host"):
        S.run(parser.parse_args(["--allow-host", "evil.test/x"]))
    with pytest.raises(SystemExit, match="--key"):
        S.run(parser.parse_args(["--host", "0.0.0.0", "--key", "short"]))


def test_a_recording_downloads_under_its_own_name(served):
    studio, port = served
    (studio.cache / "0123456789abcdef.flac").write_bytes(b"fLaC" + bytes(64))
    status, head, data = ask(port, "GET", "/audio/0123456789abcdef.flac?name=now-its-by-you.2026-09-27.abcdef.flac")
    assert status == 200 and data[:4] == b"fLaC"
    assert head["Content-Disposition"] == 'attachment; filename="now-its-by-you.2026-09-27.abcdef.flac"'
    status, head, _ = ask(port, "GET", '/audio/0123456789abcdef.flac?name=../x".flac')
    assert status == 200 and "Content-Disposition" not in head


def test_the_render_queue_says_whats_ahead_and_refuses_a_flood():
    gate = threading.Event()
    jobs = S.Jobs()
    first = jobs.submit("a", "preview", "a", lambda job: gate.wait(30))
    for _ in range(100):
        if first.state == "running":
            break
        time.sleep(0.02)
    try:
        waiting = [jobs.submit(f"k{i}", "preview", "x", lambda job: None) for i in range(S.MAX_WAITING)]
        assert jobs.view(waiting[-1])["ahead"] == 1  # the newest preview goes next, after the one running
        assert jobs.view(waiting[0])["ahead"] == S.MAX_WAITING
        with pytest.raises(S.Busy):
            jobs.submit("one-too-many", "record", "r", lambda job: None)
        assert jobs.submit("k0", "preview", "x", lambda job: None) is waiting[0]  # asked again: the same one
    finally:
        gate.set()


def test_identity_is_one_file_in_two_places():
    """The studio and the singing pages are served apart, so each has a copy of identity.css (docs/IDENTITY.md):
    the same bytes, loaded before each page's own stylesheet."""
    studio, pages = ROOT / "songbird" / "studio" / "identity.css", ROOT / "web" / "sing" / "page" / "identity.css"
    assert studio.read_bytes() == pages.read_bytes()
    assert "/identity.css" in S.STATIC
    html = (ROOT / "songbird" / "studio" / "index.html").read_text()
    assert html.index('href="/identity.css"') < html.index('href="/studio.css"')


def test_a_musician_takes_the_version_away_as_midi_and_stems(served, monkeypatch):
    """Download MIDI: at once, of the score the render sings (a person's key and tempo in it), under the song's
    name. Download the parts: a job whose zip holds each part as it renders alone, padded to the MIDI file's
    bar 1, with the MIDI file and a note on them."""
    import io
    import zipfile

    import soundfile as sf

    from songbird import midi

    studio, port = served
    edits = {"tempo": 90, "tonic": 64}
    status, made = post(port, studio, "/api/export", {"edits": edits, "what": "midi"})
    assert status == 200 and made["state"] == "done" and made["url"].startswith("/export/")
    status, head, data = ask(port, "GET", made["url"])
    assert status == 200 and head["Content-Type"] == "audio/midi" and data[:4] == b"MThd"
    assert re.fullmatch(r'attachment; filename="now-its-by-you\.\d{4}-\d\d-\d\d\.[0-9a-f]{6}\.mid"',
                        head["Content-Disposition"])
    v = studio.version(edits)
    voice = studio._score(v).part("voice")
    track = midi.read(data)["tracks"][1]
    assert [e["args"][0] for _, e in track if e.get("status") == 0x90] == [round(n.pitch) for n in voice]
    assert v.params.tonic == 64 and v.params.tempo == 90
    assert post(port, studio, "/api/export", {"edits": edits, "what": "nonsense"})[0] == 400
    assert ask(port, "GET", "/export/0123456789abcdef.zip")[0] == 404

    def fake_stems(score, seed=0, voice=None, ancestors=None, progress=None):  # the parts' own sound is tested elsewhere
        n = int(score.duration * 1000)
        return {"voice": np.full((n, 2), 0.5), "guitar": np.full((n, 2), 2.0)}

    monkeypatch.setattr(S.synth, "SR", 1000)
    monkeypatch.setattr(S.synth, "render_stems", fake_stems)
    status, job = post(port, studio, "/api/export", {"edits": edits, "what": "stems"})
    assert status == 200 and job["download"].startswith("/export/")
    for _ in range(300):
        job = json.loads(ask(port, "GET", f"/api/job/{job['id']}")[2])
        if job["state"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    status, head, data = ask(port, "GET", job["url"])
    assert status == 200 and head["Content-Type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(data))
    names = sorted(z.namelist())
    stem = names[0].split("/")[0]
    assert [n.split("/")[1] for n in names] == ["01-voice.flac", "02-guitar.flac", "README.txt", f"{stem}.mid"]
    _, lead_in = midi.from_score(studio.genome, v.params, studio._score(v))
    audio, sr = sf.read(io.BytesIO(z.read(f"{stem}/02-guitar.flac")))
    pad = int(round(-lead_in * sr))
    assert sr == 1000 and not audio[:pad].any() and abs(audio[pad, 0] - 0.989) < 1e-3  # all turned down together
    voice_audio, _ = sf.read(io.BytesIO(z.read(f"{stem}/01-voice.flac")))
    assert abs(voice_audio[pad, 0] - 0.989 / 4) < 1e-3
    note = z.read(f"{stem}/README.txt").decode()
    assert "bar 1" in note and "dry" in note and "public domain" in note and not FORBIDDEN.search(note)


def test_a_renders_progress_follows_the_parts_in_whatever_order_it_takes_them():
    """The voice first on one or two threads, some of the band beside it on more: the bar only moves forward, by
    the parts already begun, and names what's being made now."""
    job = S.Job("j", "k", "preview", "a section", work=lambda job: None)
    job.plan = [("lute", 1.0), ("fiddle", 1.0), ("voice", 4.0), ("mix", 1.0), ("master", 1.0)]
    seen = []
    for name in ("voice", "lute", "fiddle", "mix", "master"):
        job.report(name)
        seen.append(job.progress)
    assert seen == sorted(seen) and seen[0] == 0.0
    assert seen[1] == 0.5 and abs(seen[-1] - 7 / 8) < 1e-9  # the voice's four of eight, then everything before the master
    job.report("lute")  # a part reported again moves nothing back
    assert job.progress == seen[-1] and job.stage == S.stage_words("lute")
def test_a_musician_brings_notes_back_as_a_preview_and_nothing_changes_until_applied(served):
    """Notes in: the MIDI file downloaded, brought back unchanged, is no change; changed (the bass played harder
    in a few notes), a preview of part edits, in the page's words; applied, the page shows the player's notes as
    the person's. A file that isn't one, or that didn't arrive whole, says why. A take is previewed the same way."""
    import base64

    from _midi_edit import rewrite

    from songbird import notesin

    studio, port = served
    edits = {"tempo": 90}
    status, made = post(port, studio, "/api/export", {"edits": edits, "what": "midi"})
    data = ask(port, "GET", made["url"])[2]
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    status, same = post(port, studio, "/api/notes-in", {"edits": edits, "file": b64(data)})
    assert status == 200 and same["changes"] == [] and same["refused"] == [] and "Bass" in same["tracks"]
    harder = rewrite(data, lambda name, notes: [n[:4] + [min(127, n[4] + 20)] if name == "Bass" and k < 3 else n
                                                for k, n in enumerate(notes)])
    status, preview = post(port, studio, "/api/notes-in", {"edits": edits, "file": b64(harder)})
    assert status == 200 and preview["changes"] and not preview["refused"]
    assert all(c["path"].startswith("part.bass.") and c["what"].startswith("the bass: ") for c in preview["changes"])
    assert not any(FORBIDDEN.search(c["where"] + c["what"]) for c in preview["changes"])
    assert studio.version(edits).params.composition == {}  # a preview changes nothing
    mine = {**edits, **{c["path"]: c["value"] for c in preview["changes"]}}
    status, song = post(port, studio, "/api/song", {"edits": mine})
    assert status == 200 and not song["problems"]
    assert set(song["composition"]["performed"]["bass"]) == {c["path"][len("part.bass."):] for c in preview["changes"]}
    assert set(song["applied"]) >= {c["path"] for c in preview["changes"]}
    for body, why in (({"file": "not base64 at all!"}, "arrive whole"), ({"file": b64(b"hello")}, "Standard MIDI"),
                      ({"file": "A" * 400_000}, "bigger"), ({}, "a file or a take")):
        status, said = post(port, studio, "/api/notes-in", {"edits": edits, **body})
        assert status == 400 and why in said["error"], said
    v = studio.version(edits)
    first = next(ln for ln in notesin.layout(studio.genome, v.params) if ln["sung"])
    beat = studio.genome.meter.beat
    take = {"player": "fiddle", "notes": [[first["u0"] / beat, 1, v.params.tonic + 7, 90]], "lines": [first["key"]]}
    status, took = post(port, studio, "/api/notes-in", {"edits": edits, "take": take})
    assert status == 200 and [c["path"] for c in took["changes"]] == [f"part.fiddle.{first['key']}"]
    assert took["changes"][0]["value"] == [[0, 96, 7, 90]]


def test_the_arrangement_is_drawn_as_a_grid_for_a_timeline(served):
    studio, port = served
    edits = {"style.name": "synthfolk", "tempo": 130, "arrange.refrain:0.drummachine.pattern": "half",
             "arrange.refrain:1.sung": False, "arrange.refrain:1.bars": 16, "arrange.verse:0.synthbass.level": "out",
             "arrange.verse:9.guitar.level": "hard"}
    status, grid = post(port, studio, "/api/arrangement", {"edits": edits})
    assert status == 200, grid
    v = studio.version(edits)
    from songbird import composition
    assert [s["id"] for s in grid["sections"]] == composition.section_ids(v.params.form)
    players = [p["name"] for p in grid["players"]]
    assert "drummachine" in players and len(grid["cells"]) == len(grid["sections"]) * len(players)
    cell = {(c["section"], c["player"]): c for c in grid["cells"]}
    mine = cell[("refrain:0", "drummachine")]
    assert mine["by"] == "you" and mine["value"]["pattern"] == "half" and mine["program"]["pattern"] != "half"
    assert mine["why"][0]["kind"] == "you" and mine["paths"]["pattern"] == "arrange.refrain:0.drummachine.pattern"
    assert not mine["locked"]
    assert cell[("verse:0", "synthbass")]["value"]["level"] == "out"
    drop = next(s for s in grid["sections"] if s["id"] == "refrain:1")
    assert not drop["sung"] and drop["bars"] == 16 and drop["by"]["sung"] == "you" and 16 in drop["bar_options"]
    assert [ln["sung"] for ln in drop["lines"]] == [False] * 8
    assert cell[("refrain:1", "synthlead")]["value"]["pattern"] == "lead"  # the lead plays the tune where nobody sings
    program = [c for c in grid["cells"] if c["by"] == "program" and c["plays"]]
    assert program and all(c["why"] for c in program)
    # locking what the program chose keeps it, and the grid and the record say so
    first = next(c for c in program if c["program"]["pattern"])
    lock = {first["paths"][f]: first["program"][f] for f in ("level", "pattern", "from")}
    status, locked = post(port, studio, "/api/arrangement", {"edits": {**edits, **lock}})
    again = next(c for c in locked["cells"] if (c["section"], c["player"]) == (first["section"], first["player"]))
    assert again["by"] == "you" and again["locked"] and again["value"]["pattern"] == first["value"]["pattern"]
    marks = studio.version({**edits, **lock}).marks
    assert all(marks[p].get("locked") for p in lock)
    assert grid["tempo"]["value"] == 130 and grid["tempo"]["max"] > 130
    assert any(p["path"] == "arrange.verse:9.guitar.level" for p in grid["problems"])
    texts = [r["text"] for c in grid["cells"] for r in c["why"]] + [c["value"]["pattern_label"] for c in grid["cells"]]
    texts += [o["text"] for s in grid["sections"] for o in s["options"]] + [p["why"] for p in grid["problems"]]
    texts += [x["label"] for p in grid["players"] for x in p["patterns"]] + [x["label"] for x in grid["levels"]]
    assert texts and not [t for t in texts if FORBIDDEN.search(t)]
