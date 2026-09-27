"""The studio: see how your version of the song was made, change it if you like, and record it.

    songbird studio [PARENT.flac|record.json] [--song GENOME] [--machine here] [--port 8766] [--out DIR]

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
import threading
import time
import traceback
import urllib.request
import webbrowser
import zipfile
from dataclasses import dataclass, field
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import numpy as np

from . import __version__, drift as drift_mod, explain, genome as genome_mod, harvest, pack, synth, variation
from .realize import Params, realize
from .synth import master
from .synth.instruments import INSTRUMENTS
from .synth.mixing import MixParams

PAGE = Path(__file__).with_name("studio")  # index.html, studio.css, studio.js
ROOT = Path(__file__).resolve().parent.parent  # the program's folder: a packet's, or a checkout
LEAD = "h-now-its-by-you"  # in a checkout, the song the studio opens when nothing names one
PORT = 8766
KARAOKE_PORT = 8765
CACHE_LIMIT = 300 * 2**20  # bytes of previews kept; the least recently heard go first
PREVIEW_GAIN_DB = 5.3  # what mastering gives a whole rendition of H (5.1 to 5.4 dB): a section keeps its level
STATIC = {"/studio.css": ("studio.css", "text/css; charset=utf-8"),
          "/composer.js": ("composer.js", "text/javascript; charset=utf-8"),
          "/drafts.js": ("drafts.js", "text/javascript; charset=utf-8"),
          "/author.js": ("author.js", "text/javascript; charset=utf-8"),
          "/studio.js": ("studio.js", "text/javascript; charset=utf-8")}


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


class Jobs:
    """One render at a time: recordings first, oldest first; then previews, newest first (what the person
    asked for last is what they want to hear)."""

    def __init__(self):
        self.lock = threading.Condition()
        self.pending: list[Job] = []
        self.jobs: dict[str, Job] = {}
        self.by_key: dict[str, Job] = {}
        threading.Thread(target=self._run, daemon=True, name="studio-renderer").start()

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def live(self, key: str) -> Job | None:
        job = self.by_key.get(key)
        return job if job is not None and job.state in ("queued", "running") else None

    def submit(self, key: str, kind: str, label: str, work: Callable, then: Callable | None = None) -> Job:
        with self.lock:
            job = self.live(key)
            if job is not None:  # asked for again: first among the previews; a recording waits on it
                job.created = time.time()
                if kind == "record":
                    job.kind = "record"
                    job.label = label
                if then is not None:
                    job.then.append(then)
                return job
            job = Job(secrets.token_hex(6), key, kind, label, work, then=[then] if then else [])
            self.jobs[job.id] = job
            self.by_key[key] = job
            self.pending.append(job)
            finished = sorted((j for j in self.jobs.values() if j.state in ("done", "failed")), key=lambda j: j.created)
            for old in finished[:-200]:
                self.jobs.pop(old.id, None)
            self.lock.notify()
            return job

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
        job = min(records, key=lambda j: j.created) if records else max(self.pending, key=lambda j: j.created)
        self.pending.remove(job)
        return job

    def _run(self) -> None:
        while True:
            with self.lock:
                while not self.pending:
                    self.lock.wait()
                job = self._next()
                job.state = "running"
            try:
                result = job.work(job) or {}
                done = 0
                while True:  # what was asked to follow it (a recording's copy), even if asked for just now
                    with self.lock:
                        todo = job.then[done:]
                        if not todo:
                            job.result, job.progress, job.stage, job.state = result, 1.0, "", "done"
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
                 out: Path | None = None, home: Path | None = None):
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
        self.jobs = Jobs()
        self.token = secrets.token_urlsafe(18)
        self._timeline = None
        self._timeline_lock = threading.Lock()
        self.karaoke: subprocess.Popen | None = None
        self.context = explain.Context(self.genome, parent_params, record, self.voice, machine, self.day, self.t,
                                       quiet)
        prune(self.cache, CACHE_LIMIT)

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

    def listen(self, edits: dict, who: str, section: int | None) -> dict:
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
            job = self.jobs.submit(key, "preview", label, lambda job: self._whole(job, v, key))
        else:
            job = self.jobs.submit(key, "preview", label, lambda job: self._section(job, v, key, section))
        return job.view() | {"key": key}

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
        prune(self.cache, CACHE_LIMIT)
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
        prune(self.cache, CACHE_LIMIT)
        return {"url": job.url, "id": record["id"], "duration": record["duration"]}

    # ------------------------------------------------------------ recording

    def record(self, edits: dict) -> dict:
        v = self.version(edits)
        key = self.key(v, None)
        folder = self.cache / key
        keep = lambda job=None: self._keep(folder)  # noqa: E731
        if all((folder / name).exists() for name in ("rendition.json", "rendition.flac")) \
                and (self.cache / f"{key}.flac").exists():
            return {"state": "done", "progress": 1.0, "url": f"/audio/{key}.flac", "result": keep(),
                    "label": "the recording", "kind": "record"}
        return self.jobs.submit(key, "record", "the recording", lambda job: self._whole(job, v, key), then=keep).view()

    def _keep(self, folder: Path) -> dict:
        """The recording copied from the cache to where recordings go, as <song>.<day>.<its id's first six>.flac:
        one file, the program, the song and the record inside it."""
        record = json.loads((folder / "rendition.json").read_text())
        day = (record.get("rendered_at") or self.day)[:10]
        flac = self.out / f"{slug(self.genome.title)}.{day}.{record['id'][:6]}.flac"
        self.out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / "rendition.flac", flac)
        again = f"python3 {shown(flac)} studio" if self.where == "packet" else f"uv run songbird studio {shown(flac)}"
        return {"recorded": {"flac": shown(flac), "id": record["id"], "duration": record["duration"],
                             "generation": record.get("generation"), "yours": len(record.get("chosen_by_you") or {}),
                             "next": again}}

    def out_shown(self) -> str:
        return shown(self.out)

    def packet_note(self) -> str:
        return ("The recording is one file: it plays anywhere, and it carries the program that sang it, the song "
                "and its record, so anyone can run it to make the next version.")

    # ------------------------------------------------------------ singing (from a checkout of the program)

    def phrasing_files(self) -> dict[str, Path]:
        """The phrasings made on this computer for this song by people who sang it on the singing page, and
        everyone's together: name -> file. Only in a checkout (renders/phrasing, recordings/); reference
        voices are never among them."""
        folder = ROOT / "renders" / "phrasing"
        recordings = ROOT / "recordings"
        stem = self.genome_path.stem
        found = {}
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
        if (ROOT / "tools" / "karaoke.py").exists():
            return {"available": True}
        return {"available": False,
                "why": "Singing into it needs the singing page, which this copy of the program doesn't have yet."}

    def sing(self) -> dict:
        """Start the singing page (tools/karaoke.py) for this song if it isn't running, and say where it is."""
        url = f"http://127.0.0.1:{KARAOKE_PORT}"
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


class Handler(BaseHTTPRequestHandler):
    studio: Studio
    port: int = PORT
    server_version = "songbird-studio"
    sys_version = ""  # no need to say which Python
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    # ------------------------------------------------------------ guards

    def _hosts(self) -> set[str]:
        return {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def _local(self) -> bool:
        """The Host names this server, so no page elsewhere can reach it under another name; and a request
        that says where it came from came from here."""
        if self.headers.get("Host", "") not in self._hosts():
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{h}" for h in self._hosts()}

    # ------------------------------------------------------------ replies

    def send(self, body: bytes, kind: str, code: int = 200, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; media-src 'self'; img-src 'self' data:; style-src 'self'; "
                         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

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
        try:
            if path in ("/", "/index.html"):
                page = (PAGE / "index.html").read_text().replace("{{token}}", self.studio.token)
                return self.send(page.encode(), "text/html; charset=utf-8")
            if path in STATIC:
                name, kind = STATIC[path]
                return self.send((PAGE / name).read_bytes(), kind)
            if path == "/api/start":
                return self.send_json(explain.start(self.studio.context, self.studio))
            if path == "/api/timeline":
                return self.send_json(self.studio.timeline())
            if path == "/api/phrasings":
                return self.send_json(self.studio.phrasings())
            if path.startswith("/api/job/"):
                job = self.studio.jobs.get(path.rsplit("/", 1)[-1])
                return self.send_json(job.view()) if job else self.fail(404, "no such job")
            match = re.fullmatch(r"/audio/([0-9a-f]{16,64})\.flac", path)
            if match:
                return self.audio(self.studio.cache / f"{match.group(1)}.flac")
            return self.fail(404, "not found")
        except Exception as e:  # said on the page rather than dropping the connection
            traceback.print_exc()
            return self.fail(500, f"{type(e).__name__}: {e}")

    def audio(self, path: Path) -> None:
        """A rendering, with byte ranges (players seek with them; Safari won't play without)."""
        if not path.exists():
            return self.fail(404, "not made yet")
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
        self.send(path.read_bytes(), "audio/flac", 200, {"Accept-Ranges": "bytes"})

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
                return self.send_json(studio.listen(edits, who, None if section is None else int(section)))
            if path == "/api/cancel":
                return self.send_json({"cancelled": studio.jobs.cancel(str(body.get("job", "")))})
            if path == "/api/record":
                return self.send_json(studio.record(edits))
            if path == "/api/sing":
                return self.send_json(studio.sing())
            return self.fail(404, "not found")
        except (ValueError, KeyError, TypeError) as e:
            return self.fail(400, str(e))
        except Exception as e:
            traceback.print_exc()
            return self.fail(500, f"{type(e).__name__}: {e}")


class Server(ThreadingHTTPServer):
    request_queue_size = 128  # the page asks for several things at once, and a player many ranges
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        """A browser closing a connection it kept open (a player seeking, a tab closing) is no error."""
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def serve(studio: Studio, port: int = PORT, tries: int = 20) -> ThreadingHTTPServer:
    """A server for the studio on 127.0.0.1, on the port asked for or the next free one."""
    for p in range(port, port + tries):
        handler = type("StudioHandler", (Handler,), {"studio": studio, "port": p})
        try:
            server = Server(("127.0.0.1", p), handler)
        except OSError:
            continue
        return server
    raise SystemExit(f"songbird studio: no free port from {port} to {port + tries - 1}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("parent", nargs="?",
                        help="the rendition to make a new version of: a seed packet, a FLAC with its record "
                             "beside it, or a record (.json); default: the packet this program came in, else "
                             "the song as it began")
    parser.add_argument("--packet", metavar="FILE",
                        help="the packet this program came in (the file's own bootstrap passes it): the rendition "
                             "to open, as the parent of the new version")
    parser.add_argument("--song", metavar="GENOME", help="the song's genome, where the parent doesn't carry it")
    parser.add_argument("--machine", default="here", metavar="here|none|fictional:NAME|FILE",
                        help="who sings: this machine (default), none, a made-up one, or a voice file or record")
    parser.add_argument("--port", type=int, default=PORT, help=f"the port on 127.0.0.1 (default {PORT})")
    parser.add_argument("--out", metavar="DIR", help="where recordings go (default renders/)")
    parser.add_argument("--no-open", action="store_true", help="don't open the page in a browser")


def run(args: argparse.Namespace) -> int:
    parent = args.packet or args.parent or os.environ.get("SONGBIRD_PACKET") or None
    studio = Studio(parent, args.song, args.machine, Path(args.out) if args.out else None)
    server = serve(studio, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"Songbird studio: {studio.genome.title}, {studio.context.opening()}\n  open {url}  (Ctrl-C to stop)",
          flush=True)
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
