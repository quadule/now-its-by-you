"""Build the page singers use anywhere, for one song: web/sing/public/ (dev-only).

    uv run python tools/sing_site.py                                          # H, every spec, into web/sing/public
    uv run python tools/sing_site.py --sets a --keys 0,-2 --tempos 100        # only these specs
    uv run python tools/sing_site.py songs/h-now-its-by-you.json --rebuild    # render every guide again first
    cd web/sing && npx wrangler deploy                                        # then publish it (docs/SING-ONLINE.md)

What it writes, all served by web/sing/src/worker.js:

    index.html, sing.css, sing.js...  the pages (web/sing/page/), with the releases in them: for recording
                                      (web/sing/consent.md) and for words people send (words-release.md)
    karaoke.js, recorder.js           the timing core they share with the karaoke here (tools/karaoke.js)
    song/song.json                    what's on offer (v2): the sets, keys and speeds, and for every spec
                                      its guide score's digest, its words' file, and each mix's MP3 and
                                      its length; the releases' digests. Small, as a phone reads it first
    song/<spec>.json                  a spec's words and notes as they come, its beats, and its sections,
                                      each sung one with its window for recording it alone (karaoke.lyrics);
                                      and each mix's opening loudness ("opening"), so the page can tell if
                                      an MP3 decoder put silence in front: fetched only for the spec chosen
    song/<spec>.<mix>.mp3             its guides (tools/guides.py), melody and full, encoded with ffmpeg in
                                      mono (a phone decodes each to a buffer; stereo would double it): the
                                      melody at 64 kbps if it decodes in time with its guide (else 96), the
                                      full guide at 96
    _headers                          the security headers for the files served without the worker
    yours.html, yours.css, yours.js   each singer's own page (web/sing/page/), at /y/<singer>
    song/worker.json                  what the worker needs of song.json: it reads it on a cold start, well
                                      within the free plan's 10 ms of work a request

Every spec is a set (tools/sets/<song>.json) in every key and at every speed
(guides.KEYS, TEMPOS), rendered in parallel (--jobs) or found current in
renders/guide/<song>/, where each spec's MP3s are kept too, and used again while
what they were made from holds: a build of fewer specs, or with a release changed,
renders nothing. Once encoded, a spec's WAVs are let go (--keep-wavs keeps them for
the karaoke here, about 130 MB a spec). A full build of H (6 sets, 90 specs) takes
about half an hour on this machine (--jobs 4, 32 GB).

The worker serves song/ only to an open invitation. Each guide score is kept in
recordings/guides/ (tools/takes.py), so takes fetched with tools/invite.py are
measured against exactly what their singers heard, whatever the song does next;
beside them, release.<digest>.html and words-release.<digest>.html keep each
release exactly as people read it, under the digest their takes and words carry.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import multiprocessing
import re
import shutil
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
import guides as M  # noqa: E402  (tools/guides.py)
import takes as K  # noqa: E402  (tools/takes.py)

ROOT = Path(__file__).parent.parent
WEB = ROOT / "web" / "sing"
MIXES = ("melody", "full")  # what singers choose between; the tune alone first, and by default
BITRATE = "96k"
MELODY_BITRATE = "64k"  # the whistle and the pulse carry at 64 as well as at 96, in two thirds the bytes
JOBS = 4  # specs rendered at once: a render takes one core and up to 3 GB (a 4-minute spec)
FRAME = 0.001  # seconds per step of a guide's opening loudness
OPENING = 2.5  # seconds of it kept: the song's first sounds are at 0.6 s
MARK = ".songbird-site"  # in an output directory this tool may clear


def consent_html(text: str) -> str:
    """The release as HTML: paragraphs, "- " lists and "## " headings, **bold** and *italic*;
    everything else escaped, <!-- comments --> left out."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)

    def inline(s: str) -> str:
        s = html.escape(" ".join(s.split()), quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        return re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)

    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if lines[0].startswith("- "):
            items, current = [], []
            for line in lines:
                if line.startswith("- ") and current:
                    items.append(" ".join(current))
                    current = []
                current.append(line[2:] if line.startswith("- ") else line.strip())
            items.append(" ".join(current))
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
        elif lines[0].startswith("## "):
            out.append(f"<h3>{inline(lines[0][3:])}</h3>" + (f"<p>{inline(' '.join(lines[1:]))}</p>" if lines[1:] else ""))
        else:
            out.append(f"<p>{inline(block)}</p>")
    return "\n".join(out)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def envelope(x: np.ndarray, rate: int, seconds: float = OPENING, frame: float = FRAME) -> np.ndarray:
    """RMS in `frame`-second windows over the first `seconds` of a mono signal: the same steps
    as envelope() in tools/karaoke.js, which the page measures the decoded guide with."""
    n = int(np.floor(seconds / frame))
    out = np.zeros(n)
    for k in range(n):
        a, b = int(np.floor(k * frame * rate)), min(int(np.floor((k + 1) * frame * rate)), len(x))
        out[k] = np.sqrt(np.mean(x[a:b] ** 2)) if b > a else 0.0
    return out


def decode_offset(decoded: np.ndarray, rate: int, reference, frame: float = FRAME, reach: float = 0.08) -> float:
    """decodeOffset() in tools/karaoke.js, in numpy: seconds of silence a decoder put in front of
    the guide, found against the original's opening loudness; 0 if nothing clearly matches."""
    ref = np.asarray(reference, dtype=float)
    env = envelope(decoded, rate, len(ref) * frame + reach + 0.01, frame)

    def norm(a):
        d = a - a.mean()
        return d / (np.linalg.norm(d) or 1.0)

    r = norm(ref)
    lags = list(range(-5, int(round(reach / frame)) + 1))
    corr = []
    for lag in lags:
        seg = np.array([env[k + lag] if 0 <= k + lag < len(env) else 0.0 for k in range(len(r))])
        corr.append(float(np.dot(r, norm(seg))))
    i = int(np.argmax(corr))
    if corr[i] < 0.8:
        return 0.0
    lag = float(lags[i])
    if 0 < i < len(corr) - 1:
        den = corr[i - 1] - 2 * corr[i] + corr[i + 1]
        if den < 0:
            lag += 0.5 * (corr[i - 1] - corr[i + 1]) / den
    seconds = lag * frame
    return 0.0 if abs(seconds) < 0.002 else seconds


def ffmpeg(*args: str) -> bytes:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg isn't installed (brew install ffmpeg)")
    return subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", *args], check=True,
                          capture_output=True).stdout


def decode(mp3: Path, rate: int, gapless: bool = True) -> np.ndarray:
    """An MP3 decoded to mono floats at `rate`; gapless=False keeps the encoder's delay in front,
    as a decoder that ignores the LAME tag would."""
    flags = [] if gapless else ["-flags2", "+skip_manual"]
    raw = ffmpeg(*flags, "-i", str(mp3), "-f", "f32le", "-ac", "1", "-ar", str(rate), "-")
    return np.frombuffer(raw, dtype="<f4").astype(float)


class OutOfTime(ValueError):
    """An MP3 that doesn't decode in time with its guide."""


def encode(wav: Path, mp3: Path, bitrate: str = BITRATE) -> dict:
    """The guide as an MP3, and what the page needs to know about the original; OutOfTime if the
    MP3 doesn't decode as long as the guide, or its opening doesn't line up with the guide's."""
    import soundfile as sf

    ffmpeg("-y", "-i", str(wav), "-ac", "1", "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3))
    x, rate = sf.read(wav)
    mono = x.mean(axis=1) if x.ndim > 1 else x
    env = envelope(mono, rate)
    heard = decode(mp3, rate)
    drift = decode_offset(heard, rate, env)
    if abs(len(heard) - len(mono)) > 0.01 * rate or abs(drift) > 0.002:
        raise OutOfTime(f"{mp3.name} doesn't decode in time with its guide "
                        f"({len(heard) - len(mono)} samples, {drift * 1000:.1f} ms)")
    return {"file": mp3.name, "bytes": mp3.stat().st_size, "rate": rate, "samples": len(mono),
            "seconds": round(len(mono) / rate, 3), "frame": FRAME, "env": [round(float(v), 5) for v in env]}


def encode_first(wav: Path, mp3: Path, bitrates) -> dict:
    """The guide at the first of these bitrates at which it decodes in time with itself."""
    for i, bitrate in enumerate(bitrates):
        try:
            return encode(wav, mp3, bitrate)
        except OutOfTime:
            if i == len(bitrates) - 1:
                raise
    raise ValueError("no bitrate to encode at")


def clear(out: Path) -> None:
    """Empty an output directory this tool made before (it leaves a mark), or refuse."""
    if out.exists() and any(out.iterdir()):
        if not (out / MARK).exists():
            raise SystemExit(f"{out} isn't empty and wasn't built here: choose another --out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARK).write_text("built by tools/sing_site.py; cleared on every build\n")
    (out / ".assetsignore").write_text(f"{MARK}\n.assetsignore\n")  # neither is published


def specs(genome_path: Path, sets=None, keys=None, tempos=None) -> list[M.Spec]:
    """The specs to build, in order: every set, key and speed (guides.sets, KEYS, TEMPOS), or only
    those named."""
    have = [s["id"] for s in M.sets(genome_path)]
    unknown = sorted(set(sets or ()) - set(have)) + [k for k in keys or () if k not in M.KEYS] + \
        [t for t in tempos or () if t not in M.TEMPOS]
    if unknown:
        raise SystemExit(f"nothing called {', '.join(map(str, unknown))} to build: the sets are {', '.join(have)}, the "
                         f"keys {', '.join(map(str, M.KEYS))}, the speeds {', '.join(map(str, M.TEMPOS))}")
    for s in have:  # every set sung once, quickly, so a set that can't be sung stops the build here
        if not sets or s in sets:
            try:
                M.spec_score(genome_path, M.Spec(s))
            except (KeyError, ValueError) as e:
                raise SystemExit(f"set {s} can't be sung: {e}") from e
    return [M.Spec(s, k, t) for s in have if not sets or s in sets for k in M.KEYS if not keys or k in keys
            for t in M.TEMPOS if not tempos or t in tempos]


def render(job: dict) -> dict:
    """One spec's guides encoded into the site: what song.json says of them. Each MP3 is kept
    beside the spec's mixes in renders/guide/<song>/ with a note of what it was made from
    (guides.made_from) and at which bitrates, and used again while that holds; otherwise the
    mixes are rendered (or found current) and encoded. Then, unless asked to keep them, the
    spec's WAVs are let go (about 130 MB a spec; the karaoke renders them again when asked).
    Runs in a process of its own, so it's told where everything is."""
    M.GUIDES, M.SETS = Path(job["guides"]), Path(job["sets"])
    genome_path, spec, song = Path(job["genome"]), M.Spec.parse(job["spec"]), Path(job["out"]) / "song"
    phrasing = Path(job["phrasing"]) if job.get("phrasing") else None
    rates = {"melody": [job["melody_bitrate"], job["bitrate"]], "full": [job["bitrate"]]}
    score = M.spec_score(genome_path, spec)
    made = M.made_from(score, phrasing)
    kept = {mix: M.spec_path(genome_path.stem, spec, mix).with_suffix(".mp3") for mix in MIXES}
    notes = {mix: kept[mix].with_name(kept[mix].name + ".json") for mix in MIXES}

    def current(mix):
        note = M._read(notes[mix])
        return (note.get("from") == made and note.get("bitrates") == rates[mix] and kept[mix].exists()
                and note["info"]["bytes"] == kept[mix].stat().st_size)

    if job["rebuild"] or not all(current(mix) for mix in MIXES):
        guide = M.ensure_spec(genome_path, spec, MIXES[0], phrasing=phrasing, rebuild=job["rebuild"])
        score, made = guide.score, M.made_from(guide.score, phrasing)
        for mix in MIXES:
            info = encode_first(M.spec_path(genome_path.stem, spec, mix), kept[mix], rates[mix])
            M._write(notes[mix], json.dumps({"from": made, "bitrates": rates[mix], "info": info}) + "\n")
    mixes = {}
    for mix in MIXES:
        shutil.copyfile(kept[mix], song / kept[mix].name)
        mixes[mix] = M._read(notes[mix])["info"]
    if not job.get("keep_wavs"):
        for mix in M.MIXES:
            M.spec_path(genome_path.stem, spec, mix).unlink(missing_ok=True)
    return {"spec": spec.id, "score": str(score), "guide": made["score"], "mixes": mixes}


def build(genome_path: Path, out: Path, rebuild: bool = False, bitrate: str = BITRATE, sets=None, keys=None,
          tempos=None, jobs: int = JOBS, phrasing: Path | None = None, melody_bitrate: str = MELODY_BITRATE,
          progress=None, keep_wavs: bool = False) -> dict:
    """The site for one song in out (cleared first), and its song.json. sets, keys, tempos: build
    only these (default all). jobs: specs rendered at once, each in a process of its own. phrasing:
    a phrasing file the machine's lead sings the full guides with. progress, if given, is told
    each spec as it's done. keep_wavs: keep each spec's rendered mixes for the karaoke here
    (render())."""
    import karaoke  # tools/karaoke.py, for the words as they come

    from songbird import genome as G

    genome_path = Path(genome_path).resolve()
    genome = G.load(genome_path)
    todo = specs(genome_path, sets, keys, tempos)
    clear(out)
    (out / "song").mkdir()

    texts = {name: consent_html((WEB / f"{name}.md").read_text()) for name in ("consent", "words-release")
             if (WEB / f"{name}.md").exists()}
    if "words-release" not in texts:
        raise SystemExit("web/sing/words-release.md is missing: the page asks people to agree to it before sending words")
    agreed, words = digest(texts["consent"]), digest(texts["words-release"])
    fill = {"{{CONSENT_DIGEST}}": agreed, "{{CONSENT}}": texts["consent"],
            "{{WORDS_DIGEST}}": words, "{{WORDS_RELEASE}}": texts["words-release"]}
    page = (WEB / "page" / "index.html").read_text()
    if "{{CONSENT}}" not in page or "{{CONSENT_DIGEST}}" not in page:
        raise SystemExit("web/sing/page/index.html has lost its {{CONSENT}} or {{CONSENT_DIGEST}}")
    for f in sorted((WEB / "page").iterdir()):  # the pages with the releases in them, and what they load
        if f.is_file() and not f.name.startswith("."):
            if f.suffix == ".html":
                text = f.read_text()
                for mark, value in fill.items():
                    text = text.replace(mark, value)
                (out / f.name).write_text(text)
            else:
                shutil.copyfile(f, out / f.name)
    shutil.copyfile(ROOT / "tools" / "karaoke.js", out / "karaoke.js")
    shutil.copyfile(ROOT / "tools" / "karaoke-recorder.js", out / "recorder.js")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (out / "favicon.svg").write_text(FAVICON)
    (out / "_headers").write_text(HEADERS)
    # each release as people read it, kept by the digest their takes and words carry
    K.GUIDES.mkdir(parents=True, exist_ok=True)
    (K.GUIDES / f"release.{agreed}.html").write_text(texts["consent"] + "\n")
    (K.GUIDES / f"words-release.{words}.html").write_text(texts["words-release"] + "\n")

    common = {"genome": str(genome_path), "out": str(out), "guides": str(M.GUIDES), "sets": str(M.SETS),
              "rebuild": rebuild, "bitrate": bitrate, "melody_bitrate": melody_bitrate,
              "phrasing": str(phrasing) if phrasing else None, "keep_wavs": keep_wavs}
    work = [{**common, "spec": spec.id} for spec in todo]
    done: dict[str, dict] = {}
    if jobs <= 1:
        for job in work:
            done[job["spec"]] = render(job)
            if progress:
                progress(job["spec"], len(done), len(work))
    else:  # each in a fresh process: the synthesis isn't made to share one
        with concurrent.futures.ProcessPoolExecutor(jobs, mp_context=multiprocessing.get_context("spawn")) as pool:
            futures = [pool.submit(render, job) for job in work]
            try:
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    done[result["spec"]] = result
                    if progress:
                        progress(result["spec"], len(done), len(work))
            except BaseException:  # one failed, or Ctrl-C: nothing more is started
                for future in futures:
                    future.cancel()
                raise

    guides, longest = {}, 0.0
    for spec in todo:
        result = done[spec.id]
        score = Path(result["score"])
        guide = K.keep_guide(genome_path.stem, score)  # so takes sung to it can always be measured against it
        if guide != result["guide"]:
            raise SystemExit(f"{spec.id}'s guide changed while the site was built: build it again")
        data = json.loads(score.read_text())
        # each mix's opening loudness travels with the spec's words, fetched only when the spec is chosen:
        # in song.json, 90 specs' curves came to megabytes that a phone read before anything else
        opening = {mix: {"frame": m["frame"], "env": m["env"]} for mix, m in result["mixes"].items()}
        words_json = {**karaoke.lyrics(data, genome.title, data["tempo"]), "guide": guide, "spec": data["spec"],
                      "opening": opening}
        (out / "song" / f"{spec.id}.json").write_text(json.dumps(words_json, separators=(",", ":")) + "\n")
        mixes = {mix: {k: v for k, v in m.items() if k not in ("frame", "env")} for mix, m in result["mixes"].items()}
        guides[spec.id] = {"guide": guide, "lyrics": f"{spec.id}.json", "duration": round(float(data["duration"]), 3),
                           "mixes": mixes}
        longest = max(longest, float(data["duration"]))

    built = {s["id"]: s for s in M.sets(genome_path)}
    chosen = list(dict.fromkeys(spec.set for spec in todo))
    keys_built = [k for k in M.KEYS if any(spec.key == k for spec in todo)]
    tempos_built = [t for t in M.TEMPOS if any(spec.tempo == t for spec in todo)]
    song = {
        "v": 2, "title": genome.title, "song": genome_path.stem, "consent": agreed, "words_release": words,
        "sets": [{k: built[s][k] for k in ("id", "name", "about")} for s in chosen],
        "keys": keys_built, "tempos": tempos_built, "mixes": list(MIXES),
        "default": {"set": chosen[0], "key": 0 if 0 in keys_built else keys_built[0],
                    "tempo": 100 if 100 in tempos_built else tempos_built[0], "mix": MIXES[0]},
        "guides": guides,
        "max_seconds": round(longest + 60),
        "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "song" / "song.json").write_text(json.dumps(song, separators=(",", ":")) + "\n")
    # the worker's small copy of it (web/sing/src/worker.js): the same, without the loudness curves
    (out / "song" / "worker.json").write_text(json.dumps(worker_index(song), separators=(",", ":")) + "\n")
    return song


def worker_index(song: dict) -> dict:
    """What web/sing/src/worker.js needs of song.json v2: every guide's score digest, words, length and
    MP3s, the sets and the releases' digests, so a cold start reads it well within the free plan's 10 ms
    of work a request."""
    return {"song": song["song"], "consent": song["consent"], "words_release": song.get("words_release"),
            "sets": [s["id"] for s in song.get("sets", [])], "max_seconds": song.get("max_seconds"),
            "guides": {spec: {"guide": g["guide"], "lyrics": g["lyrics"], "duration": g["duration"],
                              "mixes": {mix: m["file"] for mix, m in g["mixes"].items()}}
                       for spec, g in song["guides"].items()}}


def size(out: Path) -> int:
    """The bytes the site uploads: everything in it but what .assetsignore keeps back."""
    kept = set((out / ".assetsignore").read_text().split()) if (out / ".assetsignore").exists() else set()
    return sum(f.stat().st_size for f in out.rglob("*") if f.is_file() and f.name not in kept)


HEADERS = """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  X-Frame-Options: DENY
  Cross-Origin-Resource-Policy: same-origin
  Strict-Transport-Security: max-age=15552000
"""

FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#c2533b"/>\
<path d="M13 22.5a3.5 3 0 1 1-2-2.7V8l10-2v11.5a3.5 3 0 1 1-2-2.7V9.4l-6 1.2z" fill="#fffaf3"/></svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome", nargs="?", default=str(ROOT / "songs" / "h-now-its-by-you.json"))
    ap.add_argument("--out", default=str(WEB / "public"), help="where to build the site (default web/sing/public)")
    ap.add_argument("--sets", help="only these sets, as a,b (default every one in tools/sets/<song>.json)")
    ap.add_argument("--keys", help=f"only these keys, as 0,-2 (default {','.join(map(str, M.KEYS))})")
    ap.add_argument("--tempos", help=f"only these speeds, as 100,90 (default {','.join(map(str, M.TEMPOS))})")
    ap.add_argument("--jobs", type=int, default=JOBS, help=f"specs rendered at once (default {JOBS})")
    ap.add_argument("--phrasing", help="a phrasing file the machine's lead sings the full guides with (the words stay on the grid)")
    ap.add_argument("--rebuild", action="store_true", help="render every guide again from the current code first")
    ap.add_argument("--bitrate", default=BITRATE, help=f"the full guides' MP3 bitrate (default {BITRATE})")
    ap.add_argument("--melody-bitrate", default=MELODY_BITRATE,
                    help=f"the melody guides' (default {MELODY_BITRATE}; the full guides' if it doesn't decode in time)")
    ap.add_argument("--keep-wavs", action="store_true",
                    help="keep every spec's rendered mixes for the karaoke here (about 130 MB a spec; else let go once "
                         "encoded, and rendered again when the karaoke asks)")
    args = ap.parse_args()
    out = Path(args.out).resolve()

    def listed(text, kind=str):
        return [kind(v) for v in text.split(",") if v.strip()] if text else None

    started = time.time()

    def progress(spec, n, total):
        print(f"  {spec}  ({n} of {total}, {time.time() - started:.0f} s)", flush=True)

    song = build(Path(args.genome), out, args.rebuild, args.bitrate, listed(args.sets), listed(args.keys, int),
                 listed(args.tempos, int), args.jobs, args.phrasing and Path(args.phrasing).resolve(),
                 args.melody_bitrate, progress, args.keep_wavs)
    mp3s = [m for g in song["guides"].values() for m in g["mixes"].values()]
    print(f"{out}: {song['title']}, {len(song['guides'])} guides ({len(song['sets'])} sets x {len(song['keys'])} keys x "
          f"{len(song['tempos'])} speeds), {sum(m['bytes'] for m in mp3s) / 1e6:.0f} MB of MP3s; the whole site "
          f"{size(out) / 1e6:.0f} MB in {sum(1 for f in out.rglob('*') if f.is_file())} files; built in "
          f"{time.time() - started:.0f} s")
    print(f"releases {song['consent']} (recording) and {song['words_release']} (words); every guide score is kept in "
          f"{K.GUIDES.relative_to(ROOT)}/; publish with: cd web/sing && npx wrangler deploy")


if __name__ == "__main__":
    main()
