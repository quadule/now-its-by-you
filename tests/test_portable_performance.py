"""A contribution keeps travelling after the original takes and files are gone."""

import json
from dataclasses import replace
from pathlib import Path

from songbird import cli, pack, phrasing as P

H = Path(__file__).resolve().parents[1] / "songs/h-now-its-by-you.json"


def test_a_packet_replays_its_lead_choir_singer_and_mix_without_local_files(tmp_path):
    from songbird.genome import load

    genome = load(H)
    gesture = P.Gesture(early=-0.0625, level=1, fall=-20, vibrato=12)
    way = {pid: tuple(gesture for _ in phrase.sung) for pid, phrase in genome.phrases.items()}
    phrasing = tmp_path / "volunteer.json"
    phrasing.write_text(json.dumps(P.to_json(way, source="song", source_detail="3 sung takes by 2 singers")))
    original, replay = tmp_path / "original.flac", tmp_path / "replay.flac"
    assert cli.main(["render", str(H), "--form", "tag", "--out", str(original), "--pack",
                     "--voice", "engine=formant", "tract=1.03", "--mix", "forward=6", "space=0.2",
                     "--phrasing", str(phrasing), "--choir-phrasing", str(phrasing)]) == 0
    record = pack.read_manifest(original)
    assert record["performance"] == {"lead": P.to_json(way), "choir": [P.to_json(way)]}
    assert str(tmp_path) not in json.dumps(record["performance"])
    phrasing.unlink()
    assert cli.main(["render", str(H), "--replay", str(original), "--out", str(replay), "--pack"]) == 0
    again = pack.read_manifest(replay)
    assert again["id"] == record["id"]
    assert again["singer"] == record["singer"] and again["mix"] == record["mix"]
    assert again["performance"] == record["performance"]
    # and says where the performance came from as the record did (the first version's credit line)
    assert record["phrasing"]["source_detail"] == "3 sung takes by 2 singers"
    assert (again["phrasing"], again["choir_phrasings"]) == (record["phrasing"], record["choir_phrasings"])


def test_children_inherit_delivery_and_explicit_contributions_replace_it(tmp_path, monkeypatch):
    from songbird.genome import load
    from songbird.realize import choose_params

    lead = P.to_json({"r1": (P.Gesture(early=0.125),)})
    choir = P.to_json({"r1": (P.Gesture(fall=-30),)})
    parent = {"id": "a" * 64, "params": replace(choose_params(load(H)), choir=3).to_dict(),
              "performance": {"lead": lead, "choir": [choir]}}
    parent_file = tmp_path / "parent.json"
    parent_file.write_text(json.dumps(parent))
    renders = []
    monkeypatch.setattr(cli, "render_one", lambda *a, **kw: renders.append({"params": a[1], **kw}))
    args = ["render", str(H), "--parent", str(parent_file)]
    assert cli.main(args) == 0
    assert renders[-1]["phrasing_json"] == lead and renders[-1]["choir_json"] == [choir]
    assert renders[-1]["params"].choir == 3  # inherited gestures do not pin the evolving choir's size
    replacement = tmp_path / "new.json"
    replacement.write_text(json.dumps(choir))
    assert cli.main([*args, "--phrasing", str(replacement)]) == 0
    assert renders[-1]["phrasing_json"] == choir
    assert cli.main([*args, "--choir-phrasing", str(replacement)]) == 0
    assert renders[-1]["choir_json"] == [choir] and renders[-1]["params"].choir == 1
    assert P.inherited({"seed_phrasing": lead}, {}) == (lead, [])
    assert P.inherited({"seed_phrasing": lead}, {"performance": {"lead": None, "choir": []}}) == (None, [])


def test_studio_previews_recordings_and_cache_keep_the_packets_delivery(tmp_path, monkeypatch):
    from songbird import studio as S
    from songbird.genome import load
    from songbird.realize import choose_params

    lead = P.to_json({"r1": (P.Gesture(early=0.125),)})
    choir = P.to_json({"r1": (P.Gesture(fall=-30),)})
    parent = {"id": "a" * 64, "params": choose_params(load(H)).to_dict(),
              "performance": {"lead": lead, "choir": [choir]}}
    parent_file = tmp_path / "parent.json"
    parent_file.write_text(json.dumps(parent))
    studio = S.Studio(str(parent_file), str(H), "fictional:ada", home=tmp_path, out=tmp_path / "out")
    version = studio.version({})
    assert version.phrasing_json == lead and version.choir_phrasings == [choir]

    realized = []
    original_realize = S.realize

    def inspect_score(*args, **kwargs):
        realized.append(kwargs)
        return original_realize(*args, **kwargs)

    monkeypatch.setattr(S, "realize", inspect_score)
    studio._score(version)
    assert realized[-1]["phrasing"] == P.from_json(lead)
    assert realized[-1]["choir"] == [P.from_json(choir)]
    key = studio.key(version, None)
    studio.context.parent_record["performance"]["choir"] = []
    assert studio.key(version, None) != key
    studio.context.parent_record["performance"]["choir"] = [choir]

    recorded = []

    def inspect_render(genome, params, out, **kwargs):
        recorded.append(kwargs)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"test recording")
        return {"id": "b" * 64, "duration": 1.0}

    monkeypatch.setattr(cli, "render_one", inspect_render)
    job = S.Job("portable", key, "record", "Portable recording", lambda _: None)
    studio._whole(job, version, key)
    assert recorded[-1]["phrasing_json"] == lead and recorded[-1]["choir_json"] == [choir]

    replacement = tmp_path / "replacement.json"
    replacement.write_text(json.dumps(choir))
    changed = studio.context.version({"phrasing": "replacement"}, phrasings={"replacement": str(replacement)})
    assert changed.phrasing_json == choir and changed.choir_phrasings == [choir]
