"""Swing keeps every beat where it is and delays only each beat's off-beat half, whatever the pickup.

H's first pickup is an eighth (lead 1 on a two-unit beat), so its beats fall on odd grid units; the
swing's phase is counted from the first bar line, not from the pickup. D starts on its bar line and
J has a whole-beat pickup: the same must hold for them.
"""

from dataclasses import replace

import pytest

from songbird import genome as G
from songbird import realize as realize_mod
from songbird.realize import Params, realize


ARRANGE = realize_mod.band_mod.arrange


def clocked(monkeypatch, g, params):
    """The score, with the pickup, end, melody and grid-to-seconds mapping the band was given."""
    seen = {}

    def spy(genome, params, placed, lead, end, melody, seconds):
        seen.update(lead=lead, end=end, melody=melody, seconds=seconds)
        return ARRANGE(genome, params, placed, lead, end, melody, seconds)

    monkeypatch.setattr(realize_mod.band_mod, "arrange", spy)
    return realize(g, params), seen


@pytest.mark.parametrize("song", ["h-now-its-by-you", "d-in-by-the-ear", "j-goes-like-this"])
@pytest.mark.parametrize("swing", [0.27, 1.0])
def test_swing_keeps_the_beats_and_delays_the_off_beats(monkeypatch, song, swing):
    g = G.load(f"songs/{song}.json")
    base = Params.from_dict(g.seed_params)
    straight = replace(base, humanize=0.0, band=replace(base.band, swing=0.0))
    lilting = replace(straight, band=replace(base.band, swing=swing))
    s0, a = clocked(monkeypatch, g, straight)
    s1, b = clocked(monkeypatch, g, lilting)
    lead, beat = b["lead"], g.meter.beat
    if song == "h-now-its-by-you":
        assert lead % beat != 0  # the case this guards: a pickup that isn't a whole number of beats

    # every beat, counted from the first bar line, is where it was without swing
    beats = [lead + k * beat for k in range(int((b["end"] - lead) // beat) + 1)]
    assert all(b["seconds"](u) == a["seconds"](u) for u in beats)
    # every off-beat half is later: by swing/6 of a beat outside the final ritardando
    unit = 60.0 / base.tempo / beat
    first = lead + beat / 2
    assert b["seconds"](first) - a["seconds"](first) == pytest.approx(swing * beat / 6 * unit)
    assert all(b["seconds"](u + beat / 2) > a["seconds"](u + beat / 2) for u in beats[:-1])
    # the bar lines don't move, so every section starts where it did
    assert s1.sections == s0.sections

    # the voice sings on that clock: its notes on a beat don't move, its off-beat eighths are later
    v0 = [n for n in s0.notes if n.part == "voice"]
    v1 = [n for n in s1.notes if n.part == "voice"]
    sung = [m for m in b["melody"] if m["syllable"]]
    assert len(v0) == len(v1) == len(sung)
    moved = {"on": 0, "off": 0}
    for n0, n1, m in zip(v0, v1, sung):
        assert n1.start == pytest.approx(max(0.0, b["seconds"](m["u"])))
        phase = (m["u"] - lead) % beat
        if phase == 0:
            assert n1.start == n0.start
            moved["on"] += 1
        elif phase == beat / 2:
            assert n1.start > n0.start
            moved["off"] += 1
    assert moved["on"] and moved["off"]

    # and so does the band: the same notes, none earlier, and the ones on the beat unmoved
    for part in sorted({n.part for n in s0.notes} - {"voice"}):
        p0 = [n for n in s0.notes if n.part == part]
        p1 = [n for n in s1.notes if n.part == part]
        assert len(p0) == len(p1)
        assert all(y.start >= x.start - 1e-12 for x, y in zip(p0, p1))
    unmoved = sum(x.start == y.start for x, y in zip(s0.notes, s1.notes) if x.part == y.part != "voice")
    assert unmoved > 0
