"""Python's bytecode, made with the bundle so a worker needn't compile what it imports (docs/PERFORMANCE.md, "The web
studio's start, its edits and its voice").

Pyodide compiles every module it imports from its source: its standard library and its wheels carry no bytecode, and
it writes none. A render worker imports about 860 modules, 680 of them from source (the standard library, numpy,
scipy, the program), and compiling them was 7 s of its 10 s start in node on a desktop (a phone's several times
that), paid again by every worker: each whole song's, each fourth section's, the studio's own.

So the build compiles them (build(), run in Pyodide itself under node by tools/bytecode.mjs, so the bytecode is its
interpreter's own) into archives the worker fetches beside the wheels and unpacks before it imports anything:

    stdlib.zip     Pyodide's standard library zip, with bytecode beside the source of each module the program uses
                   (the worker starts Pyodide with it in place of python_stdlib.zip)
    numpy.zip, scipy.zip, soundfile.zip   the pyc files of the modules of each package the program uses (soundfile's
                   with cffi's and pycparser's), at their paths under PREFIX
    app.zip        every module of the program and the bundle's stand-ins, likewise (in the app folder: it changes with
                   the program)

Each module's bytecode is a checked-hash pyc (PEP 552): Python runs it only for a source whose hash it carries, so a
source that differs is compiled as before, never run stale. Compiled without column tables (PYTHONNODEBUGRANGES: a
fifth smaller; a traceback still names the line). What a worker imports that the build didn't is compiled as it
always was. What runs is the source beside it, unchanged: the program's digest (pack.program_files, which never reads
a cache prefix) and every sample are the same either way.

    start()          in the worker, before anything it fetched is imported: read bytecode from under PREFIX
    build(out)       at build time, in Pyodide with numpy, scipy and soundfile loaded and the program at /app"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import io
import os
import pkgutil
import sys
import zipfile

PREFIX = "/pycache"  # sys.pycache_prefix: each module's bytecode under it, at its source's path
STDLIB = f"/lib/python{sys.version_info[0]}{sys.version_info[1]}.zip"  # where Pyodide puts the standard library
SITE = f"/lib/python{sys.version_info[0]}.{sys.version_info[1]}/site-packages"
APP = "/app"
PACKAGES = {"numpy": "numpy", "scipy": "scipy"}  # a site-packages module's top name -> its archive (else soundfile's)
DATE = (1980, 1, 1, 0, 0, 0)
JS = ("wasm_kernels", "songbird_wasm", "songbird_kernels", "js", "pyodide_js")  # what a worker's loader gives from JS


def start() -> None:
    """Read bytecode from under PREFIX (the archives fetched with the bundle, unpacked into / before this)."""
    sys.pycache_prefix = PREFIX


def pyc(source: bytes, path: str) -> bytes:
    """A module's checked-hash pyc, compiled as import compiles it."""
    from importlib._bootstrap_external import _code_to_hash_pyc

    code = compile(source, path, "exec", dont_inherit=True)
    return bytes(_code_to_hash_pyc(code, importlib.util.source_hash(source), True))


def cached(path: str) -> str:
    """Where a source's bytecode lies under PREFIX, as a name in an archive unpacked into /."""
    tag = sys.implementation.cache_tag
    folder, name = os.path.split(path)
    return f"{PREFIX}{folder}/{name[:-3]}.{tag}.pyc".lstrip("/")


def _entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def imported_by(source: bytes) -> set[str]:
    """Every module a source names in an import, at any depth (a function's own imports too), and each name taken
    from one (it may be a submodule)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def _sources(root: str) -> dict[str, bytes]:
    out = {}
    for folder, _, files in os.walk(root):
        for f in sorted(files):
            if f.endswith(".py"):
                path = os.path.join(folder, f)
                with open(path, "rb") as fh:
                    out[path] = fh.read()
    return out


def _import_everything(sources: dict[str, bytes]) -> None:
    """What the program can import, imported: each of its modules, and each module any of them names (one that fails
    is only one this build makes no bytecode for)."""
    import warnings

    if APP not in sys.path:
        sys.path.insert(0, APP)
    names = {info.name for info in pkgutil.walk_packages([APP])}
    for source in sources.values():
        names |= imported_by(source)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name in sorted(names):
            if name.split(".")[0] in JS or "test" in name.split("."):
                continue
            try:
                importlib.import_module(name)
            except BaseException:  # noqa: BLE001 (anything at all: SystemExit from a tool's module included)
                pass


def _zipped(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name in sorted(files):
            z.writestr(_entry(name), files[name], compresslevel=9)
    return buffer.getvalue()


def build(out: str) -> dict[str, int]:
    """The archives (the module's docstring) into the folder out: {archive: how many modules it has bytecode for}."""
    os.makedirs(out, exist_ok=True)
    sources = _sources(APP)
    _import_everything(sources)
    site: dict[str, dict[str, bytes]] = {}
    stdlib: set[str] = set()
    for module in list(sys.modules.values()):
        f = getattr(module, "__file__", None) or ""
        if not f.endswith(".py"):
            continue
        if f.startswith(STDLIB + "/"):
            stdlib.add(f[len(STDLIB) + 1:])
        elif f.startswith(SITE + "/"):
            top = f[len(SITE) + 1:].split("/")[0].removesuffix(".py")
            with open(f, "rb") as fh:
                site.setdefault(PACKAGES.get(top, "soundfile"), {})[cached(f)] = pyc(fh.read(), f)
    made = {}
    files = {}
    with zipfile.ZipFile(STDLIB) as served:
        for info in served.infolist():
            data = served.read(info)
            files[info.filename] = data
            if info.filename in stdlib:
                files[info.filename[:-3] + ".pyc"] = pyc(data, f"{STDLIB}/{info.filename}")
    archives = {"stdlib": files, **site, "app": {cached(path): pyc(source, path) for path, source in sources.items()}}
    for name, contents in sorted(archives.items()):
        with open(os.path.join(out, f"{name}.zip"), "wb") as fh:
            fh.write(_zipped(contents))
        made[f"{name}.zip"] = len(stdlib) if name == "stdlib" else len(contents)
    return made
