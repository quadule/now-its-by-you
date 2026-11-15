"""The command line for machines and dates: harvest, render --machine --date, year."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_a_quiet_voice_is_read_in_full_when_a_person_asks(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    H.save(H.Voice(machine=H.Machine(0.5, 0.4, 0.5), salt="0a0b"), quiet=True)  # as a render leaves it
    asked = []

    def harvest(without=(), salt=None, **kwargs):
        asked.append((set(without), salt))
        return H.Voice(machine=H.Machine(0.5, 0.4, 0.5), salt=salt)

    monkeypatch.setattr(H, "harvest", harvest)
    assert cli.main(["harvest", "--no-typing"]) == 0
    assert asked == [(set(), "0a0b")]  # everything read, the same singer
    assert "quiet" not in json.loads(H.cache_path().read_text())


def test_showing_what_is_kept_reads_nothing_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(H, "harvest", lambda *a, **k: pytest.fail("--show harvested"))
    assert cli.main(["harvest", "--show"]) == 0  # nothing kept yet: it says what a harvest would read
    shown = capsys.readouterr().out
    assert "Nothing is kept" in shown and "Documents and Desktop" in shown
    assert not H.cache_path().exists()

    H.save(H.Voice(machine=H.Machine(0.5, 0.4, 0.5), salt="0a0b"), quiet=True)  # as a render leaves it
    before = H.cache_path().read_text()
    assert cli.main(["harvest", "--show"]) == 0
    shown = capsys.readouterr().out
    assert '"salt"' in shown and "would also read" in shown and "Documents and Desktop" in shown
    assert H.cache_path().read_text() == before


def test_a_harvest_says_what_it_reads_before_it_reads(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    said = []
    monkeypatch.setattr(H, "harvest", lambda without=(), salt=None, **k: said.append(capsys.readouterr().out) or H.Voice(salt="s"))
    assert cli.main(["harvest", "--no-typing", "--without", "words"]) == 0
    assert "Reading" in said[0] and "ages" in said[0] and "Documents" not in said[0] and "type" not in said[0]


def test_a_new_voice_is_a_new_salt(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    H.save(H.fictional("ada"))
    monkeypatch.setattr(H, "harvest", lambda without=(), salt=None, **kw: H.Voice(salt=salt or "fresh"))
    assert cli.main(["harvest", "--new-voice", "--no-typing"]) == 0
    assert H.load().salt == "fresh"


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
    assert a["singer"]["tract"] == a["params"]["singer"].get("tract", a["singer"]["tract"])
    for field, value in a["params"]["mix"].items():  # the mix the rendition chose is the mix it was made with
        assert a["mix"][field] == value, field
    assert a["mix"]["rt60"] == H.fictional("bo").room.rt60
    # the record replays: its voice, sung again, is the same rendition
    c = render(tmp_path / "c.flac", str(tmp_path / "a.json"), "3")
    assert c["id"] == a["id"]


def test_a_machine_sings_words_drawn_with_its_leanings():
    from dataclasses import replace

    from songbird import drift as D, genome as G, variation as V
    from songbird.realize import Params, choose_params, realize

    g = G.load(LEAD)
    assert cli.words(g, Params.from_dict(g.seed_params)) is None  # the seed sings its own words
    voice = H.fictional("ada")
    p = choose_params(g, None, voice, D.drift(D.parse("2026-10-25"), voice.hash))
    assert "bridge2" in p.form  # a long form, with the bridge's extra stanza
    drawn = cli.words(g, p, sung_by_a_machine=True)
    again = cli.words(g, p, sung_by_a_machine=True)
    assert drawn is not None and drawn.to_dict() == again.to_dict()  # from the rendition's own seed
    assert cli.words(g, p, seed=5).to_dict() != drawn.to_dict()  # --lyrics-seed draws others
    assert cli.words(g, replace(p, form=("refrain",)), sung_by_a_machine=True) is None  # a form the bank can't fill
    score = realize(g, p, lyrics=drawn)
    bridge = [n.syllable for n in score.part("voice") if n.section == "bridge2"]
    assert bridge and len({n.part for n in score.notes if n.section == "bridge2"}) > 1  # sung, with its choir
    assert V.leanings(p).vocabulary


def test_year_table(capsys):
    assert cli.main(["year", str(LEAD), "--machine", "fictional:ada", "--from", "2026-09-25", "--days", "30",
                     "--step", "10"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    rows = [line for line in lines if line[:4].isdigit()]
    assert [r[:10] for r in rows] == ["2026-09-25", "2026-10-05", "2026-10-15"]
    assert lines[-1].startswith("over 3 renders")


def test_year_renders_a_day_a_week_a_month_and_a_year_on(tmp_path, monkeypatch):
    sung = []
    monkeypatch.setattr(cli, "render_one", lambda genome, params, out, **kw: sung.append((out.name, kw["drift"].t)))
    assert cli.main(["year", str(LEAD), "--machine", "fictional:ada", "--from", "2026-09-25", "--days", "1",
                     "--render", str(tmp_path)]) == 0
    names = [name for name, _ in sung]
    assert names == [f"h-now-its-by-you.ada.{d}.flac" for d in
                     ("2026-09-25", "2026-09-26", "2026-10-02", "2026-10-25", "2027-09-25")]
    assert [round(t - sung[0][1]) for _, t in sung] == [0, 1, 7, 30, 365]
