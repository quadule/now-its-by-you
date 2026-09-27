"""Styles: the record, the palette, the map they travel on, the harmony they may add, and that the seed is untouched."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G
from songbird.band import Band
from songbird.realize import Params, choose_params, realize
from songbird.style import Style

ROOT = Path(__file__).parent.parent
SONGS = sorted((ROOT / "songs").glob("*.json"))
H = ROOT / "songs" / "h-now-its-by-you.json"
GOLDEN = Path(__file__).parent / "golden"


# --- the seed is untouched ---------------------------------------------------------------------------


def score_hash(g) -> str:
    score = realize(g, choose_params(g))
    return hashlib.sha256(json.dumps(score.to_dict(), sort_keys=True).encode()).hexdigest()[:16]


def test_every_seed_is_arranged_exactly_as_before():
    """With no style the band plays every song's seed note for note as it did before styles existed
    (golden/seed-scores.json; regenerate only for an intended change to the seed's arrangement)."""
    import os

    path = GOLDEN / "seed-scores.json"
    got = {p.stem: score_hash(G.load(p)) for p in SONGS}
    if os.environ.get("SONGBIRD_UPDATE_GOLDEN") or not path.exists():
        path.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
    assert got == json.loads(path.read_text())


def test_the_seed_of_h_renders_byte_identical(tmp_path):
    """H's seed rendition, audio and all: its id is golden/h-seed.sha256 (441dc83b1d1e... when styles came)."""
    import os

    from songbird import cli

    g = G.load(H)
    record = cli.render_one(g, choose_params(g), tmp_path / "h.flac", phrasing_json=g.source.get("seed_phrasing"))
    path = GOLDEN / "h-seed.sha256"
    if os.environ.get("SONGBIRD_UPDATE_GOLDEN") or not path.exists():
        path.write_text(record["id"] + "\n")
    assert record["id"] == path.read_text().strip()


# --- the record ----------------------------------------------------------------------------------------


def test_old_params_load_with_the_seeds_style_and_band():
    g = G.load(H)
    old = {k: v for k, v in g.seed_params.items() if k not in ("style", "band", "mix")}  # a record from before styles
    record = Params.from_dict(old).to_dict()
    # the plain style and band leave no trace in a record, as in every record from before styles...
    assert "style" not in record and "lineup" not in record["band"]
    p = Params.from_dict(record)
    assert p.style == Style() and p.style.seed and p.band.lineup == {} and p.band == Band()
    # ...while the seed's own arrangement is written out since 2026-09-27 (Open Door, seed_params), and travels
    own = choose_params(g)
    assert own.style.name == "ballad" and own.style.entrances and own.style.breakdown and own.band.arc == 0.95
    assert Params.from_dict(own.to_dict()) == own and own != p


def test_a_style_and_a_lineup_survive_the_record():
    g = G.load(H)
    style = Style(name="bluegrass", lineage=("ballad", "oldtime", "bluegrass"), feel="double", harmony=0.4,
                  intro="count", alone=2, alone_with="banjo", breakdown=True, lift=True, ending="cold",
                  entrances=True, backing="thirds", voices=2)
    band = replace(Band(), lineup={"banjo": 1.1, "mandolin": 0.9, "fiddle": 1.0, "guitar": 1.0, "bass": 1.0})
    p = replace(Params.from_dict(g.seed_params), style=style, band=band)
    again = Params.from_dict(json.loads(json.dumps(p.to_dict())))
    assert again == p and isinstance(again.style, Style) and again.style.lineage == style.lineage
    assert again.band.plays("banjo") and not again.band.plays("lute") and again.band.gain("mandolin") == 0.9


def test_style_values_are_held_to_their_options():
    s = Style.from_dict({"feel": "polka", "harmony": 3, "ending": "explode", "voices": 99, "future": 1,
                         "lineage": ["a"] * 40, "bridge": "double"})
    assert (s.feel, s.harmony, s.ending, s.voices, s.bridge) == ("", 1.0, "", 6, "")
    assert len(s.lineage) == 16
    assert Band.from_dict({"lineup": [["banjo", 5.0], ["kit", -1]]}).lineup == {"banjo": 2.0, "kit": 0.0}


# --- the palette and the ring ---------------------------------------------------------------------------


def test_the_palette_is_whole():
    from songbird import style as S
    from songbird.synth import instruments

    assert set(S.RING) == set(S.STYLES) and len(S.RING) == len(set(S.RING))
    known = set(instruments.known())
    for s in S.STYLES.values():
        assert set(s.lineup) <= known, s.name
        assert set(s.parts) <= set(s.lineup) and all(lead in s.lineup for lead in s.leads), s.name
        assert abs(sum(s.feels.values()) - 1.0) < 1e-9 and set(s.feels) <= set(S.FEELS), s.name
        for feel in s.feels:
            lo, centre, hi = s.centre(feel)
            assert 0.4 <= lo < centre < hi <= 1.5, (s.name, feel)
        for key in ("intro", "ending", "backing"):
            assert sum(s.options.get(key, {"": 1}).values()) > 0, (s.name, key)


def machines(n):
    from songbird import harvest as HV

    return [HV.fictional(f"m{k}") for k in range(n)]


def test_styles_move_one_step_at_most_and_never_flicker():
    """A machine singing the same parent day after day changes style now and then, never back and forth
    within a week, and only ever to its parent's style or a neighbour's on the ring."""
    from songbird import drift as D, style as S, variation as V

    seed = Style()
    per_year = []
    for voice in machines(6):
        c = V.character(voice)
        days = np.arange(D.parse("2026-01-01"), D.parse("2028-01-01"), 1.0)
        chosen = [S.place(seed, c, D.drift(t, voice.hash)) for t in days]
        assert set(chosen) <= {"ballad", *S.neighbours("ballad")}
        changes = [i for i in range(1, len(chosen)) if chosen[i] != chosen[i - 1]]
        assert all(b - a >= 7 for a, b in zip(changes, changes[1:])), changes
        per_year.append(len(changes) / 2)
    assert 0 < np.mean(per_year) <= 4, per_year


def test_a_child_usually_keeps_its_parents_style():
    """Across machines, dates and parents in every style: most children keep their parent's style, the
    rest take one step; every style is some machines' home."""
    from collections import Counter

    from songbird import drift as D, style as S, variation as V

    kept = total = 0
    homes = Counter()
    for voice in machines(24):
        c = V.character(voice)
        homes[S.RING[int(np.floor(S.home(c) + 0.5)) % len(S.RING)]] += 1
        for k, name in enumerate(S.RING):
            t = D.parse("2026-03-01") + 53.0 * k + 11.0 * len(homes)
            child = S.place(Style(name=name), c, D.drift(t, voice.hash))
            assert child == name or child in S.neighbours(name)
            kept += child == name
            total += 1
    assert 0.45 <= kept / total <= 0.8, kept / total
    assert len(homes) >= 8  # machines are at home all round the ring


def test_a_machine_that_gave_nothing_keeps_its_parents_style():
    from songbird import harvest as HV

    g = G.load(H)
    parent = replace(Params.from_dict(g.seed_params), style=Style(name="gospel", lineage=("ballad", "gospel"),
                                                                   feel="twelve", backing="echo", voices=1))
    child = choose_params(g, parent, HV.Voice(salt="locked-down"))
    assert child.style.name == "gospel" and child.style.lineage == ("ballad", "gospel", "gospel")
    assert (child.style.feel, child.style.backing) == ("twelve", "echo")


def test_a_style_leans_the_singer_and_the_mix_without_compounding():
    """Generation after generation in one style on one machine, the singer's lean settles at the style's
    offset from what the machine would sing without it: it never grows."""
    from songbird import drift as D, harvest as HV, style as S

    g = G.load(H)
    voice = HV.fictional("ada")
    drift = D.drift(D.parse("2026-09-26"), voice.hash)
    plain = choose_params(g, None, voice, drift, style="ballad")
    p = choose_params(g, None, voice, drift, style="shanty")
    for _ in range(12):  # both settle where the machine and the style put them
        plain = choose_params(g, plain, voice, drift, style="ballad")
        p = choose_params(g, p, voice, drift, style="shanty")
    lean = S.STYLES["shanty"].singer["vibrato_depth"]
    got = p.singer.get("vibrato_depth", 28.0) - plain.singer.get("vibrato_depth", 28.0)
    assert abs(got - lean) < 1.0, got
    space = p.mix.get("space", 1.0) - plain.mix.get("space", 1.0)
    assert abs(space - S.STYLES["shanty"].mix["space"]) < 0.05, space
    assert p.style.lineage[-3:] == ("shanty",) * 3 and len(p.style.lineage) <= 16


def test_a_style_takes_the_song_at_its_own_tempo():
    from songbird import style as S

    g = G.load(H)
    song = Params.from_dict(g.seed_params).tempo
    for name, sdef in S.STYLES.items():
        p = choose_params(g, style=name)
        lo, _centre, hi = sdef.centre(p.style.feel)
        assert lo * song - 0.1 <= p.tempo <= hi * song + 0.1, (name, p.tempo)
        assert p.style.name == name and p.style.lineage == ("ballad", name)
        assert (p.band.lineup == {}) == (name == "ballad")


# --- the harmony a style adds -------------------------------------------------------------------------------

CHORDAL = {"strum", "ring", "boom", "travis", "roll", "claw", "chop", "tremolo", "comp", "arpeggio", "block", "oompah",
           "pad", "swell", "epiano", "pulse", "arp", "box", "bells", "boogie"}


@pytest.mark.parametrize("name", ["gospel", "lofi", "songwriter", "chamber", "country", "blues", "lullaby"])
def test_the_colours_never_rub_against_the_tune(name):
    """Every tone a style's chords add to the genome's (a sixth, a seventh, an added ninth, a suspension) is
    checked against what is sung where it sounds: never a minor second or major seventh from a sung note,
    and never a major second, minor seventh or tritone within an octave of one on a strong beat (a foot's
    start) or held a beat or more. The chord functions themselves are the genome's."""
    from songbird.idioms import chord_times
    from songbird.realize import timeline
    from songbird.theory import chord_tones

    g = G.load(H)
    p = choose_params(g, style=name, arrange={"harmony": 1.0, "lift": False, "backing": "thirds"})
    p = replace(p, choir=2)
    score = realize(g, p)
    clock = timeline(g, p)
    beat = 60.0 / p.tempo
    feet = [clock.seconds(clock.lead + k * g.meter.foot) for k in range(-1, (clock.end - clock.lead) // g.meter.foot + 1)]
    sung = [n for n in score.notes if n.part == "voice" or n.part.startswith("choir")]
    strong = {id(n): n.dur >= 0.95 * beat or min(abs(n.start - f) for f in feet) < 0.05 for n in sung}
    chords = chord_times(g, p)
    spans = [(t0, t1, s["parts"]) for (_name, t0, t1), s in zip(score.sections, score.band["sections"])]
    checked = coloured = 0
    for n in score.notes:
        parts = next((ps for t0, t1, ps in spans if t0 - 0.05 <= n.start < t1 - 0.05), spans[-1][2])
        if parts.get(n.part) not in CHORDAL or n.part in ("kit", "drummachine"):
            continue
        heard = n.start + 0.06  # a player may be a few hundredths early (a bow speaks late); judge it where it sounds
        at = next((c for c in chords if c[0] <= heard < c[1]), None)
        if at is None:
            continue
        triad = {(p.tonic + t) % 12 for t in chord_tones(at[2], p.mode)}
        checked += 1
        if int(round(n.pitch)) % 12 in triad:
            continue
        coloured += 1
        for v in sung:
            if v.start - 0.02 <= heard < v.start + v.dur:
                d = abs(int(round(n.pitch)) - int(round(v.pitch)))
                ic = min(d % 12, 12 - d % 12)
                assert ic != 1, (name, n, v)
                assert not (strong[id(v)] and ic in (2, 6) and d < 12), (name, n, v)
    assert checked > 100 and coloured > 0, (checked, coloured)  # the style did colour its chords


# --- the arrangement's options -----------------------------------------------------------------------------

OFF = {"intro": "", "alone": 0, "stops": 0, "breakdown": False, "bridge": "", "lift": False, "ending": "",
       "entrances": False, "backing": ""}


def styled(name, **options):
    g = G.load(H)
    return g, replace(choose_params(g, style=name, arrange={**OFF, **options}), choir=2)


def band_notes(score, section_index=None):
    spans = score.sections
    out = [n for n in score.notes if n.part != "voice" and not n.part.startswith("choir")]
    if section_index is None:
        return out
    _name, t0, t1 = spans[section_index]
    return [n for n in out if t0 + 0.05 <= n.start < t1 - 0.05]


def test_the_ballad_as_a_style_plays_the_seeds_band():
    """The ballad is the seed's style: with nothing asked it brings the seed's players; with the seed's own
    choices asked (Open Door, seed_params, 2026-09-27: entrances, breakdown, thirds, rit, its levels) it plays
    the seed's notes exactly."""
    g = G.load(H)
    own = choose_params(g)
    seed = realize(g, own)
    p = choose_params(g, style="ballad", arrange=OFF)
    assert p.style.name == "ballad" and not p.style.seed
    plain = realize(g, replace(p, tempo=own.tempo))
    assert {n.part for n in plain.notes} == {n.part for n in seed.notes}
    asked = replace(p, tempo=own.tempo, band=own.band, ritardando=own.ritardando, style=replace(
        p.style, lineage=(), **{f: getattr(own.style, f) for f in ("entrances", "breakdown", "backing", "ending", "lift", "feel")}))
    assert asked.style == own.style
    again = realize(g, asked)
    assert [n for n in again.notes] == [n for n in seed.notes]


def test_a_bare_verse_and_stop_time():
    g, p = styled("country", alone=2, stops=1)
    score = realize(g, p)
    verses = [k for k, s in enumerate(score.sections) if s[0] == "verse"]
    assert not band_notes(score, verses[1])  # the second verse a cappella
    stopped = band_notes(score, verses[0])
    t0, t1 = score.sections[verses[0]][1:]
    bar = 60.0 / p.tempo * g.meter.bar / g.meter.beat
    lines = ("steel",)  # a line may go on through stop-time; everyone keeping time hits the bars' ones
    kept = [n for n in stopped if n.part not in lines]
    assert kept and all(abs(((n.start - t0 + bar / 2) % bar) - bar / 2) < 0.09 for n in kept)
    g, p = styled("country", alone=1, alone_with="guitar")
    score = realize(g, p)
    first = [k for k, s in enumerate(score.sections) if s[0] == "verse"][0]
    assert {n.part for n in band_notes(score, first)} == {"guitar"}


def test_a_count_in_a_lift_and_a_cold_ending():
    g, plain = styled("indie")
    g, p = styled("indie", intro="count", lift=True, ending="cold")
    a, b = realize(g, plain), realize(g, p)
    bar = 60.0 / p.tempo * g.meter.bar / g.meter.beat
    assert abs((b.sections[0][1] - a.sections[0][1]) - bar) < 1e-6  # everything a bar later
    clicks = [n for n in b.notes if n.start < b.sections[0][1] - 0.2 and n.part == "kit"]
    assert len(clicks) == 4 and {n.art for n in clicks} == {"rim"}
    last = [s for s in b.sections if s[0] == "refrain"][-1][1]
    lifted = {round(n.pitch - m.pitch) for n, m in zip(b.part("voice"), a.part("voice")) if n.start >= last + 0.1}
    earlier = {round(n.pitch - m.pitch) for n, m in zip(b.part("voice"), a.part("voice")) if n.start < last - 2.0}
    assert lifted == {2} and earlier == {0}  # the last refrain a whole step up, nothing before it
    assert b.duration - b.sections[-1][2] < 1.0 < a.duration - a.sections[-1][2]  # a cold stop, not a ring


def test_an_amen_and_a_repeated_last_line():
    g, p = styled("gospel", ending="amen")
    score = realize(g, p)
    amen = [n for n in score.notes if n.part.startswith("choir") and n.word == "a-men"]
    assert len(amen) == 2 * p.choir and {n.syllable for n in amen} == {"a", "men"}
    last_sung = max(n.start + n.dur for n in score.part("voice"))
    assert min(n.start for n in amen) >= last_sung - 0.05  # after the last line: the singer has stopped
    g, p = styled("shanty", ending="repeat")
    form_ends_on_refrain = g.section(p.form[-1]).lyrics == "refrain"
    plain = realize(g, replace(p, style=replace(p.style, ending="")))
    again = realize(g, p)
    if form_ends_on_refrain:
        words = [n.word for n in again.part("voice")]
        tail = [n.word for n in plain.part("voice")][-len(g.phrases[g.section("refrain").phrases[-1]].sung):]
        assert len(words) == len(plain.part("voice")) + len(tail) and words[-len(tail):] == tail


def test_the_waltz_keeps_every_stressed_syllable_on_a_downbeat():
    """Re-barred in three, each foot of the song is a bar of a waltz: every stressed syllable (a foot's
    start) lands on a bar's one, the tune's pitches and order unchanged."""
    from songbird.realize import timeline

    g, p = styled("country", feel="waltz")
    plain = realize(g, replace(p, style=replace(p.style, feel="shuffle")))
    score = realize(g, p)
    assert [n.pitch for n in score.part("voice")] == [n.pitch for n in plain.part("voice")]
    clock = timeline(g, p)
    assert clock.triple == "waltz"
    ones = [t for t, bar in clock.beats() if bar]
    beats = [t for t, _bar in clock.beats()]
    for n in score.part("voice"):
        near = min(beats, key=lambda t: abs(t - n.start))
        assert abs(near - n.start) < 0.06  # every syllable on a beat of the waltz
    feet = [clock.seconds(clock.lead + k * g.meter.foot) for k in range((clock.end - clock.lead) // g.meter.foot)]
    assert all(min(abs(f - o) for o in ones) < 1e-6 for f in feet)  # every foot's start is a bar's one


@pytest.mark.parametrize("kind", ["gang", "thirds", "echo", "oohs"])
def test_the_backing_voices_are_the_lineages_own(kind):
    g, p = styled("shanty", backing=kind)
    for voices in (1, 3):
        score = realize(g, replace(p, choir=voices))
        refrains = [s for s in score.sections if s[0] == "refrain"]
        choir = [n for n in score.notes if n.part.startswith("choir")]
        assert {n.part for n in choir} == {f"choir{v + 1}" for v in range(voices)}  # never more than the lineage
        backing = [n for n in choir if n.section == "refrain" and any(t0 - 1.0 <= n.start < t1 for _nm, t0, t1 in refrains)]
        assert backing, kind
        if kind == "gang":
            sung = {(round(n.start, 1), n.pitch) for n in score.part("voice")}
            assert sum((round(n.start, 1), n.pitch) in sung for n in backing) > 0.5 * len(backing)
        if kind == "oohs":
            assert {n.syllable for n in backing} == {"oo"}
            voice = score.part("voice")
            for n in backing:  # under the singer, never on the note being sung
                assert all(n.pitch < v.pitch for v in voice if v.start <= n.start < v.start + v.dur)
    g, p = styled("shanty", backing="gang")
    assert not [n for n in realize(g, replace(p, choir=0)).notes if n.part.startswith("choir")]


@pytest.mark.parametrize("name", sorted(__import__("songbird.style", fromlist=["STYLES"]).STYLES))
def test_every_style_renders(name):
    """Every style's band, stems and all, for a verse and a refrain: finite, stereo, nothing louder than it should be."""
    from songbird import synth

    g = G.load(H)
    p = replace(choose_params(g, style=name), form=("verse", "refrain"), choir=1)
    score = realize(g, p)
    stems = synth.render_stems(score, seed=p.seed)
    assert "voice" in stems and len(stems) >= 3
    for stem_name, stem in stems.items():
        assert stem.ndim == 2 and stem.shape[1] == 2 and np.all(np.isfinite(stem)), stem_name
        assert np.abs(stem).max() < 4.0, (stem_name, float(np.abs(stem).max()))
