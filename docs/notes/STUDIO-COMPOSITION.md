# Composing beyond the seed

The studio should treat generated music as editable material. The song's
rules are good defaults for a new generation; deliberate writing should not
have to obey its original melodic or narrative ambitions. Keep the portable
program, deterministic replay, private local operation, provenance and
inheritance. Preserve old records without migrating or reinterpreting them.

## Implemented

- New melody and chord edits default to this place. Editing every repeat is
  an explicit choice; existing edits retain their scope.
- Draw and delete melody notes, with gaps as rests. Write words first and fit
  a new rhythm to them, or draw notes first and write their words. Words and
  notes apply together through the existing own-line format.
- Transpose the entire phrase, rewrite its ending, use wide leaps and a wider
  register, and add chromatic syllables. Generation retains its own rules.
- Edit pitched instrumental parts directly: generated notes become editable
  MIDI-like notes with duration, velocity, chords and rests. Reset restores
  the procedural part. This uses the same parts that keyboard and MIDI import
  already write and the renderer, MIDI export and descendants already read.
- Copy notes, complete phrases, or section contents. A phrase copy includes
  words, tune, harmony and custom instrument notes. A section copy includes
  player patterns and levels too. Destinations retain their timing structure;
  a checked paste applies atomically with one undo step.
- Keep the existing score, transport, arrangement, inspector and mix. A Part
  selector reuses the lower editor; instrumental cells open it directly.
  Extra phrase and section actions sit in disclosures instead of new views.

All these changes use existing edit paths and stored representations. Old
songs still generate and replay as before. The exported FLAC still carries
its complete program. There are no imported samples, hosted services,
plugins, new dependencies or mandatory projects beside the song file.

The bounds that remain are concrete engine contracts: finite numbers,
monophonic vocal timing, pronounceable syllables, bounded note counts and
instrument polyphony, and the phrase clock. They prevent ambiguous rendering
or unbounded work. A melisma still uses scale degrees in its existing compact
representation. Drum strokes are not pitched parts.

A rewritten lyric line still belongs to its verse or refrain identity. Its
words and melody follow that identity wherever it occurs, as existing
own-line records do. The editor states this scope; independent copies of the
same lyric identity need the clip model below.

## Web and standalone parity

Every composition feature belongs in both studios. The Python studio serves
the editor from `songbird/studio/`; the static web build copies those same
files from `studio.STATIC`. Its device worker delegates editing requests to
the same `studio.answer` implementation. The instrument roll uses the shared
`/api/players` and `/api/notes-in` routes, and checked lyric and clipboard edits
use `/api/song`. No composition rule belongs exclusively in the web shim.

The packet carries the same editor assets and Python program, so a newly
exported standalone file includes these features. Previously exported files
keep the program they carried; updating the website does not rewrite them.

`tests/test_studio_device.py` compares rewritten lyrics, wide chromatic
melodies, instrumental chords and rests, note import, MIDI bytes and render
specifications between the device adapter and native studio. It also checks
the shared editor assets. `tests/test_pack.py` checks those assets inside an
actual standalone packet. For runtime verification, build the static site,
exercise its editing flow in a browser, then render an edited section's spec
with `web/studio-wasm/node/spec_run.mjs` and compare it with the native render
using `web/studio-wasm/tools/pcm_diff.py`. Native adapter tests alone do not
exercise Pyodide or its browser fetch shim.

## The structural boundary

The timeline still lays out the song's section templates. A verse is not an
independent clip: its words are keyed by the bank's verse identity; its tune
and chords may be shared; parts and transitions use occurrence positions;
phrasing gestures use note indices. The bank also requires a valid narrative
form when it fills procedural lyrics. Removing only a drag refusal or form
validator would silently move some of those things while leaving others
behind. Copying contents is a safe way to reuse or replace material now.

The next architectural change should be independent clips, with stable IDs
separate from names such as Verse and Refrain. This is the path to arbitrary
section ordering, duplication, deletion, blank sections and changing line
counts and lengths. It should be additive:

1. Keep the inherited song and its generated form as the source. An old
   record without a clip arrangement takes the existing code path unchanged.
2. Give an authored clip a stable ID, a source reference, its own musical
   length, and optional words, notes, harmony and part overrides. Changing its
   label or order must never change its identity.
3. Store an explicit ordered list of clip instances. Duplication creates a
   new instance; linked repetition is a separate action. A deliberate
   arrangement can omit any original section, including the final refrain.
4. Resolve clips once into a shared musical timeline used by the singer,
   band, choir, MIDI, preview, mix and export. Neither the UI nor a late audio
   splice should have a competing interpretation of the arrangement.
5. Keep origin and authored overrides separate. Regenerate can replace an
   unedited layer; reset removes the authored layer; a blank clip need not
   invent a bank identity. Machine and time can still shape the instruments
   and delivery of a completely rewritten song.
6. Validate compatibility with old packets, exact replay, inheritance,
   shared-to-independent copies, moved words and transitions, variable
   lengths, missing sources and bounded rendering. Only then expose the
   familiar New / Duplicate / Delete / Split clip commands.

After that, per-track clips, multiselection, quantization and automation
lanes can build on one model. Sample recording and third-party plugin hosting
would introduce a different portability problem and are not needed to let
someone write an entirely different song with Songbird's instruments.

The useful identity is the song's ancestry and its ability to keep travelling,
not a requirement that every intentional descendant retain its refrain or
melodic shape.
