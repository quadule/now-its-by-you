"""Someone's version, received: a rendition a person opens in the studio (the FLAC they were sent, carrying its
packet), read as data and never run. docs/WEB-STUDIO.md, "Opening someone's version", has the design and its
threat model.

A packet carries a program. Nothing here executes, imports, unpacks or writes to disk anything from it, and no
name inside it ever chooses a path. The archive's directory is read by hand before zipfile opens it; exactly two
members are read, into memory and no further than their caps: manifest.json (the record) and genome.json (the
song). Both are untrusted JSON: parsed strictly, walked with caps, and checked against what this program
accepts. The record is cleaned to what a parent gives its child and held to this program's bounds; the song is
checked the way the program loads one, and laid out to see that it ends. The audio must be what the record's id
says it is, as `render --parent` has it.

All of it runs in a process of its own (`examine`, run by `Studio.receive` as `python -I`, with limits on its
time and memory): whatever a hostile file does to the reader, the studio only hears "refused". What comes back
is the cleaned record and the song's bytes, which the studio keeps (`Versions`) under an id made from them.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import io
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
import zlib
from dataclasses import fields
from datetime import date
from pathlib import Path

UPLOAD = 64 * 2**20  # the most a file may be: a rendition is about 15 to 20 MB
ENTRIES = 512  # the most entries an archive may list: a packet has about 90
DIRECTORY = 2**20  # the most its central directory may take
ARCHIVE = 100 * 2**20  # the most its entries may declare, in all (as the bootstrap caps an unpacking)
RATIO = 1000  # the most any entry may declare it grows, uncompressed against compressed
RECORD = 2**20  # manifest.json's cap (a record is about 100 KB)
GENOME = 512 * 2**10  # genome.json's (a song is about 45 KB)
DEPTH = 16  # nesting of any JSON read
VALUES = 100_000  # values in any JSON read
STRING = 4096  # characters in any string of a record
SONG_STRING = 65536  # ... of a song (its sketch, its lines)
ITEMS = 4096  # entries of any list or map
BIG = 2**53  # the largest integer taken (JSON's exact integers)
MINUTES = 12.0  # the longest a version may play, laid out as the studio would sing it
NOTES = 50_000  # the most notes it may have (H has about 3,000)
NOTE_SECONDS = 60.0  # the longest any one note may sound
AUDIO_MINUTES = MINUTES + 1  # the longest audio decoded
THINKING = 40.0  # seconds the program may take to read a version (its view, six years of its timeline): H 5 on an M1
SECONDS = 60  # the reader's time (its processor's, and about the same on the clock) before it's stopped
MEMORY = 3 * 2**30  # its address space, where the system can hold it to one (Linux)
ID = re.compile(r"[0-9a-f]{64}")
VERSION = re.compile(r"[0-9a-f]{32}")
NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._ +-]{0,199}(/[A-Za-z0-9_][A-Za-z0-9._ +-]{0,199}){0,15}/?")
TIMBRE = re.compile(r"([a-z0-9_-]{1,40}(:\d{1,20}(\.\d{1,9})?)?(,[a-z0-9_-]{1,40}(:\d{1,20}(\.\d{1,9})?)?){0,31})?")
WORD = re.compile(r"[A-Za-z0-9 _.:,+-]{0,128}")
ENGINES = ("learned", "formant")  # not the experimental waveguide
# What a parent gives its child (cli.render_one, explain.Context, phrasing.inherited, cli.choir_of): nothing else
# of a record is kept. Not its machine's numbers (voice, drift), which name nothing but aren't needed.
KEPT = ("id", "title", "name", "generation", "parent_id", "ancestry", "rendered_at", "params", "lyrics", "singer",
        "lineage_singers", "performance", "chosen_by_you", "program_sha256", "program_version", "record_format",
        "duration")


class Refused(ValueError):
    """A file that can't be opened as a version, and why, in a sentence for the person who brought it."""


# ---------------------------------------------------------------- the archive, read as data


def _directory_end(f, size: int) -> tuple[int, int, int]:
    """The end of the archive's central directory, read by hand before zipfile is trusted with it: where the
    directory starts, how long it is, and how many entries it says it has. The same end record zipfile takes
    (the last in the file's last 64 KB), and it must end the file exactly. A packet has no ZIP64, one disk, a
    few entries, and its directory right before its end record (its offsets are absolute: pack.py)."""
    span = min(size, 22 + 65535)
    f.seek(size - span)
    tail = f.read(span)
    at = tail.rfind(b"PK\x05\x06")
    if at < 0 or at + 22 > len(tail):
        raise Refused("It's a FLAC, but it carries no packet: only a Songbird rendition can be opened here.")
    (_, disk, cd_disk, here, total, cd_size, cd_start, comment) = struct.unpack("<4sHHHHIIH", tail[at:at + 22])
    if at + 22 + comment != len(tail):
        raise Refused("Its packet doesn't end where a rendition's does.")
    end = size - span + at
    if disk or cd_disk or here != total:
        raise Refused("Its packet spans several disks, which no rendition does.")
    zip64 = at >= 20 and tail[at - 20:at - 16] == b"PK\x06\x07"
    if total in (0, 0xFFFF) or cd_size == 0xFFFFFFFF or cd_start == 0xFFFFFFFF or zip64:
        raise Refused("Its packet isn't one a rendition carries (ZIP64, or empty).")
    if total > ENTRIES or cd_size > DIRECTORY:
        raise Refused(f"Its packet lists {total} files; a rendition's lists about 90.")
    if cd_start + cd_size != end:
        raise Refused("Its packet's directory isn't where a rendition's is.")
    return cd_start, cd_size, total


def _tiled(f, infos: list, cd_start: int) -> int:
    """Where the audio ends: the first entry's local header, the entries following one another without a gap or
    an overlap up to the directory, as pack.py writes them (no data descriptors). So the audio is exactly
    everything before the archive, what a player plays, and no entry is read twice (an overlapping zip bomb)."""
    at = None
    for i in sorted(infos, key=lambda i: i.header_offset):
        if i.flag_bits & 0x8:
            raise Refused("Its packet was written in a way no rendition's is (data descriptors).")
        f.seek(i.header_offset)
        head = f.read(30)
        if len(head) != 30 or head[:4] != b"PK\x03\x04":
            raise Refused("Its packet's files aren't where its directory says.")
        name_len, extra_len = struct.unpack("<HH", head[26:30])
        if at is not None and i.header_offset != at:
            raise Refused("Its packet's files overlap, or leave gaps: that's a trap, not a rendition.")
        if at is None:
            first = i.header_offset
        at = i.header_offset + 30 + name_len + extra_len + i.compress_size
    if at != cd_start:
        raise Refused("Its packet's files overlap, or leave gaps: that's a trap, not a rendition.")
    return first


def _bad_name(name: str) -> bool:
    return (not NAME.fullmatch(name) or "\\" in name or "\0" in name
            or any(part in ("", ".", "..") for part in name.rstrip("/").split("/")))


def read_packet(path: str | Path) -> tuple[int, bytes, bytes]:
    """From a file someone brought: where its audio ends, its record's bytes and its song's bytes. Refused, with
    the reason, unless it is a FLAC carrying a packet this program would make. Nothing is unpacked: the two
    members are read into memory through a bounded stream, whatever their headers claim."""
    path = Path(path)
    size = path.stat().st_size
    if size > UPLOAD:
        raise Refused(f"It's {size / 2**20:.0f} MB; a rendition is about 15 to 20 (the most taken is "
                      f"{UPLOAD // 2**20} MB).")
    with path.open("rb") as f:
        if f.read(4) != b"fLaC":
            raise Refused("It isn't a FLAC file. Open the .flac file a Songbird rendition came as.")
        try:
            cd_start, _, total = _directory_end(f, size)
            f.seek(0)
            with zipfile.ZipFile(f) as z:
                infos = z.infolist()
                if len(infos) != total or len(infos) > ENTRIES:
                    raise Refused("Its packet's directory doesn't agree with itself.")
                names = [i.filename for i in infos]
                if len(set(names)) != len(names):
                    raise Refused("Its packet lists the same file twice, which no rendition does.")
                bad = next((n for n in names if _bad_name(n)), None)
                if bad is not None:
                    raise Refused(f"Its packet holds a file named {bad[:60]!r}, which no rendition does.")
                declared = 0
                for i in infos:
                    if i.flag_bits & 0x1:
                        raise Refused("Its packet is encrypted, which no rendition is.")
                    if i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        raise Refused("Its packet is compressed in a way no rendition is.")
                    if i.file_size > RATIO * max(i.compress_size, 1) and i.file_size > 2**20:
                        raise Refused(f"A file in its packet claims to grow {i.file_size // max(i.compress_size, 1)} "
                                      f"times over: that's a trap, not a rendition.")
                    if not 42 <= i.header_offset < cd_start or i.header_offset + i.compress_size > cd_start:
                        raise Refused("Its packet's files aren't where a rendition keeps them.")
                    if i.file_size > ARCHIVE:
                        raise Refused("A file in its packet is larger than a whole rendition's program.")
                    declared += i.file_size
                if declared > ARCHIVE:
                    raise Refused(f"Its packet would unpack to {declared / 2**20:.0f} MB; a rendition's is about 6.")
                if "manifest.json" not in names:
                    raise Refused("It's a FLAC, but it carries no packet: only a Songbird rendition can be opened here.")
                if "genome.json" not in names:
                    raise Refused("Its packet carries no song (genome.json).")
                audio_end = _tiled(f, infos, cd_start)
                record = _member(z, z.getinfo("manifest.json"), RECORD)
                genome = _member(z, z.getinfo("genome.json"), GENOME)
        except Refused:
            raise
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError, zlib.error, struct.error,
                NotImplementedError, RuntimeError, ValueError) as e:
            raise Refused(f"Its packet is damaged ({type(e).__name__}).") from None
    return audio_end, record, genome


def _member(z: zipfile.ZipFile, info: zipfile.ZipInfo, cap: int) -> bytes:
    if info.file_size > cap:
        raise Refused(f"Its packet's {info.filename} is {info.file_size // 1024} KB; a rendition's is far smaller.")
    with z.open(info) as f:
        data = f.read(cap + 1)
    if len(data) > cap:
        raise Refused(f"Its packet's {info.filename} is larger than it says.")
    return data


# ---------------------------------------------------------------- JSON, strictly


def _pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise Refused(f"It says {k[:40]!r} twice in one place, which no rendition does.")
        out[k] = v
    return out


def _constant(name):
    raise Refused(f"It holds {name}, which no rendition does.")


def strict_json(data: bytes, what: str, strings: int = STRING):
    """JSON from a stranger: UTF-8, no key twice, no NaN or Infinity, and within the caps (depth, values,
    strings, lists, integers). Refused, saying what, otherwise."""
    try:
        text = data.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except Refused:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        raise Refused(f"Its {what} can't be read ({type(e).__name__}).") from None
    count = 0
    stack = [(value, 1)]
    while stack:
        v, depth = stack.pop()
        count += 1
        if count > VALUES or depth > DEPTH:
            raise Refused(f"Its {what} is too large or too deep for a rendition's.")
        if isinstance(v, dict):
            if len(v) > ITEMS or any(len(k) > 256 for k in v):
                raise Refused(f"Its {what} is too large for a rendition's.")
            stack.extend((x, depth + 1) for x in v.values())
        elif isinstance(v, list):
            if len(v) > ITEMS:
                raise Refused(f"Its {what} holds a list too long for a rendition's.")
            stack.extend((x, depth + 1) for x in v)
        elif isinstance(v, str):
            if len(v) > strings:
                raise Refused(f"Its {what} holds a string too long for a rendition's.")
        elif isinstance(v, bool) or v is None:
            pass
        elif isinstance(v, int):
            if abs(v) > BIG:
                raise Refused(f"Its {what} holds a number too large for a rendition's.")
        elif isinstance(v, float):
            if not math.isfinite(v):
                raise Refused(f"Its {what} holds a number that isn't one.")
    return value


# ---------------------------------------------------------------- the song


def check_genome(data, title: str | None):
    """The song a version sang, as this program loads one, within caps; and this studio's song (by title)."""
    from . import genome as genome_mod

    if not isinstance(data, dict):
        raise Refused("Its song isn't a song.")
    if title is not None and data.get("title") != title:
        got = str(data.get("title"))[:60]
        raise Refused(f"It's a version of \u201c{got}\u201d; this studio sings \u201c{title}\u201d.")
    shape = {"phrases": 64, "sections": 32, "form": 64, "seed_verses": 64, "refrain": 32, "hooks": 256}
    for name, most in shape.items():
        held = data.get(name)
        if held is not None and (not isinstance(held, (dict, list)) or len(held) > most):
            raise Refused(f"Its song's {name} is larger than any song's.")
    # its shape: the form's grammar is built from these (variation.parse_form), so they are held to a song's
    # size, and the verses a form may have to a few
    template = data.get("form")
    section = re.compile(r"[a-z][a-z0-9_]{0,23}")
    if not isinstance(template, list) or not 1 <= len(template) <= 24 or \
            not all(isinstance(t, str) and section.fullmatch(t.rstrip("?*")) for t in template) or \
            sum(t.endswith("*") for t in template) > 2:
        raise Refused("Its song's form isn't one this program sings.")
    if not isinstance(data.get("sections"), dict) or not all(section.fullmatch(k) for k in data["sections"]):
        raise Refused("Its song's sections aren't ones this program sings.")
    bank = data.get("bank")
    if bank is not None:
        count = (((bank.get("rules") or {}).get("verses") or {}).get("count") if isinstance(bank, dict) else None)
        if not isinstance(bank, dict) or count is not None and not (
                isinstance(count, list) and len(count) == 2 and all(isinstance(c, int) and not isinstance(c, bool)
                                                                    for c in count) and 1 <= count[0] <= count[1] <= 8):
            raise Refused("Its song's words bank isn't one this program sings (at most eight verses).")
    for spec in (data.get("phrases") or {}).values():
        if not isinstance(spec, dict) or not isinstance(spec.get("tune"), str) or len(spec["tune"]) > 1024 \
                or not isinstance(spec.get("chords"), str) or len(spec["chords"]) > 1024:
            raise Refused("Its song has a phrase this program can't read.")
    seed = data.get("seed_params")
    if not isinstance(seed, dict):
        raise Refused("Its song has no parameters of its own.")
    if not (isinstance(seed.get("tempo"), (int, float)) and 50 <= seed["tempo"] <= 220):
        raise Refused("Its song's tempo is outside what this program sings (50 to 220 beats a minute).")
    if not (isinstance(seed.get("tonic"), int) and 36 <= seed["tonic"] <= 84):
        raise Refused("Its song's key is outside what this program sings.")
    try:
        genome = genome_mod.from_dict(data)
    except Refused:
        raise
    except Exception as e:  # noqa: BLE001 - any way the program can't load it is a reason to refuse it
        raise Refused(f"Its song isn't one this program can sing: {_why(e)}") from None
    return genome


# ---------------------------------------------------------------- the record


def _why(e: Exception) -> str:
    text = str(e).strip().replace("\n", " ")[:160]
    return f"{type(e).__name__}{': ' + text if text else ''}"


def _number(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Refused(f"Its record's {what} isn't a number.")
    return float(v)


def _integer(v, what: str) -> int:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, bool) or not isinstance(v, int):
        raise Refused(f"Its record's {what} isn't a whole number.")
    return v


def _within(v: float, lo: float, hi: float, what: str) -> None:
    if not lo <= v <= hi:
        raise Refused(f"Its record's {what} ({v:g}) is outside what this program sings ({lo:g} to {hi:g}).")


def _envelope(default: float, bounds: tuple | None) -> tuple[float, float]:
    """Where a number may be in a parent's record: within this program's bounds for it, widened by their span
    each way (an older program's bounds were a little different, and the child's own is held to them anyway);
    where the program has no bounds for it, within eight times its default's size, on the default's side of 0."""
    if bounds is not None and all(math.isfinite(b) for b in bounds):
        lo, hi = bounds
        span = max(hi - lo, 1e-9)
        return lo - span, hi + span
    if default == 0:
        return -2.0, 2.0
    return (0.0, 8.0 * default) if default > 0 else (8.0 * default, 0.0)


# Where each of the singer's numbers may be in a parent's record (synth.voice.VoiceParams): wide of anything the
# program chooses (variation.KNOBS holds a child's own tighter, and a person can't set these), and every one
# finite, so that nothing a record says makes the synth's arrays enormous or its sums run away. A field this
# table doesn't know yet is held to _envelope.
SINGER = {"shift": (-24, 12), "tract": (0.8, 1.4), "rd": (0.3, 2.5), "tilt": (0.1, 2.0), "breath": (0.0, 0.5),
          "vibrato_rate": (2.0, 10.0), "vibrato_depth": (0.0, 100.0), "vibrato_delay": (0.0, 1.5),
          "glide": (0.02, 0.5), "glide_spread": (0.0, 1.5), "overshoot": (0.0, 0.2), "scoop": (0.0, 2.0),
          "jitter": (0.0, 3.0), "wander": (0.0, 40.0), "shimmer": (0.0, 15.0), "articulation": (0.3, 3.0),
          "cluster": (0.2, 2.0), "across": (0.3, 3.0), "glides": (0.3, 3.0), "liquids": (0.3, 3.0),
          "release": (0.0, 0.5), "dynamics": (0.0, 40.0), "lean": (-6.0, 12.0), "light": (-6.0, 12.0),
          "ease": (-6.0, 12.0), "let_go": (-6.0, 12.0), "climb": (-3.0, 3.0), "taper": (-24.0, 6.0),
          "vibrato_from": (0.0, 4.0), "breathe": (0.0, 1.0), "inhale": (-80.0, 0.0), "accent": (-50.0, 50.0),
          "tremolo": (0.0, 6.0), "waver": (0.0, 10.0), "spread": (0.0, 2.0), "focus": (-6.0, 12.0),
          "reduce": (0.0, 1.0), "mouth": (0.5, 2.0), "air": (0.0, 1.0), "crisp": (0.0, 2.0)}


def _range(head: str, name: str, default) -> tuple[float, float]:
    """Where a parent's number may be: the singer's table; the mix's designed ranges (synth.mixing.RANGES);
    else a knob's bounds, widened; else the envelope around its default."""
    from .synth.mixing import RANGES

    if head == "singer" and name in SINGER:
        return SINGER[name]
    if head == "mix" and name in RANGES:
        return RANGES[name]
    return _envelope(default, _knob_bounds().get(f"{head}.{name}"))


def _knob_bounds() -> dict[str, tuple]:
    from . import variation

    return {k.path: k.bounds for k in variation.KNOBS if not callable(k.bounds)}


def _fields(data, cls, head: str, what: str, extra: dict | None = None) -> dict:
    """A dict of a dataclass's fields (VoiceParams, MixParams, Band...) as a record holds them: known names only,
    each of its default's type, numbers within their envelope."""
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise Refused(f"Its record's {what} isn't a map.")
    known = {f.name: f for f in fields(cls)}
    out = {}
    for k, v in data.items():
        if k in (extra or {}):
            out[k] = extra[k](v)
            continue
        f = known.get(k)
        if f is None:
            continue  # a field this program doesn't have: left out, as its from_dict leaves it
        default = getattr(cls(), k)
        name = f"{what}'s {k}"
        if isinstance(default, bool):
            if not isinstance(v, bool):
                raise Refused(f"Its record's {name} isn't true or false.")
            out[k] = v
        elif isinstance(default, int):
            n = _integer(v, name)
            _within(n, *_range(head, k, default), name)
            out[k] = n
        elif isinstance(default, float):
            n = _number(v, name)
            _within(n, *_range(head, k, default), name)
            out[k] = n
        elif isinstance(default, str):
            if not isinstance(v, str) or not WORD.fullmatch(v):
                raise Refused(f"Its record's {name} isn't a word this program knows.")
            out[k] = v
        else:
            raise Refused(f"Its record's {name} isn't one this program reads.")
    return out


def _singer(data, what: str) -> dict:
    from .synth.voice import VoiceParams

    def engine(v):
        if v not in ENGINES:
            raise Refused(f"Its record's {what}'s engine isn't one of this program's.")
        return v

    def timbre(v):
        if not isinstance(v, str) or not TIMBRE.fullmatch(v):
            raise Refused(f"Its record's {what}'s timbre isn't one this program reads.")
        return v

    return _fields(data, VoiceParams, "singer", what, {"engine": engine, "timbre": timbre})


def _mix(data) -> dict:
    from .synth.mixing import MixParams

    def tone(v):
        if not isinstance(v, list) or len(v) > 8:
            raise Refused("Its record's mix's tone isn't one this program reads.")
        out = [_number(x, "mix's tone") for x in v]
        for x in out:
            _within(x, 0.0, 2.0, "mix's tone")
        return out

    def balance(v):
        pairs = v.items() if isinstance(v, dict) else v if isinstance(v, list) else None
        if pairs is None or len(v) > 32:
            raise Refused("Its record's mix's balance isn't one this program reads.")
        out = {}
        for pair in pairs:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2 or not isinstance(pair[0], str) \
                    or not WORD.fullmatch(pair[0]):
                raise Refused("Its record's mix's balance isn't one this program reads.")
            out[pair[0]] = _number(pair[1], "mix's balance")
            _within(out[pair[0]], -12.0, 12.0, "mix's balance")
        return out

    return _fields(data, MixParams, "mix", "mix", {"tone": tone, "balance": balance})


def _band(data) -> dict:
    from .band import Band

    def lineup(v):
        if not isinstance(v, (dict, list)) or len(v) > 32:
            raise Refused("Its record's band's lineup isn't one this program reads.")
        pairs = v.items() if isinstance(v, dict) else v
        out = {}
        for pair in pairs:
            if not isinstance(pair, (tuple, list)) or len(pair) != 2 or not isinstance(pair[0], str) \
                    or not WORD.fullmatch(pair[0]):
                raise Refused("Its record's band's lineup isn't one this program reads.")
            out[pair[0]] = _number(pair[1], "band's lineup")
            _within(out[pair[0]], 0.0, 2.0, "band's lineup")
        return out

    return _fields(data, Band, "band", "band", {"lineup": lineup})


def _plain(v, what: str, most: int = 32 * 2**10):
    """Data the program reads through its own constructors (the words held, a style, the composition, the words
    sung, a person's marks): kept as it is, within `most` bytes of JSON (the program's own are a few KB; each
    is read again for every day of the timeline), its shape left to the constructors (in the exercise)."""
    if len(json.dumps(v)) > most:
        raise Refused(f"Its record's {what} is larger than any rendition's.")
    return v


def _variants(v) -> list:
    """The lineage's departures from the written tune (songbird.variants.Variant), each within a note's reach."""
    from .variants import KINDS

    if not isinstance(v, list) or len(v) > 256:
        raise Refused("Its record's variants of the tune aren't ones this program reads.")
    for x in v:
        if not isinstance(x, dict) or not isinstance(x.get("phrase"), str) or x.get("kind") not in KINDS:
            raise Refused("Its record's variants of the tune aren't ones this program reads.")
        _within(_integer(x.get("note"), "variant's note"), 0, 1024, "variant's note")
        if x.get("degree") is not None:
            _within(_integer(x["degree"], "variant's degree"), -24, 32, "variant's degree")
        if "shift" in x:
            _within(_number(x["shift"], "variant's shift"), -16, 16, "variant's shift")
        steps = x.get("steps") or []
        if not isinstance(steps, list) or len(steps) > 16:
            raise Refused("Its record's variants of the tune aren't ones this program reads.")
        for step in steps:
            if not isinstance(step, list) or len(step) != 2:
                raise Refused("Its record's variants of the tune aren't ones this program reads.")
            _within(_number(step[0], "variant's step"), 0.0, 1.0, "variant's step")
            _within(_integer(step[1], "variant's step"), -12, 12, "variant's step")
    return v


def clean_params(data, genome) -> dict:
    """A parent's parameters, field by field against realize.Params, held to this program's bounds."""
    from . import variation
    from .realize import Params

    if not isinstance(data, dict):
        raise Refused("Its record has no parameters.")
    known = {f.name for f in fields(Params)}
    out: dict = {}
    for k in ("tonic", "mode", "tempo", "form"):
        if k not in data:
            raise Refused(f"Its record's parameters have no {k}.")
    song = Params.from_dict(genome.seed_params)
    out["tonic"] = _integer(data["tonic"], "key")
    _within(out["tonic"], song.tonic - 12, song.tonic + 12, "key")
    if data["mode"] not in variation.BRIGHTNESS:
        raise Refused("Its record's mode isn't one this program knows.")
    out["mode"] = data["mode"]
    out["tempo"] = _number(data["tempo"], "tempo")
    _within(out["tempo"], round(0.5 * song.tempo, 1), round(1.6 * song.tempo, 1), "tempo")
    form = data["form"]
    if not isinstance(form, list) or not 1 <= len(form) <= 64 or not all(isinstance(s, str) for s in form):
        raise Refused("Its record's form isn't one this program reads.")
    def sung(name: str) -> bool:  # a section of the song, or one sung again as its own (bridge2: Genome.section)
        try:
            genome.section(name)
        except KeyError:
            return False
        return True

    missing = [s for s in form if not sung(s.rstrip("?*"))]
    if missing:
        raise Refused(f"Its record's form sings a section its song doesn't have ({missing[0][:30]}).")
    out["form"] = list(form)
    numbers = {"humanize": (0.0, 0.05), "ritardando": (0.0, 1.0), "loudness": (-30.0, -6.0), "lay": (-1.0, 1.0)}
    for k, v in data.items():
        if k in out or k not in known and k not in ("room", "swing"):
            continue
        if k in numbers:
            out[k] = _number(v, k)
            _within(out[k], *numbers[k], k)
        elif k == "seed":
            out[k] = _integer(v, "seed")
            _within(out[k], 0, 2**63 - 1, "seed")
        elif k in ("choir", "generation"):
            out[k] = _integer(v, k)
            _within(out[k], 0, variation.CHOIR_MAX if k == "choir" else 100_000, k)
        elif k in ("accomp", "inventory"):
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9 ._:-]{0,256}", v):
                raise Refused(f"Its record's {k} isn't one this program reads.")
            out[k] = v
        elif k == "singer":
            out[k] = _singer(v, "singer")
        elif k in ("mix", "room"):  # room: a record from before the mix, its room the mix's rt60 and tone
            out[k] = _mix(v)
        elif k == "band":
            out[k] = _band(v)
        elif k == "swing":
            out[k] = _number(v, "swing")
            _within(out[k], 0.0, 1.0, "swing")
        elif k == "leanings":
            if not isinstance(v, dict):
                raise Refused("Its record's leanings aren't a map.")
            for name in ("era_bias", "rarity_appetite"):
                if name in v:
                    _within(_number(v[name], name), -2.0, 2.0, name)
            if "mood_weights" in v:
                if not isinstance(v["mood_weights"], dict) or len(v["mood_weights"]) > 16:
                    raise Refused("Its record's moods aren't a map.")
                for x in v["mood_weights"].values():
                    _within(_number(x, "mood"), 0.0, 10.0, "mood")
            out[k] = _plain(v, "leanings", 8 * 2**10)
        elif k == "made":
            if not isinstance(v, dict) or set(v) - {"by", "at"} or not isinstance(v.get("by", ""), str) \
                    or not re.fullmatch(r"[0-9a-f]{0,64}", v.get("by", "")):
                raise Refused("Its record's maker isn't one this program reads.")
            if "at" in v:
                _number(v["at"], "made")
            out[k] = v
        elif k == "variants":
            out[k] = _variants(v)
        elif k in ("words", "style", "composition"):
            if not isinstance(v, dict) or k == "style" and len(v.get("lineage") or []) > 64:
                raise Refused(f"Its record's {k} isn't one this program reads.")
            out[k] = _plain(v, k, 4 * 2**10 if k == "style" else 32 * 2**10)
    return out


def _phrasing(v, what: str):
    """A way of singing as a record carries it (phrasing.to_json), rebuilt from its numbers alone: every gesture
    held to its bounds (phrasing.reduce), nothing else of it kept."""
    from . import phrasing as phrasing_mod

    if v is None:
        return None
    if not isinstance(v, dict) or not isinstance(v.get("phrases"), dict):
        raise Refused(f"Its record's {what} isn't one this program reads.")
    names = v.get("fields", [f.name for f in fields(phrasing_mod.Gesture)])
    known = {f.name for f in fields(phrasing_mod.Gesture)}
    if not isinstance(names, list) or not all(isinstance(n, str) and n in known for n in names):
        raise Refused(f"Its record's {what} isn't one this program reads.")
    if len(v["phrases"]) > 64:
        raise Refused(f"Its record's {what} isn't one this program reads.")
    for rows in v["phrases"].values():
        if not isinstance(rows, list) or len(rows) > 256 or \
                not all(isinstance(r, list) and len(r) <= len(names) for r in rows):
            raise Refused(f"Its record's {what} isn't one this program reads.")
        for r in rows:
            for x in r:
                _number(x, what)
    try:
        return phrasing_mod.to_json(phrasing_mod.from_json({"fields": names, "phrases": v["phrases"]}))
    except Exception as e:  # noqa: BLE001
        raise Refused(f"Its record's {what} isn't one this program reads: {_why(e)}") from None


def clean_record(raw, genome) -> dict:
    """A parent's record as this program keeps it: the fields a parent gives its child, each checked."""
    if not isinstance(raw, dict):
        raise Refused("Its record isn't a record.")
    rid = raw.get("id")
    if not isinstance(rid, str) or not ID.fullmatch(rid):
        raise Refused("Its record has no id, so its place in the line can't be known.")
    sha = raw.get("program_sha256")
    if not isinstance(sha, str) or not ID.fullmatch(sha):
        raise Refused("Its record doesn't say which program made it, as every rendition's does.")
    if raw.get("title") != genome.title:
        raise Refused("Its record is for another song than the one it carries.")
    out: dict = {"id": rid, "title": genome.title, "program_sha256": sha}
    generation = _integer(raw.get("generation", 0), "generation")
    _within(generation, 0, 100_000, "generation")
    out["generation"] = generation
    parent_id = raw.get("parent_id")
    if parent_id is not None and (not isinstance(parent_id, str) or not ID.fullmatch(parent_id)):
        raise Refused("Its record's parent isn't an id.")
    out["parent_id"] = parent_id
    ancestry = raw.get("ancestry") or []
    if not isinstance(ancestry, list) or len(ancestry) > ITEMS or \
            not all(isinstance(a, str) and ID.fullmatch(a) for a in ancestry):
        raise Refused("Its record's ancestry isn't a list of ids.")
    out["ancestry"] = ancestry
    when = raw.get("rendered_at")
    if when is not None:
        if not isinstance(when, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?([+-]\d\d:\d\d|Z)?", when):
            raise Refused("Its record's date isn't a date.")
        with contextlib.suppress(ValueError):
            date.fromisoformat(when[:10])
            out["rendered_at"] = when
        if "rendered_at" not in out:
            raise Refused("Its record's date isn't a date.")
    version = raw.get("program_version")
    if version is not None:
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9.+_-]{1,32}", version):
            raise Refused("Its record's program version isn't one.")
        out["program_version"] = version
    if raw.get("name") is not None:  # its own title, if it has one: a line of plain text, no longer than any is
        from .edits import version_name

        try:
            named = version_name(raw["name"])
        except ValueError:
            raise Refused("Its record's own title isn't one.") from None
        if named:
            out["name"] = named
    fmt = raw.get("record_format")  # absent in records written before the number was (the first version's): 1
    if fmt is not None:
        if isinstance(fmt, bool) or not isinstance(fmt, int) or not 1 <= fmt <= 10**6:
            raise Refused("Its record's format number isn't one.")
        out["record_format"] = fmt
    if raw.get("duration") is not None:
        out["duration"] = _number(raw["duration"], "duration")
        _within(out["duration"], 0.0, AUDIO_MINUTES * 60, "duration")
    out["params"] = clean_params(raw.get("params"), genome)
    if raw.get("singer") is not None:
        out["singer"] = _singer(raw["singer"], "singer")
    sang = raw.get("lineage_singers") or []
    if not isinstance(sang, list) or len(sang) > 16:
        raise Refused("Its record's earlier singers aren't a list.")
    out["lineage_singers"] = []
    for s in sang:
        if not isinstance(s, dict) or not (s.get("id") is None or isinstance(s.get("id"), str) and ID.fullmatch(s["id"])):
            raise Refused("Its record's earlier singers aren't ones this program reads.")
        out["lineage_singers"].append({"id": s.get("id"), "singer": _singer(s.get("singer"), "earlier singer")})
    if "performance" in raw:
        perf = raw["performance"]
        if perf is not None:
            if not isinstance(perf, dict) or not isinstance(perf.get("choir") or [], list) or len(perf.get("choir") or []) > 8:
                raise Refused("Its record's performance isn't one this program reads.")
            perf = {"lead": _phrasing(perf.get("lead"), "way of singing"),
                    "choir": [_phrasing(c, "choir's way of singing") for c in perf.get("choir") or []]}
        out["performance"] = perf
    if raw.get("lyrics") is not None:
        if not isinstance(raw["lyrics"], dict):
            raise Refused("Its record's words aren't a map.")
        out["lyrics"] = _plain(raw["lyrics"], "words", 64 * 2**10)
    if raw.get("chosen_by_you") is not None:
        if not isinstance(raw["chosen_by_you"], dict):
            raise Refused("Its record's marks of a person's choices aren't a map.")
        out["chosen_by_you"] = _plain(raw["chosen_by_you"], "marks of a person's choices", 64 * 2**10)
    return out


# ---------------------------------------------------------------- the audio


def samples_id(audio: bytes, most_minutes: float = AUDIO_MINUTES) -> str:
    """pack.samples_id, a block at a time and no further than `most_minutes` (whatever the stream's header
    says): the SHA-256 of the decoded 16-bit samples, the same digest as the whole at once (the blocks are
    consecutive frames, interleaved). A rendition's audio is what the synth makes: stereo, at its rate."""
    import numpy as np
    import soundfile as sf

    from .synth import SR

    try:
        with sf.SoundFile(io.BytesIO(audio)) as f:
            if f.format != "FLAC" or f.channels != 2 or f.samplerate != SR:
                raise Refused(f"Its audio isn't a rendition's (FLAC, stereo, {SR} Hz).")
            most = int(most_minutes * 60 * f.samplerate)
            if f.frames > most:
                raise Refused(f"Its audio is longer than {most_minutes:g} minutes; no rendition is.")
            h = hashlib.sha256()
            n = 0
            for block in f.blocks(blocksize=65536, dtype="int16", always_2d=True):
                n += len(block)
                if n > most:
                    raise Refused(f"Its audio is longer than {most_minutes:g} minutes; no rendition is.")
                h.update(np.ascontiguousarray(block, dtype="<i2").tobytes())
    except Refused:
        raise
    except Exception as e:  # noqa: BLE001 - libsndfile's errors are RuntimeErrors, or worse
        raise Refused(f"Its audio can't be decoded ({type(e).__name__}).") from None
    return h.hexdigest()


# ---------------------------------------------------------------- trying it as the studio would


def exercise(record: dict, genome, machine: str = "none", day: str | None = None,
             minutes: float | None = None) -> dict:
    """The version as the studio would open it on `day` (the page's view of its child, and its timeline, by a
    neutral machine or the studio's made-up one) and as it would sing it: refused if the program can't, if it
    wouldn't end, if reading it takes the program far longer than the song as it is, or if its child would play
    longer than `minutes` (a public studio's longest whole song, with the lightest band: Studio.most_minutes).
    Returns what the page says of it, and its timeline (the page's heaviest answer, kept with it so the studio
    needn't work it out)."""
    from . import drift as drift_mod, explain, harvest, phrasing as phrasing_mod, variation
    from .cli import _parent
    from .realize import realize

    began = time.monotonic()
    day = day or date.today().isoformat()
    try:
        parent = _parent(record, genome)
        voice = harvest.machine_voice(machine) if machine.startswith(("fictional:", harvest.BROWSER)) else harvest.Voice()
        ctx = explain.Context(genome, parent, record, voice, machine, day, drift_mod.parse(day), shared=True)
        v = ctx.version({})
        explain.view(ctx, v, [])
        lead = phrasing_mod.from_json(v.phrasing_json) if v.phrasing_json else None
        choir = [phrasing_mod.from_json(p) for p in v.choir_phrasings]
        scores = [variation.lay(realize(genome, v.params, phrasing=lead, choir=choir, lyrics=v.lyrics), v.params),
                  realize(genome, parent)]
        for score in scores:
            if len(score.notes) > NOTES:
                raise Refused(f"It has {len(score.notes)} notes; no version of the song has more than {NOTES}.")
            if score.duration > MINUTES * 60 or any(not (0 <= n.start <= MINUTES * 60 and 0 <= n.dur <= NOTE_SECONDS
                                                        and 0 <= n.pitch <= 127) for n in score.notes):
                raise Refused(f"It would play for longer than {MINUTES:g} minutes, or hold a note too long.")
        if minutes is not None and scores[0].duration > minutes * 60:  # a public studio: made there in one go
            raise Refused(f"Its next version would play for {scores[0].duration / 60:.1f} minutes, longer than this "
                          f"studio makes in one go ({minutes:.1f}). Open it in the studio on your own computer "
                          "(python3 the-file.flac studio).")
        drawn = explain.timeline(ctx)
    except Refused:
        raise
    except Exception as e:  # noqa: BLE001 - any way this program can't continue it is the reason it's refused
        raise Refused(f"This program can't continue it: {_why(e)}") from None
    if time.monotonic() - began > THINKING:
        raise Refused("It takes this program far longer to read than any version of the song does.")
    reproducible = machine == "none" or machine.startswith(("fictional:", harvest.BROWSER))
    return {"minutes": round(scores[0].duration / 60, 1),
            "timeline": {"day": day, "machine": machine, "drawn": drawn} if reproducible else None}


def examine(path: str | Path, title: str | None, machine: str = "none", day: str | None = None,
            minutes: float | None = None) -> dict:
    """Everything a received file is checked for, in order, cheapest first: the file and its archive, its two
    members as strict JSON, the song, the record, the audio against the record's id, and the version tried as
    the studio would open it. Returns the cleaned record and the song's bytes (as text), or raises Refused."""
    audio_end, manifest, song = read_packet(path)
    raw = strict_json(manifest, "record")
    genome = check_genome(strict_json(song, "song", strings=SONG_STRING), title)
    record = clean_record(raw, genome)
    with Path(path).open("rb") as f:
        audio = f.read(audio_end)
    if samples_id(audio) != record["id"]:
        raise Refused("Its audio isn't the rendition its record describes, so its place in the line can't be "
                      "trusted.")
    tried = exercise(record, genome, machine, day, minutes)
    return {"record": record, "genome": song.decode("utf-8"), **tried}


def main() -> None:
    """`examine` in a process of its own (Studio.receive): a file's path, the studio's song's title, its machine
    and its day as arguments; the answer as JSON on stdout. Its time and memory are held down first."""
    with contextlib.suppress(Exception):
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (SECONDS, SECONDS))
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (MEMORY, MEMORY))
    path, title, machine, day = sys.argv[1:5]
    minutes = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else None
    try:
        out = examine(path, title or None, machine, day or None, minutes)
    except Refused as e:
        out = {"refused": str(e)}
    except MemoryError:
        out = {"refused": "It took more memory to read than any rendition does."}
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()


# The reader's command: this program's own code, from this program's own folder, never the file's (-I: no
# PYTHONPATH, no user site, no current folder on the path).
READER = ("import sys; sys.path.insert(0, sys.argv.pop(1)); sys.dont_write_bytecode = True; "
          "from songbird.received import main; main()")


def examine_apart(path: str | Path, title: str | None, machine: str, day: str, root: Path, cwd: Path,
                  timeout: float | None = None, minutes: float | None = None) -> dict:
    """`examine`, run in a process of its own (and its own process group, stopped whole if it overstays: after
    `timeout` seconds, at most its own time and a little more): whatever the file does to the reader, only a
    refusal comes back."""
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "SONGBIRD_HOME", "TMPDIR",
                                                          "SYSTEMROOT", "NUMBA_CACHE_DIR", "SONGBIRD_THREADS")}
    env |= {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMBA_NUM_THREADS": "1"}
    reader = subprocess.Popen([sys.executable, "-I", "-c", READER, str(root), str(path), title or "", machine, day,
                               "" if minutes is None else f"{minutes:.3f}"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, cwd=cwd,
                              env=env, start_new_session=os.name == "posix")
    try:
        stdout, _ = reader.communicate(timeout=min(SECONDS + 15, timeout or SECONDS + 15))
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(reader.pid, 9) if os.name == "posix" else reader.kill()
        reader.communicate()
        raise Refused("It took too long to read; no rendition does.") from None
    if reader.returncode != 0 or len(stdout) > 8 * 2**20:
        raise Refused("It couldn't be read here: the reader stopped on it.")
    try:
        out = json.loads(stdout)
    except ValueError:
        raise Refused("It couldn't be read here: the reader stopped on it.") from None
    if not isinstance(out, dict):
        raise Refused("It couldn't be read here: the reader stopped on it.")
    if "refused" in out:
        raise Refused(str(out["refused"])[:400])
    return out


# ---------------------------------------------------------------- the versions kept


def version_id(key: bytes, record: dict, genome: bytes) -> str:
    """A received version's id: a keyed hash (HMAC-SHA-256, 128 bits of it) of what is kept of it, its cleaned
    record and its song. The same file opens as the same version here; and as the key is this studio's own,
    written beside the versions and nowhere else, an id can't be worked out even from a record anyone could
    make (the song a studio sings today for no edits, say): it is known only from the link."""
    h = hmac.new(key, b"songbird-version\0", "sha256")
    h.update(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    h.update(b"\0" + hashlib.sha256(genome).digest())
    return h.hexdigest()[:32]


class Versions:
    """Received versions, as data: each a folder named by its id holding its cleaned record, its song and (for a
    studio whose machine is made up or none) its timeline, kept `days` after it was last opened, the least
    recently opened going first past `limit` bytes or `most` versions. Nothing lists them: an id is known only
    to someone who has the link."""

    def __init__(self, folder: Path, limit: int, days: float, most: int = 4000):
        self.folder, self.limit, self.days, self.most = Path(folder), limit, days, most
        self.folder.mkdir(parents=True, exist_ok=True)
        self.key = self._key()

    def _key(self) -> bytes:
        path = self.folder / ".key"
        with contextlib.suppress(OSError):
            key = path.read_bytes()
            if len(key) == 32:
                return key
        key = os.urandom(32)
        tmp = self.folder / f".key.{os.getpid()}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        tmp.replace(path)
        return path.read_bytes()

    def put(self, record: dict, genome: bytes, timeline: dict | None = None) -> str:
        vid = version_id(self.key, record, genome)
        final = self.folder / vid
        if not final.is_dir():
            part = self.folder / f".part-{vid}.{os.getpid()}.{time.monotonic_ns()}"
            part.mkdir()
            (part / "genome.json").write_bytes(genome)
            (part / "record.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
            if timeline is not None:
                (part / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            try:
                part.rename(final)
            except OSError:  # made at the same moment by another request: theirs is the same
                shutil.rmtree(part, ignore_errors=True)
        with contextlib.suppress(OSError):
            os.utime(final)
        self.prune()
        return vid

    def get(self, vid: str) -> tuple[dict, Path, dict | None] | None:
        """A kept version's record, the path of its song and its timeline if kept; None if there's none by that
        id (or it expired, or went while being read)."""
        if not VERSION.fullmatch(vid or ""):
            return None
        folder = self.folder / vid
        with contextlib.suppress(OSError, ValueError):
            if time.time() - folder.stat().st_mtime < self.days * 86400:
                record = json.loads((folder / "record.json").read_text(encoding="utf-8"))
                timeline = None
                with contextlib.suppress(OSError, ValueError):
                    timeline = json.loads((folder / "timeline.json").read_text(encoding="utf-8"))
                os.utime(folder)
                return record, folder / "genome.json", timeline
        return None

    def prune(self) -> None:
        now = time.time()
        kept = []
        for folder in self.folder.iterdir():
            with contextlib.suppress(OSError):
                if folder.name.startswith(".part-"):
                    if now - folder.stat().st_mtime > 3600:  # a put that never finished
                        shutil.rmtree(folder, ignore_errors=True)
                    continue
                if not VERSION.fullmatch(folder.name):
                    continue
                s = folder.stat()
                if now - s.st_mtime >= self.days * 86400:
                    shutil.rmtree(folder, ignore_errors=True)
                else:
                    kept.append((s.st_mtime, sum(p.stat().st_size for p in folder.iterdir()), folder))
        total = sum(size for _, size, _ in kept)
        count = len(kept)
        for _, size, folder in sorted(kept):
            if total <= self.limit and count <= self.most:
                break
            total -= size
            count -= 1
            shutil.rmtree(folder, ignore_errors=True)
