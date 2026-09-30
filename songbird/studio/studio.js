// The studio's page: the song's words, the choices and why, time, other machines, listening, recording.
// Plain JavaScript, no libraries, nothing fetched but this studio's own answers. The page keeps a person's
// edits (a map of choices, songbird/edits.py) and sends them with every request; the browser's storage keeps
// them across a reload. Everything shown is built as text: nothing from an answer is read as markup.
"use strict";

const TOKEN = document.querySelector('meta[name="studio-token"]').content;
const $ = (id) => document.getElementById(id);
const state = {
  start: null, view: null, timeline: null, edits: {}, open: {}, choose: null, options: null,
  names: [], compare: null, busy: 0, playing: null, poll: null, recordJob: null,
  optionsByKey: {}, optionsFailed: false, undo: [], redo: [], editRevision: 0, refreshSerial: 0,
  historyGroup: null, workspace: "words", saveStatus: "Saved in this browser", playerSub: "",
  solo: null, mutedLevels: {},
};

// ------------------------------------------------------------------ small helpers

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
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
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const c of children.flat()) if (c !== null && c !== undefined) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}

const PLAY = "M4 2.5v11l9-5.5z";
const PAUSE = "M4 2.5h3v11H4zM9 2.5h3v11H9z";
function playIcon() {
  return svg("svg", { viewBox: "0 0 16 16", "aria-hidden": "true" }, svg("path", { d: PLAY, fill: "currentColor" }));
}

async function api(path, body) {
  const options = body === undefined ? {} : {
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

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 2600);
}

// Saved edits belong to the exact song genome they were made for, as a draft does (drafts.js): a tune or lyric
// edit made for another version of the song's file would come back as a problem on every visit.
function storeKey() {
  const s = state.start;
  return s ? `songbird-studio|${s.title}|${s.from}|${s.machine.label}|${s.song_digest || ""}` : null;
}
function olderStoreKey() {  // before the key carried the song's digest
  const s = state.start;
  return s ? `songbird-studio|${s.title}|${s.from}|${s.machine.label}` : null;
}
// Edits written for one genome's tune, lyric keys, word bank or sections: never carried over from an unknown one.
const GENOME_BOUND = /^(tune|lyrics|words)\.|^form\.order$/;
function save() {
  // only ever after a person's own change (edits that came in the page's address are never saved on their
  // own); the day and chance drawn again aren't kept, so tomorrow opens on tomorrow
  const kept = Object.fromEntries(Object.entries(state.edits).filter(([p]) => p !== "date" && p !== "roll"));
  try {
    localStorage.setItem(storeKey(), JSON.stringify(kept));
    state.saveStatus = "Saved in this browser";
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
    if (!state.view) $("which").textContent = `The studio couldn't make your version of the song: ${e.message}`;
    toast(e.message);
  } finally {
    state.busy--;
    renderHistory();
  }
}

// ------------------------------------------------------------------ the header

function renderHeader() {
  const v = state.view;
  $("title").textContent = v.title;
  document.title = `${v.title} · Songbird studio`;
  const when = v.offset ? `on ${v.date} (${v.when})` : `today, ${v.date}`;
  $("which").replaceChildren("Your version ", h("b", {}, when), `, ${v.from}, sung by ${v.by}.`);
  $("draw").textContent = v.roll ? `chance drawn again: draw ${v.roll + 1}` : "";
  const mine = v.changed;
  const held = v.held.length > 0;
  const bar = $("yoursBar");
  bar.hidden = !mine.length && !held;
  bar.replaceChildren();
  if (mine.length || held) {
    bar.append(...[
      mine.length ? tag("you", `${mine.length} choice${mine.length === 1 ? " is" : "s are"} yours`) : null,
      held ? tag("you", "the words are kept") : null,
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
  $("day").value = v.offset;
  $("dayLabel").textContent = v.offset ? `${v.date} (${v.when})` : `today, ${v.date}`;
}

function describePath(path) {
  const m = path.match(/^words\.(verse|refrain)\.(\d+)$/);
  if (m) return `your ${m[1]} ${Number(m[2]) + 1}`;
  return { "words.refrain": "your refrain's words", "words.bridge": "your bridge's words", "words.bridge2": "your second bridge", "words.tag": "your tag", "phrasing": "the singer's way", "date": "the day" }[path] || `your ${path.replace(/^\w+\./, "").replace(/_/g, " ")}`;
}

// ------------------------------------------------------------------ the words

function renderWords() {
  const v = state.view;
  const box = $("words");
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
      if (!allAuthored && options.choices.length) selects.append(phraseChooser(w, options));
      if (!allAuthored && (options.heads || []).length > 1) selects.append(headChooser(options, w.label));
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
  const paths = [w.path];
  if (w.block === "refrain") paths.push("words.refrain");
  if (w.block === "bridge" && w.nth === 0) paths.push("words.bridge");
  const next = copyEdits();
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
  commitEdits(next, `Reset ${w.label.toLowerCase()} words`);
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
  select.addEventListener("change", () => setEdit(o.path, o.block === "verse" ? { id: select.value }
    : o.block === "refrain" ? Object.assign(refrainEdit(o), { id: select.value }) : select.value,
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
  select.addEventListener("change", () => chooseSlot(o, slot.slot, select.value));
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
  select.addEventListener("change", () => {
    const edit = refrainEdit(o);
    delete edit.slots;
    edit.head = select.value;
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
    const input = h("input", { type: "number", min: bounds.tempo.min, max: bounds.tempo.max, step: bounds.tempo.step,
      value: tempo.tempo, "aria-label": "Tempo in beats per minute" });
    input.addEventListener("change", () => {
      const value = Number(input.value);
      if (!input.value || !Number.isFinite(value) || value < bounds.tempo.min || value > bounds.tempo.max) {
        input.value = tempo.tempo;
        toast(`Choose a tempo from ${bounds.tempo.min} to ${bounds.tempo.max} BPM.`);
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

function currentSolo() {
  if (state.solo && Object.entries(state.solo.patch).some(([path, value]) => state.edits[path] !== value)) state.solo = null;
  return state.solo;
}

function soloPlayer(card, player) {
  const active = currentSolo();
  if (active?.player === player) {
    state.solo = null;
    setEdits(active.before, "Restore the band mix");
    return;
  }
  const names = Object.keys(card.players);
  const before = active?.before || Object.fromEntries(names.map((name) => {
    const path = `band.${name}`;
    return [path, Object.hasOwn(state.edits, path) ? state.edits[path] : null];
  }));
  const levels = active?.levels || Object.fromEntries(names.map((name) => [name, card.band[name]]));
  const patch = Object.fromEntries(names.map((name) => [`band.${name}`, name === player ? Math.max(0.03, levels[name] || 1) : 0]));
  state.solo = { player, before, levels, patch };
  setEdits(patch, `Solo ${card.players[player] || player}`);
}

function mutePlayer(card, player) {
  const path = `band.${player}`, level = card.band[player] || 0;
  if (level > 0.02) {
    state.mutedLevels[player] = level;
    setEdit(path, 0, `Mute ${card.players[player] || player}`);
  } else {
    setEdit(path, state.mutedLevels[player] || 1, `Unmute ${card.players[player] || player}`);
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
        h("p", { class: "hint aside-note" }, "A minor mode leans the words darker, as the machine's own would."));
    }
    case "tempo":
      return slider("Beats a minute", "tempo", c.tempo, b.tempo, (x) => `${Number(x).toFixed(0)}`, ["slower", "quicker"]);
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
        h("p", { class: "hint aside-note" }, "M mutes a player. S isolates a player in the band; click again to restore the mix. The singer stays audible."),
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
        h("p", { class: "hint aside-note" }, "A style brings its own band, its pace and its feel; a version moves one style at a time, so its children will drift back toward your machine's."));
    }
    case "mix": {
      const m = c.mix;
      return h("div", {},
        slider("How much of the room", "mix.space", m.space, b["mix.space"], (x) => `${Math.round(x * 100)}%`, ["dry", "roomy"]),
        slider("How wide", "mix.width", m.width, b["mix.width"], (x) => `${Math.round(x * 100)}%`, ["narrow", "wide"]),
        slider("The voice over the band", "mix.forward", m.forward, b["mix.forward"], (x) => `${Number(x).toFixed(1)} dB`, ["among it", "well over it"]),
        slider("How close the singer is", "mix.intimacy", m.intimacy, b["mix.intimacy"], (x) => `${Math.round(x * 100)}%`, ["further back", "at your ear"]),
        h("p", { class: "hint aside-note" }, "Judge the voice against the band on the whole song: a part heard alone is levelled for listening."));
    }
    case "singer": {
      const box = h("div", {}, h("p", { class: "hint" }, "The singer is your machine's own voice, the same in every song it sings. What you can give it is your way of singing."));
      const phrasings = phrasingChoices(s.phrasings);  // with the one sung in this browser, if any
      if (phrasings.length) {
        const select = h("select", { "aria-label": "Whose way it is sung" },
          h("option", { value: "" }, "the song's own way"),
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
  if (!tl) return;
  const width = Math.max(320, box.clientWidth || 800);
  const n = tl.dates.length;
  const left = 70, right = 10, laneH = 22, gap = 8;
  const x = (i) => left + (i / (n - 1)) * (width - left - right);
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
  const today = tl.today;
  root.append(svg("line", { class: "today-mark", x1: x(today), x2: x(today), y1: 0, y2: height - 18 }));
  const at = today + (state.view ? state.view.offset : 0);
  root.append(svg("line", { class: "cursor", x1: x(at), x2: x(at), y1: 0, y2: height - 18 }));
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
  $("day").value = offset;
  $("dayLabel").textContent = offset ? `${dateAt(offset)} · ${offset > 0 ? "+" : ""}${offset} days` : "today";
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
  const rows = state.compare.machines;
  const names = Object.keys(rows[0].rows);
  const table = h("table", { class: "compare" },
    h("thead", {}, h("tr", {}, h("th", {}, ""), rows.map((m) => h("th", {}, m.name, " ",
      h("button", { class: "play", type: "button", "aria-label": `Play ${m.name}'s whole song`, onclick: () => listen(m.who, null) }, playIcon()))))),
    h("tbody", {}, names.map((name) => h("tr", {}, h("td", { class: "rowname" }, name),
      rows.map((m, i) => h("td", { class: i && m.rows[name] !== rows[0].rows[name] ? "differs" : null }, m.rows[name]))))));
  $("compare").replaceChildren(table, h("p", { class: "hint" }, "Where theirs differs from yours, it is marked."));
}

// ------------------------------------------------------------------ listening

const audio = $("audio");

async function listen(who = "you", section = null) {
  window.SongbirdComposer?.stop();
  if (state.poll && state.playing && state.playing.job && state.playing.job.state === "queued") {
    api("/api/cancel", { job: state.playing.job.id }).catch(() => {});
  }
  clearTimeout(state.poll);
  audio.pause();
  const label = section === null ? "The whole song" : state.view.words.find((w) => w.index === section)?.label || "Song section";
  const edits = copyEdits();
  const playing = { who, section, label, job: null, editsKey: JSON.stringify(edits) };
  state.playing = playing;
  $("playPause").disabled = true;
  $("nowTime").textContent = "";
  showPlayer(label, "getting it ready…", 0, true);
  try {
    const job = await api("/api/listen", { edits, who, section });
    await follow(job, playing);
  } catch (e) {
    if (playing === state.playing) showPlayer(label, e.message, 0, false);
  }
}

function pauseAudio() {
  const playing = state.playing;
  audio.pause();
  clearTimeout(state.poll);
  state.poll = null;
  if (!playing) return;
  if (playing.job?.state === "queued") api("/api/cancel", { job: playing.job.id }).catch(() => {});
  // A replacement identity invalidates both in-flight listen and job responses. Keep the edit snapshot
  // so resuming a finished audio track still says when its choices differ from the current song.
  state.playing = { ...playing };
  if (!playing.job || ["queued", "running"].includes(playing.job.state)) {
    showPlayer(playing.label, "Preview stopped while the melody sketch plays", 0, false);
    $("playPause").disabled = true;
  }
}

async function follow(job, playing) {
  if (playing !== state.playing) return;
  playing.job = job;
  const title = job.label || playing.label;
  if (job.state === "done") {
    play(job.url, title, playing.section === null ? "the whole song, as it would be recorded" : "a preview of this part", playing);
    refreshReady(job.key);
    return;
  }
  if (job.state === "failed") {
    showPlayer(title, job.error === "cancelled" ? "stopped" : `couldn't make it: ${job.error}`, 0, false);
    return;
  }
  playing.since = playing.since || Date.now();
  const slow = Date.now() - playing.since > 8000 && (job.progress || 0) < 0.05
    ? " (the first one takes longer, while the program warms up)" : "";
  const where = job.state === "queued" ? waitingWords(job) : `${job.stage || "making it"}…`;
  showPlayer(title, `${where} ${Math.round((job.progress || 0) * 100)}%${slow}`, job.progress || 0, true);
  state.poll = setTimeout(async () => {
    try { await follow(await api(`/api/job/${job.id}`), playing); }
    catch (e) { if (playing === state.playing) showPlayer(title, e.message, 0, false); }
  }, 450);
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

function play(url, title, sub, playing = null) {
  state.playing = playing || { editsKey: JSON.stringify(state.edits), label: title, who: "you", section: null, job: null };
  clearTimeout(state.poll);
  audio.src = url;
  audio.play().catch(() => {});
  showPlayer(title, sub || "", 0, false);
  $("playPause").disabled = false;
}

function showPlayer(title, sub, progress, making) {
  $("nowTitle").textContent = title;
  state.playerSub = sub;
  markAudioState();
  $("bar").classList.toggle("making", !!making);
  $("barFill").style.width = `${Math.round((progress || 0) * 100)}%`;
}

function markAudioState() {
  const stale = !!state.playing && state.playing.editsKey !== JSON.stringify(state.edits);
  const player = document.querySelector(".player");
  player?.classList.toggle("player-stale", stale);
  if ($("nowSub")) $("nowSub").textContent = stale ? "Earlier version · press Play song to hear your edits" : state.playerSub;
}

audio.addEventListener("timeupdate", () => {
  if (!audio.duration) return;
  $("barFill").style.width = `${(audio.currentTime / audio.duration) * 100}%`;
  $("nowTime").textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
});
audio.addEventListener("play", () => { window.SongbirdComposer?.stop(); $("playShape").setAttribute("d", PAUSE); $("playPause").setAttribute("aria-label", "Pause"); });
audio.addEventListener("pause", () => { $("playShape").setAttribute("d", PLAY); $("playPause").setAttribute("aria-label", "Play"); });
$("playPause").addEventListener("click", () => (audio.paused ? audio.play() : audio.pause()));
$("bar").addEventListener("click", (ev) => {
  if (!audio.duration) return;
  const r = ev.currentTarget.getBoundingClientRect();
  audio.currentTime = ((ev.clientX - r.left) / r.width) * audio.duration;
});

// ------------------------------------------------------------------ singing and recording

async function sing() {
  const note = $("singNote");
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
  const panel = $("recordPanel");
  const details = panel.closest("details.finish-panel") || panel.closest("details");
  if (details) details.open = true;
  if (scroll) panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function record() {
  const saved = $("saved");
  if (state.recording) return;
  state.recording = true;
  for (const id of ["record", "recordNow"]) $(id).disabled = true;
  saved.replaceChildren(h("p", {}, "Recording…"));
  revealRecording(true);
  const edits = copyEdits();
  try {
    let job = await api("/api/record", { edits });
    while (job.state === "queued" || job.state === "running") {
      saved.replaceChildren(h("p", {}, `Recording: ${job.state === "queued" ? waitingWords(job) : job.stage || "making it"}… ${Math.round((job.progress || 0) * 100)}%`),
        h("div", { class: "bar making" }, h("div", { style: null })));
      saved.querySelector(".bar > div").style.width = `${Math.round((job.progress || 0) * 100)}%`;
      await new Promise((r) => setTimeout(r, 600));
      job = await api(`/api/job/${job.id}`);
    }
    if (job.state === "failed") throw new Error(job.error);
    const r = job.result.recorded;
    saved.replaceChildren(
      r.shared
        ? h("p", {}, `Made (${fmtTime(r.duration)}): the song, the program that sang it and its record, in one file. `,
          h("a", { class: "btn primary", href: r.download, download: r.name }, "Download it"), publicKept(r))
        : h("p", {}, "Saved ", h("code", {}, r.flac), ` (${fmtTime(r.duration)}): the song, the program that sang it and its record, in one file.`),
      h("p", {}, r.yours ? `${r.yours} choice${r.yours === 1 ? " is" : "s are"} marked as yours in it (what you chose, never who you are).` : "Every choice in it is the program's."),
      h("p", { class: "hint" }, "To make the next version from this one: ", h("code", {}, r.next)),
      h("button", { class: "btn", type: "button", onclick: () => play(job.url, "The recording", r.flac,
        { editsKey: JSON.stringify(edits), label: "The recording", who: "you", section: null, job }) }, "Play the recording"));
    toast("Recording saved with your edits and the studio.");
  } catch (e) {
    saved.replaceChildren(h("p", { class: "problem" }, `Couldn't record it: ${e.message}`));
    toast(`Couldn't record it: ${e.message}`);
  } finally {
    revealRecording();
    state.recording = false;
    for (const id of ["record", "recordNow"]) $(id).disabled = false;
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
  return r.expires ? ` It waits here ${r.expires} hours; after that, the same choices make it again.` : "";
}

function applyPublic(s) {
  const p = s.public;
  if (!p) return;
  $("localBadge").textContent = "Open studio";
  $("whereNote").textContent = "An open studio: the song is made on a small server, one at a time for everyone. Your changes stay in this browser.";
  $("helpWhere").textContent = `This studio is open to anyone. A small server makes the song, one at a time for everyone, so you may wait your turn; each person can have ${p.records} whole songs and ${p.previews} sections made an hour, and what's made already plays at once. What you record is yours to download (it waits ${p.download_hours} hours). Your changes stay in this browser.`;
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
    $("which").textContent = `The studio isn't answering: ${e.message}`;
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
  $("packetNote").textContent = s.packet;
  if (s.shared) {  // served from someone else's computer for a preview: say so where "this computer" would
    $("whereNote").textContent = "Served from another computer for a short preview. Your changes stay in this browser; recordings are made there.";
    $("localBadge").hidden = false;
    $("helpShows").textContent = "This studio shows the version the computer serving it makes today, and lets you:";
    $("helpWhere").textContent = "This studio is shared from someone else's computer for a short preview: that computer makes the song, and what you record is saved there too. Download it to keep it. Your changes stay in this browser.";
  }
  applyPublic(s);
  $("helpSong").textContent = s.title;
  renderLineage(s.generation || 0);
  $("singNote").textContent = s.sing.available ? "" : s.sing.why;
  $("sing").disabled = !s.sing.available;
  $("toFinishLabel").textContent = s.sing.available ? "Sing or record" : "Record it";
  $("day").min = -s.days;
  $("day").max = s.days;
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
  api("/api/timeline").then((tl) => { state.timeline = tl; renderTimeline(); scroll(); }).catch(() => {
    $("timeline").replaceChildren(h("p", { class: "hint" }, "The timeline couldn't be drawn."));
  });
  if (hash.compare !== undefined) loadCompare();
  // the song is on the page: help.js may show a first visit around it
  if (typeof CustomEvent === "function") document.dispatchEvent?.(new CustomEvent("studio:ready", { detail: { hash, shared: !!s.shared } }));
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

$("hearAll").addEventListener("click", () => listen("you", null));
$("roll").addEventListener("click", () => setEdit("roll", (state.edits.roll || 0) + 1));
$("record").addEventListener("click", record);
$("recordNow").addEventListener("click", record);
$("toFinish").addEventListener("click", () => {
  // what singing and recording are, and the button that does it: opened, not started, from the top
  const panel = $("finishPanel");
  panel.open = true;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
});
$("sing").addEventListener("click", sing);
$("day").addEventListener("input", (ev) => {
  const offset = Number(ev.target.value);
  setDay(offset, "day");
});
$("day").addEventListener("change", () => { state.historyGroup = null; });
for (const b of document.querySelectorAll("[data-step]")) {
  b.addEventListener("click", () => {
    const step = Number(b.dataset.step);
    const now = state.view ? state.view.offset : 0;
    setDay(step === 0 ? 0 : Math.max(-state.start.days, Math.min(state.start.days, now + step)));
  });
}
$("makeUp").addEventListener("submit", (ev) => {
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
