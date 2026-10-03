"""The released version's guide, for singing it in the web studio: webstudio/released.json.

    uv run python tools/released_guide.py            # renders/review/contest.flac -> webstudio/released.json

Opening the release in the studio gives its child (the next version, as the program sings it today: another day,
another tempo, other words), not the release. So the release's guide is laid once, here, as tools/piano_score.py
lays its score: from the packet with the packet's own program (checked against its record), realize() with the
record's params and words, but without its singer's phrasing (a guide is the tune on its grid) and without the
lay. It keeps only what a guide keeps (webstudio/guide.py slim: the voice and the parts that state the tune), the
beats, and the key against the song's own (the lead song this tree sings: tools/phrasing.py reads it to know the
tune). The words are checked against the packet's lyrics.txt, as piano_score.py checks its score's.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from songbird import genome as G_now  # noqa: E402  (this tree's, before the packet's program replaces songbird)
from songbird.realize import choose_params as params_now  # noqa: E402
from webstudio import guide as GD  # noqa: E402

import piano_score  # noqa: E402  (tools/piano_score.py)

OUT = ROOT / "webstudio" / "released.json"
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


def lay(flac: Path, tmp: Path) -> dict:
    """The release's guide score, laid with its own program."""
    tonic_now = params_now(G_now.load(LEAD)).tonic
    record = piano_score.unpack_program(flac, tmp)
    sys.path.insert(0, str(tmp / "program"))
    for name in [m for m in sys.modules if m == "songbird" or m.startswith("songbird.")]:
        del sys.modules[name]
    import songbird
    from songbird import genome as G, pack as P
    from songbird.arrange import Lyrics
    from songbird.realize import Params, realize, timeline

    assert Path(songbird.__file__).is_relative_to(tmp), songbird.__file__
    genome = G.load(tmp / "genome.json")
    params = Params.from_dict(record["params"])
    params = replace(params, singer=record.get("singer") or params.singer, mix=record.get("mix") or params.mix)
    lyrics = Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None
    score = realize(genome, params, lyrics=lyrics)
    if P.words_as_sung(score.to_dict(), genome.title) != (tmp / "lyrics.txt").read_text():
        raise SystemExit(f"{flac}: the guide laid again doesn't sing the packet's words; not trusting it")
    beats = [[t, int(bar)] for t, bar in timeline(genome, params).beats()]
    data = {**score.to_dict(), "tempo": params.tempo, "seed": params.seed, "transpose": params.tonic - tonic_now,
            "beats": beats}
    return {"source": {"file": "renders/review/contest.flac", "id": record.get("id"),
                       "program_sha256": record.get("program_sha256"), "title": genome.title,
                       "made_by": "tools/released_guide.py"},
            "score": GD.slim(data)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("flac", nargs="?", default=str(piano_score.RELEASE))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        out = lay(Path(args.flac), Path(tmp))
    Path(args.out).write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False) + "\n")
    s = out["score"]
    print(f"{args.out}: {out['source']['title']}, {s['tempo']:g} bpm, {s['duration']:.0f} s, "
          f"{sum(1 for n in s['notes'] if n['part'] == 'voice')} sung notes, transpose {s['transpose']}")


if __name__ == "__main__":
    main()
