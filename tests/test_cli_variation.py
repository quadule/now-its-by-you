"""The command line for machines and dates: harvest, render --machine --date, year."""

import json
import os
import subprocess
import sys
from pathlib import Path

from songbird import cli
from songbird import harvest as H

ROOT = Path(__file__).parent.parent
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


def test_harvest_fictional_and_opting_out(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    out = tmp_path / "ada.json"
    assert cli.main(["harvest", "--fictional", "ada", "--out", str(out)]) == 0
    assert H.Voice.from_dict(json.loads(out.read_text())) == H.fictional("ada")
    assert not (tmp_path / "home").exists()  # a made-up machine touches no cache

    H.save(H.fictional("ada"))  # as if this machine had been harvested
    assert cli.main(["harvest", "--without", "words", "hand"]) == 0  # leaving signals out reads nothing
    cached = json.loads(H.cache_path().read_text())
    assert cached["signals"]["words"] is None and cached["signals"]["hand"] is None
    assert cached["without"] == ["hand", "words"] and cached["salt"] == H.fictional("ada").salt
    capsys.readouterr()
    assert cli.main(["harvest", "--show"]) == 0
    shown = capsys.readouterr().out
    assert "words    (left out)" in shown and '"salt"' in shown


def test_harvest_with_everything_left_out_reads_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    everything = list(H.SIGNALS)
    assert cli.main(["harvest", "--show", "--no-save", "--no-typing", "--without", *everything]) == 0
    assert "(left out)" in capsys.readouterr().out
    assert not H.cache_path().exists()


def render(out: Path, machine: str, hash_seed: str, *extra: str) -> dict:
    subprocess.run([sys.executable, "-m", "songbird", "render", str(LEAD), "--form", "refrain", "--machine", machine,
                    "--date", "2026-09-25", "--out", str(out), *extra],
                   check=True, cwd=ROOT, capture_output=True, env={**os.environ, "PYTHONHASHSEED": hash_seed})
    return json.loads(out.with_suffix(".json").read_text())


def test_a_machine_at_a_date_renders_the_same_every_time(tmp_path):
    a = render(tmp_path / "a.flac", "fictional:bo", "1")
    b = render(tmp_path / "b.flac", "fictional:bo", "2")
    assert a["id"] == b["id"] and a["params"] == b["params"]
    assert a["voice"]["hash"] == H.fictional("bo").hash
    assert a["rendered_at"] == "2026-09-25T12:00:00+00:00" and a["drift"]["full"]
    assert a["params"]["room"] and a["singer"]["tract"] == a["params"]["singer"].get("tract", a["singer"]["tract"])
    # the record replays: its voice, sung again, is the same rendition
    c = render(tmp_path / "c.flac", str(tmp_path / "a.json"), "3")
    assert c["id"] == a["id"]


def test_year_table(capsys):
    assert cli.main(["year", str(LEAD), "--machine", "fictional:ada", "--from", "2026-09-25", "--days", "30",
                     "--step", "10"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    rows = [line for line in lines if line[:4].isdigit()]
    assert [r[:10] for r in rows] == ["2026-09-25", "2026-10-05", "2026-10-15"]
    assert lines[-1].startswith("over 3 renders")
