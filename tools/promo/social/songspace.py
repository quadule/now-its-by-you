"""The songspace: thousands of versions of the song as the program would choose them, no audio rendered.

Lineages from the release: each a chain of generations, every step on a different made-up machine
(harvest.machine_voice("fictional:NAME")) a few weeks after the last, its parameters chosen by the program's own
realize.choose_params from its parent's. With them, the versions rendered for the cut (their records as
written). Writes renders/promo/social/synced/songspace.json: one row per version, columns named in "fields".

  uv run python tools/promo/social/songspace.py [CHAINS=1400] [GENS=6]
"""

import json
import random
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from songbird import drift as D, genome as G, harvest  # noqa: E402
from songbird.cli import _parent, _parent_record, choose_params  # noqa: E402
from songbird.realize import Params  # noqa: E402
from songbird.style import HIDDEN  # noqa: E402

S = ROOT / "renders/promo/social"
OUT = S / "synced"
CHAINS = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
GENS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
MACHINES = 500
BAND = ("lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone", "brightness", "density", "swing", "wear",
        "ornament", "arc", "body")
SINGER = ("tract", "mouth", "tilt", "vibrato_rate", "jitter", "shimmer", "rd", "breath", "vibrato_depth", "glide", "wander",
          "dynamics")
MIX = ("forward", "space", "width", "intimacy", "predelay", "duck", "tilt", "rt60")
MOODS = ("plain", "light", "dark", "tender")


def row(p, path=None, machine=None, t=None):
    """One version's choices as a flat record (p: its params as a dict)."""
    style = p.get("style") or {}
    band = p.get("band") or {}
    singer = p.get("singer") or {}
    mix = p.get("mix") or {}
    lean = p.get("leanings") or {}
    words = p.get("words") or {}
    rounds = (words.get("refrain") or {}).get("rounds") or []
    first = rounds[0] if rounds else {}
    timbre = {}
    for part in str(singer.get("timbre") or "").split(","):
        if ":" in part:
            k, v = part.split(":")
            timbre[k] = float(v)
    return {
        "path": path, "machine": machine, "t": t, "gen": p.get("generation") or 0,
        "tonic": p["tonic"], "mode": p["mode"], "tempo": p["tempo"], "sections": len(p["form"]),
        "style": style.get("name") or "ballad", "feel": style.get("feel") or "straight",
        "band": [band.get(k) for k in BAND], "lead": band.get("lead"), "pattern": band.get("pattern"),
        "singer": [singer.get(k) for k in SINGER], "timbre": timbre,
        "mix": [mix.get(k) for k in MIX],
        "era": lean.get("era_bias", 0.0), "rarity": lean.get("rarity_appetite", 0.0),
        "mood": [(lean.get("mood_weights") or {}).get(k, 1.0) for k in MOODS],
        "verses": [v["id"] for v in words.get("verses") or []],
        "couplet": first.get("id"), "while": (first.get("words") or {}).get("while"),
        "then": (first.get("words") or {}).get("then"),
        "variants": [[v["phrase"], v["note"], v["kind"], v["born"]] for v in p.get("variants") or []],
        "choir": p.get("choir"),
    }


def main():
    genome = G.load(ROOT / "songs/h-now-its-by-you.json")
    release = _parent_record(str(ROOT / "renders/release/now-its-by-you.flac"))
    root_params = _parent(release, genome)
    rows = [dict(row(release["params"], path="versions/release"), parent=-1, gen=0)]
    index = {}

    # the versions rendered for the cut, as their records have them
    def add_record(path, parent_path):
        rec = json.loads((S / f"{path}.json").read_text())
        if (rec["params"].get("style") or {}).get("name") in HIDDEN:
            return
        r = row(rec["params"], path=path)
        r["gen"] = rec["generation"]
        plan = S / Path(path).parent / "plan.json"
        if plan.exists():   # which made-up machine made it
            r["mname"] = json.loads(plan.read_text())[rec["generation"] - 1]["machine"]
        r["parent"] = index.get(parent_path, 0)
        index[path] = len(rows)
        rows.append(r)

    index["versions/release"] = 0
    for f in sorted((S / "versions").glob("*.json")):
        if f.name.endswith(".score.json") or f.stem in ("release",) or f.stem.startswith("gen"):
            continue
        add_record(f"versions/{f.stem}", "versions/release")
    for g in range(1, 7):
        add_record(f"versions/gen{g}", "versions/release" if g == 1 else f"versions/gen{g - 1}")
    for chain in sorted((S / "lineages").glob("c*")):
        for g in range(1, 7):
            add_record(f"lineages/{chain.name}/gen{g}", "versions/release" if g == 1 else f"lineages/{chain.name}/gen{g - 1}")
    heard = len(rows)

    # the lineages the program would make
    voices = [harvest.machine_voice(f"fictional:m{k:03d}") for k in range(MACHINES)]
    t0 = D.parse("2026-11-29")
    dropped = 0
    for c in range(CHAINS):
        rng = random.Random(50000 + c)
        t = t0 + rng.randint(0, 120)
        parent, parent_i, used, chain_rows = root_params, 0, [], []
        ok = True
        for g in range(1, GENS + 1):
            m = rng.choice([k for k in range(MACHINES) if k not in used[-2:]])
            used.append(m)
            p = choose_params(genome, parent, voices[m], D.drift(t, voices[m].hash))
            d = p.to_dict() if hasattr(p, "to_dict") else asdict(p)
            if (d.get("style") or {}).get("name") in HIDDEN:
                ok = False
                break
            r = row(d, machine=m, t=t)
            r["gen"] = g
            r["parent"] = parent_i if g == 1 else len(rows) + len(chain_rows) - 1
            chain_rows.append(r)
            parent, parent_i = p, None
            t += rng.randint(21, 56)
        if ok:
            rows.extend(chain_rows)
        else:
            dropped += 1
        if c % 200 == 0:
            print("chain", c, flush=True)
    (OUT / "songspace.json").write_text(json.dumps({"band": BAND, "singer": SINGER, "mix": MIX, "moods": MOODS,
                                                    "rendered": heard, "rows": rows}, ensure_ascii=False))
    print(len(rows), "versions,", heard, "rendered,", dropped, "chains dropped (a hidden style)")


if __name__ == "__main__":
    main()
