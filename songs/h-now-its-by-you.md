# H. Now It's by You

*The best of. Striding 4/4 with a long-short-short lilt, D major pentatonic
(do re mi so la only), chords I, IV, V and vi, range low so to la. Four-line
verses of eleven syllables, AABB; the refrain is two couplets; the bridge is
sung by the lineage.*

A's question, answered the way B ends: nobody made it, and now it's by you.
The verses are A's vehicle ballad, one keeper per verse, each stitched from two
songs. The bridge is B's refrain, where every earlier voice in the song's
lineage joins in harmony to tell you to hand it along; the last refrain lands
on "now it's by you", and everyone sings its tune once more, without words.

> Who made this song? Nobody knows.
> It's yours while you sing it, and then it goes.
> It's nobody's making, it's old and it's new;
> by everyone, no one, and now it's by you.

The question turns each time the refrain comes round (the artist's idea):
**made**, then **sang**, then **owns** in the seed's three refrains; a form
with four puts **heard** before owns. The last refrain always asks who owns
it, and the next line answers: it's yours while you sing it.

> They saved it as numbers and sent it by wire,
> a flicker of light, and as quick as a fire.
> Each copy was perfect in every last part,
> but not one machine ever knew it by heart.

> The whole world was watching it all in a day,
> a million bright faces all lit the same way;
> they laughed and they wept, and they scrolled right along,
> but nobody hummed it; it wasn't a song.

**Bridge** (the lineage sings with the lead)

> Carry it over the water and wire,
> hand it along like a coal from the fire;
> it's nobody's making and everyone's own,
> it dies in the dark if you leave it alone.

**Tag** (everyone, on the tune of "by everyone, no one, and now it's by you")

> la la la la la la la la la la la.

**Form of the seed:** intro, verse (wire), refrain, turn, verse (screen),
refrain, turn, bridge, refrain, tag. A turn is two bars of the strings alone
(IV, V) so a singer can catch their breath. A version may also take a breath before each
refrain: the same two bars between a verse (or the bridge) and its refrain, an optional part of the form
(`breath?` in the genome's template, a section the band plays as a turn), off in the seed.

**Further seed verses**, for longer forms:

> A quiet man kept it alone in his head,
> so close and so safe that it never was said.
> It went where he went, and it slept where he slept;
> they buried it with him, the secret he kept.

> A girl wrote it down by a candle one night,
> in ink on a page, and she folded it tight.
> It lay in a drawer for a hundred-odd years;
> it speaks in a voice that now nobody hears.

> A sailor was humming it down by the quay;
> a girl selling oranges caught it for free.
> She hadn't his language, she hadn't his name;
> a mouth is enough, and she sang it the same.

**Template:** [someone] [kept, wrote, saved or showed] it [in a vehicle] [where or when] / [how the vehicle held it] / [how far or how long it went] / [what became of it]. AABB, eleven syllables a line (an unstressed pickup, three dactyls, a final stress), third person only: the song is "it", nobody is "I".

**Bank:** every verse and variation the program can draw on, with the words that swap and the rules for combining them, is in [h-bank.md](h-bank.md) for reading and under `bank` in the genome for the program; `uv run python -m songbird.bank songs/h-now-its-by-you.json` checks every way each line can be sung against the tune and the dictionary. A verse may rhyme ABAB or ABCB or run a phrase over a line break, at most one such verse per song and never the first.

## Notes

- **The artist's picks (2026-09-25).** H is the lead candidate: the chorus is
memorable and encapsulates the project. The wire and screen verses are the
favorites, so they open the seed; B's refrain quatrain ("Carry it over the
water and wire...") is another favorite and became the bridge. J's idea of
ending on the chorus's own tune without words survives as a two-bar tag,
shorter than J's four.
- **The turning question.** "Who {made|sang|heard|kept|wrote|owns} this song?"
in the genome: a fixed line may turn one word each time its block comes
round, in order, the last time always taking the last word. Authorship in six
words: making, singing, hearing, keeping, writing, owning. Three refrains ask
made, sang, owns; with four, heard comes before owns; kept and wrote only come
in with five or six. "Nobody knows" never changes.
- **The lineage choir.** The bridge and the tag are the sections where voices
from the song's lineage join in (`"choir": true` in the genome). Each takes a
harmony line against the melody from the chord underneath: the nearest chord
tone a third or more below, the nearest above, the root beneath, then the
same an octave down. The seed has no ancestors, so it sings its bridge alone;
each generation adds a voice, so you can hear how far a rendition has
travelled: a version's record carries the singers before it, up to six.
`songbird render --choir N` stands in N made-up singers.
- **The tune.** Each foot is a quarter and two eighths. Refrain lines 1 and 2
are a question and answer (open on so, closed on do); line 3 sits on la, the
top of the range; line 4 falls home so-mi-re-do. The verse is lower and
plainer: lines 2 and 4 share one melody. The bridge turns to the relative
minor (vi) with the first two lines starting on la with no pickup, climbs
back through I, and ends open, low on so over V, so the last refrain has
something to answer.
- **What gets refilled.** The verses, from the bank (or, with an LLM, from the
template), two to four per song in era order. The refrain keeps its shape and
varies only in its question word, its while/when/if and it goes/who knows/it
grows slots, chosen once per song, and the couplet each time round, canon
last. The bridge is always the canon, with one extra stanza (coat or given)
allowed after it in a long form; the tag sings one syllable, la, loo or oo.
The rules are in the bank.
- **Bank lines used.** Refrain: "Who made this song? Nobody knows" (A); "It's
yours while you sing it, and then it's gone" (A), bent to "then it goes";
"It's nobody's making" (B); "by everyone, no one, and now it's by you" (B).
Bridge: B's refrain, whole. Verses: B's wire with A's "not one machine ever
knew it by heart"; A's screen verse with B's "nobody hummed it; it wasn't a
song"; A's mind verse with C's "kept it alone in [his] head"; A's ink
couplet with B's drawer couplet; A's sailor and orange girl with C's "only a
mouth".
- **The bank.** Fifty-one verses, eight refrain couplets, eight refrain heads,
five bridges and three tag syllables, begun with the artist on September 25,
2026 and grown since, each checked against the tune: see [h-bank.md](h-bank.md). The artist's own lines
are the heard and owns refrains (now the true and take couplets) and the first
line of the kids verse.

**Quote** (2026-09-27): `quote` in the genome holds the first line of the
chorus of Daisy Bell (Harry Dacre, 1892; public domain), the first song a
computer sang (an IBM 7094 at Bell Labs, 1961) and the one HAL sings as he is
switched off, re-barred from its waltz into the song's 4/4: so mi do so, / la
ti do la / do so. It is never sung. When a rendition's intro is a quote
(`--arrange intro=quote`; docs/STYLES.md), the whistle plays it alone over the
drone in four bars before the song, the machine singer nodding to its
ancestor. The seed's own arrangement doesn't quote, so the guides the first
singers sang to kept their timing.
