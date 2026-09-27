# Singing online: the karaoke for singers anywhere

Singers who aren't in the room sing the song on a page reached by a link: the karaoke
(tools/karaoke.html) behind an invitation, recording in the guide's audio clock with the same timing
corrections, so a take sung online is measured exactly like one sung here. Each singer gets a page
of their own; their takes stay on the server for them until September 30, and you copy them into
`recordings/` as they come.

**The dates** (the release says them, and `[vars]` in web/sing/wrangler.toml must match):
singing closes **Sunday, September 27, 10 PM Pacific** (`CLOSES_AT`); recordings, files and emails are
deleted **by September 30** (`DELETE_BY` is 8 PM Pacific that day, so the hourly purge is done by 9).

- **The singing page** (web/sing/page, built into web/sing/public by tools/sing_site.py): the release
  (web/sing/consent.md), joining (an email, a name to credit or none), the guides (a set of verses,
  a key and a speed), singing the whole song or one section at a time, words for the song under
  their own release (web/sing/words-release.md).
- **Their own page**, `/y/<singer>` (web/sing/page/yours.*): what they sent, to play or download;
  their version of the song and their vocals once you've made them; "Delete recordings" (the audio,
  until September 30) and "Withdraw" (the audio and the numbers taken from it, until singing closes).
- **The Worker** (web/sing/src/worker.js) on Cloudflare: invitations and singers in KV, takes and
  everything else in a private R2 bucket, an hourly cron for the purge, and your admin API.
- **tools/invite.py**, on your machine: links, sync, mail, purge.

It runs on the free tiers of Workers, KV and R2 at this scale. A take streams straight through the
Worker into R2, which checks it against the checksum the page worked out; the Worker reads a small
copy of song.json (`song/worker.json`) so each request stays within the free plan's 10 ms.

## Invitations

    uv run python tools/invite.py new 3 --note "choir, Tuesday"     # three personal links
    uv run python tools/invite.py new --people 40 --note "instagram" # one group link, for up to 40 people
    uv run python tools/invite.py list                               # each link: open or not, who joined, takes

A **personal link** is for one person, who may join from up to three devices (laptop, then phone);
joins with the same email on one link are the same person, and their takes share a folder. A
**group link** admits `--people` joins, so it can be posted; anyone with it can join until it's full,
closed, or singing closes. `--limit` is takes per singer (default 30), `--days` how long a link stays
open (default 7; singing closing ends them all anyway). Joining is held to 20 an hour from one
address (a choir on one Wi-Fi shares one: raise `JOINS_AN_HOUR` in wrangler.toml and deploy for a
session like that). `revoke <token>` closes a link. Notes are for you; singers never see them.

## Your routine, until September 30

    uv run python tools/invite.py sync --watch 120 --measure --no-versions   # singing day: takes, words, deletions,
                                                      # and each new take measured as it comes
    uv run python tools/invite.py sync                # later (before September 30): the versions too
    uv run python tools/invite.py mail                # who needs an email, ready to paste
    uv run python tools/invite.py mail --open         # ...or open each in Mail (mailto:)
    uv run python tools/invite.py mail --sent         # after sending: mark exactly those as sent
    uv run python tools/invite.py singers             # who joined, their takes, what's been mailed
    uv run python tools/invite.py purge               # after DELETE_BY: the local copies go too

- **--measure** measures each new take as it arrives (tools/measure.py; the aligner runs one take
  at a time, up to a minute each), so when singing closes everyone's phrasing takes minutes to make.
- **sync** copies new takes into `recordings/<singer>/` with their sidecars (the guide and spec, the
  section and its window, the device's delays, the release they agreed to, whether to credit them,
  and their singer id), leaving them on the server; words go to `recordings/words/<singer>.json`.
  It applies what singers did on their pages: a deleted take loses its WAV here too (its sidecar and
  measured numbers stay), a withdrawal removes everything of theirs, phrasing and measured caches
  included. For singers with new takes it makes their version and vocals (tools/versions.py) and
  uploads them to their page (one pair per guide they sang to, on each of their pages). Rendering
  those takes a while: on a busy night run `sync --watch 120 --no-versions`, and a plain `sync` later
  (before September 30) makes them all. Once DELETE_BY has passed it runs purge.
- **mail** lists one message per address: their page's link once they've joined, and "your version
  is ready" once it is. It never sends anything: you paste or open each, send it from
  milo@winningham.net, then run `mail --sent`.
- **purge**, after DELETE_BY, deletes every online singer's WAVs and versions here, keeping sidecars
  and measured numbers, and asks the site to run its own purge now rather than on the hour. It can't know which **training sets** were built from their takes: anything
  in `renders/throat/` made from online singers' recordings must be rebuilt without them or deleted
  by September 30 (purge lists what changed there after the first online take arrived).

A folder is named after the name a singer gave, unless it already holds someone else's takes (then
their id's first characters are added), so two people called Jo never become one phrasing. (`fetch`
is the old way, from before singers had pages: use sync.)

## Put it online (tonight)

Everything below runs in `web/sing`, where `npx wrangler` is the copy `npm install` put there. You're
logged in, the bucket `songbird-takes` exists, and the KV namespace's id is in wrangler.toml.

1. **Build the site**, from the repo: `uv run python tools/sing_site.py` (all 90 guides, about half an
   hour; song.json v2 and the worker's small copy of it, `song/worker.json`; the pages). Build and
   sync on the same machine, so the guide scores takes are measured against are in `recordings/guides/`.
   Building and deploying again while people sing is safe when the words or the voice change but not
   the timing (a word said another way, a verse swapped for one of the same length): each spec lists
   its earlier guides that place a take where the new one does (`was`), and the worker still takes a
   take sung to one of them from a page loaded before the deploy. A change to the timing (the form,
   the turns, a tempo) asks those singers to reload: deploy that when nobody's singing.
2. **Check the dates** in wrangler.toml's `[vars]` against web/sing/consent.md.
3. **The backstop**: have R2 itself delete takes and files after September 30, in case the purge
   ever doesn't run (it acts within a day of the date, so it's a backstop, not the promise):

       npx wrangler r2 bucket lifecycle add songbird-takes expire-takes takes/ --expire-date 2026-10-01
       npx wrangler r2 bucket lifecycle add songbird-takes expire-files files/ --expire-date 2026-10-01

   Never make the bucket public (no r2.dev address, no custom domain on it).
4. **Deploy**: `npx wrangler deploy`. It prints the address,
   `https://songbird-sing.<your-subdomain>.workers.dev`, and sets up the hourly cron (the dashboard
   shows it under the Worker's Settings, Triggers).
5. **The admin secret**, made and kept in your secrets tool, then given to the Worker, never shown:

       python3 -c "import secrets; print(secrets.token_urlsafe(32))" | secrets set songbird-sing-admin
       secrets get songbird-sing-admin | npx wrangler secret put ADMIN_TOKEN

6. **Check it**: `export SONGBIRD_SING_URL=https://songbird-sing.<your-subdomain>.workers.dev`, then
   `uv run python tools/invite.py new`, open the link on your phone, join, sing one section and the
   whole song, open your own page, then `invite.py sync` and find the takes in `recordings/`.

To change a date later (say singing closes later), edit `[vars]` and deploy again; the release must say
the same. `tools/invite.py` talks to https://songbird.quadule.com (its `SITE`) unless `--url` or `SONGBIRD_SING_URL`
says otherwise.

### At songbird.quadule.com

A Worker answers at your own address only if the domain's DNS is on Cloudflare. If it is: uncomment
the `routes` line in wrangler.toml and deploy again (Cloudflare refuses if a DNS record for that name
already exists: delete it first). For that hostname turn off Rocket Loader, Email Obfuscation and
Bot Fight Mode (anything injected breaks the page; a challenge breaks the upload). If the DNS is
elsewhere, send the workers.dev links: they work the same.

## What is kept, where, and for how long

| Where | What | How long |
| --- | --- | --- |
| The singer's browser | their singer id per link, their name and choices, the device's measured delay (localStorage) | until they clear it |
| Cloudflare KV | each invitation (dates, limits, people, your note, open or closed); each singer's record: the link they joined by, the name to credit (if any) and whether to, whether they asked to hear when the song is released, their set, when and to which release they agreed | invitations 90 days after they expire; singers' records until you delete them (a withdrawal leaves only the dates) |
| Cloudflare R2 (private) | takes (WAV) and their sidecars; their version and vocals; words they sent; each email (never in KV, never logged); a digest of each email per link, to tell one person's joins apart; what they deleted or withdrew (ids and times) and emails sent (times); a digest of each joining address | takes, files and joining digests until DELETE_BY; emails until DELETE_BY, or, for those who asked to hear when the song is released, until you delete them; addresses' digests within the hour; words and the deleted/withdrawn events until you delete them |
| Your machine | takes and sidecars in `recordings/<singer>/`, words in `recordings/words/`, versions in `renders/versions/`, phrasings and measured numbers (never in git); in `recordings/`, `.versions.json` (which versions were made and where they went) and `.mail.json` (the emails last listed, by singer id only); in `recordings/guides/`, the guide scores and each release as singers read it | WAVs and versions until purge (by September 30); sidecars and numbers stay (they're what the song keeps), except for anyone who withdrew |

The Worker logs nothing (its logs are off, and it never logs a name, email, token or address). An
address is used only to count requests (about 120 a minute) and joins (20 an hour, as a digest,
forgotten within the hour). Cloudflare itself handles the traffic under its own privacy policy; on
your own domain the zone's analytics keep a sample of requests (paths include links) for a few days.

## Try it here first

    cd web/sing && npm install        # once: wrangler, into web/sing/node_modules
    npm test                          # the worker's and the timing core's unit tests
    cd ../.. && uv run pytest web/sing/test -q   # end to end under wrangler dev

The end-to-end test builds a small site of its own, runs the worker on it three times over the same
throwaway KV and R2 (singing open, singing closed, past DELETE_BY), and plays singers joining,
singing whole and one-section takes, sending words, using their pages, deleting and withdrawing,
with tools/invite.py syncing, mailing and purging into a temporary folder. To click through it:

    python3 -c "import secrets; print('ADMIN_TOKEN=' + secrets.token_urlsafe(32))" > web/sing/.dev.vars
    uv run python tools/sing_site.py && cd web/sing && npx wrangler dev --test-scheduled   # http://localhost:8787
    SONGBIRD_SING_URL=http://localhost:8787 SONGBIRD_SING_ADMIN=$(cut -d= -f2- web/sing/.dev.vars) \
        uv run python tools/invite.py new

Local state lives in `web/sing/.wrangler/state` (git ignores it and `.dev.vars`); visiting
`/__scheduled` runs the hourly cron once.

## How the timing holds up

A take's first sample is the frame the recorder heard when the guide's first sample reached the
singer's ears, less the delays the browser reports and the one the singer measured by tapping; then
the page slides the pitch sung against the song's notes to find any lag left, and the singer can nudge
it by ear (tools/karaoke.js, shared with the karaoke here). A one-section take holds only its window,
and its sidecar says where that starts (`from_s`). The guides travel as MP3s, and song.json carries
each one's opening loudness, so the page can find and skip any silence a decoder puts in front. Each
take's sidecar records all of these numbers, so any of them can be undone later.
