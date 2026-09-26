"""Variants: small departures from the written tune never break what the genome keeps (the contour, the
phrase targets, the stress, the mode and the chords), keep off the hooks and the refrain's first line,
stay under the bound, and are sung inside their note; with none, everything sounds exactly as before."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G
from songbird import variants as V
from songbird import variation
from songbird.realize import Params, choose_params, realize
from songbird.synth.voice import BLOCK, VoiceParams, pitch_track
from songbird.theory import MODES, degree_semitones

ROOT = Path(__file__).parent.parent
SONGS = sorted((ROOT / "songs").glob("*.json"))
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture(scope="module")
def h():
    return G.load(LEAD)


def moves(degrees) -> str:
    out = []
    for a, b in zip(degrees, degrees[1:]):
        step = b - a
        out.append("h" if step == 0 else "u" if step == 1 else "d" if step == -1 else "U" if step > 0 else "D")
    return " ".join(out)


def greedy(g, rng, tries=400):
    """A full set of variants, as a long lineage might gather: random candidates, each kept if it fits."""
    offered = list(V.candidates(g))
    chosen: list = []
    for i in rng.permutation(len(offered))[:tries]:
        if V.fits(g, chosen, offered[i]):
            chosen.append(offered[i])
    return chosen


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_every_variant_keeps_the_contour_targets_stress_and_scale(path):
    g = G.load(path)
    scale = set(V.scale(g))
    for v in V.candidates(g):
        assert not V.problems(g, [v]), v
        phrase = g.phrases[v.phrase]
        sung = V.realized(phrase, [v])
        written = phrase.sung
        assert moves([p.degree for p in sung]) == phrase.contour(), v  # holds stay holds, steps stay steps
        assert (sung[-1].degree, sung[-1].onset) == (written[-1].degree, written[-1].onset), v  # the target
        for p, n in zip(sung, written):
            if n.onset % g.meter.foot == 0:
                assert p.onset == n.onset, v  # a stressed syllable stays on its beat
            else:
                assert p.onset % g.meter.foot != 0 and (n.onset // g.meter.foot) * g.meter.foot < p.onset, v
            assert p.dur >= 1.0 - 1e-9 or p.dur == n.dur, v  # nothing is left too short to sing
            assert (p.degree - 1) % 7 + 1 in scale, v
            assert p.alter == 0 or p.variant is None
        if v.kind == "leap":  # a moved note is a tone of the chord under it
            n = written[v.note]
            assert V.chord_tone(V.chord_under(phrase, n.onset, g.meter), v.degree), v
        for _, s in v.steps:  # ornament tones keep to the song's scale; a passing waypoint keeps to the mode
            assert v.kind == "passing" or (written[v.note].degree + s - 1) % 7 + 1 in scale, v


def test_the_lead_songs_vocabulary(h):
    offered = V.candidates(h)
    kinds = {v.kind for v in offered}
    assert kinds >= {"grace", "mordent", "turn", "neighbour", "passing", "anticipation", "leap", "dotted"}
    assert V.scale(h) == (1, 2, 3, 5, 6)  # H is pentatonic: ornaments never bring in fa or ti...
    for v in offered:
        if v.kind in ("grace", "mordent", "turn", "neighbour"):
            assert all((h.phrases[v.phrase].sung[v.note].degree + s - 1) % 7 + 1 in (1, 2, 3, 5, 6) for _, s in v.steps)
    # ...except as a quick waypoint sliding across a third (a passing tone), which folk singers do
    assert {v.kind for v in offered if any((h.phrases[v.phrase].sung[v.note].degree + s - 1) % 7 + 1 in (4, 7)
                                           for _, s in v.steps)} <= {"passing"}
    # dotting H's pairs of quavers would leave a sixteenth too short for a syllable: only its crotchet pairs dot
    assert all(h.phrases[v.phrase].sung[v.note].dur == 2 for v in offered if v.kind == "dotted")


def test_hooks_and_the_refrain_first_line_stay_plain(h):
    kept = V.protected(h)
    assert {("r1", k) for k in range(len(h.phrases["r1"].sung))} <= kept  # the refrain's first line
    assert {("r4", k) for k in range(7, 11)} <= kept and {("b1", k) for k in range(10)} <= kept  # the hooks
    for v in V.candidates(h):
        assert v.key not in kept
        if v.key == ("r4", 6):  # the way into "now it's by you" is part of the hook
            assert v.kind not in ("leap", "passing", "anticipation")
    assert V.problems(h, [V.Variant("r1", 3, "grace", steps=((0.0, 1), (0.1, 0)))])


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_variants_stay_under_the_bound(path):
    g = G.load(path)
    rng = np.random.default_rng(3)
    cap = V.room(g)
    for _ in range(5):
        chosen = greedy(g, rng)
        assert not V.problems(g, chosen)
        used = V.load_of(g, chosen)
        for name, n in used.items():
            assert n <= cap[name] <= V.SHARE * sum(len(g.phrases[p].sung) for p in g.sections[name].phrases)
        notes = sorted((v.phrase, v.note) for v in chosen)
        assert all(not (a[0] == b[0] and b[1] - a[1] <= 1) for a, b in zip(notes, notes[1:]))  # a note apart
        for phrase in {v.phrase for v in chosen}:  # and together they keep each phrase's contour
            p = g.phrases[phrase]
            assert moves([x.degree for x in V.realized(p, chosen)]) == p.contour()


def test_the_bound_and_the_spacing_are_checked(h):
    graces = [v for v in V.candidates(h) if v.kind == "grace" and v.phrase == "v1"]
    too_many = []
    for v in graces:
        if all(abs(v.note - u.note) > 1 for u in too_many):
            too_many.append(v)
    assert len(too_many) > V.room(h)["verse"] and any("holds at most" in p for p in V.problems(h, too_many))
    a, b = (next(v for v in graces if v.note == k) for k in (2, 3))
    assert any("neighbours" in p for p in V.problems(h, [a, b]))


@pytest.mark.parametrize("path", SONGS, ids=lambda p: p.stem)
def test_no_variants_sings_exactly_as_before(path):
    g = G.load(path)
    seed = Params.from_dict(g.seed_params)
    assert seed.variants == () and seed.words == {}
    score = realize(g, seed)
    assert not any(n.ornament for n in score.notes)
    assert all("ornament" not in n for n in score.to_dict()["notes"])  # the score's record is as it was
    assert set(seed.to_dict()) == set(g.seed_params) | {"band", "choir", "humanize", "ritardando", "singer", "mix",
                                                         "leanings", "lay", "inventory", "seed", "accomp"}


def test_a_lineage_sings_its_variants_and_the_band_plays_them(h):
    seed = Params.from_dict(h.seed_params)
    offered = V.candidates(h)
    grace = next(v for v in offered if v.key == ("r3", 1) and v.kind == "grace")  # "no-" in the refrain, and the intro
    leap = next(v for v in offered if v.key == ("r2", 6) and v.kind == "leap")  # "and" a third lower
    passing = next(v for v in offered if v.key == ("v1", 3) and v.kind == "passing")  # "as" slides up to "num-"
    params = replace(seed, variants=V.parse([grace, leap, passing]))
    plain, sung = realize(h, seed), realize(h, params)
    voice = sung.part("voice")
    assert len(voice) == len(plain.part("voice"))  # a syllable stays one note for the singer
    moved = [(a, b) for a, b in zip(plain.part("voice"), voice) if a.pitch != b.pitch]
    assert moved and all(b.pitch - a.pitch == -4 and a.phrase == "r2" for a, b in moved)  # mi down to do, each refrain
    graced = [n for n in voice if n.ornament and n.phrase == "r3"]
    assert graced and all(n.ornament[0][1] > 0 and n.ornament[-1][1] == 0 for n in graced)
    slid = [n for n in voice if n.ornament and n.phrase == "v1"]
    assert slid and all(n.ornament[-1][1] == 1.0 for n in slid)  # mi up through fa (a semitone) to so
    choir = [n for n in sung.notes if n.part.startswith("choir")]
    assert not any(n.ornament for n in choir)  # harmony is sung plain
    intro = lambda score: [n for n in score.notes if n.section == "intro" and n.part == seed.band.lead]  # noqa: E731
    assert len(intro(sung)) > len(intro(plain))  # the lead states the tune in the intro with the grace
    assert [n.part for n in intro(sung)] and intro(plain)


def test_ornaments_are_sung_inside_their_note():
    voice = VoiceParams(jitter=0.0, wander=0.0, glide_spread=0.0)
    from songbird.score import Note

    def notes(ornament=()):
        return [Note("voice", 0.5, 0.6, 62.0, 0.8, "a", "a"), Note("voice", 1.1, 0.6, 66.0, 0.8, "b", "b", ornament=ornament),
                Note("voice", 1.7, 0.6, 64.0, 0.8, "c", "c", line_end=True)]

    n_blocks = int(3.0 * 44100 / BLOCK)
    tb = (np.arange(n_blocks) + 0.5) * BLOCK / 44100
    plain = pitch_track(notes(), n_blocks, 44100, voice, np.random.default_rng(0))
    grace = pitch_track(notes(((0.0, 2.0), (0.2, 0.0))), n_blocks, 44100, voice, np.random.default_rng(0))
    semis = 12 * np.log2(grace / plain)
    assert np.all(np.abs(semis[(tb < 1.0) | (tb > 1.7)]) < 1e-9)  # only the ornamented note moves
    assert semis[(tb > 1.1) & (tb < 1.18)].max() > 1.5  # it starts on the note above...
    assert np.abs(semis[(tb > 1.3) & (tb < 1.6)]).max() < 0.05  # ...and settles on its own
    early = pitch_track(notes(((0.0, 0.0), (0.5, -2.0))), n_blocks, 44100, voice, np.random.default_rng(0))
    f = 12 * np.log2(early / 440) + 69
    assert abs(np.median(f[(tb > 1.55) & (tb < 1.62)]) - 64.0) < 0.3  # an anticipation reaches the next pitch early
    assert np.abs(f[(tb > 1.75) & (tb < 2.1)] - 64.0).max() < 0.3  # and the next note needs no glide
    short = [replace(n, dur=0.12) if i == 1 else n for i, n in enumerate(notes(((0.0, 2.0), (0.2, 0.0))))]
    swallowed = pitch_track(short, n_blocks, 44100, voice, np.random.default_rng(0))
    unornamented = pitch_track([replace(n, ornament=()) for n in short], n_blocks, 44100, voice, np.random.default_rng(0))
    assert np.allclose(swallowed, unornamented)  # too little vowel to turn in: sung plain


def test_the_variants_keep_the_mode_in_every_mode_the_song_takes(h):
    chosen = greedy(h, np.random.default_rng(1))
    for mode in variation.allowed_modes(h, "ionian"):
        pcs = {s % 12 for s in MODES[mode]}
        params = replace(Params.from_dict(h.seed_params), mode=mode, variants=V.parse(chosen))
        for n in realize(h, params).part("voice"):
            assert (n.pitch - params.tonic) % 12 in pcs
            assert all((n.pitch + s - params.tonic) % 12 in pcs for _, s in n.ornament)


def test_the_gate_still_hears_the_same_tune(h):
    """The lineage gate compares contour: relative moves, by dynamic time warping, the hooks weighted. However
    many variants a lineage gathers, the tune stays close to the seed's and far from any other song's."""
    rng = np.random.default_rng(7)
    near = [V.distance(h, (), greedy(h, rng)) for _ in range(6)]
    assert V.distance(h, (), ()) == 0 and max(near) < 0.5, near
    whole = lambda g, vs=(): [s for _, ps in V.melody(g, vs, ornaments=True) for s in np.diff(ps)]  # noqa: E731
    mine = whole(h)
    for path in SONGS:
        if path == LEAD:
            continue
        other = whole(G.load(path))
        far = V.dtw(mine, other) / max(len(mine), len(other))
        close = V.dtw(mine, whole(h, greedy(h, rng))) / len(mine)
        assert close < far / 2, (path.stem, close, far)


def test_the_record_round_trips_and_says_where_a_variant_came_from(h):
    v = next(iter(V.candidates(h)))
    sung = V.Variant(v.phrase, v.note, v.kind, v.degree, v.steps, v.shift, "sung:milo", 3)
    assert V.Variant.from_dict(sung.to_dict()) == sung and not V.problems(h, [sung])
    assert V.problems(h, [replace(sung, source="stolen")])
    params = replace(choose_params(h), variants=(sung,), generation=4)
    assert Params.from_dict(params.to_dict()) == params
    assert V.describe(h, V.Variant("r2", 6, "leap", degree=1)) == '"and" sung a third lower (refrain, line 2)'
