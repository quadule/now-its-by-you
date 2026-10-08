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
from songbird.synth.mixing import MixParams
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
    long = V.build(h, 4, {(4, "turn", r): True for r in range(3)}, bridge2=True)
    assert " ".join(long) == ("verse refrain verse refrain turn verse refrain turn verse refrain turn "
                              "bridge bridge2 refrain")
    assert V.fits(h, long) and V.parse_form(h, long)["x8"] == "bridge2,"
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
    assert len({p.mix["rt60"] for p in children}) > 1


def test_a_neutral_machine_sings_like_its_parent(h):
    seed = Params.from_dict(h.seed_params)
    p = choose_params(h, voice=H.Voice(salt="locked-down"))
    # the seed's own mix (Open Door, 2026-09-27) comes through, its voice held to the machines' floor of 8.5 dB over the band
    assert (p.tonic, p.mode, p.tempo, p.accomp, p.singer, p.mix) == (seed.tonic, seed.mode, seed.tempo, seed.accomp,
                                                                        {}, {**seed.mix, "forward": max(seed.mix["forward"], 8.5)})
    assert p.choir == seed.choir + 1  # still a generation
    assert V.fits(h, p.form)


NEUTRAL = H.Voice()  # machine none: the public studio's, and `--machine none`


def own_again(g, parent, voice, date: str, n: int = 5, style: str | None = None) -> list:
    """A machine singing a version on a date, then singing its own last version again n times that day."""
    d = D.drift(D.parse(date), voice.hash)
    versions = [choose_params(g, parent, voice, d, style=style)]
    for _ in range(n):
        versions.append(choose_params(g, versions[-1], voice, d, style=style))
    return versions


def chosen(p) -> dict:
    """What a version chose, less what moves on every generation by design: the choir (a voice a generation),
    the style's lineage, the rendition's seed (from the parent) and who made it when."""
    data = p.to_dict()
    for key in ("choir", "generation", "made", "seed"):
        data.pop(key, None)
    if isinstance(data.get("style"), dict):
        data["style"] = {k: v for k, v in data["style"].items() if k != "lineage"}
    return data


@pytest.mark.parametrize("date", ["2026-10-07", "2028-06-10", "2031-02-09"])
def test_a_machine_singing_its_own_again_that_day_sings_it_the_same(h, date):
    # A machine with nothing of its own somewhere takes its parent's value there, moved by its day. Before October
    # 7, 2026 a machine singing its own version again added that day once more each time: machine none climbed a
    # semitone and about 5 BPM a generation (E-flat, E, F, F#, G) to the bounds, its band thinned, its mode darkened.
    # Now the day the parent already carries is taken out first (variation.Knob.centre, centred()).
    for parent in (None, child(h, "ada", "2026-06-01")):
        versions = own_again(h, parent, NEUTRAL, date)
        assert len({(p.tonic, p.tempo, p.mode) for p in versions}) == 1
        assert all(chosen(p) == chosen(versions[0]) for p in versions)


def test_a_machines_own_versions_stay_in_its_field_around_one_centre(h):
    # machine none singing its own last version every few days for a year: on each day what the day gives around
    # the seed's own values, exactly as that day's version sung from the seed, never a walk
    seed = Params.from_dict(h.seed_params)
    p = None
    for t in np.arange(D.parse("2026-10-07"), D.parse("2027-10-07"), 3.0):
        d = D.drift(t, NEUTRAL.hash)
        p = choose_params(h, p, NEUTRAL, d)
        fresh = choose_params(h, None, NEUTRAL, d)
        assert p.tonic == fresh.tonic and abs(p.tonic - seed.tonic) <= 1  # a drift of 1 moves the key 0.6 x 2
        assert abs(p.tempo - fresh.tempo) <= 0.2 and abs(p.tempo / seed.tempo - 1) <= V.PULL * 0.10 + 0.002
        assert (p.mode, p.band.pattern, p.band.lead) == (fresh.mode, fresh.band.pattern, fresh.band.lead)


def test_what_a_machine_knows_nothing_of_holds_when_it_sings_its_own_again(h):
    # a machine read only in part (as `--machine here` before a harvest: no files, hands, words or room) knows its
    # identity, so its style sets the tempo, but not its pace, its rubato or its vocabulary
    quiet = replace(H.fictional("ada"), ages=None, hand=None, words=None, room=None)
    versions = own_again(h, None, quiet, "2026-10-07")
    for read in (lambda p: p.tempo, lambda p: p.humanize, lambda p: p.band.ornament,
                 lambda p: p.leanings.get("era_bias"), lambda p: p.leanings.get("rarity_appetite")):
        assert len({read(p) for p in versions}) == 1
    # the mix's duck reads no trait of any machine: a made-up machine's own versions held it too (bo's fell from
    # 0.91 to the floor of 0.6 in four)
    assert len({p.mix.get("duck") for p in own_again(h, None, H.fictional("bo"), "2026-10-07")}) == 1


def test_only_a_machines_own_version_has_its_day_taken_out(h):
    d = D.drift(D.parse("2026-10-07"), NEUTRAL.hash)
    mine, theirs = choose_params(h, None, NEUTRAL, d), child(h, "ada", "2026-10-07")
    assert V.made_here(Params.from_dict(h.seed_params), d) is None and V.made_here(theirs, d) is None
    assert V.made_here(mine, d).t == d.t
    # a hand-off takes its one turn: machine none's version of ada's is ada's moved by its day, as ever
    kid = choose_params(h, theirs, NEUTRAL, d)
    assert abs(kid.tempo - theirs.tempo * (1 + V.PULL * 0.10 * d.full["tempo"])) <= 0.051
    # and the studio's reasons say time moved its own version since, not the machine
    trace: dict = {}
    V.choose(h, mine, NEUTRAL, D.drift(D.parse("2026-11-20"), NEUTRAL.hash), trace=trace)
    t = trace["tempo"]
    assert t["own"] == t["was"] == mine.tempo
    assert abs(V.PULL * (t["moved"] - t["own"]) - (t["value"] - t["was"])) <= 0.051


def test_making_yours_from_a_version_shared_in_the_studio_keeps_its_numbers(h):
    # the public studio sings as machine none: a version someone made there and shared, opened and made yours the
    # same day, is its parent again in every number (a person's own tempo too); a month on, its field moved by time
    from songbird import explain

    day, later = "2026-10-07", "2026-11-07"

    def yours(parent, edits, on):
        record = {"params": parent.to_dict()} if parent is not None else None
        ctx = explain.Context(h, parent, record, NEUTRAL, "none", on, D.parse(on), shared=True)
        return ctx.version(edits).params

    for edits in ({}, {"tempo": 120.0}):
        shared = yours(None, edits, day)
        assert shared.tempo == edits.get("tempo", shared.tempo)
        again = yours(shared, {}, day)
        assert (again.tonic, again.tempo, again.mode, again.band, again.mix) == \
               (shared.tonic, shared.tempo, shared.mode, shared.band, shared.mix)
        on = yours(shared, {}, later)
        assert abs(on.tonic - shared.tonic) <= 1 and abs(on.tempo / shared.tempo - 1) <= 2 * V.PULL * 0.10


def test_a_lineage_keeps_its_accent(h):
    seed = Params.from_dict(h.seed_params)
    a, b = H.fictional("ada"), H.fictional("cy")
    # in one style throughout: a style takes the song at its own tempo (tests/test_styles.py)
    first = choose_params(h, None, a, style="ballad")
    second = choose_params(h, first, b, style="ballad")
    alone = choose_params(h, None, b, style="ballad")  # machine b singing straight from the seed
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


def test_every_family_comes_round_to_its_members(h):
    days = np.arange(D.parse("2026-01-01"), D.parse("2034-01-01"), 14.0)
    reached = {"folk": set(), "bright": set(), "dark": set()}
    for k in range(60):
        voice = H.fictional(f"m{k}")
        parent = None
        for t in days:  # a lineage sung on this one machine, a fortnight apart
            parent = choose_params(h, parent, voice, D.drift(t, voice.hash))
            reached[voice.tongue.family].add(parent.mode)
    assert reached["dark"] == {"aeolian", "ionian"}  # a dark lineage in minor still comes back to the seed's mode
    assert {"ionian", "mixolydian"} <= reached["folk"] and reached["bright"] == {"ionian", "mixolydian"}


def test_the_form_changes_by_the_season_not_the_day(h):
    days = np.arange(D.parse("2026-01-01"), D.parse("2028-01-01"), 1.0)
    per_year = []
    for name in MACHINES:
        voice = H.fictional(name)
        forms = [choose_params(h, voice=voice, drift=D.drift(t, voice.hash)).form for t in days]
        for form in forms:  # a machine takes a breath after every refrain that day, or after none
            turns = sum(s == "turn" for s in form)
            assert turns in (0, sum(s == "refrain" for s in form) - 1)
        per_year.append(sum(a != b for a, b in zip(forms, forms[1:])) / 2)
    assert 2 <= np.mean(per_year) <= 15, per_year


def test_the_table_is_wired():
    from songbird.band import Band
    from songbird.synth.mixing import MixParams

    params = {f for f in Params.__dataclass_fields__}
    for knob in V.KNOBS:
        head, _, tail = knob.path.partition(".")
        assert head in params
        if head == "singer":
            assert hasattr(VoiceParams(), tail), knob.path
        if head == "band":
            assert hasattr(Band(), tail), knob.path
        if head == "mix":
            assert hasattr(MixParams(), tail), knob.path
        if head == "leanings":
            assert tail in V.LEANINGS
        dims = knob.drift if isinstance(knob.drift, tuple) else (knob.drift,) if knob.drift else ()
        spans = knob.span if isinstance(knob.span, tuple) else (knob.span,)
        assert len(dims) <= len(spans), knob.path
        for dim in dims:
            assert dim in D.DIMENSIONS, knob.path
        assert knob.view in D.VIEWS
    for dimension in ("intro", "turn", "break", "tag", "outro", "other", "verses", "pairs", "extra", "texture", "mood",
                      "mode", "key", "pattern", "lead", "arc", "sheen", "balance", "ensemble", "space", "near",
                      "duck"):
        assert dimension in D.DIMENSIONS
    assert "swing" not in params  # the band's swing is the only swing


def test_every_machine_has_its_own_band_and_nobody_sits_out(h):
    from songbird.band import INSTRUMENTS, LEADS, PATTERNS, Band

    seed = Params.from_dict(h.seed_params)
    assert seed.band.lineup == {} and seed.band.arc == 0.95 and seed.band != Band()  # the seed's own arrangement (Open Door)
    assert all(0.5 <= getattr(seed.band, i) <= 1.5 for i in INSTRUMENTS)  # within what the machines may do
    bands = {}
    for name in MACHINES:
        voice = H.fictional(name)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2029-01-01"), 11.0):
            band = choose_params(h, voice=voice, drift=D.drift(t, voice.hash)).band
            assert all(0.5 <= getattr(band, i) <= 1.5 for i in INSTRUMENTS), band  # a gain never drops a part
            assert band.pattern in PATTERNS and band.lead in LEADS
            assert 0.0 <= band.swing <= 0.6 and 0.85 <= band.body <= 1.2
            bands.setdefault(name, set()).add((band.maker, band.body))
        assert len(bands[name]) == 1  # the maker's hand and the instruments' size are the machine's, every day
    assert len({next(iter(b)) for b in bands.values()}) == len(MACHINES)  # and every machine's are its own
    neutral = choose_params(h, voice=H.Voice(salt="locked-down"))
    assert neutral.band == seed.band  # a machine that gave nothing plays as its parent's band did


def test_the_band_follows_the_machine(h):
    from songbird.band import Band

    bright = H.Voice(colour=H.Colour(1.0, 0.25, 0.5, 0.25), salt="s")
    dark = H.Voice(colour=H.Colour(0.0, 0.25, 0.5, 0.25), salt="s")
    assert choose_params(h, voice=bright).band.brightness > Band().brightness > choose_params(h, voice=dark).band.brightness
    busy = H.Voice(machine=H.Machine(1.0, 1.0, 0.5), salt="s")
    small = H.Voice(machine=H.Machine(0.0, 0.0, 0.5), salt="s")
    assert choose_params(h, voice=busy).band.density > choose_params(h, voice=small).band.density
    old = H.Voice(ages=H.Ages(median=3.5, spread=1.0), salt="s")
    young = H.Voice(ages=H.Ages(median=1.0, spread=1.0), salt="s")
    assert choose_params(h, voice=old).band.wear > choose_params(h, voice=young).band.wear
    lilting = H.Voice(hand=H.Hand(interval=200, unevenness=0.5, skew=2.5), salt="s")
    assert choose_params(h, voice=lilting).band.swing > 0.2  # a skewed hand swings the band and the singer


def test_every_machine_mixes_its_own_record_within_bounds(h):
    from songbird.synth.mixing import RANGES, MixParams

    seen = {}
    for name in MACHINES:
        voice = H.fictional(name)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2029-01-01"), 17.0):
            chosen = choose_params(h, voice=voice, drift=D.drift(t, voice.hash)).mix
            mix = MixParams.from_dict(chosen)
            for field, (lo, hi) in RANGES.items():
                assert lo <= getattr(mix, field) <= hi, (field, getattr(mix, field))
            assert 8.5 <= mix.forward <= 11.0  # the voice stays well over the band
            # width: from the seed's own 1.25 (Open Door, 2026-09-27) a machine may reach the mixer's limit
            assert 0.3 <= mix.intimacy <= 0.7 and 0.9 <= mix.width <= RANGES["width"][1] and abs(mix.tilt) <= 1.2
            assert (mix.rt60, list(mix.tone)) == (voice.room.rt60, list(voice.room.tone))  # the machine's own room
            old = voice.ages.median >= 3.4  # files some eight years old or more
            assert mix.wear < 0.35 or old  # crackle only on the oldest machines
            seen.setdefault(name, set()).add((mix.predelay, mix.wear))
        assert len(seen[name]) == 1  # the room's predelay and the recording's wear belong to the machine
    assert len({next(iter(s)) for s in seen.values()}) > 1


def test_the_mix_follows_the_machine(h):
    from songbird.synth.mixing import MixParams

    def mix(voice):
        return MixParams.from_dict(choose_params(h, voice=voice).mix)

    assert mix(H.Voice(ages=H.Ages(median=3.75, spread=1.0), salt="s")).wear > 0.35  # a truly old machine crackles
    assert mix(H.Voice(ages=H.Ages(median=1.5, spread=1.0), salt="s")).wear == 0.0  # a young one is clean
    bright = mix(H.Voice(colour=H.Colour(1.0, 0.25, 0.5, 0.25), salt="s")).tilt
    dark = mix(H.Voice(colour=H.Colour(0.0, 0.25, 0.5, 0.25), salt="s")).tilt
    assert bright > 0 > dark
    big = mix(H.Voice(room=H.Room(rt60=2.2, tone=(1, 1, 1, 0.9, 0.7)), salt="s")).predelay
    small = mix(H.Voice(room=H.Room(rt60=0.4, tone=(1, 1, 1, 0.9, 0.7)), salt="s")).predelay
    assert big > small  # a big room answers later


def test_old_records_keep_their_room(h):
    record = Params.from_dict(h.seed_params).to_dict()
    del record["mix"]
    record["room"] = {"rt60": 0.7, "tone": [1.0, 0.9, 1.0, 0.8, 0.6]}
    assert Params.from_dict(record).mix == {"rt60": 0.7, "tone": [1.0, 0.9, 1.0, 0.8, 0.6]}


def test_old_records_keep_their_swing(h):
    record = {**Params.from_dict(h.seed_params).to_dict(), "swing": 0.1}
    del record["band"]
    assert abs(Params.from_dict(record).band.swing - 0.1 / 0.333) < 1e-9


def test_pattern_and_lead_hold_against_flicker(h):
    days = np.arange(D.parse("2026-01-01"), D.parse("2030-01-01"), 1.0)
    rates, holds = {"pattern": [], "lead": []}, {"pattern": [], "lead": []}
    for name in MACHINES:
        voice = H.fictional(name)
        bands = [choose_params(h, voice=voice, drift=D.drift(t, voice.hash)).band for t in days]
        for what in ("pattern", "lead"):
            values = [getattr(b, what) for b in bands]
            changes = [i for i in range(1, len(values)) if values[i] != values[i - 1]]
            rates[what].append(len(changes) / 4)
            holds[what] += list(np.diff(changes))
    assert min(holds["pattern"] + holds["lead"], default=999) >= 7  # nothing changes back within a week
    assert np.mean(rates["lead"]) <= 1.5 and np.mean(rates["pattern"]) <= 6, rates
    assert np.mean(rates["pattern"]) > 0  # but it does move


def test_a_held_choice_is_a_schmitt_trigger():
    class Ctx:  # just enough of a Context: a drift whose past can be read
        def __init__(self, t):
            self.drift = D.drift(t, "abc")

        def at(self, view, dimension):
            return self.drift.view(view).get(dimension, 0.0)

    t = np.arange(D.parse("2026-01-01"), D.parse("2028-01-01"), 1.0)
    path = D.series(t, "abc", ["pattern"])["pattern"]["slow"]
    base, span = 1.5, 1.2  # sitting right on the boundary between categories 1 and 2
    got = [V.held(Ctx(x), "slow", "pattern", base, span, 4) for x in t]
    plain = [int(np.clip(np.floor(base + span * v + 0.5), 0, 3)) for v in path]
    flips = lambda xs: sum(a != b for a, b in zip(xs, xs[1:]))  # noqa: E731
    assert flips(got) < flips(plain)  # fewer changes than rounding would make
    for g, v in zip(got, path):  # and wherever the position is firmly in a category, that is the choice
        p = base + span * v
        if abs(p - round(p)) <= 0.5 - V.HOLD and 0 <= round(p) <= 3:
            assert g == round(p)


def test_leanings_for_the_lyric(h):
    from songbird.arrange import Leanings, arrange

    p = child(h, "ada", "2026-09-25")
    lean = p.leanings
    assert set(lean) == {"mood_weights", "era_bias", "rarity_appetite", "vocabulary"}
    assert set(lean["mood_weights"]) == {"plain", "light", "dark", "tender"}
    assert abs(sum(lean["mood_weights"].values()) - 4) < 0.05
    assert -1 <= lean["era_bias"] <= 1 and -1 <= lean["rarity_appetite"] <= 1
    assert lean["vocabulary"] and set(lean["vocabulary"]) <= V.song_words(h)  # only the song's own words
    arranged = V.leanings(p)
    assert isinstance(arranged, Leanings) and arranged.vocabulary and arranged.vocabulary <= V.song_words(h)
    assert V.leanings(Params.from_dict(h.seed_params)) is None  # the seed leans nowhere
    words = arrange(h, p.form, p.seed, arranged)
    assert words.to_dict() == arrange(h, p.form, p.seed, arranged).to_dict()


def test_the_bank_can_fill_every_form_chosen(h):
    from songbird.arrange import problem

    seconds = 0
    for name in MACHINES:
        voice = H.fictional(name)
        for t in np.arange(D.parse("2026-01-01"), D.parse("2028-01-01"), 6.1):
            p = choose_params(h, voice=voice, drift=D.drift(t, voice.hash))
            assert problem(h, p.form) is None, p.form
            seconds += "bridge2" in p.form
    assert seconds  # a long form sometimes sings the bridge's extra stanza


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
