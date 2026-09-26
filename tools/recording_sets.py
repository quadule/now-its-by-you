"""Recording sets: what singers are asked to sing, so that their takes hold the words the learned voice
says worst, while each set stays a short song that is easy to sing.

The learned voice (VoiceParams' default, the "learned" engine) sings every entry of the song's bank, dry,
at the seed's key and tempo: each verse with every word its slots can take, each refrain head with every
question it can ask, every couplet, each bridge stanza and the tag, one section at a time. Whisper base.en
hears each, never shown the lyric, and every sung word is scored heard or misheard by
tools/intelligibility.py's alignment (a homophone, a number written as digits, or a compound heard as two
words counts as heard: a listener couldn't tell them apart). The chooser then picks a few sets, each a song
the bank's rules allow, that together put every word the voice gets wrong, and every verse it gets clearly
wrong, in front of singers at least once, the worst twice.

    uv run python tools/recording_sets.py measure    # sing and hear everything (cached in renders/sets/)
    uv run python tools/recording_sets.py choose     # write tools/sets/h-now-its-by-you.json
    uv run python tools/recording_sets.py report     # the analysis, for docs/RECORDING-SETS.md

Dev-only: measuring needs faster-whisper and its base.en model; choosing needs only what measuring cached.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message="pkg_resources")
sys.path.insert(0, str(Path(__file__).parent))
from intelligibility import align  # noqa: E402  (tools/intelligibility.py)
from wer_suite import collapse_loops  # noqa: E402  (tools/wer_suite.py)

from songbird import arrange as A  # noqa: E402
from songbird import genome as G  # noqa: E402
from songbird import phonetics  # noqa: E402
from songbird.bank import slot_names, width  # noqa: E402

ROOT = Path(__file__).parent.parent
SONG = ROOT / "songs" / "h-now-its-by-you.json"
CACHE = ROOT / "renders" / "sets"
SETS = ROOT / "tools" / "sets"
SR = 44100
SEEDS = (1, 2, 3)  # the voice's own chance (its jitter, its consonants' lengths): each item is sung three ways
MODEL = "base.en"
VERSION = 1  # bump to hear everything again


# What is sung: every entry of the bank, every word its slots can take at least once


def _label(value) -> str:
    """A slot's option as it reads: a coupled slot by its first column (the noun), hyphens gone."""
    if isinstance(value, dict):
        value = value.get("noun", next(iter(value.values())))
    return str(value).replace("-", "")


def items(genome) -> list[dict]:
    """Everything the learned voice is asked to sing, one section each, as dicts (section, entry, head,
    couplet, slot words by name, lines as sung). Each slot's every option is sung at least once: an
    entry with slots is sung as many times as its widest slot has options, the i-th time with each
    slot's i-th option (round again for a narrower slot)."""
    song = A._song(genome)
    bank = song.bank
    out = []

    def picks_for(entry: dict, i: int, fixed: dict | None = None) -> dict[str, int]:
        slots = entry.get("slots", {})
        fixed = fixed or {}
        return {n: fixed[n] if n in fixed else i % width(slots, n) for n in slot_names(entry["lines"])}

    def words_of(entry: dict, picks: dict[str, int]) -> dict[str, str]:
        slots = entry.get("slots", {})
        return {n: _label(A._value(slots[n], i)) for n, i in picks.items()}

    def rounds(entry: dict, fixed: dict | None = None) -> int:
        slots = entry.get("slots", {})
        free = [n for n in slot_names(entry["lines"]) if n not in (fixed or {})]
        return max([width(slots, n) for n in free] or [1])

    for v in bank["verses"]:
        for i in range(rounds(v)):
            picks = picks_for(v, i)
            out.append({"section": "verse", "kind": "verse", "entry": v["id"], "words": words_of(v, picks),
                        "lines": list(song.sing(v, picks))})
    couplets = bank["refrain"]["couplets"]
    k = 0
    for hid, head in song.heads.items():
        fixed = song.fixed[hid]
        for i in range(rounds(head, fixed)):
            picks = picks_for(head, i, fixed)
            couplet = couplets[k % len(couplets)]
            k += 1
            out.append({"section": "refrain", "kind": "refrain", "entry": f"{hid}+{couplet['id']}", "head": hid,
                        "couplet": couplet["id"], "words": words_of(head, picks),
                        "lines": list(song.sing(head, picks) + song.sing(couplet, {}))})
    for b in bank.get("bridges", []):
        for i in range(rounds(b)):
            picks = picks_for(b, i)
            out.append({"section": "bridge", "kind": "bridge", "entry": b["id"], "words": words_of(b, picks),
                        "lines": list(song.sing(b, picks))})
    tag = genome.section("tag")
    for syllable in bank["tag"]["syllables"]:
        lines = [" ".join([syllable] * len(genome.phrases[pid].sung)) + "." for pid in tag.phrases]
        out.append({"section": "tag", "kind": "tag", "entry": syllable, "words": {}, "lines": lines})
    for item in out:
        item["key"] = ":".join([item["kind"], item["entry"]] + [f"{n}={w}" for n, w in item["words"].items()])
    return out


# Hearing it: Whisper, and the words it heard lined up against the words sung

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

# Words a listener can't tell apart when sung: either is heard right. Each group's first is the one kept.
HOMOPHONES = [
    "quay key", "to two too", "knows nose", "new knew", "heard herd", "one won", "through threw", "whole hole",
    "by buy bye", "for four fore", "hear here", "there their they're", "no know", "so sew sow", "right write",
    "eight ate", "made maid", "night knight", "would wood", "some sum", "son sun", "tale tail", "vale veil",
    "ale ail", "soul sole", "rain reign", "peace piece", "seen scene", "see sea", "weak week", "passed past",
    "sent cent scent", "blue blew", "due dew do", "hour our", "wear where ware", "which witch", "whether weather",
    "hall haul", "told tolled", "road rode rowed", "roll role", "beat beet", "grey gray", "morning mourning",
    "coal cole", "whose who's", "its it's", "missed mist", "flour flower", "all awl", "in inn", "bell belle",
    "tide tied", "wait weight", "we wee", "higher hire", "not knot", "none nun", "him hymn", "wholly holy",
    "war wore", "ward warred", "board bored", "dear deer", "fair fare", "hair hare", "pair pear", "stare stair",
    "steel steal", "real reel", "rose rows", "toe tow", "wave waive", "way weigh whey", "cellar seller", "cannon canon",
]
_SAME = {w: group.split()[0] for group in HOMOPHONES for w in group.split()}


def _number(n: int) -> str:
    """A whole number in words, the way it is sung: 8 eight, 15 fifteen, 1916 nineteen sixteen."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + _number(n % 100))
    if 1100 <= n < 2000 or 2010 <= n < 2100:  # a year
        return _number(n // 100) + " " + ("hundred" if n % 100 == 0 else _number(n % 100))
    return _number(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + _number(n % 1000))


def tokens(text: str) -> list[str]:
    """Words as a listener would compare them: lower case, no punctuation or apostrophes, digits said as
    words (8:15 as eight fifteen), and each homophone as its group's first."""
    text = text.lower().replace("’", "'").replace("-", " ")
    text = re.sub(r"\d+", lambda m: " " + _number(int(m.group())) + " ", text.replace(",", ""))
    words = re.sub(r"[^a-z' ]+", " ", text).split()
    return [_SAME.get(w, _SAME.get(w.replace("'", ""), w.replace("'", ""))) for w in words]


def joined(heard: list[str], sung: set[str]) -> list[str]:
    """Words heard as two or three where the lyric has one ("no body", "half invented") joined again."""
    out, i = [], 0
    while i < len(heard):
        n = next((n for n in (3, 2) if i + n <= len(heard) and "".join(heard[i:i + n]) in sung), 1)
        out.append("".join(heard[i:i + n]))
        i += n
    return out


def word_token(written: str) -> str:
    """A sung word, as written with its syllable hyphens, as tokens() compares it."""
    found = tokens(written.replace("-", ""))
    return found[0] if found else ""


def sung_words(notes) -> list[tuple[str, int]]:
    """The words the notes sing, in order, each as written (hyphens, no marks) with its syllable count."""
    out, i = [], 0
    while i < len(notes):
        word = notes[i].word.replace("*", "")
        out.append((re.sub(r"[^A-Za-z'\-]", "", word), notes[i].word_len))
        i += notes[i].word_len
    return out


def phones(word: str, n: int, lexicon: dict | None) -> list[str]:
    """A written word's sounds as the voice sings them (ARPAbet, vowels without stress)."""
    try:
        return [p for s in phonetics.fit(word, n, lexicon) for p in (*s.onset, s.nucleus, *s.coda)]
    except (KeyError, ValueError):
        return []


_WORKER: dict = {}


def _start(model: str) -> None:
    from faster_whisper import WhisperModel

    _WORKER["genome"] = G.load(SONG)
    _WORKER["model"] = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=2)


def _cache_path(item: dict, seed: int) -> Path:
    what = json.dumps({"lines": item["lines"], "section": item["section"], "seed": seed, "model": MODEL,
                       "version": VERSION}, sort_keys=True)
    return CACHE / f"{hashlib.sha256(what.encode()).hexdigest()[:16]}.json"


def hear(item: dict, seed: int) -> dict:
    """Sing one item dry with the default learned voice, cut from its first sound to its last, and have
    Whisper hear it: the words sung, what was heard, and each sung word's fate (heard, or what was heard
    in its place, "" for nothing)."""
    from scipy.signal import resample_poly

    from songbird.realize import choose_params, realize
    from songbird.synth import throat
    from songbird.synth.voice import VoiceParams, schedule, sing

    genome, model = _WORKER["genome"], _WORKER["model"]
    sung = A.Sung(item["section"], genome.section(item["section"]).lyrics, item["entry"], {}, tuple(item["lines"]),
                  item.get("head"))
    lyrics = A.Lyrics((item["section"],), None, (sung,))
    score = realize(genome, replace(choose_params(genome), form=(item["section"],)), lyrics=lyrics)
    notes = sorted(score.part("voice"), key=lambda n: n.start)
    voice = VoiceParams()
    y = sing(notes, SR, voice, seed=seed, lexicon=genome.lexicon)
    segs = schedule(notes, voice, genome.lexicon, throat.DURATIONS, seed=seed)
    # from the first vowel's onset consonants to the last vowel's codas, as tools/wer_suite.py cuts
    i = next(k for k, s in enumerate(segs) if s.role == "vowel")
    while i > 0 and segs[i - 1].role == "onset":
        i -= 1
    j = max(k for k, s in enumerate(segs) if s.role == "vowel")
    while j + 1 < len(segs) and segs[j + 1].role == "coda":
        j += 1
    a, b = max(int((segs[i].t0 - 0.05) * SR), 0), int((segs[j].t1 + 0.05) * SR)
    audio = resample_poly(y[a:b], 16000, SR).astype(np.float32)
    audio /= np.abs(audio).max() + 1e-9
    parts, _ = model.transcribe(audio, language="en", beam_size=5, temperature=0.0,
                                condition_on_previous_text=False, vad_filter=False, no_repeat_ngram_size=5)
    heard = " ".join(p.text for p in parts).strip()
    written = sung_words(notes)
    if item["kind"] == "tag":  # la la la... counts once, as heard
        written = written[:1]
    return score({"key": item["key"], "seed": seed, "heard": heard, "words": [[w, n] for w, n in written]})


def score(record: dict) -> dict:
    """A hearing scored: each sung word (as written, with its syllable count) with the word it is compared
    as and what was heard in its place ("" for nothing), and the edits between the two, as
    tools/intelligibility.py counts them (words heard after the lyric ends aside)."""
    written = [w[:2] for w in record["words"]]
    ref = [word_token(w) for w, _ in written]
    hyp = collapse_loops(joined(tokens(record["heard"]), set(ref)))
    _, pairs = align(ref, hyp)
    while pairs and not pairs[-1][0]:  # words heard after the lyric ends are Whisper's own
        pairs.pop()
    fates = [h for r, h in pairs if r]
    return {**record, "words": [[w, n, r, f] for (w, n), r, f in zip(written, ref, fates)],
            "inserted": sum(1 for r, _ in pairs if not r), "edits": sum(r != h for r, h in pairs)}


def _hear_cached(job: tuple[dict, int]) -> dict:
    item, seed = job
    path = _cache_path(item, seed)
    if path.exists():
        return json.loads(path.read_text())
    out = hear(item, seed)
    path.write_text(json.dumps(out))
    return out


def measure(genome, seeds=SEEDS, jobs: int = 5, model: str = MODEL) -> list[dict]:
    """Every item sung with every seed and heard, from the cache where it has them."""
    CACHE.mkdir(parents=True, exist_ok=True)
    work = [(item, seed) for item in items(genome) for seed in seeds]
    todo = [w for w in work if not _cache_path(*w).exists()]
    if todo:
        os.environ.setdefault("OMP_NUM_THREADS", "2")
        print(f"singing and hearing {len(todo)} of {len(work)} ({jobs} at a time)", file=sys.stderr)
        with ProcessPoolExecutor(jobs, initializer=_start, initargs=(model,)) as pool:
            for n, _ in enumerate(pool.map(_hear_cached, todo, chunksize=2), 1):
                if n % 25 == 0:
                    print(f"  {n}/{len(todo)}", file=sys.stderr)
    return [score(json.loads(_cache_path(*w).read_text())) for w in work]  # scored afresh: the rules may change


# What the measures say


def _mean(xs) -> float:
    xs = list(xs)
    return float(np.mean(xs)) if xs else 0.0


def analyze(genome, heard: list[dict]) -> dict:
    """The measures gathered up:

    - "entries": each verse, refrain head, couplet, bridge stanza and tag syllable, by kind:id, with its
      word error rate over every way it was sung and every seed;
    - "items": each item's word error rate (a verse with some slot words, a refrain...);
    - "words": each word as heard (tokens()), how often it was sung and how often misheard;
    - "phones": each sound, how often it was sung in a word and how often that word was misheard;
    - "overall": the word error rate over everything but the tag."""
    listed = {i["key"]: i for i in items(genome)}
    by_item = defaultdict(list)
    for h in heard:
        by_item[h["key"]].append(h)
    item_wer = {k: _mean(h["edits"] / max(len(h["words"]), 1) for h in hs) for k, hs in by_item.items()}
    entries: dict[str, list[float]] = defaultdict(list)
    for k, hs in by_item.items():
        item = listed[k]
        if item["kind"] == "refrain":
            # a refrain's head is its first two lines, its couplet the last two
            split = _head_words(item["lines"])
            for h in hs:
                head, couplet = h["words"][:split], h["words"][split:]
                entries[f"head:{item['head']}"].append(_wrong(head) / max(len(head), 1))
                entries[f"couplet:{item['couplet']}"].append(_wrong(couplet) / max(len(couplet), 1))
        else:
            entries[f"{item['kind']}:{item['entry']}"] += [h["edits"] / max(len(h["words"]), 1) for h in hs]
    words: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    phone_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    lexicon = genome.lexicon or None
    for h in heard:
        if listed[h["key"]]["kind"] == "tag":
            continue
        for written, n, ref, fate in h["words"]:
            wrong = int(fate != ref)
            words[ref][0] += 1
            words[ref][1] += wrong
            for p in set(phones(written, n, lexicon)):
                phone_counts[p][0] += 1
                phone_counts[p][1] += wrong
    sung = [h for h in heard if listed[h["key"]]["kind"] != "tag"]
    total = sum(len(h["words"]) for h in sung)
    # how often the song sings each word where it is: in each of an entry's ways, or in some of them
    ways: dict[str, list[set]] = defaultdict(list)
    for k, hs in by_item.items():
        item = listed[k]
        ways[f"{item['kind']}:{item['entry'].split('+')[0]}"].append({ref for _, _, ref, _ in hs[0]["words"]})
        if item["kind"] == "refrain":
            ways[f"couplet:{item['couplet']}"].append({ref for _, _, ref, _ in hs[0]["words"]})
    share: dict[str, float] = {}
    for sets_ in ways.values():
        for w in set().union(*sets_):
            share[w] = max(share.get(w, 0.0), sum(w in s for s in sets_) / len(sets_))
    return {
        "overall": sum(h["edits"] for h in sung) / max(total, 1),
        "misheard": sum(_wrong(h["words"]) for h in sung) / max(total, 1),
        "items": item_wer,
        "entries": {k: _mean(v) for k, v in entries.items()},
        "words": {w: tuple(c) for w, c in words.items()},
        "phones": {p: tuple(c) for p, c in phone_counts.items()},
        "share": share,
    }


def _wrong(words) -> int:
    return sum(1 for _, _, ref, fate in words if fate != ref)


def _head_words(lines) -> int:
    """How many of a refrain's sung words its head (the first two lines) sings."""
    return sum(len([w for w in line.split() if re.sub(r"[^A-Za-z]", "", w)]) for line in lines[:2])


# What the sets must hold

MISHEARD = 0.5  # a word misheard at least this often, over at least three hearings, is one the sets should hold
SURE = 0.9  # a word misheard at least this often ...
SURE_HEARINGS = 6  # ... over at least this many hearings (sung two ways, or in two places, each heard three
# times) is one the voice surely says wrong: the sets must hold it, and ideally twice
HIGH = 1.5  # a verse whose word error rate is at least this many times the verses' median is clearly high
WORST_VERSES = 5  # the verses with the highest rates, which the sets ideally hold twice


def targets(analysis: dict) -> dict[str, dict]:
    """What the sets should hold, by "word:<w>" (as tokens() has it) or "verse:<id>": {"need": how many
    times, "must": whether they must hold it at least once, "weight": how much it matters otherwise}.

    - A word misheard at least MISHEARD of the times it was sung (three hearings at least) should be held
      once; one misheard SURE of the times over SURE_HEARINGS or more must be, ideally twice. A word
      weighs its rate times how often the song sings it where it is: 1 in a verse's own words, a third as
      one of a slot's three words.
    - A verse whose rate is clearly high (HIGH times the verses' median or more) must be held, the worst
      WORST_VERSES ideally twice."""
    out = {}
    for w, (n, m) in analysis["words"].items():
        if w and n >= 3 and m / n >= MISHEARD:
            must = m / n >= SURE and n >= SURE_HEARINGS
            out[f"word:{w}"] = {"need": 2 if must else 1, "must": must, "weight": m / n * analysis["share"].get(w, 1.0)}
    for i, v in enumerate(high_verses(analysis)):
        out[f"verse:{v}"] = {"need": 2 if i < WORST_VERSES else 1, "must": True, "weight": 3.0}
    return out


def verse_rates(analysis: dict) -> dict[str, float]:
    return {k.split(":", 1)[1]: v for k, v in analysis["entries"].items() if k.startswith("verse:")}


def high_verses(analysis: dict) -> list[str]:
    """The verses whose word error rate is clearly high (HIGH times the verses' median or more), worst
    first."""
    rates = verse_rates(analysis)
    median = float(np.median(list(rates.values())))
    return sorted((v for v in rates if rates[v] >= HIGH * median), key=lambda v: -rates[v])


def _count(lines, out: Counter) -> Counter:
    for line in lines:
        for word in line.replace("*", "").split():
            t = word_token(re.sub(r"[^A-Za-z'\-]", "", word))
            if t:
                out[f"word:{t}"] += 1
    return out


def held_targets(genome, held: dict, form) -> Counter:
    """How many times some held words, sung in a form, sing each word (as tokens() has it) and each verse."""
    out = Counter()
    for s in A.sing(genome, form, held).sections:
        if s.block != "tag":
            _count(s.lines, out)
        if s.block == "verse":
            out[f"verse:{s.id}"] += 1
    return out


def coverage(genome, sets: list[dict]) -> Counter:
    """How many times the sets, together, sing each word and each verse."""
    out = Counter()
    for s in sets:
        out += held_targets(genome, s["words"], s["form"])
    return out


# The sets: each a song the bank's rules allow, in one of the song's own shapes (variation.fits)

FOUR = ("intro", "verse", "refrain", "verse", "refrain", "verse", "refrain", "bridge", "refrain", "tag")
EXTRA = ("intro", "verse", "refrain", "verse", "verse", "refrain", "bridge", "bridge2", "refrain", "tag")
LONG = ("intro", "verse", "refrain", "verse", "verse", "verse", "refrain", "bridge", "refrain", "tag")

# Each set's form and the extra bridge stanza it sings, if any; every one lasts the same, nine sung
# sections. The first and last refrains of a song sing its own head (knows), and another head is sung at
# most once a song, so only the refrains between carry the other eight: sung once each and the artist's so
# twice, that is nine, which three sets of four refrains (two between) and three of three (one) just hold.
# The two extra stanzas each need a set; the last set sings four verses, as the rules allow, since the
# words the voice surely says wrong are spread over nineteen verses.
PLAN = (("a", FOUR, None), ("b", FOUR, None), ("c", FOUR, None), ("d", EXTRA, "coat"), ("e", EXTRA, "given"),
        ("f", LONG, None))
SO = "so"  # the artist's head, sung in the first two sets


def singers_form(genome, form) -> tuple[str, ...]:
    """A set's form as a singer hears it: a turn between every two sung sections (an existing turn not
    doubled), so none touch."""
    out: list[str] = []
    for name in form:
        if out and genome.section(name).lyrics and genome.section(out[-1]).lyrics:
            out.append("turn")
        out.append(name)
    return tuple(out)


def seconds(genome, form) -> float:
    """How long a form lasts, at the seed's tempo, its last note's ring included."""
    from songbird.realize import choose_params, realize

    return float(realize(genome, replace(choose_params(genome), form=tuple(form))).duration)


def ease(entry: dict) -> float:
    """How hard a verse is to sing, roughly: one that rhymes another way or runs a line on is harder, a
    rare one a little, and the more words it has (shorter notes, more to say on each), the harder."""
    words = sum(len(line.split()) for line in entry["lines"])
    variant = entry["scheme"] != "AABB" or bool(entry.get("enjambed"))
    return 2.0 * variant + (entry.get("rarity") == "rare") + words / 40.0


def _verse_ways(genome, entry: dict) -> list[tuple[dict, Counter]]:
    """Every way a verse's slots can be sung (as held words keep them), with the words each sings."""
    import itertools

    song = A._song(genome)
    names = slot_names(entry["lines"])
    slots = entry.get("slots", {})
    out = []
    for combo in itertools.product(*(range(width(slots, n)) for n in names)):
        picks = dict(zip(names, combo))
        counts = _count(song.sing(entry, picks), Counter())
        counts[f"verse:{entry['id']}"] += 1
        out.append((A._chosen(entry, picks), counts))
    return out


def _value(have: Counter, want: dict[str, dict]) -> float:
    """How well what the sets sing meets what they should: a must a hundred for its first time and ten for
    a second it needs, anything else ten times its weight for its first time and its weight for a second."""
    total = 0.0
    for t, w in want.items():
        n = have[t]
        if n >= 1:
            total += 100.0 if w["must"] else 10.0 * w["weight"]
        if n >= 2 and w["need"] >= 2:
            total += 10.0 if w["must"] else w["weight"]
    return total


def _refrain_rounds(genome, heads: list[str], couplets: list[str], prefer) -> list[dict]:
    """A set's refrains as held words keep them: these heads and couplets, canon last, and every slot's
    words as the rules have them, prefer(slot, words) choosing among the words the rules leave free."""
    song = A._song(genome)
    words = A.refrain_words(genome, heads, [{} for _ in heads], lambda i, slot, options: prefer(slot, options))
    last = song.rules["refrain"]["couplet_last"]
    return [{"head": h, "words": w, "id": c, "slots": {}} for h, w, c in zip(heads, words, list(couplets) + [last])]


def _frames(genome, analysis: dict, want: dict[str, dict]) -> list[dict]:
    """Each set of the plan without its verses: its form, refrains, bridge and tag. The heads between the
    first and last refrains are handed out worst heard first, the artist's so in the first two sets; the
    couplets are handed round worst heard first; a slot's words are the most misheard the rules leave free
    and not yet held, else the one sung least so far; the tag's syllable turns."""
    song = A._song(genome)
    bank = song.bank
    rates = analysis["words"]
    have, sung = Counter(), Counter()

    def prefer(slot, words):
        def rank(w):
            t = f"word:{word_token(_label(w).split()[-1])}"
            n, m = rates.get(t[5:], (1, 0))
            wanted = t in want and have[t] < want[t]["need"]
            return (-(m / max(n, 1)) * wanted, sung[_label(w)], _label(w))

        w = min(words, key=rank)
        sung[_label(w)] += 1
        have[f"word:{word_token(_label(w).split()[-1])}"] += 1
        return w

    heads = sorted((h for h in song.heads if h not in (song.head_id, SO)),
                   key=lambda h: -analysis["entries"].get(f"head:{h}", 0.0))
    last = song.rules["refrain"]["couplet_last"]
    couplets = sorted((c["id"] for c in bank["refrain"]["couplets"] if c["id"] != last),
                      key=lambda c: -analysis["entries"].get(f"couplet:{c}", 0.0))
    canon = next(b for b in bank["bridges"] if b["id"] == song.rules["bridge"]["always"])
    frames, k, j = [], 0, 0
    for i, (sid, form, extra) in enumerate(PLAN):
        n = sum(genome.section(s).lyrics == "refrain" for s in form)
        middle = [SO] if i < 2 else []
        while len(middle) < n - 2:
            middle.append(heads[k % len(heads)])
            k += 1
        chosen: list[str] = []
        while len(chosen) < n - 1:
            c = couplets[j % len(couplets)]
            j += 1
            if c not in chosen:
                chosen.append(c)
        rounds_ = _refrain_rounds(genome, [song.head_id, *middle, song.head_id], chosen, prefer)
        bridge = [{"id": canon["id"], "slots": {name: prefer(name, words) for name, words in A.slot_words(canon).items()}}]
        bridge += [{"id": extra, "slots": {}}] if extra else []
        tag = bank["tag"]["syllables"][i % len(bank["tag"]["syllables"])]
        frames.append({"id": sid, "form": list(form),
                       "words": {"verses": [], "refrain": {"rounds": rounds_}, "bridge": bridge, "tag": tag}})
    return frames


def _frame_targets(genome, frame: dict) -> Counter:
    """What a set sings besides its verses."""
    song = A._song(genome)
    out = Counter()
    couplets = {c["id"]: c for c in song.bank["refrain"]["couplets"]}
    for r in frame["words"]["refrain"]["rounds"]:
        head = song.heads[r["head"]]
        _count(song.sing(head, A._held_picks(head, r["words"], "refrain")) + song.sing(couplets[r["id"]], {}), out)
    stanzas = {b["id"]: b for b in song.bank["bridges"]}
    first = frame["words"]["bridge"][0]["slots"]
    for b in frame["words"]["bridge"]:
        stanza = stanzas[b["id"]]
        _count(song.sing(stanza, A._held_picks(stanza, {**first, **b["slots"]}, "bridge")), out)
    return out


def choose(genome, analysis: dict, rounds: int = 40) -> list[dict]:
    """The sets, most important first: each {"id", "form", "words"} (words as hold() keeps them).

    The refrains, bridges and tags come from _frames(). The verses, as many as each set's form sings, are
    chosen together:
    starting from each set in turn taking the verses (and slot words) that add most to what the sets
    should hold, any one verse of any set is swapped for whichever other verse or slot words adds most,
    while any swap adds something (a verse sung in a third set costs as much as a word, and an easier
    verse is worth a little more). Every set's verses must be ones the bank's rules let be sung together
    in some order; each set sings them in the order the rules allow that has the easier verses first. Sets
    of the same size are then handed their verses by what those hold, the most to the earliest letter."""
    song = A._song(genome)
    want = targets(analysis)
    frames = _frames(genome, analysis, want)
    base = Counter()
    for f in frames:
        base += _frame_targets(genome, f)
    entries = {v.id: v.entry for v in song.verses}
    ways = {vid: _verse_ways(genome, e) for vid, e in entries.items()}
    hardness = {vid: ease(e) for vid, e in entries.items()}
    order_of = {vid: i for i, vid in enumerate(entries)}
    allowed: dict[frozenset, list | None] = {}

    def order(ids) -> list[str] | None:
        key = frozenset(ids)
        if key not in allowed:
            found = A.verse_order(genome, list(ids))
            allowed[key] = list(found) if found else None
        return allowed[key]

    def total(pick: list[list[tuple[str, int]]]) -> float:
        have = Counter(base)
        uses = Counter()
        for chosen in pick:
            for vid, w in chosen:
                have += ways[vid][w][1]
                uses[vid] += 1
        return _value(have, want) - 10.0 * sum(max(0, n - 2) for n in uses.values()) \
            - 0.5 * sum(hardness[vid] for chosen in pick for vid, _ in chosen)

    sizes = [sum(genome.section(n).lyrics == "verse" for n in f["form"]) for f in frames]
    pick: list[list[tuple[str, int]]] = [[] for _ in frames]
    for s in range(len(frames)):  # a first draw: each set in turn, verse by verse, the best addition
        while len(pick[s]) < sizes[s]:
            options = [(vid, w) for vid in entries if vid not in {v for v, _ in pick[s]}
                       for w in range(len(ways[vid])) if order([v for v, _ in pick[s]] + [vid]) is not None]
            # among equals, a verse's own first slot words (the bank's), then the bank's order
            pick[s].append(max(options, key=lambda o: (total(pick[:s] + [pick[s] + [o]] + pick[s + 1:]),
                                                       -o[1], -order_of[o[0]])))
    score = total(pick)
    for _ in range(rounds):  # then any single swap that adds most, while one adds anything
        best = None
        for s in range(len(pick)):
            for p in range(sizes[s]):
                rest = [v for i, (v, _) in enumerate(pick[s]) if i != p]
                for vid in entries:
                    if vid in rest or order(rest + [vid]) is None:
                        continue
                    for w in range(len(ways[vid])):
                        trial = [list(c) for c in pick]
                        trial[s][p] = (vid, w)
                        t = total(trial)
                        if t > score + 1e-9 and (best is None or t > best[0]):
                            best = (t, trial)
        if best is None:
            break
        score, pick = best
    # sets of the same size handed their verses by what those hold, the most first; each sings the easier
    # verses first where the rules allow
    worth = []
    for chosen in pick:
        have = Counter()
        for vid, w in chosen:
            have += ways[vid][w][1]
        worth.append(_value(have, want))
    ranked = list(range(len(pick)))
    for size in set(sizes):
        places = [s for s in range(len(pick)) if sizes[s] == size]
        for place, s in zip(places, sorted(places, key=lambda s: -worth[s])):
            ranked[place] = s
    sets = []
    for frame, s in zip(frames, ranked):
        verses = _easy_order(genome, [(vid, ways[vid][w][0]) for vid, w in pick[s]], hardness)
        held = {**frame["words"], "verses": verses}
        why = A.held_problem(genome, frame["form"], held)
        if why:
            raise ValueError(f"set {frame['id']}: {why}")
        sets.append({"id": frame["id"], "form": frame["form"], "words": held})
    return sets


def _easy_order(genome, chosen: list[tuple[str, dict]], hardness: dict[str, float]) -> list[dict]:
    """Some verses (with their slot words) in the order the rules allow that sings the easier ones first."""
    import itertools

    orders = []
    for perm in itertools.permutations(chosen):
        held = [{"id": vid, "slots": slots} for vid, slots in perm]
        if A.verse_problem(genome, held) is None:
            orders.append((tuple(hardness[vid] for vid, _ in perm), held))
    return min(orders, key=lambda o: o[0])[1]


# The sets file, for singers

# What each verse is about, a few words for a set's one line to singers.
SUBJECTS = {
    "carve": "a gravestone", "ink": "a letter in a drawer", "mouth": "a sailor on the quay", "boat": "an emigrant ship",
    "box": "a music box", "parrot": "a parrot", "bell": "the church bells", "wax": "a wax record",
    "trench": "the trenches", "milk": "the milk round", "ship": "a ship's wireless", "hall": "a dance hall",
    "mine": "a mining village", "soap": "a soap advert", "terrace": "the football crowd", "probe": "a space probe",
    "tape": "an old tape", "hold": "hold music", "wire": "the wire", "ring": "a ringtone", "sample": "a sample",
    "screen": "a screen", "wall": "a wall by the railway", "learned": "a machine", "bird": "a songbird",
    "deaf": "a girl who felt it through the floor", "fiddle": "a busker", "kids": "childhood",
    "lullaby": "a lullaby", "mind": "a secret", "names": "a failing memory", "nurse": "a hospital ward",
    "pipe": "a prison wall", "shell": "shelling peas", "shepherd": "a shepherd", "skip": "a skipping rope",
    "tongue": "a lost language", "wakes": "weddings and wakes",
}
EXTRA_ABOUT = {"coat": "the bridge's second verse, the coat", "given": "the bridge's second verse, given"}


def _and_list(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} and {words[-1]}"


def about(genome, form, held: dict) -> str:
    """One plain line for singers: what the set's verses are about, and anything else it sings that the
    song mostly doesn't."""
    song = A._song(genome)
    parts = [_and_list([SUBJECTS.get(v["id"], f"the {v['id']} verse") for v in held["verses"]])]
    heads = [r["head"] for r in held["refrain"]["rounds"] if r["head"] != song.head_id]
    extra = [b["id"] for b in held["bridge"][1:]]
    tail = []
    if SO in heads:
        tail.append("the refrain the artist wrote")
    if len(heads) > (SO in heads):
        tail.append("other ways into the refrain" if len(heads) - (SO in heads) > 1 else "another way into the refrain")
    tail += [EXTRA_ABOUT.get(e, f"the {e} bridge") for e in extra]
    return "Verses about " + parts[0] + ("; " + _and_list(tail) if tail else "")


def sets_file(genome, sets: list[dict]) -> dict:
    """The sets as tools/sets/<song>.json keeps them (the shared contract's section 1)."""
    return {
        "song": SONG.stem,
        "about": ("Recording scripts: each set is the song with verses and refrains of its own, so that between "
                  "them singers sing every part of the song the machine singer finds hardest to say clearly."),
        "made_by": "tools/recording_sets.py",
        "sets": [{"id": s["id"], "name": f"Set {s['id'].upper()}", "about": about(genome, s["form"], s["words"]),
                  "form": list(s["form"]), "words": s["words"]} for s in sets],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("what", choices=("measure", "choose", "report"))
    ap.add_argument("--jobs", type=int, default=5)
    args = ap.parse_args(argv)
    genome = G.load(SONG)
    heard = measure(genome, jobs=args.jobs)
    if args.what == "measure":
        edits = sum(h["edits"] for h in heard)
        words = sum(len(h["words"]) for h in heard)
        print(f"{len(heard)} sung; {edits} edits over {words} words ({edits / max(words, 1):.1%})")
        return 0
    analysis = analyze(genome, heard)
    if args.what == "choose":
        sets = choose(genome, analysis)
        SETS.mkdir(parents=True, exist_ok=True)
        path = SETS / f"{SONG.stem}.json"
        path.write_text(json.dumps(sets_file(genome, sets), indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
