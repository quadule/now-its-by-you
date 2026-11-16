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
    localStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key) },
    setTimeout: () => 1, clearTimeout() {},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../songbird/studio/renderer.js'), 'utf8'), context);
  const source = fs.readFileSync(path.join(__dirname, '../songbird/studio/studio.js'), 'utf8');
  vm.runInContext(source.replace(/\nmain\(\);\s*$/, '\n'), context);
  const run = (source) => vm.runInContext(source, context);
  run('state.start = {title: "Song", from: "home", machine: {label: "test"}, day: "2026-09-27", song_digest: "abc123"}');
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

test('the same edits written in another order are no step to undo', () => {
  const { run } = studio();
  run('setEdits({tempo: 100, "line.verse:wire.0": {words: "a b", notes: [{degree: 1, onset: 0, duration: 1}]}})');
  run('window.StudioBridge.replaceEdits({"line.verse:wire.0": {notes: [{duration: 1, onset: 0, degree: 1}], words: "a b"}, tempo: 100})');
  assert.equal(run('state.undo.length'), 1);
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
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, 'band.fiddle': 0, 'mix.voices': 0, tempo: 100 });
  run('soloPlayer(bandCard, "fiddle")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0, 'band.fiddle': 0.4, 'mix.voices': 0, tempo: 100 });
  run('soloPlayer(bandCard, "fiddle")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, tempo: 100 });
  run('travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0, 'band.fiddle': 0.4, 'mix.voices': 0, tempo: 100 });
});

test('the voice mutes and solos like a player: a solo brings a muted voice back, and its release the mute', () => {
  const { run } = studio();
  run(`state.edits = {"band.lute": 0.7};
    const bandCard = {players: {lute: "Lute", fiddle: "Fiddle"}, band: {lute: 0.7, fiddle: 0.4}};
    muteVoice()`);
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, 'mix.voices': 0 });
  run('soloPlayer(bandCard, VOICE)');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0, 'band.fiddle': 0 });
  assert.equal(run('currentSolo().player'), 'voice');
  run('soloPlayer(bandCard, "lute")');  // from the voice alone to a player alone
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, 'band.fiddle': 0, 'mix.voices': 0 });
  run('soloPlayer(bandCard, "lute")');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, 'mix.voices': 0 });
  run('muteVoice()');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7 });
  // a parent's mute handed down is the program's own: unmuting is the choice, muting again gives it back
  run('state.view = {cards: [{id: "mix", mix: {voices: 0}}]}; muteVoice()');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7, 'mix.voices': 1 });
  run('muteVoice()');
  assert.deepEqual(plain(run('state.edits')), { 'band.lute': 0.7 });
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
  assert.equal(nodes.get('record').disabled, true);
  details.open = false;
  run('setEdit("tempo", 100)');
  pending[0]({ state: 'done', url: '/recorded.flac', result: { recorded: { flac: 'song.flac', duration: 60, yours: 0, next: 'songbird next' } } });
  await recording;
  assert.equal(details.open, true);
  assert.equal(nodes.get('record').disabled, false);
  assert.equal(run('state.recording'), false);
  // the export, ready: its Play is the one button in it here (no Download: this studio saved the file; no Share)
  const pressable = (node) => (node?.listeners?.click ? [node] : (node?.children || []).flatMap(pressable));
  const buttons = pressable(nodes.get('saved'));
  assert.equal(buttons.length, 1);
  buttons[0].listeners.click();
  assert.equal(nodes.get('audio').src, '/recorded.flac');
  assert.match(nodes.get('nowSub').textContent, /Earlier version/);
});


test('authored lines never receive bank controls and hidden bank words have no fallback controls', () => {
  const { run } = studio();
  const result = plain(run(`lyricMatches(["My lantern is different", "The lantern stays"], [
    {slot: "light", sung: "lantern", options: ["lantern", "candle"]},
    {slot: "feeling", sung: "different", options: ["different", "familiar"]}
  ], [0])`));
  assert.equal(result.matches[0].length, 0);
  assert.equal(result.matches[1][0].slot.slot, 'light');
  const children = run(`inlineLyrics({block: "verse", nth: 0, label: "Verse", lines: ["My lantern"], authored: [0]}, {
    words: [{slot: "light", sung: "lantern", options: ["lantern", "candle"]}]
  }).children`);
  assert.equal(children.length, 1);
  assert.equal(children[0].className, 'lyric-line');
});


test('Reset words releases inherited and local original lines in the selected section as one undo', () => {
  const { run } = studio();
  run(`state.edits = {"words.verse.0": {id: "home"}, "lyrics.verse:home.2": "My new line", "lyrics.verse:away.0": "Another verse", tempo: 100};
    state.view = {composition: {sections: [{index: 2, id: "verse:0", lyric_key: "verse:home", phrases: [
      {lyric_path: "lyrics.verse:home.0", authored: true}, {lyric_path: "lyrics.verse:home.1", authored: false},
      {lyric_path: "lyrics.verse:home.2", authored: true}
    ]}]}};
    undoWords({index: 2, name: "verse", block: "verse", nth: 0, path: "words.verse.0", label: "Verse 1", authored: [0, 2]})`);
  assert.deepEqual(plain(run('state.edits')), {
    'lyrics.verse:home.0': null, 'lyrics.verse:home.2': null, 'lyrics.verse:away.0': 'Another verse', tempo: 100,
  });
  assert.equal(run('state.undo.length'), 1);
  run('travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits')), {
    'words.verse.0': { id: 'home' }, 'lyrics.verse:home.2': 'My new line', 'lyrics.verse:away.0': 'Another verse', tempo: 100,
  });
});

test('Reset words uses the second bridge identity and clears pending text without touching the first bridge', () => {
  const { run } = studio();
  run(`state.edits = {"words.bridge2": "then", "lyrics.bridge:0.0": "First bridge", "lyrics.bridge2:0.1": "Pending text"};
    state.view = {words: [{index: 0, name: "bridge"}, {index: 1, name: "bridge2"}], composition: {sections: [
      {index: 0, id: "bridge:0", lyric_key: "bridge:0", phrases: []}, {index: 1, id: "bridge2:0", lyric_key: "bridge2:0", phrases: []}]}};
    undoWords({index: 1, name: "bridge2", block: "bridge", nth: 1, path: "words.bridge2", label: "Bridge 2", authored: [0]})`);
  assert.deepEqual(plain(run('state.edits')), {
    'lyrics.bridge:0.0': 'First bridge', 'lyrics.bridge2:0.0': null, 'lyrics.bridge2:0.1': null,
  });
});


test('Sound shape controls defer to a custom arrangement and release it in one undoable transaction', () => {
  const { run } = studio();
  run(`state.start.bounds = {}; state.start.optional = ["intro"]; state.start.parts = {intro: "Intro"};
    state.view = {composition: {arranged: true}};
    state.edits = {"form.order": ["verse:0", "intro:0"], "form.intro": true, tempo: 100, "lyrics.verse:0.0": "My line"};
    const shapeControls = editor({id: "shape", parts: {}, choices: []});`);
  const tree = run('shapeControls');
  const nodes = (node) => typeof node === 'object' ? [node, ...node.children.flatMap(nodes)] : [];
  const buttons = nodes(tree).filter((node) => node.tagName === 'BUTTON');
  assert.deepEqual(buttons.map((node) => node.children.join('')), ['Open Tune', "Use the song's shape"]);
  assert.ok(buttons.every((node) => !Object.hasOwn(node, 'aria-pressed')));
  buttons[1].listeners.click();
  assert.deepEqual(plain(run('state.edits')), { 'form.order': null, tempo: 100, 'lyrics.verse:0.0': 'My line' });
  assert.equal(run('state.undo.length'), 1);
  run('travelHistory("undo")');
  assert.deepEqual(plain(run('state.edits["form.order"]')), ['verse:0', 'intro:0']);
});

test('a template part omitted from server choices is disabled rather than offered as an edit', () => {
  const { run } = studio();
  run(`state.start.bounds = {}; state.start.optional = ["intro"]; state.start.parts = {intro: "Intro"};
    state.view = {composition: {arranged: false}};`);
  const tree = run('editor({id: "shape", parts: {intro: true}, choices: []})');
  const nodes = (node) => typeof node === 'object' ? [node, ...node.children.flatMap(nodes)] : [];
  const toggle = nodes(tree).find((node) => node.tagName === 'BUTTON');
  assert.ok(Object.hasOwn(toggle, 'disabled'));
  assert.equal(toggle['aria-pressed'], 'true');
});

test('saved edits are kept under the song genome\'s digest, and older ones keep only choices any genome takes', () => {
  const { run, storage } = studio();
  run('setEdit("tempo", 100)');
  assert.deepEqual([...storage.keys()], ['songbird-studio|Song|home|test|abc123']);
  run('state.start.song_digest = "def456"');
  assert.deepEqual(plain(run('restore()')), {});  // another genome: its tune and lines aren't this one's
  storage.clear();
  storage.set('songbird-studio|Song|home|test', JSON.stringify({
    tempo: 90, 'band.lute': 0.5, 'tune.v1': [{degree: 1, onset: 0, duration: 1}], 'lyrics.verse:0.0': 'A line',
    'form.order': ['verse:0'], 'words.verse.0': {id: 'home'},
  }));
  assert.deepEqual(plain(run('restore()')), { tempo: 90, 'band.lute': 0.5 });
  assert.equal(storage.has('songbird-studio|Song|home|test'), false);
  assert.deepEqual(JSON.parse(storage.get('songbird-studio|Song|home|test|def456')), { tempo: 90, 'band.lute': 0.5 });
  assert.deepEqual(plain(run('restore()')), { tempo: 90, 'band.lute': 0.5 });
});

test('the song\'s length is shown beside the tempo and key', () => {
  const { run, nodes } = studio();
  run(`state.start.bounds = {tempo: {min: 60, max: 120, step: 0.5}};
    state.view = {cards: [{id: "tempo", tempo: 96}], composition: {duration: 187.4}}; renderSessionControls()`);
  const shown = nodes.get('sessionControls').children.at(-1);
  assert.equal(shown.className, 'session-duration hint');
  assert.equal(shown.children.join(''), 'Length 3:07');
});

test('the masthead counts the padlocks a person sees: a cell\'s lock is one, not its three paths', () => {
  const { run } = studio();
  const held = ['arrange.verse:0.synthpad.level', 'arrange.verse:0.synthpad.pattern', 'arrange.verse:0.synthpad.from',
    'style.stripped', 'words.verse.0'];
  assert.equal(run(`lockCount(${JSON.stringify(held)})`), 2);  // the EDM test's two padlocks, said as four
  assert.equal(run('lockCount(["arrange.verse:0.synthpad.level", "arrange.refrain:1.synthpad.level"])'), 2);
  assert.equal(run('lockCount([])'), 0);
});

test('a checked paste is atomic and explicit releases also override inherited parts', async () => {
  const s = studio(); let sent;
  s.context.fetch = async (_, options) => { sent = JSON.parse(options.body); return { ok: true, json: async () => ({ problems: [] }) }; };
  await s.run('applyPatch({"part.guitar.verse:0.0": null, "lyrics.verse:wire.0": "We sing now"}, "Paste phrase")');
  assert.equal(sent.edits['part.guitar.verse:0.0'], null);
  assert.equal(s.run('state.undo.length'), 1);
  s.run('travelHistory("undo")');
  assert.deepEqual(plain(s.run('state.edits')), {});
  s.context.fetch = async () => ({ ok: true, json: async () => ({ problems: [{ path: 'lyrics.verse:wire.0', why: 'unknown word' }] }) });
  await assert.rejects(s.run('applyPatch({"lyrics.verse:wire.0":"invalid", tempo: 90})'), /unknown word/);
  assert.deepEqual(plain(s.run('state.edits')), {});
});
test('a slow paste cannot overwrite a newer edit', async () => {
  const s = studio(); let resolve;
  s.context.fetch = () => new Promise((r) => { resolve = r; });
  const pending = s.run('applyPatch({tempo: 80}, "Paste")');
  s.run('setEdit("tempo", 100)');
  resolve({ ok: true, json: async () => ({ problems: [] }) });
  await assert.rejects(pending, /song changed/);
  assert.equal(s.run('state.edits.tempo'), 100);
});

test('an edit is said in words, never by its path: the rolls, the lines, the parts, the tempo and the mode', () => {
  const { run } = studio();
  run('state.view = {composition: {players: [{name: "drummachine", label: "Drum machine"}]}}');
  const said = (path) => run(`describePath(${JSON.stringify(path)})`);
  assert.equal(said('line.verse:wire.0'), 'your words and tune for line 1 of a verse');
  assert.equal(said('lyrics.refrain:0.2'), 'your words for line 3 of the refrain');
  assert.equal(said('line.bridge2:0.0'), 'your words and tune for line 1 of the second bridge');
  assert.equal(said('tune.a1'), 'your tune for a line');
  assert.equal(said('tune.verse:1.0'), 'your tune for verse 2, line 1');
  assert.equal(said('chords.bridge2:last.1'), 'your chords for the last second bridge, line 2');
  assert.equal(said('part.drummachine.verse:1.0'), 'your drum machine in verse 2, line 1');
  assert.equal(said('tempo'), 'the tempo');
  assert.equal(said('mode'), 'the mode');
  assert.equal(said('tonic'), 'the key');
  for (const path of ['line.verse:wire.0', 'part.fiddle.refrain:0.3', 'tune.b2', 'chords.a1', 'tempo', 'mode', 'tune.chorus:0.x.y', 'something:odd.3']) {
    assert.doesNotMatch(said(path), /[:.]\w|\.\d/, path);
  }
});
