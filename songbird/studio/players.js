// The sketch's players, and sending them to a musician's own instruments (Web MIDI out), in step with Play sketch.
//
// Every player of the sketch (the tune, its chords and bass, and every part of the band, the lineage voices
// among them) can sound here, go to a channel of a MIDI output (a synth, a DAW), or sit out. The band's parts
// come from the studio at once (Studio.players: the score the render sings, as the MIDI file lays it out, so the
// channels and General MIDI programs are the file's: songbird/midi.py), in beats of the song's grid, so they play
// at the sketch's tempo under its tune. Notes go out a moment ahead (a lookahead scheduler, timestamped), each
// note-on's note-off is kept until it is sent, and a stop sends them all at once; Panic silences every channel.
// Without Web MIDI (Safari), or with it refused, everything plays here and nothing breaks.
//
// composer.js asks route(player) for the tune, chords and bass it plays itself, hands start() everything it
// wants sent, and calls stop(). Plain JavaScript, no libraries.
"use strict";

(() => {
  const TOKEN = (typeof document !== "undefined" && document.querySelector?.('meta[name="studio-token"]')?.content) || "";
  const STORE = "songbird.studio.players";
  const AHEAD = 0.2; // seconds of notes sent ahead of time
  const TICK = 25; // ms between looks ahead
  const EARLY = 0.1; // beats: how far ahead of its beat a band's note may be played and still count as on it
  const OWN = [ // the sketch's own players, played by composer.js
    { part: "tune", name: "Tune" }, { part: "chords", name: "Chords" }, { part: "bass-sketch", name: "Bass (the sketch's)" },
  ];
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));

  // ------------------------------------------------------------------ pure parts: when each note sounds

  // The notes of a playback (sorted by `t`, seconds from the start of its cycle) that begin in [from, to), seconds
  // from the playback's start, across cycles when it loops: [{ note, at }] in order.
  function occurrences(notes, cycle, loop, from, to) {
    const out = [];
    if (!(to > from) || !(cycle > 0)) return out;
    const first = Math.max(0, Math.floor(from / cycle)), last = loop ? Math.floor(to / cycle) : 0;
    for (let c = first; c <= last; c++) {
      const lo = from - c * cycle, hi = to - c * cycle;
      let i = 0, j = notes.length;
      while (i < j) { const m = (i + j) >> 1; if (notes[m].t < lo) i = m + 1; else j = m; } // the first at or after lo
      for (; i < notes.length && notes[i].t < hi; i++) {
        if (notes[i].t >= 0 && notes[i].t < cycle) out.push({ note: notes[i], at: c * cycle + notes[i].t });
      }
    }
    return out;
  }
  const byTime = (a, b) => a.t - b.t;

  // The band's parts (Studio.players) within a playback: from `origin` for `span` beats, at `seconds` a beat, each
  // note's length kept inside the cycle (so nothing hangs over a loop's turn).
  function bandNotes(players, origin, span, seconds, routeOf) {
    const out = [], cycle = span * seconds;
    for (const p of players || []) {
      const route = routeOf(p.part);
      if (route === "off") continue;
      for (const [beat, length, key, vel] of p.notes) {
        // a player's small human timing may put a note a moment before the playback's first beat: it starts it
        if (beat < origin - EARLY || beat >= origin + span - EARLY) continue;
        const t = Math.max(0, (beat - origin) * seconds);
        out.push({ player: p.part, t, d: Math.max(0.03, Math.min(length * seconds, cycle - t - 0.005)), key, vel,
          drums: !!p.drums });
      }
    }
    return out;
  }

  // A scheduler for one playback: `notes` ({player, t, d, key, vel}); `send(bytes, when)` for MIDI (when in the
  // audio clock's seconds); `sound(note, when)` for this page; `routeOf(player)` "page", "off" or a channel 0-15.
  function scheduler({ notes, cycle, loop, started, send, sound, routeOf, now }) {
    const open = new Map(); // "channel:key" -> { on, off }: every note-on sent whose note-off isn't yet
    const used = new Set(); // channels a note went to
    let until = started, latest = started, list = notes.slice().sort(byTime);
    const self = {
      open, used,
      add(more) { list = list.concat(more).sort(byTime); },
      on(channel, key, vel, at, off) {
        const id = `${channel}:${key}`, prev = open.get(id);
        if (prev) { // the same key again before the last one ended: end that one just before
          send([0x80 | channel, key, 0], Math.max(prev.on + 0.001, at - 0.001));
          open.delete(id);
        }
        send([0x90 | channel, key, clamp(Math.round(vel), 1, 127)], at);
        open.set(id, { on: at, off: Math.max(off, at + 0.01) });
        used.add(channel);
        latest = Math.max(latest, at);
      },
      offsBefore(t) {
        const due = [...open.entries()].filter(([, n]) => n.off < t).sort((a, b) => a[1].off - b[1].off);
        for (const [id, n] of due) {
          const [channel, key] = id.split(":").map(Number);
          send([0x80 | channel, key, 0], n.off);
          open.delete(id);
        }
      },
      tick() {
        const t = now(), to = t + AHEAD;
        if (to <= until) return;
        for (const { note, at } of occurrences(list, cycle, loop(), until - started, to - started)) {
          const when = started + at, route = routeOf(note.player);
          if (route === "off") continue;
          if (route === "page") { if (when >= t - 0.01) sound(note, Math.max(t, when)); continue; }
          if (when < t - 0.05) continue; // too late to be in time: left out, not played late
          self.offsBefore(when + 1e-9); // what ends before (or as) this begins goes first, in time
          self.on(route, note.key, note.vel, when, when + note.d);
        }
        self.offsBefore(to);
        until = to;
      },
      // every note still sounding ends now (after its note-on, which may be a moment ahead), and each channel is
      // told so (all notes off, the sustain let go) for an instrument that missed one
      stop() {
        const t = now(), after = Math.max(t, latest + 0.002);
        for (const [id, n] of open) {
          const [channel, key] = id.split(":").map(Number);
          send([0x80 | channel, key, 0], Math.max(t, n.on + 0.001));
        }
        open.clear();
        for (const channel of used) { send([0xb0 | channel, 64, 0], after); send([0xb0 | channel, 123, 0], after); }
      },
    };
    return self;
  }

  // ------------------------------------------------------------------ settings, remembered in this browser only

  const set = { routes: {}, output: "", programs: true };
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || "{}");
    if (saved && typeof saved.routes === "object" && saved.routes) {
      for (const [k, v] of Object.entries(saved.routes)) {
        if (v === "page" || v === "off" || (Number.isInteger(v) && v >= 0 && v <= 15)) set.routes[k] = v;
      }
    }
    if (typeof saved.output === "string") set.output = saved.output;
    if (typeof saved.programs === "boolean") set.programs = saved.programs;
  } catch (_) { /* no storage here: the defaults */ }
  function save() {
    try { localStorage.setItem(STORE, JSON.stringify(set)); } catch (_) { /* a private window */ }
  }

  // ------------------------------------------------------------------ MIDI out
  const midi = { access: null, output: null, state: "idle", note: "" };
  const hasMidi = () => typeof navigator !== "undefined" && typeof navigator.requestMIDIAccess === "function";
  let band = null; // Studio.players, for the version `band.key`
  let bandAsked = null; // the key being fetched
  let viewKey = null;
  let playing = null; // { sched, timer, ctx, ... }

  // What a player does now: "off", "page", or a MIDI channel (0-15). A player sent to MIDI with no output to go
  // to plays here instead, so nothing falls silent when a device is unplugged.
  function routeOf(part) {
    const r = Object.prototype.hasOwnProperty.call(set.routes, part) ? set.routes[part] : defaultRoute(part);
    if (Number.isInteger(r)) return midi.output ? r : "page";
    return r;
  }
  function defaultRoute(part) { return OWN.some((p) => p.part === part) ? "page" : "off"; }
  // the channel each player has in the MIDI file (the sketch's bass takes the band's bass part's)
  function fileChannel(part) {
    if (part === "tune") return band?.tune?.channel ?? 0;
    if (part === "chords") return band?.chords?.channel ?? 15;
    if (part === "bass-sketch") {
      const bass = (band?.players || []).find((p) => p.part === "bass") || (band?.players || []).find((p) => /bass/.test(p.part));
      return bass ? bass.channel : 14;
    }
    return (band?.players || []).find((p) => p.part === part)?.channel ?? 0;
  }
  function program(part) {
    if (part === "tune") return band?.tune?.program ?? 52;
    if (part === "chords") return band?.chords?.program ?? 0;
    if (part === "bass-sketch") return 32;
    const p = (band?.players || []).find((q) => q.part === part);
    return p && !p.drums ? p.program : null;
  }
  // composer.js's question for its own players: "page", "midi" or "off"
  function route(player) {
    const part = player === "bass" ? "bass-sketch" : player;
    const r = routeOf(part);
    return Number.isInteger(r) ? "midi" : r;
  }

  function stamp(ctx, when) { // the audio clock's seconds as the MIDI clock's milliseconds, heard together
    const latency = (ctx && (ctx.outputLatency || ctx.baseLatency)) || 0;
    const base = typeof performance !== "undefined" ? performance.now() : Date.now();
    return base + Math.max(0, when - (ctx ? ctx.currentTime : 0) + latency) * 1000;
  }
  function sendTo(ctx) {
    return (bytes, when) => {
      if (!midi.output) return;
      try { midi.output.send(bytes, stamp(ctx, when)); } catch (e) { lost(e); }
    };
  }
  function lost(e) {
    midi.output = null;
    note(`The MIDI output stopped answering (${e && e.name ? e.name : "gone"}); the sketch plays here.`);
    paint();
  }

  async function connect(quiet) {
    if (!hasMidi()) {
      midi.state = "none";
      if (!quiet) note("This browser has no Web MIDI (Chrome, Edge and Firefox have it; Safari doesn't), so the sketch plays here.");
      paint();
      return;
    }
    midi.state = "asking";
    try {
      midi.access = await navigator.requestMIDIAccess({ sysex: false });
    } catch (e) {
      midi.state = "refused";
      if (!quiet) note(`The browser didn't allow MIDI (${e && e.name ? e.name : "refused"}). Allow it in the site's settings and press Connect again; until then the sketch plays here.`);
      paint();
      return;
    }
    midi.state = "on";
    midi.access.onstatechange = () => { choose(set.output, true); paint(); };
    choose(set.output, true);
    paint();
  }
  function outputs() { return midi.access ? [...midi.access.outputs.values()] : []; }
  function choose(id, quiet) {
    const found = id ? outputs().find((o) => o.id === id) || null : null;
    if (midi.output && midi.output !== found) silence(midi.output);
    midi.output = found;
    if (!quiet || !id || found) { set.output = id || ""; save(); }
    if (id && !found) note("The MIDI output chosen before isn't here now; the sketch plays here until it is.");
    else if (found) note(`Sending to ${found.name || "the MIDI output"}. Choose where each player goes below.`);
    else if (midi.state === "on") note(outputs().length ? "Choose a MIDI output to send players to." : "MIDI is on, but no output is here. Plug one in (or open a virtual one, such as the IAC driver): it appears by itself.");
  }

  // Panic: every channel of the output told to stop, and each note it may have missed ended
  function silence(output) {
    const out = output || midi.output;
    if (!out) return;
    try {
      if (out.clear) out.clear();
      for (let ch = 0; ch < 16; ch++) {
        out.send([0xb0 | ch, 64, 0]); out.send([0xb0 | ch, 120, 0]); out.send([0xb0 | ch, 123, 0]);
        for (let key = 0; key < 128; key++) out.send([0x80 | ch, key, 0]);
      }
    } catch (_) { /* the device went away */ }
  }
  function panic() {
    if (playing) { playing.sched.stop(); }
    silence();
    note(midi.output ? "Every channel told to stop." : "No MIDI output to quiet.");
  }

  // ------------------------------------------------------------------ the band's parts, from the studio
  async function fetchBand(key) {
    if (!key || bandAsked === key || band?.key === key) return;
    bandAsked = key;
    const edits = window.StudioBridge?.getEdits ? window.StudioBridge.getEdits() : {};
    try {
      const r = await fetch("/api/players", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Studio": TOKEN }, body: JSON.stringify({ edits }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || r.statusText);
      if (bandAsked !== key) return; // a newer version was asked for meanwhile
      band = data;
      if (playing) playing.addBand();
      paint();
    } catch (e) {
      note(`The band's parts didn't come: ${e.message}`);
    } finally {
      if (bandAsked === key) bandAsked = null;
    }
  }
  // a band part asked for (here or on MIDI), in this visit or remembered from the last
  const bandRouted = () => Object.entries(set.routes).some(([part, r]) => r !== "off" && !OWN.some((o) => o.part === part));
  const bandWanted = () => bandRouted() || panelOpen();
  function viewChanged(view) {
    viewKey = view?.listen?.whole || null;
    if (viewKey && band && band.key !== viewKey && bandWanted()) fetchBand(viewKey);
    if (viewKey && !band && bandWanted()) fetchBand(viewKey);
  }

  // ------------------------------------------------------------------ playing: composer.js's start and stop
  // start({ ctx, started, cycle, loop, seconds, origin, span, notes, sound }): notes are the sketch's own
  // ({player: "tune" | "chords" | "bass", t, d, key, vel}); the band's are added here from the studio's parts.
  function start(o) {
    stop();
    if (!o || !o.ctx) return;
    const own = (o.notes || []).map((n) => ({ ...n, player: n.player === "bass" ? "bass-sketch" : n.player }));
    const midiOwn = own.filter((n) => Number.isInteger(routeOf(n.player))); // the page plays its own the page's way
    const send = sendTo(o.ctx);
    const sched = scheduler({ notes: midiOwn, cycle: o.cycle, loop: o.loop, started: o.started, send,
      sound: o.sound || (() => {}), routeOf, now: () => o.ctx.currentTime });
    playing = { sched, ctx: o.ctx, timer: 0, bandAdded: false };
    playing.addBand = () => {
      if (!band || playing.bandAdded || (viewKey && band.key !== viewKey)) return;
      playing.bandAdded = true;
      sched.add(bandNotes(band.players, o.origin, o.span, o.seconds, routeOf));
      programs(send, o.started, band.players.map((p) => p.part));
    };
    programs(send, o.started, OWN.map((p) => p.part));
    playing.addBand();
    if (!playing.bandAdded && bandRouted() && viewKey) fetchBand(viewKey);
    sched.tick();
    playing.timer = setInterval(() => { try { sched.tick(); } catch (e) { stop(); } }, TICK);
  }
  function programs(send, when, parts) { // each player's General MIDI sound, as the MIDI file has it
    if (!set.programs || !midi.output) return;
    const sent = new Set();
    for (const part of parts) {
      const r = routeOf(part), p = program(part);
      if (!Number.isInteger(r) || p === null || p === undefined || r === 9 || sent.has(r)) continue;
      sent.add(r);
      send([0xc0 | r, p], when - 0.01);
    }
  }
  function stop() {
    if (!playing) return;
    clearInterval(playing.timer);
    try { playing.sched.stop(); } catch (_) { /* the device went away */ }
    playing = null;
  }

  // ------------------------------------------------------------------ the panel (index.html's #players)
  let status = "";
  const box = () => (typeof document !== "undefined" ? document.getElementById("players") : null);
  const panelOpen = () => !!box()?.closest?.("details")?.open;
  function note(text) { status = text; const el = document.getElementById("playersNote"); if (el) el.textContent = text; }
  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v === null || v === undefined) continue;
      if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (k === "class") node.className = v;
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }
  function changed() { save(); paint(); window.SongbirdComposer?.replay?.(); }
  function setRoute(part, value) {
    set.routes[part] = value === "page" || value === "off" ? value : clamp(Number(value) | 0, 0, 15);
    changed();
  }
  function everyone(to) {
    for (const p of [...OWN, ...(band?.players || [])]) set.routes[p.part] = to === "midi" ? fileChannel(p.part) : to;
    changed();
  }
  function routeSelect(p) {
    const own = Object.prototype.hasOwnProperty.call(set.routes, p.part) ? set.routes[p.part] : defaultRoute(p.part);
    const file = fileChannel(p.part);
    const options = [["page", "This page"], ["off", "Off"]];
    for (let ch = 0; ch < 16; ch++) options.push([String(ch), `MIDI ${ch + 1}${ch === file ? " (as the MIDI file)" : ""}`]);
    return el("select", { "aria-label": `Where ${p.name} goes`, id: `players-${p.part}`,
      onchange: (e) => setRoute(p.part, e.target.value) },
    options.map(([v, text]) => el("option", { value: v, selected: String(own) === v, disabled: v !== "page" && v !== "off" && !hasMidi() }, text)));
  }
  function paint() {
    const root = box();
    if (!root) return;
    const devices = outputs();
    const outputRow = el("div", { class: "players-row" },
      el("label", { for: "players-output" }, "MIDI out"),
      el("select", { id: "players-output", disabled: !midi.access, onchange: (e) => { choose(e.target.value); changed(); } },
        el("option", { value: "" }, midi.access ? "none: everything plays here" : "not connected"),
        devices.map((o) => el("option", { value: o.id, selected: midi.output === o }, o.name || o.id))),
      midi.access ? null : el("button", { type: "button", class: "btn", id: "players-connect", disabled: !hasMidi(),
        onclick: () => connect(false) }, "Connect MIDI"),
      el("button", { type: "button", class: "btn", id: "players-panic", title: "Every channel of the output told to stop", onclick: panic }, "Panic"));
    const programsRow = el("label", { class: "check players-row" },
      el("input", { type: "checkbox", id: "players-programs", checked: set.programs,
        onchange: (e) => { set.programs = e.target.checked; changed(); } }),
      " send each player's General MIDI sound (as in the MIDI file)");
    const list = el("div", { class: "players-list", role: "group", "aria-label": "Where each player goes" },
      [...OWN, ...(band?.players || [])].map((p) => el("label", { class: "players-player" },
        el("span", {}, p.name, p.drums ? el("small", {}, " (drums)") : null), routeSelect(p))),
      band ? null : el("p", { class: "hint" }, "The band's parts come from the studio when this opens."));
    const all = el("div", { class: "players-row" },
      el("button", { type: "button", class: "link small", onclick: () => everyone("midi"), disabled: !midi.output }, "Everyone to MIDI, as the file"),
      el("button", { type: "button", class: "link small", onclick: () => everyone("page") }, "Everyone here"),
      el("button", { type: "button", class: "link small", onclick: () => { set.routes = {}; changed(); } }, "As at first"));
    root.replaceChildren(outputRow, programsRow, list, all, el("p", { class: "hint", id: "playersNote", "aria-live": "polite" }, status));
  }

  function wire() {
    const root = box();
    if (!root) return;
    const details = root.closest?.("details");
    details?.addEventListener("toggle", () => { if (details.open) { paint(); if (viewKey && band?.key !== viewKey) fetchBand(viewKey); } });
    if (!hasMidi()) note("This browser has no Web MIDI (Chrome, Edge and Firefox have it; Safari doesn't), so the sketch plays here.");
    paint();
    // a browser that already allowed MIDI here: connect without asking again
    try {
      if (hasMidi() && navigator.permissions?.query) {
        navigator.permissions.query({ name: "midi", sysex: false }).then((p) => { if (p.state === "granted") connect(true); }, () => {});
      }
    } catch (_) { /* the browser doesn't say: wait for Connect */ }
  }
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
    else wire();
  }
  if (typeof window !== "undefined") {
    window.addEventListener?.("pagehide", stop);
    window.SongbirdPlayers = { route, start, stop, panic, viewChanged, connect, choose,
      // for tests and the console
      _core: { occurrences, bandNotes, scheduler, routeOf, set, midi, get band() { return band; }, set band(v) { band = v; } } };
  }
})();
