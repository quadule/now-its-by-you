"""Where a song's tune takes a round (songbird.canon; docs/ARRANGE.md, "A round"): every way of singing each sung
section as a round, scored by its clash, in each mode asked for, as a Markdown table.

    uv run python tools/round_fit.py songs/h-now-its-by-you.json --modes ionian aeolian
    uv run python tools/round_fit.py songs/*.json --summary
"""

from __future__ import annotations

import argparse

from songbird import canon
from songbird import genome as G


def rows(genome, mode: str):
    for name in genome.sections:
        if not canon.roundable(genome, name):
            continue
        line = genome.phrases[genome.section(name).phrases[0]].bars * genome.meter.bar
        for plan in canon.candidates(genome, name):
            score = canon.clash(genome, name, plan, mode)
            apart = plan.distance / line
            how = ("the whole" if plan.whole else "its last line") + \
                  f", {plan.voices} voices {'a line' if apart == 1 else 'half a line' if apart == 0.5 else f'{apart:g} lines'} apart"
            yield name, how, score, canon.fits(score)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("songs", nargs="+")
    ap.add_argument("--modes", nargs="+", default=None, help="the modes to score in (default: each song's own)")
    ap.add_argument("--summary", action="store_true", help="only what a round chooses in each section")
    args = ap.parse_args()
    for path in args.songs:
        genome = G.load(path)
        modes = args.modes or [genome.seed_params.get("mode", "ionian")]
        print(f"\n## {genome.title}\n")
        if args.summary:
            print("| mode | " + " | ".join(n for n in genome.sections if canon.roundable(genome, n)) + " |")
            print("|---" * (1 + sum(canon.roundable(genome, n) for n in genome.sections)) + "|")
            for mode in modes:
                cells = []
                for name in genome.sections:
                    if not canon.roundable(genome, name):
                        continue
                    plan = canon.choose(genome, name, True, mode)
                    line = genome.phrases[genome.section(name).phrases[0]].bars * genome.meter.bar
                    cells.append("none" if plan is None else
                                 f"{'whole' if plan.whole else 'last line'}, {plan.voices} at {plan.distance / line:g}")
                print(f"| {mode} | " + " | ".join(cells) + " |")
            continue
        for mode in modes:
            print(f"\n### {mode}\n")
            print("| section | sung as | voices clash | band (tune's own) | whole tones | together | fits |")
            print("|---|---|---|---|---|---|---|")
            for name, how, s, ok in rows(genome, mode):
                print(f"| {name} | {how} | {s['voices']:.2f} | {s['band']:.2f} ({s['own']:.2f}) | {s['seconds']:.1f} | "
                      f"{s['overlap']:.1f} | {'yes' if ok else ''} |")


if __name__ == "__main__":
    main()
