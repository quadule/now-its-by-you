# Overnight, 2026-09-26: what changed, what to hear, what to reconsider

The artist, going to bed: "please take this as far as you possibly can overnight, improving
anything and following the lead of my previous decisions to improve the quality and variation of
the music. Just make changes in atomic commits and flag anything I might want to reconsider later.
... Remember that we want to be able to distribute this as a self-contained application attached
to the audio file."

The asks this answers:

- **The voice:** "make the voice less robotic (we don't need to *try* to make it sound synthetic)".
- **Variety:** "strive for more variation in arrangement and genre too".
- **The deliverable:** a studio to explore and edit before recording, and a self-contained
  application attached to the audio file.

This file is updated through the night; the newest state is at the top of each section.

## Listen first

(filled in as the work lands)

## What changed

### The seed packet: the song file carries its program (landed)

A rendition is now one file, `render --pack`: a FLAC that plays anywhere and is also a zip of the
program, the song, its record and its words. `python3 song.flac new` sets the program up (asking
first) and sings a new version on that computer, as the file's child and a packet in turn.
docs/PACKET.md has the details and what was checked.

### Swing had its lilt backwards in four songs (fixed)

The swing was measured from each song's first pickup instead of its first bar line. Songs whose
pickup is an eighth before a 4/4 bar (G, H, I and K) therefore had their beats pushed late and
their off-beat eighths left on time: a reversed, short-long lilt, with every bar line late too.

**Now:** the beats stay on the grid, only each off-beat eighth is late, the band and the voice
move together, and sections start on their bar lines. tests/test_swing.py checks all of it.

**What didn't change:** the seed, the karaoke guide, the training corpora (all swing 0), the other
songs, and the compound meters. All realize byte-identically.

**What did change:** every machine-sung rendition of G, H, I and K. Each note moves by swing/3 of
an eighth: 6 to 16 ms in tonight's examples (swing 0.06 to 0.15), up to about 60 ms at the
highest swing a machine can reach (0.6).

The examples are re-rendered. The old versions are in `before-swing-fix/` beside them, in
renders/production/lineage/ and renders/production/variation/, and each README lists every
file's shift. The drift agent re-renders its evolution examples, and the sing page's refactored
clock gets the same fix.

### The voice

(in progress: the learned voice trained only on our own house singers; a delivery agent; a
vocoder agent)

**The learned voice is ready to become the default:**
- *Clearer in the mix:* in H's full mix, Whisper mishears 15.1% of its words, against 34.7% for the
  formant singer. This is the ElevenLabs-voiced benchmark, which never ships; the house model is
  the one that would.
- *Same balance:* it sits where the formant singer did (voice bus -14.0 vs -13.7 LUFS, clarity
  +8.4 vs +9.0 dB), so the mix needs no retuning.
- *A voice per machine:* each machine gets a singer of its own, a blend of the learned singers,
  inherited like everything else.
- *The bridge's lineage choir sings in the voices of the earlier versions:* the record now
  remembers them, the parent's first. Before, the choir was stand-ins.

Measured before the night's work, as automatic naturalness (UTMOS: a speech-trained predictor, so
a rough guide on singing):

| Voice | Score |
|---|---|
| the formant singer | 1.47 |
| the first learned model | 1.68 |
| the learned benchmark | 1.95 |
| SoulX, the teacher, on the same song | 2.4 to 2.7 |

Our vocoder alone costs about 0.25 of that; the model and the delivery cost the rest.

### Genres and arrangement

**Styles (landed on the styles branch; docs/STYLES.md).** Every rendition is now played in a style: a
tradition the song has been carried into, with its own band, feel, harmony and arrangement.
- *Thirteen styles on a ring:* synth folk, indie, gospel, blues, country, a string band (old-time and
  bluegrass), a shanty, the seed's ballad, chamber folk, a singer-songwriter, a lullaby, ambient and
  lo-fi. Neighbours share instruments or a feel.
- *How they travel:* a machine's harvest gives it a home on the ring. A child keeps its parent's style
  about three times in five, otherwise it steps to a neighbour. A machine singing one parent day after
  day changes style about twice a year, never back and forth. No style (the seed) is byte-identical.
- *Arrangement within any style:* a pad or a cappella start, a count-in, a bare verse, stop-time, a
  breakdown, a half-time bridge, entrances line by line, a lift to the last refrain, a cold stop, a
  repeated last line, a plagal amen. Backing voices come from the lineage's own singers: the gang,
  thirds, answers, or oohs.
- *The song in three:* a waltz or slow six-eight re-bars H so every stressed syllable lands on a
  downbeat.
- *Listen:* renders/production/styles/ (README.txt): the tour first, then the lineage, then the songs.
- *Stand-ins:* the new instruments are played by the seed band's own models until the instrument
  modules land. For now the styles differ in rhythm, harmony, form, texture and mix, not yet in timbre.
- *To reconsider:*
  - the rates (`PULL_STYLE` 0.1, `STYLE_SPAN` 1.1 in songbird/style.py);
  - the palette and the ring's order (`STYLES`, `RING`);
  - that backing voices are only the lineage's own, so early generations sound thin;
  - the styles' leans on the singer and the mix;
  - that from the seed a first child can only reach the shanty or chamber.
- *Open problem:* Whisper hears the words worse in most styles than in the ballad (STYLES.md,
  "Measurements"). In chamber, even a cappella with the ballad's singer and mix, it stays near 50%.

### Evolution, the studio, the sing page

(in progress: the drift of melody and words, the studio)

**The sing page (landed).**
- *The melody guide:* the karaoke has a melody-only guide, now its default. The tune is on the
  band's whistle, doubled softly an octave up, over a quiet pulse that counts each line in.
  Listen: renders/production/sing/h-melody-guide.mp3.
- *Singing from anywhere:* web/sing/ is a Cloudflare Worker and page for songbird.quadule.com.
  - one-time invitations, which expire after 7 days and hold up to 30 takes;
  - takes stream into a private R2 bucket, checked by the page's own SHA-256;
  - tools/invite.py mints invitations, lists them, fetches takes into recordings/ and revokes them.
- *Not deployed:* docs/SING-ONLINE.md has the steps (wrangler login, a bucket, a KV namespace, a
  secret, and quadule.com's DNS on Cloudflare for the custom domain).
- *Not yet tried on a real phone:* send one real three-minute take from a phone to the deployed
  site before inviting anyone.

## To reconsider

Each item names the choice, why it was made, and how to undo it.

1. **The packet is a polyglot: FLAC plus an appended zip.**
   - *Why:* players, unzip tools and Python all read it.
   - *The cost:* the FLAC reference tools (`flac -t`, `flac -d`) report the appended archive as an
     error after decoding every sample, and macOS `ditto` won't unzip it.
   - *The alternative:* the plan's own fallback, the archive in a FLAC metadata block, which is
     strictly valid FLAC but no longer unzippable or runnable.
2. **A packet run fetches its dependencies.** The first run asks, then fetches them from PyPI
   (~150 MB) into ~/.songbird. Carrying them inside the file would tie it to one platform and add
   about 100 MB.
3. **Where the seed and its program hash are published.**
   - *Why it matters:* a careful stranger can't look Songbird up before running a 13 MB "song" that
     wants to set up 250 MB.
   - *The suggestion (the packet review's):* one line in README.txt saying where the seed and its
     program's hash are published, e.g. songbird.quadule.com. It keeps the anonymity ("Who made
     this song? Nobody knows.") without the smell.
   - *Related:* signing the program would let a packet refuse modified programs, but it sits
     awkwardly with CC0 and with anyone packing their own changes.
4. **Whether the seed carries its day.** A seed rendered without `--date` has no rendered_at, so
   its archive's entries are dated 1980.
5. **The tags use a working title.** Rendered FLACs now carry the genome's title (e.g. "Now It's
   by You") and "Songbird" as the artist until you choose (docs/STATEMENT.md proposes "Nobody
   Knows" and "Nobody").
6. **The sing page's release and retention.**
   - *The release text:* web/sing/consent.md. It isn't legal advice and says nothing about
     payment.
   - *Withdrawal:* who singers contact to withdraw is "the person who sent me this link".
   - *Retention:* unfetched takes wait 30 days.
   - *Invite notes:* KV keeps them 90 days after expiry, so perhaps use initials.
7. **The melody guide's levels.** By ear: the whistle's statements in the intro and turns, the
   octave doubling, and the pulse (6 dB down under the singing).
