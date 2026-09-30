"""Direct composition edits remain singable, deterministic and portable."""

import copy
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import bank as B, composition as C, drift as D, edits as E, explain, harvest as H, pack
from songbird.genome import load, syllables
from songbird.bank import unmarked
from songbird.realize import Params, choose_params, realize
from songbird.synth import master

ROOT = Path(__file__).resolve().parents[1]
SONG = ROOT / "songs/h-now-its-by-you.json"
G = load(SONG)
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-27"), ADA.hash)
# Exercise the authoring path with existing song text, without inventing lyrics.
BANK_LINES = {verse["id"]: verse["lines"] for verse in G.source["bank"]["verses"]}
AUTHORED = BANK_LINES["kids"][0]
HYPHENATED = BANK_LINES["lullaby"][0]
AUTHORED_PATH = "lyrics.verse:wire.0"  # wire opens every version of this song


def editable(params=None):
    notes = C.phrase_value(G, params or choose_params(G), "v1")
    notes[1]["degree"] = 2
    notes[1]["duration"] = 0.75
    notes[2]["onset"] = 0.75
    notes[2]["duration"] = 0.75
    return notes


def rearranged(form):
    ids = C.section_ids(form)
    ids.insert(0, ids.pop(ids.index("refrain:0")))
    return ids


def test_empty_composition_does_not_change_old_parameters_or_score():
    params = choose_params(G)
    assert "composition" not in params.to_dict()
    assert Params.from_dict(params.to_dict()) == params
    assert Params.from_dict({**params.to_dict(), "composition": {}}).to_dict() == params.to_dict()
    assert realize(G, params).to_dict() == realize(G, replace(params, composition={})).to_dict()


def test_compound_meter_notes_round_trip_without_false_overlaps():
    song = load(ROOT / "songs/b-coal-from-the-fire.json")
    params = choose_params(song)
    notes = C.phrase_value(song, params, "e")
    clean = C.check_phrase(song, "e", notes)
    compact = C.pack_phrase(song, clean)
    assert [(n[1], n[2]) for n in compact] == [(n.onset, n.dur) for n in song.phrases["e"].sung]


def test_even_rhythm_stays_editable_after_compound_meter_storage():
    song = load(ROOT / "songs/b-coal-from-the-fire.json")
    notes = C.phrase_value(song, choose_params(song), "r1")
    # Actual browser Even rhythm boundaries: nine equal gaps before the
    # cadence's pickup guard, followed by its longer held final syllable.
    final_onset, end = 41 / 12, 4
    attacks = [i * (final_onset / 9) for i in range(9)] + [final_onset, end]
    for i, note in enumerate(notes):
        note.update(onset=attacks[i], duration=attacks[i + 1] - attacks[i])
    params = choose_params(song, overrides={"tune.r1": notes})
    params = Params.from_dict(json.loads(json.dumps(params.to_dict())))
    returned = C.phrase_value(song, params, "r1")
    assert C.check_phrase(song, "r1", returned)
    # A subsequent pitch edit must not reject the already accepted timing.
    returned[0]["degree"] -= 1
    clean, problems = E.check(song, {"tune.r1": returned})
    assert not problems
    replayed = choose_params(song, params, overrides=clean)
    assert C.phrase_value(song, replayed, "r1")[0]["degree"] == returned[0]["degree"]
    for original, stored in zip(notes, returned):
        assert stored["onset"] == pytest.approx(original["onset"], abs=1e-14)
        assert stored["duration"] == pytest.approx(original["duration"], abs=1e-14)


def test_moving_and_resizing_notes_changes_the_sung_score_in_beats():
    base = replace(choose_params(G), humanize=0)
    changed = choose_params(G, base, overrides={"tune.v1": editable(base)})
    original = [n for n in realize(G, base).part("voice") if n.phrase == "v1"]
    edited = [n for n in realize(G, changed).part("voice") if n.phrase == "v1"]
    beat = 60 / base.tempo
    assert edited[1].pitch - original[1].pitch == 2
    assert edited[1].dur == pytest.approx(0.75 * beat)
    assert edited[2].start - original[2].start == pytest.approx(-0.25 * beat)
    assert [n.syllable for n in edited] == [n.syllable for n in original]
    assert all(n.dur > 0 for n in edited)


@pytest.mark.parametrize("change,why", [
    (lambda n: n.pop(), "one for each syllable"),
    (lambda n: n[1].update(degree=float("nan")), "finite"),
    (lambda n: n[1].update(degree=True), "finite"),
    (lambda n: n[1].update(degree=2.5), "range"),
    (lambda n: n[1].update(degree=100), "range"),
    (lambda n: n[0].update(onset=-1), "inside"),
    (lambda n: n[1].update(duration=0.1), "inside"),
    (lambda n: n[1].update(duration=2), "overlap"),
    (lambda n: n[-1].update(degree=3), "home note"),
    (lambda n: n[-1].update(duration=4), "inside"),
    (lambda n: n[-1].update(onset=7.5, duration=0.5), "pickup"),
    (lambda n: n[1].update(extra="unknown"), "each note needs"),
])
def test_invalid_phrases_are_refused_atomically(change, why):
    notes = editable()
    change(notes)
    cleaned, problems = E.check(G, {"tune.v1": notes})
    assert cleaned == {} and why in problems[0]["why"]
    override = E.Overrides(G, {"tune.v1": notes})
    params = choose_params(G, overrides=override)
    assert "tune.v1" not in override.applied and not params.composition


def test_repeated_section_identity_cannot_silently_swap_words():
    ids = C.section_ids(G.seed_params["form"])
    a, b = ids.index("verse:0"), ids.index("verse:1")
    ids[a], ids[b] = ids[b], ids[a]
    clean, problems = E.check(G, {"form.order": ids})
    assert not clean and "story order" in problems[0]["why"]


@pytest.mark.parametrize("order", [[], ["verse:0"], ["unknown:0"], ["verse:0"] * 49, "verse refrain"])
def test_invalid_arrangements_are_refused(order):
    clean, problems = E.check(G, {"form.order": order})
    assert not clean and problems[0]["path"] == "form.order"


def test_reordering_sections_keeps_their_lyrics_and_survives_evolution():
    base = E.resolve(G, None, ADA, DAY, {})
    order = rearranged(base.params.form)
    edited = E.resolve(G, None, ADA, DAY, {"form.order": order, "tune.v1": editable(base.params)})
    assert not edited.problems
    assert edited.params.form[0] == "refrain"
    for block in ("verse", "refrain", "bridge"):
        assert [s.lines for s in edited.lyrics.sections if s.block == block] == [
            s.lines for s in base.lyrics.sections if s.block == block]
    saved = json.loads(json.dumps(edited.params.to_dict()))
    replayed = Params.from_dict(saved)
    assert replayed == edited.params
    child = choose_params(G, replayed, H.fictional("basil"), D.drift(D.parse("2028-04-06"), ADA.hash))
    assert child.form == edited.params.form and child.composition == edited.params.composition
    assert child.generation == replayed.generation + 1
    assert child.seed != replayed.seed
    assert realize(G, replayed, lyrics=edited.lyrics) == realize(G, edited.params, lyrics=edited.lyrics)


def test_provenance_replays_edits_and_reset_releases_inherited_phrase():
    r = E.resolve(G, None, ADA, DAY, {"tune.v1": editable(), "form.order": rearranged(choose_params(G).form)})
    assert not r.problems
    record = {"chosen_by_you": r.marks}
    again = E.resolve(G, None, ADA, DAY, E.from_record(record))
    assert again.params == r.params and again.marks == r.marks
    assert r.marks["tune.v1"]["was"] != r.marks["tune.v1"]["value"]
    inherited = copy.deepcopy(r.params.to_dict())
    reset = choose_params(G, r.params, overrides={"tune.v1": None})
    assert "tune" not in reset.composition
    assert reset.composition["order"] == r.params.composition["order"]
    assert r.params.to_dict() == inherited


def test_releasing_an_inherited_order_returns_to_the_parents_form_or_the_machines_not_the_seeds():
    base = choose_params(G, None, ADA, DAY)
    parent = E.resolve(G, None, ADA, DAY, {"form.order": rearranged(base.form)}).params
    assert parent.form != tuple(G.seed_params["form"])
    # no machine: nothing else is chosen, so the form is the parent's, no longer held as the person's
    kept = choose_params(G, parent, overrides={"form.order": None})
    assert kept.form == parent.form and "order" not in kept.composition
    # a machine: its own choice for this version, as it chooses from a parent with no order
    basil = H.fictional("basil")
    later = D.drift(D.parse("2027-06-01"), basil.hash)
    released = E.resolve(G, parent, basil, later, {"form.order": None})
    own = choose_params(G, replace(parent, composition={}), basil, later)
    assert "form.order" in released.applied and "order" not in released.params.composition
    assert released.params.form == own.form
    # and an order a person set only here goes back to what the machine had chosen
    fresh = E.resolve(G, None, ADA, DAY, {"form.order": None})
    assert fresh.params.form == base.form


@pytest.mark.parametrize("ending", ["", "cold"])
def test_the_view_says_how_long_the_realized_song_lasts(ending):
    params = choose_params(G, None, ADA, DAY)
    params = replace(params, style=replace(params.style, ending=ending))
    from songbird.cli import words

    lyrics = words(G, params, sung_by_a_machine=True)
    score = realize(G, params, lyrics=lyrics)
    view = C.view(G, params, explain.as_sung(G, params, lyrics))
    assert view["duration"] == pytest.approx(score.duration, abs=1e-3)
    assert view["duration"] > view["duration_seconds"]


def test_composition_view_covers_every_section_phrase_and_syllable():
    ctx = explain.Context(G, None, None, ADA, "fictional:ada", "2026-09-27", D.parse("2026-09-27"))
    v = ctx.version({"tune.v1": editable()})
    view = explain.view(ctx, v)
    assert all(card["id"] != "field.composition" for card in view["cards"])  # edited in Arrange and Words, not raw data in Sound
    data = view["composition"]
    assert data["order"] == C.section_ids(v.params.form)
    assert data["edited_phrases"] == ["v1"]
    assert data["grid"] == 0.25 and len(data["scale"]) == 7
    for section in data["sections"]:
        assert section["duration_beats"] == sum(p["duration_beats"] for p in section["phrases"])
        assert section["end_seconds"] > section["start_seconds"]
        for phrase in section["phrases"]:
            assert len(phrase["notes"]) == len(G.phrases[phrase["id"]].sung)
            for n in phrase["notes"]:
                if section["sung"]:
                    assert n["syllable"]
                if phrase["id"] == "v1":
                    assert n["edited"]


def test_composition_and_editor_travel_inside_the_audio(tmp_path):
    from songbird.studio import Studio

    params = choose_params(G, overrides={"tune.v1": editable(), "form.order": rearranged(choose_params(G).form),
                                        AUTHORED_PATH: AUTHORED})
    pcm = np.zeros((100, 2), dtype=np.int16)
    flac = tmp_path / "edited.flac"
    master.write_flac(flac, pcm, 44100)
    before = flac.read_bytes()
    record = {"title": G.title, "params": params.to_dict(), "id": master.pcm_sha256(pcm)}
    pack.pack(flac, record, SONG)
    assert pack.audio_bytes(flac) == before
    restored = Params.from_dict(pack.read_record(flac)["params"])
    assert restored.composition == params.composition
    with zipfile.ZipFile(flac) as archive:
        assert "program/songbird/composition.py" in archive.namelist()
        assert "program/songbird/studio/index.html" in archive.namelist()
        # The editor's assets remain normal package data, with no network dependency.
        assert "program/songbird/studio/studio.js" in archive.namelist()
        editor_bytes = sum(i.compress_size for i in archive.infolist()
                           if (i.filename.startswith("program/songbird/studio/")
                               and not i.filename.startswith("program/songbird/studio/piano/"))
                           or i.filename.endswith("composition.py"))
        assert editor_bytes < 100_000
        # the piano page (docs/PIANO.md) travels with it, a page of its own, counted apart
        piano_bytes = sum(i.compress_size for i in archive.infolist()
                          if i.filename.startswith("program/songbird/studio/piano/"))
        assert 0 < piano_bytes < 30_000
    assert len(json.dumps(params.composition)) < 4096
    opened = Studio(str(flac), machine="none", home=tmp_path / "home")
    try:
        assert opened.where == "packet"
        assert opened.version({}).params.composition == params.composition
        assert opened.song({})["composition"]["edited_phrases"] == ["v1"]
        verse = next(s for s in opened.song({})["composition"]["sections"] if s["lyric_key"] == "verse:wire")
        assert verse["phrases"][0]["lyric_text"] == AUTHORED
    finally:
        opened.close()


def test_authored_lines_overlay_the_score_without_changing_the_banks_words():
    base = E.resolve(G, None, ADA, DAY, {})
    changed = E.resolve(G, None, ADA, DAY, {AUTHORED_PATH: AUTHORED})
    assert not changed.problems and changed.params.words == base.params.words
    assert changed.lyrics == base.lyrics
    score = realize(G, changed.params, lyrics=changed.lyrics)
    verse = [n for n in score.part("voice") if n.phrase == "v1"]
    assert [n.syllable for n in verse[:11]] == AUTHORED.split()
    assert [n.syllable for n in verse[11:22]] != AUTHORED.split()
    assert AUTHORED in pack.words_as_sung(score.to_dict())
    assert changed.marks[AUTHORED_PATH]["value"] == AUTHORED
    assert changed.marks[AUTHORED_PATH]["was"] != AUTHORED
    replay = E.resolve(G, None, ADA, DAY, E.from_record({"chosen_by_you": changed.marks}))
    assert replay.params == changed.params


def test_authored_words_follow_their_section_and_survive_a_child():
    base = choose_params(G, None, ADA, DAY)
    parent = E.resolve(G, None, ADA, DAY, {AUTHORED_PATH: AUTHORED, "form.order": rearranged(base.form)})
    restored = Params.from_dict(json.loads(json.dumps(parent.params.to_dict())))
    child = choose_params(G, restored, H.fictional("basil"), D.drift(D.parse("2029-03-14"), ADA.hash))
    assert child.composition["lines"] == {"verse:wire": {"0": AUTHORED}}
    from songbird.cli import words

    score = realize(G, child, lyrics=words(G, child, sung_by_a_machine=True))
    assert [n.syllable for n in score.part("voice") if n.phrase == "v1"][:11] == AUTHORED.split()
    assert child.form[0] == "refrain"
    released = choose_params(G, child, overrides={AUTHORED_PATH: None})
    assert "lines" not in released.composition
    assert "lines" in child.composition


@pytest.mark.parametrize("path,text,why", [
    (AUTHORED_PATH, " ".join(AUTHORED.split()[:2]), "11 syllables"),
    (AUTHORED_PATH, " ", "1 to 500"),
    (AUTHORED_PATH, "x" * 501, "1 to 500"),
    (AUTHORED_PATH, AUTHORED.replace("They", "zzqx", 1), "pronounce"),
    (AUTHORED_PATH, AUTHORED.replace("fire", "{fire}"), "punctuation"),
    (AUTHORED_PATH, AUTHORED.replace("fire", "fi-re"), "11 syllables"),
    (AUTHORED_PATH, AUTHORED.replace("They sang", "They--sang", 1), "inside words"),
    (AUTHORED_PATH, AUTHORED.replace("fire", "*fire"), "star each side"),
    (AUTHORED_PATH, AUTHORED.replace("fire", "fi*re*"), "star each side"),
    (AUTHORED_PATH, AUTHORED.replace("kids", "**kids**"), "star each side"),
    (AUTHORED_PATH, 42, "1 to 500"),
    ("lyrics.intro:0.0", AUTHORED, "instrumental"),
    ("lyrics.verse:wire.100", AUTHORED, "no such lyric line"),
    ("lyrics.verse:nowhere.0", AUTHORED, "no verse called nowhere"),
    ("lyrics.verse:0.0", AUTHORED, "named for it, not its place"),
    ("lyrics.refrain:999.0", AUTHORED, "no such lyric line"),
    ("lyrics.bridge:last.0", AUTHORED, "no such lyric line"),
    ("lyrics.unknown:0.0", AUTHORED, "no section"),
])
def test_invalid_authored_lyrics_are_rejected_without_changing_the_line(path, text, why):
    clean, problems = E.check(G, {path: text})
    assert not clean and why in problems[0]["why"]
    override = E.Overrides(G, {path: text})
    params = choose_params(G, overrides=override)
    assert not params.composition and path not in override.applied


def test_an_authored_line_is_checked_as_a_bank_line_is():
    marked = AUTHORED.replace("fire", "*fire*")
    assert C.check_lyric(G, AUTHORED_PATH, marked) == marked  # a whole-word mark is the singer's to read
    for line in (AUTHORED, marked, AUTHORED.replace("fire", "*fire"), " ".join(AUTHORED.split()[:2])):
        try:
            B.check_block([line], {}, ["v1"], G.phrases, G.lexicon, "authored")
            bank_says = None
        except ValueError as e:
            bank_says = e
        try:
            C.check_lyric(G, AUTHORED_PATH, line)
            studio_says = None
        except ValueError as e:
            studio_says = e
        assert (bank_says is None) == (studio_says is None), line


def test_hyphenated_lyrics_keep_whole_words_for_pronunciation_and_editor():
    text = HYPHENATED
    cleaned, problems = E.check(G, {AUTHORED_PATH: text})
    assert not problems
    ctx = explain.Context(G, None, None, ADA, "fictional:ada", "2026-09-27", D.parse("2026-09-27"))
    version = ctx.version(cleaned)
    view = explain.view(ctx, version)
    section = next(s for s in view["composition"]["sections"] if s["lyric_key"] == "verse:wire")
    line = section["phrases"][0]
    assert line["lyric_text"] == text and line["lyric_path"] == AUTHORED_PATH
    assert line["syllable_count"] == 11 and line["authored"]
    assert [n["syllable"] for n in line["notes"][:3]] == ["A", "wom", "an"]
    assert line["notes"][1]["word"] == line["notes"][2]["word"] == "wom-an"
    display = next(s for s in view["words"] if s["name"] == "verse")
    assert display["authored"] == [0] and display["lines"][0] == "A woman was singing it low to a child"


def first_refrain_line():
    """The first refrain's first line as this song sings it today (a line of the song's own)."""
    today = E.resolve(G, None, ADA, DAY, {})
    return C.lyric_value(G, today.params, today.lyrics, "lyrics.refrain:0.0")


def sung(score, name, nth):
    """The syllables of the nth section called name in a score (-1: the last), phrase by phrase. Its pickup (the
    first words, sung before its first bar) is its own however slow the tempo: notes named for it from the start of
    the section before, unless that one has the same name (then half a second, as they can't be told apart)."""
    spans = [s for s in score.sections if s[0] == name]
    _, start, end = spans[nth]
    k = score.sections.index(spans[nth])
    before = score.sections[k - 1] if k > 0 else None
    since = before[1] if before is not None and before[0] != name else start - 0.5
    notes = [n for n in score.part("voice") if since <= n.start < end - 0.05 and n.section == name]
    return [n.syllable for n in notes]


def child_of(params, name, date):
    from songbird.cli import words

    machine = H.fictional(name)
    child = choose_params(G, Params.from_dict(json.loads(json.dumps(params.to_dict()))), machine,
                          D.drift(D.parse(date), machine.hash))
    lyrics = words(G, child, sung_by_a_machine=True)
    return child, lyrics, realize(G, child, lyrics=lyrics)


@pytest.mark.parametrize("path,which", [("lyrics.refrain:12.0", "refrain"), ("lyrics.verse:kids.0", "verse")])
def test_new_lyric_edit_for_an_absent_section_is_reported_and_not_claimed_as_applied(path, which):
    text = first_refrain_line() if which == "refrain" else AUTHORED  # kids isn't among today's verses
    resolved = E.resolve(G, None, ADA, DAY, {path: text})
    assert path not in resolved.applied and path not in resolved.marks
    assert not resolved.params.composition
    assert any(p["path"] == path and "doesn't sing that section" in p["why"] for p in resolved.problems)


def test_an_authored_line_stays_with_its_verse_when_a_child_sings_another_there():
    parent = E.resolve(G, None, ADA, DAY, {"lyrics.verse:deaf.0": AUTHORED})
    assert parent.lyrics.verses == ("wire", "misheard", "deaf") and not parent.problems
    assert sung(realize(G, parent.params, lyrics=parent.lyrics), "verse", 2)[:11] == AUTHORED.split()
    child, lyrics, score = child_of(parent.params, "coral", "2029-03-14")
    assert lyrics.verses == ("wire", "misheard", "stroke")  # deaf's place now sings stroke
    assert child.composition["lines"] == {"verse:deaf": {"0": AUTHORED}}  # carried, for a verse not sung
    assert AUTHORED not in pack.words_as_sung(score.to_dict())
    stroke = syllables(next(v["lines"][0] for v in G.source["bank"]["verses"] if v["id"] == "stroke"))
    assert [unmarked(x) for x in sung(score, "verse", 2)[:len(stroke)]] == [unmarked(x) for x in stroke]
    # a verse sung again later brings the line back, wherever it comes
    view = C.view(G, child, lyrics)
    assert [s["lyric_key"] for s in view["sections"] if s["name"] == "verse"] == [
        "verse:wire", "verse:misheard", "verse:stroke"]
    assert not any(p["authored"] for s in view["sections"] for p in s["phrases"])


def test_the_last_refrains_line_follows_it_when_the_count_of_refrains_changes():
    line = first_refrain_line()
    n = len(syllables(line))
    last = E.resolve(G, None, ADA, DAY, {"lyrics.refrain:last.0": line})
    third = E.resolve(G, None, ADA, DAY, {"lyrics.refrain:2.0": line})
    assert not last.problems and not third.problems and last.params.form.count("refrain") == 4
    assert sung(realize(G, last.params, lyrics=last.lyrics), "refrain", -1)[:n] == syllables(line)
    assert sung(realize(G, third.params, lyrics=third.lyrics), "refrain", 2)[:n] == syllables(line)
    child, _, score = child_of(last.params, "coral", "2030-09-01")
    assert child.form.count("refrain") == 3
    assert sung(score, "refrain", -1)[:n] == syllables(line)  # the last refrain, wherever it now comes
    child, _, score = child_of(third.params, "coral", "2030-09-01")
    assert all(sung(score, "refrain", k)[:n] != syllables(line) for k in (1, 2))  # the third is gone, and its line


def test_lines_an_older_record_kept_by_place_are_sung_there_and_handed_down_by_verse():
    today = E.resolve(G, None, ADA, DAY, {})
    old = replace(today.params, composition={"lyrics": {"verse:2": {"0": AUTHORED}}})  # the third verse: deaf
    record = Params.from_dict(json.loads(json.dumps(old.to_dict())))
    assert sung(realize(G, record, lyrics=today.lyrics), "verse", 2)[:11] == AUTHORED.split()
    assert C.handed_down(G, record).composition == {"lines": {"verse:deaf": {"0": AUTHORED}}}
    child, lyrics, score = child_of(record, "coral", "2029-03-14")
    assert child.composition == {"lines": {"verse:deaf": {"0": AUTHORED}}}
    assert AUTHORED not in pack.words_as_sung(score.to_dict())
    same = child_of(record, "fox", "2029-03-14")  # a child still singing deaf third sings the line there
    assert same[1].verses == ("wire", "misheard", "deaf")
    assert sung(same[2], "verse", 2)[:11] == AUTHORED.split()


def test_the_page_gets_each_lines_chords_where_the_band_plays_them():
    """The sketch plays the chords from the view: each where the band lays it (a bar's chords share its beats),
    named in the key, its pitch classes and its bass, following a key or mode chosen."""
    params = Params.from_dict(G.seed_params)
    view = C.view(G, params, None)
    v2 = next(p for s in view["sections"] for p in s["phrases"] if p["id"] == "v2")  # I | V I
    assert [(h["start"], h["beats"], h["name"], h["pcs"], h["bass"]) for h in v2["harmony"]] == [
        (0, 4, "D", [2, 6, 9], 2), (4, 2, "A", [9, 1, 4], 9), (6, 2, "D", [2, 6, 9], 2)]
    minor = C.view(G, replace(params, tonic=57, mode="aeolian"), None)
    r3 = next(p for s in minor["sections"] for p in s["phrases"] if p["id"] == "r3")  # vi IV | I V
    assert [h["name"] for h in r3["harmony"]] == ["F", "Dm", "Am", "Em"]
