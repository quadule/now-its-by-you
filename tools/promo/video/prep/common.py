"""What every prep script shares: the paths, the guard on every path read or written, the array writer, and the
stage edition's score as a render lays it out (with its stage plan, which the score file leaves out)."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
MEASURED = (ROOT / "renders/measured").resolve()
DATA = ROOT / "renders/promo/video/data"
SCRATCH = ROOT / "renders/promo/video/scratch"
CAPTURE = ROOT / "renders/promo/capture-live-A"
GENOME = ROOT / "performance/genome.json"
RECORD = ROOT / "performance/record-live-A.json"
RELEASE = CAPTURE / "render.flac"  # the stage version's PA mix, rendered by tools/promo/capture.py
FPS = 60


def _duration() -> float:
    import soundfile as sf
    return round(sf.info(str(RELEASE)).duration, 4) if RELEASE.exists() else 0.0


DURATION = _duration()  # s, the release file's audio


def _section_ids() -> list[str]:
    """The record's form, one id each: a kind and its count from 1 ("verse1", "breath2"); a kind sung once bare."""
    form = json.loads(RECORD.read_text(encoding="utf-8"))["params"]["form"]
    seen: dict[str, int] = {}
    ids = []
    for name in form:
        seen[name] = seen.get(name, 0) + 1
        ids.append(name if form.count(name) == 1 else f"{name}{seen[name]}")
    return ids


# the score's section names, one id each, in order; "ring" runs from the tag's end to the file's end
SECTION_IDS = _section_ids()


def guard(path) -> Path:
    """The path, resolved; a path under renders/measured/ (private, per singer) is refused."""
    p = Path(path).resolve()
    if p == MEASURED or MEASURED in p.parents:
        raise PermissionError(f"{p}: renders/measured/ is never read by the video's prep")
    return p


def read_json(path):
    return json.loads(guard(path).read_text(encoding="utf-8"))


def read_bytes(path) -> bytes:
    return guard(path).read_bytes()


def read_text(path) -> str:
    return guard(path).read_text(encoding="utf-8")


def out(name: str) -> Path:
    """A path under data/, its folder made."""
    p = guard(DATA / name)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_json(name: str, obj, indent=None) -> Path:
    p = out(name)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":")),
                 encoding="utf-8")
    return p


def write_array(name: str, a: np.ndarray, about: str, rate=None, t0=0.0, scale=1.0, offset=0.0, **extra) -> Path:
    """<name>.bin (little-endian, C order) and <name>.json, the README's array format."""
    a = np.ascontiguousarray(a)
    dt = {np.dtype(np.uint8): "uint8", np.dtype(np.int8): "int8", np.dtype(np.int16): "int16",
          np.dtype(np.uint16): "uint16", np.dtype(np.float16): "float16", np.dtype(np.float32): "float32",
          np.dtype(np.int32): "int32"}[a.dtype]
    p = out(name + ".bin")
    p.write_bytes(a.astype(a.dtype.newbyteorder("<")).tobytes())
    write_json(name + ".json", {"dtype": dt, "shape": list(a.shape), "rate": rate, "t0": t0, "scale": float(scale),
                                "offset": float(offset), "about": about, **extra}, indent=1)
    return p


def r(x, n=4):
    return round(float(x), n)


def section_spans(score_sections) -> list[dict]:
    """The README's sections: id, kind, t0, t1, and the ring to the file's end."""
    outs = [{"id": i, "kind": name, "t0": r(a), "t1": r(b)} for i, (name, a, b) in zip(SECTION_IDS, score_sections)]
    outs.append({"id": "ring", "kind": "ring", "t0": outs[-1]["t1"], "t1": DURATION})
    return outs


def section_at(spans: list[dict], t: float) -> str:
    for s in spans:
        if s["t0"] <= t < s["t1"]:
            return s["id"]
    return "intro" if t < spans[0]["t0"] else "ring"


@lru_cache(maxsize=1)
def record() -> dict:
    return read_json(RECORD)


@lru_cache(maxsize=1)
def laid():
    """(genome, params, score): the stage edition as a replay lays it out (tools/performance/wire.py's laid(),
    keeping the Score object and its stage plan)."""
    guard(GENOME)
    from songbird import genome as genome_mod
    from songbird import phrasing as phrasing_mod
    from songbird import stage
    from songbird.arrange import Lyrics
    from songbird.cli import Params, credited

    rec = record()
    genome = genome_mod.load(GENOME)
    params = Params.from_dict(rec["params"])
    params = replace(params, singer=rec.get("singer") or params.singer, mix=rec.get("mix") or params.mix)
    lyrics = Lyrics.from_dict(rec["lyrics"]) if rec.get("lyrics") else None
    lead, choir = phrasing_mod.inherited(genome.source, rec)
    if isinstance(rec.get("performance"), dict):
        lead = credited(lead, rec.get("phrasing"))
        about = list(rec.get("choir_phrasings") or [])
        choir = [credited(c, about[i] if i < len(about) else None) for i, c in enumerate(choir)]
    score = stage.laid(genome, params, phrasing=phrasing_mod.from_json(lead) if lead else None,
                       choir=[phrasing_mod.from_json(c) for c in choir], lyrics=lyrics)
    return genome, params, score


def capture_score() -> dict:
    return read_json(CAPTURE / "render.score.json")


def say(*a):
    print(*a, file=sys.stderr)
