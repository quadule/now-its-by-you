// The studio's page: the song's words, the choices and why, time, other machines, listening, recording.
// Plain JavaScript, no libraries, nothing fetched but this studio's own answers. The page keeps a person's
// edits (a map of choices, songbird/edits.py) and sends them with every request; the browser's storage keeps
// them across a reload. Everything shown is built as text: nothing from an answer is read as markup.
"use strict";

// The score (index.html, with score.js: views, one inspector) is drawn on it, told through window.SongbirdScore
// (its render, its page of words, its inspector, where the recording shows); what the page lacks is skipped.
const TOKEN = document.querySelector('meta[name="studio-token"]').content;
const $ = (id) => document.getElementById(id);
const setOn = (id, key, value) => { const el = $(id); if (el) el[key] = value; };
const score = () => window.SongbirdScore;
const state = {
  start: null, view: null, timeline: null, edits: {}, open: {}, choose: null, options: null,
  names: [], compare: null, busy: 0, playing: null, poll: null, recordJob: null,
  optionsByKey: {}, optionsFailed: false, undo: [], redo: [], editRevision: 0, refreshSerial: 0,
  historyGroup: null, workspace: "words", saveStatus: "Saved", playerSub: "",
  solo: null, mutedLevels: {},
};

// ------------------------------------------------------------------ small helpers

// An element this page made keeps its listeners in el.__on (one dispatcher a type), so morph() can keep a node on
// the page and give it the new drawing's listeners: a control is updated in place, not replaced under the pointer.
// A listener must not hold on to another node of the drawing (it finds it from the event instead): that node may be
// the one kept on the page, or the one thrown away.
function listenable(el) {
  const add = Object.getPrototypeOf(el).addEventListener;
  el.__h = true;
  el.__on = {};
  el.addEventListener = function (type, fn) {
    if (!el.__on[type]) {
      el.__on[type] = [];
      add.call(el, type, (event) => { for (const f of [...(el.__on[type] || [])]) f.call(el, event); });
    }
    el.__on[type].push(fn);
  };
  return el;
}

function h(tag, attrs, ...children) {
  const el = listenable(document.createElement(tag));
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "text") el.textContent = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function svg(tag, attrs, ...children) {
  const el = listenable(document.createElementNS("http://www.w3.org/2000/svg", tag));
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const c of children.flat()) if (c !== null && c !== undefined) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

// Draw `children` into `parent` in place (docs/history/STUDIO-EDM-TEST.md, second attempt, bugs 1 and 2): a node already
// there that the new drawing has in the same place (the same tag and data-key, both drawn by h) is kept and given
// the new one's attributes, text, value and listeners, so an answer arriving mid-click neither replaces the button
// under the pointer nor moves what didn't change; anything else is put in, or taken out. A details' open is the
// person's; a field being typed in keeps its typing; data-whole marks a node drawn by someone else, replaced whole.
function morph(parent, children) {
  const next = children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false)
    .map((c) => (typeof c === "object" ? c : document.createTextNode(String(c))));
  let i = 0;
  for (; i < next.length; i++) {
    const n = next[i], o = parent.childNodes[i];
    if (o === n) continue;
    if (!o) parent.appendChild(n);
    else if (alike(o, n)) patch(o, n);
    else parent.replaceChild(n, o);
  }
  while (parent.childNodes.length > i) parent.removeChild(parent.lastChild);
}
function alike(o, n) {
  if (o.nodeType !== n.nodeType) return false;
  if (o.nodeType !== 1) return o.nodeType === 3;
  return o.nodeName === n.nodeName && !!o.__h && !!n.__h && o.getAttribute("data-key") === n.getAttribute("data-key")
    && !o.hasAttribute("data-whole") && !n.hasAttribute("data-whole");
}
const MORPH_TEXT = new Set(["text", "number", "search", "email", "url", "tel", "password"]);
function patch(o, n) {
  if (o.nodeType === 3) { if (o.data !== n.data) o.data = n.data; return; }
  for (const a of [...o.attributes]) if (!n.hasAttribute(a.name) && !(a.name === "open" && o.nodeName === "DETAILS")) o.removeAttribute(a.name);
  for (const a of [...n.attributes]) if (o.getAttribute(a.name) !== a.value) o.setAttribute(a.name, a.value);
  for (const type of Object.keys(n.__on)) if (!o.__on[type]) o.addEventListener(type, () => {});
  o.__on = Object.fromEntries(Object.keys(o.__on).map((type) => [type, n.__on[type] || []]));
  const value = n.value, checked = n.checked;  // before its options move
  morph(o, [...n.childNodes]);
  const typing = document.activeElement === o && (o.nodeName === "TEXTAREA" || (o.nodeName === "INPUT" && MORPH_TEXT.has(o.type)));
  if (o.nodeName === "INPUT" && (o.type === "checkbox" || o.type === "radio")) o.checked = checked;
  else if (["INPUT", "TEXTAREA", "SELECT"].includes(o.nodeName) && !typing && !(o.matches?.(":active")) && o.value !== value) o.value = value;
}

const PLAY = "M4 2.5v11l9-5.5z";
const PAUSE = "M4 2.5h3v11H4zM9 2.5h3v11H9z";
function playIcon() {
  return svg("svg", { viewBox: "0 0 16 16", "aria-hidden": "true" }, svg("path", { d: PLAY, fill: "currentColor" }));
}

async function api(path, body) {
  // the token names the version the page was opened on (at /v/<id>), so the questions carry it too
  const options = body === undefined ? { headers: { "X-Studio": TOKEN } } : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Studio": TOKEN },
    body: JSON.stringify(body),
  };
  const r = await fetch(path, options);
  let data;
  try { data = await r.json(); } catch (e) { data = { error: r.statusText }; }
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

// Why the studio has no song to show: in the line under the title, and in the short one a narrow screen shows
// in its place (score.css hides the long one there), so a phone isn't left on a page that says nothing.
function stuck(text) {
  setOn("which", "textContent", text);
  setOn("whichShort", "textContent", text);
}

// A word at the foot of the page. Unless told how long, it stays long enough to be read: a line of failure
// (it ran out of memory, and what to try) longer than "Exported."
function toast(text, ms = Math.min(12000, Math.max(2600, 55 * String(text).length))) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), ms);
}

// Saved edits belong to the exact song genome they were made for, as a draft does (drafts.js): a tune or lyric
// edit made for another version of the song's file would come back as a problem on every visit.
function storeKey() {
  const s = state.start;
  return s ? `songbird-studio|${s.title}|${s.from}|${s.machine.label}|${s.song_digest || ""}${s.version ? `|${s.version.id}` : ""}` : null;
}
function olderStoreKey() {  // before the key carried the song's digest
  const s = state.start;
  return s ? `songbird-studio|${s.title}|${s.from}|${s.machine.label}` : null;
}
// Edits written for one genome's tune, lyric keys, word bank or sections: never carried over from an unknown one.
const GENOME_BOUND = /^(tune|lyrics|words|part|transition)\.|^form\.order$/;
function save() {
  // only ever after a person's own change (edits that came in the page's address are never saved on their
  // own); the day and chance drawn again aren't kept, so tomorrow opens on tomorrow
  const kept = Object.fromEntries(Object.entries(state.edits).filter(([p]) => p !== "date" && p !== "roll"));
  try {
    localStorage.setItem(storeKey(), JSON.stringify(kept));
    state.saveStatus = "Saved";
  } catch (e) { state.saveStatus = "Storage unavailable · keep this tab open"; }
  renderHistory();
}
function restore() {
  let saved = null;
  try { saved = localStorage.getItem(storeKey()); } catch (e) { return {}; }
  if (saved !== null && saved !== undefined) {
    try { return editMap(JSON.parse(saved)); } catch (e) { return {}; }
  }
  // Edits saved before the key carried the song's digest: which genome they were made for is unknown, so
  // only the choices that don't depend on it (key, tempo, shape, band, mix, style) come across, once.
  let older = {};
  try {
    const old = olderStoreKey();
    older = editMap(JSON.parse(localStorage.getItem(old) || "{}"));
    localStorage.removeItem(old);
  } catch (e) { return {}; }
  const kept = Object.fromEntries(Object.entries(older).filter(([path]) => !GENOME_BOUND.test(path)));
  if (Object.keys(kept).length) {
    try { localStorage.setItem(storeKey(), JSON.stringify(kept)); } catch (e) { /* kept for this visit */ }
  }
  return kept;
}

function lines(texts, className) {
  // a sung line: its *focus* word underlined
  return h("div", { class: className || "lines" }, texts.map((line) => {
    const p = h("p");
    line.split("*").forEach((piece, i) => p.append(i % 2 ? h("span", { class: "focus" }, piece) : document.createTextNode(piece)));
    return p;
  }));
}

function tag(kind, text) {
  const label = state.start ? state.start.kinds[kind] || kind : kind;
  return h("span", { class: `tag ${kind}`, title: label }, text || label);
}

function fmtTime(s) {
  if (!isFinite(s)) return "";
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

// ------------------------------------------------------------------ edits

function editMap(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function copyEdits(edits = state.edits) { return JSON.parse(JSON.stringify(edits)); }

function commitEdits(next, label = "Edit song", group = null) {
  next = copyEdits(editMap(next));
  if (JSON.stringify(next) === JSON.stringify(state.edits)) return false;
  if (!group || state.historyGroup !== group) {
    state.undo.push({ edits: copyEdits(), label });
    if (state.undo.length > 100) state.undo.shift();
  }
  state.redo = [];
  state.historyGroup = group;
  state.edits = next;
  state.editRevision++;
  save();
  markAudioState();
  refreshSoon(group ? 180 : 0);
  return true;
}

function setEdit(path, value, label) {
  return setEdits({ [path]: value }, label || `Change ${describePath(path).replace(/^your /, "")}`);
}

function releaseEdit(path, label) {
  // an explicit null: the server releases an inherited choice (a parent's phrase or order); merely dropping a
  // local edit would only reveal the inherited one again (as the lyrics reset does with its nulls)
  const next = copyEdits();
  next[path] = null;
  return commitEdits(next, label || `Restore ${describePath(path).replace(/^your /, "")}`);
}

function setEdits(patch, label = "Edit song", group = null) {
  const next = copyEdits();
  for (const [path, value] of Object.entries(editMap(patch))) {
    if (value === null || value === undefined) delete next[path];
    else next[path] = value;
  }
  return commitEdits(next, label, group);
}

function clearEdits(paths, label = "Restore song choices") {
  return setEdits(Object.fromEntries(paths.map((path) => [path, null])), label);
}

function travelHistory(direction) {
  const from = state[direction], to = state[direction === "undo" ? "redo" : "undo"];
  const entry = from.pop();
  if (!entry) return;
  to.push({ edits: copyEdits(), label: entry.label });
  state.edits = entry.edits;
  state.historyGroup = null;
  state.editRevision++;
  save();
  markAudioState();
  refreshSoon(0);
  toast(`${direction === "undo" ? "Undid" : "Redid"}: ${entry.label}`);
}

function renderHistory() {
  for (const direction of ["undo", "redo"]) {
    const button = $(`${direction}Edit`), entries = state[direction];
    if (!button) continue;
    button.disabled = !entries.length;
    button.title = entries.length ? `${capital(direction)}: ${entries[entries.length - 1].label}` : `Nothing to ${direction}`;
  }
  if ($("historyStatus")) $("historyStatus").textContent = state.busy ? "Updating song…" : state.saveStatus;
}

let refreshTimer = null;
function refreshSoon(delay = 160) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, delay);
}

async function refresh() {
  clearTimeout(refreshTimer);
  const edits = copyEdits(), revision = state.editRevision, serial = ++state.refreshSerial;
  state.busy++;
  renderHistory();
  try {
    const view = await api("/api/song", { edits });
    if (revision !== state.editRevision || serial !== state.refreshSerial) return;
    state.view = view;
    state.options = null;
    state.optionsByKey = {};
    state.optionsFailed = false;
    render();
    loadCompare();
    // Safe word alternates belong to the rendered words, so load them without an extra "change" step.
    const sections = view.words.filter((w) => w.sung && w.changeable);
    await Promise.all(sections.map(async (w) => {
      try {
        const options = await api("/api/options", { edits, block: w.block, index: w.nth });
        if (revision !== state.editRevision || serial !== state.refreshSerial) return;
        state.optionsByKey[`${w.block}.${w.nth}`] = options;
      } catch (e) {
        if (revision === state.editRevision && serial === state.refreshSerial) state.optionsFailed = true;
      }
    }));
    if (revision === state.editRevision && serial === state.refreshSerial) renderWords();
  } catch (e) {
    if (revision !== state.editRevision || serial !== state.refreshSerial) return;
    if (!state.view) stuck(`The studio couldn't make your version of the song: ${e.message}`);
    toast(e.message);
  } finally {
    state.busy--;
    renderHistory();
  }
}

// ------------------------------------------------------------------ the header

function renderHeader() {
  const v = state.view;
  if (!$("title").querySelector?.("input")) $("title").textContent = v.name || v.title;  // (not under a hand renaming it)
  document.title = `${v.name || v.title} · Studio`;
  // the day, then only what isn't the plain case: a parent other than the song as it began, a machine if there is one
  const from = v.from === "from the song as it began" ? "" : v.from;
  const by = v.by === "no machine, only time" ? "" : v.by.replace(/^a made-up machine called /, "");
  const published = state.start?.published;
  if (published) {  // the version as it was released: no day, no machine, nothing chosen
    const which = published.which.charAt(0).toUpperCase() + published.which.slice(1);
    $("which").replaceChildren(h("b", {}, which), ` · as published${published.made ? ` ${published.made}` : ""}`);
  } else {
    $("which").replaceChildren(h("b", {}, v.offset ? `${v.date} (${v.when})` : `Today, ${v.date}`), [from, by].filter(Boolean).map((x) => ` · ${x}`).join(""));
  }
  const mine = v.changed;
  const locks = lockCount(v.held);  // a lock (the score's padlock) is held, not changed
  const held = v.held.some((p) => p.startsWith("words."));
  const bar = $("yoursBar");
  bar.hidden = !mine.length && !held && !locks;
  bar.replaceChildren();
  if (mine.length || held || locks) {
    bar.append(...[
      mine.length ? tag("you", `${mine.length} choice${mine.length === 1 ? " is" : "s are"} yours`) : null,
      held ? tag("you", "the words are kept") : null,
      locks ? tag("you", `${locks} locked`) : null,
      mine.length ? h("button", { class: "link small", type: "button", onclick: () => listen("program", null) }, "hear it as the program would sing it") : null,
      h("button", { class: "link small", type: "button", onclick: () => {
        const keep = state.edits.date ? { date: state.edits.date } : {};
        commitEdits(keep, "Reset all song edits");
      } }, "Reset song"),
    ].filter(Boolean));  // append() would write a null out as text
  }
  const problems = v.problems.filter((p) => !["tonic", "mode", "tempo"].includes(p.path) && !p.path.startsWith("form.") && !p.path.startsWith("band.") && !p.path.startsWith("mix."));
  const pbar = $("problemsBar");
  pbar.hidden = !problems.length;
  pbar.replaceChildren(...problems.map((p) => h("p", { class: "problem" }, `Couldn't keep ${describePath(p.path)}: ${p.why}. `,
    h("button", { class: "link small", type: "button", onclick: () => clearEdits([p.path]) }, "let it go"))));
  setOn("day", "value", v.offset);
  setOn("dayLabel", "textContent", v.offset ? `${v.date} (${v.when})` : `today, ${v.date}`);
}

// the padlocks a person sees: a cell's lock keeps its level, what it plays and its line (three paths), one padlock
function lockCount(held) {
  const cell = /^(arrange\.[A-Za-z0-9_-]+:\d+\.[a-z0-9]+)\.(level|pattern|from|fill)$/;
  return new Set((held || []).filter((p) => !p.startsWith("words.")).map((p) => p.match(cell)?.[1] || p)).size;
}

function describePath(path) {
  const m = path.match(/^words\.(verse|refrain)\.(\d+)$/);
  if (m) return `your ${m[1]} ${Number(m[2]) + 1}`;
  const place = path.match(/^(tune|chords)\.([A-Za-z0-9_-]+):(\d+|last)\.(\d+)$/);  // one place of the form
  if (place) return `your ${place[1]} for ${place[3] === "last" ? `the last ${place[2]}` : `${place[2]} ${Number(place[3]) + 1}`}, line ${Number(place[4]) + 1}`;
  if (path.startsWith("chords.")) return "your chords for a line of the tune";
  const part = path.match(/^part\.([a-z0-9-]+)\.([A-Za-z0-9_-]+):(\d+)\.(\d+)$/);  // notes in (perform.js)
  if (part) return `your ${part[1]} in ${part[2]} ${Number(part[3]) + 1}, line ${Number(part[4]) + 1}`;
  const where = (sid) => sid.replace(/^(\w+?)(2)?:(\d+)$/, (_, name, two, n) => `${two ? "second " : ""}${name} ${Number(n) + 1}`);
  const cell = path.match(/^arrange\.([A-Za-z0-9_-]+:\d+)\.([a-z0-9]+)\.(level|pattern|from|fill)$/);  // the score's grid
  if (cell) return `your ${cell[2]} in ${where(cell[1])}`;
  const sec = path.match(/^arrange\.([A-Za-z0-9_-]+:\d+)\.(bars|sung|build|round)$/);
  if (sec) return `your ${{ bars: "length", sung: "drop", build: "build", round: "round" }[sec[2]]} in ${where(sec[1])}`;
  const into = path.match(/^transition\.([A-Za-z0-9_-]+:\d+)$/);
  if (into) return `your transition into ${where(into[1])}`;
  const sound = path.match(/^(sound|mix)\.([a-z0-9]+)\.(\w+)$/);
  if (path === VOICES) return "the voice's mute";
  if (sound && !["space", "width", "forward", "intimacy", "rt60", "predelay"].includes(sound[2])) return `your ${sound[2]}'s ${sound[3]}`;
  return { "name": "your title", "words.refrain": "your refrain's words", "words.bridge": "your bridge's words", "words.bridge2": "your second bridge", "words.tag": "your tag", "phrasing": "the singer's way", "date": "the day" }[path] || `your ${path.replace(/^\w+\./, "").replace(/_/g, " ")}`;
}

// ------------------------------------------------------------------ the words

function renderWords() {
  const v = state.view;
  const box = $("words");
  if (!box) return score()?.renderPage?.();  // the score sets the words on its own Page
  window.SongbirdAuthor?.capture();
  const active = document.activeElement;
  const focusKey = box.contains(active) ? active.dataset.focus : null;
  const opened = new Set([...box.querySelectorAll("details[open]")].map((d) => d.dataset.section));
  box.replaceChildren();
  for (const w of v.words) {
    const ready = v.listen.ready.includes(v.listen.sections[w.index]);
    const play = h("button", { class: `play${ready ? " ready" : ""}`, type: "button", "aria-label": `Play ${w.label}`,
      title: ready ? "ready to play" : "play (it will be made first)", onclick: () => listen("you", w.index) }, playIcon());
    const meta = h("span", { class: "sec-meta" });
    if (w.sung) {
      const kind = w.mine ? "you" : { "handed down": "lineage", "new this time": "time", "drawn by chance": "chance" }[w.how] || "song";
      meta.append(tag(kind, (w.authored || []).length ? "your lyrics" : w.mine ? "your words" : w.how));
    }
    const tools = h("span", { class: "sec-tools" }, play);
    if (w.mine) tools.prepend(h("button", { class: "link small", type: "button",
      title: "Restore the bank's words and release original lines in this section", onclick: () => undoWords(w) }, "Reset words"));
    const key = `${w.block}.${w.nth}`, options = state.optionsByKey[key];
    const sec = h("div", { class: `sec${w.sung ? "" : " instrumental"}${w.mine ? " mine" : ""}`, id: `sec-${w.index}` },
      h("div", { class: "sec-head" }, h("span", { class: "sec-name" }, w.label), meta, tools));
    if (options) {
      const allAuthored = (w.authored || []).length >= w.lines.length;
      const selects = h("div", { class: "section-selects" });
      if (!allAuthored && (options.heads || []).length > 1) selects.append(headChooser(options, w.label));  // sung first
      if (!allAuthored && options.choices.length) selects.append(phraseChooser(w, options));
      if (selects.childNodes.length) sec.append(selects);
      sec.append(inlineLyrics(w, options));
      const rules = allAuthored ? null : chooser(w, options);
      if (rules) {
        rules.open = opened.has(key) || (state.choose && state.choose.key === key);
        sec.append(rules);
      }
    } else {
      sec.append(lines(w.lines));
      if (w.sung && w.changeable) sec.append(h("p", { class: "hint" }, state.optionsFailed
        ? "Word choices couldn't load. " : "Finding singable word choices…",
      state.optionsFailed ? h("button", { type: "button", class: "link small", onclick: refresh }, "Try again") : null));
    }
    if (w.note) sec.append(h("p", { class: "sec-note" }, w.note));
    box.append(sec);
  }
  window.SongbirdAuthor?.decorate(state.view, box);
  if (focusKey) [...box.querySelectorAll("[data-focus]")].find((el) => el.dataset.focus === focusKey)?.focus({ preventScroll: true });
}

function undoWords(w) {
  commitEdits(releaseWords(w, copyEdits()), `Reset ${w.label.toLowerCase()} words`);
}

function releaseWords(w, next) {  // a section's words back to the bank's, its original lines released (into `next`)
  const paths = [w.path];
  if (w.block === "refrain") paths.push("words.refrain");
  if (w.block === "bridge" && w.nth === 0) paths.push("words.bridge");
  for (const path of paths) delete next[path];
  // A person's lines are kept by the verse (or time round) they're written for, the section's lyric_key
  // (songbird/composition.py), not by its place in the form.
  const section = state.view?.composition?.sections.find((item) => item.index === w.index);
  // Null explicitly releases inherited original text. Removing a local edit alone would reveal it again.
  for (const phrase of section?.phrases || []) if (phrase.authored && phrase.lyric_path) next[phrase.lyric_path] = null;
  if (section?.lyric_key) {
    const prefix = `lyrics.${section.lyric_key}.`;
    for (const line of w.authored || []) next[`${prefix}${line}`] = null;
    for (const path of Object.keys(next)) if (path.startsWith(prefix)) next[path] = null;
  }
  return next;
}

// Retain old deep links, while choices are now loaded and visible in every sung section.
async function toggleChooser(w) {
  state.choose = { key: `${w.block}.${w.nth}`, block: w.block, index: w.nth };
  showWorkspace("words");
  renderWords();
  $(`sec-${w.index}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function choiceLabel(c) {
  const first = (c.lines[0] || c.id).replace(/\*/g, "");
  const trade = c.trades !== null && c.trades !== undefined ? ` · swaps with refrain ${c.trades + 1}` : "";
  return `${first}${trade}${c.allowed ? "" : " · unavailable here"}`;
}

function phraseChooser(w, o) {
  const name = { verse: "Verse", refrain: "Couplet", bridge: "Stanza", tag: "Syllable" }[o.block] || "Phrase";
  const select = h("select", { class: "phrase-select", "aria-label": `${w.label}: ${name.toLowerCase()}`,
    "data-focus": `${w.block}.${w.nth}.phrase` }, o.choices.map((c) => h("option", {
      value: c.id, disabled: !c.allowed, title: c.why || c.lines.join(" / ").replace(/\*/g, "") }, choiceLabel(c))));
  select.value = o.sung;
  select.addEventListener("change", (e) => setEdit(o.path, o.block === "verse" ? { id: e.target.value }  // (morph: not `select`)
    : o.block === "refrain" ? Object.assign(refrainEdit(o), { id: e.target.value }) : e.target.value,
  `Choose ${w.label.toLowerCase()} ${name.toLowerCase()}`));
  return h("label", { class: "lyric-slot-label" }, h("span", {}, name), select);
}

function slotSelect(w, o, slot, suffix = "") {
  const select = h("select", { class: "lyric-select", "aria-label": `${w.label}: ${slot.slot.replace(/_/g, " ")}`,
    "data-focus": `${w.block}.${w.nth}.${slot.slot}${suffix}`,
    title: `${slot.slot.replace(/_/g, " ")}${slot.once ? " · changes every refrain" : " · choose a singable alternate"}` },
  slot.options.map((option) => h("option", { value: option }, (slot.labels?.[option] || option).replace(/\*/g, ""))));
  select.value = slot.sung;
  const current = (slot.labels?.[slot.sung] || slot.sung || "Choose").replace(/\*/g, "");
  select.style.width = `${Math.max(3, current.length + 2)}ch`;
  select.addEventListener("change", (e) => chooseSlot(o, slot.slot, e.target.value));
  return select;
}

// The API supplies readable slot labels, including multi-word alternatives and coupled noun slots.
// Match complete words only; anything ambiguous or absent gets a labelled select just below the lines.
function lyricMatches(texts, slots, authored = []) {
  const excluded = new Set(authored);
  const lines = texts.map((text) => text.replace(/\*/g, ""));
  const matches = lines.map(() => []), missing = [];
  const wordChar = (c) => !!c && /[\p{L}\p{N}_]/u.test(c);
  for (const slot of slots) {
    const label = (slot.labels?.[slot.sung] || slot.sung || "").replace(/\*/g, "");
    let found = false;
    for (let line = 0; label && line < lines.length && !found; line++) {
      if (excluded.has(line)) continue;
      const text = lines[line];
      let start = -1;
      while ((start = text.toLocaleLowerCase().indexOf(label.toLocaleLowerCase(), start + 1)) !== -1) {
        const end = start + label.length;
        if ((wordChar(label[0]) && wordChar(text[start - 1])) || (wordChar(label[label.length - 1]) && wordChar(text[end]))) continue;
        if (matches[line].some((match) => start < match.end && end > match.start)) continue;
        matches[line].push({ start, end, slot });
        found = true;
        break;
      }
    }
    if (!found) missing.push(slot);
  }
  matches.forEach((line) => line.sort((a, b) => a.start - b.start));
  return { lines, matches, missing };
}

function inlineLyrics(w, o) {
  const parsed = lyricMatches(w.lines, o.words || [], w.authored || []);
  const box = h("div", { class: "lines editable-lines" });
  w.lines.forEach((source, line) => {
    const p = h("p", { class: "lyric-line" });
    const focused = [];
    let focus = false;
    for (const char of source) {
      if (char === "*") focus = !focus;
      else focused.push(focus);
    }
    const appendText = (start, end) => {
      while (start < end) {
        let at = start + 1;
        while (at < end && focused[at] === focused[start]) at++;
        const text = parsed.lines[line].slice(start, at);
        p.append(focused[start] ? h("span", { class: "focus" }, text) : document.createTextNode(text));
        start = at;
      }
    };
    let at = 0;
    for (const match of parsed.matches[line]) {
      appendText(at, match.start);
      const select = slotSelect(w, o, match.slot);
      if (focused.slice(match.start, match.end).some(Boolean)) select.classList.add("focus");
      p.append(select);
      at = match.end;
    }
    appendText(at, parsed.lines[line].length);
    box.append(p);
  });
  if (parsed.missing.length && !(w.authored || []).length) box.append(h("div", { class: "lyric-fallbacks" }, parsed.missing.map((slot) =>
    h("label", { class: "lyric-slot-label" }, h("span", {}, capital(slot.slot.replace(/_/g, " "))), slotSelect(w, o, slot)))));
  if ((o.words || []).some((slot) => slot.once)) box.append(h("span", { class: "hint" }, "Shared words change in every refrain."));
  return box;
}

function chooser(w, o) {
  const refused = o.choices.filter((c) => !c.allowed);
  const fixed = o.fixed || [];
  const heads = (o.heads || []).filter((c) => !c.allowed);
  if (!fixed.length && !refused.length && !heads.length && !(w.tags || []).length) return null;
  const box = h("details", { class: "chooser word-rules", "data-section": `${w.block}.${w.nth}` },
    h("summary", {}, "Song rules & alternatives"));
  if ((w.tags || []).length) box.append(h("p", { class: "hint" }, w.tags.join(" · ")));
  for (const f of fixed) box.append(h("p", { class: "fixed" }, `${capital(f.what)}: ${f.sung}. `, h("span", { class: "hint" }, f.why)));
  for (const head of heads) box.append(h("p", { class: "hint" }, `${head.id}: ${head.why}.`));
  if (refused.length) box.append(h("ul", { class: "refused" }, refused.map((c) => {
    const offer = c.reorder
      ? h("button", { class: "link small", type: "button", onclick: () => applyOrder(c.reorder) }, `Use as verse ${c.reorder.indexOf(c.id) + 1}`)
      : c.elsewhere?.length ? h("button", { class: "link small", type: "button",
        onclick: () => setEdit(`words.verse.${c.elsewhere[0]}`, { id: c.id }) }, `Use as verse ${c.elsewhere[0] + 1}`) : null;
    return h("li", {}, h("b", {}, (c.lines[0] || c.id).replace(/\*/g, "")), `: ${c.why}. `, offer);
  })));
  return box;
}

function refrainEdit(o) {
  const current = state.edits[o.path];
  return typeof current === "string" ? { id: current } : Object.assign({}, current || {});
}

function headChooser(o, sectionLabel) {
  const select = h("select", { class: "phrase-select", "aria-label": `${sectionLabel}: opening lines`,
    "data-focus": `refrain.${o.index}.head` }, o.heads.map((head) => h("option", {
      value: head.id, disabled: !head.allowed, title: head.why || head.lines.join(" / ") }, choiceLabel(head))));
  select.value = o.head;
  select.addEventListener("change", (e) => {
    const edit = refrainEdit(o);
    delete edit.slots;
    edit.head = e.target.value;
    setEdit(o.path, edit, "Change refrain opening");
  });
  return h("label", { class: "lyric-slot-label" }, h("span", {}, "Opening"), select);
}

function chooseSlot(o, slot, value) {
  if (o.block === "verse") {
    const current = state.edits[o.path];
    const id = current && current.id ? current.id : o.sung;
    const slots = Object.assign({}, current && current.slots ? current.slots : {}, { [slot]: value });
    setEdit(o.path, { id, slots });
  } else if (o.block === "refrain" && (o.words || []).some((w) => w.slot === slot && w.once)) {
    setEdit("words.refrain", Object.assign({}, state.edits["words.refrain"] || {}, { [slot]: value }));
  } else if (o.block === "refrain") {
    const edit = refrainEdit(o);
    edit.slots = Object.assign({}, edit.slots || {}, { [slot]: value });
    setEdit(o.path, edit);
  } else {
    const path = o.slots_path;
    setEdit(path, Object.assign({}, state.edits[path] || {}, { [slot]: value }));
  }
}

function applyOrder(order) {
  setEdits(Object.fromEntries(order.map((id, i) => [`words.verse.${i}`, { id }])), "Rearrange verses");
}

function capital(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ------------------------------------------------------------------ the cards

function renderCards() {
  const box = $("cards");
  if (!box) return score()?.renderInspector?.();  // the score's cards are states of its inspector
  const openNow = new Set([...box.querySelectorAll("details.card-context[open]")].map((d) => d.dataset.card));
  box.replaceChildren();
  for (const c of state.view.cards) {
    const head = h("div", { class: "card-head" }, h("h3", {}, c.title));
    if (c.mine && c.paths && c.paths.length) head.append(h("button", { class: "link small undo", type: "button", onclick: () => clearEdits(allPaths(c)) }, "Reset"));
    const card = h("section", { class: `card${c.mine ? " mine" : ""}`, "aria-label": c.title }, head,
      h("div", { class: "value" }, c.value),
      c.today ? h("div", { class: "today" }, c.today) : null,
      (c.problems || []).map((p) => h("p", { class: "problem" }, `Couldn't keep your ${describePath(p.path).replace(/^your /, "")}: ${p.why}.`)));
    const controls = editor(c);
    if (controls) card.append(h("div", { class: "card-controls" }, controls));
    // A control's longer notes are read on demand, with the card's story, not all at once.
    const notes = controls?.querySelectorAll ? [...controls.querySelectorAll(".aside-note")] : [];
    if (c.detail || c.lines || c.reasons?.length || notes.length) {
      const d = h("details", { class: "card-context", "data-card": c.id }, h("summary", {}, "How this choice works"),
        notes, c.detail ? h("div", { class: "detail" }, c.detail) : null,
        c.lines ? h("ul", { class: "machine-lines" }, c.lines.map((l) => h("li", {}, l))) : null, reasonsOf(c));
      d.open = openNow.has(c.id) || !!state.open[c.id];
      d.addEventListener("toggle", () => { state.open[c.id] = d.open; });
      card.append(d);
    }
    box.append(card);
  }
}

function reasonsOf(c) {
  // a person's choices first; then, if there are any, the program's own reasons set apart
  if (!c.reasons || !c.reasons.length) return null;
  const row = (r) => h("div", { class: "reason" }, tag(r.kind), h("span", {}, r.text));
  const yours = c.reasons.filter((r) => r.kind === "you");
  const program = c.reasons.filter((r) => r.kind !== "you");
  return h("div", { class: "reasons" }, yours.map(row),
    yours.length && program.length ? h("div", { class: "program-why" }, "Why the program chose what it did:") : null,
    program.map(row));
}

function allPaths(c) {
  // undo on a card takes back every edit it shows
  const prefixes = { shape: ["form."], band: ["band."], mix: ["mix."], words: ["words."], variants: ["variants."] }[c.id];
  if (!prefixes) return c.paths;
  return Object.keys(state.edits).filter((p) => prefixes.some((x) => p.startsWith(x)));
}

function slider(label, path, value, b, show, ends) {
  const out = h("output", {}, show(value));
  const input = h("input", { type: "range", min: b.min, max: b.max, step: b.step || 0.01, value: value, "aria-label": label });
  input.addEventListener("input", () => { out.textContent = show(Number(input.value)); });
  input.addEventListener("change", () => setEdit(path, Number(input.value)));
  return h("div", { class: "control" }, h("div", { class: "row" }, h("label", {}, label), h("span", { class: "grow" }), out), input,
    ends ? h("div", { class: "ends" }, h("span", {}, ends[0]), h("span", {}, ends[1])) : null);
}

function chips(label, options, current, onpick, names, why) {
  const select = h("select", { "aria-label": label }, options.map((option, index) => {
    const refused = why && why[option];
    return h("option", { value: index, disabled: !!refused, title: refused || names?.title?.[option] || null },
      `${names?.text?.[option] || String(option)}${refused ? " · unavailable" : ""}`);
  }));
  select.value = options.indexOf(current);
  select.addEventListener("change", () => onpick(options[Number(select.value)]));
  return h("label", { class: "control select-control" }, h("span", {}, label), select);
}

function renderSessionControls() {
  const box = $("sessionControls");
  if (!box) return;
  const key = state.view.cards.find((c) => c.id === "key");
  const tempo = state.view.cards.find((c) => c.id === "tempo");
  const bounds = state.start.bounds;
  const controls = [];
  if (tempo) {
    const range = { ...bounds.tempo, ...(tempo.range || {}) };  // the tempos this style takes (docs/ARRANGE.md)
    const input = h("input", { type: "number", min: range.min, max: range.max, step: range.step,
      value: tempo.tempo, "aria-label": "Tempo in beats per minute" });
    input.addEventListener("change", () => {
      const value = Number(input.value);
      if (!input.value || !Number.isFinite(value) || value < range.min || value > range.max) {
        input.value = tempo.tempo;
        toast(`Choose a tempo from ${range.min} to ${range.max} BPM.`);
        return;
      }
      setEdit("tempo", value, "Change tempo");
    });
    controls.push(h("label", { class: "session-control" }, h("span", {}, "Tempo"), input, h("span", { class: "hint" }, "BPM")));
  }
  if (key) {
    const notes = [];
    for (let note = bounds.tonic.min; note <= bounds.tonic.max; note++) notes.push(note);
    controls.push(chips("Key", notes, key.tonic, (value) => setEdit("tonic", value), { text: bounds.tonic.names }));
    controls.push(chips("Scale", bounds.mode.options, key.mode, (value) => setEdit("mode", value), { text: bounds.mode.names }));
  }
  // the song's length as it will be recorded: the realized score's, the last chord's ring included
  const total = state.view.composition?.duration;
  if (total) controls.push(h("span", { class: "session-duration hint", title: "How long the song lasts" }, `Length ${fmtTime(total)}`));
  box.replaceChildren(...controls);
}

// The singers (the lead and the lineage choir) as one channel: mix.voices, 0 muted, else as sung. Muted, the band
// stays as the record has it, still making way where they sing (songbird.synth.mixing).
const VOICES = "mix.voices", VOICE = "voice";

function voicesProgram() {  // the program's own: 1, or a parent's mute handed down
  const mark = state.view?.marks?.[VOICES];
  if (mark && typeof mark.was === "number") return mark.was;
  return state.view?.cards?.find((c) => c.id === "mix")?.mix?.voices ?? 1;
}

function voicesLevel() {  // what's heard now: the latest edit's, else the program's
  return Object.hasOwn(state.edits, VOICES) && state.edits[VOICES] !== null ? state.edits[VOICES] : voicesProgram();
}

// the edit that brings the singers to a level: the program's own is given back to the program, not kept as yours
const voicesEdit = (level) => (Math.abs(level - voicesProgram()) < 1e-9 ? null : level);

function muteVoice() {
  const muted = voicesLevel() <= 0.02;
  setEdits({ [VOICES]: voicesEdit(muted ? 1 : 0) }, muted ? "Unmute the voice" : "Mute the voice");
}

function currentSolo() {
  if (state.solo && Object.entries(state.solo.patch).some(([path, value]) => (state.edits[path] ?? null) !== value)) state.solo = null;
  return state.solo;
}

function soloPlayer(card, player) {  // a band player alone, or (VOICE) the singers alone
  const active = currentSolo();
  if (active?.player === player) {
    state.solo = null;
    setEdits(active.before, "Restore the mix");
    return;
  }
  const names = Object.keys(card.players);
  const before = active?.before || Object.fromEntries([...names.map((name) => `band.${name}`), VOICES].map((path) =>
    [path, Object.hasOwn(state.edits, path) ? state.edits[path] : null]));
  const levels = active?.levels || Object.fromEntries(names.map((name) => [name, card.band[name]]));
  const patch = Object.fromEntries(names.map((name) => [`band.${name}`, name === player ? Math.max(0.03, levels[name] || 1) : 0]));
  // the singers out with the rest of the band; alone, heard even if they were muted before
  const sung = before[VOICES] ?? voicesProgram();
  patch[VOICES] = voicesEdit(player !== VOICE ? 0 : sung > 0.02 ? sung : 1);
  state.solo = { player, before, levels, patch };
  setEdits(patch, player === VOICE ? "Solo the voice" : `Solo ${card.players[player] || player}`);
}

function mutePlayer(card, player) {
  // its level now: the latest edit's (a second quick M unmutes), else the answer's
  const path = `band.${player}`, level = (Object.hasOwn(state.edits, path) && state.edits[path] !== null ? state.edits[path] : card.band[player]) || 0;
  if (level > 0.02) {
    state.mutedLevels[player] = level;
    setEdit(path, 0, `Mute ${card.players[player] || player}`);
  } else {
    // back to the level before: the program's own is given back to the program, not kept as a choice of yours
    // (a mute found on the page when it opened has no level remembered: the program's, then)
    const mark = state.view?.marks?.[path], to = state.mutedLevels[player] || (typeof mark?.was === "number" && mark.was > 0.02 ? mark.was : 1);
    if (mark && typeof mark.was === "number" && Math.abs(mark.was - to) < 1e-9) releaseEdit(path, `Unmute ${card.players[player] || player}`);
    else setEdit(path, to, `Unmute ${card.players[player] || player}`);
  }
}

function bandMixer(card) {
  const solo = currentSolo();
  // Every instrument gain uses the server's validated 0..2 range; older packets omit this bounds entry.
  const bounds = state.start.bounds["band.gain"] || { min: 0, max: 2, step: 0.01 };
  return h("div", { class: "band-mixer", role: "group", "aria-label": "Instrument mixer" }, Object.keys(card.players).map((name) => {
    const muted = card.band[name] <= 0.02;
    return h("div", { class: `mixer-strip${muted ? " muted" : ""}` },
      h("div", { class: "mixer-strip-head" }, h("span", {}, card.players[name]), h("div", { class: "mixer-buttons" },
        h("button", { type: "button", class: `chip${muted ? " on" : ""}`, "aria-label": `${muted ? "Unmute" : "Mute"} ${card.players[name]}`,
          "aria-pressed": String(muted), onclick: () => mutePlayer(card, name) }, "M"),
        h("button", { type: "button", class: `chip${solo?.player === name ? " on" : ""}`, "aria-label": `Solo ${card.players[name]}`,
          "aria-pressed": String(solo?.player === name), onclick: () => soloPlayer(card, name) }, "S"))),
      slider(`${card.players[name]} level`, `band.${name}`, card.band[name] || 0, bounds, (value) => `${Math.round(value * 100)}%`));
  }));
}

function editor(c) {
  const s = state.start, b = s.bounds, v = state.view;
  switch (c.id) {
    case "key": {
      const notes = [];
      for (let m = b.tonic.min; m <= b.tonic.max; m++) notes.push(m);
      return h("div", {},
        chips("The key's note", notes, c.tonic, (m) => setEdit("tonic", m), { text: b.tonic.names }),
        chips("Its mode", b.mode.options, c.mode, (m) => setEdit("mode", m), { text: b.mode.names, title: b.mode.glosses }),
        h("p", { class: "hint aside-note" }, "A minor mode leans the words darker, as the machine's would."));
    }
    case "tempo":
      return slider("Beats a minute", "tempo", c.tempo, { ...b.tempo, ...(c.range || {}) }, (x) => `${Number(x).toFixed(0)}`, ["slower", "quicker"]);
    case "shape": {
      const arranged = !!v.composition?.arranged;
      if (arranged || !Object.keys(c.parts || {}).length) return h("div", {},
        h("p", { class: "hint" }, "The order of the parts is edited in Tune."
          + (arranged ? " Use the song's shape to choose verse counts and optional sections here again." : "")),
        h("div", { class: "actions" },
          h("button", { class: "btn quiet", type: "button", onclick: () => showWorkspace("arrange") }, "Open Tune"),
          arranged ? h("button", { class: "btn quiet", type: "button", onclick: () => {
            const next = copyEdits();
            for (const path of Object.keys(next)) if (path.startsWith("form.")) delete next[path];
            // Explicit null also releases an arrangement inherited from a recorded parent.
            next["form.order"] = null;
            commitEdits(next, "Use the song's shape");
          } }, "Use the song's shape") : null));
      const byPart = {};
      for (const ch of c.choices || []) (byPart[ch.part] = byPart[ch.part] || []).push(ch);
      const box = h("div", {});
      if (byPart.verses) box.append(chips("Verses", byPart.verses.map((x) => x.value), c.parts.verses,
        (n) => setEdit("form.verses", n), null, Object.fromEntries(byPart.verses.filter((x) => !x.allowed).map((x) => [x.value, x.why]))));
      const toggles = h("div", { class: "chips" });
      for (const part of s.optional) {
        const options = byPart[part] || [];
        const on = !!c.parts[part];
        const flip = options.find((x) => x.value === !on);
        toggles.append(h("button", { class: `chip${on ? " on" : ""}`, type: "button", "aria-pressed": on ? "true" : "false",
          disabled: !flip || !flip.allowed,
          title: !flip ? "This part can't be changed in this arrangement" : !flip.allowed ? flip.why : null,
          onclick: () => setEdit(`form.${part}`, !on) }, s.parts[part]));
      }
      box.append(h("div", { class: "control" }, h("label", {}, "Parts of the shape"), toggles));
      return box;
    }
    case "band": {
      const band = c.band;
      return h("div", {},
        c.styled ? null : chips("How the band plays", b["band.pattern"].options, band.pattern, (x) => setEdit("band.pattern", x), { text: s.patterns }),
        c.styled ? null : chips("Who leads where nobody sings", b["band.lead"].options, band.lead, (x) => setEdit("band.lead", x), { text: c.players }),
        slider("How busy", "band.density", band.density, b["band.density"], (x) => `${Math.round(x * 100)}%`, ["sparse", "busy"]),
        slider("How bright", "band.brightness", band.brightness, b["band.brightness"], (x) => `${Math.round(x * 100)}%`, ["dark and soft", "bright"]),
        bandMixer(c),
        h("p", { class: "hint aside-note" }, "M mutes a player. S plays it alone; click again to restore the mix."),
        h("p", { class: "hint aside-note" }, c.styled ? "The style chooses who plays and who leads; change the style to change the band. With nobody playing, the voice sings alone."
          : "With nobody playing, the voice sings alone."));
    }
    case "style": {
      const st = c.style;
      return h("div", {},
        chips("The style", Object.keys(c.styles), st.name, (x) => setEdit("style.name", x), { text: c.styles }),
        chips("Its feel", Object.keys(c.feels), st.feel, (x) => setEdit("style.feel", x), { text: c.feels }),
        chips("How it ends", Object.keys(c.endings), st.ending, (x) => setEdit("style.ending", x), { text: c.endings }),
        chips("Backing voices", Object.keys(c.backings), st.backing, (x) => setEdit("style.backing", x), { text: c.backings }),
        chips("The last refrain", ["lift", "no lift"], st.lift ? "lift" : "no lift", (x) => setEdit("style.lift", x === "lift"),
          { text: { "lift": "a whole step up", "no lift": "in the same key" } }),
        h("p", { class: "hint aside-note" }, "A style sets the band, the pace and the feel. A version moves one style at a time, so its children will drift back toward your machine's."));
    }
    case "mix": {
      const m = c.mix;
      return h("div", {},
        slider("How much of the room", "mix.space", m.space, b["mix.space"], (x) => `${Math.round(x * 100)}%`, ["dry", "roomy"]),
        slider("How wide", "mix.width", m.width, b["mix.width"], (x) => `${Math.round(x * 100)}%`, ["narrow", "wide"]),
        slider("The voice over the band", "mix.forward", m.forward, b["mix.forward"], (x) => `${Number(x).toFixed(1)} dB`, ["among it", "well over it"]),
        slider("How close the singer is", "mix.intimacy", m.intimacy, b["mix.intimacy"], (x) => `${Math.round(x * 100)}%`, ["further back", "at your ear"]),
        // the room itself (a musician's reverb time and pre-delay), where the page's bounds offer it
        b["mix.rt60"] ? slider("How long the room rings", "mix.rt60", m.rt60, b["mix.rt60"], (x) => `${Number(x).toFixed(2)} s`, ["a small room", "a hall"]) : null,
        b["mix.predelay"] ? slider("How soon the room answers", "mix.predelay", m.predelay, b["mix.predelay"], (x) => `${Math.round(x * 1000)} ms`, ["at once", "later"]) : null,
        h("p", { class: "hint aside-note" }, "Judge the voice against the band on the whole song: a part heard alone is levelled for listening."));
    }
    case "singer": {
      const box = h("div", {}, h("p", { class: "hint" }, "The singer is your machine's voice, the same in every song it sings. What you can give it is your way of singing."));
      const phrasings = phrasingChoices(s.phrasings);  // with the one sung in this browser, if any
      if (phrasings.length) {
        const select = h("select", { "aria-label": "Whose way it is sung" },
          h("option", { value: "" }, "the song's way"),
          phrasings.map((p) => h("option", { value: p.id }, `${p.way || `${p.label}'s way`}${p.detail ? ` (${p.detail})` : ""}`)));
        select.value = c.phrasing || "";
        select.addEventListener("change", () => setEdit("phrasing", select.value || null));
        box.append(h("div", { class: "control" }, h("label", {}, "Whose way it is sung"), select));
      } else {
        box.append(h("p", { class: "hint" }, s.sing.available ? "Once someone has sung it on the singing page (below), the song can be sung their way here." : s.sing.why));
      }
      return box;
    }
    case "words":
      return h("div", {},
        h("p", { class: "hint" }, "Hold every word as it is now, so that time and chance change only the music."),
        h("button", { class: "btn", type: "button", onclick: keepWords }, "Keep these words"));
    case "variants":
      if (!c.variants || !c.variants.length) return null;
      return h("div", { class: "control" }, c.variants.map((x) => {
        const box = h("input", { type: "checkbox" });
        box.checked = !!x.value;
        box.addEventListener("change", () => setEdit(x.path, box.checked));
        return h("label", {}, box, x.label);
      }));
    default:
      return null;
  }
}

async function keepWords() {
  try {
    const revision = state.editRevision;
    const r = await api("/api/keep-words", { edits: copyEdits() });
    if (revision !== state.editRevision) { toast("The song changed. Keep the words again for this version."); return; }
    commitEdits(r.edits, "Keep these words");
    toast("The words are held as they are.");
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ time

const MODE_TINT = { lydian: 0.95, ionian: 0.8, mixolydian: 0.62, dorian: 0.45, aeolian: 0.32, phrygian: 0.2, locrian: 0.1 };
const PATTERN_TINT = { air: 0.25, pick: 0.45, lilt: 0.65, strum: 0.85 };

function segments(values) {
  const out = [];
  let start = 0;
  for (let i = 1; i <= values.length; i++) {
    if (i === values.length || values[i] !== values[start]) {
      out.push([start, i, values[start]]);
      start = i;
    }
  }
  return out;
}

function renderTimeline() {
  const tl = state.timeline;
  const box = $("timeline");
  // on the device, asked for once the Time drawer is open (it's drawn there)
  if (!tl && box && state.start?.device && !state.timelineAsked && $("drawer") && !$("drawer").hidden) {
    box.replaceChildren(h("p", { class: "hint" }, "Drawing six years of the song…"));
    loadTimeline();
  }
  if (!tl || !box) return;
  const width = Math.max(320, box.clientWidth || 800);
  const n = tl.dates.length;
  const left = 70, right = 10, laneH = 22, gap = 8;
  const x = (i) => left + (i / (n - 1)) * (width - left - right);
  const today = tl.today;
  const at = today + (state.view ? state.view.offset : 0);
  const existing = box.firstElementChild;
  if (existing && existing._tl === tl && existing._width === width && existing._cursor) {
    existing._cursor.setAttribute("x1", x(at));
    existing._cursor.setAttribute("x2", x(at));
    return;
  }
  const lanes = [["Style", "style"], ["Key", "key"], ["Tempo", "tempo"], ["Verses", "verses"], ["Lead", "lead"], ["Words", "lean"]];
  const height = lanes.length * (laneH + gap) + 26;
  const root = svg("svg", { class: "timeline", viewBox: `0 0 ${width} ${height}`, width: "100%", height, role: "img",
    "aria-label": "Six years of your machine's song: key, tempo, verses, band, lead and the words' leaning" });
  const style = getComputedStyle(document.documentElement);
  const accent = style.getPropertyValue("--accent").trim(), ink = style.getPropertyValue("--ink").trim(), time = style.getPropertyValue("--time").trim();
  // years
  tl.dates.forEach((d, i) => {
    if (d.endsWith("-01-01")) {
      root.append(svg("line", { class: "grid", x1: x(i), x2: x(i), y1: 0, y2: height - 18 }),
        svg("text", { x: x(i) + 3, y: height - 5 }, d.slice(0, 4)));
    }
  });
  lanes.forEach(([name, key], row) => {
    const y = row * (laneH + gap) + 4;
    const values = tl.lanes[key];
    if (key === "tempo" || key === "lean") {
      const lo = Math.min(...values), hi = Math.max(...values);
      const span = hi - lo || 1;
      let d = "";
      for (let i = 0; i < n; i += 2) d += `${i ? "L" : "M"}${x(i).toFixed(1)},${(y + laneH - 2 - ((values[i] - lo) / span) * (laneH - 4)).toFixed(1)}`;
      root.append(svg("path", { d, class: key === "tempo" ? "tempo" : "lean" }));
      // the scale under the lane's name: the tempo's range, or which way is lighter
      root.append(svg("text", { class: "lane-name", x: 0, y: y + 10 }, name),
        svg("text", { class: "lane-scale", x: 0, y: y + 21 }, key === "tempo" ? `${Math.round(lo)}–${Math.round(hi)}` : "lighter ↑"));
      return;
    }
    root.append(svg("text", { class: "lane-name", x: 0, y: y + 15 }, name));
    for (const [a, b, value] of segments(values)) {
      let tint = 0.5;
      if (key === "key") tint = MODE_TINT[tl.lanes.mode[a]] ?? 0.5;
      else if (key === "pattern") tint = PATTERN_TINT[value] ?? 0.5;
      else if (key === "verses") tint = 0.3 + 0.2 * (value - 2);
      else if (key === "lead") tint = { whistle: 0.35, fiddle: 0.6, lute: 0.85 }[value] ?? 0.5;
      else if (key === "style") tint = value === "ballad" ? 0.3 : 0.75;
      const w = Math.max(1, x(b - 1) - x(a) + (width - left - right) / n);
      root.append(svg("rect", { x: x(a), y, width: w, height: laneH, rx: 3, fill: key === "key" ? time : accent,
        "fill-opacity": (0.15 + 0.6 * tint).toFixed(2) }, svg("title", {}, `${tl.dates[a]} to ${tl.dates[b - 1]}: ${label(key, value, tl)}`)));
      const text = label(key, value, tl, w);
      if (w > 10 + 6.4 * text.length) root.append(svg("text", { x: x(a) + 4, y: y + 15, fill: ink }, text));
    }
  });
  root.append(svg("line", { class: "today-mark", x1: x(today), x2: x(today), y1: 0, y2: height - 18 }));
  const cursor = svg("line", { class: "cursor", x1: x(at), x2: x(at), y1: 0, y2: height - 18 });
  root.append(cursor);
  root._tl = tl;
  root._width = width;
  root._cursor = cursor;
  const pick = (ev) => {
    const r = root.getBoundingClientRect();
    const px = (ev.clientX - r.left) * (width / r.width);
    const i = Math.round(((px - left) / (width - left - right)) * (n - 1));
    setDay(Math.max(-tl.today, Math.min(tl.today, i - tl.today)));
  };
  root.addEventListener("click", pick);
  box.replaceChildren(root);
}

function label(key, value, tl, w) {
  if (key === "pattern") return (tl.patterns[value] || value).replace(/^a /, "");
  if (key === "lead") return tl.players[value] || value;
  if (key === "verses") return `${value} verses`;
  if (key === "style") return ((tl.styles || {})[value] || value).replace(/^(a|the) /, "");
  return String(value);
}

function dateAt(offset) {
  if (!offset) return null;
  const day = new Date(`${state.start.day}T12:00:00Z`);
  day.setUTCDate(day.getUTCDate() + offset);
  return day.toISOString().slice(0, 10);
}

function setDay(offset, group = null) {
  setEdits({ date: dateAt(offset) }, "Move through time", group);
  setOn("day", "value", offset);
  setOn("dayLabel", "textContent", offset ? `${dateAt(offset)} · ${offset > 0 ? "+" : ""}${offset} days` : "today");
}

// ------------------------------------------------------------------ other machines

let compareTimer = null;
function loadCompare() {
  clearTimeout(compareTimer);
  compareTimer = setTimeout(async () => {
    try {
      const date = state.edits.date ? { date: state.edits.date } : {};
      const revision = state.editRevision, names = JSON.stringify(state.names);
      const compare = await api("/api/compare", { edits: Object.assign({}, state.edits, date), names: state.names });
      if (revision !== state.editRevision || names !== JSON.stringify(state.names)) return;
      state.compare = compare;
      renderCompare();
    } catch (e) { /* shown on the next try */ }
  }, 250);
}

function renderCompare() {
  if (!$("compare")) return;
  const rows = state.compare.machines;
  const names = Object.keys(rows[0].rows);
  const table = h("table", { class: "compare" },
    h("thead", {}, h("tr", {}, h("th", {}, ""), rows.map((m) => h("th", {}, m.name, " ",
      h("button", { class: "play", type: "button", "aria-label": `Play ${m.name}'s whole song`, onclick: () => listen(m.who, null) }, playIcon()))))),
    h("tbody", {}, names.map((name) => h("tr", {}, h("td", { class: "rowname" }, name),
      rows.map((m, i) => h("td", { class: i && m.rows[name] !== rows[0].rows[name] ? "differs" : null }, m.rows[name]))))));
  table.title = "Where theirs differs from yours, it is marked.";
  $("compare").replaceChildren(table);
}

// ------------------------------------------------------------------ listening

const audio = $("audio");
// A preview stopped, started or moved mid-note clicks: its volume is taken down (or up) over a few milliseconds
// first. An <audio> has no gain ramp of its own, so the volume is stepped every 4 ms (FADE_MS in all); a new
// fade takes over from one under way, and a pause only happens if no play came in the meantime.
const FADE_MS = 24;
const stopFade = () => { if (audio._fade) clearInterval(audio._fade); audio._fade = null; };
function fadeAudio(to, ms = FADE_MS) {
  stopFade();
  const from = Number.isFinite(audio.volume) ? audio.volume : to;
  return new Promise((resolve) => {
    if (ms <= 0 || Math.abs(from - to) < 1e-3 || typeof setInterval !== "function") { audio.volume = to; resolve(); return; }
    const t0 = performance.now();
    audio._fade = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / ms);
      audio.volume = from + (to - from) * k;
      if (k >= 1) { clearInterval(audio._fade); audio._fade = null; resolve(); }
    }, 4);
  });
}
function quietPause() {
  if (audio.paused !== false) { audio.pause(); return Promise.resolve(); }  // (paused, or no media here at all)
  const asked = audio._asked = {};
  return fadeAudio(0).then(() => { if (audio._asked !== asked) return; audio.pause(); audio.volume = 1; });
}
// late: brought up only once it sounds (a song begun at a bar line mid-way, which isn't silence, sounds only once
// it has loaded); a pause or a jump in the meantime takes that over
function quietPlay(late = false) {
  const asked = audio._asked = {};
  if (audio.paused !== false) audio.volume = 0;
  const started = audio.play();
  if (late) Promise.resolve(started).then(() => { if (audio._asked === asked) fadeAudio(1); }, () => {});
  else fadeAudio(1, audio.currentTime > 0.05 ? FADE_MS : 8);
  return started;
}
function quietSeek(time) {
  if (audio.paused !== false) { audio.currentTime = time; return; }
  const asked = audio._asked = {};
  fadeAudio(0).then(() => { if (audio._asked !== asked) return; audio.currentTime = time; fadeAudio(1); });
}
// every preview and recording is asked of one renderer (renderer.js: the server's queue today)
const renderer = () => window.SongbirdRenderer.create((path, body) => api(path, body));

// bar: the whole song from a bar of the score's ruler (its playhead's), not its start
async function listen(who = "you", section = null, bar = null) {
  window.SongbirdComposer?.stop();
  if (state.playing?.task) renderer().cancel(state.playing.task);  // one still waiting its turn is dropped
  quietPause();
  const label = section === null ? "The whole song" : state.view.words.find((w) => w.index === section)?.label || "Song section";
  // the published version with nothing changed is its own recording: played at once, from the file as released,
  // where the site has it (nothing is made again). From a later bar, by the score's own time for that bar.
  const released = state.start?.published?.audio;
  if (released && who === "you" && section === null && !state.edits.roll
      && !(state.view.changed || []).some((p) => p !== "name")) {  // (a title of its own changes no sound)
    const sections = state.view.composition?.sections || [], perBar = state.view.composition?.beats_per_bar || 4;
    const first = sections[0]?.start_beat || 0;
    const from = Number.isInteger(bar) && bar > 1 ? sections.find((x) => Math.round((x.start_beat - first) / perBar) + 1 === bar) : null;
    play(released, label, "as published", { who, section, label, job: null, editsKey: JSON.stringify(copyEdits()), bar: null },
      from ? from.start_seconds : 0);
    return;
  }
  const edits = copyEdits();
  const playing = { who, section, label, job: null, editsKey: JSON.stringify(edits), bar: section === null ? bar : null };
  state.playing = playing;
  setOn("playPause", "disabled", true);
  setOn("nowTime", "textContent", "");
  showPlayer(label, "getting it ready…", 0, true);
  try {
    playing.task = renderer().preview({ edits, who, section }, (job) => making(job, playing));
    finished(await playing.task.done, playing);
  } catch (e) {
    if (playing === state.playing) { showPlayer(label, e.message, 0, false); toast(e.message); }
  }
}

function pauseAudio() {
  const playing = state.playing;
  quietPause();
  if (!playing) return;
  if (playing.task) renderer().cancel(playing.task);
  // A replacement identity invalidates both in-flight listen and job responses. Keep the edit snapshot
  // so resuming a finished audio track still says when its choices differ from the current song.
  state.playing = { ...playing };
  if (!playing.job || ["queued", "running"].includes(playing.job.state)) {
    showPlayer(playing.label, "Stopped while the sketch plays", 0, false);
    setOn("playPause", "disabled", true);
  }
}

function making(job, playing) {  // a preview on its way: waiting its turn, or being made
  if (playing !== state.playing) return;
  playing.job = job;
  playing.since = playing.since || Date.now();
  const slow = Date.now() - playing.since > 8000 && (job.progress || 0) < 0.05
    ? " (the first one takes longer, while the program warms up)" : "";
  const where = job.state === "queued" ? waitingWords(job) : `${job.stage || "making it"}…`;
  showPlayer(job.label || playing.label, `${where} ${Math.round((job.progress || 0) * 100)}%${slow}`, job.progress || 0, true);
}

function finished(job, playing) {
  if (playing !== state.playing || playing.task?.cancelled) return;
  playing.job = job;
  const title = job.label || playing.label;
  if (job.state === "done") {
    play(job.url, title, playing.section === null ? "the whole song, as it would be recorded" : "a preview of this part", playing,
      barTime(job.result?.bar_seconds, playing.bar));
    refreshReady(job.key);
    return;
  }
  showPlayer(title, job.error === "cancelled" ? "stopped" : `couldn't make it: ${job.error}`, 0, false);
  if (job.error !== "cancelled") toast(`Couldn't make it: ${job.error}`);  // a narrow screen hides the player's small line
}

// One song is made at a time; a shared studio's visitors wait on each other, so say how many are ahead.
function waitingWords(job) {
  return job.ahead ? `waiting its turn (${job.ahead} ahead${publicWait(job)})` : "waiting its turn";
}

function refreshReady(key) {
  if (key && state.view && !state.view.listen.ready.includes(key)) {
    state.view.listen.ready.push(key);
    renderWords();
  }
}

// Where a bar of the ruler is in a whole song's audio: its bar line's time there, from the bar lines a whole song's
// job ends with (bar_seconds, by that rendition's own clock: a count-in, a slow air and the final ritardando
// included). Bar 1, or none: 0, the very start, with the breath and the first pickup before bar 1.
function barTime(seconds, bar) {
  return Array.isArray(seconds) && Number.isInteger(bar) && bar > 1 && bar <= seconds.length ? seconds[bar - 1] : 0;
}

// start: where in it to begin (seconds), when not at its beginning. A time set before it has loaded is where a
// browser starts it; one that let it go is told again once it knows the song's length.
function play(url, title, sub, playing = null, start = 0) {
  state.playing = playing || { editsKey: JSON.stringify(state.edits), label: title, who: "you", section: null, job: null };
  stopFade();
  audio.src = url;
  window.SongbirdRenderer?.playing?.(url);  // kept while it plays, though the renderer's cache lets it go
  const at = audio._start = start > 0 ? {} : null;
  if (at) {
    audio.currentTime = start;
    audio.addEventListener("loadedmetadata", () => {
      if (audio._start === at && Math.abs(audio.currentTime - start) > 0.05) audio.currentTime = start;
    }, { once: true });
  }
  // made long after the press that asked for it, a browser may refuse to start it unasked (Safari on a phone does):
  // then it waits, and says so
  quietPlay(!!at)?.catch?.((e) => {
    if (e?.name !== "NotAllowedError" || audio._asked === undefined || !audio.paused) return;
    showPlayer(title, "ready: press ▶ to hear it", 0, false);
    toast("Ready: press ▶ to hear it.");
  });
  showPlayer(title, sub || "", 0, false);
  setOn("playPause", "disabled", false);
}

function showPlayer(title, sub, progress, making) {
  setOn("nowTitle", "textContent", title);
  state.playerSub = sub;
  markAudioState();
  $("bar")?.classList.toggle("making", !!making);
  if ($("barFill")) $("barFill").style.width = `${Math.round((progress || 0) * 100)}%`;
  score()?.playerChanged?.(title, sub, making);
}

function markAudioState() {
  const stale = !!state.playing && state.playing.editsKey !== JSON.stringify(state.edits);
  const player = document.querySelector(".player");
  player?.classList.toggle("player-stale", stale);
  if ($("nowSub")) $("nowSub").textContent = stale ? "Earlier version · press ▶ to hear your changes" : state.playerSub;
}

audio.addEventListener("timeupdate", () => {
  if (!audio.duration) return;
  if ($("barFill")) $("barFill").style.width = `${(audio.currentTime / audio.duration) * 100}%`;
  setOn("nowTime", "textContent", `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`);
});
audio.addEventListener("play", () => { window.SongbirdComposer?.stop(); $("playShape")?.setAttribute("d", PAUSE); $("playPause")?.setAttribute("aria-label", "Pause"); });
audio.addEventListener("pause", () => { $("playShape")?.setAttribute("d", PLAY); $("playPause")?.setAttribute("aria-label", "Play"); });
$("playPause")?.addEventListener("click", () => (audio.paused ? quietPlay() : quietPause()));
$("bar")?.addEventListener("click", (ev) => {
  if (!audio.duration) return;
  const r = ev.currentTarget.getBoundingClientRect();
  quietSeek(((ev.clientX - r.left) / r.width) * audio.duration);
});

// ------------------------------------------------------------------ singing and recording

async function sing() {
  const note = $("singNote") || { set textContent(text) { toast(text); } };
  const tab = window.open("about:blank", "_blank");
  note.textContent = "Opening the singing page…";
  try {
    const r = await api("/api/sing", {});
    if (r.url) {
      if (tab) tab.location = r.url; else window.location.href = r.url;
      note.textContent = "The singing page is open in another tab. When you've made your phrasing there, come back: the singer's card will offer to sing it your way.";
    } else {
      if (tab) tab.close();
      note.textContent = r.error;
    }
  } catch (e) {
    if (tab) tab.close();
    note.textContent = e.message;
  }
}

function revealRecording(scroll = false) {
  if (score()?.reveal) return score().reveal();  // the score's Export menu
  const panel = $("recordPanel");
  const details = panel.closest("details.finish-panel") || panel.closest("details");
  if (details) details.open = true;
  if (scroll) panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function record() {
  const saved = $("saved");
  if (state.recording) return;
  state.recording = true;
  setOn("record", "disabled", true);
  saved.replaceChildren(h("p", {}, "Exporting…"));
  revealRecording(true);
  const edits = copyEdits();
  try {
    const task = renderer().record({ edits }, (job) => {
      const words = `Exporting: ${job.state === "queued" ? waitingWords(job) : job.stage || "making it"}… ${Math.round((job.progress || 0) * 100)}%`;
      saved.replaceChildren(h("p", {}, words), h("div", { class: "bar making" }, h("div", { style: null })));
      saved.querySelector(".bar > div").style.width = `${Math.round((job.progress || 0) * 100)}%`;
      score()?.recording?.(words, job.progress || 0);
    });
    const job = await task.done;
    if (job.state === "failed") throw new Error(job.error);
    const r = job.result.recorded;
    state.exported = { r, job, key: JSON.stringify(edits) };
    saved.replaceChildren(exportReady(r, job, edits));
    $("record")?.classList.remove("primary");  // the file is made: the way to take it is the one to press now
    toast("Exported.");
  } catch (e) {
    saved.replaceChildren(h("p", { class: "problem" }, `Couldn't export it: ${e.message}`));
    toast(`Couldn't export it: ${e.message}`);
  } finally {
    revealRecording();
    state.recording = false;
    setOn("record", "disabled", false);
    score()?.recording?.(null);
  }
}

// ------------------------------------------------------------------ open to the public (studio --public)
// A public studio's waits, limits and downloads, in words; kept here, apart, so the rest reads as it did.
// Its refusals (a full queue, a limit reached) come from the server as sentences with when to try again,
// and show where any other trouble does: in the player, or under Record.

function publicWait(job) {  // the server's guess at the wait, when it makes one (only a public studio does)
  if (!job.eta) return "";
  const minutes = Math.round(job.eta / 60);
  return minutes <= 1 ? ", about a minute" : `, about ${minutes} minutes`;
}

function publicKept(r) {
  return r.expires ? ` Kept here ${r.expires} hours.` : "";
}

function applyPublic(s) {
  const p = s.public;
  if (!p) return;
  setOn("localBadge", "textContent", "Open studio");
  setOn("whereNote", "textContent", "An open studio: songs are made one at a time. Your changes stay in this browser (Help says what's kept).");
  setOn("helpWhere", "textContent", `This studio is open to anyone. A small server makes the song, one at a time for everyone, so you may wait your turn; each person can have ${p.records} whole songs and ${p.previews} sections made an hour, and what's made already plays at once. What you export is yours to download (it waits ${p.download_hours} hours). Your changes stay in this browser.`);
  setOn("helpKept", "textContent", whatsKept(p, s.sing?.web));
  setOn("helpKept", "hidden", false);
}

function whatsKept(p, singing) {  // what an open studio keeps, said plainly (docs/history/web-studio-server-plan.md, "What is logged, and kept")
  const hours = p.download_hours === 24 ? "a day" : `${p.download_hours} hours`;
  return "What's kept: a random id in a cookie, so everyone gets a fair share (it names nobody). Your changes stay in " +
    "this browser, sent only to make the song. A recording waits here " + hours + " to be downloaded, then goes. A " +
    "shared /v/ link, and any file you download, carries its version's record: its made-up machine's name, the " +
    "room its microphone heard, the leanings of its words." +
    (singing ? " Singing: only numbers are kept; the audio is deleted once it's measured." : "");
}

// ------------------------------------------------------------------ on the device (the static site: no server)
// The studio runs in this browser (web/studio-wasm/device.js answers the page's questions; renderer.js makes every
// song here), so what the page says is kept, and where, is this browser's. Kept here, apart, as the public studio's
// words are. docs/WEB-STUDIO.md, "On the device".

function applyDevice(s) {
  if (!s.device) return;
  setOn("whereNote", "textContent", "Your changes stay on this device unless you share a version. The site counts visits (Cloudflare Web Analytics, no cookies).");
  setOn("helpShows", "textContent", s.published ? "This studio opens on the song as it was published, and lets you:"
    : "This studio shows today's version of the song, and lets you:");
  if (window.SongbirdDevice?.share) setOn("shareTool", "hidden", false);  // a link to your version, from Export
  setOn("helpWhere", "hidden", true);  // the page's foot says it
  // the file's record (its made-up machine's name, the room, the words' leanings) and what any site sees of what it
  // serves: docs/WEB-STUDIO.md, "On the device"
  setOn("helpKept", "textContent", "What's kept: your changes, in this browser. An export stays until you leave the page, so download it to keep it. A version you share is stored on this site, where anyone with its link can open it; it is deleted 30 days after it was last opened. Your name isn't in it.");
  setOn("helpKept", "hidden", false);
  const crashed = window.SongbirdDevice?.crashed?.();
  if (crashed) {
    $("saved")?.replaceChildren(h("p", { class: "problem" }, crashed));
    toast(crashed, 9000);
  }
}

// The web studio opens on the published version as it was released (at once: the build answered it ahead), and
// offers this browser's own new version of it, first thing under the title; there, the way back. docs/WEB-STUDIO.md,
// "The published version first".
function applyPublished(s) {
  const bar = $("publishedBar");
  if (!bar) return;
  const p = s.published;
  if (p) {
    setOn("timeBtn", "hidden", true);  // nothing moves it: no other days, no machine to compare
    setOn("helpCompare", "hidden", true);
    setOn("helpTimeKey", "hidden", true);
    bar.replaceChildren(h("a", { class: "btn primary", href: "/?new", id: "toNew",
      title: "Every browser sings the song a little differently, and it changes from day to day. This makes the version yours sings today, for you to change." },
      "Hear your machine's version \u2192"));
  } else if (s.published_offer) {
    bar.classList.add("back");
    bar.replaceChildren(h("a", { href: "/" }, "\u2190 the published version"));
  } else {
    return;
  }
  bar.hidden = false;
}

// An export, ready: one line saying so, then what to do with it, each a button of the same kind (take it, hear it,
// and where the studio can keep it for a link, share it). Where the link goes once there is one: #shareOut.
function exportReady(r, job, edits) {
  const yours = r.yours ? ` \u00B7 ${r.yours} choice${r.yours === 1 ? "" : "s"} marked as yours` : "";
  const canShare = r.device && r.file && window.SongbirdDevice?.share;
  return h("div", { class: "export-ready" },
    h("p", { title: "The song, the program that sang it and its record, in one file. Your name isn't in it." },
      r.shared ? `Ready \u00B7 ${fmtTime(r.duration)}` : `Saved as ${r.flac} \u00B7 ${fmtTime(r.duration)}`, publicKept(r), yours),
    h("div", { class: "actions" },
      r.shared ? h("a", { class: "btn primary", href: r.download, download: r.name }, "Download") : null,
      h("button", { class: "btn", type: "button", onclick: () => play(job.url, "Your export", r.flac,
        { editsKey: JSON.stringify(edits), label: "Your export", who: "you", section: null, job }) }, "Play"),
      canShare ? h("button", { class: "btn", type: "button", id: "shareIt", title: SHARE_WHAT, onclick: () => shareExport() }, "Share") : null),
    h("div", { class: "share-out", id: "shareOut", "aria-live": "polite" }));
}

// Sharing: the exported file sent to the site (the studio's only upload), which keeps it under a link. The link is
// the file's own (its hash), so there is no sharing without the file: where none has been made of the song as it
// is now, Share makes it first, then sends it.
const SHARE_WHAT = "Sends the file to this site, which keeps it so anyone with the link can open it and make the next version. It is deleted 30 days after it was last opened. Nothing else leaves this device.";

async function shareExport() {
  if (state.sharing) return;
  state.sharing = true;
  for (const id of ["shareNow", "shareIt"]) setOn(id, "disabled", true);
  try {
    const current = () => state.exported && state.exported.key === JSON.stringify(copyEdits()) && state.exported.r.file;
    if (!current()) await record();
    if (!current()) return;  // it couldn't be made: record() has said why
    revealRecording();
    const out = $("shareOut");
    out.replaceChildren(h("p", {}, "Sending it\u2026"));
    try {
      const shared = await window.SongbirdDevice.share(state.exported.r.file);
      const field = h("input", { type: "text", readonly: "", value: shared.url, "aria-label": "The link to your version" });
      field.addEventListener("focus", () => field.select());
      const copy = h("button", { class: "btn", type: "button", onclick: async () => {
        try { await navigator.clipboard.writeText(shared.url); copy.textContent = "Copied"; }
        catch (e) { field.focus(); toast("Copy the link from its box"); }
      } }, "Copy link");
      out.replaceChildren(h("div", { class: "share-link" }, field, copy),
        h("p", { class: "hint" }, "Anyone with the link can open your version. It is kept for 30 days after it was last opened."));
      setOn("shareIt", "hidden", true);
    } catch (e) {
      out.replaceChildren(h("p", { class: "problem" }, `Couldn't share it: ${e.message}`));
    }
  } finally {
    state.sharing = false;
    for (const id of ["shareNow", "shareIt"]) setOn(id, "disabled", false);
  }
}

// ------------------------------------------------------------------ putting it together

function render() {
  renderHeader();
  renderWords();
  renderCards();
  renderTimeline();
  renderSessionControls();
  renderHistory();
  window.SongbirdComposer?.render(state.view);
  window.SongbirdPerform?.render(state.view);  // notes in: a part played in, a MIDI file brought back
  score()?.render(state.view);  // the score's views and inspector
  // the version changed (webstudio/sing.js follows it)
  if (typeof CustomEvent === "function") document.dispatchEvent?.(new CustomEvent("studio:render"));
}

function showWorkspace(name, focus = false) {
  const tabs = [...document.querySelectorAll("#studioTabs [data-workspace]")];
  if (!tabs.some((button) => button.dataset.workspace === name)) return;
  if (name !== "arrange") window.SongbirdComposer?.stop();
  state.workspace = name;
  tabs.forEach((button) => {
    const active = button.dataset.workspace === name;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
    if (active && focus) button.focus();
  });
  document.querySelectorAll("[data-workspace-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.workspacePanel !== name;
  });
  if (name === "explore") renderTimeline();
  if (name === "arrange" && state.view) window.SongbirdComposer?.render(state.view);
}

window.StudioBridge = {
  setEdit, setEdits, releaseEdit, clearEdits, listen, toast, pauseAudio,
  getEdits: () => copyEdits(),
  snapshot: () => ({ start: state.start ? JSON.parse(JSON.stringify(state.start)) : null, edits: copyEdits(), revision: state.editRevision }),
  replaceEdits: (edits, label = "Load a saved draft") => commitEdits(edits, label),
  undo: () => travelHistory("undo"), redo: () => travelHistory("redo"),
  showWorkspace,
};

function readHash() {
  // #day=120&open=band,key&choose=verse.1&e=<edits as JSON>: a way into a particular view (and for pictures)
  const out = {};
  for (const part of location.hash.slice(1).split("&")) {
    const [k, v] = part.split("=");
    if (k) out[k] = decodeURIComponent(v || "");
  }
  return out;
}

async function main() {
  try {
    state.start = await api("/api/start");
  } catch (e) {
    stuck(`The studio isn't answering: ${e.message}`);
    return;
  }
  const s = state.start;
  state.names = s.names.slice();
  state.edits = restore();
  const hash = readHash();
  if (hash.e) {
    try { state.edits = editMap(JSON.parse(hash.e)); } catch (e) { /* ignore */ }
  }
  if (hash.day) setDayQuiet(Number(hash.day));
  for (const id of (hash.open || "").split(",").filter(Boolean)) state.open[id] = true;
  setOn("packetNote", "textContent", s.packet);
  if (s.shared) {  // served from someone else's computer for a preview: say so where "this computer" would
    setOn("whereNote", "textContent", "Served from another computer for a short preview. Your changes stay in this browser; recordings are made there.");
    setOn("localBadge", "hidden", false);
    setOn("helpShows", "textContent", "This studio shows the version the computer serving it makes today, and lets you:");
    setOn("helpWhere", "textContent", "This studio is shared from someone else's computer for a short preview: that computer makes the song, and what you record is saved there too. Download it to keep it. Your changes stay in this browser.");
  }
  applyPublic(s);
  applyDevice(s);
  applyVersion(s);
  applyPublished(s);
  setOn("helpSong", "textContent", s.title);
  renderLineage(s.generation || 0);
  setOn("singNote", "textContent", s.sing.available ? "" : s.sing.why);
  setOn("sing", "disabled", !s.sing.available);
  setOn("toFinishLabel", "textContent", s.sing.available ? "Sing or export" : "Export it");
  setOn("day", "min", -s.days);
  setOn("day", "max", s.days);
  score()?.started?.(s, hash);
  showWorkspace(hash.workspace || "words");
  await refresh();
  if (hash.choose && state.view) {
    const [block, nth] = hash.choose.split(".");
    const w = state.view.words.find((x) => x.block === block && String(x.nth) === nth);
    if (w) await toggleChooser(w);
    if (hash.refused !== undefined) for (const d of document.querySelectorAll("details.word-rules")) d.open = true;
  }
  const scroll = () => { const el = hash.scroll && $(hash.scroll); if (el) el.scrollIntoView({ block: "start" }); };
  scroll();
  // on the device the timeline (the heaviest question: seconds of this browser's time) waits until it's looked at
  if (!s.device) loadTimeline(scroll);
  if (hash.compare !== undefined) loadCompare();
  // the song is on the page: help.js may show a first visit around it
  if (typeof CustomEvent === "function") document.dispatchEvent?.(new CustomEvent("studio:ready", { detail: { hash, shared: !!s.shared } }));
}

function loadTimeline(then) {
  if (state.timelineAsked) return;
  state.timelineAsked = true;
  api("/api/timeline").then((tl) => { state.timeline = tl; renderTimeline(); then?.(); }).catch(() => {
    $("timeline")?.replaceChildren(h("p", { class: "hint" }, "The timeline couldn't be drawn."));
  });
}

// The line this version came down: a mark for each version before it (the nearest nine), filled for this one.
function renderLineage(generation) {
  const box = $("lineage");
  box.hidden = !generation;  // the first version has no line yet: a lone mark would read as a bullet
  const shown = Math.min(generation, 9);
  const marks = generation > shown ? [h("span", { class: "more" }, "…")] : [];
  for (let i = 0; i < shown; i++) marks.push(h("i", { class: "was" }));
  marks.push(h("i", { class: "now" }));
  box.replaceChildren(...marks);
  const said = generation ? `${generation} version${generation === 1 ? "" : "s"} came before this one` : "the first version of the song";
  box.setAttribute("aria-label", said);
  box.setAttribute("title", said);
}

function setDayQuiet(offset) {
  const date = dateAt(offset);
  if (date) state.edits.date = date;
  else delete state.edits.date;
}

for (const direction of ["undo", "redo"]) $(`${direction}Edit`)?.addEventListener("click", () => travelHistory(direction));
for (const button of document.querySelectorAll("#studioTabs [data-workspace]")) {
  button.addEventListener("click", () => showWorkspace(button.dataset.workspace));
  button.addEventListener("keydown", (event) => {
    const tabs = [...document.querySelectorAll("#studioTabs [data-workspace]")];
    const index = tabs.indexOf(button);
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    showWorkspace(tabs[next].dataset.workspace, true);
  });
}
document.addEventListener("keydown", (event) => {
  if (!(event.metaKey || event.ctrlKey) || event.altKey) return;
  const target = event.target;
  if (target.isContentEditable || target.tagName === "TEXTAREA" ||
    (target.tagName === "INPUT" && !["range", "checkbox", "button"].includes(target.type))) return;
  const key = event.key.toLowerCase();
  if (key !== "z" && key !== "y") return;
  event.preventDefault();
  travelHistory(key === "y" || event.shiftKey ? "redo" : "undo");
});

$("hearAll")?.addEventListener("click", () => listen("you", null));
// A version's own title: the song's title becomes a field, 60 characters at most; Enter or leaving it keeps
// what was typed, Escape leaves it as it was. Emptied, or the song's own title again, the version goes by the song's.
const TITLE_MAX = 60;  // edits.py NAME_MAX
$("renameBtn")?.addEventListener("click", () => {
  const v = state.view, title = $("title"), button = $("renameBtn");
  if (!v || !title) return;
  const now = v.name || v.title;
  const input = h("input", { type: "text", class: "title-input", maxlength: String(TITLE_MAX), value: now,
    "aria-label": "This version's title" });
  let over = false;
  const finish = (keep) => {
    if (over) return;
    over = true;
    const typed = input.value.replace(/\s+/g, " ").trim().slice(0, TITLE_MAX);
    title.textContent = now;
    button.hidden = false;
    if (!keep || typed === now) return;
    if (!typed || typed === v.title) clearEdits(["name"], "Use the song's own title");
    else setEdit("name", typed, "Rename this version");
  };
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") finish(true);
    else if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
  title.replaceChildren(input);
  button.hidden = true;
  input.focus();
  input.select?.();
});

$("roll")?.addEventListener("click", () => {
  setEdit("roll", (state.edits.roll || 0) + 1);
  toast("A new performance. Press \u25B6 to hear it.");
});
$("record")?.addEventListener("click", record);
$("shareNow")?.addEventListener("click", shareExport);
$("toFinish")?.addEventListener("click", () => {
  // what singing and recording are, and the button that does it: opened, not started, from the top
  const panel = $("finishPanel");
  panel.open = true;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
});
$("sing")?.addEventListener("click", sing);
$("day")?.addEventListener("input", (ev) => {
  const offset = Number(ev.target.value);
  setDay(offset, "day");
});
$("day")?.addEventListener("change", () => { state.historyGroup = null; });
for (const b of document.querySelectorAll("[data-step]")) {
  b.addEventListener("click", () => {
    const step = Number(b.dataset.step);
    const now = state.view ? state.view.offset : 0;
    setDay(step === 0 ? 0 : Math.max(-state.start.days, Math.min(state.start.days, now + step)));
  });
}
$("makeUp")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const name = $("machineName").value.trim();
  if (name && !state.names.includes(name)) state.names.push(name);
  $("machineName").value = "";
  loadCompare();
});
window.addEventListener("resize", () => { clearTimeout(window.__rt); window.__rt = setTimeout(renderTimeline, 150); });
window.addEventListener("focus", async () => {
  // back from the singing page: new phrasings may be ready
  try {
    const phrasings = await api("/api/phrasings");
    if (state.start && state.view && JSON.stringify(phrasings) !== JSON.stringify(state.start.phrasings)) {
      state.start.phrasings = phrasings;
      renderCards();
    }
  } catch (e) { /* the studio may have stopped */ }
});

// ------------------------------------------------------------------ someone's version (/api/open, /v/<id>)
// A version someone was sent (its .flac), dropped anywhere on the page or chosen in "Open someone's version",
// is sent to the studio, which reads it as data (never running the program it carries) and answers with its
// link; the page then opens there, on that version as the parent. At /v/<id> the header says whose version this
// continues and gives the link to share. Kept here, apart; the rest of the page only learns the version through
// its token (every request sends it). docs/WEB-STUDIO.md, "Opening someone's version".

function applyVersion(s) {
  const bar = $("versionBar");
  const v = s.version;
  if (bar) bar.hidden = !v;
  if (!v || !bar) return;
  const which = ORDINAL_WORDS[v.generation] ? `the ${ORDINAL_WORDS[v.generation]} version` : `a version ${v.generation + 1} down the line`;
  const made = v.made ? `, made ${new Date(`${v.made}T12:00:00Z`).toLocaleDateString("en-US", { timeZone: "UTC", month: "long", day: "numeric", year: "numeric" })}` : "";
  const link = new URL(v.url, location.href).href;
  const copy = h("button", { class: "link small", type: "button", onclick: async () => {
    try { await navigator.clipboard.writeText(link); toast("The link is copied"); }
    catch (e) { toast("Copy the link from the address bar"); }
  } }, "copy the link");
  // on the device, a file the visitor brought is theirs alone (kept in this browser, no link); a shared one has its link
  const fromFile = s.device && !v.shared;
  const how = fromFile ? "which you opened from a file" : s.device ? "which someone shared" : "which someone brought here";
  // one line: whose this is, the way to hear it as it came (its own file, where the site keeps it), its link
  const named = v.name ? `\u201C${v.name}\u201D, ` : "";
  const heard = s.device && v.shared && window.SongbirdDevice?.linked
    ? h("button", { class: "link small", type: "button", title: "Its own file, as it was shared: nothing is made again",
      onclick: () => play(`/api/versions/${window.SongbirdDevice.linked}`, v.name || "Someone's version", "as it was shared",
        { editsKey: null, label: v.name || "Someone's version", who: "shared", section: null, job: null }) }, "\u25B6 hear it as shared")
    : null;
  bar.replaceChildren(h("p", { title: v.program_note },
    tag("lineage", "someone's version"), " ", `Continuing ${named}${which}${made}, ${how}. What you export is its child.`,
    ...[heard, fromFile ? null : copy, h("a", { href: "/" }, "the published version")].filter(Boolean).flatMap((x) => [" \u00B7 ", x])));
  setOn("versionNote", "textContent", "This page is on someone's version. Opening another starts from that one instead.");
}
const ORDINAL_WORDS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth",
  "eleventh", "twelfth"];

async function openVersionFile(file) {
  const note = $("versionNote") || {};
  const say = (text) => { note.textContent = text; toast(text); };
  if (!file) return;
  if (!/\.flac$/i.test(file.name) && file.type !== "audio/flac") {
    say(`${file.name} isn't a .flac file. A version of the song comes as one .flac file.`);
    return;
  }
  const most = (state.start?.open?.upload_mb || 64) * 2 ** 20;
  if (file.size > most) {
    say(`${file.name} is ${Math.round(file.size / 2 ** 20)} MB; a version is about 15 to 20 (the most taken here is ${most / 2 ** 20} MB).`);
    return;
  }
  if (openVersionFile.busy) return;
  openVersionFile.busy = true;
  setOn("versionChoose", "disabled", true);
  try {
    // asked first, so a file that would be turned away (a limit reached, the studio busy) isn't sent for nothing
    await api("/api/open/ready", { size: file.size });
    note.textContent = `Reading ${file.name}… (it's only read, never run; this takes a few seconds)`;
    const r = await fetch("/api/open", {
      method: "POST", body: file,
      headers: { "Content-Type": "application/octet-stream", "X-Studio": TOKEN },
    });
    let data;
    try { data = await r.json(); } catch (e) { data = { error: r.statusText }; }
    if (!r.ok) throw new Error(data.error || r.statusText);
    note.textContent = "Opening that version…";
    const to = new URL(data.url, location.href);
    const here = to.pathname === location.pathname && to.search === location.search;
    location.assign(to.href);
    if (here) location.reload();  // only the #version changed (a file opened on the device): opened afresh
  } catch (e) {
    say(`Couldn't open it: ${e.message}`);
  } finally {
    openVersionFile.busy = false;
    setOn("versionChoose", "disabled", false);
  }
}

$("versionChoose")?.addEventListener("click", () => $("versionFile").click());
$("versionFile")?.addEventListener("change", (ev) => {
  const file = ev.target.files && ev.target.files[0];
  ev.target.value = "";
  openVersionFile(file);
});
{
  // a file dragged over the page: the veil says what dropping it does
  const veil = $("dropVeil");
  const carriesFiles = (ev) => [...(ev.dataTransfer?.types || [])].includes("Files");
  let depth = 0;
  document.addEventListener("dragenter", (ev) => { if (carriesFiles(ev)) { depth += 1; veil.hidden = false; } });
  document.addEventListener("dragleave", (ev) => { if (carriesFiles(ev) && --depth <= 0) { depth = 0; veil.hidden = true; } });
  document.addEventListener("dragover", (ev) => { if (carriesFiles(ev)) { ev.preventDefault(); ev.dataTransfer.dropEffect = "copy"; } });
  document.addEventListener("drop", (ev) => {
    if (!carriesFiles(ev)) return;
    ev.preventDefault();
    depth = 0;
    veil.hidden = true;
    openVersionFile(ev.dataTransfer.files[0]);
  });
}

// ------------------------------------------------------------------ singing in the browser (webstudio/sing.js)
// A studio that takes singing in the browser (songbird studio --web-singing, docs/WEB-SINGING.md) adds
// webstudio/sing.js to this page, from outside the song's program. It reaches the studio only through this: the
// ways of singing it made (offered with the singer card's own) and a few of the page's functions. Without it,
// nothing here does anything.
const ownPhrasings = [];
function phrasingChoices(list) {
  const have = list || [];
  return [...have, ...ownPhrasings.filter((p) => !have.some((q) => q.id === p.id))];
}
window.songbirdStudio = { state, api, h, toast, setEdit, refresh, renderCards, listen, revealRecording, ownPhrasings };

main();
