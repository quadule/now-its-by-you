"""How much of a render runs at once, and the rule that keeps it the same to the sample.

A render splits where its pieces don't depend on one another: the band's parts and the singers
(synth.render_stems), the throat's pulses (throat.synthesize), the mix's buses and channel strips
(mixing.mix), the true-peak envelope's stretches (master.true_peak_envelope), the throat network's
activations (throat._gelu), a long stereo signal's two channels through an equalizer (fx._biquads).
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


def in_order(jobs: list, first: tuple = (), ahead: int | None = None):
    """(name, make()) for (name, make) jobs, one at a time in the jobs' order, while up to workers() threads
    make what comes next: at most `ahead` (default: twice the threads) made and not yet handed on, so a long
    list doesn't hold every result at once. The names in `first` are started first."""
    threads = min(workers(), len(jobs))
    if threads <= 1:
        for name, make in jobs:
            yield name, make()
        return
    ahead = max(ahead or 2 * threads, threads)
    order = sorted(range(len(jobs)), key=lambda k: jobs[k][0] not in first)  # stable: the rest in their order
    pool = ThreadPoolExecutor(threads)
    futures: dict = {}
    started = 0
    try:
        for k, (name, _) in enumerate(jobs):
            while started < len(order) and (len(futures) < ahead or k not in futures):
                j = order[started]
                futures[j] = pool.submit(jobs[j][1])
                started += 1
            yield name, futures.pop(k).result()
    finally:
        pool.shutdown(cancel_futures=True)


def made(jobs: list, progress=None, first: tuple = ()) -> dict:
    """{name: make()} for (name, make) jobs, in the jobs' order, made on up to workers() threads (in_order);
    the names in `first` are started first (the longest, so the rest fit around them). progress, if given,
    is told each name in order as the render comes to it."""
    out = {}
    results = in_order(jobs, first, ahead=len(jobs))
    try:
        for name, _ in jobs:
            if progress is not None:
                progress(name)
            out[name] = next(results)[1]
    finally:
        results.close()
    return out
