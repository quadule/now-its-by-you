// Help, on demand: the Help dialog (the whole studio in plain words) and a walk of four steps,
// each pointing at the one thing it names.
// No dependencies.
"use strict";

(() => {
  // where the song is made: this computer, or on the static site (made on the device) whatever the device is
  const HERE = typeof document !== "undefined" && document.querySelector('meta[name="studio-render"][content="device"]')
    ? "on this device" : "on this computer";
  const DEVICE = HERE === "on this device";
  // hear it, change something in the transport, select a section, export it. Each step says what is true where it
  // is shown: on the published version or on your own, on a wide screen or a narrow one.
  const steps = () => {
    const published = !!window.StudioBridge?.snapshot?.().start?.published;
    const narrow = typeof matchMedia === "function" && matchMedia("(max-width: 620px)").matches;
    const what = published ? "This is the song as it was published."
      : `This is your version of the song, made today ${HERE}.`;
    const how = narrow ? "Tap the song's name beside \u25B6 to choose the sketch, at once, or sung, the real thing."
      : "Sketch plays at once; Sung makes the real thing.";
    const own = published ? " \u201CHear your machine's version\u201D at the top makes yours." : "";
    return [
      { target: "tPlay", text: `${what} Start here: hear it. ${how}${own}` },
      { target: "transport", text: "Change something in the bar at the top: the tempo and the key. Undo takes anything back." },
      { target: "page", view: "page", text: "Select a section by its name (or its region in Arrange): the column beside it says what it is, why the program chose it, and how to change it." },
      { target: "recordNow", text: DEVICE
        ? "When you're done, export it. The file plays in any music player and contains the program, so anyone can make the next version from it. Export also has a link to share, the MIDI and the piano page; Tools brings things in."
        : "When you're done, export it. The file plays in any music player and contains the program, so anyone can make the next version. Export also has the MIDI, the parts and the piano page; Tools brings things in." },
    ];
  };
  let STEPS = steps();
  const $ = (id) => document.getElementById(id);
  let step = -1, shared = false;

  function show(index) {
    document.querySelectorAll(".tour-focus").forEach((el) => el.classList.remove("tour-focus"));
    if (index === 0) STEPS = steps();  // as the page is now
    step = index;
    const tour = $("tour");
    if (index < 0 || index >= STEPS.length) {
      tour.hidden = true;
      return;
    }
    const { target, view } = STEPS[index];
    if (view) window.SongbirdScore?.showView?.(view);  // what the step points at, shown
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
