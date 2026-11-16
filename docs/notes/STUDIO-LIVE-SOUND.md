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

`Keeper` (live.js) is the bookkeeping, pure and tested: `want(key)` says what the page wants; at most one
render is in flight; when it ends, its audio is offered only if it is still wanted, and the newest want is
started if it differs. A want made while a render is in flight waits for it (a server's running job can't be
stopped; one still queued is dropped by the renderer's cancel). Stopping the loop stops starting; the job in
flight finishes into the cache and is not played.

## Fast: what is made again for each kind of edit

`synth.render(cache=...)` keeps each part's stem (and what the mix's channel makes of it) in the studio's
`StemCache`, keyed by what that part's maker reads (`synth.cache.keys`). Measured on this computer (24 threads,
native) for H's first verse with the learned throat, `Studio._section` alone:

| edit | before | after |
|---|---|---|
| cold (nothing kept) | 1.89 s | |
| the same again, the file gone | 0.66 s (one stem didn't fit) | |
| a player's pan (`mix.guitar.pan`) | 0.94 s (every band stem made again) | |
| a player's level (`band.guitar`) | 1.85 s (everything, the voice too) | |
| a guitar line's notes | 0.75 s | |
| a drum line's hits | 0.76 s | |
| one melody note | 1.43 s | |

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
section's voice again, whole: exact, and the dearest edit (about 0.8 s of the 1.4 s above). It is not traded for
speed.

## Immediate feedback

An edit sounds at once through the sketch's voice: a melody note moved or drawn (as it did), an instrument's
notes added or moved, a drum hit set. This plays over the loop; it no longer stops it. An overlay of the edited
part's whole sketch for the first time round was considered and left out: at native speed the real audio is
there within the bar or two the overlay would cover, and an overlay out of tune with the real part (the
sketch's voicing isn't the band's) is more confusing than a short wait.

## A single note with the instrument's own sound

`/api/note` (`Studio.note`): one note of a player, as its maker makes it (`instruments.render_part`, the
version's band settings and the player's sound), dry, levelled to the velocity's class (soft, medium, firm,
hard) and kept as a preview file. A note of H's band takes 5 to 20 ms to make (90 ms the very first, compiling);
the page waits for the request and the decode, not the sound. The page (live.js, `Samples`) keeps decoded notes
in an LRU of 24 MB; a key with no sample yet sounds the sketch's tone at once and asks for the sample, so the
next press is the instrument. When the roll opens, the octave around its notes is fetched. Keys hash the
program, the player, its band settings and sound, the seed, the pitch, the velocity class, the drum piece.

## Where it runs on its own

`mayRenderAhead(where)` (live.js) answers one question: may the page start a render nobody pressed for?

- a studio on this computer (`songbird studio`): yes, and the single notes;
- on the device (the web build): no (a section takes many seconds there and holds hundreds of megabytes);
- a shared or public studio: no (its renders are counted and queued for everyone).

Where it doesn't, the sketch options (▾ by Sketch and Sung) have **Keep the sung loop up to date**: on, an edit
makes the looped section again as it would on this computer, through the same queue and limits; off, the loop
says **earlier version** after an edit and ▶ makes it again. Single notes are always the sketch's tone there.

## Measured after

(Filled in after the work: the table above, warm and cold, with the narrower keys.)
