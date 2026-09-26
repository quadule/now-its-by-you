"""Who sang what: sung takes kept on this computer, a folder per singer (dev-only).

    recordings/<singer>/<song>-<yyyymmdd-hhmmss>.wav    a take, already lined up with the guide
    recordings/<singer>/<song>-<yyyymmdd-hhmmss>.json   who sang it, to which guide (and which mix of
                                                        it they heard), whether to use it
    recordings/guides/<song>.<digest>.score.json        every guide anyone has sung to, so that a
                                                        take still lines up after the song changes

recordings/ never goes in git. A singer's name only names their folder here;
it goes into a phrasing only if they ask to be credited (principle 12).
Takes sung on the online page (web/sing) arrive here the same way, through
tools/invite.py fetch.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).parent.parent
RECORDINGS = ROOT / "recordings"
GUIDES = RECORDINGS / "guides"


def slug(name: str) -> str:
    """A singer's folder: their name in lowercase letters and digits, joined by hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-") or "someone"


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


@dataclass
class Take:
    path: Path  # the WAV
    singer: str  # their name as they wrote it
    song: str  # the genome's stem
    guide: str | None = None  # digest of the guide score it was sung to; None: whatever the guide is now
    use: bool = True  # whether it goes into the singer's phrasing
    info: dict = field(default_factory=dict)  # everything else the sidecar says

    @property
    def who(self) -> str:
        """The singer's folder name."""
        return self.path.parent.name

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix()

    def sidecar(self) -> Path:
        return self.path.with_suffix(".json")

    def save(self) -> None:
        data = {**self.info, "singer": self.singer, "song": self.song, "guide": self.guide, "use": self.use}
        self.sidecar().write_text(json.dumps(data, indent=1) + "\n")


STAMPED = re.compile(r"^(?P<song>.+)-\d{8}-\d{6}(-\d+)?$")  # <song>-<yyyymmdd-hhmmss>, maybe -2, -3...


def load(path: Path) -> Take:
    path = Path(path).resolve()
    side = path.with_suffix(".json")
    data = json.loads(side.read_text()) if side.exists() else {}
    named = STAMPED.match(path.stem)
    song = data.pop("song", named["song"] if named else path.stem)
    return Take(path, data.pop("singer", path.parent.name), song, data.pop("guide", None), data.pop("use", True), data)


def takes(song: str, who: str | None = None) -> list[Take]:
    """Every take of a song, or one singer's (by folder name), oldest first."""
    found = []
    for wav in sorted(RECORDINGS.glob(f"{who or '*'}/{song}-*.wav")):
        if wav.parent != GUIDES:
            found.append(load(wav))
    return sorted(found, key=lambda t: t.path.name)


def singers(song: str) -> dict[str, list[Take]]:
    """Folder name -> that singer's takes of the song."""
    out: dict[str, list[Take]] = {}
    for t in takes(song):
        out.setdefault(t.who, []).append(t)
    return out


def keep_guide(song: str, score: Path) -> str:
    """Keep a copy of the guide score a take was sung to; returns its digest."""
    d = digest(score)
    GUIDES.mkdir(parents=True, exist_ok=True)
    kept = GUIDES / f"{song}.{d}.score.json"
    if not kept.exists():
        shutil.copyfile(score, kept)
    return d


def guide_score(song: str, d: str | None) -> Path | None:
    kept = GUIDES / f"{song}.{d}.score.json" if d else None
    return kept if kept and kept.exists() else None


def keep(song: str, singer: str, wav: bytes, score: Path, **info) -> Take:
    """Save a new take by singer, sung to the guide whose score is at score."""
    return keep_sung(song, singer, wav, keep_guide(song, score), **info)


def keep_sung(song: str, singer: str, wav: bytes, guide: str, recorded: time.struct_time | None = None,
              **info) -> Take:
    """Save a take by singer, sung to a guide already kept here (by its digest):
    one just sung in the karaoke, or one fetched from the online page. recorded:
    when it was sung, in local time (default now); a second take in the same
    second gets -2, -3... after its time."""
    when = recorded or time.localtime()
    folder = RECORDINGS / slug(singer)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", when)
    path, n = folder / f"{song}-{stamp}.wav", 2
    while path.exists() or path.with_suffix(".json").exists():
        path, n = folder / f"{song}-{stamp}-{n}.wav", n + 1
    path.write_bytes(wav)
    take = Take(path, singer.strip(), song, guide, True,
                {"recorded": time.strftime("%Y-%m-%dT%H:%M:%S", when), **info})
    take.save()
    return take
