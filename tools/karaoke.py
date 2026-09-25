"""Karaoke: sing along to a song's guide and record takes for your phrasing (dev-only).

    uv run python tools/karaoke.py songs/h-now-its-by-you.json      # then open http://127.0.0.1:8765

A small server on this machine only. It serves one page (tools/karaoke.html)
that plays the guide track, shows the words as they come, and records the
microphone in the same audio clock as the playback, so every take lines up
with the guide exactly. Kept takes are saved to recordings/ (never tracked by
git). From the page you can then turn your takes into a phrasing
(tools/phrasing.py) and hear the machine sing the song your way.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import phrasing as T  # noqa: E402  (tools/phrasing.py)

from songbird import genome as G  # noqa: E402
from songbird import phrasing as P  # noqa: E402
from songbird.realize import choose_params  # noqa: E402

ROOT = Path(__file__).parent.parent
PAGE = Path(__file__).with_suffix(".html")


def lyrics(score: dict, title: str, tempo: float) -> dict:
    """The guide's words, line by line, with every syllable's time and pitch."""
    notes = sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    lines, current, left = [], [], 0
    for n in notes:
        left = left or n["word_len"]  # syllables still to come in this word
        left -= 1
        current.append({"text": n["syllable"], "start": n["start"], "end": n["start"] + n["dur"], "pitch": n["pitch"],
                        "word_end": left == 0})
        if n["line_end"]:
            lines.append((n["section"], current))
            current = []
    return {
        "title": title,
        "tempo": tempo,
        "duration": score["duration"],
        "sections": [{"name": s, "start": a, "end": b} for s, a, b in score["sections"]],
        "lines": [{"section": section, "start": line[0]["start"], "end": line[-1]["end"], "syllables": line}
                  for section, line in lines],
    }


class Karaoke(BaseHTTPRequestHandler):
    genome_path: Path
    genome = None

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def send(self, body: bytes, kind: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code: int = 200) -> None:
        self.send(json.dumps(data).encode(), "application/json", code)

    def guide(self) -> tuple[Path, Path]:
        stem = self.genome_path.stem
        wav = ROOT / "renders" / "guide" / f"{stem}.guide.wav"
        score = wav.with_name(f"{stem}.guide.score.json")
        if not wav.exists() or wav.stat().st_mtime < self.genome_path.stat().st_mtime:
            with contextlib.redirect_stdout(io.StringIO()):
                T.write_guide(self.genome_path, self.genome, 0)
        return wav, score

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/guide.wav":
            self.send(self.guide()[0].read_bytes(), "audio/wav")
        elif self.path == "/takes":
            kept = sorted((ROOT / "recordings").glob(f"{self.genome_path.stem}-*.wav"))
            self.send_json([str(f.relative_to(ROOT)) for f in kept])
        elif self.path == "/lyrics.json":
            score = json.loads(self.guide()[1].read_text())
            self.send_json(lyrics(score, self.genome.title, choose_params(self.genome).tempo))
        elif self.path.startswith("/renders/"):
            name = Path(self.path).name  # never a path out of renders/
            f = ROOT / "renders" / name
            if f.exists() and f.suffix in (".flac", ".wav"):
                self.send(f.read_bytes(), "audio/flac" if f.suffix == ".flac" else "audio/wav")
            else:
                self.send_json({"error": "no such render"}, 404)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if self.path == "/take":
                out = ROOT / "recordings" / f"{self.genome_path.stem}-{time.strftime('%Y%m%d-%H%M%S')}.wav"
                out.parent.mkdir(exist_ok=True)
                out.write_bytes(body)
                self.send_json({"path": str(out.relative_to(ROOT))})
            elif self.path == "/analyze":
                request = json.loads(body)
                takes = [str(ROOT / t) for t in request["takes"]]
                with contextlib.redirect_stdout(io.StringIO()):
                    seen, portrait = T.sung_phrasing(self.genome_path, self.genome, takes)
                    phrasing = T.gather(self.genome, seen)
                    who = request.get("name") or "the singer"
                    data = P.to_json(phrasing, source="song", source_detail=f"{len(takes)} sung take(s) by {who}",
                                     scale=T.SUNG)
                    out = ROOT / "renders" / "phrasing" / f"{self.genome_path.stem}.karaoke.json"
                    T.write(data, phrasing, out)
                self.send_json({"phrasing": str(out.relative_to(ROOT)),
                                "portrait": T.describe(portrait, choose_params(self.genome).tempo)})
            elif self.path == "/render":
                from songbird.cli import main as songbird

                request = json.loads(body)
                out = ROOT / "renders" / f"{self.genome_path.stem}.karaoke.flac"
                with contextlib.redirect_stdout(io.StringIO()):
                    songbird(["render", str(self.genome_path), "--phrasing", str(ROOT / request["phrasing"]),
                              "--choir", str(request.get("choir", 0)), "--out", str(out)])
                self.send_json({"url": f"/renders/{out.name}?t={int(time.time())}"})
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as e:  # report it on the page rather than dropping the connection
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    Karaoke.genome_path = Path(args.genome).resolve()
    Karaoke.genome = G.load(Karaoke.genome_path)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Karaoke)
    print(f"Karaoke for {Karaoke.genome.title}: open http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
