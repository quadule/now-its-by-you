// Original lyrics use the same compact, portable edits as the musical workbench.
"use strict";

(() => {
  const sections = new Map();
  let focus = null;
  const bridge = () => window.StudioBridge;
  const syllables = (text) => text.trim().split(/[\s-]+/u).filter(Boolean).length;
  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function button(text, action) {
    const item = node("button", "btn quiet", text);
    item.type = "button";
    item.addEventListener("click", action);
    return item;
  }
  function capture() {
    const active = document.activeElement;
    focus = active?.dataset?.lyricPath ? {path: active.dataset.lyricPath, start: active.selectionStart, end: active.selectionEnd} : null;
  }
  function count(row) {
    const n = syllables(row.input.value);
    row.count.textContent = `${n} / ${row.phrase.syllable_count} syllables`;
    row.count.classList.toggle("is-valid", n === row.phrase.syllable_count);
    row.input.setAttribute("aria-invalid", String(n !== row.phrase.syllable_count));
    row.input.classList.toggle("is-dirty", row.input.value !== row.base);
  }
  async function apply(section, patch) {
    if (section.busy) return;
    const snapshot = bridge().snapshot();
    const next = {...snapshot.edits, ...patch};
    const paths = new Set(Object.keys(patch));
    const submitted = new Map([...section.rows.values()].map((row) => [row.phrase.lyric_path, row.input.value]));
    section.busy = true;
    section.save.disabled = true;
    section.status.textContent = "Checking syllables and pronunciation…";
    try {
      const response = await fetch("/api/song", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Studio": document.querySelector('meta[name="studio-token"]').content},
        body: JSON.stringify({edits: next}),
      });
      const view = await response.json();
      if (!response.ok) throw new Error(view.error || "The studio couldn't check these lines. Try again.");
      const problems = (view.problems || []).filter((problem) => paths.has(problem.path));
      if (problems.length) throw new Error(problems.map((p) => `Line ${Number(p.path.split(".").at(-1)) + 1}: ${p.why}`).join(" "));
      if (bridge().snapshot().revision !== snapshot.revision) throw new Error("Your song changed while these words were checked. Apply them again when you're ready.");
      bridge().replaceEdits(next, `Write ${section.label.toLowerCase()}`);
      for (const row of section.rows.values()) if (paths.has(row.phrase.lyric_path)) {
        // Typing can continue while validation runs. Only the submitted text
        // becomes the base; newer typing must remain an unapplied draft.
        row.base = patch[row.phrase.lyric_path] ?? submitted.get(row.phrase.lyric_path);
      }
      section.status.textContent = "Your words fit the tune. Hear this section to listen.";
      bridge().toast("Your words are part of the song. Undo brings the previous lines back.");
    } catch (error) { section.status.textContent = error.message; }
    finally { section.busy = false; section.save.disabled = false; }
  }
  function makeSection(s) {
    const details = node("details", "lyric-author");
    details.dataset.authorSection = s.id;
    const summary = node("summary", "", "Write your own lines");
    const hint = node("p", "hint", "One syllable for each note. Split longer words with hyphens, like car-ry. A word between stars, like *heart*, is the one the line leans on: the singer gives it a little more. Keep, move or drop the stars. The singer checks the syllables and pronunciation; the story and rhyme are yours.");
    const lines = node("div", "author-lines");
    const status = node("p", "author-status");
    status.setAttribute("role", "status");
    const section = {details, summary, lines, rows: new Map(), label: s.label, status, busy: false};
    section.save = button("Use these lines", () => {
      const changed = [...section.rows.values()].filter((row) => row.input.value !== row.base);
      if (!changed.length) { status.textContent = "These lines are already in your song."; return; }
      const wrong = changed.filter((row) => syllables(row.input.value) !== row.phrase.syllable_count);
      if (wrong.length) {
        status.textContent = "Match each line's syllable count before applying your words.";
        wrong[0].input.focus();
        return;
      }
      apply(section, Object.fromEntries(changed.map((row) => [row.phrase.lyric_path, row.input.value])));
    });
    const discard = button("Discard typing", () => {
      for (const row of section.rows.values()) { row.input.value = row.base; count(row); }
      status.textContent = "Unapplied typing discarded. Your song is unchanged.";
    });
    const actions = node("div", "author-actions");
    actions.append(section.save, discard);
    details.append(summary, hint, lines, actions, status);
    return section;
  }
  function rowFor(section, p, index, label) {
    let row = section.rows.get(p.lyric_path);
    if (!row) {
      const wrap = node("div", "author-line");
      const input = node("textarea", "author-input");
      input.rows = 2;
      input.maxLength = 500;
      input.spellcheck = true;
      input.dataset.lyricPath = p.lyric_path;
      input.id = `author-${p.lyric_path}`;
      input.setAttribute("aria-label", `${label}: write line ${index + 1}`);
      const name = node("label", "", `Line ${index + 1}`);
      name.htmlFor = input.id;
      const tally = node("span", "author-count");
      tally.id = `${input.id}-count`;
      input.setAttribute("aria-describedby", tally.id);
      const head = node("div", "author-line-head");
      const restore = button("Use the song's line", () => apply(section, {[p.lyric_path]: null}));
      restore.className = "link small";
      restore.title = "Release your original text and sing the bank's words here, including inherited text";
      head.append(name, tally, restore);
      wrap.append(head, input);
      row = {wrap, input, count: tally, restore, base: p.lyric_text, phrase: p};
      input.value = p.lyric_text;
      input.addEventListener("input", () => { count(row); section.status.textContent = "Typing stays here until you use these lines."; });
      section.rows.set(p.lyric_path, row);
      section.lines.append(wrap);
    } else if (row.input.value === row.base) {
      row.input.value = p.lyric_text;
      row.base = p.lyric_text;
    }
    row.phrase = p;
    row.restore.hidden = !p.authored;
    count(row);
    return row;
  }
  // One line of a section, in the score's inspector (docs/STUDIO-REDESIGN.md, "A line of words"): the same rows,
  // counts, checks and apply as the section's own editor; the nodes are kept, so typing survives a redraw.
  function line(view, sectionId, lineIndex, anchor) {
    const s = (view.composition?.sections || []).find((x) => x.id === sectionId);
    const p = s?.phrases?.[lineIndex];
    if (!s || !p?.lyric_path) return false;
    capture();
    let section = sections.get(s.id);
    if (!section) { section = makeSection(s); sections.set(s.id, section); }
    section.label = s.label;
    const row = rowFor(section, p, lineIndex, s.label);
    section.save.textContent = "Use this line";
    const hint = section.details.querySelector(".hint");
    anchor.append(row.wrap, section.save.parentNode, section.status, hint);
    if (focus?.path === p.lyric_path) { row.input.focus({preventScroll: true}); row.input.setSelectionRange(focus.start, focus.end); focus = null; }
    return true;
  }
  function decorate(view, parent) {
    for (const s of view.composition?.sections || []) {
      const phrases = s.phrases.filter((p) => p.lyric_path);
      const anchor = parent.querySelector(`#sec-${s.index}`);
      if (!anchor || !phrases.length) continue;
      let section = sections.get(s.id);
      if (!section) { section = makeSection(s); sections.set(s.id, section); }
      section.label = s.label;
      section.summary.textContent = phrases.some((p) => p.authored) ? "Edit your original lines" : "Write your own lines";
      for (const [index, p] of phrases.entries()) rowFor(section, p, index, s.label);
      // Reuse the nodes so asynchronous option responses never discard typing.
      anchor.append(section.details);
    }
    if (focus) {
      const input = [...parent.querySelectorAll("textarea[data-lyric-path]")].find((item) => item.dataset.lyricPath === focus.path);
      if (input) { input.focus({preventScroll: true}); input.setSelectionRange(focus.start, focus.end); }
      focus = null;
    }
  }
  window.SongbirdAuthor = {capture, decorate, line};
})();
