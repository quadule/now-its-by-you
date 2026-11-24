// Data files from /data/ (renders/promo/video/data/), fetched once and kept.
//
//   await data.json('text.json')
//   await data.array('throat/envelope')     -> {values: Float32Array (scaled), raw, shape, rate, t0, about, at(t)}
//   await data.image('/art/front-color.png') -> {tex, width, height} a texture (sRGB values, mipmapped), decoded once
//   data.images('/blender/shot/', 'frame_%04d.png', {count, proxy: '/blender/shot-proxy/'})
//     -> {count, frame(i) -> Promise<ImageBitmap>, texture(i) -> Promise<{tex, width, height}>}
//     the preview reads the proxy directory (same names) when given; capture always reads the full frames
//   Draw an image with g.rects(..., {texture: img.tex, srgb: true}) or g.mesh(target, img.tex, grid, {srgb: true}).
//   data.get(name)  -> a file already loaded (scenes call this in render; load in init or through `assets`)
//
// A binary array is <name>.bin beside <name>.json: {"dtype", "shape", "rate", "t0", "scale", "offset", "about"};
// a stored value v means v * scale + offset.
const DTYPES = { uint8: Uint8Array, int8: Int8Array, uint16: Uint16Array, int16: Int16Array, int32: Int32Array, float32: Float32Array };

export class Data {
  constructor(base = '/data/', { g = null, capture = false } = {}) {
    this.base = base;
    this.g = g;
    this.capture = capture;
    this.cache = new Map();
    this.loaded = new Map();
  }

  url(name) { return name.startsWith('/') ? name : this.base + name; }

  _fetch(name, kind) {
    const key = kind + ':' + name;
    if (!this.cache.has(key)) {
      const p = fetch(this.url(name), { cache: 'no-store' }).then((r) => {
        if (!r.ok) throw new Error(`data: ${this.url(name)} ${r.status}`);
        return kind === 'json' ? r.json() : kind === 'bytes' ? r.arrayBuffer() : r.blob();
      });
      this.cache.set(key, p);
    }
    return this.cache.get(key);
  }

  async json(name) {
    const v = await this._fetch(name, 'json');
    this.loaded.set(name, v);
    return v;
  }

  async bytes(name) { return this._fetch(name, 'bytes'); }

  async array(name) {
    const base = name.replace(/\.(bin|json)$/, '');
    const key = 'array:' + base;
    if (!this.cache.has(key)) {
      this.cache.set(key, (async () => {
        const [head, buf] = await Promise.all([this.json(base + '.json'), this.bytes(base + '.bin')]);
        const T = DTYPES[head.dtype];
        if (!T) throw new Error(`data: ${base} has dtype ${head.dtype}`);
        const raw = new T(buf);
        const count = head.shape.reduce((a, b) => a * b, 1);
        if (raw.length !== count) throw new Error(`data: ${base}.bin holds ${raw.length} values, shape says ${count}`);
        const scale = head.scale ?? 1, offset = head.offset ?? 0;
        let values = raw;
        if (head.dtype !== 'float32' || scale !== 1 || offset !== 0) {
          values = new Float32Array(count);
          for (let i = 0; i < count; i++) values[i] = raw[i] * scale + offset;
        }
        const rowLength = head.shape.slice(1).reduce((a, b) => a * b, 1);
        const rows = head.shape[0];
        const arr = {
          ...head, raw, values, rows, rowLength,
          row: (i) => values.subarray(i * rowLength, (i + 1) * rowLength),
          // the row index at song time t (rate rows a second from t0), clamped
          index: (t) => Math.min(Math.max(Math.floor((t - (head.t0 || 0)) * head.rate), 0), rows - 1),
          at: (t) => arr.row(arr.index(t)),
        };
        this.loaded.set(base, arr);
        return arr;
      })());
    }
    return this.cache.get(key);
  }

  get(name) {
    const base = name.replace(/\.bin$/, '');
    if (this.loaded.has(name)) return this.loaded.get(name);
    if (this.loaded.has(base)) return this.loaded.get(base);
    throw new Error(`data: ${name} is not loaded (list it in the scene's assets)`);
  }

  // load a scene's assets: names ending .json load as JSON, others (or .bin) as arrays
  async load(names = []) {
    return Promise.all(names.map((n) => (n.endsWith('.json') ? this.json(n) : this.array(n))));
  }

  async _bitmap(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`image: ${url} ${r.status}`);
    return createImageBitmap(await r.blob(), { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
  }

  _upload(bm) {
    const tex = this.g.texture(bm, { filter: 'linear', mips: true });
    return { tex, width: bm.width, height: bm.height };
  }

  // a still image as a texture (its values are sRGB: draw with srgb: true); cached by url
  image(url) {
    const key = 'image:' + url;
    if (!this.cache.has(key)) this.cache.set(key, this._bitmap(url).then((bm) => { const t = this._upload(bm); bm.close(); return t; }));
    return this.cache.get(key);
  }

  // an image sequence: frame(i) resolves to a decoded ImageBitmap, texture(i) to a texture; keeps the last `keep`
  images(dir, pattern, { count = Infinity, keep = 8, first = 0, proxy = null } = {}) {
    if (proxy && !this.capture) dir = proxy;
    const decoded = new Map(), textures = new Map();
    const name = (i) => pattern.replace(/%0(\d)d/, (_, w) => String(i + first).padStart(Number(w), '0')).replace('%d', String(i + first));
    return {
      count,
      url: (i) => (dir.endsWith('/') ? dir : dir + '/') + name(i),
      frame: (i) => {
        i = Math.min(Math.max(Math.round(i), 0), count - 1);
        if (!decoded.has(i)) {
          const url = (dir.endsWith('/') ? dir : dir + '/') + name(i);
          decoded.set(i, fetch(url, { cache: 'no-store' }).then((r) => {
            if (!r.ok) throw new Error(`images: ${url} ${r.status}`);
            return r.blob();
          }).then((b) => createImageBitmap(b, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' })));
          while (decoded.size > keep) {
            const [old, p] = decoded.entries().next().value;
            decoded.delete(old);
            p.then((bm) => bm.close()).catch(() => {});
          }
        }
        return decoded.get(i);
      },
      texture: (i) => {
        i = Math.min(Math.max(Math.round(i), 0), count - 1);
        if (!textures.has(i)) {
          textures.set(i, this._bitmap((dir.endsWith('/') ? dir : dir + '/') + name(i)).then((bm) => {
            const t = this._upload(bm);
            bm.close();
            return t;
          }));
          while (textures.size > keep) {
            const [old, p] = textures.entries().next().value;
            textures.delete(old);
            p.then((t) => this.g.deleteTexture(t.tex)).catch(() => {});
          }
        }
        return textures.get(i);
      },
    };
  }
}
