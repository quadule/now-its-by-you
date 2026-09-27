/* Run with: node --test tests/studio_composer.test.cjs
 * Interaction tests for the dependency-free editor. These small DOM and audio
 * doubles exercise its public UI events; browser layout is checked separately. */
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../songbird/studio/composer.js"), "utf8");
const clone = (value) => JSON.parse(JSON.stringify(value));

class Element {
  constructor(tag, ownerDocument) {
    this.tagName = tag;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.attrs = {};
    this.style = {};
    this.listeners = {};
    this.dataset = {};
    this.className = "";
    this.parentNode = null;
    this.scrollLeft = 0;
    this.clientWidth = 1000;
  }
  setAttribute(key, value) {
    this.attrs[key] = String(value);
    if (key === "class") this.className = value;
    if (key === "id") this.id = value;
    if (key === "value") this.value = String(value);
    if (key === "hidden") this.hidden = true;
    if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
  }
  getAttribute(key) { return this.attrs[key] ?? null; }
  append(...nodes) {
    for (const node of nodes) {
      const element = typeof node === "string" ? new Text(node, this.ownerDocument) : node;
      this.children.push(element); element.parentNode = this;
    }
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  replaceWith(node) {
    const siblings = this.parentNode.children;
    siblings[siblings.indexOf(this)] = node; node.parentNode = this.parentNode;
  }
  addEventListener(kind, callback) { (this.listeners[kind] ??= []).push(callback); }
  removeEventListener(kind, callback) { this.listeners[kind] = (this.listeners[kind] || []).filter((fn) => fn !== callback); }
  emit(kind, extras = {}) {
    const event = { target: this, currentTarget: this, preventDefault() {}, button: 0, pointerId: 1, ...extras };
    for (const callback of [...(this.listeners[kind] || [])]) callback(event);
  }
  contains(node) { return this === node || this.children.some((child) => child.contains?.(node)); }
  matches(selector) {
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    if (selector.startsWith(".")) return this.className.split(" ").includes(selector.slice(1));
    const attribute = selector.match(/^\[([^=]+)="([^"]+)"\]$/);
    if (attribute) return this.getAttribute(attribute[1]) === attribute[2];
    return this.tagName === selector;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [
      ...(selector.split(", ").some((part) => child.matches?.(part)) ? [child] : []),
      ...(child.querySelectorAll?.(selector) || []),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  get classList() {
    return {
      contains: (value) => this.className.split(" ").includes(value),
      add: (...values) => { this.className = [...new Set([...this.className.split(" "), ...values])].join(" "); },
      remove: (...values) => { this.className = this.className.split(" ").filter((value) => !values.includes(value)).join(" "); },
      toggle: (value, on) => { if (on) this.classList.add(value); else this.classList.remove(value); },
    };
  }
  get textContent() { return this.children.map((child) => child.textContent).join(""); }
  set textContent(value) { this.replaceChildren(new Text(value, this.ownerDocument)); }
  get lastChild() { return this.children.at(-1); }
  focus() { this.ownerDocument.activeElement = this; }
  scrollIntoView() { this.scrolledIntoView = true; }
  getBoundingClientRect() {
    const left = parseFloat(this.style.left) || 0, width = parseFloat(this.style.width) || 100;
    return { left, top: parseFloat(this.style.top) || 0, width, right: left + width };
  }
  setPointerCapture() { this.captured = true; }
  hasPointerCapture() { return this.captured; }
  releasePointerCapture() { this.captured = false; }
}
class Text extends Element {
  constructor(value, document) { super("#text", document); this.text = String(value); }
  get textContent() { return this.text; }
}

function score({ compound = false } = {}) {
  const noteValues = compound
    ? [[3, -1 / 3, 1 / 3], [4, 0, 1 / 3], [6, 1 / 3, 2 / 3], [3, 1, 1 / 3], [1, 4 / 3, 2 / 3]]
    : [[3, -0.5, 0.5], [4, 0, 1], [6, 1, 1], [3, 2, 1], [1, 3, 1]];
  const length = compound ? 2 : 4;
  const scale = [0, 2, 4, 5, 7, 9, 11];
  const makePhrase = (id, start, sung = true) => ({
    id, path: `tune.${id}`, start_beat: start, duration_beats: length,
    pickup_beats: -noteValues[0][1], chords: [["I", "V"]],
    bounds: { min_degree: 1, max_degree: 9, min_onset: noteValues[0][1], max_end: length,
      max_final_onset: length - 0.25, min_duration: 0.25, grid: 0.25, cadence_degree: 1, max_leap: 7 },
    notes: noteValues.map(([degree, onset, duration], index) => ({
      index, degree, onset, duration, pitch: 60 + scale[degree - 1], alter: 0,
      syllable: sung ? ["Sing", "this", "song", "your", "way"][index] : "",
      word: sung ? ["Sing", "this", "song", "your", "way"][index] : "", edited: false,
    })),
  });
  const sections = [
    { name: "intro", id: "intro:0", label: "Intro", sung: false, phrase: "intro" },
    { name: "verse", id: "verse:0", label: "Verse 1", sung: true, phrase: "a1" },
    { name: "refrain", id: "refrain:0", label: "Refrain", sung: true, phrase: "b1" },
    { name: "verse", id: "verse:1", label: "Verse 2", sung: true, phrase: "a1" },
  ].map((section, index) => {
    const start = 0.5 + length * index;
    const phrase = makePhrase(section.phrase, start, section.sung);
    if (!section.sung) phrase.notes = [];
    return { ...section, index, start_beat: start, duration_beats: length, phrases: [phrase] };
  });
  return { composition: { tempo: 100, tonic: 60, mode: "ionian", scale, beats_per_bar: length, grid: 0.25,
    duration_beats: length * 4 + 0.5, duration_seconds: 55.2, sections, order: sections.map((s) => s.id), edited_phrases: [] } };
}

function setup(view = score(), { audioAvailable = true } = {}) {
  const document = new Element("document"); document.ownerDocument = document; document.activeElement = null;
  document.createElement = (tag) => new Element(tag, document);
  document.createElementNS = (_, tag) => new Element(tag, document);
  document.createTextNode = (text) => new Text(text, document);
  document.getElementById = (id) => document.querySelector(`#${id}`);
  const root = document.createElement("div"); root.setAttribute("id", "studio-composer"); document.append(root);
  const audio = document.createElement("audio"); audio.setAttribute("id", "audio"); audio.pause = () => {}; document.append(audio);
  const commits = [], toasts = [], oscillators = [], contexts = [], frames = new Map(), timers = [];
  let frameId = 0, pauseCount = 0;
  class AudioContext {
    constructor() { this.state = "running"; this.currentTime = 0; this.destination = {}; contexts.push(this); }
    createOscillator() {
      const oscillator = { frequency: { value: 0 }, connect() {}, disconnect() {},
        start(time) { assert(Number.isFinite(time)); assert(Number.isFinite(this.frequency.value) && this.frequency.value > 0); this.started = time; },
        stop(time) { if (time !== undefined) assert(Number.isFinite(time)); this.stopped = time === undefined; } };
      oscillators.push(oscillator); return oscillator;
    }
    createGain() {
      const check = (value, time) => assert(Number.isFinite(value) && Number.isFinite(time));
      return { gain: { setValueAtTime: check, linearRampToValueAtTime: check, exponentialRampToValueAtTime: check }, connect() {}, disconnect() {} };
    }
  }
  const window = new Element("window", document);
  window.StudioBridge = { setEdit: (path, value) => commits.push(clone({ path, value })), toast: (message) => toasts.push(message),
    pauseAudio: () => { pauseCount++; }, listen() {} };
  if (audioAvailable) window.AudioContext = AudioContext;
  vm.runInNewContext(source, { window, document, Node: Element, console,
    setTimeout: (fn) => { timers.push(fn); return timers.length; },
    requestAnimationFrame: (fn) => { const id = ++frameId; frames.set(id, fn); return id; },
    cancelAnimationFrame: (id) => frames.delete(id),
  });
  window.SongbirdComposer.render(view);
  const find = (selector) => { const node = root.querySelector(selector); assert(node, `Missing ${selector}`); return node; };
  const clickText = (text) => {
    const node = root.querySelectorAll("button").find((button) => button.textContent === text);
    assert(node, `Missing button ${text}`); node.emit("click");
  };
  return { root, document, window, view, find, clickText, commits, toasts, oscillators, contexts, frames, timers,
    phrase: () => view.composition.sections[1].phrases[0], pauseCount: () => pauseCount };
}

test("the full score overview, musical bars, harmony and inherited restore labels render", () => {
  const s = setup();
  assert.equal(s.root.querySelectorAll(".sbc-overview-section").length, 4);
  assert.equal(s.root.querySelectorAll(".sbc-section").length, 4);
  assert.equal(s.root.querySelectorAll(".sbc-section-foot")[0].textContent, "Bar 1");
  assert.equal(s.root.querySelectorAll(".sbc-section-foot")[1].textContent, "Bar 2");
  assert.equal(s.find(".sbc-tag").textContent, "4 sections · 0:55");
  assert.deepEqual(s.root.querySelectorAll(".sbc-chord").map((node) => node.textContent), ["I", "V"]);
  s.find('[data-overview-section="2"]').emit("click");
  assert.equal(s.find('[data-section="2"]').getAttribute("aria-pressed"), "true");
  assert(s.find('[data-section="2"]').scrolledIntoView);
  s.clickText("Restore phrase"); assert.deepEqual(s.commits.at(-1), { path: "tune.b1", value: null });
  s.clickText("Restore order"); assert.deepEqual(s.commits.at(-1), { path: "form.order", value: null });
});

test("precise length and keyboard timing keep syllables separate and update shared phrases", () => {
  const s = setup(), p = s.phrase();
  s.find('[data-note="0"]').emit("click");
  s.find("#sbc-note-length").emit("change", { target: { value: "0.25" } });
  s.find('[data-note="0"]').emit("keydown", { key: "ArrowRight" });
  const notes = s.commits.at(-1).value;
  assert.equal(notes.length, 5);
  assert.equal(notes[0].onset, -0.25);
  assert.equal(notes[0].duration, 0.25);
  assert(notes[0].onset + notes[0].duration <= notes[1].onset);
  assert.deepEqual(Object.keys(notes[0]).sort(), ["degree", "duration", "onset"]);
  assert.equal(s.view.composition.sections[3].phrases[0].notes[0].onset, -0.25);
  assert.equal(p.notes[0].syllable, "Sing");
  s.find("#sbc-note-start").emit("change", { target: { value: "99" } });
  assert.equal(s.commits.at(-1).value[0].onset, -0.25);
});

test("pointer moving and resizing commit notes; cancelling a drag does not", () => {
  const s = setup();
  let item = s.find('[data-note="1"]'), rect = item.getBoundingClientRect();
  item.emit("pointerdown", { clientX: rect.left + 2, clientY: 150 });
  item.emit("pointermove", { clientX: rect.left + 2, clientY: 127 });
  item.emit("pointerup", { clientX: rect.left + 2, clientY: 127 });
  assert.equal(s.commits.at(-1).value[1].degree, 5);
  item = s.find('[data-note="1"]'); rect = item.getBoundingClientRect();
  item.emit("pointerdown", { clientX: rect.right - 2, clientY: 127 });
  item.emit("pointermove", { clientX: rect.right - rect.width / 2, clientY: 127 });
  item.emit("pointerup", { clientX: rect.right - rect.width / 2, clientY: 127 });
  assert.equal(s.commits.at(-1).value[1].duration, 0.5);
  const count = s.commits.length;
  item = s.find('[data-note="1"]'); rect = item.getBoundingClientRect();
  item.emit("pointerdown", { clientX: rect.left + 2, clientY: 127 });
  item.emit("pointermove", { clientX: rect.left + 2, clientY: 150 });
  item.emit("pointercancel");
  assert.equal(s.commits.length, count);
});

test("composition tools preserve the cadence, count, phrase bounds and nonoverlap", () => {
  const s = setup(), p = s.phrase(), ending = p.notes.at(-1).degree;
  s.clickText("↑ Step");
  assert.equal(p.notes.at(-1).degree, ending);
  s.clickText("Soften leaps");
  assert(p.notes.every((note, index) => !index || Math.abs(note.degree - p.notes[index - 1].degree) <= 2));
  s.clickText("Even rhythm");
  assert.equal(p.notes.length, 5);
  assert.equal(p.notes.at(-1).degree, ending);
  assert(p.notes.every((note, index) => note.duration >= 0.25 && (!index || note.onset >= p.notes[index - 1].onset + p.notes[index - 1].duration - 1e-8)));
  assert(p.notes[0].onset >= p.bounds.min_onset);
  assert(p.notes.at(-1).onset + p.notes.at(-1).duration <= p.bounds.max_end);
});

test("even rhythm fits real Coal and Sticky Burr phrases with fractional pickups and early cadences", () => {
  // These phrase timings come from the repository's B and L 6/8 scores. The
  // old quarter-grid distribution either delayed their cadence or left a
  // final syllable shorter than a quarter beat.
  const cases = [
    { id: "q", end: 2, last: 17 / 12, notes: [[1, 0, 1 / 3], [1, 1 / 3, 1 / 3], [2, 2 / 3, 1 / 3], [3, 1, 1]] },
    { id: "f1", end: 4, last: 41 / 12, notes: [[5, -1 / 3, 1 / 3], [8, 0, 1 / 3], [7, 1 / 3, 1 / 3], [6, 2 / 3, 1 / 3],
      [5, 1, 1 / 3], [4, 4 / 3, 1 / 3], [5, 5 / 3, 1 / 3], [6, 2, 1 / 3], [5, 7 / 3, 1 / 3], [4, 8 / 3, 1 / 3], [5, 3, 1]] },
    { id: "r1", end: 4, last: 41 / 12, notes: [[5, 0, 1 / 3], [5, 1 / 3, 1 / 3], [3, 2 / 3, 1 / 3], [5, 1, 1 / 3],
      [5, 4 / 3, 1 / 3], [3, 5 / 3, 1 / 3], [6, 2, 2 / 3], [5, 8 / 3, 1 / 3], [3, 3, 1]] },
  ];
  for (const fixture of cases) {
    const view = score({ compound: true }), phrase = view.composition.sections[1].phrases[0];
    phrase.id = fixture.id; phrase.path = `tune.${fixture.id}`;
    phrase.duration_beats = fixture.end; phrase.pickup_beats = -fixture.notes[0][1];
    phrase.bounds = { ...phrase.bounds, min_degree: -4, max_degree: 11, min_onset: fixture.notes[0][1], max_end: fixture.end,
      max_final_onset: fixture.last, cadence_degree: fixture.notes.at(-1)[0] };
    phrase.notes = fixture.notes.map(([degree, onset, duration], index) => ({ degree, onset, duration, index,
      pitch: 60 + Math.floor((degree - 1) / 7) * 12 + view.composition.scale[(degree - 1) % 7], syllable: "la", word: "la" }));
    const s = setup(view); s.clickText("Even rhythm");
    assert.equal(s.commits.length, 1, fixture.id);
    const notes = s.commits[0].value;
    assert.equal(notes.length, fixture.notes.length);
    assert.equal(notes[0].onset, fixture.notes[0][1]);
    assert.equal(notes.at(-1).degree, fixture.notes.at(-1)[0]);
    assert(notes.at(-1).onset <= fixture.last + 1e-8, `${fixture.id}: cadence precedes pickup`);
    assert(Math.abs(notes.at(-1).onset + notes.at(-1).duration - fixture.end) < 1e-8);
    assert(notes.every((note, index) => note.duration >= 0.25 && (!index || note.onset >= notes[index - 1].onset + notes[index - 1].duration - 1e-8)), fixture.id);
  }
});

test("even rhythm leaves an impossible layout untouched and explains why", () => {
  const view = score(); view.composition.sections[1].phrases[0].bounds.max_final_onset = 0;
  const s = setup(view), before = clone(s.phrase().notes); s.clickText("Even rhythm");
  assert.equal(s.commits.length, 0);
  assert.deepEqual(s.phrase().notes, before);
  assert.match(s.toasts.at(-1), /too tightly packed/);
});

test("section moves submit stable occurrence identities and reject reversed story order", () => {
  const s = setup();
  s.clickText("Later →");
  assert.deepEqual(s.commits.at(-1), { path: "form.order", value: ["intro:0", "refrain:0", "verse:0", "verse:1"] });
  s.find('[data-section="1"]').emit("dragstart", { dataTransfer: { setData() {} } });
  s.find('[data-section="3"]').emit("drop");
  assert.equal(s.commits.length, 1);
  assert.match(s.toasts.at(-1), /lyric order/);
});

test("note keyboard focus and selection survive backend view replacement", () => {
  const s = setup();
  s.find('[data-note="1"]').focus();
  s.find('[data-note="1"]').emit("keydown", { key: "ArrowUp" });
  s.window.SongbirdComposer.render(clone(s.view));
  assert.equal(s.document.activeElement.dataset.note, "1");
  assert(s.root.contains(s.document.activeElement));
  assert.equal(s.find('[data-note="1"]').getAttribute("aria-pressed"), "true");
  assert.equal(s.find("#sbc-note-pitch").tagName, "select");
});

test("keyboard focus stays on timeline, phrase, scope, snap, zoom and shape controls", () => {
  const s = setup();
  for (const [id, value] of [["sbc-play-scope", "section"], ["sbc-snap", "0.5"], ["sbc-zoom", "2"]]) {
    const control = s.find(`#${id}`); control.focus(); control.emit("change", { target: { value } });
    assert.equal(s.document.activeElement.id, id);
    assert(s.root.contains(s.document.activeElement));
  }
  for (const selector of ['[data-overview-section="2"]', '[data-section="1"]', "#sbc-phrase-0"]) {
    const control = s.find(selector), id = control.id; control.focus(); control.emit("click");
    assert.equal(s.document.activeElement.id, id);
    assert(s.root.contains(s.document.activeElement));
  }
  const tool = s.root.querySelectorAll("button").find((button) => button.textContent === "Soften leaps");
  tool.focus(); tool.emit("click");
  assert.equal(s.document.activeElement.textContent, "Soften leaps");
  assert(s.root.contains(s.document.activeElement));
});

test("lyric emphasis markers stay out of labels without altering the song's words", () => {
  const view = score();
  view.composition.sections[1].phrases[0].notes[1].syllable = "*this*";
  view.composition.sections[1].phrases[0].notes[1].word = "*this*";
  const s = setup(view);
  assert.equal(s.root.querySelectorAll(".sbc-note-word")[1].textContent, "this");
  assert(!s.find(".sbc-phrase-words").textContent.includes("*"));
  assert(!s.find('[data-note="1"]').getAttribute("aria-label").includes("*"));
  s.find('[data-note="1"]').emit("click");
  assert(!s.find(".sbc-note-heading").textContent.includes("*"));
  assert.equal(s.phrase().notes[1].syllable, "*this*");
});

test("editing a compound-meter pitch preserves exact thirds in every note", () => {
  const s = setup(score({ compound: true })), before = s.phrase().notes.map((note) => [note.onset, note.duration]);
  s.find('[data-note="1"]').emit("keydown", { key: "ArrowUp" });
  assert.deepEqual(s.commits.at(-1).value.map((note) => [note.onset, note.duration]), before);
  assert.equal(s.commits.at(-1).value[0].onset, -1 / 3);
});

test("the final note keeps its cadence and leaves time for the following pickup", () => {
  const view = score(); view.composition.sections[1].phrases[0].bounds.max_final_onset = 3.25;
  const s = setup(view);
  s.find('[data-note="4"]').emit("click");
  s.find("#sbc-note-length").emit("change", { target: { value: "0.25" } });
  s.find("#sbc-note-start").emit("change", { target: { value: "4" } });
  assert.equal(s.commits.at(-1).value[4].onset, 3.25);
  s.find('[data-note="4"]').emit("keydown", { key: "ArrowUp" });
  assert.equal(s.commits.at(-1).value[4].degree, 8);
  assert.equal((s.commits.at(-1).value[4].degree - 1) % 7, 0);
});

test("audio sketch schedules finite tones, advances the full-song playhead and stops", () => {
  const s = setup();
  s.find("#sbc-play").emit("click");
  assert.equal(s.oscillators.length, 5);
  assert.equal(s.pauseCount(), 1);
  assert.equal(s.frames.size, 1);
  assert.equal(s.find("#sbc-song-playhead").hidden, false);
  assert.match(s.find("#sbc-song-playhead").style.left, /%$/);
  assert(s.find('[data-overview-section="1"]').classList.contains("is-playing") || s.find('[data-overview-section="0"]').classList.contains("is-playing"));
  const before = parseFloat(s.find("#sbc-song-playhead").style.left);
  const nextFrame = [...s.frames.values()][0]; s.frames.clear();
  s.contexts[0].currentTime = 0.64; nextFrame();
  assert(parseFloat(s.find("#sbc-song-playhead").style.left) > before);
  assert.equal(s.oscillators.length, 5, "animation frames do not schedule the same notes twice");
  s.window.SongbirdComposer.stop();
  assert.equal(s.frames.size, 0);
  assert(s.oscillators.every((oscillator) => oscillator.stopped));
  assert.equal(s.find("#sbc-song-playhead").hidden, true);
});

test("metronome clicks follow score downbeats after pickups in every playback scope and loop", () => {
  for (const compound of [false, true]) for (const scope of ["phrase", "section", "song"]) for (const loop of [false, true]) {
    const s = setup(score({ compound }));
    s.find("#sbc-play-scope").emit("change", { target: { value: scope } });
    s.find("#sbc-option-click").emit("change", { target: { checked: true } });
    if (loop) s.find("#sbc-option-loop").emit("change", { target: { checked: true } });
    s.find("#sbc-play").emit("click");
    const clicks = s.oscillators.filter((oscillator) => oscillator.type === "sine");
    const bar = compound ? 2 : 4, pickup = compound ? 1 / 3 : 0.5;
    const beats = scope === "song" ? bar * 4 : bar, seconds = 60 / 100;
    const cycles = loop ? 2 : 1;
    assert.equal(clicks.length, beats * cycles, `${compound ? "6/8" : "4/4"} ${scope} loop=${loop}`);
    for (let cycle = 0; cycle < cycles; cycle++) for (let beat = 0; beat < beats; beat++) {
      const click = clicks[cycle * beats + beat];
      const expectedStart = 0.04 + (pickup + beat + cycle * (beats + pickup)) * seconds;
      assert(Math.abs(click.started - expectedStart) < 1e-8, "click waits through pickup, then follows whole score beats");
      assert.equal(click.frequency.value, beat % bar === 0 ? 1200 : 800, "only the score's bar downbeats are accented");
    }
    s.window.SongbirdComposer.stop();
  }
  const view = score(), phrase = view.composition.sections[1].phrases[0];
  phrase.pickup_beats = 1.5; phrase.bounds.min_onset = -1.5; phrase.notes[0].onset = -1.5;
  const s = setup(view);
  s.find("#sbc-option-click").emit("change", { target: { checked: true } });
  s.find("#sbc-play").emit("click");
  const clicks = s.oscillators.filter((oscillator) => oscillator.type === "sine");
  assert.equal(clicks[0].frequency.value, 800, "a whole beat within a longer pickup is unaccented");
  assert.equal(clicks[1].frequency.value, 1200, "the accent arrives on the phrase's actual downbeat");
  assert(Math.abs(clicks[1].started - (0.04 + 1.5 * 0.6)) < 1e-8);
  s.window.SongbirdComposer.stop();
});

test("a browser without Web Audio keeps editing available and explains how to listen", () => {
  const s = setup(score(), { audioAvailable: false });
  s.find("#sbc-play").emit("click");
  assert.match(s.toasts.at(-1), /Hear sung section/);
  assert.equal(s.frames.size, 0);
  s.find('[data-note="1"]').emit("keydown", { key: "ArrowUp" });
  assert.equal(s.commits.at(-1).path, "tune.a1");
});
