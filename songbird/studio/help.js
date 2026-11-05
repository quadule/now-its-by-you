// Help, on demand: the Help dialog (the whole studio in plain words) and a walk of four steps,
// each pointing at the one thing it names. Each area's own "What is this?" is plain HTML (<details>).
// No dependencies.
"use strict";

(() => {
  // where the song is made: this computer, or on the static site (made on the device) whatever the device is
  const HERE = typeof document !== "undefined" && document.querySelector('meta[name="studio-render"][content="device"]')
    ? "on this device" : "on this computer";
  const CLASSIC = [
    { target: "hearAll", text: `This is your version of the song, made today ${HERE}. Start here: hear it.` },
    { target: "simpleChanges", text: "Change something simple: the key, the scale, the tempo, or a new performance. Undo takes anything back." },
    { target: "studioTabs", text: "Go deeper when you like: the words, the tune, the sound, and how the song changes with time and between computers." },
    { target: "toFinish", text: "When you're done, export it. The file plays in any music player and contains the program, so anyone can make the next version. Help is always at the top." },
  ];
  // the score (index.html): hear it, change something in the transport, select a section, record it
  const SCORE = [
    { target: "tPlay", text: `This is your version of the song, made today ${HERE}. Start here: hear it. Sketch plays at once; Sung makes the real thing.` },
    { target: "transport", text: "Change something in the bar at the top: the tempo, the key, a new performance. Undo takes anything back." },
    { target: "page", text: "Select a section by its name (or its region in Arrange): the column beside it says what it is, why the program chose it, and how to change it." },
    { target: "recordNow", text: "When you're done, export it. The file plays in any music player and contains the program, so anyone can make the next version. Tools has the MIDI, the parts, the piano page, and ways to bring things in." },
  ];
  const STEPS = document.getElementById("transport") ? SCORE : CLASSIC;
  const $ = (id) => document.getElementById(id);
  let step = -1, shared = false;

  function show(index) {
    document.querySelectorAll(".tour-focus").forEach((el) => el.classList.remove("tour-focus"));
    step = index;
    const tour = $("tour");
    if (index < 0 || index >= STEPS.length) {
      tour.hidden = true;
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
  // The walk opens from Help (tourAgain).
  document.addEventListener("studio:ready", (event) => {
    shared = !!event.detail?.shared;
  });
  window.SongbirdHelp = { open: openHelp, tour: () => show(0) };
})();
