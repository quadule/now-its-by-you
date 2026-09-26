"""Karaoke: sing along to a song's guide and record takes for your phrasing (dev-only).

    uv run python tools/karaoke.py songs/h-now-its-by-you.json      # then open http://127.0.0.1:8765

A small server on this machine only. It serves one page (tools/karaoke.html)
that plays the guide track, shows the words as they come, and records the
microphone in the same audio clock as the playback, so every take lines up
with the guide exactly. Whoever sings puts their name in first: kept takes go
to recordings/<name>/ (never tracked by git, tools/takes.py), and each
singer's takes become that singer's phrasing (tools/phrasing.py), so several
people can sing without blending into one another. Then hear the machine sing
the song one person's way, or everyone's way at once, with the other singers
in the lineage choir.
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
from urllib.parse import parse_qs, urlsplit

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import takes as K  # noqa: E402  (tools/takes.py)

from songbird import genome as G  # noqa: E402
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

    def phrasing_path(self, who: str) -> Path:
        return ROOT / "renders" / "phrasing" / f"{self.genome_path.stem}.{who}.json"

    def singers(self) -> list[dict]:
        out = []
        for who, kept in K.singers(self.genome_path.stem).items():
            phrasing = self.phrasing_path(who)
            out.append({
                "who": who,
                "name": kept[-1].singer or who,
                "takes": [{"path": t.rel, "use": t.use, "recorded": t.info.get("recorded", "")} for t in kept],
                "phrasing": phrasing.relative_to(ROOT).as_posix() if phrasing.exists() else None,
            })
        return out

    def do_GET(self) -> None:
        self.path = urlsplit(self.path).path  # a ?t=... only busts the browser's cache
        if self.path in ("/", "/index.html"):
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/guide.wav":
            self.send(self.guide()[0].read_bytes(), "audio/wav")
        elif self.path == "/singers":
            self.send_json(self.singers())
        elif self.path == "/lyrics.json":
            score = json.loads(self.guide()[1].read_text())
            self.send_json(lyrics(score, self.genome.title, choose_params(self.genome).tempo))
        elif self.path.startswith("/recordings/"):
            f = (ROOT / self.path.lstrip("/")).resolve()  # only a take, never a path out of recordings/
            if f.is_relative_to(K.RECORDINGS) and f.suffix == ".wav" and f.exists():
                self.send(f.read_bytes(), "audio/wav")
            else:
                self.send_json({"error": "no such take"}, 404)
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
        url = urlsplit(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            if url.path == "/take":
                singer = query.get("singer", "").strip()
                if not singer:
                    raise ValueError("a take needs the singer's name")
                info = {k: float(query[k]) for k in ("shift_ms", "auto_ms", "device_ms") if k in query}
                take = K.keep(self.genome_path.stem, singer, body, self.guide()[1], **info)
                self.send_json({"path": take.rel, "who": take.who})
            elif url.path == "/use":
                request = json.loads(body)
                take = K.load(ROOT / request["path"])
                if not take.path.is_relative_to(K.RECORDINGS):
                    raise ValueError("not a take")
                take.use = bool(request["use"])
                take.save()
                self.send_json({"ok": True})
            elif url.path == "/analyze":
                request = json.loads(body)
                who = K.slug(request["who"])
                chosen = [t for t in K.takes(self.genome_path.stem, who) if t.use]
                if not chosen:
                    raise ValueError(f"{who} has no takes marked to use")
                with contextlib.redirect_stdout(io.StringIO()):
                    credit = chosen[-1].singer if request.get("credit") else None
                    phrasing, data, portrait = T.singer_phrasing(self.genome_path, self.genome, chosen, credit)
                    T.write(data, phrasing, self.phrasing_path(who))
                self.send_json({"phrasing": self.phrasing_path(who).relative_to(ROOT).as_posix(),
                                "portrait": T.describe(portrait, choose_params(self.genome).tempo)})
            elif url.path == "/render":
                self.send_json(self.render(json.loads(body)))
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as e:  # report it on the page rather than dropping the connection
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def render(self, request: dict) -> dict:
        """The machine sings: one singer's way (lead: their folder name), everyone's
        blended ("everyone"), or its own (""); with the choir, the other
        singers' phrasings are its voices, and stand-ins fill it out to three."""
        from songbird.cli import main as songbird

        lead = request.get("lead", "")
        have = {s["who"]: ROOT / s["phrasing"] for s in self.singers() if s["phrasing"]}
        args = []
        if lead == "everyone":  # every singer's takes at once, each person counting once
            chosen = [t for t in K.takes(self.genome_path.stem) if t.use and t.who in have]
            with contextlib.redirect_stdout(io.StringIO()):
                phrasing, data, _ = T.singer_phrasing(self.genome_path, self.genome, chosen)
                data["source_detail"] = f"{len(chosen)} sung takes by {len(have)} singers"
                T.write(data, phrasing, self.phrasing_path("everyone"))
            args += ["--phrasing", str(self.phrasing_path("everyone"))]
        elif lead:
            args += ["--phrasing", str(have[lead])]
        if request.get("choir"):
            others = [str(f) for who, f in have.items() if who != lead]
            args += ["--choir", str(max(3, len(others)))] + (["--choir-phrasing", *others] if others else [])
        out = ROOT / "renders" / f"{self.genome_path.stem}.karaoke.{lead or 'plain'}.flac"
        with contextlib.redirect_stdout(io.StringIO()):
            songbird(["render", str(self.genome_path), *args, "--out", str(out)])
        return {"url": f"/renders/{out.name}?t={int(time.time())}"}


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
