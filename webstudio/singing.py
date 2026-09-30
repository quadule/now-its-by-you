"""The studio's side of singing in the browser (docs/WEB-SINGING.md): the page's routes, the takes waiting, the
measuring process, and the ways of singing made from them, kept by fingerprint and for a while.

    songbird studio --web-singing [--sing-kit DIR]

The studio makes one of these (Studio.enable_web_singing) and asks it first about the requests that are its:

    GET  /sing.js, /sing.css                  the page's singing (webstudio/), added to the studio's page
    GET  /karaoke.js, /recorder.js            the karaoke's timing, drawing and take recorder (tools/), reused
    GET  /api/sing/offer                      whether singing is on, what to sing to, the limits, the consent's version
    GET  /api/sing/lyrics?spec=ID             a version's words, notes, beats and sections
    GET  /api/sing/guide?spec=ID              its melody guide (FLAC, with byte ranges)
    POST /api/sing/take                       a take (the karaoke's WAV, after a small JSON of where it was sung
                                              and the takes measured before, as numbers): a job in the studio's
                                              queue, polled at /api/job/<id>, whose result is the measurement and
                                              the way of singing made from them all
    POST /api/sing/keep  {phrasing}           a way of singing this browser keeps, kept here again (by fingerprint)
    POST /api/sing/forget {name}              and forgotten here

What is kept, and where: the take's audio nowhere (it waits in memory for its turn, then goes to the measuring
process, which holds a piece of it in a temporary file while it reads it and removes it at once); the numbers
measured in the visitor's browser (they send them back with their next take); the way of singing made from
them in the browser and here, under its fingerprint, as a file of rounded numbers the studio needs to sing
it, for KEEP_DAYS after it was last used or until they forget it. No name, address or anything else about
who sang is kept with it. A recording they make carries it, as any rendition carries its singer's way.

Measuring is a heavy job, as a render is, so it waits in the studio's one queue with the renders (one heavy
job at a time: studio.Jobs) and the page says how many are ahead.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import pickle
import re
import secrets
import select
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path

from songbird.public import network

from .kit import ROOT, Kit

HERE = Path(__file__).resolve().parent
FILES = {"/sing.js": (HERE / "sing.js", "text/javascript; charset=utf-8"),
         "/sing.css": (HERE / "sing.css", "text/css; charset=utf-8"),
         "/karaoke.js": (ROOT / "tools" / "karaoke.js", "text/javascript; charset=utf-8"),
         "/recorder.js": (ROOT / "tools" / "karaoke-recorder.js", "text/javascript; charset=utf-8")}
CONSENT = 1  # the consent's version: the page asks again when what it says changes
MAX_TAKE_BYTES = 40 * 2**20  # a whole song at 48 kHz, 16-bit mono, is about 23 MB
MAX_META_BYTES = 2**20  # where it was sung, and the takes before it as numbers (about 40 kB each)
MAX_WAITING_TAKES = 3  # takes held in memory waiting for the measuring process, at once
ARRIVING = 2  # takes on their way here at once, for everyone (one from each address): each is read into memory
KEEP_DAYS = 30  # a way of singing kept here, after it was last used
MAX_PHRASING_BYTES = 256 * 2**10
IDLE = 300.0  # seconds the measuring process waits for another take before it stops, giving its memory back
TIMEOUT = 600.0  # seconds a request to it may take before it's stopped
NAME = re.compile(r"^sung-[0-9a-f]{16}$")
SINGLE = 40.0  # seconds: a take longer than this is measured in pieces (webstudio/worker.py), as long as a song
# measuring seconds for every second of a take, and a start: from this Mac (29 s for a four-minute take in pieces,
# 4.5 s for a section of 31 s) and a process's start (3 s); learned as takes are measured
PER_SECOND, START, COLD = 0.13, 1.5, 4.0


class Refused(ValueError):
    """A request the page can act on: said to the singer as it is."""


# ------------------------------------------------------------ the measuring process


class Measurer:
    """One measuring process (webstudio/worker.py), started when a take needs it and stopped when it has been
    idle for IDLE seconds (or when it failed, or took too long), so its memory is held only while people sing.
    One request at a time; the studio's queue already runs one heavy job at a time."""

    def __init__(self, kit: Kit, idle: float = IDLE, timeout: float = TIMEOUT):
        self.kit, self.idle, self.timeout = kit, idle, timeout
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.last = 0.0
        self.per_second, self.start = PER_SECOND, START
        threading.Thread(target=self._reap, daemon=True, name="songbird-measuring-reaper").start()

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def call(self, op: str, request: dict) -> dict:
        from .worker import receive, send

        with self.lock:
            if not self.running:
                self._begin()
            try:
                send(self.proc.stdin, (op, request))
            except (BrokenPipeError, OSError):
                self._end()
                raise RuntimeError("the measuring process couldn't start") from None
            del request  # the audio, if it was in it, is the process's now
            ready, _, _ = select.select([self.proc.stdout], [], [], self.timeout)
            if not ready:
                self._end()
                raise RuntimeError("measuring took too long, and was stopped")
            try:
                status, value = receive(self.proc.stdout)
            except (EOFError, OSError, pickle.UnpicklingError):
                self._end()
                raise RuntimeError("the measuring process stopped halfway (perhaps for want of memory)") from None
            self.last = time.time()
            if self.idle <= 0:  # a public studio: its memory back at once, before the next render
                self._end()
        if status == "ok":
            return value
        if status == "refused":
            raise Refused(value)
        raise RuntimeError(value)

    def _begin(self) -> None:
        """python -m webstudio.worker, from the program's folder, talking on its standard input and output."""
        self.proc = subprocess.Popen([sys.executable, "-m", "webstudio.worker", str(self.kit.root)], cwd=ROOT,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        self.last = time.time()

    def _end(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        with contextlib.suppress(OSError):
            proc.stdin.close()  # it ends by itself when its input does
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
        with contextlib.suppress(OSError):
            proc.stdout.close()

    def stop(self) -> None:
        with self.lock:
            self._end()

    def _reap(self) -> None:
        while True:
            time.sleep(min(30.0, max(self.idle / 4, 1.0)))
            if self.idle > 0 and self.running and time.time() - self.last > self.idle and self.lock.acquire(blocking=False):
                try:
                    if time.time() - self.last > self.idle:
                        self._end()
                finally:
                    self.lock.release()

    def estimate(self, seconds: float) -> float:
        """About how long measuring a take this many seconds long takes once it starts."""
        return self.start + self.per_second * seconds + (0.0 if self.running else COLD)

    def learn(self, audio_seconds: float, took: float) -> None:
        if audio_seconds > 0 and took > 0:
            self.per_second = 0.7 * self.per_second + 0.3 * max(took - self.start, 0.0) / audio_seconds


# ------------------------------------------------------------ the ways of singing kept here


class Store:
    """Ways of singing made in the browser, by fingerprint (the name "sung-" and 16 hex digits of the
    SHA-256 of their JSON): numbers only, kept KEEP_DAYS after they were last used."""

    def __init__(self, folder: Path, genome):
        self.folder = Path(folder)
        self.genome = genome

    def path(self, name: str) -> Path | None:
        if not NAME.match(str(name or "")):
            return None
        f = self.folder / f"{name}.json"
        return f if f.exists() else None

    def used(self, name: str) -> Path | None:
        f = self.path(name)
        if f is not None:
            with contextlib.suppress(OSError):
                f.touch()
        return f

    def normal(self, data) -> dict:
        """A way of singing as this studio keeps it: every gesture rounded and held to its bounds
        (songbird.phrasing), only the song's phrases, a plain description; Refused if it isn't one."""
        from songbird import phrasing as P

        if not isinstance(data, dict) or not isinstance(data.get("phrases"), dict):
            raise Refused("That isn't a way of singing.")
        if len(json.dumps(data)) > MAX_PHRASING_BYTES:
            raise Refused("That way of singing is too big.")
        phrases = self.genome.phrases
        try:
            phrasing = P.from_json(data)
        except (TypeError, ValueError, KeyError) as e:
            raise Refused("That way of singing couldn't be read.") from e
        if any(pid not in phrases or len(g) > len(phrases[pid].sung) for pid, g in phrasing.items()):
            raise Refused("That way of singing is for another song.")
        detail = re.sub(r"[^\w\s(),;.%-]", "", str(data.get("source_detail", "")))[:120]
        scale = data.get("scale") if isinstance(data.get("scale"), dict) else None
        if scale is not None:
            scale = {str(k)[:16]: float(v) for k, v in list(scale.items())[:16] if isinstance(v, (int, float))}
        return P.to_json(phrasing, source="song", source_detail=detail, **({"scale": scale} if scale else {}))

    def keep(self, data) -> tuple[str, dict]:
        data = self.normal(data)
        body = json.dumps(data, sort_keys=True)
        name = "sung-" + hashlib.sha256(body.encode()).hexdigest()[:16]
        self.folder.mkdir(parents=True, exist_ok=True)
        f = self.folder / f"{name}.json"
        if not f.exists():
            part = f.with_name(f"{name}.{secrets.token_hex(4)}.part")
            part.write_text(body + "\n")
            part.replace(f)
        f.touch()
        self.prune()
        return name, data

    def forget(self, name: str) -> bool:
        f = self.path(name)
        if f is None:
            return False
        f.unlink(missing_ok=True)
        return True

    def prune(self, days: float = KEEP_DAYS) -> None:
        cutoff = time.time() - days * 86400
        for f in self.folder.glob("sung-*.json"):
            with contextlib.suppress(OSError):
                if f.stat().st_mtime < cutoff:
                    f.unlink()


class Phrasings(Mapping):
    """The ways of singing a version may be sung, by name: those made on this computer (the studio's own
    list), and a way kept here from someone's singing in the browser, by its name, though never listed (only
    the browser that made it knows its name). Always true, so an empty list is still a lookup."""

    def __init__(self, made: dict, store: Store):
        self.made, self.store = dict(made), store

    def __getitem__(self, name):
        if name in self.made:
            return self.made[name]
        f = self.store.used(name)
        if f is None:
            raise KeyError(name)
        return f

    def __contains__(self, name) -> bool:
        return name in self.made or self.store.path(name) is not None

    def __iter__(self):
        return iter(self.made)

    def __len__(self) -> int:
        return len(self.made)

    def __bool__(self) -> bool:
        return True


# ------------------------------------------------------------ the studio's side


class Singing:
    def __init__(self, studio, kit: str | Path | None = None, measurer: Measurer | None = None, check: bool = False):
        self.studio = studio
        self.kit = Kit(kit)
        self.store = Store(Path(studio.home) / "sung", studio.genome)
        # a public studio stops the measuring process after every take, so a render never runs beside its memory
        self.measurer = measurer or Measurer(self.kit, idle=0 if getattr(studio, "public", None) else IDLE)
        self.waiting: dict[str, dict] = {}  # job key -> the take (audio and where it was sung), until it's measured
        self.arriving: set[str] = set()  # the addresses a take is on its way from now (ARRIVING at most)
        self.lock = threading.Lock()
        self.stale: str | None = None
        if check and self.kit.fits(studio.genome_path) is None:
            threading.Thread(target=self.check, daemon=True, name="songbird-singing-check").start()

    def check(self) -> None:
        """Whether the kit's templates were made by this program's measuring code (they're kept under its
        version): if not, singing is off, and says why, rather than refusing every take."""
        try:
            said = self.measurer.call("hello", {})
        except Exception as e:  # noqa: BLE001
            self.stale = f"Singing here couldn't start its measuring ({e})."
        else:
            if said["extractor"] != said["kit_extractor"]:
                self.stale = ("The singing kit was made by another version of the measuring code; it needs making "
                              "again (python -m webstudio.prepare).")
        if self.measurer.idle > 0:
            self.measurer.stop()

    # ------------------------------------------------------------ what it offers

    def why_not(self) -> str | None:
        return self.kit.fits(self.studio.genome_path) or self.stale

    def available(self) -> dict:
        why = self.why_not()
        return {"available": why is None, "web": True, **({"why": why} if why else {})}

    def offer(self) -> dict:
        why = self.why_not()
        if why:
            return {"available": False, "why": why}
        offer = self.kit.offer()
        return {"available": True, "title": offer["title"], "set": offer.get("set"), "default": offer["default"],
                "specs": [{k: s[k] for k in ("id", "key", "tempo", "duration")} for s in offer["specs"]],
                "consent": CONSENT, "keep_days": KEEP_DAYS, "max_seconds": 360, "max_bytes": MAX_TAKE_BYTES,
                "takes_an_hour": getattr(getattr(self.studio, "public", None), "takes", None),
                "measuring": {"per_second": round(self.measurer.per_second, 3), "start": self.measurer.start,
                              "cold": COLD}}

    def page(self, html: str) -> str:
        """The studio's page with the singing added: its stylesheet and script, nothing else changed."""
        return (html.replace("</head>", '<link rel="stylesheet" href="/sing.css">\n</head>', 1)
                    .replace("</body>", '<script type="module" src="/sing.js"></script>\n</body>', 1))

    # ------------------------------------------------------------ requests

    def get(self, handler, path: str, query: dict) -> bool:
        """Answer a GET that is singing's; False if it isn't one."""
        if path in FILES:
            f, kind = FILES[path]
            handler.send(f.read_bytes(), kind)
            return True
        if path == "/api/sing/offer":
            handler.send_json(self.offer())
            return True
        if path in ("/api/sing/lyrics", "/api/sing/guide"):
            spec = self.kit.spec(query.get("spec", ""))
            if spec is None or self.why_not():
                handler.fail(404, "no such version to sing to")
            elif path == "/api/sing/lyrics":
                handler.send(self.kit.lyrics(spec["id"]).read_bytes(), "application/json")
            else:
                handler.audio(self.kit.audio(spec["id"]))
            return True
        return False

    def post(self, path: str, body: dict) -> dict:
        """Answer a JSON POST that is singing's (the studio has checked it came from its own page)."""
        if path == "/api/sing/keep":
            name, data = self.store.keep(body.get("phrasing"))
            return {"name": name, "phrasing": data}
        if path == "/api/sing/forget":
            return {"forgotten": self.store.forget(str(body.get("name", "")))}
        raise Refused("not found")

    # ------------------------------------------------------------ a take

    def handle_take(self, handler) -> None:
        """POST /api/sing/take, before the studio reads any body (a take is bigger than its JSON's limit): every
        guard first, before a byte of it is read (the studio's own: its address, its key, its limit on requests,
        its page's token; then singing's: on, the visitor's takes this hour, room among the takes waiting, and
        ARRIVING takes on their way at once, one from each address), so a crowd of senders can't have the studio
        hold a take each; then the take, read whole: a JSON of where it was sung, X-Sing-Meta bytes long, and
        its WAV."""
        try:
            length = int(handler.headers.get("Content-Length") or -1)
            meta_length = int(handler.headers.get("X-Sing-Meta") or -1)
        except ValueError:
            length = meta_length = -1
        if not 0 < length <= MAX_META_BYTES + MAX_TAKE_BYTES:
            handler.close_connection = True
            return handler.fail(413, "That take is too long to measure here.")
        public = getattr(self.studio, "public", None) is not None
        refusal = handler._guard("application/x-songbird-take", "send a take")
        if refusal is None:
            refusal = self._may_take(handler, public)
        where = None
        if refusal is None:
            where = network(handler._ip())
            with self.lock:
                if where in self.arriving or len(self.arriving) >= ARRIVING:
                    refusal = lambda: handler.too_many(503, Busy(  # noqa: E731
                        "Other people's singing is on its way here; send yours again in a moment."))
                else:
                    self.arriving.add(where)
        if refusal is not None:  # the take read and dropped as it comes (a while), so the page hears why
            return handler._refuse(refusal, length, most=length, seconds=30.0)
        try:
            try:
                raw = handler._read_body(length)
            except (ValueError, TimeoutError, ConnectionError):
                handler.close_connection = True
                return handler.fail(400, "That take was cut short: send it again.")
        finally:
            with self.lock:
                self.arriving.discard(where)
        try:
            if not 0 < meta_length <= min(MAX_META_BYTES, length - 44):
                raise Refused("That take was cut short: send it again.")
            try:
                meta = json.loads(raw[:meta_length])
            except ValueError:
                meta = None
            if not isinstance(meta, dict):
                raise Refused("That take didn't say where it was sung: reload the page.")
            audio = bytes(raw[meta_length:])
            del raw
            return handler.send_json(self.take(meta, audio, handler._by() if public else None))
        except Refused as e:
            return handler.fail(400, str(e))
        except Exception as e:  # the studio's own refusals: its queue full (Busy), a visitor's limit (Limited)
            if type(e).__name__ not in ("Busy", "Limited"):
                raise
            code = 429 if type(e).__name__ == "Limited" else 503
            return handler.too_many(code, e) if public else handler.fail(code, str(e))

    def _may_take(self, handler, public: bool):
        """Why a take can't be taken now, before it's read, as the reply that says so; None if it can: singing
        off, the visitor's takes this hour (asked, not counted), or the takes waiting to be measured already."""
        why = self.why_not()
        if why:
            return lambda: handler.fail(400, why)
        gate = getattr(self.studio, "gate", None)
        if public and gate is not None:
            try:
                self.studio.jobs.one_each(handler._by()[0])
                gate.render("takes", *handler._by(), count=False)
            except Exception as e:  # noqa: BLE001 - Limited
                if type(e).__name__ != "Limited":
                    raise
                return lambda limited=e: handler.too_many(429, limited)
        jobs = self.studio.jobs
        with self.lock:
            waiting = sum(1 for k in self.waiting if jobs.live(k) is not None)
        if waiting >= MAX_WAITING_TAKES:
            busy = Busy("Other people's singing is waiting to be measured; try again in a minute.")
            return lambda: handler.too_many(503, busy) if public else handler.fail(503, str(busy))
        return None

    def where(self, meta: dict, audio: bytes) -> dict:
        """What the measuring process needs to know about a take, each part checked: the version and guide it
        was sung to (one offered, the one on the page), where on the guide's clock it starts and was meant to
        end, and its length against those."""
        import io

        import soundfile as sf

        why = self.why_not()
        if why:
            raise Refused(why)
        spec = self.kit.spec(str(meta.get("spec", "")))
        if spec is None:
            raise Refused("That version isn't one this studio offers: reload the page.")
        if meta.get("guide") != spec["guide"]:
            raise Refused("The guide changed while you sang: reload the page and sing it again.")
        try:
            from_s, to_s = float(meta.get("from_s", 0.0)), float(meta.get("to_s", spec["duration"]))
        except (TypeError, ValueError):
            raise Refused("That take didn't say where it was sung: reload the page.") from None
        if not (0.0 <= from_s < to_s <= spec["duration"] + 0.5):
            raise Refused("That take isn't inside its guide: reload the page.")
        try:
            info = sf.info(io.BytesIO(audio))
        except Exception as e:  # noqa: BLE001
            raise Refused("That take couldn't be read as a WAV file.") from e
        if info.duration > (to_s - from_s) + 10.0:
            raise Refused("That take is longer than what it was sung to.")
        earlier = meta.get("earlier") or []
        if not isinstance(earlier, list) or len(earlier) > 11:
            raise Refused("A way of singing is made from at most 12 takes: start again to sing more.")
        return {"song": self.kit.offer()["song"], "guide": spec["guide"], "from_s": from_s, "to_s": to_s,
                "earlier": earlier, "offered": [s["guide"] for s in self.kit.offer()["specs"]],
                "seconds": float(info.duration)}

    def take(self, meta: dict, audio: bytes, by: tuple[str, str] | None = None) -> dict:
        """A take waiting to be measured, in the studio's queue: the job, how many are ahead of it and about
        how long measuring it takes once it starts. by: a public studio's visitor and address, who may have one
        thing in the queue at a time and a few takes an hour (songbird/public.py "takes"), as for renders."""
        request = self.where(meta, audio)
        gate = getattr(self.studio, "gate", None)
        limits = {"whole": request["to_s"] - request["from_s"] > SINGLE}
        if by is not None and gate is not None:
            visitor, ip = by
            limits.update(owner=visitor, where=network(ip), admit=lambda: gate.render("takes", visitor, ip))
        jobs = self.studio.jobs
        with self.lock:
            for key in [k for k in self.waiting if jobs.live(k) is None]:  # cancelled or gone: its audio goes too
                self.waiting.pop(key, None)
            if len(self.waiting) >= MAX_WAITING_TAKES:
                raise Busy("Other people's singing is waiting to be measured; try again in a minute.")
            key = "sing:" + secrets.token_hex(8)
            self.waiting[key] = {**request, "audio": audio}
        del audio
        try:
            job = jobs.submit(key, "measure", "your singing", lambda job, key=key: self._measure(job, key), **limits)
        except Exception:
            with self.lock:
                self.waiting.pop(key, None)
            raise
        return jobs.view(job) | {"estimate": round(self.measurer.estimate(request["seconds"]))}

    def _measure(self, job, key: str) -> dict:
        with self.lock:
            request = self.waiting.pop(key, None)
        if request is None:
            raise RuntimeError("the take was let go before it could be measured")
        job.stage = "listening to how you sang"
        job.progress = 0.05
        seconds = request.pop("seconds")
        try:
            result = self.measurer.call("take", request)
        except Refused as e:  # the singer's to act on: said as it is, not as a failure
            return {"refused": str(e)}
        finally:
            request = None  # the audio: never kept past this
        self.measurer.learn(result.get("audio_seconds", seconds), result.get("seconds", 0.0))
        name, phrasing = self.store.keep(result["phrasing"])
        return {"measurement": result["measurement"], "name": name, "phrasing": phrasing,
                "portrait": result["portrait"], "skipped": result.get("skipped", []),
                "seconds": result.get("seconds"), "audio_seconds": result.get("audio_seconds")}

    # ------------------------------------------------------------ the studio's versions

    def lookup(self, made: dict) -> Phrasings:
        return Phrasings(made, self.store)

    def listed(self, edits: dict) -> list[dict]:
        """The way of singing the edits name, if it is one kept here from the browser: for the singer's card
        ("sung your way"). Only the page that chose it sees it."""
        name = str((edits or {}).get("phrasing") or "")
        f = self.store.path(name)
        if f is None:
            return []
        detail = ""
        with contextlib.suppress(OSError, ValueError):
            detail = json.loads(f.read_text()).get("source_detail", "")
        return [{"id": name, "label": "you", "way": "your way", "detail": detail}]

    def close(self) -> None:
        self.measurer.stop()


class Busy(Exception):
    """Too many takes waiting: the studio answers 503, as for renders."""
