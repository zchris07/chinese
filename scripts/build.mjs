// Offline pipeline: data/raw/* -> data/build/data.json (+ data.js for file:// use).
// Validates that every token is in the vocab and every character has a meaning.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const raw = (f) => readFileSync(join(root, 'data/raw', f), 'utf8');
const PUNCT = new Set(['。', '，', '？', '！', '、', '：', '；']);

function tsv(file) {
  const [, ...rows] = raw(file).split(/\r?\n/).filter((l) => l.trim());
  return rows.map((r) => r.split('\t'));
}

const words = {};
for (const [s, t, py, hsk, defs] of tsv('words.tsv')) {
  const syl = py.split(' ');
  if ([...s].length !== [...t].length || [...s].length !== syl.length) {
    throw new Error(`words.tsv: length mismatch for ${s}`);
  }
  words[s] = { t, py: syl, hsk: Number(hsk), defs: defs.split(';').map((d) => d.trim()) };
}

const charMeanings = Object.fromEntries(tsv('chars.tsv'));
const chars = {};
const errors = [];
for (const [s, w] of Object.entries(words)) {
  [...s].forEach((c) => {
    if (!charMeanings[c]) errors.push(`chars.tsv: missing meaning for ${c} (in ${s})`);
    chars[c] ??= { m: charMeanings[c] ?? '', words: [] };
    if (!chars[c].words.includes(s)) chars[c].words.push(s);
  });
}
for (const c of Object.values(chars)) c.words.sort((a, b) => words[a].hsk - words[b].hsk);

const sentences = [];
raw('sentences.txt').split(/\r?\n/).forEach((line, n) => {
  if (!line.trim() || line.startsWith('#')) return;
  const [zh, en] = line.split('\t');
  const tokens = zh.trim().split(/\s+/).map((w) => {
    if (PUNCT.has(w)) return { w, t: w, kind: 'punct' };
    const entry = words[w];
    if (!entry) { errors.push(`sentences.txt:${n + 1}: unknown token ${w}`); return null; }
    return { w, t: entry.t, py: entry.py.join(''), kind: [...w].length > 1 ? 'word' : 'char' };
  });
  if (tokens.includes(null)) return;
  const level = Math.max(...tokens.filter((t) => t.kind !== 'punct').map((t) => words[t.w].hsk));
  sentences.push({
    id: sentences.length,
    s: tokens.map((t) => t.w).join(''),
    t: tokens.map((t) => t.t).join(''),
    en,
    level,
    tokens,
  });
});

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}

const out = { sentences, words, chars };
mkdirSync(join(root, 'data/build'), { recursive: true });
writeFileSync(join(root, 'data/build/data.json'), JSON.stringify(out));
writeFileSync(join(root, 'data/build/data.js'), `window.APP_DATA = ${JSON.stringify(out)};\n`);

const byLevel = {};
for (const s of sentences) byLevel[s.level] = (byLevel[s.level] ?? 0) + 1;
console.log(`${sentences.length} sentences, ${Object.keys(words).length} words, ${Object.keys(chars).length} chars`);
console.log('sentences per HSK level:', byLevel);
