"""What measuring a sung take in the browser adds to the program (docs/WEB-SINGING.md, "On the device").

usage: uv run python web/studio-wasm/tools/sing_bundle.py [OUT.zip]   (default web/studio-wasm/dist/singing.zip)

singing.zip is unpacked into /app beside the program (songbird.zip), so tools/phrasing.py finds ROOT = /app as it
does in a checkout:

    tools/          the measuring code itself, unchanged: phrasing.py and what it imports
    webstudio/      the server's measuring process (worker.py) and the kit's layout (kit.py), unchanged
    sing_measure.py measure(take, request): the entry point (py/)
    world_wasm.py   pyworld's harvest and cheaptrick by WORLD in wasm (py/)
    sing_dtw.py     librosa.sequence.dtw as tools/phrasing.py calls it, in numpy (py/)

APP (here) is what the app folder carries besides: WORLD in wasm, its loader and its licence. build_render.py
adds both (its "Measuring a sung take" block)."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # web/studio-wasm
ROOT = HERE.parent.parent
TOOLS = ("phrasing.py", "speech_to_song.py", "align.py", "takes.py", "guides.py", "intelligibility.py", "karaoke_words.py",
         "wer_suite.py")  # tools/phrasing.py and everything it imports at the top
WEBSTUDIO = ("__init__.py", "kit.py", "worker.py", "guide.py")
PY = ("sing_measure.py", "world_wasm.py", "sing_dtw.py")
APP = {"world/world.wasm": HERE / "world" / "world.wasm", "world/world.mjs": HERE / "world" / "world.mjs",
       "world/LICENSE.txt": HERE / "world" / "LICENSE.txt"}
DATE = (1980, 1, 1, 0, 0, 0)


def files() -> dict[str, bytes]:
    out = {f"tools/{n}": (ROOT / "tools" / n).read_bytes() for n in TOOLS}
    out |= {f"webstudio/{n}": (ROOT / "webstudio" / n).read_bytes() for n in WEBSTUDIO}
    out |= {n: (HERE / "py" / n).read_bytes() for n in PY}
    return out


def singing_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files().items()):
            info = zipfile.ZipInfo(name, date_time=DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    return buffer.getvalue()


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "dist" / "singing.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(singing_zip())
    print(f"{out}  {out.stat().st_size / 2**10:.0f} KiB")


if __name__ == "__main__":
    main()
