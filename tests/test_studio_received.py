"""Someone's version, opened in the studio (songbird.received; docs/WEB-STUDIO.md, "Opening someone's version"):
a real rendition opens as the parent and its child's record names it; one made by another program opens with
this one, saying so; hostile files are refused with a reason (too large, truncated, not a FLAC, a zip bomb,
names that climb out, a record of the wrong types or sizes, a record that isn't its audio, a song that isn't
this studio's); nothing a packet carries is ever run, imported or written; the page's guards come before a byte
of the file is read; the versions kept are known only by their links, and let go."""

import copy
import http.client
import io
import json
import os
import socket
import stat
import sys
import threading
import time
import warnings
import weakref
import zipfile
from pathlib import Path

import numpy as np
import pytest

from songbird import drift as D, harvest as H, pack, public as P, received as R, studio as S, variation
from songbird.genome import load
from songbird.realize import choose_params
from songbird.synth import master

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
B = ROOT / "songs" / "b-coal-from-the-fire.json"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("STUDIO_MEMORY", "16g")  # a public studio with room for any whole song (its budget: public.render_mb)
    return tmp_path


def make_packet(folder: Path, song: Path = LEAD, name: str = "parent.flac", seconds: float = 0.5,
                generation: int = 2) -> Path:
    """A real rendition's packet, as `render --pack` makes one (a little noise for its audio): a version from a
    fictional machine, two generations down a line."""
    genome = load(song)
    rng = np.random.default_rng(7)
    pcm = np.clip(rng.normal(0, 2000, (int(44100 * seconds), 2)), -32768, 32767).astype("<i2")
    flac = folder / name
    master.write_flac(flac, pcm, 44100)
    params = choose_params(genome, None, H.fictional("basil"), D.drift(D.parse("2026-08-01"), H.fictional("basil").hash))
    record = {"id": master.pcm_sha256(pcm), "title": genome.title, "rendered_at": "2026-08-01T12:00:00+00:00",
              "params": params.to_dict(), "program_version": "test", "generation": generation,
              "parent_id": "b" * 64, "ancestry": ["a" * 64, "b" * 64],
              "singer": {"tract": 1.15, "rd": 0.8}, "lineage_singers": [{"id": "b" * 64, "singer": {"rd": 0.9}}],
              "voice": {"hash": "0e39d3ec053f13fe", "signals": {"machine": {"cores": 0.75}}},
              "chosen_by_you": {"tempo": {"value": params.tempo, "was": 96.0}}}
    pack.pack(flac, record, song)
    return flac


@pytest.fixture(scope="module")
def parent(tmp_path_factory):
    return make_packet(tmp_path_factory.mktemp("parent"))


def entries(src: Path) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(src) as z:
        return [(i.filename, z.read(i)) for i in z.infolist()]


def rebuild(src: Path, dst: Path, change: dict | None = None, extra=(), drop=(), audio: bytes | None = None) -> Path:
    """The packet again, as pack.py lays one out (the archive written onto the end of the audio), with members
    changed, added or left out."""
    buffer = io.BytesIO(pack.audio_bytes(src) if audio is None else audio)
    buffer.seek(0, io.SEEK_END)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a duplicate name, on purpose
        with zipfile.ZipFile(buffer, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for name, data in entries(src):
                if name not in drop:
                    z.writestr(name, (change or {}).get(name, data))
            for name, data in extra:
                z.writestr(name, data)
    dst.write_bytes(buffer.getvalue())
    return dst


def with_record(src: Path, dst: Path, fn) -> Path:
    record = pack.read_manifest(src)
    fn(record)
    return rebuild(src, dst, {"manifest.json": json.dumps(record).encode()})


def refused(path, match: str, title="Now It's by You"):
    with pytest.raises(R.Refused, match=match):
        R.examine(path, title, "none")


# ---------------------------------------------------------------- a real rendition, read as data


def test_a_rendition_is_read_as_data_its_record_cleaned_to_what_a_parent_gives(parent):
    out = R.examine(parent, "Now It's by You", "fictional:wren", "2026-09-29")
    record = out["record"]
    assert set(record) <= set(R.KEPT)
    assert "voice" not in record and "drift" not in record  # the maker's machine's numbers aren't needed
    manifest = pack.read_manifest(parent)
    assert record["id"] == manifest["id"] and record["generation"] == 2 and record["ancestry"] == ["a" * 64, "b" * 64]
    assert record["params"]["tempo"] == manifest["params"]["tempo"] and record["singer"] == {"tract": 1.15, "rd": 0.8}
    assert out["genome"].encode() == LEAD.read_bytes()
    assert out["timeline"]["day"] == "2026-09-29" and out["timeline"]["drawn"]["dates"]
    assert 0 < out["minutes"] < R.MINUTES


def test_the_reader_hashes_the_samples_as_the_packet_does(parent):
    audio = pack.audio_bytes(parent)
    assert R.samples_id(audio) == pack.samples_id(audio)
    with pytest.raises(R.Refused, match="longer than"):
        R.samples_id(audio, most_minutes=0.001)


# ---------------------------------------------------------------- hostile files


def test_what_isnt_a_rendition_is_refused_with_a_reason(parent, tmp_path, monkeypatch):
    (tmp_path / "text.flac").write_bytes(b"ID3\x04" + bytes(4000))
    refused(tmp_path / "text.flac", "isn't a FLAC")
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("manifest.json", "{}")
    (tmp_path / "zip.flac").write_bytes(zipped.getvalue())
    refused(tmp_path / "zip.flac", "isn't a FLAC")
    (tmp_path / "bare.flac").write_bytes(pack.audio_bytes(parent))
    refused(tmp_path / "bare.flac", "carries no packet")
    data = parent.read_bytes()
    (tmp_path / "cut.flac").write_bytes(data[: len(data) // 2])
    refused(tmp_path / "cut.flac", "carries no packet")
    (tmp_path / "tail-cut.flac").write_bytes(data[:-5])
    refused(tmp_path / "tail-cut.flac", "doesn't end|no packet")
    # the archive laid after the audio with offsets of its own (not as a rendition's are written)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        for name, member in entries(parent):
            z.writestr(name, member)
    (tmp_path / "moved.flac").write_bytes(pack.audio_bytes(parent) + zipped.getvalue())
    refused(tmp_path / "moved.flac", "isn't where")
    refused(rebuild(parent, tmp_path / "songless.flac", drop=("genome.json",)), "no song")
    monkeypatch.setattr(R, "UPLOAD", 1024)
    refused(parent, "the most taken")


def test_a_zip_bomb_is_refused_without_being_opened(parent, tmp_path):
    bomb = b"\0" * (200 * 2**20)  # 200 MB of nothing, about 200 KB compressed
    refused(rebuild(parent, tmp_path / "bomb.flac", extra=[("program/songbird/bomb.bin", bomb)]), "trap|unpack to|larger than")
    # the record itself, a small file claiming to be large
    big = b"{" + b" " * (8 * 2**20) + b"}"
    refused(rebuild(parent, tmp_path / "big.flac", {"manifest.json": big}), "manifest.json|trap")


def test_a_member_larger_than_it_says_is_refused(parent, tmp_path):
    path = rebuild(parent, tmp_path / "liar.flac")
    data = bytearray(path.read_bytes())
    with zipfile.ZipFile(path) as z:
        info = z.getinfo("manifest.json")
    # say it is 10 bytes, in its local header and in the directory (sizes at 22 and 24 of each)
    data[info.header_offset + 22:info.header_offset + 26] = (10).to_bytes(4, "little")
    end = data.rfind(b"PK\x05\x06")
    at = int.from_bytes(data[end + 16:end + 20], "little")  # the directory, entry by entry
    while data[at:at + 4] == b"PK\x01\x02":
        n, e, c = (int.from_bytes(data[at + k:at + k + 2], "little") for k in (28, 30, 32))
        if bytes(data[at + 46:at + 46 + n]) == b"manifest.json":
            data[at + 24:at + 28] = (10).to_bytes(4, "little")
            break
        at += 46 + n + e + c
    else:
        raise AssertionError("no manifest.json in the directory")
    path.write_bytes(bytes(data))
    refused(path, "damaged|can't be read")


def test_names_that_climb_out_are_refused_and_nothing_lands_anywhere(parent, tmp_path):
    for name in ("../../escaped.py", "/tmp/escaped.py", "program/../../escaped.py", "program\\..\\escaped.py",
                 "program/./x.py"):
        refused(rebuild(parent, tmp_path / "climb.flac", extra=[(name, b"print('out')")]), "named")
    assert not list(tmp_path.parent.rglob("escaped.py"))
    refused(rebuild(parent, tmp_path / "twice.flac", extra=[("manifest.json", b"{}")]), "twice")


def test_a_record_of_the_wrong_types_or_sizes_is_refused(parent, tmp_path):
    cases = [
        (lambda r: r["params"].__setitem__("tempo", "fast"), "tempo isn't a number"),
        (lambda r: r["params"].__setitem__("tempo", 9.0), "tempo"),
        (lambda r: r["params"].__setitem__("form", ["verse"] * 500), "form"),
        (lambda r: r["params"].__setitem__("form", ["verse", "coda-from-nowhere"]), "doesn't have"),
        (lambda r: r["singer"].__setitem__("rd", "nan"), "isn't a number"),
        (lambda r: r["singer"].__setitem__("release", 1e7), "release"),
        (lambda r: r["singer"].__setitem__("engine", "tube"), "engine"),
        (lambda r: r["singer"].__setitem__("timbre", "alto:nan"), "timbre"),
        (lambda r: r["lineage_singers"][0]["singer"].__setitem__("vibrato_depth", 1e9), "vibrato_depth"),
        (lambda r: r.__setitem__("ancestry", ["c" * 64] * 5000), "list too long|ancestry"),
        (lambda r: r.__setitem__("ancestry", ["../../etc"]), "ancestry"),
        (lambda r: r.__setitem__("chosen_by_you", {"x": list(range(5000))}), "too long"),
        (lambda r: r.__setitem__("chosen_by_you", {"x": "y" * 70000}), "string too long|larger"),
        (lambda r: r.__setitem__("generation", 2**60), "too large|generation"),
        (lambda r: r.__setitem__("program_sha256", None), "which program"),
        (lambda r: r.__setitem__("id", "1" * 64), "isn't the rendition its record describes"),
        (lambda r: r.__setitem__("title", "Another Song"), "another song"),
        (lambda r: r.__setitem__("performance", {"lead": {"fields": ["__class__"], "phrases": {}}, "choir": []}),
         "way of singing"),
        (lambda r: r["params"].__setitem__("mix", {"rt60": 400.0}), "rt60"),
        (lambda r: r["params"].__setitem__("variants", [{"phrase": "v1", "note": 0, "kind": "leap", "degree": 900}]),
         "degree"),
    ]
    for i, (fn, match) in enumerate(cases):
        refused(with_record(parent, tmp_path / f"r{i}.flac", fn), match)
    deep = json.dumps({"id": "a" * 64, "x": json.loads("[" * 40 + "]" * 40)}).encode()
    refused(rebuild(parent, tmp_path / "deep.flac", {"manifest.json": deep}), "too large or too deep")
    manifest = parent.read_bytes()  # the record with a key said twice, and with NaN
    record = pack.read_manifest(parent)
    twice = json.dumps(record)[:-1] + ', "generation": 3}'
    refused(rebuild(parent, tmp_path / "keys.flac", {"manifest.json": twice.encode()}), "twice in one place")
    nan = json.dumps(record).replace('"generation": 2', '"generation": NaN')
    refused(rebuild(parent, tmp_path / "nan.flac", {"manifest.json": nan.encode()}), "holds NaN")
    assert manifest == parent.read_bytes()


def test_a_song_that_isnt_this_studios_or_wouldnt_end_is_refused(parent, tmp_path):
    refused(parent, "this studio sings", title="Coal from the Fire")
    song = json.loads(LEAD.read_text())
    slow = copy.deepcopy(song)
    slow["seed_params"]["tempo"] = 1
    refused(rebuild(parent, tmp_path / "slow.flac", {"genome.json": json.dumps(slow).encode()}), "tempo")
    long = copy.deepcopy(song)
    long["form"] = long["form"] + ["verse"] * 40
    refused(rebuild(parent, tmp_path / "long.flac", {"genome.json": json.dumps(long).encode()}), "form")
    broken = copy.deepcopy(song)
    broken["phrases"][next(iter(broken["phrases"]))]["tune"] = "1 2 3"
    refused(rebuild(parent, tmp_path / "broken.flac", {"genome.json": json.dumps(broken).encode()}), "can sing")


def test_another_programs_version_opens_with_this_program_saying_so(parent, home):
    older = with_record(parent, home / "older.flac", lambda r: r.__setitem__("program_sha256", "9" * 64))
    studio = S.Studio(None, str(LEAD), "fictional:wren", out=home / "out", public=P.Limits())
    folder = studio.incoming / "t"
    folder.mkdir()
    (folder / "older.flac").write_bytes(older.read_bytes())
    answer = studio.receive(folder / "older.flac")
    view = answer["version"]
    assert view["other_program"] and view["program"] == "9" * 12
    assert "another version of the program (99999999…)" in view["program_note"]
    assert "sung by this one" in view["program_note"]
    assert view["generation"] == 2 and answer["url"] == f"/v/{answer['id']}"


# ---------------------------------------------------------------- nothing from the packet is run


CANARY = "import pathlib\npathlib.Path({marker!r}).write_text('ran')\n"


def test_nothing_a_packet_carries_is_run_imported_or_written(parent, home):
    marker = home / "RAN"
    canary = CANARY.format(marker=str(marker)).encode()
    trap = rebuild(parent, home / "trap.flac", {"__main__.py": canary, "program/songbird/__init__.py": canary,
                                                "program/songbird/received.py": canary},
                   extra=[("program/sitecustomize.py", canary), ("program/usercustomize.py", canary),
                          ("program/songbird/canary.py", canary)])
    path_before, modules_before = list(sys.path), set(sys.modules)
    R.examine(trap, "Now It's by You", "none")  # in this process
    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits())
    folder = studio.incoming / "t"
    folder.mkdir()
    (folder / "brought.flac").write_bytes(trap.read_bytes())
    studio.receive(folder / "brought.flac")  # in the reader's process, as the studio does
    assert not marker.exists()
    assert sys.path == path_before
    for name in set(sys.modules) - modules_before:
        assert str(home) not in str(getattr(sys.modules[name], "__file__", "") or "")
    # no file of the packet's program anywhere the studio writes, nor beside the file
    written = [p for p in home.rglob("*") if p.is_file()]
    assert not [p for p in written if p.name in ("canary.py", "sitecustomize.py", "usercustomize.py", "__init__.py",
                                                 "__main__.py", "received.py")]
    assert not [p for p in written if "program" in p.relative_to(home).parts]


# ---------------------------------------------------------------- the studio on someone's version


def test_a_real_rendition_opens_as_the_parent_and_its_child_names_it(home):
    """As `songbird studio parent.flac` does: the child is the next generation, its parent the version brought,
    its ancestry the parent's and the parent, sung and packed by this program."""
    flac = make_packet(home, B, "b-parent.flac")
    studio = S.Studio(None, str(B), "fictional:ada", out=home / "out")
    folder = studio.incoming / "t"
    folder.mkdir()
    (folder / "brought.flac").write_bytes(flac.read_bytes())
    answer = studio.receive(folder / "brought.flac")
    other = studio.opened(answer["id"])
    parent_record = pack.read_manifest(flac)
    assert other.context.parent is not None and other.context.from_words().startswith("from the third version")
    assert other.key(other.version({}), None) != studio.key(studio.version({}), None)
    edits = {"form.verses": 2, "form.intro": False, "form.outro": False, "form.break": False}
    job = other.record(edits)
    for _ in range(600):
        state = studio.jobs.get(job["id"]).view()
        if state["state"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert state["state"] == "done", state
    child = pack.read_manifest(home / "out" / Path(state["result"]["recorded"]["flac"]).name)
    assert child["parent_id"] == parent_record["id"] and child["generation"] == 3
    assert child["ancestry"] == ["a" * 64, "b" * 64, parent_record["id"]]
    assert child["lineage_singers"][0] == {"id": parent_record["id"], "singer": {"tract": 1.15, "rd": 0.8}}
    assert child["program_sha256"] == studio.program_digest
    with zipfile.ZipFile(home / "out" / Path(state["result"]["recorded"]["flac"]).name) as z:
        assert z.read("genome.json") == B.read_bytes()


@pytest.fixture
def public(home):
    studio = S.Studio(None, str(LEAD), "fictional:wren", out=home / "out", public=P.Limits(opens=2))
    server = S.serve(studio, 18850)
    log = io.StringIO()
    server.RequestHandlerClass.log = log
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1], log
    server.shutdown()
    server.server_close()


def send(port, data: bytes, token, headers=None, path="/api/open"):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    head = {"Host": f"127.0.0.1:{port}", "Content-Type": "application/octet-stream", **(headers or {})}
    if token is not None:
        head["X-Studio"] = token
    c.request("POST", path, body=data, headers=head)
    r = c.getresponse()
    out = r.status, json.loads(r.read() or b"{}")
    c.close()
    return out


def ask(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    head = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=head)
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def test_a_version_brought_to_the_page_opens_at_its_own_link(public, parent):
    studio, port, log = public
    status, answer = send(port, parent.read_bytes(), studio.token)
    assert status == 200, answer
    vid = answer["id"]
    assert answer["url"] == f"/v/{vid}" and len(vid) == 32
    assert not list(studio.incoming.iterdir())  # the file, gone
    status, _, page = ask(port, "GET", f"/v/{vid}")
    assert status == 200 and f'content="{studio.token}.{vid}"'.encode() in page and b"/score.js" in page
    token = f"{studio.token}.{vid}"
    status, _, start = ask(port, "GET", "/api/start", headers={"X-Studio": token})
    start = json.loads(start)
    assert start["version"]["id"] == vid and start["generation"] == 3 and start["open"]["upload_mb"] == 64
    assert start["from"].startswith("from the third version")
    status, _, plain = ask(port, "GET", "/api/start")
    assert "version" not in json.loads(plain) and json.loads(plain)["generation"] == 0
    status, _, view = ask(port, "POST", "/api/song", {"edits": {"tempo": 90}},
                          {"Content-Type": "application/json", "X-Studio": token})
    assert status == 200 and json.loads(view)["from"] == start["from"]
    status, _, timeline = ask(port, "GET", "/api/timeline", headers={"X-Studio": token})
    assert status == 200 and json.loads(timeline)["dates"]
    # the same file again: the same version
    assert send(port, parent.read_bytes(), studio.token)[1]["id"] == vid
    # the log never names a version
    assert vid not in log.getvalue() and "GET /v/… 200" in log.getvalue()


def test_the_pages_guards_come_before_a_byte_is_read(public, parent):
    studio, port, _ = public
    data = b"fLaC" + bytes(2000)  # small: a refusal reads and drops it, so the answer arrives
    assert send(port, data, None)[0] == 403  # not the page's token
    assert send(port, data, "not-the-token")[0] == 403
    assert send(port, data, studio.token, {"Host": "elsewhere.example"})[0] == 403
    assert send(port, data, studio.token, {"Origin": "https://elsewhere.example"})[0] == 403
    # the page asks first, and hears why a file would be turned away before sending it
    json_head = {"Content-Type": "application/json", "X-Studio": studio.token}
    status, _, body = ask(port, "POST", "/api/open/ready", {"size": 17 * 2**20}, json_head)
    assert status == 200 and json.loads(body) == {"ready": True}
    status, _, body = ask(port, "POST", "/api/open/ready", {"size": 90 * 2**20}, json_head)
    assert status == 413 and "the most taken here is 64 MB" in json.loads(body)["error"]
    # far too large: answered from its length alone, the body never sent
    with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
        s.sendall(f"POST /api/open HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nX-Studio: {studio.token}\r\n"
                  f"Content-Length: {200 * 2**20}\r\n\r\n".encode())
        answer = b""
        while chunk := s.recv(4096):  # headers and body may come apart: read until the studio closes
            answer += chunk
        answer = answer.decode()
    assert answer.startswith("HTTP/1.1 413") and "the most taken here is 64 MB" in answer
    # an hour's opens, counted before reading (two for this visitor: the second is refused as a file, the third
    # as one too many)
    status, why = send(port, b"not a flac at all", studio.token)
    assert status == 422 and "isn't a FLAC" in why["error"]
    assert send(port, b"nor this", studio.token)[0] == 422
    status, why = send(port, b"nor this", studio.token)
    assert status == 429 and "You've had 2 versions opened this hour" in why["error"]
    status, _, body = ask(port, "POST", "/api/open/ready", {"size": 17 * 2**20}, json_head)
    assert status == 429 and "versions opened" in json.loads(body)["error"]
    assert not list(studio.incoming.iterdir())


def test_a_file_brought_is_answered_within_a_proxys_patience(public, parent, monkeypatch):
    """Cloudflare gives up on an answer after 100 s: a file brought is never left waiting for a reader (both busy:
    "send it again in a minute", at once, and the page asking first hears so too), and its reader is given what is
    left of S.OPEN_SECONDS since it was asked."""
    studio, port, _ = public
    json_head = {"Content-Type": "application/json", "X-Studio": studio.token}
    for _ in range(2):  # both readers busy with others' files
        assert studio.reading.acquire(blocking=False)
    try:
        began = time.monotonic()
        status, why = send(port, b"fLaC" + bytes(2000), studio.token)
        assert status == 503 and "reading other versions" in why["error"] and time.monotonic() - began < 5
        status, _, body = ask(port, "POST", "/api/open/ready", {"size": 17 * 2**20}, json_head)
        assert status == 503 and "send it again in a minute" in json.loads(body)["error"]
    finally:
        studio.reading.release()
        studio.reading.release()
    given = []
    real = studio.receive
    monkeypatch.setattr(studio, "receive", lambda path, timeout=None: given.append(timeout) or real(path, timeout))
    assert send(port, parent.read_bytes(), studio.token)[0] == 200
    assert S.OPEN_SECONDS - 5 < given[0] <= S.OPEN_SECONDS < 100
    assert studio.reading.acquire(blocking=False) and studio.reading.acquire(blocking=False)  # both given back
    studio.reading.release()
    studio.reading.release()


def test_a_public_studio_opens_no_version_whose_next_would_be_too_long_to_make_there(parent, home):
    """received.MINUTES (12) is any studio's; a public one holds a version's next to what it can make in one go, with
    the lightest band (Studio.most_minutes), since a longer one couldn't be made there or in a browser."""
    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits(render_mb=2100))
    most = studio.most_minutes()
    assert 5 < most < R.MINUTES and S.Studio(None, str(LEAD), "none").most_minutes() is None
    record = R.examine(parent, "Now It's by You", "none")["record"]
    song = load(LEAD)
    assert R.exercise(record, song, "none", minutes=most)["minutes"] < most  # this one: opened
    with pytest.raises(R.Refused, match=r"Its next version would play for \d+\.\d minutes, longer than this studio "
                                        r"makes in one go \(0\.5\)"):
        R.exercise(record, song, "none", minutes=0.5)


def test_a_version_not_kept_answers_the_same_as_one_never_made(public):
    studio, port, _ = public
    for vid in ("0" * 32, "f" * 32, "not-an-id", "0" * 31):
        status, _, page = ask(port, "GET", f"/v/{vid}")
        assert status == 404 and b"isn't kept here" in page
    status, _, body = ask(port, "POST", "/api/song", {"edits": {}},
                          {"Content-Type": "application/json", "X-Studio": f"{studio.token}.{'0' * 32}"})
    assert status == 404 and "isn't kept here" in json.loads(body)["error"]
    status, _, _ = ask(port, "GET", "/api/start", headers={"X-Studio": f"{studio.token}.{'0' * 32}"})
    assert status == 404


# ---------------------------------------------------------------- the versions kept


def test_versions_are_kept_under_a_keyed_id_and_let_go(tmp_path):
    record, song = {"id": "a" * 64, "title": "T"}, b'{"title": "T"}'
    kept = R.Versions(tmp_path / "v", limit=10**6, days=30)
    vid = kept.put(record, song)
    assert R.VERSION.fullmatch(vid) and kept.put(record, song) == vid  # the same, the same
    assert stat.S_IMODE((tmp_path / "v" / ".key").stat().st_mode) == 0o600
    assert R.Versions(tmp_path / "v", 10**6, 30).put(record, song) == vid  # the key outlives the studio
    assert R.Versions(tmp_path / "w", 10**6, 30).put(record, song) != vid  # another studio's key, another id
    assert kept.get(vid)[0] == record and kept.get("0" * 32) is None and kept.get("../v") is None
    old = time.time() - 31 * 86400
    os.utime(tmp_path / "v" / vid, (old, old))
    assert kept.get(vid) is None
    kept.prune()
    assert not (tmp_path / "v" / vid).exists() and (tmp_path / "v" / ".key").exists()
    small = R.Versions(tmp_path / "s", limit=1, days=30, most=10)
    first = small.put({"id": "1"}, song)
    small.put({"id": "2"}, song)
    assert small.get(first) is None  # past the cap, the least recently opened goes first


def test_the_songs_remembered_are_the_latest_few():
    class Song:
        pass

    @variation.per_genome
    def asked(genome, n):
        return n * 2

    songs = [Song() for _ in range(variation.GENOMES_REMEMBERED + 4)]
    refs = [weakref.ref(s) for s in songs]
    for s in songs:
        assert asked(s, 3) == 6
    del songs, s
    import gc

    gc.collect()
    assert sum(r() is not None for r in refs) == variation.GENOMES_REMEMBERED


def test_an_address_is_counted_by_its_network_and_a_version_never_logged():
    assert P.network("203.0.113.5") == "203.0.113.5"
    assert P.network("2001:db8:1:2:aaaa::1") == P.network("2001:db8:1:2:bbbb::9") == "2001:db8:1:2::/64"
    assert P.network("::ffff:203.0.113.5") == "::ffff:203.0.113.5"
    gate = P.Gate(P.Limits(opens=5, opens_ip=2))
    gate.render("opens", "ann", "2001:db8:1:2::1", now=0)
    gate.render("opens", "bob", "2001:db8:1:2::2", now=1)
    with pytest.raises(P.Limited, match="versions opened"):
        gate.render("opens", "cat", "2001:db8:1:2::3", now=2)
    assert "/v/…" in P.access_line("GET", "/v/0123456789abcdef0123456789abcdef", 200, 1, 0.1)


def test_this_computers_own_studio_takes_a_version_the_same_way(home, parent):
    studio = S.Studio(None, str(LEAD), "none", out=home / "out")
    server = S.serve(studio, 18870)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port = server.server_address[1]
        status, why = send(port, b"fLaC" + bytes(100), studio.token)
        assert status == 422 and "carries no packet" in why["error"]
        status, answer = send(port, parent.read_bytes(), studio.token)
        assert status == 200 and answer["version"]["generation"] == 2
        assert send(port, b"fLaC" + bytes(100), None)[0] == 403  # still only its own page
    finally:
        server.shutdown()
        server.server_close()


def test_a_section_sung_again_as_its_own_is_one_the_song_has(parent):
    """A version that sings the bridge twice has bridge2 in its form (Genome.section): the song has it, so a record
    that sings it is read; a name that isn't a section, or a section's name with letters after it, still isn't."""
    record = pack.read_manifest(parent)
    genome = load(LEAD)
    params = dict(record["params"], form=[*record["params"]["form"], "bridge", "bridge2"])
    assert R.clean_params(params, genome)["form"][-1] == "bridge2"
    for bad in ("bridge2x", "coda2"):
        with pytest.raises(R.Refused, match="doesn't have"):
            R.clean_params(dict(params, form=[*params["form"], bad]), genome)
