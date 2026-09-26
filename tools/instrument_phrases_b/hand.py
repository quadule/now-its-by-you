"""Hand percussion: claps, stomps, a shaker, a tambourine, a cajon, in D's tempo world (96 to 110 BPM).

Grooves are step patterns as the kit's: one character a step (sixteenths unless said otherwise), bars
run on: "x" a stroke at the line's velocity, "X" an accent, "g" a ghost, "." nothing. The shaker's and
the tambourine's calibration parts are measured against percussion's target (-28.4 LUFS) by the solo
tool, but their SPECs name their own (-31.4 and -30.4: a texture over the pulse), which their tests use.
"""

from __future__ import annotations

from _common import Clock

MODULE = {"claps": "hand", "stomps": "hand", "shaker": "shaker", "tambourine": "shaker", "cajon": "cajon"}

STEP = {"x": 1.0, "X": 1.35, "g": 0.45}
DRUMS = {"claps": "drum", "stomps": "drum", "cajon": "drum"}  # the mix strip a demo borrows until it has its own


def steps(clock: Clock, part: str, lines: dict, per_beat: int = 4, vel: float = 0.6, offset: float = 0.0) -> list:
    """Notes for every line: {art: pattern} or {art: (pattern, vel)}; a stroke lasts a step."""
    notes = []
    for art, spec in lines.items():
        pattern, v = spec if isinstance(spec, tuple) else (spec, vel)
        for k, ch in enumerate(pattern.replace(" ", "").replace("|", "")):
            if ch in STEP:
                notes.append(clock.note(part, offset + k / per_beat, 1.0 / per_beat, 60, min(1.0, v * STEP[ch]), art))
    return sorted(notes, key=lambda n: n.start)


def _stomp_clap(c: Clock) -> dict:
    """Two bars of snaps over soft stomps, then the stomp-clap (stomps on 1 and 3, claps on 2 and 4) with a
    pickup stomp on the and of 4 every fourth bar, and a last stomp on the downbeat."""
    stomps = steps(c, "stomps", {"stomp": ("x.......x.......|x.......x.......", 0.5)}) + steps(
        c, "stomps", {"stomp": ("x.......x.......|x.......x.......|x.......x.......|x.......x.....x.|"
                                "x.......x.......|x.......x.......|x.......x.......|x.......x.....x.|X", 0.7)}, offset=8)
    claps = steps(c, "claps", {"snap": ("....x.......x...|....x.......x...", 0.45)}) + steps(
        c, "claps", {"clap": ("....x.......x...|" * 8, 0.65)}, offset=8)
    return dict(stomps=stomps, claps=claps)


def _shaker(c: Clock) -> dict:
    """Steady sixteenths, accented on the backbeat, a two-beat roll into the fourth bar, then eighths."""
    return dict(shaker=steps(c, "shaker", {"shaker": ("xgxgXgxgxgxgXgxg|xgxgXgxgxgxgXgxg|xgxgXgxg........", 0.6)})
                + steps(c, "shaker", {"shaker-roll": ("x", 0.55)}, per_beat=0.5, offset=10)
                + steps(c, "shaker", {"shaker": ("x.x.X.x.x.x.X.x.|x.x.X.x.x.x.X.x.|X", 0.6)}, offset=12))


def _tambourine(c: Clock) -> dict:
    """The palm on 2 and 4, a light shake on the off-beat eighths, a finger tap now and then, a thumb roll
    to finish and one last palm."""
    lines = {
        "tambourine": ("....X.......X...|....X.......X...|....X.......X...|....X...........", 0.6),
        "tambourine-shake": ("..x...x...x...x.|..x...x...x...x.|..x...x...x...x.|..x.............", 0.4),
        "tambourine-tap": ("......g.........|..............g.|......g.........|................", 0.6),
    }
    return dict(tambourine=steps(c, "tambourine", lines)
                + steps(c, "tambourine", {"tambourine-roll": ("x", 0.5)}, per_beat=0.5, offset=14)
                + steps(c, "tambourine", {"tambourine": ("X", 0.7)}, offset=16))


def _cajon(c: Clock) -> dict:
    """A cajon's pop groove: bass on 1 and the and of 2, slaps on 2 and 4, ghost taps between; a fill of
    slaps and mids in the fourth bar; a last bass stroke."""
    lines = {
        "cajon-bass": ("x.....x.x.......|x.....x.x.......|x.....x.x.......|x.....x.........", 0.65),
        "cajon-slap": ("....X.......X...|....X.......X...|....X.......X...|....X.......", 0.65),
        "cajon-tap": ("..g.g..g..g.g.gg|..g.g..g..g.g.gg|..g.g..g..g.g.gg|..g.........", 0.6),
    }
    fill = steps(c, "cajon", {"cajon-slap": "x.x.", "cajon-mid": ".x.x"}, offset=15.0, vel=0.7)
    return dict(cajon=steps(c, "cajon", lines) + fill + steps(c, "cajon", {"cajon-bass": ("X", 0.8)}, offset=16))


def _cajon_and_shaker(c: Clock) -> dict:
    """The acoustic duo's kit: the cajon groove under the shaker's eighths."""
    return dict(cajon=_cajon(c)["cajon"],
                shaker=steps(c, "shaker", {"shaker": ("x.x.X.x.x.x.X.x.|" * 4, 0.5)}))


c100, c104 = Clock(100), Clock(104)
PHRASES = {
    "hand-stomp-clap": dict(
        parts=_stomp_clap(c100), mix_as=DRUMS,
        about="two bars of snaps over soft stomps, then the stomp-clap at 100 BPM: stomps on 1 and 3 (a small "
              "group on a wooden stage: the boom, the boards' knock), claps on 2 and 4 (three to eight people, "
              "their onsets spread over 10 to 25 ms), a pickup stomp every fourth bar",
    ),
    "hand-shaker": dict(
        parts=_shaker(c100), settings={"tempo": 100},
        about="a shaker in sixteenths at 100 BPM, forward strokes on the eighths, accents on the backbeat, a "
              "two-beat roll, then eighths",
    ),
    "hand-tambourine": dict(
        parts=_tambourine(c100),
        about="a tambourine: the palm on 2 and 4 (a crash of jingles, and a thump if headed), a light shake on "
              "the off-beats, finger taps, a thumb roll to finish",
    ),
    "hand-cajon": dict(
        parts=_cajon(c104), mix_as=DRUMS,
        about="a cajon at 104 BPM: bass strokes (the boom through the hole) on 1 and the and of 2, slaps (a "
              "crack, the corners, the snares) on 2 and 4, ghost taps between, a fill in the fourth bar",
    ),
    "hand-cajon-shaker": dict(
        parts=_cajon_and_shaker(c104), mix_as=DRUMS, settings={"tempo": 104},
        about="the acoustic duo's kit: the cajon groove under a shaker's eighths",
    ),
}

LEVELS = {
    "claps": ("percussion", steps(c100, "claps", {"clap": "....x.......x...|" * 8})),
    "stomps": ("percussion", steps(c100, "stomps", {"stomp": "x.......x.......|" * 8})),
    "shaker": ("percussion", steps(c100, "shaker", {"shaker": "xxxxxxxxxxxxxxxx|" * 8})),
    "tambourine": ("percussion", steps(c100, "tambourine", {"tambourine": "....x.......x...|" * 8})),
    "cajon": ("percussion", steps(c100, "cajon", {"cajon-bass": "x.......x.......|" * 8,
                                                  "cajon-slap": "....x.......x...|" * 8,
                                                  "cajon-tap": ".x.x.x.x.x.x.x.x|" * 8})),
}
