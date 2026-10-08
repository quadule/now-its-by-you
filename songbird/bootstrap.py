"""This file is a song, and the program that sang it.

The file plays as music in any audio player. It is also a zip archive
holding the program that sang it (Songbird), the song's skeleton, this
version's record and its words. Run it with Python and it sings a new version
of the song on your computer:

    python3 THIS_FILE.flac              what this is, and what you can do
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
before anything is set up.
"""

from __future__ import annotations

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
from datetime import datetime
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

    def step_aside(self) -> int | None:
        """Done: the page will reload into the studio, which takes this port."""
        if self.server is None:
            return None
        self.done = True
        time.sleep(1.2)  # the page's next look sees it's done
        self.server.shutdown()
        self.server.server_close()
        return self.port


def python_problem(here: bool, version: tuple = sys.version_info[:2]) -> str | None:
    """Why this computer can't set the program up as it is, said before anything is asked or written."""
    if here or shutil.which("uv"):
        return None
    if tuple(version) < (3, 11):
        v = f"{version[0]}.{version[1]}"
        return (f"The program in this file needs Python 3.11 or newer, and this is Python {v}. Nothing has been "
                "written. Either of these fixes it:\n"
                "  - Install a newer Python from https://www.python.org/downloads/ and run this again with it "
                f"(for example `python3.12 {PACKET.name} ...`{'; on Windows, `py -3.12`' if os.name == 'nt' else ''}).\n"
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
    problem = python_problem(False)
    if problem:  # said now, so nobody finds out after typing a command
        say()
        say(problem.replace(" Nothing has been written.", ""))


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


def set_up(where: Path, env: Path, py: Path, wanted: str, tell=say) -> None:
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
        tell(f"Fetching what the program needs ({', '.join(loose)}): about 100 MB, the first time only. "
             "A few minutes on a slow connection.")
        try:
            with Ticking("fetching what the program needs"):
                if uv:
                    subprocess.run([uv, "venv", "--quiet", *(["--python", wanted] if wanted else []), str(env)],
                                   check=True)
                    install = [uv, "pip", "install", "--quiet", "--python", str(py)]
                else:
                    if sys.version_info < (3, 11):
                        raise SystemExit(python_problem(False))
                    if subprocess.run([sys.executable, "-m", "venv", str(env)]).returncode != 0:
                        raise SystemExit("couldn't make an environment; on Debian or Ubuntu, "
                                         "`sudo apt install python3-venv` first")
                    install = [str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
                if subprocess.run([*install, "-r", str(requirements)]).returncode != 0:
                    tell("The exact versions it was made with couldn't be installed (if you're offline, it needs the "
                         "network once); trying the newest ones instead.")
                    subprocess.run([*install, *loose], check=True)
        except (subprocess.CalledProcessError, OSError) as e:
            shutil.rmtree(env, ignore_errors=True)
            raise SystemExit(f"couldn't fetch what the program needs ({e}). If this computer is offline, connect it "
                             "and run the same command again; `--here` uses this Python as it is, for people who "
                             "already have numpy, scipy, numba, soundfile and cmudict.")
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
        if fetch:  # said before anything is asked or written: what this computer lacks, and how to get it
            problem = python_problem(here)
            if problem:
                raise SystemExit(problem)
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
        out = Path.cwd() / f"{slug(text(m, 'title') or 'song')}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.flac"
        return run(where, python, ["render", genome, "--parent", str(PACKET), "--machine", "here", "--pack",
                                   "--out", str(out), *args[1:]])
    if command == "studio":
        return run(where, python, ["studio", "--packet", str(PACKET), *extra, *args[1:]])
    return run(where, python, args[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
