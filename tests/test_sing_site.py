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


def packed(path: Path, seed: int, monkeypatch) -> str:
    """A small packed render, packed before the program embedded the cover; its audio id."""
    from songbird import pack
    from songbird.synth import master

    pcm = (np.random.default_rng(seed).normal(0, 3000, (22050, 2))).astype("<i2")
    master.write_flac(path, pcm, 44100, cover=False)
    record = {"id": master.pcm_sha256(pcm), "title": "Now It's by You", **pack.lineage(None)}
    with monkeypatch.context() as m:
        m.setattr(pack.artwork, "embed", lambda audio, description=None: audio)
        pack.pack(path, record, ROOT / "songs" / "h-now-its-by-you.json")
    return record["id"]


def edition(n: int, date: str, audio: str, released: Path, render: Path | None = None, kept: Path | None = None,
            **more) -> dict:
    """An edition as web/sing/editions.json lists one: its file as released (the bytes at `released`), served
    from a kept copy or made from its render."""
    return {"title": f"Version {n}", "date": date, "note": f"What changed in {n} & why.", "audio": audio,
            "file": {"sha256": W.sha256(released), "bytes": released.stat().st_size, **({"path": str(kept)} if kept else {})},
            **({"render": {"path": str(render), "sha256": W.sha256(render), "bytes": render.stat().st_size}} if render else {}),
            "program": "a" * 64, "python": "3.12", "source": {"commit": "10dc1e0bba140e5dfed9217f4ddcc90b4d531004"},
            "command": f"uv run songbird render --seed {n}", "credit": f"{n} sung takes", **more}


def covered(render: Path) -> Path:
    """The render as it's released: given the song's cover (pack.with_cover)."""
    from songbird import pack

    out = render.with_name(render.stem + ".released.flac")
    pack.with_cover(render, out)
    return out


def test_the_seed_pages_file_carries_the_cover_with_its_packet_and_id(tmp_path, monkeypatch):
    """The public file is a copy of the render given the song's cover (pack.with_cover): the render itself is
    left alone, and the copy has the same samples, the same packet and so the same id."""
    from songbird import artwork, pack

    render = tmp_path / "contest.flac"
    made = packed(render, 1, monkeypatch)
    released = covered(render)
    before = render.read_bytes()
    manifest = tmp_path / "editions.json"
    manifest.write_text(json.dumps({"editions": [edition(1, "2026-09-28", made, released, render=render)]}))
    released.unlink()  # made again from the render, byte for byte
    out = tmp_path / "public"
    out.mkdir()
    (out / "seed.html").write_text("{{SEED_FILE}} {{SEED_MB}} {{SEED_WORDS}}")
    monkeypatch.setattr(W, "seed_words", lambda flac: None)
    W.seed_page(out, manifest)
    served = out / "seed" / W.SEED_FILE
    assert render.read_bytes() == before
    assert [p["type"] for p in artwork.pictures(served.read_bytes())] == [artwork.FRONT]
    assert pack.read_record(served)["id"] == made == pack.samples_id(pack.audio_bytes(served))
    assert pack.read_member(served, "genome.json") == pack.read_member(render, "genome.json")
    assert (out / "seed" / "now-its-by-you-2026-09-28.flac").read_bytes() == served.read_bytes()  # its edition's own name


def test_the_home_page_offers_the_newest_edition_and_the_history_every_one(tmp_path, monkeypatch):
    """web/sing/editions.json: the seed page (the home page) plays and offers the newest edition whose bytes are
    here, its words timed, under the same name as ever; /history offers every one, newest first and numbered,
    each under its date's name with what identifies it; an edition whose bytes aren't here is left out, and the
    pages still build without any."""
    first, second = tmp_path / "first.flac", tmp_path / "second.flac"
    ids = {first: packed(first, 1, monkeypatch), second: packed(second, 2, monkeypatch)}
    kept = covered(second)  # the second's released file, kept as it is
    manifest = tmp_path / "editions.json"
    listed = [edition(1, "2026-09-28", ids[first], covered(first), render=first,
                      archives=[{"name": "Zenodo", "url": "https://doi.org/10.5281/zenodo.1"}]),
              edition(2, "2026-10-20", ids[second], kept, kept=kept),
              {**edition(3, "2026-11-02", "c" * 64, kept, kept=tmp_path / "not-yet.flac")}]
    manifest.write_text(json.dumps({"editions": listed}))
    web = tmp_path / "web"
    shutil.copytree(W.WEB / "page", web / "page")
    for name in ("consent.md", "words-release.md"):
        shutil.copyfile(W.WEB / name, web / name)
    monkeypatch.setattr(W, "WEB", web)
    monkeypatch.setattr(W, "EDITIONS", manifest)
    timed = {"duration": 0.5, "lines": [[0.0, 0.5, [["Who", 0.0, 0.5, 1]]]]}
    monkeypatch.setattr(W, "seed_words", lambda flac: timed if flac.read_bytes() == kept.read_bytes() else None)
    assert W.seed_source() == kept
    out = tmp_path / "public"
    out.mkdir()
    W.pages(out)

    seed = out / "seed"
    assert sorted(f.name for f in seed.iterdir()) == ["now-its-by-you-2026-09-28.flac", "now-its-by-you-2026-10-20.flac",
                                                       "now-its-by-you.flac", "words.json"]
    assert (seed / W.SEED_FILE).read_bytes() == (seed / "now-its-by-you-2026-10-20.flac").read_bytes() == kept.read_bytes()
    assert json.loads((seed / "words.json").read_text()) == timed
    home = (out / "seed.html").read_text()
    assert "{{" not in home
    assert home.count(f'/seed/now-its-by-you.flac?v={ids[second][:12]}"') == 2  # the player and the download
    assert f'data-words="/seed/words.json?v={W.digest((seed / "words.json").read_text())}"' in home
    assert 'Version 2, <time datetime="2026-10-20">October 20, 2026</time> · <a href="/history">History</a>' in home
    assert "Version 1" not in home and "2026-09-28" not in home  # only the current one on the home page
    page = (out / "history.html").read_text()
    assert "{{" not in page and 'href="/sing.css?v=' in page and 'href="/identity.css?v=' in page
    shown = re.findall(r'<audio controls preload="none" src="([^"]+)">', page)
    assert shown == ["/seed/now-its-by-you-2026-10-20.flac", "/seed/now-its-by-you-2026-09-28.flac"]  # newest first
    assert re.findall(r'<span class="n">(\d)</span> Version (\d)', page) == [("2", "2"), ("1", "1")]
    assert page.count('<span class="badge">on the home page</span>') == 1 and page.index("badge") < page.index("Version 1")
    assert f'<li class="card edition" id="{ids[first][:12]}">' in page
    assert '<time datetime="2026-09-28">September 28, 2026</time>' in page and "What changed in 1 &amp; why." in page
    assert ids[first] in page and listed[0]["file"]["sha256"] in page and listed[0]["render"]["sha256"] in page
    assert "uv run songbird render --seed 1" in page and '<a href="https://doi.org/10.5281/zenodo.1">Zenodo</a>' in page
    assert "github.com" not in page  # the source is private until it's switched on
    assert "Version 3" not in page  # its file isn't here

    public = tmp_path / "public-source"
    public.mkdir()
    for name in ("seed.html", "history.html"):
        shutil.copyfile(web / "page" / name, public / name)
    W.seed_page(public, public=True)
    assert '<a href="https://github.com/quadule/songbird/tree/10dc1e0bba140e5dfed9217f4ddcc90b4d531004">' in (
        public / "history.html").read_text()

    kept.unlink()  # the newest here is the current one
    assert W.seed_source() == first
    first.unlink()
    assert W.seed_source() is None
    again = tmp_path / "again"
    again.mkdir()
    W.pages(again)
    assert not (again / "seed" / W.SEED_FILE).exists() and "{{" not in (again / "seed.html").read_text()
    assert "<p>Nothing yet.</p>" in (again / "history.html").read_text()


def test_an_editions_bytes_never_change_and_a_wrong_list_stops_the_build(tmp_path, monkeypatch):
    render = tmp_path / "one.flac"
    made = packed(render, 1, monkeypatch)
    released = covered(render)
    manifest = tmp_path / "editions.json"
    out = tmp_path / "public"
    out.mkdir()
    (out / "seed.html").write_text("{{SEED_FILE}}")
    monkeypatch.setattr(W, "seed_words", lambda flac: None)

    def build(*listed):
        manifest.write_text(json.dumps({"editions": list(listed)}))
        W.seed_page(out, manifest)

    one = edition(1, "2026-09-28", made, released, render=render)
    for listed, said in (([], "lists no editions"), ([{**one, "note": ""}], "needs note"),
                         ([{**one, "date": "28 September 2026"}], r"needs date \(YYYY-MM-DD\)"),
                         ([{**one, "audio": made[:12]}], "needs audio"), ([{**one, "source": {"commit": "main"}}], "source.commit"),
                         ([{**one, "file": {"sha256": one["file"]["sha256"]}}], "file.bytes"),
                         ([{**one, "render": {}}], "file.path or render.path"),
                         ([{**one, "archives": [{"name": "IA", "url": "http://archive.org"}]}], "archives"),
                         ([one, {**one, "date": "2026-10-01"}], "another's too"),
                         ([one, edition(2, "2026-09-28", "b" * 64, released, render=render)], "another's too")):
        with pytest.raises(SystemExit, match=said):
            build(*listed)
    # the released bytes, or nothing: a render made otherwise now (another cover, say) would change the file
    for changed in ({**one["file"], "sha256": "0" * 64}, {**one["file"], "bytes": one["file"]["bytes"] + 1}):
        with pytest.raises(SystemExit, match="never change"):
            build({**one, "file": changed})
        assert not (out / "seed" / "now-its-by-you-2026-09-28.flac").exists()
    build(one)  # as it should be
    assert W.sha256(out / "seed" / W.SEED_FILE) == W.sha256(released)


def test_the_songs_editions_are_listed_rightly():
    """web/sing/editions.json as it is: the first version is the contest's file as now.itsby.you has served it since
    September 30 (the render with the cover), from the program it was made with."""
    listed = W.editions()
    first = listed[-1]
    assert (first["number"], first["id"], first["title"], first["date"]) == (1, "07ac74fbd4eb", "The first version", "2026-09-28")
    assert first["file"] == {"sha256": "c1980bc78724232b07179ffe8f611318268cd2159cc4f7e07d44f75284b6bc10", "bytes": 15840849}
    assert first["render"]["path"] == "renders/review/contest.flac" and first["source"]["commit"].startswith("10dc1e0")
    assert first["credit"] == "79 takes by eight people"
    assert W.us_date(first["day"]) == "September 28, 2026"
    if first["render"]["found"]:  # in a checkout that has it: made into exactly the bytes released
        assert W.sha256(first["render"]["found"]) == first["render"]["sha256"]


def test_the_preview_mp3_says_what_it_is(tmp_path, monkeypatch):
    """A listening copy made from a packed FLAC doesn't inherit its comment ("This file is also the program..."),
    which isn't true of an MP3."""
    import subprocess

    render = tmp_path / "packed.flac"
    packed(render, 1, monkeypatch)
    W.preview_mp3(render, tmp_path / "preview.mp3")
    tags = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json",
                                      str(tmp_path / "preview.mp3")], capture_output=True, check=True).stdout)["format"]["tags"]
    assert tags["comment"] == W.LISTENING and "also the program that sang it" not in json.dumps(
        {k: v for k, v in tags.items() if k != "comment"})


def test_the_home_pages_about_is_the_artists_statement_and_credits_the_singers_as_they_asked(tmp_path, monkeypatch):
    """The About card leads with the artist's statement word for word (their one sentence, opening with the song's
    title since the title was decided, and the pitch that continues it, as README.md quotes them); its singers are
    CREDITS.md's, as they asked, and no one else; the source code is linked only once it's switched on."""
    import html

    statement = (
        "<cite>Now It's by You</cite> is a folk song passed between people and computers that explores music's ability "
        "to take on a life of its own, in verse and by embedding the software that sang it. Run the program and you get "
        "a new version of the song, shaped by your computer and the season. Sing into it and it learns a little of your "
        "timing and inflection (your recording is deleted right after, and your voice is never cloned). The piece "
        "confronts the blurred authorship of AI music through the lens of folk music and oral tradition: it wonders who "
        "made it, and invites you to take part.")
    page = (W.WEB / "page" / "seed.html").read_text()
    shown = re.search(r"<blockquote>\s*<p>(.*?)</p>\s*</blockquote>", page, re.DOTALL)[1]
    assert " ".join(shown.split()) == statement

    credits = tmp_path / "CREDITS.md"
    credits.write_text("# Credits\n\n## Singers\n\nSome words.\n\nCredited, as they asked:\n\n- Ann\n- B & C\n- dee\n\n"
                       "And one more who sang without credit.\n\n## Other\n\n- Not a singer\n")
    assert W.credits(credits) == "Credited, as they asked: Ann, B &amp; C and dee. And one more who sang without credit."
    credits.write_text("Credited, as they asked:\n- Ann\n")
    assert W.credits(credits) == "Credited, as they asked: Ann."
    credits.write_text("# Credits\n\nNobody yet.\n")
    with pytest.raises(SystemExit, match="Credited, as they asked"):
        W.credits(credits)
    said = W.credits()  # CREDITS.md as it is
    listed = re.search(r"Credited, as they asked:\n\n((?:- .+\n)+)", (ROOT / "CREDITS.md").read_text())[1]
    assert all(html.escape(line[2:]) in said for line in listed.splitlines())

    render = tmp_path / "one.flac"
    made = packed(render, 1, monkeypatch)
    manifest = tmp_path / "editions.json"
    manifest.write_text(json.dumps({"editions": [edition(1, "2026-09-28", made, covered(render), render=render)]}))
    monkeypatch.setattr(W, "seed_words", lambda flac: None)
    for public in (False, True):
        out = tmp_path / f"public-{public}"
        out.mkdir()
        shutil.copyfile(W.WEB / "page" / "seed.html", out / "seed.html")
        W.seed_page(out, manifest, public=public)
        home = (out / "seed.html").read_text()
        assert f"<p>{said}</p>" in home and "{{" not in home
        assert ('<a href="https://github.com/quadule/songbird">The source code</a> is on GitHub.' in home) is public
