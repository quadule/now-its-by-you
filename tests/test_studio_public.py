"""The studio open to the public (`songbird studio --public`): no key needed, each visitor held to one render
at a time and a few an hour (and their address to a few more), an honest answer when the queue is full,
recordings offered for download for a while and not kept, a slow or silent connection closed, the visitor's
address believed from a proxy's header only when the proxy is near, and a log that never says who. The
local studio is as it was."""

import argparse
import contextlib
import http.client
import io
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from songbird import public as P, studio as S

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


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
    status, head, data = ask(port, "POST", path, body, head)
    return status, json.loads(data), head


def open_studio(home, **limits):
    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits(**limits))
    gate = threading.Event()

    def slow(job, v, key, *rest):  # a render that waits to be let go, and makes a small file
        job.plan = [("x", 1.0)]
        gate.wait(30)
        folder = studio.cache / key
        folder.mkdir(exist_ok=True)
        (folder / "rendition.flac").write_bytes(b"fLaC" + bytes(256))
        (folder / "rendition.json").write_text(json.dumps({"id": key * 2, "duration": 1.0, "generation": 1}))
        S.link(folder / "rendition.flac", studio.cache / f"{key}.flac")
        job.url = f"/audio/{key}.flac"
        return {"url": job.url}

    studio._section = slow
    studio._whole = slow
    return studio, gate


@pytest.fixture
def opened(home):
    studio, gate = open_studio(home, records=2, records_ip=3, previews=3, previews_ip=100, queue=3)
    server = S.serve(studio, 18830, client_ip_header="CF-Connecting-IP")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1], gate
    gate.set()
    server.shutdown()
    server.server_close()


def visitor(port):
    """A first visit: the page, and the cookie it sets for the visitor."""
    status, head, page = ask(port, "GET", "/")
    assert status == 200
    cookie = head["Set-Cookie"].split(";")[0]
    assert cookie.startswith(f"songbird-visitor-{port}=") and "HttpOnly" in head["Set-Cookie"]
    return {"Cookie": cookie}


def running(studio, job_id):
    for _ in range(200):
        if studio.jobs.get(job_id).state == "running":
            return
        time.sleep(0.01)
    raise TimeoutError


def test_the_limits_are_named_on_the_command_line_and_checked():
    limits = P.Limits.parse(["records=2", "records-ip=5", "download-hours=1.5", "cache-mb=50"])
    assert (limits.records, limits.records_ip, limits.download_hours, limits.cache_mb) == (2, 5, 1.5, 50)
    for bad in ("records", "records=", "nothing=3", "records=many", "queue=0", "timeout=-1"):
        with pytest.raises(ValueError, match="--limit"):
            P.Limits.parse([bad])
    parser = argparse.ArgumentParser()
    S.add_arguments(parser)
    args = parser.parse_args([])
    assert not args.public and args.limit == [] and args.machine is None  # "here", as ever, when not public
    with pytest.raises(SystemExit, match="--public"):
        S.run(parser.parse_args(["--limit", "records=3"]))
    with pytest.raises(SystemExit, match="--limit"):
        S.run(parser.parse_args(["--public", "--limit", "records=none"]))
    with pytest.raises(SystemExit, match="header"):
        S.run(parser.parse_args(["--public", "--client-ip-header", "CF Connecting IP"]))
    shares, here = S.links("0.0.0.0", 8766, ["studio.example.test"], ["studio.example.test"], None)
    assert shares == ["https://studio.example.test/"] and here == "http://127.0.0.1:8766/"


def test_a_visitor_and_an_address_are_counted_an_hour_under_a_key_never_written_down():
    gate = P.Gate(P.Limits(records=2, records_ip=3, previews=1, previews_ip=1))
    gate.render("records", "ann", "203.0.113.5", now=0)
    gate.render("records", "ann", "203.0.113.5", now=10)
    with pytest.raises(P.Limited, match="You've had 2 whole songs") as e:
        gate.render("records", "ann", "203.0.113.5", now=20)
    assert 3500 < e.value.retry <= 3600  # the first of hers is an hour old then
    gate.render("records", "bob", "203.0.113.5", now=30)  # another person at the same address
    with pytest.raises(P.Limited, match="Your network"):
        gate.render("records", "cat", "203.0.113.5", now=40)
    gate.render("records", "ann", "203.0.113.5", now=3601)  # an hour on, one of hers has gone
    gate.render("previews", "dan", "198.51.100.7", now=0)  # sections are counted apart from whole songs
    state = repr(gate.hour) + repr(gate.minute.seen)
    assert "203.0.113.5" not in state and "ann" not in state  # counted under a keyed hash, nothing else
    assert P.Gate(gate.limits).who("ip:203.0.113.5") != gate.who("ip:203.0.113.5")  # a new key each start
    fast = P.Gate(P.Limits(requests=3))
    for t in range(3):
        fast.request("192.0.2.1", now=t)
    with pytest.raises(P.Limited, match="Too many requests"):
        fast.request("192.0.2.1", now=3)
    fast.request("192.0.2.1", now=61)
    assert P.about(30) == "a minute" and P.about(420) == "about 7 minutes" and P.about(3 * 3600) == "about 3 hours"


def test_the_public_queue_takes_previews_in_turn_and_one_at_a_time_for_each_visitor():
    jobs = S.Jobs(4, fair=True)
    gate = threading.Event()
    first = jobs.submit("a", "preview", "a", lambda job: gate.wait(30), owner="ann")
    for _ in range(100):
        if first.state == "running":
            break
        time.sleep(0.01)
    try:
        with pytest.raises(P.Limited, match="being made now"):  # hers is running: she waits for it
            jobs.submit("a2", "preview", "x", lambda job: None, owner="ann")
        b = jobs.submit("b", "preview", "b", lambda job: None, owner="bob")
        c = jobs.submit("c", "preview", "c", lambda job: None, owner="cat")
        assert jobs.view(b)["ahead"] == 1 and jobs.view(c)["ahead"] == 2  # in the order asked
        assert jobs.view(c)["eta"] >= jobs.view(b)["eta"] > 0
        c2 = jobs.submit("c2", "preview", "c2", lambda job: None, owner="cat")  # she moved on: hers gives way
        assert c.state == "failed" and c.error == "cancelled" and jobs.view(c2)["ahead"] == 2
        r = jobs.submit("r", "record", "r", lambda job: None, owner="dan", whole=True)
        assert jobs.view(r)["ahead"] == 1  # a recording still goes first
        with pytest.raises(P.Limited, match="recording is waiting"):
            jobs.submit("r2", "preview", "x", lambda job: None, owner="dan")
        jobs.submit("e", "preview", "e", lambda job: None, owner="eve")
        with pytest.raises(S.Busy, match=r"busy: 4 songs are waiting.*Try again in") as e:
            jobs.submit("f", "preview", "f", lambda job: None, owner="fay")
        assert e.value.retry > 60
        assert jobs.submit("b", "preview", "b", lambda job: None, owner="fay") is b  # the same song: no new work
    finally:
        gate.set()


def test_a_public_studio_needs_no_key_and_gives_each_visitor_a_random_id(opened):
    studio, port, _ = opened
    assert studio.shared and studio.share_key is None
    first, second = visitor(port), visitor(port)
    assert first != second
    status, head, _ = ask(port, "GET", "/", headers=first)
    assert status == 200 and "Set-Cookie" not in head  # known already
    start = json.loads(ask(port, "GET", "/api/start", headers=first)[2])
    assert start["shared"] and start["public"] == {"records": 2, "previews": 3, "download_hours": 24.0}
    assert start["out"] == "" and not start["sing"]["available"] and "24 hours" in start["packet"]
    assert json.loads(ask(port, "GET", "/healthz")[2]) == {"ok": True, "waiting": 0, "running": False}
    assert ask(port, "GET", "/api/start", headers={"Host": "evil.example"})[0] == 403  # its own names, as ever
    s = S.Studio(None, str(LEAD), "none", public=P.Limits(), key="closed-beta-key")  # a key can still close it
    assert s.shared and s.share_key == "closed-beta-key"


def test_a_second_visitor_hears_where_they_are_in_line_and_a_full_queue_says_so(opened):
    studio, port, gate = opened
    ann, bob, cat, dan, eve = (visitor(port) for _ in range(5))
    status, job, _ = post(port, studio, "/api/record", {"edits": {}}, **ann)
    assert status == 200 and job["kind"] == "record"
    running(studio, job["id"])
    status, again, head = post(port, studio, "/api/listen", {"edits": {"roll": 9}, "section": 1}, **ann)
    assert status == 429 and "being made now" in again["error"] and again["busy"] and int(head["Retry-After"]) >= 1
    for n, who in enumerate((bob, cat, dan), start=1):
        status, waiting, _ = post(port, studio, "/api/listen", {"edits": {"roll": 10 + n}, "section": 0}, **who)
        assert status == 200 and waiting["state"] == "queued" and waiting["ahead"] == n and waiting["eta"] > 0
    status, full, head = post(port, studio, "/api/listen", {"edits": {"roll": 20}, "section": 0}, **eve)
    assert status == 503 and "3 songs are waiting" in full["error"] and int(head["Retry-After"]) > 1
    # the same song asked for by another is theirs to hear, not to cancel
    status, shared, _ = post(port, studio, "/api/listen", {"edits": {"roll": 11}, "section": 0}, **eve)
    assert status == 200 and shared["ahead"] == 1
    assert not post(port, studio, "/api/cancel", {"job": shared["id"]}, **eve)[1]["cancelled"]
    assert post(port, studio, "/api/cancel", {"job": shared["id"]}, **bob)[1]["cancelled"]
    gate.set()


def test_hourly_limits_by_visitor_and_by_the_address_a_near_proxy_names(opened):
    studio, port, gate = opened
    gate.set()
    ann = visitor(port)
    cf = {"CF-Connecting-IP": "203.0.113.9"}

    def record(who, roll, **extra):  # each roll of chance another song
        status, job, head = post(port, studio, "/api/record", {"edits": {"roll": roll}}, **who, **extra)
        if status == 200 and job["state"] != "done":
            for _ in range(200):
                if studio.jobs.get(job["id"]).state == "done":
                    break
                time.sleep(0.01)
        return status, job

    assert record(ann, 1, **cf)[0] == 200 and record(ann, 2, **cf)[0] == 200
    status, refused = record(ann, 3, **cf)
    assert status == 429 and "2 whole songs" in refused["error"]
    assert record(ann, 1, **cf)[0] == 200  # made already: no new work, no count
    assert record(visitor(port), 4, **cf)[0] == 200  # another visitor, the same address: 3 an hour for it
    status, refused = record(visitor(port), 5, **cf)
    assert status == 429 and "Your network" in refused["error"]
    assert record(visitor(port), 6, **{"CF-Connecting-IP": "198.51.100.1"})[0] == 200  # another address
    # the header is believed only from a proxy near it (here: this computer), and only when configured
    assert P.client_ip("127.0.0.1", cf, "CF-Connecting-IP") == "203.0.113.9"
    assert P.client_ip("172.18.0.3", cf, "CF-Connecting-IP") == "203.0.113.9"  # a container beside it
    assert P.client_ip("::ffff:10.0.0.2", cf, "CF-Connecting-IP") == "203.0.113.9"
    assert P.client_ip("198.51.100.20", cf, "CF-Connecting-IP") == "198.51.100.20"  # from anywhere else: no
    assert P.client_ip("2001:db8::5", cf, "CF-Connecting-IP") == "2001:db8::5"
    assert P.client_ip("127.0.0.1", cf, None) == "127.0.0.1"
    assert P.client_ip("127.0.0.1", {"CF-Connecting-IP": "not an address"}, "CF-Connecting-IP") == "127.0.0.1"


def test_a_public_recording_is_offered_for_download_for_a_while_and_not_kept(opened, home):
    studio, port, gate = opened
    gate.set()
    ann = visitor(port)
    status, job, _ = post(port, studio, "/api/record", {"edits": {}}, **ann)
    for _ in range(200):
        if studio.jobs.get(job["id"]).state == "done":
            break
        time.sleep(0.01)
    recorded = studio.jobs.view(studio.jobs.get(job["id"]))["result"]["recorded"]
    assert recorded["download"].startswith("/download/") and recorded["expires"] == 24.0 and recorded["shared"]
    assert "/" not in recorded["flac"] and recorded["next"] == f"python3 {recorded['name']} studio"
    assert not (home / "out").exists()  # nothing kept where a local studio keeps recordings
    status, head, data = ask(port, "GET", recorded["download"], headers=ann)
    assert status == 200 and data[:4] == b"fLaC"
    assert head["Content-Disposition"] == f'attachment; filename="{recorded["name"]}"'
    # the cache can let its copy go; the download waits its hours
    key = recorded["download"].split("/")[-1].split(".")[0]
    (studio.cache / f"{key}.flac").unlink()
    assert ask(port, "GET", recorded["download"], headers=ann)[0] == 200
    kept = studio.downloads.folder / f"{key}.flac"
    old = time.time() - 25 * 3600
    import os

    os.utime(kept, (old, old))
    status, _, data = ask(port, "GET", recorded["download"], headers=ann)
    assert status == 404 and b"isn't kept here any more" in data
    studio.downloads.prune()
    assert not kept.exists()


def test_the_download_store_keeps_to_its_size_the_oldest_going_first(tmp_path):
    store = P.Downloads(tmp_path / "d", limit=10**6, hours=1e9)  # nothing expires: only the size counts
    import os

    for n, key in enumerate(("aa" * 8, "bb" * 8, "cc" * 8)):
        src = tmp_path / f"{key}.src"
        src.write_bytes(bytes(400))
        store.keep(src, key)
        os.utime(store.folder / f"{key}.flac", (1e9 + n, 1e9 + n))
    store.limit = 1000
    store.prune()
    assert sorted(p.stem for p in store.folder.glob("*.flac")) == ["bb" * 8, "cc" * 8]


def test_a_silent_connection_is_closed_and_the_log_never_says_who(home, capsys):
    studio, gate = open_studio(home, timeout=1, requests=3)
    gate.set()
    server = S.serve(studio, 18840)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as s:
            began = time.monotonic()
            assert s.recv(1) == b""  # nothing sent: closed after the timeout, not held open
            assert time.monotonic() - began < 5
        for _ in range(2):
            ask(port, "GET", "/api/start?secret=1", headers={"Cookie": f"songbird-visitor-{port}=" + "v" * 24})
        with contextlib.redirect_stdout(io.StringIO()):  # as a whole song's render does, for every thread
            ask(port, "GET", "/api/start")  # logged all the same
        status, head, _ = ask(port, "GET", "/api/start")
        assert status == 429 and int(head["Retry-After"]) >= 1
        assert ask(port, "GET", "/healthz")[0] == 200  # never limited
        out = capsys.readouterr().out
        lines = [line for line in out.splitlines() if " /api/start " in line]
        assert len(lines) == 4 and lines[-1].split()[3] == "429"
        assert "127.0.0.1" not in out and "secret" not in out and "v" * 24 not in out
    finally:
        server.shutdown()
        server.server_close()


def test_a_visitors_stems_wait_their_turn_and_count_as_a_whole_song(opened):
    """The parts are a render as long as the whole song: in a public studio they queue as one, one at a time
    for each visitor, and count against the whole songs a visitor may have made an hour. MIDI is made at once."""
    studio, port, gate = opened
    ann = visitor(port)
    studio._stems = lambda job, v, key, name: gate.wait(30) and {"url": None}
    status, made, _ = post(port, studio, "/api/export", {"edits": {}, "what": "midi"}, **ann)
    assert status == 200 and made["state"] == "done" and ask(port, "GET", made["url"], headers=ann)[0] == 200
    status, job, _ = post(port, studio, "/api/export", {"edits": {}, "what": "stems"}, **ann)
    assert status == 200 and studio.jobs.get(job["id"]).owner is not None and studio.jobs.get(job["id"]).whole
    running(studio, job["id"])
    status, refused, _ = post(port, studio, "/api/listen", {"edits": {}, "section": 1}, **ann)
    assert status == 429 and "one at a time" in refused["error"]  # theirs is being made
    gate.set()
    for _ in range(200):
        if studio.jobs.get(job["id"]).state == "done":
            break
        time.sleep(0.01)
    assert post(port, studio, "/api/export", {"edits": {"roll": 1}, "what": "stems"}, **ann)[0] == 200
    time.sleep(0.05)
    status, refused, _ = post(port, studio, "/api/export", {"edits": {"roll": 2}, "what": "stems"}, **ann)
    assert status == 429 and "2 whole songs" in refused["error"]


def test_the_local_studio_is_as_it_was(home, capsys):
    studio = S.Studio(None, str(LEAD), "none", out=home / "out")
    assert not studio.shared and studio.public is None and studio.gate is None and studio.downloads is None
    server = S.serve(studio, 18850)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        status, head, _ = ask(port, "GET", "/")
        assert status == 200 and "Set-Cookie" not in head
        assert ask(port, "GET", "/healthz")[0] == 404 and ask(port, "GET", "/download/" + "a" * 16 + ".flac")[0] == 404
        start = json.loads(ask(port, "GET", "/api/start")[2])
        assert "public" not in start and start["out"]
        assert server.RequestHandlerClass.timeout is None and server.slots is None
        assert capsys.readouterr().out == ""  # quiet, as ever
    finally:
        server.shutdown()
        server.server_close()
