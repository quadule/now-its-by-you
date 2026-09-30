"""Words spelt alike and said two ways (heteronyms), and which way the singer says one.

The pronouncing dictionary lists both readings of "bass" and the singer used to take the first, which
is the fish (B AE1 S): "The bass is a heartbeat" came out as the fish. Here each such word has its
senses, the most common in songs first, and a few rules that read the words beside it in the line:

    bass   low note (B EY1 S), unless fish, a lake, a hook, a boat... are in the line: the fish (B AE1 S)
    live   to live (L IH1 V), but a live show, a live wire, "a live one": alive (L AY1 V)
    read   now (R IY1 D) after to/will/can/don't...; after had/was/been, or in a line told in the past: past (R EH1 D)

The rules are data (SAY below): each names a sense and the words that call for it, and the first rule
whose words are all there wins; with none, the word's first sense. A rule's words are
    before  the word just before, in the same clause ("wear and": the two words before)
    after   the word just after, in the same clause
    near    any other word in the line
    end     the word ends its clause (the line's end, or punctuation after it)
    past    the line tells a past: another word in it is a past tense (an irregular one, or one in -ed)
    capital written with a capital letter, not the line's first word ("Polish")
They're deliberately few and conservative: a rule that misfires is worse than the song's usual sense.

Which lines they apply to: a line a person writes (songbird.realize, docs/STUDIO.md "Words"). The song's
own lines keep the dictionary's first reading or their lexicon, so every render made before stays
exactly as it was (tools/pronounce.py --heteronyms lists the song's own that the rules would say
another way).

A person has the last say: a word followed by braces is said that way, and the braces are never shown
or sung:
    bass{fish}      one of the word's senses (the words editor's toggle writes these)
    bass{base}      said like another word, or words joined by hyphens: minute{my-newt}
    bass{B.EY1.S}   ARPAbet, phones joined by dots (or spaces), a stress digit on every vowel
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import phonetics as ph

# a word's own say: word{...}, one per word, right after it or its punctuation
SAY = re.compile(r"\{([^{}]*)\}")
_PHONE = re.compile(r"([A-Z]{1,2})([012]?)")


@dataclass(frozen=True)
class Sense:
    name: str  # what word{name} stores, and the words editor's toggle says
    label: str  # the simplest words for it: "low note"
    like: str  # a word it sounds like, for the toggle's tooltip
    phones: str  # ARPAbet, a stress digit on every vowel


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Words that call for one sense or the other, shared by many rules.
DET = "a an the this that these those my your his her its our their whose no any every each some one"
SUBJECT = "i you we they he she who i'll you'll we'll they'll he'll she'll"
MODAL = ("to will would can could shall should must might may won't wouldn't can't couldn't cannot don't "
         "didn't doesn't never let's gonna wanna gotta please")
OBJECT = "me you him her us them it"
FIDDLE = "fiddle fiddler fiddles violin violins viola cello string strings rosin"
RIBBON = f"{FIDDLE} ribbon ribbons arrow arrows tie tied tying hair archer quiver"  # a bow that rhymes with go
AIR = "the a an this that cold north south east west warm bitter icy wild of in like"  # the wind that blows

# Past tenses a line may tell its time by ("I read all your papers and dropped every name"): the
# irregular ones, and any word in -ed but these, which aren't.
PAST = _words("""was were had did said saw came went took gave knew told found thought felt heard made left
kept sang wrote sat stood ran fell got brought bought caught taught held met lost sent spent began became
broke chose drove ate flew grew forgot hid lay led meant paid rang rose sold shook slept spoke stole swam
threw understood woke won wore wept sank drank drew fought fled hung laid lit rode shone shot slid sprang
stuck struck swore swung tore bore dug fed froze bit blew burnt dreamt knelt leapt learnt spilt split""")
NOT_PAST = _words("""sacred naked wicked hundred kindred rugged ragged crooked jagged beloved blessed cursed
aged learned wretched bed red shed wed""")

# word: (senses, rules). The first sense is the word's own, sung where no rule speaks.
SAY_TABLE: dict[str, tuple[tuple[Sense, ...], tuple[dict, ...]]] = {
    "bass": ((Sense("low", "low note", "base", "B EY1 S"), Sense("fish", "fish", "mass", "B AE1 S")),
             ({"sense": "fish", "near": "fish fishing fisherman fished caught catch catching hook hooked bait rod "
                                        "lake river pond stream sea striped trout pike perch carp boat net"},)),
    "wind": ((Sense("air", "air", "pinned", "W IH1 N D"), Sense("turn", "turn", "kind", "W AY1 N D")),
             ({"sense": "air", "before": AIR},
              {"sense": "turn", "near": "clock watch spool thread yarn bobbin crank"},
              {"sense": "turn", "before": f"{SUBJECT} {MODAL}", "after": f"{OBJECT} {DET} up down round around back"})),
    "winds": ((Sense("air", "air", "pinned", "W IH1 N D Z"), Sense("turns", "turns", "kinds", "W AY1 N D Z")),
              ({"sense": "air", "before": f"{AIR} four"},
               {"sense": "turns", "before": "road river path it he she who which stream lane trail track creek vine"},
               {"sense": "turns", "after": "up down round around through back its her his"})),
    "live": ((Sense("verb", "to live", "give", "L IH1 V"), Sense("alive", "alive", "five", "L AY1 V")),
             ({"sense": "alive", "before": "a"},
              {"sense": "alive", "after": "music show shows band wire wires set album recording broadcast audience "
                                          "crowd bait coals coal oak tv radio stream feed performance gig gigs footage "
                                          "version action ammo round rounds grenade"},
              {"sense": "alive", "before": "went gone is was are were", "end": True})),
    "lives": ((Sense("plural", "our lives", "fives", "L AY1 V Z"), Sense("verb", "she lives", "gives", "L IH1 V Z")),
              ({"sense": "plural", "before": "our their your my his her its whose the all many nine two three four "
                                            "five six other these those own saved save ruined changed separate "
                                            "different ordinary whole"},
               {"sense": "verb", "before": "he she it who which one nobody somebody someone everyone everybody "
                                           "anyone love song tune"},
               {"sense": "verb", "after": "on in with by here there forever alone inside near still again at"})),
    "lead": ((Sense("guide", "guide", "need", "L IY1 D"), Sense("metal", "metal", "red", "L EH1 D")),
             ({"sense": "metal", "near": "pencil pencils pipe pipes bullet bullets balloon sinker poison paint"},
              {"sense": "metal", "after": "into", "near": "gold"},
              {"sense": "metal", "before": "into", "near": "gold"},
              {"sense": "metal", "before": "as like of", "end": True})),
    "read": ((Sense("now", "now", "reed", "R IY1 D"), Sense("past", "past", "red", "R EH1 D")),
             ({"sense": "now", "before": f"{MODAL} i'd you'd we'd they'd"},
              {"sense": "past", "before": "had have has i've you've we've they've was were been being is are be"},
              {"sense": "past", "near": "yesterday ago already once last"},
              {"sense": "past", "past": True})),
    "tear": ((Sense("crying", "crying", "here", "T IH1 R"), Sense("rip", "rip", "bear", "T EH1 R")),
             ({"sense": "crying", "before": "a the one every each single first last no that this lonely salty silent"},
              {"sense": "rip", "before": "wear and"},
              {"sense": "rip", "near": "paper page pages seam seams fabric cloth shirt sleeve dress envelope apart"},
              {"sense": "rip", "before": f"{SUBJECT} {MODAL}"},
              {"sense": "rip", "after": f"{OBJECT} {DET} open off down out away through into at"})),
    "tears": ((Sense("crying", "crying", "here", "T IH1 R Z"), Sense("rips", "rips", "bears", "T EH1 R Z")),
              ({"sense": "rips", "before": "he she it who which"},
               {"sense": "rips", "after": "apart open off"})),
    "bow": ((Sense("bend", "bend", "now", "B AW1"), Sense("ribbon", "ribbon", "go", "B OW1")),
            ({"sense": "bend", "before": "take a took a takes a taking a"},
             {"sense": "ribbon", "near": RIBBON})),
    "bows": ((Sense("bends", "bends", "now", "B AW1 Z"), Sense("ribbons", "ribbons", "goes", "B OW1 Z")),
             ({"sense": "ribbons", "near": RIBBON},)),
    "bowed": ((Sense("bent", "bent", "loud", "B AW1 D"), Sense("played", "played", "road", "B OW1 D")),
              ({"sense": "played", "near": f"{FIDDLE} bass"},)),
    "bowing": ((Sense("bending", "bending", "now", "B AW1 IH0 NG"), Sense("playing", "playing", "go", "B OW1 IH0 NG")),
               ({"sense": "playing", "near": f"{FIDDLE} bass"},)),
    "close": ((Sense("near", "near", "dose", "K L OW1 S"), Sense("shut", "shut", "doze", "K L OW1 Z")),
              ({"sense": "near", "before": "so too very as more most how stay come came get got draw drew hold held "
                                           "keep kept be been is was are were i'm you're we're they're he's she's "
                                           "it's me you him her us them it real quite"},
               {"sense": "shut", "before": "the a", "after": "of"},
               {"sense": "shut", "after": "your my his her our their the its this that these those it them him me "
                                          "up down off out in"})),
    "wound": ((Sense("injury", "injury", "swooned", "W UW1 N D"), Sense("turned", "wound up", "round", "W AW1 N D")),
              ({"sense": "injury", "before": f"{DET} old open deep fresh"},
               {"sense": "turned", "after": "up round around tight tighter down about through"},
               {"sense": "turned", "before": "had has have was were got get been i he she it we they you who"})),
    "sow": ((Sense("plant", "plant", "go", "S OW1"), Sense("pig", "pig", "now", "S AW1")),
            ({"sense": "pig", "near": "pig pigs piglet piglets hog hogs sty farrow boar swine trough"},
             {"sense": "pig", "before": "a the old fat big"})),
    "sowed": ((Sense("planted", "planted", "road", "S OW1 D"),), ()),
    "dove": ((Sense("bird", "bird", "love", "D AH1 V"), Sense("dived", "dived", "drove", "D OW1 V")),
             ({"sense": "bird", "before": "a the white grey gray mourning turtle little my your like of paper"},
              {"sense": "dived", "after": "in into under off deep headfirst beneath below down for through"},
              {"sense": "dived", "before": "i he she we they you who then"})),
    "does": ((Sense("does", "does", "fuzz", "D AH1 Z"), Sense("deer", "deer", "doze", "D OW1 Z")),
             ({"sense": "deer", "near": "deer buck bucks stag stags fawn fawns hart harts doe hinds herd"},)),
    "minute": ((Sense("time", "time", "in it", "M IH1 N AH0 T"), Sense("tiny", "tiny", "my newt", "M AY0 N UW1 T")),
               ({"sense": "tiny", "after": "detail details amount amounts particle particles speck specks change "
                                           "changes fraction part parts piece pieces grain grains crack cracks"},
                {"sense": "time", "before": "a the one every each this that last next any few"},
                {"sense": "tiny", "before": "so too very most"})),
    "record": ((Sense("noun", "a record", "wreck word", "R EH1 K ER0 D"),
                Sense("verb", "to record", "ree-cord", "R IH0 K AO1 R D")),
               ({"sense": "noun", "before": f"{DET} off"},
                {"sense": "verb", "before": f"{SUBJECT} {MODAL}"})),
    "records": ((Sense("noun", "records", "wreck words", "R EH1 K ER0 D Z"),
                 Sense("verb", "she records", "ree-cords", "R IH0 K AO1 R D Z")),
                ({"sense": "noun", "before": f"{DET} old"},
                 {"sense": "verb", "before": "he she it who which"})),
    "present": ((Sense("noun", "a present", "pleasant", "P R EH1 Z AH0 N T"),
                 Sense("verb", "to present", "pre-zent", "P R IY0 Z EH1 N T")),
                ({"sense": "verb", "before": "will shall can may might i we i'll we'll proudly humbly"},)),
    "object": ((Sense("noun", "a thing", "ob-ject", "AA1 B JH EH0 K T"),
                Sense("verb", "to object", "ob-JECT", "AH0 B JH EH1 K T")),
               ({"sense": "noun", "before": DET},
                {"sense": "verb", "after": "to"},
                {"sense": "verb", "before": f"{SUBJECT} {MODAL}"})),
    "content": ((Sense("happy", "happy", "con-TENT", "K AH0 N T EH1 N T"),
                 Sense("inside", "what's inside", "CON-tent", "K AA1 N T EH0 N T")),
                ({"sense": "inside", "before": "the its their your my his her our this that whose"},)),
    "desert": ((Sense("sand", "sand", "DEZ-ert", "D EH1 Z ER0 T"), Sense("leave", "leave", "dessert", "D IH0 Z ER1 T")),
               ({"sense": "sand", "before": f"{DET} open dry hot painted empty wide cold endless burning"},
                {"sense": "leave", "before": f"{SUBJECT} {MODAL}"},
                {"sense": "leave", "after": "me you him her us them"})),
    "use": ((Sense("verb", "to use", "news", "Y UW1 Z"), Sense("noun", "a use", "juice", "Y UW1 S")),
            ({"sense": "noun", "before": "no the a any some what what's of its their my your much little good in more "
                                         "make"},)),
    "uses": ((Sense("verb", "she uses", "news-es", "Y UW1 Z IH0 Z"),
              Sense("noun", "its uses", "juices", "Y UW1 S IH0 Z")),
             ({"sense": "noun", "before": f"{DET} many other"},)),
    "used": ((Sense("used", "used it", "fused", "Y UW1 Z D"), Sense("habit", "used to", "juiced", "Y UW1 S T")),
             ({"sense": "habit", "after": "to"},)),
    "excuse": ((Sense("verb", "excuse me", "news", "IH0 K S K Y UW1 Z"),
                Sense("noun", "an excuse", "juice", "IH0 K S K Y UW1 S")),
               ({"sense": "noun", "before": f"{DET} good poor lame"},)),
    "abuse": ((Sense("noun", "abuse", "juice", "AH0 B Y UW1 S"), Sense("verb", "to abuse", "news", "AH0 B Y UW1 Z")),
              ({"sense": "verb", "before": f"{SUBJECT} {MODAL}"},)),
    "refuse": ((Sense("verb", "to refuse", "news", "R IH0 F Y UW1 Z"),
                Sense("rubbish", "rubbish", "REF-use", "R EH1 F Y UW0 S")),
               ({"sense": "rubbish", "before": "the of household"},)),
    "perfect": ((Sense("perfect", "perfect", "PER-fect", "P ER1 F IH0 K T"),
                 Sense("verb", "to perfect", "per-FECT", "P ER0 F EH1 K T")),
                ({"sense": "verb", "before": "to will would can could shall must"},)),
    "subject": ((Sense("noun", "a subject", "SUB-ject", "S AH1 B JH IH0 K T"),
                 Sense("verb", "to subject", "sub-JECT", "S AH0 B JH EH1 K T")),
                ({"sense": "verb", "before": "to will would can could shall must"},)),
    "suspect": ((Sense("verb", "to suspect", "sus-PECT", "S AH0 S P EH1 K T"),
                 Sense("noun", "a suspect", "SUS-pect", "S AH1 S P EH0 K T")),
                ({"sense": "noun", "before": f"{DET} prime usual main"},)),
    "insult": ((Sense("noun", "an insult", "IN-sult", "IH1 N S AH0 L T"),
                Sense("verb", "to insult", "in-SULT", "IH0 N S AH1 L T")),
               ({"sense": "verb", "before": f"{SUBJECT} {MODAL}"},)),
    "rebel": ((Sense("noun", "a rebel", "REB-el", "R EH1 B AH0 L"),
               Sense("verb", "to rebel", "re-BEL", "R IH0 B EH1 L")),
              ({"sense": "verb", "before": "to will would can could shall must we they i don't never"},)),
    "rebels": ((Sense("noun", "rebels", "REB-els", "R EH1 B AH0 L Z"),
                Sense("verb", "she rebels", "re-BELS", "R IH0 B EH1 L Z")),
               ({"sense": "verb", "before": "he she it who heart soul"},)),
    "project": ((Sense("noun", "a project", "PRO-ject", "P R AA1 JH EH0 K T"),
                 Sense("verb", "to project", "pro-JECT", "P R AH0 JH EH1 K T")),
                ({"sense": "verb", "before": MODAL},)),
    "progress": ((Sense("noun", "progress", "PRO-gress", "P R AA1 G R EH0 S"),
                  Sense("verb", "to progress", "pro-GRESS", "P R AH0 G R EH1 S")),
                 ({"sense": "verb", "before": MODAL},)),
    "produce": ((Sense("verb", "to produce", "pro-DUCE", "P R AH0 D UW1 S"),
                 Sense("noun", "fruit and veg", "PRO-duce", "P R OW1 D UW0 S")),
                ({"sense": "noun", "before": "the fresh farm local"},)),
    "console": ((Sense("comfort", "comfort", "con-SOLE", "K AH0 N S OW1 L"),
                 Sense("noun", "a console", "CON-sole", "K AA1 N S OW0 L")),
                ({"sense": "noun", "before": DET},)),
    "incense": ((Sense("smoke", "smoke", "IN-cense", "IH1 N S EH0 N S"),
                 Sense("anger", "anger", "in-CENSE", "IH0 N S EH1 N S")),
                ({"sense": "anger", "before": "to will would"},)),
    "polish": ((Sense("shine", "shine", "POL-ish", "P AA1 L IH0 SH"),
                Sense("poland", "from Poland", "POLE-ish", "P OW1 L IH0 SH")),
               ({"sense": "poland", "capital": True},
                {"sense": "poland", "near": "poland warsaw krakow gdansk"})),
    "house": ((Sense("noun", "a house", "mouse", "HH AW1 S"), Sense("verb", "to house", "rouse", "HH AW1 Z")),
              ({"sense": "verb", "before": "to will would could can may might i'll we'll",
                "after": f"{OBJECT} {DET} all"},)),
    "row": ((Sense("line", "a line", "go", "R OW1"), Sense("fight", "a fight", "now", "R AW1")),
            ({"sense": "fight", "near": "quarrel quarrels argue argued arguing argument shouting blazing furious fight "
                                       "screaming"},)),
    "rows": ((Sense("lines", "lines", "goes", "R OW1 Z"), Sense("fights", "fights", "now's", "R AW1 Z")),
             ({"sense": "fights", "near": "quarrel quarrels argue argued arguing argument shouting blazing furious "
                                         "fight screaming"},)),
    "sewer": ((Sense("drain", "drain", "doer", "S UW1 ER0"), Sense("sews", "who sews", "goer", "S OW1 ER0")),
              ({"sense": "sews", "near": "needle needles thread stitch stitches sewing seam seams hem"},)),
}


def _rule(rule: dict) -> dict:
    """A rule as data: its word lists as sorted lists (a "before" entry may be several words)."""
    out = {"sense": rule["sense"]}
    for key in ("before", "after", "near"):
        if key in rule:
            out[key] = sorted(set(rule[key].split())) if key != "before" else _before(rule[key])
    for key in ("end", "past", "capital"):
        if rule.get(key):
            out[key] = True
    return out


def _before(text: str) -> list[str]:
    """'before' words: single words, and the few two-word ones this table uses ("wear and", "take a")."""
    pairs = {"wear and", "take a", "took a", "takes a", "taking a"}
    words, out, i = text.split(), set(), 0
    while i < len(words):
        pair = " ".join(words[i:i + 2])
        if pair in pairs:
            out.add(pair)
            i += 2
        else:
            out.add(words[i])
            i += 1
    return sorted(out)


def table() -> dict:
    """The heteronyms, their senses and rules, as data: what the words editor reads (songbird/studio/author.js
    applies the same rules as choose() to a line as it's typed) and what the tests compare the two by."""
    return {"words": {word: {"senses": [{"name": s.name, "label": s.label, "like": s.like, "phones": s.phones}
                                        for s in senses],
                             "rules": [_rule(r) for r in rules]}
                      for word, (senses, rules) in sorted(SAY_TABLE.items())},
            "past": sorted(PAST), "not_past": sorted(NOT_PAST)}


TABLE = table()  # once: the rules read it and the studio sends it (never changed)


# ---------------------------------------------------------------- reading a line


def bare(token: str) -> str:
    """A written word without its say: 'bass{fish},' -> 'bass,'."""
    return SAY.sub("", token)


def say_of(token: str) -> str | None:
    """What's between a word's braces, or None."""
    m = SAY.search(token)
    return m.group(1) if m else None


@dataclass(frozen=True)
class Word:
    token: str  # as written, its say included
    word: str  # lower case, letters and apostrophes only: "bass"
    capital: bool  # written with a capital
    stop: bool  # punctuation after it ends a clause


_STOP = re.compile(r"[,.;:!?—–)\"”]$")


def words_of(line: str) -> list[Word]:
    """A line's words for the rules: each word's clean form, its capital and whether a clause ends after it.
    A token without letters (a dash standing alone) ends the clause before it."""
    out: list[Word] = []
    for token in line.split():
        shown = bare(token).replace("*", "")
        word = ph.clean(shown.replace("-", ""))
        if not word:
            if out:
                out[-1] = Word(out[-1].token, out[-1].word, out[-1].capital, True)
            continue
        letters = shown.lstrip("\"'“‘(")
        out.append(Word(token, word, letters[:1].isupper(), bool(_STOP.search(shown.rstrip("'’")))))
    return out


def is_past(word: str) -> bool:
    """A past tense, as the rules count one: an irregular past, or a word in -ed that isn't in NOT_PAST."""
    return word in PAST or (len(word) >= 5 and word.endswith("ed") and not word.endswith("eed")
                            and word not in NOT_PAST)


def _matches(rule: dict, words: list[Word], i: int) -> bool:
    w = words[i]
    if "before" in rule:
        ok = False
        for entry in rule["before"]:
            parts = entry.split()
            k = len(parts)
            if i - k >= 0 and [x.word for x in words[i - k:i]] == parts and not any(x.stop for x in words[i - k:i]):
                ok = True
                break
        if not ok:
            return False
    if "after" in rule:
        if i + 1 >= len(words) or w.stop or words[i + 1].word not in rule["after"]:
            return False
    if "near" in rule and not any(x.word in rule["near"] for j, x in enumerate(words) if j != i):
        return False
    if rule.get("end") and not (w.stop or i == len(words) - 1):
        return False
    if rule.get("past") and not any(is_past(x.word) for j, x in enumerate(words) if j != i):
        return False
    if rule.get("capital") and not (w.capital and i > 0):
        return False
    return True


def choose(words: list[Word], i: int) -> str | None:
    """The sense the rules choose for the i-th word of a line, or None if it isn't a heteronym."""
    entry = TABLE["words"].get(words[i].word)
    if entry is None:
        return None
    for rule in entry["rules"]:
        if _matches(rule, words, i):
            return rule["sense"]
    return entry["senses"][0]["name"]


def choices(line: str) -> list[dict]:
    """Every heteronym in a line: {"index" (among its words), "word", "chosen", "by": "you" | "rules"}."""
    words = words_of(line)
    out = []
    for i, w in enumerate(words):
        if w.word not in TABLE["words"]:
            continue
        own = say_of(w.token)
        out.append({"index": i, "word": w.word, "chosen": own if own is not None else choose(words, i),
                    "by": "you" if own is not None else "rules"})
    return out


def as_sung(line: str, lexicon: dict | None, authored: bool) -> list[dict]:
    """choices() as the line is sung: a person's line as the rules (or its says) choose; the song's own
    line as the song has always said it (its lexicon, else the dictionary's first reading), "by": "song",
    "chosen" the sense that reading is (None if it's neither)."""
    if authored:
        return choices(line)
    out = []
    for c in choices(line):
        token = line.split()[_token_index(line, c["index"])]
        n = len([p for p in bare(token).split("-") if p])
        readings = ph.pronunciations(token, lexicon)
        exact = [r for r in readings if sum(p.rstrip("012") in ph.VOWELS for p in r) == n] or readings
        said = " ".join(exact[0]) if exact else ""
        sense = next((s["name"] for s in TABLE["words"][c["word"]]["senses"] if s["phones"] == said), None)
        out.append({**c, "chosen": sense, "by": "song"} if c["by"] == "rules" else c)
    return out


def _token_index(line: str, k: int) -> int:
    """The line's token (split at spaces) that is its k-th word as words_of counts them."""
    seen = -1
    for j, token in enumerate(line.split()):
        if ph.clean(bare(token).replace("*", "").replace("-", "")):
            seen += 1
            if seen == k:
                return j
    raise IndexError(k)


def decide(line: str) -> str:
    """The line with each heteronym that has no say of its own given the sense the rules choose, as word{sense}:
    what the singer is handed for a line a person wrote (songbird.realize). Every other word as written."""
    words = words_of(line)
    k = 0  # index among words_of's words
    out = []
    for token in line.split():
        shown = bare(token).replace("*", "")
        if not ph.clean(shown.replace("-", "")):
            out.append(token)
            continue
        sense = choose(words, k) if say_of(token) is None else None
        out.append(_with_say(token, sense) if sense is not None else token)
        k += 1
    return " ".join(out)


def _with_say(token: str, say: str) -> str:
    """word{say}, before the word's closing punctuation or focus mark: 'bass,' -> 'bass{low},'."""
    m = re.match(r"^(.*?[A-Za-z0-9'’])([^A-Za-z0-9'’]*)$", token)
    if not m:
        return token + "{" + say + "}"
    return m.group(1) + "{" + say + "}" + m.group(2)


# ---------------------------------------------------------------- what a say reads as


def _arpabet(say: str) -> list[str] | None:
    """ARPAbet phones from 'B.EY1.S' (or 'B EY1 S'), or None if it isn't ARPAbet."""
    parts = [p for p in re.split(r"[.\s]+", say.strip()) if p]
    if not parts or not all(_PHONE.fullmatch(p) for p in parts):
        return None
    phones = []
    for p in parts:
        base, digit = _PHONE.fullmatch(p).groups()
        if base in ph.VOWELS and digit:
            phones.append(p)
        elif base in ph.CONSONANTS and not digit:
            phones.append(p)
        else:
            return None
    return phones if any(p[-1].isdigit() for p in phones) else None


def readings(token: str) -> list[list[str]] | None:
    """The readings a word's say gives it (None: no say; []: a say the singer can't read). A sense of the
    word, ARPAbet, or a word or hyphened words it sounds like."""
    say = say_of(token)
    if say is None:
        return None
    word = ph.clean(bare(token).replace("-", "").replace("*", ""))
    entry = TABLE["words"].get(word)
    if entry:
        for s in entry["senses"]:
            if s["name"] == say.strip().lower():
                return [s["phones"].split()]
    phones = _arpabet(say)
    if phones is not None:
        return [phones]
    like = say.strip()
    if not re.fullmatch(r"[A-Za-z'’]+(-[A-Za-z'’]+)*", like):
        return []
    return ph.pronunciations(like.lower())


def problem(token: str, n: int) -> str | None:
    """What's wrong with a word's say, in the words editor's words, or None. n: its syllables (notes)."""
    says = SAY.findall(token)
    word = bare(token).replace("*", "").strip(".,;:!?\"()")
    if len(says) > 1 or "{" in word or "}" in word:
        return "give a word one say in braces, like bass{fish}"
    if not says:
        return None
    if not ph.clean(word.replace("-", "")):
        return "put a say in braces right after its word, like bass{fish}"
    found = readings(token)
    if not found:
        senses = TABLE["words"].get(ph.clean(word.replace("-", "")), {}).get("senses", [])
        named = "".join(f"{word}{{{s['name']}}}, " for s in senses)
        return f"the singer can't read {{{says[0]}}}: try {named}or a word that sounds right, like bass{{base}}"
    try:
        sung = len(ph.fit(token, n))
    except (KeyError, ValueError):
        sung = 0
    if sung != n:
        said = sum(p.rstrip("012") in ph.VOWELS for p in found[0])
        return f"{{{says[0]}}} says {said} syllable{'s' if said != 1 else ''}; {word!r} is sung on {n}"
    return None


def normalized(line: str) -> str:
    """A line with ARPAbet in braces written with dots: 'bass{B EY1 S}' -> 'bass{B.EY1.S}' (a line is split
    into words at spaces, so a say can't keep them)."""
    return SAY.sub(lambda m: "{" + ".".join(m.group(1).split()) + "}", line)
