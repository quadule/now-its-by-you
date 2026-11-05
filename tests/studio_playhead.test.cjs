// The whole song from the score's playhead (songbird/studio/score.js and studio.js), sung or in the sketch: the
// transport's ▶ with nothing selected starts the song's audio at the bar the ruler put the playhead at, found by the
// rendition's own clock (the bar_seconds a whole song's job ends with), and the sketch on that bar's line in its own
// beats (counted from the first pickup, not bar 1: M.sketchOffset), the transport saying the bar it plays; a selected
// section's preview is as it was. The page runs on dependency-free DOM and <audio> doubles. Run with
// `node --test tests/studio_playhead.test.cjs`.
"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = (file) => fs.readFileSync(path.join(__dirname, "../songbird/studio", file), "utf8");
const tick = () => new Promise((resolve) => setImmediate(resolve));

// An element as the score draws and patches one (morph): attributes, children, text, listeners
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
  append(...kids) { this.childNodes.push(...kids); }
  appendChild(kid) { this.childNodes.push(kid); return kid; }
  replaceChild(kid, old) { this.childNodes[this.childNodes.indexOf(old)] = kid; return old; }
  removeChild(kid) { this.childNodes.splice(this.childNodes.indexOf(kid), 1); return kid; }
  replaceChildren(...kids) { this.childNodes = kids; }
  after() {}
  setAttribute(name, value) { this.attrs[name] = String(value); }
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
  focus() {}
  scrollIntoView() {}
  getBoundingClientRect() { return { left: 0, top: 0, width: 120, height: 24 }; }
}

// <audio>: a new src begins it again (paused, at 0), as a browser's load does; play()'s promise settles when the
// test says it sounds
class Audio extends Node {
  constructor() { super("audio"); this.paused = true; this.currentTime = 0; this.volume = 1; this.played = this.url = ""; }
  get src() { return this.url; }
  set src(url) { this.url = url; this.paused = true; this.currentTime = 0; }
  play() { this.paused = false; this.played = this.url; return new Promise((resolve) => { this.sounds = resolve; }); }
  pause() { this.paused = true; }
}

// A version laid out as the reported one: Refrain 3 from bar 45. Its clock: bar 1 after a breath and the pickup,
// 2.4845 s a bar (96.6 to the minute), the last two bars slowing; a whole song's job ends with it.
const FORM = [["intro:0", "Intro", 4, false], ["verse:0", "Verse 1", 8, true], ["refrain:0", "Refrain 1", 8, true],
  ["verse:1", "Verse 2", 8, true], ["refrain:1", "Refrain 2", 8, true], ["verse:2", "Verse 3", 8, true],
  ["refrain:2", "Refrain 3", 8, true], ["bridge:0", "Bridge", 8, true], ["refrain:3", "Refrain 4", 8, true]];
let beat = 0;
const SECTIONS = FORM.map(([id, label, bars, sung], index) => {
  const s = { index, id, name: id.split(":")[0], label, role: id.split(":")[0], bars, bar_options: [bars], start_beat: beat,
    duration_beats: bars * 4, sung, can_play: sung, choir: false, build: false, by: {}, program: { bars }, paths: {},
    options: [], problems: [], lines: [], energy: 0.6 };
  beat += bars * 4;
  return s;
});
const BARS = beat / 4;  // 68
const BAR_SECONDS = Array.from({ length: BARS + 1 }, (_, k) => Math.round((0.911 + 2.4845 * k + (k > BARS - 2 ? 0.4 * (k - BARS + 2) ** 2 : 0)) * 1000) / 1000);
const WHOLE = { state: "done", url: "/audio/whole.flac", key: "w1", label: "The whole song", progress: 1, result: { bar_seconds: BAR_SECONDS } };

// lead: where the composition's (and the sketch's) beats put bar 1, counted from the song's first pickup: half a beat
// for the song's eighth-note pickup, a bar more with a count-in
function studio({ lead = 0.5 } = {}) {
  const nodes = new Map(), on = {}, asked = [], sketched = [];
  const how = { sketch: new Node("button"), sung: new Node("button") };
  how.sketch.dataset.how = "sketch"; how.sung.dataset.how = "sung";
  const document = {
    getElementById: (id) => {
      if (!nodes.has(id)) nodes.set(id, id === "audio" ? new Audio() : new Node("div"));
      return nodes.get(id);
    },
    querySelector: (selector) => (selector.startsWith("meta") ? { content: "token" } : null),
    querySelectorAll: (selector) => (selector === "[data-how]" ? [how.sketch, how.sung] : []),
    addEventListener: (type, fn) => { (on[type] ||= []).push(fn); },
    createElement: (tag) => new Node(tag),
    createElementNS: (_, tag) => new Node(tag),
    createTextNode: (text) => new Node("#text", text),
    activeElement: null,
  };
  for (const id of ["finishPanel", "drawer", "scrim", "notes", "howPop", "keyPop"]) document.getElementById(id).hidden = true;
  const window = {
    addEventListener() {},
    SongbirdComposer: { stop() {}, playing: () => false, sketch: (o) => sketched.push(JSON.parse(JSON.stringify(o))) },
  };
  const context = vm.createContext({
    document, window, Node, console, URL, location: { hash: "" }, innerWidth: 1280, CSS: { escape: (s) => s },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    setTimeout: () => 1, clearTimeout() {}, requestAnimationFrame: () => 1, ResizeObserver: class { observe() {} },
    ask: async (path, body) => {
      asked.push([path, JSON.parse(JSON.stringify(body))]);
      if (path === "/api/arrangement") return { sections: SECTIONS, players: [], cells: [], problems: [] };
      if (path === "/api/sound") return { players: [], boundaries: [] };
      if (path === "/api/listen") return body.section === null ? WHOLE : { state: "done", url: "/audio/refrain.flac", key: "s6", progress: 1, result: { duration: 21 } };
      throw new Error(`unexpected ${path}`);
    },
  });
  const run = (code) => vm.runInContext(code, context);
  for (const file of ["model.js", "renderer.js"]) run(source(file));
  run(source("studio.js").replace(/\nmain\(\);\s*$/, "\n"));
  run(source("score.js"));
  for (const fn of on.DOMContentLoaded || []) fn();  // the score wires its transport
  run(`api = ask;
    state.start = {title: "Song", from: "home", machine: {label: "test"}, kinds: {}, optional: [], bounds: {}};
    state.view = {by: "a made-up machine called Ada", date: "Wednesday, September 30, 2026", offset: 0, edits: {}, cards: [],
      words: ${JSON.stringify(FORM.map(([id, label, , sung], index) => ({ index, label, name: id.split(":")[0], block: id.split(":")[0],
    nth: 0, sung, lines: sung ? ["They sang it *home*"] : [], how: "handed down", mine: false })))},
      listen: {whole: "w1", sections: [], ready: ["w1", "s6"]},
      composition: {beats_per_bar: 4, duration: 172, sections: ${JSON.stringify(SECTIONS.map(({ id, index, start_beat, duration_beats }) =>
    ({ id, index, start_beat: start_beat + lead, duration_beats, phrases: [] })))}}};`);
  const $ = (id) => document.getElementById(id);
  const find = (node, test) => test(node) ? node : node.childNodes.reduce((hit, c) => hit || find(c, test), null);
  const button = (label) => find($("grid"), (n) => n.getAttribute?.("aria-label") === label);
  return { run, $, asked, sketched, how, button, audio: $("audio"),
    async open() { run("window.SongbirdScore.render(state.view)"); await tick(); await tick(); } };
}

test("the whole song, sung, starts at the playhead's bar by the rendition's clock, and is brought up once it sounds", async () => {
  const page = studio();
  await page.open();  // the Arrange grid drawn, nothing selected
  assert.equal(page.$("nowTitle").textContent, "The whole song");
  page.button("Put the playhead at bar 45, Refrain 3").dispatch("click", { clientX: 0 });
  assert.equal(page.$("nowTitle").textContent, "Refrain 3");
  assert.equal(page.$("nowSub").textContent, "bar 45");
  page.how.sung.dispatch("click");
  page.$("tPlay").dispatch("click");
  await tick();
  assert.deepEqual(page.asked.at(-1), ["/api/listen", { edits: {}, who: "you", section: null }]);  // the whole song, made once
  const audio = page.audio;
  assert.equal(audio.played, "/audio/whole.flac");
  assert.equal(audio.currentTime, BAR_SECONDS[44]);  // bar 45's bar line in its audio, not 0:00
  assert.equal(audio.volume, 0, "silent until it sounds there: a bar line mid-song isn't silence");
  audio.currentTime = 0;  // a browser that let the time go before it loaded is told again once it knows the length
  audio.dispatch("loadedmetadata");
  assert.equal(audio.currentTime, BAR_SECONDS[44]);
  audio.sounds();
  await tick();
  assert.equal(audio.volume, 1);
  assert.equal(page.$("tPlay").textContent, "■");
});

test("the sketch starts the song on the playhead's bar line too, and a selected section is previewed from its own start", async () => {
  const page = studio();
  await page.open();
  page.button("Put the playhead at bar 45, Refrain 3").dispatch("click", { clientX: 0 });
  page.how.sketch.dispatch("click");
  page.$("tPlay").dispatch("click");
  assert.deepEqual(page.sketched, [{ scope: "song", from: 176.5 }]);  // bar 45's line in the sketch's beats (it was 176)
  assert.ok(!page.asked.some(([p]) => p === "/api/listen"));
  page.how.sung.dispatch("click");
  find(page, "hear:refrain:2").dispatch("click");  // Refrain 3's ▶: selects it and plays it
  await tick();
  assert.deepEqual(page.asked.at(-1), ["/api/listen", { edits: {}, who: "you", section: 6 }]);
  assert.equal(page.audio.played, "/audio/refrain.flac");
  assert.equal(page.audio.currentTime, 0);
  assert.equal(page.audio.volume, 1);
});

test("with a count-in the sketch still starts on the playhead's bar, and the transport says the bar it plays", async () => {
  const page = studio({ lead: 4.5 });  // a bar of counting and the pickup before bar 1, in the sketch's beats
  await page.open();
  page.button("Put the playhead at bar 45, Refrain 3").dispatch("click", { clientX: 0 });
  page.how.sketch.dispatch("click");
  page.$("tPlay").dispatch("click");
  assert.deepEqual(page.sketched, [{ scope: "song", from: 180.5 }]);  // it was 176: more than a bar early
  const score = page.run("window.SongbirdScore");
  score.tick(188.5, 0.1);  // two bars in, as the sketch counts them
  assert.equal(page.$("nowTitle").textContent, "Refrain 3 · bar 47");  // it said bar 48
  score.tick(4, 0);  // the first pickup, before bar 1: bar 1's, not the last section's
  assert.equal(page.$("nowTitle").textContent, "Intro · bar 1");
  score.tick(null);
  page.button("Put the playhead at bar 1, Intro").dispatch("click", { clientX: 0 });
  page.$("tPlay").dispatch("click");
  assert.deepEqual(page.sketched.at(-1), { scope: "song", from: null });  // the song from its start, its first pickup with it
});

test("bar 1, no playhead, a bar past the song or a job without its clock: the whole song from its very start", async () => {
  const page = studio();
  await page.open();
  page.button("Put the playhead at bar 1, Intro").dispatch("click", { clientX: 0 });
  page.how.sung.dispatch("click");
  page.$("tPlay").dispatch("click");
  await tick();
  assert.equal(page.audio.played, "/audio/whole.flac");
  assert.equal(page.audio.currentTime, 0);  // the breath and the first pickup before bar 1 are heard
  assert.equal(page.run("barTime([0.9, 3.4, 5.9], null)"), 0);
  assert.equal(page.run("barTime([0.9, 3.4, 5.9], 3)"), 5.9);
  assert.equal(page.run("barTime([0.9, 3.4, 5.9], 4)"), 0);
  assert.equal(page.run("barTime(undefined, 3)"), 0);
});

function find(page, key) {
  const hit = (n) => n.getAttribute?.("data-key") === key ? n : n.childNodes.reduce((x, c) => x || hit(c), null);
  return hit(page.$("grid"));
}
