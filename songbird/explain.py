"""The song's choices in plain words, and why each was made (for the studio).

A rendition is decided by its parent, its machine, time and chance (see
realize.choose_params and variation). The studio shows each choice as a
person would say it, and why it was made:

- a number the table works out (tempo, the key's note, the band's density,
  the mix...) is traced as it is made (variation's trace): what it was in the
  parent, how far the machine pulled it and how far time moved it, each said
  only when it is enough to hear, with its direction;
- a choice among a few (the mode, the shape, the band's pattern and lead,
  the words' mood) is asked again three ways: without time (the drift held
  still), without the machine (one with no signals, at the same moment) and
  as the parent had it. What changes when the machine is taken away is its
  doing; what changes when time stands still is time's;
- the words and every small detail of the sound are chance; anything a
  person changed is theirs (songbird.edits), with what the program chose.

The words here are the page's: the song, the song as it began, the version
before, your machine, time (today, these weeks, this season, this year),
chance, and you; never the code's names for them (docs/STUDIO.md). A Params
field this module doesn't know yet still gets a card, in plain values.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import date as _date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import arrange as arrange_mod
from . import drift as drift_mod
from . import edits as edits_mod
from . import harvest, phrasing as phrasing_mod, variation
from .arrange import options as word_choices, seed_lyrics
from .band import INSTRUMENTS
from .synth.mixing import MixParams
from .synth.voice import VoiceParams

TIMELINE_DAYS = 1095  # three years either way

# ---------------------------------------------------------------- the page's words

NOTES = ("C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")
MODES = {
    "ionian": ("major", "the plain major"),
    "mixolydian": ("mixolydian", "a major with a softer seventh: the old folk major"),
    "dorian": ("dorian", "a minor with a brighter sixth: the folk minor"),
    "aeolian": ("minor", "the plain minor"),
    "lydian": ("lydian", "a major with a raised fourth: bright and open"),
    "phrygian": ("phrygian", "a minor with a lowered second: dark and old"),
    "locrian": ("locrian", "the darkest of the modes"),
}
MINOR = {"dorian", "aeolian", "phrygian", "locrian"}
FAMILIES = {"folk": "folk", "bright": "bright", "dark": "darker"}  # the mode families, as the page says them
LANGUAGES = {
    "english": "English", "germanic": "Germanic languages", "celtic": "Celtic languages",
    "romance": "Romance languages", "slavic": "Slavic or Baltic languages", "west_asian": "West Asian languages",
    "south_asian": "South Asian languages", "east_asian": "East Asian languages", "other": "its languages",
}
PLAYERS = {"lute": "lute", "guitar": "guitar", "harp": "harp", "bass": "bass", "fiddle": "fiddle",
           "whistle": "whistle", "drum": "frame drum", "drone": "drone",
           # the styles' players (songbird.style), as a person would name them
           "arp": "arpeggiated synth", "synthpad": "synth pad", "synthbass": "synth bass", "synthlead": "synth lead",
           "drummachine": "drum machine", "epiano": "electric piano", "ebass": "electric bass",
           "electric": "electric guitar", "kit": "drum kit", "steel": "pedal steel", "slide": "slide guitar",
           "glock": "glockenspiel", "vibes": "vibraphone", "musicbox": "music box", "stomps": "stomping feet",
           "claps": "hand claps", "strings": "string section", "banjo": "banjo", "mandolin": "mandolin",
           "cello": "cello", "piano": "piano", "organ": "organ", "harmonica": "harmonica", "concertina": "concertina",
           "celesta": "celesta", "tambourine": "tambourine", "accordion": "accordion", "harmonium": "harmonium"}
# The styles, as the page names them (songbird/style.py STYLES), and their feels
STYLE_NAMES = {"ballad": "the ballad band, the song's own", "stringband": "a string band", "country": "country",
               "gospel": "gospel", "shanty": "a sea shanty", "songwriter": "a singer-songwriter",
               "chamber": "chamber folk", "lullaby": "a lullaby", "ambient": "ambient", "synthfolk": "synth folk",
               "lofi": "lo-fi", "indie": "indie folk", "blues": "country blues"}
FEEL_NAMES = {"straight": "played straight", "swing": "swung", "shuffle": "a shuffle", "twelve": "in twelve-eight",
              "half": "half-time", "double": "double-time", "waltz": "a waltz", "six": "in six-eight"}
ENDING_NAMES = {"ring": "the last chord rings", "rit": "it slows broadly to the end", "cold": "it stops dead",
                "amen": "it ends on an amen", "repeat": "the last line is sung again"}
BACKING_NAMES = {"oohs": "backing voices on oohs", "echo": "backing voices echo the lines",
                 "thirds": "backing voices in harmony", "gang": "everyone sings along"}
PATTERNS = {"lilt": "a lilting strum", "strum": "a steady strum", "pick": "fingerpicking", "air": "a slow air"}
PATTERN_DETAIL = {"lilt": "the strum follows the tune's long-short-short", "strum": "the old faithful strum",
                  "pick": "picked strings, no strumming", "air": "rolled chords and held notes, no drum"}
SECTIONS = {"intro": "Intro", "verse": "Verse", "refrain": "Refrain", "turn": "Turn", "break": "Break",
            "bridge": "Bridge", "bridge2": "Bridge again", "tag": "Tag", "outro": "Outro"}
PARTS = {"verses": "how many verses", "pairs": "verses in pairs", "intro": "an intro",
         "turn": "a turn after the refrains", "break": "a break before the bridge", "bridge2": "the bridge twice",
         "tag": "everyone singing the tag", "outro": "an outro"}
SHORT = {"pairs": "verses in pairs", "intro": "an intro", "turn": "the turns", "break": "a break",
         "bridge2": "the bridge twice", "tag": "the tag", "outro": "an outro"}  # the parts, as a reason says them
VIEWS = {"full": "today", "slow": "these weeks", "season": "this season", "year": "this year"}
THEMES = {"sea": "the sea", "fire": "fire", "machines": "machines", "earth": "the land", "home": "home",
          "town": "the town", "music": "music", "past": "the past"}  # harvest.THEMES, as the page says them
KINDS = {"you": "you", "machine": "your machine", "time": "time", "parent": "kept", "song": "the song",
         "chance": "chance", "rule": "the song's rule", "lineage": "the versions before"}
# Params fields a card below speaks for; any other gets a plain card of its own
KNOWN = {"tonic", "mode", "tempo", "form", "seed", "accomp", "humanize", "ritardando", "choir", "band", "singer",
         "mix", "leanings", "lay", "inventory", "variants", "words", "generation", "made", "style"}
KNOWN_BAND = {*INSTRUMENTS, "brightness", "pattern", "density", "swing", "wear", "ornament", "arc", "lead", "body",
              "maker", "lineup"}
# How big a pull or a push must be to be heard, per number (smaller ones are said to have kept it as it was)
HEARD = {"tempo": 1.0, "tonic": 0.5, "band.density": 0.04, "band.brightness": 0.04, "mix.space": 0.04,
         "mix.width": 0.04, "mix.forward": 0.25, "mix.intimacy": 0.04, "mix.tilt": 0.15, "mix.wear": 0.04,
         "mix.predelay": 0.004, "leanings.era_bias": 0.1, "leanings.rarity_appetite": 0.1}


ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
            "eleventh", "twelfth")  # a record's generation 0 is the first version


def number(n: int) -> str:
    return ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
            "twelve")[n] if 0 <= n <= 12 else str(n)


def listed(items: list[str], last: str = "and") -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {last} {items[-1]}"


@lru_cache(maxsize=256)
def player(name: str) -> str:
    """An instrument as a person would name it: the page's own name, else the first words its maker used."""
    if name in PLAYERS:
        return PLAYERS[name]
    try:
        from .synth.instruments import spec

        about = str(spec(name).get("about") or name)
    except (ValueError, KeyError):
        about = name
    about = about.split(":")[0].split("(")[0].split(",")[0].strip()
    for article in ("a ", "an ", "the "):
        if about.lower().startswith(article):
            about = about[len(article):]
    return (about or name).replace("_", " ").replace("-", " ")


def note(midi: int) -> str:
    return NOTES[int(midi) % 12]


def key_words(tonic: int, mode: str) -> str:
    """'D major', 'E mixolydian', 'B minor'."""
    return f"{note(tonic)} {MODES.get(mode, (mode, ''))[0]}"


def mode_gloss(mode: str) -> str:
    return MODES.get(mode, (mode, mode))[1]


def tempo_words(bpm: float) -> str:
    feel = ("slow" if bpm < 76 else "an easy walk" if bpm < 90 else "a steady walk" if bpm < 104
            else "brisk" if bpm < 116 else "quick")
    return f"{bpm:.0f} beats a minute: {feel}"


def shape_words(parts: dict | None) -> str:
    """'three verses, with an intro, a turn after the refrains and the bridge twice'."""
    if not parts:
        return "a shape of its own"
    verses = f"{number(parts.get('verses', 0))} verse{'s' if parts.get('verses') != 1 else ''}"
    extras = [PARTS[k] for k in ("pairs", "intro", "turn", "break", "bridge2", "tag", "outro") if parts.get(k)]
    return f"{verses}, with {listed(extras)}" if extras else f"{verses}, and nothing more"


def density_words(x: float) -> str:
    return ("very sparse" if x < 0.2 else "sparse" if x < 0.38 else "moderate" if x < 0.62 else "busy" if x < 0.8
            else "very busy")


def brightness_words(x: float) -> str:
    return ("dark and soft" if x < 0.25 else "warm" if x < 0.45 else "clear" if x < 0.6 else "bright" if x < 0.8
            else "very bright")


def players(band, style=None) -> list[str]:
    """Who is in the band: a style's lineup in its own order, else the eight."""
    if band.lineup:
        from .style import of

        return of(style).order(band.lineup) if style is not None else sorted(band.lineup)
    return list(INSTRUMENTS)


def leader(band, style=None) -> str | None:
    """Who states the tune where nobody sings: the style's leads, or the band's lead, the first that plays."""
    if band.lineup and style is not None:
        from .style import of

        return next((n for n in of(style).leads if band.plays(n)), None)
    if band.plays(band.lead):
        return band.lead
    return next((n for n in ("whistle", "fiddle", "lute") if band.plays(n)), None)


def band_words(band, style=None) -> str:
    """'a steady strum with the whistle leading; moderate and clear; all eight play', or for a style's band
    'the fiddle leading; busy and bright; bass, banjo, mandolin, guitar and fiddle play'."""
    everyone = players(band, style)
    playing = [n for n in everyone if band.plays(n)]
    if not playing:
        return "no band: the voice alone"
    out = [n for n in everyone if n not in playing]
    lead = leader(band, style)
    leading = f"the {player(lead)} leading" if lead else ""
    colour = f"{density_words(band.density)} and {brightness_words(band.brightness)}"
    if band.lineup:
        who = f"{listed([player(n) for n in playing])} play"
        if out:
            who += f", the {listed([player(n) for n in out])} sitting out"
        return "; ".join(x for x in (leading, colour, who) if x)
    who = (f"all {number(len(INSTRUMENTS))} play" if not out
           else f"the {listed([player(n) for n in out])} sit{'s' if len(out) == 1 else ''} out")
    return (f"{PATTERNS.get(band.pattern, band.pattern)}{' with ' + leading if leading else ''}; {colour}; {who}")


def room_words(rt60: float) -> str:
    return ("a small, dry room" if rt60 < 0.6 else "a room like a living room" if rt60 < 1.0
            else "a warm hall" if rt60 < 1.6 else "a big hall" if rt60 < 2.2 else "a church")


def mix_words(mix) -> str:
    """'a warm hall; the voice close and well over the band; wide'."""
    near = "close" if mix.intimacy > 0.6 else "further back" if mix.intimacy < 0.4 else ""
    over = "well over the band" if mix.forward > 11 else "among the band" if mix.forward < 8.5 else "over the band"
    space = "little of it heard" if mix.space < 0.75 else "much of it heard" if mix.space > 1.2 else ""
    width = "wide" if mix.width > 1.12 else "narrow" if mix.width < 0.85 else ""
    wear = "worn like an old tape" if mix.wear > 0.3 else "a little worn" if mix.wear > 0.12 else ""
    voice = f"the voice {listed([near, over])}"
    room = f"{room_words(mix.rt60)}, {space}" if space else room_words(mix.rt60)
    return "; ".join(x for x in (room, voice, width, wear) if x)


def singer_words(singer) -> str:
    """'a high voice, clear, with a gentle vibrato'."""
    size = "small" if singer.tract > 1.14 else "big" if singer.tract < 1.03 else ""
    register = f"a {size + ', ' if size else ''}{'low' if singer.shift <= -12 else 'high'} voice"
    press = "pressed and bright" if singer.rd < 0.68 else "breathy" if singer.rd > 0.95 else "clear"
    depth = "light" if singer.vibrato_depth < 22 else "wide" if singer.vibrato_depth > 36 else "gentle"
    rate = "quick" if singer.vibrato_rate > 5.6 else "slow" if singer.vibrato_rate < 5.0 else ""
    voice = f"{register}, {press}, with a {listed([rate, depth])} vibrato"
    if getattr(singer, "engine", "formant") == "learned":
        blend = [part.split(":")[0] for part in str(singer.timbre or "").split(",") if part and ":" in part
                 and not part.startswith("machine")]
        voice += "; the learned voice" + (f", a blend of {number(len(blend))} singers it learned from" if len(blend) > 1
                                           else "")
    return voice


def lean_words(leanings: dict) -> str:
    """Which way the words lean: 'a little lighter, older and rarer'."""
    if not leanings:
        return "no particular way"
    moods = leanings.get("mood_weights", {})
    light, dark, tender = moods.get("light", 1.0), moods.get("dark", 1.0), moods.get("tender", 1.0)
    parts = ["lighter" if light / max(dark, 1e-6) > 1.25 else "darker" if dark / max(light, 1e-6) > 1.25 else "",
             "tenderer" if tender > 1.15 else ""]
    era, rare = leanings.get("era_bias", 0.0), leanings.get("rarity_appetite", 0.0)
    parts += ["newer" if era > 0.15 else "older" if era < -0.15 else "",
              "rarer" if rare > 0.15 else "commoner" if rare < -0.15 else ""]
    parts = [p for p in parts if p]
    return f"a little {listed(parts)}" if parts else "no particular way"


def machine_words(voice) -> list[str]:
    """What a machine is, as its few kept numbers say it, one plain line each."""
    if voice is None or voice.neutral:
        return ["nothing is read from it, so the song is moved by time alone"]
    out = []
    if voice.tongue:
        modes = f"{FAMILIES.get(voice.tongue.family, voice.tongue.family)} modes"
        speaks = LANGUAGES.get(voice.tongue.inventory)
        out.append(f"it speaks {speaks}, and leans to {modes}" if voice.tongue.inventory in LANGUAGES
                   and voice.tongue.inventory != "other" else f"its languages lean to {modes}")
    if voice.machine:
        size = voice.machine.cores + voice.machine.memory
        up = {0.0: "restarted today", 0.5: "up for days", 1.0: "up for more than a week"}.get(voice.machine.uptime, "")
        out.append(", ".join(x for x in (f"{'a big' if size > 1.3 else 'a small' if size < 0.7 else 'a middling'} machine", up) if x))
    if voice.ages:
        days = 10 ** voice.ages.median
        age = ("weeks" if days < 60 else "months" if days < 300 else "a year or two" if days < 900
               else "several years" if days < 3000 else "many years")
        out.append(f"its files are mostly {age} old")
    if voice.colour:
        light = "dark" if voice.colour.brightness < 0.3 else "light" if voice.colour.brightness > 0.7 else "middling"
        hue = max(("warm", voice.colour.warm), ("green", voice.colour.green), ("cool", voice.colour.cool),
                  key=lambda x: x[1])
        out.append(f"a {light} screen, {hue[0] if hue[1] > 0.4 else 'mixed'} in colour")
    if voice.words:
        even = 1.0 / max(len(voice.words.themes), 1)
        themes = [THEMES.get(t, t) for t, share in sorted(voice.words.themes.items(), key=lambda x: -x[1])
                  if share > even * 1.2][:3]
        rich = "a rich" if voice.words.richness > 0.6 else "a plain" if voice.words.richness < 0.35 else "an everyday"
        out.append(f"{rich} vocabulary" + (f", leaning to {listed(themes)}" if themes else ""))
    if voice.hand:
        speed = "quickly" if voice.hand.interval < 160 else "slowly" if voice.hand.interval > 260 else "steadily"
        even = "and evenly" if voice.hand.unevenness < 0.4 else "and unevenly" if voice.hand.unevenness > 0.6 else ""
        out.append(f"typing {speed} {even}".strip())
    if voice.room:
        out.append(f"{room_words(voice.room.rt60)} ({voice.room.rt60:.1f} s to fall quiet)")
    else:
        out.append("its room isn't heard yet, so it sings in the room of the version before")
    return out


def plain(value) -> str:
    """Any value as plain words, for a choice this module has no words of its own for."""
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, dict):
        return "; ".join(f"{str(k).replace('_', ' ')} {plain(v)}" for k, v in value.items()) or "none"
    if isinstance(value, (list, tuple)):
        return ", ".join(plain(v) for v in value) or "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value).replace("_", " ")


def long_date(day: str) -> str:
    d = _date.fromisoformat(day)
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}"


def distance(days: int) -> str:
    """'today', 'tomorrow', 'in five months', 'two years ago'."""
    if days == 0:
        return "today"
    if abs(days) == 1:
        return "tomorrow" if days > 0 else "yesterday"
    n = abs(days)
    if n < 14:
        amount = f"{number(n)} days"
    elif n < 60:
        amount = f"{number(round(n / 7))} weeks"
    elif n < 350:
        amount = f"{number(round(n / 30.44))} months"
    else:
        half = max(1.0, round(n / 365.25 * 2) / 2)
        whole = int(half)
        amount = ("a year" if half == 1 else "a year and a half" if half == 1.5 else
                  f"{number(whole)} years" if half == whole else f"{number(whole)} and a half years")
    return f"in {amount}" if days > 0 else f"{amount} ago"


def readable(line: str) -> str:
    """A sung line as it reads: its syllables joined into words, a real hyphen kept where the joined word
    isn't one and its two halves are (six-ty-odd reads sixty-odd); *focus* marks kept for the page."""
    return " ".join(_word(token) for token in line.split(" "))


@lru_cache(maxsize=8192)
def _word(token: str) -> str:
    if "-" not in token:
        return token
    words = harvest._dictionary()
    start = len(token) - len(token.lstrip("*\"'("))
    end = len(token.rstrip("*.,;:!?\"')"))
    head, core, tail = token[:start], token[start:end], token[end:]
    parts = core.split("-")
    joined = "".join(parts)
    if joined.lower() not in words:
        for k in range(1, len(parts)):
            left, right = "".join(parts[:k]), "".join(parts[k:])
            if left.lower() in words and right.lower() in words:
                return f"{head}{left}-{right}{tail}"
    return f"{head}{joined}{tail}"


# ---------------------------------------------------------------- a version: the program's choices, then a person's


def still(d):
    """The same moment with time standing still: every dimension of the drift at zero, and no past to read."""
    zero = {k: 0.0 for k in d.full}
    return drift_mod.Drift(t=d.t, full=zero, slow=dict(zero), season=dict(zero), year=dict(zero), hash="")


def singer_of(params) -> VoiceParams:
    from .cli import _singer

    return _singer(params, [])


def drawn_words(genome, params):
    """The words a machine sings with these params: drawn from the bank, or None for the song's own."""
    from .cli import words

    return words(genome, params, sung_by_a_machine=True)


def as_sung(genome, params, lyrics):
    """Words to show: the drawn ones, or the song's own for the form (named for the bank's entries)."""
    from .composition import lyric_overlay

    return lyric_overlay(genome, params, lyrics) or seed_lyrics(genome, params.form)


@dataclass
class Version:
    """One rendition as the page has it: the program's choices, and a person's on top."""

    context: Context
    edits: dict  # the edits, checked
    voice: object
    drift: object
    day: str  # the date sung, YYYY-MM-DD
    generated: object  # Params: the program's own choices
    params: object  # Params: what will be sung
    generated_lyrics: object  # Lyrics or None (the song's own words)
    lyrics: object  # Lyrics or None: what will be sung
    phrasing_json: dict | None
    trace: dict = field(default_factory=dict)  # each number's arithmetic (variation.Knob)
    problems: list = field(default_factory=list)
    applied: list = field(default_factory=list)
    marks: dict = field(default_factory=dict)
    changes: list = field(default_factory=list)  # what the program changed in the tune and the words, with why
    _cf: dict = field(default_factory=dict, repr=False)

    @property
    def choir_json(self) -> list[dict]:
        """The parent's portable choir delivery, shared by preview and recording."""
        return phrasing_mod.inherited(self.context.genome.source, self.context.parent_record)[1]

    @property
    def offset(self) -> int:
        return (_date.fromisoformat(self.day) - _date.fromisoformat(self.context.day)).days

    def without(self, what: str):
        """The program's choice with something taken away: "time" (standing still), "machine" (one with no
        signals, at the same moment); "both" is the parent's own."""
        if what not in self._cf:
            ctx = self.context
            if what == "time":
                self._cf[what] = ctx.choose(self.voice, still(self.drift))
            elif what == "machine":
                self._cf[what] = ctx.choose(harvest.Voice(), self.drift)
            else:
                self._cf[what] = ctx.base
        return self._cf[what]

    def mine(self, *prefixes: str) -> list[str]:
        """The edits that took effect under these paths."""
        return [p for p in self.applied if any(p == x or p.startswith(x) for x in prefixes)]

    @property
    def held(self) -> set[str]:
        """Word edits that hold the words as the program drew them ("keep these words"): kept, not changed."""
        return {p for p in self.applied if p.startswith("words.") and p in self.marks
                and self.marks[p].get("value") == self.marks[p].get("was")}

    @property
    def changed(self) -> list[str]:
        """The edits that changed something: not the day, not chance drawn again, not words held as they were."""
        return [p for p in self.applied if p not in ("date", "roll") and p not in self.held]

    def troubles(self, *prefixes: str) -> list[dict]:
        return [p for p in self.problems if any(p["path"] == x or p["path"].startswith(x) for x in prefixes)]


@dataclass
class Context:
    """What the studio was opened on: the song, its parent, the machine, and today."""

    genome: object
    parent: object  # Params or None
    parent_record: dict | None
    voice: object
    machine: str
    day: str  # today's date, YYYY-MM-DD
    t: float  # today's instant: noon UTC today
    quiet: bool = False  # the machine was read only in part (its languages, size and screen)

    def __post_init__(self):
        self.song = edits_mod.song_params(self.genome)
        self.base = self.parent if self.parent is not None else self.song

    def instant(self, day: str) -> float:
        return self.t if day == self.day else drift_mod.parse(day)

    def choose(self, voice, d, trace: dict | None = None):
        """The program's own choices for a machine at a moment (the edits aside)."""
        return variation.choose(self.genome, self.parent, voice, d, trace=trace)

    def version(self, edits: dict | None = None, voice=None, phrasings: dict | None = None) -> Version:
        """The rendition on the day the edits name (today if none), by this machine or another, with the
        edits in place: each checked, applied if it can be kept, and said why if not."""
        genome = self.genome
        phrasings = phrasings or {}
        clean, problems = edits_mod.check(genome, dict(edits or {}), phrasings)
        day = clean.pop("date", self.day)
        if day != self.day:
            clean["date"] = day
        voice = voice if voice is not None else self.voice
        d = drift_mod.drift(self.instant(day), (voice if voice is not None else harvest.Voice()).hash)
        chosen_phrasing = json.loads(Path(phrasings[clean["phrasing"]]).read_text()) if "phrasing" in clean else None
        trace: dict = {}
        changes: list = []
        r = edits_mod.resolve(genome, self.parent, voice, d, clean, phrasing_json=chosen_phrasing, trace=trace,
                              day_chosen="date" in clean, log=changes)
        inherited_lead, _ = phrasing_mod.inherited(genome.source, self.parent_record)
        phrasing_json = chosen_phrasing if chosen_phrasing is not None else inherited_lead
        return Version(self, clean, voice, d, day, r.generated, r.params, r.generated_lyrics, r.lyrics, phrasing_json,
                       trace, problems + r.problems, r.applied, r.marks, changes)

    # ------------------------------------------------------------ labels

    def from_words(self) -> str:
        if self.parent_record is None:
            return "from the song as it began"
        made = (self.parent_record.get("rendered_at") or "")[:10]
        generation = self.parent_record.get("generation")
        which = (f"the {ORDINALS[generation]} version" if isinstance(generation, int) and generation < len(ORDINALS)
                 else "a version before")
        return f"from {which}, made {long_date(made)}" if made else f"from {which}"

    def machine_label(self) -> str:
        spec = self.machine
        if spec == "here":
            return "this machine"
        if spec in ("none", "neutral"):
            return "no machine, only time"
        if spec.startswith("fictional:"):
            return f"a made-up machine called {spec.split(':', 1)[1].title()}"
        return "the machine its record names"

    def opening(self) -> str:
        return f"your version today ({long_date(self.day)}), {self.from_words()}, sung by {self.machine_label()}"


# ---------------------------------------------------------------- why


def _kept(v: Version, path: str | None = None) -> dict:
    ctx = v.context
    if ctx.parent is None:
        return {"kind": "song", "text": "the song's own, as it began"}
    marked = (ctx.parent_record or {}).get("chosen_by_you") or {}
    if path and any(p == path or p.startswith(path + ".") for p in marked):
        return {"kind": "lineage", "text": "kept from the version before, where a person chose it"}
    return {"kind": "parent", "text": "kept from the version before"}


def _read(params, path: str):
    if path == "form":
        return tuple(params.form)
    if path == "style.name":  # the song's own arrangement is the ballad band, named or not
        return params.style.name or "ballad"
    head, _, tail = path.partition(".")
    if tail and head not in ("singer", "mix", "leanings", "band"):
        value = getattr(params, head)
        value = asdict(value) if is_dataclass(value) else value
        return value.get(tail) if isinstance(value, dict) else None
    return variation.read(params, path) if tail else getattr(params, path)


def pulls(v: Version, path: str) -> tuple[float, float] | None:
    """How far the machine pulled a number from the parent's and how far time moved it (the child hears
    PULL of both, for a number it inherits), from the table's own arithmetic; None if the table didn't make it."""
    t = v.trace.get(path)
    if t is None:
        return None
    share = variation.PULL if t["inherit"] else 1.0
    return share * (t["own"] - t["was"]), share * (t["moved"] - t["own"])


def number_reasons(v: Version, path: str, machine, time) -> list[dict]:
    """Why a number is what it is: the machine's pull and time's push, each said with its direction when it
    is big enough to hear (HEARD); if neither is, it was kept."""
    parts = pulls(v, path)
    if parts is None:
        return []
    heard = HEARD.get(path, 0.03)
    m, t = parts
    out = []
    if abs(m) >= heard and machine is not None:
        text = machine(m)
        if text:
            out.append({"kind": "machine", "text": text})
    if abs(t) >= heard and time is not None:
        text = time(t)
        if text:
            out.append({"kind": "time", "text": text})
    if len(out) == 2 and m * t < 0 and abs(m + t) < heard:
        out.append({"kind": "parent", "text": "so in the end it is about as it was"})
    return out


def choice_reasons(v: Version, paths: list[str], machine=None, time=None, label=None) -> list[dict]:
    """Why a choice among a few is what it is, by asking again without time and without the machine.
    label(path, value) names the choice when neither alone explains it."""
    now, parent = v.generated, v.without("both")
    out: list[dict] = []
    for path in paths:
        value = _read(now, path)
        if value == _read(parent, path):
            continue
        blind, frozen = _read(v.without("machine"), path), _read(v.without("time"), path)
        said = False
        if value != blind and machine is not None:
            text = machine(path, value, blind)
            if text:
                out.append({"kind": "machine", "text": text})
                said = True
        if value != frozen and time is not None:
            text = time(path, value, frozen)
            if text:
                out.append({"kind": "time", "text": text})
                said = True
        if not said:
            what = label(path, value) if label else plain(value)
            out.append({"kind": "machine", "text": f"{what}: your machine and time together"})
    return out


def _unique(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for item in items:
        key = (item["kind"], item["text"])
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _finish(v: Version, why: list[dict], path: str | None = None) -> list[dict]:
    return _unique(why) or [_kept(v, path)]


def _when(view: str) -> str:
    return VIEWS[view]


def _drift_at(v: Version, view: str, dimension: str) -> float:
    return v.drift.view(view).get(dimension, 0.0) if v.drift is not None else 0.0


def _mine(v: Version, paths: list[str], show) -> list[dict]:
    """'chosen by you' for each edit under these paths, with what the program had chosen."""
    out = []
    for path in paths:
        mark = v.marks.get(path)
        if mark is None:
            continue
        was = show(path, mark.get("was"))
        out.append({"kind": "you", "text": f"chosen by you; the program chose {was}" if was else "chosen by you",
                    "path": path})
    return out


def _card(v: Version, id: str, title: str, value: str, detail: str, reasons: list[dict], paths: list[str],
          **extra) -> dict:
    mine = v.mine(*paths) if paths else []
    return {"id": id, "title": title, "value": value, "detail": detail, "reasons": reasons, "mine": bool(mine),
            "paths": mine, "problems": v.troubles(*paths) if paths else [], **extra}


# ---------------------------------------------------------------- the cards


def key_card(v: Version) -> dict:
    p, c = v.params, variation.character(v.voice)
    why = number_reasons(
        v, "tonic",
        lambda m: f"your machine's singer is comfortable a little {'higher' if m > 0 else 'lower'}",
        lambda t: f"{_when('year')} sits it a little {'higher' if t > 0 else 'lower'}")

    def machine(path, value, blind):
        return (f"your machine's languages lean to {FAMILIES.get(c.family, c.family)} modes" if c.family
                else "your machine's own leaning")

    def time(path, value, frozen):
        return f"{_when('year')} leans {'brighter' if variation.BRIGHTNESS[value] > variation.BRIGHTNESS[frozen] else 'darker'}"

    why += choice_reasons(v, ["mode"], machine, time, lambda path, value: f"the {MODES.get(value, (value,))[0]} mode")
    mine = _mine(v, ["tonic", "mode"], lambda path, was: note(was) if path == "tonic" else MODES.get(was, (was,))[0])
    return _card(v, "key", "Key", key_words(p.tonic, p.mode), mode_gloss(p.mode), mine + _finish(v, why, "mode"),
                 ["tonic", "mode"], tonic=p.tonic, mode=p.mode)


def tempo_card(v: Version) -> dict:
    p, c = v.params, variation.character(v.voice)

    def machine(m):
        voice = v.voice
        sources = []  # the signals that pushed the same way as the machine's pull, as the table reads them
        if voice is not None and voice.ages and (voice.ages.median < 2.3) == (m > 0):
            sources.append("new files" if m > 0 else "old files")
        if voice is not None and voice.hand and (voice.hand.interval < 220) == (m > 0):
            sources.append("quick hands" if m > 0 else "slow hands")
        return f"{'a brisk' if m > 0 else 'an unhurried'} machine" + (f" ({listed(sources)})" if sources else "")

    why = number_reasons(v, "tempo", machine, lambda t: f"{_when('full')} is a little {'quicker' if t > 0 else 'slower'}")
    name = p.style.name or "ballad"
    if name != "ballad" and "tempo" not in v.applied:  # a style takes the song at its own pace (songbird.style)
        song = v.context.song.tempo
        pace = "quicker" if p.tempo > song * 1.03 else "slower" if p.tempo < song * 0.97 else "at about the song's own pace"
        why = [{"kind": "you" if "style.name" in v.applied else "rule",
                "text": f"{STYLE_NAMES.get(name, name)} takes the song {pace}"
                        + (" than it began" if pace in ("quicker", "slower") else "")}] + why
    mine = _mine(v, ["tempo"], lambda path, was: f"{was:.0f}")
    return _card(v, "tempo", "Tempo", tempo_words(p.tempo), "", mine + _finish(v, why, "tempo"), ["tempo"],
                 tempo=p.tempo)


def shape_card(v: Version) -> dict:
    genome = v.context.genome
    parts = edits_mod.shape(genome, v.params.form)
    generated = edits_mod.shape(genome, v.generated.form) or {}
    parent = edits_mod.shape(genome, v.without("both").form) or {}
    blind = edits_mod.shape(genome, v.without("machine").form) or {}
    frozen = edits_mod.shape(genome, v.without("time").form) or {}
    c = variation.character(v.voice)
    why: list[dict] = []
    for name in ("verses", *edits_mod.optional(genome)):
        value = generated.get(name)
        if value == parent.get(name):
            continue
        what = (f"{number(value)} verses, not {number(parent.get(name, 0))}" if name == "verses"
                else f"{'with' if value else 'without'} {SHORT.get(name, PARTS[name])}")
        machine = value != blind.get(name)
        time = value != frozen.get(name)
        if machine:
            source = ("a rich vocabulary tells a longer story" if name == "verses" and "richness" in c.known and value > parent.get(name, 0)
                      else "a plain vocabulary tells a shorter one" if name == "verses" and "richness" in c.known
                      else "your machine's habit")
            why.append({"kind": "machine", "text": f"{what}: {source}"})
        if time:
            why.append({"kind": "time", "text": f"{what}: {_when('season')}"})
        if not machine and not time:
            why.append({"kind": "time", "text": f"{what}: your machine and {_when('season')} together"})
    def chosen(part: str, value) -> str:  # what the person chose for a part, as they chose it
        if part == "order":
            return "your section arrangement" if value else "the song's section arrangement"
        if part == "verses":
            return f"{number(value)} verses"
        return f"{'with' if value else 'without'} {SHORT.get(part, PARTS.get(part, part))}"

    mine = [{"kind": "you", "text": f"{chosen(p[5:], v.edits.get(p))}: chosen by you", "path": p}
            for p in v.mine("form.")]
    return _card(v, "shape", "Shape", shape_words(parts), _form_line(v.params.form), mine + _finish(v, why, "form"),
                 ["form."], parts=parts or {}, choices=edits_mod.shapes(genome, v.params.form))


def _form_line(form) -> str:
    return " · ".join(SECTIONS.get(name, name.title()) for name in form)


def band_card(v: Version) -> dict:
    band, c = v.params.band, variation.character(v.voice)
    why = number_reasons(
        v, "band.density",
        lambda m: f"a {'busy' if m > 0 else 'quiet'} machine plays {'busier' if m > 0 else 'sparer'}"
        if "density" in c.known else "your machine's own band",
        lambda t: f"{_when('slow')}, it plays a little {'busier' if t > 0 else 'sparer'}")
    why += number_reasons(
        v, "band.brightness",
        lambda m: f"your screen makes the band {'brighter' if m > 0 else 'darker'}" if "brightness" in c.known
        else "your machine's own band",
        lambda t: f"{_when('full')} the band sounds a little {'brighter' if t > 0 else 'darker'}")

    def machine(path, value, blind):
        return (f"your machine's own band plays {PATTERNS.get(value, value)}" if path == "band.pattern"
                else f"your machine's own band has the {player(value)} lead")

    def time(path, value, frozen):
        return (f"{_when('slow')} lean to {PATTERNS.get(value, value)}" if path == "band.pattern"
                else f"{_when('year')}, the {player(value)} leads")

    style = v.params.style
    if not band.lineup:  # the ballad band's own pattern and lead; a style's band is the style's (its own card)
        why = choice_reasons(v, ["band.pattern", "band.lead"], machine, time,
                             lambda path, value: PATTERNS.get(value, value) if path == "band.pattern"
                             else f"the {player(value)} leading") + why
    else:
        why = [{"kind": "rule", "text": f"the players are {STYLE_NAMES.get(style.name, style.name)}'s own"}] + why
    names = {"band.pattern": lambda w: PATTERNS.get(w, w), "band.lead": lambda w: f"the {player(w)}",
             "band.density": density_words, "band.brightness": brightness_words}
    mine = _mine(v, list(names), lambda path, was: names[path](was) if was is not None else None)
    everyone = players(band, style)
    benched = [p for p in v.mine("band.") if p[5:] in everyone]
    if benched:
        mine.append({"kind": "you", "text": "who plays: chosen by you", "path": benched[0]})
    lead = leader(band, style)
    if band.lineup:
        detail = ""
    else:
        detail = PATTERN_DETAIL.get(band.pattern, "")
        if lead and lead != band.lead:
            detail = f"the {player(band.lead)} sits out, so the {player(lead)} takes the tune; {detail}"
    extra = {k: val for k, val in band.to_dict().items() if k not in KNOWN_BAND}
    if extra:
        detail += f"; also {plain(extra)}"
    return _card(v, "band", "The band", band_words(band, style), detail, mine + _finish(v, why, "band"), ["band."],
                 band={**band.to_dict(), **{n: band.gain(n) for n in everyone}}, leader=lead,
                 players={n: player(n) for n in everyone}, styled=bool(band.lineup))


def style_card(v: Version) -> dict:
    """The tradition the song is played in (songbird.style): its feel and the arrangement's options, why,
    and every style and feel a person could choose."""
    from . import style as style_mod

    s = v.params.style
    name = s.name or "ballad"
    sdef = style_mod.of(s)
    c = variation.character(v.voice)
    feel = s.feel or next(iter(sdef.feels), "straight")
    value = f"{STYLE_NAMES.get(name, name)}, {FEEL_NAMES.get(feel, feel)}"
    options = [f"the last refrain a whole step up" if s.lift else "",
               f"verse {s.alone} sung {'with the ' + player(s.alone_with) + ' alone' if s.alone_with else 'bare'}"
               if s.alone else "",
               f"verse {s.stops} in stop-time" if s.stops else "",
               "the last refrain starts stripped down" if s.breakdown else "",
               "the band joins line by line in the first verse" if s.entrances else "",
               "the bridge in half-time" if s.bridge == "half" else "",
               {"lead": "", "pad": "a pad swells in to begin", "count": "a count-in to begin",
                "voice": "the singer begins alone"}.get(s.intro, ""),
               BACKING_NAMES.get(s.backing, ""),
               ENDING_NAMES.get(s.ending, "") if s.ending and s.ending != "ring" else ""]
    about = sdef.about.split(":", 1)[-1].strip() if name != "ballad" else \
        "harp, cittern, whistle, fiddle, guitar, upright bass, frame drum and a reed drone"
    detail = "; ".join(x for x in [about, *options] if x)

    def machine(path, value, blind):
        home = style_mod.home(c)
        if home is None:
            return None
        at = style_mod.RING[int(round(home)) % len(style_mod.RING)]
        return f"your machine is at home in {STYLE_NAMES.get(at, at)}, and a version moves one style at a time"

    def time(path, value, frozen):
        return f"{_when('slow')} lean toward {STYLE_NAMES.get(value or 'ballad', value)}"

    why = choice_reasons(v, ["style.name"], machine, time,
                         lambda path, value: STYLE_NAMES.get(value or "ballad", value))
    home = style_mod.home(c)
    if not why:  # kept: say so, and where the machine would take it, a style at a time
        why = [_kept(v, "style")]
        at = style_mod.RING[int(round(home)) % len(style_mod.RING)] if home is not None else None
        if at is not None and at != (v.generated.style.name or "ballad"):
            why.append({"kind": "machine", "text": f"your machine is at home in {STYLE_NAMES.get(at, at)}; the song "
                                                   f"moves toward it one style at a time, as the seasons allow"})
    before = list(dict.fromkeys(reversed(s.lineage[:-1])))[:3]
    if before and s.lineage[:-1]:
        where = listed([STYLE_NAMES.get(x, x).split(",")[0] for x in before])
        why.append({"kind": "lineage", "text": f"the versions before were played as {where}"})
    labels = {"style.name": lambda w: STYLE_NAMES.get(w or "ballad", w), "style.feel": lambda w: FEEL_NAMES.get(w, w),
              "style.ending": lambda w: ENDING_NAMES.get(w or "ring", w),
              "style.backing": lambda w: BACKING_NAMES.get(w, "no backing voices"),
              "style.lift": lambda w: "a lift" if w else "no lift"}
    mine = _mine(v, list(labels), lambda path, was: labels[path](was) if was is not None else None)
    feels = style_mod.feels_for(v.context.genome, sdef)
    return _card(v, "style", "The style", value, detail, mine + _finish(v, why, "style"), ["style."],
                 style={"name": name, "feel": feel, "ending": s.ending or "ring", "backing": s.backing,
                        "lift": s.lift},
                 styles={k: STYLE_NAMES.get(k, k) for k in style_mod.RING}, feels={f: FEEL_NAMES.get(f, f) for f in feels},
                 endings=dict(ENDING_NAMES), backings={"": "no backing voices", **BACKING_NAMES})


def mix_card(v: Version) -> dict:
    mix = MixParams.from_dict(v.params.mix or {})
    c = variation.character(v.voice)
    say = {  # path: (the machine's pull, time's push), each by direction
        "mix.space": (lambda m: f"your machine likes {'more' if m > 0 else 'less'} of the room",
                      lambda t: f"{_when('slow')}, {'more' if t > 0 else 'less'} of the room"),
        "mix.intimacy": (lambda m: f"your machine likes the singer {'closer' if m > 0 else 'further back'}",
                         lambda t: f"{_when('slow')}, the singer a little {'closer' if t > 0 else 'further back'}"),
        "mix.width": (lambda m: (f"a {'cool' if m > 0 else 'warm'} screen, a {'wider' if m > 0 else 'narrower'} sound"
                                 if "warmth" in c.known else f"your machine likes it {'wider' if m > 0 else 'narrower'}"),
                      lambda t: f"{_when('slow')}, a little {'wider' if t > 0 else 'narrower'}"),
        "mix.forward": (lambda m: f"your machine likes the voice further {'forward' if m > 0 else 'back'}",
                        lambda t: f"{_when('full')}, the voice a little further {'forward' if t > 0 else 'back'}"),
        "mix.tilt": (lambda m: f"a {'light' if m > 0 else 'dark'} screen, a {'brighter' if m > 0 else 'darker'} record",
                     lambda t: f"{_when('full')}, a little {'brighter' if t > 0 else 'darker'}"),
        "mix.wear": (lambda m: "old files and a tired machine wear the recording" if m > 0
                     else "young files keep the recording new", None),
        "mix.predelay": (lambda m: f"a {'big' if m > 0 else 'small'} room answers {'later' if m > 0 else 'sooner'}", None),
    }
    why: list[dict] = []
    for path, (machine, time) in say.items():
        why += number_reasons(v, path, machine, time)
    why = choice_reasons(v, ["mix.rt60"], lambda path, value, blind: f"your machine's room: {room_words(value)}",
                         None, lambda path, value: room_words(value)) + why
    labels = {"mix.space": "how much room", "mix.width": "how wide", "mix.forward": "the voice over the band",
              "mix.intimacy": "how close the singer is"}
    mine = [{"kind": "you", "text": f"{labels.get(p, p)}: chosen by you", "path": p} for p in v.mine("mix.")]
    return _card(v, "mix", "The room and the mix", mix_words(mix), f"the room takes {mix.rt60:.1f} s to fall quiet",
                 mine + _finish(v, why, "mix"), ["mix."],
                 mix={k: getattr(mix, k) for k in ("space", "width", "forward", "intimacy", "rt60", "tilt", "wear")})


def singer_card(v: Version, phrasings: list[dict]) -> dict:
    singer = singer_of(v.params)
    c = variation.character(v.voice)
    why = []
    if "identity" in c.known:
        why.append({"kind": "machine", "text": "your machine's own voice, the same in every song it sings"})
    for path, word in (("singer.rd", ("its voice is a little breathier", "its voice is a little more pressed")),
                       ("singer.breath", ("its voice is a little breathier", "its voice is a little clearer")),
                       ("singer.vibrato_depth", ("it sings with a little more vibrato", "it sings with a little less vibrato"))):
        why += number_reasons(v, path, None, lambda t, w=word: f"{_when('full')} {w[0] if t > 0 else w[1]}")
    way = "sung the song's own way"
    mine = []
    if "phrasing" in v.applied:
        who = next((p["label"] for p in phrasings if p["id"] == v.edits.get("phrasing")), "a singer")
        way = "sung the way everyone who has sung it does" if who == "everyone who has sung it" else f"sung {who}'s way"
        mine.append({"kind": "you", "text": "whose way it's sung: chosen by you", "path": "phrasing"})
    return _card(v, "singer", "The singer", singer_words(singer), way, mine + _finish(v, why, "singer"), ["phrasing"],
                 phrasing=v.edits.get("phrasing", ""))


def words_card(v: Version) -> dict:
    genome = v.context.genome
    lean = v.params.leanings or {}
    bank = genome.source.get("bank")
    c = variation.character(v.voice)
    if v.lyrics is None or not bank:
        return _card(v, "words", "The words", "the song's own words", "",
                     [{"kind": "song", "text": "this song has no store of other verses to draw from"}], [])
    why = number_reasons(v, "leanings.era_bias",
                         lambda m: f"the words you use lean them {'newer' if m > 0 else 'older'}" if "era" in c.known
                         else f"old files lean them older" if m < 0 else None,
                         lambda t: f"{_when('slow')} lean {'newer' if t > 0 else 'older'}")
    why += number_reasons(v, "leanings.rarity_appetite",
                          lambda m: f"a {'rich' if m > 0 else 'plain'} vocabulary {'seeks out' if m > 0 else 'passes over'} rare verses",
                          lambda t: f"{_when('slow')} lean to {'rarer' if t > 0 else 'commoner'} verses")

    # the mood: what choose_mood reads, each said only where it leans (the screen, a minor key, these weeks)
    mood = []
    if "brightness" in c.known and abs(c.brightness) > 0.2:
        mood.append({"kind": "machine", "text": f"your {'light' if c.brightness > 0 else 'dark'} screen leans them "
                                                f"{'lighter' if c.brightness > 0 else 'darker'}"})
    if "warmth" in c.known and c.warmth > 0.2:
        mood.append({"kind": "machine", "text": "your warm screen leans them tender"})
    if v.generated.mode in MINOR:  # the song's own rule, whatever brought the minor mode
        mood.append({"kind": "rule",
                     "text": f"the {MODES.get(v.generated.mode, (v.generated.mode,))[0]} key leans them darker"})
    tilt = _drift_at(v, "slow", "mood")
    if abs(tilt) > 0.15:
        mood.append({"kind": "time", "text": f"{_when('slow')} lean {'lighter' if tilt > 0 else 'darker'}"})
    themes = [THEMES.get(t, t) for t, share in sorted((c.themes or {}).items(), key=lambda x: -x[1])
              if share > 1.2 / max(len(c.themes or {}), 1)][:3]
    if themes and v.generated.leanings.get("vocabulary"):
        mood.append({"kind": "machine", "text": f"the words you use bring forward verses about {listed(themes)}"})
    # what reaches for which words: the machine's taste, for the words it takes in or swaps
    taste = [dict(r, text=f"what your machine reaches for: {r['text']}") for r in mood + why]
    changes = word_changes(v)
    mine = []
    if "mode" in v.applied and (v.params.leanings or {}).get("mood_weights") != (v.generated.leanings or {}).get("mood_weights"):
        mine.append({"kind": "you", "text": f"leaning {'darker' if v.params.mode in MINOR else 'lighter'} for the "
                                            f"{MODES.get(v.params.mode, (v.params.mode,))[0]} key you chose",
                     "path": "mode"})
    mine += [{"kind": "you", "text": f"{_word_place(p)}: chosen by you", "path": p}
             for p in v.mine("words.") if p not in v.held]
    if v.held:
        mine.append({"kind": "you", "text": "the words kept as they are: kept by you", "path": sorted(v.held)[0]})
    before = "the song's own words, as it began" if v.context.parent_record is None else "the version before's words"
    n = len([c for c in changes if c["kind"] != "rule"])
    value = f"{before}, handed down" + (f", with {number(n)} change{'s' if n != 1 else ''} this time" if n else " as they were")
    lineage = {"kind": "lineage", "text": "the rest handed down as they were: a song's words change a little at a time"}
    return _card(v, "words", "The words", value, f"your machine's picks lean {lean_words(lean).replace('a little ', '')}"
                 if lean_words(lean) != "no particular way" else "", mine + changes + [lineage] + _unique(taste),
                 ["words."])


CHANGE_WORDS = {"added": "taken in", "left out": "left out", "swapped": "changed", "rule": "changed by the song's rule",
                "drawn": "drawn afresh", "learned": "learned", "forgot": "forgotten", "dropped": "dropped"}


def _said(text: str) -> str:
    """The program's own why, in the page's words."""
    import re

    text = re.sub(r"\s*\([^()]*(?:%|appetite)[^()]*\)", "", str(text or ""))  # the clock's odds: code, not reasons
    text = re.sub(r"\s*\(the song's rule; the seed sings its canon every time\)", "", text.replace("bank's", "song's"))
    for code, plain_ in (("this machine's", "your machine's"), ("this machine", "your machine"),
                         ("the bank", "the song"), ("the seed's", "the song's first"), ("the seed", "the song as it began"),
                         ("canon", "last couplet")):
        text = text.replace(code, plain_)
    return text


def _named(value) -> str:
    return str(value).replace("-", "") if value else ""


def word_changes(v: Version) -> list[dict]:
    """What the program changed in the words this time, and why (evolve's log, choose_params(log=))."""
    out = []
    for e in v.changes:
        if not isinstance(e, dict) or e.get("what") != "words":
            continue
        change = CHANGE_WORDS.get(e.get("change"), e.get("change") or "changed")
        fr, to = _named(e.get("from")), _named(e.get("to"))
        what = "" if e.get("change") == "rule" else f"{fr} for {to}" if fr and to else to or fr
        where = e.get("where") or "the words"
        out.append({"kind": "rule" if e.get("change") == "rule" else "time",
                    "text": f"{where} {change}{f' ({what})' if what else ''}: {_said(e.get('why'))}", "where": where})
    return out


def tune_changes(v: Version) -> list[dict]:
    """What the program changed in the tune this time, and why."""
    out = []
    for e in v.changes:
        if not isinstance(e, dict) or e.get("what") != "tune":
            continue
        if (e.get("variant") or {}).get("phrase") in v.params.composition.get("tune", {}):
            continue
        change = CHANGE_WORDS.get(e.get("change"), e.get("change") or "changed")
        out.append({"kind": "time", "text": f"{_said(e.get('about') or 'a small change')} {change}: {_said(e.get('why'))}"})
    return out


def handed(v: Version) -> dict[tuple[str, int], bool]:
    """Which sung parts are as the version before held them: (block, nth) -> True where handed down."""
    from . import evolve

    now = v.params.words or {}
    if not now:
        return {}
    base = v.context.base
    was = getattr(base, "words", None) or evolve.seed_words(v.context.genome, base)
    out: dict[tuple[str, int], bool] = {}
    for i, entry in enumerate(now.get("verses", [])):
        old = was.get("verses", [])
        out[("verse", i)] = i < len(old) and old[i] == entry
    genome = v.context.genome
    rounds = arrange_mod.rounds(genome, now) if now.get("refrain") else []
    old_rounds = arrange_mod.rounds(genome, was) if was.get("refrain") else []
    for i, entry in enumerate(rounds):  # the last as the last before, the others place by place
        old = old_rounds[-1:] if i == len(rounds) - 1 else old_rounds[i: i + 1] if i < len(old_rounds) - 1 else []
        out[("refrain", i)] = old == [entry]
    for j, entry in enumerate(now.get("bridge", [])):
        old = was.get("bridge", [])
        out[("bridge", j)] = j < len(old) and old[j] == entry
    if now.get("tag"):
        out[("tag", 0)] = now.get("tag") == was.get("tag")
    return out


def _word_place(path: str) -> str:
    parts = path.split(".")
    if len(parts) == 3:
        return f"{parts[1]} {int(parts[2]) + 1}"
    return {"refrain": "the refrain's words", "bridge": "the bridge's words", "bridge2": "the second bridge",
            "tag": "the tag"}.get(parts[1], parts[1])


def choir_card(v: Version) -> dict:
    n = v.params.choir
    sings = [s for s in dict.fromkeys(v.params.form) if v.context.genome.section(s).choir and s != "bridge2"]
    where = listed([f"the {SECTIONS.get(s, s).lower()}" for s in sings])
    value = (f"{number(n)} voice{'s' if n != 1 else ''} from earlier versions join{'s' if n == 1 else ''} {where}"
             if n else "no voices from earlier versions yet")
    parent = v.context.parent_record or {}
    known = (1 + len(parent.get("lineage_singers") or [])) if parent.get("singer") else 0
    if not v.context.parent_record:
        detail = "the song as it began counts as the version before; a stand-in sings for it"
    elif known and n:
        own = min(known, n)
        detail = (f"{'the version before sings' if own == 1 else f'the {number(own)} versions before sing'} in "
                  f"{'its' if own == 1 else 'their'} own voice{'s' if own > 1 else ''}"
                  + (f"; stand-ins sing the other {number(n - own)}" if n > own else ""))
    else:
        detail = "stand-ins for now: the versions before haven't left their voices"
    return _card(v, "choir", "Voices before", value[0].upper() + value[1:], detail,
                 [{"kind": "lineage", "text": "one more for every version before this one, up to six"}], [])


def variants_card(v: Version) -> dict | None:
    """The tune's small changes the lineage carries (songbird.variants), each in words, each one a person
    can drop; the ones the program chose, sung or dropped."""
    from . import variants as variants_mod

    sung = tuple(getattr(v.params, "variants", None) or ())
    chosen = tuple(getattr(v.generated, "variants", None) or ())
    if not hasattr(v.params, "variants"):
        return None
    genome = v.context.genome
    items = [{"name": str(i), "label": variants_mod.describe(genome, var, v.lyrics), "value": var in sung,
              "path": f"variants.{i}", "mine": f"variants.{i}" in v.applied} for i, var in enumerate(chosen)
             if var.phrase not in v.params.composition.get("tune", {})]
    on = sum(bool(i["value"]) for i in items)
    value = (f"{number(on)} small change{'s' if on != 1 else ''} to the tune, handed down or found here"
             if on else "your composed tune" if v.params.composition.get("tune") else "the tune as it was written")
    why = tune_changes(v)  # what changed this time, and why (songbird.evolve's own reasons)
    if not why:
        why = [{"kind": "lineage", "text": "handed down as the version before sang it; a tune changes a little at a "
                                           "time, a note now and then"}] if on else []
    mine = [{"kind": "you", "text": "dropped by you: " + next((i["label"] for i in items if i["path"] == p), p),
             "path": p} for p in v.mine("variants.")]
    return _card(v, "variants", "The melody", value, "", mine + _finish(v, why, "variants"), ["variants."],
                 variants=items)


def machine_card(v: Version, label: str, quiet: bool) -> dict:
    lines = machine_words(v.voice)
    if quiet:
        lines.append("only its languages, size and screen are read so far; the rest is read, and every number "
                     "kept shown, when you choose to from the command line")
    return {"id": "machine", "title": "Your machine", "value": label, "lines": lines,
            "detail": "only a few coarse numbers are kept from it, and they stay on this computer",
            "reasons": [], "mine": False, "problems": [], "paths": []}


def other_cards(v: Version) -> list[dict]:
    """A card for every Params field no card above speaks for (a new choice the program has learned to
    make), its value in plain words and its reasons found the same way."""
    from .realize import Params

    out = []
    for f in fields(Params):
        if f.name in KNOWN:
            continue
        value = getattr(v.params, f.name)
        why = choice_reasons(v, [f.name], lambda p, a, b: "your machine", lambda p, a, b: "time")
        out.append(_card(v, f"field.{f.name}", f.name.replace("_", " ").capitalize(), plain(value), "",
                         _finish(v, why, f.name), [f.name]))
    return out


# ---------------------------------------------------------------- the words, section by section


def words_view(v: Version) -> list[dict]:
    genome = v.context.genome
    lyrics = as_sung(genome, v.params, v.lyrics)
    drawn = v.lyrics is not None
    bank = genome.source.get("bank") or {}
    verses = {e["id"]: e for e in bank.get("verses", [])}
    lead = leader(v.params.band, v.params.style)
    kept_from = handed(v) if drawn else {}
    changed_at = {c["where"]: c["text"] for c in word_changes(v)}
    sung = iter(lyrics.sections)
    seen: dict = {}
    out = []
    for k, name in enumerate(v.params.form):
        section = genome.section(name)
        block = section.lyrics
        seen[name] = seen.get(name, 0) + 1
        label = SECTIONS.get(name, name.title()) + (f" {seen[name]}" if name in ("verse", "refrain") else "")
        item = {"index": k, "name": name, "label": label, "sung": bool(block)}
        if not block:
            item["lines"] = [_instrumental(name, lead)]
            out.append(item)
            continue
        s = next(sung)
        nth = sum(1 for x in lyrics.sections[: lyrics.sections.index(s)] if x.block == s.block)
        path = (f"words.{block}.{nth}" if block in ("verse", "refrain")
                else "words.bridge2" if block == "bridge" and nth == 1 else f"words.{block}")
        paths = [path] + (["words.refrain"] if block == "refrain" else ["words.bridge"] if block == "bridge" and nth == 0
                          else [])
        taken = [p for p in paths if p in v.applied]
        mine = bool(taken)
        kept = mine and all(p in v.held for p in taken)
        tags = []
        entry = verses.get(s.id)
        if block == "verse" and entry:
            tags = [entry.get("mood"), str(entry["era"]) if entry.get("era") else None,
                    "rare" if entry.get("rarity") == "rare" else None]
        if block == "refrain" and s.slots.get("question"):
            tags = [f"asks who {s.slots['question']}"]
        note = ""
        if mine:
            how = "kept by you" if kept else "chosen by you"
        elif not drawn:
            how = "the song's own words"
        elif kept_from.get((block, nth), True):
            how = "handed down"
        else:
            how = "new this time"
            places = {"verse": [f"verse {nth + 1}"], "refrain": [f"refrain {nth + 1}", f"refrain {nth + 1}'s couplet"],
                      "bridge": ["bridge 2", "the bridge's extra stanza"] if nth else ["the bridge's"],
                      "tag": ["tag", "the tag's syllable"]}.get(block, [])
            note = next((text for where, text in changed_at.items()
                         if any(where == p or where.startswith(p) for p in places)), "")
        item.update({"block": block, "nth": nth, "id": s.id, "lines": [readable(line) for line in s.lines],
                     "tags": [t for t in tags if t], "how": how, "note": note, "mine": mine, "kept": kept,
                     "path": path, "changeable": bool(drawn and bank)})
        from .composition import section_ids

        authored = v.params.composition.get("lyrics", {}).get(section_ids(v.params.form)[k], {})
        if authored:
            item.update({"authored": sorted(int(i) for i in authored), "how": "includes your own lyrics", "mine": True})
        out.append(item)
    return out


def _instrumental(name: str, lead: str | None) -> str:
    who = f"the {player(lead)}" if lead else "the band"
    return {"intro": f"{who} plays the tune in", "turn": "the band turns a line of the refrain over",
            "break": f"{who} plays a verse's tune before the bridge", "outro": f"{who} plays it out"}.get(
        name, "the band plays")


def word_options(ctx: Context, v: Version, block: str, index: int) -> dict:
    """Every choice for one section of the words, each allowed or refused with why (arrange.options)."""
    if v.lyrics is None:
        raise ValueError("this version sings the song's own words, which can't be chosen among")
    out = word_choices(ctx.genome, v.lyrics, block, index)
    out["path"] = (f"words.{block}.{index}" if block in ("verse", "refrain")
                   else "words.bridge2" if block == "bridge" and index == 1 else f"words.{block}")
    out["slots_path"] = {"verse": out["path"], "refrain": out["path"], "bridge": "words.bridge"}.get(block)
    for head in out.get("heads", []):
        head["lines"] = [readable(line) for line in head.get("lines", [])]
    for choice in out["choices"]:
        choice["lines"] = [readable(line) for line in choice.get("lines", [])]
    for slot in out["words"]:  # as they read; the page sends them back as they read, which arrange matches
        slot["labels"] = {o: _word(o) for o in slot["options"]}
    return out


def keep_words(v: Version) -> dict:
    """The edits that hold every section's words as they are ("keep these words")."""
    return edits_mod.keep_words(v.context.genome, v.lyrics)


# ---------------------------------------------------------------- the whole view


def view(ctx: Context, v: Version, phrasings: list[dict] | None = None) -> dict:
    """Everything the page draws for a version: the header, the words, the cards, the problems."""
    from . import composition

    phrasings = phrasings or []
    cards = [style_card(v), key_card(v), tempo_card(v), shape_card(v), band_card(v), mix_card(v),
             singer_card(v, phrasings), words_card(v), choir_card(v)]
    extra = variants_card(v)
    if extra:
        cards.insert(4, extra)
    cards += other_cards(v)
    cards.append(machine_card(v, ctx.machine_label(), ctx.quiet))
    if v.offset:  # the same choices today: what moving the day changed, the person's edits and all
        today = ctx.version({k: val for k, val in v.edits.items() if k not in ("date", "phrasing")}, v.voice)
        for card in cards:
            was, now = _headline(card["id"], today), _headline(card["id"], v)
            if was is not None and was != now:
                card["today"] = f"today: {was}"
    return {
        "title": ctx.genome.title,
        "day": v.day, "offset": v.offset, "when": distance(v.offset), "date": long_date(v.day),
        "from": ctx.from_words(), "by": ctx.machine_label(),
        "roll": v.edits.get("roll", 0),
        "words": words_view(v),
        "cards": cards,
        "edits": v.edits,
        "applied": v.applied,
        "changed": v.changed,  # the person's choices that changed something: the header counts these
        "held": sorted(v.held),
        "problems": v.problems,
        "marks": v.marks,
        "form": list(v.params.form),
        "composition": composition.view(ctx.genome, v.params, as_sung(ctx.genome, v.params, v.lyrics)),
    }


def _headline(card: str, v: Version):
    p = v.params
    if card == "key":
        return key_words(p.tonic, p.mode)
    if card == "tempo":
        return f"{p.tempo:.0f} beats a minute"
    if card == "shape":
        return shape_words(edits_mod.shape(v.context.genome, p.form))
    if card == "band":
        return f"{PATTERNS.get(p.band.pattern, p.band.pattern)}, the {player(leader(p.band) or 'band')} leading"
    return None


def listen_label(ctx: Context, v: Version, section: int | None, who: str) -> str:
    whose = ("your version" if who == "you" else "as the program would sing it" if who == "program"
             else f"{who.split(':', 1)[-1].title()}'s version")
    if section is None:
        return f"The whole song, {whose}"
    return f"{words_view(v)[section]['label']}, {whose}"


# ---------------------------------------------------------------- time


def timeline(ctx: Context, days: int = TIMELINE_DAYS) -> dict:
    """The machine's own song, day by day, from `days` before today to `days` after (no edits): its key
    and mode, tempo, shape, band, and which way its words lean. For the page's lanes."""
    genome, voice = ctx.genome, ctx.voice
    start = _date.fromisoformat(ctx.day) - timedelta(days=days)
    dates = [(start + timedelta(days=k)).isoformat() for k in range(2 * days + 1)]
    ts = np.array([drift_mod.parse(d) for d in dates])
    vhash = (voice if voice is not None else harvest.Voice()).hash
    series = drift_mod.series(ts, vhash)
    names = list(series)
    lanes: dict = {k: [] for k in ("key", "mode", "tonic", "tempo", "verses", "parts", "pattern", "lead", "lean",
                                   "style")}
    for i, t in enumerate(ts):
        d = drift_mod.Drift(t=float(t), **{view: {name: float(series[name][view][i]) for name in names}
                                           for view in drift_mod.VIEWS}, hash=vhash)
        p = ctx.choose(voice, d)
        parts = edits_mod.shape(genome, p.form) or {}
        mood = (p.leanings or {}).get("mood_weights", {})
        lanes["key"].append(key_words(p.tonic, p.mode))
        lanes["mode"].append(p.mode)
        lanes["tonic"].append(p.tonic)
        lanes["tempo"].append(round(p.tempo, 1))
        lanes["verses"].append(parts.get("verses", 0))
        lanes["parts"].append(" ".join(k for k in ("intro", "turn", "break", "bridge2", "tag", "outro", "pairs")
                                       if parts.get(k)))
        lanes["pattern"].append(p.band.pattern)
        lanes["lead"].append(leader(p.band, p.style) or "")
        lanes["lean"].append(round(float(np.log2(mood.get("light", 1.0) / max(mood.get("dark", 1.0), 1e-6))), 3))
        lanes["style"].append(p.style.name or "ballad")
    names_seen = {n for n in lanes["lead"] if n}
    return {"start": dates[0], "today": days, "dates": dates, "lanes": lanes,
            "brightness": dict(variation.BRIGHTNESS), "patterns": PATTERNS,
            "players": {n: player(n) for n in names_seen | set(PLAYERS)},
            "styles": {k: STYLE_NAMES.get(k, k).split(",")[0] for k in STYLE_NAMES},
            "modes": {m: MODES[m][0] for m in MODES}}


# ---------------------------------------------------------------- other machines


def summary(ctx: Context, v: Version, who: str, name: str | None = None) -> dict:
    """One machine's version in a few plain words, for comparing machines side by side."""
    p = v.params
    lyrics = as_sung(ctx.genome, p, v.lyrics)
    first = next((readable(s.lines[0]).replace("*", "") for s in lyrics.sections if s.block == "verse" and s.lines), "")
    mix = MixParams.from_dict(p.mix or {})
    singer = singer_of(p)
    style = p.style.name or "ballad"
    lead = leader(p.band, p.style)
    band = (f"the {player(lead)} leading" if p.band.lineup else
            f"{PATTERNS.get(p.band.pattern, p.band.pattern)}, the {player(lead or 'band')} leading")
    return {"who": who, "name": name or "Yours",
            "rows": {"Style": STYLE_NAMES.get(style, style).split(",")[0],
                     "Key": key_words(p.tonic, p.mode), "Tempo": f"{p.tempo:.0f} beats a minute",
                     "Shape": shape_words(edits_mod.shape(ctx.genome, p.form)),
                     "Band": band,
                     "Singer": "a low voice" if singer.shift <= -12 else "a high voice",
                     "Room": room_words(mix.rt60), "First line": first}}


# ---------------------------------------------------------------- the opening


def start(ctx: Context, studio) -> dict:
    """What the page needs once: the song, the machine, the bounds of every choice, and what's available."""
    genome = ctx.genome
    b = edits_mod.bounds(genome)
    b["tonic"]["names"] = {str(m): note(m) for m in range(b["tonic"]["min"], b["tonic"]["max"] + 1)}
    b["mode"]["names"] = {m: MODES.get(m, (m, ""))[0] for m in b["mode"]["options"]}
    b["mode"]["glosses"] = {m: mode_gloss(m) for m in b["mode"]["options"]}
    return {
        "title": genome.title, "song_digest": studio.song_digest,
        "day": ctx.day, "date": long_date(ctx.day), "days": TIMELINE_DAYS,
        "machine": {"label": ctx.machine_label(), "lines": machine_words(ctx.voice)},
        "from": ctx.from_words(), "bounds": b, "players": {n: player(n) for n in INSTRUMENTS},
        "patterns": PATTERNS, "parts": PARTS, "optional": list(edits_mod.optional(genome)), "kinds": KINDS,
        "sing": studio.sing_available(), "phrasings": studio.phrasings(), "out": studio.out_shown(),
        "names": ["Ada", "Basil", "Coral"], "packet": studio.packet_note(),
    }
