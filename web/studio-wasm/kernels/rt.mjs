// The runtime the translated kernels (kernels.gen.mjs) lean on: array descriptors and Python's arithmetic
// where JavaScript's differs. An array is {d, nd, n0, n1, s0, s1, t}: d a typed array starting at its
// first element, n0/n1 its shape, s0/s1 its strides in elements, t 'f8' | 'i8' | 'b1' (integers and
// booleans are held in Float64Arrays; the kernels truncate on store).

let heap = () => { throw new Error('rt.setHeap was not called'); };

// Where numpy's arrays live: a function returning the ArrayBuffer of Pyodide's wasm memory (it is
// replaced when memory grows, so it is asked for each call).
export function setHeap(f) { heap = f; }

// A view of a numpy array in Pyodide's memory (no copy): its data address, shape and strides (elements).
export function view(addr, nd, n0, n1, s0, s1, t) {
  const extent = nd === 1 ? (n0 > 0 ? (n0 - 1) * s0 + 1 : 0)
    : (n0 > 0 && n1 > 0 ? (n0 - 1) * s0 + (n1 - 1) * s1 + 1 : 0);
  return { d: new Float64Array(heap(), addr, extent), nd, n0, n1, s0, s1, t };
}

export function alloc(nd, n0, n1, t, fill) {
  const n = nd === 1 ? n0 : n0 * n1;
  const d = new Float64Array(n);
  if (fill !== 0) d.fill(fill);
  return { d, nd, n0, n1: nd === 1 ? 0 : n1, s0: nd === 1 ? 1 : n1, s1: 1, t };
}

export function array(values, nd, n0, n1, t) {
  const a = alloc(nd, n0, n1, t, 0);
  a.d.set(values);
  return a;
}

export function copy(a) {
  const b = alloc(a.nd, a.n0, a.n1, a.t, 0);
  if (a.nd === 1) {
    for (let i = 0; i < a.n0; i++) b.d[i] = a.d[i * a.s0];
  } else {
    for (let i = 0; i < a.n0; i++) for (let j = 0; j < a.n1; j++) b.d[i * a.n1 + j] = a.d[i * a.s0 + j * a.s1];
  }
  return b;
}

// a contiguous typed array of exactly the array's elements (a copy only if it is a strided view)
export function packed(a) {
  if (a.t === 'c16') return a.d;  // complex: interleaved and contiguous
  const n = a.nd === 1 ? a.n0 : a.n0 * a.n1;
  const contiguous = a.nd === 1 ? a.s0 === 1 : (a.s1 === 1 && a.s0 === a.n1);
  if (contiguous) return a.d.length === n ? a.d : a.d.subarray(0, n);
  return copy(a).d;
}

// copy array a's elements, in order, to Pyodide's memory at addr (a new numpy array's data)
export function store(addr, a) {
  const src = packed(a);
  new Float64Array(heap(), addr, src.length).set(src);
}

// a.reshape(-1): the elements in C order as a 1-d array, a view when they lie so (numba's reshape needs a
// contiguous array), a copy otherwise
export function flat(a) {
  if (a.nd === 1) return a;
  const contiguous = a.s1 === 1 && a.s0 === a.n1;
  const d = contiguous ? a.d : copy(a).d;
  return { d, nd: 1, n0: a.n0 * a.n1, n1: 0, s0: 1, s1: 1, t: a.t };
}

// the same for a bool array (numpy's bool_: a byte each, 0 or 1)
export function store_u8(addr, a) {
  const src = packed(a);
  new Uint8Array(heap(), addr, src.length).set(src);
}

export function row(a, i) {
  if (i < 0) i += a.n0;
  return { d: a.d.subarray(i * a.s0), nd: 1, n0: a.n1, n1: 0, s0: a.s1, s1: 1, t: a.t };
}

export function slice1(a, lo, hi) {
  if (lo < 0) lo += a.n0;
  if (hi < 0) hi += a.n0;
  lo = Math.max(0, Math.min(lo, a.n0));
  hi = Math.max(lo, Math.min(hi, a.n0));
  return { d: a.d.subarray(lo * a.s0), nd: 1, n0: hi - lo, n1: 0, s0: a.s0, s1: 1, t: a.t };
}

export function setslice(a, v) {
  if (typeof v === 'number' || typeof v === 'boolean') {
    for (let i = 0; i < a.n0; i++) a.d[i * a.s0] = +v;
  } else {
    for (let i = 0; i < a.n0; i++) a.d[i * a.s0] = v.d[i * v.s0];
  }
}

// Python's floored modulo, CPython's float algorithm (numba's too)
export function mod(a, b) {
  const m = a % b;
  if (m !== 0) return ((b < 0) !== (m < 0)) ? m + b : m;
  return b < 0 ? -0 : 0;
}

// Python's floor division, CPython's float algorithm
export function floordiv(a, b) {
  let m = a % b;
  let div = (a - m) / b;
  if (m !== 0 && ((b < 0) !== (m < 0))) div -= 1;
  if (div === 0) return (a / b) < 0 ? -0 : 0;
  let f = Math.floor(div);
  if (div - f > 0.5) f += 1;
  return f;
}

// numba's power by a literal integer: unrolled squaring (numbers.static_power_impl)
export function ipow(x, n) {
  const invert = n < 0;
  if (invert) n = -n;
  let r = 1, v = x;
  while (n !== 0) {
    if (n & 1) r = r * v;
    n >>= 1;
    if (n !== 0) v = v * v;
  }
  return invert ? 1 / r : r;
}

export function ipowv(x, n) { return ipow(x, n); }

// Python's min and max of numbers: the first of the least (greatest)
export function pmin(a, ...rest) { for (const b of rest) if (b < a) a = b; return a; }
export function pmax(a, ...rest) { for (const b of rest) if (b > a) a = b; return a; }

export function sign(x) { return x > 0 ? 1 : x < 0 ? -1 : x; }
export function copysign(x, y) { return (y < 0 || Object.is(y, -0)) ? -Math.abs(x) : Math.abs(x); }

// Python's round(): half to even
export function pyround(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

// an elementwise array expression's result: a new 1-d array with f(i) at i
export function vec(n, f) {
  const a = alloc(1, n, 0, 'f8', 0);
  for (let i = 0; i < n; i++) a.d[i] = f(i);
  return a;
}

// numpy's minimum and maximum: NaN propagates; otherwise the lesser (greater)
export function npmin(a, b) { return (a !== a || a <= b) ? a : b; }
export function npmax(a, b) { return (a !== a || a >= b) ? a : b; }
