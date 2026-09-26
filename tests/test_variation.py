"""choose_params: the parent pulled toward the machine as the drift moves it."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import drift as D
from songbird import genome as G
from songbird import harvest as H
from songbird import variation as V
from songbird.realize import Params, choose_params, realize
from songbird.synth.voice import VoiceParams

ROOT = Path(__file__).parent.parent
SONGS = sorted((ROOT / "songs").glob("*.json"))
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
MACHINES = ("ada", "bo", "cy", "dee", "eli", "fox")


@pytest.fixture(scope="module")
def h():
    return G.load(LEAD)


def child(g, name: str, date: str, parent=None):
    voice = H.fictional(name)
    return choose_params(g, parent, voice, D.drift(D.parse(date), voice.hash))


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_no_voice_and_no_drift_is_the_parent_unchanged(path):
    g = G.load(path)
    seed = Params.from_dict(g.seed_params)
    assert choose_params(g) == seed  # the golden render depends on it
    parent = replace(seed, tempo=101.0, choir=2, singer={"rd": 0.9})
    assert choose_params(g, parent) == parent
    assert choose_params(g, seed=7) == replace(seed, seed=7)


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_every_chosen_form_follows_the_template_and_the_verse_rules(path):
    g = G.load(path)
    lo, hi = V.verse_range(g)
    assert V.fits(g, Params.from_dict(g.seed_params).form)
    allowed = V.allowed_modes(g, g.seed_params["mode"])
    counts = set()
    for name in MACHINES[:3]:
        voice = H.fictional(name)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2028-01-01"), 9.1):
            p = choose_params(g, voice=voice, drift=D.drift(t, voice.hash))
            assert V.fits(g, p.form), p.form
            counts.add(sum(V.is_verse(g, s) for s in p.form))
            assert p.mode in allowed
    assert counts <= set(range(lo, hi + 1)) and len(counts) > 1


def test_the_lead_songs_forms(h):
    assert V.verse_range(h) == (2, 4)  # the bank's rule
    refrains = lambda form: sum(s == "refrain" for s in form)  # noqa: E731
    assert refrains(V.build(h, 2, {})) == 3 and refrains(V.build(h, 4, {})) == 5  # each verse brings its refrain
    assert refrains(V.build(h, 4, {}, pairs=True)) == 4
    long = V.build(h, 4, {(4, "turn", r): True for r in range(3)})
    assert " ".join(long) == "verse refrain verse refrain turn verse refrain turn verse refrain turn bridge refrain"
    seen = set()
    for name in MACHINES:
        for date in ("2026-09-25", "2026-10-25", "2027-01-25", "2027-06-25", "2027-09-25"):
            p = child(h, name, date)
            assert V.fits(h, p.form)
            seen |= set(p.form)
            score = realize(h, p)  # every form can be sung
            assert score.part("voice")
    assert {"intro", "turn", "tag", "outro"} <= seen


def test_same_machine_instant_and_parent_same_child(h):
    a, b = child(h, "ada", "2027-02-02"), child(h, "ada", "2027-02-02")
    assert a == b
    assert child(h, "ada", "2027-02-03").seed != a.seed  # a new day, a new rendition seed
    code = ("import json; from songbird import genome as G, drift as D, harvest as H; from songbird.realize import "
            f"choose_params; g = G.load({str(LEAD)!r}); v = H.fictional('ada'); "
            "print(json.dumps(choose_params(g, None, v, D.drift(D.parse('2027-02-02'), v.hash)).to_dict()))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT,
                         env={**os.environ, "PYTHONHASHSEED": "99"})
    assert json.loads(out.stdout) == json.loads(json.dumps(a.to_dict()))


def sings(params, field: str):
    return V.read(params, f"singer.{field}")  # a field the machine left at its default isn't written


def test_two_machines_are_two_singers(h):
    children = [child(h, name, "2026-09-25") for name in MACHINES]
    bodies = {(sings(p, "shift"), sings(p, "tract"), sings(p, "vibrato_rate")) for p in children}
    assert len(bodies) == len(MACHINES)
    assert {sings(p, "shift") for p in children} == {0, -12}  # low singers and high ones
    assert len({p.room["rt60"] for p in children}) > 1


def test_a_neutral_machine_sings_like_its_parent(h):
    seed = Params.from_dict(h.seed_params)
    p = choose_params(h, voice=H.Voice(salt="locked-down"))
    assert (p.tonic, p.mode, p.tempo, p.accomp, p.singer, p.room) == (seed.tonic, seed.mode, seed.tempo, seed.accomp,
                                                                        {}, {})
    assert p.choir == seed.choir + 1  # still a generation
    assert V.fits(h, p.form)


def test_a_lineage_keeps_its_accent(h):
    seed = Params.from_dict(h.seed_params)
    a, b = H.fictional("ada"), H.fictional("cy")
    first = choose_params(h, None, a)
    second = choose_params(h, first, b)
    alone = choose_params(h, None, b)  # machine b singing straight from the seed
    own = V.character(b)
    b_tempo = seed.tempo * 2 ** (0.18 * own.pace)
    assert abs(second.tempo - (first.tempo + V.PULL * (b_tempo - first.tempo))) < 0.11
    assert abs(second.tempo - alone.tempo) > 0.1 and np.sign(second.tempo - alone.tempo) == np.sign(first.tempo - seed.tempo)
    body = ("shift", "tract", "mouth", "tilt", "vibrato_rate", "jitter", "shimmer")
    assert all(sings(second, k) == sings(alone, k) for k in body)  # the body is b's own
    learned = ("rd", "breath", "vibrato_depth", "vibrato_delay", "glide", "scoop", "wander", "dynamics")
    assert sum(sings(second, k) != sings(alone, k) for k in learned) >= 3  # its habits carry something of a
    assert (first.choir, second.choir) == (1, 2)
    for _ in range(8):
        second = choose_params(h, second, b)
    assert second.choir == V.CHOIR_MAX


def test_the_modes_chosen_keep_every_chord_a_triad(h):
    assert V.allowed_modes(h, "ionian") == ("ionian", "mixolydian", "aeolian")
    for name in MACHINES:
        voice = H.fictional(name)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2029-01-01"), 30.0):
            mode = choose_params(h, voice=voice, drift=D.drift(t, voice.hash)).mode
            members = V.MODE_FAMILIES[voice.tongue.family][0]
            assert mode in V.allowed_modes(h, "ionian") and mode in members


def test_the_table_is_wired():
    params = {f for f in Params.__dataclass_fields__}
    for knob in V.KNOBS:
        head, _, tail = knob.path.partition(".")
        assert head in params
        if head == "singer":
            assert hasattr(VoiceParams(), tail), knob.path
        if head == "leanings":
            assert tail in V.LEANINGS
        if knob.drift:
            assert knob.drift in D.DIMENSIONS, knob.path
        assert knob.view in D.VIEWS
    for dimension in list(V.SECTION_DRIFT.values()) + ["verses", "pairs", "extra", "texture", "mood", "mode", "key"]:
        assert dimension in D.DIMENSIONS


def test_leanings_for_the_lyric(h):
    p = child(h, "ada", "2026-09-25")
    lean = p.leanings
    assert set(lean) >= {"mood", "era", "rarity", "vocabulary", "extra_bridge"}
    assert set(lean["mood"]) == {"plain", "light", "dark", "tender"}
    assert abs(sum(lean["mood"].values()) - 4) < 0.05
    assert -1 <= lean["era"] <= 1 and 0 <= lean["rarity"] <= 1
    assert lean["vocabulary"] and set(lean["vocabulary"]) <= V.song_words(h)  # only the song's own words


def test_lay_moves_only_the_singers(h):
    p = replace(Params.from_dict(h.seed_params), lay=0.05, choir=1)
    score = realize(h, replace(p, lay=0.0))
    moved = V.lay(score, p)
    beat = 60.0 / p.tempo
    before = {(n.part, n.pitch, n.syllable, round(n.start, 6)) for n in score.notes if n.part != "voice" and not n.part.startswith("choir")}
    after = {(n.part, n.pitch, n.syllable, round(n.start, 6)) for n in moved.notes if n.part != "voice" and not n.part.startswith("choir")}
    assert before == after
    lead_before = sorted(n.start for n in score.part("voice"))
    lead_after = sorted(n.start for n in moved.part("voice"))
    assert all(abs((a - b) - 0.05 * beat) < 1e-9 for a, b in zip(lead_before, lead_after) if a > 0.05 * beat)
    assert V.lay(score, replace(p, lay=0.0)) is score
