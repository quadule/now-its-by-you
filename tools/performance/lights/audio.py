"""Lays a new audio track under the show's films, without touching their pictures.

    python3 tools/performance/lights/audio.py MIX.flac          (any file ffmpeg reads: wav, flac, aiff, m4a, ...)

The films are the ones the show page plays, in renders/performance/lights/: film.mp4, film-hevc.mp4, film-4k.mp4
and film-4k-hevc.mp4 (those that are there). The mix is encoded once (AAC 320 kb/s, 48 kHz), then each film is
rewritten with its video stream copied and the new audio cut or padded with silence to the video's length. The
lanterns are cued to the film's clock, so a mix of a different length gets a warning: the song must start at the
same moment. The stage's live mix is renders/promo/capture-live-A/render.flac.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = ROOT / "renders/performance/lights"
FILMS = ["film.mp4", "film-hevc.mp4", "film-4k.mp4", "film-4k-hevc.mp4"]


def tool(name: str) -> str:
    found = shutil.which(name) or next((p for p in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}")
                                        if os.path.exists(p)), None)
    if not found:
        sys.exit(f"{name} not found")
    return found


def duration(probe: str, file: Path, stream: str) -> float:
    out = subprocess.run([probe, "-v", "error", "-select_streams", stream, "-show_entries", "stream=duration",
                          "-of", "json", str(file)], check=True, capture_output=True, text=True).stdout
    return float(json.loads(out)["streams"][0]["duration"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", type=Path)
    args = ap.parse_args()
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")
    films = [HERE / f for f in FILMS if (HERE / f).exists()]
    if not films:
        sys.exit(f"no films in {HERE}")
    length = duration(ffprobe, films[0], "v:0")
    song = duration(ffprobe, args.audio, "a:0")
    print(f"{args.audio.name}: {song:.3f} s; the films: {length:.3f} s")
    if abs(song - length) > 0.1:
        print(f"  warning: {song - length:+.3f} s from the film's length; the lanterns follow the film's clock, "
              "so the song must start where it did")
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        mix = Path(tmp) / "mix.m4a"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(args.audio), "-map", "0:a:0", "-af", "apad",
                        "-t", f"{length:.6f}", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", str(mix)], check=True)
        for film in films:
            out = Path(tmp) / film.name
            subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(film), "-i", str(mix), "-map", "0:v", "-map", "1:a",
                            "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
            os.replace(out, film)
            print(f"  {film.name}")
    digest = hashlib.sha256(args.audio.read_bytes()).hexdigest()[:12]
    (HERE / "audio.txt").write_text(f"{args.audio.resolve()}\nsha256 {digest}\n")
    print(f"done: the films carry {args.audio.name} (sha256 {digest}; noted in {HERE / 'audio.txt'})")


if __name__ == "__main__":
    main()
