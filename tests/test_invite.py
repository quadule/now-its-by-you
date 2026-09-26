"""tools/invite.py against a fake of the site's admin API (web/sing/src/worker.js)."""

import hashlib
import io
import json
import secrets
import subprocess
import sys
import threading
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


class FakeSite:
    """The admin API's shape, in memory: invites and the objects of a bucket."""

    def __init__(self):
        self.invites, self.objects, self.deleted = {}, {}, []

    def add_take(self, token: str, stamp: str, name: str = "", mix: str = "melody", corrupt: bool = False) -> str:
        wav = io.BytesIO()
        sf.write(wav, np.zeros(48000 * 4), 48000, format="WAV", subtype="PCM_16")
        data = wav.getvalue()
        key = f"takes/{token}/{stamp}-abcdef"
        side = {"song": "h-now-its-by-you", "guide": GUIDE, "mix": mix, "rate": 48000, "seconds": 4.0, "name": name,
                "credit": bool(name), "consent": {"agreed": True, "at": "2026-10-01T10:00:00.000Z", "text": "896e20c8603e"},
                "shift_ms": 12, "auto_ms": 10, "device_ms": 40, "decode_ms": 0, "out_ms": 29, "in_ms": 10,
                "received": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}.000Z",
                "bytes": len(data), "sha256": hashlib.sha256(data + (b"x" if corrupt else b"")).hexdigest(), "take": 1}
        self.objects[f"{key}.wav"] = data
        self.objects[f"{key}.json"] = json.dumps(side).encode()
        return key

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
                base = f"http://{self.headers['Host']}"
                if method == "POST" and path == "invites":
                    body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    made = []
                    for _ in range(body["count"]):
                        token = secrets.token_urlsafe(18)
                        site.invites[token] = {"created": "2026-10-01T09:00:00.000Z", "expires": "2026-10-08T09:00:00.000Z",
                                               "limit": body["limit"], "note": body["note"], "state": "open"}
                        made.append({"token": token, "url": f"{base}/i/{token}", **site.invites[token]})
                    return self.reply(200, {"invites": made})
                if method == "GET" and path == "invites":
                    out = []
                    for token, inv in site.invites.items():
                        waiting = sum(k.startswith(f"takes/{token}/") and k.endswith(".json") for k in site.objects)
                        out.append({"token": token, "url": f"{base}/i/{token}", **inv, "takes": waiting, "sent": waiting})
                    return self.reply(200, {"invites": out})
                if method == "POST" and path.startswith("revoke/"):
                    site.invites[path[7:]]["state"] = "revoked"
                    return self.reply(200, {"state": "revoked"})
                if method == "GET" and path == "takes":
                    only = parse_qs(url.query).get("invite", [None])[0]
                    takes = {}
                    for key, data in sorted(site.objects.items()):
                        if only and not key.startswith(f"takes/{only}/"):
                            continue
                        tid = key.rsplit(".", 1)[0]
                        t = takes.setdefault(tid, {"id": tid, "invite": key.split("/")[1]})
                        t[key.rsplit(".", 1)[1]] = {"key": key, "size": len(data), "uploaded": "2026-10-01T10:00:00.000Z"}
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
                return self.reply(404, {"error": "unknown", "message": "No such thing."})

            def do_GET(self):
                self.route("GET")

            def do_POST(self):
                self.route("POST")

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


def test_new_invites_are_links_and_list_shows_them(site, capsys):
    made = I.new(site.api, 2, "choir, Tuesday", 7, 30)
    out = capsys.readouterr().out.split()
    assert out == [m["url"] for m in made] and all("/i/" in u for u in out)
    listed = I.listing(site.api)
    assert {inv["token"] for inv in listed} == {m["token"] for m in made}
    I.revoke(site.api, made[0]["token"])
    assert site.invites[made[0]["token"]]["state"] == "revoked"


def test_fetch_keeps_takes_like_the_karaoke_and_empties_the_server(site, tmp_path, capsys):
    token = I.new(site.api, 1, "Ana from choir", 7, 30)[0]["token"]
    K.GUIDES.mkdir(parents=True)
    (K.GUIDES / f"h-now-its-by-you.{GUIDE}.score.json").write_text("{}")  # pinned when the site was built
    named = site.add_take(token, "20261001T100000Z", name="Ana María")
    site.add_take(token, "20261001T100500Z", name="", mix="full")  # no name: the invitation's note names the folder
    kept = I.fetch(site.api)
    assert len(kept) == 2 and not site.objects  # both here, and gone from the server
    by = {t.who: t for t in kept}
    assert set(by) == {"ana-mar-a", "ana-from-choir"}
    ana = by["ana-mar-a"]
    assert (ana.singer, ana.song, ana.guide, ana.use) == ("Ana María", "h-now-its-by-you", GUIDE, True)
    assert ana.info["mix"] == "melody" and by["ana-from-choir"].info["mix"] == "full"
    assert ana.info["source"] == "online" and ana.info["remote"] == named and ana.info["invite"] == token[:6]
    assert ana.info["consent"]["agreed"] and ana.info["credit"] is True and by["ana-from-choir"].info["credit"] is False
    assert (ana.info["shift_ms"], ana.info["device_ms"], ana.info["rate"]) == (12, 40, 48000)
    assert sf.info(ana.path).samplerate == 48000
    assert K.takes("h-now-its-by-you", "ana-mar-a")[0].path == ana.path  # the karaoke and phrasing tools see it
    assert "isn't in" not in capsys.readouterr().out  # its guide score is here to measure it against
    assert I.fetch(site.api) == []  # nothing left to fetch


def test_fetch_keep_leaves_takes_and_a_later_fetch_clears_them(site, capsys):
    token = I.new(site.api, 1, "", 7, 30)[0]["token"]
    site.add_take(token, "20261001T100000Z")
    kept = I.fetch(site.api, keep=True)
    assert kept[0].who == K.slug(f"singer-{token[:6]}")  # no name, no note: the invitation names the folder
    assert len(site.objects) == 2  # still on the server
    assert "isn't in" in capsys.readouterr().out  # no guide score here: said so
    assert I.fetch(site.api) == [] and not site.objects  # already here: only cleared from the server
    assert len(K.takes("h-now-its-by-you")) == 1


def test_fetch_one_invitation_under_a_chosen_name(site):
    a, b = (inv["token"] for inv in I.new(site.api, 2, "", 7, 30))
    site.add_take(a, "20261001T100000Z", name="Jo")
    site.add_take(b, "20261001T100000Z", name="Sam")
    kept = I.fetch(site.api, invite=a, singer="Test Singer")
    assert [t.who for t in kept] == ["test-singer"] and len(site.objects) == 2


def test_a_damaged_or_half_sent_take_stays_on_the_server(site, capsys):
    token = I.new(site.api, 1, "", 7, 30)[0]["token"]
    site.add_take(token, "20261001T100000Z", corrupt=True)
    orphan = site.add_take(token, "20261001T110000Z")
    del site.objects[f"{orphan}.json"]
    assert I.fetch(site.api) == []
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
