"""Hand percussion: claps, stomps, a shaker, a tambourine, a cajon, in D's tempo world (96 to 110 BPM)."""

from __future__ import annotations

from _common import Clock

MODULE = {"claps": "hand", "stomps": "hand"}

BPM = 100
c = Clock(BPM)


def _stomp_clap(bars: int = 8) -> dict:
    """The stomp-clap: two bars of snaps and soft stomps, then stomps on 1 and 3, claps on 2 and 4, a pickup
    stomp on the and of 4 every fourth bar, and a last bar held for the downbeat."""
    stomps, claps = [], []
    for bar in range(bars):
        b = 4 * bar
        intro = bar < 2
        for beat in (0, 2):
            stomps.append(c.note("stomps", b + beat, 0.5, 60, 0.5 if intro else 0.7, "stomp"))
        for beat in (1, 3):
            claps.append(c.note("claps", b + beat, 0.5, 60, 0.45 if intro else 0.65, "snap" if intro else "clap"))
        if bar % 4 == 3:
            stomps.append(c.note("stomps", b + 3.5, 0.5, 60, 0.55, "stomp"))
    stomps.append(c.note("stomps", 4 * bars, 1.0, 60, 0.8, "stomp"))
    return dict(stomps=stomps, claps=claps)


PHRASES = {
    "hand-stomp-clap": dict(
        parts=_stomp_clap(),
        about="two bars of snaps over soft stomps, then the stomp-clap at 100 BPM: stomps on 1 and 3 (a small "
              "group on a wooden stage: the boom, the boards' knock), claps on 2 and 4 (three to eight people, "
              "their onsets spread over 10 to 25 ms), a pickup stomp every fourth bar",
    ),
}

LEVELS = {
    "claps": ("percussion", [c.note("claps", 4 * bar + beat, 0.5, 60, 0.6, "clap") for bar in range(8) for beat in (1, 3)]),
    "stomps": ("percussion", [c.note("stomps", 4 * bar + beat, 0.5, 60, 0.6, "stomp") for bar in range(8)
                              for beat in (0, 2)]),
}
