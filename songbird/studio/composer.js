/* A small, portable score editor. No samples, libraries, or network requests: the
 * sketch plays the tune, its chords and a bass on the browser's oscillators, at once;
 * the song's own renderer sings it. */
(() => {
  "use strict";

  const MODES = {
    ionian: [0, 2, 4, 5, 7, 9, 11], dorian: [0, 2, 3, 5, 7, 9, 10],
    phrygian: [0, 1, 3, 5, 7, 8, 10], lydian: [0, 2, 4, 6, 7, 9, 11],
    mixolydian: [0, 2, 4, 5, 7, 9, 10], aeolian: [0, 2, 3, 5, 7, 8, 10],
    locrian: [0, 1, 3, 5, 6, 8, 10],
  };
  // the rolls' zoom: the whole section in the width, or a scale an eighth note's syllable can be read at (model.js rollUnit)
  const ZOOMS = [["fit", "Fit"], [1, "100%"], [1.5, "150%"], [2, "200%"], [3, "300%"]];
  const state = {
    view: null, section: -1, phrase: 0, snap: 0.25, zoom: 1, player: "voice",
    loop: false, metronome: false, scope: "phrase", drag: null, chords: true, bass: true, chord: null,
    chosen: new Set(), cursor: null, // notes selected with state.note, and where a paste goes: { phrase, beat }
    where: { tune: null, chords: null }, // one place or everywhere: "line", "place" or "last" (null: as the line has it)
    // a line whose count of syllables changed, waiting for its words (docs/notes/OWN-COUNT-LINES.md):
    // { path: its line. path, notes, was: the line's notes before }
    draft: null,
    context: null, bus: null, playback: null, nodes: new Set(), frame: null,
  };
  const bridge = () => window.StudioBridge || {};
  const root = () => document.getElementById("studio-composer");
  // On the score (index.html) the editor is only the notes of one section, under the Arrange grid: the transport is
  // the page's, the sections are its regions, and a note's or a chord's card is a state of its inspector (score.js,
  // told through page()).
  const page = () => window.SongbirdScore;
  const notesMode = () => root()?.dataset?.mode === "notes";
  const composition = () => state.view && state.view.composition;
  const sections = () => composition()?.sections || [];
  const section = () => sections()[state.section];
  const phrase = () => section()?.phrases?.[state.phrase];
  const note = () => phrase()?.notes?.[state.note];
  // a line the melody roll draws: one with notes, or a sung line with none yet (a blank line, to draw into)
  const drawable = (p) => !!(p?.notes?.length || p?.own_path);
  const firstSung = () => {
    const ps = section()?.phrases || [], k = ps.findIndex((p) => p.notes?.length);
    return Math.max(0, k >= 0 ? k : ps.findIndex(drawable));
  };
  const drafts = new Map();
  let clipboard = null, phraseClipboard = null;
  // the selected note; choosing one note lets go of any others chosen with it (pick() keeps them)
  let selectedNote = null;
  Object.defineProperty(state, "note", { get: () => selectedNote, set: (value) => { selectedNote = value; state.chosen = new Set(); } });
  Object.defineProperty(state, "draft", {
    get: () => drafts.get(phrase()?.own_path) || null,
    set: (value) => { const key = value?.path || phrase()?.own_path; if (value) drafts.set(key, value); else drafts.delete(key); },
  });
  const round = (n) => Math.round(n * 10000) / 10000;
  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const fmt = (n) => Number.isInteger(n) ? String(n) : String(round(n));
  const beatLabel = (n) => n < 0 ? `pickup ${fmt(-n)}` : fmt(n + 1);
  const displayWords = (value) => String(value || "").replace(/\*/g, "").replace(/\{[^{}]*\}/g, "");  // no focus marks, no says
  const announce = (message) => {
    const status = document.getElementById("sbc-status");
    if (status) status.textContent = message;
  };
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === false || value === null || value === undefined) continue;
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "style") Object.assign(node.style, value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat(Infinity)) {
      if (child !== null && child !== undefined && child !== false) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }
  function svg(tag, attrs, ...children) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
    for (const child of children.flat()) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  function button(text, action, attrs = {}) {
    return el("button", { type: "button", class: "sbc-button", "data-composer-action": text || undefined, onclick: action, ...attrs }, text);
  }
  function select(label, value, options, action, attrs = {}) {
    const input = el("select", { "aria-label": label, onchange: (event) => action(event.target.value), ...attrs },
      options.map(([id, text]) => el("option", { value: id, selected: String(id) === String(value) }, text)));
    return el("label", { class: "sbc-field" }, el("span", {}, label), input);
  }
  function number(label, value, min, max, step, action, attrs = {}) {
    const input = el("input", { type: "number", value: fmt(value), min, max, step,
      "aria-label": label, onchange: (event) => {
        const next = Number(event.target.value);
        if (event.target.value.trim() === "" || !Number.isFinite(next)) { event.target.value = fmt(value); return; }
        action(next);
      }, ...attrs });
    return el("label", { class: "sbc-field" }, el("span", {}, label), input);
  }
  function checkbox(label, checked, action) {
    return el("label", { class: "sbc-check" }, el("input", { type: "checkbox", checked, id: `sbc-option-${label.toLowerCase()}`,
      onchange: (event) => action(event.target.checked) }), label);
  }

  function bounds(p = phrase()) {
    return { min_degree: -6, max_degree: 15, min_onset: -(p?.pickup_beats || 0),
      max_end: p?.duration_beats || 4, min_duration: composition()?.grid || 0.25,
      grid: composition()?.grid || 0.25, ...(p?.bounds || {}) };
  }
  function scaleOffset(degree) {
    const mode = composition()?.mode || state.view?.choices?.mode || "ionian";
    const scale = composition()?.scale || MODES[mode] || MODES.ionian;
    return Math.floor((degree - 1) / 7) * 12 + scale[((degree - 1) % 7 + 7) % 7];
  }
  function pitchFor(n, degree = n.degree) {
    return (n.pitch ?? ((composition()?.tonic || 60) + scaleOffset(n.degree))) + scaleOffset(degree) - scaleOffset(n.degree);
  }
  // ---- the roll's rows are semitones above the tonic; a note is kept as its degree and half step (alter)
  const M = () => window.SongbirdModel;
  const scale = () => composition()?.scale || MODES[composition()?.mode || state.view?.choices?.mode] || MODES.ionian;
  const semiOf = (n) => (n.pitch ?? (composition()?.tonic || 60) + scaleOffset(n.degree) + (n.alter || 0)) - (composition()?.tonic || 60);
  // only a line of its own holds a half step (check_phrase free), and a melisma's notes are the scale's
  const chromatic = (p, n) => !!p?.own_path && !n?.slur;
  const sign = (alter) => (alter > 0 ? "♯" : alter < 0 ? "♭" : "");
  function rowsMoved(p, n, rows) {
    const b = bounds(p);
    return M().moveRows(n, rows, { scale: scale(), chromatic: chromatic(p, n), lo: b.min_degree, hi: b.max_degree });
  }
  function pitchName(pitch) {  // as the key writes it (the server's spelling: G♯4 in C♯ minor, not A♭4)
    const names = composition()?.names || ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
    const p = Math.round(pitch), pc = ((p % 12) + 12) % 12, name = names[pc];
    const octave = Math.floor(p / 12) - 1 + (name[0] === "B" && pc === 0 ? -1 : name[0] === "C" && pc === 11 ? 1 : 0);  // B♯3, C♭5
    return `${name}${octave}`;
  }
  function degreeName(degree) {
    const octave = Math.floor((degree - 1) / 7);
    return `${((degree - 1) % 7 + 7) % 7 + 1}${octave > 0 ? "′".repeat(octave) : octave < 0 ? "₋".repeat(-octave) : ""}`;
  }
  function noteTitle(n, index, p = phrase()) {
    const name = n.slur ? `${displayWords(n.word) || "the syllable before"}, held on` : displayWords(n.syllable) || `Note ${index + 1}`;
    return `${name}, ${pitchName(pitchFor(n))}, scale degree ${sign(n.alter)}${n.degree}, beat ${beatLabel(n.onset)}, ${fmt(n.duration)} beats${index === p.notes.length - 1 ? ", phrase ending" : ""}`;
  }
  function selectedSection(index) {
    stop(); state.section = clamp(index, 0, sections().length - 1); state.phrase = firstSung(); state.note = null; state.chord = null; state.cursor = null;
    state.where = { tune: null, chords: null }; feel(); paint(); told();
  }
  function selectedPhrase(index) {
    stop(); state.phrase = index; state.note = null; state.chord = null; state.where = { tune: null, chords: null }; state.reveal = true; paint(); told();
  }
  function told() { if (notesMode()) page()?.composerSelected?.(state.chord ? "chord" : state.note !== null ? "note" : null); }

  // ---- one place, or everywhere (docs/STUDIO.md, "Looser harmony and melody"): a line's tune or chords changed
  // wherever it's sung (tune.<line>), only at this place of the form (tune.<section>:<n>.<line>), or at the last
  // time its section comes, however many there are (tune.<section>:last.<line>). Starts on where the place's own
  // come from; the choice is the person's, never made for them.
  function where(kind, p = phrase()) {
    const chosen = state.where[kind] || p?.[`${kind}_scope`]?.from || (p?.place ? "place" : "line");
    return chosen === "last" && !p?.place_last ? "place" : chosen === "place" && !p?.place ? "line" : chosen;
  }
  function scopedPath(kind, p = phrase()) {
    const scope = where(kind, p), line = kind === "tune" ? (p.path || `tune.${p.id}`) : (p.chords_path || `chords.${p.id}`);
    return scope === "place" ? `${kind}.${p.place}` : scope === "last" ? `${kind}.${p.place_last}` : line;
  }
  function ownHere(kind, p) { return ["place", "last"].includes(p?.[`${kind}_scope`]?.from); }
  function held(kind, p) { // whether the chosen scope has a change of the person's to restore
    const c = composition(), key = scopedPath(kind, p).slice(kind.length + 1);
    if (where(kind, p) !== "line") return Boolean(c?.edited_places?.[kind]?.includes(key));
    const lines = kind === "tune" ? c?.edited_phrases : c?.edited_chords;
    return lines ? lines.includes(p.id) : kind === "tune" || Boolean(p.chords_edited);
  }
  function scopeChoice(kind) {
    const p = phrase(), s = section();
    if (!p?.place || (kind === "tune" && (p.own || state.draft))) return null;
    const count = p.appearances || 1, name = s.name.replace("bridge2", "second bridge");
    const options = [["line", count > 1 ? `Everywhere it's sung (${count} places)` : "Everywhere it's sung"],
      ["place", `Only here (${s.label})`]];
    if (p.place_last) options.push(["last", `The last ${name}, however many there are`]);
    const both = p[`${kind}_scope`]?.both;
    return el("div", { class: "sbc-scope" },
      select(kind === "tune" ? "Change the tune" : "Change the chords", where(kind, p), options,
        (value) => { state.where[kind] = value; paint(); }, { id: `sbc-where-${kind}` }),
      both ? el("span", { class: "sbc-muted" }, `This ${name} has its own and the last ${name} has too: its own wins here.`) : null);
  }
  function sharesScope(kind, p, other) {
    // which of the phrases the page shows sing what this edit changes (for drawing it at once)
    if (other === p) return true;
    if (other.id !== p.id || where(kind, p) !== "line") return false;
    return !ownHere(kind, other);
  }
  // an edit, with what an undo of it says ("Undid: Move notes")
  function commit(path, value, label) {
    stop();
    if (value === null && bridge().releaseEdit) bridge().releaseEdit(path, label); // an inherited choice released, explicitly
    else if (bridge().setEdit) bridge().setEdit(path, value, label);
  }
  function serializeNotes(notes, own = false) {
    // Keep untouched expressive and compound-meter timing exact. A third of a
    // beat rounded for display can otherwise become a false syllable overlap.
    // A line of its own carries each note's half step (a tune line's notes keep the line's own by place).
    return notes.map((n) => ({ degree: n.degree, onset: n.onset, duration: n.duration, ...(n.slur ? { slur: true } : {}),
      ...(own && n.alter && !n.slur ? { alter: n.alter } : {}) }));
  }
  // ---- a melisma (docs/STUDIO.md, "A freer melody"): a note slurred on from the one before sings the same
  // syllable, starting where it ends. Moving a slurred note's start moves the boundary between the two; any other
  // change keeps each slurred note starting where the one before it now ends, and ending where it did.
  function keepSlurs(notes, moved, p = phrase()) {
    for (let i = 1; i < notes.length; i++) {
      if (!notes[i].slur) continue;
      const before = notes[i - 1], was = p.notes[i] || notes[i], end = was.onset + was.duration;
      if (i === moved) before.duration = notes[i].onset - before.onset;
      else notes[i].onset = before.onset + before.duration;
      notes[i].duration = end - notes[i].onset;
    }
    return notes;
  }
  function syllableOf(p, index) { return p.notes.slice(0, index + 1).filter((n) => !n.slur).length - 1; }
  function splitNote() {
    const p = phrase(), i = state.note, n = note(), b = bounds(p);
    if (!p || n === undefined || n === null) return;
    const k = syllableOf(p, i), group = p.notes.filter((x, j) => syllableOf(p, j) === k).length;
    if (group >= (b.melisma || 4)) { bridge().toast?.(`A syllable is sung over ${b.melisma || 4} notes at most.`); return; }
    if (n.duration < 2 * b.min_duration - 1e-9) { bridge().toast?.("This note is too short to split: each half needs a quarter beat."); return; }
    // in two on the note's own grid (halves of a third stay thirds), each at least a quarter beat
    const unit = Math.abs(n.duration * 3 - Math.round(n.duration * 3)) < 1e-6 && Math.abs(n.duration * 4 - Math.round(n.duration * 4)) > 1e-6 ? 1 / 3 : b.grid;
    const half = clamp(Math.round(n.duration / 2 / unit) * unit, b.min_duration, n.duration - b.min_duration);
    const notes = p.notes.map((x) => ({ ...x }));
    notes.splice(i, 1, { ...n, duration: half }, { ...n, onset: n.onset + half, duration: n.duration - half, slur: true, syllable: "", alter: 0, pitch: n.pitch - (n.alter || 0) });
    state.note = i + 1;
    commitNotes(notes, "Note split: the second half is sung on the same syllable. Move it to make a melisma.", "Split a note");
  }
  // ---- a line with its own count (docs/notes/OWN-COUNT-LINES.md): a note split into a new syllable, or a syllable
  // merged into the one before; the line's words are written for the new count before it is sung
  function newSyllable() {
    const p = phrase(), i = state.note, n = note(), b = bounds(p);
    if (!p?.own_path || n === undefined || n === null) return;
    if (n.duration < 2 * b.min_duration - 1e-9) { bridge().toast?.("This note is too short to split: each half needs a quarter beat."); return; }
    const unit = Math.abs(n.duration * 3 - Math.round(n.duration * 3)) < 1e-6 && Math.abs(n.duration * 4 - Math.round(n.duration * 4)) > 1e-6 ? 1 / 3 : b.grid;
    const half = clamp(Math.round(n.duration / 2 / unit) * unit, b.min_duration, n.duration - b.min_duration);
    const notes = p.notes.map((x) => ({ ...x }));
    notes.splice(i, 1, { ...n, duration: half }, { ...n, onset: n.onset + half, duration: n.duration - half, slur: false, syllable: "?", word: "", pitch: n.pitch });
    delete notes[i + 1].slur;
    state.note = i + 1;
    commitNotes(notes, "A new syllable: write the line's words for it.", "Add a syllable");
  }
  function mergeSyllable() {
    const p = phrase(), i = state.note, n = note();
    if (!p?.own_path || !n || n.slur || i === 0) return;
    const notes = p.notes.map((x) => ({ ...x }));
    notes[i - 1].duration = n.onset + n.duration - notes[i - 1].onset;  // the note before holds on through its time
    notes.splice(i, 1);  // (any notes slurred onto it go on from the one before)
    state.note = i - 1;
    commitNotes(notes, "Merged into the syllable before: write the line's words for one fewer.", "Merge syllables");
  }
  const sylls = (text) => window.SongbirdAuthor?.say?.syllables ? window.SongbirdAuthor.say.syllables(text)
    : String(text || "").replace(/\{[^{}]*\}/g, "").trim().split(/[\s-]+/u).filter(Boolean).length;
  function ownCard() {
    // the line's words for its new count: one edit with its notes (line.<key>.<i>)
    const p = phrase(), d = state.draft;
    if (!p || !d || d.path !== p.own_path) return null;
    const want = d.notes.filter((n) => !n.slur).length;
    const input = el("input", { type: "text", class: "sbc-own-words", value: d.words ?? p.lyric_text ?? "", "aria-label": want ? `The line's words, ${want} syllables` : "The line's words", id: "sbc-own-words" });
    const count = el("span", { class: "sbc-muted" }, "");
    const shown = () => { const n = sylls(input.value); count.textContent = want ? `${n} / ${want} syllables` : `${n} syllables`; count.classList.toggle("is-valid", n === want); };
    input.addEventListener("input", () => { d.words = input.value; shown(); });
    shown();
    return el("div", { class: "sbc-own" },
      el("strong", {}, "Write this line"),
      el("p", { class: "sbc-muted" }, "One syllable a note; split longer words with hyphens (car-ry)."),
      input, count, d.error ? el("p", { role: "alert", class: "problem" }, d.error) : null,
      el("div", { class: "sbc-button-group" },
        want ? button("Use these words", () => {
          if (sylls(input.value) !== want) { bridge().toast?.(`This line needs ${want} syllables; it has ${sylls(input.value)}.`); return; }
          d.words = input.value.trim(); applyDraft(p, d);
        }, { disabled: !!d.busy }) : null,
        button("Fit notes to words", () => {
          try {
            d.words = input.value;
            const notes = window.SongbirdModel.fitNotes({ ...p, notes: d.notes }, sylls(input.value));
            d.notes = notes.map((n) => ({ ...n, pitch: (composition()?.tonic || 60) + scaleOffset(n.degree) + (n.alter || 0), edited: true }));
            p.notes = d.notes; state.note = null; d.error = null; paint(); told();
          } catch (error) { d.words = input.value; d.error = error.message; paint(); told(); }
        }, { disabled: !!d.busy }),
        button("Cancel", () => { p.notes = d.was; state.draft = null; state.note = null; paint(); told(); }, { class: "sbc-button sbc-quiet" })));
  }
  async function applyDraft(p, d) {
    const value = { words: d.words, notes: serializeNotes(d.notes, true) }, snapshot = bridge().snapshot?.();
    if (!snapshot) { state.draft = null; commit(p.own_path, value, "Write a line"); return; }
    d.busy = true; d.error = null; paint(); told();
    try {
      const edits = { ...snapshot.edits, [p.own_path]: value };
      const response = await fetch("/api/song", { method: "POST", headers: { "Content-Type": "application/json",
        "X-Studio": document.querySelector('meta[name="studio-token"]').content }, body: JSON.stringify({ edits }) });
      const view = await response.json();
      if (!response.ok) throw new Error(view.error || "Couldn't check this line. Try again.");
      const problem = view.problems?.find((x) => x.path === p.own_path);
      if (problem) throw new Error(problem.why);
      if (drafts.get(p.own_path) !== d) return; // cancelled while pronunciation was checked
      if (bridge().snapshot().revision !== snapshot.revision) throw new Error("The song changed. Use these words again.");
      if (d.words === value.words && JSON.stringify(serializeNotes(d.notes, true)) === JSON.stringify(value.notes)) drafts.delete(p.own_path);
      bridge().replaceEdits(edits, "Write a line");
    } catch (error) { d.error = error.message; }
    finally { d.busy = false; paint(); told(); }
  }
  function writeLine() {
    const p = phrase();
    if (!p?.own_path || state.draft) return;
    state.draft = { path: p.own_path, notes: p.notes.map((n) => ({ ...n })), was: p.notes, words: p.lyric_text || "" };
    paint(); told();
  }
  // a note added at a time and pitch ({degree, alter}), as long as the snap or as drawn (length)
  function addNote(onset = null, pitch = null, drawn = null) {
    const p = phrase(), b = bounds(p);
    if (!p?.own_path) return;
    const notes = p.notes.map((n) => ({ ...n })), length = Math.max(b.min_duration, drawn ?? state.snap);
    const gaps = [b.min_onset, ...notes.map((n) => n.onset + n.duration)];
    if (onset === null) onset = gaps.find((t) => t >= (note()?.onset ?? b.min_onset) &&
      t + length <= b.max_end && !notes.some((n) => n.onset < t + length - 1e-8 && n.onset + n.duration > t + 1e-8));
    if (!Number.isFinite(onset)) { bridge().toast?.("Make room by shortening or deleting a note, then add a note in the gap."); return; }
    onset = Math.max(b.min_onset, M().onGrid(onset, state.snap));
    const next = notes.find((n) => n.onset >= onset), duration = Math.min(length, (next?.onset ?? b.max_end) - onset);
    if (duration < b.min_duration || notes.some((n) => n.onset <= onset && n.onset + n.duration > onset + 1e-8) ||
      (!next && onset > b.max_final_onset)) { bridge().toast?.("Draw in an empty space with room for a syllable."); return; }
    const degree = clamp(pitch?.degree ?? note()?.degree ?? 1, b.min_degree, b.max_degree);
    const newNote = { degree, onset, duration, syllable: "?", alter: degree === pitch?.degree ? pitch.alter || 0 : 0 };
    notes.push(newNote); notes.sort((a, z) => a.onset - z.onset); state.note = notes.indexOf(newNote);
    state.focusNote = true;  // the new note takes the keys: Delete and the arrows are its own
    commitNotes(notes, "Note added. Write the words for this line.", "Add a note");
  }
  // ---- several notes at once: the selected note (state.note) and any chosen with it (state.chosen), all in the
  // selected phrase; a move, a nudge, a transposition, a deletion or a paste of them is one edit, one undo step
  function picked() {
    const count = phrase()?.notes?.length || 0;
    if (state.note === null || state.note >= count) return [];
    return [...new Set([state.note, ...state.chosen])].filter((i) => i < count).sort((a, z) => a - z);
  }
  function pick(index, more = []) { state.note = index; state.chosen = new Set(more); }
  function toggleNote(pi, index) {  // Shift-click: a note added to the selection, or taken from it
    if (focusPhrase(pi) || state.note === null) { pick(index); paint(); told(); return; }
    const now = new Set(picked());
    if (now.has(index)) now.delete(index); else now.add(index);
    const rest = [...now];
    if (!rest.length) state.note = null; else pick(rest.includes(index) ? index : rest[0], rest);
    paint(); told();
    announce(`${rest.length} note${rest.length === 1 ? "" : "s"} selected`);
  }
  function selectAll() {
    const p = phrase();
    if (!p?.notes?.length) return;
    pick(0, p.notes.map((_, i) => i)); state.chord = null; state.focusNote = true; paint(); told();
    announce(`All ${p.notes.length} notes of phrase ${state.phrase + 1} selected`);
  }
  const several = () => picked().length > 1;
  function deleteNote() {
    const p = phrase(), i = state.note, n = note(), chosen = picked();
    if (!n) return;
    if (chosen.length < 2 && n.slur) { joinNote(); return; }
    const notes = window.SongbirdModel.deleteNotes(p.notes, chosen);
    const left = notes.filter((x) => !x.slur).length;
    if (left === p.notes.filter((x) => !x.slur).length) { pick(Math.min(i, notes.length - 1)); commitNotes(notes, "Joined into the notes before.", "Join notes"); return; }
    if (!p.own_path || left < 1) {
      bridge().toast?.(p.own_path ? "A sung line keeps at least one syllable."
        : "Choose a sung line to change how many notes it has."); return;
    }
    pick(Math.min(chosen[0], notes.length - 1));
    commitNotes(notes, chosen.length > 1 ? `${chosen.length} notes deleted; the gaps are rests.` : "Note deleted; the gap is a rest.",
      chosen.length > 1 ? "Delete notes" : "Delete a note");
  }
  // the clipboard: the selected notes, or the whole phrase when none (or all) are selected. A whole phrase pasted
  // takes another phrase's place, fitted to its length; a few notes go in at the cursor, after the selection, or at
  // the phrase's start, each in place of any note they overlap
  function copyNotes(quiet = false) {
    const p = phrase(); if (!p?.notes?.length) return false;
    const chosen = picked(), whole = !chosen.length || chosen.length === p.notes.length;
    clipboard = whole ? { whole, notes: serializeNotes(p.notes, true), start: bounds(p).min_onset, end: bounds(p).max_end }
      : { whole, ...window.SongbirdModel.clipOf(p.notes, chosen) };
    if (!quiet) { paint(); bridge().toast?.(whole ? "The phrase's notes copied." : `${chosen.length} note${chosen.length === 1 ? "" : "s"} copied.`); }
    return true;
  }
  function pasteAt(notes, added, p = phrase(), message = "Notes pasted.", label = "Paste notes") {
    if (!p.own_path && (notes.filter((n) => !n.slur).length !== p.notes.filter((n) => !n.slur).length || notes.some((n) => n.alter && !n.slur))) {
      bridge().toast?.("Choose a sung line to paste a different syllable count or chromatic notes."); return;
    }
    pick(added[0] ?? 0, added); state.focusNote = true;
    commitNotes(notes, message, label); told();
  }
  function pasteNotes(at = null) {
    const p = phrase(); if (!clipboard || !p) return;
    const b = bounds(p);
    if (clipboard.whole) {
      const ratio = (b.max_end - b.min_onset) / (clipboard.end - clipboard.start);
      const notes = clipboard.notes.map((n) => ({ ...n, onset: b.min_onset + (n.onset - clipboard.start) * ratio, duration: n.duration * ratio }));
      if (notes.some((n) => n.duration < b.min_duration || n.degree < b.min_degree || n.degree > b.max_degree) || notes.at(-1).onset > b.max_final_onset) {
        bridge().toast?.("These notes don't fit this phrase."); return;
      }
      pasteAt(notes, notes.map((_, i) => i)); return;
    }
    const chosen = picked();
    const where = at ?? (state.cursor?.phrase === state.phrase ? state.cursor.beat
      : chosen.length ? p.notes[chosen.at(-1)].onset + p.notes[chosen.at(-1)].duration : b.min_onset);
    try {
      if (clipboard.notes.some((n) => n.degree < b.min_degree || n.degree > b.max_degree)) throw new Error("These notes are outside this line's range.");
      const { notes, added } = window.SongbirdModel.pasteAt(p.notes, clipboard, where, b);
      pasteAt(notes, added);
    } catch (error) { bridge().toast?.(error.message); }
  }
  function quantize() {  // the selection's (or the phrase's) starts and ends on the snap
    const p = phrase(), chosen = picked();
    if (!p?.notes?.length) return;
    const all = chosen.length ? window.SongbirdModel.withSyllables(p.notes, chosen) : p.notes.map((_, i) => i);
    try {
      const notes = window.SongbirdModel.quantizeNotes(p.notes, all, state.snap, bounds(p));
      if (chosen.length) pick(state.note, chosen);
      commitNotes(notes, `${chosen.length > 1 ? `${chosen.length} notes` : chosen.length ? "The note" : "The phrase"} on the ${snapName()}-beat grid.`, "Quantize");
    } catch (error) { bridge().toast?.(error.message); }
  }
  function cutNotes() {
    if (!picked().length || !copyNotes(true)) return;
    deleteNote();
  }
  function duplicateNotes() {
    const p = phrase(), chosen = picked();
    if (!chosen.length) { bridge().toast?.("Select notes to duplicate."); return; }
    const clip = window.SongbirdModel.clipOf(p.notes, chosen), last = p.notes[chosen.at(-1)];
    try {
      const { notes, added } = window.SongbirdModel.pasteAt(p.notes, clip, last.onset + last.duration, bounds(p));
      pasteAt(notes, added, p, `${chosen.length} note${chosen.length === 1 ? "" : "s"} duplicated.`, "Duplicate notes");
    } catch (error) { bridge().toast?.("No room to duplicate here."); }
  }
  // Ctrl or ⌘ with C, X, V, D or A in the roll (model.js rollKey: never in a text field)
  function shortcut(event) {
    const key = window.SongbirdModel?.rollKey?.(event);
    if (!key || state.player !== "voice" && notesMode()) return false;
    event.preventDefault(); event.stopPropagation?.();
    if (key.action === "all") selectAll();
    else if (key.action === "copy") copyNotes();
    else if (key.action === "cut") cutNotes();
    else if (key.action === "paste") pasteNotes();
    else if (key.action === "duplicate") duplicateNotes();
    return true;
  }
  function editTools() {
    const p = phrase();
    return el("div", { class: "sbc-tools notes-foot", role: "group", "aria-label": "Edit phrase" },
      button("Add note", () => addNote(), { disabled: !p?.own_path }),
      button("Delete note", deleteNote, { disabled: state.note === null }),
      button("Copy notes", () => copyNotes(), { title: "Copy the selected notes, or the phrase (Ctrl+C)" }),
      button("Paste notes", () => pasteNotes(), { disabled: !clipboard, title: "Paste (Ctrl+V)" }),
      button("Quantize", quantize, { title: "Put the selected notes, or the phrase, on the snap" }),
      button("Write line", writeLine, { disabled: !p?.own_path || !!state.draft }),
      el("details", { class: "sbc-phrase-actions" }, el("summary", {}, "Phrase"),
        button("Copy phrase", () => {
          if (state.draft) { bridge().toast?.("Apply or cancel this line's draft before copying the phrase."); return; }
          phraseClipboard = JSON.parse(JSON.stringify(p)); paint(); bridge().toast?.("Phrase copied: words, melody, chords and custom instrumental notes.");
        }),
        button("Paste phrase", async () => {
          try {
            if (state.draft) throw new Error("Apply or cancel this line's draft before pasting.");
            await bridge().applyPatch(window.SongbirdModel.phrasePatch(phraseClipboard, p), "Paste phrase");
          } catch (error) { bridge().toast?.(error.message); }
        }, { disabled: !phraseClipboard })));
  }
  function joinNote() {
    const p = phrase(), i = state.note, n = note();
    if (!p || !n?.slur) return;
    const notes = p.notes.map((x) => ({ ...x }));
    notes[i - 1].duration = n.onset + n.duration - notes[i - 1].onset;
    notes.splice(i, 1);
    state.note = i - 1;
    commitNotes(notes, "Joined into the note before.", "Join notes");
  }
  // a phrase's notes as the page draws them after an edit: each syllable's words found again by syllable
  function sung(updated, was, shape) {
    const words = was.filter((n) => !n.slur);
    let k = -1;
    return updated.map((n, index) => {
      if (!n.slur) k++;
      const own = words[k] || {};
      return { ...(shape ? was[index] : {}), ...n, index, syllable: n.slur ? "" : own.syllable, word: own.word, edited: true };
    });
  }
  function commitNotes(notes, message, label = "Change the melody") {
    const p = phrase();
    if (!p || !notes.length) return;
    const shape = notes.length === p.notes.length && notes.every((n, index) => !n.slur === !p.notes[index].slur);
    if (shape && notes.every((n, index) => n.degree === p.notes[index].degree && (n.alter || 0) === (p.notes[index].alter || 0) && n.onset === p.notes[index].onset && n.duration === p.notes[index].duration)) {
      // A guarded drag or nudge can end exactly where it started. Pinning that
      // untouched phrase would unnecessarily stop its inherited evolution.
      paint();
      if (message) announce(message);
      return;
    }
    const updated = notes.map((n) => ({ ...n, pitch: (composition()?.tonic || 60) + scaleOffset(n.degree) + (n.alter || 0) }));
    // a line of its own, or one whose count now differs from its tune line's: its words and notes go together
    const count = updated.filter((n) => !n.slur).length;
    const chromatic = notes.some((n, i) => (n.alter || 0) !== (p.notes[i]?.alter || 0));
    if (p.own_path && (p.own || chromatic || count !== p.tune_syllable_count || state.draft?.path === p.own_path)) {
      if (count === p.syllable_count && (p.own || chromatic) && state.draft?.path !== p.own_path) {
        // drawn at once, as a tune line's change is, wherever the lyric line is sung, its words kept by syllable
        for (const s of sections()) for (const same of s.phrases || []) if (same.own_path === p.own_path) same.notes = sung(updated, same.notes, shape);
        commit(p.own_path, { words: p.lyric_text, notes: serializeNotes(updated, true) }, label);
      } else {  // its words wait to be written for the new count (ownCard)
        state.draft = { ...state.draft, path: p.own_path, notes: updated, was: state.draft?.was || p.notes };
        p.notes = updated.map((n, index) => ({ ...n, index, edited: true }));
      }
      paint();
      told();  // the score's inspector shows the words card
      if (message) announce(message);
      return;
    }
    for (const s of sections()) for (const shared of s.phrases || []) if (sharesScope("tune", p, shared)) shared.notes = sung(updated, shared.notes, shape);
    commit(scopedPath("tune", p), serializeNotes(updated), label);
    paint();
    if (message) announce(message);
  }
  function limitedNote(index, changes, p = phrase(), snap = state.snap) {
    const original = p.notes[index], b = bounds(p);
    const next = { ...original, ...changes };
    const grid = Math.max(b.grid, snap);
    const quantize = (value) => M().onGrid(value, grid);
    // a slurred note's start is the boundary with the note before: it moves between the two, each keeping a quarter beat
    const previousEnd = original.slur ? p.notes[index - 1].onset + b.min_duration
      : index ? p.notes[index - 1].onset + p.notes[index - 1].duration : b.min_onset;
    const followingStart = index < p.notes.length - 1 ? p.notes[index + 1].onset : b.max_end;
    if ("degree" in changes) {
      next.degree = clamp(Math.round(next.degree), b.min_degree, b.max_degree);
      next.alter = chromatic(p, original) ? (changes.alter ?? original.alter ?? 0) : original.alter || 0;
      // named from its new pitch, not the one it was dragged from
      next.pitch = (composition()?.tonic || 60) + scaleOffset(next.degree) + (next.alter || 0);
    }
    const latestOnset = Math.min(original.slur ? original.onset + original.duration - b.min_duration : followingStart - original.duration,
      index === p.notes.length - 1 ? b.max_final_onset ?? b.max_end : b.max_end);
    // A vertical drag sends both axes. Keep untouched expressive timing exact
    // instead of snapping thirds (or a human offset) while changing only pitch.
    if ("onset" in changes && next.onset !== original.onset) next.onset = clamp(quantize(next.onset), previousEnd, latestOnset);
    if ("duration" in changes && next.duration !== original.duration) next.duration = clamp(quantize(next.duration), b.min_duration, followingStart - next.onset);
    return next;
  }
  // what an undo of a note's change says
  const changed = (changes) => ("onset" in changes ? "Move a note" : "duration" in changes ? "Change a note's length" : "Change a note's pitch");
  function changeNote(changes, snap) {
    const p = phrase();
    if (!p || state.note === null) return;
    const notes = keepSlurs(p.notes.map((n, index) => index === state.note ? limitedNote(index, changes, p, snap) : { ...n }),
      "onset" in changes ? state.note : -1);
    commitNotes(notes, noteTitle(notes[state.note], state.note), changed(changes));
  }
  function transpose(steps) {  // the selected notes, or the whole phrase, by steps of the scale
    const p = phrase(), b = bounds();
    if (!p) return;
    const chosen = several() ? new Set(picked()) : null;
    const notes = p.notes.map((n, i) => ({ ...n, degree: n.degree + (!chosen || chosen.has(i) ? steps : 0) }));
    if (notes.some((n) => n.degree < b.min_degree || n.degree > b.max_degree)) {
      bridge().toast?.("That would go beyond this melody’s singing range."); return;
    }
    if (chosen) pick(state.note, [...chosen]);
    commitNotes(notes, chosen ? `${chosen.size} notes transposed.` : Math.abs(steps) < 7 ? "Phrase transposed." : "Phrase moved an octave.",
      chosen ? "Transpose notes" : "Transpose the phrase");
  }
  // The selection moved together: by rows (a line of its own's notes by semitones, respelled; a tune line's by the
  // scale steps its anchor moves) and by dt beats (the anchor landing on the grid, no note passing one not chosen).
  function movedGroup(p, chosen, rows, dt, anchor = state.note) {
    const b = bounds(p), model = window.SongbirdModel, tonic = composition()?.tonic || 60;
    const semis = chosen.map((i) => semiOf(p.notes[i]));
    rows = clamp(rows, scaleOffset(b.min_degree) - Math.min(...semis), scaleOffset(b.max_degree) - Math.max(...semis));
    const timed = model.withSyllables(p.notes, chosen);
    const shift = model.shiftLimit(p.notes, timed, dt, b, Math.max(b.grid, state.snap), anchor);
    const set = new Set(chosen), moved = new Set(timed), whole = chromatic(p, p.notes[anchor]);
    const steps = rowsMoved(p, p.notes[anchor], rows).degree - p.notes[anchor].degree;
    return p.notes.map((n, i) => {
      const next = { ...n };
      if (set.has(i) && rows) {
        Object.assign(next, whole ? rowsMoved(p, n, rows) : { degree: clamp(n.degree + steps, b.min_degree, b.max_degree) });
        next.pitch = tonic + scaleOffset(next.degree) + (next.alter || 0);
      }
      if (moved.has(i) && shift) next.onset = n.onset + shift;
      return next;
    });
  }
  function moveGroup(rows, dt) {
    const p = phrase(), chosen = picked(), anchor = state.note;
    pick(anchor, chosen);
    commitNotes(movedGroup(p, chosen, rows, dt, anchor), `${chosen.length} notes moved.`, "Move notes");
  }
  // The grid a phrase's rhythm lives on: halves of a beat where every note sits on them, thirds where they sit
  // on thirds (a six feel, a triplet lilt), quarters otherwise; each with the finer grids of its kind after it.
  function feelGrids(p) {
    const times = p.notes.flatMap((n) => [n.onset, n.duration]);
    const on = (parts) => times.every((t) => Math.abs(t * parts - Math.round(t * parts)) < 1e-6);
    if (on(2)) return [2, 4];
    if (on(3)) return [3, 6];
    return [4];
  }
  function evenRhythm() {
    const p = phrase(), b = bounds();
    if (!p || p.notes.length < 2) return;
    const end = p.notes.at(-1).onset + p.notes.at(-1).duration, n = p.notes.length;
    // Every note the same number of grid steps, on the phrase's own grid (never an even share of its span:
    // 1.2727 beats is off every grid a musician counts in); the last note held to where the line ended, and
    // starting early enough to leave the cadence its room before the next line's pickup. Positions are counted
    // in whole steps of the grid (parts of a beat), so a third stays exactly the third the server keeps.
    for (const parts of feelGrids(p)) {
      const first = Math.max(Math.ceil(b.min_onset * parts - 1e-9), Math.round(p.notes[0].onset * parts));
      const start = first / parts;
      const lastLimit = Math.min(start + (end - start) * (n - 1) / n, b.max_final_onset ?? b.max_end, end - b.min_duration);
      const least = Math.ceil(b.min_duration * parts - 1e-9);
      const step = Math.floor((lastLimit - start) * parts / (n - 1) + 1e-9);
      const at = (i) => (first + i * step) / parts;
      if (step < least || end - at(n - 1) < b.min_duration - 1e-9) continue;
      const notes = p.notes.map((note, i) => ({ ...note, onset: at(i), duration: i === n - 1 ? end - at(i) : at(i + 1) - at(i) }));
      commitNotes(notes, `Notes evened to ${fmt(round(step / parts))} of a beat each, on the phrase's grid; the ending held.`, "Even the rhythm");
      return;
    }
    bridge().toast?.("This phrase is too tightly packed to space evenly while keeping every syllable singable.");
  }
  function smoothMelody() {
    const p = phrase(), b = bounds();
    if (!p) return;
    const notes = p.notes.map((n) => ({ ...n }));
    // Work back from the fixed cadence so every resulting interval is a step
    // or a third and the most important note keeps its identity.
    for (let i = notes.length - 2; i >= 0; i--) {
      notes[i].degree = clamp(notes[i].degree, Math.max(b.min_degree, notes[i + 1].degree - 2), Math.min(b.max_degree, notes[i + 1].degree + 2));
    }
    commitNotes(notes, "Large leaps softened; phrase ending preserved.", "Soften leaps");
  }

  function moveSection(from, to) {
    if (from === to || to < 0 || to >= sections().length) return;
    const reordered = [...sections()];
    const [moved] = reordered.splice(from, 1); reordered.splice(to, 0, moved);
    const originalOccurrences = sections().filter((s) => s.name === moved.name).map((s) => s.id);
    const nextOccurrences = reordered.filter((s) => s.name === moved.name).map((s) => s.id);
    if (originalOccurrences.some((id, index) => id !== nextOccurrences[index])) {
      bridge().toast?.("Repeated verses and refrains keep their lyric order."); return;
    }
    const order = reordered.map((s) => s.id);
    state.section = to; state.phrase = 0; state.note = null;
    commit("form.order", order, `Move ${moved.label}`);
    announce(`Moved ${sections()[from].label} to position ${to + 1}.`);
  }
  function miniNotes(s) {
    const all = (s.phrases || []).flatMap((p) => p.notes.map((n) => ({ ...n, at: (p.start_beat || 0) - (s.start_beat || 0) + n.onset })));
    const low = Math.min(...all.map((n) => n.degree), 1), high = Math.max(...all.map((n) => n.degree), 8);
    const total = s.duration_beats || 1;
    return svg("svg", { class: "sbc-mini", viewBox: "0 0 120 28", preserveAspectRatio: "none", "aria-hidden": "true" },
      all.map((n) => svg("line", { x1: clamp(n.at / total * 120, 0, 120), x2: clamp((n.at + n.duration) / total * 120, 0, 120),
        y1: 24 - (n.degree - low) / Math.max(1, high - low) * 20, y2: 24 - (n.degree - low) / Math.max(1, high - low) * 20,
        stroke: "currentColor", "stroke-width": "2", "stroke-linecap": "round" })));
  }
  function songSpan() {
    const start = sections()[0]?.start_beat || 0;
    const last = sections().at(-1);
    return { start, duration: Math.max(1, (last?.start_beat || 0) + (last?.duration_beats || 1) - start) };
  }
  function songOverview() {
    const span = songSpan(), c = composition();
    return el("div", { class: "sbc-overview" },
      el("div", { class: "sbc-overview-labels" }, el("span", {}, "Whole song"), el("span", {}, `${fmt(span.duration / c.beats_per_bar)} bars`)),
      el("div", { class: "sbc-overview-track", role: "group", "aria-label": "Complete song timeline; select any section" },
        sections().map((s, index) => {
          const width = s.duration_beats / span.duration * 100;
          return el("button", { type: "button", id: `sbc-overview-${s.id}`, class: `sbc-overview-section${index === state.section ? " is-selected" : ""}${s.name.includes("refrain") ? " is-refrain" : ""}`,
            "data-overview-section": index, "aria-pressed": index === state.section ? "true" : "false",
            "aria-label": `${s.label}, bar ${fmt((s.start_beat - span.start) / c.beats_per_bar + 1)}`, title: s.label,
            style: { left: `${(s.start_beat - span.start) / span.duration * 100}%`, width: `${width}%` },
            onclick: () => {
              selectedSection(index);
              root()?.querySelector(`[data-section="${index}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
            },
          }, el("span", { class: "sbc-overview-section-label" }, width < 5 ? String(index + 1) : s.label), miniNotes(s));
        }),
        el("div", { id: "sbc-song-playhead", class: "sbc-song-playhead", hidden: !state.playback, "aria-hidden": "true" })));
  }
  function arrangement() {
    const c = composition();
    const start = songSpan().start;
    const cards = sections().map((s, index) => {
      const card = button("", () => selectedSection(index), {
        id: `sbc-section-${s.id}`,
        class: `sbc-section${index === state.section ? " is-selected" : ""}${s.name.includes("refrain") ? " is-refrain" : ""}`,
        draggable: "true", "aria-pressed": index === state.section ? "true" : "false",
        "aria-label": `${index + 1}. ${s.label}, ${fmt(s.duration_beats)} beats. Select to edit; drag to rearrange.`,
        "data-section": index, style: { flex: `${Math.max(s.duration_beats, 4)} 0 ${Math.max(114, Math.min(210, s.duration_beats * 4))}px` },
        ondragstart: (event) => {
          event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(index));
          state.drag = { section: index }; card.classList.add("is-dragging");
        },
        ondragend: () => { state.drag = null; root()?.querySelectorAll(".is-drop-target, .is-dragging").forEach((item) => item.classList.remove("is-drop-target", "is-dragging")); },
        ondragover: (event) => { if (state.drag?.section === undefined) return; event.preventDefault(); event.dataTransfer.dropEffect = "move"; card.classList.add("is-drop-target"); },
        ondragleave: () => card.classList.remove("is-drop-target"),
        ondrop: (event) => {
          event.preventDefault(); card.classList.remove("is-drop-target");
          if (state.drag?.section === undefined) return;
          const from = state.drag.section; state.drag = null; moveSection(from, index);
        },
      });
      card.append(el("span", { class: "sbc-section-top" }, el("span", { class: "sbc-section-num" }, String(index + 1).padStart(2, "0")),
        el("span", { class: "sbc-section-bars" }, `${fmt(s.duration_beats / c.beats_per_bar)} bars`)),
      el("strong", {}, s.label), miniNotes(s), el("span", { class: "sbc-section-foot" }, `Bar ${fmt((s.start_beat - start) / c.beats_per_bar + 1)}`));
      return card;
    });
    const totalSeconds = Math.round(c.duration_seconds ?? c.duration_beats * 60 / c.tempo);
    return el("div", { class: "sbc-arrangement" },
      el("div", { class: "sbc-row sbc-arrangement-heading" }, el("div", {}, el("h3", {}, "Arrangement"), el("p", { class: "sbc-muted" }, "Drag a section to reorder your song.")),
        el("span", { class: "sbc-tag" }, `${sections().length} sections · ${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`)),
      songOverview(),
      el("div", { class: "sbc-arrangement-scroll", "aria-label": "Song sections" }, el("div", { class: "sbc-sections" }, cards)),
      el("div", { class: "sbc-row sbc-arrangement-actions" },
        el("span", { class: "sbc-muted" }, section()?.label || ""),
        el("div", { class: "sbc-button-group", role: "group", "aria-label": "Move selected section" },
          button("← Earlier", () => moveSection(state.section, state.section - 1), { disabled: state.section === 0 }),
          button("Later →", () => moveSection(state.section, state.section + 1), { disabled: state.section === sections().length - 1 }),
          button("Restore order", () => commit("form.order", null, "Restore the order"), { class: "sbc-button sbc-quiet", title: "Remove your arrangement override and restore this song’s inherited order" }))));
  }

  function transport() {
    const c = composition();
    return el("div", { class: "sbc-transport" },
      el("div", { class: "sbc-transport-main" }, button(state.playback ? "■ Stop sketch" : "▶ Play sketch", togglePlay,
        { id: "sbc-play", class: "sbc-button sbc-primary", "aria-pressed": state.playback ? "true" : "false" }),
        select("Play", state.scope, [["phrase", "This phrase"], ["section", "This section"], ["song", "Whole song"]], (value) => { stop(); state.scope = value; paint(); }, { id: "sbc-play-scope" }),
        checkbox("Loop", state.loop, (value) => { state.loop = value; }),
        checkbox("Click", state.metronome, (value) => { state.metronome = value; if (state.playback) { stop(); play(); } }),
        // the sketch's band: the chords and a bass under the tune, from the score (a person's harmony included)
        checkbox("Chords", state.chords, (value) => { state.chords = value; if (state.playback) { stop(); play(); } }),
        checkbox("Bass", state.bass, (value) => { state.bass = value; if (state.playback) { stop(); play(); } })),
      el("div", { class: "sbc-transport-meta" }, el("span", { class: "sbc-tempo" }, `${Math.round(c.tempo)} `, el("span", {}, "BPM")),
        // what the two players are is said on demand, in the tune's "What is this?" (index.html)
        button("Hear sung section", () => { stop(); bridge().listen?.("you", section()?.index ?? state.section); }, { class: "sbc-button sbc-quiet" })));
  }
  function phraseStrip() {
    const s = section();
    return el("div", { class: "sbc-phrase-strip", role: "group", "aria-label": `Phrases in ${s.label}` },
      (s.phrases || []).map(phraseButton));
  }
  function phraseButton(p, index) {
    const words = p.notes.map((n) => displayWords(n.syllable)).filter(Boolean).join(" ") || (p.own_path && !p.notes.length ? "Empty" : "");
    return el("button", { type: "button", id: `sbc-phrase-${index}`, class: `sbc-phrase${index === state.phrase ? " is-selected" : ""}`,
      "aria-pressed": index === state.phrase ? "true" : "false", onclick: () => selectedPhrase(index) },
    el("span", { class: "sbc-phrase-label" }, `Phrase ${index + 1}${drafts.has(p.own_path) ? " · draft" : ""}`, composition().edited_phrases?.includes(p.id) ? el("span", { class: "sbc-edited-dot", title: "Your melody" }, "•") : null),
    el("span", { class: "sbc-phrase-words" }, words || "Instrumental melody"));
  }
  // ---- the whole section in one roll: its phrases end to end on one time axis, from the first line's pickup to the
  // last bar. Each note stays its phrase's, inside that phrase's own bounds; the phrase holding the selection is the
  // one the tools, the scope, the words' draft and the clipboard act on.
  const offsetOf = (p, s = section()) => (p?.start_beat ?? s?.start_beat ?? 0) - (s?.start_beat ?? 0);
  function sectionGeometry(s = section()) {
    const spans = (s?.phrases || []).map((p, i) => {
      const b = bounds(p), off = offsetOf(p, s);
      return { p, i, b, off, start: off + b.min_onset, end: off + b.max_end, final: off + (b.max_final_onset ?? b.max_end) };
    });
    const sung = spans.filter((x) => drawable(x.p)), semis = sung.flatMap((x) => x.p.notes).map(semiOf);
    const lowest = scaleOffset(Math.min(...sung.map((x) => x.b.min_degree))), highest = scaleOffset(Math.max(...sung.map((x) => x.b.max_degree)));
    const low = Math.max(lowest, Math.min(0, ...semis) - 3), high = Math.min(highest, Math.max(12, ...semis) + 3);
    const start = Math.min(0, ...sung.map((x) => x.start)), end = Math.max(s?.duration_beats || 0, ...sung.map((x) => x.end));
    const row = 23, left = 58, ruler = spans.some((x) => x.p.chords?.length) ? 54 : 28;
    const available = Math.max(500, (root()?.clientWidth || 950) - 44);
    const unit = M().rollUnit(state.zoom, available - left, end - start);
    return { spans, low, high, start, end, row, left, ruler, unit, width: left + (end - start) * unit, height: ruler + (high - low + 1) * row };
  }
  const xAt = (g, beat) => g.left + (beat - g.start) * g.unit;  // a beat of the section, on the roll
  function chordLane(roll, g, span) {
    const p = span.p, c = composition();
    const lane = p.harmony?.length ? p.harmony : p.chords.flatMap((chords, bar) => chords.map((symbol, slot) => ({
      bar, slot, symbol, name: symbol, start: bar * c.beats_per_bar + slot * c.beats_per_bar / chords.length, beats: c.beats_per_bar / chords.length })));
    lane.forEach((h) => {
      const chosen = span.i === state.phrase && state.chord && state.chord.bar === h.bar && state.chord.slot === h.slot;
      const rub = h.rubs?.length ? `; ${h.rubs.length} sung note${h.rubs.length === 1 ? "" : "s"} not in it${h.hard ? ", one a half step off" : ""}` : "";
      roll.append(el("button", { type: "button", "data-chord": `${h.bar}.${h.slot}`, "data-chord-phrase": span.i,
        class: `sbc-chord${chordMine(p, h) ? " is-edited" : ""}${chosen ? " is-selected" : ""}${h.hard ? " is-rub" : ""}`,
        "aria-pressed": chosen ? "true" : "false", "aria-label": `Phrase ${span.i + 1}, bar ${h.bar + 1}, chord ${h.name}${rub}. Select to change it.`,
        title: `Bar ${h.bar + 1}: ${h.name}${rub}. Select to change it.`, onclick: () => selectChord(h, span.i),
        style: { left: `${xAt(g, span.off + h.start)}px`, width: `${Math.max(1, h.beats * g.unit - 2)}px` } }, h.name));
    });
  }
  function pianoRoll() {
    const s = section(), g = sectionGeometry(s), c = composition(), p = phrase();
    const roll = el("div", { class: "sbc-roll", style: { width: `${g.width}px`, height: `${g.height}px` }, "aria-label": "Melody piano roll" });
    if (g.spans.some((x) => x.p.chords?.length)) roll.append(el("span", { class: "sbc-harmony-label" }, "Harmony"));
    for (const span of g.spans) if (span.p.chords?.length) chordLane(roll, g, span);
    const plot = el("div", { class: "sbc-grid", style: { left: `${g.left}px`, top: `${g.ruler}px`, width: `${g.width - g.left}px`, height: `${g.height - g.ruler}px`,
      backgroundSize: `${g.unit * state.snap}px ${g.row}px` } });
    roll.append(plot);
    plot.addEventListener("pointerdown", (event) => emptyDrag(event, g, plot));
    if (state.cursor && g.spans[state.cursor.phrase]) roll.append(el("div", { class: "sbc-cursor", "aria-hidden": "true",
      style: { left: `${xAt(g, g.spans[state.cursor.phrase].off + state.cursor.beat)}px`, top: `${g.ruler}px`, height: `${g.height - g.ruler}px` } }));
    // the selected phrase's time, and a line where each phrase after the first begins
    const chosen = g.spans[state.phrase];
    if (drawable(chosen?.p)) roll.append(el("div", { class: "sbc-phrase-span", style: { left: `${xAt(g, chosen.start)}px`, top: `${g.ruler}px`,
      width: `${(chosen.end - chosen.start) * g.unit}px`, height: `${g.height - g.ruler}px` } }));
    for (const span of g.spans.slice(1)) roll.append(el("div", { class: "sbc-phrase-line", style: { left: `${xAt(g, span.off)}px`, top: "0px", height: `${g.height}px` } }));
    // a row a semitone: the scale's own tones plain (the tonic's marked), the ones between shaded
    for (let semi = g.high; semi >= g.low; semi--) {
      const y = g.ruler + (g.high - semi) * g.row, pitch = (c.tonic || 60) + semi;
      const { degree, alter } = M().spell(semi, scale()), tonic = !alter && ((degree - 1) % 7 + 7) % 7 === 0;
      const row = alter ? "sbc-out-row" : tonic ? "sbc-tonic-row" : null;
      if (row) roll.append(el("div", { class: row, style: { left: `${g.left}px`, top: `${y}px`, width: `${g.width - g.left}px`, height: `${g.row}px` } }));
      roll.append(button("", () => audition(pitch), { class: `sbc-key${tonic ? " is-tonic" : ""}${alter ? " is-out" : ""}`,
        id: `sbc-key-${semi}`,
        title: `${pitchName(pitch)}${alter ? "" : `, scale degree ${degree}`}. Click to hear.`, "aria-label": `Hear ${pitchName(pitch)}${alter ? "" : `, scale degree ${degree}`}`,
        style: { top: `${y}px`, height: `${g.row}px`, width: `${g.left - 4}px` },
      }));
      roll.lastChild.append(el("span", {}, alter ? "" : degreeName(degree)), el("small", {}, pitchName(pitch)));
    }
    for (let beat = Math.ceil(g.start); beat <= g.end; beat++) {
      const x = xAt(g, beat);
      const bar = beat >= 0 && beat % c.beats_per_bar === 0;
      roll.append(el("span", { class: `sbc-ruler-label${bar ? " is-bar" : ""}`, style: { left: `${x}px` } },
        beat < 0 ? "↗" : bar ? `${Math.floor(beat / c.beats_per_bar) + 1}` : "·"),
      el("div", { class: `sbc-grid-line${bar ? " is-bar" : ""}`, style: { left: `${x}px`, top: `${g.ruler}px`, height: `${g.height - g.ruler}px` } }));
    }
    for (const span of g.spans) {
      const q = span.p, here = span.i === state.phrase, chosen = here ? new Set(picked()) : new Set();
      q.notes.forEach((n, index) => {
        const picked = chosen.has(index), style = noteStyle(n, g, span.off), wide = parseFloat(style.width), handle = M().grip(wide);
        const word = n.slur ? "‿" : displayWords(n.syllable) || "♪";
        const item = el("button", { type: "button", class: `sbc-note${picked ? " is-selected" : ""}${index === q.notes.length - 1 ? " is-cadence" : ""}${n.edited ? " is-edited" : ""}${n.slur ? " is-slur" : ""}${here && chosenChord()?.rubs?.includes(index) ? " is-rub" : ""}`,
          "aria-label": noteTitle(n, index, q), "aria-pressed": picked ? "true" : "false", "data-note": index, "data-phrase": span.i,
          title: `${noteTitle(n, index, q)}. Drag to move; drag its right edge, or ⌥-drag, to change its length.`,
          style, onclick: (event) => {
            if (state.drag?.moved) return;
            if (event.shiftKey) { toggleNote(span.i, index); return; }
            selectNote(span.i, index); audition(pitchFor(n));
          }, onpointerdown: (event) => startNoteDrag(event, span.i, index, g), onkeydown: (event) => noteKey(event, index, span.i),
        }, el("span", { class: "sbc-note-word" }, M().labelFits(word, wide - handle, { char: 5.4 }) ? word : ""),
        handle ? el("span", { class: "sbc-resize", "aria-hidden": "true", style: { width: `${handle}px` } }, "") : null);
        roll.append(item);
      });
    }
    roll.append(el("div", { id: "sbc-playhead", class: "sbc-playhead", hidden: !state.playback,
      style: { left: `${g.left}px`, top: `${g.ruler}px`, height: `${g.height - g.ruler}px` } }));
    if (p && state.reveal) { state.reveal = false; state.scrollTo = Math.max(0, xAt(g, g.spans[state.phrase].start) - g.left); }
    return el("div", { id: "sbc-roll-scroll", class: "sbc-roll-scroll", tabindex: "0", "aria-label": "Scrollable melody editor", onkeydown: shortcut }, roll);
  }
  // On the empty roll: a click puts the cursor there (where a paste goes) and lets the notes go; two add a note.
  // A drag draws a note as long as the drag, where a line can have notes added (a sung line); a Shift-drag (or any
  // drag in a line that can't) draws a rectangle that selects the notes it touches in the phrase it began in.
  let lastClick = null;
  function emptyDrag(event, g, plot) {
    if (event.button !== 0 || (notesMode() && page()?.narrow?.())) return;
    const rect = plot.getBoundingClientRect(), x0 = event.clientX, y0 = event.clientY;
    const at = (x, y) => ({ beat: g.start + (x - rect.left) / g.unit, semi: g.high - Math.floor((y - rect.top) / g.row) });
    const down = at(x0, y0), pi = window.SongbirdModel.phraseAt(g.spans, down.beat);
    const drawing = !event.shiftKey && pi !== null && !!g.spans[pi].p.own_path;
    const snapped = (beat) => M().onGrid(beat, state.snap);
    const drawn = (beat) => {  // the note a drag draws: from where it began to where it is, on the snap
      const a = snapped(Math.min(down.beat, beat)), z = Math.max(snapped(Math.max(down.beat, beat)), a + state.snap);
      return { onset: a - g.spans[pi].off, duration: z - a };
    };
    const box = el("div", { class: drawing ? "sbc-note is-drawing" : "sbc-marquee", hidden: true, "aria-hidden": "true" });
    plot.parentNode?.append(box);
    let moved = false;
    plot.setPointerCapture?.(event.pointerId);
    const move = (e) => {
      if (!moved && Math.abs(e.clientX - x0) + Math.abs(e.clientY - y0) < 4) return;
      moved = true; box.hidden = false;
      if (drawing) Object.assign(box.style, noteStyle({ ...drawn(at(e.clientX, e.clientY).beat), pitch: (composition()?.tonic || 60) + down.semi }, g, g.spans[pi].off));
      else Object.assign(box.style, { left: `${g.left + Math.min(x0, e.clientX) - rect.left}px`, top: `${g.ruler + Math.min(y0, e.clientY) - rect.top}px`,
        width: `${Math.abs(e.clientX - x0)}px`, height: `${Math.abs(e.clientY - y0)}px` });
    };
    const up = (e) => {
      plot.removeEventListener("pointermove", move); plot.removeEventListener("pointerup", up); plot.removeEventListener("pointercancel", cancel);
      if (plot.hasPointerCapture?.(e.pointerId)) plot.releasePointerCapture(e.pointerId);
      box.remove?.();
      if (moved && drawing) {
        const note = drawn(at(e.clientX, e.clientY).beat);
        focusPhrase(pi); addNote(note.onset, M().spell(down.semi, scale()), note.duration); return;
      }
      if (moved) { marquee(g, pi, down, at(e.clientX, e.clientY)); return; }
      const now = Date.now(), twice = lastClick && now - lastClick.time < 450 && Math.abs(lastClick.x - x0) + Math.abs(lastClick.y - y0) < 8;
      lastClick = twice ? null : { time: now, x: x0, y: y0 };
      if (pi === null) return;
      focusPhrase(pi);
      if (twice) { addNote(down.beat - g.spans[pi].off, M().spell(down.semi, scale())); return; }
      state.note = null; state.chord = null;
      state.cursor = { phrase: pi, beat: clamp(M().onGrid(down.beat - g.spans[pi].off, state.snap), g.spans[pi].b.min_onset, g.spans[pi].b.max_end) };
      paint(); told();
      root()?.querySelector("#sbc-roll-scroll")?.focus({ preventScroll: true });
    };
    const cancel = (e) => { moved = false; box.remove?.(); plot.removeEventListener("pointermove", move); plot.removeEventListener("pointerup", up); plot.removeEventListener("pointercancel", cancel); };
    plot.addEventListener("pointermove", move); plot.addEventListener("pointerup", up); plot.addEventListener("pointercancel", cancel);
  }
  function marquee(g, pi, a, z) {
    const lo = Math.min(a.beat, z.beat), hi = Math.max(a.beat, z.beat), top = Math.max(a.semi, z.semi), bottom = Math.min(a.semi, z.semi);
    const inside = (span) => span.p.notes.flatMap((n, i) => (span.off + n.onset < hi && span.off + n.onset + n.duration > lo &&
      semiOf(n) <= top && semiOf(n) >= bottom ? [i] : []));
    // the phrase it began in, or else the one it caught the most notes of
    const span = pi !== null && inside(g.spans[pi]).length ? g.spans[pi]
      : g.spans.reduce((best, x) => (inside(x).length > (best ? inside(best).length : 0) ? x : best), null);
    const chosen = span ? inside(span) : [];
    if (!chosen.length) { state.note = null; paint(); told(); return; }
    focusPhrase(span.i); pick(chosen[0], chosen); state.chord = null; state.focusNote = true;
    paint(); told();
    announce(`${chosen.length} note${chosen.length === 1 ? "" : "s"} selected`);
  }
  function noteStyle(n, g, off = offsetOf(phrase())) {
    return { left: `${xAt(g, off + n.onset) + 1}px`, top: `${g.ruler + (g.high - semiOf(n)) * g.row + 2}px`,
      width: `${Math.max(9, n.duration * g.unit - 3)}px`, height: `${g.row - 4}px` };
  }
  const noteNode = (pi, index) => [...(root()?.querySelectorAll(".sbc-note") || [])]
    .find((node) => node.dataset.note === String(index) && node.dataset.phrase === String(pi)) || null;
  // the phrase the tools act on: choosing another one lets go of the last one's chord and scope
  function focusPhrase(pi) {
    if (pi === state.phrase) return false;
    state.phrase = pi; state.note = null; state.chord = null; state.where = { tune: null, chords: null };
    return true;
  }
  function selectNote(pi, index) {
    if (focusPhrase(pi)) {  // another phrase: its tools, scope and words are drawn for it
      state.note = index; state.focusNote = true; paint();
      announce(noteTitle(phrase().notes[index], index)); told(); return;
    }
    state.note = index;
    root().querySelectorAll(".sbc-note").forEach((node) => { const chosen = Number(node.dataset.note) === index && Number(node.dataset.phrase) === pi; node.classList.toggle("is-selected", chosen); node.setAttribute("aria-pressed", String(chosen)); });
    const old = root().querySelector(".sbc-inspector");
    if (state.chord) { state.chord = null; root().querySelector(".sbc-chord-card")?.replaceWith(inspector()); root().querySelectorAll(".sbc-chord.is-selected, .sbc-note.is-rub").forEach((node) => node.classList.remove("is-selected", "is-rub")); }
    else if (old) old.replaceWith(inspector());
    announce(noteTitle(phrase().notes[index], index)); told();
  }
  function startNoteDrag(event, pi, index, geometry) {
    if (event.button !== 0) return;
    if (notesMode() && page()?.narrow?.()) return; // on a phone the roll is read, and a tap selects: the inspector edits
    if (event.shiftKey) return;  // Shift-click adds the note to the selection, or takes it away (its click)
    stop();
    let target = event.currentTarget;
    const rect = target.getBoundingClientRect();
    // its right edge (as wide as its handle: none on a narrow note) or ⌥ anywhere on it changes its length
    const handle = M().grip(rect.width);
    const resizing = event.altKey || (handle > 0 && event.clientX > rect.right - handle);
    // a note of the selection drags the whole selection (its click, without a drag, chooses it alone)
    const group = !resizing && pi === state.phrase && several() && picked().includes(index) ? picked() : null;
    if (!group) selectNote(pi, index);
    target = noteNode(pi, index) || target;  // a new phrase repaints the roll
    const p = phrase(), original = { ...p.notes[index] }, off = offsetOf(p);
    const drag = { index, original, x: event.clientX, y: event.clientY, moved: false, resizing, preview: original };
    state.drag = drag; target.setPointerCapture(event.pointerId);
    const move = (nextEvent) => {
      if (Math.abs(nextEvent.clientX - drag.x) + Math.abs(nextEvent.clientY - drag.y) < 4 && !drag.moved) return;
      drag.moved = true;
      const time = (nextEvent.clientX - drag.x) / geometry.unit;
      // a drag that stays within half a grid unit sideways is a pitch change only: the note's timing,
      // off-grid or not, is kept exactly instead of being snapped by a pixel of drift
      const sideways = Math.abs(nextEvent.clientX - drag.x) >= Math.max(4, geometry.unit / 2);
      const rows = -Math.round((nextEvent.clientY - drag.y) / geometry.row);
      if (group) {
        drag.notes = movedGroup(p, group, rows, sideways ? time : 0, index);
        drag.notes.forEach((n, i) => { const node = noteNode(state.phrase, i); if (node) Object.assign(node.style, noteStyle(n, geometry, off)); });
        target.classList.add("is-dragging");
        return;
      }
      const pitch = rowsMoved(p, original, rows);
      const changes = resizing ? { duration: original.duration + time } : sideways ? { onset: original.onset + time, ...pitch } : pitch;
      drag.preview = limitedNote(index, changes, p);
      Object.assign(target.style, noteStyle(drag.preview, geometry, off));
      target.classList.add("is-dragging");
      const detail = document.getElementById("sbc-drag-value");
      if (detail) detail.textContent = noteTitle(drag.preview, index);
    };
    const finish = (upEvent) => {
      target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", finish); target.removeEventListener("pointercancel", cancel);
      if (target.hasPointerCapture(upEvent.pointerId)) target.releasePointerCapture(upEvent.pointerId);
      target.classList.remove("is-dragging");
      if (drag.moved && group) { pick(index, group); commitNotes(drag.notes, `${group.length} notes moved.`, "Move notes"); audition(drag.notes[index].pitch); }
      else if (drag.moved) {
        const notes = keepSlurs(p.notes.map((n, i) => i === index ? drag.preview : { ...n }), drag.preview.onset !== original.onset ? index : -1);
        commitNotes(notes, noteTitle(drag.preview, index), drag.resizing ? "Change a note's length" : "Move a note"); audition(drag.preview.pitch ?? pitchFor(original, drag.preview.degree));
      }
      // A pointer's synthetic click must not audition the old pitch after a drag.
      setTimeout(() => { if (state.drag === drag) state.drag = null; }, 0);
    };
    const cancel = (cancelEvent) => {
      drag.moved = false;
      p.notes.forEach((n, i) => { const node = noteNode(state.phrase, i); if (node) Object.assign(node.style, noteStyle(n, geometry, off)); });
      finish(cancelEvent); state.drag = null;
    };
    target.addEventListener("pointermove", move); target.addEventListener("pointerup", finish); target.addEventListener("pointercancel", cancel);
  }
  function noteKey(event, index, pi = state.phrase) {
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault(); event.stopPropagation?.(); focusPhrase(pi); if (!picked().includes(index)) state.note = index; deleteNote(); return;
    }
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault(); focusPhrase(pi);
    const vertical = event.key === "ArrowUp" || event.key === "ArrowDown", direction = ["ArrowUp", "ArrowRight"].includes(event.key) ? 1 : -1;
    if (!picked().includes(index) || (event.shiftKey && !vertical)) state.note = index;  // ⇧ ← → a note's own length
    else if (several()) {
      moveGroup(vertical ? direction * (event.altKey ? 12 : 1) : 0, vertical ? 0 : direction * state.snap);
      noteNode(state.phrase, index)?.focus({ preventScroll: true });
      return;
    }
    const n = note();
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      const direction = event.key === "ArrowUp" ? 1 : -1;  // a row (a semitone, or the scale's next tone); ⌥ an octave
      changeNote(rowsMoved(phrase(), n, direction * (event.altKey ? 12 : 1)));
    } else {
      const delta = (event.key === "ArrowRight" ? 1 : -1) * state.snap;
      changeNote(event.shiftKey ? { duration: n.duration + delta } : { onset: n.onset + delta });
    }
    noteNode(state.phrase, state.note ?? index)?.focus({ preventScroll: true });
  }
  // ---- the chords (docs/STUDIO.md, "Changing the chords"): a tune line's chords, a list a bar, each a function
  // of the key (a numeral, a quality if named, a bass if not the root), changed everywhere the line is sung.
  // as theory.QUALITIES: the triads, and the chords a lead sheet writes with a fourth tone (a seventh, a sixth, a ninth)
  const QUALITIES = { maj: [0, 4, 7], m: [0, 3, 7], dim: [0, 3, 6], aug: [0, 4, 8], sus2: [0, 2, 7], sus4: [0, 5, 7],
    7: [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10], m7b5: [0, 3, 6, 10], dim7: [0, 3, 6, 9], 6: [0, 4, 7, 9],
    m6: [0, 3, 7, 9], add9: [0, 4, 7, 14], madd9: [0, 3, 7, 14], "7sus4": [0, 5, 7, 10], "7sus2": [0, 2, 7, 10] };
  const KINDS = Object.keys(QUALITIES).sort((a, b) => b.length - a.length).join("|");
  const CHORD = new RegExp(`^([#b]?)([iIvV]{1,3})(${KINDS})?(?:\\/([357]))?$`);
  const NUMERALS = { i: 1, ii: 2, iii: 3, iv: 4, v: 5, vi: 6, vii: 7 };
  const WITH_SEVENTH = new Set(["7", "maj7", "m7", "m7b5", "dim7", "7sus4", "7sus2"]); // may put its seventh in the bass
  function parseChord(symbol) {
    const m = CHORD.exec(String(symbol || "").trim());
    if (!m || !NUMERALS[m[2].toLowerCase()]) return null;
    return { root: m[1] + m[2].toUpperCase(), accidental: m[1], degree: NUMERALS[m[2].toLowerCase()], quality: m[3] || "", bass: Number(m[4] || 1) };
  }
  function chordSymbol(parts) {
    const bass = parts.bass === 7 && !WITH_SEVENTH.has(parts.quality) ? 1 : parts.bass; // no seventh: no seventh below
    return `${parts.root}${parts.quality || ""}${bass && bass !== 1 ? `/${bass}` : ""}`;
  }
  function chordPitches(symbol) {
    // as theory.chord_tones: the mode's triad on a plain numeral, major on a borrowed one, a named quality as named
    const parts = parseChord(symbol), c = composition();
    if (!parts) return [];
    const alter = parts.accidental === "#" ? 1 : parts.accidental === "b" ? -1 : 0;
    const at = (degree) => scaleOffset(degree);
    const root = at(parts.degree) + alter;
    const tones = parts.quality ? QUALITIES[parts.quality].map((t) => root + t)
      : alter ? [root, root + 4, root + 7] : [at(parts.degree), at(parts.degree + 2), at(parts.degree + 4)];
    return tones.map((t) => (c?.tonic || 60) + t);
  }
  function lineChords(p = phrase()) {
    // an edit for everywhere starts from the line's everywhere chords, not this place's own
    const base = where("chords", p) === "line" && p?.line_chords ? p.line_chords : p?.chords;
    return (base || []).map((bar) => [...bar]);
  }
  function chosenChord(p = phrase()) {
    return state.chord ? (p?.harmony || []).find((h) => h.bar === state.chord.bar && h.slot === state.chord.slot) : null;
  }
  function chordMine(p, h) {
    // a person's chord, in the second ink: one that differs from the song's own at that place
    if (!p.chords_edited) return false;
    const own = p.song_chords?.[h.bar];
    return !own || own.length !== p.chords[h.bar].length || own[h.slot] !== h.symbol;
  }
  function selectChord(h, pi = state.phrase) {
    focusPhrase(pi);
    state.chord = { bar: h.bar, slot: h.slot }; state.note = null;
    paint(); strum(h.symbol); told();
    [...root().querySelectorAll(".sbc-chord")].find((node) => node.dataset.chord === `${h.bar}.${h.slot}` && node.dataset.chordPhrase === String(pi))?.focus({ preventScroll: true });
  }
  function strum(symbol) {
    if (bridge().pauseAudio) bridge().pauseAudio();
    const ctx = audioContext();
    if (!ctx) return;
    const pitches = chordPitches(symbol).map((pitch) => within(pitch % 12, 55)).sort((a, b) => a - b);
    const bass = parseChord(symbol);
    pitches.forEach((pitch, i) => pluck(ctx, pitch, ctx.currentTime + 0.01 + i * 0.03, 1.1, 0.03));
    const tones = chordPitches(symbol);
    if (tones.length) pluck(ctx, within(tones[{ 1: 0, 3: 1, 5: 2, 7: 3 }[bass.bass] || 0] % 12, 36), ctx.currentTime + 0.01, 1.2, 0.08, "bass");
  }
  function commitChords(bars, message, label = "Change a chord") {
    const p = phrase();
    if (!p) return;
    if (JSON.stringify(bars) === JSON.stringify(lineChords(p))) { paint(); return; }
    commit(scopedPath("chords", p), bars, label);
    announce(message);
  }
  function setChord(symbol) {
    const p = phrase(), at = state.chord;
    if (!p || !at || !parseChord(symbol)) return;
    const bars = lineChords(p);
    bars[at.bar][at.slot] = symbol;
    strum(symbol);
    commitChords(bars, `Bar ${at.bar + 1}: ${symbol}. The band, the voices and the sketch follow ${where("chords", p) === "line" ? "everywhere this line is sung" : "here"}.`);
  }
  function setChordsInBar(count) {
    const p = phrase(), at = state.chord;
    if (!p || !at) return;
    const bars = lineChords(p), old = bars[at.bar];
    // each new chord is the one sounding where it starts: splitting a bar adds a chord to change; joining keeps the first
    bars[at.bar] = Array.from({ length: count }, (_, j) => old[Math.floor(j * old.length / count)]);
    state.chord = { bar: at.bar, slot: Math.min(at.slot * count / old.length | 0, count - 1) };
    commitChords(bars, count > old.length ? "Bar split: change the new chord to add a passing chord." : "Bar joined.", count > old.length ? "Split a bar" : "Join a bar");
  }
  function chordCard() {
    const p = phrase(), h = chosenChord(p), c = composition(), choices = c?.chord_choices;
    if (!p || !h || !choices) return null;
    const parts = parseChord(h.symbol) || { root: "I", quality: "", bass: 1 };
    const counts = c.chords_per_bar || [1];
    const words = p.notes.filter((_, i) => h.rubs?.includes(i))
      .map((n) => displayWords(n.syllable).replace(/[^\p{L}\p{N}'’-]+$/u, "") || pitchName(pitchFor(n)));
    const rub = (h.rubs?.length
      ? `${h.rubs.length} sung note${h.rubs.length === 1 ? "" : "s"} over it ${h.rubs.length === 1 ? "isn't" : "aren't"} in the chord (${words.join(", ")})${h.hard && !h.tension?.length ? ", one a half step from it: a sharp rub" : ": passing notes, as folk harmony has them"}.`
      : "Every sung note over it is in the chord.")
      // a person's seventh (sixth, ninth) a half step from the tune: its own sharp rub
      + (h.tension?.length ? ` The chord's ${{ 9: "sixth", 14: "ninth", 2: "ninth" }[(QUALITIES[parts.quality] || [])[3]] || "seventh"} is a half step from the tune here (${p.notes.filter((_, i) => h.tension.includes(i)).map((n) => displayWords(n.syllable).replace(/[^\p{L}\p{N}'’-]+$/u, "") || pitchName(pitchFor(n))).join(", ")}): a sharp rub.` : "");
    const repeats = p.appearances || sections().flatMap((s) => s.phrases || []).filter((item) => item.id === p.id).length;
    const scope = where("chords", p);
    const reach = scope === "place" ? `These chords change only here, in ${section().label}.`
      : scope === "last" ? `These chords change in the last ${section().name}, however many there are.`
        : repeats > 1 ? `This line's chords change in all ${repeats} places it's sung${ownHere("chords", p) ? " (but this one, which has its own)" : ""}.` : "This line's chords change wherever it's sung.";
    return el("div", { class: "sbc-chord-card", role: "group", "aria-label": `Chord in bar ${h.bar + 1}` },
      scopeChoice("chords"),
      el("div", { class: "sbc-note-heading" }, el("span", { class: "sbc-overline" }, `Bar ${h.bar + 1} · chord ${h.slot + 1} of ${p.chords[h.bar].length}`),
        el("strong", { class: chordMine(p, h) ? "is-mine" : "" }, h.name),
        el("span", { class: `sbc-muted${h.hard ? " sbc-leap-warning" : ""}` }, rub)),
      el("div", { class: "sbc-chord-row" }, el("span", { class: "sbc-overline" }, "In the key"),
        el("div", { class: "sbc-button-group", role: "group", "aria-label": "Chords in the key" },
          choices.diatonic.map((d) => button(d.name, () => setChord(d.symbol), { class: `sbc-button${d.symbol.toUpperCase() === h.symbol.toUpperCase() ? " is-on" : ""}`,
            title: `${d.symbol}: ${d.name}`, "aria-pressed": d.symbol.toUpperCase() === h.symbol.toUpperCase() ? "true" : "false" })))),
      choices.sevenths?.length ? el("div", { class: "sbc-chord-row" }, el("span", { class: "sbc-overline" }, "Sevenths"),
        el("div", { class: "sbc-button-group", role: "group", "aria-label": "Seventh chords in the key" },
          choices.sevenths.map((d) => button(d.name, () => setChord(d.symbol), { class: `sbc-button${d.symbol.toUpperCase() === h.symbol.toUpperCase() ? " is-on" : ""}`,
            title: `${d.symbol}: ${d.name}`, "aria-pressed": d.symbol.toUpperCase() === h.symbol.toUpperCase() ? "true" : "false" })))) : null,
      el("div", { class: "sbc-chord-row" },
        select("Root", parts.root, choices.roots.map((r) => [r.numeral, `${r.numeral} · ${r.note}`]), (value) => setChord(chordSymbol({ ...parts, root: value })), { id: "sbc-chord-root" }),
        select("Quality", parts.quality, choices.qualities, (value) => setChord(chordSymbol({ ...parts, quality: value })), { id: "sbc-chord-quality" }),
        select("Bass", parts.bass, choices.basses.filter(([b]) => b !== 7 || WITH_SEVENTH.has(parts.quality)), (value) => setChord(chordSymbol({ ...parts, bass: Number(value) })), { id: "sbc-chord-bass" }),
        select("Chords in this bar", p.chords[h.bar].length, counts.map((n) => [n, String(n)]), (value) => setChordsInBar(Number(value)), { id: "sbc-chord-count" }),
        button("♪", () => strum(h.symbol), { class: "sbc-button sbc-audition", "aria-label": `Hear ${h.name}` })),
      el("div", { class: "sbc-chord-row" },
        el("span", { class: "sbc-muted" }, reach),
        button(scope === "line" ? "Restore chords" : "Restore chords here", () => { state.chord = null; commit(scopedPath("chords", p), null, "Restore the chords"); },
          { class: "sbc-button sbc-quiet", disabled: !held("chords", p),
            title: scope === "line" ? "Give this line back the song's own chords, everywhere" : "Give this place back the line's chords" }),
        button("Done", () => { state.chord = null; paint(); }, { class: "sbc-button sbc-quiet" })));
  }

  function inspector() {
    const p = phrase(), n = note(), b = bounds();
    if (!n) return el("div", { class: "sbc-inspector sbc-inspector-empty" }, el("span", { class: "sbc-inspector-icon", "aria-hidden": "true" }, "↖"),
      el("div", {}, el("strong", {}, "Make the melody yours"), el("p", { class: "sbc-muted" }, "Select a note to edit its pitch, position and length. Drag its right edge to resize.")));
    const index = state.note;
    const previous = n.slur ? p.notes[index - 1].onset + b.min_duration : index ? p.notes[index - 1].onset + p.notes[index - 1].duration : b.min_onset;
    const next = index < p.notes.length - 1 ? p.notes[index + 1].onset : b.max_end;
    const last = index === p.notes.length - 1;
    // every semitone where the note may carry a half step (spelled as a move there would spell it), else the scale's
    const pitches = [], here = semiOf(n);
    if (chromatic(p, n)) {
      for (let semi = scaleOffset(b.min_degree); semi <= scaleOffset(b.max_degree); semi++) {
        const at = semi === here ? { degree: n.degree, alter: n.alter || 0 } : M().spell(semi, scale(), semi > here);
        pitches.push([`${at.degree}${sign(at.alter)}`, `${pitchName((composition()?.tonic || 60) + semi)} · ${sign(at.alter)}${degreeName(at.degree)}`]);
      }
    } else {
      for (let degree = b.min_degree; degree <= b.max_degree; degree++) pitches.push([degree, `${pitchName(pitchFor(n, degree))} · ${degreeName(degree)}`]);
    }
    return el("div", { class: "sbc-inspector" },
      el("div", { class: "sbc-note-heading" }, el("span", { class: "sbc-overline" }, `Note ${index + 1} of ${p.notes.length}`),
        el("strong", {}, displayWords(n.word || n.syllable) || "Melody note"), last ? el("span", { class: "sbc-cadence-label" }, "Phrase ending") : null),
      select("Pitch", `${n.degree}${chromatic(p, n) ? sign(n.alter) : ""}`, pitches, (value) => {
        const [, degree, mark] = /^(-?\d+)(♯|♭)?$/.exec(value) || [];
        if (degree !== undefined) changeNote({ degree: Number(degree), alter: mark === "♯" ? 1 : mark === "♭" ? -1 : 0 });
      }, { id: "sbc-note-pitch", "aria-label": "Pitch" }),
      number("Start", n.onset, previous, round(Math.min(n.slur ? n.onset + n.duration - b.min_duration : next - n.duration, last ? b.max_final_onset ?? b.max_end : b.max_end)), b.grid, (value) => changeNote({ onset: value }, b.grid), { id: "sbc-note-start", "aria-label": "Start · beats" }),
      number("Length", n.duration, b.min_duration, round(next - n.onset), b.grid, (value) => changeNote({ duration: value }, b.grid), { id: "sbc-note-length", "aria-label": "Length · beats" }),
      button("♪", () => audition(pitchFor(n)), { class: "sbc-button sbc-audition", "aria-label": `Hear ${pitchName(pitchFor(n))}` }),
      // a melisma: a note split in two sings its syllable on, and a slurred note joins the one before again
      el("div", { class: "sbc-button-group", role: "group", "aria-label": "Notes on one syllable" },
        button("Split", splitNote, { title: "Split this note in two, the second sung on the same syllable (a melisma)" }),
        n.slur ? button("Join", joinNote, { title: "Join this note into the one before it" }) : null,
        // a line's own count (docs/notes/OWN-COUNT-LINES.md): a syllable more, or one fewer, with words for them
        p.own_path ? button("New syllable", newSyllable, { title: "Split this note in two, the second a syllable of its own" }) : null,
        p.own_path && !n.slur && index ? button("Merge", mergeSyllable, { title: "Sing this note on the syllable before" }) : null));
  }
  function health() {
    const p = phrase(), notes = p.notes, degrees = notes.map((n) => n.degree);
    const pitches = notes.map((n) => pitchFor(n));
    const largest = Math.max(0, ...degrees.slice(1).map((degree, i) => Math.abs(degree - degrees[i])));
    const repeats = sections().flatMap((s) => s.phrases || []).filter((item) => item.id === p.id).length;
    return el("div", { class: "sbc-health" },
      el("span", {}, el("span", { class: "sbc-health-dot", "aria-hidden": "true" }, "●"), `${notes.filter((n) => !n.slur).length} syllables${notes.some((n) => n.slur) ? `, ${notes.filter((n) => n.slur).length} slurred on (a melisma)` : ""}`),
      el("span", {}, `Range ${pitchName(Math.min(...pitches))}–${pitchName(Math.max(...pitches))}`),
      el("span", { class: largest > 4 ? "sbc-leap-warning" : "" }, largest > 4 ? `Wide leap: ${largest} scale steps` : "Comfortable melodic steps"),
      el("span", {}, `${repeats} shared ${repeats === 1 ? "appearance" : "appearances"}`),
      ...(p.advice || []).map((text) => el("span", { class: "sbc-advice" }, text))); // a freed ending, said
  }
  function editor() {
    state.snap = M().snapFor(state.snap, M().SNAPS);
    const p = phrase();
    if (!drawable(p)) return el("p", { class: "sbc-muted" }, "This section has no editable melody.");
    return el("div", { class: "sbc-editor" },
      el("div", { class: "sbc-row sbc-editor-heading" },
        el("div", {}, el("h3", {}, section().label, el("span", { class: "sbc-muted" }, " / Melody")), el("p", { class: "sbc-muted" }, where("tune") === "line" ? "Edit a phrase once; every appearance follows." : "This change stays in this place.")),
        el("div", { class: "sbc-editor-settings" }, select("Snap", state.snap, M().SNAPS.map(([v, name]) => [v, `${name} beat`]), (value) => { state.snap = Number(value); paint(); }, { id: "sbc-snap" }),
          select("Zoom", state.zoom, ZOOMS, (value) => { state.zoom = M().zoomOf(value); paint(); }, { id: "sbc-zoom" }))),
      phraseStrip(), scopeChoice("tune"), editTools(), pianoRoll(), ownCard(), state.chord && state.note === null ? null : inspector(), chordCard(),
      el("div", { class: "sbc-tools" }, el("span", { class: "sbc-overline" }, "Shape phrase"),
        el("div", { class: "sbc-button-group", role: "group", "aria-label": "Transpose phrase" },
          button("↓ Step", () => transpose(-1), { title: "Transpose the whole phrase down one scale step" }),
          button("↑ Step", () => transpose(1), { title: "Transpose the whole phrase up one scale step" })),
        button("Soften leaps", smoothMelody, { title: "Bring notes within two scale steps of their neighbors, preserving the ending" }),
        button("Even rhythm", evenRhythm, { title: "Spread the existing syllables evenly across their current phrase span" }),
        button(where("tune", p) === "line" ? "Restore phrase" : "Restore phrase here", () => { state.note = null; commit(scopedPath("tune", p), null, "Restore the phrase"); }, { class: "sbc-button sbc-quiet", title: where("tune", p) === "line" ? "Remove your melody override and restore this song’s inherited phrase" : "Give this place back the line's own tune" })),
      p.notes.length ? health() : null,
      el("p", { id: "sbc-drag-value", class: "sbc-visually-hidden", "aria-live": "off" }));
  }

  // Lightweight synthesized audition. All timing is in score beats, so tempo
  // changes remain meaningful and nothing extra needs to travel with the song.
  function audioContext() {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) { bridge().toast?.("This browser cannot play the instant sketch. Use Hear sung section instead."); return null; }
    if (!state.context || state.context.state === "closed") state.context = new Context();
    if (state.context.state === "suspended") state.context.resume().catch(() => bridge().toast?.("Audio is paused by your browser. Press Play sketch again."));
    return state.context;
  }
  // Every voice of the sketch goes through one bus, so a stop fades them all out together (a note cut mid-wave
  // clicks): FADE seconds down to silence, then the oscillators stop. A new bus for what plays next.
  const FADE = 0.02;
  function bus(ctx) {
    if (state.bus?.context === ctx) return state.bus.node;
    const node = ctx.createGain();
    node.gain.setValueAtTime(0, ctx.currentTime);
    node.gain.linearRampToValueAtTime(1, ctx.currentTime + 0.005);  // and in, as gently
    node.connect(ctx.destination);
    state.bus = { context: ctx, node };
    return node;
  }
  function fadeOut() {  // the bus to silence and every oscillator stopped after it; returns when that is
    const ctx = state.context, b = state.bus;
    state.bus = null;
    const nodes = [...state.nodes];
    state.nodes.clear();
    if (!ctx) return 0;
    const t = ctx.currentTime, end = t + FADE;
    if (b) {
      const g = b.node.gain;
      g.cancelScheduledValues?.(t);
      g.setValueAtTime(g.value ?? 1, t);
      g.linearRampToValueAtTime(0, end);
    }
    for (const oscillator of nodes) { try { oscillator.stop(end + 0.005); } catch (_) { /* already ended */ } }
    if (b) setTimeout(() => { try { b.node.disconnect(); } catch (_) { /* gone */ } }, (FADE + 0.05) * 1000);
    return end;
  }
  function tone(ctx, pitch, start, duration, click = false, velocity = 96) {
    const oscillator = ctx.createOscillator(), gain = ctx.createGain();
    oscillator.type = click ? "sine" : "triangle";
    oscillator.frequency.value = click ? pitch : 440 * 2 ** ((pitch - 69) / 12);
    const length = Math.max(0.06, duration);
    const level = click ? 1 : clamp(velocity / 96, 1 / 96, 127 / 96);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(click ? 0.035 : 0.075 * level, start + 0.009);
    gain.gain.exponentialRampToValueAtTime(0.018 * level, start + Math.min(0.12, length * 0.4));
    gain.gain.setValueAtTime(0.018 * level, start + Math.max(0.02, length - 0.05));
    gain.gain.linearRampToValueAtTime(0.0001, start + length);
    oscillator.connect(gain); gain.connect(bus(ctx));
    state.nodes.add(oscillator);
    oscillator.onended = () => { state.nodes.delete(oscillator); oscillator.disconnect(); gain.disconnect(); };
    oscillator.start(start); oscillator.stop(start + length + 0.025);
  }
  // The sketch's band: a plain strum on each beat of a chord (the first one fuller) and a bass on its first
  // beat, the fifth halfway through a long one. Voiced from the chord's pitch classes: the triad between G3
  // and F#4, the bass between C2 and B2.
  const within = (pc, low) => low + (((pc - low) % 12) + 12) % 12;
  // The band's notes for one chord, in seconds from its cycle's start: what this page plucks and what
  // players.js sends to a MIDI channel are the same notes.
  function backingNotes(chord, seconds) {
    const out = [], beats = Math.max(1, Math.round(chord.duration));
    for (let k = 0; k < beats; k++) {
      const t = (chord.beat + k) * seconds, length = Math.min(chord.duration - k, 1) * seconds;
      if (chord.pcs.length) {
        chord.pcs.map((pc) => within(pc, 55)).sort((a, b) => a - b).forEach((pitch, i) =>
          out.push({ player: "chords", t, spread: i * 0.012, d: Math.max(0.12, length * 0.95), pitch, peak: k ? 0.013 : 0.02 }));
      }
      if (chord.bass !== undefined && (k === 0 || (beats >= 4 && k === beats / 2))) {
        const pc = k === 0 ? chord.bass : chord.pcs[2] ?? chord.bass;
        out.push({ player: "bass", t, spread: 0, d: Math.max(0.2, Math.min(2, chord.duration - k) * seconds * 0.9),
          pitch: within(pc, 36), peak: 0.07, kind: "bass" });
      }
    }
    return out;
  }
  function backing(ctx, chord, offset, seconds) {
    for (const n of backingNotes(chord, seconds)) {
      if (!included(n.player) || route(n.player) !== "page") continue;
      const start = offset + n.t;
      if (start < ctx.currentTime - 0.01) continue;
      pluck(ctx, n.pitch, Math.max(ctx.currentTime, start) + n.spread, n.d, n.peak, n.kind);
    }
  }
  // ---- the sketch's players on a musician's own instruments (players.js: MIDI out), when it is on the page
  const players = () => window.SongbirdPlayers;
  const route = (player) => players()?.route?.(player) || "page"; // "page", "midi" or "off"
  const included = (player) => (player === "chords" ? state.chords : player === "bass" ? state.bass : true);
  function sketchNotes(sequence, seconds) { // everything the sketch plays itself, for players.js to send
    const out = sequence.events.map((e) => ({ player: "tune", t: e.beat * seconds,
      d: Math.max(0.07, e.duration * seconds * 0.88), key: e.pitch, vel: 96 }));
    for (const chord of sequence.harmony || []) {
      for (const n of backingNotes(chord, seconds)) {
        if (included(n.player)) out.push({ player: n.player, t: n.t + n.spread, d: n.d, key: n.pitch, vel: n.player === "bass" ? 96 : n.peak > 0.015 ? 84 : 64 });
      }
    }
    return out;
  }
  function bandSound(note, when) { // a band part players.js has this page play: a pluck, or a drum's tap
    const ctx = state.context;
    if (!ctx || !state.playback) return;
    if (note.drums) tone(ctx, note.key < 40 ? 90 : note.key < 50 ? 220 : 2400, when, 0.05, true);
    else pluck(ctx, note.key, when, Math.max(0.08, note.d), 0.012 * (note.vel / 100), note.key < 48 ? "bass" : "strum");
  }
  function pluck(ctx, pitch, start, duration, peak, kind = "strum") {
    const oscillator = ctx.createOscillator(), gain = ctx.createGain();
    oscillator.type = kind === "bass" ? "triangle" : "sawtooth";
    oscillator.frequency.value = 440 * 2 ** ((pitch - 69) / 12);
    let out = oscillator;
    if (ctx.createBiquadFilter) {  // soften the strings' edge; the bass stays round
      const filter = ctx.createBiquadFilter();
      filter.type = "lowpass"; filter.frequency.value = kind === "bass" ? 700 : 1500;
      oscillator.connect(filter); out = filter;
    }
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(peak, start + 0.006);
    gain.gain.exponentialRampToValueAtTime(peak * 0.25, start + Math.min(0.25, duration * 0.5));
    gain.gain.linearRampToValueAtTime(0.0001, start + duration);
    out.connect(gain); gain.connect(bus(ctx));
    state.nodes.add(oscillator);
    oscillator.onended = () => { state.nodes.delete(oscillator); oscillator.disconnect(); if (out !== oscillator) out.disconnect(); gain.disconnect(); };
    oscillator.start(start); oscillator.stop(start + duration + 0.03);
  }
  // a note heard alone: over a sung loop playing (live.js), which goes on; else the rendered audio stops for it
  const quietly = () => !!bridge().liveLooping?.();
  function audition(pitch) {
    if (quietly()) { /* the loop goes on under it */ }
    else if (bridge().pauseAudio) bridge().pauseAudio();
    else document.getElementById("audio")?.pause();
    const ctx = audioContext();
    if (ctx) tone(ctx, pitch, ctx.currentTime + 0.005, 0.3);
  }
  // A player's note heard alone (a key of its roll, a note chosen or just written, a drum's row): in the player's
  // own sound where the studio has it at once (live.js samples), else the sketch's; over a sung loop, which goes on.
  // notes: [onset, length, pitch (a drum's piece), velocity], sounded together (at most four).
  function sounded(notes, drummer = null) {
    if (!quietly()) bridge().pauseAudio?.();
    const ctx = audioContext();
    if (!ctx) return;
    const unit = 60 / composition().tempo;
    for (const [, length, pitch, velocity = 96] of notes.slice(0, 4)) {
      if (bridge().note?.(state.player, pitch, velocity)) continue;
      if (drummer) for (const node of window.SongbirdDrums.play(ctx, [[0, length, pitch, velocity]], drummer, composition().tempo, bus(ctx))) state.nodes.add(node);
      else tone(ctx, composition().tonic + pitch, ctx.currentTime + 0.005, Math.min(0.6, Math.max(0.12, length / 96 * unit)), false, velocity);
    }
  }
  // the notes the roll will likely sound next, asked of the studio once a section and player (where it makes them)
  function prefetch(s, drummer, heard = []) {
    const key = `${s.id}|${state.player}`;
    if (state.prefetched === key || !bridge().prefetch) return;
    state.prefetched = key;
    const pitches = drummer ? (drummer.drums || []).map((_, i) => i) : window.SongbirdLive?.octaveAround(heard) || [];
    Promise.resolve(bridge().prefetch(state.player, pitches)).catch(() => {});
  }
  function playbackSequence() {
    // the score's transport may play a section it hasn't opened (playIndex), or the song from its playhead (from)
    const target = sections()[state.playIndex ?? state.section] || section();
    const chosen = state.scope === "song" ? sections() : [target];
    const phrases = state.scope === "phrase" ? [phrase()] : chosen.flatMap((s) => s.phrases || []);
    let origin = state.scope === "phrase" ? phrase().start_beat + bounds().min_onset
      : Math.min(chosen[0].start_beat, ...phrases.map((p) => p.start_beat - (p.pickup_beats || 0)));
    let first = state.scope === "phrase" ? phrase().start_beat : chosen[0].start_beat;  // its first bar line (a pickup before)
    const end = state.scope === "phrase" ? phrase().start_beat + bounds().max_end
      : chosen.at(-1).start_beat + chosen.at(-1).duration_beats;
    let events = phrases.flatMap((p) => p.notes.map((n) => ({ beat: p.start_beat + n.onset - origin, duration: n.duration,
      pitch: pitchFor(n), phrase: p.id }))).sort((a, b) => a.beat - b.beat);
    // the chords under the tune as the band lays them out: each where it starts in its line, for how long
    let harmony = phrases.flatMap((p) => (p.harmony || []).map((h) => ({ beat: p.start_beat + h.start - origin,
      duration: h.beats, pcs: h.pcs || [], bass: h.bass }))).filter((h) => h.beat >= -1e-9 && h.beat < end - origin - 1e-9);
    const cut = state.scope === "song" && state.from !== null && state.from !== undefined ? state.from - origin : 0;
    if (cut > 0 && cut < end - origin - 0.25) { // from the playhead: what starts before it is left out, a chord ringing across it shortened
      events = events.filter((e) => e.beat >= cut - 1e-9).map((e) => ({ ...e, beat: e.beat - cut }));
      harmony = harmony.filter((h) => h.beat + h.duration > cut + 1e-9)
        .map((h) => ({ ...h, beat: Math.max(0, h.beat - cut), duration: h.duration - Math.max(0, cut - h.beat) }));
      origin += cut;
      first = origin;
    }
    return { origin, first, duration: Math.max(0.25, end - origin), events, harmony };
  }
  function togglePlay() { if (state.playback) { stop(); paint(); } else play(); }
  function play() {
    if (!phrase()) return;
    const ctx = audioContext();
    if (!ctx) return;
    // Keep the rendered vocal and the live sketch from sounding over each other.
    if (bridge().pauseAudio) bridge().pauseAudio();
    else document.getElementById("audio")?.pause();
    const sequence = playbackSequence(), seconds = 60 / composition().tempo;
    state.playback = { ...sequence, seconds, started: ctx.currentTime + 0.04, nextCycle: 0 };
    players()?.start?.({ ctx, started: state.playback.started, cycle: sequence.duration * seconds, loop: () => state.loop,
      seconds, origin: sequence.origin, span: sequence.duration, notes: sketchNotes(sequence, seconds), sound: bandSound });
    paint(); schedule();
  }
  function replay() { if (state.playback) { stop(); play(); } }
  function schedule() {
    const playback = state.playback, ctx = state.context;
    if (!playback || !ctx) return;
    const duration = playback.duration * playback.seconds;
    const elapsed = ctx.currentTime - playback.started;
    if (!state.loop && elapsed >= duration) { stop(); paint(); return; }
    const cycle = Math.max(0, Math.floor(elapsed / duration));
    // Schedule one loop ahead, avoiding audible gaps while bounding the number
    // of live nodes even when the user leaves the editor open for hours.
    while (playback.nextCycle <= cycle + (state.loop ? 1 : 0)) {
      const offset = playback.started + playback.nextCycle * duration;
      for (const event of route("tune") === "page" ? playback.events : []) {
        const start = offset + event.beat * playback.seconds;
        if (start >= ctx.currentTime - 0.01) tone(ctx, event.pitch, Math.max(ctx.currentTime, start), Math.max(0.07, event.duration * playback.seconds * 0.88));
      }
      for (const chord of playback.harmony || []) backing(ctx, chord, offset, playback.seconds);
      if (state.metronome) {
        // The pickup precedes beat one. Anchor clicks to the score's bar grid,
        // rather than treating the first playback instant as a downbeat.
        const scoreStart = songSpan().start, bar = composition().beats_per_bar;
        const firstBeat = Math.ceil(playback.origin - scoreStart - 1e-9);
        const endBeat = playback.origin + playback.duration - scoreStart;
        for (let beat = firstBeat; beat < endBeat - 1e-9; beat++) {
          const start = offset + (scoreStart + beat - playback.origin) * playback.seconds;
          const downbeat = ((beat % bar) + bar) % bar < 1e-9;
          if (start >= ctx.currentTime) tone(ctx, downbeat ? 1200 : 800, start, 0.045, true);
        }
      }
      playback.nextCycle++;
    }
    const absoluteBeat = playback.origin + (Math.max(0, elapsed) % duration) / playback.seconds;
    const g = sectionGeometry(), localBeat = absoluteBeat - (section()?.start_beat || 0);
    const cursor = document.getElementById("sbc-playhead");
    if (cursor) { cursor.hidden = localBeat < g.start || localBeat > g.end; cursor.style.left = `${xAt(g, localBeat)}px`; }
    const currentSection = sections().findIndex((s) => absoluteBeat >= s.start_beat && absoluteBeat < s.start_beat + s.duration_beats);
    root()?.querySelectorAll(".sbc-section").forEach((node) => node.classList.toggle("is-playing", Number(node.dataset.section) === currentSection));
    root()?.querySelectorAll(".sbc-overview-section").forEach((node) => node.classList.toggle("is-playing", Number(node.dataset.overviewSection) === currentSection));
    const songCursor = document.getElementById("sbc-song-playhead"), span = songSpan();
    if (songCursor) { songCursor.hidden = false; songCursor.style.left = `${clamp((absoluteBeat - span.start) / span.duration * 100, 0, 100)}%`; }
    // the score's transport says the bar being played, a pickup into what's played as its first (score.js reads the
    // beat on its ruler: M.sketchOffset)
    page()?.tick?.(Math.max(absoluteBeat, playback.first), (elapsed % duration) / duration);
    state.frame = requestAnimationFrame(schedule);
  }
  function stop() {
    players()?.stop?.(); // every note sent to an instrument ends with the sketch
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = null; state.playback = null;
    fadeOut();
    const play = document.getElementById("sbc-play");
    if (play) { play.textContent = "▶ Play sketch"; play.setAttribute("aria-pressed", "false"); }
    const cursor = document.getElementById("sbc-playhead");
    if (cursor) cursor.hidden = true;
    const songCursor = document.getElementById("sbc-song-playhead");
    if (songCursor) songCursor.hidden = true;
    root()?.querySelectorAll(".is-playing").forEach((node) => node.classList.remove("is-playing"));
    page()?.tick?.(null);
  }
  // ---- the score's notes (index.html): the heading with the scope switch, snap and zoom, the phrase strip, the
  // roll; the selected note's or chord's card is drawn by the page's inspector from noteState() and chordState()
  function scopeSwitch(kind) {
    const p = phrase(), s = section();
    if (kind === "tune" && (p?.own || state.draft)) return el("span", { class: "hint" }, "Words and melody · this lyric line");
    const options = window.SongbirdModel?.scopeOptions(p, s) || [];
    if (!options.length) return null;
    const now = where(kind, p);
    return el("span", { class: "switch scope", role: "group", "aria-label": kind === "tune" ? "Where a change to the tune applies" : "Where a change to the chords applies" },
      options.map((o) => el("button", { type: "button", "aria-pressed": String(o.id === now), id: `sbc-scope-${kind}-${o.id}`,
        onclick: () => { state.where[kind] = o.id; paint(); told(); } }, o.label)));
  }
  const scrollTo = (x) => { state.scrollTo = x; };  // where the roll is scrolled to once it is drawn
  // the snaps this roll offers (an instrument's and a drum's ⅙ too), and the snap kept to one of them
  const snaps = () => (state.player === "voice" ? M().SNAPS : M().PART_SNAPS);
  const snapName = () => (M().PART_SNAPS.find(([v]) => Math.abs(v - state.snap) < 1e-9)?.[1] ?? fmt(state.snap));
  // a section in a six feel opens on a snap of thirds (model.js feelSnap)
  function feel(s = section()) {
    state.snap = M().feelSnap((s?.phrases || []).flatMap((p) => (p.notes || []).flatMap((n) => [n.onset, n.duration])), state.snap);
  }
  function notesPanel() {
    state.snap = M().snapFor(state.snap, snaps());
    const s = section(), p = phrase();
    const part = state.player !== "voice" && window.SongbirdParts;
    const drummer = part ? (composition().players || []).find((x) => x.name === state.player && x.drums) : null;
    return el("div", { class: "sbc-notes" },
      el("div", { class: "notes-head" },
        el("h3", { id: "notesTitle", tabindex: "-1" }, s.label),
        select("Part", state.player, (composition().players || [{ name: "voice", label: "Melody" }]).map((p) =>
          [p.name, p.name === "voice" ? "Melody" : p.label]), (value) => {
          stop(); state.player = value; state.note = null; state.chord = null;
          window.SongbirdParts?.reset?.(); window.SongbirdDrums?.reset?.(); paint(); told();
          page()?.partChosen?.(value);  // the grid's row follows: the Part menu is a second way to choose it
        }, { id: "sbc-part" }),
        part ? el("span", { class: "hint" }, "This section only") : scopeSwitch("tune"),
        el("span", { class: "settings" }, select("Snap", state.snap, snaps(), (value) => { state.snap = Number(value); paint(); }, { id: "sbc-snap" }),
          select("Zoom", state.zoom, ZOOMS, (value) => { state.zoom = M().zoomOf(value); paint(); }, { id: "sbc-zoom" })),
        button("Close", () => page()?.closeNotes?.(), { class: "sbc-button sbc-quiet", id: "sbc-close", title: "Close the notes (Esc)" }),
        !part && p?.notes?.length ? health() : null),
      (s.phrases || []).length ? phraseStrip() : null,
      // a percussion player's part is a step grid of its pieces over the section (drums.js), as the instrument's roll is
      drummer && window.SongbirdDrums ? window.SongbirdDrums.render(state.view, s, state.player, { snap: state.snap, zoom: state.zoom, paint, phrase: state.phrase, scrollTo,
        choose: (q) => { const i = (s.phrases || []).indexOf(q); if (i >= 0) { state.phrase = i; state.note = null; state.chord = null; } },
        hear: (notes) => {
          stop(); bridge().pauseAudio?.(); const ctx = audioContext(); if (!ctx) return;
          for (const node of window.SongbirdDrums.play(ctx, notes, drummer, composition().tempo, bus(ctx))) state.nodes.add(node);
        },
        // a row's name, or strokes just struck: at once, over the loop (live.js: the kit's own sound where it's here)
        sound: (notes) => sounded(notes, drummer), ready: () => prefetch(s, drummer) })
      : part ? window.SongbirdParts.render(state.view, s, state.player, { snap: state.snap, zoom: state.zoom, paint, phrase: state.phrase, scrollTo,
        // a note of another phrase chosen in the instrument's roll: that phrase is the one the strip and ▶ mean
        choose: (q) => { const i = (s.phrases || []).indexOf(q); if (i >= 0) { state.phrase = i; state.note = null; state.chord = null; } },
        hear: (notes, q = p) => {
          stop(); bridge().pauseAudio?.(); const ctx = audioContext(); if (!ctx) return;
          const unit = 60 / composition().tempo, origin = Math.min(0, ...notes.map((n) => n[0] / 96));
          for (const [start, length, pitch, velocity] of notes) tone(ctx, composition().tonic + pitch,
            ctx.currentTime + 0.03 + (start / 96 - origin) * unit, Math.min(length / 96, (q?.duration_beats ?? 4) - start / 96) * unit, false, velocity);
        },
        // a key, a note chosen, or notes just written: at once, over the loop (the instrument's own sound where it's here)
        sound: (notes) => sounded(notes), ready: (pitches) => prefetch(s, null, pitches) }) : el("div", {},
      p?.notes?.length ? editTools() : null,
      (s.phrases || []).some(drawable) ? pianoRoll() : el("p", { class: "sbc-muted notes-foot" }, "This section has no melody to change."),
      ownCard(),
      M().isBlank(p) && !state.draft ? el("div", { class: "notes-foot" }, button("Write words", writeLine, { class: "sbc-button", title: "Its words, with notes fitted to them" })) : null,
      el("p", { class: "readonly hint notes-foot" }, "Tap a note to change it in the column."),
      el("div", { class: "notes-foot" }, el("span", { title: "Arrow keys move the selected notes; ⇧ ← → a note's length; Delete removes; Ctrl or ⌘ with C, X, V, D, A: copy, cut, paste, duplicate, select all." }, "Drag on the grid to draw a note; Shift-drag to select."),
        p?.notes?.length ? button("▶ Hear this phrase", () => { state.scope = "phrase"; state.playIndex = null; play(); }, { class: "sbc-button" }) : null),
      el("p", { id: "sbc-drag-value", class: "sbc-visually-hidden", "aria-live": "off" })));
  }
  function reasons(mine, yours, theirs) { return mine ? [["you", yours]] : theirs; }
  function noteState() {
    const p = phrase(), n = note();
    if (!p || !n) return null;
    const index = state.note, last = index === p.notes.length - 1;
    const name = pitchName(pitchFor(n));
    const scope = where("tune", p);
    return {
      rubric: several() ? `${picked().length} of ${p.notes.length} notes` : `Note ${index + 1} of ${p.notes.length}`,
      set: `“${displayWords(n.slur ? n.word : n.syllable) || "♪"}”${n.slur ? ", held on" : ""} · ${name} · scale degree ${sign(n.alter)}${n.degree}${last ? " · the phrase's ending" : ""}${n.edited ? " · yours" : ""}`,
      mine: !!n.edited,
      body: el("div", { class: "sbc-note-state" }, (() => { const box = inspector(); box.querySelector(".sbc-audition")?.remove(); return box; })(),  // ▶ Hear it plays the note
        el("h4", {}, "The phrase"),
        el("div", { class: "sbc-chord-row" },
          button("↓ Step", () => transpose(-1), { title: "Transpose the whole phrase down one scale step" }),
          button("↑ Step", () => transpose(1), { title: "Transpose the whole phrase up one scale step" }),
          scopeSwitch("tune")),
        el("details", {}, el("summary", {}, "more"),
          el("div", { class: "sbc-chord-row" },
            button("Soften leaps", smoothMelody, { title: "Bring notes within two scale steps of their neighbours, keeping the ending" }),
            button("Even rhythm", evenRhythm, { title: `Even the notes on the phrase's own grid (the snap: ${snapName()} beat)` })))),
      why: reasons(n.edited, p.own ? "your words and melody, wherever this lyric line occurs" : scope === "line" ? "yours: this line is sung this way everywhere" : "yours, in this place only",
        [["song", "the tune as it was written, and as the versions before have sung it"], ["rule", "notes and words are kept together; gaps between notes are rests"]]),
      release: p.own ? { label: "Use the tune's line", disabled: false,
        action: () => { state.note = null; state.draft = null; commit(p.own_path, null, "Use the tune's line"); told(); } }
        : { label: scope === "line" ? "Reset" : "Reset here", disabled: !held("tune", p),
        action: () => { state.note = null; commit(scopedPath("tune", p), null, "Restore the phrase"); told(); } },
      hear: () => audition(pitchFor(n)),
    };
  }
  function chordState() {
    const p = phrase(), h = chosenChord(p);
    if (!p || !h) return null;
    const card = chordCard(), mine = chordMine(p, h), scope = where("chords", p);
    const body = card ? el("div", { class: "sbc-chord-state" }, ...[...card.children].filter((x) => !x.classList.contains("sbc-scope") && !x.classList.contains("sbc-note-heading"))) : null;
    body?.querySelectorAll("button").forEach((b) => { if (b.textContent === "Done" || /^Restore chords/.test(b.textContent)) b.remove(); });
    // where the change reaches is the scope's own row (Applies): its sentence, alone once its buttons went, goes
    body?.querySelectorAll(".sbc-audition").forEach((b) => b.remove());  // ▶ Hear it, in the foot, strums it
    body?.querySelectorAll(".sbc-chord-row").forEach((r) => { if (!r.querySelector("button, select")) r.remove(); });
    const rub = card?.querySelector(".sbc-note-heading .sbc-muted")?.textContent || "";
    return {
      rubric: `Bar ${h.bar + 1} · chord ${h.slot + 1} of ${p.chords[h.bar].length}`,
      set: `${h.name}${mine ? ", yours" : ", the song's own"}. ${rub}`,
      mine, scope: scopeSwitch("chords"), body,
      why: reasons(mine, scope === "line" ? "yours: this line's chords, everywhere it's sung" : "yours, in this place only",
        [["song", "the song's own harmony, as it was written"], ["rule", "the band, the voices before and the backing voices follow it; the tune stays"]]),
      release: { label: scope === "line" ? "Reset" : "Reset here", disabled: !held("chords", p),
        action: () => { state.chord = null; commit(scopedPath("chords", p), null, "Restore the chords"); told(); } },
      hear: () => strum(h.symbol),
    };
  }

  function paint() {
    const box = root(), c = composition();
    if (!box || !c) return;
    const focused = box.contains(document.activeElement) ? document.activeElement : null;
    const focusId = focused?.id, focusNote = focused?.dataset.note, focusPhrase = focused?.dataset.phrase, focusPart = focused?.dataset.partNote, focusAction = focused?.dataset.composerAction;
    const scroll = box.querySelector(".sbc-roll-scroll")?.scrollLeft || 0;
    const scrollTop = box.querySelector(".sbc-roll-scroll")?.scrollTop || 0;
    const arrangeScroll = box.querySelector(".sbc-arrangement-scroll")?.scrollLeft || 0;
    box.classList.add("sbc-composer");
    if (notesMode()) box.replaceChildren(section() ? notesPanel() : "",
      el("div", { id: "sbc-status", class: "sbc-visually-hidden", role: "status", "aria-live": "polite" }));
    else box.replaceChildren(transport(), arrangement(), section() ? editor() : null,
      el("div", { id: "sbc-status", class: "sbc-visually-hidden", role: "status", "aria-live": "polite" }));
    const roll = box.querySelector(".sbc-roll-scroll"); if (roll) { roll.scrollLeft = state.scrollTo ?? scroll; roll.scrollTop = scrollTop; }
    state.scrollTo = null;
    const arrange = box.querySelector(".sbc-arrangement-scroll"); if (arrange) arrange.scrollLeft = arrangeScroll;
    const restore = focusPart !== undefined ? box.querySelector(`[data-part-note="${focusPart}"]`)
      : focusNote !== undefined ? noteNode(focusPhrase, focusNote)
      : focusId ? document.getElementById(focusId)
        : focusAction ? [...box.querySelectorAll("button")].find((node) => node.dataset.composerAction === focusAction) : null;
    const partKey = state.player !== "voice" ? window.SongbirdParts?.focus?.() : null;  // an instrument's note, after its edit
    if (partKey) window.SongbirdParts.focused();
    const drawn = state.focusNote ? noteNode(state.phrase, state.note)
      : partKey ? [...box.querySelectorAll(".sbc-note")].find((node) => node.dataset.partNote === partKey) : null;
    state.focusNote = false;
    (drawn || restore || (focused && noteNode(state.phrase, state.note)))?.focus({ preventScroll: true });
  }
  function render(view) {
    const changed = state.view !== view;
    if (changed) stop();
    state.view = view;
    if (state.player !== "voice" && !(composition()?.players || []).some((p) => p.name === state.player)) state.player = "voice";
    for (const s of sections()) for (const p of s.phrases || []) {
      const draft = drafts.get(p.own_path);
      if (draft && changed) {
        draft.was = p.notes;
        p.notes = draft.notes.map((n) => ({ ...n, pitch: (composition()?.tonic || 60) + scaleOffset(n.degree) + (n.alter || 0), edited: true }));
      }
    }
    players()?.viewChanged?.(view);
    const box = root();
    if (!view?.composition?.sections?.length) {
      if (box) box.replaceChildren(el("p", { class: "sbc-muted" }, "The arrangement will appear when the song is ready."));
      return;
    }
    if (state.section < 0) { state.section = Math.max(0, sections().findIndex((s) => s.phrases?.some(drawable))); feel(sections()[state.section]); }
    state.section = clamp(state.section, 0, sections().length - 1);
    state.phrase = clamp(state.phrase, 0, Math.max(0, (section().phrases?.length || 0) - 1));
    if (!drawable(phrase())) state.phrase = firstSung();  // a sung line first (a blank one, to draw into, if that's all there is)
    if (state.note !== null && state.note >= (phrase()?.notes?.length || 0)) state.note = null;
    if (state.chord && !(phrase()?.chords?.[state.chord.bar]?.length > state.chord.slot)) state.chord = null;
    paint();
  }
  window.addEventListener("pagehide", stop);
  // a browser that keeps the focus on the page when a note is clicked: the roll's shortcuts while notes are selected
  document.addEventListener?.("keydown", (event) => {
    if (event.target === document.body && picked().length && root()?.isConnected !== false && !document.getElementById("notes")?.hidden) shortcut(event);
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
  // for the score: open a section's notes, the selection's card, the sketch the transport drives
  function open(index, player = "voice") {
    state.player = (composition()?.players || []).some((p) => p.name === player) ? player : "voice";
    if (index === state.section && sections()[index]) { paint(); return; }
    stop(); state.section = clamp(index, 0, sections().length - 1); state.phrase = firstSung(); state.note = null; state.chord = null; state.cursor = null;
    state.where = { tune: null, chords: null }; feel(); paint();
  }
  function deselect() { if (state.note !== null || state.chord) { state.note = null; state.chord = null; paint(); } }
  function sketch({ scope = "section", index = null, from = null } = {}) {
    stop(); state.scope = scope; state.playIndex = index; state.from = from; play();
  }
  function options(o) {
    for (const k of ["loop", "metronome", "chords", "bass"]) if (k in o) state[k] = !!o[k];
    replay();
  }
  function selection() {
    return { section: sections()[state.section]?.id || null, phrase: state.phrase, note: state.note, chord: state.chord, player: state.player };
  }
  // the chords of the section open in the melody's harmony strip: its first chord chosen, its card in the column
  function chords() {
    const ps = section()?.phrases || [], k = Math.max(0, ps.findIndex((p) => p.chords?.length));
    const p = ps[k];
    if (!p?.chords?.length) return false;
    stop(); state.player = "voice"; state.phrase = k; state.note = null;
    const first = (p.harmony?.length ? p.harmony : [{ bar: 0, slot: 0, symbol: p.chords[0][0] }])[0];
    state.chord = { bar: first.bar, slot: first.slot }; state.reveal = true;
    paint(); told();
    [...(root()?.querySelectorAll(".sbc-chord") || [])].find((node) => node.dataset.chord === `${first.bar}.${first.slot}` && node.dataset.chordPhrase === String(k))?.focus({ preventScroll: true });
    return true;
  }
  window.SongbirdComposer = { render, stop, replay, open, deselect, sketch, options, selection, noteState, chordState, chords,
    hasDraft: (id) => sections().find((s) => s.id === id)?.phrases?.some((p) => drafts.has(p.own_path)) || false,
    playing: () => !!state.playback, mini: (index) => (sections()[index] ? miniNotes(sections()[index]) : null) };
})();
