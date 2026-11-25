# The home page: now.itsby.you

The song's home page plays its current edition, keeps every edition on a history page, and opens the studio. It is
served by the Worker in web/sing, built by `tools/sing_site.py`, and deployed with `cd web/sing && npx wrangler
deploy`.

## The page

`/seed` on every host, and the root of `now.itsby.you` (wrangler.toml's `SEED_HOST`), is a public page for anyone.
It opens on a hero: the cover large at the left (46% of the page), and beside it the masthead and a short pitch (the
title once, in the masthead; the pitch opens "A folk song passed between people and computers" and ends in its "Read
more" to /about). The page is 980 px wide, at which the cover and the masthead and pitch beside it are of a height.
Under both is the current edition to play and download (`public/seed/now-its-by-you.flac`), with which edition it is
and a link to its history. Its words are under the player in two lines of one size: the line being sung lit at the
top, the next dimmed under it, sliding up into its place when its turn comes. On a phone the order is the masthead,
the cover whole, the player, then the pitch, so the cover and the way to play it share the first screen.

Then the studio (pictures of it and a button to studio.itsby.you) and how to run the file: one short set of steps for
Windows (`py`) and one for a Mac or Linux (`python3`), as two tabs that open on the visitor's kind of computer
(seed.js; without the script, both sets one after the other), each ending in one command, the file run by itself,
alone in its box so that copying it copies nothing else, with a Copy button beside it. (A file made from November 2026
on then asks what to do, new or studio: bootstrap.py `choose`; the first version lists its commands.) While the
edition offered was made before October 7, 2026, the Mac's steps say to use the studio on an Intel Mac
(`INTEL_SINCE`). Then the AI disclosure, and a foot with the ways on.

`/about` (page/about.html) is the page about the song, shortened from the artist's process document for the AI Song
Contest 2026 and not repeating the home page, in the artist's words: an opening (authorship and compensation, folk
music and open source), what the song takes from both and why it is in the public domain, how it was made (the idea,
the program, the voice), and short credits: the song and program, the singers as CREDITS.md credits them
(`{{CREDITS}}`), and the models whose outputs the voice was trained with, linked (SoulX-Singer, Scylla's Band).
README.md opens with the home page's words. The home page and the history link to /about. It is served like the
history, on every host.

The same Worker answers at itsby.you and www.itsby.you (they redirect to now.itsby.you; itsby.you's DNS is on
Cloudflare) and at songbird.quadule.com, where `/seed` is the same page. songbird.quadule.com was the September 2026
site that invited volunteers to sing into the first version; that is finished and its recordings deleted
([history/SING-ONLINE.md](history/SING-ONLINE.md)). An invitation link answers with a notice that singing
happens in the studio, linked to studio.itsby.you.

**The studio's pictures** (web/sing/page/tab-page.webp, tab-arrange.webp, tab-mix.webp, tab-sing.webp, 860 x 484
each) are four close crops, one of each view with something being changed in it: a refrain being edited (Page), a
refrain's players set to hard (Arrange), the whistle's fader moved beside the voice's strip (Mix), the lane while a
line is sung (Sing). `tools/site_pictures.mjs` takes them from the web studio served on this computer with headless
Chromium (Playwright) at 2x, in the light colours, and `tools/site_pictures.py` makes the WebP files; both say how to
run them. On a wide screen they are one row of four slanted stripes, each a part of its picture (sing.css chooses
which part); on a phone, a row to swipe, each picture whole. Take them again when the studio's look changes.

**The source code.** `SOURCE` in tools/sing_site.py is https://github.com/quadule/now-its-by-you, and
`SOURCE_PUBLIC` is on: the home page and /about link the repository in their foot, and the history each edition's
commit and tag (`first-version` on 10dc1e0, `awards-draft` on ffe661b, pushed with the repository).

**Cloudflare Web Analytics.** The zone injects Cloudflare's Web Analytics beacon into each page a browser asks for (a
`<script type="module">` from `static.cloudflareinsights.com`, with its integrity hash). The Worker's page policy
(web/sing/src/worker.js, `PAGE_CSP`) lets in that script and its report of a page view to `cloudflareinsights.com`
(no cookies), those two hosts and nothing else; web/sing/test/worker.test.mjs holds it to exactly those two. The
studio's pages do the same (docs/WEB-STUDIO.md).

**The contest.** A thin dark bar across the top of the page, above the title, in spaced capitals: "An AI Song
Contest 2026 finalist", linked to https://www.aisongcontest.com/the-2026-finalists (page/seed.html, `.contest` in
sing.css). The awards are in Bangkok on November 29, 2026; say how it ended, or take the bar down, after that.

## Editions

web/sing/editions.json lists the song's editions; the home page plays and offers the newest, and `/history` every
one, newest first, numbered from the oldest, with what identifies each behind *Details*. An edition is named by its
audio id (the SHA-256 of its samples, in its record), and **its bytes never change once released**: a file's SHA-256
is its studio link (`/v/<sha256[:32]>`) and what an archive holds, and the same audio can be packed into different
bytes (adding the cover made the first version's file c1980bc7... from 1ddc820a... as rendered). So each edition
lists:

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
| `held` | optional: `true` leaves it off the home page and /history while the studio's build still reads it |

The build copies the kept file, or makes it from the render with the cover (`pack.with_cover`, which makes
c1980bc7... exactly), and stops unless it is exactly `file.sha256` and `file.bytes`. Each is served as
`/seed/now-its-by-you-<date>.flac` (the worker serves any such name the site has, in ranges, cached a day), and the
newest whose bytes this checkout has as `/seed/now-its-by-you.flac` too, with its words timed (`/seed/words.json`);
an edition whose bytes aren't here is left out, said. One edition a day at most (its file is named by its date).

**To add one:** keep its released file somewhere that lasts (renders/ is the checkout's, not the repository's), add
its entry first in the list (newest first: tools/released_record.py and the studio's build read the first as the
newest), make the studio's record and guide of it (`tools/released_record.py FILE`, `tools/released_guide.py FILE`),
build and deploy. The home page moves to it and the history keeps every one before it.

The site offers three editions. The newest, "Awards performance" (November 25, 2026), is the stage version in A
major: performance/record-final-A.json rendered with `--pack` at the `awards` tag, kept as
renders/release/now-its-by-you-awards.flac. The "Awards performance draft" (November 14, 2026,
renders/release/now-its-by-you-awards-draft.flac) and the first version are in the history.
