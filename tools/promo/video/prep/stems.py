"""The stems for the film, from the instrumented replay's dry stems (replay.py), written to
renders/promo/video/data/stems/.

    uv run python tools/promo/video/prep/stems.py

stems/<part>.wav: 16-bit mono at 44.1 kHz, (left + right) / 2 of the dry stem, every part times one shared gain
(stems/gain.json) so levels compare across parts. stems/<part>.env (.bin + .json) and stems/mix.env (the release
file itself): per video frame, RMS, peak, a spectral-flux onset value and 96 log-spaced band levels.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DURATION, FPS, RELEASE, ROOT, SCRATCH, guard, out, say, write_array, write_json  # noqa: E402

RENDER = guard(SCRATCH / "replay" / "render.flac")
SR = 44100
FRAMES = int(np.ceil(DURATION * FPS))  # 9,074: frame i at i / 60 s, the last at 151.217
BANDS = 96
LO, HI = 40.0, 16000.0
NFFT = 4096
FLUX_FFT = 1024
FLOOR = -100.0  # dB: the stored range is FLOOR..0
SCALE = -FLOOR / 255.0
FLUX_SCALE = 0.25  # dB a step for the flux column
PEAK_DB = -1.0  # the loudest stem's peak after the shared gain


def stem_files() -> dict[str, Path]:
    prefix = RENDER.stem + "."
    found = {p.name[len(prefix):-4]: p for p in sorted(RENDER.parent.glob(prefix + "*.wav"))}
    if not found:
        raise SystemExit(f"no stems beside {RENDER}: run replay.py first")
    return found


def edges() -> np.ndarray:
    return np.exp(np.linspace(np.log(LO), np.log(HI), BANDS + 1))


def envelope(y: np.ndarray, sr: int = SR) -> np.ndarray:
    """(FRAMES, 3 + BANDS) uint8: [RMS dB, peak dB, flux, band dB...], frame i centred on i / 60 s.
    y: (samples, channels) float, full scale 1."""
    if y.ndim == 1:
        y = y[:, None]
    half = sr // (2 * FPS)
    pad = NFFT
    total = int(np.ceil(FRAMES * sr / FPS)) + 2 * pad + NFFT  # the stems end at the score's end: silence after
    z = np.pad(y, ((pad, max(0, total - pad - len(y))), (0, 0)))
    centres = np.round(np.arange(FRAMES) * sr / FPS).astype(np.int64) + pad
    win = np.hanning(NFFT)
    norm = 2.0 / (NFFT * np.sum(win ** 2))  # a sine of amplitude A reads A^2 / 2 summed over its band
    freqs = np.fft.rfftfreq(NFFT, 1.0 / sr)
    e = edges()
    centre = np.sqrt(e[:-1] * e[1:])
    out = np.zeros((FRAMES, 3 + BANDS), dtype=np.float64)
    last = None
    win_f = np.hanning(FLUX_FFT)
    freqs_f = np.fft.rfftfreq(FLUX_FFT, 1.0 / sr)

    def bands(spec, fq):
        cum = np.concatenate([np.zeros((len(spec), 1)), np.cumsum(spec, axis=1)], axis=1)
        lo, hi = np.searchsorted(fq, e[:-1]), np.searchsorted(fq, e[1:])
        band = cum[:, hi] - cum[:, lo]
        thin = hi <= lo  # a band narrower than a bin: the bin's density at its centre, times its width
        if thin.any():
            dens = np.stack([np.interp(centre[thin], fq, x) for x in spec]) / (fq[1] - fq[0])
            band[:, thin] = dens * (e[1:] - e[:-1])[thin]
        return np.maximum(10 * np.log10(np.maximum(band, 1e-30)), FLOOR)

    for a in range(0, FRAMES, 512):
        c = centres[a:a + 512]
        idx = c[:, None] + np.arange(-half, half)[None, :]
        seg = z[idx]  # (frames, 735, ch)
        rms = np.sqrt(np.mean(seg ** 2, axis=(1, 2)))
        peak = np.max(np.abs(seg), axis=(1, 2))
        fidx = c[:, None] + np.arange(-NFFT // 2, NFFT // 2)[None, :]
        spec = np.mean(np.abs(np.fft.rfft(z[fidx] * win[None, :, None], axis=1)) ** 2, axis=2) * norm
        db = bands(spec, freqs)
        # the flux from a short window (FLUX_FFT) centred on the frame, so an onset lands on its own frame
        gidx = c[:, None] + np.arange(-FLUX_FFT // 2, FLUX_FFT // 2)[None, :]
        short = bands(np.mean(np.abs(np.fft.rfft(z[gidx] * win_f[None, :, None], axis=1)) ** 2, axis=2)
                      * (2.0 / (FLUX_FFT * np.sum(win_f ** 2))), freqs_f)
        prev = np.vstack([last if last is not None else short[:1], short[:-1]])
        flux = np.mean(np.maximum(short - prev, 0.0), axis=1)
        last = short[-1:]
        out[a:a + len(c), 0] = np.maximum(20 * np.log10(np.maximum(rms, 1e-30)), FLOOR)
        out[a:a + len(c), 1] = np.maximum(20 * np.log10(np.maximum(peak, 1e-30)), FLOOR)
        out[a:a + len(c), 2] = flux
        out[a:a + len(c), 3:] = db
    q = np.empty(out.shape, dtype=np.uint8)
    q[:, :2] = np.clip(np.round((out[:, :2] - FLOOR) / SCALE), 0, 255)
    q[:, 2] = np.clip(np.round(out[:, 2] / FLUX_SCALE), 0, 255)
    q[:, 3:] = np.clip(np.round((out[:, 3:] - FLOOR) / SCALE), 0, 255)
    return q


ABOUT = ("per video frame (frame i centred on i / 60 s): column 0 RMS dBFS over the frame's 1/60 s, 1 peak dBFS, "
         "2 spectral flux (the mean rise in dB over the 96 bands since the frame before, from a 1024-point "
         "Hann window centred on the frame: v * flux_scale dB), "
         "3.. the 96 band levels in dB (a sine of amplitude 1 in a band reads -3 dB, as its RMS does) from a "
         "4096-point Hann window centred on the frame, bands log-spaced 40 Hz to 16 kHz (band_edges_hz); "
         "columns 0, 1 and 3.. are dB = v * scale + offset, v 0 meaning at or below -100 dB")


def write_env(name: str, y: np.ndarray, **extra) -> None:
    write_array(f"stems/{name}.env", envelope(y), ABOUT, rate=float(FPS), t0=0.0, scale=SCALE, offset=FLOOR,
                flux_scale=FLUX_SCALE, band_edges_hz=[round(float(x), 3) for x in edges()], **extra)


def main() -> None:
    files = stem_files()
    peaks = {}
    for name, p in files.items():
        y, sr = sf.read(str(p), dtype="float64", always_2d=True)
        assert sr == SR
        peaks[name] = float(np.max(np.abs(y.mean(axis=1)))) if len(y) else 0.0
    gain = 10 ** (PEAK_DB / 20) / max(peaks.values())
    for name, p in files.items():
        y, _ = sf.read(str(p), dtype="float64", always_2d=True)
        mono = y.mean(axis=1) * gain
        sf.write(str(out(f"stems/{name}.wav")), np.round(np.clip(mono, -1, 1) * 32767).astype(np.int16), SR,
                 subtype="PCM_16")
        write_env(name, y, part=name, source=str(p.relative_to(ROOT)))
        say(f"stem {name}: peak {20 * np.log10(max(peaks[name], 1e-12)):.1f} dBFS dry")
    mix, sr = sf.read(str(guard(RELEASE)), dtype="float64", always_2d=True)
    write_env("mix", mix, part="mix", source="renders/release/now-its-by-you-awards-draft.flac")
    write_json("stems/gain.json", {
        "gain": gain, "gain_db": round(20 * np.log10(gain), 3), "peak_db_after": PEAK_DB, "loudest": max(peaks, key=peaks.get),
        "parts": list(files),
        "dry_peak_db": {k: round(20 * np.log10(max(v, 1e-12)), 3) for k, v in peaks.items()},
        "about": "every stems/<part>.wav is (left + right) / 2 of the replay's dry stem times this one gain, so the "
                 "loudest part peaks at -1 dBFS and all compare; the .env files are measured on the dry float stems "
                 "themselves (both channels, full scale 1), before this gain"}, indent=1)
    say(f"stems: {len(files)} parts, shared gain {20 * np.log10(gain):+.2f} dB")


if __name__ == "__main__":
    main()
