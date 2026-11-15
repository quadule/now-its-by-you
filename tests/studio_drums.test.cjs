"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm"), fs = require("node:fs"), path = require("node:path");
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../songbird/studio/drums.js"), "utf8"), { window });
const { LEVELS, levelOf, bounds, stepOf, columns, cellOf, hitsAt, setCell, setVelocity, setLength, normalize, fit, voice } = window.SongbirdDrums.core;
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
  append(...nodes) { for (const n of nodes) this.children.push(n); }
  addEventListener(k, f) { (this.listeners[k] ||= []).push(f); }
  removeEventListener() {}
  fire(k, e = {}) { for (const f of this.listeners[k] || []) f({ button: 0, preventDefault() {}, stopPropagation() {}, currentTarget: this, ...e }); }
  get textContent() { return this.children.map((c) => c.textContent ?? "").join(""); }
  closest() { return null; }
  focus() {}
  all(test, out = []) { if (test(this)) out.push(this); for (const c of this.children) if (c instanceof Element) c.all(test, out); return out; }
}
function editor(saved) {
  const edits = [], win = {}, doc = {
    createElement: (t) => new Element(t), createTextNode: (t) => new Text(t),
    getElementById: () => ({ clientWidth: 900 }), querySelector: () => null,
  };
  win.StudioBridge = { getEdits: () => ({}), setEdit: (p, v) => edits.push([p, v]), releaseEdit: (p) => edits.push([p, null]) };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../songbird/studio/drums.js"), "utf8"), { window: win, document: doc, Node, fetch: () => new Promise(() => {}) });
  const player = { name: "drum", label: "Drum", poly: true, drums: ["bass", "tip", "mute", "rim", "top"].map((name, index) => ({ index, name, label: name })) };
  const view = { composition: { players: [player], beats_per_bar: 4 } };
  const p = { part_key: "verse:0.0", pickup_beats: 0.5, duration_beats: 8, start_beat: 0.5, part_editable: true, part_notes: saved === undefined ? {} : { drum: saved } };
  const heard = [];
  let box;
  const options = { snap: 0.25, zoom: 1, hear: (n) => heard.push(n), paint: () => { box = win.SongbirdDrums.render(view, p, "drum", options); } };
  options.paint();
  return { edits, heard, box: () => box, cells: () => box.all((e) => e.dataset.drumCell !== undefined), button: (text) => box.all((e) => e.tagName === "button" && e.textContent === text)[0] };
}
test("the grid draws a row a piece and a column a step, the pickup included", () => {
  const ed = editor([[0, 24, 0, 100], [96, 96, 4, 40]]);
  const cells = ed.cells();
  assert.equal(cells.length, 5 * (8 * 4 + 2));
  const hit = cells.filter((c) => c.classes.has("is-hit")).map((c) => c.dataset.drumCell);
  assert.deepEqual(hit, ["0:2", "4:6"]);
  assert.ok(cells.find((c) => c.dataset.drumCell === "4:6").classes.has("is-ghost"));
  assert.ok(cells.find((c) => c.dataset.drumCell === "0:2").classes.has("is-bar"));
  assert.equal(cells.filter((c) => c.attrs.tabindex === "0").length, 1, "one cell in the tab order");
});
test("keys strike, clear and set a level; nothing changed writes nothing", () => {
  const ed = editor([[0, 24, 0, 100]]);
  const cell = (id) => ed.cells().find((c) => c.dataset.drumCell === id);
  cell("0:2").fire("keydown", { key: "Enter" });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", []]);
  cell("0:2").fire("keydown", { key: " " });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[0, 24, 0, 90]]]);
  cell("0:2").fire("keydown", { key: "ArrowUp", shiftKey: true });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[0, 24, 0, 120]]]);
  cell("0:2").fire("keydown", { key: "ArrowRight", shiftKey: true });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[0, 48, 0, 120]]]);
  const count = ed.edits.length;
  cell("0:2").fire("keydown", { key: "ArrowUp", shiftKey: true });  // already accented
  cell("1:5").fire("keydown", { key: "Delete" });  // already empty
  assert.equal(ed.edits.length, count);
  ed.button("Hear phrase").fire("click");
  assert.deepEqual(clone(ed.heard), [[[0, 48, 0, 120]]]);
});
test("a click strikes a cell; a part not yet loaded starts empty as a rest; reset releases it", () => {
  const ed = editor([]);
  ed.cells().find((c) => c.dataset.drumCell === "2:0").fire("pointerdown", { pointerType: "touch" });
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", [[-48, 24, 2, 90]]]);
  ed.button("Reset part").fire("click");
  assert.deepEqual(clone(ed.edits.at(-1)), ["part.drum.verse:0.0", null]);
  const fresh = editor(undefined);
  assert.equal(fresh.cells().length, 0);
  assert.match(fresh.box().textContent, /Loading the part/);
  fresh.button("Start empty").fire("click");
  assert.deepEqual(clone(fresh.edits), [["part.drum.verse:0.0", []]]);
});
