"""Python's bytecode, kept in this browser so the next worker needn't compile it again (docs/WEB-STUDIO.md,
"Bytecode kept in the browser").

Pyodide compiles every module it imports from its source: its standard library and its wheels carry no bytecode, and
it writes none. A render worker imports about 860 modules, 680 of them from source (the standard library, numpy,
scipy, the program), and compiling them was more than half of its start (about 7 s of 10.5 in node on a desktop; a
phone's several times that), paid again by every worker: each whole song's, each fourth section's, the studio's own.

So a worker writes what it compiles, as Python's import does with a cache prefix (start(): sys.pycache_prefix), and
once it has made something its kept copy lacked, kept() hands back archives of it for the worker to keep (Cache
Storage, by the bundle's own content-named folders): each module a checked-hash pyc (PEP 552), which Python runs only
for a source whose hash it carries. A changed source is compiled again, never run stale. The standard library is
imported from a zip, where Python writes nothing: the modules this worker imported from it are compiled (a few at a
time, stdlib_step(), so a question asked meanwhile waits for one step at most) into a copy of the zip, which the
next worker is started with in place of the one served.

Only bytecode is kept, and what it runs is the source beside it, unchanged: the program's digest (pack.program_files,
which never reads __pycache__ or a prefix) and every sample are the same either way."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import time
import zipfile

PREFIX = "/pycache"  # sys.pycache_prefix: every module's bytecode under it, at its source's path
STDLIB = f"/lib/python{sys.version_info[0]}{sys.version_info[1]}.zip"  # where Pyodide puts the standard library
GROUPS = {"app": PREFIX + "/app", "site": PREFIX + "/lib"}  # the program (with the bundle), and Pyodide's packages
CHECKED = (0b11).to_bytes(4, "little")  # a pyc's flags: hash-based, its source checked

_known: set[str] = set()  # the pyc files this worker started with, or has handed back
_stdlib: dict[str, bytes] = {}  # standard library modules compiled since (their names in the zip: the pyc's bytes)
_stdlib_given = 0  # how many of them kept() has handed back (each archive holds them all)


def start() -> None:
    """Write and read bytecode under PREFIX (before anything else is imported), knowing what was there to start with
    (the archives kept by an earlier worker, unpacked into / before this)."""
    os.makedirs(PREFIX, exist_ok=True)  # (import makes a missing top folder relative to the working one, and fails)
    sys.pycache_prefix = PREFIX
    sys.dont_write_bytecode = False
    _known.update(_files(PREFIX))


def _files(root: str) -> list[str]:
    out = []
    for folder, _, names in os.walk(root):
        out.extend(os.path.join(folder, n) for n in names if n.endswith(".pyc"))
    return out


def _stdlib_todo() -> list[str]:
    """The standard library's modules this worker imported that the zip it started with has no bytecode for, by
    their names in the zip."""
    with zipfile.ZipFile(STDLIB) as z:
        have = set(z.namelist())
    todo = []
    for module in list(sys.modules.values()):
        f = getattr(module, "__file__", None) or ""
        if f.startswith(STDLIB + "/") and f.endswith(".py"):
            name = f[len(STDLIB) + 1:]
            if name[:-3] + ".pyc" not in have and name not in _stdlib:
                todo.append(name)
    return sorted(set(todo))


def stdlib_step(seconds: float = 0.05) -> int:
    """Compile standard library modules for about this long; how many are left."""
    todo = _stdlib_todo()
    if not todo:
        return 0
    from importlib._bootstrap_external import _code_to_hash_pyc

    end = time.perf_counter() + seconds
    with zipfile.ZipFile(STDLIB) as z:
        while todo and time.perf_counter() < end:
            name = todo.pop()
            source = z.read(name)
            code = compile(source, f"{STDLIB}/{name}", "exec", dont_inherit=True)
            _stdlib[name] = bytes(_code_to_hash_pyc(code, importlib.util.source_hash(source), True))
    return len(todo)


def new() -> bool:
    """Whether this worker has compiled anything since it started (or last handed it back)."""
    return len(_stdlib) > _stdlib_given or any(p not in _known for p in _files(PREFIX))


def _checked(pyc: str) -> None:
    """A pyc Python's import wrote (by its source's time and size, which differ in every worker: Pyodide unpacks its
    files when it starts) made checked-hash: the same code, kept for its source's hash."""
    with open(pyc, "rb") as f:
        data = f.read()
    if int.from_bytes(data[4:8], "little") & 1:
        return
    with open(importlib.util.source_from_cache(pyc), "rb") as f:
        source = f.read()
    with open(pyc, "wb") as f:
        f.write(data[:4] + CHECKED + importlib.util.source_hash(source) + data[16:])


def kept(folder: str) -> dict[str, str]:
    """Archives of everything compiled so far, for the groups that have something new: {"app" | "site" | "stdlib":
    the archive's path in folder}. app and site are zips of their pyc files at their paths from / (unpacked there
    before start()); stdlib is the standard library's zip with bytecode for its modules (Pyodide's in its place)."""
    global _stdlib_given
    os.makedirs(folder, exist_ok=True)
    out = {}
    for group, root in GROUPS.items():
        files = _files(root)
        if all(p in _known for p in files):
            continue
        path = os.path.join(folder, f"{group}.zip")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for pyc in sorted(files):
                try:
                    _checked(pyc)
                except OSError:  # its source gone (a file the worker wrote and removed): not kept
                    continue
                z.write(pyc, pyc.lstrip("/"))
        _known.update(files)
        out[group] = path
    if len(_stdlib) > _stdlib_given:
        path = os.path.join(folder, "stdlib.zip")
        shutil.copyfile(STDLIB, path)
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name, pyc in sorted(_stdlib.items()):
                z.writestr(zipfile.ZipInfo(name[:-3] + ".pyc", (1980, 1, 1, 0, 0, 0)), pyc)
        _stdlib_given = len(_stdlib)
        out["stdlib"] = path
    return out
