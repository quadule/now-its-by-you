const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

function setup() {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {}; this.classList = {toggle() {}}; }
    append(...items) { this.children.push(...items); }
    setAttribute(name, value) { this[name] = value; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    focus() { doc.activeElement = this; }
    setSelectionRange() {}
    querySelectorAll(selector) { return this.children.flatMap((item) => [item, ...item.querySelectorAll(selector)]).filter((item) => selector.includes('textarea') ? item.tag === 'textarea' : true); }
    querySelector() { return this; }
  }
  const parent = new Element('root');
  const doc = {activeElement: null, createElement: (tag) => new Element(tag), querySelector: () => ({content: 'token'})};
  let revision = 0, edits = {}, pending, requests = 0;
  const win = {StudioBridge: {
    snapshot: () => ({revision, edits: JSON.parse(JSON.stringify(edits))}),
    replaceEdits: (next) => { edits = next; revision++; }, toast() {},
  }};
  const context = vm.createContext({document: doc, window: win, fetch: () => {requests++; return new Promise((resolve) => { pending = resolve; }); }});
  vm.runInContext(readFileSync(join(__dirname, '../songbird/studio/author.js'), 'utf8'), context);
  const view = (text = 'I sing this song.', authored = false) => ({composition: {sections: [{id: 'verse:0', index: 1, label: 'Verse 1', phrases: [{lyric_path: 'lyrics.verse:0.0', lyric_text: text, syllable_count: 4, authored}]}]}});
  const render = (v = view()) => { win.SongbirdAuthor.capture(); parent.children = []; win.SongbirdAuthor.decorate(v, parent); };
  render();
  const all = () => parent.querySelectorAll('*');
  return {
    all, render, view, input: () => all().find((x) => x.tag === 'textarea'),
    type: (text) => { const input = all().find((x) => x.tag === 'textarea'); input.value = text; input.listeners.input(); },
    save: () => all().find((x) => x.textContent === 'Use these lines').listeners.click(),
    status: () => all().find((x) => x.className === 'author-status').textContent,
    answer: (problems = []) => pending({ok: true, json: async () => ({problems})}),
    flush: () => new Promise((resolve) => setImmediate(resolve)),
    change: () => revision++, get edits() { return edits; }, get requests() { return requests; },
  };
}

test('asynchronous lyric option refresh preserves unapplied writing', () => {
  const s = setup(); s.type('We sing our song.'); const before = s.input(); s.render();
  assert.equal(s.input(), before);
  assert.equal(s.input().value, 'We sing our song.');
});

test('bad syllable counts never submit; pronunciation refusal keeps work editable', async () => {
  const s = setup(); s.type('Too short.'); s.save();
  assert.equal(s.requests, 0);
  s.type('Zzzzzz sings this song.'); s.save();
  s.answer([{path: 'lyrics.verse:0.0', why: 'unknown pronunciation'}]); await s.flush();
  assert.deepEqual(s.edits, {});
  assert.match(s.status(), /unknown pronunciation/);
  assert.equal(s.input().value, 'Zzzzzz sings this song.');
});

test('new typing while validation runs stays unapplied after saving older text', async () => {
  const s = setup(); s.type('We sing our song.'); s.save(); s.type('You sing your song.');
  s.answer(); await s.flush();
  assert.equal(s.edits['lyrics.verse:0.0'], 'We sing our song.');
  s.render(s.view('We sing our song.', true));
  assert.equal(s.input().value, 'You sing your song.');
});

test('an intervening song edit prevents an older validation replacing newer choices', async () => {
  const s = setup(); s.type('We sing our song.'); s.save(); s.change(); s.answer(); await s.flush();
  assert.deepEqual(s.edits, {});
  assert.match(s.status(), /changed while/);
});

test('the words say what the stars around a word are for', () => {
  const s = setup();
  const hint = s.all().find((x) => x.className === 'hint');
  assert.match(hint.textContent, /between stars, like \*heart\*, is the one the line leans on/);
});
