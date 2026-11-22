// The score's pure parts (docs/notes/STUDIO-REDESIGN.md): the Arrange grid made from the studio's answers, what a
// selection is, the scope of a chord or tune edit, a lock, the order a section may move to, the keyboard. No DOM,
// no requests: score.js draws what these say, and tests/studio_model.test.cjs checks them.
"use strict";

(() => {
  const LEVELS = ["out", "soft", "plays", "hard"];
  const KINDS = ["riser", "sweep", "roll", "stop"];  // a seam's transitions over the bars before (a stop in beats)
  const KIND_WORDS = { riser: "a riser", sweep: "a sweep", roll: "a snare roll", stop: "a stop", impact: "an impact", down: "a downlifter" };
  const words = (line) => String(line || "").replace(/\*/g, "").replace(/\{[^{}]*\}/g, "");  // no focus marks, no says (bass{fish})

  // ------------------------------------------------------------------ the grid
  // From /api/arrangement (sections, players, cells), the song's view (its words, its composition) and
  // /api/sound's boundaries: the regions on a ruler of bars, and one track per player, the singer first.
  function grid(arrangement, view, sound) {
    const c = view?.composition || {};
    const perBar = c.beats_per_bar || 4;
    const first = arrangement?.sections?.[0]?.start_beat || 0;
    const byId = new Map((c.sections || []).map((s) => [s.id, s]));
    const wordsAt = new Map(pageWords(view).map((w) => [w.index, w]));
    const seams = new Map((sound?.boundaries || []).map((b) => [b.id, b]));
    const order = view?.edits?.["form.order"];
    const clips = c.clips, marks = linkMarks(clips), yours = clipsYours(clips);
    const sections = (arrangement?.sections || []).map((s) => {
      const own = byId.get(s.id), w = wordsAt.get(s.index), seam = seams.get(s.id);
      const at = clipAt(clips, s.index), blank = !!at && !at.clip.source;
      // a blank clip's length is its lines' (op lines); any other's, as the arrangement lays it
      const lengths = blank ? clipLengths(at.clip, clips).filter((x) => !x.disabled).map((x) => x.bars) : null;
      const chords = (own?.phrases || []).flatMap((p) => (p.harmony || []).map((h) => h.name));
      return {
        id: s.id, index: s.index, name: s.name, label: s.label, role: s.role, bars: s.bars,
        startBar: Math.round((s.start_beat - first) / perBar) + 1, startBeat: s.start_beat, beats: s.duration_beats,
        startSeconds: s.start_seconds, endSeconds: s.end_seconds,
        sung: s.sung, canPlay: s.can_play, choir: !!s.choir, build: s.build, barOptions: lengths || s.bar_options || [s.bars],
        clip: at?.clip.id ?? null, instance: at?.instance ?? 0, blank, can: at?.clip.can || {}, link: at && marks.has(at.clip.id) ? marks.get(at.clip.id) : null,
        clipMine: !!at && yours.has(at.clip.id) || (at?.instance || 0) > 0 && !!clips?.stored,
        round: !!s.round, canRound: !!s.can_round, roundWords: s.round_words || "", roundWhy: s.round_why || "",
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
  // everyone in a section, or one player everywhere: a cell whose program's own level this is is given back to the
  // program (null), not kept as a choice of the same value
  function levelPatch(cells, level) {
    if (!LEVELS.includes(level)) throw new Error(`a level is ${LEVELS.join(", ")}`);
    return Object.fromEntries(cells.filter((cell) => cell?.paths?.level && cell.plays !== false)
      .map((cell) => [cell.paths.level, cell.program?.level === level ? null : level]));
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
    if (was.some((id, i) => id !== now[i])) return { error: "Repeated verses and refrains keep their story order." };
    return { order: next.map((s) => s.id) };
  }

  // Which sections a person moved: the fewest whose moving turns the program's order (for the shape now chosen,
  // the record's "was") into this one, the rest keeping their order (a longest common subsequence). One section
  // dragged past another could be either; `hint`, the ones the person dragged on this page, settles it.
  function movedIds(before, now, hint = []) {
    if (!Array.isArray(before) || !Array.isArray(now)) return new Set();
    const a = before.filter((id) => now.includes(id)), b = now.filter((id) => before.includes(id));
    const held = new Set(hint), w = (id) => (held.has(id) ? 1 - 1e-6 : 1);
    const t = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
    for (let i = a.length - 1; i >= 0; i--) for (let j = b.length - 1; j >= 0; j--)
      t[i][j] = a[i] === b[j] ? w(a[i]) + t[i + 1][j + 1] : Math.max(t[i + 1][j], t[i][j + 1]);
    const kept = new Set();
    for (let i = 0, j = 0; i < a.length && j < b.length;) {
      if (a[i] === b[j] && Math.abs(t[i][j] - (w(a[i]) + t[i + 1][j + 1])) < 1e-12) { kept.add(a[i]); i++; j++; }
      else if (t[i + 1][j] >= t[i][j + 1]) i++; else j++;
    }
    return new Set(b.filter((id) => !kept.has(id)));
  }

  // ------------------------------------------------------------------ clips: the song's sections as a person's own form
  // (docs/notes/STUDIO-CLIPS.md, "For the editor"). The view's composition.clips: the arrangement (stored, or the
  // form's own implicit one) and each clip with its lines, its instances (indexes in the sections) and what can be
  // done with it.
  const ROLE_NAMES = { intro: "Intro", verse: "Verse", refrain: "Refrain", turn: "Turn", break: "Break", bridge: "Bridge", tag: "Outro", outro: "Outro" };  // a tag (an older ending, sung) is an outro
  const SUNG_ROLES = ["verse", "refrain", "bridge", "tag"];
  const NEW_SECTION = { role: "verse", sung: true, bars: 8, lines: 4 };  // what + adds
  // the clip a section of the song is, and which time it comes (0 the first; a linked repeat 1, 2...)
  function clipAt(clips, index) {
    const clip = (clips?.clips || []).find((c) => (c.instances || []).includes(index));
    return clip ? { clip, instance: clip.instances.indexOf(index) } : null;
  }
  // the clips a person made or moved: a blank one, a copy (not the clip its source section became), and the fewest
  // whose moving makes this order from the source form's (movedIds); none without stored clips
  function clipsYours(clips) {
    const v = clips?.value;
    if (!clips?.stored || !v) return new Set();
    const ids = v.form.map((n, k) => `${n}:${v.form.slice(0, k).filter((x) => x === n).length}`);
    const home = new Map(v.form.map((n, k) => [ids[k], `${n.replace(/\d+$/, "")}${101 + k}`]));
    const out = new Set((clips.clips || []).filter((c) => !c.source || home.get(c.source) !== c.id).map((c) => c.id));
    const first = [...new Set(v.order)];
    for (const id of movedIds(v.form.map((_, k) => home.get(ids[k])), first)) out.add(id);
    return out;
  }
  // linked repeats: a clip sung more than once, each with its own mark (0, 1, 2...), in the order they first come
  function linkMarks(clips) {
    const out = new Map();
    for (const c of [...(clips?.clips || [])].sort((a, b) => a.instances[0] - b.instances[0])) if ((c.instances || []).length > 1) out.set(c.id, out.size);
    return out;
  }
  // bars shared evenly over a clip's lines, as the engine shares them (clips.operate, op blank)
  function evenBars(total, n) {
    return Array.from({ length: n }, (_, k) => Math.floor(total / n) + (k < total % n ? 1 : 0));
  }
  const lineSpecs = (clip) => (clip?.lines || []).map((l) => (l.of !== null && l.of !== undefined ? { of: l.of } : { bars: l.bars }));
  // the lengths a blank clip may have over its lines (each line 1 to line_bars bars, the clip and the song in bounds):
  // [{bars, disabled, why}] for 2, 4, 8 and 16 bars and its own
  function clipLengths(clip, clips) {
    const b = clips?.bounds || {}, n = (clip?.lines || []).length, most = b.line_bars || 8;
    const song = (clips?.clips || []).reduce((t, c) => t + c.bars * (c.instances || []).length, 0);
    return [...new Set([2, 4, 8, 16, clip.bars])].sort((x, y) => x - y).map((bars) => {
      const lines = n === 1 ? "One line is" : `${n} lines are`;
      const why = bars < n ? `${lines} ${n} bar${n === 1 ? "" : "s"} at least.` : bars > n * most ? `${lines} ${n * most} bars at most.`
        : bars > (b.clip_bars || 64) ? `A section is ${b.clip_bars || 64} bars at most.`
          : song + (bars - clip.bars) * clip.instances.length > (b.song_bars || 768) ? `A song is ${b.song_bars || 768} bars at most.` : null;
      return { bars, disabled: !!why, why };
    });
  }
  // a clip's lines changed: a line added (a blank line of `bars` at the end), the last taken away, or a blank line's
  // bars set; {lines} for op "lines", or {error}
  function clipLines(clip, clips, change) {
    const b = clips?.bounds || {}, most = b.line_bars || 8, lines = lineSpecs(clip);
    const total = (ls) => ls.reduce((t, l, i) => t + (l.bars ?? clip.lines[i]?.bars ?? 0), 0);
    if (change.add) {
      if (lines.length >= (b.lines || 16)) return { error: `A section has ${b.lines || 16} lines at most.` };
      lines.push({ bars: change.add });
    } else if (change.remove) {
      if (lines.length <= 1) return { error: "A section needs one line." };
      lines.pop();
    } else if (change.line !== undefined) {
      const l = lines[change.line];
      if (!l || l.of !== undefined) return { error: "This line is as long as its tune." };
      if (change.bars < 1 || change.bars > most) return { error: `A line is 1 to ${most} bars.` };
      l.bars = change.bars;
    }
    if (total(lines) > (b.clip_bars || 64)) return { error: `A section is ${b.clip_bars || 64} bars at most.` };
    return { lines };
  }
  // A section's place in the order moved: one operation on the clips (op move), the same whichever way it was moved
  function moveOp(sections, from, to) {
    if (from === to || to < 0 || to >= sections.length || from < 0 || from >= sections.length) return { error: "It is already there." };
    return { op: { op: "move", from, to } };
  }
  // The section ids (clip:n) the clips' order gives, in order: the nth time a clip comes is its nth instance
  function instanceIds(order) {
    const seen = {};
    return (order || []).map((c) => { const n = seen[c] || 0; seen[c] = n + 1; return `${c}:${n}`; });
  }
  // what a clip operation leaves selected: the clip made, the one moved where it went, the section after one deleted
  function selectedAfter(op, result, order) {
    const ids = instanceIds(result?.edits?.clips?.order || order);
    if (result?.clip) return `${result.clip}:0`;
    if (op.op === "move") return ids[op.to] ?? null;
    if (op.op === "repeat") return ids[op.at] ?? null;
    if (op.op === "delete") return ids[Math.min(op.at, ids.length - 1)] ?? null;
    return null;
  }
  // The Page's sections, in the song's order: the view's words cards (a song in clips has its own: explain.clip_words)
  function pageWords(view) {
    return view?.words || [];
  }
  // which editor a cell of the grid opens: the singer's row the melody, a player's its own roll or step grid, the
  // chords row the melody's chords; none for the voices before, or a player the notes don't have
  function cellEditor(track, players) {
    if (track?.kind === "singer") return { player: "voice" };
    if (track?.kind === "chords") return { player: "voice", chords: true };
    if (track?.kind === "player" && (players || []).some((p) => p.name === track.id)) return { player: track.id };
    return null;
  }
  // the grid row a Part menu's choice is
  function rowOfPart(player, tracks) {
    return player === "voice" ? (tracks || []).find((t) => t.kind === "singer") : (tracks || []).find((t) => t.kind === "player" && t.id === player);
  }

  // ------------------------------------------------------------------ a seam: what happens into a section
  // a sweep may be {bars, type}: a highpass rising (the default) or a lowpass falling (sound.py)
  const lasts = (v) => (v && typeof v === "object" ? v.bars : v);
  function seamWords(value) {
    if (!value) return "nothing: the band goes straight on";
    const parts = [];
    for (const k of KINDS) {
      const n = lasts(value[k]);
      if (!n) continue;
      const how = k === "sweep" && typeof value[k] === "object" ? (value[k].type === "lowpass" ? ", falling" : ", rising") : "";
      parts.push(`${KIND_WORDS[k]}${how} over ${n} ${k === "stop" ? "beat" : "bar"}${n === 1 ? "" : "s"}`);
    }
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
  // how long one kind lasts, the others as they are (a 4-bar riser with a 1-bar roll); a sweep keeps its direction
  function seamLength(value, kind, bars) {
    if (!value?.[kind] || kind === "impact") return value || null;
    return { ...value, [kind]: typeof value[kind] === "object" ? { ...value[kind], bars } : bars };
  }
  // the kinds that last, each with its length, in the order the page lists them (a stop's in beats)
  function seamLengths(value) {
    return [...KINDS, "down"].filter((k) => value?.[k]).map((k) => ({ kind: k, bars: lasts(value[k]), unit: k === "stop" ? "beat" : "bar" }));
  }
  function seamOver(value, bars) {  // how long: every kind that lasts, at once
    if (!value) return null;
    const next = { ...value };
    for (const k of [...KINDS, "down"]) if (next[k]) next[k] = typeof next[k] === "object" ? { ...next[k], bars } : bars;
    return next;
  }

  // ------------------------------------------------------------------ the scope of a chord or tune edit
  // Everywhere this line is sung, here only (the default for a new edit), and at the
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
    return from || (phrase?.place ? "place" : "line");
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
    const id = sel?.section || (sel && ["section", "seam", "line", "cell"].includes(sel.kind) ? sel.id : null);
    const s = id ? sections.find((x) => x.id === id) : null;
    return { section: s ? s.index : null, phrase: sel && (sel.kind === "note" || sel.kind === "chord") };
  }
  function neighbour(list, id, step) {
    const i = list.findIndex((x) => x.id === id);
    return i < 0 ? list[0] : list[Math.max(0, Math.min(list.length - 1, i + step))];
  }
  // the section a beat of the ruler is in: before bar 1 (the first pickup), the first; past the end, the last
  function sectionAtBeat(beat, sections) {
    if (!sections.length) return null;
    if (beat < sections[0].startBeat) return sections[0];
    return sections.find((x) => beat >= x.startBeat - 1e-9 && beat < x.startBeat + x.beats) || sections.at(-1);
  }
  // where the playhead is, in words: a section, a bar, and the time
  function position(beat, sections, perBar) {
    const s = sectionAtBeat(beat, sections);
    if (!s) return { label: "", bar: 1 };
    return { id: s.id, label: s.label, bar: s.startBar + Math.floor(Math.max(0, beat - s.startBeat) / perBar) };
  }
  // The sketch (composer.js) counts beats from the song's first pickup, as the composition view does; the ruler from
  // bar 1's bar line, as the arrangement does. A ruler's beat plus this is the sketch's: half a beat for an
  // eighth-note pickup, a bar more with a count-in.
  function sketchOffset(grid, composition) {
    const sketch = composition?.sections?.[0]?.start_beat, ruler = grid?.sections?.[0]?.startBeat;
    return Number.isFinite(sketch) && Number.isFinite(ruler) ? sketch - ruler : 0;
  }
  // where the sketch starts the song for the playhead, in its own beats: on the playhead's bar line; at bar 1 (or with
  // none), null, the song from its start with its first pickup, as it's sung
  function sketchFrom(playhead, grid, composition) {
    const first = grid?.sections?.[0];
    if (playhead === null || playhead === undefined || !first || playhead <= first.startBeat + 1e-9) return null;
    return playhead + sketchOffset(grid, composition);
  }

  // ------------------------------------------------------------------ the keyboard (docs/notes/STUDIO-REDESIGN.md's table)
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
    if (mod && !event.altKey && !event.shiftKey && (k === "d" || k === "D")) return { action: "duplicate" };  // (a section's: score.js)
    if (mod || event.altKey) return null;
    if ((k === "Delete" || k === "Backspace") && !event.shiftKey) return { action: "delete" };  // (a section's: score.js)
    if (k === " " || k === "Spacebar") return { action: "play", how: event.shiftKey ? "sung" : "sketch" };
    const plain = { k: "click", m: "mute", s: "solo", e: "record", t: "time", "?": "help", Enter: "open", Escape: "escape" };
    if (plain[k.length === 1 ? k.toLowerCase() : k] && !(k.length === 1 && event.shiftKey && k !== "?")) return { action: plain[k.length === 1 ? k.toLowerCase() : k] };
    if (["1", "2", "3", "4"].includes(k)) return { action: "view", view: ["page", "arrange", "mix", "sing"][Number(k) - 1] };
    if (k === "ArrowLeft" || k === "ArrowRight") return { action: "step", axis: "section", step: k === "ArrowLeft" ? -1 : 1 };
    if (k === "ArrowUp" || k === "ArrowDown") return { action: "step", axis: "track", step: k === "ArrowUp" ? -1 : 1 };
    return null;
  }

  // ------------------------------------------------------------------ a roll's scale and its notes (composer.js, parts.js, drums.js)
  // Pixels a beat: "fit" puts the whole span in the width (at least `least`); a number is a zoom on a scale where an
  // eighth note is wide enough to read its syllable (`base` pixels a beat, or the fit where that is wider), the roll
  // scrolling past the width.
  const ROLL_BEAT = 64;
  function rollUnit(zoom, available, span, { least = 12, base = ROLL_BEAT } = {}) {
    const fit = Math.max(least, available / Math.max(1, span));
    return zoom === "fit" ? fit : Math.max(fit, base) * (Number(zoom) || 1);
  }
  const zoomOf = (value) => (value === "fit" ? "fit" : Number(value) || 1);  // a Zoom menu's value
  // A note's resize handle on its right edge, in pixels: a quarter of a note's width, 4 to 9 pixels; none on a note
  // narrower than 20, whose whole face moves it (⌥-drag, ⇧←→ or the Length field change its length).
  function grip(width) { return width < 20 ? 0 : Math.max(4, Math.min(9, Math.round(width / 4))); }
  // Whether a note's label is drawn whole in `width` pixels (about `char` a character, `pad` of padding): a label
  // that doesn't fit isn't drawn cut short; the note's name and tooltip carry it.
  function labelFits(text, width, { char = 5.6, pad = 8 } = {}) {
    const n = [...String(text ?? "")].length;
    return n > 0 && n * char + pad <= width + 1e-9;
  }

  // ------------------------------------------------------------------ the snap
  // The snaps a roll offers: the melody's ¼, ⅓, ½ and a beat (a sung note is a quarter beat at least, so no ⅙); an
  // instrument's and a drum's ⅙ too (16 and 32 of the 96ths a beat its notes are kept in).
  const SNAPS = [[0.25, "¼"], [1 / 3, "⅓"], [0.5, "½"], [1, "1"]];
  const PART_SNAPS = [[1 / 6, "⅙"], ...SNAPS];
  // a time put on the snap's grid: a third's multiples exact as k / 3 (never 0.3333), so a third stays the third the
  // server keeps and two notes on thirds meet exactly
  function onGrid(value, grid) {
    const parts = Math.round(1 / grid);
    if (Math.abs(parts * grid - 1) < 1e-9) return Math.round(value * parts) / parts;
    return Math.round(Math.round(value / grid) * grid * 1e9) / 1e9;
  }
  // The snap a section opens on: ⅓ where its tune sits on thirds and not on halves (a six feel, a triplet lilt),
  // unless the snap is one of thirds already; otherwise the snap as it was. `times`: its notes' onsets and lengths.
  function feelSnap(times, snap) {
    const on = (parts) => times.length > 0 && times.every((t) => Math.abs(t * parts - Math.round(t * parts)) < 1e-6);
    const thirds = Math.abs(snap * 6 - Math.round(snap * 6)) < 1e-9 && Math.abs(snap * 4 - Math.round(snap * 4)) > 1e-9;
    return on(3) && !on(2) && !thirds ? 1 / 3 : snap;
  }
  // a snap the roll offers: one it hasn't (⅙ for the melody) gives way to the nearest it has
  function snapFor(snap, offered) {
    return offered.reduce((best, [s]) => (Math.abs(s - snap) < Math.abs(best - snap) - 1e-12 ? s : best), offered[0][0]);
  }

  // ------------------------------------------------------------------ the section's roll (composer.js)
  // The phrase a time of the section's roll belongs to. spans: each phrase's { off: its bar line, start: its earliest
  // note, end: its latest, final: its last note's latest start }, in beats from the section's start. Where the next
  // line's pickup lies in a line's last bar, a time past the line's last possible start is the next line's.
  function phraseAt(spans, t) {
    const inside = spans.map((s, i) => ({ ...s, i })).filter((s) => t >= s.start - 1e-9 && t < s.end - 1e-9);
    const here = inside.filter((s) => t >= s.off - 1e-9).at(-1), early = inside.find((s) => t < s.off - 1e-9);
    if (here && early && t > here.final + 1e-9) return early.i;
    return (here ?? early)?.i ?? null;
  }

  // The melody roll's rows are semitones above the tonic; a note is stored as a scale degree and a half step (alter).
  const MAJOR = [0, 2, 4, 5, 7, 9, 11];
  function semitone(degree, alter = 0, scale = MAJOR) {
    return Math.floor((degree - 1) / 7) * 12 + scale[((degree - 1) % 7 + 7) % 7] + (alter || 0);
  }
  // A semitone written as the scale writes it: a tone of the scale is its degree; one between two is the degree
  // below sharpened where it was reached going up, else the degree above flattened (F♯ climbing from F, G♭ falling
  // from G).
  function spell(semi, scale = MAJOR, up = false) {
    const octave = Math.floor(semi / 12), pc = semi - octave * 12, at = (k) => scale.indexOf(k);
    if (at(pc) >= 0) return { degree: octave * 7 + at(pc) + 1, alter: 0 };
    const below = { degree: octave * 7 + at(pc - 1) + 1, alter: 1 };
    const above = pc === 11 ? { degree: (octave + 1) * 7 + 1, alter: -1 } : { degree: octave * 7 + at(pc + 1) + 1, alter: -1 };
    if (up && at(pc - 1) >= 0) return below;
    return pc === 11 || at(pc + 1) >= 0 ? above : below;
  }
  // A note moved by rows (semitones) of the roll, inside the degrees lo..hi. Where it may carry a half step (a line
  // of its own's note, not slurred: chromatic), it lands on the row; elsewhere on the scale's next tone the way it
  // moved, keeping its own half step.
  function moveRows(note, rows, { scale = MAJOR, chromatic = false, lo = -Infinity, hi = Infinity } = {}) {
    const alter = note.alter || 0;
    if (!rows) return { degree: note.degree, alter };
    const up = rows > 0;
    if (chromatic) {
      const target = Math.min(semitone(hi, 0, scale), Math.max(semitone(lo, 0, scale), semitone(note.degree, alter, scale) + rows));
      return spell(target, scale, up);
    }
    let target = semitone(note.degree, 0, scale) + rows;
    while (spell(target, scale).alter) target += up ? 1 : -1;
    return { degree: Math.min(hi, Math.max(lo, spell(target, scale).degree)), alter };
  }

  // ------------------------------------------------------------------ several notes of a melody line at once
  // A note slurred on (slur) sings the syllable before it; a melody line's notes are in time order, none overlapping.
  // The notes a time move takes: each chosen note with the rest of its syllable (a melisma moves whole).
  function withSyllables(notes, indices) {
    const out = new Set();
    for (const i of indices) {
      let a = i, z = i;
      while (a > 0 && notes[a].slur) a--;
      while (notes[z + 1]?.slur) z++;
      for (let k = a; k <= z; k++) out.add(k);
    }
    return [...out].sort((x, y) => x - y);
  }
  // How far (beats) the chosen notes move together for a wish of dt: the anchor note lands on the grid, and none
  // passes an unchosen neighbour, the line's start or end, or (the line's last note) its latest start.
  function shiftLimit(notes, indices, dt, b, grid, anchor = indices[0]) {
    const set = new Set(indices), a = notes[anchor];
    if (!set.size || !a || !dt) return 0;
    const want = onGrid(a.onset + dt, grid) - a.onset;
    let lo = -Infinity, hi = Infinity;
    for (let i = 0; i < notes.length; i++) {
      if (!set.has(i) || set.has(i - 1)) continue;
      let j = i;
      while (set.has(j + 1)) j++;
      const before = i ? notes[i - 1].onset + notes[i - 1].duration : b.min_onset;
      const after = j < notes.length - 1 ? notes[j + 1].onset : b.max_end;
      lo = Math.max(lo, before - notes[i].onset);
      hi = Math.min(hi, after - (notes[j].onset + notes[j].duration));
      if (j === notes.length - 1) hi = Math.min(hi, (b.max_final_onset ?? b.max_end) - notes[j].onset);
    }
    if (lo > hi + 1e-9) return 0;
    const v = Math.min(hi, Math.max(lo, want)), twelfths = Math.round(v * 12);  // a quarter's, a third's, a sixth's: exact
    return Math.abs(v * 12 - twelfths) < 1e-6 ? twelfths / 12 : Math.round(v * 1e9) / 1e9;
  }
  // The chosen notes taken out: a syllable with its melisma; a slurred note alone joins the note before.
  function deleteNotes(notes, indices) {
    const set = new Set(indices), out = [];
    let dropping = false;
    notes.forEach((n, i) => {
      if (!n.slur) dropping = set.has(i);
      if (dropping) return;
      if (set.has(i) && n.slur && out.length) { const prev = out.at(-1); prev.duration = n.onset + n.duration - prev.onset; return; }
      out.push({ ...n });
    });
    return out;
  }
  // Notes copied: each as written, timed from the first's start. A slurred note stays slurred only after its own.
  function clipOf(notes, indices) {
    const chosen = indices.map((i) => notes[i]);
    return { start: chosen[0].onset, end: chosen.at(-1).onset + chosen.at(-1).duration,
      notes: chosen.map((n, k) => ({ degree: n.degree, onset: n.onset, duration: n.duration,
        ...(n.slur && k && indices[k - 1] === indices[k] - 1 ? { slur: true } : !n.slur && n.alter ? { alter: n.alter } : {}) })) };
  }
  // Copied notes put in at a time (beats of the line), each in place of any note it overlaps. A slurred note
  // without a note ending where it starts sings a syllable of its own. Returns the notes, and where the
  // pasted ones are; refuses (throws) notes that don't fit the line.
  function pasteAt(notes, clip, at, b) {
    const shift = at - clip.start, most = b.melisma || 4;
    const put = clip.notes.map((n) => ({ ...n, onset: Math.round((n.onset + shift) * 1e9) / 1e9, syllable: n.slur ? "" : "?", word: "", pasted: true }));
    if (!put.length || put.some((n) => n.onset < b.min_onset - 1e-8 || n.onset + n.duration > b.max_end + 1e-8))
      throw new Error("These notes don't fit here.");
    const kept = notes.filter((n) => !put.some((m) => n.onset < m.onset + m.duration - 1e-8 && n.onset + n.duration > m.onset + 1e-8));
    const out = [...kept.map((n) => ({ ...n })), ...put].sort((x, y) => x.onset - y.onset);
    let run = 0;
    out.forEach((n, i) => {
      if (n.slur && (!i || Math.abs(out[i - 1].onset + out[i - 1].duration - n.onset) > 1e-8 || run >= most - 1)) {
        delete n.slur; n.syllable = "?";
      }
      run = n.slur ? run + 1 : 0;
      if (n.slur) n.alter = 0;
    });
    if (out.at(-1).onset > (b.max_final_onset ?? b.max_end) + 1e-8)
      throw new Error("The last note would leave the next line's pickup no room.");
    const added = out.flatMap((n, i) => (n.pasted ? [i] : []));
    out.forEach((n) => delete n.pasted);
    return { notes: out, added };
  }
  // The chosen notes' starts and ends put on the grid (beats), each still at least a grid step long: a slurred
  // note still starts where the one before ends, no note overlaps the next, and the line's last note leaves the next
  // line's pickup its room. Returns the notes, or throws where they can't all go on the grid.
  function quantizeNotes(notes, indices, grid, b) {
    const set = new Set(indices), at = (t) => onGrid(t, grid);
    const out = notes.map((n, i) => {
      if (!set.has(i)) return { ...n };
      const onset = at(n.onset), end = Math.max(at(n.onset + n.duration), onset + grid);
      return { ...n, onset, duration: at(end - onset) };
    });
    for (let i = 0; i < out.length; i++) {
      const n = out[i], prev = out[i - 1], next = out[i + 1];
      if (n.slur && prev) { const end = n.onset + n.duration; n.onset = prev.onset + prev.duration; n.duration = end - n.onset; }
      if (next && n.onset + n.duration > next.onset + 1e-9) n.duration = (next.slur ? next.onset + next.duration - grid : next.onset) - n.onset;
    }
    const last = out.at(-1), least = Math.min(grid, b.min_duration ?? grid) - 1e-9;
    if (out.some((n, i) => n.duration < least || n.onset < b.min_onset - 1e-9 || n.onset + n.duration > b.max_end + 1e-9 ||
      (i && n.onset < out[i - 1].onset + out[i - 1].duration - 1e-9)) || last.onset > (b.max_final_onset ?? b.max_end) + 1e-9)
      throw new Error("These notes need a finer snap.");
    return out;
  }
  // the shortcuts of a roll with notes selected: copy, cut, paste, duplicate, all (never in a text field)
  function rollKey(event) {
    if (inField(event.target) || !(event.metaKey || event.ctrlKey) || event.altKey || event.shiftKey) return null;
    const action = { c: "copy", x: "cut", v: "paste", d: "duplicate", a: "all" }[String(event.key).toLowerCase()];
    return action ? { action } : null;
  }

  // ------------------------------------------------------------------ said after an edit (the live region)
  function saidCell(track, section, level) {
    return level === "out" ? `${section.label}: the ${track.label} sits out` : `${section.label}: the ${track.label} now ${level === "plays" ? "plays" : `plays ${level}`}`;
  }

  // Words can establish a new rhythm. Keep the contour and span, allocate whole
  // grid steps to each syllable, and leave the original phrase untouched.
  function fitNotes(phrase, count, text = "") {
    const source = (phrase.notes || []).filter((n) => !n.slur), b = phrase.bounds || {};
    if (!Number.isInteger(count) || count < 1 || count > 32) throw new Error("Write 1 to 32 syllables for this line.");
    if (!source.length) {
      if (!phrase.own_path) throw new Error("Choose a line with a melody first.");
      return blankTune(phrase, count, text);
    }
    const grid = b.min_duration || 0.25;
    const start = Math.max(b.min_onset ?? -phrase.pickup_beats, source[0].onset);
    const end = Math.min(b.max_end ?? phrase.duration_beats, Math.max(source.at(-1).onset + source.at(-1).duration, start + count * grid));
    const step = Math.floor((end - start + 1e-8) / count / grid) * grid;
    if (step < grid || start + (count - 1) * step > (b.max_final_onset ?? end - grid) + 1e-8)
      throw new Error("These words need more room than this line has.");
    return Array.from({ length: count }, (_, i) => {
      const n = source[Math.round(i * (source.length - 1) / Math.max(1, count - 1))];
      return { degree: n.degree, ...(n.alter ? { alter: n.alter } : {}), onset: start + i * step,
        duration: i === count - 1 ? end - (start + i * step) : step };
    });
  }
  // A blank line's first notes, for words written into it: a syllable a beat where the line has room (less where it
  // hasn't, on its grid), from its first bar line, the last held up to two beats. Their tune is one of a bank's
  // (TUNES), each a pair: a section's lines take them by turns, one ending away from home, the next coming home to
  // the tonic, as its last line always does. Which pair is the line's section's and its words' (the same words on the same line, the same tune).
  const TUNES = [
    [[3, 4, 5, 5, 4, 3, 2, 2], [3, 4, 5, 5, 4, 3, 2, 1]],
    [[1, 2, 3, 5, 5, 6, 5, 5], [5, 6, 5, 3, 2, 3, 2, 1]],
    [[5, 5, 6, 5, 3, 3, 2, 2], [5, 5, 6, 5, 3, 2, 1, 1]],
    [[1, 1, 3, 3, 5, 5, 6, 5], [6, 6, 5, 5, 3, 3, 2, 1]],
    [[5, 3, 5, 6, 5, 3, 2, 3], [5, 3, 5, 6, 5, 2, 3, 1]],
    [[3, 3, 2, 1, 2, 3, 5, 5], [3, 3, 2, 1, 2, 3, 2, 1]],
    [[1, 3, 5, 8, 6, 5, 6, 5], [8, 6, 5, 3, 5, 3, 2, 1]],
    [[6, 5, 3, 5, 6, 5, 3, 2], [6, 5, 3, 5, 3, 2, 1, 1]],
  ];
  function tuneFor(phrase, text) {
    const [, section = "", line = "0"] = /^line\.(.*)\.(\d+)$/.exec(phrase.own_path || "") || [];
    let h = 2166136261;  // (FNV-1a)
    for (const c of `${section}|${String(text).toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim()}`) h = Math.imul(h ^ c.codePointAt(0), 16777619);
    return TUNES[(h >>> 0) % TUNES.length][phrase.closes || Number(line) % 2 ? 1 : 0];
  }
  function blankTune(phrase, count, text = "") {
    const b = phrase.bounds || {}, grid = b.min_duration || 0.25, tune = tuneFor(phrase, text);
    const within = (d) => {  // an octave down or up where the song's range stops short of it
      while (b.max_degree != null && d > b.max_degree && d - 7 >= (b.min_degree ?? -Infinity)) d -= 7;
      while (b.min_degree != null && d < b.min_degree && d + 7 <= (b.max_degree ?? Infinity)) d += 7;
      return d;
    };
    const start = Math.max(0, b.min_onset ?? 0), end = b.max_end ?? phrase.duration_beats;
    const step = Math.min(1, Math.floor((end - start + 1e-8) / count / grid) * grid);
    if (step < grid || start + (count - 1) * step > (b.max_final_onset ?? end - grid) + 1e-8)
      throw new Error("These words need more room than this line has.");
    return Array.from({ length: count }, (_, i) => {
      const onset = start + i * step;
      return { degree: within(count === 1 ? 1 : tune[Math.round(i * (tune.length - 1) / (count - 1))]), onset,
        duration: i === count - 1 ? Math.min(end - onset, Math.max(step, 2)) : step };
    });
  }
  // a line with nothing in it yet: sung, its words and notes to write (a blank line, or one emptied)
  const isBlank = (phrase) => !!phrase?.own_path && !(phrase.notes || []).length;
  function writtenNotes(notes) {
    return notes.map((n) => ({ degree: n.degree, onset: n.onset, duration: n.duration,
      ...(n.slur ? { slur: true } : n.alter ? { alter: n.alter } : {}) }));
  }
  function lyricPatch(phrase, text, fit = false) {
    if (fit || phrase.own) {
      if (!phrase.own_path) throw new Error("Choose a sung line to write new words.");
      const count = String(text).replace(/\{[^{}]*\}/g, "").trim().split(/[\s-]+/u).filter(Boolean).length;
      return { [phrase.own_path]: { words: text, notes: fit ? fitNotes(phrase, count, text) : writtenNotes(phrase.notes) } };
    }
    return { [phrase.lyric_path]: text };
  }
  // ------------------------------------------------------------------ the whole lyric at once (author.js's sheet)
  // The sections a lyric sheet writes, in the song's order: each sung words once (a refrain's are the same every
  // time it comes), with the lines that can be written.
  function lyricTargets(composition) {
    const seen = new Set(), out = [];
    for (const s of composition?.sections || []) {
      const phrases = (s.phrases || []).filter((p) => p.lyric_path);
      const key = s.lyric_key || phrases[0]?.lyric_path?.split(".").slice(0, -1).join(".");
      if (!s.sung || !phrases.length || seen.has(key)) continue;
      seen.add(key);
      out.push({ key, id: s.id, label: s.label, phrases });
    }
    return out;
  }
  function lyricSheet(targets) {
    return targets.map((t) => [`[${t.label}]`, ...t.phrases.map((p) => p.lyric_text || "")].join("\n")).join("\n\n");
  }
  // A sheet's paragraphs: a blank line between sections; a line in brackets ([Verse 2]) names the one it starts.
  function parseLyricSheet(text) {
    const blocks = [];
    let block = null;
    String(text).split(/\r?\n/).forEach((raw, at) => {
      const line = raw.trim();
      if (!line) { block = null; return; }
      if (/^\[[^\]]*\]$/.test(line)) { block = { label: line.slice(1, -1).trim(), lines: [] }; blocks.push(block); return; }
      if (!block) { block = { label: null, lines: [] }; blocks.push(block); }
      block.lines.push({ text: line, at });
    });
    return blocks.filter((b) => b.lines.length);
  }
  // Each paragraph onto the next section, line by line: a line changed is written, its notes fitted to it where its
  // count of syllables differs from the tune's. Lines left out keep their words. Returns the one patch, what each
  // line does, and what can't be (a paragraph or a line too many, words that don't fit).
  function lyricSheetPatch(targets, blocks, count) {
    const patch = {}, lines = [], errors = [];
    const many = (n, one) => `${n} ${one}${n === 1 ? "" : "s"}`;
    if (blocks.length > targets.length) errors.push({ message: `This song has ${many(targets.length, "sung section")}, not ${blocks.length}.` });
    blocks.slice(0, targets.length).forEach((block, b) => {
      const t = targets[b];
      if (block.lines.length > t.phrases.length) errors.push({ block: b, message: `${t.label} has ${many(t.phrases.length, "line")}, not ${block.lines.length}.` });
      block.lines.slice(0, t.phrases.length).forEach((line, i) => {
        const p = t.phrases[i], n = count(line.text), entry = { block: b, line: i, at: line.at, label: t.label, text: line.text,
          syllables: n, want: p.syllable_count, changed: line.text !== p.lyric_text, fitted: false, paths: [] };
        lines.push(entry);
        if (!entry.changed) return;
        try {
          const one = lyricPatch(p, line.text, n !== p.syllable_count);
          entry.fitted = n !== p.syllable_count;
          entry.paths = Object.keys(one);
          Object.assign(patch, one);
        } catch (error) { entry.error = error.message; errors.push({ block: b, line: i, message: `${t.label}, line ${i + 1}: ${error.message}` }); }
      });
    });
    return { patch, lines, errors };
  }
  function phrasePatch(source, target) {
    const a = source.bounds?.min_onset ?? -(source.pickup_beats || 0), b = target.bounds?.min_onset ?? -(target.pickup_beats || 0);
    const ratio = (target.duration_beats - b) / (source.duration_beats - a);
    const notes = writtenNotes(source.notes).map((n) => ({ ...n, onset: b + (n.onset - a) * ratio, duration: n.duration * ratio }));
    const limits = target.bounds || {}, count = notes.filter((n) => !n.slur).length;
    if (isBlank(source)) return chordsAndParts(source, target, a, b, ratio);  // a blank line carries no melody: the destination's stays
    if ((!count && target.tune_syllable_count !== 0) || notes.some((n) => n.duration < (limits.min_duration || 0.25) - 1e-8 ||
      n.degree < limits.min_degree || n.degree > limits.max_degree) || notes.at(-1)?.onset > (limits.max_final_onset ?? target.duration_beats) + 1e-8)
      throw new Error("This melody doesn't fit that phrase.");
    const patch = {};
    if (target.own_path && source.lyric_text) {
      patch[target.own_path] = { words: source.lyric_text, notes };
    } else if (count) {
      if (count !== target.tune_syllable_count || notes.some((n) => n.alter))
        throw new Error("Paste these words and notes into a sung phrase.");
      patch[target.place ? `tune.${target.place}` : target.path] = notes;
    }
    return Object.assign(patch, chordsAndParts(source, target, a, b, ratio));
  }
  // a line's chords and players' notes, onto another line (its bars, its time)
  function chordsAndParts(source, target, a, b, ratio) {
    const patch = {}, bars = target.chords?.length || 0;
    if (bars && source.chords?.length) patch[target.place ? `chords.${target.place}` : target.chords_path] =
      Array.from({ length: bars }, (_, i) => [...source.chords[Math.floor(i * source.chords.length / bars)]]);
    // Custom instrumental notes are optional: absence restores procedural playing
    // at the destination; an empty array deliberately keeps a rest.
    for (const player of new Set([...Object.keys(source.part_notes || {}), ...Object.keys(target.part_notes || {})])) {
      const held = source.part_notes?.[player];
      patch[`part.${player}.${target.part_key}`] = held ? held.map(([onset, duration, pitch, velocity]) =>
        [Math.round((b + (onset / 96 - a) * ratio) * 96), Math.max(1, Math.round(duration * ratio)), pitch, velocity]) : null;
    }
    return patch;
  }
  // a section's contents onto another of as many lines; any other is refused, saying how many
  function sectionPatch(source, target) {
    const n = source?.phrases?.length || 0;
    if (!n || n !== target.phrases?.length)
      throw new Error(`These contents are ${n} line${n === 1 ? "" : "s"}: paste them into a section of ${n}.`);
    return Object.assign({}, ...source.phrases.map((p, i) => phrasePatch(p, target.phrases[i])));
  }

  const api = { LEVELS, KIND_WORDS, grid, look, whoseWords, cellLabel, lockPatch, releasePatch, levelPatch, optionLock,
    moveOrder, movedIds, ROLE_NAMES, SUNG_ROLES, NEW_SECTION, clipAt, clipsYours, linkMarks, evenBars, lineSpecs, clipLengths, clipLines, moveOp,
    instanceIds, selectedAfter, pageWords, cellEditor, rowOfPart, seamWords, seamToggle, seamOver, seamLength, seamLengths, scopeOptions, scopeStart, selectionKey, defaultHow, playTarget,
    neighbour, sectionAtBeat, position, sketchOffset, sketchFrom, inField, keyAction, ROLL_BEAT, rollUnit, zoomOf, grip, labelFits,
    SNAPS, PART_SNAPS, onGrid, feelSnap, snapFor,
    phraseAt, semitone, spell, moveRows,
    withSyllables, shiftLimit, deleteNotes, clipOf, pasteAt, quantizeNotes, rollKey, saidCell, fitNotes, blankTune, isBlank, writtenNotes, lyricPatch,
    lyricTargets, lyricSheet, parseLyricSheet, lyricSheetPatch, phrasePatch, sectionPatch };
  if (typeof window !== "undefined") window.SongbirdModel = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})();
