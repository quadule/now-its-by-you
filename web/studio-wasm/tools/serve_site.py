"""A static site built by build_site.py, served as its host would serve it, for trying it on this computer: every file
with site.json's headers, /v/<id> rewritten to the page, and a stand-in for the hosting Worker's two endpoints,
keeping shared versions in a folder (docs/WEB-STUDIO.md, "On the device").

usage: uv run python web/studio-wasm/tools/serve_site.py SITE [--port 8820] [--versions DIR]

    POST /api/versions        a FLAC (at most 64 MB, starting fLaC) -> 201 {"id": 32 hex, "url": "/v/<id>"}, or 4xx {"error"}
    GET  /api/versions/<id>   that file, as audio/flac, an attachment, with a policy that runs nothing

Standard library only; 127.0.0.1 only. Not the deploy: the Worker another part of the work builds is."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MOST = 64 * 2**20
# what the Worker must send a shared version with (docs/WEB-STUDIO.md, "On the device", "For the host"): bytes from
# anyone, served on the studio's own origin, so never as anything a browser would run or render
VERSION_HEADERS = {"Content-Type": "audio/flac", "X-Content-Type-Options": "nosniff",
                   "Content-Disposition": "attachment; filename=\"version.flac\"",
                   "Content-Security-Policy": "default-src 'none'; sandbox", "Cache-Control": "private, max-age=3600"}


def handler(site: Path, versions: Path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send(self, code: int, body: bytes, headers: dict) -> None:
            self.send_response(code)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code: int, data: dict) -> None:
            self._send(code, json.dumps(data).encode(), {"Content-Type": "application/json",
                                                         "X-Content-Type-Options": "nosniff"})

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            manifest = json.loads((site / "site.json").read_text())  # read each time: a build again is served at once
            files, index = manifest["files"], manifest.get("index", {})
            path = self.path.split("?", 1)[0].split("#", 1)[0]
            shared = re.fullmatch(r"/api/versions/([0-9a-f]{32})", path)
            if shared:
                f = versions / f"{shared.group(1)}.flac"
                if not f.is_file():
                    return self._json(404, {"error": "No version by that id."})
                said = manifest.get("network", {}).get("GET /api/versions/*", {})
                return self._send(200, f.read_bytes(), said.get("headers") if isinstance(said, dict) else VERSION_HEADERS)
            if path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if re.fullmatch(r"/v/[^/]*/?", path):  # the rewrite
                path = "/index.html"
            path = index.get(path, path)
            entry = files.get(path)
            if entry is None:
                return self._send(404, b"not found", {"Content-Type": "text/plain"})
            headers = {"Content-Type": entry["type"], "Cache-Control": entry["cache"], **manifest.get("headers", {})}
            if "csp" in entry:
                headers["Content-Security-Policy"] = entry["csp"]
            return self._send(200, (site / path.lstrip("/")).read_bytes(), headers)

        def do_POST(self) -> None:
            if self.path.split("?", 1)[0] != "/api/versions":
                return self._json(404, {"error": "not found"})
            try:
                length = int(self.headers.get("Content-Length") or -1)
            except ValueError:
                length = -1
            if not 0 < length <= MOST:
                self.close_connection = True
                return self._json(413, {"error": "A version is one FLAC file of at most 64 MB."})
            data = self.rfile.read(length)
            if not data.startswith(b"fLaC"):
                return self._json(415, {"error": "That isn't a FLAC file."})
            vid = secrets.token_hex(16)
            (versions / f"{vid}.flac").write_bytes(data)
            return self._json(201, {"id": vid, "url": f"/v/{vid}"})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site")
    parser.add_argument("--port", type=int, default=8820)
    parser.add_argument("--versions", help="where shared versions are kept (a new temporary folder if not given)")
    args = parser.parse_args()
    versions = Path(args.versions or tempfile.mkdtemp(prefix="songbird-versions-"))
    versions.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(Path(args.site).resolve(), versions))
    print(f"http://127.0.0.1:{args.port}/ (shared versions in {versions})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
