"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm"), fs = require("node:fs"), path = require("node:path");
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../songbird/studio/drums.js"), "utf8"), { window });
const { LEVELS, levelOf, bounds, stepOf, columns, cellOf, hitsAt, setCell, setVelocity, setLength, normalize, fit, sectionColumns, voice } = window.SongbirdDrums.core;
const clone = (x) => JSON.parse(JSON.stringify(x));

test("the grid's columns are the snap's steps from the bar line, the pickup's start included", () => {
  const b = bounds({ pickup_beats: 0.5, duration_beats: 4 });
  assert.deepEqual(clone(b), { start: -48, end: 384 });
  assert.deepEqual(clone(columns(b, 0.25)), [-48, -24, 0, 24, 48, 72, 96, 120, 144, 168, 192, 216, 240, 264, 288, 312, 336, 360]);
  assert.deepEqual(clone(columns(b, 1)), [-48, 0, 96, 192, 288], "a pickup shorter than a step keeps a column");
  assert.deepEqual(clone(columns(bounds({ duration_beats: 2 }), 0.5)), [0, 48, 96, 144]);
  assert.equal(stepOf(0.25), 24);
});
test("a stroke shows in its nearest column, a little early or late", () => {
  const cols = columns({ start: 0, end: 384 }, 0.25);
  assert.equal(cellOf(0, cols), 0);
  assert.equal(cellOf(-2, cols), 0);
  assert.equal(cellOf(26, cols), 1);
  assert.equal(cellOf(383, cols), 15);
  const notes = [[0, 24, 0, 90], [97, 24, 1, 90], [96, 24, 0, 90]];
  assert.deepEqual(clone(hitsAt(notes, cols, 0, 4)), [2]);
  assert.deepEqual(clone(hitsAt(notes, cols, 1, 4)), [1]);
});
test("a cell is struck at its onset and cleared of what shows there, the source untouched", () => {
  const cols = columns({ start: -48, end: 384 }, 0.5), notes = [[2, 48, 3, 70]];
  const struck = setCell(notes, cols, 0, 0, true, 48, 90);
  assert.deepEqual(clone(struck), [[2, 48, 3, 70], [-48, 48, 0, 90]]);
  assert.equal(setCell(struck, cols, 0, 0, true, 48, 120), struck, "striking a struck cell changes nothing");
  assert.deepEqual(clone(setCell(struck, cols, 3, 1, false, 48, 0)), [[-48, 48, 0, 90]], "the early stroke on the bar line clears");
  assert.equal(setCell(notes, cols, 5, 3, false, 48, 0), notes, "clearing an empty cell changes nothing");
  assert.deepEqual(clone(notes), [[2, 48, 3, 70]]);
});
test("velocity levels: ghost, normal, accent; a stroke's own velocity reads as the nearest", () => {
  assert.deepEqual(clone(LEVELS.map((l) => l.velocity)), [40, 90, 120]);
  assert.deepEqual([1, 40, 60, 61, 90, 109, 110, 127].map(levelOf), [0, 0, 0, 1, 1, 1, 2, 2]);
  assert.ok(LEVELS.every((l, k) => levelOf(l.velocity) === k));
  assert.deepEqual(clone(setVelocity([[0, 24, 0, 90], [0, 24, 1, 90]], [1], 120)), [[0, 24, 0, 90], [0, 24, 1, 120]]);
  assert.deepEqual(clone(setLength([[0, 24, 0, 90]], [0], 0)), [[0, 1, 0, 90]]);
  assert.deepEqual(clone(setLength([[0, 24, 0, 90]], [0], 99999)), [[0, 3072, 0, 90]]);
});
test("strokes are checked as the studio checks them", () => {
  const b = { start: -48, end: 384 };
  assert.deepEqual(clone(normalize([[96, 24, 1, 80], [0, 24, 0, 64], [0, 48, 0, 90], [0, 24, 4, 90]], 5, b)),
    [[0, 48, 0, 90], [0, 24, 4, 90], [96, 24, 1, 80]], "sorted; a piece struck twice at once kept once, the longest");
  assert.deepEqual(clone(normalize(Array.from({ length: 15 }, (_, k) => [0, 24, k, 90]), 15, b)).length, 15, "any number at once");
  assert.throws(() => normalize([[0, 24, 5, 90]], 5, b), /inside/);
  assert.throws(() => normalize([[-49, 24, 0, 90]], 5, b), /inside/);
  assert.throws(() => normalize([[384, 24, 0, 90]], 5, b), /inside/);
  assert.throws(() => normalize([[0, 0, 0, 90]], 5, b), /inside/);
  assert.throws(() => normalize([[0, 24, 0, 128]], 5, b), /inside/);
  assert.throws(() => normalize([[0.5, 24, 0, 90]], 5, b), /inside/);
  assert.throws(() => normalize([[0, 24, 0]], 5, b), /inside/);
  assert.throws(() => normalize(Array.from({ length: 33 }, (_, k) => [k, 1, 0, 90]), 5, b), /32 strokes in a beat/);
  assert.throws(() => normalize(Array.from({ length: 513 }, (_, k) => [k % 384, 1, k % 5, 90]), 5, b), /512/);
  assert.deepEqual(clone(normalize([], 5, b)), [], "a rest");
});
test("a paste keeps the strokes that fit the phrase and the player", () => {
  const notes = [[-48, 24, 0, 90], [0, 24, 6, 90], [500, 24, 1, 90], [96, 24, 1, 70]];
  assert.deepEqual(clone(fit(notes, 5, { start: 0, end: 384 })), [[96, 24, 1, 70]]);
});
test("every piece has a sketch sound", () => {
  for (const name of ["kick", "snare", "rim", "hat", "hat-open", "crash", "tom-lo", "brush-sweep", "bass", "tip", "clap", "cajon-slap", "tambourine-shake"])
    assert.ok(["low", "noise", "snare"].includes(voice(name).kind), name);
  assert.equal(voice("kick").kind, "low");
  assert.equal(voice("hat").kind, "noise");
});

test("a section's columns: its phrases end to end, each from its pickup to where the next one's begins", () => {
  const lines = [{ off: 0, bounds: { start: -48, end: 384 } }, { off: 4, bounds: { start: -48, end: 384 } }];
  const { local, cols } = sectionColumns(lines, 1);
  assert.deepEqual(clone(local), [[-48, 0, 96, 192, 288], [-48, 0, 96, 192, 288]], "the first phrase stops where the second's pickup begins");
  assert.deepEqual(clone(cols.map((c) => [c.pi, c.k, c.at])), [[0, 0, -0.5], [0, 1, 0], [0, 2, 1], [0, 3, 2], [0, 4, 3],
    [1, 0, 3.5], [1, 1, 4], [1, 2, 5], [1, 3, 6], [1, 4, 7]]);
});

// ---- the editor on a small DOM double: what it draws and the edits it makes
class Node {}
class Text extends Node { constructor(text) { super(); this.textContent = text; this.children = []; } }
class Element extends Node {
  constructor(tag) {
    super(); this.tagName = tag; this.children = []; this.attrs = {}; this.style = {}; this.listeners = {}; this.dataset = {};
    this.className = ""; this.classes = new Set();
    this.classList = { toggle: (c, on) => (on ? this.classes.add(c) : this.classes.delete(c)) };
  }
  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-([a-z])/g, (_, l) => l.toUpperCase())] = String(v);
  }
  set className(v) { this._class = v; this.classes = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get className() { return [...(this.classes || [])].join(" "); }
  append(...nodes) { for (const n of nodes) { this.children.push(n); n.parent = this; } }
  addEventListener(k, f) { (this.listeners[k] ||= []).push(f); }
  removeEventListener(k, f) { this.listeners[k] = (this.listeners[k] || []).filter((x) => x !== f); }
  fire(k, e = {}) { for (const f of this.listeners[k] || []) f({ button: 0, preventDefault() {}, stopPropagation() {}, currentTarget: this, ...e }); }
  get textContent() { return this.children.map((c) => c.textContent ?? "").join(""); }
  closest(selector) {
    const fits = (at) => (selector === "[data-drum-cell]" ? at.dataset?.drumCell !== undefined : at.classes?.has(selector.slice(1)));
    let at = this; while (at && !fits(at)) at = at.parent; return at || null;
  }
  contains(node) { for (let at = node; at; at = at.parent) if (at === this) return true; return false; }
  setPointerCapture() { throw Object.assign(new Error("InvalidStateError"), { name: "InvalidStateError" }); }
  hasPointerCapture() { return false; }
  focus() {}
  all(test, out = []) { if (test(this)) out.push(this); for (const c of this.children) if (c instanceof Element) c.all(test, out); return out; }
}
// a section of two phrases of the frame drum, 8 beats each from a half-beat pickup, and one the arrangement added
function editor(saved, more = []) {
  const edits = [], win = {}, doc = {
    createElement: (t) => new Element(t), createTextNode: (t) => new Text(t),
    getElementById: () => ({ clientWidth: 900 }), querySelector: () => null,
  };
  win.StudioBridge = { getEdits: () => ({}), setEdit: (p, v, label) => edits.push([p, v, label]), releaseEdit: (p) => edits.push([p, null]),
    setEdits: (patch, label) => edits.push([patch, label]) };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../songbird/studio/model.js"), "utf8"), { window: win });
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../songbird/studio/drums.js"), "utf8"), { window: win, document: doc, Node, fetch: () => new Promise(() => {}) });
  doc.elementFromPoint = (x, y) => box.all((e) => e.dataset.drumCell === `${y}:${x}`)[0] || null;
  const player = { name: "drum", label: "Drum", poly: true, drums: ["bass", "tip", "mute", "rim", "top"].map((name, index) => ({ index, name, label: name })) };
  const view = { composition: { players: [player], beats_per_bar: 4 } };
  const phrase = (k, notes) => ({ part_key: `verse:0.${k}`, pickup_beats: 0.5, duration_beats: 8, start_beat: 0.5 + 8 * k, part_editable: true,
    part_notes: notes === undefined ? {} : { drum: notes } });
  const section = { id: "verse:0", start_beat: 0.5, phrases: [phrase(0, saved), phrase(1, more[0] ?? saved), ...more.slice(1).map(() => ({ ...phrase(2), part_editable: false, part_key: "verse:0.2" }))] };
  const heard = [];
  let box;
  const options = { snap: 0.25, zoom: 1, phrase: 0, hear: (n) => heard.push(n), choose: (p) => { options.phrase = section.phrases.indexOf(p); },
    paint: () => { box = win.SongbirdDrums.render(view, section, "drum", options); } };
  options.paint();
  const cells = () => box.all((e) => e.dataset.drumCell !== undefined);
  return { edits, heard, options, box: () => box, cells, cell: (id) => cells().find((c) => c.dataset.drumCell === id),
    button: (text) => box.all((e) => e.tagName === "button" && e.textContent === text)[0] };
}
test("the grid spans the section: a row a piece, a column a step, each phrase from its pickup, the second where its pickup begins", () => {
  const ed = editor([[0, 24, 0, 100], [96, 96, 4, 40]]);
  const cells = ed.cells();
  assert.equal(cells.length, 5 * (8 * 4 + 2 + 8 * 4), "the first phrase's pickup, then 32 steps each, the first's last step under the second's pickup");
  const hit = cells.filter((c) => c.classes.has("is-hit")).map((c) => c.dataset.drumCell);
  assert.deepEqual(hit, ["0:2", "0:34", "4:6", "4:38"], "each phrase's own strokes in its own time");
  assert.ok(ed.cell("4:6").classes.has("is-ghost"));
  assert.ok(ed.cell("0:2").classes.has("is-bar"));
  assert.ok(ed.cell("0:34").classes.has("is-bar") && ed.cell("0:32").classes.has("is-phrase"), "bar 3 is the second phrase's first; its pickup starts the phrase");
  assert.match(ed.cell("0:34").attrs["aria-label"], /phrase 2, beat 1,/);
  assert.equal(cells.filter((c) => c.attrs.tabindex === "0").length, 1, "one cell in the tab order");
});
test("keys strike, clear and set a level, each phrase its own edit; nothing changed writes nothing", () => {
  const ed = editor([[0, 24, 0, 100]]);
  ed.cell("0:2").fire("keydown", { key: "Enter" });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [], "Clear a stroke"]);
  ed.cell("0:2").fire("keydown", { key: " " });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[0, 24, 0, 90]], "Strike a drum"]);
  ed.cell("0:2").fire("keydown", { key: "ArrowUp", shiftKey: true });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[0, 24, 0, 120]], "Change a stroke's level"]);
  ed.cell("0:2").fire("keydown", { key: "ArrowRight", shiftKey: true });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[0, 48, 0, 120]], "Change a stroke's length"]);
  ed.cell("1:35").fire("keydown", { key: " " });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.1", [[0, 24, 0, 100], [24, 24, 1, 120]], "Strike a drum"], "the second phrase's own");
  assert.equal(ed.options.phrase, 0, "the keys alone don't choose a phrase; a move does");
  ed.cell("1:35").fire("keydown", { key: "ArrowRight" });
  assert.equal(ed.options.phrase, 1, "the focus in the second phrase: the strip follows");
  const count = ed.edits.length;
  ed.cell("0:2").fire("keydown", { key: "ArrowUp", shiftKey: true });  // already accented
  ed.cell("1:5").fire("keydown", { key: "Delete" });  // already empty
  assert.equal(ed.edits.length, count);
  ed.button("Hear phrase").fire("click");
  assert.deepEqual(clone(ed.heard.at(-1)), [[0, 24, 0, 100], [24, 24, 1, 120]]);
});
test("a click strikes a cell, a drag across two phrases is one undo step, and a pointer that can't be captured still paints", () => {
  const ed = editor([]);
  ed.cell("2:0").fire("pointerdown", { pointerType: "touch" });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[-48, 24, 2, 90]], "Strike a drum"]);
  const grid = ed.box().all((e) => e.classes.has("sbc-drum-grid"))[0];
  ed.cell("3:31").fire("pointerdown", { pointerType: "mouse", pointerId: 1 });  // setPointerCapture throws: guarded
  for (const x of [32, 33]) grid.fire("pointermove", { clientX: x, clientY: 3 });  // (the double's point: column, row)
  grid.fire("pointerup", { pointerId: 1 });
  assert.deepEqual(clone(ed.edits.at(-1)), [{ "part.drum.verse:0.0": [[-48, 24, 2, 90], [696, 24, 3, 90]],
    "part.drum.verse:0.1": [[-48, 24, 3, 90], [-24, 24, 3, 90]] }, "Strike a drum"], "both phrases' edits, one step");
  ed.button("Reset part").fire("click");
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.1", null], "the phrase the drag ended in");
});
test("a phrase not loaded yet: the part loads first, then Start empty rests every unloaded phrase in one step", () => {
  const fresh = editor(undefined);
  assert.equal(fresh.cells().length, 0);
  assert.match(fresh.box().textContent, /Loading the part/);
  fresh.button("Start empty").fire("click");
  assert.deepEqual(clone(fresh.edits), [[{ "part.drum.verse:0.0": [], "part.drum.verse:0.1": [] }, "Start empty"]]);
});
test("a phrase the arrangement added is drawn but can't be written", () => {
  const ed = editor([], [[], "added"]);
  const locked = ed.cells().filter((c) => c.classes.has("is-locked"));
  assert.ok(locked.length > 0);
  assert.match(locked[0].attrs["aria-label"], /can't be written/);
  const count = ed.edits.length;
  locked[0].fire("pointerdown", { pointerType: "touch" });
  locked[0].fire("keydown", { key: " " });
  assert.equal(ed.edits.length, count);
});
