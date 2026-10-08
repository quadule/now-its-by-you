"""Build the page singers use anywhere, for one song: web/sing/public/ (dev-only).

    uv run python tools/sing_site.py                                          # H, every spec, into web/sing/public
    uv run python tools/sing_site.py --sets a --keys 0,-2 --tempos 100        # only these specs
    uv run python tools/sing_site.py songs/h-now-its-by-you.json --rebuild    # render every guide again first
    cd web/sing && npx wrangler deploy                                        # then publish it (docs/SING-ONLINE.md)

What it writes, all served by web/sing/src/worker.js:

    index.html, sing.css, sing.js...  the pages (web/sing/page/), with the releases in them: for recording
                                      (web/sing/consent.md) and for words people send (words-release.md);
                                      and the seed page's cover.jpg and seed.js
    seed/now-its-by-you.flac          the seed page's file: the current edition's (the newest in web/sing/editions.json
                                      whose render is here: seed_source()), with the song's cover embedded
                                      (pack.with_cover: the same audio, packet and id), and seed/words.json its words
                                      as it sang them, timed (seed_words()), shown as it plays
    seed/now-its-by-you-<date>.flac   every edition's file, as /history (history.html) offers them, newest first
    karaoke.js, recorder.js           the timing core they share with the karaoke here (tools/karaoke.js)
    song/song.json                    what's on offer (v2): the sets, keys and speeds, and for every spec
                                      its guide score's digest, its words' file, and each mix's MP3 and
                                      its length; the releases' digests. Small, as a phone reads it first.
                                      And each spec's earlier guides that place a take exactly as this one
                                      does ("was", earlier()): the worker takes a take sung to one of them
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
measured against exactly what their singers heard, whatever the song does next,
and a build that changes the words or the voice but not the timing never turns
away a take from a page loaded before it was published ("was");
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
SLOWER = 90  # the speed a singer starts at, a little slower than written: easier to learn (the artist's choice)
BITRATE = "96k"
MELODY_BITRATE = "64k"  # the whistle and the pulse carry at 64 as well as at 96, in two thirds the bytes
JOBS = 4  # specs rendered at once: a render takes one core and up to 3 GB (a 4-minute spec)
FRAME = 0.001  # seconds per step of a guide's opening loudness
OPENING = 2.5  # seconds of it kept: the song's first sounds are at 0.6 s
MARK = ".songbird-site"  # in an output directory this tool may clear
EARLIER = 24  # earlier guides a spec keeps taking takes for (earlier()): a day of builds, and more


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


PREVIEW_BITRATE = "256k"  # the song as it stands, in stereo: about 4.8 MB for two and a half minutes (128k fluttered on held vowels turned up)


def preview_mp3(flac: Path, mp3: Path) -> dict:
    """The song as it stands, encoded for the page, and what song.json says of it: the file, its size and
    digest (the page busts caches with it), how long it is, when it was rendered and by how many singers'
    takes (from the packet's record, when the render carries one; tools/everyone.py --render does)."""
    if not flac.exists():
        raise SystemExit(f"{flac} doesn't exist: render it first (tools/everyone.py --render {flac})")
    mp3.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-y", "-i", str(flac), "-vn", "-ac", "2", "-codec:a", "libmp3lame", "-b:a", PREVIEW_BITRATE, str(mp3))
    data = mp3.read_bytes()
    out = {"file": mp3.name, "bytes": len(data), "digest": hashlib.sha256(data).hexdigest()[:12],
           "seconds": round(len(decode(mp3, 44100)) / 44100, 1)}
    try:
        from songbird import pack

        record = pack.read_record(flac)
    except Exception:  # noqa: BLE001  (a plain FLAC, or a packet from another version: the preview still plays)
        record = {}
    if record:
        if record.get("rendered_at"):
            out["made"] = record["rendered_at"]
        out["id"] = str(record.get("id", ""))[:12]
        detail = str((record.get("phrasing") or {}).get("source_detail") or "")
        m = re.match(r"(\d+) sung takes by (\d+) singers", detail)
        if m:
            out["takes"], out["singers"] = int(m[1]), int(m[2])
    return out


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
          progress=None, keep_wavs: bool = False, preview: Path | None = None) -> dict:
    """The site for one song in out (built beside it, then put in its place whole), and its song.json.
    sets, keys, tempos: build only these (default all). jobs: specs rendered at once, each in a
    process of its own. phrasing:
    a phrasing file the machine's lead sings the full guides with. progress, if given, is told
    each spec as it's done. keep_wavs: keep each spec's rendered mixes for the karaoke here
    (render()). preview: a render of the song as it stands (tools/everyone.py --render), put on
    the page as an MP3 for singers to hear before they sing (song.json "preview")."""
    import karaoke  # tools/karaoke.py, for the words as they come

    from songbird import genome as G

    genome_path = Path(genome_path).resolve()
    genome = G.load(genome_path)
    todo = specs(genome_path, sets, keys, tempos)
    final = Path(out)
    if final.exists() and any(final.iterdir()) and not (final / MARK).exists():
        raise SystemExit(f"{final} isn't empty and wasn't built here: choose another --out")
    out = aside(final)  # built beside it, and put in its place whole at the end (publish())
    clear(out)
    (out / "song").mkdir()

    texts = pages(out)
    agreed, words = digest(texts["consent"]), digest(texts["words-release"])
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

    guides, placed, longest = {}, {}, 0.0
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
        placed[spec.id] = placement(words_json)
        longest = max(longest, float(data["duration"]))
    was = earlier(genome_path.stem, genome.title, {s: (g["guide"], placed[s]) for s, g in guides.items()})
    for s, g in guides.items():
        g["was"] = was[s]

    built = {s["id"]: s for s in M.sets(genome_path)}
    chosen = list(dict.fromkeys(spec.set for spec in todo))
    keys_built = [k for k in M.KEYS if any(spec.key == k for spec in todo)]
    tempos_built = [t for t in M.TEMPOS if any(spec.tempo == t for spec in todo)]
    song = {
        "v": 2, "title": genome.title, "song": genome_path.stem, "consent": agreed, "words_release": words,
        "sets": [{k: built[s][k] for k in ("id", "name", "about")} for s in chosen],
        "keys": keys_built, "tempos": tempos_built, "mixes": list(MIXES),
        "default": {"set": chosen[0], "key": 0 if 0 in keys_built else keys_built[0],
                    "tempo": SLOWER if SLOWER in tempos_built else 100 if 100 in tempos_built else tempos_built[0],
                    "mix": MIXES[0]},
        "guides": guides,
        "max_seconds": round(longest + 60),
        "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    if preview is None and seed_source() is not None:  # the page's preview is the seed page's file unless told otherwise
        preview = seed_source()
        print(f"preview: {preview.relative_to(ROOT) if preview.is_relative_to(ROOT) else preview} (the seed page's file)")
    if preview is not None:
        song["preview"] = preview_mp3(Path(preview), out / "song" / "preview.mp3")
    (out / "song" / "song.json").write_text(json.dumps(song, separators=(",", ":")) + "\n")
    # the worker's small copy of it (web/sing/src/worker.js): the same, without the loudness curves
    (out / "song" / "worker.json").write_text(json.dumps(worker_index(song), separators=(",", ":")) + "\n")
    publish(out, final)
    return song


def pages(out: Path) -> dict[str, str]:
    """Everything in the site but song/: the pages (web/sing/page/) with the releases in them, the seed page with
    the song's editions (seed_page), each page asking for its scripts and styles by digest, and the small files.
    The releases' texts, as the page shows them."""
    texts = {name: consent_html((WEB / f"{name}.md").read_text()) for name in ("consent", "words-release")
             if (WEB / f"{name}.md").exists()}
    if "words-release" not in texts:
        raise SystemExit("web/sing/words-release.md is missing: the page asks people to agree to it before sending words")
    fill = {"{{CONSENT_DIGEST}}": digest(texts["consent"]), "{{CONSENT}}": texts["consent"],
            "{{WORDS_DIGEST}}": digest(texts["words-release"]), "{{WORDS_RELEASE}}": texts["words-release"]}
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
    seed_page(out)
    versioned(out)
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (out / "favicon.svg").write_text(FAVICON)
    (out / "_headers").write_text(HEADERS)
    return texts


def aside(out: Path) -> Path:
    """Where a site is built before it takes out's place: beside it, where wrangler never looks."""
    return out.with_name(out.name + ".next")


def publish(built: Path, out: Path) -> None:
    """A finished site into out, whole. Until then out holds the site built before, so a deploy while a
    build runs publishes that, never part of this one (on 2026-09-26 a deploy caught a build 70 specs
    in, before its song.json was written, and the site was down until it was rolled back)."""
    old = out.with_name(out.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if out.exists():
        out.rename(old)
    built.rename(out)
    shutil.rmtree(old, ignore_errors=True)


def placement(lyrics: dict) -> list:
    """Where a guide puts a take, as the worker checks it (web/sing/src/lib.js checkTake): the song's
    length, and each section's place, name and window."""
    return [round(float(lyrics["duration"]), 3),
            [[x["index"], x["name"], bool(x["sung"]), [round(float(t), 3) for t in x["window"]] if x.get("window") else None]
             for x in lyrics["sections"]]]


def earlier(song: str, title: str, now: dict[str, tuple[str, list]]) -> dict[str, list[str]]:
    """For each spec (its guide's digest and placement() now), the digests of its earlier guides that
    place a take exactly where this one does, newest first, at most EARLIER: the words or the voice
    changed, not the timing. Every guide ever built is kept in recordings/guides/ (build() keeps it),
    so a take sung to one of them, from a page loaded before this build was published, is measured
    against what its singer heard, and lies on this guide's timeline for their version: the worker
    takes it rather than asking them to reload and sing it again."""
    import karaoke  # tools/karaoke.py

    found: dict[str, list[str]] = {spec: [] for spec in now}
    for f in sorted(K.GUIDES.glob(f"{song}.*.score.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        named = re.fullmatch(re.escape(song) + r"\.([0-9a-f]{12})\.score\.json", f.name)
        if not named:
            continue
        data = json.loads(f.read_text())
        spec = data["spec"].get("id") if isinstance(data.get("spec"), dict) else None
        if spec not in now or named[1] == now[spec][0] or len(found[spec]) >= EARLIER:
            continue
        try:
            same = placement(karaoke.lyrics(data, title, data["tempo"])) == now[spec][1]
        except (KeyError, TypeError, ValueError):  # a score from before sections had windows
            same = False
        if same:
            found[spec].append(named[1])
    return found


SEED_FILE = "now-its-by-you.flac"  # the seed page's file name (web/sing/src/worker.js SEED_FILE serves exactly this)
EDITIONS = WEB / "editions.json"  # the song's editions: the seed page offers the newest, /history every one
FIELDS = ("id", "title", "date", "render", "audio", "commit", "note")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def us_date(day: dt.date) -> str:
    """A date as people here read it: September 28, 2026 (whatever the machine's locale)."""
    return f"{MONTHS[day.month - 1]} {day.day}, {day.year}"


def editions(path: Path | None = None) -> list[dict]:
    """The song's editions (web/sing/editions.json), newest first, each as written with its day (a date), its
    render found ("found": None if this checkout hasn't it) and the name it's served under in seed/
    (now-its-by-you-<date>.flac, its date making it its own). A manifest that's wrong stops the build: a field
    missing or malformed, an id or a date twice."""
    path = Path(path or EDITIONS)
    listed = json.loads(path.read_text()).get("editions") or []
    if not listed:
        raise SystemExit(f"{path} lists no editions: the seed page offers the newest")
    out, ids, dates = [], set(), set()
    for n, e in enumerate(listed, 1):
        missing = [k for k in FIELDS if not isinstance(e.get(k), str) or not e[k].strip()]
        if missing:
            raise SystemExit(f"{path}: edition {n} has no {', '.join(missing)}")
        try:
            day = dt.date.fromisoformat(e["date"])
        except ValueError:
            raise SystemExit(f"{path}: edition {n}'s date {e['date']!r} isn't YYYY-MM-DD") from None
        wrong = [k for k, pattern in (("id", r"[A-Za-z0-9-]+"), ("audio", r"[0-9a-f]{12,64}"), ("commit", r"[0-9a-f]{7,40}"))
                 if not re.fullmatch(pattern, e[k])]
        if wrong:
            raise SystemExit(f"{path}: edition {n}'s {', '.join(wrong)} isn't one (id: letters, digits and -; audio: "
                             "the start of the render's id, 12 or more hex digits; commit: a commit's hash)")
        if e["id"] in ids or day in dates:
            raise SystemExit(f"{path}: edition {n}'s id or date is another's too: each is its own")
        ids.add(e["id"])
        dates.add(day)
        render = Path(e["render"]) if Path(e["render"]).is_absolute() else ROOT / e["render"]
        out.append({**e, "day": day, "found": render if render.is_file() else None,
                    "file": f"now-its-by-you-{day.isoformat()}.flac"})
    return sorted(out, key=lambda e: e["day"], reverse=True)


def seed_source(path: Path | None = None) -> Path | None:
    """The render the seed page offers, and the singing page's preview unless --preview says otherwise: the
    current edition's, the newest whose render this checkout has (editions()); None without any."""
    found = [e["found"] for e in editions(path) if e["found"]]
    return found[0] if found else None


def seed_page(out: Path, path: Path | None = None) -> None:
    """The public seed page (/seed, and the root of now.itsby.you) and its history (/history): every edition's
    file in public/seed/ (its own name), the current one's (the newest this checkout has) as the seed page's file
    too, with its words as sung, timed (seed_words), for the page to show as it plays; and history.html, every
    edition newest first. An edition whose render isn't here is left out, said; without any, the pages still
    build and say so (no file, no words)."""
    from songbird import pack as P

    (out / "seed").mkdir(exist_ok=True)
    offered = []
    for e in editions(path):
        if e["found"] is None:
            print(f"seed page: edition {e['id']} ({e['render']}) isn't in this checkout; it's left out", file=sys.stderr)
            continue
        try:  # its packet's record, checked against its own audio
            made = str((P.read_record(e["found"]) or {}).get("id") or "")
        except ValueError:
            made = ""
        if not made.startswith(e["audio"]):
            raise SystemExit(f"edition {e['id']}: {e['render']} is audio {made[:12] or '(no record)'}, not {e['audio']}: "
                             "the wrong file, or the wrong id in web/sing/editions.json")
        served = out / "seed" / e["file"]
        try:  # the song's cover as its front cover, if the render hasn't it: the same audio, packet and id
            P.with_cover(e["found"], served)
        except ValueError as err:
            print(f"seed page: edition {e['id']} is offered without the cover ({err})", file=sys.stderr)
            shutil.copyfile(e["found"], served)
        offered.append({**e, "bytes": served.stat().st_size})
    fill = {"{{SEED_FILE}}": SEED_FILE, "{{SEED_MB}}": "0", "{{SEED_V}}": "", "{{SEED_WORDS}}": "", "{{EDITION}}": ""}
    if not offered:
        print("seed page: no edition's render to offer (web/sing/editions.json); the page is built without a file",
              file=sys.stderr)
    else:
        now = offered[0]
        shutil.copyfile(out / "seed" / now["file"], out / "seed" / SEED_FILE)
        fill["{{SEED_MB}}"] = f"{now['bytes'] / 2**20:.0f}"
        fill["{{SEED_V}}"] = now["audio"]  # a new edition's file under the same name, never an old one's from a cache
        fill["{{EDITION}}"] = (f'{html.escape(now["title"])}, <time datetime="{now["date"]}">{us_date(now["day"])}</time>'
                               ' · <a href="/history">History</a>')
        print(f"seed page: edition {now['id']}, {now['render']} -> seed/{SEED_FILE} ({fill['{{SEED_MB}}']} MB); "
              f"{len(offered)} in its history")
        timed = seed_words(now["found"])
        if timed is None:
            print("seed page: the file's words can't be timed (not a packed render, or its score doesn't come out as "
                  "it sang); the page plays it without them", file=sys.stderr)
        else:
            text = json.dumps(timed, separators=(",", ":")) + "\n"
            (out / "seed" / SEED_WORDS).write_text(text)
            fill["{{SEED_WORDS}}"] = f"/seed/{SEED_WORDS}?v={digest(text)}"  # a new render's words, never an old one's
    page = (out / "seed.html").read_text()
    for mark, value in fill.items():
        page = page.replace(mark, value)
    (out / "seed.html").write_text(page)
    if (out / "history.html").exists():
        (out / "history.html").write_text((out / "history.html").read_text().replace("{{EDITIONS}}", history(offered)))


def history(offered: list[dict]) -> str:
    """The history page's editions, newest first: each one's title, date and note, a player and its file."""
    items = []
    for e in offered:
        src, anchor = f"/seed/{e['file']}", f"edition-{e['id']}"
        items.append(f"""<article class="card edition" id="{anchor}" aria-labelledby="{anchor}-title">
    <h2 id="{anchor}-title">{html.escape(e["title"])}</h2>
    <p class="when"><time datetime="{e["date"]}">{us_date(e["day"])}</time></p>
    <p>{html.escape(e["note"])}</p>
    <audio controls preload="none" src="{src}"></audio>
    <p class="hint"><a href="{src}" download>{e["file"]}</a> ({e["bytes"] / 2**20:.0f} MB, FLAC)</p>
  </article>""")
    return "\n  ".join(items) or "<p>Nothing yet.</p>"


SEED_WORDS = "words.json"  # the seed file's words, timed (web/sing/src/worker.js SEED_FILES serves it)


def seed_words(flac: Path) -> dict | None:
    """A packed render's words as it sang them, line by line, each syllable's start and end (seconds):
    {"duration", "lines": [[start, end, [[text, start, end, word_end], ...]], ...]}. Its score is laid again
    from the record and the genome it carries, as `songbird render --replay` lays it (realize, then
    variation.lay: no audio), and trusted only if its words come out exactly as the packet's lyrics.txt;
    else None. The times match the audio: the master adds nothing in front."""
    import tempfile
    from dataclasses import replace

    import karaoke  # tools/karaoke.py
    from songbird import genome as G, pack as P, phrasing as PH, variation
    from songbird.arrange import Lyrics
    from songbird.realize import Params, realize

    record = P.read_manifest(flac)
    genome_json, sung = P.read_member(flac, "genome.json"), P.read_member(flac, "lyrics.txt")
    if not record or not genome_json or not sung:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "genome.json").write_text(genome_json)
        genome = G.load(Path(tmp) / "genome.json")
    params = Params.from_dict(record["params"])
    params = replace(params, singer=record.get("singer") or params.singer, mix=record.get("mix") or params.mix)
    lyrics = Lyrics.from_dict(record["lyrics"]) if record.get("lyrics") else None
    lead, choir = PH.inherited(genome.source, record)
    score = variation.lay(realize(genome, params, phrasing=PH.from_json(lead) if lead else None,
                                  choir=[PH.from_json(d) for d in choir], lyrics=lyrics), params).to_dict()
    if P.words_as_sung(score, genome.title) != sung:
        return None
    lines = karaoke.lyrics(score, genome.title, params.tempo)["lines"]
    return {"duration": round(float(record.get("duration") or score["duration"]), 3),
            "lines": [[round(line["start"], 3), round(line["end"], 3),
                       [[s["text"], round(s["start"], 3), round(s["end"], 3), int(s["word_end"])] for s in line["syllables"]]]
                      for line in lines]}


def versioned(out: Path) -> None:
    """Every page asks for its scripts and styles by the digest of what they are now (?v=...), so neither a
    browser nor the domain's cache can hand a phone a page of one build with a script of another (sing.js
    imports karaoke.js by name: a stale one breaks the page). The files loaded first, then what loads them."""
    def stamp(name: str) -> str:
        return digest((out / name).read_text())

    def swap(name: str, old: str, new: str) -> None:
        f = out / name
        text = f.read_text()
        if old not in text:
            raise SystemExit(f"{name} no longer loads {old}: tools/sing_site.py's versioned() needs telling")
        f.write_text(text.replace(old, new))

    swap("sing.js", 'from "./karaoke.js"', f'from "./karaoke.js?v={stamp("karaoke.js")}"')
    swap("sing.js", 'addModule("/recorder.js")', f'addModule("/recorder.js?v={stamp("recorder.js")}")')
    for page in ("index.html", "seed.html", "history.html", "yours.html"):  # identity.css: the tokens and shared pieces, first
        swap(page, 'href="/identity.css"', f'href="/identity.css?v={stamp("identity.css")}"')
    for page in ("index.html", "seed.html", "history.html"):
        swap(page, 'href="/sing.css"', f'href="/sing.css?v={stamp("sing.css")}"')
    swap("seed.html", 'src="/seed.js"', f'src="/seed.js?v={stamp("seed.js")}"')
    swap("index.html", 'src="/sing.js"', f'src="/sing.js?v={stamp("sing.js")}"')
    swap("yours.html", 'href="/yours.css"', f'href="/yours.css?v={stamp("yours.css")}"')
    swap("yours.html", 'src="/yours.js"', f'src="/yours.js?v={stamp("yours.js")}"')


def worker_index(song: dict) -> dict:
    """What web/sing/src/worker.js needs of song.json v2: every guide's score digest, words, length and
    MP3s, the sets and the releases' digests, so a cold start reads it well within the free plan's 10 ms
    of work a request."""
    return {"song": song["song"], "consent": song["consent"], "words_release": song.get("words_release"),
            "sets": [s["id"] for s in song.get("sets", [])], "max_seconds": song.get("max_seconds"),
            **({"preview": {"file": song["preview"]["file"]}} if song.get("preview") else {}),
            "guides": {spec: {"guide": g["guide"], "lyrics": g["lyrics"], "duration": g["duration"],
                              "mixes": {mix: m["file"] for mix, m in g["mixes"].items()}, "was": g.get("was", [])}
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
    ap.add_argument("--preview", metavar="FLAC", help="a render of the song as it stands (tools/everyone.py --render), "
                                                     "for singers to hear on the page before they sing")
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
                 args.melody_bitrate, progress, args.keep_wavs, args.preview and Path(args.preview).resolve())
    mp3s = [m for g in song["guides"].values() for m in g["mixes"].values()]
    print(f"{out}: {song['title']}, {len(song['guides'])} guides ({len(song['sets'])} sets x {len(song['keys'])} keys x "
          f"{len(song['tempos'])} speeds), {sum(m['bytes'] for m in mp3s) / 1e6:.0f} MB of MP3s; the whole site "
          f"{size(out) / 1e6:.0f} MB in {sum(1 for f in out.rglob('*') if f.is_file())} files; built in "
          f"{time.time() - started:.0f} s")
    print(f"releases {song['consent']} (recording) and {song['words_release']} (words); every guide score is kept in "
          f"{K.GUIDES.relative_to(ROOT)}/; publish with: cd web/sing && npx wrangler deploy")


if __name__ == "__main__":
    main()
