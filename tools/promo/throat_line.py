"""The line the learned throat draws 200 times a second, and the lines before it receding behind.

    uv run python tools/promo/throat_line.py CAPTURE.pkl OUT.mp4 [--from S --to S] [--audio FLAC] [--dark]

CAPTURE.pkl is one call kept by tools/promo/capture.py. Each line is one 5 ms frame of the network's spectral
envelope (how loud the voice is from low to high, 128 points to 11.8 kHz), as sing() shapes it before the
vocoder. Under the newest line: the note's harmonics where the voice is pitched (red), and dots where it is
breath (indigo, by the network's aperiodicity)."""
import argparse
import pickle
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from songbird.synth import throat

W, H, FPS, SS = 1080, 1350, 30, 2
SERIF = "/usr/share/fonts/TTF/Georgia.TTF"
INTRO, OUTRO = 1.2, 1.2
BACK = 1.8  # seconds of earlier lines shown
EVERY = 4  # model frames between the lines kept behind
FRONT_Y, FAR_Y, HEIGHT, FRONT_W = 1090, 330, 330, 940
RANGE = 62.0  # dB from the loudest point shown to the line's foot


def words(notes):
    out, i = [], 0
    while i < len(notes):
        group = notes[i: i + max(1, int(notes[i].get("word_len") or 1))]
        out.append({"text": "".join(n["syllable"].replace("*", "") for n in group), "t0": group[0]["start"],
                    "t1": group[-1]["start"] + group[-1]["dur"], "line_end": group[-1]["line_end"]})
        i += len(group)
    return out


def main() -> None:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("capture")
    ap_.add_argument("out")
    ap_.add_argument("--from", dest="t0", type=float, default=30.4)
    ap_.add_argument("--to", dest="t1", type=float, default=40.9)
    ap_.add_argument("--audio")
    ap_.add_argument("--dark", action="store_true")
    a = ap_.parse_args()
    paper, ink, red, indigo, dim = (244, 236, 220), (43, 35, 29), (163, 54, 31), (43, 68, 116), (143, 125, 102)
    if a.dark:
        paper, ink, red, indigo, dim = (27, 22, 17), (239, 230, 218), (224, 102, 77), (140, 175, 235), (154, 141, 127)
    with open(a.capture, "rb") as f:
        cap = pickle.load(f)
    model = throat.load()

    # the envelope as sing() hands it to the vocoder (before the vibrato's sway in loudness)
    sp, ap = throat.predict(model, cap["t"], cap["lf0"], cap["singer"], gv=1.0, last=cap["last"])
    sp = throat.sharpen(sp, throat.SHARPEN) * (10.0 / np.log(10.0))  # dB
    f0 = np.exp(cap["lf0"])
    voiced = np.array([throat.PHONES[int(p)] not in throat.UNVOICED for p in cap["t"]["phone"]])
    silent = np.array([throat.PHONES[int(p)] in ("sil", "breath") for p in cap["t"]["phone"]])
    lo, hi = int(a.t0 / throat.FRAME), int(a.t1 / throat.FRAME)
    top = np.percentile(sp[lo:hi].max(axis=1), 99)
    level = np.clip((sp - (top - RANGE)) / RANGE, 0.0, 1.15)
    # the network's envelope for a silence is not sung (the vocoder is hushed there): the line settles over 40 ms
    level *= (1.0 - np.convolve(silent.astype(float), np.hanning(17) / np.hanning(17).sum(), mode="same"))[:, None]
    points = level.shape[1]
    fine = np.linspace(0, points - 1, 420)
    freqs, ap_at = throat.grid(points), np.linspace(0, points - 1, ap.shape[1])

    def curve(i: float) -> np.ndarray:
        i0 = int(np.clip(np.floor(i), 0, len(level) - 2))
        row = level[i0] + (level[i0 + 1] - level[i0]) * (i - i0)
        return np.interp(fine, np.arange(points), row)

    big, mid, small = (ImageFont.truetype(SERIF, s * SS) for s in (46, 30, 22))
    lines, line = [], []
    for x in words(cap["notes"]):
        if a.t0 - 0.2 <= x["t0"] < a.t1:
            line.append(x)
            if x["line_end"]:
                lines.append(line)
                line = []
    if line:
        lines.append(line)
    blend = lambda c, k: tuple(int(p + (q - p) * k) for p, q in zip(paper, c))
    rng = np.random.default_rng(1)

    def frame(now: float, singing: bool) -> bytes:
        im = Image.new("RGB", (W * SS, H * SS), paper)
        d = ImageDraw.Draw(im)
        i_now = now / throat.FRAME
        first = int(np.ceil((now - BACK) / throat.FRAME / EVERY)) * EVERY
        for i in list(range(first, int(i_now), EVERY)) + [i_now]:  # far to near
            u = float(np.clip((i_now - i) * throat.FRAME / BACK, 0, 1))
            newest = i == i_now
            scale = 1.0 - 0.45 * u ** 0.9
            base = FRONT_Y - (FRONT_Y - FAR_Y) * u ** 0.75
            xs = (W / 2 + (fine / (points - 1) - 0.5) * FRONT_W * scale) * SS
            c = curve(i)
            ys = (base - c * HEIGHT * scale) * SS
            poly = [(xs[0], base * SS), *zip(xs, ys), (xs[-1], base * SS)]
            d.polygon(poly, fill=paper)
            if newest:
                j = int(np.clip(round(i_now), 0, len(f0) - 1))
                if voiced[j] and not silent[j]:
                    k = np.arange(1, int(freqs[-1] / f0[j]) + 1) * f0[j]
                    at = np.interp(k, freqs, np.arange(points))
                    clear = 1.0 - np.interp(at, ap_at, ap[j])
                    for p, cl in zip(at, clear):
                        x = (W / 2 + (p / (points - 1) - 0.5) * FRONT_W) * SS
                        y = (base - np.interp(p, fine, c) * HEIGHT) * SS
                        d.line([(x, base * SS), (x, y)], fill=blend(red, 0.25 + 0.75 * cl), width=2 * SS)
                if not silent[j]:
                    n = 2600
                    px = rng.uniform(0, points - 1, n)
                    keep = rng.uniform(0, 1, n) < np.interp(px, ap_at, ap[j]) ** 1.5
                    py = rng.uniform(0, 1, n) * np.interp(px, fine, c)
                    for p, q in zip(px[keep], py[keep]):
                        x = (W / 2 + (p / (points - 1) - 0.5) * FRONT_W) * SS
                        y = (base - q * HEIGHT) * SS
                        d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=indigo)
            d.line(list(zip(xs, ys)), fill=blend(ink, (1 - u) ** 1.6 * 0.85 + 0.04) if not newest else ink,
                   width=6 if newest else 2, joint="curve")
        m = W * SS // 2
        d.text((m, 84 * SS), "The singer draws this line", font=big, fill=ink, anchor="mm")
        d.text((m, 140 * SS), "200 times a second.", font=big, fill=ink, anchor="mm")
        d.text((m, 196 * SS), "A 3 MB model, 886,372 numbers", font=mid, fill=dim, anchor="mm")
        left, right = (W - FRONT_W) / 2 * SS, (W + FRONT_W) / 2 * SS
        d.text((left, (FRONT_Y + 26) * SS), "low", font=small, fill=dim, anchor="lm")
        d.text((right, (FRONT_Y + 26) * SS), "high", font=small, fill=dim, anchor="rm")
        if singing:
            for ln in [x for x in lines if x[0]["t0"] - 0.5 <= now][-1:]:  # one line at a time: the latest begun
                if True:
                    widths = [d.textlength(x["text"] + " ", font=big) for x in ln]
                    x = (W * SS - sum(widths)) / 2
                    for word, width in zip(ln, widths):
                        fill = red if word["t0"] <= now < word["t1"] else (ink if now >= word["t1"] else dim)
                        d.text((x, 1238 * SS), word["text"], font=big, fill=fill, anchor="ls")
                        x += width
        d.text((m, 1310 * SS), "Now It's by You  ·  now.itsby.you", font=small, fill=dim, anchor="mm")
        return im.resize((W, H), Image.LANCZOS).tobytes()

    sr = cap["sr"]
    with tempfile.TemporaryDirectory(dir=Path(a.out).parent) as tmp:
        wav = Path(tmp) / "voice.wav"
        start, length = a.t0 - INTRO, a.t1 - a.t0 + INTRO + OUTRO
        if a.audio:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-t", str(length), "-i", a.audio, str(wav)],
                           check=True)
        else:
            import soundfile as sf
            v = cap["y"][int(start * sr): int((start + length) * sr)].copy()
            v *= 0.5 / np.abs(v).max()
            sf.write(wav, v, sr)
        fade = f"afade=t=in:d=0.3,afade=t=out:st={length - 0.5}:d=0.5"
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-i", str(wav), "-af", fade, "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
        for k in range(int(length * FPS)):
            now = start + (k + 0.5) / FPS
            ff.stdin.write(frame(now, a.t0 - 0.3 <= now))
        ff.stdin.close()
        ff.wait()
    print(a.out, f"{length:.1f} s")


if __name__ == "__main__":
    main()
