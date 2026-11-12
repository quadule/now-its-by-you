"""The best voice a throat model can make for each singer it never heard, fitted by gradient (dev only; torch).

    python tools/throat/fit_unseen.py DATASET MODEL.npz [MODEL.npz ...] --singers folk-a folk-b ... \
        --out fitted.json [--device cuda]

tools/throat/unseen.py fits with Nelder-Mead in numpy: fine for 8 numbers, slow and loose for a 16-number singer
and an 8-number room on a wide model. This fits the same thing on the same frames (the first half of each held-out
singer's segments, at most --fit-frames of them, the same error: mean absolute dB over the scored in-band points,
after the global-variance postfilter songbird.synth.throat.predict applies) with Adam on the whole embedding at
once, from the same start (the mean of the singer rows, and of the recordings' rooms when the model kept them), and
writes each embedding for unseen.py --fitted to score with its own numpy (the numbers in the tables come from there).

Needs only numpy and torch: the network is run from the .npz as songbird.synth.throat runs it.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

KEYS = ["phone", "prev", "next", "prev2", "next2", "role", "pos", "dur", "stress", "level"]


class Net:
    """A throat .npz as tensors, with the room's FiLM weights after the singer's when it has them."""

    def __init__(self, path: Path, dev: str):
        z = np.load(path)
        self.config = json.loads(str(z["config"]))
        t = lambda a: torch.tensor(np.asarray(a, dtype=np.float32), device=dev)  # noqa: E731
        self.w = {k[2:]: t(z[k]) for k in z.files if k.startswith("w.")}
        self.sp_mean, self.sp_std, self.gv = t(z["sp_mean"]), t(z["sp_std"]), t(z["gv"])
        rows = z["w.singer.weight"]
        self.start = rows.mean(0)
        if "room_film.0" in z.files:
            table = z["room_table"]
            for k in range(len(self.config["dilations"])):
                r = t(z[f"room_film.{k}"])
                self.w[f"films.{k}.weight"] = torch.cat([self.w[f"films.{k}.weight"], r], dim=1)
                self.w[f"films.{k}.bias"] = self.w[f"films.{k}.bias"] - r @ t(table[0])
            self.start = np.concatenate([self.start, table[1:].mean(0)])
        self.n_sp = len(z["sp_mean"])

    def predict(self, run: dict, emb: torch.Tensor) -> torch.Tensor:
        """Log-power envelope (frames, points), as throat.predict makes it (gv 1)."""
        w = self.w
        x = torch.cat([w["phone.weight"][run["phones"]].flatten(1), w["role.weight"][run["role"]], run["cont"]], dim=1)
        x = x @ w["inp.weight"].T + w["inp.bias"]
        n = len(x)
        for i, d in enumerate(self.config["dilations"]):
            gamma, beta = (emb @ w[f"films.{i}.weight"].T + w[f"films.{i}.bias"]).chunk(2)
            p = F.pad(x, (0, 0, d, d))
            stacked = torch.cat([p[:n], p[d: d + n], p[2 * d: 2 * d + n]], dim=1)
            h = (stacked @ w[f"convs.{i}.weight"].T + w[f"convs.{i}.bias"]) * (1.0 + gamma) + beta
            x = x + F.gelu(h, approximate="tanh") @ w[f"mixes.{i}.weight"].T + w[f"mixes.{i}.bias"]
        sp = (x @ w["out.weight"].T + w["out.bias"])[:, : self.n_sp]
        sung = run["role"] >= 2
        mu = sp[sung].mean(0) if bool(sung.any()) else sp.mean(0)
        scale = torch.clamp(torch.sqrt(self.gv[: self.n_sp]), 1.0, 1.6)
        return (mu + (sp - mu) * scale) * self.sp_std + self.sp_mean


def continuous(t: dict, lf0: np.ndarray) -> np.ndarray:
    pos = t["pos"].astype(np.float64)
    slope = np.diff(lf0, prepend=lf0[:1]) * 100.0
    return np.stack([pos, np.sin(np.pi * pos), np.cos(np.pi * pos), t["dur"] + 2.5, t["stress"], t["level"] / 10.0,
                     (lf0 - np.log(220.0)) / 0.6, slope], axis=-1)


def runs_of(d: dict, segs: list[int], dev: str, budget: int | None = None) -> list[dict]:
    """The segments' frames as contiguous runs (as unseen.chunked), each with what predict and the error need."""
    idx = np.concatenate([np.arange(int(d["offsets"][i]), int(d["offsets"][i]) + int(d["lengths"][i])) for i in segs])
    out = []
    for r in np.split(idx, np.flatnonzero(np.diff(idx) != 1) + 1):
        if budget is not None:
            if budget <= 0:
                break
            r = r[:budget]
            budget -= len(r)
        sl = slice(r[0], r[-1] + 1)
        t = {k: np.asarray(d[k][sl]) for k in KEYS}
        lf0 = np.asarray(d["lf0"][sl]).astype(np.float64)
        top = np.asarray(d["sp_top"][sl]) if "sp_top" in d else np.full(len(r), 128)
        m = np.asarray(d["mask"][sl]) & (t["role"] >= 2)
        w = (np.arange(d["sp"].shape[1])[None, :] < top[:, None]) & m[:, None]
        tt = lambda a, dtype=torch.float32: torch.tensor(np.asarray(a), dtype=dtype, device=dev)  # noqa: E731
        out.append(dict(phones=tt(np.stack([t["prev2"], t["prev"], t["phone"], t["next"], t["next2"]], -1), torch.long),
                        role=tt(t["role"], torch.long), cont=tt(continuous(t, lf0)), real=tt(d["sp"][sl].astype(np.float32)),
                        w=tt(w)))
    return out


def error(net: Net, runs: list[dict], emb: torch.Tensor) -> torch.Tensor:
    tot, n = 0.0, 0.0
    for r in runs:
        tot = tot + ((net.predict(r, emb) - r["real"]).abs() * r["w"]).sum()
        n += float(r["w"].sum())
    return tot / max(n, 1.0) * (10 / math.log(10))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset")
    ap.add_argument("models", nargs="+", type=Path)
    ap.add_argument("--singers", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--fit-frames", type=int, default=4000)
    ap.add_argument("--steps", type=int, default=400)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--skip", nargs="*", default=[], help="segment name fragments not used (unseen.py --skip alike)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()
    z = np.load(args.dataset)
    d = {k: z[k] for k in z.files}
    segs = [str(s) for s in d["segments"]]
    fitted = json.loads(args.out.read_text()) if args.out.exists() else {}
    for path in args.models:
        net = Net(path, args.device)
        res = fitted.setdefault(path.name, {})
        for s in args.singers:
            mine = [i for i, n in enumerate(segs) if n.startswith(s + "/") and not any(k in n for k in args.skip)]
            if not mine:
                continue
            half = len(mine) // 2 or 1
            runs = runs_of(d, mine[:half], args.device, args.fit_frames)
            emb = torch.tensor(net.start, dtype=torch.float32, device=args.device, requires_grad=True)
            opt = torch.optim.Adam([emb], lr=args.lr)
            sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, args.steps)
            with torch.no_grad():
                e0 = float(error(net, runs, emb))
            for _ in range(args.steps):
                loss = error(net, runs, emb)
                opt.zero_grad()
                loss.backward()
                opt.step()
                sched.step()
            with torch.no_grad():
                e1 = float(error(net, runs, emb))
            res[s] = dict(embedding=[float(v) for v in emb.detach().cpu()], fit_error=e1, start_error=e0)
            print(f"{path.name} {s}: fit frames {e0:.2f} -> {e1:.2f} dB ({len(net.start)} numbers)", flush=True)
        args.out.write_text(json.dumps(fitted, indent=1))


if __name__ == "__main__":
    main()
