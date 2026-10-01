# Singing in the web studio (2026-09-29)

The studio's *Sing it* works on the web: a visitor sings along to the guide
on the studio's own page, the take is measured on the server and its audio
deleted there (since 2026-09-30 it can be measured on the visitor's own
device instead, so it never leaves it: "On the device" below), and the
song is sung their way: by the machine's voice, with
their timing, holds, loudness and pitch gestures, never their voice. They can
hear it and record a rendition that carries it. This is the web studio's
singing (docs/WEB-STUDIO.md has the public studio it runs in); the karaoke on
the artist's computer (tools/karaoke.py) and the contest's online page
(docs/SING-ONLINE.md) are unchanged.

    uv run python -m webstudio.prepare                  # once, on a computer with the memory: the singing kit
    uv run songbird studio --public --web-singing       # or without --public, on this computer only

`--web-singing` needs a checkout (tools/, webstudio/), the `web-singing`
dependency group (pyworld, librosa: `uv sync --group web-singing`; the dev
group has them too) and the singing kit (`--sing-kit DIR`, else
$SONGBIRD_SING_KIT, else `renders/sing-kit`). Without any of them the studio
runs as before; with a kit missing or made for another version of the song
or of the measuring code, the singing card says so and the rest works.

Nothing of this is in the song's program: `webstudio/` sits beside
`songbird/`, a packet carries `songbird/` alone, and the studio imports it
only when `--web-singing` asks.

## The flow

```mermaid
flowchart LR
  C[Consent: what is kept, and what isn't] --> S[Sing: a section or the whole song, to the melody guide]
  S --> L[Listen back, slide the timing]
  L --> M[Measure it: the take sent, queued, measured, deleted]
  M --> Y[Your way: a few sentences on how you sang; the singer's card sings it your way]
  Y --> H[Hear the song your way] --> R[Record it: the rendition carries your numbers]
  Y --> S
  Y --> F[Forget my singing]
```

- **Consent first.** The first press of *Sing it here* shows what happens to
  the singing, and nothing records until the visitor ticks "I understand"
  (the page remembers the consent's version in its browser, and asks again
  if the words change):
  - *Your singing never leaves this device.* Measured on the device ("On
    the device" below), the take is recorded in the browser only while they
    sing, measured there in the page's memory and let go: never sent, saved,
    played to anyone or used to copy a voice. Where the studio measures on
    its server instead (the page as it is until it is wired to measure on
    the device), the words are the server's: *Your voice is not kept.* A
    take sent to be measured goes to the computer serving the studio, which
    measures it and deletes the recording straight away.
  - *What's kept is numbers*, for each note: how early or late, how long
    held, how loud, how they slid into it and off it. In their browser, and
    on the server under a code (no name, no address) for 30 days after last
    use, so the studio can sing it.
  - *Nothing is published unless they record.* A recording carries the
    numbers (rounded), as every rendition carries its singer's way.
  - *They can take it back.* Forget my singing removes the numbers from the
    browser and the server (not from a recording already made).
- **Singing** reuses the karaoke's own code, served from tools/ as it is
  (tools/karaoke.js and tools/karaoke-recorder.js; webstudio/sing.js imports
  them): the take is recorded in the guide's audio clock by the same
  worklet, cut from the same frame, auto-synced by the same pitch slide and
  written as the same 16-bit WAV, so it is measured exactly as a karaoke or
  online take is. The lane of notes and the words as they're sung are the
  karaoke's; a section or the whole song; a key from the kit (the song's
  own, and two steps either way by default; the kit's `--keys`); a device
  delay learned from each take's sync.
- **Measure it** sends the take (a small JSON of where it was sung, then the
  WAV, in one request) with the numbers of the takes measured before it,
  which the browser keeps. It waits in the studio's one queue, with the
  renders (below), and the page says how many are ahead and about how long.
  Its result is the new take's numbers and a way of singing made from all
  of them (each person counts once: tools/phrasing.py `singer_phrasing`),
  and a portrait ("You sit 12 ms behind the beat on average… You slide into
  26 of 44 notes…"). The page sets the singer's card to *your way* and
  offers *Hear the song your way* and *Record it your way*. Each further
  take joins the way (up to 12).

## What is kept, where, and for how long

| Where | What | How long |
|---|---|---|
| The visitor's browser (localStorage `songbird-web-singing`) | the consent's version, the key chosen, the device's delay, each take's measured numbers (about 40 kB for a whole take), the way made from them | until they forget it or clear the browser |
| The page's memory | the take's audio, between Stop and Measure it (listen back, slide) | until it is measured (on the device) or sent (to a server), sung again, or the page closes |
| The page's measuring (on the device) | the take decoded in the measuring worker's memory; each piece it reads as a temporary WAV in Pyodide's in-memory /tmp (never storage); WORLD's own memory for its analysis | each piece removed as soon as it has been read, any left by a fault swept before measuring returns; WORLD's memory let go with the take; the rest freed when measuring returns (its bytes reused, gone when the worker ends) |
| The server's memory (measuring on the server only) | the take's audio while it waits for the measuring process | until it's measured (at most 3 wait at once; a cancelled one is let go with it) |
| The measuring process (on the server only) | the take decoded in memory; each piece it reads in a temporary WAV (0600) in /dev/shm (memory) or /tmp | removed as soon as it has been read, whatever happens; leftovers from a killed process swept at its next start |
| The server's disk (`$SONGBIRD_HOME/studio/sung/sung-<16 hex>.json`) | the way of singing: rounded, bounded gestures by phrase and note, "1 sung take(s)"; named by its fingerprint | 30 days after it was last used, or until forgotten |
| A recording the visitor makes | the way's rounded gestures, in the record's `performance` (as any rendition's), marked "a person's way" | the file's; a public studio keeps it for download a day |

No name, address, cookie or anything about who sang is kept with any of it;
the job's result (numbers) lives in the queue's memory with the job, as a
preview's does. The server never lists the ways it keeps: a page names its
own, and only a page that made one knows its name. The access log records
`POST /api/sing/take 200` like any request, never who.

## Measuring on a server

webstudio/worker.py measures a take with tools/phrasing.py's own functions,
in a process of its own (`python -m webstudio.worker KIT`), started when a
take needs it. Two differences from the artist's computer, both for a
server:

- **No forced aligner.** MFA isn't in the container, so each vowel's start
  is found where its loudness climbs out of the consonant before it, as it
  was before MFA. **No speech recogniser either:** faster-whisper reads
  plain spoken readings (tools/phrasing.py `--speech`), never sung takes,
  so no model is chosen or loaded. (It is imported at the top of
  tools/phrasing.py; the worker puts a stand-in that refuses to work in its
  place, which saves 30 MB and four seconds, and lets the image go without
  it.) For the record, faster-whisper `base.en` int8 on this Mac: 62 MB to
  import, 395 MB loaded, 518 MB transcribing 30 s.
- **Long takes in pieces.** WORLD's pitch tracker (pyworld `harvest`) holds
  about 14 to 19 MB for every second it analyses at once, so a whole take
  (four minutes at 90%) is 3.4 GB in one piece. A take longer than 40 s is
  cut in the middle of every rest of 3 s or more between notes (the turns
  between sections; any piece still over 40 s at its longest rest), each
  piece measured from 2 s before its first note to 1 s after its end as
  tools/phrasing.py measures a take of one section (`measure_window`). A
  take of one section (31 s at 90%) is measured whole, exactly as there.

The template singer's analysis of each guide (what a take is compared
with) takes 4 GB and a minute to make, so the kit carries it, made ahead.

### The kit

`python -m webstudio.prepare [--keys -4 -2 0 2 4] [--tempos 90] [--octaves -12 0 12] [--kit DIR]`
writes, for each version offered (the first recording set, each key and
speed): its score, the melody guide (the karaoke's default mix: the tune on
a whistle over a pulse, rendered from the score alone, mono at 22.05 kHz:
6 MB of FLAC for the whole song), its words, and the template singer's
analysis in the guide's key and an octave either side. Each template is
made in a process of its own (4 GB, about a minute on an M-series Mac); the
default five keys are 15 templates, about 15 minutes; the kit is about
45 MB. Nobody's voice is in it: the guides are the song's, the templates the
machine's.

The templates are kept under the measuring code's version
(tools/phrasing.py `version()`, which hashes the singer's code), so the kit
must be made by the program the server runs; the studio checks at start
and says "the singing kit was made by another version of the measuring
code" rather than refusing every take. A take sung more than a few
semitones off the guide's key or its octaves has no template, and is
refused with what to do: "choose the key nearest your voice and sing it
again".

### How the numbers compare

- **The same as the tools.** A take of one section is measured with exactly
  the numbers tools/phrasing.py `measure_window` gives the same file without
  MFA (tests/test_web_singing.py: every note, the lag and the key).
- **A planted way is heard.** The template singer singing the first verse
  with every second note 60 ms late: those notes measure later than the
  rest by 0.14 beats against the 0.086 planted (the neighbours' onsets move
  too; the test asks for at least half).
- **Pieces against a whole take.** The machine's own singer (the spec's
  voice mix, 244 s) measured whole and in the nine pieces the worker cuts:
  every vowel start within 20 ms (all but a handful within 10 ms), timing
  and holds equal for 98% of notes, pitch gestures within a fraction of a
  cent; loudness and swell differ by about 0.9 dB (median), because each is
  read against the same vowel elsewhere in the piece rather than in the
  whole take, as for any take of one section.
- **Without MFA, against the measurements kept with it** (volunteers' takes,
  read in place from the main checkout for this comparison only, their
  audio never copied; each note's vowel start and gestures against the
  cached MFA-led measurement): see the table below. This is the accuracy
  cost of no aligner: docs/PHRASING-CALIBRATION.md measured it on planted
  takes (78% of vowel starts within 30 ms without MFA, 96% with it) and on
  windows (16 to 46% within 10 ms of the whole take's without MFA).

| take (singer, what) | notes | vowel starts the kept measurement took from MFA | within 30 ms | within 60 ms | median | r timing | r hold | r level | r scoop |
|---|---|---|---|---|---|---|---|---|---|
| A, verse 1 | 44 | 40 | 55% | 73% | 20 ms | 0.62 | 0.76 | 0.90 | 0.81 |
| A, refrain 1 | 40 | 40 | 70% | 93% | 20 ms | 0.85 | 0.82 | 0.99 | 0.70 |
| B, verse 1 | 44 | 4 | 95% | 95% | 0 ms | | 0.99 | 1.00 | 1.00 |
| B, refrain 1 | 40 | 6 | 97% | 97% | 0 ms | 1.00 | 1.00 | 0.99 | 0.95 |
| C, verse 1 | 44 | 38 | 70% | 73% | 15 ms | 0.97 | 0.99 | 0.87 | 0.90 |
| C, refrain 1 | 40 | 16 | 88% | 95% | 0 ms | | | 0.98 | 0.95 |
| D, verse 1 | 44 | 38 | 39% | 43% | 108 ms | 0.81 | 0.45 | 0.65 | 0.94 |
| D, the whole song (in 9 pieces) | 347 | 177 | 44% | 48% | 115 ms | 0.23 | 0.23 | 0.61 | 0.51 |

(Blank: too few notes timed in both to say.) Where MFA had given up on a
take (B), the two agree almost exactly, as they should: the same code. Where
it led, the web studio's vowel starts sit within 30 ms of it for 55 to 88%
of notes, and its timing follows MFA's note by note (r 0.62 to 0.97) for
three singers of four. The fourth (D) sits about 110 ms from MFA throughout,
a constant offset in a section (r 0.81) that doesn't survive a whole take cut
in pieces (r 0.23): a voice whose consonants the loudness-based starts read
very differently from MFA. Level and scoop hold up better than timing
(r 0.5 to 1.0). So a web visitor's way is a fair sketch of their phrasing,
pitch and dynamics more than timing, and weaker than what the artist's
computer measures; decision 2 below.

### Memory and time

On this Mac (M-series), one process measuring, the kit's templates ready:

| | measuring | the whole request, cold | peak memory of the measuring process |
|---|---|---|---|
| a section (31 s) | 4.5 s | 6.6 s (the process starting: about 2 s) | 610 to 870 MB |
| the whole song (244 s, in 9 pieces) | 29 s | 31.6 s | 880 MB |
| the process idle (imports, a guide) | | | 270 MB |

A slower server core will take perhaps twice as long. The studio's own
process doesn't load the measuring tools at all. The container's cap
(2.5 GB, a render up to 1.5 GB) holds because a measurement is a job in
the studio's one queue (`studio.jobs`, kind `measure`): a render and a
measurement never run at once. In a public studio the measuring process is
stopped after every take (its memory given back before the next render); on
one's own computer it waits five idle minutes for the next take.

## On the device (2026-09-30)

A take can be measured in the visitor's own browser, so the singing never
leaves their device: the same code as the server's measuring process, in
Pyodide beside the program the browser already renders with
(docs/BROWSER-RENDER.md). The page's side (calling it from the studio's
browser worker) is being wired separately; this is what it calls.

### The design

- **The same code.** `web/studio-wasm/py/sing_measure.py` runs
  webstudio/worker.py's own `take` (its pieces, tools/phrasing.py's
  `measure_window` and `singer_phrasing`), unchanged, with three modules
  stood in for in `sys.modules`, in the browser only: **pyworld** by
  WORLD in wasm (`py/world_wasm.py`), **librosa** by its DTW in numpy
  (`py/sing_dtw.py`), **faster_whisper** by worker.py's stub that refuses.
  MFA is off, as on the server. worker.py itself changed in one line: it
  imports `resource` (which Pyodide hasn't) only where it reads it.
- **WORLD in wasm** (`web/studio-wasm/world/`): the measuring calls
  `harvest(x, 44100, f0_floor=60, f0_ceil=900, frame_period=5)` and
  `cheaptrick(x, f0, t, 44100)` with its defaults (q1 -0.15, an FFT of
  2048), nothing else (tests/test_world_wasm.py checks that). pyworld
  0.3.5's own WORLD sources (`src/`, BSD, its licence beside them and in
  the bundle) are compiled with zig 0.16's clang for wasm32-wasi
  (`build.sh`), with a glue (`glue.cpp`) that runs CheapTrick a chunk of
  frames at a time, carrying its noise generator from chunk to chunk, so
  the spectrogram is never whole in WORLD's memory. Two things hold its
  memory down, neither changing a number:
  - **An allocator of its own** (`alloc.h`). zig's libc allocates in wasm
    with `std.heap.WasmAllocator`, which never splits a freed block for a
    smaller request: Harvest frees a few 12 MB buffers and then makes tens
    of thousands of 1 kB rows, so the memory grew to 2.5 times what WORLD
    held (485 MB for 206 MB on 35 s of singing).
  - **A lean Harvest** (`harvest_lean.cpp`, built in `src/harvest.cpp`'s
    place, each change marked). Its FixStep3 gave every voiced section (at
    its 1 ms frames, 500 of them in 35 s) a channel as long as the whole
    contour, which grows as the square of the length (140 MB at 35 s);
    now each channel holds only the 101 frames either side of its section
    where anything can be written, and reads as zero beyond, as before.
    SmoothF0Contour filters one channel at a time, and the candidates'
    scores are made once the raw candidates are gone. On 23 signals (the
    artist's takes in 35 s pieces and sections, the machine singer's) its
    f0 is bit for bit the unmodified build's.

  The module (83 kB, 37 kB sent) has its own memory, not Pyodide's: one
  instance per take, its pieces reusing the same memory, let go when the
  take is measured. It is committed with the digests of what it was built
  from (`world/sources.json`, `tools/world_sources.py`), so the bundle
  builds without zig and a source changed without a rebuild is caught.
- **librosa's DTW in numpy** (`py/sing_dtw.py`): exactly the call
  align_by_pitch makes (a cost matrix, `subseq=True`, steps (1,1) (1,2)
  (2,1), no weights), a row at a time since every step advances the row,
  with librosa's first-strict-minimum rule, its default steps of infinite
  weight, its swapped path columns when the cost has more rows than
  columns (a take cut at its edge) and its refusals. Natively
  tools/phrasing.py keeps librosa (decision 2 below).
- **The bundle**: `web/studio-wasm/tools/build_render.py` adds, in a block
  of its own (`tools/sing_bundle.py`), `singing.zip` (79 kB: tools/phrasing.py
  and the six tools modules it imports, webstudio's worker.py and kit.py,
  the three Python files above; unpacked into `/app` beside the program,
  byte for byte, since `version()` hashes their source) and `world/`
  (world.wasm, its loader world.mjs, WORLD's licence) in the app folder.

### How to call it

In the studio's browser worker, once Pyodide, numpy, scipy and soundfile
and the program are loaded (as `studio-worker.mjs` does):

```js
const { loadWorld } = await import(`${app}world/world.mjs`);
py.registerJsModule('songbird_world', await loadWorld(await (await fetch(`${app}world/world.wasm`)).arrayBuffer()));
py.unpackArchive(new Uint8Array(await (await fetch(`${app}singing.zip`)).arrayBuffer()), 'zip', { extractDir: '/app' });
const measure = py.pyimport('sing_measure');
// the kit's files the take needs, written under /kit (kit_files names them; the server serves the kit)
for (const name of measure.kit_files(py.toPy(offer), guide, py.toPy(earlier)).toJs()) {
  py.FS.mkdirTree(`/kit/${name.split('/').slice(0, -1).join('/')}`);
  py.FS.writeFile(`/kit/${name}`, new Uint8Array(await (await fetch(`${kitURL}${name}`)).arrayBuffer()));
}
const answer = JSON.parse(measure.answer_json(takeWavBytes, py.toPy({
  song, guide, from_s, to_s, earlier, offered, kit: '/kit' })));
// { ok: { measurement, phrasing, portrait, skipped, audio_seconds, seconds, peak_mb } }
// | { refused: "what the singer can do" } | { error: "what went wrong" }
```

`measure(take, request)` is the same returning the result and raising
`Refused` (worker.py's) for what the singer can act on. The request is the
server's (`webstudio/singing.py` `where()`: song, guide, from_s, to_s,
earlier, offered) plus `kit`; the checks `where()` makes before a take is
queued (the version offered, the guide unchanged, the length) are the
caller's. The kit must be one made by this measuring code: its templates
are named by tools/phrasing.py `version()`, and a kit of another version
is said as such. Per take it needs offer.json, the song, each guide's
score sung to (0.2 to 0.5 MB) and the guide's three templates (about
0.4 MB each for a 151 s guide). One take at a time; nothing is uploaded.

### How it agrees with native

On the artist's own three takes (recordings/milo/: each whole, 151 s, cut
in pieces as the server cuts it; and two sections cut from each as the
page cuts one, 28 to 98 s) and the machine singer's (a section and the
whole song, every third note planted 50 ms late, at 48 kHz as a browser
records), against webstudio/worker.py natively on this Mac with the same
kit: **every case identical, byte for byte**: each note's onset, offset
and gestures, the lag, key and pieces, the stamp, the phrasing made and
its portrait (11 takes, 1,030 notes measured). Underneath:

- **WORLD**: on twelve 35 s pieces of the artist's takes, Harvest's f0 is
  native pyworld's to within 9e-15 (relative; a few bits in the last
  place: the Mac's build fuses multiply-adds, wasm doesn't, and their maths
  libraries differ at the last bit), voiced on exactly the same frames;
  CheapTrick's spectrogram within 2e-9 relative, the loudness
  tools/phrasing.py reads from it within 1e-12 dB and its activity the
  same. tests/test_world_wasm.py holds a sung signal to that.
- **DTW**: bit for bit librosa's (costs and path) on 160 random cost
  matrices with ties and every shape, on align_by_pitch's own costs from
  made-up lines sung late, flat, an octave down and cut short
  (tests/test_sing_dtw.py), and on every one of the 180 alignments (160
  million cells) the eleven takes above made.
- **The rest** (numpy 2.4.6 and scipy 1.18.0 in Pyodide, 2.5.3 and 1.18.1
  here): resampling a 48 kHz take to 44.1 kHz differs by at most 7e-16 (half
  the samples identical); everything after it gives the same numbers.

Bit-identical isn't promised for every take: a few bits of f0 sit on
either side of a threshold one day (a voicing decision, a rounding to the
nearest frame), and a vowel's start moves a frame (5 ms). The server
(Linux, no fused multiply-adds, another maths library) differs from this
Mac by as much.

### Memory and time

Under node (Pyodide 314.0.7), each in a fresh worker, this Mac:

| | measuring (native) | measuring in Pyodide | Pyodide's heap at most | WORLD's memory at most | together |
|---|---|---|---|---|---|
| a section (28 to 33 s) | 3.2 to 5.4 s | 5.0 to 6.3 s | 269 to 279 MiB | 99 to 112 MiB | 367 to 391 MiB |
| a long section (98 s, in pieces) | 12 to 14 s | 18 to 19 s | | | |
| the whole song (151 s, in pieces) | 18 to 21 s | 28 to 34 s | 322 MiB | 114 to 151 MiB | 436 to 473 MiB |

(Times measured with the machine otherwise quiet; under a heavy load they
were three to five times longer. Loading Pyodide and the program, about
2 to 5 s, comes before, once per worker.) Pyodide's heap is 75 MiB loaded,
130 MiB once the measuring code is imported; the rest is the take, its
piece's spectrogram (CheapTrick's, 1.6 MB a second, which
tools/phrasing.py reads whole) and the measuring. WORLD's memory follows
the longest piece (Harvest holds about 3.3 MB a second analysed: 117 MiB
for 35 s); a take is measured in pieces of at most about 43 s (40 s and
its lead and tail), so a whole song needs no more than a long section. It
is given back when the take is measured; Pyodide's heap only grows, so it
is given back when the worker ends.

### Privacy

Nothing is uploaded: the take goes from the recorder to the measuring
worker in memory, and only numbers come back to the page. Each piece's WAV
lives in Pyodide's in-memory file system for as long as it is read, and
any left by a fault is swept before `measure` returns; the take's bytes,
once freed, are memory the worker reuses, gone when it ends. Nothing of it
reaches the Cache API, IndexedDB or localStorage (the kit's files may: they
are the song's and the machine's).

### Open decisions

1. **No server fallback for measuring.** If measuring on the device fails
   (an old phone out of memory), sending the take to the server instead
   would break "Your singing never leaves this device". Suggested: say so
   on the page ("This device couldn't measure your take") and keep the
   server out of it; the artist chose not to gate phones.
2. **librosa natively, or the numpy DTW everywhere.** The port is bit for
   bit librosa's, so tools/phrasing.py could use it and the server image
   drop librosa (and numba with it). But align_by_pitch's source is hashed
   into `version()`, which names every kept measurement in renders/measured
   and every kit template: switching re-measures every kept take (some of
   whose audio is now deleted) and remakes the kit. Suggested: switch at
   the next change that moves `version()` anyway.
3. **The consent's words on the page** (webstudio/sing.js) still describe
   the server; when the page measures on the device they become the
   simplest true statement: "Your singing never leaves this device." (and
   the hint under *Measure it*: "Measured here, on this device; the
   recording is let go once it has been.").
4. **The worker's memory on phones.** About 390 MiB for a section and 470
   MiB for the whole song at most, more if measuring shares the render
   worker after a whole-song render (Pyodide's heap is never given back
   while the worker lives). Ending the worker after measuring (as the
   renderer does after a whole song) gives everything back, the take's
   freed bytes included. The kit's templates are downloaded once per guide
   and key (about 1.2 MB for three).
5. **WORLD's sources are ours to keep.** world/src is pyworld 0.3.5's, the
   lean Harvest our change to it; a new pyworld natively (the test pins
   0.3.5) means taking its sources again, checking the f0 bit for bit
   against the unmodified build, and rebuilding with zig.

## Limits

| | | |
|---|---|---|
| a take's size | 40 MB (a whole song at 48 kHz is 23 MB) | 413 |
| its length | 3 s to 6 minutes, and no more than 10 s past what it says it sang | 400, said |
| takes waiting in memory | 3 at once | 503 "try again in a minute" |
| takes on their way | 2 at once, one from each address (each is read into memory) | 503 "send yours again in a moment" |
| a public visitor | one thing in the queue at a time (a take or a render); `--limit takes=12` an hour, `takes-ip=30` for an address | 429 with Retry-After, as for renders |
| a way of singing | 12 takes; 256 kB; only this song's phrases, every gesture rounded and bounded | 400, said |
| kept ways | 30 days after last use | |

The take is guarded as the studio's own requests are: its address (Host,
Origin), a shared studio's key, the page's token, a content type of its own
(`application/x-songbird-take`), and a public studio's requests-a-minute.
Since 2026-09-30 every one of them, and singing's own (on, the visitor's
turn and takes this hour, room among the takes waiting, and the takes on
their way), is asked before a byte of the take is read; a refused take is
read and dropped a block at a time, nothing of it held (docs/WEB-STUDIO.md,
"Before launch").

## In the code

- `webstudio/`: `kit.py` (where the kit's files are; standard library
  only), `prepare.py`, `worker.py` (the measuring process), `singing.py`
  (the studio's side: routes, the waiting takes, the Measurer, the Store of
  ways by fingerprint), `sing.js` and `sing.css` (the page's side).
- `songbird/studio.py`: `--web-singing`, `--sing-kit`;
  `Studio.enable_web_singing`, `phrasing_choices` (a name `sung-…` is looked
  up in the Store, never listed), `sung_phrasings` (the card's "your way");
  the handler asks singing first about its routes and the take's upload,
  and the page gets `/sing.js` and `/sing.css` added. `songbird/public.py`:
  the `takes` limits. `songbird/explain.py`: a phrasing may say its own way
  ("sung your way"). `songbird/studio/studio.js`: the ways a browser made are
  offered on the singer's card beside the studio's (`phrasingChoices`), and
  its last section hands webstudio/sing.js a few of the page's functions
  (`window.songbirdStudio`).
- `tools/phrasing.py`: `sung_phrasing`/`singer_phrasing` take measurements
  already made (`measurements=`), for takes that were never files.
- `deploy/studio/`: the image installs the `web-singing` group (a compiler
  lent to build pyworld), copies tools/ and webstudio/; the compose file
  mounts the kit read-only at /kit and passes `--web-singing --sing-kit /kit`
  (`STUDIO_SINGING`, `SING_KIT`).
- On the device (2026-09-30), in `web/studio-wasm/`: `py/sing_measure.py`
  (`measure`, `answer`, `kit_files`), `py/world_wasm.py` (pyworld's
  harvest and cheaptrick over world.wasm), `py/sing_dtw.py` (librosa's DTW),
  `world/` (WORLD's sources, the glue, the allocator, the lean Harvest,
  `build.sh`, the committed world.wasm and `sources.json`),
  `tools/sing_bundle.py` and `tools/world_sources.py`, the block in
  `tools/build_render.py`, and `node/sing_run.mjs` (a Python file run in
  that Pyodide under node). Checked by tests/test_sing_measure.py (the
  planted verse measured in Pyodide as the server measures it, where Pyodide
  is installed), tests/test_world_wasm.py and tests/test_sing_dtw.py.

## Decisions for the artist

1. **Web visitors' numbers stay theirs.** Nothing sung in the web studio
   joins everyone's way or the lineage choir: the numbers live in the
   visitor's browser and, for 30 days, under a code on the server, to sing
   their own version. Gathering them into the song (with an opt-in and its
   own consent, as the contest's volunteers gave) is a separate decision.
2. **No aligner on the server.** Vowel starts without MFA are good but
   plainly less exact (the table above). MFA in the container is possible
   (a conda environment of about 1.5 GB on disk; about 20 s and more memory
   per section) but heavy; the alternative is to accept this as a web
   visitor's way, a sketch of their phrasing.
3. **30 days** for a way kept on the server after its last use (so the
   studio can sing it on a later visit). Shorter is more private; the
   browser can always give it back while it has it.
4. **A recording carries the numbers.** As every rendition does now
   (`performance` in its record). The consent says so; the alternative
   would be a web recording that can't be replayed elsewhere.
5. **Keys offered**: the song's own and two and four steps either way at
   90% (the kit's defaults); each key is a guide (6 MB) and three templates.
6. **The melody guide only.** The band's guide ("the whole song") would need
   a full render per key (6.7 GB peak on this Mac) and 20 MB downloads; the
   karaoke's default was the melody anyway.
7. **A take is one of a public visitor's turns.** Twelve an hour by
   default, one thing in the queue at a time, like a section.

## How it was checked

- tests/test_web_singing.py: without `--web-singing` nothing of it is
  served; the page gets the singing and the karaoke's own files; a kit for
  another song is said, not used; a take is refused for a wrong token, type,
  address, guide, version, length or body, and too big before its body is
  read, with nothing reaching the measuring process; a take waits in the
  queue, is measured, and no audio is held or written anywhere after; a
  refusal is said to the singer; the queue refuses a flood; a public
  studio counts takes against each visitor and holds them to one at a time;
  the song is sung "your way" by a name that is never listed, marked "a
  person's way", never whose; a way kept is rounded, bounded, stable,
  forgettable and expires; a long take is cut in its rests; and the real
  measuring process on a planted take gives tools/phrasing.py's own numbers,
  hears the planted notes late, and leaves no piece behind.
- By hand, in the built-in browser (a public studio with `--web-singing`
  and a three-key kit): the consent, the stage (lane, words, count-in,
  progress) rehearsing a verse to the guide, laptop and phone widths with
  no sideways scroll; a whole synthesized take sent as the page sends it
  (the browser pane has no microphone), measured in 31.6 s; the singer's
  card saying "sung your way"; the whole song rendered that way; Forget my
  singing removing it from the browser and the server; no measuring process
  left running and no piece of a take left in the temporary folder.
