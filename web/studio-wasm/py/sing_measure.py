"""A sung take measured on the visitor's device, in Pyodide: the singing never leaves it (docs/WEB-SINGING.md,
"On the device").

    import sing_measure
    result = sing_measure.measure(take, request)

take: the take's WAV, as bytes (or a JS ArrayBuffer/Uint8Array: it is copied once into Python and let go).
request: what webstudio/singing.py hands the server's measuring process for a "take", plus where the kit is:

    song      the song's stem (the kit's offer.json "song")
    guide     the digest of the guide it was sung to (one the kit offers)
    from_s    where on the guide's clock the take's first sample is (seconds)
    to_s      where it was meant to end
    earlier   the measurements of this visitor's takes before it (each result's "measurement"), at most 11
    offered   the guides' digests the kit offers (offer.json specs' "guide")
    kit       where the singing kit is in Pyodide's file system (default KIT): offer.json, song/<song>.json,
              guides/, guide/ and measured/templates/ as webstudio/kit.py lays them out (no audio/ or lyrics/
              needed). The caller puts those files there before measuring.

It returns what webstudio/worker.py's "take" op returns, made by the same code: {"measurement" (the take's numbers,
tools/phrasing.py's shape), "phrasing" (a way of singing made from it and the earlier ones), "portrait" (a few
sentences about how they sang), "skipped", "audio_seconds", "seconds", "peak_mb"}; peak_mb here is the wasm
memory held at most (Pyodide's heap and WORLD's largest instance). A take this can't measure raises Refused, whose
message is the singer's to act on ("Your take sat 7 semitones above the guide's key..."); anything else raised is
a fault. One take at a time.

What runs is tools/phrasing.py and webstudio/worker.py themselves, unchanged, with three stand-ins put in their
modules' places here and nowhere else: pyworld (world_wasm: WORLD's own C++ in wasm), librosa (sing_dtw: its DTW
in numpy, bit for bit) and faster_whisper (worker.py's own, which refuses). MFA is off, as on the server. The take
is decoded in memory; worker.py writes each piece it measures as a WAV in /tmp, which in Pyodide is memory
(MEMFS), and removes it as soon as it is read; whatever happens, none is left when this returns."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

KIT = "/kit"

_tools = None


class _Refused(Exception):  # replaced by webstudio.worker.Refused once the tools are loaded (install())
    pass


Refused = _Refused


def install() -> None:
    """The stand-ins in their modules' places, and worker.py's memory report pointed at the wasm heaps."""
    global Refused
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
    Refused = worker.Refused


def heap_mb() -> int:
    """The wasm memory measuring has held at most, in MB: Pyodide's heap (which only grows, so its size is its
    peak) and the largest memory a WORLD instance held (each is let go after its analysis)."""
    import world_wasm

    try:
        import pyodide_js

        heap = int(pyodide_js._module.HEAPU8.length)
    except Exception:  # noqa: BLE001  (not in Pyodide)
        heap = 0
    return int((heap + world_wasm.PEAK["bytes"]) / 2**20)


def tools(kit: str | Path = KIT):
    """webstudio.worker.Tools for the kit at kit, made once (it keeps the guides and templates it has read)."""
    global _tools
    install()
    from webstudio import worker
    from webstudio.kit import Kit

    root = Path(kit).resolve()
    if _tools is None or _tools.kit.root != root:
        _tools = worker.Tools(Kit(root))
    return _tools


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
