// The score (docs/STUDIO-REDESIGN.md): one transport, three views of the song (Page, Arrange, Mix), one inspector
// that shows whatever is selected, Your tools as a sheet and Time as a drawer. It draws; studio.js keeps the edits,
// the history, the drafts and the listening (its globals: state, h, api, setEdit, listen, record...), composer.js the
// notes and the sketch, author.js a line of words, players.js where the sketch's players go, perform.js notes in.
// Pure parts are model.js's. Everything shown is built as text: nothing from an answer is read as markup.
"use strict";

(() => {
  const M = window.SongbirdModel;
  const $ = (id) => document.getElementById(id);
  const C = () => window.SongbirdComposer;
  const P = () => window.SongbirdPlayers?.ui;
  const S = {
    view: "page", sel: null, how: "sung", howSet: false, open: null, arr: null, sound: null, grid: null, serial: 0,
    keyed: false, about: false, playhead: null, sketch: false, recording: null, why: {}, tall: false, pop: null,
    lastOptions: {}, dragged: new Set(), moved: new Set(), movedKey: null,
  };
  const card = (id) => state.view?.cards?.find((c) => c.id === id);
  const edited = (path) => Object.prototype.hasOwnProperty.call(state.edits, path) && state.edits[path] !== null;
  const was = (path) => state.view?.marks?.[path]?.was;
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;
  const narrow = () => ($("app")?.clientWidth || innerWidth) <= 620;
  const compIndex = (id) => (state.view?.composition?.sections || []).findIndex((s) => s.id === id);
  const sectionAt = (id) => S.grid?.sections.find((s) => s.id === id);
  const wordsOf = (s) => state.view?.words?.find((w) => w.index === s?.index);
  function say(text) { const el = $("said"); if (el) { el.textContent = ""; setTimeout(() => { el.textContent = text; }, 40); } }
  function lockIcon() {
    return svg("svg", { class: "lock", viewBox: "0 0 9 11", "aria-hidden": "true" },
      svg("path", { d: "M2 5V3.4a2.5 2.5 0 0 1 5 0V5", fill: "none", stroke: "currentColor", "stroke-width": "1.4" }),
      svg("rect", { x: "0.5", y: "5", width: "8", height: "5.5", rx: "1", fill: "currentColor" }));
  }
  // redraw without losing the keyboard's place: the focused element is found again by its data-key or id
  function keepFocus(draw) {
    const a = document.activeElement, key = a?.dataset?.key, id = a?.id;
    draw();
    if (!a || document.activeElement === a || !(key || id)) return;
    const again = key ? document.querySelector(`[data-key="${CSS.escape(key)}"]`) : $(id);
    again?.focus({ preventScroll: true });
  }

  // ------------------------------------------------------------------ views
  const ABOUT = {
    page: "The words as this version sings them. A word with a dashed line under it can change: pick another and the tune keeps its syllables. Select a section's name or a line to change more; ▶ plays that part, sung.",
    arrange: "The song as a timeline: its sections over a ruler of bars, and under them a row for each player. A cell says whether that player plays there and how hard. Select a section, a player, a cell, or the seam between two. Double-click a section for its notes (its tune and chords), or the singer's row for its words; the section's column has both.",
    mix: "A strip for each player (its level, where it sits, how it pumps), then the voice and the room. Judge the voice against the band on the whole song.",
  };
  function showView(v, focus = false) {
    if (!["page", "arrange", "mix"].includes(v)) return;
    S.view = v;
    for (const t of document.querySelectorAll("#tabs [role=tab]")) {
      const on = t.dataset.view === v;
      t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    }
    for (const b of document.querySelectorAll("#bottombar [data-view]")) b.setAttribute("aria-pressed", String(b.dataset.view === v));
    for (const m of document.querySelectorAll("main.view")) m.hidden = m.dataset.view !== v;
    $("viewAbout").textContent = ABOUT[v];
    if (v !== "arrange") C()?.stop?.();
  }

  // ------------------------------------------------------------------ what is selected
  function select(sel, options = {}) {
    S.sel = sel || null;
    S.about = false;
    if (sel) S.songShown = false;
    if (!sel || !["note", "chord"].includes(sel.kind)) C()?.deselect?.();
    if (!S.howSet) setHow(M.defaultHow(sel), false);
    repaint();
    const keyed = S.keyed || options.keyboard;
    S.keyed = false;
    if (keyed && sel) $("inspectorTitle")?.focus({ preventScroll: false });
    idle();
  }
  function repaint() { renderPage(); renderGrid(); renderMix(); renderInspector(); }
  function composerSelected(kind) {  // composer.js: a note or a chord chosen in the roll, or let go
    if (kind) select({ kind, section: S.open });
    else if (S.sel && ["note", "chord"].includes(S.sel.kind)) select({ kind: "section", id: S.open });
  }
  function openNotes(id, focus = false) {
    const i = compIndex(id);
    if (i < 0) return;
    S.open = id;
    if (S.sel && ["note", "chord"].includes(S.sel.kind) && S.sel.section !== id) S.sel = { kind: "section", id };  // the old note's gone
    $("notes").hidden = false;
    if (S.view !== "arrange") showView("arrange");
    C()?.open?.(i);
    renderGrid();
    renderInspector();
    if (focus) $("notesTitle")?.focus();
    $("notes").scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }
  // a section's words, to edit: the Page, scrolled to it, its first line that can be written in the column, ready
  function editWords(id, line = null) {
    const s = sectionAt(id), phrases = state.view?.composition?.sections?.find((x) => x.id === id)?.phrases || [];
    const j = line ?? phrases.findIndex((p) => p.lyric_path);
    if (!s || j < 0 || !phrases[j]?.lyric_path) return false;
    showView("page");
    select({ kind: "line", id, line: j });
    $(`sec-${s.index}`)?.scrollIntoView?.({ block: "start", behavior: "smooth" });
    const input = $("inspector").querySelector("textarea");
    input?.focus({ preventScroll: true });
    say(`${s.label}, line ${j + 1}: write it here`);
    return true;
  }
  const canWrite = (id) => (state.view?.composition?.sections?.find((x) => x.id === id)?.phrases || []).some((p) => p.lyric_path);
  function closeNotes() {
    C()?.stop?.(); C()?.deselect?.();
    S.open = null;
    $("notes").hidden = true;
    if (S.sel && ["note", "chord"].includes(S.sel.kind)) select({ kind: "section", id: S.sel.section });
    else renderGrid();
  }

  // ------------------------------------------------------------------ the transport
  function setHow(how, chosen = true) {
    S.how = how;
    if (chosen) S.howSet = true;
    for (const b of document.querySelectorAll("[data-how]")) b.setAttribute("aria-pressed", String(b.dataset.how === how));
    for (const b of document.querySelectorAll(".regioncell > .play")) {  // the regions' ▶ say how they play
      const label = b.getAttribute("aria-label").replace(/, (sung|the sketch)$/, `, ${how === "sung" ? "sung" : "the sketch"}`);
      b.setAttribute("aria-label", label); b.title = label;
    }
  }
  const making = () => ["queued", "running"].includes(state.playing?.job?.state) && !state.playing?.task?.cancelled;
  const sounding = () => !!C()?.playing?.() || !$("audio").paused;
  function stopAll() { C()?.stop?.(); pauseAudio(); paintPlay(); idle(); }
  function play(how = S.how) {
    if (sounding() || making() || (state.playing?.task && !state.playing.job)) { stopAll(); return; }
    const secs = S.grid?.sections || [];
    const t = M.playTarget(S.sel, secs);
    if (how === "sketch") {
      if (!state.view?.composition?.sections?.length) return;
      const s = secs.find((x) => x.index === t.section);
      if (t.phrase && S.open) C().sketch({ scope: "phrase", index: compIndex(S.open) });
      else if (s) C().sketch({ scope: "section", index: compIndex(s.id) });
      else C().sketch({ scope: "song", from: S.playhead });
    } else listen("you", t.section);
    paintPlay();
  }
  function paintPlay() {
    const on = sounding() || making();
    const b = $("tPlay");
    b.textContent = on ? "■" : "▶";
    b.classList.toggle("playing", on);
    b.setAttribute("aria-label", on ? "Stop (Space)" : "Play (Space)");
    b.title = on ? "Stop (Space): back to where it started" : "Play what is selected (Space; Shift+Space sung); press again to stop";
  }
  function tick(beat, fraction) {  // composer.js, as the sketch plays (null when it stops)
    const head = $("gridHead");
    if (beat === null) {
      S.sketch = false;
      document.querySelectorAll(".cell.playing").forEach((c) => c.classList.remove("playing"));
      if (head && S.playhead === null) head.hidden = true;
      paintPlay(); idle();
      return;
    }
    S.sketch = true;
    const g = S.grid;
    if (!g) return;
    const where = M.position(beat, g.sections, g.perBar);
    $("nowTitle").textContent = `${where.label} · bar ${where.bar}`;
    $("nowSub").textContent = "the sketch";
    $("barFill").style.width = `${Math.round((fraction || 0) * 1000) / 10}%`;
    placeHead(beat);
    paintPlay();
  }
  function placeHead(beat) {
    const head = $("gridHead"), g = S.grid;
    if (!head || !g || beat === null) return;
    const s = g.sections.find((x) => beat >= x.startBeat - 1e-9 && beat < x.startBeat + x.beats) || g.sections.at(-1);
    const cell = document.querySelector(`[data-region="${CSS.escape(s.id)}"]`);
    if (!cell) return;
    head.hidden = false;
    head.style.left = `${cell.offsetLeft + cell.offsetWidth * Math.min(1, Math.max(0, (beat - s.startBeat) / s.beats))}px`;
  }
  function idle() {  // the position field when nothing is being made or heard: where the selection is, the length
    if (S.sketch || S.recording || making() || !$("audio").paused) return;
    const s = S.sel?.id ? sectionAt(S.sel.id) : S.sel?.section ? sectionAt(S.sel.section) : null;
    const g = S.grid, total = state.view?.composition?.duration;
    const at = S.playhead !== null && g ? M.position(S.playhead, g.sections, g.perBar) : null;
    $("nowTitle").textContent = s ? s.label : at ? at.label : "The whole song";
    $("nowSub").textContent = s ? `bar ${s.startBar}, ${s.bars} bars` : at ? `bar ${at.bar}` : g ? `${g.bars} bars` : "";
    $("nowTime").textContent = total ? fmtTime(total) : "";
    $("barFill").style.width = "0";
    $("bar").classList.remove("making");
    $("position").classList.remove("stale");
  }
  function playerChanged(title, sub, busy) {  // studio.js's player: a preview being made, or playing
    $("position").classList.toggle("stale", /^Earlier version/.test($("nowSub").textContent));
    paintPlay();
  }
  function recording(words, progress) {  // studio.js: a recording on its way (null when done)
    S.recording = words;
    if (!words) { idle(); return; }
    $("nowTitle").textContent = "Recording";
    $("nowSub").textContent = words.replace(/^Recording: /, "");
    $("bar").classList.add("making");
    $("barFill").style.width = pct(progress);
  }
  function wholeSongAt() {  // the whole song heard: say which section the audio is in
    const g = S.grid, a = $("audio");
    if (!g || state.playing?.section !== null || !a.duration) return;
    const t = a.currentTime;
    const s = g.sections.find((x) => t >= x.startSeconds && t < x.endSeconds);
    if (s) { $("nowTitle").textContent = `${s.label}`; $("nowSub").textContent = "sung"; }
  }

  function renderTransport() {
    const v = state.view, tempo = card("tempo"), key = card("key");
    if (tempo) {
      $("tempoValue").textContent = Math.round(tempo.tempo);
      $("tempoBtn").classList.toggle("you", edited("tempo"));
      $("tempoBtn").title = `Tempo: ${tempo.value}${edited("tempo") && was("tempo") ? `; was ${Math.round(was("tempo"))}` : ""}. This style: ${tempo.range?.min} to ${tempo.range?.max}`;
      $("tempoBtn").setAttribute("aria-label", `Tempo ${Math.round(tempo.tempo)} beats a minute${edited("tempo") ? ", yours" : ""}`);
    }
    if (key) {
      $("keyBtn").textContent = key.value;
      $("keyBtn").classList.toggle("you", edited("tonic") || edited("mode"));
      $("keyBtn").setAttribute("aria-label", `Key: ${key.value}${edited("tonic") || edited("mode") ? ", yours" : ""}`);
    }
    const by = v.by.replace(/^a made-up machine called /, "");
    $("whichShort").textContent = `${v.offset ? v.date : "today"} · ${by}`;
    if (S.pop === "tempoPop") tempoPop();
    if (S.pop === "keyPop") keyPop();
  }
  const opener = (id) => ({ howPop: narrow() ? "positionNow" : "howMore", tempoPop: "tempoBtn", keyPop: "keyBtn" })[id];
  function togglePop(id) {
    const open = S.pop !== id;
    for (const p of ["howPop", "tempoPop", "keyPop"]) $(p).hidden = true;
    for (const b of ["howMore", "tempoBtn", "keyBtn", "positionNow"]) $(b).setAttribute("aria-expanded", "false");
    S.pop = open ? id : null;
    if (!open) return;
    if (id === "tempoPop") tempoPop();
    if (id === "keyPop") keyPop();
    $(id).hidden = false;
    $(opener(id)).setAttribute("aria-expanded", "true");
    $(id).querySelector("input, button, select")?.focus();
  }
  function tempoPop() {
    const c = card("tempo");
    if (!c) return;
    const range = { ...state.start.bounds.tempo, ...(c.range || {}) };
    const out = h("output", { class: edited("tempo") ? "you" : null }, `${Math.round(c.tempo)}`);
    const number = h("input", { type: "number", id: "tempoNumber", min: range.min, max: range.max, step: 1, value: Math.round(c.tempo), "aria-label": "Tempo in beats a minute" });
    const slider = h("input", { type: "range", min: range.min, max: range.max, step: 1, value: c.tempo, class: edited("tempo") ? "you" : null, "aria-label": "Tempo" });
    const commit = (value) => {
      if (!Number.isFinite(value) || value < range.min || value > range.max) { number.value = Math.round(c.tempo); toast(`Choose a tempo from ${range.min} to ${range.max} for this style.`); return; }
      setEdit("tempo", value, "Change tempo");
    };
    number.addEventListener("change", () => commit(Number(number.value)));
    slider.addEventListener("input", () => { out.textContent = slider.value; number.value = slider.value; });
    slider.addEventListener("change", () => commit(Number(slider.value)));
    $("tempoPop").replaceChildren(
      h("label", { class: "field" }, h("span", { class: "label" }, "Beats a minute ", out), number),
      slider, h("div", { class: "ends hint" }, `${c.value}. This style: ${range.min} to ${range.max}.`),
      edited("tempo") ? h("div", { class: "row" }, h("span", { class: "hint" }, `yours; the program's was ${Math.round(was("tempo") || 0)}`),
        h("button", { class: "link small", type: "button", onclick: () => releaseEdit("tempo", "The program's tempo") }, "The program's own")) : "");
  }
  function keyPop() {
    const c = card("key"), b = state.start.bounds;
    if (!c) return;
    const notes = [];
    for (let n = b.tonic.min; n <= b.tonic.max; n++) notes.push(n);
    $("keyPop").replaceChildren(
      chipRow("Note", notes.map((n) => ({ value: n, text: b.tonic.names[n] })), c.tonic, (n) => setEdit("tonic", n, "Change the key"), edited("tonic")),
      chipRow("Scale", b.mode.options.map((m) => ({ value: m, text: b.mode.names[m], title: b.mode.glosses?.[m] })), c.mode, (m) => setEdit("mode", m, "Change the scale"), edited("mode")),
      h("p", { class: "hint" }, "A minor mode leans the words darker, as the machine's own would."),
      edited("tonic") || edited("mode") ? h("button", { class: "link small", type: "button", onclick: () => clearEdits(["tonic", "mode"], "The program's key") }, "The program's own") : "");
  }

  // ------------------------------------------------------------------ Page: the words as sung
  function renderPage() {
    const v = state.view, box = $("page");
    if (!v || !box) return;
    keepFocus(() => box.replaceChildren(...v.words.map(pageSection)));
  }
  function pageSection(w) {
    const v = state.view, o = state.optionsByKey[`${w.block}.${w.nth}`];
    const sid = v.composition?.sections?.find((s) => s.index === w.index)?.id || `${w.name}:${w.nth}`;
    const chosen = S.sel && ["section", "line"].includes(S.sel.kind) && S.sel.id === sid;
    const ready = v.listen.ready.includes(v.listen.sections[w.index]);
    const arranged = S.grid && [...S.grid.cells.values()].some((c) => c.section === sid && (c.by === "you" || c.locked));
    const kind = w.mine ? "you" : { "handed down": "lineage", "new this time": "time", "drawn by chance": "chance" }[w.how] || "song";
    const allAuthored = (w.authored || []).length >= w.lines.length;
    const head = h("div", { class: "sec-head" },
      h("button", { class: "rub", type: "button", "data-key": `rub:${sid}`, "aria-pressed": String(chosen && S.sel.kind === "section"),
        title: `Select ${w.label}: its length, who sings, its words`, onclick: () => select({ kind: "section", id: sid }) },
      h("span", { class: `rubric${w.mine ? " hand" : ""}` }, w.label)),
      w.sung ? tag(kind, (w.authored || []).length ? "your lines" : w.mine ? "your words" : w.how) : null,
      o && w.sung && !allAuthored && o.choices.length > 1 ? phraseChooser(w, o) : null,
      o && w.sung && !allAuthored && (o.heads || []).length > 1 ? headChooser(o, w.label) : null,
      h("span", { class: "sectools" }, h("button", { class: `play${ready ? " ready" : ""}`, type: "button", "aria-label": `Hear ${w.label}, sung`,
        title: ready ? "ready to play" : "sung (it will be made first)", onclick: () => { setHow("sung", false); listen("you", w.index); } }, playIcon())));
    let body;
    if (o && w.sung) {
      body = inlineLyrics(w, o);
      [...body.querySelectorAll("p")].forEach((p, j) => {
        p.classList.add("pick");
        if (S.sel?.kind === "line" && S.sel.id === sid && S.sel.line === j) p.classList.add("selected");
        p.title = "Select this line to write your own";
        p.addEventListener("click", (e) => { if (!e.target.closest("select")) select({ kind: "line", id: sid, line: j }); });
      });
    } else body = lines(w.lines);
    const sec = h("div", { class: `sec${w.sung ? "" : " instrumental"}${w.mine ? " mine" : ""}${chosen ? " selected" : ""}`, id: `sec-${w.index}` }, head, body,
      !w.sung && arranged ? h("p", { class: "hint you" }, "arranged by you ✎") : null,
      w.note ? h("p", { class: "sec-note" }, w.note) : null);
    return sec;
  }

  // ------------------------------------------------------------------ Arrange: the grid, from /api/arrangement and /api/sound
  async function loadGrid() {
    const edits = copyEdits(), revision = state.editRevision, serial = ++S.serial;
    try {
      const [arr, sound] = await Promise.all([api("/api/arrangement", { edits }), api("/api/sound", { edits })]);
      if (serial !== S.serial || revision !== state.editRevision) return;
      S.arr = arr; S.sound = sound; S.grid = M.grid(arr, state.view, sound);
      if (S.sel && !stillThere(S.sel)) S.sel = null;
      repaint();
      idle();
      P()?.parts().length || (S.sel?.kind === "player" && P()?.fetch());
    } catch (e) {
      if (serial === S.serial) $("grid").replaceChildren(h("p", { class: "problem" }, `The arrangement couldn't be drawn: ${e.message}`));
    }
  }
  function stillThere(sel) {
    const g = S.grid;
    if (sel.id && ["section", "seam", "line", "cell"].includes(sel.kind) && !sectionAt(sel.id)) return false;
    if (sel.kind === "cell" && !g.tracks.some((t) => t.id === sel.player)) return false;
    if (sel.kind === "player" && !g.tracks.some((t) => t.id === sel.id)) return false;
    return true;
  }
  const row = (...kids) => h("div", { role: "row" }, ...kids);
  function renderGrid() {
    const g = S.grid, box = $("grid");
    if (!g || !box) return;
    keepFocus(() => {
      box.style.gridTemplateColumns = `var(--head, 176px) ${g.sections.map((s) => `minmax(${s.bars < 4 ? 44 : 72}px, ${s.bars}fr)`).join(" ")}`;
      const rows = [
        row(h("div", { class: "head", role: "columnheader" }, h("span", { class: "hint" }, "bar")),
          g.sections.map((s) => h("div", { class: "rule-cell", role: "columnheader", "aria-label": `${s.label}, from bar ${s.startBar}`,
            onpointermove: (e) => { if (e.buttons & 1) setPlayhead(s, e, false); } },
          h("button", { class: "rule", type: "button", "data-key": `rule:${s.id}`, title: `${s.label}: bar ${s.startBar}. Put the playhead here (drag along the ruler to move it).`,
            "aria-label": `Put the playhead at bar ${s.startBar}, ${s.label}`, onclick: (e) => setPlayhead(s, e) }, h("b", {}, String(s.startBar))),
          s.seam?.value ? h("span", { class: "mark", title: `Into ${s.label}: ${M.seamWords(s.seam.value)}` }, "⤴") : null))),
        row(h("div", { class: "head", role: "rowheader" }, h("span", { class: "rubric small" }, "Sections")), g.sections.map(regionCell)),
        ...g.tracks.map((t) => row(trackHead(t), g.sections.map((s) => cellFor(t, s)))),
      ];
      box.setAttribute("aria-rowcount", String(rows.length));
      box.setAttribute("aria-colcount", String(g.sections.length + 1));
      morph(box, [...rows, h("div", { class: "playhead", id: "gridHead", "aria-hidden": "true", hidden: true })]);  // in place: a cell clicked as an answer lands stays the one clicked
      roving();
      if (S.playhead !== null) requestAnimationFrame(() => placeHead(S.playhead));
      problemsUnderGrid();
    });
  }
  function problemsUnderGrid() {
    // only what the masthead doesn't already say (a choice kept from the version before, waiting): said once
    const list = (S.arr?.problems || []).filter((p) => !(state.view?.problems || []).some((q) => q.path === p.path));
    let box = $("arrangeProblems");
    if (!box) { box = h("div", { id: "arrangeProblems" }); $("gridScroll").after(box); }
    box.replaceChildren(...list.map((p) => h("p", { class: "problem" }, `Waiting, not played: ${describePath(p.path)}: ${p.why}. `,
      h("button", { class: "link small", type: "button", onclick: () => clearEdits([p.path]) }, "let it go"))));
  }
  // a region a person moved: one of the fewest whose moves make this order from the program's (for the shape now
  // chosen, the record's "was"), not every region whose index a move shifted
  function moved(s) {
    const before = was("form.order"), now = S.grid.sections.map((x) => x.id), key = `${JSON.stringify(before)}|${now}|${[...S.dragged]}`;
    if (S.movedKey !== key) { S.movedKey = key; S.moved = M.movedIds(before, now, [...S.dragged]); }
    return S.moved.has(s.id);
  }
  function regionCell(s, i) {
    const chosen = S.sel?.kind === "section" && S.sel.id === s.id;
    const mine = moved(s) || Object.values(s.by).includes("you");
    const region = h("button", { class: `region${s.name.startsWith("refrain") ? " refrain" : ""}${chosen ? " selected" : ""}${mine ? " mine" : ""}`,
      type: "button", draggable: "true", "data-key": `region:${s.id}`, "aria-pressed": String(chosen),
      "aria-label": `${s.label}, ${s.bars} bars, ${s.sung ? "sung" : "played"}${mine ? "; yours" : ""}. Enter opens its notes.`,
      title: `${s.label}, ${s.bars} bars${mine ? "; yours" : ""}. Double-click for its notes; drag to move it.`,
      onclick: () => select({ kind: "section", id: s.id }), ondblclick: () => openNotes(s.id),
      ondragstart: (e) => { e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/x-section", s.id); e.currentTarget.classList.add("dragging"); },
      ondragend: (e) => { e.currentTarget.classList.remove("dragging"); document.querySelectorAll(".region.drop").forEach((r) => r.classList.remove("drop")); },
      ondragover: (e) => { if ([...e.dataTransfer.types].includes("text/x-section")) { e.preventDefault(); e.currentTarget.classList.add("drop"); } },
      ondragleave: (e) => e.currentTarget.classList.remove("drop"),
      ondrop: (e) => { const from = e.dataTransfer.getData("text/x-section"); if (!from) return; e.preventDefault(); e.stopPropagation(); moveSection(from, { onto: s.id }); } },
    h("span", { class: "name" }, s.label),
    h("span", { class: "bars" }, `${s.bars} bars${s.sung ? "" : " · instr."}${s.build ? " · build" : ""}`),
    C()?.mini?.(compIndex(s.id)) || null);
  // its length by its right edge: a handle of its own beside the region (not inside it, where a press began the
  // region's drag), 10 px, above and clear of the next section's seam (which starts where this cell ends)
  const edge = s.barOptions.length > 1 ? h("span", { class: "edge", title: `${s.label}: drag for its length (${s.barOptions.join(", ")} bars)`, "aria-hidden": "true",
    "data-edge": s.id, onpointerdown: (e) => edgeDrag(e, s), onmousedown: (e) => { e.preventDefault(); e.stopPropagation(); }, onclick: (e) => e.stopPropagation() }) : null;
    const ready = state.view?.listen?.ready.includes(state.view.listen.sections[s.index]);
    return h("div", { class: "regioncell", role: "gridcell", "data-region": s.id },
      h("button", { class: `play${ready ? " ready" : ""}`, type: "button", "data-key": `hear:${s.id}`, "aria-label": `Hear ${s.label}, ${S.how === "sung" ? "sung" : "the sketch"}`,
        title: `Hear ${s.label}, ${S.how === "sung" ? "sung" : "the sketch"}`, onclick: (e) => { e.stopPropagation(); select({ kind: "section", id: s.id }); play(S.how); } }, playIcon()),
      i > 0 ? h("button", { class: `seam${S.sel?.kind === "seam" && S.sel.id === s.id ? " selected" : ""}${s.seam?.value ? " set" : ""}`, type: "button",
        "data-key": `seam:${s.id}`, "aria-label": `The seam into ${s.label}: ${M.seamWords(s.seam?.value)}`, title: `Into ${s.label}: a riser, a sweep, a roll, a stop…`,
        onclick: (e) => { e.stopPropagation(); select({ kind: "seam", id: s.id }); } }) : null,
      region, edge);
  }
  // the order a move starts from: the latest edit's, when it has these sections, not the one drawn before it (two
  // quick ← Earlier move a section two places, not one)
  function latestOrder() {
    const drawn = S.grid.sections, o = state.edits["form.order"];
    return Array.isArray(o) && o.length === drawn.length && drawn.every((s) => o.includes(s.id)) ? o.map((x) => drawn.find((s) => s.id === x)) : drawn;
  }
  function moveSection(id, where) {  // where: {step: ±1}, or {onto: the section it was dropped on}
    const list = latestOrder(), from = list.findIndex((s) => s.id === id);
    const to = where.step !== undefined ? from + where.step : list.findIndex((s) => s.id === where.onto);
    const r = M.moveOrder(list, from, to);
    if (r.error) { if (from !== to) toast(r.error); return; }
    S.dragged.add(id);
    setEdit("form.order", r.order, `Move ${list[from].label}`);
    say(`${list[from].label} moved to place ${to + 1}`);
  }
  function edgeDrag(e, s) {
    e.preventDefault(); e.stopPropagation();
    const edge = e.currentTarget, region = edge.parentNode.querySelector(".region"), label = region.querySelector(".bars");
    const perBar = region.getBoundingClientRect().width / s.bars, x0 = e.clientX;
    let pick = s.bars;
    edge.setPointerCapture(e.pointerId); edge.classList.add("active");
    const move = (ev) => {
      const want = s.bars + (ev.clientX - x0) / perBar;
      pick = s.barOptions.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a), s.bars);
      label.textContent = pick === s.bars ? `${s.bars} bars` : `${s.bars} → ${pick} bars`;
    };
    const up = () => {
      edge.removeEventListener("pointermove", move); edge.removeEventListener("pointerup", up); edge.removeEventListener("pointercancel", up);
      edge.classList.remove("active");
      if (pick !== s.bars) setBars(s, pick);
    };
    edge.addEventListener("pointermove", move); edge.addEventListener("pointerup", up); edge.addEventListener("pointercancel", up);
  }
  function setBars(s, n) {
    if (n === s.program.bars) releaseEdit(s.paths.bars, `${s.label} as long as the program had it`);
    else setEdit(s.paths.bars, n, `${s.label}: ${n} bars`);
    say(`${s.label}: ${n} bars`);
  }
  function trackHead(t) {
    const chosen = (S.sel?.kind === "player" && S.sel.id === t.id) || (S.sel?.kind === t.kind && ["singer", "choir"].includes(t.kind));
    const target = t.kind === "player" ? { kind: "player", id: t.id } : t.kind === "chords" ? null : { kind: t.kind };
    return h("div", { class: `head track-head ${t.kind}${chosen ? " selected" : ""}`, role: "rowheader" },
      target ? h("button", { class: "name", type: "button", "data-key": `track:${t.id}`, title: t.kind === "player" ? `${t.label} everywhere` : t.label,
        onclick: () => select(target) }, t.label) : h("span", { class: "name" }, t.label),
      t.kind === "player" ? muteSolo(t.id, t.label) : null,
      t.kind === "player" ? routeMark(t.id) : null);
  }
  function muteSolo(name, label) {
    const band = card("band"), players = band ? { ...band.players } : {};
    if (!band) return null;
    if (!players[name]) players[name] = label;
    const bc = { ...band, players };
    const level = band.band?.[name] ?? 1, muted = level <= 0.02, solo = currentSolo()?.player === name;
    return h("span", { class: "ms" },
      h("button", { type: "button", "aria-pressed": String(muted), "aria-label": `${muted ? "Unmute" : "Mute"} ${label}`, title: "Mute (M)", onclick: () => { mutePlayer(bc, name); say(`${label} ${muted ? "back in" : "muted"}`); } }, "M"),
      h("button", { type: "button", "aria-pressed": String(solo), "aria-label": `Solo ${label}`, title: "Solo (S): the singer stays", onclick: () => { soloPlayer(bc, name); say(`${label} ${solo ? "back in the band" : "alone with the singer"}`); } }, "S"));
  }
  function routeMark(name) {
    const ui = P();
    if (!ui) return null;
    const r = ui.own(name);
    if (r === "off" && !Object.prototype.hasOwnProperty.call(ui.set.routes, name)) return h("span", { class: "route" });
    const text = r === "page" ? "here" : r === "off" ? "off" : `MIDI ${r + 1}`;
    return h("span", { class: `route${Number.isInteger(r) ? " midi" : ""}`, title: "Where the sketch sends it: here, over MIDI, or off" }, text);
  }
  function cellFor(t, s) {
    const chosen = S.sel?.kind === "cell" && S.sel.id === s.id && S.sel.player === t.id;
    const common = { type: "button", role: "gridcell", "data-key": `cell:${t.id}:${s.id}`, "data-track": t.id, "data-section": s.id, tabindex: "-1",
      onclick: () => (t.kind === "chords" ? openNotes(s.id) : select({ kind: "cell", id: s.id, player: t.id })) };
    if (t.kind === "singer") {
      const mine = s.by.sung === "you";
      return h("button", { ...common, ondblclick: () => editWords(s.id), class: `cell words${s.wordsMine || mine ? " you" : ""}${chosen ? " selected" : ""}`,
        "aria-label": `The singer in ${s.label}: ${s.sung ? "sings" : "nobody sings"}${mine ? "; yours" : ""}`, title: `${s.sung ? s.first : "played: nobody sings"}${mine ? "; yours" : ""}${canWrite(s.id) ? ". Double-click to edit its words" : ""}` },
      s.sung ? s.first : h("i", {}, "instrumental"));
    }
    if (t.kind === "choir") {
      return h("button", { ...common, class: `cell choir ${s.choir ? "plays" : "out"}${chosen ? " selected" : ""}`,
        "aria-label": `The voices before in ${s.label}: ${s.choir ? "sing" : "out"}; the program's choice` }, h("span", { class: "e" }));
    }
    if (t.kind === "chords") {
      const names = s.chords.filter((c, i, all) => i === 0 || c !== all[i - 1]);
      return h("button", { ...common, class: `cell chord-cell${s.chordsMine ? " you" : ""}`, "aria-label": `Chords in ${s.label}: ${names.join(", ") || "none"}${s.chordsMine ? "; some yours" : ""}. Opens its notes.`,
        title: `${s.label}: ${names.join(" ")}` }, names.slice(0, 4).join(" · ") + (names.length > 4 ? " …" : ""));
    }
    const cell = S.grid.cells.get(`${t.id}|${s.id}`), l = M.look(cell);
    const cls = `cell ${l.level}${l.whose === "you" ? " you" : l.locked ? " locked" : l.whose === "before" ? " before" : ""}${l.chance ? " chance" : ""}${chosen ? " selected" : ""}`;
    // no marks on a cell (a glyph at this size gets covered): whose it is is in its drawing, and in its words
    return h("button", { ...common, class: cls, "aria-label": M.cellLabel(t, s, cell), title: M.cellLabel(t, s, cell) }, h("span", { class: "e" }));
  }
  function roving() {  // one cell of the grid in the tab order: the selected one, else the first
    const cells = [...document.querySelectorAll("#grid button[role=gridcell]")];
    const on = cells.find((c) => c.classList.contains("selected")) || cells[0];
    if (on) on.tabIndex = 0;
  }
  function setPlayhead(s, e, restart = true) {
    const r = (e.currentTarget.closest?.(".rule-cell") || e.currentTarget).getBoundingClientRect();
    const bars = Math.floor(Math.max(0, e.clientX - r.left) / r.width * s.bars);
    S.playhead = s.startBeat + bars * S.grid.perBar;
    placeHead(S.playhead);
    if (restart && C()?.playing?.() && !S.sel) { play("sketch"); play("sketch"); }  // the song again from here
    idle();
  }
  function stepCell(axis, step, from) {  // the arrow keys through the grid: from the focused cell, else the selection
    const g = S.grid;
    if (!g) return false;
    const focused = from?.closest?.("#grid [role=gridcell][data-track]");
    const sel = focused && focused.dataset.track !== "chords" ? { kind: "cell", id: focused.dataset.section, player: focused.dataset.track } : S.sel;
    const tracks = g.tracks.filter((t) => t.kind !== "chords");
    if (sel?.kind === "cell") {
      let t = tracks.findIndex((x) => x.id === sel.player), s = g.sections.findIndex((x) => x.id === sel.id);
      if (axis === "track") t = Math.max(0, Math.min(tracks.length - 1, t + step)); else s = Math.max(0, Math.min(g.sections.length - 1, s + step));
      S.keyed = false;
      select({ kind: "cell", id: g.sections[s].id, player: tracks[t].id });
      document.querySelector(`[data-key="cell:${CSS.escape(tracks[t].id)}:${CSS.escape(g.sections[s].id)}"]`)?.focus();
      return true;
    }
    if (axis === "section" && ["section", "seam", "line"].includes(sel?.kind)) {
      const next = M.neighbour(g.sections, sel.id, step);
      select({ kind: "section", id: next.id }, { keyboard: false });
      (document.querySelector(`[data-key="region:${CSS.escape(next.id)}"]`) || document.querySelector(`[data-key="rub:${CSS.escape(next.id)}"]`))?.focus();
      return true;
    }
    if (axis === "track" && ["player", "singer", "choir"].includes(sel?.kind)) {
      const heads = g.tracks.filter((t) => t.kind !== "chords");
      const i = heads.findIndex((t) => (sel.kind === "player" ? t.id === sel.id : t.kind === sel.kind));
      const t = heads[Math.max(0, Math.min(heads.length - 1, i + step))];
      select(t.kind === "player" ? { kind: "player", id: t.id } : { kind: t.kind });
      document.querySelector(`[data-key="track:${CSS.escape(t.id)}"]`)?.focus();
      return true;
    }
    return false;
  }

  // ------------------------------------------------------------------ Mix: a strip for each player, the voice, the room
  function renderMix() {
    const box = $("mix"), band = card("band"), mix = card("mix");
    if (!box || !S.sound || !band) return;
    keepFocus(() => {
      const strips = S.sound.players.filter((p) => p.playing !== false).map((sp) => strip(sp, band));
      morph(box, [...strips, voiceStrip(mix), roomStrip(mix), masterStrip()]);  // in place: a fader being moved stays put
    });
  }
  const PUMPED = /bass|pad|drone|synth|arp/;
  function strip(sp, band) {
    const name = sp.player, label = sp.name || name, gain = sp.gain?.value ?? band.band?.[name] ?? 1;
    const yours = !!sp.gain?.yours || edited(`band.${name}`), program = was(`band.${name}`);
    const chosen = S.sel?.kind === "player" && S.sel.id === name;
    const out = h("div", { class: `val${yours ? " you" : ""}` }, pct(gain));
    const input = h("input", { type: "range", min: 0, max: 2, step: 0.01, value: gain, "data-key": `fader:${name}`, "aria-label": `${label}: level`, "aria-valuetext": pct(gain),
      oninput: (e) => { e.target.closest(".strip").querySelector(".val").textContent = pct(Number(e.target.value)); e.target.setAttribute("aria-valuetext", pct(Number(e.target.value))); },
      onchange: (e) => setEdit(`band.${name}`, Number(e.target.value), `${label}: level`) });
    const fader = h("div", { class: `fader${yours ? " you" : ""}` }, input,
      yours && typeof program === "number" ? tickAt(program) : null);
    const pan = sp.pan, panYours = !!pan?.yours;
    const pump = sp.sidechain;
    return h("div", { class: `strip${chosen ? " selected" : ""}${gain <= 0.02 ? " muted" : ""}` },
      h("button", { class: "nm", type: "button", "data-key": `strip:${name}`, onclick: () => select({ kind: "player", id: name }), title: `${label}: open it in the column` }, label),
      muteSolo(name, label),
      fader, out,
      pan ? h("label", { class: `knob${panYours ? " you" : ""}` }, h("span", {}, `pan ${panWords(pan.value)}`),
        h("input", { type: "range", min: -1, max: 1, step: 0.05, value: pan.value, class: panYours ? "you" : null, "data-key": `pan:${name}`, "aria-label": `${label}: pan`,
          "aria-valuetext": panWords(pan.value),
          oninput: (e) => { const x = Number(e.target.value); e.target.previousSibling.textContent = `pan ${panWords(x)}`; e.target.setAttribute("aria-valuetext", panWords(x)); },
          onchange: (e) => setEdit(pan.path, Number(e.target.value), `${label}: pan`) })) : null,
      pump && PUMPED.test(name) && !pump.is_key ? h("label", { class: `knob${pump.yours ? " you" : ""}` }, h("span", {}, "pump"),
        pumpSelect(pump, `${label}: pump`)) : null,
      sp.patch || sp.kit ? h("button", { class: "patch", type: "button", onclick: () => select({ kind: "player", id: name }), title: "Its sound: open it in the column" },
        (sp.patch || sp.kit).value) : null,
      h("div", { class: "why" }, yours && typeof program === "number" ? `was ${pct(program)}` : "the program's"));
  }
  function tickAt(program) {  // the program's level, a faint mark beside a fader a person moved
    const tick = h("span", { class: "tick", title: `the program's: ${pct(program)}` });
    tick.style.top = `${(1 - Math.min(2, program) / 2) * 150}px`;
    return tick;
  }
  // a pump's value: the server's spelled out {depth, release, key, sections}, or an edit's (a preset's name, or
  // {preset, sections}); what it is now is the latest edit's, so a quick second choice builds on the first
  const pumpNow = (pump) => (Object.prototype.hasOwnProperty.call(state.edits, pump.path) ? state.edits[pump.path] : pump.value) || null;
  function presetOf(value) {
    if (!value) return "none";
    if (typeof value === "string") return value;
    if (value.preset && value.depth === undefined) return value.preset;
    const hit = Object.entries((S.sound?.players?.[0]?.sidechain?.presets) || {}).find(([, p]) => p.depth === value.depth && p.release === value.release && p.key === value.key);
    return hit ? hit[0] : "yours";
  }
  function pumpWith(pump, preset, sections) {  // the edit for a preset (or the person's own) over some sections
    if (preset === "none") return null;
    const v = pumpNow(pump), where = sections?.length ? { sections } : {};
    if (preset !== "yours") return where.sections ? { preset, ...where } : preset;
    return { depth: v.depth, release: v.release, key: v.key, ...where };
  }
  function pumpSelect(pump, label) {
    const now = presetOf(pumpNow(pump));
    const s = h("select", { "aria-label": label, "data-key": `pump:${label}` },
      ["none", ...Object.keys(pump.presets || {})].map((k) => h("option", { value: k }, k === "none" ? "none" : k)),
      now === "yours" ? h("option", { value: "yours" }, "yours") : null);
    s.value = now;
    s.addEventListener("change", (e) => { const to = e.target.value;  // (not `s`: morph may keep the one on the page)
      if (to === "none") releaseEdit(pump.path, `${label}: none`);
      else if (to !== "yours") setEdit(pump.path, pumpWith(pump, to, pumpNow(pump)?.sections), `${label}: ${to}`); });
    return s;
  }
  // where it pumps: everywhere (wherever the kick plays), or the sections chosen (a drop, not the breakdown);
  // always drawn, so choosing a pump adds no row under the pointer
  function pumpWhere(pump, label) {
    const v = pumpNow(pump), on = presetOf(v) !== "none", chosen = new Set(v?.sections || []);
    const pick = (id) => {
      const now = pumpNow(pump), has = new Set(now?.sections || []);
      if (id === null) has.clear(); else if (has.has(id)) has.delete(id); else has.add(id);
      const list = S.grid.sections.map((x) => x.id).filter((x) => has.has(x));
      setEdit(pump.path, pumpWith(pump, presetOf(now), list), `${label}: ${list.length ? `in ${list.length} section${list.length === 1 ? "" : "s"}` : "everywhere"}`);
    };
    const chip = (id, text) => {
      const pressed = id === null ? !chosen.size : chosen.has(id);
      return h("button", { class: `chip${pressed && on ? " on" : ""}${pressed && on && pump.yours ? " you" : ""}`, type: "button", "aria-pressed": String(pressed && on),
        disabled: !on, title: on ? null : "Choose a pump first", onclick: () => pick(id) }, text);
    };
    return h("div", { class: "row" }, h("span", { class: "label" }, "Where"),
      h("span", { class: "chips", role: "group", "aria-label": `${label}: where` }, chip(null, "everywhere"), (S.grid?.sections || []).map((x) => chip(x.id, x.label))));
  }
  const panWords = (x) => (Math.abs(x) < 0.05 ? "middle" : `${Math.round(Math.abs(x) * 100)}% ${x < 0 ? "left" : "right"}`);
  function busSlider(label, path, value, bounds, show, key) {
    const out = h("span", {}, show(value));
    return h("label", {}, h("span", {}, label), out,
      h("input", { type: "range", min: bounds.min, max: bounds.max, step: bounds.step || 0.01, value, class: edited(path) ? "you" : null, "data-key": key, "aria-label": label,
        oninput: (e) => { e.target.previousSibling.textContent = show(Number(e.target.value)); }, onchange: (e) => setEdit(path, Number(e.target.value), label) }));
  }
  function voiceStrip(mix) {
    const b = state.start.bounds, m = mix.mix;
    return h("div", { class: `strip bus${S.sel?.kind === "singer" ? " selected" : ""}` },
      h("button", { class: "nm", type: "button", onclick: () => select({ kind: "singer" }) }, "Voice"),
      h("div", { class: "sliders" },
        busSlider("over the band", "mix.forward", m.forward, b["mix.forward"], (x) => `${Number(x).toFixed(1)} dB`, "bus:forward"),
        busSlider("how close", "mix.intimacy", m.intimacy, b["mix.intimacy"], pct, "bus:intimacy")),
      h("div", { class: "why" }, edited("mix.forward") || edited("mix.intimacy") ? "yours ✎" : "the machine's own"));
  }
  function roomStrip(mix) {
    const b = state.start.bounds, m = mix.mix;
    return h("div", { class: `strip bus${S.sel?.kind === "room" ? " selected" : ""}` },
      h("button", { class: "nm", type: "button", onclick: () => select({ kind: "room" }) }, "Room"),
      h("div", { class: "sliders" },
        busSlider("how much", "mix.space", m.space, b["mix.space"], pct, "bus:space"),
        busSlider("how wide", "mix.width", m.width, b["mix.width"], pct, "bus:width"),
        b["mix.rt60"] ? busSlider("rings for", "mix.rt60", m.rt60, b["mix.rt60"], (x) => `${Number(x).toFixed(1)} s`, "bus:rt60") : null),
      h("div", { class: "why" }, mix.value));
  }
  function masterStrip() {
    const loud = card("field.loudness");
    return h("div", { class: "strip bus" }, h("div", { class: "nm" }, "Master"),
      h("div", { class: "val" }, loud ? `${loud.value} LUFS` : ""),
      h("div", { class: "why" }, "the song's own loudness, as every version has it; not a control"));
  }

  // ------------------------------------------------------------------ the inspector: one shape in every state
  const STATE_ABOUT = {
    song: "This version in five doors: its style, its singer, its band, its shape and its room. Select anything on the page to see what it is, why the program chose it, and change it.",
    section: "A part of the song. Its length, who sings, how hard everyone plays and its moment are yours to choose; so are its words. The program's own gives back everything you set here.",
    player: "One player, everywhere it plays: its level, its sound, where it sits, how it pumps, and where the sketch sends it.",
    cell: "One player in one section: out, soft, plays or hard, and what it plays there. What chance drew is drawn dashed; Lock keeps it through a new performance.",
    seam: "The moment one section turns into the next: a riser, a sweep, a snare roll or a stop over the bars before, an impact on the downbeat, a downlifter after it.",
    chord: "A chord under the tune. The band, the voices before and the backing voices follow it; the tune stays. A sung note that isn't in the chord is shown, not forbidden.",
    note: "A note of the tune: its pitch, where it starts and how long. A phrase keeps its syllables and its ending's place in the scale unless you free it.",
    line: "A line of the words. Write your own if it fits the notes: one syllable a note, longer words split with hyphens (car-ry).",
    singer: "The singer is your machine's own voice, the same in every song it sings. What you can give it is a way of singing, and where it sits against the band.",
    choir: "Voices from the versions before this one, one more for every version, up to six; they sing where the song has a choir.",
    room: "The room the song is sung in: how much of it you hear, how wide it is, how long it rings and how soon it answers.",
    style: "A style brings its own band, its pace and its feel; a version moves one style at a time, so its children drift back toward your machine's.",
    band: "How the band plays everywhere: its pattern, who leads where nobody sings, how busy and how bright. Each player's own is in Arrange and Mix.",
    shape: "The parts of the song and how many verses. Their order is the regions in Arrange: drag them there.",
  };
  function shell({ kind, rubric, set, mine, body, why, release, hear, problems, extra }) {
    const box = $("inspector");
    box.classList.toggle("empty", kind === "song");
    box.classList.toggle("shown", kind === "song" && !!S.songShown);  // on a phone, the song's summary asked for
    box.classList.toggle("tall", S.tall);
    $("songBtn").setAttribute("aria-expanded", String(kind === "song" && !!S.songShown));
    const whyOpen = !!S.why[kind];
    morph(box, [  // in place, not redrawn whole: what the pointer is on stays where it is (studio.js morph)
      h("button", { class: "handle", type: "button", "aria-label": S.tall ? "Lower the column" : "Raise the column", onclick: () => { S.tall = !S.tall; box.classList.toggle("tall", S.tall); } }),
      h("div", { class: "top" }, h("span", { class: "rubric", id: "inspectorTitle", tabindex: "-1" }, rubric, mine ? h("span", { class: "you", "aria-label": ", yours" }, " ✎") : null),
        h("button", { class: "what", type: "button", "aria-expanded": String(S.about), "aria-label": "What is this?", title: "What is this?", onclick: () => { S.about = !S.about; renderInspector(); } }, "?"),
        kind === "song" && !S.songShown ? null : h("button", { class: "close", type: "button", "aria-label": "Close (Esc)", title: "Close (Esc)",
          onclick: () => { S.songShown = false; select(null); } }, "✕")),
      S.about ? h("p", { class: "about" }, STATE_ABOUT[kind] || "") : null,
      set ? h("p", { class: `set${mine ? " you" : ""}` }, set) : null,
      (problems || []).map((p) => h("p", { class: "problem" }, typeof p === "string" ? p : `Couldn't keep ${describePath(p.path)}: ${p.why}.`)),
      body || null,
      why?.length ? reasonsFold(kind, why, whyOpen) : null,
      hear || release || extra ? h("div", { class: "foot" },
        hear ? h("button", { class: "btn", type: "button", onclick: hear }, "▶ Hear it") : null, extra || null,
        release ? h("button", { class: "link small release", type: "button", disabled: !!release.disabled, title: "Give it back to the program: your choice released",
          onclick: release.action }, release.label || "The program's own") : null) : null]);
  }
  function reasonsFold(kind, why, open) {
    const list = why.map((r) => (Array.isArray(r) ? { kind: r[0], text: r[1] } : r)).filter((r) => r.text);
    list.sort((a, b) => (b.kind === "you") - (a.kind === "you"));
    const d = h("details", {}, h("summary", {}, "Why the program chose this"),
      list.map((r) => h("div", { class: "reason" }, tag(r.kind === "program" ? "song" : r.kind), h("span", {}, r.text))));
    d.open = open;
    d.addEventListener("toggle", (e) => { S.why[kind] = e.target.open; });
    return d;
  }
  function chipRow(label, options, current, pick, yours = false, extra = {}) {
    return h("div", { class: "row" }, label ? h("span", { class: "label" }, label) : null,
      h("span", { class: "chips", role: "group", "aria-label": label || extra.aria || "" }, options.map((o) => {
        const on = String(o.value) === String(current);
        return h("button", { class: `chip${on ? " on" : ""}${on && yours ? " you" : ""}${on && extra.drawn ? " drawn" : ""}`, type: "button", "aria-pressed": String(on),
          disabled: !!o.disabled, title: o.title || null, onclick: (e) => {
            // what's pressed now is the row's, not the answer drawn before (a second quick click is judged by the first),
            // and it shows at once: the answer, when it comes, draws the same in place
            const b = e.currentTarget;
            if (b.getAttribute("aria-pressed") === "true") return;
            for (const x of b.parentNode.children) {
              const me = x === b;
              x.setAttribute("aria-pressed", String(me)); x.classList.toggle("on", me); x.classList.toggle("you", me); x.classList.remove("drawn");
            }
            pick(o.value);
          } }, o.text);
      })));
  }
  // a slider in the inspector: its value in the ink that set it; `log` for a cutoff (moved on octaves), `commit` for
  // a value that is part of a larger one (a drum's tune inside its piece)
  function field(label, path, value, bounds, show, ends, { log = false, commit = null, yours = edited(path) } = {}) {
    const to = (x) => (log ? Math.log2(x) : x), from = (x) => (log ? Math.round(2 ** x) : x);
    const out = h("output", { class: yours ? "you" : null }, show(value));
    return h("div", { class: "field" }, h("span", { class: "label" }, h("span", {}, label), out),
      h("input", { type: "range", min: to(bounds.min), max: to(bounds.max), step: log ? 0.01 : bounds.step || 0.01, value: to(value), class: yours ? "you" : null,
        id: `f-${path}`, "aria-label": label, "aria-valuetext": show(value),
        oninput: (e) => { const x = from(Number(e.target.value)); e.target.closest(".field").querySelector("output").textContent = show(x); e.target.setAttribute("aria-valuetext", show(x)); },
        onchange: (e) => (commit || ((x) => setEdit(path, x, label)))(from(Number(e.target.value))) }),
      ends ? h("div", { class: "ends" }, h("span", {}, ends[0]), h("span", {}, ends[1])) : null);
  }
  function releasing(paths, label) {  // "The program's own": each path the person set, released in one step
    const mine = paths.filter((p) => Object.prototype.hasOwnProperty.call(state.edits, p));
    return { disabled: !mine.length, action: () => clearEdits(mine, label) };
  }
  const hearHow = () => play(S.how);

  function renderInspector() {
    if (!state.view || !$("inspector")) return;
    keepFocus(() => {
      const kind = S.sel?.kind || "song";
      const draw = { section: sectionState, player: playerState, cell: cellState, seam: seamState, chord: composerState, note: composerState,
        line: lineState, singer: singerState, choir: choirState, room: roomState, style: styleState, band: bandState, shape: shapeState }[kind] || songState;
      if (!draw(S.sel)) { S.sel = null; songState(); }
    });
  }

  function songState() {
    const v = state.view, style = card("style"), singer = card("singer"), band = card("band"), shape = card("shape"), mix = card("mix");
    const yoursCells = S.grid ? [...S.grid.cells.values()].filter((c) => c.by === "you" || c.locked) : [];
    const who = [...new Set(yoursCells.map((c) => S.grid.tracks.find((t) => t.id === c.player)?.label))];
    const off = shape?.parts ? state.start.optional.filter((p) => !shape.parts[p]).map((p) => state.start.parts[p]) : [];
    const door = (rubric, value, detail, sel, mine) => h("button", { class: "door", type: "button", onclick: () => select(sel) },
      h("span", { class: "rubric" }, rubric), h("span", { class: `v${mine ? " you" : ""}` }, value, mine ? " ✎" : ""), detail ? h("span", { class: `d${mine ? " you" : ""}` }, detail) : null);
    const line = (c, label, value, extra = null) => {
      if (!c) return null;
      const more = h("div", { class: "hint", hidden: true }, [c.detail, ...(c.lines || []), ...(c.reasons || []).map((r) => r.text)].filter(Boolean).join(" · "), extra);
      return h("div", {}, h("div", { class: "lineitem" }, h("span", {}, label), h("b", {}, value || c.value),
        h("button", { class: "what", type: "button", "aria-label": `About ${label}`, "aria-expanded": "false",
          onclick: (e) => { const box = e.currentTarget.parentNode.nextSibling; box.hidden = !box.hidden; e.currentTarget.setAttribute("aria-expanded", String(!box.hidden)); } }, "?")), more);
    };
    shell({ kind: "song", rubric: "This version",
      body: h("div", {},
        h("div", { class: "doors" },
          style ? door("The style", style.value, style.detail, { kind: "style" }, style.mine) : null,
          singer ? door("The singer", singer.value, singer.detail, { kind: "singer" }, singer.mine) : null,
          band ? door("The band", band.value, who.length ? `${who.join(", ")}: yours in ${yoursCells.length} place${yoursCells.length === 1 ? "" : "s"} ✎` : band.detail, { kind: "band" }, band.mine || yoursCells.length > 0) : null,
          shape ? door("The shape", shape.value, off.length ? `add: ${off.slice(0, 4).join(" · ")}` : null, { kind: "shape" }, shape.mine || !!v.edits["form.order"]) : null,
          mix ? door("The room", mix.value, mix.detail, { kind: "room" }, mix.mine) : null),
        h("h4", {}, "And"),
        line(card("variants"), "The melody", null, (card("variants")?.variants || []).length ? h("div", { class: "row" }, card("variants").variants.map((x) =>
          h("label", { class: "check" }, h("input", { type: "checkbox", checked: !!x.value, onchange: (e) => setEdit(x.path, e.target.checked, x.label) }), ` ${x.label}`))) : null),
        line(card("choir"), "Voices before"),
        line(card("words"), "The words", card("words")?.detail, h("div", { class: "row" }, h("button", { class: "btn quiet", type: "button", onclick: keepWords,
          title: "Hold every word as it is now, so that time and chance change only the music" }, "Keep these words"))),
        line(card("field.loudness"), "Loudness", card("field.loudness") ? `${card("field.loudness").value} LUFS` : ""), line(card("machine"), "Your machine"),
        h("p", { class: "hint later" }, "Every value on this page has a reason. Select a section, a player, a cell, a chord, a note or a line to see it and change it.")) });
    return true;
  }

  function sectionState(sel) {
    const s = sectionAt(sel.id), w = wordsOf(s);
    if (!s) return false;
    // its words' choosers: while this version's are on their way, the last ones, drawn and not to be used, so the
    // rows under them don't jump out and back as an answer lands
    const key = w ? `${w.block}.${w.nth}` : null, fresh = key ? state.optionsByKey[key] : null;
    if (fresh) S.lastOptions[key] = fresh;
    const o = fresh || (key && !state.optionsFailed ? S.lastOptions[key] : null) || null, stale = !!o && !fresh;
    const cells = [...S.grid.cells.values()].filter((c) => c.section === s.id && c.plays !== false);
    const levels = new Set(cells.map((c) => c.value?.level));
    const everyone = levels.size === 1 ? [...levels][0] : null;
    const list = S.grid.sections, i = list.findIndex((x) => x.id === s.id);
    const mine = Object.values(s.by).includes("you") || !!w?.mine || moved(s);
    const phrases = state.view.composition?.sections?.find((x) => x.id === s.id)?.phrases || [];
    const writable = phrases.some((p) => p.lyric_path);
    const allAuthored = w && (w.authored || []).length >= w.lines.length;
    const choosers = o && w.sung && !allAuthored ? [o.choices.length ? phraseChooser(w, o) : null, (o.heads || []).length > 1 ? headChooser(o, w.label) : null].filter(Boolean) : [];
    const oneChoice = o && o.choices.filter((c) => c.allowed).length <= 1 && (o.heads || []).filter((c) => c.allowed).length <= 1;
    const rules = o && w.sung && !allAuthored ? chooser(w, o) : null;
    if (rules) rules.querySelector("summary").textContent = "Refused here, and why";
    if (stale) for (const c of choosers) c.querySelectorAll("select").forEach((x) => { x.disabled = true; x.setAttribute("disabled", ""); });
    const options = s.options.map((opt) => optionRow(opt));
    const release = () => {
      const next = copyEdits();
      for (const p of Object.keys(next)) if (p.startsWith(`arrange.${s.id}.`)) delete next[p];
      if (moved(s)) next["form.order"] = null;  // its place: the order is one choice, given back whole
      if (w) releaseWords(w, next);
      commitEdits(next, `${s.label} as the program had it`);
    };
    const anyMine = Object.keys(state.edits).some((p) => p.startsWith(`arrange.${s.id}.`)) || !!w?.mine || moved(s);
    shell({ kind: "section", rubric: s.label, mine,
      set: `${s.bars} bars, ${s.sung ? `sung: “${s.first}”` : w?.sung ? `played; its words wait, unsung: “${String(w.lines[0] || "").replace(/\*/g, "")}”` : `played${w ? `: ${String(w.lines[0] || "").replace(/\*/g, "")}` : ""}`}${w?.id && w.block === "verse" ? ` (the verse “${w.id}”)` : ""}`,
      problems: s.problems,
      body: h("div", {},
        h("div", { class: "row edit-it" },  // the ways into the section's own material, first
          writable ? h("button", { class: "btn", type: "button", onclick: () => editWords(s.id), title: "Its words on the Page, a line ready to write in the column" }, "Edit its words") : null,
          h("button", { class: "btn", type: "button", onclick: () => openNotes(s.id, true), title: "Its tune and chords, under the grid (Enter, or double-click the section)" }, "Edit its notes")),
        // every length drawn, the ones this section can't have disabled: a drop's shorter lengths don't push the rows
        chipRow("Length", [...new Set([2, 4, 8, 16, ...s.barOptions])].sort((a, b) => a - b).map((n) => ({ value: n, text: `${n} bars`,
          disabled: !s.barOptions.includes(n), title: s.barOptions.includes(n) ? null : s.sung ? "A sung section is as long as its lines; played, it can be shorter" : "Not this section's" })),
          s.bars, (n) => setBars(s, n), s.by.bars === "you"),
        s.canPlay ? chipRow("Who sings", [{ value: true, text: "the singer" }, { value: false, text: "nobody: played" }], s.sung,
          (v) => (v ? releaseEdit(s.paths.sung, `${s.label} sung again`) : setEdit(s.paths.sung, false, `${s.label} played, not sung`)), s.by.sung === "you") : null,
        chipRow("Everyone", [{ value: "soft", text: "soft" }, { value: "plays", text: "plays" }, { value: "hard", text: "hard" }], everyone,
          (lv) => { setEdits(M.levelPatch(cells, lv), `Everyone in ${s.label}: ${lv}`); say(`${s.label}: everyone plays ${lv === "plays" ? "as the style has it" : lv}`); },
          cells.some((c) => c.by === "you")),
        chipRow("Moment", [{ value: false, text: "none" }, { value: true, text: "a build", disabled: i === list.length - 1, title: i === list.length - 1 ? "Nothing comes after the last section to build toward" : "The players come in one after another and rise toward the next section" }],
          s.build, (v) => (v ? setEdit(s.paths.build, true, `A build in ${s.label}`) : releaseEdit(s.paths.build, `No build in ${s.label}`)), s.by.build === "you"),
        s.seam && i > 0 ? h("div", { class: "row" }, h("span", { class: "label" }, "Into it"),  // the seam's twin, a bigger target
          h("button", { class: `btn quiet${s.seam.value ? " you" : ""}`, type: "button", title: M.seamWords(s.seam.value), onclick: () => select({ kind: "seam", id: s.id }) },
            s.seam.value ? M.seamLengths(s.seam.value).map((x) => x.kind).concat(s.seam.value.impact ? ["impact"] : []).map((k) => ({ down: "downlifter" })[k] || k).join(" · ") : "a riser, a sweep, a roll…")) : null,
        h("div", { class: "row" },
          h("button", { class: "btn quiet", type: "button", disabled: i === 0, onclick: () => moveSection(s.id, { step: -1 }), title: "Earlier (⌘/Ctrl ←)" }, "← Earlier"),
          h("button", { class: "btn quiet", type: "button", disabled: i === list.length - 1, onclick: () => moveSection(s.id, { step: 1 }), title: "Later (⌘/Ctrl →)" }, "Later →"),
          h("button", { class: "btn quiet", type: "button", hidden: S.open !== s.id, onclick: closeNotes }, "Close the notes")),
        // what the style and the words offer here last: rows that come and go with an answer push only what's below
        options,
        choosers.length && !oneChoice ? h("div", { class: "row" }, choosers) : null,
        choosers.length && oneChoice ? h("details", {}, h("summary", {}, "more"), h("div", { class: "row" }, choosers)) : null,
        rules),
      why: [
        w?.sung ? { kind: w.mine ? "you" : { "handed down": "lineage", "new this time": "time", "drawn by chance": "chance" }[w.how] || "song", text: w.mine ? "these words are yours" : `the words: ${w.how}${(w.tags || []).length ? ` (${w.tags.join(", ")})` : ""}` } : null,
        s.by.bars === "you" ? { kind: "you", text: `${s.bars} bars; the program had ${s.program.bars}` } : null,
        s.by.sung === "you" ? { kind: "you", text: "played, not sung: a drop" } : null,
        s.by.build === "you" ? { kind: "you", text: "a build toward the next section" } : null,
        moved(s) ? { kind: "you", text: "moved here by you" } : null,
        ...s.options.map((opt) => ({ kind: opt.by === "you" ? "you" : opt.by === "chance" ? "chance" : opt.by === "song" ? "song" : "rule", text: opt.text })),
        { kind: "rule", text: `the band's weight here: ${Math.round((S.arr.sections.find((x) => x.id === s.id)?.energy || 0) * 100)}% of its fullest, the program's arc for a ${s.role}` },
      ].filter(Boolean),
      hear: hearHow,
      release: { disabled: !anyMine, action: release } });
    return true;
  }
  // a style's option that lives in this section (the stripped start, the band joining line by line...): choosable,
  // lockable (the same value, kept), said with where it came from
  function optionRow(opt) {
    const yours = opt.by === "you", locked = yours && was(opt.path) === opt.value && state.view.marks?.[opt.path]?.locked;
    const bool = typeof opt.value === "boolean";
    const controls = bool
      ? chipRow(null, [{ value: true, text: "yes" }, { value: false, text: "no" }], opt.value, (v) => setEdit(opt.path, v, opt.text), yours, { drawn: opt.by === "chance", aria: opt.text })
      : typeof opt.value === "number" && opt.value > 0 ? h("button", { class: "btn quiet", type: "button", onclick: () => setEdit(opt.path, 0, `Not: ${opt.text}`) }, "none here") : null;
    return h("div", { class: "row" }, h("span", { class: `label${yours ? " you" : ""}` }, opt.text, opt.by === "chance" && !yours ? h("span", { class: "hint" }, " · drawn by chance") : null),
      controls,
      yours ? h("button", { class: "link small", type: "button", onclick: () => releaseEdit(opt.path, `${opt.text}: the program's`) }, locked ? "unlock" : "the program's")
        : h("button", { class: "btn quiet", type: "button", title: "Keep it as it is through a new performance", onclick: () => { setEdits(M.optionLock(opt), `Lock: ${opt.text}`); say(`Locked: ${opt.text}`); } }, lockIcon(), " Lock"));
  }

  function cellState(sel) {
    const s = sectionAt(sel.id), t = S.grid.tracks.find((x) => x.id === sel.player);
    if (!s || !t) return false;
    if (t.kind === "singer") {
      const mine = s.by.sung === "you";
      shell({ kind: "cell", rubric: `The singer · ${s.label}`, mine, set: s.sung ? `sings: “${s.first}”` : "nobody sings here: played",
        body: s.canPlay ? chipRow("Here", [{ value: true, text: "sings" }, { value: false, text: "nobody: an instrumental" }], s.sung,
          (v) => (v ? releaseEdit(s.paths.sung, `${s.label} sung again`) : setEdit(s.paths.sung, false, `${s.label} played, not sung`)), mine)
          : h("p", { class: "hint" }, "Nobody sings here: this part of the song has no words."),
        why: [mine ? ["you", "played, not sung: the band keeps its weight and the lead takes the tune (a drop)"] : ["song", s.sung ? "sung, as the song has it" : "a part of the song without words"]],
        hear: hearHow, release: mine ? { action: () => releaseEdit(s.paths.sung, `${s.label} sung again`) } : null });
      return true;
    }
    if (t.kind === "choir") return choirState();
    const cell = S.grid.cells.get(`${t.id}|${s.id}`), l = M.look(cell);
    if (!cell) return false;
    const v = cell.value || {}, mine = l.whose === "you" || l.locked;
    const lineChoices = s.lines.map((_, j) => ({ value: j, text: j === 0 ? "from the start" : `line ${j + 1}` }));
    shell({ kind: "cell", rubric: `${t.label} · ${s.label}`, mine,
      set: `${l.level === "out" ? "out" : `${l.level}${v.pattern_label && v.pattern_label !== "out" ? `, ${v.pattern_label}` : ""}`}${v.from ? `, from line ${v.from + 1}` : ""}; ${M.whoseWords(l)}`,
      problems: cell.problems,
      body: h("div", {},
        chipRow("Here", M.LEVELS.map((x) => ({ value: x, text: x })), l.level, (lv) => {
          if (lv === cell.program?.level && edited(cell.paths.level)) releaseEdit(cell.paths.level, M.saidCell(t, s, lv)); else setEdit(cell.paths.level, lv, M.saidCell(t, s, lv));
          say(M.saidCell(t, s, lv)); },
          cell.by === "you" && !l.locked, { drawn: l.chance }),
        // the rows under Here are drawn whether it plays or not (out: not to choose), so choosing out, or back in,
        // moves nothing under the pointer
        t.patterns.length ? chipRow("Plays", t.patterns.map((p) => ({ value: p.id, text: p.label, disabled: l.level === "out" })), l.level === "out" ? null : v.pattern,
          (p) => setEdit(cell.paths.pattern, p, `${t.label} in ${s.label}: ${t.patterns.find((x) => x.id === p)?.label}`), edited(cell.paths.pattern)) : null,
        lineChoices.length > 1 ? chipRow("Comes in", lineChoices.map((c) => ({ ...c, disabled: l.level === "out" })), l.level === "out" ? null : v.from || 0,
          (j) => (j === (cell.program?.from || 0) ? releaseEdit(cell.paths.from) : setEdit(cell.paths.from, j, `${t.label} comes in at line ${j + 1} of ${s.label}`)), edited(cell.paths.from), { drawn: l.chance }) : null,
        t.fills ? chipRow("A fill into the next", [{ value: true, text: "yes", disabled: l.level === "out" }, { value: false, text: "no", disabled: l.level === "out" }], l.level === "out" ? null : !!v.fill,
          (f) => setEdit(cell.paths.fill, f, `${t.label}: ${f ? "a fill" : "no fill"} at the end of ${s.label}`), edited(cell.paths.fill)) : null,
        h("div", { class: "row" },
          l.locked ? h("button", { class: "btn quiet", type: "button", onclick: () => clearEdits(Object.keys(M.releasePatch(cell)), `Unlock ${t.label} in ${s.label}`) }, lockIcon(), " Unlock")
            : cell.by !== "you" ? h("button", { class: "btn quiet", type: "button", title: "Keep what the program drew here, through a new performance",
              onclick: () => { setEdits(M.lockPatch(cell), `Lock ${t.label} in ${s.label}`); say(`${t.label} in ${s.label}: locked`); } }, lockIcon(), " Lock")
            : h("button", { class: "btn quiet", type: "button", disabled: true, title: "Yours: nothing of chance's here to lock" }, lockIcon(), " Lock")),
        h("div", { class: "row" },
          h("button", { class: "btn quiet", type: "button", onclick: () => select({ kind: "player", id: t.id }) }, `${t.label} everywhere`),
          h("button", { class: "btn quiet", type: "button", onclick: () => select({ kind: "section", id: s.id }) }, `everyone in ${s.label}`))),
      why: (cell.why || []).map((r) => ({ kind: r.kind === "before" ? "parent" : r.kind, text: r.text })),
      hear: hearHow,
      release: { disabled: !(cell.by === "you" || l.locked), action: () => clearEdits(Object.keys(M.releasePatch(cell)), `${t.label} in ${s.label}: the program's`) } });
    return true;
  }

  function seamState(sel) {
    const s = sectionAt(sel.id), seam = s?.seam;
    if (!s || !seam) return false;
    // drawn from the latest edit, not the answer drawn before it: a click shows at once (the column is drawn again
    // in place), and a quick second click (a riser, then a roll) builds on the first instead of undoing it
    const latest = () => (Object.prototype.hasOwnProperty.call(state.edits, seam.path) ? state.edits[seam.path] : seam.value) || null;
    const value = latest(), yours = edited(seam.path) || seam.yours;
    const bars = S.sound?.transition?.bars || [1, 2, 4];
    const put = (next, label) => { if (next) setEdit(seam.path, next, label); else releaseEdit(seam.path, label); renderInspector(); };
    const longest = (v) => Math.max(0, ...M.seamLengths(v).filter((x) => x.kind !== "stop").map((x) => x.bars));
    // each kind on its own row with its own length (a 4-bar riser with a 1-bar roll); every row always drawn, so a
    // choice adds no row under the pointer. A length pressed for a kind that's off puts it on at that length.
    const kindRow = (k) => {
      const on = !!value?.[k], n = on ? M.seamLengths(value).find((x) => x.kind === k).bars : 0, unit = k === "stop" ? "beat" : "bar";
      return [
        h("button", { class: `chip${on ? " on you" : ""}`, type: "button", "aria-pressed": String(on), "data-key": `seam:${k}`,
          onclick: () => put(M.seamToggle(latest(), k, k === "stop" ? 2 : longest(latest()) || 1), `Into ${s.label}: ${on ? `no ${M.KIND_WORDS[k].replace(/^an? /, "")}` : M.KIND_WORDS[k]}`) }, M.KIND_WORDS[k]),
        h("span", { class: "chips lengths", role: "group", "aria-label": `${M.KIND_WORDS[k]}: how long` }, bars.map((b) => h("button", {
          class: `chip small${on && n === b ? " on you" : ""}${on ? "" : " off"}`, type: "button", "aria-pressed": String(on && n === b),
          title: on ? null : `${M.KIND_WORDS[k]} over ${b} ${unit}${b === 1 ? "" : "s"}`,
          onclick: () => { if (on && n === b) return; const v = latest(); put(v?.[k] ? M.seamLength(v, k, b) : M.seamToggle(v, k, b), `Into ${s.label}: ${M.KIND_WORDS[k]} over ${b} ${unit}${b === 1 ? "" : "s"}`); } },
        `${b} ${unit}${b === 1 ? "" : "s"}`)))];
    };
    const sweepType = typeof value?.sweep === "object" ? value.sweep.type : "highpass";
    const from = seam.from ? sectionAt(seam.from) : null;
    shell({ kind: "seam", rubric: `Into ${s.label}`, mine: yours,
      // short, so it keeps its two lines as kinds are added (the chips say which, and how long; the tooltip, in words)
      set: h("span", { title: M.seamWords(value) }, `${from ? `From ${from.label}` : "At the start"}: ${value
        ? `${["riser", "sweep", "roll", "stop", "impact", "down"].filter((k) => value[k]).map((k) => ({ down: "downlifter" })[k] || k).join(" · ")}${yours ? " (yours)" : ""}`
        : "nothing, the band goes straight on"}`),
      body: h("div", {},
        seam.before ? h("div", { class: "seamkinds", role: "group", "aria-label": "Before it" }, h("span", { class: "label wide" }, "Before it"),
          ["riser", "sweep", "roll", "stop"].flatMap(kindRow))
          : h("p", { class: "hint" }, "Nothing comes before the first section, so nothing builds into it; an impact on its downbeat can."),
        h("div", { class: "seamkinds", role: "group", "aria-label": "On the downbeat" }, h("span", { class: "label wide" }, "On the downbeat and after"),
          h("button", { class: `chip${value?.impact ? " on you" : ""}`, type: "button", "aria-pressed": String(!!value?.impact), "data-key": "seam:impact",
            onclick: () => put(M.seamToggle(latest(), "impact"), `Into ${s.label}: an impact`) }, "an impact"), h("span", {}),
          kindRow("down")),
        seam.before ? h("div", { class: "row" }, h("span", { class: "label" }, "The sweep"), h("span", { class: "chips", role: "group", "aria-label": "The sweep" },
          [["highpass", "rising (the bass thins out)"], ["lowpass", "falling (the top closes)"]].map(([type, text]) => h("button", {
            class: `chip${value?.sweep && sweepType === type ? " on you" : ""}`, type: "button", disabled: !value?.sweep, "aria-pressed": String(!!value?.sweep && sweepType === type),
            title: value?.sweep ? null : "Choose a sweep first",
            onclick: () => { const v = latest(); if (!v?.sweep || sweepType === type) return; put({ ...v, sweep: { bars: typeof v.sweep === "object" ? v.sweep.bars : v.sweep, type } }, `Into ${s.label}: the sweep ${type === "lowpass" ? "falling" : "rising"}`); } }, text)))) : null,
        h("p", { class: "hint" }, "A transition is sound, not arrangement: it doesn't change who plays or how long a section is; a roll takes the snare's place in its bars, a stop quiets the band and not the singer.")),
      why: yours ? [["you", `yours: ${M.seamWords(value)}`]] : [["song", "the song's own seams are plain: the band goes straight on, and a turn is how this song breathes between parts"]],
      hear: () => listen("you", s.index),
      release: { disabled: !edited(seam.path), action: () => { releaseEdit(seam.path, `Into ${s.label}: the program's`); renderInspector(); } } });
    return true;
  }

  function composerState(sel) {
    const st = sel.kind === "chord" ? C()?.chordState?.() : C()?.noteState?.();
    if (!st) return sectionState({ kind: "section", id: sel.section || S.open });
    shell({ kind: sel.kind, rubric: st.rubric, set: st.set, mine: st.mine,
      body: h("div", {}, sel.kind === "chord" && st.scope ? h("div", { class: "row" }, h("span", { class: "label" }, "Applies"), st.scope) : null, st.body),
      why: st.why, hear: st.hear, release: st.release });
    return true;
  }

  function lineState(sel) {
    const s = sectionAt(sel.id), w = wordsOf(s);
    const phrases = state.view.composition?.sections?.find((x) => x.id === sel.id)?.phrases || [];
    const p = phrases[sel.line];
    if (!s || !p?.lyric_path) return false;
    const anchor = h("div", { class: "lyric-author", "data-whole": "" });  // author.js's own nodes: redrawn whole
    // one line at a time: a line used, the column moves on to the next one to write (typing elsewhere stays a draft)
    const next = () => {
      const j = phrases.findIndex((q, k) => k > sel.line && q.lyric_path);
      if (j < 0 || S.sel?.kind !== "line" || S.sel.id !== sel.id || S.sel.line !== sel.line) return;
      select({ kind: "line", id: sel.id, line: j });
      $("inspector").querySelector("textarea")?.focus({ preventScroll: true });
    };
    window.SongbirdAuthor?.line(state.view, sel.id, sel.line, anchor, { next });
    shell({ kind: "line", rubric: `${s.label}, line ${sel.line + 1}`, mine: !!p.authored,
      set: `${p.authored ? "yours" : w?.how ? `the song's own, ${w.how}` : "the song's own"}: ${p.syllable_count} syllables`,
      body: h("div", {},
        phrases.length > 1 ? chipRow("Line", phrases.map((_, j) => ({ value: j, text: String(j + 1), disabled: !phrases[j].lyric_path })), sel.line,
          (j) => select({ kind: "line", id: sel.id, line: j })) : null,
        anchor,
        h("p", { class: "hint" }, "Checked for its count and the singer's pronunciation before it changes the song. The meaning and the rhyme are yours.")),
      why: p.authored ? [["you", "your line; it follows these words wherever they are sung"]] : [["lineage", "handed down from the song as it began"], ["machine", card("words")?.detail || ""]],
      hear: () => listen("you", s.index) });
    return true;
  }

  function playerState(sel) {
    const t = S.grid?.tracks.find((x) => x.id === sel.id);
    if (!t || t.kind !== "player") return false;
    const sp = S.sound?.players.find((p) => p.player === t.id), band = card("band"), b = state.start.bounds;
    const gain = sp?.gain?.value ?? band?.band?.[t.id] ?? 1;
    const program = was(`band.${t.id}`);
    const row = S.grid.sections.map((s) => {
      const cell = S.grid.cells.get(`${t.id}|${s.id}`), l = M.look(cell);
      return h("i", { class: `${l.level !== "out" ? "on" : ""}${l.level === "hard" ? " hard" : ""}${l.whose === "you" || l.locked ? " you" : ""}`, title: `${s.label}: ${l.level}` });
    });
    const paths = [`band.${t.id}`, ...Object.keys(state.edits).filter((p) => p.startsWith(`sound.${t.id}.`) || p.startsWith(`mix.${t.id}.`))];
    const leads = band && !band.styled && (state.start.bounds["band.lead"]?.options || []).includes(t.id);
    shell({ kind: "player", rubric: t.label, mine: paths.some(edited),
      set: `${pct(gain)}${edited(`band.${t.id}`) && typeof program === "number" ? ` (was ${pct(program)})` : ""}; ${t.family || ""}${sp?.patch ? `, ${sp.patch.value}` : sp?.kit ? `, the ${sp.kit.value} kit` : ""}`,
      body: h("div", {},
        h("div", { class: "row" }, h("span", { class: "label" }, "Plays in"), h("span", { class: "minisec", title: "Each section, left to right" }, row)),
        field("Level", `band.${t.id}`, gain, b["band.gain"] || { min: 0, max: 2, step: 0.01 }, pct, ["out", "200%"]),
        soundControls(t, sp),
        leads ? chipRow("Leads where nobody sings", [{ value: true, text: "this one" }], band.band.lead === t.id, () => setEdit("band.lead", t.id, `${t.label} leads where nobody sings`), edited("band.lead")) : null,
        routeControls(t.id, t.label),
        h("div", { class: "row" }, h("button", { class: "btn quiet", type: "button", onclick: () => setEdit(`band.${t.id}`, 0, `${t.label} sits out`) }, "Sit out everywhere"))),
      why: [edited(`band.${t.id}`) ? ["you", `${pct(gain)}; the program had ${pct(program)}`] : null, ...(band?.reasons || []).filter((r) => r.kind !== "you").slice(0, 3)].filter(Boolean),
      hear: hearHow,
      release: releasing(paths, `${t.label}: the program's`) });
    return true;
  }
  function soundControls(t, sp) {
    if (!sp) return null;
    const out = [];
    if (sp.patch) out.push(chipRow("Sound", sp.patch.options.map((o) => ({ value: o.name, text: o.name, title: o.about })), sp.patch.value,
      (v) => (v === sp.patch.program ? releaseEdit(sp.patch.path, `${t.label}: its own sound`) : setEdit(sp.patch.path, v, `${t.label}: ${v}`)), sp.patch.yours));
    if (sp.kit) out.push(chipRow("Kit", sp.kit.options.map((o) => ({ value: o.name, text: o.name, title: o.about })), sp.kit.value,
      (v) => (v === sp.kit.program ? releaseEdit(sp.kit.path, `${t.label}: its own kit`) : setEdit(sp.kit.path, v, `${t.label}: the ${v} kit`)), sp.kit.yours));
    if (sp.sidechain && (!sp.sidechain.is_key || sp.sidechain.yours)) {  // not on the drummer: it's the kick it ducks on
      out.push(h("div", { class: "row" }, h("span", { class: "label" }, "Pump"), pumpSelect(sp.sidechain, `${t.label}: pump`),
        h("span", { class: "hint" }, sp.sidechain.has_kick ? "ducks on the kick" : "no kick here: it pumps on the beat")));
      out.push(pumpWhere(sp.sidechain, `${t.label}: pump`));
    }
    if (sp.pan) out.push(field("Where it sits", sp.pan.path, sp.pan.value, { min: -1, max: 1, step: 0.05 }, panWords, ["left", "right"]));
    const more = [];
    if (sp.send) more.push(field("How much reaches the room", sp.send.path, sp.send.value, { min: sp.send.min, max: sp.send.max, step: 0.05 }, (x) => `${Number(x).toFixed(2)}×`, ["dry", "3×"]));
    if (sp.filter) {
      const f = sp.filter;
      more.push(field("Filter: how open", f.cutoff.path, f.cutoff.value, f.cutoff, (x) => `${Math.round(x)} Hz`, ["dark", "open"], { log: true, yours: !!f.cutoff.yours }));
      if (f.resonance) more.push(field("Filter: resonance", f.resonance.path, f.resonance.value, { min: 0, max: 1, step: 0.01 }, pct, ["none", "sings"], { yours: !!f.resonance.yours }));
      if (f.envelope) more.push(field("Filter: envelope", f.envelope.path, f.envelope.value, { min: 0, max: 6, step: 0.1 }, (x) => `${Number(x).toFixed(1)} oct`, ["still", "wide"], { yours: !!f.envelope.yours }));
    }
    if (sp.pieces) for (const [piece, v] of Object.entries(sp.pieces)) {
      if (!v) continue;
      const now = v.value || {};
      for (const [knob, r] of Object.entries(v.knobs || {})) {
        more.push(field(`The ${piece}: ${knob}`, `${v.path}.${knob}`, now[knob] ?? r.own ?? 0, { min: r.min, max: r.max, step: knob === "tune" ? 1 : 0.05 },
          (x) => (knob === "tune" ? `${x > 0 ? "+" : ""}${x} st` : `${Number(x).toFixed(2)}×`), knob === "tune" ? ["lower", "higher"] : ["shorter", "longer"],
          { yours: !!v.yours, commit: (x) => setEdit(v.path, { ...(edited(v.path) ? state.edits[v.path] : now), [knob]: x }, `${t.label}: the ${piece}'s ${knob}`) }));
      }
    }
    if (more.length) out.push(h("details", {}, h("summary", {}, "more"), more));
    return h("div", {}, out);
  }
  function routeControls(part, label) {
    const ui = P();
    if (!ui) return null;
    if (!ui.parts().length) ui.fetch();
    const r = ui.own(part), file = ui.fileChannel(part), midi = ui.midi;
    const now = Number.isInteger(r) ? "midi" : r;
    const pick = (to) => {
      if (to === "midi") { if (!midi.access) ui.fetch(); window.SongbirdPlayers.connect(false).then(() => ui.setRoute(part, String(file))); }
      else ui.setRoute(part, to);
    };
    return h("div", {},
      chipRow("In the sketch", [{ value: "page", text: "here" }, { value: "midi", text: "over MIDI", disabled: !ui.hasMidi(), title: ui.hasMidi() ? "To a channel of your synth or sequencer" : "This browser has no Web MIDI" }, { value: "off", text: "off" }],
        now, pick, Object.prototype.hasOwnProperty.call(ui.set.routes, part)),
      Number.isInteger(r) ? h("div", { class: "row" }, h("span", { class: "label" }, "Channel"),
        h("span", { class: "stepper" }, h("button", { type: "button", "aria-label": "Channel down", onclick: () => ui.setRoute(part, String(Math.max(0, r - 1))) }, "−"),
          h("output", {}, `${r + 1}${r === file ? " (the file's)" : ""}`), h("button", { type: "button", "aria-label": "Channel up", onclick: () => ui.setRoute(part, String(Math.min(15, r + 1))) }, "+"))) : null,
      h("details", {}, h("summary", {}, "more: MIDI out"),
        h("div", { class: "row" }, midi.access
          ? h("select", { "aria-label": "MIDI out", onchange: (e) => { window.SongbirdPlayers.choose(e.target.value); renderInspector(); } },
            h("option", { value: "" }, "none: everything plays here"), ui.outputs().map((o) => h("option", { value: o.id, selected: midi.output === o }, o.name || o.id)))
          : h("button", { class: "btn quiet", type: "button", disabled: !ui.hasMidi(), onclick: () => window.SongbirdPlayers.connect(false) }, "Connect MIDI"),
          h("button", { class: "btn quiet", type: "button", onclick: () => window.SongbirdPlayers.panic(), title: "Every channel of the output told to stop" }, "Panic")),
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: ui.set.programs, onchange: (e) => ui.programs(e.target.checked) }), " send its General MIDI sound"),
        // the sketch's own players (the tune, its chords, its bass): where each goes, as the band's parts do
        ui.OWN.filter((o) => o.part !== part).map((o) => {
          const own = ui.own(o.part), at = Number.isInteger(own) ? "midi" : own;
          return chipRow(o.name, [{ value: "page", text: "here" }, { value: "midi", text: "MIDI", disabled: !midi.output }, { value: "off", text: "off" }], at,
            (to) => ui.setRoute(o.part, to === "midi" ? String(ui.fileChannel(o.part)) : to), Object.prototype.hasOwnProperty.call(ui.set.routes, o.part));
        }),
        h("div", { class: "row" },
          h("button", { class: "link small", type: "button", disabled: !midi.output, onclick: () => ui.everyone("midi") }, "Everyone to MIDI, as the file"),
          h("button", { class: "link small", type: "button", onclick: () => ui.everyone("page") }, "Everyone here"),
          h("button", { class: "link small", type: "button", onclick: () => { ui.set.routes = {}; ui.setRoute("tune", "page"); } }, "As at first")),
        h("p", { class: "hint", "aria-live": "polite" }, ui.note())));
  }

  function singerState() {
    const c = card("singer"), mix = card("mix"), b = state.start.bounds, m = mix?.mix || {};
    const phrasings = phrasingChoices(state.start.phrasings);
    const sel = h("select", { "aria-label": "Whose way it is sung", id: "singerWay" }, h("option", { value: "" }, "the song's own way"),
      phrasings.map((p) => h("option", { value: p.id }, `${p.way || `${p.label}'s way`}${p.detail ? ` (${p.detail})` : ""}`)));
    sel.value = c?.phrasing || "";
    sel.addEventListener("change", (e) => setEdit("phrasing", e.target.value || null, "The singer's way"));
    const sung = S.grid?.sections.map((s) => h("i", { class: s.sung ? "on" : "", title: `${s.label}: ${s.sung ? "sung" : "played"}` })) || [];
    shell({ kind: "singer", rubric: "The singer", mine: edited("phrasing") || edited("mix.forward") || edited("mix.intimacy"),
      set: `${c?.value || ""}${c?.detail ? `; ${c.detail}` : ""}`,
      body: h("div", {},
        h("div", { class: "row" }, h("span", { class: "label" }, "Sings in"), h("span", { class: "minisec" }, sung)),
        phrasings.length ? h("div", { class: "row" }, h("span", { class: "label" }, "Whose way"), sel)
          : h("p", { class: "hint" }, state.start.sing.available ? "Sing it (under Tools) and the song can be sung your way here." : state.start.sing.why),
        field("Over the band", "mix.forward", m.forward, b["mix.forward"], (x) => `${Number(x).toFixed(1)} dB`, ["among it", "well over it"]),
        field("How close", "mix.intimacy", m.intimacy, b["mix.intimacy"], pct, ["further back", "at your ear"]),
        routeControls("tune", "the tune")),
      why: c?.reasons || [], hear: () => listen("you", null),
      release: releasing(["phrasing", "mix.forward", "mix.intimacy"], "The singer as the program has it") });
    return true;
  }
  function choirState() {
    const c = card("choir");
    const where = S.grid?.sections.map((s) => h("i", { class: s.choir ? "on" : "", title: `${s.label}: ${s.choir ? "they sing" : "out"}` })) || [];
    shell({ kind: "choir", rubric: "Voices before", set: `${c?.value || ""}${c?.detail ? `; ${c.detail}` : ""}`,
      body: h("div", {}, h("div", { class: "row" }, h("span", { class: "label" }, "Sing in"), h("span", { class: "minisec" }, where)),
        routeControls("choir1", "the first voice before"),
        h("p", { class: "hint" }, "How many there are follows the versions before; where they sing is the song's.")),
      why: c?.reasons || [], hear: hearHow });
    return true;
  }
  function roomState() {
    const c = card("mix"), b = state.start.bounds, m = c?.mix || {};
    shell({ kind: "room", rubric: "The room", mine: ["mix.space", "mix.width", "mix.rt60", "mix.predelay"].some(edited), set: `${c?.value}; ${c?.detail}`,
      body: h("div", {},
        field("How much of the room", "mix.space", m.space, b["mix.space"], pct, ["dry", "roomy"]),
        field("How wide", "mix.width", m.width, b["mix.width"], pct, ["narrow", "wide"]),
        b["mix.rt60"] ? h("details", {}, h("summary", {}, "more"),
          field("How long it rings", "mix.rt60", m.rt60, b["mix.rt60"], (x) => `${Number(x).toFixed(2)} s`, ["a small room", "a hall"]),
          b["mix.predelay"] ? field("How soon it answers", "mix.predelay", m.predelay, b["mix.predelay"], (x) => `${Math.round(x * 1000)} ms`, ["at once", "later"]) : null) : null),
      why: c?.reasons || [], hear: () => listen("you", null),
      release: releasing(["mix.space", "mix.width", "mix.rt60", "mix.predelay"], "The room as the program has it") });
    return true;
  }
  function styleState() {
    const c = card("style");
    if (!c) return false;
    const st = c.style, opts = (map) => Object.entries(map || {}).map(([value, text]) => ({ value, text }));
    const styles = h("select", { "aria-label": "The style", id: "styleName" }, opts(c.styles).map((o) => h("option", { value: o.value }, o.text)));
    styles.value = st.name;
    styles.addEventListener("change", (e) => setEdit("style.name", e.target.value, `The style: ${c.styles[e.target.value]}`));
    shell({ kind: "style", rubric: "The style", mine: c.mine, set: `${c.value}${c.detail ? `: ${c.detail}` : ""}`,
      body: h("div", {},
        h("div", { class: "row" }, h("span", { class: "label" }, "The style"), styles),
        chipRow("Its feel", opts(c.feels), st.feel, (x) => setEdit("style.feel", x, "The feel"), edited("style.feel")),
        chipRow("How it ends", opts(c.endings), st.ending, (x) => setEdit("style.ending", x, "The ending"), edited("style.ending")),
        chipRow("Backing voices", opts(c.backings), st.backing, (x) => setEdit("style.backing", x, "The backing voices"), edited("style.backing")),
        chipRow("The last refrain", [{ value: true, text: "a whole step up" }, { value: false, text: "in the same key" }], !!st.lift, (x) => setEdit("style.lift", x, "The last refrain"), edited("style.lift"))),
      why: c.reasons, hear: () => listen("you", null), release: releasing(allPaths(c).concat(Object.keys(state.edits).filter((p) => p.startsWith("style."))), "The program's style") });
    return true;
  }
  function bandState() {
    const c = card("band"), b = state.start.bounds, s = state.start;
    if (!c) return false;
    const band = c.band;
    shell({ kind: "band", rubric: "The band", mine: ["band.pattern", "band.lead", "band.density", "band.brightness"].some(edited), set: `${c.value}${c.detail ? `: ${c.detail}` : ""}`,
      body: h("div", {},
        c.styled ? null : chipRow("How it plays", b["band.pattern"].options.map((x) => ({ value: x, text: s.patterns[x] || x })), band.pattern, (x) => setEdit("band.pattern", x, "How the band plays"), edited("band.pattern")),
        c.styled ? null : chipRow("Who leads where nobody sings", b["band.lead"].options.map((x) => ({ value: x, text: c.players[x] || x })), band.lead, (x) => setEdit("band.lead", x, "Who leads"), edited("band.lead")),
        field("How busy", "band.density", band.density, b["band.density"], pct, ["sparse", "busy"]),
        field("How bright", "band.brightness", band.brightness, b["band.brightness"], pct, ["dark and soft", "bright"]),
        h("p", { class: "hint" }, c.styled ? "The style chooses who plays and who leads; each player's part is theirs to change in Arrange, its level and sound in Mix." : "Each player's part is in Arrange; its level in Mix."),
        h("div", { class: "row" }, h("button", { class: "btn quiet", type: "button", onclick: () => showView("arrange") }, "Arrange"), h("button", { class: "btn quiet", type: "button", onclick: () => showView("mix") }, "Mix"))),
      why: c.reasons, hear: () => listen("you", null), release: releasing(["band.pattern", "band.lead", "band.density", "band.brightness"], "The band as the program has it") });
    return true;
  }
  function shapeState() {
    const c = card("shape"), s = state.start, v = state.view;
    if (!c) return false;
    const arranged = !!v.composition?.arranged;
    const byPart = {};
    for (const ch of c.choices || []) (byPart[ch.part] = byPart[ch.part] || []).push(ch);
    const toggles = s.optional.map((part) => {
      const drawn = !!c.parts?.[part], flip = (byPart[part] || []).find((x) => x.value === !drawn);
      const now = () => (edited(`form.${part}`) ? !!state.edits[`form.${part}`] : drawn);  // a second quick click undoes the first
      const on = now();
      return h("button", { class: `chip${on ? " on" : ""}${on && edited(`form.${part}`) ? " you" : ""}`, type: "button", "aria-pressed": String(on), disabled: !flip || !flip.allowed,
        title: !flip ? "This part can't be changed in this arrangement" : !flip.allowed ? flip.why : null, onclick: () => { const was = now(); setEdit(`form.${part}`, !was, was ? `No ${s.parts[part].replace(/^(an?|the) /, "")}` : `With ${s.parts[part]}`); } }, s.parts[part]);
    });
    const release = () => { const next = copyEdits(); for (const p of Object.keys(next)) if (p.startsWith("form.")) delete next[p]; next["form.order"] = null; commitEdits(next, "Use the song's shape"); };
    shell({ kind: "shape", rubric: "The shape", mine: c.mine || !!v.edits["form.order"], set: c.value,
      body: arranged ? h("div", {}, h("p", { class: "hint" }, "The parts are in the order you set in Arrange. Use the song's shape to choose the verses and parts here again."),
        h("button", { class: "btn quiet", type: "button", onclick: release }, "Use the song's shape"))
        : h("div", {},
          byPart.verses ? chipRow("Verses", byPart.verses.map((x) => ({ value: x.value, text: String(x.value), disabled: !x.allowed, title: x.why })), c.parts.verses, (n) => setEdit("form.verses", n, `${n} verses`), edited("form.verses")) : null,
          h("div", { class: "row" }, h("span", { class: "label" }, "Parts"), h("span", { class: "chips" }, toggles)),
          h("p", { class: "hint" }, "Their order is the regions in Arrange: drag them there, or ← → on a section.")),
      why: c.reasons, hear: () => listen("you", null), release: { disabled: !c.mine && !v.edits["form.order"], action: release } });
    return true;
  }

  // ------------------------------------------------------------------ sheets: Your tools, the Time drawer
  function openTools(on, side) {
    const sheet = $("finishPanel");
    if (on === undefined) on = sheet.hidden;
    sheet.hidden = !on;
    $("scrim").hidden = !on && $("drawer").hidden;
    $("toolsBtn").setAttribute("aria-expanded", String(on));
    if (on) {
      if (side === "record") $("recordPanel").scrollIntoView({ block: "nearest" });
      else $("toolsTitle").focus();
      sayTarget();
    } else $("toolsBtn").focus({ preventScroll: true });
  }
  function reveal(what, scroll) { if ($("finishPanel").hidden) openTools(true, what); else if (scroll) $("recordPanel").scrollIntoView({ block: "nearest" }); }
  function sayTarget() {  // what "Play a part in" plays over: the selection
    const s = S.open || S.sel?.id || S.sel?.section;
    const label = s ? sectionAt(s)?.label : null;
    $("performWhat").textContent = `A MIDI keyboard, live, over the sketch as the guide: only the notes are kept. It starts on ${label || "the whole song"}; choose the player and the lines in it.`;
    const where = $("performWhere");
    if (where && s) { const i = compIndex(s); if (i >= 0 && where.value !== String(i)) { where.value = String(i); where.dispatchEvent(new Event("change")); } }
  }
  function openTime(on) {
    const d = $("drawer");
    if (on === undefined) on = d.hidden;
    d.hidden = !on;
    $("timeBtn").setAttribute("aria-expanded", String(on));
    $("timeBtn").textContent = on ? "Time ▴" : "Time ▾";
    $("scrim").hidden = !on && $("finishPanel").hidden;
    if (on) { d.style.top = `${$("transport").offsetTop + $("transport").offsetHeight}px`; renderTimeline(); loadCompare(); d.querySelector("h2")?.setAttribute("tabindex", "-1"); d.querySelector("h2")?.focus(); }
    else $("timeBtn").focus({ preventScroll: true });
  }
  function escape() {
    if (S.pop) { const back = opener(S.pop); togglePop(S.pop); $(back)?.focus(); return true; }
    if (!$("finishPanel").hidden) { openTools(false); return true; }
    if (!$("drawer").hidden) { openTime(false); return true; }
    if (S.open) { closeNotes(); return true; }
    if (S.sel) { select(null); return true; }
    if (S.songShown) { S.songShown = false; renderInspector(); return true; }
    return false;
  }

  // ------------------------------------------------------------------ the keyboard (docs/STUDIO-REDESIGN.md's table)
  function key(e) {
    // Enter or Space on a control of the page's is a keyboard selection: the inspector's heading takes the focus
    if (e.key === "Enter" && e.target.closest?.("#grid [role=gridcell], #grid .region, #grid .name, #page .rub, #mix .nm, .door")) {
      S.keyed = true;
      setTimeout(() => { S.keyed = false; }, 0);  // only for the selection this key makes
    }
    const a = M.keyAction(e);
    if (!a || document.querySelector("dialog[open]")) return;
    if (e.target.closest?.(".sbc-note, .sbc-roll-scroll") && a.action === "step") return;  // a note's own arrows (composer.js)
    // Space plays from the page, the grid and ▶ ■; on another button, a link or a field it presses it
    if (a.action === "play" && e.target.closest?.("button, a, summary, select, input") && !e.target.closest("#grid") && !e.target.matches("#tPlay")) return;
    if (a.action === "play" && e.target.matches?.("input[type=checkbox], input[type=radio]")) return;
    switch (a.action) {
      case "play": e.preventDefault(); play(a.how); break;
      case "loop": toggle("tLoop"); break;
      case "click": toggle("tClick"); break;
      case "view": showView(a.view, e.target.getAttribute?.("role") === "tab"); break;
      case "open": {
        const region = e.target.closest?.(".region");
        const id = region ? region.dataset.key.slice(7) : S.sel?.kind === "section" && !e.target.closest?.("button, a, input, select, summary") ? S.sel.id : null;
        if (id) { e.preventDefault(); S.keyed = false; if (S.sel?.id !== id) select({ kind: "section", id }); openNotes(id, true); }
        break;
      }
      case "escape": if (escape()) e.preventDefault(); break;
      case "mute": case "solo": {
        const name = S.sel?.kind === "player" ? S.sel.id : S.sel?.kind === "cell" ? S.sel.player : null;
        const t = S.grid?.tracks.find((x) => x.id === name && x.kind === "player");
        if (t) { e.preventDefault(); const band = card("band"); const bc = { ...band, players: { ...band.players, [t.id]: t.label } }; (a.action === "mute" ? mutePlayer : soloPlayer)(bc, t.id); }
        break;
      }
      case "record": e.preventDefault(); record(); break;
      case "time": e.preventDefault(); openTime(); break;
      case "move": if (S.sel?.kind === "section") { e.preventDefault(); moveSection(S.sel.id, { step: a.step }); } break;
      case "step":
        if (e.target.closest?.(".sbc-note, input, select, [role=tab]")) return;
        if (stepCell(a.axis, a.step, e.target)) e.preventDefault();
        break;
      default: break;
    }
  }
  function toggle(id) {
    const b = $(id), on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(on));
    if (id === "tLoop") { C()?.options?.({ loop: on }); $("popLoop").checked = on; }
    if (id === "tClick") { C()?.options?.({ metronome: on }); $("popClick").checked = on; }
    say(`${id === "tLoop" ? "Loop" : "Click"} ${on ? "on" : "off"}`);
  }

  // ------------------------------------------------------------------ wiring
  function wire() {
    for (const t of document.querySelectorAll("#tabs [role=tab]")) {
      t.addEventListener("click", () => showView(t.dataset.view));
      t.addEventListener("keydown", (e) => {
        const tabs = [...document.querySelectorAll("#tabs [role=tab]")], i = tabs.indexOf(t);
        const next = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 }[e.key];
        if (next === undefined) return;
        e.preventDefault(); e.stopPropagation(); showView(tabs[next].dataset.view, true);
      });
    }
    for (const b of document.querySelectorAll("#bottombar [data-view]")) b.addEventListener("click", () => showView(b.dataset.view));
    $("viewWhat").addEventListener("click", () => { const a = $("viewAbout"); a.hidden = !a.hidden; $("viewWhat").setAttribute("aria-expanded", String(!a.hidden)); });
    for (const b of document.querySelectorAll("[data-how]")) b.addEventListener("click", () => setHow(b.dataset.how));
    $("tPlay").addEventListener("click", () => play());
    $("tLoop").addEventListener("click", () => toggle("tLoop"));
    $("tClick").addEventListener("click", () => toggle("tClick"));
    $("popLoop").addEventListener("change", () => toggle("tLoop"));
    $("popClick").addEventListener("change", () => toggle("tClick"));
    $("sketchChords").addEventListener("change", (e) => C()?.options?.({ chords: e.target.checked }));
    $("sketchBass").addEventListener("change", (e) => C()?.options?.({ bass: e.target.checked }));
    $("howMore").addEventListener("click", () => togglePop("howPop"));
    $("positionNow").addEventListener("click", () => { if (narrow()) togglePop("howPop"); });
    $("tempoBtn").addEventListener("click", () => togglePop("tempoPop"));
    $("keyBtn").addEventListener("click", () => togglePop("keyPop"));
    for (const b of document.querySelectorAll("#howPop [data-do]")) b.addEventListener("click", () => {
      if (b.dataset.do === "roll") $("roll").click(); else travelHistory(b.dataset.do);
    });
    $("toolsBtn").addEventListener("click", () => openTools());
    $("timeBtn").addEventListener("click", () => openTime());
    $("scrim").addEventListener("click", () => { openTools(false); openTime(false); });
    for (const b of document.querySelectorAll("[data-close]")) b.addEventListener("click", () => (b.closest("#drawer") ? openTime(false) : openTools(false)));
    $("performOpen").addEventListener("click", () => {
      const p = $("performPanel"); p.hidden = !p.hidden; $("performOpen").setAttribute("aria-expanded", String(!p.hidden));
      if (!p.hidden) { window.SongbirdPerform?.render(state.view); sayTarget(); }
    });
    const drop = $("midiDrop");
    drop.addEventListener("click", () => $("importFile").click());
    for (const ev of ["dragenter", "dragover"]) drop.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); drop.classList.add("over"); $("dropVeil").hidden = true; });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => { e.preventDefault(); e.stopPropagation(); drop.classList.remove("over"); $("dropVeil").hidden = true; window.SongbirdPerform?.bringBack(e.dataTransfer.files[0]); });
    document.addEventListener("keydown", key);
    document.addEventListener("click", (e) => {  // a popover closes when something else is pressed
      if (S.pop && !e.target.closest(".pop, #howMore, #tempoBtn, #keyBtn, #positionNow")) togglePop(S.pop);
    });
    const audio = $("audio");
    for (const ev of ["play", "pause", "ended"]) audio.addEventListener(ev, () => { paintPlay(); if (ev !== "play") setTimeout(idle, 1200); });
    audio.addEventListener("timeupdate", wholeSongAt);
    new ResizeObserver(() => { if (S.playhead !== null) placeHead(S.playhead); }).observe($("gridScroll"));
    showView("page");
    setHow(M.defaultHow(null), false);  // nothing selected: the whole song, sung (decision 2)
    $("songBtn").addEventListener("click", () => { S.songShown = !S.songShown; select(null); });
  }

  // ------------------------------------------------------------------ what studio.js tells the score
  // its render has already set the words (renderPage) and the inspector (renderInspector); the grid and the mix
  // come from the arrangement and the sound, asked for again with the same edits
  function render(view) {
    if (!view) return;
    renderTransport();
    idle();
    if (S.hash) loadGrid().then(afterFirst); else loadGrid();
  }
  function started(start, hash) {
    const classic = location.pathname.replace(/\/$/, "");
    $("classicLink").href = `${classic.startsWith("/v/") ? classic : ""}/classic`;
    const p = start.public;
    $("toolsWhere").textContent = p
      ? `An open studio: each person can have ${p.records} whole songs and ${p.previews} sections made an hour, one at a time for everyone; what you record waits ${p.download_hours} hours to be downloaded.`
      : start.shared ? "Recordings are made, and kept, on the computer serving this studio: download yours to keep it."
        : `Recordings go into ${start.out} on this computer.`;
    if (p) {  // what an open studio keeps: in Help, a word away
      const kept = document.createElement("button");
      Object.assign(kept, { type: "button", className: "btn quiet", textContent: "What's kept" });
      kept.addEventListener("click", () => { window.SongbirdHelp?.open(); $("helpKept")?.scrollIntoView?.({ block: "nearest" }); });
      $("toolsWhere").append(" ", kept);
    }
    if (start.version) $("versionNote").textContent = "This page is on someone's version. Opening another starts from that one instead.";
    // a view and a selection in the address, for a link or a picture: #view=arrange&sel=cell:drum:refrain:0&open=refrain:0&panel=tools
    if (hash.view) showView(hash.view);
    S.hash = hash;
  }
  function afterFirst() {  // once the grid is drawn: the address's selection, notes and sheet
    const hash = S.hash;
    if (!hash) return;
    S.hash = null;
    if (hash.open) openNotes(hash.open);
    if (hash.sel) {
      const [kind, ...rest] = hash.sel.split(":");
      const parts = rest.join(":");
      const sel = kind === "cell" ? { kind, player: rest[0], id: rest.slice(1).join(":") } : kind === "line" ? { kind, id: rest.slice(0, 2).join(":"), line: Number(rest[2] || 0) }
        : ["section", "seam"].includes(kind) ? { kind, id: parts } : kind === "player" ? { kind, id: parts } : { kind };
      select(sel);
    }
    if (hash.panel === "tools") openTools(true);
    if (hash.panel === "time") openTime(true);
  }
  window.SongbirdScore = {
    render, renderPage, renderInspector, started, reveal, recording, playerChanged, tick, composerSelected, closeNotes, narrow,
    playersChanged: () => { if (S.sel?.kind === "player" || S.sel?.kind === "choir") renderInspector(); renderGrid(); },
    _state: S,
  };
  document.addEventListener("DOMContentLoaded", wire);  // after studio.js, whose globals it uses
})();
