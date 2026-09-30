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
import secrets
import shutil
import threading
import time
from collections import deque
from dataclasses import dataclass, fields
from pathlib import Path


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
    cache_mb: int = 300  # previews kept, shared by everyone who makes the same choices
    downloads_mb: int = 1024  # recordings waiting to be downloaded
    download_hours: float = 24.0  # how long a recording waits
    timeout: float = 30.0  # seconds a connection may send nothing before it's closed
    connections: int = 64  # connections served at once

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
        self.hour = {"records": Counter(3600), "previews": Counter(3600), "takes": Counter(3600)}
        self.minute = Counter(60)

    def who(self, text: str) -> str:
        return hmac.new(self.salt, text.encode("utf-8", "replace"), "sha256").hexdigest()[:20]

    def request(self, ip: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        who = self.who("ip:" + ip)
        with self.lock:
            wait = self.minute.wait(who, self.limits.requests, now)
            if wait:
                raise Limited("Too many requests from your address at once; wait a moment.", wait)
            self.minute.add(who, now)

    def render(self, kind: str, visitor: str, ip: str, now: float | None = None) -> None:
        """A new render for this visitor ("records": a whole song, "previews": a section; "takes": a take sung in
        the browser, measured in the same queue), counted if it's allowed; else Limited, saying why and when."""
        now = time.monotonic() if now is None else now
        mine, theirs = self.who("v:" + visitor), self.who("ip:" + ip)
        each, shared = getattr(self.limits, kind), getattr(self.limits, kind + "_ip")
        what = {"records": "whole songs", "previews": "new sections", "takes": "takes measured"}[kind]
        with self.lock:
            counter = self.hour[kind]
            wait = counter.wait(mine, each, now)
            if wait:
                raise Limited(f"You've had {each} {what} made this hour, as many as one person may while "
                              f"everyone shares one renderer. Try again in {about(wait)}; what's made already "
                              f"plays at once.", wait)
            wait = counter.wait(theirs, shared, now)
            if wait:
                raise Limited(f"Your network has had {shared} {what} made this hour, as many as one address may "
                              f"while everyone shares one renderer. Try again in {about(wait)}.", wait)
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


def access_line(method: str, path: str, code: int, size: int, seconds: float) -> str:
    """One request, as the log keeps it: when, what, how it was answered. Never who."""
    when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return f"{when} {method} {path[:120]} {code} {size} {seconds * 1000:.0f}ms"
