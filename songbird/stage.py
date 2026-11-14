"""A stage edition: the song as a stage mix plays it, from its record (docs/ARRANGE.md, "A stage edition").

A record says it in two layers.

The grid, in a person's arrangement (params.composition["arrange"], songbird.takeover), handed down to a child
as the arrangement is:

    arrange.<section>:<n>.human            how much of people is in the lead there (amounts()), 0 to 1: one
                                           amount for the section, or a list of them, one a line
    arrange.<section>:<n>.<player>.synth   "all": the player's synth twin (TWINS) plays the player's own notes in
                                           its place; "until:<line>": the twin until that line (0 the first),
                                           then the player itself; "under": the twin under the player, UNDER dB

The edition's own exact data, params.composition["exact"], which the renderer honors and no child inherits
(composition.handed_down drops it):

    {"human": {"verse:0": [0, 0, 0, 0.2]},                   amounts finer than the grid's, by section (optional)
     "twins": {"harp~": ["harp", "arp"], "harp#": ["harp", "chip"]},
                                                             a synth (any instrument) on a player's own notes,
                                                             level with the player (whole-stem RMS), by its name
     "layers": [{"style": "synthfolk", "parts": ["arp", "synthpad"],
                 "copy": [{"part": "synthpad", "to": "verse:0", "from": "verse:1"}]}],
                                                             another style's players on the same song (its key,
                                                             tempo, form and chords: layered()), a section of a
                                                             part played as it plays another
     "levels": {"harp~": [["verse:0.3", -3], ["refrain:0", null]], ...},
                                                             each named part's level along the song: points
                                                             (where, dB or null for silent) joined by straight
                                                             fades, the first and last held (curve())
     "release": 0.35}                                        s over which the lead and each choir voice let go
                                                             of their last note (released())

A place is "<section>:<n>" (its start), "<section>:<n>.<line>" (where its line begins, 0 the first: a line is
the lead's, from just before its first note, its pickup with it) or "<section>:<n>.end". "twins" and "levels",
where the exact data gives them, are the edition's whole table and every level: what the grid's synth cells
would make of them is left aside. With neither layer, nothing here is called and every render is the program's
own, to the sample.

The lead with an amount of people is sung whole at each amount the song names (its phrasing's gestures and the
singer's own liveliness scaled, the people's share of its timbre set) and the takes joined where its lines
begin (arc_plan, spliced). A section with no amount keeps the one before it (before any, the least named).
prepare() lays all of it out from the score (Score.stage); jobs() makes the stems from that (synth.stem_jobs).
"""

from __future__ import annotations

import threading
from dataclasses import replace

import numpy as np

# What of the singer is its own liveliness (VoiceParams): scaled with the phrasing below human 0.5
LIVELY = ("vibrato_depth", "jitter", "wander", "shimmer", "scoop", "overshoot", "dynamics")
SHARE_MOST = 0.6  # the people's share of the timbre at human 1 (throat.HUMAN_SHARE: the artist allows 0.3-0.6)
# Which synth twins which player (arrange.<section>:<n>.<player>.synth): it plays the player's own notes
TWINS = {"harp": "arp", "bass": "synthbass", "guitar": "arp", "drum": "drummachine", "whistle": "synthlead",
         "fiddle": "synthlead"}
UNDER = -7.0  # dB a twin plays under its player ("under")
EDGE = 0.12  # s a level takes to change where two points fall at one place
PICKUP = 0.6  # s before a section's first downbeat a line of it may begin
SPLICE = 0.03  # s one take of the lead fades into the next


def exact(params) -> dict:
    """The edition's exact data (params.composition["exact"]), {} for none."""
    return (getattr(params, "composition", None) or {}).get("exact") or {}


def wanted(params) -> bool:
    """Whether these parameters ask for a stage edition: the grid's stage fields or exact data."""
    from .takeover import staged

    return bool(staged(params) or exact(params))


def amounts(human: float) -> tuple[float, float]:
    """One knob, 0 to 1, for how much of people is in the lead: (how far the sung phrasing and the singer's own
    liveliness are applied, the people's share of the timbre). 0: the machine alone, every note on the grid and
    level, no people in its timbre. 0.5: the performance voice as it is (the phrasing whole, a share of 0.3).
    1: the most people the timbre may hold, the phrasing as sung."""
    return min(2 * human, 1.0), SHARE_MOST * human


def phrased(phrasing, k: float):
    """A phrasing with every gesture k of the way from none to as sung (past 1: larger than sung, within its bounds)."""
    from . import phrasing as phrasing_mod

    def one(g):
        return phrasing_mod.reduce(phrasing_mod.Gesture(
            early=g.early * k, hold=1.0 - (1.0 - g.hold) * min(k, 1.0), level=g.level * k, swell=g.swell * k,
            scoop=g.scoop * k, bend=g.bend * k, fall=g.fall * k, vibrato=g.vibrato * k if g.vibrato >= 0 else -1.0,
            tune=g.tune * k))
    return {pid: tuple(one(g) for g in row) for pid, row in phrasing.items()}


# ---------------------------------------------------------------- where things fall


def sections(score, form) -> dict[str, tuple[float, float]]:
    """The score's sections by the arrangement's ids (verse:0, verse:1...): (start, end) in seconds."""
    from .composition import section_ids

    ids = section_ids(form)
    if len(ids) != len(score.sections) or any(sid.split(":")[0] != s[0] for sid, s in zip(ids, score.sections)):
        raise ValueError("the score's sections aren't the form's")
    return {sid: (float(a), float(b)) for sid, (_, a, b) in zip(ids, score.sections)}


def line_starts(score) -> list[float]:
    """Where each sung line of the lead begins: just before its first note (a pickup goes with its line)."""
    starts, new = [], True
    for n in sorted(score.part("voice"), key=lambda n: n.start):
        if new:
            starts.append(n.start - SPLICE)
        new = bool(n.line_end)
    return starts


def lines_of(lines: list[float], a: float, b: float) -> list[float]:
    """The lines that begin in a section from a to b (a pickup up to PICKUP before its first downbeat)."""
    return [t for t in lines if a - PICKUP <= t < b - PICKUP]


def when(place: str, secs: dict, lines: list[float]) -> float:
    """A place in seconds: "<section>:<n>", "<section>:<n>.<line>" or "<section>:<n>.end". A line past the
    section's own is its end."""
    sid, _, rest = place.partition(".")
    a, b = secs[sid]
    if rest == "end":
        return b
    if rest:
        mine = lines_of(lines, a, b)
        return mine[int(rest)] if int(rest) < len(mine) else b
    return a


def points(levels: list, secs: dict, lines: list[float]) -> tuple[list[float], list[float]]:
    """A part's levels (where, dB or None for silent) as times and gains, for curve(): a point that falls on
    the one before it comes EDGE after it. A place in a section the version hasn't got is left out."""
    ts, gs = [], []
    for place, db in levels:
        if place.partition(".")[0] not in secs:
            continue
        t = when(place, secs, lines)
        ts.append(t if not ts or t > ts[-1] else ts[-1] + EDGE)
        gs.append(0.0 if db is None else 10 ** (db / 20))
    return ts, gs


def curve(ts: list[float], gs: list[float], length: int, sr: int) -> np.ndarray:
    """A gain per sample from points joined by straight fades, the first and last held."""
    return np.interp(np.arange(length) / sr, ts, gs)


def arc_plan(arc: dict, secs: dict, starts: dict) -> list[tuple[float, float]]:
    """Which take of the lead is heard from where: (from this time, this amount), in order. Each line is sung at
    its section's amount, or its own where the section has a list; a take comes in at its own beginning of the
    line it takes up. arc: {section id: amount or [one a line]}; starts: each take's line_starts."""
    levels = sorted({h for v in arc.values() for h in (v if isinstance(v, list) else [v])})
    order = sorted(secs.items(), key=lambda kv: kv[1][0])
    plan, nth = [], {}
    for j, t in enumerate(starts[levels[0]]):
        # the section a line belongs to: the one its first downbeat falls in (a pickup starts just before it)
        name = next((n for n, (a, b) in order if a - PICKUP <= t < b - PICKUP), order[-1][0])
        k = nth[name] = nth.get(name, -1) + 1
        h = arc.get(name, plan[-1][1] if plan else levels[0])
        if isinstance(h, list):
            h = h[min(k, len(h) - 1)]
        if not plan or plan[-1][1] != h:
            plan.append((starts[h][j], h))
    return plan


def grid_levels(grid: dict, ids: list[str]) -> tuple[dict, dict]:
    """The twins and levels the grid's synth cells make: (twins {name: (player, synth)}, levels {name: points}).
    A player with a cell has its twin "<player>~" (TWINS); the twin is silent and the player itself where a
    section has no cell; a change at a section's start or a line comes in over EDGE."""
    players = sorted({p for entry in grid.values() for p, cell in (entry.get("players") or {}).items()
                      if cell.get("synth")})
    twins, levels = {}, {}

    def step(row: list, place: str, db) -> None:
        if not row:
            row.append([place, db])
        elif row[-1][1] != db:
            row.append([place, row[-1][1]])
            row.append([place, db])

    for player in players:
        twin, own = [], []
        for sid in ids:
            way = ((grid.get(sid) or {}).get("players") or {}).get(player, {}).get("synth")
            if way is None:
                step(twin, sid, None), step(own, sid, 0.0)
            elif way == "all":
                step(twin, sid, 0.0), step(own, sid, None)
            elif way == "under":
                step(twin, sid, UNDER), step(own, sid, 0.0)
            else:  # until:<line>
                line = f"{sid}.{int(way.split(':')[1])}"
                step(twin, sid, 0.0), step(own, sid, None)
                step(twin, line, None), step(own, line, 0.0)
        if any(db is not None for _, db in twin):
            twins[f"{player}~"] = (player, TWINS[player])
            levels[f"{player}~"] = twin
        if any(db != 0.0 for _, db in own):
            levels[player] = own
    return twins, levels


def layered(genome, params, style: str, phrasing=None, choir=(), lyrics=None):
    """The song as another style's band would play it: the same key, tempo, form and chords. (params, score)."""
    from . import variation
    from .realize import choose_params, realize

    q = choose_params(genome, params, None, None, seed=params.seed, style=style)
    plain = replace(q.style, feel="straight", ending=params.style.ending, intro=params.style.intro, coda="",
                    harmony=0.0, alone=0, alone_with="", stops=0, breakdown=False, lift=False, drop=0, loop="",
                    dissolve=0, bridge="", backing="", voices=0)
    p2 = replace(params, band=q.band, style=plain)
    return p2, variation.lay(realize(genome, p2, phrasing=phrasing, choir=list(choir), lyrics=lyrics), p2)


# ---------------------------------------------------------------- the plan


def prepare(genome, params, score, phrasing=None, choir=(), lyrics=None):
    """The score with its stage plan (Score.stage), when the parameters ask for a stage edition (wanted());
    the same score otherwise. phrasing, choir, lyrics: as the score was realized with them."""
    from . import variation
    from .composition import section_ids
    from .realize import realize
    from .takeover import staged

    grid, ex = staged(params), exact(params)
    if not grid and not ex:
        return score
    ids = section_ids(params.form)
    secs = sections(score, params.form)
    lines = line_starts(score)
    plan: dict = {}

    arc = {sid: entry["human"] for sid, entry in grid.items() if "human" in entry}
    arc.update(ex.get("human") or {})
    arc = {sid: h for sid, h in arc.items() if sid in secs}
    if arc and score.part("voice"):
        takes, starts = {}, {}
        for h in sorted({h for v in arc.values() for h in (v if isinstance(v, list) else [v])}):
            k, share = amounts(h)
            take = variation.lay(realize(genome, params, phrasing=phrased(phrasing, k) if phrasing else phrasing,
                                         choir=list(choir), lyrics=lyrics), params)
            takes[h] = {"notes": take.part("voice"), "lexicon": take.lexicon, "k": k, "share": share}
            starts[h] = line_starts(take)
        plan["takes"], plan["plan"] = takes, arc_plan(arc, secs, starts)

    twins, levels = grid_levels(grid, ids)
    if "twins" in ex:
        twins = {name: tuple(pair) for name, pair in ex["twins"].items()}
    if "levels" in ex:
        levels = ex["levels"]
    if twins:
        plan["twins"] = twins
    if levels:
        plan["levels"] = {name: points(row, secs, lines) for name, row in levels.items()}
        plan["levels"] = {name: tg for name, tg in plan["levels"].items() if tg[0]}

    layers = []
    for layer in ex.get("layers") or []:
        p2, s2 = layered(genome, params, layer["style"], phrasing, choir, lyrics)
        copies = [(c["part"], secs[c["to"]], secs[c["from"]][0]) for c in layer.get("copy") or []
                  if c["to"] in secs and c["from"] in secs]
        layers.append({"score": s2, "seed": p2.seed, "parts": tuple(layer["parts"]), "copies": copies})
    if layers:
        plan["layers"] = layers
    if ex.get("release"):
        plan["release"] = float(ex["release"])
    return replace(score, stage=plan) if plan else score


def touched(score) -> set[str]:
    """The stems a stage plan makes or changes: none of them is the program's own stem of that name (a stem
    cache keeps none of them under its own key: synth.render)."""
    plan = getattr(score, "stage", None) or {}
    out = set(plan.get("levels") or {}) | set(plan.get("twins") or {})
    out |= {part for part, _ in (plan.get("twins") or {}).values()}
    out |= {name for layer in plan.get("layers") or [] for name in layer["parts"]}
    if plan.get("takes") or plan.get("release"):
        out.add("voice")
    if plan.get("release"):
        out |= {n.part for n in score.notes if n.part.startswith("choir")}
    return out


# ---------------------------------------------------------------- the sound


def fit(y: np.ndarray, length: int) -> np.ndarray:
    return np.pad(y, (0, max(0, length - len(y))))[:length]


def spliced(takes: dict, plan: list[tuple[float, object]], sr: int, fade: float = SPLICE) -> np.ndarray:
    """One lead from several takes of it: plan is (from this time, this take), in order."""
    length = len(next(iter(takes.values())))
    out = np.zeros(length)
    f = int(fade * sr)
    for k, (t, key) in enumerate(plan):
        i0 = max(0, int(t * sr)) if k else 0
        i1 = int(plan[k + 1][0] * sr) if k + 1 < len(plan) else length
        w = np.zeros(length)
        w[i0:i1] = 1.0
        if k:
            w[i0: i0 + f] = np.linspace(0.0, 1.0, f)
        if k + 1 < len(plan):  # it fades as the next comes in
            w[i1: i1 + f] = np.linspace(1.0, 0.0, f)
        out += takes[key] * w
    return out


def released(y: np.ndarray, over: float, sr: int) -> np.ndarray:
    """A sung stem with its last note let go softly: its last `over` seconds of sound faded (a held note
    otherwise stops while it still sounds). In place."""
    loud = np.flatnonzero(np.abs(y).reshape(len(y), -1).max(axis=1) > 1e-4)
    if len(loud):
        end = loud[-1] + 1
        n = min(int(over * sr), end)
        fade = 0.5 + 0.5 * np.cos(np.linspace(0.0, np.pi, n))
        y[end - n: end] = (y[end - n: end].T * fade).T
    return y


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)))


class _Played:
    """A player's own stem, made once for the player and its twins: the twins read its level (rms), the player
    takes the stem itself."""

    def __init__(self, make):
        self.make, self.lock, self.y, self.level = make, threading.Lock(), None, None

    def _made(self) -> None:
        if self.level is None:
            self.y = self.make()
            self.level = rms(self.y)

    def rms(self) -> float:
        with self.lock:
            self._made()
            return self.level

    def take(self) -> np.ndarray:
        with self.lock:
            self._made()
            y, self.y = self.y, None
            return y


def sung(notes, sr: int, singer, seed: int, lexicon, share: float) -> np.ndarray:
    """A take of the lead, mono: through the learned throat with the people's share of its timbre at `share`
    (where the throat is here), else by the singer's own engine."""
    from .synth import throat, voice as voice_mod

    if singer.engine == "learned" and throat.available():
        return throat.sing(list(notes), sr, singer, seed, lexicon, mix=singer.timbre, share=share)
    return voice_mod.sing(list(notes), sr, singer, seed, lexicon)


def jobs(score, sr: int, seed: int, voice, jobs: list) -> list:
    """The stems' makers (synth.stem_jobs') as the score's stage plan has them: the lead joined from its takes,
    the twins and the layered parts added, each named part at its levels along the song, the singers' last
    notes let go."""
    from .synth import VOICE_GAIN, pan
    from .synth.instruments import band_parts, render_part
    from .synth.voice import VoiceParams

    plan = score.stage
    length = int(np.ceil(score.duration * sr))
    voice = voice or VoiceParams()
    makes = dict(jobs)
    order = [name for name, _ in jobs]
    release = plan.get("release")
    twins = {name: pair for name, pair in (plan.get("twins") or {}).items() if pair[0] in makes}
    played = {part: _Played(makes[part]) for part, _ in twins.values()}
    for part, shared in played.items():
        makes[part] = shared.take

    if plan.get("takes"):
        takes = plan["takes"]

        def lead() -> np.ndarray:
            sung_takes = {}
            for h, take in takes.items():
                singer = replace(voice, **{f: getattr(voice, f) * min(take["k"], 1.0) for f in LIVELY})
                y = sung(take["notes"], sr, singer, seed, take["lexicon"], take["share"])
                sung_takes[h] = fit(y, length) * VOICE_GAIN
            y = spliced(sung_takes, plan["plan"], sr)
            del sung_takes
            if release:
                y = released(y, release, sr)
            return pan(y, 0.0)
        makes["voice"] = lead
    elif release and "voice" in makes:
        makes["voice"] = lambda make=makes["voice"]: released(make(), release, sr)
    if release:
        for name in order:
            if name.startswith("choir"):
                makes[name] = lambda make=makes[name]: released(make(), release, sr)

    for name, (part, synth_name) in twins.items():
        def twin(part=part, synth_name=synth_name) -> np.ndarray:
            y = render_part(synth_name, score.part(part), sr, length, score.band, seed, None)
            return y * (played[part].rms() / max(rms(y), 1e-9))  # level with the player whose part it plays
        makes[name] = twin
        if name not in order:
            order.append(name)

    for layer in plan.get("layers") or []:
        theirs = dict(band_parts(layer["score"], sr, layer["seed"]))
        for name in layer["parts"]:
            if name not in theirs:
                continue
            copies = [(span, start) for part, span, start in layer["copies"] if part == name]

            def theirs_here(make=theirs[name], copies=copies) -> np.ndarray:
                y = make()
                for (a1, b1), a2 in copies:  # a section played as the part plays another (the same bars, chords)
                    i1, i2, n = int(a1 * sr), int(a2 * sr), int((b1 - a1) * sr)
                    y[i1: i1 + n] = y[i2: i2 + n]
                return y
            makes[name] = theirs_here
            if name not in order:
                order.append(name)

    for name, (ts, gs) in (plan.get("levels") or {}).items():
        if name in makes:
            makes[name] = lambda make=makes[name], ts=ts, gs=gs: make() * curve(ts, gs, length, sr)[:, None]
    return [(name, makes[name]) for name in order]
