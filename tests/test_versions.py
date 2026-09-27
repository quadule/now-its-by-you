"""A singer's own version and their vocals alone (tools/versions.py), made from small stems and scores."""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import takes as K  # noqa: E402  (tools/takes.py)
import versions as VS  # noqa: E402  (tools/versions.py)

from songbird import synth  # noqa: E402

SR = synth.SR
LENGTH = 12.0
# two sung sections with a turn between, as a spec's guide has them
VERSE = [(1.0 + 0.5 * i, 0.45, "verse") for i in range(6)]
REFRAIN = [(7.0 + 0.5 * i, 0.45, "refrain") for i in range(6)]


def tone(hz: float, amp: float, notes, sr: int, seconds: float = LENGTH) -> np.ndarray:
    """A sine at hz sounding during the notes, amp high."""
    t = np.arange(int(seconds * sr)) / sr
    on = np.zeros(len(t))
    for start, dur, _ in notes:
        on[int(start * sr) : int((start + dur) * sr)] = 1.0
    return amp * np.sin(2 * np.pi * hz * t) * on


def strip(x, sr, seed):
    """A stand-in for the machine voice's strip and room: a little gain, a short echo, in the middle."""
    y = 0.8 * x
    y[int(0.03 * sr) :] += 0.2 * x[: -int(0.03 * sr)]
    return synth.pan(y, 0.0)


@pytest.fixture
def stems(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    band = np.stack([tone(110.0, 0.1, [(0.0, LENGTH, "")], SR)] * 2, axis=1)
    lead = synth.pan(tone(220.0, 0.2, VERSE + REFRAIN, SR), 0.0)
    sf.write(str(tmp_path / "a.k0.t100.band.wav"), band.astype(np.float32), SR, subtype="FLOAT")
    sf.write(str(tmp_path / "a.k0.t100.lead.wav"), lead.astype(np.float32), SR, subtype="FLOAT")
    notes = [{"part": "voice", "start": s, "dur": d, "pitch": 57.0, "vel": 0.8, "section": name}
             for s, d, name in VERSE + REFRAIN]
    notes.append({"part": "lute", "start": 0.0, "dur": 1.0, "pitch": 45.0, "vel": 0.5})  # the band's aren't sung
    score = {"notes": notes, "duration": LENGTH, "sections": [["verse", 0.9, 4.0], ["turn", 4.0, 6.9],
                                                               ["refrain", 6.9, 10.0]], "seed": 1, "tempo": 96.0}
    (tmp_path / "a.k0.t100.score.json").write_text(json.dumps(score))
    return tuple(tmp_path / f"a.k0.t100.{x}" for x in ("band.wav", "lead.wav", "score.json"))


def sung(notes, from_s: float, to_s: float, amp: float = 0.05, rate: int = 48000, when=(2026, 9, 27, 20, 0, 0),
         spec: str = "a.k0.t100", song: str = "song", **info) -> K.Take:
    """A take by Ana at 330 Hz where the notes are, holding only from_s to to_s of the guide."""
    y = tone(330.0, amp, [(s - from_s, d, n) for s, d, n in notes if from_s <= s < to_s], rate, to_s - from_s)
    y = y + 1e-4 * np.random.default_rng(0).standard_normal(len(y))
    buf = K.RECORDINGS / "in.wav"
    buf.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(buf), y, rate, subtype="PCM_16")
    take = K.keep_sung(song, "Ana", buf.read_bytes(), "abc123abc123", recorded=time.struct_time((*when, 0, 0, -1)),
                       spec=spec, from_s=from_s, to_s=to_s, **info)
    buf.unlink()
    return take


def near(x: np.ndarray, hz: float, sr: int, a: float, b: float) -> float:
    """How much of x (mono) between a and b seconds is a sine at hz: its amplitude there."""
    seg = x[int(a * sr) : int(b * sr)]
    t = np.arange(len(seg)) / sr
    return float(2 * np.abs(np.mean(seg * np.exp(-2j * np.pi * hz * t))))


def test_sections_and_which_take_sings_each(stems):
    score = json.loads(stems[2].read_text())
    runs = VS.runs(score)
    assert [(r.start, round(r.end, 2), len(r.notes)) for r in runs] == [(1.0, 3.95, 6), (7.0, 9.95, 6)]
    assert VS.cuts(runs, LENGTH) == [(0.0, 5.475), (5.475, LENGTH)]
    whole = sung(VERSE + REFRAIN, 0.0, LENGTH, when=(2026, 9, 27, 19, 0, 0))
    old = sung(REFRAIN, 5.5, 10.4, when=(2026, 9, 27, 19, 30, 0), section=2)
    new = sung(REFRAIN, 5.5, 10.4, when=(2026, 9, 27, 20, 0, 0), section=2)
    assert VS.choose([whole, old, new], runs) == [whole, new]  # the latest sings the refrain
    spans = VS.cuts(runs, LENGTH)
    assert VS.stretches([whole, whole], spans) == [(whole, 0.0, LENGTH)]  # heard straight through, no seam
    assert VS.stretches([whole, new], spans) == [(whole, 0.0, 5.475), (new, 5.475, LENGTH)]
    new.use = False
    assert VS.choose([whole, old, new], runs) == [whole, old]  # unless it's marked not to be used
    short = sung(REFRAIN, 5.5, 8.0, when=(2026, 9, 27, 21, 0, 0), section=2)  # stopped halfway: not the refrain's
    assert VS.choose([old, short], runs) == [None, old]


def test_a_version_has_their_voice_where_they_sang_and_the_machine_elsewhere(stems, tmp_path):
    take = sung(REFRAIN, 5.5, 10.4, section=2)
    runs = VS.runs(json.loads(stems[2].read_text()))
    chosen = VS.choose([take], runs)
    lead, _ = sf.read(str(stems[1]), always_2d=True)
    out, gains = VS.lead_track(chosen, runs, VS.cuts(runs, LENGTH), lead, SR, 1, strip)
    mono = out.mean(axis=1)
    assert near(mono, 220.0, SR, 1.0, 3.9) == pytest.approx(near(lead.mean(axis=1), 220.0, SR, 1.0, 3.9), rel=1e-6)
    assert near(mono, 220.0, SR, 7.0, 9.9) < 1e-3  # the machine steps aside in the refrain
    assert near(mono, 330.0, SR, 7.0, 9.9) > 0.05  # and they sing it
    assert VS.level(out, SR, runs[1].notes) == pytest.approx(VS.level(lead, SR, runs[1].notes), abs=0.5)
    assert 8.0 < gains[take.path] < 16.0  # a take 12 dB under the machine's lead, raised to meet it

    made = VS.make(Path("song.json"), [take, sung(REFRAIN, 5.5, 10.4, spec="a.k-2.t80", section=2)], "a.k0.t100",
                   tmp_path / "out", stems=stems, strip=strip, title="H (your version)")
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=channels,codec_name,bit_rate",
                                       "-show_entries", "format=duration", "-of", "json", str(made.version)],
                                      capture_output=True, text=True, check=True).stdout)
    assert probe["streams"][0]["codec_name"] == "mp3" and probe["streams"][0]["channels"] == 2
    assert int(probe["streams"][0]["bit_rate"]) == 192000 and abs(float(probe["format"]["duration"]) - LENGTH) < 0.2
    assert made.sections == [{"start": 1.0, "end": 3.95, "take": None},
                             {"start": 7.0, "end": 9.95, "take": take.path.name}]
    info = sf.info(str(made.vocals))
    assert (info.channels, info.samplerate, info.subtype) == (1, 48000, "PCM_16")
    vocals, _ = sf.read(str(made.vocals))
    assert len(vocals) == int(LENGTH * 48000)
    assert np.max(np.abs(vocals[: int(5.4 * 48000)])) < 1e-3  # nothing where they didn't sing
    raw, _ = sf.read(str(take.path))
    at = int(5.5 * 48000)
    assert np.allclose(vocals[at + 48000 : at + 96000], raw[48000:96000], atol=1e-4)  # dry, where it was sung
    assert not list((tmp_path / "out").glob("*.part*"))


def test_the_command_makes_a_pair_for_each_spec_they_sang(stems, tmp_path, monkeypatch, capsys):
    made = []

    def stems_for(genome_path, spec):  # tools/guides.py's stems(), as the guides agent makes them
        made.append(spec)
        return stems

    monkeypatch.setitem(sys.modules, "guides", SimpleNamespace(stems=stems_for, voice_strip=strip))
    song = Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json"
    sung(REFRAIN, 5.5, 10.4, section=2, song=song.stem)
    sung(REFRAIN, 5.5, 10.4, spec="a.k-2.t80", section=2, song=song.stem)
    monkeypatch.setattr(sys, "argv", ["versions.py", str(song), "--singer", "Ana", "--spec", "a.k0.t100",
                                      "--out", str(tmp_path / "out")])
    VS.main()
    assert made == ["a.k0.t100"] and (tmp_path / "out" / "a.k0.t100" / "version.mp3").exists()
    assert (tmp_path / "out" / "a.k0.t100" / "vocals.wav").exists()
    assert "1 of 2 sections theirs" in capsys.readouterr().out


def test_only_takes_sung_to_the_spec_count(stems, tmp_path):
    other = sung(REFRAIN, 5.5, 10.4, spec="a.k-2.t80", section=2)
    with pytest.raises(ValueError, match="none of these takes"):
        VS.make(Path("song.json"), [other], "a.k0.t100", tmp_path / "out", stems=stems, strip=strip)
