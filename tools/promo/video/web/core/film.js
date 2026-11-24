// The film: loads the data and the scenes, and draws frame i at t = i / fps.
//
//   const film = await Film.create(canvas, {w, h, solo, capture})
//   window.film = { ready, frames, fps, render(i, {subframes, check}), draw(t), size(w, h), capture(i, opts), send(...) }
//
// A frame is a pure function of its index: scenes draw from t alone, every noise is seeded by pixel and frame,
// and caches hold only what any order of frames would build the same way.
import { GL, DESIGN_H } from './gl.js';
import { Timeline } from './timeline.js';
import { Score } from './score.js';
import { Data } from './data.js';
import { Type } from './type.js';
import { Post } from './post.js';
import { makePalette } from './palette.js';
import { prng, hash, rand } from './prng.js';
import * as math from './math.js';
import * as draw from './draw.js';
import * as camera from './camera.js';
import * as daisy from './daisy.js';
import SCENES from '../scenes/index.js';

// a transition's default when a scene names none: a dissolve over one beat, ending on the section's downbeat
const DEFAULT_ENTER = { kind: 'dissolve', beats: 1, align: 'end' };

export class Film {
  static async create(canvas, opts = {}) {
    const f = new Film(canvas, opts);
    await f.init();
    return f;
  }

  constructor(canvas, { w = 1920, h = 1080, solo = null, capture = false } = {}) {
    this.canvas = canvas;
    this.opts = { solo, capture };
    this.g = new GL(canvas, { preserve: capture });
    this.data = new Data('/data/', { g: this.g, capture });
    this.type = new Type(this.g);
    this.post = new Post(this.g);
    this.w = w; this.h = h;
  }

  async init() {
    const [timelineJson, scoreJson, copy] = await Promise.all([
      this.data.json('timeline.json'), this.data.json('score.json'),
      fetch('/copy.json', { cache: 'no-store' }).then((r) => r.json()),
    ]);
    this.timeline = new Timeline(timelineJson);
    this.score = new Score(scoreJson);
    this.copy = copy;
    this.palette = makePalette(this.timeline);
    this.fps = this.timeline.fps;
    this.frames = this.timeline.frames;
    await this.type.ready();
    // the daisy's marks, for core/daisy.js (any scene may draw it)
    await this.data.json('daisy.json').catch(() => null);
    this.modules = [];
    for (const name of SCENES) {
      const mod = (await import(`../scenes/${name}/index.js`)).default;
      if (!mod || mod.id !== name) throw new Error(`scene ${name}: its default export's id must be "${name}"`);
      this.modules.push(mod);
    }
    this._schedule();
    this.size(this.w, this.h);
    for (const s of this.modules) {
      await this.data.load(s.assets || []);
      if (s.init) await s.init(this.ctxFor(s));
    }
    this._inited = true;
  }

  // each scene's span and its transition in (a scene draws from its transition's start to the end of the next one's)
  _schedule() {
    const tl = this.timeline;
    this.plan = this.modules.map((m) => ({ m, ...tl.span(m.section) }));
    this.plan.sort((a, b) => a.t0 - b.t0);
    this.plan.forEach((p, i) => {
      const enter = { ...DEFAULT_ENTER, ...(p.m.enter || {}) };
      const len = enter.kind === 'cut' ? 0 : (enter.bars ? enter.bars * tl.barLength : (enter.beats || 0) * tl.beatLength);
      const T = enter.kind === 'cut' ? tl.nearestBar(p.t0) : p.t0;
      const [a, b] = enter.align === 'start' ? [T, T + len] : enter.align === 'center' ? [T - len / 2, T + len / 2] : [T - len, T];
      p.enter = { ...enter, t0: i === 0 ? -1 : a, t1: i === 0 ? -1 : b, at: T };
    });
  }

  ctxFor(m) {
    if (m._ctx) return m._ctx;
    const film = this;
    const copyOf = this.copy[m.id] || {};
    m._ctx = {
      id: m.id, g: this.g, gl: this.g.gl, timeline: this.timeline, score: this.score, palette: this.palette, type: this.type,
      data: this.data, copy: this.copy, prng, hash, rand, math, draw, camera, daisy, post: this.post,
      get size() { return { w: film.g.design[0], h: DESIGN_H, px: film.g.px, W: film.g.screen.w, H: film.g.screen.h }; },
      // the paper amount this scene draws with at t (0 stage .. 1 paper): its own light(), else the record's
      k: (t) => math.clamp(m.light ? m.light(m._ctx, t) : film.timeline.paper(t)),
      // a label of this scene from copy.json; a missing key is an error, so no label is ever typed into a scene
      label: (key) => {
        if (!(key in copyOf)) throw new Error(`copy.json has no ${m.id}.${key}`);
        return copyOf[key];
      },
      // a neighbour scene's module, and its anchor at t (the strand's state where it hands over), or null
      scene: (id) => film.modules.find((s) => s.id === id) || null,
      anchor: (id, t) => {
        const s = film.modules.find((x) => x.id === id);
        return s && s.anchor ? s.anchor(film.ctxFor(s), t) : null;
      },
      target: () => film.g.screen,
    };
    return m._ctx;
  }

  size(w, h) {
    this.w = w; this.h = h;
    const g = this.g;
    g.size(w, h);
    for (const t of [this.slotA, this.slotB, this.composed, this.accum, this.out, this.out10]) if (t) g.free(t);
    this.slotA = g.target(w, h, { float: true });
    this.slotB = g.target(w, h, { float: true });
    this.composed = g.target(w, h, { float: true });
    this.accum = g.target(w, h, { float: true });
    this.out = g.target(w, h, { float: false });
    this.out10 = null;
    this.post.resize(w, h);
    this.type.clear();
    // scenes that keep targets or textures at the frame's size rebuild them
    if (this._inited) for (const m of this.modules) if (m.resize) m.resize(this.ctxFor(m));
  }

  // a scene's own amounts at t: its paper amount (its light(), else the record's), how raw, how much cover finish
  _amounts(p, t) {
    const ctx = this.ctxFor(p.m);
    return { k: ctx.k(t), raw: math.clamp(p.m.raw ? p.m.raw(ctx, t) : 0), finish: math.clamp(p.m.finish ? p.m.finish(ctx, t) : 0) };
  }

  // The final pass's settings at t: the ground's lightness (0 stage .. 1 paper) from the drawing scenes' paper
  // amounts, and their raw and finish amounts, blended as the transition between them blends their pictures.
  look(t) {
    const test = this._test;
    const byId = (id) => this.plan.find((p) => p.m.id === id);
    const act = test ? { a: byId(test.a), b: byId(test.b), k: test.k, kind: test.kind } : this.active(t);
    const A = this._amounts(act.a, t);
    let v = A;
    if (act.b) {
      const B = this._amounts(act.b, test && test.tb !== undefined ? test.tb : t);
      const w = act.kind === 'dissolve' ? math.ease.inOutSine(act.k) : act.kind === 'cut' ? (act.k >= 0.5 ? 1 : 0) : act.k;
      v = { k: math.mix(A.k, B.k, w), raw: math.mix(A.raw, B.raw, w), finish: math.mix(A.finish, B.finish, w) };
    }
    return { paper: this.palette.light(v.k), raw: v.raw, finish: v.finish };
  }

  // the scenes drawing at t, and the transition between them
  active(t) {
    if (this.opts.solo) {
      const p = this.plan.find((p) => p.m.id === this.opts.solo);
      if (!p) throw new Error(`no scene ${this.opts.solo}`);
      return { a: p, b: null, k: 0 };
    }
    let cur = this.plan[0];
    for (const p of this.plan) if (t >= (p.enter.t0 >= 0 ? Math.min(p.enter.t0, p.enter.at) : -Infinity)) cur = p;
    const i = this.plan.indexOf(cur);
    const prev = this.plan[i - 1];
    const e = cur.enter;
    if (prev && e.kind !== 'cut' && t < e.t1) {
      const k = math.clamp((t - e.t0) / Math.max(e.t1 - e.t0, 1e-6));
      return { a: prev, b: cur, k, kind: e.kind, enter: e };
    }
    if (prev && e.kind === 'cut' && t < e.at) return { a: prev, b: null, k: 0 };
    return { a: cur, b: null, k: 0 };
  }

  _scene(p, t, target) {
    const ctx = this.ctxFor(p.m);
    p.m.render(ctx, t, target);
  }

  async _prepare(t) {
    const act = this.active(t);
    for (const p of [act.a, act.b]) if (p && p.m.prepare) await p.m.prepare(this.ctxFor(p.m), t);
  }

  // the composed frame (linear light) at song time t; `test` forces a transition between any two scenes
  // ({kind, a: id, b: id, k, tb: b's own time}) so a transition can be judged on scenes that differ
  _compose(t) {
    const test = this._test;
    const byId = (id) => this.plan.find((p) => p.m.id === id);
    const act = test ? { a: byId(test.a), b: byId(test.b), k: test.k, kind: test.kind, enter: {} } : this.active(t);
    if (!act.b) {
      this._scene(act.a, t, this.composed);
      return;
    }
    this._scene(act.a, t, this.slotA);
    this._scene(act.b, test && test.tb !== undefined ? test.tb : t, this.slotB);
    const e = act.enter;
    this.post.transition(this.composed, this.slotA, this.slotB, {
      kind: act.kind, k: act.kind === 'dissolve' ? math.ease.inOutSine(act.k) : act.k, seed: hash(act.b.m.id) % 997,
      from: e.from || null,
    });
  }

  // The frame at song time t into the linear-light accumulator. With subframes, the average of N renders at
  // t + k * shutter / (fps * N): the shutter open for that fraction of the frame from t (0.5, as a film
  // camera's 180 degrees, keeps a fast edge from smearing into steps).
  async _frame(t, subframes, shutter = 0.5) {
    const g = this.g;
    if (subframes <= 1) {
      await this._prepare(t);
      this._compose(t);
      return this.composed;
    }
    g.clear(this.accum, [0, 0, 0, 0]);
    const scale = g.program('film:scale', SCALE);
    for (let k = 0; k < subframes; k++) {
      const s = t + (k * shutter) / (this.fps * subframes);
      await this._prepare(s);
      this._compose(s);
      g.pass(this.accum, scale, { uSrc: this.composed, uK: 1 / subframes }, { blend: 'add' });
    }
    return this.accum;
  }

  // the preview: draw song time t to the canvas
  async draw(t, { subframes = 1, shutter = 0.5, frame = Math.round(t * this.fps) } = {}) {
    const src = await this._frame(t, subframes, shutter);
    this.post.finish(src, null, { ...this.look(t), frame });
  }

  // frame i to the canvas; resolves once the GPU has drawn it
  async render(i, { subframes = 1, shutter = 0.5, check = false } = {}) {
    const t = i / this.fps;
    const src = await this._frame(t, subframes, shutter);
    this.post.finish(src, null, { ...this.look(t), frame: i, check });
    // reading one pixel waits until the GPU has drawn the frame (gl.finish does not, in Chromium)
    const gl = this.g.gl;
    this.g.use(null);
    gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, this._one || (this._one = new Uint8Array(4)));
  }

  // frame i's pixels: RGBA rows from the top (8 bits), or packed 10-bit words (bits: 10)
  async capture(i, { subframes = 1, shutter = 0.5, check = false, bits = 8, show = false, test = null } = {}) {
    const t = i / this.fps;
    this._test = test;
    const src = await this._frame(t, subframes, shutter);
    let out = this.out;
    if (bits === 10) {
      if (!this.out10) this.out10 = this.g.target(this.w, this.h, { format: 'rgb10a2' });
      out = this.out10;
    }
    const look = this.look(t);
    this.post.finish(src, out, { ...look, frame: i, check, flip: true, bits });
    if (show) this.post.finish(src, null, { ...look, frame: i, check, bits: 8 });
    this._test = null;
    return this.g.read(out);
  }

  // frames [from, to) captured and POSTed to url?i=N, a few uploads in flight while the next frame draws
  async send(from, to, url, opts = {}) {
    // uploads in flight are capped near 64 MB: past about 100 MB of bodies Chromium fails the fetch
    const frameBytes = this.w * this.h * 4;
    const inflight = [], depth = Math.max(1, Math.min(opts.inflight || 3, Math.floor(64e6 / frameBytes))), started = performance.now();
    for (let i = from; i < to; i++) {
      const px = await this.capture(i, opts);
      // a Blob body crosses to the network process far faster than a typed array
      inflight.push(fetch(`${url}?i=${i}`, { method: 'POST', body: new Blob([px]) }).then((r) => {
        if (!r.ok) throw new Error(`sink ${r.status}`);
      }));
      while (inflight.length >= depth) await inflight.shift();
    }
    await Promise.all(inflight);
    return { frames: to - from, ms: performance.now() - started };
  }
}

const SCALE = `#version 300 es
precision highp float; precision highp int;
in vec2 vUv; uniform sampler2D uSrc; uniform float uK; out vec4 o;
void main() { o = texture(uSrc, vUv) * uK; }`;
