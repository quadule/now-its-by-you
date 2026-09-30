"""Run once while the image is built: the synthesis compiled into NUMBA_CACHE_DIR, so the first visitor
of the day (and of every restart) doesn't wait 10 to 15 s for it, whichever band they choose.

The song's first verse with its own band and with each style's (every instrument a visitor can pick),
then what a recording adds (mastering to the target loudness, its measures) on a few seconds of noise:
a whole song would need a whole render's memory. What is made goes nowhere: SONGBIRD_HOME is a
temporary folder here.
"""

import os
import sys
import tempfile
import time

os.environ["SONGBIRD_HOME"] = tempfile.mkdtemp()

import numpy as np  # noqa: E402

from songbird import studio  # noqa: E402
from songbird.style import STYLES  # noqa: E402
from songbird.synth import SR, master  # noqa: E402


def made(s, answer):
    job = s.jobs.get(answer["id"]) if answer.get("id") else None
    while job is not None and job.state in ("queued", "running"):
        time.sleep(0.2)
    if job is not None and job.state == "failed":
        raise SystemExit(f"warm: {job.label}: {job.error}")


def main() -> int:
    began = time.monotonic()
    s = studio.Studio(None, None, "none")
    first = next((k for k, name in enumerate(s.version({}).params.form) if s.genome.section(name).lyrics), 0)
    for edits in [{}, *({"style.name": name} for name in sorted(STYLES))]:
        made(s, s.listen(edits, "you", first))
        print(f"warm: {edits.get('style.name', 'its own band')} ({time.monotonic() - began:.0f} s)", flush=True)
    noise = np.random.default_rng(0).standard_normal((5 * SR, 2)) * 0.1
    loud = master.master(noise, SR)
    master.loudness_range(loud, SR)
    master.true_peak(loud)
    print(f"warm: mastering ({time.monotonic() - began:.0f} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
