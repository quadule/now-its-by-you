"""Measure every take not yet measured, a few at once, so phrasings are quick to make later (dev-only).

    uv run python tools/measure.py songs/h-now-its-by-you.json              # every singer's takes marked to use
    uv run python tools/measure.py songs/h-now-its-by-you.json --jobs 3 --all

Measuring a take (tools/phrasing.py measured()) takes up to a minute or so, most of it the aligner,
which runs one take at a time whatever happens (tools/align.py holds a lock); the pitch analysis and
the template singer run beside it. What's measured is kept in renders/measured/ until the take, the
guide it was sung to or the measuring code changes, so a take measured here is instant when a phrasing
is made from it (the karaoke's "Make X's phrasing", everyone's way, or tools/phrasing.py --singer).
Run it while people are singing (tools/invite.py sync fetches their takes), and the night's phrasings
take minutes, not hours.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import io
import multiprocessing
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import takes as K  # noqa: E402  (tools/takes.py)

JOBS = 3

_genome = {}


def _measure(genome_path: str, wav: str) -> tuple[str, float, str | None]:
    """One take measured (or found measured), in a process of its own: (its path, seconds, what went wrong)."""
    import phrasing as T  # tools/phrasing.py: the aligner and whisper come with it, so once per process

    from songbird import genome as G

    if genome_path not in _genome:
        _genome[genome_path] = G.load(genome_path)
    began = time.time()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            T.measured(Path(genome_path), _genome[genome_path], K.load(Path(wav)))
    except (Exception, SystemExit) as e:  # a take that can't be measured is reported, not fatal
        return wav, time.time() - began, f"{type(e).__name__}: {e}"
    return wav, time.time() - began, None


def measure_all(genome_path: Path, jobs: int = JOBS, everything: bool = False, say=print) -> int:
    """Measure every take of the song (those marked to use, or all), `jobs` at once; the number measured
    or found measured. Takes whose guide score isn't kept here can't be measured and are reported."""
    genome_path = Path(genome_path).resolve()
    chosen = [t for t in K.takes(genome_path.stem) if everything or t.use]
    if not chosen:
        say("no takes to measure")
        return 0
    done = 0
    began = time.time()
    context = multiprocessing.get_context("spawn")
    with concurrent.futures.ProcessPoolExecutor(max(1, jobs), mp_context=context) as pool:
        futures = [pool.submit(_measure, str(genome_path), str(t.path)) for t in chosen]
        for f in concurrent.futures.as_completed(futures):
            wav, seconds, error = f.result()
            name = Path(wav).relative_to(K.ROOT).as_posix() if Path(wav).is_relative_to(K.ROOT) else wav
            if error:
                say(f"  {name}: not measured ({error})")
            else:
                done += 1
                if seconds > 2:  # found measured already takes a second or two; say only what was new
                    say(f"  {name}: measured in {seconds:.0f} s")
    say(f"{done} of {len(chosen)} takes measured, in {time.time() - began:.0f} s")
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--jobs", type=int, default=JOBS, help=f"takes measured at once (default {JOBS})")
    ap.add_argument("--all", action="store_true", help="takes not marked to use as well")
    args = ap.parse_args()
    measure_all(Path(args.genome), args.jobs, args.all)


if __name__ == "__main__":
    main()
