"""Checks the video's data against its sources, then prints a one-screen summary with sizes.

    uv run python tools/promo/video/prep/verify.py

timeline.json and score.json against renders/promo/capture-live-A/render.score.json (notes per part, sections, the
whistle's four Daisy Bell notes); the lyric lines against render.txt; packet.json against the release file on disk;
that nothing in prep reads under renders/measured/."""
from __future__ import annotations

import collections
import math
import io
import json
import re
import zipfile
from pathlib import Path

import common

failed = []


def check(ok: bool, what: str) -> None:
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        failed.append(what)


def main() -> None:
    import soundfile as sf

    cap = common.capture_score()
    tl = common.read_json(common.DATA / "timeline.json")
    sc = common.read_json(common.DATA / "score.json")

    # sections
    ids = [s["id"] for s in tl["sections"]]
    check(ids == common.SECTION_IDS + ["ring"], "section ids in order, ring last")
    check(all(abs(s["t0"] - a) < 1e-4 and abs(s["t1"] - b) < 1e-4 and s["kind"] == n
              for s, (n, a, b) in zip(tl["sections"], cap["sections"])), "section times equal render.score.json's")
    info = sf.info(str(common.guard(common.RELEASE)))
    check(abs(info.duration - tl["duration"]) < 5e-4 and tl["sections"][-1]["t1"] == tl["duration"],
          f"duration {tl['duration']} is the release file's ({info.duration:.4f} s)")
    check(tl["frames"] == math.ceil(info.duration * 60), f"{tl['frames']:,} frames at 60")

    # notes per part
    counts = collections.Counter(n["part"] for n in cap["notes"])
    mine = {p: len(v) for p, v in sc["parts"].items()}
    check(all(mine.get(p) == c for p, c in counts.items()), f"notes per part equal render.score.json's ({dict(counts)})")
    check(sum(counts.values()) == len(cap["notes"]), f"{len(cap['notes'])} notes in render.score.json")
    check(sc["stems"] == tl["stems"] and set(sc["parts"]) == set(sc["stems"]), f"{len(sc['stems'])} stems named alike")
    own = [n for n in cap["notes"] if n["part"] not in ("voice",)]
    by_part = collections.defaultdict(list)
    for n in own:
        by_part[n["part"]].append((round(n["start"], 4), n["pitch"]))
    check(all(sorted(by_part[p]) == sorted((x["t"], x["p"]) for x in sc["parts"][p]) for p in by_part),
          "every player's and choir's note equal (start, pitch)")
    sung = sorted((round(n["start"], 4), n["pitch"], n["syllable"].replace("*", "")) for n in cap["notes"]
                  if n["part"] == "voice")
    heard = sorted((x["t"], x["p"], x["syl"]) for x in sc["parts"]["voice"])
    same = sum(a == b for a, b in zip(sung, heard))
    check([s[1:] for s in sung] == [h[1:] for h in heard],
          f"the heard lead sings the score's pitches and syllables ({same} of {len(sung)} at the score's own times: "
          f"the rest are the less phrased takes)")

    # the daisy
    whistle = [n for n in cap["notes"] if n["part"] == "whistle" and n["section"] == "bridge"]
    check([int(n["pitch"]) for n in whistle] == [d["pitch"] for d in tl["daisy"]] == [tl["tonic"] + k for k in (31, 28, 24, 19)]
          and all(abs(n["start"] - d["t"]) < 1e-4 for n, d in zip(whistle, tl["daisy"])),
          "the whistle's four bridge notes: " + ", ".join(f"{d['pitch']} {d['degree']} {d['t']}" for d in tl["daisy"]))

    # the lyric
    txt = [ln for ln in common.read_text(common.CAPTURE / "render.txt").splitlines()[2:] if ln.strip()]
    check([ln["text"] for ln in tl["lines"]] == txt, f"{len(tl['lines'])} lines equal render.txt's")
    check(all(" ".join(w["text"] for w in ln["words"]) == ln["text"] for ln in tl["lines"]), "words make each line")
    check([h for _, h in tl["human"]] == [0.0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75], "human steps 0 .2 .3 .4 .5 .6 .7 .75")
    tag = next(x for x in tl["sections"] if x["id"] == "tag")
    check(tl["bars"][0] == tl["sections"][0]["t0"] and tl["bars"][-1] == tag["t1"],
          f"{len(tl['bars'])} bar lines from {tl['bars'][0]} to the tag's end (ritardando in the tag)")

    # the packet
    pk = common.read_json(common.DATA / "packet.json")
    raw = common.read_bytes(common.RELEASE)
    from songbird import pack
    z = zipfile.ZipFile(io.BytesIO(raw))
    check(pk["bytes"] == len(raw), f"file size {len(raw):,}")
    check(pk["zip"]["offset"] == pack.packet_start(str(common.guard(common.RELEASE))) == pk["flac"]["audio"]["end"],
          f"zip at {pk['zip']['offset']:,} (pack.packet_start)")
    check(pk["zip"]["entries_count"] == len(z.infolist()), f"{len(z.infolist())} zip entries")
    check(common.read_json(common.RELEASE.with_suffix(".json"))["id"].startswith(pk["manifest"]["id"][:12]), f"manifest id {pk['manifest']['id'][:12]}")
    pb = common.read_json(common.DATA / "packet-bytes.json")
    data = common.read_bytes(common.DATA / "packet-bytes.bin")
    check(all(data[i * 4096:(i + 1) * 4096] == raw[row["offset"]: row["offset"] + 4096] for i, row in enumerate(pb["rows"])),
          "packet-bytes.bin is the file's own bytes")

    # throat
    tk = common.read_json(common.DATA / "throat/takes.json")
    check(len(tk["calls"]) == 11 and sorted(c["id"] for c in tk["calls"] if c["kind"] == "lead")
          == [f"lead-{h:.2f}" for h in (0, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75)], "11 calls: 8 lead takes, 3 choir")

    # renders/measured/
    try:
        common.guard(common.ROOT / "renders/measured/x")
        refused = False
    except PermissionError:
        refused = True
    check(refused, "guard() refuses renders/measured/")
    here = Path(__file__).resolve().parent
    named = [p.name for p in here.glob("*.py") if p.name != "common.py" and p.name != "verify.py"
             and re.search(r"[\"'/]measured[/\"']", p.read_text(encoding="utf-8"))]
    check(not named, f"no prep script but common.py writes a measured/ path {named or ''}")
    files = [p for p in common.DATA.rglob("*") if p.is_file()]
    check(all(common.guard(p) for p in files) and not any(p.is_symlink() for p in files),
          "every data file resolves outside renders/measured/")

    # summary
    print()
    sizes = collections.defaultdict(int)
    for p in files:
        top = p.relative_to(common.DATA).parts[0]
        sizes[top if "/" not in str(p.relative_to(common.DATA)) and p.parent == common.DATA else top + "/"] += p.stat().st_size
    for k in sorted(sizes):
        print(f"  {k:28s} {sizes[k] / 1e6:8.2f} MB")
    print(f"  {'total':28s} {sum(sizes.values()) / 1e6:8.2f} MB in {len(files)} files")
    print(f"  {len(sc['stems'])} parts: {' '.join(sc['stems'])}")
    print(f"  {len(tl['lines'])} lines, {len(tl['bars'])} bars, {len(tl['beats'])} beats, {len(tl['entries'])} entries")
    print("\n" + ("all checks pass" if not failed else f"{len(failed)} FAILED"))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
