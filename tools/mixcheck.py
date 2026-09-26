"""Checks on a finished mix that catch a bad-sounding result without ears.

    uv run python tools/mixcheck.py songs/h-now-its-by-you.json [--choir 3] [--stems FILE.npz] [--mix field=value ...]

Renders the song's stems (or loads them), mixes and masters them, and reports
against thresholds a mix engineer would hold to (each line says what it
checks, the number, and ok or LOOK):

- the buses at master level: voice, band (while the voice sings and in the
  gaps), choir, room and plate;
- clarity: the voice against band and room in 1-4 kHz while it sings;
- pumping: how much band and room drop just after the voice comes in;
- the limiter: how much it took, and how often;
- tonal balance: the low end against the middle, the fall above 1 kHz;
- stereo: left/right correlation (10th percentile and lowest, 400 ms
  windows) and what folding to mono costs;
- clicks the mix added, the ending's tail, and energy under 30 Hz.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfiltfilt, welch

sys.path.insert(0, str(Path(__file__).parent.parent))
from songbird.synth.voice import VoiceParams  # noqa: E402
from songbird import genome as G, synth  # noqa: E402
from songbird.realize import choose_params, realize  # noqa: E402
from songbird.synth import master, mixing  # noqa: E402
from songbird.synth.mixing import MixParams  # noqa: E402

SR = synth.SR


def band_level(x: np.ndarray, lo: float, hi: float, where: np.ndarray | None = None) -> float:
    y = sosfiltfilt(butter(4, [lo, hi], btype="bandpass", fs=SR, output="sos"), x.reshape(len(x), -1), axis=0)
    y = y if where is None else y[where[: len(y)]]
    return float(10 * np.log10(np.mean(y**2) + 1e-20))


def octave(x: np.ndarray, lo: float, hi: float) -> float:
    f, p = welch(x.reshape(len(x), -1).mean(axis=1), SR, nperseg=8192)
    return float(10 * np.log10(p[(f >= lo) & (f < hi)].sum() + 1e-20))


def line(what: str, value: float, unit: str, good: bool) -> None:
    print(f"  {what:58} {value:+7.1f} {unit:4} {'ok' if good else 'LOOK'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("genome")
    ap.add_argument("--choir", type=int, default=None)
    ap.add_argument("--stems", help="an .npz of stems to use instead of rendering")
    ap.add_argument("--mix", nargs="*", default=[], metavar="FIELD=VALUE")
    ap.add_argument("--voice", nargs="*", default=[], metavar="FIELD=VALUE",
                    help="the singer, e.g. --voice engine=learned (VoiceParams fields)")
    args = ap.parse_args()

    g = G.load(args.genome)
    params = choose_params(g)
    if args.choir is not None:
        params = replace(params, choir=args.choir)
    if args.stems:
        with np.load(args.stems) as z:
            stems = {k: z[k].astype(np.float64) for k in z.files}
    else:
        defaults = VoiceParams()
        singer = replace(defaults, **{k: type(getattr(defaults, k))(v) for k, v in (kv.split("=", 1) for kv in args.voice)})
        stems = synth.render_stems(realize(g, params), seed=params.seed, voice=singer)
    taps, mtaps = {}, {}
    mixed = mixing.mix(stems, SR, params.seed, MixParams.parse(args.mix), taps=taps)
    final = master.master(mixed, SR, taps=mtaps)
    gain = 10 ** (mtaps["gain_db"] / 20)
    n = len(stems[next(iter(stems))])
    singing = taps["singing"] > 0.5 if taps.get("singing") is not None else np.zeros(n, bool)
    gaps = (taps["singing"] < 0.05) if taps.get("singing") is not None else np.ones(n, bool)
    bus = {k: (taps[k] * gain if taps.get(k) is not None else None) for k in ("voice", "band", "choir")}
    wet = taps["wet"][:n] * gain

    print("buses at master level (LUFS)")
    lv = {k: master.loudness(v, SR) for k, v in bus.items() if v is not None}
    for k, v in lv.items():
        print(f"  {k:10} {v:6.1f}")
    print(f"  {'room':10} {master.loudness(wet, SR):6.1f}")
    if bus["band"] is not None and singing.any() and gaps.any():
        band_gaps = master.loudness(bus["band"][gaps], SR)
        line("room under the band, in the gaps between lines (<= -3)", master.loudness(wet[gaps], SR) - band_gaps, "dB",
             master.loudness(wet[gaps], SR) - band_gaps <= -3.0)
    if bus["voice"] is not None and singing.any():
        rest = bus["band"] + wet if bus["band"] is not None else wet
        clarity = band_level(bus["voice"], 1000, 4000, singing) - band_level(rest, 1000, 4000, singing)
        line("clarity: voice over band and room, 1-4 kHz, singing (>= 5)", clarity, "dB", clarity >= 5.0)
        # pumping: band and room just after each line starts, against just before; the arrangement itself
        # comps softer under words, so what the mix adds is what counts
        onsets = np.flatnonzero(np.diff(singing.astype(int)) == 1)
        raw = sum(v for k, v in stems.items() if mixing.role_of(k) not in ("voice", "choir"))

        def drops(x):
            acc = (x.reshape(len(x), -1) ** 2).sum(axis=1)
            out = []
            for i in onsets:
                before = acc[max(0, i - int(0.3 * SR)) : i - int(0.05 * SR)]
                after = acc[i + int(0.05 * SR) : i + int(0.3 * SR)]
                if len(before) > 100 and len(after) > 100:
                    out.append(10 * np.log10((after.mean() + 1e-20) / (before.mean() + 1e-20)))
            return np.array(out)
        mine, theirs = drops(rest), drops(raw) if np.any(raw) else np.zeros(0)
        if len(mine) and len(theirs):
            added = float(np.median(mine - theirs))
            print(f"  band as arranged, after a line starts: {np.median(theirs):+.1f} dB (median), the band and room as mixed {np.median(mine):+.1f}")
            line("pumping: what the mix adds to that (|.| <= 1.5)", added, "dB", abs(added) <= 1.5)
            worst = float(np.percentile(mine - theirs, 10))
            line("pumping: 10th percentile of what it adds (>= -3)", worst, "dB", worst >= -3.0)
    # what the clip and limiter took, heard over 10 ms: the level out against the level in, after the gain
    k = int(0.01 * SR)
    m = min(len(final), len(mixed)) // k
    out_e = (final[: m * k] ** 2).sum(axis=1).reshape(m, k).sum(axis=1)
    in_e = ((mixed[: m * k] * gain) ** 2).sum(axis=1).reshape(m, k).sum(axis=1)
    loud = in_e > in_e.max() * 10 ** (-12 / 10)
    took = 10 * np.log10((out_e[loud] + 1e-20) / (in_e[loud] + 1e-20))
    line("clip and limiter: the most they took over 10 ms (<= 3)", float(-took.min()), "dB", -took.min() <= 3.0)
    share = float(np.mean(took < -1.0)) * 100
    line("clip and limiter: loud 10 ms stretches they took 1 dB from (<= 2%)", share, "%", share <= 2.0)

    body, low, one, two = (octave(final, 500, 1000), octave(final, 125, 250), octave(final, 1000, 2000),
                           octave(final, 2000, 4000))
    line("low end: 125-250 Hz against 500-1000 Hz (>= -8)", low - body, "dB", low - body >= -8.0)
    line("the fall from 1-2 kHz to 2-4 kHz (<= 10)", one - two, "dB", one - two <= 10.0)

    k = int(0.4 * SR)
    m = len(final) // k
    l, r = final[: m * k, 0].reshape(m, k), final[: m * k, 1].reshape(m, k)
    e = (l * l).sum(1) + (r * r).sum(1)
    live = e > e.max() * 1e-4
    corr = ((l * r).sum(1) / np.sqrt((l * l).sum(1) * (r * r).sum(1) + 1e-30))[live]
    line("correlation, 10th percentile of 400 ms windows (>= 0.4)", float(np.percentile(corr, 10)), "", np.percentile(corr, 10) >= 0.4)
    line("correlation, lowest window (>= -0.2)", float(corr.min()), "", corr.min() >= -0.2)
    fold = master.loudness(final.mean(axis=1, keepdims=True) * np.sqrt(2), SR) - master.loudness(final, SR)
    line("folded to mono, loudness change (>= -0.5)", fold, "LU", fold >= -0.5)

    def jumps(x: np.ndarray) -> int:
        highs = sosfiltfilt(butter(4, 6000, btype="highpass", fs=SR, output="sos"), x.reshape(len(x), -1), axis=0)
        jump = np.abs(np.diff(highs, axis=0)).max(axis=1)
        local = np.sqrt(np.maximum(uniform_filter1d((highs**2).mean(axis=1), int(0.02 * SR)), 0.0)[1:]) + 1e-9
        return int(np.sum(jump > local * 10 ** (24 / 20)))
    here, there = jumps(final), jumps(sum(stems.values()))
    print(f"  high-band jumps 24 dB over the local level: {there} in the stems as they come, {here} in the master")
    line("clicks the mix added (0)", max(0, here - there), "", here <= there)
    tail = master.loudness(final[-int(0.5 * SR):], SR) if len(final) > SR else -np.inf
    line("the last half second (< -70)", max(tail, -120.0), "LUFS", tail < -70.0)
    sub = octave(final, 1, 30) - octave(final, 30, 20000)
    line("energy under 30 Hz against the rest (<= -30)", sub, "dB", sub <= -30.0)


if __name__ == "__main__":
    main()
