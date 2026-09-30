"""The singing kit: everything the web studio needs to take a take, made ahead by webstudio/prepare.py.

Measuring a take compares it with the template singer singing the same guide, and making that analysis for a
whole guide takes 4 GB and a minute (tools/phrasing.py template(): the formant singer, then WORLD's harvest,
which holds about 14 MB for every second analysed). A server in a memory-capped container can't, so the kit
carries it, made once on a computer that can, beside the guides themselves:

    offer.json                                      what is offered: the song (its genome's digest), each
                                                    version to sing to (a spec, tools/guides.py) and its guide
    song/<song>.json                                the genome the kit was made from
    guides/<song>.<digest>.score.json               each guide's score, by digest (tools/takes.py GUIDES)
    guide/<song>/<spec>.score.json, .note.json      each spec's score as tools/guides.py keeps it
    audio/<spec>.melody.flac                        the melody guide a visitor hears (whistle and pulse)
    lyrics/<spec>.json                              its words, notes, beats and sections (tools/karaoke.py)
    measured/templates/<digest>.<key>.<ver>.npz     the template singer's analysis in each key offered

Nothing here is anyone's voice: the guides are the song's, the templates the machine's. This module reads the
kit with the standard library alone, so the studio's own process never loads the measuring tools.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

VERSION = 1  # the kit's layout
ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "renders" / "sing-kit"
SPEC = re.compile(r"^[a-z0-9]{1,8}\.k-?\d{1,2}\.t\d{1,3}$")
DIGEST = re.compile(r"^[0-9a-f]{12}$")


def home(given: str | Path | None = None) -> Path:
    """Where the kit is: given, else $SONGBIRD_SING_KIT, else renders/sing-kit in a checkout."""
    return Path(given or os.environ.get("SONGBIRD_SING_KIT") or DEFAULT).expanduser().resolve()


class Kit:
    def __init__(self, root: str | Path | None = None):
        self.root = home(root)

    # ------------------------------------------------------------ where things are

    @property
    def offer_path(self) -> Path:
        return self.root / "offer.json"

    def genome(self, song: str) -> Path:
        return self.root / "song" / f"{song}.json"

    @property
    def guides(self) -> Path:  # tools/takes.py GUIDES: scores by digest
        return self.root / "guides"

    @property
    def specs(self) -> Path:  # tools/guides.py GUIDES: each spec's score and note
        return self.root / "guide"

    @property
    def measured(self) -> Path:  # tools/phrasing.py MEASURED: the templates
        return self.root / "measured"

    def audio(self, spec: str) -> Path:
        return self.root / "audio" / f"{spec}.melody.flac"

    def lyrics(self, spec: str) -> Path:
        return self.root / "lyrics" / f"{spec}.json"

    # ------------------------------------------------------------ what it offers

    def offer(self) -> dict | None:
        try:
            data = json.loads(self.offer_path.read_text())
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and data.get("kit") == VERSION else None

    def spec(self, spec_id: str) -> dict | None:
        """One version offered, by its id; None if it isn't offered (or isn't an id at all)."""
        offer = self.offer()
        if offer is None or not SPEC.match(str(spec_id or "")):
            return None
        return next((s for s in offer["specs"] if s["id"] == spec_id), None)

    def fits(self, genome_path: Path) -> str | None:
        """Why this kit can't take takes for the song at genome_path; None if it can."""
        offer = self.offer()
        if offer is None:
            return ("Singing here needs its guides made first (python -m webstudio.prepare), and they "
                    "haven't been.")
        digest = hashlib.sha256(Path(genome_path).read_bytes()).hexdigest()
        if digest != offer.get("genome"):
            return "The singing guides were made for another version of this song; they need making again."
        return None
