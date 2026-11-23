"""This file is a song, and the program that sang it.

The file plays as music in any audio player. It is also a zip archive
holding the program that sang it (Songbird), the song's skeleton, this
version's record and its words. Run it with Python and it sings a new version
of the song on your computer:

    python3 THIS_FILE.flac              what this is; at a terminal, it then asks what you'd like to do
    python3 THIS_FILE.flac new          sing a new version here, today
    python3 THIS_FILE.flac studio       open the studio: hear it, change it, make your own
    python3 THIS_FILE.flac unpack       unpack everything into a folder, to read it first
    python3 THIS_FILE.flac songbird ... run one of the program's own commands

(On Windows, `py THIS_FILE.flac`.) It needs Python 3.11 or newer, or uv
(https://docs.astral.sh/uv/), which fetches one. Running it runs the program inside the
file. Before anything is written, it says what it will do and asks. The first
time, the program needs numpy, scipy, numba, soundfile and cmudict. It fetches
them from PyPI into a folder of its own (~/.songbird, or $SONGBIRD_HOME), and
installs nothing into your system. `--yes` answers the question in advance;
`--here` uses this Python as it is, for people who already have them. Both go
before the command.

This is the archive's __main__.py. It is standard-library only, and it runs
before anything is set up, on whatever Python it is given: it is written to
parse and run on Python 3.7 and every later one, so that an old Python can say
what's wrong, and a new one finds nothing here it has stopped understanding
(so no `from __future__ import annotations`, which is to be withdrawn: the
annotations an old Python couldn't evaluate are written as strings).
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKET = Path(os.path.abspath(sys.argv[0]))
HOME = Path(os.environ.get("SONGBIRD_HOME") or Path.home() / ".songbird")
MOST = 100 * 2**20  # the most an archive may unpack to: the program is a few MB
FLAGS = ("--yes", "--here")


def say(text: str = "") -> None:
    print(text, flush=True)


def elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} min {s} s" if m else f"{s} s"


class Ticking:
    """A line now and then while something slow runs (fetching the dependencies), so a quiet terminal isn't
    taken for a stuck one."""

    def __init__(self, what: str, every: float = 15.0):
        self.what, self.every = what, every
        self.done = threading.Event()

    def __enter__(self):
        start = time.time()

        def tick():
            while not self.done.wait(self.every):
                say(f"  ... still {self.what} ({elapsed(time.time() - start)})")

        threading.Thread(target=tick, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.done.set()


WAITING_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light dark">
<title>Getting the studio ready</title><style>
body { font: 18px/1.55 "Iowan Old Style", Palatino, Georgia, serif; background: #f6f1e6; color: #2a2118;
  max-width: 34em; margin: 14vh auto; padding: 0 20px; }
@media (prefers-color-scheme: dark) { body { background: #17130e; color: #ece3d0; } }
h1 { font-weight: 500; font-size: 30px; margin: 0 0 14px; } #now { font-weight: 600; } .hint { opacity: .75; font-size: 16px; }
</style></head><body><h1>Getting the studio ready</h1>
<p>This happens only the first time. <span id="now">Starting...</span> <span id="time"></span></p>
<p class="hint">The terminal you started it from says the same, and asks if anything needs you.
This page turns into the studio by itself when it's ready.</p>
<script>
const now = document.getElementById("now"), time = document.getElementById("time");
async function poll() {
  let s;
  try { s = await (await fetch("/status", { cache: "no-store" })).json(); }
  catch (e) { return studio(); }  // gone: the studio is taking its place
  now.textContent = s.stage; time.textContent = s.seconds > 5 ? "(" + s.seconds + " s so far)" : "";
  if (s.failed) return;
  if (s.done) { now.textContent = "Opening the studio..."; return setTimeout(studio, 1500); }
  setTimeout(poll, 1000);
}
async function studio() {  // this address answers as the studio once it has started: then become it
  try { if ((await fetch("/api/start", { cache: "no-store" })).ok) return location.reload(); } catch (e) {}
  setTimeout(studio, 1000);
}
poll();
</script></body></html>
"""


class WaitingPage:
    """For `studio` the first time: a page in the browser, at the address the studio will have, that says
    what the setup is doing, and turns into the studio when it starts (this server steps aside for it)."""

    def __init__(self, port: int = 8766, browser: bool = True):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.stage, self.start, self.done, self.failed = "Starting...", time.time(), False, False
        page = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path == "/status":
                    body = json.dumps({"stage": page.stage, "seconds": int(time.time() - page.start),
                                       "done": page.done, "failed": page.failed}).encode()
                    kind = "application/json"
                elif self.path in ("/", "/index.html"):
                    body, kind = WAITING_PAGE.encode(), "text/html; charset=utf-8"
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        self.server = None
        for p in range(port, port + 20):
            try:
                self.server = ThreadingHTTPServer(("127.0.0.1", p), Handler)
                break
            except OSError:
                continue
        if self.server is None:
            return
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        if browser:
            import webbrowser

            webbrowser.open(f"http://127.0.0.1:{self.port}/")

    def say(self, text: str) -> None:
        self.stage = text
        say(text)

    def fail(self, text: str) -> None:
        self.stage, self.failed = text, True

    def step_aside(self) -> "int | None":
        """Done: the page will reload into the studio, which takes this port."""
        if self.server is None:
            return None
        self.done = True
        time.sleep(1.2)  # the page's next look sees it's done
        self.server.shutdown()
        self.server.server_close()
        return self.port


def python_problem(here: bool, version: tuple = sys.version_info[:2]) -> "str | None":
    """Why this computer can't set the program up as it is, said before anything is asked or written."""
    if here or shutil.which("uv"):
        return None
    if tuple(version) < (3, 11):
        v = f"{version[0]}.{version[1]}"
        return (f"The program in this file needs Python 3.11 or newer, and this is Python {v}. Nothing has been "
                "written. Either of these fixes it:\n"
                "  - Install a newer Python from https://www.python.org/downloads/ and run this again with it "
                f"(`{run_as()} {PACKET.name} ...`).\n"
                "  - Or install uv (https://docs.astral.sh/uv/), which fetches the right Python by itself, and "
                "run the same command again.")
    if importlib.util.find_spec("venv") is None or importlib.util.find_spec("ensurepip") is None:
        return ("This Python can't make a separate environment for the program (it lacks venv or ensurepip). "
                "Nothing has been written. On Debian or Ubuntu, `sudo apt install python3-venv` fixes it; "
                "or install uv (https://docs.astral.sh/uv/) and run the same command again.")
    return None


def run_as() -> str:
    return "py" if os.name == "nt" else "python3"


def usage(z: zipfile.ZipFile) -> str:
    name = PACKET.name
    studio = "program/songbird/studio.py" in z.namelist()
    lines = [f"usage: {run_as()} {name} [--yes] [--here] [new | {'studio | ' if studio else ''}unpack [DIR] | about | "
             "songbird COMMAND ...]", "",
             "  new             sing a new version of the song here, today, shaped by this computer and the day"]
    if studio:
        lines.append("  studio          open the studio: explore the choices, change them, then make your own version")
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


def text(m: dict, key: str, n: "int | None" = None) -> str:
    value = m.get(key)
    value = value if isinstance(value, str) else ""
    return value[:n] if n else value


def program_hash(z: zipfile.ZipFile) -> str:
    """The program's hash, computed from the archive as songbird.pack computes it when packing."""
    h = hashlib.sha256()
    for name in sorted(n for n in z.namelist() if n.startswith("program/") and not n.endswith("/")):
        h.update(name.encode() + b"\0" + hashlib.sha256(z.read(name)).digest())
    return h.hexdigest()


def sung_on(stamp: str) -> str:
    """The day a version was sung, where it is read (as songbird.dates.local_day: a day kept as noon UTC is that
    day; any other moment, the local day it was then)."""
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return stamp[:10]
    if moment.tzinfo is None:
        return stamp[:10]
    utc = moment.astimezone(timezone.utc)
    if (utc.hour, utc.minute, utc.second, utc.microsecond) == (12, 0, 0, 0):
        return utc.date().isoformat()
    return moment.astimezone().date().isoformat()


def about(z: zipfile.ZipFile, m: dict) -> None:
    generation = m.get("generation") if isinstance(m.get("generation"), int) else 0
    say(text(m, "name", 80) or text(m, "title") or "A song")  # its own title, if it was given one
    if generation == 0:
        say("the seed: a version with none before it")
    else:
        say(f"generation {generation}: {generation} version{'s' if generation != 1 else ''} before this one")
    if text(m, "rendered_at"):
        say(f"sung {sung_on(text(m, 'rendered_at'))}")
    say(f"id {text(m, 'id', 12) or '?'}; program {text(m, 'program_version') or '?'}, "
        f"{text(m, 'program_sha256', 16) or '?'}")
    say()
    say("This file plays as music. It is also the program that sang it: run it to sing a new version of")
    say("the song on your computer, shaped by a few plain facts about it and by the day. Running it runs")
    say("the program inside; `unpack` lets you read it all first (README.txt says what it reads and keeps).")
    say()
    say(usage(z))
    problem = python_problem(False)
    if problem:  # said now, so nobody finds out after typing a command
        say()
        say(problem.replace(" Nothing has been written.", ""))


def choose(has_studio: bool) -> "str | None":
    """The file run with no command, by a person at a terminal: after saying what it is, it asks what they'd like
    to do, so one line is all anyone has to type. "new" or "studio", or None (nothing chosen; not a terminal, as
    when a script runs it; or this computer can't run the program yet, which `about` has just said)."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()) or python_problem(False):
        return None
    say()
    say("What would you like to do?")
    say("  n   sing a new version of the song here, today")
    if has_studio:
        say("  s   open the studio: hear it, change it, make your own version")
    say("  (or press Enter to do nothing)")
    try:
        answer = input("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        say()
        return None
    if answer in ("n", "new"):
        return "new"
    if has_studio and answer in ("s", "studio"):
        return "studio"
    return None


def safe_members(z: zipfile.ZipFile, to: Path) -> "list[zipfile.ZipInfo]":
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
            (tmp / ".complete").write_text(datetime.now().isoformat() + "\n", encoding="utf-8")
            if where.exists():
                shutil.rmtree(where)
            os.replace(tmp, where)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
    return where


def needs(requirements: str) -> "list[str]":
    """What a requirements.txt asks for, a line each (`numpy==2.5.3`), without its comments and blank lines."""
    return [line.strip() for line in requirements.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def environment(requirements: bytes, wanted: str) -> "tuple[Path, Path]":
    """Where the program's libraries go, and the Python there: one folder for every file that asks for the same
    versions with the same Python, whatever its requirements.txt says in its comment (which program wrote it)."""
    asked = "\n".join(needs(requirements.decode("utf-8", "replace")))
    key = hashlib.sha256((asked + "\n" + wanted).encode()).hexdigest()[:16]
    env = HOME / "envs" / key
    return env, env / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


THIS_PYTHON = "%d.%d" % sys.version_info[:2]


def made(env: Path) -> dict:
    """How an environment was made, from its .ready: {"with": "uv" or "pip", "versions": "pinned" or "newest",
    "python": "3.12"}. Empty for one that isn't ready; {"with": "?"} for one an earlier bootstrap made (its .ready
    is only a date), which is taken as it is."""
    try:
        lines = (env / ".ready").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    return dict(line.split("=", 1) for line in lines if "=" in line) or {"with": "?"}


def ready(env: Path, py: Path) -> bool:
    """Whether the environment can be used as it is. Not if it was never finished; not if pip made it from a Python
    that has since been replaced by another (a system upgrade leaves its libraries where the new one doesn't look);
    and not if it holds the newest versions for want of the pinned ones and uv is here now, which can fetch the
    Python those were made for: then it is made again."""
    how = made(env)
    if not how or not py.exists():
        return False
    if how.get("with") == "pip" and how.get("python") != THIS_PYTHON:
        return False
    if how.get("with") == "pip" and how.get("versions") == "newest" and shutil.which("uv"):
        return False
    return True


READY_MADE = ["--only-binary", ":all:"]  # wheels only, for pip and uv alike: nothing is compiled


def set_up(where: Path, env: Path, py: Path, wanted: str, tell=say) -> None:
    """Make the program's environment: with uv if it's there (with the Python the version was made with, or failing
    that the one uv has), else, or if uv can't, this Python's venv and pip. Ready-made builds (wheels) only, so
    nothing is compiled: the pinned versions first, else the newest versions made for this computer. (Intel Macs
    are why: numba's builds for them stop at 0.62.1, and asking for the newest without this picked a later numba,
    to compile, which fails.) How it was made is written into its .ready (made())."""
    requirements = where / "requirements.txt"
    loose = [line.split("==")[0] for line in needs(requirements.read_text(encoding="utf-8"))]
    uv = shutil.which("uv")

    def venv_with_uv() -> "list[str] | None":
        for python in ([["--python", wanted]] if wanted else []) + [[]]:  # the Python it was made with, else uv's own
            if subprocess.run([uv, "venv", "--quiet", *python, str(env)]).returncode == 0:
                return [uv, "pip", "install", "--quiet", "--python", str(py)]
            shutil.rmtree(env, ignore_errors=True)
        return None

    def venv_with_pip() -> "list[str]":
        if sys.version_info < (3, 11):
            raise SystemExit(python_problem(False) or "The program in this file needs Python 3.11 or newer.")
        if subprocess.run([sys.executable, "-m", "venv", str(env)]).returncode != 0:
            raise SystemExit("couldn't make an environment; on Debian or Ubuntu, `sudo apt install python3-venv` first")
        return [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]

    with Lock(env.with_name(env.name + ".lock")):
        if ready(env, py):
            return
        if env.exists():
            shutil.rmtree(env)
        tell(f"Fetching what the program needs ({', '.join(loose)}): about 100 MB, the first time only. "
             "A few minutes on a slow connection.")
        try:
            with Ticking("fetching what the program needs"):
                install = venv_with_uv() if uv else None
                by = "uv" if install else "pip"
                if install is None:
                    if uv:
                        tell("uv couldn't make an environment; trying with this Python instead.")
                    install = venv_with_pip()
                versions = "pinned"
                if subprocess.run([*install, *READY_MADE, "-r", str(requirements)]).returncode != 0:
                    tell("The exact versions it was made with couldn't be installed here (if you're offline, it needs "
                         "the network once); trying the newest ones made for this computer instead. What it sings "
                         "with them may differ, and if they have moved on too far it may not run: then install uv "
                         "(https://docs.astral.sh/uv/), which fetches the Python it was made with, and run it again.")
                    versions = "newest"
                    subprocess.run([*install, *READY_MADE, *loose], check=True)
        except (subprocess.CalledProcessError, OSError) as e:
            shutil.rmtree(env, ignore_errors=True)
            other = "" if uv or not wanted or wanted == THIS_PYTHON else (
                f" If it's online, they may not be made for Python {THIS_PYTHON} on this computer: with uv "
                f"(https://docs.astral.sh/uv/) installed, it uses Python {wanted}, the one this version was made with.")
            why = "the installer stopped" if isinstance(e, subprocess.CalledProcessError) else str(e)
            raise SystemExit(f"couldn't fetch what the program needs ({why}; its own words are above). If this "
                             f"computer is offline, connect it and run the same command again.{other} `--here` uses "
                             "this Python as it is, for people who already have numpy, scipy, numba, soundfile and "
                             "cmudict.")
        (env / ".ready").write_text(f"made={datetime.now().isoformat()}\nwith={by}\nversions={versions}\n"
                                    f"python={wanted if by == 'uv' and wanted else THIS_PYTHON}\n", encoding="utf-8")


def consent(lines: "list[str]", yes: bool) -> None:
    say("\n".join(lines))
    if yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit("run again with --yes (before the command) to go ahead")
    try:
        answer = input("Go ahead? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        answer = ""
        say()
    if answer.strip().lower() not in ("y", "yes"):
        raise SystemExit("nothing done")


def slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower().replace("'", "").replace("’", "")).strip("-") or "song"


def run(where: Path, py: str, args: "list[str]") -> int:
    env = dict(os.environ, SONGBIRD_PACKET=str(PACKET))  # which file the program was started from
    # only the file's own program, never a songbird/ (or a random.py) that happens to be in the folder it is run
    # from: Python 3.11 and later leave the current folder off the path when told to
    env["PYTHONSAFEPATH"] = "1"
    env["PYTHONPATH"] = str(where / "program") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.call([py, "-m", "songbird", *args], env=env)


def main(argv: "list[str]") -> int:
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
        has_studio = "program/songbird/studio.py" in z.namelist()
        command = args[0] if args else "about"
        if command in ("about", "-h", "--help", "help"):
            about(z, m)
            command = choose(has_studio) if not args else None  # the file run by itself, at a terminal: it asks
            if command is None:
                return 0
            args = [command]
        if command == "unpack":
            to = Path(args[1]) if len(args) > 1 else PACKET.with_name(PACKET.stem + "-unpacked")
            say(f"unpacked into {unpack(z, to)}")
            return 0
        if command not in ("new", "songbird") and not (command == "studio" and has_studio):
            say(f"{PACKET.name} has no command {command!r}.")
            say()
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
        fetch = not here and not ready(env, py)
        if fetch:  # said before anything is asked or written: what this computer lacks, and how to get it
            problem = python_problem(here)
            if problem:
                raise SystemExit(problem)
        if fresh or fetch:
            size = sum(i.file_size for i in z.infolist()) / 2**20
            lines = [f"This will run the program inside {PACKET.name}.",
                     f"  - It unpacks the program into {where} ({size:.1f} MB)." if fresh else None]
            if fetch:
                names = ", ".join(line.split("==")[0] for line in needs(requirements.decode("utf-8", "replace")))
                lines.append(f"  - It fetches {names} from PyPI (about 100 MB to download, 250 MB on disk) into "
                             f"{env}" + (", with uv, which may also fetch Python " + wanted if shutil.which("uv") and
                                         wanted else "") + "; the installers keep their usual download caches.")
            if command == "new":
                lines.append("  - To sing, it reads a few plain facts about this computer (its languages, its size, its "
                             f"screen's colours), keeps them reduced to a handful of numbers in {HOME / 'voice.json'}, "
                             "and writes the new version, one FLAC file of about 15 MB, into this folder.")
            if command == "studio":
                lines.append("  - The studio reads the same few plain facts about this computer (its languages, its "
                             f"size, its screen's colours), keeps them reduced to a handful of numbers in "
                             f"{HOME / 'voice.json'}, and opens a page in your browser that only this computer can "
                             "reach. What you record there is written into this folder.")
            lines.append("  Nothing is installed into your system. `unpack` lets you read everything first.")
            consent([line for line in lines if line], "--yes" in flags)
        # the studio's first time: a page in the browser says what it's waiting for, then becomes the studio
        page = WaitingPage() if command == "studio" and fetch and not args[1:] else None
        tell = page.say if page and page.server else say
        if fresh:
            tell("Unpacking the program...")
        where = extracted(z, key)
    extra = []
    try:
        if not here:
            set_up(where, env, py, wanted, tell)
    except SystemExit as e:
        if page and page.server:
            page.fail(f"It stopped: {e}")
            time.sleep(2)  # the page's next look shows why
        raise
    if page and page.server:
        page.say("Starting the studio...")
        port = page.step_aside()
        extra = ["--port", str(port), "--no-open"]
    elif fetch or fresh:
        say("Ready." + (" Starting the studio; your browser opens by itself." if command == "studio" else ""))
    python = sys.executable if here else str(py)
    genome = str(where / "genome.json")
    if command == "new":
        out = Path.cwd() / f"{slug(text(m, 'name', 80) or text(m, 'title') or 'song')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.flac"
        return run(where, python, ["render", genome, "--parent", str(PACKET), "--machine", "here", "--pack",
                                   "--out", str(out), *args[1:]])
    if command == "studio":
        return run(where, python, ["studio", "--packet", str(PACKET), *extra, *args[1:]])
    return run(where, python, args[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
