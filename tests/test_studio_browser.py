"""The song made in the visitor's browser (`songbird studio --public --browser-render DIR`; docs/WEB-STUDIO.md, "Made
in the visitor's browser"): the studio serves a built bundle (here a small stand-in) for good under hashed folders,
only if it carries this very program, with the worker's own policy; the page's policy lets a song made in the
browser play and nothing else changes; a local studio never serves it. The render spec the page is given makes,
through web/studio-wasm/py/studio_render.py, the same section and the same recording, byte for byte, as the studio
makes itself (natively here; in Pyodide by web/studio-wasm/bench/identity.sh and in Chrome by hand)."""

import gzip
import http.client
import importlib.util
import json
import threading
from pathlib import Path

import pytest
import soundfile as sf

from songbird import pack, public as P, studio as S
from songbird.synth import master

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"
B = ROOT / "songs" / "b-coal-from-the-fire.json"
PY, APP = "py-0123456789abcdef", "app-fedcba9876543210"


def studio_render():
    spec = importlib.util.spec_from_file_location("studio_render", ROOT / "web" / "studio-wasm" / "py" / "studio_render.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("STUDIO_MEMORY", "16g")  # a public studio with room for any whole song (its budget: public.render_mb)
    return tmp_path


def fake_bundle(folder: Path, program: str) -> Path:
    """A bundle as build_render.py lays one out, with a few small files in it."""
    (folder / PY).mkdir(parents=True)
    (folder / APP / "kernels").mkdir(parents=True)
    wasm = b"\0asm" + bytes(4000)
    (folder / PY / "pyodide.asm.wasm").write_bytes(wasm)
    (folder / PY / "pyodide.asm.wasm.gz").write_bytes(gzip.compress(wasm))
    (folder / APP / "studio-worker.mjs").write_text("postMessage({kind: 'ready'});\n")
    (folder / APP / "kernels" / "rt.mjs").write_text("export const x = 1;\n")
    (folder / APP / ".hidden.json").write_text("{}")
    (folder / APP / "notes.txt").write_text("not served")
    (folder / "elsewhere.json").write_text("{}")
    (folder / "bundle.json").write_text(json.dumps({"v": 1, "pyodide": PY, "app": APP, "program_sha256": program,
                                                    "bytes": 8123, "transfer": 4567, "packages": ["numpy"]}))
    return folder


def ask(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None,
              headers={"Host": f"127.0.0.1:{port}", **(headers or {})})
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def post(port, studio, path, body):
    status, head, data = ask(port, "POST", path, body, {"Content-Type": "application/json", "X-Studio": studio.token})
    return status, json.loads(data)


@pytest.fixture
def public(home):
    studio = S.Studio(None, str(LEAD), "fictional:wren", out=home / "out", public=P.Limits())
    studio.enable_browser_render(fake_bundle(home / "bundle", studio.program_digest))
    server = S.serve(studio, 18850)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield studio, server.server_address[1]
    server.shutdown()
    server.server_close()


def test_the_bundle_is_served_for_good_under_its_hashed_folders(public):
    studio, port = public
    status, head, data = ask(port, "GET", "/render/bundle.json")
    assert status == 200 and head["Cache-Control"] == "no-cache"
    view = json.loads(data)
    assert (view["pyodide"], view["app"], view["base"], view["transfer"]) == (PY, APP, "/render/", 4567)
    assert view["program"] == studio.program_digest
    status, head, data = ask(port, "GET", f"/render/{APP}/studio-worker.mjs")
    assert status == 200 and data.startswith(b"postMessage")
    assert head["Cache-Control"] == "public, max-age=31536000, immutable"
    assert head["Content-Type"].startswith("text/javascript")
    policy = head["Content-Security-Policy"]
    assert "'wasm-unsafe-eval'" in policy and "'unsafe-eval'" not in policy and "connect-src 'self'" in policy
    assert ask(port, "GET", f"/render/{APP}/kernels/rt.mjs")[0] == 200
    # wasm as wasm (compiled as it streams in), compressed for a browser that takes it
    status, head, data = ask(port, "GET", f"/render/{PY}/pyodide.asm.wasm")
    assert status == 200 and head["Content-Type"] == "application/wasm" and data[:4] == b"\0asm"
    assert "Content-Encoding" not in head
    status, head, data = ask(port, "GET", f"/render/{PY}/pyodide.asm.wasm", headers={"Accept-Encoding": "gzip, br"})
    assert status == 200 and head["Content-Encoding"] == "gzip" and gzip.decompress(data)[:4] == b"\0asm"
    # nothing else of the folder, nor outside its two folders
    for path in (f"/render/{APP}/.hidden.json", f"/render/{APP}/notes.txt", "/render/elsewhere.json",
                 f"/render/{PY}/pyodide.asm.wasm.gz", f"/render/{APP}/../bundle.json", f"/render/{APP}/%2e%2e/bundle.json",
                 "/render/py-000000000000/pyodide.asm.wasm", f"/render/{APP}/kernels", f"/render/{APP}/"):
        assert ask(port, "GET", path)[0] == 404, path


def test_the_page_may_play_what_the_browser_made_and_is_otherwise_as_strict(public, home):
    studio, port = public
    status, head, page = ask(port, "GET", "/")
    assert status == 200 and b'id="makeWhere"' in page
    assert b'<meta name="studio-render" content="bundle">' in page  # so the page asks for the bundle
    policy = head["Content-Security-Policy"]
    assert "media-src 'self' blob:" in policy and "script-src 'self';" in policy and "eval" not in policy
    local = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out2")
    server = S.serve(local, 18851)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        port2 = server.server_address[1]
        status, head, page2 = ask(port2, "GET", "/")
        assert "media-src 'self';" in head["Content-Security-Policy"]
        assert b'name="studio-render"' not in page2  # a local studio's page doesn't ask for a bundle it hasn't got
        assert ask(port2, "GET", "/render/bundle.json")[0] == 404  # a local studio sings the song itself
        assert post(port2, local, "/api/render/spec", {"edits": {}, "section": 1})[0] == 404
    finally:
        server.shutdown()
        server.server_close()
    with pytest.raises(ValueError, match="public"):
        local.enable_browser_render(home / "bundle")


def test_a_bundle_built_from_another_program_is_refused(home):
    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits())
    with pytest.raises(ValueError, match="another program"):
        studio.enable_browser_render(fake_bundle(home / "other", "0" * 64))
    with pytest.raises(ValueError, match="bundle.json"):
        studio.enable_browser_render(home / "nothing-here")


def test_a_section_from_its_spec_is_the_studios_own_byte_for_byte(public, home):
    studio, port = public
    edits = {"tempo": 90, "roll": 2}
    status, answer = post(port, studio, "/api/render/spec", {"edits": edits, "who": "you", "section": 1})
    assert status == 200 and answer["kind"] == "section" and isinstance(answer["spec"], str)
    spec = json.loads(answer["spec"])
    assert spec["program"] == studio.program_digest and spec["section"] == 1 and spec["key"] == answer["key"]
    assert spec["genome"] == LEAD.read_text() and "voice" not in spec  # a section needs no machine or day
    made = studio_render().run(answer["spec"], home / "browser", program=studio.program_digest)
    job = S.Job(id="x", key=answer["key"], kind="preview", label="", work=None)
    studio._section(job, studio.version(edits), answer["key"], 1)
    theirs = studio.cache / f"{answer['key']}.flac"
    pcm, _ = sf.read(theirs, dtype="int16", always_2d=True)
    assert made["id"] == master.pcm_sha256(pcm)
    assert Path(made["flac"]).read_bytes() == theirs.read_bytes()
    # made now, the studio says so, and the page asks for it as ever (it plays at once)
    status, again = post(port, studio, "/api/render/spec", {"edits": edits, "section": 1})
    assert again == {"key": answer["key"], "label": answer["label"], "made": True}
    assert post(port, studio, "/api/render/spec", {"edits": {}, "section": 99})[0] == 400
    assert post(port, studio, "/api/render/spec", {"edits": {}, "who": "someone else"})[0] == 400


def test_a_recording_from_its_spec_is_the_studios_own_packet_byte_for_byte(home):
    studio = S.Studio(None, str(B), "fictional:ada", out=home / "out", public=P.Limits())
    edits = {"tempo": 70, "band.pattern": "pick", "form.verses": 2}
    answer = studio.render_spec(edits)
    assert answer["kind"] == "whole" and answer["name"] == {"song": "coal-from-the-fire", "day": studio.day}
    spec = json.loads(answer["spec"])
    assert spec["packet"]["requirements"] == pack.requirements() and spec["marks"]["tempo"]["value"] == 70.0
    render = studio_render()
    made = render.run(answer["spec"], home / "browser", program=studio.program_digest)
    job = S.Job(id="x", key=answer["key"], kind="record", label="", work=None)
    studio._whole(job, studio.version(edits), answer["key"])
    theirs = studio.cache / answer["key"] / "rendition.flac"
    assert made["record"] == pack.read_manifest(theirs)
    assert made["record"]["program_sha256"] == studio.program_digest and made["record"]["chosen_by_you"]
    assert Path(made["flac"]).read_bytes() == theirs.read_bytes()
    with pytest.raises(render.Refused, match="another|program"):
        render.run(answer["spec"], home / "again", program="f" * 64)
    with pytest.raises(render.Refused, match="shape"):
        render.run(json.dumps({**spec, "v": 99}), home / "again", program=studio.program_digest)


def test_a_whole_song_too_long_for_a_browsers_heap_goes_to_the_server_or_is_said_to_be_too_long(public, monkeypatch):
    """A browser's wasm heap tops out at 4 GiB: a whole song estimated past public.BROWSER_MB of it isn't given to the
    browser; the server makes it if it fits there, and if it doesn't either the page is told why, the same sentence,
    and nothing is sent anywhere. One that fits the browser but not the server: the server says "make it in your
    browser"."""
    from songbird import edits as E, genome

    monkeypatch.setenv("SONGBIRD_THREADS", "2")
    studio, port = public
    song = genome.load(LEAD)
    long = {"style.name": "chamber", "tempo": 48.4, "form.verses": 4, **{f"form.{n}": True for n in E.optional(song)}}
    status, answer = post(port, studio, "/api/render/spec", {"edits": {}})
    assert status == 200 and answer["kind"] == "whole" and "spec" in answer  # the song as the program has it: here
    status, answer = post(port, studio, "/api/render/spec", {"edits": long})
    assert status == 200 and answer["server"] and "spec" not in answer  # past a browser; a server with 16 GB makes it
    studio.public.render_mb = 2100  # the VPS's
    status, answer = post(port, studio, "/api/render/spec", {"edits": long})
    assert status == 200 and "spec" not in answer and not answer.get("server")
    assert answer["too_long"].startswith("This version is ") and "too long for this small server or a browser" in \
        answer["too_long"] and answer["too_long"].endswith("shorten it (fewer verses, a quicker tempo).")
    assert post(port, studio, "/api/render/spec", {"edits": long, "section": 2})[1]["kind"] == "section"  # a section: yes
    # a version the browser can make but this server can't: the server says so, and where to make it
    seconds, parts = studio.whole_cost(studio.version({}))
    assert S.Studio.fits_browser(seconds, parts)
    studio.public.render_mb = 600
    status, refused = post(port, studio, "/api/record", {"edits": {}})
    assert status == 422 and refused["too_long"] and "make it in your browser, or shorten it" in refused["error"]
    assert post(port, studio, "/api/render/spec", {"edits": {}})[1]["kind"] == "whole"  # and the browser is given it
