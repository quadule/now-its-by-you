"""Styles: the musical tradition a rendition is played in, and how its arrangement is shaped.

The song is a folk song passed between people and computers; each rendition
dresses it in a tradition. A style is a coherent bundle: a feel and a tempo
range, a lineup of instruments in roles (bass, chords, lead and counter, pad,
percussion, backing voices) with idiomatic parts for each, a harmony
vocabulary always checked against the sung tune, leanings for the singer and
a mix aesthetic. The palette and the map they travel on are below; the
arrangement they make is songbird/idioms.py.

Params.style records a rendition's: its name, the styles its line has been
sung in, and the arrangement's options (Style). An empty name is the seed's
own arrangement, exactly as it always played (the ballad band).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, fields

import numpy as np

FEELS = ("straight", "swing", "shuffle", "twelve", "half", "double", "waltz", "six")
INTROS = ("lead", "pad", "count", "voice", "quote", "air")  # air: the tune slow and free, the lead alone
ENDINGS = ("ring", "rit", "cold", "amen", "repeat", "version")  # version: a dub after the song (2026-09-30)
BACKINGS = ("oohs", "echo", "thirds", "gang", "hum")  # hum: an a cappella's open-fifth drone under the verses
LINEAGE_MAX = 16  # generations of styles a record remembers
# Style's options a record leaves out while they're off (added after records were made)
QUIET_OFF = ("drop", "loop", "dissolve")
# Values retired since records were made, read as what replaced them: an a cappella's intro sung on shape-note
# syllables (2026-09-30) is now the lead humming the tune over the group; the Celtic session is the jig
RENAMED = {"intro": {"notes": "lead"}, "name": {"celtic": "jig"}}


def renamed(option: str, value):
    """A style option's value as it is now called (a retired one read as its replacement)."""
    return RENAMED.get(option, {}).get(value, value) if isinstance(value, str) else value


@dataclass(frozen=True)
class Style:
    """How a rendition is dressed. Every option has an off value ("" or 0 or False), which is the
    seed's; out-of-range values are dropped to off, unknown names ignored.

    name        the style (STYLES); "" the seed's own arrangement, byte for byte
    lineage     the styles this rendition's line was sung in, one a generation, oldest first, this one last
    feel        straight, swing, shuffle (a triplet lilt with a shuffle's groove), twelve (12/8), half
                (half-time), double (double-time), waltz or six (the song re-barred in three, where it can
                be); "" the style's own
    harmony     0..1, how much of the style's harmony vocabulary colours the chords (sevenths, sixths, added
                ninths, suspensions, a plagal amen...), always voiced around the sung tune
    intro       lead (an instrument states the tune), pad (a pad swells in alone), count (a count-in on
                sticks), voice (the singer starts alone and the band comes in on the second line), quote
                (the lead instrument alone plays a line of an older song the genome names, genome.quote,
                in bars cleared before the song; a genome with no quote starts as the form has it); "" as
                the form has it
    alone       which verse (1 the first) is sung with little: a cappella, or with one instrument; 0 none
    alone_with  the one instrument playing under it; "" a cappella
    stops       which verse is played in stop-time (the band hits the downbeats and leaves the words bare); 0 none
    breakdown   the last refrain starts stripped to the rhythm and the band comes back at its third line
    bridge      "half": the bridge in half-time; "" as the style plays it
    lift        the last refrain a whole step up
    ending      ring (the last chord rings), rit (a broad ritardando), cold (a dead stop), amen (a
                plagal IV-I with the backing voices' amen), repeat (the last line sung again), version (after
                the last line the band plays the last refrain's chords again, nobody singing, and the desk dubs
                it: drop-outs, echo throws, a spring's splash); "" ring
    entrances   the first verse builds, instruments joining line by line
    backing     what the backing voices sing: oohs (chord tones), echo (answers at the ends of lines),
                thirds (harmony above and below), gang (everyone on the tune); "" none
    voices      how many backing voices sing it (the lineage's own, and stand-ins where a style wants a group)
    coda        quote: after the last line, as the last chord rings two bars on, the lead instrument alone plays
                the opening of the older song the genome names (genome.quote), softly: a leitmotif; "" none
    motif       bridge: in the bridge, where the lineage sings, the lead instrument (H: the whistle) plays the quote's
                opening over the third phrase, the fiddle's pad resting for it (band.motif_part; only where every
                note is a tone of the chord under it); chance:
                about a third of renditions do, by their seed, an easter egg; "" none
    drop        a breakdown and a drop: after this refrain (1 the first) every section before the next refrain
                is the breakdown (the drums, the bass and the rest out, the singer with the pad; the band's
                low-pass opening across it, a riser and a snare roll into the refrain after), and that refrain
                is the drop; 0 none. Left out of a record while 0, so a record is as it was before it
    loop        a chord loop of the style's own (StyleDef.loops, by name) under the sections the style loops, in place
                of the song's chords; "song" the song's own; "" the style's default (the loop that best fits the tune
                in this key and mode, for a style with loops). Left out of a record while ""
    dissolve    the song dissolved into its version after this refrain (1 the first): every section after it the
                version (the singer's lines in fragments thrown into the echo, the riddim, the melodica's pieces,
                the desk harder); 0 none. Left out of a record while 0
    """

    name: str = ""
    lineage: tuple[str, ...] = ()
    feel: str = ""
    harmony: float = 0.0
    intro: str = ""
    alone: int = 0
    alone_with: str = ""
    stops: int = 0
    breakdown: bool = False
    bridge: str = ""
    lift: bool = False
    ending: str = ""
    entrances: bool = False
    backing: str = ""
    voices: int = 0
    coda: str = ""  # quote: after the last line, over the ringing last chord, the lead alone plays the quote's opening
    motif: str = ""  # bridge: the lead plays the quote's opening over the bridge's third phrase; chance: some renditions
    drop: int = 0  # the refrain a breakdown and a drop follow (house's habit, 2026-09-30); 0 none, and no trace in a record
    loop: str = ""  # a loop of the style's own under the song (house's, dub's riddim; 2026-09-30, evening)
    dissolve: int = 0  # the refrain after which the song dissolves into its version (dub's); 0 none

    @classmethod
    def from_dict(cls, data: dict | None) -> Style:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**values).clamped()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["lineage"] = list(self.lineage)
        for name in QUIET_OFF:  # options added since records were made: absent while off, so a digest is as it was
            if not data[name]:
                del data[name]
        return data

    def clamped(self) -> Style:
        def pick(v, options):
            return v if v in options else ""

        return Style(
            name=str(renamed("name", self.name) or ""),
            lineage=tuple(str(renamed("name", x)) for x in (self.lineage or ()))[-LINEAGE_MAX:],
            feel=pick(self.feel, FEELS),
            harmony=float(min(1.0, max(0.0, float(self.harmony or 0.0)))),
            intro=pick(renamed("intro", self.intro), INTROS),
            alone=max(0, int(self.alone or 0)),
            alone_with=str(self.alone_with or ""),
            stops=max(0, int(self.stops or 0)),
            breakdown=bool(self.breakdown),
            bridge="half" if self.bridge == "half" else "",
            lift=bool(self.lift),
            ending=pick(self.ending, ENDINGS),
            entrances=bool(self.entrances),
            backing=pick(self.backing, BACKINGS),
            voices=max(0, min(6, int(self.voices or 0))),
            coda=pick(self.coda, ("quote",)),
            motif=pick(self.motif, ("bridge", "chance")),
            drop=max(0, min(8, int(self.drop or 0))),
            loop=str(self.loop or "") if re.fullmatch(r"[a-z]{1,16}", str(self.loop or "")) else "",
            dissolve=max(0, min(8, int(self.dissolve or 0))),
        )

    @property
    def seed(self) -> bool:
        """Whether this is the seed's own arrangement (no style, no options)."""
        return self == Style()


# --- the palette ------------------------------------------------------------------------------------
#
# A style's parts: for each instrument, what it plays in each kind of section (intro, verse, refrain, turn,
# break, bridge, tag, outro; "verse1" the first verse, "last" the last refrain, "*" anything else), either
# an idiom (songbird.idioms.WRITERS) or ((busy, idiom), ...) where busy is how full the band is there (the
# section's energy, and the band's density) and the first threshold it reaches wins; "" sits out.


@dataclass(frozen=True)
class StyleDef:
    """One style of the palette: who plays and how, and everything else it leans on."""

    name: str
    about: str
    lineup: dict  # instrument -> gain as the style has it
    parts: dict  # instrument -> {section kind: idiom or ((busy, idiom), ...)}
    leads: tuple  # who states the tune: the first opens and closes, breaks and turns go round
    feels: dict  # feel -> weight (a waltz or six-eight only where the song can be re-barred)
    tempo: dict  # feel -> (lowest, centre, highest) as multiples of the song's own tempo; "*" for any other
    colours: dict  # chord function (or "*") -> the colours its harmony may add
    harmony: float  # how much colour, 0..1
    at: tuple  # (machine, drive): where machines at home in it are, -1..1 each
    band: dict = field(default_factory=dict)  # offsets to the band's density, brightness, wear, ornament, arc
    feel: dict = field(default_factory=dict)  # humanize (a factor) and ritardando (an offset)
    singer: dict = field(default_factory=dict)  # offsets to the singer's habits (VoiceParams fields), gently
    mix: dict = field(default_factory=dict)  # offsets to the mix (MixParams fields; "choir" dB for the backing voices)
    options: dict = field(default_factory=dict)  # the arrangement's propensities (see choose_options)
    swaps: dict = field(default_factory=dict)  # a player -> {another who may play the part instead: how often}
    optional: dict = field(default_factory=dict)  # a player -> how often it comes at all (else it sits in at gain 0)
    group: int = 0  # the fewest backing voices the style sings with: the lineage's, then the program's own
    rounds: int = 0  # how many times round a short played section's tune goes (the jig's); 0 as the form has it
    ornaments: float = 0.0  # how often the singer ornaments a long stressed note of its own accord (the jig's)
    # a style's own sound design, under a person's (songbird.sound.program_players): {"players": {part: {kit, patch,
    # sidechain...}}, "intro": "open" (the band's low-pass opening across an intro)}; {}: none (house, 2026-09-30)
    sound: dict = field(default_factory=dict)
    # the mixing desk as an instrument (dub, 2026-09-30; songbird.idioms "the desk"): drop-outs, throws and splashes
    # by section, the echo's time and feedback (DESK's keys); {}: the desk is left alone
    desk: dict = field(default_factory=dict)
    # chord loops of the style's own (house's, dub's riddims; 2026-09-30, evening): {name: (degrees a bar, sevenths)},
    # the mode's own chords on those degrees; and the sections that take one ("version": dub's dissolved sections)
    loops: dict = field(default_factory=dict)
    looped: tuple = ()
    # the style's own section lengths and the bars it plays after a sung one (house's): {"bars": {role: bars},
    # "after": {"drop": bars, "last": bars}, "layers": {...}}; {}: the form's own
    form: dict = field(default_factory=dict)
    # a vocal chop (house's): the singer sings a short phrase of the song's words on the grid, in the style's hook bars
    hook: dict = field(default_factory=dict)

    def order(self, lineup: dict) -> list[str]:
        """The instruments of a lineup in the style's own order (one swapped in where its part is), any others
        after by name."""
        mine = [who for name in self.lineup for who in (name, *self.swaps.get(name, {})) if who in lineup]
        return mine + sorted(name for name in lineup if name not in mine)

    def playing(self, name: str, lineup) -> str:
        """Who plays the style's part `name` in a lineup: its own player, or the one swapped in for it."""
        return next((who for who in (name, *self.swaps.get(name, {})) if who in lineup), name)

    def part_of(self, name: str) -> str:
        """The style's part a player plays: its own, or the one it was swapped in for."""
        return next((part for part, swaps in self.swaps.items() if name in swaps), name)

    def colours_for(self, symbol: str) -> tuple:
        key = symbol if symbol in self.colours else symbol.upper() if symbol.upper() in self.colours else "*"
        return tuple(self.colours.get(key, ()))

    def centre(self, feel: str) -> tuple[float, float, float]:
        return tuple(self.tempo.get(feel, self.tempo.get("*", (0.75, 1.0, 1.3))))


def _def(name, about, lineup, parts, leads, feels, tempo, colours, harmony, at, **rest) -> StyleDef:
    return StyleDef(name, about, dict(lineup), {k: dict(v) for k, v in parts.items()}, tuple(leads), dict(feels),
                    dict(tempo), dict(colours), harmony, tuple(at), **rest)


BALLAD = _def(
    "ballad", "the seed's own band: an English and Celtic ballad band, harp, cittern, whistle, fiddle, guitar, "
              "upright bass, frame drum and reed drone (songbird.band arranges it)",
    {name: 1.0 for name in ("lute", "guitar", "harp", "bass", "fiddle", "whistle", "drum", "drone")},
    {}, ("whistle", "fiddle", "lute"), {"straight": 1.0}, {"*": (0.75, 1.0, 1.3)},
    {"V": ("7",), "*": ("sus2", "power")}, 0.0, (-0.9, -0.1),
    options={"intro": {"lead": 0.8, "pad": 0.1, "voice": 0.1}, "alone": 0.12, "stops": 0.0, "breakdown": 0.12,
             "lift": 0.1, "ending": {"ring": 0.6, "rit": 0.3, "cold": 0.1}, "entrances": 0.2,
             "backing": {"": 0.8, "oohs": 0.1, "thirds": 0.1}},
)

STRINGBAND = _def(
    "stringband", "an old-time and bluegrass string band: clawhammer banjo when it's quiet and forward rolls when "
                  "it drives, the mandolin's chop on the backbeat, a boom-chick guitar with its runs, fiddle breaks "
                  "and fills, the upright bass on one and three",
    {"bass": 1.0, "banjo": 0.9, "mandolin": 0.85, "guitar": 0.9, "fiddle": 1.0},
    {"bass": {"*": "two", "verse1": ((0.4, "two"), (0.0, "roots")), "bridge": "two", "tag": "long"},
     "banjo": {"intro": "roll", "verse1": "claw", "verse": ((0.6, "roll"), (0.0, "claw")),
               "refrain": ((0.5, "roll"), (0.0, "claw")), "break": "roll", "turn": "roll", "bridge": "claw",
               "tag": "ring", "outro": "roll"},
     "mandolin": {"*": "chop", "verse1": ((0.3, "chop"), (0.0, "")), "bridge": "tremolo", "tag": "ring"},
     "guitar": {"*": "boom", "tag": "ring", "bridge": "boom"},
     "fiddle": {"verse1": "", "verse": "fills", "refrain": "fills", "last": "counter", "bridge": "tone", "tag": "double"}},
    ("fiddle", "banjo", "mandolin"), {"straight": 0.85, "waltz": 0.15},
    {"straight": (1.08, 1.22, 1.4), "waltz": (0.66, 0.74, 0.84)},
    {"V": ("7",), "*": ("power",)}, 0.3, (-0.85, 0.55),
    band={"density": 0.1, "brightness": 0.12, "wear": 0.05},
    singer={"rd": -0.08, "tilt": -0.04, "vibrato_depth": -8.0},
    mix={"space": -0.1, "intimacy": 0.05, "width": 0.05},
    options={"intro": {"lead": 0.75, "count": 0.25}, "alone": 0.08, "stops": 0.3, "breakdown": 0.2, "lift": 0.25,
             "ending": {"cold": 0.5, "ring": 0.3, "rit": 0.2}, "entrances": 0.3,
             "backing": {"thirds": 0.75, "": 0.25}},
)

COUNTRY = _def(
    "country", "country, as a shuffle or a waltz: pedal steel swells and answers under the voice, a honky piano, "
               "brushes, an upright walking up into each chord, a strummed guitar",
    {"bass": 1.0, "guitar": 0.85, "piano": 0.85, "steel": 0.9, "kit": 0.75},
    {"bass": {"*": "two", "verse1": "roots", "tag": "long"},
     "guitar": {"*": "strum", "bridge": "boom", "tag": "ring"},
     "piano": {"verse1": ((0.3, "comp"), (0.0, "")), "*": "comp", "bridge": "arpeggio", "tag": "ring"},
     "steel": {"*": "under", "verse1": "fills", "bridge": "tone", "tag": "double"},
     "kit": {"verse1": ((0.3, "brushes"), (0.0, "")), "verse": "brushes", "refrain": "groove", "bridge": "brushes",
             "tag": "end", "turn": "groove"}},
    ("steel", "piano"), {"shuffle": 0.55, "waltz": 0.45},
    {"shuffle": (0.86, 1.0, 1.12), "waltz": (0.62, 0.7, 0.8)},
    {"I": ("6",), "IV": ("6",), "V": ("7",)}, 0.45, (-0.3, 0.2),
    singer={"scoop": 0.08, "glide": 0.01, "vibrato_depth": -3.0, "tilt": -0.03},
    mix={"plate": 0.2, "width": 0.05},
    options={"intro": {"lead": 0.9, "count": 0.1}, "alone": 0.1, "stops": 0.1, "breakdown": 0.2, "lift": 0.35,
             "ending": {"ring": 0.4, "rit": 0.4, "cold": 0.2}, "entrances": 0.25,
             "backing": {"thirds": 0.6, "oohs": 0.2, "": 0.2}},
)

GOSPEL = _def(
    "gospel", "gospel in twelve-eight: a piano's chords on every beat and its runs, an organ holding and swelling, "
              "hand claps and a tambourine on two and four, the backing voices answering, a plagal amen",
    {"piano": 1.0, "organ": 0.9, "ebass": 0.95, "claps": 0.8, "tambourine": 0.65, "kit": 0.55},
    {"piano": {"*": "block", "verse1": "arpeggio", "tag": "block"},
     "organ": {"*": "pad", "refrain": "swell", "last": "swell"},
     "ebass": {"verse1": "roots", "*": "walk", "tag": "long"},
     "claps": {"verse1": "", "verse": ((0.55, "claps"), (0.0, "")), "refrain": "claps", "tag": "claps",
               "break": "claps", "bridge": ""},
     "tambourine": {"refrain": "tambourine", "last": "tambourine", "tag": "tambourine"},
     "kit": {"verse1": "", "verse": ((0.5, "groove"), (0.0, "")), "refrain": "groove", "bridge": "groove",
             "tag": "end", "turn": "groove"}},
    ("piano", "organ"), {"twelve": 1.0}, {"twelve": (0.58, 0.69, 0.8)},
    {"I": ("6", "add9", "maj7"), "IV": ("6", "7", "minor"), "V": ("7", "sus4"), "vi": ("7",)}, 0.6, (-0.1, 0.75),
    singer={"vibrato_depth": 8.0, "scoop": 0.08, "dynamics": 1.5},
    mix={"space": 0.25, "plate": 0.3, "width": 0.1, "choir": 2.0},
    options={"intro": {"lead": 0.5, "pad": 0.3, "voice": 0.2}, "alone": 0.15, "stops": 0.1, "breakdown": 0.45,
             "lift": 0.5, "ending": {"amen": 0.7, "rit": 0.3}, "entrances": 0.3,
             "backing": {"echo": 0.6, "thirds": 0.3, "oohs": 0.1}},
)

SHANTY = _def(
    "shanty", "a sea shanty or work song: the shantyman alone at first, then the gang on every refrain, feet "
              "stamping on one and three and hands on two and four, a concertina's oom-pah, a fiddle",
    {"concertina": 0.9, "fiddle": 0.8, "stomps": 1.0, "claps": 0.8, "bass": 0.7},
    {"concertina": {"verse1": "", "*": "oompah", "bridge": "pad", "tag": "pad"},
     "fiddle": {"verse1": "", "verse": ((0.55, "fills"), (0.0, "")), "refrain": ((0.6, "counter"), (0.0, "")),
                "last": "counter", "bridge": "tone"},
     "stomps": {"verse1": ((0.45, "stomp"), (0.0, "")), "*": "stomp"},
     "claps": {"verse1": "", "verse": ((0.55, "claps"), (0.0, "")), "refrain": "claps", "tag": "claps",
               "bridge": ""},
     "bass": {"verse1": "", "*": "two", "bridge": "long", "tag": "long"}},
    ("fiddle", "concertina"), {"straight": 0.7, "six": 0.3},
    {"straight": (0.88, 1.0, 1.1), "six": (1.05, 1.2, 1.35)},
    {"*": ("power",)}, 0.3, (-0.7, 0.9),
    singer={"rd": -0.1, "vibrato_depth": -10.0, "dynamics": 1.0},
    mix={"space": 0.2, "width": 0.15, "intimacy": -0.08, "choir": 3.0},
    options={"intro": {"voice": 0.6, "lead": 0.4}, "alone": 0.7, "stops": 0.15, "breakdown": 0.3, "lift": 0.2,
             "ending": {"cold": 0.4, "ring": 0.3, "repeat": 0.3}, "entrances": 0.5,
             "backing": {"gang": 0.9, "echo": 0.1}},
    swaps={"concertina": {"accordion": 0.3}},  # a crew's squeezebox is sometimes an accordion: its bass buttons' oom-pah
)

SONGWRITER = _def(
    "songwriter", "a singer-songwriter: a Travis-picked guitar, a harmonica in the breaks and between lines, an "
                  "upright bass coming in later, close and dry",
    {"guitar": 1.0, "harmonica": 0.85, "bass": 0.75},
    {"guitar": {"*": "travis", "tag": "ring"},
     "harmonica": {"verse1": "", "verse": ((0.45, "fills"), (0.0, "")), "refrain": "", "last": "fills",
                   "bridge": "", "tag": "double"},
     "bass": {"verse1": "", "verse": ((0.45, "roots"), (0.0, "")), "refrain": "roots", "bridge": "long",
              "tag": "long"}},
    ("harmonica", "guitar"), {"straight": 0.8, "swing": 0.2}, {"*": (0.84, 0.94, 1.06)},
    {"I": ("add9", "sus2", "maj7"), "IV": ("add9", "maj7", "6"), "V": ("sus4",), "vi": ("7",)}, 0.5, (-0.2, -0.5),
    band={"density": -0.1, "ornament": -0.4},
    singer={"breath": 0.01, "rd": 0.05, "vibrato_depth": -6.0},
    mix={"intimacy": 0.2, "space": -0.3, "width": -0.05},
    options={"intro": {"lead": 0.5, "voice": 0.3, "pad": 0.2}, "alone": 0.2, "stops": 0.0, "breakdown": 0.1,
             "lift": 0.05, "ending": {"ring": 0.5, "rit": 0.4, "repeat": 0.1}, "entrances": 0.1,
             "backing": {"": 0.7, "oohs": 0.15, "thirds": 0.15}},
)

CHAMBER = _def(
    "chamber", "chamber folk: a string section holding the harmony under the voice, a cello's own line below it, "
               "the piano's broken chords, no drums, rubato",
    {"piano": 0.95, "strings": 0.85, "cello": 0.9},
    {"piano": {"*": "arpeggio", "tag": "ring"},
     "strings": {"verse1": "", "*": "pad", "last": "counter", "tag": "pad"},
     "cello": {"verse1": "long", "*": "under", "bridge": "long", "tag": "long"}},
    ("cello", "piano", "strings"), {"straight": 0.7, "waltz": 0.3},
    {"straight": (0.7, 0.8, 0.9), "waltz": (0.56, 0.63, 0.72)},
    {"I": ("maj7", "add9", "sus4"), "IV": ("maj7", "6", "add9"), "V": ("sus4", "7"), "vi": ("7", "add9")}, 0.55,
    (-0.45, -0.85),
    band={"arc": 0.1},
    feel={"humanize": 1.8, "ritardando": 0.2},
    singer={"vibrato_depth": 6.0, "breath": -0.005},
    mix={"space": 0.3, "width": 0.15, "intimacy": -0.05},
    options={"intro": {"lead": 0.6, "pad": 0.4}, "alone": 0.2, "stops": 0.0, "breakdown": 0.15, "lift": 0.15,
             "ending": {"rit": 0.7, "ring": 0.3}, "entrances": 0.5, "backing": {"oohs": 0.3, "": 0.7}},
)

LULLABY = _def(
    "lullaby", "a lullaby: a music box's comb and a celesta high above the voice, a harp's broken chords, a soft pad",
    {"musicbox": 0.9, "harp": 0.8, "celesta": 0.7, "synthpad": 0.6},
    {"musicbox": {"*": "box", "bridge": "box"},
     "harp": {"verse1": ((0.3, "arpeggio"), (0.0, "")), "*": "arpeggio", "tag": "ring"},
     "celesta": {"verse1": "", "verse": "", "refrain": "bells", "last": "hook", "bridge": "bells"},
     "synthpad": {"*": "pad"}},
    ("musicbox", "celesta"), {"waltz": 0.5, "six": 0.3, "straight": 0.2},
    {"straight": (0.65, 0.73, 0.83), "waltz": (0.44, 0.5, 0.58), "six": (0.73, 0.83, 0.95)},
    {"I": ("add9", "maj7", "6"), "IV": ("add9", "maj7"), "V": ("sus4",), "vi": ("7",)}, 0.5, (0.1, -1.0),
    band={"density": -0.2, "brightness": -0.1, "arc": -0.2},
    singer={"breath": 0.02, "rd": 0.1, "vibrato_depth": -6.0, "dynamics": -2.0},
    mix={"intimacy": 0.2, "space": 0.1, "plate": 0.3},
    options={"intro": {"pad": 0.6, "lead": 0.4}, "alone": 0.1, "stops": 0.0, "breakdown": 0.0, "lift": 0.0,
             "ending": {"rit": 0.8, "ring": 0.2}, "entrances": 0.3, "backing": {"oohs": 0.4, "": 0.6}},
)

AMBIENT = _def(
    "ambient", "ambient drone: a synth pad and a slow bowed swell over a held drone, a vibraphone's scattered "
               "notes, no drums, the voice far off in a big space",
    {"synthpad": 1.0, "strings": 0.7, "drone": 0.7, "vibes": 0.5},
    {"synthpad": {"*": "pad"},
     "strings": {"verse1": "", "verse": "", "refrain": "swell", "bridge": "swell", "tag": "swell"},
     "drone": {"*": "drone"},
     "vibes": {"verse1": "", "verse": ((0.45, "bells"), (0.0, "")), "refrain": "bells", "bridge": "bells"}},
    ("vibes", "strings"), {"half": 1.0}, {"*": (0.62, 0.7, 0.8)},
    {"*": ("add9", "sus2", "power")}, 0.6, (0.6, -0.9),
    band={"density": -0.25, "arc": -0.2},
    singer={"breath": 0.015, "rd": 0.08, "vibrato_depth": -4.0},
    mix={"space": 0.45, "intimacy": -0.15, "width": 0.25, "plate": 0.5},
    options={"intro": {"pad": 0.9, "lead": 0.1}, "alone": 0.2, "stops": 0.0, "breakdown": 0.0, "lift": 0.0,
             "ending": {"ring": 0.6, "rit": 0.4}, "entrances": 0.6, "backing": {"oohs": 0.6, "": 0.4}},
)

SYNTHFOLK = _def(
    "synthfolk", "synth folk: an analog arpeggio ticking over a strummed guitar, a sub bass, a pad, a drum "
                 "machine's four on the floor, a synth lead taking the breaks",
    {"synthbass": 1.0, "arp": 0.85, "guitar": 0.75, "synthpad": 0.75, "drummachine": 0.9, "synthlead": 0.8},
    {"synthbass": {"verse1": "sub", "*": "eighths", "bridge": "sub", "tag": "long"},
     "arp": {"verse1": ((0.35, "arp"), (0.0, "")), "*": "arp", "bridge": "", "tag": "arp"},
     "guitar": {"*": "strum", "tag": "ring"},
     "synthpad": {"*": "pad"},
     "drummachine": {"verse1": ((0.45, "half"), (0.0, "")), "verse": ((0.45, "four"), (0.0, "half")), "*": "four",
                     "bridge": "half", "tag": "end"}},
    ("synthlead", "arp"), {"straight": 1.0}, {"*": (1.04, 1.15, 1.27)},
    {"*": ("add9", "sus2"), "V": ("sus4",)}, 0.5, (1.0, 0.3),
    singer={"vibrato_depth": -10.0, "tilt": -0.03},
    mix={"width": 0.2, "space": 0.05, "plate": 0.2},
    options={"intro": {"pad": 0.4, "lead": 0.3, "count": 0.3}, "alone": 0.1, "stops": 0.2, "breakdown": 0.5,
             "lift": 0.2, "ending": {"cold": 0.4, "ring": 0.3, "repeat": 0.3}, "entrances": 0.7,
             "backing": {"oohs": 0.3, "gang": 0.2, "": 0.5}},
)

LOFI = _def(
    "lofi", "lo-fi bedroom: an electric piano's lazy sevenths and ninths, a soft swung drum machine, a round bass, "
            "a vibraphone now and then, worn tape and a dark top",
    {"epiano": 1.0, "synthbass": 0.9, "drummachine": 0.75, "vibes": 0.45},
    {"epiano": {"*": "epiano", "tag": "ring"},
     "synthbass": {"verse1": "sub", "*": "sub", "tag": "long"},
     "drummachine": {"verse1": ((0.4, "lofi"), (0.0, "")), "*": "lofi", "tag": "end"},
     "vibes": {"verse1": "", "verse": "", "refrain": "bells", "bridge": "bells"}},
    ("vibes", "epiano"), {"swing": 1.0}, {"*": (0.73, 0.81, 0.92)},
    {"I": ("maj7", "6", "add9"), "IV": ("maj7", "6"), "V": ("7", "sus4"), "vi": ("7",)}, 0.75, (0.75, -0.35),
    band={"density": -0.1},
    singer={"breath": 0.02, "rd": 0.08, "vibrato_depth": -12.0},
    mix={"wear": 0.22, "tilt": -0.6, "width": -0.1, "intimacy": 0.2, "space": -0.15},
    options={"intro": {"lead": 0.5, "pad": 0.5}, "alone": 0.1, "stops": 0.05, "breakdown": 0.2, "lift": 0.0,
             "ending": {"ring": 0.3, "cold": 0.3, "rit": 0.4}, "entrances": 0.3, "backing": {"oohs": 0.25, "": 0.75}},
)

INDIE = _def(
    "indie", "indie folk and folk rock: a kit driving four to the floor with the floor toms, an electric bass in "
             "eighths, a tremolo electric guitar, an organ underneath, a glockenspiel's hook, claps, gang vocals",
    {"kit": 1.0, "ebass": 1.0, "guitar": 0.8, "electric": 0.8, "organ": 0.65, "glock": 0.55, "claps": 0.65},
    {"kit": {"verse1": ((0.3, "toms"), (0.0, "")), "verse": "toms", "refrain": "groove", "last": "four", "bridge": "half",
             "tag": "end", "turn": "groove"},
     "ebass": {"verse1": "roots", "*": "eighths", "bridge": "roots", "tag": "long"},
     "guitar": {"*": "strum", "tag": "ring"},
     "electric": {"verse1": ((0.3, "tremolo"), (0.0, "")), "verse": "tremolo", "refrain": "pulse", "bridge": "tremolo",
                  "tag": "ring"},
     "organ": {"verse1": "", "*": "pad"},
     "glock": {"refrain": "hook", "last": "hook"},
     "claps": {"last": "claps", "tag": "claps"}},
    ("electric", "glock"), {"straight": 0.75, "half": 0.25}, {"*": (1.06, 1.17, 1.3)},
    {"*": ("add9", "sus2", "power")}, 0.45, (0.4, 0.8),
    singer={"breath": 0.01, "vibrato_depth": -10.0},
    mix={"space": 0.15, "width": 0.2, "wear": 0.05, "choir": 2.0},
    options={"intro": {"count": 0.4, "lead": 0.3, "pad": 0.3}, "alone": 0.1, "stops": 0.25, "breakdown": 0.5,
             "lift": 0.2, "ending": {"cold": 0.4, "ring": 0.3, "repeat": 0.3}, "entrances": 0.6,
             "backing": {"gang": 0.6, "oohs": 0.3, "": 0.1}},
)

BLUES = _def(
    "blues", "country blues: a guitar's shuffle boogie on the low strings, a slide and a harmonica answering the "
             "voice, a foot stomping every beat, dominant sevenths where the tune allows",
    {"guitar": 1.0, "slide": 0.85, "harmonica": 0.8, "stomps": 0.9},
    {"guitar": {"*": "boogie", "tag": "ring"},
     "slide": {"verse1": "fills", "*": "fills", "bridge": "tone", "tag": "double"},
     "harmonica": {"verse1": "", "verse": "", "refrain": ((0.55, "fills"), (0.0, "")), "last": "fills"},
     "stomps": {"*": "stomp4", "verse1": "stomp4"}},
    ("slide", "harmonica"), {"shuffle": 1.0}, {"*": (0.79, 0.9, 1.0)},
    {"I": ("7",), "IV": ("7",), "V": ("7",)}, 0.7, (-0.45, 0.05),
    band={"wear": 0.15},
    singer={"rd": -0.08, "scoop": 0.1},
    mix={"space": -0.15, "wear": 0.15, "intimacy": 0.1},
    options={"intro": {"lead": 0.7, "voice": 0.3}, "alone": 0.1, "stops": 0.4, "breakdown": 0.1, "lift": 0.0,
             "ending": {"ring": 0.3, "cold": 0.4, "rit": 0.3}, "entrances": 0.1, "backing": {"": 0.8, "echo": 0.2}},
)

STYLES = {s.name: s for s in (BALLAD, CHAMBER, LULLABY, AMBIENT, SYNTHFOLK, LOFI, SONGWRITER, COUNTRY, BLUES,
                              GOSPEL, INDIE, SHANTY, STRINGBAND)}
# The ring the styles travel on: each sits between two that share its instruments or its feel, and the ring
# runs once round the plane of (machine, drive), so a machine's harvest puts it somewhere on it (home()):
# synth folk at the machine's end, then the loud ones (indie, gospel), the Americana (blues, country, the
# string band), the traditional (shanty, the ballad, chamber), the hushed (songwriter, lullaby, ambient)
# and lo-fi back at the machine's end. A rendition moves at most one step from its parent's. The seed's own
# arrangement is the ballad.
RING = ("synthfolk", "indie", "gospel", "blues", "country", "stringband", "shanty", "ballad", "chamber", "songwriter",
        "lullaby", "ambient", "lofi")
RING_START = 15.0  # degrees on the (machine, drive) plane where the ring's first style sits
# Styles beside the ring (docs/STYLES.md, "Two more"): each at a ring style's place, its anchor. A person chooses
# one; a lineage in it travels from its anchor's place (keeping its own style where it would keep the anchor's),
# and nothing steps into one by chance, so adding one moves no lineage's way round the ring.
OFF_RING: dict[str, str] = {}


def on_ring(name: str) -> str:
    """The ring style a style sits at: itself, or the anchor of one beside the ring."""
    name = name or "ballad"
    return OFF_RING.get(name, name)


def of(style: Style) -> StyleDef:
    """The palette's entry for a rendition's style (the seed's own, "", is the ballad)."""
    return STYLES.get(style.name or "ballad", BALLAD)


def neighbours(name: str) -> tuple[str, str]:
    k = RING.index(on_ring(name))
    return RING[(k - 1) % len(RING)], RING[(k + 1) % len(RING)]


# --- beside the ring: a cappella (docs/STYLES.md, "Two more", 2026-09-30; "A cappella and the jig, revised") ---
#
# Only voices: the lead on the tune and a group in harmony around it, the lineage's own voices first and then the
# program's own harmony voices, at least three (group); the parts are idioms.shape_parts. Everyone on the refrains'
# words; under the verses a hum, "oo"s or the line ends answered; where a band would play the tune the lead hums it
# on "oo" over the group's chords (revised 2026-09-30: no shape-note syllables). Feet or hands come now and then
# (optional); a player that doesn't come sits in the lineup at gain 0, so the lineup is never empty (empty is the
# seed's eight).

ACAPPELLA = _def(
    "acappella", "a cappella, voices alone: the lead on the tune and a group in open harmony around it, everyone on "
                 "the refrains' words, a hum or answers under the verses, feet or hands now and then",
    {"stomps": 0.9, "claps": 0.7},
    {"stomps": {"verse1": "", "verse": ((0.5, "stomp"), (0.0, "")), "refrain": "stomp", "turn": "stomp", "bridge": "",
                "tag": "stomp"},
     "claps": {"refrain": ((0.6, "claps"), (0.0, "")), "last": "claps", "tag": "claps"}},
    (), {"straight": 0.7, "waltz": 0.3}, {"straight": (0.85, 0.95, 1.1), "waltz": (0.6, 0.66, 0.76)},
    {"*": ("power",)}, 0.4, (-0.7, 0.9),
    singer={"vibrato_depth": -6.0, "rd": -0.05},
    mix={"space": 0.25, "plate": 0.2, "width": 0.15, "choir": 1.5},
    options={"intro": {"lead": 0.65, "pad": 0.35, "voice": 0.5}, "alone": 0.6, "stops": 0.0, "breakdown": 0.0,
             "lift": 0.0, "ending": {"ring": 0.6, "repeat": 0.25, "rit": 0.15}, "entrances": 0.6,
             "backing": {"hum": 0.4, "oohs": 0.35, "echo": 0.25}},
    optional={"stomps": 0.35, "claps": 0.25},
    group=3,
)
STYLES[ACAPPELLA.name] = ACAPPELLA
OFF_RING[ACAPPELLA.name] = "shanty"  # the gang, the crowd singing


def voices_alone(params) -> bool:
    """Whether a rendition's band is its voices (a style that sings as a group, with no instrument on the tune)."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    return sdef is not None and sdef.group > 0 and not sdef.leads


def vocalise(params) -> str:
    """What the lead sings where a band would play the tune (an intro, a break, an outro, a line played): "oo",
    the group humming the chords under it (idioms.shape_parts); "" where a band plays it (every style but a
    cappella). An a cappella's shape-note syllables (fa, sol, la, mi) were taken out on 2026-09-30: the artist
    heard them as gibberish."""
    return "oo" if voices_alone(params) else ""


# --- beside the ring: the jig (docs/STYLES.md, "Two more", 2026-09-30; "A cappella and the jig, revised") --------
#
# The song as a jig, always in six-eight (H's long-short-short feet are a jig's dotted beat; a song that can't be
# re-barred keeps its beats and plays them in threes: feels_for). The whistle and the fiddle (and a concertina, when
# it comes) play the tune together where nobody sings, each its own way (cuts and rolls, slides and slurs, plain),
# a short played section round twice (rounds: songbird.takeover.phrase_plan), the first time the lead and the
# guitar, the second everyone; the frame drum tipped, down-up-down on each dotted beat; a guitar in an open tuning
# (DADGAD); a reed drone when it comes. The singer keeps the song, with a few turns of its own (ornaments). Named
# for what it plays, not for a tradition it would claim: it was "celtic", a session, with a reel, until the artist
# asked for "jig" (2026-09-30); records and edits that say "celtic" are read as the jig (RENAMED).

JIG = _def(
    "jig", "jig: the song in six-eight, the whistle and the fiddle on the tune together, round twice between the "
           "verses, a tipped frame drum, a guitar in DADGAD, a concertina or a reed drone when they come",
    {"whistle": 1.0, "fiddle": 0.95, "guitar": 0.85, "drum": 0.8, "concertina": 0.75, "drone": 0.5},
    {"whistle": {"intro": "lead", "outro": "lead", "break": "lead", "turn": "quote", "verse1": "",
                 "verse": ((0.35, "fills"), (0.0, "")), "refrain": "", "last": "descant", "bridge": "", "tag": "double"},
     "fiddle": {"intro": "lead", "outro": "lead", "break": "lead", "turn": "quote", "verse1": "",
                "verse": ((0.35, "fills"), (0.0, "")), "refrain": ((0.55, "counter"), (0.0, "")), "last": "counter",
                "bridge": "tone", "tag": "double"},
     "concertina": {"intro": "lead", "outro": "lead", "break": "lead", "turn": "quote", "verse1": "", "verse": "",
                    "refrain": ((0.6, "pad"), (0.0, "")), "bridge": "pad", "tag": "pad"},
     "guitar": {"*": "dadgad"},
     "drum": {"intro": "tipped", "verse1": ((0.4, "tipped-light"), (0.0, "")), "verse": "tipped-light",
              "refrain": "tipped", "turn": "tipped", "break": "tipped", "outro": "tipped", "bridge": "tipped-light",
              "tag": "tipped"},
     "drone": {"intro": "drone", "turn": "drone", "break": "drone", "outro": "drone", "bridge": "drone",
               "tag": "drone"}},
    ("whistle", "fiddle", "concertina"), {"six": 1.0},
    # six-eight re-barred; twelve-eight (a song that can't be: each beat in threes, a dotted beat at about 72 for a
    # song at 96); a song already in threes (six-eight) in its own time, a little brisker
    {"six": (1.35, 1.5, 1.6), "twelve": (0.7, 0.75, 0.8), "*": (0.95, 1.05, 1.15)},
    {"*": ("sus2", "power")}, 0.35, (-0.9, 0.3),
    band={"ornament": 0.3, "brightness": 0.05, "wear": 0.05},
    singer={"vibrato_depth": -8.0, "rd": -0.05},
    mix={"space": -0.1, "intimacy": 0.08},
    options={"intro": {"lead": 0.75, "air": 0.25, "voice": 0.3}, "alone": 0.1, "stops": 0.0, "breakdown": 0.0,
             "lift": 0.1, "ending": {"ring": 0.4, "cold": 0.35, "rit": 0.25}, "entrances": 0.3,
             "backing": {"thirds": 0.3, "": 0.7}},
    optional={"concertina": 0.45, "drone": 0.35},
    rounds=2,
    ornaments=0.125,
)
STYLES[JIG.name] = JIG
OFF_RING[JIG.name] = "ballad"  # the seed's own band: whistle, fiddle, frame drum and drone

SET_BARS = 4  # a played section this long or shorter goes round a jig's `rounds` times (the break, eight, once)
AIR_SLOW = 1.7  # a slow air's pace against the song's (the tune slow and free, the lead alone): this many times as slow...
AIR_BROADEN = 0.6  # ...and each line broadening toward its end, its last beat this much slower again


def rounds(genome, params, name: str) -> int:
    """How many times round a section of the form goes as its style plays it: the jig plays a short tune where
    nobody sings round twice; every other section, and every other style, once."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    if sdef is None or sdef.rounds < 2:
        return 1
    section = genome.section(name)
    if section.lyrics is not None:
        return 1
    return sdef.rounds if sum(genome.phrases[p].bars for p in section.phrases) <= SET_BARS else 1


def air(genome, params, phrases, lead: float) -> tuple:
    """The slow air before the song, for the clock (realize.Clock.air): where it ends (units from the first
    pickup: the intro's first time round, a pickup short of the next), how slow, how each line broadens, a line's
    units; () where the rendition has none (every rendition but one whose intro is an air)."""
    if params.style.intro != "air" or not params.form or genome.section(params.form[0]).lyrics is not None:
        return ()
    from .takeover import phrase_plan

    bar = genome.meter.bar
    own = len(genome.section(params.form[0]).phrases)
    k = min(own, len(phrase_plan(genome, params)[0]))  # its first time round (all of it, if it goes round once)
    end = lead + sum(p.bars for p in phrases[:k]) * bar - (phrases[k].pickup if k < len(phrases) else 0)
    return (float(end), AIR_SLOW, AIR_BROADEN, float(phrases[0].bars * bar))


def sung_ornaments(genome, params) -> tuple:
    """A singer's own ornaments where its style leans that way (the jig's singer): on some long stressed
    notes the lineage hasn't ornamented, a grace, a mordent or a turn from the song's own vocabulary
    (variants.candidates: always a degree of its scale, on a note long enough to hold it), fixed by the rendition's
    seed and never handed down; () for every other style."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    if sdef is None or not sdef.ornaments:
        return ()
    from . import variants as V

    have = {v.key for v in params.variants}
    foot, beat = genome.meter.foot, genome.meter.beat
    by_note: dict = {}
    for v in V.candidates(genome):
        note = genome.phrases[v.phrase].sung[v.note]
        if v.kind in ("grace", "mordent", "turn") and v.key not in have and note.onset % foot == 0 and note.dur >= beat:
            by_note.setdefault(v.key, []).append(v)
    rng = np.random.default_rng([int(params.seed) & 0xFFFFFFFF, 0x5EA7])
    chosen: list = []
    for key in sorted(by_note):
        options = by_note[key]
        if rng.random() < sdef.ornaments:
            v = options[int(rng.integers(len(options)))]
            if V.fits(genome, (*params.variants, *chosen), v):
                chosen.append(v)
    return tuple(chosen)


# --- house and dub (2026-09-30; docs/STYLES.md, "House and dub") --------------------------------------------------
#
# Beside the ring, as a cappella and the session are (OFF_RING): a person chooses them, or a parent hands one down; a
# child of one travels from its anchor's place, keeping its style where it would keep the anchor's and stepping to
# the anchor's neighbour where the drift moves it. So a lineage can leave them, never wander in.

# The dub desk's habits (songbird.idioms, the desk; songbird.sound.thrown; synth/dub.py): how often a bar drops out
# by section, which way, how often a line's end or a hit is thrown into the tape echo or splashed into the spring,
# and the echo's time (beats), feedback and levels.
DESK = {
    "dropout": {"intro": 0.3, "turn": 0.5, "break": 0.4, "outro": 0.4, "version": 0.55, "verse": 0.08,
                "refrain": 0.06, "bridge": 0.12},
    "kinds": {"riddim": 0.5, "drums": 0.25, "nodrums": 0.25},  # drums and bass alone, the drums alone, no drums
    "voice": {"verse": 0.3, "refrain": 0.45, "bridge": 0.3, "tag": 0.6},  # a line's last word into the echo
    "splash": 0.12,  # a bar's snare kicked into the spring
    "time": 0.75, "feedback": 0.6, "level": 2.0, "voice_level": 0.5, "splash_level": 3.0,
}
# A version after the song in a style without a desk of its own: the desk works the version only, and throws the
# singer's last line into it.
VERSION_DESK = {**DESK, "dropout": {"version": 0.55}, "voice": {}, "splash": 0.0}
VERSION_BARS = 8  # the version: the last refrain's last eight bars' chords again
VERSION_RING = 6.0  # s after the version's last chord: its echoes' tails

# House's loops (2026-09-30, evening): degrees a bar, voiced as sevenths; the rendition plays one that fits its tune
HOUSE_LOOPS = {"vamp": ((6, 4), True), "lift": ((4, 1), True), "home": ((1, 4), True), "deep": ((2, 5, 1, 6), True),
               "royal": ((4, 5, 3, 6), True), "pop": ((6, 4, 1, 5), True), "minor": ((7, 4, 1, 5), True)}
# The chop's rhythms: a two-bar figure, each bar (sixteenth of the bar, syllable, sixteenths long); drawn per rendition
HOUSE_HOOK = {
    "syllables": 4, "vel": 0.85, "drop": 1.0, "soft": 0.6, "staccato": 0.85,
    "answered": ("drop", "last"),  # where every other bar is the answer ("now it's by you"); hook_bars' hows
    "rhythms": {"beat": ([(0, 0, 2), (2, 1, 1), (3, 2, 1), (4, 3, 4)],
                         [(0, 0, 2), (2, 1, 1), (3, 2, 1), (4, 3, 2), (8, 3, 1), (10, 3, 2)]),
                "off": ([(2, 0, 1), (3, 1, 1), (4, 2, 2), (6, 3, 3)],
                        [(2, 0, 1), (3, 1, 1), (4, 2, 2), (6, 3, 2), (10, 3, 1), (14, 3, 2)]),
                "stutter": ([(0, 0, 1), (1, 1, 1), (2, 2, 1), (3, 3, 2), (6, 3, 1), (7, 3, 1)],
                            [(0, 0, 1), (1, 1, 1), (2, 2, 1), (3, 3, 4)])},
}

HOUSE = _def(
    "house", "house: a drum machine's four on the floor (a 909), claps on two and four, open hats on the off-beats, "
             "the ride in the drop, a chord loop of its own in piano stabs, an off-beat and octave synth bass, a "
             "pluck, a pad pumping under the kick, and the song's hook chopped and sung on the grid",
    {"drummachine": 1.0, "synthbass": 0.95, "piano": 0.8, "synthpad": 0.7, "arp": 0.6},
    {"drummachine": {"intro": "floor", "verse1": "floor", "verse": ((0.55, "house"), (0.0, "floor")),
                     "refrain": "house", "drop": "drop", "turn": "house", "break": "drop", "bridge": "house",
                     "tag": "end", "outro": "house"},
     "synthbass": {"verse1": ((0.35, "offbeat"), (0.0, "")), "*": "offbeat", "refrain": "octave", "turn": "octave",
                   "outro": "octave", "drop": "rolling", "tag": "long"},
     "piano": {"verse1": ((0.4, "stab"), (0.0, "")), "verse": ((0.45, "stab"), (0.0, "")), "*": "stab", "tag": "ring"},
     "synthpad": {"*": "pad"},
     "arp": {"refrain": "pluck", "drop": "pluck", "break": "pluck", "turn": "pluck", "outro": "pluck"}},
    ("piano", "arp"), {"straight": 1.0}, {"*": (1.27, 1.29, 1.31)},
    {"I": ("add9", "6"), "IV": ("add9", "maj7"), "V": ("sus4", "7"), "vi": ("7", "add9"), "ii": ("7",)}, 0.6,
    (0.95, 0.95),
    band={"density": 0.1, "brightness": 0.1},
    singer={"vibrato_depth": -6.0},
    mix={"space": -0.05, "width": 0.2, "plate": 0.25},
    options={"intro": {"lead": 0.5, "pad": 0.5}, "alone": 0.0, "stops": 0.0, "breakdown": 0.0, "lift": 0.15,
             "ending": {"cold": 0.5, "ring": 0.5}, "entrances": 0.5,
             "backing": {"echo": 0.4, "oohs": 0.3, "": 0.3}, "drop": 0.8, "half": 0.0},
    swaps={"piano": {"organ": 0.3}},  # the stabs are sometimes an organ's
    sound={"players": {"drummachine": {"kit": "909"}, "synthpad": {"sidechain": "classic"},
                       "synthbass": {"sidechain": "subtle"}, "piano": {"sidechain": "subtle"},
                       "arp": {"sidechain": "subtle"}},
           "intro": "open"},
    loops=HOUSE_LOOPS,
    looped=("intro", "verse", "refrain", "turn", "break", "tag", "outro"),  # the bridge keeps the song's own chords
    # the intro builds in layers (bars in: the drums, the bass at five, the pad and stabs at nine, the tune or the
    # chop at thirteen), the outro leaves in layers (bars out: the stabs, pad and pluck at nine, the bass at thirteen)
    form={"bars": {"intro": 16, "turn": 4, "outro": 16}, "after": {"drop": 8, "last": 8},
          "layers": {"intro": {"bass": 4, "chords": 8, "lead": 12}, "outro": {"chords": 8, "bass": 12}}},
    hook=HOUSE_HOOK,
)

DUB_DESK = {
    **DESK,
    # the version (Style.dissolve): bars dropping out more, a fragment's echo longer and louder, the spring kicked more,
    # the band's low-pass swept closed and open now and then, the bass leading, the melodica resting a line now and then
    "dissolved": {"dropout": 0.45, "feedback": 0.72, "voice_level": 0.8, "voice_throw": 0.9, "voice_spring": 0.2,
                  "splash": 0.3, "sweep": 0.5, "sweep_bars": 2, "bass": 1.12, "others": 0.9, "rest": 0.5},
}

DUB = _def(
    "dub", "dub and roots reggae: the kit's one drop, the skank on the off-beats, an organ's bubble, a deep round bass "
           "with space, a melodica's answers, and the mixing desk played: the song sung, then taken apart into "
           "its version over a riddim, the singer's lines in fragments thrown into the echo, the band dropping out "
           "and back",
    {"kit": 0.9, "ebass": 1.05, "electric": 0.95, "organ": 0.6, "melodica": 0.75},
    {"kit": {"verse1": ((0.3, "onedrop"), (0.0, "")), "*": "onedrop", "last": "steppers", "version": "onedrop"},
     "ebass": {"*": "dubbass"},
     "electric": {"verse1": ((0.3, "skank"), (0.0, "")), "*": "skank", "dubbed": "skank"},
     "organ": {"verse1": "", "verse": ((0.45, "bubble"), (0.0, "")), "*": "bubble", "bridge": "pad",
               "dubbed": "bubble"},
     "melodica": {"verse1": "", "verse": "fills", "refrain": ((0.6, "fills"), (0.0, "")), "last": "fills",
                  "bridge": "", "tag": "", "version": "lead", "dubbed": "lead"}},
    ("melodica", "organ"), {"swing": 0.65, "straight": 0.35}, {"*": (0.73, 0.77, 0.81)},
    {"vi": ("7",), "ii": ("7",), "iii": ("7",)}, 0.2, (0.55, -0.55),
    band={"wear": 0.1, "brightness": -0.08},
    singer={"vibrato_depth": -6.0, "scoop": 0.04},
    mix={"space": 0.15, "width": 0.1, "wear": 0.08, "tilt": -0.3, "plate": 0.2},
    options={"intro": {"lead": 0.6, "pad": 0.1, "count": 0.3}, "alone": 0.1, "stops": 0.0, "breakdown": 0.35,
             "lift": 0.0, "ending": {"version": 0.75, "ring": 0.15, "cold": 0.1}, "entrances": 0.3,
             "backing": {"thirds": 0.4, "echo": 0.3, "": 0.3}, "half": 0.0, "dissolve": 0.9,
             "slack": 4.0},  # a riddim under fragments may rub a little more than a loop under the whole tune
    desk=DUB_DESK,
    loops={"roots": ((1, 4), False), "minor": ((6, 4), False), "plagal": ((4, 1), False)},  # the riddims
    looped=("version",),  # the version's sections (Style.dissolve), and so the dub-out after the song
)

STYLES[HOUSE.name] = HOUSE
OFF_RING[HOUSE.name] = "synthfolk"  # the machines' end, the drum machine and the synths
STYLES[DUB.name] = DUB
OFF_RING[DUB.name] = "lofi"  # slow, worn, the bass and the room
# Not offered in the studio's picker for now (the artist, 2026-09-30: "they haven't convinced me like the others
# yet"): a record, a draft or --style still plays them, and a version already in one still shows it
HIDDEN = frozenset({HOUSE.name, DUB.name})


def offered(current: str | None = None) -> tuple[str, ...]:
    """The styles the studio offers: the ring and those beside it, but the hidden ones, unless it's this version's."""
    return tuple(k for k in (*RING, *OFF_RING) if k not in HIDDEN or k == current)


def desk_of(params) -> dict:
    """The desk a rendition's band is dubbed with: its style's, or a version's in a style without one; {} none."""
    sdef = of(params.style)
    if sdef.desk:
        return sdef.desk
    return VERSION_DESK if params.style.ending == "version" else {}


# --- a loop of the style's own (2026-09-30, evening; docs/STYLES.md, "House and dub, again") ------------------------
#
# A loop is scale degrees a bar, the mode's own chords on them (a seventh where the style voices sevenths), laid
# under the sections the style loops from each section's first bar, round and round, in place of the song's chords
# (composition.form_phrases). Which loop: the rendition's (Style.loop), or the one that best fits the tune.

NUMERALS = ("I", "II", "III", "IV", "V", "VI", "VII")
SEVENTH_NAMES = {(4, 7, 11): "maj7", (3, 7, 10): "m7", (4, 7, 10): "7", (3, 6, 10): "m7b5", (3, 6, 9): "dim7"}
LOOP_SLACK = 2.0  # beats: a loop fits if it clashes with the tune no more than the song's own chords and this much


def loop_symbols(degrees, sevenths: bool, mode: str) -> list[str]:
    """A loop's chords in a mode, one a bar, as the genome writes chords: the mode's triad on each degree (a plain
    numeral, lower case where it is minor), or its seventh chord (vim7, IVmaj7, V7) where the style voices sevenths;
    a major tonic an added ninth instead (Iadd9: a maj7's leading tone would sit a semitone under the tune's home)."""
    from .theory import degree_semitones

    out = []
    for d in degrees:
        tones = [degree_semitones(d + 2 * k, mode) for k in range(4)]
        steps = tuple(t - tones[0] for t in tones[1:])
        numeral = NUMERALS[d - 1] if steps[0] == 4 else NUMERALS[d - 1].lower()
        quality = SEVENTH_NAMES.get(steps, "") if sevenths else ""
        if sevenths and d == 1 and steps[0] == 4:
            quality = "add9"
        out.append(numeral + quality)
    return out


def _chord_pcs(symbol: str, mode: str, triad: bool = True) -> set:
    from .theory import chord_tones

    tones = chord_tones(symbol, mode)
    return {t % 12 for t in (tones[:3] if triad else tones)}


def tune_clash(genome, mode: str, chord_at) -> float:
    """How much of the song's verse and refrain tune clashes with the chords `chord_at(section, line, bar, onset)`
    gives (a symbol): the beats of sung notes that aren't tones of their chord (a seventh counts: the tune on a maj7 is
    its colour; a seventh a semitone from a sung note steps aside) and are a semitone from one of its triad,
    a long or strong note (a beat or more, or on a foot) counted whole and a passing one a third."""
    from .theory import degree_semitones

    m = genome.meter
    bad = 0.0
    for name in ("verse", "refrain"):
        if name not in genome.sections:
            continue
        for line, pid in enumerate(genome.section(name).phrases):
            p = genome.phrases[pid]
            for n in p.sung:
                bar = int(min(max(n.onset // m.bar, 0), p.bars - 1))
                symbol = chord_at(name, line, bar, n.onset)
                chord, whole = _chord_pcs(symbol, mode), _chord_pcs(symbol, mode, triad=False)
                pc = degree_semitones(n.degree, mode, n.alter) % 12
                if pc in whole or not any(min((pc - t) % 12, (t - pc) % 12) == 1 for t in chord):
                    continue
                w = n.dur / m.beat
                bad += w if n.dur >= m.beat or n.onset % m.foot == 0 else w / 3.0
    return round(bad, 4)


def _own_chord(genome, name, line, bar, onset) -> str:
    p = genome.phrases[genome.section(name).phrases[line]]
    in_bar = p.chords[bar]
    return in_bar[int(min(max((onset - bar * genome.meter.bar) * len(in_bar) // genome.meter.bar, 0), len(in_bar) - 1))]


def loop_clash(genome, degrees, sevenths: bool, mode: str) -> float:
    """tune_clash() for a loop laid from each section's first bar."""
    symbols = loop_symbols(degrees, sevenths, mode)

    def at(name, line, bar, onset):
        before = sum(genome.phrases[q].bars for q in genome.section(name).phrases[:line])
        return symbols[(before + bar) % len(symbols)]

    return tune_clash(genome, mode, at)


def fitting_loops(genome, sdef: StyleDef, mode: str) -> list[str]:
    """The style's loops that fit the tune in this mode (no more clash than the song's own chords and the style's
    slack, LOOP_SLACK by default), in the style's order; where none does, ["song"]: the song's own chords (the style's
    form, bass and hook carry it there)."""
    if not sdef.loops:
        return []
    own = tune_clash(genome, mode, lambda n, line, bar, onset: _own_chord(genome, n, line, bar, onset))
    scores = {name: loop_clash(genome, d, s, mode) for name, (d, s) in sdef.loops.items()}
    fit = [name for name in sdef.loops if scores[name] <= own + sdef.options.get("slack", LOOP_SLACK) + 1e-9]
    return fit or ["song"]


def loop_of(genome, params) -> list[str] | None:
    """The rendition's loop as chords a bar in its mode (Style.loop, or the style's best-fitting one), or None: the
    song's own chords (a style without loops, or "song")."""
    name = params.style.name
    sdef = STYLES.get(name) if name else None
    if sdef is None or not sdef.loops or params.style.loop == "song":
        return None
    chosen = params.style.loop if params.style.loop in sdef.loops else fitting_loops(genome, sdef, params.mode)[0]
    if chosen not in sdef.loops:
        return None
    degrees, sevenths = sdef.loops[chosen]
    return loop_symbols(degrees, sevenths, params.mode)


def section_role(genome, name: str) -> str:
    """A section's role as the band names it (songbird.band): intro, verse, refrain, turn, break, bridge, tag, outro."""
    from .band import _role

    return _role(name, genome.section(name))


def dissolved_from(genome, params) -> int | None:
    """The first section of the form that is the version (Style.dissolve: the section after that refrain), or None."""
    k = int(getattr(params.style, "dissolve", 0) or 0)
    refrains = [i for i, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    if not 0 < k <= len(refrains) or refrains[k - 1] + 1 >= len(params.form):
        return None
    return refrains[k - 1] + 1


def own_lines(genome, params) -> list:
    """Each section of the form's tune lines as the style lays them where it has lengths of its own (StyleDef.form:
    house's 16-bar intro and outro, its four-bar turns, the drop's eight bars of the hook before its refrain is sung,
    the last refrain's eight after it), each (line, sung); None where the section is the form's own. The hook's bars
    are laid on the song's turn (a line with no tune: the chop has them to itself), or where it has none, on the
    section's last lines, played. A person's length is laid over this (songbird.takeover)."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    if sdef is None or not sdef.form:
        return [None] * len(params.form)
    from .takeover import fit

    bars, after = sdef.form.get("bars", {}), sdef.form.get("after", {})
    refrains = [k for k, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    drop = int(getattr(params.style, "drop", 0) or 0)
    into = refrains[drop] if 0 < drop < len(refrains) else None
    out = []
    for k, name in enumerate(params.form):
        section = genome.section(name)
        role = section_role(genome, name)
        own = list(section.phrases)
        size = sum(genome.phrases[p].bars for p in own)
        lines = None
        if role in bars and not section.lyrics and bars[role] != size:
            if any(genome.phrases[p].sung for p in own):
                lines = fit(genome, name, bars[role], False)
            elif bars[role] % size == 0:  # a turn: its own line (a quote, or the style's hook) round again
                lines = [(p, False) for p in own] * (bars[role] // size)
        if section.lyrics == "refrain" and (k == into or k == len(params.form) - 1):
            before = hook_lines(genome, own, after.get("drop", 0)) if k == into else []
            behind = hook_lines(genome, own, after.get("last", 0)) if k == len(params.form) - 1 else []
            if before or behind:
                lines = [(p, False) for p in before] + [(p, True) for p in own] + [(p, False) for p in behind]
        out.append(lines)
    return out


def hook_lines(genome, own: list, bars: int) -> list:
    """Lines making `bars` bars for a style's hook: the song's turn round again (a line with no tune) where it has one
    that fits, else the section's own last lines (takeover.tail); [] for none."""
    from .takeover import tail

    if bars <= 0:
        return []
    turn = [p for p in (genome.sections["turn"].phrases if "turn" in genome.sections else ())]
    size = sum(genome.phrases[p].bars for p in turn)
    if turn and size and bars % size == 0 and not any(genome.phrases[p].sung for p in turn):
        return turn * (bars // size)
    return tail(genome, own, bars) or []


def breakdown_of(genome, params) -> tuple[int, int] | None:
    """The sections of the form a drop's breakdown holds (Style.drop), as (first, the drop's refrain), or None."""
    drop = int(getattr(params.style, "drop", 0) or 0)
    refrains = [k for k, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    if not 0 < drop < len(refrains) or refrains[drop] - refrains[drop - 1] < 2:
        return None
    return refrains[drop - 1] + 1, refrains[drop]


def hook_bars(genome, params, lead: float) -> list[tuple[float, float, str]]:
    """Where a style's vocal chop sings (StyleDef.hook, house's), in grid units: (from, to, how): its turns whole, the
    bars the style lays in a refrain before or after its lines (own_lines: the drop's before, the last's after), the
    intro's last bars where no instrument states the tune there, the outro's first half; "soft" in a breakdown, "drop"
    at the drop, "last" after the last refrain, "turn" in a turn, "full" elsewhere (the answer, "now it's by you",
    joins the call where the hook's "answered" says)."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    if sdef is None or not sdef.hook:
        return []
    from .takeover import phrase_plan, spans

    bar = genome.meter.bar
    down = breakdown_of(genome, params)
    refrains = [k for k, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    styled = own_lines(genome, params)
    out = []
    for k, ((sid, name, a, b), lines) in enumerate(zip(spans(genome, params, lead), phrase_plan(genome, params))):
        role = section_role(genome, name)
        soft = down is not None and down[0] <= k < down[1]
        how = "soft" if soft else "full"
        if role == "turn":
            out.append((a, b, "soft" if soft else "turn"))
        elif role == "refrain" and lines == styled[k] and any(not sung for _p, sung in lines):  # the style's bars
            u, run = a, None
            for pid, sung in lines + [("", True)]:
                if not sung and run is None:
                    run = u
                elif sung and run is not None:
                    drop = down is not None and k == down[1] and run == a  # the drop: the hook before the refrain
                    out.append((run, u, "drop" if drop else "last" if k == refrains[-1] else how))
                    run = None
                u += genome.phrases[pid].bars * bar if pid else 0
        elif role == "intro" and params.style.intro != "lead" and b - a >= 8 * bar:
            out.append((b - 4 * bar, b, how))
        elif role == "outro" and b - a >= 8 * bar:
            out.append((a, a + (b - a) / 2, how))
    return [(a, z, how) for a, z, how in out if z > a + 1e-9]


def hook_words(genome, placed, which: str, n: int) -> list[tuple[str, str, int, int]]:
    """The chop's words and notes: the last words (up to n syllables, the last word at least) of the first refrain's
    first line ("call") or the last refrain's last line ("answer"), as sung there: (syllable, word, syllables in the
    word, pitch degree index in the line)."""
    from .genome import sung_words

    refrains = [(name, phrase, line) for name, phrase, _s, line in placed
                if genome.section(name).lyrics == "refrain" and line]
    if not refrains:
        return []
    firsts = [r for r in refrains if r[1].id == genome.section(r[0]).phrases[0]]
    lasts = [r for r in refrains if r[1].id == genome.section(r[0]).phrases[-1]]
    pick = (firsts[:1] if which == "call" else lasts[-1:]) or refrains[:1]
    name, phrase, line = pick[0]
    words = sung_words(line)[: len(phrase.sung)]
    groups, j = [], 0
    while j < len(words):  # the syllables word by word
        groups.append(j)
        j += max(1, words[j][2])
    k = groups[-1]
    for g in reversed(groups[:-1]):  # back a whole word at a time, as far as n syllables
        if len(words) - g > n:
            break
        k = g
    return [(s, w, c, j) for j, (s, w, c) in enumerate(words) if j >= k]


def chops(genome, params, placed, clock, melody) -> list:
    """A style's vocal chop (house's): the singer singing a short phrase of the song's own words, short and on the grid,
    over and over in the hook's bars (hook_bars), on a two-bar rhythm drawn for the rendition; the song's own notes.
    The chop's own part ("chop": the singer's voice, made without breaths and mixed into the band, on the grid,
    not with the singer's lay), clear of anything sung; [] for a style without a hook."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    if sdef is None or not sdef.hook or not placed:
        return []
    from .score import Note
    from .theory import degree_semitones

    hook = sdef.hook
    bars = hook_bars(genome, params, clock.lead)
    if not bars:
        return []
    m = genome.meter
    sixteenth = m.beat / 4.0
    rhythms = hook["rhythms"]
    names = sorted(rhythms)
    rng = np.random.default_rng([int(params.seed) & 0xFFFFFFFF, 0xC409])
    first = int(rng.integers(len(names)))  # the rendition's rhythm; the drop takes the next (a change of figure)
    sung = sorted((m_["u"], m_["u_end"]) for m_ in melody if m_.get("syllable"))

    def voiced(which):
        words = hook_words(genome, placed, which, hook.get("syllables", 4))
        if not words:
            return []
        phrase = next(p for name, p, _s, line in placed if line and genome.section(name).lyrics == "refrain"
                      and (p.id == genome.section(name).phrases[0 if which == "call" else -1]))
        notes = phrase.sung
        out, at = [], 0
        for s, w, c, j in words:  # each syllable, and whether it begins its word and ends it
            if j < len(notes):
                pitch = params.tonic + degree_semitones(notes[j].degree, params.mode, notes[j].alter)
                out.append((s, w, c, pitch, at == 0, at + 1 >= max(1, c)))
            at = 0 if at + 1 >= max(1, c) else at + 1
        if out:
            out[-1] = (*out[-1][:5], True)  # the phrase's end ends a word
        while 0 < len(out) < 4:  # a short phrase stutters its first syllable in
            out.insert(0, out[0])
        return out

    call, answer = voiced("call"), voiced("answer")
    if not call:
        return []
    from .takeover import spans

    where = spans(genome, params, clock.lead)
    level = {"soft": hook["soft"], "drop": hook["drop"]}
    answered = hook.get("answered", ("drop", "last"))

    def clear(u, end):  # no sung note under it, nor one starting within a sixteenth after (one ending as it starts)
        return not any(a < end + sixteenth - 1e-9 and u + 1e-9 < z for a, z in sung)

    out = []
    for u0, u1, how in bars:
        k = 0
        start = u0
        while start < u1 - 1e-9:
            second = k % 2 == 1
            if how == "soft" and second:
                start += m.bar
                k += 1
                continue
            words = answer if how in answered and second and answer else call
            rhythm = rhythms[names[(first + (how == "drop")) % len(names)]]
            figure = rhythm[1] if second else rhythm[0]
            heard = []  # the figure from its first syllable to where a sung note or the hook's end stops it
            for step, j, length in figure:
                j = min(j, len(words) - 1)
                u = start + step * sixteenth
                end = min(u + length * sixteenth, u1)
                if u >= u1 - 1e-9 or not clear(u, end):
                    break
                heard.append((u, end, j))
            while heard and not words[heard[-1][2]][5]:  # whole words: never ending inside one
                heard.pop()
            if heard and not words[heard[0][2]][4]:  # nor starting inside one
                heard = []
            for u, end, j in heard:
                s, w, c, pitch = words[j][:4]
                t0, t1 = clock.seconds(u), clock.seconds(end)
                section = next((name for _sid, name, a, b in where if a - 1e-9 <= u < b - 1e-9), params.form[-1])
                out.append(Note(part="chop", start=t0, dur=max(0.1, hook.get("staccato", 0.85) * (t1 - t0)),
                                pitch=float(pitch), vel=level.get(how, hook["vel"]), syllable=s, word=w,
                                word_len=c, line_end=j == len(words) - 1, section=section, phrase=""))
            start += m.bar
            k += 1
    return out


FRAGMENTS = {"end": 0.4, "head": 0.2, "tail": 0.2, "whole": 0.05, "none": 0.15}  # a dissolved line's, by its coin
HOOK_LINE = {"whole": 0.5, "tail": 0.5}  # a refrain's first line in the version: the hook at least


def fragments(genome, params, placed) -> dict[int, set]:
    """The syllables the singer keeps of each line in the version (Style.dissolve): {placed index: the syllables'
    indices sung}, for the lines after the song dissolves (but the bridge's: it comes back whole); every other line
    sung whole (absent). Each line by its own coin: its last word, its first or second half (at the word nearest the
    middle), all of it now and then, or nothing; a refrain's first line keeps at least its second half ("nobody
    knows"), the last refrain's last line its second half ("now it's by you")."""
    start = dissolved_from(genome, params)
    if start is None:
        return {}
    from .genome import sung_words
    from .takeover import phrase_plan

    owner = [k for k, lines in enumerate(phrase_plan(genome, params)) for _ in lines]
    refrains = [k for k, name in enumerate(params.form) if genome.section(name).lyrics == "refrain"]
    out: dict[int, set] = {}
    for j, (name, phrase, _s, line) in enumerate(placed):
        if j >= len(owner) or not dissolves(genome, params, owner[j], start) or not line:
            continue
        n = len(phrase.sung)
        words = sung_words(line)[:n]
        groups, g = [], 0
        while g < len(words):
            groups.append(g)
            g += max(1, words[g][2])
        inner = [g for g in groups if 0 < g < n] or [n // 2]
        middle = min(inner, key=lambda g: (abs(g - n / 2.0), g))
        own = genome.section(name).phrases
        rng = np.random.default_rng([int(params.seed) & 0xFFFFFFFF, 0xD0B, j])
        u = float(rng.random())
        if genome.section(name).lyrics == "refrain" and phrase.id == own[0]:
            kind = pick(HOOK_LINE, u)
        elif owner[j] == refrains[-1] and phrase.id == own[-1]:
            kind = "tail"
        else:
            kind = pick(FRAGMENTS, u)
        keep = {"end": range(groups[-1] if groups else 0, n), "head": range(0, middle), "tail": range(middle, n),
                "whole": range(0, n), "none": range(0)}[kind]
        out[j] = set(keep)
    return out


def looped(genome, params) -> list[bool]:
    """Whether each section of the form takes the style's loop: its role is one the style loops, or, for "version",
    it is after the song dissolves (Style.dissolve)."""
    sdef = STYLES.get(params.style.name) if params.style.name else None
    if sdef is None or not sdef.loops:
        return [False] * len(params.form)
    start = dissolved_from(genome, params)
    out = []
    for k, name in enumerate(params.form):
        role = section_role(genome, name)
        out.append(role in sdef.looped or ("version" in sdef.looped and dissolves(genome, params, k, start)))
    return out


def dissolves(genome, params, k: int, start: int | None = None) -> bool:
    """Whether the k-th section of the form is the version (Style.dissolve): after the song dissolves, but for the
    bridge, which comes back whole (sung, the lineage's choir with it, on the song's own chords: the vocal dropping
    back in is a dub's move too)."""
    start = dissolved_from(genome, params) if start is None else start
    return start is not None and k >= start and section_role(genome, params.form[k]) != "bridge"


# --- how a rendition's style is chosen ---------------------------------------------------------------
#
# Like everything else a rendition decides (songbird/variation.py): the machine has a style it is at home
# in, read from its harvest; the drift moves it; the child moves from its parent's style toward it. On
# the ring that means: the machine's home is a place on the ring, the child's place is its parent's moved
# a little way (PULL_STYLE) toward the machine's home and by the slow drift (STYLE_SPAN), a style is
# chosen with hysteresis (a stateless Schmitt trigger, as variation.held), and never more than a step
# from the parent's. The measured rates are in docs/STYLES.md.

PULL_STYLE = 0.1  # how far along the ring a child moves from its parent's style toward its machine's home
STYLE_SPAN = 1.1  # how far a drift of 1 (the slow view) moves it along the ring
STYLE_HOLD = 0.2  # a style changes only once the position is this far past the halfway to the next
HISTORY = 730  # days the hysteresis looks back
KEEP_FEEL = 0.6  # how often a child that keeps its parent's style keeps its feel too


def ring_delta(a: float, b: float, n: int = len(RING)) -> float:
    """The shortest signed way round the ring from a to b."""
    return (b - a + n / 2) % n - n / 2


def at_home(c) -> tuple[float, float] | None:
    """Where a machine is at home among the styles, (machine, drive), each about -1..1, from its harvest:
    newer words and younger files lean to the machine's end, older ones to tradition; a brisk, busy,
    rested machine leans to the loud styles, a slow, tired, free one to the hushed; and its identity
    scatters it, so machines that read alike still differ. None for a machine that gave nothing."""
    if "identity" not in c.known:
        return None
    x = 0.3 * c.era - 0.25 * c.wear + 0.1 * c.density + 0.6 * c.id("style:machine")
    y = 0.3 * c.pace + 0.2 * c.density - 0.2 * c.tired - 0.15 * c.rubato + 0.6 * c.id("style:drive")
    return max(-1.2, min(1.2, x)), max(-1.2, min(1.2, y))


def home(c) -> float | None:
    """The place on the ring a machine is at home in: the angle of its (machine, drive) on the plane the
    ring runs round, as a place between two styles (0 the ring's first, 1 the next...)."""
    where = at_home(c)
    if where is None:
        return None
    x, y = where
    angle = (np.degrees(np.arctan2(y, x)) - RING_START) % 360.0
    return float(angle / (360.0 / len(RING)))


def held_ring(drift, base: float, span: float, n: int = len(RING)) -> int:
    """A place on a ring of n at base + span x the drift's slow "style" dimension, with hysteresis: within
    STYLE_HOLD of a boundary the choice is the one the position last sat firmly in, read back from the
    drift field day by day; so a style changes only when the drift has moved well past a boundary."""
    from .drift import series

    def firm(p: float) -> int | None:
        k = int(np.floor(p + 0.5))
        return k % n if abs(p - k) <= 0.5 - STYLE_HOLD else None

    now = base + span * (drift.view("slow").get("style", 0.0) if drift is not None else 0.0)
    here = firm(now)
    if here is not None:
        return here
    if drift is not None and drift.hash:
        for start in range(1, HISTORY + 1, 60):
            back = np.arange(start, min(start + 60, HISTORY + 1), dtype=float)
            for v in series(drift.t - back, drift.hash, ["style"])["style"]["slow"]:
                k = firm(base + span * float(v))
                if k is not None:
                    return k
    return int(np.floor(now + 0.5)) % n


def place(parent: Style, c, drift) -> str:
    """The style a child is played in: its parent's, or the neighbour its machine and the drift lean to."""
    was = RING.index(on_ring(parent.name))
    own = home(c)
    if own is None:
        return parent.name or "ballad"
    base = was + PULL_STYLE * ring_delta(was, own)
    k = held_ring(drift, base, STYLE_SPAN)
    step = ring_delta(was, k)
    if abs(step) > 1:  # never more than a step from the parent's: the folk process, not a jump
        k = (was + int(np.sign(step))) % len(RING)
    if int(k) == was and (parent.name or "ballad") in OFF_RING:  # kept: a style beside the ring keeps itself
        return parent.name
    return RING[int(k)]


def coin(material: str, what: str, drift=None) -> float:
    """A number in [0, 1) for one of the arrangement's choices: fixed by the machine and the parent, and
    turned slowly by the season's drift, so a rendition a minute later makes the same choice and one a
    season later may not."""
    x = int.from_bytes(hashlib.sha256(f"{material}|{what}".encode()).digest()[:8], "little") / 2**64
    if drift is not None:
        x += 0.35 * drift.view("season").get("arrange", 0.0)
    return x % 1.0


def player(sdef: StyleDef, part: str, parent: dict, material: str) -> str:
    """Who plays one of the style's parts in a rendition: its own player, or one the style may swap in for it
    (the shanty's squeezebox is sometimes an accordion), fixed by the machine and the parent; a lineage keeps
    the player it had."""
    swaps = sdef.swaps.get(part)
    if not swaps:
        return part
    had = next((who for who in (part, *swaps) if who in parent), None)
    if had is not None:
        return had
    return pick({part: 1.0 - sum(swaps.values()), **swaps}, coin(material, f"swap:{part}"))


def comes(sdef: StyleDef, part: str, inst: str, was: dict, kept: bool, material: str) -> bool:
    """Whether a style's optional player comes this time (StyleDef.optional): as it did for a parent in the same
    style, else by chance, fixed by the machine and the parent."""
    if kept and inst in was:
        return was[inst] > 0.02
    return coin(material, f"comes:{part}") < sdef.optional[part]


def pick(weights: dict, u: float) -> str:
    total = sum(w for w in weights.values() if w > 0)
    if total <= 0:
        return ""
    acc = 0.0
    for key, w in sorted(weights.items()):
        if w <= 0:
            continue
        acc += w / total
        if u < acc:
            return key
    return max(sorted(weights), key=lambda k: weights[k])


def feels_for(genome, sdef: StyleDef) -> dict:
    """The feels a style can play this song in: a waltz or six-eight only where the song can be re-barred."""
    from .idioms import triple_ok

    ok = triple_ok(genome)
    feels = {f: w for f, w in sdef.feels.items() if ok or f not in ("waltz", "six")}
    if not feels and set(sdef.feels) == {"six"}:  # the jig on a song that can't be re-barred: its beats in threes
        m = genome.meter
        return {"straight": 1.0} if m.beat % 3 == 0 and m.beat > 1 else {"twelve": 1.0}
    return feels or {"straight": 1.0}


def choose_options(genome, form, sdef: StyleDef, parent: Style, kept: bool, voices: int, material: str,
                   drift, c, mode: str = "") -> dict:
    """The arrangement's options for a rendition in this style: its feel, how much colour, how it starts and
    ends, which verse is bare or in stop-time, a breakdown, a lift, entrances, what the backing voices sing."""
    o = sdef.options
    feels = feels_for(genome, sdef)
    if kept and parent.feel in feels and coin(material, "keep-feel") < KEEP_FEEL:
        feel = parent.feel
    else:
        feel = pick(feels, coin(material, "feel", drift))
    verses = [k for k, name in enumerate(form) if genome.section(name).lyrics == "verse"]
    refrains = [k for k, name in enumerate(form) if genome.section(name).lyrics == "refrain"]
    has_intro = any(genome.section(name).lyrics is None and name.startswith("intro") for name in form[:1])
    intros = o.get("intro", {"lead": 1.0})
    if has_intro:
        intro = pick({k: w for k, w in intros.items() if k in ("lead", "pad", "air")} or {"lead": 1.0},
                     coin(material, "intro", drift))
    else:
        intro = pick({k: w for k, w in intros.items() if k in ("count", "voice")} | {"": 0.5}, coin(material, "intro", drift))
    alone = alone_with = stops = 0
    alone_with = ""
    if verses and coin(material, "alone", drift) < o.get("alone", 0.0):
        alone = 1 if o.get("alone", 0.0) >= 0.5 or len(verses) < 2 else max(2, len(verses) - 1)
        chords = [name for name in sdef.lineup if name in CHORDS_FIRST]
        alone_with = "" if coin(material, "alone-with") < 0.45 or not chords else chords[0]
    if len(verses) >= 2 and coin(material, "stops", drift) < o.get("stops", 0.0):
        stops = next((v for v in range(2, len(verses) + 1) if v != alone), 0)
    breakdown = len(refrains) >= 2 and coin(material, "breakdown", drift) < o.get("breakdown", 0.0)
    lift = len(refrains) >= 2 and coin(material, "lift", drift) < o.get("lift", 0.0)
    endings = dict(o.get("ending", {"ring": 1.0}))
    last = genome.section(form[-1]).lyrics if form else None
    if last != "refrain":
        endings.pop("repeat", None)
    ending = pick(endings, coin(material, "ending", drift))
    if sdef.group:  # a style that sings as a group: the lineage's voices, then the program's own (docs/STYLES.md)
        voices = max(voices, min(6, sdef.group))
    backing = pick(o.get("backing", {"": 1.0}), coin(material, "backing", drift)) if voices else ""
    drums = any(instruments_family(name) in ("drums", "drum machine") for name in sdef.lineup)
    bridge = "half" if drums and coin(material, "bridge", drift) < o.get("half", 0.35) else ""
    richness = c.richness if "richness" in c.known else 0.0
    season = drift.view("season").get("arrange", 0.0) if drift is not None else 0.0
    harmony = round(max(0.0, min(1.0, sdef.harmony + 0.15 * richness + 0.12 * season)), 2)
    out = dict(feel=feel, harmony=harmony, intro=intro, alone=alone, alone_with=alone_with, stops=stops,
               breakdown=bool(breakdown), bridge=bridge, lift=bool(lift), ending="" if ending == "ring" else ending,
               entrances=coin(material, "entrances", drift) < o.get("entrances", 0.0), backing=backing,
               voices=voices if backing else 0)
    if o.get("drop") and len(refrains) >= 2 and coin(material, "drop", drift) < o["drop"]:
        # a breakdown and a drop (house's habit): after the second refrain, the first where the song has two
        out["drop"] = 2 if len(refrains) >= 3 else 1
    if sdef.loops and mode:  # a loop of the style's own, one that fits the tune in this mode (a coin of its own)
        fit = fitting_loops(genome, sdef, mode)
        out["loop"] = fit[min(len(fit) - 1, int(coin(material, "loop") * len(fit)))]
    if o.get("dissolve") and refrains and coin(material, "dissolve", drift) < o["dissolve"]:
        # the song dissolves into its version after half its refrains (at least the first)
        out["dissolve"] = max(1, len(refrains) // 2) if len(refrains) >= 2 else 0
    return out


# Instruments that can accompany a bare verse on their own, in the order a style's lineup is searched.
CHORDS_FIRST = ("guitar", "piano", "harp", "epiano", "banjo", "concertina", "accordion", "musicbox", "organ")


def instruments_family(name: str) -> str:
    from .synth import instruments

    try:
        return instruments.spec(name)["family"]
    except ValueError:
        return ""


def _knob(path: str):
    from .variation import KNOBS

    return next((k for k in KNOBS if k.path == path), None)


def _lean(out: dict, path: str, own: float, was: float, lo: float, hi: float, kept: float, current: float,
          step: float = 0.001) -> None:
    """Move a chosen value by this style's offset (own), taking back the share of the parent style's offset
    (was) that reached the child: all of it for a value copied from the parent, 1 - PULL for one pulled
    from it, none for the machine's own. So a style's lean never compounds down a lineage."""
    from .variation import write

    value = current + own - kept * was
    value = round(float(round(max(lo, min(hi, value)) / step) * step), 6)
    write(out, path, value)


def choose_style(out: dict, ctx, forced: str | None = None, arrange: dict | None = None) -> None:
    """The rendition's style: where on the ring it is played (its parent's, or a neighbour's), and what that
    brings: the arrangement's options, the band's lineup and its lean, the tempo the style takes the song
    at, the singer's and the mix's lean. A machine that gave nothing keeps its parent's style."""
    from .synth.voice import VoiceParams
    from .variation import PULL

    parent: Style = ctx.parent.style
    c = ctx.c
    lineage = tuple(parent.lineage) or ((parent.name or "ballad"),)
    if forced is None and "identity" not in c.known:
        out["style"] = Style.from_dict({**parent.to_dict(), "lineage": (lineage + (parent.name or "ballad",))}).to_dict()
        return
    name = renamed("name", forced) or place(parent, c, ctx.drift)
    sdef, pdef = STYLES[name], of(parent)
    kept = name == (parent.name or "ballad")
    digest = hashlib.sha256(json.dumps(ctx.parent.to_dict(), sort_keys=True).encode()).hexdigest()[:16]
    material = f"{c.hash or 'no-voice'}|{digest}|{name}"
    form = tuple(out.get("form", ctx.parent.form))
    voices = int(out.get("choir", ctx.parent.choir))
    options = choose_options(ctx.genome, form, sdef, parent, kept, voices, material, ctx.drift, c,
                             out.get("mode", ctx.parent.mode))
    if arrange and kept and "identity" not in c.known:
        # a person choosing one of the options with no machine to draw the rest: the rest as the version had them
        options = {k: v for k, v in parent.to_dict().items() if k not in ("name", "lineage")}
    options.update(arrange or {})
    style = Style.from_dict({"name": name, "lineage": lineage + (name,), **options})
    out["style"] = style.to_dict()

    # the tempo the style takes the song at: the parent's tempo as a share of its own style's centre, pulled
    # toward the machine's own pace (moved by the day's drift), then that share of this style's centre
    song = ctx.song.tempo
    pl, pc, ph = pdef.centre(parent.feel or "straight") if parent.name else (0.75, 1.0, 1.3)
    lo, centre, hi = sdef.centre(style.feel)
    r_parent = ctx.parent.tempo / (pc * song)
    r_own = r_parent
    if "pace" in c.known:
        r_own = 2 ** (0.18 * c.pace)
    if ctx.drift is not None:
        span = 0.10 + 0.06 * (c.range if "range" in c.known else 0.0)
        r_own *= 1.0 + span * ctx.drift.view("full").get("tempo", 0.0)
    r = r_parent + PULL * (r_own - r_parent)
    out["tempo"] = round(max(lo * song, min(hi * song, r * centre * song)), 1)

    # the band: who plays, as loud as the style has them, each machine's balance its own way
    band = dict(out.get("band") or {})
    if name == "ballad":
        band["lineup"] = {}
    else:
        was = dict(ctx.parent.band.lineup)
        drift = ctx.drift.view("slow") if ctx.drift is not None else {}
        lineup = {}
        for part, gain in sdef.lineup.items():
            inst = player(sdef, part, was, material)
            if part in sdef.optional and not comes(sdef, part, inst, was, kept, material):
                lineup[inst] = 0.0  # it doesn't come this time: in the lineup, sitting out (a person may bring it in)
                continue
            own = gain * 2 ** (0.3 * c.id(f"gain:{inst}")) * (1 + 0.25 * c.id(f"balance:{inst}") * drift.get("balance", 0.0))
            known = inst in was and (part not in sdef.optional or was[inst] > 0.02)  # (one that sat out comes anew)
            g = was[inst] + PULL * (own - was[inst]) if known else own
            lineup[inst] = round(max(0.5 * gain, min(1.5 * gain, g)), 2)
        band["lineup"] = lineup
    for field_name in ("density", "brightness", "wear", "ornament", "arc"):
        off, poff = sdef.band.get(field_name, 0.0), pdef.band.get(field_name, 0.0) if parent.name else 0.0
        if off or poff:
            current = float(band.get(field_name, getattr(ctx.parent.band, field_name)))
            tmp: dict = {}
            _lean(tmp, "x", off, poff, 0.0, 1.0, 1.0 - PULL, current, 0.01)
            band[field_name] = tmp["x"]
    out["band"] = band

    # the performance's looseness: a chamber group breathes, and slows more at the end
    fh, pfh = sdef.feel.get("humanize", 1.0), pdef.feel.get("humanize", 1.0) if parent.name else 1.0
    if fh != 1.0 or pfh != 1.0:
        h = float(out.get("humanize", ctx.parent.humanize)) * fh / pfh ** (1.0 - PULL)
        out["humanize"] = round(max(0.002, min(0.03, h)), 4)
    rit, prit = sdef.feel.get("ritardando", 0.0), pdef.feel.get("ritardando", 0.0) if parent.name else 0.0
    if style.ending == "rit":
        rit += 0.2
    if parent.ending == "rit":
        prit += 0.2
    if rit or prit:
        _lean(out, "ritardando", rit, prit, 0.1, 0.9, 1.0 - PULL, float(out.get("ritardando", ctx.parent.ritardando)),
              0.01)

    # the singer's lean: gently, only the habits a singer might bring to a tradition
    singer = out.setdefault("singer", {})
    for field_name in sorted(set(sdef.singer) | (set(pdef.singer) if parent.name else set())):
        knob = _knob(f"singer.{field_name}")
        off = sdef.singer.get(field_name, 0.0)
        poff = pdef.singer.get(field_name, 0.0) if parent.name else 0.0
        current = float(singer.get(field_name, getattr(VoiceParams(), field_name)))
        lo_b, hi_b = knob.bounds if knob is not None and not callable(knob.bounds) else (-1e9, 1e9)
        kept_share = (1.0 - PULL if knob.inherit else 0.0) if knob is not None else 1.0
        _lean(out, f"singer.{field_name}", off, poff, lo_b, hi_b, kept_share, current, knob.step if knob else 0.001)

    # the mix's lean: how much room, how close, how wide, how far forward; never the room itself
    from .synth.mixing import RANGES, MixParams

    mix = out.setdefault("mix", {})
    defaults = MixParams()
    for field_name in sorted((set(sdef.mix) | (set(pdef.mix) if parent.name else set())) - {"choir"}):
        off = sdef.mix.get(field_name, 0.0)
        poff = pdef.mix.get(field_name, 0.0) if parent.name else 0.0
        knob = _knob(f"mix.{field_name}")
        current = float(mix.get(field_name, getattr(defaults, field_name)))
        lo_b, hi_b = RANGES[field_name]
        kept_share = (1.0 - PULL if knob.inherit else 0.0) if knob is not None else 1.0
        _lean(out, f"mix.{field_name}", off, poff, lo_b, hi_b, kept_share, current, 0.01)
    balance = dict(mix.get("balance") or {})
    if sdef.mix.get("choir"):
        balance["choir"] = float(sdef.mix["choir"])
    else:
        balance.pop("choir", None)
    if balance:
        mix["balance"] = balance
    else:
        mix.pop("balance", None)


# --- what the style asks of realize() -----------------------------------------------------------------


def swing(params) -> float:
    """How far the off-beats are pushed late for the singer and the band (0 straight, 1 a triplet lilt):
    the band's own swing for the seed's arrangement and the ballad; a style's feel otherwise, the band's
    swing being how much within a swung feel."""
    style = params.style
    if not style.name or style.name == "ballad" and not style.feel:
        return params.band.swing
    feel = style.feel or "straight"
    if feel in ("shuffle", "twelve"):
        return 1.0
    if feel == "swing":
        return max(0.35, min(0.7, params.band.swing))
    if feel in ("waltz", "six"):
        return 0.0
    return min(0.25, params.band.swing)  # straight, half, double: a machine's own small lilt at most


def rebarred(genome, params) -> bool:
    """Whether the song is re-barred in three for this rendition (a waltz or a slow six-eight)."""
    from .idioms import triple_ok

    return params.style.feel in ("waltz", "six") and triple_ok(genome)


def triple(genome, params) -> str:
    """"waltz" or "six" when the song is re-barred in three for this rendition, else ""."""
    return params.style.feel if rebarred(genome, params) else ""


def rebar(u: float, lead: float) -> float:
    """Grid units re-barred in three, the feet counted from the first bar line (songbird.idioms.warp)."""
    from .idioms import warp

    return warp(u, lead)


def count_in(genome, params) -> int:
    """Grid units before the song: a bar of silence for a count-in, when the style counts in, or the bars
    of the genome's quote (an older song's line the lead plays alone, songbird.band.prelude_part), when
    the intro quotes and the genome has one to play."""
    if params.style.intro == "count":
        return genome.meter.bar
    if params.style.intro == "quote" and getattr(genome, "quote", None) is not None:
        return genome.quote.bars * genome.meter.bar
    return 0


def coda(genome, params) -> int:
    """Grid units after the last line: two bars for a plagal amen (IV, then I), when the style ends so, or two
    bars of the last chord ringing under the quote's opening (songbird.band.coda_part), when the style asks; a
    dub version's bars (the last refrain's chords again), when the style ends with one."""
    if params.style.ending == "version":
        return VERSION_BARS * genome.meter.bar
    if params.style.ending == "amen" or (params.style.coda == "quote" and getattr(genome, "quote", None) is not None):
        return 2 * genome.meter.bar
    return 0


def slowing(genome, params, rit_start: int, end: int) -> int:
    """Where the final ritardando begins (grid units): the last phrase's first bar line, as ever; a dub version
    holds its tempo and slows only through its last two bars (the riddim doesn't drag under the dub)."""
    if params.style.ending == "version":
        return max(rit_start, end - 2 * genome.meter.bar)
    return rit_start


def repeated_phrases(genome, params) -> list:
    """The phrases sung again after the form: the last line, when the style ends by repeating it and the
    song ends on a refrain."""
    if params.style.ending != "repeat" or not params.form:
        return []
    last = genome.section(params.form[-1])
    return [genome.phrases[last.phrases[-1]]] if last.lyrics == "refrain" else []


def repeated(genome, params, placed) -> list:
    """(section, phrase, line) to lay out after the last placed phrase: the last line again, as sung."""
    if not repeated_phrases(genome, params) or not placed:
        return []
    name, phrase, _start, line = placed[-1]
    if line is None:  # a person had the song's last lines played (songbird.takeover): the last one sung, again
        line = next((x for n, p, _s, x in reversed(placed) if n == name and p.id == phrase.id and x), None)
    return [(name, phrase, line)]


def ring(params) -> float:
    """Seconds the last chord rings on: a cold ending stops short; a dub version's last echoes take longer."""
    if params.style.ending == "version":
        return VERSION_RING
    return 0.9 if params.style.ending == "cold" else 3.0


UNPITCHED = ("drum", "kit", "drummachine", "claps", "stomps", "shaker", "tambourine", "cajon")


def lifted(genome, score) -> float | None:
    """Where the last refrain starts (seconds, its first bar line), or None if the song has no two refrains."""
    refrains = [s for s in score.sections if genome.section(s[0]).lyrics == "refrain"]
    return refrains[-1][1] if len(refrains) >= 2 else None


def finish(score, genome, params):
    """The score as a style leaves it: with a lift, everything pitched from the last refrain's first line
    on (its pickup too) goes up a whole step, the singer, the backing voices and the band together."""
    if not params.style.lift:
        return score
    from dataclasses import replace

    start = lifted(genome, score)
    if start is None:
        return score
    beat = 60.0 / params.tempo
    names = {s[0] for s in score.sections if s[1] >= start - 1e-6}
    notes = []
    for n in score.notes:
        pitched = n.part not in UNPITCHED
        late = n.start >= start - 1e-6 or (n.section in names and n.start >= start - 1.5 * beat
                                            and (n.part == "voice" or n.part.startswith("choir")))
        notes.append(replace(n, pitch=n.pitch + 2.0) if pitched and late else n)
    return replace(score, notes=tuple(notes))
