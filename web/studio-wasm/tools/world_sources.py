"""What world/world.wasm was built from (world/sources.json): each source's digest and the wasm's own, so a change
to a source that wasn't built, or a wasm that isn't the build of these sources, is caught without a toolchain
(tests/test_world_wasm.py). docs/WEB-SINGING.md, "On the device".

usage: uv run python web/studio-wasm/tools/world_sources.py [--write]
--write records the sources and the wasm as they are now (after world/build.sh); without it, says what is stale
and exits 1 if anything is."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

WORLD = Path(__file__).resolve().parent.parent / "world"
RECORD = WORLD / "sources.json"
ZIG = "0.16.0"  # the zig (pip's ziglang) world.wasm was built with: its clang and its libc's maths


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def sources() -> list[Path]:
    return [WORLD / "build.sh", WORLD / "glue.cpp", WORLD / "alloc.h", *sorted((WORLD / "src").rglob("*.cpp")),
            *sorted((WORLD / "src").rglob("*.h"))]


def current() -> dict:
    return {"zig": ZIG, "sources": {p.relative_to(WORLD).as_posix(): digest(p) for p in sources()},
            "world.wasm": digest(WORLD / "world.wasm")}


def stale() -> list[str]:
    """What differs from the record: empty when world.wasm is the build of the sources here."""
    if not RECORD.exists():
        return ["world/sources.json is missing"]
    kept, now = json.loads(RECORD.read_text()), current()
    problems = [f"world/{name} changed since world.wasm was built" for name, d in now["sources"].items()
                if kept["sources"].get(name) != d]
    problems += [f"world/{name} is gone" for name in kept["sources"] if name not in now["sources"]]
    if kept.get("world.wasm") != now["world.wasm"]:
        problems.append("world/world.wasm isn't the one recorded")
    return problems


REBUILD = ('rebuild: ZIG="uv run --with ziglang==' + ZIG + ' python -m ziglang" sh web/studio-wasm/world/build.sh, '
           "then uv run python web/studio-wasm/tools/world_sources.py --write")


def main() -> None:
    if "--write" in sys.argv[1:]:
        RECORD.write_text(json.dumps(current(), indent=1, sort_keys=True) + "\n")
        print(f"recorded {RECORD}")
        return
    problems = stale()
    for p in problems:
        print(p)
    if problems:
        print(REBUILD)
        raise SystemExit(1)
    print("world.wasm is current")


if __name__ == "__main__":
    main()
