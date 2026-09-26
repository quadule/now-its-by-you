"""This file is a song, and the program that sang it.

The file plays as music in any audio player. It is also a zip archive
holding the program that sang it (Songbird), the song's skeleton, this
version's record and its words. Run it with Python and it sings a new version
of the song on your computer:

    python3 THIS_FILE.flac              what this is, and what you can do
    python3 THIS_FILE.flac new          sing a new version here, today
    python3 THIS_FILE.flac studio       open the studio: explore, change and record a version
    python3 THIS_FILE.flac unpack       unpack everything into a folder beside this file
    python3 THIS_FILE.flac songbird ... run any of the program's own commands

The first time the program runs it needs numpy, scipy, numba, soundfile and
cmudict. It asks before fetching them (from PyPI, about 150 MB) into a folder
of its own (~/.songbird, or $SONGBIRD_HOME), and nothing is installed
anywhere else. `--yes` skips the question; `--here` uses this Python as it is,
for people who already have them.

This is the archive's __main__.py: it is standard-library only, and it runs
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
import zipfile
from datetime import datetime
from pathlib import Path

PACKET = Path(os.path.abspath(sys.argv[0]))
HOME = Path(os.environ.get("SONGBIRD_HOME") or Path.home() / ".songbird")
USAGE = """\
usage: python3 {name} [new | studio | unpack [DIR] | about | songbird COMMAND ...] [--yes] [--here]

  new             sing a new version of the song here, today, shaped by this computer and the day
  studio          open the studio: explore the choices, change them, record, then sing it
  unpack [DIR]    unpack the program, the song and this version's record into DIR
  about           what this file is (the default)
  songbird ...    run one of the program's own commands, e.g. `songbird render --help`
"""


def say(text: str = "") -> None:
    print(text, flush=True)


def manifest(z: zipfile.ZipFile) -> dict:
    return json.loads(z.read("manifest.json"))


def about(m: dict) -> None:
    ancestry = m.get("ancestry") or []
    generation = m.get("generation", 0)
    say(f"{m.get('title', 'A song')}")
    if generation == 0:
        say("the seed: the first version, sung by the program that made it")
    else:
        say(f"generation {generation}: {len(ancestry)} version{'s' if len(ancestry) != 1 else ''} before this one")
    if m.get("rendered_at"):
        say(f"sung {m['rendered_at'][:10]}")
    say(f"id {m.get('id', '?')[:12]}")
    say()
    say("This file plays as music. It is also the program that sang it: run it to sing a new version")
    say("of the song on your computer, shaped by a few plain facts about it and by the day. See README.txt")
    say("inside (`unpack`) for exactly what it reads and what it keeps.")
    say()
    say(USAGE.format(name=PACKET.name))


def unpack(z: zipfile.ZipFile, to: Path) -> Path:
    to.mkdir(parents=True, exist_ok=True)
    for info in z.infolist():
        target = (to / info.filename).resolve()
        if not str(target).startswith(str(to.resolve())):
            raise SystemExit(f"refusing to unpack {info.filename!r} outside {to}")
        z.extract(info, to)
    return to


def extracted(z: zipfile.ZipFile, m: dict) -> Path:
    """The packet unpacked into the program's own folder, once per version."""
    where = HOME / "packets" / str(m.get("id", "unknown"))[:16]
    if not (where / ".complete").exists():
        if where.exists():
            shutil.rmtree(where)
        unpack(z, where)
        (where / ".complete").write_text(datetime.now().isoformat() + "\n")
    return where


def python_for(where: Path, m: dict, yes: bool, here: bool) -> str:
    """A Python with the program's dependencies: this one (--here), or an environment of the program's own."""
    if here:
        return sys.executable
    requirements = (where / "requirements.txt").read_bytes()
    wanted = str(m.get("python") or "")
    key = hashlib.sha256(requirements + wanted.encode()).hexdigest()[:16]
    env = HOME / "envs" / key
    py = env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if (env / ".ready").exists() and py.exists():
        return str(py)
    names = ", ".join(line.split("==")[0] for line in requirements.decode().splitlines() if line and not line.startswith("#"))
    say(f"The program needs {names}.")
    say(f"It can fetch them from PyPI (about 150 MB) into {env}; nothing is installed anywhere else.")
    if not yes:
        if not sys.stdin.isatty():
            raise SystemExit("run again with --yes to allow that, or --here to use this Python as it is")
        if input("Fetch them now? [y/N] ").strip().lower() not in ("y", "yes"):
            raise SystemExit("nothing fetched; `--here` uses this Python as it is")
    if env.exists():
        shutil.rmtree(env)
    uv = shutil.which("uv")
    loose = [line.split("==")[0] for line in requirements.decode().splitlines() if line and not line.startswith("#")]
    try:
        if uv:
            subprocess.run([uv, "venv", "--quiet", *(["--python", wanted] if wanted else []), str(env)], check=True)
            install = [uv, "pip", "install", "--quiet", "--python", str(py)]
        else:
            if sys.version_info < (3, 11):
                raise SystemExit("the program needs Python 3.11 or newer (or uv: https://docs.astral.sh/uv/)")
            subprocess.run([sys.executable, "-m", "venv", str(env)], check=True)
            install = [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
        if subprocess.run([*install, "-r", str(where / "requirements.txt")]).returncode != 0:
            say("The exact versions it was made with aren't available here; trying the newest ones instead.")
            subprocess.run([*install, *loose], check=True)
    except (subprocess.CalledProcessError, OSError) as e:
        raise SystemExit(f"couldn't set up the program's environment ({e}); `--here` uses this Python as it is")
    (env / ".ready").write_text(datetime.now().isoformat() + "\n")
    return str(py)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "").replace("\u2019", "")).strip("-") or "song"


def run(where: Path, m: dict, py: str, args: list[str]) -> int:
    env = dict(os.environ, SONGBIRD_PACKET=str(PACKET))
    env["PYTHONPATH"] = str(where / "program") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.call([py, "-m", "songbird", *args], env=env)


def main(argv: list[str]) -> int:
    flags = {a for a in argv if a in ("--yes", "--here")}
    args = [a for a in argv if a not in flags]
    try:
        z = zipfile.ZipFile(PACKET)
    except (zipfile.BadZipFile, OSError) as e:
        raise SystemExit(f"{PACKET} doesn't carry a program ({e})")
    with z:
        m = manifest(z)
        command = args[0] if args else "about"
        if command in ("about", "-h", "--help", "help"):
            about(m)
            return 0
        if command == "unpack":
            to = Path(args[1]) if len(args) > 1 else PACKET.with_name(PACKET.stem + "-unpacked")
            say(f"unpacked into {unpack(z, to)}")
            return 0
        if command not in ("new", "studio", "songbird"):
            say(USAGE.format(name=PACKET.name))
            return 2
        if sys.version_info < (3, 8):
            raise SystemExit("Python 3.8 or newer is needed even to set up")
        where = extracted(z, m)
    py = python_for(where, m, yes="--yes" in flags, here="--here" in flags)
    genome = str(where / "genome.json")
    if command == "new":
        out = Path.cwd() / f"{slug(m.get('title', 'song'))}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.flac"
        return run(where, m, py, ["render", genome, "--parent", str(PACKET), "--machine", "here", "--pack",
                                  "--out", str(out), *args[1:]])
    if command == "studio":
        return run(where, m, py, ["studio", "--packet", str(PACKET), *args[1:]])
    return run(where, m, py, args[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
