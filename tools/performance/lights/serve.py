"""Serves the show page: the film with the three lanterns drawn under it, and in Chrome the real lanterns too.

    python3 tools/performance/lights/serve.py            then open http://127.0.0.1:8870/ in Chrome

The page offers the final film in H.265 10-bit (played where the browser can, as Chrome on a Mac does) and in H.264
for other browsers, and the same pair at 4K when they are there; --film replaces them all with one video, --port
picks the port. The films are renders/performance/lights/film*.mp4: film-hevc.mp4 is a copy of
renders/promo/video/out/film-v11-live-A.mp4, render_4k.sh makes the 4K pair, and audio.py lays a new mix under all
four. The cues are renders/performance/lights/cues.bin (cues.py writes them). Range requests are answered, so the
film seeks.
"""

from __future__ import annotations

import argparse
import http.server
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
# the final film with the live mix, rendered for Chromium (H.264 High, 8-bit 4:2:0, CRF 10, 1080p60):
#   node tools/promo/video/capture/render.mjs --codec x264 --bits 10 --crf 10 --out renders/performance/lights/film.mp4
FILM = ROOT / "renders/performance/lights/film.mp4"
HEVC = ROOT / "renders/performance/lights/film-hevc.mp4"
FILMS_4K = {"/film-4k-hevc.mp4": ROOT / "renders/performance/lights/film-4k-hevc.mp4",
            "/film-4k.mp4": ROOT / "renders/performance/lights/film-4k.mp4"}
CUES = ROOT / "renders/performance/lights"


def handler(film: Path, hevc: Path | None):
    files = {
        "/": (HERE / "show.html", "text/html; charset=utf-8"),
        "/cues.bin": (CUES / "cues.bin", "application/octet-stream"),
        "/cues.json": (CUES / "cues.json", "application/json"),
        "/film.mp4": (film, "video/mp4"),
    }
    if hevc:
        files["/film-hevc.mp4"] = (hevc, "video/mp4")
        files.update({path: (file, "video/mp4") for path, file in FILMS_4K.items()})

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path not in files or not files[path][0].exists():
                self.send_error(404)
                return
            file, kind = files[path]
            size = file.stat().st_size
            start, end = 0, size - 1
            ranged = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            if ranged:
                if ranged[1]:
                    start = int(ranged[1])
                    end = int(ranged[2]) if ranged[2] else end
                else:
                    start = size - int(ranged[2])
            end = min(end, size - 1)
            self.send_response(206 if ranged else 200)
            self.send_header("Content-Type", kind)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Cache-Control", "no-store")
            if ranged:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(file, "rb") as f:
                f.seek(start)
                left = end - start + 1
                try:
                    while left > 0:
                        chunk = f.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def log_message(self, *args):
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8870)
    ap.add_argument("--film", type=Path)
    args = ap.parse_args()
    film, hevc = (args.film, None) if args.film else (FILM, HEVC)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler(film, hevc))
    print(f"http://127.0.0.1:{args.port}/  ({film.name}{', ' + hevc.name if hevc else ''})")
    server.serve_forever()


if __name__ == "__main__":
    main()
