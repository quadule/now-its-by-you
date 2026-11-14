"""The harvest: each signal reduced to a few coarse numbers, and nothing raw ever returned.

Every scanner runs on fixture folders made here; no test reads the real home
directory, documents, screen or keys.
"""

import json
import os
import shutil
import sys
import zipfile
from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest

from songbird import harvest as H

DAY = 86400.0


def aged(path: Path, days: float, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    when = H.time.time() - days * DAY
    os.utime(path, (when, when))
    return path


def test_file_ages_skip_hidden_system_media_private_links_and_packages(tmp_path):
    home = tmp_path / "home"
    logs = np.linspace(0.5, 3.0, 31)  # log10 of the ages that should count: median 1.75, spread 1.25
    for k, lg in enumerate(logs):
        aged(home / "projects" / f"{k // 10}" / f"f{k}.txt", 10 ** lg)
    far = 10**4.5  # anything counted from here would move the median a bucket
    for where in (".hidden/a", ".dotfile", "Library/Caches/b", "Pictures/c.jpg", "node_modules/d/e.js",
                  "Thing.app/Contents/f", "Documents/g.txt", "Desktop/h.txt", "Downloads/i.zip",
                  "Documents/deep/j.txt", "Desktop/k.txt"):
        aged(home / where, far)
    (home / "link").symlink_to(home / "Documents")
    got = H.ages(home, private=False)
    assert got == H.reduce_ages(10**logs) == H.Ages(median=1.75, spread=1.25)
    assert H.ages(home, private=True).median > got.median  # Desktop, Documents and Downloads count when allowed
    assert H.ages(home, private=False, max_depth=0) is None  # the top level alone has too few files to say
    assert H.ages(tmp_path / "nowhere") is None


def test_file_age_scan_stops_at_its_limits(tmp_path):
    for k in range(60):
        aged(tmp_path / f"f{k:02d}", 10 + k)
    few = H.ages(tmp_path, limit=25)
    assert few is not None and few != H.ages(tmp_path)


def _documents(root: Path) -> None:
    rng = np.random.default_rng(3)
    sea = "sea ship harbour sailor boat water river tide island shore".split()
    other = "morning table walked across garden letter window evening quiet around started found".split()
    for k in range(4):
        words = list(rng.choice(sea, 120)) + list(rng.choice(other, 120))
        rng.shuffle(words)
        text = " ".join(words)
        text += " Zanzibar Zanzibar hunterpass hunterpass Harbour"  # a name, a non-word, a capital
        if k == 0:
            text += " quixotically"  # one document only: rare
        (root / f"note{k}.txt").write_text(text)


def test_words_keep_only_theme_shares_era_and_richness(tmp_path):
    docs = tmp_path / "Documents"
    docs.mkdir()
    _documents(docs)
    got = H.words([docs])
    assert isinstance(got, H.Words)
    assert max(got.themes, key=got.themes.get) == "sea"
    assert abs(sum(got.themes.values()) - 1) < 1e-9 and set(got.themes) == set(H.THEMES)
    assert 0 <= got.richness <= 1 and -1 <= got.era <= 1
    text = json.dumps(H.Voice(words=got, salt="abc").to_dict()).lower()
    for raw in ("zanzibar", "hunterpass", "quixotically", "harbour", "sailor", "garden", "note0", "documents"):
        assert raw not in text
    assert H.words([tmp_path / "missing"]) is None


def test_words_need_enough_documents(tmp_path):
    (tmp_path / "one.txt").write_text("sea " * 500)
    assert H.words([tmp_path]) is None


def test_document_formats_to_plain_text(tmp_path):
    docx = tmp_path / "a.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", "<w:document><w:t>the harbour</w:t><w:t>at night</w:t></w:document>")
    rtf = tmp_path / "b.rtf"
    rtf.write_text(r"{\rtf1\ansi {\b bold} sea \par ship}")
    html = tmp_path / "c.html"
    html.write_text("<p>the <b>river</b></p>")
    assert H._text(str(docx), ".docx", 10_000).split() == ["the", "harbour", "at", "night"]
    assert H._text(str(rtf), ".rtf", 10_000).split() == ["bold", "sea", "ship"]
    assert H._text(str(html), ".html", 10_000).split() == ["the", "river"]


def test_hand_rhythm():
    rng = np.random.default_rng(1)
    steady = [0.2] * 20
    assert H.reduce_hand(steady) == H.Hand(interval=200, unevenness=0.0, skew=0.0)
    lilting = list(rng.gamma(2.0, 0.08, 60)) + [4.0, 0.001]  # a pause to think and a double byte, both dropped
    got = H.reduce_hand(lilting)
    assert got.interval % 20 == 0 and got.skew > 0 and got.unevenness > 0.3
    assert H.reduce_hand([0.2] * 5) is None


def test_typing_is_never_passive():
    # without a person at a terminal (as under pytest) the prompt never appears and nothing is timed
    assert H.typing_sample() is None
    assert H.harvest(without=set(H.SIGNALS) - {"hand"}, salt="s").hand is None  # typing only when asked


def test_colour_from_pixels_and_appearance():
    red, blue, grey = np.zeros((8, 8, 3)), np.zeros((8, 8, 3)), np.full((8, 8, 3), 0.5)
    red[..., 0] = 1.0
    blue[..., 2] = 1.0
    assert H.reduce_colour(red) == H.Colour(brightness=0.25, warm=1.0, green=0.0, cool=0.0)
    assert H.reduce_colour(blue).cool == 1.0
    assert H.reduce_colour(grey) == H.Colour(brightness=0.5, warm=0.25, green=0.5, cool=0.25)
    assert H.reduce_appearance(True, "blue") == H.Colour(0.25, 0.0, 0.0, 1.0)
    assert H.reduce_appearance(False, None) == H.Colour(0.75, 0.25, 0.5, 0.25)


def bmp(width: int, height: int, rgb) -> bytes:
    row = ((24 * width + 31) // 32) * 4
    pixels = bytearray()
    for _ in range(height):
        line = bytes([rgb[2], rgb[1], rgb[0]]) * width
        pixels += line + bytes(row - len(line))
    header = b"BM" + (54 + len(pixels)).to_bytes(4, "little") + bytes(4) + (54).to_bytes(4, "little")
    info = (40).to_bytes(4, "little") + width.to_bytes(4, "little") + height.to_bytes(4, "little")
    info += (1).to_bytes(2, "little") + (24).to_bytes(2, "little") + bytes(24)
    return header + info + bytes(pixels)


def test_bmp_and_a_wallpaper(tmp_path):
    pixels = H.read_bmp(bmp(5, 3, (255, 128, 0)))
    assert pixels.shape == (3, 5, 3) and np.allclose(pixels[0, 0], (1.0, 128 / 255, 0.0))
    if sys.platform == "darwin" and shutil.which("sips"):
        picture = tmp_path / "wall.bmp"
        picture.write_bytes(bmp(40, 30, (20, 40, 200)))
        got = H.colour(picture)
        assert got.cool == 1.0 and got.brightness == 0.25


def test_machine_and_tongue():
    assert H.reduce_machine(10, 32 * 2**30, 3 * DAY) == H.Machine(cores=0.75, memory=0.6, uptime=0.5)
    assert H.reduce_machine(2, 4 * 2**30, 0.5 * DAY) == H.Machine(cores=0.0, memory=0.0, uptime=0.0)
    assert H.reduce_machine(None, None, None) is None
    assert H.reduce_tongue(["en_US.UTF-8"]) == H.Tongue("english", "folk")
    assert H.reduce_tongue(["de-CH", "de_DE.UTF-8", "en"]) == H.Tongue("germanic", "bright")
    assert H.reduce_tongue(["pl", "en"]).inventory == "slavic"  # a tie goes to the system's own language
    assert H.reduce_tongue(["C.UTF-8", "POSIX", ""]) is None
    assert H.reduce_tongue(["xx"]) == H.Tongue("other", "folk")
    assert H.layout_language("com.apple.keylayout.German") == "de"
    assert H.layout_language("com.apple.keylayout.US") == "en"
    assert H.layout_language("com.apple.keylayout.Russian") == "ru"
    assert H.layout_language("gb") == "en" and H.layout_language("fr") == "fr"
    assert H.layout_language("com.apple.keylayout.Dvorak") is None


ALLOWED_STRINGS = set(H.INVENTORIES) | set(H.MODE_FAMILIES)


def plain_numbers(value) -> bool:
    """Only numbers, or names from the program's own tables."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return value in ALLOWED_STRINGS
    if isinstance(value, (tuple, list)):
        return all(plain_numbers(v) for v in value)
    if isinstance(value, dict):
        return all(k in H.THEMES for k in value) and all(plain_numbers(v) for v in value.values())
    return False


@pytest.mark.parametrize("name", ["ada", "bo", "cy", "dee"])
def test_a_voice_holds_only_reduced_numbers(name):
    voice = H.fictional(name)
    assert voice == H.fictional(name) and not voice.neutral
    for signal in H.SIGNALS:
        reduced = getattr(voice, signal)
        assert reduced is not None
        for f in fields(reduced):
            assert plain_numbers(getattr(reduced, f.name)), (signal, f.name, getattr(reduced, f.name))
    again = H.Voice.from_dict(json.loads(json.dumps(voice.to_dict())))
    assert again == voice and again.hash == voice.hash
    assert H.Voice.from_dict({"voice": voice.to_dict()}) == voice  # from a render's record


def test_hash_comes_from_the_salt_and_signals_can_be_left_out():
    assert H.fictional("ada").hash != H.fictional("bo").hash
    nothing = H.harvest(without=H.SIGNALS, salt="00ff")
    assert nothing.neutral and nothing.salt == "00ff"
    assert nothing.hash == H.Voice(salt="00ff").hash != H.Voice(salt="00fe").hash
    assert H.harvest(without=H.SIGNALS).salt != H.harvest(without=H.SIGNALS).salt  # a new machine, a new salt
    assert H.signal_name("files") == "ages" and H.signal_name("Typing") == "hand"
    with pytest.raises(ValueError):
        H.signal_name("camera")


def test_a_render_never_reads_files_documents_or_typing(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "cache"))
    asked = []

    def harvest(without=(), **kwargs):
        asked.append((set(without), kwargs.get("pictures", True)))
        return H.Voice(machine=H.Machine(0.5, 0.4, 0.5), salt="quiet")

    monkeypatch.setattr(H, "harvest", harvest)
    first = H.machine_voice("here")  # a machine nobody has harvested yet
    assert asked == [({"ages", "words", "hand"}, False)] and first.salt == "quiet"  # and no picture opened
    assert json.loads(H.cache_path().read_text())["quiet"] is True
    assert H.machine_voice("here").salt == "quiet" and len(asked) == 1  # the same singer from then on


def test_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "cache"))
    assert H.load() is None
    voice = H.fictional("ada")
    H.save(voice)
    assert H.load() == voice
    assert H.machine_voice("here").hash == voice.hash  # the cache, with its uptime read afresh
    assert H.machine_voice("none") == H.Voice()
    assert H.machine_voice("fictional:bo") == H.fictional("bo")
    record = tmp_path / "render.json"
    record.write_text(json.dumps({"id": "x", "voice": voice.to_dict()}))
    assert H.machine_voice(str(record)) == voice
    assert "Documents" not in (tmp_path / "cache" / "voice.json").read_text()


def test_a_voice_file_this_program_cant_read_keeps_its_singer_and_what_was_left_out(tmp_path, monkeypatch):
    """A voice file from another version of the program, or a damaged one: a signal this program can't make is left
    out and the rest kept; and where no voice can be made of it at all, its salt (the singer) and the signals a
    person asked to be left out are kept, and the file is set aside, not written over."""
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path))
    path = H.cache_path()
    good = H.fictional("ada").to_dict()
    newer = {**good, "songbird_voice": 2, "signals": {**good["signals"], "machine": {"cores_of_tomorrow": 1}}}
    voice = H.Voice.from_dict(newer)
    assert voice.machine is None and voice.tongue == H.fictional("ada").tongue and voice.salt == good["salt"]

    path.write_text(json.dumps({"songbird_voice": 3, "salt": "abcd1234", "signals": "elsewhere", "without": ["colour", "ages"]}))
    assert H.load() is None and H.stored()["salt"] == "abcd1234"
    monkeypatch.setattr(H, "harvest", lambda without=(), **kw: H.Voice(salt=kw.get("salt") or "new") if "colour" in without else None)
    voice = H.here()
    assert voice.salt == "abcd1234"
    assert H.stored()["without"] == ["ages", "colour"] and H.stored()["salt"] == "abcd1234"
    assert json.loads(path.with_name("voice.json.unread").read_text())["songbird_voice"] == 3
    assert not list(tmp_path.glob("*.part"))
