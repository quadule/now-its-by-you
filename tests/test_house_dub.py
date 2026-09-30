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
    # the bass on the off-beats, never on a kick
    bass = [n.start for n in score.notes if n.part == "synthbass" and inside(n.start, refrains)]
    assert bass and sum(min(abs(b - (t + beat / 2)) for t in ks) < 0.04 for b in bass) > 0.8 * len(bass)


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
    assert held <= {"synthpad", "drummachine"}  # the singer with the pad (and the roll into the drop)
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


def test_a_child_of_house_or_dub_stays_or_steps_onto_the_ring_at_its_anchor():
    from songbird import drift as D, harvest as HV, variation as V

    seen = {"house": set(), "dub": set()}
    for k in range(10):
        voice = HV.fictional(f"m{k}")
        c = V.character(voice)
        for name in seen:
            for day in ("2026-03-01", "2026-06-01", "2026-09-01"):
                seen[name].add(S.place(S.Style(name=name), c, D.drift(D.parse(day), voice.hash)))
    assert seen["house"] <= {"house", "synthfolk"} and "house" in seen["house"]
    assert seen["dub"] <= {"dub", "lofi"} and "dub" in seen["dub"]


@pytest.mark.parametrize("name", ["house", "dub"])
def test_a_style_can_be_chosen_as_an_edit(name):
    from songbird.edits import Overrides

    g = G.load(H)
    p = choose_params(g, overrides=Overrides(g, {"style.name": name, "style.ending": "version", "style.drop": 1}))
    assert p.style.name == name and p.style.ending == "version" and p.style.drop == 1
