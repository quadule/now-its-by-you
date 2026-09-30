"""The piano page's score (songbird.piano): any rendition laid out on the grid, the tune with its words, the
chords as the band plays them, and left-hand parts. The studio feeds its page the version on the page (a
person's key, tempo, chords, style), tools/piano_score.py the release; both through the same export."""

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from songbird import band, piano, studio as S
from songbird import phrasing as PH

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
RELEASE = ROOT / "renders" / "review" / "contest.flac"


@pytest.fixture(scope="module")
def studio(tmp_path_factory):
    return S.Studio(None, str(LEAD), "none", home=tmp_path_factory.mktemp("home"))


def laid(studio, edits):
    v = studio.version(edits)
    phrasing = PH.from_json(v.phrasing_json) if v.phrasing_json else None
    choir = [PH.from_json(d) for d in v.choir_phrasings]
    return v, piano.lay(studio.genome, v.params, phrasing=phrasing, choir=choir, lyrics=v.lyrics)


def sung(score):
    return [round(n.pitch) for n in sorted(score.part("voice"), key=lambda n: n.start)]


def test_the_score_is_the_version_as_sung(studio):
    """Every sung note, in order, at the pitch the render sings it, with its syllable; the words in lines; the
    chords as the band lays them; a left hand to choose."""
    v, lay = laid(studio, {})
    data = piano.export(lay, {"kind": "studio"})
    tune = [n for n in data["melody"] if "lyric" in n]
    assert [n["pitch"] for n in tune] == sung(lay["score"])
    assert [n["start"] for n in data["melody"]] == sorted(n["start"] for n in data["melody"])
    assert len(data["chords"]) == len(lay["ctx"].chords) and data["lines"]
    assert data["tempo"] == v.params.tempo and data["key"]["tonicMidi"] == v.params.tonic
    assert set(data["left"]) == {"bass", "fifths", "folk", "block"}
    assert data["bars"] == round(data["end"] / data["timeSignature"][0]) and "lift" not in data
    assert json.loads(json.dumps(data)) == data


def test_a_persons_key_tempo_and_chords_are_in_it(studio):
    v0, lay0 = laid(studio, {})
    first = next(p for s in studio.song({})["composition"]["sections"] for p in s["phrases"] if p["notes"])
    bars = [["vi"], ["IV/3", "Vsus4"]] + first["chords"][2:]
    edits = {"tonic": v0.params.tonic + 2, "tempo": 110, f"chords.{first['id']}": bars}
    v, lay = laid(studio, edits)
    data = piano.export(lay, {"kind": "studio"})
    before = piano.export(lay0, {"kind": "studio"})
    assert data["tempo"] == 110 and data["key"]["tonicPc"] == (before["key"]["tonicPc"] + 2) % 12
    # the sung tune moves with the key (an instrument's quote may take another octave to stay in its range)
    assert [n["pitch"] for n in data["melody"] if "lyric" in n] == [n["pitch"] + 2 for n in before["melody"] if "lyric" in n]
    romans = {c["roman"] for c in data["chords"]}
    assert {"vi", "IV/3", "Vsus4"} <= romans
    inversion = next(c for c in data["chords"] if c["roman"] == "IV/3")
    sus = next(c for c in data["chords"] if c["roman"] == "Vsus4")
    tonic = data["key"]["tonicPc"]
    assert inversion["root"] == (tonic + 5) % 12 and inversion["bass"] == (tonic + 9) % 12 and "/" in inversion["name"]
    assert sus["quality"] == "sus4" and sus["name"].endswith("sus4")
    # the left hand made from the chords takes the inversion's bass
    folk = [n for n in data["left"]["folk"]["notes"] if n["start"] == inversion["start"]]
    assert folk and folk[0]["pitch"] % 12 == inversion["bass"]
    # a plain chord has no bass of its own (the release's score stays as it was)
    assert all("bass" not in c for c in before["chords"])


def test_a_styles_lift_is_in_the_notes(studio):
    """A style's last refrain a whole step up: the tune (its pickup too) and the chords go up with the band."""
    v, lay = laid(studio, {"style.name": "country", "style.lift": True})
    data = piano.export(lay, {"kind": "studio"})
    assert data["lift"]["by"] == 2
    assert [n["pitch"] for n in data["melody"] if "lyric" in n] == sung(lay["score"])
    after = [c for c in data["chords"] if c["start"] >= data["lift"]["at"]]
    assert after and all(c["name"] for c in after)


def test_listening_in_hears_only_its_own_thread(studio):
    """The band hands its Context over only to the thread that asked (a render on another thread goes on)."""
    v = studio.version({})
    other: dict = {}

    def render():
        studio._score(v)
        other["done"] = True

    with band.overheard() as heard:
        t = threading.Thread(target=render)
        t.start()
        t.join()
        assert other["done"] and heard == {}
    _, lay = laid(studio, {})
    assert lay["ctx"].sections


@pytest.mark.skipif(not RELEASE.exists(), reason="the release isn't in this checkout (renders/ isn't kept)")
def test_the_release_score_is_made_again_byte_for_byte(tmp_path):
    out = tmp_path / "score.json"
    subprocess.run([sys.executable, str(ROOT / "tools" / "piano_score.py"), "--out", str(out)], check=True,
                   capture_output=True)
    assert out.read_bytes() == (ROOT / "web" / "piano" / "score.json").read_bytes()
