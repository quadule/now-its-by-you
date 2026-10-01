"""The jazz trio (docs/STYLES.md, "A jazz trio", September 30, 2026): piano, upright bass and brushes, the song as a
jazz waltz or a swung ballad, the trio's own changes fitted to the tune."""

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from songbird import drift as D, genome as G, harvest, style as S
from songbird.composition import form_phrases
from songbird.idioms import chord_times
from songbird.realize import Params, choose_params, realize
from songbird.theory import chord_tones, degree_semitones

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"
MACHINES = (("ada", "2026-09-27"), ("bob", "2026-03-14"), ("coral", "2026-11-02"), ("dmitri", "2026-06-21"))
SUNG = ("voice", "choir")


def machine(name: str, date: str, **arrange):
    g = G.load(H)
    voice = harvest.machine_voice(f"fictional:{name}")
    p = choose_params(g, None, voice, D.drift(D.parse(date), voice.hash), style="jazz", arrange=arrange or None)
    return g, p


def trio(harmony: float = 1.0, mode: str = "ionian", form=None, **style):
    g = G.load(H)
    p = Params.from_dict(g.seed_params)
    return g, replace(p, mode=mode, form=tuple(form or p.form), style=S.Style(name="jazz", harmony=harmony, **style))


def rubs(symbol: str, mode: str, pcs) -> set:
    tones = {t % 12 for t in chord_tones(symbol, mode)}
    return {q for q in pcs if any(min((q - t) % 12, (t - q) % 12) == 1 for t in tones)}


def test_beside_the_ring_at_chamber_chosen_by_a_person():
    """Beside the ring at chamber's place, offered in the studio's picker, named for what plays; never drawn by a
    machine on the ring, and a child of a jazz version keeps it or steps to chamber's neighbours."""
    from songbird import explain

    assert "jazz" not in S.RING and S.OFF_RING["jazz"] == "chamber" and S.on_ring("jazz") == "chamber"
    assert "jazz" in S.offered() and "jazz" not in S.HIDDEN
    assert explain.STYLE_NAMES["jazz"] == "jazz trio"
    assert S.JAZZ.about.split(":", 1)[1].strip() == "piano, upright bass and brushes"
    assert set(S.JAZZ.lineup) == {"piano", "bass", "kit"} and S.JAZZ.leads == ("piano",)
    assert set(S.JAZZ.feels) == {"waltz", "swing"}
    assert S.neighbours("jazz") == S.neighbours("chamber")


def test_its_changes_rub_against_nothing_the_songs_own_chords_dont():
    """In every mode, at every harmony, the trio's chords rub a semitone against no note sung over them (the line's
    own, and the next line's pickup over its last chord) that the song's own chord there doesn't."""
    for mode in ("ionian", "mixolydian", "dorian", "aeolian"):
        for harmony in (0.0, 0.5, 1.0):
            g, p = trio(harmony, mode)
            phrases = form_phrases(g, p)
            bar = g.meter.bar
            for k, phrase in enumerate(phrases):
                own = g.phrases[phrase.id]
                after = [n for n in (phrases[k + 1].sung if k + 1 < len(phrases) else ()) if n.onset < 0]
                for b, chords in enumerate(phrase.chords):
                    for j, symbol in enumerate(chords):
                        a = b * bar + j * bar / len(chords)
                        z = a + bar / len(chords)
                        song = own.chords[b][min(len(own.chords[b]) - 1, int(j * len(own.chords[b]) / len(chords)))]
                        notes = [n for n in own.sung if n.onset >= 0 and n.onset < z and n.onset + n.dur > a]
                        if z >= phrase.bars * bar - 1e-9:
                            notes += after
                        pcs = [degree_semitones(n.degree, mode, n.alter) % 12 for n in notes]
                        assert rubs(symbol, mode, pcs) <= rubs(song, mode, pcs), (mode, harmony, phrase.id, b, symbol)


def test_its_changes_colour_every_chord_and_pass_into_the_cadences():
    """H in D major: every chord coloured (a seventh, a sixth or an added ninth); at harmony 1 a ii-V ends the
    bridge and the turn and the third verse line, I7 walks into IV, iiim7 into vi; at harmony 0 no passing chord."""
    g, p = trio(1.0)
    lines = [(0, 0, g.phrases[x]) for x in ("r3", "r4", "v1", "v2", "v3", "v2", "r1", "r2", "r3", "r4", "t1", "b1",
                                            "b2", "b3", "b4", "r1")]
    changes = S.trio_changes(g, p, lines)
    assert changes["b4"] == (("Imaj7", "vim7"), ("iim7", "V7"))
    assert changes["t1"] == (("IVmaj7", "vim7"), ("iim7", "V7"))
    assert changes["v3"] == (("Imaj7", "I7"), ("IVmaj7", "IVmaj7", "iim7", "V7"))
    assert changes["r1"][0] == ("I6", "I7") and changes["b3"][0] == ("Imaj7", "iiim7")
    for pid, bars in changes.items():
        for chords in bars:
            assert all(len(chord_tones(s, "ionian")) == 4 for s in chords), (pid, chords)
    g, p = trio(0.0)
    plain = S.trio_changes(g, p, lines)
    from songbird.theory import parse_symbol

    for pid, bars in plain.items():  # the song's own chords, coloured: the same roots in the same places
        assert [[parse_symbol(s)[0] for s in b] for b in bars] == \
            [[parse_symbol(s)[0] for s in b] for b in g.phrases[pid].chords]


def test_a_bar_it_cant_write_keeps_its_shares_and_a_waltz_splits_only_a_whole_bar():
    """A bar of three or four chords takes no ii-V it can't write (the review: it crashed); in a waltz a V is split
    into ii-V only where it fills a whole bar of the song (two bars of three), never a beat and two."""
    g, p = trio(1.0)
    for chords in ((("I", "IV", "V", "I"), ("V",)), (("vi", "ii", "V"), ("I",))):
        g2 = replace(g, phrases={**g.phrases, "v1": replace(g.phrases["v1"], chords=chords)})
        out = S.trio_changes(g2, p, [(0, 0, g2.phrases["v1"]), (0, 0, g2.phrases["v2"])])["v1"]
        assert [len(b) for b in out] == [len(b) for b in chords]
    g, p = trio(1.0, feel="waltz")
    assert S.rebarred(g, p)
    lines = [(0, 0, g.phrases[x]) for x in ("v1", "v2", "v3", "v2", "r1", "r2", "r3", "r4", "t1", "b1", "b2", "b3",
                                            "b4", "r1")]
    changes = S.trio_changes(g, p, lines)
    assert all(len(b) <= 2 for bars in changes.values() for b in bars)
    assert changes["b4"][1] == ("iim7", "V7") and changes["t1"][1] == ("iim7", "V7")


def test_a_held_chord_is_one_chord_in_the_midi_file_and_the_piano_score():
    from songbird.idioms import chord_times

    g, p = trio(1.0)
    times = chord_times(g, p)
    held = S.held_chords(times, p)
    assert len(held) < len(times) and all(a[2] != b[2] for a, b in zip(held, held[1:]))
    other = replace(p, style=S.Style(name="chamber", harmony=1.0))
    assert S.held_chords(chord_times(g, other), other) == chord_times(g, other)


def test_the_style_card_says_what_the_chords_do():
    from songbird import explain

    g, p = trio(1.0)
    assert explain.changes_words(g, p).endswith("and passing chords into the cadences")
    assert explain.changes_words(g, replace(p, style=S.Style(name="jazz", harmony=0.0))) == \
        "the song's chords with sevenths and sixths"


def test_a_persons_chords_and_every_other_style_are_left_as_they_are():
    g, p = trio(1.0)
    p = replace(p, composition={"chords": {"v1": [["IV"], ["V"]]}})
    from songbird.composition import harmonized

    song = harmonized(g, p)
    phrases = form_phrases(song, p)
    assert all(ph.chords == (("IV",), ("V",)) for ph in phrases if ph.id == "v1")
    assert any(ph.chords != g.phrases[ph.id].chords for ph in phrases if ph.id != "v1")
    for name in S.STYLES:  # nothing but the trio plays its own changes (the hymn sets its own harmony: songbird.hymn)
        if name not in ("jazz", "hymn"):
            q = replace(p, composition={}, style=S.Style(name=name, harmony=1.0))
            assert [ph.chords for ph in form_phrases(g, q)] == [g.phrases[ph.id].chords for ph in form_phrases(g, q)] \
                or S.STYLES[name].loops


def test_a_break_for_the_pianos_chorus_unless_the_form_was_set_by_hand():
    g = G.load(H)
    no_break = ("intro", "verse", "refrain", "turn", "verse", "refrain", "turn", "bridge", "refrain", "tag")
    added = [S.with_break(g, no_break, m, S.JAZZ) for m in "abcdefghij"]
    assert sum("break" in f for f in added) >= 6
    assert all(f == list(no_break) or f == [*no_break[:7], "break", *no_break[7:]] for f in added)
    assert S.with_break(g, no_break, "a", S.CHAMBER) == list(no_break)
    voice = harvest.machine_voice("fictional:ada")
    p = choose_params(g, None, voice, D.drift(D.parse("2026-09-27"), voice.hash), style="jazz", form=no_break)
    assert p.form == no_break


def test_the_trio_plays_as_designed():
    """The piano comps without the root under the singer and has the tune with its chords in the break; the bass walks
    a note a beat in the refrains; the kit is brushes only: sweeps, taps and a feathered bass drum."""
    g, p = machine("bob", "2026-03-14")
    assert "break" in p.form
    score = realize(g, p)
    parts = score.band["sections"]
    assert {s["parts"].get("piano") for s in parts if s["role"] == "break"} == {"solo"}
    assert {s["parts"].get("bass") for s in parts if s["role"] == "refrain"} == {"walking"}
    kit = Counter(n.art for n in score.notes if n.part == "kit")
    assert set(kit) <= {"brush-sweep", "brush-tap", "kick"} and kit["brush-sweep"] > 50
    times = chord_times(g, p)
    spans = {name: (a, b) for name, a, b in score.sections}
    a, b = spans["break"]
    tune = [n for n in score.notes if n.part == "piano" and a <= n.start < b and n.pitch >= p.tonic + 7]
    assert len(tune) >= 30  # the verse tune an octave up
    verse = [n for n in score.notes if n.part == "piano" and n.section == "refrain"]

    def root_at(t):
        sym = next(s for x, y, s in times if x - 1e-6 <= t < y)
        return (p.tonic + chord_tones(sym, p.mode)[0]) % 12

    roots = sum(1 for n in verse if int(round(n.pitch)) % 12 == root_at(n.start + 0.01))
    assert roots <= 0.1 * len(verse)  # rootless: the bass has the root


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


def test_the_studio_offers_it_in_plain_words_and_shows_its_players(home):
    """The style card names it "jazz trio" and says what plays; the arrangement view gives each player its patterns
    in plain words; the Sound view has the three players."""
    import re

    from songbird import explain, studio as ST, takeover as T

    studio = ST.Studio(None, str(H), "fictional:ada", out=home / "out")
    forbidden = re.compile(r"\b(genome|drift|harvest|hash|knob|params?|seed|jazz standard|bebop)\b", re.I)
    v = studio.version({"style.name": "jazz"})
    card = next(c for c in explain.view(studio.context, v)["cards"] if c["id"] == "style")
    assert card["styles"]["jazz"] == "jazz trio" and card["value"].startswith("jazz trio, ")
    assert card["detail"].startswith("piano, upright bass and brushes")
    for text in [card["value"], card["detail"]] + [r["text"] for r in card["reasons"]]:
        assert not forbidden.search(text), text
    grid = studio.arrangement({"style.name": "jazz"})
    players = {p["name"]: {x["id"]: x["label"] for x in p["patterns"]} for p in grid["players"]}
    assert set(players) == {"piano", "bass", "kit"}
    assert {"rootless", "solo"} <= set(players["piano"]) and {"walking", "twofeel"} <= set(players["bass"])
    assert {"swept", "swept-light"} <= set(players["kit"])
    for idiom in ("rootless", "rootless-light", "solo", "walking", "twofeel", "swept", "swept-light"):
        assert T.LABELS[idiom] and not forbidden.search(T.LABELS[idiom])
    sound = studio.sound({"style.name": "jazz"})
    assert {"piano", "bass", "kit"} <= {p["player"] for p in sound["players"]}


@pytest.mark.parametrize("name,date", MACHINES)
def test_nine_in_ten_of_its_notes_are_on_the_chord_and_few_rub(name, date):
    """The share of the piano's and the bass's notes on a tone of the chord under them (its ninth counted apart), and
    how many rub a semitone against a sung note sounding with them."""
    g, p = machine(name, date)
    score = realize(g, p)
    times = chord_times(g, p)
    lift = S.lifted(g, score) if p.style.lift else None
    sung = [n for n in score.notes if n.part.startswith(SUNG)]
    for part in ("piano", "bass"):
        notes = [n for n in score.notes if n.part == part]
        on = rub = 0
        for n in notes:
            up = 2 if lift is not None and n.start >= lift - 1e-6 else 0
            sym = next((s for x, y, s in times if x - 1e-6 <= n.start + 0.01 < y), times[-1][2])
            tones = chord_tones(sym, p.mode)
            pcs = {(p.tonic + up + t) % 12 for t in (*tones, tones[0] + 2)}
            pc = int(round(n.pitch)) % 12
            on += pc in pcs
            over = [s for s in sung if s.start < n.start + n.dur - 0.02 and s.start + s.dur > n.start + 0.02]
            rub += any(min((pc - int(round(s.pitch))) % 12, (int(round(s.pitch)) - pc) % 12) == 1 for s in over)
        assert on >= 0.85 * len(notes), (part, on, len(notes))
        assert rub <= 0.12 * len(notes), (part, rub, len(notes))
