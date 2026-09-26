"""This file is a song, and the program that sang it.

The file plays as music in any audio player. It is also a zip archive
holding the program that sang it (Songbird), the song's skeleton, this
version's record and its words. Run it with Python and it sings a new version
of the song on your computer:

    python3 THIS_FILE.flac              what this is, and what you can do
    python3 THIS_FILE.flac new          sing a new version here, today
    python3 THIS_FILE.flac unpack       unpack everything into a folder, to read it first
    python3 THIS_FILE.flac songbird ... run one of the program's own commands

(On Windows, `py THIS_FILE.flac`.) Running it runs the program inside the
file. Before anything is written, it says what it will do and asks. The first
time, the program needs numpy, scipy, numba, soundfile and cmudict. It fetches
them from PyPI into a folder of its own (~/.songbird, or $SONGBIRD_HOME), and
installs nothing into your system. `--yes` answers the question in advance;
`--here` uses this Python as it is, for people who already have them. Both go
before the command.

This is the archive's __main__.py. It is standard-library only, and it runs
before anything is set up.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

PACKET = Path(os.path.abspath(sys.argv[0]))
HOME = Path(os.environ.get("SONGBIRD_HOME") or Path.home() / ".songbird")
MOST = 100 * 2**20  # the most an archive may unpack to: the program is a few MB
FLAGS = ("--yes", "--here")


def say(text: str = "") -> None:
    print(text, flush=True)


def run_as() -> str:
    return "py" if os.name == "nt" else "python3"


def usage(z: zipfile.ZipFile) -> str:
    name = PACKET.name
    lines = [f"usage: {run_as()} {name} [--yes] [--here] [new | unpack [DIR] | about | songbird COMMAND ...]", "",
             "  new             sing a new version of the song here, today, shaped by this computer and the day"]
    if "program/songbird/studio.py" in z.namelist():
        lines.append("  studio          open the studio: explore the choices, change them, record, then sing it")
    lines += ["  unpack [DIR]    unpack the program, the song and this version's record, to read them first",
              "  about           what this file is (the default)",
              "  songbird ...    run one of the program's own commands, e.g. `songbird render --help`"]
    return "\n".join(lines)


def manifest(z: zipfile.ZipFile) -> dict:
    try:
        m = json.loads(z.read("manifest.json"))
    except (KeyError, ValueError) as e:
        raise SystemExit(f"{PACKET.name} carries no readable record ({e})")
    if not isinstance(m, dict):
        raise SystemExit(f"{PACKET.name}'s record isn't a record")
    return m


def text(m: dict, key: str, n: int | None = None) -> str:
    value = m.get(key)
    value = value if isinstance(value, str) else ""
    return value[:n] if n else value


def program_hash(z: zipfile.ZipFile) -> str:
    """The program's hash, computed from the archive as songbird.pack computes it when packing."""
    h = hashlib.sha256()
    for name in sorted(n for n in z.namelist() if n.startswith("program/") and not n.endswith("/")):
        h.update(name.encode() + b"\0" + hashlib.sha256(z.read(name)).digest())
    return h.hexdigest()


def about(z: zipfile.ZipFile, m: dict) -> None:
    generation = m.get("generation") if isinstance(m.get("generation"), int) else 0
    say(text(m, "title") or "A song")
    if generation == 0:
        say("the seed: the first version, sung by the program that made it")
    else:
        say(f"generation {generation}: {generation} version{'s' if generation != 1 else ''} before this one")
    if text(m, "rendered_at"):
        say(f"sung {text(m, 'rendered_at', 10)}")
    say(f"id {text(m, 'id', 12) or '?'}; program {text(m, 'program_version') or '?'}, "
        f"{text(m, 'program_sha256', 16) or '?'}")
    say()
    say("This file plays as music. It is also the program that sang it: run it to sing a new version of")
    say("the song on your computer, shaped by a few plain facts about it and by the day. Running it runs")
    say("the program inside; `unpack` lets you read it all first (README.txt says what it reads and keeps).")
    say()
    say(usage(z))


def safe_members(z: zipfile.ZipFile, to: Path) -> list[zipfile.ZipInfo]:
    """Every entry, checked to land inside `to`, and not too much in all."""
    root = os.path.realpath(to)
    if sum(i.file_size for i in z.infolist()) > MOST:
        raise SystemExit(f"{PACKET.name} would unpack to more than {MOST // 2**20} MB; not unpacking it")
    for info in z.infolist():
        target = os.path.realpath(os.path.join(root, info.filename))
        if os.path.commonpath([root, target]) != root:
            raise SystemExit(f"refusing to unpack {info.filename!r}: it would land outside {to}")
    return z.infolist()


def unpack(z: zipfile.ZipFile, to: Path) -> Path:
    to.mkdir(parents=True, exist_ok=True)
    z.extractall(to, members=safe_members(z, to))
    return to


def packet_hash() -> str:
    h = hashlib.sha256()
    with open(PACKET, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class Lock:
    """One setup at a time for a folder: a lock file made exclusively, waited on, and cleared if stale."""

    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        start = time.time()
        while True:
            try:
                os.close(os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 1800:  # a setup that died long ago
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.time() - start > 1800:
                    raise SystemExit(f"another setup has held {self.path} for half an hour; remove it if it's stale")
                time.sleep(1.0)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def extracted(z: zipfile.ZipFile, key: str) -> Path:
    """The packet unpacked into its own folder, named by the file's own hash (so a changed file never
    runs an old copy, and nothing in the record chooses a path), unpacked whole or not at all."""
    where = HOME / "packets" / key
    if (where / ".complete").exists():
        return where
    with Lock(HOME / "packets" / f"{key}.lock"):
        if (where / ".complete").exists():
            return where
        tmp = Path(tempfile.mkdtemp(prefix=f".{key}-", dir=HOME / "packets"))
        try:
            unpack(z, tmp)
            (tmp / ".complete").write_text(datetime.now().isoformat() + "\n")
            if where.exists():
                shutil.rmtree(where)
            os.replace(tmp, where)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
    return where


def environment(requirements: bytes, wanted: str) -> tuple[Path, Path]:
    key = hashlib.sha256(requirements + wanted.encode()).hexdigest()[:16]
    env = HOME / "envs" / key
    return env, env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def set_up(where: Path, env: Path, py: Path, wanted: str) -> None:
    """Make the program's environment: with uv if it's there (with the Python the version was made
    with), else this Python's venv and pip; the pinned versions first, the newest if they fail."""
    requirements = where / "requirements.txt"
    loose = [line.split("==")[0] for line in requirements.read_text().splitlines() if line and not line.startswith("#")]
    with Lock(env.with_name(env.name + ".lock")):
        if (env / ".ready").exists() and py.exists():
            return
        if env.exists():
            shutil.rmtree(env)
        uv = shutil.which("uv")
        try:
            if uv:
                subprocess.run([uv, "venv", "--quiet", *(["--python", wanted] if wanted else []), str(env)], check=True)
                install = [uv, "pip", "install", "--quiet", "--python", str(py)]
            else:
                if sys.version_info < (3, 11):
                    raise SystemExit("the program needs Python 3.11 or newer (or uv, which can fetch one: "
                                     "https://docs.astral.sh/uv/)")
                if subprocess.run([sys.executable, "-m", "venv", str(env)]).returncode != 0:
                    raise SystemExit("couldn't make an environment; on Debian or Ubuntu, install python3-venv first")
                install = [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
            if subprocess.run([*install, "-r", str(requirements)]).returncode != 0:
                say("The exact versions it was made with couldn't be installed (if you're offline, it needs the "
                    "network once); trying the newest ones instead.")
                subprocess.run([*install, *loose], check=True)
        except (subprocess.CalledProcessError, OSError) as e:
            shutil.rmtree(env, ignore_errors=True)
            raise SystemExit(f"couldn't set up the program's environment ({e}); `--here` uses this Python as it is")
        (env / ".ready").write_text(datetime.now().isoformat() + "\n")


def consent(lines: list[str], yes: bool) -> None:
    say("\n".join(lines))
    if yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("run again with --yes (before the command) to go ahead")
    if input("Go ahead? [y/N] ").strip().lower() not in ("y", "yes"):
        raise SystemExit("nothing done")


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower().replace("'", "").replace("’", "")).strip("-") or "song"


def run(where: Path, py: str, args: list[str]) -> int:
    env = dict(os.environ, SONGBIRD_PACKET=str(PACKET))  # which file the program was started from
    env["PYTHONPATH"] = str(where / "program") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.call([py, "-m", "songbird", *args], env=env)


def main(argv: list[str]) -> int:
    # the bootstrap's own flags go before the command; everything after `songbird` is the program's
    head, tail = (argv[: argv.index("songbird")], argv[argv.index("songbird"):]) if "songbird" in argv else (argv, [])
    flags = {a for a in head if a in FLAGS}
    args = [a for a in head if a not in FLAGS] + tail
    try:
        z = zipfile.ZipFile(PACKET)
    except (zipfile.BadZipFile, OSError) as e:
        raise SystemExit(f"{PACKET} doesn't carry a program ({e})")
    with z:
        m = manifest(z)
        command = args[0] if args else "about"
        if command in ("about", "-h", "--help", "help"):
            about(z, m)
            return 0
        if command == "unpack":
            to = Path(args[1]) if len(args) > 1 else PACKET.with_name(PACKET.stem + "-unpacked")
            say(f"unpacked into {unpack(z, to)}")
            return 0
        has_studio = "program/songbird/studio.py" in z.namelist()
        if command not in ("new", "songbird") and not (command == "studio" and has_studio):
            say(usage(z))
            return 2
        recorded = text(m, "program_sha256")
        if recorded and program_hash(z) != recorded:
            raise SystemExit("the program inside this file doesn't match its own record: the file was changed "
                             "after it was made, so it won't run it (`unpack` still shows what's inside)")
        key = packet_hash()[:16]
        where = HOME / "packets" / key
        requirements = z.read("requirements.txt") if "requirements.txt" in z.namelist() else b""
        wanted = text(m, "python")
        env, py = environment(requirements, wanted)
        here = "--here" in flags
        fresh = not (where / ".complete").exists()
        fetch = not here and not ((env / ".ready").exists() and py.exists())
        if fresh or fetch:
            size = sum(i.file_size for i in z.infolist()) / 2**20
            lines = [f"This will run the program inside {PACKET.name}.",
                     f"  - It unpacks the program into {where} ({size:.1f} MB)." if fresh else None]
            if fetch:
                names = ", ".join(line.split("==")[0] for line in requirements.decode().splitlines()
                                  if line and not line.startswith("#"))
                lines.append(f"  - It fetches {names} from PyPI (about 100 MB to download, 250 MB on disk) into "
                             f"{env}" + (", with uv, which may also fetch Python " + wanted if shutil.which("uv") and
                                         wanted else "") + "; the installers keep their usual download caches.")
            if command == "new":
                lines.append("  - To sing, it reads a few plain facts about this computer (its languages, its size, its "
                             f"screen's colours), keeps them reduced to a handful of numbers in {HOME / 'voice.json'}, "
                             "and writes the new version, one FLAC file of about 15 MB, into this folder.")
            lines.append("  Nothing is installed into your system. `unpack` lets you read everything first.")
            consent([line for line in lines if line], "--yes" in flags)
        where = extracted(z, key)
    if not here:
        set_up(where, env, py, wanted)
    python = sys.executable if here else str(py)
    genome = str(where / "genome.json")
    if command == "new":
        out = Path.cwd() / f"{slug(text(m, 'title') or 'song')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.flac"
        return run(where, python, ["render", genome, "--parent", str(PACKET), "--machine", "here", "--pack",
                                   "--out", str(out), *args[1:]])
    if command == "studio":
        return run(where, python, ["studio", "--packet", str(PACKET), *args[1:]])
    return run(where, python, args[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
