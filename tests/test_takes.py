import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import takes as K  # noqa: E402  (tools/takes.py, dev-only but pure stdlib)


def test_names_become_folders():
    assert K.slug("Milo") == "milo"
    assert K.slug("  Ana María & co ") == "ana-mar-a-co"
    assert K.slug("!!!") == "someone"


def test_takes_stay_with_their_singer(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    monkeypatch.setattr(K, "ROOT", tmp_path)
    guide = tmp_path / "guide.score.json"
    guide.write_text('{"notes": []}')
    a = K.keep("song", "Milo", b"RIFF-a", guide, shift_ms=35.0)
    b = K.keep("song", "Jo Ann", b"RIFF-b", guide)
    assert a.path.parent.name == "milo" and b.path.parent.name == "jo-ann"
    assert K.guide_score("song", a.guide).read_text() == guide.read_text()  # the guide it was sung to is kept
    by = K.singers("song")
    assert set(by) == {"milo", "jo-ann"} and by["milo"][0].info["shift_ms"] == 35.0
    b.use = False
    b.save()
    again = K.load(b.path)
    assert (again.singer, again.use, again.song) == ("Jo Ann", False, "song")
    assert K.takes("other") == []


def test_takes_in_the_same_second_keep_apart(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    at = time.struct_time((2026, 9, 26, 14, 5, 9, 0, 0, -1))
    a = K.keep_sung("song-x", "Ana", b"RIFF-a", "abc123abc123", recorded=at, mix="melody", source="online")
    b = K.keep_sung("song-x", "Ana", b"RIFF-b", "abc123abc123", recorded=at)
    assert a.path.name == "song-x-20260926-140509.wav" and b.path.name == "song-x-20260926-140509-2.wav"
    assert a.info["recorded"] == "2026-09-26T14:05:09" and a.info["mix"] == "melody"
    got = K.takes("song-x", "ana")
    assert [t.song for t in got] == ["song-x", "song-x"] and {t.guide for t in got} == {"abc123abc123"}
    b.sidecar().unlink()  # a take that lost its sidecar still knows its song from its name
    assert K.load(b.path).song == "song-x"
