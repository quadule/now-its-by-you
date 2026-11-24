"""throat/: the learned throat's frames for each of the 11 calls the render made (renders/promo/capture/sing-*.pkl,
kept by tools/promo/capture.py), the singer embeddings, the weights as one picture and what they add through verse 1.

    uv run python tools/promo/video/prep/throat.py

Per call (DATA.md, "throat/"): the spectral envelope as tools/promo/throat_line.py computes it (throat.predict,
then throat.sharpen and dB), aperiodicity, log f0, voiced and silent flags, the phone segments; which take it is
and which seconds of it are heard (the stage plan's splice)."""
from __future__ import annotations

import pickle
import sys

import numpy as np

import common
from common import r

sys.path.insert(0, str(common.guard(common.ROOT / "tools/promo")))
import singer_picture  # noqa: E402

RATE = 200  # model frames a second (throat.FRAME = 5 ms)
ENV_OFFSET, ENV_SCALE = -126.0, 0.5  # dB = v * 0.5 - 126 (the envelope spans about -125 to +1 dB)
ACT_FPS = 60  # frames a second of act-verse1
VERSE1 = (10.9125, 30.9125)


def load(i: int) -> dict:
    with open(common.guard(common.CAPTURE / f"sing-{i:03d}.pkl"), "rb") as f:
        return pickle.load(f)


def identify(model, score) -> list[dict]:
    """Which take each call is. A choir call's notes are its part's; a lead call is the take whose notes it sang
    (stage plan "takes"), told apart where notes are alike by the people's share in its singer embedding: the
    embedding moves along the line from the human-0 take's toward the "volunteers" row as the share grows."""
    takes = score.stage["takes"]
    people = model.w["singer.weight"][model.config["singers"].index("volunteers")]
    caps = []
    for i in range(11):
        c = load(i)
        caps.append({"i": i, "part": c["notes"][0]["part"], "singer": np.array(c["singer"]),
                     "starts": np.array([n["start"] for n in c["notes"]])})
    plain = next(c for c in caps if c["part"] == "voice"
                 and np.allclose(c["starts"], [n.start for n in takes[0.0]["notes"]], atol=1e-9))
    e0 = plain["singer"]
    out = []
    for c in caps:
        if c["part"] != "voice":
            out.append({"call": c["i"], "kind": "choir", "part": c["part"], "id": c["part"], "human": None,
                        "share": None, "singer": c["singer"]})
            continue
        share = float((c["singer"] - e0) @ (people - e0) / ((people - e0) @ (people - e0)))
        fits = [h for h, tk in takes.items() if len(tk["notes"]) == len(c["starts"])
                and np.allclose(c["starts"], [n.start for n in tk["notes"]], atol=1e-9)]
        h = min(fits, key=lambda h: abs(takes[h]["share"] - share))
        assert abs(takes[h]["share"] - share) < 0.01 or h == 0.0, (c["i"], share, fits)
        out.append({"call": c["i"], "kind": "lead", "part": "voice", "id": f"lead-{h:.2f}", "human": float(h),
                    "share": float(takes[h]["share"]), "share_measured": r(share, 4), "k": float(takes[h]["k"]),
                    "singer": c["singer"]})
    assert len({o["id"] for o in out}) == 11
    return out


def heard_spans(score, takes_info) -> dict:
    """Seconds of each call that are heard: a lead take from its plan time to the next (stage.spliced, 30 ms fades
    at each join); a choir voice where its part sings."""
    plan = score.stage["plan"]
    spans = {}
    for k, (t, h) in enumerate(plan):
        a = 0.0 if k == 0 else t
        b = plan[k + 1][0] if k + 1 < len(plan) else common.DURATION
        spans.setdefault(f"lead-{h:.2f}", []).append([r(a), r(b)])
    for o in takes_info:
        if o["kind"] == "choir":
            notes = score.part(o["part"])
            spans[o["id"]] = [[r(min(n.start for n in notes)), r(max(n.start + n.dur for n in notes))]]
    return spans


def segments(phones: np.ndarray, notes: list[dict], names) -> list[list]:
    """Runs of one phone: [phone, t0, t1, note index or -1]. A phone belongs to the note sounding at its middle,
    reaching 0.12 s before the note's start for its leading consonants; silence and breath belong to none."""
    edges = np.flatnonzero(np.diff(phones)) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [len(phones)]])
    on = np.array([n["start"] - 0.12 for n in notes])
    off = np.array([n["start"] + n["dur"] for n in notes])
    out = []
    for a, b in zip(starts, ends):
        name = names[int(phones[a])]
        mid = (a + b) / 2 / RATE
        k = -1
        if name not in ("sil", "breath"):
            hit = np.flatnonzero((on <= mid) & (mid < off))
            k = int(hit[-1]) if len(hit) else int(np.argmin(np.abs(on + 0.12 - mid)))
        out.append([name, r(a / RATE, 3), r(b / RATE, 3), k])
    return out


def frames(model, cap) -> dict:
    """throat_line.py's envelope (dB) and the network's aperiodicity, log f0 and flags, one row a 5 ms frame."""
    from songbird.synth import throat

    sp, ap = throat.predict(model, cap["t"], cap["lf0"], cap["singer"], gv=1.0, last=cap["last"])
    sp = throat.sharpen(sp, throat.SHARPEN) * (10.0 / np.log(10.0))
    names = [throat.PHONES[int(p)] for p in cap["t"]["phone"]]
    voiced = np.array([p not in throat.UNVOICED for p in names])
    silent = np.array([p in ("sil", "breath") for p in names])
    return {"env": np.clip(np.round((sp - ENV_OFFSET) / ENV_SCALE), 0, 255).astype(np.uint8),
            "ap": np.clip(np.round(ap * 255), 0, 255).astype(np.uint8),
            "lf0": np.asarray(cap["lf0"], np.float32),
            "flags": (voiced.astype(np.uint8) | (silent.astype(np.uint8) << 1))}


def write_take(o: dict, f: dict, cap: dict, heard: list) -> None:
    from songbird.synth import throat

    tid = o["id"]
    n = len(f["env"])
    common.write_array(f"throat/{tid}.env", f["env"], rate=RATE, t0=0.0, scale=ENV_SCALE, offset=ENV_OFFSET,
                       about="spectral envelope, dB, 128 points from 40 Hz to 11.8 kHz (throat.grid), as "
                             "throat_line.py draws it: throat.predict then throat.sharpen(1.5)",
                       freqs=[r(x, 1) for x in throat.grid(f["env"].shape[1])])
    common.write_array(f"throat/{tid}.ap", f["ap"], rate=RATE, t0=0.0, scale=1 / 255, offset=0.0,
                       about="aperiodicity 0..1 (how much is breath), 32 points across the same band")
    common.write_array(f"throat/{tid}.lf0", f["lf0"], rate=RATE, t0=0.0,
                       about="log f0 (natural log of Hz) the throat was told, as sung (exp it for Hz)")
    common.write_array(f"throat/{tid}.flags", f["flags"], rate=RATE, t0=0.0,
                       about="bit 0: voiced (the phone is not in throat.UNVOICED); bit 1: silence or breath")
    notes = [{"t": r(x["start"]), "d": r(x["dur"]), "p": x["pitch"], "syl": x.get("syllable"), "word": x.get("word"),
              "line_end": x.get("line_end")} for x in cap["notes"]]
    common.write_json(f"throat/{tid}.phones.json", {
        "id": tid, "frames": n, "rate": RATE,
        "segments": segments(np.asarray(cap["t"]["phone"]), cap["notes"], throat.PHONES),
        "segment_fields": ["phone", "t0", "t1", "note"], "notes": notes, "heard": heard})


def picture(model) -> tuple[np.ndarray, list[dict]]:
    """Every weight where singer_picture.layout() puts it (its tiles(): a conv's three taps as three squares), on a
    canvas cropped to the weights; NaN where no weight is."""
    w = model.w
    at = singer_picture.layout(w)
    pieces = [(n, x, y, p) for n, v in w.items() for x, y, p in singer_picture.tiles(n, v, at[n])]
    x0 = min(x for _, x, _, _ in pieces)
    y0 = min(y for _, _, y, _ in pieces)
    x1 = max(x + p.shape[1] for _, x, _, p in pieces)
    y1 = max(y + p.shape[0] for _, _, y, p in pieces)
    img = np.full((y1 - y0, x1 - x0), np.nan, np.float32)
    rects = []
    drawn = 0
    for k, (n, x, y, p) in enumerate(pieces):
        img[y - y0: y - y0 + p.shape[0], x - x0: x - x0 + p.shape[1]] = p
        rects.append({"name": n, "tile": sum(1 for q in pieces[:k] if q[0] == n), "x": x - x0, "y": y - y0,
                      "w": int(p.shape[1]), "h": int(p.shape[0])})
        drawn += p.size
    assert drawn == model.config["params"] == 886372
    return img, rects, (x0, y0)


def activations(model, caps: dict, plan) -> tuple[np.ndarray, list[dict], dict]:
    """singer_picture.py's adding(), factored: each weight's contribution at a frame is the weight times one number
    of a vector (a column's input for inp/out/convs/mixes, a row's count for phone/role, the singer's eight for
    films). These vectors, averaged over each 1/60 s as adding() averages over a video frame, for verse 1 as heard
    (the take the stage plan has there)."""
    from songbird.synth import throat

    w = model.w
    names = ["inp", "out"] + [f"convs.{i}" for i in range(8)] + [f"mixes.{i}" for i in range(8)]
    n_frames = int(round((VERSE1[1] - VERSE1[0]) * ACT_FPS))
    step = 1.0 / ACT_FPS / throat.FRAME
    f0 = int(VERSE1[0] / throat.FRAME)
    f1 = int(VERSE1[1] / throat.FRAME)
    seen_by = {}
    for tid, cap in caps.items():
        lo, hi = max(0, f0 - 400), min(len(cap["lf0"]), f1 + 400)
        cont = throat.continuous(cap["t"], cap["lf0"])
        t = {k: v[lo:hi] for k, v in cap["t"].items()}
        _, seen = singer_picture.forward(model, t, cont[lo:hi], cap["singer"])
        seen_by[tid] = (lo, seen, np.asarray(cap["singer"]))
    cols = []
    for nm in names:
        cols.append((nm, seen_by[next(iter(seen_by))][1][nm].shape[1]))
    cols += [("phone", len(w["phone.weight"])), ("role", len(w["role.weight"])), ("singer", 8)]
    width = sum(c for _, c in cols)
    out = np.zeros((n_frames, width), np.float32)
    which = []
    for k in range(n_frames):
        t_now = VERSE1[0] + (k + 0.5) / ACT_FPS
        h = [h for t, h in plan if t <= t_now][-1] if plan[0][0] <= t_now else plan[0][1]
        tid = f"lead-{h:.2f}"
        which.append(tid)
        lo, seen, singer = seen_by[tid]
        i0 = int(round(f0 - lo + k * step))
        i1 = int(round(f0 - lo + (k + 1) * step))
        row = [seen[nm][i0:i1].mean(axis=0) for nm in names]
        phone = np.bincount(seen["phones"][i0:i1].ravel(), minlength=len(w["phone.weight"])) / (5.0 * (i1 - i0)) * 3
        role = np.bincount(seen["role"][i0:i1], minlength=len(w["role.weight"])) / float(i1 - i0)
        out[k] = np.concatenate(row + [phone, role, singer])
    layout, at = [], 0
    for nm, c in cols:
        layout.append({"vector": nm, "from": at, "to": at + c})
        at += c
    # one scale per array as singer_picture.py sets it: the 99.5th percentile of |weight x input| over every 6th frame (light_scale)
    scale = {}
    sample = out[::6]
    for nm, c in cols:
        sl = next(x for x in layout if x["vector"] == nm)
        vec = sample[:, sl["from"]: sl["to"]]
        if nm in ("phone", "role"):
            arr = np.abs(w[f"{nm}.weight"][None] * vec[:, :, None])
            key = f"{nm}.weight"
        elif nm == "singer":
            for i in range(8):
                scale[f"films.{i}.weight"] = float(max(np.percentile(np.abs(w[f"films.{i}.weight"][None] * vec[:, None, :]), 99.5), 1e-9))
            continue
        else:
            arr = np.abs(w[f"{nm}.weight"][None] * vec[:, None, :])
            key = f"{nm}.weight"
        scale[key] = float(max(np.percentile(arr, 99.5), 1e-9))
    return out, layout, {"scale": scale, "take": which}


def main() -> None:
    from songbird.synth import throat

    _, _, score = common.laid()
    model = throat.load()
    info = identify(model, score)
    heard = heard_spans(score, info)
    leads, plain_lf0 = {}, None
    for o in info:
        cap = load(o["call"])
        f = frames(model, cap)
        write_take(o, f, cap, heard[o["id"]])
        if o["kind"] == "lead":
            leads[o["id"]] = f["env"]
            if o["human"] == 0.0:
                plain_lf0 = f["lf0"], f["flags"]
        common.say(o["id"], f"call {o['call']}", f["env"].shape)
        del cap, f

    # the heard lead's envelope, spliced as stage.spliced joins the takes (each from its plan time; the 30 ms fades
    # are left out: a frame is the take coming in), and the human-0 take's f0 over the whole song
    n = int(np.ceil(common.DURATION * RATE))
    plan = score.stage["plan"]
    env = np.zeros((n, 128), np.uint8)
    take_of = np.zeros(n, np.uint8)
    times = np.arange(n) / RATE
    for k, (t, h) in enumerate(plan):
        a = 0 if k == 0 else int(np.ceil(t * RATE))
        b = int(np.ceil(plan[k + 1][0] * RATE)) if k + 1 < len(plan) else n
        src = leads[f"lead-{h:.2f}"]
        m = min(b, len(src))
        env[a:m] = src[a:m]
        take_of[a:b] = k
    common.write_array("throat/lead-heard.env", env, rate=RATE, t0=0.0, scale=ENV_SCALE, offset=ENV_OFFSET,
                       about="the heard lead's envelope (dB, 128 points), each frame from the take the stage plan has "
                             "there; zero (silence) after a take's last frame")
    common.write_array("throat/lead-heard.take", take_of, rate=RATE, t0=0.0,
                       about="index into takes.json 'plan': which take each frame of lead-heard.env is from")
    lf0, flags = plain_lf0
    pad = np.full(n, np.nan, np.float32)
    pad[: min(n, len(lf0))] = lf0[:n]
    fl = np.zeros(n, np.uint8)
    fl[: min(n, len(flags))] = flags[:n]
    common.write_array("throat/lead-0.00-whole.lf0", pad, rate=RATE, t0=0.0,
                       about="log f0 of the human-0 take (the machine alone, every note on the grid), the whole song; "
                             "NaN after its last frame")
    common.write_array("throat/lead-0.00-whole.flags", fl, rate=RATE, t0=0.0, about="as lead-0.00.flags, padded")

    names = model.config["singers"]
    retired = set(model.config.get("retired") or [])
    sources = model.config.get("sources") or {}
    common.write_json("throat/takes.json", {
        "calls": [{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in o.items()} for o in info],
        "plan": [{"t": r(t), "human": float(h), "id": f"lead-{h:.2f}"} for t, h in plan],
        "heard": heard,
        "rows": [{"name": nm, "source": sources.get(nm), "retired": nm in retired,
                  "embedding": [r(x, 5) for x in model.w["singer.weight"][i]]} for i, nm in enumerate(names)],
        "about": "calls: each captured call (sing-NNN.pkl) and the take it is, with the eight-number singer embedding "
                 "it sang with; rows: the model's singer table (throat.npz w.singer.weight), 'volunteers' the people's "
                 "row (source human); a take's embedding is its default blend with the volunteers row at its share"},
        indent=1)

    img, rects, origin = picture(model)
    common.write_array("throat/weights", img.astype(np.float16), about=(
        "every weight of the throat as one picture, placed as tools/promo/singer_picture.py layout()/tiles() place "
        "them (cropped: the canvas origin is singer_picture's pixel 'origin'); NaN where no weight is"),
        rects=rects, origin=list(origin), params=int(model.config["params"]))

    caps = {o["id"]: load(o["call"]) for o in info if o["id"] in {f"lead-{h:.2f}" for t, h in plan
                                                                  if t < VERSE1[1]}}
    vec, layout, extra = activations(model, caps, plan)
    vmax = float(np.abs(vec).max())
    common.write_array("throat/act-verse1", vec.astype(np.float16), rate=ACT_FPS, t0=VERSE1[0], about=(
        "singer_picture.py's adding() for verse 1, factored: contribution of weight W[i, j] of array A at frame k = "
        "W[i, j] * v[k, column j of A's vector] for inp/out/convs.n/mixes.n (vector named as the array without "
        ".weight), W[i, j] * v[k, row i of 'phone' or 'role'] for phone.weight/role.weight, and films.n.weight "
        "[i, j] * v[k, 'singer' j]; biases as they are; singer.weight 0. 'light_scale' is the per-array 99.5th "
        "percentile singer_picture uses to light a pixel: amount = clip(|contribution| / scale, 0, 1) ** 0.8"),
        layout=layout, light_scale=extra["scale"], take=sorted(set(extra["take"])),
        take_changes=[[r(VERSE1[0] + k / ACT_FPS), t] for k, t in enumerate(extra["take"])
                      if k == 0 or extra["take"][k - 1] != t], max_abs=vmax)
    common.say("act-verse1", vec.shape)


if __name__ == "__main__":
    main()
