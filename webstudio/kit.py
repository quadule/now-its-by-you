"""The singing kit: what measuring a take needs besides the take, made as it's needed and kept (docs/WEB-SINGING.md).

Measuring a take compares it with the template singer singing the same notes (tools/phrasing.py template()), on
the guide the take was sung to. Both are made from the version the visitor sang (webstudio/guide.py), when they
sing it: the guide's score when they open Sing, its melody and the template singer's analysis of the stretch they
sing (a section, or each piece of a whole song) when it's first needed. Nothing is made ahead, so the guide is
always the version on the page. The kit is a folder laid out as the tools expect their own:

    song/<song>.json                                    the song a way of singing is made for (its genome)
    guides/<song>.<digest>.score.json                   each guide's score, by digest (tools/takes.py GUIDES)
    audio/<digest>.<from ms>-<to ms>.wav                a stretch of a guide's melody (a server's; a browser keeps
                                                        its own in IndexedDB)
    measured/parts/<notes>.<key>.<measuring code>.npz   the template singer's analysis of a stretch's notes, in a
                                                        take's key (webstudio/worker.py part_template)

On a server it is a folder of the studio's (--sing-kit, else $SONGBIRD_SING_KIT, else the studio's home), its files
let go a while after they were last used; in a visitor's browser it is the measuring worker's memory, filled from
and saved back to the browser's own storage. Nothing here is anyone's voice: the guides are the song's, the
templates the machine's. This module needs the standard library alone, so the studio's own process never loads
the measuring tools.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIGEST = re.compile(r"^[0-9a-f]{12}$")
KEEP_DAYS = 30  # a file of the kit kept on a server after it was last used


def home(given: str | Path | None = None, default: str | Path | None = None) -> Path:
    """Where the kit is: given, else $SONGBIRD_SING_KIT, else default."""
    where = given or os.environ.get("SONGBIRD_SING_KIT") or default
    if not where:
        raise ValueError("no folder for the singing kit")
    return Path(where).expanduser().resolve()


class Kit:
    def __init__(self, root: str | Path | None = None, default: str | Path | None = None):
        self.root = home(root, default)

    # ------------------------------------------------------------ where things are

    def genome(self, song: str) -> Path:
        return self.root / "song" / f"{song}.json"

    @property
    def guides(self) -> Path:  # tools/takes.py GUIDES: scores by digest
        return self.root / "guides"

    @property
    def specs(self) -> Path:  # tools/guides.py GUIDES (nothing is written there: the tools only want it to exist)
        return self.root / "guide"

    @property
    def measured(self) -> Path:  # tools/phrasing.py MEASURED: the templates
        return self.root / "measured"

    def guide(self, song: str, digest: str) -> Path | None:
        """A guide's score, if it is here."""
        if not DIGEST.match(str(digest or "")):
            return None
        f = self.guides / f"{song}.{digest}.score.json"
        return f if f.is_file() else None

    def audio(self, digest: str, a: float, b: float) -> Path:
        return self.root / "audio" / f"{digest}.{round(a * 1000)}-{round(b * 1000)}.wav"

    # ------------------------------------------------------------ keeping

    def keep_song(self, song: str, data: bytes) -> Path:
        f = self.genome(song)
        if not f.is_file() or f.read_bytes() != data:
            write(f, data)
        return f

    def keep_guide(self, song: str, digest: str, text: str) -> Path:
        f = self.guides / f"{song}.{digest}.score.json"
        if f.is_file():
            with contextlib.suppress(OSError):
                f.touch()
        else:
            write(f, text.encode())
        return f

    def prune(self, days: float = KEEP_DAYS) -> int:
        """What wasn't used for days goes (the songs stay: each is the studio's own)."""
        cutoff, gone = time.time() - days * 86400, 0
        for folder in (self.guides, self.root / "audio", self.measured / "parts"):
            for f in folder.glob("*") if folder.is_dir() else ():
                with contextlib.suppress(OSError):
                    if f.is_file() and f.stat().st_mtime < cutoff:
                        f.unlink()
                        gone += 1
        return gone


def write(f: Path, data: bytes) -> None:
    """Whole or not at all, whoever else is writing it."""
    f.parent.mkdir(parents=True, exist_ok=True)
    part = f.with_name(f"{f.name}.{secrets.token_hex(4)}.part")
    part.write_bytes(data)
    os.replace(part, f)
