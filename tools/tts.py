"""Speech from a few text-to-speech services, for reference singers only (dev-only).

    say:Daniel             a macOS system voice
    elevenlabs:George      an ElevenLabs premade voice, by name or voice id   (ELEVENLABS_API_KEY)
    gemini:Kore            a Gemini TTS prebuilt voice                        (GEMINI_API_KEY)

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
import json
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
ELEVENLABS_MODEL = "eleven_multilingual_v2"
GEMINI_MODEL = "gemini-3.8-flash-tts"


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


def request(url: str, headers: dict, body: dict | None = None, tries: int = 6) -> bytes:
    """POST (or GET without a body), waiting and retrying when the service says slow down."""
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"})
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


def elevenlabs_voice(name: str) -> str:
    """A voice id from a premade voice's name (its first word will do), or the id itself."""
    xi = {"xi-api-key": key("ELEVENLABS_API_KEY")}
    voices = json.loads(request("https://api.elevenlabs.io/v1/voices", xi))["voices"]
    for v in voices:
        if name in (v["voice_id"], v["name"]) or v["name"].split(" ")[0].lower() == name.lower():
            return v["voice_id"]
    raise SystemExit(f"no ElevenLabs voice called {name}; try one of: " + ", ".join(v["name"].split(" ")[0] for v in voices))


def elevenlabs(text: str, voice: str) -> tuple[np.ndarray, int]:
    xi = {"xi-api-key": key("ELEVENLABS_API_KEY")}
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice(voice)}?output_format=pcm_24000"
    body = {"text": text, "model_id": ELEVENLABS_MODEL, "voice_settings": {"stability": 0.6, "similarity_boost": 0.75}}
    return pcm16(request(url, xi, body)), 24000


def gemini(text: str, voice: str) -> tuple[np.ndarray, int]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}},
    }
    reply = json.loads(request(url, {"x-goog-api-key": key("GEMINI_API_KEY")}, body))
    part = reply["candidates"][0]["content"]["parts"][0]["inlineData"]
    rate = int(part["mimeType"].split("rate=")[1].split(";")[0]) if "rate=" in part["mimeType"] else 24000
    return pcm16(base64.b64decode(part["data"])), rate


def say(text: str, voice: str) -> tuple[np.ndarray, int]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "line.aiff"
        subprocess.run(["say", "-v", voice, "-o", str(path), text], check=True)
        y, sr = sf.read(str(path), always_2d=True)
    return y.mean(axis=1), sr


SERVICES = {"say": say, "elevenlabs": elevenlabs, "gemini": gemini}


def parse(spec: str) -> tuple[str, str]:
    """'elevenlabs:George' -> ('elevenlabs', 'George'); a bare name is a macOS voice."""
    service, _, voice = spec.partition(":")
    return (service, voice) if voice and service in SERVICES else ("say", spec)


def slug(spec: str) -> str:
    service, voice = parse(spec)
    return f"{service}-" + "".join(c if c.isalnum() else "-" for c in voice.lower()).strip("-")


def line(text: str, spec: str, sr: int) -> np.ndarray:
    """One line of text read aloud in a voice, at sr, trimmed of silence at either end."""
    service, voice = parse(spec)
    model = {"elevenlabs": ELEVENLABS_MODEL, "gemini": GEMINI_MODEL}.get(service, "")
    name = hashlib.sha256(f"{service}|{voice}|{model}|{text}".encode()).hexdigest()[:16]
    cached = CACHE / slug(spec) / f"{name}.wav"
    if cached.exists():
        y, rate = sf.read(str(cached))
    else:
        y, rate = SERVICES[service](text, voice)
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
