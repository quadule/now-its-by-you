"""The studio's piano page and the sketch's players. "Learn it at the piano" lays the version on the page out
for the piano page (a person's key, tempo and chords in it) and serves that page from the studio, the very
files web/piano/ serves; the sketch's players are the MIDI file's parts, its channels and programs, in beats of
the song's grid. Both are made at once, and a public studio holds them to its limit on requests."""

import http.client
import json
import threading
from pathlib import Path

import pytest

from songbird import midi, public as P, studio as S

ROOT = Path(__file__).resolve().parents[1]
LEAD = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGBIRD_HOME", str(tmp_path / "home"))
    return tmp_path


def running(studio):
    server = S.serve(studio, 18796)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


@pytest.fixture
def served(home):
    studio = S.Studio(None, str(LEAD), "fictional:ada", out=home / "out")
    server, port = running(studio)
    yield studio, port
    server.shutdown()
    server.server_close()


def ask(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    head = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    c.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=head)
    r = c.getresponse()
    out = r.status, dict(r.getheaders()), r.read()
    c.close()
    return out


def post(port, studio, path, body):
    status, _, data = ask(port, "POST", path, body, {"Content-Type": "application/json", "X-Studio": studio.token})
    return status, json.loads(data)


def test_the_piano_page_is_one_source_with_web_piano():
    """web/piano/ serves the studio's own files (links to them), so the page is never forked."""
    for name in ("index.html", "piano.js", "piano.css", "sound.js"):
        web = ROOT / "web" / "piano" / name
        assert web.is_symlink() and web.resolve() == (ROOT / "songbird" / "studio" / "piano" / name).resolve()
    assert (ROOT / "web" / "piano" / "identity.css").read_bytes() == (ROOT / "songbird" / "studio" / "identity.css").read_bytes()
    html = (ROOT / "songbird" / "studio" / "piano" / "index.html").read_text()
    assert 'href="identity.css"' in html and "style=" not in html and "<script>" not in html  # the studio's policy


def test_learn_it_at_the_piano_teaches_the_version_on_the_page(served):
    studio, port = served
    first = next(p for s in studio.song({})["composition"]["sections"] for p in s["phrases"] if p["notes"])
    edits = {"tonic": 64, "tempo": 110, f"chords.{first['id']}": [["vi"], ["IV/3", "Vsus4"]] + first["chords"][2:]}
    status, made = post(port, studio, "/api/piano", {"edits": edits})
    assert status == 200 and made["url"].startswith("/piano/?score=score/") and made["url"].endswith(".json")
    status, head, page = ask(port, "GET", made["url"])
    assert status == 200 and head["Content-Type"].startswith("text/html") and b'src="piano.js"' in page
    assert "script-src 'self'" in head["Content-Security-Policy"]
    for name in ("piano.js", "sound.js", "piano.css", "identity.css"):
        assert ask(port, "GET", f"/piano/{name}")[0] == 200
    status, head, raw = ask(port, "GET", made["score"])
    score = json.loads(raw)
    assert status == 200 and head["Content-Type"] == "application/json"
    assert score["source"]["kind"] == "studio" and score["key"]["tonicMidi"] == 64 and score["tempo"] == 110
    assert {"vi", "IV/3", "Vsus4"} <= {c["roman"] for c in score["chords"]}
    assert any(c["name"].endswith("sus4") for c in score["chords"]) and any("/" in c["name"] for c in score["chords"])
    # made once: asked again, the same file
    assert post(port, studio, "/api/piano", {"edits": edits})[1] == made
    # the way in without its slash, and a score never made
    status, head, _ = ask(port, "GET", "/piano?score=score/x.json")
    assert status == 301 and head["Location"] == "/piano/?score=score/x.json"
    assert ask(port, "GET", "/piano/score/0123456789abcdef.json")[0] == 404
    assert ask(port, "GET", "/piano/../studio.py")[0] == 404


def test_the_sketchs_players_are_the_midi_files_parts_in_beats(served):
    """Every part but the singer's (the sketch's tune is its own), on the MIDI file's channels with its programs,
    each note in beats of the grid the composition view counts: the band's lute doubles the tune on its beats."""
    studio, port = served
    status, data = post(port, studio, "/api/players", {"edits": {"tonic": 64}})
    assert status == 200 and data["key"] == studio.key(studio.version({"tonic": 64}), None)
    v = studio.version({"tonic": 64})
    layout = {t["part"]: t for t in midi.layout(studio._score(v))}
    assert data["tune"]["channel"] == layout["voice"]["channel"] and data["chords"]["channel"] == midi.CHORDS_CHANNEL
    parts = {p["part"]: p for p in data["players"]}
    assert "voice" not in parts and set(parts) == set(layout) - {"voice"}
    for part, p in parts.items():
        assert (p["channel"], p["program"], p["drums"]) == (layout[part]["channel"], layout[part]["program"], layout[part]["drums"])
        assert all(0 <= key <= 127 and 1 <= vel <= 127 and length > 0 for _, length, key, vel in p["notes"])
    assert parts["drum"]["channel"] == 9 and parts["drum"]["program"] is None
    # on the view's grid: every tune note's beat, and the band's notes land within a sixteenth of the grid
    view = studio.song({"tonic": 64})["composition"]
    beats = [p["start_beat"] + n["onset"] for s in view["sections"] for p in s["phrases"] for n in p["notes"]]
    on_grid = [b for part in ("bass", "harp", "lute") for b, *_ in parts[part]["notes"]]
    assert sum(abs(b * 4 - round(b * 4)) < 0.2 for b in on_grid) > 0.9 * len(on_grid)
    assert min(beats) - 1 <= min(on_grid) and max(b for b, *_ in parts["bass"]["notes"]) <= view["duration_beats"] + 1


def test_a_public_studio_serves_them_under_its_limits(home):
    studio = S.Studio(None, str(LEAD), "none", out=home / "out", public=P.Limits(requests=4))
    server, port = running(studio)
    try:
        status, made = post(port, studio, "/api/piano", {"edits": {}})
        assert status == 200
        assert ask(port, "GET", made["url"])[0] == 200
        assert post(port, studio, "/api/players", {"edits": {}})[0] == 200
        assert ask(port, "GET", made["score"])[0] == 200
        assert ask(port, "GET", made["score"])[0] == 429  # past the address's requests a minute, like any other
    finally:
        server.shutdown()
        server.server_close()
