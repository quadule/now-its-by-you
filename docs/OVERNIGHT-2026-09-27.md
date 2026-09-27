# Overnight, 2026-09-27: what changed, what to hear, what to decide

The artist, going to bed around 1:30 AM PT: "please take this as far as you can overnight". Singing
closes tonight at 10 PM PT; the contest render is due 4 AM PT Monday. Nothing was deployed or pushed;
the site was rebuilt and checked, and waits for your `wrangler deploy` (below).

## Do first

1. **Deploy the rebuilt site** (all 90 guides: the new tune, Open Door as the arrangement, the voice
   fixes, everyone's phrasing from 28 takes by four singers; every spec still takes takes sung to the
   live guides, so nobody mid-song is interrupted):

       cd ~/Code/songbird/web/sing && npx wrangler deploy

   Built 02:32 PT (`web/sing/public`, 90 guides, 452 MB) from the committed song and code, everyone's
   phrasing from 28 takes; checked: all 90 specs list the live guides among the ones they still accept.

2. **Restart your sync loop** on the new code (the extractor's stamp moved with Codex's merge; every
   counted take was measured again, 4 minutes):

       uv run python tools/invite.py sync --watch 120 --measure --no-versions

3. **Restart the karaoke server** (port 8765) if you use it today: it runs old code.

## Listen first

1. **renders/review/contest-candidate.flac**: what the contest render would be right now. The default
   arrangement (Open Door), the lead sung everyone's way (28 takes, 4 singers), the lineage choir's
   three voices each sung a singer's way (gorman + the open-call singer; your wife; you), thirds behind
   the last two refrains. Packed: `python3 renders/review/contest-candidate.flac` says what it is.
   -14.04 LUFS, LRA 9.0 LU, true peak -1.05 dBTP; by section (LUFS), a build of 5.9 dB from the first verse to the last refrain:

   | section  | LUFS   |
   |----------|--------|
   | intro    |  -20.5 |
   | verse    |  -17.2 |
   | refrain  |  -15.6 |
   | turn     |  -20.6 |
   | verse    |  -16.0 |
   | refrain  |  -12.1 |
   | turn     |  -20.8 |
   | bridge   |  -13.0 |
   | refrain  |  -11.3 |
   | tag      |  -11.5 |

2. **The build the mixer was hiding.** renders/review/open-door.flac (last night's edition, level
   lead) against the scratch render that showed the fix, and the candidate above: verse 1 now sits
   at -15.5 LUFS and the last refrain at -12.2, a 3.3 dB build where there was 0.5.
3. **The roughness.** Both fixes are in the candidate: the lead's saturation down (0.2 → 0.05: it was
   distorting the loudest syllables 12 dB more than now, exactly "as the voice gets loud"), and the
   vocoder's pulses spread a little more (spread 0.25, scatter 0.5; the highs bunched at each pulse,
   worst in low voices). The advisor's A/B pair of a low voice is renders/review/low-voice-before.wav
   and low-voice-after.wav, if you want the isolated effect.

## What changed (all on main, e0b33c4 and after; the full suite on it: 1293 passed, 11 skipped)

Commits, oldest first: 4ec52a0 the tune · 1456235 the first refrain's questions · 4d4d065 + 3ca1db5 Codex's
branch (the merge commit came out with only its new files: a `git stash` while it was staged unstaged the
rest, which 3ca1db5 puts in; the working tree and every test run had it all along) · 77aca7c lone refrain +
tests · 332c43e hard_notes · f934b1a the 8 MiB goal · 1c9291d bird verse · 5540454 Gemini's couplet, verses
and readings · d59f95d Open Door as the seed's own · 0470d1a six verses from the lyric review · f4f5345 the
lead's arc and saturation · 517e727 vocoder texture · b0ac4a9 vowel end · 735aa18 tools/everyone.py ·
96dbdb3 goldens and this summary · e0b33c4 tests.


- **Tune** (commit 4ec52a0, your "yes let's go"): v2's pickup and "and", r2's "you", b2's "like a",
  b3's "and", b4's "you". Pitch only. Old takes keep their timing and loudness data, not their tuning
  on those notes. hard_notes.py now measures old takes against the tune as it is (it was still
  comparing to the old notes, which made the changes look undone).
- **First refrain asks made, wrote or sang** (1456235), preferring a word no head in the song fixes.
- **Codex's branch merged** (4d4d065): performances travel in packets and to children; crowded
  learned timing keeps syllables in order; fairer phrasing learning (the vibrato sentinel bug was
  real); listening editions; `songbird budget`. **The 8 MiB is now a goal that warns, not a wall**
  (40 MiB refuses): your "don't let it limit experimentation".
- **Open Door is the seed's own arrangement** (`seed_params` style/band/mix): harp under the first
  line, players entering one by one, the upper band out for the first half of the last refrain; with
  the mix review's tweaks: `forward` 7.5, `width` 1.25, `drum` 1.5. Timing is identical to before, so
  the deploy is safe mid-session. The edition file spells the same choices out.
- **The lead follows the arrangement's energy** (`mixing.lead_lift`, LEAD_ARC 6 dB per unit of energy,
  -2..+2.5 dB, smoothed a second): the mixer used to bring the voice to the same loudness in every
  sung section, so the band's 6.6 dB build reached the record as 0.5 LU. docs/MIX.md has the numbers.
- **Voice roughness**: `VOICE_DRIVE` 0.05; `Texture` spread 0.25, scatter 0.5. Word recognition
  unchanged within noise (dry 12.9→13.4%, in the mix 14.8→15.4%, of 657 words).
- **Bird verse** rewritten (lines 3-4, your "both are good"): "It sang it at dawn to a bird on the
  wing, / who {carried it home | took it back home} to the young in her nest." Set F holds the first.
- **From Gemini's branch** (song_and_vocal_enhancement, kept as a branch): the wind couplet (Set E's
  second refrain now sings it, blue stays in A and C), the bone and border verses (their focus marks
  stripped: the bank is unmarked), six lexicon readings (banjo, sunday, inside, misheard, whatever,
  fifteen), and its takes.py path fix. Not taken: readings that flatten everyone/anyone/someone/
  somewhere/nowhere/afternoon (English keeps a full vowel and a secondary stress there; afternoon's
  stress *is* on noon), and its hard_notes categories (they'd conflict with the tune correction;
  worth merging by hand later).
- **Tried and dropped**: singing only primary stress as stressed (Gemini's diagnosis, my rule):
  12.9% → 14.3% misheard, everywhere, because the throat was taught with secondary stress as
  stressed. docs/DELIVERY.md.

## Six new verses, and a lyric review to read

A lyric advisor read the whole bank against the tune and the voice's mishearings
([docs/LYRIC-REVIEW-2026-09-27.md](LYRIC-REVIEW-2026-09-27.md)). Its six verses are **in the bank**
(you asked for lots; remove any you don't want): *machine* (a girl sings it to a box and the lineage
answers), *court* (two men sue over whose it is), *car* (a father's kids call it his), *voicemail*, *stroke*
(a man a stroke left wordless finishes the song), *hymn* (1750: a minister makes it a hymn, the inn keeps it).
Not applied, for you: its rewrites of bone ("the words were the flesh, and the tune was the bone") and
border ("over the fence"; "the tune had no papers, and needed no gate"), "carries on through" for wind,
a meter slip in wall's last line, two couplets, a "sang" head, and drop-in swaps for the surely-misheard
words (put, disc, ruined, hiss, hummed, low, cannon, counting).

## Decide

1. **Bone and border lines.** Two lines read weak to me; your call (nothing changed):
   - bone, line 3: "The words were all weathered and buried in cold" → "The words were all weathered,
     worn thin by the cold".
   - border, line 4: "the sound of it crossed with no need of a sky" → "but nothing could stop what
     was sung to the sky".
2. **Backing voices in the default.** Open Door's `backing: thirds` only sings with `--choir`; the
   default seed render has none, the contest candidate has three volunteers' voices. The advisor
   suggested `--choir 2` plain stand-ins for the seed; I left the seed solo (your voice philosophy).
3. **Louder master for the contest?** -14 LUFS is right if the contest normalizes loudness; if it
   plays files as they are, -12 LUFS costs almost nothing here (limiter max 0.6 dB). Ask them.
4. **Gemini's remaining ideas**: hard_notes categories and `--as-variants` (folk variants into the
   lineage's drift); the "pickup lift" it saw (so, → la,) is 2-of-3 singers, not adopted.
5. **The band under the rests.** Every time the singer stops, the record drops 6 dB (the intro and the
   turns sit at -20 LUFS against -14 sung). The mix review's suggestion: `RIDE` in mixing.py from 3 to
   5 dB, a less deflating intro (the turns barely change: the ride's 1.5 s up and down eats most of a 5 s
   turn). Not done tonight: it changes every guide's mix, so it wants a rebuild you'd hear first.
6. **The bridge's last line**: all three singers went *up* on "leave **it** alone" instead of down
   to do, each to a different note. More singers tonight will settle it (`tools/hard_notes.py`).

## Tonight's routine (unchanged)

Final `sync` after 10 PM; measure is automatic; then the contest render:

    uv run python tools/everyone.py --render renders/review/contest.flac

(the karaoke's "everyone's way, with the lineage choir" does the same from the page).
