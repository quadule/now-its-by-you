"""Direct composition edits remain singable, deterministic and portable."""

import copy
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from songbird import composition as C, drift as D, edits as E, explain, harvest as H, pack
from songbird.genome import load
from songbird.realize import Params, choose_params, realize
from songbird.synth import master

ROOT = Path(__file__).resolve().parents[1]
SONG = ROOT / "songs/h-now-its-by-you.json"
G = load(SONG)
ADA = H.fictional("ada")
DAY = D.drift(D.parse("2026-09-27"), ADA.hash)


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


def test_composition_view_covers_every_section_phrase_and_syllable():
    ctx = explain.Context(G, None, None, ADA, "fictional:ada", "2026-09-27", D.parse("2026-09-27"))
    v = ctx.version({"tune.v1": editable()})
    data = explain.view(ctx, v)["composition"]
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
                                        "lyrics.verse:0.0": "I keep the light and sing it through the dark night."})
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
                           if i.filename.startswith("program/songbird/studio/") or i.filename.endswith("composition.py"))
        assert editor_bytes < 100_000
    assert len(json.dumps(params.composition)) < 4096
    opened = Studio(str(flac), machine="none", home=tmp_path / "home")
    try:
        assert opened.where == "packet"
        assert opened.version({}).params.composition == params.composition
        assert opened.song({})["composition"]["edited_phrases"] == ["v1"]
        verse = next(s for s in opened.song({})["composition"]["sections"] if s["id"] == "verse:0")
        assert verse["phrases"][0]["lyric_text"] == "I keep the light and sing it through the dark night."
    finally:
        opened.close()


AUTHORED = "I keep the light and sing it through the dark night."
AUTHORED_PATH = "lyrics.verse:0.0"


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
    assert child.composition["lyrics"] == {"verse:0": {"0": AUTHORED}}
    from songbird.cli import words

    score = realize(G, child, lyrics=words(G, child, sung_by_a_machine=True))
    assert [n.syllable for n in score.part("voice") if n.phrase == "v1"][:11] == AUTHORED.split()
    assert child.form[0] == "refrain"
    released = choose_params(G, child, overrides={AUTHORED_PATH: None})
    assert "lyrics" not in released.composition
    assert "lyrics" in child.composition


@pytest.mark.parametrize("path,text,why", [
    (AUTHORED_PATH, "too few", "11 syllables"),
    (AUTHORED_PATH, " ", "1 to 500"),
    (AUTHORED_PATH, "x" * 501, "1 to 500"),
    (AUTHORED_PATH, "zzqx keep the light and sing it through the dark night.", "pronounce"),
    (AUTHORED_PATH, "I keep the light and sing it through the dark {night}.", "punctuation"),
    (AUTHORED_PATH, "I keep the light and sing it through the dark ni-ght.", "11 syllables"),
    (AUTHORED_PATH, "I--keep the light and sing it through the dark night.", "inside words"),
    (AUTHORED_PATH, 42, "1 to 500"),
    ("lyrics.intro:0.0", AUTHORED, "instrumental"),
    ("lyrics.verse:0.100", AUTHORED, "no such lyric line"),
    ("lyrics.verse:999.0", AUTHORED, "no such lyric line"),
    ("lyrics.unknown:0.0", AUTHORED, "no section"),
])
def test_invalid_authored_lyrics_are_rejected_without_changing_the_line(path, text, why):
    clean, problems = E.check(G, {path: text})
    assert not clean and why in problems[0]["why"]
    override = E.Overrides(G, {path: text})
    params = choose_params(G, overrides=override)
    assert not params.composition and path not in override.applied


def test_hyphenated_lyrics_keep_whole_words_for_pronunciation_and_editor():
    text = "We car-ry light and sing it through the dark night."
    cleaned, problems = E.check(G, {AUTHORED_PATH: text})
    assert not problems
    ctx = explain.Context(G, None, None, ADA, "fictional:ada", "2026-09-27", D.parse("2026-09-27"))
    version = ctx.version(cleaned)
    view = explain.view(ctx, version)
    section = next(s for s in view["composition"]["sections"] if s["id"] == "verse:0")
    line = section["phrases"][0]
    assert line["lyric_text"] == text and line["lyric_path"] == AUTHORED_PATH
    assert line["syllable_count"] == 11 and line["authored"]
    assert [n["syllable"] for n in line["notes"][:3]] == ["We", "car", "ry"]
    assert line["notes"][1]["word"] == line["notes"][2]["word"] == "car-ry"
    display = next(s for s in view["words"] if s["name"] == "verse")
    assert display["authored"] == [0] and display["lines"][0] == text.replace("car-ry", "carry")


def test_new_lyric_edit_for_an_absent_section_is_reported_and_not_claimed_as_applied():
    path = "lyrics.verse:12.0"
    resolved = E.resolve(G, None, ADA, DAY, {path: AUTHORED})
    assert path not in resolved.applied and path not in resolved.marks
    assert not resolved.params.composition
    assert any(p["path"] == path and "no such section" in p["why"] for p in resolved.problems)
