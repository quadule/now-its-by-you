"""The bowed bass's own physics for s08b_harp (breath 3) and s09b_bass (the tag), written to
renders/promo/video/data/bass/.

    uv run python tools/promo/video/prep/bass.py

The bowed bass ("bowedbass") is the stage's twin of the whistle two octaves down, plain (songbird/stage.py), played
by synth/cello.py: each stretch of its bowed notes goes through bowed.run_primed (bowed.run with a player's clean
attack: at each stroke the string is set into Helmholtz motion whole). The instrumented replay (replay.py) keeps
bowed.run's calls, not run_primed's, so this script makes the bowed bass's stem again by itself: the stage edition
laid as the replay lays it (common.laid), synth.stem_jobs' "bowedbass" job run with run_primed's calls kept, the
stem checked equal to the replay's own (scratch/replay/render.bowedbass.wav, the PA render's audio id 8660c5b6af71),
and an instrumented copy of run_primed checked equal to it, bit for bit. From that copy, as physics.py's bow() does
for the fiddle: at each video frame one period of the string in slow motion (sixteen snapshots of its
displacement and velocity along it) and the bow's control tracks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from numba import njit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, SCRATCH, guard, laid, read_json, say, write_array, write_json  # noqa: E402
from songbird.synth.bowed import _read_masked  # noqa: E402

SR = 44100
FPS = 60
PART = "bowedbass"
OUT = "bass"
PERIOD_SHOTS = 16  # snapshots across one period at each video frame
POINTS = 96  # places along the string, bridge to nut


@njit(cache=True, nogil=True)
def primed_traced(period, bridge_len, bow_v, grip, noise, pole, gain, at, velocity):
    """bowed.run_primed with the same arithmetic in the same order, also keeping, every sample, the waves the two
    delay lines meet at the bow (from_bridge, from_nut arriving; v what the bow adds) and each line's contents as
    its reads find them (a sample written, or laid down by a stroke's priming)."""
    n = period.shape[0]
    size = 4096
    mask = size - 1
    to_nut = np.zeros(size)
    to_bridge = np.zeros(size)
    out = np.zeros(n)
    fb_k = np.zeros(n)
    fn_k = np.zeros(n)
    v_k = np.zeros(n)
    hb = np.zeros(n)  # to_bridge's contents by sample index, the last written
    hn = np.zeros(n)
    lp = 0.0
    e = 0
    for t in range(n):
        lb = bridge_len[t]
        ln = period[t] - lb
        pl = pole[t]
        while e < at.shape[0] and at[e] < t:
            e += 1
        if e < at.shape[0] and at[e] == t:
            p = period[t] + pl / (1.0 - pl)
            height = velocity[e] * p / lb
            for j in range(t - int(lb) - 3, t):
                x = (j + lb - t) / p
                to_bridge[j & mask] = -height * (0.5 - (x - np.floor(x))) / gain[t]
                if j >= 0:
                    hb[j] = to_bridge[j & mask]
            for j in range(t - int(ln) - 3, t):
                x = (j - t) / p
                to_nut[j & mask] = -height * ((x - np.floor(x)) - 0.5)
                if j >= 0:
                    hn[j] = to_nut[j & mask]
            lp = -0.5 * height / gain[t]
            e += 1
        arriving = _read_masked(to_bridge, t, lb)
        lp = (1.0 - pl) * arriving + pl * lp
        from_bridge = -gain[t] * lp
        from_nut = -_read_masked(to_nut, t, ln)
        v_string = from_bridge + from_nut
        v = 0.0
        if bow_v[t] != 0.0:
            dv = bow_v[t] - v_string + noise[t]
            r = np.abs(0.25 * dv / grip[t]) + 0.75
            r = r * r
            r = 1.0 / (r * r)
            if r > 1.0:
                r = 1.0
            v = dv * r
        to_nut[t & mask] = from_bridge + v
        to_bridge[t & mask] = from_nut + v
        hb[t] = to_bridge[t & mask]
        hn[t] = to_nut[t & mask]
        out[t] = arriving
        fb_k[t] = from_bridge
        fn_k[t] = from_nut
        v_k[t] = v
    return out, fb_k, fn_k, v_k, hb, hn


def at_times(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    """x read at fractional sample times t (linear), 0 outside."""
    i = np.floor(t).astype(np.int64)
    f = t - i
    ok = (i >= 0) & (i + 1 < len(x))
    i = np.clip(i, 0, len(x) - 2)
    return np.where(ok, (1 - f) * x[i] + f * x[i + 1], 0.0)


def string_at(waves: dict, lb, ln, delay, times: np.ndarray, points: int):
    """physics.py's string_at with the loss filter's delay a track (run_primed's pole moves note by note): the
    string at fractional sample times, (velocity, displacement) at `points` places from the bridge (0) to the nut
    (1). Bridge side: the wave going out left the bow s samples ago (the line's contents at t - s), the one coming
    back reaches it s samples from now (from_bridge); the nut side likewise. The bridge side is (bridge_len +
    delay) / 2 samples of travel long, the nut side (period - bridge_len) / 2."""
    x = (np.arange(points) + 0.5) / points
    i = np.clip(np.round(times).astype(np.int64), 0, len(lb) - 1)
    L = (lb[i] + delay[i]) / 2.0
    N = ln[i] / 2.0
    place = x[None, :] * (L + N)[:, None]
    bridge_side = place < L[:, None]
    s_b = L[:, None] - place
    s_n = place - L[:, None]
    tt = times[:, None]
    res = []
    for kind in ("v", "y"):
        w = waves[kind]
        vb = at_times(w["out_b"], tt - s_b) + at_times(w["fb"], tt + s_b)
        vn = at_times(w["out_n"], tt - s_n) + at_times(w["fn"], tt + s_n)
        res.append(np.where(bridge_side, vb, vn))
    return res


def capture() -> tuple[list[dict], np.ndarray]:
    """The bowed bass's stem made again, run_primed's calls kept: [{s0, args, out, notes}], and the stem."""
    from songbird import synth
    from songbird.synth import bowed

    calls: list[dict] = []
    engine = bowed.run_primed

    def kept(period, bridge_len, bow_v, grip, noise, pole, gain, at, velocity):
        y = engine(period, bridge_len, bow_v, grip, noise, pole, gain, at, velocity)
        up = sys._getframe(2).f_locals  # cello.player: the stretch's first sample and its notes
        calls.append({"s0": int(up["s0"]), "notes": [(float(n.start), float(n.dur), float(n.pitch), float(n.vel),
                                                      str(n.art or "")) for n in up["group"]],
                      "args": [np.array(a, copy=True) for a in (period, bridge_len, bow_v, grip, noise, pole, gain,
                                                               at, velocity)], "out": y.copy()})
        return y

    _, params, score = laid()
    bowed.run_primed = kept
    try:
        jobs, _ = synth.stem_jobs(score, SR, params.seed)
        make = dict(jobs)[PART]
        y = make()
    finally:
        bowed.run_primed = engine
    return calls, y


def check_stem(y: np.ndarray) -> float:
    import soundfile as sf

    ref, sr = sf.read(str(guard(SCRATCH / "replay" / f"render.{PART}.wav")), dtype="float32", always_2d=True)
    assert sr == SR
    mine = y.astype(np.float32).reshape(ref.shape) if y.ndim == ref.ndim else y.astype(np.float32)[:, None]
    assert mine.shape == ref.shape, (mine.shape, ref.shape)
    worst = float(np.max(np.abs(mine - ref)))
    assert worst == 0.0, f"the stem made again differs from the replay's by {worst}"
    return worst


def window(call: dict, name: str, a: float, b: float, notes: list) -> dict:
    """One window [a, b) s of the song from a run_primed call: the slow-motion periods and the tracks."""
    period, lb, bow_v, grip, noise, pole, gain, at, vel = call["args"]
    s0 = call["s0"]
    out, fb, fn, v, hb, hn = primed_traced(period, lb, bow_v, grip, noise, pole, gain, at, vel)
    assert np.array_equal(out, call["out"]), "the traced copy isn't bowed.run_primed"
    w0, w1 = int(a * SR) - s0, int(np.ceil(b * SR)) - s0
    assert 0 <= w0 < w1 <= len(period), (name, w0, w1, len(period))
    d = pole / (1.0 - pole)  # the loss filter's delay at low frequencies, a track
    vw = {"out_b": hb, "fb": fb, "out_n": hn, "fn": fn}
    yw = {k: np.cumsum(x) for k, x in vw.items()}
    pts = POINTS
    xs = (np.arange(pts) + 0.5) / pts

    def pinned(y):  # the ends are fixed: what the sums leave there is taken off along a line between them
        e0 = y[..., 0] - (y[..., 1] - y[..., 0]) * 0.5
        e1 = y[..., -1] + (y[..., -1] - y[..., -2]) * 0.5
        return y - e0[..., None] * (1 - xs) - e1[..., None] * xs

    g0 = s0 + w0  # the window's first sample in the song
    frames = np.arange(int(np.ceil(g0 / SR * FPS)), int((s0 + w1) / SR * FPS))
    t_f = frames / FPS * SR - s0  # each frame's time in the call's samples
    loop = period[np.clip(t_f.astype(np.int64), 0, len(period) - 1)] + d[np.clip(t_f.astype(np.int64), 0, len(period) - 1)]
    sub = t_f[:, None] + loop[:, None] * np.arange(PERIOD_SHOTS)[None, :] / PERIOD_SHOTS
    pv, py = string_at({"v": vw, "y": yw}, lb, period - lb, d, sub.ravel(), pts)
    py = pinned(py).reshape(len(frames), PERIOD_SHOTS, pts)
    pv = pv.reshape(len(frames), PERIOD_SHOTS, pts)
    write_array(f"{OUT}/{name}-period", np.stack([py, pv], axis=2).astype(np.float32), rate=float(FPS),
                t0=float(frames[0] / FPS),
                about=f"the bowed bass at each video frame from t0: {PERIOD_SHOTS} snapshots spread over one period of "
                      f"the string starting at that frame's time, each [displacement, velocity] at {pts} places from "
                      "the bridge (0) to the nut: the Helmholtz corner's whole trip, in slow motion")
    step = SR // 240
    sl = slice(w0, w1, step)
    hz = SR / (period + d - bowed_slip())
    tracks = np.stack([bow_v[sl], grip[sl], (lb / (period + d))[sl], hz[sl], call["out"][sl]], axis=1)
    write_array(f"{OUT}/{name}-tracks", tracks.astype(np.float32), rate=240.0, t0=g0 / SR,
                about="the bowed bass's control tracks at 240 a second: [bow velocity (signed), bow force (grip: the "
                      "widest slip the hair holds), bow position (fraction of the loop from the bridge), pitch Hz "
                      "(the loop's), bridge force out]")
    primes = [(int(t_) + s0) / SR for t_ in at if w0 <= t_ < w1]
    say(f"{name}: {g0 / SR:.3f}..{(s0 + w1) / SR:.3f} s, {len(frames)} slow-motion periods, {len(primes)} strokes primed")
    return {"t0": g0 / SR, "t1": (s0 + w1) / SR, "frames": int(len(frames)), "primed": [round(p, 6) for p in primes],
            "notes": [n for n in notes if a - 0.5 <= n["t"] < b]}


def bowed_slip() -> float:
    from songbird.synth import bowed
    return bowed._SLIP_EARLY


def main() -> None:
    tl = read_json(DATA / "timeline.json")
    sec = {s["id"]: s for s in tl["sections"]}
    calls, y = capture()
    check_stem(y)
    say(f"{PART}: {len(calls)} bowed stretches; the stem made again equals the replay's, sample for sample")
    notes = sorted(({"t": round(s0n[0] + c["s0"] / SR, 6), "d": round(s0n[1], 6), "p": round(s0n[2], 3),
                     "v": round(s0n[3], 4), "art": s0n[4]} for c in calls for s0n in c["notes"]), key=lambda n: n["t"])
    # breath 3 from just before its first note (its stretch's start); the tag from a bar before it (the bass's level comes up in the last
    # bar of refrain 3) to the ring's first bar
    bar = tl["bar"]
    wins = {"breath3": (sec["breath3"]["t0"] - 0.1, sec["breath3"]["t1"] + 0.25),
            "tag": (sec["tag"]["t0"] - bar, min(sec["ring"]["t0"] + bar, tl["duration"] - 0.1))}
    meta = {}
    for name, (a, b) in wins.items():
        call = next(c for c in calls if c["s0"] <= b * SR and a * SR < c["s0"] + len(c["out"]))
        a = max(a, (call["s0"] + 1) / SR)  # a stretch starts a little before its first note
        meta[name] = window(call, name, a, b, notes)
    write_json(f"{OUT}/bass.json", {
        "part": PART, "sr": SR, "windows": meta,
        "check": f"the {PART} stem made again by itself equals the replay's (render.{PART}.wav, audio id "
                 "8660c5b6af71) sample for sample; the instrumented copy of bowed.run_primed gives the engine's "
                 "output bit for bit",
        "about": "the bowed bass (synth/cello.py's upright bass under the bow, the whistle's notes two octaves "
                 "down, plain) on bowed.run_primed: the string is two delay lines meeting at the bow, which adds v "
                 "where the hair grips; at each stroke (primed) the string is laid into Helmholtz motion whole, so "
                 "from that sample the picture is the motion the player's bow is heading for. In <window>-period "
                 "(a period in slow motion at each frame) the displacement is two straight lines meeting at the "
                 "corner, the velocity a step at it. Notes are the stretches' own, in song seconds, pitch as "
                 "played."}, indent=1)


if __name__ == "__main__":
    main()
