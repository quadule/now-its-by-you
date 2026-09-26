"""What the throat's vocoder loses against the voice it resynthesizes, measured (dev only).

    uv run python tools/throat/vocoder_eval.py [SINGER/SEGMENT ...] [--seconds 12] [--features DIR]
        [--variant NAME [key=value ...]] [--world] [--render FILE ...] [--out DIR] [--mos]

Copy synthesis of house-singer segments: WORLD features (as tools/throat/features.py writes them)
through songbird.synth.throat.synthesize, against the SoulX original. Beside the log-mel distance,
the things a vocoder like WORLD is known to lose, each measured the same way on the original and
the resynthesis (docs/THROAT.md, "Vocoder"):

- periodicity (hnr_*): how alike each period is to the one before, per band, once the pair is
  aligned by the single lag that matches them best (so timing jitter alone costs nothing), as a
  harmonic-to-noise ratio r / (1 - r). From the signal resampled so every period of the f0 track
  has N samples, one DFT a period.
- coherence (coh_*): how steady each harmonic's period-to-period phase step stays over 8 periods,
  unaligned (timing jitter lowers it, the more the higher the harmonic); 1 steady, about 0.33 random.
- modulation (mod_*): the share of a band's energy in the loudest quarter of each period, folded
  from that period's own excitation (0.29 for noise, near 1 for a click every period).
- kurtosis (kurt_*): excess kurtosis of the band-passed signal over 30 ms of steady voicing, the
  louder half: how peaky the band is.
- level: the resynthesis against the original per band on voiced frames, and on unvoiced ones.
- mel: the log-mel distance tools/throat/copysynth.py prints (it is mostly the lowest bands);
  mel_hp the same with both signals high-passed at 50 Hz and the 0-133 Hz band left out. Neither
  should gate a change to the texture: a per-frame distance rewards the smoothest guess, and every
  move toward the original's irregularity costs it.

--render measures whole files instead (the learned engine singing, say) with their own Harvest f0,
beside the originals' figures. --mos scores every written file with UTMOS and DNSMOS
(renders/reference/mos/score.py, in its own venv). A variant is keyword arguments to
throat.Texture (texture=none for the plain WORLD-style vocoder).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfiltfilt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from songbird.synth import throat  # noqa: E402

DATA = Path("/Users/milo/Code/songbird/renders/throat")  # the corpus lives in the main checkout
BANDS = ((0, 1000), (1000, 2000), (2000, 4000), (4000, 6000), (6000, 8000), (8000, 11800))
# One refrain line and one other song per house singer; the lead's two held-out segments among them.
SEGMENTS = [f"{s}/{s}.{g}" for s, g in (
    ("house-alto", "h-now-its-by-you.01"), ("house-alto", "j-goes-like-this.01"),
    ("house-baritone", "h-now-its-by-you.01"), ("house-baritone", "a-nobody-knows.01"),
    ("house-bass", "h-now-its-by-you.01"), ("house-bass", "f-the-long-count.01"),
    ("house-breathy", "h-now-its-by-you.01"), ("house-breathy", "i-something-going-round.01"),
    ("house-bright", "h-now-its-by-you.01"), ("house-bright", "g-hweelonalay.01"),
    ("house-low-alto", "h-now-its-by-you.01"), ("house-low-alto", "c-somebody-sang-it.01"),
    ("house-mezzo", "h-now-its-by-you.01"), ("house-mezzo", "d-in-by-the-ear.01"),
    ("house-rough", "h-now-its-by-you.01"), ("house-rough", "k-still-you-grew.02"),
    ("house-soft-tenor", "h-now-its-by-you.01"), ("house-soft-tenor", "l-sticky-burr.01"),
    ("house-tenor", "h-now-its-by-you.01"), ("house-tenor", "e-nothing-of-you.01"),
)]


def load(key: str, features: Path, seconds: float | None) -> tuple[np.ndarray, int, dict]:
    singer, seg = key.split("/")
    x, sr = sf.read(str(DATA / "corpus" / singer / f"{seg}.wav"), dtype="float64")
    z = np.load(features / singer / f"{seg}.npz")
    f = {k: z[k].astype(np.float64) for k in ("f0", "sp", "ap")}
    if seconds:
        frames = int(round(seconds / throat.FRAME))
        f = {k: v[:frames] for k, v in f.items()}
        x = x[: int(round(frames * throat.FRAME * sr))]
    return x, sr, f


# ---- the f0 track as a phase, and the signal resampled onto it --------------------------------------

def phase_of(f0: np.ndarray, sr: int, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Cycles elapsed at every sample (unvoiced stretches paced at 100 Hz so it always rises), and
    which samples lie in steady voicing (the frame and four either side voiced)."""
    frames = np.arange(n) / sr / throat.FRAME
    f = np.interp(frames, np.arange(len(f0)), np.where(f0 > 0, f0, 100.0))
    voiced = f0 > 0
    steady = voiced.copy()
    for d in range(1, 5):
        steady[d:] &= voiced[:-d]
        steady[:-d] &= voiced[d:]
    k = np.clip(np.round(frames).astype(int), 0, len(f0) - 1)
    return np.cumsum(f / sr), steady[k]


class Warped:
    """A signal read at given phases (cycles) of its f0 track, through an 8x oversampled copy."""

    UP = 8

    def __init__(self, x: np.ndarray, phase: np.ndarray):
        self.up = resample_poly(x, self.UP, 1)
        self.phase = phase

    def at(self, cycles: np.ndarray) -> np.ndarray:
        idx = np.interp(cycles, self.phase, np.arange(len(self.phase)))
        return np.interp(idx * self.UP, np.arange(len(self.up)), self.up)


def windows(phase: np.ndarray, steady: np.ndarray, periods: int, hop_s: float, sr: int) -> list[float]:
    """Starting phases of runs of `periods` whole periods lying in steady voicing, about hop_s apart."""
    out = []
    step = max(int(hop_s * sr), 1)
    for c in range(0, len(phase), step):
        if not steady[c]:
            continue
        p0 = np.ceil(phase[c])
        end = np.searchsorted(phase, p0 + periods)
        if end < len(phase) and steady[c:end].all():
            out.append(p0)
    return out


def local_f0(phase: np.ndarray, p0: float, periods: int, sr: int) -> float:
    a, b = np.searchsorted(phase, [p0, p0 + periods])
    return periods * sr / max(b - a, 1)


def excitation(x: np.ndarray, sr: int) -> np.ndarray:
    return sosfiltfilt(butter(4, [1000, 4000], btype="bandpass", fs=sr, output="sos"), x) ** 2


def centred(x: np.ndarray, phase: np.ndarray, starts: list[float], sr: int, run: int) -> list[float]:
    """Each run's start moved so its periods' excitation (the peak of the 1-4 kHz energy, folded over
    the run) sits mid-window: a jittered pulse then stays in its own period."""
    ref = excitation(x, sr)
    out = []
    for p0 in starts:
        a, b = np.searchsorted(phase, [p0, p0 + run])
        where = ((phase[a:b] - p0) % 1.0 * 32).astype(int) % 32
        prof = np.bincount(where, weights=ref[a:b], minlength=32)
        peak = (np.argmax(np.convolve(np.concatenate([prof[-2:], prof, prof[:2]]), np.ones(5), mode="valid")) + 0.5) / 32
        out.append(p0 + peak - 0.5 if peak >= 0.5 else p0 + peak + 0.5)
    return out


N = 512  # samples per period after warping: harmonics to 256 x f0


def harmonics(w: Warped, phase: np.ndarray, p0: float, run: int) -> np.ndarray:
    """Complex harmonics 1..N/2-1 of `run` consecutive periods from p0, one rectangular DFT a period."""
    seg = w.at(p0 + np.arange(run * N) / N).reshape(run, N)
    return np.fft.rfft(seg, axis=1)[:, 1: N // 2]


def periodicity(w: Warped, phase: np.ndarray, starts: list[float], sr: int, run: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Per band: the harmonic-to-noise ratio (dB) of consecutive periods aligned by their best lag,
    and the unaligned coherence of each harmonic's period-to-period phase step, power-weighted."""
    hs = np.arange(1, N // 2)
    lags = np.linspace(-0.02, 0.02, 81)  # periods
    turn = np.exp(-2j * np.pi * lags[:, None] * hs[None, :])
    num, den, cnum, cden = (np.zeros(len(BANDS)) for _ in range(4))
    for p0 in starts:
        f0 = local_f0(phase, p0, run, sr)
        a = harmonics(w, phase, p0, run)
        cross = a[1:] * np.conj(a[:-1])  # (run - 1, harmonics)
        best = np.argmax((cross @ turn.T).real, axis=1)
        aligned = (cross * turn[best]).real
        norm = np.sqrt(np.abs(a[1:]) ** 2 * np.abs(a[:-1]) ** 2)
        steady = np.abs(np.exp(1j * np.angle(cross)).mean(axis=0))
        power = (np.abs(a) ** 2).mean(axis=0)
        for b, (lo, hi) in enumerate(BANDS):
            sel = (hs * f0 >= lo) & (hs * f0 < hi)
            num[b] += aligned[:, sel].sum()
            den[b] += norm[:, sel].sum()
            cnum[b] += (steady[sel] * power[sel]).sum()
            cden[b] += power[sel].sum()
    r = np.clip(num / np.maximum(den, 1e-20), 1e-4, 1 - 1e-6)
    return 10 * np.log10(r / (1 - r)), cnum / np.maximum(cden, 1e-20)


def modulation(x: np.ndarray, phase: np.ndarray, starts: list[float], sr: int, band: tuple[float, float],
               run: int = 16, bins: int = 16) -> float:
    """Share of a band's energy in the loudest quarter of the period (0.29 for noise with this
    estimator), each period folded from its own excitation, `run` periods at a time."""
    sos = butter(6, [band[0], min(band[1], 0.49 * sr)], btype="bandpass", fs=sr, output="sos")
    e = sosfiltfilt(sos, x) ** 2
    ref = excitation(x, sr)
    shares = []
    for p0 in starts:
        prof = np.zeros(bins)
        count = np.zeros(bins)
        for k in range(run):
            a, b = np.searchsorted(phase, [p0 + k, p0 + k + 1])
            if b - a < 4:
                continue
            peak = a + int(np.argmax(ref[a:b]))
            where = ((phase[a:b] - phase[peak]) % 1.0 * bins).astype(int) % bins
            prof += np.bincount(where, weights=e[a:b], minlength=bins)
            count += np.bincount(where, minlength=bins)
        prof /= np.maximum(count, 1)
        if prof.sum() <= 0:
            continue
        ring = np.concatenate([prof, prof])
        quarter = np.array([ring[i: i + bins // 4].sum() for i in range(bins)])
        shares.append(quarter.max() / prof.sum())
    return float(np.mean(shares)) if shares else float("nan")


def kurtosis(x: np.ndarray, steady: np.ndarray, sr: int, band: tuple[float, float]) -> float:
    """Excess kurtosis of the band-passed signal over 30 ms windows of steady voicing, the louder half."""
    y = sosfiltfilt(butter(6, [band[0], min(band[1], 0.49 * sr)], btype="bandpass", fs=sr, output="sos"), x)
    hop = int(0.03 * sr)
    ks, lv = [], []
    for a in range(0, len(y) - hop, hop):
        if not steady[a: a + hop].all():
            continue
        w = y[a: a + hop]
        m = np.mean(w**2)
        if m > 0:
            ks.append(np.mean(w**4) / m**2 - 3.0)
            lv.append(m)
    if not ks:
        return float("nan")
    ks, lv = np.array(ks), np.array(lv)
    return float(np.mean(ks[lv >= np.median(lv)]))


def measure(x: np.ndarray, sr: int, f0: np.ndarray) -> dict:
    """Every texture measure of one signal, on its f0 track."""
    phase, steady = phase_of(f0, sr, len(x))
    w = Warped(x, phase)
    eight = [p for p in centred(x, phase, windows(phase, steady, 9, 0.04, sr), sr, 8) if p + 8 < phase[-1]]
    sixteen = windows(phase, steady, 16, 0.05, sr)
    out = {}
    for (lo, hi), h, c in zip(BANDS, *periodicity(w, phase, eight, sr)):
        out[f"hnr_{lo // 1000}k"] = float(h)
        out[f"coh_{lo // 1000}k"] = float(c)
    for name, band in (("1-3k", (1000, 3000)), ("4-8k", (4000, 8000)), ("8k+", (8000, 11800))):
        out[f"mod_{name}"] = modulation(x, phase, sixteen, sr, band)
    for name, band in (("1-3k", (1000, 3000)), ("3-5k", (3000, 5000)), ("5-8k", (5000, 8000))):
        out[f"kurt_{name}"] = kurtosis(x, steady, sr, band)
    return out


def logmel(x: np.ndarray, sr: int, n: int = 80) -> np.ndarray:
    import librosa

    m = librosa.feature.melspectrogram(y=x.astype(np.float32), sr=sr, n_fft=1024, hop_length=120, n_mels=n, fmax=sr / 2)
    return 10 * np.log10(np.maximum(m, 1e-10)).T


def spectral(x: np.ndarray, y: np.ndarray, f0: np.ndarray, sr: int) -> dict:
    """Log-mel distances (dB, frames within 40 dB of the original's peak) and the resynthesis's level
    against the original's per band on voiced frames, and overall on unvoiced ones."""
    import librosa

    a, b = logmel(x, sr), logmel(y, sr)
    k = min(len(a), len(b))
    a, b = a[:k], b[:k]
    loud = a.max(axis=1) > a.max() - 40
    hp = butter(4, 50.0, btype="highpass", fs=sr, output="sos")
    ah, bh = logmel(sosfiltfilt(hp, x), sr)[:k], logmel(sosfiltfilt(hp, y), sr)[:k]
    fr = np.clip(np.round(np.arange(k) * 120 / sr / throat.FRAME).astype(int), 0, len(f0) - 1)
    v = loud & (f0[fr] > 0)
    u = loud & (f0[fr] == 0)
    freqs = librosa.mel_frequencies(n_mels=a.shape[1], fmax=sr / 2)

    def level(s, m, sel):
        return 10 * np.log10(np.mean(10 ** (s[m][:, sel] / 10)))

    out = {"mel": float(np.sqrt(np.mean((a[loud] - b[loud]) ** 2))),
           "mel_hp": float(np.sqrt(np.mean((ah[loud][:, 1:] - bh[loud][:, 1:]) ** 2)))}
    for lo, hi in BANDS:
        sel = (freqs >= lo) & (freqs < hi)
        out[f"level_{lo // 1000}k"] = float(level(b, v, sel) - level(a, v, sel)) if v.any() else float("nan")
    every = np.ones(a.shape[1], dtype=bool)
    out["level_unvoiced"] = float(level(b, u, every) - level(a, u, every)) if u.any() else float("nan")
    return out


def render_measures(path: Path, seconds: float) -> dict:
    """The texture measures of a whole file (the learned engine singing, say), on its own Harvest f0,
    at 24 kHz like the corpus."""
    import pyworld as pw

    x, sr = sf.read(str(path), dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != throat.RATE:
        x = resample_poly(x, throat.RATE // np.gcd(sr, throat.RATE), sr // np.gcd(sr, throat.RATE))
        sr = throat.RATE
    x = x[: int(seconds * sr)]
    f0, _ = pw.harvest(x, sr, f0_floor=70.0, f0_ceil=900.0, frame_period=throat.FRAME * 1000)
    n = int(round(len(f0) * throat.FRAME * sr))
    x = np.concatenate([x, np.zeros(max(0, n - len(x)))])[:n]
    return measure(x, sr, f0)


def texture_of(kv: list[str]) -> throat.Texture:
    """A variant's Texture from key=value pairs over the default one; texture=none for none at all."""
    pairs = dict(item.split("=", 1) for item in kv)
    base = throat.PLAIN if pairs.pop("texture", "") == "none" else throat.TEXTURE
    return replace(base, **{k: float(v) for k, v in pairs.items()})


def main() -> None:
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMBA_NUM_THREADS"):
        os.environ.setdefault(var, "2")  # a shared machine
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("segments", nargs="*", default=SEGMENTS)
    ap.add_argument("--features", type=Path, default=DATA / "features")
    ap.add_argument("--seconds", type=float, default=12.0, help="the first so many seconds of each segment")
    ap.add_argument("--variant", nargs="+", action="append", default=[], metavar=("NAME", "KEY=VALUE"))
    ap.add_argument("--world", action="store_true", help="also pyworld's own resynthesis from full-resolution features")
    ap.add_argument("--render", nargs="+", type=Path, default=[], help="measure these whole files instead")
    ap.add_argument("--out", type=Path, default=None, help="write every signal here as a wav (and results.json)")
    ap.add_argument("--mos", action="store_true", help="score the written files with UTMOS and DNSMOS (needs --out)")
    args = ap.parse_args()
    if args.render:
        rows = {p.stem: {"all": render_measures(p, 60.0)} for p in args.render}
        if args.mos:
            mos = score_mos(args.render)
            for p in args.render:
                rows[p.stem]["all"] |= mos.get(p.stem, {})
        report(rows)
        return
    variants = {v[0]: texture_of(v[1:]) for v in args.variant} or {"ours": throat.TEXTURE}
    rows: dict[str, dict[str, dict]] = {}
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    for key in args.segments:
        x, sr, f = load(key, args.features, args.seconds)
        sigs = {"original": x}
        if args.world:
            import pyworld as pw

            t = np.arange(len(f["f0"])) * throat.FRAME
            fft = pw.get_cheaptrick_fft_size(sr, 50.0)
            sp = pw.cheaptrick(x, f["f0"], t, sr, fft_size=fft)
            sigs["world"] = pw.synthesize(f["f0"], sp, pw.d4c(x, f["f0"], t, sr, fft_size=fft), sr, frame_period=5.0)[: len(x)]
        for name, texture in variants.items():
            sigs[name] = throat.synthesize(f["f0"], f["sp"], f["ap"], sr, np.random.default_rng(0), texture=texture)[: len(x)]
        seg = key.split("/")[1]
        for name, y in sigs.items():
            y = np.concatenate([y, np.zeros(len(x) - len(y))])
            r = measure(y, sr, f["f0"])
            if name != "original":
                r |= spectral(x, y, f["f0"], sr)
            rows.setdefault(name, {})[seg] = r
            if args.out:
                sf.write(str(args.out / f"{seg}.{name}.wav"), (0.9 * y / max(np.abs(y).max(), 1e-9)).astype(np.float32), sr)
        print(f"{key}: " + "  ".join(f"{n} mel_hp {rows[n][seg].get('mel_hp', 0):.2f}" for n in sigs), flush=True)
    if args.mos and args.out:
        mos = score_mos(sorted(args.out.glob("*.wav")))
        for name in rows:
            for seg in rows[name]:
                rows[name][seg] |= mos.get(f"{seg}.{name}", {})
    report(rows)
    if args.out:
        (args.out / "results.json").write_text(json.dumps(rows, indent=1))


MOS_PYTHON = "/Users/milo/Code/mos/.venv/bin/python"
MOS_SCRIPT = """
import json, sys
sys.path.insert(0, "/Users/milo/Code/songbird/renders/reference/mos")
import score
out = {}
for path in sys.argv[1:]:
    s = score.score_file(path, window_s=8.0, min_window_s=2.0)["summary"]
    out[path.rsplit("/", 1)[1].rsplit(".", 1)[0]] = {k: s[k]["mean"] for k in ("utmos", "dnsmos_sig", "dnsmos_ovrl")}
print(json.dumps(out))
"""


def score_mos(paths: list[Path]) -> dict:
    """UTMOS and DNSMOS for every file, in the MOS scorer's own venv (one model load)."""
    done = subprocess.run([MOS_PYTHON, "-W", "ignore", "-c", MOS_SCRIPT, *map(str, paths)], capture_output=True, text=True,
                          check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def report(rows: dict[str, dict[str, dict]]) -> None:
    """Each measure's mean over segments, per signal."""
    names = list(rows)
    keys = list(dict.fromkeys(k for n in names for r in rows[n].values() for k in r))
    print(f"{'':15}" + "".join(f"{n[:12]:>13}" for n in names))
    for k in keys:
        vals = []
        for n in names:
            v = [r[k] for r in rows[n].values() if k in r and np.isfinite(r[k])]
            vals.append(np.mean(v) if v else np.nan)
        print(f"{k:15}" + "".join(f"{v:13.3f}" for v in vals))


if __name__ == "__main__":
    main()
