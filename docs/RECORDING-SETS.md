# Recording sets

*Made by `tools/recording_sets.py` (2026-09-26), for singing v2. The sets themselves are in `tools/sets/h-now-its-by-you.json`.*

Singers are asked to sing one of six sets: each is the whole song, three or four verses, its refrains, the bridge and the tag, in one of the song's own shapes and within the bank's rules. Between them the sets put in front of singers the words and verses the learned voice says worst, so that singers' takes are the data for making every word legible. The singers never hear that: each set's line for them only says what its verses are about.

## The sets

| Set | Verses, in order | Refrains between the first and last | Couplets | Bridge | Tag | Length |
|---|---|---|---|---|---|---|
| a | bell (belfry), probe, screen | so (who wrote), kept (who kept) | due, true, blue, canon | canon (border, coal, cold) | la | 3:40 |
| b | milk, hall, lullaby (thirty) | so (who wrote), swear (who made) | take, sang, due, canon | canon (desert, coal, dark) | loo | 3:40 |
| c | ink (monk, ninetyodd), tape (trunk by the bed), skip | go (who heard), stuck (who kept) | true, blue, take, canon | canon (mountain, light, cold) | oo | 3:40 |
| d | box, trench, sample (boy, him) | window (who sang) | sang, due, canon | canon (water, spark, dark) + coat | la | 3:40 |
| e | carve (wife's), wax (Sunday), kids | even (who wrote) | true, blue, canon | canon (border, light, cold) + given | loo | 3:40 |
| f | shell, shepherd (goatherd, goats), parrot, bird (linnet, spring) | never (who heard) | take, sang, canon | canon (desert, spark, dark) | oo | 3:40 |

What each set tells singers:

- **a**: Verses about the church bells, a space probe and a screen; the refrain the artist wrote and another way into the refrain
- **b**: Verses about the milk round, a dance hall and a lullaby; the refrain the artist wrote and another way into the refrain
- **c**: Verses about a letter in a drawer, an old tape and a skipping rope; other ways into the refrain
- **d**: Verses about a music box, the trenches and a sample; another way into the refrain and the bridge's second verse, the coat
- **e**: Verses about a gravestone, a wax record and childhood; another way into the refrain and the bridge's second verse, given
- **f**: Verses about shelling peas, a shepherd, a parrot and a songbird; another way into the refrain

Every set lasts 3:40 with a two-bar turn between its sung sections, at 96 BPM (the seed's rendition is 2:30, with two turns): nine sung sections each, where three verses, three refrains, the bridge and the tag would be eight (3:15). The rules and what the sets must hold add the ninth:

- The first and last refrains of a song always sing the song's own head (knows), and another head at most once a song, so the other heads can only go in the refrains between. Nine of them (the seven others once, the artist's so twice) take three sets with four refrains.
- The bridge's extra stanzas, coat and given, can only follow the canon's, so two sets sing two bridge sections.
- The words the voice surely says wrong, and the verses it gets clearly wrong, take 19 verses, so the last set sings four.

Singers can record one section at a time, so no one need sing a whole set at once.

## What the learned voice says worst

The default learned voice sang every entry of the bank dry, at the seed's key and tempo, one section at a time: all 38 verses with every word each slot can take, all nine refrain heads with every question each can ask, the six couplets, the three bridge stanzas and the three tag syllables, 141 ways in all, each three times with the voice's own chance (seeds 1-3). Whisper base.en, never shown the lyric, heard each; a homophone (quay and key), a number written as digits, or a compound heard as two words counted as heard. Over 14,778 sung words, 10% were misheard (a word error rate of 11%).

**Sounds.** A word with one of these sounds in it was misheard more often than the 10% of all words:

| Sound | Misheard | Words it was in, misheard |
|---|---|---|
| p | 23% of 648 | put, penny, wept, passed, rope, page |
| g (go) | 21% of 321 | go, grow, grave, grows, gray, gun |
| ire (fire) | 19% of 48 | wire, fire, choir |
| a (cat) | 16% of 822 | hadn't, sang, passed, cannon, band, laughed |
| k | 16% of 1,005 | ink, record, coat, disc, cannon, counting |
| h | 16% of 888 | hummed, humming, hadn't, hum, who'd, hiss |
| j | 15% of 72 | page, jeer, banjo |
| o (go) | 14% of 1,371 | old, go, grow, though, low, coat |

The best said: oy 0%, sh 1%, y 3%, o (hot) 4%, th (thin) 4%. Of the 25 words the voice surely says wrong (below), 20 have one of the sounds above, so the sets that hold those words hold the sounds too.

**Words.** 91 words were misheard at least half the times they were sung (three hearings or more). These 25 were misheard at least nine times in ten, over six hearings or more (sung two ways, or in two places): the voice surely says them wrong.

| Word | Misheard | Heard as |
|---|---|---|
| hummed | 36 of 36 | hung, honed |
| put | 18 of 18 | hooded, who'd |
| grow | 18 of 18 | roll |
| hum | 15 of 15 | hold, hung |
| ink | 12 of 12 | ganged, aint |
| who'd | 12 of 12 | who |
| low | 12 of 12 | below |
| record | 12 of 12 | rug, gone |
| dies | 12 of 12 | ties, dries |
| lit | 9 of 9 | only |
| wept | 9 of 9 | out, it |
| disc | 9 of 9 | is, did |
| cannon | 9 of 9 | and, in |
| ruined | 9 of 9 | and |
| hiss | 9 of 9 | hearse, piece |
| counting | 9 of 9 | in |
| rope | 9 of 9 | row |
| grave | 9 of 9 | rain, train |
| woke | 9 of 9 | a, wore |
| belfry | 6 of 6 | free |
| peas | 6 of 6 | piece |
| repeat | 6 of 6 | ready, ruby |
| ale | 6 of 6 | eil, eel |
| parrot | 6 of 6 | bear, it |
| coal | 6 of 6 | cold |

**Verses.** The verses' median word error rate is 11%; these 10 are clearly high (1.5 times that or more): trench 23%, screen 22%, milk 21%, kids 21%, hall 20%, ink 20%, probe 19%, lullaby 19%, bell 19%, box 18%. The best heard: ship 3%, fiddle 4%, deaf 5%, wire 5%, ring 5%.

**Refrains and bridges.** Heads: kept 18%, swear 17%, go 9%, so 6%, stuck 6%, window 4%, even 3%, knows 1%, never 0%. Couplets: due 14%, true 11%, blue 9%, take 2%, sang 0%. Bridge stanzas: canon 6%, coat 10%, given 4%. In the last refrain's couplet, old (it's old and it's new) was misheard 31 times in 36, most often as so; in the bridge, dies as ties and coal as cold. The tag's loo and oo aren't words, so Whisper never heard them as sung; la it heard.

## How the sets were chosen

- **Must hold (35):** every word surely misheard (above) and every verse clearly high. All 35 are held at least once. The worst would ideally be held twice, but the verses that hold them fill all 19 verse places the six sets have, so only 4 of 30 are, in two sets or more: hummed, put, coal, dies.
- **Should hold (66):** every other word misheard at least half the times it was sung, weighed by how often it is misheard and how often the song sings it (a word one of three slot choices counts a third). 39 of them are held.
- **Heads:** every head at least once, the artist's so in sets a and b; the others worst heard first. **Couplets:** each three times, worst heard first. **Bridges:** the canon in every set, coat in d, given in e; the canon's slot words and the refrain's question, while and then words are the most misheard the rules leave free, then the least sung so far. **Tag:** la, loo and oo in turn.
- **Verses:** chosen together: each set in turn takes the verses and slot words that add most, then any single verse of any set is swapped for whatever adds most, until nothing does. Every set's verses keep the bank's rules (checked with `arrange.held_problem`, with and without the turns). A verse keeps its own first slot words unless another one is misheard. Each set sings its easier verses first where the rules leave the order free (a verse that rhymes another way or runs a line on, a rare one, or a wordy one counts as harder). The sets with the most in them come first: set a holds the most.

## Left out

Six sets can't hold everything. These 27 words, each misheard at least half the times it was sung but less surely, or one of a slot's choices, aren't in any set (the verse that sings each is in brackets): buries (wakes), child's (carve), cook (ship), cope (soap), door (deaf), eight (wall), firm's (soap), hadn't (mouth), harbor (boat), jeer (terrace), meet (boat), Monday (wax/nurse), mothers (tongue/terrace), next (deaf), nun (mind/ink), others (mine), painted (wall), peddler (mouth), pit's (mine), postman (milk), sprayed (wall), squall (boat), starling (bird), tinker (mouth), twenty (tongue), violets (mouth), wakes (wakes).

A seventh set, if one is wanted, would start from the verses that sing most of them: mouth (4), boat (3), wall (3), tongue (2), mine (2), wakes (2).

## Doubts

- Whisper base.en is a proxy for a listener, and a harsh one on singing; it knows nothing of the lyric, so a rare word (belfry, goatherd, squall) is misheard partly for being rare.
- Three hearings of a word sung once are few: the should-hold words are less certain than the must-hold ones, which is why they weigh less.
- The voice was heard dry. In the full mix the band covers some consonants further.
- Every set lasts 3:40, not three minutes (above).

## Running it again

    uv run python tools/recording_sets.py measure    # sing and hear it all (renders/sets/, 4 minutes)
    uv run python tools/recording_sets.py choose     # write tools/sets/h-now-its-by-you.json
    uv run python tools/recording_sets.py report     # write this page
