"""A hymn: an organ under everyone singing the tune in parts (docs/STYLES.md, "A hymn", 2026-09-30, night)."""

from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G, hymn, style as S
from songbird.idioms import chord_times
from songbird.realize import choose_params, realize
from songbird.theory import FLOOR, chord_tones, degree_semitones

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


@lru_cache(maxsize=8)
def sung(choir: int = 0, **arrange):
    g = G.load(H)
    p = replace(choose_params(g, style="hymn", arrange=dict(arrange) or None), choir=choir)
    return g, p, realize(g, p)


def band_chord(times, t: float) -> str:
    """The chord the band plays at t (seconds)."""
    return next((s for a, z, s in times if a - 1e-6 <= t < z - 1e-6), times[-1][2])


def test_beside_the_ring_and_chosen_by_a_person():
    """Beside the ring at chamber's place: offered on the page, never drawn by a machine's place on the ring."""
    assert S.OFF_RING["hymn"] == "chamber" and "hymn" not in S.RING
    assert "hymn" in S.offered() and "hymn" not in S.HIDDEN
    assert S.HYMN.group == 3 and S.HYMN.leads == ("pipeorgan",) and not S.HYMN.colours


def test_an_organ_and_everyone_singing():
    """The organ and a group of three at least (the program's own where the lineage has none), the singers matched
    to the parts at synthesis; no drums, no colour, slower than the song."""
    g, p, score = sung()
    assert set(p.band.lineup) <= {"pipeorgan", "harmonium"} and len(p.band.lineup) == 1
    assert p.style.voices >= 3 and p.style.backing == "gang" and p.style.harmony == 0.0
    assert {n.part for n in score.notes} == {next(iter(p.band.lineup)), "voice", "choir1", "choir2", "choir3"}
    assert score.band["parts"] == "voices"
    lo, centre, hi = S.HYMN.centre("straight")
    assert lo * 96 <= p.tempo <= hi * 96 and p.tempo < 96


def test_the_setting_a_chord_a_beat_or_a_half_bar():
    """The style's own harmonization: triads and first inversions, a bar's chords on its beats (one, two or four),
    each line closing on the song's own chord in root position, the tune's struck notes mostly chord tones; a line
    with no tune keeps its own chords."""
    g = G.load(H)
    ok = total = 0
    for pid, phrase in g.phrases.items():
        notes = tuple((n.degree, n.alter, float(n.onset), float(n.dur)) for n in phrase.sung)
        bars = hymn.harmonize(notes, phrase.chords, phrase.bars, g.meter, "ionian")
        assert len(bars) == phrase.bars
        if not notes:
            assert bars == phrase.chords  # the turn
            continue
        assert all(len(b) in (1, 2, 4) for b in bars)
        assert all(c in hymn.candidates("ionian") for b in bars for c in b)
        assert bars[-1][-1] == phrase.chords[-1][-1]  # the song's own cadence, root position
        for n in phrase.sung:
            if n.onset >= 0 and n.onset % g.meter.beat == 0:
                bar = bars[n.onset // g.meter.bar]
                c = bar[int((n.onset % g.meter.bar) * len(bar) // g.meter.bar)]
                total += 1
                ok += degree_semitones(n.degree, "ionian", n.alter) % 12 in {t % 12 for t in chord_tones(c, "ionian")}
    assert ok / total > 0.9, (ok, total)
    changes = sum(len(set(b)) for p in g.phrases.values() for b in hymn.harmonize(
        tuple((n.degree, n.alter, float(n.onset), float(n.dur)) for n in p.sung), p.chords, p.bars, g.meter, "ionian"))
    assert 1.4 <= changes / sum(p.bars for p in g.phrases.values()) <= 2.5  # a chord a beat or a half bar


def test_only_a_hymn_is_set_and_a_persons_chords_win():
    from songbird.composition import form_phrases

    g = G.load(H)
    gospel = choose_params(g, style="gospel")
    assert [p.chords for p in form_phrases(g, gospel)] == [g.phrases[p.id].chords for p in form_phrases(g, gospel)]
    p = choose_params(g, style="hymn")
    set_ = form_phrases(g, p)
    assert any(len(b) == 4 for x in set_ for b in x.chords)
    mine = replace(p, composition={"chords": {"r1": [["I"], ["IV", "V"]]}})
    assert all(x.chords == (("I",), ("IV", "V")) for x in form_phrases(g, mine) if x.id == "r1")


def test_the_parts_keep_to_the_chord_and_clear_of_the_tune():
    """Every sung part is a tone of the chord the organ plays there (a pickup's too, the line before's chord) or
    the tune's own note; never a semitone from the lead; the parts between E3 and the tune; no parallel fifths
    or octaves between the lines."""
    g, p, score = sung()
    times = chord_times(g, p)
    lead = sorted((n for n in score.notes if n.part == "voice"), key=lambda n: n.start)
    for n in (n for n in score.notes if n.part.startswith("choir")):
        at = min(lead, key=lambda v: abs(v.start - n.start))
        assert abs(at.start - n.start) < 0.06 and n.syllable == at.syllable
        d = int(n.pitch) - int(at.pitch)
        assert d % 12 not in (1, 11), (n, at)
        assert FLOOR <= n.pitch <= at.pitch, (n, at)
        pcs = {(p.tonic + t) % 12 for t in chord_tones(band_chord(times, at.start + 0.03), p.mode)}
        assert d == 0 or int(n.pitch) % 12 in pcs, (n, at)


def test_the_lines_and_their_voice_leading(monkeypatch):
    """The four lines over the setting (hymn.voicing): the tenor under the alto under the tune, the pedal under all,
    and parallel fifths or octaves rare."""
    g, p, _score = sung()
    made = []
    real = hymn.voicing
    monkeypatch.setattr(hymn, "voicing", lambda ctx: made.append(ctx) or real(ctx))
    realize(g, p)
    slices = made[0]._hymn
    assert slices
    found = 0
    for a, b in zip(slices, slices[1:]):
        assert b.b < b.t <= b.a <= b.top, (b.u0, b.lines())
        assert 36 <= b.b <= 50 and FLOOR <= b.t
        found += hymn.parallels(a.lines(), b.lines())
    assert found <= len(slices) // 50, (found, len(slices))


def test_unison_verses_and_verses_in_parts():
    """The first verse in unison (everyone on the tune), the second in parts; the refrains in parts."""
    g, p, score = sung()
    lead = {round(n.start, 1): n.pitch for n in score.notes if n.part == "voice"}
    names = [s for s in score.sections]
    verses = [(a, b) for name, a, b in names if name == "verse"]
    refrains = [(a, b) for name, a, b in names if name == "refrain"]

    def unison(a, b):
        ns = [n for n in score.notes if n.part.startswith("choir") and a + 0.3 <= n.start < b - 0.3]
        same = sum(1 for n in ns if lead.get(round(n.start, 1), lead.get(round(n.start - 0.1, 1))) == n.pitch)
        return same / max(1, len(ns))

    assert unison(*verses[0]) > 0.95
    assert unison(*verses[1]) < 0.6 and unison(*refrains[0]) < 0.6


def test_the_organ_gives_the_tune_out_and_its_pedal_takes_the_bass():
    """In the intro nobody sings and the organ's top line is the tune, full; the pedal's notes are its lowest,
    under E3; the organ plays with the singers in the verses."""
    g, p, score = sung()
    organ = [n for n in score.notes if n.part == "pipeorgan"]
    if not organ:
        pytest.skip("a harmonium this time")
    intro = [n for n in organ if n.section == "intro"]
    assert intro and all("full" in n.art for n in intro)
    assert not [n for n in score.notes if n.section == "intro" and (n.part == "voice" or n.part.startswith("choir"))]
    pedal = [n for n in organ if "pedal" in n.art]
    assert pedal and max(n.pitch for n in pedal) < FLOOR and min(n.pitch for n in organ if "pedal" not in n.art) >= FLOOR
    assert any(n.section == "verse" for n in organ)


def test_a_harmonium_for_some_machines():
    """The organ's part is a harmonium's where the machine draws one (S.HYMN.swaps), the same lines."""
    g = G.load(H)
    p = choose_params(g, style="hymn")
    q = replace(p, band=replace(p.band, lineup={"harmonium": 1.0}))
    score = realize(g, q)
    parts = {n.part for n in score.notes}
    assert "harmonium" in parts and "pipeorgan" not in parts
    assert S.HYMN.swaps == {"pipeorgan": {"harmonium": 0.35}}


def test_the_amen_is_everyones():
    g, p, score = sung(ending="amen")
    amen = [n for n in score.notes if n.syllable in ("a", "men") and n.word == "a-men"]
    assert len({n.part for n in amen}) >= 3


def test_the_lead_alone_with_the_organ_when_a_person_says_so():
    g, p, score = sung(backing="")
    assert not [n for n in score.notes if n.part.startswith("choir")]
    from songbird.explain import hymn_words

    assert "the singer alone with the organ" in hymn_words(p)


def test_the_descant_is_the_organs():
    """Over the last refrain, where the rendition has one: the organ's line above the tune, to A5; nobody sings it."""
    g = G.load(H)
    for seed in range(1, 12):
        p = replace(choose_params(g, style="hymn"), seed=seed)
        if hymn.descant(p):
            break
    score = realize(g, p)
    last = [s for s in score.sections if s[0] == "refrain"][-1]
    organ = [n for n in score.notes if n.part in ("pipeorgan", "harmonium") and last[1] <= n.start < last[2]]
    lead = [n for n in score.notes if n.part == "voice" and last[1] <= n.start < last[2]]
    assert max(n.pitch for n in organ) > max(n.pitch for n in lead) + 2 and max(n.pitch for n in organ) <= 81
    sung_top = max(n.pitch for n in score.notes if n.part.startswith("choir"))
    assert sung_top <= max(n.pitch for n in score.notes if n.part == "voice")


def test_the_pipe_organ():
    """Its registrations differ as they should (the full chorus brighter than the diapasons, the flutes darker),
    its pedal sounds an octave under the key (the 16'), and a pipe speaks its upper harmonics first."""
    from songbird.score import Note
    from songbird.synth import pipeorgan

    sr = 44100

    def play(art, pitch=62, dur=1.5):
        notes = [Note(part="pipeorgan", start=0.1, dur=dur, pitch=float(pitch), vel=0.7, art=art)]
        rng, make = np.random.default_rng(1), np.random.default_rng(2)
        return pipeorgan.render("pipeorgan", notes, sr, int(2.0 * sr), rng, make, {})

    def centroid(y):
        s = np.abs(np.fft.rfft(y[int(0.6 * sr):int(1.4 * sr)]))
        f = np.fft.rfftfreq(int(1.4 * sr) - int(0.6 * sr), 1 / sr)
        return float((s * f).sum() / s.sum())

    full, plain, flutes = play("full"), play(""), play("flutes")
    assert np.isfinite(full).all() and np.abs(full).max() > 0.01
    assert centroid(full) > centroid(plain) > centroid(flutes)
    low = play("pedal", pitch=38)  # D2 on the pedal: the bourdon at D1
    s = np.abs(np.fft.rfft(low[int(0.6 * sr):int(1.4 * sr)]))
    f = np.fft.rfftfreq(int(1.4 * sr) - int(0.6 * sr), 1 / sr)
    d1 = s[(f > 34) & (f < 39)].max()
    assert d1 > 0.1 * s[(f > 60) & (f < 80)].max()

    def upper_share(y, a, b):
        seg = y[int(a * sr):int(b * sr)]
        s = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / sr)
        fund = s[(f > 280) & (f < 310)].sum()
        return s[f > 500].sum() / (fund + 1e-12)

    y = play("")
    assert upper_share(y, 0.1, 0.125) > upper_share(y, 0.8, 0.825)


def test_the_page_says_it_plainly(tmp_path, monkeypatch):
    import re

    from songbird import explain, studio as ST

    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    studio = ST.Studio(None, str(H), "fictional:ada", out=tmp_path / "out")
    v = studio.version({"style.name": "hymn"})
    card = next(c for c in explain.view(studio.context, v)["cards"] if c["id"] == "style")
    assert card["value"] == "hymn, stately" and card["styles"]["hymn"] == "hymn"
    assert card["detail"].startswith("organ, and everyone singing in parts")
    assert "the organ's pedal takes the bass" in card["detail"]
    assert not re.search(r"church|chapel|sacred|gospel|hymnal|psalm|congregation", card["detail"], re.I)
    grid = studio.arrangement({"style.name": "hymn"})
    organ = next(pl for pl in grid["players"] if pl["name"] in ("pipeorgan", "harmonium"))
    assert {"hymn", "givingout"} <= {x["id"] for x in organ["patterns"]}
