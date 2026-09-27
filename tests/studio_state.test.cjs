// Run with `node --test tests/studio_state.test.cjs`; the shipped studio has no JS dependencies.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function studio() {
  class Node {
    constructor(tag = '') {
      this.tagName = tag.toUpperCase();
      this.children = [];
      this.childNodes = this.children;
      this.dataset = {};
      this.style = {};
      this.classList = { add() {}, remove() {}, toggle() {} };
      this.listeners = {};
      this.textContent = '';
      this.value = '';
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; this.childNodes = children; }
    setAttribute(name, value) { this[name] = value; }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    querySelectorAll() { return []; }
    contains() { return false; }
    closest() { return this.ancestor || null; }
    scrollIntoView() { this.scrolledWithAncestorOpen = this.ancestor?.open; }
    pause() {}
    play() { return Promise.resolve(); }
  }
  const nodes = new Map(), storage = new Map();
  const document = {
    getElementById: (id) => {
      if (!nodes.has(id)) nodes.set(id, new Node());
      return nodes.get(id);
    },
    querySelector: (selector) => selector.startsWith('meta') ? { content: 'token' } : null,
    querySelectorAll: () => [],
    addEventListener() {},
    createElement: (tag) => new Node(tag),
    createElementNS: (_, tag) => new Node(tag),
    createTextNode: (text) => text,
  };
  const context = vm.createContext({
    document, Node, console, URL, location: { hash: '' },
    window: { addEventListener() {} },
    localStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value) },
    setTimeout: () => 1, clearTimeout() {},
  });
  const source = fs.readFileSync(path.join(__dirname, '../songbird/studio/studio.js'), 'utf8');
  vm.runInContext(source.replace(/\nmain\(\);\s*$/, '\n'), context);
  const run = (source) => vm.runInContext(source, context);
  run('state.start = {title: "Song", from: "home", machine: {label: "test"}, day: "2026-09-27"}');
  return { context, run, nodes, storage };
}
const plain = (value) => JSON.parse(JSON.stringify(value));

test('a batch of phrase and order edits is one independent, reversible transaction', () => {
  const { run } = studio();
  run(`const patch = {"tune.line": {pitch: 2}, "form.order": [1, 0]}; setEdits(patch, "Move phrase"); patch["tune.line"].pitch = 99`);
  assert.deepEqual(plain(run('state.edits')), { 'tune.line': { pitch: 2 }, 'form.order': [1, 0] });
  assert.equal(run('state.undo.length'), 1);
  run('travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits')), {});
  run('travelHistory("redo")');
  assert.equal(run('state.edits["tune.line"].pitch'), 2);
  run('travelHistory("undo"); setEdit("tempo", 100)');
  assert.equal(run('state.redo.length'), 0);
});

test('no-op changes leave history intact and null clears only the requested paths', () => {
  const { run } = studio();
  run('setEdits({tempo: 100, mode: "dorian"}); setEdit("tempo", 100); clearEdits(["missing"])');
  assert.equal(run('state.undo.length'), 1);
  run('clearEdits(["tempo"]); travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits')), { tempo: 100, mode: 'dorian' });
});

test('a timeline drag becomes one undo and ephemeral date/chance are not saved', () => {
  const { run, storage } = studio();
  run('setDay(1, "day"); setDay(10, "day"); setDay(30, "day")');
  assert.equal(run('state.undo.length'), 1);
  assert.equal(run('state.edits.date'), '2026-10-27');
  run('state.historyGroup = null; setEdit("roll", 2); setEdit("tempo", 100)');
  assert.deepEqual(JSON.parse([...storage.values()][0]), { tempo: 100 });
  run('travelHistory("undo"); travelHistory("undo"); travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits')), {});
});

test('inline alternatives match focused multi-word labels at word boundaries, with explicit fallbacks', () => {
  const { run } = studio();
  const result = plain(run(`lyricMatches(["The stall holds *all*, in the old town.", "A lantern waits."], [
    {slot: "size", sung: "all", options: ["all"]},
    {slot: "place", sung: "old town", options: ["old town"]},
    {slot: "light", sung: "lan-tern", labels: {"lan-tern": "lantern"}},
    {slot: "missing", sung: "unheard"}
  ])`));
  assert.equal(result.matches[0][0].start, 16);
  assert.equal(result.matches[0][1].slot.slot, 'place');
  assert.equal(result.matches[1][0].slot.slot, 'light');
  assert.equal(result.missing[0].slot, 'missing');
});

test('shared refrain words retain other held slots, while local words retain their couplet and head', () => {
  const { run } = studio();
  run(`state.edits = {"words.refrain": {when: "today"}, "words.refrain.1": {id: "home", head: "canon"}};
    const opts = {block: "refrain", path: "words.refrain.1", words: [{slot: "when", once: true}]};
    chooseSlot(opts, "when", "tonight"); chooseSlot(opts, "place", "garden")`);
  assert.deepEqual(plain(run('state.edits')), {
    'words.refrain': { when: 'tonight' },
    'words.refrain.1': { id: 'home', head: 'canon', slots: { place: 'garden' } },
  });
});

test('an older song response cannot replace a later version after undo returns to the same edits', async () => {
  const { run, context } = studio();
  const pending = [];
  context.request = () => new Promise((resolve) => pending.push(resolve));
  run('api = request; render = () => {}; renderWords = () => {}; loadCompare = () => {}');
  const older = run('refresh()');
  run('setEdit("tempo", 100); travelHistory("undo")');
  const newer = run('refresh()');
  pending[1]({ title: 'newest', words: [] });
  await newer;
  pending[0]({ title: 'stale', words: [] });
  await older;
  assert.equal(run('state.view.title'), 'newest');
});

test('a slower listen request cannot hijack the current preview', async () => {
  const { run, context, nodes } = studio();
  const pending = [];
  context.request = () => new Promise((resolve) => pending.push(resolve));
  run('api = request; refreshReady = () => {}; state.view = {words: [{index: 0, label: "Verse"}]}');
  const older = run('listen("you", 0)');
  const newer = run('listen("you", null)');
  pending[1]({ state: 'done', url: '/new.flac' });
  await newer;
  pending[0]({ state: 'done', url: '/old.flac' });
  await older;
  assert.equal(nodes.get('audio').src, '/new.flac');
  run('setEdit("tempo", 100)');
  assert.match(nodes.get('nowSub').textContent, /Earlier version/);
});

test('solo switches players and restores the original gain edits in one undoable batch', () => {
  const { run } = studio();
  run(`state.edits = {"band.lute": 0.7, tempo: 100};
    const bandCard = {players: {lute: "Lute", fiddle: "Fiddle"}, band: {lute: 0.7, fiddle: 0.4}};
    soloPlayer(bandCard, "lute")`);
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, 'band.fiddle': 0, tempo: 100 });
  run('soloPlayer(bandCard, "fiddle")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0, 'band.fiddle': 0.4, tempo: 100 });
  run('soloPlayer(bandCard, "fiddle")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, tempo: 100 });
  run('travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0, 'band.fiddle': 0.4, tempo: 100 });
});

test('mute restores the previous audible level instead of discarding the mix', () => {
  const { run } = studio();
  run(`const bandCard = {players: {lute: "Lute"}, band: {lute: 0.7}};
    mutePlayer(bandCard, "lute"); bandCard.band.lute = 0; mutePlayer(bandCard, "lute")`);
  assert.equal(run('state.edits["band.lute"]'), 0.7);
  assert.equal(run('state.undo.length'), 2);
});


test('starting a sketch invalidates an in-flight vocal request and preserves stale-audio tracking', async () => {
  const { run, context, nodes } = studio();
  const pending = [];
  context.request = () => new Promise((resolve) => pending.push(resolve));
  run('api = request; refreshReady = () => {}; state.view = {words: []}');
  const listening = run('listen("you", null)');
  run('pauseAudio()');
  pending[0]({ state: 'done', url: '/obsolete.flac' });
  await listening;
  assert.equal(nodes.get('audio').src, undefined);
  assert.equal(nodes.get('playPause').disabled, true);
  run('setEdit("tempo", 100)');
  assert.match(nodes.get('nowSub').textContent, /Earlier version/);
});

test('Record opens the finish panel before scrolling and reopens it when the finished result arrives', async () => {
  const { run, context, nodes } = studio();
  const pending = [];
  context.request = () => new Promise((resolve) => pending.push(resolve));
  run('api = request');
  const panel = context.document.getElementById('recordPanel');
  const details = { open: false };
  panel.ancestor = details;
  const recording = run('record()');
  assert.equal(panel.scrolledWithAncestorOpen, true);
  assert.equal(nodes.get('recordNow').disabled, true);
  details.open = false;
  run('setEdit("tempo", 100)');
  pending[0]({ state: 'done', url: '/recorded.flac', result: { recorded: { flac: 'song.flac', duration: 60, yours: 0, next: 'songbird next' } } });
  await recording;
  assert.equal(details.open, true);
  assert.equal(nodes.get('recordNow').disabled, false);
  assert.equal(run('state.recording'), false);
  nodes.get('saved').children.at(-1).listeners.click();
  assert.equal(nodes.get('audio').src, '/recorded.flac');
  assert.match(nodes.get('nowSub').textContent, /Earlier version/);
});
