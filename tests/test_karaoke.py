"""The karaoke plays the guide a singer chooses and each take says which it heard (tools/karaoke.py)."""

import io
import json
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import guides as M  # noqa: E402  (tools/guides.py)
import karaoke  # noqa: E402  (tools/karaoke.py)
import phrasing as T  # noqa: E402  (tools/phrasing.py)
import takes as K  # noqa: E402  (tools/takes.py)

from songbird import genome as G  # noqa: E402

ROOT = Path(__file__).parent.parent
H = ROOT / "songs" / "h-now-its-by-you.json"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setattr(M, "GUIDES", tmp_path / "renders" / "guide")
    monkeypatch.setattr(K, "ROOT", tmp_path)
    monkeypatch.setattr(K, "RECORDINGS", tmp_path / "recordings")
    monkeypatch.setattr(K, "GUIDES", tmp_path / "recordings" / "guides")
    return tmp_path


def short(folder: Path, form=("verse",)) -> Path:
    """H's genome with a seed rendition only a section long, as a file the karaoke can reload."""
    data = json.loads(H.read_text())
    data["seed_params"]["form"] = list(form)
    path = folder / "h-short.json"
    path.write_text(json.dumps(data))
    return path


def test_the_karaoke_says_which_guide_a_take_heard(workspace, monkeypatch):
    path = short(workspace)
    monkeypatch.setattr(karaoke.Karaoke, "genome_path", path, raising=False)
    monkeypatch.setattr(karaoke.Karaoke, "genome", G.load(path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), karaoke.Karaoke)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/guide.wav?mix=melody") as r:
            digest = r.headers["X-Guide-Score"]
            assert r.headers["Content-Type"] == "audio/wav" and r.read() == M.mix_path("h-short", "melody").read_bytes()
        with urllib.request.urlopen(f"{base}/guide.wav") as r:  # asked for as before there was a choice: the full guide
            assert r.headers["X-Guide-Score"] == digest and r.read() == M.mix_path("h-short", "full").read_bytes()
        with urllib.request.urlopen(f"{base}/lyrics.json") as r:
            words = json.loads(r.read())
            assert words["guide"] == digest and words["beats"] and words["lines"]
        with urllib.request.urlopen(f"{base}/karaoke.js") as r:
            assert b"export function autoSync" in r.read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/guide.wav?mix=kazoo")
        assert e.value.code == 404

        wav = io.BytesIO()
        sf.write(wav, np.zeros(48000), 48000, format="WAV", subtype="PCM_16")

        def take(**query):
            q = "&".join(f"{k}={v}" for k, v in query.items())
            req = urllib.request.Request(f"{base}/take?{q}", data=wav.getvalue(), headers={"Content-Type": "audio/wav"})
            try:
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as err:
                return json.loads(err.read())

        kept = take(singer="Jo", mix="melody", guide=digest, shift_ms=12)
        side = json.loads((workspace / kept["path"]).with_suffix(".json").read_text())
        assert (side["mix"], side["guide"], side["shift_ms"]) == ("melody", digest, 12.0)
        assert K.guide_score("h-short", digest)  # the score it was sung to is kept beside the takes
        assert "changed" in take(singer="Jo", mix="melody", guide="0" * 12)["error"]  # sung to a guide that's gone
        assert "changed" in take(singer="Jo", mix="melody")["error"]  # or to one it doesn't name
        assert "which guide" in take(singer="Jo", guide=digest)["error"]  # a take says which mix it heard
        assert "which guide" in take(singer="Jo", mix="kazoo", guide=digest)["error"]
        # sung to an earlier render of the song whose score is still kept: kept, and pinned to it
        (K.GUIDES / "h-short.abcdefabcdef.score.json").write_text("{}")
        older = take(singer="Jo", mix="full", guide="abcdefabcdef")
        assert json.loads((workspace / older["path"]).with_suffix(".json").read_text())["guide"] == "abcdefabcdef"
    finally:
        server.shutdown()
        server.server_close()


def voice(start, dur, syllable, word=None, word_len=1, line_end=False, section="verse"):
    return {"part": "voice", "start": start, "dur": dur, "pitch": 62.0, "syllable": syllable, "word": word or syllable,
            "word_len": word_len, "line_end": line_end, "section": section}


def test_each_sung_section_has_its_first_line_and_a_window_to_record_it_alone():
    beats = [[0.5 * k, int(k % 4 == 0)] for k in range(58)]  # 4/4 at 120: a bar every 2 s
    notes = [voice(1.75, 0.25, "Oh", line_end=True, section="verse"),  # a verse right at the start
             voice(7.75, 0.25, "They"), voice(8.0, 0.5, "*num", "*num-bers*", 2), voice(8.5, 0.5, "bers*", "*num-bers*", 2),
             voice(9.0, 1.0, "wire,", line_end=True), voice(10.0, 5.9, "gone.", line_end=True),  # an eighth's pickup
             voice(20.0, 1.0, "Who", section="refrain"), voice(21.0, 6.0, "knows?", line_end=True, section="refrain"),
             voice(24.0 + 5.0, 0.5, "la", line_end=True, section="tag")]
    notes[0]["start"], notes[0]["dur"] = 0.5, 1.0
    score = {"duration": 28.5, "beats": beats, "notes": notes,
             "sections": [["verse", 0.5, 2.0], ["intro", 2.0, 8.0], ["verse", 8.0, 16.0], ["turn", 16.0, 20.0],
                          ["refrain", 20.0, 28.0], ["tag", 28.0, 28.5]]}
    found = karaoke.sections(score)
    assert [(s["index"], s["name"], s["sung"], s.get("nth")) for s in found] == [
        (0, "verse", True, 1), (1, "intro", False, None), (2, "verse", True, 2), (3, "turn", False, None),
        (4, "refrain", True, 1), (5, "tag", False, None)]  # the tag's note is past its end: not its own
    first, verse, refrain = found[0], found[2], found[4]
    assert verse["label"] == "They numbers wire," and refrain["label"] == "Who knows?"
    assert first["window"] == [0.0, 3.5]  # never before the start
    assert verse["window"] == [4.0, 17.9]  # the downbeat two bars before its bar line (the pickup's), a bar after it ends
    assert refrain["window"] == [16.0, 28.5]  # after a turn, the turn's first downbeat; never past the end
    assert not any("window" in s for s in found if not s["sung"])
    words = karaoke.lyrics(score, "H", 120)
    assert words["sections"] == found and [line["section"] for line in words["lines"]][:3] == ["verse", "verse", "verse"]


def test_a_label_keeps_a_compounds_hyphen_and_closes_up_the_syllables():
    assert [karaoke.written(w) for w in ("*num-bers*", "half-in-vent-ed", "nine-ty-odd,", "half-a-sleep;", "has-n't",
                                         "in-vent-ed", "hum-med", "wire,", "zor-blax")] == [
        "numbers", "half-invented", "ninety-odd,", "half-asleep;", "hasn't", "invented", "hummed", "wire,", "zorblax"]
    assert karaoke.written("zor-blax-ing", {"zor-blax-ing": "Z AO1 R B L AE0 K S IH0 NG"}) == "zorblaxing"


def test_the_karaoke_sings_a_spec_and_records_one_section_at_a_time(workspace, monkeypatch):
    path = short(workspace)
    monkeypatch.setattr(M, "SETS", workspace / "sets")
    monkeypatch.setattr(karaoke.Karaoke, "genome_path", path, raising=False)
    monkeypatch.setattr(karaoke.Karaoke, "genome", G.load(path))
    server = ThreadingHTTPServer(("127.0.0.1", 0), karaoke.Karaoke)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers, err.read()

    try:
        code, _, body = get("/variants")
        offered = json.loads(body)
        assert offered["default"] == {"set": "song", "key": 0, "tempo": 100, "mix": "melody"}
        assert offered["keys"] == list(M.KEYS) and offered["tempos"] == list(M.TEMPOS) and offered["mixes"] == list(M.MIXES)
        code, _, body = get("/lyrics.json?spec=song.k-2.t90")
        words = json.loads(body)
        assert code == 200 and words["spec"] == {"id": "song.k-2.t90", "set": "song", "key": -2, "tempo": 90}
        assert words["tempo"] == pytest.approx(0.9 * G.load(path).seed_params["tempo"]) and words["lines"]
        sung = [s for s in words["sections"] if s["sung"]]
        assert sung and sung[0]["label"] and sung[0]["window"][1] > sung[0]["window"][0] >= 0
        assert not (workspace / "renders" / "guide" / "h-short" / "song.k-2.t90.melody.wav").exists()  # words: no audio
        assert K.guide_score("h-short", words["guide"])  # its score kept as it's handed out, for the takes sung to it
        code, headers, body = get("/guide.wav?spec=song.k-2.t90&mix=melody")
        assert code == 200 and headers["X-Guide-Score"] == words["guide"]
        assert body == M.spec_path("h-short", "song.k-2.t90", "melody").read_bytes()
        assert get("/guide.wav?spec=song.k3.t90&mix=melody")[0] == 404
        assert get("/guide.wav?spec=song.k-2.t90&mix=kazoo")[0] == 404
        assert get("/lyrics.json?spec=nope.k0.t100")[0] == 404

        wav = io.BytesIO()
        sf.write(wav, np.zeros(48000), 48000, format="WAV", subtype="PCM_16")

        def take(**query):
            q = "&".join(f"{k}={v}" for k, v in query.items())
            req = urllib.request.Request(f"{base}/take?{q}", data=wav.getvalue(), headers={"Content-Type": "audio/wav"})
            try:
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as err:
                return json.loads(err.read())

        section = sung[0]
        a, b = section["window"]
        kept = take(singer="Jo", mix="melody", guide=words["guide"], spec="song.k-2.t90", from_s=a, to_s=b,
                    section=section["index"], shift_ms=3)
        side = json.loads((workspace / kept["path"]).with_suffix(".json").read_text())
        assert (side["spec"], side["from_s"], side["to_s"], side["section"], side["guide"], side["shift_ms"]) == (
            "song.k-2.t90", a, b, section["index"], words["guide"], 3.0)
        assert K.guide_score("h-short", words["guide"])  # the spec's score, kept beside the takes
        whole = take(singer="Jo", mix="full", guide=words["guide"], spec="song.k-2.t90")
        side = json.loads((workspace / whole["path"]).with_suffix(".json").read_text())
        assert (side["from_s"], side["to_s"], side["section"]) == (0.0, words["duration"], None)
        assert "sings nothing" in take(singer="Jo", mix="melody", guide=words["guide"], spec="song.k-2.t90", section=99)["error"]
        assert "isn't inside" in take(singer="Jo", mix="melody", guide=words["guide"], spec="song.k-2.t90", from_s=-1)["error"]
        assert "changed" in take(singer="Jo", mix="melody", guide="0" * 12, spec="song.k-2.t90")["error"]
        # a spec's guide isn't the single guide's, nor another spec's
        assert "isn't the spec" in take(singer="Jo", mix="melody", guide=words["guide"], spec="song.k0.t100")["error"]

        code, _, body = get("/singers")
        takes = {t["section"]: t for t in json.loads(body)[0]["takes"]}  # two takes in one second: either order
        assert set(takes) == {section["index"], None} and {t["spec"] for t in takes.values()} == {"song.k-2.t90"}
        assert (takes[section["index"]]["from_s"], takes[section["index"]]["to_s"]) == (a, b)
    finally:
        server.shutdown()
        server.server_close()


def test_a_singer_who_asked_not_to_be_credited_is_not(workspace):
    here = K.keep_sung("song", "Milo", b"RIFF-a", "abc123abc123")  # sung here: credited if the artist asks
    assert karaoke.credited([here]) == "Milo"
    yes = K.keep_sung("song", "Ana", b"RIFF-b", "abc123abc123", source="online", credit=True, credit_as="Ana María")
    no = K.keep_sung("song", "Ana", b"RIFF-c", "abc123abc123", source="online", credit=False, credit_as="Ana María")
    assert karaoke.credited([yes]) == "Ana María"  # the name they gave to be credited by
    assert karaoke.credited([yes, no]) is None  # one take said no: no credit
    nameless = K.keep_sung("song", "choir (ab12cd)", b"RIFF-d", "abc123abc123", source="online", credit=False, credit_as="")
    assert karaoke.credited([nameless]) is None
