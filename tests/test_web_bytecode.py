"""What a browser worker keeps of the bytecode Python compiled (web/studio-wasm/py/bytecode.py), natively: the archives
it hands back hold checked-hash pycs (PEP 552) of what it imported, the standard library's zip gains its modules'
bytecode, a worker started from them compiles nothing it was given, and a source that changed (even to the same size,
whose time a Pyodide worker can't trust) is compiled again, never run stale. Each worker is a process of its own."""

import json
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path

PY = Path(__file__).resolve().parent.parent / "web" / "studio-wasm" / "py"

WORKER = textwrap.dedent("""
    import json, os, sys, zipfile
    root, prefix, stdlib = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path.insert(0, {py!r})
    import bytecode
    bytecode.PREFIX, bytecode.STDLIB = prefix, stdlib
    bytecode.GROUPS = {{"app": prefix + root + "/app", "site": prefix + root + "/site"}}
    for name in sys.argv[4:]:  # archives an earlier worker kept, unpacked into / as the worker does
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
    sys.path[:0] = [root + "/app", root + "/site", stdlib]
    import tune, helper, stdmod
    left = bytecode.stdlib_step(0)
    while bytecode.stdlib_step(10.0):
        pass
    out = {{"values": [tune.VALUE, helper.VALUE, stdmod.VALUE], "compiled": sorted(compiled), "new": bytecode.new(),
            "stdlib_left": left, "kept": bytecode.kept(root + "/kept")}}
    out["new_after"] = bytecode.new()
    print(json.dumps(out))
""").format(py=str(PY))


def worker(tmp: Path, *archives: str) -> dict:
    script = tmp / "worker.py"
    script.write_text(WORKER)
    run = subprocess.run([sys.executable, str(script), str(tmp), str(tmp / "pycache"), str(tmp / "stdlib.zip"),
                          *archives], capture_output=True, text=True, check=True)
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_kept_bytecode_is_used_and_never_stale(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "site").mkdir()
    (tmp_path / "app" / "tune.py").write_text("VALUE = 1\n")
    (tmp_path / "site" / "helper.py").write_text("VALUE = 'a'\n")
    with zipfile.ZipFile(tmp_path / "stdlib.zip", "w") as z:
        z.writestr("stdmod.py", "VALUE = 3.5\n")

    first = worker(tmp_path)
    assert first["values"] == [1, "a", 3.5]
    assert first["compiled"] == ["helper.py", "tune.py"]  # (zipimport compiles stdmod its own way)
    assert first["new"] and first["stdlib_left"] == 1 and not first["new_after"]
    kept = first["kept"]
    assert sorted(kept) == ["app", "site", "stdlib"]
    for group in ("app", "site"):
        with zipfile.ZipFile(kept[group]) as z:
            (name,) = z.namelist()
            pyc = z.read(name)
        assert name.endswith(".pyc") and not name.startswith("/")
        assert int.from_bytes(pyc[4:8], "little") == 0b11  # hash-based, checked against its source
    with zipfile.ZipFile(kept["stdlib"]) as z:
        assert sorted(z.namelist()) == ["stdmod.py", "stdmod.pyc"]
        assert int.from_bytes(z.read("stdmod.pyc")[4:8], "little") == 0b11

    # the next worker: started from what was kept (the standard library's zip in place of the one served)
    (tmp_path / "stdlib.zip").write_bytes(Path(kept["stdlib"]).read_bytes())
    archives = []
    for group in ("app", "site"):
        archives.append(str(tmp_path / f"{group}-kept.zip"))
        Path(archives[-1]).write_bytes(Path(kept[group]).read_bytes())
    import shutil

    shutil.rmtree(tmp_path / "pycache")
    second = worker(tmp_path, *archives)
    assert second["values"] == [1, "a", 3.5] and second["compiled"] == []
    assert second["stdlib_left"] == 0 and not second["new"] and second["kept"] == {}

    # a source changed to the same size: compiled again, and that kept
    (tmp_path / "app" / "tune.py").write_text("VALUE = 2\n")
    shutil.rmtree(tmp_path / "pycache")
    third = worker(tmp_path, *archives)
    assert third["values"] == [2, "a", 3.5] and third["compiled"] == ["tune.py"]
    assert sorted(third["kept"]) == ["app"]
