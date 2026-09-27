"""The quote: before the song, the lead instrument alone plays a line of an older song the genome
names (H: Daisy Bell, the first song a computer sang, 1961), over the drone, when the arrangement's
intro option asks for it (style.intro == "quote"). Nothing else moves: the song starts later by the
quote's bars, as it does after a count-in."""

from dataclasses import replace
from pathlib import Path

from songbird import genome as G
from songbird.realize import choose_params, realize
from songbird.style import INTROS, Style, count_in

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


def quoted(g):
    p = choose_params(g)
    return p, replace(p, style=replace(p.style, intro="quote"))


def test_h_names_daisy_bell_and_its_line_is_on_the_grid():
    g = G.load(H)
    q = g.quote
    assert q is not None and q.bars == 5 and q.pickup == 0 and "Daisy Bell" in g.source["quote"]["about"]
    # Daisy, Daisy, give me your answer, do: so mi do so, | la, ti, do la, | do so, (the chorus, Dacre 1892)
    assert [n.degree for n in q.sung] == [5, 3, 1, -2, -1, 0, 1, -1, 1, -2]
    assert "quote" in INTROS and Style.from_dict({"intro": "quote"}).intro == "quote"


def test_the_quote_clears_its_bars_and_the_lead_plays_it_alone_over_the_drone():
    g = G.load(H)
    plain, p = quoted(g)
    assert count_in(g, plain) == 0 and count_in(g, p) == g.quote.bars * g.meter.bar
    a, b = realize(g, plain), realize(g, p)
    bar = 60.0 / p.tempo * g.meter.bar / g.meter.beat
    shift = g.quote.bars * bar
    assert abs((b.sections[0][1] - a.sections[0][1]) - shift) < 1e-6  # the song starts later by the quote's bars
    first = b.sections[0][1]
    unit = bar / g.meter.bar
    before = [n for n in b.notes if n.start < first - 1.5 * unit]  # before the intro's own pickup, a unit early
    assert {n.part for n in before} == {"whistle", "drone"}, {n.part for n in before}
    tune = sorted((n for n in before if n.part == "whistle" and n.dur >= 0.25), key=lambda n: n.start)
    pcs = [int(round(n.pitch - p.tonic)) % 12 for n in tune]
    assert set(pcs) == {7, 4, 0, 9, 11} and pcs[0] == 7 and pcs[-1] == 7, pcs  # so mi do so, la, ti, do la, do so,
    assert min(n.start for n in before if n.part == "drone") < tune[0].start - 0.5  # the drone alone first, then the whistle
    # after the quote, the intro's bass waits for the second phrase; the harp and whistle start it
    assert min(n.start for n in b.notes if n.part == "bass") >= first + 2 * bar - 0.1
    assert min(n.start for n in b.notes if n.part == "harp") < first + 0.5
    assert min(n.start for n in a.notes if n.part == "bass") < a.sections[0][1] + 0.5  # as it doesn't without one
    # the song itself is as it was, later by the quote: every sung note, and every part's notes by pitch
    va, vb = a.part("voice"), b.part("voice")
    assert len(va) == len(vb) and all(abs((y.start - x.start) - shift) < 1e-6 and y.pitch == x.pitch
                                      for x, y in zip(va, vb))
    for part in {n.part for n in a.notes} - {"drone", "bass"}:  # the drone runs on from the quote, the bass waits
        mine = sorted(round(n.pitch) for n in a.notes if n.part == part)
        theirs = sorted(round(n.pitch) for n in b.notes if n.part == part and n.start >= first - 1.5 * unit)
        assert mine == theirs, part


def test_a_song_with_no_quote_to_play_starts_as_it_did():
    g = G.load(H)
    bare = G.from_dict({k: v for k, v in g.source.items() if k != "quote"})
    assert bare.quote is None
    plain, p = quoted(bare)
    assert count_in(bare, p) == 0
    a, b = realize(bare, plain), realize(bare, p)
    assert b.sections == a.sections and len(b.notes) == len(a.notes)


def test_the_quote_as_a_coda_the_whistle_alone_over_the_last_chord():
    """The leitmotif the artist asked for instead of an intro: after the last line, as the last chord rings two
    bars on, the whistle alone plays the quote's opening (Daisy, Daisy: so mi do so,), softly."""
    g = G.load(H)
    plain = choose_params(g)
    p = replace(plain, style=replace(plain.style, coda="quote"))
    a, b = realize(g, plain), realize(g, p)
    bar = 60.0 / p.tempo * g.meter.bar / g.meter.beat
    assert b.sections[0] == a.sections[0]  # nothing before the song moves
    sung_end = max(n.start + n.dur for n in list(b.part("voice")) + [n for n in b.notes if n.part.startswith("choir")])
    after = [n for n in b.notes if n.start > sung_end + 0.2]  # begun after the last sung note
    assert {n.part for n in after} == {"whistle"}, {n.part for n in after}
    pcs = [int(round(n.pitch - p.tonic)) % 12 for n in sorted(after, key=lambda n: n.start) if n.dur >= 0.25]
    assert pcs == [7, 4, 0, 7], pcs
    assert b.duration > a.duration + 1.5 * bar  # the last chord rings on under it (the ritardando stretches the bars)
    ringing = [n for n in b.notes if n.start < sung_end - 0.5 and n.start + n.dur > after[0].start + 0.5 and n.part != "drum"]
    assert {"drone"} <= {n.part for n in ringing}, {n.part for n in ringing}
    assert len(a.part("voice")) == len(b.part("voice"))


def test_the_quote_woven_into_the_bridge_in_the_whistles_voice():
    """The leitmotif: in the bridge's third phrase, where the lineage sings, the whistle plays Daisy, Daisy
    (so mi do so,), each a tone of the chord under it, the fiddle's pad resting; nothing else moves, and by chance about a third of
    renditions do it."""
    g = G.load(H)
    plain = choose_params(g)
    p = replace(plain, style=replace(plain.style, motif="bridge"))
    a, b = realize(g, plain), realize(g, p)
    assert b.sections == a.sections and len(b.part("voice")) == len(a.part("voice"))
    bridge = next(s for s in b.sections if s[0] == "bridge")
    bar = 60.0 / p.tempo * g.meter.bar / g.meter.beat
    third = (bridge[1] + 4 * bar, bridge[1] + 6 * bar)  # the bridge's third phrase: bars 5 and 6 of eight
    whistle = sorted((n for n in b.notes if n.part == "whistle" and third[0] - 0.2 <= n.start < third[1] - 0.2), key=lambda n: n.start)
    pcs = [int(round(n.pitch - p.tonic)) % 12 for n in whistle if n.dur >= 0.4]
    assert pcs == [7, 4, 0, 7], pcs
    choir_top = max(n.pitch for n in b.notes if n.part.startswith("choir") or n.part == "voice")
    assert all(n.pitch > choir_top for n in whistle)  # above the singers
    assert not [n for n in a.notes if n.part == "whistle" and third[0] - 0.2 <= n.start < third[1] - 0.2]  # silent there without it
    fiddle_then = [n for n in b.notes if n.part == "fiddle" and third[0] + 0.3 <= n.start < third[1] - 0.3]
    assert not fiddle_then, fiddle_then  # the pad rests while the motif plays
    from songbird.band import wants_motif
    from songbird.band import Context  # noqa: F401  (the chance is drawn from the seed)
    chance = replace(plain, style=replace(plain.style, motif="chance"))
    hits = 0
    for seed in range(60):
        score = realize(g, replace(chance, seed=seed))
        fid = [n for n in score.notes if n.part == "whistle" and third[0] - 0.2 <= n.start < third[1] - 0.2 and n.dur >= 0.4]
        hits += [int(round(n.pitch - p.tonic)) % 12 for n in fid] == [7, 4, 0, 7]
    assert 8 <= hits <= 32, hits
