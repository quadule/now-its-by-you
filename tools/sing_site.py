"""Build the page singers use anywhere, for one song: web/sing/public/ (dev-only).

    uv run python tools/sing_site.py                                          # H, into web/sing/public
    uv run python tools/sing_site.py songs/h-now-its-by-you.json --rebuild    # render the full guide again first
    cd web/sing && npx wrangler deploy                                        # then publish it (docs/SING-ONLINE.md)

What it writes, all served by web/sing/src/worker.js:

    index.html, sing.css, sing.js    the page (web/sing/page/), with the release (web/sing/consent.md) in it
    karaoke.js, recorder.js          the timing core it shares with the karaoke here (tools/karaoke.js)
    song/song.json                   the words and notes as they come (karaoke.lyrics), the guide score's
                                     digest, the release's digest, and each guide's length and opening
                                     loudness (so the page can tell if an MP3 decoder put silence in front)
    song/melody.mp3, song/full.mp3   the guides (tools/guides.py), encoded with ffmpeg

The worker serves song/ only to an open invitation. The guide score is kept in
recordings/guides/ (tools/takes.py), so takes fetched with tools/invite.py are
measured against exactly what their singers heard, whatever the song does next.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
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
BITRATE = "128k"
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


def encode(wav: Path, mp3: Path, bitrate: str = BITRATE) -> dict:
    """The guide as an MP3, and what the page needs to know about the original."""
    import soundfile as sf

    ffmpeg("-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3))
    x, rate = sf.read(wav)
    mono = x.mean(axis=1) if x.ndim > 1 else x
    env = envelope(mono, rate)
    heard = decode(mp3, rate)
    drift = decode_offset(heard, rate, env)
    if abs(len(heard) - len(mono)) > 0.01 * rate or abs(drift) > 0.002:
        raise SystemExit(f"{mp3.name} doesn't decode in time with its guide ({len(heard) - len(mono)} samples, {drift * 1000:.1f} ms)")
    return {"file": mp3.name, "bytes": mp3.stat().st_size, "rate": rate, "samples": len(mono),
            "seconds": round(len(mono) / rate, 3), "frame": FRAME, "env": [round(float(v), 5) for v in env]}


def clear(out: Path) -> None:
    """Empty an output directory this tool made before (it leaves a mark), or refuse."""
    if out.exists() and any(out.iterdir()):
        if not (out / MARK).exists():
            raise SystemExit(f"{out} isn't empty and wasn't built here: choose another --out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARK).write_text("built by tools/sing_site.py; cleared on every build\n")
    (out / ".assetsignore").write_text(f"{MARK}\n.assetsignore\n")  # neither is published


def build(genome_path: Path, out: Path, rebuild: bool = False, bitrate: str = BITRATE) -> dict:
    import karaoke  # tools/karaoke.py, for the words as they come

    from songbird import genome as G
    from songbird.realize import choose_params

    genome_path = Path(genome_path)
    genome = G.load(genome_path)
    wavs = {mix: M.ensure(genome_path, genome, mix, rebuild=rebuild and mix == MIXES[0])[0] for mix in MIXES}
    score = M.full_paths(genome_path.stem)[1]
    guide = K.keep_guide(genome_path.stem, score)  # so takes sung to it can always be measured against it
    data = json.loads(score.read_text())

    clear(out)
    (out / "song").mkdir()
    text = consent_html((WEB / "consent.md").read_text())
    agreed = digest(text)
    page = (WEB / "page" / "index.html").read_text()
    if "{{CONSENT}}" not in page or "{{CONSENT_DIGEST}}" not in page:
        raise SystemExit("web/sing/page/index.html has lost its {{CONSENT}} or {{CONSENT_DIGEST}}")
    (out / "index.html").write_text(page.replace("{{CONSENT_DIGEST}}", agreed).replace("{{CONSENT}}", text))
    for name in ("sing.css", "sing.js"):
        shutil.copyfile(WEB / "page" / name, out / name)
    shutil.copyfile(ROOT / "tools" / "karaoke.js", out / "karaoke.js")
    shutil.copyfile(ROOT / "tools" / "karaoke-recorder.js", out / "recorder.js")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    (out / "favicon.svg").write_text(FAVICON)

    tempo = data.get("tempo") or choose_params(genome).tempo
    song = {
        **karaoke.lyrics(data, genome.title, tempo),
        "song": genome_path.stem, "guide": guide, "consent": agreed, "default": MIXES[0],
        "mixes": {mix: encode(wavs[mix], out / "song" / f"{mix}.mp3", bitrate) for mix in MIXES},
        "max_seconds": round(data["duration"] + 60),
        "built": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    (out / "song" / "song.json").write_text(json.dumps(song, separators=(",", ":")) + "\n")
    return song


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle cx="16" cy="16" r="15" fill="#c2533b"/>\
<path d="M13 22.5a3.5 3 0 1 1-2-2.7V8l10-2v11.5a3.5 3 0 1 1-2-2.7V9.4l-6 1.2z" fill="#fffaf3"/></svg>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("genome", nargs="?", default=str(ROOT / "songs" / "h-now-its-by-you.json"))
    ap.add_argument("--out", default=str(WEB / "public"), help="where to build the site (default web/sing/public)")
    ap.add_argument("--rebuild", action="store_true", help="render the full guide again from the current code first")
    ap.add_argument("--bitrate", default=BITRATE, help=f"the guides' MP3 bitrate (default {BITRATE})")
    args = ap.parse_args()
    out = Path(args.out).resolve()
    song = build(Path(args.genome), out, args.rebuild, args.bitrate)
    sizes = ", ".join(f"{m} {v['bytes'] / 1e6:.1f} MB" for m, v in song["mixes"].items())
    print(f"{out}: {song['title']}, guide score {song['guide']}, release {song['consent']}; {sizes}")
    print(f"the guide score is kept in {K.GUIDES.relative_to(ROOT)}/; publish with: cd web/sing && npx wrangler deploy")


if __name__ == "__main__":
    main()
