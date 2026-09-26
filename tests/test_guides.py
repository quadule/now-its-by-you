"""The karaoke's guides: one score, three mixes (tools/guides.py)."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import guides as M  # noqa: E402  (tools/guides.py)
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import takes as K  # noqa: E402  (tools/takes.py)

from songbird import genome as G  # noqa: E402
from songbird.realize import choose_params, timeline  # noqa: E402
from songbird.score import Note, Score  # noqa: E402

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


def short(path: Path = H, form=("intro", "verse")):
    """A genome whose seed rendition is only a few sections long, for a quick guide."""
    g = G.load(path)
    return replace(g, seed_params={**g.seed_params, "form": list(form)})


# --- the melody line ---------------------------------------------------------------------------


def note(part, start, dur, pitch, vel=0.7, syllable=None, art=""):
    return Note(part, start, dur, float(pitch), vel, syllable=syllable, art=art)


def test_the_melody_is_the_sung_line_and_the_bands_statement_where_no_one_sings():
    sung = [note("voice", 4.0 + 0.5 * k, 0.55, 60 + k % 3, syllable="la") for k in range(6)]
    stated = [note("whistle", 0.5 + 0.5 * k, 0.5, 84 + k % 2, vel=0.4) for k in range(6)]  # an intro, two octaves up
    fill = [note("fiddle", 4.2, 0.3, 90)]  # a fill under the singing: not the tune
    score = Score(tuple(sorted(sung + stated + fill, key=lambda n: n.start)), 8.0, (("intro", 0.5, 4.0), ("verse", 4.0, 8.0)))
    line = M.melody_line(score)
    assert [n.start for n in line] == sorted(n.start for n in sung + stated)
    assert all(n.part == "guide" for n in line)
    assert all(a.start + a.dur <= b.start + 1e-9 for a, b in zip(line, line[1:]))  # one line: nothing overlaps
    intro = [n for n in line if n.start < 4.0]
    assert {n.pitch for n in intro} == {60.0, 61.0}  # moved by octaves into the singer's register
    assert np.median([n.vel for n in intro]) == pytest.approx(M.STATED * 0.7)  # a little under the singer
    assert all(n.art == "" for n in line if n.start >= 4.0)  # every syllable tongued


def test_a_short_rest_keeps_the_band_out_of_the_melody():
    sung = [note("voice", 0.2, 0.5, 60, syllable="a"), note("voice", 1.5, 0.5, 62, syllable="b")]
    fill = [note("whistle", 0.8, 0.4, 79)]  # between two lines 0.8 s apart
    line = M.melody_line(Score(tuple(sung + fill), 3.0, (("verse", 0.0, 3.0),)))
    assert [n.pitch for n in line] == [60.0, 62.0]


def test_the_pulse_sits_on_the_beats_and_leans_on_the_downbeats():
    sr = 44100
    beats = [(0.5, True), (1.0, False), (1.5, False)]
    y = M.pulse(beats, sr, 2 * sr)
    for t, _ in beats:
        i = int(round(t * sr))
        assert np.abs(y[i - 200 : i]).max() == 0.0  # silent until the stroke
        assert np.abs(y[i : i + 400]).max() > 0.1
    down, off = np.abs(y[22050:24000]).max(), np.abs(y[44100:46000]).max()
    assert 20 * np.log10(down / off) == pytest.approx(M.PULSE_DB[1] - M.PULSE_DB[0], abs=0.2)
    spectrum = np.abs(np.fft.rfft(M.tock(False, 44100)))
    f = np.fft.rfftfreq(len(M.tock(False, 44100)), 1 / 44100)
    assert spectrum[f < 600].sum() < 0.05 * spectrum.sum()  # nothing to cover the tune's fundamentals


# --- one score, every mix ----------------------------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    return tmp_path


def test_every_mix_follows_one_score(workspace):
    genome = short()
    melody, score = M.ensure(H, genome, "melody")
    full, same = M.ensure(H, genome, "full")
    assert same == score and melody != full
    data = json.loads(score.read_text())
    assert data["seed"] == choose_params(genome).seed and data["tempo"] == choose_params(genome).tempo
    assert [b[0] for b in data["beats"]] == [t for t, _ in timeline(genome, choose_params(genome)).beats()]
    stamp = json.loads(melody.with_suffix(".json").read_text())
    assert stamp["score"] == K.digest(score)  # made from the full guide's score, by digest

    y, sr = sf.read(melody)
    x = y.mean(axis=1)
    assert len(y) >= data["duration"] * sr  # the whole timeline, and the room's tail
    # the sung notes are where the score puts them: each starts where the melody guide gets louder
    hop = int(0.005 * sr)
    env = 20 * np.log10(np.sqrt(np.convolve(x ** 2, np.ones(hop) / hop, mode="same")) + 1e-9)
    sung = [n for n in data["notes"] if n["part"] == "voice"]
    rises = [env[int((n["start"] + 0.03) * sr)] - env[int((n["start"] - 0.005) * sr)] for n in sung]
    assert np.mean(np.array(rises) > 3.0) > 0.9

    # the same take measures the same whichever mix was heard: nothing about the score changed
    again, score_again = M.ensure(H, genome, "melody")
    assert again == melody and K.digest(score_again) == stamp["score"]


def test_a_stale_mix_is_made_again(workspace):
    genome = short(form=("verse",))
    melody, score = M.ensure(H, genome, "melody")
    note_path = melody.with_suffix(".json")
    note_path.write_text(json.dumps({"score": "000000000000", "recipe": M.recipe()}))
    before = melody.stat().st_mtime_ns
    M.ensure(H, genome, "melody")
    assert melody.stat().st_mtime_ns != before
    assert json.loads(note_path.read_text())["score"] == K.digest(score)


def test_a_guide_without_beats_is_written_again(workspace):
    genome = short(form=("verse",))
    _, score = M.ensure(H, genome, "full")
    data = json.loads(score.read_text())
    del data["beats"]
    score.write_text(json.dumps(data))
    assert not M.fresh(H)
    M.ensure(H, genome, "melody")
    assert "beats" in json.loads(score.read_text())
