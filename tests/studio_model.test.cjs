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
