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
    for name in ("sing.js", "sing.css", "identity.css", "karaoke.js", "recorder.js", "robots.txt", "favicon.svg"):
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
    assert song["guides"]["song.k0.t100"]["was"] == []  # nothing before it

    # the voice says a word another way, not when: takes sung to the guide before, from a page loaded before
    # this build is published, are still taken (web/sing/src/lib.js specOf), and measured against what was heard
    genome["lexicon"] = {**genome.get("lexicon", {}), "numbers": "N AH1 M B ER0 Z"}
    path.write_text(json.dumps(genome))
    before = song["guides"]["song.k0.t100"]["guide"]
    later = W.build(path, out, keys=[0], tempos=[100], jobs=1)["guides"]["song.k0.t100"]
    assert later["guide"] != before and later["was"] == [before]
    assert json.loads((out / "song" / "worker.json").read_text())["guides"]["song.k0.t100"]["was"] == [before]
    # a guide timed otherwise is no longer taken: the takes' places in the song would be wrong
    genome["seed_params"]["form"] = ["verse", "refrain"]
    path.write_text(json.dumps(genome))
    assert W.build(path, out, keys=[0], tempos=[100], jobs=1)["guides"]["song.k0.t100"]["was"] == []


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


def test_a_site_being_built_never_replaces_the_one_there_until_it_is_whole(tmp_path, monkeypatch):
    """A deploy while a build runs publishes the site built before, never part of this one: the new one
    is built beside it (where wrangler never looks) and put in its place only once it's whole."""
    out = tmp_path / "public"
    W.clear(out)  # the site built before, as the last build left it
    (out / "song").mkdir()
    (out / "song" / "song.json").write_text('{"built": "before"}\n')
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")

    def fails(job):
        assert Path(job["out"]) == W.aside(out) and not Path(job["out"], "song", "song.json").exists()
        raise RuntimeError("a render failed")

    monkeypatch.setattr(W, "render", fails)
    with pytest.raises(RuntimeError, match="render failed"):
        W.build(ROOT / "songs" / "h-now-its-by-you.json", out, sets=["a"], keys=[0], tempos=[100], jobs=1)
    assert (out / "song" / "song.json").read_text() == '{"built": "before"}\n' and (out / W.MARK).exists()
    built, site = tmp_path / "built", tmp_path / "site"
    W.clear(built)
    (built / "new.txt").write_text("whole")
    W.publish(built, site)  # nothing there yet
    assert (site / "new.txt").exists() and not built.exists()
    W.clear(built)
    W.publish(built, site)  # the one there before goes
    assert not (site / "new.txt").exists() and (site / W.MARK).exists() and not site.with_name("site.old").exists()


def test_the_seed_pages_words_are_timed_as_the_file_sang_them(tmp_path):
    """The seed page shows a packed render's words as it plays: its score laid again from what the packet
    carries, a person's phrasing (sung early) and all, matching the score the render itself wrote."""
    import karaoke  # tools/karaoke.py
    from songbird import cli, phrasing as P
    from songbird.genome import load

    H = ROOT / "songs" / "h-now-its-by-you.json"
    genome = load(H)
    way = {pid: tuple(P.Gesture(early=-0.0625) for _ in phrase.sung) for pid, phrase in genome.phrases.items()}
    phrasing = tmp_path / "early.json"
    phrasing.write_text(json.dumps(P.to_json(way)))
    packed, plain = tmp_path / "packed.flac", tmp_path / "plain.flac"
    for out, pack in ((packed, ["--pack"]), (plain, [])):
        assert cli.main(["render", str(H), "--form", "tag", "--out", str(out), "--phrasing", str(phrasing), *pack]) == 0
    phrasing.unlink()  # the packet carries what it needs
    timed = W.seed_words(packed)
    score = json.loads(plain.with_suffix(".score.json").read_text())
    lines = karaoke.lyrics(score, genome.title, 0)["lines"]
    assert [[s[0] for s in line[2]] for line in timed["lines"]] == [[s["text"] for s in line["syllables"]] for line in lines]
    assert [s[1] for line in timed["lines"] for s in line[2]] == pytest.approx(
        [s["start"] for line in lines for s in line["syllables"]], abs=1e-3)
    assert timed["duration"] == pytest.approx(json.loads(plain.with_suffix(".json").read_text())["duration"], abs=1e-3)
    assert W.seed_words(plain) is None  # no packet, nothing to lay it from
