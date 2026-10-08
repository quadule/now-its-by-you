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

The pages alone build in seconds over the site as it was last built, its guides kept:
`uv run python tools/sing_site.py --pages`, then `cd web/sing && npx wrangler deploy`. A whole build (without
`--pages`) also renders every guide that isn't current; on October 7, 2026 none was (the code had changed since
September 28), so it would take about 26 minutes, for guides only singers' own pages still use.

**The studio's pictures** (web/sing/page/studio.webp, 1600 x 1063, and studio-phone.webp, 780 x 880, for a
screen 640 px wide or less) are the live studio's Page view, light, taken with headless Chromium (Playwright) on
October 7, 2026: a 1024 x 680 window at 1.5625x, and a 390 px phone's first screen at 3x, cropped and halved.
Take them again when the studio's look changes.

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
