"""A rendition as a standard MIDI file, for a musician to take into their own tools.

    songbird render ... --midi          (beside the FLAC: SONG.mid)
    the studio's "Download for musicians"

Made from the very score the rendition is rendered from (realize, then variation.lay and a style's
finish), so it is what is heard: the singer's notes with their syllables as lyric events, each
lineage voice, every band part on its own track (a General MIDI program near it; percussion on
channel 10), and a track of the chords under the tune, voiced plainly, each with its name. The first
track carries the tempo map, the time signature, the key and the sections as markers.

The notes keep their performed timing (a person's phrasing, the band's swing and small human
timing); the tempo map follows the rendition's clock (realize.timeline: its tempo, its final
ritardando, a count-in) beat by beat, so the bar lines fall where the song's do and the file lines
up with the audio. Bar 1 begins a little before the song's first sound, where the bar the first
pickup sits in begins: the stems the studio exports are padded by the same amount (lead_in), so
both start together at bar 1 in any sequencer.

Standard library only: a format 1 file, 480 ticks a quarter note.
"""

from __future__ import annotations

import struct

TPQ = 480  # ticks a quarter note
PERCUSSION_CHANNEL = 9  # MIDI channel 10

# The nearest General MIDI program for each instrument (0-based): only a starting point, for a musician to
# change; an instrument not named here takes its family's.
PROGRAMS = {
    "voice": 52, "choir": 53, "chords": 0, "chop": 54,  # a style's vocal chop (house's): synth voice
    "lute": 24, "guitar": 25, "harp": 46, "bass": 32, "fiddle": 40, "whistle": 78, "drone": 109,
    "piano": 0, "epiano": 4, "epiano-reed": 4, "organ": 19, "harmonium": 20, "accordion": 21, "concertina": 21,
    "harmonica": 22, "nylon": 24, "steel": 25, "electric": 27, "electric-crunch": 29, "electric-tremolo": 27,
    "slide": 25, "ukulele": 24, "banjo": 105, "mandolin": 25, "ebass": 33, "cello": 42, "viola": 41,
    "strings": 48, "vibes": 11, "vibraphone": 11, "marimba": 12, "glock": 9, "glockenspiel": 9, "celesta": 8,
    "musicbox": 10, "music-box": 10, "synthpad": 89, "synth-pad": 89, "synthbass": 38, "synth-bass": 38,
    "sub-bass": 38, "synthbass2": 39, "chip-bass": 38, "synthlead": 81, "synth-solo": 81, "chip": 80,
    "arp": 81, "synth-arp": 81,
}
FAMILY_PROGRAMS = {"plucked": 25, "bowed": 40, "blown": 73, "reed": 21, "keys": 0, "organ": 19, "mallets": 11,
                   "pad": 89, "bass": 32, "lead": 81, "synth": 81}
# How a drum's strokes are written for General MIDI's drum keys
DRUM_KEYS = {
    "kick": 36, "bass": 36, "stomp": 36, "cajon-bass": 36, "tom-lo": 41, "tom-mid": 45, "tom-hi": 48,
    "snare": 38, "rim": 37, "clap": 39, "cajon-slap": 38, "crash": 49, "ride": 51, "hat": 42, "hat-open": 46,
    "shaker": 70, "tambourine": 54, "brush-tap": 38, "brush-sweep": 40, "ghost": 38, "tip": 60, "mute": 61,
}


# ---------------------------------------------------------------- the file format


def vlq(n: int) -> bytes:
    """A MIDI variable-length quantity."""
    n = max(0, int(n))
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def meta(kind: int, data: bytes) -> bytes:
    return bytes([0xFF, kind]) + vlq(len(data)) + data


def text(kind: int, words: str) -> bytes:
    return meta(kind, words.encode("utf-8"))


def chunk(events: list[tuple[int, int, bytes]]) -> bytes:
    """A track chunk from (tick, order, event) triples: sorted, with delta times and its end."""
    body = bytearray()
    now = 0
    for tick, _, event in sorted(events, key=lambda e: (e[0], e[1])):
        body += vlq(tick - now) + event
        now = tick
    body += vlq(0) + meta(0x2F, b"")
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def write(tracks: list[list[tuple[int, int, bytes]]]) -> bytes:
    """A format 1 standard MIDI file of these tracks."""
    return b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), TPQ) + b"".join(chunk(t) for t in tracks)


# ---------------------------------------------------------------- reading one back (for tests and checks)


def read(data: bytes) -> dict:
    """A MIDI file's tracks as lists of (tick, event) with events as dicts: enough to check what was
    written (notes, lyrics, markers, tempo, time and key signatures, programs, names)."""
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    _, fmt, count, tpq = struct.unpack(">IHHH", data[4:14])
    pos, tracks = 14, []
    for _ in range(count):
        if data[pos:pos + 4] != b"MTrk":
            raise ValueError("a track is missing")
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body, pos = data[pos + 8:pos + 8 + length], pos + 8 + length
        i, tick, status, events = 0, 0, 0, []

        def number() -> int:
            nonlocal i
            n = 0
            while True:
                b = body[i]
                i += 1
                n = (n << 7) | (b & 0x7F)
                if not b & 0x80:
                    return n

        while i < len(body):
            tick += number()
            if body[i] & 0x80:
                status = body[i]
                i += 1
            if status == 0xFF:
                kind = body[i]
                i += 1
                size = number()
                payload = body[i:i + size]
                i += size
                events.append((tick, {"meta": kind, "data": payload}))
            elif status in (0xF0, 0xF7):
                size = number()
                i += size
            else:
                kind, channel = status & 0xF0, status & 0x0F
                width = 1 if kind in (0xC0, 0xD0) else 2
                args = tuple(body[i:i + width])
                i += width
                events.append((tick, {"status": kind, "channel": channel, "args": args}))
        tracks.append(events)
    return {"format": fmt, "tpq": tpq, "tracks": tracks}


# ---------------------------------------------------------------- reading any file, defensively (notes in)


MAX_FILE = 256 * 1024  # bytes: the export of a whole song is some 20 KB; sent as base64 in a request of 1 MiB
MAX_TRACKS = 64
MAX_EVENTS = 100_000  # across the file (the export of a whole song has some 2,500)
MAX_TICK = 2**28  # a track's last tick: far past any song at any division
MAX_TEXT = 256  # characters kept of a name, a marker, a lyric


class Unreadable(ValueError):
    """A file that isn't a MIDI file Songbird can read, and why, in plain words."""


def parse(data: bytes) -> dict:
    """Any Standard MIDI File, read defensively for bringing notes in: a file from anywhere (a sequencer, a
    stranger in a public studio) is held to its size, its track and event counts, and every length it gives
    is checked against what is there; one pass, linear in the file. Format 0 or 1, ticks a quarter note
    (SMPTE time refused). Each track: its name, its notes paired (a note-off, or a note-on at velocity 0,
    ends the earliest note still sounding on that channel and key; one never ended ends with its track),
    its texts (text, lyric, marker) and the tempo, time and key signatures. Unreadable says why."""
    if not isinstance(data, (bytes, bytearray)):
        raise Unreadable("no file was sent")
    if len(data) > MAX_FILE:
        raise Unreadable(f"it is bigger than a song's MIDI file can be ({MAX_FILE // 1024} KB)")
    if len(data) < 14 or data[:4] != b"MThd":
        raise Unreadable("it isn't a Standard MIDI File")
    size, fmt, count, division = struct.unpack(">IHHH", data[4:14])
    if size < 6 or 8 + size > len(data):
        raise Unreadable("its header is broken")
    if fmt not in (0, 1):
        raise Unreadable("it is a format 2 file (separate songs); save it as format 1")
    if division & 0x8000 or division == 0:
        raise Unreadable("it counts time in frames (SMPTE); save it counting beats")
    if count > MAX_TRACKS:
        raise Unreadable(f"it has {count} tracks; a song's file has at most {MAX_TRACKS}")
    pos, tracks, events = 8 + size, [], 0
    while pos + 8 <= len(data) and len(tracks) < count:
        kind, length = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        start, pos = pos + 8, pos + 8 + length
        if pos > len(data):
            raise Unreadable(f"track {len(tracks) + 1} is cut short")
        if kind != b"MTrk":  # a chunk of another kind: the standard says to pass over it
            continue
        track, used = _track(memoryview(data)[start:pos], len(tracks) + 1, MAX_EVENTS - events)
        events += used
        tracks.append(track)
    if len(tracks) < count:
        raise Unreadable(f"it says it has {count} tracks but holds {len(tracks)}")
    return {"format": fmt, "tpq": division, "tracks": tracks}


def _track(body: memoryview, which: int, budget: int) -> tuple[dict, int]:
    end, i, tick, status, used = len(body), 0, 0, 0, 0
    name, notes, texts, tempos, meters, keys, programs = None, [], [], [], [], [], []
    sounding: dict[tuple[int, int], list] = {}  # (channel, key) -> [(tick, velocity), ...], oldest first
    heads: dict[tuple[int, int], int] = {}  # where each list's oldest unended note is (no quadratic pops)

    def broken(why: str) -> Unreadable:
        return Unreadable(f"track {which} is broken: {why}")

    def number() -> int:
        nonlocal i
        n = 0
        for _ in range(4):
            if i >= end:
                raise broken("it ends inside a number")
            b = body[i]
            i += 1
            n = (n << 7) | (b & 0x7F)
            if not b & 0x80:
                return n
        raise broken("a number is longer than four bytes")

    def text(payload) -> str:
        return bytes(payload).decode("utf-8", "replace").replace("\x00", "")[:MAX_TEXT]

    while i < end:
        used += 1
        if used > budget:
            raise Unreadable(f"it has more than {MAX_EVENTS:,} events")
        tick += number()
        if tick > MAX_TICK:
            raise broken("it goes on far longer than a song")
        if i >= end:
            raise broken("it ends inside an event")
        if body[i] & 0x80:
            status = body[i]
            i += 1
        elif not status:
            raise broken("an event has no status")
        if status == 0xFF:
            if i >= end:
                raise broken("it ends inside an event")
            kind = body[i]
            i += 1
            size = number()
            if i + size > end:
                raise broken("an event is longer than its track")
            payload = body[i:i + size]
            i += size
            status = 0  # running status doesn't carry over a meta event
            if kind == 0x2F:
                break
            if kind == 0x03 and name is None:
                name = text(payload)
            elif kind in (0x01, 0x05, 0x06):
                texts.append((tick, kind, text(payload)))
            elif kind == 0x51 and size == 3:
                tempos.append((tick, int.from_bytes(bytes(payload), "big")))
            elif kind == 0x58 and size >= 2:
                meters.append((tick, payload[0], 2 ** min(payload[1], 6)))
            elif kind == 0x59 and size == 2:
                keys.append((tick, struct.unpack(">bB", bytes(payload))))
            continue
        if status in (0xF0, 0xF7):
            size = number()
            if i + size > end:
                raise broken("an event is longer than its track")
            i += size
            status = 0
            continue
        if status >= 0xF0:
            raise broken("it holds a message that doesn't belong in a file")
        kind, channel = status & 0xF0, status & 0x0F
        width = 1 if kind in (0xC0, 0xD0) else 2
        if i + width > end:
            raise broken("it ends inside an event")
        args = bytes(body[i:i + width])
        i += width
        if any(b & 0x80 for b in args):
            raise broken("an event's data is out of range")
        if kind == 0x90 and args[1]:
            sounding.setdefault((channel, args[0]), []).append((tick, args[1]))
        elif kind in (0x80, 0x90):
            k = (channel, args[0])
            waiting, head = sounding.get(k), heads.get(k, 0)
            if waiting and head < len(waiting):
                on, vel = waiting[head]
                heads[k] = head + 1
                notes.append((on, tick, channel, args[0], vel))
        elif kind == 0xC0:
            programs.append((tick, channel, args[0]))
    for (channel, key), waiting in sounding.items():  # a note never ended ends with its track
        for on, vel in waiting[heads.get((channel, key), 0):]:
            notes.append((on, max(tick, on), channel, key, vel))
    notes.sort()
    return ({"name": name, "notes": notes, "texts": texts, "tempos": tempos, "meters": meters, "keys": keys,
             "programs": programs, "end": tick}, used)


# ---------------------------------------------------------------- the rendition's clock, as ticks


class TickMap:
    """Seconds to ticks along a rendition's clock: points (seconds, tick) at every beat (every foot of a
    song re-barred in three), straight lines between them, the edge segments carried on beyond."""

    def __init__(self, points: list[tuple[float, int]]):
        self.points = points

    def tick(self, t: float) -> int:
        p = self.points
        if t <= p[0][0]:
            (s0, k0), (s1, k1) = p[0], p[1]
        elif t >= p[-1][0]:
            (s0, k0), (s1, k1) = p[-2], p[-1]
        else:
            lo, hi = 0, len(p) - 1
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if p[mid][0] <= t:
                    lo = mid
                else:
                    hi = mid
            (s0, k0), (s1, k1) = p[lo], p[hi]
        return max(0, int(round(k0 + (t - s0) * (k1 - k0) / max(s1 - s0, 1e-9))))

    def tempos(self) -> list[tuple[int, int]]:
        """(tick, microseconds a quarter note) where the tempo changes."""
        out: list[tuple[int, int]] = []
        for (s0, k0), (s1, k1) in zip(self.points, self.points[1:]):
            us = int(round((s1 - s0) / (k1 - k0) * TPQ * 1e6))
            if not out or abs(us - out[-1][1]) > max(1, out[-1][1] // 1000):
                out.append((k0, us))
        return out


def tick_grid(genome, params):
    """How a rendition's grid units become ticks: (the clock, the grid unit at tick 0, grid units a step, ticks
    a step, the time signature, grid units a bar). Tick 0 is a bar line at or before the first sound; a step is
    a beat (a foot of a song re-barred in three); ticks are linear in grid units, so a tick read back from a
    file is a grid position exactly (songbird.notesin)."""
    from .realize import timeline

    clock = timeline(genome, params)
    m = genome.meter
    if clock.triple:  # re-barred in three: a foot is a bar of three beats (a waltz), or half a bar of six
        step, per = m.foot, (3 * TPQ if clock.triple == "waltz" else 3 * TPQ // 2)
        signature = (3, 4) if clock.triple == "waltz" else (6, 8)
        bar = m.foot if clock.triple == "waltz" else 2 * m.foot
    else:
        step, per = m.beat, m.beat * TPQ * 4 // m.unit
        top, bottom = (int(x) for x in m.signature.split("/"))
        signature, bar = (top, bottom), m.bar
    origin = clock.lead
    while clock.seconds(origin) > 1e-9:  # back to a bar line at or before the first sound
        origin -= bar
    return clock, origin, step, per, signature, bar


def clock_map(genome, params, until: float) -> tuple[TickMap, tuple[int, int], float]:
    """The rendition's clock as ticks, its time signature, and where bar 1 begins in seconds (at or before
    zero: the stems are padded by minus this, so they start at bar 1 too)."""
    clock, origin, step, per, signature, _ = tick_grid(genome, params)
    points, u = [], origin
    while u <= clock.end or len(points) < 2:
        points.append((clock.seconds(u), (u - origin) // step * per))
        u += step
    while points[-1][0] < until:  # past the last bar line, the last tempo carries on (the last chord's ring)
        (s0, k0), (s1, k1) = points[-2], points[-1]
        points.append((s1 + (s1 - s0), k1 + per))
    return TickMap(points), signature, clock.seconds(origin)


# ---------------------------------------------------------------- a score, as tracks


def program(part: str) -> int:
    if part.startswith("choir"):
        return PROGRAMS["choir"]
    if part in PROGRAMS:
        return PROGRAMS[part]
    from .synth.instruments import spec

    try:
        return FAMILY_PROGRAMS.get(spec(part)["family"], 0)
    except ValueError:
        return 0


def percussive(part: str) -> bool:
    from .style import UNPITCHED

    if part in UNPITCHED or "drum" in part:
        return True
    if part == "voice" or part.startswith("choir"):
        return False
    from .synth.instruments import spec

    try:
        return spec(part)["register"] is None
    except ValueError:
        return False


def part_name(part: str) -> str:
    if part == "voice":
        return "Voice"
    if part.startswith("choir"):
        return f"Lineage voice {part[5:]}"
    if part == "chop":
        return "Vocal chop"
    return part.replace("-", " ").capitalize()


def key_name(tonic: int, mode: str) -> str:
    """The key as a musician says it: D major, A minor, E dorian (D♭ lydian: no key of eight sharps)."""
    from .theory import scale_names

    return f"{scale_names(tonic, mode)[0]} {({'ionian': 'major', 'aeolian': 'minor'}).get(mode, mode)}"


def key_signature(tonic: int, mode: str) -> bytes:
    """The key as MIDI has it (major or minor): a mode other than those two by its relative major's; its sharps
    or flats the ones the key is named and spelt by (theory.key_signature: C♯ major seven sharps, not D♭'s five)."""
    from .theory import key_signature as signature

    return meta(0x59, struct.pack(">bB", signature(tonic, mode), 1 if mode == "aeolian" else 0))


def section_labels(genome, form, sections, bars=None) -> list[tuple[str, float]]:
    """Each section of the form and when it starts: the score keeps a run of sections of one name as one
    (verse, verse), shared out evenly (they have the same phrases), or by their bars where a person made them
    different lengths (songbird.takeover), as the studio's previews cut them."""
    out, k = [], 0
    counts: dict[str, int] = {}
    total = {name: list(form).count(name) for name in form}
    for name, a, b in sections:
        run = 1
        while k + run < len(form) and form[k + run] == name:
            run += 1
        weights = [1.0] * run if bars is None else [float(x) for x in bars[k:k + run]]
        done = 0.0
        for j in range(run):
            counts[name] = counts.get(name, 0) + 1
            label = name.replace("bridge2", "Bridge 2").title()
            if total.get(name, 1) > 1:
                label += f" {counts[name]}"
            out.append((label, a + (b - a) * j / run if bars is None else a + (b - a) * done / sum(weights)))
            done += weights[j]
        k += run
    return out


def chord_notes(symbol: str, tonic: int, mode: str) -> list[int]:
    """A chord voiced plainly for the chord track: its bass in the octave below middle C, then its three
    tones close above middle C."""
    from .theory import chord_bass, chord_tones

    tones = chord_tones(symbol, mode)
    root = 60 + (tonic + tones[0]) % 12
    upper = sorted(root + (t - tones[0]) for t in tones)
    return [48 + (tonic + chord_bass(symbol, mode)) % 12, *upper]


def layout(score) -> list[dict]:
    """Each part of the score as the file lays it out, in its track order: the singer, the lineage voices, then
    the band as it first sounds; each with its name, its channel (0-based: percussion on 9, the chords keep 15)
    and General MIDI program (None for percussion). The studio's sketch sends its players by the same
    (songbird/studio/players.js), so a musician's instruments set up for the file answer the sketch too."""
    parts = []
    for n in score.notes:
        if n.part not in parts:
            parts.append(n.part)
    order = sorted(parts, key=lambda p: (p != "voice", not p.startswith("choir"), parts.index(p)))
    channels = [c for c in range(15) if c != PERCUSSION_CHANNEL]  # 16 is the chords'
    out, used = [], 0
    for part in order:
        drums = percussive(part)
        channel = PERCUSSION_CHANNEL if drums else channels[used % len(channels)]
        used += 0 if drums else 1
        out.append({"part": part, "name": part_name(part), "channel": channel,
                    "program": None if drums else program(part), "drums": drums})
    return out


CHORDS_CHANNEL = 15  # the Chords track's (MIDI channel 16), program PROGRAMS["chords"]


def note_key(n, drums: bool) -> int:
    """The key a note is written on: its pitch, or a drum stroke's General MIDI drum key."""
    return DRUM_KEYS.get(n.art, 38) if drums else int(round(n.pitch))


def in_beats(genome, params, score) -> list[dict]:
    """The file's parts (`layout`, the same channels, programs and keys) with their notes in beats of the song's
    grid instead of ticks: [beat, length, key, velocity 1-127], a beat as the song counts them and 0 where its
    grid starts, as the studio's composition view counts (a phrase's start_beat). The rendition's clock is read
    backwards, so the final slowing, a swing and a re-barring come back to the grid, and the band's small human
    timing stays. For the studio's sketch, which plays at the song's tempo and sends these to a musician's own
    instruments in step with its tune (songbird/studio/players.js)."""
    from bisect import bisect_left

    from .realize import timeline

    clock = timeline(genome, params)
    unit = genome.meter.beat
    lo, hi, step = -8.0 * genome.meter.bar, clock.end + 8.0 * genome.meter.bar, 0.25
    us = [lo + k * step for k in range(int((hi - lo) / step) + 1)]
    ts = [clock.seconds(u) for u in us]

    def beat(t: float) -> float:
        i = min(max(bisect_left(ts, t), 1), len(ts) - 1)
        t0, t1 = ts[i - 1], ts[i]
        return (us[i - 1] + (t - t0) * (us[i] - us[i - 1]) / max(t1 - t0, 1e-9)) / unit

    out = []
    for track in layout(score):
        notes = []
        for n in score.part(track["part"]):
            key = note_key(n, track["drums"])
            if 0 <= key <= 127:
                b0 = beat(n.start)
                notes.append([round(b0, 3), round(max(beat(n.start + n.dur) - b0, 0.01), 3), key,
                              max(1, min(127, int(round(n.vel * 127))))])
        out.append({**track, "notes": notes})
    return out


def from_score(genome, params, score, title: str | None = None) -> tuple[bytes, float]:
    """The MIDI file of a rendition's score (as rendered), and where its bar 1 begins in seconds (at or
    before zero)."""
    from . import composition, idioms, style as style_mod
    from .theory import chord_name

    ticks, (top, bottom), lead_in = clock_map(genome, params, score.duration)
    head: list[tuple[int, int, bytes]] = [
        (0, 0, text(0x03, title or genome.title)),
        (0, 1, meta(0x58, bytes([top, max(0, bottom.bit_length() - 1), 24, 8]))),
        (0, 2, key_signature(params.tonic, params.mode)),
        (0, 3, text(0x01, f"Made by Songbird: {key_name(params.tonic, params.mode)}, "
                          f"{params.tempo:g} beats a minute.")),
    ]
    head += [(tick, 4, meta(0x51, us.to_bytes(3, "big"))) for tick, us in ticks.tempos()]
    from .takeover import arranged, phrase_plan

    bars = [sum(genome.phrases[p].bars for p, _ in lines) for lines in phrase_plan(genome, params)]         if arranged(params) else None  # sections a person made other lengths (songbird.takeover)
    for label, start in section_labels(genome, params.form, score.sections, bars):
        head.append((ticks.tick(start), 5, text(0x06, label)))
    tracks = [head]

    for track in layout(score):
        part, channel, drums = track["part"], track["channel"], track["drums"]
        events: list[tuple[int, int, bytes]] = [(0, 0, text(0x03, track["name"]))]
        if not drums:
            events.append((0, 1, bytes([0xC0 | channel, track["program"]])))
        syllable = 0
        for n in score.part(part):
            on, off = ticks.tick(n.start), ticks.tick(n.start + n.dur)
            key = note_key(n, drums)
            if not 0 <= key <= 127:
                continue
            vel = max(1, min(127, int(round(n.vel * 127))))
            if part == "voice" and n.syllable:
                word_len = max(1, int(n.word_len or 1))
                syllable = syllable + 1 if 0 < syllable < word_len else 1
                shown = str(n.syllable).replace("*", "")
                events.append((on, 2, text(0x05, shown + ("-" if syllable < word_len else " "))))
                if syllable >= word_len:
                    syllable = 0
            # a person's melisma: each of its notes a note of its own (the syllable's lyric on the first), at its
            # moment on the grid
            turns = [(t, s) for t, s in getattr(n, "melisma", ()) if t < n.dur - 1e-6] if part == "voice" else []
            starts = [on] + [ticks.tick(n.start + t) for t, _ in turns]
            keys = [key] + [max(0, min(127, key + int(round(s)))) for _, s in turns]
            ends = starts[1:] + [off]
            for a, z, k in zip(starts, ends, keys):
                events.append((a, 4, bytes([0x90 | channel, k, vel])))
                events.append((max(z, a + 1), 3, bytes([0x80 | channel, k, 0])))
        tracks.append(events)

    # the chords under the tune (a person's own harmony among them), each named where it starts
    harmony = composition.harmonized(genome, params)
    lift = style_mod.lifted(genome, score) if params.style.lift else None
    events = [(0, 0, text(0x03, "Chords")), (0, 1, bytes([0xC0 | CHORDS_CHANNEL, PROGRAMS["chords"]]))]
    for a, z, symbol in style_mod.held_chords(idioms.chord_times(harmony, params), params):
        up = 2 if lift is not None and a >= lift - 1e-6 else 0
        on, off = ticks.tick(a), ticks.tick(z)
        events.append((on, 2, text(0x01, chord_name(symbol, params.tonic + up, params.mode))))
        for key in chord_notes(symbol, params.tonic + up, params.mode):
            events.append((on, 4, bytes([0x90 | CHORDS_CHANNEL, key, 64])))
            events.append((max(off, on + 1), 3, bytes([0x80 | CHORDS_CHANNEL, key, 0])))
    if lift is not None:
        head.append((ticks.tick(lift), 2, key_signature(params.tonic + 2, params.mode)))
    tracks.append(events)
    return write(tracks), lead_in
