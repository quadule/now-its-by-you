# Overnight, 2026-09-26: what changed, what to hear, what to reconsider

> The night of 2026-10-07 (new house singers from our own voice) is in [OVERNIGHT-2026-10-07.md](OVERNIGHT-2026-10-07.md).
>
> The night of 2026-09-27 (the last before singing closes) is in [OVERNIGHT-2026-09-27.md](OVERNIGHT-2026-09-27.md).

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

Everything is merged into main in atomic commits and merges, with 1053 tests passing. Nothing was
pushed or deployed.

## Listen first

1. **The voice, before and after.** H's first verse and refrain, everything else the same:
   - renders/production/voice/1-formant-singer.verse-refrain.flac, the old default;
   - renders/production/voice/2-learned-voice.verse-refrain.flac, the new default.
2. **The genre tour.** renders/production/styles/tour/01-13: one made-up machine on one day, in
   each of the thirteen styles, with the new instruments and the learned voice. README.txt there
   says what each is.
3. **A lineage that wanders genres.** renders/production/styles/lineage/0-6, the *.verse-refrain
   files first: the seed's ballad, then a shanty, a string band, country twice, blues and gospel.
   Each generation also carries the melody's small variants and the words' slow changes.
4. **Whole songs in four styles:** renders/production/styles/songs/.
5. **The instruments alone:** renders/production/instruments/, in README.txt and README-b.txt.
   The kit, brushes, banjo rolls, piano, organ, mallets, synths, chip, strings and more.
6. **The melody-only karaoke guide:** renders/production/sing/h-melody-guide.mp3.
7. **The studio.** Run `uv run songbird studio` (it opens a browser), or see the screenshots in
   renders/production/studio/.
8. **The details, if you want them:**
   - the melody and word drift on their own: renders/production/evolution/, with a changelog and
     piano rolls, sung by the old voice;
   - the delivery A/B: renders/production/delivery/;
   - the vocoder A/B: renders/production/vocoder/.

The drafts made before the instruments and the learned voice landed are kept beside the new
files: styles/draft-standins-formant/, lineage/before-swing-fix/ and variation/before-swing-fix/.

## What changed

### The voice: the learned singer is now the default

The house model is trained only on SoulX singing our own scores in timbres our own formant singer
prompted. No ElevenLabs audio is anywhere in its lineage. It ships in songbird/synth/throat.npz
(3.6 MB), and VoiceParams.engine defaults to "learned".

| On H | Formant singer | Learned voice, now |
|---|---|---|
| Words misheard, dry | 19.6% | **11.9%** (as good as the ElevenLabs benchmark) |
| Words misheard, in the full mix | 34.7% | **12.8%** |
| Naturalness (UTMOS, a rough speech-trained guide) | 1.46 | **1.91** |

Three pieces of work got it there, besides the model itself:
- **Delivery** (docs/DELIVERY.md): measured against a natural singer on our own notes.
  - each move between notes has its own timing and overshoot;
  - pitch sags through consonants;
  - vibrato comes on some held notes, each note's its own;
  - slow drift, and loudness that wavers inside a held vowel;
  - real breaths, shaped noise instead of silence.
- **The vocoder** (docs/THROAT.md, "Vocoder"): it buzzes less (upper harmonics loosened) and its
  formants are sharper.
- **Each machine sings with a singer of its own,** a blend of the ten house singers, inherited
  down a lineage. The bridge's lineage choir sings in the actual voices of the earlier versions,
  which each file now remembers.

### Genres and arrangement: thirteen styles, and thirty-nine new instruments

- **Styles** (docs/STYLES.md). Every rendition is played in a style: a tradition the song has been
  carried into.
  - *The thirteen:* synth folk, indie, gospel (12/8), blues (shuffle), country (shuffle or
    waltz), string band, shanty, the seed's ballad, chamber, singer-songwriter, lullaby, ambient,
    lo-fi.
  - *How they travel:* they sit on a ring. A machine's harvest gives it a home there, and a child
    keeps its parent's style about 3 times in 5, otherwise stepping to a neighbour. One machine
    changes style about twice a year, never flickering.
  - *Arranging within any style:* a count-in, an a cappella or pad start, a bare verse, stop-time,
    a breakdown, a half-time bridge, a key lift for the last refrain, an amen, a cold ending, and
    backing voices (gang, thirds, answers, oohs) sung by the lineage's own voices.
  - *No style chosen:* the seed is the ballad band as before.
- **Instruments** (docs/INSTRUMENTS.md, docs/INSTRUMENTS-B.md): all synthesized, measured against
  real ones, levelled to the band.
  - *Keys:* piano, electric pianos, tonewheel organ with rotary speaker, harmonium.
  - *Mallets and bells:* vibraphone, marimba, glockenspiel, celesta, music box.
  - *Synths:* analog pad, bass, lead, arp and sub bass; chip voices; two drum machines.
  - *Drums and percussion:* a drum kit (sticks, brushes, rods, mallets); claps, stomps, shaker,
    tambourine, cajón.
  - *Strings and more:* banjo, mandolin, nylon guitar, ukulele, electric guitar (clean, crunch,
    tremolo), electric bass, cello, viola, a string section, harmonica.
  - *The styles play them by name.*

### The tune and the words evolve (docs/EVOLUTION.md)

- **The melody** gains and loses small variants down a lineage: grace notes, mordents, turns,
  passing tones, anticipations, a resized leap, dotted pairs.
  - *Guards:* the contour, the stresses, the phrase endings, the scale and the hooks.
  - *Limits:* at most 12% of a section's notes.
  - *Who sings them:* the singer, and the band's lead where it states the tune.
- **The words** hold for weeks and change a verse or a slot word at a time, instead of being
  redrawn every render.

### The studio (docs/STUDIO.md)

`songbird studio`, or `python3 song.flac studio` from any rendition, opens your version of the
song today.
- **It explains:** every choice, and why, in plain words.
- **It explores:** other days, chance and other machines.
- **It takes changes:** words, key, tempo, band, mix, shape, and dropping a melody variant.
- **It speaks the new systems:**
  - *Style:* the style card says the style and its players in plain words. You can change the
    style, its feel, its ending, its backing voices and the lift, and its band and tempo follow.
  - *Words:* the words are the ones the lineage hands down, each labelled "handed down" or "new
    this time", with the reason. A word you choose changes only that word.
- **It records:** one file that carries the program, the child of the version you opened.

### The song file carries its program (docs/PACKET.md)

`render --pack` makes one FLAC that plays anywhere and is also a zip of the program, the song and
its record. `python3 song.flac new` sings a new version on that computer, after asking first.
After a Fable review, the program:
- refuses a file whose program doesn't match its record;
- takes a parent file only if its audio matches its id;
- carries the full CC0 licence;
- carries tags players can show.

### The sing page (docs/SING-ONLINE.md)

A melody-only karaoke guide, now the default, and a Cloudflare Worker and page for
songbird.quadule.com, with one-time invitations and private storage for takes. It isn't
deployed: you run `wrangler login` and the steps in the doc.

The karaoke's full-song guide was re-rendered, so the learned voice sings it. Your two earlier
takes stay pinned to the guide they were sung to.

### Fixed

- **Swing had its lilt backwards** in G, H, I and K, whose first pickup is an eighth. The beats were
  pushed late and their off-beats left on time. Now the phase is counted from the bar line. The
  old examples are in before-swing-fix/.
- **The new instruments reach the mixer's proper strips** (organ, keys, guitar, strings) and are
  played by their own modules, not stand-ins.

## To reconsider

Each item names the choice, and how to undo it or where it lives.

**The voice**
1. **The learned voice is the default.** Undo: `engine: str = "formant"` in songbird/synth/voice.py.
2. **The delivery's randomness is set to 0.7** (`spread`), not the natural 1.0, because 1.0 cost
   words.
   - *Line ends:* still let go early.
   - *Breaths:* at the teacher's -36 dB, so quiet in the mix; -30 would make them a feature.
3. **The vocoder sharpens formants ×1.5.** One of two automatic judges dipped slightly, so listen
   for roughness or a metallic ring. `SHARPEN` in songbird/synth/throat.py.

**Genres and arrangement**
4. **How fast styles travel:** `PULL_STYLE` 0.1 and `STYLE_SPAN` 1.1 in songbird/style.py.
   - *Near the seed:* a seed's first child can only reach the ballad's neighbours, the shanty or
     chamber.
   - *Backing voices:* they are the lineage's own, so early generations sound thin.
5. **Words in the busier styles.** With the learned voice and the real instruments, Whisper
   mishears 1.4% of the tour's words in the ballad and lo-fi, and 18% at worst, in indie (country
   16%).
   - *Before:* with the old voice and stand-ins it was 29% to 71%; chamber, the worst, is now 10%.
   - *Where to look next:* indie's and country's kit and electric guitar in the voice's range.
   - *The numbers:* renders/production/styles/tour-wer-learned.txt.
6. **Instruments:**
   - *The kit:* sits at folk level (rock wants it louder) and is heard from the drummer's seat,
     with the hi-hat on the left.
   - *Never delivered:* the pedal steel, slide guitar, accordion and concertina, so stand-ins play
     them.
   - *Names in the docs:* some docstrings name the machines modelled (808, 909, Juno).

**The melody and the words**
7. **How fast the melody and the words drift:** the constants at the top of songbird/evolve.py.
   - *The quick ornament tones* may touch fa and ti.
   - *The form can flip back within a week,* as it always could: `choose_form` has no hold.
8. **The first child always changes couplets**, because the bank's rules make a child sing others
   before the canon. So the studio's words card says "six changes this time" at the first
   generation.
9. **One machine's style can flip for short stretches.** Across the studio's six-year timeline, one
   machine moves between the ballad band and the shanty and back, and the tempo jumps with each
   style. A stronger hold is in songbird/style.py (the Schmitt trigger's margin).

**The studio** (all in docs/STUDIO.md)
10. **The studio's defaults:**
   - a person's choices pass to their children;
   - "today" is noon UTC;
   - a phrasing isn't embedded in a record;
   - the comparison machines are named Ada, Basil and Coral.

**The sing page**
11. **The page's terms:**
    - the release text, web/sing/consent.md (not legal advice; nothing on payment);
    - who singers contact to withdraw;
    - 30 days for unfetched takes;
    - invite notes kept 90 days;
    - not yet tried on a real phone.
12. **The melody guide's levels,** by ear: the whistle's statements, the octave doubling, the
    pulse.

**The song file**
13. **The packet is a polyglot, FLAC plus an appended zip.**
    - *The cost:* `flac -t` complains after decoding every sample, and macOS `ditto` won't unzip it.
    - *The alternative:* a metadata block, which is strictly valid FLAC but no longer a zip or a
      program.
14. **The first run fetches dependencies,** about 100 MB from PyPI, after asking.
15. **Where the seed and its program hash are published.** One line in the README would let a
    careful stranger check a file before running it, for example on songbird.quadule.com. Signing
    sits awkwardly with CC0.
16. **Whether the seed carries its day,** and the tags' working title and "Songbird" as artist
    (docs/STATEMENT.md proposes "Nobody Knows" and "Nobody").

## After the first notes (2026-09-26, afternoon)

### Listen first

- `renders/production/refrain/seed-11.flac`: each chorus with words of its own, your "Nobody, so" in the
  middle one (its lyric sheet beside it). `seed-3.second-refrain.flac`: the song's own head asking "Who heard
  this song?".
- `renders/production/mix/hiss/4-hana.verse-refrain.before.flac` and `.after.flac`: the hiss (README.txt
  there has the other pairs, and the murmur that was removed, on its own).
- `renders/production/instruments/styles/country-steel.flac` against `country-standin.flac`, and
  `blues-slide.flac` against `blues-standin.flac`: the pedal steel and the slide guitar.
- `renders/production/instruments/shanty-concertina.flac` and `shanty-accordion.flac`: the concertina and
  the accordion.
- `renders/production/instruments/review-2026-09-26/styles/stringband-tour-before.flac` against
  `stringband-tour-after.flac`: the clawhammer and the mandolin's chop, heard for the first time (README-b.txt).

### What changed

- **Every chorus has words of its own** (docs/ARRANGE.md, songs/h-bank.md). The first asks who made the song
  and the last who owns it; each between asks something else. "While" varies from chorus to chorus, and each
  chorus ends its own way ("it goes", "who knows", "it grows"), so three choruses sing all three. The first
  and last keep "Nobody knows"; a chorus between may sing your head, "Who wrote this song? Nobody, so / it's
  yours if you sing it and then who knows?", as you wrote it, and when it does no other chorus says "who
  knows". The drift hands each chorus's words down and changes them a word at a time; the studio chooses
  them chorus by chorus. A Fable review tried to break the rules and found two bugs (both fixed).
- **Your verse swaps**: the girls, boys or kids in the field or yard; a quiet kid, with "their", "they" and
  "them" all through the verse.
- **The hiss** (docs/MIX.md, "The hiss"): the "s" sounds, and the reverb carrying them. The de-esser had
  never worked (it took half a decibel from an "s"), and the choir had none; both now take about 5 dB off a
  loud "s". Under it, the learned voice murmured wherever a singer rested (it had only ever learned short
  silences), and the choir's reverb spread the murmur through the room. The singers are now silent where
  nothing is sung, but for their breaths.
- **Four instruments finished** (docs/INSTRUMENTS-B.md): the pedal steel (E9, pedals and knee levers, a
  volume pedal riding each note) and the slide guitar (acoustic, resonator or electric, open tunings), the
  accordion (Stradella bass, musette tunings, bellows that turn when the air runs out) and an English
  concertina.
- **Five families reviewed by measurement**: banjo and mandolin (metal picks, a tuned head, the chop), the
  electric guitar and bass (the amp by the rig's heat, an audible tremolo, stiff strings), the cello, viola
  and strings (a swell bug, vibrato, a stereo section), the harmonica (legato across the holes, the blues on
  the cross harp). The string band had never played clawhammer or a chop: its parts asked for strums and
  ticks. Every instrument now has a mix strip that suits it.

### To reconsider

1. **How often your head comes**: in about half the songs with three choruses (three quarters with four).
   One number makes it rarer.
2. **"While" varying**: the review thought "while / when / if" changing from chorus to chorus reads as a
   slip, and suggested holding it once a song; I left it varying, as you asked for variety.
3. **Endings distinct** ("it goes / who knows / it grows" each once): my call on the review's advice, so your
   "who knows?" is always heard as a question. One line in the bank's rules undoes it.
4. **The de-esser's strength** (about 5 dB off a loud "s", at most 8); voiced "z" sounds could be caught
   harder. **A darker plate** is a matter of taste, left as designed. **Line ends** may sound clipped now
   that the murmur doesn't soften them.
5. **The accordion in the shanty**: about 3 machines in 10 now play the shanty's squeezebox part on an
   accordion (commit 5b14231, drop it to keep the concertina). The six-eight shanties' concertina now plays
   oom-pa-pa chords where it played bass alone.
6. **The pedal steel**: it sits 2-4 dB under where its stand-in sat; 45% of makers tune its thirds flat for
   sweeter chords, which sounds flat on a melody; a quarter of the blues slides are electric.
7. **Balances**: in indie the electric guitar still sits 8 LU under the acoustic; in the blues the slide's
   answers sit under the harmonica's.
8. **The harmonica**: keep the compromise and Marine Band tunings (the latter's thirds 12 cents low), and the
   songwriter's harp in a neck rack?

## Next

**The artist's first notes (the morning after), all done that afternoon (above):** each chorus's
own words; the "Nobody, so" head; the hiss. Seven more heads along the same lines were offered in
chat and wait for the artist's pick before they go in the bank.

**Then:**

- **Human singers.**
  - *Finding them:* docs/SINGERS.md has the brief and release.
  - *Recording:* the sing page is ready to deploy.
  - *What they bring:* the voice's next leap, and the first phrasings from real people.
- **Learn from singers.** Note shifts and ornaments (docs/MAKING-IT-THEIR-OWN.md). The variant
  record already takes `source: "sung:<name>"`.
- **A second, larger house corpus** and a retrained voice. More data has helped at every step.
- **Words in indie and country,** and deploying the sing page.
- **The song's title.**
