# The studio on the web (2026-09-29)

The artist wants the studio public, for good, so experienced musicians can
make their own versions of the song. `songbird studio --public` is that mode,
and `deploy/studio/` puts it in a container on the VPS beside mailcow (or on
the desktop as a fallback), reached only through a Cloudflare tunnel at
something like `https://studio.itsby.you`. Nothing here has been deployed.

The local studio is unchanged: 127.0.0.1, no key, standard library only,
offline, quiet. The shared preview (`--host`, `--allow-host`, `--key`:
docs/STUDIO.md, "Sharing the studio for a preview") is unchanged too. Public
mode is a third way, built on the shared one.

## What public mode is

    songbird studio --public [--allow-host studio.itsby.you] [--host 0.0.0.0]
                    [--client-ip-header CF-Connecting-IP] [--limit NAME=N ...] [--key WORD] [--machine none]

It is *shared* (everything the shared preview does: the Host and Origin
checks, the page's token on every change, the singing page off, only
everyone's phrasing offered, "the computer serving this studio" in the
page's words), and in addition:

- **No key needed**, unless `--key` is given (a closed beta by link). The
  better lock for a closed beta is Cloudflare Access (below).
- **A visitor is a random id** in a cookie (`songbird-visitor-PORT`,
  HttpOnly, SameSite=Lax, Secure behind https, a day long), set with the
  page. It names nobody: it is how the limits tell two people apart.
- **Each visitor has one render at a time.** Asking for a new section while
  a preview of theirs is still waiting drops that one (they've moved on);
  while one of theirs is being made, or their recording waits, the answer is
  "yours is being made now; ask for the next when it's done", shown in the
  player. Asking for something already made, or already being made for
  someone else, costs nothing and isn't counted.
- **A few an hour.** Whole songs (hearing the whole song is making it, so it
  counts as a recording) and sections are counted per visitor and per
  address over the last hour. Past a limit the answer is 429 with
  Retry-After and a sentence: "You've had 4 whole songs made this hour… Try
  again in about 23 minutes; what's made already plays at once."
- **The queue in turn.** Previews are made in the order asked (a local
  studio makes the newest first, which suits one person); recordings still
  go first. Each job the page polls carries `ahead` and `eta` (seconds, from
  how long renders have been taking), so the page says "waiting its turn (2
  ahead, about 3 minutes)". A full queue answers 503 with Retry-After: "The
  studio is busy: 12 songs are waiting to be made, one at a time for
  everyone. Try again in about 9 minutes."
- **Recordings aren't kept.** A local studio copies each recording into
  `renders/`; a public one offers it for download from a store capped in
  size, each kept for a day after it was last asked for
  (`/download/<key>.flac?name=song.day.id.flac`). The file is the same
  packet a local studio records: the program, the song, its record, the
  visitor's choices marked (never who). After it expires, the same choices
  make the same song again.
- **Slow and silent clients.** A connection that sends nothing for 30 s is
  closed (the handler's socket timeout); at most 64 connections are served
  at once and more are turned away; files are streamed rather than read
  whole into memory; requests from one address are capped per minute. The
  server was already threaded (`ThreadingHTTPServer`, one thread per
  connection), with one renderer thread behind it. Behind Cloudflare, the
  edge buffers requests, so a slow upload never reaches the studio as one.
- **The visitor's address** is the connection's; with
  `--client-ip-header CF-Connecting-IP` it is what that header says, but
  only when the connection comes from this machine or a private network
  (cloudflared in the container beside it). From anywhere else the header is
  ignored, so it can't be forged to dodge the limits.
- **`/healthz`** answers `{"ok": true, "waiting": N, "running": bool}`
  without a key and without counting.
- **The machine is never the host's.** `--public` without `--machine`
  sings as `none` (a neutral machine); `fictional:NAME` gives the song a
  made-up machine's character. The container never has the host's harvested
  voice (docs/HARVEST.md) to offer.
- **The page** says it is an open studio, how many songs an hour each person
  has, and how long a recording waits (songbird/studio/studio.js, the
  section "open to the public", kept apart from the rest).

The code is songbird/public.py (the limits, the counts, the download store,
the address, the log line: about 250 lines, standard library) and small
hooks in songbird/studio.py (the queue's fairness and one-at-a-time, the
routes, the connection cap). It ships in the packet like the rest of the
studio (`songbird budget`: 5.45 MiB of 8).

## Limits and their defaults

`--limit NAME=N`, repeatable. Every name, with its default:

| Name | Default | What it limits |
|---|---|---|
| `records` | 4 | whole songs made for one visitor an hour (a recording, or hearing the whole song) |
| `records-ip` | 10 | the same, for one address (a household, a school, a phone network share one) |
| `previews` | 60 | sections made for one visitor an hour |
| `previews-ip` | 150 | the same, for one address |
| `requests` | 600 | requests from one address a minute (the page asks every half second while it waits, and a player asks for ranges) |
| `queue` | 12 | renders waiting at once, for everyone |
| `cache-mb` | 300 | previews kept (shared: the same choices are made once for everyone) |
| `downloads-mb` | 1024 | recordings waiting to be downloaded (about 17 MB each: 60 or so) |
| `download-hours` | 24 | how long a recording waits after it was last asked for |
| `timeout` | 30 | seconds a connection may send nothing |
| `connections` | 64 | connections served at once |

What they mean in time, on the VPS once a whole render fits in its memory
(say 40 to 60 s for a whole song on 2 threads, 3 to 8 s a section; the M1
Max does a whole song in 10 to 17 s): one renderer makes about 60 to 90
whole songs an hour, or several hundred sections. Four whole songs per
person per hour lets 15 to 20 people record in the same hour; the queue of
12 means nobody waits more than about ten minutes before being told to come
back. These are guesses to be tuned from the log (the 429s and 503s in it).

## Architecture

    visitor ─https─▶ Cloudflare edge ◀─outbound─ cloudflared ──http──▶ studio:8766
                     (DNS, TLS, Access)          (container)   internal   (container,
                                                               network    no way out)

- **One process**, `songbird studio --public`: a threaded HTTP server and
  one renderer thread (Jobs). Everything heavy (a section, a whole song) is
  a job; request threads only compute the song's view and options (tens of
  milliseconds). The page keeps each visitor's edits and sends them with
  every request, so the server holds no sessions: only caches, the queue,
  and counts.
- **Previews are content-addressed** (a hash of the program's version, the
  song, the parameters, the words, the voice, the section) and shared: two
  visitors with the same choices hear one render. Nobody can list them.
- **One heavy job at a time.** A render uses up to SONGBIRD_THREADS threads
  (the same bytes whatever it says). Measuring a visitor's singing
  (`--web-singing`, docs/WEB-SINGING.md) is a job in the same queue
  (`studio.jobs`), so a render and a measurement never run at once; it runs
  in a process of its own that peaks under 900 MB and is stopped after each
  take. It loads no speech model: sung takes don't need one.
- **The container** (deploy/studio/Dockerfile): Python 3.12 slim, uv, the
  locked dependencies (`uv sync --frozen --no-dev`), the program and the
  songs, and nothing else of the checkout (no renders, recordings,
  volunteers' takes, voices, or the site: Dockerfile.dockerignore). While
  it's built, warm.py renders the first verse with each style's band and
  masters a few seconds of noise, so every instrument's synthesis is
  compiled into the image (about 30 s, 1.5 GB at build time); the entrypoint
  copies that into the volume, where a new compilation is kept too. A new
  image's first start clears the previews the old program made (the cache's
  keys carry the version number, which doesn't change with every commit).
  It runs as an unprivileged user on a read-only root, with all capabilities
  dropped, writing only to its volume (/data) and a small /tmp.
- **The compose file** (deploy/studio/docker-compose.yml) caps the studio's
  memory with no swap on top (`mem_limit` = `memswap_limit`, 2500m by
  default), its CPUs (2) and processes (256), sets SONGBIRD_THREADS=2, and
  gives it `oom_score_adj: 800`: if a render outgrows the cap, the kernel
  kills the studio (and Docker restarts it) rather than anything of
  mailcow's; if the host itself runs short, the studio is the first to go.
  The studio's only network is `internal`: it can be reached by the tunnel
  and reaches nothing. The tunnel (cloudflared, 128 MB, half a CPU) is on
  that network and one with a way out; it dials Cloudflare, so the host
  opens no port.

What happens when the studio dies mid-render (out of memory, or a restart):
the queue is gone; each waiting page's next poll gets "no such job" and says
so where it was waiting; asking again starts over. Finished previews and
downloads are on the volume and survive.

## Memory: not on the VPS yet

A whole render today peaks at about 3.8 GB with 2 threads (the render-memory
work reports that; measured here on macOS, 6.0 GB maximum resident). The
VPS has 7.57 GB, of which mailcow and the Rails app use about 4.2 GB, so
about 3.4 GB is free: a 2.5 GB cap would kill the studio on the first whole
song, every time. **Deploy to the VPS only after the render-memory work
lands and a whole render stays under about 1.5 GB**, leaving the rest of the
2.5 GB for the server, the preview cache's pages and the measuring model.
Until then, the desktop is the place (same compose file, with
`STUDIO_MEMORY=8g` and `STUDIO_CPUS=4` in `.env`).

To check a new program before deploying: `SONGBIRD_THREADS=2 /usr/bin/time
-v uv run songbird render songs/h-now-its-by-you.json --machine none --out
/tmp/x.flac` on Linux ("Maximum resident set size"), or watch `docker stats`
while a recording is made in the container.

## Deploying on the VPS, beside mailcow

mailcow keeps ports 80 and 443 and its own compose project; this project
publishes no ports and has its own networks, so the two never meet.

1. **The tunnel.** In the Cloudflare dashboard, Zero Trust > Networks >
   Tunnels > Create a tunnel > Cloudflared, named `songbird-studio`. Copy the
   token from the install command (the long string after `--token`); don't
   run the command. Under Public hostnames, add: subdomain `studio`, domain
   `itsby.you`, type HTTP, URL `studio:8766`. Cloudflare makes the DNS record
   (`studio` CNAME to the tunnel, proxied) by itself. Leave "HTTP Host
   Header" empty: the studio answers only to the name it was given, and
   cloudflared passes the visitor's (`studio.itsby.you`). If the studio
   answers "this page answers only its own address", set it to
   `studio.itsby.you` there.
2. **The checkout.** On the VPS: `git clone` the repository (say to
   `/opt/songbird`), then
   `cp deploy/studio/studio.env.example deploy/studio/.env` and fill in
   `TUNNEL_TOKEN` (the file is git-ignored; `chmod 600` it).
3. **Build and start:**
   `docker compose -f deploy/studio/docker-compose.yml up -d --build`
   (a few minutes the first time; the tunnel waits for the studio to be
   healthy).
4. **Check:** `docker compose -f deploy/studio/docker-compose.yml ps` (both
   up, the studio healthy), `… logs -f studio` (the start message, then one
   line per request), `docker stats` while making a recording, then open
   `https://studio.itsby.you`.
5. **Upgrading:** `git pull`, then the same `up -d --build`. The volume
   keeps downloads; old previews are cleared.
6. **Stopping:** `docker compose -f deploy/studio/docker-compose.yml down`
   (the volume stays; `down -v` removes it, and with it every waiting
   download).

The compose file pins cloudflared's version (`CLOUDFLARED_VERSION` in
`.env` changes it); update it now and then.

## On the desktop, as a fallback

The same compose file, with Docker Desktop or OrbStack (arm64 builds
natively), and `.env` giving it more room (`STUDIO_MEMORY=8g`,
`STUDIO_CPUS=4`, `SONGBIRD_THREADS=4`). The tunnel's token moves with the
`.env`: only one of the two machines should run the tunnel at a time
(Cloudflare balances between connectors of one tunnel, and two studios
would keep two queues). Keep the Mac awake (`caffeinate -i`).

To try the image without the tunnel, on 127.0.0.1:8766:

    docker compose -f deploy/studio/docker-compose.yml -f deploy/studio/docker-compose.try.yml up --build studio

Or without Docker at all, the studio from the checkout and cloudflared from
Homebrew, with the tunnel's public hostname pointing at `http://localhost:8766`
instead of `studio:8766` (edit it in the dashboard, or make a second tunnel
for the desktop):

    uv run songbird studio --public --machine none --allow-host studio.itsby.you --client-ip-header CF-Connecting-IP
    cloudflared tunnel run --token "$TUNNEL_TOKEN"

## A closed beta first

Cloudflare Access puts a sign-in in front of the studio without changing it:
Zero Trust > Access > Applications > Add an application > Self-hosted,
domain `studio.itsby.you`, a policy "Allow" with the invited people's email
addresses (or an email domain), sign-in by one-time PIN (a code sent to the
address; no accounts). Free for up to 50 users. Visitors then sign in once
and the studio sees them as it sees anyone (a random id); taking the policy
away opens it to everyone. The studio's own `--key` (in `STUDIO_ARGS`) does
the same by link, with the link as the only lock.

## What is logged, and kept

- **The access log**, one line per request on the studio's stdout (Docker's
  log, rotated at 3 × 10 MB): the time (UTC), the method, the path without
  its query, the status, the bytes sent, the milliseconds taken:
  `2026-09-30T01:52:54Z POST /api/record 200 181 32ms`. Never an address, a
  cookie, a user agent, a referrer, a query, a body, or anyone's edits.
- **Counts**, in memory only: for each visitor id and each address, the
  times of their renders in the last hour and of their requests in the last
  minute, under a keyed hash (HMAC) whose key is made at start and never
  written down. The address itself isn't kept; the counts vanish on
  restart and are purged as they age.
- **Errors**: a render or request that fails prints its traceback to the
  same log. A traceback can include what was asked for (an edit's value),
  never who asked.
- **On disk** (the volume): previews (up to `cache-mb`), recordings waiting
  to be downloaded (up to `downloads-mb`, a day each), the compiled
  synthesis. None of it names a visitor; a preview or recording is named by
  a hash of the choices that made it.
- **Cloudflare** sees what any CDN sees (addresses, TLS, the requests) and
  keeps its analytics per its own policy; cloudflared logs its connections,
  not requests. Cloudflare Access, if used, knows each signed-in email.

A privacy note on the page would say: an open studio; your changes stay in
your browser and are sent only to make the song; a random id in a cookie
counts your songs per hour; nothing names you; recordings are deleted after
a day.

## Costs

- **Cloudflare**: the tunnel, DNS and proxying are free; Access is free up
  to 50 users.
- **The VPS**: already paid. The studio takes up to 2.5 GB of its memory and
  2 of its 4 CPUs while rendering, idles at a few hundred MB; disk about
  1 GB for the image and up to 1.5 GB for the volume (previews, downloads,
  logs). Traffic: a section is about 1.6 MB, a recording about 17 MB, so
  1,000 recordings a month is about 20 GB out, within any VPS's allowance.
- **The desktop**: electricity, and the Mac kept awake.

## Decisions for the artist

1. **Open or gated at first.** Recommended: Cloudflare Access for a closed
   beta of invited musicians, then open. The studio needs no change either
   way.
2. **The limits' values** (the table above). Four whole songs an hour per
   person may be tight for a musician iterating; 8 may be fairer once a
   whole render is quick. The log's 429s and 503s will say.
3. **Whose machine sings.** `none` (neutral) by default; a named made-up
   machine (`fictional:NAME`) would give the public studio a character of
   its own, the same for everyone. Reading each visitor's own browser to
   shape their version would be a second harvest, with its own consent
   (docs/STUDIO.md).
4. **Hearing the whole song counts as a recording** toward the hourly limit,
   because it is the same render. The alternative (a separate, looser count
   for listening) costs the same renderer time.
5. **Downloads wait a day.** Longer means more disk; shorter, more "make it
   again".
6. **The singing card** is disabled in public mode, saying it opens only on
   the serving computer, unless the studio takes singing in the browser
   (`--web-singing`, on in deploy/studio/): then it opens the singing on the
   page itself. Its own decisions are in docs/WEB-SINGING.md.
7. **VPS or desktop first.** The VPS must wait for the render-memory work;
   the desktop can serve today, while it's awake.

## How it was checked

- tests/test_studio_public.py: the limits parse and refuse nonsense; a
  visitor and an address are counted an hour under a key never written
  down; the public queue takes previews in turn, one at a time per visitor,
  says who's ahead and how long, and answers a full queue honestly; a
  public studio needs no key and gives each visitor a random id; a second
  visitor hears where they are in line while a recording runs; hourly limits
  by visitor and by the address a near proxy names (and not a far one); a
  recording is offered for download, not kept, and expires; the download
  store keeps to its size; a silent connection is closed; the log never
  says who (and keeps logging while a render swaps stdout); the local studio
  is as it was.
- tests/test_studio.py and the page's node tests, unchanged, pass.
- A real run in the built-in browser (`--public --machine fictional:wren`):
  a tempo edit, a verse previewed, a recording made (3:02, a valid packet
  marking the tempo as the visitor's, downloaded under its name, nothing in
  `renders/`); while it rendered, the same visitor's next request was
  refused in the player ("Yours is being made now…") and a second visitor
  was answered queued, 1 ahead, an eta of 90 s. It found a bug the tests then covered: a whole render's
  `redirect_stdout` swallowed the log lines of every other thread.
- The container's command run natively with the headers cloudflared sends
  (Host, Origin, X-Forwarded-Proto, CF-Connecting-IP): the page, a preview,
  the Secure cookie; another origin and another host refused. The compose
  file validated with `docker compose config`. **The image itself was not
  built here**: Docker's daemon wasn't running on the desktop. Build it
  with the try override before the first deploy.

## Opening someone's version (2026-09-29)

The artist wants a visitor to be able to drop someone's version of the song
(a FLAC they were sent) into the studio and continue the lineage from it, and
to share a link that opens that version for others later. Locally,
`songbird studio renders/x.flac` already does this from the command line
(docs/STUDIO.md); this brings it to the page, in public mode and locally.

### What a visitor sees

- **"Open someone's version"**: a panel (in "Other versions") with a file
  picker, and a drop anywhere on the page. Only a `.flac` is taken, up to
  64 MB. The page says "reading it…", and then either opens the studio on it
  or says, in a sentence, why it can't.
- The studio then opens at **`/v/<id>`**: the same page, on that version as
  the parent. Everything is relative to it (edits, the cards' "kept from the
  version before", the line of versions in the header, one more mark), and
  Record makes its child: a packet whose record names it as the parent
  (`parent_id`, `generation` + 1, `ancestry`), exactly as
  `songbird studio parent.flac` records one locally.
- The page shows the link to share (`https://…/v/<id>`) and a way back to
  the song as it began. Anyone with the link opens the same version, until it
  expires. The link is the only way to it: nothing lists versions.

### What is kept, and for how long

Never the file. The upload is written to a temporary file in the studio's own
folder (`studio/incoming/`, a random name), read, and deleted whatever
happens (anything left there by a crash is cleared at start). What is kept is
the version as data, in `studio/versions/<id>/`:

- `record.json`: the record as this program read and cleaned it (only the
  fields a parent contributes: id, title, generation, parent_id, ancestry,
  rendered_at, params, lyrics, singer, lineage_singers, performance,
  chosen_by_you, program_sha256, program_version, duration);
- `genome.json`: the song as that version sang it, after validation.

The id is content-addressed: the first 32 hex digits (128 bits) of
SHA-256("songbird-version" ‖ the cleaned record ‖ the genome's SHA-256).
Opening the same file twice gives the same id. It can't be guessed: the
rendition's own id (which its children's records carry) isn't enough; it
takes the whole record, which only the file itself (or the link) gives.

The store is capped (`--limit versions-mb=256`), and a version is kept
`--limit version-days=30` after it was last opened, the least recently
opened going first past the cap. A local studio keeps them the same way
(256 MB, 90 days). This is the seed of a later lineage gallery, but nothing
is published or listed now.

### Another program's version

Every rendition names the program that sang it (`program_sha256`), and
almost every one in circulation was made by an earlier program than the one
serving the studio. The studio **opens it with its own program, and says
so**: "made by another version of the program (971e37bd…); this studio
continues it with its own, so the new version is sung by this one." That is
what the local studio does with a parent, and what `python3 parent.flac new`
does in a newer checkout: a child is always sung by the program that makes
it, and carries that program. The parent's audio is never re-rendered, so
nothing needs replaying faithfully; what matters is that this program can
*read* the record. It is refused, with the reason, when it can't: a field of
the wrong type, a value outside what this program accepts, a section the
genome doesn't have, a shape this program can't sing. A record without a
`program_sha256` isn't a packet a program made, and is refused too.

The song must be this studio's song: the genome's title (and the record's)
must be the title of the song the studio serves. The genome itself may
differ from the one in the checkout (the song file has changed since most
versions were made); the child is sung from the parent's genome, as locally.

### Threat model

A packet carries a **program** (`program/`, `__main__.py`). Running it is
running a stranger's code. The studio **never executes, imports, unpacks or
writes to disk anything from an uploaded packet's program**, and never lets
a name inside the archive choose a path. It reads exactly two members,
`manifest.json` and `genome.json`, as bytes, into memory, and treats both as
untrusted data.

| Threat | Defence |
|---|---|
| Code execution via the packet's program (`__main__.py`, `program/songbird/*.py`, a `.pth`, an `.npz` with pickles) | Never extracted, never on `sys.path`, never imported, never decompressed. Only `manifest.json` and `genome.json` are read. The program's hash is only compared, as text, with this program's. |
| Code execution via data the program loads | Every field is checked against what this program consumes; no field names a file, a module or a class (the voice's `timbre` and `engine` are held to a pattern and a set). JSON is parsed with the standard library, never pickle; the audio is decoded by libsndfile in a separate, short-lived process (below). |
| Path traversal (`../`, absolute names, backslashes, NUL, duplicate names) | Nothing is ever written under a name from the archive. Such names are refused outright, as a sign of a hostile file. Our own paths are `versions/<hex id>/record.json` and `genome.json`. |
| Zip bomb, a huge directory | The end-of-central-directory record is parsed first, by hand: at most 512 entries, a directory of at most 1 MB, no ZIP64, no multi-disk, before `zipfile` opens it. Every entry's declared size is capped (the whole archive 100 MB, as the bootstrap caps it) and its ratio (1000:1). The two members read are capped (1 MB and 512 KB) and read through a bounded stream, whatever their headers claim. Encrypted entries and methods other than stored and deflate are refused. |
| Oversized, slow or endless upload | `Content-Length` is required and checked (64 MB) before a byte is read; the body is streamed to the temporary file with an overall deadline (2 minutes) on top of the 30 s idle timeout; at most two uploads are read at once (more: "busy, try again"); each upload counts as a request against the per-minute limit and against an hourly one (`opens`: 12 per visitor, 40 per address). |
| Not a FLAC, truncated, a FLAC without a packet | It must begin with `fLaC`, carry a packet after the audio, and its audio must decode; each failure has its sentence. |
| Malformed or hostile audio (libFLAC bugs, a header claiming hours) | Decoded in a separate Python process (`python -I`, this program's own code, never the packet's), with a CPU limit, an address-space limit where the OS supports one, and a timeout; it checks the stream's header (FLAC, 1 or 2 channels, up to 192 kHz, at most 20 minutes) before decoding. A crash there is a refusal, not a dead studio. |
| A forged lineage (a record that isn't its audio's) | As `render --parent` does: the audio's samples must hash to the record's `id`, so a lineage is never taken on faith. |
| Hostile JSON (deep nesting, huge arrays or strings, NaN, duplicate keys, huge integers) | Parsed with duplicate keys, NaN and Infinity refused; then walked with caps: depth 12, 100,000 values, strings 4 KB (the genome's 64 KB), lists 4,096, integers within ±2^53. |
| A record that makes renders endless or enormous (a tempo of 1, a 500-section form, a singer's release of an hour) | Numbers are held to this program's own bounds where it has them (the edits' and knobs' bounds, the mix's ranges), and elsewhere to a generous envelope around the program's defaults (never more than 8 times the default's size); the form to the song's sections, at most 64; then the version is laid out as the studio would sing it and refused if it lasts more than 12 minutes or has more than 50,000 notes. |
| A record the program chokes on | After the checks, the studio builds the page's view of the version (what `/api/start` and `/api/song` answer) before accepting it; any error is a refusal, with the reason. |
| Enumerating other people's versions | Ids are 128 bits derived from content no one else has; no listing; an unknown id answers 404 without saying whether one ever existed. |
| Filling the disk | The store is capped and expires; the upload is deleted in a `finally`; the preview cache and downloads keep their own caps. |
| Cross-site upload | The upload needs the page's token (`X-Studio`), the page's own address (Host and Origin), and in a keyed studio the key, like every other change. |

What this doesn't defend against: a vulnerability in libsndfile or libFLAC
that escapes its process (the process has the server's privileges; in the
container, those are few), and a record that is valid but unwelcome (the
words someone chose, which the page already lets anyone write).

### The pieces

- **songbird/received.py** (new; the standard library, but for the audio
  check): reading an uploaded packet as data (the archive's directory by
  hand, the two members, strict JSON), the audio check in its own process,
  the record cleaned to what a parent contributes and held to this program's
  bounds, the genome validated, and the store (`Versions`).
- **songbird/studio.py**, a section of its own ("someone's version"):
  `Studio.receive(path)` (validate, exercise, store), `Studio.opened(id)`
  (the studio on that parent: a light copy sharing the queue, caches,
  limits and token, with its own genome, record and context; a few kept in
  memory), and in the handler `POST /api/open` (the raw file) and
  `GET /v/<id>` (the page). A preview's key names the received parent, so
  two parents never share a render.
- **The page names its version** through the token it was given: at
  `/v/<id>` the page's token is `<token>.<id>`, so every request the page
  already sends (`X-Studio`) says which version it is about, with no change
  to the rest of the page's scripts. A token naming an unknown id is refused.
- **songbird/public.py**: the new limits (`opens`, `opens-ip`, `upload-mb`,
  `versions-mb`, `version-days`).
- **songbird/studio/studio.js**, a section of its own: the panel, the drop,
  the note on a received version, the link to share.

### Open decisions for the artist

1. **Other songs.** Only this studio's song is opened (by title). A packet of
   another song could be opened too (the program sings any genome), at the
   cost of the public studio singing songs it wasn't set up for.
2. **How long a link lives.** 30 days after it was last opened; a gallery
   would want "for good", with a way to take one down.
3. **Another program's versions** open with this program, saying so. The
   alternative, refusing them, would refuse almost every version in
   circulation today.
4. **Words.** A shared link can carry words someone wrote; nothing moderates
   them. A gallery would need that decided first.
