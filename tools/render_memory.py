"""A rendition's time and peak memory, stage by stage (docs/PERFORMANCE.md, 2026-09-29).

    uv run python tools/render_memory.py                      # H's seed, as tests/test_styles.py renders it
    SONGBIRD_THREADS=2 MallocLargeCache=0 uv run python tools/render_memory.py --form refrain

Prints the PCM id, the wall time and the peak resident memory (the process's high-water mark), and for each
stage the render reports (each part, "mix", "master") its seconds and the highest resident memory sampled
during it. On macOS the allocator keeps freed large blocks for reuse, so the resident peak includes memory
already freed; MallocLargeCache=0 makes it hand them back at once, as Linux's does for arrays of more than
32 MB, which is the figure a server's limit sees (about a fifth slower on macOS: fresh pages)."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import os
import resource
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _Usage(ctypes.Structure):  # macOS's rusage_info_v2 (and room to spare): ri_resident_size is f6
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(f"f{i}", ctypes.c_uint64) for i in range(40)]


_LIBC = ctypes.CDLL(ctypes.util.find_library("c")) if sys.platform == "darwin" else None


def resident() -> int:
    """This process's resident bytes now (0 where it can't be read)."""
    if _LIBC is not None:
        info = _Usage()
        return info.f6 if _LIBC.proc_pid_rusage(os.getpid(), 2, ctypes.byref(info)) == 0 else 0
    try:
        return int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except OSError:
        return 0


def main() -> None:
    from songbird import cli, genome
    from songbird.realize import choose_params

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome", nargs="?", default=str(ROOT / "songs" / "h-now-its-by-you.json"))
    ap.add_argument("--form", nargs="+", help="render only these sections")
    ap.add_argument("--edits", help="a person's edits (a JSON map, as `songbird render --edits` takes), with no machine")
    args = ap.parse_args()

    g = genome.load(args.genome)
    params = choose_params(g)
    if args.edits:
        import json

        from songbird import edits as edits_mod

        clean, _ = edits_mod.check(g, json.loads(Path(args.edits).read_text()))
        params = edits_mod.resolve(g, None, None, None, clean).params
    if args.form:
        params = replace(params, form=tuple(args.form))
    stage, peaks, marks = ["start"], {}, []

    def sample() -> None:
        while True:
            peaks[stage[0]] = max(peaks.get(stage[0], 0), resident())
            time.sleep(0.003)

    threading.Thread(target=sample, daemon=True).start()

    def progress(name: str) -> None:
        marks.append((name, time.perf_counter()))
        stage[0] = name

    t0 = time.perf_counter()
    with tempfile.TemporaryDirectory() as d:
        record = cli.render_one(g, params, Path(d) / "out.flac", phrasing_json=g.source.get("seed_phrasing"),
                                progress=progress)
    t1 = time.perf_counter()
    scale = 1 if sys.platform == "darwin" else 1024  # ru_maxrss: bytes on macOS, kilobytes on Linux
    print(f"id {record['id'][:12]}  threads {os.environ.get('SONGBIRD_THREADS', 'default')}  wall {t1 - t0:.2f} s  "
          f"peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale / 1e9:.2f} GB")
    for k, (name, t) in enumerate(marks):
        end = marks[k + 1][1] if k + 1 < len(marks) else t1
        print(f"  {name:12s} {end - t:6.2f} s  up to {peaks.get(name, 0) / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
