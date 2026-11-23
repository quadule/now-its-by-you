const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');

function setup(opts = {}) {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.listeners = {}; this.classList = {toggle() {}}; }
    append(...items) { for (const item of items) if (item && typeof item === 'object') item.parentNode = this; this.children.push(...items); }
    setAttribute(name, value) { this[name] = value; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    focus() { doc.activeElement = this; }
    setSelectionRange() {}
    querySelectorAll(selector) { return this.children.flatMap((item) => [item, ...item.querySelectorAll(selector)]).filter((item) => selector.includes('textarea') ? item.tag === 'textarea' : true); }
    querySelector() { return this; }
    replaceChildren(...items) { this.children = []; this.append(...items); }
  }
  const parent = new Element('root');
  const doc = {activeElement: null, createElement: (tag) => new Element(tag), querySelector: () => ({content: 'token'})};
  let revision = 0, edits = {}, pending, requests = 0;
  const win = {SongbirdModel: require('../songbird/studio/model.js'), StudioBridge: {
    snapshot: () => ({revision, edits: JSON.parse(JSON.stringify(edits))}),
    replaceEdits: (next) => { edits = next; revision++; }, toast() {},
  }};
  const fetch = (url, init) => {
    if (url === '/api/syllables') return Promise.resolve({ok: true, json: async () => opts.syllables(JSON.parse(init.body).lines)});
    requests++; return new Promise((resolve) => { pending = resolve; });
  };
  const timers = opts.syllables ? {setTimeout: (f) => setImmediate(f), clearTimeout: () => {}} : {};
  const context = vm.createContext({document: doc, window: win, fetch, ...timers});
  vm.runInContext(readFileSync(join(__dirname, '../songbird/studio/author.js'), 'utf8'), context);
  const view = (text = 'I sing this song.', authored = false) => ({composition: {sections: [{id: 'verse:0', index: 1, label: 'Verse 1', phrases: [{lyric_path: 'lyrics.verse:0.0', lyric_text: text, syllable_count: 4, authored}]}]}});
  const render = (v = view()) => { win.SongbirdAuthor.capture(); parent.children = []; win.SongbirdAuthor.decorate(v, parent); };
  render();
  const all = () => parent.querySelectorAll('*');
  return {
    all, render, view, line: (...a) => win.SongbirdAuthor.line(...a), get say() { return win.SongbirdAuthor.say; }, element: (tag) => new Element(tag), input: () => all().find((x) => x.tag === 'textarea'),
    type: (text) => { const input = all().find((x) => x.tag === 'textarea'); input.value = text; input.listeners.input(); },
    save: () => all().find((x) => x.textContent === 'Use these lines').listeners.click(),
    status: () => all().find((x) => x.className === 'author-status').textContent,
    answer: (problems = []) => pending({ok: true, json: async () => ({problems})}),
    flush: () => new Promise((resolve) => setImmediate(resolve)),
    change: () => revision++, get edits() { return edits; }, get requests() { return requests; }, win,
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

test('the words say what the stars around a word are for (in the tooltip: the hint itself is one short rule)', () => {
  const s = setup();
  const hint = s.all().find((x) => x.className === 'hint');
  assert.match(hint.textContent, /one syllable a note/i);
  assert.match(hint.title, /between stars, like \*heart\*, is the one the line leans on/);
  assert.match(s.input().title, /between stars/);
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
  assert.match(first.status(), /in your song/i);
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

// Words said two ways (songbird/heteronyms.py): the editor applies the Python's rules to a line as it's typed, from the
// table the view sends; both read tests/golden/say-*.json (tests/test_heteronyms.py pins them to the Python).
const TABLE = JSON.parse(readFileSync(join(__dirname, 'golden/say-table.json'), 'utf8'));
const DECIDED = JSON.parse(readFileSync(join(__dirname, 'golden/say-lines.json'), 'utf8'));
const withSay = (text, said, authored = false) => ({composition: {say: TABLE, sections: [{id: 'verse:0', index: 1, label: 'Verse 1',
  phrases: [{lyric_path: 'lyrics.verse:0.0', lyric_text: text, syllable_count: 11, authored, ...(said ? {said} : {})}]}]}});
const chips = (s) => s.all().filter((x) => typeof x.className === 'string' && x.className.startsWith('chip'));
const shown = (s) => chips(s).map((c) => `${c.textContent}${c['aria-pressed'] === 'true' ? '*' : ''}`).join(' ');

test('the rules in the editor are the singer\'s: every line decided as songbird/heteronyms.py decides it', () => {
  const s = setup(); s.render(withSay('I sing this song.'));
  for (const [line, want] of Object.entries(DECIDED)) assert.equal(s.say.decide(line), want, line);
  assert.equal(s.say.syllables('The bass{fish} is a heart-beat'), 6, 'a say is no syllable');
  assert.equal(s.say.syllables('min-ute{my-newt} to go'), 4);
});

test('a typed line shows its word said two ways, the rules\' way chosen; choosing the other writes it into the line', async () => {
  const s = setup(); s.render(withSay('I sing this song.'));
  assert.equal(chips(s).length, 0, 'no word said two ways: nothing shown');
  s.type('The bass is a heart-beat that no-bo-dy wrote');
  assert.equal(shown(s), 'low note* fish');
  const group = s.all().find((x) => x.className === 'say-word');
  assert.match(group.title, /chose this from the words around it/);
  assert.equal(s.all().find((x) => x.className === 'say-name').textContent, 'bass:');
  assert.match(chips(s)[1].title, /Sung like “mass”/);
  chips(s)[1].listeners.click();  // fish
  assert.equal(s.input().value, 'The bass{fish} is a heart-beat that no-bo-dy wrote');
  assert.equal(shown(s), 'low note fish*');
  assert.match(chips(s)[1].className, /\bon you\b/, 'a person\'s choice is marked theirs');
  assert.match(s.status(), /Not in the song until you use it/);
  s.save();
  s.answer(); await s.flush();
  assert.equal(s.edits['lyrics.verse:0.0'], 'The bass{fish} is a heart-beat that no-bo-dy wrote', 'stored with the line');
  chips(s)[0].listeners.click();  // back to the low note: the say is replaced, not added
  assert.equal(s.input().value, 'The bass{low} is a heart-beat that no-bo-dy wrote');
});

test('the rules follow the words: a fish in the line makes it the fish; punctuation and stars stay put', () => {
  const s = setup(); s.render(withSay('I sing this song.'));
  s.type('The fish that he caught was a *bass*, by the sea');
  assert.equal(shown(s), 'low note fish*');
  chips(s)[0].listeners.click();
  assert.equal(s.input().value, 'The fish that he caught was a *bass{low}*, by the sea');
});

test('the song\'s own line shows the way the song sings it, until it\'s typed over', () => {
  const s = setup();
  s.render(withSay('the wind took it down to the farms in the vale,', [{index: 1, word: 'wind', chosen: 'turn', by: 'song'}]));
  assert.equal(shown(s), 'air turn*');
  assert.match(s.all().find((x) => x.className === 'say-word').title, /As the song sings it/);
  s.type('the wind took it down to the farms in the dale,');
  assert.equal(shown(s), 'air* turn', 'typed: the rules choose');
});

test('a say of the person\'s own that is no sense shows as theirs', () => {
  const s = setup(); s.render(withSay('I sing this song.'));
  s.type('The bass{base} is a heart-beat that no-bo-dy wrote');
  assert.equal(shown(s), 'low note fish');
  assert.equal(s.all().find((x) => x.className === 'say-own').textContent, 'your way: {base}');
});

test('fitting new words stores their notes atomically, and later words preserve the custom melody', async () => {
  const s = setup(), v = s.view();
  const p = v.composition.sections[0].phrases[0];
  Object.assign(p, { own_path: 'line.verse:wire.0', duration_beats: 4, pickup_beats: 0,
    bounds: { min_onset: 0, max_end: 4, max_final_onset: 3.75, min_duration: 0.25 },
    notes: [1, 3, 5, 1].map((degree, i) => ({ degree, onset: i, duration: 1 })) });
  s.render(v); s.type('We sing now');
  s.all().find((x) => x.textContent === 'Fit notes to words').listeners.click();
  s.answer(); await s.flush();
  const entry = s.edits['line.verse:wire.0'];
  assert.equal(entry.words, 'We sing now'); assert.equal(entry.notes.length, 3);
  Object.assign(p, { own: 'verse:wire.0', lyric_text: entry.words, syllable_count: 3, notes: entry.notes });
  s.render(v); s.type('We sing here'); s.save(); s.answer(); await s.flush();
  assert.equal(s.edits['line.verse:wire.0'].words, 'We sing here');
  assert.deepEqual(s.edits['line.verse:wire.0'].notes, entry.notes);
});

test('the whole lyric at once: each paragraph onto the next section, a changed count fitted, one checked patch, and why a line is refused beside it', async () => {
  const s = setup(), calls = [];
  const phrase = (key, i, text, count) => ({lyric_path: `lyrics.${key}.${i}`, own_path: `line.${key}.${i}`, lyric_text: text, syllable_count: count,
    tune_syllable_count: count, duration_beats: 4, pickup_beats: 0, bounds: {min_onset: 0, max_end: 4, max_final_onset: 3.5, min_duration: 0.25},
    notes: Array.from({length: count}, (_, k) => ({degree: k + 1, onset: k * 0.5, duration: 0.5}))});
  const v = {composition: {sections: [
    {id: 'verse:0', lyric_key: 'verse:0', label: 'Verse 1', sung: true, phrases: [phrase('verse:0', 0, 'I sing this song', 4), phrase('verse:0', 1, 'you sing it too', 4)]},
    {id: 'refrain:0', lyric_key: 'refrain', label: 'Refrain 1', sung: true, phrases: [phrase('refrain', 0, 'now it is yours', 4)]},
    {id: 'refrain:1', lyric_key: 'refrain', label: 'Refrain 2', sung: true, phrases: [phrase('refrain', 0, 'now it is yours', 4)]}]}};
  let refuse = null;
  s.win.StudioBridge.applyPatch = async (patch) => { calls.push(patch); if (refuse) throw Object.assign(new Error('no'), {problems: refuse}); return true; };
  const box = s.win.SongbirdAuthor.sheet(v);
  const find = (pred) => [box, ...box.querySelectorAll('*')].find(pred);
  find((x) => x.textContent === 'Write lyrics').listeners.click();
  const text = find((x) => x.tag === 'textarea');
  assert.equal(text.value, '[Verse 1]\nI sing this song\nyou sing it too\n\n[Refrain 1]\nnow it is yours', 'a refrain once');
  // a paragraph too many is refused before anything is checked
  text.value = 'a b c d\n\ne f g h\n\ni j k l'; text.listeners.input();
  find((x) => x.textContent === 'Use these words').listeners.click();
  assert.equal(calls.length, 0);
  assert.match(find((x) => x.className === 'author-status').textContent, /This song has 2 sung sections, not 3\./);
  // the first line kept, the second longer (its notes fitted), the refrain's the same count
  text.value = 'I sing this song\nyou sing it to me now\n\nnow it is ours'; text.listeners.input();
  assert(find((x) => x.className === 'unit' && /notes fitted/.test(x.textContent)), 'said under the field');
  refuse = [{path: 'lyrics.refrain.0', why: "the singer can't say “ours” yet"}];
  await find((x) => x.textContent === 'Use these words').listeners.click();
  assert.deepEqual(Object.keys(calls[0]).sort(), ['line.verse:0.1', 'lyrics.refrain.0'], 'one patch: the unchanged line left out');
  assert.equal(calls[0]['line.verse:0.1'].notes.length, 6);
  assert.equal(calls[0]['lyrics.refrain.0'], 'now it is ours');
  assert(find((x) => x.className === 'problem' && /“ours”/.test(x.textContent)), 'the refusal beside its line');
  refuse = null;
  await find((x) => x.textContent === 'Use these words').listeners.click();
  assert.equal(calls.length, 2);
  assert.equal(find((x) => x.className === 'lyric-sheet-panel').hidden, true, 'used: the field closes');
});

test('words written whole are counted and sent as the singer splits them (POST /api/syllables)', async () => {
  const s = setup({syllables: (lines) => lines.map((l) => (l.text === 'My father sings.'
    ? {text: 'My fa-ther sings.', count: 4} : {text: l.text, count: l.text.split(/[\s-]+/).filter(Boolean).length}))});
  s.type('My father sings.');
  for (let i = 0; i < 4; i++) await s.flush();
  const tally = s.all().filter((x) => / \/ 4$/.test(String(x.textContent || ''))).map((x) => x.textContent);
  assert.deepEqual(tally, ['4 / 4'], 'the count is the program\'s');
  s.save(); s.answer(); await s.flush();
  assert.equal(s.edits['lyrics.verse:0.0'], 'My fa-ther sings.');
  assert.equal(s.input().value, 'My fa-ther sings.');  // the field shows how it was split
});
