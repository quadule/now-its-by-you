// Learn it at the piano: the piano page (songbird/studio/piano/, docs/PIANO.md) in a tab of its own, teaching the
// version on this page, a person's key, tempo, chords, words, form and tune among it. The studio lays the score
// again for it (Studio.piano: no render, at once) and keeps it under its own address, so the tab can be reloaded.
// Pressing it again after a change sends the same tab the new version. Plain JavaScript, no libraries.
"use strict";

(() => {
  const TOKEN = document.querySelector('meta[name="studio-token"]')?.content || "";
  const TAB = "songbird-piano";
  const bridge = () => window.StudioBridge || {};
  let busy = false;

  function say(text, link) {
    for (const note of document.querySelectorAll("[data-piano-note]")) {
      note.replaceChildren(text);
      if (link) {
        const a = document.createElement("a");
        a.href = link; a.target = TAB; a.rel = "opener"; a.textContent = "open the piano page";
        note.append(" ", a, ".");
      }
    }
  }

  async function learn() {
    if (busy) return;
    busy = true;
    // the tab first, while the press still counts (browsers let a page open one only then), then where it goes
    let tab = null;
    try { tab = window.open("", TAB); } catch (_) { tab = null; }
    say("Laying out your version for the piano…");
    try {
      const r = await fetch("/api/piano", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Studio": TOKEN },
        body: JSON.stringify({ edits: bridge().getEdits ? bridge().getEdits() : {} }),
      });
      let made;
      try { made = await r.json(); } catch (_) { made = { error: r.statusText }; }
      if (!r.ok) throw new Error(made.error || r.statusText);
      if (tab && !tab.closed) {
        tab.location.href = made.url;
        try { tab.focus(); } catch (_) { /* the browser decides */ }
        say("Opened in its own tab. Changed something? Press it again and the tab follows.");
      } else {
        say("Your browser kept the tab from opening:", made.url);
      }
    } catch (e) {
      if (tab && !tab.closed && tab.location.href === "about:blank") tab.close();
      say(`Couldn't lay it out: ${e.message}`);
      bridge().toast?.(`Couldn't lay it out for the piano: ${e.message}`);
    } finally {
      busy = false;
    }
  }

  function wire() {
    for (const button of document.querySelectorAll("[data-learn-piano]")) button.addEventListener("click", learn);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
  window.SongbirdLearn = { learn };
})();
