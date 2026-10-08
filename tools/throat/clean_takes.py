"""The volunteers' takes with the guide's leak and the room's steady noise taken out (dev only; private, temporary).

    uv run python tools/throat/clean_takes.py [OUT] [--only singer-a,singer-b] [--taps 128] [--floor-db -12] [--jobs 6]
    uv run python tools/throat/volunteers.py cut WORK --takes OUT/takes      # then the pipeline as usual

OUT defaults to songbird-volunteers/cleaned/ in the system's temporary folder (never the checkout).
Read-only on recordings/: every take that tools/throat/volunteers.py would cut (its counts()) is
written to OUT/takes/<singer>/<name>.wav, with its
sidecar copied beside it field for field plus a "cleaned" field saying what was done. A take that needs
nothing is linked, not copied. OUT/report.json has every take's numbers, OUT/guides/ the re-rendered guides.

What is done to a take, in order:

1. The guide's leak, cancelled. A take sung without headphones and without echo cancellation carries
   the guide from the speaker. Its guide is rendered again from the score it was sung to
   (recordings/guides/<song>.<digest>.score.json) exactly as tools/sing_site.py makes the site's MP3:
   tools/guides.py's render_melody, mastered to 16 bits, encoded with ffmpeg at the melody's bitrate and
   decoded, gapless, at the take's rate. It is found in the take by cross-correlation (GCC-PHAT) around
   where the sidecar puts it (the take's sample 0 is guide time from_s + shift_ms), looked for in its
   gaps between sung lines, where only the leak and the room are. Then a least-squares FIR (--taps, 128
   at 48 kHz: 2.7 ms, starting a quarter of a millisecond before the direct sound), the speaker's and the
   room's colouring of the guide, is fitted on the whole take and subtracted from it. (Fitted on the gaps
   alone it would learn only the pulse, a woodblock with nothing under 600 Hz, and it added 3-5 dB to the
   sung lines under 600 Hz where it guessed at the whistle; over the whole take the singing, which isn't
   correlated with the guide's waveform, only adds noise to the fit.) The leak is measured in the gaps
   and in the lines before and after, the filter fitted on alternate 2-second blocks and measured on the
   others, so the number isn't the fit flattering itself. Nothing is subtracted unless the guide stands
   out of the correlation (a leak), the held-out gaps come down by at least 1 dB and the held-out lines
   don't go up.
   A take sung to the "full" guide heard the machine's voice too, which was changed after it was sung:
   only the band re-renders as it was, so only --full cancels it (partly), and by default it is left be.
   Then what the filter left of the leak (the speaker's distortion, the room's tail past 2.7 ms) is
   turned down where the predicted leak is loud, as an echo canceller's post-filter does: per STFT bin,
   the share of the predicted leak's power still in the take is read from the gaps, and the bin's
   power gain is 1 - share x leak/take, smoothed, never under --floor-db (--no-residual leaves it).
2. The steady noise, gated. From the quietest 10% of the (leak-cancelled) take's STFT frames, a noise
   spectrum; each bin's power gain is 1 - 1.5 x noise/power, smoothed over neighbouring frames and
   bins, and never under --floor-db (default -12 dB): gentle on purpose, as this is training data for a
   spectral-envelope model, where a hollowed vowel is worse than a little hiss. Only a take whose
   background (measured as volunteers.py measures it) is still within --gate-above dB (default 30) of its
   singing is gated: a take that is clean enough already isn't touched, since gating costs it something.

The pipeline is then run on OUT/takes as it is on recordings/ (volunteers.py cut --takes; see
desktop/rebuild.sh in the work directory).

PRIVACY: cleaned takes are still recordings of people. OUT, and every work directory and dataset
made from it, is deleted with the originals, by the end of 2026-09-30 (Pacific).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).parent))

import takes as K  # noqa: E402

DEFAULT_OUT = Path(tempfile.gettempdir()) / "songbird-volunteers" / "cleaned"  # people's voices: never the checkout
FRAME = 0.005
REACH = 0.6  # seconds either side of the sidecar's placement the leak is looked for
PRE = 0.25e-3  # seconds of the filter before the direct sound (sub-sample and the decoder's slop)


# --- the guide, as the singer's speaker played it -------------------------------------------------------


def guide_audio(song: str, digest: str, mix: str, rate: int, out: Path) -> tuple[np.ndarray, dict]:
    """The guide a take was sung to, as the page decoded it, mono at `rate`; and what was found of it
    (the MP3's bitrate, whether it is byte for byte the site's). Cached in out/."""
    import sing_site as S

    out.mkdir(parents=True, exist_ok=True)
    mp3 = out / f"{digest}.{mix}.mp3"
    info_path = out / f"{digest}.{mix}.json"
    if not mp3.exists():
        import guides as M
        import soundfile as sf
        from songbird import synth
        from songbird.synth import master

        score, data = M.load_score(K.guide_score(song, digest))
        seed = int(data.get("seed", 0))
        if mix == "melody":
            x = M.render_melody(score, [(float(t), bool(b)) for t, b in data["beats"]], synth.SR, seed)
            rates = [S.MELODY_BITRATE, S.BITRATE]
        else:  # the band as it was, the machine's voice as it is now (it changed after these were sung)
            from songbird.synth import mixing

            x = mixing.mix(synth.render_stems(score, synth.SR, seed), synth.SR, seed)
            rates = [S.BITRATE]
        wav = out / f"{digest}.{mix}.wav"
        sf.write(str(wav), master.to_pcm16(master.master(x, synth.SR), seed=seed), synth.SR, subtype="PCM_16")
        enc = S.encode_first(wav, mp3, rates)
        wav.unlink()
        info = {"bitrate_kbps": round(enc["bytes"] * 8 / enc["seconds"] / 1000)}
        # the site's own MP3 for this guide, if the site still offers it: are they the same?
        spec = data.get("spec") or {}
        site = ROOT / "web/sing/public/song" / f"{M.Spec(spec['set'], spec.get('key', 0), spec.get('tempo', 100)).id}.{mix}.mp3" \
            if spec.get("set") else None
        song_json = ROOT / "web/sing/public/song/song.json"
        if site and site.exists() and song_json.exists():
            sj = json.loads(song_json.read_text())
            g = sj["guides"].get(site.name.split(f".{mix}.")[0], {})
            if g.get("guide") == digest:
                a, b = S.decode(mp3, 44100), S.decode(site, 44100)
                n = min(len(a), len(b))
                res = b[:n] - a[:n]
                info["site_mp3"] = site.relative_to(ROOT).as_posix()
                info["same_bytes"] = mp3.read_bytes() == site.read_bytes()
                info["site_corr"] = round(float(np.dot(a[:n], b[:n]) / np.sqrt(np.dot(a[:n], a[:n]) * np.dot(b[:n], b[:n]))), 6)
                info["site_diff_db"] = round(float(10 * np.log10(np.dot(res, res) / np.dot(b[:n], b[:n]) + 1e-30)), 1)
            else:
                info["site_mp3"] = None  # the site has moved on to another guide for this spec
        info_path.write_text(json.dumps(info))
    return S.decode(mp3, rate), json.loads(info_path.read_text())


# --- where the guide was singing, and the take's background as volunteers.py measures it ----------------


def voice_notes(song: str, digest: str) -> list[dict]:
    data = json.loads(K.guide_score(song, digest).read_text())
    return sorted((n for n in data["notes"] if n["part"] == "voice"), key=lambda n: n["start"])


def frame_mask(notes: list[dict], from_s: float, nfr: int, clear: float = 0.35) -> np.ndarray:
    """Per 5 ms frame of the take: True where the guide sings (within `clear` s of a note)."""
    expect = np.zeros(nfr, dtype=bool)
    for n in notes:
        a = int(round((n["start"] - clear - from_s) / FRAME))
        b = int(round((n["start"] + n["dur"] + clear - from_s) / FRAME))
        expect[max(a, 0): max(min(b, nfr), 0)] = True
    return expect


def measure(y: np.ndarray, sr: int, expect_fn) -> dict:
    """The take's singing and background levels exactly as volunteers.cut_take measures them (at 24 kHz)."""
    import pyworld as pw
    from scipy.signal import resample_poly

    y24 = resample_poly(y, 24000, sr) if sr != 24000 else y
    x16 = resample_poly(y24, 16000, 24000)
    f0, _ = pw.harvest(x16, 16000, f0_floor=60.0, f0_ceil=900.0, frame_period=FRAME * 1000)
    hop = int(FRAME * 24000)
    nfr = len(f0)
    level = 20 * np.log10(np.maximum(np.array([np.sqrt(np.mean(y24[i * hop: i * hop + 2 * hop] ** 2) + 1e-20)
                                               for i in range(nfr)]), 1e-6))
    expect = expect_fn(nfr)
    sung, quiet = (f0 > 0) & expect, ~expect
    sing_db = float(np.median(level[sung])) if sung.any() else -120.0
    back_db = float(np.median(level[quiet])) if quiet.sum() >= 40 else None
    return dict(singing_db=round(sing_db, 1), background_db=None if back_db is None else round(back_db - sing_db, 1),
                voiced_in_gaps=round(float(np.mean(f0[quiet] > 0)), 3) if quiet.sum() >= 40 else None)


# --- 1. the leak ------------------------------------------------------------------------------------------


def gcc_phat(y: np.ndarray, ref: np.ndarray, reach: int, sr: int) -> tuple[int, float]:
    """Where the guide leaks into y: the offset (samples) at which y[n] ~ ref[n + offset], looked for in
    0..2*reach (ref starts `reach` samples before the sidecar's placement), by GCC-PHAT over 200 Hz to
    4 kHz (a phone's speaker, and the whistle's range); and how far the peak stands above the median."""
    n = len(y) + len(ref)
    nfft = 1 << (n - 1).bit_length()
    X = np.fft.rfft(y, nfft) * np.conj(np.fft.rfft(ref, nfft))
    X /= np.abs(X) + 1e-12
    f = np.fft.rfftfreq(nfft, 1 / sr)
    X[(f < 200) | (f > 4000)] = 0
    cc = np.fft.irfft(X, nfft)  # cc[k] = sum y[m + k] ref[m]: y[n] = ref[n + off] peaks at k = -off
    vals = cc[(-np.arange(0, 2 * reach + 1)) % nfft]
    i = int(np.argmax(vals))
    return i, float(vals[i] / (np.median(np.abs(vals)) + 1e-18))


def fit_fir(y: np.ndarray, ref: np.ndarray, offset: int, taps: int, pre: int, where: np.ndarray,
            ridge: float = 1e-4) -> np.ndarray:
    """Least squares: y[n] ~ sum_k h[k] ref[n + offset + pre - k] over the samples `where` (bool)."""
    idx = np.flatnonzero(where)
    R = np.zeros((taps, taps))
    p = np.zeros(taps)
    for s in range(0, len(idx), 40000):
        j = idx[s: s + 40000]
        base = j + offset + pre
        G = np.stack([ref[np.clip(base - k, 0, len(ref) - 1)] for k in range(taps)], axis=1)
        R += G.T @ G
        p += G.T @ y[j]
    R += ridge * np.trace(R) / taps * np.eye(taps)
    return np.linalg.solve(R, p)


def apply_fir(ref: np.ndarray, h: np.ndarray, offset: int, pre: int, n: int) -> np.ndarray:
    """The leak the filter predicts, for take samples 0..n-1."""
    from scipy.signal import fftconvolve

    full = fftconvolve(ref, h)  # full[m] = sum_k h[k] ref[m - k]
    m = np.arange(n) + offset + pre
    ok = (m >= 0) & (m < len(full))
    out = np.zeros(n)
    out[ok] = full[m[ok]]
    return out


def db(x: np.ndarray) -> float:
    return float(10 * np.log10(np.mean(x ** 2) + 1e-20))


def cancel_leak(y: np.ndarray, sr: int, guide: np.ndarray, start: float, gaps: np.ndarray, taps: int) -> tuple[np.ndarray, dict]:
    """The take with the guide's leak taken out, and the numbers. start: guide time (s) of the take's sample 0
    by its sidecar; gaps: per sample, True where only the leak and the room are there."""
    reach = int(REACH * sr)
    a = int(round(start * sr)) - reach
    ref = np.zeros(len(y) + 2 * reach + 4 * taps)
    lo, hi = max(a, 0), min(a + len(ref), len(guide))
    if hi > lo:
        ref[lo - a: hi - a] = guide[lo:hi]
    # coarse: y[n] ~ ref[n + offset], offset around `reach`
    off, prom = gcc_phat(y * gaps, ref[: len(y) + 2 * reach], reach, sr)
    lag_ms = (off - reach) / sr * 1000  # the leak later than the sidecar says: negative
    pre = int(round(PRE * sr)) + 4
    info = dict(lag_ms=round(-lag_ms, 1), prominence=round(prom, 1), taps=taps)
    if prom < 6:
        return y, dict(info, cancelled=False, why="no leak stands out of the correlation")
    # fitted on the whole take: the gaps alone hold only the pulse (a woodblock, nothing under 600 Hz), so a
    # filter fitted there knows nothing of the whistle's fundamentals and adds to the lines what it guesses
    # there; the singing is as good as uncorrelated with the guide's waveform, so over the whole take it
    # only adds noise to the fit. Fitted on alternate 2-second blocks, measured on the others.
    block = (np.arange(len(y)) // (2 * sr)) % 2 == 0
    held = np.empty(len(y))
    for part in (block, ~block):
        h_part = fit_fir(y, ref, off, taps, pre, part)
        held[~part] = (y - apply_fir(ref, h_part, off, pre, len(y)))[~part]
    h = fit_fir(y, ref, off, taps, pre, np.ones(len(y), dtype=bool))
    leak = apply_fir(ref, h, off, pre, len(y))
    out = y - leak
    lines = ~gaps
    info.update(gaps_before_db=round(db(y[gaps]), 1), gaps_after_db=round(db(out[gaps]), 1),
                gaps_after_heldout_db=round(db(held[gaps]), 1), leak_in_gaps_db=round(db(leak[gaps]), 1),
                reduction_heldout_db=round(db(y[gaps]) - db(held[gaps]), 1),
                lines_before_db=round(db(y[lines]), 1), lines_after_db=round(db(out[lines]), 1),
                lines_after_heldout_db=round(db(held[lines]), 1), leak_in_lines_db=round(db(leak[lines]), 1),
                peak_tap_ms=round((int(np.argmax(np.abs(h))) - pre) / sr * 1000, 2))
    if db(y[gaps]) - db(held[gaps]) < 1.0:
        return y, dict(info, cancelled=False, why="the fitted filter doesn't bring the held-out gaps down")
    if db(held[lines]) > db(y[lines]) + 0.1:
        return y, dict(info, cancelled=False, why="the fitted filter adds to the sung lines (held out)")
    return out, dict(info, cancelled=True, _leak=leak)


def suppress_residual(e: np.ndarray, leak: np.ndarray, sr: int, gaps: np.ndarray, floor_db: float = -12.0,
                      over: float = 1.0) -> tuple[np.ndarray, dict]:
    """What the filter left of the leak (the speaker's distortion, the room's tail past the filter), turned
    down where the leak is loud: an echo canceller's post-filter. Per STFT bin, how much of the predicted
    leak's power is still there is read from the gaps (the residual's power regressed on the predicted
    leak's, frame by frame: |E|^2 ~ noise + beta |L|^2); each bin's power gain is then
    1 - over x beta |L|^2 / |E|^2, smoothed, never under floor_db."""
    from scipy.ndimage import uniform_filter
    from scipy.signal import istft, stft

    nper = 1 << int(round(np.log2(0.043 * sr)))
    kw = dict(nperseg=nper, noverlap=nper * 3 // 4)
    _, _, E = stft(e, sr, **kw)
    _, _, L = stft(leak, sr, **kw)
    PE, PL = np.abs(E) ** 2, np.abs(L) ** 2
    hop = nper // 4
    centre = np.clip(np.arange(E.shape[1]) * hop, 0, len(gaps) - 1)
    g_fr = gaps[centre]
    a, b = PL[:, g_fr], PE[:, g_fr]
    am, bm = a.mean(axis=1, keepdims=True), b.mean(axis=1, keepdims=True)
    beta = np.clip(((a - am) * (b - bm)).sum(axis=1) / (((a - am) ** 2).sum(axis=1) + 1e-30), 0, 1)
    beta = uniform_filter(beta, size=5, mode="nearest")[:, None]
    PEs = uniform_filter(PE, size=(3, 3), mode="nearest")
    PLs = uniform_filter(PL, size=(3, 3), mode="nearest")
    g = np.maximum(1 - over * beta * PLs / (PEs + 1e-30), 10 ** (floor_db / 10))
    g = uniform_filter(g, size=(3, 3), mode="nearest")
    _, out = istft(E * np.sqrt(g), sr, **kw)
    out = out[: len(e)]
    out = np.pad(out, (0, len(e) - len(out)))
    lines = ~g_fr
    return out, dict(beta_median_db=round(float(10 * np.log10(np.median(beta) + 1e-20)), 1),
                     gain_in_lines_db=round(float(10 * np.log10(np.mean(g[:, lines]))), 1) if lines.any() else None,
                     gain_in_gaps_db=round(float(10 * np.log10(np.mean(g[:, g_fr]))), 1) if g_fr.any() else None)


# --- 2. the steady noise ----------------------------------------------------------------------------------


def gate(y: np.ndarray, sr: int, floor_db: float = -12.0, over: float = 1.5, quiet: float = 0.10) -> tuple[np.ndarray, dict]:
    """Spectral gating (a power-subtraction Wiener-style gain with a floor), gentle."""
    from scipy.ndimage import uniform_filter
    from scipy.signal import istft, stft

    nper = 1 << int(round(np.log2(0.043 * sr)))  # about 43 ms: 2048 at 48 kHz
    f, _, X = stft(y, sr, nperseg=nper, noverlap=nper * 3 // 4)
    P = np.abs(X) ** 2
    e = P.sum(axis=0)
    q = e <= np.quantile(e, quiet)
    noise = P[:, q].mean(axis=1, keepdims=True)
    Ps = uniform_filter(P, size=(3, 5), mode="nearest")  # 3 bins, 5 frames: no musical noise
    floor = 10 ** (floor_db / 10)
    g = np.maximum(1 - over * noise / (Ps + 1e-20), floor)
    g = uniform_filter(g, size=(3, 3), mode="nearest")
    _, out = istft(X * np.sqrt(g), sr, nperseg=nper, noverlap=nper * 3 // 4)
    out = out[: len(y)]
    if len(out) < len(y):
        out = np.pad(out, (0, len(y) - len(out)))
    loud = e >= np.quantile(e, 0.5)  # the singing, roughly
    return out, dict(noise_floor_db=round(float(10 * np.log10(noise.sum() / nper + 1e-20)), 1),
                     gain_in_loud_frames_db=round(float(10 * np.log10(np.mean(g[:, loud]))), 1),
                     gain_in_quiet_frames_db=round(float(10 * np.log10(np.mean(g[:, q]))), 1),
                     nfft=nper)


def band_change(y: np.ndarray, x: np.ndarray, sr: int, lines: np.ndarray) -> dict:
    """How cleaning changed the singing's long-term spectrum: the louder half of the frames in the sung
    lines, their mean power per band after against before (dB). A hollowed or dulled voice shows here."""
    from scipy.signal import stft

    nper = 1 << int(round(np.log2(0.043 * sr)))
    f, _, Y = stft(y, sr, nperseg=nper, noverlap=nper // 2)
    _, _, X = stft(x, sr, nperseg=nper, noverlap=nper // 2)
    centre = np.clip(np.arange(Y.shape[1]) * (nper // 2), 0, len(lines) - 1)
    PY, PX = np.abs(Y) ** 2, np.abs(X) ** 2
    e = PY.sum(axis=0)
    use = lines[centre] & (e >= np.median(e[lines[centre]]))
    out = {}
    for lo, hi in ((80, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)):
        band = (f >= lo) & (f < hi)
        out[f"{lo}-{hi}"] = round(float(10 * np.log10(PX[band][:, use].sum() / (PY[band][:, use].sum() + 1e-30) + 1e-30)), 1)
    return out


# --- a take -----------------------------------------------------------------------------------------------


def clean_one(wav: str, out: str, taps48: int, floor_db: float, gate_above: float, full: bool, suppress: bool = True) -> dict:
    import soundfile as sf

    t = K.load(Path(wav))
    out = Path(out)
    y, sr = sf.read(str(t.path), dtype="float64")
    y = y if y.ndim == 1 else y.mean(axis=1)
    mix = t.info.get("mix") or "melody"
    notes = voice_notes(t.song, t.guide)
    from_s = t.from_s
    shift = float(t.info.get("shift_ms") or 0) / 1000
    rep = dict(take=t.rel, singer=t.who, seconds=round(len(y) / sr, 1), mix=mix, spec=t.spec, aec=t.info.get("aec"), rate=sr)
    expect = lambda nfr: frame_mask(notes, from_s, nfr)  # noqa: E731
    rep["before"] = measure(y, sr, expect)
    x = y
    done = []
    # the gaps, per sample: 0.35 s clear of every guide note (as the background is measured)
    nfr = int(np.ceil(len(y) / sr / FRAME)) + 1
    gaps = np.repeat(~frame_mask(notes, from_s, nfr), int(FRAME * sr))[: len(y)]
    gaps = np.pad(gaps, (0, len(y) - len(gaps)))
    rep["gaps_s"] = round(gaps.sum() / sr, 1)
    if mix == "melody" or full:
        if gaps.sum() < 2 * sr:
            rep["leak"] = dict(cancelled=False, why="under 2 s of gaps to fit a filter on")
        else:
            guide, ginfo = guide_audio(t.song, t.guide, mix, sr, out / "guides")
            rep["guide"] = dict(ginfo, digest=t.guide)
            taps = max(16, int(round(taps48 * sr / 48000)))
            x, rep["leak"] = cancel_leak(y, sr, guide, from_s + shift, gaps, taps)
            leak = rep["leak"].pop("_leak", None)
            if rep["leak"]["cancelled"]:
                done.append("leak")
                if suppress:
                    x, rep["residual"] = suppress_residual(x, leak, sr, gaps, floor_db)
                    done.append("residual")
    else:
        rep["leak"] = dict(cancelled=False, why="sung to the full guide, whose voice has changed since (--full to try)")
    mid = measure(x, sr, expect) if done else rep["before"]
    rep["after_leak"] = mid
    if mid["background_db"] is not None and mid["background_db"] > -gate_above:
        x, rep["gate"] = gate(x, sr, floor_db)
        done.append("gate")
        rep["after"] = measure(x, sr, expect)
    else:
        rep["after"] = mid
    rep["done"] = done
    if done:
        rep["singing_spectrum_change_db"] = band_change(y, x, sr, ~gaps)
    d = out / "takes" / t.who
    d.mkdir(parents=True, exist_ok=True)
    dest = d / t.path.name
    dest.unlink(missing_ok=True)
    if done:
        peak = np.max(np.abs(x))
        sf.write(str(dest), x * (0.99 / peak if peak > 0.99 else 1.0), sr, subtype="FLOAT")
    else:
        dest.symlink_to(t.path)  # nothing done: the take itself
    side = json.loads(t.sidecar().read_text()) if t.sidecar().exists() else {}
    side["cleaned"] = dict(done=done, original=t.rel, leak=rep.get("leak"), residual=rep.get("residual"), gate=rep.get("gate"))
    dest.with_suffix(".json").write_text(json.dumps(side, indent=1) + "\n")
    return rep


def main() -> None:
    from volunteers import counts

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", type=Path, nargs="?", default=DEFAULT_OUT)
    ap.add_argument("--only", default="", help="comma-separated singers' folders (default: everyone's takes that count)")
    ap.add_argument("--taps", type=int, default=128, help="the leak filter's length at 48 kHz (scaled to the take's rate)")
    ap.add_argument("--floor-db", type=float, default=-12.0, help="the gate's least gain")
    ap.add_argument("--gate-above", type=float, default=30.0, help="gate a take whose background is within this many dB of its singing")
    ap.add_argument("--full", action="store_true", help="also cancel full-guide takes (the band only re-renders as it was)")
    ap.add_argument("--no-residual", action="store_true", help="don't turn down what the filter left of the leak")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    out = args.out.resolve()
    for forbidden in (ROOT / "recordings", ROOT / "renders", ROOT / "web"):
        if out == forbidden or forbidden in out.parents:
            raise SystemExit(f"{out} is inside {forbidden}: give a scratch directory")
    only = {s for s in args.only.split(",") if s}
    shutil.rmtree(out / "takes", ignore_errors=True)  # a withdrawn take leaves nothing here
    todo = []
    for wav in sorted(K.RECORDINGS.glob("*/*.wav")):
        if wav.parent.name in K.NOT_SINGERS or (only and wav.parent.name not in only):
            continue
        if counts(K.load(wav)) is None:
            todo.append(str(wav))
    # render each guide once before the pool (they're shared)
    seen = set()
    for w in todo:
        t = K.load(Path(w))
        key = (t.guide, t.info.get("mix") or "melody")
        if key not in seen and (key[1] == "melody" or args.full):
            seen.add(key)
            guide_audio(t.song, t.guide, key[1], 48000, out / "guides")
    print(f"{len(todo)} takes; {len(seen)} guides rendered", flush=True)
    reports = []
    with ProcessPoolExecutor(args.jobs) as pool:
        for r in pool.map(clean_one, todo, [str(out)] * len(todo), [args.taps] * len(todo), [args.floor_db] * len(todo),
                          [args.gate_above] * len(todo), [args.full] * len(todo),
                          [not args.no_residual] * len(todo)):
            reports.append(r)
            lk = r.get("leak") or {}
            print(f"{r['take'][11:]}: background {r['before']['background_db']} -> {r['after_leak']['background_db']} -> "
                  f"{r['after']['background_db']} dB, gaps voiced {r['before']['voiced_in_gaps']} -> {r['after']['voiced_in_gaps']}; "
                  f"leak {lk.get('reduction_heldout_db', '-')} dB held out (prom {lk.get('prominence', '-')}, lag {lk.get('lag_ms', '-')} ms) "
                  f"{'' if lk.get('cancelled') else lk.get('why', '')}; {'+'.join(r['done']) or 'as it was'}", flush=True)
    (out / "report.json").write_text(json.dumps(reports, indent=1))
    print(f"-> {out / 'takes'} (report: {out / 'report.json'})")


if __name__ == "__main__":
    main()
