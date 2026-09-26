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


def test_a_record_for_other_audio_is_refused(rendition):
    flac, _, record = rendition
    with pytest.raises(ValueError):
        pack.pack(flac, {**record, "id": "0" * 64}, GENOME)


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
    about = _run(flac, home=tmp_path / "home")
    assert about.returncode == 0 and "Now It's by You" in about.stdout and "the seed" in about.stdout
    # the program inside runs (with this Python's own dependencies: --here)
    help_ = _run(flac, "songbird", "--help", "--here", home=tmp_path / "home")
    assert help_.returncode == 0, help_.stderr
    assert "render" in help_.stdout and "pack" in help_.stdout
    assert list((tmp_path / "home" / "packets").glob("*/program/songbird/cli.py"))
    unpacked = _run(flac, "unpack", str(tmp_path / "out"), home=tmp_path / "home")
    assert unpacked.returncode == 0 and (tmp_path / "out" / "manifest.json").exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_other_players_hear_the_same_samples(rendition):
    flac, pcm, record = rendition
    pack.pack(flac, record, GENOME)
    decoded = subprocess.run(["ffmpeg", "-v", "quiet", "-i", str(flac), "-f", "s16le", "-"], capture_output=True).stdout
    assert decoded == np.ascontiguousarray(pcm, dtype="<i2").tobytes()
