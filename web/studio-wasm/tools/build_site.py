"""The studio as a static site, running entirely on the visitor's device (docs/WEB-STUDIO.md, "On the device"): the
studio's page, the piano page, and the bundle its workers run (Pyodide, the kernels, this very program), with no
studio server behind them. Every question the page asks is answered in the visitor's browser
(web/studio-wasm/device.js and py/studio_device.py); the only requests that reach a server are the hosting Worker's
POST /api/versions and GET /api/versions/<id> (a version someone chose to share).

usage: uv run python web/studio-wasm/tools/build_site.py OUT [--machine none] [--sing-kit DIR] [--days 400]

It writes, into OUT (emptied first, if it holds an earlier build):

    index.html, *.js, *.css     the studio's page, served from the root; device.js first among its scripts
    notice.css                  the plain pages' look ("This version isn't here")
    piano/                      the piano page the studio opens in a tab (index.html, piano.js, sound.js, *.css)
    render/bundle.json          which folders are current, and the studio's settings (its song, its machine, the Python
                                and pinned dependencies a recording names)
    render/py-<hash>/           Pyodide and numpy, scipy, soundfile (build_render.py's)
    render/app-<hash>/          the worker, the kernels, the program, the device's side of the studio; with a singing
                                kit, the measuring too (singing.zip, world/: build_render.py's singing_files)
    render/first-<hash>/        the page's first questions answered ahead, a file a day (<day>.gzip: gzip'd JSON, which
                                device.js unpacks), from two days before the build to --days after: the song as it
                                began, as the studio's worker answers it that day (studio_device.first_answers, run
                                here natively), so the page shows its song before Python is fetched
    render/kit-<hash>/          the singing kit (--sing-kit, webstudio/prepare.py's), its files as the kit lays them
                                out, each fetched only when it's needed: offer.json at start; a version's words and
                                melody guide when it's chosen; the song, the guide's score and its three templates when
                                a take sung to it is measured (sing_measure.kit_files). The largest is a guide, 6 MB
    site.json                   for the host: every file's type, cache policy and security policy, the rewrite of
                                /v/<id> to the page, and the paths that are the Worker's own (the hosting Worker's
                                web/studio-site/tools/prepare.mjs checks it, and writes _headers from its own rules)

Folders named by a hash are cached for good (immutable); the page, bundle.json and the page's own scripts are
asked again every visit (no-cache). No file is over 25 MiB (Cloudflare's limit per file); the build refuses one that
is. Text isn't stored compressed: the host compresses. Every address in it is from the root (/studio.js,
/render/..., /piano/piano.js): the page is also served at /v/<id>, where a relative one would point elsewhere, and its
policy allows no <base>."""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # web/studio-wasm
ROOT = HERE.parent.parent
MOST = 25 * 2**20  # Cloudflare's largest file
IMMUTABLE = "public, max-age=31536000, immutable"
FRESH = "no-cache"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json",
         ".wasm": "application/wasm", ".zip": "application/zip", ".whl": "application/zip", ".flac": "audio/flac",
         ".npz": "application/octet-stream", ".gzip": "application/octet-stream"}
SONG = ROOT / "songs" / "h-now-its-by-you.json"  # the song the studio opens on (build_render.py's BESIDE)
DAYS = 400  # the first answers ahead (render/first-<hash>/): a file a day, about 50 KB each
BEFORE = 2  # ... from this many days before the build's date (a visitor west of here is still on yesterday)
# The policy every page and script is served with: the hosting Worker's (web/studio-site/src/policy.js, PAGE_POLICY,
# which tests/test_studio_device.py holds this to): the studio's own (songbird/studio.py, Handler.send), and what the
# browser's renderer needs: Pyodide compiling WebAssembly ('wasm-unsafe-eval', never 'unsafe-eval'), a song made here
# playing from a blob: URL, its workers from here
POLICY = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; "
          "media-src 'self' blob:; connect-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; "
          "frame-ancestors 'none'")
HEADERS = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
# The Worker's own two paths, never rewritten to the page, and what the page expects of them. A shared version is
# bytes from anyone served on the studio's own origin: it must never be something a browser would run or render
# (a page, a script), so it is checked for FLAC's magic on the way in and sent as an attachment that runs nothing.
NETWORK = {
    "POST /api/versions": {"body": "a version's FLAC, as it is", "most_bytes": 64 * 2**20, "starts_with": "fLaC",
                           "answers": '201 {"id": "<32 hex>", "url": "/v/<id>"}, or 4xx {"error": "<a sentence>"}'},
    "GET /api/versions/*": {"answers": "that file, or 404 {\"error\"}",
                            "headers": {"Content-Type": "audio/flac", "X-Content-Type-Options": "nosniff",
                                        "Content-Disposition": 'attachment; filename="version.flac"',
                                        "Content-Security-Policy": "default-src 'none'; sandbox",
                                        "Cache-Control": "private, max-age=3600"}},
}
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
    # what's kept, true from the first paint (studio.js says the same once it starts)
    html = html.replace("Nothing on this page leaves this computer.", "Nothing leaves this device unless you share a version.", 1)
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
    files["piano/index.html"] = rooted((PAGE / "piano" / "index.html").read_text(), "/piano/").encode()
    if singing:
        for name, source in SINGING.items():
            files[name] = source.read_bytes()
    return files


def rooted(html: str, folder: str) -> str:
    """A page's addresses from the root: the piano page's own (identity.css, piano.js) under `folder`, its way back to
    the studio ("../") the root. (The page itself is the same file web/piano/ serves, from wherever it's put.)"""
    def one(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        if url.startswith(("/", "#", "http:", "https:", "data:", "mailto:")):
            return m.group(0)
        return f'{attr}="{"/" if url == "../" else folder + url}"'

    return re.sub(r'\b(src|href)="([^"]*)"', one, html)


def kit_files(folder: Path) -> dict[str, bytes]:
    """The singing kit's files the device fetches, by their path in the kit (webstudio/kit.py's layout), from its
    offer: offer.json and the song; for each version offered, its words, its melody guide, its score and the template
    singer's analysis in each key the kit made one for. Refused, saying why, if the kit isn't one for this song and
    this measuring code (its templates are named by tools/phrasing.py version(), which the device's copy shares)."""
    sys.path.insert(0, str(ROOT))
    from webstudio.kit import Kit

    kit = Kit(folder)
    why = kit.fits(SONG)
    if why:
        raise SystemExit(f"--sing-kit {folder}: {why}")
    offer = kit.offer()
    extractor = ("import sys; from webstudio.kit import Kit; from webstudio.worker import Tools; "
                 "print(Tools(Kit(sys.argv[1])).extractor)")  # the measuring code's version, in a process of its own
    ran = subprocess.run([sys.executable, "-c", extractor, str(kit.root)], cwd=ROOT, capture_output=True, text=True,
                         check=False)
    made = (ran.stdout.strip().splitlines() or [""])[-1]
    if ran.returncode or not made:
        raise SystemExit(f"--sing-kit {folder}: the measuring code couldn't be loaded to check the kit (it needs the "
                         f"web-singing dependencies: uv sync --group web-singing):\n{ran.stderr[-800:]}")
    if offer["extractor"] != made:
        raise SystemExit(f"--sing-kit {folder}: made by another version of the measuring code ({offer['extractor']}, "
                         f"not {made}): make it again (uv run python -m webstudio.prepare --kit {folder})")
    song, extractor = offer["song"], offer["extractor"]
    names = ["offer.json", f"song/{song}.json"]
    for spec in offer["specs"]:
        names += [f"lyrics/{spec['id']}.json", f"audio/{spec['id']}.melody.flac",
                  f"guides/{song}.{spec['guide']}.score.json",
                  *[f"measured/templates/{spec['guide']}.{int(k):+d}.{extractor}.npz" for k in spec["templates"]]]
    missing = [n for n in names if not (kit.root / n).is_file()]
    if missing:
        raise SystemExit(f"--sing-kit {folder} is missing {', '.join(missing)}: make it again")
    return {name: (kit.root / name).read_bytes() for name in dict.fromkeys(names)}


def runs_with() -> dict:
    """What a recording made on the device names as its Python and dependencies: this build's (the release's, as the
    server's own recordings name them), never Pyodide's."""
    from songbird.studio import Studio

    return Studio.runs_with(None)


def first_answers(config: dict, days: list[str], jobs: int | None = None) -> dict[str, bytes]:
    """Each day's first answers, as the page fetches them: <day>.gzip, the JSON studio_device.first_days writes,
    gzip'd here (the host doesn't compress it again, and device.js unpacks it with the browser's DecompressionStream).
    Worked out natively by the studio's own code, in a few processes at once (numpy and scipy's own, not the
    stand-ins the browser's py/ folder holds: it is put last on their path)."""
    n = max(1, min(jobs or os.cpu_count() or 1, 8, len(days)))
    script = ("import json, sys; sys.path.append(sys.argv[1]); import studio_device; "
              "studio_device.first_days(json.loads(sys.argv[2]), sys.argv[4:], sys.argv[3])")
    with tempfile.TemporaryDirectory(prefix="songbird-first-") as tmp:
        runs = [subprocess.Popen([sys.executable, "-c", script, str(HERE / "py"), json.dumps(config), tmp, *days[i::n]],
                                 cwd=ROOT, stderr=subprocess.PIPE, text=True) for i in range(n)]
        failed = [r.stderr.read()[-1500:] for r in runs if r.wait()]
        if failed:
            raise SystemExit("the first answers couldn't be worked out:\n" + failed[0])
        return {f"{day}.gzip": gzip.compress((Path(tmp) / f"{day}.json").read_bytes(), 9, mtime=0) for day in days}


def window(today: date, days: int = DAYS) -> list[str]:
    """The days the first answers are made for: from BEFORE days before `today`, `days` of them after."""
    return [(today + timedelta(days=k)).isoformat() for k in range(-BEFORE, days)] if days > 0 else []


def fetched(py_files: dict[str, bytes], app_files: dict[str, bytes], lock: dict, packages: list[str]) -> int:
    """What a worker fetches (its bytes as they arrive, unpacked: what it counts), by the packages it loads: Python,
    its library, the lock, those packages' wheels and the program; a render worker also its kernels' manifest and
    wasm (scripts it imports aren't counted)."""
    wheels = set()
    todo = list(packages)
    while todo:
        name = todo.pop()
        if name not in wheels:
            wheels.add(name)
            todo += lock["packages"][name].get("depends", [])
    names = ["pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json",
             *[lock["packages"][w]["file_name"] for w in wheels]]
    app = ["songbird.zip"] + (["kernels/manifest.json", "wasm/kernels.wasm"] if "scipy" in packages else [])
    return sum(len(py_files[n]) for n in names) + sum(len(app_files[n]) for n in app)


def describe(rel: str) -> dict:
    """A file's type, cache policy and security policy, by where it is."""
    suffix = Path(rel).suffix
    entry = {"type": TYPES.get(suffix, "application/octet-stream")}
    hashed = rel.startswith(("render/py-", "render/app-", "render/kit-", "render/first-"))
    entry["cache"] = IMMUTABLE if hashed else FRESH
    if suffix in (".html", ".mjs", ".js"):  # a page, or a script (a worker keeps its own script's policy)
        entry["csp"] = POLICY
    return entry


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("out", help="the folder to write the site into")
    parser.add_argument("--machine", default="none",
                        help="the machine the studio sings as: none (the default, as the VPS did), or fictional:NAME")
    parser.add_argument("--sing-kit", help="the singing kit (uv run python -m webstudio.prepare: renders/sing-kit): "
                                           "singing is offered, measured on the device")
    parser.add_argument("--days", type=int, default=DAYS,
                        help=f"the days ahead the page's first answers are made for (default {DAYS}; 0: none, the page "
                             "waits for Python as before)")
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
    singing = bool(args.sing_kit)
    kit = kit_files(Path(args.sing_kit)) if singing else {}
    if singing:
        app_files |= render.singing_files()  # measuring a sung take: singing.zip and WORLD in wasm
    folders = {f"py-{render.folder_hash(py_files)}": py_files, f"app-{render.folder_hash(app_files)}": app_files}
    if kit:
        folders[f"kit-{render.folder_hash(kit)}"] = kit
    py_dir, app_dir = list(folders)[:2]
    native = {"song": str(SONG), "machine": args.machine, "runs_with": runs_with()}
    if singing:
        native["sing_kit"] = str(Path(args.sing_kit).resolve())
    days = window(date.today(), args.days)
    first = first_answers(native, days) if days else {}
    if first:
        folders[f"first-{render.folder_hash(first)}"] = first

    files: dict[str, bytes] = page_files(singing)
    for folder, contents in folders.items():
        for name, data in contents.items():
            files[f"render/{folder}/{name}"] = data
    lock = json.loads(py_files["pyodide-lock.json"])
    sent = sum(len(gzip.compress(d, 6, mtime=0)) if Path(n).suffix in (".mjs", ".js", ".json", ".wasm") else len(d)
               for f, c in folders.items() if f.startswith(("py-", "app-")) for n, d in c.items())
    studio = {"song": "/app/songs/h-now-its-by-you.json", "machine": args.machine, "runs_with": runs_with()}
    if kit:
        studio["kit"] = f"{next(f for f in folders if f.startswith('kit-'))}/"
    # bytes: what a render worker fetches, and studio_bytes the studio's (numpy alone: lazy_imports), each as it
    # counts them; transfer: the whole bundle on the wire, the first time (the host compresses text and wasm)
    bundle = {"v": 1, "base": "/render/", "pyodide": py_dir, "app": app_dir, "packages": names,
              "bytes": fetched(py_files, app_files, lock, ["numpy", "scipy", "soundfile"]),
              "studio_bytes": fetched(py_files, app_files, lock, ["numpy"]),
              "transfer": sent, "program": program, "pyodide_version": version, "studio": studio}
    if first:  # the days the page's first answers are ready for, and where
        bundle["first"] = {"folder": f"{next(f for f in folders if f.startswith('first-'))}/", "from": days[0],
                           "to": days[-1]}
    files["render/bundle.json"] = (json.dumps(bundle, indent=2) + "\n").encode()

    big = [f"{rel} ({len(data) / 2**20:.1f} MiB)" for rel, data in files.items() if len(data) > MOST]
    if big:
        raise SystemExit("over Cloudflare's 25 MiB a file: " + ", ".join(big))
    described = {f"/{rel}": describe(rel) for rel in sorted(files)}
    site = {"v": 1, "program": program,
            "about": "docs/WEB-STUDIO.md, 'On the device': serve every file below at its path with its headers",
            "index": {"/": "/index.html", "/piano/": "/piano/index.html"},
            "rewrites": [{"from": "/v/*", "to": "/index.html", "status": 200}],
            "network": NETWORK,
            "headers": HEADERS, "files": described}

    if out.exists():
        shutil.rmtree(out)
    for rel, data in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (out / "site.json").write_text(json.dumps(site, indent=1) + "\n")
    largest = max(files.items(), key=lambda kv: len(kv[1]))
    print(f"{out}: {len(files)} files, {sum(map(len, files.values())) / 2**20:.1f} MiB "
          f"({sent / 2**20:.1f} MiB on the wire the first time); the largest {largest[0]} "
          f"({len(largest[1]) / 2**20:.1f} MiB); program {program[:12]}, machine {args.machine}"
          f"{f', singing ({len(kit)} kit files, {sum(map(len, kit.values())) / 2**20:.1f} MiB)' if singing else ''}"
          f"{f'; first answers for {len(first)} days, {days[0]} to {days[-1]} ({sum(map(len, first.values())) / 2**20:.1f} MiB)' if first else ''}")


if __name__ == "__main__":
    main()
