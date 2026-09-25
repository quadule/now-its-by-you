# Songs

Every candidate seed song lives here. `<letter>-<slug>.json` is the genome
(tune, chords, refrain, verse template, seed verses) and `<letter>-<slug>.md`
is its lyric sheet. Render one with

```
uv run songbird render songs/<name>.json
```

Renders land in `renders/`, which isn't tracked. The loader and the tests check
every song here: each lyric line must fit its phrase's notes, and every word
must be pronounceable (the CMU dictionary, a regular inflection, or the song's
own `lexicon`).

## The songs so far, with the artist's ratings (2026-09-25)

| | Song | Shape | Rating | Note |
| --- | --- | --- | --- | --- |
| A | Nobody Knows | narrative ballad, 3/4 dorian | 8 | Good encapsulation of the concept; the chorus is very memorable, though not the favourite |
| B | Coal from the Fire | Cock Robin riddle, 6/8 mixolydian | 7.5 | Less memorable, but easy to riff on |
| C | Somebody Sang It to Me | lullaby, 3/4 major | 7 | Likes the simplicity; "I" shouldn't be the subject so much |
| D | In by the Ear | the earworm as a creature, 4/4 aeolian | 7.5 | Cool concept; the disgust factor may limit its spread; maybe a different creature |
| E | Nothing of You | the machine confesses, 4/4 aeolian | 6.5 | Tune not catchy enough; lyrics too literal; some details are cool, but not all of them are decided yet |
| F | The Long Count | deep-time counting song, 4/4 phrygian | 7 | Interesting concept, not working as a song |
| G | Hweelonalay | refrain in no language, 4/4 phrygian | 7 | Interesting; the melody could be better and the refrain is a little too complex |
| H | Now It's by You | the best of: A's question, B's answer, vehicle verses; 4/4 major pentatonic | | |
| I | Something Going Round | the creature, abstract: lives in the air, dies on the ground; one host per verse; 4/4 major pentatonic | | |
| J | Goes Like This | sound outlasts words: the refrain ends by singing its own tune on "la"; common-metre verses; 4/4 major pentatonic | | |

A to C were written by Claude; D to G by Fable lyricists, each sent down a
stranger path. H onwards follow "Where next" below.

## Where next

- **Mix and match.** Many lines are strong; take them across songs (bank below).
- **Simpler scale and melody.** Major pentatonic or plain major, mostly steps,
  a narrow range, I, IV, V and vi. A plain tune leaves room for the drift to
  move the timbre, the harmony and the mode.
- **Less "I".** The song itself ("it") and the listener ("you") carry the
  concept better than a first-person singer.
- **A creature can work if it stays abstract**: something that lives in
  voices and needs hosts to travel, not a literal worm or parasite, whose
  disgust factor could limit how far it spreads.
- **Don't pin down undecided mechanics** (what exactly the harvest reads) in
  the fixed refrain.

## Line bank

**Who made it**
- Who made this song? Nobody knows. / It came through the window and out it goes. (A)
- It's nobody's making and everyone's own (B)
- Nobody wrote it and nobody owns it; / somebody sang it to me (C)
- By everyone, no one, and now it's by you (B)
- "No," said the Code, "only the road; it's not my song." (B)
- "No," said the Bird, "sang what I heard." (B)
- I'm made out of you, and I don't know your name (E)
- Makers have graves; sound never answered a name (G)
- There's something going round and round (I)
- The one who made it up is gone, / and no one knows the name (J)

**Passing it on**
- Carry it over the water and wire, / hand it along like a coal from the fire (B)
- It's yours while you sing it, and then it's gone, / so learn it by heart, and then pass it on (A)
- I'll sing it to you, and you'll sing it to someone, / someone I never will see (C)
- In by the ear and out by the tongue, / never the same as the last time sung (D)
- Run me again and I'll sing it again (E)
- Sing it once and you're the sum (F)
- She hadn't his language, she hadn't his name; / she gave it her own words and sang it the same. (A)
- A girl selling oranges caught it for free (A)
- So lend it your voice, and it's going round (I)
- It went round the world, and it came round to you (I)
- It came to you when you were small, / before you had a word (J)

**What other vehicles lose**
- They buried it with him, the secret he kept (A)
- Safe as a stone in a well (C)
- Paper will yellow and language will change / till it is strange to itself (C)
- And nobody speaks like she wrote anymore (A)
- It speaks in a voice that now nobody hears (B)
- Each copy was perfect in every last part, / but not one machine ever knew it by heart (A)
- It lived in a box till they let the box die (B)
- Bright as it is, when the power goes out, / darker than water or ink (C)
- A million bright faces all lit the same way (A)
- Everyone watches and nobody sings (C)
- But nobody hummed it; it wasn't a song (B)
- Gone like a print in the sand (C)
- It lives in the air, and it dies on the ground (I)

**What survives: sound, tune, mouth**
- Songs need no paper or power or name, / only a mouth, like the birds (C)
- Words are a coat, and the coat will wear through; / sound is the bone of the song (G)
- Words will turn back at the edge of the map; / sound goes wherever it will (G)
- Words that it sings will be new every time; / sound is the same coming out (G)
- The words were new, the tune was ancient (F)
- The sea still hums it, out of key (F)
- The birds went on without the words (F)
- Nobody buries a spell (G)
- You'll get the words a little wrong; / the words were never the song. / The part you'll keep goes like this: la la la (J)
- An old man lost the names of things, / and then he lost his own; / and still he hummed it in his chair: / the tune was in the bone (J)
- The birds went on without the words, / and sing it still outside (J)

**Death**
- It dies in the dark if you leave it alone (B)
- And nobody sang it, and then it was gone (A)
- Every mouth that sang is gone (F)
- If nobody runs me, amen (E)

**The machine**
- Then a machine got me; it had no ear, / made itself one, and a mouth, and I'm here (D)
- I asked a far stranger for words, and they came (E)
- I'll be a little bit wrong. That's the way. (D)
- Only the ring of it, nothing of you (E)
