// Pitched band parts use the same portable part.* notes as MIDI import.
// No samples or new file format: time is in 96ths of a beat, pitch relative to the key.
(() => {
  "use strict";
  const PPB = 96;
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const copy = (notes) => notes.map((n) => n.slice());
  const bridge = () => window.StudioBridge;
  let current = null, clipboard = null, serial = 0;
  const names = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"];
  const pitchName = (n) => `${names[((n % 12) + 12) % 12]}${Math.floor(n / 12) - 1}`;
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === false || value === undefined || value === null) continue;
      if (key === "class") node.className = value;
      else if (key === "style") Object.assign(node.style, value);
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  const button = (text, onclick, attrs = {}) => el("button", { type: "button", class: "sbc-button", onclick, ...attrs }, text);
  function field(label, value, min, max, step, apply) {
    return el("label", { class: "sbc-field" }, el("span", {}, label), el("input", { type: "number", value, min, max, step, "aria-label": label,
      onchange: (e) => { if (e.target.value.trim() && Number.isFinite(Number(e.target.value))) apply(clamp(Number(e.target.value), min, max)); } }));
  }
  function limits(c, p, player) {
    const tonic = c.tonic, seed = c.part_seed_tonic ?? tonic;
    return { low: Math.max(-seed, player.low - 5 - seed), high: Math.min(127 - seed, player.high + 5 - seed),
      start: -Math.round((p.pickup_beats || 0) * PPB), end: Math.round(p.duration_beats * PPB) };
  }
  function normalize(notes, player, b) {
    if (notes.length > 512) throw new Error("Use at most 512 notes in a phrase.");
    const sorted = copy(notes).sort((a, z) => a[0] - z[0] || a[2] - z[2] || z[1] - a[1]);
    const out = [], starts = new Map();
    for (const n of sorted) {
      if (n.length !== 4 || n.some((v) => !Number.isInteger(v)) || n[0] < b.start || n[0] >= b.end ||
        n[1] < 1 || n[1] > 32 * PPB || n[2] < b.low || n[2] > b.high || n[3] < 1 || n[3] > 127)
        throw new Error("Keep notes inside the phrase and the instrument's range.");
      if (out.some((x) => x[0] === n[0] && x[2] === n[2])) continue;
      const count = (starts.get(Math.floor(n[0] / PPB)) || 0) + 1;
      starts.set(Math.floor(n[0] / PPB), count);
      if (count > 32) throw new Error("Use at most 32 note starts in a beat.");
      if (!player.poly && out.length) {
        const prev = out.at(-1);
        if (prev[0] === n[0]) throw new Error("This instrument plays one note at a time. Move one of these notes.");
        prev[1] = Math.min(prev[1], n[0] - prev[0]);
      }
      if (player.poly && out.filter((x) => x[0] + x[1] > n[0]).length >= 10)
        throw new Error("Use at most ten notes at once.");
      out.push(n);
    }
    return out;
  }
  async function ask(path, body) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json",
      "X-Studio": document.querySelector('meta[name="studio-token"]').content }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Couldn't load the notes. Try again.");
    return data;
  }
  async function load(s) {
    try {
      const edits = bridge().getEdits?.() || {}, data = await ask("/api/players", { edits });
      if (current !== s || !s.loading) return;
      const p = s.phrase, from = p.start_beat - (p.pickup_beats || 0) - 0.125, end = p.start_beat + p.duration_beats;
      const notes = (data.players.find((x) => x.part === s.player.name)?.notes || []).filter((n) => n[0] >= from && n[0] < end);
      const preview = await ask("/api/notes-in", { edits, take: { player: s.player.name, notes, lines: [p.part_key] } });
      if (current !== s || !s.loading) return;
      if (preview.refused?.length) throw new Error(`${preview.refused[0].why}. Start empty to write a new part.`);
      s.notes = copy(preview.changes.find((x) => x.path === s.path)?.value || []);
      s.ready = true;
    } catch (error) { if (current === s && s.loading) s.error = error.message; }
    if (current === s) { s.loading = false; s.paint(); }
  }
  function save(notes, selection = null) {
    const s = current;
    if (!s) return;
    try {
      const clean = normalize(notes, s.player, s.bounds);
      s.notes = clean; s.ready = true; s.mine = true; s.error = null; s.loading = false;
      s.selected = selection ? clean.findIndex((n) => n.every((x, i) => x === selection[i])) : null;
      if (s.selected === -1) s.selected = null;
      bridge().setEdit(s.path, clean);
      s.paint();
    } catch (error) { s.error = error.message; s.paint(); }
  }
  function add(onset = null, pitch = null) {
    const s = current; if (!s?.ready) return;
    const grid = Math.max(1, Math.round(s.snap * PPB)), selected = s.notes[s.selected];
    const start = onset ?? (selected ? selected[0] + selected[1] : 0);
    const n = [clamp(Math.round(start / grid) * grid, s.bounds.start, s.bounds.end - 1), grid,
      clamp(Math.round(pitch ?? selected?.[2] ?? 0), s.bounds.low, s.bounds.high), 96];
    save([...s.notes, n], n);
  }
  function change(index, changes) {
    const s = current, notes = copy(s.notes), n = notes[index];
    if (!n) return;
    Object.assign(n, changes); save(notes, n);
  }
  function remove() {
    const s = current;
    if (!s || s.selected === null) return;
    save(s.notes.filter((_, i) => i !== s.selected));
  }
  function select(index) { current.selected = index; current.paint(); }
  function moveKey(e, index) {
    if (!["Delete", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault(); e.stopPropagation(); current.selected = index;
    if (e.key === "Delete" || e.key === "Backspace") { remove(); return; }
    const n = current.notes[index], dir = ["ArrowUp", "ArrowRight"].includes(e.key) ? 1 : -1;
    if (["ArrowUp", "ArrowDown"].includes(e.key)) change(index, { 2: clamp(n[2] + dir * (e.altKey ? 12 : 1), current.bounds.low, current.bounds.high) });
    else { const key = e.shiftKey ? 1 : 0; change(index, { [key]: clamp(n[key] + dir * Math.round(current.snap * PPB), key ? 1 : current.bounds.start, key ? 32 * PPB : current.bounds.end - 1) }); }
  }
  function drag(e, index, g) {
    if (e.button !== 0 || window.SongbirdScore?.narrow?.()) return;
    const s = current, target = e.currentTarget, n = s.notes[index].slice(), rect = target.getBoundingClientRect();
    s.selected = index;
    const resize = e.clientX > rect.right - Math.min(10, rect.width / 3), x = e.clientX, y = e.clientY;
    let preview = n.slice(), moved = false;
    target.setPointerCapture(e.pointerId);
    const move = (event) => {
      if (Math.abs(event.clientX - x) + Math.abs(event.clientY - y) < 4 && !moved) return;
      moved = true; preview = n.slice();
      const dt = Math.round((event.clientX - x) / g.unit / s.snap) * Math.round(s.snap * PPB);
      if (resize) preview[1] = clamp(n[1] + dt, 1, 32 * PPB);
      else { preview[0] = clamp(n[0] + dt, s.bounds.start, s.bounds.end - 1); preview[2] = clamp(n[2] - Math.round((event.clientY - y) / g.row), s.bounds.low, s.bounds.high); }
      Object.assign(target.style, noteStyle(preview, g));
    };
    const finish = (event) => {
      target.removeEventListener("pointermove", move); target.removeEventListener("pointerup", finish); target.removeEventListener("pointercancel", cancel);
      if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
      if (current === s && moved) change(index, Object.fromEntries(preview.map((v, i) => [i, v])));
    };
    const cancel = (event) => { moved = false; Object.assign(target.style, noteStyle(n, g)); finish(event); };
    target.addEventListener("pointermove", move); target.addEventListener("pointerup", finish); target.addEventListener("pointercancel", cancel);
  }
  function noteStyle(n, g) {
    return { left: `${g.left + (n[0] / PPB - g.start) * g.unit + 1}px`, top: `${g.top + (g.high - n[2]) * g.row + 2}px`,
      width: `${Math.max(8, n[1] / PPB * g.unit - 3)}px`, height: `${g.row - 4}px` };
  }
  function roll(s) {
    const center = clamp(0, s.bounds.low, s.bounds.high);
    const low = Math.max(s.bounds.low, Math.min(center, ...s.notes.map((n) => n[2])) - 2);
    const high = Math.min(s.bounds.high, Math.max(center + 12, ...s.notes.map((n) => n[2])) + 2);
    const g = { low, high, row: 19, top: 28, left: 58, start: s.bounds.start / PPB,
      unit: Math.max(42, ((document.getElementById("studio-composer")?.clientWidth || 700) - 100) / s.phrase.duration_beats) * s.zoom };
    const width = g.left + (s.bounds.end / PPB - g.start) * g.unit, height = g.top + (high - low + 1) * g.row;
    const box = el("div", { class: "sbc-roll", style: { width: `${width}px`, height: `${height}px` } });
    const plot = el("div", { class: "sbc-grid", style: { left: `${g.left}px`, top: `${g.top}px`, width: `${width - g.left}px`, height: `${height - g.top}px`, backgroundSize: `${g.unit * s.snap}px ${g.row}px` },
      ondblclick: (event) => { const r = plot.getBoundingClientRect(); add((g.start + (event.clientX - r.left) / g.unit) * PPB, g.high - Math.floor((event.clientY - r.top) / g.row)); } });
    box.append(plot);
    for (let pitch = high; pitch >= low; pitch--) {
      const key = pitch + s.tonic, y = g.top + (high - pitch) * g.row, black = [1, 3, 6, 8, 10].includes((key + 120) % 12);
      box.append(button(pitchName(key), () => s.hear([[0, 48, pitch, 96]]), { class: `sbc-key${black ? " is-black" : ""}`,
        "aria-label": `Hear ${pitchName(key)}`, style: { top: `${y}px`, height: `${g.row}px`, width: `${g.left - 4}px` } }));
    }
    for (let beat = 0; beat <= s.phrase.duration_beats; beat++) box.append(el("span", { class: "sbc-ruler-label", style: { left: `${g.left + (beat - g.start) * g.unit}px` } }, beat % s.perBar === 0 ? beat / s.perBar + 1 : "·"));
    s.notes.forEach((n, i) => box.append(button(pitchName(n[2] + s.tonic), () => select(i), { class: `sbc-note${s.mine ? " is-edited" : ""}${s.selected === i ? " is-selected" : ""}`,
      "data-part-note": i, "aria-pressed": s.selected === i, "aria-label": `${pitchName(n[2] + s.tonic)}, beat ${(n[0] / PPB + 1).toFixed(2)}, velocity ${n[3]}`,
      style: noteStyle(n, g), onpointerdown: (e) => drag(e, i, g), onkeydown: (e) => moveKey(e, i) })));
    return el("div", { class: "sbc-roll-scroll", tabindex: "0", "aria-label": `${s.player.label} piano roll` }, box);
  }
  function render(view, phrase, name, options) {
    if (phrase.part_editable === false) return el("p", { class: "notes-foot" }, "This is a generated extension. Choose one of the section's original phrases to write this instrument's notes.");
    const player = view.composition.players.find((p) => p.name === name), path = `part.${name}.${phrase.part_key}`;
    const key = `${view.listen?.whole || JSON.stringify(bridge().getEdits?.() || {})}|${path}`;
    if (!current || current.key !== key) {
      const saved = phrase.part_notes?.[name];
      const selected = current?.path === path ? current.selected : null;
      current = { id: ++serial, key, path, phrase, player, tonic: view.composition.tonic, perBar: view.composition.beats_per_bar,
        bounds: limits(view.composition, phrase, player), notes: saved ? copy(saved) : [], mine: saved !== undefined,
        ready: saved !== undefined, loading: saved === undefined, selected, ...options };
      if (current.loading) load(current);
    }
    const s = current; Object.assign(s, options);
    const n = s.notes[s.selected];
    return el("div", { class: "sbc-part-editor" },
      el("div", { class: "notes-foot", role: "group", "aria-label": "Edit instrument notes" },
        button("Add note", () => add(), { disabled: !s.ready }), button("Delete note", remove, { disabled: !n }),
        button("Copy notes", () => { clipboard = copy(s.notes); s.paint(); }, { disabled: !s.ready }),
        button("Paste notes", () => save(copy(clipboard)), { disabled: !clipboard }),
        button(s.ready ? "Clear notes" : "Start empty", () => save([])),
        button("Reset part", () => { bridge().releaseEdit(s.path); current = null; s.paint(); }, { disabled: !s.mine })),
      el("p", { class: "notes-foot", role: "status" }, s.error || (s.loading ? "Loading the instrument's notes…" : s.mine ? "Your notes · this phrase only" : "Generated notes · edit to make them yours"),
        s.error ? button("Retry", () => { s.error = null; s.loading = true; load(s); s.paint(); }) : null),
      s.ready ? roll(s) : null,
      n ? el("div", { class: "notes-foot" },
        field("Pitch (MIDI)", n[2] + s.tonic, s.bounds.low + s.tonic, s.bounds.high + s.tonic, 1, (v) => change(s.selected, { 2: Math.round(v) - s.tonic })),
        field("Start (beats)", n[0] / PPB, s.bounds.start / PPB, (s.bounds.end - 1) / PPB, s.snap, (v) => change(s.selected, { 0: Math.round(v * PPB) })),
        field("Length (beats)", n[1] / PPB, 1 / PPB, 32, s.snap, (v) => change(s.selected, { 1: Math.round(v * PPB) })),
        field("Velocity", n[3], 1, 127, 1, (v) => change(s.selected, { 3: Math.round(v) }))) : null,
      s.ready ? el("div", { class: "notes-foot" }, button("Hear phrase", () => s.hear(s.notes)),
        "Double-click to draw. Drag to move or resize. Arrow keys move; Shift + arrows change length.") : null);
  }
  window.SongbirdParts = { render, reset: () => { current = null; }, core: { limits, normalize } };
})();
