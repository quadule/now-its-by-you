// Run with `node --test tests/studio_piano.test.cjs`: the piano page spells as the studio does (songbird/theory.py
// spelling, tests/test_spelling.py), by the key's signature, and for a transposed key too.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../songbird/studio/piano/piano.js'), 'utf8');
const start = source.indexOf('  const LETTERS = ');
const end = source.indexOf('    return out;\n  }\n', start) + '    return out;\n  }\n'.length;
const inPage = vm.runInNewContext(`${source.slice(start, end)}; spelling`);
const spelling = (pc, mode) => [...inPage(pc, mode)];  // an array of this realm, to compare

test('the piano page spells by the key signature: G# in C# minor, E# in F# major, flats in a flat key', () => {
  assert.deepEqual(spelling(1, 'minor'), ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']);
  const dFlat = spelling(1, 'major');  // D flat major (five flats), not C sharp major (seven sharps)
  assert.equal(dFlat[1], 'Db'); assert.equal(dFlat[0], 'C'); assert.equal(dFlat[8], 'Ab');
  assert.equal(spelling(6, 'major')[5], 'E#');  // F sharp major's seventh
  assert.equal(spelling(8, 'minor')[8], 'G#');  // G sharp minor (five sharps), not A flat minor (seven flats)
  assert.equal(spelling(3, 'minor')[11], 'Cb');  // E flat minor's sixth
  assert.equal(spelling(1, 'lydian')[1], 'Db');  // no key of eight sharps: D flat lydian
  assert.deepEqual(spelling(0, 'major'), ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']);
  assert.equal(spelling(9, 'dorian')[6], 'F#');  // a mode by its own signature (A dorian: one sharp)
  for (let pc = 0; pc < 12; pc++) for (const mode of ['major', 'minor']) {
    const names = spelling(pc, mode);
    const letters = new Set([0, 2, 4, 5, 7, 9, 11].map((x) => names[(pc + (mode === 'major' ? [0, 2, 4, 5, 7, 9, 11] : [0, 2, 3, 5, 7, 8, 10])[[0, 2, 4, 5, 7, 9, 11].indexOf(x)]) % 12][0]));
    assert.equal(letters.size, 7, `${pc} ${mode}: seven letters`);
  }
});
