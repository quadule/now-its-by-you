"""Invitations for singers anywhere, and the takes they send back (dev-only).

    uv run python tools/invite.py new 3 --note "choir, Tuesday"     # three one-time links, open 7 days
    uv run python tools/invite.py list                              # every invitation and its takes
    uv run python tools/invite.py fetch                             # takes into recordings/, then off the server
    uv run python tools/invite.py revoke <token>                    # close one

Talks to the site's admin API (web/sing/src/worker.js) at https://songbird.quadule.com,
or wherever --url or SONGBIRD_SING_URL says (http://127.0.0.1:8787 under `wrangler dev`).
The admin token comes from SONGBIRD_SING_ADMIN, or else from `secrets get
songbird-sing-admin`, and is never printed.

fetch keeps each take the way the karaoke keeps one (tools/takes.py): in
recordings/<singer>/, beside a sidecar saying which guide mix was heard, pinned to
the guide score it was sung to (tools/sing_site.py keeps that score in
recordings/guides/ when it builds the site, with the release as singers read it).
The singer's folder is the name they gave, unless that folder already holds
someone else's takes (another invitation's, or ones sung here), when the
invitation's first six characters follow the name; with no name, the invitation's
note and those characters, or singer-<them>. One person's takes never merge with
another's by accident; --singer puts them where you say. Then the take is deleted
from the server, unless --keep: the recordings stay private and with the artist
(docs/SING-ONLINE.md).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import takes as K  # noqa: E402  (tools/takes.py)

SITE = "https://songbird.quadule.com"
SECRET = "songbird-sing-admin"  # its name in the artist's secrets tool
TIMING = ("shift_ms", "auto_ms", "device_ms", "decode_ms", "out_ms", "in_ms")
LOCAL = ("localhost", "127.0.0.1", "::1")
STALE = 600  # seconds after which half a take on the server is left over, not still arriving


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
        req = urllib.request.Request(f"{self.url}{path}", data=data, method=method,
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                                              "User-Agent": "songbird-invite"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = r.read()
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read()).get("message", "")
            except ValueError:
                message = ""
            raise SystemExit(f"{method} {path.split('?')[0]}: {e.code} {message}".strip()) from None
        except urllib.error.URLError as e:
            raise SystemExit(f"can't reach {self.url}: {e.reason}") from None
        return payload if raw else json.loads(payload)


def admin_token() -> str:
    """The admin token: SONGBIRD_SING_ADMIN, else the artist's secrets tool."""
    token = os.environ.get("SONGBIRD_SING_ADMIN", "").strip()
    if token:
        return token
    try:
        got = subprocess.run(["secrets", "get", SECRET], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        got = None
    if got is None or got.returncode or not got.stdout.strip():
        raise SystemExit(f"no admin token: set SONGBIRD_SING_ADMIN, or keep it as {SECRET!r} in your secrets tool "
                         "(the same value as `wrangler secret put ADMIN_TOKEN`)")
    return got.stdout.strip()


def when(iso: str) -> str:
    """2026-10-03T08:10:19.306Z -> 3 Oct 2026, 10:10 (local time)."""
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    return f"{t.day} {t:%b %Y, %H:%M}"


def new(site: Site, count: int, note: str, days: int, limit: int) -> list[dict]:
    made = site.call("POST", "/api/admin/invites", {"count": count, "note": note, "days": days, "limit": limit})["invites"]
    for inv in made:
        print(inv["url"])
    if made:
        print(f"open until {when(made[0]['expires'])}, up to {made[0]['limit']} takes each" +
              (f"; note: {made[0]['note']}" if made[0]["note"] else ""), file=sys.stderr)
    return made


def listing(site: Site) -> list[dict]:
    invites = site.call("GET", "/api/admin/invites")["invites"]
    if not invites:
        print("no invitations yet: make some with `new`")
    for inv in invites:
        print(f"{inv['state']:8s} sent {inv['sent']:2d}/{inv['limit']:<3d} waiting {inv['takes']:2d}  "
              f"until {when(inv['expires']):22s} {inv['note'] or '-':24.24s} {inv['url']}")
    return invites


def revoke(site: Site, token: str) -> None:
    site.call("POST", f"/api/admin/revoke/{urllib.parse.quote(token)}")
    print(f"revoked {token[:6]}…")


def fetched() -> dict[str, K.Take]:
    """The takes already fetched here, by their id on the server."""
    out = {}
    for side in K.RECORDINGS.glob("*/*.json"):
        if side.parent == K.GUIDES:
            continue
        try:
            remote = json.loads(side.read_text()).get("remote")
        except ValueError:
            continue
        if remote:
            out[remote] = K.load(side.with_suffix(".wav"))
    return out


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
    """Whose takes these are, as the singer's name their folder is made from (takes.slug): --singer as
    given; the name they gave, with the invitation after it if that folder holds anyone else's takes;
    with no name (or none a folder can be made of), the invitation's note or "singer", and the invitation."""
    if singer:
        return singer
    tag = invite[:6]
    name = (info.get("name") or "").strip()
    if name and K.slug(name) != "someone":
        return name if invites_in(K.slug(name)) <= {tag} else f"{name} ({tag})"
    return f"{notes.get(invite) or 'singer'} ({tag})"


def fetch(site: Site, invite: str | None = None, keep: bool = False, singer: str | None = None, dry_run: bool = False,
          purge: bool = False) -> list:
    """Every take waiting on the server (or one invitation's) into recordings/, then off the server.
    purge: delete what's left of takes that never arrived whole (half a take, STALE seconds old)."""
    query = f"?invite={urllib.parse.quote(invite)}" if invite else ""
    waiting = site.call("GET", f"/api/admin/takes{query}")["takes"]
    notes = {inv["token"]: inv.get("note", "") for inv in site.call("GET", "/api/admin/invites")["invites"]}
    have = fetched()
    kept = []
    for t in waiting:
        if t["id"] in have:  # fetched before (with --keep, or the deleting was cut short)
            print(f"{t['id']}: already here as {have[t['id']].rel}" + ("" if keep or dry_run else "; deleted from the server"))
            if not (keep or dry_run):
                remove(site, t)
            continue
        if "json" not in t or "wav" not in t:
            part = t.get("wav") or t.get("json")
            uploaded = dt.datetime.fromisoformat(part["uploaded"].replace("Z", "+00:00"))
            age = (dt.datetime.now(dt.timezone.utc) - uploaded).total_seconds()
            if purge and age > STALE and not dry_run:
                remove(site, t)
                print(f"{t['id']}: never arrived whole (its {'sidecar' if 'wav' in t else 'WAV'} is missing): deleted")
            else:
                print(f"{t['id']}: incomplete on the server (its {'sidecar' if 'wav' in t else 'WAV'} is missing), left there"
                      + ("" if age <= STALE else "; --purge-incomplete deletes it"))
            continue
        info = site.call("GET", f"/api/admin/take/{t['json']['key']}")
        who = folder_name(info, notes, t["invite"], singer)
        if dry_run:
            print(f"{t['id']}: {info.get('seconds', 0):.0f} s sung to the {info.get('mix')} guide by {who} "
                  "(not fetched: --dry-run)")
            continue
        wav = site.call("GET", f"/api/admin/take/{t['wav']['key']}", raw=True)
        if len(wav) != info.get("bytes") or hashlib.sha256(wav).hexdigest() != info.get("sha256"):
            print(f"{t['id']}: the WAV doesn't match its sidecar, left on the server")
            continue
        received = dt.datetime.fromisoformat(info["received"].replace("Z", "+00:00")).astimezone()
        extra = {k: info[k] for k in TIMING if k in info}
        # credit_as: the name they gave, the only one they may be credited by, and only if they said so
        take = K.keep_sung(info["song"], who, wav, info["guide"], recorded=received.timetuple(),
                           mix=info["mix"], source="online", remote=t["id"], invite=t["invite"][:6], rate=info["rate"],
                           credit=bool(info.get("credit") and info.get("name")), credit_as=info.get("name", ""),
                           consent=info.get("consent"), **extra)
        missing = []
        if not K.guide_score(info["song"], info["guide"]):
            missing.append(f"its guide score {info['guide']}")
        if not (K.GUIDES / f"release.{(info.get('consent') or {}).get('text')}.html").exists():
            missing.append(f"the release it was agreed under ({(info.get('consent') or {}).get('text')})")
        print(f"{take.rel}: {info['seconds']:.0f} s, {info['mix']} guide" +
              (f" ({' and '.join(missing)} not in {K.GUIDES.name}/ here: build the site on this machine, "
               "or copy them over)" if missing else ""))
        kept.append(take)
        if not keep:
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
    a = sub.add_parser("new", help="make one-time links")
    a.add_argument("count", nargs="?", type=int, default=1)
    a.add_argument("--note", default="", help="who they're for, to find them later (kept on the server, never shown to singers)")
    a.add_argument("--days", type=int, default=7, help="how long each stays open (default 7)")
    a.add_argument("--limit", type=int, default=30, help="the most takes each can send (default 30)")
    sub.add_parser("list", help="every invitation, its state and its takes")
    f = sub.add_parser("fetch", help="download the takes into recordings/, then delete them from the server")
    f.add_argument("--invite", help="only this invitation's takes (its token)")
    f.add_argument("--singer", help="keep them under this singer's name, whatever they gave")
    f.add_argument("--keep", action="store_true", help="leave them on the server too")
    f.add_argument("--dry-run", action="store_true", help="say what would be fetched, and fetch nothing")
    f.add_argument("--purge-incomplete", action="store_true",
                   help=f"delete what's left of takes that never arrived whole (over {STALE // 60} minutes old)")
    r = sub.add_parser("revoke", help="close an invitation")
    r.add_argument("token")
    args = ap.parse_args()

    site = Site(args.url, admin_token())
    if args.command == "new":
        new(site, args.count, args.note, args.days, args.limit)
    elif args.command == "list":
        listing(site)
    elif args.command == "fetch":
        fetch(site, args.invite, args.keep, args.singer, args.dry_run, args.purge_incomplete)
    else:
        revoke(site, args.token)


if __name__ == "__main__":
    main()
