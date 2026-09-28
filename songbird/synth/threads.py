"""How much of a render runs at once, and the rule that keeps it the same to the sample.

A render splits where its pieces don't depend on one another: the band's parts and the singers
(synth.render_stems), the throat's pulses (throat.synthesize).
Each piece draws on its own random stream and is computed exactly as it would be alone; only the
putting together (a sum, an overlap-add) happens in one place, in the order it always has. So a
render is the same whichever thread makes which piece, and whatever SONGBIRD_THREADS says.

numpy's large operations and the numba loops (compiled with nogil) let go of the interpreter
while they run, so the threads work side by side.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor


def workers() -> int:
    """How many threads a render may use for work that splits: SONGBIRD_THREADS if set (1: none), else
    the machine's cores, at most 6 (more only contend: on a 10-core Mac, 4 to 6 render fastest)."""
    try:
        wanted = int(os.environ.get("SONGBIRD_THREADS", "0"))
    except ValueError:
        wanted = 0
    return max(1, wanted if wanted > 0 else min(os.cpu_count() or 1, 6))


def made(jobs: list, progress=None, first: tuple = ()) -> dict:
    """{name: make()} for (name, make) jobs, in the jobs' order, made on up to workers() threads; the
    names in `first` are started first (the longest, so the rest fit around them). progress, if given,
    is told each name in order as the render comes to it."""
    threads = min(workers(), len(jobs))
    out = {}
    if threads <= 1:
        for name, make in jobs:
            if progress is not None:
                progress(name)
            out[name] = make()
        return out
    pool = ThreadPoolExecutor(threads)
    try:
        order = sorted(range(len(jobs)), key=lambda k: jobs[k][0] not in first)  # stable: the rest in order
        futures = {jobs[k][0]: pool.submit(jobs[k][1]) for k in order}
        for name, _ in jobs:
            if progress is not None:
                progress(name)
            out[name] = futures[name].result()
    finally:
        pool.shutdown(cancel_futures=True)
    return out
