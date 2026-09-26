"""End to end under `wrangler dev`: the site built for H, an invitation, a take, fetched, the invitation closed.

    uv run pytest web/sing/test -q          # not in the main run: it needs node_modules (cd web/sing && npm install)

Builds the site into a temporary folder (web/sing/public is left alone), runs the
worker on it with local, throwaway KV and R2 and a random admin token, then plays
the singer's part over HTTP with a synthetic take (the melody guide itself, in mono
at 48 kHz) and the artist's with tools/invite.py. The take is fetched into
recordings/<a test singer>/, checked, and deleted, with the test's own guide score
left pinned in recordings/guides/ like any other.
"""

import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import resample_poly

WEB = Path(__file__).parent.parent
ROOT = WEB.parent.parent
WRANGLER = WEB / "node_modules" / ".bin" / "wrangler"
H = ROOT / "songs" / "h-now-its-by-you.json"
sys.path.insert(0, str(ROOT / "tools"))
import guides as M  # noqa: E402  (tools/guides.py)
import invite as I  # noqa: E402  (tools/invite.py)
import sing_site as W  # noqa: E402  (tools/sing_site.py)
import takes as K  # noqa: E402  (tools/takes.py)

pytestmark = pytest.mark.skipif(not WRANGLER.exists() or not shutil.which("ffmpeg"),
                                reason="needs web/sing/node_modules (npm install) and ffmpeg")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sing")
    song = W.build(H, tmp / "public")
    config = (WEB / "wrangler.toml").read_text()
    config = config.replace('main = "src/worker.js"', f'main = "{WEB / "src" / "worker.js"}"')
    config = config.replace('directory = "./public"', f'directory = "{tmp / "public"}"')
    (tmp / "wrangler.toml").write_text(config)
    admin, port = secrets.token_urlsafe(32), free_port()
    server = subprocess.Popen(
        [str(WRANGLER), "dev", "-c", str(tmp / "wrangler.toml"), "--port", str(port), "--ip", "127.0.0.1",
         "--persist-to", str(tmp / "state"), "--var", f"ADMIN_TOKEN:{admin}", "--show-interactive-dev-session=false"],
        cwd=WEB, env={**os.environ, "WRANGLER_SEND_METRICS": "false"}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                with urllib.request.urlopen(base + "/", timeout=2):
                    break
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                time.sleep(0.5)
        else:
            pytest.fail("wrangler dev didn't start")
        yield {"base": base, "admin": I.Site(base, admin), "song": song, "public": tmp / "public"}
    finally:
        server.terminate()
        server.wait(timeout=30)


def request(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def guide_take(seconds: float = 30.0, rate: int = 48000) -> bytes:
    """A synthetic take: the melody guide itself, mono, at a phone's rate, as the page writes it."""
    x, sr = sf.read(M.mix_path(H.stem, "melody"))
    mono = resample_poly(x.mean(axis=1)[: int(seconds * sr)], rate // 300, sr // 300)
    pcm = np.clip(np.round(mono * 32767), -32768, 32767).astype("<i2").tobytes()
    head = b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
    head += (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + rate.to_bytes(4, "little")
    head += (rate * 2).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
    return head + b"data" + len(pcm).to_bytes(4, "little") + pcm


def sidecar(song: dict, **extra) -> str:
    info = {"song": song["song"], "guide": song["guide"], "mix": "melody", "rate": 48000, "name": "Test Singer E2E",
            "credit": False, "consent": {"agreed": True, "at": datetime.now(timezone.utc).isoformat(), "text": song["consent"]},
            "shift_ms": 0, "auto_ms": 0, "device_ms": 0, "decode_ms": 0, "out_ms": 25, "in_ms": 5, **extra}
    return base64.urlsafe_b64encode(json.dumps(info).encode()).decode().rstrip("=")


def put_take(base, token, body, info, kind="audio/wav"):
    return request(f"{base}/api/take/{token}", "PUT", body, {"Content-Type": kind, "X-Take-Info": info})


def test_an_invitation_from_link_to_recordings(site):
    base, admin, song = site["base"], site["admin"], site["song"]
    token = I.new(admin, 1, "e2e", 1, 3)[0]["token"]

    # the singer's side: the page, the song, a guide
    code, headers, page = request(f"{base}/i/{token}")
    assert code == 200 and b'data-digest="' + song["consent"].encode() in page
    assert "script-src 'self'" in headers["Content-Security-Policy"] and headers["Referrer-Policy"] == "no-referrer"
    state = json.loads(request(f"{base}/api/invite/{token}")[2])
    assert (state["state"], state["limit"], state["takes"]) == ("open", 3, 0)
    code, _, body = request(f"{base}/api/song/{token}")
    assert code == 200 and json.loads(body)["guide"] == song["guide"]
    code, headers, mp3 = request(f"{base}/api/guide/{token}/melody")
    assert code == 200 and headers["Content-Type"] == "audio/mpeg"
    assert mp3 == (site["public"] / "song" / "melody.mp3").read_bytes()

    # nothing private without an open invitation, and nothing but what's asked for
    for path in ("/song/song.json", "/song/melody.mp3", "/index.html", "/.songbird-site", f"/api/guide/{'A' * 24}/melody",
                 f"/api/song/{token}x", "/api/admin/invites", f"/api/admin/take/takes/{token}/../../x.wav"):
        assert request(base + path)[0] in (401, 404), path

    # the ways a take is refused (on an invitation of their own: six tries a minute each)
    take = guide_take()
    other = I.new(admin, 1, "e2e refusals", 1, 3)[0]["token"]
    assert put_take(base, other, take, sidecar(song), kind="text/plain")[0] == 415
    assert put_take(base, other, take[:-3], sidecar(song))[0] == 400  # not a whole WAV
    stale = {"agreed": True, "at": "2026-10-01T10:00:00Z", "text": "0" * 12}  # agreed to another release
    assert put_take(base, other, take, sidecar(song, consent=stale))[0] == 400
    assert put_take(base, other, take, sidecar(song, mix="kazoo"))[0] == 400
    assert put_take(base, other, take, sidecar(song, rate=44100))[0] == 400
    assert put_take(base, other, take, "not-json")[0] == 400
    assert put_take(base, other, take, sidecar(song))[0] == 429  # a seventh try within the minute
    assert put_take(base, "B" * 24, take, sidecar(song))[0] == 404
    assert json.loads(request(f"{base}/api/invite/{other}")[2])["takes"] == 0

    # a take
    code, _, body = put_take(base, token, take, sidecar(song))
    assert code == 200 and json.loads(body) == {"ok": True, "take": 1, "limit": 3}
    assert json.loads(request(f"{base}/api/invite/{token}")[2])["takes"] == 1

    # the artist's side: fetched into recordings/, pinned to the guide, gone from the server
    who = f"test-e2e-{secrets.token_hex(3)}"
    try:
        kept = I.fetch(admin, invite=token, singer=who)
        assert len(kept) == 1
        t = kept[0]
        assert t.path.parent == K.RECORDINGS / who and t.path.read_bytes() == take
        assert (t.song, t.guide, t.info["mix"]) == (H.stem, song["guide"], "melody")
        assert (t.info["source"], t.info["rate"]) == ("online", 48000)
        assert t.info["consent"]["text"] == song["consent"] and t.info["credit"] is False
        assert K.guide_score(H.stem, t.guide) is not None  # it can be measured against what was heard
        assert admin.call("GET", f"/api/admin/takes?invite={token}")["takes"] == []
        # fetching frees no room: the invitation still counts what it sent
        assert json.loads(request(f"{base}/api/invite/{token}")[2])["takes"] == 1
    finally:
        shutil.rmtree(K.RECORDINGS / who, ignore_errors=True)

    # "I'm done" closes it
    assert json.loads(request(f"{base}/api/done/{token}", "POST")[2]) == {"state": "done"}
    assert json.loads(request(f"{base}/api/invite/{token}")[2])["state"] == "done"
    assert request(f"{base}/i/{token}")[0] == 410
    assert put_take(base, token, take, sidecar(song))[0] == 410
    assert request(f"{base}/api/guide/{token}/melody")[0] == 410
    listed = {inv["token"]: inv for inv in admin.call("GET", "/api/admin/invites")["invites"]}
    assert listed[token]["state"] == "done" and listed[token]["sent"] == 1


def test_an_invitation_takes_no_more_than_its_limit_and_can_be_revoked(site):
    base, admin, song = site["base"], site["admin"], site["song"]
    token = I.new(admin, 1, "", 1, 1)[0]["token"]
    take = guide_take(seconds=5.0)
    assert put_take(base, token, take, sidecar(song))[0] == 200
    code, _, body = put_take(base, token, take, sidecar(song))
    assert code == 403 and json.loads(body)["error"] == "limit"
    for part in admin.call("GET", f"/api/admin/takes?invite={token}")["takes"]:  # clean up the take
        for kind in ("wav", "json"):
            admin.call("DELETE", f"/api/admin/take/{part[kind]['key']}")
    I.revoke(admin, token)
    assert request(f"{base}/i/{token}")[0] == 410
    assert json.loads(request(f"{base}/api/invite/{token}")[2])["state"] == "revoked"
