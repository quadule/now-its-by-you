// The studio's live sound (docs/notes/STUDIO-LIVE-SOUND.md): a section looped with the real sound and kept up to
// date as it is edited, and single notes in an instrument's own sound. Plain JavaScript, no libraries; the pure parts
// (where it may render on its own, the coalescing, the loop's clock, the notes' memory) are exported for the tests.
//
//   SongbirdLive.mayRenderAhead({ device, public, shared })  -> { auto, notes, why }: may the page make a render nobody
//                pressed for (auto), and single notes in the instrument's sound (notes)?
//   SongbirdLive.keeper({ start, cancel, offer })   the bookkeeping: what is wanted, what is in flight, what is heard
//   SongbirdLive.looper(ctx)                        a section's preview played round on its own clock, swapped at a bar line
//   SongbirdLive.samples({ ask, ... })              single notes: asked, decoded, kept in an LRU of bytes
"use strict";

(() => {
  const MARGIN = 0.06;  // s: a bar line nearer than this is too near to schedule a swap at cleanly
  const AHEAD = 0.4;  // s ahead each time round is scheduled
  const SEAM_FADE = 0.12;  // s the time round before fades over at a seam
  const SWAP_FADE = 0.02;  // s the old audio fades out (and the new in) at a swap
  const IN_FADE = 0.015;  // s a time round fades in
  const SETTLE = 120;  // ms of quiet after an edit before a render is asked for (a burst of edits is made once)
  const NOTE_BYTES = 24 * 2 ** 20;  // single notes kept decoded
  const VELOCITIES = [40, 72, 96, 120];  // the classes a note's velocity is taken to (studio.NOTE_VELOCITIES)

  // ---------------------------------------------------------------- where it may make what nobody pressed for
  // On this computer: yes. On the device a section takes many seconds and hundreds of megabytes; a shared or open
  // studio counts and queues its renders for everyone: there, only when the person turns it on.
  function mayRenderAhead(where = {}) {
    if (where.device) return { auto: false, notes: false, why: "device" };
    if (where.public) return { auto: false, notes: false, why: "open" };
    if (where.shared) return { auto: false, notes: true, why: "shared" };
    return { auto: true, notes: true, why: "" };
  }

  // ---------------------------------------------------------------- the loop's clock
  // A preview's loop (studio.loop_of): `start` its first bar line in the file, `length` bar line to bar line, `head`
  // its pickup, `bars` its bar lines from the first. A file without one loops as it is.
  function shape(loop, duration) {
    const length = Number(loop?.length) > 0.05 ? Number(loop.length) : Math.max(0.05, Number(duration) || 0.05);
    const start = Math.max(0, Number(loop?.start) || 0);
    const head = Math.min(start, Math.max(0, Number(loop?.head) || 0), length / 2);
    const bars = (Array.isArray(loop?.bars) && loop.bars.length ? loop.bars : [0]).map(Number)
      .filter((b) => b >= 0 && b < length).sort((a, b) => a - b);
    return { start, length, head, bars: bars.length ? bars : [0] };
  }
  // The time round sounding at t: the first (0) plays the file from its beginning, its first bar line at b0; each
  // later k from `head` before its bar line b0 + k·length.
  function roundAt(t, b0, s) {
    if (t < b0 + s.length - s.head) return 0;
    return Math.floor((t - b0 + s.head) / s.length);
  }
  // where in the file the audio is at t: its round and the offset into the file
  function offsetAt(t, b0, s) {
    const k = roundAt(t, b0, s);
    return { k, offset: s.start + (t - (b0 + k * s.length)) };
  }
  // The earliest time after now + margin new audio may take over: a bar line of the loop (not one inside the pickup
  // of the next time round), or the start of a time round.
  function swapTime(now, b0, s, margin = MARGIN) {
    const from = now + margin, k = roundAt(from, b0, s);
    let best = Infinity;
    for (let j = k; j <= k + 2; j++) {
      const base = b0 + j * s.length;
      if (j > 0 && base - s.head > from) best = Math.min(best, base - s.head);
      for (const bar of s.bars) {
        if (bar > s.length - s.head - 0.05) continue;
        const t = base + bar;
        if (t > from && t < best) best = t;
      }
      if (best < Infinity) break;
    }
    return best;
  }
  // how far round the loop t is, 0..1 (0 before the first bar line)
  function fraction(t, b0, s) {
    if (t < b0) return 0;
    return ((t - b0) % s.length) / s.length;
  }

  // ---------------------------------------------------------------- coalescing: only the latest is made
  // want(target): the page wants the audio of target.key (the view's preview key for the section, studio.Studio.key).
  // At most one render is in flight. A want for something else drops it if it is still waiting its turn (waiting:
  // the renderer's job queued), else waits for it (one renderer makes one thing at a time, and an open studio lets a
  // visitor ask for the next only once theirs is made), and then asks for the latest. A render is asked for once
  // edits have settled (SETTLE ms). Its audio is offered only if its key is still the one wanted, and is the key it
  // was asked for. auto off: a want is kept, made when now() is called. stop(): nothing more is asked for.
  function keeper({ start, cancel = () => {}, offer = () => {}, changed = () => {}, settle = SETTLE,
                    waiting = (task) => task?.job?.state === "queued",
                    schedule = (f, ms) => setTimeout(f, ms), unschedule = (t) => clearTimeout(t), auto = true } = {}) {
    let want = null, flight = null, have = null, failed = null, timer = null, on = false;
    const k = {};
    function launch() {
      timer = null;
      if (!on || !want || flight || have?.key === want.key || failed === want.key) { changed(); return; }
      const target = want, task = start(target);
      flight = { target, task };
      changed();
      Promise.resolve(task?.done).then((job) => land(target, task, job),
        (e) => land(target, task, { state: "failed", error: String(e?.message || e) }));
    }
    function land(target, task, job) {
      if (flight?.task !== task) return;  // abandoned: never heard
      flight = null;
      if (on && job?.state === "done" && want?.key === target.key && (!job.key || job.key === target.key)) {
        have = target;
        offer(job, target);
      } else if (on && job?.state === "failed" && job.error !== "cancelled" && want?.key === target.key) {
        failed = target.key;
      }
      if (on && want && want.key !== have?.key && want.key !== failed) soon(); else changed();
    }
    function soon(ms = settle) {
      if (timer !== null) unschedule(timer);
      timer = schedule(launch, ms);
      changed();
    }
    Object.defineProperties(k, Object.getOwnPropertyDescriptors({
      auto,
      // the page's latest: an edit settled (the view for it came), or the section played
      want(target) {
        want = target;
        if (flight && flight.target.key !== target.key && waiting(flight.task)) { cancel(flight.task); flight = null; }
        if (!on) return;
        if (have?.key === target.key || flight) { changed(); return; }
        if (k.auto || !have) soon(); else changed();  // (the first audio is made whenever the loop is played)
      },
      // what the page has playing now (the first audio, or what it had)
      heard(target) { have = target; changed(); },
      begin() { on = true; failed = null; if (want && want.key !== have?.key) soon(0); },
      now() { if (!on) on = true; failed = null; soon(0); },
      stop() {
        on = false;
        if (timer !== null) { unschedule(timer); timer = null; }
        if (flight) { cancel(flight.task); flight = null; }
        have = null; want = null; failed = null;
        changed();
      },
      // "current" (what plays is what is wanted), "updating" (being made, or about to be), "earlier" (not made: auto
      // off), "failed" (the latest couldn't be made), or "off"
      status() {
        if (!on) return "off";
        if (!want || have?.key === want.key) return flight || timer !== null ? "updating" : "current";
        if (failed === want.key) return "failed";
        return flight || timer !== null ? "updating" : "earlier";
      },
      get wanted() { return want; },
      get had() { return have; },
      get flight() { return flight; },
    }));
    return k;
  }

  // ---------------------------------------------------------------- the loop, played
  // ctx: a WebAudio context (or a stand-in with createBufferSource, createGain, currentTime, destination).
  // ended(): the loop let go (finish) has played its last time round out.
  function looper(ctx, { destination = null, tick = (f) => setInterval(f, 50), untick = (t) => clearInterval(t),
                         ended = () => {} } = {}) {
    const out = destination || ctx.destination;
    let buffer = null, s = null, b0 = 0, key = null, voices = [], next = 0, timer = null, queued = null, swap = null;
    let finishing = false;
    const L = {};
    function voice(buf, at, offset, k, fadeIn) {
      const src = ctx.createBufferSource(), gain = ctx.createGain();
      src.buffer = buf;
      gain.gain.setValueAtTime(0, at);
      gain.gain.linearRampToValueAtTime(1, at + fadeIn);
      src.connect(gain); gain.connect(out);
      src.start(at, Math.max(0, offset));
      const v = { src, gain, k, at };
      src.onended = () => { voices = voices.filter((x) => x !== v); try { gain.disconnect(); } catch (e) { /* gone */ } };
      voices.push(v);
      return v;
    }
    function fade(v, at, over) {  // once: a voice faded out stays out
      if (v.gone) return;
      v.gone = true;
      v.gain.gain.setValueAtTime(1, at);
      v.gain.gain.linearRampToValueAtTime(0, at + over);
      try { v.src.stop(at + over + 0.02); } catch (e) { /* stopped */ }
    }
    function round(k) {  // the time round k, scheduled with the audio there is then
      const at = b0 + k * s.length - s.head;
      for (const v of voices) if (v.k < k) fade(v, at, SEAM_FADE);
      voice(buffer, at, s.start - s.head, k, IN_FADE);
      next = k + 1;
    }
    function step() {
      if (!buffer) return;
      const t = ctx.currentTime;
      if (swap && t >= swap.at) { key = swap.key; swap = null; }  // the new audio is what sounds now
      if (finishing) {  // no more times round: once the last has rung out, it's over
        if (!voices.length) { L.stop(); ended(); }
        return;
      }
      if (queued && !swap) { const q = queued; queued = null; take(q.buf, q.loop, q.key); }
      if (b0 + next * s.length - s.head < t - 0.05) {  // a time round's start passed unscheduled (a hidden tab's slow
        // timers): it joins where it is, and those before it are let go
        const { k, offset } = offsetAt(t, b0, s);
        if (k >= next) {
          for (const v of voices) fade(v, t, SWAP_FADE);
          voice(buffer, t, offset, k, SWAP_FADE);
          next = k + 1;
        }
      }
      while (b0 + next * s.length - s.head - t < AHEAD) round(next);
    }
    // the new audio at the next bar line (or the next time round, when its length differs: a tempo changed)
    function take(buf, loop, newKey) {
      const t = ctx.currentTime, ns = shape(loop, buf.duration);
      const same = Math.abs(ns.length - s.length) < 1e-3 && Math.abs(ns.start - s.start) < 2e-3;
      if (!same) {  // a new clock from the next time round on
        const at = b0 + next * s.length - s.head > t + MARGIN ? b0 + next * s.length - s.head : b0 + (next + 1) * s.length - s.head;
        for (const v of voices) if (v.at >= at - 1e-6) { try { v.src.stop(0); } catch (e) { /* never started */ } }
        voices = voices.filter((v) => v.at < at - 1e-6);
        for (const v of voices) fade(v, at, SEAM_FADE);
        buffer = buf; s = ns; b0 = at + ns.head; next = 0;
        voice(buffer, at, ns.start - ns.head, 0, IN_FADE);
        next = 1;
        swap = { at, key: newKey };
        return at;
      }
      const at = swapTime(t, b0, s);
      const { k, offset } = offsetAt(at, b0, s);
      // what was to start after it is started again with the new audio; what sounds at it fades out there
      for (const v of voices) if (v.at >= at - 1e-6) { try { v.src.stop(0); } catch (e) { /* never started */ } }
      voices = voices.filter((v) => v.at < at - 1e-6);
      const starts = Math.abs(at - (b0 + k * s.length - s.head)) < 1e-6 && k > 0;
      for (const v of voices) fade(v, at, starts ? SEAM_FADE : SWAP_FADE);
      buffer = buf;
      voice(buffer, at, starts ? s.start - s.head : offset, k, starts ? IN_FADE : SWAP_FADE);
      next = k + 1;
      swap = { at, key: newKey };
      return at;
    }
    Object.defineProperties(L, Object.getOwnPropertyDescriptors({
      // from the file's beginning, now: the breath, the band before, the pickup
      play(buf, loop, newKey, when = ctx.currentTime + 0.05) {
        L.stop();
        buffer = buf; s = shape(loop, buf.duration); key = newKey; b0 = when + s.start; next = 1; queued = null; swap = null;
        finishing = false;
        voice(buffer, when, 0, 0, IN_FADE);
        timer = tick(step);
        step();
      },
      // new audio for the loop: taken at the next bar line (after one already on its way)
      swap(buf, loop, newKey) {
        if (!buffer) { L.play(buf, loop, newKey); return ctx.currentTime; }
        if (swap) { queued = { buf, loop, key: newKey }; return null; }
        return take(buf, loop, newKey);
      },
      // loop off: the time round playing plays to its end (its ring too), and no other starts
      finish() {
        if (!buffer) return;
        finishing = true;
        const t = ctx.currentTime;
        for (const v of voices) if (v.at > t + 1e-3) { try { v.src.stop(0); } catch (e) { /* never started */ } }
        voices = voices.filter((v) => v.at <= t + 1e-3);
        queued = null;
      },
      stop() {
        if (timer !== null) untick(timer);
        timer = null;
        const t = ctx.currentTime;
        for (const v of voices) {
          try {
            v.gain.gain.cancelScheduledValues?.(t);
            v.gain.gain.setValueAtTime(v.gain.gain.value ?? 1, t);
            v.gain.gain.linearRampToValueAtTime(0, t + 0.024);
            v.src.stop(t + 0.03);
          } catch (e) { /* stopped */ }
        }
        voices = []; buffer = null; key = null; queued = null; swap = null;
      },
      get playing() { return !!buffer; },
      get finishing() { return finishing; },
      // the audio's key sounding now; the key on its way (a swap scheduled, or queued), if any
      get key() { return key; },
      get coming() { return queued?.key ?? swap?.key ?? null; },
      // how far round the loop it is (0..1), and its length in seconds
      where() { return buffer ? { fraction: fraction(ctx.currentTime, b0, s), length: s.length, start: b0 } : null; },
      _voices: () => voices,
    }));
    return L;
  }

  // ---------------------------------------------------------------- single notes
  // An LRU of byte-counted values: the least recently used go first once the bytes pass the limit.
  function lru(limit) {
    const map = new Map();
    let bytes = 0;
    return {
      get(key) {
        const hit = map.get(key);
        if (!hit) return undefined;
        map.delete(key); map.set(key, hit);
        return hit.value;
      },
      put(key, value, size) {
        if (map.has(key)) { bytes -= map.get(key).size; map.delete(key); }
        if (size > limit) return false;
        map.set(key, { value, size });
        bytes += size;
        for (const [old, e] of map) {
          if (bytes <= limit) break;
          map.delete(old); bytes -= e.size;
        }
        return true;
      },
      has: (key) => map.has(key),
      clear() { map.clear(); bytes = 0; },
      get bytes() { return bytes; },
      get size() { return map.size; },
      keys: () => [...map.keys()],
    };
  }
  const velocityClass = (v) => VELOCITIES.reduce((best, c) => (Math.abs(c - v) < Math.abs(best - v) ? c : best), VELOCITIES[0]);
  // A note's name for this page: the player, its pitch (a drum's piece), its velocity's class, the edits' revision
  // (a new revision asks the studio again, which answers the same file where nothing the player's maker reads changed)
  const noteName = (revision, player, pitch, velocity) => `${revision}|${player}|${pitch}|${velocityClass(velocity)}`;

  // ask(path, body) -> the studio's answer; bytes(url) -> ArrayBuffer; context() -> a WebAudio context;
  // allowed() -> whether the instrument's own notes are asked here; edits() and revision(): the page's edits
  function samples({ ask, bytes, context, allowed = () => true, edits = () => ({}), revision = () => 0, limit = NOTE_BYTES } = {}) {
    const decoded = lru(limit);  // the studio's key -> AudioBuffer
    const named = new Map();  // noteName -> the studio's key (this revision's)
    const asking = new Map();  // noteName -> Promise
    let named_at = null;
    function fresh() {
      const r = revision();
      if (r !== named_at) { named.clear(); asking.clear(); named_at = r; }
      return r;
    }
    function fetchNote(player, pitch, velocity) {
      const r = fresh(), name = noteName(r, player, pitch, velocity);
      if (named.has(name) && decoded.has(named.get(name))) return Promise.resolve(decoded.get(named.get(name)));
      if (asking.has(name)) return asking.get(name);
      const p = (async () => {
        const answer = await ask("/api/note", { edits: edits(), player, pitch, velocity: velocityClass(velocity) });
        let buf = decoded.get(answer.key);
        if (!buf) {
          const ctx = context();
          if (!ctx) return null;
          buf = await ctx.decodeAudioData(await bytes(answer.url));
          decoded.put(answer.key, buf, (buf.length || 0) * (buf.numberOfChannels || 2) * 4);
        }
        if (revision() === r) named.set(name, answer.key);
        return buf;
      })().catch(() => null).finally(() => asking.delete(name));
      asking.set(name, p);
      return p;
    }
    return {
      // the note in the instrument's own sound if it's here, at once; else false (the caller sounds the sketch's
      // tone) and it's asked for, for the next time
      play(player, pitch, velocity = 96) {
        if (!allowed()) return false;
        const r = fresh(), name = noteName(r, player, pitch, velocity), buf = named.has(name) ? decoded.get(named.get(name)) : null;
        if (!buf) { fetchNote(player, pitch, velocity); return false; }
        const ctx = context();
        if (!ctx) return false;
        const src = ctx.createBufferSource(), gain = ctx.createGain();
        src.buffer = buf; gain.gain.value = 0.9;
        src.connect(gain); gain.connect(ctx.destination);
        src.start(ctx.currentTime + 0.005);
        src.onended = () => { try { gain.disconnect(); } catch (e) { /* gone */ } };
        return true;
      },
      // the notes a roll is likely to sound next, asked one after another (when the instrument's notes are asked here)
      async prefetch(player, pitches, velocity = 96) {
        if (!allowed()) return 0;
        let n = 0;
        for (const pitch of pitches.slice(0, 24)) { if (await fetchNote(player, pitch, velocity)) n++; }
        return n;
      },
      decoded, named,
    };
  }

  // the octave a roll's notes sit around: twelve semitones centred on their middle (the key's note when there are none)
  function octaveAround(pitches) {
    const sorted = pitches.filter(Number.isFinite).sort((a, b) => a - b);
    const mid = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    return Array.from({ length: 12 }, (_, i) => mid - 6 + i);
  }

  const api = { mayRenderAhead, shape, roundAt, offsetAt, swapTime, fraction, keeper, looper, lru, samples, velocityClass,
    noteName, octaveAround, MARGIN, SEAM_FADE, SWAP_FADE, SETTLE, VELOCITIES };
  if (typeof window !== "undefined") window.SongbirdLive = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})();
