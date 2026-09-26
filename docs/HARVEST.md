# What the harvest reads, and what it becomes

A machine sings in its own voice, read from its context (principle 4) and
reduced so that nothing identifying leaves it (principle 8). This is the
audit: every source the program reads, what it keeps, and what that drives.
The code is `songbird/harvest.py` (reading and reducing) and
`songbird/variation.py` (turning the numbers into music); each signal is one
small function whose docstring says the same as its entry here.

See it for yourself:

```
uv run songbird harvest --show            # read this machine, cache it, print exactly what is kept
uv run songbird harvest --show --without words hand
```

## The rules

- Each signal is read by one function and collapsed there to a few coarse
  numbers. File names, paths, document text, pictures and keystrokes never
  leave that function; they are never printed, logged, cached or written.
- The reductions are many-to-one: every number is bucketed (quarter steps,
  tenths, twentieths), so a voice can't be turned back into what it was read
  from.
- Every signal can be left out. A missing signal is neutral: every decision
  that would have read it keeps the parent's value, so a locked-down machine
  still sings, closer to its parent.
- The voice is cached in `~/.songbird/voice.json` (or `$SONGBIRD_HOME`),
  holding only the reduced numbers, a salt, a hash and which signals are left
  out. It stays the same until you harvest again.
- Typing is only ever timed when you run `songbird harvest` yourself at a
  terminal and choose to type the line it shows. Never in the background,
  never during a render.
- Files, documents and pictures are only read by `songbird harvest`. A
  render as this machine (`--machine here`) before any harvest reads only its
  languages, its size and its screen's appearance (dark mode and accent
  colour), says so, and caches that; the next `songbird harvest` reads the
  rest, keeping the same singer.
- Nothing goes over the network.

## The salt and the hash

The first harvest draws a salt: eight random bytes from the operating
system, not derived from anything. The voice's hash is
`sha256("songbird-voice|" + salt)`, first 16 hex digits. It seeds the drift
field (`songbird/drift.py`) and the singer's body (register, vocal tract,
mouth, vibrato rate, grain) and habits (whether it likes an intro, a turn, a
tag). Because it comes from the salt alone, the hash says nothing about the
signals (a hash of a few coarse numbers could be reversed by trying them
all), two machines that read the same still sing as two people, and a later
`--refresh` moves the traits the signals give without changing who is
singing. `--new-voice` draws a new salt.

## The signals

### tongue: languages and keyboard

Reads the system's preferred languages and region (on macOS the first two of
`defaults read -g AppleLanguages` and `defaults read -g AppleLocale`), the
first of the `LC_ALL`, `LC_MESSAGES`, `LANG` environment variables that is
set, and the keyboard layout's name (macOS `defaults read com.apple.HIToolbox
AppleCurrentKeyboardLayoutInputSourceID`, Linux `setxkbmap -query`, Windows
the active layout's language id).

Keeps one language group, by vote (a tie goes to the system's own language):
`english`, `germanic`, `celtic`, `romance`, `slavic`, `west_asian`,
`south_asian`, `east_asian` or `other`, and the mode family the group sings
in: `folk` (ionian, mixolydian, dorian, aeolian; home ionian) for English,
Celtic, South Asian and other; `bright` (lydian, ionian, mixolydian; home
ionian) for Germanic, Romance and East Asian; `dark` (ionian, dorian,
aeolian, phrygian; home aeolian) for Slavic and West Asian. The year's
drift moves a machine through its family: for H a folk or bright machine
sings ionian most years and mixolydian some, a dark one aeolian most years
and the seed's own ionian some. The tables are `harvest.LANGUAGES`, `FAMILY_OF`
and `MODE_FAMILIES`, and they are a stylization for the artist to revisit.

Drives which modes the tune is realized in (only modes in which every chord
of the song stays a major or minor triad: for H's I IV V vi, ionian,
mixolydian and aeolian). The group is also recorded as the phoneme inventory
a future singer will take its vowels from; today's singer doesn't read it.

### machine: size and uptime

Reads the number of CPU cores, the installed memory and the time since the
machine started (macOS `sysctl -n kern.boottime`, Linux `/proc/uptime`,
Windows `GetTickCount64`).

Keeps a bucket for each: cores up to 2, 4, 8, 16 or more (0 to 1 in
quarters); memory up to 4, 8, 16, 32, 64 GB or more (0 to 1 in fifths);
uptime under a day, under a week, or longer (0, 0.5, 1). Uptime is read
again at every render: it is how long the machine has gone without rest, not
what the machine is.

Drives density (cores and memory): how busy the accompaniment pattern is
(and, for the instruments, how many layers). Tiredness (uptime): a little
more breath and roughness in the voice.

### ages: how old the files are

Reads the modification time of up to 50,000 files under the home directory,
at most eight folders deep, for at most four seconds. Never entered: hidden
files and folders, `Library`, `Applications`, `AppData`, `OneDrive`, iCloud
Drive, code-dependency and build folders (`node_modules`, `venv`, `build`,
`dist`, `target`, ...), packages (`.app`, `.photoslibrary`, ...), symbolic
links, and the home's own `Pictures`, `Movies`, `Music` and `Videos`. The
home's `Desktop`, `Documents` and `Downloads` are included (macOS will ask
you first). A file's name is only used to decide where to walk next; only
its age is counted.

Keeps the median of log10(age in days) and the interquartile range of those
logs, each in quarter steps (a median of 2.5 is about ten months).

Drives pace (young files: a brisker tempo), range (a wide spread of ages: a
tempo that wanders further with the drift) and wear (old files: a breathier,
rougher voice, and a lyric that leans to older verses).

### colour: the screen

Reads a desktop picture: one you name with `--wallpaper FILE`, or on Linux
(GNOME) and Windows the one the system's settings name, shrunk to 64 pixels
(macOS `sips`, into a temporary folder deleted at once, or Pillow where it
happens to be installed). Without one, whether the screen is
in dark mode and its accent colour (macOS `AppleInterfaceStyle` and
`AppleAccentColor`, GNOME `color-scheme` and `accent-color`, Windows
`AppsUseLightTheme`). macOS keeps its desktop picture in a database under
`Library`, which the harvest never opens.

Keeps brightness (0 to 1 in quarters) and how the colour divides into warm
(reds, oranges, yellows), green and cool (blues, purples), in quarters that
sum to 1.

Drives the singer's brightness (a light screen, a brighter tilt and a more
pressed voice) and the lyric's mood (a light screen leans light, a dark one
dark, a warm one tender).

### words: the person's common words

Reads the text of up to 600 plain-text, Markdown, RTF, TeX, Org, reST, HTML,
Word (`.docx`) and OpenDocument (`.odt`) files in `Documents` and `Desktop`,
256 KB of each at most, 30 MB and six seconds in all.

In memory only, then discarded: the lowercase words of three letters or more
(a capitalized word, usually a name, never counts), kept only if they appear
in at least two documents, are in the CMU Pronouncing Dictionary and aren't
function words; of those, the 200 most frequent.

Keeps, for eight public word lists (`harvest.THEMES`: sea, fire, machines,
earth, home, town, music, past), how much of each list those 200 words cover
(distinct words, not counts, and as a fraction of the list, so a short list
and a long one count alike), as shares summing to 1 in twentieths; an era
lean (new-fashioned words against old-fashioned ones, `harvest.ERA`, in
quarters); and richness (the moving-average type-token ratio of all the
text, 0.45 to 0.75 mapped onto 0 to 1, in tenths). No word is kept, and no mood is read: what a person writes about is
not the song's business.

Drives the lyric's vocabulary (the song's own words in the themes the
person's words favour, so only words the song already has ever appear), its
era, its appetite for rare verses, and the verse count (a rich vocabulary
tells longer stories).

### hand: the rhythm of a typed line

Reads, only when you run `songbird harvest` at a terminal and choose to, the
time between your keys as you type `who made this song? nobody knows`. Each
key is answered with a dot; the keys themselves are never kept. Esc skips.
Pauses over 1.5 seconds (thinking) are dropped.

Keeps the mean interval (20 ms steps), its coefficient of variation (tenths)
and its skewness (quarters). A typed sample is kept until you type again.

Drives where the singer sits against the beat (quick hands ahead, slow ones
behind, up to 0.08 of a beat), rubato (uneven hands: looser playing, a
longer ritardando, deeper vibrato), swing (a skewed rhythm, for the players)
and pace, and a little of the singer's vibrato rate, glides and scoops.

### room: not yet

A microphone needs a library the program doesn't have, so the room isn't
read and every machine's room is its parent's. The plan: a clap or a
two-second capture, reduced at once to a reverberation time (Schroeder
integration) and a five-band tonal profile, the capture deleted. The made-up
machines below carry a room, so rooms can be heard already.

## What the numbers become

`variation.character()` reads the signals as a few traits, each -1 to 1
with 0 typical; a trait the machine gave no signal for is unknown, and
whatever reads only unknown traits keeps the parent's value.

| Trait | From | Moves |
| --- | --- | --- |
| pace | (2.3 - median age) / 1.2, and the hand's speed | tempo, ritardando |
| range | spread of ages - 1 | how far the tempo drifts |
| wear | median age - 2.5 | breath, glottal shape, jitter, wander, shimmer; the band's wear; the recording's wear; older lyric era |
| density | cores + memory - 1 | the band's density and the harp's picking; a busy machine leans to the strum |
| tired | 2 uptime - 1 | breath, jitter, the band's and the recording's wear |
| brightness | 2 brightness - 1 | the singer's tilt and glottal shape, the band's brightness, the record's tilt, mood |
| warmth | warm - cool | the band's brightness (a warm screen, a softer band), the mix's width (a warm one, a little narrower), tender mood |
| lay | (220 ms - mean interval) / 120 | where the singer sits against the beat, vibrato rate, glide, scoop |
| rubato | (variation - 0.45) / 0.3 | humanize, ritardando, vibrato depth |
| swing | (skew - 1) / 1.5 | the band's swing, which the singer's time follows too |
| richness | 2 richness - 1 | verse count, rarity appetite, the band's ornament |
| era, themes | the words | lyric era, vocabulary |
| family, inventory | the tongue | mode, (vowels) |
| identity | the salt | the singer's register, tract, mouth, vibrato rate, grain; habits; comfortable key; the band's maker, its instruments' size (with the singer's build), each instrument's gain, its pattern and lead, its arc; the mix's space, intimacy, width, the voice's place over the band, the room's predelay |
| room | the room | the mix's rt60 and tone, and its predelay (a big room answers later) |

The whole table of knobs, with spans and bounds, is `variation.KNOBS`; the
choices a number can't make (mode, form, accompaniment, the band's pattern
and lead, choir, the room, the lyric's leanings) are `variation.DECISIONS`.
The band's rows are in [BAND.md](BAND.md), the mix's in [MIX.md](MIX.md).

## What a rendition carries

A render's record (`renders/<name>.json`) holds the voice (the reduced
numbers, the salt and the hash), the drift vector, the parameters chosen
and, where the words came from the bank, the words sung (with a lyric
sheet beside it); only the bank's words ever appear there. The parameters
include the tune's variants and the words the lineage holds, and who made
the rendition (the hash's first 12 digits) and when, so a child on the same
machine can tell which of its clocks have turned since (docs/EVOLUTION.md).
The seed packet's manifest (milestone 6) should carry less: the parameters
(what can be heard anyway) and the hash, not the voice block.

## Made-up machines

`songbird harvest --fictional NAME [--out FILE]` makes a plausible machine,
drawn from the ranges above and reduced the same way, the same one every
time for a name; `--machine fictional:NAME` sings as it. They are for
hearing two machines side by side without two computers.
