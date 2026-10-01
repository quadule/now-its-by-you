"""Train the learned throat (dev only; run with a Python that has torch, e.g. SoulX-Singer's venv).

    ~/Code/svs/SoulX-Singer/.venv/bin/python -B tools/throat/train.py renders/throat/dataset.npz \
        --out renders/throat/model.npz [--steps 30000] [--channels 128] [--hold-out bright.a-nobody]
        [--init renders/throat/model-house.npz]

A small stack of dilated 1-D convolutions over 5 ms frames. In: what is being sung (the phone and two
neighbours either side as learned embeddings, its role, how far through it, its length, stress, the
note's level), log f0 and its slope, and the singer, whose learned embedding scales and shifts every
layer (a machine's voice will be a mix of the singers' embeddings, never one of them). Out: the WORLD
envelope (log power, on songbird.synth.throat's mel grid) and aperiodicity. Trained with L1 on the
frames and on their frame-to-frame change, labels jittered against the audio by up to 10 ms so the
throat doesn't insist on the aligner's exact boundaries.

Every layer is a sum of shifted copies through a matrix, a tanh-GELU and additions, so
songbird.synth.throat runs it in numpy from the .npz this writes: the weights, the phone, role and
singer lists, the normalisations, and the variance of real envelopes against predicted ones (for
the global-variance postfilter that keeps a small model's envelopes from going soft).

--init starts from a model this wrote (a fine-tune): its weights, and its normalisations, so the
envelope keeps the space the old model sang in. Singers are matched by name; a singer the old model
didn't know starts at the mean of the ones it did. The channels must match the old model's. A singer in
the dataset's list with no frames of its own (one whose recordings are gone: tools/throat/folk.py merge)
keeps the old model's row and register.

A band-limited recording's frames (sp_top, ap_top in the dataset: tools/throat/dataset.py) are learned only
inside their band: the points of each grid above it count for nothing in the loss, the normalisations or
the global variance.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

DILATIONS = (1, 2, 4, 8, 1, 2, 4, 8)
KERNEL = 3
EMBED = 16
ROLE = 4
SINGER = 8
CONT = 8
JITTER = 2  # frames


def continuous(d: dict, sl) -> np.ndarray:
    """The continuous inputs, normalised as songbird.synth.throat.continuous does."""
    pos = d["pos"][sl]
    lf0 = d["lf0"][sl]
    slope = np.diff(lf0, prepend=lf0[:1]) * 100.0
    return np.stack([pos, np.sin(np.pi * pos), np.cos(np.pi * pos), d["dur"][sl] + 2.5, d["stress"][sl],
                     d["level"][sl] / 10.0, (lf0 - math.log(220.0)) / 0.6, slope], axis=-1).astype(np.float32)


def shifted(x: torch.Tensor, d: int) -> torch.Tensor:
    """(batch, frames, channels) -> (batch, frames, 3 * channels): the frames d before, at and d after."""
    p = F.pad(x, (0, 0, d, d))
    t = x.shape[1]
    return torch.cat([p[:, :t], p[:, d: d + t], p[:, 2 * d: 2 * d + t]], dim=-1)


class Throat(nn.Module):
    def __init__(self, phones: int, roles: int, singers: int, channels: int, sp: int, ap: int, dropout: float = 0.0):
        super().__init__()
        self.drop = nn.Dropout(dropout)
        self.phone = nn.Embedding(phones, EMBED)
        self.role = nn.Embedding(roles, ROLE)
        self.singer = nn.Embedding(singers, SINGER)
        self.inp = nn.Linear(5 * EMBED + ROLE + CONT, channels)
        self.convs = nn.ModuleList([nn.Linear(KERNEL * channels, channels) for _ in DILATIONS])
        self.films = nn.ModuleList([nn.Linear(SINGER, 2 * channels) for _ in DILATIONS])
        self.mixes = nn.ModuleList([nn.Linear(channels, channels) for _ in DILATIONS])
        for f, m in zip(self.films, self.mixes):
            nn.init.zeros_(f.weight)
            nn.init.zeros_(f.bias)
            m.weight.data *= 0.3
            nn.init.zeros_(m.bias)
        self.out = nn.Linear(channels, sp + ap)

    def forward(self, phones: torch.Tensor, role: torch.Tensor, cont: torch.Tensor, singer: torch.Tensor):
        """phones (batch, frames, 5): prev2, prev, phone, next, next2; singer (batch, frames, SINGER)."""
        e = self.phone(phones).flatten(2)
        x = self.inp(torch.cat([e, self.role(role), cont], dim=-1))
        for conv, film, mix, d in zip(self.convs, self.films, self.mixes, DILATIONS):
            gamma, beta = film(singer).chunk(2, dim=-1)
            h = conv(shifted(x, d)) * (1.0 + gamma) + beta
            x = x + mix(self.drop(F.gelu(h, approximate="tanh")))
        return self.out(x)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=30000)
    ap.add_argument("--channels", type=int, default=128)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--crop", type=int, default=400)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--delta", type=float, default=0.5, help="weight of the loss on frame-to-frame change")
    ap.add_argument("--dropout", type=float, default=0.1)
    ap.add_argument("--noise", type=float, default=1.0,
                    help="scale of the noise added to the pitch (about 30 cents) and level (about 1 dB) inputs while training")
    ap.add_argument("--hold-out", nargs="*", default=None, help="segment name fragments kept out for validation")
    ap.add_argument("--exclude", nargs="*", default=None,
                    help="segment name fragments left out altogether (neither trained on nor validated: a smaller corpus)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log-every", type=int, default=500)
    ap.add_argument("--init", type=Path, default=None, help="start from this model's weights and normalisations")
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)

    raw = np.load(args.dataset)
    d = {k: raw[k] for k in raw.files}
    segments, offsets, lengths = [str(s) for s in d["segments"]], d["offsets"], d["lengths"]
    singers = [str(s) for s in d["singers"]]
    sources = [str(s) for s in d["sources"]] if "sources" in d else ["eleven-music"] * len(singers)
    phones = [str(p) for p in d["phones"]]
    roles = ["sil", "breath", "onset", "vowel", "coda"]
    sp = d["sp"].astype(np.float32)
    apr = d["ap"].astype(np.float32)
    mask = d["mask"]
    n_sp, n_ap = sp.shape[1], apr.shape[1]
    sp_top = d["sp_top"] if "sp_top" in d else np.full(len(sp), n_sp, dtype=np.int16)
    ap_top = d["ap_top"] if "ap_top" in d else np.full(len(sp), n_ap, dtype=np.int16)
    full = mask & (sp_top >= n_sp) & (ap_top >= n_ap)  # frames learned in every band
    sp_mean, sp_std = sp[full].mean(0), sp[full].std(0) + 1e-3
    ap_mean, ap_std = apr[full].mean(0), apr[full].std(0) + 1e-3
    init = np.load(args.init) if args.init else None
    if init is not None:  # a fine-tune keeps the space the old model's outputs are in
        sp_mean, sp_std, ap_mean, ap_std = (init[k].astype(np.float32) for k in ("sp_mean", "sp_std", "ap_mean", "ap_std"))
    y_all = np.concatenate([(sp - sp_mean) / sp_std, (apr - ap_mean) / ap_std], axis=1).astype(np.float32)
    phone5 = np.stack([d["prev2"], d["prev"], d["phone"], d["next"], d["next2"]], axis=-1).astype(np.int64)
    cont_all = continuous(d, slice(None))
    out = {i for i, s in enumerate(segments) if args.exclude and any(h in s for h in args.exclude)}
    held = [i for i, s in enumerate(segments) if args.hold_out and any(h in s for h in args.hold_out) and i not in out]
    train = [i for i in range(len(segments)) if i not in held and i not in out and lengths[i] > args.crop + 2 * JITTER]
    print(f"{len(train)} training segments, {len(held)} held out, {len(out)} left out; {len(phones)} phones, "
          f"singers {singers}", flush=True)

    dev = args.device
    model = Throat(len(phones), len(roles), len(singers), args.channels, sp.shape[1], apr.shape[1], args.dropout).to(dev)
    if init is not None:
        old = json.loads(str(init["config"]))
        if old["channels"] != args.channels or old["phones"] != phones:
            raise SystemExit(f"--init {args.init}: {old['channels']} channels and its phones; asked for {args.channels}")
        state = model.state_dict()
        for k in state:
            w = torch.tensor(init[f"w.{k}"])
            if k == "singer.weight":  # by name; a new singer starts at the mean of the old ones
                rows = [w[old["singers"].index(n)] if n in old["singers"] else w.mean(0) for n in singers]
                w = torch.stack(rows)
            state[k] = w
        model.load_state_dict(state)
        print(f"from {args.init}: singers {[n for n in singers if n not in old['singers']]} new", flush=True)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"{n_params / 1e6:.2f}M parameters", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, s / 500) * 0.5 * (1 + math.cos(math.pi * s / args.steps)))

    def batch(ids, crop, jitter=JITTER):
        xs, ys = [], []
        for _ in range(args.batch):
            i = ids[rng.integers(len(ids))]
            a = offsets[i] + jitter + rng.integers(lengths[i] - crop - 2 * jitter + 1)
            j = int(rng.integers(-jitter, jitter + 1)) if jitter else 0
            xs.append(slice(a + j, a + j + crop))  # labels a little off the audio, as ours will be
            ys.append(slice(a, a + crop))
        t = lambda arr, rows, dtype=torch.float32: torch.tensor(np.stack([arr[s] for s in rows]), dtype=dtype, device=dev)  # noqa: E731
        cont = t(cont_all, ys)
        bands = torch.cat([dims_sp[None, None] < t(sp_top, ys, torch.long)[..., None],
                           dims_ap[None, None] < t(ap_top, ys, torch.long)[..., None]], dim=-1).float()
        if jitter and args.noise:  # our pitch and dynamics won't be SoulX's: don't lean on their exact values
            b = cont.shape[0]
            cont[..., 6] += args.noise * 0.03 * torch.randn(b, 1, device=dev)  # log f0 (a whole crop, ~30 cents)
            cont[..., 5] += args.noise * 0.1 * torch.randn(b, 1, device=dev)  # level (~1 dB)
        return (t(phone5, xs, torch.long), t(d["role"], xs, torch.long), cont, t(d["singer"], ys, torch.long),
                t(y_all, ys), t(mask, ys), bands)

    dims_sp = torch.arange(n_sp, device=dev)
    dims_ap = torch.arange(n_ap, device=dev)

    def loss_of(xb):
        phone, role, cont, singer, y, m, bands = xb
        pred = model(phone, role, cont, model.singer(singer))
        m3 = m[..., None] * bands  # each frame's points inside its band (every point, but for old records)
        base = ((pred - y).abs() * m3).sum() / (m3.sum() + 1e-6)
        dm = m[:, 1:, None] * m[:, :-1, None] * bands[:, 1:] * bands[:, :-1]
        delta = (((pred[:, 1:] - pred[:, :-1]) - (y[:, 1:] - y[:, :-1])).abs() * dm).sum() / (dm.sum() + 1e-6)
        return base + args.delta * delta, base

    t0 = time.time()
    for step in range(1, args.steps + 1):
        model.train()
        loss, base = loss_of(batch(train, args.crop))
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        if step % args.log_every == 0 or step == args.steps:
            msg = f"step {step}: loss {loss.item():.4f} (frames {base.item():.4f})"
            if held:
                model.eval()
                with torch.no_grad():
                    crop = int(min(args.crop, min(lengths[i] for i in held) - 1))
                    vals = [loss_of(batch(held, crop, jitter=0))[1].item() for _ in range(4)]
                    msg += f"; held out {np.mean(vals):.4f}"
                    by_singer = {}  # and each singer's held-out segments alone, when there are several
                    for i in held:
                        by_singer.setdefault(singers[int(d["singer"][offsets[i]])], []).append(i)
                    if len(by_singer) > 1:
                        for name, ids in sorted(by_singer.items()):
                            c = int(min(args.crop, min(lengths[i] for i in ids) - 1))
                            msg += f" ({name} {np.mean([loss_of(batch(ids, c, jitter=0))[1].item() for _ in range(4)]):.4f})"
            print(f"{msg}; {time.time() - t0:.0f} s", flush=True)

    # global variance: how much real envelopes vary within a segment, against how much predicted ones do
    model.eval()
    real_var, pred_var = [], []
    with torch.no_grad():
        for i in train[:: max(1, len(train) // 40)]:
            sl = slice(offsets[i], offsets[i] + lengths[i])
            tt = lambda arr, dtype=torch.float32: torch.tensor(arr[sl][None], dtype=dtype, device=dev)  # noqa: E731
            pred = model(tt(phone5, torch.long), tt(d["role"], torch.long), tt(cont_all), model.singer(tt(d["singer"], torch.long)))
            pred = pred[0].cpu().numpy()
            m = full[sl] & (d["role"][sl] >= 2)
            if m.sum() < 50:  # a band-limited recording's segment: its upper points aren't real
                continue
            real_var.append(y_all[sl][m].var(0))
            pred_var.append(pred[m].var(0))
    gv = np.mean(real_var, axis=0) / np.maximum(np.mean(pred_var, axis=0), 1e-6)
    print(f"global variance, real over predicted: envelope median {np.median(gv[:sp.shape[1]]):.2f}, "
          f"aperiodicity {np.median(gv[sp.shape[1]:]):.2f}", flush=True)

    # each singer's register: the median pitch it sang (MIDI), so a machine's voice can be mixed from
    # the singers who sing where it sings
    voiced = mask & (d["role"] == 3)
    old_registers = json.loads(str(init["config"])).get("registers", {}) if init is not None else {}
    registers = {name: (float(69 + 12 * np.log2(np.exp(np.median(d["lf0"][voiced & (d["singer"] == i)])) / 440.0))
                        if (voiced & (d["singer"] == i)).any() else old_registers[name])
                 for i, name in enumerate(singers)}
    weights = {k: v.detach().cpu().numpy().astype(np.float32) for k, v in model.state_dict().items()}
    config = dict(channels=args.channels, dilations=list(DILATIONS), kernel=KERNEL, embed=EMBED, role=ROLE,
                  dropout=args.dropout, noise=args.noise,
                  singer=SINGER, cont=CONT, phones=phones, roles=roles, singers=singers, steps=args.steps,
                  registers=registers, sources=dict(zip(singers, sources)),
                  dataset=str(args.dataset), frames=int(len(sp)), params=int(n_params), held_out=args.hold_out or [],
                  excluded=args.exclude or [],
                  lr=args.lr, init=str(args.init) if args.init else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.out, config=json.dumps(config), sp_mean=sp_mean, sp_std=sp_std, ap_mean=ap_mean, ap_std=ap_std,
             gv=gv.astype(np.float32), **{f"w.{k}": v for k, v in weights.items()})
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
