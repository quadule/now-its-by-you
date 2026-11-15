"""Golden ids of rendered audio, kept per platform.

A rendition's id is the SHA-256 of its samples, and the samples may differ on another platform (the README.txt
in every file says so: other math libraries, other numpy builds), so each golden names the platform it was
rendered on: golden/<name>.<platform>.sha256, e.g. h-seed.darwin-arm64.sha256. Where there is none for this
platform the test is skipped, saying so. A golden is only ever written when asked: SONGBIRD_UPDATE_GOLDEN=1,
after an intended change to the sound (or to pin it on a new platform).
"""

import os
import platform
import sys
from pathlib import Path

import pytest

DIR = Path(__file__).parent / "golden"


def here() -> str:
    """This platform as a golden's name has it: darwin-arm64, linux-x86_64, linux-arm64, win32-x86_64..."""
    machine = platform.machine().lower()
    return f"{sys.platform}-{ {'aarch64': 'arm64', 'amd64': 'x86_64'}.get(machine, machine)}"


def path(name: str) -> Path:
    return DIR / f"{name}.{here()}.sha256"


def check(name: str, got: str) -> None:
    """got is the golden <name> on this platform: written first if SONGBIRD_UPDATE_GOLDEN is set, skipped if
    there is none."""
    golden = path(name)
    if os.environ.get("SONGBIRD_UPDATE_GOLDEN"):
        golden.write_text(got + "\n")
    if not golden.exists():
        pytest.skip(f"no golden {name} for {here()} (audio may differ by platform; "
                    f"SONGBIRD_UPDATE_GOLDEN=1 writes {golden.name})")
    assert got == golden.read_text().strip()


MAC = "darwin-arm64"  # where the tables written into the tests themselves were made


def pinned(table: str, key, got: str, mac: dict | None) -> None:
    """got is the golden for `key` in a table of them: on the artist's Mac, the table `mac` the test writes out (made
    there, against the tree before an optimization); on any other platform (and on the Mac too, with no `mac`),
    golden/<table>.<platform>.json, pinned there when SONGBIRD_UPDATE_GOLDEN is set (each key written as it is
    made) and skipped where it has none."""
    import json

    if here() == MAC and mac is not None:
        assert got == mac[key]
        return
    golden = DIR / f"{table}.{here()}.json"
    name = key if isinstance(key, str) else " ".join(str(k) for k in (key if isinstance(key, tuple) else (key,)))
    held = json.loads(golden.read_text()) if golden.exists() else {}
    if os.environ.get("SONGBIRD_UPDATE_GOLDEN"):
        held[name] = got
        golden.write_text(json.dumps(held, indent=1, sort_keys=True) + "\n")
    if name not in held:
        pytest.skip(f"no golden {table} {name!r} for {here()} (samples may differ by platform; "
                    f"SONGBIRD_UPDATE_GOLDEN=1 writes {golden.name})")
    assert got == held[name]
