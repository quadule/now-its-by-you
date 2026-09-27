"""Karaoke: sing along to a song's guide and record takes for your phrasing (dev-only).

    uv run python tools/karaoke.py songs/h-now-its-by-you.json      # then open http://127.0.0.1:8765

A small server on this machine only. It serves one page (tools/karaoke.html)
that plays a guide, shows the words as they come, and records the
microphone in the same audio clock as the playback, so every take lines up
with the guide exactly. The guide is the tune alone on a whistle over a quiet
pulse (melody, the default), the whole song (full) or the machine's singer
alone (voice): all three follow one score, so a take is measured the same
whichever was heard, and its sidecar says which (tools/guides.py). Whoever
sings puts their name in first: kept takes go to recordings/<name>/ (never
tracked by git, tools/takes.py), and each singer's takes become that
singer's phrasing (tools/phrasing.py), so several people can sing without
blending into one another. Then hear the machine sing the song one person's
way, or everyone's way at once, with the other singers in the lineage choir.
The same page, for singers anywhere, is web/sing (docs/SING-ONLINE.md).

A singer can also choose a spec (tools/guides.py): a set of the song's words,
a key and a speed, each with its own guide, rendered the first time it's asked
for; and record one section at a time, from its window (sections()).

    GET  /variants                        the sets, keys, speeds and mixes on offer, and the default
    GET  /lyrics.json?spec=a.k-2.t90      its words, notes, beats and sections (no spec: the single guide)
    GET  /guide.wav?spec=a.k-2.t90&mix=melody     (X-Guide-Score: the digest of the score it follows)
    POST /take?singer=&mix=&guide=&spec=&from_s=&to_s=&section=&shift_ms=&auto_ms=&device_ms=
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import io
import json
import math
import sys
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import everyone as EV  # noqa: E402  (tools/everyone.py)
import guides as M  # noqa: E402  (tools/guides.py)
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import takes as K  # noqa: E402  (tools/takes.py)

from songbird import genome as G  # noqa: E402
from songbird.realize import choose_params  # noqa: E402

ROOT = Path(__file__).parent.parent
PAGE = Path(__file__).with_suffix(".html")
# what the page shares with the online one (web/sing): its timing, sync and drawing, and the take recorder
SLOWER = 90  # the speed a singer starts at, a little slower than written (the artist's choice; as tools/sing_site.py)
CHOIR = 3  # the choir's voices: its harmony has three lines, and more voices would only double them lower
SCRIPTS = {"/karaoke.js": Path(__file__).with_suffix(".js"), "/recorder.js": Path(__file__).with_name("karaoke-recorder.js")}


def lyrics(score: dict, title: str, tempo: float) -> dict:
    """The guide's words, line by line, with every syllable's time and pitch, the beats
    (seconds) its notes were placed on, to count each line in, and its sections (sections())."""
    notes = sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"])
    lines, current, left = [], [], 0
    for n in notes:
        left = left or n["word_len"]  # syllables still to come in this word
        left -= 1
        current.append({"text": n["syllable"].replace("*", ""), "start": n["start"], "end": n["start"] + n["dur"], "pitch": n["pitch"],
                        "word_end": left == 0})
        if n["line_end"]:
            lines.append((n["section"], current))
            current = []
    return {
        "title": title,
        "tempo": tempo,
        "duration": score["duration"],
        "sections": sections(score),
        "lines": [{"section": section, "start": line[0]["start"], "end": line[-1]["end"], "syllables": line}
                  for section, line in lines],
        "beats": [round(t, 4) for t, _ in score.get("beats", [])],
    }


def sections(score: dict) -> list[dict]:
    """The guide's sections in order, {"index", "name", "start", "end", "sung"}, and for each sung
    one, which of its kind it is ("nth": verse 1, verse 2..., bridge2 the second bridge), its
    first line as plain words ("label", written()), and the window for recording it alone
    ("window": [from, to], seconds): from the downbeat two bars before its first sung note (a
    pickup's bar line counts: after a turn, the turn's first downbeat), never before the song's
    start, to a bar after its last sung note ends, so the last word's fall isn't cut off, never
    after the song's end."""
    beats = [(float(t), bool(bar)) for t, bar in score.get("beats") or []]
    duration = float(score["duration"])
    spans = score["sections"]
    # each sung note is its section's, by name and time: a pickup reaches back into what comes before, a bar at most
    times = [t for t, _ in beats]
    reach = per_bar(beats) * float(np.median(np.diff(times))) if len(times) > 1 else 2.0
    sung: dict[int, list[dict]] = {}
    for n in sorted((n for n in score["notes"] if n["part"] == "voice"), key=lambda n: n["start"]):
        mine = [i for i, (name, a, b) in enumerate(spans) if name == n["section"] and a - reach <= n["start"] < b]
        if mine:
            sung.setdefault(mine[-1], []).append(n)
    out, seen = [], {}
    for i, (name, a, b) in enumerate(spans):
        entry = {"index": i, "name": name, "start": a, "end": b, "sung": i in sung}
        if i in sung:
            kind = name.rstrip("0123456789") or name  # bridge2 is the second bridge
            seen[kind] = seen.get(kind, 0) + 1
            entry.update(nth=seen[kind], label=first_line(sung[i], score.get("lexicon")),
                         window=window(sung[i], beats, duration))
        out.append(entry)
    return out


def first_line(notes: list[dict], lexicon: dict | None = None) -> str:
    """The first line some sung notes sing, as plain words (written()): no *focus* marks, no
    syllable hyphens."""
    words, left = [], 0
    for n in notes:
        if not left:  # a word's first syllable: the whole word, as written
            words.append(n.get("word") or n["syllable"])
            left = n["word_len"]
        left -= 1
        if n["line_end"]:
            break
    return " ".join(written(w, lexicon) for w in words)


def written(word: str, lexicon: dict | None = None) -> str:
    """A word as it's read. The bank's hyphens split syllables and a compound's real hyphen alike
    ("half-in-vent-ed"), so they're told apart as songbird.phonetics tells them apart to say the
    word: closed up if the dictionary (or the song's lexicon) knows the whole word, or it's a
    regular inflection of one ("in-vent-ed": invented); else kept only between the fewest words
    it knows that cover the syllables (half-invented, ninety-odd, half-asleep)."""
    from songbird import phonetics as ph

    pieces = [p for p in word.replace("*", "").split("-") if p]
    if len(pieces) < 2:
        return "".join(pieces)
    words, own = ph._dictionary(), {ph.clean(k.replace("-", "")) for k in lexicon or {}}
    whole = ph.clean("".join(pieces))
    if whole in words or whole in own or ph._inflected(whole):
        return "".join(pieces)
    best: list[list[tuple[int, int]] | None] = [[]] + [None] * len(pieces)  # the fewest words to cover pieces[:k]
    for end in range(1, len(pieces) + 1):
        for start in range(end):
            chunk = ph.clean("".join(pieces[start:end]))
            if (best[start] is not None and chunk and (chunk in words or chunk in own)
                    and (best[end] is None or len(best[start]) + 1 < len(best[end]))):
                best[end] = best[start] + [(start, end)]
    return "-".join("".join(pieces[a:b]) for a, b in best[-1]) if best[-1] else "".join(pieces)


def window(notes: list[dict], beats: list[tuple[float, bool]], duration: float, bars: int = 2) -> list[float]:
    """Where to start playing to record some sung notes alone, and where to stop (sections())."""
    times, bar = [t for t, _ in beats], per_bar(beats)
    first, last = notes[0]["start"], notes[-1]["start"] + notes[-1]["dur"]
    # the beat the first note is on, or a pickup's beat before it; back two bars less a beat, to a bar line
    k = bisect.bisect_right(times, first + 0.05) - 1 - (bars * bar - 1)
    while k > 0 and not beats[k][1]:
        k -= 1
    start = times[k] if k >= 0 and beats[k][1] else 0.0
    # a bar of the beats around the last note's end
    j = min(max(bisect.bisect_right(times, last) - 1, 0), max(len(times) - 2, 0))
    beat = times[j + 1] - times[j] if len(times) > 1 else 0.5
    return [round(max(start, 0.0), 4), round(min(last + bar * beat, duration), 4)]


def per_bar(beats: list[tuple[float, bool]]) -> int:
    """Beats to a bar, from where the bars begin."""
    downbeats = [k for k, (_, bar) in enumerate(beats) if bar]
    return int(np.median(np.diff(downbeats))) if len(downbeats) > 1 else 4


def where(score: dict, query: dict) -> dict:
    """Where in its guide a take sung to a spec was sung, for its sidecar, checked against the score
    it was sung to: the spec; the guide time of its first sample ("from_s": 0 from the top); where
    it was meant to end ("to_s": its window's end, or the song's); and the sung section it
    recorded alone ("section", its index; None for the whole song)."""
    spec = M.Spec.parse(query["spec"])
    if (score.get("spec") or {}).get("id") != spec.id:
        raise ValueError("the guide this take names isn't the spec it was sung to: reload the page")
    duration = float(score["duration"])
    section = query.get("section")
    section = None if section in (None, "", "null", "none") else int(section)
    start, end = 0.0, duration
    if section is not None:
        found = sections(score)
        if not 0 <= section < len(found) or not found[section]["sung"]:
            raise ValueError(f"the guide sings nothing in a section {section}")
        start, end = found[section]["window"]
    from_s, to_s = float(query.get("from_s", start)), float(query.get("to_s", end))
    if not (math.isfinite(from_s) and math.isfinite(to_s) and 0.0 <= from_s < to_s <= duration + 0.5):
        raise ValueError(f"a take from {from_s} s to {to_s} s isn't inside its {duration:.1f} s guide")
    return {"spec": spec.id, "from_s": from_s, "to_s": to_s, "section": section}


def spec_lyrics(genome_path: Path, title: str, spec) -> dict:
    """A spec's words and notes as the page shows them (lyrics()), with its score's digest and the
    spec: from its score alone, written if need be (quick, no audio). The score is kept beside the
    takes as it's handed out, so a take sung to it is kept even if the spec is rendered again
    while it's sung (its set changed, say)."""
    score = M.spec_score(genome_path, spec)
    data = json.loads(score.read_text())
    return {**lyrics(data, title, data["tempo"]), "guide": K.keep_guide(Path(genome_path).stem, score), "spec": data["spec"]}


def credited(takes: list) -> str | None:
    """The name a phrasing made from these takes may credit: the one the singer gave to be credited
    by, and only if every take says they want it (a take sung here says nothing: the singer was in
    the room to be asked); None if not."""
    if not takes or not all(t.info.get("credit", True) for t in takes):
        return None
    return takes[-1].info.get("credit_as", takes[-1].singer) or None


class Karaoke(BaseHTTPRequestHandler):
    genome_path: Path
    genome = None
    phrasing: Path | None = None  # what the machine sings the specs' full guides with (--phrasing)

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def send(self, body: bytes, kind: str, code: int = 200, headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code: int = 200) -> None:
        self.send(json.dumps(data).encode(), "application/json", code)

    def guide(self, mix: str = "full") -> M.Mix:
        """A guide mix's WAV, the score every mix follows and its digest, rendered if missing or
        stale (from the genome file as it is now)."""
        return M.ensure(self.genome_path, None, mix)

    @staticmethod
    def mix(mix) -> str:
        if mix not in M.MIXES:
            raise ValueError(f"no guide mix {mix!r}")
        return mix

    def spec_guide(self, spec) -> M.Mix:
        """A spec's score and its digest (the page's default mix beside them): all a take needs, so
        nothing waits for audio."""
        score = M.spec_score(self.genome_path, spec)
        return M.Mix(M.spec_path(self.genome_path.stem, spec, M.DEFAULT), score, K.digest(score))

    def phrasing_path(self, who: str) -> Path:
        return ROOT / "renders" / "phrasing" / f"{self.genome_path.stem}.{who}.json"

    def singers(self) -> list[dict]:
        out = []
        for who, kept in K.singers(self.genome_path.stem).items():
            phrasing = self.phrasing_path(who)
            out.append({
                "who": who,
                "name": kept[-1].singer or who,
                # which spec and section each take sang (a whole-song take: section None; before specs: spec None)
                "takes": [{"path": t.rel, "use": t.use, "recorded": t.info.get("recorded", ""),
                           "mix": t.info.get("mix", "full"), "online": t.info.get("source") == "online",
                           "guide": t.guide, **{k: t.info.get(k) for k in ("spec", "section", "from_s", "to_s")}}
                          for t in kept],
                "credit": credited(kept) is not None,
                "phrasing": phrasing.relative_to(ROOT).as_posix() if phrasing.exists() else None,
            })
        return out

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        self.path = url.path  # a ?t=... only busts the browser's cache
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            self.get(query)
        except ValueError as e:  # a spec or mix that isn't on offer
            self.send_json({"error": str(e)}, 404)
        except Exception as e:  # report it on the page rather than dropping the connection
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)

    def get(self, query: dict) -> None:
        if self.path in ("/", "/index.html"):
            self.send(PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path in SCRIPTS:
            self.send(SCRIPTS[self.path].read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/variants":
            offered = M.variants(self.genome_path)
            if SLOWER in offered["tempos"]:  # a singer starts a little slower than written: easier to learn
                offered["default"] = {**offered["default"], "tempo": SLOWER}
            self.send_json(offered)
        elif self.path == "/guide.wav" and "spec" in query:
            # a spec's guide, rendered the first time it's asked for (half a minute), and which score it follows
            guide = M.ensure_spec(self.genome_path, query["spec"], self.mix(query.get("mix", M.DEFAULT)),
                                  phrasing=self.phrasing)
            self.send(guide.wav.read_bytes(), "audio/wav", headers={"X-Guide-Score": guide.digest})
        elif self.path == "/guide.wav":
            mix = query.get("mix", "full")  # asked for without a mix, as before there was a choice: the full guide
            if mix not in M.MIXES:
                self.send_json({"error": f"no guide mix {mix!r}"}, 404)
            else:  # which score it follows, so the take can say what it was sung to
                guide = self.guide(mix)
                self.send(guide.wav.read_bytes(), "audio/wav", headers={"X-Guide-Score": guide.digest})
        elif self.path == "/singers":
            self.send_json(self.singers())
        elif self.path == "/lyrics.json" and "spec" in query:
            self.send_json(spec_lyrics(self.genome_path, self.genome.title, query["spec"]))
        elif self.path == "/lyrics.json":
            guide = self.guide()
            score = json.loads(guide.score.read_text())
            words = lyrics(score, self.genome.title, score.get("tempo") or choose_params(self.genome).tempo)
            self.send_json({**words, "guide": guide.digest})
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
                if query.get("aec") == "1":  # sung without headphones, the guide taken out of the microphone
                    info["aec"] = True
                mix, heard = query.get("mix"), query.get("guide", "")
                if mix not in M.MIXES:
                    raise ValueError("a take must say which guide it was sung to: reload the page")
                song = self.genome_path.stem
                # every mix follows its guide's score: a spec's, or the single guide's
                now = self.spec_guide(query["spec"]) if query.get("spec") else self.guide()
                if heard == now.digest:
                    sung_to = now.score
                elif heard and K.guide_score(song, heard):  # sung to an earlier guide, which is still kept
                    sung_to = K.guide_score(song, heard)
                else:
                    raise ValueError("the guide changed while you sang (the song was rendered again): reload and sing it anew")
                if query.get("spec"):
                    info.update(where(json.loads(sung_to.read_text()), query))
                if heard == now.digest:
                    take = K.keep(song, singer, body, now.score, mix=mix, **info)
                else:
                    take = K.keep_sung(song, singer, body, heard, mix=mix, **info)
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
                    credit = credited(chosen) if request.get("credit") else None
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

    def blend(self, name: str, takes: list) -> Path:
        """A phrasing from these takes, each person counting once, kept as renders/phrasing/<song>.<name>.json
        (a name no singer's folder can have: "everyone", "choir.1"); tools/everyone.py does the same by hand."""
        return EV.blend(self.genome_path, self.genome, name, takes)

    def render(self, request: dict) -> dict:
        """The machine sings: one singer's way (lead: their folder name), everyone's
        blended ("everyone": every take ticked to count, whether or not its singer's
        phrasing has been made), or its own (""); with the choir, the other singers
        are its voices, each their own way, or, with more of them than the choir has
        voices, several blended in each, so everyone who sang is in it; stand-ins
        fill it out to three."""
        from songbird.cli import main as songbird

        lead = request.get("lead", "")
        have = {s["who"]: ROOT / s["phrasing"] for s in self.singers() if s["phrasing"]}
        counted = [t for t in K.takes(self.genome_path.stem) if t.use]
        args = []
        if lead == "everyone":  # every singer's takes at once, each person counting once
            args += ["--phrasing", str(self.blend("everyone", counted))]
        elif lead:
            args += ["--phrasing", str(have[lead])]
        if request.get("choir"):
            voices = [str(v) for v in EV.choir_blends(self.genome_path, self.genome, counted, lead, CHOIR)]
            args += ["--choir", str(CHOIR)] + (["--choir-phrasing", *voices] if voices else [])
        out = ROOT / "renders" / f"{self.genome_path.stem}.karaoke.{lead or 'plain'}.flac"
        with contextlib.redirect_stdout(io.StringIO()):
            songbird(["render", str(self.genome_path), *args, "--out", str(out)])
        return {"url": f"/renders/{out.name}?t={int(time.time())}"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--phrasing", help="a phrasing file the machine's singer sings the specs' full guides with, "
                                       "everyone's say (the words and the takes stay on the grid)")
    args = ap.parse_args()
    Karaoke.phrasing = Path(args.phrasing).resolve() if args.phrasing else None
    Karaoke.genome_path = Path(args.genome).resolve()
    Karaoke.genome = G.load(Karaoke.genome_path)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Karaoke)
    print(f"Karaoke for {Karaoke.genome.title}: open http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
