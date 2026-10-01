"""The studio open to anyone (`songbird studio --public`): the limits that let strangers share one
renderer fairly, the store their recordings wait in to be downloaded, and what it keeps of them.

What it keeps of a visitor is counts: how many songs and sections they (a random id in a cookie) and
their address had made in the last hour, and how many requests their address sent in the last minute,
each under a keyed hash whose key lives only in memory, so an address can't be read back from them and
they are gone when the studio stops. The access log says what was asked and how it was answered,
never by whom (no address, no cookie, no query, no body). docs/WEB-STUDIO.md has the design.
"""

from __future__ import annotations

import contextlib
import hmac
import ipaddress
import os
import re
import secrets
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, field, fields
from pathlib import Path


# ---------------------------------------------------------------- a whole song's memory
#
# A whole render's peak memory grows with the song's length, and with who plays it. Measured on 30 September, after
# the heaviest parts were made lean (docs/PERFORMANCE.md, "The heaviest parts"; tools/render_memory.py: H with each
# style's own band, and the ballad, chamber and the kit's bands at 3 to 8 minutes; two threads, MallocLargeCache=0,
# which hands freed arrays back as Linux does; docs/WEB-STUDIO.md, "A whole song's memory"), it is about BASE_MB and
# so many MB for every second of the song. A part's rate is the lightest band's it plays in (the lullaby's 4.7, the
# songwriter's 5.0), and a band none of whose parts reaches its own rate that way gives it to its own part (the
# kit its band's, the steel country's). A part in none of those bands: the ballad's band with it playing the whistle's
# line or the drum's strokes (tools/part_memory.py), and a little more. A song's rate is its heaviest part's, and
# MARGIN more; every measurement is at or under it (tests/test_studio_public.py, MEASURED).

BASE_MB = 300  # the program and its imports, and the page's work beside a render
RATES = {  # MB for a second of the song, on two threads
    # the old 78's band (2026-09-30: a voice, a piano or a guitar, a fiddle, mono) is the lightest these play in: 3.3
    # MB a second measured; 4.5 keeps every measurement at or under its estimate and within 1.3 of it
    "voice": 4.5, "piano": 4.5, "guitar": 4.5, "fiddle": 4.5,
    "chop": 4.7, "harp": 4.7, "celesta": 4.7, "musicbox": 4.7, "synthpad": 4.7,  # chop: house's sung hook
    "bass": 5.0, "harmonica": 5.0,
    "claps": 5.6, "stomps": 5.6, "concertina": 5.6,
    "cello": 5.8, "strings": 5.8, "drone": 5.9, "vibes": 5.9,
    "drummachine": 6.2, "synthbass": 6.2, "epiano": 6.2,
    "slide": 6.4, "synthlead": 6.4, "arp": 6.4, "banjo": 6.6, "mandolin": 6.6,
    "lute": 7.0, "drum": 7.0, "whistle": 7.0,
    "kit": 7.1, "organ": 7.1, "ebass": 7.1, "tambourine": 7.1, "electric": 7.2, "glock": 7.2,
    "steel": 7.5,
    # in no band as the program sings H: measured in the ballad's (tools/part_memory.py), 0.3 more
    "accordion": 7.2, "cajon": 6.8, "chip": 7.2, "chip-bass": 7.0, "chip-drums": 7.7, "drums-808": 6.3,
    "drums-909": 7.2, "electric-crunch": 6.9, "electric-tremolo": 7.0, "epiano-reed": 6.8, "glockenspiel": 7.2,
    "harmonium": 6.9, "marimba": 6.9, "music-box": 7.1, "nylon": 6.9, "shaker": 6.4, "sub-bass": 6.9,
    "synth-arp": 6.9, "synth-bass": 6.9, "synth-pad": 6.9, "synth-solo": 6.9, "ukulele": 6.9, "vibraphone": 6.9,
    "viola": 7.0,
    "melodica": 7.4,  # (2026-09-30: 5.9 to 7.4 over three runs; the highest)
    "pipeorgan": 4.7,  # a hymn's (2026-09-30, night): H's hymn with the lead alone 4.5 (with voices the choir sets it)
}
UNMEASURED = 7.7  # a part never measured (one added since): the heaviest rate above
MARGIN = 1.05
CHOIR = 1.0  # a voice from before, more than the voice's (not measured apart: a guess)
STEM = 0.71  # a stereo stem held whole until the stems' zip is packed (float64, 44.1 kHz), for each part
MORE_THREADS = 0.12  # each thread past two makes this much more at once (H's seed: 1.33 GB on 2, 1.92 on 6)
# a browser's heap (renderer.js: one thread, wasm32) is 2.0 to 2.3 GiB for H with a voice before it, about 1.7 times
# the estimate here; Chrome's ceiling is 4 GiB (4295 MB), and a whole song made in a browser is kept under BROWSER_MB
# of it (a ballad of about 4.4 minutes; one past it goes to the server, or is refused with the same sentence)
BROWSER_MB = 3800
BROWSER_FACTOR = 1.7


def render_rate(parts, threads: int = 2) -> float:
    """MB for a second of a song these parts play (the score's part names), on `threads`."""
    rates = [CHOIR + RATES["voice"] if p.startswith("choir") else RATES.get(p, UNMEASURED) for p in parts]
    return max(rates or [RATES["voice"]]) * MARGIN * (1.0 + MORE_THREADS * max(0, threads - 2))


def render_mb(seconds: float, parts, threads: int = 2, stems: bool = False) -> float:
    """About the most memory a whole render of a song this long, with these parts, takes (MB); `stems`: every part
    made alone and held for the zip, after the recording."""
    parts = sorted(set(parts))
    return BASE_MB + seconds * (render_rate(parts, threads) + (STEM * len(parts) if stems else 0.0))


def memory_mb() -> int:
    """The memory this studio is given, in MB: STUDIO_MEMORY as Docker takes it (2500m, 2g; the compose passes it
    in), else the container's own limit (cgroup v2), else 2500 (the VPS's)."""
    text = os.environ.get("STUDIO_MEMORY", "").strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kmg]?)b?", text)
    if match:
        scale = {"": 1 / 2**20, "k": 1 / 1024, "m": 1, "g": 1024}[match.group(2)]
        return int(float(match.group(1)) * scale)
    with contextlib.suppress(OSError, ValueError):
        return int(Path("/sys/fs/cgroup/memory.max").read_text().strip()) // 2**20
    return 2500


def default_render_mb() -> int:
    """What a whole render may take: the studio's memory, less 400 MB for everything else (the server, the pages'
    requests, a take or two on its way)."""
    return max(500, memory_mb() - 400)


def minutes(seconds: float) -> str:
    """A song's length in words: "6.9 minutes"."""
    return f"{seconds / 60:.1f}".rstrip("0").rstrip(".") + " minutes"


class TooLong(ValueError):
    """A whole song too long (with its players) for this studio to make in one go: said to the person."""


def too_long(seconds: float, most: float, browser: bool | None) -> str:
    """Why a whole song isn't made here, in a sentence: `most`, the longest it makes with these players; `browser`,
    whether a browser may make it instead (None: the studio has none to offer)."""
    if browser:
        return (f"This version is {minutes(seconds)} long, too long for this small server to make in one go (about "
                f"{minutes(most)} at most with these players): make it in your browser, or shorten it (fewer "
                "verses, a quicker tempo).")
    where = "this small server" if browser is None else "this small server or a browser"
    return (f"This version is {minutes(seconds)} long, too long for {where} to make in one go (about "
            f"{minutes(most)} at most with these players): shorten it (fewer verses, a quicker tempo).")


@dataclass
class Limits:
    """A public studio's limits (--limit NAME=VALUE; the names with - for _)."""
    records: int = 4  # whole songs made for one visitor an hour (hearing the whole song is making it)
    records_ip: int = 10  # ... for one address (a household or a school shares one)
    previews: int = 60  # sections made for one visitor an hour
    previews_ip: int = 150
    takes: int = 12  # takes sung in the browser and measured, for one visitor an hour (--web-singing)
    takes_ip: int = 30
    requests: int = 600  # requests from one address a minute (the page asks every half second while it waits)
    queue: int = 12  # renders waiting at once, for everyone
    queue_ip: int = 3  # ... from one address (an IPv6 one by its /64), however many visitors (or none) it holds
    cache_mb: int = 300  # previews kept, shared by everyone who makes the same choices
    downloads_mb: int = 1024  # recordings waiting to be downloaded
    download_hours: float = 24.0  # how long a recording waits
    timeout: float = 30.0  # seconds a connection may send nothing before it's closed
    connections: int = 64  # connections served at once
    connections_ip: int = 16  # ... from one address (a page asks several things at once, a player several ranges)
    send_kb: int = 16  # the slowest a download is sent (KB a second, over its whole time, after a minute's grace)
    opens: int = 12  # versions someone was sent, opened by one visitor an hour (each read in a process of its own)
    opens_ip: int = 40
    upload_mb: int = 64  # the largest file taken as a version to open (a rendition is 15 to 20 MB)
    versions_mb: int = 256  # versions opened, kept as data (a record and a song, about 150 KB each)
    version_days: float = 30.0  # how long a version is kept after it was last opened (its link works that long)
    # the most a whole render may take, MB (the container's memory less 400): a whole song estimated past it (its
    # length and players: render_mb, above) is refused before it's queued, and made in a browser where one can
    render_mb: int = field(default_factory=default_render_mb)

    @classmethod
    def parse(cls, items: list[str] | None) -> "Limits":
        limits = cls()
        known = {f.name: f.type for f in fields(cls)}
        for item in items or []:
            name, _, value = item.partition("=")
            name = name.strip().replace("-", "_")
            if name not in known or not value.strip():
                raise ValueError(f"--limit takes NAME=NUMBER, NAME one of {', '.join(names())}; not {item!r}")
            try:
                number = float(value) if known[name] == "float" else int(value)
            except ValueError:
                raise ValueError(f"--limit {name.replace('_', '-')} takes a number, not {value!r}") from None
            if number <= 0:
                raise ValueError(f"--limit {name.replace('_', '-')} must be more than 0")
            setattr(limits, name, number)
        return limits

    def view(self) -> dict:
        """What the page tells a visitor."""
        return {"records": self.records, "previews": self.previews, "download_hours": self.download_hours}


def names() -> list[str]:
    return [f.name.replace("_", "-") for f in fields(Limits)]


class Limited(Exception):
    """Asked for more than a public studio gives one person: said to them, with when to try again."""

    def __init__(self, message: str, retry: float):
        super().__init__(message)
        self.retry = max(1, int(retry + 0.999))


def about(seconds: float) -> str:
    """A wait as a person says it: "a minute", "about 7 minutes", "about 2 hours"."""
    minutes = max(1, round(seconds / 60))
    if minutes == 1:
        return "a minute"
    if minutes < 90:
        return f"about {minutes} minutes"
    return f"about {round(minutes / 60)} hours"


class Counter:
    """How many times each someone did a thing in the last `span` seconds."""

    def __init__(self, span: float):
        self.span = span
        self.seen: dict[str, deque] = {}

    def recent(self, who: str, now: float) -> deque:
        times = self.seen.get(who)
        if times is None:
            return deque()
        while times and times[0] <= now - self.span:
            times.popleft()
        if not times:
            del self.seen[who]
        return times

    def wait(self, who: str, limit: int, now: float) -> float:
        """Seconds until one more is allowed; 0 if it is now."""
        times = self.recent(who, now)
        return 0.0 if len(times) < limit else times[len(times) - limit] + self.span - now

    def add(self, who: str, now: float) -> None:
        self.seen.setdefault(who, deque()).append(now)

    def purge(self, now: float) -> None:
        for who in list(self.seen):
            self.recent(who, now)


class Gate:
    """The per-visitor and per-address counts, under a key that is never written down."""

    def __init__(self, limits: Limits):
        self.limits = limits
        self.salt = secrets.token_bytes(16)
        self.lock = threading.Lock()
        self.hour = {"records": Counter(3600), "previews": Counter(3600), "takes": Counter(3600), "opens": Counter(3600)}
        self.minute = Counter(60)

    def who(self, text: str) -> str:
        return hmac.new(self.salt, text.encode("utf-8", "replace"), "sha256").hexdigest()[:20]

    def request(self, ip: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        who = self.who("ip:" + network(ip))
        with self.lock:
            wait = self.minute.wait(who, self.limits.requests, now)
            if wait:
                raise Limited("Too many requests from your address at once; wait a moment.", wait)
            self.minute.add(who, now)

    def render(self, kind: str, visitor: str, ip: str, now: float | None = None, count: bool = True) -> None:
        """A new render for this visitor ("records": a whole song, "previews": a section; "takes": a take sung in
        the browser, measured in the same queue; "opens": a version someone was sent, read), counted if it's
        allowed (or, with `count` False, only asked about); else Limited, saying why and when."""
        now = time.monotonic() if now is None else now
        mine, theirs = self.who("v:" + visitor), self.who("ip:" + network(ip))
        each, shared = getattr(self.limits, kind), getattr(self.limits, kind + "_ip")
        what = {"records": "whole songs", "previews": "new sections", "takes": "takes measured",
                "opens": "versions opened"}[kind]
        made, after = ("", "") if kind == "opens" else (" made", "; what's made already plays at once")
        with self.lock:
            counter = self.hour[kind]
            wait = counter.wait(mine, each, now)
            if wait:
                raise Limited(f"You've had {each} {what}{made} this hour, as many as one person may while "
                              f"everyone shares one renderer. Try again in {about(wait)}{after}.", wait)
            wait = counter.wait(theirs, shared, now)
            if wait:
                raise Limited(f"Your network has had {shared} {what}{made} this hour, as many as one address may "
                              f"while everyone shares one renderer. Try again in {about(wait)}.", wait)
            if count:
                counter.add(mine, now)
                counter.add(theirs, now)

    def purge(self) -> None:
        now = time.monotonic()
        with self.lock:
            for counter in (*self.hour.values(), self.minute):
                counter.purge(now)


class Downloads:
    """Recordings waiting to be downloaded: each kept `hours` after it was last asked for, the oldest going
    first when they pass `limit` bytes. A recording is named by what it is (its render's key), as a preview
    is, so asking again for the same one keeps one file."""

    def __init__(self, folder: Path, limit: int, hours: float):
        self.folder, self.limit, self.hours = Path(folder), limit, hours
        self.folder.mkdir(parents=True, exist_ok=True)

    def keep(self, src: Path, key: str) -> Path:
        dst = self.folder / f"{key}.flac"
        if not dst.exists():
            tmp = self.folder / f"{key}.part"
            with contextlib.suppress(OSError):
                tmp.unlink()
            try:
                os.link(src, tmp)  # the cache's file, not a second copy
            except OSError:
                shutil.copyfile(src, tmp)
            tmp.replace(dst)
        os.utime(dst)
        self.prune()
        return dst

    def path(self, key: str) -> Path | None:
        p = self.folder / f"{key}.flac"
        with contextlib.suppress(OSError):
            if time.time() - p.stat().st_mtime < self.hours * 3600:
                return p
        return None

    def prune(self) -> None:
        now = time.time()
        kept = []
        for p in self.folder.glob("*.flac"):
            with contextlib.suppress(OSError):
                s = p.stat()
                if now - s.st_mtime >= self.hours * 3600:
                    p.unlink()
                else:
                    kept.append((s.st_mtime, s.st_size, p))
        total = sum(size for _, size, _ in kept)
        for _, size, p in sorted(kept):
            if total <= self.limit:
                break
            total -= size
            with contextlib.suppress(OSError):
                p.unlink()


NEAR = [ipaddress.ip_network(n) for n in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128",
                                           "fc00::/7")]  # this machine, and private networks (a container's)


def client_ip(peer: str, headers, header: str | None) -> str:
    """Who is asking: the connection's address; or, behind a proxy on this machine or its private network
    (cloudflared), the address the proxy names in `header` (CF-Connecting-IP), when one was configured.
    A header from anywhere else is not believed."""
    if header:
        with contextlib.suppress(ValueError):
            near = ipaddress.ip_address(peer.split("%")[0])
            near = getattr(near, "ipv4_mapped", None) or near
            if any(near in net for net in NEAR if net.version == near.version):
                return str(ipaddress.ip_address((headers.get(header) or "").strip()))
    return peer


def network(ip: str) -> str:
    """An address as the limits count it: an IPv4 address itself; an IPv6 one by its /64, the network one
    household or phone is given (and can pick any address in)."""
    with contextlib.suppress(ValueError):
        address = ipaddress.ip_address(ip.split("%")[0])
        if address.version == 6 and address.ipv4_mapped is None:
            return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return ip


def access_line(method: str, path: str, code: int, size: int, seconds: float) -> str:
    """One request, as the log keeps it: when, what, how it was answered. Never who, and never a version's id
    (/v/<id>: its link is the only key to it)."""
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path = re.sub(r"^/v/[^/?#]*", "/v/…", path)
    return f"{when} {method} {path[:120]} {code} {size} {seconds * 1000:.0f}ms"
