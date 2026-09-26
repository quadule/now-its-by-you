"""Evolution: a lineage's tune and words, changed a little at a time (docs/EVOLUTION.md).

Two decisions for variation.DECISIONS, both the same shape as every other choice there: a child starts
from its parent's and leans toward its own machine's.

- choose_variants, the tune (songbird.variants): a child keeps its parent's variants; now and then it
  forgets one, and now and then it learns one of its machine's own, more often for a machine that
  ornaments (a rich vocabulary, an ornate habit) and in a season the drift makes free with the tune.
  Variants that last become the lineage's settled way and are forgotten more slowly.
- choose_words, the words the lineage holds (arrange.hold): a child keeps its parent's verses, couplets
  and slot words; now and then one is swapped for one its machine likes; a longer form takes in a verse
  of the machine's choosing, a shorter one leaves the last out; the seed's own refrain (the canon couplet
  every time round) takes other couplets before the last, as the bank's rules ask of drawn words.

Neither reads the instant a render starts. Every chance is read from a clock (drift.epoch): stretches of
weeks or months of its own for each machine and each thing that can change, so a choice holds through a
stretch and changes as the next begins, never overnight and never on a calendar edge, and one thing at a
time. A child sung on the machine that made its parent changes only what a clock has turned on since then
(a machine singing its own last rendition the next day sings it the same); a child sung on another machine
takes its one turn at everything, so a lineage changes about once a hand-off. The rates below are for the
artist to tune by ear.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

import numpy as np

from . import arrange
from . import variants as V
from .drift import chance, epoch, series

if TYPE_CHECKING:
    from .variation import Context

# ---------------------------------------------------------------- rates (for the artist to tune by ear)

# The tune. A machine's appetite for variants is 0..1, 0.5 typical: more for a rich vocabulary and an ornate
# habit, and moved by the slow "tune" drift.
LEARN = (0.25, 0.5)  # chance of learning a variant when a learning clock turns: base + this x appetite
LEARN_AGAIN = 0.6  # a second learning clock, for ornamenting machines only: this x (appetite - 0.5)
FORGET = (0.03, 0.04)  # chance of forgetting a variant when its clock turns: base + this x (1 - appetite)
SETTLED = 3  # a variant this many generations old is the lineage's own and is forgotten half as often
CROWDED = 0.3  # and more often as its sections fill: this x (fullness - 0.6), fullness 1 at SHARE
LEARN_DAYS = (60, 150)  # how long each learning clock's stretches run
FORGET_DAYS = (90, 220)  # and each variant's forgetting clock
# How much the machine likes each kind, before its character (a plain singer moves notes, an ornate one
# decorates them), and where: verses are where a folk tune wanders, a refrain is what everyone knows.
KIND_WEIGHTS = {"grace": 1.0, "mordent": 0.5, "turn": 0.35, "neighbour": 0.5, "passing": 0.7,
                "anticipation": 0.5, "leap": 0.6, "dotted": 0.4, "even": 0.4}
LONE = 3.0  # no single candidate weighs more than this many grace notes (a kind offered once isn't a habit)
PLACES = {"verse": 1.3, "bridge": 1.0, "refrain": 0.7}
STRESSED, QUAVER = 1.5, 0.5  # a grace, mordent or turn likes a stressed note, and not a passing quaver

# The words.
SWAP = (0.3, 0.2, 0.2)  # chance of a swap when the swap clock turns: base + habit x this + slow drift x this
SWAP_BOUNDS = (0.1, 0.6)
SWAP_DAYS = (40, 110)
# Where a swap falls, by weight: a verse most often, then a slot word, a couplet, the refrain's and the
# bridge's slot words, the tag's syllable and the bridge's extra stanza.
SWAPS = {"verse": 0.45, "slot": 0.25, "couplet": 0.15, "refrain": 0.07, "bridge": 0.05, "tag": 0.02, "extra": 0.01}


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


_MEMO: dict = {}


def _memo(key, make, owner=None):
    """Remember what holds for a whole clock stretch (a machine's ranking of every variant, say): a year of
    daily renders asks the same things again and again. owner: the genome it was worked out for, which
    must be the very same object (an id can be reused once an object is gone)."""
    hit = _MEMO.get(key)
    if hit is None or hit[0] is not owner:
        if len(_MEMO) > 4096:
            _MEMO.clear()
        hit = _MEMO[key] = (owner, make())
    return hit[1]


def _ranked(parts: tuple, items: list, weights=None, names=None) -> list:
    """Items in a weighted random order fixed by `parts`: the heavier, the likelier to come early. Each
    item's place comes from its own name, so adding or removing an option never reorders the others."""
    if not items:
        return []
    weights = [1.0] * len(items) if weights is None else weights
    names = [str(i) for i in items] if names is None else names
    keys = [np.log(max(chance("rank", *parts, name), 1e-300)) / max(float(w), 1e-12) for name, w in zip(names, weights)]
    return [items[i] for i in sorted(range(len(items)), key=lambda i: (-keys[i], names[i]))]


class Clocks:
    """A machine's clocks (drift.epoch), and whether each has turned since the parent was made: always,
    for a parent made on another machine or never made (the seed)."""

    def __init__(self, ctx: Context):
        self.hash = ctx.drift.hash if ctx.drift is not None and ctx.drift.hash else (ctx.c.hash or "timeless")
        self.t = ctx.drift.t if ctx.drift is not None else 0.0
        made = getattr(ctx.parent, "made", None) or {}
        self.then = made.get("at") if made.get("by") == self.hash[:12] else None

    def at(self, name: str, days: tuple[float, float]) -> tuple[bool, int, float]:
        """(turned since the parent was made, this stretch's index, the day it began)."""
        k, start = epoch(self.t, self.hash, name, *days)
        if self.then is None:
            return True, k, start
        return epoch(self.then, self.hash, name, *days)[0] != k, k, start

    def coin(self, name: str, k: int) -> float:
        return chance(self.hash, name, k)


def slow(ctx: Context, dimension: str, t: float) -> float:
    """The slow view of a drift dimension for this machine at a day (a clock's stretch's start)."""
    if ctx.drift is None or not ctx.drift.hash:
        return 0.0
    h = ctx.drift.hash
    return _memo(("slow", h, dimension, t), lambda: float(series([t], h, [dimension])[dimension]["slow"][0]))


def _log(ctx: Context, entry) -> None:
    """Add to the rendition's record of what changed, if one is being kept; entry: a dict, or a function
    making one (so nothing is described for a render that keeps no record)."""
    log = getattr(ctx, "log", None)
    if log is not None:
        log.append(entry() if callable(entry) else entry)


# ---------------------------------------------------------------- the tune


def appetite(ctx: Context, t: float) -> float:
    """How freely this machine takes the tune at a day, 0..1 (0.5 typical)."""
    c = ctx.c
    rich = c.richness if "richness" in c.known else 0.0
    return clip(0.5 + 0.25 * rich + 0.2 * c.id("ornate") + 0.25 * slow(ctx, "tune", t))


def kind_weights(c) -> dict[str, float]:
    """How much a machine's character likes each kind of variant."""
    rich = c.richness if "richness" in c.known else 0.0
    ornate = max(0.2, 1.0 + 0.6 * rich + 0.4 * c.id("ornate"))
    w = {k: v * ornate if k in ("grace", "mordent", "turn", "neighbour", "passing") else v
         for k, v in KIND_WEIGHTS.items()}
    w["anticipation"] *= max(0.2, 1.0 + 0.6 * c.lay)  # a singer ahead of the beat gets there early
    w["leap"] *= max(0.2, 1.0 + 0.5 * c.id("leap"))
    for k in ("dotted", "even"):
        w[k] *= max(0.2, 1.0 + 0.6 * c.swing)
    return w


def _place(genome, pid: str) -> float:
    blocks = {s.lyrics for s in genome.sections.values() if pid in s.phrases and s.lyrics}
    return max((PLACES.get(b, PLACES["refrain"] if b != "verse" else 1.0) for b in blocks), default=1.0)


def _emphasis(genome, v: V.Variant) -> float:
    """An ornament at a note's start sits better on a stressed or a longer note than on a passing quaver."""
    if v.kind not in V.HEAD:
        return 1.0
    n = genome.phrases[v.phrase].sung[v.note]
    return STRESSED if n.onset % genome.meter.foot == 0 else QUAVER if n.dur <= 1 else 1.0


def own_variant(ctx: Context, name: str, k: int, current) -> V.Variant | None:
    """The machine's pick of a variant this stretch of a learning clock: the first, in its own weighted
    order of everything the tune allows, that the lineage's variants have room for. A kind's weight is
    shared among its candidates, but no one candidate weighs more than LONE times a grace note does, so a
    kind the tune offers once (H's one dotted pair) can't become every lineage's habit."""
    genome = ctx.genome
    hash_ = Clocks(ctx).hash

    def ranking():
        offered = list(V.candidates(genome))
        likes = kind_weights(ctx.c)
        count = {kind: sum(v.kind == kind for v in offered) for kind in likes}
        each = {kind: likes[kind] / max(count[kind], 1) for kind in likes}
        cap = LONE * each["grace"] if count.get("grace") else max(each.values())
        weights = [min(each[v.kind], cap) * _place(genome, v.phrase) * _emphasis(genome, v) for v in offered]
        return _ranked((hash_, name, k), offered, weights, [repr(v.what) for v in offered])

    for v in _memo(("own", id(genome), hash_, name, k), ranking, genome):
        if V.fits(genome, current, v):
            return v
    return None


def _fullness(genome, variants, v) -> float:
    """How full the fullest section the variant is sung in is (1: at SHARE)."""
    cap, used = V.room(genome), V.load_of(genome, variants)
    names = [n for n, s in genome.sections.items() if v.phrase in s.phrases and n in cap]
    return max((used.get(n, 0) / max(cap[n], 1) for n in names), default=0.0)


def choose_variants(out: dict, ctx: Context) -> None:
    """The lineage's variants: the parent's, less any it forgets, plus any its machine teaches it. (After
    choose_words, so a change is described with the words this rendition sings.)"""
    genome = ctx.genome
    parent = ctx.parent
    generation = int(out.get("generation", 0))
    sung: list = []  # the words this rendition sings, worked out only if a change needs describing

    def about(v: V.Variant) -> str:
        if not sung:
            words = out.get("words")
            ok = words and genome.source.get("bank") and not arrange.held_problem(genome, out["form"], words)
            sung.append(arrange.sing(genome, out["form"], words) if ok else None)
        return V.describe(genome, v, sung[0])

    kept: list[V.Variant] = []
    for v in V.parse(getattr(parent, "variants", ())):
        why = V.problems(genome, kept + [v])
        if why:
            _log(ctx, lambda v=v: {"what": "tune", "change": "dropped", "variant": v.to_dict(), "about": about(v),
                       "why": f"it no longer fits: {why[0]}"})
            continue
        kept.append(v)
    if ctx.drift is None:  # no time, nothing moves
        out["variants"] = [v.to_dict() for v in kept]
        return
    clocks = Clocks(ctx)
    now: list[V.Variant] = []
    for v in kept:
        name = f"forget:{v.phrase}:{v.note}"
        turned, k, start = clocks.at(name, FORGET_DAYS)
        if turned:
            a = appetite(ctx, start)
            p = FORGET[0] + FORGET[1] * (1.0 - a)
            if generation - v.born >= SETTLED:
                p *= 0.5
            p += CROWDED * max(0.0, _fullness(genome, kept, v) - 0.6)
            if clocks.coin(name, k) < p:
                _log(ctx, lambda v=v: {"what": "tune", "change": "forgot", "variant": v.to_dict(), "about": about(v),
                           "why": f"forgotten ({p:.0%} a turn of its clock)"})
                continue
        now.append(v)
    for j in range(2):
        name = f"learn:{j}"
        turned, k, start = clocks.at(name, LEARN_DAYS)
        if not turned:
            continue
        a = appetite(ctx, start)
        p = LEARN[0] + LEARN[1] * a if j == 0 else LEARN_AGAIN * max(0.0, a - 0.5)
        if clocks.coin(name, k) >= p:
            continue
        v = own_variant(ctx, name, k, now)
        if v is None:
            continue
        v = V.Variant(v.phrase, v.note, v.kind, v.degree, v.steps, v.shift, "drift", generation)
        now.append(v)
        _log(ctx, lambda v=v: {"what": "tune", "change": "learned", "variant": v.to_dict(), "about": about(v),
                   "why": f"this machine's way this season ({p:.0%} a turn of its clock, appetite {a:.2f})"})
    out["variants"] = [v.to_dict() for v in V.parse(now)]


# ---------------------------------------------------------------- the words


class Picker:
    """The machine's own picks for words its parent didn't have (a verse for a longer form, a couplet for a
    refrain, the bridge's extra stanza, a slot word): which verse it would take in, which couplet. Weighted
    as arrange() weighs a draw, with the machine's leanings, and fixed for this machine and this generation
    of the song (stamp), so a machine singing one parent for months takes in the same verse whenever its
    form grows, as a singer has a verse they reach for."""

    def __init__(self, genome, hash_: str = "timeless", stamp=0, leanings=None):
        self.genome, self.hash, self.stamp = genome, hash_, stamp
        self.leanings = leanings
        self.vocabulary = frozenset(getattr(leanings, "vocabulary", ()) or ())

    def one(self, name: str, options: list, weights=None):
        """The machine's pick among some options."""
        if not options:
            return None
        names = [repr(o) for o in options]
        key = ("one", self.hash, name, self.stamp, tuple(names), tuple(weights) if weights is not None else None)
        at = _memo(key, lambda: names.index(repr(_ranked((self.hash, name, self.stamp), list(options), weights, names)[0])))
        return options[at]

    def verse(self, name: str, ok) -> str | None:
        """The machine's verse: the first, in its own order of the bank's verses (weighted as arrange()
        weighs them with its leanings), for which ok(id) holds."""
        lean = self.leanings.to_dict() if self.leanings is not None else None

        def ranking():
            weights = arrange.verse_weights(self.genome, self.leanings)
            ids = list(arrange.verse_ids(self.genome))
            return _ranked((self.hash, name, self.stamp), ids, [weights[i] for i in ids])

        key = ("verse", id(self.genome), self.hash, name, self.stamp, repr(lean))
        return next((i for i in _memo(key, ranking, self.genome) if ok(i)), None)

    def couplet(self, name: str, ids: list[str]) -> str | None:
        return self.one(name, ids, arrange.affinity(self.genome, "couplet", ids, self.vocabulary) if ids else None)

    def slots(self, name: str, entry: dict, keep: dict | None = None) -> dict:
        """Slot words for a bank entry: those kept where they are its words, the machine's pick for the rest."""
        keep = keep or {}
        out = {}
        for slot, words in arrange.slot_words(entry).items():
            out[slot] = keep[slot] if keep.get(slot) in words else self.one(f"{name}:{slot}", words)
        return out


def seed_words(genome, params) -> dict:
    """The words a parent holds that never held any: the seed's own for its form, as held words."""
    form = tuple(params.form)
    return copy.deepcopy(_memo(("seed words", id(genome), form),
                               lambda: arrange.hold(genome, arrange.seed_lyrics(genome, form)), genome))


def _blocks(genome, form) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in form:
        block = genome.section(name).lyrics
        if block:
            counts[block] = counts.get(block, 0) + 1
    return counts


def fit(genome, form, held: dict, picker: Picker, log=None) -> dict:
    """Held words fitted to a form, keeping all they can: a longer form takes in a verse of the machine's
    choosing (at the end where the rules allow), a shorter one leaves the last out, the couplets and
    bridge stanzas follow the refrains and bridges, and anything the rules forbid is replaced by the
    machine's pick. Every change is logged with why."""
    note = log.append if log is not None else (lambda entry: None)
    held = copy.deepcopy(held or {})
    blocks = _blocks(genome, form)
    all_verses = arrange.verse_ids(genome)

    verses = list(held.get("verses", []))
    while verses and arrange.verse_problem(genome, verses):
        why = arrange.verse_problem(genome, verses)
        gone = verses.pop()
        note({"what": "words", "change": "left out", "where": f"verse {len(verses) + 1}", "from": gone.get("id"),
              "why": f"the bank's rules: {why}"})
    want = blocks.get("verse", 0)
    while len(verses) > want:
        gone = verses.pop()
        note({"what": "words", "change": "left out", "where": f"verse {len(verses) + 1}", "from": gone["id"],
              "why": f"the form sings {want} verse{'s' if want != 1 else ''}"})
    while len(verses) < want:
        ids = [v["id"] for v in verses]
        name = f"verse:{len(verses) + 1}"
        # at the end, where the rules allow; else wherever they do
        chosen = picker.verse(name, lambda x: x not in ids and arrange.verse_order(genome, ids + [x], ids + [x]) == tuple(ids + [x])) \
            or picker.verse(name, lambda x: x not in ids and arrange.verse_order(genome, ids + [x], ids) is not None)
        if chosen is None:
            break
        order = arrange.verse_order(genome, ids + [chosen], ids)
        new = {"id": chosen, "slots": picker.slots(f"slots:{chosen}", arrange.bank_entry(genome, "verse", chosen))}
        by_id = {v["id"]: v for v in verses} | {chosen: new}
        verses = [by_id[i] for i in order]
        note({"what": "words", "change": "added", "where": f"verse {order.index(chosen) + 1}", "to": chosen,
              "why": f"the form sings {want} verses; this machine's verse this season"})
    held["verses"] = verses

    refrain = held.setdefault("refrain", {})
    slots = dict(refrain.get("slots", {}))
    for slot, words in arrange.refrain_slot_words(genome).items():
        if slots.get(slot) not in words:
            slots[slot] = picker.one(f"refrain:{slot}", words)
    refrain["slots"] = slots
    allowed = arrange.couplet_ids(genome)
    couplets, seen, dropped = [], set(), []
    for c in refrain.get("couplets", []):
        if c.get("id") in allowed and c["id"] not in seen:
            couplets.append(c)
            seen.add(c["id"])
        else:
            dropped.append(c.get("id"))
    if dropped:
        note({"what": "words", "change": "rule", "where": "refrain", "from": ", ".join(map(str, dropped)),
              "why": "each refrain before the last sings a couplet of its own, the canon only last (the bank's rule; "
                     "the seed sings its canon every time)"})
    want = max(blocks.get("refrain", 0) - 1, 0)
    while len(couplets) > want:
        gone = couplets.pop()
        note({"what": "words", "change": "left out", "where": f"refrain {len(couplets) + 1}", "from": gone["id"],
              "why": f"the form sings {want + 1} refrains"})
    while len(couplets) < want:
        options = [c for c in allowed if c not in {x["id"] for x in couplets}]
        chosen = picker.couplet(f"couplet:{len(couplets) + 1}", options)
        if chosen is None:
            break
        couplets.append({"id": chosen, "slots": picker.slots(f"couplet-slots:{chosen}",
                                                             arrange.bank_entry(genome, "couplet", chosen))})
        note({"what": "words", "change": "added", "where": f"refrain {len(couplets)}", "to": chosen,
              "why": "a refrain needed a couplet; this machine's this season"})
    refrain["couplets"] = couplets
    canon = arrange.bank_entry(genome, "couplet", arrange.last_couplet(genome))
    if arrange.slot_words(canon) and blocks.get("refrain"):  # the last refrain's couplet, where it has slot words
        kept = (refrain.get("last") or {}).get("slots", {})
        refrain["last"] = {"id": canon["id"], "slots": picker.slots(f"couplet-slots:{canon['id']}", canon, kept)}

    always, extras = arrange.bridge_ids(genome)
    bridges = list(held.get("bridge", []))
    want = blocks.get("bridge", 0)
    first = bridges[0] if bridges and bridges[0].get("id") == always else {"id": always, "slots": {}}
    first = {"id": always, "slots": picker.slots("bridge", arrange.bank_entry(genome, "bridge", always), first.get("slots"))}
    out = [first] if want else []
    if want > 1:
        second = bridges[1] if len(bridges) > 1 and bridges[1].get("id") in extras else None
        if second is None:
            chosen = picker.one("extra", list(extras))
            second = {"id": chosen, "slots": {}}
            note({"what": "words", "change": "added", "where": "bridge 2", "to": chosen,
                  "why": "the form sings the bridge twice; this machine's extra stanza this season"})
        entry = arrange.bank_entry(genome, "bridge", second["id"])
        second = {"id": second["id"], "slots": picker.slots("bridge", entry, {**first["slots"], **second.get("slots", {})})}
        out.append(second)
    held["bridge"] = out

    if blocks.get("tag"):
        syllables = list(arrange.tag_syllables(genome))
        if held.get("tag") not in syllables:
            held["tag"] = picker.one("tag", syllables)
            note({"what": "words", "change": "added", "where": "tag", "to": held["tag"],
                  "why": "the form sings the tag; this machine's syllable"})
    else:
        held.pop("tag", None)
    return held


def places(genome, held: dict) -> list[tuple]:
    """Every place in some held words a swap could fall, with how likely the drift is to choose it: ("verse",
    i), ("slot", i, name) for a verse's slot word, ("couplet", i), ("refrain", name), ("bridge", name),
    ("tag",) and ("extra",). What a person editing the words could change, one thing at a time."""
    out = []
    verses = held.get("verses", [])
    for i, v in enumerate(verses):
        out.append((("verse", i), SWAPS["verse"] / max(len(verses), 1)))
    for i, v in enumerate(verses):
        names = sorted(arrange.slot_words(arrange.bank_entry(genome, "verse", v["id"])))
        for name in names:
            out.append((("slot", i, name), SWAPS["slot"] / max(len(verses), 1) / len(names)))
    couplets = held.get("refrain", {}).get("couplets", [])
    for i, _ in enumerate(couplets):
        out.append((("couplet", i), SWAPS["couplet"] / len(couplets)))
    names = sorted(arrange.refrain_slot_words(genome))
    for name in names:
        out.append((("refrain", name), SWAPS["refrain"] / len(names)))
    if held.get("bridge"):
        names = sorted(arrange.slot_words(arrange.bank_entry(genome, "bridge", held["bridge"][0]["id"])))
        for name in names:
            out.append((("bridge", name), SWAPS["bridge"] / len(names)))
    if held.get("tag"):
        out.append((("tag",), SWAPS["tag"]))
    if len(held.get("bridge", [])) > 1:
        out.append((("extra",), SWAPS["extra"]))
    return out


def alternatives(genome, held: dict, where: tuple) -> list:
    """What could stand in one of those places, keeping the bank's rules as the rest of the words stand:
    verse ids, a slot's words (a coupled slot's as a whole, a noun with its pronouns), couplet ids, tag
    syllables or extra stanzas."""
    kind = where[0]
    if kind == "verse":
        i = where[1]
        ids = [v["id"] for v in held["verses"]]
        out = []
        for x in arrange.verse_ids(genome):
            if x in ids:
                continue
            trial = ids[:i] + [x] + ids[i + 1:]
            if arrange.verse_order(genome, trial, trial) == tuple(trial):
                out.append(x)
        return out
    if kind == "slot":
        v = held["verses"][where[1]]
        words = arrange.slot_words(arrange.bank_entry(genome, "verse", v["id"])).get(where[2], [])
        return [w for w in words if w != v.get("slots", {}).get(where[2])]
    if kind == "couplet":
        taken = {c["id"] for c in held["refrain"]["couplets"]}
        return [c for c in arrange.couplet_ids(genome) if c not in taken]
    if kind == "refrain":
        return [w for w in arrange.refrain_slot_words(genome)[where[1]] if w != held["refrain"]["slots"].get(where[1])]
    if kind == "bridge":
        words = arrange.slot_words(arrange.bank_entry(genome, "bridge", held["bridge"][0]["id"]))[where[1]]
        return [w for w in words if w != held["bridge"][0].get("slots", {}).get(where[1])]
    if kind == "tag":
        return [s for s in arrange.tag_syllables(genome) if s != held.get("tag")]
    if kind == "extra":
        return [e for e in arrange.bridge_ids(genome)[1] if e != held["bridge"][1]["id"]]
    return []


def label(where: tuple) -> str:
    """A place in the words, for reading: "verse 2", "verse 1's who", "the refrain's while"."""
    kind = where[0]
    return {"verse": lambda: f"verse {where[1] + 1}", "slot": lambda: f"verse {where[1] + 1}'s {where[2]}",
            "couplet": lambda: f"refrain {where[1] + 1}'s couplet", "refrain": lambda: f"the refrain's {where[1]}",
            "bridge": lambda: f"the bridge's {where[1]}", "tag": lambda: "the tag's syllable",
            "extra": lambda: "the bridge's extra stanza"}[kind]()


def swap(genome, form, held: dict, ctx: Context, picker: Picker, mode: str | None = None) -> dict:
    """At most one swap when the swap clock turns (on another machine, once a hand-off): a verse, a slot
    word, a couplet, the tag's syllable... for one the machine likes this season (its leanings as they
    stood when the stretch began, so the pick holds through it). Where it falls is fixed for this machine
    and this generation of the song, so a machine singing one parent for months swaps in one place, while a
    lineage swaps somewhere new each generation."""
    from .variation import own_leanings

    clocks = Clocks(ctx)
    turned, k, start = clocks.at("swap", SWAP_DAYS)
    if not turned:
        return held
    p = clip(SWAP[0] + SWAP[1] * ctx.c.id("restless") + SWAP[2] * slow(ctx, "words", start), *SWAP_BOUNDS)
    if clocks.coin("swap", k) >= p:
        return held
    spots = places(genome, held)
    if not spots:
        return held
    generation = getattr(ctx.parent, "generation", 0)
    for where in _ranked((clocks.hash, "where", generation), [p for p, _ in spots], [w for _, w in spots]):
        options = alternatives(genome, held, where)
        if not options:
            continue
        new = copy.deepcopy(held)
        kind = where[0]
        if kind == "verse":
            season = _memo(("season", id(genome), ctx.c.hash, clocks.hash, start, mode,
                            repr(getattr(ctx.parent, "leanings", None))), lambda: own_leanings(ctx, start, mode), genome)
            weights = arrange.verse_weights(genome, season)
            chosen = _ranked((clocks.hash, "swap-in", k), options, [weights[x] for x in options])[0]
            was = new["verses"][where[1]]["id"]
            new["verses"][where[1]] = {"id": chosen, "slots": picker.slots(f"slots:{chosen}",
                                                                           arrange.bank_entry(genome, "verse", chosen))}
        else:
            chosen = _ranked((clocks.hash, "swap-in", k), options, names=[repr(o) for o in options])[0]
            if kind == "slot":
                was = new["verses"][where[1]]["slots"].get(where[2])
                new["verses"][where[1]]["slots"][where[2]] = chosen
            elif kind == "couplet":
                was = new["refrain"]["couplets"][where[1]]["id"]
                new["refrain"]["couplets"][where[1]] = {"id": chosen, "slots": picker.slots(
                    f"couplet-slots:{chosen}", arrange.bank_entry(genome, "couplet", chosen))}
            elif kind == "refrain":
                was = new["refrain"]["slots"].get(where[1])
                new["refrain"]["slots"][where[1]] = chosen
            elif kind == "bridge":
                was = new["bridge"][0]["slots"].get(where[1])
                new["bridge"][0]["slots"][where[1]] = chosen
            elif kind == "tag":
                was, new["tag"] = new.get("tag"), chosen
            else:
                was = new["bridge"][1]["id"]
                new["bridge"][1] = {"id": chosen, "slots": {}}
        if arrange.held_problem(genome, form, new):
            continue
        _log(ctx, {"what": "words", "change": "swapped", "where": label(where), "from": _plain(was), "to": _plain(chosen),
                   "why": f"this machine's own this season ({p:.0%} a turn of its clock)"})
        return new
    return held


def _plain(value):
    if isinstance(value, dict):
        return "/".join(str(v) for v in value.values()).replace("-", "")
    return str(value).replace("-", "") if value is not None else None


def choose_words(out: dict, ctx: Context) -> None:
    """The words the lineage holds: the parent's (the seed's own, the first time), fitted to this form, with
    at most one swap when the swap clock turns. A song without a bank, or a form its bank can't fill,
    keeps what it holds and sings the seed's words."""
    genome = ctx.genome
    if not genome.source.get("bank") or arrange.problem(genome, out["form"]):
        return
    from .variation import own_leanings

    hash_ = Clocks(ctx).hash
    stamp = getattr(ctx.parent, "generation", 0)
    taste = _memo(("taste", id(genome), ctx.c.hash, hash_, stamp, repr(getattr(ctx.parent, "leanings", None))),
                  lambda: own_leanings(ctx), genome)
    picker = Picker(genome, hash_, stamp, taste)
    base = getattr(ctx.parent, "words", None) or seed_words(genome, ctx.parent)
    held = fit(genome, tuple(out["form"]), base, picker, getattr(ctx, "log", None))
    if ctx.drift is not None:
        held = swap(genome, tuple(out["form"]), held, ctx, picker, out.get("mode"))
    if arrange.held_problem(genome, out["form"], held):  # never expected: the words are drawn afresh instead
        why = arrange.held_problem(genome, out["form"], held)
        held = arrange.hold(genome, arrange.arrange(genome, out["form"], int(out.get("seed", 0)) % 2**31, taste))
        _log(ctx, {"what": "words", "change": "drawn", "why": f"the held words couldn't be sung ({why}), so all are drawn afresh"})
    out["words"] = held


def fitted(genome, params, voice=None, drift=None) -> dict:
    """A rendition's held words fitted to its form, when the form was set after its words were chosen (a
    --form): the words as held if they fit, else fitted with the machine's picks."""
    held = params.words or seed_words(genome, params)
    if not arrange.held_problem(genome, params.form, held):
        return held
    from .variation import leanings

    hash_ = drift.hash if drift is not None and drift.hash else (voice.hash if voice is not None else "timeless")
    picker = Picker(genome, hash_, max(params.generation - 1, 0), leanings(params))
    return fit(genome, params.form, held, picker)


# ---------------------------------------------------------------- what changed (for a record and the studio)


def _entry(e) -> str | None:
    """A held verse, couplet or stanza for reading: its id and its slot words."""
    if not e:
        return None
    words = ", ".join(_plain(v) for v in (e.get("slots") or {}).values())
    return f"{e['id']} ({words})" if words else e["id"]


def diff(genome, parent, child) -> list[dict]:
    """What a child sings differently from its parent, in the tune and the words, for reading, without the
    why (a rendition's record keeps the why its choices were made with)."""
    out = []
    was = {v.what: v for v in V.parse(getattr(parent, "variants", ()))}
    now = {v.what: v for v in V.parse(getattr(child, "variants", ()))}
    for key in sorted(set(was) - set(now)):
        out.append({"what": "tune", "change": "dropped", "about": V.describe(genome, was[key])})
    for key in sorted(set(now) - set(was)):
        out.append({"what": "tune", "change": "gained", "about": V.describe(genome, now[key])})
    a = getattr(parent, "words", None) or seed_words(genome, parent)
    b = getattr(child, "words", None) or {}
    if not b:
        return out
    va, vb = a.get("verses", []), b.get("verses", [])
    for i in range(max(len(va), len(vb))):
        x, y = (va[i] if i < len(va) else None), (vb[i] if i < len(vb) else None)
        if x != y:
            out.append({"what": "words", "change": "verse", "where": f"verse {i + 1}", "from": _entry(x), "to": _entry(y)})
    ra, rb = a.get("refrain", {}), b.get("refrain", {})
    pairs = (("couplets", lambda r: ", ".join(_entry(c) for c in r.get("couplets", []))),
             ("refrain", lambda r: ", ".join(f"{k} {_plain(v)}" for k, v in r.get("slots", {}).items())))
    for change, text in pairs:
        if text(ra) != text(rb):
            out.append({"what": "words", "change": change, "from": text(ra), "to": text(rb)})
    ba, bb = (", ".join(_entry(e) for e in w.get("bridge", [])) for w in (a, b))
    if ba != bb:
        out.append({"what": "words", "change": "bridge", "from": ba, "to": bb})
    if b.get("tag") is not None and a.get("tag") != b.get("tag"):
        out.append({"what": "words", "change": "tag", "from": a.get("tag"), "to": b.get("tag")})
    return out
