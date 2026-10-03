"""A guide made as the studio makes one, and a take with a planted way of singing, for tests/test_web_singing.py
(run as a script, in a process of its own: it loads the measuring tools, which the test's own process shouldn't).

    python tests/_web_singing_take.py KIT OUT

KIT gets the lead song and a guide for its first verse and refrain (the version the studio sings today, at 90%, laid as
webstudio/guide.py lays a guide, cut after the refrain so it stays small); OUT gets take.wav, the template singer
singing the refrain with every second note 60 ms late (the rest on time), at 48 kHz as a browser records, cut to
the refrain's window as the page cuts a take of one section; take.json, where it was sung; reference.json,
tools/phrasing.py measure_window's own measurement of the same file (without MFA) with the template singer singing
the refrain's notes (webstudio/worker.py PartTemplates); and template.json, how that part template compares with
template()'s, the template singer singing the whole guide, over the same frames.
"""

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from webstudio import guide as GD  # noqa: E402
from webstudio.kit import Kit  # noqa: E402
from webstudio.worker import PartTemplates, Tools  # noqa: E402

LATE = 0.06


def main(kit_root: str, out_root: str) -> None:
    import soundfile as sf
    from scipy.signal import resample_poly

    from songbird import studio as S

    out = Path(out_root)
    out.mkdir(parents=True, exist_ok=True)
    song = ROOT / "songs" / "h-now-its-by-you.json"
    stem = song.stem
    kit = Kit(kit_root)
    kit.keep_song(stem, song.read_bytes())
    tools = Tools(kit)
    T = tools.T
    path, genome = tools.genome(stem)
    studio = S.Studio(None, str(song), "none", out=out / "studio")
    v = studio.version({})
    full = GD.score_for(genome, v.params, v.lyrics, 90, 0)
    words = GD.words(full, genome.title, "x")
    verse = [s for s in words["sections"] if s.get("window")][1]  # the first refrain: a verse before it
    a, b = verse["window"]
    end = b + 1.0
    cut = {**full, "notes": [n for n in full["notes"] if n["start"] < b], "duration": end,
           "sections": [[name, s0, min(s1, end)] for name, s0, s1 in full["sections"] if s0 < end],
           "beats": [bt for bt in full["beats"] if bt[0] < end]}
    digest = GD.digest(cut)
    kit.keep_guide(stem, digest, GD.text(cut))
    g = tools.guide(stem, digest)

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
    g.templates = PartTemplates(g, tools, a, b)
    (out / "reference.json").write_text(json.dumps(T.measure_window(take, g, a, b)))

    # the part template against the whole guide's, over the frames of the refrain's notes
    part = g.templates[0]
    g.templates = {}
    whole = T.template(g, 0)
    inside = [n for n in g.notes if a <= n.start < b]
    last = int((inside[-1].start + inside[-1].dur) / T.S.FRAME)
    frames = slice(int(inside[0].start / T.S.FRAME), min(len(part[0]), len(whole[0]), last))
    pf, wf = part[0][frames], whole[0][frames]
    both = (pf > 0) & (wf > 0)
    (out / "template.json").write_text(json.dumps({
        "voiced_agree": float(np.mean((pf > 0) == (wf > 0))),
        "median_cents": float(np.median(np.abs(1200 * np.log2(pf[both] / wf[both])))),
        "band_db": float(np.median(np.abs(part[1][frames] - whole[1][frames])))}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
