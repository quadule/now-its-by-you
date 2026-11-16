"""The studio: see how your version of the song was made, change it if you like, and export it.

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
docs/history/web-studio-server-plan.md.
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
import struct
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
from dataclasses import dataclass, field, replace as dataclass_replace
from datetime import date
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

import numpy as np

from . import RECORD_FORMAT, artwork, drift as drift_mod, explain, genome as genome_mod, harvest, midi, pack, stage, synth
from . import clips, public as public_mod, received, stems as stems_mod
from .realize import Params
from .synth import master
from .synth.instruments import INSTRUMENTS
from .synth.mixing import MixParams

PAGE = Path(__file__).with_name("studio")  # index.html, score.css, studio.js
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
# the score (docs/notes/STUDIO-REDESIGN.md): one page, three views, one inspector (index.html)
STATIC["/renderer.js"] = ("renderer.js", "text/javascript; charset=utf-8")  # previews and recordings, one interface
STATIC["/model.js"] = ("model.js", "text/javascript; charset=utf-8")
STATIC["/parts.js"] = ("parts.js", "text/javascript; charset=utf-8")
STATIC["/drums.js"] = ("drums.js", "text/javascript; charset=utf-8")  # a percussion player's step grid
STATIC["/drums.css"] = ("drums.css", "text/css; charset=utf-8")
STATIC["/score.js"] = ("score.js", "text/javascript; charset=utf-8")
STATIC["/score.css"] = ("score.css", "text/css; charset=utf-8")
PAGES = {"": "index.html", "/index.html": "index.html"}


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
                if json.loads(path.read_text(encoding="utf-8")).get("title") == record["title"]:
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


def today(clock: Callable[[], date] = date.today) -> tuple[str, float]:
    """Today's date on this computer, and the instant the studio sings it: noon UTC that day, as
    `songbird render --date YYYY-MM-DD` has it, so the same machine opens on the same version all day."""
    day = clock().isoformat()
    return day, drift_mod.parse(day)


# ---------------------------------------------------------------- previews


def spans(score, form, bars=None) -> list[tuple[str, float, float]]:
    """Each section of the form and when it plays: the score's spans, with a run of sections of one
    name (verse, verse), which the score keeps as one, shared out evenly (they have the same phrases), or by
    their bars where a person made them different lengths (songbird.takeover)."""
    out: list[tuple[str, float, float]] = []
    k = 0
    for name, a, b in score.sections:
        run = 1
        while k + run < len(form) and form[k + run] == name:
            run += 1
        weights = [1.0] * run if bars is None else [float(x) for x in bars[k:k + run]]
        total, done = sum(weights), 0.0
        for j in range(run):
            out.append((name, a + (b - a) * done / total, a + (b - a) * (done + weights[j]) / total))
            done += weights[j]
        k += run
    return out


def window(genome, params: Params, score, form, index: int) -> tuple[float, float]:
    """Where a section's preview starts and ends: from a breath before its first pickup (a beat of the band
    before it at least) to where the next section's pickup begins."""
    from .clips import resolved
    from .takeover import arranged, phrase_plan

    genome, params, _ = resolved(genome, params)  # a person's clips, as one song: their sections (songbird.clips)
    if genome.clips is not None:
        form = params.form
    lined = phrase_plan(genome, params)  # each section's lines, as long as a person made it
    bars = [sum(genome.phrases[pid].bars for pid, _ in lines) for lines in lined] \
        if arranged(params) or genome.clips is not None else None
    parts = spans(score, form, bars)
    _, s0, s1 = parts[index]
    unit = 60.0 / params.tempo / genome.meter.beat

    def pickup(k: int) -> float:
        return genome.phrases[lined[k][0][0]].pickup * unit

    t0 = max(0.0, s0 - max(pickup(index), genome.meter.beat * unit) - 0.5)
    t1 = parts[index + 1][1] - pickup(index + 1) - 0.5 * unit if index + 1 < len(parts) else s1
    return t0, max(t1, s0 + unit)


def bar_seconds(genome, params: Params) -> list[float]:
    """Where each bar line of the score's ruler falls in the whole song's audio, in seconds (bar 1's first, the
    song's last bar line last), by the rendition's own clock (realize.timeline: its preroll and any count-in, a slow
    air, the final ritardando): the page starts the whole song at its playhead's bar with them."""
    from .realize import timeline

    clock, bar = timeline(genome, params), genome.meter.bar
    return [round(clock.seconds(clock.lead + k * bar), 3) for k in range((clock.end - clock.lead) // bar + 1)]


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
        if (n.part in ("voice", "chop") or n.part.startswith("choir")) and n.start < t0:  # (a chop sung too)
            continue
        if n.start < start:
            n = dc_replace(n, dur=n.start + n.dur - start, start=start)
        notes.append(dc_replace(n, start=n.start - start))
    moved = {}
    if getattr(score, "sound", None):  # a person's key track and transitions move with the notes (songbird.sound)
        from .sound import shifted

        moved = {"sound": shifted(score.sound, start, t1)}
    if getattr(score, "stage", None):  # a stage edition's plan moves with the notes (songbird.stage)
        from .stage import shifted

        moved["stage"] = shifted(score.stage, start, t0, t1, cut)
    return dc_replace(score, notes=tuple(notes), duration=(t1 - start) + tail,
                      sections=tuple((s, max(0.0, a - start), b - start) for s, a, b in score.sections
                                     if b > start and a < t1), **moved), t0 - start


def faded(x: np.ndarray, sr: int, skip: float, fade_in: float = 0.25, fade_out: float = 1.5,
          inplace: bool = False) -> np.ndarray:
    """The preview from where the section starts, faded in and out. inplace: reuse an owned float64 mix."""
    y = x[int(skip * sr):]
    if not inplace or y.dtype != np.float64:
        y = y.copy()
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
    where: str | None = None  # ... and their address (public.network: an IPv6 one by its /64)
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

    def __init__(self, waiting: int | None = None, fair: bool = False, per_address: int | None = None,
                 thread: bool = True):
        self.lock = threading.Condition()
        self.per_address = per_address  # renders waiting at once from one address (a public studio), or no limit
        self.pending: list[Job] = []
        self.jobs: dict[str, Job] = {}
        self.by_key: dict[str, Job] = {}
        self.waiting = waiting or MAX_WAITING
        self.fair = fair
        self.took = {True: 90.0, False: 15.0, "measure": 30.0}  # seconds a whole song, a section and a sung take take:
        # guesses, then measured (each its own, so measuring takes never skews the renders' estimate)
        if thread:  # (a studio on the visitor's device has none: it makes a job between requests, _work)
            threading.Thread(target=self._run, daemon=True, name="studio-renderer").start()

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def live(self, key: str) -> Job | None:
        job = self.by_key.get(key)
        return job if job is not None and job.state in ("queued", "running") else None

    def submit(self, key: str, kind: str, label: str, work: Callable, then: Callable | None = None,
               owner: str | None = None, whole: bool = False, admit: Callable | None = None,
               where: str | None = None) -> Job:
        """A render, or the same one already asked for. `owner` (a public studio's visitor) may have one
        at a time, and `where` (their address) `per_address` waiting at once, however many visitors it holds
        (a visitor without a cookie is a new one each time); `admit`, a public studio's count of what each visitor
        has had made, runs once the queue has room, and may refuse (public.Limited)."""
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
            if where is not None and self.per_address is not None:
                theirs = [j for j in self.pending if j.where == where]
                if len(theirs) >= self.per_address:
                    raise public_mod.Limited(f"Your network has {len(theirs)} songs waiting to be made already, as "
                                             "many as one address may while everyone shares one renderer; ask again "
                                             "when one is done.", self._eta(theirs[:1]))
            if admit is not None:
                admit()
            job = Job(secrets.token_hex(6), key, kind, label, work, then=[then] if then else [], owner=owner,
                      whole=whole, where=where)
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

    def one_each(self, owner: str) -> None:
        """Whether this visitor may ask for something now (public.Limited if not), changing nothing: asked before
        a take is read."""
        with self.lock:
            self._one_each(owner, drop=False)

    def _one_each(self, owner: str, drop: bool = True) -> None:
        """A visitor's render at a time: a preview of theirs still waiting gives way to what they ask for
        now; one being made, or a recording waiting, is waited for."""
        for job in list(self.pending):
            if job.owner == owner:
                if job.kind != "preview":
                    what = "Your singing is waiting to be measured" if job.kind == "measure" else \
                        "Your recording is waiting its turn"
                    raise public_mod.Limited(f"{what}; the next can be asked for when it's done.", self._eta([job]))
                if drop:
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
            self._work(job)

    def _work(self, job: Job) -> None:
        """One job made, and what follows it; its result or its failure kept on it. (_run's, one at a time; a
        studio on the visitor's device, which can't start threads, calls it between requests.)"""
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
        # the program itself, not its version number (which changes only at a release), so an updated program never plays
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
                quiet = cached is None or bool(json.loads(harvest.cache_path().read_text(encoding="utf-8")).get("quiet"))
        self.machine = machine
        self.voice = harvest.machine_voice(machine)
        self.day, self.t = today(self.clock)
        # a checkout records into renders/; a packet's program, into the folder it was run from
        self.out = Path(out) if out else (Path.cwd() if self.where == "packet" else Path("renders"))
        self.jobs = Jobs(public.queue, fair=True, per_address=public.queue_ip) if public else Jobs(thread=self.threads)
        self.cache_limit = public.cache_mb * 2**20 if public else CACHE_LIMIT
        from .synth.cache import StemCache

        self._stem_cache = StemCache(64 * 2**20)
        # a public studio's counts of what each visitor has had made, and its recordings waiting to be downloaded
        self.gate = public_mod.Gate(public) if public else None
        self.downloads = public_mod.Downloads(self.home / "downloads", public.downloads_mb * 2**20,
                                              public.download_hours) if public else None
        self.token = secrets.token_urlsafe(18)
        self._timeline = None
        self._timeline_lock = threading.Lock()
        self._roll_lock = threading.Lock()
        self._serving: collections.Counter = collections.Counter()  # requests being served, by address (public)
        self._serving_lock = threading.Lock()
        self.karaoke: subprocess.Popen | None = None
        self.singing = None  # singing in the browser, when asked for (enable_web_singing)
        self.context = explain.Context(self.genome, parent_params, record, self.voice, machine, self.day, self.t,
                                       quiet, shared=self.shared)
        self._versions_setup(public)
        prune(self.cache, self.cache_limit)
        if public:
            threading.Thread(target=self._tidy, daemon=True, name="studio-tidy").start()

    # ------------------------------------------------------------ the day

    clock: Callable[[], date] = staticmethod(date.today)  # this computer's date (a test's fake clock)
    threads = True  # its render queue runs in a thread of its own (not on the visitor's device: Pyodide has none)

    def roll(self) -> bool:
        """A public studio's day moved on at this computer's midnight, as it would be if it were started then: the
        machine sings the new day's version and a recording is stamped with it (a studio running for weeks would
        otherwise sing its first day for good). Asked at every request; True if it moved. What was asked before
        keeps the day it was asked on: a render's job holds its version (and its record the day it was sung), and
        a request under way its studio. The page's timeline is worked out again, and each version someone brought
        is opened again on the new day. A local studio keeps the day it was started on, as ever."""
        if self.public is None:
            return False
        day = self.clock().isoformat()
        if day == self.day:
            return False
        with self._roll_lock:
            if day == self.day:
                return False
            t = drift_mod.parse(day)
            context = dataclass_replace(self.context, day=day, t=t)
            with self._timeline_lock:
                self.context, self.t, self._timeline = context, t, None
                self.day = day
            with self._opened_lock:
                self._opened.clear()
        return True

    # ------------------------------------------------------------ the song

    def version(self, edits: dict | None = None, who: str = "you") -> explain.Version:
        """The rendition as the page has it: made by the machine on the day asked, with the edits on top.
        "program": the same day as the program would sing it (the edits aside); another machine: its own
        version that day."""
        edits = dict(edits or {})
        day = {"date": edits["date"]} if "date" in edits else {}
        target_edits = day if (who == "program" or who.startswith("fictional:")) else edits
        cache = getattr(self, "_version_cache", None)
        if cache is None:
            cache = self._version_cache = collections.OrderedDict()
        perf = (self.context.parent_record or {}).get("performance")
        cache_key = None
        if "phrasing" not in target_edits:
            cache_key = (id(self.context), self.day, self.t, id(perf),
                         json.dumps(perf, sort_keys=True, default=str) if perf else "",
                         who, json.dumps(target_edits, sort_keys=True, default=str))
            hit = cache.get(cache_key)
            if hit is not None:
                cache.move_to_end(cache_key)
                return hit
        if who == "program":
            v = self.context.version(day, phrasings=self.phrasing_choices())
        elif who.startswith("fictional:"):
            v = self.context.version(day, voice=harvest.fictional(who.split(":", 1)[1]))
        else:
            v = self.context.version(edits, phrasings=self.phrasing_choices())
        if cache_key is not None:
            cache[cache_key] = v
            while len(cache) > 16:
                cache.popitem(last=False)
        return v

    def start_view(self) -> dict:
        """What the page asks once (GET /api/start): the song, the machine, the bounds of every choice, what's
        available; and for an open studio its limits, the largest file it takes, and the version it is on."""
        start = explain.start(self.context, self)
        if self.public is not None:
            start["public"] = self.public.view()
        start["open"] = {"upload_mb": self.upload_limit // 2**20}
        if self.version_id is not None:
            start["version"] = self.version_view()
        return start

    def song(self, edits: dict) -> dict:
        v = self.version(edits)
        view = explain.view(self.context, v, self.phrasings() + self.sung_phrasings(edits))
        view["listen"] = self.listen_keys(v)
        return view

    def options(self, edits: dict, block: str, index: int) -> dict:
        return explain.word_options(self.context, self.version(edits), block, index)

    def clips(self, edits: dict, body: dict) -> dict:
        """An operation on the version's clips (docs/notes/STUDIO-CLIPS.md, "For the editor"): the whole edits map
        it leaves, and the clip it made."""
        v = self.version(edits)
        return clips.operate(self.genome, v.params, v.lyrics, edits, {k: x for k, x in body.items() if k != "edits"})

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

    def name_of(self, v: explain.Version) -> str | None:
        """The version's own title (a person's, else its parent's), or None when it goes by the song's."""
        return explain.version_name_of(self.context, v)

    def key(self, v: explain.Version, section: int | None) -> str:
        """What a render depends on, hashed: the same rendition and section are made once."""
        choir = v.choir_phrasings
        tag = (self.program_digest, self.song_digest, self.version_id, choir)
        kcache = getattr(v, "_key_cache", None)
        if kcache is None or kcache[0] != tag:
            base = {"program": self.program_digest, "song": self.song_digest, "params": v.params.to_dict(),
                    "lyrics": v.lyrics.to_dict() if v.lyrics else None, "phrasing": v.phrasing_json,
                    "choir_phrasings": choir,
                    "voice": v.voice.to_dict() if v.voice is not None else None,
                    "drift": v.drift.to_dict() if v.drift is not None else None,
                    "gain": PREVIEW_GAIN_DB}
            if self.version_id is not None:  # someone's version: its lineage sings the choir and names the parent
                base["parent"] = self.version_id
            kcache = v._key_cache = (tag, base, {})
        _, base, keys = kcache
        if section not in keys:
            material = {**base, "section": section, "marks": v.marks if section is None else None}
            keys[section] = hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:24]
        return keys[section]

    def listen_keys(self, v: explain.Version) -> dict:
        keys = {"whole": self.key(v, None), "sections": [self.key(v, k) for k in range(len(clips.sung_form(v.params)))]}
        keys["ready"] = [k for k in [keys["whole"], *keys["sections"]] if (self.cache / f"{k}.flac").exists()]
        return keys

    def listen(self, edits: dict, who: str, section: int | None, by: tuple[str, str] | None = None) -> dict:
        """A preview (a section, or the whole song) made or on its way. `by`: the visitor and address asking,
        in a public studio, for its limits."""
        v = self.version(edits, who)
        if section is not None and not 0 <= section < len(clips.sung_form(v.params)):
            raise ValueError("no such section")
        key = self.key(v, section)
        label = explain.listen_label(self.context, v, section, who)
        flac = self.cache / f"{key}.flac"
        if flac.exists():
            os.utime(flac)
            done = {"state": "done", "url": f"/audio/{key}.flac", "label": label, "progress": 1.0, "key": key}
            if section is None:  # as a whole song's job ends (_whole)
                done["result"] = {"bar_seconds": bar_seconds(self.genome, v.params)}
            return done
        if section is None:
            self.check_whole(v)
            job = self.jobs.submit(key, "preview", label, lambda job: self._whole(job, v, key),
                                   **self._limits(by, whole=True))
        else:
            job = self.jobs.submit(key, "preview", label, lambda job: self._section(job, v, key, section),
                                   **self._limits(by, whole=False))
        return self.jobs.view(job) | {"key": key}

    # ---- a whole song's memory (a public studio): a render past the container's memory would kill the studio, and
    # its queue with it, so a whole song estimated past it (public.render_mb: its length and its players) is refused
    # before it's queued, with a sentence; a browser makes it instead where one can (render_spec)

    def whole_cost(self, v: explain.Version) -> tuple[float, set[str]]:
        """A whole render of this version: its length (seconds, laid out as it would be sung) and its parts."""
        score = self._score(v)
        return score.duration, {n.part for n in score.notes}

    def fits_here(self, seconds: float, parts: set[str], stems: bool = False) -> tuple[bool, float]:
        """Whether this server makes a whole song this long with these parts within its budget (render_mb, on its
        threads), and the longest it would make with them (seconds)."""
        from .synth.threads import workers

        threads = workers()
        mb = public_mod.render_mb(seconds, parts, threads, stems)
        per_second = public_mod.render_mb(1.0, parts, threads, stems) - public_mod.BASE_MB
        return mb <= self.public.render_mb, (self.public.render_mb - public_mod.BASE_MB) / per_second

    @staticmethod
    def fits_browser(seconds: float, parts: set[str]) -> bool:
        """Whether a browser makes a whole song this long with these parts (its heap kept under BROWSER_MB)."""
        return public_mod.BROWSER_FACTOR * public_mod.render_mb(seconds, parts) <= public_mod.BROWSER_MB

    def most_minutes(self) -> float | None:
        """The longest whole song made for a visitor somewhere (this server, or a browser where the studio serves the
        bundle), with the lightest band: received.MINUTES for a public studio (a version someone brings is refused
        if its child would be longer). None for a local studio, which makes what it's asked."""
        if self.public is None:
            return None
        browser = public_mod.BROWSER_MB / public_mod.BROWSER_FACTOR if self.browser is not None else 0.0
        most = max(float(self.public.render_mb), browser)
        return min(received.MINUTES, (most - public_mod.BASE_MB) / min(public_mod.RATES.values()) / 60)

    def check_whole(self, v: explain.Version, stems: bool = False) -> None:
        """A public studio's whole render (or its stems), refused before it's queued (public.TooLong, saying why and
        what to do) if it wouldn't fit in the studio's memory; nothing for a local studio."""
        if self.public is None:
            return
        seconds, parts = self.whole_cost(v)
        fits, most = self.fits_here(seconds, parts, stems)
        if not fits:
            browser = None if stems or self.browser is None else self.fits_browser(seconds, parts)
            raise public_mod.TooLong(public_mod.too_long(seconds, most, browser))

    def _limits(self, by: tuple[str, str] | None, whole: bool) -> dict:
        """What the queue needs to hold a public studio's visitor to its limits (nothing for anyone else)."""
        if self.gate is None or by is None:
            return {"whole": whole}
        visitor, ip = by
        return {"whole": whole, "owner": visitor, "where": public_mod.network(ip),
                "admit": lambda: self.gate.render("records" if whole else "previews", visitor, ip)}

    def warm(self) -> None:
        """Make today's first verse while the page opens: the synthesis is compiled the first time it runs
        (10 to 15 s), so the first thing a person asks to hear doesn't wait for that, and it's ready."""
        v = self.version({})
        song, sung, _ = clips.resolved(self.genome, v.params)  # (a person's clips: their sections)
        first = next((k for k, name in enumerate(sung.form) if song.section(name).lyrics), 0)
        self.listen({}, "you", first)

    def _score_and_heard(self, v: explain.Version) -> tuple[object, dict]:
        from . import band as band_mod, phrasing as phrasing_mod, realize as realize_mod

        cached = getattr(v, "_score_cache", None)
        if cached is not None and cached[0] is realize_mod.realize:
            return cached[1], cached[2]
        phrasing = phrasing_mod.from_json(v.phrasing_json) if v.phrasing_json else None
        choir = [phrasing_mod.from_json(ph) for ph in v.choir_phrasings]
        with band_mod.overheard() as heard:
            score = stage.laid(self.genome, v.params, phrasing=phrasing, choir=choir, lyrics=v.lyrics)  # (as cli.render_one)
        v._score_cache = (realize_mod.realize, score, heard)
        return score, heard

    def _score(self, v: explain.Version):
        return self._score_and_heard(v)[0]

    def _section(self, job: Job, v: explain.Version, key: str, index: int) -> dict:
        """A preview of one section: cut from the whole rendition's score, made, and brought up by the gain a
        whole rendition gets in mastering (so a quiet verse stays quiet), under the same ceiling."""
        from .cli import choir_of

        job.stage = stage_words("score")
        score = self._score(v)
        t0, t1 = window(self.genome, v.params, score, v.params.form, index)  # (a person's clips: their sections)
        part, lead_in = cut(score, t0, t1)
        job.plan = stages(part)
        singer = explain.singer_of(v.params)
        ancestors = choir_of(self.parent_record, singer)[1]  # the earlier versions sing its choir, as they will
        mix = synth.render(part, seed=v.params.seed, voice=singer, mix_params=MixParams.from_dict(v.params.mix or {}),
                           ancestors=ancestors, progress=job.report, cache=self._stem_cache)
        job.report("master")
        ceiling = master.CEILING_DB - master.MARGIN_DB
        mix *= 10.0 ** (PREVIEW_GAIN_DB / 20.0)
        loud = master.limit(master.clip(mix, ceiling, inplace=True), synth.SR, ceiling, inplace=True)
        del mix
        loud = faded(loud, synth.SR, lead_in, inplace=True)
        pcm = master.to_pcm16(loud, seed=v.params.seed)
        del loud
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

        self._stem_cache.clear()
        job.stage = stage_words("score")
        score = self._score(v)
        job.plan = stages(score)
        kept, lead_in, midi_file = self._stems_kept(v, score)
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
                                chosen_by_you=v.marks or None, progress=job.report, name=self.name_of(v),
                                kept=kept)
        (folder / "rendition.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        link(folder / "rendition.flac", self.cache / f"{key}.flac")
        made = kept.finished()
        if made is not None:  # the stems, kept as it was made: Export → Stems has them at once
            gain, files, _ = made
            self._zip_stems(key, v, record, kept.parts, gain, files.pop, midi_file, lead_in)
        job.url = f"/audio/{key}.flac"
        prune(self.cache, self.cache_limit)
        return {"url": job.url, "id": record["id"], "duration": record["duration"],
                "bar_seconds": bar_seconds(self.genome, v.params)}

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
                data, _ = midi.from_score(self.genome, v.params, self._score(v), title=self.genome.title, lyrics=v.lyrics)
                path.write_bytes(data)
            return {"state": "done", "progress": 1.0,
                    "url": f"/export/{key}.mid?name={self.export_name(v, '.mid')}", "label": "the MIDI file"}
        if what != "stems":
            raise ValueError("export midi or stems")
        if (self.cache / f"{key}.zip").exists():
            url = f"/export/{key}.zip?name={self.stems_name(key)}.stems.zip"
            return {"state": "done", "progress": 1.0, "url": url, "label": "the stems", "kind": "export"}
        self.check_whole(v, stems=True)
        job = self.jobs.submit(f"{key}-stems", "preview", "the stems", lambda job: self._stems(job, v, key),
                               **self._limits(by, whole=True))
        return self.jobs.view(job) | {"download": f"/export/{key}.zip?name={self.export_name(v, '.stems.zip')}"}

    # ---- the stems belong to a recording (docs/STUDIO.md, "The smaller things"): made after the recording of the
    # same version, from the same choices and score, and named after it, as <song>.<day>.<its id's first six>

    def recorded(self, job, v: explain.Version, key: str) -> dict:
        """The record of this version's recording, made first if it isn't yet (as Record it makes it: the same
        rendition, which Record it then only copies)."""
        folder = self.cache / key
        if not ((folder / "rendition.json").exists() and (self.cache / f"{key}.flac").exists()):
            self._whole(job, v, key)
        return json.loads((folder / "rendition.json").read_text(encoding="utf-8"))

    def recording_name(self, record: dict) -> str:
        """A recording's file name without its extension, as Record it names it (_keep)."""
        return f"{slug(self.genome.title)}.{(record.get('rendered_at') or self.day)[:10]}.{record['id'][:6]}"

    def stems_name(self, key: str) -> str:
        """The name the stems of the version cached under key go by: their recording's."""
        return self.recording_name(json.loads((self.cache / key / "rendition.json").read_text(encoding="utf-8")))

    def _stems_kept(self, v: explain.Version, score) -> tuple[stems_mod.Kept, float, bytes]:
        """What keeps the stems as the whole song is made (stems.Kept), with the MIDI file's lead-in and the file."""
        from .cli import choir_of

        data, lead_in = midi.from_score(self.genome, v.params, score, title=self.genome.title, lyrics=v.lyrics)
        singer = explain.singer_of(v.params)
        jobs, _ = synth.stem_jobs(score, seed=v.params.seed, voice=singer,
                                  ancestors=choir_of(self.parent_record, singer)[1])
        parts = stems_mod.in_order([name for name, _ in jobs])
        return stems_mod.Kept(parts, int(round(-lead_in * synth.SR)), self.genome.title), lead_in, data

    def _zip_stems(self, key: str, v: explain.Version, record: dict, order: list[str], gain: float, flac_of,
                   midi_file: bytes, lead_in: float) -> str:
        """The stems' zip, named after the recording (record): flac_of(part) is each part's file, in the zip's order;
        the MIDI file and the note beside them. Its name."""
        stem = self.recording_name(record)
        tmp = self.cache / f"{key}.part.zip"
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for i, part in enumerate(order, 1):
                z.writestr(f"{stem}/{i:02d}-{part}.flac", flac_of(part))
            z.writestr(f"{stem}/{stem}.mid", midi_file)
            z.writestr(f"{stem}/README.txt", stems_note(self.genome.title, v.params, -lead_in, gain, order,
                                                        recording=(f"{stem}.flac", record["id"])))
        tmp.replace(self.cache / f"{key}.zip")
        prune(self.cache, CACHE_LIMIT)
        return f"{stem}.stems.zip"

    def _stems(self, job: Job, v: explain.Version, key: str) -> dict:
        """Every part of the rendition rendered alone and dry (synth.render_stems, as the command line's
        --stems), each padded to start at the MIDI file's bar 1, as 24-bit FLAC; the MIDI file and a note on
        what they are beside them, in one zip named after the recording they belong to (songbird.stems). Made
        with the recording if it isn't made yet (_whole keeps them as it makes it: then they take the job's
        progress); otherwise made here."""
        from .cli import choir_of

        if not ((self.cache / key / "rendition.json").exists() and (self.cache / f"{key}.flac").exists()):
            self.recorded(job, v, key)
            if (self.cache / f"{key}.zip").exists():
                job.url = f"/export/{key}.zip?name={self.stems_name(key)}.stems.zip"
                return {"url": job.url, "parts": len(zipfile.ZipFile(self.cache / f"{key}.zip").namelist()) - 2}
        record = self.recorded(job, v, key)
        job.stage = stage_words("score")
        score = self._score(v)
        job.plan = [p for p in stages(score) if p[0] not in ("mix", "master")] + [("master", 1.0)]
        data, lead_in = midi.from_score(self.genome, v.params, score, title=self.genome.title, lyrics=v.lyrics)
        singer = explain.singer_of(v.params)
        stems = synth.render_stems(score, seed=v.params.seed, voice=singer,
                                   ancestors=choir_of(self.parent_record, singer)[1], progress=job.report)
        job.report("master")
        job.stage = "packing the stems"
        pad = int(round(-lead_in * synth.SR))
        gain = stems_mod.gain_of(max((stems_mod.peak_of(x) for x in stems.values()), default=0.0))
        order = stems_mod.in_order(list(stems))
        name = self._zip_stems(key, v, record, order, gain,
                               lambda part: stems_mod.packed(stems_mod.padded(stems[part], pad, gain), self.genome.title),
                               data, lead_in)
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
            tmp.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
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

    # ------------------------------------------------------------ the arrangement as a grid (docs/STUDIO.md, "Arrangement control")
    # The version on the page as a timeline draws it: sections x players, each cell the program's and the person's
    # (arrange.* edits, songbird.takeover), with the program's reasons. Made at once from the score laid out (no
    # audio), like the MIDI file; held to a public studio's limit on requests like every other request.

    def arrangement(self, edits: dict) -> dict:
        from . import takeover

        v = self.version(edits)
        _, heard = self._score_and_heard(v)
        grid = takeover.grid(self.genome, v, heard)
        for s in grid["sections"]:  # where the voices before sing (the score's track for them): a choir section, sung, or a round
            s["choir"] = bool(s.get("round") or v.params.choir and s["sung"] and self.genome.section(s["name"]).choir)
        return {"key": self.key(v, None), **grid}

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
        return notesin.take(self.genome, v.params, str(take.get("player", "")), take.get("notes"), take.get("lines"),
                            played=take.get("played") is True)

    # ------------------------------------------------------------ sound design (docs/SOUND-DESIGN.md)

    def sound(self, edits: dict) -> dict:
        """Every player's sound and channel (patch, filter, kit and its pieces, pan, send, sidechain) and every
        section boundary's transition, each as sung, as the program has it, and whether it is the person's
        (songbird.sound.view). Made at once, without a render: the page sets them as edits and listens as ever."""
        from . import sound as sound_mod

        v = self.version(edits)
        view = sound_mod.view(self.genome, v.params, v.generated, v.applied, v.problems, self._score(v))
        return {"key": self.key(v, None), **view}

    def record(self, edits: dict, by: tuple[str, str] | None = None) -> dict:
        v = self.version(edits)
        key = self.key(v, None)
        folder = self.cache / key
        keep = lambda job=None: self._keep(folder)  # noqa: E731
        if all((folder / name).exists() for name in ("rendition.json", "rendition.flac")) \
                and (self.cache / f"{key}.flac").exists():
            return {"state": "done", "progress": 1.0, "url": f"/audio/{key}.flac", "result": keep(),
                    "label": "the recording", "kind": "record"}
        self.check_whole(v)
        return self.jobs.view(self.jobs.submit(key, "record", "the recording", lambda job: self._whole(job, v, key),
                                               then=keep, **self._limits(by, whole=True)))

    def _keep(self, folder: Path) -> dict:
        """The recording copied from the cache to where recordings go, as <song>.<day>.<its id's first six>.flac:
        one file, the program, the song and the record inside it."""
        record = json.loads((folder / "rendition.json").read_text(encoding="utf-8"))
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
        # what a recording is, the Tools sheet's Record it says; this is only where it's kept, when not here
        if self.public:
            return f"Download your copy: the studio keeps it for {self.public.download_hours:g} hours."
        if self.shared:
            return "It is saved on the computer serving this studio: download your copy."
        return ""

    # ------------------------------------------------------------ open to the public

    def serving_begin(self, where: str) -> bool:
        """A request from this address being served (a public studio's), if it has fewer than connections_ip at
        once; False if it has as many already."""
        with self._serving_lock:
            if self._serving[where] >= self.public.connections_ip:
                return False
            self._serving[where] += 1
            return True

    def serving_end(self, where: str) -> None:
        with self._serving_lock:
            self._serving[where] -= 1
            if self._serving[where] <= 0:
                del self._serving[where]

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

    def receive(self, path: Path, timeout: float | None = None) -> dict:
        """A file someone brought (in a folder of its own, which the caller removes), read as data by a process
        of its own (given `timeout` seconds at most) and kept, if this program can continue it, as a version this
        studio opens at /v/<id>. Raises received.Refused, saying why, if not."""
        out = received.examine_apart(path, self.genome.title, self.machine, self.day, ROOT, path.parent,
                                     timeout=timeout, minutes=self.most_minutes())
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
        newer = isinstance(r.get("record_format"), int) and r["record_format"] > RECORD_FORMAT
        return {"id": self.version_id, "url": f"/v/{self.version_id}", "generation": generation(r),
                "made": (r.get("rendered_at") or "")[:10] or None, "rendition": r["id"][:12], "name": r.get("name"),
                "program": theirs[:12], "other_program": other,
                "program_note": ("It was made by a newer version of the program than this studio's, which continues "
                                 "it with what it understands of it; the file's own studio understands all of it."
                                 if newer else
                                 f"It was made by another version of the program ({theirs[:8]}…); this studio "
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
                detail = json.loads(path.read_text(encoding="utf-8")).get("source_detail", "")
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
    # program (a packet never carries it): it needs a checkout's tools and their dev dependencies. These are the
    # studio's only hooks into it.

    def enable_web_singing(self, kit: str | Path | None = None, check: bool = False) -> None:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        try:
            from webstudio.singing import Singing
        except ImportError:  # it doesn't travel in a version's file: singing is in a checkout, and at studio.itsby.you
            raise SystemExit("songbird: singing isn't in this file's studio; sing at https://studio.itsby.you, "
                             "or from the program's source") from None

        self.singing = Singing(self, kit, check=check)

    def phrasing_choices(self):
        """The ways of singing a version may name: those made on this computer, and, with singing in the
        browser, the one a page made there (by its fingerprint, never listed)."""
        made = self.phrasing_files()
        return self.singing.lookup(made) if self.singing is not None else made

    def sung_phrasings(self, edits: dict) -> list[dict]:
        """For the singer's card: the way of singing in the browser these edits chose, if they chose one."""
        return self.singing.listed(edits) if self.singing is not None else []

    # ------------------------------------------------------------ rendering in the visitor's browser (--browser-render)
    #
    # A public studio given a built bundle (web/studio-wasm/tools/build_render.py: Pyodide, numpy and scipy, the
    # kernels in JS and wasm, and this very program) serves it under /render/, and the page's renderer
    # (songbird/studio/renderer.js) makes previews and recordings in a worker in the visitor's browser, the
    # server's queue as its fallback. The page asks for a render spec: the version resolved here, exactly as
    # _section and _whole would sing it (the song's file, the params, the words, the phrasing, the parent, the
    # machine and day), so the browser works nothing out again and makes the same samples, and the same packet.
    # Nothing a browser makes is sent back or kept here. docs/WEB-STUDIO.md, "Made in the visitor's browser".

    browser = None  # the bundle served (BrowserBundle), when --browser-render gave one
    noindex = False  # a public studio asks search engines not to list it (--noindex: its beta)

    @property
    def makes_specs(self) -> bool:
        """Whether the page may ask for render specs (/api/render/spec): where a browser makes the song."""
        return self.browser is not None

    def enable_browser_render(self, folder: str | Path) -> None:
        if self.public is None:
            raise ValueError("rendering in the browser is for a public studio (--public); this computer's own "
                             "studio sings the song itself")
        self.browser = BrowserBundle(Path(folder), self.program_digest)

    def runs_with(self) -> dict:
        """What a recording's packet says the program runs with: this Python and its pinned dependencies (a studio on
        the visitor's device says the release's, which its build recorded: never Pyodide's)."""
        return {"python": f"{sys.version_info.major}.{sys.version_info.minor}", "requirements": pack.requirements()}

    def render_spec(self, edits: dict, who: str = "you", section: int | None = None) -> dict:
        """What the browser needs to make a preview (a section) or the whole song (the recording) exactly as this
        studio would: the key it would be cached under, the words the player says, and the spec (as JSON text,
        so the page never reads its 64-bit seeds as floats). What this studio has made already is said instead
        ("made"): the page then asks for it as ever, and it plays at once."""
        v = self.version(edits, who)
        if section is not None and not 0 <= section < len(clips.sung_form(v.params)):
            raise ValueError("no such section")
        key = self.key(v, section)
        label = explain.listen_label(self.context, v, section, who)
        if (self.cache / f"{key}.flac").exists():
            return {"key": key, "label": label, "made": True}
        if section is None and self.public is not None:  # too long for a browser's heap: the server, if it can
            seconds, parts = self.whole_cost(v)
            if not self.fits_browser(seconds, parts):
                fits, most = self.fits_here(seconds, parts)
                if not fits:
                    return {"key": key, "label": label, "too_long": public_mod.too_long(seconds, most, False)}
                return {"key": key, "label": label, "server": True}
        spec = {"v": RENDER_SPEC, "kind": "section" if section is not None else "whole", "key": key,
                "program": self.program_digest,
                "genome": (self.genome_bytes or self.genome_path.read_bytes()).decode("utf-8"),
                "params": v.params.to_dict(), "lyrics": v.lyrics.to_dict() if v.lyrics else None,
                "phrasing": v.phrasing_json, "choir": v.choir_phrasings, "parent": self.parent_record}
        if section is not None:
            spec["section"] = section
        else:  # as _whole hands them to render_one, and as the packet names what the program runs with
            spec |= {"voice": v.voice.to_dict() if v.voice is not None else None,
                     "drift": v.drift.to_dict() if v.drift is not None else None,
                     "changes": v.changes if v.drift is not None else None, "marks": v.marks or None,
                     "name": self.name_of(v), "packet": self.runs_with()}
        answer = {"key": key, "label": label, "kind": spec["kind"], "spec": json.dumps(spec, default=str)}
        if section is None:  # what the recording is called, as _keep names it (the day, then its id's first six)
            answer["name"] = {"song": slug(self.name_of(v) or self.genome.title), "day": self.day}
            answer["bar_seconds"] = bar_seconds(self.genome, v.params)  # its clock, as _whole's job ends with it
        return answer


def generation(record: dict) -> int:
    g = record.get("generation")
    return g if isinstance(g, int) and g >= 0 else 0


def singer_name(who: str) -> str:
    """A singer's name as they wrote it, from their newest take's note; else their folder's name."""
    for note in sorted((ROOT / "recordings" / who).glob("*.json"), reverse=True):
        with contextlib.suppress(OSError, ValueError):
            name = json.loads(note.read_text(encoding="utf-8")).get("singer")
            if name:
                return str(name)
    return who.replace("-", " ").title()


def stems_note(title: str, params: Params, pad: float, gain: float, parts: list[str],
               recording: tuple[str, str] | None = None) -> str:
    """What the stems are, for the person who unzips them; recording: the file name and id of the rendition they
    are the parts of."""
    level = ("" if gain >= 1.0 else
             f"\n\nAll of them were turned down together by {-20 * np.log10(gain):.1f} dB, so none clips "
             "and they keep their balance.")
    which = "" if recording is None else textwrap.fill(
        f"These are the parts of the recording {recording[0]} (its id {recording[1]}): the same version, made "
        "from the same choices and the same notes. Record it in the studio saves that recording (at once: it is "
        "already made); its record says every choice in it.", 100) + "\n\n"
    return textwrap.dedent(f"""\
        {title}: the parts, for your own tools
        Made by Songbird's studio: {midi.key_name(params.tonic, params.mode)}, {params.tempo:g} beats a minute.

        {{which}}
        Each part is rendered alone and dry, as the program plays it before the mix: no room, no mix's
        balance, no mastering (the recording has those, so these don't add up to it exactly).{{level}}

        Every file starts at bar 1 of the MIDI file beside them ({pad:.3f} s of silence before the
        song's first sound), so put them all at the start of a project with the MIDI file and they line
        up: the MIDI file carries the tempo (with the ending's slowing), the bars, the key, the
        sections, the words as lyrics and the chords.

        Parts: {", ".join(parts)}. 24-bit FLAC, 44.1 kHz, stereo.

        The song and the program are public domain (CC0): do what you like with them.
        """).replace("{level}", level).replace("{which}\n", which)


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


# ---------------------------------------------------------------- rendering in the visitor's browser: the bundle
#
# What web/studio-wasm/tools/build_render.py makes: bundle.json, naming folders named by their contents' hash,
# py-<hash>/ (Pyodide and its packages: changes with Pyodide), app-<hash>/ (the worker, the kernels, this
# program: changes with every program) and bc-<hash>/ (the bytecode of Pyodide's library and packages), so each file is cached by the visitor for good and a new program fetches
# only its own few megabytes. Served only if it was built from this very program (its digest), since a recording
# made in the browser carries it.

RENDER_SPEC = 1  # the render spec's shape, as web/studio-wasm/py/studio_render.py makes it (its VERSION)
RENDER_TYPES = {".mjs": "text/javascript; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                ".wasm": "application/wasm", ".json": "application/json", ".zip": "application/zip",
                ".whl": "application/zip"}
# the worker's own policy (a worker keeps the one its script came with): scripts and data from here only, and
# WebAssembly compiled, which Pyodide is; Emscripten also evals the small JS its libraries carry (EM_JS), so the
# worker, and only the worker, may eval. The page keeps its own policy, which allows neither.
RENDER_POLICY = ("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; "
                 "frame-ancestors 'none'")


class BrowserBundle:
    """A built bundle, checked: its manifest, its folders, and that it carries this program."""

    def __init__(self, folder: Path, program: str):
        folder = Path(folder).resolve()
        try:
            manifest = json.loads((folder / "bundle.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"{folder} has no bundle.json (build it with web/studio-wasm/tools/build_render.py): "
                             f"{e}") from None
        dirs = {manifest.get("pyodide"), manifest.get("app")}
        if manifest.get("bytecode") is not None:  # the bytecode's folder (a bundle built before it has none)
            dirs.add(manifest["bytecode"])
        if not all(isinstance(d, str) and re.fullmatch(r"(py|app|bc)-[0-9a-f]{12,64}", d) and (folder / d).is_dir()
                   for d in dirs) or len(dirs) != 2 + ("bytecode" in manifest):
            raise ValueError(f"{folder}/bundle.json names folders it hasn't got; build it again")
        if manifest.get("program_sha256") != program:
            raise ValueError(f"the bundle in {folder} was built from another program "
                             f"({str(manifest.get('program_sha256'))[:12]}; this one is {program[:12]}): a recording "
                             "made in the browser carries its program, so build it again from this one")
        self.folder, self.manifest, self.dirs = folder, manifest, dirs

    def view(self) -> dict:
        """What the page is told (GET /render/bundle.json): where the two folders are, and how much a first visit
        fetches."""
        m = self.manifest
        return {"v": RENDER_SPEC, "base": "/render/", "pyodide": m["pyodide"], "app": m["app"],
                **({"bytecode": m["bytecode"]} if m.get("bytecode") else {}),
                "packages": m.get("packages", []), "bytes": m.get("bytes"), "transfer": m.get("transfer"),
                "program": m["program_sha256"]}

    def file(self, rel: str) -> Path | None:
        """A file of the bundle by its path under /render/ ("app-1234…/kernels/rt.mjs"), or None: only in its
        folders, only plain names (no dot files, no climbing), only the types it serves."""
        parts = rel.split("/")
        if len(parts) < 2 or parts[0] not in self.dirs or len(rel) > 200 \
                or not all(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._+-]{0,120}", p) for p in parts[1:]) \
                or Path(parts[-1]).suffix not in RENDER_TYPES:
            return None
        path = self.folder.joinpath(*parts)
        return path if path.is_file() and path.resolve().is_relative_to(self.folder) else None


# ---------------------------------------------------------------- the page's questions, answered
#
# What each of the page's JSON requests is answered with, apart from how it arrived: by the Handler (over HTTP, after
# its guards), and by a studio on the visitor's device (web/studio-wasm/py/studio_device.py): the same JSON either way.

QUESTIONS = ("/api/start", "/api/timeline", "/api/phrasings")  # GET: what the page asks, changing nothing


class NotFound(LookupError):
    """No such question, or no such job: 404, saying so."""


def asked(studio: Studio, path: str) -> dict | list:
    """A GET question's answer (QUESTIONS, or /api/job/<id>)."""
    if path == "/api/start":
        return studio.start_view()
    if path == "/api/timeline":
        return studio.timeline()
    if path == "/api/phrasings":
        return studio.phrasings()
    if path.startswith("/api/job/"):
        job = studio.jobs.get(path.rsplit("/", 1)[-1])
        if job is None:
            raise NotFound("no such job")
        return studio.jobs.view(job)
    raise NotFound("not found")


def _who(body: dict) -> str:
    who = str(body.get("who", "you"))
    if who not in ("you", "program") and not re.fullmatch(r"fictional:[a-z0-9 _-]{1,24}", who):
        raise ValueError("no such machine")
    return who


def answer(studio: Studio, path: str, body: dict, by: tuple[str, str] | None = None) -> dict | list:
    """A POST's answer: `body` the page's JSON (a map, its edits a map), `by` a public studio's visitor and address.
    Raises NotFound (404), ValueError, KeyError or TypeError (400), Busy (503), public.Limited (429) and
    public.TooLong (422), which the caller says as it says them."""
    edits = body.get("edits") or {}
    if path == "/api/song":
        return studio.song(edits)
    if path == "/api/options":
        return studio.options(edits, str(body.get("block", "")), int(body.get("index", 0)))
    if path == "/api/keep-words":
        return studio.keep_words(edits)
    if path == "/api/clips":  # an operation on the song's clips, as the edits it leaves (songbird.clips)
        return studio.clips(edits, body)
    if path == "/api/compare":
        return studio.compare(edits, list(body.get("names", [])))
    if path == "/api/listen":
        section = body.get("section")
        return studio.listen(edits, _who(body), None if section is None else int(section), by=by)
    if path == "/api/cancel":
        return {"cancelled": studio.jobs.cancel(str(body.get("job", "")), owner=by[0] if by else None)}
    if path == "/api/export":
        return studio.export(edits, str(body.get("what", "")), by=by)
    if path == "/api/record":
        return studio.record(edits, by=by)
    if path == "/api/piano":  # the piano page's score of this version (made at once)
        return studio.piano(edits)
    if path == "/api/players":  # every part in beats, for the sketch's players (MIDI out)
        return studio.players(edits)
    if path == "/api/notes-in":  # a take or a MIDI file, as a preview of edits (notes in)
        return studio.notes_in(edits, body)
    # the arrangement as a grid, for a timeline (docs/STUDIO.md, "Arrangement control"; songbird.takeover)
    if path == "/api/arrangement":
        return studio.arrangement(edits)
    if path == "/api/sound":  # sound design: each player's sound and channel, each boundary's transition
        return studio.sound(edits)
    if path == "/api/render/spec" and studio.makes_specs:  # to make it in the visitor's browser
        section = body.get("section")
        return studio.render_spec(edits, _who(body), None if section is None else int(section))
    if path == "/api/sing":
        return studio.sing()
    if path.startswith("/api/sing/") and studio.singing is not None:
        return studio.singing.post(path, body, studio)
    raise NotFound("not found")


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
    _where: str | None = None  # a public studio's: the address this request is counted under (serving_begin)
    send_grace = 60.0  # seconds a download may take before it's held to public.Limits.send_kb

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def parse_request(self) -> bool:
        self._began = time.monotonic()
        with contextlib.suppress(Exception):  # a public studio's day moves on at midnight (Studio.roll)
            self.studio.roll()
        if not super().parse_request():
            return False
        if self.studio.public is not None and urlsplit(self.path).path != "/healthz":
            # a public studio's requests at once from one address (the connection's may be the proxy's): past
            # connections_ip, turned away, so one address can't hold every connection the studio serves
            where = public_mod.network(self._ip())
            if not self.studio.serving_begin(where):
                self.close_connection = True
                self.too_many(429, public_mod.Limited("Too many requests from your address at once; wait a "
                                                      "moment.", 5))
                return False
            self._where = where
        return True

    def handle_one_request(self) -> None:
        self._sent, self._where = None, None
        try:
            super().handle_one_request()
        finally:
            if self._where is not None:
                self.studio.serving_end(self._where)
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

    def _guard(self, kind: str, wrong_kind: str) -> Callable[[], None] | None:
        """Why a POST can't be taken, as the reply that says so, before a byte of its body is read; None if it can.
        Only the studio's own page: its address, its key, a public studio's limit on requests, the body's type
        (`kind`), and the token the page was given (a header no other page can send without asking first, which
        this server never answers)."""
        if not self._local():
            return lambda: self.fail(403, "this page answers only its own address")
        if not self._admitted():
            return lambda: self.fail(403, "this studio needs its link's key")
        if self.studio.public is not None:
            try:
                self.studio.gate.request(self._ip())
            except public_mod.Limited as e:
                return lambda limited=e: self.too_many(429, limited)
        if self.headers.get("Content-Type", "").split(";")[0].strip() != kind:
            return lambda: self.fail(415, wrong_kind)
        if not self._page_token()[0]:
            return lambda: self.fail(403, "this page answers only the page it gave out")
        return None

    def _refuse(self, reply: Callable[[], None], length: int, most: int = 2**20, seconds: float = 5.0) -> None:
        """A refusal before the body was read: the body, up to `most` bytes, read and dropped a block at a time
        (nothing of it kept) for up to `seconds`, so the connection stays in step for the next request; then said
        (and the connection closed if the body couldn't be let go of whole)."""
        if not self._drain(length, most, seconds):
            self.close_connection = True
        reply()

    def _read_body(self, length: int, rate: int = 32 * 1024) -> bytearray:
        """The body, `length` bytes, read a block at a time: whole, and no slower than a slow connection sends
        (a minute, and a second for every `rate` bytes), else ValueError."""
        deadline = time.monotonic() + 60 + length / rate
        buf = bytearray(length)
        view, got = memoryview(buf), 0
        while got < length:
            n = self.rfile.readinto(view[got:got + 2**16])
            if not n:
                raise ValueError("It didn't arrive whole; send it again.")
            got += n
            if time.monotonic() > deadline:
                raise ValueError("It came too slowly to take; send it again on a faster connection.")
        view.release()
        return buf

    def too_many(self, code: int, e: Exception) -> None:
        retry = getattr(e, "retry", 60)
        self.send(json.dumps({"error": str(e), "retry": retry, "busy": True}).encode(), "application/json", code,
                  {"Retry-After": str(retry)})

    def refuse_visitor(self) -> None:
        page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                "<title>Studio</title><link rel=stylesheet href='/notice.css'><body class=notice>"
                "<h1>This studio is shared by link</h1>"
                "<p>Its link carries a key: ask the person who shared it for the whole link, "
                "ending in <code>?key=</code>.</p></body>")
        self.send(page.encode(), "text/html; charset=utf-8", 403)

    # ------------------------------------------------------------ replies

    def send(self, body: bytes | io.BufferedReader, kind: str, code: int = 200,
             extra: dict | list | None = None, cache: str = "no-store", policy: str | None = None,
             length: int | None = None) -> None:
        """A reply: bytes, or an open file's from where it stands (sent as it's read, not held whole; `length`
        bytes of it, for a range)."""
        whole = isinstance(body, (bytes, bytearray))
        size = len(body) if whole else length if length is not None else os.fstat(body.fileno()).st_size
        self._sent = (code, size)
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        # a song made in this browser plays from a blob: URL (--browser-render); nothing else changes
        media = "'self' blob:" if self.studio.browser is not None else "'self'"
        self.send_header("Content-Security-Policy", policy or
                         f"default-src 'self'; media-src {media}; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'")
        if self.studio.noindex:  # a public studio in its beta: no search engine lists it
            self.send_header("X-Robots-Tag", "noindex, nofollow")
        for k, v in (extra.items() if isinstance(extra, dict) else extra or ()):
            self.send_header(k, v)
        self.end_headers()
        if self.command == "HEAD":
            return
        if whole:
            self.wfile.write(body)
            return
        # a file, a block at a time; open to the public, no slower than send_kb a second over the whole of it (after
        # a minute's grace), so a reader taking a byte at a time can't hold its connection for days
        rate = self.studio.public.send_kb * 1024 if self.studio.public is not None else None
        began, sent, left = time.monotonic(), 0, size
        before = self.connection.gettimeout()
        try:
            while left:
                chunk = body.read(min(left, 2**16))
                if not chunk:
                    break
                if rate:  # each block sent by when the least rate has it sent: a reader that stops reading blocks
                    # the write itself, so the write is what times out
                    due = began + self.send_grace + (sent + len(chunk)) / rate - time.monotonic()
                    self.connection.settimeout(max(due, 0.05) if before is None else min(max(due, 0.05), before))
                try:
                    self.wfile.write(chunk)
                except (TimeoutError, socket.timeout):
                    self.let_go()
                    return
                sent += len(chunk)
                left -= len(chunk)
                if rate and left and time.monotonic() - began > self.send_grace + sent / rate:
                    self.let_go()
                    return
        finally:
            if rate:
                self.connection.settimeout(before)

    def let_go(self) -> None:
        """A download too slow to keep: the rest isn't sent, and what the system still holds for it is dropped (the
        connection reset, not closed), so a reader taking a byte at a time can't drain megabytes from its buffers."""
        self.close_connection = True
        with contextlib.suppress(OSError):
            self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))

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
            if path == "/robots.txt" and self.studio.noindex:
                return self.send(b"User-agent: *\nDisallow: /\n", "text/plain; charset=utf-8")
            if self._throttled():
                return
        if path == "/notice.css":  # the plain pages' look, for a visitor without the key too
            return self.send((PAGE / "notice.css").read_bytes(), "text/css; charset=utf-8")
        if not self._admitted():
            return self.refuse_visitor() if path in ("/", "/index.html") or path.startswith("/v/") \
                else self.fail(403, "this studio needs its link's key")
        try:
            singing = self.studio.singing
            if singing is not None and singing.get(self, path, {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}):
                return None
            if path.startswith("/render/") and self.studio.browser is not None:  # the bundle (--browser-render)
                return self.render_file(path[len("/render/"):])
            if path == "/piano" or path.startswith("/piano/"):  # learning it at the piano
                return self.piano_page(path)
            # someone's version: the page's token names it
            version = re.fullmatch(r"/v/([0-9a-f]{32})", path)
            if path.startswith("/v/") and (version is None or self.studio.opened(version.group(1)) is None):
                return self.version_gone()
            page_name = PAGES.get(path.rstrip("/") if path != "/" else "") or ("index.html" if version else None)
            if page_name:
                token = f"{self.studio.token}.{version.group(1)}" if version else self.studio.token
                page = (PAGE / page_name).read_text(encoding="utf-8").replace("{{token}}", token)
                if self.studio.browser is not None:  # the page asks for the browser's bundle only when there is one
                    page = page.replace('<meta name="studio-token"', '<meta name="studio-render" content="bundle">\n<meta name="studio-token"', 1)
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
            if path in QUESTIONS or path.startswith("/api/job/"):  # the page's questions (asked())
                studio = self._asked() if path in QUESTIONS else self.studio
                if studio is None:  # the version the page was opened on (someone brought it) isn't kept any more
                    return self.version_gone()
                try:
                    return self.send_json(asked(studio, path))
                except NotFound as e:
                    return self.fail(404, str(e))
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
        except ConnectionError:  # a player letting go of a file it was sent (it jumped, or stopped): no error
            raise  # (Server.handle_error)
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
            with path.open("rb") as f:  # just the part asked for, streamed: never a whole song in memory
                f.seek(start)
                return self.send(f, "audio/flac", 206,
                                 {"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"},
                                 length=end + 1 - start)
        with path.open("rb") as f:
            self.send(f, "audio/flac", 200, {"Accept-Ranges": "bytes"})

    # ------------------------------------------------------------ POST

    def do_POST(self) -> None:
        if self.studio.singing is not None and urlsplit(self.path).path == "/api/sing/take":
            return self.studio.singing.handle_take(self)  # a take is bigger than a JSON; its own guards, the same
        if urlsplit(self.path).path == "/api/open":
            return self.open_version()  # a file someone brought: every guard before a byte of it is read
        # every guard before a byte of the body is read; a refusal closes the connection (its body unread)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 2**20:
            self.close_connection = True
            return self.fail(413, "too much")
        refusal = self._guard("application/json", "send JSON")
        if refusal is not None:
            return self._refuse(refusal, length)
        version = self._page_token()[1]
        try:
            raw = self._read_body(length) if length else b""
        except ValueError as e:
            self.close_connection = True
            return self.fail(400, str(e))
        path = urlsplit(self.path).path
        try:
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict) or not isinstance(body.get("edits") or {}, dict):
                return self.fail(400, "send a map, with the edits a map of choices")
            # the studio on the version the page was opened on, if someone brought it (singing is the song's own, but
            # for the guide, which is the version on the page)
            studio = self.studio if version is None or (path.startswith("/api/sing") and path != "/api/sing/guide") \
                else self.studio.opened(version)
            if studio is None:
                return self.version_gone()
            if path == "/api/open/ready":  # someone's version: would a file this size be taken now?
                refusal = self._may_open(int(body.get("size") or 0), count=False)
                return refusal() if refusal is not None else self.send_json({"ready": True})
            return self.send_json(answer(studio, path, body, self._by() if studio.public is not None else None))
        except NotFound as e:
            return self.fail(404, str(e))
        except Busy as e:
            return self.too_many(503, e) if self.studio.public is not None else self.fail(503, str(e))
        except public_mod.Limited as e:
            return self.too_many(429, e)
        except public_mod.TooLong as e:  # a whole song past this studio's memory: said, never queued
            return self.send_json({"error": str(e), "too_long": True}, 422)
        except (ValueError, KeyError, TypeError) as e:
            return self.fail(400, str(e))
        except Exception as e:
            traceback.print_exc()
            return self.fail(500, f"{type(e).__name__}: {e}")


    # ------------------------------------------------------------ rendering in the visitor's browser: its files
    #
    # /render/bundle.json says where the bundle's two folders are (asked each visit, never cached for long);
    # everything under them is named by its folder's hash, so it's cached for good. A file built compressed too
    # (NAME.gz beside it) is sent so to a browser that takes it. The worker's script carries the worker's policy
    # (RENDER_POLICY); nothing here is a page.

    def render_file(self, rel: str) -> None:
        bundle = self.studio.browser
        if rel == "bundle.json":
            return self.send(json.dumps(bundle.view()).encode(), "application/json", cache="no-cache")
        path = bundle.file(rel)
        if path is None:
            return self.fail(404, "not found")
        extra = {"Cross-Origin-Resource-Policy": "same-origin", "Vary": "Accept-Encoding"}
        packed = path.with_name(path.name + ".gz")
        if packed.is_file() and "gzip" in self.headers.get("Accept-Encoding", "").lower():
            path, extra["Content-Encoding"] = packed, "gzip"
        with path.open("rb") as f:
            return self.send(f, RENDER_TYPES[Path(rel).suffix], 200, extra,
                             cache="public, max-age=31536000, immutable", policy=RENDER_POLICY)

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
                "<title>Studio</title><link rel=stylesheet href='/notice.css'><body class=notice>"
                "<h1>This version isn't here</h1>"
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
                elif not studio.reading.acquire(blocking=False):  # its reader's place, held from now: never waited for
                    refusal = self._reading
                else:
                    studio.arriving.add(where)
        if refusal is not None:
            refusal()
            return self._linger(length)
        folder = Path(tempfile.mkdtemp(prefix="open-", dir=studio.incoming))
        try:
            path = folder / "brought.flac"
            self._arrive(path, length)
            # answered within OPEN_SECONDS of being asked (a proxy gives up on an answer after 100): the reader's
            # time is what's left of them, and a file that took most of them to arrive is refused
            left = OPEN_SECONDS - (time.monotonic() - self._began)
            if left < received.SECONDS / 2:
                raise received.Refused("The file came too slowly to read in time; send it again on a faster "
                                       "connection.")
            answer = studio.receive(path, timeout=left)
        except received.Refused as e:
            return self.fail(422, str(e))
        except (TimeoutError, ConnectionError):
            return None  # the sender went quiet, or away: no one to answer
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            studio.reading.release()
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
            if not count:  # the page asking first: whether a reader is free now (open_version holds one from the start)
                if not studio.reading.acquire(blocking=False):
                    return self._reading
                studio.reading.release()
        return None

    def _reading(self) -> None:
        self.too_many(503, Busy("The studio is reading other versions just now; send it again in a minute.", 60))

    def _busy(self) -> None:
        self.too_many(503, Busy("A file is on its way here from you already, or several from others; send it "
                                "again in a moment.", 30))

    def _linger(self, length: int) -> None:
        """After a refusal, a small body read and dropped, so the answer isn't lost to the connection's reset (a
        large one is never read: the page asks first, /api/open/ready)."""
        self._drain(length, 2**16, 2.0)

    def _drain(self, length: int, most: int, seconds: float) -> bool:
        """A body of `length` bytes read a block at a time and dropped, if it's no more than `most` and comes
        within `seconds`: whether it all was."""
        if length <= 0:
            return length == 0
        if length > most:
            return False
        deadline = time.monotonic() + seconds
        before = self.connection.gettimeout()
        try:
            self.connection.settimeout(min(before or seconds, seconds))
            while length > 0:
                if time.monotonic() > deadline:
                    return False
                chunk = self.rfile.read(min(length, 2**16))
                if not chunk:
                    return False
                length -= len(chunk)
        except (OSError, ValueError):
            return False
        finally:
            with contextlib.suppress(OSError):
                self.connection.settimeout(before)
        return True

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
OPEN_SECONDS = 88.0  # a file brought is answered within this long of being asked: Cloudflare gives up after 100


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
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):  # reset, broken pipe, aborted
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
    parser.add_argument("--out", metavar="DIR", help="where recordings go (default: renders/ in a checkout, the current folder from a file)")
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
                             "log that never says who (docs/history/web-studio-server-plan.md)")
    parser.add_argument("--limit", action="append", default=[], metavar="NAME=N",
                        help=f"a public studio's limit: {', '.join(public_mod.names())} (docs/history/web-studio-server-plan.md)")
    parser.add_argument("--client-ip-header", metavar="HEADER",
                        help="public, behind a proxy on this machine or its private network: the header that "
                             "names the visitor's address (CF-Connecting-IP for a Cloudflare tunnel)")
    parser.add_argument("--web-singing", action="store_true",
                        help="take singing in the browser, measured here and its audio deleted (a checkout with the "
                             "dev tools: docs/WEB-SINGING.md)")
    parser.add_argument("--sing-kit", metavar="DIR",
                        help="where singing keeps the guides and template analyses it makes (default "
                             "$SONGBIRD_SING_KIT, else sing-kit in the studio's home)")
    parser.add_argument("--noindex", action="store_true",
                        help="public: ask search engines not to list it (X-Robots-Tag: noindex on every reply, and a "
                             "robots.txt that disallows everything), as for a beta")
    parser.add_argument("--browser-render", metavar="DIR",
                        help="public: serve the bundle built in DIR (web/studio-wasm/tools/build_render.py), so a "
                             "desktop browser makes the song itself and this server only when it can't "
                             "(docs/WEB-STUDIO.md)")


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
    elif getattr(args, "limit", []) or getattr(args, "client_ip_header", None) or getattr(args, "noindex", False):
        raise SystemExit("songbird studio: --limit, --client-ip-header and --noindex are for a public studio "
                         "(--public)")
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
    studio.noindex = bool(limits) and getattr(args, "noindex", False)
    if getattr(args, "web_singing", False):
        studio.enable_web_singing(getattr(args, "sing_kit", None), check=True)
    if getattr(args, "browser_render", None):
        try:
            studio.enable_browser_render(args.browser_render)
        except ValueError as e:
            raise SystemExit(f"songbird studio: --browser-render: {e}") from None
    server = serve(studio, args.port, host=host, names=names, client_ip_header=header)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    print(f"The studio: {studio.genome.title}, {studio.context.opening()}", flush=True)
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
    if studio.browser is not None:
        view = studio.browser.view()
        print(f"  Made in the visitor's browser where it can be ({(view['transfer'] or 0) / 2**20:.0f} MB on a first "
              "visit), here where it can't.", flush=True)
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
