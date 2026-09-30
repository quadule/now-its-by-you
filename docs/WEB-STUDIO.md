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
                    [--browser-render DIR]     (the song made in desktop browsers: "Made in the visitor's browser")

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
| `queue-ip` | 3 | renders waiting at once from one address (an IPv6 one by its /64), however many visitors or none it holds |
| `render-mb` | STUDIO_MEMORY less 400 | the most a whole song may take to make here: one estimated past it is refused before it's queued ("A whole song's memory", below) |
| `cache-mb` | 300 | previews kept (shared: the same choices are made once for everyone) |
| `downloads-mb` | 1024 | recordings waiting to be downloaded (about 17 MB each: 60 or so) |
| `download-hours` | 24 | how long a recording waits after it was last asked for |
| `timeout` | 30 | seconds a connection may send nothing |
| `connections` | 64 | connections served at once |
| `connections-ip` | 16 | requests served at once from one address (past it: 429) |
| `send-kb` | 16 | the slowest a download is sent, KB a second over its whole time, after a minute's grace (a slower reader is let go) |
| `opens` | 12 | versions someone was sent, opened by one visitor an hour (each is read in a process of its own: about 9 s) |
| `opens-ip` | 40 | the same, for one address (an IPv6 address counted by its /64) |
| `upload-mb` | 64 | the largest file taken as a version to open (a rendition is 15 to 20 MB) |
| `versions-mb` | 256 | versions opened, kept as data (about 150 KB each; at most 4,000 of them) |
| `version-days` | 30 | how long a version is kept after it was last opened: its link works that long |

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

## Memory

Since 2026-09-29 (docs/PERFORMANCE.md, "Memory (2026-09-29)") a whole render
peaks at about 1.33 GB with 2 threads and 1.13 GB with 1, the output byte for
byte what it was (it was 3.2 GB). Those are macOS figures with
`MallocLargeCache=0`, the nearest stand-in for Linux, which hands large freed
arrays straight back; the compose file sets `MALLOC_ARENA_MAX=2` and
`MALLOC_MMAP_THRESHOLD_=1048576` so glibc does. A measuring process for
singing (under 900 MB) never runs beside a render: they share one queue. So
the 2.5 GB cap holds H's seed with room for the server and its pages, on the
VPS's ~3.4 GB free beside mailcow; but not every version (a long one, or one
with a drum kit): "A whole song's memory", below, is how the studio keeps a
render inside the cap. **Measure it once in the container before
opening it** (`docker stats` while a whole song is recorded, or
`tools/render_memory.py`): these figures are from a Mac, not the VPS.

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

The page says it (since 2026-09-30: the footer, Help's "What's kept", a word
in the Tools sheet that opens it): a random id in a cookie, so everyone gets
a fair share (it names nobody); your changes stay in this browser, sent only
to make the song; a recording waits a day to be downloaded, then goes; a
shared /v/ link, and any file downloaded, carries its version's own record
(its made-up machine's name, the room its microphone heard, the leanings of
its words); singing keeps only numbers, the audio deleted once measured.

## Costs

- **Cloudflare**: the tunnel, DNS and proxying are free; Access is free up
  to 50 users.
- **The VPS**: already paid. The studio takes up to 2.5 GB of its memory and
  2 of its 4 CPUs while rendering, idles at a few hundred MB; disk about
  1 GB for the image and up to 1.5 GB for the volume (previews, downloads,
  logs). Traffic: a section is about 1.6 MB, a recording about 17 MB, so
  1,000 recordings a month is about 20 GB out, within any VPS's allowance.
  With the song made in visitors' browsers (below, "Made in the visitor's
  browser"), the VPS mostly serves files: each new desktop visitor fetches
  the singer once (about 28 MB), and the renderer works only for phones,
  tablets and fallbacks.
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

- Before sending, the page asks whether a file that size would be taken now
  (`POST /api/open/ready`): a limit reached or a busy studio is said in a
  sentence before 17 MB go anywhere.

### What is kept, and for how long

Never the file. The upload is written to a folder of its own in the studio's
folder (`studio/incoming/open-…/`), read, and removed whatever happens (a
folder older than an hour, left by a stopped studio, is cleared at start). What
is kept is the version as data, in `studio/versions/<id>/`:

- `record.json`: the record as this program read and cleaned it (only the
  fields a parent gives its child: id, title, generation, parent_id,
  ancestry, rendered_at, params, lyrics, singer, lineage_singers,
  performance, chosen_by_you, program_sha256, program_version, duration;
  not the maker's machine's numbers, `voice` and `drift`);
- `genome.json`: the song as that version sang it, after validation;
- `timeline.json`: its six years of timeline for the studio's machine and
  day, worked out while it was read, so the page's heaviest question doesn't
  cost the studio again (a new day works it out afresh).

The id is a keyed hash: the first 32 hex digits (128 bits) of
HMAC-SHA-256(key, "songbird-version" ‖ the cleaned record ‖ the genome's
SHA-256), the key made once and kept beside the versions (`.key`, 0600).
Opening the same file twice gives the same id. It can't be worked out, even
for a version anyone could make (the child a studio sings for no edits on a
given day, say, which is deterministic): only the link says it. The access
log writes `/v/…`, never the id.

The store is capped (`--limit versions-mb=256`, and 4,000 versions), and a
version is kept `--limit version-days=30` after it was last opened, the
least recently opened going first past the cap. A local studio keeps them
the same way (256 MB, 90 days). This is the seed of a later lineage gallery,
but nothing is published or listed now.

### Another program's version

Every rendition names the program that sang it (`program_sha256`), and
almost every one in circulation was made by an earlier program than the one
serving the studio (every rendition under renders/ on 29 September was).
The studio **opens it with its own program, and says so**: "It was made by
another version of the program (971e37bd…); this studio continues it with
its own (58b771d1…), so the new version is sung by this one." That is what
the local studio does with a parent, and what `python3 parent.flac new` does
in a newer checkout: a child is always sung by the program that makes it,
and carries that program. The parent's audio is never re-rendered, so
nothing needs replaying faithfully; what matters is that this program can
*read* the record. It is refused, with the reason, when it can't: a field of
the wrong type, a value outside what this program accepts, a section the
song doesn't have, a shape this program can't sing. A record without a
`program_sha256` isn't a packet a program made, and is refused too.

The song must be this studio's song: the genome's title (and the record's)
must be the title of the song the studio serves. The genome itself may
differ from the checkout's (the song file has changed since most versions
were made, and six renditions from four programs all opened); the child is
sung from the parent's genome, as locally, and packs it.

### Threat model

A packet carries a **program** (`program/`, `__main__.py`). Running it is
running a stranger's code. The studio **never executes, imports, unpacks or
writes to disk anything from an uploaded packet's program**, and never lets
a name inside the archive choose a path. It reads exactly two members,
`manifest.json` and `genome.json`, as bytes, into memory, and treats both as
untrusted data. And it does all of the reading **in a process of its own**
(`python -I`, this program's own code from this program's own folder: no
PYTHONPATH, no user site, no current folder; a CPU limit of 60 s, an
address-space limit of 3 GB where the system has one, its own process group,
stopped whole past 75 s), so whatever a hostile file does to the reader, the
studio only hears "refused".

| Threat | Defence |
|---|---|
| Code execution via the packet's program (`__main__.py`, `program/songbird/*.py`, a `sitecustomize.py`, an `.npz` with pickles) | Never extracted, never on `sys.path`, never imported, never decompressed. Only `manifest.json` and `genome.json` are read. The program's hash is only compared, as text, with this program's. A test puts canaries in all of these (and a `program/songbird/received.py` that would shadow the reader) and checks nothing ran or was written. |
| Code execution via data the program loads | Every field is checked against what this program consumes; no field names a file, a module or a class (the voice's `timbre` is held to name:number pairs and `engine` to learned or formant: not the experimental waveguide). JSON is parsed with the standard library, never pickle. |
| Path traversal (`../`, absolute names, backslashes, NUL, `.` parts, duplicate names) | Nothing is ever written under a name from the archive. Such names are refused outright, as a sign of a hostile file. Our own paths are `versions/<hex id>/…`. |
| Zip bomb, a huge directory, overlapping entries | The end record zipfile will use (the last in the final 64 KB) is parsed first, by hand, and must end the file: at most 512 entries, a directory of at most 1 MB right before it, no ZIP64, one disk. Then zipfile's own list is checked again: no encryption, stored or deflate only, no data descriptors, declared sizes within 100 MB in all (as the bootstrap caps an unpacking) and 1000:1 each, and the entries' local headers must tile the archive exactly from the end of the audio to the directory, so no entry overlaps another (Python 3.11 doesn't refuse that itself) and "the audio" is exactly what a player plays. The two members read are capped (1 MB and 512 KB) and read through a bounded stream, whatever their headers claim. |
| Oversized, slow or endless upload | The page asks first. Then every guard (address, key, per-minute requests, token, `Content-Length` within 64 MB, the hourly `opens`, one upload per address and four in all) comes before a byte of the body is read; a refused body is never read (a small one is read and dropped, so the answer isn't lost to a reset). The body is streamed to disk with a deadline of a minute plus a second per 32 KB, on top of the 30 s idle timeout; two files are read at once. Behind Cloudflare, the edge buffers the upload anyway. |
| Not a FLAC, truncated, a FLAC without a packet, a preview (no packet) | It must begin with `fLaC` and carry a packet after the audio; each failure has its sentence. |
| Malformed or hostile audio (libFLAC bugs, a header claiming hours, a FLAC bomb of silent frames) | Decoded in the reader's process; it must be FLAC, stereo, at the synth's 44.1 kHz, and is hashed a block at a time, stopping past 13 minutes whatever the header says. |
| A forged lineage (a record that isn't its audio's) | As `render --parent` does: the audio's samples must hash to the record's `id`. |
| Hostile JSON (deep nesting, huge arrays or strings, NaN, duplicate keys, huge integers) | Parsed with duplicate keys, NaN and Infinity refused; then walked with caps: depth 16, 100,000 values, strings 4 KB (the song's 64 KB), lists and maps 4,096, integers within ±2^53. Free-form parts (words held, the composition, the words sung, a person's marks) are capped by size too (32 to 64 KB). |
| A record that makes renders endless or enormous, or poisons the child (a tempo of 1, a 500-section form, a singer's release of an hour, NaN as a string) | Numbers must be JSON numbers (never strings the program would coerce), finite, and within: an explicit table for every one of the singer's 40 numbers (for the lead, and for every earlier singer, who sing the choir); the mix's designed ranges; for the band, a knob's bounds widened by their span or eight times the default; tempo within 0.5 to 1.6 times the song's, key within an octave, the form the song's own sections (at most 64). Variants, gestures (rebuilt through `phrasing.reduce`) and the choir's ways of singing are held to their reach. The child the studio records inherits only this cleaned record, so a hostile record doesn't travel on to the people who run the child. |
| A song that doesn't end, or chokes the program (a form grammar with nested repeats, a bank asking for a thousand verses) | Its form at most 24 parts with at most two repeats, sections named plainly, at most eight verses, its tempo 50 to 220 and its key within reach; then loaded as the program loads a song, and the version laid out as the studio would sing it: refused past 12 minutes, 50,000 notes, or a note of more than 60 s. |
| A record the program chokes on, or takes ages over | The reader builds the page's view of the version, lays it out, and draws its whole timeline (about 5 s for the song on an M1); any error is a refusal, with the reason, and so is taking longer than 40 s. |
| Memory growing with every version opened | The studio keeps its latest 16 versions in memory and shares one parsed song among those that sang the same one; `variation.per_genome`, which kept every song it was ever asked about, now keeps the latest 16. |
| Enumerating other people's versions | Keyed 128-bit ids; no listing; an unknown or malformed id answers 404 without saying whether one ever existed; the log never writes an id. |
| Filling the disk | The store is capped by size and count and expires; the upload's folder is removed in a `finally`; the preview cache and downloads keep their own caps. A version's recording packs the song from its own render folder, so pruning a version never breaks a render in flight. |
| Cross-site upload | The upload needs the page's token (`X-Studio`, a header no other site's page can send without asking), the page's own address (Host and Origin), and in a keyed studio the key, like every other change. |
| Someone's IPv6 addresses dodging the limits | Every limit counts an IPv6 address by its /64. |

What this doesn't defend against:

- a vulnerability in libsndfile or libFLAC that escapes the reader's process
  (it has the server's privileges; in the container, those are few);
- a visitor clearing their cookie: the per-visitor `opens` count is only as
  good as the cookie; the per-address count (40 an hour) is what holds;
- a record that is valid but unwelcome: the words someone chose, which the
  page already lets anyone write (decision 4);
- someone flooding the store from many addresses to push others' links out
  (40 an hour from each of five addresses fills 256 MB in about eight hours);
  a per-address share of the store would be the next step if it happens.

**Privacy.** What is kept of a version is what its file already carries and
what its children carry by design (docs/HARVEST.md): the lineage's parameters,
among them the maker's machine's pseudonym (`params.made.by`, twelve hex
digits), the room its microphone heard (`mix`), the moods and vocabulary its
words lean to (`leanings`), and the singer drawn from it. The record's own
`voice` and `drift` (the machine's reduced numbers) are not kept. The link
shows no more than the file does, to anyone the link is passed to; the person
who brings a file may not be the person who made it.

### The pieces

- **songbird/received.py** (new): reading an uploaded packet as data (the
  archive's directory by hand, the entries' tiling, the two members, strict
  JSON), the song checked, the record cleaned to what a parent gives and held
  to this program's bounds, the audio against the record's id, the version
  tried as the studio would open it; `examine` does it all, `examine_apart`
  runs it in its own process; `Versions`, the store.
- **songbird/studio.py**, a section of its own ("someone's version"):
  `Studio.receive(path)` and `Studio.opened(id)` (the studio on that parent:
  a light copy sharing the queue, caches, limits and token, with its own
  song, record, context and timeline; the latest 16 kept). A preview's key
  names the received parent, so two parents never share a render; a
  recording packs the song the parent sang. In the handler, a section of its
  own too: `POST /api/open` (the raw file, every guard first),
  `POST /api/open/ready` (would a file this size be taken now?), and
  `GET /v/<id>` (the page).
- **The page names its version** through the token it was given: at
  `/v/<id>` the page's token is `<token>.<id>`, so every request it sends
  (`X-Studio`) says which version it is about, and nothing else on the page
  needed to change (the web singing's take reads the token's first part).
  The page's questions (`/api/start`, `/api/timeline`) send it too. A token
  naming a version not kept answers 404.
- **songbird/public.py**: the new limits (`opens`, `opens-ip`, `upload-mb`,
  `versions-mb`, `version-days`), `Gate.render(..., count=False)` for the
  page's question, addresses counted by their network, the log's `/v/…`.
- **songbird/studio/studio.js**, a section of its own: the panel, the drop
  and its veil, the header's note at `/v/<id>` with the link to share; the
  page's saved edits are kept per version.

### The review (Fable, 2026-09-29)

A read-only security review of the design above, before it was built. Its
main points, and what came of them (all are in the design as it stands):

- **Lineage laundering.** The child copies its parent's `singer` and
  earlier singers into its record, so a hostile record would travel to
  everyone who runs the child locally, where `VoiceParams(**data)` checks
  nothing. The record is rebuilt field by field, and the child inherits only
  that.
- **Most of the singer's numbers had no bounds** (the knobs cover about 20
  of 40), and "eight times the default" collapses at a default of 0: an
  explicit table now covers all of them.
- **NaN smuggled as strings** (`"rd": "nan"`, which the program's own
  coercions accept): numbers must be JSON numbers.
- **The timeline is a 2,191-fold amplifier** of a heavy record, per id and
  again after eviction: sizes are capped, the reading is timed with the
  timeline included, and the timeline is kept with the version.
- **`per_genome` pinned every genome forever**: now the latest 16.
- **The title check doesn't make it this studio's song**: said plainly in
  decision 1 below, with the song's shape bounded.
- **The audio cap was loose**, and a header can lie: stereo at 44.1 kHz only,
  hashed a block at a time, stopped past 13 minutes.
- **zipfile and a hand parser can disagree**; overlapping entries are only
  refused by Python 3.12; an entry pointing into the audio would shorten
  "the audio": the same end record as zipfile's, the entries tiling the
  archive, no data descriptors.
- **Read the guards before the body**, **per-address concurrency**, the
  **per-visitor count is cosmetic** (cookies), **IPv6**: all as above.
- **Store races and eviction**: puts are atomic renames, a vanished version
  reads as 404, a render packs from its own folder; a count cap too.
- **The id leaked to the access log**, and a deterministic record's id could
  be worked out: `/v/…` in the log, and a keyed id.
- **Privacy of what's kept**: the section above.
- Not taken: checking `timbre`'s singer names against the learned model
  (unknown names are ignored by the program; loading the model to check
  costs more than it saves), a minimum byte rate (the deadline scales with
  the size instead).

### How it was checked

- tests/test_studio_received.py (18 tests): a real packet read as data, its
  record cleaned (no `voice`); the reader's hash is the packet's; refused, each
  with its reason: not a FLAC, a zip alone, a bare FLAC, truncated in the
  middle and at the end, the archive moved, no song, over the size; a
  200 MB bomb inside and an 8 MB record; a member larger than it says; five
  kinds of climbing names, and a name twice; twenty records of the wrong
  types or sizes (among them `"nan"` as a string, a release of 10^7 s, the
  waveguide, a timbre of NaN, an earlier singer's vibrato of 10^9, 5,000
  ancestors, a forged id, another title, a gesture naming `__class__`), a
  record 40 deep, a key twice, NaN; a song of another title, a tempo of 1, a
  form of 52 parts, a broken tune. Another program's version opens saying so.
  Canaries in `__main__.py`, `program/songbird/__init__.py`,
  `program/songbird/received.py`, `sitecustomize.py` and `usercustomize.py`
  never run, in this process or the reader's, and nothing of the program is
  written; `sys.path` is untouched. A real render: the child of a version of
  B brought to a local studio is generation 3, names its parent, carries its
  ancestry and its singer, this program, and B's song. Over HTTP: the upload,
  `/v/<id>`, `/api/start` and `/api/song` on it, the same file the same id,
  the log never naming it; every guard (no token, another token, another
  host, another origin, 200 MB announced and answered 413 before any body,
  the page's question, the hour's opens) and nothing left in `incoming`; a
  version not kept answers as one never made; the store's keyed ids, key
  file, expiry and caps; the memo's 16 songs; IPv6 /64 counting. This
  computer's own studio takes a version the same way.
- A real run in the built-in browser, the public studio served from this
  checkout (`--public --machine fictional:wren`, its own `SONGBIRD_HOME`):
  renders/review/contest.flac (made by program 971e37bd, 15.8 MB) dropped on
  the page (a real drop event; the veil showed) was asked about, sent and
  read in 8.5 s, and the page moved to `/v/<id>`: "Continuing the first
  version (07ac74fbd4eb…)… What you record is its child", the other program
  said, the link to share. The tempo set to 92 and recorded (3:12): its
  record, checked against its audio, is generation 1, parent 07ac74fbd4eb,
  ancestry [07ac74fbd4eb], this program (58b771d1), the tempo marked as the
  visitor's (92, was 101.8). The link opened in a new tab on the same
  version (its edits kept for it); `/` opened on the song as it began, with
  its own edits; an unknown id answered 404. A text file was refused on the
  page, and a section preview (a FLAC with no packet) by the server, each in
  a sentence. The upload folder was empty afterwards; no errors in the
  console. The log: `POST /api/open 200 … 8540ms`, `GET /v/… 200`.

### Open decisions for the artist

1. **Other songs.** Only this studio's song is opened, by title; but its
   tune, words and bank may differ from the checkout's (as older versions'
   do), so the public studio will sing what a version brought, within the
   bounds above. A stricter rule would open only songs whose files this
   program has known (a list of their hashes, kept as the song changes),
   which would refuse versions made from a checkout's changes.
2. **How long a link lives.** 30 days after it was last opened; a gallery
   would want "for good", with a way to take one down.
3. **Another program's versions** open with this program, saying so. The
   alternative, refusing them, would refuse every version in circulation
   today.
4. **Words.** A shared link can carry words someone wrote; nothing moderates
   them. A gallery would need that decided first.
5. **What a link shows of the maker** (the privacy note above): the same as
   the file, to whoever has the link. Blurring the machine's pseudonym and
   room for shared links would change what the child inherits.

## Made in the visitor's browser (2026-09-30)

The feasibility spike (docs/BROWSER-RENDER.md) showed the program itself running in a browser: Pyodide, the numba
kernels translated to JavaScript and a few to C/wasm, the same samples as native. This puts it behind the studio's
page, so a desktop visitor's own browser makes their previews and their recording, and the VPS mostly serves files.
The server stays the fallback for everything the browser can't do. The local studio is unchanged: it renders
natively, and the bundle never goes into the song's packet.

    songbird studio --public --browser-render DIR      DIR: built by web/studio-wasm/tools/build_render.py

### What a visitor sees

- **Nothing new, at first.** On a desktop browser the first ▶ or *Record it* says "getting the singer ready (once:
  12 of 35 MB)" in the player, then what the program is doing ("singing", "playing the fiddle", "mastering"), as
  a server render does. This happens once per visitor: the files are cached for good after that, and later visits
  say only "getting the singer ready" for the 5 or 6 seconds Python takes to start.
- **The Tools sheet** has *Make the song: automatically · in this browser · on the server* under *Record it*, with a
  line saying what automatically means here ("This browser makes the song itself, as the server would…", or "The server makes the song:
  phones and tablets have the server make it") and where the last one was made ("The last section was made in this
  browser (5.1 s)"). The choice is kept in this browser. The setting is shown only where the studio serves the
  bundle.
- **A recording made in the browser** is downloaded straight from the page (*Download it*, a Blob with the file's
  own name, `now-its-by-you.2026-09-30.477703.flac`). The server never sees it and keeps nothing: no download
  store, no hourly count.
- **When the browser can't**, the render goes to the server and the player says so in passing ("this browser
  couldn't make it, so the server is", then "mixing on the server…"). Nothing else changes.

### How it works

1. **The render spec.** The page asks `POST /api/render/spec` (edits, who, section) and the studio answers with
   what its own renderer would be handed: the key it would cache the render under, the player's words, and the spec
   (JSON, sent as a string so the page never reads its 64-bit seeds as floats): the song's file as it is, the
   version's resolved params (`Params.to_dict`), its words (`Lyrics.to_dict`), the phrasing and the voices before,
   the parent's record; for the whole song also the machine, the day (drift), the changes and the person's marks,
   the Python and pinned dependencies the packet names, and the recording's name. If the studio has made it
   already, it says `made` instead, and the page asks for it as ever (it plays at once, and costs nothing).
2. **The worker** (web/studio-wasm/studio-worker.mjs, a module Web Worker) loads Pyodide, numpy, scipy and
   soundfile, the kernels (JS, and the 14 C ports as wasm), and the program, and runs
   web/studio-wasm/py/studio_render.py: a section exactly as `Studio._section` makes it (the same `window`, `cut`,
   gain, limiter, `faded`, `to_pcm16`, FLAC), the whole song exactly as `Studio._whole` does (`cli.render_one`,
   packed). Its progress is the server's own (`Job.report` over `stages`). It hands back the FLAC and the record.
3. **The program in the bundle is the server's**, file for file (`pack.program_files`), so a recording made in the
   browser names the same `program_sha256`. The studio checks the bundle's digest against its own at start and
   refuses a bundle built from another program; the worker checks the spec's digest against its own before
   making anything.
4. **The renderer** (songbird/studio/renderer.js) decides where each render is made, keeps what it made (16
   sections, 3 whole songs, as Blob URLs) so asking again plays at once, and reports where each was made
   (`job.where`, `SongbirdRenderer.made`). studio.js and score.js didn't change: they ask the renderer as before.

### When the browser makes it

- **Automatically** (the default): when the studio serves the bundle, and this is a browser with WebAssembly and
  Web Workers, not a phone or a tablet (`navigator.userAgentData.mobile`, the user agent, an iPad calling itself a
  Mac, a screen under 600 px), and `navigator.deviceMemory` (where the browser says: Chrome and Edge) is 4 GB or
  more. Desktop Chrome, Edge, Firefox and Safari qualify; Safari is untested.
- **In this browser**: the visitor's choice, phones included.
- **On the server**: always the server.
- **After a failure**: that render goes to the server. Two failures in a visit send the rest of the visit to the
  server; a whole song that runs out of memory sends whole songs to the server (sections stay in the browser).
  A failure is the worker's error (a Python exception, `MemoryError`, a RangeError from wasm memory, something the
  policy blocked), the worker dying (`onerror`), or a stall: no word from the worker for 3 minutes while getting ready, 5 for a section, 10
  for a whole song (a hidden tab's worker runs several times slower, so a render isn't timed as a whole), and 40
  minutes in all.

**Workers.** A whole song is made in a worker of its own, terminated when it's done (wasm memory never shrinks:
a worker that has sung a whole song holds its 1-2 GB until it goes), and the section worker is terminated before
it starts (two heaps at once is too much). Sections share one worker, replaced after four (its heap only grows)
or after three minutes unused. Cancelling a whole song being made terminates its worker; a section being made
finishes and is kept (as the server's queue does).

**First use: a quiet default, not a prompt.** Decided: the browser makes it without asking. The download is
about 28 MB on the wire (35 MB unpacked), once; a prompt would ask every desktop visitor a question they can't
weigh, before their first note, and the Tools sheet says what happens and lets them choose the server. The
progress in the player makes the one slow first time visible.

### Serving the bundle

- `GET /render/bundle.json`: which two folders are current, the program, the sizes. `Cache-Control: no-cache`.
- `GET /render/py-<hash>/…` (Pyodide 314.0.7 and five packages: numpy, scipy, soundfile, cffi, pycparser; 29.9
  MiB, 23.1 on the wire) and `GET /render/app-<hash>/…` (the worker, the kernels, the program; 5.2 MiB, 5.0 on
  the wire). Each folder is named by a hash of its files, so every file is `public, max-age=31536000,
  immutable`: fetched once per visitor, from the HTTP cache after. A new program fetches only its 5 MB; a new
  Pyodide, the rest. Text and wasm files are stored gzipped beside themselves and sent so to a browser that takes
  gzip (pyodide.asm.wasm 9.2 MiB, 3.4 sent). Only the two folders, only plain names (no dot files, no climbing,
  no directory listings), only `.mjs .js .wasm .json .zip .whl`.
- **The policies.** The page's is as strict as before, with `media-src 'self' blob:` added (a song made in the
  browser plays from a Blob) only when the bundle is served. The bundle's files carry their own policy, which the
  worker keeps (a dedicated worker takes its script's): `default-src 'none'; script-src 'self' 'wasm-unsafe-eval';
  connect-src 'self'`. Pyodide compiles WebAssembly, so `'wasm-unsafe-eval'`; `'unsafe-eval'` isn't needed (tried
  in Chrome 152: Pyodide, numpy and scipy load without it). Chrome enforces it in the worker (tried: without
  `'wasm-unsafe-eval'` Pyodide can't compile; the worker reports the violation and the server makes the song within
  a second). No cross-origin isolation is needed (no
  SharedArrayBuffer). Workers come from `'self'` under the page's `script-src`.
- **Limits.** A browser's render isn't counted against `records` or `previews` and never waits in the queue; the
  spec is a request like `/api/song` (tens of milliseconds, within `requests`), and so is every file of the bundle.
  The queue and the hourly limits now hold only what the server makes: phones, tablets, fallbacks, and visitors
  who chose the server.

### Byte identity

Checked three ways: natively (tests/test_studio_browser.py, a section and a recording made from their specs are
the studio's own, byte for byte), in Pyodide under node from the built bundle (web/studio-wasm/bench/identity.sh,
the same Python, packages and kernels as the worker), and in Chrome 152 (the built-in browser, the public studio
on this Mac, machine `fictional:wren`).

| what | browser (Pyodide) vs server | id |
|---|---|---|
| H, turn (section 2) | identical | `1a107628c193…` |
| H, refrain 1 (section 1), tempo 92 | identical | `80c694a9ec06…` |
| H, refrain 1, Chrome, from the page's ▶ | identical | `d320a6020835…` |
| H, turn, tempo 92 and 95, Chrome | identical | `096114786424…`, `ae2bdb6fdda8…` |
| H, turn 2 (section 5), roll 2 | identical | `3908c953318e…` |
| B, section 1 | identical | `1605ac5b672d…` |
| B, whole song (a recording) | identical: samples, record, every packet member | `288c16ecbdef…` |
| B, whole song, tempo 70, picking | identical, the same | `27e40e44abd4…` |
| H, whole song | identical, the same | `417585a8574b…` |
| H, whole song, recorded in Chrome (after merging main's drum machine and synth bass) | identical | `417585a8574b…` |
| H, verse 2, tempo 98, Chrome, from the page's ▶ | identical | `24433351e24b…` |
| H, refrain 1, synth folk (the drum machine, the analog synths), node and Chrome | identical | `8405f26c4c5c…` |
| B, whole song, synth folk | identical | `b6fb5e07d050…` |
| H, whole song, roll 2 | **23 of 7.66 M samples differ, by 1 LSB** | `95f79249…` vs the server's |
| H, whole song, tempo 92, roll 1 (Chrome and node) | **1 of 8.47 M samples, 1 LSB** | `73df8752…` vs `f040fd7d…` |
| H, whole song, tempo 98, recorded from the Tools sheet in Chrome | **differs** | `47770304…` vs `24b99913…` |

(Run again on main after the drum machine and the synth bass joined the rhythm, 5974a66: the same.) So: every
section tried and four of the seven whole-song versions are the server's to the last bit, and where the samples are the
same, the record is too (every packet member identical, `program_sha256` the server's). The FLAC's own bytes differ
by the encoder (Pyodide's libFLAC 1.4.2, the server's 1.4.3), not in what they decode to: the id is the samples'.

**Where they part: the fiddle.** Every part alone and dry, browser against server (bench/stems_diff.py, H whole,
roll 2): the bass, accordion, claps and stomps agree to -243 dB or better below their peaks, the voice and the
voice before to -197 and -192 dB, **the fiddle only to -116 dB**. Pyodide's `sin`, `cos`, `exp`, `tanh`, `log1p`
(musl's, and V8's in the kernels) differ from macOS's in the last bit (all five, on a million values), as the
spike found; everywhere else that stays a -190 dB whisper, but the bowed string's friction is a feedback loop that
grows a last-bit difference in its vibrato (`bowed.tracks`, `np.sin`) into one about 1/20 of an LSB: enough to tip
a sample's rounding now and then in a long song (0, 1, 23 samples). The versions this machine (Wren) sings put the
fiddle in most whole songs. The Linux server and a Mac very likely part the same way, their libm differing too.

What a difference means: the browser's recording is a valid packet (its record's id is its own audio's), plays the
same (1 LSB is -96 dBFS, a handful of samples), and continues the lineage the same; but it isn't the file the server
would have made, and rendering its record again natively gives the server's id, not its own. The cure is the one
docs/BROWSER-RENDER.md names: deterministic `sin`, `cos`, `exp`… in the kernels and on the few hot numpy paths
(here, the bowed string's vibrato), which changes the native renders of fiddle versions once (decision 1 below).

### Time and memory

In Chrome 152 on the M1 Max (a machine shared with other agents), while the page was visible:

- **Getting ready**: 4.8-5.0 s from the cache (Python, numpy, scipy and soundfile, the program, importing every
  instrument); the first time, from a local server, the same plus the download (35 MB in ~2 s here; ~20 s at
  15 Mbit/s).
- **A section**: 2.0 s for a turn (no voice); H's refrain with the voice and a voice before it, 7.7 s in Pyodide
  under node (Chrome within 20% of node in the spike). Native: 1.2 s.
- **A whole song**: 55-62 s for H (Wren's versions: the voice, a voice before it, the band), 18 s for B; native
  9-10 s for H. The spike's 35 s was H's seed with no voice before it.
- **The wasm heap**: a section 224-464 MiB; a whole song 1.14 GiB (B) and **2.0-2.3 GiB for H** with a voice
  before it (the heap grows during the two voices and never shrinks). Chrome's wasm32 ceiling is 4 GB, so it
  fits, but it is past the spike's 1.5 GB target: modest laptops and Safari may fail it, and fall back.
- **A hidden tab is several times slower**: with the page hidden (another tab in front, the window covered), H's
  refrain took 52-72 s and a whole song 333 s. The worker keeps going, and the stall watch is generous for it.

### The deploy

deploy/studio/Dockerfile builds the bundle in a stage of its own (`node:22-bookworm-slim` with uv: the locked
dependencies, `npm ci` for Pyodide, numpy and scipy from Pyodide's CDN checked against its lock file, then
build_render.py from the same program files as the image), and copies only its output (about 35 MB) into
`/opt/studio/render`. Node never reaches the runtime image, and zig isn't needed (the C kernels are committed).
docker-compose.yml passes `--browser-render /opt/studio/render` (`STUDIO_BROWSER` in `.env`; a space turns it
off). The image wasn't built here: Docker's daemon (OrbStack) wasn't running. `docker compose config` checks.

Outside Docker:

    cd web/studio-wasm && npm ci && cd ../..
    uv run python web/studio-wasm/tools/build_render.py renders/render-bundle     # again after any change to songbird/
    uv run songbird studio --public --machine none --browser-render renders/render-bundle

The bundle must be rebuilt with every change to the program (the studio refuses it otherwise, saying so), and the
kernels must be current (build_render.py refuses stale ones, as tests/test_browser_kernels.py does).

### How it was checked

- tests/studio_renderer_browser.test.cjs (node, 11 tests, a stand-in worker): who makes the song (a desktop, not a
  phone, a small memory, no workers; the setting; earlier failures); a section made in the browser (the spec
  asked, the worker's URLs, the first-visit progress, a Blob, kept to play again); a section worker replaced after
  its few, a whole song's worker of its own and terminated, the section's first; a recording's name and download;
  what the server has made asked of it; a crash, running out of memory, a stall and a killed worker each sending the
  render to the server, two failures the visit; cancelling a whole song terminating its worker; the server chosen,
  no bundle, a phone: the queue as ever. tests/studio_renderer.test.cjs and the other node tests unchanged, passing.
- tests/test_studio_browser.py (5): the bundle served for good under its folders, compressed, as wasm, with the
  worker's policy, and nothing else (dot files, other types, climbing, the .gz by name, directories); the page's
  policy with `blob:` only when the bundle is served; a local studio serves none and refuses the flag; a bundle
  from another program refused; a section and a recording from their specs the studio's own byte for byte (the
  recording's packet file too), a spec of another program or shape refused. test_browser_kernels passes.
- In the built-in browser (Chrome 152), `--public --machine fictional:wren --browser-render`: sections from the
  page's ▶ and a recording from the Tools sheet made in the browser, their ids above; the recording's *Download
  it* a Blob under its name, 3:00, one choice marked; the worker killed mid-render (`SongbirdRenderer.debug.kill()`)
  and the section made by the server instead, playing from `/audio/…`; at a phone's width (the mobile preset:
  an Android user agent) the server made it and the Tools sheet said why.

### Decisions for the artist

1. **Byte identity for fiddle versions.** As built, a recording made in the browser is the server's to the last
   bit for every section tried and four of the seven whole songs, and differs by 1 to 23 samples at 1 LSB for the other three (all H with Wren's fiddle; above). Three ways: (a)
   accept it (built; the packet is valid and self-consistent, the difference inaudible, and the Linux server and a
   Mac very likely differ the same way already); (b) have the server make every *recording*, the browser only previews and
   hearing the whole song (a line in renderer.js's `choose`: `kind === "record"` → server; the VPS then does the
   heavy work only when someone records); (c) the determinism work: deterministic transcendental functions in the
   engine, starting with the bowed string's vibrato, changing fiddle, steel and cello renders once (new goldens if
   a golden plays them), after which the browser, Linux and macOS agree. Recommended: (c), with (a) meanwhile.
2. **Whole songs' memory.** 2.0-2.3 GiB of wasm heap for H with a voice before it, past the 1.5 GB target. It works
   in desktop Chrome and falls back elsewhere; the voices' memory (the learned throat run twice) is where to cut.
3. **First use is quiet** (above): no prompt, the progress says "once: 12 of 35 MB". A prompt is a small change
   if wanted.
4. **What the packet says it runs with.** A browser-made packet names the server's Python and pinned dependencies
   (the render is the server's, byte for byte, where it is), not Pyodide's, which no one would run it with.
5. **A browser's recordings aren't counted** against the hourly limits (they cost the server nothing). Someone
   could make many; only their own computer pays.
6. **Safari** qualifies automatically but is untested; if it misbehaves, a line in `capable` sends it to the server.

## Before launch (2026-09-30)

A Fable review of the public studio as built found four launch blockers and a few smaller things. What came of each
(tests in brackets):

| | found | now |
|---|---|---|
| 1 | **A long whole song kills the studio.** Chamber at its slowest, four verses, every part on: 7 minutes, peaking at 4.1 GB on 2 threads against the container's 2.5 GB. The kernel kills the studio mid-render; the queue is lost (since made lean, byte for byte, it peaks at 2.5 GB: still past the budget) | Every whole render (hearing the whole song, recording, the stems) is estimated before it's queued, from its laid-out length and its players, and refused past the studio's budget with a sentence: "This version is 6.9 minutes long, too long for this small server to make in one go (about 4.9 minutes at most with these players): make it in your browser, or shorten it (fewer verses, a quicker tempo)." Below, "A whole song's memory" (test_studio_public, test_studio_browser, studio_renderer_browser) |
| 2 | **Bodies read before their guards**: a take (up to 41 MB) read whole before its Host, token or limits were asked; 64 connections could have the studio hold 2.6 GB | Every POST asks every guard first (the studio's JSON, a take, a file brought). A take also asks, before a byte is read, whether singing is on, the visitor's turn and takes this hour, and room among the takes waiting; two takes are on their way at once, one from each address. A refused body is read and dropped a block at a time (nothing of it held), so the answer still arrives and the connection stays in step (test_web_singing) |
| 3 | **A range read into memory**: a player's `bytes=0-` held the whole song (17 MB) per connection | Ranges are streamed a block at a time, as a whole file is (test_studio_public, with a 20 MB file under tracemalloc) |
| 4 | **The studio's day was fixed at start**: a container up for weeks would sing, and stamp, every version as its first day's | A public studio's day moves on at this computer's midnight (`Studio.roll`, asked at every request): the machine's context, the timeline, the versions someone brought, all opened again on the new day. A render asked for before keeps the version it was asked with, and its record the day it was sung. A local studio keeps its day, as ever (test_studio_public, with a fake clock) |
| 5 | A client without a cookie is a new visitor each time, so one sender could fill the queue | `queue-ip` (3): renders waiting at once from one address, an IPv6 one by its /64 |
| 6 | A slow reader held one of the 64 connections for days | `connections-ip` (16): requests served at once from one address (the real one, from CF-Connecting-IP; past it, 429); and a download is sent no slower than `send-kb` (16 KB/s over its whole time, after a minute) or let go |
| 7 | The page didn't say what an open studio keeps | The footer, Help's "What's kept", and a "What's kept" button in the Tools sheet ("What is logged, and kept", above) |
| 8 | `/api/open` could hold a request 90 s waiting for a reader and 75 s reading, past Cloudflare's 100 s | A file brought takes its reader's place before a byte is read, or is answered at once: "The studio is reading other versions just now; send it again in a minute" (the page, asking first, hears it too); its reader has what's left of 88 s since it was asked, and a file that took most of them to arrive is refused (test_studio_received) |
| 9 | Search engines would list the beta | `--noindex` (the compose passes it: `STUDIO_NOINDEX`, a space to drop it): `X-Robots-Tag: noindex, nofollow` on every reply, and a robots.txt that disallows everything |
| 10 | The plain pages' inline styles were blocked by `style-src 'self'` | In `notice.css`, served to a visitor without the key too |

### A whole song's memory

Measured on 30 September on the M1 Max, `tools/render_memory.py` (the whole process's resident high-water mark,
`MallocLargeCache=0` as the stand-in for Linux): first as the review found it, then after the heaviest parts were made
lean the same day, byte for byte (docs/PERFORMANCE.md, "The heaviest parts"; every rendition below renders to the id
it rendered to before, at one thread and two). Two threads unless said:

| version | length | parts | peak, 2 threads (before → now) | 1 thread (before → now) |
|---|---|---|---|---|
| H's seed (the ballad) | 151 s | bass drone drum fiddle guitar harp lute voice whistle | 1.30 → 1.30 GB | 1.13 → 1.13 GB |
| the ballad, 3 verses, every part | 217 s | the same | 1.61 → 1.57 GB | |
| the ballad, 4 verses, every part, slowest | 347 s | the same | 2.38 → 2.36 GB | |
| chamber | 189 s | cello piano strings voice | 2.16 → **1.30 GB** | 1.91 → 1.26 GB |
| chamber, 2 verses, tempo 60 | 239 s | the same | 2.66 → 1.57 GB | |
| chamber, 3 verses, slowest, every part | 342 s | the same | 3.82 → 2.26 GB | |
| chamber, 4 verses, slowest, every part (the review's) | 413 s | the same | 4.27 → **2.53 GB** | |
| lullaby | 298 s | celesta harp musicbox synthpad voice | 2.01 → 1.69 GB | 2.03 → 1.57 GB |
| ambient | 214 s | drone strings synthpad vibes voice | 2.07 → 1.56 GB | 2.05 → 1.51 GB |
| synth folk | 132 s | arp drummachine guitar synthbass synthlead synthpad voice | 1.14 → 1.15 GB | 1.15 → 0.95 GB |
| lo-fi | 186 s | drummachine epiano synthbass vibes voice | 1.98 → 1.45 GB | 1.97 → 1.36 GB |
| songwriter | 161 s | bass guitar harmonica voice | 1.09 → 1.10 GB | 1.01 → 0.98 GB |
| **country** | 152 s | bass guitar **kit** piano steel voice | 2.36 → **1.43 GB** | 2.09 → 1.29 GB |
| country, 4 verses, every part, slowest | 347 s | the same | (past the container) → 2.41 GB | |
| blues | 165 s | guitar harmonica slide stomps voice | 1.81 → 1.34 GB | 1.69 → 1.11 GB |
| **gospel** | 225 s | claps ebass **kit** organ piano tambourine voice | 2.90 → **1.90 GB** | 2.77 → 1.41 GB |
| gospel, 4 verses, every part, slowest | 507 s | the same | (past the container) → 3.87 GB | |
| indie | 128 s | claps ebass electric glock guitar **kit** organ voice | 2.16 → 1.22 GB | 2.02 → 0.99 GB |
| indie, 4 verses, every part, slowest | 345 s | the same | (past the container) → 2.48 GB | |
| shanty | 151 s | bass claps concertina fiddle stomps voice | 1.66 → 1.13 GB | 1.56 → 1.10 GB |
| string band | 125 s | banjo bass fiddle guitar mandolin voice | 1.12 → 1.12 GB | 0.99 → 0.97 GB |
| a cappella (added 30 September: docs/STYLES.md, "Two more") | 226 s | voice and three voices of the program's own | 1.85 → 1.51 GB | |
| a cappella, six lineage voices | 226 s | voice, choir1-6 | 2.33 → 1.51 GB | |
| a cappella, 4 verses, every part, six voices, tempo 55 | 496 s | the same | → 2.79 GB | |
| a Celtic session (a jig, a slow air) | 120 s | concertina drone drum fiddle guitar voice whistle | 1.07 GB | |
| a Celtic session, 4 verses, every part, a reel at 91 | 347 s | the same | 2.34 GB | |
| house (2026-09-30, new) | 118 s | arp drummachine (a 909) piano synthbass synthpad voice | 0.97 GB | |
| dub, with its version after the song (new) | 221 s | ebass electric kit melodica organ voice | 1.89 GB | |

(The "before" column is the same measure taken again on the tree as the review found it; a few differ from the
review's own figures by a few percent, and two of its drawn-out versions are measured here at the lengths these edits
give: the ballad's 3 verses at 217 s, chamber's 2 verses at tempo 60 at 239 s.)

So the drum kit no longer sets its bands apart: country, gospel and indie are now 7.1 to 7.5 MB for every second of
song on two threads, beside the ballad's 7.0, and chamber's 5.8. What's left is mostly what every render holds (the
program, the band's sums and the voice's bus, two parts being made at once on two threads), which is why the bands
whose heaviest parts were already light (the ballad, the songwriter, the string band, synth folk) are where they were.

**The estimate** (`songbird/public.py`, `render_mb`): 300 MB, and for every second of the song the rate of its
heaviest part, 5% more; more threads more (12% a thread past two, from H's seed on six). A part's rate is the
lightest band's it plays in (the lullaby's 4.7, the songwriter's 5.0), and a band none of whose parts reaches its own
rate that way gives it to its signature part (the kit 7.1, the steel 7.5, the lute 7.0, the cello 5.8...); a part in
no band above, its rate in the ballad's band (`tools/part_memory.py`: H's seed with the whistle's line, or the drum's
strokes, played by it), and a little more; a part never measured, the heaviest rate (7.7). A voice from before adds 1
(a guess); the stems hold every part whole until the zip is packed (0.71 MB a second each). Every measurement above is
at or under its estimate, none by more than 26% (tests/test_studio_public.py, `MEASURED`).

**The budget**: `--limit render-mb`, by default the container's memory less 400 MB (the compose passes
`STUDIO_MEMORY` in; else the cgroup's limit; else 2500 MB): **2100 MB** on the VPS. What it lets the server make in one
go, on two threads, before → now:

| band | rate before → now (MB/s) | minutes in 2100 MB, before → now |
|---|---|---|
| country (kit, steel) | 16.5 → 7.5 | 1.7 → **3.8** |
| gospel (kit) | 16.5 → 7.1 | 1.7 → **4.0** |
| indie (kit) | 16.5 → 7.2 | 1.7 → **4.0** |
| chamber (cello) | 10.3 → 5.8 | 2.8 → **4.9** |
| blues (slide) | 9.2 → 6.4 | 3.1 → 4.5 |
| lo-fi (epiano) | 9.1 → 6.2 | 3.1 → 4.6 |
| shanty (concertina) | 9.0 → 5.6 | 3.2 → 5.1 |
| ambient (strings, vibes) | 8.3 → 5.9 | 3.4 → 4.8 |
| the ballad (lute, whistle, drum) | 7.2 → 7.0 | 4.0 → 4.1 |
| string band (banjo, mandolin) | 6.6 → 6.6 | 4.3 → 4.3 |
| synth folk (arp) | 6.5 → 6.4 | 4.4 → 4.5 |
| lullaby (synthpad, musicbox) | 5.9 → 4.7 | 4.8 → **6.1** |
| songwriter (harmonica) | 4.9 → 5.0 | 5.8 → 5.7 |
| a cappella (the group's voices) | 6.0 | 5.0 |
| a Celtic session (whistle, drum) | 7.4 | 4.1 |
| house (arp) | 6.4 | 4.5 |
| dub (melodica, 2026-09-30) | 7.4 | 3.9 (a dub version of H's own shape is 3.7: it fits; a machine's longer shape, three verses and the bridge twice, is 5 minutes and doesn't) |

(An a cappella's peak grew with its voices until the group's bus was summed as its voices came rather than
held until the last, 30 September, to the bit: 1.85 and 2.33 GB before, for three and six voices, 1.51 after.)

Every style's own default now fits (country's 2.5 minutes and gospel's 3.75 were refused before: they would have
killed the studio). `STUDIO_MEMORY=3g`, if the VPS can spare it, is about a quarter longer each.

**In a browser** (renderer.js, one thread, wasm32): H's whole song with a voice before it took 2.0-2.3 GiB of heap in
Chrome, about 1.7 times its estimate here, and Chrome's ceiling is 4 GiB; a whole song estimated past 3800 MB of heap
(`BROWSER_MB`: the ballad at about 4.4 minutes) isn't given to the browser. The render spec says `server` when the
server can make it instead, or `too_long` with the same sentence ("…too long for this small server or a browser…:
shorten it…") when neither can; the page says it and sends it nowhere. The server, refusing a whole song a browser
could make, says "make it in your browser". Sections are made as ever, in either. (The factor is H's, whose band
changed least; the lean parts are lean in a browser too, one thread and the same code, so the kit's and chamber's
bands should now sit near it as well: worth a measurement in Chrome.)

**A version someone brings**: a public studio opens it only if its next version plays no longer than the longest it
makes in one go with the lightest band (`Studio.most_minutes`: 6.9 minutes on the VPS with the bundle, received.MINUTES' 12
elsewhere), and says so otherwise: "Open it in the studio on your own computer."

Decisions for the artist: the budget's headroom (400 MB for the pages, a take or two on its way, and the reader of a
version brought, which runs beside a render); the browser's factor (1.7, from one version: measure a long ballad, and
now a kit's band, in Chrome to tighten it). The kit's memory, the open question here before, is fixed: every style
with a kit makes about 4 minutes on the server.

### Cloudflare: cache the bundle

Cloudflare caches by extension, and `.wasm`, `.mjs`, `.whl` aren't among its defaults: without a rule, every first
visit's 28 MB comes from the VPS. Rules > Cache Rules > Create rule: *When* `URI Path` *starts with* `/render/`, *then*
Cache eligibility: **Eligible for cache**, Edge TTL: **Use cache-control header if present** (the bundle's files say
`public, max-age=31536000, immutable`; `bundle.json` says `no-cache`, so it isn't kept, and a new program is seen at
once). Browser TTL: respect the origin. Check with `curl -sI https://studio.itsby.you/render/<app-…>/<a file>`
twice: `cf-cache-status: HIT` the second time.

### The checklist

Before opening it (Cloudflare Access first, for the beta: "A closed beta first", above):

1. **Build with the try override** and open it on 127.0.0.1:8766:
   `docker compose -f deploy/studio/docker-compose.yml -f deploy/studio/docker-compose.try.yml up --build studio`.
   The bundle stage runs; the studio's start says "Made in the visitor's browser…" and "Singing in the browser: on".
2. **`docker stats`** while recording H's seed (under 1.5 GB), then while asking for the review's long chamber
   version (refused at once, nothing queued) and a chamber version just under the budget (under 2.1 GB). If Linux
   peaks higher than the Mac, lower `render-mb` or raise `STUDIO_MEMORY`.
3. **Disk**: `df -h` on the VPS, and `docker builder prune` after the build (the bundle's stage leaves ~2 GB of
   layers); the volume grows to about 1.5 GB (previews, downloads, versions, the compiled synthesis).
4. **The compiled synthesis built on the VPS**: the image's numba cache is for the build machine's CPU; the first
   render after a start compiles what doesn't match (10-15 s, kept in the volume). Let `warm` run once (the start
   message, then the first verse), then record once before inviting anyone.
5. **The Secure cookie**: cloudflared must pass `X-Forwarded-Proto: https` (it does by default); check the page's
   `Set-Cookie` carries `Secure` through the tunnel (`curl -sI https://studio.itsby.you/`).
6. **CF-Connecting-IP believed**: the studio believes it only from a private network; check the compose network's
   subnet (`docker network inspect songbird-studio_inside`, usually 172.16.0.0/12) is among the private ranges
   (`public.NEAR`), and that two devices on different networks are counted apart (a 429 on one isn't on the other).
7. **/dev/shm with a read-only root**: numba and the measuring process use shared memory; `docker compose exec studio
   df -h /dev/shm` (Docker gives 64 MB by default; `shm_size: 256m` if a take's measuring fails with "no space").
8. **The seed's id in the container**: render H's seed there
   (`docker compose exec studio songbird render songs/h-now-its-by-you.json --machine none --out /tmp/h.flac`, if the
   read-only root allows /tmp) and compare its id with the Mac's (`9b0766353b73…`): whether Linux and macOS already
   part (the fiddle's last bits, "Byte identity" above).
9. **Cloudflare Access** in front for the beta (Zero Trust > Access > Applications), the cache rule above, and
   `STUDIO_NOINDEX` left as `--noindex`.
