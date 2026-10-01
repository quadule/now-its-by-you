"""The studio on the visitor's device: every question the page asks (/api/*), answered in the browser by the studio's
own code (songbird/studio.py), in the long-lived worker the page starts (songbird/studio/device.js, through
web/studio-wasm/studio-worker.mjs). docs/WEB-STUDIO.md, "On the device".

The page sends what it would send a server (the path, the JSON, the version its token names) and gets back what a
server would answer: the same routes (studio.asked, studio.answer), the same studio (a DeviceStudio is a Studio),
the same statuses for the same refusals. What differs is only what a server can't be here:

- **No renders.** The page's renderer makes every preview and recording in a render worker of its own
  (studio_render.py), from the render spec asked here (Studio.render_spec). /api/listen, /api/record and the
  render queue are never asked for on the device.
- **No threads** (Pyodide has none): the studio's queue has no thread (Studio.threads); the few jobs the device
  takes (a sung take's measuring) are made between requests (Device.work).
- **A version someone brought, or shared,** is read here (received.examine: the archive by hand, two members as
  strict JSON, the song, the record cleaned, the audio against the record's id, the version tried), in this
  process rather than one of its own (it is the visitor's own browser), and as ever never running, importing or
  unpacking anything of the packet's program. The page keeps what was read (the record, the song, its timeline: never
  the audio) in the browser's storage and gives it back at start (Device.restore).
- **Files** a server would offer at an address (the MIDI file, the piano page's score) are handed to the page, which
  keeps them as the browser keeps things (a Blob, local storage).
- **Singing**: a take's measurement is sing_measure.measure (made for the browser elsewhere), if it is here and the
  singing kit is too; until then singing says it isn't available yet.

    Device(config).handle(method, path, query, version, body, headers) -> {"status", "json", "file"?, ...}
"""

from __future__ import annotations

import contextlib
import json
import tempfile
import traceback
from pathlib import Path

from songbird import public as public_mod
from songbird import received
from songbird import studio as studio_mod
from songbird.studio import Busy, NotFound, Studio

NOT_YET = "Singing here isn't available yet."
NO_STEMS = ("The parts can't be made in the browser yet. Record it, then open the recording with Python on a "
            "computer (python3 the-file.flac studio) to make them.")
THINKING = 300.0  # seconds the program may take to read a version brought here: a server's 40 is for its own CPU, and
# a slow phone shouldn't be refused for being slow
KEY = b"songbird-device"  # a version's id here: not secret (there is no one to hide it from on one's own device)


class DeviceVersions:
    """The versions read on this device, as data, by id: the page's storage keeps them across visits (the record, the
    song, the timeline), and gives them back at start. Shared: one with a link (the hosting site's id), else a file
    the visitor brought."""

    days = float("inf")

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.shared: dict[str, bool] = {}

    def put(self, vid: str, record: dict, genome: bytes, timeline: dict | None, shared: bool) -> str:
        if not received.VERSION.fullmatch(vid or ""):
            raise ValueError("a version's id is 32 hex digits")
        folder = self.folder / vid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "genome.json").write_bytes(genome)
        (folder / "record.json").write_text(json.dumps(record))
        if timeline is not None:
            (folder / "timeline.json").write_text(json.dumps(timeline))
        self.shared[vid] = bool(shared)
        return vid

    def get(self, vid: str):
        if not received.VERSION.fullmatch(vid or ""):
            return None
        folder = self.folder / vid
        with contextlib.suppress(OSError, ValueError):
            record = json.loads((folder / "record.json").read_text())
            timeline = None
            with contextlib.suppress(OSError, ValueError):
                timeline = json.loads((folder / "timeline.json").read_text())
            return record, folder / "genome.json", timeline
        return None

    def prune(self) -> None:  # the page's storage is the visitor's to clear
        pass


class DeviceStudio(Studio):
    """The studio as it is on a visitor's device: this computer's own in what it may do (no limits, no queue to share,
    no key), a neutral or made-up machine (the device's own isn't measured), and no checkout beside it."""

    threads = False
    makes_specs = True  # every render is made in the browser, from its spec
    device = True
    singing_why = NOT_YET

    def __init__(self, song: str, machine: str = "none", home: str | Path | None = None, runs_with: dict | None = None):
        super().__init__(song=song, machine=machine, home=Path(home or tempfile.mkdtemp(prefix="songbird-")))
        self.versions = DeviceVersions(self.home / "versions")
        self._runs_with = runs_with

    def runs_with(self) -> dict:
        """The release's Python and pinned dependencies, as its build recorded them (build_site.py): a recording made
        here says what to run it with on a computer, never Pyodide's."""
        return dict(self._runs_with) if self._runs_with else super().runs_with()

    def render_spec(self, edits: dict, who: str = "you", section: int | None = None) -> dict:
        """As the studio's own, and for a whole song estimated past what a browser holds (public.BROWSER_MB), a word
        of warning: it is made all the same (every device tries)."""
        answer = super().render_spec(edits, who, section)
        if section is None and "spec" in answer:
            seconds, parts = self.whole_cost(self.version(edits, who))
            if not self.fits_browser(seconds, parts):
                answer["warn"] = (f"a long version ({seconds / 60:.1f} minutes), which may need more memory than a "
                                  "browser has")
        return answer

    # what a checkout or a server has, and a device hasn't
    def phrasing_files(self) -> dict[str, Path]:
        return {}

    def out_shown(self) -> str:
        return ""

    def packet_note(self) -> str:
        return ""

    def sing_available(self) -> dict:
        if self.singing is not None:
            return self.singing.available()
        return {"available": False, "why": self.singing_why}

    def sing(self) -> dict:
        return {"error": self.sing_available().get("why") or NOT_YET}

    def export(self, edits: dict, what: str, by=None) -> dict:
        if what == "stems":
            raise ValueError(NO_STEMS)
        return super().export(edits, what, by)

    def listen(self, *args, **kwargs) -> dict:
        raise NotFound("Songs are made by the page here, not asked for.")

    def record(self, *args, **kwargs) -> dict:
        raise NotFound("Songs are made by the page here, not asked for.")

    def start_view(self) -> dict:
        start = super().start_view()
        start["device"] = True
        return start

    def version_view(self) -> dict | None:
        view = super().version_view()
        if view is not None:
            shared = self.versions.shared.get(self.version_id, False)
            view["shared"] = shared
            view["url"] = f"/v/{self.version_id}" if shared else f"/#version={self.version_id}"
        return view


class Device:
    """The page's questions answered (handle), a version someone brought kept (restore: examine reads it, in a worker
    of its own), the jobs made (work)."""

    def __init__(self, config: dict):
        received.THINKING = max(received.THINKING, THINKING)
        self.config = config
        self.studio = DeviceStudio(config["song"], config.get("machine") or "none", config.get("home"),
                                   config.get("runs_with"))
        self.studio.singing_why = config.get("singing_why") or NOT_YET
        self._singing(config)

    def _singing(self, config: dict) -> None:
        """Singing, if its measurement is here (sing_measure, made for the browser) and the kit it measures against."""
        kit = config.get("sing_kit")
        if not kit:
            return
        try:
            import sing_measure  # noqa: F401 - another part of the work: until it's here, singing isn't

            from webstudio.singing import Singing
        except Exception:  # noqa: BLE001 - absent, or not runnable here: said, not raised
            return
        self.studio.singing = Singing(self.studio, kit, measurer=Measuring())

    @property
    def view(self) -> dict:
        s = self.studio
        return {"program": s.program_digest, "song": s.song_digest, "machine": s.machine, "day": s.day,
                "title": s.genome.title}

    # ------------------------------------------------------------ as the worker hands them over (studio-worker.mjs)
    # what comes in through a file in Pyodide's memory (BODY: a request's body, a version's file); what goes out as
    # JSON text, the answer's own JSON as text inside it

    @staticmethod
    def _wire(out: dict) -> str:
        said = {"status": out["status"], "json": json.dumps(out["json"]) if "json" in out else None}
        if "file" in out:
            said["file"] = out["file"]
        return json.dumps(said)

    def handle_wire(self, method, path, query, version, body_path, headers) -> str:
        body = Path(body_path).read_bytes()
        Path(body_path).unlink(missing_ok=True)
        return self._wire(self.handle(method, path, query, version, body, {str(k).lower(): v for k, v in headers.items()}))

    def restore_wire(self, vid, record, genome, timeline, shared) -> str:
        ok = self.restore(vid, record, genome, timeline, shared)
        return self._wire({"status": 200 if ok else 404, "json": {"restored": ok}})

    # ------------------------------------------------------------ the page's questions

    def _for(self, version: str | None, path: str) -> Studio | None:
        if version is None or path.startswith("/api/sing"):  # singing is the song's own, as on a server
            return self.studio
        return self.studio.opened(version)

    def handle(self, method: str, path: str, query: dict | None = None, version: str | None = None,
               body: bytes | None = None, headers: dict | None = None) -> dict:
        """One request, as the server's Handler answers it once it is through its guards."""
        try:
            return self._handle(method, path, query or {}, version or None, body or b"", headers or {})
        except NotFound as e:
            return {"status": 404, "json": {"error": str(e)}}
        except Busy as e:
            return {"status": 503, "json": {"error": str(e)}}
        except public_mod.Limited as e:
            return {"status": 429, "json": {"error": str(e)}}
        except public_mod.TooLong as e:
            return {"status": 422, "json": {"error": str(e), "too_long": True}}
        except (ValueError, KeyError, TypeError) as e:
            return {"status": 400, "json": {"error": str(e)}}
        except MemoryError:
            return {"status": 500, "json": {"error": "This browser ran out of memory answering that."}}
        except Exception as e:  # noqa: BLE001 - said on the page, as the server says it
            traceback.print_exc()
            return {"status": 500, "json": {"error": f"{type(e).__name__}: {e}"}}

    def _handle(self, method, path, query, version, body, headers) -> dict:
        studio = self._for(version, path)
        if studio is None:
            raise NotFound("This version isn't kept in this browser any more. Open its file, or its link, again.")
        if method == "GET":
            if path in studio_mod.QUESTIONS or path.startswith("/api/job/"):
                return {"status": 200, "json": studio_mod.asked(studio, path)}
            if path.startswith("/api/sing/") and studio.singing is not None:
                return self._sing_get(studio, path, query)
            raise NotFound("not found")
        if method != "POST":
            raise NotFound("not found")
        if path == "/api/sing/take":
            return self._take(studio, body, headers)
        if len(body) > 2**20:
            raise ValueError("too much")
        data = json.loads(body or b"{}")
        if not isinstance(data, dict) or not isinstance(data.get("edits") or {}, dict):
            raise ValueError("send a map, with the edits a map of choices")
        if path == "/api/open/ready":  # nothing to wait for here: the file is read on this device
            return {"status": 200, "json": {"ready": True}}
        out = {"status": 200, "json": studio_mod.answer(studio, path, data, None)}
        return self._files(studio, path, out)

    def _files(self, studio: Studio, path: str, out: dict) -> dict:
        """A file a server would offer at an address, handed to the page instead (its path in this worker's memory)."""
        answer = out["json"]
        if path == "/api/export" and isinstance(answer, dict) and str(answer.get("url", "")).startswith("/export/"):
            key, _, rest = answer["url"][len("/export/"):].partition("?")
            name = rest.partition("name=")[2] or "song.mid"
            out["file"] = {"path": str(studio.cache / key), "type": "audio/midi", "name": name}
        if path == "/api/piano" and isinstance(answer, dict) and answer.get("key"):
            out["file"] = {"path": str(studio.cache / f"{answer['key']}.piano.json"), "type": "application/json",
                           "name": f"{answer['key']}.json"}
        return out

    # ------------------------------------------------------------ someone's version, read here

    def restore(self, vid: str, record: dict, genome: str, timeline: dict | None, shared: bool) -> bool:
        """A version this device read before, given back from the page's storage: kept again as it was read (a record
        cleaned and a song checked by this program; one another program cleaned is read again by the page)."""
        try:
            self.studio.versions.put(vid, record, genome.encode("utf-8"), timeline, shared)
            return self.studio.opened(vid) is not None
        except (ValueError, KeyError, TypeError, OSError):
            return False

    # ------------------------------------------------------------ the jobs a device makes (between requests)

    def work(self) -> int:
        """Every job waiting, made one at a time (a sung take's measuring): how many."""
        jobs = self.studio.jobs
        made = 0
        while True:
            with jobs.lock:
                if not jobs.pending:
                    return made
                job = jobs._next()
                job.state = "running"
            jobs._work(job)
            made += 1

    # ------------------------------------------------------------ singing, when its measurement is here

    def _sing_get(self, studio: Studio, path: str, query: dict) -> dict:
        singing = studio.singing
        if path == "/api/sing/offer":
            return {"status": 200, "json": singing.offer()}
        if path in ("/api/sing/lyrics", "/api/sing/guide"):
            spec = singing.kit.spec(str(query.get("spec", "")))
            if spec is None or singing.why_not():
                raise NotFound("no such version to sing to")
            if path == "/api/sing/lyrics":
                return {"status": 200, "file": {"path": str(singing.kit.lyrics(spec["id"])), "type": "application/json"}}
            return {"status": 200, "file": {"path": str(singing.kit.audio(spec["id"])), "type": "audio/flac"}}
        raise NotFound("not found")

    def _take(self, studio: Studio, body: bytes, headers: dict) -> dict:
        """A take (a JSON of where it was sung, X-Sing-Meta bytes long, then its WAV): measured here between
        requests, as the server's queue would; the page polls its job."""
        from webstudio import singing as singing_mod

        if studio.singing is None:
            raise ValueError(self.studio.sing_available().get("why") or NOT_YET)
        try:
            meta_length = int(headers.get("x-sing-meta") or -1)
        except ValueError:
            meta_length = -1
        if not 0 < len(body) <= singing_mod.MAX_META_BYTES + singing_mod.MAX_TAKE_BYTES \
                or not 0 < meta_length <= min(singing_mod.MAX_META_BYTES, len(body) - 44):
            raise ValueError("That take was cut short: send it again.")
        try:
            meta = json.loads(body[:meta_length])
        except ValueError:
            meta = None
        if not isinstance(meta, dict):
            raise ValueError("That take didn't say where it was sung: reload the page.")
        try:
            return {"status": 200, "json": studio.singing.take(meta, bytes(body[meta_length:]), None)}
        except singing_mod.Refused as e:
            raise ValueError(str(e)) from None


# ---------------------------------------------------------------- someone's version, read on this device
# In a worker of its own (the page's shim starts one for each file, and lets it go after: a hostile file's worst is
# done to a worker that holds nothing and is thrown away), never in the studio's.


def examine(path: str | Path, title: str, machine: str, day: str, vid: str | None = None) -> dict:
    """A version's file, read as data (received.examine: never its program), as the page keeps it: under `vid` (a
    shared link's id) or its own (a file the visitor brought: the same file, the same id, on any visit). {"status":
    422, "json": {"error"}} if this program can't continue it, saying why."""
    received.THINKING = max(received.THINKING, THINKING)
    try:
        out = received.examine(path, title, machine, day)
    except received.Refused as e:
        return {"status": 422, "json": {"error": str(e)}}
    except MemoryError:
        return {"status": 422, "json": {"error": "It took more memory to read than this browser had to give."}}
    finally:
        Path(path).unlink(missing_ok=True)
    record, song = out["record"], out["genome"]
    shared = vid is not None
    if shared and not received.VERSION.fullmatch(vid):
        return {"status": 404, "json": {"error": "That isn't a version's link."}}
    vid = vid or received.version_id(KEY, record, song.encode("utf-8"))
    return {"status": 200, "json": {"id": vid, "url": f"/v/{vid}" if shared else f"/#version={vid}",
                                    "shared": shared, "record": record, "genome": song,
                                    "timeline": out.get("timeline"), "minutes": out.get("minutes")}}


def examine_wire(body_path: str, title: str, machine: str, day: str, vid: str | None = None) -> str:
    return Device._wire(examine(body_path, title, machine, day, vid))


class Measuring:
    """The measuring process's stand-in on the device: a take measured here, by sing_measure.measure (the same
    answer as webstudio/worker.py's "take"), between requests."""

    idle = 0.0
    per_second, start = 0.13, 1.5

    def call(self, op: str, request: dict) -> dict:
        if op != "take":
            raise RuntimeError(f"no {op} here")
        import sing_measure

        take = request.pop("audio")
        return sing_measure.measure(take, request)

    def estimate(self, seconds: float) -> float:
        return self.start + self.per_second * seconds

    def learn(self, audio_seconds: float, took: float) -> None:
        if audio_seconds > 0 and took > 0:
            self.per_second = 0.7 * self.per_second + 0.3 * max(took - self.start, 0.0) / audio_seconds

    def stop(self) -> None:
        pass

    running = False
