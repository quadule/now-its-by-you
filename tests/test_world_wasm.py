"""WORLD in wasm (web/studio-wasm/world/world.wasm, the browser's pyworld: docs/WEB-SINGING.md, "On the device")
keeps step with its sources and with native pyworld. Without a toolchain: the wasm is the build of the sources
recorded beside it (world/sources.json), as tests/test_browser_kernels.py holds the C kernels. With node: on a
made-up song (three sung notes with vibrato and a slide, breath noise, silence), Harvest's f0 is native pyworld's
to the last few bits and voiced on exactly the same frames, CheapTrick's spectrogram and the loudness and activity
tools/phrasing.py reads from it agree to within 1e-9 dB, CheapTrick made a chunk of frames at a time is bit for
bit the same as made at once, and the allocator holds up on its own. And the measuring code still calls only
what the browser has: pyworld's harvest and cheaptrick, librosa's dtw as tools/phrasing.py calls it."""

import importlib.util
import inspect
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
WASM = ROOT / "web" / "studio-wasm"
SR = 44100


def world_sources():
    spec = importlib.util.spec_from_file_location("world_sources", WASM / "tools" / "world_sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_wasm_is_the_build_of_its_sources():
    w = world_sources()
    problems = w.stale()
    assert not problems, "web/studio-wasm/world is stale:\n  " + "\n  ".join(problems) + "\n" + w.REBUILD


def test_the_measuring_calls_only_what_the_browser_has():
    sys.path.insert(0, str(ROOT / "tools"))
    import phrasing as T  # noqa: E402
    import speech_to_song as S  # noqa: E402

    analyze = inspect.getsource(T.analyze_take)
    called = {w.split("(")[0] for w in analyze.replace("S.pyworld.", " pyworld.").split() if w.startswith("pyworld.")}
    assert called == {"pyworld.harvest", "pyworld.cheaptrick"}, called
    assert "f0_floor=60.0, f0_ceil=900.0, frame_period=S.FRAME * 1000" in analyze and S.SR == SR and S.FRAME == 0.005
    assert "S.pyworld.cheaptrick(x, f0, t, S.SR)" in analyze  # its defaults: q1 -0.15, floor 71, FFT 2048
    align = inspect.getsource(T.align_by_pitch)
    assert ("librosa.sequence.dtw(C=cost, subseq=True, step_sizes_sigma=steps,\n"
            "                                   weights_add=np.zeros(3), weights_mul=np.ones(3))") in align
    assert "steps = np.array([[1, 1], [1, 2], [2, 1]])" in align


def song() -> np.ndarray:
    """Three sung notes (a slide into the second, vibrato on the third), breath noise between, silence around."""
    rng = np.random.default_rng(3)
    t = np.arange(int(6.0 * SR)) / SR
    hz = np.zeros_like(t)
    for a, b, f in ((0.5, 1.7, 196.0), (1.9, 3.4, 247.0), (3.6, 5.4, 220.0)):
        on = (t >= a) & (t < b)
        hz[on] = f
    hz[(t >= 1.9) & (t < 2.05)] *= 2 ** (np.linspace(-1.5, 0, int(0.15 * SR) + 1)[: int(np.sum((t >= 1.9) & (t < 2.05)))] / 12)
    third = (t >= 3.6) & (t < 5.4)
    hz[third] *= 2 ** (0.4 * np.sin(2 * np.pi * 5.5 * t[third]) / 12)
    phase = 2 * np.pi * np.cumsum(hz) / SR
    voice = sum(np.sin(k * phase) / k**1.3 for k in range(1, 18)) * (hz > 0)
    envelope = np.convolve((hz > 0).astype(float), np.hanning(2205) / np.sum(np.hanning(2205)), mode="same")
    return np.ascontiguousarray(0.2 * voice * envelope + 0.003 * rng.standard_normal(len(t)) * (t > 0.3) * (t < 5.7))


@pytest.mark.skipif(shutil.which("node") is None, reason="node runs the wasm")
def test_world_in_wasm_is_native_pyworld_on_a_sung_signal(tmp_path):
    pyworld = pytest.importorskip("pyworld")
    assert pyworld.__version__ == "0.3.5"  # world/src is its WORLD: another pyworld means taking its sources again
    sys.path.insert(0, str(ROOT / "tools"))
    import speech_to_song as S  # noqa: E402

    x = song()
    x.astype("<f8").tofile(tmp_path / "x.f64")
    ran = subprocess.run(["node", str(ROOT / "tests" / "_world_wasm.mjs"), str(tmp_path / "x.f64"), str(tmp_path)],
                         capture_output=True, text=True, timeout=300)
    assert ran.returncode == 0, ran.stderr[-2000:]
    said = json.loads(ran.stdout.strip().splitlines()[-1])
    assert said["selftest"] == [0, 0, 0]

    f0, t = pyworld.harvest(x, SR, f0_floor=60.0, f0_ceil=900.0, frame_period=5.0)
    sp = pyworld.cheaptrick(x, f0, t, SR)
    w_f0 = np.fromfile(tmp_path / "f0.f64")
    w_sp = np.fromfile(tmp_path / "sp.f64").reshape(sp.shape)
    assert np.array_equal(np.fromfile(tmp_path / "sp_whole.f64"), w_sp.reshape(-1))  # chunked: the same bits

    voiced = f0 > 0
    assert voiced.sum() > 600 and np.array_equal(voiced, w_f0 > 0)
    assert np.max(np.abs(w_f0[voiced] - f0[voiced]) / f0[voiced]) < 1e-12
    assert np.max(np.abs(w_sp - sp) / sp) < 1e-8
    band, active = S.tracks(sp)
    w_band, w_active = S.tracks(w_sp)
    assert np.max(np.abs(w_band - band)) < 1e-9 and np.array_equal(w_active, active)
