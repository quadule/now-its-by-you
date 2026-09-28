# Running the song (2026-09-27)

The artist: "What are the full system requirements to run the studio from the
song? How can we make that setup process easier for less experienced users?"

A rendition of the song is one FLAC file. It plays in any audio player, and it
is also a program (docs/PACKET.md): `python3 song.flac studio` opens the
studio on it. This page says what that needs, as it is in
songbird/bootstrap.py (the file's `__main__.py`) and pyproject.toml, and what
a person meets doing it for the first time.

## In short

- **Python 3.11 or newer**, or **uv** (which fetches the right Python by itself).
- **The network once**: about 100 MB fetched from PyPI into `~/.songbird`, about 250 MB on disk.
- **A web browser** from 2023 or later, on the same computer.
- **Memory**: a whole song peaked at about 5.6 GB while it was made (measured on an M1 Max); 8 GB computers will manage, slowly.
- **Time**: a few minutes the first time; then a sung section in about 6 s and the whole song in about 40 s.

## What it needs

| | What | Why, and where it comes from |
|---|---|---|
| Python | 3.11 or newer (`python3`; `py` on Windows) | pyproject.toml's `requires-python`. The bootstrap itself runs on 3.7 and up, so it can say what's wrong; older ones (and Python 2) stop with a SyntaxError before it can. With **uv** on the path, the Python version doesn't matter: uv fetches the one the rendition was made with (3.12 for today's). |
| The program's libraries | numpy, scipy, numba (with llvmlite), soundfile (with cffi, and libsndfile inside its wheel), cmudict | The file's `requirements.txt`, pinned to the versions it was made with (numpy 2.5.3, scipy 1.18.1, numba 0.67.0, soundfile 0.14.0, cmudict 1.1.3). If the pins can't be installed (a newer Python they have no wheels for), it tries the newest versions. |
| Download | about 100 MB, once | From PyPI, by uv or by pip. The installers keep their usual caches. |
| Disk | about 250 MB for the libraries; about 6 MB for each rendition's unpacked program; up to 300 MB of studio previews; about 15 to 22 MB for each recording | `~/.songbird/envs/` (one environment, shared by every rendition with the same pins), `~/.songbird/packets/<the file's hash>/`, `~/.songbird/studio/cache/` (the least recently heard go first), and the folder you ran it from. `$SONGBIRD_HOME` moves everything but the recordings. |
| Memory | about 5.6 GB at the peak of a whole song | Measured with `/usr/bin/time -l` rendering Now It's by You on an M1 Max (38.8 s). Sections need less. On 8 GB the computer will swap and it will be slower; below that it may not finish. |
| Processor | a 64-bit Mac (Apple silicon or Intel), Windows PC (x64) or Linux (x86-64 or ARM64, glibc) | Where numba and llvmlite publish wheels. Not 32-bit systems, Windows on ARM, or Alpine-style Linux, where pip would try to compile llvmlite and fail. |
| Browser | Safari 16.4, Chrome or Edge 111, Firefox 113, or newer | The page uses `color-mix()`, `<dialog>` and modern JavaScript; no plugins. It must run on the same computer (the studio answers only 127.0.0.1) unless it is shared on purpose (docs/STUDIO.md). |

## What it doesn't need

No account, no password, no administrator rights, no installing anything into
the system; no GPU; no compiler, ffmpeg, Node or Homebrew; no models or
weights to download (the learned voice travels in the file); no microphone
(the singing page is the checkout's, not the file's); no network after the
first time. Nothing is sent anywhere.

## How long it takes

| | About | Notes |
|---|---|---|
| Reading `python3 song.flac` | instant | writes nothing |
| Unpacking the program | a second | the first time for each file |
| Fetching the libraries | 20 s from uv's cache; 1 to 5 minutes on a home connection | the first time on a computer |
| The first sound | 10 to 15 s more | numba compiles the synthesis the first time it runs; the studio starts this as it opens, on today's first verse |
| A section, then | about 6 s | a preview, made when asked |
| The whole song, or a recording | about 40 s | 38.8 s measured on an M1 Max; a slower or busier computer takes longer |
| A new version from the file, cold | 38 to 51 s | docs/PACKET.md, including setting up from uv's cache |

## The first time, as a less experienced person meets it

1. **Getting a terminal.** The file plays when double-clicked; running it
   takes a terminal. On a Mac: Terminal (in Applications, Utilities). On
   Windows: right-click the folder holding the file, *Open in Terminal*.
   On Linux: any terminal. Typing `python3 ` and then dragging the file onto
   the window fills in its path.
2. **Having a Python.** `python3 --version` says which.
   - *macOS* comes with none that's new enough: `python3` either offers to
     install Apple's developer tools (whose Python is 3.9) or is 3.9. Install
     Python from https://www.python.org/downloads/ (the macOS installer), then
     open a new Terminal window.
   - *Windows*: install Python from python.org (tick *Add python.exe to
     PATH*) or the Microsoft Store, then use `py` instead of `python3`.
   - *Linux*: most have Python; Ubuntu 22.04's is 3.10, too old. Debian and
     Ubuntu also need `sudo apt install python3-venv`.
   - *Anywhere*: installing uv (https://docs.astral.sh/uv/) instead makes the
     Python version stop mattering.
3. **`python3 song.flac`** says what the file is and what it can do, and, if
   this Python is too old to run it, says so and how to get one.
4. **`python3 song.flac studio`** checks this computer first. If its Python
   is too old or can't make an environment, it says so, and how to fix it,
   before asking or writing anything. Otherwise it lists what it will do
   (unpack, fetch, read a few facts about this computer, open a page) and asks
   `Go ahead? [y/N]`.
5. **After `y`**, the browser opens on a page titled *Getting the studio
   ready*, which says what it is doing (unpacking, fetching, starting) and for
   how long; the terminal says the same, with a line every 15 seconds while
   the libraries download. The page turns into the studio by itself.
6. **The studio** opens on a short walk of four steps (hear it, change
   something, go deeper, record it), and has Help at the top.
7. **Next time**, `python3 song.flac studio` opens the studio in a few
   seconds without asking.

## When something goes wrong

| It says | What it means | What to do |
|---|---|---|
| `SyntaxError`, or `future feature annotations is not defined` | a very old Python (2.x, or 3.6 and older) | install a current one (step 2) |
| `needs Python 3.11 or newer, and this is Python 3.9` | too old for the program | install a newer Python, or uv |
| `can't make a separate environment for the program` | Debian or Ubuntu without python3-venv | `sudo apt install python3-venv`, or uv |
| `couldn't fetch what the program needs` | offline, or a firewall or proxy in the way | connect, and run the same command again |
| `run again with --yes` | it wasn't run from a terminal it could ask in | `python3 song.flac --yes studio` |
| `doesn't match its own record` | the file was changed after it was made | get another copy; `unpack` still shows what's inside |
| pip tries to *build* llvmlite and fails | a platform without wheels (see Processor) | use another computer |
| the browser doesn't open | no default browser, or a remote session | open the address the terminal prints (`http://127.0.0.1:8766`) |
| the computer grinds on the whole song | too little memory | close other programs; sections still work |

## What changed to make it easier (this pass)

- The bootstrap checks for a new enough Python (and for venv, on Debian and
  Ubuntu) **before** asking or writing anything, and says in plain words how
  to get one, uv included.
- Consenting to `studio` now says what the studio reads and writes, as `new`
  already did.
- The first `studio` opens a **waiting page** in the browser (standard
  library only, on the address the studio will have) that says what is
  happening and becomes the studio when it starts; the terminal reports
  every 15 seconds while the libraries download instead of sitting silent.
- The file's README.txt and `about` mention `studio` and the Python it needs;
  `about` warns at once when this Python can't run it.
- tests/test_pack.py checks that the bootstrap imports only the standard
  library, that the Python check speaks before anything is written, and that
  the waiting page answers, reports and steps aside.

## Left for the artist

- **The memory.** 5.6 GB at the peak of a whole song is the heaviest
  requirement, and the least expected. Worth measuring where it goes (the
  whole rendition held at once, per part, before mixing, is the likely
  place); not touched here, since it lives in the synthesis.
- **Fetching uv for the person.** The bootstrap could offer to install uv
  when Python is too old, which would make step 2 disappear; but that runs an
  installer script from the internet, a bigger thing to ask than fetching
  libraries. Only with the artist's yes.
- **Carrying the libraries.** A file with wheels inside would need no
  network, but would be about 100 MB larger and tied to one platform
  (docs/PACKET.md already weighed this and said no).
- **A double-click launcher.** A `.command` (macOS) or `.bat` (Windows)
  beside the file would spare the terminal, but it can't travel inside the
  FLAC, and a downloaded script is itself something to trust. The
  songbird.quadule.com page could offer one per platform.
- **Not tried here:** Windows and Linux. The bootstrap and the harvest have
  code for both; nobody has run a rendition's studio on them yet.
