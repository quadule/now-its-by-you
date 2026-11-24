"""The whole learned throat as one picture, every weight a pixel, lit by what each adds while it sings.

    uv run python tools/promo/singer_picture.py CAPTURE.pkl OUT.mp4 [--from S --to S] [--audio FLAC]

CAPTURE.pkl is one call kept by tools/promo/capture.py. A pixel's colour is its weight times the value it is
multiplied by at that moment (red adds, indigo takes away); at rest the picture shows the weights' sizes alone.
--audio plays that file's same seconds in place of the captured dry voice."""
import argparse
import pickle
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from songbird.synth import throat

W, H, FPS = 1080, 1350, 30
PAPER, INK = np.array([244, 236, 220.0]), np.array([43, 35, 29.0])
RED, INDIGO = np.array([163, 54, 31.0]), np.array([43, 68, 116.0])
DIM = (143, 125, 102)
SERIF = "/usr/share/fonts/TTF/Georgia.TTF"
BLOCK_W, BLOCK_H, GAP = 332, 320, 12
GRID_X, GRID_Y = (W - 3 * BLOCK_W - 2 * GAP) // 2, 190
INTRO, OUTRO = 1.6, 1.2


def layout(w: dict) -> dict[str, tuple[int, int]]:
    """Where each array's top left pixel goes. Nine slots, three by three: the way in and the way out, then
    the eight blocks in order. A block: its timbre weights down the left, then four squares (the frames before,
    now and after, and the mix), its two biases down the right."""
    at = {}
    x0, y0 = GRID_X, GRID_Y
    at["inp.weight"], at["inp.bias"] = (x0, y0), (x0 + 92, y0)
    at["phone.weight"], at["role.weight"], at["singer.weight"] = (x0 + 104, y0), (x0 + 130, y0), (x0 + 144, y0)
    at["out.weight"], at["out.bias"] = (x0 + 171, y0 + 160), (x0 + 331, y0 + 160)
    for i in range(8):
        slot = i + 1
        bx, by = GRID_X + (slot % 3) * (BLOCK_W + GAP), GRID_Y + (slot // 3) * (BLOCK_H + GAP)
        at[f"films.{i}.weight"], at[f"films.{i}.bias"] = (bx, by), (bx + 8, by)
        at[f"convs.{i}.weight"] = (bx + 11, by)  # drawn as three squares by draw()
        at[f"mixes.{i}.weight"] = (bx + 171, by + 160)
        at[f"convs.{i}.bias"], at[f"mixes.{i}.bias"] = (bx + 331, by), (bx + 331, by + 160)
    return at


def tiles(name: str, a: np.ndarray, at: tuple[int, int]):
    """(x, y, 2-D piece) for an array: a bias is a column, a conv's three taps are three squares."""
    x, y = at
    if a.ndim == 1:
        yield x, y, a[:, None]
    elif name.startswith("convs."):
        yield x, y, a[:, :160]
        yield x + 160, y, a[:, 160:320]
        yield x, y + 160, a[:, 320:]
    else:
        yield x, y, a


def forward(model, t: dict, cont: np.ndarray, singer: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """throat._predict_raw, keeping what every weight array is multiplied by at each frame."""
    w, seen = model.w, {}
    phones = np.stack([t["prev2"], t["prev"], t["phone"], t["next"], t["next2"]], axis=-1).astype(int)
    seen["phones"], seen["role"] = phones, t["role"].astype(int)
    first = np.concatenate([w["phone.weight"][phones].reshape(len(cont), -1), w["role.weight"][seen["role"]], cont], axis=1)
    seen["inp"] = first
    x = first @ w["inp.weight"].T + w["inp.bias"]
    for i, d in enumerate(model.config["dilations"]):
        gamma, beta = np.split(singer[None] @ w[f"films.{i}.weight"].T + w[f"films.{i}.bias"], 2, axis=1)
        stacked = np.zeros((len(x), 480))
        stacked[:, 160:320] = x
        stacked[d:, :160] = x[: len(x) - d]
        stacked[: len(x) - d, 320:] = x[d:]
        seen[f"convs.{i}"] = stacked
        h = throat._gelu((stacked @ w[f"convs.{i}.weight"].T + w[f"convs.{i}.bias"]) * (1.0 + gamma) + beta)
        seen[f"mixes.{i}"] = h
        x = x + h @ w[f"mixes.{i}.weight"].T + w[f"mixes.{i}.bias"]
    seen["out"] = x
    return x @ w["out.weight"].T + w["out.bias"], seen


def words(notes: list[dict]) -> list[dict]:
    """The notes' syllables joined into words, each with when it starts and ends and whether it ends a line."""
    out, i = [], 0
    while i < len(notes):
        group = notes[i: i + max(1, int(notes[i].get("word_len") or 1))]
        text = "".join(n["syllable"].replace("*", "") for n in group)
        out.append({"text": text, "t0": group[0]["start"], "t1": group[-1]["start"] + group[-1]["dur"],
                    "line_end": group[-1]["line_end"]})
        i += len(group)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("out")
    ap.add_argument("--from", dest="t0", type=float, default=30.4)
    ap.add_argument("--to", dest="t1", type=float, default=40.9)
    ap.add_argument("--audio")
    ap.add_argument("--dark", action="store_true", help="the site's stage colours in place of its paper")
    a = ap.parse_args()
    with open(a.capture, "rb") as f:
        cap = pickle.load(f)
    global PAPER, INK, RED, INDIGO, DIM
    if a.dark:
        PAPER, INK = np.array([27, 22, 17.0]), np.array([239, 230, 218.0])
        RED, INDIGO, DIM = np.array([242, 178, 92.0]), np.array([120, 160, 230.0]), (154, 141, 127)
    model = throat.load()
    w = model.w

    # the network over the window, with room either side for its context
    f0, f1 = int(a.t0 / throat.FRAME), int(a.t1 / throat.FRAME)
    lo, hi = max(0, f0 - 400), min(len(cap["lf0"]), f1 + 400)
    cont = throat.continuous(cap["t"], cap["lf0"])
    t = {k: v[lo:hi] for k, v in cap["t"].items()}
    y, seen = forward(model, t, cont[lo:hi], cap["singer"])
    assert np.allclose(y, throat._predict_raw(model, t, cont[lo:hi].copy(), cap["singer"])), "not the throat's own sums"

    at = layout(w)
    total = sum(v.size for v in w.values())
    assert set(at) == set(w) and total == model.config["params"]
    frames = int(round((a.t1 - a.t0) * FPS))
    step = 1.0 / FPS / throat.FRAME  # model frames in a video frame

    def inputs(key: str, k: int) -> np.ndarray:
        i0 = int(round(f0 - lo + k * step))
        return seen[key][i0: int(round(f0 - lo + (k + 1) * step))].mean(axis=0)

    def adding(k: int) -> dict[str, np.ndarray]:
        """Each weight times what it is multiplied by, over video frame k."""
        out = {"inp.weight": w["inp.weight"] * inputs("inp", k), "out.weight": w["out.weight"] * inputs("out", k)}
        for i in range(8):
            out[f"convs.{i}.weight"] = w[f"convs.{i}.weight"] * inputs(f"convs.{i}", k)
            out[f"mixes.{i}.weight"] = w[f"mixes.{i}.weight"] * inputs(f"mixes.{i}", k)
            out[f"films.{i}.weight"] = w[f"films.{i}.weight"] * cap["singer"]
        i0, i1 = int(round(f0 - lo + k * step)), int(round(f0 - lo + (k + 1) * step))
        phone = np.bincount(seen["phones"][i0:i1].ravel(), minlength=len(w["phone.weight"])) / (5.0 * (i1 - i0))
        role = np.bincount(seen["role"][i0:i1], minlength=len(w["role.weight"])) / float(i1 - i0)
        out["phone.weight"], out["role.weight"] = w["phone.weight"] * phone[:, None] * 3, w["role.weight"] * role[:, None]
        for name, v in w.items():
            if v.ndim == 1:
                out[name] = v
        out["singer.weight"] = np.zeros_like(w["singer.weight"])
        return out

    # one scale per array, from a sample of frames, so a quiet layer shows as much as a loud one
    sample = [adding(k) for k in range(0, frames, 6)]
    scale = {n: max(np.percentile(np.abs(np.stack([s[n] for s in sample])), 99.5), 1e-9) for n in at}
    size = {n: np.percentile(np.abs(v), 99.5) for n, v in w.items()}

    base = np.tile(PAPER, (H, W, 1))
    rest = np.zeros((H, W))  # how inked each pixel is at rest
    drawn = 0
    for n, v in w.items():
        for x, yy, piece in tiles(n, v, at[n]):
            rest[yy: yy + piece.shape[0], x: x + piece.shape[1]] = 0.06 + 0.22 * np.clip(np.abs(piece) / size[n], 0, 1)
            drawn += piece.size
    assert drawn == total == 886372, drawn
    still = base + (INK - base) * rest[..., None]

    big, mid, small = (ImageFont.truetype(SERIF, s) for s in (46, 30, 22))
    sung = [x for x in words(cap["notes"]) if a.t0 - 0.2 <= x["t0"] < a.t1]
    lines, line = [], []
    for x in sung:
        line.append(x)
        if x["line_end"]:
            lines.append(line)
            line = []
    if line:
        lines.append(line)

    LIT = (224, 102, 77) if a.dark else tuple(RED.astype(int))

    def text(img: np.ndarray, now: float | None, lit: float) -> np.ndarray:
        im = Image.fromarray(img)
        d = ImageDraw.Draw(im)
        d.text((W // 2, 78), "This picture is the entire singer.", font=big, fill=tuple(INK.astype(int)), anchor="mm")
        d.text((W // 2, 136), "886,372 numbers, one pixel each", font=mid, fill=DIM, anchor="mm")
        if now is not None:
            for ln in lines:
                if ln[0]["t0"] - 0.6 <= now < ln[-1]["t1"] + 0.5:
                    widths = [d.textlength(x["text"] + " ", font=big) for x in ln]
                    x = (W - sum(widths)) / 2
                    for word, width in zip(ln, widths):
                        fill = tuple(RED.astype(int)) if word["t0"] <= now < word["t1"] else (
                            tuple(INK.astype(int)) if now >= word["t1"] else DIM)
                        d.text((x, 1238), word["text"], font=big, fill=fill, anchor="ls")
                        x += width
        d.text((W // 2, 1310), "Now It's by You  ·  now.itsby.you", font=small, fill=DIM, anchor="mm")
        return np.asarray(im)

    def frame(k: int | None, lit: float = 1.0) -> bytes:
        img = still.copy()
        if k is not None and lit > 0:
            c = adding(k)
            for n in at:
                for x, yy, piece in tiles(n, c[n], at[n]):
                    amount = (np.clip(np.abs(piece) / scale[n], 0, 1) ** 0.8 * lit)[..., None]
                    colour = np.where(piece[..., None] > 0, RED, INDIGO)
                    region = img[yy: yy + piece.shape[0], x: x + piece.shape[1]]
                    region += (colour - region) * amount
        now = None if k is None else a.t0 + (k + 0.5) / FPS
        return text(np.clip(img, 0, 255).astype(np.uint8), now, lit).tobytes()

    sr = cap["sr"]
    with tempfile.TemporaryDirectory(dir=Path(a.out).parent) as tmp:
        wav = Path(tmp) / "voice.wav"
        if a.audio:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(a.t0), "-t", str(a.t1 - a.t0), "-i", a.audio, str(wav)],
                           check=True)
        else:
            import soundfile as sf
            v = cap["y"][int(a.t0 * sr): int(a.t1 * sr)].copy()
            v *= 0.5 / np.abs(v).max()
            sf.write(wav, v, sr)
        fade = f"afade=t=in:d=0.15,afade=t=out:st={a.t1 - a.t0 - 0.4}:d=0.4,adelay={int(INTRO * 1000)}:all=1,apad=pad_dur={OUTRO}"
        ff = subprocess.Popen(
            ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-i", str(wav), "-af", fade, "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
        for _ in range(int(INTRO * FPS)):
            ff.stdin.write(frame(None))
        ramp = int(0.3 * FPS)
        for k in range(frames):
            ff.stdin.write(frame(k, min(1.0, (k + 1) / ramp, (frames - k) / ramp)))
        for _ in range(int(OUTRO * FPS)):
            ff.stdin.write(frame(None))
        ff.stdin.close()
        ff.wait()
    print(a.out, f"{INTRO + (a.t1 - a.t0) + OUTRO:.1f} s, {drawn:,} weights drawn")


if __name__ == "__main__":
    main()
