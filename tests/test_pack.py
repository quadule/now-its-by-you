"""The seed packet: a FLAC that plays unchanged, unzips, and runs its own program."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from songbird import pack
from songbird.synth import master

ROOT = Path(__file__).resolve().parents[1]
GENOME = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture
def rendition(tmp_path):
    rng = np.random.default_rng(3)
    pcm = np.clip(rng.normal(0, 3000, (44100, 2)), -32768, 32767).astype("<i2")
    flac = tmp_path / "song.flac"
    master.write_flac(flac, pcm, 44100)
    record = {"id": master.pcm_sha256(pcm), "title": "Now It's by You", "rendered_at": "2026-09-26T12:00:00+00:00",
              "params": {"tempo": 100}, "program_version": "test", **pack.lineage(None)}
    return flac, pcm, record


def test_packet_plays_unzips_and_keeps_its_audio(rendition, tmp_path):
    flac, pcm, record = rendition
    original = flac.read_bytes()
    pack.pack(flac, record, GENOME, lyrics="la la\n")
    # the audio is untouched, byte for byte, and decodes to the same samples
    assert flac.read_bytes()[: len(original)] == original
    assert pack.audio_bytes(flac) == original
    assert np.array_equal(sf.read(str(flac), dtype="int16", always_2d=True)[0], pcm)
    with zipfile.ZipFile(flac) as z:
        names = set(z.namelist())
        assert {"__main__.py", "README.txt", "LICENSE", "manifest.json", "genome.json", "lyrics.txt",
                "requirements.txt", "program/songbird/cli.py", "program/pyproject.toml"} <= names
        assert not [n for n in names if "__pycache__" in n]
        manifest = json.loads(z.read("manifest.json"))
        assert z.read("genome.json") == GENOME.read_bytes()
    assert manifest["id"] == record["id"] and manifest["generation"] == 0 and manifest["ancestry"] == []
    assert pack.read_record(flac)["id"] == record["id"]
    # packing again replaces the archive rather than stacking another on it
    size = flac.stat().st_size
    pack.pack(flac, record, GENOME, lyrics="la la\n")
    assert flac.stat().st_size == size and pack.audio_bytes(flac) == original


def test_the_same_rendition_packs_to_the_same_bytes(rendition, tmp_path):
    flac, _, record = rendition
    a = pack.pack(flac, record, GENOME, out=tmp_path / "a.flac")
    b = pack.pack(flac, record, GENOME, out=tmp_path / "b.flac")
    assert a.read_bytes() == b.read_bytes()


def test_the_budget_report_measures_the_program_against_the_goal():
    """The 8 MiB is a goal to keep in mind (the artist, 2026-09-27), not a wall: the report says where we are."""
    report = pack.budget()
    assert report["goal_bytes"] == 8 * 2**20 and report["limit_bytes"] == pack.LIMIT > report["goal_bytes"]
    assert 0 < report["model_bytes"] < report["program_bytes"] <= report["limit_bytes"]
    assert report["source_bytes"] + report["model_bytes"] == report["program_bytes"]
    assert report["headroom_bytes"] == report["goal_bytes"] - report["program_bytes"]


def test_oversized_program_is_refused_before_replacing_audio(rendition, tmp_path, monkeypatch):
    flac, _, record = rendition
    original = flac.read_bytes()
    monkeypatch.setattr(pack, "LIMIT", 100)
    with pytest.raises(ValueError, match="meant to travel"):
        pack.pack(flac, record, GENOME)
    assert flac.read_bytes() == original and not flac.with_name(flac.name + ".part").exists()


def test_large_performance_or_lineage_cannot_bypass_budget(rendition, monkeypatch):
    flac, _, record = rendition
    original = flac.read_bytes()
    monkeypatch.setattr(pack, "program_files", lambda root: {})
    monkeypatch.setattr(pack, "LIMIT", 100)
    with pytest.raises(ValueError, match="rendition data.*limit"):
        pack.pack(flac, record, GENOME)
    assert flac.read_bytes() == original


def test_budget_command_reports_exact_counts(capsys):
    from songbird import cli

    assert cli.main(["budget", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == pack.budget()


def test_a_record_for_other_audio_is_refused(rendition):
    flac, _, record = rendition
    with pytest.raises(ValueError):
        pack.pack(flac, {**record, "id": "0" * 64}, GENOME)


def test_a_replay_is_compared_with_its_recording_sample_by_sample():
    rng = np.random.default_rng(5)
    a = rng.integers(-20000, 20000, (44100, 2)).astype("<i2")
    assert pack.compare_samples(a, a.copy()) == "matches"
    near = a.copy()
    near[100, 0] += 3  # another platform's rounding: a step or three here and there
    near[200, 1] -= 1
    assert pack.compare_samples(near, a) == "matches within 3 steps (largest difference −80.8 dB)"
    edge = a.copy()
    edge[7, 0] += pack.SMALL_STEPS
    assert pack.compare_samples(edge, a).startswith(f"matches within {pack.SMALL_STEPS} steps")
    far = a.copy()
    far[22050, 1] += 1000  # a real change, half a second in
    assert pack.compare_samples(far, a) == "differs by up to 1000 steps (−30.3 dB), the most at 0.500 s"
    assert pack.compare_samples(a[:-10], a).startswith("differs: 44090 samples long")
    assert pack.compare_samples(a[:, :1], a) == "differs: 1 channels, the recording 2"
    assert pack.compare_samples(a[:, 0], a[:, 0]) == "matches"  # mono, as one channel


def test_replay_says_how_it_compares_with_the_recording_at_hand(rendition, tmp_path):
    from songbird import cli

    flac, pcm, record = rendition
    near = pcm.copy()
    near[10, 0] += 2
    out = tmp_path / "again.flac"
    master.write_flac(out, near, 44100)
    made = {"id": master.pcm_sha256(near)}
    # a render record, its FLAC beside it (render_one writes NAME.flac and NAME.json)
    (tmp_path / "song.json").write_text(json.dumps(record))
    recorded, beside = cli.recording_of(tmp_path / "song.json")
    assert beside and cli.replayed(record, made, out, recorded, beside) == \
        "matches within 2 steps (largest difference −84.3 dB)"
    assert cli.replayed(record, {"id": record["id"]}, out, recorded, beside) == "matches"  # the same id
    # a packet carries its own recording
    packet = tmp_path / "packet.flac"
    pack.pack(flac, record, GENOME, out=packet)
    recorded, beside = cli.recording_of(packet)
    assert not beside and cli.replayed(record, made, out, recorded, beside).startswith("matches within 2 steps")
    # no recording at hand (or the one beside is another rendition's): only the ids can be compared
    alone = tmp_path / "alone" / "song.json"
    alone.parent.mkdir()
    alone.write_text(json.dumps(record))
    assert cli.recording_of(alone) == (None, False)
    assert cli.replayed(record, made, out, None, False).startswith("differs from the record's id")
    other = {**record, "id": "0" * 64}
    recorded, beside = cli.recording_of(tmp_path / "song.json")
    assert cli.replayed(other, made, out, recorded, beside).startswith("differs from the record's id")


def test_lineage_counts_generations():
    seed = {"id": "a" * 64, **pack.lineage(None)}
    child = {"id": "b" * 64, **pack.lineage(seed)}
    grandchild = pack.lineage(child)
    assert (seed["generation"], child["generation"], grandchild["generation"]) == (0, 1, 2)
    assert grandchild["parent_id"] == "b" * 64 and grandchild["ancestry"] == ["a" * 64, "b" * 64]


def test_words_as_sung_reads_lines_from_the_score():
    def note(start, syllable, word, word_len, line_end=False, section="verse"):
        return {"part": "voice", "start": start, "syllable": syllable, "word": word, "word_len": word_len,
                "line_end": line_end, "section": section}

    score = {"notes": [note(0, "who", "Who", 1), note(1, "made", "made", 1), note(2, "this", "*this*", 1),
                       note(3, "song", "song?", 1, True), note(4, "no", "No-bo-dy", 3, section="refrain"),
                       note(5, "bo", "No-bo-dy", 3, section="refrain"), note(6, "dy", "No-bo-dy", 3, section="refrain"),
                       note(7, "knows", "knows.", 1, True, section="refrain"),
                       {"part": "fiddle", "start": 0.5, "syllable": None}]}
    assert pack.words_as_sung(score, "T") == "T\n\nWho made this song?\n\nNobody knows.\n"


def _run(packet, *args, home):
    env = dict(os.environ, SONGBIRD_HOME=str(home))
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(packet), *args], capture_output=True, text=True, env=env, timeout=300)


def test_python_runs_the_file(rendition, tmp_path):
    flac, _, record = rendition
    pack.pack(flac, record, GENOME)
    home = tmp_path / "home"
    about = _run(flac, home=home)
    assert about.returncode == 0 and "Now It's by You" in about.stdout and "the seed" in about.stdout
    assert not home.exists()  # reading about it writes nothing
    # nothing is written before the person agrees
    asked = _run(flac, "--here", "songbird", "--help", home=home)
    assert asked.returncode != 0 and "--yes" in asked.stderr and not (home / "packets").exists()
    # the program inside runs (with this Python's own dependencies: --here)
    help_ = _run(flac, "--yes", "--here", "songbird", "--help", home=home)
    assert help_.returncode == 0, help_.stderr
    assert "render" in help_.stdout and "pack" in help_.stdout
    assert list((home / "packets").glob("*/program/songbird/cli.py"))
    unpacked = _run(flac, "unpack", str(tmp_path / "out"), home=home)
    assert unpacked.returncode == 0 and (tmp_path / "out" / "manifest.json").exists()
    # the studio isn't offered until the program has one
    assert ("studio" in about.stdout) == (ROOT / "songbird" / "studio.py").exists()


def _rewrite(packet, out, change):
    """A copy of a packet with its archive's entries changed by change(name, data) -> data."""
    with zipfile.ZipFile(packet) as z:
        entries = [(i, change(i.filename, z.read(i.filename))) for i in z.infolist()]
    out.write_bytes(pack.audio_bytes(packet))
    with zipfile.ZipFile(out, "a") as z:
        for info, data in entries:
            z.writestr(info, data)
    return out


def test_a_changed_program_is_refused_and_the_record_chooses_no_paths(rendition, tmp_path):
    flac, _, record = rendition
    pack.pack(flac, record, GENOME)
    home = tmp_path / "home"
    tampered = _rewrite(flac, tmp_path / "tampered.flac",
                        lambda n, d: d + b"\nprint('changed')\n" if n == "program/songbird/cli.py" else d)
    run = _run(tampered, "--yes", "--here", "songbird", "--help", home=home)
    assert run.returncode != 0 and "doesn't match" in run.stderr and not (home / "packets").exists()
    # a record whose id is a path unpacks where every packet does: in a folder named by the file's own hash
    hostile = _rewrite(flac, tmp_path / "hostile.flac", lambda n, d: json.dumps(
        {**json.loads(d), "id": "../../../escaped"}).encode() if n == "manifest.json" else d)
    run = _run(hostile, "--yes", "--here", "songbird", "--help", home=home)
    assert run.returncode == 0, run.stderr
    assert not (tmp_path / "escaped").exists() and not (home.parent / "escaped").exists()
    assert all(len(p.name) == 16 for p in (home / "packets").iterdir() if p.is_dir())


def test_a_packet_sings_its_children_with_the_license_and_is_checked_as_a_parent(rendition, tmp_path):
    flac, pcm, record = rendition
    pack.pack(flac, record, GENOME)
    inside = pack.unpack(flac, tmp_path / "inside")
    # packed again by the program it carries (its root is program/), the license comes along in full
    child = tmp_path / "child.flac"
    master.write_flac(child, pcm[::-1].copy(), 44100)
    child_record = {"id": master.pcm_sha256(pcm[::-1].copy()), "title": "Now It's by You", **pack.lineage(record)}
    pack.pack(child, child_record, GENOME, root=inside / "program")
    with zipfile.ZipFile(child) as z:
        assert z.read("LICENSE") == (ROOT / "LICENSE").read_bytes() and b"Statement of Purpose" in z.read("LICENSE")
        assert json.loads(z.read("manifest.json"))["generation"] == 1
    assert pack.read_record(child)["parent_id"] == record["id"]
    # a packet whose audio isn't the one its record describes is refused as a parent
    swapped = tmp_path / "swapped.flac"
    swapped.write_bytes(pack.audio_bytes(child) + flac.read_bytes()[len(pack.audio_bytes(flac)):])
    with pytest.raises(ValueError):
        pack.read_record(swapped)
    # a packet packs again from what it carries, and a plain FLAC has nothing to unpack
    from songbird.cli import main

    assert main(["pack", str(flac), "--out", str(tmp_path / "again.flac")]) == 0
    assert pack.read_record(tmp_path / "again.flac")["id"] == record["id"]
    plain = tmp_path / "plain.flac"
    master.write_flac(plain, pcm, 44100)
    with pytest.raises(ValueError):
        pack.unpack(plain, tmp_path / "nothing")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_other_players_hear_the_same_samples(rendition):
    flac, pcm, record = rendition
    pack.pack(flac, record, GENOME)
    decoded = subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(flac), "-f", "s16le", "-"], capture_output=True).stdout
    assert decoded == np.ascontiguousarray(pcm, dtype="<i2").tobytes()


def test_the_bootstrap_is_the_standard_library_only():
    import ast

    tree = ast.parse((ROOT / "songbird" / "bootstrap.py").read_text())
    names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert names - {"__future__"} <= set(sys.stdlib_module_names), names - set(sys.stdlib_module_names)


def test_the_bootstrap_says_what_this_computer_lacks_before_asking(monkeypatch):
    from songbird import bootstrap

    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: None)  # no uv
    said = bootstrap.python_problem(False, (3, 9))
    assert "3.11 or newer" in said and "3.9" in said and "python.org" in said and "uv" in said
    assert "Nothing has been written" in said
    assert bootstrap.python_problem(True, (3, 9)) is None  # --here: this Python as it is
    assert bootstrap.python_problem(False, sys.version_info[:2]) is None
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: "/usr/bin/uv")  # uv fetches a Python
    assert bootstrap.python_problem(False, (3, 9)) is None


PINS = "# the first version's\nnumpy==2.5.3\nscipy==1.18.1\nnumba==0.67.0\nsoundfile==0.14.0\ncmudict==1.1.3\n"


class Installer:
    """uv and pip, stood in for: each command is kept; a venv command makes the environment; an install fails if it
    asks for something with no ready-made build here (`unbuilt`, e.g. numba 0.67.0 on an Intel Mac) or would compile
    (no --only-binary :all:), and every install fails offline."""

    def __init__(self, unbuilt=(), offline=False):
        self.calls, self.unbuilt, self.offline = [], set(unbuilt), offline

    def __call__(self, cmd, check=False, **kwargs):
        cmd = [str(c) for c in cmd]
        self.calls.append(cmd)
        if "venv" in cmd:
            (Path(cmd[-1]) / "bin").mkdir(parents=True)
            (Path(cmd[-1]) / "bin" / "python").write_text("")
            return subprocess.CompletedProcess(cmd, 0)
        asked = Path(cmd[cmd.index("-r") + 1]).read_text().split() if "-r" in cmd else cmd
        ready_made = "--only-binary" in cmd and cmd[cmd.index("--only-binary") + 1] == ":all:"
        ok = ready_made and not self.offline and not self.unbuilt & set(asked)
        if not ok and check:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0 if ok else 1)


def _set_up(tmp_path, monkeypatch, installer, uv=None, wanted="3.12"):
    from songbird import bootstrap

    (tmp_path / "packet").mkdir(parents=True)
    (tmp_path / "packet" / "requirements.txt").write_text(PINS)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda name: uv)
    monkeypatch.setattr(bootstrap.subprocess, "run", installer)
    env = tmp_path / "envs" / "e"
    said = []
    bootstrap.set_up(tmp_path / "packet", env, env / "bin" / "python", wanted, tell=said.append)
    return env, " ".join(said)


def test_the_bootstrap_installs_the_pins_ready_made_and_else_the_newest_made_for_this_computer(tmp_path, monkeypatch):
    # an Intel Mac, with pip: numba 0.67.0 has no build for it, so the pins fail, and the newest made for it install
    pip = Installer(unbuilt={"numba==0.67.0"})
    env, said = _set_up(tmp_path, monkeypatch, pip)
    installs = [c for c in pip.calls if "install" in c]
    assert len(installs) == 2 and installs[0][-2:] == ["-r", str(tmp_path / "packet" / "requirements.txt")]
    assert installs[1][-5:] == ["numpy", "scipy", "numba", "soundfile", "cmudict"]  # unpinned: the resolver picks
    assert all(c[c.index("--only-binary") + 1] == ":all:" for c in installs)  # never compiled, either time
    assert "couldn't be installed here" in said and "newest ones made for this computer" in said
    assert (env / ".ready").exists()
    # with uv, where the pins have builds: uv makes it with the Python the version was made with, and that's all
    uv = Installer()
    env, said = _set_up(tmp_path / "uv", monkeypatch, uv, uv="/usr/bin/uv")
    assert uv.calls[0][:5] == ["/usr/bin/uv", "venv", "--quiet", "--python", "3.12"]
    assert [c[:3] for c in uv.calls[1:]] == [["/usr/bin/uv", "pip", "install"]] and "-r" in uv.calls[1]
    assert "--only-binary" in uv.calls[1] and "couldn't" not in said and (env / ".ready").exists()


def test_when_nothing_installs_the_bootstrap_says_why_it_may_be_and_keeps_nothing(tmp_path, monkeypatch):
    # offline: both tries fail, the half-made environment goes, and it says to connect
    with pytest.raises(SystemExit) as stop:
        _set_up(tmp_path, monkeypatch, Installer(offline=True), wanted="3.10")
    assert "offline" in str(stop.value) and not (tmp_path / "envs" / "e").exists()
    # with pip on a Python other than the version's, there may be no builds for this one: uv fetches the version's
    assert "may not be made for Python" in str(stop.value) and "uv" in str(stop.value) and "3.10" in str(stop.value)
    with pytest.raises(SystemExit) as stop:  # uv already fetched that Python: nothing more to suggest
        _set_up(tmp_path / "uv", monkeypatch, Installer(offline=True), uv="/usr/bin/uv", wanted="3.10")
    assert "offline" in str(stop.value) and "may not be made" not in str(stop.value)


def test_the_studios_first_time_has_a_page_that_says_what_it_waits_for():
    import http.client

    from songbird import bootstrap

    page = bootstrap.WaitingPage(port=18820, browser=False)
    assert page.server is not None

    def get(path):
        c = http.client.HTTPConnection("127.0.0.1", page.port, timeout=10)
        c.request("GET", path)
        r = c.getresponse()
        out = r.status, r.read()
        c.close()
        return out

    status, body = get("/")
    assert status == 200 and b"Getting the studio ready" in body
    page.say("Fetching what the program needs")
    status, body = get("/status")
    assert json.loads(body)["stage"] == "Fetching what the program needs" and not json.loads(body)["done"]
    assert get("/api/start")[0] == 404  # it answers as the studio only once the studio is there
    port = page.step_aside()
    assert port == page.port
    with pytest.raises(OSError):
        get("/status")  # stepped aside: the studio takes the address


# ---------------------------------------------------------------- the song's cover, in every file (songbird/artwork.py)


def front_covers(data: bytes) -> list[dict]:
    from songbird import artwork

    return [p for p in artwork.pictures(data) if p["type"] == 3]


def test_the_cover_is_the_songs_art_at_a_size_a_packet_carries():
    from songbird import artwork

    jpeg = artwork.COVER.read_bytes()
    assert artwork._jpeg_size(jpeg) == (600, 600, 24) and len(jpeg) < 100 * 1024
    assert "program/songbird/cover.jpg" in pack.program_files()  # every child can embed it


def test_a_packed_file_carries_one_front_cover_and_the_same_samples(rendition, tmp_path):
    from songbird import artwork, received

    flac, pcm, record = rendition
    bare = tmp_path / "bare.flac"
    master.write_flac(bare, pcm, 44100, cover=False)
    assert artwork.pictures(bare.read_bytes()) == [] and front_covers(flac.read_bytes())  # write_flac's own
    pack.pack(bare, record, GENOME, lyrics="la la\n")  # whatever wrote the FLAC, the packet has the cover
    pack.pack(flac, record, GENOME, lyrics="la la\n")
    for f in (flac, bare):
        (cover,) = front_covers(pack.audio_bytes(f))
        assert (cover["mime"], cover["width"], cover["height"], cover["depth"]) == ("image/jpeg", 600, 600, 24)
        assert cover["data"] == artwork.COVER.read_bytes() and cover["description"] == "Now It's by You"
        assert np.array_equal(sf.read(str(f), dtype="int16", always_2d=True)[0], pcm)  # it plays
        with zipfile.ZipFile(f) as z:
            assert z.testzip() is None and json.loads(z.read("manifest.json"))["id"] == record["id"]
        assert pack.samples_id(pack.audio_bytes(f)) == record["id"] == pack.read_record(f)["id"]
        audio_end, manifest, _ = received.read_packet(f)  # the studio's strict reader takes it
        assert audio_end == len(pack.audio_bytes(f)) and json.loads(manifest)["id"] == record["id"]
        assert received.samples_id(pack.audio_bytes(f)) == record["id"]
    assert flac.read_bytes() == bare.read_bytes()


def test_embedding_keeps_the_tags_and_replaces_a_cover_rather_than_stacking_one(tmp_path):
    from songbird import artwork

    pcm = np.zeros((4410, 2), dtype="<i2")
    tagged = tmp_path / "tagged.flac"
    master.write_flac(tagged, pcm, 44100, tags={"title": "Coal from the Fire", "artist": "The Volunteers"})
    data = tagged.read_bytes()
    assert [k for k, _ in artwork.blocks(data)[0]] == [artwork.STREAMINFO, artwork.VORBIS_COMMENT, artwork.PICTURE]
    assert front_covers(data)[0]["description"] == "Coal from the Fire"
    assert artwork.embed(data, "Coal from the Fire") == data  # once is enough
    again = artwork.embed(data, "Another")
    assert [p["description"] for p in front_covers(again)] == ["Another"]
    assert sf.info(str(tagged)).frames == 4410 and sf.SoundFile(str(tagged)).title == "Coal from the Fire"
    with pytest.raises(ValueError):
        artwork.embed(b"fLaC" + bytes(64))
    with pytest.raises(ValueError):
        artwork.embed(b"RIFF" + bytes(64))


def test_an_older_file_is_given_the_cover_with_its_packet_kept_byte_for_byte(rendition, tmp_path, monkeypatch):
    from songbird import artwork, received

    _, pcm, record = rendition
    old = tmp_path / "old.flac"
    master.write_flac(old, pcm, 44100, cover=False)
    with monkeypatch.context() as m:  # a file packed before the program embedded the cover
        m.setattr(pack.artwork, "embed", lambda audio, description=None: audio)
        pack.pack(old, record, GENOME, lyrics="la la\n")
    assert artwork.pictures(pack.audio_bytes(old)) == []
    new = pack.with_cover(old, tmp_path / "new.flac")
    assert len(front_covers(pack.audio_bytes(new))) == 1
    assert new.read_bytes()[len(pack.audio_bytes(new)):] != old.read_bytes()[len(pack.audio_bytes(old)):]  # moved
    with zipfile.ZipFile(old) as a, zipfile.ZipFile(new) as b:
        assert b.testzip() is None and a.namelist() == b.namelist()
        assert all(a.read(n) == b.read(n) for n in a.namelist())
        assert [i.compress_size for i in a.infolist()] == [i.compress_size for i in b.infolist()]
    assert pack.read_record(new)["id"] == record["id"] == pack.samples_id(pack.audio_bytes(new))
    assert received.read_packet(new)[0] == len(pack.audio_bytes(new))
    assert pack.with_cover(new, tmp_path / "again.flac").read_bytes() == new.read_bytes()
    if shutil.which("unzip"):
        assert subprocess.run(["unzip", "-tq", str(new)], capture_output=True).returncode == 0
    plain = tmp_path / "plain.flac"  # no packet: only the cover added
    master.write_flac(plain, pcm, 44100, cover=False)
    assert len(front_covers(pack.with_cover(plain, tmp_path / "plain2.flac").read_bytes())) == 1


def test_a_render_carries_the_cover_and_replays_to_the_same_samples(tmp_path, capsys):
    from songbird import cli

    out, again = tmp_path / "tag.flac", tmp_path / "again.flac"
    assert cli.main(["render", str(GENOME), "--form", "tag", "--out", str(out), "--pack"]) == 0
    (cover,) = front_covers(pack.audio_bytes(out))
    assert (cover["width"], cover["height"], cover["description"]) == (600, 600, "Now It's by You")
    assert sf.SoundFile(str(out)).title == "Now It's by You"  # the Vorbis comments kept beside it
    record = pack.read_record(out)
    capsys.readouterr()
    assert cli.main(["render", str(GENOME), "--replay", str(out), "--out", str(again)]) == 0
    assert "replay: matches" in capsys.readouterr().out
    assert len(front_covers(again.read_bytes())) == 1 and pack.samples_id(again.read_bytes()) == record["id"]
