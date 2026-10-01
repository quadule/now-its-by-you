// Files for a musician's own tools: the version on the page as MIDI (every part, the words as lyrics, the
// chords, the tempo, key and sections), or every part rendered alone (stems) with the MIDI, zipped.
// songbird/studio.py (Studio.export) makes them; nothing leaves this computer. Plain JavaScript, no libraries.
"use strict";

(() => {
  const TOKEN = document.querySelector('meta[name="studio-token"]')?.content || "";
  const busy = { midi: false, stems: false };
  const $ = (id) => document.getElementById(id);
  const bridge = () => window.StudioBridge || {};

  async function ask(path, body) {
    const options = body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json", "X-Studio": TOKEN }, body: JSON.stringify(body),
    };
    const r = await fetch(path, options);
    let data;
    try { data = await r.json(); } catch (_) { data = { error: r.statusText }; }
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  }

  function save(url, name = "") {  // name: a file made on the device, a Blob with no address to name it
    const link = document.createElement("a");
    link.href = url;
    link.download = name || new URL(url, location.href).searchParams.get("name") || "";
    document.body.append(link);
    link.click();
    link.remove();
  }

  function say(text) {
    const note = $("exportNote");
    if (note) note.textContent = text;
  }

  async function exportFile(what) {
    if (busy[what]) return;
    const button = $(what === "midi" ? "exportMidi" : "exportStems");
    busy[what] = true;
    if (button) button.disabled = true;
    const edits = bridge().getEdits ? bridge().getEdits() : {};
    try {
      say(what === "midi" ? "Writing the MIDI file…" : "Playing every part alone: about as long as making the whole song…");
      let job = await ask("/api/export", { edits, what });
      const url = job.download || job.url;
      while (job.state === "queued" || job.state === "running") {
        const ahead = job.state === "queued" && job.ahead ? ` (${job.ahead} ahead of it)` : "";
        say(`Making the stems${ahead}: ${job.stage || "starting"}… ${Math.round((job.progress || 0) * 100)}%`);
        await new Promise((resolve) => setTimeout(resolve, 700));
        job = await ask(`/api/job/${job.id}`);
      }
      if (job.state === "failed") throw new Error(job.error || "it failed");
      save(job.url && (job.url.startsWith("/export/") || job.url.startsWith("blob:")) ? job.url : url, job.name);
      say(what === "midi"
        ? "Saved: every part, the words and the chords, with the tempo, key and sections. Bar 1 starts just before the first note."
        : "Saved: each part alone and dry, with the MIDI file and a note on them. They all start at bar 1, so they line up.");
    } catch (e) {
      say(`Couldn't make it: ${e.message}`);
      bridge().toast?.(`Couldn't make it: ${e.message}`);
    } finally {
      busy[what] = false;
      if (button) button.disabled = false;
    }
  }

  function reveal() {
    const panel = $("exportPanel");
    const details = panel?.closest("details");
    if (details) details.open = true;
    panel?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function wire() {
    $("exportMidi")?.addEventListener("click", () => exportFile("midi"));
    $("exportStems")?.addEventListener("click", () => exportFile("stems"));
    $("toExport")?.addEventListener("click", reveal);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();
  window.SongbirdExport = { exportFile, reveal };
})();
