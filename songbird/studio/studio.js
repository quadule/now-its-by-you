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

function storeKey() {
  return state.start ? `songbird-studio|${state.start.title}|${state.start.from}|${state.start.machine.label}` : null;
}
function save() {
  // only ever after a person's own change (edits that came in the page's address are never saved on their
  // own); the day and chance drawn again aren't kept, so tomorrow opens on tomorrow
  const kept = Object.fromEntries(Object.entries(state.edits).filter(([p]) => p !== "date" && p !== "roll"));
  try { localStorage.setItem(storeKey(), JSON.stringify(kept)); } catch (e) { /* storage may be off */ }
}
function restore() {
  try { return JSON.parse(localStorage.getItem(storeKey()) || "{}") || {}; } catch (e) { return {}; }
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

function setEdit(path, value) {
  if (value === null || value === undefined) delete state.edits[path];
  else state.edits[path] = value;
  save();
  refresh();
}

function clearEdits(paths) {
  for (const p of paths) delete state.edits[p];
  save();
  refresh();
}

let refreshTimer = null;
function refreshSoon(delay = 160) {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refresh, delay);
}

async function refresh() {
  const asked = JSON.stringify(state.edits);
  state.busy++;
  try {
    const view = await api("/api/song", { edits: state.edits });
    if (asked !== JSON.stringify(state.edits)) return; // a newer edit is on its way
    state.view = view;
    state.options = null;
    if (state.choose) await loadOptions(state.choose.block, state.choose.index, true);
    render();
    loadCompare();
  } catch (e) {
    if (!state.view) $("which").textContent = `The studio couldn't make your version of the song: ${e.message}`;
    toast(e.message);
  } finally {
    state.busy--;
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
        state.edits = keep; save(); refresh();
      } }, "undo all"),
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
  box.replaceChildren();
  const drawn = v.words.some((w) => w.sung && w.how !== "the song's own words");
  $("wordsAside").textContent = drawn ? "as they'll be sung; change any sung part" : "";
  for (const w of v.words) {
    const ready = v.listen.ready.includes(v.listen.sections[w.index]);
    const play = h("button", { class: `play${ready ? " ready" : ""}`, type: "button", "aria-label": `Play ${w.label}`,
      title: ready ? "ready to play" : "play (it will be made first)", onclick: () => listen("you", w.index) }, playIcon());
    const meta = h("span", { class: "sec-meta" });
    if (w.sung) {
      if (w.id && w.block === "verse") meta.append(h("span", {}, w.id));
      for (const t of w.tags || []) meta.append(h("span", { class: "tag rule" }, t));
      meta.append(w.mine ? tag("you", w.how) : tag(w.how === "drawn by chance" ? "chance" : "song", w.how));
    }
    const tools = h("span", { class: "sec-tools" }, play);
    const key = `${w.block}.${w.nth}`;
    if (w.sung && w.changeable) {
      const openNow = state.choose && state.choose.key === key;
      tools.prepend(h("button", { class: "link small", type: "button", "aria-expanded": openNow ? "true" : "false",
        onclick: () => toggleChooser(w) }, openNow ? "close" : "change"));
      if (w.mine) tools.prepend(h("button", { class: "link small", type: "button", onclick: () => undoWords(w) }, "undo"));
    }
    const sec = h("div", { class: `sec${w.sung ? "" : " instrumental"}${w.mine ? " mine" : ""}`, id: `sec-${w.index}` },
      h("div", { class: "sec-head" }, h("span", { class: "sec-name" }, w.label), meta, tools),
      lines(w.lines));
    if (state.choose && state.choose.key === key && state.options) sec.append(chooser(w, state.options));
    box.append(sec);
  }
}

function undoWords(w) {
  const paths = [w.path];
  if (w.block === "refrain") paths.push("words.refrain");
  if (w.block === "bridge" && w.nth === 0) paths.push("words.bridge");
  clearEdits(paths);
}

async function toggleChooser(w) {
  const key = `${w.block}.${w.nth}`;
  if (state.choose && state.choose.key === key) {
    state.choose = null;
    state.options = null;
    renderWords();
    return;
  }
  state.choose = { key, block: w.block, index: w.nth };
  await loadOptions(w.block, w.nth);
  renderWords();
  const el = $(`sec-${w.index}`);
  if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

async function loadOptions(block, index, quiet) {
  try {
    state.options = await api("/api/options", { edits: state.edits, block, index });
  } catch (e) {
    state.options = null;
    if (!quiet) toast(e.message);
  }
}

function chooser(w, o) {
  const box = h("div", { class: "chooser" });
  for (const f of o.fixed || []) box.append(h("p", { class: "fixed" }, `${capital(f.what)}: ${f.sung}. `, h("span", { class: "hint" }, `Kept by the song's rule: ${f.why}.`)));
  const allowed = o.choices.filter((c) => c.allowed);
  const refused = o.choices.filter((c) => !c.allowed);
  if (o.choices.length) {
    const what = { verse: "Choose the verse", refrain: "Choose this refrain's couplet", bridge: "Choose the second stanza", tag: "Choose the tag's syllable" }[o.block];
    box.append(h("h3", {}, what));
    if (o.block === "tag") {
      box.append(h("div", { class: "chips" }, o.choices.map((c) => h("button", {
        class: `chip${c.id === o.sung ? " on" : ""}`, type: "button", "aria-pressed": c.id === o.sung ? "true" : "false",
        onclick: () => setEdit(o.path, c.id) }, c.id))));
    } else {
      box.append(h("div", { class: "choices", role: "list" }, allowed.map((c) => {
        const first = (c.lines[0] || c.id).replace(/\*/g, "");
        const bits = [c.mood, c.era, c.rare ? "rare" : null, c.variant ? "rhymes its own way" : null].filter(Boolean).join(" · ");
        const trade = c.trades !== null && c.trades !== undefined ? `trades places with refrain ${c.trades + 1}` : "";
        return h("button", { class: `choice${c.id === o.sung ? " sung" : ""}`, type: "button", role: "listitem",
          title: c.lines.join("\n").replace(/\*/g, ""),
          onclick: () => setEdit(o.path, o.block === "verse" ? { id: c.id } : c.id) },
          h("span", { class: "first" }, first),
          h("span", { class: "meta" }, [c.id, bits, trade].filter(Boolean).join(" · ")));
      })));
    }
    if (refused.length) {
      const list = h("ul", {}, refused.map((c) => {
        const offers = [];
        if (c.reorder) offers.push(h("button", { class: "link small", type: "button", onclick: () => applyOrder(c.reorder) },
          `sing it as verse ${c.reorder.indexOf(c.id) + 1} instead`));
        else if (c.elsewhere && c.elsewhere.length) offers.push(h("button", { class: "link small", type: "button",
          onclick: () => setEdit(`words.verse.${c.elsewhere[0]}`, { id: c.id }) }, `it could be verse ${c.elsewhere[0] + 1} instead`));
        return h("li", {}, h("b", {}, (c.lines[0] || c.id).replace(/\*/g, "")), ` (${c.id}): ${c.why}. `, ...offers);
      }));
      box.append(h("details", { class: "refused" }, h("summary", {}, `${refused.length} that can't go here, and why`), list));
    }
  }
  for (const slot of o.words || []) {
    box.append(h("div", { class: "slot" }, h("div", { class: "label" }, slot.slot),
      h("div", { class: "chips" }, slot.options.map((opt) => h("button", {
        class: `chip${opt === slot.sung ? " on" : ""}`, type: "button", "aria-pressed": opt === slot.sung ? "true" : "false",
        onclick: () => chooseSlot(o, slot.slot, opt) }, (slot.labels && slot.labels[opt]) || opt)))));
  }
  if ((o.words || []).length && o.block !== "verse") box.append(h("p", { class: "hint" }, "These words are chosen once for the whole song."));
  return box;
}

function chooseSlot(o, slot, value) {
  if (o.block === "verse") {
    const current = state.edits[o.path];
    const id = current && current.id ? current.id : o.sung;
    const slots = Object.assign({}, current && current.slots ? current.slots : {}, { [slot]: value });
    setEdit(o.path, { id, slots });
  } else {
    const path = o.slots_path;
    setEdit(path, Object.assign({}, state.edits[path] || {}, { [slot]: value }));
  }
}

function applyOrder(order) {
  order.forEach((id, i) => { state.edits[`words.verse.${i}`] = { id }; });
  save();
  refresh();
}

function capital(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

// ------------------------------------------------------------------ the cards

function renderCards() {
  const box = $("cards");
  const openNow = new Set([...box.querySelectorAll("details.change[open]")].map((d) => d.dataset.card));
  box.replaceChildren();
  for (const c of state.view.cards) {
    const head = h("div", { class: "card-head" }, h("h3", {}, c.title));
    if (c.mine && c.paths && c.paths.length) head.append(h("button", { class: "link small undo", type: "button", onclick: () => clearEdits(allPaths(c)) }, "undo"));
    const card = h("section", { class: `card${c.mine ? " mine" : ""}`, "aria-label": c.title }, head,
      h("div", { class: "value" }, c.value),
      c.today ? h("div", { class: "today" }, c.today) : null,
      c.detail ? h("div", { class: "detail" }, c.detail) : null,
      c.lines ? h("ul", { class: "machine-lines" }, c.lines.map((l) => h("li", {}, l))) : null,
      reasonsOf(c),
      (c.problems || []).map((p) => h("p", { class: "problem" }, `Couldn't keep your ${describePath(p.path).replace(/^your /, "")}: ${p.why}.`)));
    const controls = editor(c);
    if (controls) {
      const d = h("details", { class: "change", "data-card": c.id }, h("summary", {}, c.id === "words" ? "keep or choose" : "change"), controls);
      if (openNow.has(c.id) || state.open[c.id]) d.open = true;
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
  return h("div", { class: "control" }, h("label", {}, label), h("div", { class: "chips" }, options.map((o) => {
    const refused = why && why[o];
    return h("button", { class: `chip${o === current ? " on" : ""}`, type: "button", disabled: refused ? true : null,
      title: refused || (names && names.title && names.title[o]) || null, "aria-pressed": o === current ? "true" : "false",
      onclick: () => onpick(o) }, names && names.text ? names.text[o] || o : String(o));
  })));
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
        h("p", { class: "hint" }, "A minor mode leans the words darker, as the machine's own would."));
    }
    case "tempo":
      return slider("Beats a minute", "tempo", c.tempo, b.tempo, (x) => `${Number(x).toFixed(0)}`, ["slower", "quicker"]);
    case "shape": {
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
          disabled: flip && !flip.allowed ? true : null, title: flip && !flip.allowed ? flip.why : null,
          onclick: () => setEdit(`form.${part}`, !on) }, s.parts[part]));
      }
      box.append(h("div", { class: "control" }, h("label", {}, "Parts of the shape"), toggles));
      return box;
    }
    case "band": {
      const band = c.band;
      const players = h("div", { class: "players" }, b["band.players"].options.map((n) => {
        const box = h("input", { type: "checkbox" });
        box.checked = band[n] > 0.02;
        box.addEventListener("change", () => setEdit(`band.${n}`, box.checked ? null : 0));
        return h("label", {}, box, c.players[n] || n);
      }));
      return h("div", {},
        chips("How the band plays", b["band.pattern"].options, band.pattern, (x) => setEdit("band.pattern", x), { text: s.patterns }),
        chips("Who leads where nobody sings", b["band.lead"].options, band.lead, (x) => setEdit("band.lead", x), { text: c.players }),
        slider("How busy", "band.density", band.density, b["band.density"], (x) => `${Math.round(x * 100)}%`, ["sparse", "busy"]),
        slider("How bright", "band.brightness", band.brightness, b["band.brightness"], (x) => `${Math.round(x * 100)}%`, ["dark and soft", "bright"]),
        h("div", { class: "control" }, h("label", {}, "Who plays"), players),
        h("p", { class: "hint" }, "With nobody playing, the voice sings alone."));
    }
    case "mix": {
      const m = c.mix;
      return h("div", {},
        slider("How much of the room", "mix.space", m.space, b["mix.space"], (x) => `${Math.round(x * 100)}%`, ["dry", "roomy"]),
        slider("How wide", "mix.width", m.width, b["mix.width"], (x) => `${Math.round(x * 100)}%`, ["narrow", "wide"]),
        slider("The voice over the band", "mix.forward", m.forward, b["mix.forward"], (x) => `${Number(x).toFixed(1)} dB`, ["among it", "well over it"]),
        slider("How close the singer is", "mix.intimacy", m.intimacy, b["mix.intimacy"], (x) => `${Math.round(x * 100)}%`, ["further back", "at your ear"]),
        h("p", { class: "hint" }, "Judge the voice against the band on the whole song: a part heard alone is levelled for listening."));
    }
    case "singer": {
      const box = h("div", {}, h("p", { class: "hint" }, "The singer is your machine's own voice, the same in every song it sings. What you can give it is your way of singing."));
      const phrasings = s.phrasings || [];
      if (phrasings.length) {
        const select = h("select", { "aria-label": "Whose way it is sung" },
          h("option", { value: "" }, "the song's own way"),
          phrasings.map((p) => h("option", { value: p.id }, `${p.label}'s way${p.detail ? ` (${p.detail})` : ""}`)));
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
        h("p", { class: "hint" }, "Choose any verse, couplet or word in the words themselves. Or hold every word as it is now, so that moving through time and rolling chance change only the music."),
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
    const r = await api("/api/keep-words", { edits: state.edits });
    state.edits = r.edits;
    save();
    toast("The words are held as they are.");
    refresh();
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
  const lanes = [["Key", "key"], ["Tempo", "tempo"], ["Verses", "verses"], ["Band", "pattern"], ["Lead", "lead"], ["Words", "lean"]];
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
  return String(value);
}

function setDay(offset) {
  const today = state.start.day;
  if (!offset) delete state.edits.date;
  else {
    const d = new Date(`${today}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() + offset);
    state.edits.date = d.toISOString().slice(0, 10);
  }
  save();
  $("day").value = offset;
  renderTimeline();
  refreshSoon(120);
}

// ------------------------------------------------------------------ other machines

let compareTimer = null;
function loadCompare() {
  clearTimeout(compareTimer);
  compareTimer = setTimeout(async () => {
    try {
      const date = state.edits.date ? { date: state.edits.date } : {};
      state.compare = await api("/api/compare", { edits: Object.assign({}, state.edits, date), names: state.names });
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
  $("compare").replaceChildren(table, h("p", { class: "hint" }, "Yours includes the choices you made; theirs are their own. Differences are marked."));
}

// ------------------------------------------------------------------ listening

const audio = $("audio");

async function listen(who, section) {
  if (state.poll && state.playing && state.playing.job && state.playing.job.state === "queued") {
    api("/api/cancel", { job: state.playing.job.id }).catch(() => {});
  }
  clearTimeout(state.poll);
  audio.pause();
  const label = section === null ? "The whole song" : state.view.words[section].label;
  state.playing = { who, section, label, job: null };
  showPlayer(label, "getting it ready…", 0, true);
  try {
    const job = await api("/api/listen", { edits: state.edits, who, section });
    await follow(job, state.playing);
  } catch (e) {
    showPlayer(label, e.message, 0, false);
  }
}

async function follow(job, playing) {
  if (playing !== state.playing) return;
  playing.job = job;
  const title = job.label || playing.label;
  if (job.state === "done") {
    play(job.url, title, playing.section === null ? "the whole song, as it would be recorded" : "a preview of this part");
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
  const where = job.state === "queued" ? "waiting its turn" : `${job.stage || "making it"}…`;
  showPlayer(title, `${where} ${Math.round((job.progress || 0) * 100)}%${slow}`, job.progress || 0, true);
  state.poll = setTimeout(async () => {
    try { await follow(await api(`/api/job/${job.id}`), playing); } catch (e) { showPlayer(title, e.message, 0, false); }
  }, 450);
}

function refreshReady(key) {
  if (key && state.view && !state.view.listen.ready.includes(key)) {
    state.view.listen.ready.push(key);
    renderWords();
  }
}

function play(url, title, sub) {
  audio.src = url;
  audio.play().catch(() => {});
  showPlayer(title, sub || "", 0, false);
  $("playPause").disabled = false;
}

function showPlayer(title, sub, progress, making) {
  $("nowTitle").textContent = title;
  $("nowSub").textContent = sub;
  $("bar").classList.toggle("making", !!making);
  $("barFill").style.width = `${Math.round((progress || 0) * 100)}%`;
}

audio.addEventListener("timeupdate", () => {
  if (!audio.duration) return;
  $("barFill").style.width = `${(audio.currentTime / audio.duration) * 100}%`;
  $("nowTime").textContent = `${fmtTime(audio.currentTime)} / ${fmtTime(audio.duration)}`;
});
audio.addEventListener("play", () => { $("playShape").setAttribute("d", PAUSE); $("playPause").setAttribute("aria-label", "Pause"); });
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

async function record() {
  const saved = $("saved");
  if (state.recording) return;
  state.recording = true;
  for (const id of ["record", "recordNow"]) $(id).disabled = true;
  saved.replaceChildren(h("p", {}, "Recording…"));
  $("recordPanel").scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    let job = await api("/api/record", { edits: state.edits });
    while (job.state === "queued" || job.state === "running") {
      saved.replaceChildren(h("p", {}, `Recording: ${job.state === "queued" ? "waiting its turn" : job.stage || "making it"}… ${Math.round((job.progress || 0) * 100)}%`),
        h("div", { class: "bar making" }, h("div", { style: null })));
      saved.querySelector(".bar > div").style.width = `${Math.round((job.progress || 0) * 100)}%`;
      await new Promise((r) => setTimeout(r, 600));
      job = await api(`/api/job/${job.id}`);
    }
    if (job.state === "failed") throw new Error(job.error);
    const r = job.result.recorded;
    saved.replaceChildren(
      h("p", {}, "Saved ", h("code", {}, r.flac), ` (${fmtTime(r.duration)}): the song, the program that sang it and its record, in one file.`),
      h("p", {}, r.yours ? `${r.yours} choice${r.yours === 1 ? " is" : "s are"} marked as yours in it (what you chose, never who you are).` : "Every choice in it is the program's."),
      h("p", { class: "hint" }, "To make the next version from this one: ", h("code", {}, r.next)),
      h("button", { class: "btn", type: "button", onclick: () => play(job.url, "The recording", r.flac) }, "Play the recording"));
  } catch (e) {
    saved.replaceChildren(h("p", { class: "problem" }, `Couldn't record it: ${e.message}`));
  } finally {
    state.recording = false;
    for (const id of ["record", "recordNow"]) $(id).disabled = false;
  }
}

// ------------------------------------------------------------------ putting it together

function render() {
  renderHeader();
  renderWords();
  renderCards();
  renderTimeline();
}

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
    try { state.edits = JSON.parse(hash.e) || {}; } catch (e) { /* ignore */ }
  }
  if (hash.day) setDayQuiet(Number(hash.day));
  for (const id of (hash.open || "").split(",").filter(Boolean)) state.open[id] = true;
  $("packetNote").textContent = s.packet;
  $("singNote").textContent = s.sing.available ? "" : s.sing.why;
  $("sing").disabled = !s.sing.available;
  $("day").min = -s.days;
  $("day").max = s.days;
  await refresh();
  if (hash.choose) {
    const [block, nth] = hash.choose.split(".");
    const w = state.view.words.find((x) => x.block === block && String(x.nth) === nth);
    if (w) await toggleChooser(w);
    if (hash.refused !== undefined) for (const d of document.querySelectorAll(".chooser details.refused")) d.open = true;
  }
  const scroll = () => { const el = hash.scroll && $(hash.scroll); if (el) el.scrollIntoView({ block: "start" }); };
  scroll();
  api("/api/timeline").then((tl) => { state.timeline = tl; renderTimeline(); scroll(); }).catch(() => {
    $("timeline").replaceChildren(h("p", { class: "hint" }, "The timeline couldn't be drawn."));
  });
  if (hash.compare !== undefined) loadCompare();
}

function setDayQuiet(offset) {
  if (!offset) { delete state.edits.date; return; }
  const d = new Date(`${state.start.day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + offset);
  state.edits.date = d.toISOString().slice(0, 10);
}

$("hearAll").addEventListener("click", () => listen("you", null));
$("roll").addEventListener("click", () => setEdit("roll", (state.edits.roll || 0) + 1));
$("record").addEventListener("click", record);
$("recordNow").addEventListener("click", record);
$("sing").addEventListener("click", sing);
$("day").addEventListener("input", (ev) => {
  const offset = Number(ev.target.value);
  setDayQuiet(offset);
  save();
  if (state.timeline) renderTimeline();
  refreshSoon(180);
});
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
    if (JSON.stringify(phrasings) !== JSON.stringify(state.start.phrasings)) {
      state.start.phrasings = phrasings;
      renderCards();
    }
  } catch (e) { /* the studio may have stopped */ }
});

main();
