# Social cut: plan v3

Vertical 1080x1920, 60 fps, about 38 s, Instagram Reels and X. Subject: how the song changes as it is
passed on, and what is passed on. Everything sits in y 250 to 1450 (the Reels caption and buttons cover the
bottom).

## The picture

A stack of sung lines, one row per generation, all singing the same bridge line, "hand it along like a coal
from the fire":

- **Tempo as length.** Each row is drawn on one shared axis of seconds, not stretched to fit, so the 96 BPM
  release and the 46 BPM lullaby six generations later differ visibly in length, about two to one.
- **Key as height.** Pitch is drawn as sung, not from the key's home note, so the rows step up from D to
  E-flat to E and settle.
- **The ancestors' harmony.** Under each lead line, its choir parts' real pitches as hairlines: one more
  voice per generation (the singers of the versions before it), 3 under the release up to 6.
- **What is learned is carried down.** The grace note on "like", learned in generation 1, is drawn as a notch
  in red on the row where it first appears and in ink on every row after, in the same column. Generation 6
  adds a second, on "it's". Red always means new in this generation, ink means inherited. Words follow the
  same rule.
- The coal: the red point on the row being heard.

## Words on screen

- The sung line (above y 1450).
- At each row's end, data only: the version's real date (November 29, 2027) and its machine's id.
- At most one line in the program's own words from its change log (gen 1: "a grace note from below on
  'like'").
- At most one authored line, early, for the artist to word (e.g. "Every computer sings it differently").
- End: the title and now.itsby.you on clean paper.

## Beats (about 38 s)

| Time | Heard | Seen |
|---|---|---|
| 0 to 2.5 s | the release and generation 6 singing "hand it along", cut hard on a word | two rows, one twice as long with six voices under it, filling the frame from the first frame |
| 2.5 to 9 s | the release, bridge lines 1 to 2 | row 0 drawn as it is sung |
| 9 to 15 s | four styles, a half-line each, the same notes | thin rows off row 0, the same shape; style names small |
| 15 to 31 s | generations 1 to 6, each the same bridge line | a new row each, to scale; one more voice under it; the notch carried down; date and machine at the row end |
| 31 to 36 s | generation 6, "and now it's by you" | the stack holds, the coal on an empty seventh row |
| 36 to 38 s | ring | title, now.itsby.you |

## Before building

- **The chain.** All six generations so far were made on this computer at dates a year apart, so they are
  one machine ageing, not a hand-over. Truer: pass the file across the artist's own computers, each rendering
  from the last on its own day (`songbird render --parent <last file> --machine here`), with each machine's
  id shown. The other option is to keep this computer and show it as "the same computer, a year apart".
- **The root's id.** Generation 1's parent is the release FLAC's id, 07ac74fbd4eb; the replay used for timing
  (04fbc35246d3) and the film's awards draft (eb8fb05eb2bb) are other files. Draw 07ac74fbd4eb.
