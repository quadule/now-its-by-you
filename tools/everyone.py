"""Everyone's way: the phrasing every counted take makes together, the choir's, and the render (dev-only).

    uv run python tools/everyone.py                          # the blends: renders/phrasing/<song>.everyone.json, .choir.1-3.json
    uv run python tools/everyone.py --render renders/review/contest.flac   # ...and the song sung that way, packed
    uv run python tools/everyone.py --stamp                  # also a dated copy, for a site build (--phrasing FILE)

The karaoke page's "everyone's way, blended, with the lineage choir" does the same (tools/karaoke.py
render); this is it from the command line, for the contest render after singing closes. Every take
ticked to count (tools/takes.py) goes into the lead's blend, each person counting once at each place
in the song. The choir's CHOIR voices are the singers, each their own way; with more singers than
voices, several are blended into each (round robin, in name order), so everyone who sang is in it.
A voice whose singers never sang a whole note is left to a stand-in (the machine's own way).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import takes as K  # noqa: E402  (tools/takes.py)

CHOIR = 3  # the lineage choir's voices in a render (songbird.realize: choir=)
H = ROOT / "songs" / "h-now-its-by-you.json"


def phrasing_path(song: str, name: str) -> Path:
    """renders/phrasing/<song>.<name>.json: a name no singer's folder can have ("everyone", "choir.1")."""
    return ROOT / "renders" / "phrasing" / f"{song}.{name}.json"


def blend(genome_path: Path, genome, name: str, takes: list) -> Path:
    """A phrasing from these takes, each person counting once, kept under `name`."""
    with contextlib.redirect_stdout(io.StringIO()):
        phrasing, data, _ = T.singer_phrasing(genome_path, genome, takes)
    data["source_detail"] = f"{len(takes)} sung takes by {len({t.who for t in takes})} singers"
    out = phrasing_path(Path(genome_path).stem, name)
    T.write(data, phrasing, out)
    return out


def choir_blends(genome_path: Path, genome, counted: list, lead: str = "everyone", choir: int = CHOIR) -> list[Path]:
    """The choir's voices' phrasings: the singers other than the lead (everyone: all of them), round robin
    into `choir` voices; a voice whose singers never sang a whole note is skipped (a stand-in sings it)."""
    others = sorted({t.who for t in counted} - {lead})
    voices = []
    for i in range(min(choir, len(others))):
        with contextlib.suppress(ValueError):
            voices.append(blend(genome_path, genome, f"choir.{i + 1}", [t for t in counted if t.who in others[i::choir]]))
    return voices


def render_args(genome_path: Path, genome, counted: list, choir: int = CHOIR) -> list[str]:
    """The `songbird render` arguments that sing the song everyone's way, with the choir."""
    args = ["--phrasing", str(blend(genome_path, genome, "everyone", counted))]
    voices = choir_blends(genome_path, genome, counted, "everyone", choir)
    return args + ["--choir", str(choir)] + (["--choir-phrasing", *map(str, voices)] if voices else [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--song", default=str(H))
    ap.add_argument("--choir", type=int, default=CHOIR, help=f"the choir's voices (default {CHOIR})")
    ap.add_argument("--render", metavar="OUT.flac", help="render the song everyone's way, packed, to this file")
    ap.add_argument("--stamp", action="store_true", help="also keep everyone's blend as <song>.site-<date-time>.json")
    ap.add_argument("--arrange", nargs="*", default=[], metavar="FIELD=VALUE",
                    help="the arrangement's options for the render (songbird render --arrange), e.g. intro=quote "
                         "for the Daisy Bell quote before the song")
    args = ap.parse_args()

    from songbird import genome as G

    genome_path = Path(args.song).resolve()
    genome = G.load(genome_path)
    counted = [t for t in K.takes(genome_path.stem) if t.use]
    if not counted:
        raise SystemExit("no takes are marked to count")
    render = render_args(genome_path, genome, counted, args.choir)
    print(f"everyone: {len(counted)} takes by {len({t.who for t in counted})} singers -> {render[1]}")
    for i, voice in enumerate(render[render.index("--choir-phrasing") + 1:] if "--choir-phrasing" in render else []):
        print(f"choir voice {i + 1}: {voice}")
    if args.stamp:
        stamped = phrasing_path(genome_path.stem, "site-" + time.strftime("%Y%m%d-%H%M"))
        stamped.write_bytes(Path(render[1]).read_bytes())
        print(f"for the site: {stamped}")
    if args.render:
        from songbird.cli import main as songbird

        arrange = ["--arrange", *args.arrange] if args.arrange else []
        code = songbird(["render", str(genome_path), *render, *arrange, "--out", args.render, "--pack"])
        if code:
            raise SystemExit(code)


if __name__ == "__main__":
    main()
