"""Renders candidate lineages: each a chain of six generations from the release, every step on a different
made-up machine (songbird harvest --fictional), at dates a few weeks apart. Writes renders/promo/social/lineages/
<chain>/gen<N>.{flac,json,score.json} and plan.json (which machine and date made each)."""

import json
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "renders/promo/social/lineages"
RELEASE = ROOT / "renders/release/now-its-by-you.flac"
POOL = "ada bo cleo dev eli fern gus hana ivo juno kai lena milo nora otto pia quin rosa sami theo uma vik wren xia yuri zoe".split()
CHAINS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
GENS = 6


def chain(k):
    rng = random.Random(1000 + k)
    d = date(2026, 11, 29)
    machines = []
    for _ in range(GENS):
        machines.append(rng.choice([m for m in POOL if m not in machines[-2:]]))
    folder = OUT / f"c{k:02d}"
    folder.mkdir(parents=True, exist_ok=True)
    steps, parent = [], RELEASE
    for g, m in enumerate(machines, 1):
        out = folder / f"gen{g}.flac"
        if not out.exists():
            subprocess.run(["uv", "run", "songbird", "render", "songs/h-now-its-by-you.json", "--parent", str(parent),
                            "--machine", f"fictional:{m}", "--date", d.isoformat(), "--out", str(out)],
                           cwd=ROOT, check=True, capture_output=True)
        steps.append({"gen": g, "machine": m, "date": d.isoformat()})
        parent = out
        d += timedelta(weeks=rng.randint(3, 8))
    (folder / "plan.json").write_text(json.dumps(steps, indent=1))
    return k


with ThreadPoolExecutor(3) as ex:
    for k in ex.map(chain, range(CHAINS)):
        print("chain", k, "done", flush=True)
