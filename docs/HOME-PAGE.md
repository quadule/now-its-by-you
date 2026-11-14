# The home page: now.itsby.you

*October 7, 2026.* The song's home page plays its current edition, keeps every edition before it on a history
page, and opens the studio. It is served by the Worker in web/sing (the same Worker that served the invitations
to sing in September 2026: [history/SING-ONLINE.md](history/SING-ONLINE.md)), built by `tools/sing_site.py`, and
deployed with `cd web/sing && npx wrangler deploy`.

## The page

`/seed` on every host, and the root of `now.itsby.you` (wrangler.toml's `SEED_HOST`), is a public page for
anyone. Since November 11, 2026 it opens on a hero: the cover large at the left (46% of the page, 280 px before),
the masthead and a short pitch beside it (the title once, in the masthead; the pitch opens "A folk song passed
between people and computers" and ends in its "Read more" to /about; the page is 980 px wide, at which the
cover and the masthead and pitch beside it are of a height), and under both the current edition to play (its words under the player, two lines of one size: the line being sung lit at the
top, the next dimmed under it, sliding up into its place when its turn comes) and download (`public/seed/now-its-by-you.flac`), with which edition it is and a link to its history.
On a phone the order is the masthead, the cover whole, the player, then the pitch, so the cover and the way to play
it share the first screen. Then the studio (pictures of it and a button to studio.itsby.you) and how to run the
file: one short set of steps for Windows (`py`) and one for a Mac or Linux (`python3`), as two tabs that open on
the visitor's own kind of computer (seed.js; without the script, both sets one after the other), each ending in
one command, the file run by itself, alone in its box so that copying it copies nothing else, with a Copy button
beside it. (A file made from
November 2026 on then asks what to do, new or studio: bootstrap.py `choose`; the first version lists its
commands.) While the edition offered was made before October 7, 2026, the Mac's steps say to use the studio on an
Intel Mac (`INTEL_SINCE`). Then the AI
disclosure, and a foot with the ways on.

`/about` (page/about.html) is the page about the song, shortened from the artist's process document for the AI
Song Contest 2026 and not repeating the home page: the artist's opening (authorship and compensation, folk music
and open source), the likeness of the two and what the song takes from both, why it is made in code (a gap left
for the artist's early experiments with Suno), how it was made in five numbered steps (a plan, a fixed core, a
band and a voice in code, eight singers, one loop judged by ear), the voice as a copy of a copy (and Daisy Bell in the bridge), and short credits:
the song and program, the singers as CREDITS.md credits them (`{{CREDITS}}`), and the projects the voice learned
from, linked (SoulX-Singer, Scylla's Band, Chimera). The artist's statement stays in README.md. The home page and
the history link to it. It is served like the history, on every host.

now.itsby.you is a second custom-domain route of the same worker (itsby.you's DNS is on Cloudflare), so it opens on
the seed page; songbird.quadule.com/seed is the same page. Every invited singer's page is unchanged; the bare root
of the singing host still shows its one line.

**The studio's pictures** (web/sing/page/tab-page.webp, tab-arrange.webp, tab-mix.webp, tab-sing.webp, 860 x 484
each) are four close crops, one of each view with something being changed in it and nothing shared between them:
a refrain being edited (Page), a refrain's players set to hard (Arrange), the whistle's fader moved beside the
voice's strip (Mix), the lane while a line is sung (Sing). `tools/site_pictures.mjs` takes them from the web studio
served on this computer with headless Chromium (Playwright) at 2x, in the light colours, and `tools/site_pictures.py`
makes the WebP files; both say how to run them. On a wide screen they are one row of four slanted stripes, each a part of its picture (sing.css chooses which part);
on a phone, a row to swipe, each picture whole. Take them
again when the studio's look changes.

**The source code.** `SOURCE_PUBLIC` in tools/sing_site.py is off. Turned on (once github.com/quadule/songbird
is public, with the tag `first-version` on 10dc1e0 pushed), the home page and /about link the repository in their
foot, and the history each edition's commit and tag.

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
file somewhere that lasts (renders/ is the checkout's, not the repository's), add its entry first in the list
(newest first: tools/released_record.py and the studio's build read the first as the newest), make the studio's
record and guide of it (`tools/released_record.py FILE`, `tools/released_guide.py FILE`), build and deploy; the home page moves to it and the history keeps every one before it. One edition a day at most (its
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

## The performance version (2026-11-12; on the home page since November 14 as "Awards performance draft")

The second edition: performance/'s replay (the contest version in B major, the performance voice, id 67be86f259eb),
packed with the program as it stood that day (0.2.0, record format 2) into
renders/release/now-its-by-you-performance.flac, listed first in editions.json, with webstudio/released-record.json
and released.json made from it. Its entry is provisional until it is released: when the program changes again
before then, render and pack it again with the entry's own command and put the new file's `sha256`, `bytes`,
`program` and `source.commit` (and the day it is released as `date`) in its entry, then the two tools above. Once
it has been served, its bytes never change.

Since November 14, 2026 it is the second edition, "Awards performance draft": the home page offers it, /history
lists both, and the studio opens on it. Its bytes are served, so they never change; a later performance render is
an edition of its own. An edition marked `"held": true` is left off the home page and /history (tools/sing_site.py)
while the studio's build still reads it, for one not ready to be listed.
