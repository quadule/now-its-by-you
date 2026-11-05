"""Cut a screen recording of a session down to a song's length, every action on the beat.

    uv run python tools/video/beatcut.py --video raw.webm --actions actions.json --audio song.flac \
        --out process.mp4 [--midi song.mid] [--bpm 124.8] [--fps 30] [--report cut.json]

Inputs: the raw footage, an action log (JSON: {"actions": [{t, kind, label, weight, hold, dur?}, ...]}, t in
seconds of the log's clock; tools/video/studio_session.mjs writes one) and the audio the video is set to. The
result is exactly as long as the audio, and its sound is the audio.

- **The beat grid.** From a MIDI file of the same music if given (its tempo map, time signature and section
  markers; its bar 1 placed against the audio by the onsets), else by beat-tracking the audio (librosa), bars
  of four, the downbeat phase taken where the low end hits hardest, sections every eight bars.
- **The log's clock against the footage.** A "sync" action marks a white flash drawn into the page; its first
  bright frame gives the offset (else the log's clock is taken as the footage's).
- **Placing actions.** Each action (weight >= 1) is an anchor: its moment (the click landing, the value
  changing) goes on a beat; weight 2 on a half bar, weight 3 on a bar line, or a section's first downbeat when
  one is near. The gaps between anchors follow the raw gaps, compressed to fit: at least `hold` beats after
  an action (and enough to show typing at no more than twice its speed), waits squeezed hardest. When even
  the least is too long, the lightest actions stop being anchors (they still play inside their neighbours).
- **Between two anchors** the footage plays at its own speed around each moment (a beat before it, the
  response after it), and the rest is held (a still) or run fast (up to 8x), or cut on a beat when it is
  longer still (a render's wait). Every cut and every speed change falls on a beat.

Writes the video (H.264, AAC), and a report: each anchor's beat time and the frame its moment lands on,
with the offsets from the beat.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


# ------------------------------------------------------------------------------------------ the beat grid
@dataclass
class Grid:
    beats: np.ndarray            # beat times in the audio, seconds
    downbeats: np.ndarray        # bar lines
    sections: list[tuple[float, str]] = field(default_factory=list)  # (time, name)


def read_midi(path: Path):
    """Tempo map, time signatures and markers of a standard MIDI file (format 0 or 1): the first track's meta events."""
    data = path.read_bytes()
    assert data[:4] == b"MThd"
    division = int.from_bytes(data[12:14], "big")
    pos, tempos, sigs, markers = 14, [], [], []
    while pos < len(data):
        kind, size = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], "big")
        body, pos = data[pos + 8:pos + 8 + size], pos + 8 + size
        if kind != b"MTrk":
            continue
        i, tick, status = 0, 0, 0
        while i < len(body):
            delta = 0
            while True:
                b = body[i]; i += 1
                delta = (delta << 7) | (b & 0x7F)
                if b < 0x80:
                    break
            tick += delta
            if body[i] & 0x80:
                status = body[i]; i += 1
            if status == 0xFF:
                typ = body[i]; i += 1
                n = 0
                while True:
                    b = body[i]; i += 1
                    n = (n << 7) | (b & 0x7F)
                    if b < 0x80:
                        break
                payload = body[i:i + n]; i += n
                if typ == 0x51:
                    tempos.append((tick, int.from_bytes(payload, "big")))
                elif typ == 0x58:
                    sigs.append((tick, payload[0], 2 ** payload[1]))
                elif typ == 0x06:
                    markers.append((tick, payload.decode("utf-8", "replace")))
            elif status in (0xF0, 0xF7):
                n = 0
                while True:
                    b = body[i]; i += 1
                    n = (n << 7) | (b & 0x7F)
                    if b < 0x80:
                        break
                i += n
            else:
                i += 1 if (status & 0xF0) in (0xC0, 0xD0) else 2
    return division, sorted(tempos) or [(0, 500000)], sorted(sigs) or [(0, 4, 4)], sorted(markers)


def midi_grid(path: Path, length: float) -> Grid:
    """The MIDI file's beats and bars in its own seconds (bar 1 at 0)."""
    division, tempos, sigs, markers = read_midi(path)

    def seconds(tick: int) -> float:
        t, last_tick, us = 0.0, 0, tempos[0][1] if tempos[0][0] == 0 else 500000
        for tt, u in tempos:
            if tt > tick:
                break
            t += (tt - last_tick) / division * us / 1e6
            last_tick, us = tt, u
        return t + (tick - last_tick) / division * us / 1e6

    beats, downs, tick, k = [], [], 0, 0
    while True:
        num, den = next(((n, d) for tt, n, d in reversed(sigs) if tt <= tick), (4, 4))
        step = division * 4 // den
        if den == 8 and num % 3 == 0:  # compound: the dotted quarter is the beat
            step *= 3
            per_bar = num // 3
        else:
            per_bar = num
        s = seconds(tick)
        if s > length + 30:
            break
        beats.append(s)
        if k % per_bar == 0:
            downs.append(s)
        tick += step
        k += 1
    sections = [(seconds(t), name) for t, name in markers]
    return Grid(np.array(beats), np.array(downs), sections)


def onset_env(audio: np.ndarray, sr: int):
    import librosa
    hop = 256
    env = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop)
    low = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=hop, fmax=200, n_mels=8)
    return env, low, hop


def place_grid(grid: Grid, env: np.ndarray, sr: int, hop: int, search=(-4.0, 4.0)) -> tuple[Grid, float]:
    """Shift a grid (in its own seconds) to where the audio's onsets agree with it best."""
    times = np.arange(len(env)) * hop / sr
    best, best_off = -1.0, 0.0
    for off in np.arange(search[0], search[1], 0.004):
        b = grid.beats + off
        b = b[(b >= 0) & (b < times[-1])]
        if len(b) < 8:
            continue
        score = float(np.interp(b, times, env).mean())
        if score > best:
            best, best_off = score, float(off)
    return Grid(grid.beats + best_off, grid.downbeats + best_off, [(t + best_off, n) for t, n in grid.sections]), best_off


def tracked_grid(audio: np.ndarray, sr: int, bpm: float | None) -> Grid:
    import librosa
    env, low, hop = onset_env(audio, sr)
    _, frames = librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop, start_bpm=bpm or 120.0, tightness=400)
    beats = librosa.frames_to_time(frames, sr=sr, hop_length=hop)
    lowv = np.interp(beats, np.arange(len(low)) * hop / sr, low)
    phase = int(np.argmax([lowv[p::4].mean() for p in range(4)]))
    downs = beats[phase::4]
    return Grid(beats, downs, [(float(t), f"bar {1 + 8 * k}") for k, t in enumerate(downs[::8])])


# --------------------------------------------------------------------------------------- the log vs the video
def probe_duration(path: Path) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def flash_time(video: Path, near: float, window: float = 6.0) -> float | None:
    """The flash: the first frame within `window` seconds of `near` that is white all over (mean luma over 248,
    little spread) after one that isn't, from a small decode. A rising edge, so neither a light page (the
    studio's paper is luma 237) nor the blank white of a page still loading is taken for it."""
    start = max(0.0, near - window / 2)
    cmd = [FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{window:.3f}", "-i", str(video),
           "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-fps_mode", "passthrough", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, 36 * 64)
    # timestamps: decode again with showinfo would be exact; frame index / fps is enough at the recorder's constant rate
    fps = video_fps(video)
    white = [bool(f.mean() > 248 and f.std() < 8) for f in frames.astype(np.float32)]
    for k in range(1, len(frames)):
        if white[k] and not white[k - 1]:
            return start + k / fps
    return None


def video_fps(video: Path) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True).stdout.strip()
    a, b = out.split("/")
    return float(a) / float(b)


# ------------------------------------------------------------------------------------------------ the plan
@dataclass
class Anchor:
    t: float           # in the footage
    kind: str
    label: str
    weight: int
    hold: float        # beats at least after it
    dur: float = 0.0   # an action that lasts (typing): its span in the footage
    o: float = 0.0     # where its moment lands in the output


RESPONSE = {"click": 0.9, "select": 1.2, "slider": 0.8, "drag": 1.3, "type": 0.0, "play": 0.6, "hear": 2.0,
            "record": 1.5, "saved": 2.0, "refused": 1.5, "download": 1.0}


def need(a: Anchor, beat: float, type_speed: float = 2.5) -> float:
    """The least output time after an anchor, in seconds: its hold (a light one half of it), and time to see it."""
    show = a.dur / type_speed if a.kind == "type" else RESPONSE.get(a.kind, 0.8)
    if a.weight <= 1 and a.kind != "type":
        return max(2 * beat, show)
    return max(a.hold * beat, show + beat, 2 * beat)


def snapper(grid: Grid, beat: float):
    """snap(t, weight, lo, hi): the grid point for a moment near t, at or after lo and at or before hi: any beat,
    a half bar (weight 2) or a bar line (weight 3), falling back to a finer grid when none is in reach."""
    idx = np.searchsorted(grid.beats, grid.downbeats)
    halves = np.unique(np.concatenate([grid.beats[np.clip(idx, 0, len(grid.beats) - 1)],
                                       grid.beats[np.clip(idx + 2, 0, len(grid.beats) - 1)]]))
    levels = {1: [grid.beats], 2: [halves, grid.beats], 3: [grid.downbeats, halves, grid.beats]}

    def snap(t: float, weight: int, lo: float, hi: float) -> float:
        for pts in levels[max(1, min(3, weight))]:
            c = pts[(pts >= lo - 1e-6) & (pts <= hi + 1e-6)]
            if len(c):
                return float(c[np.argmin(np.abs(c - t))])
        c = grid.beats[grid.beats >= lo - 1e-6]
        return float(c[0]) if len(c) else lo
    return snap


def plan(anchors: list[Anchor], grid: Grid, start: float, stop: float, first_fixed: bool = False) -> list[Anchor]:
    """Put each anchor's moment on a beat in [start, stop), in order, spaced like the footage, squeezed to fit.
    stop is where the next window's first moment lands (or the end); the last anchor keeps its least time before it.
    When even the least times don't fit, the lightest anchors stop being anchors (they still play inside)."""
    beat = float(np.median(np.diff(grid.beats)))
    snap = snapper(grid, beat)
    anchors = list(anchors)
    if not anchors:
        return []
    while len(anchors) > 1 and sum(need(a, beat) for a in anchors) > (stop - start):
        cands = range(1 if first_fixed else 0, len(anchors))
        gap_before = lambda i: anchors[i].t - anchors[i - 1].t if i else 1e9
        light = min(cands, key=lambda i: (anchors[i].weight + (1 if anchors[i].kind == "type" else 0), gap_before(i)))
        anchors.pop(light)
    n = len(anchors)
    raw_next = [anchors[i + 1].t - anchors[i].t for i in range(n - 1)] + [None]
    lows = [need(a, beat) for a in anchors]
    # a gap's wish: its raw length, pressed toward its least with a square root beyond it (waits count for little)
    wish = [lo + (math.sqrt(max(0.0, g - lo)) * 1.2 if g is not None else beat) for g, lo in zip(raw_next, lows)]
    room = stop - start
    if sum(wish) <= room:
        gaps = [w * room / sum(wish) for w in wish]
    else:
        spare = room - sum(lows)
        extra = sum(w - lo for w, lo in zip(wish, lows))
        gaps = [lo + spare * (w - lo) / max(1e-9, extra) for w, lo in zip(wish, lows)]
    ideal = start + np.concatenate([[0.0], np.cumsum(gaps)[:-1]])
    for i, a in enumerate(anchors):
        if i == 0 and first_fixed:
            a.o = start
            continue
        lo = start if i == 0 else anchors[i - 1].o + lows[i - 1]
        hi = stop - sum(lows[i:])  # the rest must still fit after it
        a.o = snap(float(ideal[i]), a.weight, lo, max(lo, hi))
    return anchors


# ------------------------------------------------------------------------------------------------ the cut
@dataclass
class Piece:
    src0: float
    src1: float
    out: float      # output length
    still: bool = False


def pieces_between(a: Anchor, b: Anchor, beat: float, ff_max: float = 8.0) -> list[Piece]:
    """The footage from a's moment to b's, fitted to the output time between them; changes of speed on beats."""
    raw, out = b.t - a.t, b.o - a.o
    if out <= 1e-6:
        return []
    pre = min(beat, out / 2, raw / 2)
    if a.kind == "type":
        post_raw = min(a.dur + 0.3, raw - pre)
    else:
        post_raw = min(RESPONSE.get(a.kind, 0.8), raw - pre)
    post_out = beat * math.ceil(post_raw / beat - 1e-6) if post_raw > 0 else 0.0
    if a.kind == "type":
        post_out = beat * math.ceil((post_raw / 2.0) / beat - 1e-6)
    post_out = min(post_out, out - pre)
    mid_raw, mid_out = raw - pre - post_raw, out - pre - post_out
    if mid_out < -1e-6 or post_out <= 0 or raw <= out:
        # simple: all of it at one speed if faster than real time, else real time and a still to fill
        if raw >= out:
            return [Piece(a.t, b.t, out)]
        return [Piece(a.t, a.t + raw - pre, raw - pre), Piece(a.t + raw - pre, a.t + raw - pre, out - raw, still=True),
                Piece(b.t - pre, b.t, pre)]
    ps = [Piece(a.t, a.t + post_raw, post_out)]
    m0, m1 = a.t + post_raw, b.t - pre
    if mid_out > 1e-6:
        if mid_raw <= mid_out:
            ps += [Piece(m0, m1, mid_raw), Piece(m1, m1, mid_out - mid_raw, still=True)] if mid_raw > 1e-3 else \
                  [Piece(m1, m1, mid_out, still=True)]
        elif mid_raw <= mid_out * ff_max:
            ps.append(Piece(m0, m1, mid_out))
        else:  # too long to run: half of it fast from the start, a cut on the beat, the rest fast up to the next
            h = beat * max(1, round(mid_out / 2 / beat))
            h = min(h, mid_out)
            ps.append(Piece(m0, m0 + h * ff_max, h))
            if mid_out - h > 1e-6:
                ps.append(Piece(m1 - (mid_out - h) * ff_max, m1, mid_out - h))
    ps.append(Piece(b.t - pre, b.t, pre))
    return [p for p in ps if p.out > 1e-4]


def render(pieces: list[Piece], video: Path, audio: Path, out: Path, length: float, fps: int, work: Path,
           size: tuple[int, int] | None, crf: int = 16) -> None:
    """Each piece as a short intermediate at the output's frame rate, then one concat with the audio."""
    files = []
    clock = 0.0
    for k, p in enumerate(pieces):
        # frame-exact lengths: the piece ends where the output clock's frame count says
        n0, n1 = round(clock * fps), round((clock + p.out) * fps)
        clock += p.out
        frames = n1 - n0
        if frames <= 0:
            continue
        f = work / f"p{k:04d}.mp4"
        scale = f",scale={size[0]}:{size[1]}:flags=lanczos" if size else ""
        base = max(0.0, p.src0 - 2.0)  # seek near, then trim exactly
        s0, s1 = p.src0 - base, p.src1 - base
        if p.still or p.src1 - p.src0 < 1e-3:
            vf = f"trim=start={s0:.4f}:duration=0.2,setpts=PTS-STARTPTS,fps={fps},tpad=stop_mode=clone:stop=-1{scale}"
        else:
            speed = (p.src1 - p.src0) / p.out
            vf = f"trim=start={s0:.4f}:end={s1:.4f},setpts=(PTS-STARTPTS)/{speed:.6f},fps={fps},tpad=stop_mode=clone:stop=-1{scale}"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-ss", f"{base:.3f}", "-i", str(video), "-vf", vf,
                        "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "4",
                        "-pix_fmt", "yuv420p", str(f)], check=True)
        files.append(f)
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
                    "-map", "0:v", "-map", "1:a", "-vf", f"trim=end_frame={int(length * fps)}",  # never past the audio
                    "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-tune", "stillimage", "-pix_fmt", "yuv420p",
                    "-r", str(fps), "-c:a", "aac", "-b:a", "256k",
                    "-t", f"{length:.6f}", "-movflags", "+faststart",
                    str(out)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--actions", type=Path, required=True)
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--midi", type=Path, help="a MIDI file of the same music: its tempo map, bars and sections")
    ap.add_argument("--midi-lead", type=float, help="where the MIDI file's bar 1 falls in the audio, in seconds "
                                                     "(negative before it; a Songbird stems README says it), instead of fitting it")
    ap.add_argument("--bpm", type=float, help="a tempo hint for beat tracking")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1920x1080", help="output size, WxH (default 1920x1080)")
    ap.add_argument("--crf", type=int, default=16, help="the H.264 quality of the result (lower is sharper; 16 keeps "
                                                        "small text crisp at 1080p; the pieces between are near lossless)")
    ap.add_argument("--from", dest="first", help="start at the first action whose label contains this")
    ap.add_argument("--to", dest="last", help="end at the first action (after --from) whose label contains this")
    ap.add_argument("--min-weight", type=int, default=1)
    ap.add_argument("--phases", help="phases to sections: 'open=Intro,tempo=Verse 1,...': the first action of each "
                                     "phase lands on that section's first downbeat (a name from the MIDI markers, "
                                     "or seconds; '+N' adds N beats)")
    ap.add_argument("--pin", action="append", default=[],
                    help="LABEL=SECTION[+N]: the first action whose label contains LABEL lands there (repeatable)")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--keep", action="store_true", help="keep the intermediate pieces")
    args = ap.parse_args()

    import soundfile as sf
    audio, sr = sf.read(str(args.audio), always_2d=True)
    mono = audio.mean(axis=1).astype(np.float32)
    length = len(mono) / sr
    env, low, hop = onset_env(mono, sr)
    if args.midi:
        mg = midi_grid(args.midi, length)
        fitted, fit = place_grid(mg, env, sr, hop)
        if args.midi_lead is not None:
            lead = args.midi_lead
            grid = Grid(mg.beats + lead, mg.downbeats + lead, [(t + lead, n) for t, n in mg.sections])
            source = f"MIDI tempo map, bar 1 at {lead:+.3f} s in the audio (given; the onsets say {fit:+.3f})"
        else:
            grid, lead = fitted, fit
            source = f"MIDI tempo map, bar 1 at {lead:+.3f} s in the audio (fitted to the onsets)"
    else:
        grid = tracked_grid(mono, sr, args.bpm)
        source = "beat tracking"
    keep = (grid.beats >= -1e-6) & (grid.beats <= length)
    grid = Grid(grid.beats[keep], grid.downbeats[(grid.downbeats >= -1e-6) & (grid.downbeats <= length)],
                [(t, n) for t, n in grid.sections if 0 <= t <= length])
    beat = float(np.median(np.diff(grid.beats)))

    log = json.loads(args.actions.read_text())["actions"]
    vlen = probe_duration(args.video)
    sync = next((a for a in log if a["kind"] == "sync"), None)
    offset = 0.0
    if sync:
        ft = flash_time(args.video, sync["t"])
        if ft is not None:
            offset = ft - sync["t"]
    acts = [a for a in log if a.get("weight", 1) >= args.min_weight and a["kind"] not in ("sync", "phase", "end")]
    if args.first:
        acts = acts[next(i for i, a in enumerate(acts) if args.first in a["label"]):]
    if args.last:
        acts = acts[:next(i for i, a in enumerate(acts) if args.last in a["label"]) + 1]
    anchors = [Anchor(a["t"] + offset, a["kind"], a["label"], int(a.get("weight", 1)), float(a.get("hold", 2)),
                      float(a.get("dur", 0.0))) for a in acts]
    phases = [a.get("phase", "") for a in acts]

    def where(spec: str) -> float:
        name, _, plus = spec.partition("+")
        name = name.strip()
        hit = next((t for t, n in grid.sections if n.strip().lower() == name.lower()), None)
        t = float(name) if hit is None else hit
        # a section's marker sits at its pickup's bar: its first downbeat at or after the marker
        d = grid.downbeats[grid.downbeats >= t - 1e-3]
        t = float(d[0]) if len(d) and hit is not None else t
        if plus:
            k = int(np.searchsorted(grid.beats, t - 1e-6)) + int(plus)
            t = float(grid.beats[min(k, len(grid.beats) - 1)])
        return t

    pins: dict[int, float] = {}
    for item in (args.phases.split(",") if args.phases else []):
        ph, _, spec = item.partition("=")
        i = next((i for i, p in enumerate(phases) if p == ph.strip()), None)
        if i is not None:
            pins[i] = where(spec)
    for item in args.pin:
        lab, _, spec = item.rpartition("=")
        i = next((i for i, a in enumerate(anchors) if lab in a.label), None)
        if i is not None:
            pins[i] = where(spec)
    # the first beat after a short opening, and a bar's tail after the last
    start = float(grid.downbeats[1]) if len(grid.downbeats) > 1 else beat * 4
    end = length - 4 * beat
    pins.setdefault(0, start)
    order = sorted(pins)
    assert all(pins[a] < pins[b] for a, b in zip(order, order[1:])), f"pins out of order: {[(anchors[i].label, pins[i]) for i in order]}"
    placed: list[Anchor] = []
    for k, i in enumerate(order):
        j = order[k + 1] if k + 1 < len(order) else len(anchors)
        stop = pins[order[k + 1]] if k + 1 < len(order) else end
        placed += plan(anchors[i:j], grid, pins[i], stop, first_fixed=True)
    anchors = placed
    # the opening: the footage leading up to the first anchor, at its own speed where it can
    after_sync = (sync["t"] + offset + 0.5) if sync else 0.0  # never the flash itself
    head = Anchor(max(after_sync, anchors[0].t - anchors[0].o), "open", "open", 0, 0)
    head.o = 0.0
    tail = Anchor(min(vlen - 0.05, anchors[-1].t + (length - anchors[-1].o)), "end", "end", 0, 0)
    tail.o = length
    seq = [head] + anchors + [tail]
    pieces: list[Piece] = []
    for a, b in zip(seq, seq[1:]):
        pieces += pieces_between(a, b, beat)

    w, h = (int(x) for x in args.size.lower().split("x"))
    work = Path(tempfile.mkdtemp(prefix="beatcut-"))
    try:
        wav = work / "audio.wav"  # decoded once: a file that carries more than audio (a packet) muxes cleanly
        sf.write(str(wav), audio, sr, subtype="PCM_24")
        render(pieces, args.video, wav, args.out, length, args.fps, work, (w, h), args.crf)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)

    # where each moment landed: the output frame nearest its time, against the nearest beat
    rows, offs = [], []
    for a in anchors:
        frame_t = round(a.o * args.fps) / args.fps
        nearest = float(grid.beats[np.argmin(np.abs(grid.beats - frame_t))])
        off = frame_t - nearest
        offs.append(abs(off))
        on_bar = bool(np.min(np.abs(grid.downbeats - a.o)) < 1e-3)
        rows.append({"label": a.label, "kind": a.kind, "weight": a.weight, "raw": round(a.t, 3), "out": round(a.o, 3),
                     "frame": round(frame_t * args.fps), "off_beat_ms": round(off * 1000, 1), "on_bar": on_bar})
    bitrate = 8 * args.out.stat().st_size / probe_duration(args.out) / 1e6
    report = {"audio": str(args.audio), "length": length, "grid": source, "beat": beat, "log_offset": offset,
              "mbps": round(bitrate, 2), "on_bar": sum(r["on_bar"] for r in rows),
              "anchors": len(anchors), "actions_in_log": len(acts), "mean_off_ms": round(1000 * float(np.mean(offs)), 2),
              "max_off_ms": round(1000 * float(np.max(offs)), 2), "video_duration": probe_duration(args.out),
              "sections": grid.sections, "placed": rows}
    if args.report:
        args.report.write_text(json.dumps(report, indent=1))
    print(f"{args.out}: {report['video_duration']:.3f} s for {length:.3f} s of audio; {len(anchors)} of {len(acts)} "
          f"actions on the beat ({source}); moments off the beat by {report['mean_off_ms']} ms on average, "
          f"{report['max_off_ms']} ms at most (the frame grid); {report['on_bar']} on a bar line; {bitrate:.1f} Mb/s")


if __name__ == "__main__":
    main()
