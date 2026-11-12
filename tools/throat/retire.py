"""A copy of a throat model drawing only some of its singers (dev only).

    uv run python tools/throat/retire.py IN.npz OUT.npz PREFIX [PREFIX ...]

Every singer whose name starts with none of the prefixes is retired (config "retired", as `train.py --retire`
does at training time): its row stays, so a version whose timbre names it still sings as it did, but no default
or machine's own blend draws it (`throat.drawn`). The weights are untouched, so one training run can be heard with
different singers drawn: model-C trained on blend A and Scylla's Band, drawing the blend singers alone
(`blend-`) or Scylla's alone (`scylla-`).
"""

from __future__ import annotations

import json
import sys

import numpy as np


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    src, dst, *keep = sys.argv[1:]
    z = dict(np.load(src))
    cfg = json.loads(str(z["config"]))
    cfg["retired"] = [s for s in cfg["singers"] if not any(s.startswith(k) for k in keep)]
    if len(cfg["retired"]) == len(cfg["singers"]):
        raise SystemExit(f"no singer in {src} starts with {keep}")
    z["config"] = np.array(json.dumps(cfg))
    np.savez(dst, **z)
    print(f"{dst}: draws {[s for s in cfg['singers'] if s not in cfg['retired']]}")


if __name__ == "__main__":
    main()
