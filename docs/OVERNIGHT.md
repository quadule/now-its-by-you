# Overnight, 2026-09-26: what changed, what to hear, what to reconsider

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

This file is updated through the night; the newest state is at the top of each section.

## Listen first

(filled in as the work lands)

## What changed

### The seed packet: the song file carries its program (landed)

A rendition is now one file, `render --pack`: a FLAC that plays anywhere and is also a zip of the
program, the song, its record and its words. `python3 song.flac new` sets the program up (asking
first) and sings a new version on that computer, as the file's child and a packet in turn.
docs/PACKET.md has the details and what was checked.

### The voice

(in progress: the learned voice trained only on our own house singers; a delivery agent; a
vocoder agent)

**The learned voice is ready to become the default:**
- *Clearer in the mix:* in H's full mix, Whisper mishears 15.1% of its words, against 34.7% for the
  formant singer. This is the ElevenLabs-voiced benchmark, which never ships; the house model is
  the one that would.
- *Same balance:* it sits where the formant singer did (voice bus -14.0 vs -13.7 LUFS, clarity
  +8.4 vs +9.0 dB), so the mix needs no retuning.
- *A voice per machine:* each machine gets a singer of its own, a blend of the learned singers,
  inherited like everything else.
- *The bridge's lineage choir sings in the voices of the earlier versions:* the record now
  remembers them, the parent's first. Before, the choir was stand-ins.

Measured before the night's work, as automatic naturalness (UTMOS: a speech-trained predictor, so
a rough guide on singing):

| Voice | Score |
|---|---|
| the formant singer | 1.47 |
| the first learned model | 1.68 |
| the learned benchmark | 1.95 |
| SoulX, the teacher, on the same song | 2.4 to 2.7 |

Our vocoder alone costs about 0.25 of that; the model and the delivery cost the rest.

### Genres and arrangement

(in progress: a style agent, and two agents building new instruments)

### Evolution, the studio, the sing page

(in progress: the drift of melody and words, the studio, the shareable sing-along page)

## To reconsider

Each item names the choice, why it was made, and how to undo it.

1. **The packet is a polyglot: FLAC plus an appended zip.**
   - *Why:* players, unzip tools and Python all read it.
   - *The cost:* the FLAC reference tools (`flac -t`, `flac -d`) report the appended archive as an
     error after decoding every sample, and macOS `ditto` won't unzip it.
   - *The alternative:* the plan's own fallback, the archive in a FLAC metadata block, which is
     strictly valid FLAC but no longer unzippable or runnable.
2. **A packet run fetches its dependencies.** The first run asks, then fetches them from PyPI
   (~150 MB) into ~/.songbird. Carrying them inside the file would tie it to one platform and add
   about 100 MB.
