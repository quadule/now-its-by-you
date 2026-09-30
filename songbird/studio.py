"""The studio: see how your version of the song was made, change it if you like, and record it.

    songbird studio [PARENT.flac|record.json] [--song GENOME] [--machine here] [--port 8766] [--out DIR]
                    [--host 0.0.0.0] [--allow-host NAME] [--key WORD]
                    [--public [--limit NAME=N] [--client-ip-header CF-Connecting-IP]]

A page on this computer only (127.0.0.1), served by the standard library,
with plain HTML, CSS and JavaScript from songbird/studio/ and nothing from
anywhere else, so it runs from a seed packet's own program with no network:
started there with no arguments, it opens the rendition the packet came from
(its genome.json and manifest.json beside the program). It opens on your
song today: the version this machine would sing now, from that parent (or
from the song as it began). It shows every choice and why (songbird.explain),
lets you move through time, roll chance again, hear other machines and
listen to any section, lets you change what you like (songbird.edits: each
change marked as yours and undoable), sends you to the singing page if the
program has one, and records the rendition exactly as `songbird render`
would, with your choices marked. docs/STUDIO.md has the design.

The page keeps the person's edits and sends them with every request; the
server keeps nothing else but caches, so any request can be replayed.

Shared (`--host` other than this computer, or `--allow-host` for a tunnel's
name), it is a temporary preview for a few people: every visitor needs the
link's key, the singing page is off, only everyone's phrasing is offered (no
singer's name), each recording can be downloaded from the page, and the
machine that shapes the song is the computer serving it. docs/STUDIO.md,
"Sharing the studio for a preview".

Public (`--public`), it is open to anyone who reaches it, for good: shared as above but with no key
unless one is given, each visitor held to one render at a time and a few an hour (songbird.public),
recordings offered for download a while and not kept, and an access log that never says who.
docs/WEB-STUDIO.md.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import urllib.request
import webbrowser
import zipfile
from dataclasses import dataclass, field
from datetime import date
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

import numpy as np

from . import drift as drift_mod, explain, genome as genome_mod, harvest, midi, pack, synth, variation
from . import public as public_mod, received
from .realize import Params, realize
from .synth import master
from .synth.instruments import INSTRUMENTS
from .synth.mixing import MixParams

PAGE = Path(__file__).with_name("studio")  # index.html, studio.css, studio.js
ROOT = Path(__file__).resolve().parent.parent  # the program's folder: a packet's, or a checkout
LEAD = "h-now-its-by-you"  # in a checkout, the song the studio opens when nothing names one
PORT = 8766
KARAOKE_PORT = 8765
HOST = "127.0.0.1"  # this computer only, unless asked to share (--host, --allow-host)
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
LOCAL_VERSION_DAYS = 90  # how long this computer's own studio keeps a version someone opened in it
MAX_WAITING = 12  # renders waiting at once: more are refused until the queue shortens (a shared studio)
CACHE_LIMIT = 300 * 2**20  # bytes of previews kept; the least recently heard go first
PREVIEW_GAIN_DB = 5.3  # what mastering gives a whole rendition of H (5.1 to 5.4 dB): a section keeps its level
STATIC = {"/identity.css": ("identity.css", "text/css; charset=utf-8"),  # the shared tokens (docs/IDENTITY.md)
          "/studio.css": ("studio.css", "text/css; charset=utf-8"),
          "/composer.js": ("composer.js", "text/javascript; charset=utf-8"),
          "/drafts.js": ("drafts.js", "text/javascript; charset=utf-8"),
          "/author.js": ("author.js", "text/javascript; charset=utf-8"),
          "/studio.js": ("studio.js", "text/javascript; charset=utf-8"),
          "/help.js": ("help.js", "text/javascript; charset=utf-8"),
          "/export.js": ("export.js", "text/javascript; charset=utf-8"),
          "/perform.js": ("perform.js", "text/javascript; charset=utf-8")}  # notes in: a take, a file brought back
# learning it at the piano (docs/PIANO.md): the page in studio/piano/ (the very files web/piano/ serves too), fed the
# version on the studio's page by /api/piano; and the sketch's players, sent to a musician's instruments (MIDI out)
PIANO_STATIC = {"/piano/": ("piano/index.html", "text/html; charset=utf-8"),
                "/piano/index.html": ("piano/index.html", "text/html; charset=utf-8"),
                "/piano/piano.js": ("piano/piano.js", "text/javascript; charset=utf-8"),
                "/piano/sound.js": ("piano/sound.js", "text/javascript; charset=utf-8"),
                "/piano/piano.css": ("piano/piano.css", "text/css; charset=utf-8"),
                "/piano/identity.css": ("identity.css", "text/css; charset=utf-8")}
STATIC["/players.js"] = ("players.js", "text/javascript; charset=utf-8")
STATIC["/learn.js"] = ("learn.js", "text/javascript; charset=utf-8")


# ---------------------------------------------------------------- where the song and its parent come from


def packet_beside() -> tuple[Path, Path] | None:
    """An unpacked seed packet: its genome.json and manifest.json beside the program (docs/PACKET.md: the
    program under program/, the song and record beside it). Both, if so."""
    for folder in (ROOT, ROOT.parent):
        genome, record = folder / "genome.json", folder / "manifest.json"
        if genome.is_file() and record.is_file():
            return genome, record
    return None


def packet_genome(path: Path, into: Path) -> Path | None:
    """The song a seed packet carries (its genome.json), copied out to sing from and to pack again; None if
    the file carries no packet. Nothing else in it is opened."""
    try:
        with zipfile.ZipFile(path) as z:
            if pack.MANIFEST not in z.namelist() or "genome.json" not in z.namelist():
                return None
            info = z.getinfo("genome.json")
            if info.file_size > 16 * 2**20:
                return None
            into.mkdir(parents=True, exist_ok=True)
            (into / "genome.json").write_bytes(z.read(info))
    except (OSError, zipfile.BadZipFile):
        return None
    return into / "genome.json"


def find_song(record: dict | None, song: str | None) -> Path:
    """The song's genome: the one named; else, in a checkout, the one whose title the parent's record
    carries, else the lead song."""
    if song:
        return Path(song)
    songs = ROOT / "songs"
    if record and record.get("title") and songs.is_dir():
        for path in sorted(songs.glob("*.json")):
            with contextlib.suppress(OSError, ValueError):
                if json.loads(path.read_text()).get("title") == record["title"]:
                    return path
    lead = songs / f"{LEAD}.json"
    if lead.exists():
        return lead
    raise SystemExit("songbird studio: which song? Name its genome with --song")


def locate(parent: str | None, song: str | None, cache: Path) -> tuple[Path, dict | None, str]:
    """The song's genome, the parent's record (or None: the song as it began), and where they came from:
    "packet" (a seed packet: the file given, or unpacked beside the program), "file" (a render record, or a
    FLAC with its record beside it), or "checkout" (the program's own songs)."""
    if parent:
        path = Path(parent)
        record = pack.read_manifest(path) if path.suffix.lower() != ".json" else None
        if record is not None:
            key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
            genome = Path(song) if song else packet_genome(path, cache / "packets" / key)
            return genome, record, "packet"
        record_path = path if path.suffix.lower() == ".json" else path.with_suffix(".json")
        if not record_path.is_file():
            raise SystemExit(f"songbird studio: {parent} carries no packet, and there's no record beside it")
        record = pack.read_record(record_path)
        return find_song(record, song), record, "file"
    beside = packet_beside()
    if beside and not song:
        return beside[0], pack.read_record(beside[1]), "packet"
    return find_song(None, song), None, "checkout"


def slug(text: str) -> str:
    """A title as a file name: 'Now It's by You' -> now-its-by-you."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "").replace("’", "")).strip("-") or "song"


def today() -> tuple[str, float]:
    """Today's date on this computer, and the instant the studio sings it: noon UTC that day, as
    `songbird render --date YYYY-MM-DD` has it, so the same machine opens on the same version all day."""
    day = date.today().isoformat()
    return day, drift_mod.parse(day)


# ---------------------------------------------------------------- previews


def spans(score, form) -> list[tuple[str, float, float]]:
    """Each section of the form and when it plays: the score's spans, with a run of sections of one
    name (verse, verse), which the score keeps as one, shared out evenly (they have the same phrases)."""
    out: list[tuple[str, float, float]] = []
    k = 0
    for name, a, b in score.sections:
        run = 1
        while k + run < len(form) and form[k + run] == name:
            run += 1
        for j in range(run):
            out.append((name, a + (b - a) * j / run, a + (b - a) * (j + 1) / run))
        k += run
    return out


def window(genome, params: Params, score, form, index: int) -> tuple[float, float]:
    """Where a section's preview starts and ends: from a breath before its first pickup (a beat of the band
    before it at least) to where the next section's pickup begins."""
    parts = spans(score, form)
    _, s0, s1 = parts[index]
    unit = 60.0 / params.tempo / genome.meter.beat

    def pickup(k: int) -> float:
        return genome.phrases[genome.section(form[k]).phrases[0]].pickup * unit

    t0 = max(0.0, s0 - max(pickup(index), genome.meter.beat * unit) - 0.5)
    t1 = parts[index + 1][1] - pickup(index + 1) - 0.5 * unit if index + 1 < len(parts) else s1
    return t0, max(t1, s0 + unit)


def cut(score, t0: float, t1: float, before: float = 1.0, tail: float = 2.5):
    """The notes sounding between t0 and t1, moved so that t0 - before is zero: an instrument's note already
    ringing starts at zero (held that much shorter), so the second of lead-in gives it time to settle before
    t0, where the preview begins. A sung syllable before t0 is left out: none is begun halfway."""
    from dataclasses import replace as dc_replace

    start = max(0.0, t0 - before)
    notes = []
    for n in score.notes:
        if n.start >= t1 or n.start + n.dur <= start:
            continue
        if (n.part == "voice" or n.part.startswith("choir")) and n.start < t0:
            continue
        if n.start < start:
            n = dc_replace(n, dur=n.start + n.dur - start, start=start)
        notes.append(dc_replace(n, start=n.start - start))
    return dc_replace(score, notes=tuple(notes), duration=(t1 - start) + tail,
                      sections=tuple((s, max(0.0, a - start), b - start) for s, a, b in score.sections
                                     if b > start and a < t1)), t0 - start


def faded(x: np.ndarray, sr: int, skip: float, fade_in: float = 0.25, fade_out: float = 1.5) -> np.ndarray:
    """The preview from where the section starts, faded in and out."""
    y = x[int(skip * sr):].copy()
    n_in, n_out = min(len(y), int(fade_in * sr)), min(len(y), int(fade_out * sr))
    if n_in:
        y[:n_in] *= (0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, n_in)))[:, None]
    if n_out:
        y[len(y) - n_out:] *= (0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, n_out)))[:, None]
    return y


STAGE_WEIGHTS = {"voice": 5.0, "mix": 5.0, "master": 1.0}  # a band part 1, a lineage voice 2 (measured on H)
STAGE_WORDS = {"voice": "singing", "mix": "mixing", "master": "mastering", "score": "laying out the song"}


def stages(score) -> list[tuple[str, float]]:
    """What a render will make, in order, each with its rough share of the time."""
    parts = [(n, 1.0) for n in INSTRUMENTS if score.part(n)]
    if score.part("voice"):
        parts.append(("voice", STAGE_WEIGHTS["voice"]))
    parts += [(p, 2.0) for p in sorted({n.part for n in score.notes if n.part.startswith("choir")})]
    return parts + [("mix", STAGE_WEIGHTS["mix"]), ("master", STAGE_WEIGHTS["master"])]


def stage_words(name: str) -> str:
    """What a render is doing, as the player says it: "playing the lute", "singing", "mixing"."""
    if name.startswith("choir"):
        return "a voice from before singing"
    return STAGE_WORDS.get(name, f"playing the {explain.player(name)}")


# ---------------------------------------------------------------- the render queue


@dataclass
class Job:
    id: str
    key: str
    kind: str  # "preview" or "record"
    label: str
    work: Callable
    created: float = field(default_factory=time.time)
    state: str = "queued"  # queued, running, done, failed
    progress: float = 0.0
    stage: str = ""
    url: str | None = None
    error: str | None = None
    result: dict | None = None
    then: list = field(default_factory=list)  # run after the work, with the job (a recording's copy)
    plan: list = field(default_factory=list)  # (stage, weight), for its progress
    started: list = field(default_factory=list)  # the stages a render has begun, in its own order
    owner: str | None = None  # the visitor who asked for it (a public studio)
    whole: bool = False  # the whole song, not a section: how long it may take

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "label": self.label, "state": self.state,
                "progress": round(self.progress, 3), "stage": self.stage, "url": self.url, "error": self.error,
                "result": self.result}

    def report(self, name: str) -> None:
        """A render starting on a part: the progress up to it, and what it is making now. The parts it has
        started before this one count as made, in whatever order the render takes them (the voice first on
        one or two threads, some of the band beside it on more)."""
        weights = dict(self.plan)
        total = sum(weights.values()) or 1.0
        before = [stage for stage in self.started if stage != name]
        if name not in self.started:
            self.started.append(name)
        done = sum(weights.get(stage, 0.0) for stage in before)
        self.progress = max(self.progress, min(0.99, done / total))
        self.stage = stage_words(name)


class Busy(Exception):
    """Too many renders waiting (a shared studio): try again when the queue has shortened."""

    def __init__(self, message: str, retry: float = 60.0):
        super().__init__(message)
        self.retry = max(1, int(retry + 0.999))


class Jobs:
    """One render at a time: recordings first, oldest first; then previews, newest first (what the person
    asked for last is what they want to hear). At most MAX_WAITING wait at once.

    Open to the public (`fair`), previews go in the order asked, each visitor has one render queued or
    running at most, and the page is told about how long it will wait."""

    def __init__(self, waiting: int | None = None, fair: bool = False):
        self.lock = threading.Condition()
        self.pending: list[Job] = []
        self.jobs: dict[str, Job] = {}
        self.by_key: dict[str, Job] = {}
        self.waiting = waiting or MAX_WAITING
        self.fair = fair
        self.took = {True: 90.0, False: 15.0, "measure": 30.0}  # seconds a whole song, a section and a sung take take:
        # guesses, then measured (each its own, so measuring takes never skews the renders' estimate)
        threading.Thread(target=self._run, daemon=True, name="studio-renderer").start()

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def live(self, key: str) -> Job | None:
        job = self.by_key.get(key)
        return job if job is not None and job.state in ("queued", "running") else None

    def submit(self, key: str, kind: str, label: str, work: Callable, then: Callable | None = None,
               owner: str | None = None, whole: bool = False, admit: Callable | None = None) -> Job:
        """A render, or the same one already asked for. `owner` (a public studio's visitor) may have one
        at a time; `admit`, a public studio's count of what each visitor has had made, runs once the queue
        has room, and may refuse (public.Limited)."""
        with self.lock:
            job = self.live(key)
            if job is not None:  # asked for again: first among the previews; a recording waits on it
                if not self.fair:
                    job.created = time.time()
                if kind == "record":
                    job.kind = "record"
                    job.label = label
                if then is not None:
                    job.then.append(then)
                return job
            if owner is not None:
                self._one_each(owner)
            if len(self.pending) >= self.waiting:
                if self.fair:
                    raise Busy(f"The studio is busy: {len(self.pending)} songs are waiting to be made, one at a "
                               f"time for everyone. Try again in {public_mod.about(self._eta(self.pending))}.",
                               self._eta(self.pending))
                raise Busy("The studio is busy making other songs; try again in a minute.")
            if admit is not None:
                admit()
            job = Job(secrets.token_hex(6), key, kind, label, work, then=[then] if then else [], owner=owner,
                      whole=whole)
            self.jobs[job.id] = job
            self.by_key[key] = job
            self.pending.append(job)
            finished = sorted((j for j in self.jobs.values() if j.state in ("done", "failed")), key=lambda j: j.created)
            for old in finished[:-200]:
                self.jobs.pop(old.id, None)
            self.lock.notify()
            return job

    def view(self, job: Job) -> dict:
        """A job as the page sees it, with how many renders will run before it (the one running included)."""
        out = job.view()
        with self.lock:
            if job.state == "queued":
                running = sum(1 for j in self.jobs.values() if j.state == "running")
                if job.kind == "record":
                    before = [j for j in self.pending if j.kind == "record" and j.created < job.created]
                elif self.fair:
                    before = [j for j in self.pending if j.kind == "record" or j.created < job.created]
                else:
                    before = [j for j in self.pending if j.kind == "record" or j.created > job.created]
                out["ahead"] = running + len(before)
                if self.fair:
                    out["eta"] = round(self._eta(before))
        return out

    def _one_each(self, owner: str) -> None:
        """A visitor's render at a time: a preview of theirs still waiting gives way to what they ask for
        now; one being made, or a recording waiting, is waited for."""
        for job in list(self.pending):
            if job.owner == owner:
                if job.kind != "preview":
                    what = "Your singing is waiting to be measured" if job.kind == "measure" else \
                        "Your recording is waiting its turn"
                    raise public_mod.Limited(f"{what}; the next can be asked for when it's done.", self._eta([job]))
                self.pending.remove(job)
                job.state, job.error = "failed", "cancelled"
        for job in self.jobs.values():
            if job.owner == owner and job.state == "running":
                raise public_mod.Limited("Yours is being made now; ask for the next when it's done (one at a time "
                                     "for each person, so everyone gets a turn).", self._eta([]))

    def _eta(self, waiting: list[Job]) -> float:
        """Seconds until the renders in `waiting` are made, with the one running now."""
        left = sum(self.took[self._sort(j)] * (1 - j.progress) for j in self.jobs.values() if j.state == "running")
        return left + sum(self.took[self._sort(j)] for j in waiting)

    @staticmethod
    def _sort(job: Job):
        """Which estimate a job's time is: a sung take's measuring, else a whole song's or a section's."""
        return "measure" if job.kind == "measure" else job.whole

    def cancel(self, job_id: str, owner: str | None = None) -> bool:
        """A preview still waiting, dropped; in a public studio only by the visitor who asked for it."""
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or job.state != "queued" or job.kind == "record" or (owner and job.owner != owner):
                return False
            self.pending.remove(job)
            job.state, job.error = "failed", "cancelled"
            return True

    def _next(self) -> Job:
        records = [j for j in self.pending if j.kind == "record"]
        if records or self.fair:
            job = min(records or self.pending, key=lambda j: j.created)
        else:
            job = max(self.pending, key=lambda j: j.created)
        self.pending.remove(job)
        return job

    def _run(self) -> None:
        while True:
            with self.lock:
                while not self.pending:
                    self.lock.wait()
                job = self._next()
                job.state = "running"
            began = time.monotonic()
            try:
                result = job.work(job) or {}
                done = 0
                while True:  # what was asked to follow it (a recording's copy), even if asked for just now
                    with self.lock:
                        todo = job.then[done:]
                        if not todo:
                            job.result, job.progress, job.stage, job.state = result, 1.0, "", "done"
                            self.took[self._sort(job)] = 0.7 * self.took[self._sort(job)] + 0.3 * (time.monotonic() - began)
                            break
                    for then in todo:
                        result.update(then(job) or {})
                    done += len(todo)
            except Exception as e:  # said on the page; the studio carries on
                traceback.print_exc()
                job.error, job.state = f"{type(e).__name__}: {e}", "failed"


# ---------------------------------------------------------------- the studio


class Studio:
    """The song, its parent, the machine and today; the caches; and everything the page asks for."""

    def __init__(self, parent: str | None = None, song: str | None = None, machine: str = "here",
                 out: Path | None = None, home: Path | None = None, key: str | None = None,
                 public: public_mod.Limits | None = None):
        # shared with others by a link carrying this key, or this computer's alone (None); or open to anyone
        # who reaches it, with limits (--public: a key is then optional)
        self.share_key = key
        self.public = public
        self.shared = key is not None or public is not None
        self.home = Path(home or harvest.home_dir()) / "studio"
        self.cache = self.home / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        genome_path, record, self.where = locate(parent, song, self.home)
        self.genome_path = Path(genome_path).resolve()
        self.genome = genome_mod.load(self.genome_path)
        self.song_digest = hashlib.sha256(self.genome_path.read_bytes()).hexdigest()
        # the program itself, not its version number (which stays 0.1.0), so an updated program never plays
        # a preview an older one made
        self.program_digest = pack.program_sha256(pack.program_files())
        self.parent_record = record
        from .cli import _parent

        # as `songbird render --parent` reads it: its generation from the record, and the words it sang as the
        # words it holds where it is from before its lineage held words
        parent_params = _parent(record, self.genome) if record else None
        quiet = False
        if machine == "here":
            cached = harvest.load()
            with contextlib.suppress(OSError, ValueError):
                quiet = cached is None or bool(json.loads(harvest.cache_path().read_text()).get("quiet"))
        self.machine = machine
        self.voice = harvest.machine_voice(machine)
        self.day, self.t = today()
        # a checkout records into renders/; a packet's program, into the folder it was run from
        self.out = Path(out) if out else (Path.cwd() if self.where == "packet" else Path("renders"))
        self.jobs = Jobs(public.queue, fair=True) if public else Jobs()
        self.cache_limit = public.cache_mb * 2**20 if public else CACHE_LIMIT
        # a public studio's counts of what each visitor has had made, and its recordings waiting to be downloaded
        self.gate = public_mod.Gate(public) if public else None
        self.downloads = public_mod.Downloads(self.home / "downloads", public.downloads_mb * 2**20,
                                              public.download_hours) if public else None
        self.token = secrets.token_urlsafe(18)
        self._timeline = None
        self._timeline_lock = threading.Lock()
        self.karaoke: subprocess.Popen | None = None
        self.singing = None  # singing in the browser, when asked for (enable_web_singing)
        self.context = explain.Context(self.genome, parent_params, record, self.voice, machine, self.day, self.t,
                                       quiet, shared=self.shared)
        self._versions_setup(public)
        prune(self.cache, self.cache_limit)
        if public:
            threading.Thread(target=self._tidy, daemon=True, name="studio-tidy").start()

    # ------------------------------------------------------------ the song

    def version(self, edits: dict | None = None, who: str = "you") -> explain.Version:
        """The rendition as the page has it: made by the machine on the day asked, with the edits on top.
        "program": the same day as the program would sing it (the edits aside); another machine: its own
        version that day."""
        edits = dict(edits or {})
        day = {"date": edits["date"]} if "date" in edits else {}
        if who == "program":
            return self.context.version(day, phrasings=self.phrasing_choices())
        if who.startswith("fictional:"):
            return self.context.version(day, voice=harvest.fictional(who.split(":", 1)[1]))
        return self.context.version(edits, phrasings=self.phrasing_choices())

    def song(self, edits: dict) -> dict:
        v = self.version(edits)
        view = explain.view(self.context, v, self.phrasings() + self.sung_phrasings(edits))
        view["listen"] = self.listen_keys(v)
        return view

    def options(self, edits: dict, block: str, index: int) -> dict:
        return explain.word_options(self.context, self.version(edits), block, index)

    def keep_words(self, edits: dict) -> dict:
        return {"edits": {**edits, **explain.keep_words(self.version(edits))}}

    def timeline(self) -> dict:
        with self._timeline_lock:
            if self._timeline is None:
                self._timeline = explain.timeline(self.context)
            return self._timeline

    def compare(self, edits: dict, names: list[str]) -> dict:
        rows = [explain.summary(self.context, self.version(edits), "you")]
        own = self.machine.split(":", 1)[1].lower() if self.machine.startswith("fictional:") else None
        for name in names[:6]:
            name = re.sub(r"[^A-Za-z0-9 _-]", "", str(name)).strip()[:24]
            if name and name.lower() != own:
                who = f"fictional:{name.lower()}"
                rows.append(explain.summary(self.context, self.version(edits, who), who, name=name.title()))
        return {"machines": rows}

    # ------------------------------------------------------------ listening

    def key(self, v: explain.Version, section: int | None) -> str:
        """What a render depends on, hashed: the same rendition and section are made once."""
        material = {"program": self.program_digest, "song": self.song_digest, "params": v.params.to_dict(),
                    "lyrics": v.lyrics.to_dict() if v.lyrics else None, "phrasing": v.phrasing_json,
                    "choir_phrasings": v.choir_phrasings,
                    "section": section, "voice": v.voice.to_dict() if v.voice is not None else None,
                    "drift": v.drift.to_dict() if v.drift is not None else None,
                    "marks": v.marks if section is None else None, "gain": PREVIEW_GAIN_DB}
        if self.version_id is not None:  # someone's version: its lineage sings the choir and names the parent
            material["parent"] = self.version_id
        return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:24]

    def listen_keys(self, v: explain.Version) -> dict:
        keys = {"whole": self.key(v, None), "sections": [self.key(v, k) for k in range(len(v.params.form))]}
        keys["ready"] = [k for k in [keys["whole"], *keys["sections"]] if (self.cache / f"{k}.flac").exists()]
        return keys

    def listen(self, edits: dict, who: str, section: int | None, by: tuple[str, str] | None = None) -> dict:
        """A preview (a section, or the whole song) made or on its way. `by`: the visitor and address asking,
        in a public studio, for its limits."""
        v = self.version(edits, who)
        if section is not None and not 0 <= section < len(v.params.form):
            raise ValueError("no such section")
        key = self.key(v, section)
        label = explain.listen_label(self.context, v, section, who)
        flac = self.cache / f"{key}.flac"
        if flac.exists():
            os.utime(flac)
            return {"state": "done", "url": f"/audio/{key}.flac", "label": label, "progress": 1.0, "key": key}
        if section is None:
            job = self.jobs.submit(key, "preview", label, lambda job: self._whole(job, v, key),
                                   **self._limits(by, whole=True))
        else:
            job = self.jobs.submit(key, "preview", label, lambda job: self._section(job, v, key, section),
                                   **self._limits(by, whole=False))
        return self.jobs.view(job) | {"key": key}

    def _limits(self, by: tuple[str, str] | None, whole: bool) -> dict:
        """What the queue needs to hold a public studio's visitor to its limits (nothing for anyone else)."""
        if self.gate is None or by is None:
            return {"whole": whole}
        visitor, ip = by
        return {"whole": whole, "owner": visitor,
                "admit": lambda: self.gate.render("records" if whole else "previews", visitor, ip)}

    def warm(self) -> None:
        """Make today's first verse while the page opens: the synthesis is compiled the first time it runs
        (10 to 15 s), so the first thing a person asks to hear doesn't wait for that, and it's ready."""
        v = self.version({})
        first = next((k for k, name in enumerate(v.params.form) if self.genome.section(name).lyrics), 0)
        self.listen({}, "you", first)

    def _score(self, v: explain.Version):
        from . import phrasing as phrasing_mod

        phrasing = phrasing_mod.from_json(v.phrasing_json) if v.phrasing_json else None
        choir = [phrasing_mod.from_json(ph) for ph in v.choir_phrasings]
        return variation.lay(realize(self.genome, v.params, phrasing=phrasing, choir=choir, lyrics=v.lyrics), v.params)

    def _section(self, job: Job, v: explain.Version, key: str, index: int) -> dict:
        """A preview of one section: cut from the whole rendition's score, made, and brought up by the gain a
        whole rendition gets in mastering (so a quiet verse stays quiet), under the same ceiling."""
        from .cli import choir_of

        job.stage = stage_words("score")
        score = self._score(v)
        t0, t1 = window(self.genome, v.params, score, v.params.form, index)
        part, lead_in = cut(score, t0, t1)
        job.plan = stages(part)
        singer = explain.singer_of(v.params)
        ancestors = choir_of(self.parent_record, singer)[1]  # the earlier versions sing its choir, as they will
        mix = synth.render(part, seed=v.params.seed, voice=singer, mix_params=MixParams.from_dict(v.params.mix or {}),
                           ancestors=ancestors, progress=job.report)
        job.report("master")
        ceiling = master.CEILING_DB - master.MARGIN_DB
        loud = master.limit(master.clip(mix * 10.0 ** (PREVIEW_GAIN_DB / 20.0), ceiling), synth.SR, ceiling)
        pcm = master.to_pcm16(faded(loud, synth.SR, lead_in), seed=v.params.seed)
        tmp = self.cache / f"{key}.part.flac"
        master.write_flac(tmp, pcm, synth.SR)
        tmp.replace(self.cache / f"{key}.flac")
        job.url = f"/audio/{key}.flac"
        prune(self.cache, self.cache_limit)
        return {"url": job.url, "duration": round(len(pcm) / synth.SR, 2)}

    def _whole(self, job: Job, v: explain.Version, key: str) -> dict:
        """The whole rendition, made exactly as `songbird render --pack` makes it (cli.render_one): one file
        carrying the program, the song and its record, the child of the version the studio opened on. It is
        the recording."""
        from .cli import render_one

        job.stage = stage_words("score")
        job.plan = stages(self._score(v))
        folder = self.cache / key
        genome_file = self.genome_path
        if self.version_id is not None:  # someone's version: the song it sang, beside its child, whatever becomes of it
            folder.mkdir(parents=True, exist_ok=True)
            genome_file = folder / "genome.json"
            genome_file.write_bytes(self.genome_bytes)
        with contextlib.redirect_stdout(io.StringIO()):
            record = render_one(self.genome, v.params, folder / "rendition.flac", voice=v.voice, drift=v.drift,
                                lyrics=v.lyrics, phrasing_json=v.phrasing_json, choir_json=v.choir_phrasings,
                                parent=self.parent_record,
                                packet_genome=genome_file, changes=v.changes if v.drift is not None else None,
                                chosen_by_you=v.marks or None, progress=job.report)
        (folder / "rendition.json").write_text(json.dumps(record, indent=2) + "\n")
        link(folder / "rendition.flac", self.cache / f"{key}.flac")
        job.url = f"/audio/{key}.flac"
        prune(self.cache, self.cache_limit)
        return {"url": job.url, "id": record["id"], "duration": record["duration"]}

    # ------------------------------------------------------------ exporting for musicians

    def export_name(self, v: explain.Version, suffix: str) -> str:
        return f"{slug(self.genome.title)}.{self.day}.{self.key(v, None)[:6]}{suffix}"

    def export(self, edits: dict, what: str, by: tuple[str, str] | None = None) -> dict:
        """Files for a musician's own tools, of the version as the page has it: "midi", every part as MIDI
        (made at once, from the score the render sings); "stems", every part rendered alone, dry, as
        `songbird render --stems` makes them, with the MIDI, in one zip (a render, so a job: in a public
        studio it waits its turn and counts as a whole song made for the visitor, `by`)."""
        v = self.version(edits)
        key = self.key(v, None)
        if what == "midi":
            path = self.cache / f"{key}.mid"
            if not path.exists():
                data, _ = midi.from_score(self.genome, v.params, self._score(v), title=self.genome.title)
                path.write_bytes(data)
            return {"state": "done", "progress": 1.0,
                    "url": f"/export/{key}.mid?name={self.export_name(v, '.mid')}", "label": "the MIDI file"}
        if what != "stems":
            raise ValueError("export midi or stems")
        name = self.export_name(v, ".stems.zip")
        url = f"/export/{key}.zip?name={name}"
        if (self.cache / f"{key}.zip").exists():
            return {"state": "done", "progress": 1.0, "url": url, "label": "the stems", "kind": "export"}
        job = self.jobs.submit(f"{key}-stems", "preview", "the stems", lambda job: self._stems(job, v, key, name),
                               **self._limits(by, whole=True))
        return self.jobs.view(job) | {"download": url}

    def _stems(self, job: Job, v: explain.Version, key: str, name: str) -> dict:
        """Every part of the rendition rendered alone and dry (synth.render_stems, as the command line's
        --stems), each padded to start at the MIDI file's bar 1, as 24-bit FLAC; the MIDI file and a note on
        what they are beside them, in one zip."""
        import soundfile as sf

        from .cli import choir_of

        job.stage = stage_words("score")
        score = self._score(v)
        job.plan = [p for p in stages(score) if p[0] not in ("mix", "master")] + [("master", 1.0)]
        data, lead_in = midi.from_score(self.genome, v.params, score, title=self.genome.title)
        singer = explain.singer_of(v.params)
        stems = synth.render_stems(score, seed=v.params.seed, voice=singer,
                                   ancestors=choir_of(self.parent_record, singer)[1], progress=job.report)
        job.report("master")
        job.stage = "packing the stems"
        pad = int(round(-lead_in * synth.SR))
        peak = max((float(np.max(np.abs(x))) for x in stems.values() if x.size), default=0.0)
        gain = min(1.0, 0.989 / peak) if peak > 0 else 1.0  # one gain for all, so they keep their balance
        order = sorted(stems, key=lambda p: (p != "voice", not p.startswith("choir"), list(stems).index(p)))
        stem = name[: -len(".stems.zip")]
        tmp = self.cache / f"{key}.part.zip"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for i, part in enumerate(order, 1):
                buffer = io.BytesIO()
                sf.write(buffer, np.pad(stems[part] * gain, [(pad, 0), (0, 0)]), synth.SR, format="FLAC",
                         subtype="PCM_24")
                z.writestr(f"{stem}/{i:02d}-{part}.flac", buffer.getvalue())
            z.writestr(f"{stem}/{stem}.mid", data)
            z.writestr(f"{stem}/README.txt", stems_note(self.genome.title, v.params, -lead_in, gain, order))
        tmp.replace(self.cache / f"{key}.zip")
        prune(self.cache, CACHE_LIMIT)
        job.url = f"/export/{key}.zip?name={name}"
        return {"url": job.url, "parts": len(order)}

    # ------------------------------------------------------------ at the piano, and the sketch's players (MIDI out)
    # Both are cheap (the score laid again, no audio: a tenth of a second or two for H), made at once like the MIDI
    # file, and held to a public studio's limit on requests like every other request.

    def piano(self, edits: dict) -> dict:
        """The piano page's score (songbird.piano) of the version as the page has it, kept in the cache by what it
        depends on, and where the page that teaches it is: /piano/?score=score/KEY.json."""
        from . import phrasing as phrasing_mod, piano as piano_mod

        v = self.version(edits)
        key = self.key(v, None)
        path = self.cache / f"{key}.piano.json"
        if path.exists():
            os.utime(path)
        else:
            phrasing = phrasing_mod.from_json(v.phrasing_json) if v.phrasing_json else None
            choir = [phrasing_mod.from_json(ph) for ph in v.choir_phrasings]
            laid = piano_mod.lay(self.genome, v.params, phrasing=phrasing, choir=choir, lyrics=v.lyrics)
            data = piano_mod.export(laid, {"kind": "studio", "exporter": "songbird studio", "day": self.day,
                                           "version": key[:6]})
            tmp = self.cache / f"{key}.piano.part.json"
            tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
            tmp.replace(path)
            prune(self.cache, self.cache_limit)
        return {"url": f"/piano/?score=score/{key}.json", "score": f"/piano/score/{key}.json", "key": key}

    def players(self, edits: dict) -> dict:
        """Every part of the version as the MIDI file has it (midi.layout: the same channels and programs), each
        part's notes in beats of the song's grid, for the sketch to play or send to a musician's instruments in
        step with its tune (songbird/studio/players.js). The singer's part is the sketch's own tune, so only its
        channel and program are given; the chords' are the MIDI file's Chords track's."""
        v = self.version(edits)
        parts = midi.in_beats(self.genome, v.params, self._score(v))
        voice = next((p for p in parts if p["part"] == "voice"), None)
        return {"key": self.key(v, None), "tempo": v.params.tempo,
                "tune": {"channel": voice["channel"] if voice else 0, "program": midi.PROGRAMS["voice"]},
                "chords": {"channel": midi.CHORDS_CHANNEL, "program": midi.PROGRAMS["chords"]},
                "players": [p for p in parts if p["part"] != "voice"]}

    # ------------------------------------------------------------ recording

    # ------------------------------------------------------------ notes in (docs/STUDIO.md, "Notes in")

    def notes_in(self, edits: dict, body: dict) -> dict:
        """A preview of notes brought in over the version on the page (songbird.notesin): a MIDI file ("file",
        base64; "assign" names tracks it couldn't), or a take played along with the sketch ("take": its player,
        its notes and the lines it covered). Nothing changes here: the page applies the changes it is shown.
        Made at once, without a render; a file it can't read, or one from another version, says why."""
        from . import notesin

        v = self.version(edits)
        if "file" in body:
            assign = body.get("assign") or {}
            if not isinstance(assign, dict) or len(assign) > midi.MAX_TRACKS * 16:
                raise ValueError("name the tracks as a map")
            data = notesin.decode(body["file"])
            return notesin.from_file(self.genome, v.params, self._score(v), data, assign)
        take = body.get("take")
        if not isinstance(take, dict):
            raise ValueError("send a file or a take")
        return notesin.take(self.genome, v.params, str(take.get("player", "")), take.get("notes"), take.get("lines"))

    def record(self, edits: dict, by: tuple[str, str] | None = None) -> dict:
        v = self.version(edits)
        key = self.key(v, None)
        folder = self.cache / key
        keep = lambda job=None: self._keep(folder)  # noqa: E731
        if all((folder / name).exists() for name in ("rendition.json", "rendition.flac")) \
                and (self.cache / f"{key}.flac").exists():
            return {"state": "done", "progress": 1.0, "url": f"/audio/{key}.flac", "result": keep(),
                    "label": "the recording", "kind": "record"}
        return self.jobs.view(self.jobs.submit(key, "record", "the recording", lambda job: self._whole(job, v, key),
                                               then=keep, **self._limits(by, whole=True)))

    def _keep(self, folder: Path) -> dict:
        """The recording copied from the cache to where recordings go, as <song>.<day>.<its id's first six>.flac:
        one file, the program, the song and the record inside it."""
        record = json.loads((folder / "rendition.json").read_text())
        day = (record.get("rendered_at") or self.day)[:10]
        flac = self.out / f"{slug(self.genome.title)}.{day}.{record['id'][:6]}.flac"
        if self.downloads is not None:  # open to the public: kept a while to download, not here for good
            self.downloads.keep(folder / "rendition.flac", folder.name)
            return {"recorded": {"flac": flac.name, "name": flac.name, "id": record["id"],
                                 "duration": record["duration"], "generation": record.get("generation"),
                                 "yours": len(record.get("chosen_by_you") or {}),
                                 "next": f"python3 {flac.name} studio", "shared": True,
                                 "download": f"/download/{folder.name}.flac?name={flac.name}",
                                 "expires": self.public.download_hours}}
        self.out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / "rendition.flac", flac)
        if self.shared:  # the visitor's copy is the download; the path is the host's
            again = f"python3 {flac.name} studio"
        elif self.where == "packet":
            again = f"python3 {shown(flac)} studio"
        else:
            again = f"uv run songbird studio {shown(flac)}"
        return {"recorded": {"flac": shown(flac), "name": flac.name, "id": record["id"],
                             "duration": record["duration"], "generation": record.get("generation"),
                             "yours": len(record.get("chosen_by_you") or {}), "next": again,
                             "download": f"/audio/{folder.name}.flac?name={flac.name}", "shared": self.shared}}

    def out_shown(self) -> str:
        return "" if self.public else shown(self.out)  # the serving computer's folders are its own

    def packet_note(self) -> str:
        note = ("The recording is one file: it plays anywhere, and it carries the program that sang it, the song "
                "and its record, so anyone can run it to make the next version.")
        if self.public:
            hours = self.public.download_hours
            note += f" Download your copy here: the studio keeps it for {hours:g} hours, then lets it go."
        elif self.shared:
            note += " It is saved on the computer serving this studio; download your copy here."
        return note

    # ------------------------------------------------------------ open to the public

    def health(self) -> dict:
        """/healthz: that it answers, and how long the queue is."""
        with self.jobs.lock:
            return {"ok": True, "waiting": len(self.jobs.pending),
                    "running": any(j.state == "running" for j in self.jobs.jobs.values())}

    def _tidy(self, every: float = 600.0) -> None:
        """Now and then: recordings past their time let go, the cache kept to its size, old counts forgotten."""
        while True:
            time.sleep(every)
            with contextlib.suppress(Exception):
                self.downloads.prune()
                prune(self.cache, self.cache_limit)
                self.gate.purge()

    # ------------------------------------------------------------ someone's version (songbird.received)
    #
    # A person opens a rendition they were sent (its FLAC) and the studio continues from it, as `songbird studio
    # parent.flac` does from the command line. POST /api/open brings the file; `receive` has it read, as data and
    # never as the program it carries, in a process of its own (received.examine_apart), and keeps what a parent
    # gives its child under an id; `opened` is this studio on that parent, which the page reaches at /v/<id>.
    # docs/WEB-STUDIO.md, "Opening someone's version".

    version_id: str | None = None  # the version this studio was opened on, when someone brought it (opened)
    genome_bytes: bytes | None = None  # ... and the song it sang, as it came

    def _versions_setup(self, public: public_mod.Limits | None) -> None:
        limits = public or public_mod.Limits()
        self.versions = received.Versions(self.home / "versions", limits.versions_mb * 2**20,
                                          limits.version_days if public else LOCAL_VERSION_DAYS)
        self.upload_limit = min(limits.upload_mb * 2**20, received.UPLOAD)
        # each file brought is written to a folder of its own here, read, and removed; a folder older than an
        # hour is one a stopped studio left
        self.incoming = self.home / "incoming"
        self.incoming.mkdir(parents=True, exist_ok=True)
        for old in self.incoming.iterdir():
            with contextlib.suppress(OSError):
                if time.time() - old.stat().st_mtime > 3600:
                    shutil.rmtree(old, ignore_errors=True)
        self.reading = threading.BoundedSemaphore(2)  # files read at once, each by a process of its own
        self.arriving: set[str] = set()  # the addresses sending a file now: one each, and a few in all
        self._arriving_lock = threading.Lock()
        self._opened: collections.OrderedDict = collections.OrderedDict()  # id -> Studio, the latest few
        self._genomes: collections.OrderedDict = collections.OrderedDict()  # song digest -> Genome, shared
        self._opened_lock = threading.Lock()

    def receive(self, path: Path) -> dict:
        """A file someone brought (in a folder of its own, which the caller removes), read as data by a process
        of its own and kept, if this program can continue it, as a version this studio opens at /v/<id>.
        Raises received.Refused, saying why, if not."""
        out = received.examine_apart(path, self.genome.title, self.machine, self.day, ROOT, path.parent)
        record, song = out.get("record"), out.get("genome")
        if not isinstance(record, dict) or not isinstance(song, str):
            raise received.Refused("It couldn't be read here: the reader stopped on it.")
        timeline = out.get("timeline")
        timeline = timeline if isinstance(timeline, dict) and timeline.get("day") == self.day \
            and timeline.get("machine") == self.machine else None
        vid = self.versions.put(record, song.encode("utf-8"), timeline)
        other = self.opened(vid)
        if other is None:
            raise received.Refused("It was read, but couldn't be kept here; try again in a moment.")
        return {"id": vid, "url": f"/v/{vid}", "version": other.version_view(), "minutes": out.get("minutes")}

    def opened(self, vid: str) -> Studio | None:
        """This studio on a version someone brought (by its id), as `songbird studio parent.flac` would open
        on it: its own song, record and context; the queue, caches, limits, counts and token shared. The
        latest few are kept; None if there's no such version kept here."""
        with self._opened_lock:
            hit = self._opened.get(vid)
            if hit is not None:
                self._opened.move_to_end(vid)
                return hit
        kept = self.versions.get(vid)
        if kept is None:
            return None
        record, genome_path, timeline = kept
        try:
            data = genome_path.read_bytes()
        except OSError:
            return None
        digest = hashlib.sha256(data).hexdigest()
        from .cli import _parent

        with self._opened_lock:
            genome = self.genome if digest == self.song_digest else self._genomes.get(digest)
        if genome is None:  # checked when it was brought; parsed again from this studio's own store
            genome = genome_mod.from_dict(json.loads(data))
        other = copy.copy(self)
        other.version_id, other.parent_record, other.genome_bytes = vid, record, data
        other.genome, other.song_digest = genome, digest
        # the song as this studio has it, if it's the same (its phrasings are found by its file's name)
        other.genome_path = self.genome_path if digest == self.song_digest else genome_path
        other.context = explain.Context(genome, _parent(record, genome), record, self.voice, self.machine, self.day,
                                        self.t, self.context.quiet, shared=self.shared)
        other._timeline = timeline.get("drawn") if timeline and timeline.get("day") == self.day \
            and timeline.get("machine") == self.machine else None
        other._timeline_lock = threading.Lock()
        other.karaoke = None
        with self._opened_lock:
            if digest != self.song_digest:
                self._genomes[digest] = genome
                while len(self._genomes) > 8:
                    self._genomes.popitem(last=False)
            other = self._opened.setdefault(vid, other)
            while len(self._opened) > 16:
                self._opened.popitem(last=False)
        return other

    def version_view(self) -> dict | None:
        """What the page says of the version it was opened on, when someone brought it."""
        if self.version_id is None:
            return None
        r = self.parent_record
        theirs = r["program_sha256"]
        other = theirs != self.program_digest
        return {"id": self.version_id, "url": f"/v/{self.version_id}", "generation": generation(r),
                "made": (r.get("rendered_at") or "")[:10] or None, "rendition": r["id"][:12],
                "program": theirs[:12], "other_program": other,
                "program_note": (f"It was made by another version of the program ({theirs[:8]}…); this studio "
                                 f"continues it with its own ({self.program_digest[:8]}…), so the new version is "
                                 "sung by this one." if other else "It was made by the same program as this studio.")}

    # ------------------------------------------------------------ singing (from a checkout of the program)

    def phrasing_files(self) -> dict[str, Path]:
        """The phrasings made on this computer for this song by people who sang it on the singing page, and
        everyone's together: name -> file. Only in a checkout (renders/phrasing, recordings/); reference
        voices are never among them."""
        folder = ROOT / "renders" / "phrasing"
        recordings = ROOT / "recordings"
        stem = self.genome_path.stem
        found = {}
        if self.shared:  # shared with others: everyone's together only, never one singer's way or name
            everyone = folder / f"{stem}.everyone.json"
            return {"everyone": everyone} if recordings.is_dir() and everyone.exists() else {}
        if recordings.is_dir() and folder.is_dir():
            for person in sorted(p for p in recordings.iterdir() if p.is_dir() and p.name != "guides"):
                if any(person.glob(f"{stem}-*.wav")) and (folder / f"{stem}.{person.name}.json").exists():
                    found[person.name] = folder / f"{stem}.{person.name}.json"
        if found and (folder / f"{stem}.everyone.json").exists():
            found["everyone"] = folder / f"{stem}.everyone.json"
        return found

    def phrasings(self) -> list[dict]:
        out = []
        for who, path in self.phrasing_files().items():
            detail = ""
            with contextlib.suppress(OSError, ValueError):
                detail = json.loads(path.read_text()).get("source_detail", "")
            out.append({"id": who, "label": "everyone who has sung it" if who == "everyone" else singer_name(who),
                        "detail": detail})
        return out

    def sing_available(self) -> dict:
        if self.singing is not None:  # singing in the browser, here (webstudio/): the karaoke page isn't needed
            return self.singing.available()
        if self.shared:
            return {"available": False,
                    "why": "The singing page opens only on the computer serving this studio, not over a shared link."}
        if (ROOT / "tools" / "karaoke.py").exists():
            return {"available": True}
        return {"available": False,
                "why": "Singing into it needs the singing page, which this copy of the program doesn't have yet."}

    def sing(self) -> dict:
        """Start the singing page (tools/karaoke.py) for this song if it isn't running, and say where it is."""
        url = f"http://127.0.0.1:{KARAOKE_PORT}"
        if self.shared:  # a visitor can't reach it, and shouldn't start anything on this computer
            return {"error": self.sing_available()["why"]}
        if listening(KARAOKE_PORT):
            if self.karaoke_title() == self.genome.title:
                return {"url": url}
            return {"error": f"Something else is using port {KARAOKE_PORT}, where the singing page would open."}
        available = self.sing_available()
        if not available["available"]:
            return {"error": available["why"]}
        if self.karaoke is None or self.karaoke.poll() is not None:
            self.karaoke = subprocess.Popen([sys.executable, str(ROOT / "tools" / "karaoke.py"), str(self.genome_path),
                                             "--port", str(KARAOKE_PORT)], cwd=ROOT, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
        for _ in range(160):  # it loads its measuring tools first: a few seconds
            if listening(KARAOKE_PORT):
                return {"url": url}
            if self.karaoke.poll() is not None:
                return {"error": "The singing page didn't start."}
            time.sleep(0.25)
        return {"error": "The singing page is taking a long time to start; try again in a moment."}

    def karaoke_title(self) -> str | None:
        with contextlib.suppress(Exception):
            with urllib.request.urlopen(f"http://127.0.0.1:{KARAOKE_PORT}/lyrics.json", timeout=20) as r:
                return json.loads(r.read()).get("title")
        return None

    def close(self) -> None:
        if self.karaoke is not None and self.karaoke.poll() is None:
            self.karaoke.terminate()
        if self.singing is not None:
            self.singing.close()

    # ------------------------------------------------------------ singing in the browser (webstudio/, --web-singing)
    #
    # A visitor sings to a guide on the studio's own page; the take is measured here and its audio deleted, and
    # the song can be sung their way (docs/WEB-SINGING.md). All of it lives in webstudio/, outside the song's
    # program (a packet never carries it): it needs a checkout's tools, their dev dependencies and the singing
    # kit. These are the studio's only hooks into it.

    def enable_web_singing(self, kit: str | Path | None = None, check: bool = False) -> None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from webstudio.singing import Singing

        self.singing = Singing(self, kit, check=check)

    def phrasing_choices(self):
        """The ways of singing a version may name: those made on this computer, and, with singing in the
        browser, the one a page made there (by its fingerprint, never listed)."""
        made = self.phrasing_files()
        return self.singing.lookup(made) if self.singing is not None else made

    def sung_phrasings(self, edits: dict) -> list[dict]:
        """For the singer's card: the way of singing in the browser these edits chose, if they chose one."""
        return self.singing.listed(edits) if self.singing is not None else []


def generation(record: dict) -> int:
    g = record.get("generation")
    return g if isinstance(g, int) and g >= 0 else 0


def singer_name(who: str) -> str:
    """A singer's name as they wrote it, from their newest take's note; else their folder's name."""
    for note in sorted((ROOT / "recordings" / who).glob("*.json"), reverse=True):
        with contextlib.suppress(OSError, ValueError):
            name = json.loads(note.read_text()).get("singer")
            if name:
                return str(name)
    return who.replace("-", " ").title()


def stems_note(title: str, params: Params, pad: float, gain: float, parts: list[str]) -> str:
    """What the stems are, for the person who unzips them."""
    level = ("" if gain >= 1.0 else
             f"\n\nAll of them were turned down together by {-20 * np.log10(gain):.1f} dB, so none clips "
             "and they keep their balance.")
    return textwrap.dedent(f"""\
        {title}: the parts, for your own tools
        Made by Songbird's studio: {midi.key_name(params.tonic, params.mode)}, {params.tempo:g} beats a minute.

        Each part is rendered alone and dry, as the program plays it before the mix: no room, no mix's
        balance, no mastering (the recording has those, so these don't add up to it exactly).{{level}}

        Every file starts at bar 1 of the MIDI file beside them ({pad:.3f} s of silence before the
        song's first sound), so put them all at the start of a project with the MIDI file and they line
        up: the MIDI file carries the tempo (with the ending's slowing), the bars, the key, the
        sections, the words as lyrics and the chords.

        Parts: {", ".join(parts)}. 24-bit FLAC, 44.1 kHz, stereo.

        The song and the program are public domain (CC0): do what you like with them.
        """).replace("{level}", level)


def link(src: Path, dst: Path) -> None:
    """dst the same file as src (a hard link, so a whole song isn't stored twice), else a copy."""
    with contextlib.suppress(OSError):
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def listening(port: int) -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def shown(path: Path) -> str:
    """A path as a person would type it: relative to here if it can be, else with ~ for home."""
    path = Path(path).resolve()
    with contextlib.suppress(ValueError):
        return str(path.relative_to(Path.cwd()))
    home = str(Path.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def prune(folder: Path, limit: int) -> None:
    """Keep the cache under its limit, the least recently used first to go: a preview's file, or a whole
    rendition's folder at once (never half of one)."""
    units = []
    for p in folder.iterdir():
        with contextlib.suppress(OSError):
            if p.is_dir():
                files = [f for f in p.rglob("*") if f.is_file()]
                stats = [f.stat() for f in files]
                units.append((max((s.st_mtime for s in stats), default=p.stat().st_mtime),
                              sum(s.st_size for s in stats), p))
            else:
                s = p.stat()
                units.append((s.st_mtime, s.st_size, p))
    total = sum(size for _, size, _ in units)
    for _, size, p in sorted(units, key=lambda u: u[0]):
        if total <= limit:
            break
        total -= size
        with contextlib.suppress(OSError):
            shutil.rmtree(p) if p.is_dir() else p.unlink()


# ---------------------------------------------------------------- the server


def allowed_host(host: str, port: int, names: tuple[str, ...]) -> bool:
    """Whether a Host header names this server: 127.0.0.1 or localhost at its port; else, shared, one of the
    names it was given (with or without a port: a tunnel's name has none), or a name under one given with
    a leading dot (".trycloudflare.com")."""
    host = host.strip().lower()
    if host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
        return True
    bare = host[: -len(f":{port}")] if host.endswith(f":{port}") else host
    for name in names:
        if name.startswith("."):
            if bare.endswith(name) and len(bare) > len(name) and ":" not in bare:
                return True
        elif bare == name:
            return True
    return False


class Handler(BaseHTTPRequestHandler):
    studio: Studio
    port: int = PORT
    names: tuple[str, ...] = ()  # the other names it answers to, when shared (lower case)
    server_version = "songbird-studio"
    sys_version = ""  # no need to say which Python
    protocol_version = "HTTP/1.1"

    client_ip_header: str | None = None  # behind a proxy (--client-ip-header CF-Connecting-IP): who it says asked
    log = None  # a public studio's access log: stdout as it was when serving began (a render swaps sys.stdout)
    _sent: tuple[int, int] | None = None
    _began = 0.0

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def parse_request(self) -> bool:
        self._began = time.monotonic()
        return super().parse_request()

    def handle_one_request(self) -> None:
        self._sent = None
        super().handle_one_request()
        if self.studio.public is not None and self._sent is not None:  # a public studio's access log: never who
            self.log.write(public_mod.access_line(self.command, urlsplit(self.path).path, *self._sent,
                                                  time.monotonic() - self._began) + "\n")
            self.log.flush()

    # ------------------------------------------------------------ guards

    def _local(self) -> bool:
        """The Host names this server, so no page elsewhere can reach it under another name (DNS rebinding);
        and a request that says where it came from came from a page of this server's, by its own name."""
        host = self.headers.get("Host", "")
        if not allowed_host(host, self.port, self.names):
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() in (f"http://{host.lower()}", f"https://{host.lower()}")

    def _key(self) -> str | None:
        """The key this request carries: in the link (?key=) or the cookie a first visit with it set."""
        given = parse_qs(urlsplit(self.path).query).get("key", [""])[0]
        if given:
            return given
        with contextlib.suppress(CookieError):
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get(self._cookie())
            return morsel.value if morsel else None
        return None

    def _cookie(self) -> str:
        return f"songbird-studio-{self.port}"

    def _admitted(self) -> bool:
        """This computer's own studio admits its own page; a shared one, only a visitor with its key (a
        public one without a key, anyone)."""
        if not self.studio.shared or self.studio.share_key is None:
            return True
        key = self._key() or ""
        return secrets.compare_digest(key.encode("utf-8", "replace"), self.studio.share_key.encode())

    def _ip(self) -> str:
        return public_mod.client_ip(self.client_address[0], self.headers, self.client_ip_header)

    def _visitor(self) -> str | None:
        """A public studio's visitor: the random id its page's cookie carries (nothing else is known of them)."""
        with contextlib.suppress(CookieError):
            morsel = SimpleCookie(self.headers.get("Cookie", "")).get(f"songbird-visitor-{self.port}")
            if morsel and re.fullmatch(r"[A-Za-z0-9_-]{16,64}", morsel.value):
                return morsel.value
        return None

    def _by(self) -> tuple[str, str]:
        """Who is asking, for a public studio's limits: the visitor (or, with no cookie, their address) and
        their address."""
        ip = self._ip()
        return self._visitor() or f"ip:{ip}", ip

    def _throttled(self) -> bool:
        """A public studio's limit on requests from one address: said, and True, if it's past."""
        try:
            self.studio.gate.request(self._ip())
        except public_mod.Limited as e:
            self.close_connection = True
            self.too_many(429, e)
            return True
        return False

    def too_many(self, code: int, e: Exception) -> None:
        retry = getattr(e, "retry", 60)
        self.send(json.dumps({"error": str(e), "retry": retry, "busy": True}).encode(), "application/json", code,
                  {"Retry-After": str(retry)})

    def refuse_visitor(self) -> None:
        page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                "<title>Songbird studio</title><body style='font:17px/1.5 Georgia,serif;max-width:34em;"
                "margin:12vh auto;padding:0 16px'><h1 style='font-weight:500'>This studio is shared by link</h1>"
                "<p>Its link carries a key: ask the person who shared it for the whole link, "
                "ending in <code>?key=</code>.</p></body>")
        self.send(page.encode(), "text/html; charset=utf-8", 403)

    # ------------------------------------------------------------ replies

    def send(self, body: bytes | io.BufferedReader, kind: str, code: int = 200,
             extra: dict | list | None = None) -> None:
        """A reply: bytes, or an open file's (sent as it's read, not held whole)."""
        whole = isinstance(body, (bytes, bytearray))
        size = len(body) if whole else os.fstat(body.fileno()).st_size
        self._sent = (code, size)
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; media-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'")
        for k, v in (extra.items() if isinstance(extra, dict) else extra or ()):
            self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD":
            return
        if whole:
            self.wfile.write(body)
        else:
            shutil.copyfileobj(body, self.wfile, 2**16)

    def send_json(self, data, code: int = 200) -> None:
        self.send(json.dumps(data).encode(), "application/json", code)

    def fail(self, code: int, message: str) -> None:
        self.send_json({"error": message}, code)

    # ------------------------------------------------------------ GET

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        if not self._local():
            return self.fail(403, "this page answers only its own address")
        path = urlsplit(self.path).path
        if self.studio.public is not None:
            if path == "/healthz":
                return self.send_json(self.studio.health())
            if self._throttled():
                return
        if not self._admitted():
            return self.refuse_visitor() if path in ("/", "/index.html") or path.startswith("/v/") \
                else self.fail(403, "this studio needs its link's key")
        try:
            singing = self.studio.singing
            if singing is not None and singing.get(self, path, {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}):
                return None
            if path == "/piano" or path.startswith("/piano/"):  # learning it at the piano
                return self.piano_page(path)
            version = re.fullmatch(r"/v/([0-9a-f]{32})", path)  # someone's version: the page's token names it
            if path.startswith("/v/") and (version is None or self.studio.opened(version.group(1)) is None):
                return self.version_gone()
            if path in ("/", "/index.html") or version:
                token = f"{self.studio.token}.{version.group(1)}" if version else self.studio.token
                page = (PAGE / "index.html").read_text().replace("{{token}}", token)
                if singing is not None:
                    page = singing.page(page)
                extra = []
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "").lower() == "https" else ""
                if self.studio.share_key:  # the key, kept for this visit's other requests (the audio's among them)
                    extra.append(("Set-Cookie", f"{self._cookie()}={self.studio.share_key}; Path=/; HttpOnly; "
                                                f"SameSite=Lax{secure}"))
                if self.studio.public is not None and self._visitor() is None:  # a random id for the limits
                    extra.append(("Set-Cookie", f"songbird-visitor-{self.port}={secrets.token_urlsafe(18)}; Path=/; "
                                                f"Max-Age=86400; HttpOnly; SameSite=Lax{secure}"))
                return self.send(page.encode(), "text/html; charset=utf-8", extra=extra)
            if path in STATIC:
                name, kind = STATIC[path]
                return self.send((PAGE / name).read_bytes(), kind)
            studio = self._asked() if path in ("/api/start", "/api/timeline", "/api/phrasings") else self.studio
            if studio is None:  # the version the page was opened on (someone brought it) isn't kept any more
                return self.version_gone()
            if path == "/api/start":
                start = explain.start(studio.context, studio)
                if studio.public is not None:
                    start["public"] = studio.public.view()
                start["open"] = {"upload_mb": studio.upload_limit // 2**20}
                if studio.version_id is not None:
                    start["version"] = studio.version_view()
                return self.send_json(start)
            if path == "/api/timeline":
                return self.send_json(studio.timeline())
            if path == "/api/phrasings":
                return self.send_json(studio.phrasings())
            if path.startswith("/api/job/"):
                job = self.studio.jobs.get(path.rsplit("/", 1)[-1])
                return self.send_json(self.studio.jobs.view(job)) if job else self.fail(404, "no such job")
            match = re.fullmatch(r"/export/([0-9a-f]{16,64})\.(mid|zip)", path)
            if match:  # a file for a musician's own tools (Studio.export), saved under its name
                name = parse_qs(urlsplit(self.path).query).get("name", [""])[0]
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.(mid|zip)", name):
                    name = f"song.{match.group(2)}"
                file = self.studio.cache / f"{match.group(1)}.{match.group(2)}"
                if not file.exists():
                    return self.fail(404, "not made yet")
                kind = "audio/midi" if match.group(2) == "mid" else "application/zip"
                with file.open("rb") as f:  # streamed: a song's stems are tens of megabytes
                    return self.send(f, kind, 200, {"Content-Disposition": f'attachment; filename="{name}"'})
            match = re.fullmatch(r"/audio/([0-9a-f]{16,64})\.flac", path)
            if match:
                # ?name=song.day.id.flac: saved under that name (a recording downloaded, as a visitor keeps theirs)
                name = parse_qs(urlsplit(self.path).query).get("name", [""])[0]
                name = name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.flac", name) else None
                return self.audio(self.studio.cache / f"{match.group(1)}.flac", name)
            match = re.fullmatch(r"/download/([0-9a-f]{16,64})\.flac", path)
            if match and self.studio.downloads is not None:  # a public studio's recording, while it's kept
                name = parse_qs(urlsplit(self.path).query).get("name", [""])[0]
                name = name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.flac", name) else "song.flac"
                kept = self.studio.downloads.path(match.group(1))
                if kept is None:
                    hours = self.studio.public.download_hours
                    return self.fail(404, f"This recording isn't kept here any more (the studio keeps each for "
                                          f"{hours:g} hours). Make it again from the studio: the same choices make "
                                          f"the same song.")
                return self.audio(kept, name)
            return self.fail(404, "not found")
        except Exception as e:  # said on the page rather than dropping the connection
            traceback.print_exc()
            return self.fail(500, f"{type(e).__name__}: {e}")

    def piano_page(self, path: str) -> None:
        """The piano page and its files, and the scores the studio made for it (Studio.piano), by their keys."""
        if path == "/piano":
            query = urlsplit(self.path).query
            query = query if re.fullmatch(r"[A-Za-z0-9=&%._/-]{0,300}", query) else ""
            return self.send(b"", "text/plain; charset=utf-8", 301,
                             {"Location": "/piano/" + (f"?{query}" if query else "")})
        if path in PIANO_STATIC:
            name, kind = PIANO_STATIC[path]
            return self.send((PAGE / name).read_bytes(), kind)
        match = re.fullmatch(r"/piano/score/([0-9a-f]{16,64})\.json", path)
        if match:
            file = self.studio.cache / f"{match.group(1)}.piano.json"
            if not file.exists():
                return self.fail(404, "not made, or not kept any more: open it again from the studio")
            return self.send(file.read_bytes(), "application/json")
        return self.fail(404, "not found")

    def audio(self, path: Path, name: str | None = None) -> None:
        """A rendering, with byte ranges (players seek with them; Safari won't play without); with a name,
        as a file to save."""
        if not path.exists():
            return self.fail(404, "not made yet")
        if name:
            with path.open("rb") as f:
                return self.send(f, "audio/flac", 200, {"Content-Disposition": f'attachment; filename="{name}"'})
        size = path.stat().st_size
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:
                start, end = max(0, size - int(rng.group(2))), size - 1
            if start >= size or start > end:
                return self.send(b"", "audio/flac", 416, {"Content-Range": f"bytes */{size}"})
            with path.open("rb") as f:  # just the part asked for, not the whole file each time
                f.seek(start)
                part = f.read(end + 1 - start)
            return self.send(part, "audio/flac", 206,
                             {"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
        with path.open("rb") as f:
            self.send(f, "audio/flac", 200, {"Accept-Ranges": "bytes"})

    # ------------------------------------------------------------ POST

    def do_POST(self) -> None:
        if self.studio.singing is not None and urlsplit(self.path).path == "/api/sing/take":
            return self.studio.singing.handle_take(self)  # a take is bigger than a JSON; its own guards, the same
        if urlsplit(self.path).path == "/api/open":
            return self.open_version()  # a file someone brought: every guard before a byte of it is read
        # the body first, so a refusal leaves the connection in step for the next request
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 2**20:
            self.close_connection = True
            return self.fail(413, "too much")
        raw = self.rfile.read(length) if length else b""
        # only the studio's own page: its address, JSON, and the token it was given (a header no other page
        # can send without asking first, which this server never answers)
        if not self._local():
            return self.fail(403, "this page answers only its own address")
        if not self._admitted():
            return self.fail(403, "this studio needs its link's key")
        if self.studio.public is not None and self._throttled():
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.fail(415, "send JSON")
        mine, version = self._page_token()
        if not mine:
            return self.fail(403, "this page answers only the page it gave out")
        path = urlsplit(self.path).path
        try:
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict) or not isinstance(body.get("edits") or {}, dict):
                return self.fail(400, "send a map, with the edits a map of choices")
            edits = body.get("edits") or {}
            # the studio on the version the page was opened on, if someone brought it (singing is the song's own)
            studio = self.studio if version is None or path.startswith("/api/sing") else self.studio.opened(version)
            if studio is None:
                return self.version_gone()
            by = self._by() if studio.public is not None else None
            if path == "/api/song":
                return self.send_json(studio.song(edits))
            if path == "/api/options":
                return self.send_json(studio.options(edits, str(body.get("block", "")), int(body.get("index", 0))))
            if path == "/api/keep-words":
                return self.send_json(studio.keep_words(edits))
            if path == "/api/compare":
                return self.send_json(studio.compare(edits, list(body.get("names", []))))
            if path == "/api/listen":
                section = body.get("section")
                who = str(body.get("who", "you"))
                if who not in ("you", "program") and not re.fullmatch(r"fictional:[a-z0-9 _-]{1,24}", who):
                    return self.fail(400, "no such machine")
                return self.send_json(studio.listen(edits, who, None if section is None else int(section), by=by))
            if path == "/api/cancel":
                return self.send_json({"cancelled": studio.jobs.cancel(str(body.get("job", "")),
                                                                       owner=by[0] if by else None)})
            if path == "/api/export":
                return self.send_json(studio.export(edits, str(body.get("what", "")), by=by))
            if path == "/api/record":
                return self.send_json(studio.record(edits, by=by))
            if path == "/api/piano":  # the piano page's score of this version (made at once)
                return self.send_json(studio.piano(edits))
            if path == "/api/players":  # every part in beats, for the sketch's players (MIDI out)
                return self.send_json(studio.players(edits))
            if path == "/api/notes-in":  # a take or a MIDI file, as a preview of edits (notes in)
                return self.send_json(studio.notes_in(edits, body))
            if path == "/api/open/ready":  # someone's version: would a file this size be taken now?
                refusal = self._may_open(int(body.get("size") or 0), count=False)
                return refusal() if refusal is not None else self.send_json({"ready": True})
            if path == "/api/sing":
                return self.send_json(studio.sing())
            if path.startswith("/api/sing/") and studio.singing is not None:
                return self.send_json(studio.singing.post(path, body))
            return self.fail(404, "not found")
        except Busy as e:
            return self.too_many(503, e) if self.studio.public is not None else self.fail(503, str(e))
        except public_mod.Limited as e:
            return self.too_many(429, e)
        except (ValueError, KeyError, TypeError) as e:
            return self.fail(400, str(e))
        except Exception as e:
            traceback.print_exc()
            return self.fail(500, f"{type(e).__name__}: {e}")


    # ------------------------------------------------------------ someone's version: the page's, and the file brought
    #
    # The page at /v/<id> was given the token '<token>.<id>', so every request it sends (X-Studio) says which version
    # it is about, and nothing else on the page needs to know. A file brought is guarded before a byte of it is
    # read, streamed to a folder of its own, read in a process of its own (Studio.receive) and removed.

    def _page_token(self) -> tuple[bool, str | None]:
        """The token the page sends back (X-Studio): whether it's the one this studio gave out, and the version
        the page was opened on, if someone brought it."""
        token, _, version = self.headers.get("X-Studio", "").partition(".")
        mine = secrets.compare_digest(token.encode("utf-8", "replace"), self.studio.token.encode())
        return mine, version or None

    def _asked(self) -> Studio | None:
        """For the page's questions that change nothing (GET /api/start...): the studio on the version its token
        names, or this one; None for a version that isn't kept here."""
        mine, version = self._page_token()
        return self.studio.opened(version) if mine and version is not None else self.studio

    def version_gone(self) -> None:
        """A version that isn't kept here: never saying whether it ever was."""
        days = self.studio.versions.days
        why = (f"This version isn't kept here (any more): a version someone opens is kept {days:g} days after it "
               "was last opened. Open its file again to continue from it.")
        if not urlsplit(self.path).path.startswith("/v/"):
            return self.fail(404, why)
        page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                "<title>Songbird studio</title><body style='font:17px/1.5 Georgia,serif;max-width:34em;"
                "margin:12vh auto;padding:0 16px'><h1 style='font-weight:500'>This version isn't here</h1>"
                f"<p>{why}</p><p><a href='/'>Open the studio on the song as it began</a></p></body>")
        self.send(page.encode(), "text/html; charset=utf-8", 404)

    def open_version(self) -> None:
        """POST /api/open: a rendition's FLAC, as the body. Refused before a byte of it is read unless it comes
        from this studio's own page (its address, its key, its token), within the limits and the size; then
        written to a folder of its own, read as data, never run (Studio.receive), and removed whatever happens."""
        studio = self.studio
        self.close_connection = True  # the body may go unread, so the connection isn't used again
        try:
            length = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            length = -1
        refusal = self._may_open(length, count=True)
        where = public_mod.network(self._ip())
        if refusal is None:
            with studio._arriving_lock:
                if where in studio.arriving or len(studio.arriving) >= ARRIVING:
                    refusal = self._busy
                else:
                    studio.arriving.add(where)
        if refusal is not None:
            refusal()
            return self._linger(length)
        folder = Path(tempfile.mkdtemp(prefix="open-", dir=studio.incoming))
        try:
            path = folder / "brought.flac"
            self._arrive(path, length)
            if not studio.reading.acquire(timeout=90):
                return self.too_many(503, Busy("The studio is reading other files; send it again in a moment.", 30))
            try:
                answer = studio.receive(path)
            finally:
                studio.reading.release()
        except received.Refused as e:
            return self.fail(422, str(e))
        except (TimeoutError, ConnectionError):
            return None  # the sender went quiet, or away: no one to answer
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            with studio._arriving_lock:
                studio.arriving.discard(where)
        return self.send_json(answer)

    def _may_open(self, length: int, count: bool) -> Callable[[], None] | None:
        """Why a file of `length` bytes can't be brought now, as the reply that says so; None if it can. `count`:
        the file itself, counted (a request, and one of the hour's opens); or the page asking first
        (/api/open/ready, before it sends a file that would only be turned away)."""
        studio = self.studio
        if not self._local():
            return lambda: self.fail(403, "this page answers only its own address")
        if not self._admitted():
            return lambda: self.fail(403, "this studio needs its link's key")
        if not self._page_token()[0]:
            return lambda: self.fail(403, "this page answers only the page it gave out")
        if length <= 0:
            return lambda: self.fail(411, "Send the file whole, with its length.")
        if length > studio.upload_limit:
            return lambda: self.fail(413, f"It's {length / 2**20:.0f} MB; a rendition is about 15 to 20 (the most "
                                          f"taken here is {studio.upload_limit // 2**20} MB).")
        if studio.gate is not None:
            try:
                if count:
                    studio.gate.request(self._ip())
                studio.gate.render("opens", *self._by(), count=count)
            except public_mod.Limited as e:
                return lambda limited=e: self.too_many(429, limited)
        with studio._arriving_lock:
            if public_mod.network(self._ip()) in studio.arriving or len(studio.arriving) >= ARRIVING:
                return self._busy
        return None

    def _busy(self) -> None:
        self.too_many(503, Busy("A file is on its way here from you already, or several from others; send it "
                                "again in a moment.", 30))

    def _linger(self, length: int) -> None:
        """After a refusal, a small body read and dropped, so the answer isn't lost to the connection's reset (a
        large one is never read: the page asks first, /api/open/ready)."""
        if 0 < length <= 2**16:
            with contextlib.suppress(OSError, ValueError):
                self.connection.settimeout(2)
                self.rfile.read(length)

    def _arrive(self, path: Path, length: int) -> None:
        """The body, `length` bytes, streamed to `path`: whole, and no slower than a slow connection sends
        (a minute, and a second for every 32 KB), or refused."""
        deadline = time.monotonic() + 60 + length / (32 * 1024)
        left = length
        with path.open("wb") as f:
            while left:
                chunk = self.rfile.read(min(left, 2**16))
                if not chunk:
                    raise received.Refused("The file didn't arrive whole; send it again.")
                f.write(chunk)
                left -= len(chunk)
                if time.monotonic() > deadline:
                    raise received.Refused("The file came too slowly to take; send it again on a faster connection.")


ARRIVING = 4  # files on their way at once, for everyone (one from each address)


class Server(ThreadingHTTPServer):
    request_queue_size = 128  # the page asks for several things at once, and a player many ranges
    daemon_threads = True
    slots: threading.BoundedSemaphore | None = None  # a public studio's connections at once

    def process_request(self, request, client_address) -> None:
        if self.slots is not None and not self.slots.acquire(blocking=False):
            self.shutdown_request(request)  # as many as it serves at once already: this one is turned away
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            if self.slots is not None:
                self.slots.release()

    def handle_error(self, request, client_address) -> None:
        """A browser closing a connection it kept open (a player seeking, a tab closing) is no error."""
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class Server6(Server):
    address_family = socket.AF_INET6


def serve(studio: Studio, port: int = PORT, tries: int = 20, host: str = HOST,
          names: tuple[str, ...] | list[str] = (), client_ip_header: str | None = None) -> ThreadingHTTPServer:
    """A server for the studio on `host` (127.0.0.1: this computer only, unless it is shared), on the port
    asked for or the next free one; answering to its own names and, shared, to `names`. Public, behind a
    proxy: the visitor's address from `client_ip_header`."""
    names = tuple(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    kind = Server6 if ":" in host else Server
    attrs = {"studio": studio, "names": names}
    if studio.public is not None:  # a connection that sends nothing for this long is closed
        attrs |= {"timeout": studio.public.timeout, "client_ip_header": client_ip_header, "log": sys.stdout}
    for p in range(port, port + tries):
        handler = type("StudioHandler", (Handler,), attrs | {"port": p})
        try:
            server = kind((host, p), handler)
        except OSError:
            continue
        if studio.public is not None:
            server.slots = threading.BoundedSemaphore(studio.public.connections)
        return server
    raise SystemExit(f"songbird studio: no free port from {port} to {port + tries - 1} on {host}")


def addresses() -> list[str]:
    """This computer's addresses on its networks (IPv4, not loopback): where people nearby reach it."""
    found = []
    with contextlib.suppress(OSError):
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    for probe in ("192.168.0.1", "10.0.0.1", "8.8.8.8"):  # a UDP "connect" sends nothing: it only picks a route
        with contextlib.suppress(OSError), contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as s:
            s.connect((probe, 9))
            found.append(s.getsockname()[0])
    return list(dict.fromkeys(a for a in found if not a.startswith("127.") and a != "0.0.0.0"))


def share_names(host: str, allow: list[str] | None) -> list[str]:
    """The names a shared studio answers to besides 127.0.0.1: the ones given (a tunnel's), the address it
    is bound to, and, bound to every network (0.0.0.0 or ::), this computer's addresses and its name (and
    NAME.local for a bare name, as Bonjour has it). Empty: this computer's alone."""
    names = [a.strip().lower() for a in allow or [] if a.strip()]
    if host in ("0.0.0.0", "::"):
        name = socket.gethostname().lower()
        names += addresses() + [name] + ([f"{name}.local"] if "." not in name else [])
    elif host.lower() not in LOOPBACK:
        names.append(f"[{host.lower()}]" if ":" in host else host.lower())
    return list(dict.fromkeys(names))


def links(host: str, port: int, allow: list[str], names: list[str], key: str | None) -> tuple[list[str], str]:
    """Where visitors open a shared studio (a tunnel's name by https, without a port; this computer's by
    http at its port), and where the person serving it does. A public studio without a key: bare links."""
    q = f"/?key={key}" if key else "/"
    given = [a.strip().lower() for a in allow or [] if a.strip()]
    out = [f"https://{'NAME-THE-TUNNEL-PRINTED' if n.startswith('.') else ''}{n}{q}" for n in given]
    out += [f"http://{n}:{port}{q}" for n in names if n not in given]
    here = f"http://127.0.0.1:{port}{q}" if host in ("0.0.0.0", "::") or host.lower() in LOOPBACK \
        else (out[-1] if out else f"http://127.0.0.1:{port}{q}")
    return out, here


def shared_warning(shares: list[str], out: str, lan: bool) -> str:
    """What sharing the studio means, said in the terminal when it starts."""
    lock = ("The key in the link is the only lock, and on this network the link travels as plain http: send it "
            "only to the people you mean to invite. Beyond your network, use a tunnel (docs/STUDIO.md)." if lan else
            "The key in the link is the only lock: send it only to the people you mean to invite.")
    points = ["Visitors hear, change and record the song with this computer's time. One song is made at a time, "
              "so they wait on each other: a section takes seconds, a whole song about a minute.",
              f"What they record is saved into {out}/ here, and each can download theirs from the page.",
              "Their version is shaped by this computer (its languages, size and screen), not by theirs.",
              lock, "The singing page is off, and no singer's name or own way of singing is offered."]
    return "\n".join(["  SHARED, for a short preview. Anyone with one of these links can use the studio, on this "
                      "computer:", *(f"    {link}" for link in shares), "  What that means:",
                      *(textwrap.fill(point, 104, initial_indent="    - ", subsequent_indent="      ")
                        for point in points), "  Stop it with Ctrl-C when the preview is over."])


def public_warning(shares: list[str], limits: public_mod.Limits, key: str | None, machine: str,
                   singing: bool = False) -> str:
    """What opening the studio to the public means, said when it starts."""
    points = [("Anyone who reaches it can use it" if key is None else "Anyone with the key can use it")
              + f"; the song is shaped by the machine '{machine}' for everyone.",
              f"One song is made at a time: {limits.queue} may wait; each visitor has one at a time, "
              f"{limits.records} whole songs and {limits.previews} sections an hour ({limits.records_ip} and "
              f"{limits.previews_ip} for an address), {limits.requests} requests a minute from an address.",
              f"Recordings aren't kept here: each is offered for download for {limits.download_hours:g} hours "
              f"(up to {limits.downloads_mb} MB); previews are cached up to {limits.cache_mb} MB.",
              "Each request is logged on one line (when, what, the answer), never by whom; visitors are counted "
              "under a key kept only in memory.",
              "Singing in the browser is on (below)." if singing else "Singing is off: start with --web-singing to take it."]
    return "\n".join(["  PUBLIC. Open at:", *(f"    {link}" for link in shares), "  What that means:",
                      *(textwrap.fill(point, 104, initial_indent="    - ", subsequent_indent="      ")
                        for point in points)])


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("parent", nargs="?",
                        help="the rendition to make a new version of: a seed packet, a FLAC with its record "
                             "beside it, or a record (.json); default: the packet this program came in, else "
                             "the song as it began")
    parser.add_argument("--packet", metavar="FILE",
                        help="the packet this program came in (the file's own bootstrap passes it): the rendition "
                             "to open, as the parent of the new version")
    parser.add_argument("--song", metavar="GENOME", help="the song's genome, where the parent doesn't carry it")
    parser.add_argument("--machine", metavar="here|none|fictional:NAME|FILE",
                        help="who sings: this machine (the default; public, none), none, a made-up one, or a "
                             "voice file or record")
    parser.add_argument("--port", type=int, default=PORT, help=f"the port (default {PORT}, or the next free one)")
    parser.add_argument("--out", metavar="DIR", help="where recordings go (default renders/)")
    parser.add_argument("--no-open", action="store_true", help="don't open the page in a browser")
    parser.add_argument("--host", default=HOST, metavar="ADDRESS",
                        help="where to serve it: 127.0.0.1, this computer only (the default); 0.0.0.0 for "
                             "people on this computer's networks, as a short preview (it prints links with a "
                             "key; docs/STUDIO.md)")
    parser.add_argument("--allow-host", action="append", default=[], metavar="NAME",
                        help="a name visitors reach it by through a tunnel (a leading dot allows every name "
                             "under it: .trycloudflare.com); shares it by link, as --host does")
    parser.add_argument("--key", metavar="WORD",
                        help="the key a shared studio's links carry (default: a new one each time it starts; "
                             "public, none)")
    parser.add_argument("--public", action="store_true",
                        help="open to anyone who reaches it, for good, with limits for each visitor: no link key "
                             "needed (unless --key), recordings offered for download and not kept, an access "
                             "log that never says who (docs/WEB-STUDIO.md)")
    parser.add_argument("--limit", action="append", default=[], metavar="NAME=N",
                        help=f"a public studio's limit: {', '.join(public_mod.names())} (docs/WEB-STUDIO.md)")
    parser.add_argument("--client-ip-header", metavar="HEADER",
                        help="public, behind a proxy on this machine or its private network: the header that "
                             "names the visitor's address (CF-Connecting-IP for a Cloudflare tunnel)")
    parser.add_argument("--web-singing", action="store_true",
                        help="take singing in the browser, measured here and its audio deleted (a checkout with the "
                             "dev tools and a singing kit: docs/WEB-SINGING.md)")
    parser.add_argument("--sing-kit", metavar="DIR",
                        help="the singing kit, made by python -m webstudio.prepare (default $SONGBIRD_SING_KIT, else "
                             "renders/sing-kit)")


def run(args: argparse.Namespace) -> int:
    parent = args.packet or args.parent or os.environ.get("SONGBIRD_PACKET") or None
    host = getattr(args, "host", HOST) or HOST
    allow = getattr(args, "allow_host", []) or []
    for name in allow:
        if not re.fullmatch(r"\.?[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", name.strip()):
            raise SystemExit(f"songbird studio: --allow-host takes a name like songbird.example.com, not {name!r}")
    names = share_names(host, allow)
    limits = None
    if getattr(args, "public", False):
        try:
            limits = public_mod.Limits.parse(getattr(args, "limit", []))
        except ValueError as e:
            raise SystemExit(f"songbird studio: {e}") from None
    elif getattr(args, "limit", []) or getattr(args, "client_ip_header", None):
        raise SystemExit("songbird studio: --limit and --client-ip-header are for a public studio (--public)")
    header = getattr(args, "client_ip_header", None)
    if header and not re.fullmatch(r"[A-Za-z0-9-]{1,64}", header):
        raise SystemExit("songbird studio: --client-ip-header takes a header's name, like CF-Connecting-IP")
    shared = limits is not None or bool(names) or host.lower() not in LOOPBACK
    key = None
    if shared:
        key = getattr(args, "key", None) or (None if limits else secrets.token_urlsafe(9))
        if key is not None and not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", key):
            raise SystemExit("songbird studio: --key takes 8 to 64 letters, digits, - or _")
    machine = args.machine or ("none" if limits else "here")  # public: never the serving computer's own
    studio = Studio(parent, args.song, machine, Path(args.out) if args.out else None, key=key, public=limits)
    if getattr(args, "web_singing", False):
        studio.enable_web_singing(getattr(args, "sing_kit", None), check=True)
    server = serve(studio, args.port, host=host, names=names, client_ip_header=header)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    print(f"Songbird studio: {studio.genome.title}, {studio.context.opening()}", flush=True)
    if limits:
        shares, url = links(host, port, allow, names, key)
        print(public_warning(shares or [url], limits, key, machine, singing=studio.singing is not None), flush=True)
    elif shared:
        shares, url = links(host, port, allow, names, key)
        print(shared_warning(shares, studio.out_shown(), lan=any(link.startswith("http://") for link in shares)))
    if studio.singing is not None:
        why = studio.singing.why_not()
        print("  Singing in the browser: " + (why or "on. Each take is measured here and its audio deleted at once; "
                                              "only numbers stay (docs/WEB-SINGING.md)."), flush=True)
    print(f"  open {url}  (Ctrl-C to stop)", flush=True)
    threading.Thread(target=studio.timeline, daemon=True).start()  # ready by the time it's scrolled to
    studio.warm()
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        studio.close()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="songbird studio", description=__doc__.split("\n\n")[0])
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
