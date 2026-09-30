// Notes in (docs/STUDIO.md, "Notes in"): a part played in on a MIDI keyboard along with the sketch, and a MIDI
// file brought back from a sequencer. Only notes are kept, as numbers (when a key went down and up, which, how
// hard), never a sound. The server (songbird/studio.py, /api/notes-in) turns them into edits line by line and
// says what it can't take and why; this page shows that and applies it as one undoable step.
// Plain JavaScript, no libraries. The capture, timing and quantizing are pure functions (tested with synthetic
// events in tests/studio_perform.test.cjs).
"use strict";

(() => {
  const doc = typeof document !== "undefined" ? document : null;
  const TOKEN = doc?.querySelector('meta[name="studio-token"]')?.content || "";
  const bridge = () => (typeof window !== "undefined" && window.StudioBridge) || {};
  const $ = (id) => doc?.getElementById(id);

  // ---------------------------------------------------------------- pure: time, capture, quantize

  // A MIDI event's moment (its timeStamp, performance.now()'s clock, in ms) as a beat of the score: through the
  // audio clock (anchored now: perfNow is performance.now() and ctxNow the AudioContext's time, read together),
  // less the audio's output latency, so a note played to what was heard lands where it was heard.
  function beatOf(eventMs, clock) {
    const ctxTime = clock.ctxNow - (clock.perfNow - eventMs) / 1000;
    return clock.origin + (ctxTime - (clock.latency || 0) - clock.started) / clock.secondsPerBeat;
  }

  // Notes from note-on and note-off events: a key struck again before it was let go ends the earliest first,
  // a note-on at velocity 0 is a note-off, and a note still held when the take ends ends there.
  class Capture {
    constructor() { this.held = new Map(); this.notes = []; }
    on(key, velocity, beat) {
      if (!velocity) return this.off(key, beat);
      if (!this.held.has(key)) this.held.set(key, []);
      this.held.get(key).push([beat, velocity]);
      return null;
    }
    off(key, beat) {
      const waiting = this.held.get(key);
      if (!waiting || !waiting.length) return null;
      const [start, velocity] = waiting.shift();
      const note = [start, Math.max(beat - start, 1 / 96), key, velocity];
      this.notes.push(note);
      return note;
    }
    message(data, beat) {  // a raw MIDI message: [status, key, velocity]
      const kind = data[0] & 0xf0;
      if (kind === 0x90) return this.on(data[1], data[2], beat);
      if (kind === 0x80) return this.off(data[1], beat);
      return null;
    }
    finish(beat) {
      for (const key of [...this.held.keys()]) while (this.held.get(key).length) this.off(key, beat);
      return this.notes.slice().sort((a, b) => a[0] - b[0] || a[2] - b[2]);
    }
  }

  // Timing tidied to a grid (in beats: 1/2, 1/4, 1/3; 0 keeps it as played), counted from a bar line (anchor):
  // each onset to the nearest step, each length to a whole number of steps, at least one.
  function quantize(notes, grid, anchor = 0) {
    if (!grid) return notes.map((n) => n.slice());
    const snap = (x) => Math.round(x / grid) * grid;
    return notes.map(([beat, length, key, velocity]) => [anchor + snap(beat - anchor), Math.max(grid, snap(length)), key, velocity]);
  }

  // The lines a take covers: the whole song, a section's, or one line of it (keys as the server has them).
  function linesFor(composition, where, line) {
    const sections = composition?.sections || [];
    const chosen = where === "song" ? sections : [sections[Number(where)]].filter(Boolean);
    return chosen.flatMap((s) => (s.phrases || []).filter((p, j) => where === "song" || line === "all" || Number(line) === j)
      .map((p) => ({ key: p.part_key, start: p.start_beat, pickup: p.pickup_beats || 0, end: p.start_beat + p.duration_beats, section: s })));
  }

  // What the take plays along with: the tune (unless the tune is what's played) and the chords, from the first
  // bar line after a bar's count-in to the end of the last line; and the clicks.
  function backingFor(composition, lines, player) {
    const first = lines[0], last = lines[lines.length - 1], bar = composition.beats_per_bar || 4;
    const origin = first.start - bar, end = last.end;
    const tune = [], chords = [];
    for (const s of composition.sections || []) for (const p of s.phrases || []) {
      if (p.start_beat + p.duration_beats <= origin || p.start_beat - (p.pickup_beats || 0) >= end) continue;
      if (player !== "voice") for (const n of p.notes || []) tune.push({ beat: p.start_beat + n.onset, length: n.duration, pitch: n.pitch });
      for (const h of p.harmony || []) chords.push({ beat: p.start_beat + h.start, length: h.beats, pcs: h.pcs || [] });
    }
    const clicks = [];
    for (let k = 0; origin + k < end - 1e-9; k++) clicks.push({ beat: origin + k, down: k % bar === 0 });  // on the bars' beats
    return { origin, end, tune: tune.filter((n) => n.beat >= origin && n.beat < end), chords: chords.filter((c) => c.beat >= first.start - 1e-9 && c.beat < end), clicks };
  }

  // The preview's changes as one patch of edits, applied as one undoable step.
  function patchOf(preview) {
    return Object.fromEntries((preview?.changes || []).map((c) => [c.path, c.value]));
  }

  // ---------------------------------------------------------------- the page

  const state = {
    view: null, access: null, inputs: [], take: null, capture: null, context: null, nodes: new Set(), timer: null,
    preview: null, previewFrom: null, file: null, assign: {}, busy: false,
  };

  function el(tag, attrs, ...children) {
    const node = doc.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c instanceof Object && c.nodeType ? c : doc.createTextNode(String(c)));
    return node;
  }

  async function ask(body) {
    const r = await fetch("/api/notes-in", { method: "POST", headers: { "Content-Type": "application/json", "X-Studio": TOKEN }, body: JSON.stringify(body) });
    let data;
    try { data = await r.json(); } catch (_) { data = { error: r.statusText }; }
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  }

  const composition = () => state.view?.composition;
  const players = () => composition()?.players || [];
  const choice = (id, fallback) => $(id)?.value ?? fallback;

  function say(id, text) { const n = $(id); if (n) n.textContent = text; }

  // ---- listening to a keyboard (Web MIDI; the browser asks first)

  async function connect() {
    if (!navigator.requestMIDIAccess) {
      say("performNote", "This browser can't listen to a MIDI keyboard. Chrome, Edge and Firefox can.");
      return false;
    }
    try {
      state.access = state.access || await navigator.requestMIDIAccess();
    } catch (e) {
      say("performNote", "The browser wasn't allowed to listen to a MIDI keyboard.");
      return false;
    }
    state.inputs = [...state.access.inputs.values()];
    state.access.onstatechange = () => { state.inputs = [...state.access.inputs.values()]; paint(); };
    for (const input of state.inputs) input.onmidimessage = heard;
    say("performNote", state.inputs.length ? `Listening to ${state.inputs.map((i) => i.name).join(", ")}.` : "No MIDI keyboard is connected.");
    return state.inputs.length > 0;
  }

  function heard(event) {
    if (!state.capture || !state.take) return;
    const ctx = state.context;
    const clock = { ...state.take.clock, ctxNow: ctx.currentTime, perfNow: performance.now() };
    const note = state.capture.message(event.data, beatOf(event.timeStamp, clock));
    if (note) say("performNote", `${state.capture.notes.length} note${state.capture.notes.length === 1 ? "" : "s"} so far…`);
  }

  // ---- the backing (oscillators, as the sketch's)

  function audio() {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return null;
    if (!state.context || state.context.state === "closed") state.context = new Context();
    if (state.context.state === "suspended") state.context.resume().catch(() => {});
    return state.context;
  }
  function tone(ctx, pitch, start, length, peak, type = "triangle", hz = null) {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.value = hz || 440 * 2 ** ((pitch - 69) / 12);
    g.gain.setValueAtTime(0, start);
    g.gain.linearRampToValueAtTime(peak, start + 0.008);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0001, peak * 0.3), start + Math.max(0.03, Math.min(0.2, length * 0.5)));
    g.gain.linearRampToValueAtTime(0.0001, start + Math.max(0.05, length));
    o.connect(g); g.connect(ctx.destination);
    state.nodes.add(o);
    o.onended = () => { state.nodes.delete(o); o.disconnect(); g.disconnect(); };
    o.start(start); o.stop(start + Math.max(0.05, length) + 0.03);
  }
  const within = (pc, low) => low + (((pc - low) % 12) + 12) % 12;
  function playBacking(ctx, backing, started, spb, withClick, take) {
    const at = (beat) => started + (beat - backing.origin) * spb;
    for (const n of backing.tune) tone(ctx, n.pitch, at(n.beat), n.length * spb * 0.9, 0.06);
    for (const c of backing.chords) c.pcs.map((pc) => within(pc, 55)).forEach((p, i) => tone(ctx, p, at(c.beat) + i * 0.012, c.length * spb * 0.9, 0.018, "sawtooth"));
    for (const c of backing.clicks) if (withClick || c.beat < backing.origin + (composition().beats_per_bar || 4)) tone(ctx, 0, at(c.beat), 0.045, 0.04, "sine", c.down ? 1200 : 800);
    for (const [beat, length, key, velocity] of take || []) tone(ctx, key, at(beat), length * spb, 0.03 + 0.09 * velocity / 127, "square");
  }
  function silence() {
    for (const o of state.nodes) { try { o.stop(); } catch (_) { /* ended */ } }
    state.nodes.clear();
    clearTimeout(state.timer);
  }

  // ---- a take

  async function record() {
    if (state.take?.recording) return stopRecording();
    if (!state.inputs.length && !(await connect())) return;
    const lines = linesFor(composition(), choice("performWhere", "song"), choice("performLine", "all"));
    if (!lines.length) return;
    const ctx = audio();
    if (!ctx) { say("performNote", "This browser can't play the sketch."); return; }
    bridge().pauseAudio?.();
    window.SongbirdComposer?.stop?.();
    silence();
    const player = choice("performPlayer", "voice");
    const backing = backingFor(composition(), lines, player);
    const spb = 60 / composition().tempo;
    const started = ctx.currentTime + 0.15;
    const latency = (ctx.outputLatency || 0) + (ctx.baseLatency || 0);
    state.capture = new Capture();
    state.take = { player, lines, backing, recording: true, notes: null, clock: { origin: backing.origin, started, secondsPerBeat: spb, latency } };
    state.preview = null;
    playBacking(ctx, backing, started, spb, $("performClick")?.checked !== false);
    say("performNote", "A bar to count in, then play…");
    state.timer = setTimeout(stopRecording, ((backing.end - backing.origin) * spb + 0.6) * 1000);
    paint();
  }

  function stopRecording() {
    if (!state.take?.recording) return;
    const ctx = state.context, take = state.take;
    const clock = { ...take.clock, ctxNow: ctx.currentTime, perfNow: performance.now() };
    const now = Math.min(take.backing.end, beatOf(performance.now(), clock));
    silence();
    take.recording = false;
    const grid = Number(choice("performGrid", "0"));
    const bar = take.lines[0].start;
    take.notes = quantize(state.capture.finish(now), grid, bar).filter((n) => n[0] < take.backing.end);
    state.capture = null;
    say("performNote", take.notes.length ? `${take.notes.length} note${take.notes.length === 1 ? "" : "s"} played. Hear it back, or keep it.` : "Nothing was played.");
    paint();
  }

  function hearBack() {
    const take = state.take, ctx = audio();
    if (!take?.notes || !ctx) return;
    silence();
    const spb = 60 / composition().tempo;
    playBacking(ctx, { ...take.backing, clicks: [] }, ctx.currentTime + 0.1, spb, false, take.notes);
  }

  async function keep() {
    const take = state.take;
    if (!take?.notes) return;
    state.busy = true; paint();
    try {
      const preview = await ask({ edits: bridge().getEdits?.() || {}, take: { player: take.player, notes: take.notes.map((n) => n.map((x) => Math.round(x * 10000) / 10000)), lines: take.lines.map((l) => l.key) } });
      show(preview, "take");
    } catch (e) { say("performNote", `Couldn't take it: ${e.message}`); }
    state.busy = false; paint();
  }

  // ---- a MIDI file brought back

  function bytesToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let text = "";
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(text);
  }

  async function bringBack(file) {
    if (!file) return;
    if (file.size > 256 * 1024) { say("importNote", "That file is bigger than a song's MIDI file can be (256 KB)."); return; }
    state.file = bytesToBase64(await file.arrayBuffer());
    state.assign = {};
    await readFile();
  }

  async function readFile() {
    state.busy = true; say("importNote", "Reading it against this version…"); paint();
    try {
      const preview = await ask({ edits: bridge().getEdits?.() || {}, file: state.file, assign: state.assign });
      show(preview, "file");
      say("importNote", "");
    } catch (e) { state.preview = null; say("importNote", `Couldn't read it: ${e.message}`); }
    state.busy = false; paint();
  }

  // ---- the preview, and applying it

  function show(preview, from) {
    state.preview = preview;
    state.previewFrom = from;
    paint();
    $(from === "file" ? "importPreview" : "performPreview")?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  }

  function apply() {
    const preview = state.preview;
    const patch = patchOf(preview);
    if (!Object.keys(patch).length) return;
    const label = state.previewFrom === "file" ? "Bring the MIDI file back" : `Play the ${state.take?.player === "voice" ? "tune" : state.take?.player} in`;
    bridge().setEdits?.(patch, label);
    bridge().toast?.(`${Object.keys(patch).length} change${Object.keys(patch).length === 1 ? "" : "s"} yours: undo takes ${Object.keys(patch).length === 1 ? "it" : "them"} back`);
    state.preview = null;
    if (state.previewFrom === "take") state.take = null;
    paint();
  }

  function cancel() { state.preview = null; paint(); }

  function previewBox(from) {
    const p = state.preview;
    if (!p || state.previewFrom !== from) return null;
    const rows = [];
    if (p.changes.length) rows.push(el("p", {}, `${p.changes.length} change${p.changes.length === 1 ? "" : "s"}, all yours when applied:`),
      el("ul", { class: "notes-in-list yours" }, p.changes.map((c) => el("li", {}, el("b", {}, c.where), ` — ${c.what}`))));
    else rows.push(el("p", {}, from === "file" ? "Nothing in it differs from this version." : "Nothing to change."));
    if (p.refused.length) rows.push(el("p", {}, "Not taken:"), el("ul", { class: "notes-in-list" }, p.refused.map((r) => el("li", {}, el("b", {}, r.where), ` — ${r.why}`))));
    for (const s of p.said || []) rows.push(el("p", { class: "hint" }, s));
    if (p.unmatched?.length) {
      rows.push(el("p", {}, "Which part is each of these tracks?"));
      for (const t of p.unmatched) {
        const pick = el("select", { "aria-label": `The part the track ${t.name} is`, onchange: (e) => { state.assign[t.track] = e.target.value; } },
          el("option", { value: "" }, "Leave it"), (p.tracks || []).map((name) => el("option", { value: name }, name)));
        pick.value = state.assign[t.track] || "";
        rows.push(el("label", { class: "notes-in-assign" }, `${t.name} (${t.notes} notes) `, pick));
      }
      rows.push(el("div", { class: "actions" }, el("button", { class: "btn", type: "button", onclick: readFile }, "Read it again")));
    }
    rows.push(el("div", { class: "actions" },
      p.changes.length ? el("button", { class: "btn primary", type: "button", id: from === "file" ? "importApply" : "performApply", onclick: apply }, "Apply") : null,
      el("button", { class: "btn quiet", type: "button", onclick: cancel }, p.changes.length ? "Cancel" : "Close")));
    return el("div", { class: "notes-in-preview", id: from === "file" ? "importPreview" : "performPreview", role: "region", "aria-label": "What will change" }, rows);
  }

  // ---- what's been played in, and giving it back

  function performedBox() {
    const c = composition();
    const played = c?.performed || {};
    const names = Object.keys(played);
    if (!names.length) return null;
    const where = (key) => {
      for (const s of c.sections) for (const [j, p] of (s.phrases || []).entries()) if (p.part_key === key) return `${s.label}, line ${j + 1}`;
      return key;
    };
    return el("div", { class: "notes-in-yours" }, el("p", {}, "Played in by you:"),
      el("ul", { class: "notes-in-list yours" }, names.map((name) => el("li", {},
        el("b", {}, (players().find((p) => p.name === name)?.label) || name), ` — ${played[name].map(where).join(", ")} `,
        el("button", { class: "link small", type: "button", onclick: () => bridge().clearEdits?.(played[name].map((k) => `part.${name}.${k}`), `Give the ${name}'s part back`) }, "give it back")))));
  }

  function paint() {
    const box = $("performPanel");
    if (box && composition()) {
      const c = composition();
      const sections = c.sections || [];
      const where = choice("performWhere", "song"), line = choice("performLine", "all");
      const whereSelect = el("select", { id: "performWhere", "aria-label": "How much", onchange: paint },
        el("option", { value: "song" }, "The whole song"), sections.map((s, i) => el("option", { value: String(i) }, s.label)));
      whereSelect.value = where;
      const lineSelect = el("select", { id: "performLine", "aria-label": "Which line", disabled: where === "song" },
        el("option", { value: "all" }, "every line"), ((sections[Number(where)] || {}).phrases || []).map((_, j) => el("option", { value: String(j) }, `line ${j + 1}`)));
      lineSelect.value = where === "song" ? "all" : line;
      const playerSelect = el("select", { id: "performPlayer", "aria-label": "Who you play" }, players().map((p) => el("option", { value: p.name }, p.label)));
      playerSelect.value = state.take?.player || $("performPlayer")?.value || (players()[1] || players()[0] || {}).name || "voice";
      const gridSelect = el("select", { id: "performGrid", "aria-label": "Timing" }, [["0", "as played"], ["0.5", "tidied to eighths"], ["0.25", "tidied to sixteenths"], ["0.3333333333", "tidied to eighth triplets"]].map(([v, t]) => el("option", { value: v }, t)));
      gridSelect.value = $("performGrid")?.value || "0";
      const click = el("input", { type: "checkbox", id: "performClick" });
      click.checked = $("performClick") ? $("performClick").checked : true;
      const recording = !!state.take?.recording;
      box.replaceChildren(...[
        el("div", { class: "area-head" }, el("h3", {}, "Play a part in"),
          el("details", { class: "whatis" }, el("summary", { title: "What is this?" }, el("span", { class: "sr-only" }, "What is this?")),
            el("div", {}, el("p", {}, "Play a player's part (or the tune) on a MIDI keyboard, along with the sketch: a bar of clicks counts you in. Only the notes are kept: when, which and how hard, never a sound."),
              el("p", {}, "Your notes take the place of that player's own in those lines, played by its instrument, and are marked as yours. The tune keeps one note for each syllable, in the key's scale.")))),
        el("div", { class: "notes-in-controls" },
          el("label", {}, "Play ", playerSelect), el("label", {}, "over ", whereSelect, " ", lineSelect),
          el("label", {}, "timing ", gridSelect), el("label", {}, click, " click")),
        el("div", { class: "actions" },
          el("button", { class: `btn${recording ? " primary" : ""}`, type: "button", id: "performRecord", onclick: record, disabled: state.busy }, recording ? "■ Stop" : "● Record"),
          el("button", { class: "btn quiet", type: "button", id: "performHear", onclick: hearBack, disabled: !state.take?.notes?.length || recording }, "Hear it back"),
          el("button", { class: "btn", type: "button", id: "performKeep", onclick: keep, disabled: !state.take?.notes || recording || state.busy }, "Keep it")),
        el("p", { class: "hint", id: "performNote", "aria-live": "polite" }, $("performNote")?.textContent || (typeof navigator !== "undefined" && navigator.requestMIDIAccess ? "Connect a MIDI keyboard, then Record." : "This browser can't listen to a MIDI keyboard. Chrome, Edge and Firefox can.")),
        previewBox("take"), performedBox()].filter(Boolean));  // (replaceChildren would write a null as "null")
    }
    const holder = $("importBox");
    if (holder) holder.replaceChildren(previewBox("file") || "");
    const bring = $("importMidi");
    if (bring) bring.disabled = state.busy;
  }

  function render(view) {
    state.view = view;
    if (state.take?.recording) return;  // don't redraw under a take
    paint();
  }

  function wire() {
    $("importMidi")?.addEventListener("click", () => $("importFile")?.click());
    $("importFile")?.addEventListener("change", (e) => { bringBack(e.target.files[0]); e.target.value = ""; });
  }

  const api = { beatOf, Capture, quantize, linesFor, backingFor, patchOf, render, apply, show, state };
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.SongbirdPerform = api;
  if (doc) {
    if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", wire);
    else wire();
    if (typeof window !== "undefined") window.addEventListener?.("pagehide", silence);
  }
})();
