# Learning the song at the piano (2026-09-29)

A page for learning "Now It's by You" on a piano or a MIDI keyboard, note for note as the released version
sings it: falling notes over a keyboard, the chord above, the words below. It is dev-only for now: it isn't
part of the public site and nothing deploys it.

## Running it

    python3 -m http.server 8770 --bind 127.0.0.1 --directory web
    open http://127.0.0.1:8770/piano/

(or `piano` in .claude/launch.json). It serves `web/` rather than `web/piano/` so the page can use the
site's own `web/sing/page/identity.css` instead of a third copy of it. Chrome, Edge and Firefox have Web
MIDI; Safari doesn't, so there the page plays from the screen's keys and the computer's.

To make the score again, after a new release:

    uv run python tools/piano_score.py --check     # renders/review/contest.flac -> web/piano/score.json

## What it does

- **Input**: a MIDI keyboard (Connect, then pick one or take every one; the sustain pedal works for the
  page's own sound), the keys drawn on the screen (click or touch, several fingers at once, softer toward
  the top of a key), or the computer's keys: `A W S E D F T G Y H U J K O L P ; '` from C4, `Z` and `X`
  an octave down or up. MIDI out can send the score to the keyboard's own sound instead of the page's.
- **Display**: the right hand (the tune) in amber, the left in blue, falling onto the keyboard; the hand
  being practised full strength, the other dimmer. Bar numbers, section names and chord names on the roll,
  note names on the notes, each sung note's syllable beside it. The chord now and next above; the line
  being sung below, lit syllable by syllable, and the next line under it.
- **Speed** 25% to 125%, in 5% steps. The last phrase slows as it's sung (the rendition's ritardando);
  "slow down at the end" can turn that off.
- **Key**: -6 to +6 semitones, with the key's name, and every chord and note name spelt for it.
- **Your keyboard**: say how many keys it has (25, 37, 49, 61, 88; a C-to-C board's lowest C can be moved
  an octave either way) or press "Learn it" and play its lowest key, then its highest. The page then draws
  only those keys and moves each hand by whole octaves so the song fits: fewest notes off the keys first,
  then the hands kept apart (the left below the right), then as near as written. "Fit" does it again after
  a nudge; changing the key or the left-hand part refits. A note still off the keys is moved an octave in
  and outlined. On 37 keys (C3 to C6) every left-hand part fits in every key with nothing moved (both hands
  go up an octave in the song's own key); on 25 keys most keys fit, a few move a handful of notes. "Any
  octave counts" accepts the right note in any octave, for a keyboard's own octave buttons.
- **Hands**: practise the right, the left, both, or just listen. The left hand can be the band's bass line
  (an octave up), root and fifth, broken chords (root, fifth, octave, fifth) or block chords. Each hand has
  a volume and a mute; the other hand plays along (or not), and the practised hand can sound too, as a guide.
- **Practice**: loop any section (with its pickup) or bars A to B ("A here" and "B here" set them from
  where you are), a bar's count-in, a metronome, and "wait for me", which stops at each note of the hand
  being practised until it's played. Right, missed and wrong notes are counted (from the first key played;
  Start resets the count), and notes turn green when played or are outlined red when missed.
- **Shortcuts**: space plays and pauses; R or Home back to the start (of the loop); left and right a bar;
  up and down speed; `[` `]` key; `1` `2` `3` `0` right, left, both, listen; `N` wait, `M` metronome,
  `C` count-in, `B` loop on and off. The settings are remembered in the browser (localStorage).
- Light and dark follow the system, or can be chosen; the roll is the site's stage, dark in both.

## How the score was derived

`tools/piano_score.py` (its docstring has the details). The release, `renders/review/contest.flac`, is a
packet (docs/PACKET.md): it carries the program that sang it, the genome, the render record and the words.
The exporter unzips the packet's own program (checked against the record's `program_sha256`) and imports
it ahead of this tree's `songbird/`, so later changes can't move a note. Then it lays the score again as
`songbird render --replay` does (and `tools/sing_site.py` `seed_words`): `realize()` with the record's
params, words and phrasings, then `variation.lay`. It trusts the score only if its words come out exactly as
the packet's `lyrics.txt`.

The phrasing pushes and pulls every sung note off the grid, so the exporter takes the grid itself: it
listens in on `songbird.band.plan` (handed the band's Context: the sections, the chord under every beat,
the tune note by note, all in grid units) and `songbird.band.arrange` (handed `realize()`'s melody entries
with their syllables). The band's own notes (the bass, the turns' quotes) are in seconds; they are put back
on the grid through the rendition's clock, inverted, and snapped to a sixteenth.

- **Key, tempo, form**: D major (the tune is major pentatonic, D E F# A B, with the chords' G and C#),
  4/4 at 96 to the quarter, 58 bars: intro (4), verse (8), refrain (8), turn (2), verse, refrain, turn,
  bridge (8), refrain, tag (2). The last phrase (the tag) slows by the record's ritardando, 0.27.
- **Right hand**: the tune as sung. In the intro nobody sings: the whistle plays the tune an octave up. In
  the turns the fiddle, then the lute, quote the refrain's third line, an octave up too. The score has them
  at the sung register, with `by` and `octave` saying who plays them and where.
- **Chords**: I, IV, V and vi, as the genome writes them per bar, split evenly through the bar, exactly as
  `songbird.band` lays them for the players.
- **Left hand**: the band has no keyboard (lute, guitar, harp, bass, fiddle, whistle, drum, drone), so the
  left hand is the bass line as the band plays it, or a part made from the chords.

`--check` holds the score up against the recording's audio (151.2 s):

| What | The recording | Moved by a semitone or more |
|---|---|---|
| Pitch classes against the score's notes | r = 0.90 | at best 0.72 |
| Chord spans whose best-fitting triad is the score's chord | 87% of 89 | at most 2% |
| Sung notes whose pitch class is among the three strongest | 100% of 117 | at most 75% |
| Onsets' period (autocorrelation) | 0.624 s, 96.2 bpm | (the score: 0.625 s) |
| Onset strength on the score's beats, and halfway between | 16.3 and 3.3 | |

A key profile alone would call the recording A major: a major pentatonic tune's notes all sit in the key a
fifth above too. The chords (G and Bm are there, G# isn't) and the note-by-note checks settle it as D.

## What's where

| File | What |
|---|---|
| `tools/piano_score.py` | the exporter, and `--check` |
| `web/piano/score.json` | its output: tempo, ritardando, key, sections, chords, melody with syllables, lines, left-hand parts (in beats from the first bar line) |
| `web/piano/index.html`, `piano.css` | the page, on `web/sing/page/identity.css`'s tokens |
| `web/piano/piano.js` | the page's workings: clock, scheduler, judging, roll, MIDI, keys |
| `web/piano/sound.js` | the page's own piano-ish voice, click and room (Web Audio, no samples) |

`window.pianoPage` in the browser's console exposes the state and `noteOn(pitch, velocity, source)` for testing.

## Not yet

- The written tune, not how the singers phrased it: the lead's pushes, pulls and ornaments aren't in it.
- No staff notation.
- Hands are told apart by part, not by a split point on the keyboard: a note played counts for whichever
  practised hand has it there.
