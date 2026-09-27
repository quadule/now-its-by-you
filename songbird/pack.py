"""The seed packet: one file that is both a playable FLAC and a zip of the program that sang it.

A rendition travels as a single file. Its audio is an ordinary FLAC, and appended to it is a zip
archive holding the program, the song's genome, the rendition's record and its words. Players
ignore bytes after the last audio frame, and zip readers find an archive from the end of a file,
so the same file plays in any player, opens with any unzip tool, and runs with Python:

    python3 now-its-by-you.flac new     sing a new version of it here, today (see bootstrap.py)

Inside the archive (docs/PACKET.md):

    __main__.py       the bootstrap (songbird/bootstrap.py): standard library only
    README.txt        what the file is, in plain words
    LICENSE           CC0
    manifest.json     the rendition's record, with its lineage: id, generation, parent, ancestry
    genome.json       the song's skeleton, as it was sung
    lyrics.txt        the words as sung
    requirements.txt  the program's dependencies, pinned to the versions it ran with
    program/          the program itself: songbird/ (source and data) and pyproject.toml

The archive's offsets are absolute (it is written onto the end of the audio), so readers need no
adjustment; the audio before it is left byte for byte as it was, and packing again replaces the
archive rather than stacking a second one.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import numpy as np

from . import __version__

ROOT = Path(__file__).resolve().parents[1]  # the program's tree: songbird/ and pyproject.toml beside it
RUNTIME = ("numpy", "scipy", "numba", "soundfile", "cmudict")  # pyproject's dependencies, what the program needs
MANIFEST = "manifest.json"
GOAL = 8 * 2**20  # what the portable program + model should fit in (audio is separate): pack warns past it
LIMIT = 40 * 2**20  # a program larger than this is a mistake (a stray render in songbird/), not a program


def packet_start(path: str | Path) -> int | None:
    """Where the attached archive begins in the file, or None if it carries none."""
    try:
        with zipfile.ZipFile(path) as z:
            if MANIFEST not in z.namelist():
                return None
            # zipfile reports each entry's offset in the whole file, whatever came before the archive
            return min(info.header_offset for info in z.infolist())
    except (zipfile.BadZipFile, OSError):
        return None


def audio_bytes(path: str | Path) -> bytes:
    """The file's audio alone: everything before an attached packet."""
    data = Path(path).read_bytes()
    start = packet_start(path)
    return data if start is None else data[:start]


def read_member(path: str | Path, name: str) -> str | None:
    """One text file from a packet's archive, or None."""
    try:
        with zipfile.ZipFile(path) as z:
            return z.read(name).decode() if name in z.namelist() else None
    except (zipfile.BadZipFile, OSError):
        return None


def read_manifest(path: str | Path) -> dict | None:
    """A packet's record, or None if the file carries no packet."""
    try:
        with zipfile.ZipFile(path) as z:
            return json.loads(z.read(MANIFEST)) if MANIFEST in z.namelist() else None
    except (zipfile.BadZipFile, OSError):
        return None


def samples_id(audio: bytes) -> str:
    """A rendition's identity from its audio: the SHA-256 of its decoded 16-bit samples."""
    import soundfile as sf

    pcm, _ = sf.read(io.BytesIO(audio), dtype="int16", always_2d=True)
    return hashlib.sha256(np.ascontiguousarray(pcm, dtype="<i2").tobytes()).hexdigest()


def read_record(path: str | Path, verify: bool = True) -> dict:
    """A rendition's record, from its packet (a FLAC carrying one) or from a render record (.json). A
    packet's record is checked against its own audio, so a lineage is never taken on faith."""
    record = read_manifest(path)
    if record is not None:
        if verify and record.get("id") and samples_id(audio_bytes(path)) != record["id"]:
            raise ValueError(f"{Path(path).name}'s audio isn't the rendition its record describes")
        return record
    try:
        return json.loads(Path(path).read_text())
    except UnicodeDecodeError:
        raise ValueError(f"{path} is neither a packet nor a render record") from None


def lineage(parent: dict | None) -> dict:
    """A child's place in the lineage, from its parent's record (none: the seed)."""
    if not parent:
        return {"generation": 0, "parent_id": None, "ancestry": []}
    return {"generation": int(parent.get("generation", 0)) + 1, "parent_id": parent.get("id"),
            "ancestry": [*(parent.get("ancestry") or []), parent.get("id")]}


def program_files(root: Path = ROOT) -> dict[str, bytes]:
    """The program as it travels: every file of the songbird package (source and data, without caches),
    and pyproject.toml, under program/."""
    files = {}
    for path in sorted((root / "songbird").rglob("*")):
        rel = path.relative_to(root)
        if path.is_dir() or "__pycache__" in rel.parts or path.suffix in (".pyc", ".pyo", ".nbi", ".nbc") \
                or any(part.startswith(".") for part in rel.parts):
            continue
        files[f"program/{rel.as_posix()}"] = path.read_bytes()
    for name in ("pyproject.toml", "LICENSE"):  # the license travels with the program, so children carry it too
        if (root / name).exists():
            files[f"program/{name}"] = (root / name).read_bytes()
    total = sum(len(b) for b in files.values())
    if total > LIMIT:
        biggest = max(files, key=lambda k: len(files[k]))
        raise ValueError(f"the program is {total / 2**20:.0f} MB; is {biggest} meant to travel with it?")
    return files


def budget(root: Path = ROOT) -> dict:
    """Portable bytes before compression, against the GOAL (the artist, 2026-09-27: a goal to keep in mind
    while the model is trimmed, compressed or quantized, not a wall; only LIMIT refuses). Audio and
    installed runtime dependencies are separate."""
    files = program_files(root)
    total = sum(map(len, files.values()))
    model = sum(len(data) for name, data in files.items() if name.endswith(".npz"))
    return {"goal_bytes": GOAL, "limit_bytes": LIMIT, "program_bytes": total, "model_bytes": model,
            "source_bytes": total - model, "headroom_bytes": GOAL - total, "files": len(files)}


def program_sha256(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + hashlib.sha256(files[name]).digest())
    return h.hexdigest()


def requirements() -> str:
    """The runtime dependencies, pinned to the versions this program runs with now."""
    from importlib.metadata import PackageNotFoundError, version

    lines = [f"# songbird {__version__}'s dependencies, as they were when this file was made "
             f"(python {sys.version_info.major}.{sys.version_info.minor})"]
    for name in RUNTIME:
        try:
            lines.append(f"{name}=={version(name)}")
        except PackageNotFoundError:
            lines.append(name)
    return "\n".join(lines) + "\n"


def words_as_sung(score: dict, title: str | None = None) -> str:
    """The words the singer sang, read from a score (its .score.json), a line to a line."""
    notes = sorted((n for n in score["notes"] if n["part"] == "voice" and n.get("syllable")), key=lambda n: n["start"])
    out = [title, ""] if title else []
    line, section, k = [], None, 0
    while k < len(notes):
        n = notes[k]
        if section is not None and n.get("section") != section and not line and out and out[-1] != "":
            out.append("")
        section = n.get("section")
        step = max(1, int(n.get("word_len") or 1))
        line.append((n.get("word") or n["syllable"]).replace("*", "").replace("-", ""))  # focus marks, syllable breaks
        last = notes[min(k + step, len(notes)) - 1]
        k += step
        if last.get("line_end") or k >= len(notes):
            out.append(" ".join(line))
            line = []
    return "\n".join(out).rstrip("\n") + "\n"


def readme(m: dict) -> str:
    title = m.get("title") or "A song"
    generation = m.get("generation", 0)
    where = "the seed: the first version" if generation == 0 else \
        f"generation {generation}, the child of {str(m.get('parent_id'))[:12]}"
    return f"""{title}

{where}; id {str(m.get('id'))[:12]}{', sung ' + m['rendered_at'][:10] if m.get('rendered_at') else ''}.

This file is a song and the program that sang it. It plays as music in any
audio player. It is also a zip archive: unzip, bsdtar, 7-Zip and Python open
it (the FLAC reference decoder reports the archive as trailing data after the
last sample; `flac -d -F` decodes it anyway). And Python runs it:

    python3 THIS_FILE.flac          what this is, and what you can do
    python3 THIS_FILE.flac new      sing a new version here, today
    python3 THIS_FILE.flac unpack   unpack everything into a folder, to read it first

(On Windows: py THIS_FILE.flac.) Running it runs the program inside the file.
It says what it will do and asks before it writes anything.

A new version keeps the song's tune, refrain and chords and inherits from
this one. Its singer, band, room, tempo, key and verses take their character
from a few plain facts about the computer it is sung on (its languages, its
size, its screen's colours) and from the day. Those facts are reduced to a
handful of numbers before anything uses them. Only the numbers are kept, in
~/.songbird/voice.json and in the new version's record, so no one can read
your computer back out of them.
`python3 THIS_FILE.flac songbird harvest --show` shows exactly what is read
and kept, and `... songbird harvest --without ...` leaves anything out.

The first time it runs, the program needs numpy, scipy, numba, soundfile and
cmudict. It fetches them from PyPI (about 100 MB to download, 250 MB on disk)
into ~/.songbird (or $SONGBIRD_HOME); with uv it may also fetch the Python it
was made with. The installers keep their usual download caches. Nothing is
installed into your system.

Inside:
    manifest.json     this version's record: its lineage and every choice it made
    genome.json       the song's skeleton: its tune, refrain, chords and verse bank
    lyrics.txt        the words as sung
    program/          the program that sang it (Songbird {m.get('program_version') or '?'}; its hash,
                      {str(m.get('program_sha256') or '?')[:16]}, is the same in every version it sings)
    requirements.txt  what it needs to run
    LICENSE           CC0: this song and its program belong to no one

Who made this song? Nobody knows.
"""


def _entry(name: str, date: tuple) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=date)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (0o755 if name == "__main__.py" else 0o644) << 16
    return info


def pack(flac: str | Path, record: dict, genome: str | Path, lyrics: str | None = None,
         out: str | Path | None = None, root: Path = ROOT) -> Path:
    """Attach the packet to a rendition's FLAC (in place unless `out` is given). The record is the render
    record (with its lineage); the id it carries must be the audio's own."""
    flac, out = Path(flac), Path(out) if out else Path(flac)
    audio = audio_bytes(flac)
    sha = samples_id(audio)
    if record.get("id") and record["id"] != sha:
        raise ValueError(f"the record is for {record['id'][:12]}, but {flac.name} holds {sha[:12]}")
    program = program_files(root)
    m = {**record, "id": sha, **{k: record[k] for k in ("generation", "parent_id", "ancestry") if k in record}}
    m.setdefault("generation", 0)
    m.setdefault("parent_id", None)
    m.setdefault("ancestry", [])
    m |= {"gate": record.get("gate"), "path": record.get("path", "record"), "llm": None,
          "program_sha256": program_sha256(program), "python": f"{sys.version_info.major}.{sys.version_info.minor}",
          "name": record.get("name")}
    files = {
        "__main__.py": (Path(__file__).with_name("bootstrap.py")).read_bytes(),
        "README.txt": readme(m).encode(),
        "LICENSE": ((root / "LICENSE").read_bytes() if (root / "LICENSE").exists()
                    else b"CC0 1.0 Universal: dedicated to the public domain.\n"),
        MANIFEST: (json.dumps(m, indent=2) + "\n").encode(),
        "genome.json": Path(genome).read_bytes(),
        "requirements.txt": requirements().encode(),
        **program,
    }
    if lyrics:
        files["lyrics.txt"] = lyrics.encode()
    total = sum(map(len, files.values()))
    if total > LIMIT:
        raise ValueError(f"the program, model and rendition data are {total / 2**20:.2f} MiB, "
                         f"over the {LIMIT / 2**20:g} MiB limit (audio excluded)")
    if total > GOAL:
        print(f"songbird: the program, model and rendition data are {total / 2**20:.2f} MiB, past the "
              f"{GOAL / 2**20:g} MiB goal (audio excluded)", file=sys.stderr)
    # the entries' dates are the rendition's own, so the same rendition packs to the same bytes
    stamp = re.match(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)", m.get("rendered_at") or "")
    date = tuple(int(x) for x in stamp.groups()) if stamp and int(stamp.group(1)) >= 1980 else (1980, 1, 1, 0, 0, 0)
    buffer = io.BytesIO(audio)
    buffer.seek(0, io.SEEK_END)
    with zipfile.ZipFile(buffer, "a", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        order = ["__main__.py", "README.txt", MANIFEST, "genome.json", "lyrics.txt", "LICENSE", "requirements.txt"]
        for name in [n for n in order if n in files] + sorted(n for n in files if n not in order):
            z.writestr(_entry(name, date), files[name])
    if buffer.tell() - len(audio) > LIMIT:
        raise ValueError(f"the attached archive exceeds the {LIMIT / 2**20:g} MiB limit (audio excluded)")
    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(buffer.getvalue())
    tmp.replace(out)
    return out


def unpack(path: str | Path, to: str | Path) -> Path:
    """Unpack a packet's archive into a folder."""
    to = Path(to)
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise ValueError(f"{path} carries no packet") from None
    with z:
        if MANIFEST not in z.namelist():
            raise ValueError(f"{path} carries no packet")
        for info in z.infolist():
            if not (to / info.filename).resolve().is_relative_to(to.resolve()):
                raise ValueError(f"refusing to unpack {info.filename!r} outside {to}")
        z.extractall(to)
    return to
