"""Singing in a studio on this computer, from a checkout or a packet (docs/WEB-SINGING.md, "Measuring without
pyworld or librosa"): the Sing view is on whenever its files are here; what measuring lacks (wasmtime, where pyworld
isn't installed) is said, with its size, and fetched once when asked; if it can't be, singing says where else to
sing; a program without singing's files says the same."""

import subprocess
import sys
from pathlib import Path

import pytest

from songbird import studio as S
from webstudio import singing as W, standins

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


def lacking(monkeypatch, fetched):
    """A computer without pyworld or wasmtime, until fetched["done"]."""
    monkeypatch.setattr(standins, "missing", lambda: None if fetched.get("done") else "wasmtime")


def test_what_measuring_lacks_is_said_with_its_size_and_fetched_when_asked(home, monkeypatch):
    fetched = {}
    lacking(monkeypatch, fetched)

    def fetch():
        fetched["done"] = True
        return None

    monkeypatch.setattr(standins, "fetch", fetch)
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    studio.enable_web_singing(home / "kit")
    assert isinstance(studio.singing.measurer, W.Measurer)
    offer = studio.singing.offer()
    assert not offer["available"] and "wasmtime" in offer["why"]
    assert offer["fetch"] == {"what": f"wasmtime {standins.WASMTIME}", "mb": standins.WASMTIME_MB, "from": "PyPI",
                              "into": str(home / "home" / "singing")}
    assert not fetched
    with pytest.raises(W.Refused):
        studio.singing.where({"guide": "0123456789ab"}, b"")  # no take is taken meanwhile
    assert studio.singing.post("/api/sing/fetch", {})["available"] and fetched["done"]
    studio.close()


def test_when_it_cant_be_fetched_singing_says_where_else_to_sing(home, monkeypatch):
    lacking(monkeypatch, {})
    monkeypatch.setattr(standins, "fetch", lambda: "wasmtime couldn't be fetched for this computer")
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    studio.enable_web_singing(home / "kit")
    offer = studio.singing.post("/api/sing/fetch", {})
    assert not offer["available"] and "fetch" not in offer
    assert offer["why"] == ("Singing couldn't be set up here: wasmtime couldn't be fetched for this computer. "
                            "Sing at https://studio.itsby.you.")
    studio.close()


def test_fetching_asks_for_a_ready_made_build_into_the_programs_own_folder(home, monkeypatch):
    asked = []

    def run(command, **kw):
        asked.append(command)
        return subprocess.CompletedProcess(command, 0 if len(asked) > 1 else 1, "", "")

    assert standins.fetch(run) is not None and not (standins.folder() / ".ready").exists()  # failed: nothing kept
    assert standins.fetch(run) is None and (standins.folder() / ".ready").exists()
    command = asked[-1]
    assert command[-3:] == ["--only-binary", ":all:", f"wasmtime=={standins.WASMTIME}"]
    assert command[command.index("--target") + 1] == str(standins.folder())
    assert standins.folder().is_relative_to(home / "home" / "singing")
    assert standins.path_entry() == str(standins.folder())
    assert standins.fetch(run) is None and len(asked) == 2  # once


def test_a_program_without_singings_files_says_where_to_sing(home, monkeypatch):
    monkeypatch.setitem(sys.modules, "webstudio.singing", None)  # as an older version's file has it
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    studio.enable_web_singing(None, required=False)
    assert studio.singing is None
    assert studio.sing_available() == {"available": False, "why": S.SING_ELSEWHERE}
    assert studio.sing() == {"error": S.SING_ELSEWHERE} and "studio.itsby.you" in S.SING_ELSEWHERE
    with pytest.raises(SystemExit):
        studio.enable_web_singing(None)  # asked for: said
    studio.close()


def test_a_studio_on_this_computer_sings_without_being_asked(home, monkeypatch):
    """`songbird studio` takes the Sing view by default; shared, only with --web-singing; it never starts the
    recording page."""
    made = []

    class Stop(Exception):
        pass

    def serve(studio, *a, **kw):
        made.append(studio)
        raise Stop

    monkeypatch.setattr(S, "serve", serve)
    monkeypatch.setattr(W.Singing, "check", lambda self: None)
    parser = S.argparse.ArgumentParser()
    S.add_arguments(parser)
    for argv, sings in ((["--song", str(LEAD)], True), (["--song", str(LEAD), "--host", "0.0.0.0"], False),
                        (["--song", str(LEAD), "--host", "0.0.0.0", "--web-singing"], True)):
        args = parser.parse_args([*argv, "--machine", "fictional:ada", "--out", str(home / "out")])
        with pytest.raises(Stop):
            S.run(args)
        assert (made[-1].singing is not None) == sings
        made[-1].close()
    assert not hasattr(made[-1], "karaoke") and not hasattr(made[-1], "recorder")
