"""The collation: for each chunk of the synced cut, the half-line as the heard version sings it and as every one
of its ancestors sang the same notes, the release first. Writes renders/promo/social/synced/collation.json.

Per chunk, rows from the release (generation 0) down to the heard version, each with its syllables (text,
pitch as that version sang it, the ornament it sings there), marked where they entered the line: a word that
differs from its parent row's word, an ornament its parent did not sing. A row's `voice` is when that ancestor
sings in the heard version's choir: choir voice k is the ancestor k generations back (songbird/synth: the
parent first, cli.choir_of), its notes already on the cut's clock in picture.json. A version whose choir is
matched to voices by range (a cappella) has no row lit, since which voice is whose is not one to one.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))
import synced  # noqa: E402

S = ROOT / "renders/promo/social"
OUT = S / "synced"


def plain(s):
    return "".join(c for c in (s or "") if c.isalpha() or c == "'").lower()


def notes(sc, name, occ):
    """The section's notes, as synced.notes; a last refrain that sings its last line twice gives its first time."""
    try:
        return synced.notes(sc, name, occ)
    except AssertionError:
        _, a, b = synced.section(sc, name, occ)
        ns = [n for n in sc["notes"] if n["part"] == "voice" and n["section"] == name and a - 2.0 <= n["start"] < b]
        assert name == "refrain" and len(ns) == 51 and [n["syllable"] for n in ns[29:40]] == [n["syllable"] for n in ns[40:]], len(ns)
        return ns[:40]


def ancestry(path):
    """The versions from the release down to this one."""
    if path == "versions/release":
        return ["versions/release"]
    if path.startswith("lineages/"):
        _, chain, gen = path.split("/")
        n = int(gen[3:])
        return ["versions/release"] + [f"lineages/{chain}/gen{g}" for g in range(1, n + 1)]
    return ["versions/release", path]


def word_spans(ns):
    """Each note's word: (first index, last index) of the run of notes singing it."""
    spans = [None] * len(ns)
    i = 0
    while i < len(ns):
        j = i
        while synced_cont(ns, j):
            j += 1
        for k in range(i, j + 1):
            spans[k] = (i, j)
        i = j + 1
    return spans


def synced_cont(ns, k):
    n = ns[k]
    if k + 1 >= len(ns) or n["word_len"] < 2 or ns[k + 1]["word"] != n["word"]:
        return False
    run, j = 0, k
    while j > 0 and ns[j - 1]["word"] == n["word"] and run < n["word_len"] - 1:
        j -= 1
        run += 1
    return run < n["word_len"] - 1


def main():
    pic = json.loads((OUT / "picture.json").read_text())
    scores = {}

    def score(p):
        if p not in scores:
            scores[p] = (json.loads((S / f"{p}.score.json").read_text()), json.loads((S / f"{p}.json").read_text()))
        return scores[p]

    out = []
    for c in pic["chunks"]:
        i0, i1 = c["i0"], c["i1"]
        chain = ancestry(c["version"])
        heard_score, heard_rec = score(c["version"])
        by_voices = (heard_score["band"] or {}).get("parts") == "voices"
        rows, prev = [], None
        for depth, p in enumerate(chain):
            sc, rec = score(p)
            ns = notes(sc, c["section"], c["occ"])
            spans = word_spans(ns)
            syl = []
            for i in range(i0, i1):
                n = ns[i]
                a, b = spans[i]
                word = " ".join(plain(ns[k]["syllable"]) for k in range(a, b + 1))
                entered = prev is not None and word != prev["words"][i]
                orn = n.get("ornament")
                orn_entered = bool(orn) and (prev is None or not prev["orn"][i])
                syl.append({"i": i, "text": n["syllable"], "p": n["pitch"], "cont": synced_cont(ns, i),
                            "entered": entered, "orn": orn, "orn_entered": orn_entered})
            words = {}
            for i in range(len(ns)):
                a, b = spans[i]
                words[i] = " ".join(plain(ns[k]["syllable"]) for k in range(a, b + 1))
            row = {"path": p, "gen": rec.get("generation", 0) if p != "versions/release" else 0,
                   "style": (rec["params"].get("style") or {}).get("name") or "ballad",
                   "tonic": rec["params"]["tonic"], "mode": rec["params"]["mode"], "syl": syl,
                   "words": words, "orn": {i: ns[i].get("ornament") for i in range(len(ns))}}
            rows.append(row)
            prev = row
        # when each ancestor sings in the heard version's choir
        n_anc = len(chain) - 1
        for depth, row in enumerate(rows[:-1]):
            k = n_anc - depth   # generations back from the heard version
            row["voice"] = [] if by_voices else [[t0, t1] for (v, t0, t1, _) in c["choir"] if v == k]
        rows[-1]["voice"] = None
        for row in rows:
            del row["words"], row["orn"]
        out.append({"version": c["version"], "section": c["section"], "t0": c["t0"], "t1": c["t1"],
                    "sung": c["sung"], "rows": rows})
        lit = sum(1 for r in rows[:-1] if r["voice"])
        marks = [(r["gen"], s["text"]) for r in rows for s in r["syl"] if s["entered"] or s["orn_entered"]]
        print(f"{c['t0']:6.2f} {c['version']:20} rows {len(rows)} singing {lit}  entered {marks}")
    data = {"duration": pic["duration"], "chunks": out, "copy": pic["copy"]}
    (OUT / "collation.json").write_text(json.dumps(data, ensure_ascii=False))


if __name__ == "__main__":
    main()
