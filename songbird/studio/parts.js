// Pitched band parts use the same portable part.* notes as MIDI import.
// No samples or new file format: time is in 96ths of a beat, pitch relative to the key.
// The roll shows a whole section: each phrase's notes in its own time, kept as that phrase's part edit.
(() => {
  "use strict";
  const PPB = 96;
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const copy = (notes) => notes.map((n) => n.slice());
  const same = (a, b) => a.length === b.length && a.every((n, i) => n.every((v, k) => v === b[i][k]));
  const bridge = () => window.StudioBridge;
  let current = null, clipboard = null, serial = 0, lastClick = null;
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
        if (prev[0] === n[0]) throw new Error("This instrument plays one note at a time.");
        prev[1] = Math.min(prev[1], n[0] - prev[0]);
      }
      if (player.poly && out.filter((x) => x[0] + x[1] > n[0]).length >= 10)
        throw new Error("Use at most ten notes at once.");
      out.push(n);
    }
    return out;
  }
  // ---- several notes at once (pure: [start, length, pitch, velocity] in 96ths, pitch from the key)
  // the chosen notes moved together by dt (96ths) and dp (semitones), held so every one stays inside the phrase
  function shifted(notes, chosen, dt, dp, b) {
    const set = new Set(chosen), moving = notes.filter((_, i) => set.has(i));
    if (!moving.length) return copy(notes);
    const t = clamp(dt, Math.max(...moving.map((n) => b.start - n[0])), Math.min(...moving.map((n) => b.end - 1 - n[0])));
    const q = clamp(dp, Math.max(...moving.map((n) => b.low - n[2])), Math.min(...moving.map((n) => b.high - n[2])));
    return notes.map((n, i) => (set.has(i) ? [n[0] + t, n[1], n[2] + q, n[3]] : n.slice()));
  }
  function clipOf(notes, chosen) {
    const list = chosen.map((i) => notes[i]), start = Math.min(...list.map((n) => n[0]));
    return { start, notes: list.map((n) => [n[0] - start, n[1], n[2], n[3]]) };
  }
  // copied notes put in at a time (96ths of the phrase): beside the notes there, or, for an instrument that plays
  // one note at a time (mono), in place of the notes they overlap
  function pasted(notes, clip, at, b, mono = false) {
    const put = clip.notes.map((n) => [n[0] + at, n[1], n[2], n[3]]);
    if (!put.length || put.some((n) => n[0] < b.start || n[0] >= b.end || n[2] < b.low || n[2] > b.high))
      throw new Error("These notes don't fit here.");
    const kept = mono ? notes.filter((n) => !put.some((m) => n[0] < m[0] + m[1] && n[0] + n[1] > m[0])) : notes;
    return { notes: [...copy(kept), ...put], put };
  }
  // the chosen notes' starts and ends on the grid (96ths), each at least a grid step long
  function quantized(notes, chosen, grid, b) {
    const set = new Set(chosen);
    return notes.map((n, i) => {
      if (!set.has(i)) return n.slice();
      const on = clamp(Math.round(n[0] / grid) * grid, Math.ceil(b.start / grid) * grid, b.end - 1);
      const end = Math.max(Math.round((n[0] + n[1]) / grid) * grid, on + grid);
      return [on, clamp(end - on, 1, 32 * PPB), n[2], n[3]];
    });
  }
  async function ask(path, body) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json",
      "X-Studio": document.querySelector('meta[name="studio-token"]').content }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Couldn't load the notes. Try again.");
    return data;
  }
  // the program's notes for the section's phrases a person hasn't written, as the part edits they would be
  async function load(s) {
    try {
      const missing = s.lines.filter((x) => !x.ready);
      const edits = bridge().getEdits?.() || {}, data = await ask("/api/players", { edits });
      if (current !== s || !s.loading) return;
      // the notes in the windows of those phrases (each from just before its pickup to its end), never a written one's
      const inside = (t) => missing.some(({ p }) => t >= p.start_beat - (p.pickup_beats || 0) - 0.125 && t < p.start_beat + p.duration_beats);
      const notes = (data.players.find((x) => x.part === s.player.name)?.notes || []).filter((n) => inside(n[0]));
      const preview = await ask("/api/notes-in", { edits, take: { player: s.player.name, notes, lines: missing.map((x) => x.p.part_key) } });
      if (current !== s || !s.loading) return;
      if (preview.refused?.length) throw new Error(`${preview.refused[0].why}.`);
      for (const x of missing) { x.notes = copy(preview.changes.find((c) => c.path === x.path)?.value || []); x.ready = true; }
    } catch (error) { if (current === s && s.loading) s.error = error.message; }
    if (current === s) { s.loading = false; s.paint(); }
  }
  const line = () => current?.lines[current.focus];
  const chosenOf = (s = current) => [...s.selected].filter((i) => i < (s.lines[s.focus]?.notes.length || 0)).sort((a, z) => a - z);
  // a phrase's notes saved as its part edit; `keep`, the notes to select after, by their start and pitch
  function save(notes, keep = [], pi = current?.focus) {
    const s = current, x = s?.lines[pi];
    if (!x) return;
    try {
      const clean = normalize(notes, s.player, x.bounds), unchanged = x.ready && same(clean, x.notes);
      s.error = null; s.focus = pi;
      s.selected = new Set(keep.map((k) => clean.findIndex((n) => n[0] === k[0] && n[2] === k[2])).filter((i) => i >= 0));
      if (!unchanged) {  // nothing changed: no edit, no undo step (the program's notes stay the program's)
        x.notes = clean; x.ready = true; x.mine = true;
        bridge().setEdit(x.path, clean);
      }
      s.paint();
    } catch (error) { s.error = error.message; s.paint(); }
  }
  function focusLine(pi) {
    const s = current;
    if (s.focus === pi) return false;
    s.focus = pi; s.selected = new Set(); s.cursor = null; s.choose?.(s.lines[pi].p);
    return true;
  }
  function add(onset = null, pitch = null, length = null) {
    const s = current, x = line(); if (!x?.ready) return;
    const grid = Math.max(1, Math.round(s.snap * PPB)), chosen = chosenOf(), last = x.notes[chosen.at(-1)];
    const start = onset ?? (s.cursor?.pi === s.focus ? s.cursor.t : last ? last[0] + last[1] : 0);
    const n = [clamp(Math.round(start / grid) * grid, x.bounds.start, x.bounds.end - 1), Math.max(grid, Math.round((length ?? grid) / grid) * grid),
      clamp(Math.round(pitch ?? last?.[2] ?? 0), x.bounds.low, x.bounds.high), 96];
    s.focusNote = true;
    save([...x.notes, n], [n]);
  }
  function change(index, changes) {
    const notes = copy(line().notes), n = notes[index];
    if (!n) return;
    Object.assign(n, changes); save(notes, [n]);
  }
  function remove() {
    const x = line(), chosen = new Set(chosenOf());
    if (!x || !chosen.size) return;
    save(x.notes.filter((_, i) => !chosen.has(i)));
  }
  function move(dt, dp) {
    const x = line(), chosen = chosenOf();
    if (!x || !chosen.length) return;
    const notes = shifted(x.notes, chosen, dt, dp, x.bounds);
    save(notes, chosen.map((i) => notes[i]));
  }
  function selectAll() { const s = current, x = line(); if (!x?.notes.length) return; s.selected = new Set(x.notes.map((_, i) => i)); s.focusNote = true; s.paint(); }
  function copyNotes(quiet = false) {
    const x = line(); if (!x?.ready) return false;
    const chosen = chosenOf();
    clipboard = chosen.length ? clipOf(x.notes, chosen) : { start: x.bounds.start, notes: x.notes.map((n) => [n[0] - x.bounds.start, n[1], n[2], n[3]]), whole: true };
    if (!quiet) { current.paint(); bridge().toast?.(chosen.length ? `${chosen.length} note${chosen.length === 1 ? "" : "s"} copied.` : "The phrase's notes copied."); }
    return true;
  }
  function paste(at = null) {
    const s = current, x = line(); if (!clipboard || !x?.ready) return;
    if (clipboard.whole && at === null) { save(clipboard.notes.map((n) => [n[0] + x.bounds.start, n[1], n[2], n[3]]).filter((n) => n[0] < x.bounds.end)); return; }
    const chosen = chosenOf(), end = chosen.length ? Math.max(...chosen.map((i) => x.notes[i][0] + x.notes[i][1])) : 0;
    try {
      const { notes, put } = pasted(x.notes, clipboard, at ?? (s.cursor?.pi === s.focus ? s.cursor.t : chosen.length ? end : 0), x.bounds, !s.player.poly);
      s.focusNote = true; save(notes, put);
    } catch (error) { bridge().toast?.(error.message); }
  }
  function duplicate() {
    const x = line(), chosen = chosenOf();
    if (!chosen.length) { bridge().toast?.("Select notes to duplicate."); return; }
    const clip = clipOf(x.notes, chosen), end = Math.max(...chosen.map((i) => x.notes[i][0] + x.notes[i][1]));
    try { const { notes, put } = pasted(x.notes, clip, end, x.bounds, !current.player.poly); current.focusNote = true; save(notes, put); }
    catch (error) { bridge().toast?.("No room to duplicate here."); }
  }
  function quantize() {
    const s = current, x = line(); if (!x?.ready || !x.notes.length) return;
    const chosen = chosenOf(), all = chosen.length ? chosen : x.notes.map((_, i) => i);
    const notes = quantized(x.notes, all, Math.max(1, Math.round(s.snap * PPB)), x.bounds);
    save(notes, chosen.map((i) => notes[i]));
  }
  function shortcut(e) {
    const key = window.SongbirdModel?.rollKey?.(e);
    if (!key) return;
    e.preventDefault(); e.stopPropagation?.();
    ({ all: selectAll, copy: () => copyNotes(), cut: () => { if (chosenOf().length && copyNotes(true)) remove(); }, paste: () => paste(), duplicate })[key.action]();
  }
  function moveKey(e, pi, index) {
    if (!["Delete", "Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault(); e.stopPropagation?.();
    const s = current;
    focusLine(pi);
    if (!s.selected.has(index) || (e.shiftKey && ["ArrowLeft", "ArrowRight"].includes(e.key))) s.selected = new Set([index]);
    s.focusNote = true;
    if (e.key === "Delete" || e.key === "Backspace") { remove(); return; }
    const dir = ["ArrowUp", "ArrowRight"].includes(e.key) ? 1 : -1, step = Math.round(s.snap * PPB);
    if (["ArrowUp", "ArrowDown"].includes(e.key)) move(0, dir * (e.altKey ? 12 : 1));
    else if (e.shiftKey) { const n = line().notes[index]; change(index, { 1: clamp(n[1] + dir * step, 1, 32 * PPB) }); }
    else move(dir * step, 0);
  }
  function choose(e, pi, index) {  // a click: the note alone, or with Shift added to the selection or taken from it
    const s = current;
    if (s.drag?.moved) return;
    const other = focusLine(pi);
    if (e.shiftKey && !other) { if (s.selected.has(index)) s.selected.delete(index); else s.selected.add(index); }
    else s.selected = new Set([index]);
    s.cursor = null; s.focusNote = true; s.paint();
  }
  function drag(e, pi, index, g) {
    if (e.button !== 0 || e.shiftKey || window.SongbirdScore?.narrow?.()) return;
    const s = current, target = e.currentTarget, rect = target.getBoundingClientRect();
    if (focusLine(pi) || !s.selected.has(index)) { s.selected = new Set([index]); }
    const x = line(), group = chosenOf(), n = x.notes[index].slice(), x0 = e.clientX, y0 = e.clientY;
    const handle = window.SongbirdModel.grip(rect.width), resize = e.altKey || (handle > 0 && e.clientX > rect.right - handle);
    let preview = copy(x.notes), moved = false;
    s.drag = { moved: false };
    target.setPointerCapture(e.pointerId);
    const nodes = () => [...(target.parentNode?.querySelectorAll?.(".sbc-note") || [])];
    const draw = () => nodes().forEach((node) => { const [p, i] = String(node.dataset.partNote).split(".").map(Number); if (p === pi && preview[i]) Object.assign(node.style, noteStyle(preview[i], g, g.lines[pi].off)); });
    const motion = (event) => {
      if (Math.abs(event.clientX - x0) + Math.abs(event.clientY - y0) < 4 && !moved) return;
      moved = true; s.drag.moved = true;
      const dt = Math.round((event.clientX - x0) / g.unit / s.snap) * Math.round(s.snap * PPB);
      if (resize) { preview = copy(x.notes); preview[index][1] = clamp(n[1] + dt, 1, 32 * PPB); }
      else preview = shifted(x.notes, group, dt, -Math.round((event.clientY - y0) / g.row), x.bounds);
      draw();
    };
    const finish = (event) => {
      target.removeEventListener("pointermove", motion); target.removeEventListener("pointerup", finish); target.removeEventListener("pointercancel", cancel);
      if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId);
      if (current === s && moved) save(preview, group.map((i) => preview[i]));
      setTimeout(() => { if (s.drag?.moved !== undefined) s.drag = null; }, 0);
    };
    const cancel = (event) => { moved = false; preview = copy(x.notes); draw(); finish(event); };
    target.addEventListener("pointermove", motion); target.addEventListener("pointerup", finish); target.addEventListener("pointercancel", cancel);
  }
  // on the empty grid: a click puts the cursor there, two add a note, a drag draws one, a Shift-drag selects
  function empty(e, g, plot) {
    if (e.button !== 0 || window.SongbirdScore?.narrow?.()) return;
    const s = current, r = plot.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    const at = (cx, cy) => ({ beat: g.start + (cx - r.left) / g.unit, pitch: g.high - Math.floor((cy - r.top) / g.row) });
    const down = at(x0, y0), pi = window.SongbirdModel.phraseAt(g.lines, down.beat);
    if (pi === null) return;
    const off = g.lines[pi].off, select = e.shiftKey, snap = (beat) => Math.round(beat / s.snap) * s.snap;
    const drawn = (beat) => { const a = snap(Math.min(down.beat, beat)), z = Math.max(snap(Math.max(down.beat, beat)), a + s.snap); return [Math.round((a - off) * PPB), Math.round((z - a) * PPB)]; };
    const box = el("div", { class: select ? "sbc-marquee" : "sbc-note is-drawing", hidden: true, "aria-hidden": "true" });
    plot.parentNode?.append(box);
    let moved = false;
    plot.setPointerCapture?.(e.pointerId);
    const motion = (event) => {
      if (!moved && Math.abs(event.clientX - x0) + Math.abs(event.clientY - y0) < 4) return;
      moved = true; box.hidden = false;
      if (select) Object.assign(box.style, { left: `${g.left + Math.min(x0, event.clientX) - r.left}px`, top: `${g.top + Math.min(y0, event.clientY) - r.top}px`, width: `${Math.abs(event.clientX - x0)}px`, height: `${Math.abs(event.clientY - y0)}px` });
      else { const [t, d] = drawn(at(event.clientX, event.clientY).beat); Object.assign(box.style, noteStyle([t, d, down.pitch, 96], g, off)); }
    };
    const up = (event) => {
      plot.removeEventListener("pointermove", motion); plot.removeEventListener("pointerup", up); plot.removeEventListener("pointercancel", cancel);
      if (plot.hasPointerCapture?.(event.pointerId)) plot.releasePointerCapture(event.pointerId);
      box.remove?.();
      const z = at(event.clientX, event.clientY);
      focusLine(pi);
      if (moved && !select) { const [t, d] = drawn(z.beat); add(t, down.pitch, d); return; }
      if (moved) {
        const lo = Math.min(down.beat, z.beat) - off, hi = Math.max(down.beat, z.beat) - off, top = Math.max(down.pitch, z.pitch), bottom = Math.min(down.pitch, z.pitch);
        s.selected = new Set(line().notes.flatMap((n, i) => (n[0] / PPB < hi && (n[0] + n[1]) / PPB > lo && n[2] <= top && n[2] >= bottom ? [i] : [])));
        s.focusNote = true; s.paint(); return;
      }
      const now = Date.now(), twice = lastClick && now - lastClick.time < 450 && Math.abs(lastClick.x - x0) + Math.abs(lastClick.y - y0) < 8;
      lastClick = twice ? null : { time: now, x: x0, y: y0 };
      if (twice) { add(Math.round((down.beat - off) * PPB), down.pitch); return; }
      s.selected = new Set(); s.cursor = { pi, t: Math.round(snap(down.beat - off) * PPB) }; s.paint();
    };
    const cancel = () => { box.remove?.(); plot.removeEventListener("pointermove", motion); plot.removeEventListener("pointerup", up); plot.removeEventListener("pointercancel", cancel); };
    plot.addEventListener("pointermove", motion); plot.addEventListener("pointerup", up); plot.addEventListener("pointercancel", cancel);
  }
  function noteStyle(n, g, off) {
    return { left: `${g.left + (off + n[0] / PPB - g.start) * g.unit + 1}px`, top: `${g.top + (g.high - n[2]) * g.row + 2}px`,
      width: `${Math.max(8, n[1] / PPB * g.unit - 3)}px`, height: `${g.row - 4}px` };
  }
  function roll(s) {
    const ready = s.lines.filter((x) => x.ready), all = ready.flatMap((x) => x.notes);
    const bLow = Math.min(...s.lines.map((x) => x.bounds.low)), bHigh = Math.max(...s.lines.map((x) => x.bounds.high));
    const center = clamp(0, bLow, bHigh);
    const low = Math.max(bLow, Math.min(center, ...all.map((n) => n[2])) - 2);
    const high = Math.min(bHigh, Math.max(center + 12, ...all.map((n) => n[2])) + 2);
    const lines = s.lines.map((x, i) => ({ i, off: x.off, start: x.off + x.bounds.start / PPB, end: x.off + x.bounds.end / PPB,
      final: x.off + x.bounds.end / PPB }));
    const start = Math.min(0, ...lines.map((x) => x.start)), end = Math.max(...lines.map((x) => x.end));
    const g = { low, high, row: 19, top: 28, left: 58, start, lines,
      unit: window.SongbirdModel.rollUnit(s.zoom, (document.getElementById("studio-composer")?.clientWidth || 700) - 100, end - start) };
    const width = g.left + (end - start) * g.unit, height = g.top + (high - low + 1) * g.row;
    const box = el("div", { class: "sbc-roll", style: { width: `${width}px`, height: `${height}px` } });
    const plot = el("div", { class: "sbc-grid", style: { left: `${g.left}px`, top: `${g.top}px`, width: `${width - g.left}px`, height: `${height - g.top}px`, backgroundSize: `${g.unit * s.snap}px ${g.row}px` },
      onpointerdown: (event) => empty(event, g, plot) });
    box.append(plot);
    const here = lines[s.focus];
    if (here) box.append(el("div", { class: "sbc-phrase-span", style: { left: `${g.left + (here.start - start) * g.unit}px`, top: `${g.top}px`, width: `${(here.end - here.start) * g.unit}px`, height: `${height - g.top}px` } }));
    for (const x of lines.slice(1)) box.append(el("div", { class: "sbc-phrase-line", style: { left: `${g.left + (x.off - start) * g.unit}px`, top: "0px", height: `${height}px` } }));
    if (s.cursor && lines[s.cursor.pi]) box.append(el("div", { class: "sbc-cursor", "aria-hidden": "true", style: { left: `${g.left + (lines[s.cursor.pi].off + s.cursor.t / PPB - start) * g.unit}px`, top: `${g.top}px`, height: `${height - g.top}px` } }));
    for (let pitch = high; pitch >= low; pitch--) {
      const key = pitch + s.tonic, y = g.top + (high - pitch) * g.row, black = [1, 3, 6, 8, 10].includes((key + 120) % 12);
      box.append(button(pitchName(key), () => s.hear([[0, 48, pitch, 96]]), { class: `sbc-key${black ? " is-black" : ""}`,
        "aria-label": `Hear ${pitchName(key)}`, style: { top: `${y}px`, height: `${g.row}px`, width: `${g.left - 4}px` } }));
    }
    for (let beat = Math.ceil(start); beat <= end; beat++) box.append(el("span", { class: `sbc-ruler-label${beat >= 0 && beat % s.perBar === 0 ? " is-bar" : ""}`, style: { left: `${g.left + (beat - start) * g.unit}px` } },
      beat < 0 ? "↗" : beat % s.perBar === 0 ? beat / s.perBar + 1 : "·"));
    s.lines.forEach((x, pi) => x.notes.forEach((n, i) => {
      const on = pi === s.focus && s.selected.has(i), name = pitchName(n[2] + s.tonic), style = noteStyle(n, g, x.off);
      const wide = parseFloat(style.width), handle = window.SongbirdModel.grip(wide);
      const item = button(window.SongbirdModel.labelFits(name, wide - handle, { char: 6.2 }) ? name : "", (e) => choose(e, pi, i), {
        class: `sbc-note${x.mine ? " is-edited" : ""}${on ? " is-selected" : ""}`, title: `${name}. Drag to move; drag its right edge, or ⌥-drag, to change its length.`,
        "data-part-note": `${pi}.${i}`, "aria-pressed": String(on), "aria-label": `${name}, phrase ${pi + 1}, beat ${(n[0] / PPB + 1).toFixed(2)}, velocity ${n[3]}`,
        style, onpointerdown: (e) => drag(e, pi, i, g), onkeydown: (e) => moveKey(e, pi, i) });
      if (handle) item.append(el("span", { class: "sbc-resize", "aria-hidden": "true", style: { width: `${handle}px` } }));
      box.append(item);
    }));
    return el("div", { class: "sbc-roll-scroll", id: "sbc-part-roll", tabindex: "0", "aria-label": `${s.player.label} piano roll`, onkeydown: shortcut }, box);
  }
  function render(view, section, name, options) {
    const player = view.composition.players.find((p) => p.name === name);
    const phrases = (section.phrases || []).filter((p) => p.part_editable !== false);
    if (!phrases.length) return el("p", { class: "notes-foot" }, "The arrangement added this section's phrases. Their notes can't be written.");
    const key = `${view.listen?.whole || JSON.stringify(bridge().getEdits?.() || {})}|${section.id}|${name}`;
    if (!current || current.key !== key) {
      const was = current?.sid === section.id && current?.player.name === name ? current : null;
      const lines = phrases.map((p) => {
        const saved = p.part_notes?.[name];
        return { p, path: `part.${name}.${p.part_key}`, off: (p.start_beat ?? section.start_beat) - section.start_beat,
          bounds: limits(view.composition, p, player), notes: saved ? copy(saved) : [], mine: saved !== undefined, ready: saved !== undefined };
      });
      current = { id: ++serial, key, sid: section.id, player, tonic: view.composition.tonic, perBar: view.composition.beats_per_bar, lines,
        focus: was?.focus ?? 0, selected: was?.selected ?? new Set(), cursor: was?.cursor ?? null, loading: lines.some((x) => !x.ready), ...options };
      if (current.loading) load(current);
    }
    const s = current; Object.assign(s, options);
    const at = phrases.indexOf(section.phrases?.[options.phrase]);
    if (at >= 0 && at !== s.focus) { s.focus = at; s.selected = new Set(); s.cursor = null; }
    s.focus = clamp(s.focus, 0, s.lines.length - 1);
    const x = line(), chosen = chosenOf(), n = chosen.length === 1 ? x.notes[chosen[0]] : null, ready = s.lines.every((y) => y.ready);
    const out = el("div", { class: "sbc-part-editor" },
      el("div", { class: "notes-foot", role: "group", "aria-label": "Edit instrument notes" },
        button("Add note", () => add(), { disabled: !x.ready }), button(chosen.length > 1 ? "Delete notes" : "Delete note", remove, { disabled: !chosen.length }),
        button("Copy notes", () => copyNotes(), { disabled: !x.ready, title: "Copy the selected notes, or the phrase (Ctrl+C)" }),
        button("Paste notes", () => paste(), { disabled: !clipboard, title: "Paste (Ctrl+V)" }),
        button("Quantize", quantize, { disabled: !x.ready, title: "Put the selected notes, or the phrase, on the snap" }),
        button(x.ready ? "Clear notes" : "Start empty", () => save([])),
        button("Reset part", () => { bridge().releaseEdit(x.path); current = null; s.paint(); }, { disabled: !x.mine })),
      el("p", { class: "notes-foot", role: "status" }, s.error || (s.loading ? "Loading the instrument's notes…" : x.mine ? "Your notes" : "The program's notes"),
        s.error ? button("Retry", () => { s.error = null; s.loading = true; load(s); s.paint(); }) : null),
      ready || s.lines.some((y) => y.ready) ? roll(s) : null,
      n ? el("div", { class: "notes-foot" },
        field("Pitch (MIDI)", n[2] + s.tonic, x.bounds.low + s.tonic, x.bounds.high + s.tonic, 1, (v) => change(chosen[0], { 2: Math.round(v) - s.tonic })),
        field("Start (beats)", n[0] / PPB, x.bounds.start / PPB, (x.bounds.end - 1) / PPB, s.snap, (v) => change(chosen[0], { 0: Math.round(v * PPB) })),
        field("Length (beats)", n[1] / PPB, 1 / PPB, 32, s.snap, (v) => change(chosen[0], { 1: Math.round(v * PPB) })),
        field("Velocity", n[3], 1, 127, 1, (v) => change(chosen[0], { 3: Math.round(v) }))) : null,
      x.ready ? el("div", { class: "notes-foot" }, button("Hear phrase", () => s.hear(x.notes, x.p)),
        el("span", { title: "Arrow keys move the selected notes; ⇧ ← → a note's length; Delete removes; Ctrl or ⌘ with C, X, V, D, A: copy, cut, paste, duplicate, select all." },
          "Drag on the grid to draw a note; Shift-drag to select.")) : null);
    return out;
  }
  // a browser that keeps the focus on the page when a note is clicked: the roll's shortcuts while notes are selected
  if (typeof document !== "undefined") document.addEventListener?.("keydown", (e) => {
    if (e.target === document.body && current?.selected.size && document.getElementById("sbc-part-roll")) shortcut(e);
  });
  window.SongbirdParts = { render, reset: () => { current = null; }, focus: () => current?.focusNote ? `${current.focus}.${chosenOf()[0] ?? 0}` : null,
    focused: () => { if (current) current.focusNote = false; }, core: { limits, normalize, shifted, clipOf, pasted, quantized } };
})();
