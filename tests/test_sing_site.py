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
def test_the_site_has_a_guide_for_every_spec(tmp_path, monkeypatch):
    for mod, name in ((T, "ROOT"), (K, "ROOT")):
        monkeypatch.setattr(mod, name, tmp_path)
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")
    monkeypatch.setattr(M, "SETS", tmp_path / "sets")  # none: the song's own words and form
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    genome = json.loads((ROOT / "songs" / "h-now-its-by-you.json").read_text())
    genome["seed_params"]["form"] = ["verse"]
    path = tmp_path / "h-short.json"
    path.write_text(json.dumps(genome))
    # the pages as they'll be, with the words release in them too
    web = tmp_path / "web"
    shutil.copytree(W.WEB / "page", web / "page")
    for name in ("consent.md", "words-release.md"):
        shutil.copyfile(W.WEB / name, web / name)
    index = (web / "page" / "index.html").read_text()
    if "{{WORDS_RELEASE}}" not in index:
        index = index.replace("</body>", '<div id="wordsRelease" data-digest="{{WORDS_DIGEST}}">{{WORDS_RELEASE}}</div></body>')
    (web / "page" / "index.html").write_text(index)
    monkeypatch.setattr(W, "WEB", web)

    out = tmp_path / "public"
    with pytest.raises(SystemExit, match="nothing called"):
        W.build(path, out, keys=[3])
    done = []
    song = W.build(path, out, keys=[0, -2], tempos=[100], jobs=2, progress=lambda *a: done.append(a[0]))
    assert sorted(done) == ["song.k-2.t100", "song.k0.t100"]  # each in a process of its own
    assert (song["v"], song["song"], song["mixes"], song["keys"], song["tempos"]) == (2, "h-short", ["melody", "full"],
                                                                                      [-2, 0], [100])
    assert song["sets"] == [{"id": "song", "name": "The song", "about": M.SONG["about"]}]
    assert song["default"] == {"set": "song", "key": 0, "tempo": 100, "mix": "melody"}
    assert list(song["guides"]) == ["song.k-2.t100", "song.k0.t100"]
    for spec, guide in song["guides"].items():
        score = M.spec_path("h-short", spec, "score")
        assert guide["guide"] == K.digest(score) and K.guide_score("h-short", guide["guide"])  # pinned for fetched takes
        words = json.loads((out / "song" / guide["lyrics"]).read_text())
        assert words["guide"] == guide["guide"] and words["spec"]["id"] == spec and words["lines"]
        assert [s["window"] for s in words["sections"] if s["sung"]] and words["duration"] == pytest.approx(guide["duration"], abs=1e-3)
        for mix, m in guide["mixes"].items():
            assert m["file"] == f"{spec}.{mix}.mp3" and (out / "song" / m["file"]).stat().st_size == m["bytes"] > 10000
            assert m["rate"] == 44100 and "env" not in m  # song.json stays small: a phone reads it first
            assert len(words["opening"][mix]["env"]) == int(W.OPENING / W.FRAME) and words["opening"][mix]["frame"] == W.FRAME
        assert guide["mixes"]["melody"]["bytes"] < 0.8 * guide["mixes"]["full"]["bytes"]  # the melody at 64 kbps
    assert song["max_seconds"] == round(max(g["duration"] for g in song["guides"].values()) + 60)
    page = (out / "index.html").read_text()
    shown = re.search(r'data-digest="([0-9a-f]{12})">(.*?)</div>', page, re.S)
    assert shown and shown[1] == song["consent"] == W.digest(shown[2])  # the digest is of the text on the page
    assert song["words_release"] == W.digest(W.consent_html((web / "words-release.md").read_text()))
    assert f'data-digest="{song["words_release"]}"' in page and "{{" not in page
    assert (K.GUIDES / f"release.{song['consent']}.html").exists()  # each release as people read it
    assert (K.GUIDES / f"words-release.{song['words_release']}.html").exists()
    for name in ("sing.js", "sing.css", "karaoke.js", "recorder.js", "robots.txt", "favicon.svg"):
        assert (out / name).exists()
    assert (out / "karaoke.js").read_text() == (ROOT / "tools" / "karaoke.js").read_text()
    assert (out / ".assetsignore").read_text().split() == [W.MARK, ".assetsignore"]
    assert W.size(out) == sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) - sum(
        (out / n).stat().st_size for n in (W.MARK, ".assetsignore"))
    # the WAVs are let go once encoded; the MP3s are kept, and used again while what they were made from holds
    assert not M.spec_path("h-short", "song.k0.t100", "full").exists()
    again = W.build(path, out, keys=[0], tempos=[100], jobs=1)
    assert not M.spec_path("h-short", "song.k0.t100", "full").exists()  # nothing rendered
    assert again["guides"]["song.k0.t100"] == song["guides"]["song.k0.t100"]
    W.build(path, out, keys=[0], tempos=[100], jobs=1, keep_wavs=True, melody_bitrate="48k")  # another bitrate: made again
    assert M.spec_path("h-short", "song.k0.t100", "full").exists()


def test_a_set_that_cant_be_sung_stops_the_build_before_it_starts(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")
    monkeypatch.setattr(M, "SETS", tmp_path / "sets")
    (tmp_path / "sets").mkdir()
    (tmp_path / "sets" / "h-now-its-by-you.json").write_text(json.dumps(
        {"sets": [{"id": "a", "form": ["verse"], "words": {"verses": [{"id": "wire", "slots": {}}]}}]}))
    with pytest.raises(SystemExit, match="set a can't be sung: .*2, 3 or 4 verses"):
        W.specs(ROOT / "songs" / "h-now-its-by-you.json")


def test_a_melody_that_wont_decode_in_time_is_encoded_at_the_full_guides_rate(tmp_path, monkeypatch):
    tried = []

    def encode(wav, mp3, bitrate):
        tried.append(bitrate)
        if bitrate == "64k":
            raise W.OutOfTime("late")
        return {"bitrate": bitrate}

    monkeypatch.setattr(W, "encode", encode)
    assert W.encode_first(tmp_path / "x.wav", tmp_path / "x.mp3", ("64k", "96k")) == {"bitrate": "96k"}
    assert tried == ["64k", "96k"]
    with pytest.raises(W.OutOfTime):
        W.encode_first(tmp_path / "x.wav", tmp_path / "x.mp3", ("64k",))
