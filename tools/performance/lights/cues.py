"""The lanterns' part in the show: three lanterns, left, center and right, cued 60 times a second to the music video.

    python3 tools/performance/lights/cues.py          writes renders/performance/lights/cues.npz, .bin and .json

Reads the film's data (renders/promo/video/data): timeline.json (sections, sung lines, the players' entries, the
record's human amount), score.json (every part's notes), stems/*.env (every part's loudness at the film's 60 frames
a second) and throat/*.env (the singers' spectral envelopes at 200 a second). A cue at frame i is for frame i.

The lanterns go from copies to people, as the song does.

Copies. Until the players come in, the three are one machine three times: a dot ticking round each screen on the
beat, and one hard light stepping along each arch to the machine's notes, the same on all three.

Players. Each wakes when its player enters (the harp on the left, the lute on the right, the bass in the center),
takes its own color, and from then on moves its own way. On the arches pitch is height: low notes near the feet,
high ones at the top, so a tune is seen to climb and fall.
  left, the harp     each pluck lands at its height and spreads like a ripple; rings open on the screen
  center, the beat   the bass rises from the feet like a tide; each drum hit runs down from the top
  right, the tune    the melody's notes stay lit a moment where they landed, so the line of the tune is seen;
                     a dot on the screen sings at the note's height
"a million bright faces all lit the same way" turns them back into copies for a line; on "but nobody sang it, so
then it was gone" they go out one by one. In refrain 2 a spark runs from lantern to lantern at each line's end;
in turn 2 each whistle note runs along all three.

People. In the bridge each screen opens its eyes: a face, singing one of the three choir voices with a mouth
shaped by its vowels (the first formant opens it, the second widens it). They look at each other; on "hand it
along like a coal from the fire" a coal passes along the arches and their eyes follow it; the four notes of the
daisy tune fall one per lantern; on "it dies in the dark if you leave it alone" they close their eyes and dim. In
the last refrain all three sing the lead, each its own face, warming to one color; in the tag they turn to the
singer; at the end they shut their eyes one at a time.

cues.npz: "scenes" uint8 [frames, 3, RECORD] (a screen record without its id: firmware/src/scenes.h), "leds"
uint8 [frames, 3, LEDS, 3]. cues.bin is the same per frame and lantern (the record, then the LEDs) for show.html.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "renders/promo/video/data"
OUT = ROOT / "renders/performance/lights/cues.npz"

FPS = 60
LEDS = 20                 # along the arch, from the left foot over the top to the right foot
ROLES = ("left", "center", "right")
SCENES = ("dark", "glow", "ring", "ripples", "rays", "rise", "arch", "bands", "mouth", "face", "dot")
RECORD = 19               # [scene][r g b][r2 g2 b2][a][b][c][d][e][f][g][h][i][j][k][backlight]
GROUND = 0.05             # how much of its color a screen's background keeps
GAMMA = 2.0               # LEDs: brightness as seen to PWM
MACHINE = (0.6, 0.18)     # the copies' color: hue, saturation
OWN = {"left": 0.93, "center": 0.11, "right": 0.47}  # each player's own hue: rose, amber, teal
PEOPLE_HUE = 0.07         # warm, where the colors end
WAKE_TIME = 1.5           # s for a copy to become a player
# each face's own eyes: size and how far apart (scenes.h j, k)
EYES = {"left": (165, 95), "center": (115, 70), "right": (135, 150)}
SEAT = {"left": -1.0, "center": 0.0, "right": 1.0}  # where each stands, for where the others look


def load():
    timeline = json.loads((DATA / "timeline.json").read_text())
    parts = json.loads((DATA / "score.json").read_text())["parts"]
    return timeline, parts


def followed(x: np.ndarray, attack: float, release: float) -> np.ndarray:
    up, down = np.exp(-1 / (attack * FPS)), np.exp(-1 / (release * FPS))
    y = np.empty_like(x)
    v = 0.0
    for i, t in enumerate(x):
        c = up if t > v else down
        v = c * v + (1 - c) * t
        y[i] = v
    return y


def loudness(stem: str, frames: int) -> np.ndarray:
    """A stem's loudness at each frame, 0-1: its RMS against its own loud playing, rising fast and falling slower."""
    meta = json.loads((DATA / f"stems/{stem}.env.json").read_text())
    raw = np.fromfile(DATA / f"stems/{stem}.env.bin", dtype=np.uint8).reshape(meta["shape"])
    db = raw[:, 0].astype(float) * meta["scale"] + meta["offset"]
    playing = db[db > -60]
    loud = np.percentile(playing, 95) if len(playing) else 0
    x = np.clip((db - (loud - 36)) / 36, 0, 1) ** 1.5
    x = np.pad(x, (0, max(0, frames - len(x))))[:frames]
    return followed(x, 0.02, 0.2)


def number(x):
    return json.loads(x) if isinstance(x, str) else x


def vowels(name: str, frames: int):
    """A singer's mouth at each frame from its envelope: how loud (0-1), how open (0-1), how wide (0-1)."""
    meta = json.loads((DATA / f"throat/{name}.env.json").read_text())
    freqs = np.array(json.loads((DATA / "throat/choir1.env.json").read_text())["freqs"])
    raw = np.fromfile(DATA / f"throat/{name}.env.bin", np.uint8)
    env = raw.reshape(number(meta["shape"])).astype(float) * number(meta["scale"]) + number(meta["offset"])
    rate = number(meta["rate"])
    at = np.minimum((np.arange(frames) / FPS * rate).astype(int), len(env) - 1)
    env = env[at]
    b1, b2 = (freqs >= 250) & (freqs <= 1000), (freqs >= 900) & (freqs <= 2800)
    f1 = freqs[b1][np.argmax(env[:, b1], axis=1)]
    f2 = freqs[b2][np.argmax(env[:, b2], axis=1)]
    loud = np.clip((env.max(axis=1) + 40) / 34, 0, 1)
    loud[np.arange(frames) / FPS * rate >= len(raw) / 128] = 0
    opening = np.clip((f1 - 250) / 650, 0, 1)
    width = np.clip((f2 - 900) / 1400, 0, 1)
    return followed(loud, 0.015, 0.08), followed(opening, 0.03, 0.06), followed(width, 0.03, 0.08)


def human_at(timeline, frames: int) -> np.ndarray:
    """The record's human amount at each frame (it steps; here it glides over 2 s)."""
    x = np.zeros(frames)
    for t, h in timeline["human"]:
        x[int(t * FPS):] = h
    return followed(x, 2, 2)


class Notes:
    """A part's notes as arrays, sorted by start, with its pitch range for heights on the arch."""

    def __init__(self, notes: list, low: float | None = None, high: float | None = None):
        notes = sorted(notes, key=lambda n: n["t"])
        self.t = np.array([n["t"] for n in notes])
        self.d = np.array([n["d"] for n in notes])
        self.p = np.array([n["p"] for n in notes])
        self.v = np.array([n["v"] for n in notes])
        self.low = self.p.min() if low is None else low
        self.high = self.p.max() if high is None else high

    def recent(self, t: float, back: float) -> np.ndarray:
        """Indices of the notes that started in the last `back` s."""
        return np.arange(np.searchsorted(self.t, t - back), np.searchsorted(self.t, t, side="right"))

    def last(self, t: float) -> int:
        """The latest note started by t, or -1."""
        return int(np.searchsorted(self.t, t, side="right")) - 1

    def since(self, t: float) -> float:
        k = self.last(t)
        return t - self.t[k] if k >= 0 else 99.0

    def height(self, p: float) -> float:
        return float(np.clip((p - self.low) / max(1, self.high - self.low), 0, 1))


# ---- colors ----

def rgb(hue: float, sat: float = 0.7, v: float = 1.0) -> np.ndarray:
    return np.array(colorsys.hsv_to_rgb(hue % 1, sat, 1)) * 255 * v


def toward(hue: float, target: float, k: float) -> float:
    return hue + ((target - hue + 0.5) % 1 - 0.5) * k


def own(role: str, human: float, warm: float = 0.0, p_height: float = 0.5) -> np.ndarray:
    """A player's color: its own hue, drawn a little warmer by the human amount, fully by `warm`, a touch higher
    with its note."""
    hue = toward(OWN[role], PEOPLE_HUE, 0.25 * human / 0.75 + 0.75 * warm) + (p_height - 0.5) * 0.06
    return rgb(hue, 0.72 - 0.2 * warm)


def machine() -> np.ndarray:
    return rgb(*MACHINE)


def blend(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    return a + (b - a) * k


# ---- screens ----

def record(kind: str, color, v: float, a=0.0, b=0.0, c=0.0, d=128.0, e=128.0, f=0.0, g=0.0,
           h=0.0, i=128.0, j=0.0, k=0.0) -> np.ndarray:
    """A screen record (no id): the shape in `color` at brightness v over a dark ground of the same color."""
    if v < 0.02:
        return np.zeros(RECORD, np.uint8)
    color = np.asarray(color, float)
    shape, ground = color * min(1.0, v), color * GROUND * min(1.0, v)
    backlight = 255 * max(0.2, min(1.0, v * 1.5))  # a dim backlight keeps the dark parts dark
    values = (SCENES.index(kind), *shape, *ground, a, b, c, d, e, f, g, h, i, j, k, backlight)
    return np.clip(np.round(values), 0, 255).astype(np.uint8)


# ---- strips: float RGB per LED, through the gamma at the end ----

FOOT = np.minimum(np.arange(LEDS), LEDS - 1 - np.arange(LEDS)).astype(float)  # each LED's height in LEDs
TOP = (LEDS - 1) / 2


def paint(color, levels) -> np.ndarray:
    return np.outer(np.clip(np.broadcast_to(levels, (LEDS,)), 0, 1), color)


def pair(level: float, height: float, width: float = 1.2) -> np.ndarray:
    """Light at `height` (0 the feet, 1 the top) on both sides of the arch."""
    return level * np.clip(1 - np.abs(FOOT - height * TOP) / width, 0, 1)


def tide(level: float, height: float, soft: float = 1.5) -> np.ndarray:
    """Lit from the feet up to `height`."""
    return level * np.clip((height * TOP - FOOT) / soft + 1, 0, 1)


def from_top(age: float, length: float = 0.5, width: float = 2.5) -> np.ndarray:
    """A pulse that leaves the top of the arch and runs down both sides in `length` s."""
    if not 0 <= age < length:
        return np.zeros(LEDS)
    k = age / length
    return (1 - k) * np.clip(1 - np.abs(FOOT - TOP * (1 - k)) / width, 0, 1)


def along(at: float, lantern: int, width: float = 2.0) -> np.ndarray:
    """A dot at `at` LEDs along all three arches end to end (0 the left one's left foot)."""
    return np.clip(1 - np.abs(np.arange(LEDS) + lantern * LEDS - at) / width, 0, 1)


def strip_bytes(x: np.ndarray) -> np.ndarray:
    return np.clip(255 * (np.clip(x, 0, 255) / 255) ** GAMMA, 0, 255).astype(np.uint8)


def build():
    timeline, parts = load()
    frames = int(timeline["duration"] * FPS) + 1
    sections, lines = timeline["sections"], timeline["lines"]
    human = human_at(timeline, frames)
    entry = {e["part"]: e["t"] for e in timeline["entries"]}
    wake = {"left": entry["harp"], "right": entry["lute"], "center": entry["bass"]}
    beats = np.array(timeline["beats"])

    N = {name: Notes(parts[name]) for name in
         ("harp", "bass", "drum", "lute", "fiddle", "whistle", "guitar", "drum~", "bowedbass")}
    N["voice"] = Notes(parts["voice"])
    for name in ("choir1", "choir2", "choir3"):
        N[name] = Notes(parts[name], 52, 69)  # one range, so the low voice sits low and the high one high
    N["machine"] = Notes(parts["arp"] + parts["harp~"])
    L = {name: loudness(name, frames) for name in ("harp", "bass", "lute", "fiddle", "whistle", "guitar", "mix")}
    V = {"voice": vowels("lead-heard", frames), **{k: vowels(k, frames) for k in ("choir1", "choir2", "choir3")}}
    bass_height = followed(np.array([N["bass"].height(N["bass"].p[max(0, N["bass"].last(i / FPS))])
                                     for i in range(frames)]), 0.15, 0.5)
    daisy = timeline["daisy"]

    def line(prefix):
        found = next(x for x in lines if x["text"].startswith(prefix))
        return found["t0"], found["t1"]

    faces_line, gone_line = line("a million bright faces"), line("but nobody sang it")
    carry, coal, own_line = line("Carry it over"), line("hand it along"), line("it's nobody's making and everyone")
    alone = line("it dies in the dark")
    refrain2 = next(s for s in sections if s["id"] == "refrain2")
    refrain2_ends = [x["t1"] for x in lines if refrain2["t0"] < x["t1"] <= refrain2["t1"] + 0.1]
    tunes = {"verse1": ("lute",), "breath1": ("whistle",), "refrain1": ("guitar",), "turn1": ("lute",),
             "verse2": ("lute", "fiddle", "guitar"), "breath2": ("fiddle", "whistle"),
             "refrain2": ("lute", "fiddle", "guitar"), "refrain3": ("lute", "fiddle", "guitar")}

    scenes = np.zeros((frames, 3, RECORD), np.uint8)
    leds = np.zeros((frames, 3, LEDS, 3), np.uint8)
    gaze = {role: 0.0 for role in ROLES}   # smoothed: where each face looks, -1 left to 1 right
    eyes = {role: 0.0 for role in ROLES}   # smoothed: how open its eyes are

    def section_at(t):
        return next((s for s in sections if s["t0"] <= t < s["t1"]), None)

    for i in range(frames):
        t = i / FPS
        s = section_at(t)
        if s is None:
            continue
        sid, u, h = s["id"], (t - s["t0"]) / (s["t1"] - s["t0"]), human[i]

        # ---- the copies ----
        def copy():
            beat_no = int(np.searchsorted(beats, t, side="right"))
            turn = beat_no / 16 * 2 * np.pi  # a dot ticking round a circle, a step a beat
            screen = record("dot", machine(), 0.8, a=36, b=8, c=90,
                            d=(120 - 46 * np.cos(turn)) / 239 * 255, e=128 + 46 / 60 * 128 * np.sin(turn))
            k = N["machine"].last(t)
            lit = 1.0 if k >= 0 and t - N["machine"].t[k] < 0.12 else 0.4
            height = N["machine"].height(N["machine"].p[k]) if k >= 0 else 0
            light = np.maximum(pair(lit, height, 0.6), 0.08 * (FOOT < 0.5))  # one hard light, the feet faint
            return screen, paint(machine(), light)

        # ---- the players ----
        def harp(role, level=1.0, warm=0.0):
            x = np.zeros(LEDS)
            for k in N["harp"].recent(t, 2.2):  # each pluck rings as long as its note, spreading as it fades
                age, life = t - N["harp"].t[k], min(N["harp"].d[k], 1.6) + 0.5
                x = np.maximum(x, max(0.0, 1 - age / life) ** 1.5 * (0.6 + 0.4 * N["harp"].v[k])
                               * pair(1, N["harp"].height(N["harp"].p[k]), 0.7 + age * 2))
            k = N["harp"].last(t)
            p_h = N["harp"].height(N["harp"].p[k]) if k >= 0 else 0.5
            color = own(role, h, warm, p_h)
            ring = min(1.0, N["harp"].since(t) / 0.8)
            v = (0.25 + 0.75 * (1 - ring)) * level
            screen = record("ring", color, v, a=25 + 170 * ring, b=30 + 40 * (1 - ring))
            return screen, paint(color, (0.06 + x) * level)

        def beat(role, level=1.0, warm=0.0):
            hb = bass_height[i]
            color = own(role, h, warm, hb)
            drums = t >= entry["drum"]
            hit = from_top(N["drum"].since(t), 0.45) if drums else np.zeros(LEDS)
            x = np.maximum(tide(0.25 + 0.45 * L["bass"][i], 0.15 + 0.6 * hb), hit)
            punch = max(0.0, 1 - N["drum"].since(t) / 0.25) if drums else 0
            screen = record("rise", color, (0.4 + 0.35 * L["bass"][i] + 0.3 * punch) * level,
                            a=40 + 160 * hb + 40 * punch, b=30)
            return screen, paint(color, x * level)

        def tune(role, names, level=1.0, warm=0.0):
            # the part playing: the first of `names` heard in the last second, or else the one heard last
            name = next((n for n in names if N[n].since(t) < 1.0),
                        min(names, key=lambda n: N[n].since(t)))
            n = N[name]
            x = np.zeros(LEDS)
            for k in n.recent(t, 4.0):
                age, d = t - n.t[k], min(n.d[k], 1.5)
                fade = 1.0 if age < d else max(0.0, 1 - (age - d) / 0.9) ** 2
                if fade > 0:
                    x = np.maximum(x, (0.35 + 0.65 * fade) * fade * pair(1, n.height(n.p[k]), 1.0))
            k = n.last(t)
            p_h = n.height(n.p[k]) if k >= 0 else 0.5
            color = own(role, h, warm, p_h)
            loud = L[name][i]
            screen = record("dot", color, (0.35 + 0.65 * loud) * level, a=40 + 70 * loud, b=40, c=180,
                            d=225 - 190 * p_h, e=128 + 55 * np.sin(t * 0.9))
            return screen, paint(color, (0.05 + x) * level)

        def resting(role, level=0.15):
            color = own(role, h)
            return record("glow", color, level, a=22, b=40), paint(color, level * (FOOT < 1.5))

        def waking(role, player):
            """A copy becoming a player over WAKE_TIME: a ring opens from the center, the colors change."""
            k = (t - wake[role]) / WAKE_TIME
            screen, strip = player
            if k >= 1:
                return screen, strip
            _, copied = copy()
            color = blend(machine(), own(role, h), k)
            if k < 0.6:
                screen = record("ring", color, 1 - 0.5 * k, a=20 + 230 * k / 0.6, b=40)
            return screen, copied * (1 - k) + strip * k

        # ---- the faces ----
        def face(role, singer=None, warm=0.0, dim=1.0, look=0.0, open_eyes=1.0, mouth_rest=0.05):
            gaze[role] += (look - gaze[role]) * 0.12
            eyes[role] += (open_eyes - eyes[role]) * 0.2
            k = ROLES.index(role)
            blink = ((t + 1.3 * k) % (3.1 + 0.7 * k)) < 0.13
            size, apart = EYES[role]
            if singer:
                loud, opening, width = (x[i] for x in V[singer])
                n = N[singer]
                kk = n.last(t)
                p_h = n.height(n.p[kk]) if kk >= 0 else 0.5
            else:
                loud, opening, width, p_h = 0.0, 0.0, 0.5, 0.5
            color = own(role, h, warm, p_h)
            open_ = mouth_rest + (1 - mouth_rest) * loud * (0.3 + 0.7 * opening)
            wide = 0.55 + 0.45 * width - 0.15 * (1 - width) * (1 - opening)
            sway = np.sin(t * 1.3 + k * 2.1) * 8 * loud
            screen = record("face", color, (0.45 + 0.55 * loud) * dim,
                            a=open_ * 95, b=15 + 95 * wide, c=60 + 140 * width, d=172 - 30 * p_h, e=128 + sway,
                            f=60, g=110, h=0 if blink else 255 * eyes[role], i=128 + 120 * gaze[role],
                            j=size, k=apart)
            light = np.full(LEDS, 0.05)
            if singer:
                light = np.maximum(pair(0.25 + 0.75 * loud, p_h, 1.3), 0.6 * from_top(n.since(t)))
            return screen, paint(color, np.maximum(light, 0.04) * dim)

        def looking_at(role, at: float) -> float:
            """Where `role` looks to see something at seat `at` (-1 left, 1 right)."""
            return float(np.clip((at - SEAT[role]) * 1.2, -1, 1))

        out = {}
        if sid in ("intro", "verse1", "breath1", "refrain1") and t < max(wake.values()) + WAKE_TIME:
            for role in ROLES:
                if t < wake[role]:
                    out[role] = copy()
                elif role == "left":
                    out[role] = waking(role, harp(role))
                elif role == "right":
                    out[role] = waking(role, tune(role, tunes.get(sid, ("lute",))))
                else:
                    out[role] = waking(role, beat(role))
        elif sid in ("refrain1", "verse2", "refrain2"):
            out["left"], out["center"], out["right"] = harp("left"), beat("center"), tune("right", tunes[sid])
            if faces_line[0] <= t < faces_line[1]:  # "a million bright faces all lit the same way": copies again
                out = {role: copy() for role in ROLES}
            elif gone_line[0] <= t < gone_line[1] + 0.6:  # "but nobody sang it, so then it was gone": out one by one
                for k, role in enumerate(ROLES):
                    out_at = gone_line[0] + (gone_line[1] - gone_line[0]) * (k + 0.5) / 3
                    left_ = float(np.clip(1 - (t - out_at) / 0.5, 0, 1))
                    out[role] = (out[role][0] if left_ > 0.5 else np.zeros(RECORD, np.uint8),
                                 out[role][1] * left_)
            if sid == "refrain2":  # at each line's end a spark runs from the right lantern to the left
                for end in refrain2_ends:
                    age = t - end
                    if 0 <= age < 0.9:
                        at = 3 * LEDS * (1 - age / 0.9)
                        for k, role in enumerate(ROLES):
                            spark = paint(rgb(PEOPLE_HUE, 0.3), along(at, k, 2.5))
                            out[role] = out[role][0], np.maximum(out[role][1], spark)
        elif sid == "turn1":
            out["right"], out["left"], out["center"] = tune("right", ("lute",)), resting("left"), resting("center")
        elif sid == "breath2":
            out["right"] = tune("right", tunes[sid])
            # the left and center stay out after "so then it was gone", and come back with refrain 2
        elif sid == "turn2":
            # each whistle note runs from the left lantern's left foot to the right's right foot in 1.5 s
            for k, role in enumerate(ROLES):
                x, near, across = np.zeros(LEDS), 0.0, 128.0
                for kk in N["whistle"].recent(t, 1.5):
                    at = (t - N["whistle"].t[kk]) / 1.5 * 3 * LEDS
                    x = np.maximum(x, along(at, k, 3))
                    here = float(np.clip(1 - abs(at - (k + 0.5) * LEDS) / LEDS, 0, 1))
                    if here > near:
                        near, across = here, 128 + np.clip((at - (k + 0.5) * LEDS) / (LEDS / 2), -1, 1) * 127
                color = own(role, h, 0, 0.7)
                screen = record("dot", color, 0.15 + 0.85 * near, a=50, b=40, c=180, d=110, e=across)
                out[role] = screen, paint(color, np.maximum(x, 0.04))
        elif sid == "bridge":
            dim = 1.0 if t < alone[0] else max(0.12, 1 - (t - alone[0]) / (alone[1] - alone[0]))
            open_eyes = 1.0 if t < alone[0] + 2 else 0.0  # they shut their eyes in the dark
            singers = dict(zip(ROLES, ("choir3", "choir1", "choir2")))
            looks = {role: 0.0 for role in ROLES}
            if carry[0] + 1.0 <= t < carry[1]:  # they find each other
                looks = {"left": 0.7, "center": 0.6 * float(np.sign(np.sin(t * 1.4))), "right": -0.7}
            coal_at = None
            if coal[0] <= t < coal[1] + 0.4:  # the coal passes from the left to the right; they watch it
                coal_at = (t - coal[0]) / (coal[1] - coal[0]) * 3 * LEDS
                looks = {role: looking_at(role, coal_at / LEDS - 1.5) for role in ROLES}
            note_at = None
            for k, note in enumerate(daisy):  # the daisy tune: one falling note per lantern, and they look
                if note["t"] <= t < note["t"] + note["dur"]:
                    note_at = (k % 3, note)
                    looks = {role: looking_at(role, SEAT[ROLES[k % 3]]) for role in ROLES}
            if own_line[0] + 3 <= t < alone[0]:
                looks = {role: 0.0 for role in ROLES}  # out at everyone
            for k, role in enumerate(ROLES):
                opened = open_eyes if t >= s["t0"] + 0.3 + 0.6 * k else 0.0  # one at a time as the bridge begins
                out[role] = face(role, singers[role], dim=dim, look=looks[role], open_eyes=opened)
                if coal_at is not None:
                    ember = paint(rgb(0.04, 0.9), along(coal_at, k, 3.5))
                    out[role] = out[role][0], np.maximum(out[role][1] * 0.5, ember)
                if note_at and note_at[0] == k:
                    note = note_at[1]
                    fade = max(0.0, 1 - (t - note["t"]) / note["dur"])
                    white = paint(rgb(0.1, 0.1), pair(fade, np.clip((note["pitch"] - 74) / 14, 0, 1), 1.4))
                    out[role] = out[role][0], np.maximum(out[role][1], white)
        elif sid == "breath3":
            for k, role in enumerate(ROLES):
                opened = 1.0 if t >= s["t0"] + 1.0 + 0.5 * k else 0.0
                screen, _ = face(role, None, dim=0.7, look=0.0, open_eyes=opened)
                color = own(role, h, 0.3)
                hit = from_top(N["drum~"].since(t), 0.45) if t >= entry["drum~"] else np.zeros(LEDS)
                out[role] = screen, paint(color, np.maximum(tide(0.5, u, 2.0), hit))
        elif sid == "refrain3":
            for k, role in enumerate(ROLES):
                screen, voice = face(role, "voice", warm=u, look=0.35 * np.sin(t * 0.37 + k * 2.0))
                if role == "left":
                    _, extra = harp(role, 0.6, u)
                elif role == "center":
                    _, extra = beat(role, 0.6, u)
                else:
                    _, extra = tune(role, tunes[sid], 0.6, u)
                out[role] = screen, np.maximum(voice, extra)
        elif sid == "tag":
            for role in ROLES:
                look = {"left": 0.8, "center": 0.0, "right": -0.8}[role]  # to the singer
                screen, _ = face(role, None, warm=1.0, dim=0.8, look=look, mouth_rest=0.08)
                _, light = harp(role, 0.8, 1.0)
                out[role] = screen, light
        elif sid == "ring":
            for k, role in enumerate(ROLES):
                shut = u >= 0.15 + 0.25 * k  # left first, right last
                gone = float(np.clip((u - (0.25 + 0.25 * k)) * (s["t1"] - s["t0"]) / 0.6, 0, 1))
                screen, _ = face(role, None, warm=1.0, dim=(1 - gone) * 0.7, open_eyes=0.0 if shut else 1.0)
                out[role] = screen, paint(own(role, h, 1.0), (1 - gone) * (0.1 + 0.4 * L["mix"][i]) * (FOOT < 3))

        for k, role in enumerate(ROLES):
            if role in out:
                scenes[i, k] = out[role][0]
                leds[i, k] = strip_bytes(out[role][1])
    return timeline, scenes, leds


def main():
    timeline, scenes, leds = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT, scenes=scenes, leds=leds, fps=FPS, roles=np.array(ROLES))
    frames = len(scenes)
    flat = np.concatenate([scenes, leds.reshape(frames, 3, LEDS * 3)], axis=2)
    flat.tofile(OUT.with_suffix(".bin"))
    meta = {"fps": FPS, "frames": frames, "leds": LEDS, "record": RECORD, "roles": ROLES, "scenes": SCENES,
            "sections": [{"id": s["id"], "t0": s["t0"], "t1": s["t1"]} for s in timeline["sections"]]}
    OUT.with_suffix(".json").write_text(json.dumps(meta))
    print(f"{OUT.relative_to(ROOT)} (+ .bin, .json): {frames} frames, {frames / FPS:.1f} s")


if __name__ == "__main__":
    main()
