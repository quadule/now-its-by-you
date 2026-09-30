"""Each instrument's share of a whole render's peak memory (songbird/public.py, RATES; docs/WEB-STUDIO.md, "A whole
song's memory").

    SONGBIRD_THREADS=2 MallocLargeCache=0 uv run python tools/part_memory.py accordion cajon      # or none: all

H's seed laid out (the ballad, 151 s), one of its band's parts played by the instrument instead (a drum's strokes for
a percussion instrument, the whistle's line for any other), the mix made as the studio makes it (synth.render),
each in a fresh process, since freed memory isn't always handed back; prints the peak resident memory and the
rate it gives, (peak - public.BASE_MB) / the song's seconds, which is what public.RATES holds for the part."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

PERCUSSION = {"cajon", "shaker", "tambourine", "claps", "stomps", "kit", "drummachine", "drums-808", "drums-909",
              "chip-drums", "drum"}


def one(name: str) -> None:
    from render_memory import resident

    from songbird import genome, synth, variation
    from songbird.realize import choose_params, realize
    from songbird.synth.mixing import MixParams

    g = genome.load(ROOT / "songs" / "h-now-its-by-you.json")
    params = choose_params(g)
    score = variation.lay(realize(g, params), params)
    instead = "drum" if name in PERCUSSION else "whistle"
    notes = tuple(replace(n, part=name) if n.part == instead else n for n in score.notes)
    score = replace(score, notes=notes)
    peak = [0]

    def sample() -> None:
        while True:
            peak[0] = max(peak[0], resident())
            time.sleep(0.003)

    threading.Thread(target=sample, daemon=True).start()
    began = time.perf_counter()
    synth.render(score, seed=params.seed, mix_params=MixParams.from_dict(params.mix or {}))
    took = time.perf_counter() - began
    time.sleep(0.02)
    rate = (peak[0] / 1e6 - 300) / score.duration
    print(f"{name:18s} for {instead:8s} {score.duration:6.1f} s  {took:5.1f} s  peak {peak[0] / 1e9:.2f} GB  "
          f"rate {rate:.1f} MB/s", flush=True)


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        return one(sys.argv[2])
    from songbird.synth.instruments import known

    names = sys.argv[1:] or [n for n in known()]
    for name in names:
        subprocess.run([sys.executable, __file__, "--one", name], check=False, env=os.environ)


if __name__ == "__main__":
    main()
