"""The karaoke plays the guide a singer chooses and each take says which it heard (tools/karaoke.py)."""

import io
import json
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import guides as M  # noqa: E402  (tools/guides.py)
import karaoke  # noqa: E402  (tools/karaoke.py)
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import takes as K  # noqa: E402  (tools/takes.py)

from songbird import genome as G  # noqa: E402

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    return tmp_path


def short(form=("verse",)):
    g = G.load(H)
    return replace(g, seed_params={**g.seed_params, "form": list(form)})


def test_the_karaoke_says_which_guide_a_take_heard(workspace, monkeypatch):
    genome = short()
    monkeypatch.setattr(karaoke.Karaoke, "genome_path", H, raising=False)
    monkeypatch.setattr(karaoke.Karaoke, "genome", genome)
    server = ThreadingHTTPServer(("127.0.0.1", 0), karaoke.Karaoke)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/guide.wav?mix=melody") as r:
            digest = r.headers["X-Guide-Score"]
            assert r.headers["Content-Type"] == "audio/wav" and r.read(4) == b"RIFF"
        with urllib.request.urlopen(f"{base}/karaoke.js") as r:
            assert b"export function autoSync" in r.read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/guide.wav?mix=kazoo")
        assert e.value.code == 404

        wav = io.BytesIO()
        sf.write(wav, np.zeros(48000), 48000, format="WAV", subtype="PCM_16")

        def take(**query):
            q = "&".join(f"{k}={v}" for k, v in query.items())
            req = urllib.request.Request(f"{base}/take?{q}", data=wav.getvalue(), headers={"Content-Type": "audio/wav"})
            try:
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as err:
                return json.loads(err.read())

        kept = take(singer="Jo", mix="melody", guide=digest, shift_ms=12)
        side = json.loads((workspace / kept["path"]).with_suffix(".json").read_text())
        assert (side["mix"], side["guide"], side["shift_ms"]) == ("melody", digest, 12.0)
        assert "changed" in take(singer="Jo", mix="melody", guide="0" * 12)["error"]  # sung to a guide that's gone
        assert "mix" in take(singer="Jo", mix="kazoo")["error"]
    finally:
        server.shutdown()
        server.server_close()
