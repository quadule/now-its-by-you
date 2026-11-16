# The studio's live sound: a section looped with the real sound, kept up to date

*An engineering note (November 15, 2026). What it covers: hearing an edit with the real singer and band while
a section loops; how fast that is; the sketch in the meantime; single notes with the instrument's own sound; where
it runs on its own and where it waits to be asked. The studio itself is docs/STUDIO.md; the transport and its
two players are docs/notes/STUDIO-REDESIGN.md.*

## What a person hears

Loop on, Sung chosen, a section selected, ▶: the section's preview plays round and round, made by the program
as a recording would be. An edit to it (a note, a chord, a drum hit, a level, a word) is heard at once through
the sketch's voice (the note or hit itself), while the section is made again in the background; the new audio
takes over at the next bar line. Until it does, the old audio keeps playing and the transport says
**updating** (its progress bar filling). Edits made in quick succession are made once, as the last of them
leaves the song. Stop, and nothing new is started.

The sketch is untouched: Sketch with Loop on loops the sketch, as before; Loop is one switch on the transport
(L) for both.

## The loop

A section's preview is a file cut from the whole song's score (`studio.window`, `studio.cut`): from a breath
and a beat of the band before the section's first pickup, to where the next section's pickup begins, with 2.5 s
of ring after and fades in and out. It isn't a loop as it stands: its start is the end of the section before it.

So the page plays it through WebAudio (live.js, `Looper`), on the section's own clock, which the preview's job
now ends with (`result.loop`, kept beside the file as `<key>.loop.json` so a preview made before is looped too):

- `start`: where the section's first bar line is in the file (seconds);
- `length`: the section's length, bar line to bar line (seconds, by the score's own clock);
- `head`: the section's own pickup before its first bar line (seconds, 0 for none);
- `bars`: each bar line of the section, in seconds from its first.

The first time round plays the file from its beginning (the breath, the band before, the pickup), as ▶ always
has. Each later time round starts `head` before the bar line, so the pickup is sung again, and the time round
before is faded out over 120 ms from there: the section's own ring is cut short at the seam (as a DAW's loop
cuts at its end), never doubled with the band of the section before it. A file without `loop` (none made
before this note) loops as it is.

New audio takes over at the next bar line of the loop (`swapTime`): the new source starts there at the same
place in its file, the old fades out over 20 ms while the new fades in. A bar line less than 60 ms away is
too near to schedule cleanly: the one after it is taken.

## What audio is played, and how it can't be stale

The page's view of the song (`/api/song`) carries each section's preview key for the edits it was made from
(`listen.sections`: `Studio.key`, a hash of everything the render depends on). The loop's audio carries the key
of the job that made it. The loop plays the newest audio it has; it says **updating** whenever

- the edits have moved on since the view the page has (a view is on its way), or
- the audio's key isn't the view's key for the section.

Audio is never swapped in unless its key is the key the page wants now; a render finished for edits since
replaced is thrown away (and the newest asked for). So whatever plays as the real sound is either exactly the
edits shown or marked as catching up. The section is followed by its id: moved, it is looped where it is now;
deleted, the loop stops.

## Coalescing

`keeper` (live.js) is the bookkeeping, pure and tested (tests/studio_live.test.cjs): `want(target)` says what
the page wants (its key and the edits it is of); a render is asked for once edits have settled for 120 ms, so a
burst of edits (undo held down, a drag's steps) is made once; at most one render is in flight. A want made while
one is in flight drops it if it is still waiting its turn (the renderer's cancel), else waits for it: the
studio's one renderer makes one thing at a time anyway, and an open studio lets a visitor ask for their next
only once theirs is made. When it ends, its audio is offered only if its key is still the one wanted and is the
key that was asked for; else the latest is asked for. A render that fails says so ("couldn't make it") and isn't
asked for again by itself; the next edit tries. Back to what plays (an undo) is current at once and makes
nothing. Stopping the loop asks for nothing more; the job in flight finishes into the cache, unheard. The renderer
is asked after every 150 ms for a looped section (`preview({ quick })`) on this computer, as ever in an open studio.

## Fast: what is made again for each kind of edit

`synth.render(cache=...)` keeps each part's stem (and what the mix's channel makes of it) in the studio's
`StemCache`, keyed by what that part's maker reads (`synth.cache.keys`). Measured on this computer (24 threads,
native) for H's first verse with the learned throat, `Studio._section` alone:

| edit | before | after | what is made again, after |
|---|---|---|---|
| cold (nothing kept) | 1.89 s | 1.70 s | everything |
| the same again, the file gone | 0.66 s (one stem didn't fit) | 0.53 s | nothing but the mix |
| a player's pan (`mix.guitar.pan`) | 0.94 s (every band stem made again) | 0.73 s | the guitar |
| a player's level (`band.guitar`) | 1.85 s (everything, the voice too) | 0.75 s | the guitar |
| a guitar line's notes | 0.75 s | 0.75 s | the guitar |
| a drum line's hits | 0.76 s | 0.79 s | the drum |
| one melody note | 1.43 s | 1.13 s | the voice |

(Each row's edits are on top of the row before's; the "before" column kept only what fitted in 64 MB.) Every
preview pays the mix itself, the buses and the room, about 0.45 s, and its master and file, 0.05 s: that is the
floor. A tempo, a key or a style changes every part (1.4 to 2.0 s, as cold).

As the page has it, from the edit's `/api/listen` to the file fetched, asking after it every 150 ms, over the
studio's own HTTP (H's first verse; its first refrain): a level or a pan 0.80 s (0.61 s), a guitar line 0.95 s
(0.62 s), a drum line 0.80 s (0.65 s), a melody note 1.54 s (1.55 s), a tempo 2.01 s (1.40 s). Then the page
decodes the file and the new audio takes over at the next bar line: a bar of H is 2.6 s.

On the device a warm section is several seconds (docs/notes/BROWSER-RENDER.md: H's refrain 4.4 s in Chrome),
which is why it waits to be turned on there.

Two keys were wider than what the makers read: every band stem's key held the whole sound design (so a pan on
the guitar made the harp again), and every stem's key held the whole band dict, levels included (so a level on
the guitar sang the voice again). The makers read: an instrument, its own `sound.players[name]` and the band's
settings with its own level (`settings[name]`, `gains[name]`; render_part and render_other read no other
player's); the singers, only `band["parts"]` (whether the voices sing alone, `synth.matched`). The keys are
those now. The budget was 64 MB, less than one verse's band (a stereo float64 stem of 20 s is 14 MB): a
studio on this computer keeps 256 MB, a public one 64 MB.

**The voice.** The singer (formant and learned throat alike) sings a part as one: one random stream through the
whole part, the timbre drawn for its median pitch, every vowel levelled against the part's median vowel. A line
sung alone is not the same samples as that line sung in its section. So an edited sung line sings the
section's voice again, whole: exact, and the dearest edit (about 0.6 s of the 1.1 s above). It is not traded for
speed. Exactness is tested: a verse made through the kept stems after a pan, a level, a guitar line, a drum line
and a melody note, one after another, is the same 16-bit samples as the same edits made cold in a fresh studio,
and each step made only its own part again (tests/test_studio_live.py); every instrument of H's verse makes the
same stem whatever another player's level or pan.

## Immediate feedback

An edit sounds at once, over whatever plays: a melody note moved or chosen (the sketch's tone, as before), an
instrument's notes drawn, moved, pasted or changed and a note chosen (up to four at once), a drum's stroke struck
or its level changed. An instrument's or a drum's is in its own sound where the studio has that note (below),
else the sketch's. A melody note's tone over a sung loop leaves the loop playing; elsewhere it stops the sung
audio as it did. An overlay of the edited part's whole sketch for the first time round was considered and left
out: on this computer the real audio is there within a bar or so, and the sketch's part over the real band
(its voicing and timbre aren't the band's) reads as a second, wrong band more than as the edit.

## A single note with the instrument's own sound

`/api/note` (`Studio.note`): one note of a player, as its maker makes it (`instruments.render_part`, the
version's band settings and the player's sound), dry, levelled to the velocity's class (soft, medium, firm,
hard) and kept as a preview file (2 s, about 100 KB). A note of H's band takes 5 to 30 ms to make (90 ms the very
first, compiling), 27 ms asked over HTTP and fetched, 1 ms when it is made already. The page (live.js
`samples`) keeps decoded notes in an LRU of 24 MB (a note is 0.7 MB decoded: about 34); a key with no note yet
sounds the sketch's tone at once and asks for it, so the next press is the instrument. Once an instrument's roll
has its notes, the octave around them is asked for, one after another; a drum's grid, every piece. The file's
key hashes the program, the player, the note as made (its pitch, the velocity's class, a drum's piece), the
band's settings as that player's maker reads them, its sound, the seed: a level or a patch on that player is
another note, another player's isn't. The page asks again after each edit (a new revision), and the studio
answers the same file where nothing that player reads changed. The melody's keys are the sketch's tone: the
singer sings a syllable, not a note, and a sung note alone wasn't in scope.

## Where it runs on its own

`mayRenderAhead(where)` (live.js) answers one question: may the page start a render nobody pressed for?

- a studio on this computer (`songbird studio`): yes, and the single notes;
- on the device (the web build): no, and no single notes (a section takes many seconds there and holds
  hundreds of megabytes);
- a studio shared by a key: no (the computer serving it is someone else's), but single notes (a few
  milliseconds each);
- an open studio (`--public`): no, and no single notes (its renders are counted and queued for everyone;
  `/api/note` refuses there).

Where it doesn't, the sketch options (▾ by Sketch and Sung) have **Keep the sung loop up to date** (kept in this
browser): on, an edit makes the looped section again as it would on this computer, through the same queue and
limits (each counts as a preview in an open studio); off, the loop says **earlier version** after an edit, and
■ then ▶ makes it again. The first time round is made whenever the loop is played, everywhere. The one function
is tested for each (tests/studio_live.test.cjs).

## What is where

- live.js: `mayRenderAhead`, `keeper`, `looper` (with `shape`, `roundAt`, `offsetAt`, `swapTime`, `fraction`),
  `samples` and `lru`; studio.js: the loop (`loopSection`, `liveChanged`, `liveState`), the setting, the notes;
  score.js: the Loop switch (L), `loopTick` (the transport while it loops); composer.js, parts.js, drums.js: the
  edit heard at once, the notes asked ahead; renderer.js: `quick`, and a section made in the browser ending with
  its loop and its file.
- studio.py: `loop_of` (and `<key>.loop.json`), a job's key, `Studio.note` and `/api/note`, `STEM_CACHE_MB`;
  synth/cache.py: the keys; web/studio-wasm: a section made on the device ends with its loop.

## The sketch

The sketch stays instant and plain. A band player's own sketch (its roll's Hear phrase, its notes written, its
part played on the page) is by its family, from its name: plucked, bowed (a swell, a slow vibrato), blown, keys
(struck, then held lower), a round bass, a held drone. The tune, its chords and its bass are as they were.

## Left as they are

- The whole song looped sung is the file looped by the player, as made: it isn't made again as it is edited.
- The Page doesn't mark the line being sung while a section loops (it follows the player's own audio).
- An edit stops the sketch while it plays (composer.js stops on every new view): the sketch's loop isn't kept
  going through edits.
