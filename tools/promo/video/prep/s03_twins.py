"""s03_instruments' twins: the samples of the synth each player takes over from, around the player's entry.

On each of refrain 1's first three lines a player comes in as a synth goes out: the bass as the layer's synth bass
stops (30.9 s), the guitar as the arp stops (35.6 s), the frame drum as the drum machine stops (40.6 s). This
writes the outgoing synth's own stem samples (stems/<part>.wav, 16-bit mono 44.1 kHz, the shared gain) from a
bar before the player's entry to a bar after it, as data/s03/twin-<part>.bin int16 (scale 1/32768).

    uv run python tools/promo/video/prep/s03_twins.py
"""
from __future__ import annotations

import json
import wave

import numpy as np

from common import DATA, guard, read_json, say, write_array

# the outgoing synth for each player that enters on a line of refrain 1 (timeline.json's levels and entries)
PAIRS = [("bass", "synthbass"), ("guitar", "arp"), ("drum", "drummachine")]


def level_off(levels: list, after: float) -> float:
    """The time a level curve reaches silence (null) at or after `after`."""
    for t, db in levels:
        if t >= after and db is None:
            return t
    raise ValueError("no silence")


def main() -> None:
    tl = read_json(DATA / "timeline.json")
    bar = tl["bar"]
    entries = {e["part"]: e["t"] for e in tl["entries"]}
    index = []
    for player, synth in PAIRS:
        off = level_off(tl["levels"][synth], entries[player] - bar)
        t0, t1 = off - bar, off + bar
        with wave.open(str(guard(DATA / "stems" / f"{synth}.wav")), "rb") as w:
            sr = w.getframerate()
            assert w.getnchannels() == 1 and w.getsampwidth() == 2
            w.setpos(int(round(t0 * sr)))
            n = int(round((t1 - t0) * sr))
            a = np.frombuffer(w.readframes(n), dtype="<i2").copy()
        start = int(round(t0 * sr)) / sr
        write_array(f"s03/twin-{synth}", a, f"{synth}'s stem samples (stems/{synth}.wav) around the {player}'s entry",
                    rate=sr, t0=start, scale=1 / 32768, player=player, synth=synth, silent_at=off)
        index.append({"player": player, "synth": synth, "t0": start, "samples": len(a), "silent_at": off})
        say(f"{synth}: {len(a)} samples from {start:.4f} s (silent at {off:.4f})")
    (guard(DATA / "s03")).mkdir(parents=True, exist_ok=True)
    guard(DATA / "s03" / "twins.json").write_text(json.dumps(index, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
