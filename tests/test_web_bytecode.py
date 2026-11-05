"""The bundle's bytecode (web/studio-wasm/py/bytecode.py), natively: build() makes bytecode for every module of the
program and for what it imports from the standard library's zip and from site-packages, each archive's pycs
checked-hash (PEP 552) at the paths a worker's import reads (under PREFIX), the standard library's zip whole with
bytecode beside its imported modules; a worker started from them compiles nothing, and a source that changed (even
to the same size) is compiled again, never run stale. Each step is a process of its own, as a build and a worker are.
(tools/bytecode.mjs runs build() in Pyodide itself; tests/test_studio_quick_start.py and the device studio's tests
run the worker with what it makes.)"""

import json
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

PY = Path(__file__).resolve().parent.parent / "web" / "studio-wasm" / "py"

SETUP = textwrap.dedent("""
    import json, os, sys
    root = sys.argv[1]
    sys.path.insert(0, {py!r})
    import bytecode
    bytecode.PREFIX, bytecode.STDLIB = root + "/pycache", root + "/stdlib.zip"
    bytecode.SITE, bytecode.APP = root + "/site", root + "/app"
    bytecode.PACKAGES = {{"fakepkg": "fakepkg"}}
    sys.path[:0] = [root + "/site", root + "/stdlib.zip"]
""").format(py=str(PY))

BUILD = SETUP + "print(json.dumps(bytecode.build(root + '/out')))\n"

WORKER = SETUP + textwrap.dedent("""
    import zipfile
    for name in sys.argv[2:]:
        zipfile.ZipFile(name).extractall("/")
    bytecode.start()
    compiled = []
    import importlib._bootstrap_external as be
    was = be.SourceLoader.source_to_code
    def counting(self, data, path, *a, **k):
        if str(path).startswith(root):
            compiled.append(os.path.basename(path))
        return was(self, data, path, *a, **k)
    be.SourceLoader.source_to_code = counting
    sys.path.insert(0, root + "/app")
    import tune
    print(json.dumps({"values": tune.VALUES, "compiled": sorted(compiled)}))
""")


def run(script: str, *args: str) -> dict:
    out = subprocess.run([sys.executable, "-c", script, *map(str, args)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_the_bundles_bytecode_is_used_and_never_stale(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "site" / "fakepkg").mkdir(parents=True)
    (tmp_path / "app" / "tune.py").write_text("import fakepkg, stdmod\nVALUES = [1, fakepkg.VALUE, stdmod.VALUE]\n")
    (tmp_path / "app" / "later.py").write_text("def f():\n    import stdlate\n    return stdlate.VALUE\n")
    (tmp_path / "site" / "fakepkg" / "__init__.py").write_text("VALUE = 'a'\n")
    with zipfile.ZipFile(tmp_path / "stdlib.zip", "w") as z:
        z.writestr("stdmod.py", "VALUE = 3.5\n")
        z.writestr("stdlate.py", "VALUE = 4\n")  # imported only inside a function: found by reading the program
        z.writestr("unused.py", "VALUE = 5\n")

    made = run(BUILD, tmp_path)
    assert made == {"app.zip": 2, "fakepkg.zip": 1, "stdlib.zip": 2}
    out = tmp_path / "out"
    with zipfile.ZipFile(out / "stdlib.zip") as z:
        assert sorted(z.namelist()) == ["stdlate.py", "stdlate.pyc", "stdmod.py", "stdmod.pyc", "unused.py"]
        assert int.from_bytes(z.read("stdmod.pyc")[4:8], "little") == 0b11  # hash-based, checked against its source
    for name in ("app.zip", "fakepkg.zip"):
        with zipfile.ZipFile(out / name) as z:
            for entry in z.namelist():
                assert entry.startswith(str(tmp_path / "pycache").lstrip("/")) and entry.endswith(".pyc")
                assert int.from_bytes(z.read(entry)[4:8], "little") == 0b11
    again = tmp_path / "again"
    (tmp_path / "out").rename(again)
    assert run(BUILD, tmp_path) == made
    for name in made:  # the same bytes each build
        assert (again / name).read_bytes() == (out / name).read_bytes(), name

    # a worker: the standard library's zip in place of the one served, the pycs unpacked before it imports
    (tmp_path / "stdlib.zip").write_bytes((out / "stdlib.zip").read_bytes())
    archives = [out / "app.zip", out / "fakepkg.zip"]
    assert run(WORKER, tmp_path, *archives) == {"values": [1, "a", 3.5], "compiled": []}

    # a source changed to the same size: compiled again, not the stale bytecode
    (tmp_path / "app" / "tune.py").write_text("import fakepkg, stdmod\nVALUES = [2, fakepkg.VALUE, stdmod.VALUE]\n")
    assert run(WORKER, tmp_path, *archives) == {"values": [2, "a", 3.5], "compiled": ["tune.py"]}
