"""Speech from a few text-to-speech services, for reference singers only (dev-only).

    say:Daniel             a macOS system voice
    elevenlabs:George      an ElevenLabs premade voice, by name or voice id   (ELEVENLABS_API_KEY)
    elevenlabs:George/sings    the same with an Eleven v3 audio tag before every line: [sings]
    gemini:Kore            a Gemini TTS prebuilt voice                        (GEMINI_API_KEY)

Each service's newest speech model and its own controls for delivery: Eleven
v3 (ELEVENLABS_MODEL) at its "Natural" stability, with an optional audio tag
per line; Gemini 3.8 TTS (GEMINI_MODEL) through its interactions API, with a
speech_metadata style (GEMINI_STYLE) saying how the lyric is read. And
revoice(): ElevenLabs' voice changer (speech to speech), which re-voices a
sung take in one of its voices while keeping the take's pitch and timing.

These voices belong to nobody, which is the point: they sing the song with a
phrasing we choose, so we can check how well the extractor finds it again
(tools/reference.py). They never join the lineage. Keys come from the
environment or from a .env file at the repository root, which git ignores.
Every line read is kept in renders/reference/speech/, so the same line in the
same voice is only ever paid for once.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import uuid
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = Path(__file__).parent.parent
CACHE = ROOT / "renders" / "reference" / "speech"
ELEVENLABS_MODEL = "eleven_v3"  # the most expressive; audio tags in [brackets]
ELEVENLABS_STABILITY = 0.5  # v3's "Natural": 0.0 Creative (drifts), 1.0 Robust (flat, ignores tags)
ELEVENLABS_REVOICE = "eleven_multilingual_sts_v2"  # the voice changer
GEMINI_MODEL = "gemini-3.8-flash-tts"
# How a Gemini voice reads each line (speech_metadata "style"): a lyric, not an announcement.
GEMINI_STYLE = "reading the lyric of a folk song aloud: warm, unhurried and gentle, every vowel full and clear"


def key(name: str) -> str:
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == name and v.strip():
                return v.strip().strip("'\"")
    raise SystemExit(f"{name} isn't set (in the environment or in .env)")


def request(url: str, headers: dict, body: dict | bytes | None = None, tries: int = 6) -> bytes:
    """POST (or GET without a body), waiting and retrying when the service says slow down.
    A dict body goes as JSON; bytes go as they are (headers then say what they are)."""
    data = json.dumps(body).encode() if isinstance(body, dict) else body
    kind = {"Content-Type": "application/json"} if isinstance(body, dict) else {}
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={**kind, **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt + 1 < tries:
                time.sleep(min(60.0, 4.0 * 2**attempt))
                continue
            raise SystemExit(f"{url.split('?')[0]}: HTTP {e.code} {e.read()[:300]!r}") from None
    raise AssertionError("unreachable")


def pcm16(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def audio(raw: bytes, rate: int) -> tuple[np.ndarray, int]:
    """Sound from a service's bytes: a WAV (read by its header, never played as samples) or bare 16-bit PCM."""
    if raw[:4] == b"RIFF":
        y, sr = sf.read(io.BytesIO(raw), always_2d=True)
        return y.mean(axis=1), sr
    return pcm16(raw), rate


def elevenlabs_voice(name: str) -> str:
    """A voice id from a premade voice's name (its first word will do), or the id itself."""
    xi = {"xi-api-key": key("ELEVENLABS_API_KEY")}
    voices = json.loads(request("https://api.elevenlabs.io/v1/voices", xi))["voices"]
    for v in voices:
        if name in (v["voice_id"], v["name"]) or v["name"].split(" ")[0].lower() == name.lower():
            return v["voice_id"]
    raise SystemExit(f"no ElevenLabs voice called {name}; try one of: " + ", ".join(v["name"].split(" ")[0] for v in voices))


def elevenlabs(text: str, voice: str, tag: str = "") -> tuple[np.ndarray, int]:
    """Eleven v3 reading one line, with an audio tag before it if given ("sings": [sings] ...)."""
    xi = {"xi-api-key": key("ELEVENLABS_API_KEY")}
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice(voice)}?output_format=pcm_24000"
    body = {"text": f"[{tag}] {text}" if tag else text, "model_id": ELEVENLABS_MODEL,
            "voice_settings": {"stability": ELEVENLABS_STABILITY}, "seed": 1}
    return audio(request(url, xi, body), 24000)


def revoice(y: np.ndarray, sr: int, voice: str) -> np.ndarray:
    """A take sung again in an ElevenLabs voice by its voice changer, keeping the take's pitch
    and timing: every sung stretch sent on its own (the silences between aren't paid for), put back
    where it was. Returns sound at sr."""
    xi = {"xi-api-key": key("ELEVENLABS_API_KEY")}
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{elevenlabs_voice(voice)}?output_format=pcm_24000"
    out = np.zeros(len(y))
    for a, b in stretches(y, sr):
        buf = io.BytesIO()
        sf.write(buf, y[a:b].astype(np.float32), sr, format="WAV", subtype="PCM_16")
        name = hashlib.sha256(buf.getvalue() + f"|{voice}|{ELEVENLABS_REVOICE}".encode()).hexdigest()[:16]
        cached = CACHE / f"revoice-{voice.lower()}" / f"{name}.wav"
        if cached.exists():
            z, rate = sf.read(str(cached))
        else:
            fields = {"model_id": ELEVENLABS_REVOICE, "seed": "1", "remove_background_noise": "false",
                      "voice_settings": json.dumps({"stability": 0.5, "similarity_boost": 0.75})}
            body, kind = multipart(fields, "audio", "take.wav", buf.getvalue())
            z, rate = audio(request(url, {**xi, "Content-Type": kind}, body), 24000)
            cached.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(cached), z, rate, subtype="FLOAT")
        z = resample_poly(z, sr, rate) if rate != sr else z
        n = min(len(z), len(out) - a)
        fade = np.minimum(1.0, np.minimum(np.arange(n), np.arange(n)[::-1]) / (0.01 * sr))  # no clicks at the seams
        out[a : a + n] += z[:n] * fade
    return out


def stretches(y: np.ndarray, sr: int, gap: float = 0.6, pad: float = 0.15) -> list[tuple[int, int]]:
    """Where a take has singing: runs of sound, split where it's quiet for gap seconds, with pad either side."""
    hop = int(0.01 * sr)
    db = 10 * np.log10(np.array([np.mean(y[i : i + hop] ** 2) for i in range(0, len(y) - hop, hop)]) + 1e-12)
    on = np.flatnonzero(db > np.max(db) - 45.0)
    if not len(on):
        return []
    runs, start, last = [], on[0], on[0]
    for i in on[1:]:
        if (i - last) * 0.01 >= gap:
            runs.append((start, last + 1))
            start = i
        last = i
    runs.append((start, last + 1))
    return [(max(int((a * 0.01 - pad) * sr), 0), min(int((b * 0.01 + pad) * sr), len(y))) for a, b in runs]


def multipart(fields: dict, file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    """A multipart/form-data body with some text fields and one file."""
    boundary = uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: audio/wav\r\n\r\n".encode() + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def gemini(text: str, voice: str, tag: str = "") -> tuple[np.ndarray, int]:
    """Gemini 3.8 TTS reading one line (interactions API), in GEMINI_STYLE, or tag as the style if given."""
    body = {
        "model": GEMINI_MODEL,
        "input": [{"type": "user_input", "content": [{
            "type": "text", "text": text,
            "annotations": [{"type": "speech_metadata", "style": tag or GEMINI_STYLE}],
        }]}],
        "response_format": {"type": "audio", "mime_type": "audio/l16", "sample_rate": 24000},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }
    reply = json.loads(request("https://generativelanguage.googleapis.com/v1beta/interactions",
                               {"x-goog-api-key": key("GEMINI_API_KEY")}, body))
    data = b"".join(base64.b64decode(c["data"]) for step in reply.get("steps", [])
                    for c in step.get("content", []) if "data" in c)
    if not data:
        raise SystemExit(f"Gemini sent no audio: {json.dumps(reply)[:300]}")
    return audio(data, 24000)


def say(text: str, voice: str, tag: str = "") -> tuple[np.ndarray, int]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "line.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(path), text], check=True)
        y, sr = sf.read(str(path), always_2d=True)
    return y.mean(axis=1), sr


SERVICES = {"say": say, "elevenlabs": elevenlabs, "gemini": gemini}


def parse(spec: str) -> tuple[str, str, str]:
    """'elevenlabs:George/sings' -> ('elevenlabs', 'George', 'sings'); a bare name is a macOS voice."""
    service, _, rest = spec.partition(":")
    if not rest or service not in SERVICES:
        service, rest = "say", spec
    voice, _, tag = rest.partition("/")
    return service, voice, tag


def slug(spec: str) -> str:
    service, voice, tag = parse(spec)
    return f"{service}-" + "".join(c if c.isalnum() else "-" for c in f"{voice}-{tag}".lower()).strip("-")


def line(text: str, spec: str, sr: int) -> np.ndarray:
    """One line of text read aloud in a voice, at sr, trimmed of silence at either end."""
    service, voice, tag = parse(spec)
    how = {"elevenlabs": f"{ELEVENLABS_MODEL}|{ELEVENLABS_STABILITY}", "gemini": f"{GEMINI_MODEL}|{GEMINI_STYLE}"}.get(service, "")
    name = hashlib.sha256(f"{service}|{voice}|{tag}|{how}|{text}".encode()).hexdigest()[:16]
    cached = CACHE / slug(spec) / f"{name}.wav"
    if cached.exists():
        y, rate = sf.read(str(cached))
    else:
        y, rate = SERVICES[service](text, voice, tag)
        cached.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(cached), y, rate, subtype="FLOAT")
    y = resample_poly(y, sr, rate) if rate != sr else y
    loud = np.flatnonzero(np.abs(y) > 0.01 * np.max(np.abs(y)))
    return y[max(loud[0] - int(0.02 * sr), 0) : loud[-1] + int(0.05 * sr)] if len(loud) else y


def speak(lines: list[str], spec: str, sr: int, pause: float) -> np.ndarray:
    """Lines read one at a time, with pause seconds of silence after each."""
    parts = [np.zeros(int(0.3 * sr))]
    for text in lines:
        parts += [line(text, spec, sr), np.zeros(int(pause * sr))]
    return np.concatenate(parts)
