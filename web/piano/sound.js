// The page's own sound: a small piano-ish voice made in Web Audio (no samples), a metronome's click, and a
// room around them. window.PianoSound. Nothing here knows the song.
"use strict";

(function () {
  let ctx = null, master = null, room = null, bus = null, clicks = null;
  const held = new Map(); // key -> voice, for notes played by hand (released on key up)

  function newBus(into) { // every scheduled voice goes through one bus, so a stop can cut them all at once
    const b = ctx.createGain();
    b.connect(master);
    const send = ctx.createGain(); send.gain.value = 0.22;
    b.connect(send); send.connect(room);
    return b;
  }

  function start() {
    if (ctx) {
      if (ctx.state === "suspended") ctx.resume();
      return ctx;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    try { ctx = new AC({ latencyHint: "interactive" }); } catch (e) { return null; }
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.knee.value = 12; comp.ratio.value = 3; comp.attack.value = 0.004; comp.release.value = 0.2;
    comp.connect(ctx.destination);
    master = ctx.createGain(); master.gain.value = 0.8; master.connect(comp);
    // a small wooden room: a second and a half of noise dying away, a little darker as it goes
    const len = Math.floor(ctx.sampleRate * 1.6), ir = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = ir.getChannelData(c);
      let lp = 0;
      for (let i = 0; i < len; i++) {
        const t = i / ctx.sampleRate, k = 0.25 + 0.7 * Math.exp(-t * 3);
        lp += k * ((Math.random() * 2 - 1) - lp);
        d[i] = lp * Math.exp(-t * 4.2) * Math.min(1, i / (ctx.sampleRate * 0.008));
      }
    }
    room = ctx.createConvolver(); room.buffer = ir; room.connect(master);
    bus = newBus();
    clicks = ctx.createGain(); clicks.connect(master);
    return ctx;
  }

  const hz = (p) => 440 * Math.pow(2, (p - 69) / 12);

  // One struck string: a triangle and three sine partials, a brightness that closes after the strike, and a
  // decay that is longer low down, as a piano's is. Returns a voice to damp.
  function voice(pitch, vel, when, gain, into) {
    if (!ctx) return null;
    const t = Math.max(when, ctx.currentTime), f = hz(pitch);
    const v = Math.min(1, Math.max(0.05, vel)), amp = v * gain * 0.3;
    const out = ctx.createGain();
    const filt = ctx.createBiquadFilter(); filt.type = "lowpass"; filt.Q.value = 0.4;
    filt.frequency.setValueAtTime(Math.min(9000, f * (4 + 10 * v)), t);
    filt.frequency.setTargetAtTime(Math.max(f * 1.6, 300), t + 0.01, 0.35);
    const decay = 0.45 + 2.2 * Math.max(0, Math.min(1, (84 - pitch) / 48)); // seconds: long in the bass
    out.gain.setValueAtTime(0, t);
    out.gain.linearRampToValueAtTime(amp, t + 0.004);
    out.gain.setTargetAtTime(amp * 0.35, t + 0.004, 0.09); // the strike's first fall
    out.gain.setTargetAtTime(0.0001, t + 0.12, decay);      // then the long ring
    const oscs = [];
    for (const [type, mul, g] of [["triangle", 1, 1], ["sine", 2.002, 0.28], ["sine", 3.003, 0.08], ["sine", 0.998, 0.35]]) {
      const o = ctx.createOscillator(); o.type = type; o.frequency.value = f * mul;
      const og = ctx.createGain(); og.gain.value = g;
      o.connect(og); og.connect(filt); o.start(t); oscs.push(o);
    }
    filt.connect(out); out.connect(into || bus);
    const stopAt = t + 0.12 + decay * 5;
    oscs.forEach((o) => o.stop(stopAt));
    oscs[0].onended = () => { try { out.disconnect(); } catch (e) { /* gone */ } };
    return { out, oscs, t };
  }

  function damp(v, when) {
    if (!v || !ctx) return;
    const t = Math.max(when || ctx.currentTime, v.t + 0.02);
    v.out.gain.cancelScheduledValues(t);
    v.out.gain.setTargetAtTime(0, t, 0.07);
    v.oscs.forEach((o) => { try { o.stop(t + 0.6); } catch (e) { /* already stopped */ } });
  }

  let hands = null; // the bus for notes played by hand: silence() leaves them alone
  window.PianoSound = {
    start,
    get running() { return !!ctx && ctx.state === "running"; },
    now() { return ctx ? ctx.currentTime : 0; },
    // a note from the score: struck at `when` (audio clock), damped `dur` seconds later
    note(pitch, vel, when, dur, gain) {
      if (!ctx || gain <= 0) return;
      damp(voice(pitch, vel, when, gain), when + Math.max(0.05, dur));
    },
    // a note played by hand, held until up(key)
    down(key, pitch, vel, gain) {
      if (!start()) return;
      if (!hands) hands = newBus();
      if (held.has(key)) damp(held.get(key));
      held.set(key, voice(pitch, vel, ctx.currentTime, gain, hands));
    },
    up(key) {
      if (held.has(key)) { damp(held.get(key)); held.delete(key); }
    },
    click(when, accent, gain) {
      if (!ctx || gain <= 0) return;
      const t = Math.max(when, ctx.currentTime);
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = "sine"; o.frequency.value = accent ? 1760 : 1175;
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime((accent ? 0.45 : 0.28) * gain, t + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.06);
      o.connect(g); g.connect(clicks); o.start(t); o.stop(t + 0.08);
    },
    // cut every note and click the score has scheduled (not the ones held by hand)
    silence() {
      if (!ctx) return;
      const old = bus, oldClicks = clicks, t = ctx.currentTime;
      [old, oldClicks].forEach((n) => {
        n.gain.setTargetAtTime(0, t, 0.015);
        setTimeout(() => { try { n.disconnect(); } catch (e) { /* gone */ } }, 250);
      });
      bus = newBus();
      clicks = ctx.createGain(); clicks.connect(master);
    },
  };
})();
