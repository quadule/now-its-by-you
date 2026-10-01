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
import re
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
    monkeypatch.setenv("STUDIO_MEMORY", "16g")  # a public studio with room for any whole song (its budget: public.render_mb)
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


def test_one_address_has_a_few_renders_waiting_however_many_visitors_it_holds():
    """A visitor is a cookie, and a client without one is a new visitor each time: the address (an IPv6 one by its
    /64) has queue_ip renders waiting at most, so one sender can't fill the queue for everyone."""
    jobs = S.Jobs(12, fair=True, per_address=2)
    gate = threading.Event()
    first = jobs.submit("run", "preview", "x", lambda job: gate.wait(30), owner="ann", where="198.51.100.1")
    try:
        running(type("S", (), {"jobs": jobs})(), first.id)
        where = P.network("2001:db8:1:2::5")
        jobs.submit("a", "preview", "a", lambda job: None, owner="ip:1", where=where)
        jobs.submit("b", "preview", "b", lambda job: None, owner="ip:2", where=P.network("2001:db8:1:2::77"))
        with pytest.raises(P.Limited, match="Your network has 2 songs waiting"):
            jobs.submit("c", "preview", "c", lambda job: None, owner="ip:3", where=P.network("2001:db8:1:2:ffff::9"))
        jobs.submit("d", "preview", "d", lambda job: None, owner="ip:4", where=P.network("2001:db8:1:3::5"))  # another
        assert jobs.submit("a", "preview", "a", lambda job: None, owner="ip:5", where=where).key == "a"  # the same song
        assert P.Limits().queue_ip == 3 and P.Limits.parse(["queue-ip=2"]).queue_ip == 2
    finally:
        gate.set()


def test_one_address_has_a_few_connections_served_at_once_and_a_slow_reader_is_let_go(home):
    """The studio serves `connections` at once for everyone: one address has connections_ip of them at most, and a
    download sent slower than send_kb a second (after its grace) is ended, so a reader taking a byte at a time can't
    hold a place for days."""
    studio, gate = open_studio(home, connections_ip=2, send_kb=4096)
    gate.set()
    server = S.serve(studio, 18870, client_ip_header="CF-Connecting-IP")
    server.RequestHandlerClass.send_grace = 0.2
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    key = "cd" * 12
    (studio.cache / f"{key}.flac").write_bytes(bytes(40 * 2**20))
    try:
        def stalled(ip):  # a download asked for and not read: the studio blocks sending it
            s = socket.create_connection(("127.0.0.1", port), timeout=10)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            s.sendall(f"GET /audio/{key}.flac HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nCF-Connecting-IP: {ip}\r\n\r\n"
                      .encode())
            return s

        held = [stalled("203.0.113.7"), stalled("203.0.113.7")]
        for _ in range(200):
            if studio._serving.get("203.0.113.7") == 2:
                break
            time.sleep(0.01)
        status, head, _ = ask(port, "GET", "/api/start", headers={"CF-Connecting-IP": "203.0.113.7"})
        assert status == 429 and int(head["Retry-After"]) >= 1  # a third from the same address: turned away
        assert ask(port, "GET", "/api/start", headers={"CF-Connecting-IP": "198.51.100.3"})[0] == 200  # another
        assert ask(port, "GET", "/healthz")[0] == 200
        began = time.monotonic()
        got = 0
        for s in held:  # read slowly: far under the least rate, so each is ended
            while True:
                try:
                    chunk = s.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break
                got += len(chunk)
                time.sleep(0.005)
            s.close()
        assert got < 8 * 2**20 and time.monotonic() - began < 30, got  # each ended early
        for _ in range(200):
            if not studio._serving:
                break
            time.sleep(0.01)
        assert not studio._serving  # their places given back
        assert ask(port, "GET", "/api/start", headers={"CF-Connecting-IP": "203.0.113.7"})[0] == 200
    finally:
        server.shutdown()
        server.server_close()


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
    studio._stems = lambda job, v, key: gate.wait(30) and {"url": None}
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


def test_a_range_of_a_large_recording_is_streamed_not_held_in_memory(opened):
    """A player asks for `bytes=0-` (the whole of a 17 MB song) on every connection it opens: each range is sent
    as it's read, a block at a time, so a few dozen players never hold a few dozen songs in the studio's memory."""
    import hashlib
    import os
    import tracemalloc

    studio, port, _ = opened
    key = "ab" * 12
    data = os.urandom(20 * 2**20)
    (studio.cache / f"{key}.flac").write_bytes(data)

    def fetch(rng):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        c.request("GET", f"/audio/{key}.flac", headers={"Host": f"127.0.0.1:{port}", "Range": rng})
        r = c.getresponse()
        h, n = hashlib.sha256(), 0
        while True:
            chunk = r.read(2**16)
            if not chunk:
                break
            h.update(chunk)
            n += len(chunk)
        out = r.status, r.getheader("Content-Range"), int(r.getheader("Content-Length")), n, h.hexdigest()
        c.close()
        return out

    tracemalloc.start()
    try:
        status, where, length, n, digest = fetch("bytes=0-")
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert status == 206 and where == f"bytes 0-{len(data) - 1}/{len(data)}" and length == n == len(data)
    assert digest == hashlib.sha256(data).hexdigest()
    assert peak < 4 * 2**20  # blocks of 64 KB, never the 20 MB
    status, where, length, n, digest = fetch("bytes=1000-2000047")
    assert (status, where, length, n) == (206, f"bytes 1000-2000047/{len(data)}", 1999048, 1999048)
    assert digest == hashlib.sha256(data[1000:2000048]).hexdigest()
    status, where, length, n, digest = fetch("bytes=-5000")  # the last 5000
    assert (status, length, digest) == (206, 5000, hashlib.sha256(data[-5000:]).hexdigest())
    assert fetch(f"bytes={len(data)}-")[0] == 416


def test_a_public_studios_day_moves_on_at_midnight_and_what_was_asked_keeps_its_own(opened, home):
    """A studio running for weeks sings each day's version, not its first day's: at this computer's midnight the
    day, the machine's context and the page's timeline move on, and versions someone brought open again on it; a
    render asked for before keeps the version (and so the day) it was asked with. A local studio keeps its day."""
    from datetime import date, timedelta

    studio, port, gate = opened
    day = date.fromisoformat(studio.day)
    clock = [day]
    studio.clock = lambda: clock[0]
    asked = []
    slow = studio._whole
    studio._whole = lambda job, v, key: asked.append(v.drift.to_dict()["at"][:10]) or slow(job, v, key)
    ann = visitor(port)
    assert json.loads(ask(port, "GET", "/api/start", headers=ann)[2])["day"] == studio.day
    status, job, _ = post(port, studio, "/api/record", {"edits": {}}, **ann)
    running(studio, job["id"])
    before = post(port, studio, "/api/song", {"edits": {}}, **ann)[1]
    studio._timeline = {"drawn": "yesterday's"}
    studio._opened["f" * 32] = studio  # a version someone brought, opened on the old day
    clock[0] = day + timedelta(days=1)  # midnight
    start = json.loads(ask(port, "GET", "/api/start", headers=ann)[2])
    assert start["day"] == studio.day == (day + timedelta(days=1)).isoformat()
    assert studio.context.day == studio.day and studio._timeline is None and not studio._opened
    after = post(port, studio, "/api/song", {"edits": {}}, **ann)[1]
    assert after["listen"]["whole"] != before["listen"]["whole"]  # another day's version
    gate.set()
    for _ in range(200):
        if studio.jobs.get(job["id"]).state == "done":
            break
        time.sleep(0.01)
    assert asked == [day.isoformat()]  # the recording asked for yesterday is yesterday's
    assert not studio.roll()  # the same day: nothing moves
    local = S.Studio(None, str(LEAD), "none", out=home / "out")
    first = local.day
    local.clock = lambda: date.fromisoformat(first) + timedelta(days=3)
    assert not local.roll() and local.day == first  # this computer's own studio: as ever


def test_the_page_says_plainly_what_an_open_studio_keeps(opened):
    """The footer, Help and the Tools sheet say what's kept: a random id in a cookie, changes in the browser, a
    recording a day, a shared link's and a file's own record, singing's numbers (only where singing is on)."""
    studio, port, _ = opened
    page = ask(port, "GET", "/")[2].decode()
    assert '<p id="helpKept" hidden></p>' in page  # filled and shown in an open studio only (studio.js applyPublic)
    script = (S.PAGE / "studio.js").read_text()
    for said in ("What's kept: a random id in a cookie", "sent only to make the song", "its made-up machine's name",
                 "room its microphone heard, the leanings of its words", "carries its version's own record",
                 "only numbers are kept; the audio is deleted once it's measured",
                 "Your changes stay in this browser (Help says what's kept)"):
        assert said in script, said
    assert "What's kept" in (S.PAGE / "score.js").read_text() and "helpKept" in (S.PAGE / "index.html").read_text()


def test_the_plain_pages_carry_no_style_the_policy_would_block(home):
    """A shared studio's page for a visitor without its key, and a version not kept here: their look in a stylesheet
    (style-src 'self' blocks a style written in the page), which a visitor without the key may fetch."""
    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits(), key="closed-beta-key")
    server = S.serve(studio, 18880)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        for path, code in (("/", 403), ("/v/" + "0" * 32 + "?key=closed-beta-key", 404)):
            status, head, page = ask(port, "GET", path)
            assert status == code and b"style=" not in page and b"<style" not in page, path
            assert b"href='/notice.css'" in page and b"class=notice" in page and "style-src 'self'" in \
                head["Content-Security-Policy"]
        status, head, css = ask(port, "GET", "/notice.css")
        assert status == 200 and head["Content-Type"].startswith("text/css") and b"body.notice" in css
    finally:
        server.shutdown()
        server.server_close()


def test_a_public_studio_in_its_beta_asks_search_engines_not_to_list_it(opened):
    studio, port, _ = opened
    assert "X-Robots-Tag" not in ask(port, "GET", "/")[1] and ask(port, "GET", "/robots.txt")[0] == 404  # not asked
    studio.noindex = True  # --noindex
    for path in ("/", "/studio.js", "/api/start", "/audio/" + "a" * 16 + ".flac"):
        assert ask(port, "GET", path)[1]["X-Robots-Tag"] == "noindex, nofollow", path
    status, head, data = ask(port, "GET", "/robots.txt")
    assert status == 200 and data == b"User-agent: *\nDisallow: /\n" and head["X-Robots-Tag"]
    parser = argparse.ArgumentParser()
    S.add_arguments(parser)
    with pytest.raises(SystemExit, match="--noindex"):
        S.run(parser.parse_args(["--noindex"]))  # for a public studio only


# ---------------------------------------------------------------- a whole song's memory

# Measured on 30 September, after the heaviest parts were made lean (tools/render_memory.py, two threads,
# MallocLargeCache=0; docs/WEB-STUDIO.md, "A whole song's memory"): H with each style's own band as the program sings
# it (no edits but the style), and the ballad, chamber and the kit's bands drawn out to 4 to 8.5 minutes (more
# verses, every part, the slowest tempo). (seconds, the render's parts, its peak in MB)
BALLAD = "bass drone drum fiddle guitar harp lute voice whistle"
MEASURED = {
    "seed": (151.4, BALLAD, 1303),
    "ballad": (151.7, BALLAD, 1348),
    "ballad 3 verses, every part": (216.7, BALLAD, 1567),
    "ballad 4 verses, every part, slowest": (347.2, BALLAD, 2360),
    "chamber": (189.0, "cello piano strings voice", 1298),
    "chamber, 2 verses, tempo 60": (238.5, "cello piano strings voice", 1567),
    "chamber, 3 verses, tempo 48.4, every part": (341.6, "cello piano strings voice", 2263),
    "chamber, 4 verses, tempo 48.4, every part": (413.0, "cello piano strings voice", 2527),
    "lullaby": (298.2, "celesta harp musicbox synthpad voice", 1689),
    "ambient": (213.8, "drone strings synthpad vibes voice", 1558),
    "synthfolk": (132.2, "arp drummachine guitar synthbass synthlead synthpad voice", 1145),
    "lofi": (186.0, "drummachine epiano synthbass vibes voice", 1451),
    "songwriter": (160.6, "bass guitar harmonica voice", 1097),
    "country": (151.7, "bass guitar kit piano steel voice", 1430),
    "country 4 verses, every part, slowest": (347.2, "bass guitar kit piano steel voice", 2407),
    "blues": (165.3, "guitar harmonica slide stomps voice", 1342),
    "gospel": (225.2, "claps ebass kit organ piano tambourine voice", 1897),
    "gospel 4 verses, every part, slowest": (506.6, "claps ebass kit organ piano tambourine voice", 3867),
    "indie": (127.9, "claps ebass electric glock guitar kit organ voice", 1220),
    "indie 4 verses, every part, slowest": (344.5, "claps ebass electric glock guitar kit organ voice", 2484),
    "shanty": (151.2, "bass claps concertina fiddle stomps voice", 1133),
    "stringband": (124.9, "banjo bass fiddle guitar mandolin voice", 1118),
    # beside the ring (docs/STYLES.md, "Two more", 2026-09-30): voices alone, and the jig (it was a session, with
    # a reel); both measured again after "A cappella and the jig, revised" but the straight a cappella and the reel
    "acappella (waltz, three voices of its own)": (224.7, "choir1 choir2 choir3 voice", 1540),
    "acappella, six lineage voices": (224.7, "choir1 choir2 choir3 choir4 choir5 choir6 voice", 1530),
    "acappella, straight": (158.9, "choir1 choir2 choir3 voice", 1200),
    "acappella 4 verses, every part, six voices, tempo 55": (450.4, "choir1 choir2 choir3 choir4 choir5 choir6 voice",
                                                             2560),
    "jig": (112.2, "concertina drum fiddle guitar voice whistle", 990),
    # the old 78 (docs/STYLES.md, "An old 78", 2026-09-30): the song's length as the studio estimates it (the
    # record has three seconds of run-out groove more); a parlour piano alone, mono: the lightest band yet
    "old78 (a parlour piano, a waltz)": (242.9, "piano voice", 1140),
    "old78, 4 verses, every part, a fiddle, tempo 58": (471.0, "fiddle piano voice", 1950),
    "jig 4 verses, every part, tempo 130": (212.7, "concertina drum fiddle guitar voice whistle", 1560),
    "the session before it was the jig: 4 verses, every part, a reel at 91": (
        347.1, "concertina drone drum fiddle guitar voice whistle", 2340),
    # house and dub (2026-09-30; docs/STYLES.md, "House and dub"): dub's with its version after the song
    # again (2026-09-30, evening; "House and dub, again"): house's own lengths and its chop, dub dissolving
    "house": (163.3, "arp chop drummachine piano synthbass synthpad voice", 1270),
    "dub": (222.2, "ebass electric kit melodica organ voice", 1910),
}


def test_a_whole_songs_memory_is_estimated_from_its_length_and_players_never_under_what_was_measured(monkeypatch):
    for name, (seconds, parts, peak) in MEASURED.items():
        estimate = P.render_mb(seconds, parts.split(), threads=2)
        assert peak <= estimate <= peak * 1.3, (name, estimate, peak)
    assert P.render_mb(100, ["voice", "kit"]) > P.render_mb(100, ["voice", "guitar"])  # the heaviest part sets it
    from songbird.synth.instruments import known

    assert set(known()) <= set(P.RATES)  # every instrument measured (tools/part_memory.py for a new one)
    assert P.render_mb(100, ["voice", "theremin"]) == P.BASE_MB + 100 * P.UNMEASURED * P.MARGIN  # never measured
    assert P.render_mb(100, ["voice"], threads=6) > P.render_mb(100, ["voice"], threads=1) == P.render_mb(100, ["voice"])
    assert P.render_mb(100, ["voice", "guitar"], stems=True) == pytest.approx(P.render_mb(100, ["voice", "guitar"])
                                                                               + 200 * P.STEM)
    # the budget: the studio's memory (the compose passes STUDIO_MEMORY in), less 400 MB
    for given, mb in (("2500m", 2500), ("2g", 2048), ("8G", 8192), ("2621440000", 2500)):
        monkeypatch.setenv("STUDIO_MEMORY", given)
        assert P.memory_mb() == mb and P.Limits().render_mb == mb - 400
    assert P.Limits.parse(["render-mb=1500"]).render_mb == 1500
    assert P.minutes(413.0) == "6.9 minutes" and P.minutes(180) == "3 minutes"


@pytest.fixture
def budget(home, monkeypatch):
    """A public studio of the VPS's size (2.5 GB, two threads), its renders faked, and a version seven minutes long:
    chamber at its slowest, four verses, every part the song can have (the review's)."""
    from songbird import edits as E, genome

    monkeypatch.setenv("SONGBIRD_THREADS", "2")
    monkeypatch.setenv("STUDIO_MEMORY", "2500m")
    studio, gate = open_studio(home)
    gate.set()
    song = genome.load(LEAD)
    long = {"style.name": "chamber", "tempo": 48.4, "form.verses": 4, **{f"form.{n}": True for n in E.optional(song)}}
    server = S.serve(studio, 18860)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1], long
    server.shutdown()
    server.server_close()


def test_a_whole_song_too_long_for_the_servers_memory_is_refused_before_its_queued(budget):
    studio, port, long = budget
    assert studio.public.render_mb == 2100
    seconds, parts = studio.whole_cost(studio.version(long))
    assert seconds > 400 and "cello" in parts and not studio.fits_here(seconds, parts)[0]
    ann = visitor(port)
    for path, body in (("/api/record", {"edits": long}), ("/api/listen", {"edits": long, "section": None}),
                       ("/api/export", {"edits": long, "what": "stems"})):
        status, refused, _ = post(port, studio, path, body, **ann)
        assert status == 422 and refused["too_long"], (path, refused)
        assert re.match(r"This version is \d+(\.\d)? minutes long, too long for this small server to make in one "
                        r"go \(about \d+(\.\d)? minutes at most with these players\): shorten it \(fewer verses, a "
                        r"quicker tempo\)\.$", refused["error"]), refused
    assert not studio.jobs.pending and not studio.jobs.jobs  # nothing queued, nothing counted
    status, job, _ = post(port, studio, "/api/listen", {"edits": long, "section": 3}, **ann)
    assert status == 200  # a section of it is made as ever
    status, job, _ = post(port, studio, "/api/record", {"edits": {}}, **ann)
    assert status == 200 and job["kind"] == "record"  # the song as the program has it fits
    studio.public.render_mb = 10**6
    assert post(port, studio, "/api/record", {"edits": {**long, "roll": 1}}, **ann)[0] != 422  # a bigger server
    local = S.Studio(None, str(LEAD), "none")
    local.check_whole(local.version(long))  # a local studio makes what it's asked, as ever
