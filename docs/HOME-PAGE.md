# The home page: now.itsby.you

*October 7, 2026.* The song's home page plays its current edition, keeps every edition before it on a history
page, and opens the studio. It is served by the Worker in web/sing (the same Worker that served the invitations
to sing in September 2026: [history/SING-ONLINE.md](history/SING-ONLINE.md)), built by `tools/sing_site.py`, and
deployed with `cd web/sing && npx wrangler deploy`.

## The page

`/seed` on every host, and the root of `now.itsby.you` (wrangler.toml's `SEED_HOST`), is a public page for
anyone: the current edition to play (its words lit under the player as it sings them) and download
(`public/seed/now-its-by-you.flac`), which edition it is with a link to its history, the studio (a picture of it
and a button to studio.itsby.you), the three commands that run the file, About (the artist's statement word for word, as README.md quotes it, and the singers as CREDITS.md credits
them), and the AI disclosure. now.itsby.you is a second custom-domain route of the same worker (itsby.you's DNS is on Cloudflare), so it
opens on the seed page; songbird.quadule.com/seed is the same page. Every invited singer's page is unchanged; the bare root of the singing host still shows
its one line.

The pages alone build in seconds: `uv run python tools/sing_site.py --pages`, then `cd web/sing && npx wrangler
deploy`. Over a site built here before, its guides (song/) are kept; with none, the pages are built without them
(since 2026-11-11). The guides are the singing page's, served only to an open invitation, and none has been open
since singing moved to the studio on September 30 (`STUDIO_URL`: every invitation and the singing API say so), so
nothing on the site reads them now; the home page doesn't wait on them. A whole build (without `--pages`) renders
the 90 guides too (6 sets x 5 keys x 3 speeds, about half an hour), only needed to open singing here again.

**The studio's pictures** (web/sing/page/tab-page.webp, tab-arrange.webp, tab-mix.webp, tab-sing.webp, 860 x 484
each) are four close crops, one of each view with something being changed in it and nothing shared between them:
a refrain being edited (Page), a refrain's players set to hard (Arrange), the whistle's fader moved beside the
voice's strip (Mix), the lane while a line is sung (Sing). `tools/site_pictures.mjs` takes them from the web studio
served on this computer with headless Chromium (Playwright) at 2x, in the light colours, and `tools/site_pictures.py`
makes the WebP files; both say how to run them. On a wide screen they are one row of four slanted stripes, each a part of its picture (sing.css chooses which part);
on a phone, a row to swipe, each picture whole. Take them
again when the studio's look changes.

**The source code.** `SOURCE_PUBLIC` in tools/sing_site.py is off. Turned on (once github.com/quadule/songbird
is public, with the tag `first-version` on 10dc1e0 pushed), the home page links the repository and the history
each edition's commit and tag.

## Editions (2026-10-07)

web/sing/editions.json lists the song's editions; the home page plays and offers the newest, and `/history`
every one, newest first, numbered from the oldest, with what identifies each behind *Details*. An edition is
named by its audio id (the SHA-256 of its samples, in its record) and **its bytes never change once released**:
a file's SHA-256 is its studio link (`/v/<sha256[:32]>`) and what an archive holds, and adding the cover changed
the first version's (1ddc820a... as rendered, c1980bc7... as served since September 30) without changing its
audio. So each edition lists:

| field | what |
|---|---|
| `title`, `date`, `note` | as the pages show them (the date ISO here, September 28, 2026 on the page); the note, a sentence on what changed |
| `audio` | the full audio id |
| `file` | the released file's `sha256` and `bytes`, and its `path` if a copy is kept (the bytes themselves) |
| `render` | the render it was made from: `path`, `sha256`, `bytes` |
| `program`, `python` | the record's program hash and Python |
| `source` | `commit`, and `tag` |
| `command` | what made it, every option spelled out |
| `credit` | the record's credit line |
| `archives` | `[{name, url}]`: a DOI, an Internet Archive item, a SWHID, once there are any |

The build copies the kept file, or makes it from the render with the cover (`pack.with_cover`, which today makes
c1980bc7... exactly), and stops unless it is exactly `file.sha256` and `file.bytes`. Each is served as
`/seed/now-its-by-you-<date>.flac` (the worker serves any such name the site has, in ranges, cached a day), and the
newest whose bytes this checkout has as `/seed/now-its-by-you.flac` too, with its words timed
(`/seed/words.json`); an edition whose bytes aren't here is left out, said. **To add one:** keep its released
file somewhere that lasts (renders/ is the checkout's, not the repository's), add its entry at the end, build and
deploy; the home page moves to it and the history keeps every one before it. One edition a day at most (its
file is named by its date).

## Cloudflare Web Analytics (2026-11-09)

The zone injects Cloudflare's Web Analytics beacon into each page a browser asks for (a `<script type="module">`
from `static.cloudflareinsights.com`, with its integrity hash), and the Worker's page policy had blocked it ("violates
… script-src 'self'"), so no visit was counted. The policy (web/sing/src/worker.js, `PAGE_CSP`) now lets in that
script and its report of a page view to `cloudflareinsights.com` (no cookies), those two hosts and nothing else;
web/sing/test/worker.test.mjs holds it to exactly those two. The studio's pages do the same (docs/WEB-STUDIO.md).
Takes effect when the Worker is deployed.

## The contest (2026-11-09)

A thin dark bar across the top of the page, above the title, in spaced capitals: "Now an AI Song Contest 2026
finalist — Vote by November 21", the contest's name linked to https://www.aisongcontest.com/ and the vote to
https://www.aisongcontest.com/the-2026-finalists (page/seed.html, `.contest` in sing.css; on a phone the two halves
stack). Public voting closes November 21. The winner is half the jury's and half the public's; the awards are in Bangkok on November 29, 2026. Take
it down, or say how it ended, after that.
