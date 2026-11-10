"""The bundle a public studio serves so a visitor's browser can make the song itself (songbird studio --public
--browser-render DIR; docs/WEB-STUDIO.md, "Made in the visitor's browser").

usage: uv run python web/studio-wasm/tools/build_render.py OUT_DIR

It writes, into OUT_DIR (emptied of any earlier build first):

    bundle.json     which folders are current, the program they carry (its digest), what a first visit fetches
    py-<hash>/      Pyodide (its core, the standard library) and the packages the program needs from it: numpy,
                    scipy, soundfile (and theirs), checked against Pyodide's own lock file
    app-<hash>/     the worker (studio-worker.mjs), the kernels in JS (kernels/) and C/wasm (wasm/), and the
                    program: songbird.zip, holding exactly the files a packet carries as program/ (so a recording
                    made in the browser names the same program as the server's), cmudict, the browser's stand-ins
                    (py/: numba, the wasm kernels' adapters, the patches) and studio_render.py; and the program's
                    bytecode (bytecode.zip, py/bytecode.py)
    bc-<hash>/      the bytecode of the standard library and the packages, as the program imports them: made in
                    Pyodide under node (tools/bytecode.mjs), so a worker needn't compile them as it starts

Each folder is named by a hash of its contents, so the studio serves every file for good (immutable) and a new
program fetches only its own few megabytes. Text and wasm files get a .gz beside them, which the studio sends to a
browser that takes it. Needs Node (for Pyodide's npm package: `npm ci` in web/studio-wasm, run here if missing;
numpy and scipy come from Pyodide's CDN the first time and are cached beside it) at build time only; zig isn't
needed (the C kernels are built and committed: wasm/kernels.wasm and kernels-simd.wasm). Refuses to build from kernels that are stale
(tools/transpile.py --check)."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # web/studio-wasm
ROOT = HERE.parent.parent
PYODIDE = HERE / "node_modules" / "pyodide"
CORE = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip")
PACKAGES = ("numpy", "scipy", "soundfile")  # what the program imports from Pyodide (and their dependencies)
APP = {"studio-worker.mjs": HERE / "studio-worker.mjs",
       "kernels/kernels.gen.mjs": HERE / "kernels" / "kernels.gen.mjs",
       "kernels/rt.mjs": HERE / "kernels" / "rt.mjs",
       "kernels/hand.mjs": HERE / "kernels" / "hand.mjs",
       "kernels/manifest.json": HERE / "kernels" / "manifest.json",
       "wasm/kernels.mjs": HERE / "wasm" / "kernels.mjs",
       "wasm/kernels.wasm": HERE / "wasm" / "kernels.wasm",
       "wasm/kernels-simd.wasm": HERE / "wasm" / "kernels-simd.wasm"}
STANDINS = ("numba/__init__.py", "wasm_kernels.py", "web_patches.py", "studio_render.py",  # py/ (not soundfile.py)
            "studio_device.py",  # the studio itself on the visitor's device (build_site.py)
            "lazy_imports.py",  # ... whose worker stands in for scipy and soundfile until they're used
            "bytecode.py")  # every worker: what Python compiles, kept in the browser for the next one
OPTIONAL = ("sing_measure.py",)  # py/, when it's there: a sung take measured in the browser (another part of the work)
# beside the program, for the studio on the device: the song it opens on, and singing's side of the studio (outside
# the program, as on a server: a packet never carries it)
BESIDE = ("songs/h-now-its-by-you.json", "webstudio/__init__.py", "webstudio/kit.py", "webstudio/singing.py",
          "webstudio/guide.py", "webstudio/released.json", "webstudio/released-record.json", "tools/karaoke_words.py")
SQUEEZE = (".mjs", ".js", ".json", ".wasm")  # worth sending compressed; zips and wheels are already
DATE = (1980, 1, 1, 0, 0, 0)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def kernels_current() -> None:
    problems = _module(HERE / "tools" / "transpile.py", "transpile").stale()
    if problems:
        raise SystemExit("the browser's kernels are stale:\n  " + "\n  ".join(problems))


def packages(lock: dict) -> list[str]:
    """The packages to ship: PACKAGES and everything they depend on, by Pyodide's lock file."""
    out, todo = [], list(PACKAGES)
    while todo:
        name = todo.pop(0)
        if name in out:
            continue
        out.append(name)
        todo += lock["packages"][name].get("depends", [])
    return sorted(out)


def pyodide_files() -> tuple[dict[str, bytes], list[str], str]:
    if not (PYODIDE / "pyodide.mjs").exists():
        subprocess.run(["npm", "ci"], cwd=HERE, check=True)
    lock = json.loads((PYODIDE / "pyodide-lock.json").read_text())
    names = packages(lock)
    wanted = {lock["packages"][n]["file_name"] for n in names}
    if not all((PYODIDE / f).exists() for f in wanted):  # fetched from Pyodide's CDN once, cached beside it
        script = ("import { loadPyodide } from 'pyodide'; const py = await loadPyodide(); "
                  f"await py.loadPackage({json.dumps(list(PACKAGES))}, {{ messageCallback: () => {{}} }});")
        subprocess.run(["node", "--input-type=module", "-e", script], cwd=HERE, check=True)
    files = {name: (PYODIDE / name).read_bytes() for name in CORE}
    for n in names:
        entry = lock["packages"][n]
        data = (PYODIDE / entry["file_name"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['file_name']} isn't the file Pyodide's lock names (its sha256 differs)")
        files[entry["file_name"]] = data
    # the lock, with only what is shipped: nothing can send Pyodide looking elsewhere for a package
    trimmed = {**lock, "packages": {n: lock["packages"][n] for n in names}}
    files["pyodide-lock.json"] = (json.dumps(trimmed, indent=1, sort_keys=True) + "\n").encode()
    version = json.loads((PYODIDE / "package.json").read_text())["version"]
    return files, names, version


def _entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def program_zip() -> tuple[bytes, str]:
    """The program as the worker unpacks it into /app: the packet's program/ at the top (so pack.program_files
    finds the same files there and names the same digest), and what the browser adds beside it."""
    sys.path.insert(0, str(ROOT))
    from songbird import pack

    program = pack.program_files(ROOT)
    import cmudict

    site = Path(cmudict.__file__).resolve().parent.parent
    extra = {}
    for d in ("cmudict", *[q.name for q in site.glob("cmudict-*.dist-info")]):
        for p in sorted((site / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                extra[p.relative_to(site).as_posix()] = p.read_bytes()
    for name in STANDINS:
        extra[name] = (HERE / "py" / name).read_bytes()
    for name in OPTIONAL:
        if (HERE / "py" / name).is_file():
            extra[name] = (HERE / "py" / name).read_bytes()
    for name in BESIDE:
        extra[name] = (ROOT / name).read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted({k[len("program/"):]: v for k, v in program.items()}.items()):
            z.writestr(_entry(name), data)
        for name, data in sorted(extra.items()):
            z.writestr(_entry(name), data)
    return buffer.getvalue(), pack.program_sha256(program)


def bytecode_files(program: bytes) -> tuple[dict[str, bytes], bytes]:
    """The bundle's bytecode (py/bytecode.py), made in Pyodide under node (tools/bytecode.mjs) from this program zip:
    the bc folder's files (the standard library's zip, numpy's, scipy's and soundfile's pycs) and the program's own
    (app.zip, the app folder's bytecode.zip). The same bytes for the same program and Pyodide."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        zipped, out = Path(tmp) / "program.zip", Path(tmp) / "out"
        zipped.write_bytes(program)
        run = subprocess.run(["node", str(HERE / "tools" / "bytecode.mjs"), str(zipped), str(out)], cwd=HERE,
                             capture_output=True, text=True)
        if run.returncode != 0:
            raise SystemExit(f"tools/bytecode.mjs failed: {run.stderr[-2000:]}")
        files = {p.name: p.read_bytes() for p in sorted(out.glob("*.zip"))}
    return {n: d for n, d in files.items() if n != "app.zip"}, files["app.zip"]


def folder_hash(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode() + b"\0" + hashlib.sha256(files[name]).digest())
    return h.hexdigest()[:16]


def write(out: Path, folder: str, files: dict[str, bytes]) -> tuple[int, int]:
    """The folder's files, and a .gz beside each worth compressing; (bytes, bytes sent compressed)."""
    raw = sent = 0
    for name, data in files.items():
        path = out / folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        raw += len(data)
        size = len(data)
        if path.suffix in SQUEEZE and len(data) > 1024:
            packed = gzip.compress(data, compresslevel=9, mtime=0)
            if len(packed) < 0.9 * len(data):
                path.with_name(path.name + ".gz").write_bytes(packed)
                size = len(packed)
        sent += size
    return raw, sent


# ---------------------------------------------------------------------------------------------------------------
# Measuring a sung take on the device (docs/WEB-SINGING.md, "On the device"): self-contained, tools/sing_bundle.py
# says what it adds. In the app folder: singing.zip (the measuring code and py/sing_measure.py, unpacked into /app
# beside the program, as songbird.zip is) and world/ (WORLD in wasm, its loader and its licence). The worker
# registers world/world.mjs's loadWorld(bytes) as the JS module `songbird_world` before importing sing_measure.


def singing_files() -> dict[str, bytes]:
    bundle = _module(HERE / "tools" / "sing_bundle.py", "sing_bundle")
    stale = _module(HERE / "tools" / "world_sources.py", "world_sources").stale()
    if stale:
        raise SystemExit("WORLD in wasm is stale:\n  " + "\n  ".join(stale))
    return {"singing.zip": bundle.singing_zip(), **{name: path.read_bytes() for name, path in bundle.APP.items()}}


# ---------------------------------------------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__.split("\n\n")[1])
    out = Path(sys.argv[1]).resolve()
    kernels_current()
    py_files, names, version = pyodide_files()
    zipped, program = program_zip()
    app_files = {name: path.read_bytes() for name, path in APP.items()} | {"songbird.zip": zipped}
    app_files |= singing_files()  # measuring a sung take (the block above)
    bc_files, app_files["bytecode.zip"] = bytecode_files(zipped)
    py_dir, app_dir, bc_dir = (f"py-{folder_hash(py_files)}", f"app-{folder_hash(app_files)}",
                               f"bc-{folder_hash(bc_files)}")
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():  # an earlier build's folders go: a studio serves one bundle
        if old.is_dir() and old.name.split("-")[0] in ("py", "app", "bc"):
            shutil.rmtree(old)
    py_raw, py_sent = write(out, py_dir, py_files)
    app_raw, app_sent = write(out, app_dir, app_files)
    bc_raw, bc_sent = write(out, bc_dir, bc_files)
    manifest = {"v": 1, "pyodide": py_dir, "app": app_dir, "bytecode": bc_dir, "program_sha256": program,
                "pyodide_version": version, "packages": names, "bytes": py_raw + app_raw + bc_raw,
                "transfer": py_sent + app_sent + bc_sent, "program_bytes": len(zipped)}
    (out / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{out}: {py_dir} ({py_raw / 2**20:.1f} MiB, {py_sent / 2**20:.1f} sent), "
          f"{app_dir} ({app_raw / 2**20:.1f} MiB, {app_sent / 2**20:.1f} sent), {bc_dir} ({bc_raw / 2**20:.1f} MiB); "
          f"program {program[:12]}")


if __name__ == "__main__":
    main()
