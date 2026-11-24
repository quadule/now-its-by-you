// The film's colours. Scenes use these tokens only.
//
//   palette.srgb.paper -> [r, g, b] 0..1 (display values)   palette.lin.paper -> linear light (what shaders take)
//   palette.inks(k)    -> {ground, ink, ink2, red, rule, ruleStrong, sung, cold, card, light, side} in linear light for paper amount k
//   palette.light(k)   -> the ground's lightness 0..1 (the final pass grades with it); palette.side(k) -> 0 stage inks, 1 paper inks
//   (a scene's inks: palette.inks(ctx.k(t)), the paper amount that scene draws with)
//   palette.mix(a, b, k) -> a token mix in OKLab, linear out
//   palette.hand(datum, k) -> indigo, only for what a person chose; throws without the datum
//   palette.css(name)  -> '#rrggbb' for Canvas 2D
export const HEX = {
  stage: '#1b1611', stageInk: '#efe6da', cold: '#8cafeb', sung: '#f2b25c', stageRed: '#e0664d',
  paper: '#f4ecdc', card: '#fbf7ee', wash: '#ebe0c9', ink: '#2b231d', ink2: '#554737', ink3: '#6b5c4b',
  red: '#a3361f', hand: '#2b4474', stageHand: '#a9c2ea', rule: '#d6c8ae', ruleStrong: '#8f7d66',
  stageRule: '#3d3429', stageInk2: '#c9bba4',
  daisyYellow: '#dea833', daisyGreen: '#98a36b',
};

export const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
export const toSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
const parse = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);

export const srgb = Object.fromEntries(Object.entries(HEX).map(([k, v]) => [k, parse(v)]));
export const lin = Object.fromEntries(Object.entries(srgb).map(([k, v]) => [k, v.map(toLinear)]));

// OKLab from linear sRGB and back
function oklab([r, g, b]) {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}
function fromOklab([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s].map((v) => Math.max(v, 0));
}

const asLin = (c) => (typeof c === 'string' ? lin[c] : c);
export function mix(a, b, k) {
  if (k <= 0) return asLin(a).slice();
  if (k >= 1) return asLin(b).slice();
  const A = oklab(asLin(a)), B = oklab(asLin(b));
  return fromOklab(A.map((v, i) => v + (B[i] - v) * k));
}

// The ground's lightness for a paper amount k. Below FLIP the stage warms like a page under a lamp; across
// FLIP the light comes up onto paper; above it the paper whitens. The inks change sides at FLIP, so text
// on the ground is legible at every amount the record holds.
export const FLIP = 0.6;
const FLIP_BAND = 0.035;
const smooth = (a, b, x) => { const k = Math.min(Math.max((x - a) / (b - a), 0), 1); return k * k * (3 - 2 * k); };
export function light(k) {
  const lo = 0.4 * Math.min(k / FLIP, 1.2), hi = 0.62 + 0.38 * Math.max((k - FLIP) / (1 - FLIP), -0.2);
  return Math.min(Math.max(lo + (hi - lo) * smooth(FLIP - FLIP_BAND, FLIP + FLIP_BAND, k), 0), 1);
}
// 0 while the inks are the stage's, 1 once they are the paper's
export const side = (k) => smooth(FLIP - FLIP_BAND, FLIP + FLIP_BAND, k);

// the ground along its lightness: stage, a lamp-warmed dark, a lamp-warmed paper, paper
const LAMP_DARK = mix('stage', 'sung', 0.2), LAMP_LIGHT = mix('paper', 'sung', 0.14);
export function groundAt(u) {
  if (u <= 0.4) return mix('stage', LAMP_DARK, u / 0.4);
  if (u <= 0.62) return mix(LAMP_DARK, LAMP_LIGHT, (u - 0.4) / 0.22);
  return mix(LAMP_LIGHT, 'paper', (u - 0.62) / 0.38);
}

// the inks for a paper amount k (0 stage, 1 paper), linear light
const PAIRS = {
  ink: ['stageInk', 'ink'], ink2: ['stageInk2', 'ink2'], red: ['stageRed', 'red'], rule: ['stageRule', 'rule'],
  ruleStrong: ['ruleStrong', 'ruleStrong'], sung: ['sung', 'red'], cold: ['cold', 'ink2'], card: ['stage', 'card'],
};
export function inks(k) {
  const u = light(k), s = side(k), out = { k, light: u, side: s, ground: groundAt(u) };
  for (const [name, [a, b]] of Object.entries(PAIRS)) out[name] = mix(a, b, s);
  return out;
}

// indigo marks only what a person chose: the caller hands over the datum that says so
export function hand(datum, k = 1) {
  if (datum === undefined || datum === null || datum === false) throw new Error('palette.hand needs the datum a person chose');
  return mix('stageHand', 'hand', k);
}

export const css = (name) => HEX[name];
export const cssOf = (linRgb) => '#' + linRgb.map((c) => Math.round(Math.min(Math.max(toSrgb(c), 0), 1) * 255).toString(16).padStart(2, '0')).join('');

export function makePalette(timeline) {
  return { HEX, srgb, lin, mix, inks, hand, css, cssOf, toLinear, toSrgb, light, side, groundAt, FLIP };
}
