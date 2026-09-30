// The score's pure parts (docs/STUDIO-REDESIGN.md): the Arrange grid made from the studio's answers, what a
// selection is, the scope of a chord or tune edit, a lock, the order a section may move to, the keyboard. No DOM,
// no requests: score.js draws what these say, and tests/studio_model.test.cjs checks them.
"use strict";

(() => {
  const LEVELS = ["out", "soft", "plays", "hard"];
  const KINDS = ["riser", "sweep", "roll", "stop"];  // a seam's transitions over the bars before (a stop in beats)
  const KIND_WORDS = { riser: "a riser", sweep: "a sweep", roll: "a snare roll", stop: "a stop", impact: "an impact", down: "a downlifter" };
  const words = (line) => String(line || "").replace(/\*/g, "");

  // ------------------------------------------------------------------ the grid
  // From /api/arrangement (sections, players, cells), the song's view (its words, its composition) and
  // /api/sound's boundaries: the regions on a ruler of bars, and one track per player, the singer first.
  function grid(arrangement, view, sound) {
    const c = view?.composition || {};
    const perBar = c.beats_per_bar || 4;
    const first = arrangement?.sections?.[0]?.start_beat || 0;
    const byId = new Map((c.sections || []).map((s) => [s.id, s]));
    const wordsAt = new Map((view?.words || []).map((w) => [w.index, w]));
    const seams = new Map((sound?.boundaries || []).map((b) => [b.id, b]));
    const order = view?.edits?.["form.order"];
    const sections = (arrangement?.sections || []).map((s) => {
      const own = byId.get(s.id), w = wordsAt.get(s.index), seam = seams.get(s.id);
      const chords = (own?.phrases || []).flatMap((p) => (p.harmony || []).map((h) => h.name));
      return {
        id: s.id, index: s.index, name: s.name, label: s.label, role: s.role, bars: s.bars,
        startBar: Math.round((s.start_beat - first) / perBar) + 1, startBeat: s.start_beat, beats: s.duration_beats,
        startSeconds: s.start_seconds, endSeconds: s.end_seconds,
        sung: s.sung, canPlay: s.can_play, choir: !!s.choir, build: s.build, barOptions: s.bar_options || [s.bars],
        first: s.sung ? words(w?.lines?.[0]) : "", wordsMine: !!w?.mine, chords, chordsMine: (own?.phrases || []).some((p) => p.chords_edited),
        moved: Array.isArray(order), by: s.by || {}, program: s.program || {}, paths: s.paths || {}, options: s.options || [],
        problems: s.problems || [], lines: s.lines || [],
        seam: seam ? { path: seam.path, value: seam.value, yours: !!seam.yours, program: seam.program, before: seam.before, from: seam.from } : null,
      };
    });
    const tracks = [
      { id: "singer", kind: "singer", label: "The singer" },
      { id: "choir", kind: "choir", label: "Voices before" },
      { id: "chords", kind: "chords", label: "Chords" },
      ...(arrangement?.players || []).map((p) => ({ id: p.name, kind: "player", label: p.label, family: p.family,
        plays: p.plays, patterns: p.patterns || [], fills: !!p.fills })),
    ];
    const cells = new Map((arrangement?.cells || []).map((cell) => [`${cell.player}|${cell.section}`, cell]));
    const bars = sections.reduce((n, s) => n + s.bars, 0);
    return { sections, tracks, cells, bars, perBar, first };
  }

  // how a cell reads: its level, whose it is, and in words (a screen reader reads the grid as a table)
  function look(cell) {
    if (!cell) return { level: "out", whose: "program", chance: false, locked: false };
    const level = cell.value?.level || "out";
    const locked = !!cell.locked;
    const whose = locked ? "locked" : cell.by === "you" ? "you" : cell.by === "before" ? "before" : "program";
    return { level, whose, chance: !!cell.chance && whose === "program", locked };
  }
  function whoseWords(l) {
    return l.locked ? "locked by you" : l.whose === "you" ? "yours" : l.whose === "before" ? "kept from the version before"
      : l.chance ? "drawn by chance" : "the program's choice";
  }
  function cellLabel(track, section, cell) {
    const l = look(cell);
    const pattern = (cell?.value?.pattern_label && l.level !== "out" ? `, ${cell.value.pattern_label}` : "")
      + (cell?.value?.from && l.level !== "out" ? `, from line ${cell.value.from + 1}` : "");
    return `${track.label} in ${section.label}: ${l.level}${pattern}; ${whoseWords(l)}`;
  }

  // ------------------------------------------------------------------ edits the grid makes (each one undoable step)
  // A lock is the same edit as a choice, with the program's own value (docs/ARRANGE.md): what chance drew stays.
  function lockPatch(cell) {
    const out = {}, v = cell?.value || {}, paths = cell?.paths || {};
    if (!paths.level) return out;
    out[paths.level] = v.level;
    if (v.pattern && paths.pattern) out[paths.pattern] = v.pattern;
    if (v.from && paths.from) out[paths.from] = v.from;  // an entrance at a later line is what chance drew
    return out;
  }
  function releasePatch(cell) {
    return Object.fromEntries(Object.values(cell?.paths || {}).map((path) => [path, null]));
  }
  function levelPatch(cells, level) {  // everyone in a section, or one player everywhere
    if (!LEVELS.includes(level)) throw new Error(`a level is ${LEVELS.join(", ")}`);
    return Object.fromEntries(cells.filter((cell) => cell?.paths?.level && cell.plays !== false).map((cell) => [cell.paths.level, level]));
  }
  function optionLock(option) { return { [option.path]: option.value }; }

  // ------------------------------------------------------------------ moving a section
  // The order a section moved from one place to another gives, or why not: repeated verses and refrains keep
  // their story order (the server checks the rest).
  function moveOrder(sections, from, to) {
    if (from === to || to < 0 || to >= sections.length || from < 0 || from >= sections.length) return { error: "It is already there." };
    const next = sections.slice();
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    const was = sections.filter((s) => s.name === moved.name).map((s) => s.id);
    const now = next.filter((s) => s.name === moved.name).map((s) => s.id);
    if (was.some((id, i) => id !== now[i])) return { error: "Repeated verses and refrains keep their story order. Move this section between other kinds of section." };
    return { order: next.map((s) => s.id) };
  }

  // ------------------------------------------------------------------ a seam: what happens into a section
  function seamWords(value) {
    if (!value) return "nothing: the band goes straight on";
    const parts = [];
    for (const k of KINDS) if (value[k]) parts.push(`${KIND_WORDS[k]} over ${value[k]} ${k === "stop" ? "beat" : "bar"}${value[k] === 1 ? "" : "s"}`);
    if (value.impact) parts.push("an impact on the downbeat");
    if (value.down) parts.push(`a downlifter over ${value.down} bar${value.down === 1 ? "" : "s"}`);
    return parts.join(", ") || "nothing: the band goes straight on";
  }
  function seamToggle(value, kind, bars = 1) {  // one kind on or off, the rest kept
    const next = { ...(value || {}) };
    if (next[kind]) delete next[kind];
    else next[kind] = kind === "impact" ? true : bars;
    return Object.keys(next).length ? next : null;
  }
  function seamOver(value, bars) {  // how long: every kind that lasts, at once
    if (!value) return null;
    const next = { ...value };
    for (const k of [...KINDS, "down"]) if (next[k]) next[k] = bars;
    return next;
  }

  // ------------------------------------------------------------------ the scope of a chord or tune edit
  // Everywhere this line is sung (the default: a line is the unit the song is made of), here only, and at the
  // last of several times, the last one however many there are (docs/STUDIO.md, "Looser harmony and melody").
  function scopeOptions(phrase, section) {
    if (!phrase?.place) return [];
    const n = phrase.appearances || 1;
    const name = String(section?.name || "section").replace("bridge2", "second bridge");
    const out = [{ id: "line", label: n > 1 ? `everywhere it's sung (${n})` : "everywhere it's sung" },
      { id: "place", label: `here only (${section?.label || name})` }];
    if (phrase.place_last) out.push({ id: "last", label: `the last ${name}, however many` });
    return out;
  }
  function scopeStart(phrase, kind) {  // where a place has its own, the switch starts there, so a change is heard there
    const from = phrase?.[`${kind}_scope`]?.from;
    return from === "place" || from === "last" ? from : "line";
  }

  // ------------------------------------------------------------------ what is selected, and what plays
  const SELECTIONS = ["song", "section", "player", "cell", "seam", "chord", "note", "line", "singer", "choir", "room", "style", "band", "shape"];
  function selectionKey(sel) {
    if (!sel) return "song";
    if (!SELECTIONS.includes(sel.kind)) throw new Error(`nothing to select called ${sel.kind}`);
    return [sel.kind, sel.id, sel.player, sel.line].filter((x) => x !== undefined && x !== null).join(":");
  }
  // decision 2: the sketch for a section, a phrase, a note, a chord; the singing for the whole song
  function defaultHow(sel) { return !sel || ["song", "singer", "choir", "room", "style", "band", "shape"].includes(sel.kind) ? "sung" : "sketch"; }
  // what ▶ plays: a section's index, or the whole song (null); with the notes open, the phrase for the sketch
  function playTarget(sel, sections) {
    const id = sel?.section || (sel && ["section", "seam", "line"].includes(sel.kind) ? sel.id : null);
    const s = id ? sections.find((x) => x.id === id) : null;
    return { section: s ? s.index : null, phrase: sel && (sel.kind === "note" || sel.kind === "chord") };
  }
  function neighbour(list, id, step) {
    const i = list.findIndex((x) => x.id === id);
    return i < 0 ? list[0] : list[Math.max(0, Math.min(list.length - 1, i + step))];
  }
  // where the playhead is, in words: a section, a bar, and the time
  function position(beat, sections, perBar) {
    const s = sections.find((x) => beat >= x.startBeat - 1e-9 && beat < x.startBeat + x.beats) || sections.at(-1) || null;
    if (!s) return { label: "", bar: 1 };
    return { id: s.id, label: s.label, bar: s.startBar + Math.floor(Math.max(0, beat - s.startBeat) / perBar) };
  }

  // ------------------------------------------------------------------ the keyboard (docs/STUDIO-REDESIGN.md's table)
  function inField(target) {
    const tag = target?.tagName;
    return !!target?.isContentEditable || tag === "TEXTAREA" || tag === "SELECT" ||
      (tag === "INPUT" && !["range", "checkbox", "button", "radio"].includes(target.type));
  }
  function keyAction(event) {
    if (inField(event.target)) return null;
    const mod = event.metaKey || event.ctrlKey, k = event.key;
    if (mod && !event.altKey && (k === "z" || k === "Z" || k === "y")) return { action: k === "y" || event.shiftKey ? "redo" : "undo" };
    if (mod && (k === "ArrowLeft" || k === "ArrowRight")) return { action: "move", step: k === "ArrowLeft" ? -1 : 1 };
    if (mod || event.altKey) return null;
    if (k === " " || k === "Spacebar") return { action: "play", how: event.shiftKey ? "sung" : "sketch" };
    const plain = { l: "loop", k: "click", m: "mute", s: "solo", r: "record", t: "time", "?": "help", Enter: "open", Escape: "escape" };
    if (plain[k.length === 1 ? k.toLowerCase() : k] && !(k.length === 1 && event.shiftKey && k !== "?")) return { action: plain[k.length === 1 ? k.toLowerCase() : k] };
    if (["1", "2", "3"].includes(k)) return { action: "view", view: ["page", "arrange", "mix"][Number(k) - 1] };
    if (k === "ArrowLeft" || k === "ArrowRight") return { action: "step", axis: "section", step: k === "ArrowLeft" ? -1 : 1 };
    if (k === "ArrowUp" || k === "ArrowDown") return { action: "step", axis: "track", step: k === "ArrowUp" ? -1 : 1 };
    return null;
  }

  // ------------------------------------------------------------------ said after an edit (the live region)
  function saidCell(track, section, level) {
    return level === "out" ? `${section.label}: the ${track.label} sits out` : `${section.label}: the ${track.label} now ${level === "plays" ? "plays" : `plays ${level}`}`;
  }

  const api = { LEVELS, KIND_WORDS, grid, look, whoseWords, cellLabel, lockPatch, releasePatch, levelPatch, optionLock,
    moveOrder, seamWords, seamToggle, seamOver, scopeOptions, scopeStart, selectionKey, defaultHow, playTarget,
    neighbour, position, inField, keyAction, saidCell };
  if (typeof window !== "undefined") window.SongbirdModel = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})();
