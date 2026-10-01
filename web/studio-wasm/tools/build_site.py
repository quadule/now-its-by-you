"""The studio as a static site, running entirely on the visitor's device (docs/WEB-STUDIO.md, "On the device"): the
studio's page, the piano page, and the bundle its workers run (Pyodide, the kernels, this very program), with no
studio server behind them. Every question the page asks is answered in the visitor's browser
(web/studio-wasm/device.js and py/studio_device.py); the only requests that reach a server are the hosting Worker's
POST /api/versions and GET /api/versions/<id> (a version someone chose to share).

usage: uv run python web/studio-wasm/tools/build_site.py OUT [--machine none] [--sing-kit DIR]

It writes, into OUT (emptied first, if it holds an earlier build):

    index.html, *.js, *.css     the studio's page, served from the root; device.js first among its scripts
    notice.css                  the plain pages' look ("This version isn't here")
    piano/                      the piano page the studio opens in a tab (index.html, piano.js, sound.js, *.css)
    render/bundle.json          which folders are current, and the studio's settings (its song, its machine, the Python
                                and pinned dependencies a recording names)
    render/py-<hash>/           Pyodide and numpy, scipy, soundfile (build_render.py's)
    render/app-<hash>/          the worker, the kernels, the program, the device's side of the studio
    render/kit-<hash>/kit.zip   the singing kit, with --sing-kit and only when py/sing_measure.py is here
    site.json                   for the host: every file's type, cache policy and security policy, the rewrite of
                                /v/<id> to the page, and the paths that are the Worker's own
    _headers                    the same headers in Cloudflare's _headers form (site.json is the authority)

Folders named by a hash are cached for good (immutable); the page, bundle.json and the page's own scripts are
asked again every visit (no-cache). No file is over 25 MiB (Cloudflare's limit per file); the build refuses one that
is. Text isn't stored compressed: the host compresses."""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # web/studio-wasm
ROOT = HERE.parent.parent
MOST = 25 * 2**20  # Cloudflare's largest file
IMMUTABLE = "public, max-age=31536000, immutable"
FRESH = "no-cache"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json",
         ".wasm": "application/wasm", ".zip": "application/zip", ".whl": "application/zip"}
# the page's policy: the studio's own (songbird/studio.py, Handler.send), a song made here playing from a blob: URL,
# and its workers from here; Pyodide runs only in the workers, whose scripts carry WORKER_POLICY (a dedicated worker
# keeps its own script's policy), so the page itself never compiles WebAssembly
PAGE_POLICY = ("default-src 'self'; media-src 'self' blob:; img-src 'self' data:; style-src 'self'; script-src 'self'; "
               "worker-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
WORKER_POLICY = ("default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; "
                 "frame-ancestors 'none'")
HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
SINGING = {"sing.js": ROOT / "webstudio" / "sing.js", "sing.css": ROOT / "webstudio" / "sing.css",
           "karaoke.js": ROOT / "tools" / "karaoke.js", "recorder.js": ROOT / "tools" / "karaoke-recorder.js"}


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def page(singing: bool) -> str:
    """The studio's page as the static site serves it: on the device (its token names no server, only the version
    the page is on, which device.js sets), the shim first among its scripts."""
    from songbird.studio import PAGE

    html = (PAGE / "index.html").read_text()
    marker = '<meta name="studio-token" content="{{token}}">'
    if marker not in html or '<script src="/renderer.js" defer></script>' not in html:
        raise SystemExit("songbird/studio/index.html has changed shape: build_site.py doesn't know where to add the "
                         "device's shim")
    html = html.replace(marker, '<meta name="studio-render" content="device">\n'
                        '<meta name="studio-token" content="device">', 1)
    html = html.replace('<script src="/renderer.js" defer></script>',
                        '<script src="/device.js" defer></script>\n<script src="/renderer.js" defer></script>', 1)
    if singing:  # as webstudio.singing.Singing.page adds it
        html = (html.replace("</head>", '<link rel="stylesheet" href="/sing.css">\n</head>', 1)
                    .replace("</body>", '<script type="module" src="/sing.js"></script>\n</body>', 1))
    return html


def page_files(singing: bool) -> dict[str, bytes]:
    from songbird.studio import PAGE, PIANO_STATIC, STATIC

    files = {"index.html": page(singing).encode(), "device.js": (HERE / "device.js").read_bytes(),
             "notice.css": (PAGE / "notice.css").read_bytes()}
    for path, (name, _) in STATIC.items():
        files[path.lstrip("/")] = (PAGE / name).read_bytes()
    for path, (name, _) in PIANO_STATIC.items():
        if not path.endswith("/"):
            files[path.lstrip("/")] = (PAGE / name).read_bytes()
    if singing:
        for name, source in SINGING.items():
            files[name] = source.read_bytes()
    return files


def kit_zip(folder: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                z.writestr(p.relative_to(folder).as_posix(), p.read_bytes())
    return buffer.getvalue()


def runs_with() -> dict:
    """What a recording made on the device names as its Python and dependencies: this build's (the release's, as the
    server's own recordings name them), never Pyodide's."""
    from songbird.studio import Studio

    return Studio.runs_with(None)


def describe(rel: str) -> dict:
    """A file's type, cache policy and security policy, by where it is."""
    suffix = Path(rel).suffix
    entry = {"type": TYPES.get(suffix, "application/octet-stream")}
    hashed = rel.startswith(("render/py-", "render/app-", "render/kit-"))
    entry["cache"] = IMMUTABLE if hashed else FRESH
    if suffix == ".html":
        entry["csp"] = PAGE_POLICY
    elif rel.startswith("render/") and suffix in (".mjs", ".js"):
        entry["csp"] = WORKER_POLICY
    return entry


def headers_file(files: dict) -> str:
    """Cloudflare's _headers form of site.json's headers, a path at a time."""
    lines = []
    for rel, entry in sorted(files.items()):
        lines.append(rel)
        lines.append(f"  Content-Type: {entry['type']}")
        lines.append(f"  Cache-Control: {entry['cache']}")
        if "csp" in entry:
            lines.append(f"  Content-Security-Policy: {entry['csp']}")
        for k, v in HEADERS.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", help="the folder to write the site into")
    parser.add_argument("--machine", default="none",
                        help="the machine the studio sings as: none (the default, as the VPS did), or fictional:NAME")
    parser.add_argument("--sing-kit", help="the singing kit (webstudio/prepare.py), offered only if "
                                           "web/studio-wasm/py/sing_measure.py is here too")
    args = parser.parse_args(argv)
    if args.machine != "none" and not args.machine.startswith("fictional:"):
        raise SystemExit("--machine: none, or fictional:NAME (a visitor's own computer isn't measured)")
    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()) and not (out / "site.json").exists():
        raise SystemExit(f"{out} holds something other than a site this built; give an empty or new folder")
    sys.path.insert(0, str(ROOT))
    render = _module(HERE / "tools" / "build_render.py", "build_render")
    render.kernels_current()
    py_files, names, version = render.pyodide_files()
    zipped, program = render.program_zip()
    app_files = {name: path.read_bytes() for name, path in render.APP.items()} | {"songbird.zip": zipped}
    singing = bool(args.sing_kit) and (HERE / "py" / "sing_measure.py").is_file()
    kit_files = {"kit.zip": kit_zip(Path(args.sing_kit))} if singing else {}
    folders = {f"py-{render.folder_hash(py_files)}": py_files, f"app-{render.folder_hash(app_files)}": app_files}
    if kit_files:
        folders[f"kit-{render.folder_hash(kit_files)}"] = kit_files
    py_dir, app_dir = list(folders)[:2]

    files: dict[str, bytes] = page_files(singing)
    for folder, contents in folders.items():
        for name, data in contents.items():
            files[f"render/{folder}/{name}"] = data
    raw = sum(len(d) for f, c in folders.items() for d in c.values())
    sent = sum(len(gzip.compress(d, 6, mtime=0)) if Path(n).suffix in (".mjs", ".js", ".json", ".wasm") else len(d)
               for f, c in folders.items() if not f.startswith("kit-") for n, d in c.items())
    studio = {"song": "/app/songs/h-now-its-by-you.json", "machine": args.machine, "runs_with": runs_with()}
    if kit_files:
        studio["kit"] = f"{next(f for f in folders if f.startswith('kit-'))}/kit.zip"
    bundle = {"v": 1, "base": "/render/", "pyodide": py_dir, "app": app_dir, "packages": names, "bytes": raw,
              "transfer": sent, "program": program, "pyodide_version": version, "studio": studio}
    files["render/bundle.json"] = (json.dumps(bundle, indent=2) + "\n").encode()

    big = [f"{rel} ({len(data) / 2**20:.1f} MiB)" for rel, data in files.items() if len(data) > MOST]
    if big:
        raise SystemExit("over Cloudflare's 25 MiB a file: " + ", ".join(big))
    described = {f"/{rel}": describe(rel) for rel in sorted(files)}
    site = {"v": 1, "program": program,
            "about": "docs/WEB-STUDIO.md, 'On the device': serve every file below at its path with its headers",
            "index": {"/": "/index.html", "/piano/": "/piano/index.html"},
            "rewrites": [{"from": "/v/*", "to": "/index.html", "status": 200}],
            "network": {"POST /api/versions": "the Worker's: a version shared (FLAC bytes)",
                        "GET /api/versions/*": "the Worker's: that version's file"},
            "headers": HEADERS, "files": described}

    if out.exists():
        shutil.rmtree(out)
    for rel, data in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (out / "site.json").write_text(json.dumps(site, indent=1) + "\n")
    (out / "_headers").write_text(headers_file(described))
    largest = max(files.items(), key=lambda kv: len(kv[1]))
    print(f"{out}: {len(files)} files, {sum(map(len, files.values())) / 2**20:.1f} MiB "
          f"({sent / 2**20:.1f} MiB on the wire the first time); the largest {largest[0]} "
          f"({len(largest[1]) / 2**20:.1f} MiB); program {program[:12]}, machine {args.machine}"
          f"{', singing' if singing else ''}")


if __name__ == "__main__":
    main()
