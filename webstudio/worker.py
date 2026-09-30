"""The measuring process: a take sung in the web studio measured, and its audio gone (docs/WEB-SINGING.md).

The studio starts one of these when the first take waits (webstudio/singing.py Measurer), hands it one request
at a time, and stops it when it has been idle a while, so the memory measuring needs is held only while
someone sings. It measures exactly as tools/phrasing.py measures a take on the artist's computer, with two
differences, both for a server:

- **No forced aligner.** MFA (tools/align.py) isn't here, so each vowel's start is found where its loudness
  climbs out of the consonant before it, as it was before MFA (docs/PHRASING-CALIBRATION.md has what that
  costs). No speech recogniser is needed either: faster-whisper reads plain readings, never sung takes, so
  it isn't loaded (a stand-in that refuses to work is put in its place, should anything reach for it).
- **Long takes in pieces.** WORLD's pitch tracker holds about 14 MB for every second it analyses at once, so
  a take of the whole song (four minutes: 3.4 GB) is measured a section at a time, cut in the rests between
  sung sections, each piece as tools/phrasing.py measures a take of one section (measure_window). A take of
  one section is measured whole, as it would be there.

The audio arrives as bytes, is decoded in memory, and each piece measured is written to a temporary file
(tools/phrasing.py reads takes from files) in /dev/shm where there is one (memory, never a disk), else the
system's temporary folder, readable by this user alone, and removed as soon as it has been read, whatever
happens. Only numbers come back.

    python -m webstudio.worker KIT      the loop, on its standard input and output: one (op, request) at a
                                        time, each a length and a pickle (the studio is its only reader):
                                        "take" -> the take's measurement and the phrasing made with it;
                                        "measure", "phrasing" -> each alone; "hello" -> what this process is
"""

from __future__ import annotations

import contextlib
import io
import os
import pickle
import resource
import sys
import tempfile
import time
import traceback
import types
from collections import Counter
from dataclasses import fields
from pathlib import Path

import numpy as np

from .kit import ROOT, Kit

SINGLE = 40.0  # seconds: a take this long or shorter is measured whole (a section's window: 31 s at 90%, 38 s at 80%)
BIG_REST = 3.0  # seconds without a note: where a long take is cut into pieces (the turns between sections)
LEAD, TAIL = 2.0, 1.0  # seconds of a piece kept before its first note and after its window, for its lag and release
MAX_PIECE = 40.0  # seconds: no piece longer (a piece's rest is cut at its longest silence until none is)
MIN_SECONDS, MAX_SECONDS = 3.0, 360.0
MAX_TAKES = 12  # measurements a phrasing is made from at once
SCRATCH_PREFIX = "songbird-take-"


class Refused(Exception):
    """A take or request this studio can't measure, with what the singer can do about it."""


class NoTemplate(Refused):
    def __init__(self, key: int):
        way = "above" if key > 0 else "below"
        super().__init__(f"Your take sat {abs(key)} semitones {way} the guide's key. This studio can measure a take "
                         "sung in the guide's key or an octave from it: choose the key nearest your voice and sing it "
                         "again.")
        self.key = key


# ------------------------------------------------------------ the measuring tools, pointed at the kit


def _no_whisper() -> types.ModuleType:
    """faster-whisper's place taken by a module that refuses: tools/phrasing.py imports it for plain readings,
    which the web studio never measures (and loading it costs 30 MB and seconds for nothing)."""
    stub = types.ModuleType("faster_whisper")

    class WhisperModel:  # noqa: D401
        def __init__(self, *args, **kwargs):
            raise RuntimeError("the web studio measures sung takes only: no speech recogniser here")

    stub.WhisperModel = WhisperModel
    return stub


class Tools:
    """tools/phrasing.py, tools/takes.py and tools/guides.py, reading and writing only inside the kit."""

    def __init__(self, kit: Kit):
        os.environ["MFA"] = "off"  # tools/align.py: without the forced aligner, whatever is installed
        if "faster_whisper" not in sys.modules:
            sys.modules["faster_whisper"] = _no_whisper()
        tools = str(ROOT / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import warnings

        warnings.filterwarnings("ignore", message="pkg_resources")
        import guides as M  # noqa: E402
        import phrasing as T  # noqa: E402
        import takes as K  # noqa: E402

        from songbird import genome as G

        K.GUIDES = kit.guides
        M.GUIDES = kit.specs
        T.MEASURED = kit.measured
        self.kit, self.T, self.K, self.M, self.G = kit, T, K, M, G
        self.extractor = T.version()
        self._genomes: dict = {}

    def genome(self, song: str):
        path = self.kit.genome(song)
        if song not in self._genomes:
            self._genomes[song] = (path, self.G.load(path))
        return self._genomes[song]

    def guide(self, song: str, digest: str):
        """The guide a take was sung to, from the kit alone (never the checkout's), its templates guarded."""
        if self.K.guide_score(song, digest) is None:
            raise Refused("This guide isn't one this studio offers: reload the page.")
        path, genome = self.genome(song)
        g = self.T.guide(path, genome, digest)
        if not isinstance(g.templates, Templates):
            g.templates = Templates(g, self)
        return g


class Templates(dict):
    """A guide's template analyses, by key: one the kit carries is loaded from it (tools/phrasing.py
    template() does that when the key isn't here yet); any other is refused, since making one takes 4 GB."""

    def __init__(self, g, tools: Tools):
        super().__init__(g.templates)
        self.g, self.tools = g, tools

    def __contains__(self, key) -> bool:
        if dict.__contains__(self, key):
            return True
        kept = self.tools.T.MEASURED / "templates" / f"{self.g.digest}.{key:+d}.{self.tools.extractor}.npz"
        if kept.exists():
            return False  # template() loads it
        raise NoTemplate(int(key))


# ------------------------------------------------------------ a take's audio, briefly


def scratch_dir() -> Path:
    """Where a piece of a take waits while it is read: memory (/dev/shm) where there is some, else /tmp."""
    shm = Path("/dev/shm")
    if shm.is_dir() and os.access(shm, os.W_OK):
        return shm
    return Path(tempfile.gettempdir())


def sweep(older_than: float = 3600.0) -> int:
    """Remove pieces left by a measuring process that was stopped halfway (killed, say, for its memory)."""
    gone = 0
    for f in scratch_dir().glob(f"{SCRATCH_PREFIX}*"):
        with contextlib.suppress(OSError):
            if time.time() - f.stat().st_mtime > older_than:
                f.unlink()
                gone += 1
    return gone


@contextlib.contextmanager
def briefly(y: np.ndarray, sr: int):
    """A piece of a take as a WAV file readable by this user alone, removed when the block ends, however."""
    import soundfile as sf

    fd, name = tempfile.mkstemp(prefix=SCRATCH_PREFIX, suffix=".wav", dir=scratch_dir())
    try:
        with os.fdopen(fd, "wb") as f:
            sf.write(f, y, sr, format="WAV", subtype="FLOAT")
        yield Path(name)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(name)


def decode(audio: bytes) -> tuple[np.ndarray, int]:
    """A take's WAV bytes as mono float32 samples and their rate; Refused if it isn't a take this can use."""
    import soundfile as sf

    try:
        y, sr = sf.read(io.BytesIO(audio), dtype="float32", always_2d=True)
    except Exception as e:  # noqa: BLE001  (whatever the file is, it's not a WAV this can read)
        raise Refused("That take couldn't be read as a WAV file.") from e
    if not 8000 <= sr <= 192000:
        raise Refused("That take's sample rate isn't one a microphone records at.")
    seconds = len(y) / sr
    if seconds < MIN_SECONDS:
        raise Refused("That take is too short to measure: sing a little more.")
    if seconds > MAX_SECONDS:
        raise Refused("That take is longer than the song.")
    return np.ascontiguousarray(y.mean(axis=1), dtype=np.float32), int(sr)


# ------------------------------------------------------------ measuring


def pieces(notes, a: float, b: float) -> list[tuple[float, float]]:
    """The stretches [from, to) of guide time a take from a to b is measured in: the whole of it if it is short
    (SINGLE), else cut in the middle of every rest of BIG_REST or more between the notes that start inside it,
    and any piece still longer than MAX_PIECE at its longest rest, until none is."""
    if b - a <= SINGLE:
        return [(a, b)]
    inside = sorted((n for n in notes if a <= n.start < b), key=lambda n: n.start)
    rests = [((m.start + n.start + n.dur) / 2, m.start - (n.start + n.dur)) for n, m in zip(inside, inside[1:])]
    cuts = [t for t, gap in rests if gap >= BIG_REST]
    out = []
    for lo, hi in zip([a, *cuts], [*cuts, b]):
        out += _split(lo, hi, rests)
    return out


def _split(lo: float, hi: float, rests) -> list[tuple[float, float]]:
    first = [(t, gap) for t, gap in rests if lo < t < hi]
    if hi - lo <= MAX_PIECE or not first:
        return [(lo, hi)]
    t = max(first, key=lambda r: r[1])[0]
    return _split(lo, t, rests) + _split(t, hi, rests)


def measure(tools: Tools, request: dict) -> dict:
    """One take: its measurement (tools/phrasing.py measured()'s shape, with where it was sung), how long
    measuring it took and this process's peak memory. request: song, guide (digest), from_s, to_s, audio."""
    began = time.time()
    T = tools.T
    g = tools.guide(str(request["song"]), str(request["guide"]))
    y, sr = decode(request.pop("audio"))
    from_s = float(request["from_s"])
    end = from_s + len(y) / sr
    to_s = min(float(request["to_s"]), end)
    if not to_s > from_s:
        raise Refused("That take ends before it begins.")
    results, refused = [], []
    for a, b in pieces(g.notes, from_s, to_s):
        if b - a <= SINGLE and (a, b) == (from_s, to_s):  # the take whole, as tools/phrasing.py measures one section
            i0, start = 0, from_s
        else:  # a piece: from a moment before its first note, so its lag can be found
            first = min((n.start for n in g.notes if a <= n.start < b), default=a)
            start = max(a, first - LEAD)
            i0 = int(round((start - from_s) * sr))
            start = from_s + i0 / sr
        i1 = len(y) if (a, b) == (from_s, to_s) else min(len(y), int(round((b + TAIL - from_s) * sr)))
        if i1 - i0 < int(MIN_SECONDS * sr / 3):
            continue
        with briefly(y[i0:i1], sr) as path:
            try:
                results.append(T.measure_window(path, g, start, b))
            except NoTemplate as e:
                refused.append(e)
    del y
    if not results:
        raise refused[0] if refused else Refused("No note of the song was sung in that take.")
    notes, lags, keys = [], [], Counter()
    for k in range(len(g.notes)):
        mine = next((r["notes"][k] for r in results if r["notes"][k]["onset"] is not None), None)
        notes.append(mine or results[0]["notes"][k])
    for r in results:
        sung = sum(1 for n in r["notes"] if n["onset"] is not None)
        if sung:
            lags.append(r["lag"])
            keys[r["key"]] += sung
    if not any(n["onset"] is not None for n in notes):
        raise Refused("No note of the song was sung in that take: sing along with the words as they light up.")
    return {
        "measurement": {
            "take": "a take", "stamp": {"guide": g.digest, "extractor": tools.extractor, "window": T.window_version(),
                                        "aligner": None, "from_s": round(from_s, 4), "to_s": round(to_s, 4)},
            "lag": float(np.median(lags)) if lags else 0.0, "key": keys.most_common(1)[0][0] if keys else 0,
            "window": [round(from_s, 4), round(to_s, 4)], "aligner": None, "fields": results[0]["fields"],
            "pieces": [r["window"] + [r["lag"], r["key"]] for r in results], "notes": notes},
        "skipped": [e.key for e in refused],
        "audio_seconds": round(end - from_s, 2),
        "seconds": round(time.time() - began, 2),
        "peak_mb": peak_mb(),
    }


def peak_mb() -> int:
    """This process's peak resident memory so far, in MB (Linux counts it in kB, macOS in bytes)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak / (2**20 if sys.platform == "darwin" else 2**10))


# ------------------------------------------------------------ a phrasing from measurements


def checked(tools: Tools, song: str, data, offered: set[str]) -> dict:
    """A measurement the page sent back, held to the shape measure() gives: its guide one offered, a note for
    every note of it in order, every number finite. Refused if not (a forged one could only mislead its
    sender's own phrasing, which is bounded anyway, but it mustn't break anything)."""
    T = tools.T
    if not isinstance(data, dict) or not isinstance(data.get("stamp"), dict):
        raise Refused("A take's numbers were damaged: start again.")
    digest = str(data["stamp"].get("guide", ""))
    if digest not in offered:
        raise Refused("A take was sung to a guide this studio no longer offers: start again.")
    g = tools.guide(song, digest)
    names = list(data.get("fields") or [])
    notes = data.get("notes")
    if names != [f.name for f in fields(T.P.Gesture)]:
        raise Refused("A take's numbers were made by another version of this studio: start again.")
    if not isinstance(notes, list) or len(notes) != len(g.notes):
        raise Refused("A take's numbers don't fit the guide: start again.")

    def number(v, lo=-1e6, hi=1e6):
        return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v) and lo <= v <= hi)

    out = []
    for k, (n, note) in enumerate(zip(notes, g.notes)):
        if not isinstance(n, dict) or n.get("phrase") != note.phrase or n.get("index") != T.index_in_phrase(g.notes, k):
            raise Refused("A take's numbers don't fit the guide: start again.")
        gesture = n.get("gesture")
        if not (number(n.get("onset")) and number(n.get("off")) and
                (gesture is None or (isinstance(gesture, list) and len(gesture) == len(names) and all(map(number, gesture))))):
            raise Refused("A take's numbers were damaged: start again.")
        out.append({"phrase": note.phrase, "index": n["index"], "start": round(note.start, 4), "onset": n.get("onset"),
                    "off": n.get("off"), "gesture": gesture})
    lag, key = data.get("lag"), data.get("key")
    if not (number(lag, -60, 60) and lag is not None and isinstance(key, int) and not isinstance(key, bool) and -48 <= key <= 48):
        raise Refused("A take's numbers were damaged: start again.")
    return {"take": "a take", "stamp": {"guide": digest}, "lag": float(lag), "key": key, "fields": names, "notes": out}


def phrasing(tools: Tools, request: dict) -> dict:
    """A phrasing made from one visitor's measured takes (each person counts once, and they are one person),
    the file's JSON, and a few plain sentences about how they sang. request: song, measurements, offered."""
    from songbird.realize import choose_params

    T = tools.T
    song = str(request["song"])
    given = request.get("measurements") or []
    if not isinstance(given, list) or not 1 <= len(given) <= MAX_TAKES:
        raise Refused(f"A way of singing is made from 1 to {MAX_TAKES} takes.")
    offered = set(request.get("offered") or [])
    data = [checked(tools, song, d, offered) for d in given]
    for i, d in enumerate(data):
        d["take"] = f"Take {i + 1}"
    path, genome = tools.genome(song)
    try:
        ph, out, portrait = T.singer_phrasing(path, genome, [""] * len(data), None, data)
    except ValueError as e:  # none of them sang a whole note
        raise Refused("None of your takes sang a whole note of the song.") from e
    return {"phrasing": out, "portrait": T.describe(portrait, choose_params(genome).tempo)}


def take(tools: Tools, request: dict) -> dict:
    """A take measured, and the phrasing made from it with the takes measured before it (the page keeps
    those, as numbers, and sends them back)."""
    measured = measure(tools, request)
    made = phrasing(tools, {"song": request["song"], "offered": request.get("offered") or [],
                            "measurements": [*(request.get("earlier") or []), measured["measurement"]]})
    return {**measured, **made, "peak_mb": peak_mb()}


def hello(tools: Tools, request: dict) -> dict:
    offer = tools.kit.offer() or {}
    return {"extractor": tools.extractor, "kit_extractor": offer.get("extractor"), "peak_mb": peak_mb(), "pid": os.getpid()}


OPS = {"measure": measure, "phrasing": phrasing, "take": take, "hello": hello}


def send(f, message) -> None:
    """One message on a pipe: its length, then its pickle."""
    data = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    f.write(len(data).to_bytes(8, "big"))
    f.write(data)
    f.flush()


def _read(f, size: int) -> bytes:
    """Exactly size bytes from a pipe (a raw one hands them over as they come); EOFError if it ends first."""
    parts, left = [], size
    while left:
        part = f.read(left)
        if not part:
            raise EOFError
        parts.append(part)
        left -= len(part)
    return b"".join(parts)


def receive(f):
    """One message from a pipe (send()'s); EOFError when the other end has gone."""
    return pickle.loads(_read(f, int.from_bytes(_read(f, 8), "big")))


def serve(inp, out, kit_root: str) -> None:
    """The loop the studio's Measurer talks to: one (op, request) at a time, answered ("ok", result),
    ("refused", why: the singer's to act on) or ("error", what went wrong)."""
    sweep()
    tools = Tools(Kit(kit_root))
    while True:
        try:
            op, request = receive(inp)
        except (EOFError, OSError, KeyboardInterrupt):
            return
        try:
            answer = ("ok", OPS[op](tools, request))
        except Refused as e:
            answer = ("refused", str(e))
        except Exception as e:  # noqa: BLE001  (said to the studio, which says it on the page)
            traceback.print_exc()
            answer = ("error", f"{type(e).__name__}: {e}")
        request = None  # the audio, if anything still held it, goes now
        send(out, answer)


def main(argv: list[str] | None = None) -> int:
    """python -m webstudio.worker KIT: the loop on this process's standard input and output. Anything the
    tools print goes to standard error, so the answers' pipe carries answers alone."""
    kit = (argv if argv is not None else sys.argv[1:])[0]
    out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    serve(sys.stdin.buffer, out, kit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
