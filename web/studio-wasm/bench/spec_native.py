"""A render spec made natively (web/studio-wasm/py/studio_render.py) against the public studio's own render of the
same edits: the same samples, and for the whole song the same record and packet. The native half of the browser's
identity check; tests/test_studio_browser.py does it for a section and a recording in the suite.

usage: uv run python web/studio-wasm/bench/spec_native.py SONG.json SECTION|whole ['{"tempo": 92}'] [--spec OUT.json] [--out SERVER.flac]"""

import importlib.util
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("SONGBIRD_HOME", tempfile.mkdtemp())

import soundfile as sf  # noqa: E402

from songbird import pack, public as P, studio as S  # noqa: E402
from songbird.synth import master  # noqa: E402

# by its path: web/studio-wasm/py also holds the browser's stand-ins (numba, soundfile), not for here
_spec = importlib.util.spec_from_file_location("studio_render", ROOT / "web" / "studio-wasm" / "py" / "studio_render.py")
studio_render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(studio_render)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    song, which = args[0], args[1]
    edits = json.loads(args[2]) if len(args) > 2 else {}
    st = S.Studio(None, str(ROOT / "songs" / song), "fictional:wren", out=Path(tempfile.mkdtemp()), public=P.Limits())
    st.browser = True
    index = None if which == "whole" else int(which)
    spec = st.render_spec(edits, "you", index)
    if "--spec" in sys.argv:
        Path(sys.argv[sys.argv.index("--spec") + 1]).write_text(json.dumps(spec))
    t = time.time()
    out = studio_render.run(spec["spec"], tempfile.mkdtemp(), progress=lambda f, w: None)
    print(f"from the spec  {time.time() - t:5.1f} s  {out['id']}")
    v = st.version(edits)
    job = S.Job(id="x", key=spec["key"], kind="preview", label="", work=None)
    t = time.time()
    if index is None:
        made = st._whole(job, v, spec["key"])
        print(f"the server's   {time.time() - t:5.1f} s  {made['id']}")
        server = st.cache / spec["key"] / "rendition.flac"
        a, b = pack.read_manifest(out["flac"]), pack.read_manifest(server)
        print("record the same:", a == b, sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))
    else:
        st._section(job, v, spec["key"], index)
        server = st.cache / f"{spec['key']}.flac"
        pcm, _ = sf.read(server, dtype="int16", always_2d=True)
        print(f"the server's   {time.time() - t:5.1f} s  {master.pcm_sha256(pcm)}")
    print("file the same:", Path(out["flac"]).read_bytes() == server.read_bytes())
    if "--out" in sys.argv:  # the server's file, to compare with the browser's (tools/compare.py, or pcm_diff)
        Path(sys.argv[sys.argv.index("--out") + 1]).write_bytes(server.read_bytes())


if __name__ == "__main__":
    main()
