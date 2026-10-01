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

For real people's recordings (docs/THROAT.md, "Folk singers"): --singer-dim widens the singer embedding (an old
model's rows keep their numbers, the new dimensions start small and random); --spread starts a new singer at a
random point spread as the old singers are, not at their mean (where the folk singers all stayed, one voice);
--singer-lr learns the singer table (and the recording table) faster, without weight decay; --channel-dim gives
every recording of a "folk" or "record" singer a row of its own beside the singer's (its microphone and room), the
house audio one shared row, "studio", and the model written sings through "studio" (folded into the FiLM biases,
so songbird.synth.throat runs it unchanged); --contrast adds L1 on the envelope less its 17-point trend (log
power, inside the band), which keeps formant contrast a small model would average away; --rhotic-from-house learns
an R after a vowel only from the house audio (people's folk singing mostly drops it).

Against the average (docs/THROAT.md, "Folk singers", round 3): --adversarial trains a critic beside the throat, a
small 2-D convolution over a patch of frames and grid points of the envelope (log power to 5.6 kHz, CRITIC_TOP, each
frame's mean taken out) that learns to tell the real singer's from the throat's, and the throat learns to make it fail
(least squares, and the critic's own features matched on the same frames, each layer's relative to its size,
--feature-match); only frames whose band reaches CRITIC_TOP count, and the written model is the throat alone.
--share FRAGMENT=FRACTION draws that fraction of every batch from the segments whose names hold FRAGMENT. --init a model narrower than --channels widens it, every new channel starting
where it changes nothing the old model sang, so a bigger throat fine-tunes from the house model too. With
--channel-dim the room's FiLM weights are written beside the folded model (room_film.K), so a room can be fitted
for a recording it never heard (tools/throat/unseen.py).
"""

from __future__ import annotations

import argparse
import contextlib
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
CRITIC_TOP = 96  # grid points the critic judges (to 5.6 kHz): nearly every folk recording's band reaches it, few reach 128


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
    def __init__(self, phones: int, roles: int, singers: int, channels: int, sp: int, ap: int, dropout: float = 0.0,
                 singer_dim: int = SINGER, rooms: int = 0, room_dim: int = 0):
        super().__init__()
        self.drop = nn.Dropout(dropout)
        self.phone = nn.Embedding(phones, EMBED)
        self.role = nn.Embedding(roles, ROLE)
        self.singer = nn.Embedding(singers, singer_dim)
        self.room = nn.Embedding(rooms, room_dim) if room_dim else None
        self.inp = nn.Linear(5 * EMBED + ROLE + CONT, channels)
        self.convs = nn.ModuleList([nn.Linear(KERNEL * channels, channels) for _ in DILATIONS])
        self.films = nn.ModuleList([nn.Linear(singer_dim + room_dim, 2 * channels) for _ in DILATIONS])
        self.mixes = nn.ModuleList([nn.Linear(channels, channels) for _ in DILATIONS])
        for f, m in zip(self.films, self.mixes):
            nn.init.zeros_(f.weight)
            nn.init.zeros_(f.bias)
            m.weight.data *= 0.3
            nn.init.zeros_(m.bias)
        self.out = nn.Linear(channels, sp + ap)

    def voice(self, singer: torch.Tensor, room: torch.Tensor | None = None) -> torch.Tensor:
        """What the FiLMs read: the singer's row, and the recording's beside it when there are rooms."""
        v = self.singer(singer)
        return torch.cat([v, self.room(room)], dim=-1) if self.room is not None else v

    def forward(self, phones: torch.Tensor, role: torch.Tensor, cont: torch.Tensor, singer: torch.Tensor):
        """phones (batch, frames, 5): prev2, prev, phone, next, next2; singer (batch, frames, SINGER)."""
        e = self.phone(phones).flatten(2)
        x = self.inp(torch.cat([e, self.role(role), cont], dim=-1))
        for conv, film, mix, d in zip(self.convs, self.films, self.mixes, DILATIONS):
            gamma, beta = film(singer).chunk(2, dim=-1)
            h = conv(shifted(x, d)) * (1.0 + gamma) + beta
            x = x + mix(self.drop(F.gelu(h, approximate="tanh")))
        return self.out(x)


class Critic(nn.Module):
    """Real envelope or the throat's? (batch, frames, points) -> a judgement for every frame and a quarter of the
    points' patch around it, and every layer's features. Spectral norm keeps it from winning too easily."""

    def __init__(self, ch: int = 32):
        super().__init__()
        sn = nn.utils.parametrizations.spectral_norm
        self.layers = nn.ModuleList([sn(nn.Conv2d(1, ch, 3, padding=1)),
                                     sn(nn.Conv2d(ch, 2 * ch, 3, stride=(1, 2), padding=(2, 1), dilation=(2, 1))),
                                     sn(nn.Conv2d(2 * ch, 2 * ch, 3, stride=(1, 2), padding=(4, 1), dilation=(4, 1))),
                                     sn(nn.Conv2d(2 * ch, 2 * ch, 3, padding=(8, 1), dilation=(8, 1)))])
        self.out = sn(nn.Conv2d(2 * ch, 1, 3, padding=1))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, list[torch.Tensor]]:
        h, feats = x[:, None], []
        for layer in self.layers:
            h = F.leaky_relu(layer(h), 0.2)
            feats.append(h)
        return self.out(h)[:, 0], feats


def widened(k: str, w: torch.Tensor, new: torch.Tensor, c: int) -> torch.Tensor:
    """An old model's weight k, c channels wide, in a wider model's place (new: that model's fresh weight): the old
    numbers where they were, so it sings as the old one did. The new channels of the running sum start at zero
    (nothing writes into them yet, but every layer and the output read them, so they learn); the new units of a
    layer read the old ones but write nothing back yet."""
    out = new.detach().cpu().clone()
    if k.startswith("inp."):
        out.zero_()
        out[:c] = w
    elif k.startswith("convs.") and k.endswith(".weight"):
        C = new.shape[0]
        for j in range(KERNEL):  # [x d back | x | x d on], each block C wide now
            out[:c, j * C: j * C + c] = w[:, j * c: (j + 1) * c]
    elif k.startswith("convs."):
        out[:c] = w
    elif k.startswith("mixes.") and k.endswith(".weight"):
        out.zero_()
        out[:c, :c] = w
    elif k.startswith("mixes."):
        out.zero_()
        out[:c] = w
    elif k.startswith("films."):  # [gamma | beta], each C wide now; the new units' FiLM starts at nothing, as a FiLM does
        C = new.shape[0] // 2
        out.zero_()
        out[:c], out[C: C + c] = w[:c], w[c:]
    elif k == "out.weight":
        out[:, :c] = w
    else:
        out = w
    return out


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
    ap.add_argument("--singer-dim", type=int, default=None, help="numbers per singer (default: the --init model's, or 8)")
    ap.add_argument("--spread", action="store_true", help="a new singer starts spread as the old ones are, not at their mean")
    ap.add_argument("--singer-lr", type=float, default=None, help="learning rate of the singer and room tables (no decay)")
    ap.add_argument("--channel-dim", type=int, default=0, help="numbers per recording (its room and microphone); 0: none")
    ap.add_argument("--contrast", type=float, default=0.0, help="weight of L1 on the envelope less its trend")
    ap.add_argument("--rhotic-from-house", action="store_true",
                    help="learn an R after a vowel (and ER, AYR, AWR, OYR) only from the house audio, not from people's")
    ap.add_argument("--adversarial", type=float, default=0.0, help="weight of fooling the critic (0: no critic)")
    ap.add_argument("--feature-match", type=float, default=None,
                    help="weight of matching the critic's features on real and predicted (default: twice --adversarial)")
    ap.add_argument("--critic-lr", type=float, default=2e-4)
    ap.add_argument("--share", nargs="*", default=[], metavar="FRAGMENT=FRACTION",
                    help="the segments whose names hold FRAGMENT are this fraction of every batch (else as many as any)")
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
    if args.rhotic_from_house:  # the folk singing is mostly non-rhotic (hymn and art-song diction, British and Irish
        # singers: F3 under a coda R 2.66 kHz against the house corpus's 2.31): learned from it, "fire" sang "fi"
        people = np.array([s in ("folk", "record") for s in sources])[d["singer"].astype(np.int64)]
        rhotic = np.isin(d["phone"], [phones.index(p) for p in ("ER", "AYR", "AWR", "OYR") if p in phones])
        rhotic |= (d["phone"] == phones.index("R")) & (d["role"] == 4)
        mask = mask & ~(people & rhotic)
        print(f"rhotic frames of people's singing left out: {int((people & rhotic).sum())}", flush=True)
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

    # rooms: every recording of a person (source folk or record) its own, the rest one shared "studio"
    rooms = ["studio"]
    room_of = np.zeros(len(sp), dtype=np.int64)
    if args.channel_dim:
        for i, seg in enumerate(segments):
            who, _, name = seg.partition("/")
            if sources[singers.index(who)] in ("folk", "record") if who in singers else False:
                rec = name.rsplit(".s", 1)[0].split("~")[0]  # a recording's room is before a "~" (VocalSet's: the singer's)
                if rec not in rooms:
                    rooms.append(rec)
                room_of[offsets[i]: offsets[i] + lengths[i]] = rooms.index(rec)
        print(f"{len(rooms)} rooms (studio and {len(rooms) - 1} recordings)", flush=True)

    dev = args.device
    old = json.loads(str(init["config"])) if init is not None else None
    sdim = args.singer_dim or (old.get("singer", SINGER) if old else SINGER)
    model = Throat(len(phones), len(roles), len(singers), args.channels, sp.shape[1], apr.shape[1], args.dropout,
                   singer_dim=sdim, rooms=len(rooms), room_dim=args.channel_dim).to(dev)
    gen = torch.Generator().manual_seed(args.seed)
    if init is not None:
        if old["channels"] > args.channels or old["phones"] != phones:
            raise SystemExit(f"--init {args.init}: {old['channels']} channels and its phones; asked for {args.channels}")
        state = model.state_dict()
        for k in state:
            if k == "room.weight":
                continue
            w = torch.tensor(init[f"w.{k}"])
            if args.channels > old["channels"]:  # the singer's new numbers, if any, are added below
                fresh = state[k][:, : w.shape[1]] if k.startswith("films.") and k.endswith(".weight") else state[k]
                w = widened(k, w, fresh, old["channels"])
            if k == "singer.weight":  # by name; a new singer starts at the old ones' mean (or spread as they are)
                mean, std = w.mean(0), w.std(0)
                rows = [w[old["singers"].index(n)] if n in old["singers"]
                        else mean + (std * torch.randn(len(mean), generator=gen) if args.spread else 0) for n in singers]
                w = torch.stack(rows)
                if sdim > w.shape[1]:  # wider: the new numbers start small and random (their FiLM weights at zero)
                    w = torch.cat([w, 0.3 * std.mean() * torch.randn(len(w), sdim - w.shape[1], generator=gen)], dim=1)
            elif k.startswith("films.") and k.endswith(".weight") and state[k].shape[1] > w.shape[1]:
                w = torch.cat([w, torch.zeros(w.shape[0], state[k].shape[1] - w.shape[1])], dim=1)
            state[k] = w
        if model.room is not None:  # rooms start small and random, their FiLM weights at zero
            state["room.weight"] = 0.3 * torch.randn(len(rooms), args.channel_dim, generator=gen)
        model.load_state_dict(state)
        print(f"from {args.init}: singers {[n for n in singers if n not in old['singers']]} new", flush=True)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"{n_params / 1e6:.2f}M parameters, {sdim} numbers a singer", flush=True)
    tables = [model.singer.weight] + ([model.room.weight] if model.room is not None else [])
    rest = [p for n, p in model.named_parameters() if n not in ("singer.weight", "room.weight")]
    opt = torch.optim.AdamW([dict(params=rest), dict(params=tables, lr=args.singer_lr or args.lr,
                                                      weight_decay=0.0 if args.singer_lr else 1e-4)],
                            lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, s / 500) * 0.5 * (1 + math.cos(math.pi * s / args.steps)))

    shares = [(frag, float(f)) for frag, f in (x.split("=") for x in args.share)]
    pools = [[i for i in train if frag in segments[i]] for frag, _ in shares]
    rest_pool = [i for i in train if not any(frag in segments[i] for frag, _ in shares)]
    for (frag, f), pool in zip(shares, pools):
        print(f"{len(pool)} training segments hold {frag!r}: {f:.0%} of every batch", flush=True)

    def pick(ids):
        """A segment: from a --share pool by its fraction (training batches only), else any."""
        if shares and ids is train:
            u = rng.random()
            for (_, f), pool in zip(shares, pools):
                if u < f and pool:
                    return pool[rng.integers(len(pool))]
                u -= f
            return rest_pool[rng.integers(len(rest_pool))]
        return ids[rng.integers(len(ids))]

    def batch(ids, crop, jitter=JITTER):
        xs, ys = [], []
        for _ in range(args.batch):
            i = pick(ids)
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
                t(y_all, ys), t(mask, ys), bands, t(room_of, ys, torch.long))

    dims_sp = torch.arange(n_sp, device=dev)
    dims_ap = torch.arange(n_ap, device=dev)

    sp_std_t = torch.tensor(sp_std, device=dev)
    sp_mean_t = torch.tensor(sp_mean, device=dev)
    hann = torch.hann_window(19, periodic=False, device=dev)[1:-1]
    hann = (hann / hann.sum()).view(1, 1, -1)

    def detrended(v):
        """(batch, frames, sp) log power less its 17-point trend along frequency (the edges held)."""
        flat = v.reshape(-1, 1, v.shape[-1])
        trend = F.conv1d(F.pad(flat, (8, 8), mode="replicate"), hann).reshape(v.shape)
        return v - trend

    def loss_of(xb, critic_too=False):
        phone, role, cont, singer, y, m, bands, room = xb
        pred = model(phone, role, cont, model.voice(singer, room))
        m3 = m[..., None] * bands  # each frame's points inside its band (every point, but for old records)
        base = ((pred - y).abs() * m3).sum() / (m3.sum() + 1e-6)
        dm = m[:, 1:, None] * m[:, :-1, None] * bands[:, 1:] * bands[:, :-1]
        delta = (((pred[:, 1:] - pred[:, :-1]) - (y[:, 1:] - y[:, :-1])).abs() * dm).sum() / (dm.sum() + 1e-6)
        loss = base + args.delta * delta
        if args.contrast:  # the formants' height over the envelope's trend, as the real singer had it
            ps, ys_ = (v[..., :n_sp] * sp_std_t + sp_mean_t for v in (pred, y))
            mc = m3[..., :n_sp]
            c = ((detrended(ps) - detrended(ys_)).abs() * mc).sum() / (mc.sum() + 1e-6) / sp_std_t.mean()
            loss = loss + args.contrast * c
        if critic_too:
            return loss, base, pred, y, m * (bands[..., CRITIC_TOP - 1] > 0)  # the frames the critic judges
        return loss, base

    critic = Critic().to(dev) if args.adversarial else None
    # the critic's 2-D convolutions are most of a step's work: in bfloat16 on a GPU (its judgements and losses in float)
    fast = (lambda: torch.autocast("cuda", dtype=torch.bfloat16)) if str(dev).startswith("cuda") else contextlib.nullcontext
    if str(dev).startswith("cuda"):
        torch.backends.cudnn.benchmark = True
    fm_weight = 2 * args.adversarial if args.feature_match is None else args.feature_match
    if critic is not None:
        copt = torch.optim.Adam(critic.parameters(), lr=args.critic_lr, betas=(0.5, 0.9))
        print(f"critic: {sum(p.numel() for p in critic.parameters()) / 1e3:.0f}k parameters, adversarial {args.adversarial}, "
              f"features {fm_weight}", flush=True)

    def judged(v):
        """What the critic sees of an envelope (normalised, as the throat writes it): log power up to CRITIC_TOP,
        each frame's mean out, about unit scale."""
        ps = v[..., :CRITIC_TOP] * sp_std_t[:CRITIC_TOP] + sp_mean_t[:CRITIC_TOP]
        return (ps - ps.mean(-1, keepdim=True)) / 3.0

    def masked(v, w):
        """Mean of v (batch, frames, ...) over the frames w (batch, frames) counts."""
        w = w.reshape(w.shape + (1,) * (v.dim() - 2)).expand_as(v)
        return (v * w).sum() / (w.sum() + 1e-6)

    t0 = time.time()
    for step in range(1, args.steps + 1):
        model.train()
        if critic is None:
            loss, base = loss_of(batch(train, args.crop))
        else:
            loss, base, pred, y, judge = loss_of(batch(train, args.crop), critic_too=True)
            fake = judged(pred)
            real = torch.where(judge[..., None] > 0, judged(y), fake.detach())  # elsewhere both the same: nothing to tell
            with fast():
                d_real, _ = critic(real)
                d_fake, _ = critic(fake.detach())
            d_real, d_fake = d_real.float(), d_fake.float()
            c_loss = masked((d_real - 1) ** 2, judge) + masked(d_fake ** 2, judge)
            copt.zero_grad()
            c_loss.backward()
            copt.step()
            ramp = min(1.0, step / 1000)  # the critic finds its feet before the throat answers it
            critic.requires_grad_(False)  # the throat's step: the critic's gradients would only be thrown away
            with fast():
                d_fake, f_fake = critic(fake)
                with torch.no_grad():
                    _, f_real = critic(real)
            d_fake, f_fake, f_real = d_fake.float(), [f.float() for f in f_fake], [f.float() for f in f_real]
            critic.requires_grad_(True)
            adv = masked((d_fake - 1) ** 2, judge)
            # each layer's features matched relative to their own size (a spectral-normed critic's are small: unscaled,
            # the match would weigh nothing)
            fm = sum(masked((a - b).abs().mean(1), judge) / (masked(b.abs().mean(1), judge) + 1e-6)
                     for a, b in zip(f_fake, f_real)) / len(f_fake)
            loss = loss + ramp * (args.adversarial * adv + fm_weight * fm)
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        if step % args.log_every == 0 or step == args.steps:
            msg = f"step {step}: loss {loss.item():.4f} (frames {base.item():.4f})"
            if critic is not None:
                msg += f" critic {c_loss.item():.3f}, fooled {adv.item():.3f}, features {fm.item():.4f}"
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
            pred = model(tt(phone5, torch.long), tt(d["role"], torch.long), tt(cont_all),
                         model.voice(tt(d["singer"], torch.long), tt(room_of, torch.long)))
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
    room_table = weights.pop("room.weight", None)
    room_films = {}
    if room_table is not None:  # sing through the studio: its row folded into every FiLM's bias
        for k in range(len(DILATIONS)):
            w = weights[f"films.{k}.weight"]
            weights[f"films.{k}.bias"] = weights[f"films.{k}.bias"] + w[:, sdim:] @ room_table[0]
            weights[f"films.{k}.weight"] = np.ascontiguousarray(w[:, :sdim])
            room_films[f"room_film.{k}"] = np.ascontiguousarray(w[:, sdim:])  # another room: bias + this @ (row - studio)
    config = dict(channels=args.channels, dilations=list(DILATIONS), kernel=KERNEL, embed=EMBED, role=ROLE,
                  dropout=args.dropout, noise=args.noise,
                  singer=sdim, cont=CONT, phones=phones, roles=roles, singers=singers, steps=args.steps,
                  spread=args.spread, singer_lr=args.singer_lr, rooms=len(rooms), room_dim=args.channel_dim,
                  room_folded="studio" if args.channel_dim else None, contrast=args.contrast,
                  adversarial=args.adversarial, share=args.share, feature_match=fm_weight if args.adversarial else 0.0,
                  widened_from=old["channels"] if old and old["channels"] < args.channels else None,
                  registers=registers, sources=dict(zip(singers, sources)),
                  dataset=str(args.dataset), frames=int(len(sp)), params=int(n_params), held_out=args.hold_out or [],
                  excluded=args.exclude or [],
                  lr=args.lr, init=str(args.init) if args.init else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    extra = dict(rooms=np.array(rooms), room_table=room_table, **room_films) if room_table is not None else {}
    np.savez(args.out, config=json.dumps(config), sp_mean=sp_mean, sp_std=sp_std, ap_mean=ap_mean, ap_std=ap_std,
             gv=gv.astype(np.float32), **{f"w.{k}": v for k, v in weights.items()}, **extra)
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
