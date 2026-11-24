# The video's data

Everything in `renders/promo/video/data/`, written by the scripts in this folder. Run each from the repo root
with `uv run python tools/promo/video/prep/<script>.py`. Every path a script reads or writes goes through
`common.guard()`, which refuses anything under `renders/measured/`.

## Part names (the stems)

24 parts, in the order `synth.stem_jobs` makes them for this score (the order `--stems` writes them;
`timeline.json` and `score.json` carry the same list as `"stems"`):

```
lute guitar harp bass fiddle whistle drum drone          the score's players
voice choir1 choir2 choir3                               the lead (spliced from its takes) and the choir
arp synthpad drummachine synthbass                       the synthfolk layer's parts (stage plan "layers")
whistle~ harp~ bass~ guitar~ drum~ fiddle~               synth twins: a synth on the player's own notes
harp# drummachine#                                       chip twins: harp's notes on the chip, the layer's
                                                         drum machine on the chip's drums
```

The twin pairs (name: player, instrument), from the record's `params.composition.exact.twins`:
`whistle~` whistle/synthlead, `harp~` harp/arp, `bass~` bass/synthbass, `guitar~` guitar/arp,
`drum~` drum/drummachine, `fiddle~` fiddle/synthlead, `harp#` harp/chip, `drummachine#` drummachine/chip-drums.

## Where everything comes from

The song is `performance/genome.json` replayed with `performance/record-arc-morph.json`, laid out as a render
lays it (`common.laid()`: `stage.laid` with the record's params, singer, mix, lyrics and inherited phrasing, the
same steps as `tools/performance/wire.py`). Its `to_dict()` equals `renders/promo/capture/render.score.json`
note for note (2,042 notes); the stage plan (`Score.stage`, left out of score files) is read from that object.

Arrays are `<name>.bin` + `<name>.json` as the README says (`common.write_array`): little-endian, C order; a
stored value v means `v * scale + offset`; `rate` frames a second from `t0`. Extra keys in the `.json` say more.

## timeline.json (timeline.py)

The README's schema, plus `"stems"` (the 24 names above). Where each field comes from:

- `sections`: `Score.sections` (identical to render.score.json's), ids by order; `ring` 146.5875 to 151.227
  (the release file's length, checked against the FLAC by verify.py).
- `bars`, `beats`: `realize.timeline(genome, params).beats()`, the clock the notes were placed on (`bar`
  true starts a bar). 59 bar lines, 0.9125 to 146.5875, 2.5 s apart until the tag; the tag's ritardando
  (`params.ritardando` 0.27) makes its two bars 2.66875 and 3.00625 s. 234 beats from 0.2875.
- `lines`: the lead **as heard**: in each span of the stage plan (`Score.stage["plan"]`), the notes of the take
  sung there (`stage.spliced` joins the takes' audio at the same times). A line's `t0` is its first note less
  `stage.SPLICE` (0.03 s: `stage.line_starts`, where a take comes in); `t1` its last note's end. Word text is
  `pack.words_as_sung`'s rule (the bank's hyphens and `*` marks dropped), so the lines equal render.txt's.
  Syllables: each note's syllable, time and MIDI pitch. `focus`: the word is starred in the genome's lyric
  (`*num-bers*`); every syllable of a starred word is marked.
- `human`: the take's amount at each change, `[t, h]`, t the line start where the plan switches take
  (0 at 0; 0.2 at 25.588; 0.3 30.597; 0.4 35.614; 0.5 40.618; 0.6 75.624; 0.7 100.933; 0.75 120.614). Verse 2 keeps
  0.5 and the tag 0.75, so they add no step. Per line it is the line's `human`.
- `entries`: each stem's first note whose part's level is above silence anywhere over the note (`a > 0` in
  score.json). Kinds: player, voice, choir, twin (`~` or `#`), layer.
- `levels`: `Score.stage["levels"]` (record `params.composition.exact.levels` resolved by `stage.points` to
  seconds; a second point at the same place comes `stage.EDGE` 0.12 s later). dB, null silent. The engine
  (`stage.curve`) interpolates **linear gain** (10^(dB/20), null 0) between points and holds the first and last;
  a part with no curve plays at 0 dB.
- `daisy`: the whistle's notes in the bridge, from the score; `degree` is the pitch above the tonic (59) in
  solfa: 90 so, 87 mi, 83 do, 78 so.

## score.json (timeline.py)

`{"stems": [...], "parts": {name: [note]}}`. Note: `t` start s, `d` duration s, `p` MIDI pitch, `v` velocity,
`syl`, `word` (the genome's spelling with `*` and hyphens), `sec` section id (a pickup up to a bar before its
section counts as that section), `phrase`, `art` (strum direction etc.), `g` the nine gesture numbers the note
was sung with (lead and choir), `a` the most linear gain its part's level reaches over the note (0: not heard;
1 where no curve), `h` (voice only) the take's human amount.

- Players and choir: `Score.notes` as laid (equal to render.score.json's notes by part, start and pitch).
- `voice`: the heard lead (see `lines`). Same 261 syllables and pitches as render.score.json's voice (whose
  notes are the fully phrased take's); 207 of 261 fall at that file's own times, the others are the earlier,
  less phrased takes.
- Layers (`arp synthpad drummachine synthbass`): the synthfolk layer's own score (`stage.layered`), with the
  record's copies applied (`stage.copied_all`: verse 1's bars of each part are its verse 2 bars). The stem copies
  the sound itself (`stage.jobs`), so notes ringing across the copied span's edges differ slightly.
- Twins: the player's notes (for `drummachine#`, the layer's drum machine notes with its copies), as
  `stage.jobs` hands them to `render_part`.

## text.json (text.py)

- `phrases`: the genome's `phrases` (`tune` in scale degrees as written, `,` below, `'` above; `chords`) and
  `notes`: one per note, `degree`, `at` (eighth-note units from the phrase's first bar line, a pickup negative),
  `units`. `sections`, `form.genome` (with `?` `*` marks), `form.sung` (the record's), `refrain`, `bridge`, `tag`,
  `quote` (the genome's Daisy Bell note), `meter`, `sketch`.
- `refrain.turning_word`: the bank's `question` slot (made sang heard kept wrote owns); `refrain.sung` the three
  sung "Who ..." lines.
- `bank`: every entry: kind (head, couplet, verse, bridge), id, `by`, lines, slots, era/mood/scheme/rarity where
  given; `sung_lines` the index in render.txt's lines of the first sung line each bank line matches (slots as
  any words), `sung` true where all match; `rewritten` the lines the record replaces. `sings.entries`:
  head:knows, couplet:canon, verse:wire, verse:screen, bridge:canon. `sings.rewritten`: the record's
  `params.composition.lines` (verse:screen lines 2 and 3).
- `gestures`: `record.performance.lead` and `.choir[0..2]`: `fields` in the record's order (early hold level swell
  scoop bend fall **vibrato tune**), `rows` one per note of each phrase (`phrase`, `note` index, its `degree`,
  `g` the nine numbers).
- `moved`: the eight rows of the table in docs/history/MAKING-IT-THEIR-OWN.md ("The first note shifts the song
  took"): phrase, position, `notes` (0-based in the phrase, the pickup 0), words (`focus` the italic ones), from,
  to, `tune_now` and `agrees` (the genome's tune holds the new note: true for all), singers. `count_said` 15 is
  the doc's own count for its first six rows, in sung notes; `sung_in_this_form` counts each moved phrase note's
  instances in this version's form (19 for all eight rows).
- `credits`: CREDITS.md as written: `byline`, `heading`, the six `names`, `uncredited` ("And two more who sang
  without credit."), `people` ("eight"), `record_line` (12 singers in the record).
- `counts`: each `{value, source}`: takes 79, people eight, record_singers 12, credited_names 6, choir_takes,
  verses 51, bridges 5, heads 9, couplets 8, questions, gesture_rows_lead, weights 886,372, moved_rows 8,
  moved_said 15.

## packet.json, packet-bytes, packet-text.json (packet.py)

Read from `renders/release/now-its-by-you-awards-draft.flac` itself:

- `flac.blocks`: each metadata block's type, offset (of its 4-byte header), length (of its body), `last`;
  STREAMINFO parsed (44.1 kHz, 2 channels, 16 bits, samples, md5), VORBIS_COMMENT (vendor and comments), PICTURE
  (mime, size, data length). Blocks: STREAMINFO at 4, VORBIS_COMMENT at 42, PICTURE at 256 (70,000 bytes).
- `flac.audio`: frames from 70,260 to 12,588,764 (checked: soundfile decodes bytes [0, zip) to STREAMINFO's
  sample count, 151.2271 s).
- `zip`: offset 12,588,764 (`pack.packet_start`), 4,303,253 bytes, 25.5% of the file; `entries` (name, offset of
  its local header, data_offset, compressed, size, method, crc) for all 129 (97 .py); central directory and end
  record (offsets are absolute, as pack.py writes them); totals and `by_extension`.
- `manifest`: id, generation 0, parent_id null, ancestry [], program_sha256, record_format 2, title, duration.
- `throat`: program/songbird/synth/throat.npz, 3,075,973 bytes, local header at 13,703,182.
- `packet-bytes.bin` uint8 [2, 4096]: row 0 the first audio frame's bytes (from 70,260); row 1 from 12,586,716,
  the zip's `PK\x03\x04` at column 2048. Offsets in `.json` `rows`.
- `packet-text.json`: the first 2,000 characters of pack.py, synth/throat.py, synth/pluck.py, genome.json and
  lyrics.txt as the zip holds them, with each entry's offset.

## daisy.json (daisy.py)

The cover's woodcut marks from `tools/cover/woodcut.py`, made by its own functions in `draw()`'s order with seed
11 (checked equal to `draw().marks`). `groups` in growth order: `crack` (from slab(): the gap, its hairlines,
the crack down the front face, its mouth, and the crumbs), `stem` (stem() and the crack's lip over its root),
`leaves` (both leaf()), `back_petals`, `front_petals_disc` (petals(front) and disc()). Each mark: `op` fill or cut,
`ink` (black, green, yellow, white), `rule` nonzero/evenodd, `rings` polygons. Every woodcut line is a filled
ribbon, so a stroke's width is its polygon. Points are normalised: `(p - (box.x0, box.y0)) / box.size`, y down,
the longer side 1. Inks are face.py's: black #2b231d, green #98a36b, yellow #dea833, white #fbf8f1 (also concrete,
grey, red, unused here). Printing as face.py does: one plate per ink; black over the tints; a later fill of
another ink hides a tint below; a cut takes white out of the black only; tints multiply with the paper.
`root`, `crack_gap`, `stem_line` (every 4th point), `disc_centre`, `disc_radius` for anchoring the strand.
Picture: renders/promo/video/scratch/daisy-stages.png (the five stages, printed so).

## throat/ (throat.py)

- `takes.json`: `calls`: the 11 captured calls and which take each is: sing-000 lead-0.00, 004 lead-0.20, 005
  lead-0.30, 006 lead-0.40, 007 lead-0.50, 008 lead-0.60, 009 lead-0.70, 010 lead-0.75, 001 choir3, 002 choir2,
  003 choir1. A choir call is known by its notes' part; a lead call by its notes (the stage plan's take) and,
  where notes are alike (0.5 to 0.75 all sing the phrasing whole), by its embedding's distance along the line
  from the human-0 embedding to the volunteers row (`share_measured`, equal to the take's share 0, .12, .18,
  .24, .30, .36, .42, .45). Each with `singer` (its eight numbers), `human`, `share`, `k`. `plan` the stage plan;
  `heard` the seconds heard of each (lead: from its plan time to the next, 30 ms fades at the joins; choir: its
  part's first note to last note's end). `rows`: the model's 24 singer rows (name, source formant / human /
  scyllasband, `retired` for the 13 scylla rows, embedding); `volunteers` is the people's row.
- Per call `<id>` (lead-0.00 ... lead-0.75, choir1-3), 200 frames a second from t = 0 of the song:
  `<id>.env` uint8 [frames, 128]: dB = v * 0.5 - 126, the envelope throat_line.py draws (throat.predict, gv 1,
  then throat.sharpen 1.5, in dB), `freqs` the 128 points (40 Hz to 11.8 kHz); `<id>.ap` uint8 [frames, 32]:
  aperiodicity = v / 255; `<id>.lf0` float32: natural-log f0 the throat was told; `<id>.flags` uint8: bit 0 voiced
  (phone not in throat.UNVOICED), bit 1 silence or breath; `<id>.phones.json`: `segments` [phone, t0, t1, note]
  (a run of one phone; `note` indexes `notes`, the note sounding at the run's middle, reaching 0.12 s before its
  start for leading consonants; -1 for sil and breath), `notes`, `heard`.
- `lead-heard.env` uint8 [30246, 128]: the heard lead, 0 to 151.23 s, each frame from the take the plan has there
  (the 30 ms crossfades are not blended: a frame is the incoming take's); zero after a take's last frame
  (146.6 s). `lead-heard.take`: index into `plan` per frame.
- `lead-0.00-whole.lf0` float32 [30246] and `.flags`: the human-0 take's log f0 and flags over the whole song
  (NaN after its last frame): the machine's straight line.
- `weights` float16 [984, 1020] (rows, columns): every one of the 886,372 weights where `singer_picture.layout()`/`tiles()` put
  them, cropped (`origin` [30, 190] is the crop's corner in singer_picture's 1080 x 1350 frame); NaN where none.
  `rects`: each tile (name, tile index, x, y, w, h).
- `act-verse1` float16 [1200, 5430], 60 a second from 10.9125 (verse 1, 20 s): `singer_picture.adding()` factored.
  Each weight's contribution is the weight times one number of this vector: W[i, j] of `inp`, `out`, `convs.n`,
  `mixes.n` times column j of that array's slice; `phone.weight`/`role.weight` [i, j] times row i of the `phone`
  / `role` slice; `films.n.weight` [i, j] times `singer` j; biases as they are, `singer.weight` 0. `layout` names
  each slice; `light_scale` is singer_picture's per-array 99.5th percentile (a pixel's amount is
  clip(|contribution| / scale, 0, 1) ** 0.8, red where positive, indigo negative). Averaged over each 1/60 s as
  adding() averages over a video frame. The take is the heard one: lead-0.00 to 25.596, lead-0.20, then lead-0.30
  from 30.596 (`take_changes`). Stored this way (13 MB) because per-weight values would be 886,372 a frame.

## verify.py

Checks the above against render.score.json, render.txt, the release file and `pack.packet_start`, that guard()
refuses renders/measured/ and no other prep script writes such a path, then prints sizes. Exit 1 on a failure.

## Replay data (replay.py, stems.py, physics.py)

### The replay (replay.py)

`uv run python tools/promo/video/prep/replay.py` runs `songbird render performance/genome.json --replay
performance/record-arc-morph.json --stems --out renders/promo/video/scratch/replay/render.flac`
(SONGBIRD_THREADS=2) with wrappers around the models' own functions, installed from outside as
`tools/promo/capture.py` does; no engine file is touched. **It prints audio id eb8fb05eb2bb**, the release's:
the wrappers changed nothing. The dry stems are written by render_one's own `kept` hook during the mix's pass
(the stem the mix receives, as `<out>.<part>.wav`, 32-bit float, exactly what `--stems` writes), and `--stems`'
second synthesis of every part is skipped. A thread-local stack of part names says which stem each model call
belongs to (a twin's player, made inside the twin's thread, pushes its own name). Captures go to
`renders/promo/video/scratch/replay/capture/` (`<kind>.pkl`, and the bow's and pipe's whole control tracks as
`bow-fiddle.npz`, `pipe-whistle.npz`); physics.py reads only those.

Where a model's loop is compiled (numba) and keeps its state in locals (`bowed.run`, `pipe.run`,
`analog._voice`, `chip._noise_events`), physics.py has an **instrumented copy**: the same arithmetic in the
same order, also storing the state, run on the captured inputs and asserted equal to the engine's output
(`np.array_equal`, bit for bit). Every one of them passes.

Below, **own** means the file holds the model's own signal or state; **re-run** means it holds the
parameters and the browser runs the same arithmetic to get the shape.

### stems/ (stems.py)

- `stems/<part>.wav` for the 24 parts above: 16-bit **mono** 44.1 kHz, (left + right) / 2 of the dry stem times
  **one shared gain, -3.55 dB** (`stems/gain.json`: the loudest part, voice, peaks at -1 dBFS; `dry_peak_db` per
  part), so levels compare across parts. 149.5875 s long (the score's length; the release file rings to
  151.227 with the room and master). The stage's twins, layers and level curves are in them. Own.
- `stems/<part>.env` and `stems/mix.env` (the release FLAC itself): uint8 `[9074, 99]`, `rate` 60, frame i
  centred on i / 60 s. Column 0 RMS dBFS over the frame's 1/60 s, 1 peak dBFS, 2 spectral flux, 3..98 96 band
  levels from 40 Hz to 16 kHz, log-spaced (`band_edges_hz`, 97 edges). dB = v * 0.392157 - 100 (`scale`,
  `offset`; v 0 is -100 dB or less). Flux = v * 0.25 dB (`flux_scale`): the mean rise over the bands since the
  previous frame, from a 1024-point Hann window centred on the frame (an onset lands on its frame: the drum's
  biggest flux values are within 0.35 frame of its hits). Bands: a 4096-point Hann window centred on the frame,
  each band's power summed over its bins and scaled so a sine of amplitude 1 reads -3 dB (as its RMS does);
  a band narrower than one bin (below about 300 Hz) reads the bin's density at its centre, so neighbouring low
  bands are correlated. Measured on the dry float stems, both channels, before the shared gain. Own.

### physics/ (physics.py), 27 MB in all

**pluck-<part>-notes.json + pluck-<part>.bin** (harp 324 notes, guitar 734, bass 176, lute 58). Re-run. Every
`pluck.pluck` call in time order, with the score note (`t d p v art`, `s` its start sample), the string's own
tuning offset (`tune`, cents), pick place, brightness, hardness, `len` samples, and its `planes`: a single string
has two (`across` the top: T60 0.8 x, full excitation; `along` the top: T60 2 x, excitation x `planes`, tuned
`split` cents away, 0.2 to 0.8: the slow beat); the lute's paired course has two strings (`string` 0 and 1,
`cents` -course/2 and +course/2, the second starting `lag` samples later), so four. Each plane: `N` (the whole
delay), `taps` (5: the one-zero loss [1 - loss, loss] convolved with a cubic Lagrange fractional delay; N + the
taps' delay = the period exactly), `g` the loop gain 10^(-3 / (T60 f)), `rg` the release gain (the finger
landing, from sample `held`), `smooth` (the gain's one-pole glide), `len`, and `x0`, `xn` into the .bin
(float32, every plane's one-period excitation in turn). The loop (`loop` in the file):
`y[n] = x[n] + g[n] * sum_k taps[k] * y[n - N - k]`, g = g0 until held, then g <- rg + (g - rg) * smooth.
**Check** (`check`): physics.loop_reference (plain Python) on the captured parameters equals the model's own
`_loop` output for the first four notes of each part exactly with float64 excitations (error 0), and to
5.2e-8 of the peak with the stored float32 ones. The plane's y is **bridge force**, not displacement; the note's
sound adds a pick or nail click, the finger's touch noise, a 4 ms end fade and a DC blocker to the summed
planes, then the part's sympathetic open strings and the body (not re-run). **The loop's state at sample n is
the last N + 5 values of y: one period of bridge force.** To draw the string truthfully: for an ideal string
fixed at both ends the bridge force over one period P is the slope of the string's travelling wave, so with F
the last P samples (less their mean) and S their running sum, the shape at that moment is
`y(j) = S[n - P + j] - S[n - j]`, j = 0..P/2 samples of travel from the bridge (x = 2j / P of the string). The
two planes are the string's two polarizations: drawn as vertical and horizontal displacement they trace the
string's orbit.

**strum.json**. Own. 195 guitar strokes: notes of one articulation (down, up, mute: a chop) starting within
45 ms of the stroke's first (the model's own grouping for the pick noise); each string's `p`, `dt` (onset after
the stroke's first, in the order the pick met them), `v`, `d`. 159 strokes are the strumming hand's
(`band._hand_stroke`, captured from the score's own realization and matched note for note, all 159): `kind`
(D d U u x B b), `accent`, `flag` (`open`: the open top strings as the fretting hand lifts), `slot` of `slots`,
`span`, `chord`, and each string's index 0 (low E) to 5. The other 36 (verse 2 from 55.9 s, and the tag) are
the older strum pattern's strokes: no hand data (`kind` null).

**drum.json + drum-modes.bin**. Re-run. The membrane has **196 modes** (`membrane()`: every Bessel zero below
40, m 0..39, counted from the code): `m n j ratio radiate`. 186 hits: `t d p v art`, `stroke` (bass 98, top 68,
tip 20), `r` (0 centre, 1 rim) and `theta` of the strike, `f0`, `contact_ms`, `glide`/`glide_time` (the two
lowest modes start that much sharp), `gain` (what hit() multiplies the ring by afterwards), `choke` (`[left, tau]`
from drum.py's CHOKES for a pressed stroke, else null). drum-modes.bin float32 `[186, 196, 3]`: per mode `amp` exactly as `_ring` received it, `T60` s, and `strike` (the mode's
amplitude at the strike, all directions: J_m(j r) / |J_(m+1)(j)| x the contact filter x the hit's own spread,
the spread rebuilt by repeating the hit's random draws from its captured generator state; amp = strike x
cos(m theta) x radiate, rebuilt to 2e-16). Sound: `sum amp_k exp(-6.9078 t / T60_k) sin(2 pi f0 ratio_k t)`
x gain, plus slap and click noise in the first 60 and 4 ms; at a hit with a choke, what the earlier hits still ring
is multiplied by `left + (1 - left) exp(-(t - its time) / tau)` (play()); the part high-passed (first order) at
0.7 x the skin's pitch.
Skin: `z(rho, phi, t) = sum strike_k J_m(j_k rho) cos(m_k (phi - theta)) exp(-6.9078 t / T60_k) sin(2 pi f_k t)`.

**body.json + body-<instrument>.bin** (lute guitar harp bass fiddle drone). Own. The body each instrument was
built with (body.CITTERN GUITAR HARP BASS FIDDLE REED_BOX), its maker's `seed` and `size`; its named modes as the
seed moved them (`hz q db t60`, repeated from the seed with impulse_response's own draws), the scattered plate
modes' frequencies, and the impulse response's first 100 ms (float32 `[4410, 2]`, two microphones).

**bow.json, bow-period, bow-shape, bow-velocity, bow-tracks** (the fiddle, 50.8 to 61.0 s: turn 1 and the
first verse-2 note after it). Own, from the instrumented copy of `bowed.run` (equal to the engine for the whole
song). The string is two delay lines meeting at the bow (bow to bridge and back, bow to nut and back); the copy
keeps, each sample, what the bridge and the nut send back and what the bow adds. The velocity at a place is
the wave going out (left the bow s samples ago) plus the wave coming back (reaching the bow s samples from
now), the bridge's loss filter (its delay pole/(1 - pole) = 0.82 samples) placed at the bridge; displacement
is the same read of each wave's running sum, less the straight line between the ends (what the sums leave at
the fixed ends). 96 places from the bridge (0) to the nut. `bow-period` float32 `[609, 16, 2, 96]`: at each
video frame from 50.8 s, **16 snapshots spread over one period** (displacement, velocity): the Helmholtz
corner's whole trip in slow motion; the displacement is two straight lines meeting at the corner. `bow-shape`
and `bow-velocity` `[4944, 96]` at 484.6 a second (every 91 samples: strobes the 554-988 Hz period, as a camera would).
`bow-tracks` `[2459, 5]` at 240 a second: bow velocity (signed), bow force (grip), bow position (fraction of the
loop from the bridge, about 0.085), loop pitch Hz, bridge force out.

**pipe.json, pipe-daisy-bore, pipe-daisy-tracks, pipe-daisy-jet** (the whistle 110.6 to 116.6 s: the four Daisy
notes). Own, from the instrumented copy of `pipe.run` (equal to the engine). The whistle's intro notes are
rendered but silent (its stage level is null until refrain 1; whistle~ plays them), so no intro file. The bore
is a single delay line one period long with a one-pole loss (feedback 0.65): `pipe-daisy-bore` `[2908, 64]` at
484.6 a second is its last period (point q is q/64 of a period back): the wave circulating in it (a comb
resonator, not a spatial pressure profile). Tracks at 240 a second: breath, chiff, drive, aim, pitch Hz, output.
Jet at 11,025 a second: the jet's deflection sin(phase) and the flow it puts into the bore.

**analog.json + analog-traces.bin**. Own, from the instrumented copy of `analog._voice` (all 1,008 phrases
equal to the engine's samples). Every voice phrase of the analog twins and layers (arp, synthpad, synthbass,
whistle~ harp~ bass~ guitar~ fiddle~): `stem machine t notes`, the preset's `oscillators` and the voice's `waves`
(a width-modulated pulse is two saws), each oscillator's detune, `resonance_k`, drive, key `track`, chorus, the
envelopes and per note the filter envelope's `amount_oct` and `base_cutoff_hz`; `row0`, `rows` into the traces:
float32 at 240 a second from the phrase's `t`: pitch (MIDI, with glide and vibrato), amp envelope x velocity
gain, filter envelope, **ladder cutoff Hz** (the filter moving).

**chip.json + chip-harp-pulse.bin, chip-drummachine-noise.bin, chip-drummachine-triangle.bin**. Own. The NES
2A03 twins' driver frames (60.0988 a second). harp# pulse `[8811, 7]`: t0, t1, Hz, 4-bit volume, the 8-step
sequence's high part lo..hi (duty), restart. drummachine# triangle `[815, 3]`: t0, t1, Hz (the kick and toms
swept down a frame a step). drummachine# noise `[3137, 6]`: t0, t1, clock Hz, short mode, volume, **the 15-bit
register as the frame begins** (from the instrumented copy of `chip._noise_events`, equal to the engine), and
per hit (`hits`): piece, clock index and period (CPU cycles), `seed` (the register at the hit), taps [0, 1]
(32,767 steps) or [0, 6] (93 steps). The register shifts once a clock,
`reg = (reg >> 1) | (((reg ^ (reg >> tap)) & 1) << 14)`, sounding the volume while bit 0 is clear. The chip
drums' notes start at 0.92 s; their stage level is null until 5.88 s (intro@0.5).

**drummachine.json**. Own. 688 hits of the two TR-808s (`drummachine`, the layer's; `drum~`, the drum's twin):
the piece (the circuit voice), trigger `size`, `accent`, `cents`, `loose`, `cut_s` (choked by), `mix`, `len_s`,
`peak`; `machines` the machine's own settings (tolerances and knobs, as its maker drew them).

**reed.json + reed-tables.bin + reed-tracks.bin**. Own. The drone's 6 notes: each note's wavetable (float32
`[6, 4096]`, one period, as `reed.table` made it), and at 240 a second the bellows curve (swell, pumping,
velocity) and, for each of its 3 reeds, Hz and amplitude.

Decimated: the bow's string to 96 places (at 484.6 a second, plus 16 per period at each frame), the pipe's bore
to 64 points at 484.6 a second, its jet to every 4th sample, the analog traces and the bow's, pipe's and reed's
tracks to 240 a second, the body responses to 100 ms. The pluck excitations, drum modes and chip frames are whole.
