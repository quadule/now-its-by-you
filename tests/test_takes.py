import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import takes as K  # noqa: E402  (tools/takes.py, dev-only but pure stdlib)


def test_names_become_folders():
    assert K.slug("Milo") == "milo"
    assert K.slug("  Ana María & co ") == "ana-maria-co"
    assert K.slug("Zoë") == "zoe" and K.slug("Ольга") == "ольга" and K.slug("明美") == "明美"
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


@pytest.fixture
def kept(tmp_path, monkeypatch):
    """A recordings folder of its own, and somewhere for the renders made from it."""
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    return tmp_path


def at(*when) -> time.struct_time:
    return time.struct_time((*when, 0, 0, -1))


def test_a_take_of_one_section_says_where_it_starts(kept):
    one = K.keep_sung("song", "Ana", b"RIFF-a", "abc123abc123", recorded=at(2026, 9, 27, 20, 1, 2), mix="melody",
                      spec="a.k-2.t90", from_s=25.3, to_s=51.75, section=4, source="online", sid="s" * 24)
    again = K.load(one.path)
    assert (again.from_s, again.to_s, again.section, again.spec) == (25.3, 51.75, 4, "a.k-2.t90")
    assert again.online and again.sid == "s" * 24 and again.recorded_at == datetime(2026, 9, 27, 20, 1, 2)
    again.use = False
    again.save()  # saving keeps every field
    assert K.load(one.path).info == again.info and K.load(one.path).section == 4
    whole = K.keep_sung("song", "Ana", b"RIFF-b", "abc123abc123", from_s=0.0, to_s=190.2, spec="a.k0.t100")
    assert (whole.from_s, whole.section) == (0.0, None) and not whole.online and whole.sid is None
    asked = K.keep_sung("song", "Ana", b"RIFF-d", "abc123abc123", from_s="", to_s="", section="", spec="")
    assert (asked.from_s, asked.to_s, asked.section, asked.spec) == (0.0, None, None, None)  # left empty in a query
    old = K.keep_sung("song", "Ana", b"RIFF-c", "abc123abc123", recorded=at(2026, 9, 25, 15, 28, 7))  # from before
    assert (old.from_s, old.to_s, old.section, old.spec) == (0.0, None, None, None)
    old.sidecar().unlink()  # a take without its sidecar still knows when it was sung, from its name
    assert K.load(old.path).recorded_at == datetime(2026, 9, 25, 15, 28, 7)


def test_online_takes_are_found_with_their_singer_and_time(kept):
    late = K.keep_sung("song", "Bo", b"RIFF-a", "abc123abc123", recorded=at(2026, 9, 27, 21, 0, 0), source="online",
                       sid="b" * 24)
    early = K.keep_sung("song", "Ana", b"RIFF-b", "abc123abc123", recorded=at(2026, 9, 26, 9, 0, 0), source="online",
                        sid="a" * 24)
    K.keep_sung("song", "Milo", b"RIFF-c", "abc123abc123")  # sung here
    K.keep_sung("other", "Ana", b"RIFF-d", "abc123abc123", source="online", sid="a" * 24)
    K.GUIDES.mkdir(parents=True)
    (K.GUIDES / "song.abc123abc123.score.json").write_text("{}")  # not a take
    got = K.online("song")
    assert [t.path for t in got] == [early.path, late.path] and [t.sid for t in got] == ["a" * 24, "b" * 24]
    assert len(K.online()) == 3
    assert [t.sid for t in K.online("song") if t.recorded_at < datetime(2026, 9, 27)] == ["a" * 24]


def test_removing_a_take_removes_what_measuring_it_kept(kept):
    a = K.keep_sung("song", "Ana", b"RIFF-a", "abc123abc123", recorded=at(2026, 9, 26, 9, 0, 0))
    b = K.keep_sung("song", "Ana", b"RIFF-b", "abc123abc123", recorded=at(2026, 9, 26, 9, 5, 0))
    measured, aligned = K.caches(a)
    assert measured == kept / "renders" / "measured" / f"recordings__ana__{a.path.stem}.json"
    assert aligned == kept / "renders" / "measured" / "mfa" / f"recordings__ana__{a.path.stem}.json"
    for f in [*K.caches(a), *K.caches(b)]:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    gone = K.remove(a)
    assert set(gone) == {a.path, a.sidecar(), measured, aligned}
    assert not any(f.exists() for f in gone) and all(f.exists() for f in [b.path, b.sidecar(), *K.caches(b)])
    assert K.remove(a) == []  # nothing left to remove


def test_removing_a_singer_removes_their_takes_phrasings_and_renders(kept):
    theirs = [K.keep_sung(song, "Ana", b"RIFF", "abc123abc123", recorded=at(2026, 9, 26, 9, m, 0))
              for m, song in enumerate(["song", "song", "other"])]
    bo = K.keep_sung("song", "Bo", b"RIFF", "abc123abc123")
    phrasing = kept / "renders" / "phrasing"
    phrasing.mkdir(parents=True)
    for name in ("song.ana.json", "other.ana.json", "song.bo.json", "song.everyone.json"):
        (phrasing / name).write_text("{}")
    (kept / "renders" / "song.karaoke.ana.flac").write_bytes(b"fLaC")
    for f in [*K.caches(theirs[0]), *K.caches(bo)]:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("{}")
    gone = K.remove_singer("ana", "song")
    assert theirs[0].path in gone and theirs[1].sidecar() in gone and not any(f.exists() for f in K.caches(theirs[0]))
    assert not (phrasing / "song.ana.json").exists() and not (kept / "renders" / "song.karaoke.ana.flac").exists()
    assert (phrasing / "other.ana.json").exists() and theirs[2].path.exists()  # another song's stay
    K.remove_singer("ana")
    assert not (K.RECORDINGS / "ana").exists() and not (phrasing / "other.ana.json").exists()
    assert bo.path.exists() and (phrasing / "song.bo.json").exists() and (phrasing / "song.everyone.json").exists()
    assert all(f.exists() for f in K.caches(bo))
    for wrong in ("guides", "words", "../ana", "Ana"):
        with pytest.raises(ValueError):
            K.remove_singer(wrong)
    assert K.remove_singer("nobody") == []


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
