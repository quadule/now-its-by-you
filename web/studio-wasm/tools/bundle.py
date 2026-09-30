"""The program as the browser loads it: one zip unpacked into Pyodide's file system and put on sys.path.

usage: uv run python web/studio-wasm/tools/bundle.py [OUT.zip]   (default web/studio-wasm/dist/songbird.zip)

It holds songbird/ (its Python and the learned voice, throat.npz; not the native studio's page), cmudict
(pure Python, not in Pyodide), the numba and soundfile shims (web/studio-wasm/py), section.py and the
songs. numpy and scipy come from Pyodide's own packages."""

import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent.parent


def site_packages() -> Path:
    import cmudict

    return Path(cmudict.__file__).resolve().parent.parent


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "dist" / "songbird.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    sp = site_packages()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted((ROOT / "songbird").rglob("*")):
            rel = p.relative_to(ROOT)
            if p.is_dir() or "__pycache__" in rel.parts or rel.parts[1] == "studio":
                continue
            if p.suffix in (".py", ".npz"):
                z.write(p, rel.as_posix())
        for p in sorted((ROOT / "songs").glob("*.json")):
            z.write(p, p.relative_to(ROOT).as_posix())
        for p in sorted((HERE / "py").rglob("*.py")):
            z.write(p, p.relative_to(HERE / "py").as_posix())
        z.write(HERE / "section.py", "section.py")
        for d in ("cmudict", *[q.name for q in sp.glob("cmudict-*.dist-info")]):
            for p in sorted((sp / d).rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    z.write(p, p.relative_to(sp).as_posix())
    print(f"{out}  {out.stat().st_size / 2**20:.2f} MiB")


if __name__ == "__main__":
    main()
