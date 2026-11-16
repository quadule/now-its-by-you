"""Invitations for singers anywhere, and what they send back (dev-only).

    uv run python tools/invite.py new 3 --note "choir, Tuesday"       # three personal links, open 7 days
    uv run python tools/invite.py new --people 40 --note "the list"   # one group link, for up to 40 people
    uv run python tools/invite.py new --people 20 --word family      # ...at a word you can say and type: /i/family
    uv run python tools/invite.py list                                # every invitation: who joined, their takes
    uv run python tools/invite.py singers [--emails]                  # everyone who joined, and what they were mailed
    uv run python tools/invite.py sync [--watch 60]                   # the site and this computer, in step
    uv run python tools/invite.py mail [--open]                       # who needs an email, ready to paste
    uv run python tools/invite.py mail --sent                         # ...and once they're sent
    uv run python tools/invite.py purge                               # once DELETE_BY has passed
    uv run python tools/invite.py revoke <token>                      # close one
    uv run python tools/invite.py fetch                               # the old way, for first-version links

Talks to the site's admin API (web/sing/src/worker.js) at https://songbird.quadule.com,
or wherever --url or SONGBIRD_SING_URL says (http://127.0.0.1:8787 under `wrangler dev`).
The admin token comes from SONGBIRD_SING_ADMIN, or else from `secrets get
songbird-sing-admin`, and is never printed.

Everyone who joins gets a private page (/y/<sid>) where they can listen to what
they sent, download it, delete it, or withdraw until singing closes; recordings
are deleted by DELETE_BY (the release they agreed to: web/sing/consent.md), so
takes stay on the site until then. sync, in this order: does here what singers
deleted (the audio goes; its sidecar and the numbers measured from it stay) or
withdrew (everything of theirs goes: takes, words, versions, phrasing, measured
numbers); keeps new takes the way the recording page keeps one (tools/takes.py), with
where in the song each was sung; keeps the words people send
(recordings/words/<sid>.json); makes each singer's version of the song and their
vocals (tools/versions.py) and puts them on their page; and once DELETE_BY has
passed, purges. A person's takes share one folder: the one already holding them,
else the name they gave, unless anyone else's takes are there, when the first six
characters of their id follow it; with no name, the invitation's note (or
"singer") and those characters. Two people never share a folder.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import datetime as dt
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import takes as K  # noqa: E402  (tools/takes.py)

SITE = "https://songbird.quadule.com"  # where singing is live (also at songbird-sing.quadule.workers.dev)
SECRET = "songbird-sing-admin"  # its name in the artist's secrets tool
TIMING = ("shift_ms", "auto_ms", "device_ms", "decode_ms", "out_ms", "in_ms")
HOW = ("aec",)  # how it was sung: without headphones, the guide taken out of the microphone
PLACE = ("spec", "from_s", "to_s", "section", "label")  # where in the song a take was sung, as its page said
LOCAL = ("localhost", "127.0.0.1", "::1")
STALE = 600  # seconds after which half a take on the server is left over, not still arriving
SID = re.compile(r"^[A-Za-z0-9_-]{24}$")  # a singer's id (and an invitation's token): it opens their page
TOKENISH = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24}(?![A-Za-z0-9_-])")
NOT_SINGERS = tuple(getattr(K, "NOT_SINGERS", ("guides", "words")))  # folders in recordings/ that aren't a singer's
RESERVED = {"someone", "everyone", *NOT_SINGERS}  # names a singer's folder can't have (see folder_for)
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}\.(mp3|wav)$")  # a file the site keeps for a singer
KINDS = {".mp3": "audio/mpeg", ".wav": "audio/wav"}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


class Failed(SystemExit):
    """A request the site refused (status: its HTTP status) or never got (status None)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Site:
    """The site's admin API."""

    def __init__(self, url: str, token: str):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in LOCAL):
            raise SystemExit(f"{url}: the admin token only travels over https (or plain http to this computer)")
        self.url = url.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None, raw: bool = False):
        data = json.dumps(body).encode() if body is not None else None
        return self.send(method, path, data, "application/json", raw)

    def put(self, path: str, data: bytes, kind: str) -> dict:
        """A file's bytes, sent as they are (a singer's version of the song, say)."""
        return self.send("PUT", path, data, kind)

    def send(self, method: str, path: str, data: bytes | None, kind: str, raw: bool = False):
        req = urllib.request.Request(f"{self.url}{path}", data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": kind,
                                              "User-Agent": "songbird-invite"})
        where = short(f"{method} {path.split('?')[0]}")  # never a whole singer id: it opens their page
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read()).get("message", "")
            except (OSError, ValueError, AttributeError):
                message = ""
            raise Failed(f"{where}: {e.code} {message}".strip(), e.code) from None
        except urllib.error.URLError as e:
            raise Failed(f"can't reach {self.url}: {e.reason}") from None
        except (OSError, http.client.HTTPException) as e:  # cut off halfway: a timeout, a dropped connection
            raise Failed(f"{where}: {e or type(e).__name__}") from None
        if raw:
            return payload
        try:
            return json.loads(payload)
        except ValueError:
            raise Failed(f"{where}: the site's answer wasn't JSON") from None


def admin_token() -> str:
    """The admin token: SONGBIRD_SING_ADMIN, else the artist's secrets tool."""
    token = os.environ.get("SONGBIRD_SING_ADMIN", "").strip()
    if token:
        return token
    try:
        got = subprocess.run(["secrets", "get", SECRET], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        got = None
    if got is None or got.returncode or not got.stdout.strip():
        raise SystemExit(f"no admin token: set SONGBIRD_SING_ADMIN, or keep it as {SECRET!r} in your secrets tool "
                         "(the same value as `wrangler secret put ADMIN_TOKEN`)")
    return got.stdout.strip()


def short(text: str) -> str:
    """Text with every invitation token and singer id in it cut to six characters: whole, either opens a page."""
    return TOKENISH.sub(lambda m: m[0][:6] + "…", text)


def plain(text) -> str:
    """What a singer typed (a name, an address), safe to print: no control characters, which a terminal acts on."""
    return "".join(c for c in str(text or "") if unicodedata.category(c) != "Cc").strip()


def instant(iso: str) -> dt.datetime:
    """A time as the site gives one (2026-09-26T23:15:01.000Z, or with an offset)."""
    t = dt.datetime.fromisoformat(iso)
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def after(a: str | None, b: str | None) -> bool:
    """Whether time a is later than time b; not if either is unknown."""
    return bool(a and b) and instant(a) > instant(b)


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def when(iso: str) -> str:
    """2026-10-03T08:10:19.306Z -> Oct 3, 2026, 10:10 (local time)."""
    t = instant(iso).astimezone()
    return f"{t:%b} {t.day}, {t:%Y, %H:%M}"


def day(iso: str) -> str:
    """2026-09-30T20:00:00-07:00 -> September 30 (where the date was set)."""
    t = dt.datetime.fromisoformat(iso)
    return f"{MONTHS[t.month - 1]} {t.day}"


def moment(iso: str) -> str:
    """2026-09-27T22:00:00-07:00 -> Sunday, September 27 at 10 PM Pacific (where the time was set)."""
    t = dt.datetime.fromisoformat(iso)
    clock = f"{t.hour % 12 or 12}" + (f":{t.minute:02d}" if t.minute else "")
    return f"{DAYS[t.weekday()]}, {day(iso)} at {clock} {'AM' if t.hour < 12 else 'PM'}{zone(t)}"


def zone(t: dt.datetime) -> str:
    off = t.utcoffset()
    if off is None:
        return ""
    if off in (dt.timedelta(hours=-7), dt.timedelta(hours=-8)):  # daylight or standard time
        return " Pacific"
    minutes = round(off.total_seconds() / 60)
    return " UTC" + (f"{'+' if minutes > 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}" if minutes else "")


# ---------- files here (every path from K.ROOT and K.RECORDINGS as they are when asked, so tests can move them)

def words_dir() -> Path:
    return K.RECORDINGS / "words"


def versions_file() -> Path:
    return K.RECORDINGS / ".versions.json"


def mail_file() -> Path:
    return K.RECORDINGS / ".mail.json"


def phrasing_path(song: str, folder: str) -> Path:
    """A folder's phrasing, as the recording page writes it (tools/recorder.py)."""
    return K.ROOT / "renders" / "phrasing" / f"{song}.{folder}.json"


def karaoke_render(song: str, folder: str) -> Path:
    """The machine singing a folder's way, as the recording page renders it (tools/recorder.py)."""
    return K.ROOT / "renders" / f"{song}.karaoke.{folder}.flac"


def versions_root() -> Path:
    return K.ROOT / "renders" / "versions"


def rel(path: Path) -> str:
    """A path as the records keep it: from the repo, if it's in it."""
    for p in (Path(path), Path(path).resolve()):
        for root in (K.ROOT, K.ROOT.resolve()):
            if p.is_relative_to(root):
                return p.relative_to(root).as_posix()
    return Path(path).resolve().as_posix()


def here(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else K.ROOT / p


def measurements(wav: Path) -> list[Path]:
    """Where the numbers measured from a take are kept: renders/measured/<its path in the repo, / as __>.json
    (tools/phrasing.py measured()), and the aligner's under renders/measured/mfa/ (tools/align.py); takes.caches
    says so itself where it's there."""
    found = []
    if hasattr(K, "caches"):  # tools/takes.py's own (another agent's)
        with contextlib.suppress(Exception):
            found = [Path(p) for p in K.caches(K.load(wav))]
    stem = rel(wav).lstrip("/").replace("/", "__").removesuffix(".wav") + ".json"
    base = K.ROOT / "renders" / "measured"
    return list(dict.fromkeys([*found, base / stem, base / "mfa" / stem]))


def read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def write(path: Path, data) -> None:
    """A record, whole or not at all (a round cut short never leaves half a file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_text(json.dumps(data, indent=1) + "\n")
    os.replace(part, path)


def mark(side: Path, **fields) -> None:
    """Add to a take's sidecar what it doesn't already say (as tools/takes.py writes one)."""
    info = json.loads(side.read_text())
    new = {k: v for k, v in fields.items() if k not in info}
    if new:
        side.write_text(json.dumps({**info, **new}, indent=1) + "\n")


@contextlib.contextmanager
def whole():
    """Ctrl-C waits until what's inside is done: a take, or a deletion, is never left halfway."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    caught = []
    before = signal.signal(signal.SIGINT, lambda *_: caught.append(True))
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, before if before is not None else signal.default_int_handler)
        if caught:
            raise KeyboardInterrupt


@contextlib.contextmanager
def alone():
    """One sync (or purge, or fetch) at a time on this computer: two would keep the same take twice."""
    import fcntl

    K.RECORDINGS.mkdir(parents=True, exist_ok=True)
    with open(K.RECORDINGS / ".sync.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another sync, purge or fetch is running on this computer: let it finish, or stop it") from None
        yield


def sidecars():
    """Every take's sidecar here (not recordings/guides/ or recordings/words/), and what it says."""
    skip = {K.GUIDES, *(K.RECORDINGS / name for name in NOT_SINGERS)}
    for side in sorted(K.RECORDINGS.glob("*/*.json")):
        if side.parent in skip or side.parent.name.startswith("."):
            continue
        info = read(side, None)
        if isinstance(info, dict):
            yield side, info


def fetched() -> dict[str, K.Take]:
    """The takes already fetched here, by their id on the server (with their audio or not)."""
    return {info["remote"]: K.load(side.with_suffix(".wav")) for side, info in sidecars() if info.get("remote")}


# ---------- what sync says

class Say:
    """sync's lines, one per thing done: in a watch, each after the time, and on a line of its own after the
    quiet rounds' dots."""

    clock = False  # put the time first (a watch)
    dots = False  # the last thing printed was a quiet round's dot
    lines = 0  # how many lines so far


def say(line: str) -> None:
    if Say.dots:
        print()
        Say.dots = False
    print(f"{time.strftime('%H:%M:%S')}  {line}" if Say.clock else line, flush=True)
    Say.lines += 1


def memory() -> dict:
    """What a run of sync keeps from round to round: what it has said once, what failed (not tried again)."""
    return {"said": set(), "failed": set()}


# ---------- invitations and singers

def new(site: Site, count: int, note: str, days: int, limit: int, people: int = 1, word: str | None = None) -> list[dict]:
    """count invitations: personal links (people 1), or group links one person can post (up to people each);
    with a word, one link at that word (https://songbird.quadule.com/i/family), short enough to say aloud and
    type, and so guessable: for family and friends."""
    body = {"count": count, "note": note, "days": days, "limit": limit, "people": people}
    if word is not None:
        body["word"] = word
    made = site.call("POST", "/api/admin/invites", body)["invites"]
    for inv in made:
        print(inv["url"])
    if made:
        size = made[0].get("people", people)
        each = "each " if len(made) > 1 else ""
        kind = f"{each}a group link for up to {size} people" if size > 1 else f"{each}a personal link"
        print(f"open until {when(made[0]['expires'])}, up to {made[0]['limit']} takes per singer; {kind}" +
              (f"; note: {made[0]['note']}" if made[0]["note"] else ""), file=sys.stderr)
    return made


def listing(site: Site) -> list[dict]:
    invites = site.call("GET", "/api/admin/invites")["invites"]
    if not invites:
        print("no invitations yet: make some with `new`")
    for inv in invites:
        print(f"{inv['state']:8s} joined {inv.get('joined', 0):3d}/{inv.get('people', 1):<4d} takes {inv.get('takes', 0):3d}  "
              f"until {when(inv['expires']):22s} {inv.get('note') or '-':24.24s} {inv['url']}")
    return invites


def revoke(site: Site, token: str) -> None:
    site.call("POST", f"/api/admin/revoke/{urllib.parse.quote(token)}")
    print(f"revoked {token[:6]}…")


def everyone(site: Site, emails: bool = False) -> list[dict]:
    """Every singer who joined, oldest first (the site lists them a page at a time); their emails only if asked."""
    out, cursor, seen = [], None, set()
    while True:
        query = {**({"emails": "1"} if emails else {}), **({"cursor": cursor} if cursor else {})}
        got = site.call("GET", "/api/admin/singers" + (f"?{urllib.parse.urlencode(query)}" if query else ""))
        out += got.get("singers") or []
        cursor = got.get("cursor")
        if not cursor or cursor in seen:
            return out
        seen.add(cursor)


def singers(site: Site, emails: bool = False) -> list[dict]:
    """Every singer: when they joined, their state, set, takes, words and files, which emails they've had,
    their name and their page; their email address only with emails."""
    people = everyone(site, emails)
    if not people:
        print("no one has joined yet")
    for s in people:
        state = "done" if s.get("done") and s.get("state") == "open" else s.get("state", "?")
        mailed = ",".join(k for k in ("link", "ready") if (s.get("sent") or {}).get(k)) or "-"
        print(f"{when(s['created']) if s.get('created') else '-':22s} {state:9s} set {s.get('set') or '-':4s} "
              f"{s.get('takes', 0):3d} takes {s.get('words', 0):2d} words {len(s.get('files') or []):2d} files  "
              f"mailed {mailed:10s} {plain(s.get('name')) or '-':20.20s} {s.get('page', '')}" +
              (f"  {plain(s.get('email')) or '-'}" if emails else ""))
    return people


# ---------- whose folder

def holders(folder: Path) -> set:
    """Whose takes a folder holds: each take's person (or sid); None for a take with neither (sung here, or from
    a first-version invitation)."""
    found = set()
    for side in folder.glob("*.json"):
        info = read(side, {})
        found.add((info.get("person") or info.get("sid")) if isinstance(info, dict) else None)
    found |= {None for wav in folder.glob("*.wav") if not wav.with_suffix(".json").exists()}
    return found


def free(folder: str, person: str, song: str | None) -> bool:
    """Whether a person's takes may go in a folder of this name: none of anyone else's are there, and nothing
    else's phrasing (a reading, a synthetic voice) is named after it."""
    if folder in RESERVED:
        return False
    there = holders(K.RECORDINGS / folder)
    if there - {person}:
        return False
    return bool(there) or not (song and phrasing_path(song, folder).exists())


def homes() -> dict[str, str]:
    """Each person's folder here, as the singer's name it's made from: the one already holding their takes."""
    found = {}
    for side, info in sidecars():
        person = info.get("person") or info.get("sid")
        if person and person not in found:
            shown = (info.get("singer") or "").strip()
            found[person] = shown if shown and K.slug(shown) == side.parent.name else side.parent.name
    return found


def folder_for(person: str, name: str | None, song: str | None, note, known: dict | None = None) -> str:
    """Whose takes these are, as the singer's name their folder is made from (takes.slug): the folder already
    holding this person's takes (every page of one person's goes in one; known: homes(), if at hand); else the
    name they gave, if that folder is free; else the name and the first six characters of their id; with no name
    (or none a folder can be made of), the invitation's note (note(): asked for only now) or "singer", and those
    characters."""
    home = (homes() if known is None else known).get(person)
    if home:
        return home
    name = plain(name)[:60]  # a folder's name has room for a name, not an essay
    named = bool(name) and K.slug(name) != "someone"
    if named and free(K.slug(name), person, song):
        return name
    base = name if named else (note() or "singer")
    for tag in (person[:6], person[:12], person):
        who = f"{base} ({tag})"
        if free(K.slug(who), person, song):
            break
    return who


def invites_in(folder: str) -> set:
    """The invitations whose takes are in a singer's folder (None for takes sung here)."""
    found = set()
    for side in (K.RECORDINGS / folder).glob("*.json"):
        try:
            found.add(json.loads(side.read_text()).get("invite"))
        except ValueError:
            continue
    return found


def folder_name(info: dict, notes: dict, invite: str, singer: str | None) -> str:
    """For a first-version take: whose takes these are, as the singer's name their folder is made from
    (takes.slug): --singer as given; the name they gave, with the invitation after it if that folder holds anyone
    else's takes; with no name (or none a folder can be made of), the invitation's note or "singer", and the
    invitation."""
    if singer:
        return singer
    tag = invite[:6]
    name = (info.get("name") or "").strip()
    if name and K.slug(name) != "someone":
        return name if invites_in(K.slug(name)) <= {tag} else f"{name} ({tag})"
    return f"{notes.get(invite) or 'singer'} ({tag})"


# ---------- keeping takes and words

def missing(info: dict) -> str:
    """What a take needs to be measured that isn't here (its guide score, the release it was agreed under)."""
    gone = []
    if not K.guide_score(info["song"], info["guide"]):
        gone.append(f"its guide score {info['guide']}")
    release = (info.get("consent") or {}).get("text")
    if not (K.GUIDES / f"release.{release}.html").exists():
        gone.append(f"the release it was agreed under ({release})")
    return (f" ({' and '.join(gone)} not in {K.GUIDES.name}/ here: build the site on this machine, or copy them over)"
            if gone else "")


def keep_online(t: dict, info: dict, wav: bytes, who: str) -> K.Take:
    """A take from a singer's page, kept the way the recording page keeps one, with what the site knows of it."""
    name = plain(info.get("name"))
    sid = t.get("singer") or info.get("sid")
    received = info.get("received") or utc_now()
    extra = {k: info[k] for k in (*PLACE, *TIMING, *HOW) if k in info}
    # credit_as: the name they gave, the only one they may be credited by, and only if they said so
    with whole():
        return K.keep_sung(info["song"], who, wav, info["guide"], recorded=instant(received).astimezone().timetuple(),
                           mix=info.get("mix"), source="online", remote=t["id"], sid=sid,
                           person=info.get("person") or sid, invite=(info.get("invite") or "")[:6],
                           rate=info.get("rate"), received=received, credit=bool(info.get("credit") and name),
                           credit_as=name, consent=info.get("consent"), **extra)


def covered(events: list[dict], sid: str, remote: str, received: str | None) -> bool:
    """Whether what a singer deleted or withdrew takes in this take of theirs."""
    for e in events:
        if e.get("singer") != sid:
            continue
        if e.get("what") == "withdrawn" or e.get("take") == remote:
            return True
        if e.get("what") == "deleted" and not e.get("take") and not after(received, e.get("at")):
            return True
    return False


def keep_new(site: Site, events: list[dict], withdrawn: set, memo: dict) -> None:
    """New takes from singers' pages into recordings/ (they stay on the site for their singers)."""
    listed = site.call("GET", "/api/admin/takes")["takes"]
    have = {info["remote"] for _, info in sidecars() if info.get("remote")}
    notes = {}

    def note(token: str) -> str:  # an invitation's note: listing them costs the site's scarce KV reads, so once at most
        if "all" not in notes:
            notes["all"] = {inv["token"]: inv.get("note", "") for inv in site.call("GET", "/api/admin/invites")["invites"]}
        return notes["all"].get(token, "")

    known = None  # each person's folder, found when a take first needs one
    for t in sorted(listed, key=lambda t: t["id"].rsplit("/", 1)[-1]):  # as they arrived: the first Jo is "jo"
        sid = t.get("singer")
        if (t["id"] in have or not sid or not SID.match(sid) or sid in withdrawn or "json" not in t or "wav" not in t
                or t["id"] in memo["failed"] or any(e.get("take") == t["id"] for e in events)):
            continue  # here already; half a take (still arriving, or cut short); or its singer took it back
        label = t["id"].rsplit("/", 1)[-1]
        try:
            info = site.call("GET", f"/api/admin/take/{t['json']['key']}")
            if isinstance(info, dict) and info.get("sid") and not covered(events, sid, t["id"], info.get("received")):
                wav = b"" if t["wav"].get("size") != info.get("bytes") else \
                    site.call("GET", f"/api/admin/take/{t['wav']['key']}", raw=True)
        except Failed as e:
            if e.status == 404:  # deleted since it was listed: what its singer did arrives as an event
                continue
            raise
        if not isinstance(info, dict) or not info.get("sid"):
            memo["failed"].add(t["id"])
            say(f"a first-version take ({label}) is waiting on the site: `fetch` keeps those")
            continue
        if covered(events, sid, t["id"], info.get("received")):
            continue
        if len(wav) != info.get("bytes") or hashlib.sha256(wav).hexdigest() != info.get("sha256"):
            memo["failed"].add(t["id"])
            say(f"a take ({label}) doesn't match its sidecar: left on the site")
            continue
        person = info.get("person") or sid
        try:
            known = homes() if known is None else known
            who = folder_for(person, info.get("name"), info.get("song"), lambda i=info: note(i.get("invite") or ""), known)
            take = keep_online(t, info, wav, who)
        except (KeyError, TypeError, ValueError, OSError) as e:  # not a take this can keep: said once
            memo["failed"].add(t["id"])
            say(f"a take ({label}) can't be kept: {type(e).__name__}: {short(str(e))}")
            continue
        known[person] = who
        where = "the whole song" if info.get("section") is None else f"section {info['section']}"
        say(f"{take.rel}: {info.get('seconds', 0):.0f} s, {where}, {info.get('spec') or '-'}, "
            f"{info.get('mix')} guide{missing(info)}")


def keep_words(site: Site, withdrawn: set) -> None:
    """Words people sent (verses, suggestions) into recordings/words/<sid>.json, one file per singer, merged by
    key: {"sid", "person", "name", "credit", "words": [{"key", "at", "text", "release"}]}."""
    listed = site.call("GET", "/api/admin/words")["words"]
    known = {w.get("key") for f in words_dir().glob("*.json") for w in (read(f, {}) or {}).get("words", [])}
    new_ones: dict[str, list[str]] = {}
    for w in listed:
        sid = w.get("singer") or ""
        if w.get("key") not in known and SID.match(sid) and sid not in withdrawn:
            new_ones.setdefault(sid, []).append(w["key"])
    for sid, keys in new_ones.items():
        path = words_dir() / f"{sid}.json"
        data = read(path, None) or {"sid": sid, "person": sid, "name": "", "credit": False, "words": []}
        for key in keys:
            got = site.call("GET", f"/api/admin/word/{key}")
            data.update(person=got.get("person") or data.get("person") or sid, name=(got.get("name") or "").strip(),
                        credit=bool(got.get("credit")))
            data["words"].append({"key": key, "at": got.get("at"), "text": got.get("text"), "release": got.get("release")})
        data["words"].sort(key=lambda w: (w.get("at") or "", w["key"]))
        write(path, data)
        folder = next((side.parent.name for side, info in sidecars()
                       if (info.get("person") or info.get("sid")) == data["person"]), None)
        say(f"words from {folder or plain(data['name']) or f'a singer ({sid[:6]})'}: {len(keys)} new")


# ---------- what singers deleted or withdrew

def forget_audio(take: K.Take, at: str) -> bool:
    """A take whose singer deleted it: its WAV goes; its sidecar stays, saying when ("deleted"), and so do the
    numbers measured from it (tools/takes.py has no audio-only delete: it's done here). False if its audio had
    gone already."""
    if not take.path.exists():
        return False
    with whole():
        if take.sidecar().exists():
            mark(take.sidecar(), deleted=at)
        take.path.unlink(missing_ok=True)
    return True


def only(folder: Path, sid: str) -> bool:
    """Whether every take in a folder is this sid's (none from the same person's other pages, or anyone else's)."""
    return (all(read(side, {}).get("sid") == sid for side in folder.glob("*.json"))
            and all(wav.with_suffix(".json").exists() for wav in folder.glob("*.wav")))


def forget_singer(sid: str, site: Site | None = None) -> list[str]:
    """Everything here of a singer who withdrew (their sid): their takes (WAVs and sidecars) and the numbers
    measured from them; the phrasing of each folder they sang into, and everyone's, and the machine singing them
    (each holds their numbers, as do the choir's blends and its renders: the recording page makes them again from what's
    left); their words; and the versions made with their takes, from their person's other pages too when site is
    given (sync makes those again). Only this sid's takes: anyone else's in the same folder stay. What went, in
    words (nothing: it had all gone already)."""
    mine = [(side, info) for side, info in sidecars() if info.get("sid") == sid]
    folders = sorted({side.parent for side, _ in mine})
    songs = sorted({info.get("song") for _, info in mine if info.get("song")})
    went = []
    # what was made from their numbers first, their takes last: a withdrawal cut short is done again, whole
    numbers = [f for side, _ in mine for f in measurements(side.with_suffix(".wav")) if f.exists()]
    made = [f for song in songs for who in [*(folder.name for folder in folders), "everyone"]
            for f in (phrasing_path(song, who), karaoke_render(song, who)) if f.exists()]
    # the choir's blends hold their numbers too, as does any render the choir sang in, and a render's score
    made += sorted(({f for song in songs for f in phrasing_path(song, "*").parent.glob(f"{song}.choir.*.json")}
                    | {f for song in songs for f in karaoke_render(song, "*").parent.glob(f"{song}.karaoke.*.flac")
                       if read(f.with_suffix(".json"), {}).get("choir_phrasings")}) - set(made))
    made += [f for r in made if r.suffix == ".flac" for f in (r.with_suffix(".json"), r.with_suffix(".score.json"))
             if f.exists()]
    with whole():
        for f in numbers + made:
            f.unlink(missing_ok=True)
    if numbers:
        went.append(f"{len(numbers)} measurements")
    if made:
        went.append(f"{len(made)} phrasings and renders made with them")
    dropped = outdated(site, sid)
    if dropped:
        went.append(f"{dropped} versions")
    words = words_dir() / f"{sid}.json"
    if SID.match(sid) and words.exists():
        words.unlink()
        went.append("their words")
    for folder in folders:
        if only(folder, sid) and hasattr(K, "remove_singer"):  # tools/takes.py's own (another agent's): its
            with contextlib.suppress(TypeError, OSError):  # takes, phrasings, the recording page's renders, and the folder
                K.remove_singer(folder.name)
        for side in (side for side, _ in mine if side.parent == folder):
            if hasattr(K, "remove") and side.exists():  # its WAV, sidecar and caches (tools/takes.py's own)
                with contextlib.suppress(TypeError, OSError):
                    K.remove(K.load(side.with_suffix(".wav")))
            with whole():  # whatever's left of it: all of it, without tools/takes.py's own
                side.with_suffix(".wav").unlink(missing_ok=True)
                side.unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            folder.rmdir()  # empty now: it was named after them
        if not any(read(side, {}).get("source") == "online" for side in folder.glob("*.json")):
            shutil.rmtree(versions_root() / folder.name, ignore_errors=True)  # anything else made for them there
    if mine:
        went.insert(0, f"{len(mine)} takes")
    return went


def apply_gone(site: Site, events: list[dict]) -> set:
    """What singers deleted or withdrew, done here too. The site keeps every event, so each round does them all
    again: done already, nothing happens and nothing is said. The sids that withdrew."""
    withdrawn = {e.get("singer") for e in events if e.get("what") == "withdrawn"}
    by_sid: dict[str, list] = {}
    for side, info in sidecars():
        if info.get("sid"):
            by_sid.setdefault(info["sid"], []).append((side, info))
    made = versions()
    for e in events:
        sid, at = e.get("singer") or "", e.get("at")
        if not SID.match(sid) or not at:
            continue
        who = ", ".join(sorted({side.parent.name for side, _ in by_sid.get(sid, [])})) or f"a singer ({sid[:6]})"
        if e.get("what") == "withdrawn":
            if sid in by_sid or touching(made, sid) or (words_dir() / f"{sid}.json").exists():
                went = forget_singer(sid, site)
                if went:
                    say(f"{who} withdrew: removed {', '.join(went)}")
        elif e.get("what") == "deleted":
            for side, info in by_sid.get(sid, []):
                hit = info.get("remote") == e["take"] if e.get("take") else not after(info.get("received"), at)
                if hit and forget_audio(K.load(side.with_suffix(".wav")), at):
                    say(f"{rel(side.with_suffix('.wav'))}: deleted by its singer, so its audio is gone here too "
                        "(its sidecar and numbers stay)")
            if touching(made, sid) and outdated(site, sid, at):
                say(f"{who}: versions made before they deleted recordings are gone; they'll be made again from "
                    "what's left")
    return withdrawn


# ---------- versions of the song: one per person and spec, on each of their pages

def versions() -> dict:
    """The versions made here, by person and spec: {"takes": [the takes' ids on the site], "files": [{"path":
    from the repo, "name": on the site (or null)}], "dir": where they were made, "sids": [the pages they were put
    on], "at": the site's time when the round that made them began, "uploaded": whether every page has them}."""
    data = read(versions_file(), {})
    return data if isinstance(data, dict) else {}


def keep_versions(data: dict) -> None:
    write(versions_file(), {person: specs for person, specs in data.items() if specs})


def touches(made: dict, sid: str) -> bool:
    """Whether a version was put on this sid's page or made with its takes."""
    return sid in made.get("sids", []) or any(t.startswith(f"takes/{sid}/") for t in made.get("takes", []))


def touching(data: dict, sid: str) -> bool:
    return any(touches(made, sid) for specs in data.values() for made in specs.values())


def drop(made: dict) -> int:
    """A version's files, deleted here, and the folder it was made in. How many files there were."""
    n = 0
    for f in made.get("files", []):
        p = here(f["path"])
        if p.exists():
            p.unlink()
            n += 1
    d = here(made["dir"]) if made.get("dir") else None
    if d and d.is_relative_to(versions_root()) and d != versions_root():
        shutil.rmtree(d, ignore_errors=True)
        with contextlib.suppress(OSError):
            d.parent.rmdir()  # the person's folder of versions, once it holds no other spec's
    return n


def outdated(site: Site | None, sid: str, at: str | None = None) -> int:
    """Versions a singer's deleting (at: when) or withdrawing (at None) leaves stale: those made with their takes,
    or put on their page, before then. The site deleted their own page's files then, but a person's version is on
    every page of theirs and may hold what was deleted, so each goes, here and (given the site) from every page it
    was put on; sync makes them again from what's left. How many went."""
    data = versions()
    count = 0
    for specs in data.values():
        for spec, made in list(specs.items()):
            current = at and made.get("at") and not after(at, made["at"])  # made in a round that had done this
            if not touches(made, sid) or current:
                continue
            for page in made.get("sids", []) if site else []:
                for f in made.get("files", []):
                    if f.get("name"):
                        try:
                            site.call("DELETE", f"/api/admin/file/{page}/{urllib.parse.quote(f['name'])}")
                        except Failed as e:
                            if e.status is None:  # the site wasn't reached: the next round tries again
                                raise
            drop(made)
            del specs[spec]
            keep_versions(data)
            count += 1
    return count


def make_versions(folder: Path, spec: str, takes: list[K.Take]) -> list[Path]:
    """A person's version of the song for one spec (their takes in the sections they sang, the machine's lead
    elsewhere, mastered, as MP3) and their vocals alone (WAV), made by tools/versions.py (another agent's,
    imported only now) in renders/versions/<folder>/<spec>/; the files made. ValueError: none of the takes sings
    a whole section."""
    import versions as V  # tools/versions.py

    song = takes[0].song
    genome = K.ROOT / "songs" / f"{song}.json"
    title = (read(genome, {}) or {}).get("title") or song
    made = V.make(genome, takes, spec, versions_root() / folder.name / spec, title=f"{title} (your version)")
    return [Path(p) for p in (getattr(made, "version", None), getattr(made, "vocals", None)) if p]


def about(name: str) -> str:
    """What a singer's file is, as their page says."""
    low = name.lower()
    return "Your version of the song" if "version" in low else "Your vocals on their own" if "vocals" in low else ""


def upload_name(name: str) -> str | None:
    """The name a made file is kept under on the site (letters, digits, dots, dashes; .mp3 or .wav), or None."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).lstrip("._-")
    return name if FILE_NAME.match(name) else None


def make_all(site: Site, now: str, withdrawn: set, memo: dict) -> None:
    """Each person's version and vocals for each spec they sang in, from all their takes that still have their
    audio (whichever of their pages they sang from), made again whenever those change (new takes, deleted ones),
    and put on each of their pages (every sid of theirs that sang here and hasn't withdrawn)."""
    people: dict[str, dict] = {}
    for side, info in sidecars():
        sid = info.get("sid") or ""
        if info.get("source") != "online" or not SID.match(sid) or sid in withdrawn:
            continue
        p = people.setdefault(info.get("person") or sid, {"folder": side.parent, "sids": set(), "specs": {}})
        p["sids"].add(sid)
        if info.get("spec") and side.with_suffix(".wav").exists():
            p["specs"].setdefault(info["spec"], []).append(side)
    data = versions()
    for person, p in sorted(people.items()):
        folder, sids = p["folder"], sorted(p["sids"])
        for spec, sides in sorted(p["specs"].items()):
            takes = [K.load(side.with_suffix(".wav")) for side in sides]
            ids = sorted(t.info.get("remote") or t.rel for t in takes)
            was = data.get(person, {}).get(spec) or {}
            key = (person, spec, tuple(ids))
            if (was.get("takes") == ids and was.get("sids") == sids and was.get("uploaded")) or key in memo["failed"]:
                continue
            if not (was.get("takes") == ids and was.get("files") and all(here(f["path"]).exists() for f in was["files"])):
                try:
                    made = make_versions(folder, spec, takes)
                except ImportError as e:
                    if "versions" not in memo["said"]:
                        memo["said"].add("versions")
                        say(f"versions skipped: tools/versions.py can't be used here ({e})")
                    return
                except Exception as e:  # noqa: BLE001  (ValueError: no whole section sung; said once, the rest go on)
                    memo["failed"].add(key)
                    if not was:  # whatever it left halfway is recorded nowhere else
                        shutil.rmtree(versions_root() / folder.name / spec, ignore_errors=True)
                    say(f"{folder.name}: no {spec} version: {type(e).__name__}: {e}")
                    continue
                files = [{"path": rel(f), "name": upload_name(f"{spec}.{f.name}")} for f in made]
                for f in was.get("files", []):  # made before under other names
                    if f["path"] not in {g["path"] for g in files}:
                        here(f["path"]).unlink(missing_ok=True)
                data.setdefault(person, {})[spec] = {"takes": ids, "files": files,
                                                     "dir": rel(versions_root() / folder.name / spec),
                                                     "sids": was.get("sids", []), "at": now, "uploaded": False}
                keep_versions(data)  # recorded before anything leaves: every file holding their voice is found later
            entry = data[person][spec]
            try:
                for sid in sids:
                    for f in sorted(entry["files"], key=lambda f: "version" in (f["name"] or "")):  # the version last
                        if f["name"]:
                            query = urllib.parse.urlencode({**({"about": about(f["name"])} if about(f["name"]) else {}),
                                                            "spec": spec}, quote_via=urllib.parse.quote)
                            site.put(f"/api/admin/file/{sid}/{f['name']}?{query}", here(f["path"]).read_bytes(),
                                     KINDS[Path(f["name"]).suffix.lower()])
                    if sid not in entry["sids"]:
                        entry["sids"].append(sid)
                        keep_versions(data)
            except Failed as e:
                if e.status is None:  # the site wasn't reached: the next round tries again
                    raise
                memo["failed"].add(key)
                say(f"{folder.name}: their {spec} version couldn't go on their page: {e}")
                continue
            entry.update(sids=sorted(entry["sids"]), uploaded=True)
            keep_versions(data)
            say(f"{folder.name}: their {spec} version is on their page{'s' if len(sids) > 1 else ''} "
                f"({', '.join(f['name'] for f in entry['files'] if f['name'])})")


# ---------- sync

def sync(site: Site, make: bool = True, memo: dict | None = None, measure: bool = False) -> int:
    """One round: what singers deleted or withdrew, new takes, words, versions (unless not make), the new
    takes measured (if measure: tools/measure.py, so that phrasings made when singing closes take minutes),
    and after DELETE_BY the purge. Once in step, a round asks the site only what its bucket lists cheaply
    (status, gone, takes, words) and says nothing. How many things it did (it says each)."""
    memo = memory() if memo is None else memo
    start = Say.lines
    state = site.call("GET", "/api/admin/status")
    events = site.call("GET", "/api/admin/gone")["gone"]
    withdrawn = apply_gone(site, events)
    if not state.get("deleting"):
        keep_new(site, events, withdrawn, memo)
    keep_words(site, withdrawn)
    if measure and not state.get("deleting"):
        measure_new(memo)
    if make and not state.get("deleting"):  # made after every deleting listed here was done: as of the latest
        made_at = max([state.get("now") or utc_now(), *(e["at"] for e in events if e.get("at"))], key=instant)
        make_all(site, made_at, withdrawn, memo)
    if state.get("deleting"):
        purge(site, state, quiet=True, now=state.get("now"))  # as of the site's clock, like made_at
    return Say.lines - start


def measure_new(memo: dict) -> None:
    """Every take of each song people sang online measured, if it isn't yet (tools/measure.py), saying only what
    was measured anew; what's been dealt with is remembered from round to round, so a quiet round costs nothing."""
    import measure as E  # tools/measure.py

    done = memo.setdefault("measured", set())
    for stem in sorted({t.song for t in K.online()}):
        genome = K.ROOT / "songs" / f"{stem}.json"
        if genome.exists():
            here = {str(t.path) for t in K.takes(stem)}  # after this, each is measured or was said not to be
            E.measure_all(genome, say=say, skip=done, quiet=True)
            done.update(here)


def watch(site: Site, seconds: float, make: bool = True, measure: bool = False) -> None:
    """sync every so many seconds until Ctrl-C: a round that fails says why, and the next starts over (everything a
    round does is safe to do again); a quiet round is a dot."""
    memo = memory()
    Say.clock = True
    try:
        while True:
            try:
                if not sync(site, make, memo, measure):
                    print(".", end="", flush=True)
                    Say.dots = True
            except SystemExit as e:
                say(f"this round didn't finish: {e}")
            except Exception as e:  # noqa: BLE001  (left running overnight: say it, and try again next round)
                say(f"this round didn't finish: {type(e).__name__}: {e}")
            time.sleep(seconds)
    except KeyboardInterrupt:
        say("stopped")
    finally:
        Say.clock = False


# ---------- mail

def letter(group: list[dict], state: dict) -> dict | None:
    """The one message an address needs now, or None: their page (every page of theirs, if any hasn't had it)
    and, once one has a version, that it's ready. {"to", "subject", "body", "covers": [(sid, kind)]}."""
    def had(s, kind):
        return (s.get("sent") or {}).get(kind)

    with_version = [s for s in group if any(f.get("kind") == "version" for f in s.get("files") or [])]
    pages = group if any(not had(s, "link") for s in group) else []
    ready = with_version if any(not had(s, "ready") for s in with_version) else []
    if not pages and not ready:
        return None
    name = next((plain(s["name"]) for s in group if plain(s.get("name"))), "")
    by = day(state["delete_by"])
    keep = (f"Everything you recorded, and these files, are deleted by {by}, so download anything you'd like to "
            "keep before then.")
    parts = [f"Hi {name}," if name else "Hi,"]
    if pages:
        links = [s.get("page", "") for s in pages]
        parts.append("Thank you for singing! " + (f"Your own page is here: {links[0]}" if len(links) == 1 else
                                                  "Your pages are here:\n" + "\n".join(links)))
        if state.get("closed"):
            there = "There you can listen to what you sent, download it, or delete it."
        else:
            there = ("There you can listen to what you sent, download it, delete it, or withdraw. You can withdraw "
                     f"until singing closes on {moment(state['closes'])}.")
        if ready:
            there += f" Your version of the song is there too, ready to download, with your vocals on their own. {keep}"
        else:
            there += (f" Your version of the song will appear there in a few days, before {by} (I'll write again "
                      f"when it does). Everything you recorded is deleted by {by}.")
        parts.append(there)
    else:
        links = [s.get("page", "") for s in ready]
        parts.append("Your version of the song is ready on " + (f"your page: {links[0]}" if len(links) == 1 else
                                                                "your pages:\n" + "\n".join(links)))
        parts.append(f"You can listen to it there and download it, with your vocals on their own. {keep}")
    if any(s.get("notify") for s in group):
        parts.append("You asked to hear when the song is released to the public, so I'll write again then.")
    parts.append("Milo" if pages else "Thank you for singing!\nMilo")
    return {"to": plain(group[0]["email"]),
            "subject": ("Your Songbird pages" if len(pages) > 1 else "Your Songbird page") if pages else
                       "Your version of the song is ready",
            "body": "\n\n".join(parts),
            "covers": [(s["sid"], "link") for s in pages] + [(s["sid"], "ready") for s in ready]}


def mailto(address: str, subject: str, body: str) -> str:
    """A mailto: link (RFC 6068): each part percent-encoded (UTF-8; spaces as %20, never "+"), line breaks as
    %0D%0A."""
    crlf = body.replace("\r\n", "\n").replace("\n", "\r\n")
    q = urllib.parse.quote
    return f"mailto:{q(address, safe='@')}?subject={q(subject, safe='')}&body={q(crlf, safe='')}"


def mail(site: Site, open_: bool = False) -> list[dict]:
    """Who needs an email, one message per address, each printed ready to paste (with open_, also opened in the
    mail app): their page, once they've joined; that their version is ready, once it is. None once DELETE_BY has
    passed: by then an email is kept only for the one message about the song's release. Saves what it listed
    (sid and kind) for mail --sent."""
    state = site.call("GET", "/api/admin/status")
    if not (state.get("closes") and state.get("delete_by")):
        raise SystemExit("the site doesn't say when singing closes or recordings are deleted: set CLOSES_AT and "
                         "DELETE_BY in web/sing/wrangler.toml first")
    letters = []
    if not state.get("deleting"):
        by_address: dict[str, list] = {}
        for s in everyone(site, emails=True):
            if s.get("email") and s.get("state") != "withdrawn":
                by_address.setdefault(s["email"].strip().lower(), []).append(s)
        letters = [m for m in (letter(group, state) for group in by_address.values()) if m]
    write(mail_file(), {"listed": utc_now(), "emails": [{"sid": sid, "kind": kind} for m in letters
                                                        for sid, kind in m["covers"]]})
    for m in letters:
        print(f"To: {m['to']}\nSubject: {m['subject']}\n\n{m['body']}\n\n{'-' * 72}")
        if open_:
            subprocess.run(["open", mailto(m["to"], m["subject"], m["body"])], check=False)
    if letters:
        print(f"{len(letters)} to send" + (", opened in your mail app" if open_ else "") +
              "; once they're sent: uv run python tools/invite.py mail --sent")
    else:
        print("no one needs an email now")
    return letters


def mark_sent(site: Site) -> int:
    """Marks as sent exactly the emails the last `mail` listed (not anyone who joined since), then forgets that
    listing. How many it marked."""
    path = mail_file()
    listed = read(path, None)
    if not isinstance(listed, dict) or not isinstance(listed.get("emails"), list):
        print("nothing to mark: run `mail` first, send what it lists, then `mail --sent`")
        return 0
    left, marked = list(listed["emails"]), []
    for item in listed["emails"]:
        try:
            site.call("POST", f"/api/admin/sent/{urllib.parse.quote(item['sid'])}", {"kind": item["kind"]})
        except Failed as e:
            if e.status is None:  # the site wasn't reached: what's left stays listed, for the next --sent
                write(path, {**listed, "emails": left})
                raise
            print(f"a {item['kind']} email couldn't be marked: {e}")
        else:
            marked.append(item)
        left.remove(item)
    path.unlink(missing_ok=True)
    kinds = collections.Counter(item["kind"] for item in marked)
    print(f"marked as sent: {kinds['link']} page links and {kinds['ready']} 'your version is ready'" if marked else
          "the last `mail` listed no one: nothing to mark")
    return len(marked)


# ---------- purge

def newest(path: Path) -> float:
    """When anything in path (a file, or a folder and everything in it) last changed."""
    latest = path.stat().st_mtime
    if path.is_dir():
        for folder, _, names in os.walk(path):
            for n in [*names, "."]:
                with contextlib.suppress(OSError):
                    latest = max(latest, os.stat(os.path.join(folder, n)).st_mtime)
    return latest


def throat(first: str, delete_by: str | None) -> None:
    """A warning, not a deletion: the training sets under renders/throat (tools/throat) changed since the first
    online take arrived may be built from online singers' voices. Nothing there is deleted by name: a singer
    called Alto would match a synthetic voice's folder."""
    root = K.ROOT / "renders" / "throat"
    if not root.is_dir():
        return
    since = instant(first).timestamp()
    hits = [p for p in sorted(root.iterdir()) if (p.is_dir() or "dataset" in p.name) and newest(p) > since]
    if hits:
        say(f"warning: these in renders/throat changed after the first online take arrived ({when(first)}), so they "
            "may hold online singers' voices. Nothing there was deleted: rebuild them without online takes, or "
            f"delete them, by {day(delete_by) if delete_by else 'DELETE_BY'}:")
        for p in hits:
            say(f"  {rel(p)}{'/' if p.is_dir() else ''}")


def purge(site: Site, state: dict | None = None, quiet: bool = False, server: bool = False,
          now: str | None = None) -> int:
    """Once DELETE_BY has passed: the audio of every online take here (from a singer's page: its sidecar has a
    sid) and every version made from them, deleted; their sidecars (saying "purged", as of now: an ISO time, the
    clock's if not given) and the numbers measured from them stay. Training sets that may hold their voices are
    named, not deleted. server: the site's own purge too, now (it runs hourly anyway). How many files went here."""
    state = state or site.call("GET", "/api/admin/status")
    if not state.get("deleting"):
        if not quiet:
            print("not yet: recordings are kept for their singers until "
                  f"{when(state['delete_by']) if state.get('delete_by') else 'DELETE_BY'}; purge does nothing before then")
        return 0
    now, takes, first, folders = now or utc_now(), 0, None, set()
    for side, info in sidecars():
        if info.get("source") == "online" and info.get("sid"):
            folders.add(side.parent.name)
            if info.get("received") and (first is None or instant(info["received"]) < instant(first)):
                first = info["received"]
            if side.with_suffix(".wav").exists():
                with whole():
                    mark(side, purged=now)
                    side.with_suffix(".wav").unlink()
                takes += 1
    data = versions()
    files = sum(drop(made) for specs in data.values() for made in specs.values())
    for folder in folders:  # and anything else made for them there (versions are made in renders/versions/<folder>/)
        shutil.rmtree(versions_root() / folder, ignore_errors=True)
    if data:
        keep_versions({})
    if takes or files:
        say(f"purged: the audio of {takes} online takes and {files} version files (sidecars and measured numbers stay)")
    elif not quiet:
        say("nothing here holds an online singer's recordings any more")
    if first and (takes or files or not quiet):
        throat(first, state.get("delete_by"))
    if server:
        total = collections.Counter()
        for _ in range(100):
            got = site.call("POST", "/api/admin/purge")
            total.update({k: int(got.get(k) or 0) for k in ("takes", "files", "emails")})
            if not got.get("more"):
                break
        say(f"on the site, now: {total['takes']} takes, {total['files']} files and {total['emails']} emails deleted")
    return takes + files


# ---------- the old way: first-version invitations

def fetch(site: Site, invite: str | None = None, keep: bool = False, singer: str | None = None, dry_run: bool = False,
          purge: bool = False, now: dt.datetime | None = None) -> list:
    """The old way, for first-version (one-time) invitations: every take waiting on the server (or one
    invitation's) into recordings/ (under --singer's name, if given), then off the server. A take from a singer's
    page (a second-version take: its sidecar has a sid) is kept as sync keeps it, in its person's own folder, and
    never deleted from the server here: its singer needs it until DELETE_BY. purge: delete what's left of
    first-version takes that never arrived whole (half a take, STALE seconds old as of now: the clock's if not given)."""
    now = now or dt.datetime.now(dt.UTC)
    query = f"?invite={urllib.parse.quote(invite)}" if invite else ""
    waiting = site.call("GET", f"/api/admin/takes{query}")["takes"]
    notes = {inv["token"]: inv.get("note", "") for inv in site.call("GET", "/api/admin/invites")["invites"]}
    have = fetched()
    kept = []
    for t in waiting:
        paged = "singer" in t  # listed as a singer's (second version), not an invitation's
        if invite and t.get("invite") != invite:
            continue  # a second-version site lists takes by singer, whatever ?invite= says
        label = short(t["id"])
        if t["id"] in have:  # fetched before (with --keep, or the deleting was cut short)
            paged = paged or bool(have[t["id"]].info.get("sid"))
            clear = not (keep or dry_run or paged)
            print(f"{label}: already here as {have[t['id']].rel}" + ("; deleted from the server" if clear else ""))
            if clear:
                remove(site, t)
            continue
        if "json" not in t or "wav" not in t:
            part = t.get("wav") or t.get("json")
            age = (now - instant(part["uploaded"])).total_seconds()
            if purge and age > STALE and not dry_run and not paged:
                remove(site, t)
                print(f"{label}: never arrived whole (its {'sidecar' if 'wav' in t else 'WAV'} is missing): deleted")
            else:
                print(f"{label}: incomplete on the server (its {'sidecar' if 'wav' in t else 'WAV'} is missing), left there"
                      + ("" if age <= STALE or paged else "; --purge-incomplete deletes it"))
            continue
        info = site.call("GET", f"/api/admin/take/{t['json']['key']}")
        paged = paged or bool(info.get("sid"))
        if paged:  # --singer isn't for these: two people's pages never share a folder
            sid = t.get("singer") or info["sid"]
            who = folder_for(info.get("person") or sid, info.get("name"), info.get("song"),
                             lambda i=info: notes.get(i.get("invite"), ""))
        else:
            who = folder_name(info, notes, t.get("invite") or "", singer)
        if dry_run:
            print(f"{label}: {info.get('seconds', 0):.0f} s sung to the {info.get('mix')} guide by {who} "
                  "(not fetched: --dry-run)")
            continue
        wav = site.call("GET", f"/api/admin/take/{t['wav']['key']}", raw=True)
        if len(wav) != info.get("bytes") or hashlib.sha256(wav).hexdigest() != info.get("sha256"):
            print(f"{label}: the WAV doesn't match its sidecar, left on the server")
            continue
        if paged:
            take = keep_online(t, info, wav, who)
        else:
            extra = {k: info[k] for k in TIMING if k in info}
            # credit_as: the name they gave, the only one they may be credited by, and only if they said so
            take = K.keep_sung(info["song"], who, wav, info["guide"],
                               recorded=instant(info["received"]).astimezone().timetuple(), mix=info["mix"],
                               source="online", remote=t["id"], invite=t["invite"][:6], rate=info["rate"],
                               credit=bool(info.get("credit") and info.get("name")), credit_as=info.get("name", ""),
                               consent=info.get("consent"), **extra)
        print(f"{take.rel}: {info['seconds']:.0f} s, {info['mix']} guide{missing(info)}")
        kept.append(take)
        if not (keep or paged):
            remove(site, t)
    if not waiting:
        print("no takes waiting")
    return kept


def remove(site: Site, take: dict) -> None:
    for part in ("wav", "json"):
        if part in take:
            site.call("DELETE", f"/api/admin/take/{take[part]['key']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default=os.environ.get("SONGBIRD_SING_URL", SITE), help=f"the site (default {SITE})")
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("new", help="make invitations: personal links, or a group link")
    a.add_argument("count", nargs="?", type=int, default=1)
    a.add_argument("--people", type=int, default=1,
                   help="how many people may join with each (default 1: a personal link; more: a group link one person can post)")
    a.add_argument("--note", default="", help="who they're for, to find them later (kept on the server, never shown to singers)")
    a.add_argument("--days", type=int, default=7, help="how long each stays open (default 7)")
    a.add_argument("--limit", type=int, default=30, help="the most takes each singer can keep (default 30)")
    a.add_argument("--word", help="one link at this word instead of a random token (/i/<word>): 4 to 24 lowercase "
                                  "letters, digits and hyphens, a letter first; easy to say and type, so guessable")
    sub.add_parser("list", help="every invitation: its state, who joined, their takes")
    s = sub.add_parser("singers", help="everyone who joined: what they sent, which emails they've had, their page")
    s.add_argument("--emails", action="store_true", help="their email addresses too")
    y = sub.add_parser("sync", help="takes and words into recordings/, what singers deleted or withdrew gone here "
                                    "too, their versions made and put on their pages")
    y.add_argument("--watch", type=float, metavar="SECONDS", help="again every SECONDS (10 or more) until Ctrl-C")
    y.add_argument("--no-versions", action="store_true", help="don't make or upload singers' versions")
    y.add_argument("--measure", action="store_true", help="measure new takes too (tools/measure.py), so phrasings are quick")
    m = sub.add_parser("mail", help="who needs an email (their page; their version, once ready), ready to paste")
    m.add_argument("--open", action="store_true", help="open each in your mail app too (a mailto: link)")
    m.add_argument("--sent", action="store_true", help="mark the ones the last `mail` listed as sent")
    sub.add_parser("purge", help="once DELETE_BY has passed: the online takes' audio and their versions, deleted "
                                 "here (and on the site, now)")
    r = sub.add_parser("revoke", help="close an invitation")
    r.add_argument("token")
    f = sub.add_parser("fetch", help="the old way, for first-version links (use sync): takes into recordings/, "
                                     "then off the server")
    f.add_argument("--invite", help="only this invitation's takes (its token)")
    f.add_argument("--singer", help="keep first-version takes under this singer's name, whatever they gave")
    f.add_argument("--keep", action="store_true", help="leave them on the server too")
    f.add_argument("--dry-run", action="store_true", help="say what would be fetched, and fetch nothing")
    f.add_argument("--purge-incomplete", action="store_true",
                   help=f"delete what's left of takes that never arrived whole (over {STALE // 60} minutes old)")
    args = ap.parse_args()
    if args.command == "new" and args.people < 1:
        ap.error("--people is 1 or more")
    if args.command == "new" and args.word is not None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,22}[a-z0-9]", args.word):
            ap.error("--word is 4 to 24 lowercase letters, digits and hyphens, a letter first")
        if args.count != 1:
            ap.error("--word makes one link")
    if args.command == "sync" and args.watch is not None and args.watch < 10:
        ap.error("--watch needs 10 seconds or more (every round lists the site's bucket)")

    site = Site(args.url, admin_token())
    if args.command == "new":
        new(site, args.count, args.note, args.days, args.limit, args.people, args.word)
    elif args.command == "list":
        listing(site)
    elif args.command == "singers":
        singers(site, args.emails)
    elif args.command == "sync":
        with alone():
            if args.watch:
                watch(site, args.watch, not args.no_versions, args.measure)
            elif not sync(site, not args.no_versions, measure=args.measure):
                print("nothing new")
    elif args.command == "mail":
        mark_sent(site) if args.sent else mail(site, args.open)
    elif args.command == "purge":
        with alone():
            purge(site, server=True)
    elif args.command == "fetch":
        with alone():
            fetch(site, args.invite, args.keep, args.singer, args.dry_run, args.purge_incomplete)
    else:
        revoke(site, args.token)


if __name__ == "__main__":
    main()
