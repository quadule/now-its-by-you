# The studio on a server: the first plan (September 29-30, 2026)

*History: the first design for a public studio, where a server made every version, written September 29-30, 2026.
It was built (`songbird studio --public`, deploy/studio/) and tested, but never deployed: studio.itsby.you runs
entirely in the visitor's browser instead ([WEB-STUDIO.md](../WEB-STUDIO.md)). Kept as it was written, without the
details of the host it was meant for.*

The artist wants the studio public, for good, so experienced musicians can
make their own versions of the song. `songbird studio --public` is that mode,
and `deploy/studio/` puts it in a container on a small server (or on the
desktop as a fallback), reached only through a Cloudflare tunnel at
something like `https://studio.itsby.you`.

The local studio is unchanged: 127.0.0.1, no key, standard library only,
offline, quiet. The shared preview (`--host`, `--allow-host`, `--key`:
docs/STUDIO.md, "Sharing the studio for a preview") is unchanged too. Public
mode is a third way, built on the shared one.

## What public mode is

    songbird studio --public [--allow-host studio.itsby.you] [--host 0.0.0.0]
                    [--client-ip-header CF-Connecting-IP] [--limit NAME=N ...] [--key WORD] [--machine none]
                    [--browser-render DIR]     (the song made in desktop browsers: docs/WEB-STUDIO.md, "Made in the visitor's browser")

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
| `render-mb` | STUDIO_MEMORY less 400 | the most a whole song may take to make here: one estimated past it is refused before it's queued (docs/WEB-STUDIO.md, "A whole song's memory") |
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
  kills the studio (and Docker restarts it) rather than anything else on
  the host; if the host itself runs short, the studio is the first to go.
  The studio's only network is `internal`: it can be reached by the tunnel
  and reaches nothing. The tunnel (cloudflared, 128 MB, half a CPU) is on
  that network and one with a way out; it dials Cloudflare, so the host
  opens no port.

What happens when the studio dies mid-render (out of memory, or a restart):
the queue is gone; each waiting page's next poll gets "no such job" and says
so where it was waiting; asking again starts over. Finished previews and
downloads are on the volume and survive.

## Memory

Since 2026-09-29 (docs/notes/PERFORMANCE.md, "Memory (2026-09-29)") a whole render
peaks at about 1.33 GB with 2 threads and 1.13 GB with 1, the output byte for
byte what it was (it was 3.2 GB). Those are macOS figures with
`MallocLargeCache=0`, the nearest stand-in for Linux, which hands large freed
arrays straight back; the compose file sets `MALLOC_ARENA_MAX=2` and
`MALLOC_MMAP_THRESHOLD_=1048576` so glibc does. A measuring process for
singing (under 900 MB) never runs beside a render: they share one queue. So
the 2.5 GB cap holds H's seed with room for the server and its pages; but
not every version (a long one, or one
with a drum kit): docs/WEB-STUDIO.md, "A whole song's memory", is how the studio keeps a
render inside the cap. **Measure it once in the container before
opening it** (`docker stats` while a whole song is recorded, or
`tools/render_memory.py`): these figures are from a Mac, not the VPS.

To check a new program before deploying: `SONGBIRD_THREADS=2 /usr/bin/time
-v uv run songbird render songs/h-now-its-by-you.json --machine none --out
/tmp/x.flac` on Linux ("Maximum resident set size"), or watch `docker stats`
while a recording is made in the container.

## Deploying on the VPS

This project publishes no ports and has its own networks, so it never meets anything
else the server runs.

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
- **The VPS**: the studio takes up to 2.5 GB of its memory and 2 CPUs
  while rendering, idles at a few hundred MB; disk about
  1 GB for the image and up to 1.5 GB for the volume (previews, downloads,
  logs). Traffic: a section is about 1.6 MB, a recording about 17 MB, so
  1,000 recordings a month is about 20 GB out, within any VPS's allowance.
  With the song made in visitors' browsers (docs/WEB-STUDIO.md, "Made in the visitor's
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

## Before launch (2026-09-30)

A Fable review of the public studio as built found four launch blockers and a few smaller things. What came of each
(tests in brackets):

| | found | now |
|---|---|---|
| 1 | **A long whole song kills the studio.** Chamber at its slowest, four verses, every part on: 7 minutes, peaking at 4.1 GB on 2 threads against the container's 2.5 GB. The kernel kills the studio mid-render; the queue is lost (since made lean, byte for byte, it peaks at 2.5 GB: still past the budget) | Every whole render (hearing the whole song, recording, the stems) is estimated before it's queued, from its laid-out length and its players, and refused past the studio's budget with a sentence: "This version is 6.9 minutes long, too long for this small server to make in one go (about 4.9 minutes at most with these players): make it in your browser, or shorten it (fewer verses, a quicker tempo)." docs/WEB-STUDIO.md, "A whole song's memory" (test_studio_public, test_studio_browser, studio_renderer_browser) |
| 2 | **Bodies read before their guards**: a take (up to 41 MB) read whole before its Host, token or limits were asked; 64 connections could have the studio hold 2.6 GB | Every POST asks every guard first (the studio's JSON, a take, a file brought). A take also asks, before a byte is read, whether singing is on, the visitor's turn and takes this hour, and room among the takes waiting; two takes are on their way at once, one from each address. A refused body is read and dropped a block at a time (nothing of it held), so the answer still arrives and the connection stays in step (test_web_singing) |
| 3 | **A range read into memory**: a player's `bytes=0-` held the whole song (17 MB) per connection | Ranges are streamed a block at a time, as a whole file is (test_studio_public, with a 20 MB file under tracemalloc) |
| 4 | **The studio's day was fixed at start**: a container up for weeks would sing, and stamp, every version as its first day's | A public studio's day moves on at this computer's midnight (`Studio.roll`, asked at every request): the machine's context, the timeline, the versions someone brought, all opened again on the new day. A render asked for before keeps the version it was asked with, and its record the day it was sung. A local studio keeps its day, as ever (test_studio_public, with a fake clock) |
| 5 | A client without a cookie is a new visitor each time, so one sender could fill the queue | `queue-ip` (3): renders waiting at once from one address, an IPv6 one by its /64 |
| 6 | A slow reader held one of the 64 connections for days | `connections-ip` (16): requests served at once from one address (the real one, from CF-Connecting-IP; past it, 429); and a download is sent no slower than `send-kb` (16 KB/s over its whole time, after a minute) or let go |
| 7 | The page didn't say what an open studio keeps | The footer, Help's "What's kept", and a "What's kept" button in the Tools sheet ("What is logged, and kept", above) |
| 8 | `/api/open` could hold a request 90 s waiting for a reader and 75 s reading, past Cloudflare's 100 s | A file brought takes its reader's place before a byte is read, or is answered at once: "The studio is reading other versions just now; send it again in a minute" (the page, asking first, hears it too); its reader has what's left of 88 s since it was asked, and a file that took most of them to arrive is refused (test_studio_received) |
| 9 | Search engines would list the beta | `--noindex` (the compose passes it: `STUDIO_NOINDEX`, a space to drop it): `X-Robots-Tag: noindex, nofollow` on every reply, and a robots.txt that disallows everything |
| 10 | The plain pages' inline styles were blocked by `style-src 'self'` | In `notice.css`, served to a visitor without the key too |

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
   part (the fiddle's last bits: docs/WEB-STUDIO.md, "Byte identity").
9. **Cloudflare Access** in front for the beta (Zero Trust > Access > Applications), the cache rule above, and
   `STUDIO_NOINDEX` left as `--noindex`.
