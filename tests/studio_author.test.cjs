const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

function setup() {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {}; this.classList = {toggle() {}}; }
    append(...items) { for (const item of items) if (item && typeof item === 'object') item.parentNode = this; this.children.push(...items); }
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
    all, render, view, line: (...a) => win.SongbirdAuthor.line(...a), element: (tag) => new Element(tag), input: () => all().find((x) => x.tag === 'textarea'),
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

test('"Use this line" uses this line only; another typed stays a draft, and a refusal refuses only this one', async () => {
  const s = setup();
  const two = {composition: {sections: [{id: 'verse:0', index: 1, label: 'Verse 1', phrases: [
    {lyric_path: 'lyrics.verse:0.0', lyric_text: 'I sing this song.', syllable_count: 4},
    {lyric_path: 'lyrics.verse:0.1', lyric_text: 'You hear it now.', syllable_count: 4}]}]}};
  const find = (anchor, pred) => anchor.children.flatMap((k) => [k, ...(k.children || [])]).find(pred);
  const ui = (j, next = null) => {
    const anchor = s.element('div');
    s.line(two, 'verse:0', j, anchor, {next});
    return {anchor, input: find(anchor, (k) => k.tag === 'textarea'), use: find(anchor, (k) => k.textContent === 'Use this line'),
      status: () => find(anchor, (k) => k.className === 'author-status').textContent};
  };
  let moved = 0;
  const first = ui(0, () => moved++), second = ui(1);
  assert.ok(!find(first.anchor, (k) => k.textContent === 'Use these lines'), 'one line, one button');
  second.input.value = 'They hear it now.'; second.input.listeners.input();  // a draft in line 2
  first.input.value = 'We sing this song.'; first.input.listeners.input();
  first.use.listeners.click();
  assert.equal(s.requests, 1);
  second.use.listeners.click();  // used while line 1 is checked: waits its turn
  assert.equal(s.requests, 1);
  assert.match(second.status(), /Waiting/);
  s.answer(); await s.flush(); await s.flush();
  assert.deepEqual(JSON.parse(JSON.stringify(s.edits)), {'lyrics.verse:0.0': 'We sing this song.'}, 'line 1 alone, not line 2 with it');
  assert.equal(moved, 1, 'the column moves on to the next line');
  assert.equal(s.requests, 2);
  s.answer([{path: 'lyrics.verse:0.1', why: 'unknown pronunciation'}]); await s.flush(); await s.flush();
  assert.deepEqual(JSON.parse(JSON.stringify(s.edits)), {'lyrics.verse:0.0': 'We sing this song.'}, 'line 2 refused alone; line 1 kept');
  assert.match(second.status(), /Line 2: unknown pronunciation/);
  assert.match(first.status(), /in your song/);
});

test('a line redrawn in the inspector keeps its hint and never writes out a null', () => {
  const s = setup();
  for (const pass of [1, 2, 3]) {  // the score redraws the column on every change: the hint moved out stays found
    const anchor = s.element('div');
    s.line(s.view(), 'verse:0', 0, anchor);
    const kids = anchor.children;
    assert.ok(kids.every((k) => k && typeof k === 'object'), `pass ${pass}: nothing null among the line's parts`);
    assert.ok(kids.some((k) => k.className === 'hint'), `pass ${pass}: the hint is there`);
    assert.ok(!kids.some((k) => k.tag === 'details'), `pass ${pass}: not the whole section's editor`);
  }
});
