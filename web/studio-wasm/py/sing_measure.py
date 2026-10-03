"""A sung take measured on the visitor's device, in Pyodide: the singing never leaves it (docs/WEB-SINGING.md,
"On the device").

    import sing_measure
    result = sing_measure.measure(take, request)       # raises Refused, or anything else for a fault
    answer = sing_measure.answer(take, request)        # never raises: {"ok": result} | {"refused": why} | {"error": what}

take: the take's WAV, as bytes (or a JS ArrayBuffer/Uint8Array: it is copied once into Python and let go).
request: what webstudio/singing.py hands the server's measuring process for a "take", plus where the kit is:

    song      the song's stem (the song a way of singing is made for: /app/songs/<song>.json)
    guide     the digest of the guide it was sung to (the studio made it from the version on the page)
    from_s    where on the guide's clock the take's first sample is (seconds)
    to_s      where it was meant to end
    earlier   the measurements of this visitor's takes before it (each result's "measurement"), at most 11
    kit       where the kit is in Pyodide's file system (default KIT), laid out as webstudio/kit.py lays it out:
              the caller writes there the scores of the guides sung to (guides/<song>.<digest>.score.json) and
              the template singer's analyses it kept (measured/parts/, those parts() names), first

It returns what webstudio/worker.py's "take" op returns, made by the same code: {"measurement" (the take's numbers,
tools/phrasing.py's shape), "phrasing" (a way of singing made from it and the earlier ones), "portrait" (a few
sentences about how they sang), "skipped", "templates" (the template analyses it used: those it made are new files
in the kit's measured/parts, for the caller to keep), "audio_seconds", "seconds", "peak_mb"}; peak_mb here is the
wasm memory held at most (Pyodide's heap, which only grows, and the largest WORLD instance's). A take this can't
measure raises Refused (webstudio.worker's), whose message is the singer's to act on ("Your take sat 21 semitones
above the guide's key..."); anything else raised is a fault. answer() gives the same three outcomes as worker.py's
serve() does. One take at a time.

    sing_measure.op_json("parts", request)       the names of the templates a take will want (worker.parts)
    sing_measure.op_json("melody", request)      a stretch of a guide's melody, written to MELODY (worker.melody)
    sing_measure.op_json("template", request)    the template singer's analyses made ahead (worker.templates)

What runs is tools/phrasing.py and webstudio/worker.py themselves, unchanged, with three stand-ins put in their
modules' places here and nowhere else: pyworld (world_wasm: WORLD's own C++ in wasm), librosa (sing_dtw: its DTW
in numpy, bit for bit) and faster_whisper (worker.py's own, which refuses). MFA is off, as on the server. The take
is decoded in memory; worker.py writes each piece it measures as a WAV in /tmp, which in Pyodide is the worker's
memory (MEMFS), never storage, and removes it as soon as it is read; whatever happens, none is left when this
returns."""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

from webstudio.worker import Refused  # noqa: F401  (the singer's to act on: raised by measure)

KIT = "/kit"

_tools = None


def install() -> None:
    """The stand-ins in their modules' places, and worker.py's memory report pointed at the wasm heaps."""
    os.environ["MFA"] = "off"
    if "pyworld" not in sys.modules:
        import world_wasm

        sys.modules["pyworld"] = world_wasm
    if "librosa" not in sys.modules:
        import sing_dtw

        sys.modules["librosa"] = sing_dtw.librosa_module()
    from webstudio import worker

    if "faster_whisper" not in sys.modules:  # as worker.Tools does, for whatever imports the tools first
        sys.modules["faster_whisper"] = worker._no_whisper()
    worker.peak_mb = heap_mb


def heap_mb() -> int:
    """The wasm memory measuring has held at most, in MB: Pyodide's heap (which only grows, so its size is its
    peak) and the largest memory a WORLD instance held (each is let go after its take)."""
    import world_wasm

    try:
        import pyodide_js

        heap = int(pyodide_js._module.HEAPU8.length)
    except Exception:  # noqa: BLE001  (not in Pyodide)
        heap = 0
    return int((heap + world_wasm.PEAK["bytes"]) / 2**20)


def tools(kit: str | Path = KIT):
    """webstudio.worker.Tools for the kit at kit, made once (it keeps the guides it has read), with the song there
    (the program's own copy, /app/songs)."""
    global _tools
    install()
    from webstudio import worker
    from webstudio.kit import Kit

    root = Path(kit).resolve()
    if _tools is None or _tools.kit.root != root:
        _tools = worker.Tools(Kit(root))
    return _tools


def _song(t, song: str) -> None:
    if not t.kit.genome(song).exists():
        t.kit.keep_song(song, (Path(__file__).resolve().parent / "songs" / f"{song}.json").read_bytes())


def op_json(name: str, request) -> str:
    """One of the measuring process's other ops here (parts, melody, template), its outcome as answer() says it,
    as JSON: a melody's WAV is written to MELODY, not returned."""
    if hasattr(request, "to_py"):
        request = request.to_py()
    request = dict(json.loads(request) if isinstance(request, str) else request)
    kit = request.pop("kit", None) or KIT
    try:
        t = tools(kit)
        _song(t, str(request["song"]))
        from webstudio import worker

        import world_wasm

        t.made = []
        with world_wasm.session():
            out = worker.OPS[name](t, request)
        if "wav" in out:
            Path(MELODY).write_bytes(out.pop("wav"))
            out["file"] = MELODY
        return json.dumps({"ok": out})
    except Refused as e:
        return json.dumps({"refused": str(e)})
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return json.dumps({"error": f"{type(e).__name__}: {e}"})


MELODY = "/tmp/songbird-melody.wav"


def measure(take, request) -> dict:
    """The take measured and the phrasing made with it: webstudio/worker.py's "take", here. See above."""
    if hasattr(request, "to_py"):  # a JS object
        request = request.to_py()
    request = dict(request)
    kit = request.pop("kit", None) or KIT
    if hasattr(take, "to_bytes"):  # a JS ArrayBuffer or typed array
        take = take.to_bytes()
    elif not isinstance(take, bytes):
        take = bytes(take)
    began = time.time()
    t = tools(kit)
    _song(t, str(request["song"]))
    from webstudio import worker

    import world_wasm

    request["audio"] = take
    del take
    try:
        with world_wasm.session():  # one WORLD instance for the take's pieces, let go with its memory after
            result = worker.take(t, request)
    finally:
        request.pop("audio", None)
        worker.sweep(older_than=-1.0)  # any piece left by a fault: gone now, not when the page closes
    result["seconds"] = round(time.time() - began, 2)
    return result


def answer(take, request) -> dict:
    """measure(), its outcome as worker.py's serve() says it: {"ok": result}, {"refused": what the singer can do}
    or {"error": what went wrong} (and its trace on standard error)."""
    try:
        return {"ok": measure(take, request)}
    except Refused as e:
        return {"refused": str(e)}
    except Exception as e:  # noqa: BLE001  (said to the page, which says it)
        traceback.print_exc()
        return {"error": f"{type(e).__name__}: {e}"}


def answer_json(take, request) -> str:
    """answer() as JSON text, for a JS caller that would rather not convert a Python dict."""
    return json.dumps(answer(take, request))
