"""Who sang what: sung takes kept on this computer, a folder per singer (the studio in a browser keeps none).

    recordings/<singer>/<song>-<yyyymmdd-hhmmss>.wav    a take, already lined up with the guide
    recordings/<singer>/<song>-<yyyymmdd-hhmmss>.json   who sang it, to which guide (and which mix of
                                                        it they heard), whether to use it
    recordings/guides/<song>.<digest>.score.json        every guide anyone has sung to, so that a
                                                        take still lines up after the song changes

A take of one section holds only its window of the guide: its sidecar says
where on the guide's clock its first sample is (from_s), where it was meant to
end or the singer stopped (to_s), which section it sang (section, its index
in the lyrics' sections) and which set, key and speed it was sung to (spec,
as tools/guides.py names them). A take from the top has from_s 0, or none.

recordings/ never goes in git. A singer's name only names their folder here;
it goes into a phrasing only if they ask to be credited (principle 12).
Takes sung on the online page (web/sing) arrive here the same way, through
tools/invite.py, their sidecars saying so (source "online") and whose they
are there (sid); online() finds them, and remove() and remove_singer() delete
a take or a singer with everything measuring them kept.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
RECORDINGS = ROOT / "recordings"
GUIDES = RECORDINGS / "guides"
NOT_SINGERS = ("guides", "words")  # folders in recordings/ that hold no one's takes


def slug(name: str) -> str:
    """A singer's folder: their name in lowercase letters and digits, joined by hyphens; accents
    dropped (Zoë: zoe), letters of other scripts kept as they are."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", "-", plain.strip().lower()).strip("-") or "someone"


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

    def said(self, name: str) -> str | float | int | None:
        """What the sidecar says of one field, None if nothing (a query string's empty value too)."""
        value = self.info.get(name)
        return None if value is None or value == "" else value

    @property
    def from_s(self) -> float:
        """Where on its guide's clock the take's first sample is, in seconds: 0 for a take from the top."""
        return float(self.said("from_s") or 0.0)

    @property
    def to_s(self) -> float | None:
        """Where it was meant to end, or where the singer stopped (guide time); None: the song's end."""
        return None if self.said("to_s") is None else float(self.said("to_s"))

    @property
    def section(self) -> int | None:
        """The one section it sang (its index in the lyrics' sections); None for a take of the whole song."""
        return None if self.said("section") is None else int(self.said("section"))

    @property
    def spec(self) -> str | None:
        """The set, key and speed it was sung to (a spec id, a.k-2.t90); None for the song's own guide."""
        return self.info.get("spec") or None

    @property
    def online(self) -> bool:
        """Whether it was sung on the online page."""
        return self.info.get("source") == "online"

    @property
    def sid(self) -> str | None:
        """Its singer's id on the online page, for a take sung there."""
        return self.info.get("sid") or None

    @property
    def recorded_at(self) -> datetime | None:
        """When it was sung, in this computer's local time: as its sidecar says (a time with its zone is
        moved into this one), or else its file's name."""
        with_time = self.info.get("recorded")
        if with_time:
            try:
                when = datetime.fromisoformat(str(with_time))
                return when.astimezone().replace(tzinfo=None) if when.tzinfo else when
            except ValueError:
                pass
        named = re.search(r"-(\d{8}-\d{6})(-\d+)?$", self.path.stem)
        return datetime.strptime(named[1], "%Y%m%d-%H%M%S") if named else None

    def sidecar(self) -> Path:
        return self.path.with_suffix(".json")

    def save(self) -> None:
        data = {**self.info, "singer": self.singer, "song": self.song, "guide": self.guide, "use": self.use}
        self.sidecar().write_text(json.dumps(data, indent=1) + "\n")


STAMPED = re.compile(r"^(?P<song>.+)-\d{8}-\d{6}(-\d+)?$")  # <song>-<yyyymmdd-hhmmss>, maybe -2, -3...


def load(path: Path) -> Take:
    path = Path(path).absolute()  # not resolve(): a worktree's symlinked recordings/ must stay under its root
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


def online(song: str | None = None) -> list[Take]:
    """Every take sung on the online page (of one song, or any), oldest first: each knows its
    singer's id there (Take.sid) and when it was sung (Take.recorded_at), so a purge on a date,
    or a singer who withdraws, finds every one."""
    found = []
    for wav in RECORDINGS.glob("*/*.wav"):
        if wav.parent.name not in NOT_SINGERS:
            t = load(wav)
            if t.online and (song is None or t.song == song):
                found.append(t)
    return sorted(found, key=lambda t: (t.recorded_at or datetime.min, t.path.name))


def caches(take: Take | Path) -> list[Path]:
    """What measuring a take kept about it, whether or not it's there yet: its measurement
    (tools/phrasing.py, renders/measured/) and where MFA heard its vowels (tools/align.py,
    renders/measured/mfa/), each named for the take's path as those tools name it."""
    path = Path(take.path if isinstance(take, Take) else take).resolve()
    name = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.as_posix().lstrip("/")
    flat = name.replace("/", "__").removesuffix(".wav") + ".json"
    measured = ROOT / "renders" / "measured"
    return [measured / flat, measured / "mfa" / flat]


def remove(take: Take) -> list[Path]:
    """Delete a take: its WAV, its sidecar and what measuring it kept. Returns what was deleted."""
    gone = []
    for f in [take.path, take.sidecar(), *caches(take)]:
        if f.exists():
            f.unlink()
            gone.append(f)
    return gone


def remove_singer(who: str, song: str | None = None) -> list[Path]:
    """Delete one singer's takes (by folder name) of a song, or of every song, with what measuring
    them kept, their phrasings (renders/phrasing/<song>.<who>.json) and the karaoke's renders of the
    machine singing their way; their folder too, once nothing else is in it (without a song,
    everything in it goes). A blend of everyone's phrasings keeps what it learned until it's made
    again. Returns what was deleted."""
    if who != slug(who) or who in NOT_SINGERS:
        raise ValueError(f"{who!r} isn't a singer's folder")
    folder = RECORDINGS / who
    gone = []
    for wav in sorted(folder.glob("*.wav")):
        t = load(wav)
        if song is None or t.song == song:
            gone += remove(t)
    renders = ROOT / "renders"
    for f in [*(renders / "phrasing").glob(f"{song or '*'}.{who}.json"), *renders.glob(f"{song or '*'}.karaoke.{who}.flac")]:
        f.unlink()
        gone.append(f)
    if folder.is_dir() and (song is None or not [f for f in folder.iterdir() if f.name != ".DS_Store"]):
        gone += [f for f in sorted(folder.rglob("*")) if f.is_file()]
        shutil.rmtree(folder)
    return gone


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
