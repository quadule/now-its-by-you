"""What the synced cut's picture draws, from synced/cut.json and the versions' own scores and records. Writes
renders/promo/social/synced/picture.json:

- chunks: each chunk of the cut with every note its version plays near it, on the cut's clock (the same warp
  the audio had): the lead (with its learned ornaments), the choir (the earlier versions' singers), the band.
- lines: the sung lines as heard, syllable by syllable, each marked where its word differs from the release's.
- tree: every version rendered for this (none in a hidden style), with its parent: the release at the root.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
from songbird.style import HIDDEN  # noqa: E402
import synced  # noqa: E402

S = ROOT / "renders/promo/social"
OUT = S / "synced"
PERC = {"kit", "drum", "drummachine", "claps", "stomps", "tambourine"}
RELEASE_ID = "07ac74fbd4eb"   # the release FLAC's own id: every child here names it as parent
LINES = {"refrain": [(0, 8), (8, 18), (18, 29), (29, 40)], "bridge": [(0, 10), (10, 20)]}


def plain(s):
    return "".join(c for c in (s or "") if c.isalpha() or c == "'").lower()


def mapper(m):
    src, dst, local = m["src"], m["dst"], m["local"]

    def f(t):
        if len(src) == 1 or t <= src[0]:
            return dst[0] + (t - src[0]) / local
        if t >= src[-1]:
            return dst[-1] + (t - src[-1]) / local
        for j in range(len(src) - 1):
            if src[j] <= t <= src[j + 1]:
                return dst[j] + (t - src[j]) * (dst[j + 1] - dst[j]) / (src[j + 1] - src[j])
    return f


def cont(ns, k):
    """Whether note k's syllable runs on into the next note's (one word over both)."""
    n = ns[k]
    if k + 1 >= len(ns) or n["word_len"] < 2 or ns[k + 1]["word"] != n["word"]:
        return False
    run, j = 0, k
    while j > 0 and ns[j - 1]["word"] == n["word"] and run < n["word_len"] - 1:
        j -= 1
        run += 1
    return run < n["word_len"] - 1


def main():
    cut = json.loads((OUT / "cut.json").read_text())
    rel = json.loads((S / "versions/release.score.json").read_text())
    chunks = []
    for c in cut["chunks"]:
        score = json.loads((S / f"{c['version']}.score.json").read_text())
        f = mapper(c["map"])
        s0, s1 = c["map"]["s0"] - 4, c["map"]["s1"] + 4
        voice, choir, band = [], [], []
        for n in score["notes"]:
            if n["pitch"] is None or not (s0 < n["start"] < s1):
                continue
            t0 = f(n["start"])
            t1 = f(n["start"] + n["dur"])
            if n["part"] == "voice":
                voice.append([round(t0, 4), round(t1, 4), n["pitch"], n.get("ornament")])
            elif n["part"].startswith("choir"):
                choir.append([int(n["part"][5:]), round(t0, 4), round(t1, 4), n["pitch"]])
            else:
                band.append([n["part"], round(t0, 4), round(t1, 4), n["pitch"], round(n["vel"], 3), n["part"] in PERC])
        c = dict(c, voice=voice, choir=choir, band=band)
        if c["section"] != "lift":
            ns = synced.notes(score, c["section"], c["occ"])
            rs = synced.notes(rel, c["section"], c["occ"])
            for s in c["sung"]:
                i = s["i"]
                s["changed"] = plain(ns[i]["syllable"]) != plain(rs[i]["syllable"])
                s["cont"] = cont(ns, i)
        chunks.append(c)

    # the sung lines as heard: a line of the section, its halves from whichever chunks sang them
    lines = []
    for ci, c in enumerate(chunks):
        if not c["sung"]:
            continue
        lo, hi = next((a, b) for a, b in LINES[c["section"]] if a <= c["i0"] < b)
        key = (c["section"], c["occ"], lo)
        if not lines or lines[-1]["key"] != key:
            lines.append({"key": key, "t0": c["t0"], "syl": [], "chunks": []})
        line = lines[-1]
        row = len(line["chunks"])
        line["chunks"].append(ci)
        for s in c["sung"]:
            line["syl"].append(dict(s, chunk=ci))
        line["t1"] = c["t1"]
    for line in lines:
        line["key"] = list(line["key"])

    # the family: every version rendered for this, the release at the root
    tree = [{"path": "versions/release", "id": RELEASE_ID, "parent": None, "gen": 0, "style": "ballad", "tonic": 62}]
    for rec_path in sorted(list((S / "versions").glob("*.json")) + list((S / "lineages").glob("*/gen*.json"))):
        if rec_path.name.endswith(".score.json") or rec_path.stem == "release":
            continue
        rec = json.loads(rec_path.read_text())
        style = (rec["params"].get("style") or {}).get("name")
        if style in HIDDEN:
            continue
        key = str(rec_path.relative_to(S))[:-5]
        tree.append({"path": key, "id": rec["id"][:12], "parent": (rec.get("parent_id") or "")[:12], "gen": rec["generation"],
                     "style": style, "tonic": rec["params"]["tonic"], "mode": rec["params"]["mode"]})
    ids = {n["id"] for n in tree}
    for n in tree:
        assert n["parent"] is None or n["parent"] in ids, n
    used = {c["version"] for c in chunks}
    for n in tree:
        n["used"] = n["path"] in used

    copy = json.loads((Path(__file__).with_name("copy.json")).read_text())
    data = {"duration": cut["duration"], "tempo": cut["tempo"], "bar": cut["bar"], "chunks": chunks, "lines": lines,
            "tree": tree, "copy": copy}
    (OUT / "picture.json").write_text(json.dumps(data, ensure_ascii=False))
    print(len(chunks), "chunks,", len(lines), "lines,", len(tree), "versions in the tree,", sum(n["used"] for n in tree), "heard")
    for line in lines:
        print(f" {line['t0']:6.2f} {' '.join(s['syl'].replace('*', '') + ('°' if s['changed'] else '') for s in line['syl'])}")


if __name__ == "__main__":
    main()
