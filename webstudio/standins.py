"""What measuring a sung take needs, on a computer that may not have it (docs/WEB-SINGING.md, "Measuring without
pyworld or librosa").

tools/phrasing.py measures with pyworld (WORLD's harvest and cheaptrick) and librosa (one DTW). Neither comes
ready-made for every computer (pyworld has no wheels for macOS or Linux), so where they aren't installed their
places are taken, in sys.modules, by:

    pyworld   world_wasmtime: the same world.wasm the browser runs (web/studio-wasm/world/), under wasmtime
    librosa   web/studio-wasm/py/sing_dtw.py: librosa.sequence.dtw as tools/phrasing.py calls it, in numpy

wasmtime is fetched the first time a studio is asked to (fetch()), from PyPI, into the program's own folder
(~/.songbird/singing/, or $SONGBIRD_HOME's), never into the system or the program's environment. The browser has
its own stand-ins (web/studio-wasm/py/sing_measure.py) and never comes here."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .kit import ROOT

WASMTIME = "50.0.1"  # the wasmtime fetched: ready-made for Windows, macOS and Linux (x86-64 and arm64)
WASMTIME_MB = 10  # about what it is to download
DTW = ROOT / "web" / "studio-wasm" / "py" / "sing_dtw.py"


def home() -> Path:
    return Path(os.environ.get("SONGBIRD_HOME") or Path.home() / ".songbird")


def folder() -> Path:
    """Where the fetched wasmtime is kept: by its version and this computer's kind (its wheels are any Python's)."""
    return home() / "singing" / f"wasmtime-{WASMTIME}-{sys.platform}-{platform.machine().lower()}"


def _on_path() -> None:
    f = folder()
    if (f / ".ready").exists() and str(f) not in sys.path:
        sys.path.append(str(f))


def has(name: str) -> bool:
    if name in sys.modules:
        return True
    _on_path()
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def missing() -> str | None:
    """What measuring lacks here that can be fetched ("wasmtime"), or None if nothing is."""
    return None if has("pyworld") or has("wasmtime") else "wasmtime"


def install() -> list[str]:
    """The stand-ins put in place of what isn't installed, before tools/phrasing.py is imported; the names of the
    modules stood in for. pyworld and librosa are used wherever they are installed."""
    put = []
    if not has("pyworld"):
        if not has("wasmtime"):
            raise ImportError("measuring needs pyworld, or wasmtime to run WORLD in wasm")
        from . import world_wasmtime

        sys.modules["pyworld"] = world_wasmtime
        put.append("pyworld")
    if not has("librosa"):
        spec = importlib.util.spec_from_file_location("sing_dtw", DTW)
        dtw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dtw)
        sys.modules["librosa"] = dtw.librosa_module()
        put.append("librosa")
    return put


def path_entry() -> str | None:
    """The folder a measuring process needs on its path for the fetched wasmtime, if it was fetched."""
    f = folder()
    return str(f) if (f / ".ready").exists() else None


def fetch(run=subprocess.run) -> str | None:
    """wasmtime fetched from PyPI into folder() (ready-made builds only: nothing is compiled), with uv if it is here,
    else this Python's pip. None if it is ready; else why not, said to the person."""
    f = folder()
    if (f / ".ready").exists():
        return None
    f.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if uv:
        command = [uv, "pip", "install", "--quiet", "--python", sys.executable, "--target", str(f)]
    elif importlib.util.find_spec("pip") is not None:
        command = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--target", str(f)]
    else:
        return "there's no installer here (neither uv nor pip) to fetch wasmtime with"
    try:
        done = run([*command, "--only-binary", ":all:", f"wasmtime=={WASMTIME}"], capture_output=True, text=True,
                   timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        shutil.rmtree(f, ignore_errors=True)
        return f"fetching wasmtime stopped ({e})"
    if done.returncode != 0:
        shutil.rmtree(f, ignore_errors=True)
        return "wasmtime couldn't be fetched for this computer (offline, or no ready-made build for it)"
    (f / ".ready").write_text(f"wasmtime=={WASMTIME}\n", encoding="utf-8")
    _on_path()
    return None
