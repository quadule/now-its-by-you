// A song's sections as clips in the score (songbird/studio/score.js; docs/notes/STUDIO-CLIPS.md, "For the editor"):
// + adds a blank section after the one selected, Duplicate, Repeat and Delete in the column and on a section's
// header keys, a move through the clips when the song has them, a section's lines and a blank one's length, each one
// request to /api/clips and one step of the history. The page runs on dependency-free DOM doubles, as
// tests/studio_playhead.test.cjs's. Run with `node --test tests/studio_clips.test.cjs`.
"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = (file) => fs.readFileSync(path.join(__dirname, "../songbird/studio", file), "utf8");
const tick = () => new Promise((resolve) => setImmediate(resolve));
const settle = async () => { for (let i = 0; i < 6; i++) await tick(); };

class Node {
  constructor(tag, text = "") {
    this.nodeName = this.tagName = tag.toUpperCase();
    this.nodeType = tag === "#text" ? 3 : 1;
    this.data = text;
    this.childNodes = []; this.attrs = {}; this.on = {}; this.dataset = {}; this.style = {}; this.hidden = false;
    this.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
  }
  get textContent() { return this.nodeType === 3 ? this.data : this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(text) {
    if (this.nodeType === 3) this.data = String(text);
    else this.childNodes = text === "" ? [] : [new Node("#text", String(text))];
  }
  get children() { return this.childNodes.filter((c) => c.nodeType === 1); }
  get lastChild() { return this.childNodes.at(-1) || null; }
  get attributes() { return Object.entries(this.attrs).map(([name, value]) => ({ name, value })); }
  append(...kids) { for (const k of kids) k.parentNode = this; this.childNodes.push(...kids); }
  appendChild(kid) { kid.parentNode = this; this.childNodes.push(kid); return kid; }
  replaceChild(kid, old) { kid.parentNode = this; this.childNodes[this.childNodes.indexOf(old)] = kid; return old; }
  removeChild(kid) { this.childNodes.splice(this.childNodes.indexOf(kid), 1); return kid; }
  replaceChildren(...kids) { for (const k of kids) k.parentNode = this; this.childNodes = kids; }
  after() {}
  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, l) => l.toUpperCase())] = String(value);
  }
  getAttribute(name) { return Object.hasOwn(this.attrs, name) ? this.attrs[name] : null; }
  hasAttribute(name) { return Object.hasOwn(this.attrs, name); }
  removeAttribute(name) { delete this.attrs[name]; }
  addEventListener(type, fn) { (this.on[type] ||= []).push(fn); }
  dispatch(type, event = {}) {
    for (const fn of this.on[type] || []) fn.call(this, { target: this, currentTarget: this, preventDefault() {}, stopPropagation() {}, ...event });
  }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  matches() { return false; }
  focus() {}
  scrollIntoView() {}
  getBoundingClientRect() { return { left: 0, top: 0, width: 120, height: 24 }; }
}

// Intro, Verse 1, Refrain 1: the form's own implicit clips, or the same stored
const FORM = [["intro", "intro101", "Intro", 4, false], ["verse", "verse102", "Verse 1", 8, true], ["refrain", "refrain103", "Refrain", 8, true]];
function song({ stored = false, extra = [] } = {}) {
  const rows = [...FORM, ...extra];
  let beat = 0;
  const sections = rows.map(([name, clip, label, bars, sung], index) => {
    const id = stored ? `${clip}:0` : `${name}:0`;
    const s = { index, id, name: stored ? clip : name, label, role: name, bars, bar_options: [bars], start_beat: beat, duration_beats: bars * 4,
      sung, can_play: sung, choir: false, build: false, by: {}, program: { bars }, paths: { bars: `arrange.${id}.bars` }, options: [], problems: [], lines: [], energy: 0.6 };
    beat += bars * 4;
    return s;
  });
  const clips = {
    stored, roles: ["intro", "verse", "refrain", "turn", "break", "bridge", "tag", "outro"],
    bounds: { instances: 48, clips: 48, lines: 16, line_bars: 8, clip_bars: 64, song_bars: 768, label: 24 },
    value: { form: FORM.map((r) => r[0]), order: rows.map((r) => r[1]), clips: Object.fromEntries(rows.map((r, k) => [r[1], k < 3 ? { from: `${r[0]}:0` } : { role: r[0], sung: r[4], lines: [{ bars: 2 }, { bars: 2 }] }])), next: 101 + rows.length },
    clips: rows.map(([name, clip, label, bars, sung], k) => ({
      id: clip, label, role: name, source: k < 3 ? `${name}:0` : null, sung, bars, instances: [k], authored: false,
      lines: k < 3 ? [{ phrase: `${name[0]}1`, of: 0, bars: bars / 2 }, { phrase: `${name[0]}2`, of: 1, bars: bars / 2 }] : [{ phrase: `${clip}-0`, of: null, bars: 2 }, { phrase: `${clip}-1`, of: null, bars: 2 }],
      can: { delete: true, duplicate: true, repeat: true } })),
  };
  return { sections, clips };
}

function studio(view = song()) {
  const nodes = new Map(), on = {}, asked = [];
  const document = {
    getElementById: (id) => { if (!nodes.has(id)) nodes.set(id, new Node(id === "audio" ? "audio" : "div")); return nodes.get(id); },
    querySelector: (selector) => (selector.startsWith("meta") ? { content: "token" } : null),
    querySelectorAll: () => [],
    addEventListener: (type, fn) => { (on[type] ||= []).push(fn); },
    createElement: (tag) => new Node(tag),
    createElementNS: (_, tag) => new Node(tag),
    createTextNode: (text) => new Node("#text", text),
    activeElement: null,
  };
  const audio = document.getElementById("audio");
  Object.assign(audio, { paused: true, pause() {}, play: () => Promise.resolve() });
  for (const id of ["finishPanel", "drawer", "scrim", "notes", "howPop", "keyPop", "emptyConfirm"]) document.getElementById(id).hidden = true;
  const opened = [];
  let player = "voice";
  const window = { addEventListener() {}, SongbirdComposer: { stop() {}, playing: () => false, sketch() {}, deselect() {}, mini: () => null,
    open: (index, who) => { player = who; opened.push([index, who]); }, chords: () => { opened.push("chords"); return true; }, selection: () => ({ player }) } };
  // the engine's answer: here, the edits with a mark of each operation (the page's view is the test's own)
  let answer = (body) => ({ edits: { ...body.edits, [`op${Object.keys(body.edits).length}`]: body.op }, clip: ["blank", "duplicate"].includes(body.op) ? "verse104" : null });
  const context = vm.createContext({
    document, window, Node, console, URL, location: { hash: "" }, innerWidth: 1280, CSS: { escape: (s) => s },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    setTimeout: () => 1, clearTimeout() {}, requestAnimationFrame: () => 1, ResizeObserver: class { observe() {} },
    ask: async (p, body) => {
      asked.push([p, JSON.parse(JSON.stringify(body))]);
      if (p === "/api/arrangement") return { sections: view.sections, players: view.players || [], cells: view.cells || [], problems: [] };
      if (p === "/api/sound") return { players: [], boundaries: [] };
      if (p === "/api/clips") { const r = answer(body); if (r instanceof Error) throw r; return r; }
      if (p === "/api/song") return null;  // (the refresh after an edit: not drawn here)
      throw new Error(`unexpected ${p}`);
    },
  });
  const run = (code) => vm.runInContext(code, context);
  for (const file of ["model.js", "renderer.js"]) run(source(file));
  run(source("studio.js").replace(/\nmain\(\);\s*$/, "\n"));
  run(source("score.js"));
  for (const fn of on.DOMContentLoaded || []) fn();
  context.VIEW = view;
  run(`api = ask; refreshSoon = () => {};
    state.start = {title: "Song", from: "home", machine: {label: "test"}, kinds: {}, optional: [], bounds: {}};
    state.view = {by: "a made-up machine called Ada", date: "Today", offset: 0, edits: {}, cards: [], words: [],
      listen: {whole: "w", sections: [], ready: []},
      composition: {beats_per_bar: 4, duration: 60, clips: VIEW.clips, players: VIEW.players || [], sections: VIEW.sections.map((s) => ({ id: s.id, index: s.index, label: s.label, start_beat: s.start_beat, duration_beats: s.duration_beats, phrases: [] }))}};`);
  const $ = (id) => document.getElementById(id);
  const findIn = (node, test) => test(node) ? node : node.childNodes.reduce((hit, c) => hit || findIn(c, test), null);
  const key = (k) => findIn($("grid"), (n) => n.getAttribute?.("data-key") === k);
  const button = (text) => findIn($("inspector"), (n) => n.nodeName === "BUTTON" && n.textContent.trim() === text);
  const press = (target, k, mods = {}) => { for (const fn of on.keydown || []) fn({ key: k, target, preventDefault() {}, ...mods }); };
  const region = (id) => {
    const r = key(`region:${id}`);
    r.closest = (sel) => (/region|button/.test(sel) ? r : null);
    return r;
  };
  return { run, $, asked, opened, key, button, press, region, setAnswer: (fn) => { answer = fn; },
    clipAsks: () => asked.filter(([p]) => p === "/api/clips").map(([, b]) => { const { edits, ...op } = b; return op; }),
    async open() { run("window.SongbirdScore.render(state.view)"); await settle(); } };
}

test("+ adds a blank 8-bar verse of 4 lines at the end, or after the section selected, as one step of the history", async () => {
  const page = studio();
  await page.open();
  page.key("add-section").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks(), [{ op: "blank", role: "verse", sung: true, bars: 8, lines: 4, at: 3 }]);
  assert.equal(page.run("state.undo.length"), 1);
  assert.equal(page.run("state.undo.at(-1).label"), "New verse");
  assert.equal(JSON.stringify(page.run("state.edits")), '{"op0":"blank"}');
  page.region("verse:0").dispatch("click");
  page.key("add-section").dispatch("click");
  await settle();
  assert.equal(page.clipAsks().at(-1).at, 2, "after Verse 1");
  assert.equal(page.run("state.undo.at(-1).label"), "New verse after Verse 1");
  assert.equal(page.run("state.undo.length"), 2);
});

test("Duplicate, Repeat and Delete in the column; Ctrl/⌘ D and Delete on a section's header only", async () => {
  const page = studio();
  await page.open();
  page.region("verse:0").dispatch("click");
  page.button("Duplicate").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "duplicate", clip: "verse102", at: 2 });
  assert.equal(page.run("state.undo.at(-1).label"), "Duplicate Verse 1");
  page.button("Repeat").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "repeat", clip: "verse102", at: 2 });
  page.button("Delete").dispatch("click");
  await settle();
  assert.equal(page.clipAsks().length, 3);  // (the song's clips weren't stored: the section's place is its index)
  assert.deepEqual(page.clipAsks().at(-1), { op: "delete", at: 1 });
  assert.equal(page.run("state.undo.at(-1).label"), "Delete Verse 1");
  const n = page.clipAsks().length;
  page.press(page.region("refrain:0"), "d", { ctrlKey: true });
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "duplicate", clip: "refrain103", at: 3 });
  page.press(page.region("intro:0"), "Delete");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "delete", at: 0 });
  // a note, a cell or a field focused: not the section's
  page.press({ tagName: "BUTTON", closest: () => null, matches: () => false, dataset: {} }, "Delete");
  page.press({ tagName: "INPUT", type: "text", closest: () => null }, "d", { metaKey: true });
  await settle();
  assert.equal(page.clipAsks().length, n + 2);
});

// score.js clipOp: an operation asked for while the song's first (the one that stores its clips) is still on its way
// names its section by the id the grid gave then ("intro:0"); run after the first, placeOf looks that id up among the
// stored clips' instances ("intro101:0"), finds nothing, and the operation is dropped without a word.
test("an operation asked for while the first on a song without clips is on its way is done after it", { todo: "score.js placeOf: the id is resolved when the operation runs, not when it is asked for" }, async () => {
  const page = studio();
  await page.open();
  let land;
  page.setAnswer((body) => new Promise((resolve) => { land = () => resolve({ edits: { ...body.edits,
    clips: { form: ["intro", "verse", "refrain"], order: ["intro101", "verse102", "verse104", "refrain103"], clips: {}, next: 105 } }, clip: "verse104" }); }));
  page.region("verse:0").dispatch("click");
  page.button("Duplicate").dispatch("click");
  await settle();
  page.setAnswer((body) => ({ edits: { ...body.edits, deleted: true }, clip: null }));
  page.region("intro:0").dispatch("click");
  page.button("Delete").dispatch("click");  // while the duplicate is on its way
  land();
  await settle();
  assert.deepEqual(page.clipAsks(), [{ op: "duplicate", clip: "verse102", at: 2 }, { op: "delete", at: 0 }]);
});

test("a refused operation is disabled, its reason the engine's sentence", async () => {
  const view = song();
  view.clips.clips[1].can = { delete: "a song needs one clip", duplicate: "the song has as many clips as it can", repeat: true };
  const page = studio(view);
  await page.open();
  page.region("verse:0").dispatch("click");
  const del = page.button("Delete"), dup = page.button("Duplicate");
  assert.equal(del.getAttribute("disabled"), "");
  assert.equal(del.getAttribute("title"), "A song needs one clip.");
  assert.equal(dup.getAttribute("title"), "The song has as many clips as it can.");
  page.press(page.region("verse:0"), "Backspace");
  await settle();
  assert.equal(page.clipAsks().length, 0);
});

test("a move is one function: the shape's order without clips, the clips' move with them, and the engine's refusal said", async () => {
  const page = studio();
  await page.open();
  page.region("intro:0").dispatch("click");
  page.button("Later →").dispatch("click");
  assert.equal(page.run("state.edits['form.order'].join(' ')"), "verse:0 intro:0 refrain:0");
  assert.equal(page.clipAsks().length, 0);

  const stored = studio(song({ stored: true }));
  await stored.open();
  stored.region("intro101:0").dispatch("click");
  stored.button("Later →").dispatch("click");
  await settle();
  assert.deepEqual(stored.clipAsks(), [{ op: "move", from: 0, to: 1 }]);
  assert.equal(stored.run("state.undo.at(-1).label"), "Move Intro");
  stored.press(stored.region("refrain103:0"), "ArrowLeft", { ctrlKey: true });
  await settle();
  // the order the first move left is the one the next starts from
  assert.equal(stored.clipAsks().length, 1, "the refrain wasn't selected: ⌘← moves the selection");
  stored.setAnswer(() => new Error("a song is at most 768 bars; these clips make 800"));
  stored.region("refrain103:0").dispatch("click");
  stored.button("← Earlier").dispatch("click");
  await settle();
  assert.equal(stored.run("document.getElementById('toast').textContent"), "A song is at most 768 bars; these clips make 800.");
  assert.equal(stored.run("state.undo.length"), 1);
});

test("a section's lines: a blank line's bars, a line added or the last taken away; a blank section's length is its lines'", async () => {
  const page = studio(song({ stored: true, extra: [["break", "break104", "Break", 4, false]] }));
  await page.open();
  page.region("break104:0").dispatch("click");
  page.button("+ line").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "lines", clip: "break104", lines: [{ bars: 2 }, { bars: 2 }, { bars: 2 }] });
  page.button("− line").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "lines", clip: "break104", lines: [{ bars: 2 }] });
  page.button("8 bars").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "lines", clip: "break104", lines: [{ bars: 4 }, { bars: 4 }] });
  assert.equal(page.button("16 bars").getAttribute("disabled"), null, "two lines of 8 bars at most: 16 is allowed");
  page.region("verse102:0").dispatch("click");
  page.button("+ line").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks().at(-1), { op: "lines", clip: "verse102", lines: [{ of: 0 }, { of: 1 }, { bars: 2 }] });
  assert.equal(page.run("state.undo.length"), 4);
});

test("one selection: a cell opens its track's editor on its section, the notes follow the section selected, the Part menu is a row", async () => {
  const view = song();
  view.players = [{ name: "fiddle", label: "Fiddle", family: "bowed", plays: true, patterns: [] }];
  view.cells = view.sections.map((s) => ({ section: s.id, player: "fiddle", plays: true, value: { level: "plays" }, program: { level: "plays" }, by: "program", paths: {}, why: [], problems: [] }));
  const page = studio(view);
  await page.open();
  page.key("cell:singer:verse:0").dispatch("click");
  assert.deepEqual(page.opened.at(-1), [1, "voice"], "the singer's row: the melody of Verse 1");
  assert.equal(page.run("JSON.stringify(window.SongbirdScore._state.sel)"), '{"kind":"cell","id":"verse:0","player":"singer"}');
  page.key("cell:fiddle:refrain:0").dispatch("click");
  assert.deepEqual(page.opened.at(-1), [2, "fiddle"], "a player's row: its roll, in the Refrain");
  page.region("intro:0").dispatch("click");
  assert.deepEqual(page.opened.at(-1), [0, "fiddle"], "a section selected: the notes follow it, on the same part");
  assert.equal(page.run("window.SongbirdScore._state.open"), "intro:0");
  page.key("cell:chords:verse:0").dispatch("click");
  assert.deepEqual(page.opened.slice(-2), [[1, "voice"], "chords"], "the chords row: the melody's harmony strip");
  page.run("window.SongbirdScore.partChosen('fiddle')");
  assert.equal(page.run("JSON.stringify(window.SongbirdScore._state.sel)"), '{"kind":"cell","id":"verse:0","player":"fiddle"}');
  assert.equal(page.run("JSON.stringify(window.SongbirdModel.playTarget(window.SongbirdScore._state.sel, window.SongbirdScore._state.grid.sections))"), JSON.stringify({ section: 1, phrase: false }), "▶ plays the cell's section");
});

test("Empty song: one confirmed step, the form one blank verse, the Arrange view on it", async () => {
  const page = studio();
  await page.open();
  page.$("emptySong").dispatch("click");
  assert.equal(page.$("emptyConfirm").hidden, false, "it asks first");
  assert.equal(page.clipAsks().length, 0);
  page.$("emptyNo").dispatch("click");
  assert.equal(page.$("emptyConfirm").hidden, true);
  page.$("emptySong").dispatch("click");
  page.$("emptyYes").dispatch("click");
  await settle();
  assert.deepEqual(page.clipAsks(), [{ op: "empty", role: "verse", sung: true, bars: 8, lines: 4 }]);
  assert.equal(page.run("state.undo.length"), 1);
  assert.equal(page.run("state.undo.at(-1).label"), "Empty song");
  assert.equal(page.run("window.SongbirdScore.view()"), "arrange");
});
