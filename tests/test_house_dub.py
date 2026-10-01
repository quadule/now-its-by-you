"""House and dub (docs/STYLES.md, "House and dub"): where their players' notes land, what a style's own sound and
desk bring, the drop and the version, the record, and that nothing else moved."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import genome as G
from songbird import style as S
from songbird.realize import Params, choose_params, realize, timeline

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"
OFF = {"intro": "", "alone": 0, "stops": 0, "breakdown": False, "bridge": "", "lift": False, "ending": "",
       "entrances": False, "backing": ""}


def styled(name, **options):
    g = G.load(H)
    return g, choose_params(g, style=name, arrange={**OFF, **options})


def spans_of(score, name):
    return [(a, b) for n, a, b in score.sections if n == name]


def inside(t, spans, pad=0.05):
    return any(a + pad <= t < b - pad for a, b in spans)


def beats_in(clock, spans):
    return [(t, bar) for t, bar in clock.beats() if inside(t, spans)]


# --- house ------------------------------------------------------------------------------------------------------


def test_house_refrains_are_four_on_the_floor_with_claps_and_off_beat_hats():
    g, p = styled("house", drop=0)  # (a drop's refrain rolls its bass: below)
    score = realize(g, p)
    clock = timeline(g, p)
    beat = 60.0 / p.tempo
    refrains = spans_of(score, "refrain")
    machine = [n for n in score.notes if n.part == "drummachine"]
    kicks = [n.start for n in machine if n.art == "kick"]
    beats = beats_in(clock, refrains)
    assert beats and all(min(abs(k - t) for k in kicks) < 0.04 for t, _ in beats)  # a kick on every beat
    claps = [n.start for n in machine if n.art == "clap" and inside(n.start, refrains)]
    ks = [t for t, _ in clock.beats()]
    index = [int(np.argmin([abs(c - t) for t in ks])) for c in claps]
    bars = {i for i, (t, bar) in enumerate(clock.beats()) if bar}
    first = min(bars)
    assert claps and all((i - first) % 4 in (1, 3) for i in index)  # on two and four
    opens = [n.start for n in machine if n.art == "hat-open" and inside(n.start, refrains)]
    assert opens and all(min(abs(o - (t + beat / 2)) for t in ks) < 0.04 for o in opens)  # on the off-beats
    # the bass in octaves on the eighths (2026-09-30, evening: the refrains' riff), its octave on the off-beats
    bass = [n for n in score.notes if n.part == "synthbass" and inside(n.start, refrains)]
    offs = [n for n in bass if min(abs(n.start - (t + beat / 2)) for t in ks) < 0.04]
    ons = [n for n in bass if min(abs(n.start - t) for t in ks) < 0.04]
    assert bass and len(offs) + len(ons) > 0.95 * len(bass) and len(offs) > 0.4 * len(bass)
    assert np.mean([n.pitch for n in offs]) > np.mean([n.pitch for n in ons]) + 6


def test_house_brings_its_909_and_pumps_and_a_person_can_turn_them_off():
    g, p = styled("house")
    score = realize(g, p)
    players = score.sound["players"]
    assert players["drummachine"]["kit"] == "909"
    assert players["synthpad"]["sidechain"]["depth"] == 8.0 and players["synthbass"]["sidechain"]["depth"] == 4.0
    assert {pl for _, pl in score.sound["triggers"]} >= {"synthpad", "synthbass"}
    off = replace(p, sound={"players": {"synthpad": {"sidechain": {"depth": 0.0, "release": 0.55, "key": "kick",
                                                                    "sections": None}},
                                         "drummachine": {"kit": "808"}}})
    again = realize(g, off)
    assert "sidechain" not in again.sound["players"].get("synthpad", {})
    assert again.sound["players"]["drummachine"]["kit"] == "808"
    assert "synthpad" not in {pl for _, pl in again.sound["triggers"]}


def test_a_house_drop_breaks_down_opens_the_filter_and_hits_with_the_ride():
    g, p = styled("house", drop=2)
    assert p.style.drop == 2
    score = realize(g, p)
    refrains = spans_of(score, "refrain")
    assert len(refrains) >= 3
    breakdown = (refrains[1][1], refrains[2][0])
    band = [n for n in score.notes if n.part not in ("voice",) and not n.part.startswith("choir")]
    held = {n.part for n in band if breakdown[0] + 0.05 <= n.start < breakdown[1] - 0.05}
    assert "synthpad" in held and "synthbass" not in held  # the singer with the pad, no bass
    sung = [(a, b) for name, a, b in score.sections if breakdown[0] - 0.05 <= a < breakdown[1] - 0.05
            and g.section(name).lyrics]
    under = {n.part for n in band if any(a + 0.05 <= n.start < b - 0.05 for a, b in sung)}
    assert under <= {"synthpad", "drummachine"}  # where the singer sings it, the pad alone (and the roll)
    rolled = [n for n in band if n.part == "drummachine" and breakdown[0] + 0.05 <= n.start < breakdown[1]]
    assert rolled and {n.art for n in rolled} == {"snare"}  # only the roll's strokes, in its last bars
    kinds = {t["kind"]: t for t in score.sound["transitions"]}
    assert kinds["riser"]["end"] == pytest.approx(refrains[2][0], abs=0.05)
    assert kinds["sweep-open"]["start"] == pytest.approx(breakdown[0], abs=0.05)  # opening across the breakdown
    ride = [n for n in band if n.part == "drummachine" and n.art == "ride"]
    assert ride and all(inside(n.start, [refrains[2]], 0.0) for n in ride)  # the ride in the drop


def test_house_draws_its_drop_and_no_other_style_does():
    g = G.load(H)
    from songbird import drift as D, harvest as HV

    drops = []
    for k in range(8):
        voice = HV.fictional(f"h{k}")
        p = choose_params(g, None, voice, D.drift(D.parse("2026-09-30"), voice.hash), style="house")
        drops.append(p.style.drop)
    assert sum(d > 0 for d in drops) >= 4  # most renditions (0.8)
    for name in S.RING:
        assert "drop" not in S.STYLES[name].options and "version" not in S.STYLES[name].options.get("ending", {})
        assert not S.STYLES[name].sound and not S.STYLES[name].desk


# --- dub --------------------------------------------------------------------------------------------------------


def test_dub_is_a_one_drop_with_the_skank_on_the_off_beats():
    g, p = styled("dub")
    score = realize(g, p)
    clock = timeline(g, p)
    verses = spans_of(score, "verse")
    ks = clock.beats()
    first = min(i for i, (_, bar) in enumerate(ks) if bar)
    kit = [n for n in score.notes if n.part == "kit" and inside(n.start, verses)]
    kicks = [n.start for n in kit if n.art == "kick"]
    crosses = [n.start for n in kit if n.art == "snare-cross"]
    at = [int(np.argmin([abs(k - t) for t, _ in ks])) for k in kicks]
    assert kicks and all((i - first) % 4 == 2 for i in at)  # the kick on three, nothing on the one
    assert crosses and all(min(abs(c - k) for k in kicks) < 0.03 for c in crosses)  # with the cross-stick
    skank = [n.start for n in score.notes if n.part == "electric" and inside(n.start, verses)]
    offs = [clock.seconds(clock.lead + j * g.meter.beat + g.meter.beat / 2) for j in range(-2, 400)]
    assert skank and all(min(abs(s - o) for o in offs) < 0.04 for s in skank)  # on the (swung) off-beats
    bass = [n.start for n in score.notes if n.part == "ebass" and inside(n.start, verses)]
    at = [int(np.argmin([abs(b - t) for t, _ in ks])) for b in bass]
    near = [min(abs(b - t) for t, _ in ks) for b in bass]
    assert not [1 for i, d in zip(at, near) if (i - first) % 4 == 2 and d < 0.03]  # the bass leaves three to the drop


def test_a_dub_version_is_played_after_the_song_and_the_desk_throws():
    g, plain = styled("dub")
    g, p = styled("dub", ending="version")
    a, b = realize(g, plain), realize(g, p)
    bar = 60.0 / p.tempo * g.meter.bar / g.meter.beat
    sung = max(n.start + n.dur for n in b.part("voice"))
    # the song's own sections, the version after them (the last line not slowed: the version holds its tempo)
    assert [s[:2] for s in b.sections] == [s[:2] for s in a.sections] and b.sections[-1][2] < a.sections[-1][2]
    after = [n for n in b.notes if n.start > sung + 0.2]
    assert {"kit", "ebass"} <= {n.part for n in after}
    assert max(n.start for n in after) > sung + 7 * bar  # eight bars of it
    assert not [n for n in after if n.part == "voice"]
    throws = b.sound["throws"]
    assert any(t["part"] == "voice" and t["end"] >= sung - 0.5 for t in throws)  # the last line into the echo
    assert {t["kind"] for t in throws} == {"echo", "spring"}
    assert all(t["time"] == pytest.approx(0.75 * 60.0 / p.tempo) for t in throws if t["kind"] == "echo")
    assert realize(g, p).notes == b.notes and realize(g, p).sound == b.sound  # the same again


def test_the_echo_repeats_at_its_time_darker_and_the_spring_rings():
    from songbird.synth import dub

    sr = 44100
    x = np.zeros(int(0.1 * sr))
    x[:200] = np.hanning(200)
    y = dub.echo(x, sr, 0.3, 0.6, 1.0, 1)
    env = np.abs(y).sum(axis=1)
    peaks = [int(np.argmax(env[int((k * 0.3 - 0.05) * sr): int((k * 0.3 + 0.05) * sr)])) + int((k * 0.3 - 0.05) * sr)
             for k in (1, 2, 3)]
    assert all(abs(p / sr - k * 0.3) < 0.01 for p, k in zip(peaks, (1, 2, 3)))
    levels = [env[p - 400: p + 400].max() for p in peaks]
    assert levels[0] > levels[1] > levels[2]
    s = dub.spring(x, sr, 1.0)
    assert s.shape[1] == 2 and np.abs(s[int(1.0 * sr):]).max() > 1e-4  # still ringing a second on


def test_the_sweep_that_opens_lets_the_top_back_in():
    from songbird.synth import sweeps

    sr = 44100
    rng = np.random.default_rng(1)
    x = rng.standard_normal((4 * sr, 2))
    y = x.copy()
    sweeps.sweep([y], sr, [("sweep-open", 0, 4 * sr)])

    def top(z):
        f = np.abs(np.fft.rfft(z[:, 0]))
        freqs = np.fft.rfftfreq(len(z), 1 / sr)
        return f[freqs > 4000].sum() / f.sum()

    assert top(y[: sr // 2]) < 0.2 * top(x[: sr // 2]) and top(y[-sr // 2:]) > 0.6 * top(x[-sr // 2:])


# --- the record and the ring --------------------------------------------------------------------------------------


def test_the_drop_leaves_no_trace_while_off_and_travels_when_on():
    g, p = styled("house", drop=2)
    assert Params.from_dict(p.to_dict()).style.drop == 2
    plain = S.Style(name="lofi")
    assert "drop" not in plain.to_dict() and S.Style.from_dict(plain.to_dict()) == plain
    assert S.Style().seed


def test_a_child_of_house_or_dub_keeps_it_or_steps_beside_its_anchor():
    from songbird import drift as D, harvest as HV, variation as V

    seen = {"house": set(), "dub": set()}
    for k in range(10):
        voice = HV.fictional(f"m{k}")
        c = V.character(voice)
        for name in seen:
            for day in ("2026-03-01", "2026-06-01", "2026-09-01"):
                seen[name].add(S.place(S.Style(name=name), c, D.drift(D.parse(day), voice.hash)))
    assert seen["house"] <= {"house", *S.neighbours("synthfolk")} and "house" in seen["house"]
    assert seen["dub"] <= {"dub", *S.neighbours("lofi")} and "dub" in seen["dub"]


@pytest.mark.parametrize("name", ["house", "dub"])
def test_a_style_can_be_chosen_as_an_edit(name):
    from songbird.edits import Overrides

    g = G.load(H)
    p = choose_params(g, overrides=Overrides(g, {"style.name": name, "style.ending": "version", "style.drop": 1}))
    assert p.style.name == name and p.style.ending == "version" and p.style.drop == 1


# --- the page -----------------------------------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


def test_the_studio_shows_their_patterns_sound_and_options(home):
    import re

    from songbird import explain, studio as ST

    studio = ST.Studio(None, str(H), "fictional:ada", out=home / "out")
    forbidden = re.compile(r"\b(genome|drift|harvest|hash|knob|params?|seed)\b", re.I)
    v = studio.version({"style.name": "house", "style.drop": 2})
    view = explain.view(studio.context, v)
    card = next(c for c in view["cards"] if c["id"] == "style")
    assert "house" in card["styles"] and "dub" not in card["styles"] and "version" in card["endings"]  # hidden: its own
    assert "the drop" in card["detail"]
    for c in view["cards"]:
        for text in [c["value"], c.get("detail") or ""] + [r["text"] for r in c["reasons"]]:
            assert not forbidden.search(text), text
    grid = studio.arrangement({"style.name": "house", "style.drop": 2})
    machine = next(p for p in grid["players"] if p["name"] == "drummachine")
    assert {"floor", "house", "drop"} <= {x["id"] for x in machine["patterns"]}
    assert any(o["field"] == "drop" for s in grid["sections"] for o in s["options"])
    out = [c for c in grid["cells"] if c["player"] == "drummachine" and c["value"]["pattern"] is None]
    assert any("breakdown before the drop" in r["text"] for c in out for r in c["why"])
    sound = studio.sound({"style.name": "house"})
    dm = next(p for p in sound["players"] if p["player"] == "drummachine")
    pad = next(p for p in sound["players"] if p["player"] == "synthpad")
    assert dm["kit"]["value"] == "909" and not dm["kit"]["yours"]
    assert pad["sidechain"]["value"]["depth"] == 8.0 and not pad["sidechain"]["yours"]
    grid = studio.arrangement({"style.name": "dub"})
    kit = next(p for p in grid["players"] if p["name"] == "kit")
    assert {"onedrop", "steppers"} <= {x["id"] for x in kit["patterns"]}
    assert "melodica" in {p["name"] for p in grid["players"]}


# --- house and dub, again (2026-09-30, evening; docs/STYLES.md, "House and dub, again") -------------------------


def chords_by_section(g, p):
    """Each section's chords as realize lays them (idioms.chord_times), by the score's sections."""
    from songbird.idioms import chord_times

    score = realize(g, p)
    out: dict = {}
    for a, b, symbol in chord_times(g, p):
        name = next((n for n, s0, s1 in score.sections if s0 - 1e-6 <= a < s1 - 1e-6), None)
        out.setdefault(name, []).append(symbol)
    return out


def test_house_plays_a_loop_of_its_own_fitted_to_the_tune():
    g, p = styled("house", drop=0, loop="vamp")
    by = chords_by_section(g, p)
    for name, symbols in by.items():
        if name and name.startswith("bridge"):
            assert set(symbols) <= {"vi", "I", "V"}  # the breakdown's heart keeps the song's own
        elif name:
            assert set(symbols) == {"vim7", "IVmaj7"}, (name, symbols)  # Bm7 and Gmaj7, round and round
    assert S.loop_symbols((6, 4, 1, 5), True, "ionian") == ["vim7", "IVmaj7", "Iadd9", "V7"]  # the mode's own
    assert S.loop_symbols((6, 4), True, "aeolian") == ["VImaj7", "ivm7"]
    fit = S.fitting_loops(g, S.HOUSE, "ionian")
    assert {"vamp", "lift", "home"} <= set(fit) and "pop" not in fit and "minor" not in fit
    assert S.fitting_loops(g, S.DUB, "aeolian") == ["song"]  # nothing fits: the song's own chords
    # the song's own chords, asked for; a person's chords for a line win over the loop there
    g, own = styled("house", drop=0, loop="song")
    assert "vim7" not in {s for v in chords_by_section(g, own).values() for s in v}
    mine = replace(p, composition={"chords": {"r1": [["I"], ["V"]]}})
    from songbird.composition import form_phrases, harmonized

    lines = form_phrases(harmonized(g, mine), mine)
    assert all(ph.chords == (("I",), ("V",)) for ph in lines if ph.id == "r1")
    assert any(ph.chords == (("vim7",), ("IVmaj7",)) for ph in lines if ph.id == "r2")
    # the seventh a colour: where a sung note is a semitone off it, the stabs leave it out (Gmaj7's F♯ under a G)
    from songbird.idioms import chord_times

    score = realize(g, p)
    sung = [n for n in score.notes if n.part == "voice"]
    seventh = (p.tonic + 4) % 12
    under = [(a, b) for a, b, symbol in chord_times(g, p) if symbol == "IVmaj7"]
    for n in score.notes:
        if n.part == "piano" and round(n.pitch) % 12 == seventh and inside(n.start, under, 0.0):
            near = [s for s in sung if s.start - 0.01 <= n.start < s.start + s.dur]
            assert not any(round(s.pitch) % 12 == (seventh + 1) % 12 for s in near)


def test_house_lays_its_own_lengths_and_a_person_can_change_them():
    from songbird.takeover import phrase_plan

    g, p = styled("house", drop=2)
    plan = phrase_plan(g, p)
    bars = [sum(g.phrases[x].bars for x, _ in lines) for lines in plan]
    form = list(p.form)
    assert bars[form.index("intro")] == 16 and all(bars[k] == 4 for k, n in enumerate(form) if n == "turn")
    refrains = [k for k, n in enumerate(form) if n == "refrain"]
    drop = plan[refrains[2]]
    assert [s for _, s in drop[:4]] == [False] * 4 and all(s for _, s in drop[4:8])  # the hook first, then sung
    assert {x for x, _ in drop[:4]} == {"t1"}
    # the words still sung in order: every refrain's first line asks its question
    score = realize(g, p)
    firsts = [n for n in score.part("voice") if n.syllable == "Who"]
    assert len(firsts) == len(refrains)
    mine = replace(p, composition={"arrange": {"intro:0": {"bars": 4}}})
    assert sum(g.phrases[x].bars for x, _ in phrase_plan(g, mine)[0]) == 4


def test_house_chops_its_hook_on_the_grid():
    g, p = styled("house", drop=2)
    score = realize(g, p)
    chop = list(score.part("chop"))
    assert chop and {n.word for n in chop} <= {"No-bo-dy", "knows.", "now", "it's", "by", "*you*."}
    assert sum(n.word == "knows." for n in chop) >= 12  # the hook, over and over
    voice = list(score.part("voice"))
    assert not [c for c in chop for v in voice if c.start < v.start + v.dur and v.start < c.start + c.dur]
    beat = 60.0 / p.tempo
    clock = timeline(g, p)
    grid = [clock.seconds(clock.lead + k * g.meter.beat / 4) for k in range(-8, 2000)]
    assert all(min(abs(n.start - t) for t in grid) < 1e-6 for n in chop)  # on the sixteenths, no jitter or lay
    assert all(n.dur <= beat for n in chop)  # short
    refrains = spans_of(score, "refrain")
    drop = [n for n in chop if inside(n.start, refrains[2:3], 0.0)]
    assert {n.word for n in drop} >= {"No-bo-dy", "now"}  # the drop: the call and "now it's by you"
    again = realize(g, p)
    assert list(again.part("chop")) == chop


def test_house_chop_never_starts_mid_word():
    """The artist (2026-09-30, night): the hook "doesn't work well" where the first turn opens. A figure's first
    syllable was left out wherever the singer's last note ended on the turn's downbeat ("bo-dy knows", no "No"); now
    a sung note ending as a figure begins is clear of it, and a figure is sung from a word's first syllable to a
    word's last, or not at all."""
    for seed in (1, 3, 6):
        g, p = styled("house", drop=2)
        p = replace(p, seed=seed)  # each rhythm of the three, by the rendition's draw
        score = realize(g, p)
        clock = timeline(g, p)
        bars = [t for t, bar in clock.beats() if bar]
        chop = sorted(score.part("chop"), key=lambda n: n.start)
        by_bar = {}
        for n in chop:
            by_bar.setdefault(max(t for t in bars if t <= n.start + 1e-6), []).append(n)
        for figure in by_bar.values():
            assert figure[0].word.startswith(figure[0].syllable)  # "No", "now": never "bo"
            assert figure[-1].word.endswith(figure[-1].syllable)  # never ending on "No" or "bo"
        sixteenth = 15.0 / p.tempo
        answered = 0
        for a, b in spans_of(score, "turn"):  # each turn after a sung refrain: the hook from its first bar
            first = next(n for n in chop if n.start >= a - 1e-6)
            assert first.syllable == "No" and first.start < a + 2 * sixteenth + 1e-6
            figures = [by_bar[t] for t in sorted(by_bar) if a - 1e-6 <= t < b - 1e-6]
            assert all(f[0].syllable == "No" for f in figures[::2])  # the call, and in a full turn the answer
            answered += sum(f[0].syllable == "now" for f in figures[1::2])
        assert answered >= 2  # (the drop's breakdown sings its turn's call alone, once in two bars, soft)
        stutter = S.HOUSE_HOOK["rhythms"]["stutter"][0]
        again = [(step, length) for (_, j0, _), (step, j, length) in zip(stutter, stutter[1:]) if j == j0]
        assert again and all(step % 2 == 0 and length >= 2 for step, length in again)  # "knows, knows" on eighths


def test_house_bass_riffs_in_octaves_and_its_intro_builds_in_layers():
    g, p = styled("house", drop=0, intro="lead")
    score = realize(g, p)
    refrains = spans_of(score, "refrain")
    bass = [n for n in score.notes if n.part == "synthbass" and inside(n.start, refrains)]
    pitches = sorted({round(n.pitch) for n in bass})
    assert any(q - r == 12 for r in pitches for q in pitches)  # the root and its octave
    intro = spans_of(score, "intro")[0]
    bar = 4 * 60.0 / p.tempo

    def first(part):
        return min(n.start for n in score.notes if n.part == part and inside(n.start, [intro], 0.0))

    assert first("drummachine") < intro[0] + 0.2
    assert first("synthbass") >= intro[0] + 4 * bar - 0.05
    assert first("synthpad") >= intro[0] + 8 * bar - 0.05
    assert first("piano") >= intro[0] + 12 * bar - 0.05  # the tune at thirteen


def test_dub_dissolves_into_its_version_after_the_first_refrain():
    from songbird.takeover import spans

    g, p = styled("dub", dissolve=1, ending="version", loop="minor")
    score = realize(g, p)
    clock = timeline(g, p)
    sp = spans(g, p, clock.lead)
    start = S.dissolved_from(g, p)
    assert start == list(p.form).index("refrain") + 1
    t0 = clock.seconds(sp[start][2])
    bridge = [(clock.seconds(a), clock.seconds(b)) for k, (_, n, a, b) in enumerate(sp) if n == "bridge" and k >= start]
    voice = list(score.part("voice"))
    before = [n for n in voice if n.start < t0 - 0.5]
    after = [n for n in voice if n.start >= t0 and not inside(n.start, bridge, -1.0)]
    own = sum(len(g.phrases[x].sung) for k in range(start, len(p.form)) if p.form[k] != "bridge"
              for x in g.section(p.form[k]).phrases)
    assert before and len(after) < 0.6 * own  # fragments
    assert " ".join(n.word for n in after).count("No-bo-dy") >= 2  # every refrain in the version keeps "nobody knows"
    inbridge = [n for n in voice if inside(n.start, bridge, 0.0)]
    assert len(inbridge) >= sum(len(g.phrases[x].sung) for x in g.section("bridge").phrases) - 1  # the bridge whole
    melodica = [n for n in score.notes if n.part == "melodica" and n.start >= t0]
    assert melodica  # the tune in pieces where the singer leaves it
    throws = score.sound["throws"]
    assert any(t["part"] == "voice" and t["feedback"] == 0.72 for t in throws)  # the fragments' long tails
    assert any(t["kind"].startswith("sweep") for t in score.sound.get("transitions", []))
    by = chords_by_section(g, p)
    assert set(by["intro"]) | set(by["verse"]) >= {"I", "IV", "V"}  # sung straight over the song's chords
    assert {"vi", "IV"} <= set(by["refrain"])  # the riddim in the version's refrains
    assert realize(g, p).sound == score.sound


def test_the_new_options_leave_no_trace_while_off_and_travel_when_on():
    plain = S.Style(name="house", drop=2)
    assert "loop" not in plain.to_dict() and "dissolve" not in plain.to_dict()
    on = S.Style(name="dub", loop="minor", dissolve=1)
    assert S.Style.from_dict(on.to_dict()) == on
    for name in [*S.RING, "acappella", "jig"]:
        sdef = S.STYLES[name]
        assert not sdef.loops and not sdef.form and not sdef.hook and "dissolve" not in sdef.options
    # a house record from before (no loop) still loads and sings, its loop the best fit
    g = G.load(H)
    old = choose_params(g, style="house", arrange={**OFF, "drop": 2}).to_dict()
    old["style"].pop("loop", None)
    p = Params.from_dict(old)
    assert p.style.loop == "" and S.loop_of(g, p) is not None and realize(g, p).part("chop")


def test_house_and_dub_are_hidden_from_the_picker_but_still_play():
    """Not offered for now (the artist, 2026-09-30), unless a version already plays one; a record or --style still does."""
    assert "house" not in S.offered() and "dub" not in S.offered()
    assert {"acappella", "jig", *S.RING} <= set(S.offered())
    assert "house" in S.offered("house") and "dub" not in S.offered("house")
    assert "house" in S.STYLES and "dub" in S.STYLES


def test_the_singer_lets_go_before_the_last_hook():
    """The last refrain's last word ends with its line, not under the hook's eight bars after it (it was held 16.9 s
    in house2-ada); a style without bars of its own after the last line holds it as ever."""
    g, p = styled("house", drop=2)
    p = replace(p, form=("verse", "refrain", "turn", "verse", "refrain", "turn", "bridge", "refrain"))
    last = max((n for n in realize(g, p).notes if n.part == "voice"), key=lambda n: n.start)
    assert last.dur < 60 / p.tempo * g.meter.bar / g.meter.beat  # within its bar, not the hook's eight
