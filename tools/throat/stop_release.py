"""Our throat's stops and affricates against Scylla's, on the same items, notes and timing (dev only).

    PYTHONPATH=. python tools/throat/stop_release.py CONFIGS.json [N_ITEMS] [--phones T,K,...] [--voice tract=0.95]

CONFIGS is {name: "asis" | "physical" | {...}}: "asis" sings every release as articulate makes it without
throat.STOP_RELEASE; "physical" with throat.STOP_PHYSICAL (the t, k and p the artist chose); a dict is
STOP_RELEASE settings by phone on top of STOP_PHYSICAL ({"_base": "asis", ...} on top of none).

Scylla sang H's items (renders/throat-scylla2: the corpus, its plan and the align labels); we sing the same
items' notes with the throat and place each phone with our own schedule, as throat.sing does. For each phone
and place in the syllable (away from fricatives, whose hiss would be measured instead), a detector finds the
release from the audio: the quietest 10 ms from 60 ms before the label to 60 ms after (the closure), then the
sharpest rise of 2-9 kHz energy after it, within 80 ms or by the label's end. Printed: the median of three bands' envelopes (dB re the
voice's vowel level, the median 6 ms frame within 25 dB of its loudest) at moments after the release, their
first 30 ms's energy, and the mean |difference| from Scylla's over the first 40 ms.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import fields, replace
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import stft

sys.path.insert(0, str(Path(__file__).parent))
from corpus import items  # noqa: E402

from songbird.score import Note  # noqa: E402
from songbird.synth import throat  # noqa: E402
from songbird.synth.voice import VoiceParams, schedule  # noqa: E402

SR, HOP = 24000, 24  # 1 ms frames
ROOT = Path("renders/throat-scylla2")
FRIC = {"S", "Z", "SH", "ZH", "F", "V", "TH", "DH", "HH", "CH", "JH"}
BANDS = (("b1", 1500, 2700), ("b2", 2700, 4500), ("b3", 4500, 9000))
AT = [0, 2, 5, 10, 20, 30, 40, 60]


def frames(y):
    f, t, Z = stft(y, SR, nperseg=144, noverlap=144 - HOP, boundary=None, padded=False)  # 6 ms windows
    P = np.abs(Z) ** 2 + 1e-12
    band = lambda lo, hi: 10 * np.log10(P[(f >= lo) & (f < hi)].sum(0))  # noqa: E731
    return t + 0.003, {"tot": band(0, 9000), "hi": band(2000, 9000), **{k: band(lo, hi) for k, lo, hi in BANDS}}


def release_env(t, B, ref, s, e):
    idx = np.flatnonzero((t >= s - 0.06) & (t <= e + 0.06))
    if len(idx) < 20:
        return None
    sm = np.convolve(B["tot"], np.ones(10) / 10, "same")
    c = idx[np.argmin(sm[idx])]
    after = idx[(idx > c) & (t[idx] <= max(t[c] + 0.08, e + 0.01))]  # a long closure (a ch's) releases late
    if len(after) < 5:
        return None
    d = np.diff(B["hi"])[np.clip(after - 1, 0, len(B["hi"]) - 2)]
    r = after[np.argmax(np.convolve(d, np.ones(3), "same"))]
    pk = r + int(np.argmax(B["hi"][r: r + 15])) if r + 15 < len(t) else r
    if B["hi"][pk] - B["hi"][c] <= 6 or r - 20 < 0 or r + 80 >= len(t):
        return None
    return {k: B[k][r - 20: r + 80] - ref for k, _, _ in BANDS}


def stops_of(y, phones, out, voice, wanted):
    t, B = frames(y)
    tot = B["tot"]
    ref = float(np.median(tot[tot > tot.max() - 25]))
    strip = lambda p: re.sub(r"\d", "", p)  # noqa: E731
    for i, p in enumerate(phones):
        ph = strip(p["phone"])
        if ph not in wanted or p["role"] not in ("onset", "coda"):
            continue
        if p["role"] == "onset":
            nb = strip(phones[i - 1]["phone"]) if i else ""
        else:
            nb = strip(phones[i + 1]["phone"]) if i + 1 < len(phones) else ""
        if nb in FRIC:
            continue
        e = release_env(t, B, ref, p["start"], p["end"])
        if e:
            out.setdefault((voice, ph, p["role"]), []).append(e)


def apply(cfg):
    throat.STOP_RELEASE.update({p: None for p in throat.STOP_RELEASE})
    if cfg == "asis":
        return
    if cfg == "physical":
        throat.STOP_RELEASE.update(throat.STOP_PHYSICAL)
        return
    cfg = dict(cfg)
    if cfg.pop("_base", "physical") == "physical":
        throat.STOP_RELEASE.update(throat.STOP_PHYSICAL)
    throat.STOP_RELEASE.update(cfg)


def main(argv):
    phones = ["T", "K", "P", "CH", "B", "D", "G", "JH"]
    singer = VoiceParams()
    if "--voice" in argv:  # another singer, e.g. --voice tract=0.95 (Scylla's own stops stay the reference)
        i = argv.index("--voice")
        singer = replace(singer, **{k: float(v) for k, v in (kv.split("=") for kv in argv[i + 1].split(","))})
        argv = argv[:i] + argv[i + 2:]
    if "--phones" in argv:
        i = argv.index("--phones")
        phones = argv[i + 1].split(",")
        argv = argv[:i] + argv[i + 2:]
    configs = json.loads(Path(argv[0]).read_text())
    n_items = int(argv[1]) if len(argv) > 1 else 24
    plan = json.loads((ROOT / "plan.json").read_text())["items"]
    pool = {it["id"]: it for it in items(np.random.default_rng(0))}
    chosen = [p for p in plan if p["item"] in pool][:: max(1, len(plan) // n_items)][:n_items]
    known = {f.name for f in fields(Note)}
    res: dict = {}
    for plan_it in chosen:
        it = pool[plan_it["item"]]
        shifted = [dict(n, pitch=n["pitch"] + plan_it["shift"]) for n in it["notes"]]
        notes = sorted([Note(**{"part": "voice", **{k: v for k, v in n.items() if k in known}}) for n in shifted],
                       key=lambda n: n.start)
        for s in plan_it["segments"]:
            labels = ROOT / "align" / f"scylla-{plan_it['voice']}" / f"{s['index']}.json"
            lab = json.loads(labels.read_text())["phones"]
            y, _ = sf.read(str(ROOT / "corpus" / f"scylla-{plan_it['voice']}" / f"{s['index']}.wav"))
            stops_of(y.mean(1) if y.ndim > 1 else y, lab, res, "scylla", phones)
        for name, cfg in configs.items():
            apply(cfg)
            y = throat.sing(notes, SR, singer, plan_it["seed"], it["lexicon"])
            ours = schedule(notes, singer, it["lexicon"], throat.DURATIONS, seed=plan_it["seed"])
            stops_of(y, [{"phone": g.phone, "role": g.role, "start": g.t0, "end": g.t1} for g in ours], res, name,
                     phones)
    apply("asis")
    for ph in phones:
        for role in ("onset", "coda"):
            S = res.get(("scylla", ph, role), [])
            if len(S) < 3:
                continue
            ref = {k: np.median(np.array([x[k] for x in S]), 0) for k, _, _ in BANDS}
            print(f"== {ph} {role}  (b1 1.5-2.7, b2 2.7-4.5, b3 4.5-9 kHz; dB re the vowel)  ms: "
                  + " ".join(f"{a:>4}" for a in AT) + "    e30  |diff|")
            for v in ["scylla", *configs]:
                r = res.get((v, ph, role), [])
                if len(r) < 3:
                    continue
                devs = []
                for k, _, _ in BANDS:
                    E = np.median(np.array([x[k] for x in r]), 0)
                    e30 = 10 * np.log10(np.mean(10 ** (E[20:50] / 10)))
                    dev = float(np.mean(np.abs(E[20:60] - ref[k][20:60])))
                    devs.append(dev)
                    print(f"   {v[:12]:>12} {len(r):4} {k} " + " ".join(f"{E[20 + a]:+4.0f}" for a in AT)
                          + f"  {e30:+5.1f}  {dev:4.1f}")
                if v != "scylla":
                    print(f"   {'':>12} {'':4}    mean |diff| {np.mean(devs):.1f} dB")


if __name__ == "__main__":
    main(sys.argv[1:])
