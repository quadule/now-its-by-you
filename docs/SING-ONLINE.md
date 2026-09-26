# Singing online: the karaoke for singers anywhere

Singers who aren't in the room sing the song on a page of their own, reached by a one-time link.
It is the karaoke (tools/karaoke.html) behind an invitation: the same recording, in the guide's
audio clock, with the same timing corrections, so a take sung online is measured exactly like one
sung here. Their takes wait, privately, until you fetch them into `recordings/`; fetching deletes
them from the server.

- **The page** (web/sing/page, built into web/sing/public by tools/sing_site.py): what this is, the
  release (web/sing/consent.md, which you edit), a name to credit or none, a microphone check and a
  tapped measurement of the device's delay, the guide (the tune alone by default, or the whole
  song), singing with the words as they come, listening back, keeping or redoing, and "I'm done".
- **The Worker** (web/sing/src/worker.js) on Cloudflare: serves the page to open invitations only,
  keeps invitations in KV and takes in a private R2 bucket, and answers your admin commands.
- **tools/invite.py**, on your machine: makes links, lists them, fetches takes, revokes.

It runs on the free tiers of Workers, KV and R2 at this scale (a few singers, a few hundred MB).

## The guides

`tools/guides.py` renders three mixes from one score, the full guide's
(`renders/guide/<song>.guide.score.json`), so a take measures the same whichever was heard, and every
take's sidecar says which:

- **melody**, the default for singers: every sung note on the band's whistle, played plainly and
  doubled softly an octave up so it carries over the singer's own voice; where no one sings (the
  intro, the turns) the tune as the band plays it there, at the band's own octave and softer, so
  the singer hears their entry drop into their register. Under it a small woodblock keeps the beat:
  higher on the downbeat, louder on the four beats that count in each line after a rest, and 6 dB
  quieter under the singing, so it keeps time without pressing the singer onto the grid. Singers
  hear the tune without copying the machine's phrasing, which is what their takes are for.
- **full**: the song as the machine sings it, band and all.
- **voice**: the machine's singer alone (the karaoke here only).

The karaoke here has the same choice (`uv run python tools/karaoke.py songs/h-now-its-by-you.json`).

## Build the site

    uv run python tools/sing_site.py                 # H into web/sing/public: the page, song.json, two MP3 guides
    uv run python tools/sing_site.py --rebuild       # render the full guide from the current code first

The guides come from the guide on disk in `renders/guide/` (rendered again if the genome changed);
`--rebuild` renders it from the code as it is now. Each build keeps the guide's score in
`recordings/guides/`, so fetched takes can always be measured against what their singers heard:
**build and fetch on the same machine** (or copy that score file across). Rebuild and deploy
whenever you change the release or want a new guide; a take records the digest of the release text
its singer agreed to and of the guide score it was sung to, and a take sung to a page that has since
been replaced is refused with "reload it".

## Try it here first

    cd web/sing && npm install                              # once: wrangler, into web/sing/node_modules
    npm test                                                # the worker's and the timing core's unit tests
    cd ../.. && uv run pytest web/sing/test -q              # end to end under wrangler dev (about 20 s)

The end-to-end test builds H's site in a temporary folder, runs the worker on it with throwaway local
KV and R2 and a random admin token, makes an invitation, sends a take (the melody guide itself),
fetches it into a test singer's folder in `recordings/`, checks it, closes the invitation, and deletes
the test take. To click through the page yourself:

    python3 -c "import secrets; print('ADMIN_TOKEN=' + secrets.token_urlsafe(32))" > web/sing/.dev.vars
    uv run python tools/sing_site.py && cd web/sing && npx wrangler dev          # http://localhost:8787
    SONGBIRD_SING_URL=http://localhost:8787 SONGBIRD_SING_ADMIN=$(cut -d= -f2- web/sing/.dev.vars) \
        uv run python tools/invite.py new                                        # open the link it prints

Local takes live in `web/sing/.wrangler/state` (git ignores it and `.dev.vars`).

## Put it online

Everything below runs in `web/sing`. `npx wrangler` is the copy `npm install` put there.

1. **Log in**: `npx wrangler login` opens a browser to your Cloudflare account (free is fine).
2. **The bucket for takes**: `npx wrangler r2 bucket create songbird-takes`. It is private: don't
   turn on its public r2.dev address or give it a custom domain. As a backstop, have R2 delete
   anything left unfetched after 30 days:
   `npx wrangler r2 bucket lifecycle add songbird-takes expire-unfetched --expire-days 30`.
3. **The invitations**: `npx wrangler kv namespace create INVITES`, then paste the `id` it prints
   into `wrangler.toml` in place of `PASTE-THE-KV-NAMESPACE-ID-HERE` (the id isn't a secret).
4. **Build and deploy**: `uv run python tools/sing_site.py` (from the repo), then
   `npx wrangler deploy`. It prints the address: `https://songbird-sing.<your-subdomain>.workers.dev`
   (Cloudflare asks you to choose the subdomain the first time).
5. **The admin secret**, made and kept in your secrets tool, then given to the Worker, never shown:

       python3 -c "import secrets; print(secrets.token_urlsafe(32))" | secrets set songbird-sing-admin
       secrets get songbird-sing-admin | npx wrangler secret put ADMIN_TOKEN

   Until it's set the admin API answers 503. To change it later, run both lines again.
6. **Check it**: `SONGBIRD_SING_URL=https://songbird-sing.<your-subdomain>.workers.dev uv run python tools/invite.py new`,
   open the link on your phone, sing a take, then `... tools/invite.py fetch` and find it in `recordings/`.

### At songbird.quadule.com

A Worker can answer at your own address only if the domain's DNS is on Cloudflare.

- **quadule.com is already a Cloudflare zone**: uncomment the `routes` line in `wrangler.toml` and
  `npx wrangler deploy` again. Cloudflare makes the DNS record and the certificate for
  songbird.quadule.com itself. (Or in the dashboard: Workers & Pages, songbird-sing, Settings,
  Domains & Routes, Add, Custom domain.) If you like, set `workers_dev = false` then, so only the
  custom address answers.
- **quadule.com's DNS is elsewhere** (at the registrar or another host): a CNAME from
  songbird.quadule.com to the workers.dev address won't work, because workers.dev answers only its
  own names. Either move quadule.com's DNS to Cloudflare (free: add the domain in the dashboard, check
  that every existing record was copied, especially mail (MX, SPF, DKIM), then change the nameservers
  at your registrar; it takes effect within a day), or keep the DNS where it is and send the
  workers.dev links, which work the same. Cloudflare's partial (CNAME) setup, which leaves DNS
  elsewhere, needs a paid Business plan.

`tools/invite.py` talks to https://songbird.quadule.com unless `--url` or `SONGBIRD_SING_URL` says
otherwise, so while you're on the workers.dev address, export `SONGBIRD_SING_URL` with it.

## Inviting singers and collecting their takes

From the repo, on the machine that built the site:

    uv run python tools/invite.py new 3 --note "choir, Tuesday"      # three links, open 7 days, 30 takes each
    uv run python tools/invite.py new --days 14 --limit 10 --note "Ana"
    uv run python tools/invite.py list                               # state, takes sent and waiting, expiry
    uv run python tools/invite.py fetch                              # every waiting take into recordings/
    uv run python tools/invite.py fetch --invite <token> --singer "Ana" --keep
    uv run python tools/invite.py revoke <token>

Send each person their own link: a link is the key, and anyone who has it can sing on it until it
closes (when they press "I'm done", when it expires, when it has its takes, or when you revoke it).
If a link goes astray, revoke it and send a new one. The note is only for you; singers never see it.

`fetch` puts each take in `recordings/<singer>/` beside a sidecar, as the karaoke does: the name they
gave (or the invitation's note, or `singer-<token>`) names the folder, and the sidecar keeps the
guide score's digest, the mix they heard, the device's delays and sample rate, when they agreed to
the release and to which text, and whether they want to be credited. From there it's the same as a
karaoke take: the karaoke's Singers panel lists it, and "Make X's phrasing" measures it. A take that
arrives damaged (its size or hash doesn't match) is left on the server and reported.

## What is kept, where, and for how long

| Where | What | How long |
| --- | --- | --- |
| The singer's browser | the name they typed, their credit choice, the guide they chose, their device's measured delay (localStorage, on their device only) | until they clear it |
| Cloudflare KV | each invitation: when it was made and expires, its take limit, your note, whether it's open, done or revoked; and how many takes it sent | 90 days after it expires, then deleted by KV |
| Cloudflare R2 (private) | each take (16-bit mono WAV) and its sidecar: the name given, the credit choice, when the release was agreed and a digest of its text, the guide's digest and mix, the sample rate and delays, when it arrived, its size and hash; and for each closed invitation an empty marker saying when and how it closed (KV takes up to a minute to tell every location; R2 tells them at once) | until you fetch it (fetch deletes it), delete it, or the 30-day rule in step 2 does |
| Your machine | the takes and sidecars in `recordings/` (never in git), the guide scores in `recordings/guides/` | yours to keep; delete a singer's folder if they withdraw |

Nothing else is stored: no addresses, no browser or device details, no logs (the Worker's logs are
off, and it never logs a name, a token or an address). A singer's address is used only as the key
for a rate limit (240 requests a minute), counted briefly at the edge and never written down;
invitations take at most 6 takes a minute. Cloudflare itself handles the traffic under its own
privacy policy, as any host would.

If a singer withdraws before the version their takes were used in is released: delete their folder in
`recordings/` and any phrasing made from it (`renders/phrasing/<song>.<singer>.json`), and, if they
were still on the server, `tools/invite.py fetch --invite <token>` first (or delete them with the
admin API).

## Before you send the first link

- **The release** in `web/sing/consent.md` is adapted from the draft in docs/SINGERS.md. It isn't
  legal advice: have it read by someone who knows. It says nothing about payment; if you pay singers,
  add the terms there. It tells singers to withdraw by telling the person who sent the link, so that
  should be someone they can reach.
- **How long takes may wait** on the server before you fetch them (the lifecycle rule in step 2 says
  30 days).
- **Headphones**: the page asks for them, but can't tell. A take with the guide bleeding into it
  still measures, but less well; listen to a singer's first take when it comes in.

## How the timing holds up

A take's first sample is the frame the recorder heard when the guide's first sample reached the
singer's ears, less the delays the browser reports for playback and the microphone and the one the
singer measured by tapping; then the page slides the pitch sung against the song's notes to find any
lag left, and the singer can nudge it by ear (tools/karaoke.js, shared with the karaoke here). The
guide travels as an MP3, and a decoder that ignores the encoder's delay would put about 25 ms of
silence in front of it; song.json carries the guide's opening loudness in 1 ms steps, and the page
finds any such silence by sliding the decoded opening against it and starts the guide past it
(checked on raw decodes of the real guides: 25.0 ms found against LAME's 25.06 ms; Chromium trims it
itself). Each take's sidecar records all of these numbers, so any of them can be undone later.
