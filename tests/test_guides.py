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
    by = {part: [n for n in line if n.part == part] for part in ("sung", "stated")}
    assert len(by["sung"]) == 6 and len(by["stated"]) == 6 and len(line) == 12
    for part in by.values():  # each one line: nothing overlaps
        assert all(a.start + a.dur <= b.start + 1e-9 for a, b in zip(part, part[1:]))
    assert {n.pitch for n in by["stated"]} == {84.0, 85.0}  # at the band's own octave: the singer's entry drops below it
    assert np.median([n.vel for n in by["stated"]]) == pytest.approx(M.STATED * 0.7)  # under the singer's level
    assert all(n.art == "" for n in by["sung"])  # every syllable tongued


def test_a_short_rest_keeps_the_band_out_of_the_melody():
    sung = [note("voice", 0.2, 0.5, 60, syllable="a"), note("voice", 1.5, 0.5, 62, syllable="b")]
    fill = [note("whistle", 0.8, 0.4, 79)]  # between two lines 0.8 s apart
    line = M.melody_line(Score(tuple(sung + fill), 3.0, (("verse", 0.0, 3.0),)))
    assert [(n.pitch, n.part) for n in line] == [(60.0, "sung"), (62.0, "sung")]


def test_the_pulse_sits_on_the_beats_and_leans_on_the_downbeats():
    sr = 44100
    beats = [(0.5, True), (1.0, False), (1.5, False)]
    y = M.pulse(beats, sr, 2 * sr)
    for t, _ in beats:
        i = int(round(t * sr))
        assert np.abs(y[i - 200 : i]).max() == 0.0  # silent until the stroke
        assert np.abs(y[i : i + 400]).max() > 0.1
    down, off = np.abs(y[22050:24000]).max(), np.abs(y[44100:46000]).max()
    assert 20 * np.log10(down / off) == pytest.approx(M.PULSE_DB["downbeat"] - M.PULSE_DB["beat"], abs=0.2)


def test_the_pulse_counts_each_entry_in_and_steps_back_under_the_singing():
    beats = [(0.5 * k, k % 4 == 0) for k in range(24)]  # 4/4 at 120, bar lines every 2 s
    # a line on a pickup at 3.75 s (half a beat before the bar at 4.0) to 7.0 s; a rest; the next line on 10.0 s
    sung = [note("voice", 3.75 + 0.25 * k, 0.25, 60, syllable="la") for k in range(13)]
    sung += [note("voice", 10.0 + 0.5 * k, 0.5, 62, syllable="la") for k in range(2)]
    marks = {t: (kind, db) for t, kind, db in M.strokes(beats, sung)}
    assert [t for t, (kind, _) in marks.items() if kind == "count"] == [2.0, 2.5, 3.0, 3.5, 8.0, 8.5, 9.0, 9.5]
    assert marks[3.5][1] == M.PULSE_DB["count"] - M.PULSE_DB["downbeat"]  # counted in, louder than a downbeat
    under = M.PULSE_DB["beat"] - M.PULSE_DB["downbeat"]  # a beat against a downbeat
    assert marks[4.0] == ("downbeat", -M.DUCK_DB) and marks[4.5] == ("beat", under - M.DUCK_DB)
    assert marks[7.5] == ("beat", under)  # the rest: not ducked
    assert marks[10.0][0] == "downbeat"  # the entry itself isn't part of its count-in
    assert M.entries(sorted(sung, key=lambda n: n.start)) == [3.75, 10.0]
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
    melody, score, digest = M.ensure(H, genome, "melody")
    full, same, same_digest = M.ensure(H, genome, "full")
    assert same == score and melody != full and digest == same_digest == K.digest(score)
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
    again = M.ensure(H, genome, "melody")
    assert again.wav == melody and again.digest == stamp["score"]


def test_a_stale_mix_is_made_again(workspace):
    genome = short(form=("verse",))
    melody, score, _ = M.ensure(H, genome, "melody")
    note_path = melody.with_suffix(".json")
    note_path.write_text(json.dumps({"score": "000000000000", "recipe": M.recipe()}))
    before = melody.stat().st_mtime_ns
    M.ensure(H, genome, "melody")
    assert melody.stat().st_mtime_ns != before
    assert json.loads(note_path.read_text())["score"] == K.digest(score)


def test_a_spec_is_only_what_is_on_offer():
    spec = M.Spec.parse("a.k-2.t90")
    assert (spec.set, spec.key, spec.tempo, spec.id) == ("a", -2, 90, "a.k-2.t90")
    assert spec.to_dict() == {"id": "a.k-2.t90", "set": "a", "key": -2, "tempo": 90}
    assert M.Spec.parse("song.k0.t100") == M.Spec("song")
    for bad in ("a.k+2.t90", "a.k3.t90", "a.k0.t95", "a.k-0.t100", "a.k02.t100", "A.k0.t100", "toolongset.k0.t100",
                "a.k0", "../x.k0.t100", "", None):
        with pytest.raises(ValueError):
            M.Spec.parse(bad)


def test_the_singers_arrangement_puts_the_band_between_sung_sections():
    genome = G.load(H)
    assert M.arrangement(genome, ["intro", "verse", "refrain", "verse", "refrain", "bridge", "refrain", "tag"]) == (
        "intro", "verse", "turn", "refrain", "turn", "verse", "turn", "refrain", "turn", "bridge", "turn", "refrain",
        "turn", "tag")
    # an existing turn isn't doubled, nor is one put after something unsung
    assert M.arrangement(genome, ["verse", "turn", "refrain", "break", "verse"]) == ("verse", "turn", "refrain", "break",
                                                                                      "verse")


def held(genome, form, seed):
    """Words a set might hold: drawn from the bank for a form, as a lineage keeps them."""
    from songbird import arrange

    return arrange.hold(genome, arrange.arrange(genome, form, seed))


@pytest.fixture
def specs(workspace, monkeypatch):
    """A short H on disk and a sets file of its own: set "a" sings drawn words in a short form, "b"
    the song's own words in its own form."""
    data = json.loads(H.read_text())
    data["seed_params"]["form"] = ["verse"]
    path = workspace / "h-short.json"
    path.write_text(json.dumps(data))
    genome = G.load(path)
    monkeypatch.setattr(M, "SETS", workspace / "sets")
    sets = {"song": "h-short", "sets": [
        {"id": "a", "name": "Set A", "about": "two verses and a refrain", "form": ["verse", "refrain", "verse"],
         "words": held(genome, ["verse", "refrain", "verse"], 5)},
        {"id": "b", "name": "Set B", "about": "the song's own"}]}
    (workspace / "sets").mkdir()
    (workspace / "sets" / "h-short.json").write_text(json.dumps(sets))
    return path


def test_sets_come_from_the_sets_file_or_are_the_song(specs, workspace):
    have = M.sets(specs)
    assert [s["id"] for s in have] == ["a", "b"] and have[1]["form"] == ["verse"] and have[1]["words"] is None
    assert M.variants(specs) == {"sets": [{"id": "a", "name": "Set A", "about": "two verses and a refrain"},
                                          {"id": "b", "name": "Set B", "about": "the song's own"}],
                                 "keys": [-4, -2, 0, 2, 4], "tempos": [100, 90, 80], "mixes": ["melody", "full", "voice"],
                                 "default": {"set": "a", "key": 0, "tempo": 100, "mix": "melody"}}
    (workspace / "sets" / "h-short.json").unlink()
    assert [(s["id"], s["form"], s["words"]) for s in M.sets(specs)] == [("song", ["verse"], None)]
    (workspace / "sets" / "h-short.json").write_text(json.dumps({"sets": [{"id": "Set A"}]}))
    with pytest.raises(ValueError, match="lowercase"):
        M.sets(specs)


def test_a_spec_score_is_the_set_in_the_singers_arrangement_at_its_key_and_speed(specs):
    score = M.spec_score(specs, "a.k2.t80")
    assert sorted(p.name for p in score.parent.iterdir()) == ["a.k2.t80.note.json", "a.k2.t80.score.json"]  # no audio
    data = json.loads(score.read_text())
    assert data["spec"] == {"id": "a.k2.t80", "set": "a", "key": 2, "tempo": 80}
    seed = choose_params(G.load(specs))
    assert data["tempo"] == pytest.approx(seed.tempo * 0.8) and data["transpose"] == 2 and data["seed"] == seed.seed
    assert [s[0] for s in data["sections"]] == ["verse", "turn", "refrain", "turn", "verse"]
    turn = data["sections"][1]
    assert turn[2] - turn[1] == pytest.approx(2 * 4 * 60 / data["tempo"])  # two bars of the band alone
    assert not [n for n in data["notes"] if n["part"] == "voice" and turn[1] + 0.1 < n["start"] < turn[2] - 0.5]
    # the set's words, a tone up from the song's own key
    song = json.loads(M.spec_score(specs, "b.k0.t100").read_text())
    first = [n for n in data["notes"] if n["part"] == "voice"][0]
    assert first["pitch"] == [n for n in song["notes"] if n["part"] == "voice"][0]["pitch"] + 2
    held_verse = M.find_set(specs, "a")["words"]["verses"][0]["id"]
    assert held_verse in {v["id"] for v in G.load(specs).source["bank"]["verses"]}
    # asked for again: the same file, untouched; stale once the set changes
    before = score.stat().st_mtime_ns
    assert M.spec_score(specs, "a.k2.t80") == score and score.stat().st_mtime_ns == before
    sets = json.loads(M.SETS.joinpath("h-short.json").read_text())
    sets["sets"][0]["form"] = ["verse", "verse"]
    sets["sets"][0]["words"] = held(G.load(specs), ["verse", "verse"], 9)
    M.SETS.joinpath("h-short.json").write_text(json.dumps(sets))
    assert [s[0] for s in json.loads(M.spec_score(specs, "a.k2.t80").read_text())["sections"]] == ["verse", "turn", "verse"]


def test_a_spec_has_every_mix_and_stems_that_make_the_full_guide(specs):
    melody, score, digest = M.ensure_spec(specs, "b.k-2.t100")
    assert melody == M.spec_path("h-short", "b.k-2.t100", "melody") and digest == K.digest(score)
    for mix in M.MIXES:
        assert M.spec_path("h-short", "b.k-2.t100", mix).exists()
    assert not M.spec_path("h-short", "b.k-2.t100", "band").exists()  # the stems only when asked for
    full = M.spec_path("h-short", "b.k-2.t100", "full")
    before = full.stat().st_mtime_ns
    assert M.ensure_spec(specs, "b.k-2.t100", "full").wav == full and full.stat().st_mtime_ns == before  # kept

    band, lead, same = M.stems(specs, "b.k-2.t100")
    assert same == score and K.digest(score) == digest  # the same score, so every take still measures
    b, sr = sf.read(band)
    v, _ = sf.read(lead)
    y, _ = sf.read(full)
    assert sf.info(band).subtype == "FLOAT" and b.shape == v.shape == y.shape
    from songbird.synth import master

    data = json.loads(score.read_text())
    pcm = master.to_pcm16(master.master(b + v, sr), seed=data["seed"]).astype(int)
    assert np.abs(pcm - np.round(y * 32768).astype(int)).max() <= 1  # the full guide, to the dither's last bit
    # the lead is the voice (and its room): quiet where no one sings, where the band plays on
    sung = [n for n in data["notes"] if n["part"] == "voice"]
    a, z = int((sung[-1]["start"] + sung[-1]["dur"] + 2.0) * sr), int((data["duration"] - 0.2) * sr)
    rms = lambda x: np.sqrt(np.mean(x ** 2))  # noqa: E731
    if z - a > sr // 2:
        assert rms(v[a:z]) < 0.05 * rms(b[a:z])
    inside = np.concatenate([v[int(n["start"] * sr) + 2000 : int((n["start"] + n["dur"]) * sr)] for n in sung])
    assert rms(inside) > 0.3 * rms(b)


def test_a_phrasing_moves_the_machines_singing_but_not_the_score(specs, workspace):
    from songbird import phrasing as P

    score = M.spec_score(specs, "b.k0.t100")
    grid, data = M.load_score(score)
    genome = G.load(specs)
    late = {pid: tuple(P.Gesture(early=-0.25) for _ in phrase.sung) for pid, phrase in genome.phrases.items()}
    path = workspace / "late.json"
    path.write_text(json.dumps(P.to_json(late, source="test")))
    sung = M.phrased(grid, data, path)
    before, after = grid.part("voice"), sung.part("voice")
    assert len(before) == len(after)
    assert all(b.start + 0.25 * 60 / data["tempo"] == pytest.approx(a.start) for a, b in zip(after, before))
    assert [n for n in sung.notes if n.part != "voice"] == [n for n in grid.notes if n.part != "voice"]
    digest = K.digest(score)
    M.ensure_spec(specs, "b.k0.t100", "full", phrasing=path)
    assert K.digest(score) == digest and json.loads(M.spec_path("h-short", "b.k0.t100", "note").read_text())["audio"][
        "phrasing"] == K.digest(path)


def test_a_take_goes_through_the_machines_strip_and_room():
    sr = 44100
    t = np.arange(2 * sr) / sr
    dry = 0.1 * np.sin(2 * np.pi * 220 * t) * (t > 0.5)
    wet = M.voice_strip(dry, sr, 1)
    assert wet.ndim == 2 and wet.shape[1] == 2 and len(wet) > len(dry)  # stereo, with the room's tail
    assert np.abs(wet[len(dry):]).max() > 0  # the room rings on
    assert np.corrcoef(wet[:, 0], wet[:, 1])[0, 1] > 0.8  # in the middle, the room around it


def test_a_guide_without_beats_is_written_again(workspace):
    genome = short(form=("verse",))
    score = M.ensure(H, genome, "full").score
    data = json.loads(score.read_text())
    before = [n["pitch"] for n in data["notes"] if n["part"] == "voice"]
    del data["beats"]
    data["transpose"] = 2  # a guide someone asked for two semitones up (phrasing.py --guide --transpose 2)
    score.write_text(json.dumps(data))
    assert not M.fresh(H)
    M.ensure(H, genome, "melody")
    again = json.loads(score.read_text())
    assert "beats" in again and again["transpose"] == 2  # written again, still where they sing it
    assert [n["pitch"] for n in again["notes"] if n["part"] == "voice"] == [x + 2 for x in before]
