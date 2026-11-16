"""A take sung over a version with a line of its own, for tests/test_singing_after_rewriting.py (run as a script, in
a process of its own: it loads the measuring tools).

    python tests/_singing_rewritten_take.py KIT OUT [standins]

KIT gets the lead song and a guide for the version with the first verse's first line of twelve syllables (its own
line, tests/test_own_lines.py), laid as webstudio/guide.py lays a guide at 90%, cut after the first verse; OUT gets
result.json: webstudio/worker.py take()'s answer for the template singer singing that verse with every note of the
line of its own LATE seconds late (the rest on time), at 48 kHz as a browser records, cut to the verse's window.
With "standins", pyworld and librosa are hidden, so measuring runs WORLD in wasm under wasmtime and the numpy DTW
(webstudio/standins.py).
"""

import importlib.abc
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from webstudio import guide as GD, worker  # noqa: E402
from webstudio.kit import Kit  # noqa: E402

LATE = 0.08


class Hidden(importlib.abc.MetaPathFinder):
    """pyworld and librosa as on a computer without them."""

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("pyworld", "librosa"):
            raise ModuleNotFoundError(f"No module named {name!r}")
        return None


def main(kit_root: str, out_root: str, standins: bool = False) -> None:
    if standins:
        sys.meta_path.insert(0, Hidden())
    import io

    import soundfile as sf
    from scipy.signal import resample_poly

    from test_composition import ADA, DAY, G, SONG
    from test_own_lines import PATH, WORDS, twelve

    from songbird import edits as E

    out = Path(out_root)
    out.mkdir(parents=True, exist_ok=True)
    kit = Kit(kit_root)
    kit.keep_song(SONG.stem, SONG.read_bytes())
    tools = worker.Tools(kit)
    T = tools.T
    r = E.resolve(G, None, ADA, DAY, {PATH: {"words": WORDS, "notes": twelve()}})
    full = GD.score_for(G, r.params, r.lyrics, 90, 0)
    words = GD.words(full, G.title, "x")
    verse = next(s for s in words["sections"] if s.get("window"))  # the first verse
    a, b = verse["window"]
    end = b + 1.0
    voice = sorted([n for n in full["notes"] if n["part"] == "voice"], key=lambda n: n["start"])
    kept = [k for k, n in enumerate(voice) if n["start"] < b]
    cut = {**full, "notes": [n for n in full["notes"] if n["start"] < b], "duration": end,
           "sections": [[name, s0, min(s1, end)] for name, s0, s1 in full["sections"] if s0 < end],
           "beats": [bt for bt in full["beats"] if bt[0] < end], "line_of": [full["line_of"][k] for k in kept]}
    digest = GD.digest(cut)
    kit.keep_guide(SONG.stem, digest, GD.text(cut))
    g = tools.guide(SONG.stem, digest)
    told = T.guide_lines(tools.genome(SONG.stem)[0], digest, len(g.notes))
    own = [k for k, t in enumerate(told["notes"]) if t[0] == PATH.removeprefix("line.")]
    planted = [replace(n, start=n.start + LATE, dur=n.dur - LATE) if k in own else n for k, n in enumerate(g.notes)]
    y = T.V.sing(planted, T.S.SR, T.FLAT, 0, g.lexicon)
    y = y[int(a * T.S.SR): int((b + 0.6) * T.S.SR)]
    y = resample_poly(y, 160, 147) * (0.3 / max(1e-9, float(np.max(np.abs(y)))))
    buffer = io.BytesIO()
    sf.write(buffer, y, 48000, subtype="PCM_16", format="WAV")
    result = worker.take(tools, {"song": SONG.stem, "guide": digest, "from_s": a, "to_s": b, "earlier": [],
                                 "audio": buffer.getvalue()})
    (out / "result.json").write_text(json.dumps({"result": result, "pyworld": sys.modules["pyworld"].__name__, "own": own, "tempo": g.tempo, "late": LATE,
                                                 "phrases": [n.phrase for n in g.notes],
                                                 "measured": [k for k, n in enumerate(result["measurement"]["notes"])
                                                              if n["gesture"] is not None]}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:] == ["standins"])
