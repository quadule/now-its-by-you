"""The instruments' own physics for the film, from the instrumented replay's captures (replay.py), written to
renders/promo/video/data/physics/.

    uv run python tools/promo/video/prep/physics.py [pluck strum drum body bow pipe analog chip drummachine reed]

With no names it writes them all. Every file is described in DATA.md ("Replay data"). Where a model's loop is
compiled (numba) and keeps its state in locals, an instrumented copy here runs the same arithmetic, also
keeping the state, and is checked against the engine's own output, sample for sample.
"""
from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np
from numba import njit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, SCRATCH, guard, read_json, say, write_array, write_json  # noqa: E402
from songbird.synth.analog import ATTACK_TARGET, COMP, CTRL, _ladder_step, _wave  # noqa: E402
from songbird.synth.bowed import _read  # noqa: E402
from songbird.synth.chip import _lfsr  # noqa: E402

CAP = guard(SCRATCH / "replay" / "capture")
PHYS = "physics"
SR = 44100
FPS = 60


def load(kind: str):
    with open(guard(CAP / f"{kind}.pkl"), "rb") as f:
        return pickle.load(f)


def r(x, n=6):
    return None if x is None else round(float(x), n)


def note_of(n: dict | None) -> dict | None:
    if n is None:
        return None
    return {"t": r(n["start"]), "d": r(n["dur"]), "p": r(n["pitch"], 3), "v": r(n["vel"], 4), "art": n["art"]}


# ---------------------------------------------------------------------------------------------- plucked strings


def loop_reference(x: np.ndarray, whole: int, taps, gain: float, release_at: int, release_gain: float,
                   length: int, smooth: float) -> np.ndarray:
    """pluck._loop in plain Python, as the browser runs it: y[n] = x[n] + g[n] sum_k taps[k] y[n - whole - k],
    g gliding from gain toward release_gain from sample release_at on, g <- rg + (g - rg) smooth."""
    taps = [float(t) for t in taps]
    nt = len(taps)
    pad = whole + nt
    y = [0.0] * (pad + length)
    g = gain
    nx = len(x)
    for n in range(length):
        if n >= release_at:
            g = release_gain + (g - release_gain) * smooth
        acc = float(x[n]) if n < nx else 0.0
        base = pad + n - whole
        fb = 0.0
        for k in range(nt):
            fb += taps[k] * y[base - k]
        y[pad + n] = acc + g * fb
    return np.array(y[pad:])


def pluck() -> None:
    """physics/pluck-<part>.json and its excitations (.bin): every plucked note's string planes."""
    recs = load("pluck")
    parts = sorted({r_["stem"] for r_ in recs})
    errors = {}
    for part in parts:
        mine = sorted((p for p in recs if p["stem"] == part), key=lambda p: (p["note"]["start"], p["note"]["pitch"]))
        exc, notes = [], []
        offset = 0
        for rec in mine:
            planes = []
            for j, pl in enumerate(rec["planes"]):
                x = pl["excitation"]
                exc.append(x.astype(np.float32))
                planes.append({"string": j // 2, "plane": "across" if j % 2 == 0 else "along", "lag": pl["lag"],
                               "f": r(pl["freq"], 6), "cents": r(pl["cents"], 4), "split": r(pl["split"], 4) if j % 2 else 0.0,
                               "N": pl["whole"], "taps": [float(t) for t in pl["taps"]], "g": float(pl["gain"]),
                               "rg": float(pl["release_gain"]), "smooth": float(pl["smooth"]), "held": pl["held"],
                               "len": pl["length"], "t60": r(pl["t60"]), "loss": r(pl["loss"]),
                               "x0": offset, "xn": int(len(x))})
                offset += len(x)
            n = rec["note"]
            notes.append({**note_of(n), "s": rec["start_sample"], "f": r(rec["freq"], 5), "tune": r(rec["tuning_cents"], 3),
                          "pick": r(rec.get("pick"), 5), "bright": r(rec.get("brightness"), 5),
                          "hard": r(rec.get("hardness"), 4), "mute": bool(rec.get("mute", False)),
                          "len": rec["length"], "planes": planes})
        # the reference: the captured parameters through loop_reference against the loop's own output
        for rec in mine:
            for pl in rec["planes"]:
                if "out" not in pl:
                    continue
                # the excitation as captured (float64), then as stored (float32): errors alternate in the list
                for x in (pl["excitation"], pl["excitation"].astype(np.float32).astype(np.float64)):
                    y = loop_reference(x, pl["whole"], pl["taps"], pl["gain"], pl["held"], pl["release_gain"],
                                       pl["length"], pl["smooth"])
                    peak = float(np.max(np.abs(pl["out"]))) or 1.0
                    errors.setdefault(part, []).append(float(np.max(np.abs(y - pl["out"]))) / peak)
        name = f"{PHYS}/pluck-{part}"
        write_array(name, np.concatenate(exc) if exc else np.zeros(0, np.float32),
                    about=f"every {part} pluck's one-period excitations, each plane's in turn (offsets x0, xn in "
                          f"{name}-notes.json)")
        write_json(f"{name}-notes.json", {
            "part": part, "sr": SR, "notes": notes,
            "loop": "y[n] = x[n] + g[n] * sum_k taps[k] * y[n - N - k], x the plane's excitation (0 past its end); "
                    "g = g0 until held, then g <- rg + (g - rg) * smooth each sample; the plane starts at the "
                    "note's sample s + lag and runs len samples",
            "check": {"max_rel_error_float64": max(errors.get(part, [0.0])[0::2] or [0.0]),
                      "max_rel_error_float32_excitation": max(errors.get(part, [0.0])[1::2] or [0.0]),
                      "planes_checked": len(errors.get(part, [])) // 2}})
        say(f"pluck {part}: {len(notes)} notes, {offset} excitation samples, reference error "
            f"{max(errors.get(part, [0.0])[0::2] or [0.0]):.2e} (float64) {max(errors.get(part, [0.0])[1::2] or [0.0]):.2e} (float32)")


# ---------------------------------------------------------------------------------------------- the strumming hand


def strokes_of(notes: list[dict]) -> list[list[dict]]:
    """A strummed part's notes as strokes, as instruments.pick_noise groups them: notes of one articulation
    starting within 45 ms of the stroke's first."""
    groups: list[list[dict]] = []
    for n in sorted((n for n in notes if n["art"] in ("down", "up", "mute")), key=lambda n: n["start"]):
        if groups and n["start"] - groups[-1][0]["start"] < 0.045 and n["art"] == groups[-1][0]["art"]:
            groups[-1].append(n)
        else:
            groups.append([n])
    return groups


def strum() -> None:
    """physics/strum.json: the guitar's strokes, each with the strings it met (their onsets a few ms apart) and
    the strumming hand's own stroke where the hand played it."""
    played = sorted((p for p in load("pluck") if p["stem"] == "guitar"), key=lambda p: p["note"]["start"])
    notes = [{**p["note"], "string_hz": p["freq"]} for p in played]
    runs = load("strum_runs")
    hand = runs[0] if runs else []
    groups = strokes_of(notes)
    out, h = [], 0
    unmatched_groups = 0
    for g in groups:
        pitches = [n["pitch"] for n in g]
        match = None
        # the hand's next stroke whose strings are these, in this order
        for k in range(h, min(h + 6, len(hand))):
            if [e["pitch"] for e in hand[k]["events"]] == pitches:
                match, h = hand[k], k + 1
                break
        if match is None:
            unmatched_groups += 1
        t0 = g[0]["start"]
        voiced = (match or {}).get("voiced") or {}
        strings = [p[0] if isinstance(p, list) else None for p, _, _ in voiced.get("played", [])]
        out.append({
            "t": r(t0), "dir": "up" if g[0]["art"] == "up" else "down", "chop": g[0]["art"] == "mute",
            "kind": match["kind"] if match else None, "accent": r(match["accent"], 3) if match else None,
            "flag": match["flag"] if match else None, "slot": match["slot"] if match else None,
            "slots": match["slots"] if match else None, "span": r(match["span"], 3) if match else None,
            "chord": match["chord"] if match else None,
            "strings": [{"p": r(n["pitch"], 2), "dt": r(n["start"] - t0), "v": r(n["vel"], 4), "d": r(n["dur"]),
                         "string": strings[i] if i < len(strings) else None} for i, n in enumerate(g)]})
    write_json(f"{PHYS}/strum.json", {
        "part": "guitar", "strokes": out,
        "about": "a stroke is the guitar's notes of one articulation (down, up, mute: a chop) starting within 45 ms "
                 "of its first, as the model groups them for the pick's noise; dt is each string's onset after the "
                 "stroke's first, in the order the pick met them, string 0 (low) to 5 (high) where the hand's data names it; kind/accent/flag/slot/span are the strumming hand's "
                 "own stroke (songbird.strumming.Stroke: D d U u x B b, accent 0..1, flag 'open' for the open strings "
                 "as the fretting hand lifts, slot of slots in the bar, span the section's reach) where the hand "
                 "played it, else null",
        "hand_strokes": len(hand), "matched": len(groups) - unmatched_groups, "strokes_total": len(groups)})
    say(f"strum: {len(groups)} strokes, {len(groups) - unmatched_groups} matched to the hand's {len(hand)}")


# ---------------------------------------------------------------------------------------------- the frame drum


def drum() -> None:
    """physics/drum.json and drum-modes.bin: the membrane's modes and, per hit, each mode as _ring received it."""
    from songbird.synth import drum as drum_mod

    modes = drum_mod.membrane()
    j01 = modes[0][2]
    m = np.array([a for a, _, _ in modes])
    hits = sorted(load("drum"), key=lambda h: h["note"]["start"])
    rows, out, worst = [], [], 0.0
    for h in hits:
        # the hit's own draws repeated from its generator's state: its place, then each mode's spread
        g = np.random.Generator(np.random.PCG64())
        g.bit_generator.state = h["rng_state"]
        radius = float(np.clip(drum_mod.STROKES.get(h["stroke"], drum_mod.STROKES["tip"])[0] + g.normal(0.0, 0.06), 0.0, 0.98))
        theta = g.uniform(0.0, np.pi)
        g.normal(0.0, 0.01)
        spread = g.uniform(0.8, 1.2, len(modes))
        assert radius == h["radius"] and theta == h["theta"], "the hit's draws didn't repeat"
        strike = h["shape"] * h["spectrum"] * spread  # the mode's amplitude at the strike, all directions
        amps = strike * np.cos(m * theta) * h["radiate"]
        worst = max(worst, float(np.max(np.abs(amps - h["amps"]))) / float(np.max(np.abs(h["amps"]))))
        rows.append(np.stack([h["amps"], h["t60s"], strike], axis=1))
        n = h["note"]
        out.append({**note_of(n), "stroke": h["stroke"], "r": r(radius), "theta": r(theta), "f0": r(h["f0"]),
                    "contact_ms": r(h["contact"] * 1e3, 4), "glide": r(h["glide"]), "glide_time": h["glide_time"],
                    "gain": h["gain"], "len": h["length"], "level": r(n["vel"], 4),
                    "choke": list(drum_mod.CHOKES[h["stroke"]]) if h["stroke"] in drum_mod.CHOKES else None})
    write_array(f"{PHYS}/drum-modes", np.array(rows, dtype=np.float32),
                about="per hit (as drum.json's hits), per mode (as its modes): [amp as _ring receives it (the sound "
                      "at the listening axis), T60 in seconds, the mode's amplitude at the strike]")
    write_json(f"{PHYS}/drum.json", {
        "part": "drum", "count": len(modes), "j01": j01,
        "modes": [{"m": a, "n": b, "j": r(j, 6), "ratio": r(j / j01, 6), "radiate": 1.0 if a == 0 else 0.45}
                  for a, b, j in modes],
        "hits": out,
        "sound": "the drum's ring is sum_k amp_k * exp(-6.9078 t / T60_k) * sin(2 pi f_k t), f_k = f0 * ratio_k "
                 "(the two lowest start glide higher and fall back with time constant glide_time), times gain; "
                 "a band of slap noise and the stick's click are added in the first 60 ms and 4 ms; a hit with a "
                 "choke [left, tau] (the hand pressed on the skin) multiplies what the earlier hits still ring by "
                 "left + (1 - left) * exp(-(t - its time) / tau); and the whole part is high-passed (first order) "
                 "at 0.7 times the skin's pitch",
        "skin": "z(rho, phi, t) = sum_k strike_k * J_m(j_k rho) * cos(m_k (phi - theta)) * exp(-6.9078 t / T60_k) * "
                "sin(2 pi f_k t), rho 0 at the centre to 1 at the rim, the stick landing at (r, theta); strike_k is "
                "J_m(j_k r) / |J_(m+1)(j_k)| (the mode's normalization) * the stick's contact filter * the hit's own "
                "spread; amp_k is strike_k * cos(m_k theta) * radiate_k (the sound heard along phi = 0)",
        "check": {"max_rel_error_amps_from_strike": worst}})
    say(f"drum: {len(modes)} modes, {len(out)} hits, amps rebuilt to {worst:.1e}")


# ---------------------------------------------------------------------------------------------- bodies


def bodies() -> None:
    """physics/body.json and body-<instrument>.bin: each instrument's body as the render built it: its named
    modes as the maker's seed moved them, and its impulse response's first 100 ms."""
    from songbird.synth import body as body_mod

    out = {}
    for b in load("body"):
        spec, size, seed = b["spec"], b["size"], b["seed"]
        rng = np.random.default_rng(seed)
        modes = []
        for freq, q, db in spec.modes:  # the same draws impulse_response makes for the named modes
            f = freq / size * np.exp(rng.normal(0.0, 0.025))
            qq = q * np.exp(rng.normal(0.0, 0.1))
            d = db + rng.normal(0.0, 0.7)
            modes.append({"hz": r(f, 3), "q": r(qq, 3), "db": r(d, 3), "t60": r(6.9078 * qq / (np.pi * f), 5)})
        lo, hi, count = spec.dense
        freqs = np.sort(np.exp(rng.uniform(np.log(lo / size), np.log(hi / size), count)))
        n = int(0.1 * b["sr"])
        name = b["stem"]
        write_array(f"{PHYS}/body-{name}", b["ir"][:n].astype(np.float32), rate=b["sr"],
                    about=f"the {name}'s body (body.{b['body']}): its impulse response, two microphones, first 100 ms")
        out[name] = {"body": b["body"], "seed": seed, "size": size, "modes": modes,
                     "plate_modes": {"count": int(count), "hz": [r(f, 2) for f in freqs], "q": list(spec.q),
                                     "tilt_db_per_octave": spec.tilt},
                     "direct": spec.direct, "lowcut": spec.lowcut, "highcut": spec.highcut,
                     "ir_seconds": spec.length, "ir": f"body-{name}.bin"}
    write_json(f"{PHYS}/body.json", {
        "bodies": out,
        "about": "each instrument's body as the render built it (synth/body.py impulse_response): the named low "
                 "modes moved by its maker's seed (Hz, Q, dB; T60 = 6.9078 Q / (pi f)), the scattered plate modes' "
                 "frequencies (each microphone hears its own mix of them), and a stem is the bridge force "
                 "convolved with the response"}, indent=1)
    say(f"body: {', '.join(out)}")


# ---------------------------------------------------------------------------------------------- the bow


@njit(cache=True, nogil=True)
def bow_traced(period, bridge_len, bow_v, grip, noise, pole, gain, w0, w1):
    """bowed.run with the same arithmetic in the same order, also keeping, for samples w0..w1, the waves the
    string's two delay lines meet at the bow: from_bridge, from_nut (arriving), v (what the bow adds)."""
    n = period.shape[0]
    size = 4096
    to_nut = np.zeros(size)
    to_bridge = np.zeros(size)
    out = np.zeros(n)
    m = w1 - w0
    fb_k = np.zeros(m)
    fn_k = np.zeros(m)
    v_k = np.zeros(m)
    lp = 0.0
    for t in range(n):
        lb = bridge_len[t]
        ln = period[t] - lb
        arriving = _read(to_bridge, t, lb)
        lp = (1.0 - pole) * arriving + pole * lp
        from_bridge = -gain * lp
        from_nut = -_read(to_nut, t, ln)
        v_string = from_bridge + from_nut
        v = 0.0
        if bow_v[t] != 0.0:
            dv = bow_v[t] - v_string + noise[t]
            r = np.abs(0.25 * dv / grip[t]) + 0.75
            r = r**-4.0
            if r > 1.0:
                r = 1.0
            v = dv * r
        to_nut[t % size] = from_bridge + v
        to_bridge[t % size] = from_nut + v
        out[t] = arriving
        if w0 <= t < w1:
            fb_k[t - w0] = from_bridge
            fn_k[t - w0] = from_nut
            v_k[t - w0] = v
    return out, fb_k, fn_k, v_k


def at_times(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    """x read at fractional sample times t (linear), 0 outside."""
    i = np.floor(t).astype(np.int64)
    f = t - i
    ok = (i >= 0) & (i + 1 < len(x))
    i = np.clip(i, 0, len(x) - 2)
    return np.where(ok, (1 - f) * x[i] + f * x[i + 1], 0.0)


def string_at(waves: dict, lb, ln, w0: int, times: np.ndarray, points: int, delay: float):
    """The string at fractional sample times (from the window's start): (velocity, displacement) at `points`
    places from the bridge (0) to the nut (1). On the bridge side, s samples of travel from the bow, the wave
    going out toward the bridge left the bow s samples ago (from_nut + v) and the one coming back reaches the bow
    s samples from now (from_bridge); on the nut side likewise (from_bridge + v going out, from_nut coming back).
    The bridge's loss filter sits at the bridge: its delay (`delay` samples, pole/(1 - pole)) is part of that
    side's round trip, so the bridge side is (bridge_len + delay) / 2 samples of travel long and the nut side
    (period - bridge_len) / 2. Displacement is each wave's running sum (the same, integrated) read the same way:
    velocity x samples, from the window's start."""
    x = (np.arange(points) + 0.5) / points
    i = np.clip(np.round(times).astype(np.int64), 0, len(lb) - 1)
    L = (lb[i] + delay) / 2.0
    N = ln[i] / 2.0
    place = x[None, :] * (L + N)[:, None]
    bridge_side = place < L[:, None]
    s_b = L[:, None] - place
    s_n = place - L[:, None]
    tt = times[:, None]
    out = []
    for kind in ("v", "y"):
        w = waves[kind]
        vb = at_times(w["out_b"], tt - s_b) + at_times(w["fb"], tt + s_b)
        vn = at_times(w["out_n"], tt - s_n) + at_times(w["fn"], tt + s_n)
        out.append(np.where(bridge_side, vb, vn))
    return out


BOW_RATE = 480  # string snapshots a second, near enough: one every SR // 480 samples
PERIOD_SHOTS = 16  # snapshots across one period at each video frame


def bow() -> None:
    """physics/bow-*: the fiddle's breath (breath 2, where it plays the tune) and its first phrase after: its control tracks, the string's
    velocity and displacement along its length (from the instrumented copy of bowed.run, checked equal)."""
    from songbird.synth import bowed

    z = np.load(guard(CAP / "bow-fiddle.npz"))
    notes = sorted(load("bow")[0]["notes"], key=lambda n: n["start"])
    sec = next(x for x in read_json(DATA / "timeline.json")["sections"] if x["id"] == "breath2")
    w0s, w1s = sec["t0"] - 0.1, sec["t1"] - 0.2  # the breath from just before its first note
    after = [n for n in notes if n["start"] >= w1s]
    end = w1s
    for k, n in enumerate(after):  # the first phrase after: up to its first rest of a quarter second or more
        end = n["start"] + n["dur"]
        if k + 1 < len(after) and after[k + 1]["start"] - end >= 0.25:
            break
    end = min(end, w1s + 3.0)  # the film shows the breath and the start of what follows
    w0, w1 = int(w0s * SR), int(np.ceil((end + 0.4) * SR))
    args = [np.ascontiguousarray(z[k]) for k in ("period", "bridge_len", "bow_v", "grip", "noise")]
    out, fb, fn, v = bow_traced(*args, float(z["pole"]), float(z["gain"]), 0, len(args[0]))
    assert np.array_equal(out, z["out"]), "the traced copy isn't bowed.run"
    engine = bowed.run(*args, float(z["pole"]), float(z["gain"]))
    assert np.array_equal(out, engine)
    fb, fn, v = fb[w0:w1], fn[w0:w1], v[w0:w1]
    vw = {"out_b": fn + v, "fb": fb, "out_n": fb + v, "fn": fn}
    yw = {k: np.cumsum(x) for k, x in vw.items()}
    period, lb = args[0][w0:w1], args[1][w0:w1]
    d = bowed._FILTER_DELAY
    m = w1 - w0
    every = SR // BOW_RATE
    pts = 96
    xs = (np.arange(pts) + 0.5) / pts

    def pinned(y):  # the ends are fixed: what the sums leave there is taken off along a line between them
        e0 = y[..., 0] - (y[..., 1] - y[..., 0]) * 0.5
        e1 = y[..., -1] + (y[..., -1] - y[..., -2]) * 0.5
        return y - e0[..., None] * (1 - xs) - e1[..., None] * xs

    times = np.arange(0, m - 1, every, dtype=np.float64)
    vel, disp = string_at({"v": vw, "y": yw}, lb, period - lb, w0, times, pts, d)
    disp = pinned(disp)
    # at each video frame, one period of the string in PERIOD_SHOTS steps (slow motion of the corner's trip)
    frames = np.arange(int(np.ceil(w0 / SR * FPS)), int((w1 / SR - 0.05) * FPS))
    t_f = frames / FPS * SR - w0
    loop = period[np.clip(t_f.astype(np.int64), 0, m - 1)] + d
    sub = t_f[:, None] + loop[:, None] * np.arange(PERIOD_SHOTS)[None, :] / PERIOD_SHOTS
    pv, py = string_at({"v": vw, "y": yw}, lb, period - lb, w0, sub.ravel(), pts, d)
    py = pinned(py).reshape(len(frames), PERIOD_SHOTS, pts)
    pv = pv.reshape(len(frames), PERIOD_SHOTS, pts)
    write_array(f"{PHYS}/bow-velocity", vel.astype(np.float32), rate=SR / every, t0=w0 / SR,
                about=f"the fiddle string's velocity at {pts} places from the bridge (0) to the nut, snapshots at "
                      f"{SR / every:.1f} a second (the waveguide's own waves, read off its two delay lines)")
    write_array(f"{PHYS}/bow-shape", disp.astype(np.float32), rate=SR / every, t0=w0 / SR,
                about="the fiddle string's displacement at the same places and times (each wave's running sum, read "
                      "as the velocity is; units velocity x samples), less the straight line between its two ends")
    write_array(f"{PHYS}/bow-period", np.stack([py, pv], axis=2).astype(np.float32), rate=float(FPS),
                t0=float(frames[0] / FPS),
                about=f"at each video frame from t0: {PERIOD_SHOTS} snapshots spread over one period of the string "
                      f"starting at that frame's time, each [displacement, velocity] at {pts} places from the bridge: "
                      "the Helmholtz corner's whole trip, in slow motion")
    step = SR // 240
    hz = SR / (period + d - bowed._SLIP_EARLY)
    tracks = np.stack([args[2][w0:w1:step], args[3][w0:w1:step], (lb / (period + d))[::step], hz[::step],
                       z["out"][w0:w1:step]], axis=1)
    write_array(f"{PHYS}/bow-tracks", tracks.astype(np.float32), rate=240.0, t0=w0 / SR,
                about="the fiddle's control tracks at 240 a second: [bow velocity (signed), bow force (grip: the "
                      "widest slip the hair holds), bow position (fraction of the loop from the bridge), "
                      "pitch Hz (the loop's), bridge force out]")
    write_json(f"{PHYS}/bow.json", {
        "part": "fiddle", "t0": w0 / SR, "t1": w1 / SR,
        "notes": [note_of(n) for n in notes if w0 / SR - 0.5 <= n["start"] < w1 / SR],
        "check": "the instrumented copy of bowed.run gives the engine's output bit for bit over the whole song",
        "about": "the string is two delay lines meeting at the bow: bow to bridge and back (bow position x "
                 "period samples) and bow to nut and back; the bow adds v where the hair grips (the STK bow "
                 "table); Helmholtz motion shows as one corner running round the string each period: in bow-period "
                 "(a period in slow motion at each frame) the displacement is two straight lines meeting at the "
                 "corner, the velocity a step at it; bow-shape and bow-velocity sample it at 480 a second, which "
                 "strobes the period (an alias, as a camera would)"}, indent=1)
    say(f"bow: {w0 / SR:.2f}..{w1 / SR:.2f} s, {len(times)} snapshots, {len(frames)} slow-motion periods, equal to the engine")


# ---------------------------------------------------------------------------------------------- the pipe


@njit(cache=True, nogil=True)
def pipe_traced(freq, breath, chiff, drive, aim, noise, feedback, damping, sr, w0, w1, every, points):
    """pipe.run with the same arithmetic, also keeping, every `every` samples in w0..w1, the bore's last
    period (resampled to `points`), and each sample's jet and flow there."""
    n = freq.shape[0]
    size = 8192
    bore = np.zeros(size)
    out = np.zeros(n)
    phase = 0.0
    lp = 0.0
    turb_lp = 0.0
    m = w1 - w0
    shots = np.zeros(((m + every - 1) // every, points))
    jets = np.zeros(m)
    flows = np.zeros(m)
    for t in range(n):
        f = freq[t]
        phase += f / sr
        if phase > 1.0:
            phase -= 1.0
        jet = np.sin(2.0 * np.pi * phase)
        k = drive[t]
        flow = np.tanh(k * jet + aim[t]) - np.tanh(aim[t])
        turb_lp = 0.35 * noise[t] + 0.65 * turb_lp
        turb = turb_lp * (0.6 + 0.4 * jet) * (0.1 * breath[t] + chiff[t])
        x = flow * breath[t] / (k + 0.3) + turb
        period = sr / f - damping / (1.0 - damping)
        pos = t - period
        i = int(np.floor(pos))
        frac = pos - i
        back = (1.0 - frac) * bore[i % size] + frac * bore[(i + 1) % size]
        lp = (1.0 - damping) * back + damping * lp
        y = x + feedback * lp
        bore[t % size] = y
        out[t] = y
        if w0 <= t < w1:
            jets[t - w0] = jet
            flows[t - w0] = flow * breath[t] / (k + 0.3)
            if (t - w0) % every == 0:
                for q in range(points):
                    at = t - period * q / points  # q/points of a period back
                    ii = int(np.floor(at))
                    ff = at - ii
                    shots[(t - w0) // every, q] = (1.0 - ff) * bore[ii % size] + ff * bore[(ii + 1) % size]
    return out, shots, jets, flows


PIPE_RATE = 480  # bore snapshots a second, near enough: one every SR // 480 samples


def pipe() -> None:
    """physics/pipe-*: the whistle's four Daisy notes in the bridge:
    breath, jet drive and the bore's circulating wave, from the instrumented copy of pipe.run, checked equal."""
    from songbird.synth import pipe as pipe_mod

    z = np.load(guard(CAP / "pipe-whistle.npz"))
    notes = sorted(load("pipe")[0]["notes"], key=lambda n: n["start"])
    args = [np.ascontiguousarray(z[k]) for k in ("freq", "breath", "chiff", "drive", "aim", "noise")]
    fbk, dmp, sr = float(z["feedback"]), float(z["damping"]), float(z["sr"])
    engine = pipe_mod.run(*args, fbk, dmp, sr)
    assert np.array_equal(engine, z["out"])
    # the bridge's four notes; the intro's whistle notes are rendered but silent there (the stage's level for
    # the whistle is null until refrain 1: its synth twin whistle~ plays them)
    d0 = read_json(DATA / "timeline.json")["daisy"][0]["t"]
    windows = {"daisy": (d0 - 0.3, d0 + 5.7)}
    every = SR // PIPE_RATE
    meta = {}
    for name, (a, b) in windows.items():
        w0, w1 = int(a * SR), int(b * SR)
        out, shots, jets, flows = pipe_traced(*args, fbk, dmp, sr, w0, w1, every, 64)
        assert np.array_equal(out, engine), "the traced copy isn't pipe.run"
        write_array(f"{PHYS}/pipe-{name}-bore", shots.astype(np.float32), rate=SR / every, t0=w0 / SR,
                    about="the bore's circulating wave: its last period (64 points, newest first: point q is q/64 of "
                          f"a period back), {SR / every:.1f} snapshots a second")
        step = SR // 240
        hz = args[0][w0:w1:step]
        tr = np.stack([args[1][w0:w1:step], args[2][w0:w1:step], args[3][w0:w1:step], args[4][w0:w1:step], hz,
                       out[w0:w1:step]], axis=1)
        write_array(f"{PHYS}/pipe-{name}-tracks", tr.astype(np.float32), rate=240.0, t0=w0 / SR,
                    about="the whistle's control tracks at 240 a second: [breath, chiff, drive (how far the jet "
                          "swings into saturation), aim (its offset from the edge), pitch Hz, the pipe's output]")
        write_array(f"{PHYS}/pipe-{name}-jet", np.stack([jets, flows], axis=1)[:: 4].astype(np.float32),
                    rate=SR / 4, t0=w0 / SR,
                    about="the jet's deflection (sin of its phase) and the flow it puts into the bore, every 4th "
                          "sample")
        meta[name] = {"t0": w0 / SR, "t1": w1 / SR, "notes": [note_of(n) for n in notes if a <= n["start"] < b]}
    write_json(f"{PHYS}/pipe.json", {
        "part": "whistle", "windows": meta, "feedback": fbk, "damping": dmp,
        "check": "the instrumented copy of pipe.run gives the engine's output bit for bit over the whole song",
        "about": "the jet flips at the note's frequency (jet = sin(phase)); its flow is tanh(drive jet + aim) - "
                 "tanh(aim), scaled by the breath; with turbulence it feeds a bore that is one delay line a period "
                 "long through a one-pole loss (feedback 0.65): the bore's contents over one period are the wave "
                 "circulating in it (a comb resonator, not a spatial pressure profile)"}, indent=1)
    say(f"pipe: {', '.join(f'{k} {v[0]:.2f}..{v[1]:.2f}' for k, v in windows.items())}, equal to the engine")


# ---------------------------------------------------------------------------------------------- the analog synths


@njit(cache=True, nogil=True)
def voice_traced(buf, at, n, on, off, pitch, retrig, glide, bend, amp, env, famt, fbase, kinds, levels, shifted, ratio,
                 pw, phases, gcoef, bcoef, vib, track, pref, k, drive, noise, seed, inv_sr2, trace):
    """analog._voice with the same arithmetic, also writing into trace, every 16 samples (at twice the rate):
    the pitch (MIDI, with glide and vibrato), the amp envelope, the filter envelope, the cutoff (Hz)."""
    nev = on.shape[0]
    n_w = kinds.shape[0]
    ph = phases.copy()
    lad = np.zeros(4)
    gain = (1.0 + COMP * k) / drive
    depth, rate, delay, fade = vib[0], vib[1], vib[2], vib[3]
    cur_p = pitch[0]
    target = pitch[0]
    coef = 1.0
    since = 0
    ea = 0.0
    astg = 0
    ef = 0.0
    fstg = 0
    gate = 0
    cur = 0
    j = 0
    vg = amp[0]
    big_g = 0.0
    dg = 0.0
    base = 0.0
    last_p = -1e9
    x_state = seed
    hz = np.zeros(n_w)
    duty = np.zeros(n_w)
    fc = 0.0
    for i in range(n):
        while j < nev and on[j] <= i:
            if glide[j]:
                target = pitch[j]
                coef = gcoef
            elif bend[j]:
                cur_p = pitch[j] - 2.0
                target = pitch[j]
                coef = bcoef
            else:
                cur_p = pitch[j]
                target = pitch[j]
            since = i
            if retrig[j] or gate == 0:
                if ea < 1e-3:
                    vg = amp[j]
                astg = 1
                fstg = 1
            gate = 1
            cur = j
            j += 1
        if gate == 1 and off[cur] >= 0 and i >= off[cur]:
            gate = 0
            astg = 3
            fstg = 3
        cur_p += (target - cur_p) * coef
        p = cur_p
        if depth > 0.0:
            tt = (i - since) * inv_sr2 - delay
            if tt > 0.0:
                w = tt / fade if tt < fade else 1.0
                p += 0.01 * depth * w * math.sin(2.0 * math.pi * rate * tt)
        if p != last_p:
            base = 440.0 * math.exp(0.057762265046662105 * (p - 69.0))
            last_p = p
        if astg == 1:
            ea += (ATTACK_TARGET - ea) * env[cur, 0]
            if ea >= 1.0:
                ea = 1.0
                astg = 2
        elif astg == 2:
            ea += (env[cur, 2] - ea) * env[cur, 1]
        elif astg == 3:
            ea -= ea * env[cur, 3]
        if fstg == 1:
            ef += (ATTACK_TARGET - ef) * env[cur, 4]
            if ef >= 1.0:
                ef = 1.0
                fstg = 2
        elif fstg == 2:
            ef += (env[cur, 6] - ef) * env[cur, 5]
        elif fstg == 3:
            ef -= ef * env[cur, 7]
        vg += (amp[cur] - vg) * 0.004
        if (i & 15) == 0:
            lf = fbase[cur] + track * (p - pref) / 12.0 + famt[cur] * ef
            fc = math.exp(0.6931471805599453 * lf)
            if fc < 16.0:
                fc = 16.0
            elif fc > 18000.0:
                fc = 18000.0
            g = math.tan(math.pi * fc * inv_sr2)
            tg = g / (1.0 + g)
            if i == 0:
                big_g = tg
                dg = 0.0
            else:
                dg = (tg - big_g) * 0.0625
            c = i / CTRL
            kc = int(c)
            fr = c - kc
            for w in range(n_w):
                hz[w] = ratio[w, kc] + (ratio[w, kc + 1] - ratio[w, kc]) * fr
                duty[w] = pw[w, kc] + (pw[w, kc + 1] - pw[w, kc]) * fr
            row = i >> 4
            trace[row, 0] = p
            trace[row, 1] = ea * vg
            trace[row, 2] = ef
            trace[row, 3] = fc
        big_g += dg
        x = 0.0
        for w in range(n_w):
            f = base * hz[w]
            if shifted[w]:
                f += duty[w]
            dt = f * inv_sr2
            if dt > 0.25:
                dt = 0.25
            q = ph[w]
            x += levels[w] * _wave(kinds[w], q, dt, duty[w])
            q += dt
            if q >= 1.0:
                q -= 1.0
            ph[w] = q
        if noise > 0.0:
            x_state ^= x_state >> np.uint64(12)
            x_state ^= x_state << np.uint64(25)
            x_state ^= x_state >> np.uint64(27)
            rr = (x_state * np.uint64(2685821657736338717)) >> np.uint64(11)
            x += noise * (rr * (2.0 / 9007199254740992.0) - 1.0)
        buf[at + i] += _ladder_step(drive * x, big_g, k, lad) * gain * ea * vg
        if gate == 0 and j >= nev and ea < 3e-5:
            return i + 1
    return n


TRACE_RATE = 240


def analog() -> None:
    """physics/analog.json and analog-traces.bin: every analog synth phrase of the twins and layers: its
    notes, the machine's oscillators and filter, and the traced pitch, envelopes and ladder cutoff."""
    from songbird.synth import analog as an

    recs = load("analog")
    waves = {0: "saw", 1: "pulse", 2: "triangle"}
    rows, phrases, worst_eq = [], [], 0
    offset = 0
    for rec in sorted(recs, key=lambda q: (q["stem"], q["args"]["at"])):
        a = rec["args"]
        names = list(a)
        n = int(a["n"])
        trace = np.zeros((n // 16 + 2, 4))
        mine, theirs = np.zeros(a["at"] + n + 8), np.zeros(a["at"] + n + 8)
        r1 = voice_traced(mine, *[a[k] for k in names], trace)
        r2 = an._voice(theirs, *[a[k] for k in names])
        assert r1 == r2 == rec["sounded"] and np.array_equal(mine, theirs), "the traced copy isn't analog._voice"
        worst_eq += 1
        used = (r1 + 15) // 16
        step = int(round(2 * SR / 16 / TRACE_RATE))  # trace rows (every 16 samples at twice the rate) a frame
        tr = trace[:used:step].astype(np.float32)
        rows.append(tr)
        p = rec["preset"]
        phrases.append({
            "stem": rec["stem"], "machine": rec["machine"], "t": r(a["at"] / (2 * SR)),
            "notes": [note_of(x) for x in rec["notes"]],
            "oscillators": [{"wave": o[0], "octave": o[1], "level": o[3], "width": o[4], "pwm": o[5]} for o in p["oscs"]],
            "waves": [{"wave": waves[int(kd)], "level": r(lv, 4), "pwm_saw": bool(sh)} for kd, lv, sh in
                      zip(a["kinds"], a["levels"], a["shifted"])],
            "detune_cents": [r(c, 3) for c in (1200 * np.log2(a["ratio"][:, 0]) % 1200 + 600) % 1200 - 600],
            "resonance_k": r(a["k"], 4), "drive": a["drive"], "track": a["track"], "chorus": bool(p.get("chorus")),
            "env": {"amp": list(p["aenv"]), "filter": list(p["fenv"]), "amount_oct": [r(x, 4) for x in a["famt"]],
                    "base_cutoff_hz": [r(2 ** x, 2) for x in a["fbase"]]},
            "row0": offset, "rows": len(tr)})
        offset += len(tr)
    write_array(f"{PHYS}/analog-traces", np.concatenate(rows), rate=TRACE_RATE,
                about="every analog phrase's trace (rows row0..row0+rows of analog.json's phrase, from its t): "
                      "[pitch MIDI (glide, vibrato), amp envelope x velocity gain, filter envelope 0..1, ladder "
                      "cutoff Hz]")
    write_json(f"{PHYS}/analog.json", {
        "phrases": phrases, "rate": TRACE_RATE,
        "check": f"the traced copy of analog._voice gives the engine's samples bit for bit for all {worst_eq} phrases",
        "about": "the twins' and layers' analog synths (synth/analog.py): each voice's phrase runs its oscillators "
                 "(polyBLEP saws and pulses; a width-modulated pulse is two saws, pwm_saw) through a four-pole "
                 "ladder low-pass at twice the rate; cutoff = 2^(base + track (pitch - ref)/12 + amount x filter "
                 "envelope); the stem is then AC-coupled (8 Hz) and, for the pad, chorused"})
    say(f"analog: {len(phrases)} phrases, all equal to the engine")


# ---------------------------------------------------------------------------------------------- the chip


@njit(cache=True, nogil=True)
def noise_traced(t0, t1, rate, short, vol, reg):
    """chip._noise_events with the same arithmetic, also giving the register as each frame begins."""
    cap = 16
    for k in range(t0.shape[0]):
        cap += int((t1[k] - t0[k]) * rate[k] + 2.0) + 2
    out_t = np.empty(cap)
    out_v = np.empty(cap)
    regs = np.zeros(t0.shape[0], dtype=np.int64)
    m = 0
    level = 0.0
    last_end = -1.0
    last_rate = 0.0
    last_short = False
    next_clock = 0.0
    for k in range(t0.shape[0]):
        t = t0[k]
        r = rate[k]
        if last_end >= 0.0 and t > last_end and last_rate > 0.0:
            clocks = int((t - last_end) * last_rate) % (2883 if last_short else 32767)
            for _ in range(clocks):
                reg = _lfsr(reg, last_short)
        if r != last_rate or t > last_end:
            next_clock = t + 1.0 / r
        regs[k] = reg
        v = vol[k]
        new = v if (reg & 1) == 0 else 0.0
        if new != level:
            out_t[m] = t
            out_v[m] = new
            m += 1
            level = new
        while next_clock < t1[k]:
            reg = _lfsr(reg, short[k])
            new = v if (reg & 1) == 0 else 0.0
            if new != level:
                out_t[m] = next_clock
                out_v[m] = new
                m += 1
                level = new
            next_clock += 1.0 / r
        last_end = t1[k]
        last_rate = r
        last_short = short[k]
    return out_t[:m], out_v[:m], reg, regs


def chip() -> None:
    """physics/chip.json and chip-*.bin: the chip twins' register-level events: the pulse channel's frames
    (frequency, 4-bit volume, duty), the triangle's frames, and the noise channel's hits with the 15-bit
    register as each frame begins (from an instrumented copy of chip._noise_events, checked equal)."""
    from songbird.synth import chip as ch

    recs = load("chip")
    out = {"cpu_hz": ch.CPU, "frame_hz": ch.FRAME, "noise_periods_cpu": list(ch.NOISE_PERIODS),
           "triangle_steps": ch.TRIANGLE_STEPS.tolist(), "duties": ch.DUTIES, "channels": []}
    for k, rec in enumerate(sorted(recs, key=lambda q: (q["stem"], q["channel"]))):
        f = rec["frames"]
        name = f"{PHYS}/chip-{rec['stem'].replace('#', '')}-{rec['channel']}"
        entry = {"stem": rec["stem"], "channel": rec["channel"], "frames": f"{name.split('/')[-1]}.bin",
                 "count": len(f["t0"])}
        if rec["channel"] == "pulse":
            arr = np.stack([f["t0"], f["t1"], f["hz"], f["vol"], f["lo"], f["hi"], f["reset"]], axis=1)
            about = ("the pulse channel's driver frames: [t0 s, t1 s, Hz, volume 0..15, the 8-step sequence's high "
                     "part from lo to hi of a period (12.5%: 0.875..1, 25%: 0.75..1, 50%: 0.5..1), restarts 0/1]")
            entry["driver"] = {k2: (r(v, 6) if isinstance(v, float) else v) for k2, v in rec["driver"].items()}
            entry["notes"] = len(rec["notes"])
        elif rec["channel"] == "triangle":
            arr = np.stack([f["t0"], f["t1"], f["hz"]], axis=1)
            about = "the triangle's running frames: [t0 s, t1 s, Hz]; it steps the 32-step table at 32 x Hz"
            entry["hits"] = [{"t": r(t), "piece": pc, "v": r(v, 4)} for t, pc, v in rec["tri_hits"]]
        else:
            et, ev, reg, regs = noise_traced(f["t0"], f["t1"], f["rate"], f["short"], f["vol"], rec["reg0"])
            assert np.array_equal(et, rec["events"][0]) and np.array_equal(ev, rec["events"][1]), \
                "the traced copy isn't chip._noise_events"
            arr = np.stack([f["t0"], f["t1"], f["rate"], f["short"], f["vol"], regs], axis=1)
            about = ("the noise channel's driver frames: [t0 s, t1 s, clock Hz (CPU / period), short mode 0/1 "
                     "(feedback bit 0 xor bit 6, else bit 0 xor bit 1), volume 0..15, the 15-bit register as the "
                     "frame begins]; it sounds the volume while bit 0 is clear and shifts once a clock: "
                     "reg = (reg >> 1) | (((reg ^ (reg >> tap)) & 1) << 14)")
            hits, starts = [], list(f["t0"])
            for t, pc, v in rec["noise_hits"]:
                i = int(np.searchsorted(f["t0"], t - 1e-9))
                index, looped, envelope = ch.KIT[pc]["noise"]
                index = int(np.clip(index + rec["shift"].get(pc, 0), 0, 15))
                hits.append({"t": r(t), "piece": pc, "v": r(v, 4), "frame": i, "seed": int(regs[i]) if i < len(regs) else None,
                             "clock_index": index, "period_cpu": ch.NOISE_PERIODS[index],
                             "clock_hz": r(ch.CPU / ch.NOISE_PERIODS[index], 3), "short": bool(looped),
                             "taps": [0, 6 if looped else 1]})
            entry.update({"reg0": rec["reg0"], "hits": hits, "kick_scale": rec["kick_scale"], "shift": rec["shift"],
                          "check": "the instrumented copy gives the engine's level changes exactly"})
        write_array(name, arr.astype(np.float64).astype(np.float32) if rec["channel"] != "noise" else arr.astype(np.float32),
                    about=about)
        out["channels"].append(entry)
    write_json(f"{PHYS}/chip.json", out)
    say(f"chip: {', '.join(c['stem'] + ' ' + c['channel'] + ' ' + str(c['count']) for c in out['channels'])}")


def drummachine() -> None:
    """physics/drummachine.json: every drum machine hit: its circuit voice, trigger and the machine's settings."""
    hits = sorted(load("drummachine"), key=lambda h: (h["stem"], h["t"]))
    kits = load("drummachine_kit")
    write_json(f"{PHYS}/drummachine.json", {
        "machines": [{"stem": k["stem"], "machine": k["machine"], "settings": k["settings"]} for k in kits],
        "hits": [{"stem": h["stem"], "machine": h["machine"], "piece": h["piece"], "t": r(h["t"]),
                  "v": r(h["vel"], 4), "size": r(h["size"], 5), "accent": r(h["accent"], 4), "cents": r(h["cents"], 3),
                  "loose": r(h["loose"], 5), "cut_s": r(h["cut"] / SR) if h["cut"] is not None else None,
                  "cut_tau": h["cut_tau"], "mix": h["mix"], "len_s": r(h["length"] / SR), "peak": r(h["peak"], 5)}
                 for h in hits],
        "about": "each trigger of the layer's and twin's drum machine (synth/drummachine.py): the piece is the "
                 "circuit voice (the 808's bridged-T rings, its six-square-wave metal, the 909's swept "
                 "oscillators and ROM cymbals); size is the trigger's height (touch.gain over 18 dB, times the "
                 "accent's 5 dB), cents its detune, loose its decay's tolerance, cut_s when a later trigger chokes it; "
                 "settings are the machine's tolerances and knobs as its maker drew them"})
    say(f"drummachine: {len(hits)} hits on {len(kits)} machines")


def reed() -> None:
    """physics/reed.json, reed-tables.bin, reed-tracks.bin: the drone's wavetables and bellows."""
    recs = sorted(load("reed"), key=lambda q: q["note"]["start"])
    tables = np.stack([q["wave"] for q in recs]) if recs else np.zeros((0, 4096), np.float32)
    rows, notes, off = [], [], 0
    for q in recs:
        n = len(q["env"])
        cols = [q["env"]]
        for rd in q["reeds"]:
            cols += [rd["hz"][:n], rd["amp"][:n]]
        rows.append(np.stack(cols, axis=1))
        notes.append({**note_of(q["note"]), "hz": r(q["freq"], 4), "pump_s": r(q["pump"], 4), "row0": off, "rows": n,
                      "reeds": [{"phase0": r(rd["phase0"]), "cents": r(rd["cents0"], 4)} for rd in q["reeds"]]})
        off += n
    write_array(f"{PHYS}/reed-tables", tables.astype(np.float32),
                about="each drone note's free-reed wavetable (one period, 4096 points, as reed.table made it)")
    width = max((x.shape[1] for x in rows), default=1)
    write_array(f"{PHYS}/reed-tracks", np.concatenate([np.pad(x, ((0, 0), (0, width - x.shape[1]))) for x in rows])
                if rows else np.zeros((0, 1), np.float32), rate=240.0,
                about="per drone note (rows row0.. of reed.json's note, from its start), 240 a second: [the bellows "
                      "curve (swell, pumping, velocity), then for each reed its Hz and amplitude]")
    write_json(f"{PHYS}/reed.json", {"part": "drone", "notes": notes,
                                     "about": "each note sounds three reeds reading its table, a few cents apart; "
                                              "the reed box's body (body.json REED_BOX) colours them; the hiss of air "
                                              "past the reeds is added and not tabled"})
    say(f"reed: {len(notes)} notes")


JOBS = {"pluck": pluck, "strum": strum, "drum": drum, "body": bodies, "bow": bow, "pipe": pipe, "analog": analog, "chip": chip, "drummachine": drummachine, "reed": reed}


if __name__ == "__main__":
    for job in sys.argv[1:] or list(JOBS):
        JOBS[job]()
