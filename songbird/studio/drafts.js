// Portable studio drafts: just the song's identity and an undoable map of choices.
// No dependencies, audio blobs, or executable content travel in a draft.
"use strict";

(() => {
  const MAX_BYTES = 512 * 1024;
  const FORMAT = "songbird-studio-draft";
  let reading = false;

  function bridge() { return window.StudioBridge; }
  function notify(message) { bridge()?.toast(message); }

  function readDraft(text, song) {
    if (new TextEncoder().encode(text).length > MAX_BYTES) throw new Error("This draft is too large (maximum 512 KB).");
    let draft;
    try { draft = JSON.parse(text); } catch (_) { throw new Error("Choose a Songbird draft JSON file."); }
    if (!draft || draft.format !== FORMAT || draft.version !== 1) throw new Error("This isn't a supported Songbird draft.");
    if (draft.song !== song) throw new Error("This draft belongs to a different song. Open that song's studio first.");
    if (!draft.edits || typeof draft.edits !== "object" || Array.isArray(draft.edits)) throw new Error("This draft has no map of song choices.");
    if (Object.keys(draft.edits).length > 2048) throw new Error("This draft has too many choices.");
    for (const key of Object.keys(draft.edits)) {
      if (key === "__proto__" || key === "constructor" || key === "prototype") throw new Error("This draft contains an invalid choice.");
    }
    return draft.edits;
  }

  function download() {
    const snapshot = bridge()?.snapshot();
    if (!snapshot?.start?.song_digest) return notify("Wait for your song to finish opening.");
    const draft = {
      format: FORMAT, version: 1, title: snapshot.start.title,
      song: snapshot.start.song_digest, edits: snapshot.edits,
    };
    const blob = new Blob([JSON.stringify(draft, null, 2) + "\n"], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${snapshot.start.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "song"}.songbird.json`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify("Draft saved. Open it in this song's studio to keep editing.");
  }

  async function upload(event) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file || reading) return;
    reading = true;
    try {
      const snapshot = bridge()?.snapshot();
      if (!snapshot?.start?.song_digest) throw new Error("Wait for your song to finish opening.");
      if (file.size > MAX_BYTES) throw new Error("This draft is too large (maximum 512 KB).");
      const edits = readDraft(await file.text(), snapshot.start.song_digest);
      // Validate on the same path as an ordinary edit before replacing a draft.
      const response = await fetch("/api/song", {
        method: "POST", headers: {"Content-Type": "application/json", "X-Studio": document.querySelector('meta[name="studio-token"]').content},
        body: JSON.stringify({edits}),
      });
      if (!response.ok) throw new Error("The studio couldn't open this draft. Your current work is still here.");
      const view = await response.json();
      if (view.problems?.length) throw new Error(`This draft needs a correction: ${view.problems[0].why}. Your current work is still here.`);
      // If edits changed during validation, never overwrite the newer work.
      if (JSON.stringify(bridge().snapshot().edits) !== JSON.stringify(snapshot.edits)) throw new Error("Your song changed while the draft opened. Open the draft again when you're ready.");
      bridge().replaceEdits(edits);
      notify("Draft opened. Undo returns to your previous choices.");
    } catch (error) { notify(error.message); }
    finally { reading = false; input.value = ""; }
  }

  document.getElementById("saveDraft")?.addEventListener("click", download);
  document.getElementById("openDraft")?.addEventListener("click", () => document.getElementById("draftFile").click());
  document.getElementById("draftFile")?.addEventListener("change", upload);
  // The parser is kept independently testable without browser libraries.
  if (typeof module !== "undefined" && module.exports) module.exports = {readDraft};
})();
