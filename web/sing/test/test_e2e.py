"""End to end under `wrangler dev`: singing online from the link to the purge, with tools/invite.py.

    uv run pytest web/sing/test -q          # not in the main run: it needs node_modules (cd web/sing && npm install)

Builds a small site of its own in a temporary folder (song.json v2 with two sets, their lyrics
with sections and windows, stand-in MP3s, the pages from web/sing/page), then runs the worker on
it three times over the same throwaway local KV and R2, with a random admin token: while singing
is open, after it has closed, and after DELETE_BY (the dates are the only difference). Singers
join, sing whole takes and one section, send words, use their own page, delete and withdraw; the
artist's side is tools/invite.py (sync, mail, purge) against the same worker, with recordings/ in
a temporary folder and a stand-in for tools/versions.py. Nothing touches the real recordings/.
"""

import base64
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

WEB = Path(__file__).parent.parent
ROOT = WEB.parent.parent
WRANGLER = WEB / "node_modules" / ".bin" / "wrangler"
sys.path.insert(0, str(ROOT / "tools"))
import invite as I  # noqa: E402  (tools/invite.py)
import sing_site as W  # noqa: E402  (tools/sing_site.py, for the worker's small copy of song.json)
import takes as K  # noqa: E402  (tools/takes.py)

pytestmark = pytest.mark.skipif(not WRANGLER.exists(), reason="needs web/sing/node_modules (npm install)")

OPEN = "2099-01-01T00:00:00-08:00"
PAST = "2001-01-01T00:00:00-08:00"
CONSENT, WORDS = "c0c0c0c0c0c0", "d1d1d1d1d1d1"
RATE = 8000  # small takes: the worker takes any of the page's rates
SECTIONS = [
    {"index": 0, "name": "intro", "start": 0.0, "end": 5.0, "sung": False},
    {"index": 1, "name": "verse", "start": 5.0, "end": 20.0, "sung": True, "nth": 1,
     "label": "They saved it as numbers and sent it by wire,", "window": [2.5, 21.0]},
    {"index": 2, "name": "turn", "start": 20.0, "end": 25.0, "sung": False},
    {"index": 3, "name": "refrain", "start": 25.0, "end": 40.0, "sung": True, "nth": 1, "label": "Now it's by you",
     "window": [22.5, 41.0]},
    {"index": 4, "name": "tag", "start": 40.0, "end": 60.0, "sung": True, "nth": 1, "label": "By you", "window": [37.5, 60.0]},
]
GUIDES = {"a.k0.t100": "aaaaaaaaaaaa", "b.k-2.t90": "bbbbbbbbbbbb"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_site(public: Path) -> dict:
    """The site as tools/sing_site.py builds it for song.json v2, small: two sets, a guide each."""
    (public / "song").mkdir(parents=True)
    guides = {}
    for spec, digest in GUIDES.items():
        s, k, t = spec.split(".")
        lyrics = {"title": "Now It's By You", "tempo": 96 * int(t[1:]) / 100, "duration": 60.0, "lines": [], "beats": [],
                  "guide": digest, "spec": {"id": spec, "set": s, "key": int(k[1:]), "tempo": int(t[1:])}, "sections": SECTIONS}
        (public / "song" / f"{spec}.json").write_text(json.dumps(lyrics))
        mixes = {}
        for mix in ("melody", "full"):
            mp3 = secrets.token_bytes(3000)  # stand-ins: the worker never decodes them
            (public / "song" / f"{spec}.{mix}.mp3").write_bytes(mp3)
            mixes[mix] = {"file": f"{spec}.{mix}.mp3", "bytes": len(mp3), "rate": 44100, "samples": 60 * 44100, "seconds": 60.0,
                          "frame": 0.001, "env": [0.0] * 2500}
        guides[spec] = {"guide": digest, "lyrics": f"{spec}.json", "duration": 60.0, "mixes": mixes}
    song = {"v": 2, "title": "Now It's By You", "song": "h-now-its-by-you", "consent": CONSENT, "words_release": WORDS,
            "sets": [{"id": "a", "name": "Set A", "about": ""}, {"id": "b", "name": "Set B", "about": ""}],
            "keys": [-2, 0], "tempos": [100, 90], "mixes": ["melody", "full"],
            "default": {"set": "a", "key": 0, "tempo": 100, "mix": "melody"}, "guides": guides, "max_seconds": 127,
            "built": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (public / "song" / "song.json").write_text(json.dumps(song))
    (public / "song" / "worker.json").write_text(json.dumps(W.worker_index(song)))
    (public / "index.html").write_text(f'<!doctype html><title>sing</title><div data-digest="{CONSENT}"></div>')
    for name in ("yours.html", "yours.css", "yours.js", "sing.css"):
        shutil.copyfile(WEB / "page" / name, public / name)
    (public / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (public / "_headers").write_text(W.HEADERS)
    (public / ".assetsignore").write_text(".assetsignore\n")
    return song


class Worker:
    """wrangler dev on the test's site, started again for each part of the story over the same state."""

    def __init__(self, tmp: Path, public: Path):
        self.tmp, self.public, self.admin, self.proc, self.runs = tmp, public, secrets.token_urlsafe(32), None, 0

    def start(self, closes: str, delete_by: str) -> str:
        self.stop()
        self.runs += 1
        config = (WEB / "wrangler.toml").read_text()
        config = config.replace('main = "src/worker.js"', f'main = "{WEB / "src" / "worker.js"}"')
        config = config.replace('directory = "./public"', f'directory = "{self.public}"')
        config = config.replace('CLOSES_AT = "2026-09-27T22:00:00-07:00"', f'CLOSES_AT = "{closes}"')
        config = config.replace('DELETE_BY = "2026-09-30T20:00:00-07:00"', f'DELETE_BY = "{delete_by}"')
        config = config.replace("simple = { limit = 120, period = 60 }", "simple = { limit = 100000, period = 60 }")  # every request here is from one address
        assert f'CLOSES_AT = "{closes}"' in config and f'DELETE_BY = "{delete_by}"' in config
        path = self.tmp / f"wrangler-{self.runs}.toml"
        path.write_text(config)
        port = free_port()
        self.proc = subprocess.Popen(
            [str(WRANGLER), "dev", "-c", str(path), "--port", str(port), "--ip", "127.0.0.1", "--persist-to", str(self.tmp / "state"),
             "--var", f"ADMIN_TOKEN:{self.admin}", "--test-scheduled", "--show-interactive-dev-session=false"],
            cwd=WEB, env={**os.environ, "WRANGLER_SEND_METRICS": "false"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                with urllib.request.urlopen(self.base + "/", timeout=2):
                    return self.base
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.5)
        pytest.fail("wrangler dev didn't start")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=30)
            self.proc = None


@pytest.fixture(scope="module")
def online(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sing")
    build_site(tmp / "public")
    worker = Worker(tmp, tmp / "public")
    state = {"worker": worker, "tmp": tmp}
    try:
        yield state
    finally:
        worker.stop()


@pytest.fixture
def here(online, monkeypatch):
    """recordings/ and renders/ in the test's own folder, the same for every part of the story."""
    root = online["tmp"] / "repo"
    monkeypatch.setattr(K, "ROOT", root)
    monkeypatch.setattr(K, "RECORDINGS", root / "recordings")
    monkeypatch.setattr(K, "GUIDES", root / "recordings" / "guides")
    K.GUIDES.mkdir(parents=True, exist_ok=True)
    for digest in GUIDES.values():  # pinned when the site was built, as tools/sing_site.py does
        (K.GUIDES / f"h-now-its-by-you.{digest}.score.json").write_text("{}")
    (K.GUIDES / f"release.{CONSENT}.html").write_text("<p>the release</p>")
    return root


def request(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def api(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    code, _, out = request(base + path, method, data, {"Content-Type": "application/json", **(headers or {})})
    return code, json.loads(out or b"{}")


def join(base, invite, email, name="", notify=False):
    consent = {"agreed": True, "at": datetime.now(timezone.utc).isoformat(), "text": CONSENT}
    return api(base, "POST", f"/api/join/{invite}", {"email": email, "name": name, "credit": bool(name), "notify": notify,
                                                     "consent": consent}, {"Sec-Fetch-Site": "same-origin"})


def wav(seconds: float) -> bytes:
    """A take as the page writes it: 16-bit mono PCM."""
    t = np.arange(int(seconds * RATE)) / RATE
    pcm = np.round(np.sin(2 * np.pi * 220 * t) * 0.3 * 32767).astype("<i2").tobytes()
    head = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
    head += (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + RATE.to_bytes(4, "little")
    head += (RATE * 2).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    return head + b"data" + len(pcm).to_bytes(4, "little") + pcm


def send(base, sid, seconds=40.0, **extra):
    """A take and its sidecar, as the page sends them; returns (status, reply, the WAV)."""
    body = wav(seconds)
    info = {"song": "h-now-its-by-you", "spec": "a.k0.t100", "guide": GUIDES["a.k0.t100"], "mix": "melody", "rate": RATE,
            "from_s": 0, "to_s": 60, "shift_ms": 12, "auto_ms": 10, "device_ms": 40, "out_ms": 25, "in_ms": 5,
            "sha256": hashlib.sha256(body).hexdigest(), **extra}
    header = base64.urlsafe_b64encode(json.dumps(info).encode()).decode().rstrip("=")
    code, _, out = request(f"{base}/api/take/{sid}", "PUT", body, {"Content-Type": "audio/wav", "X-Take-Info": header})
    return code, json.loads(out or b"{}"), body


def words(base, sid, text):
    release = {"agreed": True, "at": datetime.now(timezone.utc).isoformat(), "text": WORDS}
    return api(base, "POST", f"/api/words/{sid}", {"text": text, "release": release})


def mine(base, sid) -> dict:
    code, data = api(base, "GET", f"/api/yours/{sid}")
    assert code == 200, data
    return data


def local_takes(sid=None):
    out = []
    for side in sorted(K.RECORDINGS.glob("*/*.json")):
        if side.parent.name in ("guides", "words"):
            continue
        info = json.loads(side.read_text())
        if info.get("source") == "online" and (sid is None or info.get("sid") == sid):
            out.append((side, info))
    return out


def fake_versions(made: list):
    """A stand-in for tools/versions.py's make(): version.mp3 and vocals.wav for one singer's takes of one spec."""
    module = types.ModuleType("versions")

    def make(genome_path, takes, spec, out_dir, stems=None, strip=None, title=""):
        made.append((Path(genome_path).stem, sorted(t.path.name for t in takes), spec))
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "version.mp3").write_bytes(b"ID3 their version")
        (out_dir / "vocals.wav").write_bytes(wav(3.0))
        return types.SimpleNamespace(version=out_dir / "version.mp3", vocals=out_dir / "vocals.wav", sections=[])

    module.make = make
    return module


def test_while_singing_is_open(online, here):
    base = online["worker"].start(OPEN, OPEN)
    site = I.Site(base, online["worker"].admin)
    story = online["story"] = {}

    # a personal link, used from a laptop and then a phone; a group link for three
    personal = I.new(site, 1, "Ana", 1, 5, people=1)[0]["token"]
    group = I.new(site, 1, "choir", 1, 5, people=3)[0]["token"]
    code, headers, page = request(f"{base}/i/{personal}")
    assert code == 200 and "script-src 'self'" in headers["Content-Security-Policy"]
    state = api(base, "GET", f"/api/invite/{personal}")[1]
    # a personal link: one person, on up to three devices (the page checks joined against people)
    assert (state["state"], state["people"], state["personal"], state["joined"], state["full"]) == ("open", 3, True, 0, False)
    code, ana = join(base, personal, "ana@example.org", "Ana María")
    assert code == 200 and ana["page"] == f"/y/{ana['singer']}"
    code, phone = join(base, personal, "Ana@Example.org")  # the same person on her phone: another page
    assert code == 200 and phone["singer"] != ana["singer"]
    bo, cy, di = (join(base, group, f"{who}@example.org", who.title(), notify=who == "bo")[1]["singer"] for who in ("bo", "cy", "di"))
    code, full = join(base, group, "ed@example.org")
    assert (code, full["error"]) == (403, "full")
    assert {ana["set"], phone["set"]} == {"a", "b"}  # nothing sung yet: sets in turn
    a, p = ana["singer"], phone["singer"]
    story.update(ana=a, phone=p, bo=bo, cy=cy, di=di, personal=personal, group=group)

    # singing: the whole song, one section at a time; the checks refuse what doesn't fit its guide
    code, reply, whole = send(base, a, 58.0)
    assert (code, reply) == (200, {"ok": True, "take": 1, "limit": 5})
    code, reply, verse = send(base, a, 18.0, section=1, from_s=2.5, to_s=21.0, mix="full")
    assert code == 200 and reply["take"] == 2
    assert send(base, p, 12.5, section=3, from_s=22.5, to_s=35.0)[0] == 200  # the refrain from her phone, stopped early
    code, reply, _ = send(base, a, 18.0, section=1, from_s=12.0, to_s=21.0)
    assert code == 400 and "doesn't match" in reply["message"]
    code, reply, _ = send(base, a, 40.0, spec="b.k-2.t90")  # a's score, called b's guide
    assert code == 400 and "reload" in reply["message"]
    assert send(base, a, 40.0, section=2, from_s=20.0, to_s=25.0)[0] == 400  # the turn: nobody sings there
    assert send(base, bo, 30.0, spec="b.k-2.t90", guide=GUIDES["b.k-2.t90"])[0] == 200
    assert send(base, bo, 20.0, section=4, from_s=37.5, to_s=60.0, spec="b.k-2.t90", guide=GUIDES["b.k-2.t90"])[0] == 200
    assert send(base, cy, 30.0, to_s=30.0)[0] == 200  # the whole song, stopped halfway
    assert send(base, di, 30.0)[0] == 200
    assert words(base, a, "A verse about the river,\nand the wire.")[0] == 200
    assert words(base, di, "Di's line")[0] == 200
    assert words(base, a, "x" * 4001)[0] == 400
    assert api(base, "POST", f"/api/done/{a}", {}, {"Sec-Fetch-Site": "cross-site"})[0] == 403

    # her own page: what she sent, played and downloaded (downloading deletes nothing)
    code, headers, html = request(f"{base}/y/{a}")
    assert code == 200 and headers["X-Robots-Tag"] == "noindex" and headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in headers["Content-Security-Policy"] and b"/yours.js" in html
    assert request(f"{base}/yours.js")[0] == 200
    page = mine(base, a)
    assert (page["name"], page["state"], page["can_withdraw"], page["sing_more"]) == ("Ana María", "open", True, f"/i/{personal}#s={a}")
    parts = {t["section"]: t for t in page["takes"]}
    assert set(parts) == {None, 1} and parts[1]["name"] == "Verse 1" and parts[1]["label"].startswith("They saved it")
    assert [w["text"] for w in page["words"]] == ["A verse about the river,\nand the wire."]
    for _ in range(2):
        code, headers, got = request(f"{base}/api/yours/{a}/take/{parts[1]['id']}?download=1")
        assert code == 200 and got == verse and headers["Content-Disposition"].startswith("attachment")
    code, headers, got = request(f"{base}/api/yours/{a}/take/{parts[None]['id']}", headers={"Range": "bytes=0-1"})
    assert code == 206 and got == whole[:2] and headers["Content-Range"] == f"bytes 0-1/{len(whole)}"
    assert len(mine(base, a)["takes"]) == 2
    assert api(base, "POST", f"/api/done/{a}")[1]["state"] == "done"  # a note: it closes nothing
    assert api(base, "GET", f"/api/invite/{personal}")[1]["state"] == "open"


def test_the_artist_syncs_and_mails_while_singers_change_their_minds(online, here, monkeypatch, capsys):
    story = online["story"]
    base, site = online["worker"].base, I.Site(online["worker"].base, online["worker"].admin)
    made = []
    monkeypatch.setitem(sys.modules, "versions", fake_versions(made))
    a, p, bo, cy, di = (story[k] for k in ("ana", "phone", "bo", "cy", "di"))

    # sync: every take into recordings/ (Ana's laptop and phone in one folder), words, versions made and uploaded
    I.sync(site)
    kept = {sid: local_takes(sid) for sid in (a, p, bo, cy, di)}
    assert [len(kept[s]) for s in (a, p, bo, cy, di)] == [2, 1, 2, 1, 1]
    folders = {sid: {side.parent.name for side, _ in kept[sid]} for sid in kept}
    assert folders[a] == folders[p] and len(folders[a]) == 1  # one person, two pages, one folder
    assert len({next(iter(folders[s])) for s in (a, bo, cy, di)}) == 4
    side, info = next((s, i) for s, i in kept[a] if i.get("section") == 1)
    assert (info["spec"], info["from_s"], info["to_s"], info["section"], info["sid"], info["source"]) == ("a.k0.t100", 2.5, 21.0, 1, a, "online")
    assert info["guide"] == GUIDES["a.k0.t100"] and info["credit"] is True and info["consent"]["text"] == CONSENT
    assert side.with_suffix(".wav").read_bytes()[:4] == b"RIFF"
    ana_words = json.loads((K.RECORDINGS / "words" / f"{a}.json").read_text())
    assert [w["text"] for w in ana_words["words"]] == ["A verse about the river,\nand the wire."]
    assert made, "versions were made"
    for sid in (a, p, bo):
        names = {f["name"] for f in mine(base, sid)["files"]}
        assert any(n.endswith(".version.mp3") for n in names) and any(n.endswith(".vocals.wav") for n in names), (sid, names)
    before = len(made)
    capsys.readouterr()
    I.sync(site)  # nothing new: nothing fetched, nothing made
    assert len(made) == before and sum(len(local_takes(s)) for s in kept) == 7

    # mail: one message per address, ready to paste; marked sent, it isn't listed again
    letters = I.mail(site)
    out = capsys.readouterr().out
    assert len(letters) == 4  # Ana's two pages share one address, so one message
    ana_mail = next(m for m in letters if m["to"].lower() == "ana@example.org")
    assert f"{base}/y/{a}" in ana_mail["body"] and f"{base}/y/{p}" in ana_mail["body"] and ana_mail["body"] in out
    assert "or withdraw" in ana_mail["body"] and ana_mail["body"].endswith("Milo")
    assert "deleted by 1 January" in ana_mail["body"]  # DELETE_BY here is 1 January 2099; on the site, 30 September
    assert "released to the public" in next(m for m in letters if m["to"] == "bo@example.org")["body"]  # Bo asked
    I.mark_sent(site)
    capsys.readouterr()
    assert I.mail(site) == []

    # Bo deletes one take, Cy all of hers, Di withdraws; the next sync follows them here
    bo_take = next(t["id"] for t in mine(base, bo)["takes"] if t["section"] is None)
    assert api(base, "DELETE", f"/api/yours/{bo}/take/{bo_take}")[1] == {"deleted": bo_take}
    assert api(base, "POST", f"/api/yours/{cy}/delete")[1]["deleted"] >= 1
    assert api(base, "POST", f"/api/yours/{di}/withdraw")[1] == {"state": "withdrawn"}
    assert mine(base, di)["state"] == "withdrawn" and send(base, di, 10.0)[0] == 410
    gone = site.call("GET", "/api/admin/gone")["gone"]
    assert [(g["singer"], g["what"], bool(g["take"])) for g in gone] == [(bo, "deleted", True), (cy, "deleted", False), (di, "withdrawn", False)]
    di_folder = next(iter(folders[di]))
    I.sync(site)
    bo_takes = {i["remote"].rsplit("/", 1)[1]: (s, i) for s, i in local_takes(bo)}
    s, i = bo_takes[bo_take]
    assert not s.with_suffix(".wav").exists() and i.get("deleted")  # the audio's gone; what was measured stays
    assert all(s.with_suffix(".wav").exists() for k, (s, _) in bo_takes.items() if k != bo_take)
    assert all(not s.with_suffix(".wav").exists() for s, _ in local_takes(cy))
    assert local_takes(di) == [] and not (K.RECORDINGS / di_folder).exists()
    assert not (K.RECORDINGS / "words" / f"{di}.json").exists()
    capsys.readouterr()
    I.sync(site)  # applied once: again, nothing happens
    assert "withdr" not in capsys.readouterr().out.lower()
def test_after_singing_closes(online, here):
    story = online["story"]
    base = online["worker"].start(PAST, OPEN)
    a, bo = story["ana"], story["bo"]
    assert request(f"{base}/i/{story['group']}")[0] == 410
    assert join(base, story["group"], "late@example.org")[0] == 410
    code, reply, _ = send(base, a, 20.0)
    assert (code, reply["error"]) == (410, "closed")
    assert words(base, a, "late")[0] == 410
    page = mine(base, a)
    assert (page["state"], page["sing_more"], page["can_withdraw"]) == ("closed", None, False)
    code, reply = api(base, "POST", f"/api/yours/{a}/withdraw")
    assert code == 410 and "part of it now" in reply["message"]
    # deleting recordings still works, until DELETE_BY
    take = page["takes"][0]["id"]
    assert api(base, "DELETE", f"/api/yours/{a}/take/{take}")[1] == {"deleted": take}
    assert len(mine(base, a)["takes"]) == 1
    site = I.Site(base, online["worker"].admin)
    assert site.call("GET", "/api/admin/status")["closed"] is True
    assert mine(base, bo)["state"] == "closed"
    I.sync(site)  # and here: its audio goes, its sidecar stays
    side, info = next((s, i) for s, i in local_takes(a) if i["remote"].endswith(take))
    assert not side.with_suffix(".wav").exists() and info.get("deleted")
    assert [s.with_suffix(".wav").exists() for s, i in local_takes(a) if not i["remote"].endswith(take)] == [True]


def test_after_delete_by(online, here, capsys):
    story = online["story"]
    base = online["worker"].start(PAST, PAST)
    site = I.Site(base, online["worker"].admin)
    before = site.call("GET", "/api/admin/singers?emails=1")["singers"]
    assert any(s["email"] for s in before)
    code, _, _ = request(f"{base}/__scheduled?cron=0+*+*+*+*")  # the hourly cron, now
    assert code == 200
    for _ in range(40):  # it runs after answering
        if not site.call("GET", "/api/admin/takes")["takes"]:
            break
        time.sleep(0.25)
    assert site.call("GET", "/api/admin/takes")["takes"] == []
    after = {s["sid"]: s for s in site.call("GET", "/api/admin/singers?emails=1")["singers"]}
    assert after[story["bo"]]["email"] == "bo@example.org"  # Bo asked to hear when the song is released
    assert [sid for sid, s in after.items() if s["email"]] == [story["bo"]]
    page = mine(base, story["ana"])
    assert (page["state"], page["takes"], page["files"], len(page["words"])) == ("deleted", [], [], 1)
    assert request(f"{base}/y/{story['ana']}")[0] == 200  # her page still says what happened
    assert site.call("POST", "/api/admin/purge") == {"takes": 0, "files": 0, "emails": 0, "more": False}

    # and here: every online take's audio and every version goes; what was measured stays
    assert any(s.with_suffix(".wav").exists() for s, _ in local_takes())
    I.purge(site)
    assert local_takes() and not any(s.with_suffix(".wav").exists() for s, _ in local_takes())
    assert not [f for f in (K.ROOT / "renders" / "versions").rglob("*") if f.is_file()]
