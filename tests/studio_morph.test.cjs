// Run with `node --test tests/studio_morph.test.cjs`: the score's column, grid and mix drawn again in place
// (songbird/studio/studio.js morph; docs/history/STUDIO-EDM-TEST.md, second attempt, bugs 1 and 2). A node the new drawing
// has in the same place is kept and given the new one's attributes, text, value and listeners, so an answer that
// lands mid-click neither replaces the button under the pointer nor moves what didn't change.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// a small DOM: enough of Node and Element for h(), morph() and a click
class Node {
  constructor(type, name) { this.nodeType = type; this.nodeName = name; this.childNodes = []; this.parentNode = null; }
  get lastChild() { return this.childNodes.at(-1) || null; }
  get firstChild() { return this.childNodes[0] || null; }
  get children() { return this.childNodes.filter((c) => c.nodeType === 1); }
  get textContent() { return this.nodeType === 3 ? this.data : this.childNodes.map((c) => c.textContent).join(''); }
  set textContent(t) { this.childNodes = []; if (t !== '') this.appendChild(new Text(String(t))); }
  detach() { if (this.parentNode) { const p = this.parentNode; p.childNodes.splice(p.childNodes.indexOf(this), 1); this.parentNode = null; } }
  appendChild(n) { n.detach(); n.parentNode = this; this.childNodes.push(n); return n; }
  append(...ns) { for (const n of ns) this.appendChild(typeof n === 'object' ? n : new Text(String(n))); }
  replaceChild(n, o) { n.detach(); const i = this.childNodes.indexOf(o); this.childNodes[i] = n; n.parentNode = this; o.parentNode = null; return o; }
  removeChild(o) { o.detach(); return o; }
}
class Text extends Node { constructor(data) { super(3, '#text'); this.data = data; } }
class Element extends Node {
  constructor(tag) { super(1, tag.toUpperCase()); this.attrs = new Map(); this.heard = {}; this.value = ''; this.checked = false; this.type = ''; }
  get attributes() { return [...this.attrs].map(([name, value]) => ({ name, value })); }
  get className() { return this.attrs.get('class') || ''; }
  set className(v) { this.attrs.set('class', v); }
  setAttribute(k, v) { this.attrs.set(k, String(v)); if (k === 'value') this.value = String(v); if (k === 'type') this.type = String(v); }
  getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
  hasAttribute(k) { return this.attrs.has(k); }
  removeAttribute(k) { this.attrs.delete(k); }
  addEventListener(type, fn) { (this.heard[type] ||= []).push(fn); }
  dispatch(type) { for (const fn of this.heard[type] || []) fn({ type, target: this, currentTarget: this }); }
  matches() { return false; }
}
function load() {
  const document = {
    activeElement: null,
    createElement: (tag) => new Element(tag), createElementNS: (_, tag) => new Element(tag), createTextNode: (t) => new Text(t),
    getElementById: () => new Element('div'), querySelector: (s) => (s.startsWith('meta') ? { content: 'token' } : null), querySelectorAll: () => [],
    addEventListener() {},
  };
  const context = vm.createContext({ document, Node, console, URL, location: { hash: '' }, window: { addEventListener() {} },
    localStorage: { getItem() {}, setItem() {}, removeItem() {} }, setTimeout: () => 1, clearTimeout() {} });
  const source = fs.readFileSync(path.join(__dirname, '../songbird/studio/studio.js'), 'utf8');
  vm.runInContext(source.replace(/\nmain\(\);\s*$/, '\n'), context);
  return { h: context.h, morph: context.morph, document };
}

test('a button redrawn in place is the same node, with the new drawing\'s class, text and listener', () => {
  const { h, morph } = load();
  const box = h('div', {});
  const heard = [];
  morph(box, [h('p', { class: 'set' }, 'a riser'), h('button', { class: 'chip', onclick: () => heard.push('old') }, 'a snare roll')]);
  const button = box.childNodes[1];
  morph(box, [h('p', { class: 'set' }, 'a riser over 2 bars, a snare roll'), h('button', { class: 'chip on you', 'aria-pressed': 'true', onclick: () => heard.push('new') }, 'a snare roll')]);
  assert.equal(box.childNodes[1], button, 'the node under the pointer is kept');
  assert.equal(button.className, 'chip on you');
  assert.equal(button.getAttribute('aria-pressed'), 'true');
  assert.equal(box.childNodes[0].textContent, 'a riser over 2 bars, a snare roll');
  button.dispatch('click');
  assert.deepEqual(heard, ['new'], 'its listener is the new drawing\'s, once');
});

test('a listener added after h(), a new kind of listener, and one the new drawing hasn\'t got', () => {
  const { h, morph } = load();
  const box = h('div', {});
  const heard = [];
  const first = h('select', { onfocus: () => heard.push('focus-old') }, h('option', { value: 'a' }, 'a'));
  first.addEventListener('change', () => heard.push('change-old'));
  morph(box, [first]);
  const next = h('select', { oninput: () => heard.push('input-new') }, h('option', { value: 'a' }, 'a'), h('option', { value: 'b' }, 'b'));
  next.addEventListener('change', (e) => heard.push(`change-new:${e.target === first}`));
  next.value = 'b';
  morph(box, [next]);
  assert.equal(box.childNodes[0], first);
  assert.equal(first.childNodes.length, 2);
  assert.equal(first.value, 'b', 'its value is the new drawing\'s');
  for (const type of ['change', 'input', 'focus']) first.dispatch(type);
  assert.deepEqual(heard, ['change-new:true', 'input-new'], 'the old listeners are gone, the new heard on the kept node');
});

test('what differs is replaced; a data-key keeps rows apart; extra nodes go', () => {
  const { h, morph } = load();
  const box = h('div', {});
  morph(box, [h('button', { 'data-key': 'cell:a' }, 'a'), h('button', { 'data-key': 'cell:b' }, 'b'), h('p', {}, 'x')]);
  const [a, b] = box.childNodes;
  morph(box, [h('button', { 'data-key': 'cell:a' }, 'a'), h('span', {}, 'b'), h('button', { 'data-key': 'cell:c' }, 'c')]);
  assert.equal(box.childNodes.length, 3);
  assert.equal(box.childNodes[0], a);
  assert.notEqual(box.childNodes[1], b);
  assert.equal(box.childNodes[1].nodeName, 'SPAN');
  assert.equal(box.childNodes[2].getAttribute('data-key'), 'cell:c');
  morph(box, [h('button', { 'data-key': 'cell:a' }, 'a')]);
  assert.deepEqual(box.childNodes.map((n) => n.textContent), ['a']);
});

test('the person\'s own: a details they opened, a field they are typing in; data-whole is drawn whole', () => {
  const { h, morph, document } = load();
  const box = h('div', {});
  morph(box, [h('details', {}, h('summary', {}, 'more')), h('textarea', {}), h('div', { 'data-whole': '' }, 'author.js')]);
  const [details, area, whole] = box.childNodes;
  details.setAttribute('open', '');
  area.value = 'half a line';
  document.activeElement = area;
  morph(box, [h('details', {}, h('summary', {}, 'more')), h('textarea', {}), h('div', { 'data-whole': '' }, 'author.js')]);
  assert.equal(box.childNodes[0], details);
  assert.ok(details.hasAttribute('open'), 'still open');
  assert.equal(area.value, 'half a line', 'the typing stays');
  assert.notEqual(box.childNodes[2], whole, 'drawn whole');
  const check = h('input', { type: 'checkbox' });
  morph(box, [check]);
  const on = h('input', { type: 'checkbox' }); on.checked = true;
  morph(box, [on]);
  assert.equal(box.childNodes[0], check);
  assert.equal(check.checked, true);
});
