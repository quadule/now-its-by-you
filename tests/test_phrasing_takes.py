"""The sung-take extractor (tools/phrasing.py) with takes of one section, and guides in other keys and speeds.

Every take here is the formant singer singing a guide with a phrasing planted in it, so what it did is
known; MFA is off, as it is wherever it isn't installed."""

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import speech_to_song as S  # noqa: E402
import takes as K  # noqa: E402

from songbird import arrange  # noqa: E402
from songbird import genome as G  # noqa: E402
from songbird import phrasing as P  # noqa: E402
from songbird.realize import choose_params, realize, sung_as, timeline  # noqa: E402
from songbird.synth import voice as V  # noqa: E402

H = Path(__file__).parent.parent / "songs" / "h-now-its-by-you.json"
FORM = ("verse", "turn", "verse", "turn", "refrain")  # a second verse and a last refrain, a turn before each


@pytest.fixture(scope="module")
def studio(tmp_path_factory):
    """Recordings and measurements of their own (MFA off), for every test here."""
    root = tmp_path_factory.mktemp("studio")
    T.version()  # what the extractor is, read from this checkout before ROOT moves
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MFA", "off")
        mp.setattr(T, "ROOT", root)
        mp.setattr(T, "MEASURED", root / "renders" / "measured")
        mp.setattr(K, "ROOT", root)
        mp.setattr(K, "RECORDINGS", root / "recordings")
        mp.setattr(K, "GUIDES", root / "recordings" / "guides")
        yield root


def guide_for(root: Path, genome, form=FORM, key: int = 0, tempo: int = 100):
    """A guide as tools/guides.py writes a spec's: the seed's rendition in this form, moved key semitones and
    played at tempo percent, its score kept beside the takes. Returns its Guide, the spec id and its beats."""
    params = choose_params(genome)
    params = replace(params, form=tuple(form), tonic=params.tonic + key, tempo=params.tempo * tempo / 100)
    score = realize(genome, params)
    beats = [[t, int(bar)] for t, bar in timeline(genome, params).beats()]
    spec = f"song.k{key}.t{tempo}"
    data = {**score.to_dict(), "tempo": params.tempo, "seed": params.seed, "transpose": key, "beats": beats,
            "spec": {"id": spec, "set": "song", "key": key, "tempo": tempo}}
    path = root / f"{'-'.join(form)}.{spec}.score.json"
    path.write_text(json.dumps(data) + "\n")
    return T.guide(H, genome, K.keep_guide(H.stem, path)), spec, [b for b, _ in beats]


def planted(g, seed: int = 5) -> list[P.Gesture]:
    """A singer's way with every note of a guide, one gesture for each (phrase, place) wherever it comes
    round: a little behind the beat, some notes pushed or pulled, scooping into most."""
    rng = np.random.default_rng(seed)
    way = {}
    for k, n in enumerate(g.notes):
        early, scoop = float(np.clip(rng.normal(-0.04, 0.05), -0.15, 0.15)), float(rng.normal(-30, 20))
        way.setdefault((n.phrase, T.index_in_phrase(g.notes, k)), P.Gesture(early=early, scoop=scoop))
    return [way[(n.phrase, T.index_in_phrase(g.notes, k))] for k, n in enumerate(g.notes)]


def sing(g, gestures, shift: int = 0, seed: int = 3) -> np.ndarray:
    """The guide's notes sung with these gestures by the formant singer, shift semitones from the guide, and
    a quiet room after the last note until the guide ends, as a take goes on until it's stopped."""
    beat = 60.0 / g.tempo
    y = V.sing([sung_as(n, ge, beat) for n, ge in zip(g.notes, gestures)], S.SR,
               V.VoiceParams(engine="formant", shift=shift), seed, g.lexicon)
    y = np.pad(y / np.max(np.abs(y)) * 0.5, (0, int(3.0 * S.SR)))
    return y + 1e-4 * np.random.default_rng(seed).standard_normal(len(y))


def window(g, beats, section: tuple) -> tuple[float, float]:
    """A section's window as the karaoke gives it: from two bars before its first sung note (on a beat) to
    a beat after its last ends."""
    name, s0, s1 = section
    inside = [n for n in g.notes if s0 - 1.0 <= n.start < s1]
    beat = 60.0 / g.tempo
    from_s = max([b for b in beats if b <= inside[0].start - 8 * beat] or [0.0])
    return from_s, inside[-1].start + inside[-1].dur + beat


def keep(singer: str, y: np.ndarray, g, spec: str, **info) -> K.Take:
    buf = Path(K.RECORDINGS / "incoming.wav")
    buf.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(buf), y.astype(np.float32), S.SR, subtype="FLOAT")
    take = K.keep_sung(H.stem, singer, buf.read_bytes(), g.digest, spec=spec, **info)
    buf.unlink()
    return take


@pytest.fixture(scope="module")
def sung(studio):
    """A whole take of FORM, and what the extractor makes of it."""
    genome = G.load(H)
    g, spec, beats = guide_for(studio, genome)
    gestures = planted(g)
    y = sing(g, gestures)
    whole = keep("Ana", y, g, spec)
    return dict(genome=genome, g=g, spec=spec, beats=beats, gestures=gestures, y=y, whole=whole,
                measured=T.measured(H, genome, whole),
                sections=json.loads(K.guide_score(H.stem, g.digest).read_text())["sections"])


@pytest.mark.parametrize("which", [2, 4])  # the second verse, the last refrain
def test_a_take_of_one_section_measures_its_own_notes(sung, which):
    g, whole = sung["g"], sung["measured"]
    from_s, to_s = window(g, sung["beats"], sung["sections"][which])
    y = sung["y"][int(round(from_s * S.SR)) : int(round(to_s * S.SR))]
    take = keep("Ana", y, g, sung["spec"], from_s=from_s, to_s=to_s, section=which)
    data = T.measured(H, sung["genome"], take)
    assert (data["stamp"]["from_s"], data["stamp"]["to_s"]) == (round(from_s, 4), round(to_s, 4))
    assert "from_s" not in whole["stamp"] and "window" not in whole  # a whole take's measurement is as ever
    inside = [k for k, n in enumerate(g.notes) if from_s <= n.start < to_s]
    name, s0, s1 = sung["sections"][which]
    assert inside and all(s0 - 1.0 <= g.notes[k].start < s1 for k in inside)
    assert [k for k, n in enumerate(data["notes"]) if n["gesture"] is not None] == inside  # its own notes, no others
    assert all(data["notes"][k]["onset"] is None and data["notes"][k]["off"] is None
               for k in range(len(g.notes)) if k not in inside)
    assert data["lag"] == 0.0 and data["key"] == whole["key"] == 0
    onsets = np.array([data["notes"][k]["onset"] for k in inside])
    same = np.array([whole["notes"][k]["onset"] for k in inside])
    assert np.mean(np.abs(onsets - same) <= 0.010) >= 0.9 and np.sum(np.abs(onsets - same) > 0.03) <= 2
    early = np.array([data["notes"][k]["gesture"][0] for k in inside], dtype=float)
    truth = np.array([sung["gestures"][k].early for k in inside])
    assert np.corrcoef(early, truth)[0, 1] > 0.5  # it hears the way they were sung
    assert K.caches(take)[0].exists() and T.measured(H, sung["genome"], take) == data  # kept, and read back


def test_a_late_take_of_one_section_is_found_where_it_was_sung(sung):
    g, whole = sung["g"], sung["measured"]
    from_s, to_s = window(g, sung["beats"], sung["sections"][2])
    y = sung["y"][int(round(from_s * S.SR)) : int(round(to_s * S.SR))]
    late = np.concatenate([np.zeros(int(0.4 * S.SR)), y])  # their device ran 0.4 s behind, past the sync
    data = T.measure_window(keep("Ana", late, g, sung["spec"]).path, g, from_s, to_s + 0.4)
    assert abs(data["lag"] - 0.4) <= 0.05
    inside = [k for k, n in enumerate(g.notes) if from_s <= n.start < to_s]
    moved = np.array([data["notes"][k]["onset"] for k in inside]) - 0.4
    same = np.array([whole["notes"][k]["onset"] for k in inside])
    assert np.median(np.abs(moved - same)) <= 0.01


def test_a_take_that_stopped_leaves_the_rest_unmeasured(sung):
    g = sung["g"]
    stop = sung["sections"][3][1] + 1.0  # the singer stopped in the turn before the refrain
    y = sung["y"][: int(stop * S.SR)]
    spec = sung["spec"]
    data = T.measured(H, sung["genome"], keep("Bo", y, g, spec, from_s=0.0, to_s=stop))
    sang = [k for k, n in enumerate(data["notes"]) if n["gesture"] is not None]
    assert sang == [k for k, n in enumerate(g.notes) if n.start < stop]
    assert data["window"] == pytest.approx([0, stop], abs=1e-3)
    # a take that doesn't say where it stopped stops where its sound does; one sung to the end is a whole take
    assert T.window_of(keep("Bo", y, g, spec, from_s=0.0, to_s=80.0), g) == pytest.approx((0, stop), abs=1e-3)
    assert T.window_of(keep("Bo", sung["y"], g, spec, from_s=0.0, to_s=80.0), g) is None
    assert T.window_of(sung["whole"], g) is None  # and so is one from before takes said where they start


def test_a_phrasing_counts_what_each_take_sang_once_a_person(sung):
    g, genome, spec = sung["g"], sung["genome"], sung["spec"]
    from_s, to_s = window(g, sung["beats"], sung["sections"][2])
    part = sung["y"][int(round(from_s * S.SR)) : int(round(to_s * S.SR))]
    info = dict(from_s=from_s, to_s=to_s, section=2)
    twice = [keep("Ana", part, g, spec, **info), keep("Ana", part, g, spec, **info)]  # who sang the whole take too
    seen, (words, weights), portrait = T.sung_phrasing(H, genome, twice)
    verse = {(n.phrase, T.index_in_phrase(g.notes, k)) for k, n in enumerate(g.notes) if from_s <= n.start < to_s}
    assert set(seen) == verse  # the refrain wasn't sung: no sightings of it at all
    assert all(sum(w) == pytest.approx(len(w) / 2) for w in weights.values())  # the same place twice: half each
    assert len(portrait) == 2 and all(len(p[3]) == len(verse) + 11 for p in portrait)  # v2 comes round twice
    # with a whole take by the same person, a place both sang counts a third each; one only the whole sang, fully
    seen, (words, weights), _ = T.sung_phrasing(H, genome, [sung["whole"], *twice])
    r1 = [w for (phrase, _), w in weights.items() if phrase == "r1"]
    v1 = weights[("v1", 0)]  # sung in both verses by the whole take, the second verse by the two others
    assert all(x == [1.0] for x in r1) and sorted(v1) == pytest.approx([1 / 3, 1 / 3, 1 / 3, 1.0])
    _, data, _ = T.singer_phrasing(H, genome, [sung["whole"], *twice], "Ana")
    assert data["source_detail"] == f"3 sung take(s) by Ana, 2 of one section; sung to {spec} (3)"


def test_the_key_is_read_in_any_key_and_an_octave_down(studio):
    genome = G.load(H)
    g, _, _ = guide_for(studio, genome, ("verse",))
    frames = int(g.notes[-1].start / S.FRAME) + 400
    for shift in (-4, -3, -2, -1, 0, 1, 2, 3, 4, -12, -16, -8):  # f0 alone: a singer in their own key
        f0 = np.zeros(frames)
        for (_, v0, v1, *_r), n in zip(g.knots, g.notes):
            f0[int(v0 / S.FRAME) : int(v1 / S.FRAME)] = 440.0 * 2 ** ((n.pitch + shift - 69 + 0.3) / 12)
        assert T.find_key(f0, g, 0) == shift


@pytest.mark.parametrize("key,shift", [(-4, 0), (4, -12)])
def test_a_guide_in_another_key_is_measured_in_it(studio, key, shift):
    genome = G.load(H)
    g, spec, _ = guide_for(studio, genome, ("verse",), key=key)
    assert g.notes[0].pitch == guide_for(studio, genome, ("verse",))[0].notes[0].pitch + key
    gestures = planted(g)
    data = T.measured(H, genome, keep("Di", sing(g, gestures, shift), g, spec))
    assert data["key"] == shift  # sung along in the guide's key, or an octave under it
    early = np.array([n["gesture"][0] for n in data["notes"]], dtype=float)
    truth = np.array([ge.early for ge in gestures])
    ok = np.isfinite(early)
    assert ok.mean() > 0.9 and np.corrcoef(early[ok], truth[ok])[0, 1] > 0.5
    offs = np.array([n["off"] for n in data["notes"] if n["off"] is not None])
    assert np.median(np.abs(offs)) < 30  # on the tune: the template sang in the same key


def test_timing_is_kept_in_beats_so_a_slow_take_carries_to_the_song_s_own_speed(sung, studio):
    """A singer who lands an eighth of a beat late at 80% is an eighth of a beat late at full speed: early is
    measured in beats of the tempo they heard and a phrasing is sung in beats (realize.sung_as), hold as a
    share of the note, so nothing needs scaling by the spec's tempo."""
    genome = sung["genome"]
    g, spec, _ = guide_for(studio, genome, ("verse",), tempo=80)
    gestures = planted(g)  # the same way with the same notes as the whole take at full speed
    assert gestures == sung["gestures"][: len(g.notes)]
    data = T.measured(H, genome, keep("Ed", sing(g, gestures), g, spec))

    def early(d, n):
        return np.array([np.nan if x["gesture"][0] is None else x["gesture"][0] for x in d["notes"][:n]])

    slow, full = early(data, len(g.notes)), early(sung["measured"], len(g.notes))
    truth = np.array([ge.early for ge in gestures])
    ok = np.isfinite(slow) & np.isfinite(full)
    assert ok.mean() > 0.9 and np.corrcoef(slow[ok], truth[ok])[0, 1] > 0.5
    assert abs(np.nanmedian(slow) - np.nanmedian(full)) < 0.02  # the same lean, in beats
    assert np.median(np.abs(slow[ok] - full[ok])) < 0.03


def test_bank_words_keep_the_seed_s_note_keys():
    """A phrasing is keyed by (phrase, place in phrase), so a gesture learned on one set of words must land on
    the same note of the tune under any other. Every line of the bank fits its phrase's notes exactly (the
    bank's check, and Lyrics.lines_for, refuse one that doesn't), so words from the bank move no note."""
    genome = G.load(H)
    form = ("intro", "verse", "turn", "refrain", "turn", "verse", "turn", "refrain", "turn", "bridge", "turn",
            "refrain", "turn", "tag")
    params = replace(choose_params(genome), form=form)

    def keyed(score):
        notes = sorted(score.part("voice"), key=lambda n: n.start)
        return [(n.phrase, T.index_in_phrase(notes, k), n.pitch, round(n.start, 6)) for k, n in enumerate(notes)], \
            [n.syllable for n in notes]

    seed_keys, seed_words = keyed(realize(genome, params))
    for s in (1, 2, 3):
        drawn = arrange.arrange(genome, form, s)
        sung = arrange.sing(genome, form, arrange.hold(genome, drawn))
        keys, words = keyed(realize(genome, params, lyrics=sung))
        assert keys == seed_keys and words != seed_words
    for (phrase, index, _, _) in seed_keys:
        assert index < len(genome.phrases[phrase].sung)
