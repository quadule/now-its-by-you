# Open questions

*Engineering and design questions left open, gathered from the pages they were raised on. Each says when.*

## Running a rendition (from docs/RUNNING-THE-SONG.md, September 27, 2026)

- **Fetching uv for the person.** The bootstrap could offer to install uv
  when Python is too old, which would make step 2 disappear; but that runs an
  installer script from the internet, a bigger thing to ask than fetching
  libraries. Only with the artist's yes.
- **Carrying the libraries.** A file with wheels inside would need no
  network, but would be about 100 MB larger and tied to one platform
  (docs/PACKET.md already weighed this and said no).
- **A double-click launcher.** A `.command` (macOS) or `.bat` (Windows)
  beside the file would spare the terminal, but it can't travel inside the
  FLAC, and a downloaded script is itself something to trust. The
  songbird.quadule.com page could offer one per platform.
- **Not tried here:** Windows and Linux. The bootstrap and the harvest have
  code for both; nobody has run a rendition's studio on them yet.

## How the song evolves (from docs/EVOLUTION.md, September 26, 2026)

- **How fast.** The rates are the constants at the top of `songbird/evolve.py`. Now: about half a variant
  and a third of a word swap a hand-off; one machine's own song changes its tune two to four times a year.
- **Fa and ti.** H's grace notes, neighbour notes, anticipations and moved notes keep to its five notes;
  passing tones (an 80 ms slide through fa or ti across a third) and mordents and turns (a 75 ms step) may
  touch them. Banning them would leave H's passing tones to mi-do and do-la, and its mordents and turns to
  notes with a scale step on both sides.
- **The seed's refrain.** A child of the seed sings other couplets before its last refrain (the bank's rule
  for drawn words), so the first hand-off always changes those couplets. Holding the seed's canon until a
  swap changes it is the alternative.
- **Anticipation** is a pitch anticipation, the syllable still on its beat (the stress guard forbids moving a
  stressed syllable); a true rhythmic anticipation, the syllable an eighth early, would need that guard
  relaxed.
- **A machine that ornaments a lot**, singing its own renditions for years, can fill the song's room for
  variants (about fourteen notes in H). The second learning clock and the crowding term keep it from
  going further; a lower cap would keep such a machine plainer.
- **The form still flips back within a week now and then** (the season's form choice has no hold), and the
  words follow it: a verse can come and go within days a couple of times in three years. Holding the form
  as the band's pattern is held would stop it.
