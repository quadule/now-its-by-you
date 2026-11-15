# Sound design in the studio

A person can change what each player sounds like and what happens at a
section boundary: synth patches and filters, drum kits, a sidechain pump,
pan and sends, risers, rolls, sweeps, impacts and stops. These are edits like
every other choice in the studio: marked as the person's, undoable, recorded,
replayed byte for byte by `--replay`, handed down to children. What a person
gets on the page is in docs/STUDIO.md, "Sound design"; this is the engine.
The tests are tests/test_sound.py.

A player's *pattern* (what it plays) is the arrangement's; its *patch* or
*kit* (what it sounds like) is sound design's.

## Design

### What a person may change

| Path | Value | What it does |
|---|---|---|
| `sound.<player>.patch` | a patch's name for that player's synth (below), or null | the synth's sound: oscillators, filter, envelopes |
| `sound.<player>.cutoff` | Hz at the patch's reference note, 40 to 16,000 | the ladder's cutoff, in place of the patch's (the band's brightness doesn't move it) |
| `sound.<player>.resonance` | 0 to 1 (1 sings) | the ladder's resonance |
| `sound.<player>.envelope` | octaves, 0 to 6 | how far the filter's envelope opens it |
| `sound.<player>.kit` | `808`, `909`, `lofi`, `acoustic`, or null | a drum player's kit |
| `sound.<player>.kick`, `.snare`, `.hat` | kick `{"tune": semitones -12..12, "decay": 0.25..4 times}`; the snare also `"snappy": 0..2` times; the hat `{"decay"}` | a drum machine piece's character |
| `mix.<player>.pan` | -1 (left) to 1 (right) | where the player sits, in place of its own place |
| `mix.<player>.send` | 0 to 3 times its designed send (1 as designed, 0 dry) | how much of it reaches the room |
| `mix.<player>.sidechain` | a preset (`subtle`, `classic`, `heavy`, `off`), or `{"depth": dB 0..24, "release": beats 0.1..2, "key": "kick" or "beat", "sections": [ids or names]}` (any left out: `classic`'s), or null | the player ducks on the kick, or on every beat (a pump without a kick), in all sections or only those named |
| `transition.<section-id>` | `{"riser": bars, "down": bars, "roll": bars, "sweep": bars or {"bars": n, "type": "highpass", "lowpass" or "open"}, "stop": beats, "impact": bool}`, bars 0, 1, 2 or 4, a stop 1, 2 or 4 beats; or null | what happens at the boundary into that section (`refrain:2`: the third refrain, as `form.order` names it) |

`<player>` is a player of this version's band (`synthbass`, `synthpad`,
`arp`, `synthlead`, `chip`, `drummachine`, `kit`, the eight...). An edit for
a player the band hasn't got is refused with why, as a gain for one is
(`band.<player>`); one inherited from a parent waits, silent, for a version
whose band has it. A transition into a section this form doesn't sing is
refused, said as a part for one is ("Notes in"). No riser, roll, sweep or
stop goes into the first section (nothing comes before it: refused with
why); an impact or a downlifter there is fine.

The sidechain presets: **subtle** 4 dB, released over 0.35 of a beat;
**classic** (the default) 8 dB over 0.55 of a beat; **heavy** 14 dB over 0.85
of a beat; **off** no pump (it takes away a style's own); all keyed on the
kick, with a 3 ms attack. A release in beats follows the tempo, so a pump
keeps its shape at 100 or 128.

Dict values are made canonical by `check()` (fixed keys in a fixed order,
numbers rounded, a preset expanded to its numbers, unknown keys refused), so
the record, `from_record` and a child's seed don't depend on how the page
wrote them. As with a person's chords or parts, any sound edit changes the
seed each child draws from its parent's record (`variation.Chance` hashes
it).

### The patches

Each is named for its sound; the program's own is the default.

| Player's synth | Patches (the program's own first) |
|---|---|
| synth bass (`synth-bass`) | **analog** (two saws and a square an octave down, a snappy filter), **sub** (the sine of `sub-bass`, phase-reset, a touch of its octave), **reese** (two saws 16 cents apart and one a little further, their beating slow, through a closed ladder, no filter envelope, held), **pluck** (a saw and a pulse, the filter snapping shut in 0.12 s, no sustain) |
| synth lead (`synth-solo`) | **saw** (two detuned saws and a 4' square), **square** (a pulse at 50% and one an octave down at 25%, hollow), **supersaw** (seven saws spread over ±22 cents, the filter open) |
| synth pad (`synth-pad`) | **warm** (PWM and two saws, the ladder at 1.1 kHz, the chorus), **glass** (a narrow pulse and a saw an octave up, a resonant ladder at 3 kHz, a slow attack), **wide** (the saws 22 cents apart, the chorus twice as deep) |
| arpeggio (`synth-arp`) | **pluck**, **bell** (a saw and a pulse an octave and a fifth up, a resonant filter, gone in half a second, no sustain) |
| chip (`chip`) | **own** (the pulse's width by the band's brightness), **thin** (12.5%), **reedy** (25%), **hollow** (50%) |

A patch is a variation of the analog synth's preset dictionary
(`analog.PRESETS`), so the numba voice is the same kernel (any number of saws
and pulses, their octaves any ratio). The patches sit after the kernels in
analog.py, so each kernel keeps the line the browser's translation names it
by. Each patch is levelled by loudness (BS.1770, a typical part at velocity
0.6, each patch's `out`): all within 0.1 dB of the program's own, the sub 1.8
dB under by design (K-weighting reads a sub quieter than it is). Choosing one
changes the sound, not the balance; the gain is `band.<player>`.

A person's cutoff replaces the patch's, and only the brightness's ±0.8 octave
is dropped; the maker's trim, the key tracking, the velocity and the
envelope's velocity scaling stay. `envelope` replaces the amount before its
velocity scaling.

### The kits

| Kit | What plays |
|---|---|
| **808** | `drums-808` (the drum machine's own) |
| **909** | `drums-909` |
| **lofi** | the 808 soft and worn: its body 1.25 (lower, longer), brightness 0.15, wear 0.6, then a 6 kHz low-pass and a little saturation, as a sampler's |
| **acoustic** | the kit (`kit`), the machine's strokes as a drummer's |

A kit is a module chosen for the player; its level is the module's own
calibrated level (each sits as the band's reference for percussion), times
the player's gain. A kit swap maps the strokes both ways (a drum machine's
pattern on the acoustic kit, a drummer's on a machine: `hat-foot` to
`hat-pedal`, `snare-ghost` and `brush-tap` a soft `snare`, a brush sweep left
out, `ride-bell` to `cowbell`, a clap as a rim shot...), and the mix treats
the channel as the module that plays it (a machine as `drum`, the acoustic kit as
`kit`), not as its player's name. A drum machine piece's character moves its
circuit after the machine is made (`bd_f0` and `bd_t60` for the kick...), so
the maker's tolerances draw as they do without it; a piece's decay is at
most 4 times (an 808 kick under 4 s). The acoustic kit has no piece
character: its drums are tuned by its drummer.

### The drum player

One drum player gives the pump its key, plays the roll and gives the page
its "has a kick": the first of the band's `kit`, `drummachine`, `claps`,
`stomps`, `cajon`, `drum` that plays (idioms' own order for a count-in). A
kick is read through each module's names: the drum machine's `piece_of`
(`kick`, `bd`, `bass`...), the kit's `kick` and `kick-dead`, the cajon's
`cajon-bass`, a stomp, the frame drum's `bass`.

### The sidechain

The triggers are a silent **key track** (a "ghost kick" as producers keep
one): realize writes one for each kick the drum player plays, as played
(after its human timing), or each beat of the clock for `"key": "beat"`, in
the sections asked, with the player it ducks, into `Score.sound["triggers"]`.
A section with no kick has no pump. The key track is never rendered or
exported, and it moves with the score, so a section's preview (`studio.cut`)
pumps where the whole song does. The depth and release (in seconds, from the
tempo) ride in `Score.sound["players"]`.

The mix (`mixing.mix_made`, `Design`) applies the pump in its stretch loop:
each stretch of a pumped channel, after its strip, is scaled before it goes
into the band, its send and what steps back, by a gain that dips `depth` dB
at each trigger within 3 ms and comes back over `release` (a raised cosine);
of overlapping triggers the deeper envelope wins. So its send to the room
pumps too, as a sidechain on the channel does. The voice's own ducking (the
band making way for the singer) comes after, as it is.

### The transitions

Realize writes them into the score (`Score.sound["transitions"]`, each its
kind, span, level and key) after the band and a person's parts, from the
section's first bar line on the rendition's clock. A bar is the meter's
(`meter.bar` grid units on `composition.beat_clock`, straight within a beat,
or a foot in a re-barred feel); under the final ritardando a riser stretches
with the clock and still ends on the downbeat.

- **riser**: an `fx` note over the bars before: noise through a band-pass
  rising exponentially from 250 Hz to 9 kHz, swelling (level up 18 dB), a
  sine an octave up under it, wider as it rises; it stops at the downbeat.
- **roll**: snare strokes on the drum player, a quarter of the span each in
  quarters, eighths, sixteenths and thirty-seconds, velocity rising 0.35 to
  0.95. They are real notes, written after realize's last ring is added; the
  player's own snares, claps, rims and toms in the span are left out (its
  kick and hats stay), including those under the previous line's cadence
  and a singer's pickup. With no drum player the `fx` track plays it on a
  909. A roll on the acoustic kit changes the touch of that kit's later
  strokes (it draws its randomness stroke by stroke).
- **sweep**: over the span every band channel (not the singers, not `fx`)
  goes through a high-pass rising from 20 Hz to 1.5 kHz, a low-pass falling
  from 16 kHz to 350 Hz, or (`open`) a low-pass rising from 350 Hz to 16 kHz,
  at 0.3 resonance, its coefficients moved every 64 samples with the filter's
  state carried, snapping back at the downbeat. It is applied once on the
  band bus: the band's sum, what steps back under the voice and the band's
  send to the room, all three (else the voice's duck would bring back unswept
  sound).
- **stop**: the band silent for the last 1, 2 or 4 beats before the section,
  the singer and the transitions going on, on the band bus as the sweep is.
- **impact**: an `fx` note on the downbeat: a sine falling from 110 to 42 Hz
  in 0.25 s and ringing 1.5 s, a burst of low-passed noise, a little wide.
  Where the drum player has a kick within 30 ms of the downbeat, the boom is
  high-passed at 90 Hz and 6 dB lower, so the two don't fight.
- **down** (downlifter): an `fx` note over the bars after: noise through a
  band-pass falling from 6 kHz to 200 Hz, fading.

A transition is made over its whole span from its own noise stream (the
render's seed and the transition's `key`, not where it starts), and a
section's preview keeps only the part inside it, so a riser heard from its
middle sounds as it does in the whole song.

The `fx` stem is rendered by `synth/sweeps.py` (numpy and scipy only: noise,
`sosfilt` a block at a time, cumulative phases; no numba, so nothing for the
browser's kernel translation), placed in the middle, and mixed as a role of
its own (a 30 Hz high-pass, the band's send, no step back), joining after the
band's sweep, unswept. It is among `--stems`.

### Pan and sends

A pan replaces the player's place at `instruments.place` (a mono source
panned, a stereo one's middle moved and its sides kept), so the stems
(`--stems`) carry it too. A send multiplies the channel's strip send
(`Strip.send`) in `mix_made`. Stems are dry: no send, no sidechain, no sweep.

### Where it lives

`Params.sound` (a dict, left out of `to_dict()` while empty):
`{"players": {player: {patch, cutoff, resonance, envelope, kit, kick, snare,
hat, pan, send, sidechain}}, "transitions": {section-id: {...}}}`. Children
inherit it (`variation.choose` starts from the parent's dict), as a person's
chords and parts pass on. The key track and the transitions are not notes:
as notes every part-enumerator would meet them (the band's stems, the
render's stages, the MIDI file, notes in, the piano page, a style's key
lift). They are `Score.sound`, also left out of `to_dict()` while empty:
`{"players": {...}, "triggers": [[seconds, player], ...], "transitions":
[[kind, start, end, level, key], ...]}`. Only the synthesis reads it, and
`studio.cut` shifts and trims it with the notes.

| Where | What |
|---|---|
| songbird/sound.py | the catalog, `check`, `pin`, `value_of` (a mark's "was"), `produce` (realize's rolls, key track, transitions), `shifted` (a preview's), `view` and `label` (the page's) |
| songbird/edits.py | calls sound.py where it checks, pins and marks, in marked lines; the mix's own knobs skip `mix.<player>.*` |
| songbird/realize.py | `Params.sound`; one call to `sound.produce` before the score is made, after the band and a person's parts are laid |
| songbird/score.py | `Score.sound`, left out of `to_dict()` while empty |
| songbird/synth/analog.py, chip.py, drummachine.py | patches and the filter; the chip's width; the lofi kit and the pieces' character |
| songbird/synth/instruments.py | `voiced`: a player's patch, filter, pieces, kit (its module, strokes renamed, level) and pan; the `fx` stem last |
| songbird/synth/mixing.py | `Design`: sends, the pump in each channel, the band's sweeps and stops once on its bus, the dub desk's throws; the `fx` role |
| songbird/synth/sweeps.py | risers, downlifters, impacts, a drummerless roll; the moving filter (numpy and scipy only) |
| songbird/synth/dub.py | the dub desk's tape echo and spring |
| songbird/studio.py | `Studio.sound` and `POST /api/sound`, in their own section; `cut` moves a score's sound design |

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

Each value says whether it is the program's (`yours` false; `program` is what
the program has, inherited and a style's values included) or the person's,
and carries its `path`, the edit that sets it. The page sets values as edits
and asks `/api/song` and `/api/listen` as ever.

### Byte for byte

With no such edits: `Params.to_dict()` and `Score.to_dict()` have no `sound`
key, `score.band` is untouched, there are no new notes, and every function
takes its plain path (a patch of None is the preset object itself;
`mix_made` with `sound=None` runs the same code). The goldens
(tests/golden/*.sha256, tests/test_determinism.py, the seed scores) and the
lean-render tests hold. No numba kernel is added and nothing uses fastmath.
Memory: the pump gain is made a stretch at a time (65,536 samples) like the
send sums; a sweep holds only its span; the `fx` stem is one stem more (107
MB stereo for H) and only when a transition is asked for.

### Decisions for the artist

1. **The patches are few and named by sound**, not the synths' parameters;
   the filter is the only raw knob (cutoff, resonance, envelope). Envelopes
   (attack, release) and oscillator mixes could be next.
2. **A person's cutoff replaces the band's brightness** for that synth: the
   knob a person turned wins.
3. **Sidechain by preset or numbers**, keyed on the kick the drum player
   really plays (no kick in a verse: no pump there), or on every beat.
4. **Transitions are sound, not arrangement**: they don't change which
   players play or the section's length (the arrangement's work); a roll
   takes the snare's place in its bars.
5. **The kit is a sound**: an acoustic kit playing a drum machine's pattern
   plays it as a drummer would (with its own touch).
6. Exporting the key track as a muted MIDI track (for a producer's own
   sidechain) is left for later.

## A style's own sound, and the dub desk

House and dub (docs/STYLES.md, "House and dub") bring sound design of their
own, the program's, under a person's:

- **A style's sound** (`StyleDef.sound`; `sound.program_players`,
  `merged_players`): house's drum machine on its 909, a classic pump on the
  pad and a subtle one on the synth bass, the stabs and the pluck. A
  person's `sound.*` and `mix.<player>.*` sit over it path by path;
  `/api/sound` and a record's "was" show it as the program's. To take a pump
  away: the preset **off** (depth 0: no pump, and no triggers for it); a kit:
  choose another.
- **A style's transitions** (`sound.style_transitions`), made straight into
  the score, never into the person's table: a drop (`Style.drop`) gets a
  riser over the breakdown's last two bars, a snare roll over its last one
  (two when the breakdown is eight bars or more) and the band's low-pass
  **opening** across the whole breakdown; house opens the same filter across
  an intro. A person's transition at that boundary replaces the style's;
  **false** there silences both.
- **The desk's throws** (`Score.sound["throws"]`, from the arranger's desk:
  songbird/idioms.py `dubbed`; `sound.thrown`): each its part, its window in
  seconds, and for an echo its time, feedback and level. The mix
  (`Design.throw`) cuts the window from the part's channel while it is in
  hand (the singer's from its bus at the end) and adds what `synth/dub.py`
  returns: a tape echo (the window again at its time, each repeat darker and
  saturated, to 50 dB down) or a spring tank's splash, into the band and a
  little into its send to the room (the singer's beside its bus). A
  section's preview keeps the throws whose windows it plays. The stems stay
  dry.
