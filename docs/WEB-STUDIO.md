# The studio on the web

How https://studio.itsby.you works:

- **It runs in the visitor's browser.** The site is static files on Cloudflare (web/studio-site: a Worker in front
  of Workers Static Assets). The page's questions are answered by the studio's own Python, the same code as
  `songbird studio`, run in the browser by Pyodide, with the program's compiled loops translated to JavaScript and
  WebAssembly. Every song is made there, phones included; no server makes a version ("On the device").
- **Two things reach the site**: a version someone chooses to share (*Share it* sends the recording's file as it is)
  and a shared link being opened (`/v/<id>`). A shared file is kept for 30 days after it was last shared or opened;
  no address is stored, and nothing lists versions ("Hosted on Cloudflare").
- **Everything else stays in the browser**: the edits, the versions opened, the ways of singing made. A first visit
  fetches about 14 MiB before the song can be edited and about 28 MiB once something is sung; later visits use the
  browser's cache.
- **Singing** (the Sing view) is measured on the device; the recording is deleted and only numbers are kept
  ([WEB-SINGING.md](WEB-SINGING.md)).
- **The same samples as on a computer**, for every section tried and some whole songs; other whole songs differ in a
  handful of samples by the last bit ("Byte identity").

To build it and try it on this computer, and to deploy it:

    uv run python web/studio-wasm/tools/build_site.py renders/studio-site     # the site (Node once: npm ci in web/studio-wasm)
    uv run python web/studio-wasm/tools/serve_site.py renders/studio-site     # try it: http://127.0.0.1:8820
    cd web/studio-site && npx wrangler deploy                                  # "Deploying it", below

The program also has a server mode, `songbird studio --public` (deploy/studio/), which is tested but not deployed;
its design is [history/web-studio-server-plan.md](history/web-studio-server-plan.md). Parts of this page that apply
to it say so.

## On the device

The site has no studio server behind it. Every question the page asks (`/api/*`) is answered in the visitor's
browser by the studio's own Python, with the same JSON as `songbird studio`. The only requests that reach a server
are the Worker's `POST /api/versions` and `GET /api/versions/<id>`: a version someone chose to share.

    uv run python web/studio-wasm/tools/build_site.py OUT [--machine browser|none|fictional:NAME] [--no-singing] [--days 400]
    uv run python web/studio-wasm/tools/serve_site.py OUT                                     # try it: 127.0.0.1:8820

### Architecture

    page (index.html, studio.js, score.js, …)                       the hosting Worker
      │ fetch("/api/…")                                              ▲ POST /api/versions        (Share it)
      ▼                                                              │ GET  /api/versions/<id>   (a /v/<id> link)
    device.js: the page's fetch, wrapped ────────────────────────────┘ the only network calls
      │ postMessage
      ├─▶ the studio's worker (one, the whole visit)   studio-worker.mjs + py/studio_device.py: a DeviceStudio,
      │     answering /api/start, /api/song, /api/options, /api/arrangement, /api/sound, /api/compare, /api/export,
      │     /api/piano, /api/players, /api/notes-in, /api/keep-words, /api/timeline, /api/phrasings, /api/job/*,
      │     /api/render/spec, /api/sing* through studio.asked and studio.answer: the server's own routes
      ├─▶ a reader worker (one per file, let go after) received.examine: a version's file, read as data
      └── renderer.js ─▶ render workers                 studio_render.py: a section's worker (kept for four),
                                                        a whole song's (its own, terminated after)

- **The page's shim** (web/studio-wasm/device.js; only the static page loads it, first of its scripts) wraps
  `window.fetch`: a request to this site's `/api/…` (except `/api/versions`) is posted to the studio's worker and
  answered with the server's status and JSON, so studio.js, score.js, export.js, learn.js, players.js, perform.js,
  drafts.js and author.js ask as they would of a server. Everything else (the page's files, the bundle,
  `/api/versions`) goes to the network. A Service Worker could also catch `<audio src>`, downloads and the piano tab,
  but it is stopped when idle, losing the Python in it; renders are Blob URLs, and the two answers that are files
  (the MIDI file, the piano score) are handed over as a Blob and as localStorage.
- **The studio's worker** is the render worker's script (studio-worker.mjs) with four more commands (`studio`,
  `request`, `restore`, `read`), running web/studio-wasm/py/studio_device.py: a `DeviceStudio` (a `Studio` with no
  thread, since Pyodide can't start one; no limits; no checkout beside it) and a `Device`, which routes each request
  through the functions the server's Handler calls: `studio.asked` for the GET questions and `studio.answer` for the
  JSON posts, with the server's statuses for the same refusals. Requests are answered one at a time, the timeline
  last.
- **Renders** are made by the render workers (renderer.js, studio_render.py: "Made in the visitor's browser"). The
  render spec is asked of the studio's worker, so nothing is worked out twice.

**Two kinds of worker.** The studio's worker holds 130 MiB once ready, and 187 MiB after every question including the
timeline. A whole song's render worker reaches 1.3 to 2.3 GiB and never gives it back (wasm memory doesn't shrink).
Kept apart, the page answers at once while a song is made (Python is one thread), and the render's heap goes when
the recording is done. The cost is a second Pyodide (130 MiB, about 5 s to start from the cache): at the peak, about
190 MiB + 1.3-2.3 GiB in two wasm memories. Reading a version's file takes a third, short-lived one.

**What's kept, and where** (the page says it in its footer, "Nothing leaves this device unless you share a
version.", in Help's *What's kept*, and in the Tools sheet's "Made on this device."):

- In this browser: the edits (localStorage); the versions opened (IndexedDB `songbird-studio`: the cleaned record,
  the song, the timeline, never the audio); each day's timeline; the ways of singing made; the latest three piano
  scores; the bundle in the HTTP cache. A recording is a Blob in the page's memory until the page closes; *Download
  it* keeps it.
- On the site: only a version the visitor chose to share (*Share it*: the recording's file as it is), and what any
  site sees (which files were fetched, which `/v/<id>` was opened). A file the visitor brings is read and kept on the
  device, never uploaded; its address is `/#version=<id>`, a fragment, so even its id never reaches the host.
- The day is the visitor's own (their browser's date).
- The stems are made on the device a part at a time. `/api/export` answers them with the whole song's spec, of kind
  `stems`, and the renderer makes them in a render worker of its own (studio_render.stems_zipped, renderer.js
  `stems`). Each part's FLAC is handed to the page as soon as it is made and let go in the worker, so the worker holds
  one part's samples at a time; the page keeps each as a Blob and zips them, stored, with the MIDI file and the note.
  Every file is the server's own (Studio._stems) to the byte. The band is made before the singers, so the slow parts
  are made last; one gain is shared by all, so a part made before a louder one is made again, quieter (on H, the
  band's parts before the drum). The recording isn't made first: the zip is named as the server names it before its
  recording (`<song>.<day>.<key's first six>.stems.zip`), or after the recording if the page has made it. H's stems
  (19 parts, ?new, Chromium on this desktop): 215 s, the worker's heap at most 1.2 GiB (the voice), against 2.0-2.3
  GiB for the whole song.

### The page

- **device.js**: at `/v/<id>` it looks in IndexedDB first, else fetches `/api/versions/<id>` and reads it; at
  `/#version=<id>` it looks only in IndexedDB ("This version was opened from a file, and this browser doesn't keep it
  any more. Open the file again."). Either way the page's token becomes `device.<id>`, so every request names its
  version as the server's token does (`<token>.<id>`). A version that can't be found or read replaces the page with
  the notice "This version isn't here". A version kept by an earlier program is read again (a shared one) or asked
  for again (a file). If the studio's worker dies (for memory), the next request starts it again. A reader gets 3
  minutes to get ready and 6 to read.
- **renderer.js**: on the device (the page's `studio-render` meta says `device`) every song is made in this browser,
  with no check of the device. A failure is said as it is, with what may help, never blaming the device first ("it
  ran out of memory in this browser. A shorter version (fewer verses, a quicker tempo) may fit, or a computer.";
  "the browser stopped it, perhaps for want of memory…"; "it stopped making progress…"). A whole song estimated past
  what a browser holds (`public.BROWSER_MB`) is warned of in its progress and made all the same ("a long version (6.1
  minutes), which may need more memory than a browser has"). A whole song is marked in localStorage while it's made,
  so a page the browser closed for memory (iOS does, with no error) says so when it's opened again.
- **studio.js**: the device's words (`applyDevice`); *Share it* beside *Download it* after a recording (the file
  posted to `/api/versions`; the link shown with *copy the link*; the Worker's `{error}` said as it is); the version
  bar says "which you opened from a file" (no link) or "which someone shared" (its link); the timeline is asked for
  only when *Time* is opened; a file opened reloads the page on its `#version=`.
- **export.js** saves a Blob under its name; **learn.js** opens only a `/piano/` address; **piano.js** reads
  `?score=device/<key>.json` from localStorage. Built with `--no-singing`, the singing note says "Singing here isn't
  available yet."

### Singing

Singing is in the site unless it is built with `--no-singing`: the Sing view, the fourth beside Page, Arrange and
Mix. It is the server's singing (webstudio.singing's `Singing`: the offer, guide, checks, queue, keep and forget, in
the studio's worker), with the guide's melody, the template singer's analyses and the take's measuring done in
workers of the page's own ([WEB-SINGING.md](WEB-SINGING.md), "The Sing view" and "In the studio's page"). In short:

- **What is sung is the version on the page**: the studio's worker lays the guide from the page's edits (or the
  released version, webstudio/released.json), at a speed and in a key for a voice. A singing worker (the full one:
  the whistle is a kernel) makes a section's melody (about 1 s) and the template singer's part (about 6 s) when
  they're first wanted, kept in IndexedDB (`songbird-singing`), and is let go when idle.
- **The take never reaches the studio's worker.** device.js sends it only where the take was sung and its length;
  the studio checks and queues it (`Singing.take(meta, None, seconds=…)`), then hands out the measuring request
  without audio (`Device.handout`). The page starts a measuring worker for that take (studio-worker.mjs, `init` with
  `lean`, then `kit` and `measure`), hands it the guides and templates it needs, moves the audio to it, and ends it
  when it answers, so the measuring's memory (about 390 MB for a section) is given back at once. Its answer
  finishes the job in the studio's worker through `Singing._measure` (`Device.measured`); the page polls
  `/api/job/<id>`.
- The ways of singing made are kept in IndexedDB and given back at start; *Forget my singing* forgets every one
  kept, and clears what singing made.

### For the host: the build and site.json

The hosting Worker is web/studio-site ("Hosted on Cloudflare"): Workers Static Assets serve the built site, and its
Worker answers `/api/*` and `/v/*`. `uv run python web/studio-wasm/tools/build_site.py renders/studio-site` runs
`npm ci` in web/studio-wasm if needed and refuses stale kernels (about 40 s, most of it the first answers below, in
up to eight processes; `--days 0` skips them); then wrangler's `[build]` runs `tools/prepare.mjs`, which checks
site.json against its rules and writes `_headers` and `.assetsignore`. The build writes:

    OUT/index.html, *.js, *.css   the page, from the root: device.js, renderer.js, studio.js, score.js, model.js, …
    OUT/notice.css                the plain pages' look
    OUT/piano/                    index.html (its addresses made /piano/…), piano.js, sound.js, piano.css, identity.css
    OUT/render/bundle.json        {"v", "base": "/render/", "pyodide", "app", "packages", "bytes", "studio_bytes",
                                   "transfer", "program", "pyodide_version", "studio": {"song", "machine", "runs_with",
                                   "singing"?, "opens"?}, "first"?: {"folder", "from", "to"}}  (bytes: what a render
                                   worker fetches, studio_bytes the studio's worker: each counted as it arrives)
    OUT/render/py-<hash>/         Pyodide 314.0.7, numpy, scipy, soundfile (29.9 MiB)
    OUT/render/app-<hash>/        the worker, the kernels (JS and C/wasm), songbird.zip: the program, studio_render.py,
                                  studio_device.py, the lead song, webstudio's singing (5.3 MiB), and singing's
                                  measuring (singing.zip, world/; not with --no-singing)
    OUT/render/first-<hash>/      the page's first answers, <day>.gzip a day (gzip'd JSON, 42-49 KB; 402 days, 17 MiB:
                                  "A quicker start")
    OUT/site.json                 for the host (below; .assetsignore keeps it off the site)

About 50 files and 36 MiB, and 402 more (17 MiB) of first answers. The host compresses (no `.gz` siblings). The
largest file is scipy's wheel, 13.4 MiB; the build refuses any file over 25 MiB. The machine is each visitor's
browser by default (`--machine browser`: "Each visitor's browser"); `--machine none` sings as time alone, and
`--machine fictional:NAME` as a made-up machine. **Every address is from the root** (`/studio.js`, `/render/…`, the
workers' URLs, the piano page's files): the page is served at `/v/<id>` too, and its policy allows no `<base>`.

**site.json** (prepare.mjs reads `files` and checks each `cache` against its rules):

    {"v": 1, "program": "<the program's sha256>",
     "index":    {"/": "/index.html", "/piano/": "/piano/index.html"},
     "rewrites": [{"from": "/v/*", "to": "/index.html", "status": 200}],
     "network":  {"POST /api/versions":  {"body", "most_bytes": 67108864, "starts_with": "fLaC", "answers"},
                  "GET /api/versions/*": {"answers", "headers": {...what a shared version is sent with}}},
     "headers":  {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"},      (on every file)
     "files":    {"/index.html": {"type": "text/html; charset=utf-8", "cache": "no-cache", "csp": "…"},
                  "/render/app-…/studio-worker.mjs": {"type": "text/javascript; charset=utf-8",
                                                      "cache": "public, max-age=31536000, immutable", "csp": "…"},
                  …every file, by its path}}

- **Cache**: everything under `render/py-*`, `render/app-*` and `render/first-*` is immutable (named by its contents'
  hash); the page, its scripts, `bundle.json` and the piano page are `no-cache` (a 304 when unchanged). A new program
  changes `app-<hash>` (5 MB to fetch); a new Pyodide, `py-<hash>`.
- **The policy** (web/studio-site/src/policy.js), on the page and on the workers' scripts alike:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; media-src 'self'
  blob:; connect-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`, with
  `'wasm-unsafe-eval'` for Pyodide (never `'unsafe-eval'`) and `blob:` for the songs made here. It also lets in
  Cloudflare Web Analytics, which the zone injects into each page a browser asks for: its beacon from
  `https://static.cloudflareinsights.com` (`script-src`) reporting a page view, with no cookies, to
  `https://cloudflareinsights.com` (`connect-src`), those two hosts and no other. The device's foot says so: "The
  site counts visits (Cloudflare Web Analytics, no cookies)". The page needs no inline script or style, no `blob:`
  worker and no fetch of a `blob:` URL (a recording's file is kept as a Blob for *Share it*). build_site.py's
  `POLICY` is held to policy.js's by a test.
- **Types that matter**: `.wasm` as `application/wasm` (compiled as it streams), `.mjs` as JavaScript.
- **The Worker's own paths, never rewritten to the page**: `/api/versions` and `/api/versions/*`. *Share it* posts
  the recording's bytes with `X-Content-SHA256` (one `crypto.subtle.digest`), so the Worker needn't hash 20 MB; the
  answer is 201 `{"id", "url"}` or 4xx `{"error"}`, said as it is. The page fetches `/api/versions/<id>` as bytes
  (it is an attachment; the page never navigates there), reads it only as data, and takes back only an id of 32 hex
  digits.
- serve_site.py does the same on 127.0.0.1 with a stand-in for the Worker (its headers from site.json, the digest
  checked); `wrangler dev` in web/studio-site (launch.json "studio-site", 127.0.0.1:8813) is the real thing, over
  `renders/studio-site`.

### What a recording names

A recording made on the device names the release's Python and pinned dependencies, not Pyodide's 3.14 and its
numpy, which a listener's uv would then try to fetch: the build records them (`Studio.runs_with`, natively) in
bundle.json, and the device's specs carry them (tests/test_studio_device.py compares them with a native studio's).
A version's id from a file is a fixed-key HMAC of what was read (the same file, the same id, any visit); a shared one
keeps the Worker's id; the path wins over the fragment.

### Measurements

On the M1 Max, shared with other work (a load average of 8 to 19, so slower than an idle machine), in Chrome 152 in
the app's built-in pane (mostly hidden, which throttles the page's timers) from serve_site.py, and in node (Pyodide
under node from the same built site, web/studio-wasm/node/device_run.mjs, each worker a Pyodide of its own):

| | Chrome | node |
|---|---|---|
| a question (`/api/song`, `/api/arrangement`, `/api/sound`) | | 0.6-0.7 s the first time, 0.05 s again |
| the timeline (once a day, then kept) | | 5.1-6.7 s |
| **a section** (refrain 1, its worker's start included) | 14.2 s (9.4 s making it) | 5.2 s start + 10.3-12.7 s |
| **a whole song** | 118-123 s | 117 s (synth folk), 185 s (songwriter) |
| a version's file read (15.8 MB; a recording 19.0 MB) | 70 s and 280 s at a load of 19 to 23; once kept, a reload opens it from IndexedDB | 5.2 s start + 9.6 s; 12.5 + 28.8 s |
| **wasm heap** | | the studio's worker 130 → 187 MiB; a reader 187 MiB; a section 387 MiB; a whole song 1.30-1.56 GiB, 2.0-2.3 GiB for H with a voice before it |

The time to the page's first answers is in "A quicker start". A phone's viewport (the mobile preset, 375 px) made
verse 1 in the browser, identical to the native render. A real phone is untried: expect a few times these numbers,
and a whole song's 1.3-2.3 GiB is the risk.

### Tests

- tests/test_studio_device.py: every JSON route answered as a native studio answers it; `/api/start` saying the
  device and what it can't do; the server's statuses for bad edits, a bad machine, a body too large; the stems'
  spec, and every file packed a part at a time as the server packs it (studio_render.stems_zipped); a
  render spec the server's but for the release's Python; a long whole song warned of and still specified; the MIDI
  file and piano score handed over; a real packet read as data, restored, opened at `#version=` and at `/v/<id>`; the
  static page, its policies, its files and the Worker's headers.
- tests/studio_renderer_device.test.cjs: a phone makes it, never the server; a recording keeps its file and is marked
  while made; memory, a killed worker and an error each said plainly; a long one warned of and made.
- tests/test_studio_quick_start.py and tests/studio_device_start.test.cjs ("A quicker start");
  tests/test_browser_machine.py ("Each visitor's browser", "The published version first").

### Open decisions for the artist

1. **Byte identity of whole songs** ("Made in the visitor's browser", decision 1): sections and some whole songs are
   the native render's to the bit; others differ by a handful of samples at 1 LSB.
2. **Phones and whole songs.** Nothing is gated. A whole song needs 1.3-2.3 GiB of wasm heap on top of the studio's
   190 MiB; many phones will manage a section and some a whole song. A failure is said, and a crash is said next
   time. Making whole songs lighter is the lever (the voices' memory first).
3. **A shared link costs its first opener** a 15-20 MB download, a Pyodide to read it and the reading (seconds on a
   laptop, perhaps a minute on a phone). Opening the page as soon as the record is cleaned, and checking the audio
   against it in the background, would halve it.
4. **The reader shares the studio's origin.** The file is never run, but if a libsndfile bug let a file take over
   Pyodide, this origin's storage would be within reach; a sandboxed iframe on a separate origin would close that.
   Worth it if the Worker ever serves files it didn't check.
5. **The stems' recording.** On the device they are named after a recording only if the page has made it; the
   server makes the recording first. Making it first would double the time and bring back the whole song's memory.
6. **Safari and Firefox** are untried. If a browser applied the page's policy to the workers instead of their own
   script's, Pyodide couldn't compile, and the page would say "it went wrong in this browser".

### A quicker start

The song is on the page at once, and the studio's worker fetches half as much behind it. The first answers are made
for the version the page opens on: in the default build, the published version as it was released ("The published
version first"); in a build naming one machine (`--machine none` or `fictional:NAME`), that machine's version. A
visitor's own browser can't be answered ahead, so its version (`/?new`) waits for the worker.

**What a visitor sees.** The song's words, the header, the transport, the choices of words, the sidebar, the Arrange
and Mix views and the Sketch, within a fraction of a second of the page arriving. Python loads behind them; until
it's ready, anything that needs it (an edit, *New performance*, Sung, export, opening a version) waits, and if
someone has just pressed or typed something, the page says "The studio is still getting ready: one moment."; the
change shows when it's ready. With an edit saved in this browser, the header says "Getting the studio ready (40%)…"
until the worker has made the song with that edit. On a version's page, or on a day outside the files, the page waits
for the worker.

**How.**

- **The first answers, a day at a time.** The page's first questions (its start, the singing offer, the song, the
  arrangement, the sound, each sung section's other words, the other computers, the sketch's players, the ways of
  singing) are answered by the studio's own code (`studio_device.first_answers`) at build time, natively, for 402
  days (two before the build's date, for a visitor west of it, and 400 from it: `--days`), and shipped as
  `render/first-<hash>/<day>.gzip` (gzip'd JSON, 42-49 KB each, 17 MiB in all; immutable). The words change by day,
  so there is one file a day. They're compressed here because the host can't send a stored `.gz` as gzip without the
  Worker in front of every file; the page unpacks them with `DecompressionStream` (Chrome 80, Safari 16.4, Firefox
  113; without it, the page waits for the worker).
- **The page's day is the worker's.** device.js reads this browser's date once, fetches that day's file beside the
  worker's start, and tells the worker the same day (`config.day`: `DeviceStudio(day=…)`), so both answer for one day
  even across midnight.
- **Answered from the file only while it's true.** A question is answered from the file only if it is asked exactly
  as the file has it (method, path and JSON body with its keys sorted: `studio_device.question`, `device.js
  question()`), before the worker is ready, with no version on the page and no way of singing kept in this browser.
  Anything else waits for the worker. Something that changes the studio's answers (singing kept or forgotten, a
  version opened) ends the file's answers, so nothing after it is answered out of order. Once the worker is ready it
  answers everything.
- **The studio's worker doesn't fetch scipy or soundfile.** It imports the whole program but plays nothing, so it
  loads numpy alone; `py/lazy_imports.py` stands in for scipy and soundfile (`from scipy.signal import sosfilt` gives
  a stand-in that becomes the real function once the package is loaded). No question the studio answers runs either.
  The tables the instruments compute with scipy (the frame drum's membrane modes, the shaker's skin, the struck
  bank's and the oscillators' half-band filters) are made on first use (`functools.cache`); the voice's glide shape
  is left where it is (voice.py's bytes are part of the singing measurement's version), and its stand-in makes it on
  first use. If a stand-in is ever used for real, it raises `lazy_imports.Needed`, and the worker fetches the
  package and asks the same question again (a version's reader does this for soundfile). Render and measuring workers
  load everything. The studio's worker fetches the program and its wheel beside Python rather than after it.
- **The words of loading** say a percentage of what that worker fetches ("Getting the studio ready (40%)…",
  "getting the singer ready (40%)"): bundle.json's `studio_bytes` and `bytes`, counted as they arrive.

**What it costs.** The first Sung after a visit fetches scipy (14 MB, in the render worker), and the site holds 17
MiB more (402 files; 483 in all, under the 20,000), uploaded again whenever the program changes. The day's file
(about 44 KB) is the only extra fetch.

**Measured** (Chrome in the app's pane, mostly hidden, from a stand-in host that compresses as Cloudflare does and
holds the whole server to one bandwidth, nothing cached; the machine shared with other work, loads 4 to 13):

| a first visit | |
|---|---|
| fetched before the page can be edited | 14.3 MiB (Python, numpy, the program) |
| the words on the page, 50 Mbit/s, desktop | 0.07-0.08 s |
| editing ready, 50 Mbit/s, desktop | 4.5 s (at load 10: 10.9 s) |
| the words on the page, 10 Mbit/s, the phone preset | 0.20-0.28 s |
| editing ready, 10 Mbit/s, the phone preset | 13.3-19.3 s (four runs) |
| the studio's worker: making the studio (node) | 1.06 s |
| the first Sung section, 50 Mbit/s, at load 10 (scipy fetched by the render worker) | 69 s |

The Sketch plays before Python is ready. On a phone's 10 Mbit/s the download is most of what's left: 14.3 MiB is
about 12 s.

**Tests.** tests/test_studio_quick_start.py: the page's day is the studio's; the first answers are what a studio
started that day answers, question by question, under the key device.js makes; every question the studio's worker
answers is answered the same with scipy and soundfile stood in for; a stand-in used for real asks for its package;
in Pyodide under node with numpy alone, the build's first answers are the worker's byte for byte.
tests/studio_device_start.test.cjs: device.js answers from the day's file before the worker is ready and never
after; the same key however the page orders its JSON; what changes the studio's answers ends the file's; the worker
is told the page's day; a version's page, a day outside the files, no file, or no `DecompressionStream`: the worker
answers everything.

**Open decisions for the artist**

1. **How many days ahead.** 400 days of first answers is 17 MiB and 40 s of build, uploaded again with each new
   program. A site not deployed for 13 months falls back to waiting for Python. Fewer days (60: 2.6 MiB) would do if
   it's deployed often.
2. **Fetch scipy for the singer ahead of time?** The first Sung fetches it (14 MB); a visitor who only reads, edits
   and plays the Sketch never does. Fetching it once the page is idle would make the first Sung a few seconds quicker
   on a slow connection, at 14 MB for everyone.
3. **Saved edits** (a returning visitor) wait for Python (from the browser's cache: a few seconds).
4. **The timeline** (*Time*) waits for Python and then takes a few seconds; it could be shipped a day at a time too
   (about 13 KB more a day, compressed: 5 MiB for 400 days).
5. **The first question after the worker is ready** pays for importing what it needs (about 1 s in node; more on a
   busy phone); the worker could ask the song once in the background as soon as it's ready.

## Each visitor's browser

`build_site.py --machine browser` (the default) has device.js gather what any page may ask (the languages, the core
count, Chromium's deviceMemory, the dark-mode setting) and a salt it keeps in localStorage, and the studio's worker
reduces them as a computer's quiet reading is (`harvest.browser`, `studio_device.machine_of`; docs/HARVEST.md, "A
visitor's browser"). A machine that gives nothing keeps its parent's style (style.py, `choose_style`), so without
this every visitor on a day would have the same version and the style would never move. The worker sings as
`browser:{salt, signals}`, a spec that is the voice itself, so the render workers, a version's reader and the record
all sing as the same machine. The page says "this browser", and its machine card says what was read ("it speaks
English, and leans to folk modes", "a big machine", "a dark screen"). Nothing leaves the browser but what a recording
or a shared version carries, as on a computer: the reduced numbers and the salt.

The page opens on the published version (next section), answered ahead. This browser's own version waits for the
worker: about 1.4 s after the press on a 24-core desktop with the files cached, and on a phone that pressed at once,
the rest of the 14 MiB first.

Tests: tests/test_browser_machine.py (the reduction, the spec, the musical traits with no uptime, the words, the
device studio singing as the browser and its style moving where `none`'s doesn't); tests/studio_device_start.test.cjs
(the worker is told the browser's facts and the kept salt; the next visit the same salt; a build naming its own
machine reads nothing).

## The published version first

**What a visitor sees.** At `/`, the published version as it was released: its edition's title and date under the
song's ("The first version · as published Monday, September 28, 2026"), its words and settings, the machine "as it
was published" ("nothing chose anything here"), no Time menu (nothing moves it). It is on the page in about 70 ms,
from the build's first answers. On the same line, **Hear your machine's version →**, to `/?new`: this browser's next
version of it (generation 1), with "← the published version" back to `/`. The line above the title links to the
song's page (now.itsby.you). A version someone shared (`/v/…`, `#version=…`) is continued by this browser. A
person's changes can be made on either; each keeps its own (the page's saved edits are keyed by the machine's label).

**How.**

- **The release's record** is webstudio/released-record.json: the packet's manifest.json of the newest edition in
  web/sing/editions.json, byte for byte (`tools/released_record.py THE-EDITION.flac`, which refuses any other file;
  the build refuses a record that isn't the newest edition's). It rides beside the program (build_render.py's
  BESIDE, 100 KB), and the studio's worker opens with it as its parent (`DeviceStudio(parent=…)`), so this browser's
  version continues the published one, as `python3 the-file.flac studio` does on a computer. The edition's date comes
  from editions.json (`released_on`): the released record keeps none.
- **The machine "published"** (`harvest.PUBLISHED`, `explain.Context.published`): the parent with no voice and no
  drift, which `choose_params` gives back as it is: its settings exactly, its words, its phrasing; a person's edits
  on top as on any version. The start says so (`published`: which version, when; generation the parent's own) and
  studio.js draws the header and the button from it (`applyPublished`); the browser's start carries
  `published_offer` for the way back.
- **The build** (`--machine browser`) makes the first answers for the published version (`opens: "published"` in
  bundle.json's studio); device.js opens the worker on "published" unless the address asks for `?new` (or a
  version), and then neither uses the day's file nor reads the browser until it's asked for.

*Sung* on the published version is made by today's program from its settings, so it isn't the released recording
byte for byte (the home page's file is the recording itself).

Tests: tests/test_browser_machine.py (the record is the newest edition's; the published view's settings are the
record's exactly, every first question answered, an edit on top; this browser's is generation 1 and different);
tests/studio_device_start.test.cjs (a build opening on the published version answers from the file and starts the
worker on "published", reading nothing of the browser; `?new` waits for the worker, fetches no day's file and sends
the browser's facts).

## Hosted on Cloudflare

studio.itsby.you is a Cloudflare Worker (web/studio-site) serving the built site from Workers Static Assets, plus a
small API for sharing versions. "Deploying it", below, has the commands.

### Architecture

- **The site** is static: build_site.py writes the studio's page at the root, the render bundle under `render/` and
  `site.json`. Workers Static Assets serves every file from Cloudflare's edge without running the Worker: those
  requests are free and unlimited.
- **The headers** come from `_headers`, which `web/studio-site/tools/prepare.mjs` writes into the built site before
  every deploy and `wrangler dev` (wrangler.toml's `[build]`):
  - every file: the page's Content-Security-Policy, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
    `X-Frame-Options: DENY`, COOP and CORP `same-origin`, HSTS, and a Permissions-Policy (no camera, geolocation,
    payment or USB; the microphone is left to the page);
  - a hashed folder's files (`render/py-…/*`, `render/app-…/*`, any folder named `<word>-<8+ hex>`):
    `public, max-age=31536000, immutable`;
  - `/`, `/index.html` and `/render/bundle.json`: `no-cache`. Any other file gets Workers Static Assets' default,
    `public, max-age=0, must-revalidate`: kept, and checked by its ETag each time.
  - No rule sets a header another rule sets (`_headers` would join them with a comma). If `site.json` names a cache
    policy the rules would serve differently, prepare.mjs refuses the build; it also refuses a file over 25 MiB (the
    static assets' limit for one file) and more than 20,000 files.
- **The policy** is the one under "For the host" (src/policy.js holds it, for both the Worker and prepare.mjs). It is
  on every file, so the render worker (a dedicated worker keeps its script's policy) has it too.
- **Compression.** The bundle's `.gz` copies aren't uploaded (`.assetsignore`): a precompressed copy would need the
  Worker in front of every file (paid requests) to send it as gzip. Cloudflare compresses responses itself, with
  Brotli or gzip, for the types it compresses (JavaScript, JSON, wasm, HTML, CSS among them); `.zip` and `.whl` are
  compressed already.
- **The Worker** runs first only for `/api/*` and `/v/*`:
  - `POST /api/versions`: share a version (below). `201 {"id": "<32 hex>", "url": "/v/<id>"}`.
  - `GET /api/versions/<id>`: the file, `audio/flac`, `public, max-age=31536000, immutable`, its id as the ETag,
    whole or a range, `Content-Disposition: attachment` and its own policy, `default-src 'none'; sandbox`. Every
    fetch is an open, which keeps the version (a HEAD and a 304 too; a 304 only while it is still there). The page
    sends an uncached HEAD when it opens a version the browser already keeps, so its link stays alive for others.
  - `GET /v/<id>`: the studio's page (index.html, with the page's headers and `no-cache`); the page reads the id
    from its address, fetches the file and opens it on the device.
  - anything else under `/api/`: 404, `{"error": "There's nothing here."}`. Every error is `{"error": "<a
    sentence>"}` with a 4xx status (500 if something broke here).
- **R2** (`songbird-versions`, private, bound as `VERSIONS`): `versions/<id>.flac`; `opened/<id>`, when one was last
  opened; `incoming/…`, a file being checked; `keys/address`, the key addresses are counted under. The bucket is never
  public: files are only served through `/api/versions/<id>`. The Worker is only at studio.itsby.you
  (`workers_dev = false`).
- **No robots.txt, no noindex**: the public studio may be found (the artist's choice). prepare.mjs warns if the
  built site ever has one; `/robots.txt` is a 404.

### Sharing a version

`POST /api/versions`, the body a rendition: the FLAC with its packet appended, exactly as a recording is downloaded.
Every guard comes before a byte of the body is read:

1. the page itself: `Sec-Fetch-Site` same-origin and `Origin` this site's, when a browser sends them (a tool sends
   neither, and is held to the same limits);
2. 3 a minute from an address (the rate-limiting binding, counted at each Cloudflare location), an IPv6 address by
   its /64;
3. `Content-Length` said, at least 4 KB and at most **64 MB** (as the studio's reader, `received.UPLOAD`; a
   rendition is about 15 to 25 MB, its packet about 6);
4. this hour's shares, counted in one place, a Durable Object (`Shares`, bound as `SHARES`), which admits or refuses
   each share in one step, so shares arriving together can't all pass the same count: at most 10 tries from one
   address (a refused file counts too), and at most 60 versions kept from everywhere (a place is taken before the
   file is read and given back if it isn't kept, so junk from many addresses can't close sharing for everyone). An
   address is counted only as 64 bits of an HMAC of the hour and the address, under a random key the Worker makes on
   first use (`keys/address`), so a count can't be worked back to an address. The counts go with the hour.

Then the file is stored and checked as data, never run:

- **Its name is its content.** The id is the first 32 hex digits (128 bits) of the file's SHA-256. The page sends the
  whole digest as `X-Content-SHA256`, and R2 checks the bytes against it as they're written; a body that isn't the
  file its digest names is refused. Without the header the Worker hashes the file on its way to R2 (one pipeline,
  each chunk hashed before it goes on), which can take more CPU than the free plan's 10 ms a request.
- **Checked before it has a name.** The file goes to `incoming/` first, is checked there, and only then is copied to
  `versions/<id>.flac` (R2 checking the digest again). Whatever stops the Worker half way, nothing unchecked is ever
  under a version's name, and `incoming/` is swept within the hour. Sharing a file that is already there writes the
  same bytes again: only its date changes.
- **Checked from a few ranged reads** of what was stored (src/packet.js; about 100 KB read in all), to the rules
  songbird/received.py holds a file to: it begins with `fLaC` and a STREAMINFO at 44.1 kHz, stereo; the archive's end
  record is the last in its final 64 KB and ends the file; one disk, no ZIP64, at most 512 entries and a 1 MB
  directory right before the end record; every name plain (no `..`, absolute paths, backslashes, NUL, empty parts)
  and listed once; nothing encrypted, stored or deflated only, no data descriptors, no entry growing more than 1000
  times or past 100 MB, every entry between the audio and the directory; `manifest.json` and `genome.json` present.
  Only **manifest.json** is read: its local header must be where the directory says and name it; a manifest declaring
  more than 1 MiB compressed is refused before it is read; it's inflated through a stream that stops at 1 MiB; its
  CRC and size must match; and it must be a record (a 64-hex `id` and `program_sha256`, a title, a whole
  `generation` from 0 to 100,000, a `parent_id` and `ancestry` of ids). The entries' tiling (received.py's `_tiled`)
  is checked on the device. Anything else: `422 {"error": …}` with received.py's sentence ("It isn't a FLAC file…",
  "Its packet lists the same file twice, which no rendition does."), and the file is deleted at once.
- **Nothing in it is ever unpacked or run.** The bytes are kept and served back as they came, as `audio/flac` with
  `nosniff`, `attachment` and a sandboxing policy, so even a file built to look like a page does nothing on this
  site. Everything else (the song, the record against this program's bounds, the samples against the record's id)
  is checked by the studio's reader, on the device, when the version is opened ("Opening someone's version").

### What is kept, and for how long

- **The file itself**, exactly as it was shared, as `versions/<id>.flac`: the device needs the whole file to open
  it. It carries what any copy of it carries (the record, among it the maker's machine's pseudonym, the room and
  leanings: "Privacy", under "Opening someone's version"), and its program.
- **For 30 days after it was last shared or opened.** An open (the file fetched) is noted in `opened/<id>` at most
  once a week, so a version is kept at least 30 days after anyone last opened it, and at most a week more. The hourly
  cron deletes the rest (`KEEP_DAYS`, `REFRESH_DAYS` in `[vars]`), looking at each version again before deleting it.
  A browser that has fetched one keeps its copy (immutable) whatever happens here.
- **Nothing about who shared it.** No IP address is stored: only this hour's counting marks, deleted when the hour
  is over. No logs (`observability` off); errors log only their kind.
- **Nothing lists versions.** An id is 128 bits; one not there answers 404, and an address asking after many is held
  to 20 a minute. An id is a plain content address, so anyone who has a file can work out its link, and could check
  whether it has been shared, or keep a share alive by fetching it. A deterministic render (the seed's child sung
  with no edits on a given day) can be made by anyone, so its link can be found (decision 3 below).

### Deploying it

Once:

1. **Build the site** (Node for Pyodide's package, once: `cd web/studio-wasm && npm ci && cd ../..`):

       uv run python web/studio-wasm/tools/build_site.py renders/studio-site

2. **Install wrangler, sign in, make the bucket**:

       cd web/studio-site
       npm ci
       npx wrangler login                                  # if this computer isn't signed in yet
       npx wrangler r2 bucket create songbird-versions

   Optionally, a backstop if the cron ever stops: `npx wrangler r2 bucket lifecycle add songbird-versions incoming
   incoming/ --expire-days 1`. (Not for `versions/`: R2's rules count from the
   upload, and would delete versions people still open.)

3. **Deploy** (it runs prepare.mjs first, which refuses a site it can't serve; the custom domain makes its own DNS
   record and certificate):

       npx wrangler deploy

Every later deploy: build the site again, then `npx wrangler deploy` from web/studio-site.

**Check after** (`curl -sI` shows headers):

- `curl -sI https://studio.itsby.you/`: 200, the policy above, `cache-control: no-cache`.
- `curl -sI https://studio.itsby.you/render/bundle.json`: `no-cache`. Then a file of the bundle, compressed:
  `curl -sI -H 'Accept-Encoding: br, gzip' https://studio.itsby.you/render/<py-…>/pyodide.asm.wasm`:
  `content-type: application/wasm`, `immutable`, `content-encoding: br` (or gzip).
- `curl -s https://studio.itsby.you/robots.txt -o /dev/null -w '%{http_code}\n'`: 404.
- Singing: `render/bundle.json`'s `studio.singing` is true; in a browser, the Sing view (4) sets out the Page's
  words and makes a section's guide in a few seconds. A template's name may hold "+", which Static Assets would
  redirect to %2B: each part of a kit path is encoded, so a template should load.
- Share the seed (`f` its FLAC; prints the id and link):

      f=web/sing/public/seed/now-its-by-you.flac
      curl -s -X POST -H "X-Content-SHA256: $(shasum -a 256 $f | cut -c1-64)" --data-binary @$f https://studio.itsby.you/api/versions

  then open `https://studio.itsby.you/v/<id>` in a browser: the studio opens on the seed.
- After a day, Workers & Pages > songbird-studio > Metrics: no "Exceeded CPU" errors (if there are, the free plan
  is too tight: Workers Paid is $5 a month).

### Costs

Cloudflare's prices on September 30, 2026:

| | free | beyond |
|---|---|---|
| Static assets (the whole site) | free and unlimited requests, no storage charge; 20,000 files (100,000 on Workers Paid), 25 MiB a file | free |
| Worker requests (`/api/*`, `/v/*`) | 100,000 a day, 10 ms CPU each | Workers Paid: $5 a month for 10 million, then $0.30 a million; 30 s CPU allowed |
| R2 storage | 10 GB-month | $0.015 a GB-month |
| R2 class A (write, list) | 1 million a month | $4.50 a million |
| R2 class B (read, head) | 10 million a month | $0.36 a million |
| Egress (R2 and the site) | free | free |

What each thing costs here:

- **A visit to the studio**: nothing (static assets), however much of the bundle it fetches.
- **Sharing a version**: 5 class A (the hour's list, its two marks, the file into `incoming/` and into its place)
  and about 6 class B (the key, the ranged reads, the copy). About 20 MB stored for at least 30 days.
- **Opening a shared link**: 2 Worker requests (the page, the file) and 1 class B; at most weekly, 1 class B and
  1 class A more.
- **The hourly tidy**: 4 class A an hour (about 2,900 a month) while fewer than 1,000 versions are kept.

So 1,000 shares a month keep about 20 GB (10 GB over the free tier: $0.15 a month); 10,000 shares a month keep about
200 GB ($2.85 a month) and 50,000 class A, well within the free million. 50,000 opened links a day is the free
plan's 100,000 requests. **The most it could cost**, with the hourly ceiling reached every hour for a month by
someone uploading 64 MB files that pass the checks: 43,200 files kept 37 days, about 3.4 TB, about $50 a month
(about $16 at a rendition's real size); lowering `ALL_AN_HOUR` lowers it in proportion. A Cloudflare billing
notification (Manage Account > Billing > Notifications) is worth setting once Workers Paid or R2 has a card on it.
R2 needs a payment method on file even within its free tier.

### Tests

**web/studio-site/test** (`npm test`, node): packet.test.mjs (a rendition is a version; the seed itself, when built;
only the head, the end and manifest.json are read; each way a file isn't a rendition refused with its sentence),
worker.test.mjs (shared with and without the digest, the same id and nothing left incoming; a wrong digest refused;
nothing unchecked ever under a version's name, even with R2 failing mid-check; size asked before the body is read;
another site's page refused; the minute's and the hour's limits, with only digests kept, and shares arriving
together counted one at a time; ranges, HEAD, 304 (an open, and only for a version still there), 405,
404s and the guessing limit; `/v/<id>` with the page's policy; retention through opens, its weekly note and the
cron; a broken bucket a plain 500), prepare.test.mjs (hashed folders, `_headers` with no header set twice,
site.json checked against the rules, a 26 MiB file and a missing index.html refused).

### Decisions for the artist

1. **The limits**: 64 MB a file, 10 an hour from one address, 60 from everywhere, kept 30 days after the last open.
   The ceiling is what bounds the bill (above); raise it if real use reaches it.
2. **Workers Paid** ($5 a month) if the free plan's 10 ms of CPU a request is ever too tight.
3. **Content-addressed ids** let anyone with a file (or who can make it: a deterministic render) find whether it was
   shared. The alternative keeps everything else: the id as `HMAC(a key of the Worker's, the file's SHA-256)`, cut
   to 32 hex; R2 still checks the digest, the same file still gets the same id, and the page learns its link from
   the 201 rather than working it out. A small change in worker.js.
4. **What the site keeps of a shared version, and for how long** (a gallery, deletion, words someone wrote).

## Made in the visitor's browser

The program itself runs in a browser (the spike: docs/notes/BROWSER-RENDER.md): Pyodide, the numba kernels
translated to JavaScript and a few to C/wasm, the same samples as native. On studio.itsby.you every song is made
this way. The local studio renders natively, and the bundle never goes into the song's packet.

    uv run python web/studio-wasm/tools/build_render.py DIR     # the bundle alone; build_site.py makes it for the site

### How it works

1. **The render spec.** The page asks `POST /api/render/spec` (edits, who, section) and the studio answers with
   what its own renderer would be handed: the key it would cache the render under, the player's words, and the spec
   (JSON, sent as a string so the page never reads its 64-bit seeds as floats): the song's file as it is, the
   version's resolved params (`Params.to_dict`), its words (`Lyrics.to_dict`), the phrasing and the voices before,
   the parent's record; for the whole song also the machine, the day (drift), the changes and the person's marks,
   the Python and pinned dependencies the packet names, and the recording's name.
2. **The worker** (web/studio-wasm/studio-worker.mjs, a module Web Worker) loads Pyodide, numpy, scipy and
   soundfile, the kernels (JS, and the 14 C ports as wasm), and the program, and runs
   web/studio-wasm/py/studio_render.py: a section exactly as `Studio._section` makes it (the same `window`, `cut`,
   gain, limiter, `faded`, `to_pcm16`, FLAC), the whole song exactly as `Studio._whole` does (`cli.render_one`,
   packed). Its progress is the studio's (`Job.report` over `stages`). It hands back the FLAC and the record.
3. **The program in the bundle is the studio's**, file for file (`pack.program_files`), so a recording made in the
   browser names the same `program_sha256`. The worker checks the spec's digest against its own before making
   anything. The bundle must be rebuilt with every change to the program, and the kernels must be current
   (build_render.py refuses stale ones, as tests/test_browser_kernels.py does).
4. **The renderer** (songbird/studio/renderer.js) keeps what it made (16 sections, 3 whole songs, as Blob URLs) so
   asking again plays at once, and reports where each was made (`job.where`, `SongbirdRenderer.made`). studio.js and
   score.js ask the renderer.

**Workers.** A whole song is made in a worker of its own, terminated when it's done (a worker that has sung a whole
song holds its 1-2 GB until it goes), and the section worker is terminated before it starts (two heaps at once is
too much). Sections share one worker, replaced after four (its heap only grows) or after three minutes unused.
Cancelling a whole song being made terminates its worker; a section being made finishes and is kept. A worker is
given up on after no word from it for 3 minutes while getting ready, 5 for a section, 10 for a whole song (a hidden
tab's worker runs several times slower, so these watch for a stall), and 40 minutes in all.

**In the server mode** (`songbird studio --public --browser-render DIR`, deploy/studio/: not deployed), the server
serves the bundle at `/render/` (immutable, gzipped copies beside, only `.mjs .js .wasm .json .zip .whl`, with
`media-src 'self' blob:` added to the page's policy and a worker policy of `default-src 'none'; script-src 'self'
'wasm-unsafe-eval'; connect-src 'self'`), checks the bundle's program digest against its own at start, and may
answer `made` to a spec it has already rendered. The renderer then chooses: by default in the browser for a desktop
browser with WebAssembly and workers and (where `navigator.deviceMemory` says) 4 GB or more, on the server for phones
and tablets; the Tools sheet's *Make the song: automatically · in this browser · on the server* overrides it. A
failure sends that render to the server, two failures the rest of the visit, and a whole song that ran out of memory
every whole song after. A browser's render isn't counted against the server's limits. deploy/studio/Dockerfile
builds the bundle in a stage of its own.

### Byte identity

Checked natively (tests/test_studio_browser.py: a section and a recording made from their specs are the studio's
own, byte for byte), in Pyodide under node from the built bundle (web/studio-wasm/bench/identity.sh), and in
Chrome 152.

| what | browser (Pyodide) vs native | id |
|---|---|---|
| H, turn (section 2); tempo 92 and 95 in Chrome | identical | `1a107628c193…`; `096114786424…`, `ae2bdb6fdda8…` |
| H, refrain 1 (section 1), tempo 92 | identical | `80c694a9ec06…` |
| H, refrain 1 (Chrome, from the page's renderer) | identical | `c2e36da52b55…` |
| H, verse 1, tempo 92 (Chrome, the mobile preset) | identical | `91ea074162fe…` |
| H, verse 2, tempo 98 (Chrome) | identical | `24433351e24b…` |
| H, turn 2 (section 5), roll 2 | identical | `3908c953318e…` |
| H, refrain 1, synth folk (node and Chrome) | identical | `8405f26c4c5c…`, `76f91272f99e…` |
| B, section 1 | identical | `1605ac5b672d…` |
| B, whole song; tempo 70, picking; synth folk | identical: samples, record, every packet member | `288c16ecbdef…`, `27e40e44abd4…`, `b6fb5e07d050…` |
| H, whole song (also recorded in Chrome) | identical | `417585a8574b…` |
| whole song, songwriter (node; Chrome under the Worker: recorded, shared, fetched back) | identical | `779ae148bea7…` |
| H, whole song, roll 2 | 23 of 7.66 M samples differ, by 1 LSB | `95f79249…` vs native |
| H, whole song, tempo 92, roll 1 (Chrome and node) | 1 of 8.47 M samples, 1 LSB | `73df8752…` vs `f040fd7d…` |
| whole song, tempo 92 (Chrome: recorded, shared, read back) | 13 of 8.8 M samples, 1 LSB | `bade764f3743…` vs `a2f6283aa311…` |
| whole song, synth folk (node) | 1 of 7.0 M samples, 1 LSB | `022a0295ad9a…` vs `e5d6eb1ddac8…` |
| H, whole song, tempo 98 (Chrome) | differs | `47770304…` vs `24b99913…` |

Every section tried and most whole songs are native to the last bit, and where the samples are the same, the record
is too (every packet member identical, `program_sha256` the same). The render keys, the records' program,
parameters, marks and requirements.txt match in every case. The FLAC's own bytes may differ by the encoder
(Pyodide's libFLAC 1.4.2, native 1.4.3), not in what they decode to: the id is the samples'.

**Where they part.** Every part alone and dry, browser against native (bench/stems_diff.py, H whole, roll 2): the
bass, accordion, claps and stomps agree to -243 dB or better below their peaks, the voice and the voice before to
-197 and -192 dB, the fiddle only to -116 dB. Pyodide's `sin`, `cos`, `exp`, `tanh`, `log1p` (musl's, and V8's in the
kernels) differ from macOS's in the last bit; everywhere else that stays a -190 dB whisper, but the bowed string's
friction is a feedback loop that grows a last-bit difference in its vibrato (`bowed.tracks`, `np.sin`) into one
about 1/20 of an LSB, enough to tip a sample's rounding now and then in a long song. Synth folk, with no fiddle,
also parts by one sample (its arp or pad, likely). Linux and a Mac very likely part the same way, their libm
differing too.

A recording that differs is still a valid packet (its record's id is its own audio's), plays the same (1 LSB is -96
dBFS, a handful of samples), and continues the lineage the same; but rendering its record again natively gives the
native id, not its own. The cure is deterministic `sin`, `cos`, `exp`… in the kernels and on the few hot numpy paths
(decision 1).

### Time and memory

In Chrome 152 on the M1 Max (shared with other work), the page visible:

- **Getting ready**: 4.8-5.0 s from the cache (Python, numpy, scipy and soundfile, the program, importing every
  instrument); a first visit adds the download (about 20 s at 15 Mbit/s).
- **A section**: 2.0 s for a turn (no voice); H's refrain with the voice and a voice before it, 7.7 s in Pyodide
  under node (Chrome within 20% of node). Native: 1.2 s.
- **A whole song**: 55-62 s for H (the voice, a voice before it, the band), 18 s for B; native 9-10 s for H.
- **The wasm heap**: a section 224-464 MiB; a whole song 1.14 GiB (B) and 2.0-2.3 GiB for H with a voice before it
  (the heap grows during the two voices and never shrinks). Chrome's wasm32 ceiling is 4 GB.
- **A hidden tab is several times slower**: H's refrain took 52-72 s and a whole song 333 s. The worker keeps going,
  and the stall watch allows for it.

### Tests

tests/studio_renderer_browser.test.cjs (node, a stand-in worker: who makes the song, the section worker replaced
after its few, a whole song's worker of its own and terminated, a recording's name and download, failures and
cancelling); tests/test_studio_browser.py (the server mode's bundle served for good, its policies, a bundle from
another program refused, a section and a recording from their specs the studio's own byte for byte);
tests/test_browser_kernels.py.

### Decisions for the artist

1. **Byte identity for fiddle versions.** A recording made in the browser is native to the last bit for every
   section tried and most whole songs, and differs by 1 to 23 samples at 1 LSB for others. Either accept it (the
   packet is valid and self-consistent, the difference inaudible, and Linux and macOS very likely differ the same way
   already), or do the determinism work: deterministic transcendental functions in the engine, starting with the
   bowed string's vibrato, changing fiddle, steel and cello renders once (new goldens if a golden plays them), after
   which the browser, Linux and macOS agree. Recommended: the determinism work, accepting it meanwhile.
2. **Whole songs' memory.** 2.0-2.3 GiB of wasm heap for H with a voice before it; the voices' memory (the learned
   throat run twice) is where to cut.

## A whole song's memory

What a whole song takes to make, natively and in a browser, and how the program estimates it before it starts
(`songbird/public.py`). On studio.itsby.you a whole song estimated past what a browser holds ("In a browser", below)
is warned of and made all the same; the server mode refuses one past its budget.

Measured on the M1 Max with `tools/render_memory.py` (the whole process's resident high-water mark, `MallocLargeCache=0`
as the stand-in for Linux), two threads; tests/test_studio_public.py's `MEASURED` holds these:

| version | length | parts | peak |
|---|---|---|---|
| H's seed (the ballad) | 151 s | bass drone drum fiddle guitar harp lute voice whistle | 1.30 GB (1.13 on one thread) |
| the ballad, 3 verses, every part | 217 s | the same | 1.57 GB |
| the ballad, 4 verses, every part, slowest | 347 s | the same | 2.36 GB |
| chamber | 189 s | cello piano strings voice | 1.30 GB |
| chamber, 2 verses, tempo 60 | 239 s | the same | 1.57 GB |
| chamber, 3 verses, slowest, every part | 342 s | the same | 2.26 GB |
| chamber, 4 verses, slowest, every part | 413 s | the same | 2.53 GB |
| lullaby | 298 s | celesta harp musicbox synthpad voice | 1.69 GB |
| ambient | 214 s | drone strings synthpad vibes voice | 1.56 GB |
| synth folk | 132 s | arp drummachine guitar synthbass synthlead synthpad voice | 1.15 GB |
| lo-fi | 186 s | drummachine epiano synthbass vibes voice | 1.45 GB |
| songwriter | 161 s | bass guitar harmonica voice | 1.10 GB |
| country | 152 s | bass guitar kit piano steel voice | 1.43 GB |
| country, 4 verses, every part, slowest | 347 s | the same | 2.41 GB |
| blues | 165 s | guitar harmonica slide stomps voice | 1.34 GB |
| gospel | 225 s | claps ebass kit organ piano tambourine voice | 1.90 GB |
| gospel, 4 verses, every part, slowest | 507 s | the same | 3.87 GB |
| indie | 128 s | claps ebass electric glock guitar kit organ voice | 1.22 GB |
| indie, 4 verses, every part, slowest | 345 s | the same | 2.48 GB |
| shanty | 151 s | bass claps concertina fiddle stomps voice | 1.13 GB |
| string band | 125 s | banjo bass fiddle guitar mandolin voice | 1.12 GB |
| a cappella, three voices of its own | 225 s | voice, choir1-3 | 1.54 GB |
| a cappella, straight | 159 s | voice, choir1-3 | 1.20 GB |
| a cappella, six lineage voices | 225 s | voice, choir1-6 | 1.53 GB |
| a cappella, 4 verses, every part, six voices, tempo 55 | 450 s | the same | 2.56 GB |
| a cappella, six voices, a refrain and the bridge as rounds (docs/ARRANGE.md, "A round") | 255 s | the same | 1.54 GB |
| the jig | 112 s | concertina drum fiddle guitar voice whistle | 0.99 GB |
| the jig, 4 verses, every part, tempo 130 | 213 s | the same | 1.56 GB |
| house | 163 s | arp chop drummachine piano synthbass synthpad voice | 1.27 GB |
| dub, dissolving into its version | 222 s | ebass electric kit melodica organ voice | 1.91 GB |
| a hymn, three voices of its own | 201 s | pipeorgan, voice, choir1-3 | 1.18 GB |
| a hymn, six voices | 201 s | pipeorgan, voice, choir1-6 | 1.20 GB |
| a hymn, the lead alone with the organ | 201 s | pipeorgan voice | 1.21 GB |
| a hymn, 4 verses, every part, six voices, tempo 63.4, a harmonium | 394 s | harmonium, voice, choir1-6 | 2.46 GB |
| the jazz trio, a waltz with its break | 201 s | bass kit (brushes) piano voice | 1.74 GB |
| the jazz trio, swung | 206 s | the same | 1.78 GB |
| the jazz trio, 4 verses, every part, slowest | 372 s | the same | 2.51 to 3.06 GB (four runs) |
| an old 78, a parlour piano alone (mono) | 243 s | piano voice | 1.14 GB |
| an old 78, 4 verses, every part, a fiddle, tempo 58 | 471 s | fiddle piano voice | 1.95 GB |

The bands with a drum kit are 7.1 to 7.5 MB for every second of song on two threads, beside the ballad's 7.0 and
chamber's 5.8. Most of it is what every render holds (the program, the band's sums and the voice's bus, two parts
being made at once on two threads).

**The estimate** (`songbird/public.py`, `render_mb`): 300 MB, and for every second of the song the rate of its
heaviest part, 5% more; more threads more (12% a thread past two, from H's seed on six). A part's rate is the
lightest band's it plays in (the lullaby's 4.7, the songwriter's 5.0), and a band none of whose parts reaches its
rate that way gives it to its signature part (the kit 7.1, the steel 7.5, the lute 7.0, the cello 5.8...); a part in
no band above, its rate in the ballad's band (`tools/part_memory.py`: H's seed with the whistle's line, or the drum's
strokes, played by it), and a little more; a part never measured, the heaviest rate (7.7). A voice from before adds 1
(a guess); the stems hold every part whole until the zip is packed (0.71 MB a second each). Every measurement above
is at or under its estimate, none by more than 30% (tests/test_studio_public.py).

**The server mode's budget**: `--limit render-mb`, by default the container's memory less 400 MB (`STUDIO_MEMORY`;
else the cgroup's limit; else 2500 MB): 2100 MB in the server plan's container, about 4 minutes of song for the kit's
bands, 4.9 for chamber and 6.1 for the lullaby on two threads. Every style's own default fits. A version someone
brings is opened only if its next version plays no longer than the longest the studio makes in one go with the
lightest band (`Studio.most_minutes`; received.MINUTES' 12 elsewhere).

**In a browser** (renderer.js, one thread, wasm32): H's whole song with a voice before it took 2.0-2.3 GiB of heap in
Chrome, about 1.7 times its estimate here, and Chrome's ceiling is 4 GiB; a whole song estimated past 3800 MB of heap
(`BROWSER_MB`: the ballad at about 4.4 minutes) is warned of on the device. The factor (`BROWSER_FACTOR`) is from H
alone; a measurement of a long ballad and a kit's band in Chrome would tighten it.

## Opening someone's version

A visitor can drop someone's version of the song (a FLAC they were sent) into the studio and continue the lineage
from it. Locally, `songbird studio renders/x.flac` does this from the command line (docs/STUDIO.md). The reading
(songbird/received.py: the threat model, the bounds a record is held to) is the same everywhere. On studio.itsby.you
the file is read in a worker in the visitor's browser and kept there, and a shared link's file is kept by the site
("On the device"; "Hosted on Cloudflare", "Sharing a version"). The store below is the one a studio on a computer
keeps (`songbird studio`, and the server mode).

### What a visitor sees

- **"Open someone's version"**: a panel (in "Other versions") with a file picker, and a drop anywhere on the page.
  Only a `.flac` is taken, up to 64 MB. The page says "reading it…", and then either opens the studio on it or says,
  in a sentence, why it can't.
- The studio then opens on that version as the parent (at `/v/<id>`, or `/#version=<id>` on the device). Everything
  is relative to it (edits, the cards' "kept from the version before", the line of versions in the header, one more
  mark), and Record makes its child: a packet whose record names it as the parent (`parent_id`, `generation` + 1,
  `ancestry`), exactly as `songbird studio parent.flac` records one locally.
- The page shows the link to share and a way back to the song as it began. The link is the only way to it: nothing
  lists versions.
- On a computer's studio, before sending, the page asks whether a file that size would be taken now
  (`POST /api/open/ready`).

### What is kept, and for how long

A studio on a computer never keeps the file. The upload is written to a folder of its own (`studio/incoming/open-…/`),
read, and removed whatever happens (a folder older than an hour, left by a stopped studio, is cleared at start). What
is kept is the version as data, in `studio/versions/<id>/`:

- `record.json`: the record as this program read and cleaned it (only the fields a parent gives its child: id,
  title, generation, parent_id, ancestry, rendered_at, params, lyrics, singer, lineage_singers, performance,
  chosen_by_you, program_sha256, program_version, duration; not the maker's machine's numbers, `voice` and `drift`);
- `genome.json`: the song as that version sang it, after validation;
- `timeline.json`: its six years of timeline for the studio's machine and day, worked out while it was read (a new
  day works it out afresh).

The id is the first 32 hex digits (128 bits) of HMAC-SHA-256(key, "songbird-version" ‖ the cleaned record ‖ the
genome's SHA-256), the key made once and kept beside the versions (`.key`, 0600). Opening the same file twice gives
the same id, and it can't be worked out even for a version anyone could make; only the link says it. The access log
writes `/v/…`, never the id. The store is capped (256 MB and 4,000 versions), and a version is kept 30 days after it
was last opened in the server mode (`--limit versions-mb`, `version-days`) and 90 days locally, the least recently
opened going first past the cap.

### Another program's version

Every rendition names the program that sang it (`program_sha256`), and almost every one in circulation was made by
an earlier program than the one serving the studio. The studio **opens it with its own program, and says so**: "It
was made by another version of the program (971e37bd…); this studio continues it with its own (58b771d1…), so the
new version is sung by this one." That is what the local studio does with a parent, and what `python3 parent.flac
new` does in a newer checkout: a child is always sung by the program that makes it, and carries that program. The
parent's audio is never re-rendered; what matters is that this program can *read* the record. It is refused, with
the reason, when it can't: a field of the wrong type, a value outside what this program accepts, a section the song
doesn't have, a shape this program can't sing. A record without a `program_sha256` isn't a packet a program made, and
is refused too.

The song must be this studio's song: the genome's title (and the record's) must be the title of the song the studio
serves. The genome itself may differ from the checkout's (the song file changes); the child is sung from the
parent's genome, as locally, and packs it.

### Threat model

A packet carries a **program** (`program/`, `__main__.py`). Running it is running a stranger's code. The studio
**never executes, imports, unpacks or writes to disk anything from a received packet's program**, and never lets a
name inside the archive choose a path. It reads exactly two members, `manifest.json` and `genome.json`, as bytes,
into memory, and treats both as untrusted data. On a computer it does all of the reading **in a process of its own**
(`examine_apart`: `python -I`, this program's code from its own folder, no PYTHONPATH, user site or current folder;
a CPU limit of 60 s, an address-space limit of 3 GB where the system has one, its own process group, stopped whole
past 75 s), so whatever a hostile file does to the reader, the studio only hears "refused". On the device it is read
in a worker started for the file and terminated after, which holds nothing; what comes back is held to its shape (a
32-hex id, a record, a song) before it is kept or used.

| Threat | Defence |
|---|---|
| Code execution via the packet's program (`__main__.py`, `program/songbird/*.py`, a `sitecustomize.py`, an `.npz` with pickles) | Never extracted, never on `sys.path`, never imported, never decompressed. Only `manifest.json` and `genome.json` are read. The program's hash is only compared, as text, with this program's. A test puts canaries in all of these (and a `program/songbird/received.py` that would shadow the reader) and checks nothing ran or was written. |
| Code execution via data the program loads | Every field is checked against what this program consumes; no field names a file, a module or a class (the voice's `timbre` is held to name:number pairs and `engine` to learned or formant). JSON is parsed with the standard library, never pickle. |
| Path traversal (`../`, absolute names, backslashes, NUL, `.` parts, duplicate names) | Nothing is ever written under a name from the archive. Such names are refused outright. Our own paths are `versions/<hex id>/…`. |
| Zip bomb, a huge directory, overlapping entries | The end record zipfile will use (the last in the final 64 KB) is parsed first, by hand, and must end the file: at most 512 entries, a directory of at most 1 MB right before it, no ZIP64, one disk. Then zipfile's list is checked again: no encryption, stored or deflate only, no data descriptors, declared sizes within 100 MB in all and 1000:1 each, and the entries' local headers must tile the archive exactly from the end of the audio to the directory, so no entry overlaps another and "the audio" is exactly what a player plays. The two members read are capped (1 MB and 512 KB) and read through a bounded stream, whatever their headers claim. |
| Oversized, slow or endless upload (a computer's studio) | The page asks first. Every guard (address, key, per-minute requests, token, `Content-Length` within 64 MB, the hourly `opens`, one upload per address and four in all) comes before a byte of the body is read. The body is streamed to disk with a deadline of a minute plus a second per 32 KB, on top of the 30 s idle timeout. |
| Not a FLAC, truncated, a FLAC without a packet, a preview (no packet) | It must begin with `fLaC` and carry a packet after the audio; each failure has its sentence. |
| Malformed or hostile audio (libFLAC bugs, a header claiming hours, a FLAC bomb of silent frames) | Decoded in the reader; it must be FLAC, stereo, at the synth's 44.1 kHz, and is hashed a block at a time, stopping past 13 minutes whatever the header says. |
| A forged lineage (a record that isn't its audio's) | As `render --parent` does: the audio's samples must hash to the record's `id`. |
| Hostile JSON (deep nesting, huge arrays or strings, NaN, duplicate keys, huge integers) | Parsed with duplicate keys, NaN and Infinity refused; then walked with caps: depth 16, 100,000 values, strings 4 KB (the song's 64 KB), lists and maps 4,096, integers within ±2^53. Free-form parts (words held, the composition, the words sung, a person's marks) are capped by size too (32 to 64 KB). |
| A record that makes renders endless or enormous, or poisons the child (a tempo of 1, a 500-section form, a singer's release of an hour, NaN as a string) | Numbers must be JSON numbers (never strings the program would coerce), finite, and within: an explicit table for every one of the singer's 40 numbers (for the lead, and for every earlier singer, who sing the choir); the mix's designed ranges; for the band, a knob's bounds widened by their span or eight times the default; tempo within 0.5 to 1.6 times the song's, key within an octave, the form the song's own sections (at most 64). Variants, gestures (rebuilt through `phrasing.reduce`) and the choir's ways of singing are held to their reach. The child inherits only this cleaned record, rebuilt field by field, so a hostile record doesn't travel on to the people who run the child. |
| A song that doesn't end, or chokes the program (a form grammar with nested repeats, a bank asking for a thousand verses) | Its form at most 24 parts with at most two repeats, sections named plainly, at most eight verses, its tempo 50 to 220 and its key within reach; then loaded as the program loads a song, and the version laid out as the studio would sing it: refused past 12 minutes, 50,000 notes, or a note of more than 60 s. |
| A record the program chokes on, or takes ages over | The reader builds the page's view of the version, lays it out, and draws its whole timeline (about 5 s for the song on an M1); any error is a refusal, with the reason, and so is taking longer than 40 s. The timeline is kept with the version, so it is drawn once. |
| Memory growing with every version opened | The studio keeps its latest 16 versions in memory and shares one parsed song among those that sang the same one; `variation.per_genome` keeps the latest 16. |
| Enumerating other people's versions | Keyed 128-bit ids; no listing; an unknown or malformed id answers 404 without saying whether one ever existed; the log never writes an id. |
| Filling the disk | The store is capped by size and count and expires; the upload's folder is removed in a `finally`. A version's recording packs the song from its own render folder, so pruning a version never breaks a render in flight. |
| Cross-site upload | The upload needs the page's token (`X-Studio`), the page's own address (Host and Origin), and in a keyed studio the key, like every other change. |
| Someone's IPv6 addresses dodging the limits | Every limit counts an IPv6 address by its /64. |

What this doesn't defend against:

- a vulnerability in libsndfile or libFLAC that escapes the reader's process (it has the server's privileges) or,
  on the device, takes over the reader's Pyodide (this origin's storage is within reach: "On the device", decision 4);
- in the server mode, a visitor clearing their cookie (the per-visitor `opens` count is only as good as the cookie;
  the per-address count, 40 an hour, is what holds), or someone flooding the store from many addresses to push
  others' links out;
- a record that is valid but unwelcome: the words someone chose, which the page already lets anyone write.

Checking `timbre`'s singer names against the learned model isn't done (unknown names are ignored by the program, and
loading the model to check costs more than it saves).

**Privacy.** What is kept of a version is what its file already carries and what its children carry by design
(docs/HARVEST.md): the lineage's parameters, among them the maker's machine's pseudonym (`params.made.by`, twelve hex
digits), the room its microphone heard (`mix`), the moods and vocabulary its words lean to (`leanings`), and the
singer drawn from it. The record's `voice` and `drift` (the machine's reduced numbers) are not kept. The link shows
no more than the file does, to anyone the link is passed to; the person who brings a file may not be the person who
made it.

### The pieces

- **songbird/received.py**: reading a received packet as data (the archive's directory by hand, the entries'
  tiling, the two members, strict JSON), the song checked, the record cleaned to what a parent gives and held to this
  program's bounds, the audio against the record's id, the version tried as the studio would open it; `examine` does
  it all, `examine_apart` runs it in its own process; `Versions`, the store.
- **songbird/studio.py** ("someone's version"): `Studio.receive(path)` and `Studio.opened(id)` (the studio on that
  parent: a light copy sharing the queue, caches, limits and token, with its own song, record, context and timeline;
  the latest 16 kept). A preview's key names the received parent, so two parents never share a render; a recording
  packs the song the parent sang. The handler: `POST /api/open` (the raw file, every guard first), `POST
  /api/open/ready`, and `GET /v/<id>` (the page).
- **The page names its version** through its token: at `/v/<id>` the token is `<token>.<id>` (`device.<id>` on the
  device), so every request it sends (`X-Studio`) says which version it is about. A token naming a version not kept
  answers 404.
- **songbird/public.py**: the limits (`opens`, `opens-ip`, `upload-mb`, `versions-mb`, `version-days`), addresses
  counted by their network, the log's `/v/…`.
- **songbird/studio/studio.js** ("someone's version"): the panel, the drop and its veil, the header's note with the
  link to share; the page's saved edits are kept per version.

Tests: tests/test_studio_received.py (a real packet read as data; each kind of refusal with its reason; canaries
that never run; a real child of a received version; over HTTP, every guard and the store's keyed ids, expiry and
caps).

### Open decisions for the artist

1. **Other songs.** Only this studio's song is opened, by title; but its tune, words and bank may differ from the
   checkout's (as older versions' do), so the studio will sing what a version brought, within the bounds above. A
   stricter rule would open only songs whose files this program has known (a list of their hashes), which would
   refuse versions made from a checkout's changes.
2. **How long a link lives.** 30 days after it was last opened; a gallery would want "for good", with a way to take
   one down.
3. **Another program's versions** open with this program, saying so. Refusing them would refuse almost every version
   in circulation.
4. **Words.** A shared link can carry words someone wrote; nothing moderates them. A gallery would need that decided
   first.
5. **What a link shows of the maker** (the privacy note above): the same as the file, to whoever has the link.
   Blurring the machine's pseudonym and room for shared links would change what the child inherits.
