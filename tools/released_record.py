"""The released version's record, for the web studio to open on: webstudio/released-record.json.

    uv run python tools/released_record.py RELEASE.flac      # the newest edition's file -> webstudio/released-record.json

The web studio starts on the published version as it was released (its words and settings, nothing chosen: the
machine "published", explain.Context.published), answered at once from the build's first answers, and offers this
browser's new version of it (docs/WEB-STUDIO.md, "The published version first"). Both need the release's record:
the packet's own manifest.json, kept here byte for byte. The file given must be the newest edition in
web/sing/editions.json (its SHA-256, or a render whose record names the edition's audio id), so the studio opens on
what the home page offers and nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "webstudio" / "released-record.json"
EDITIONS = ROOT / "web" / "sing" / "editions.json"


def newest() -> dict:
    """The newest edition (editions.json lists them newest first, as the home page offers them)."""
    return json.loads(EDITIONS.read_text())["editions"][0]


def record_of(flac: Path, edition: dict) -> bytes:
    """The packet's manifest.json, as released: refused unless the file is the edition's."""
    data = flac.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    try:
        with zipfile.ZipFile(flac) as z:
            raw = z.read("manifest.json")
    except (zipfile.BadZipFile, KeyError):
        raise SystemExit(f"{flac} carries no packet: a released file is one") from None
    record = json.loads(raw)
    if digest != edition["file"]["sha256"] and record.get("id") != edition["audio"]:
        raise SystemExit(f"{flac} isn't the newest edition ({edition['title']}, {edition['audio'][:12]}…)")
    return raw


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("flac", type=Path, help="the newest edition's released file (a packet)")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    raw = record_of(args.flac, newest())
    args.out.write_bytes(raw)
    print(f"{args.out}: {json.loads(raw)['id'][:12]}…, {len(raw)} bytes", file=sys.stderr)


if __name__ == "__main__":
    main()
