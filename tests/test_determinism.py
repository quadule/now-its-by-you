"""Milestone 1 acceptance: a render is byte-identical across runs.

Renders run in separate processes with different hash seeds, so anything that
depends on set or dict-of-str ordering would show up here. The golden hash
pins the output on this platform; after an intentional change to the sound,
regenerate it with SONGBIRD_UPDATE_GOLDEN=1.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import soundfile as sf

ROOT = Path(__file__).parent.parent
SKETCH = ROOT / "songs" / "b-coal-from-the-fire.json"
GOLDEN = Path(__file__).parent / "golden" / "b-refrain.sha256"


def render(out: Path, hash_seed: str) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    subprocess.run(
        [sys.executable, "-m", "songbird", "render", str(SKETCH), "--form", "refrain", "--out", str(out)],
        check=True, env=env, cwd=ROOT, capture_output=True,
    )
    return json.loads(out.with_suffix(".json").read_text())


def test_render_is_byte_identical(tmp_path):
    a = render(tmp_path / "a.flac", "1")
    b = render(tmp_path / "b.flac", "2")
    assert a["id"] == b["id"]
    assert (tmp_path / "a.flac").read_bytes() == (tmp_path / "b.flac").read_bytes()

    pcm, _ = sf.read(tmp_path / "a.flac", dtype="int16")
    assert pcm.shape[1] == 2

    if os.environ.get("SONGBIRD_UPDATE_GOLDEN"):
        GOLDEN.write_text(a["id"] + "\n")
    if not GOLDEN.exists():
        pytest.skip("no golden hash yet; run with SONGBIRD_UPDATE_GOLDEN=1")
    assert a["id"] == GOLDEN.read_text().strip()
