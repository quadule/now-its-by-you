// Original lyrics use the same compact, portable edits as the musical workbench.
"use strict";

(() => {
  const sections = new Map();
  let focus = null;
  const bridge = () => window.StudioBridge;
  // what a line's field says on hover: the rest of how a line is written (the column says only the count's rule)
  const STARS = "A word between stars, like *heart*, is the one the line leans on: the singer gives it a little more. " +
    "A word said two ways, like bass, shows its ways under the line: choose one. To say any word your own way, " +
    "write how it sounds in braces after it, like bass{base}, or in ARPAbet, like bass{B.EY1.S}. " +
    "The singer checks the syllables and the pronunciation; the story and the rhyme are yours.";
  // A word's say in braces, bass{fish} (songbird/heteronyms.py): never a syllable, never shown.
  const SAY = /\{[^{}]*\}/g;
  const bare = (text) => String(text).replace(SAY, "");
  const syllables = (text) => bare(text).trim().split(/[\s-]+/u).filter(Boolean).length;

  // Words said two ways: the rules of songbird/heteronyms.py over the table the view sends (view.composition.say),
  // so a line shows its choices as it's typed. choose(), choices() and decide() are the Python's, line for line
  // (tests/studio_author.test.cjs reads the same lines as tests/test_heteronyms.py).
  let table = null, past = new Set(), notPast = new Set();
  function useTable(say) {
    if (!say || say === table) return;
    table = say;
    past = new Set(say.past);
    notPast = new Set(say.not_past);
  }
  const clean = (w) => w.toLowerCase().replace(/’/g, "'").replace(/[^a-z']/g, "").replace(/^'+|'+$/g, "");
  function wordsOf(line) {
    const parts = String(line).split(/(\s+)/), words = [];
    parts.forEach((token, at) => {
      if (!token || /^\s+$/u.test(token)) return;
      const shown = bare(token).replace(/\*/g, "");
      const word = clean(shown.replace(/-/g, ""));
      if (!word) { if (words.length) words[words.length - 1].stop = true; return; }
      const letters = shown.replace(/^["'“‘(]+/u, "");
      words.push({token, at, word, capital: /^\p{Lu}/u.test(letters),
        stop: /[,.;:!?—–)"”]$/u.test(shown.replace(/['’]+$/u, ""))});
    });
    return {parts, words};
  }
  const isPast = (w) => past.has(w) || (w.length >= 5 && w.endsWith("ed") && !w.endsWith("eed") && !notPast.has(w));
  function matches(rule, words, i) {
    const w = words[i];
    if (rule.before && !rule.before.some((entry) => {
      const want = entry.split(" "), k = want.length, got = words.slice(i - k, i);
      return i - k >= 0 && got.every((x, j) => x.word === want[j]) && !got.some((x) => x.stop);
    })) return false;
    if (rule.after && (i + 1 >= words.length || w.stop || !rule.after.includes(words[i + 1].word))) return false;
    if (rule.near && !words.some((x, j) => j !== i && rule.near.includes(x.word))) return false;
    if (rule.end && !(w.stop || i === words.length - 1)) return false;
    if (rule.past && !words.some((x, j) => j !== i && isPast(x.word))) return false;
    if (rule.capital && !(w.capital && i > 0)) return false;
    return true;
  }
  function choose(words, i) {
    const entry = table?.words?.[words[i].word];
    if (!entry) return null;
    const rule = entry.rules.find((r) => matches(r, words, i));
    return rule ? rule.sense : entry.senses[0].name;
  }
  const sayOf = (token) => /\{([^{}]*)\}/.exec(token)?.[1] ?? null;
  function choices(line) {
    const {words} = wordsOf(line), out = [];
    words.forEach((w, i) => {
      if (!table?.words?.[w.word]) return;
      const own = sayOf(w.token);
      out.push({index: i, word: w.word, chosen: own ?? choose(words, i), by: own === null ? "rules" : "you"});
    });
    return out;
  }
  function withSay(token, say) {
    const m = /^(.*?[A-Za-z0-9'’])([^A-Za-z0-9'’]*)$/u.exec(token);
    return m ? `${m[1]}{${say}}${m[2]}` : `${token}{${say}}`;
  }
  function decide(line) {
    const {words} = wordsOf(line);
    let k = 0;  // the token's place among the words (a dash standing alone isn't one)
    return String(line).split(/\s+/u).filter(Boolean).map((token) => {
      if (!clean(bare(token).replace(/\*/g, "").replace(/-/g, ""))) return token;
      const i = k++;
      const sense = sayOf(token) === null ? choose(words, i) : null;
      return sense === null ? token : withSay(token, sense);
    }).join(" ");
  }
  // The ways each word said two ways can go, under its line: "bass: low note · fish". The line as it's sung (the
  // view's, for the text in the song) or as typed (the rules here); a choice writes its say into the line.
  const WHY = {
    rules: "The singer chose this from the words around it. Choose the other to change it.",
    song: "As the song sings it. Choose the other to sing it that way in your line.",
    you: "Your choice, kept with the line in braces.",
  };
  function says(row) {
    if (!row.say) return;
    const text = row.input.value;
    const said = text === row.base && row.phrase.said ? row.phrase.said : choices(text);
    const groups = [];
    for (const c of said) {
      const entry = table?.words?.[c.word];
      if (!entry || entry.senses.length < 2) continue;
      const group = node("span", "say-word");
      group.title = c.by === "you" ? `${WHY.you} ${c.word}{${c.chosen}}` : WHY[c.by] || WHY.rules;
      group.append(node("span", "say-name", `${c.word}:`));
      entry.senses.forEach((s, k) => {
        if (k) group.append(node("span", "say-dot", "·"));
        const on = s.name === c.chosen;
        const chip = node("button", `chip${on ? " on" : ""}${on && c.by === "you" ? " you" : ""}`, s.label);
        chip.type = "button";
        chip.setAttribute("aria-pressed", String(on));
        chip.title = `Sung like “${s.like}”`;
        chip.addEventListener("click", () => pick(row, c.index, s.name));
        group.append(chip);
      });
      if (c.by === "you" && !entry.senses.some((s) => s.name === c.chosen)) group.append(node("span", "say-own", `your way: {${c.chosen}}`));
      groups.push(group);
    }
    row.say.replaceChildren(...groups);
    // on the score's Page, only for a line a person has written: the song's lines are said as the song has them
    row.say.hidden = !groups.length || (!!row.section.whole && text === row.base && !row.phrase.authored);
  }
  function pick(row, index, name) {
    const {parts, words} = wordsOf(row.input.value);
    const w = words[index];
    if (!w) return;
    parts[w.at] = withSay(bare(w.token), name);
    row.input.value = parts.join("");
    count(row);
    row.section.status.textContent = row.section.whole ? "" : "Not in the song until you use it.";
    if (row.status) row.status.textContent = "Not in the song until you use it.";
  }
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
    row.count.textContent = `${n} / ${row.phrase.syllable_count}`;
    row.count.append(node("span", "unit", " syllables"));  // (the word goes where there's no room for it)
    row.count.classList.toggle("is-valid", n === row.phrase.syllable_count);
    row.input.setAttribute("aria-invalid", String(n !== row.phrase.syllable_count));
    row.input.classList.toggle("is-dirty", row.input.value !== row.base);
    says(row);
  }
  // `row`: one line used on its own (the score's column): its refusal, its status and what follows are its own.
  // A section's checks run one after another (a line used while the one before is checked waits its turn), each on
  // the song as the one before left it.
  function apply(section, patch, row = null, done = null) {
    if (!section.busy) section.chain = check(section, patch, row, done);
    else if (row) {
      row.status.textContent = "Waiting for the line before…";
      section.chain = section.chain.then(() => check(section, patch, row, done));
    }
    return section.chain;
  }
  async function check(section, patch, row, done) {
    const status = row?.status || section.status, save = row?.use || section.save;
    const snapshot = bridge().snapshot();
    const next = {...snapshot.edits, ...patch};
    const paths = new Set(Object.keys(patch));
    const submitted = new Map([...section.rows.values()].map((row) => [row.phrase.lyric_path, row.input.value]));
    section.busy = true;
    save.disabled = true;
    status.textContent = "Checking…";
    try {
      const response = await fetch("/api/song", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Studio": document.querySelector('meta[name="studio-token"]').content},
        body: JSON.stringify({edits: next}),
      });
      const view = await response.json();
      if (!response.ok) throw new Error(view.error || "The studio couldn't check these lines. Try again.");
      const problems = (view.problems || []).filter((problem) => paths.has(problem.path));
      if (problems.length) throw new Error(problems.map((p) => `Line ${Number(p.path.split(".").at(-1)) + 1}: ${p.why}`).join(" "));
      if (bridge().snapshot().revision !== snapshot.revision) throw new Error("The song changed while this was checked: use it again.");
      bridge().replaceEdits(next, `Write ${section.label.toLowerCase()}`);
      for (const row of section.rows.values()) if (paths.has(row.phrase.lyric_path)) {
        // Typing can continue while validation runs. Only the submitted text
        // becomes the base; newer typing must remain an unapplied draft.
        row.base = patch[row.phrase.lyric_path] ?? submitted.get(row.phrase.lyric_path);
      }
      status.textContent = row ? "In your song." : "In your song. Hear the section to listen.";
      bridge().toast(row ? "Your line is in the song. Undo takes it back." : "Your words are in the song. Undo takes them back.");
      done?.();
    } catch (error) { status.textContent = error.message; }
    finally { section.busy = false; save.disabled = false; }
  }
  function makeSection(s) {
    const details = node("details", "lyric-author");
    details.dataset.authorSection = s.id;
    const summary = node("summary", "", "Write your own lines");
    const hint = node("p", "hint", "One syllable a note; split longer words with hyphens (car-ry).");
    hint.title = STARS;
    const lines = node("div", "author-lines");
    const status = node("p", "author-status");
    status.setAttribute("role", "status");
    const section = {details, summary, lines, rows: new Map(), label: s.label, status, hint: null, busy: false};
    section.save = button("Use these lines", () => {
      const changed = [...section.rows.values()].filter((row) => row.input.value !== row.base);
      if (!changed.length) { status.textContent = "Already in your song."; return; }
      const wrong = changed.filter((row) => syllables(row.input.value) !== row.phrase.syllable_count);
      if (wrong.length) {
        status.textContent = "Each line needs its count of syllables.";
        wrong[0].input.focus();
        return;
      }
      apply(section, Object.fromEntries(changed.map((row) => [row.phrase.lyric_path, row.input.value])));
    });
    const discard = button("Discard typing", () => {
      for (const row of section.rows.values()) { row.input.value = row.base; count(row); }
      status.textContent = "";
    });
    const actions = node("div", "author-actions");
    actions.append(section.save, discard);
    details.append(summary, hint, lines, actions, status);
    section.hint = hint;  // kept: the score's line state moves it out of the details
    // how a line is written, shown beside the fields (the score's Page): an example of each mark and what it does
    const legend = node("p", "author-legend");
    legend.append(node("span", "", "One syllable a note."));
    for (const [mark, does] of [["car-ry", "two notes"], ["*heart*", "leaned on"], ["bass{base}", "said like “base”"]]) {
      const item = node("span");
      item.append(node("code", "", mark), ` ${does}`);
      legend.append(item);
    }
    legend.title = STARS;
    section.legend = legend;
    section.actions = actions;
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
      restore.title = "Your line let go: the song's own words sung here again";
      head.append(name, tally, restore);
      const say = node("div", "author-say");  // its words said two ways, and which way
      say.setAttribute("aria-label", "Words said two ways");
      wrap.append(head, input, say);
      row = {wrap, input, count: tally, restore, say, section, base: p.lyric_text, phrase: p};
      input.value = p.lyric_text;
      input.title = STARS;
      input.addEventListener("input", () => { count(row); section.status.textContent = section.whole ? "" : "Not in the song until you use it."; });
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
  // A line's own Use and Discard, for the score's column: one line at a time, as the column is (a draft typed in
  // another line stays a draft there, and a refusal of this one refuses only this one)
  function lineActions(section, row, options) {
    if (!row.use) {
      row.use = button("Use this line", () => {
        const text = row.input.value;
        if (text === row.base) { row.status.textContent = "Already in your song."; return; }
        if (syllables(text) !== row.phrase.syllable_count) {
          row.status.textContent = `This line needs ${row.phrase.syllable_count} syllables; it has ${syllables(text)}.`;
          row.input.focus();
          return;
        }
        apply(section, {[row.phrase.lyric_path]: text}, row, () => row.next?.());
      });
      row.use.className = "btn";
      const discard = button("Discard typing", () => { row.input.value = row.base; count(row); row.status.textContent = ""; });
      row.actions = node("div", "author-actions");
      row.actions.append(row.use, discard);
      row.status = node("p", "author-status");
      row.status.setAttribute("role", "status");
      row.input.addEventListener("input", () => { row.status.textContent = "Not in the song until you use it."; });
    }
    row.next = options.next || null;  // what follows a line used: the score's next line to write
    return row;
  }
  // One line of a section, in the score's inspector (docs/notes/STUDIO-REDESIGN.md, "A line of words"): the same rows,
  // counts and checks as the section's own editor, one line used at a time; the nodes are kept, so typing survives a
  // redraw.
  function line(view, sectionId, lineIndex, anchor, options = {}) {
    const s = (view.composition?.sections || []).find((x) => x.id === sectionId);
    const p = s?.phrases?.[lineIndex];
    if (!s || !p?.lyric_path) return false;
    useTable(view.composition?.say);
    capture();
    let section = sections.get(s.id);
    if (!section) { section = makeSection(s); sections.set(s.id, section); }
    section.label = s.label;
    const row = rowFor(section, p, lineIndex, s.label);
    lineActions(section, row, options);
    anchor.append(row.wrap, row.actions, row.status, section.hint);
    if (focus?.path === p.lyric_path) { row.input.focus({preventScroll: true}); row.input.setSelectionRange(focus.start, focus.end); focus = null; }
    return true;
  }
  // A section's lines, all of them, where the section stands on the score's Page: a field for each line, the legend
  // of how a line is written, and Use and Discard for the lot. The nodes are kept, so typing survives a redraw.
  function whole(view, sectionId, anchor) {
    const s = (view.composition?.sections || []).find((x) => x.id === sectionId);
    if (!s || !s.phrases.some((p) => p.lyric_path)) return false;
    useTable(view.composition?.say);
    capture();
    let section = sections.get(s.id);
    if (!section) { section = makeSection(s); sections.set(s.id, section); }
    section.label = s.label;
    section.whole = true;  // the Page's Done uses the lines (finish): no button of its own, nothing to say until then
    // the lines of the words sung here now: a field kept for other words (another verse chosen) goes
    const sung = new Set(s.phrases.map((p) => p.lyric_path).filter(Boolean));
    for (const [path, row] of section.rows) if (!sung.has(path)) { row.wrap.remove(); section.rows.delete(path); }
    for (const [index, p] of s.phrases.entries()) {
      if (!p.lyric_path) continue;
      const row = rowFor(section, p, index, s.label);
      section.lines.append(row.wrap);
      if (!row.fits) {  // a field as tall as its line
        row.fits = () => { row.input.style.height = "auto"; row.input.style.height = `${row.input.scrollHeight}px`; };
        row.input.rows = 1;
        row.input.addEventListener("input", row.fits);
      }
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(row.fits);
    }
    anchor.append(section.lines, section.legend, section.status);
    if (focus) {
      const input = [...section.rows.values()].map((row) => row.input).find((item) => item.dataset.lyricPath === focus.path);
      if (input) { input.focus({preventScroll: true}); input.setSelectionRange(focus.start, focus.end); }
      focus = null;
    }
    return true;
  }
  // The Page's Done: what was typed in a section's fields goes into the song (true), or its status says why it
  // can't and the first such line is focused (false). With nothing typed there is nothing to do.
  const typed = (section) => [...(section?.rows.values() || [])].filter((row) => row.input.value !== row.base);
  function finish(sectionId) {
    const section = sections.get(sectionId), changed = typed(section);
    if (!changed.length) return Promise.resolve(true);
    const wrong = changed.filter((row) => syllables(row.input.value) !== row.phrase.syllable_count);
    if (wrong.length) {
      section.status.textContent = "Each line needs its count of syllables.";
      wrong[0].input.focus();
      return Promise.resolve(false);
    }
    let used = false;
    return Promise.resolve(apply(section, Object.fromEntries(changed.map((row) => [row.phrase.lyric_path, row.input.value])), null, () => { used = true; }))
      .then(() => { if (used) section.status.textContent = ""; return used; });
  }
  const dirty = (sectionId) => typed(sections.get(sectionId)).length > 0;
  function discard(sectionId) {
    const section = sections.get(sectionId);
    if (!section) return;
    for (const row of section.rows.values()) { row.input.value = row.base; count(row); }
    section.status.textContent = "";
  }
  function decorate(view, parent) {
    useTable(view.composition?.say);
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
  window.SongbirdAuthor = {capture, decorate, line, whole, finish, dirty, discard, say: {useTable, choices, decide, bare, syllables}};
})();
