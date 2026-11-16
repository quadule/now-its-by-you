"""tools/invite.py against a fake of the site's admin API (web/sing/src/worker.js)."""

import datetime as dt
import hashlib
import io
import json
import os
import secrets
import subprocess
import sys
import threading
import types
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import invite as I  # noqa: E402  (tools/invite.py)
import takes as K  # noqa: E402  (tools/takes.py)

ADMIN = "a" * 43
GUIDE = "86341ecd9a2a"
SONG = "h-now-its-by-you"
CLOSES, DELETE_BY = "2026-09-27T22:00:00-07:00", "2026-09-30T20:00:00-07:00"  # the Worker's CLOSES_AT, DELETE_BY
OPEN, CLOSED, DELETING = "2026-09-26T23:30:00.000Z", "2026-09-28T06:00:00.000Z", "2026-10-01T04:00:00.000Z"
UPLOADED = "2026-10-01T10:00:00.000Z"  # when a take reached the bucket, unless a test says otherwise


def iso(stamp: str) -> str:
    """20260926T231501Z -> 2026-09-26T23:15:01.000Z"""
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}.000Z"


def moment(iso_time: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso_time)


def wav_bytes() -> bytes:
    wav = io.BytesIO()
    sf.write(wav, np.zeros(48000 * 4), 48000, format="WAV", subtype="PCM_16")
    return wav.getvalue()


class FakeSite:
    """The admin API's shape, in memory: invitations, the singers who joined, and the objects of a bucket
    (takes, words, what singers deleted or withdrew, the files on their pages)."""

    def __init__(self):
        self.invites, self.objects, self.deleted, self.times = {}, {}, [], {}
        self.singers, self.words, self.gone, self.files = {}, {}, [], {}
        self.requests, self.purged = [], []
        self.now = OPEN  # the site's clock
        self.page = 50  # singers per page of their listing
        self.broken = False  # every request answers 503

    def status(self) -> dict:
        now = moment(self.now)
        return {"closes": CLOSES, "delete_by": DELETE_BY, "now": self.now, "closed": now >= moment(CLOSES),
                "deleting": now >= moment(DELETE_BY)}

    def add_take(self, token: str, stamp: str, name: str = "", mix: str = "melody", corrupt: bool = False,
                 uploaded: str = UPLOADED) -> str:
        """A first-version take: kept under its invitation, no singer id."""
        data = wav_bytes()
        key = f"takes/{token}/{stamp}-abcdef"
        side = {"song": SONG, "guide": GUIDE, "mix": mix, "rate": 48000, "seconds": 4.0, "name": name,
                "credit": bool(name), "consent": {"agreed": True, "at": "2026-10-01T10:00:00.000Z", "text": "896e20c8603e"},
                "shift_ms": 12, "auto_ms": 10, "device_ms": 40, "decode_ms": 0, "out_ms": 29, "in_ms": 10,
                "received": iso(stamp), "bytes": len(data), "sha256": hashlib.sha256(data + (b"x" if corrupt else b"")).hexdigest(),
                "take": 1}
        self.objects[f"{key}.wav"] = data
        self.objects[f"{key}.json"] = json.dumps(side).encode()
        self.times[f"{key}.wav"] = self.times[f"{key}.json"] = uploaded
        return key

    def add_singer(self, token: str, name: str = "", email: str | None = None, credit: bool = True, notify: bool = False,
                   person: str | None = None) -> str:
        """Someone joining with an invitation (person: the sid of the first to join with it and the same email)."""
        sid = secrets.token_urlsafe(18)
        self.singers[sid] = {"sid": sid, "person": person or sid, "invite": token, "created": "2026-09-26T23:10:00.000Z",
                             "name": name, "credit": credit, "notify": notify, "set": "a", "state": "open", "done": None,
                             "email": email, "sent": {"link": None, "ready": None}}
        return sid

    def add_sung(self, sid: str, stamp: str, spec: str = "a.k0.t100", section: int | None = None, label: str | None = None,
                 from_s: float = 0.0, to_s: float = 150.2, rand: str = "abcdef", corrupt: bool = False,
                 uploaded: str | None = None) -> str:
        """A take from a singer's page, kept under their sid."""
        s, data = self.singers[sid], wav_bytes()
        key = f"takes/{sid}/{stamp}-{rand}"
        side = {"song": SONG, "spec": spec, "guide": GUIDE, "mix": "melody", "rate": 48000, "seconds": 4.0,
                "from_s": from_s, "to_s": to_s, "section": section, "label": label, "sid": sid, "person": s["person"],
                "invite": s["invite"], "name": s["name"], "credit": s["credit"],
                "consent": {"agreed": True, "at": iso(stamp), "text": "896e20c8603e"},
                "sha256": hashlib.sha256(data + (b"x" if corrupt else b"")).hexdigest(), "shift_ms": 12, "auto_ms": 10,
                "device_ms": 40, "decode_ms": 0, "out_ms": 29, "in_ms": 10, "received": iso(stamp), "bytes": len(data),
                "take": 1}
        self.objects[f"{key}.wav"] = data
        self.objects[f"{key}.json"] = json.dumps(side).encode()
        self.times[f"{key}.wav"] = self.times[f"{key}.json"] = uploaded or iso(stamp)
        return key

    def add_words(self, sid: str, text: str, at: str, rand: str = "wxyz23") -> str:
        s = self.singers[sid]
        key = f"words/{sid}/{at[:19].replace('-', '').replace(':', '')}Z-{rand}.json"
        self.words[key] = {"sid": sid, "person": s["person"], "at": at, "text": text,
                           "release": {"agreed": True, "at": at, "text": "5e1ea5ed1ge5"}, "name": s["name"],
                           "credit": s["credit"]}
        return key

    def event(self, sid: str, what: str, take: str | None, at: str) -> None:
        self.gone.append({"key": f"gone/{sid}/{at[:19].replace('-', '').replace(':', '')}Z-{len(self.gone):06d}.json",
                          "singer": sid, "what": what, "take": take, "at": at})

    def delete_take(self, sid: str, take: str, at: str) -> None:
        """What a singer's page does when they delete a take: it goes, and so do the files on their page."""
        for ext in ("wav", "json"):
            self.objects.pop(f"{take}.{ext}", None)
        self.files.pop(sid, None)
        self.event(sid, "deleted", take, at)

    def delete_all(self, sid: str, at: str) -> None:
        for key in [k for k in self.objects if k.startswith(f"takes/{sid}/") and moment(self.times[k]) < moment(at)]:
            del self.objects[key]
        self.files.pop(sid, None)
        self.event(sid, "deleted", None, at)

    def withdraw(self, sid: str, at: str) -> None:
        for key in [k for k in self.objects if k.startswith(f"takes/{sid}/")]:
            del self.objects[key]
        for key in [k for k in self.words if k.startswith(f"words/{sid}/")]:
            del self.words[key]
        self.files.pop(sid, None)
        self.singers[sid].update(state="withdrawn", email=None)
        self.event(sid, "withdrawn", None, at)

    def handler(site):  # noqa: N805  (the fake site, seen from its request handler)
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, code, data, kind="application/json"):
                body = data if isinstance(data, bytes) else json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def route(self, method):
                if self.headers.get("Authorization") != f"Bearer {ADMIN}":
                    return self.reply(401, {"error": "auth", "message": "Not allowed."})
                url = urlsplit(self.path)
                path = url.path.removeprefix("/api/admin/")
                query = parse_qs(url.query)
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                site.requests.append((method, path, url.query))
                if site.broken:
                    return self.reply(503, {"error": "busy", "message": "Try again in a moment."})
                base = f"http://{self.headers['Host']}"
                if method == "GET" and path == "status":
                    return self.reply(200, site.status())
                if method == "POST" and path == "invites":
                    asked = json.loads(body)
                    made = []
                    for _ in range(asked["count"]):
                        token = secrets.token_urlsafe(18)
                        site.invites[token] = {"v": 2, "created": "2026-10-01T09:00:00.000Z",
                                               "expires": "2026-10-08T09:00:00.000Z", "limit": asked["limit"],
                                               "note": asked["note"], "state": "open", "people": asked.get("people", 1)}
                        made.append({"token": token, "url": f"{base}/i/{token}", **site.invites[token]})
                    return self.reply(200, {"invites": made})
                if method == "GET" and path == "invites":
                    out = []
                    for token, inv in site.invites.items():
                        joined = [sid for sid, s in site.singers.items() if s["invite"] == token]
                        waiting = sum(k.endswith(".json") and k.split("/")[1] in {token, *joined} for k in site.objects)
                        out.append({"token": token, "url": f"{base}/i/{token}", **inv, "joined": len(joined),
                                    "takes": waiting, "sent": waiting})
                    return self.reply(200, {"invites": out})
                if method == "POST" and path.startswith("revoke/"):
                    site.invites[path[7:]]["state"] = "revoked"
                    return self.reply(200, {"state": "revoked"})
                if method == "GET" and path == "singers":
                    start = int(query.get("cursor", ["0"])[0])
                    everyone = list(site.singers.values())
                    out = []
                    for s in everyone[start:start + site.page]:
                        row = {k: v for k, v in s.items() if k != "email"}
                        row.update(page=f"{base}/y/{s['sid']}",
                                   takes=sum(k.startswith(f"takes/{s['sid']}/") and k.endswith(".json") for k in site.objects),
                                   words=sum(k.startswith(f"words/{s['sid']}/") for k in site.words),
                                   files=[{k: f[k] for k in ("name", "kind", "about", "bytes", "made")}
                                          for f in site.files.get(s["sid"], {}).values()])
                        if query.get("emails") == ["1"]:
                            row["email"] = s["email"]
                        out.append(row)
                    more = start + site.page < len(everyone)
                    return self.reply(200, {"singers": out, "dates": {"closes": CLOSES, "delete_by": DELETE_BY},
                                            "cursor": str(start + site.page) if more else None})
                if method == "GET" and path == "takes":
                    only = query.get("invite", query.get("singer", [None]))[0]
                    takes = {}
                    for key, data in sorted(site.objects.items()):
                        owner = key.split("/")[1]
                        if only and owner != only:
                            continue
                        tid = key.rsplit(".", 1)[0]
                        t = takes.setdefault(tid, {"id": tid, **({"singer": owner} if owner in site.singers else {"invite": owner})})
                        t[key.rsplit(".", 1)[1]] = {"key": key, "size": len(data), "uploaded": site.times[key]}
                    return self.reply(200, {"takes": list(takes.values())})
                if path.startswith("take/"):
                    key = path[5:]
                    if key not in site.objects:
                        return self.reply(404, {"error": "unknown", "message": "No such take."})
                    if method == "DELETE":
                        site.deleted.append(key)
                        del site.objects[key]
                        return self.reply(200, {"deleted": key})
                    return self.reply(200, site.objects[key], "audio/wav" if key.endswith(".wav") else "application/json")
                if method == "GET" and path == "words":
                    return self.reply(200, {"words": [{"key": k, "singer": k.split("/")[1], "size": len(json.dumps(w)),
                                                       "uploaded": w["at"]} for k, w in sorted(site.words.items())]})
                if method == "GET" and path.startswith("word/"):
                    return self.reply(200, site.words[path[5:]])
                if method == "GET" and path == "gone":
                    return self.reply(200, {"gone": site.gone})
                if path.startswith("file/"):
                    sid, name = path[5:].split("/", 1)
                    if sid not in site.singers:
                        return self.reply(404, {"error": "unknown", "message": "No such singer."})
                    if method == "DELETE":
                        site.files.get(sid, {}).pop(name, None)
                        return self.reply(200, {"deleted": name})
                    if site.singers[sid]["state"] == "withdrawn":
                        return self.reply(409, {"error": "withdrawn", "message": "They withdrew."})
                    if site.status()["deleting"]:
                        return self.reply(410, {"error": "deleted", "message": "Recordings have been deleted."})
                    if not I.FILE_NAME.match(name):
                        return self.reply(400, {"error": "name", "message": "Not a file name."})
                    kind = "version" if ".version." in name else "vocals" if ".vocals." in name else "other"
                    site.files.setdefault(sid, {})[name] = {
                        "name": name, "kind": kind, "about": query.get("about", [""])[0], "bytes": len(body), "made": site.now,
                        "spec": query.get("spec", [None])[0], "type": self.headers["Content-Type"], "data": body,
                        "query": url.query}
                    return self.reply(200, {"ok": True, "name": name, "bytes": len(body)})
                if method == "POST" and path.startswith("sent/"):
                    sent = site.singers[path[5:]]["sent"]
                    sent[json.loads(body)["kind"]] = site.now
                    return self.reply(200, {"sent": sent})
                if method == "POST" and path == "purge":
                    if not site.status()["deleting"]:
                        return self.reply(409, {"error": "early", "message": "Not yet."})
                    takes = [k for k in site.objects if k.endswith(".json")]
                    files = sum(len(f) for f in site.files.values())
                    emails = sum(bool(s["email"]) and not s["notify"] for s in site.singers.values())
                    site.objects.clear()
                    site.files.clear()
                    for s in site.singers.values():
                        s["email"] = s["email"] if s["notify"] else None
                    site.purged.append({"takes": len(takes), "files": files, "emails": emails})
                    return self.reply(200, {**site.purged[-1], "more": False})
                return self.reply(404, {"error": "unknown", "message": "No such thing."})

            def do_GET(self):
                self.route("GET")

            def do_POST(self):
                self.route("POST")

            def do_PUT(self):
                self.route("PUT")

            def do_DELETE(self):
                self.route("DELETE")

        return Handler


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    fake = FakeSite()
    server = ThreadingHTTPServer(("127.0.0.1", 0), fake.handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    fake.api = I.Site(f"http://127.0.0.1:{server.server_address[1]}", ADMIN)
    yield fake
    server.shutdown()
    server.server_close()


def pinned() -> None:
    """The guide score and the release, kept here when the site was built."""
    K.GUIDES.mkdir(parents=True, exist_ok=True)
    (K.GUIDES / f"{SONG}.{GUIDE}.score.json").write_text("{}")
    (K.GUIDES / "release.896e20c8603e.html").write_text("<p>the release</p>")


def online(site, people: int = 1, note: str = "") -> str:
    """An invitation's token."""
    return I.new(site.api, 1, note, 7, 30, people=people)[0]["token"]


def kept() -> dict:
    """The online takes here, with their audio or not, by their id on the site."""
    return I.fetched()


def fake_versions(made: list):
    """tools/versions.py as sync calls it: make(genome_path, takes, spec, out_dir, ..., title) -> Made."""
    def make(genome_path, takes, spec, out_dir, stems=None, strip=None, title=""):
        out_dir.mkdir(parents=True, exist_ok=True)
        made.append({"genome": genome_path, "spec": spec, "takes": sorted(t.info["remote"] for t in takes),
                     "title": title, "out": out_dir})
        (out_dir / "version.mp3").write_bytes(b"ID3 " + spec.encode())
        (out_dir / "vocals.wav").write_bytes(b"RIFF " + spec.encode())
        return types.SimpleNamespace(version=out_dir / "version.mp3", vocals=out_dir / "vocals.wav", sections=[0])

    return types.SimpleNamespace(make=make)


# ---------- the first version's one-time links, as before

def test_new_invites_are_links_and_list_shows_them(site, capsys):
    made = I.new(site.api, 2, "choir, Tuesday", 7, 30)
    out = capsys.readouterr().out.split()
    assert out == [m["url"] for m in made] and all("/i/" in u for u in out)
    listed = I.listing(site.api)
    assert {inv["token"] for inv in listed} == {m["token"] for m in made}
    I.revoke(site.api, made[0]["token"])
    assert site.invites[made[0]["token"]]["state"] == "revoked"


def test_fetch_keeps_takes_like_the_recording_page_and_empties_the_server(site, tmp_path, capsys):
    token = I.new(site.api, 1, "Ana from choir", 7, 30)[0]["token"]
    pinned()  # its guide score and the release as it read, pinned when the site was built
    named = site.add_take(token, "20261001T100000Z", name="Ana María")
    site.add_take(token, "20261001T100500Z", name="", mix="full")  # no name: the invitation's note names the folder
    kept = I.fetch(site.api)
    assert len(kept) == 2 and not site.objects  # both here, and gone from the server
    by = {t.who: t for t in kept}
    noted = K.slug(f"Ana from choir ({token[:6]})")
    assert set(by) == {"ana-maria", noted}
    ana = by["ana-maria"]
    assert (ana.singer, ana.song, ana.guide, ana.use) == ("Ana María", "h-now-its-by-you", GUIDE, True)
    assert ana.info["mix"] == "melody" and by[noted].info["mix"] == "full"
    assert ana.info["source"] == "online" and ana.info["remote"] == named and ana.info["invite"] == token[:6]
    assert ana.info["consent"]["agreed"] and ana.info["credit"] is True and ana.info["credit_as"] == "Ana María"
    assert by[noted].info["credit"] is False and by[noted].info["credit_as"] == ""  # no name to credit
    assert (ana.info["shift_ms"], ana.info["device_ms"], ana.info["rate"]) == (12, 40, 48000)
    assert sf.info(ana.path).samplerate == 48000
    assert K.takes("h-now-its-by-you", "ana-maria")[0].path == ana.path  # the recording page and phrasing tools see it
    assert "not in guides" not in capsys.readouterr().out  # its guide score and release are here
    assert I.fetch(site.api) == []  # nothing left to fetch


def test_fetch_keep_leaves_takes_and_a_later_fetch_clears_them(site, capsys):
    token = I.new(site.api, 1, "", 7, 30)[0]["token"]
    site.add_take(token, "20261001T100000Z")
    kept = I.fetch(site.api, keep=True)
    assert kept[0].who == K.slug(f"singer ({token[:6]})")  # no name, no note: the invitation names the folder
    assert len(site.objects) == 2  # still on the server
    out = capsys.readouterr().out
    assert "guide score" in out and "release" in out and "not in guides" in out  # neither is here: said so
    assert I.fetch(site.api) == [] and not site.objects  # already here: only cleared from the server
    assert len(K.takes("h-now-its-by-you")) == 1


def test_fetch_one_invitation_under_a_chosen_name(site):
    a, b = (inv["token"] for inv in I.new(site.api, 2, "", 7, 30))
    site.add_take(a, "20261001T100000Z", name="Jo")
    site.add_take(b, "20261001T100000Z", name="Sam")
    kept = I.fetch(site.api, invite=a, singer="Test Singer")
    assert [t.who for t in kept] == ["test-singer"] and len(site.objects) == 2


def test_different_people_never_share_a_folder(site):
    a, b, c, d, e = (inv["token"] for inv in I.new(site.api, 5, "choir, Tuesday", 7, 30))
    K.keep_sung("h-now-its-by-you", "Milo", b"RIFF-here", GUIDE)  # sung here, on the recording page
    ja = site.add_take(a, "20261001T100000Z", name="Jo")
    jb = site.add_take(b, "20261001T100100Z", name="Jo")  # someone else called Jo
    ja2 = site.add_take(a, "20261001T100200Z", name="Jo")  # the first Jo again
    milo = site.add_take(c, "20261001T100300Z", name="Milo")  # not the Milo who sang here
    blank = site.add_take(d, "20261001T100400Z")  # two who gave no name, from invitations with one note
    blank2 = site.add_take(e, "20261001T100500Z")
    odd = site.add_take(e, "20261001T100600Z", name="!!!")
    akemi = site.add_take(e, "20261001T100700Z", name="明美")
    by = {t.info["remote"]: t.who for t in I.fetch(site.api)}
    assert by[ja] == by[ja2] != by[jb] and "jo" in (by[ja], by[jb])
    assert {by[ja], by[jb]} - {"jo"} <= {K.slug(f"Jo ({a[:6]})"), K.slug(f"Jo ({b[:6]})")}
    assert by[milo] == K.slug(f"Milo ({c[:6]})")
    assert by[blank] == K.slug(f"choir, Tuesday ({d[:6]})") != by[blank2] == K.slug(f"choir, Tuesday ({e[:6]})")
    assert by[odd] == by[blank2]  # a name no folder can be made of is no name: the same invitation, the same singer
    assert by[akemi] == "明美"


def test_the_admin_token_travels_only_over_https(site):
    with pytest.raises(SystemExit, match="https"):
        I.Site("http://songbird.quadule.com", ADMIN)
    I.Site("https://songbird.quadule.com", ADMIN)
    I.Site("http://localhost:8787", ADMIN)


def test_what_never_arrived_whole_can_be_cleared(site, capsys):
    token = I.new(site.api, 1, "", 7, 30)[0]["token"]
    old = site.add_take(token, "20260101T100000Z", uploaded="2026-01-01T10:00:00.000Z")
    new = site.add_take(token, "20261001T100000Z")  # the sidecar may still be on its way
    del site.objects[f"{old}.json"], site.objects[f"{new}.json"]
    soon = moment(UPLOADED) + dt.timedelta(seconds=I.STALE // 2)  # the clock, as the tool sees it
    assert I.fetch(site.api, now=soon) == [] and len(site.objects) == 2
    assert "--purge-incomplete deletes it" in capsys.readouterr().out
    assert I.fetch(site.api, purge=True, now=soon) == []
    assert list(site.objects) == [f"{new}.wav"] and site.deleted == [f"{old}.wav"]


def test_a_damaged_or_half_sent_take_stays_on_the_server(site, capsys):
    token = I.new(site.api, 1, "", 7, 30)[0]["token"]
    site.add_take(token, "20261001T100000Z", corrupt=True)
    orphan = site.add_take(token, "20261001T110000Z")
    del site.objects[f"{orphan}.json"]
    assert I.fetch(site.api, now=moment(UPLOADED) + dt.timedelta(hours=1)) == []
    assert len(site.objects) == 3 and not site.deleted
    out = capsys.readouterr().out
    assert "doesn't match" in out and "incomplete" in out


def test_dry_run_fetches_nothing(site, capsys):
    token = I.new(site.api, 1, "", 7, 30)[0]["token"]
    site.add_take(token, "20261001T100000Z", name="Jo")
    assert I.fetch(site.api, dry_run=True) == [] and len(site.objects) == 2
    assert "--dry-run" in capsys.readouterr().out


def test_the_wrong_admin_token_is_refused(site):
    with pytest.raises(SystemExit, match="401"):
        I.Site(site.api.url, "b" * 43).call("GET", "/api/admin/invites")


def test_the_admin_token_comes_from_the_environment_or_the_secrets_tool(monkeypatch):
    monkeypatch.setenv("SONGBIRD_SING_ADMIN", "from-env")
    assert I.admin_token() == "from-env"
    monkeypatch.delenv("SONGBIRD_SING_ADMIN")
    asked = []

    def run(cmd, **kw):
        asked.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="from-secrets\n", stderr="")

    monkeypatch.setattr(I.subprocess, "run", run)
    assert I.admin_token() == "from-secrets" and asked == [["secrets", "get", "songbird-sing-admin"]]
    monkeypatch.setattr(I.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="nope"))
    with pytest.raises(SystemExit, match="SONGBIRD_SING_ADMIN"):
        I.admin_token()


# ---------- the second version: a page for everyone who joins

def test_a_group_link_says_so_and_the_list_shows_who_joined(site, capsys):
    made = I.new(site.api, 1, "the list", 7, 30, people=40)
    out, err = capsys.readouterr()
    token = made[0]["token"]
    assert out.split() == [made[0]["url"]] and "a group link for up to 40 people" in err
    assert site.invites[token]["people"] == 40
    I.new(site.api, 2, "", 7, 30)
    assert "each a personal link" in capsys.readouterr().err
    site.add_sung(site.add_singer(token, name="Jo"), "20260926T231501Z")
    site.add_singer(token)
    I.listing(site.api)
    line = next(line for line in capsys.readouterr().out.splitlines() if token in line)
    assert line.startswith("open") and "joined   2/40" in line and "takes   1" in line and "the list" in line


def test_singers_shows_their_emails_only_when_asked(site, capsys):
    token = online(site, people=5)
    ana = site.add_singer(token, name="Ana María", email="ana+songs@example.com")
    site.add_singer(token, email="jo@example.com")
    site.singers[ana]["done"] = "2026-09-26T23:40:00.000Z"
    site.page = 1  # the site lists them a page at a time
    capsys.readouterr()
    rows = I.singers(site.api)
    out = capsys.readouterr().out
    assert len(rows) == 2 and not any("email" in row for row in rows)
    assert "@example.com" not in out and "Ana María" in out and f"/y/{ana}" in out and " done " in out
    assert I.singers(site.api, emails=True)[0]["email"] == "ana+songs@example.com"
    out = capsys.readouterr().out
    assert "ana+songs@example.com" in out and "jo@example.com" in out
    assert ("GET", "singers", "emails=1&cursor=1") in site.requests  # the second page, still with emails


def test_sync_keeps_takes_with_where_they_were_sung_and_leaves_them_on_the_site(site, capsys):
    pinned()
    token = online(site)
    ana = site.add_singer(token, name="Ana María")
    whole = site.add_sung(ana, "20260926T231501Z")
    verse = site.add_sung(ana, "20260926T232000Z", spec="a.k-2.t90", section=1, label="They saved it as numbers,",
                          from_s=5.9, to_s=31.4, rand="bcdefg")
    capsys.readouterr()
    assert I.sync(site.api, make=False) == 2
    out = capsys.readouterr().out
    assert "the whole song" in out and "section 1" in out and "not in guides" not in out and ana not in out
    takes = kept()
    t = takes[verse]
    assert (t.who, t.singer, t.song, t.guide, t.use) == ("ana-maria", "Ana María", SONG, GUIDE, True)
    assert {k: t.info[k] for k in ("source", "sid", "person", "invite", "spec", "from_s", "to_s", "section", "label",
                                   "mix", "rate", "received")} == {
        "source": "online", "sid": ana, "person": ana, "invite": token[:6], "spec": "a.k-2.t90", "from_s": 5.9,
        "to_s": 31.4, "section": 1, "label": "They saved it as numbers,", "mix": "melody", "rate": 48000,
        "received": "2026-09-26T23:20:00.000Z"}
    assert t.info["credit"] is True and t.info["credit_as"] == "Ana María" and t.info["consent"]["agreed"]
    assert {k: t.info[k] for k in I.TIMING} == {"shift_ms": 12, "auto_ms": 10, "device_ms": 40, "decode_ms": 0,
                                               "out_ms": 29, "in_ms": 10}
    assert (takes[whole].info["section"], takes[whole].info["label"], takes[whole].info["spec"]) == (None, None, "a.k0.t100")
    assert sf.info(t.path).samplerate == 48000
    assert len(site.objects) == 4 and not site.deleted  # still on the site: their singer needs them until DELETE_BY
    asked = len(site.requests)
    assert I.sync(site.api, make=False) == 0 and capsys.readouterr().out == ""  # in step: nothing fetched, nothing said
    assert [(m, p) for m, p, _ in site.requests[asked:]] == [("GET", "status"), ("GET", "gone"), ("GET", "takes"),
                                                             ("GET", "words")]  # R2 listings only: no KV lists


def test_credit_only_by_a_name_they_gave_and_asked_to_be_credited_by(site):
    token = online(site, people=5)
    shy = site.add_sung(site.add_singer(token, name="Jo", credit=False), "20260926T231501Z")
    nameless = site.add_sung(site.add_singer(token, credit=True), "20260926T231601Z")
    I.sync(site.api, make=False)
    takes = kept()
    assert (takes[shy].info["credit"], takes[shy].info["credit_as"]) == (False, "Jo")
    assert (takes[nameless].info["credit"], takes[nameless].info["credit_as"]) == (False, "")


def test_a_person_keeps_one_folder_and_two_people_never_share_one(site):
    group = online(site, people=20, note="choir, Tuesday")
    K.keep_sung(SONG, "Milo", b"RIFF-here", GUIDE)  # sung here, on the recording page
    (K.ROOT / "renders" / "phrasing").mkdir(parents=True)
    I.phrasing_path(SONG, "daniel").write_text("{}")  # a reading's phrasing, by a synthetic voice called Daniel
    jo = site.add_singer(group, name="Jo")
    other = site.add_singer(group, name="Jo")  # someone else called Jo
    phone = site.add_singer(group, name="Jo", person=jo)  # the first Jo again, on their phone
    milo = site.add_singer(group, name="Milo")  # not the Milo who sang here
    words = site.add_singer(group, name="Words")  # recordings/words/ holds the words people send
    daniel = site.add_singer(group, name="Daniel")
    blank, blank2 = site.add_singer(group), site.add_singer(group)
    a, b, c = (site.add_sung(s, f"20260926T2315{n}1Z") for n, s in enumerate((jo, other, phone)))
    d, e, f = (site.add_sung(s, f"20260926T2316{n}1Z") for n, s in enumerate((milo, words, daniel)))
    g, h = (site.add_sung(s, f"20260926T2317{n}1Z") for n, s in enumerate((blank, blank2)))
    asked = len(site.requests)
    I.sync(site.api, make=False)
    assert sum(path == "invites" for _, path, _ in site.requests[asked:]) == 1  # the note, asked for once
    by = {remote: t.who for remote, t in kept().items()}
    assert by[a] == by[c] == "jo" and by[b] == K.slug(f"Jo ({other[:6]})")  # one person's pages share a folder
    assert by[d] == K.slug(f"Milo ({milo[:6]})") and by[e] == K.slug(f"Words ({words[:6]})")
    assert by[f] == K.slug(f"Daniel ({daniel[:6]})")
    assert by[g] == K.slug(f"choir, Tuesday ({blank[:6]})") != by[h] == K.slug(f"choir, Tuesday ({blank2[:6]})")
    K.keep_sung(SONG, "Jo", b"RIFF-here", GUIDE)  # now someone called Jo sings here, on the recording page
    later = site.add_sung(jo, "20260926T232001Z")
    third = site.add_singer(group, name="Jo")
    theirs = site.add_sung(third, "20260926T232101Z")
    asked = len(site.requests)
    I.sync(site.api, make=False)
    by = {remote: t.who for remote, t in kept().items()}
    assert by[later] == "jo" and by[theirs] == K.slug(f"Jo ({third[:6]})")  # the first Jo's stay together; a third apart
    assert not any(path == "invites" for _, path, _ in site.requests[asked:])  # everyone had a name


def test_words_people_send_are_kept_by_singer(site, capsys):
    ana = site.add_singer(online(site), name="Ana María")
    first = site.add_words(ana, "A verse about the wire", "2026-09-26T23:20:00.000Z")
    capsys.readouterr()
    assert I.sync(site.api, make=False) == 1
    assert "words from Ana María: 1 new" in capsys.readouterr().out
    path = K.RECORDINGS / "words" / f"{ana}.json"
    release = {"agreed": True, "at": "2026-09-26T23:20:00.000Z", "text": "5e1ea5ed1ge5"}
    assert json.loads(path.read_text()) == {"sid": ana, "person": ana, "name": "Ana María", "credit": True, "words": [
        {"key": first, "at": "2026-09-26T23:20:00.000Z", "text": "A verse about the wire", "release": release}]}
    second = site.add_words(ana, "Zoë's line, and another", "2026-09-26T23:25:00.000Z", rand="wxyz45")
    I.sync(site.api, make=False)
    words = json.loads(path.read_text())["words"]
    assert [w["key"] for w in words] == [first, second] and words[1]["text"] == "Zoë's line, and another"
    assert I.sync(site.api, make=False) == 0
    assert I.fetched() == {} and K.takes(SONG) == []  # words aren't takes


def test_a_take_its_singer_deleted_loses_its_audio_here_but_keeps_its_numbers(site, capsys):
    jo = site.add_singer(online(site), name="Jo")
    one = site.add_sung(jo, "20260926T231501Z")
    two = site.add_sung(jo, "20260926T231601Z", rand="bcdefg")
    I.sync(site.api, make=False)
    takes = kept()
    numbers = I.measurements(takes[one].path)
    assert numbers[0] == K.ROOT / "renders" / "measured" / f"recordings__jo__{takes[one].path.stem}.json"
    for f in numbers:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    site.delete_take(jo, one, "2026-09-26T23:40:00.000Z")
    capsys.readouterr()
    assert I.sync(site.api, make=False) == 1
    assert "audio is gone here too" in capsys.readouterr().out
    assert not takes[one].path.exists() and takes[two].path.exists()
    side = json.loads(takes[one].sidecar().read_text())
    assert side["deleted"] == "2026-09-26T23:40:00.000Z" and side["remote"] == one and side["sid"] == jo
    assert all(f.exists() for f in numbers)  # the numbers already taken stay
    assert I.sync(site.api, make=False) == 0 and capsys.readouterr().out == ""  # done again: nothing, said nothing
    takes[two].path.unlink()  # the artist deletes a take's audio here by hand: it isn't fetched again
    assert I.sync(site.api, make=False) == 0 and not takes[two].path.exists()


def test_deleting_everything_takes_only_what_arrived_before(site):
    jo = site.add_singer(online(site), name="Jo")
    early = site.add_sung(jo, "20260926T231501Z")
    I.sync(site.api, make=False)
    site.delete_all(jo, "2026-09-26T23:40:00.000Z")
    late = site.add_sung(jo, "20260926T235000Z", rand="bcdefg")  # they sing again afterwards
    lagging = site.add_sung(jo, "20260926T233000Z", rand="cdefgh")  # arrived before, but still listed
    I.sync(site.api, make=False)
    takes = kept()
    assert not takes[early].path.exists() and takes[early].info["deleted"] == "2026-09-26T23:40:00.000Z"
    assert takes[late].path.exists() and "deleted" not in takes[late].info
    assert lagging not in takes  # what they deleted is never fetched
    assert I.sync(site.api, make=False) == 0 and takes[late].path.exists()


def test_a_singer_who_withdraws_leaves_nothing_here(site, capsys):
    group = online(site, people=10)
    ana, jo, lee = (site.add_singer(group, name=name) for name in ("Ana", "Jo", "Lee"))
    phone = site.add_singer(group, name="Lee", person=lee)  # Lee again, on their phone
    a1 = site.add_sung(ana, "20260926T231501Z")
    a2 = site.add_sung(ana, "20260926T231601Z", spec="a.k-2.t90", rand="bcdefg")
    j1 = site.add_sung(jo, "20260926T231701Z")
    l1, l2 = site.add_sung(lee, "20260926T231801Z"), site.add_sung(phone, "20260926T231901Z")
    site.add_words(ana, "a verse", "2026-09-26T23:20:00.000Z")
    site.add_words(jo, "another", "2026-09-26T23:21:00.000Z")
    I.sync(site.api, make=False)
    K.keep_sung(SONG, "Jo", b"RIFF-here", GUIDE)  # a singer called Jo on the recording page, in Jo's folder
    takes = kept()
    for t in takes.values():
        for f in I.measurements(t.path):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}")
    (K.ROOT / "renders" / "phrasing").mkdir(parents=True)
    for who in ("ana", "jo", "lee", "everyone"):
        I.phrasing_path(SONG, who).write_text("{}")
        I.karaoke_render(SONG, who).write_bytes(b"fLaC")
    I.phrasing_path(SONG, "choir.1").write_text("{}")  # the recording page's choir: a blend of several singers
    solo, sung = I.karaoke_render(SONG, "jo"), I.karaoke_render(SONG, "plain")  # Jo's way alone; its own with the choir
    solo.with_suffix(".json").write_text(json.dumps({"choir_phrasings": None}))
    sung.write_bytes(b"fLaC")
    sung.with_suffix(".json").write_text(json.dumps({"choir_phrasings": [{"source_detail": "1 sung take(s)"}]}))
    sung.with_suffix(".score.json").write_text("{}")
    site.withdraw(ana, "2026-09-26T23:50:00.000Z")
    site.withdraw(phone, "2026-09-26T23:51:00.000Z")
    capsys.readouterr()
    assert I.sync(site.api, make=False) == 2
    out = capsys.readouterr().out
    assert "ana withdrew" in out and "lee withdrew" in out
    assert not (K.RECORDINGS / "ana").exists() and not (K.RECORDINGS / "words" / f"{ana}.json").exists()
    assert not any(f.exists() for t in (takes[a1], takes[a2], takes[l2]) for f in I.measurements(t.path))
    assert not takes[l2].path.exists() and not takes[l2].sidecar().exists()
    for who in ("ana", "lee", "everyone"):  # each held numbers taken from them
        assert not I.phrasing_path(SONG, who).exists() and not I.karaoke_render(SONG, who).exists()
    assert not I.phrasing_path(SONG, "choir.1").exists()  # and so did the choir, and what it sang
    assert not any(f.exists() for f in (sung, sung.with_suffix(".json"), sung.with_suffix(".score.json")))
    assert solo.with_suffix(".json").exists()
    for t in (takes[j1], takes[l1]):  # Jo's, and Lee's other page's, stay
        assert t.path.exists() and t.sidecar().exists() and all(f.exists() for f in I.measurements(t.path))
    assert (K.RECORDINGS / "words" / f"{jo}.json").exists() and I.phrasing_path(SONG, "jo").exists()
    assert I.karaoke_render(SONG, "jo").exists() and len(K.takes(SONG, "jo")) == 2
    assert I.sync(site.api, make=False) == 0 and capsys.readouterr().out == ""  # done again: nothing, said nothing


def test_versions_are_made_for_each_person_and_put_on_each_of_their_pages(site, monkeypatch, capsys):
    made = []
    monkeypatch.setitem(sys.modules, "versions", fake_versions(made))
    token = online(site)
    ana = site.add_singer(token, name="Ana")
    phone = site.add_singer(token, name="Ana", person=ana)  # the same person, on their phone
    one = site.add_sung(ana, "20260926T231501Z")
    capsys.readouterr()
    assert I.sync(site.api) == 2  # the take, and its version
    assert "their a.k0.t100 version is on their page" in capsys.readouterr().out
    assert [(m["spec"], m["takes"], m["out"]) for m in made] == [
        ("a.k0.t100", [one], K.ROOT / "renders" / "versions" / "ana" / "a.k0.t100")]
    assert made[0]["genome"] == K.ROOT / "songs" / f"{SONG}.json" and made[0]["title"].endswith("(your version)")
    files = site.files[ana]
    assert set(files) == {"a.k0.t100.version.mp3", "a.k0.t100.vocals.wav"} and phone not in site.files
    version, vocals = files["a.k0.t100.version.mp3"], files["a.k0.t100.vocals.wav"]
    assert (version["type"], version["about"], version["spec"], version["data"]) == (
        "audio/mpeg", "Your version of the song", "a.k0.t100", b"ID3 a.k0.t100")
    assert (vocals["type"], vocals["about"], vocals["kind"]) == ("audio/wav", "Your vocals on their own", "vocals")
    assert "about=Your%20version%20of%20the%20song" in version["query"]  # no "+" for spaces
    assert I.sync(site.api) == 0 and len(made) == 1  # in step: nothing made again
    two = site.add_sung(phone, "20260926T232001Z", rand="bcdefg")  # they sing from their phone
    site.now = "2026-09-26T23:35:00.000Z"
    I.sync(site.api)
    assert made[-1]["takes"] == sorted([one, two]) and set(site.files[phone]) == set(files)  # on both pages
    site.delete_take(ana, one, "2026-09-26T23:40:00.000Z")  # the site deletes that page's files, not the phone's
    site.now = "2026-09-26T23:45:00.000Z"
    capsys.readouterr()
    I.sync(site.api)
    out = capsys.readouterr().out
    assert "made again" in out and made[-1]["takes"] == [two]
    assert ("DELETE", f"file/{phone}/a.k0.t100.version.mp3", "") in site.requests  # it held the deleted take
    assert set(site.files[ana]) == set(site.files[phone]) == {"a.k0.t100.version.mp3", "a.k0.t100.vocals.wav"}
    record = json.loads(I.versions_file().read_text())[ana]["a.k0.t100"]
    assert record["takes"] == [two] and record["sids"] == sorted([ana, phone]) and record["uploaded"]
    assert record["files"] == [{"path": "renders/versions/ana/a.k0.t100/version.mp3", "name": "a.k0.t100.version.mp3"},
                               {"path": "renders/versions/ana/a.k0.t100/vocals.wav", "name": "a.k0.t100.vocals.wav"}]
    count = len(made)
    assert I.sync(site.api) == 0 and len(made) == count  # in step again


def test_versions_skipped_without_tools_versions_or_for_takes_it_cant_use(site, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "versions", None)  # tools/versions.py isn't here
    jo = site.add_singer(online(site), name="Jo")
    site.add_sung(jo, "20260926T231501Z")
    memo = I.memory()
    capsys.readouterr()
    I.sync(site.api, memo=memo)
    out = capsys.readouterr().out
    assert out.count("versions skipped") == 1 and "tools/versions.py" in out and not site.files
    site.add_sung(jo, "20260926T231601Z", rand="bcdefg")
    I.sync(site.api, memo=memo)
    assert "versions skipped" not in capsys.readouterr().out  # said once

    def make(genome_path, takes, spec, out_dir, **kw):
        raise ValueError("none of these takes sings a whole section")

    monkeypatch.setitem(sys.modules, "versions", types.SimpleNamespace(make=make))
    I.sync(site.api, memo=memo)
    assert "no a.k0.t100 version: ValueError: none of these takes sings a whole section" in capsys.readouterr().out
    assert I.sync(site.api, memo=memo) == 0 and not site.files  # said once, not tried again until the takes change


def test_mail_writes_one_message_per_address(site, capsys):
    token = online(site, people=10)
    ana = site.add_singer(token, name="Ana María", email="ana@example.com", notify=True)
    phone = site.add_singer(token, name="Ana María", email="Ana@Example.com ", person=ana)  # her phone
    jo = site.add_singer(token, email="jo@example.com")
    site.add_singer(token, name="Sam")  # gave no email
    lee = site.add_singer(token, name="Lee", email="lee@example.com")
    site.withdraw(lee, "2026-09-26T23:25:00.000Z")
    capsys.readouterr()
    letters = I.mail(site.api)
    out = capsys.readouterr().out
    base = site.api.url
    assert [m["to"] for m in letters] == ["ana@example.com", "jo@example.com"] and out.count("To: ") == 2
    assert letters[0]["subject"] == "Your Songbird pages"
    assert letters[0]["body"] == (
        "Hi Ana María,\n\n"
        f"Thank you for singing! Your pages are here:\n{base}/y/{ana}\n{base}/y/{phone}\n\n"
        "There you can listen to what you sent, download it, delete it, or withdraw. You can withdraw until singing "
        "closes on Sunday, September 27 at 10 PM Pacific. Your version of the song will appear there in a few days, "
        "before September 30 (I'll write again when it does). Everything you recorded is deleted by September 30.\n\n"
        "You asked to hear when the song is released to the public, so I'll write again then.\n\n"
        "Milo")
    assert letters[1]["subject"] == "Your Songbird page"
    assert letters[1]["body"].startswith(f"Hi,\n\nThank you for singing! Your own page is here: {base}/y/{jo}\n\n")
    assert letters[1]["body"].endswith("deleted by September 30.\n\nMilo")
    assert "lee@example.com" not in out and "Sam" not in out and "shared" not in out
    listed = json.loads(I.mail_file().read_text())["emails"]
    assert listed == [{"sid": ana, "kind": "link"}, {"sid": phone, "kind": "link"}, {"sid": jo, "kind": "link"}]


def test_mail_once_singing_has_closed_and_once_a_version_is_ready(site, capsys):
    token = online(site, people=10)
    jo = site.add_singer(token, name="Jo", email="jo@example.com")
    ana = site.add_singer(token, name="Ana", email="ana@example.com")
    site.singers[jo]["sent"]["link"] = OPEN  # had their page already
    version = {"name": "a.k0.t100.version.mp3", "kind": "version", "about": "Your version of the song", "bytes": 9,
               "made": OPEN}
    site.files[jo] = site.files[ana] = {version["name"]: version}
    site.now = CLOSED
    base = site.api.url
    letters = {m["to"]: m for m in I.mail(site.api)}
    assert letters["jo@example.com"]["subject"] == "Your version of the song is ready"
    assert letters["jo@example.com"]["body"] == (
        f"Hi Jo,\n\nYour version of the song is ready on your page: {base}/y/{jo}\n\n"
        "You can listen to it there and download it, with your vocals on their own. Everything you recorded, and "
        "these files, are deleted by September 30, so download anything you'd like to keep before then.\n\n"
        "Thank you for singing!\nMilo")
    both = letters["ana@example.com"]  # their page and their version at once: one message
    assert both["subject"] == "Your Songbird page" and "withdraw" not in both["body"]
    assert "There you can listen to what you sent, download it, or delete it. Your version of the song is there too" in both["body"]
    assert both["body"].endswith("so download anything you'd like to keep before then.\n\nMilo")
    assert both["covers"] == [(ana, "link"), (ana, "ready")]
    site.now = OPEN
    assert "You can withdraw until singing closes on Sunday, September 27 at 10 PM Pacific." in I.mail(site.api)[1]["body"]
    site.now = DELETING  # emails are kept only for the one message about the song's release by then
    capsys.readouterr()
    assert I.mail(site.api) == [] and "no one needs an email" in capsys.readouterr().out


def test_mail_open_makes_each_message_a_mailto_link(site, monkeypatch):
    zoe = site.add_singer(online(site), name="Zoë Ångström", email="zoe+songs@example.com")
    opened = []
    monkeypatch.setattr(I.subprocess, "run", lambda cmd, **kw: opened.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    letters = I.mail(site.api, open_=True)
    assert len(opened) == 1 and opened[0][0] == "open"
    url = opened[0][1]
    assert url.startswith("mailto:zoe%2Bsongs@example.com?subject=Your%20Songbird%20page&body="
                          "Hi%20Zo%C3%AB%20%C3%85ngstr%C3%B6m%2C%0D%0A%0D%0AThank%20you%20for%20singing%21")
    assert not set(url) & set(" +\r\n") and zoe in url
    fields = dict(part.split("=", 1) for part in url.split("?", 1)[1].split("&"))
    assert urllib.parse.unquote(fields["subject"]) == "Your Songbird page"
    assert urllib.parse.unquote(fields["body"]) == letters[0]["body"].replace("\n", "\r\n")


def test_sent_marks_exactly_what_mail_listed(site, capsys):
    token = online(site, people=10)
    ana = site.add_singer(token, name="Ana", email="ana@example.com")
    jo = site.add_singer(token, email="jo@example.com")
    I.mail(site.api)
    late = site.add_singer(token, email="late@example.com")  # joined after the listing
    capsys.readouterr()
    assert I.mark_sent(site.api) == 2
    assert "marked as sent: 2 page links" in capsys.readouterr().out
    assert site.singers[ana]["sent"]["link"] and site.singers[jo]["sent"]["link"] and not site.singers[late]["sent"]["link"]
    assert not I.mail_file().exists()
    assert I.mark_sent(site.api) == 0 and "run `mail` first" in capsys.readouterr().out
    assert [m["to"] for m in I.mail(site.api)] == ["late@example.com"]


def test_purge_waits_for_delete_by_then_takes_the_online_audio(site, monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "versions", fake_versions([]))
    jo = site.add_singer(online(site), name="Jo")
    one = site.add_sung(jo, "20260926T231501Z")
    I.sync(site.api)
    here = K.keep_sung(SONG, "Milo", b"RIFF-here", GUIDE)  # sung here: not the site's to delete
    old = K.keep_sung(SONG, "Old", b"RIFF-v1", GUIDE, source="online", remote="takes/x/y", invite="abcdef")  # first version
    take = kept()[one]
    numbers = I.measurements(take.path)
    for f in numbers:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    throat = K.ROOT / "renders" / "throat"
    (throat / "corpus" / "jo").mkdir(parents=True)
    (throat / "corpus" / "jo" / "0001.wav").write_bytes(b"RIFF")
    for name in ("dataset.npz", "dataset-v1.npz", "model.npz"):
        (throat / name).write_bytes(b"PK")
    os.utime(throat / "dataset-v1.npz", (1e9, 1e9))  # built in 2001, long before anyone sang online
    capsys.readouterr()
    assert I.purge(site.api) == 0 and "not yet" in capsys.readouterr().out and take.path.exists()
    site.now = DELETING
    assert I.purge(site.api, server=True, now=DELETING) == 3  # its audio, and its version and vocals
    out = capsys.readouterr().out
    assert not take.path.exists() and json.loads(take.sidecar().read_text())["purged"] == DELETING
    assert here.path.exists() and old.path.exists() and all(f.exists() for f in numbers)
    assert not (K.ROOT / "renders" / "versions" / "jo").exists() and json.loads(I.versions_file().read_text()) == {}
    assert "renders/throat/corpus/" in out and "renders/throat/dataset.npz" in out  # named, not deleted
    assert "dataset-v1.npz" not in out and "model.npz" not in out and (throat / "dataset.npz").exists()
    assert site.purged and not site.objects  # the site's own purge, now
    site.add_sung(jo, "20260930T200000Z", rand="bcdefg")  # left on the site until its hourly purge
    assert I.sync(site.api) == 0 and capsys.readouterr().out == ""  # nothing fetched, nothing left to purge


def test_fetch_never_deletes_a_take_its_singer_can_still_hear(site, capsys):
    jo = site.add_singer(online(site), name="Jo")
    first = site.add_sung(jo, "20260926T231501Z")
    taken = I.fetch(site.api)
    assert [(t.info["remote"], t.info["sid"], t.info["spec"], t.who) for t in taken] == [(first, jo, "a.k0.t100", "jo")]
    assert len(site.objects) == 2 and not site.deleted
    assert I.fetch(site.api) == [] and not site.deleted  # already here, and still left there
    half = site.add_sung(jo, "20260101T100000Z", rand="bcdefg", uploaded="2026-01-01T10:00:00.000Z")
    del site.objects[f"{half}.json"]
    I.fetch(site.api, purge=True)
    assert f"{half}.wav" in site.objects and not site.deleted
    assert I.sync(site.api, make=False) == 0  # sync knows it's here
    assert jo not in capsys.readouterr().out  # a singer's whole id opens their page: never printed


def test_sync_leaves_damaged_and_half_sent_takes_and_says_so_once(site, capsys):
    jo = site.add_singer(online(site), name="Jo")
    site.add_sung(jo, "20260926T231501Z", corrupt=True)
    half = site.add_sung(jo, "20260926T231601Z", rand="bcdefg")
    del site.objects[f"{half}.json"]
    memo = I.memory()
    capsys.readouterr()
    assert I.sync(site.api, make=False, memo=memo) == 1
    assert "doesn't match its sidecar" in capsys.readouterr().out
    assert I.sync(site.api, make=False, memo=memo) == 0
    assert len(site.objects) == 3 and not site.deleted and K.takes(SONG) == []


def test_one_sync_at_a_time(site):
    with I.alone():
        with pytest.raises(SystemExit, match="another sync"), I.alone():
            pass  # a second, while the first runs: refused
    with I.alone():  # the first has finished: free again
        pass


def test_watch_carries_on_after_a_failed_round_and_stops_on_ctrl_c(site, monkeypatch, capsys):
    naps = []

    def nap(seconds):
        naps.append(seconds)
        site.broken = len(naps) == 1  # the second round fails
        if len(naps) == 3:
            raise KeyboardInterrupt

    monkeypatch.setattr(I.time, "sleep", nap)
    jo = site.add_singer(online(site), name="Jo")
    site.add_sung(jo, "20260926T231501Z")
    capsys.readouterr()
    I.watch(site.api, 30, make=False)
    lines = capsys.readouterr().out.splitlines()
    assert naps == [30, 30, 30] and len(lines) == 4
    assert "recordings/jo/" in lines[0]  # the first round keeps the take
    assert "didn't finish" in lines[1] and "503" in lines[1]  # the second fails, and says so
    assert lines[2] == "." and lines[3].endswith("stopped")  # the third has nothing to do; then Ctrl-C
    assert not I.Say.clock
