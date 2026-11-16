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
  // A section's columns, its phrases end to end: each phrase's steps from its pickup to where the next phrase's
  // pickup begins (the last to its end), so no time has two columns. lines: each phrase's { off: its bar line in
  // beats from the section's, bounds }. Returns each phrase's own column onsets (96ths from its bar line) and the
  // section's columns in order, each { pi: its phrase, k: its place among the phrase's, t: its onset, at: its beat
  // in the section }.
  function sectionColumns(lines, snap) {
    const local = lines.map((x, i) => {
      const next = lines[i + 1], cut = next ? Math.round((next.off - x.off) * PPB) + next.bounds.start : x.bounds.end;
      return columns({ start: x.bounds.start, end: Math.max(x.bounds.start + 1, Math.min(x.bounds.end, cut)) }, snap);
    });
    const cols = local.flatMap((ts, pi) => ts.map((t, k) => ({ pi, k, t, at: lines[pi].off + t / PPB })));
    return { local, cols };
  }

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
  // the program's strokes for the section's phrases a person hasn't written, as the part edits they would be
  // (/api/players' strokes, as pieces, made an edit's numbers by notes-in): one request for all of them
  async function load(s) {
    try {
      const missing = s.lines.filter((x) => !x.ready);
      const edits = bridge().getEdits?.() || {}, data = await ask("/api/players", { edits });
      if (current !== s || !s.loading) return;
      // the strokes in the windows of those phrases (each from just before its pickup to its end), never a written one's
      const inside = (t) => missing.some(({ p }) => t >= p.start_beat - (p.pickup_beats || 0) - 0.125 && t < p.start_beat + p.duration_beats);
      const notes = (data.players.find((x) => x.part === s.player.name)?.strokes || []).filter((n) => inside(n[0]));
      const preview = await ask("/api/notes-in", { edits, take: { player: s.player.name, notes, lines: missing.map((x) => x.p.part_key) } });
      if (current !== s || !s.loading) return;
      if (preview.refused?.length) throw new Error(`${preview.refused[0].why}.`);
      for (const x of missing) { x.notes = copy(preview.changes.find((c) => c.path === x.path)?.value || []); x.ready = true; }
    } catch (error) { if (current === s && s.loading) s.error = error.message; }
    if (current === s) { s.loading = false; s.paint(); }
  }
  // phrases' strokes saved, each as its own part edit, together as one undo step; `label`, what an undo says.
  // changes: Map(phrase → its strokes). Nothing changed writes nothing.
  function save(changes, label = "Change the drum part") {
    const s = current;
    if (!s) return;
    try {
      const patch = {}, clean = new Map();
      for (const [pi, notes] of changes) {
        const x = s.lines[pi];
        if (!x?.editable) continue;
        const kept = normalize(notes, s.player.drums.length, x.bounds);
        if (x.ready && same(kept, x.notes)) continue;
        clean.set(pi, kept); patch[x.path] = kept;
      }
      s.error = null;
      if (clean.size) {
        // a stroke struck (or its level changed) is heard at once: the first few, together
        const struck = [...clean].flatMap(([pi, kept]) => kept.filter((n) => !(s.lines[pi].notes || []).some((o) => same([o], [n]))));
        if (struck.length && struck.length <= 4) s.sound?.(struck.map((n) => [0, n[1], n[2], n[3]]));
        for (const [pi, kept] of clean) Object.assign(s.lines[pi], { notes: kept, ready: true, mine: true });
        if (clean.size === 1) bridge().setEdit(Object.keys(patch)[0], Object.values(patch)[0], label);
        else bridge().setEdits(patch, label);
      }
      s.paint();
    } catch (error) { s.error = error.message; s.paint(); }
  }
  const one = (pi, notes) => new Map([[pi, notes]]);
  const cellId = (row, col) => `drum:${row}:${col}`;
  const lineOf = (s, col) => s.lines[s.cols[col]?.pi];
  // the cell given the keys: focused before the page is drawn again, so the page keeps it (data-part-note)
  function take(row, col) {
    const s = current;
    s.focus = { row: clamp(row, 0, s.player.drums.length - 1), col: clamp(col, 0, s.cols.length - 1) };
    const pi = s.cols[s.focus.col]?.pi;
    if (pi !== undefined && pi !== s.at) { s.at = pi; s.choose?.(s.lines[pi].p); }  // the phrase the strip, ▶ and the buttons mean
    document.querySelector(`[data-part-note="${cellId(s.focus.row, s.focus.col)}"]`)?.focus({ preventScroll: false });
  }
  function focusCell(row, col) { take(row, col); current.paint(); }
  // a cell's strokes in its own phrase's terms: the phrase, its columns, the column's place among them
  function cellAt(s, row, col) {
    const c = s.cols[col], x = s.lines[c.pi];
    return { pi: c.pi, x, cols: s.local[c.pi], k: c.k, here: hitsAt(x.notes, s.local[c.pi], row, c.k) };
  }
  function keydown(e) {
    const s = current, [row, col] = e.currentTarget.dataset.drumCell.split(":").map(Number);
    s.focus = { row, col };
    const { pi, x, cols, k, here } = cellAt(s, row, col), step = stepOf(s.snap);
    const moves = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    const writes = x.editable && x.ready;
    if (e.shiftKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {  // the stroke's level
      if (!here.length || !writes) return;
      const next = clamp(levelOf(x.notes[here[0]][3]) + (e.key === "ArrowUp" ? 1 : -1), 0, 2);
      level = next; save(one(pi, setVelocity(x.notes, here, LEVELS[next].velocity)), "Change a stroke's level");
    } else if (e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {  // how long it is held
      if (!here.length || !writes) return;
      save(one(pi, setLength(x.notes, here, x.notes[here[0]][1] + (e.key === "ArrowRight" ? step : -step))), "Change a stroke's length");
    } else if (moves[e.key]) focusCell(row + moves[e.key][0], col + moves[e.key][1]);
    else if (e.key === "Home") focusCell(row, 0);
    else if (e.key === "End") focusCell(row, s.cols.length - 1);
    else if (e.key === " " || e.key === "Enter") { if (writes) save(one(pi, setCell(x.notes, cols, row, k, !here.length, step, LEVELS[level].velocity)), here.length ? "Clear a stroke" : "Strike a drum"); }
    else if (e.key === "Delete" || e.key === "Backspace") { if (writes) save(one(pi, setCell(x.notes, cols, row, k, false, step, 0)), "Clear a stroke"); }
    else return;
    e.preventDefault(); e.stopPropagation();
  }
  // a press on a cell strikes or clears it, and a drag paints the same across the cells it passes (into the next
  // phrase too: one undo step); ⇧ on a stroke raises its level, ⌥ lowers it
  function press(e, row, col) {
    const s = current;
    if (e.button !== 0 || !s) return;
    const start = cellAt(s, row, col);
    if (!start.x.editable || !start.x.ready) return;
    e.preventDefault();
    take(row, col);
    const step = stepOf(s.snap);
    if (start.here.length && (e.shiftKey || e.altKey)) {
      const next = clamp(levelOf(start.x.notes[start.here[0]][3]) + (e.shiftKey ? 1 : -1), 0, 2);
      level = next; save(one(start.pi, setVelocity(start.x.notes, start.here, LEVELS[next].velocity)), "Change a stroke's level");
      return;
    }
    const on = !start.here.length, label = on ? "Strike a drum" : "Clear a stroke", painted = new Map();
    const paint = (r, c) => {
      const at = cellAt(s, r, c);
      if (!at.x.editable || !at.x.ready) return false;
      painted.set(at.pi, setCell(painted.get(at.pi) ?? at.x.notes, at.cols, r, at.k, on, step, LEVELS[level].velocity));
      return true;
    };
    paint(row, col);
    e.currentTarget.classList.toggle("is-hit", on);
    if (e.pointerType === "touch") { save(painted, label); return; }  // a finger strikes one cell; a drag scrolls
    const grid = e.currentTarget.closest(".sbc-drum-grid");
    try { grid?.setPointerCapture?.(e.pointerId); } catch (_) { /* a pointer that can't be captured paints only where it goes */ }
    const move = (event) => {
      const cell = document.elementFromPoint?.(event.clientX, event.clientY)?.closest?.("[data-drum-cell]");
      if (!cell || !grid?.contains(cell)) return;
      const [r, c] = cell.dataset.drumCell.split(":").map(Number);
      if (paint(r, c)) { cell.classList.toggle("is-hit", on); take(r, c); }
    };
    const finish = (event) => {
      grid?.removeEventListener("pointermove", move); grid?.removeEventListener("pointerup", finish); grid?.removeEventListener("pointercancel", cancel);
      try { if (grid?.hasPointerCapture?.(event.pointerId)) grid.releasePointerCapture(event.pointerId); } catch (_) { /* released */ }
      if (current === s) save(painted, label);
    };
    const cancel = (event) => { painted.clear(); finish(event); };
    if (!grid) { save(painted, label); return; }
    grid.addEventListener("pointermove", move); grid.addEventListener("pointerup", finish); grid.addEventListener("pointercancel", cancel);
  }
  function grid(s) {
    const step = stepOf(s.snap), cols = s.cols, pieces = s.player.drums, last = s.lines.at(-1);
    const span = (last.off + last.bounds.end / PPB) - Math.min(0, ...s.lines.map((x) => x.off + x.bounds.start / PPB));
    const unit = window.SongbirdModel.rollUnit(s.zoom, (document.getElementById("studio-composer")?.clientWidth || 700) - 100, span, { base: 80 });
    const end = last.off + last.bounds.end / PPB, firstCol = s.local.map((_, pi) => s.cols.findIndex((c) => c.pi === pi));
    const width = (c) => ((cols[c + 1]?.at ?? end) - cols[c].at) * unit;
    const template = `var(--sbc-drum-label) ${cols.map((_, c) => `${Math.max(4, width(c))}px`).join(" ")}`;
    if (s.reveal) {  // a phrase chosen on the strip: the grid scrolled to its start
      s.reveal = false;
      s.scrollTo?.(cols.slice(0, Math.max(0, cols.findIndex((c) => c.pi === s.at))).reduce((sum, _, c) => sum + Math.max(4, width(c)), 0));
    }
    const bar = s.perBar * PPB, hits = new Map();
    s.lines.forEach((x, pi) => x.notes.forEach((n) => {
      const key = `${n[2]}:${firstCol[pi] + cellOf(n[0], s.local[pi])}`;
      if (!hits.has(key)) hits.set(key, n);
    }));
    const beat96 = (c) => Math.round(cols[c].at * PPB);  // the column's onset in 96ths of the section
    const where = (c) => `phrase ${cols[c].pi + 1}, beat ${(cols[c].t / PPB + 1).toFixed(2).replace(/\.00$/, "")}`;
    const style = { gridTemplateColumns: template };
    const ruler = el("div", { class: "sbc-drum-row sbc-drum-ruler", "aria-hidden": "true", style }, el("span", {}),
      cols.map((_, c) => {
        const t = beat96(c), first = c > 0 && cols[c - 1].pi !== cols[c].pi;
        return el("span", { class: `sbc-drum-tick${t % bar === 0 && t >= 0 ? " is-bar" : ""}${first ? " is-phrase" : ""}` },
          t % bar === 0 && t >= 0 ? t / bar + 1 : t % PPB === 0 ? "·" : "");
      }));
    const rows = pieces.map((piece, row) => el("div", { class: "sbc-drum-row", role: "row", style },
      el("span", { role: "rowheader", class: "sbc-drum-head" }, button(piece.label, () => (s.sound || s.hear)([[0, step, row, LEVELS[level].velocity]]),
        { class: "sbc-drum-piece", "aria-label": `Hear ${piece.label}` })),
      cols.map((c, col) => {
        const x = s.lines[c.pi], n = hits.get(`${row}:${col}`), focused = s.focus.row === row && s.focus.col === col;
        const lv = n ? LEVELS[levelOf(n[3])] : null, t = beat96(col), first = col > 0 && cols[col - 1].pi !== c.pi;
        return el("span", { role: "gridcell", tabindex: focused ? "0" : "-1", "data-drum-cell": `${row}:${col}`, "data-part-note": cellId(row, col),
          class: `sbc-drum-cell${n ? ` is-hit is-${lv.name}` : ""}${x.mine ? " is-edited" : ""}${x.editable ? "" : " is-locked"}${first ? " is-phrase" : ""}${t % bar === 0 ? " is-bar" : t % PPB === 0 ? " is-beat" : ""}${c.pi === s.at ? " is-here" : ""}`,
          "aria-label": `${piece.label}, ${where(col)}${n ? `, ${lv.label.toLowerCase()}` : ""}${x.editable ? "" : ", can't be written"}`,
          "aria-disabled": x.editable ? null : "true", title: x.editable ? null : "Added by the arrangement: its part can't be written.",
          onpointerdown: (e) => press(e, row, col), onkeydown: keydown, onfocus: () => { s.focus = { row, col }; } },
        n && n[1] > step ? el("i", { class: "sbc-drum-held", style: { width: `${Math.min(n[1] / PPB * unit, 4000) - 4}px` } }) : null);
      })));
    return el("div", { class: "sbc-roll-scroll", "aria-label": `${s.player.label} steps` },
      el("div", { class: "sbc-drum-grid", role: "grid", "aria-label": `${s.player.label}: ${pieces.length} pieces` }, ruler, rows));
  }
  // A percussion player's part over a whole section: its phrases end to end (each still its own part edit), a
  // phrase the arrangement added shown but not writable. options: snap, zoom, paint, hear, phrase (the strip's),
  // choose (a phrase chosen here).
  function render(view, section, name, options) {
    const player = view.composition.players.find((p) => p.name === name);
    if (!player?.drums?.length) return el("p", { class: "notes-foot" }, "This player's part can't be written yet.");
    const phrases = section.phrases || [];
    if (!phrases.some((p) => p.part_editable !== false)) return el("p", { class: "notes-foot" }, "The arrangement added this section's phrases. Their part can't be written.");
    const key = `${view.listen?.whole || JSON.stringify(bridge().getEdits?.() || {})}|${section.id}|${name}`;
    if (!current || current.key !== key) {
      const was = current?.sid === section.id && current?.player.name === name ? current : null;
      const lines = phrases.map((p) => {
        const editable = p.part_editable !== false, saved = editable ? p.part_notes?.[name] : undefined;
        return { p, editable, path: editable ? `part.${name}.${p.part_key}` : null, off: (p.start_beat ?? section.start_beat) - section.start_beat,
          bounds: bounds(p), notes: saved ? copy(saved) : [], mine: saved !== undefined, ready: !editable || saved !== undefined };
      });
      current = { key, sid: section.id, player, perBar: view.composition.beats_per_bar, lines, at: was?.at ?? null,
        focus: was?.focus ?? { row: 0, col: 0 }, loading: lines.some((x) => !x.ready), ...options };
      if (current.loading) load(current);
    }
    const s = current; Object.assign(s, options);
    if (!s.fetched) { s.fetched = true; s.ready?.(); }  // its pieces, asked ahead
    ({ local: s.local, cols: s.cols } = sectionColumns(s.lines, s.snap));
    // the strip's phrase: the focus goes to its first column, unless the focus is in it
    const strip = phrases[options.phrase] ? options.phrase : null;
    if (strip !== null && strip !== s.at) {
      s.at = strip; s.reveal = true;
      if (s.cols[s.focus.col]?.pi !== strip) s.focus = { row: s.focus.row, col: Math.max(0, s.cols.findIndex((c) => c.pi === strip)) };
    }
    s.focus = { row: clamp(s.focus.row, 0, player.drums.length - 1), col: clamp(s.focus.col, 0, s.cols.length - 1) };
    if (s.at === null) s.at = s.cols[s.focus.col]?.pi ?? 0;
    const x = s.lines[s.at], cell = cellAt(s, s.focus.row, s.focus.col), here = cell.x.ready ? cell.here : [];
    const shown = here.length ? levelOf(cell.x.notes[here[0]][3]) : level;
    const levels = el("span", { class: "sbc-button-group", role: "group", "aria-label": "Velocity" },
      LEVELS.map((lv, k) => button(lv.label, () => {
        level = k;
        if (here.length && cell.x.editable) save(one(cell.pi, setVelocity(cell.x.notes, here, lv.velocity)), "Change a stroke's level"); else s.paint();
      }, { class: `sbc-button${shown === k ? " is-on" : ""}`, "aria-pressed": shown === k ? "true" : "false" })));
    const pasteable = clipboard?.player === name && x.editable;
    const ready = s.lines.every((y) => y.ready);
    return el("div", { class: "sbc-part-editor sbc-drum-editor" },
      el("div", { class: "notes-foot", role: "group", "aria-label": `Edit phrase ${s.at + 1}'s part` },
        button("Copy", () => { clipboard = { player: name, notes: copy(x.notes) }; s.paint(); bridge().toast?.(`Phrase ${s.at + 1}'s strokes copied.`); },
          { disabled: !x.ready || !x.editable, title: "Copy this phrase's strokes" }),
        button("Paste", () => save(one(s.at, fit(clipboard.notes, player.drums.length, x.bounds)), "Paste strokes"), { disabled: !pasteable || !x.ready, title: "Paste into this phrase" }),
        ready ? button("Clear", () => save(one(s.at, []), "Clear the phrase's strokes"), { disabled: !x.editable, title: "Clear this phrase's strokes" })
          : button("Start empty", () => save(new Map(s.lines.flatMap((y, pi) => (y.ready ? [] : [[pi, []]]))), "Start empty"), { title: "A rest in the phrases not yet loaded" }),
        button("Reset part", () => { bridge().releaseEdit(x.path, "Reset the part"); current = null; s.paint(); }, { disabled: !x.mine }),
        ready ? levels : null),
      el("p", { class: "notes-foot", role: "status" }, s.error || (s.loading ? "Loading the part…" : !x.editable ? `Phrase ${s.at + 1}: added by the arrangement, can't be written`
        : `Phrase ${s.at + 1}: ${x.mine ? "your part" : "the program's part"}`),
      s.error ? button("Retry", () => { s.error = null; s.loading = true; load(s); s.paint(); }) : null),
      ready ? grid(s) : null,
      ready ? el("div", { class: "notes-foot" }, button("Hear phrase", () => s.hear(x.notes)),
        el("span", { title: "Arrow keys move; Space strikes or clears; ⇧ ↑ ↓ the level; ⇧ ← → how long it is held; Delete clears." },
          "Click or drag to strike. ⇧-click louder, ⌥-click softer.")) : null);
  }
  window.SongbirdDrums = { render, reset: () => { current = null; }, play,
    core: { PPB, LEVELS, levelOf, bounds, stepOf, columns, cellOf, hitsAt, setCell, setVelocity, setLength, normalize, fit, sectionColumns, voice } };
})();
