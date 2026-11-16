// A percussion player's part as a step grid: one row a piece, one column a step of the snap.
// The same portable part.* notes as pitched parts: [onset, length, piece, velocity], time in 96ths of a beat
// from the phrase's first bar line, the piece a place in the player's own pieces (the view's player.drums).
(() => {
  "use strict";
  const PPB = 96, LONGEST = 32 * PPB, LINE = 512, BEAT_STARTS = 32;
  // velocity levels a stroke is drawn and set at; a stroke from elsewhere keeps its own velocity until set
  const LEVELS = [{ name: "ghost", label: "Ghost", velocity: 40 }, { name: "normal", label: "Normal", velocity: 90 },
    { name: "accent", label: "Accent", velocity: 120 }];
  const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
  const copy = (notes) => notes.map((n) => n.slice());
  const same = (a, b) => a.length === b.length && a.every((n, i) => n.every((v, k) => v === b[i][k]));
  const bridge = () => window.StudioBridge;
  let current = null, clipboard = null, level = 1;

  // ---- pure: the grid and the notes (tests/studio_drums.test.cjs)

  function levelOf(velocity) { return velocity <= 60 ? 0 : velocity >= 110 ? 2 : 1; }
  function bounds(phrase) {
    return { start: -Math.round((phrase.pickup_beats || 0) * PPB), end: Math.round(phrase.duration_beats * PPB) };
  }
  function stepOf(snap) { return Math.max(1, Math.round(snap * PPB)); }
  // each column's onset: the snap's steps from the first bar line, and the pickup's start where it falls between
  function columns(b, snap) {
    const step = stepOf(snap), first = Math.ceil(b.start / step) * step, out = first > b.start ? [b.start] : [];
    for (let t = first; t < b.end; t += step) out.push(t);
    return out;
  }
  // the column a stroke shows in: the one whose onset is nearest (a stroke a little early or late stays on its step)
  function cellOf(onset, cols) {
    let best = 0;
    for (let i = 1; i < cols.length; i++) if (Math.abs(cols[i] - onset) < Math.abs(cols[best] - onset)) best = i;
    return best;
  }
  function hitsAt(notes, cols, row, col) {
    const out = [];
    notes.forEach((n, i) => { if (n[2] === row && cellOf(n[0], cols) === col) out.push(i); });
    return out;
  }
  // a cell struck or cleared: `on` true adds a stroke at the column's onset (none if one is there), false clears it
  function setCell(notes, cols, row, col, on, step, velocity) {
    const here = hitsAt(notes, cols, row, col);
    if (on) return here.length ? notes : [...notes, [cols[col], step, row, velocity]];
    return here.length ? notes.filter((_, i) => !here.includes(i)) : notes;
  }
  function setVelocity(notes, indices, velocity) {
    return notes.map((n, i) => (indices.includes(i) ? [n[0], n[1], n[2], velocity] : n));
  }
  function setLength(notes, indices, length) {
    return notes.map((n, i) => (indices.includes(i) ? [n[0], clamp(length, 1, LONGEST), n[2], n[3]] : n));
  }
  // checked as the studio checks them (composition._check_strokes): sorted, a piece struck twice at once kept once
  function normalize(notes, pieces, b) {
    if (notes.length > LINE) throw new Error(`Use at most ${LINE} strokes in a phrase.`);
    const sorted = copy(notes).sort((a, z) => a[0] - z[0] || a[2] - z[2] || z[1] - a[1]);
    const out = [], starts = new Map();
    for (const n of sorted) {
      if (n.length !== 4 || n.some((v) => !Number.isInteger(v)) || n[0] < b.start || n[0] >= b.end ||
        n[1] < 1 || n[1] > LONGEST || n[2] < 0 || n[2] >= pieces || n[3] < 1 || n[3] > 127)
        throw new Error("Keep strokes inside the phrase.");
      const prev = out.at(-1);
      if (prev && prev[0] === n[0] && prev[2] === n[2]) continue;
      const beat = Math.floor(n[0] / PPB), count = (starts.get(beat) || 0) + 1;
      starts.set(beat, count);
      if (count > BEAT_STARTS) throw new Error(`Use at most ${BEAT_STARTS} strokes in a beat.`);
      out.push(n);
    }
    return out;
  }
  // strokes pasted into another phrase: those that fit it
  function fit(notes, pieces, b) { return copy(notes).filter((n) => n[0] >= b.start && n[0] < b.end && n[2] < pieces); }

  // ---- the sketch's drum sounds: a quick stand-in for the instrument, made in the browser

  function voice(name) {
    if (/kick|bass|stomp|tom-lo|conga-lo/.test(name)) return { kind: "low", f: 70, d: 0.22 };
    if (/tom|conga|top|tip/.test(name)) return { kind: "low", f: /hi/.test(name) ? 190 : 140, d: 0.18 };
    if (/crash|ride|open|roll|sweep|shake/.test(name)) return { kind: "noise", f: 6000, d: /crash/.test(name) ? 0.9 : 0.35 };
    if (/hat|shaker|maracas|tambourine|tap|cowbell|clave|bell/.test(name)) return { kind: "noise", f: 7500, d: 0.06 };
    return { kind: "snare", f: 1800, d: 0.14 };  // snare, rim, cross-stick, clap, snap, slap, mute
  }
  // strokes [onset, length, piece, velocity] played from `when` at `tempo`; the nodes made, for the host to stop
  function play(ctx, strokes, player, tempo, destination = ctx.destination, when = ctx.currentTime + 0.03) {
    const unit = 60 / tempo, origin = Math.min(0, ...strokes.map((n) => n[0])), nodes = [];
    let noise = null;
    for (const [onset, length, piece, velocity] of strokes) {
      const v = voice(player.drums?.[piece]?.name || ""), t = when + (onset - origin) / PPB * unit;
      const d = /roll|sweep|shake/.test(player.drums?.[piece]?.name || "") ? Math.max(v.d, length / PPB * unit) : v.d;
      const gain = ctx.createGain(), peak = 0.25 * (velocity / 127);
      gain.gain.setValueAtTime(peak, t);
      gain.gain.exponentialRampToValueAtTime(0.0005, t + d);
      gain.connect(destination);
      let source;
      if (v.kind === "low") {
        source = ctx.createOscillator();
        source.frequency.setValueAtTime(v.f * 2, t);
        source.frequency.exponentialRampToValueAtTime(v.f, t + 0.05);
      } else {
        if (!noise) {
          noise = ctx.createBuffer(1, Math.round(ctx.sampleRate), ctx.sampleRate);
          const data = noise.getChannelData(0);
          let x = 1;
          for (let i = 0; i < data.length; i++) { x = (x * 16807) % 2147483647; data[i] = x / 1073741823.5 - 1; }
        }
        source = ctx.createBufferSource();
        source.buffer = noise;
      }
      let into = gain;
      if (v.kind !== "low" && ctx.createBiquadFilter) {
        const filter = ctx.createBiquadFilter();
        filter.type = v.kind === "snare" ? "bandpass" : "highpass";
        filter.frequency.value = v.f;
        filter.connect(gain); into = filter; nodes.push(filter);
      }
      source.connect(into);
      source.start(t); source.stop(t + d + 0.02);
      nodes.push(source, gain);
    }
    return nodes;
  }

  // ---- the page

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
  async function ask(path, body) {
    const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json",
      "X-Studio": document.querySelector('meta[name="studio-token"]').content }, body: JSON.stringify(body) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Couldn't load the part. Try again.");
    return data;
  }
  // the program's strokes in this phrase, as pieces (/api/players' strokes), made an edit's numbers by notes-in
  async function load(s) {
    try {
      const edits = bridge().getEdits?.() || {}, data = await ask("/api/players", { edits });
      if (current !== s || !s.loading) return;
      const p = s.phrase, from = p.start_beat - (p.pickup_beats || 0) - 0.125, end = p.start_beat + p.duration_beats;
      const notes = (data.players.find((x) => x.part === s.player.name)?.strokes || []).filter((n) => n[0] >= from && n[0] < end);
      const preview = await ask("/api/notes-in", { edits, take: { player: s.player.name, notes, lines: [p.part_key] } });
      if (current !== s || !s.loading) return;
      if (preview.refused?.length) throw new Error(`${preview.refused[0].why}.`);
      s.notes = copy(preview.changes.find((x) => x.path === s.path)?.value || []);
      s.ready = true;
    } catch (error) { if (current === s && s.loading) s.error = error.message; }
    if (current === s) { s.loading = false; s.paint(); }
  }
  function save(notes) {
    const s = current;
    if (!s) return;
    try {
      const clean = normalize(notes, s.player.drums.length, s.bounds);
      s.error = null; s.loading = false;
      if (s.ready && same(clean, s.notes)) { s.paint(); return; }  // nothing changed: no edit, no undo step
      s.notes = clean; s.ready = true; s.mine = true;
      bridge().setEdit(s.path, clean);
      s.paint();
    } catch (error) { s.error = error.message; s.paint(); }
  }
  const cellId = (row, col) => `drum:${row}:${col}`;
  // the cell given the keys: focused before the page is drawn again, so the page keeps it (data-part-note)
  function take(row, col) {
    const s = current;
    s.focus = { row: clamp(row, 0, s.player.drums.length - 1), col: clamp(col, 0, s.cols.length - 1) };
    document.querySelector(`[data-part-note="${cellId(s.focus.row, s.focus.col)}"]`)?.focus({ preventScroll: false });
  }
  function focusCell(row, col) { take(row, col); current.paint(); }
  function keydown(e) {
    const s = current, [row, col] = e.currentTarget.dataset.drumCell.split(":").map(Number);
    s.focus = { row, col };
    const here = hitsAt(s.notes, s.cols, row, col);
    const step = stepOf(s.snap);
    const moves = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    if (e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {  // the stroke's level
      if (!here.length) return;
      const now = levelOf(s.notes[here[0]][3]), next = clamp(now + (e.key === "ArrowUp" ? 1 : -1), 0, 2);
      level = next; save(setVelocity(s.notes, here, LEVELS[next].velocity));
    } else if (e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {  // how long it is held
      if (!here.length) return;
      save(setLength(s.notes, here, s.notes[here[0]][1] + (e.key === "ArrowRight" ? step : -step)));
    } else if (moves[e.key]) focusCell(row + moves[e.key][0], col + moves[e.key][1]);
    else if (e.key === "Home") focusCell(row, 0);
    else if (e.key === "End") focusCell(row, s.cols.length - 1);
    else if (e.key === " " || e.key === "Enter") save(setCell(s.notes, s.cols, row, col, !here.length, step, LEVELS[level].velocity));
    else if (e.key === "Delete" || e.key === "Backspace") save(setCell(s.notes, s.cols, row, col, false, step, 0));
    else return;
    e.preventDefault(); e.stopPropagation();
  }
  // a press on a cell strikes or clears it, and a drag paints the same across the cells it passes; ⇧ on a
  // stroke raises its level, ⌥ lowers it
  function press(e, row, col) {
    const s = current;
    if (e.button !== 0 || !s?.ready) return;
    e.preventDefault();
    take(row, col);
    const step = stepOf(s.snap), here = hitsAt(s.notes, s.cols, row, col);
    if (here.length && (e.shiftKey || e.altKey)) {
      const next = clamp(levelOf(s.notes[here[0]][3]) + (e.shiftKey ? 1 : -1), 0, 2);
      level = next; save(setVelocity(s.notes, here, LEVELS[next].velocity));
      return;
    }
    const on = !here.length, grid = e.currentTarget.closest(".sbc-drum-grid");
    let notes = setCell(s.notes, s.cols, row, col, on, step, LEVELS[level].velocity);
    const mark = (cell) => cell.classList.toggle("is-hit", on);
    mark(e.currentTarget);
    if (e.pointerType === "touch") { save(notes); return; }  // a finger strikes one cell; a drag scrolls
    grid.setPointerCapture(e.pointerId);
    const move = (event) => {
      const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest?.("[data-drum-cell]");
      if (!cell || !grid.contains(cell)) return;
      const [r, c] = cell.dataset.drumCell.split(":").map(Number);
      notes = setCell(notes, s.cols, r, c, on, step, LEVELS[level].velocity);
      mark(cell);
      take(r, c);
    };
    const finish = (event) => {
      grid.removeEventListener("pointermove", move); grid.removeEventListener("pointerup", finish); grid.removeEventListener("pointercancel", cancel);
      if (grid.hasPointerCapture(event.pointerId)) grid.releasePointerCapture(event.pointerId);
      if (current === s) save(notes);
    };
    const cancel = (event) => { notes = s.notes; finish(event); };
    grid.addEventListener("pointermove", move); grid.addEventListener("pointerup", finish); grid.addEventListener("pointercancel", cancel);
  }
  function grid(s) {
    const step = stepOf(s.snap), cols = s.cols, pieces = s.player.drums;
    const unit = window.SongbirdModel.rollUnit(s.zoom, (document.getElementById("studio-composer")?.clientWidth || 700) - 100, s.phrase.duration_beats, { least: 42 });
    const width = (k) => ((cols[k + 1] ?? s.bounds.end) - cols[k]) / PPB * unit;
    const template = `var(--sbc-drum-label) ${cols.map((_, k) => `${width(k)}px`).join(" ")}`;
    const bar = s.perBar * PPB, hits = new Map();
    s.notes.forEach((n) => { const key = `${n[2]}:${cellOf(n[0], cols)}`; if (!hits.has(key)) hits.set(key, n); });
    const where = (t) => `beat ${(t / PPB + 1).toFixed(2).replace(/\.00$/, "")}`;
    const style = { gridTemplateColumns: template };
    const ruler = el("div", { class: "sbc-drum-row sbc-drum-ruler", "aria-hidden": "true", style }, el("span", {}),
      cols.map((t) => el("span", { class: `sbc-drum-tick${t % bar === 0 ? " is-bar" : ""}` },
        t % bar === 0 ? t / bar + 1 : t % PPB === 0 ? "·" : "")));
    const rows = pieces.map((piece, row) => el("div", { class: "sbc-drum-row", role: "row", style },
      el("span", { role: "rowheader", class: "sbc-drum-head" }, button(piece.label, () => s.hear([[0, step, row, LEVELS[level].velocity]]),
        { class: "sbc-drum-piece", "aria-label": `Hear ${piece.label}` })),
      cols.map((t, col) => {
        const n = hits.get(`${row}:${col}`), focused = s.focus.row === row && s.focus.col === col;
        const lv = n ? LEVELS[levelOf(n[3])] : null;
        return el("span", { role: "gridcell", tabindex: focused ? "0" : "-1", "data-drum-cell": `${row}:${col}`, "data-part-note": cellId(row, col),
          class: `sbc-drum-cell${n ? ` is-hit is-${lv.name}` : ""}${s.mine ? " is-edited" : ""}${t % bar === 0 ? " is-bar" : t % PPB === 0 ? " is-beat" : ""}`,
          "aria-label": `${piece.label}, ${where(t)}${n ? `, ${lv.label.toLowerCase()}` : ""}`,
          onpointerdown: (e) => press(e, row, col), onkeydown: keydown, onfocus: () => { s.focus = { row, col }; } },
        n && n[1] > step ? el("i", { class: "sbc-drum-held", style: { width: `${Math.min(n[1] / PPB * unit, 4000) - 4}px` } }) : null);
      })));
    return el("div", { class: "sbc-roll-scroll", "aria-label": `${s.player.label} steps` },
      el("div", { class: "sbc-drum-grid", role: "grid", "aria-label": `${s.player.label}: ${pieces.length} pieces` }, ruler, rows));
  }
  function render(view, phrase, name, options) {
    if (phrase.part_editable === false) return el("p", { class: "notes-foot" }, "The arrangement added this phrase. Its part can't be written.");
    const player = view.composition.players.find((p) => p.name === name), path = `part.${name}.${phrase.part_key}`;
    if (!player?.drums?.length) return el("p", { class: "notes-foot" }, "This player's part can't be written yet.");
    const key = `${view.listen?.whole || JSON.stringify(bridge().getEdits?.() || {})}|${path}`;
    if (!current || current.key !== key) {
      const saved = phrase.part_notes?.[name], focus = current?.path === path ? current.focus : { row: 0, col: 0 };
      current = { key, path, phrase, player, perBar: view.composition.beats_per_bar, bounds: bounds(phrase),
        notes: saved ? copy(saved) : [], mine: saved !== undefined, ready: saved !== undefined, loading: saved === undefined, focus, ...options };
      if (current.loading) load(current);
    }
    const s = current; Object.assign(s, options);
    s.cols = columns(s.bounds, s.snap);
    s.focus = { row: clamp(s.focus.row, 0, player.drums.length - 1), col: clamp(s.focus.col, 0, s.cols.length - 1) };
    const here = s.ready ? hitsAt(s.notes, s.cols, s.focus.row, s.focus.col) : [];
    const shown = here.length ? levelOf(s.notes[here[0]][3]) : level;
    const levels = el("span", { class: "sbc-button-group", role: "group", "aria-label": "Velocity" },
      LEVELS.map((lv, k) => button(lv.label, () => { level = k; if (here.length) save(setVelocity(s.notes, here, lv.velocity)); else s.paint(); },
        { class: `sbc-button${shown === k ? " is-on" : ""}`, "aria-pressed": shown === k ? "true" : "false" })));
    const pasteable = clipboard?.player === name;
    return el("div", { class: "sbc-part-editor sbc-drum-editor" },
      el("div", { class: "notes-foot", role: "group", "aria-label": "Edit the part" },
        button("Copy", () => { clipboard = { player: name, notes: copy(s.notes) }; s.paint(); }, { disabled: !s.ready }),
        button("Paste", () => save(fit(clipboard.notes, player.drums.length, s.bounds)), { disabled: !pasteable }),
        button(s.ready ? "Clear" : "Start empty", () => save([])),
        button("Reset part", () => { bridge().releaseEdit(s.path); current = null; s.paint(); }, { disabled: !s.mine }),
        s.ready ? levels : null),
      el("p", { class: "notes-foot", role: "status" }, s.error || (s.loading ? "Loading the part…" : s.mine ? "Your part" : "The program's part"),
        s.error ? button("Retry", () => { s.error = null; s.loading = true; load(s); s.paint(); }) : null),
      s.ready ? grid(s) : null,
      s.ready ? el("div", { class: "notes-foot" }, button("Hear phrase", () => s.hear(s.notes)),
        el("span", { title: "Arrow keys move; Space strikes or clears; ⇧ ↑ ↓ the level; ⇧ ← → how long it is held; Delete clears." },
          "Click or drag to strike. ⇧-click louder, ⌥-click softer.")) : null);
  }
  window.SongbirdDrums = { render, reset: () => { current = null; }, play,
    core: { PPB, LEVELS, levelOf, bounds, stepOf, columns, cellOf, hitsAt, setCell, setVelocity, setLength, normalize, fit, voice } };
})();
