# Sound design in the studio (2026-09-29)

docs/STUDIO-EDM-TEST.md's first finding: "No EDM sounds. There is no sidechain pump (the mixer only ducks
for the voice), no synth patch or filter choices, no risers, sweeps or snare rolls, and the drum kit is
fixed." This is how a person gets them: as edits, like every other choice in the studio (marked as the
person's, undoable, recorded, replayed byte for byte by `--replay`, handed down to children). The engine and
its API; the mixer and inspector pages are being designed apart (a channel strip per player: gain, pan,
mute/solo, sends, sidechain; an inspector showing a selected player's sound).

## Design

### What a person may change

Names are kept apart from the arrangement's: a player's *pattern* (what it plays, the arrangement's) is not
its *patch* or *kit* (what it sounds like, here).

| Path | Value | What it does |
|---|---|---|
| `sound.<player>.patch` | a patch's name for that player's synth (below), or null | the synth's sound: oscillators, filter, envelopes |
| `sound.<player>.cutoff` | Hz at the patch's reference note, 40 to 16,000 | the ladder's cutoff, in place of the patch's (the band's brightness no longer moves it) |
| `sound.<player>.resonance` | 0 to 1 (1 sings) | the ladder's resonance |
| `sound.<player>.envelope` | octaves, 0 to 6 | how far the filter's envelope opens it |
| `sound.<player>.kit` | `808`, `909`, `lofi`, `acoustic`, or null | a drum player's kit |
| `sound.<player>.kick`, `.snare`, `.hat` | `{"tune": semitones -12..12, "decay": 0.25..4 times}` (the snare also `"snappy": 0..2` times) | a drum machine piece's character |
| `mix.<player>.pan` | -1 (left) to 1 (right) | where the player sits, in place of its own place |
| `mix.<player>.send` | 0 to 3 times its designed send (1 as designed, 0 dry) | how much of it reaches the room |
| `mix.<player>.sidechain` | a preset (`subtle`, `classic`, `heavy`), or `{"depth": dB 0..24, "release": beats 0.1..2, "key": "kick" or "beat", "sections": [ids or names]}` (any left out: the preset `classic`'s), or null | the player ducks on the kick, or on every beat (a pump without a kick), in all sections or only those named |
| `transition.<section-id>` | `{"riser": bars, "down": bars, "impact": bool, "roll": bars, "sweep": bars or {"bars": n, "type": "highpass" or "lowpass"}}`, bars 0, 1, 2 or 4; or null | what happens at the boundary into that section (`refrain:2`: the third refrain, as `form.order` names it): a riser and a snare roll over the bars before, the band's filter sweeping over them, an impact on the downbeat and a downlifter falling after it |

`<player>` is a player of this version's band (`synthbass`, `synthpad`, `arp`, `synthlead`, `chip`,
`drummachine`, `kit`, the eight...). An edit for a player the band hasn't got is refused with why, as a gain
for one is (`band.<player>`); one inherited from a parent waits, silent, for a version whose band has it.
A transition into a section this form doesn't sing is refused, said as a part for one is ("Notes in").

The presets: **subtle** 4 dB, released over 0.35 of a beat; **classic** (the default) 8 dB over 0.55 of a
beat; **heavy** 14 dB over 0.85 of a beat; all keyed on the kick, with a 3 ms attack. A release in beats
follows the tempo, so a pump keeps its shape at 100 or 128.

### The patches

Each named for its sound; the program's own is the preset the synth has always had, and is the default.

| Player's synth | Patches (the program's own first) |
|---|---|
| synth bass (`synth-bass`) | **analog** (two saws and a square an octave down, a snappy filter), **sub** (the sine of `sub-bass`, phase-reset, a touch of its octave), **reese** (two saws 16 cents apart and one a little further, their beating slow, through a closed ladder, no filter envelope, held), **pluck** (a saw and a pulse, the filter snapping shut in 0.12 s, no sustain) |
| synth lead (`synth-solo`) | **saw** (two detuned saws and a 4' square, as it is), **square** (a pulse at 50% and one an octave down at 25%, hollow), **supersaw** (seven saws spread over ±22 cents, the filter open, no vibrato's delay changed) |
| synth pad (`synth-pad`) | **warm** (as it is: PWM and two saws, the ladder at 1.1 kHz, the chorus), **glass** (a narrow pulse and a saw an octave up, a resonant ladder at 3 kHz, a slow attack), **wide** (the saws 22 cents apart, the chorus twice as deep) |
| arpeggio (`synth-arp`) | **pluck** (as it is), **bell** (a saw and a pulse an octave and a fifth up, a resonant filter, gone in half a second, no sustain) |
| chip (`chip`) | **its own** (the pulse's width by the band's brightness), **thin** (12.5%), **reedy** (25%), **hollow** (50%) |

A patch is a variation of the analog synth's preset dictionary (`analog.PRESETS`), so the numba voice is
the same kernel (any number of saws and pulses, their octaves any ratio): no new kernel. Each patch is set so
a typical part at velocity 0.6 is within 2 dB of the program's own (a test measures it), so choosing one
changes the sound, not the balance; the gain is `band.<player>`.

### The kits

| Kit | What plays |
|---|---|
| **808** | `drums-808` (the drum machine's own) |
| **909** | `drums-909` |
| **lofi** | the 808 soft and worn: its body 1.25 (lower, longer), brightness 0.15, wear 0.6, then a 6 kHz low-pass and a little saturation, as a sampler's |
| **acoustic** | the kit (`kit`), the machine's strokes as a drummer's (kick, snare, hat, open hat, toms, crash, ride, clap as a rim shot) |

A kit is a module chosen for the player; its level is the module's own calibrated level (each sits as the
band's reference for percussion), times the player's gain. A drum machine piece's character moves its
circuit after the machine is made (`bd_f0` and `bd_t60` for the kick...), so the maker's tolerances draw as
before; the acoustic kit has none (its drums are tuned by its drummer: said).

### The sidechain

The mix (`mixing.mix_made`) applies, to a pumped player's channel after its strip and before the band sum,
a gain that dips `depth` dB at each trigger within 3 ms and comes back over `release` (a raised cosine), so
its send to the room pumps too, as a sidechain on the channel does. The voice's own ducking (the band making
way for the singer) is kept as it is, after.

The triggers are a silent **key track** (a "ghost kick" as producers keep one): realize writes one for each
kick the band's drum player plays (or each beat of the clock, for `"key": "beat"`) in the sections asked,
with the player it ducks, into `Score.sound["triggers"]` (see the review, point 1). It is never rendered or
exported, and it moves with the score, so a section's preview (`studio.cut`) pumps where the whole song
does. The depth and release (in seconds, from the tempo) ride in `Score.sound["players"]`.

### The transitions

Also written into the score by realize (`Score.sound["transitions"]`, each its kind, span and level; the
review's points 1 and 2), after the band and a person's parts, from the section's first bar line on the
rendition's clock, straight within each beat (`composition.beat_clock`):

- **riser**: an `fx` note over the bars before: noise through a band-pass rising exponentially from 250 Hz
  to 9 kHz, swelling (level up 18 dB), a sine an octave up under it, wider as it rises; it stops at the
  downbeat.
- **roll**: snare strokes on the band's drum player (a drum machine, a kit, the chip's), a quarter of the
  span each in quarters, eighths, sixteenths and thirty-seconds, velocity rising 0.35 to 0.95; the player's
  own snares, claps, rims and toms in the span are left out (its kick and hats stay). With no drum player the
  `fx` track plays it on a 909.
- **sweep**: an `fx` note the mixer reads: over the span every band channel (not the singers, not `fx`)
  goes through a high-pass rising from 20 Hz to 1.5 kHz (or a low-pass falling from 16 kHz to 350 Hz), at
  0.3 resonance, its coefficients moved every 64 samples with the filter's state carried, snapping back at
  the downbeat.
- **impact**: an `fx` note on the downbeat: a sine falling from 110 to 42 Hz in 0.25 s and ringing 1.5 s, a
  burst of low-passed noise, a little wide.
- **down** (downlifter): an `fx` note over the bars after: noise through a band-pass falling from 6 kHz to
  200 Hz, fading.

The `fx` stem is rendered by `synth/sweeps.py` (numpy and scipy only: noise, `sosfilt` a block at a time,
cumulative phases; no numba, so nothing for the browser's kernel translation), placed in the middle, and mixed
as a role of its own (a high-pass at 30 Hz, the band's send). Its randomness is its own stream from the
render's seed.

### Pan and sends

A pan replaces the player's place at `instruments.place` (a mono source panned, a stereo one's middle moved
and its sides kept), so the stems (`--stems`) carry it too. A send multiplies the channel's strip send
(`Strip.send`) in `mix_made`. Stems are dry: no send, no sidechain, no sweep.

### Where it lives

- `Params.sound` (new, a dict, left out of `to_dict()` while empty, so every record, seed and child is as
  before): `{"players": {player: {patch, cutoff, resonance, envelope, kit, kick, snare, hat, pan, send,
  sidechain}}, "transitions": {section-id: {...}}}`. Children inherit it (`variation.choose` starts from the
  parent's dict), as a person's chords and parts pass on.
- `songbird/sound.py` (new): the catalog (players' synths, patches, kits, presets), `check()` for each path,
  `pin()` into the table's dict, `marks`' "was", the score's additions (`produce()`: the rolls into the
  notes; the key track, the transitions and the per-player settings for the synth into `Score.sound`), and
  `view()` for the page.
- `songbird/edits.py`: a clearly separated "sound design" section that calls sound.py (check, pin, marks);
  the generic `mix.` pin skips the per-player paths.
- `songbird/realize.py`: two calls, both returning what they were given when `params.sound` is empty.
- `songbird/synth/`: `instruments.render_part/render_other` read the player's sound (patch and filter into
  the module's settings, a kit's module, a pan); `analog.py` and `chip.py` take a patch; `drummachine.py` the
  lofi kit and pieces' character; `sweeps.py` the `fx` stem; `mixing.mix_made(..., sound=None)` the sends,
  sidechain and sweeps; `synth.render` reads `score.sound`.
- `songbird/studio.py`: a "Sound design" section: `POST /api/sound` with the edits, returning each player's
  sound (below) and the boundaries; everything else (hearing, recording) is the edits as ever.

### The API

`POST /api/sound {"edits": {...}}`:

```json
{"players": [
   {"player": "synthbass", "name": "the synth bass", "synth": "synth-bass", "role": "bass",
    "gain": {"value": 1.0, "yours": false},
    "patch": {"value": "reese", "program": "analog", "yours": true,
              "options": [{"name": "analog", "about": "..."}, ...]},
    "filter": {"cutoff": {"value": 420, "program": 320, "min": 40, "max": 16000, "yours": true},
               "resonance": {...}, "envelope": {...}},
    "kit": null, "pieces": null,
    "pan": {"value": 0.0, "program": 0.0, "min": -1, "max": 1, "yours": false},
    "send": {"value": 1.0, "program": 1.0, "min": 0, "max": 3, "yours": false},
    "sidechain": {"value": {"depth": 8, "release": 0.55, "key": "kick", "sections": null}, "program": null,
                  "yours": true, "presets": {"subtle": {...}, "classic": {...}, "heavy": {...}},
                  "keys": ["kick", "beat"], "has_kick": true}}, ...],
 "boundaries": [
   {"id": "refrain:0", "name": "Refrain 1", "from": "verse:0", "bar": 9,
    "value": {"riser": 2, "roll": 1}, "program": null, "yours": true}, ...],
 "limits": {...}, "problems": [...]}
```

Each value says whether it is the program's (`yours` false; `program` is what the program has, inherited
values included) or the person's. The page sets values as edits and asks `/api/song` and `/api/listen` as
ever.

### Byte for byte

With no such edits: `Params.to_dict()` unchanged (no `sound` key), `Score.to_dict()` unchanged (no `sound` key), `score.band` untouched,
no new notes, every changed function taking its old path when the sound is empty (a patch
of None is the preset object itself; `mix_made` with `sound=None` runs the same code). The goldens
(tests/golden/*.sha256, tests/test_determinism.py, the seed scores) and the lean-render tests hold. No new
numba kernel; no fastmath anywhere. Memory: the pump gain is made a stretch at a time (65,536 samples) like
the send sums; a sweep holds only its span; the `fx` stem is one stem more (107 MB stereo for H) and only
when a transition is asked for.

### Decisions for the artist

1. **The patches are few and named by sound**, not the synths' parameters; the filter is the only raw knob
   (cutoff, resonance, envelope). Envelopes (attack, release) and oscillator mixes could be next.
2. **A person's cutoff replaces the band's brightness** for that synth (the brightness slider no longer moves
   it): the knob a person turned wins.
3. **Sidechain by preset or numbers**, keyed on the kick the drum player really plays (no kick in a verse: no
   pump there), or on every beat.
4. **Transitions are sound, not arrangement**: they don't change which players play or the section's length
   (the arrangement's work); a roll takes the snare's place in its bars.
5. **The kit is a sound**: an acoustic kit playing a drum machine's pattern plays it as a drummer would
   (with its own touch).

## After a Fable review (read-only, before building)

A read-only review of the design above; its points are in, and change it where they say:

1. **The key track and the transitions are not notes.** As notes in `score.notes` every part-enumerator would
   have met them (the band's stems, the render's stages, the MIDI file and the sketch's players, notes in,
   the piano page, a style's key lift). They are a field of their own, `Score.sound` (left out of
   `to_dict()` while empty, so the seed scores' hashes hold): `{"players": {...}, "triggers": [[seconds,
   player], ...], "transitions": [[kind, start, end, level, key], ...]}`. Only the synthesis reads it, and
   `studio.cut` shifts and trims it with the notes (one place). A roll's strokes are real notes on the drum
   player, as its own are.
2. **A transition is its whole span.** A section's preview may begin in the middle of a riser: it is made
   over its whole span, from its own noise stream (the render's seed and the transition's `key`, not where
   it starts), and only the part inside the preview is kept, so it sounds as it does in the whole song.
3. **The sweep is on the band bus**, once over its span: the band's sum, what steps back under the voice and
   the band's send to the room, all three (else the voice's duck would take away unswept sound). The `fx`
   stem comes last and joins after it, unswept.
4. **The pump is in the mix's stretch loop**: each stretch of a pumped channel is scaled before it goes into
   the band, its send and what steps back. Overlapping triggers: the deeper of the two envelopes. The trigger
   is the kick as played (after its human timing), not the grid: the pump follows the drummer.
5. **One drum player** for the pump's key, the roll and the page's "has a kick": the first of the band's
   `kit`, `drummachine`, `chip`'s drums, `claps`, `stomps`, `cajon`, `drum` that plays (idioms' own order for a
   count-in). A kick is read through each module's names: the drum machine's `piece_of` (`kick`, `bd`,
   `bass`...), the kit's `kick` and `kick-dead`, the cajon's `cajon-bass`, a stomp, the frame drum's `bass`.
6. **A kit swap maps the strokes both ways** (a drum machine's pattern on the acoustic kit, a drummer's on a
   machine: `hat-foot` to `hat-pedal`, `snare-ghost` a soft `snare`, `brush-tap` a soft `snare`, a brush
   sweep left out, `ride-bell` to `cowbell`...), and the mix treats the channel as the module it now is (a
   machine as `drum`, the acoustic kit as `kit`), not as its player's name.
7. **`fx` is a role of its own** in the mix (a 30 Hz high-pass, the band's send, no step back), and the `fx`
   stem is among `--stems`.
8. **No riser, roll or sweep into the first section** (nothing comes before it: refused with why); an impact
   or a downlifter there is fine. The rolls are written after realize's last ring is added.
9. **A bar is the meter's** (`meter.bar` grid units on `composition.beat_clock`, straight within a beat, or a
   foot in a re-barred feel); a roll replaces the snares under the previous line's cadence and a singer's
   pickup (said). Under the final ritardando a riser stretches with the clock and still ends on the downbeat.
10. **Dict values are made canonical by `check()`** (fixed keys in a fixed order, numbers rounded, a preset
    expanded to its numbers, unknown keys refused), so the record, `from_record` and a child's seed don't
    depend on how the page wrote them. As with a person's chords or parts, any sound edit changes the seed
    each child draws from its parent's record (`variation.Chance` hashes it).
11. **Patches levelled by loudness** (BS.1770, a typical part at velocity 0.6, each patch's `out`): all within
    0.1 dB of the program's own, the sub 1.8 dB under by design (K-weighting reads a sub quieter than it is).
12. **Cutoff**: a person's replaces the patch's, and only the brightness's ±0.8 octave is dropped; the maker's
    trim, the key tracking, the velocity and the envelope's velocity scaling stay. `envelope` replaces the
    amount before its velocity scaling. A piece's decay at most 4 times (an 808 kick under 4 s).
13. **An impact on a kick**: where the drum player has a kick within 30 ms of the downbeat, the impact's boom
    is high-passed at 90 Hz and 6 dB lower, so the two don't fight.
14. Its suggestion to cut the lofi and acoustic kits, the low-pass sweep, the downlifter and `"key": "beat"`
    was weighed against the brief, which asks for each; all are small and kept. Its suggestion to export the
    key track as a muted MIDI track (for a producer's own sidechain) is left for later.
15. **Robust to the other work going on**: everything is read from the score after the band and a person's
    parts are laid (a pump where a section has no kick is silent; a roll where it has no snare is added), and
    the `mix.<player>.*` paths are checked and pinned apart from the mix's own knobs. A roll on the acoustic
    kit changes the touch of that kit's later strokes (it draws its randomness stroke by stroke), only when
    asked for.

## As built

As designed with the review's changes, and one more: a **stop** (`"stop": 1, 2 or 4`, in beats: the band
silent for the last beats before the section, the singer and the transitions going on), which the redesign's
seam offers (docs/STUDIO-REDESIGN.md). Each value in `/api/sound` also carries its `path`, the edit that sets
it. The analog synth's patches sit after its kernels in analog.py, so each kernel keeps the line the browser's
translation names it by (web/studio-wasm is unchanged). What a person gets, the API, the measurements of a
real run (the pad pumping at the beat rate, the riser's centroid rising, replay exact, 1.13 GB on two threads)
and the decisions for the artist are in docs/STUDIO.md, "Sound design (2026-09-29)"; the tests are
tests/test_sound.py.

| Where | What |
|---|---|
| songbird/sound.py | the catalog, `check`, `pin`, `value_of` (a mark's "was"), `produce` (realize's rolls, key track, transitions), `shifted` (a preview's), `view` and `label` (the page's) |
| songbird/edits.py | calls sound.py where it checks, pins and marks, in marked lines; the mix's own knobs skip `mix.<player>.*` |
| songbird/realize.py | `Params.sound`; one call to `sound.produce` before the score is made |
| songbird/score.py | `Score.sound`, left out of `to_dict()` while empty |
| songbird/synth/analog.py, chip.py, drummachine.py | patches and the filter; the chip's width; the lofi kit and the pieces' character |
| songbird/synth/instruments.py | `voiced`: a player's patch, filter, pieces, kit (its module, strokes renamed, level) and pan; the `fx` stem last |
| songbird/synth/mixing.py | `Design`: sends, the pump in each channel, the band's sweeps and stops once on its bus; the `fx` role |
| songbird/synth/sweeps.py | risers, downlifters, impacts, a drummerless roll; the moving filter (numpy and scipy only) |
| songbird/studio.py | `Studio.sound` and `POST /api/sound`, in their own section; `cut` moves a score's sound design |
