// Seeded randomness. The same seed gives the same numbers on every frame and in every shard.

// a 32-bit hash of any number of integers or strings
export function hash(...keys) {
  let h = 0x811c9dc5;
  for (const k of keys) {
    if (typeof k === 'string') {
      for (let i = 0; i < k.length; i++) h = Math.imul(h ^ k.charCodeAt(i), 0x01000193);
    } else {
      // a number: its integer part and its fraction to 1e-6
      const n = Math.floor(k), f = Math.round((k - n) * 1e6);
      h = Math.imul(h ^ (n | 0), 0x01000193);
      h = Math.imul(h ^ f, 0x01000193);
    }
    h ^= h >>> 15;
  }
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return (h ^ (h >>> 16)) >>> 0;
}

// mulberry32: a generator of floats in [0, 1) from a seed (a number or the keys to hash)
export function prng(...seed) {
  let a = seed.length === 1 && typeof seed[0] === 'number' && Number.isInteger(seed[0]) ? seed[0] >>> 0 : hash(...seed);
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  next.range = (lo, hi) => lo + (hi - lo) * next();
  next.int = (n) => Math.floor(next() * n);
  next.pick = (list) => list[Math.floor(next() * list.length)];
  next.normal = () => {
    const u = Math.max(next(), 1e-12), v = next();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
  return next;
}

// a float in [0, 1) for these keys, without a generator
export const rand = (...keys) => hash(...keys) / 4294967296;
