"""Milestone 1 acceptance: a render is byte-identical across runs.

Renders run in separate processes with different hash seeds, so anything that
depends on set or dict-of-str ordering would show up here. The golden hash
pins the output on each platform that has one (tests/_golden.py); after an
intentional change to the sound, regenerate it with SONGBIRD_UPDATE_GOLDEN=1.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import soundfile as sf
from _golden import check

ROOT = Path(__file__).parent.parent
SKETCH = ROOT / "songs" / "b-coal-from-the-fire.json"


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

    check("b-refrain", a["id"])
