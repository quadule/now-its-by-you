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
from dataclasses import asdict, dataclass, field, fields

import numpy as np

FEELS = ("straight", "swing", "shuffle", "twelve", "half", "double", "waltz", "six")
INTROS = ("lead", "pad", "count", "voice", "quote")
ENDINGS = ("ring", "rit", "cold", "amen", "repeat", "version")  # version: a dub after the song (2026-09-30)
BACKINGS = ("oohs", "echo", "thirds", "gang")
LINEAGE_MAX = 16  # generations of styles a record remembers
QUIET_OFF = ("drop",)  # Style's options a record leaves out while they're off (added after records were made)


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
            name=str(self.name or ""),
            lineage=tuple(str(x) for x in (self.lineage or ()))[-LINEAGE_MAX:],
            feel=pick(self.feel, FEELS),
            harmony=float(min(1.0, max(0.0, float(self.harmony or 0.0)))),
            intro=pick(self.intro, INTROS),
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
    # a style's own sound design, under a person's (songbird.sound.program_players): {"players": {part: {kit, patch,
    # sidechain...}}, "intro": "open" (the band's low-pass opening across an intro)}; {}: none (house, 2026-09-30)
    sound: dict = field(default_factory=dict)
    # the mixing desk as an instrument (dub, 2026-09-30; songbird.idioms "the desk"): drop-outs, throws and splashes
    # by section, the echo's time and feedback (DESK's keys); {}: the desk is left alone
    desk: dict = field(default_factory=dict)

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


# --- house and dub (2026-09-30; docs/STYLES.md, "House and dub") --------------------------------------------------
#
# Beside the ring, not on it: every machine's home is its angle divided by the ring's length, so two more styles on
# it would move every lineage. A person chooses them, or a parent hands one down; each sits beside an anchor on the
# ring, and a child of a parent in one is placed as if its parent were at the anchor: it keeps the style where it
# would stay, and steps onto the ring where the drift moves it. So a lineage can leave them, never wander in.

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

HOUSE = _def(
    "house", "house: a drum machine's four on the floor (a 909), claps on two and four, open hats on the off-beats, "
             "the ride in the drop, an off-beat synth bass, piano stabs, a pluck, a pad pumping under the kick",
    {"drummachine": 1.0, "synthbass": 0.95, "piano": 0.8, "synthpad": 0.7, "arp": 0.6},
    {"drummachine": {"intro": "floor", "verse1": "floor", "verse": ((0.55, "house"), (0.0, "floor")),
                     "refrain": "house", "drop": "drop", "turn": "floor", "break": "drop", "bridge": "house",
                     "tag": "end", "outro": "floor"},
     "synthbass": {"intro": "", "verse1": ((0.35, "offbeat"), (0.0, "")), "*": "offbeat", "drop": "rolling",
                   "tag": "long"},
     "piano": {"verse1": ((0.4, "stab"), (0.0, "")), "verse": ((0.45, "stab"), (0.0, "")), "*": "stab", "tag": "ring"},
     "synthpad": {"*": "pad"},
     "arp": {"refrain": "pluck", "drop": "pluck", "break": "pluck"}},
    ("piano", "arp"), {"straight": 1.0}, {"*": (1.22, 1.29, 1.33)},
    {"I": ("add9", "6"), "IV": ("add9", "maj7"), "V": ("sus4", "7"), "vi": ("7", "add9"), "ii": ("7",)}, 0.6,
    (0.95, 0.95),
    band={"density": 0.1, "brightness": 0.1},
    singer={"vibrato_depth": -6.0},
    mix={"space": -0.05, "width": 0.2, "plate": 0.25},
    options={"intro": {"lead": 0.6, "pad": 0.4}, "alone": 0.0, "stops": 0.0, "breakdown": 0.0, "lift": 0.15,
             "ending": {"cold": 0.35, "repeat": 0.35, "ring": 0.3}, "entrances": 0.5,
             "backing": {"echo": 0.4, "oohs": 0.3, "": 0.3}, "drop": 0.8, "half": 0.0},
    swaps={"piano": {"organ": 0.3}},  # the stabs are sometimes an organ's
    sound={"players": {"drummachine": {"kit": "909"}, "synthpad": {"sidechain": "classic"},
                       "synthbass": {"sidechain": "subtle"}, "piano": {"sidechain": "subtle"},
                       "arp": {"sidechain": "subtle"}},
           "intro": "open"},
)

DUB = _def(
    "dub", "dub and roots reggae: the kit's one drop, the skank on the off-beats, an organ's bubble, a deep round bass "
           "with space, a melodica's answers, and the mixing desk played: echoes thrown, a spring splashed, the band "
           "dropping out and back, a version after the song",
    {"kit": 0.9, "ebass": 1.05, "electric": 0.95, "organ": 0.6, "melodica": 0.75},
    {"kit": {"verse1": ((0.3, "onedrop"), (0.0, "")), "*": "onedrop", "last": "steppers", "version": "onedrop"},
     "ebass": {"*": "dubbass"},
     "electric": {"verse1": ((0.3, "skank"), (0.0, "")), "*": "skank"},
     "organ": {"verse1": "", "verse": ((0.45, "bubble"), (0.0, "")), "*": "bubble", "bridge": "pad"},
     "melodica": {"verse1": "", "verse": "fills", "refrain": ((0.6, "fills"), (0.0, "")), "last": "fills",
                  "bridge": "", "tag": "", "version": "lead"}},
    ("melodica", "organ"), {"swing": 0.65, "straight": 0.35}, {"*": (0.72, 0.78, 0.86)},
    {"vi": ("7",), "ii": ("7",), "iii": ("7",)}, 0.2, (0.55, -0.55),
    band={"wear": 0.1, "brightness": -0.08},
    singer={"vibrato_depth": -6.0, "scoop": 0.04},
    mix={"space": 0.15, "width": 0.1, "wear": 0.08, "tilt": -0.3, "plate": 0.2},
    options={"intro": {"lead": 0.6, "pad": 0.1, "count": 0.3}, "alone": 0.1, "stops": 0.0, "breakdown": 0.35,
             "lift": 0.0, "ending": {"version": 0.65, "ring": 0.2, "cold": 0.15}, "entrances": 0.3,
             "backing": {"thirds": 0.4, "echo": 0.3, "": 0.3}, "half": 0.0},
    desk=DESK,
)

STYLES.update({s.name: s for s in (HOUSE, DUB)})
OFF_RING = {"house": "synthfolk", "dub": "lofi"}  # each beside its anchor on the ring


def desk_of(params) -> dict:
    """The desk a rendition's band is dubbed with: its style's, or a version's in a style without one; {} none."""
    sdef = of(params.style)
    if sdef.desk:
        return sdef.desk
    return VERSION_DESK if params.style.ending == "version" else {}


def of(style: Style) -> StyleDef:
    """The palette's entry for a rendition's style (the seed's own, "", is the ballad)."""
    return STYLES.get(style.name or "ballad", BALLAD)


def on_ring(name: str) -> str:
    """The style's place on the ring: its own, or its anchor's for one beside it (house, dub)."""
    return OFF_RING.get(name or "ballad", name or "ballad")


def neighbours(name: str) -> tuple[str, str]:
    if name in OFF_RING:  # beside the ring: its one way onto it is its anchor
        return OFF_RING[name], OFF_RING[name]
    k = RING.index(name or "ballad")
    return RING[(k - 1) % len(RING)], RING[(k + 1) % len(RING)]


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
    """The style a child is played in: its parent's, or the neighbour its machine and the drift lean to. A parent
    beside the ring (house, dub) is placed at its anchor: the child keeps its style where it would stay, and steps
    onto the ring at the anchor where the drift moves it."""
    name = parent.name or "ballad"
    was = RING.index(on_ring(name))
    own = home(c)
    if own is None:
        return name
    base = was + PULL_STYLE * ring_delta(was, own)
    k = held_ring(drift, base, STYLE_SPAN)
    step = ring_delta(was, k)
    if abs(step) > 1:  # never more than a step from the parent's: the folk process, not a jump
        k = (was + int(np.sign(step))) % len(RING)
    if name in OFF_RING:
        return name if int(k) == was else RING[was]
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
    return feels or {"straight": 1.0}


def choose_options(genome, form, sdef: StyleDef, parent: Style, kept: bool, voices: int, material: str,
                   drift, c) -> dict:
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
        intro = pick({k: w for k, w in intros.items() if k in ("lead", "pad")} or {"lead": 1.0}, coin(material, "intro", drift))
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
    name = forced or place(parent, c, ctx.drift)
    sdef, pdef = STYLES[name], of(parent)
    kept = name == (parent.name or "ballad")
    digest = hashlib.sha256(json.dumps(ctx.parent.to_dict(), sort_keys=True).encode()).hexdigest()[:16]
    material = f"{c.hash or 'no-voice'}|{digest}|{name}"
    form = tuple(out.get("form", ctx.parent.form))
    voices = int(out.get("choir", ctx.parent.choir))
    options = choose_options(ctx.genome, form, sdef, parent, kept, voices, material, ctx.drift, c)
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
            own = gain * 2 ** (0.3 * c.id(f"gain:{inst}")) * (1 + 0.25 * c.id(f"balance:{inst}") * drift.get("balance", 0.0))
            g = was[inst] + PULL * (own - was[inst]) if inst in was else own
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
