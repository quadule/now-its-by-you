"""Turn 2 as s07_gather draws it: the whistle's bore and jet, and the fiddle's held string, through the turn, from
physics.py's instrumented copies of pipe.run and bowed.run (each checked equal to the engine). Writes
renders/promo/video/data/turn2/.

    uv run python tools/promo/video/prep/turn2.py

At each video frame, SHOTS snapshots spread over one period of each instrument starting at that frame's time: the
period in slow motion, as physics/bow-period holds the breath's fiddle.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, read_json, say, write_array, write_json  # noqa: E402
from physics import (CAP, FPS, PIPE_RATE, SR, bow_traced, load, note_of, pipe_traced,  # noqa: E402
                     string_at)

OUT = "turn2"
SHOTS = 16      # snapshots across one period at each video frame
BORE = 64       # points along the bore's period
STRING = 96     # places along the fiddle's string


def window() -> tuple[float, float]:
    """The turn, from just before its downbeat to a little past the bridge's (the bridge dissolves in over it)."""
    sec = next(x for x in read_json(DATA / "timeline.json")["sections"] if x["id"] == "turn2")
    return sec["t0"] - 0.3, sec["t1"] + 0.2


def frames_in(w0: int, w1: int) -> np.ndarray:
    return np.arange(int(np.ceil(w0 / SR * FPS)), int((w1 / SR - 0.05) * FPS))


def whistle(a: float, b: float) -> dict:
    from songbird.synth import pipe as pipe_mod

    z = np.load(CAP / "pipe-whistle.npz")
    notes = sorted(load("pipe")[0]["notes"], key=lambda n: n["start"])
    args = [np.ascontiguousarray(z[k]) for k in ("freq", "breath", "chiff", "drive", "aim", "noise")]
    fbk, dmp, sr = float(z["feedback"]), float(z["damping"]), float(z["sr"])
    engine = pipe_mod.run(*args, fbk, dmp, sr)
    assert np.array_equal(engine, z["out"])
    w0, w1 = int(a * SR), int(b * SR)
    every = SR // PIPE_RATE
    out, shots, jets, flows = pipe_traced(*args, fbk, dmp, sr, w0, w1, every, BORE)
    assert np.array_equal(out, engine), "the traced copy isn't pipe.run"
    freq = args[0]

    # The bore is a delay line holding the pipe's own output: its contents at sample t are out[t - q/BORE of a
    # period], read as pipe_traced reads them. Checked against the traced snapshots where both exist.
    def bore_at(ts: np.ndarray) -> np.ndarray:
        period = sr / freq[ts] - dmp / (1.0 - dmp)
        at = ts[:, None] - period[:, None] * np.arange(BORE)[None, :] / BORE
        ii = np.floor(at).astype(np.int64)
        ff = at - ii
        return (1.0 - ff) * out[ii] + ff * out[ii + 1]

    check = np.arange(w0, w1, every)
    assert np.array_equal(bore_at(check), shots), "the bore read from the output isn't the traced bore"

    frames = frames_in(w0, w1)
    tf = np.round(frames / FPS * SR).astype(np.int64)
    period = sr / freq[tf] - dmp / (1.0 - dmp)
    sub = tf[:, None] + np.round(period[:, None] * np.arange(SHOTS)[None, :] / SHOTS).astype(np.int64)
    sub = np.clip(sub, w0, w1 - 1)
    bore = bore_at(sub.ravel()).reshape(len(frames), SHOTS, BORE)
    per = sr / freq[sub] - dmp / (1.0 - dmp)
    jet = np.stack([jets[sub - w0], flows[sub - w0], per], axis=2)
    t0f = float(frames[0] / FPS)
    write_array(f"{OUT}/pipe-period", bore.astype(np.float32), rate=float(FPS), t0=t0f,
                about=f"the whistle's bore at each video frame from t0: {SHOTS} snapshots spread over one period "
                      f"starting at that frame's time, each the bore's last period at {BORE} points, newest first "
                      "(point q is q/64 of a period back): the wave circulating in it, in slow motion")
    write_array(f"{OUT}/pipe-jet", jet.astype(np.float32), rate=float(FPS), t0=t0f,
                about="at the same snapshots: the jet's deflection (sin of its phase), the flow it puts into the "
                      "bore, and the bore's length in samples (a period, less the loss filter's delay)")
    step = SR // 240
    tr = np.stack([args[1][w0:w1:step], args[2][w0:w1:step], args[3][w0:w1:step], args[4][w0:w1:step],
                   freq[w0:w1:step], out[w0:w1:step]], axis=1)
    write_array(f"{OUT}/pipe-tracks", tr.astype(np.float32), rate=240.0, t0=w0 / SR,
                about="the whistle's control tracks at 240 a second: [breath, chiff, drive (how far the jet swings "
                      "into saturation), aim (its offset from the edge), pitch Hz, the pipe's output]")
    peak = float(np.max(np.abs(out[w0:w1])))
    say(f"whistle: {a:.2f}..{b:.2f} s, {len(frames)} frames x {SHOTS}, peak {peak:.3f}, equal to the engine")
    return {"t0": w0 / SR, "t1": w1 / SR, "feedback": fbk, "damping": dmp, "peak": peak,
            "notes": [note_of(n) for n in notes if a <= n["start"] < b]}


def fiddle(a: float, b: float) -> dict:
    from songbird.synth import bowed

    z = np.load(CAP / "bow-fiddle.npz")
    notes = sorted(load("bow")[0]["notes"], key=lambda n: n["start"])
    args = [np.ascontiguousarray(z[k]) for k in ("period", "bridge_len", "bow_v", "grip", "noise")]
    pole, gain = float(z["pole"]), float(z["gain"])
    out, fb, fn, v = bow_traced(*args, pole, gain, 0, len(args[0]))
    assert np.array_equal(out, z["out"]), "the traced copy isn't bowed.run"
    assert np.array_equal(out, bowed.run(*args, pole, gain))
    w0, w1 = int(a * SR), int(b * SR)
    fb, fn, v = fb[w0:w1], fn[w0:w1], v[w0:w1]
    vw = {"out_b": fn + v, "fb": fb, "out_n": fb + v, "fn": fn}
    yw = {k: np.cumsum(x) for k, x in vw.items()}
    period, lb = args[0][w0:w1], args[1][w0:w1]
    d = bowed._FILTER_DELAY
    m = w1 - w0
    xs = (np.arange(STRING) + 0.5) / STRING

    def pinned(y):  # the ends are fixed: what the sums leave there is taken off along a line between them
        e0 = y[..., 0] - (y[..., 1] - y[..., 0]) * 0.5
        e1 = y[..., -1] + (y[..., -1] - y[..., -2]) * 0.5
        return y - e0[..., None] * (1 - xs) - e1[..., None] * xs

    frames = frames_in(w0, w1)
    t_f = frames / FPS * SR - w0
    loop = period[np.clip(t_f.astype(np.int64), 0, m - 1)] + d
    sub = t_f[:, None] + loop[:, None] * np.arange(SHOTS)[None, :] / SHOTS
    _, py = string_at({"v": vw, "y": yw}, lb, period - lb, w0, sub.ravel(), STRING, d)
    py = pinned(py).reshape(len(frames), SHOTS, STRING)
    write_array(f"{OUT}/fiddle-period", py.astype(np.float32), rate=float(FPS), t0=float(frames[0] / FPS),
                about=f"the fiddle string's displacement at each video frame from t0: {SHOTS} snapshots spread over "
                      f"one period starting at that frame's time, at {STRING} places from the bridge (0) to the nut "
                      "(units velocity x samples, less the line between its ends), as physics/bow-period")
    step = SR // 240
    hz = SR / (period + d - bowed._SLIP_EARLY)
    tr = np.stack([args[2][w0:w1:step], args[3][w0:w1:step], (lb / (period + d))[::step], hz[::step],
                   out[w0:w1:step]], axis=1)
    write_array(f"{OUT}/fiddle-tracks", tr.astype(np.float32), rate=240.0, t0=w0 / SR,
                about="the fiddle's control tracks at 240 a second: [bow velocity (signed), bow force, bow position "
                      "(fraction of the loop from the bridge), pitch Hz, bridge force out]")
    peak = float(np.max(np.abs(py)))
    say(f"fiddle: {a:.2f}..{b:.2f} s, {len(frames)} frames x {SHOTS}, peak displacement {peak:.2f}, equal to the engine")
    return {"t0": w0 / SR, "t1": w1 / SR, "peak": peak,
            "notes": [note_of(n) for n in notes if a - 2.6 <= n["start"] < b]}


def main() -> None:
    a, b = window()
    write_json(f"{OUT}/turn2.json", {
        "whistle": whistle(a, b), "fiddle": fiddle(a, b), "shots": SHOTS, "fps": FPS,
        "check": "the instrumented copies of pipe.run and bowed.run give the engine's output bit for bit over the "
                 "whole song; the bore's snapshots read from the output equal the traced copy's",
        "about": "the whistle's bore is one delay line a period long through a one-pole loss: its contents over a "
                 "period are the wave circulating in it, newest at the mouth; the jet flips at the note's frequency "
                 "and feeds it. The fiddle's string is two delay lines meeting at the bow (physics/bow.json)"},
        indent=1)


if __name__ == "__main__":
    main()
