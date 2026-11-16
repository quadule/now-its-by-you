// The score's pure parts (songbird/studio/model.js): the grid, a cell's look, a lock, moving a section, a seam,
// the scope switch, the selection and the keyboard. Run with node --test.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const M = require("../songbird/studio/model.js");

function cell(section, player, level, extra = {}) {
  return { section, player, plays: true, value: { level, pattern: level === "out" ? null : "strum", pattern_label: "strummed", from: 0 },
    program: { level, pattern: "strum", from: 0 }, by: "program", chance: false, locked: false, why: [],
    paths: { level: `arrange.${section}.${player}.level`, pattern: `arrange.${section}.${player}.pattern`,
      from: `arrange.${section}.${player}.from`, fill: `arrange.${section}.${player}.fill` }, problems: [], ...extra };
}
const arrangement = {
  sections: [
    { index: 0, id: "intro:0", name: "intro", label: "Intro", role: "intro", bars: 4, bar_options: [4, 8], start_beat: -0.5, duration_beats: 16, sung: false, can_play: false, choir: false },
    { index: 1, id: "verse:0", name: "verse", label: "Verse 1", role: "verse", bars: 8, bar_options: [8, 16], start_beat: 15.5, duration_beats: 32, sung: true, can_play: true },
    { index: 2, id: "refrain:0", name: "refrain", label: "Refrain 1", role: "refrain", bars: 8, bar_options: [8, 16], start_beat: 47.5, duration_beats: 32, sung: true, can_play: true, choir: true },
  ],
  players: [{ name: "guitar", label: "guitar", family: "plucked", plays: true, patterns: [{ id: "strum", label: "strummed" }] }],
  cells: [cell("intro:0", "guitar", "out"), cell("verse:0", "guitar", "soft", { chance: true }), cell("refrain:0", "guitar", "hard", { by: "you" })],
};
const view = {
  edits: {},
  words: [{ index: 1, lines: ["They saved it as *numbers*"], mine: false }, { index: 2, lines: ["Who *sang* this song?"], mine: true }],
  composition: { beats_per_bar: 4, sections: [{ id: "refrain:0", phrases: [{ harmony: [{ name: "D" }, { name: "G" }], chords_edited: true }] }] },
};
const sound = { boundaries: [{ id: "refrain:0", path: "transition.refrain:0", value: { riser: 2 }, yours: true, before: true }] };

test("the grid: regions on a ruler of bars, the singer first, a cell for every player and section", () => {
  const g = M.grid(arrangement, view, sound);
  assert.deepEqual(g.sections.map((s) => s.startBar), [1, 5, 13]);
  assert.equal(g.bars, 20);
  assert.deepEqual(g.tracks.map((t) => t.id), ["singer", "choir", "chords", "guitar"]);
  assert.equal(g.sections[1].first, "They saved it as numbers");
  assert.equal(g.sections[2].wordsMine, true);
  assert.deepEqual(g.sections[2].chords, ["D", "G"]);
  assert.equal(g.sections[2].choir, true);
  assert.deepEqual(g.sections[2].seam.value, { riser: 2 });
  assert.equal(g.cells.get("guitar|verse:0").value.level, "soft");
});

test("a cell reads its level and whose it is, in words too", () => {
  const g = M.grid(arrangement, view, sound);
  const guitar = g.tracks[3];
  assert.deepEqual(M.look(g.cells.get("guitar|verse:0")), { level: "soft", whose: "program", chance: true, locked: false });
  assert.equal(M.cellLabel(guitar, g.sections[1], g.cells.get("guitar|verse:0")), "guitar in Verse 1: soft, strummed; drawn by chance");
  assert.match(M.cellLabel(guitar, g.sections[2], g.cells.get("guitar|refrain:0")), /hard, strummed; yours$/);
  const locked = cell("verse:0", "guitar", "soft", { by: "you", locked: true, chance: true });
  assert.deepEqual(M.look(locked), { level: "soft", whose: "locked", chance: false, locked: true });
  assert.equal(M.whoseWords(M.look(locked)), "locked by you");
});

test("a lock writes the program's own value (the entrance chance drew among it); a release gives every path back", () => {
  const drawn = cell("verse:0", "guitar", "soft", { chance: true });
  drawn.value.from = 2;
  assert.deepEqual(M.lockPatch(drawn), { "arrange.verse:0.guitar.level": "soft", "arrange.verse:0.guitar.pattern": "strum",
    "arrange.verse:0.guitar.from": 2 });
  assert.deepEqual(M.lockPatch(cell("intro:0", "guitar", "out")), { "arrange.intro:0.guitar.level": "out" });
  assert.deepEqual(Object.values(M.releasePatch(drawn)), [null, null, null, null]);
  assert.deepEqual(M.optionLock({ path: "style.breakdown", value: true }), { "style.breakdown": true });
});

test("everyone in a section at one level is one patch; a level is one of four", () => {
  const cells = arrangement.cells;
  // (the third is the program's own hard already: nothing of yours is kept there)
  assert.deepEqual(Object.values(M.levelPatch(cells, "hard")), ["hard", "hard", null]);
  assert.throws(() => M.levelPatch(cells, "loud"), /out, soft, plays, hard/);
  // the program's own level for a cell releases that cell's choice rather than storing the same value as yours
  const mine = { ...cells[0], by: "you", value: { level: "hard" }, program: { level: "soft" } };
  assert.deepEqual(M.levelPatch([mine], "soft"), { [mine.paths.level]: null });
  assert.deepEqual(M.levelPatch([mine], "plays"), { [mine.paths.level]: "plays" });
});

test("a section moves, but repeated sections keep their story order", () => {
  const s = [{ id: "intro:0", name: "intro" }, { id: "verse:0", name: "verse" }, { id: "refrain:0", name: "refrain" },
    { id: "verse:1", name: "verse" }];
  assert.deepEqual(M.moveOrder(s, 0, 1).order, ["verse:0", "intro:0", "refrain:0", "verse:1"]);
  assert.match(M.moveOrder(s, 3, 0).error, /story order/);
  assert.ok(M.moveOrder(s, 0, 0).error);
});

test("a seam's transitions: toggled, lengthened together, said in words", () => {
  let v = M.seamToggle(null, "riser", 2);
  assert.deepEqual(v, { riser: 2 });
  v = M.seamToggle(v, "impact");
  v = M.seamOver(v, 4);
  assert.deepEqual(v, { riser: 4, impact: true });
  assert.equal(M.seamWords(v), "a riser over 4 bars, an impact on the downbeat");
  assert.equal(M.seamToggle(M.seamToggle(v, "riser"), "impact"), null);
  assert.equal(M.seamWords(null), "nothing: the band goes straight on");
  assert.equal(M.seamWords({ stop: 1 }), "a stop over 1 beat");
  // a sweep that says which way (sound.py's {bars, type}) keeps its way when it is lengthened
  const sweep = { sweep: { bars: 2, type: "lowpass" } };
  assert.equal(M.seamWords(sweep), "a sweep, falling over 2 bars");
  assert.deepEqual(M.seamOver(sweep, 4), { sweep: { bars: 4, type: "lowpass" } });
});

test("a seam's kinds each last their own length: a 4-bar riser with a 1-bar roll (EDM test 2)", () => {
  // two quick clicks, each built on the edit before (the page's latest()), then a length for one kind alone
  let v = M.seamToggle(null, "riser", 2);
  v = M.seamToggle(v, "roll", 2);
  v = M.seamLength(v, "riser", 4);
  v = M.seamLength(v, "roll", 1);
  v = M.seamToggle(v, "impact");
  assert.deepEqual(v, { riser: 4, roll: 1, impact: true });  // sound.py's transition takes each kind's bars
  assert.equal(M.seamWords(v), "a riser over 4 bars, a snare roll over 1 bar, an impact on the downbeat");
  assert.deepEqual(M.seamLengths(v).map((x) => [x.kind, x.bars]), [["riser", 4], ["roll", 1]]);
  assert.deepEqual(M.seamLength({ sweep: { bars: 2, type: "lowpass" } }, "sweep", 1), { sweep: { bars: 1, type: "lowpass" } });
  assert.deepEqual(M.seamLength(v, "sweep", 2), v);  // a kind that's off isn't put on by a length alone here
  assert.equal(M.seamLengths({ stop: 2 })[0].unit, "beat");
});

test("the scope switch: everywhere first, here only, and the last one however many at the last of several", () => {
  const p = { place: "refrain:3.1", place_last: "refrain:last.1", appearances: 4, tune_scope: { from: null }, chords_scope: { from: "last" } };
  const opts = M.scopeOptions(p, { name: "refrain", label: "Refrain 4" });
  assert.deepEqual(opts.map((o) => o.id), ["line", "place", "last"]);
  assert.equal(opts[0].label, "everywhere it's sung (4)");
  assert.equal(opts[2].label, "the last refrain, however many");
  assert.equal(M.scopeStart(p, "tune"), "place");
  assert.equal(M.scopeStart(p, "chords"), "last");
  assert.deepEqual(M.scopeOptions({ place: "intro:0.0", appearances: 1 }, { name: "intro", label: "Intro" }).map((o) => o.id), ["line", "place"]);
  assert.deepEqual(M.scopeOptions({}, {}), []);
});

test("what is selected: a key, what plays it and how", () => {
  assert.equal(M.selectionKey(null), "song");
  assert.equal(M.selectionKey({ kind: "cell", id: "verse:0", player: "guitar" }), "cell:verse:0:guitar");
  assert.throws(() => M.selectionKey({ kind: "wobble" }));
  assert.equal(M.defaultHow(null), "sung");
  assert.equal(M.defaultHow({ kind: "section", id: "verse:0" }), "sketch");
  const g = M.grid(arrangement, view, sound);
  assert.deepEqual(M.playTarget({ kind: "section", id: "refrain:0" }, g.sections), { section: 2, phrase: false });
  assert.deepEqual(M.playTarget({ kind: "note", section: "verse:0" }, g.sections), { section: 1, phrase: true });
  assert.deepEqual(M.playTarget(null, g.sections), { section: null, phrase: null });
  assert.equal(M.neighbour(g.sections, "verse:0", 1).id, "refrain:0");
  assert.equal(M.neighbour(g.sections, "refrain:0", 1).id, "refrain:0");
  assert.deepEqual(M.position(52, g.sections, 4), { id: "refrain:0", label: "Refrain 1", bar: 14 });
});

test("the sketch counts beats from the first pickup, the ruler from bar 1's bar line: one turned into the other", () => {
  const g = M.grid(arrangement, view, sound);  // the ruler's bar 1 at beat -0.5 here
  const sketch = { sections: [{ id: "intro:0", start_beat: 4 }, { id: "verse:0", start_beat: 20 }] };  // a count-in, then bar 1
  assert.equal(M.sketchOffset(g, sketch), 4.5);
  assert.equal(M.sketchOffset(g, null), 0);
  assert.equal(M.sketchFrom(47.5, g, sketch), 52);  // Refrain 1's bar line, in the sketch's beats
  assert.equal(M.sketchFrom(-0.5, g, sketch), null);  // bar 1: the song from its start, its first pickup with it
  assert.equal(M.sketchFrom(null, g, sketch), null);
  // a beat before bar 1 (the first pickup) is bar 1's, not the last section's; one past the end, the last section's
  assert.deepEqual(M.position(-1, g.sections, 4), { id: "intro:0", label: "Intro", bar: 1 });
  assert.equal(M.sectionAtBeat(-1, g.sections).id, "intro:0");
  assert.equal(M.sectionAtBeat(999, g.sections).id, "refrain:0");
  assert.equal(M.sectionAtBeat(0, []), null);
});

test("the keyboard: none fires in a text field; the table's keys", () => {
  const key = (k, o = {}) => M.keyAction({ key: k, target: { tagName: "BODY" }, ...o });
  assert.deepEqual(key(" "), { action: "play", how: "sketch" });
  assert.deepEqual(key(" ", { shiftKey: true }), { action: "play", how: "sung" });
  assert.deepEqual(key("z", { metaKey: true }), { action: "undo" });
  assert.deepEqual(key("z", { ctrlKey: true, shiftKey: true }), { action: "redo" });
  assert.deepEqual(key("2"), { action: "view", view: "arrange" });
  assert.deepEqual(key("4"), { action: "view", view: "sing" });  // the Sing view, where the studio has one
  assert.deepEqual(key("ArrowRight", { metaKey: true }), { action: "move", step: 1 });
  assert.deepEqual(key("ArrowUp"), { action: "step", axis: "track", step: -1 });
  for (const [k, a] of [["k", "click"], ["m", "mute"], ["s", "solo"], ["e", "record"], ["t", "time"], ["?", "help"], ["Enter", "open"], ["Escape", "escape"]]) {
    assert.equal(key(k).action, a);
  assert.equal(key("l"), null);  // no loop: the transport plays what is selected once
  }
  assert.equal(M.keyAction({ key: " ", target: { tagName: "INPUT", type: "text" } }), null);
  assert.equal(M.keyAction({ key: "m", target: { tagName: "TEXTAREA" } }), null);
  assert.deepEqual(M.keyAction({ key: " ", target: { tagName: "INPUT", type: "range" } }), { action: "play", how: "sketch" });
  assert.equal(M.saidCell({ label: "lute" }, { label: "Verse 1" }, "hard"), "Verse 1: the lute now plays hard");
});

test("a moved region is one a person moved, not every one whose place a move shifted (EDM test 2, bug 4)", () => {
  const program = ["intro:0", "verse:0", "refrain:0", "verse:1", "refrain:1", "bridge:0", "refrain:2", "tag:0", "outro:0"];
  const now = ["intro:0", "verse:0", "refrain:0", "refrain:1", "verse:1", "bridge:0", "refrain:2", "tag:0", "outro:0"];
  assert.deepEqual([...M.movedIds(program, now, ["verse:1"])], ["verse:1"]);  // verse 2 dragged after refrain 2
  assert.equal(M.movedIds(program, now).size, 1);  // one of the two, whichever, without the hint
  assert.equal(M.movedIds(program, program).size, 0);
  const far = ["verse:0", "refrain:0", "verse:1", "refrain:1", "bridge:0", "refrain:2", "tag:0", "outro:0", "intro:0"];
  assert.deepEqual([...M.movedIds(program, far)], ["intro:0"]);  // the intro to the end: only it
  assert.equal(M.movedIds(undefined, now).size, 0);  // no order of the person's: nothing moved
});

test("new words can establish their own rhythm without changing the source", () => {
  const phrase = { duration_beats: 8, pickup_beats: 0.5,
    bounds: { min_onset: -0.5, max_end: 8, max_final_onset: 7.25, min_duration: 0.25 },
    notes: [{ degree: 1, onset: -0.5, duration: 1 }, { degree: 8, alter: -1, onset: 0.5, duration: 7 }] };
  const before = JSON.stringify(phrase), fitted = M.fitNotes(phrase, 5);
  assert.equal(fitted.length, 5);
  assert.equal(fitted[0].degree, 1);
  assert.equal(fitted.at(-1).degree, 8);
  assert.equal(fitted.at(-1).alter, -1);
  assert(fitted.every((n, i) => n.duration >= 0.25 && (!i || n.onset >= fitted[i - 1].onset + fitted[i - 1].duration)));
  assert.equal(JSON.stringify(phrase), before);
  assert.throws(() => M.fitNotes(phrase, 33), /32/);
  assert.throws(() => M.fitNotes({ ...phrase, duration_beats: 1, bounds: { ...phrase.bounds, max_end: 1 } }, 20), /more room/);
});

test("phrase contents copy as portable local edits, including rests and inherited-part release", () => {
  const p = { duration_beats: 4, pickup_beats: 0, bounds: { min_onset: 0, max_final_onset: 3.75, min_degree: -12, max_degree: 16 },
    notes: [{ degree: 3, onset: 0, duration: 2 }, { degree: 7, onset: 2, duration: 2 }], lyric_text: "Sing now", chords: [["I"], ["V"]],
    part_notes: { guitar: [[0, 96, 0, 100]], bass: [] } };
  const q = { ...p, own_path: "line.verse:wire.0", place: "verse:0.0", part_key: "verse:0.0", part_notes: { fiddle: [[0, 96, 0, 90]] } };
  const patch = M.phrasePatch(p, q);
  assert.equal(patch['line.verse:wire.0'].words, "Sing now");
  assert.deepEqual(patch['chords.verse:0.0'], [["I"], ["V"]]);
  assert.deepEqual(patch['part.bass.verse:0.0'], []);
  assert.equal(patch['part.fiddle.verse:0.0'], null);
  patch['part.guitar.verse:0.0'][0][0] = 100;
  assert.equal(p.part_notes.guitar[0][0], 0, "the source is immutable");
  assert.throws(() => M.sectionPatch({ phrases: [p] }, { phrases: [q, q] }), /same number/);
});

test("a time of the section's roll belongs to the phrase that can sing a note there: a pickup past a line's last start is the next line's", () => {
  // two four-beat lines, each with a half-beat pickup; a line's last note starts by 3.25 to leave the next one's pickup room
  const spans = [{ off: 0, start: -0.5, end: 4, final: 3.25 }, { off: 4, start: 3.5, end: 8, final: 7.25 }];
  assert.equal(M.phraseAt(spans, -0.5), 0, "the first line's pickup");
  assert.equal(M.phraseAt(spans, 2), 0);
  assert.equal(M.phraseAt(spans, 3.25), 0, "the first line's latest start");
  assert.equal(M.phraseAt(spans, 3.5), 1, "past it, the second line's pickup");
  assert.equal(M.phraseAt(spans, 4), 1);
  assert.equal(M.phraseAt(spans, 8), null);
  assert.equal(M.phraseAt(spans, -1), null);
});

test("a semitone is spelled as the scale writes it: a sharp reached going up, else a flat; a tune line's note keeps to the scale", () => {
  const major = [0, 2, 4, 5, 7, 9, 11], minor = [0, 2, 3, 5, 7, 8, 10];
  assert.deepEqual(M.spell(4, major), { degree: 3, alter: 0 });
  assert.deepEqual(M.spell(6, major, true), { degree: 4, alter: 1 }, "F♯ from F");
  assert.deepEqual(M.spell(6, major, false), { degree: 5, alter: -1 }, "G♭ from G");
  assert.deepEqual(M.spell(-1, major), { degree: 0, alter: 0 }, "the B below the tonic");
  assert.deepEqual(M.spell(-2, major, false), { degree: 0, alter: -1 }, "the B♭ below");
  assert.deepEqual(M.spell(11, minor, false), { degree: 8, alter: -1 }, "the leading tone, falling from the octave");
  assert.deepEqual(M.spell(11, minor, true), { degree: 7, alter: 1 }, "and climbing to it");
  assert.equal(M.semitone(8, -1, minor), 11);
  for (let semi = -14; semi <= 26; semi++) for (const up of [true, false]) {
    const at = M.spell(semi, minor, up);
    assert.equal(M.semitone(at.degree, at.alter, minor), semi, `${semi}`);
  }
  const free = { scale: major, chromatic: true, lo: -3, hi: 10 };
  assert.deepEqual(M.moveRows({ degree: 4 }, 1, free), { degree: 4, alter: 1 });
  assert.deepEqual(M.moveRows({ degree: 4, alter: 1 }, -1, free), { degree: 4, alter: 0 });
  assert.deepEqual(M.moveRows({ degree: 10 }, 5, free), { degree: 10, alter: 0 }, "kept inside the line's range");
  const scaleOnly = { scale: major, chromatic: false, lo: -3, hi: 10 };
  assert.deepEqual(M.moveRows({ degree: 4 }, 1, scaleOnly), { degree: 5, alter: 0 }, "F♯ is passed over to G");
  assert.deepEqual(M.moveRows({ degree: 3 }, 1, scaleOnly), { degree: 4, alter: 0 }, "E to F is a row");
  assert.deepEqual(M.moveRows({ degree: 1 }, -12, scaleOnly), { degree: -3, alter: 0 }, "an octave, held at the range's bottom");
});

test("several notes at once: a move stops at the notes not chosen, a melisma moves and goes whole, a paste takes the place of what it overlaps", () => {
  const b = { min_onset: -0.5, max_end: 4, max_final_onset: 3.5, melisma: 4 };
  const notes = [{ degree: 3, onset: -0.5, duration: 0.5 }, { degree: 4, onset: 0, duration: 0.5 }, { degree: 5, onset: 0.5, duration: 0.5, slur: true },
    { degree: 6, onset: 2, duration: 1 }, { degree: 1, onset: 3, duration: 0.5 }];
  assert.deepEqual(M.withSyllables(notes, [2]), [1, 2], "a slurred note moves with its syllable");
  assert.equal(M.shiftLimit(notes, [1, 2], 2, b, 0.25), 1, "up to the note after");
  assert.equal(M.shiftLimit(notes, [1, 2], -2, b, 0.25), 0, "the note before is in the way");
  assert.equal(M.shiftLimit(notes, [3, 4], 0.6, b, 0.25), 0.5, "the last note keeps the next line's pickup clear");
  assert.equal(M.shiftLimit(notes, [3], 0.3, b, 0.25), 0, "and the next note");
  assert.equal(M.shiftLimit(notes, [3], -0.3, b, 0.25), -0.25, "the anchor on the grid");
  assert.deepEqual(M.deleteNotes(notes, [2]).map((n) => [n.onset, n.duration]), [[-0.5, 0.5], [0, 1], [2, 1], [3, 0.5]], "a slurred note alone joins the one before");
  assert.deepEqual(M.deleteNotes(notes, [1, 4]).map((n) => n.onset), [-0.5, 2], "a syllable goes with its melisma");
  const clip = M.clipOf(notes, [2, 3]);
  assert.deepEqual(clip.notes.map((n) => !!n.slur), [false, false], "a slurred note copied without its own sings its own syllable");
  assert.equal(clip.start, 0.5);
  const { notes: put, added } = M.pasteAt(notes, M.clipOf(notes, [1, 2]), 2, b);
  assert.deepEqual(put.map((n) => [n.degree, n.onset, !!n.slur]), [[3, -0.5, false], [4, 0, false], [5, 0.5, true], [4, 2, false], [5, 2.5, true], [1, 3, false]]);
  assert.deepEqual(added, [3, 4]);
  assert.throws(() => M.pasteAt(notes, M.clipOf(notes, [3]), 3.5, b), /fit here/);
  assert.throws(() => M.pasteAt(notes, { start: 0, notes: [{ degree: 1, onset: 0, duration: 0.25 }] }, 3.75, b), /pickup/);
  const field = { tagName: "INPUT", type: "text" };
  assert.deepEqual(M.rollKey({ key: "c", ctrlKey: true, target: {} }), { action: "copy" });
  assert.deepEqual(M.rollKey({ key: "D", metaKey: true, target: {} }), { action: "duplicate" });
  assert.equal(M.rollKey({ key: "c", ctrlKey: true, target: field }), null);
  assert.equal(M.rollKey({ key: "z", ctrlKey: true, target: {} }), null, "undo is the page's");
  assert.equal(M.rollKey({ key: "c", target: {} }), null);
});

test("a lyric sheet: paragraphs onto the song's sections of words in order, brackets naming them, lines too many refused", () => {
  const p = (path, text, count = 3) => ({ lyric_path: path, own_path: path.replace("lyrics", "line"), lyric_text: text, syllable_count: count,
    duration_beats: 4, pickup_beats: 0, bounds: { min_onset: 0, max_end: 4, max_final_onset: 3.5, min_duration: 0.25 },
    notes: Array.from({ length: count }, (_, k) => ({ degree: k + 1, onset: k, duration: 1 })) });
  const composition = { sections: [{ id: "intro:0", sung: false, phrases: [{}] },
    { id: "verse:0", lyric_key: "verse:0", label: "Verse 1", sung: true, phrases: [p("lyrics.verse:0.0", "one two three"), p("lyrics.verse:0.1", "four five six")] },
    { id: "refrain:0", lyric_key: "refrain", label: "Refrain", sung: true, phrases: [p("lyrics.refrain.0", "la la la")] },
    { id: "refrain:1", lyric_key: "refrain", label: "Refrain 2", sung: true, phrases: [p("lyrics.refrain.0", "la la la")] }] };
  const targets = M.lyricTargets(composition);
  assert.deepEqual(targets.map((t) => t.label), ["Verse 1", "Refrain"]);
  assert.equal(M.lyricSheet(targets), "[Verse 1]\none two three\nfour five six\n\n[Refrain]\nla la la");
  const blocks = M.parseLyricSheet("[Verse 1]\n one two three \n\n\n  \nseven eight nine ten\n[Refrain]\nla la la");
  assert.deepEqual(blocks.map((b) => [b.label, b.lines.map((l) => l.text)]), [["Verse 1", ["one two three"]], [null, ["seven eight nine ten"]], ["Refrain", ["la la la"]]]);
  const count = (t) => t.trim().split(/[\s-]+/).length;
  const two = M.lyricSheetPatch(targets, M.parseLyricSheet("one two three\nfour five six seven\n\nla la la"), count);
  assert.deepEqual(two.errors, []);
  assert.deepEqual(Object.keys(two.patch), ["line.verse:0.1"], "unchanged lines are no edit");
  assert.equal(two.patch["line.verse:0.1"].notes.length, 4);
  assert.equal(two.lines[1].fitted, true);
  const many = M.lyricSheetPatch(targets, M.parseLyricSheet("a b c\nd e f\ng h i"), count);
  assert.match(many.errors[0].message, /Verse 1 has 2 lines; this paragraph has 3/);
  const long = M.lyricSheetPatch(targets, M.parseLyricSheet(Array(20).fill("la").join(" ")), count);
  assert.match(long.errors[0].message, /Verse 1, line 1: These words need more room/);
});

test("quantize puts the chosen notes' starts and ends on the grid, keeping a melisma joined and the next line's pickup clear", () => {
  const b = { min_onset: -0.5, max_end: 4, max_final_onset: 3.5, min_duration: 0.25 };
  const notes = [{ degree: 1, onset: -1 / 3, duration: 1 / 3 }, { degree: 2, onset: 0.1, duration: 0.6 }, { degree: 3, onset: 0.7, duration: 0.55, slur: true },
    { degree: 4, onset: 1.4, duration: 1.2 }, { degree: 5, onset: 3.4, duration: 0.6 }];
  const q = M.quantizeNotes(notes, [0, 1, 2, 3, 4], 0.5, b);
  assert.deepEqual(q.map((n) => [n.onset, n.duration]), [[-0.5, 0.5], [0, 0.5], [0.5, 1], [1.5, 1], [3.5, 0.5]]);
  assert.equal(q[2].slur, true);
  assert.deepEqual(M.quantizeNotes(notes, [3], 1, b).map((n) => [n.onset, n.duration]).slice(3), [[1, 2], [3.4, 0.6]], "only the chosen; the others as they were");
  assert.throws(() => M.quantizeNotes(notes, [4], 0.5, { ...b, max_final_onset: 3.4 }), /finer snap/, "the last note past the next line's pickup");
});

test("a roll's scale: Fit puts the span in the width; a zoom starts where an eighth note's syllable can be read", () => {
  assert.equal(M.rollUnit("fit", 900, 64), 14.0625, "a long section, whole in the width");
  assert.equal(M.rollUnit("fit", 900, 300), 12, "never narrower than 12 a beat");
  assert.equal(M.rollUnit(1, 900, 64), M.ROLL_BEAT, "100%: an eighth note 32 pixels wide, the roll scrolling");
  assert.equal(M.rollUnit(2, 900, 64), 2 * M.ROLL_BEAT);
  assert.equal(M.rollUnit(1, 900, 4.5), 200, "a short section is as wide as the width at 100%");
  assert.equal(M.zoomOf("fit"), "fit");
  assert.equal(M.zoomOf("1.5"), 1.5);
});

test("a note's resize handle is a quarter of it, 4 to 9 pixels, and none on a narrow note; a label is drawn whole or not at all", () => {
  assert.equal(M.grip(12), 0);
  assert.equal(M.grip(19), 0);
  assert.equal(M.grip(21), 5, "an eighth note at the old fit: its middle moves it");
  assert.equal(M.grip(40), 9);
  assert.equal(M.grip(200), 9);
  assert.equal(M.labelFits("su", 21), true);
  assert.equal(M.labelFits("sunlight", 21), false);
  assert.equal(M.labelFits("", 100), false);
});

test("triplet snaps: ⅓ for a melody, ⅙ too for an instrument; thirds kept exact; a six feel opens on ⅓", () => {
  assert.deepEqual(M.SNAPS.map(([, n]) => n), ["¼", "⅓", "½", "1"]);
  assert.deepEqual(M.PART_SNAPS.map(([, n]) => n), ["⅙", "¼", "⅓", "½", "1"]);
  assert.equal(M.onGrid(0.34, 1 / 3), 1 / 3);
  assert.equal(M.onGrid(0.65, 1 / 3), 2 / 3);
  assert.equal(M.onGrid(0.65, 1 / 3) + 1 / 3, 1, "two thirds and a third meet a beat exactly");
  assert.equal(M.onGrid(0.3, 0.25), 0.25);
  const six = [-1 / 3, 1 / 3, 0, 1 / 3, 1 / 3, 2 / 3, 1, 1 / 3];
  assert.equal(M.feelSnap(six, 0.25), 1 / 3);
  assert.equal(M.feelSnap(six, 1 / 6), 1 / 6, "a snap of thirds already is kept");
  assert.equal(M.feelSnap([0, 0.5, 0.5, 0.5, 1, 1], 0.25), 0.25, "a straight tune keeps the snap");
  assert.equal(M.feelSnap([0, 1, 1, 1], 0.25), 0.25, "whole beats are no six feel");
  assert.equal(M.feelSnap([0, 1 / 3], 1 / 3), 1 / 3);
  assert.equal(M.snapFor(1 / 6, M.SNAPS), 0.25, "no ⅙ for the melody: the nearest");
  assert.equal(M.snapFor(1 / 3, M.SNAPS), 1 / 3);
});

// ------------------------------------------------------------------ clips (docs/notes/STUDIO-CLIPS.md, "For the editor")
const BOUNDS = { instances: 48, clips: 48, lines: 16, line_bars: 8, clip_bars: 64, song_bars: 768, label: 24 };
const blank = { id: "break104", source: null, bars: 4, instances: [3], lines: [{ phrase: "break104-0", of: null, bars: 2 }, { phrase: "break104-1", of: null, bars: 2 }] };
const sourced = { id: "verse102", source: "verse:0", bars: 8, instances: [1, 4], lines: [{ phrase: "v1", of: 0, bars: 4 }, { phrase: "v2", of: 1, bars: 4 }] };
const CLIPS = { stored: true, bounds: BOUNDS, clips: [sourced, blank], value: { form: ["intro", "verse", "refrain"], order: ["intro101", "verse102", "refrain103", "break104", "verse102"] } };

test("a blank section's lengths are its lines': two lines of 1 to 8 bars, the song in bounds", () => {
  assert.deepEqual(M.clipLengths(blank, CLIPS).map((x) => [x.bars, x.disabled]), [[2, false], [4, false], [8, false], [16, false]]);
  const one = { ...blank, lines: [blank.lines[0]], bars: 2 };
  assert.deepEqual(M.clipLengths(one, CLIPS).map((x) => [x.bars, x.why]), [[2, null], [4, null], [8, null], [16, "One line is 8 bars at most."]]);
  const four = { ...blank, lines: [...blank.lines, ...blank.lines], bars: 8 };
  assert.equal(M.clipLengths(four, CLIPS)[0].why, "4 lines are 4 bars at least.");
  const full = { ...CLIPS, clips: [{ ...sourced, bars: 760, instances: [0] }, blank] };
  assert.equal(M.clipLengths(blank, full).find((x) => x.bars === 8).why, null);
  assert.equal(M.clipLengths(blank, full).find((x) => x.bars === 16).why, "A song is 768 bars at most.");
  assert.deepEqual(M.evenBars(7, 3), [3, 2, 2]);
  assert.deepEqual(M.evenBars(8, 4), [2, 2, 2, 2]);
});

test("a section's lines: a blank line added or the last taken away, a blank line's bars; a line of its tune stays its own", () => {
  assert.deepEqual(M.clipLines(sourced, CLIPS, { add: 2 }), { lines: [{ of: 0 }, { of: 1 }, { bars: 2 }] });
  assert.deepEqual(M.clipLines(sourced, CLIPS, { remove: true }), { lines: [{ of: 0 }] });
  assert.deepEqual(M.clipLines(blank, CLIPS, { line: 1, bars: 5 }), { lines: [{ bars: 2 }, { bars: 5 }] });
  assert.equal(M.clipLines(sourced, CLIPS, { line: 0, bars: 2 }).error, "This line is as long as its tune.");
  assert.equal(M.clipLines(blank, CLIPS, { line: 0, bars: 9 }).error, "A line is 1 to 8 bars.");
  assert.equal(M.clipLines({ ...blank, lines: [blank.lines[0]] }, CLIPS, { remove: true }).error, "A section needs one line.");
  const sixteen = { ...blank, lines: Array(16).fill(blank.lines[0]) };
  assert.equal(M.clipLines(sixteen, CLIPS, { add: 2 }).error, "A section has 16 lines at most.");
  const long = { ...blank, lines: Array(8).fill({ of: null, bars: 8 }) };
  assert.equal(M.clipLines(long, CLIPS, { add: 1 }).error, "A section is 64 bars at most.");
});

test("instances in the clips' order, and what an operation leaves selected", () => {
  assert.deepEqual(M.instanceIds(CLIPS.value.order), ["intro101:0", "verse102:0", "refrain103:0", "break104:0", "verse102:1"]);
  const order = ["intro101", "verse102", "verse105", "refrain103"];
  assert.equal(M.selectedAfter({ op: "duplicate", at: 2 }, { edits: { clips: { order } }, clip: "verse105" }), "verse105:0");
  assert.equal(M.selectedAfter({ op: "move", from: 3, to: 0 }, { edits: { clips: { order: ["refrain103", "intro101", "verse102", "verse102"] } } }), "refrain103:0");
  assert.equal(M.selectedAfter({ op: "repeat", at: 3 }, { edits: { clips: { order: ["intro101", "verse102", "refrain103", "verse102"] } } }), "verse102:1");
  assert.equal(M.selectedAfter({ op: "delete", at: 2 }, { edits: { clips: { order: ["intro101", "verse102"] } } }), "verse102:0");
  assert.deepEqual(M.moveOp([1, 2, 3], 0, 2), { op: { op: "move", from: 0, to: 2 } });
  assert.equal(M.moveOp([1, 2, 3], 0, 3).error, "It is already there.");
});

test("the grid knows each section's clip: a linked repeat's mark, a blank one's length, a person's own", () => {
  const arr = { sections: ["intro101:0", "verse102:0", "refrain103:0", "break104:0", "verse102:1"].map((id, index) => ({ index, id, name: id.split(":")[0], label: id, bars: 4, bar_options: [4], start_beat: index * 16, duration_beats: 16 })), players: [], cells: [] };
  const clips = { ...CLIPS, clips: [{ id: "intro101", source: "intro:0", instances: [0], bars: 4, lines: [] }, sourced, { id: "refrain103", source: "refrain:0", instances: [2], bars: 4, lines: [] }, blank] };
  const g = M.grid(arr, { composition: { clips } }, null);
  assert.deepEqual(g.sections.map((s) => [s.clip, s.instance, s.link, s.blank]), [["intro101", 0, null, false], ["verse102", 0, 0, false], ["refrain103", 0, null, false], ["break104", 0, null, true], ["verse102", 1, 0, false]]);
  assert.deepEqual(g.sections[3].barOptions, [2, 4, 8, 16]);
  assert.deepEqual(g.sections.map((s) => s.clipMine), [false, false, false, true, true]);  // a blank one, a repeat
  const unstored = M.grid(arr, { composition: { clips: { ...clips, stored: false } } }, null);
  assert.ok(unstored.sections.every((s) => !s.clipMine));
});

test("a cell opens its track's editor; the Part menu's choice is a row; a section's own keys; ▶ plays a cell's section", () => {
  const players = [{ name: "fiddle" }, { name: "drum", drums: true }];
  assert.deepEqual(M.cellEditor({ kind: "singer" }, players), { player: "voice" });
  assert.deepEqual(M.cellEditor({ kind: "chords" }, players), { player: "voice", chords: true });
  assert.deepEqual(M.cellEditor({ kind: "player", id: "drum" }, players), { player: "drum" });
  assert.equal(M.cellEditor({ kind: "player", id: "pad" }, players), null);
  assert.equal(M.cellEditor({ kind: "choir" }, players), null);
  const tracks = [{ id: "singer", kind: "singer" }, { id: "fiddle", kind: "player" }];
  assert.equal(M.rowOfPart("voice", tracks).id, "singer");
  assert.equal(M.rowOfPart("fiddle", tracks).id, "fiddle");
  const key = (k, o = {}) => M.keyAction({ key: k, target: { tagName: "BUTTON" }, ...o });
  assert.deepEqual(key("d", { ctrlKey: true }), { action: "duplicate" });
  assert.deepEqual(key("Delete"), { action: "delete" });
  assert.deepEqual(key("Backspace"), { action: "delete" });
  assert.equal(M.keyAction({ key: "Backspace", target: { tagName: "INPUT", type: "text" } }), null);
  const g = M.grid(arrangement, view, sound);
  assert.deepEqual(M.playTarget({ kind: "cell", id: "verse:0", player: "guitar" }, g.sections), { section: 1, phrase: false });
});
