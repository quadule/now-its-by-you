"""Measure a rendition recorded as a 78 (MixParams.disc; synth/disc.py, docs/STYLES.md "An old 78").

    uv run python tools/discmeter.py renders/styles/old78-ada-2026-09-27.flac [...]

For each render (its record and score beside it) it makes the mix again as the record says, once without the disc
and once through it (checking that the second, mastered, is the render's own samples), and reports:

- the horn drawn for the record, and the band it actually passed: the music's level after the horn against before
  it, by frequency (Welch, the whole song), its -3, -10 and -20 dB points, and the level at a few frequencies;
- the wow: the record's own eccentricity (drawn), and a steady 1 kHz tone through the same record's turntable, its
  frequency's deviation (peak, and the rate it wavers at);
- the surface: its loudness under the music's, and in the finished file the needle's lead-in and the run-out
  groove against the music; the clicks a second (scratches heard each revolution, pops, the run-out's) and how many
  are heard again exactly a revolution later;
- the finished file's loudness, loudness range and true peak.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import hilbert, welch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from songbird import cli, genome as genome_mod, phrasing as phrasing_mod, synth, variation  # noqa: E402
from songbird.realize import Params, realize  # noqa: E402
from songbird.synth import disc, master, mixing  # noqa: E402
from songbird.synth.mixing import MixParams  # noqa: E402

SR = synth.SR


def remake(flac: Path):
    """The record's score, singer and mix, and its mix made again without the disc."""
    record = json.loads(flac.with_suffix(".json").read_text())
    genome = genome_mod.load(Path(__file__).resolve().parent.parent / "songs" / "h-now-its-by-you.json")
    params = Params.from_dict(record["params"])
    params = replace(params, singer=record.get("singer") or params.singer, mix=record.get("mix") or params.mix)
    from songbird.arrange import Lyrics

    lyrics = Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None
    phrasing_json, choir_json = phrasing_mod.inherited(genome.source, record)
    phrasing = phrasing_mod.from_json(phrasing_json) if phrasing_json else None
    choir = [phrasing_mod.from_json(d) for d in choir_json]
    score = variation.lay(realize(genome, params, phrasing=phrasing, choir=choir, lyrics=lyrics), params)
    singer = cli._singer(params, [])
    mix = MixParams.from_dict(params.mix or {})
    dry = synth.render(score, seed=params.seed, voice=singer, mix_params=replace(mix, disc=0.0))
    return record, params, mix, dry


def transfer(before: np.ndarray, after: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(len(before), len(after))
    f, a = welch(before[:n], SR, nperseg=8192)
    f, b = welch(after[:n], SR, nperseg=8192)
    gain = 10 * np.log10((b + 1e-30) / (a + 1e-30))
    return f, gain - np.median(gain[(f > 300) & (f < 3500)])


def edges(f: np.ndarray, gain: np.ndarray, drop: float) -> tuple[float, float]:
    """The lowest and highest frequency around 1 kHz before the gain falls `drop` dB under the passband."""
    k = int(np.argmin(np.abs(f - 1000)))
    lo = k
    while lo > 0 and gain[lo - 1] > -drop:
        lo -= 1
    hi = k
    while hi < len(f) - 1 and gain[hi + 1] > -drop:
        hi += 1
    return float(f[lo]), float(f[hi])


def wow_of(seed: int) -> tuple[float, float]:
    """A 1 kHz tone through this record's turntable: its frequency's peak deviation (fraction) and its rate (Hz)."""
    t = np.arange(int(20 * SR)) / SR
    x = np.zeros((len(t), 2))
    x[int(0.6 * SR):] = 0.3 * np.sin(2 * np.pi * 1000 * t[int(0.6 * SR):])[:, None]
    taps: dict = {}
    disc.record(x, SR, 1.0, seed, taps)
    m = taps["music"][int(2 * SR): int(18 * SR)]
    inst = np.diff(np.unwrap(np.angle(hilbert(m)))) * SR / (2 * np.pi)
    k = int(0.01 * SR)
    dev = np.convolve(inst, np.ones(k) / k, mode="valid")[SR // 2: -SR // 2] / 1000.0 - 1.0  # (not the edges)
    dev -= np.median(dev)
    f, p = welch(dev, SR, nperseg=len(dev) // 2)
    return float(np.max(np.abs(dev))), float(f[np.argmax(p * (f < 5))])


def measure(flac: Path) -> dict:
    record, params, mix, dry = remake(flac)
    taps: dict = {}
    wet = disc.record(dry.copy(), SR, mix.disc, params.seed, taps)
    pcm = master.to_pcm16(master.master(wet, SR), seed=params.seed)
    same = master.pcm_sha256(pcm) == record["id"]
    mono = (dry[:, 0] + dry[:, 1]) / 2
    a, b = taps["begins"], taps["ends"]
    f, gain = transfer(mono[a:b], taps["music"][a:b])
    out = {"file": flac.name, "same samples": same, "horn": taps["horn"], "eccentric %": round(100 * taps["eccentric"], 3)}
    for drop in (3, 6, 10, 20):
        out[f"-{drop} dB"] = tuple(round(x) for x in edges(f, gain, drop))
    out["gain at"] = {hz: round(float(np.interp(hz, f, gain)), 1) for hz in (80, 100, 150, 200, 300, 500, 1000, 2000,
                                                                               3000, 4000, 5000, 6000, 8000, 12000)}
    peak, rate = wow_of(params.seed)
    out["wow peak %"], out["wow Hz"] = round(100 * peak, 3), round(rate, 3)
    level = disc._quick(taps["music"], SR)
    out["surface under the music LU"] = round(disc._quick(taps["surface"][a:b], SR) - level, 1)
    clicks = np.array([t for t, _s in taps["clicks"]])
    later = (clicks[None, :] - clicks[:, None]).ravel()
    out["clicks"] = len(clicks)
    out["clicks a second"] = round(len(clicks) / (len(wet) / SR), 2)
    out["heard again a revolution later"] = int(np.sum(np.abs(later - disc.TURN) < 1e-6))
    x = pcm / 32768.0
    m = x[:, 0]
    music = 10 * np.log10(np.mean(m[a:b] ** 2))
    lead = m[int(0.25 * SR): int(0.55 * SR)]
    out["lead-in under the music dB"] = round(10 * np.log10(np.mean(lead**2) + 1e-30) - music, 1) if a > 0.55 * SR else None
    if taps.get("runout") is not None:
        tail = m[taps["runout"] + int(0.5 * SR): len(m) - int(0.5 * SR)]
        out["run-out under the music dB"] = round(10 * np.log10(np.mean(tail**2) + 1e-30) - music, 1)
        out["run-out s"] = round((len(m) - taps["runout"]) / SR, 2)
    out["mono (before the dither)"] = bool(np.array_equal(wet[:, 0], wet[:, 1]))
    out["lufs"] = round(master.loudness(x, SR), 2)
    out["lra"] = round(master.loudness_range(x, SR), 1)
    out["true peak"] = round(master.true_peak(x), 2)
    out["length s"] = round(len(x) / SR, 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("flac", nargs="+")
    args = ap.parse_args()
    for f in args.flac:
        r = measure(Path(f))
        print(json.dumps(r, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
