"""Render a song while keeping, for every call to the learned throat, what it was told and what it sang.

    uv run python tools/promo/capture.py OUTDIR -- render GENOME [songbird render options]

Writes OUTDIR/sing-NNN.pkl: the notes, the timeline, log f0, the singer embedding and the dry voice."""
import dataclasses
import pickle
import sys
import threading
from pathlib import Path

import numpy as np

from songbird.synth import throat

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
args = sys.argv[sys.argv.index("--") + 1:]
local = threading.local()
lock = threading.Lock()
count = [0]
_predict, _sing = throat.predict, throat.sing


def predict(model, t, lf0, singer, gv=1.0, last=None, **kw):
    local.told = {"t": {k: np.array(v) for k, v in t.items()}, "lf0": np.array(lf0), "singer": np.array(singer),
                  "last": last}
    return _predict(model, t, lf0, singer, gv=gv, last=last, **kw)


def plain(n):
    d = dataclasses.asdict(n) if dataclasses.is_dataclass(n) else dict(vars(n))
    return {k: v for k, v in d.items() if isinstance(v, (int, float, str, bool, type(None)))}


def sing(notes, sr, voice, *a, **k):
    y = _sing(notes, sr, voice, *a, **k)
    with lock:
        i = count[0]
        count[0] += 1
    with open(out / f"sing-{i:03d}.pkl", "wb") as f:
        pickle.dump({"notes": [plain(n) for n in notes], "sr": sr, "voice": repr(voice), "y": y.astype(np.float32),
                     **getattr(local, "told", {})}, f)
    return y


throat.predict, throat.sing = predict, sing
from songbird.cli import main  # noqa: E402

sys.argv = ["songbird", *args]
main()
