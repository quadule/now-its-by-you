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
  const state = {
    view: null, section: -1, phrase: 0, note: null, snap: 0.25, zoom: 1,
    loop: false, metronome: false, scope: "phrase", drag: null, chords: true, bass: true, chord: null,
    context: null, playback: null, nodes: new Set(), frame: null,
  };
  const bridge = () => window.StudioBridge || {};
  const root = () => document.getElementById("studio-composer");
  const composition = () => state.view && state.view.composition;
  const sections = () => composition()?.sections || [];
  const section = () => sections()[state.section];
  const phrase = () => section()?.phrases?.[state.phrase];
  const note = () => phrase()?.notes?.[state.note];
  const round = (n) => Math.round(n * 10000) / 10000;
  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const fmt = (n) => Number.isInteger(n) ? String(n) : String(round(n));
  const beatLabel = (n) => n < 0 ? `pickup ${fmt(-n)}` : fmt(n + 1);
  const displayWords = (value) => String(value || "").replace(/\*/g, "");
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
  function pitchName(pitch) {
    const names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
    return `${names[((Math.round(pitch) % 12) + 12) % 12]}${Math.floor(pitch / 12) - 1}`;
  }
  function degreeName(degree) {
    const octave = Math.floor((degree - 1) / 7);
    return `${((degree - 1) % 7 + 7) % 7 + 1}${octave > 0 ? "′".repeat(octave) : octave < 0 ? "₋".repeat(-octave) : ""}`;
  }
  function noteTitle(n, index, p = phrase()) {
    return `${displayWords(n.syllable) || `Note ${index + 1}`}, ${pitchName(pitchFor(n))}, scale degree ${n.degree}, beat ${beatLabel(n.onset)}, ${fmt(n.duration)} beats${index === p.notes.length - 1 ? ", phrase ending" : ""}`;
  }
  function selectedSection(index) {
    stop(); state.section = clamp(index, 0, sections().length - 1); state.phrase = 0; state.note = null; state.chord = null; paint();
  }
  function selectedPhrase(index) {
    stop(); state.phrase = index; state.note = null; state.chord = null; paint();
  }
  function commit(path, value) {
    stop();
    if (value === null && bridge().releaseEdit) bridge().releaseEdit(path); // an inherited choice released, explicitly
    else if (bridge().setEdit) bridge().setEdit(path, value);
  }
  function serializeNotes(notes) {
    // Keep untouched expressive and compound-meter timing exact. A third of a
    // beat rounded for display can otherwise become a false syllable overlap.
    return notes.map((n) => ({ degree: n.degree, onset: n.onset, duration: n.duration }));
  }
  function commitNotes(notes, message) {
    const p = phrase();
    if (!p || !notes.length) return;
    if (notes.every((n, index) => n.degree === p.notes[index].degree && n.onset === p.notes[index].onset && n.duration === p.notes[index].duration)) {
      // A guarded drag or nudge can end exactly where it started. Pinning that
      // untouched phrase would unnecessarily stop its inherited evolution.
      paint();
      if (message) announce(message);
      return;
    }
    if (notes.some((n, index) => index && Math.abs(n.degree - notes[index - 1].degree) > Math.max(bounds(p).max_leap || 7, Math.abs(p.notes[index].degree - p.notes[index - 1].degree)))) {
      bridge().toast?.("That would make a leap wider than an octave. Try moving the neighboring note first."); return;
    }
    const updated = notes.map((n, index) => ({ ...n, pitch: pitchFor(p.notes[index], n.degree) }));
    for (const s of sections()) for (const shared of s.phrases || []) {
      if (shared.id === p.id) shared.notes = updated.map((n, index) => ({ ...shared.notes[index], ...n, syllable: shared.notes[index]?.syllable, word: shared.notes[index]?.word, edited: true }));
    }
    commit(p.path || `tune.${p.id}`, serializeNotes(updated));
    paint();
    if (message) announce(message);
  }
  function limitedNote(index, changes, p = phrase(), snap = state.snap) {
    const original = p.notes[index], b = bounds(p);
    const next = { ...original, ...changes };
    const grid = Math.max(b.grid, snap);
    const quantize = (value) => round(Math.round(value / grid) * grid);
    const previousEnd = index ? p.notes[index - 1].onset + p.notes[index - 1].duration : b.min_onset;
    const followingStart = index < p.notes.length - 1 ? p.notes[index + 1].onset : b.max_end;
    if ("degree" in changes) {
      const leap = b.max_leap || 7;
      const before = index ? p.notes[index - 1].degree : null;
      const after = index < p.notes.length - 1 ? p.notes[index + 1].degree : null;
      const low = Math.max(b.min_degree, before === null ? b.min_degree : before - Math.max(leap, Math.abs(original.degree - before)), after === null ? b.min_degree : after - Math.max(leap, Math.abs(original.degree - after)));
      const high = Math.min(b.max_degree, before === null ? b.max_degree : before + Math.max(leap, Math.abs(original.degree - before)), after === null ? b.max_degree : after + Math.max(leap, Math.abs(original.degree - after)));
      next.degree = clamp(Math.round(next.degree), low, high);
      // Cadences identify a phrase as it evolves. Its ending may move octaves,
      // but stays on the inherited scale-degree class.
      if (index === p.notes.length - 1) {
        const octaves = Math.round((next.degree - original.degree) / 7);
        const degree = original.degree + 7 * octaves;
        next.degree = degree >= low && degree <= high ? degree : original.degree;
      }
    }
    const latestOnset = Math.min(followingStart - original.duration, index === p.notes.length - 1 ? b.max_final_onset ?? b.max_end : b.max_end);
    // A vertical drag sends both axes. Keep untouched expressive timing exact
    // instead of snapping thirds (or a human offset) while changing only pitch.
    if ("onset" in changes && next.onset !== original.onset) next.onset = clamp(quantize(next.onset), previousEnd, latestOnset);
    if ("duration" in changes && next.duration !== original.duration) next.duration = clamp(quantize(next.duration), b.min_duration, followingStart - next.onset);
    return next;
  }
  function changeNote(changes, snap) {
    const p = phrase();
    if (!p || state.note === null) return;
    const notes = p.notes.map((n, index) => index === state.note ? limitedNote(index, changes, p, snap) : { ...n });
    commitNotes(notes, noteTitle(notes[state.note], state.note));
  }
  function transpose(steps) {
    const p = phrase(), b = bounds();
    if (!p) return;
    const notes = p.notes.map((n, index) => {
      const shift = index === p.notes.length - 1 && Math.abs(steps) < 7 ? 0 : steps;
      return { ...n, degree: n.degree + shift };
    });
    if (notes.some((n) => n.degree < b.min_degree || n.degree > b.max_degree)) {
      bridge().toast?.("That would go beyond this melody’s singing range."); return;
    }
    commitNotes(notes, Math.abs(steps) < 7 ? "Melody moved; phrase ending preserved." : "Phrase moved an octave.");
  }
  function evenRhythm() {
    const p = phrase(), b = bounds();
    if (!p || p.notes.length < 2) return;
    const start = p.notes[0].onset, end = p.notes.at(-1).onset + p.notes.at(-1).duration;
    // Equal attacks are not always multiples of a quarter beat (6/8 regularly
    // uses thirds). Leave the cadence its required pickup space and let it
    // sustain longer when a perfectly even ending would start too late.
    const lastStart = Math.min(start + (end - start) * (p.notes.length - 1) / p.notes.length,
      b.max_final_onset ?? b.max_end, end - b.min_duration);
    const step = (lastStart - start) / (p.notes.length - 1);
    if (step < b.min_duration - 1e-9 || end - lastStart < b.min_duration - 1e-9) {
      bridge().toast?.("This phrase is too tightly packed to space evenly while keeping every syllable singable."); return;
    }
    const boundaries = p.notes.map((_, i) => i === p.notes.length - 1 ? lastStart : start + i * step);
    const notes = p.notes.map((n, i) => ({ ...n, onset: boundaries[i],
      duration: Math.max(b.min_duration, (boundaries[i + 1] ?? end) - boundaries[i]) }));
    commitNotes(notes, "Notes spaced evenly; the ending leaves room for the next phrase.");
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
    commitNotes(notes, "Large leaps softened; phrase ending preserved.");
  }

  function moveSection(from, to) {
    if (from === to || to < 0 || to >= sections().length) return;
    const reordered = [...sections()];
    const [moved] = reordered.splice(from, 1); reordered.splice(to, 0, moved);
    const originalOccurrences = sections().filter((s) => s.name === moved.name).map((s) => s.id);
    const nextOccurrences = reordered.filter((s) => s.name === moved.name).map((s) => s.id);
    if (originalOccurrences.some((id, index) => id !== nextOccurrences[index])) {
      bridge().toast?.("Repeated verses and refrains keep their lyric order. Move this section between other kinds of section."); return;
    }
    const order = reordered.map((s) => s.id);
    state.section = to; state.phrase = 0; state.note = null;
    commit("form.order", order);
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
          button("Restore order", () => commit("form.order", null), { class: "sbc-button sbc-quiet", title: "Remove your arrangement override and restore this song’s inherited order" }))));
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
    const words = p.notes.map((n) => displayWords(n.syllable)).filter(Boolean).join(" ");
    return el("button", { type: "button", id: `sbc-phrase-${index}`, class: `sbc-phrase${index === state.phrase ? " is-selected" : ""}`,
      "aria-pressed": index === state.phrase ? "true" : "false", onclick: () => selectedPhrase(index) },
    el("span", { class: "sbc-phrase-label" }, `Phrase ${index + 1}`, composition().edited_phrases?.includes(p.id) ? el("span", { class: "sbc-edited-dot", title: "Your melody" }, "•") : null),
    el("span", { class: "sbc-phrase-words" }, words || "Instrumental melody"));
  }
  function gridGeometry(p) {
    const b = bounds(p), notes = p.notes || [];
    const low = Math.max(b.min_degree, Math.min(1, ...notes.map((n) => n.degree)) - 2);
    const high = Math.min(b.max_degree, Math.max(8, ...notes.map((n) => n.degree)) + 2);
    const start = b.min_onset, end = b.max_end;
    const row = 23, left = 58, ruler = p.chords?.length ? 54 : 28;
    const available = Math.max(500, (root()?.clientWidth || 950) - 44);
    const unit = Math.max(42, (available - left) / Math.max(1, end - start)) * state.zoom;
    return { low, high, start, end, row, left, ruler, unit, width: left + (end - start) * unit, height: ruler + (high - low + 1) * row };
  }
  function pianoRoll() {
    const p = phrase(), g = gridGeometry(p), c = composition();
    const roll = el("div", { class: "sbc-roll", style: { width: `${g.width}px`, height: `${g.height}px` }, "aria-label": "Melody piano roll" });
    if (p.chords?.length) {
      roll.append(el("span", { class: "sbc-harmony-label" }, "Harmony"));
      const lane = p.harmony?.length ? p.harmony : p.chords.flatMap((chords, bar) => chords.map((symbol, slot) => ({
        bar, slot, symbol, name: symbol, start: bar * c.beats_per_bar + slot * c.beats_per_bar / chords.length, beats: c.beats_per_bar / chords.length })));
      lane.forEach((h) => {
        const chosen = state.chord && state.chord.bar === h.bar && state.chord.slot === h.slot;
        const rub = h.rubs?.length ? `; ${h.rubs.length} sung note${h.rubs.length === 1 ? "" : "s"} not in it${h.hard ? ", one a half step off" : ""}` : "";
        roll.append(el("button", { type: "button", "data-chord": `${h.bar}.${h.slot}`,
          class: `sbc-chord${chordMine(p, h) ? " is-edited" : ""}${chosen ? " is-selected" : ""}${h.hard ? " is-rub" : ""}`,
          "aria-pressed": chosen ? "true" : "false", "aria-label": `Bar ${h.bar + 1}, chord ${h.name}${rub}. Select to change it.`,
          title: `Bar ${h.bar + 1}: ${h.name}${rub}. Select to change it.`, onclick: () => selectChord(h),
          style: { left: `${g.left + (h.start - g.start) * g.unit}px`, width: `${Math.max(1, h.beats * g.unit - 2)}px` } }, h.name));
      });
    }
    const plot = el("div", { class: "sbc-grid", style: { left: `${g.left}px`, top: `${g.ruler}px`, width: `${g.width - g.left}px`, height: `${g.height - g.ruler}px`,
      backgroundSize: `${g.unit * state.snap}px ${g.row}px` } });
    roll.append(plot);
    for (let degree = g.high; degree >= g.low; degree--) {
      const y = g.ruler + (g.high - degree) * g.row;
      const tonic = ((degree - 1) % 7 + 7) % 7 === 0;
      if (tonic) roll.append(el("div", { class: "sbc-tonic-row", style: { left: `${g.left}px`, top: `${y}px`, width: `${g.width - g.left}px`, height: `${g.row}px` } }));
      const ref = p.notes[0];
      roll.append(button("", () => audition(pitchFor(ref, degree)), { class: `sbc-key${tonic ? " is-tonic" : ""}`,
        id: `sbc-key-${degree}`,
        title: `Scale degree ${degree}, ${pitchName(pitchFor(ref, degree))}. Click to hear.`, "aria-label": `Hear ${pitchName(pitchFor(ref, degree))}, scale degree ${degree}`,
        style: { top: `${y}px`, height: `${g.row}px`, width: `${g.left - 4}px` },
      }));
      roll.lastChild.append(el("span", {}, degreeName(degree)), el("small", {}, pitchName(pitchFor(ref, degree))));
    }
    for (let beat = Math.ceil(g.start); beat <= g.end; beat++) {
      const x = g.left + (beat - g.start) * g.unit;
      const bar = beat >= 0 && beat % c.beats_per_bar === 0;
      roll.append(el("span", { class: `sbc-ruler-label${bar ? " is-bar" : ""}`, style: { left: `${x}px` } },
        beat < 0 ? "↗" : bar ? `${Math.floor(beat / c.beats_per_bar) + 1}` : "·"),
      el("div", { class: `sbc-grid-line${bar ? " is-bar" : ""}`, style: { left: `${x}px`, top: `${g.ruler}px`, height: `${g.height - g.ruler}px` } }));
    }
    p.notes.forEach((n, index) => {
      const item = el("button", { type: "button", class: `sbc-note${index === state.note ? " is-selected" : ""}${index === p.notes.length - 1 ? " is-cadence" : ""}${n.edited ? " is-edited" : ""}${chosenChord()?.rubs?.includes(index) ? " is-rub" : ""}`,
        "aria-label": noteTitle(n, index, p), "aria-pressed": index === state.note ? "true" : "false", "data-note": index,
        title: `${noteTitle(n, index, p)}. Drag to move; drag right edge to resize. Arrow keys move; Shift + left/right changes length.`,
        style: noteStyle(n, g), onclick: () => {
          if (state.drag?.moved) return;
          state.note = index; selectNote(item, index); audition(pitchFor(n));
        }, onpointerdown: (event) => startNoteDrag(event, index, g), onkeydown: (event) => noteKey(event, index),
      }, el("span", { class: "sbc-note-word" }, displayWords(n.syllable) || "♪"), el("span", { class: "sbc-resize", "aria-hidden": "true" }, ""));
      roll.append(item);
    });
    roll.append(el("div", { id: "sbc-playhead", class: "sbc-playhead", hidden: !state.playback,
      style: { left: `${g.left}px`, top: `${g.ruler}px`, height: `${g.height - g.ruler}px` } }));
    return el("div", { id: "sbc-roll-scroll", class: "sbc-roll-scroll", tabindex: "0", "aria-label": "Scrollable melody editor" }, roll);
  }
  function noteStyle(n, g) {
    return { left: `${g.left + (n.onset - g.start) * g.unit + 1}px`, top: `${g.ruler + (g.high - n.degree) * g.row + 2}px`,
      width: `${Math.max(9, n.duration * g.unit - 3)}px`, height: `${g.row - 4}px` };
  }
  function selectNote(item, index) {
    state.note = index;
    root().querySelectorAll(".sbc-note").forEach((node) => { const chosen = Number(node.dataset.note) === index; node.classList.toggle("is-selected", chosen); node.setAttribute("aria-pressed", String(chosen)); });
    const old = root().querySelector(".sbc-inspector");
    if (old) old.replaceWith(inspector());
    announce(noteTitle(phrase().notes[index], index));
  }
  function startNoteDrag(event, index, geometry) {
    if (event.button !== 0) return;
    stop();
    const target = event.currentTarget, p = phrase(), original = { ...p.notes[index] };
    const rect = target.getBoundingClientRect();
    const resizing = event.target.classList.contains("sbc-resize") || event.clientX > rect.right - Math.min(10, rect.width / 3);
    state.note = index; selectNote(target, index);
    const drag = { index, original, x: event.clientX, y: event.clientY, moved: false, resizing, preview: original };
    state.drag = drag; target.setPointerCapture(event.pointerId);
    const move = (nextEvent) => {
      if (Math.abs(nextEvent.clientX - drag.x) + Math.abs(nextEvent.clientY - drag.y) < 4 && !drag.moved) return;
      drag.moved = true;
      const time = (nextEvent.clientX - drag.x) / geometry.unit;
      // a drag that stays within half a grid unit sideways is a pitch change only: the note's timing,
      // off-grid or not, is kept exactly instead of being snapped by a pixel of drift
      const sideways = Math.abs(nextEvent.clientX - drag.x) >= Math.max(4, geometry.unit / 2);
      const degree = original.degree - Math.round((nextEvent.clientY - drag.y) / geometry.row);
      const changes = resizing ? { duration: original.duration + time } : sideways ? { onset: original.onset + time, degree } : { degree };
      drag.preview = limitedNote(index, changes, p);
      Object.assign(target.style, noteStyle(drag.preview, geometry));
      target.classList.add("is-dragging");
      const detail = document.getElementById("sbc-drag-value");
      if (detail) detail.textContent = noteTitle(drag.preview, index);
    };
    const finish = (upEvent) => {
      target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", finish); target.removeEventListener("pointercancel", cancel);
      if (target.hasPointerCapture(upEvent.pointerId)) target.releasePointerCapture(upEvent.pointerId);
      target.classList.remove("is-dragging");
      if (drag.moved) {
        const notes = p.notes.map((n, i) => i === index ? drag.preview : { ...n });
        commitNotes(notes, noteTitle(drag.preview, index)); audition(pitchFor(original, drag.preview.degree));
      }
      // A pointer's synthetic click must not audition the old pitch after a drag.
      setTimeout(() => { if (state.drag === drag) state.drag = null; }, 0);
    };
    const cancel = (cancelEvent) => {
      drag.moved = false; Object.assign(target.style, noteStyle(original, geometry)); finish(cancelEvent); state.drag = null;
    };
    target.addEventListener("pointermove", move); target.addEventListener("pointerup", finish); target.addEventListener("pointercancel", cancel);
  }
  function noteKey(event, index) {
    if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault(); state.note = index;
    const n = note(), last = index === phrase().notes.length - 1;
    if (event.key === "ArrowUp" || event.key === "ArrowDown") {
      const direction = event.key === "ArrowUp" ? 1 : -1;
      changeNote({ degree: n.degree + direction * (last || event.altKey ? 7 : 1) });
    } else {
      const delta = (event.key === "ArrowRight" ? 1 : -1) * state.snap;
      changeNote(event.shiftKey ? { duration: n.duration + delta } : { onset: n.onset + delta });
    }
    root()?.querySelector(`[data-note="${index}"]`)?.focus({ preventScroll: true });
  }
  // ---- the chords (docs/STUDIO.md, "Changing the chords"): a tune line's chords, a list a bar, each a function
  // of the key (a numeral, a quality if named, a bass if not the root), changed everywhere the line is sung.
  const CHORD = /^([#b]?)([iIvV]{1,3})(maj|m|dim|aug|sus2|sus4)?(?:\/([35]))?$/;
  const NUMERALS = { i: 1, ii: 2, iii: 3, iv: 4, v: 5, vi: 6, vii: 7 };
  const QUALITIES = { maj: [0, 4, 7], m: [0, 3, 7], dim: [0, 3, 6], aug: [0, 4, 8], sus2: [0, 2, 7], sus4: [0, 5, 7] };
  function parseChord(symbol) {
    const m = CHORD.exec(String(symbol || "").trim());
    if (!m || !NUMERALS[m[2].toLowerCase()]) return null;
    return { root: m[1] + m[2].toUpperCase(), accidental: m[1], degree: NUMERALS[m[2].toLowerCase()], quality: m[3] || "", bass: Number(m[4] || 1) };
  }
  function chordSymbol(parts) {
    return `${parts.root}${parts.quality || ""}${parts.bass && parts.bass !== 1 ? `/${parts.bass}` : ""}`;
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
  function lineChords(p = phrase()) { return (p?.chords || []).map((bar) => [...bar]); }
  function chosenChord(p = phrase()) {
    return state.chord ? (p?.harmony || []).find((h) => h.bar === state.chord.bar && h.slot === state.chord.slot) : null;
  }
  function chordMine(p, h) {
    // a person's chord, in the second ink: one that differs from the song's own at that place
    if (!p.chords_edited) return false;
    const own = p.song_chords?.[h.bar];
    return !own || own.length !== p.chords[h.bar].length || own[h.slot] !== h.symbol;
  }
  function selectChord(h) {
    state.chord = { bar: h.bar, slot: h.slot }; state.note = null;
    paint(); strum(h.symbol);
    root()?.querySelector(`[data-chord="${h.bar}.${h.slot}"]`)?.focus({ preventScroll: true });
  }
  function strum(symbol) {
    if (bridge().pauseAudio) bridge().pauseAudio();
    const ctx = audioContext();
    if (!ctx) return;
    const pitches = chordPitches(symbol).map((pitch) => within(pitch % 12, 55)).sort((a, b) => a - b);
    const bass = parseChord(symbol);
    pitches.forEach((pitch, i) => pluck(ctx, pitch, ctx.currentTime + 0.01 + i * 0.03, 1.1, 0.03));
    const tones = chordPitches(symbol);
    if (tones.length) pluck(ctx, within(tones[{ 1: 0, 3: 1, 5: 2 }[bass.bass] || 0] % 12, 36), ctx.currentTime + 0.01, 1.2, 0.08, "bass");
  }
  function commitChords(bars, message) {
    const p = phrase();
    if (!p) return;
    if (JSON.stringify(bars) === JSON.stringify(lineChords(p))) { paint(); return; }
    commit(p.chords_path || `chords.${p.id}`, bars);
    announce(message);
  }
  function setChord(symbol) {
    const p = phrase(), at = state.chord;
    if (!p || !at || !parseChord(symbol)) return;
    const bars = lineChords(p);
    bars[at.bar][at.slot] = symbol;
    strum(symbol);
    commitChords(bars, `Bar ${at.bar + 1}: ${symbol}. The band, the voices and the sketch follow everywhere this line is sung.`);
  }
  function setChordsInBar(count) {
    const p = phrase(), at = state.chord;
    if (!p || !at) return;
    const bars = lineChords(p), old = bars[at.bar];
    // each new chord is the one sounding where it starts: splitting a bar adds a chord to change; joining keeps the first
    bars[at.bar] = Array.from({ length: count }, (_, j) => old[Math.floor(j * old.length / count)]);
    state.chord = { bar: at.bar, slot: Math.min(at.slot * count / old.length | 0, count - 1) };
    commitChords(bars, count > old.length ? "Bar split: change the new chord to add a passing chord." : "Bar joined.");
  }
  function chordCard() {
    const p = phrase(), h = chosenChord(p), c = composition(), choices = c?.chord_choices;
    if (!p || !h || !choices) return null;
    const parts = parseChord(h.symbol) || { root: "I", quality: "", bass: 1 };
    const counts = c.chords_per_bar || [1];
    const words = p.notes.filter((_, i) => h.rubs?.includes(i)).map((n) => displayWords(n.syllable) || pitchName(pitchFor(n)));
    const rub = h.rubs?.length
      ? `${h.rubs.length} sung note${h.rubs.length === 1 ? "" : "s"} over it ${h.rubs.length === 1 ? "isn't" : "aren't"} in the chord (${words.join(", ")})${h.hard ? ", one a half step from it: a sharp rub" : ": passing notes, as folk harmony has them"}.`
      : "Every sung note over it is in the chord.";
    const repeats = sections().flatMap((s) => s.phrases || []).filter((item) => item.id === p.id).length;
    return el("div", { class: "sbc-chord-card", role: "group", "aria-label": `Chord in bar ${h.bar + 1}` },
      el("div", { class: "sbc-note-heading" }, el("span", { class: "sbc-overline" }, `Bar ${h.bar + 1} · chord ${h.slot + 1} of ${p.chords[h.bar].length}`),
        el("strong", { class: chordMine(p, h) ? "is-mine" : "" }, h.name),
        el("span", { class: `sbc-muted${h.hard ? " sbc-leap-warning" : ""}` }, rub)),
      el("div", { class: "sbc-chord-row" }, el("span", { class: "sbc-overline" }, "In the key"),
        el("div", { class: "sbc-button-group", role: "group", "aria-label": "Chords in the key" },
          choices.diatonic.map((d) => button(d.name, () => setChord(d.symbol), { class: `sbc-button${d.symbol.toUpperCase() === h.symbol.toUpperCase() ? " is-on" : ""}`,
            title: `${d.symbol}: ${d.name}`, "aria-pressed": d.symbol.toUpperCase() === h.symbol.toUpperCase() ? "true" : "false" })))),
      el("div", { class: "sbc-chord-row" },
        select("Root", parts.root, choices.roots.map((r) => [r.numeral, `${r.numeral} · ${r.note}`]), (value) => setChord(chordSymbol({ ...parts, root: value })), { id: "sbc-chord-root" }),
        select("Quality", parts.quality, choices.qualities, (value) => setChord(chordSymbol({ ...parts, quality: value })), { id: "sbc-chord-quality" }),
        select("Bass", parts.bass, choices.basses, (value) => setChord(chordSymbol({ ...parts, bass: Number(value) })), { id: "sbc-chord-bass" }),
        select("Chords in this bar", p.chords[h.bar].length, counts.map((n) => [n, String(n)]), (value) => setChordsInBar(Number(value)), { id: "sbc-chord-count" }),
        button("♪", () => strum(h.symbol), { class: "sbc-button sbc-audition", "aria-label": `Hear ${h.name}` })),
      el("div", { class: "sbc-chord-row" },
        el("span", { class: "sbc-muted" }, repeats > 1 ? `This line's chords change in all ${repeats} places it's sung.` : "This line's chords change wherever it's sung."),
        button("Restore chords", () => { state.chord = null; commit(p.chords_path || `chords.${p.id}`, null); },
          { class: "sbc-button sbc-quiet", disabled: !p.chords_edited, title: "Give this line back the song's own chords" }),
        button("Done", () => { state.chord = null; paint(); }, { class: "sbc-button sbc-quiet" })));
  }

  function inspector() {
    const p = phrase(), n = note(), b = bounds();
    if (!n) return el("div", { class: "sbc-inspector sbc-inspector-empty" }, el("span", { class: "sbc-inspector-icon", "aria-hidden": "true" }, "↖"),
      el("div", {}, el("strong", {}, "Make the melody yours"), el("p", { class: "sbc-muted" }, "Select a note to edit its pitch, position and length. Drag its right edge to resize.")));
    const index = state.note;
    const previous = index ? p.notes[index - 1].onset + p.notes[index - 1].duration : b.min_onset;
    const next = index < p.notes.length - 1 ? p.notes[index + 1].onset : b.max_end;
    const last = index === p.notes.length - 1;
    const degrees = [];
    for (let degree = b.min_degree; degree <= b.max_degree; degree++) {
      if ((!last || (degree - n.degree) % 7 === 0) && limitedNote(index, { degree }, p).degree === degree) degrees.push([degree, `${pitchName(pitchFor(n, degree))} · ${degreeName(degree)}`]);
    }
    return el("div", { class: "sbc-inspector" },
      el("div", { class: "sbc-note-heading" }, el("span", { class: "sbc-overline" }, `Note ${index + 1} of ${p.notes.length}`),
        el("strong", {}, displayWords(n.word || n.syllable) || "Melody note"), last ? el("span", { class: "sbc-cadence-label" }, "Phrase ending") : null),
      select("Pitch · scale degree", n.degree, degrees, (value) => changeNote({ degree: Number(value) }), { id: "sbc-note-pitch" }),
      number("Start · beats", n.onset, previous, round(Math.min(next - n.duration, last ? b.max_final_onset ?? b.max_end : b.max_end)), b.grid, (value) => changeNote({ onset: value }, b.grid), { id: "sbc-note-start" }),
      number("Length · beats", n.duration, b.min_duration, round(next - n.onset), b.grid, (value) => changeNote({ duration: value }, b.grid), { id: "sbc-note-length" }),
      button("♪", () => audition(pitchFor(n)), { class: "sbc-button sbc-audition", "aria-label": `Hear ${pitchName(pitchFor(n))}` }));
  }
  function health() {
    const p = phrase(), notes = p.notes, degrees = notes.map((n) => n.degree);
    const pitches = notes.map((n) => pitchFor(n));
    const largest = Math.max(0, ...degrees.slice(1).map((degree, i) => Math.abs(degree - degrees[i])));
    const repeats = sections().flatMap((s) => s.phrases || []).filter((item) => item.id === p.id).length;
    return el("div", { class: "sbc-health" },
      el("span", {}, el("span", { class: "sbc-health-dot", "aria-hidden": "true" }, "●"), `${notes.length} syllable slots preserved`),
      el("span", {}, `Range ${pitchName(Math.min(...pitches))}–${pitchName(Math.max(...pitches))}`),
      el("span", { class: largest > 4 ? "sbc-leap-warning" : "" }, largest > 4 ? `Wide leap: ${largest} scale steps` : "Comfortable melodic steps"),
      el("span", {}, `${repeats} shared ${repeats === 1 ? "appearance" : "appearances"}`));
  }
  function editor() {
    const p = phrase();
    if (!p?.notes?.length) return el("p", { class: "sbc-muted" }, "This section has no editable melody.");
    return el("div", { class: "sbc-editor" },
      el("div", { class: "sbc-row sbc-editor-heading" },
        el("div", {}, el("h3", {}, section().label, el("span", { class: "sbc-muted" }, " / Melody")), el("p", { class: "sbc-muted" }, "Edit a phrase once; every appearance follows.")),
        el("div", { class: "sbc-editor-settings" }, select("Snap", state.snap, [[0.25, "¼ beat"], [0.5, "½ beat"], [1, "1 beat"]], (value) => { state.snap = Number(value); paint(); }, { id: "sbc-snap" }),
          select("Zoom", state.zoom, [[1, "Fit"], [1.5, "150%"], [2, "200%"], [3, "300%"]], (value) => { state.zoom = Number(value); paint(); }, { id: "sbc-zoom" }))),
      phraseStrip(), pianoRoll(), inspector(), chordCard(),
      el("div", { class: "sbc-tools" }, el("span", { class: "sbc-overline" }, "Shape phrase"),
        el("div", { class: "sbc-button-group", role: "group", "aria-label": "Transpose melody; keep its ending" },
          button("↓ Step", () => transpose(-1), { title: "Lower melody one scale step, keeping its phrase ending" }),
          button("↑ Step", () => transpose(1), { title: "Raise melody one scale step, keeping its phrase ending" })),
        button("Soften leaps", smoothMelody, { title: "Bring notes within two scale steps of their neighbors, preserving the ending" }),
        button("Even rhythm", evenRhythm, { title: "Spread the existing syllables evenly across their current phrase span" }),
        button("Restore phrase", () => { state.note = null; commit(p.path || `tune.${p.id}`, null); }, { class: "sbc-button sbc-quiet", title: "Remove your melody override and restore this song’s inherited phrase" })),
      health(),
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
  function tone(ctx, pitch, start, duration, click = false) {
    const oscillator = ctx.createOscillator(), gain = ctx.createGain();
    oscillator.type = click ? "sine" : "triangle";
    oscillator.frequency.value = click ? pitch : 440 * 2 ** ((pitch - 69) / 12);
    const length = Math.max(0.06, duration);
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(click ? 0.035 : 0.075, start + 0.009);
    gain.gain.exponentialRampToValueAtTime(0.018, start + Math.min(0.12, length * 0.4));
    gain.gain.setValueAtTime(0.018, start + Math.max(0.02, length - 0.05));
    gain.gain.linearRampToValueAtTime(0.0001, start + length);
    oscillator.connect(gain); gain.connect(ctx.destination);
    state.nodes.add(oscillator);
    oscillator.onended = () => { state.nodes.delete(oscillator); oscillator.disconnect(); gain.disconnect(); };
    oscillator.start(start); oscillator.stop(start + length + 0.025);
  }
  // The sketch's band: a plain strum on each beat of a chord (the first one fuller) and a bass on its first
  // beat, the fifth halfway through a long one. Voiced from the chord's pitch classes: the triad between G3
  // and F#4, the bass between C2 and B2.
  const within = (pc, low) => low + (((pc - low) % 12) + 12) % 12;
  function backing(ctx, chord, offset, seconds) {
    const beats = Math.max(1, Math.round(chord.duration));
    for (let k = 0; k < beats; k++) {
      const start = offset + (chord.beat + k) * seconds;
      if (start < ctx.currentTime - 0.01) continue;
      const at = Math.max(ctx.currentTime, start), length = Math.min(chord.duration - k, 1) * seconds;
      if (state.chords && chord.pcs.length) {
        chord.pcs.map((pc) => within(pc, 55)).sort((a, b) => a - b).forEach((pitch, i) =>
          pluck(ctx, pitch, at + i * 0.012, Math.max(0.12, length * 0.95), k ? 0.013 : 0.02));
      }
      if (state.bass && chord.bass !== undefined && (k === 0 || (beats >= 4 && k === beats / 2))) {
        const pc = k === 0 ? chord.bass : chord.pcs[2] ?? chord.bass;
        pluck(ctx, within(pc, 36), at, Math.max(0.2, Math.min(2, chord.duration - k) * seconds * 0.9), 0.07, "bass");
      }
    }
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
    out.connect(gain); gain.connect(ctx.destination);
    state.nodes.add(oscillator);
    oscillator.onended = () => { state.nodes.delete(oscillator); oscillator.disconnect(); if (out !== oscillator) out.disconnect(); gain.disconnect(); };
    oscillator.start(start); oscillator.stop(start + duration + 0.03);
  }
  function audition(pitch) {
    if (bridge().pauseAudio) bridge().pauseAudio();
    else document.getElementById("audio")?.pause();
    const ctx = audioContext();
    if (ctx) tone(ctx, pitch, ctx.currentTime + 0.005, 0.3);
  }
  function playbackSequence() {
    const chosen = state.scope === "song" ? sections() : [section()];
    const phrases = state.scope === "phrase" ? [phrase()] : chosen.flatMap((s) => s.phrases || []);
    const origin = state.scope === "phrase" ? phrase().start_beat + bounds().min_onset
      : Math.min(chosen[0].start_beat, ...phrases.map((p) => p.start_beat - (p.pickup_beats || 0)));
    const end = state.scope === "phrase" ? phrase().start_beat + bounds().max_end
      : chosen.at(-1).start_beat + chosen.at(-1).duration_beats;
    const events = phrases.flatMap((p) => p.notes.map((n) => ({ beat: p.start_beat + n.onset - origin, duration: n.duration,
      pitch: pitchFor(n), phrase: p.id }))).sort((a, b) => a.beat - b.beat);
    // the chords under the tune as the band lays them out: each where it starts in its line, for how long
    const harmony = phrases.flatMap((p) => (p.harmony || []).map((h) => ({ beat: p.start_beat + h.start - origin,
      duration: h.beats, pcs: h.pcs || [], bass: h.bass }))).filter((h) => h.beat >= -1e-9 && h.beat < end - origin - 1e-9);
    return { origin, duration: Math.max(0.25, end - origin), events, harmony };
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
    paint(); schedule();
  }
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
      for (const event of playback.events) {
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
    const p = phrase(), g = gridGeometry(p), localBeat = absoluteBeat - p.start_beat;
    const cursor = document.getElementById("sbc-playhead");
    if (cursor) { cursor.hidden = localBeat < g.start || localBeat > g.end; cursor.style.left = `${g.left + (localBeat - g.start) * g.unit}px`; }
    const currentSection = sections().findIndex((s) => absoluteBeat >= s.start_beat && absoluteBeat < s.start_beat + s.duration_beats);
    root()?.querySelectorAll(".sbc-section").forEach((node) => node.classList.toggle("is-playing", Number(node.dataset.section) === currentSection));
    root()?.querySelectorAll(".sbc-overview-section").forEach((node) => node.classList.toggle("is-playing", Number(node.dataset.overviewSection) === currentSection));
    const songCursor = document.getElementById("sbc-song-playhead"), span = songSpan();
    if (songCursor) { songCursor.hidden = false; songCursor.style.left = `${clamp((absoluteBeat - span.start) / span.duration * 100, 0, 100)}%`; }
    state.frame = requestAnimationFrame(schedule);
  }
  function stop() {
    if (state.frame) cancelAnimationFrame(state.frame);
    state.frame = null; state.playback = null;
    for (const oscillator of state.nodes) { try { oscillator.stop(); } catch (_) { /* already ended */ } }
    state.nodes.clear();
    const play = document.getElementById("sbc-play");
    if (play) { play.textContent = "▶ Play sketch"; play.setAttribute("aria-pressed", "false"); }
    const cursor = document.getElementById("sbc-playhead");
    if (cursor) cursor.hidden = true;
    const songCursor = document.getElementById("sbc-song-playhead");
    if (songCursor) songCursor.hidden = true;
    root()?.querySelectorAll(".is-playing").forEach((node) => node.classList.remove("is-playing"));
  }
  function paint() {
    const box = root(), c = composition();
    if (!box || !c) return;
    const focused = box.contains(document.activeElement) ? document.activeElement : null;
    const focusId = focused?.id, focusNote = focused?.dataset.note, focusAction = focused?.dataset.composerAction;
    const scroll = box.querySelector(".sbc-roll-scroll")?.scrollLeft || 0;
    const arrangeScroll = box.querySelector(".sbc-arrangement-scroll")?.scrollLeft || 0;
    box.classList.add("sbc-composer");
    box.replaceChildren(transport(), arrangement(), section() ? editor() : null,
      el("div", { id: "sbc-status", class: "sbc-visually-hidden", role: "status", "aria-live": "polite" }));
    const roll = box.querySelector(".sbc-roll-scroll"); if (roll) roll.scrollLeft = scroll;
    const arrange = box.querySelector(".sbc-arrangement-scroll"); if (arrange) arrange.scrollLeft = arrangeScroll;
    const restore = focusNote !== undefined ? box.querySelector(`[data-note="${focusNote}"]`)
      : focusId ? document.getElementById(focusId)
        : focusAction ? [...box.querySelectorAll("button")].find((node) => node.dataset.composerAction === focusAction) : null;
    restore?.focus({ preventScroll: true });
  }
  function render(view) {
    if (state.view !== view) stop();
    state.view = view;
    const box = root();
    if (!view?.composition?.sections?.length) {
      if (box) box.replaceChildren(el("p", { class: "sbc-muted" }, "The arrangement will appear when the song is ready."));
      return;
    }
    if (state.section < 0) state.section = Math.max(0, sections().findIndex((s) => s.phrases?.some((p) => p.notes?.length)));
    state.section = clamp(state.section, 0, sections().length - 1);
    state.phrase = clamp(state.phrase, 0, Math.max(0, (section().phrases?.length || 0) - 1));
    if (state.note !== null && state.note >= (phrase()?.notes?.length || 0)) state.note = null;
    if (state.chord && !(phrase()?.chords?.[state.chord.bar]?.length > state.chord.slot)) state.chord = null;
    paint();
  }
  window.addEventListener("pagehide", stop);
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); });
  window.SongbirdComposer = { render, stop };
})();
