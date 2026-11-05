# The studio on the web

How https://studio.itsby.you works (October 2026):

- **It runs in the visitor's browser.** The site is static files on Cloudflare (web/studio-site: a Worker in front
  of Workers Static Assets). The page's questions are answered by the studio's own Python, the same code as
  `songbird studio`, run in the browser by Pyodide, with the program's compiled loops translated to JavaScript and
  WebAssembly. Every song is made there, phones included: no server makes a version. ("On the device", below.)
- **Two things reach the site**: a version someone chooses to share (*Share it* sends the recording's file as it is)
  and a shared link being opened (`/v/<id>`). A shared file is kept for 30 days after it was last shared or opened;
  no address is stored, and nothing lists versions. ("Hosted on Cloudflare", below.)
- **Everything else stays in the browser**: the edits, the versions opened, the ways of singing made. A first visit
  fetches about 14 MiB before the song can be edited and about 28 MiB once something is sung; later visits use the
  browser's cache.
- **Singing** (the Sing view) is measured on the device; the recording is deleted and only numbers are kept
  ([WEB-SINGING.md](WEB-SINGING.md)).
- **The same samples as on a computer**, for every section tried and some whole songs; other whole songs differ in a
  handful of samples by the last bit ("Byte identity", under "Made in the visitor's browser", below).

To build it and try it on this computer, and to deploy it:

    uv run python web/studio-wasm/tools/build_site.py renders/studio-site     # the site (Node once: npm ci in web/studio-wasm)
    uv run python web/studio-wasm/tools/serve_site.py renders/studio-site     # try it: http://127.0.0.1:8820
    cd web/studio-site && npx wrangler deploy                                  # "Deploying it", below

This page began on September 29, 2026 as the design for a studio served from a server. That design was built
(`songbird studio --public`, deploy/studio/) but never deployed; it is now
[history/web-studio-server-plan.md](history/web-studio-server-plan.md). The sections below are dated when they were
written. The code is the final word.

## On the device (2026-09-30)

The studio now runs entirely on the visitor's device. It is served as static files from `studio.itsby.you` by a
Cloudflare Worker (built elsewhere), with no studio server behind it. Every question the page asks (`/api/*`) is
answered in the visitor's browser by the studio's own Python: the same code and the same JSON as `songbird studio`.
Every song is made there too, phones included. The only requests that reach a server are the Worker's
`POST /api/versions` and `GET /api/versions/<id>`: a version someone chose to share. The local studio
(`songbird studio`: native, 127.0.0.1) and `--public` (the server design, [history/web-studio-server-plan.md](history/web-studio-server-plan.md)) are unchanged and
pass their tests; this is a fourth way, the one studio.itsby.you runs.

    uv run python web/studio-wasm/tools/build_site.py OUT [--machine none] [--no-singing]     # the site
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
  `window.fetch`: a request to this site's `/api/…` (but `/api/versions`) is posted to the studio's worker and answered
  with the server's status and JSON, so studio.js, score.js, export.js, learn.js, players.js, perform.js, drafts.js
  and author.js ask exactly as they did. Everything else (the page's files, the bundle, `/api/versions`) goes to the
  network. Chosen over a Service Worker, which could also catch `<audio src>`, downloads and the piano tab, but is
  stopped when idle (losing the Python in it) and complicates a first visit; renders were Blob URLs already, and two
  answers (the MIDI file, the piano score) are turned into what the browser keeps.
- **The studio's worker** is the render worker's own script (studio-worker.mjs) with four more commands (`studio`,
  `request`, `restore`, `read`), running web/studio-wasm/py/studio_device.py: a `DeviceStudio` (a `Studio` with no
  thread, since Pyodide can't start one; no limits; the machine the build names, `none` by default as on a server; no
  checkout beside it) and a `Device`, which routes each request through **the functions the server's Handler now
  calls too**: `studio.asked` for the GET questions and `studio.answer` for the JSON posts, moved out of the Handler
  for this, with the server's statuses for the same refusals. Requests are answered one at a time, the timeline last.
- **Renders** are made by the existing render workers (renderer.js, studio_render.py), always: there is no server to
  fall back to. The render spec is asked of the studio's worker, so nothing is worked out twice.
- **songbird/studio.py**: `answer`, `asked`, `NotFound`, `Studio.start_view`, `Studio.runs_with`, `Jobs._work` and
  `Jobs(thread=False)` (`Studio.threads`) were factored out; the Handler calls them; nothing it answers changed.

**Memory: two kinds of worker, decided by measurement.** The studio's worker holds 130 MiB once ready, and 187 MiB
after every question including the timeline (node, below). A whole song's render worker reaches 1.3 to 2.3 GiB and
never gives it back (wasm memory doesn't shrink). In one worker, the studio would carry a recording's heap for the rest
of the visit, and every edit's question would wait a minute or more behind a recording (Python is one thread). Apart,
the page answers at once while a song is made, and the heap goes when the recording is done. The cost is a second
Pyodide (130 MiB, about 5 s to start from the cache) beside the render: at the peak, while a whole song is made, about
190 MiB + 1.3-2.3 GiB in two wasm memories. Reading a version's file takes a third, short-lived one.

### What moved, and what's kept

| | a server (`--public`) | on the device |
|---|---|---|
| the page's questions | the server | the studio's worker, in this browser |
| sections and recordings | desktop browsers; the server for phones and as the fallback | this browser, always, every browser |
| the render spec | the server | the same, from the studio's worker |
| a recording | the server's store (a day), or a Blob | a Blob: *Download it*, and *Share it* |
| a version someone brings | uploaded, read in a process of its own, kept 30 days | read in a worker of its own in this browser, kept in this browser |
| a shared link `/v/<id>` | the server's keyed id over the version it kept | the Worker's id over the file someone shared: fetched, read here, kept here |
| the timeline | the server, per day | here, when *Time* is first opened; kept per day |
| the MIDI file, the piano score | `/export/…`, `/piano/score/…` | a Blob; the score in localStorage (the latest three), which piano.js reads |
| the stems | a job on the server | not yet: said in a sentence |
| ways of singing made | the server, by fingerprint | this browser (IndexedDB), given back to the studio at start |
| limits, the queue, the visitor cookie | yes | none: nothing shared to protect |

**What's kept, and where** (what the page now says: the footer "Nothing leaves this device unless you share a
version."; Help's where and *What's kept*; the Tools sheet's "Made on this device."):

- In this browser: the edits (localStorage, as ever); the versions opened (IndexedDB `songbird-studio`: the cleaned
  record, the song, the timeline, never the audio); each day's timeline; the ways of singing made; the latest three
  piano scores; the bundle in the HTTP cache (28 MB, once); the bytecode Python compiled, for the next worker's start
  (Cache Storage `songbird-bytecode`, about 17 MB, replaced with each new program: docs/notes/PERFORMANCE.md, "The web
  studio's start, its edits and its voice"). A recording is a Blob in the page's memory until the page
  closes: *Download it* keeps it.
- On the site: only a version the visitor chose to share (*Share it*: the recording's file as it is), and what any site
  sees (which files were fetched, which `/v/<id>` was opened). A file the visitor brings is read and kept on the device,
  never uploaded; its address is `/#version=<id>` (a fragment: even its id never reaches the host).

### The page

- **device.js**: at `/v/<id>` it looks in IndexedDB first, else fetches `/api/versions/<id>` and reads it; at
  `/#version=<id>` it looks only in IndexedDB ("This version was opened from a file, and this browser doesn't keep it
  any more. Open the file again."). Either way the page's token becomes `device.<id>`, so every request names its
  version as the server's token does (`<token>.<id>`). A version that can't be found or read replaces the page with the
  server's notice ("This version isn't here"). A version kept by an earlier program is read again (a shared one) or
  asked for again (a file). If the studio's worker dies (for memory), the next request starts it again.
- **renderer.js**: on the device (the page's `studio-render` meta says `device`) every song is made here: no
  phone/tablet/small-screen/`deviceMemory` check, no server, no "made", "server" or "too long" answers. A failure is
  said as it is, with what may help, never blaming the device first: "couldn't make it: it ran out of memory in this
  browser. A shorter version (fewer verses, a quicker tempo) may fit, or a computer."; "the browser stopped it,
  perhaps for want of memory…"; "it stopped making progress. Try again, or a shorter version, or a computer."; "it
  went wrong in this browser (…). Try again…". A whole song estimated past what a browser holds (`public.BROWSER_MB`,
  as before) is **warned of in its progress and made all the same** ("a long version (6.1 minutes), which may need more
  memory than a browser has"). A whole song is marked in localStorage while it's made, so a page the browser closed
  for memory (iOS does: no error ever arrives) says so when it's opened again. The Tools sheet's "automatically · in
  this browser · on the server" is hidden on the device.
- **studio.js**: the device's words (`applyDevice`, kept apart like the public studio's); *Share it* beside
  *Download it* after a recording (the file posted to `/api/versions`; the link shown with *copy the link*; the
  Worker's `{error}` said as it is); the version bar says "which you opened from a file" (no link: it has none) or
  "which someone shared" (its link); the timeline is asked for only when *Time* is opened; a file opened reloads the
  page on its `#version=`.
- **export.js** saves a Blob under its own name; **learn.js** opens only a `/piano/` address; **piano.js** reads
  `?score=device/<key>.json` from localStorage. Built with `--no-singing`, the singing note says "Singing here isn't
  available yet."

### Singing

Singing is in the site unless it is built with `--no-singing` (then the page says "Singing here isn't available
yet."): the Sing view, the fourth beside Page, Arrange and Mix (2026-10-03). It is the server's singing
(webstudio.singing's `Singing`: the same offer, guide, checks, queue, keep and forget, in the studio's worker), with
the guide's melody, the template singer's analyses and the take's measuring done in workers of the page's own:
docs/WEB-SINGING.md, "The Sing view" and "In the studio's page", has it whole. In short:

- **What is sung is the version on the page**: the studio's worker lays the guide from the page's edits (or the
  released version, webstudio/released.json), at a speed and in a key for a voice. Nothing is made ahead or fetched:
  a singing worker (the full one: the whistle is a kernel) makes a section's melody (about 1 s) and the template
  singer's part (about 6 s) when they're first wanted, kept in IndexedDB (`songbird-singing`), and is let go when
  idle.
- **The take never reaches the studio's worker.** device.js sends it only where the take was sung and its length;
  the studio checks and queues it (`Singing.take(meta, None, seconds=…)`), then hands it out (`Device.handout`: the
  server's measuring request, without audio). The page starts a **measuring worker for that take** (the same
  studio-worker.mjs, `init` with `lean`, then `kit` and `measure`), hands it the guides and templates it needs,
  moves the audio to it, and ends it when it answers, so the measuring's memory (about 390 MB for a section) is
  given back at once. Its answer finishes the job in the studio's worker through the server's own
  `Singing._measure` (`Device.measured`); the page polls `/api/job/<id>` as ever.
- The ways of singing made are kept in IndexedDB and given back at start; *Forget my singing* forgets every one kept,
  and clears what singing made.

### For the host: the build and site.json

The hosting Worker is web/studio-site ("Hosted on Cloudflare", below): Workers Static Assets serve the built site,
and its Worker answers `/api/*` and `/v/*`. `uv run python web/studio-wasm/tools/build_site.py renders/studio-site`
(it runs `npm ci` in web/studio-wasm if needed, as build_render.py does, and refuses stale kernels; about 40 s, most
of it the first answers below, in up to eight processes; `--days 0` skips them), then
wrangler's `[build]` runs `tools/prepare.mjs`, which checks site.json against its own rules and writes `_headers` and
`.assetsignore`. The build writes:

    OUT/index.html, *.js, *.css   the page, from the root: device.js, renderer.js, studio.js, score.js, model.js, …
    OUT/notice.css                the plain pages' look
    OUT/piano/                    index.html (its addresses made /piano/…), piano.js, sound.js, piano.css, identity.css
    OUT/render/bundle.json        {"v", "base": "/render/", "pyodide", "app", "packages", "bytes", "studio_bytes",
                                   "transfer", "program", "pyodide_version", "studio": {"song", "machine", "runs_with",
                                   "singing"?}, "first"?: {"folder", "from", "to"}}  (bytes: what a render worker fetches,
                                   studio_bytes the studio's worker: each counted as it arrives, for its percentage)
    OUT/render/py-<hash>/         Pyodide 314.0.7, numpy, scipy, soundfile (29.9 MiB)
    OUT/render/app-<hash>/        the worker, the kernels (JS and C/wasm), songbird.zip: the program, studio_render.py,
                                  studio_device.py, the lead song, webstudio's singing (5.3 MiB)
                                  and singing's measuring (singing.zip, world/; not with --no-singing). Until
                                  2026-10-03 a singing kit made ahead was served beside (render/kit-<hash>/, 42 MiB);
                                  singing now makes what it needs on the device ("Singing" above)
    OUT/render/first-<hash>/      the page's first answers, <day>.gzip a day (gzip'd JSON, 42-49 KB; 402 days, 17 MiB:
                                  "A quicker start", below)
    OUT/site.json                 for the host (below; .assetsignore keeps it off the site)

About 50 files and 36 MiB, and 402 more (17 MiB) of first answers; a first visit fetches 14 MiB of it before the
page can be edited, and 28.5 MiB once something is sung (the host compresses: no `.gz` siblings). The largest is
scipy's wheel, 13.4 MiB; the build refuses any file over 25 MiB. `--machine fictional:NAME` sings as a made-up
machine instead of `none`. **Every address is from the root** (`/studio.js`, `/render/…`, the workers' URLs, the
piano page's own files): the page is served at `/v/<id>` too, and its policy allows no `<base>`.

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
  hash); the page, its scripts, `bundle.json` and the piano page are `no-cache` (asked again each visit: a 304 when
  unchanged). A new program changes `app-<hash>` (5 MB to fetch); a new Pyodide, `py-<hash>`.
- **The policy**: the Worker's (web/studio-site/src/policy.js), on the page and on the workers' scripts alike:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; media-src 'self'
  blob:; connect-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`. That is
  the studio's own, with `'wasm-unsafe-eval'` for Pyodide (never `'unsafe-eval'`) and `blob:` for the songs made here.
  The page needs nothing more: no inline script or style, no `blob:` worker, no fetch of a `blob:` URL (a recording's
  file is kept as a Blob for *Share it*). build_site.py's `POLICY` is held to policy.js's by a test.
- **Types that matter**: `.wasm` as `application/wasm` (compiled as it streams), `.mjs` as JavaScript.
- **The Worker's own paths, never rewritten to the page**: `/api/versions` and `/api/versions/*`. *Share it* posts
  the recording's bytes with `X-Content-SHA256` (one `crypto.subtle.digest`), so the Worker needn't hash 20 MB; the
  answer is 201 `{"id", "url"}` or 4xx `{"error"}`, said as it is. The page fetches `/api/versions/<id>` as bytes
  (it is an attachment; it never navigates there), reads it only as data, and takes back only an id of 32 hex digits.
- serve_site.py does the same on 127.0.0.1 with a stand-in for the Worker (its headers from site.json, the digest
  checked); `wrangler dev` in web/studio-site (launch.json "studio-site", 127.0.0.1:8813) is the real thing, over
  `renders/studio-site`.

### The review (Fable, 2026-09-30)

A read-only review of the design before most of it was built. Its points, ranked as it ranked them, and what came of
each:

1. **A recording made on the device would name Pyodide's Python and pins** (3.14 and its numpy), which a listener's
   uv would then try to fetch. The build records the release's (`Studio.runs_with`, natively, at build time) in
   bundle.json, and the device's specs carry those (checked: the packet's requirements.txt says python 3.12 and the
   server's pins; tests/test_studio_device.py compares them with a native studio's).
2. **The Worker becomes a same-origin file host.** Its requirements went into site.json (`network`); the hosting
   Worker (web/studio-site) checks what's shared and serves it as an attachment.
3. **A hostile version's file would be read in the studio's own heap**, with no process around it. It is read in a
   worker of its own, started for the file and terminated after (a deadline of 6 minutes, and 3 to get ready), which
   holds nothing; what comes back is held to its shape (a 32-hex id, a record, a song) before it is kept or used.
   Residual: the reader is still this origin's code with this origin's storage within reach, if a libsndfile bug let a
   file take over Pyodide; a sandboxed iframe on another origin would close that (decision 4).
4. **Opening a shared link is heavy on a phone** (fetch 15-20 MB, decode, hash, lay out twice, draw the timeline).
   Kept whole for now, said in words while it happens, and kept in IndexedDB so it happens once (decision 3).
5. **Memory on phones fails loudly**: iOS closes the tab. A whole song is marked while it's made and the page says so
   next time; a long one is warned of first, and made all the same.
6. **The timeline blocks everything.** Asked for only when *Time* is opened, last in the worker's queue, and kept per
   day in IndexedDB.
7. **`/api/job/*` is needed** (singing's takes; the stems): answered by the studio's worker (`asked`), its jobs made
   between requests. The stems are refused in a sentence instead.
8. **Version ids, and the hash-only navigation**: a file's id is a fixed-key HMAC of what was read (the same file,
   the same id, any visit); a shared one keeps the Worker's id; opening a file reloads the page on its `#version=`;
   the path wins over the fragment.
9. Smaller: the "ready to play" marks come from the renderer's own cache (the studio's worker has no audio); the
   recording's Blob is kept for *Share it* (no `connect-src blob:`); the piano score in localStorage, the latest three;
   `/piano/identity.css` is copied; the queue's thread doesn't start in Pyodide; webstudio is in the app zip; *What's
   kept* says the site sees which shared versions are opened. piano.js's innerHTML of score strings is the program's
   own words (unchanged).
10. **A test that the device and the server answer alike**, route by route: tests/test_studio_device.py.

### Measurements

On the M1 Max, **shared with other agents' work throughout** (a load average of 8 to 19: every number here is slower
than an idle machine's; the earlier section's Chrome figures, taken on a quieter machine, stand beside them). The
browser is Chrome 152 in the app's built-in pane, from serve_site.py on 127.0.0.1; the pane was **hidden** for most
runs, which throttles the page's own timers several-fold (the workers less). node is Pyodide under node from the same
built site (web/studio-wasm/node/device_run.mjs): each worker a Pyodide of its own, as in the browser.

| | Chrome (pane hidden, loaded machine) | node (loaded machine) |
|---|---|---|
| **Time to ready**: the page's first question answered | 7.6 and 8.2 s the first visit (35 MB from 127.0.0.1: serve_site.py, then wrangler dev); 6.4 s from the cache | Pyodide and the program 5.2-5.5 s, the studio 0.6 s |
| a question (`/api/song`, `/api/arrangement`, `/api/sound`) | | 0.6-0.7 s the first time, 0.05 s again |
| the timeline (once a day, then kept) | | 6.7 s (5.1 on a quieter run) |
| **a section** (refrain 1, the first one, its worker's start included) | 14.2 s (9.4 s making it) | 5.2 s start + 10.3-12.7 s |
| **a whole song** | 123 s (H at tempo 92), 118 s (songwriter), recorded from the page | 117 s (synth folk), 185 s (songwriter) |
| a version's file read (contest.flac 15.8 MB; a recording 19.0 MB) | about 70 s and 280 s, hidden, at a load of 19 to 23; once kept, a reload opens it from IndexedDB | 5.2 s start + 9.6 s (contest.flac); 12.5 + 28.8 s (the recording, at a load of 23) |
| **wasm heap** | | the studio's worker 130 → 187 MiB; a reader 187 MiB; a section 387 MiB; a whole song 1.30 GiB (synth folk), 1.56 GiB (songwriter); 2.0-2.3 GiB for H with a voice before it (the earlier section's) |

A phone's viewport (the mobile preset: an Android user agent, 375 px) tried: nothing gated, verse 1 made in the
browser (172 s, hidden and loaded), identical to the native render. The phone itself is untried: the numbers to
expect are a few times these, and a whole song's 1.3-2.3 GiB is the risk (decision 2).

**Byte identity** (the program's promise; "Byte identity", under "Made in the visitor's browser", below):

| what | the device | native | |
|---|---|---|---|
| refrain 1 (Chrome, from the page's renderer) | `c2e36da52b55…` | `c2e36da52b55…` | identical |
| verse 1, tempo 92 (Chrome, the mobile preset) | `91ea074162fe…` | `91ea074162fe…` | identical |
| refrain 1, synth folk (node) | `76f91272f99e…` | `76f91272f99e…` | identical |
| whole song, songwriter (node; and Chrome under the Worker: recorded, shared, fetched back) | `779ae148bea7…` | `779ae148bea7…` | **identical** |
| whole song, tempo 92 (Chrome: recorded, shared, read back from the Worker's store) | `bade764f3743…` | `a2f6283aa311…` | 13 of 8.8 M samples by 1 LSB |
| whole song, synth folk (node) | `022a0295ad9a…` | `e5d6eb1ddac8…` | 1 of 7.0 M samples by 1 LSB |

The render keys match in every case, as do the records' program (`3506e022…`), parameters, marks and
requirements.txt; where the samples differ, it is the last-bit drift of Pyodide's libm ("Byte identity", below). New here: synth folk,
with no fiddle, parted by one sample, so the drift isn't the fiddle's alone (its arp or pad, likely); decision 1 of
"Made in the visitor's browser" (deterministic transcendentals) covers it the same way.

### How it was checked

- tests/test_studio_device.py (17): every JSON route answered as a native studio answers it; `/api/start` saying the
  device and what it can't do; the timeline; a job 404; the server's statuses for bad edits, a bad machine, a body too
  large, `/api/listen` and `/api/record`, the stems; a render spec the server's but for the release's Python; a long
  whole song warned of and still specified; the MIDI file and piano score handed over; a real packet read as data (the
  file let go, the same id twice, no `voice` kept), restored, opened at `#version=` and at `/v/<id>` with the Worker's
  id, an unknown id 404, a text file and a climbing id refused; singing's stand-in calling `measure(take, request)`;
  the static page, its policies, its files and the Worker's headers.
- tests/studio_renderer_device.test.cjs (6): a phone makes it, never the server; a server's word in a spec changes
  nothing; a recording keeps its file and is marked while made; memory, a killed worker and an error each said
  plainly; a long one warned of and made; no workers, said.
- The studio's server tests (test_studio, test_studio_public, test_studio_browser, test_studio_received,
  test_web_singing: 92) after the refactor, and every node test (121).
- In Chrome under the hosting Worker itself (`wrangler dev` in web/studio-site over this build, after its
  prepare.mjs accepted site.json and wrote `_headers`; its policy on every file): the page ready on a first visit in
  8.2 s; the songwriter band recorded from *Record* in 118 s, its id the native render's (`779ae148…`); *Share it*
  answered 201 with `X-Content-SHA256` sent; the link `/v/<id>` opened in the page: fetched from the Worker's store,
  read in its own worker, "which someone shared … the same program as this studio", its link. The file fetched back
  from the Worker is the recording, id and all.
- In Chrome, from serve_site.py: the page drawn from the device ("no machine, only time", the footer, Help, Tools,
  no server/browser choice); a section played; the tempo set to 92 and the whole song recorded from *Record*, then
  *Share it* (`201`, the link shown), the shared file's id checked against the native render above; a rendition from
  renders/ (562cea, another program) dropped on the page with a real drop event: read in its worker, the page reloaded
  on `#version=…`, "which you opened from a file", the other program said; renders/review/contest.flac opened as a
  shared link `/v/<id>` (fetched from the stand-in Worker, read, "which someone shared", its link), and reloaded from
  IndexedDB without fetching it again; the MIDI export a Blob named `now-its-by-you.2026-09-30.1efd07.mid`; the stems
  refused in their sentence; the piano page opened on `?score=device/<key>.json` at 92; the mobile preset (above). No
  errors in the console (one connection reset from the stand-in server under load, retried by the browser). In the
  app's pane, a new worker fetched scipy's 13 MB wheel again rather than from the HTTP cache (the Worker sends it
  immutable, with an ETag): worth checking in an ordinary Chrome, where a reader's and a render worker's start would
  then be the 5 s from the cache measured in node.

### Open decisions for the artist

1. **Byte identity of whole songs** stands as before ("Made in the visitor's browser", decision 1), now with one
   synth-folk sample beside the fiddle's: sections and some whole songs are the native render's to the bit; others
   differ by a handful of samples at 1 LSB.
2. **Phones and whole songs.** Nothing is gated. A whole song needs 1.3-2.3 GiB of wasm heap on top of the studio's
   190 MiB; many phones will manage a section and some a whole song. A failure is said, and a crash is said next time.
   Making whole songs lighter is the lever (the voices' memory, first).
3. **A shared link costs its first opener** a 15-20 MB download, a Pyodide to read it and the reading (seconds on a
   laptop, perhaps a minute on a phone). Opening the page as soon as the record is cleaned, and checking the audio
   against it in the background, would halve it.
4. **The reader shares the studio's origin.** A sandboxed iframe on a separate origin would keep even a libsndfile
   exploit away from the visitor's storage (the file is never run as a program in any case). Worth it if the Worker
   ever serves files it didn't check.
5. **The stems** aren't made on the device yet: a whole song and then every part alone, in one worker, is 2× the time
   and more memory than a recording. Said in a sentence; the recording opened locally makes them.
6. **What the site keeps of a shared version, and for how long** (the Worker's: a gallery, deletion, words someone
   wrote) is the hosting side's decision, as it was a server's.
7. **The day** is the visitor's own (their browser's date), where a server used its own; a version made just after
   midnight in Tokyo is that day's.
8. **Safari and Firefox** are untried (the workers' policy is their own script's in Chrome; if a browser applied the
   page's instead, Pyodide couldn't compile, and the page would say "it went wrong in this browser").

### A quicker start (2026-10-03)

The artist: "Does it really need to load 78MB to display the lyrics and become interactive?" It didn't. A first visit
showed "Getting the studio ready (once: 3 of 78 MB)…" and no words until the studio's worker had fetched Python,
numpy, scipy, soundfile and the program (28.5 MiB on the wire; the 78 was bundle.json's unpacked bytes with the
singing kit, which was fetched only to sing, a file at a time, and is now retired). Now the song is on the page at once, and the worker
fetches half as much behind it.

**What a visitor sees.** The song's words, the header ("Your version today, …"), the transport, the choices of words,
the sidebar, the Arrange and Mix views and the Sketch, within a fraction of a second of the page arriving. Python
loads behind them; until it's ready, anything that needs it (an edit, *New performance*, Sung, export, opening a
version) waits, and if someone has just pressed or typed something, the page says "The studio is still getting ready:
one moment."; the change shows when it's ready. With an edit saved in this browser, the header says "Getting the
studio ready (40%)…" until the worker has made the song with that edit (what the page asks of its own accord as it
opens is never toasted). On a version's page, or on a day outside the files, the page waits for the worker as before.

**How.**

- **The first answers, a day at a time.** The page's first questions on the song as it began (its start, the singing
  offer, the song, the arrangement, the sound, each sung section's other words, the other computers, the sketch's
  players, the ways of singing) are answered by the studio's own code (`studio_device.first_answers`) at build time,
  natively, for 402 days (two before the build's date, for a visitor west of it, and 400 from it: `--days`), and
  shipped as `render/first-<hash>/<day>.gzip` (gzip'd JSON, 42-49 KB each, 17 MiB in all; immutable). The view
  differs day by day (the words are handed down, or new, by day), so one file a day. They're compressed here rather
  than by the host because the host can't send a stored `.gz` as gzip without the Worker in front of every file; the
  page unpacks them with the browser's `DecompressionStream` (Chrome 80, Safari 16.4, Firefox 113; without it, the
  page waits for the worker). The build takes about 40 s instead of 5.
- **The page's day is the worker's.** device.js reads this browser's date once, fetches that day's file beside the
  worker's start, and tells the worker the same day (`config.day`: `DeviceStudio(day=…)`), so both answer for one day
  even across midnight.
- **Answered from the file only while it's true.** A question is answered from the file only if it is asked exactly
  as the file has it (method, path and JSON body with its keys sorted: `studio_device.question`, `device.js
  question()`), before the worker is ready, with no version on the page and no way of singing kept in this browser
  (those change the studio's answers). Anything else waits for the worker. Something that changes the studio's
  answers (singing kept or forgotten, a version opened) ends the file's answers, so nothing after it is answered out
  of order. Once the worker is ready it answers everything.
- **The studio's worker doesn't fetch scipy or soundfile.** It imports the whole program but plays nothing, so it
  loads numpy alone; `py/lazy_imports.py` stands in for scipy and soundfile (`from scipy.signal import sosfilt` gives a
  stand-in that becomes the real function once the package is loaded). Measured first, natively and in Pyodide: no
  question the studio answers (the timeline, a render's spec, the MIDI file and the piano score among them) runs
  either. Five tables were computed with scipy as their modules were imported: the frame drum's membrane modes, the
  shaker's skin, the struck bank's and the oscillators' half-band filters are now made on first use
  (`functools.cache`; the gauntlet's 60 stems identical to before, bit for bit); the voice's glide shape is left as it
  is (voice.py's bytes are part of the singing measurement's version, so changing it would make every template
  singing has measured and kept stale), and its stand-in makes it on first use. If a stand-in is ever used for real, it raises
  `lazy_imports.Needed`, and the worker fetches the package and asks the same question again (a version's reader does
  this for soundfile, checked). Render and measuring workers load everything, as before. The control worker also
  fetches the program and its wheel beside Python rather than after it.
- **The words of loading** say a percentage of what that worker fetches ("Getting the studio ready (40%)…", "getting
  the singer ready (40%)"): bundle.json's `studio_bytes` and `bytes`, counted as they arrive. No sizes on the page.

**What it costs.** The first Sung after a visit fetches scipy then (14 MB, in the render worker; it was fetched up
front before), and the site holds 17 MiB more (402 files; 483 in all, under the 20,000), uploaded again whenever the
program changes. The day's file (about 44 KB) is the only thing a visit fetches that it didn't.

**Measured** (Chrome in the app's pane, mostly hidden, from a stand-in host that compresses as Cloudflare does and
holds the whole server to one bandwidth; a new port each time, so nothing was cached. The machine was shared with
other agents' work, loads 4 to 13, so the seconds are slower than an idle machine's and vary run to run; the bytes
don't):

| a first visit | before (68016b8) | now |
|---|---|---|
| fetched before the page can be edited | 28.5 MiB (Python, numpy, scipy, soundfile, the program) | **14.3 MiB** (Python, numpy, the program) |
| the words on the page, 50 Mbit/s, desktop | 11.7 s (another run, at load 10: 48 s) | **0.07-0.08 s** |
| editing ready, 50 Mbit/s, desktop | 10.8 s (at load 10: 42 s) | **4.5 s** (at load 10: 10.9 s) |
| the words on the page, 10 Mbit/s, the phone preset | 61 s (at load 10: 70 s) | **0.20-0.28 s** |
| editing ready, 10 Mbit/s, the phone preset | 56 s (at load 10: 64.5 s) | **13.3-19.3 s** (four runs) |
| the studio's worker: making the studio (node) | 3.25 s | 1.06 s |
| the first Sung section, 50 Mbit/s, at load 10 (scipy fetched by the render worker now) | 72 s | 69 s, the same file (`afc608272142…`) |

The Sketch played before Python was ready (10 Mbit/s, the phone preset: ▶ at 3 s, "Verse 1 · bar 1, the sketch").
*New performance* pressed before it was ready: said, and drawn once it was (draw 2). A version brought as a file
(renders/review/contest.flac) read by a reader that fetched soundfile when it needed it, and opened at
`#version=…` (no first answers there: the worker's, as before). On a phone's 10 Mbit/s the download is most of what's
left: 14.3 MiB is about 12 s.

**How it was checked.** tests/test_studio_quick_start.py: the page's day is the studio's; the first answers are what a
studio started that day answers, question by question, under the key device.js makes; every question the studio's
worker answers is answered the same with scipy and soundfile stood in for, needing neither, and a stand-in used for
real asks for its package and is then the package's own function; **in Pyodide under node with numpy alone, the
build's first answers are the worker's byte for byte** (the first day the build makes, one a third of the way, the
last, singing offered); the window of days. tests/studio_device_start.test.cjs: device.js answers from the day's file
before the worker is ready and never after; the same key however the page orders its JSON; anything else waits and is
said; what changes the studio's answers ends the file's; the worker is told the page's day; a version's page, a day
outside the file's, no file, or no `DecompressionStream`: the worker answers everything. The gauntlet natively, before
and after the instruments' tables moved: all 60 stems identical. The host's prepare.mjs accepted the full build (484
files, `render/first-*` immutable).

**Open decisions for the artist**

1. **How many days ahead.** 400 days of first answers is 17 MiB and 40 s of build, uploaded again with each new
   program. A site not deployed for 13 months falls back to waiting for Python (still working). Fewer days (60: 2.6
   MiB) would do if it's deployed often.
2. **Fetch scipy for the singer ahead of time?** Now the first Sung fetches it (14 MB) when it's asked for; a visitor
   who only reads, edits and plays the Sketch never does. Fetching it once the page is idle would make the first Sung
   a few seconds quicker on a slow connection, at 14 MB for everyone.
3. **Saved edits** (a returning visitor) still wait for Python (from the browser's cache: a few seconds). The first
   answers could cover them only by being worked out in the page, which is what Python is for.
4. **The timeline** (*Time*) still waits for Python and then takes a few seconds; it could be shipped a day at a time
   too (about 13 KB more a day, compressed: 5 MiB for 400 days).
5. **The first question after the worker is ready** pays for importing what it needs (about 1 s in node; more on a
   busy phone); the worker could ask the song once in the background as soon as it's ready.

## Hosted on Cloudflare (2026-09-30)

The studio now runs entirely on the visitor's device, so it needs no server of its own: studio.itsby.you is a
Cloudflare Worker (web/studio-site) serving the built site from Workers Static Assets, plus a small API for sharing
versions. The server, the container and the tunnel of the first plan ([history/web-studio-server-plan.md](history/web-studio-server-plan.md)) aren't needed for it.
It is live; "Deploying it", below, has the commands.

### Architecture

- **The site** is static: `uv run python web/studio-wasm/tools/build_site.py renders/studio-site` writes the
  studio's page at the root, the render bundle under `render/` (`bundle.json`, `py-<hash>/`, `app-<hash>/`) and
  `site.json`.
  Workers Static Assets serves every file straight from Cloudflare's edge, without running the Worker: those
  requests are free and unlimited.
- **The headers** come from `_headers`, which `web/studio-site/tools/prepare.mjs` writes into the built site before
  every deploy and `wrangler dev` (wrangler.toml's `[build]`):
  - every file: the page's Content-Security-Policy, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
    `X-Frame-Options: DENY`, COOP and CORP `same-origin`, HSTS, and a Permissions-Policy (no camera, geolocation,
    payment or USB; the microphone is left to the page);
  - a hashed folder's files (`render/py-…/*`, `render/app-…/*`, any folder named `<word>-<8+ hex>`):
    `public, max-age=31536000, immutable`;
  - `/`, `/index.html` and `/render/bundle.json`: `no-cache`. Any other file gets Workers Static Assets' own
    default, `public, max-age=0, must-revalidate`: kept, and checked by its ETag each time.
  - No rule sets a header another rule sets (`_headers` would join them with a comma). If `site.json` names a cache
    policy the rules would serve differently, prepare.mjs refuses the build; it also refuses a file over 25 MiB
    (the static assets' limit for one file; the largest, `pyodide.asm.wasm`, is 9.2 MiB) and more than 20,000
    files.
- **The policy** is the studio's own, strict as before, with what the browser's renderer needs:
  `default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; media-src
  'self' blob:; connect-src 'self'; worker-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`.
  Pyodide compiles WebAssembly (`'wasm-unsafe-eval'`, never `'unsafe-eval'`); a song made in the browser plays
  from a Blob (`blob:` media). The same policy is on every file, so the render worker (a dedicated worker keeps its
  script's policy) has it too. (src/policy.js holds it, for both the Worker and prepare.mjs.)
- **Compression.** The bundle's `.gz` copies aren't uploaded (`.assetsignore`): Workers Static Assets serves a file
  as it is, and a precompressed copy would need the Worker in front of every file (paid requests) to send it as
  gzip. Cloudflare compresses responses itself, with Brotli or gzip, for the types it compresses (JavaScript, JSON,
  wasm, HTML, CSS among them); `.zip` and `.whl` are compressed already.
- **The Worker** runs first only for `/api/*` and `/v/*` (and for a path with no file, to say 404):
  - `POST /api/versions`: share a version (below). `201 {"id": "<32 hex>", "url": "/v/<id>"}`.
  - `GET /api/versions/<id>`: the file, `audio/flac`, `public, max-age=31536000, immutable`, its id as the ETag,
    whole or a range, `Content-Disposition: attachment` and its own policy, `default-src 'none'; sandbox`.
  - `GET /v/<id>`: the studio's page (index.html, with the page's headers and `no-cache`); the page reads the id
    from its address, fetches the file and opens it on the device. **The page must refer to its own files from the
    root** (`/studio.js`, not `studio.js`), or at `/v/<id>` they'd be looked for under `/v/`.
  - anything else under `/api/`: 404, `{"error": "There's nothing here."}`. Every error is `{"error": "<a
    sentence>"}` with a 4xx status (500 if something broke here).
- **R2** (`songbird-versions`, private, bound as `VERSIONS`): `versions/<id>.flac`; `opened/<id>`, when one was last
  opened; `limits/<hour>/<mark>-<random>` and `limits/<hour>/kept-<random>`, this hour's tries and versions kept;
  `incoming/…`, a file being checked; `keys/address`, the key the address marks are made with. The bucket is never
  public: files are only ever served through `/api/versions/<id>`. The Worker is only at studio.itsby.you
  (`workers_dev = false`: no second address on workers.dev).
- **No robots.txt, no noindex**: the public studio may be found (the artist's choice). The built site has none
  (prepare.mjs warns if it ever does); `/robots.txt` is a 404.

### Sharing a version

`POST /api/versions`, the body a rendition: the FLAC with its packet appended, exactly as a recording is downloaded.
Every guard comes before a byte of the body is read:

1. the page itself: `Sec-Fetch-Site` same-origin and `Origin` this site's, when a browser sends them (a tool sends
   neither, and is held to the same limits);
2. 3 a minute from an address (the rate-limiting binding, counted at each Cloudflare location), an IPv6 address by
   its /64;
3. `Content-Length` said, at least 4 KB and at most **64 MB** (as the studio's own reader, `received.UPLOAD`; a
   rendition is about 15 to 25 MB, its packet about 6);
4. this hour's shares, counted by marks in R2: at most 10 tries from one address (a refused file counts too, so a
   flood of junk is held back), and at most 60 versions kept from everywhere (only kept ones, so junk from many
   addresses can't close sharing for everyone). An address is marked only as 64 bits of an HMAC of the hour and
   the address, under a random key the Worker makes on first use (`keys/address`): without the key, a mark can't be
   worked back to an address (a plain digest of an IPv4 address could be, by trying all four billion). Marks go
   with the hour.

Then the file is stored and checked as data, never run:

- **Its name is its content.** The id is the first 32 hex digits (128 bits) of the file's SHA-256. The page should
  send the whole digest as `X-Content-SHA256` (one `crypto.subtle.digest` of the file it already holds): then R2
  itself checks the bytes against it as they're written, and a body that isn't the file its digest names is
  refused. Without the header the Worker hashes the file on its way to R2 (one pipeline, so R2's pace bounds what
  is held in memory); that works, but hashing 20 MB takes more CPU than the free plan's 10 ms a request, so the
  page should send it.
- **Checked before it has a name.** The file goes to `incoming/` first, is checked there, and only then is copied to
  `versions/<id>.flac` (R2 checking the digest again). Whatever stops the Worker half way (an error, a limit), nothing
  unchecked is ever under a version's name, and `incoming/` is swept within the hour. Sharing a file that is already
  there writes the same bytes again: only its date changes.
- **Checked from a few ranged reads** of what was stored (src/packet.js; about 100 KB read in all, never the whole
  file, so the Worker's memory stays small), to the same rules songbird/received.py holds a file to: it begins with
  `fLaC` and a STREAMINFO at 44.1 kHz, stereo; the archive's end record is the last in its final 64 KB and ends the
  file; one disk, no ZIP64, at most 512 entries and a 1 MB directory right before the end record; every name
  plain (no `..`, absolute paths, backslashes, NUL, empty parts) and listed once; nothing encrypted, stored or
  deflated only, no data descriptors, no entry growing more than 1000 times or past 100 MB, every entry between
  the audio and the directory; `manifest.json` and `genome.json` present. Only **manifest.json** is read: its
  local header must be where the directory says and name it, it's inflated through a stream that stops at 1 MiB
  whatever the header claims, its CRC and size must match, and it must be a record (a 64-hex `id` and
  `program_sha256`, a title, a whole `generation` from 0 to 100,000, a `parent_id` and `ancestry` of ids). A
  manifest whose entry declares more than 1 MiB compressed is refused before it is read (deflate never grows data
  much, so that's padding, which would otherwise be read into memory). The entries' tiling (received.py's
  `_tiled`) isn't checked here: the host reads nothing but the manifest; the device checks it.
  Anything else: `422 {"error": …}` with received.py's sentence ("It isn't a FLAC file…", "Its packet lists the same
  file twice, which no rendition does."), and the file is deleted at once.
- **Nothing in it is ever unpacked or run**: not the program, not `__main__.py`, not genome.json. The bytes are
  kept and served back as they came, as `audio/flac` with `nosniff`, `attachment` and a sandboxing policy, so even
  a file built to look like a page does nothing on this site. Everything else (the song, the record against
  this program's bounds, the samples against the record's id) is the studio's reader's, on the device, when the
  version is opened ("Opening someone's version", "Threat model", below): the host only stores and serves.

### What is kept, and for how long

- **The file itself**, exactly as it was shared, as `versions/<id>.flac`: unlike the server's studio (which kept only the
  record and the song), the device needs the whole file to open it. It carries what any copy of it carries (the
  record, among it the maker's machine's pseudonym, the room and leanings: "Privacy", in "Opening someone's
  version" below), and its program.
- **For 30 days after it was last shared or opened.** Sharing the same file again writes it again; an open (the
  file fetched) is noted in `opened/<id>` at most once a week, so a version is kept at least 30 days after anyone
  last opened it, and at most a week more. The hourly cron deletes the rest (`KEEP_DAYS`, `REFRESH_DAYS` in
  `[vars]`). A browser that has fetched one keeps its copy (immutable) whatever happens here.
- **Nothing about who shared it.** No IP address is stored: only this hour's counting marks, 64 bits of a keyed
  HMAC of the address, deleted when the hour is over. No logs (`observability` off); errors log only their kind.
- **Nothing lists versions.** An id is 128 bits; one not there answers 404, and an address asking after many is held
  to 20 a minute. An id is a plain content address, so anyone who has a file can work out its link, and could check
  whether it has been shared, or keep a share alive by fetching it: that says only that someone shared what they
  already hold. A deterministic render (the seed's child sung with no edits on a given day) can be made by anyone,
  so its link can be found. (The server's studio's keyed ids hid even that: decision 4 below.)

### Deploying it

Once:

1. **Build the site** (Node for Pyodide's package, once: `cd web/studio-wasm && npm ci && cd ../..`). Singing needs
   nothing made ahead (since 2026-10-03):

       uv run python web/studio-wasm/tools/build_site.py renders/studio-site

2. **Install wrangler, sign in, make the bucket**:

       cd web/studio-site
       npm ci
       npx wrangler login                                  # if this computer isn't signed in yet
       npx wrangler r2 bucket create songbird-versions

   Optionally, a backstop if the cron ever stops: `npx wrangler r2 bucket lifecycle add songbird-versions limits
   limits/ --expire-days 1` and the same for `incoming incoming/`. (Not for `versions/`: R2's rules count from the
   upload, and would delete versions people still open.)

3. **Free studio.itsby.you, if something has it**: a DNS record for `studio` (Cloudflare > itsby.you > DNS >
   Records; a tunnel's CNAME, from the server plan: [history/web-studio-server-plan.md](history/web-studio-server-plan.md)), the tunnel's public hostname for it, and an Access
   application in front of it (Zero Trust > Access > Applications) all go; the custom domain makes its own record
   and certificate. The cache rule for `/render/` (the server plan's "Cloudflare: cache the bundle") isn't needed: the static
   assets are served from Cloudflare's edge already, with their own headers.

4. **Deploy** (it runs prepare.mjs first, which refuses a site it can't serve):

       npx wrangler deploy

5. **The old singing site** points to the studio (docs/history/SING-ONLINE.md, "Singing moved to the studio"):

       cd ../sing && npx wrangler deploy

Every later deploy: build the site again, then `npx wrangler deploy` from web/studio-site.

**Check after** (`curl -sI` shows headers):

- `curl -sI https://studio.itsby.you/`: 200, the policy above, `cache-control: no-cache`.
- `curl -sI https://studio.itsby.you/render/bundle.json`: `no-cache`. Then a file of the bundle, compressed:
  `curl -sI -H 'Accept-Encoding: br, gzip' https://studio.itsby.you/render/<py-…>/pyodide.asm.wasm`:
  `content-type: application/wasm`, `immutable`, `content-encoding: br` (or gzip).
- `curl -s https://studio.itsby.you/robots.txt -o /dev/null -w '%{http_code}\n'`: 404.
- Singing: `render/bundle.json`'s `studio.singing` is true; in a browser, the Sing view (4) sets out the Page's
  words and makes a section's guide in a few seconds.
- Share the seed (`f` its FLAC; prints the id and link):

      f=web/sing/public/seed/now-its-by-you.flac
      curl -s -X POST -H "X-Content-SHA256: $(shasum -a 256 $f | cut -c1-64)" --data-binary @$f https://studio.itsby.you/api/versions

  then open `https://studio.itsby.you/v/<id>` in a browser: the studio opens on the seed.
- `https://songbird.quadule.com/i/anything`: "Singing happens in the studio now: studio.itsby.you"; now.itsby.you
  as before.
- After a day, Workers & Pages > songbird-studio > Metrics: no "Exceeded CPU" errors (if there are, the page isn't
  sending `X-Content-SHA256`, or the free plan is too tight: Workers Paid is $5 a month).

### Costs

Cloudflare's prices on 30 September 2026:

| | free | beyond |
|---|---|---|
| Static assets (the whole site) | free and unlimited requests, no storage charge; 20,000 files (100,000 on Workers Paid), 25 MiB a file | free |
| Worker requests (`/api/*`, `/v/*`, 404s) | 100,000 a day, 10 ms CPU each | Workers Paid: $5 a month for 10 million, then $0.30 a million; 30 s CPU allowed |
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

So: 1,000 shares a month keep about 20 GB (10 GB over the free tier: $0.15 a month) and use a few thousand
operations; 10,000 shares a month keep about 200 GB ($2.85 a month), 50,000 class A, well within the free million.
50,000 opened links a day is the free plan's 100,000 requests. **The most it could cost**, with the hourly ceiling
reached every hour for a month by someone uploading 64 MB files that pass the checks: 43,200 files kept 37 days,
about 3.4 TB, about $50 a month (about $16 at a rendition's real size); lowering `ALL_AN_HOUR` lowers it in
proportion. A
Cloudflare billing notification (Manage Account > Billing > Notifications) is worth setting once Workers Paid or R2
has a card on it. R2 needs a payment method on file even within its free tier.

### How it was checked

- **web/studio-site/test** (`npm test`, node, 22 tests): packet.test.mjs (a rendition is a version; the seed itself,
  when built; only the head, the end and manifest.json are read, never the program's entries; each way a file isn't
  a rendition refused with its sentence: not FLAC, 48 kHz, mono, no packet, bytes after it, a misplaced directory,
  ZIP64 or empty, too many entries, `../`, absolute and backslashed names, duplicates, encryption, data descriptors,
  bzip2, a 1000:1 bomb, 101 MB declared, an entry outside the archive, no manifest or song; the manifest too large,
  inflating past its size, a bad CRC, not JSON, not a record, each field wrong, nested 100,000 deep, a local header
  elsewhere), worker.test.mjs (shared with and without the digest, the same id and nothing left incoming; a wrong
  digest refused without touching the version there; refused files not kept, and nothing unchecked ever under a
  version's name, even with R2 failing mid-check; size asked before the body is read;
  another site's page refused; the minute, the hour from one /64 and from everywhere, with only digests kept; ranges,
  HEAD, 304, 405, 404s for every other `/api/` path and the guessing limit; `/v/<id>` with the page's policy and
  nothing else under `/v/`; retention through opens, its weekly note and the cron; a broken bucket a plain 500),
  prepare.test.mjs (hashed folders, `_headers` with no header set twice, site.json in its shapes checked against
  the rules, a 26 MiB file and a missing index.html refused).
- **Under `wrangler dev`** (launch.json `studio-site`, a stand-in site with a hashed bundle, a wasm file and its
  `.gz`): every header as above; the `.gz` copies, site.json and `_headers` not served; no robots.txt; the seed
  shared with and without its digest (the same id, `c1980bc7…`), fetched whole (its SHA-256 the same) and in a
  range; a wrong digest and a junk file refused; the minute's limit; in the built-in browser, `/v/<id>` loaded the
  page, which fetched the 15.8 MB file, and a module worker compiled WebAssembly under the policy; a share from the
  page was 201.
- **The old site**: web/sing's tests, with a new one: every invitation points to the studio, nothing more is sung or
  kept, singers' pages work, and the seed host answers byte for byte as before.

### Decisions for the artist

1. **The page sends `X-Content-SHA256`** (web/studio-wasm/device.js): without it, a share
   costs the Worker the hashing, which may pass the free plan's 10 ms of CPU and fail. Or take Workers Paid.
2. **The limits**: 64 MB a file, 10 an hour from one address, 60 from everywhere, kept 30 days after the last open.
   The ceiling is what bounds the bill (above); raise it if real use reaches it.
3. **The seed page could link to the studio** (now.itsby.you says how to run the song; a line "or open it in the
   studio" with `https://studio.itsby.you/v/<the seed's id>` once the seed is shared there). Not done: the seed page
   stays byte for byte as it is until you say.
4. **Content-addressed ids** are what was asked for, and they let anyone with a file (or who can make it: a
   deterministic render) find whether it was shared. The review's alternative keeps everything else: the id as
   `HMAC(a key of the Worker's, the file's SHA-256)`, cut to 32 hex; R2 still checks the digest, the same file still
   gets the same id, and the page learns its link from the 201 rather than working it out. A small change in
   worker.js if you want it.
5. **The page's own files from the root.** At `/v/<id>` a relative `./worker.mjs` would be looked for under `/v/`
   (web/studio-wasm/index.html uses one today); build_site.py's page must use `/…` paths (`base-uri 'none'` rules
   out a `<base>`).

### The review (Fable, 2026-09-30)

A read-only Fable review of this hosting, the upload API above all. What came of each point:

| | found | now |
|---|---|---|
| 1 | **Unchecked bytes could stay under a version's name**: the file was written to its place before it was checked, and only a refusal deleted it; an error, or the Worker stopped (a manifest entry padded to 60 MB read into a 128 MB isolate), would have left it there, servable | Checked in `incoming/` and only then copied to its place; a manifest declaring more than 1 MiB compressed is refused before it's read (test: R2 failing mid-check leaves nothing under `versions/`; a padded manifest refused) |
| 2 | Refused files counted against everyone's hourly ceiling: a few addresses sending junk closed sharing for all | Tries count per address; only versions kept count against the ceiling (test: six junk shares from six addresses, then two real ones kept) |
| 3 | A plain 64-bit digest of an IPv4 address can be undone by trying them all | An HMAC under a key of the site's own (`keys/address`) |
| 4 | Content-addressed ids can be worked out for deterministic renders | Kept as asked; the keyed alternative is decision 4 |
| 5 | Concurrent shares all pass the hour's count before any is marked | Accepted: the per-minute limit (3) is the brake, and kept versions are marked after they're kept |
| 6 | A tee for the Worker's own hashing could buffer up to the whole file | One pipeline, each chunk hashed before it goes on |
| 7 | The tidy could delete a version shared again between its listing and its deleting; an open racing a delete left a mark for good | Each version is looked at again before it's deleted; marks for versions gone are deleted (test) |
| 8 | `workers_dev` gave the site a second origin; `/v/<id>` didn't revalidate; a failing limiter said nothing | `workers_dev = false`; `If-None-Match` passed on; the limiter's failure logged by kind |

Fine as it was, the review said: nothing uploaded can run or render on the site (`fLaC` first, `audio/flac`, `nosniff`,
attachment, a sandboxing policy); R2's digest check means a stored file always hashes to its name; the same-site
check; ranges and 304s; the retention arithmetic; and the old singing site's change (its seed host byte for byte).

## Made in the visitor's browser (2026-09-30)

The feasibility spike (docs/notes/BROWSER-RENDER.md) showed the program itself running in a browser: Pyodide, the numba
kernels translated to JavaScript and a few to C/wasm, the same samples as native. This puts it behind the studio's
page, so a desktop visitor's own browser makes their previews and their recording, and the server mostly serves
files. The server stays the fallback for everything the browser can't do. (Written for the server design,
[history/web-studio-server-plan.md](history/web-studio-server-plan.md); on studio.itsby.you every song is made this way, with nothing to fall back to: "On the
device", above.) The local studio is unchanged: it renders
natively, and the bundle never goes into the song's packet.

    songbird studio --public --browser-render DIR      DIR: built by web/studio-wasm/tools/build_render.py

### What a visitor sees

- **Nothing new, at first.** On a desktop browser the first ▶ or *Export it* says "getting the singer ready (once:
  12 of 35 MB)" in the player, then what the program is doing ("singing", "playing the fiddle", "mastering"), as
  a server render does. This happens once per visitor: the files are cached for good after that, and later visits
  say only "getting the singer ready" for the 5 or 6 seconds Python takes to start.
- **The Tools sheet** has *Make the song: automatically · in this browser · on the server* under *Export it*, with a
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
docs/notes/BROWSER-RENDER.md names: deterministic `sin`, `cos`, `exp`… in the kernels and on the few hot numpy paths
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
   hearing the whole song (a line in renderer.js's `choose`: `kind === "record"` → server; the server then does the
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

## A whole song's memory (2026-09-30)

What a whole song takes to make, natively and in a browser, and how the program estimates it before it starts
(`songbird/public.py`). It was measured for the server plan's review ("Before launch", in
[history/web-studio-server-plan.md](history/web-studio-server-plan.md)), so the budget below is that server's. On
studio.itsby.you a whole song estimated past what a browser holds ("In a browser", below) is warned of and made all
the same ("On the device", "The page").

Measured on 30 September on the M1 Max, `tools/render_memory.py` (the whole process's resident high-water mark,
`MallocLargeCache=0` as the stand-in for Linux): first as the review found it, then after the heaviest parts were made
lean the same day, byte for byte (docs/notes/PERFORMANCE.md, "The heaviest parts"; every rendition below renders to the id
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
| a cappella revised (evening: hummed, not sung on shape-notes), three voices of its own | 225 s | voice, choir1-3 | 1.54 GB | |
| a cappella revised, six lineage voices | 225 s | voice, choir1-6 | 1.53 GB | |
| a cappella revised, 4 verses, every part, six voices, tempo 55 | 450 s | the same | 2.56 GB | |
| a Celtic session (a jig, a slow air) | 120 s | concertina drone drum fiddle guitar voice whistle | 1.07 GB | |
| a Celtic session, 4 verses, every part, a reel at 91 | 347 s | the same | 2.34 GB | |
| the jig (the session renamed, evening; always six-eight, no reel) | 112 s | concertina drum fiddle guitar voice whistle | 0.99 GB | |
| the jig, 4 verses, every part, tempo 130 | 213 s | the same | 1.56 GB | |
| house (2026-09-30, new) | 118 s | arp drummachine (a 909) piano synthbass synthpad voice | 0.97 GB | |
| dub, with its version after the song (new) | 221 s | ebass electric kit melodica organ voice | 1.89 GB | |
| a hymn (2026-09-30, night: docs/STYLES.md, "A hymn"), three voices of its own | 201 s | pipeorgan, voice, choir1-3 | 1.18 GB | |
| a hymn, six voices | 201 s | pipeorgan, voice, choir1-6 | 1.20 GB | |
| a hymn, the lead alone with the organ | 201 s | pipeorgan voice | 1.21 GB | |
| a hymn with a harmonium | 201 s | harmonium, voice, choir1-3 | 1.12 GB (estimated 1.76: the harmonium's rate is the ballad's) | |
| a hymn, 4 verses, every part, six voices, tempo 63.4 | 394 s | pipeorgan, voice, choir1-6 | 1.77 GB (estimated 2.66) | |
| a hymn, 4 verses, every part, six voices, tempo 63.4, a harmonium | 394 s | harmonium, voice, choir1-6 | 2.46 GB | |
| house again (the evening: its own lengths, the chop; docs/STYLES.md, "House and dub, again") | 163 s | arp chop drummachine piano synthbass synthpad voice | 1.27 GB | |
| dub again (dissolving into its version after the first refrain, the dub-out after) | 222 s | ebass electric kit melodica organ voice | 1.91 GB | |
| a cappella, six voices, a refrain and the bridge as rounds (an arrangement option, not a style: docs/ARRANGE.md, "A round") | 255 s | voice, choir1-6 | 1.54 GB | |
| a cappella, 4 verses, every part, six voices, tempo 55, every refrain, verse and bridge a round | 712 s | the same | 2.86 GB (2.78 without the rounds, 494 s); refused in the studio, as before | |
| the jazz trio (September 30, new: docs/STYLES.md, "A jazz trio"), a waltz with its break | 201 s | bass kit (brushes) piano voice | 1.74 GB | |
| the jazz trio, swung | 206 s | the same | 1.78 GB | |
| the jazz trio, 4 verses, every part, slowest | 372 s | the same | 2.51 to 3.06 GB (four runs) | |
| an old 78 (2026-09-30, night: docs/STYLES.md, "An old 78"), a parlour piano alone, recorded as a 78 (mono) | 243 s (246 with its run-out groove) | piano voice | 1.14 GB | |
| an old 78, 4 verses, every part, a fiddle, tempo 58 | 471 s | fiddle piano voice | 1.95 GB | |

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
`STUDIO_MEMORY` in; else the cgroup's limit; else 2500 MB): **2100 MB** in the server plan's container. What it lets the server make in one
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
| the jig, was a Celtic session (whistle, drum) | 7.4 | 4.1 |
| house (arp; the chop at the voice's rate) | 6.4 | 4.5 (its own lengths make its versions longer: a machine's long shape with a drop, ada's, is 3.8 minutes: it fits) |
| dub (melodica, 2026-09-30) | 7.4 | 3.9 (a dub version of H's own shape is 3.7: it fits; a machine's longer shape, three verses and the bridge twice, is 4.5 to 5 minutes and doesn't) |
| the jazz trio (kit: brushes only, at the kit's rate) | 7.1 | 4.0 (H's own shape with the piano's break is 3.4 minutes: it fits; a machine's longer shape, three verses and the bridge twice, is 4.1 to 4.5 minutes and doesn't; the trio measured 6.0 to 7.4 MB a second over the base, so the estimate is about right) |
| an old 78 (voice, piano or guitar, fiddle: 4.5 each since 2026-09-30, the lightest band measured, 3.3 a second) | 4.5 | 6.3 (every machine's old 78 fits; the longest of four, coral's waltz with three verses and the bridge twice, is 5.5 minutes) |

(An a cappella's peak grew with its voices until the group's bus was summed as its voices came rather than
held until the last, 30 September, to the bit: 1.85 and 2.33 GB before, for three and six voices, 1.51 after.)

Every style's own default now fits (country's 2.5 minutes and gospel's 3.75 were refused before: they would have
killed the studio). `STUDIO_MEMORY=3g`, if the server can spare it, is about a quarter longer each.

**In a browser** (renderer.js, one thread, wasm32): H's whole song with a voice before it took 2.0-2.3 GiB of heap in
Chrome, about 1.7 times its estimate here, and Chrome's ceiling is 4 GiB; a whole song estimated past 3800 MB of heap
(`BROWSER_MB`: the ballad at about 4.4 minutes) isn't given to the browser. The render spec says `server` when the
server can make it instead, or `too_long` with the same sentence ("…too long for this small server or a browser…:
shorten it…") when neither can; the page says it and sends it nowhere. The server, refusing a whole song a browser
could make, says "make it in your browser". Sections are made as ever, in either. (The factor is H's, whose band
changed least; the lean parts are lean in a browser too, one thread and the same code, so the kit's and chamber's
bands should now sit near it as well: worth a measurement in Chrome.)

**A version someone brings**: a public studio opens it only if its next version plays no longer than the longest it
makes in one go with the lightest band (`Studio.most_minutes`: 6.9 minutes in that container with the bundle, received.MINUTES' 12
elsewhere), and says so otherwise: "Open it in the studio on your own computer."

Decisions for the artist: the budget's headroom (400 MB for the pages, a take or two on its way, and the reader of a
version brought, which runs beside a render); the browser's factor (1.7, from one version: measure a long ballad, and
now a kit's band, in Chrome to tighten it). The kit's memory, the open question here before, is fixed: every style
with a kit makes about 4 minutes on the server.

## Opening someone's version (2026-09-29)

The artist wants a visitor to be able to drop someone's version of the song
(a FLAC they were sent) into the studio and continue the lineage from it, and
to share a link that opens that version for others later. Locally,
`songbird studio renders/x.flac` already does this from the command line
(docs/STUDIO.md); this brings it to the page, in public mode and locally.

Written for the server design ([history/web-studio-server-plan.md](history/web-studio-server-plan.md)). The reading
(songbird/received.py: the threat model, the bounds a record is held to) is the same everywhere; on
studio.itsby.you the file is read in a worker in the visitor's browser and kept there, and a shared link's file is
kept by the site ("On the device", "What moved, and what's kept"; "Hosted on Cloudflare", "Sharing a version").
The store below is the one `songbird studio` keeps.

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
