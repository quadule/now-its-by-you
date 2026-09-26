"""The karaoke plays the guide a singer chooses and each take says which it heard (tools/karaoke.py)."""

import io
import json
import sys
import threading
import urllib.error
import urllib.request
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


def short(folder: Path, form=("verse",)) -> Path:
    """H's genome with a seed rendition only a section long, as a file the karaoke can reload."""
    data = json.loads(H.read_text())
    data["seed_params"]["form"] = list(form)
    path = folder / "h-short.json"
    path.write_text(json.dumps(data))
    return path


def test_the_karaoke_says_which_guide_a_take_heard(workspace, monkeypatch):
    path = short(workspace)
    monkeypatch.setattr(karaoke.Karaoke, "genome_path", path, raising=False)
    monkeypatch.setattr(karaoke.Karaoke, "genome", G.load(path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), karaoke.Karaoke)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/guide.wav?mix=melody") as r:
            digest = r.headers["X-Guide-Score"]
            assert r.headers["Content-Type"] == "audio/wav" and r.read() == M.mix_path("h-short", "melody").read_bytes()
        with urllib.request.urlopen(f"{base}/guide.wav") as r:  # asked for as before there was a choice: the full guide
            assert r.headers["X-Guide-Score"] == digest and r.read() == M.mix_path("h-short", "full").read_bytes()
        with urllib.request.urlopen(f"{base}/lyrics.json") as r:
            words = json.loads(r.read())
            assert words["guide"] == digest and words["beats"] and words["lines"]
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
        assert K.guide_score("h-short", digest)  # the score it was sung to is kept beside the takes
        assert "changed" in take(singer="Jo", mix="melody", guide="0" * 12)["error"]  # sung to a guide that's gone
        assert "changed" in take(singer="Jo", mix="melody")["error"]  # or to one it doesn't name
        assert "which guide" in take(singer="Jo", guide=digest)["error"]  # a take says which mix it heard
        assert "which guide" in take(singer="Jo", mix="kazoo", guide=digest)["error"]
        # sung to an earlier render of the song whose score is still kept: kept, and pinned to it
        (K.GUIDES / "h-short.abcdefabcdef.score.json").write_text("{}")
        older = take(singer="Jo", mix="full", guide="abcdefabcdef")
        assert json.loads((workspace / older["path"]).with_suffix(".json").read_text())["guide"] == "abcdefabcdef"
    finally:
        server.shutdown()
        server.server_close()
