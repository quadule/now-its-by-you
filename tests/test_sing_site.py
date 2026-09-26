"""tools/sing_site.py: the page for singers anywhere, built from one guide score."""

import json
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import guides as M  # noqa: E402  (tools/guides.py)
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import sing_site as W  # noqa: E402  (tools/sing_site.py)
import takes as K  # noqa: E402  (tools/takes.py)

ROOT = Path(__file__).parent.parent


def test_the_release_is_its_text_and_nothing_else():
    text = """<!-- a note for the artist, never shown -->
**By ticking the box, I agree that:**

- my *takes* may be measured
  and kept, one item over two lines
- <script>alert(1)</script> is only text

## Credit
Credited as I choose.
"""
    out = W.consent_html(text)
    assert "note for the artist" not in out
    assert "<p><strong>By ticking the box, I agree that:</strong></p>" in out
    assert "<li>my <em>takes</em> may be measured and kept, one item over two lines</li>" in out
    assert "&lt;script&gt;" in out and "<script>" not in out
    assert "<h3>Credit</h3><p>Credited as I choose.</p>" in out
    assert W.digest(out) == W.digest(W.consent_html(text)) and len(W.digest(out)) == 12


def test_the_release_on_file_renders():
    out = W.consent_html((W.WEB / "consent.md").read_text())
    assert out.count("<li>") >= 4 and "CC0" in out and "<!--" not in out


def opening(rate, seconds=3.0):
    x = np.zeros(int(rate * seconds))
    for k in range(8):
        a = int((0.6 + 0.3 * k) * rate)
        i = np.arange(int(0.25 * rate))
        x[a : a + len(i)] += 0.3 * np.sin(2 * np.pi * (220 + 30 * k) * i / rate) * np.exp(-i / (0.1 * rate))
    return x


def test_silence_a_decoder_put_in_front_is_found():
    reference = W.envelope(opening(44100), 44100)
    assert len(reference) == int(W.OPENING / W.FRAME)
    for rate in (44100, 48000):
        at = opening(rate)
        assert W.decode_offset(at, rate, reference) == 0.0
        late = np.concatenate([np.zeros(round(1105 * rate / 44100)), at])
        assert W.decode_offset(late, rate, reference) == pytest.approx(1105 / 44100, abs=5e-4)
    noise = np.random.default_rng(0).standard_normal(48000 * 3)
    assert W.decode_offset(noise, 48000, reference) == 0.0


def test_an_output_folder_is_cleared_only_if_this_tool_made_it(tmp_path):
    mine = tmp_path / "site"
    W.clear(mine)
    (mine / "old.txt").write_text("stale")
    W.clear(mine)
    assert not (mine / "old.txt").exists() and (mine / W.MARK).exists()
    other = tmp_path / "somebody-elses"
    other.mkdir()
    (other / "precious.txt").write_text("keep me")
    with pytest.raises(SystemExit, match="choose another"):
        W.clear(other)
    assert (other / "precious.txt").read_text() == "keep me"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_the_site_is_built_from_one_guide_score(tmp_path, monkeypatch):
    for mod, name in ((T, "ROOT"), (K, "ROOT")):
        monkeypatch.setattr(mod, name, tmp_path)
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    genome = json.loads((ROOT / "songs" / "h-now-its-by-you.json").read_text())
    genome["seed_params"]["form"] = ["intro", "verse"]
    path = tmp_path / "h-short.json"
    path.write_text(json.dumps(genome))

    out = tmp_path / "public"
    song = W.build(path, out)
    score = M.full_paths("h-short")[1]
    assert song["guide"] == K.digest(score) and K.guide_score("h-short", song["guide"])  # pinned for fetched takes
    assert song["song"] == "h-short" and song["default"] == "melody" and list(song["mixes"]) == ["melody", "full"]
    assert song["lines"] and song["tempo"] == json.loads(score.read_text())["tempo"]
    for mix, m in song["mixes"].items():
        assert (out / "song" / m["file"]).stat().st_size == m["bytes"] > 10000
        assert len(m["env"]) == int(W.OPENING / W.FRAME) and m["rate"] == 44100
    page = (out / "index.html").read_text()
    shown = re.search(r'data-digest="([0-9a-f]{12})">(.*?)</div>', page, re.S)
    assert shown and shown[1] == song["consent"] == W.digest(shown[2])  # the digest is of the text on the page
    for name in ("sing.js", "sing.css", "karaoke.js", "recorder.js", "robots.txt", "favicon.svg"):
        assert (out / name).exists()
    assert (out / "karaoke.js").read_text() == (ROOT / "tools" / "karaoke.js").read_text()
    assert (out / ".assetsignore").read_text().split() == [W.MARK, ".assetsignore"]
