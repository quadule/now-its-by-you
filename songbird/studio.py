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
import contextlib
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

from . import __version__, drift as drift_mod, explain, genome as genome_mod, harvest, pack, synth, variation
from . import public as public_mod
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
MAX_WAITING = 12  # renders waiting at once: more are refused until the queue shortens (a shared studio)
CACHE_LIMIT = 300 * 2**20  # bytes of previews kept; the least recently heard go first
PREVIEW_GAIN_DB = 5.3  # what mastering gives a whole rendition of H (5.1 to 5.4 dB): a section keeps its level
STATIC = {"/identity.css": ("identity.css", "text/css; charset=utf-8"),  # the shared tokens (docs/IDENTITY.md)
          "/studio.css": ("studio.css", "text/css; charset=utf-8"),
          "/composer.js": ("composer.js", "text/javascript; charset=utf-8"),
          "/drafts.js": ("drafts.js", "text/javascript; charset=utf-8"),
          "/author.js": ("author.js", "text/javascript; charset=utf-8"),
          "/studio.js": ("studio.js", "text/javascript; charset=utf-8"),
          "/help.js": ("help.js", "text/javascript; charset=utf-8")}


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
    owner: str | None = None  # the visitor who asked for it (a public studio)
    whole: bool = False  # the whole song, not a section: how long it may take

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "label": self.label, "state": self.state,
                "progress": round(self.progress, 3), "stage": self.stage, "url": self.url, "error": self.error,
                "result": self.result}

    def report(self, name: str) -> None:
        """A render starting on a part: the progress up to it, and what it is making now."""
        total = sum(w for _, w in self.plan) or 1.0
        done = 0.0
        for stage, weight in self.plan:
            if stage == name:
                self.progress = max(self.progress, min(0.99, done / total))
                break
            done += weight
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
        self.took = {True: 90.0, False: 15.0}  # seconds a whole song and a section take: guesses, then measured
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
                    raise public_mod.Limited("Your recording is waiting its turn; the next can be asked for when "
                                         "it's made.", self._eta([job]))
                self.pending.remove(job)
                job.state, job.error = "failed", "cancelled"
        for job in self.jobs.values():
            if job.owner == owner and job.state == "running":
                raise public_mod.Limited("Yours is being made now; ask for the next when it's done (one at a time "
                                     "for each person, so everyone gets a turn).", self._eta([]))

    def _eta(self, waiting: list[Job]) -> float:
        """Seconds until the renders in `waiting` are made, with the one running now."""
        left = sum(self.took[j.whole] * (1 - j.progress) for j in self.jobs.values() if j.state == "running")
        return left + sum(self.took[j.whole] for j in waiting)

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None or job.state != "queued" or job.kind == "record":
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
                            self.took[job.whole] = 0.7 * self.took[job.whole] + 0.3 * (time.monotonic() - began)
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
        self.context = explain.Context(self.genome, parent_params, record, self.voice, machine, self.day, self.t,
                                       quiet, shared=self.shared)
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
            return self.context.version(day, phrasings=self.phrasing_files())
        if who.startswith("fictional:"):
            return self.context.version(day, voice=harvest.fictional(who.split(":", 1)[1]))
        return self.context.version(edits, phrasings=self.phrasing_files())

    def song(self, edits: dict) -> dict:
        v = self.version(edits)
        view = explain.view(self.context, v, self.phrasings())
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
        material = {"program": __version__, "song": self.song_digest, "params": v.params.to_dict(),
                    "lyrics": v.lyrics.to_dict() if v.lyrics else None, "phrasing": v.phrasing_json,
                    "choir_phrasings": v.choir_phrasings,
                    "section": section, "voice": v.voice.to_dict() if v.voice is not None else None,
                    "drift": v.drift.to_dict() if v.drift is not None else None,
                    "marks": v.marks if section is None else None, "gain": PREVIEW_GAIN_DB}
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
        with contextlib.redirect_stdout(io.StringIO()):
            record = render_one(self.genome, v.params, folder / "rendition.flac", voice=v.voice, drift=v.drift,
                                lyrics=v.lyrics, phrasing_json=v.phrasing_json, choir_json=v.choir_phrasings,
                                parent=self.parent_record,
                                packet_genome=self.genome_path, changes=v.changes if v.drift is not None else None,
                                chosen_by_you=v.marks or None, progress=job.report)
        (folder / "rendition.json").write_text(json.dumps(record, indent=2) + "\n")
        link(folder / "rendition.flac", self.cache / f"{key}.flac")
        job.url = f"/audio/{key}.flac"
        prune(self.cache, self.cache_limit)
        return {"url": job.url, "id": record["id"], "duration": record["duration"]}

    # ------------------------------------------------------------ recording

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


def singer_name(who: str) -> str:
    """A singer's name as they wrote it, from their newest take's note; else their folder's name."""
    for note in sorted((ROOT / "recordings" / who).glob("*.json"), reverse=True):
        with contextlib.suppress(OSError, ValueError):
            name = json.loads(note.read_text()).get("singer")
            if name:
                return str(name)
    return who.replace("-", " ").title()


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
            return self.refuse_visitor() if path in ("/", "/index.html") else self.fail(403, "this studio needs its link's key")
        try:
            if path in ("/", "/index.html"):
                page = (PAGE / "index.html").read_text().replace("{{token}}", self.studio.token)
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
            if path == "/api/start":
                start = explain.start(self.studio.context, self.studio)
                if self.studio.public is not None:
                    start["public"] = self.studio.public.view()
                return self.send_json(start)
            if path == "/api/timeline":
                return self.send_json(self.studio.timeline())
            if path == "/api/phrasings":
                return self.send_json(self.studio.phrasings())
            if path.startswith("/api/job/"):
                job = self.studio.jobs.get(path.rsplit("/", 1)[-1])
                return self.send_json(self.studio.jobs.view(job)) if job else self.fail(404, "no such job")
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
        if not secrets.compare_digest(self.headers.get("X-Studio", "").encode("utf-8", "replace"),
                                      self.studio.token.encode()):
            return self.fail(403, "this page answers only the page it gave out")
        path = urlsplit(self.path).path
        try:
            body = json.loads(raw or b"{}")
            if not isinstance(body, dict) or not isinstance(body.get("edits") or {}, dict):
                return self.fail(400, "send a map, with the edits a map of choices")
            edits = body.get("edits") or {}
            studio = self.studio
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
                return self.send_json({"cancelled": studio.jobs.cancel(str(body.get("job", "")))})
            if path == "/api/record":
                return self.send_json(studio.record(edits, by=by))
            if path == "/api/sing":
                return self.send_json(studio.sing())
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


def public_warning(shares: list[str], limits: public_mod.Limits, key: str | None, machine: str) -> str:
    """What opening the studio to the public means, said when it starts."""
    points = [("Anyone who reaches it can use it" if key is None else "Anyone with the key can use it")
              + f"; the song is shaped by the machine '{machine}' for everyone.",
              f"One song is made at a time: {limits.queue} may wait; each visitor has one at a time, "
              f"{limits.records} whole songs and {limits.previews} sections an hour ({limits.records_ip} and "
              f"{limits.previews_ip} for an address), {limits.requests} requests a minute from an address.",
              f"Recordings aren't kept here: each is offered for download for {limits.download_hours:g} hours "
              f"(up to {limits.downloads_mb} MB); previews are cached up to {limits.cache_mb} MB.",
              "Each request is logged on one line (when, what, the answer), never by whom; visitors are counted "
              "under a key kept only in memory.", "The singing page is off."]
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
    server = serve(studio, args.port, host=host, names=names, client_ip_header=header)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}"
    print(f"Songbird studio: {studio.genome.title}, {studio.context.opening()}", flush=True)
    if limits:
        shares, url = links(host, port, allow, names, key)
        print(public_warning(shares or [url], limits, key, machine), flush=True)
    elif shared:
        shares, url = links(host, port, allow, names, key)
        print(shared_warning(shares, studio.out_shown(), lan=any(link.startswith("http://") for link in shares)))
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
