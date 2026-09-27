# H. Now It's by You: the bank

Every verse, refrain couplet, bridge and tag syllable the song can draw on,
for reading. The same bank, syllabified and with its rules as data, is under
`bank` in [h-now-its-by-you.json](h-now-its-by-you.json); the seed
arrangement and the notes on the tune stay in
[h-now-its-by-you.md](h-now-its-by-you.md). Check every way each line can be
sung against the tune and the dictionary with

    uv run python -m songbird.bank songs/h-now-its-by-you.json

Each entry has a label to refer to it by, a rough year (or none, for a verse
that could be any time), a mood, its rhyme scheme and who wrote it. Words in
italics can swap for the ones listed under the entry; every swap keeps the
syllable count and the stress, and where a noun swaps, its pronouns follow.
Every line is eleven syllables, an unstressed pickup, three dactyls and a
final stress, except where the tune says otherwise: the refrain's first two
lines are eight and ten, and the bridge's first two are ten with no pickup.

## The refrain

> Who *made* this song? Nobody knows.
> It's yours *while* you sing it, and then *it goes*.
> It's nobody's making, it's old and it's new;
> by everyone, no one, and now it's by you.

Every refrain has words of its own. *Made* is the question: the first
refrain asks who made, wrote or sang it (whichever no head the song sings
asks as written, where it can), the last who owns it, and each refrain
between asks something else (made, sang, heard, kept or wrote), a different
word each time. *While* can be when or if, drawn afresh each time round. *It goes*
can be who knows or it grows, and each refrain ends its own way, so three
refrains sing all three.

Lines 1 and 2 are the refrain's head. The first and last refrains always
sing this one (**knows**), so the hook is heard first and last; a refrain
between may sing another head instead, each at most once a song:

**so** · by artist

> Who wrote this song? Nobody, so
> it's yours if you sing it and then who knows?

It asks who wrote it, says "if" and ends "who knows?", as written; no other
refrain in the same song ends "who knows", so the question comes as a
question.

These seven, the artist's pick of all of them (2026-09-26), turn "Nobody" the
same way or keep "Nobody knows" and turn the second line. Each asks whatever
question its refrain draws, but for swear (made) and kept (kept), as written:

**stuck** · by claude

> Who heard this song? Nobody, though
> it's stuck in your head, and it won't let go.

**even** · by claude

> Who sang this song? Nobody, though
> there's somebody singing it, even so.

**swear** · by claude

> Who made this song? Nobody, though
> you'd swear that you wrote it, the way it goes.

**kept** · by claude

> Who kept this song? Nobody, so
> it's kept by the singing, and on it goes.

**never** · by claude

> Who sang this song? Nobody knows,
> but once you have heard it, it never goes.

**window** · by claude

> Who kept this song? Nobody knows;
> it came in the window, the way it goes.

A refrain between the first and last sings any of the nine heads (the song's
own among them) about as often as another.

Lines 3 and 4 are one of these couplets, a different one each time round,
canon always last:

**canon** · by fable (A's question, B's answer)

> It's nobody's making, it's old and it's new;
> by everyone, no one, and now it's by you.

**true** · by artist

> It's nobody's making, it might not be true;
> but now that you know it, go make it from you.

**take** · by artist and fable

> It's yours for the taking, so take it, and do
> whatever you like, but leave some of you too.

**blue** · by fable

> It's nobody's making, it's out of the blue
> and goes back to nowhere unless it's through you.

**due** · by fable

> It's nobody's making, and nobody's due
> a penny for singing; so sing it right through.

**sang** · by fable

> It's nobody's making, and that much is true;
> but somebody sang it, and now it's by you.

## The verses

Grouped by when they happen, since the chosen verses are sung in era order,
earliest first; the verses with no year go anywhere.

### Old times, to 1900

**carve** · 1800 · dark · AABB · pairs with ink · by fable

> They carved the first line of it into a stone
> above a man's grave, in a churchyard, alone;
> the name's worn to nothing, the line's still cut clear,
> and anyone reading it has it by ear.

Swap *man's* for wife's or child's.

**ink** · 1800 · dark · AABB · pairs with carve · by fable (A's ink couplet, B's drawer couplet)

> A girl wrote it down by a candle one night,
> in ink on a page, and she folded it tight.
> It lay in a drawer for a hundredodd years;
> it speaks in a voice that now nobody hears.

Swap *girl* for boy, nun or monk, the pronouns following; *hundredodd* for thousandodd, sixtyodd or ninetyodd.

**mouth** · 1800 · plain · AABB · by fable (A's sailor and orange girl, C's 'only a mouth')

> A sailor was humming it down by the quay;
> a girl selling oranges caught it for free.
> She hadn't his language, she hadn't his name;
> a mouth is enough, and she sang it the same.

Swap *sailor* for soldier, tinker or peddler; *oranges* for newspapers or violets.

**boat** · 1850 · plain · AABB · by fable

> They sang it on deck as the harbor grew small,
> and sang it below through the sickness and squall;
> they landed with nothing, and no one to meet;
> by spring it was sung on the whole of the street.

**box** · 1850 · plain · AABB · by fable

> They pinned it on brass in a box with a key
> that played it for children who climbed on a knee;
> the comb's lost a tooth, and it's missing a pin;
> it plays it with gaps, and the children fill in.

**parrot** · 1850 · light · AABB · by fable
*A clone that can't make it its own.*

> A parrot had learned it, a line and a half,
> and sang it all day, and it made people laugh;
> the sailor's long dead, but it sings in his voice
> the line and a half, and it hasn't a choice.

Swap *sailor's* for soldier's.

**choir** · 1880 · plain · AABB · by claude

> A choir learned it once from a page on a stand,
> in somebody's handwriting, somebody's hand;
> the page had no name at the top or the end;
> they sang it, and folded it, sent to a friend.

**bell** · 1900 · plain · AABB · by fable

> A tower was ringing it out over town
> each evening, till someone had taken it down.
> The bells went for cannon, the tower for stone;
> the tune's in the streets now, and rings on its own.

Swap *tower* for steeple or belfry; *evening* for morning.

**wax** · 1900 · plain · AABB · pairs with sample · by fable

> They cut it in wax on a Tuesday in town;
> the needle went round and the record wore down.
> It kept the one slip where the singer went wrong,
> and everyone since sings the slip in the song.

Swap *Tuesday* for Monday, Friday or Sunday.

### The last hundred years

**trench** · 1916 · dark · ABAB · rare · enjambed · by fable
*A noun split across the line break; ration it.*

> Two armies in mud with a field in between
> were both of them singing it, neither one knew,
> in two different tongues. In the dark, a machine
> gun stopped, for the length of a verse, and then two.

**milk** · 1930 · plain · AABB · by fable

> A milkman would whistle it, street after street,
> at five in the morning, in rain and in sleet;
> and no one was up, and it fell on no ear;
> they all woke up humming it, year after year.

Swap *milkman* for postman or baker.

**ship** · 1930 · plain · AABB · by fable

> A ship in the night picked it up on the air
> from somebody's wireless, and who could say where;
> it crackled and faded and went with the dawn;
> the cook whistled on, though the signal was gone.

**hall** · 1950 · tender · AABB · by fable

> They danced to it, Saturdays, up at the hall;
> the band had it wrong, and that suited them all.
> The hall's been pulled down, and the band is long dead;
> the couples who met there still hum it in bed.

**mine** · 1950 · plain · AABB · by fable

> The men in the mine used to sing it below;
> as long as they're singing, the others all know.
> The pit's long been closed, and the village is small;
> the choir every Sunday still gives it its all.

**soap** · 1955 · light · AABB · by fable

> A company bought it to sell people soap,
> and played it so often that no one could cope;
> the soap is long gone, and the firm's been dissolved;
> the tune didn't notice; it wasn't involved.

**terrace** · 1970 · light · AABB · by fable

> The crowd at the football would sing it to jeer
> with words that their mothers were sorry to hear;
> the tune didn't mind, it had heard worse before;
> it went home with both sides, whatever the score.

Swap *football* for ballgame.

**probe** · 1977 · plain · AABB · by fable

> They put it aboard with the gold and the maps
> and shot it past Neptune to no one, perhaps.
> Out there it's a groove in a disc, nothing more;
> it's patient; it's waited for singers before.

Swap *Neptune* for Saturn or Pluto.

**tape** · 1980 · plain · AABB · by fable, last line the artist's

> It sat on a tape in a box in a shed,
> a name on the label of somebody dead.
> The tape was near ruined, the hiss was like rain,
> but still, some years on, it was heard once again.

Swap *box in a shed* for drawer by the bed or trunk by the bed.

**hold** · 1990 · light · ABAB · pairs with ring · by fable

> It played on the phone while a million held on
> for somebody, anyone, hoping to speak;
> they hated it, hummed it, hung up, and were gone;
> they're singing it still in the shower each week.

Swap *million* for billion or thousand.

**wire** · 1990 · plain · AABB · pairs with learned · by fable (B's wire verse, A's last line)

> They saved it as numbers and sent it by wire,
> a flicker of light, and as quick as a fire.
> Each copy was perfect in every last part,
> but not one machine ever knew it by heart.

**mic** · 1995 · light · AABB · enjambed · by claude
*A sentence runs over the line break, into the third line: ration it.*

> A crowd in a bar took their turns at the mic,
> and each of them sang it a little unlike
> the singer before them, and none of them knew
> they'd changed it for good, and they'd passed it on through.

**ring** · 2005 · light · AABB · pairs with hold · by fable

> They put it in phones as the sound of a ring;
> it went off in pockets, and no one would sing;
> and now when they hear it, they reach for their phone,
> and half of them think that the tune is their own.

**sample** · 2010 · plain · AABB · pairs with wax · by fable

> A girl put a piece of it under a beat,
> two seconds of somebody's voice, on repeat;
> and nobody asked who the somebody was,
> and nobody paid her, and nobody does.

Swap *girl* for boy; *her* for him.

**screen** · 2015 · plain · AABB · by fable (A's screen verse, B's last line)

> The whole world was watching it all in a day,
> a million bright faces all lit the same way;
> they laughed and they wept, and they scrolled right along,
> but nobody hummed it; it wasn't a song.

Swap *million* for billion or thousand.

**wall** · 2020 · plain · AABB · enjambed · by fable

> A kid with a can sprayed the words on a wall
> in red, by the railway, about ten feet tall;
> they painted it out; but the eight fifteen train
> had already passed it, and passed it again.

Swap *kid* for lad or girl.

**search** · 2020 · light · AABB · by claude

> A stranger once hummed it to find out its name;
> the phone listened close, and the answer that came
> was nobody's song, with a thousand to thank,
> and under "who wrote it", the line was left blank.

**learned** · 2025 · plain · AABB · rare · pairs with wire · by fable
*The project's self-portrait; answers the wire verse.*

> They fed a machine every way it was sung
> by anyone, ever, on tape or on wire;
> it learned every note, and it learned every tongue,
> and sings it in all of their voices: a choir.

### Any time

**bird** · plain · ABCB · by fable

> A blackbird outside of a window in June
> picked up the first line and invented the rest.
> It sang it at dawn to a bird who'd flown in
> from somewhere; she took it back home to her nest.

Swap *blackbird* for starling, robin or linnet; *June* for May, March or spring.

**deaf** · tender · AABB · by fable

> A girl who was deaf felt it come through the floor
> whenever her mother was singing next door;
> she never once heard it, but she knew the beat;
> her children all learned it by watching her feet.

Swap *girl* for boy, the pronouns following.

**fiddle** · plain · ABCB · by fable

> A man with a fiddle would play it for coins,
> the trains ran above it, the traffic ran by;
> and nobody stopped, but a thousand went home,
> the tune in their pockets, not knowing quite why.

Swap *man* for girl or boy; *fiddle* for whistle, squeezebox or banjo.

**kids** · tender · ABAB · pairs with lullaby · by artist (first line) and fable

> They sang it as kids while they sat by the fire,
> the words halfinvented, the tune halfasleep;
> they're gray now, and scattered, and most of the choir
> are grandparents, singing their grandkids to sleep.

**lullaby** · tender · ABAB · pairs with kids · by fable

> A woman was singing it low to a child
> who slept before ever the second verse came;
> the child never learned it. At forty, she smiled
> at strangers who hummed it, not knowing its name.

Swap *forty* for fifty, sixty or thirty.

**mind** · dark · AABB · pairs with names · by fable (A's mind verse, C's 'kept it alone in his head')

> A quiet man kept it alone in his head,
> so close and so safe that it never was said.
> It went where he went, and it slept where he slept;
> they buried it with him, the secret he kept.

Swap *man* for girl, boy, kid, nun or monk, the pronouns following (they
for the kid: "It went where they went, and it slept where they slept").

**names** · tender · AABB · pairs with mind · by fable

> An old woman lost all the names and the years,
> and who was her daughter, and why there were tears;
> but somebody hummed the first line, and she smiled,
> and sang all the rest as she did as a child.

Swap *daughter* for husband.

**nurse** · plain · AABB · by fable

> A nurse used to hum it at night on the ward,
> and most of them slept, and the rest of them snored;
> but one lay awake, and he learned every note;
> it went home on Tuesday inside of his coat.

Swap *he* for she; *his* for her; *Tuesday* for Monday, Friday or Sunday.

**pipe** · dark · AABB · by fable

> A man in a cell tapped it out on the wall
> to someone he never once saw, down the hall.
> The someone tapped back, and for years, every day,
> it went through the stone; it was all they could say.

Swap *man* for girl or boy, the pronouns following.

**shell** · plain · AABB · by fable

> A woman was humming it, shelling the peas;
> the tune drifted out on the afternoon breeze
> to somebody passing who couldn't have said
> its name, but it went all the way to his bed.

Swap *his* for her.

**shepherd** · plain · AABB · by fable

> A shepherd would sing it to sheep on a hill;
> the sheep never learned it, and never stood still;
> the wind took it down to the farms in the vale,
> and that's how it came to be sung over ale.

Swap *shepherd* for goatherd; *sheep* for goats.

**skip** · plain · AABB · by fable, the swaps the artist's

> The *girls* in the *yard* turned it into a game;
> they skipped to it, counting; the rope always came
> down early, and no one had heard how it ends.
> They made up an ending and taught it to friends.

Swap *girls* for boys or kids; *yard* for field.

**tongue** · plain · ABCB · enjambed · by fable

> It's sung in a language that nobody speaks
> by seven old women who don't know a word;
> they learned it as sound from their mothers, and sound
> is all that a song ever needs to be heard.

Swap *seven* for twenty or thirty.

**wakes** · plain · AABB · by fable

> They sang it at weddings, they sang it at wakes;
> it's merry or mournful, whichever it takes.
> It's been to more churches than anyone knows;
> it marries, it buries, and then off it goes.

**misheard** · tender · AABB · by claude

> They sang it for years with a line they'd misheard,
> and taught it their children that way, word for word;
> and that is the way that it's sung in their town:
> the wrong word is right now, and handed on down.

## The bridge

Sung by the lineage choir. The canon is always sung, its swaps chosen once
per song; in a long form one extra stanza, coat, owed, borrow or slow, may follow it,
sung by the same choir on the same tune.

**canon** · AABB · by fable (B's refrain)

> Carry it over the water and wire,
> hand it along like a coal from the fire;
> it's nobody's making and everyone's own,
> it dies in the dark if you leave it alone.

Swap *water* for mountain, border or desert; *coal* for spark or light; *dark* for cold.

**coat** · ABAB · by fable

> Give it away like a coat that's too small;
> somebody's shivering, somebody's near.
> So sing it out loud in a room or a hall,
> and sing it to someone, or no one will hear.

**owed** · ABAB · by claude

> Nobody owns it, and nobody's owed;
> nobody holds it for long in their hands.
> It travels by mouth and it travels by road,
> and settles in strangers in faraway lands.

**borrow** · ABAB · by claude, its ending chosen by the artist

> Borrow it, wear it, and give it away;
> change what you like, and then hand it along.
> A stranger will sing it back some other day,
> a little bit changed, and you'll know it's your song.

**slow** · AABB · by claude

> Sing it too slowly or sing it too fast,
> sing it a little unlike it was last;
> it doesn't mind wandering, doesn't mind wear,
> it only goes quiet when nobody's there.

## The tag

Everyone, on the tune of "by everyone, no one, and now it's by you", one
syllable on every note: la, loo or oo, chosen once per song.

## The rules

How a song is put together from the bank; the same rules are data under
`bank.rules` in the genome.

- **Verses.** Two to four per song. The first is a common AABB verse without
  enjambment: it teaches the shape. At most one variant (ABAB, ABCB or
  enjambed) and at most one rare verse per song, never first. The chosen
  verses go in era order, earliest first, so the song reads as time passing;
  verses with no year go anywhere. Paired verses are sung adjacent, in era
  order. No two dark verses adjacent; at most one light verse.
- **Refrain.** Every refrain has words of its own. The first asks who made,
  wrote or sang it (one no head the song sings asks, where it can; the
  artist's, 2026-09-27), the last who owns it; each between asks something
  else, a different word each time while any are left. While, when or if is drawn
  afresh each time round, and it goes, who knows or it grows too, each
  refrain a different one while any are left. The first
  and last refrains sing the knows head; a refrain between may sing another
  head, each at most once a song, with the words it fixes as written. Each
  refrain sings one couplet, none twice until all are used, and the last
  always sings canon.
- **Bridge.** The canon is always sung, its swaps chosen once per song. A
  long form may add one extra stanza, coat, owed, borrow or slow, after it.
- **Tag.** One syllable for the whole tag, chosen once per song.

## Dropped along the way

- An envelope-rhymed refrain (ABBA) that swapped lines 2 and 4: it can't be
  sung as written, since those phrases have ten and eleven notes, and it moved
  "now it's by you" off its cadence.
- An enjambed ABAB refrain ("Who heard this song? Nobody knows / how far it
  has gone, or who's singing where; / it's nobody's making, and nobody owes /
  it anything more than the breath and the air"): it fits the tune, but it
  replaces every hook line, so the refrain would stop being the refrain.
- "Who owns this song? What does it owe?" as a first line: "Nobody knows"
  opens and closes every song. The artist's so head is the one change to
  it, and only in a refrain between.
- Verses about a mill and a school; a soap-for-beer swap that broke the
  soap/cope rhyme; "mm" as a tag syllable, which has no vowel to sing.
- The go head ("Who heard this song? Nobody. Go / and sing it to someone,
  and watch it grow") and the given stanza ("Nobody wrote it, and nobody's
  paid; / nobody signed it, and nobody's due. / And somebody sang it to you,
  and you're made / of what you were given. It's given to you."): the artist
  found both hard to read (2026-09-26); a rewritten close didn't save given.
  A machine stanza ("Someone's machine has been singing it now") was offered
  with owed and slow, and left out.
