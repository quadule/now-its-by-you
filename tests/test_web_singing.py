"""Singing in the web studio (webstudio/, docs/WEB-SINGING.md): only when asked for; a take is guarded as the
studio's own requests are, waits in its one queue, and its audio is let go once measured; the song is then sung
the visitor's way by a name only their page knows, rounded and bounded, kept a while and forgettable; a guide is
the version on the page; and a take is measured exactly as tools/phrasing.py measures one (without the aligner),
with the template singer singing what was sung, planted gestures and all."""

import hashlib
import http.client
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from songbird import studio as S
from webstudio import kit as KIT, singing as W, worker

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
GUIDE, GUIDE2 = "0123456789ab", "ba9876543210"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("STUDIO_MEMORY", "16g")  # a public studio with room for any whole song (its budget: public.render_mb)
    return tmp_path


def a_kit(root: Path) -> KIT.Kit:
    """A kit with a guide in it and nothing heavy: a minute of the lead song's guide, by its name."""
    kit = KIT.Kit(root)
    for name in (GUIDE, GUIDE2):
        kit.keep_guide(LEAD.stem, name, json.dumps({"duration": 60.0, "notes": [], "tempo": 90.0, "sections": [],
                                                    "beats": []}))
    return kit


PHRASING = {"fields": ["early", "hold", "level", "swell", "scoop", "bend", "fall", "vibrato", "tune"], "source": "song",
            "source_detail": "1 sung take(s)", "phrases": {"v1": [[0.1, 0.9, 1.0, 0.0, -30.0, 0.0, 0.0, -1.0, 0.0]]}}


class FakeMeasurer:
    """The measuring process's answers without the process: what it was asked, and a way of singing."""

    def __init__(self):
        self.asked, self.release = [], threading.Event()
        self.release.set()
        self.running, self.per_second, self.start, self.idle = False, 0.1, 1.0, 0

    def call(self, op, request):
        self.asked.append((op, dict(request)))
        self.release.wait(10)
        if op == "melody":
            return {"wav": wav(1.0, 22050), "rate": 22050}
        return {"measurement": {"notes": []}, "phrasing": PHRASING, "portrait": "Take 1: lined up with the guide.",
                "skipped": [], "seconds": 0.5, "audio_seconds": 6.0}

    def estimate(self, seconds):
        return 2.0

    def learn(self, *a):
        pass

    def stop(self):
        pass


@pytest.fixture
def singing(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    a_kit(home / "kit")
    studio.enable_web_singing(home / "kit")
    fake = studio.singing.measurer = FakeMeasurer()
    server = S.serve(studio, 18780)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1], fake
    server.shutdown()
    server.server_close()


def ask(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request(method, path, body=body, headers={"Host": f"127.0.0.1:{port}", **(headers or {})})
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def post(port, studio, path, body):
    status, _, data = ask(port, "POST", path, json.dumps(body).encode(),
                          {"Content-Type": "application/json", "X-Studio": studio.token})
    return status, json.loads(data)


def wav(seconds=6.0, sr=48000) -> bytes:
    out = io.BytesIO()
    t = np.arange(int(seconds * sr)) / sr
    sf.write(out, 0.2 * np.sin(2 * np.pi * 220 * t), sr, format="WAV", subtype="PCM_16")
    return out.getvalue()


def take(port, studio, meta=None, audio=None, **headers):
    meta = json.dumps({"guide": GUIDE, "section": 1, "from_s": 6.0, "to_s": 14.0, "earlier": [],
                       **(meta or {})}).encode()
    head = {"Content-Type": "application/x-songbird-take", "X-Studio": studio.token, "X-Sing-Meta": str(len(meta)),
            **headers}
    status, _, data = ask(port, "POST", "/api/sing/take", meta + (audio if audio is not None else wav()), head)
    return status, json.loads(data)


def wait(port, job):
    for _ in range(200):
        if job["state"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
        job = json.loads(ask(port, "GET", f"/api/job/{job['id']}")[2])
    raise AssertionError("the job never finished")


# ------------------------------------------------------------ only when asked


def test_without_web_singing_none_of_it_is_served(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    server = S.serve(studio, 18779)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        assert studio.singing is None
        page = ask(port, "GET", "/")[2]
        assert b"/sing.js" not in page and b"/sing.css" not in page
        for path in ("/sing.js", "/karaoke.js", "/recorder.js", "/api/sing/offer",
                     f"/api/sing/melody?guide={GUIDE}&from=0&to=10"):
            assert ask(port, "GET", path)[0] == 404, path
        assert take(port, studio)[0] == 415  # not JSON: the studio's own refusal, nothing of singing's
    finally:
        server.shutdown()
        server.server_close()


def test_the_page_gets_the_singing_and_the_karaokes_own_code(singing):
    studio, port, fake = singing
    page = ask(port, "GET", "/")[2].decode()
    assert '<script type="module" src="/sing.js">' in page and 'href="/sing.css"' in page
    assert ask(port, "GET", "/karaoke.js")[2] == (ROOT / "tools" / "karaoke.js").read_bytes()  # reused, not copied
    assert ask(port, "GET", "/recorder.js")[2] == (ROOT / "tools" / "karaoke-recorder.js").read_bytes()
    assert ask(port, "GET", "/sing.js")[0] == 200 and ask(port, "GET", "/sing.css")[0] == 200
    offer = json.loads(ask(port, "GET", "/api/sing/offer")[2])
    assert offer["available"] and offer["keep_days"] == W.KEEP_DAYS and offer["released"]
    assert offer["speeds"] == [100, 90, 80] and offer["speed"] == 90 and 0 in offer["keys"]
    status, _, body = ask(port, "GET", f"/api/sing/melody?guide={GUIDE}&from=0.000&to=60.000")
    assert status == 200 and body[:4] == b"RIFF"
    assert studio.singing.kit.audio(GUIDE, 0.0, 60.0).is_file()  # kept: asked again, it isn't made again
    assert ask(port, "GET", f"/api/sing/melody?guide={GUIDE}&from=0&to=60")[2] == body and len(fake.asked) == 1
    assert ask(port, "GET", "/api/sing/melody?guide=../../offer&from=0&to=1")[0] == 404
    for a, b in ((0, 900), (6, 14.6), (0.05, 60)):  # only what a page sings: the whole song, or a sung section
        assert ask(port, "GET", f"/api/sing/melody?guide={GUIDE}&from={a}&to={b}")[0] == 404, (a, b)
    assert ask(port, "GET", f"/api/sing/melody?guide={GUIDE}&from=0.001&to=60")[2] == body  # its own, as kept
    assert len(fake.asked) == 1
    start = json.loads(ask(port, "GET", "/api/start")[2])
    assert start["sing"] == {"available": True, "web": True}


def test_a_guide_is_the_version_on_the_page(singing):
    """The words sung are the page's: its version's words, key and tempo, at the speed asked; or the released
    version's; each kept by its digest, which a take names."""
    studio, port, _ = singing
    status, page = post(port, studio, "/api/sing/guide", {"edits": {}, "speed": 100, "key": 0})
    assert status == 200 and page["which"] == "page" and studio.singing.kit.guide(LEAD.stem, page["guide"])
    letters = lambda s: re.sub(r"[^a-z]", "", s.lower())  # noqa: E731
    shown = [letters(line) for w in studio.song({})["words"] if w["sung"] for line in w["lines"]]
    sung = [letters("".join(s["text"] for s in line["syllables"])) for line in page["lines"]]
    assert sung == shown  # the page's own words, line for line
    assert page["tempo"] == studio.version({}).params.tempo
    a, b = next(s["window"] for s in page["sections"] if s.get("window"))  # a section's melody, as the page asks
    query = f"guide={page['guide']}&from={a:.3f}&to={min(page['duration'], b + 1.0):.3f}"
    assert ask(port, "GET", f"/api/sing/melody?{query}")[0] == 200
    status, slow = post(port, studio, "/api/sing/guide", {"edits": {}, "speed": 90, "key": -2})
    assert slow["guide"] != page["guide"] and abs(slow["duration"] - page["duration"] / 0.9) < 1e-6
    first = lambda d: d["lines"][0]["syllables"][0]  # noqa: E731
    assert first(slow)["pitch"] == first(page)["pitch"] - 2 and abs(first(slow)["start"] - first(page)["start"] / 0.9) < 1e-6
    status, again = post(port, studio, "/api/sing/guide", {"edits": {}, "speed": 100, "key": 0})
    assert again["guide"] == page["guide"]  # the same version is the same guide
    status, released = post(port, studio, "/api/sing/guide", {"which": "released", "speed": 100, "key": 0})
    assert status == 200 and released["which"] == "released" and released["tempo"] == 96.0
    words = " ".join(s["text"] for s in released["lines"][0]["syllables"])
    assert words.startswith("They saved it as num bers")  # the release's first line, as the piano page has it
    assert post(port, studio, "/api/sing/guide", {"speed": 70})[0] == 400
    assert post(port, studio, "/api/sing/guide", {"which": "somewhere"})[0] == 400


def test_singing_that_cant_measure_here_says_so(home):
    class Broken(FakeMeasurer):
        def call(self, op, request):
            raise RuntimeError("no pyworld here")

    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    singing = W.Singing(studio, home / "kit", measurer=Broken())
    singing.check()
    assert not singing.available()["available"] and "couldn't start its measuring" in singing.available()["why"]


# ------------------------------------------------------------ a take


def test_a_take_is_guarded_as_the_studios_own_requests_are(singing):
    studio, port, fake = singing
    assert take(port, studio, **{"X-Studio": "wrong"})[0] == 403
    assert take(port, studio, **{"Content-Type": "audio/wav"})[0] == 415
    assert take(port, studio, **{"Host": "evil.example"})[0] == 403
    status, body = take(port, studio, meta={"guide": "ffffffffffff"})
    assert status == 400 and "isn't one this studio made" in body["error"]
    status, body = take(port, studio, meta={"guide": "../../x"})
    assert status == 400 and "isn't one this studio made" in body["error"]
    status, body = take(port, studio, audio=b"not a wav at all" * 10)
    assert status == 400 and "WAV" in body["error"]
    status, body = take(port, studio, meta={"from_s": 50.0, "to_s": 40.0})
    assert status == 400
    assert take(port, studio, audio=wav(40.0))[0] == 400  # far longer than the eight seconds it says it sang
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)  # too big to read: refused before its body
    c.putrequest("POST", "/api/sing/take")
    for k, v in {"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-songbird-take", "X-Studio": studio.token,
                 "X-Sing-Meta": "10", "Content-Length": str(W.MAX_TAKE_BYTES + W.MAX_META_BYTES + 1)}.items():
        c.putheader(k, v)
    c.endheaders()
    assert c.getresponse().status == 413
    c.close()
    assert not fake.asked  # nothing of any of them reached the measuring process


def test_a_take_waits_in_the_queue_and_its_audio_is_let_go(singing, home):
    studio, port, fake = singing
    status, job = take(port, studio)
    assert status == 200 and job["state"] in ("queued", "running", "done") and job["estimate"] >= 1
    job = wait(port, job)
    assert job["state"] == "done", job
    result = job["result"]
    assert result["name"].startswith("sung-") and result["portrait"].startswith("Take 1")
    op, request = fake.asked[0]
    assert op == "take" and request["audio"][:4] == b"RIFF" and request["guide"] == GUIDE
    assert request["from_s"] == 6.0 and request["to_s"] == 14.0 and request["song"] == LEAD.stem
    assert not studio.singing.waiting  # the studio holds no take once it's measured
    assert not [p for p in home.rglob("*") if p.suffix in (".wav", ".flac") and "kit" not in p.parts]
    kept = home / "home" / "studio" / "sung" / f"{result['name']}.json"
    assert kept.exists() and json.loads(kept.read_text())["phrases"]  # numbers only: no audio, no name


def test_a_refused_take_is_said_to_the_singer(singing):
    studio, port, fake = singing
    fake.call = lambda op, request: (_ for _ in ()).throw(W.Refused("Your take sat 5 semitones above the guide's key."))
    job = wait(port, take(port, studio)[1])
    assert job["state"] == "done" and job["result"] == {"refused": "Your take sat 5 semitones above the guide's key."}


def test_the_queue_refuses_a_flood_of_takes(singing):
    studio, port, fake = singing
    fake.release.clear()  # the first is measured and holds; the rest wait, in memory, up to the limit
    jobs = [take(port, studio)[1] for _ in range(W.MAX_WAITING_TAKES + 1)]
    assert all("id" in j for j in jobs)
    status, body = take(port, studio)
    assert status == 503 and "try again" in body["error"]
    fake.release.set()
    for j in jobs:
        assert wait(port, j)["state"] == "done"
    assert not studio.singing.waiting


def test_a_public_studio_counts_takes_against_each_visitors_limits(home):
    from songbird import public as P

    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits(takes=1))
    a_kit(home / "kit")
    studio.enable_web_singing(home / "kit")
    assert studio.singing.measurer.idle == 0  # public: the measuring process goes after every take
    fake = studio.singing.measurer = FakeMeasurer()
    server = S.serve(studio, 18781)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        cookie = {"Cookie": f"songbird-visitor-{port}=someone-singing-here"}
        offer = json.loads(ask(port, "GET", "/api/sing/offer", headers=cookie)[2])
        assert offer["takes_an_hour"] == 1
        fake.release.clear()
        status, job = take(port, studio, **cookie)
        assert status == 200
        status, body = take(port, studio, **cookie)  # one thing in the queue at a time for each visitor
        assert status == 429 and ("being made" in body["error"] or "waiting to be measured" in body["error"])
        fake.release.set()
        assert wait(port, job)["state"] == "done"
        status, body = take(port, studio, **cookie)  # and a few takes an hour
        assert status == 429 and "takes measured" in body["error"] and body["retry"] > 0
        assert take(port, studio, **{"Cookie": f"songbird-visitor-{port}=someone-else"})[0] == 200
    finally:
        server.shutdown()
        server.server_close()


def test_a_public_visitor_has_one_melody_made_at_a_time(home):
    """A guide's melody is made in a public studio's one queue, as the visitor's one thing in it: a second asked for
    while the first waits is refused (429), and nobody else's turn is taken."""
    from songbird import public as P

    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits())
    a_kit(home / "kit")
    studio.enable_web_singing(home / "kit")
    fake = studio.singing.measurer = FakeMeasurer()
    server = S.serve(studio, 18782)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        cookie = {"Cookie": f"songbird-visitor-{port}=someone-singing-here"}
        fake.release.clear()
        first = []
        threading.Thread(target=lambda: first.append(ask(port, "GET", f"/api/sing/melody?guide={GUIDE}&from=0&to=60",
                                                         headers=cookie)[0]), daemon=True).start()
        for _ in range(100):
            if fake.asked:
                break
            time.sleep(0.05)
        assert ask(port, "GET", f"/api/sing/melody?guide={GUIDE2}&from=0&to=60", headers=cookie)[0] == 429
        fake.release.set()
        for _ in range(100):
            if first:
                break
            time.sleep(0.05)
        assert first == [200]
    finally:
        fake.release.set()
        server.shutdown()
        server.server_close()


def test_a_take_is_guarded_before_a_byte_of_it_is_read_and_only_a_few_arrive_at_once(home):
    """Every guard is asked before a take's body is read (up to 41 MB each): a take from elsewhere, without the
    page's token or past a limit is read and dropped a block at a time (nothing of it held) and answered; and only
    W.ARRIVING takes are on their way at once, one from each address, so a crowd of senders can't have the studio
    hold one each."""
    import socket
    import tracemalloc

    from songbird import public as P

    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits(takes=1))
    a_kit(home / "kit")
    studio.enable_web_singing(home / "kit")
    studio.singing.measurer = FakeMeasurer()
    server = S.serve(studio, 18782, client_ip_header="CF-Connecting-IP")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    meta = json.dumps({"guide": GUIDE, "from_s": 6.0, "to_s": 14.0}).encode()
    big = meta + bytes(30 * 2**20)  # made before memory is watched
    try:
        tracemalloc.start()
        try:
            for headers in ({"X-Studio": "not-the-token"}, {"Host": "evil.example"}):
                status, _, data = ask(port, "POST", "/api/sing/take", big, {
                    "Content-Type": "application/x-songbird-take", "X-Studio": studio.token,
                    "X-Sing-Meta": str(len(meta)), **headers})
                assert status == 403, data
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert peak < 4 * 2**20  # read and dropped, never held
        cookie = {"Cookie": f"songbird-visitor-{port}=someone-singing-here"}
        assert take(port, studio, **cookie)[0] == 200
        status, body = take(port, studio, **cookie)  # one at a time for each visitor: said before it's read
        assert status == 429

        def sender(ip):  # a take on its way, slowly: its headers and a little of its body
            s = socket.create_connection(("127.0.0.1", port), timeout=10)
            meta = b'{"guide": "0123456789ab"}'
            s.sendall((f"POST /api/sing/take HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: "
                       f"application/x-songbird-take\r\nX-Studio: {studio.token}\r\nX-Sing-Meta: {len(meta)}\r\n"
                       f"CF-Connecting-IP: {ip}\r\nCookie: songbird-visitor-{port}=visitor-{ip.replace('.', '-')}xx"
                       f"\r\nContent-Length: {10 * 2**20}\r\n\r\n").encode() + meta)
            return s

        slow = [sender("203.0.113.1")]
        for _ in range(100):
            if studio.singing.arriving:
                break
            time.sleep(0.01)
        status, body = take(port, studio, **{"CF-Connecting-IP": "203.0.113.1",
                                             "Cookie": f"songbird-visitor-{port}=another-one-here"})
        assert status == 503 and "on its way" in body["error"]  # one from each address
        slow.append(sender("203.0.113.2"))
        for _ in range(100):
            if len(studio.singing.arriving) == W.ARRIVING:
                break
            time.sleep(0.01)
        status, body = take(port, studio, **{"CF-Connecting-IP": "203.0.113.3",
                                             "Cookie": f"songbird-visitor-{port}=a-third-one-here"})
        assert status == 503 and "on its way" in body["error"]  # a few in all
        for s in slow:
            s.close()
        for _ in range(200):
            if not studio.singing.arriving:
                break
            time.sleep(0.01)
        assert not studio.singing.arriving  # a sender gone lets its place go
    finally:
        server.shutdown()
        server.server_close()


def test_a_json_body_is_read_only_after_its_guards(home):
    """The studio's own POSTs (up to 1 MB of JSON: a MIDI file brought in, edits) are guarded before they're read,
    and a refusal still keeps the connection in step (the body read and dropped)."""
    studio = S.Studio(None, str(LEAD), "none", out=home / "out")
    server = S.serve(studio, 18783)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    seen = []
    real = S.Handler._read_body

    def spy(self, length, *a, **k):
        seen.append(length)
        return real(self, length, *a, **k)

    S.Handler._read_body = spy
    try:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        body = json.dumps({"edits": {}, "pad": "x" * 900_000}).encode()
        for headers, code in (({"X-Studio": "wrong"}, 403), ({"X-Studio": studio.token, "Content-Type": "text/plain"}, 415),
                              ({"X-Studio": studio.token}, 200)):
            c.request("POST", "/api/song", body=body, headers={"Host": f"127.0.0.1:{port}",
                                                                "Content-Type": "application/json", **headers})
            r = c.getresponse()
            r.read()
            assert r.status == code
        assert seen == [len(body)]  # read once: for the request that passed its guards
    finally:
        S.Handler._read_body = real
        server.shutdown()
        server.server_close()


# ------------------------------------------------------------ the way it's sung


def test_the_song_is_sung_the_visitors_way_by_a_name_only_their_page_knows(singing):
    studio, port, _ = singing
    status, kept = post(port, studio, "/api/sing/keep", {"phrasing": PHRASING})
    assert status == 200 and W.NAME.match(kept["name"])
    assert post(port, studio, "/api/sing/keep", {"phrasing": kept["phrasing"]})[1]["name"] == kept["name"]  # stable
    status, view = post(port, studio, "/api/song", {"edits": {"phrasing": kept["name"]}})
    singer = next(c for c in view["cards"] if c["id"] == "singer")
    assert status == 200 and singer["detail"] == "sung your way" and singer["mine"]
    assert kept["name"] not in json.dumps(json.loads(ask(port, "GET", "/api/phrasings")[2]))  # never listed
    assert kept["name"] not in json.dumps(json.loads(ask(port, "GET", "/api/start")[2]))
    mark = studio.version({"phrasing": kept["name"]}).marks["phrasing"]
    assert mark["value"] == "a person's way" and mark["detail"] == "1 sung take(s)"  # what it is, never whose
    view = post(port, studio, "/api/song", {"edits": {"phrasing": "sung-0000000000000000"}})[1]
    assert any(p["path"] == "phrasing" for p in view["problems"])  # a name that isn't kept is refused, said why


def test_a_way_kept_is_rounded_bounded_and_can_be_forgotten(singing):
    studio, port, _ = singing
    wild = {**PHRASING, "source_detail": "<b>Ana</b> 1 take", "phrases": {"v1": [[5.0, 0.1, 99, 0, 999, 0, 0, -1, 0]]}}
    status, kept = post(port, studio, "/api/sing/keep", {"phrasing": wild})
    row = kept["phrasing"]["phrases"]["v1"][0]
    assert status == 200 and row[0] == 0.25 and row[1] == 0.6 and row[2] == 8.0 and row[4] == 150.0
    assert "<" not in kept["phrasing"]["source_detail"]
    assert post(port, studio, "/api/sing/keep", {"phrasing": {"phrases": {"no-such-phrase": [[0] * 9]}}})[0] == 400
    assert post(port, studio, "/api/sing/keep", {"phrasing": "a way"})[0] == 400
    assert post(port, studio, "/api/sing/forget", {"name": kept["name"]})[1] == {"forgotten": True}
    assert post(port, studio, "/api/sing/forget", {"name": "../../etc"})[1] == {"forgotten": False}
    assert kept["name"] not in studio.phrasing_choices()


def test_ways_kept_here_go_after_a_while_unused(home):
    from songbird.genome import load

    store = W.Store(home / "sung", load(LEAD))
    name, _ = store.keep(PHRASING)
    old = time.time() - (W.KEEP_DAYS + 1) * 86400
    os.utime(store.path(name), (old, old))
    W.Phrasings({}, store)[name]  # used: its clock starts again
    store.prune()
    assert store.path(name) is not None
    os.utime(store.path(name), (old, old))
    store.prune()
    assert store.path(name) is None
    assert bool(W.Phrasings({}, store)) and name not in W.Phrasings({}, store)  # empty, still a lookup


# ------------------------------------------------------------ measuring


def test_the_kit_is_held_to_its_age_and_size(tmp_path):
    """What singing makes on a server goes 30 days after its last use, and past the kit's size the longest unused
    go first; its songs stay."""
    kit = KIT.Kit(tmp_path)
    kit.keep_song(LEAD.stem, b"{}")
    now = time.time()
    for k, folder in enumerate(("guides", "audio", "measured/parts", "audio")):
        f = tmp_path / folder / f"f{k}.bin"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x" * 100)
        os.utime(f, (now - k * 3600, now - k * 3600))  # f0 the newest
    old = tmp_path / "guides" / "old.json"
    old.write_bytes(b"x")
    os.utime(old, (now - 31 * 86400, now - 31 * 86400))
    assert kit.prune(most=250) == 3  # the month-old one, then the two longest unused
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["f0.bin", "f1.bin", f"{LEAD.stem}.json"]


def test_a_long_take_is_measured_in_pieces_cut_in_its_rests():
    notes = [SimpleNamespace(start=s, dur=0.5) for s in list(np.arange(10, 32, 1.0)) + list(np.arange(38, 60, 1.0))
             + list(np.arange(66, 120, 0.8))]
    assert worker.pieces(notes, 6.0, 37.0) == [(6.0, 37.0)]  # a section: whole
    cut = worker.pieces(notes, 0.0, 130.0)
    assert cut[0][0] == 0.0 and cut[-1][1] == 130.0 and all(b - a <= worker.MAX_PIECE for a, b in cut)
    assert all(a2 == b1 for (_, b1), (a2, _) in zip(cut, cut[1:]))
    for t in [b for _, b in cut[:-1]]:  # never through a note
        assert not any(n.start < t < n.start + n.dur for n in notes)
    assert 34 < cut[0][1] < 36  # the first rest of the song, between its first two stretches


def test_the_template_singer_sings_a_piece_in_whole_words():
    """A long take is cut at its longest rest, which may fall between two syllables of a word held apart; the
    template singer sings that piece's words whole (the formant singer refuses half a word)."""
    syllables = [("They", 1), ("half", 4), ("in", 4), ("vent", 4), ("ed", 4), ("fire", 1)]
    notes = [SimpleNamespace(start=float(k), dur=0.5, word_len=n, syllable=s) for k, (s, n) in enumerate(syllables)]
    g = SimpleNamespace(notes=notes)
    assert [n.syllable for n in worker.part_notes(g, 2.5, 4.5)] == ["half", "in", "vent", "ed"]
    assert [n.syllable for n in worker.part_notes(g, 0.0, 2.5)] == ["They", "half", "in", "vent", "ed"]
    assert [n.syllable for n in worker.part_notes(g, 5.0, 9.0)] == ["fire"] and worker.part_notes(g, 9.0, 10.0) == []


def test_a_planted_way_is_measured_as_the_tools_measure_it_and_the_audio_goes(tmp_path):
    """The template singer sings the first refrain with every second note 60 ms late; the web studio's measuring
    process finds those notes later than the rest, with exactly the numbers tools/phrasing.py measure_window gives
    the same take (without MFA) against the template singer singing the refrain's notes, made ahead in the
    measuring process as a page asks for it while its singer rehearses; that template is the whole guide's over
    the refrain, to a fraction of a cent; its melody is made too; and nothing of the take is left where it was
    read."""
    kit, out = tmp_path / "kit", tmp_path / "out"
    made = subprocess.run([sys.executable, str(ROOT / "tests" / "_web_singing_take.py"), str(kit), str(out)],
                          capture_output=True, text=True, timeout=600)
    assert made.returncode == 0, made.stderr[-2000:]
    where = json.loads((out / "take.json").read_text())
    close = json.loads((out / "template.json").read_text())
    assert close["voiced_agree"] > 0.97 and close["median_cents"] < 2.0 and close["band_db"] < 1.5
    for f in (kit / "measured" / "parts").glob("*.npz"):  # made again, by the measuring process
        f.unlink()
    measurer = W.Measurer(KIT.Kit(kit), idle=60)
    before = set(worker.scratch_dir().glob(f"{worker.SCRATCH_PREFIX}*"))
    stretch = {"song": where["song"], "guide": where["guide"], "from_s": where["from_s"], "to_s": where["to_s"]}
    try:
        ahead = measurer.call("template", {**stretch, "key": 0})
        melody = measurer.call("melody", {**stretch, "to_s": where["to_s"] + 0.6})
        result = measurer.call("take", {**stretch, "earlier": [], "audio": (out / "take.wav").read_bytes()})
        hello = measurer.call("hello", {})
    finally:
        measurer.stop()
    assert set(worker.scratch_dir().glob(f"{worker.SCRATCH_PREFIX}*")) == before
    assert hello["extractor"] and len(ahead["templates"]) == 1 and result["templates"] == ahead["templates"]
    seconds = sf.info(io.BytesIO(melody["wav"])).duration
    assert melody["rate"] == 22050 and abs(seconds - (where["to_s"] + 0.6 - where["from_s"])) < 0.01
    m, reference = result["measurement"], json.loads((out / "reference.json").read_text())
    assert m["notes"] == reference["notes"] and m["lag"] == reference["lag"] and m["key"] == reference["key"]
    early = m["fields"].index("early")
    planted = set(where["planted"])
    late = [n["gesture"][early] for k, n in enumerate(m["notes"]) if k in planted and n["gesture"] and n["gesture"][early] is not None]
    rest = [n["gesture"][early] for k, n in enumerate(m["notes"]) if k not in planted and n["gesture"] and n["gesture"][early] is not None]
    assert len(late) >= 15 and len(rest) >= 15
    want = where["late"] * where["tempo"] / 60.0  # beats
    assert np.median(late) < np.median(rest) - 0.5 * want  # the planted notes are heard late
    assert result["phrasing"]["phrases"] and result["portrait"].startswith("Take 1")
    assert result["peak_mb"] < 1500 and result["seconds"] < 60
