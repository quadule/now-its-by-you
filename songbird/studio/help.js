// Help, on demand: the Help dialog (the whole studio in plain words) and a first-visit walk of four steps,
// each pointing at the one thing it names. Each area's own "What is this?" is plain HTML (<details>).
// No dependencies; what a person has seen is kept in this browser only.
"use strict";

(() => {
  const SEEN = "songbird-studio-tour-seen";
  const CLASSIC = [
    { target: "hearAll", text: "This is your version of the song, made today on this computer. Start here: hear it." },
    { target: "simpleChanges", text: "Change something simple: the key, the scale, the tempo, or a new performance. Undo takes anything back." },
    { target: "studioTabs", text: "Go deeper when you like: the words, the tune, the sound, and how the song changes with time and between computers." },
    { target: "toFinish", text: "When it's yours, record it: one file that plays anywhere and carries the song on. Help is always at the top." },
  ];
  // the score (index.html): hear it, change something in the transport, select a section, record it
  const SCORE = [
    { target: "tPlay", text: "This is your version of the song, made today on this computer. Start here: hear it. Sketch plays at once; Sung makes the real thing." },
    { target: "transport", text: "Change something in the bar at the top: the tempo, the key, a new performance. Undo takes anything back." },
    { target: "page", text: "Select a section by its name (or its region in Arrange): the column beside it says what it is, why the program chose it, and how to change it." },
    { target: "recordNow", text: "When it's yours, record it: one file that plays anywhere and carries the song on. Tools has the MIDI, the parts, the piano page, and ways to bring things in." },
  ];
  const STEPS = document.getElementById("transport") ? SCORE : CLASSIC;
  const $ = (id) => document.getElementById(id);
  let step = -1, shared = false;

  function seen() {
    try { return localStorage.getItem(SEEN) === "1"; } catch (e) { return true; }  // no storage: don't nag
  }
  function remember() {
    try { localStorage.setItem(SEEN, "1"); } catch (e) { /* this visit only */ }
  }

  function show(index) {
    document.querySelectorAll(".tour-focus").forEach((el) => el.classList.remove("tour-focus"));
    step = index;
    const tour = $("tour");
    if (index < 0 || index >= STEPS.length) {
      tour.hidden = true;
      remember();
      return;
    }
    const { target } = STEPS[index];
    // shared for a preview, the version is the serving computer's, not the visitor's
    const text = index === 0 && shared ? STEPS[0].text.replace("on this computer", "on the computer serving this studio") : STEPS[index].text;
    const el = $(target);
    if (el) {
      el.classList.add("tour-focus");
      el.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    $("tourStep").textContent = `${index + 1} of ${STEPS.length}`;
    $("tourText").textContent = text;
    $("tourBack").hidden = index === 0;
    $("tourNext").textContent = index === STEPS.length - 1 ? "Done" : "Next";
    tour.hidden = false;
    $("tourNext").focus({ preventScroll: true });
  }

  function openHelp() {
    const dialog = $("help");
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  $("helpOpen").addEventListener("click", openHelp);
  $("tourAgain").addEventListener("click", () => {
    const dialog = $("help");
    if (typeof dialog.close === "function") dialog.close(); else dialog.removeAttribute("open");
    show(0);
  });
  $("tourNext").addEventListener("click", () => show(step + 1));
  $("tourBack").addEventListener("click", () => show(step - 1));
  $("tourSkip").addEventListener("click", () => show(-1));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("tour").hidden) show(-1);
    // "?" opens help, outside text fields
    const t = event.target;
    if (event.key === "?" && !(t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName))) openHelp();
  });
  // A first visit gets the walk once the song is on the page; a link into a particular view doesn't.
  document.addEventListener("studio:ready", (event) => {
    const hash = event.detail?.hash || {};
    shared = !!event.detail?.shared;
    if (seen() || hash.scroll || hash.choose || hash.workspace || hash.view || hash.sel) return;
    setTimeout(() => { if (!$("help").open) show(0); }, 500);
  });
  window.SongbirdHelp = { open: openHelp, tour: () => show(0) };
})();
