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

from dataclasses import asdict, dataclass, fields

FEELS = ("straight", "swing", "shuffle", "twelve", "half", "double", "waltz", "jig")
INTROS = ("lead", "pad", "count", "voice")
ENDINGS = ("ring", "rit", "cold", "fade", "amen", "repeat")
BACKINGS = ("oohs", "echo", "thirds", "gang")
LINEAGE_MAX = 16  # generations of styles a record remembers


@dataclass(frozen=True)
class Style:
    """How a rendition is dressed. Every option has an off value ("" or 0 or False), which is the
    seed's; out-of-range values are dropped to off, unknown names ignored.

    name        the style (STYLES); "" the seed's own arrangement, byte for byte
    lineage     the styles this rendition's line was sung in, one a generation, oldest first, this one last
    feel        straight, swing, shuffle (a triplet lilt with a shuffle's groove), twelve (12/8), half
                (half-time), double (double-time), waltz or jig (the song re-barred in three, where it can
                be); "" the style's own
    harmony     0..1, how much of the style's harmony vocabulary colours the chords (sevenths, sixths, added
                ninths, suspensions, a plagal amen...), always voiced around the sung tune
    intro       lead (an instrument states the tune), pad (a pad swells in alone), count (a count-in on
                sticks), voice (the singer starts alone and the band comes in on the second line); "" as
                the form has it
    alone       which verse (1 the first) is sung with little: a cappella, or with one instrument; 0 none
    alone_with  the one instrument playing under it; "" a cappella
    stops       which verse is played in stop-time (the band hits the downbeats and leaves the words bare); 0 none
    breakdown   the last refrain starts stripped to the rhythm and the band comes back at its third line
    bridge      "half": the bridge in half-time; "" as the style plays it
    lift        the last refrain a whole step up
    ending      ring (the last chord rings), rit (a broad ritardando), cold (a dead stop), fade, amen (a
                plagal IV-I with the backing voices' amen), repeat (the last line sung again); "" ring
    entrances   the first verse builds, instruments joining line by line
    backing     what the backing voices sing: oohs (chord tones), echo (answers at the ends of lines),
                thirds (harmony above and below), gang (everyone on the tune); "" none
    voices      how many backing voices sing it (the lineage's own, and stand-ins where a style wants a group)
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

    @classmethod
    def from_dict(cls, data: dict | None) -> Style:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**values).clamped()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["lineage"] = list(self.lineage)
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
        )

    @property
    def seed(self) -> bool:
        """Whether this is the seed's own arrangement (no style, no options)."""
        return self == Style()
