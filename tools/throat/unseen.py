"""How close each throat model gets to real singers it never trained on (dev only).

    uv run python tools/throat/unseen.py DATASET MODEL.npz [MODEL.npz ...] --singers folk-a folk-b ...
        [--house-held seg ...]

DATASET is a training set (tools/throat/dataset.py, or folk.py merge's) holding the singers' segments; they
must have been held out of (or excluded from) every model's training. docs/THROAT.md, "Folk singers".

For every held-out singer (all their frames were held out of training): the best voice the model can make
for them, a singer embedding fitted (Nelder-Mead from the mean of the model's rows, 40 tries a number) on the first
half of their sung frames, then the envelope's error on the second half: mean absolute dB over the grid points
inside each frame's band, vowels and sonorants only (unmasked frames, role >= onset); and the same with each
stretch's own average spectrum taken out of both (the microphone's and the room's colouring). Also the envelope's
formant contrast (RMS dB about a 17-point Hann trend, 200 Hz-5 kHz) and flutter (RMS dB of the frame-to-frame
change) on those frames, predicted against real, since a small network's envelope is an average.

The house singers' held-out segments are scored with their own rows (does adding people cost the house
singers anything?).
"""
import argparse
import sys

import numpy as np
from scipy.optimize import minimize

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from songbird.synth import throat  # noqa: E402

DB = 10 / np.log(10)
KEYS = ["phone", "prev", "next", "prev2", "next2", "role", "pos", "dur", "stress", "level"]


def frames_of(d, segs, cap=6000):
    idx = []
    for i in segs:
        a, n = int(d["offsets"][i]), int(d["lengths"][i])
        idx.append(np.arange(a, a + n))
    idx = np.concatenate(idx) if idx else np.zeros(0, int)
    return idx


def chunked(d, idx):
    """Contiguous runs of idx (predict needs frames in order: it convolves along time)."""
    if not len(idx):
        return []
    cuts = np.flatnonzero(np.diff(idx) != 1) + 1
    return np.split(idx, cuts)


def predict_runs(model, d, runs, emb):
    sps = []
    for r in runs:
        t = {k: np.asarray(d[k][r[0]: r[-1] + 1]) for k in KEYS}
        sp, _ = throat.predict(model, t, np.asarray(d["lf0"][r[0]: r[-1] + 1]).astype(np.float64), emb)
        sps.append(sp)
    return sps


def scored(d, runs):
    """Per run: which frames count (unmasked, sung or sonorant: role >= 2) and how many grid points (band)."""
    out = []
    for r in runs:
        sl = slice(r[0], r[-1] + 1)
        m = np.asarray(d["mask"][sl]) & (np.asarray(d["role"][sl]) >= 2)
        top = np.asarray(d["sp_top"][sl]) if "sp_top" in d.files else np.full(len(r), 128)
        out.append((m, top))
    return out


def err(model, d, runs, sc, emb, channel=False):
    """Mean absolute envelope error (dB) over scored in-band points; with channel, after taking each run's own
    average spectrum (its scored frames') out of the predicted and the real alike: the voice's moving shape, not
    the microphone's and the room's colouring."""
    tot, n = 0.0, 0
    for sp, r, (m, top) in zip(predict_runs(model, d, runs, emb), runs, sc):
        real = np.asarray(d["sp"][r[0]: r[-1] + 1]).astype(np.float64)
        g = np.arange(sp.shape[1])[None, :] < top[:, None]
        w = g & m[:, None]
        if channel:
            if m.sum() < 10:
                continue
            sp = sp - (sp * w).sum(0) / np.maximum(w.sum(0), 1)
            real = real - (real * w).sum(0) / np.maximum(w.sum(0), 1)
        tot += float((np.abs(sp - real) * w).sum()) * DB
        n += int(w.sum())
    return tot / max(n, 1)


def texture(model, d, runs, sc, emb):
    """Formant contrast and flutter (dB), predicted and real, on full-band scored frames."""
    g = throat.grid(len(model.sp_mean))
    band = (g >= 200) & (g <= 5000)
    win = np.hanning(19)[1:-1]
    win /= win.sum()

    def measure(sp):
        trend = np.apply_along_axis(lambda v: np.convolve(np.pad(v, 8, mode="edge"), win, "valid"), 1, sp)
        c = np.sqrt(np.mean(((sp - trend)[:, band] * DB) ** 2))
        f = np.sqrt(np.mean((np.diff(sp[:, band], axis=0) * DB) ** 2)) if len(sp) > 1 else np.nan
        return c, f

    pc, pf, rc, rf = [], [], [], []
    for sp, r, (m, top) in zip(predict_runs(model, d, runs, emb), runs, sc):
        keep = m & (top >= int(np.sum(g <= 5000)))  # inside the band the measures use (200 Hz-5 kHz)
        if keep.sum() < 20:
            continue
        real = np.asarray(d["sp"][r[0]: r[-1] + 1]).astype(np.float64)
        # contiguous scored stretches only, for flutter
        for k in np.split(np.flatnonzero(keep), np.flatnonzero(np.diff(np.flatnonzero(keep)) != 1) + 1):
            if len(k) < 10:
                continue
            a, b = measure(sp[k]), measure(real[k])
            pc.append(a[0]); pf.append(a[1]); rc.append(b[0]); rf.append(b[1])
    return (np.mean(pc), np.mean(pf), np.mean(rc), np.mean(rf)) if pc else (np.nan,) * 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("models", nargs="+")
    ap.add_argument("--singers", nargs="+", required=True, help="held-out singers (all their frames held out)")
    ap.add_argument("--house-held", nargs="*", default=["house-alto.j-goes-like-this.01", "house-rough.k-still-you-grew.02"])
    ap.add_argument("--fit-frames", type=int, default=4000)
    args = ap.parse_args()
    d = np.load(args.dataset, mmap_mode="r")
    segs = [str(s) for s in d["segments"]]
    for path in args.models:
        model = throat.load(path)
        names = model.config["singers"]
        rows = model.w["singer.weight"]
        print(f"== {path.split('/')[-1]}  ({len(names)} singers)", flush=True)
        errs = []
        for s in args.singers:
            mine = [i for i, n in enumerate(segs) if n.startswith(s + "/")]
            if not mine:
                print(f"  {s}: no segments")
                continue
            half = len(mine) // 2 or 1
            fit_runs = chunked(d, frames_of(d, mine[:half]))
            test_runs = chunked(d, frames_of(d, mine[half:] or mine[:half]))
            # fit on at most fit-frames frames, for speed
            budget, fr = args.fit_frames, []
            for r in fit_runs:
                if budget <= 0:
                    break
                fr.append(r[:budget]); budget -= len(fr[-1])
            sc_fit, sc_test = scored(d, fr), scored(d, test_runs)
            start = rows.mean(axis=0)
            res = minimize(lambda e: err(model, d, fr, sc_fit, e), start, method="Nelder-Mead",
                           options=dict(maxfev=40 * len(start), xatol=1e-3, fatol=1e-4))  # as many tries a number
            e_mean, e_fit = err(model, d, test_runs, sc_test, start), err(model, d, test_runs, sc_test, res.x)
            c_mean, c_fit = (err(model, d, test_runs, sc_test, e, channel=True) for e in (start, res.x))
            pc, pf, rc, rf = texture(model, d, test_runs, sc_test, res.x)
            errs.append((e_fit, e_mean, c_fit, c_mean))
            print(f"  {s:28} error {e_fit:5.2f} dB fitted ({e_mean:5.2f} at the mean row); channel out {c_fit:4.2f} ({c_mean:4.2f}); "
                  f"contrast {pc:4.2f} vs real {rc:4.2f}, flutter {pf:4.2f} vs {rf:4.2f}", flush=True)
        if errs:
            e = np.mean(errs, axis=0)
            print(f"  MEAN over unseen singers: {e[0]:5.2f} dB fitted, {e[1]:5.2f} at the mean row; channel out {e[2]:4.2f} fitted, "
                  f"{e[3]:4.2f} at the mean row", flush=True)
        for h in args.house_held:
            mine = [i for i, n in enumerate(segs) if h in n]
            if not mine:
                continue
            singer = segs[mine[0]].split("/")[0] if "/" in segs[mine[0]] else h.split(".")[0]
            singer = singer if singer in names else h.split(".")[0]
            runs = chunked(d, frames_of(d, mine))
            emb = throat.timbre(model, {singer: 1.0})
            print(f"  house held-out {h:36} error {err(model, d, runs, scored(d, runs), emb):5.2f} dB (own row)", flush=True)


if __name__ == "__main__":
    main()
