"""A small singing kit and a take with a planted way of singing, for tests/test_web_singing.py (run as a script,
in a process of its own: it loads the measuring tools, which the test's own process shouldn't).

    python tests/_web_singing_take.py KIT OUT

KIT gets a kit for the lead song's first verse alone (its spec's score cut after the verse, so the template
singer's analysis takes a moment, not a minute and 4 GB); OUT gets take.wav, the template singer singing that
verse with every second note 60 ms late (the rest on time), at 48 kHz as a browser records, cut to
the verse's window as the page cuts a take of one section; take.json, where it was sung; and reference.json,
tools/phrasing.py measure_window's own measurement of the same file (without MFA), to compare with.
"""

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webstudio.kit import VERSION, Kit  # noqa: E402
from webstudio.worker import Tools  # noqa: E402

LATE = 0.06
SPEC = "a.k0.t90"


def main(kit_root: str, out_root: str) -> None:
    import soundfile as sf
    from scipy.signal import resample_poly

    kit, out = Kit(kit_root), Path(out_root)
    out.mkdir(parents=True, exist_ok=True)
    tools = Tools(kit)
    T, K, M = tools.T, tools.K, tools.M
    import karaoke as KA  # tools/karaoke.py

    song = ROOT / "songs" / "h-now-its-by-you.json"
    stem = song.stem
    kit.genome(stem).parent.mkdir(parents=True, exist_ok=True)
    kit.genome(stem).write_bytes(song.read_bytes())
    path, genome = tools.genome(stem)
    full = json.loads(M.spec_score(path, SPEC).read_text())
    verse = next(s for s in KA.sections(full) if s.get("window"))
    a, b = verse["window"]
    end = b + 1.0
    cut = {**full, "notes": [n for n in full["notes"] if n["start"] < b], "duration": end,
           "sections": [[name, s0, min(s1, end)] for name, s0, s1 in full["sections"] if s0 < end],
           "beats": [bt for bt in full["beats"] if bt[0] < end]}
    score = out / "verse.score.json"
    score.write_text(json.dumps(cut))
    digest = K.keep_guide(stem, score)
    lyrics = {**KA.lyrics(cut, genome.title, cut["tempo"]), "guide": digest, "spec": cut["spec"]}
    kit.lyrics(SPEC).parent.mkdir(parents=True, exist_ok=True)
    kit.lyrics(SPEC).write_text(json.dumps(lyrics))
    kit.audio(SPEC).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(kit.audio(SPEC)), np.zeros(22050, dtype=np.int16), 22050, format="FLAC")
    g = tools.guide(stem, digest)
    g.templates = {}
    T.template(g, 0)
    kit.offer_path.write_text(json.dumps({
        "kit": VERSION, "song": stem, "title": genome.title, "genome": hashlib.sha256(song.read_bytes()).hexdigest(),
        "extractor": tools.extractor, "set": {"id": "a", "name": "Set A", "about": ""}, "default": SPEC,
        "specs": [{"id": SPEC, "set": "a", "key": 0, "tempo": 90, "guide": digest, "duration": end, "templates": [0]}]}))

    # the template singer, every second note LATE seconds late (it ends where it did)
    planted = [replace(n, start=n.start + LATE, dur=n.dur - LATE) if k % 2 else n for k, n in enumerate(g.notes)]
    y = T.V.sing(planted, T.S.SR, T.FLAT, 0, g.lexicon)
    y = y[int(a * T.S.SR): int((b + 0.6) * T.S.SR)]
    y = resample_poly(y, 160, 147) * (0.3 / max(1e-9, float(np.max(np.abs(y)))))
    take = out / "take.wav"
    sf.write(str(take), y, 48000, subtype="PCM_16")
    (out / "take.json").write_text(json.dumps({"song": stem, "guide": digest, "from_s": a, "to_s": b,
                                               "section": verse["index"], "tempo": g.tempo, "late": LATE,
                                               "planted": [k for k, (n, p) in enumerate(zip(g.notes, planted))
                                                           if p.start != n.start]}))
    (out / "reference.json").write_text(json.dumps(T.measure_window(take, g, a, b)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
