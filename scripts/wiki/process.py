"""Turn fetched Wikipedia articles into analyzable passages for the app.

Reads   data/raw/wiki/articles.jsonl, data/raw/cedict/cedict.txt.gz,
        data/raw/hsk/complete.json, data/raw/wiki/translations.jsonl (cache)
Writes  data/build/wiki/index.json + shard-NNN.json (passages with their own
        word/char tables), and data/raw/wiki/pending.jsonl (sentences still
        needing translation, for translate.py).

    python scripts/wiki/process.py --per-article 4 --shard-size 100
"""
import argparse
import gzip
import hashlib
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import jieba
import opencc
from pypinyin import Style, lazy_pinyin

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/build/wiki'
LICENSE = 'CC BY-SA 4.0'

T2S = opencc.OpenCC('t2s')
S2T = opencc.OpenCC('s2t')
jieba.setLogLevel(60)

CJK = re.compile(r'[㐀-䶿一-鿿]')
STOP_SECTIONS = ('参考', '注释', '脚注', '外部链接', '外部連結', '参见', '延伸阅读', '扩展阅读', '相关条目', '资料来源', '来源', '文献')


# ---------- dictionaries ----------
TONES = {'a': 'āáǎàa', 'e': 'ēéěèe', 'i': 'īíǐìi', 'o': 'ōóǒòo', 'u': 'ūúǔùu', 'ü': 'ǖǘǚǜü'}


def tone_mark(syl):
    """'zhong1' -> 'zhōng', 'lu:4' -> 'lǜ'."""
    syl = syl.replace('u:', 'ü').replace('v', 'ü')
    m = re.fullmatch(r'([a-zA-Zü]+)([1-5])', syl)
    if not m:
        return syl
    base, tone = m.group(1), int(m.group(2))
    low = base.lower()
    if 'a' in low or 'e' in low:
        idx = low.index('a') if 'a' in low else low.index('e')
    elif 'ou' in low:
        idx = low.index('o')
    else:
        idx = max(i for i, c in enumerate(low) if c in 'aeiouü') if any(c in 'aeiouü' for c in low) else -1
    if idx < 0:
        return base
    ch = TONES[low[idx]][tone - 1]
    if base[idx].isupper():
        ch = ch.upper()
    return base[:idx] + ch + base[idx + 1:]


def clean_defs(raw):
    out = []
    for d in raw:
        d = d.strip()
        if not d or d.startswith(('CL:', 'old variant of', 'variant of', 'see ', 'Taiwan pr.')):
            continue
        d = re.sub(r'\[[^\]]*\]', '', d)              # drop inline pinyin like [zhong1]
        d = re.sub(r'[㐀-鿿]+\|[㐀-鿿]+', lambda m: m.group(0).split('|')[1], d)
        d = re.sub(r'\s+', ' ', d).strip(' ,;')
        if d and d not in out:
            out.append(d)
    return out


def load_cedict():
    entries = defaultdict(list)
    line_re = re.compile(r'^(\S+) (\S+) \[([^\]]+)\] /(.*)/$')
    with gzip.open(RAW / 'cedict/cedict.txt.gz', 'rt', encoding='utf8') as f:
        for line in f:
            m = line_re.match(line.strip())
            if not m:
                continue
            trad, simp, py, defs = m.groups()
            entries[simp].append({
                't': trad,
                'py': [tone_mark(s) for s in py.split()],
                'defs': clean_defs(defs.split('/')),
            })
    return entries


def load_hsk():
    levels, freq = {}, {}
    for e in json.load(open(RAW / 'hsk/complete.json', encoding='utf8')):
        old = [int(l[4:]) for l in e['level'] if l.startswith('old-')]
        new = [int(l[4:]) for l in e['level'] if l.startswith('new-')]
        levels[e['simplified']] = min(old) if old else (7 if min(new) >= 7 else min(new))
        freq[e['simplified']] = e.get('frequency') or 10 ** 6
    return levels, freq


# ---------- paragraph selection ----------
def clean_text(text):
    text = T2S.convert(text)
    text = re.sub(r'（[^（）]*[A-Za-z][^（）]*）', '', text)  # romanized names, English glosses
    text = re.sub(r'\([^()]*[A-Za-z][^()]*\)', '', text)
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'[ \t　]+', '', text)
    return unicodedata.normalize('NFC', text)


def split_sentences(p):
    parts = re.findall(r'[^。！？]+[。！？]+[”」』）]*', p)
    tail = p[sum(len(x) for x in parts):].strip()
    return parts + ([tail] if tail else [])


def good_paragraph(p):
    if not (50 <= len(p) <= 360) or p.endswith(('：', ':')):
        return False
    cjk = len(CJK.findall(p))
    if cjk / len(p) < 0.75:
        return False
    sents = split_sentences(p)
    return 2 <= len(sents) <= 6 and all(s.endswith(('。', '！', '？', '”', '」', '』', '）')) for s in sents)


def paragraphs(text):
    out = []
    for block in text.split('\n'):
        block = block.strip()
        if block.startswith('=='):
            if any(k in block for k in STOP_SECTIONS):
                break
            continue
        p = clean_text(block)
        if good_paragraph(p):
            out.append(p)
    return out


# ---------- tokens ----------
def kind_of(tok):
    if all(unicodedata.category(c).startswith(('P', 'S', 'Z')) for c in tok):
        return 'punct'
    if all(CJK.match(c) for c in tok):
        return 'word' if len(tok) > 1 else 'char'
    return 'other'


def split_known(tok, cedict):
    """Greedy longest-match split of an unknown multi-character token into dictionary words."""
    if tok in cedict or len(tok) == 1:
        return [tok]
    out, i = [], 0
    while i < len(tok):
        for j in range(len(tok), i, -1):
            if tok[i:j] in cedict or j == i + 1:
                out.append(tok[i:j])
                i = j
                break
    return out


def tokenize(sentence, cedict):
    toks = []
    for t in jieba.lcut(sentence, HMM=True):
        if not t.strip():
            continue
        toks += split_known(t, cedict) if kind_of(t) in ('word', 'char') else [t]
    syl = lazy_pinyin(toks, style=Style.TONE, errors=lambda x: [x])
    out, k = [], 0
    for t in toks:
        kind = kind_of(t)
        if kind in ('word', 'char'):
            py = syl[k:k + len(t)]
            k += len(t)
        else:
            py, k = [], k + 1
        out.append({'w': t, 'kind': kind, 'syl': py})
    if k != len(syl):  # alignment drifted; redo pinyin token by token
        for o in out:
            if o['kind'] in ('word', 'char'):
                o['syl'] = lazy_pinyin(o['w'], style=Style.TONE)
    return out


def traditional(tokens):
    simp = ''.join(t['w'] for t in tokens)
    trad = S2T.convert(simp)
    if len(trad) != len(simp):
        return [S2T.convert(t['w']) for t in tokens]
    out, i = [], 0
    for t in tokens:
        out.append(trad[i:i + len(t['w'])])
        i += len(t['w'])
    return out


def strip_tone(s):
    return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower()


def pick_defs(entries, syl):
    """Definitions with the reading that matches this context first."""
    want = [strip_tone(s) for s in syl]
    ranked = sorted(entries, key=lambda e: [strip_tone(s) for s in e['py']] != want)
    defs = []
    for e in ranked:
        defs += [d for d in e['defs'] if d not in defs]
    return defs[:5]


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-article', type=int, default=4)
    ap.add_argument('--shard-size', type=int, default=100)
    ap.add_argument('--max-unknown', type=float, default=0.02, help='max share of chars missing from CC-CEDICT')
    ap.add_argument('--seed', type=int, default=11)
    args = ap.parse_args()

    cedict = load_cedict()
    hsk, freq = load_hsk()
    cache_file = RAW / 'wiki/translations.jsonl'
    cache = {}
    if cache_file.exists():
        cache = {r['key']: (r['en'], r.get('engine', 'claude')) for r in map(json.loads, cache_file.open(encoding='utf8'))}

    rng = random.Random(args.seed)
    passages, seen, rejected = [], set(), Counter()
    for line in (RAW / 'wiki/articles.jsonl').open(encoding='utf8'):
        art = json.loads(line)
        paras = paragraphs(art['text'])
        rng.shuffle(paras)
        taken = 0
        for pi, p in enumerate(paras):
            if taken >= args.per_article:
                break
            h = hashlib.sha1(p.encode('utf8')).hexdigest()
            if h in seen:
                rejected['duplicate'] += 1
                continue
            seen.add(h)
            sents = []
            for s in split_sentences(p):
                toks = tokenize(s, cedict)
                trad = traditional(toks)
                sents.append({'s': s, 'toks': toks, 'trad': trad})
            hz = [c for s in sents for c in s['s'] if CJK.match(c)]
            unknown = sum(1 for c in hz if c not in cedict)
            if unknown / len(hz) > args.max_unknown:
                rejected['unknown characters'] += 1
                continue
            passages.append({'id': f"wiki-{art['pageid']}-{pi}", 'title': T2S.convert(art['title']),
                             'url': art['url'], 'sents': sents})
            taken += 1

    rng.shuffle(passages)

    # Global word frequency in the corpus, for ranking "words with this character".
    corpus_freq = Counter(t['w'] for p in passages for s in p['sents'] for t in s['toks']
                          if t['kind'] in ('word', 'char'))
    candidates = defaultdict(set)  # char -> words containing it
    for w in set(corpus_freq) | set(hsk):
        if w in cedict and len(w) > 1:
            for c in set(w):
                candidates[c].add(w)

    def rank(w):
        return (hsk.get(w, 8), -corpus_freq.get(w, 0), freq.get(w, 10 ** 6))

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('shard-*.json'):
        old.unlink()
    pending, shards = [], []
    level_counts = Counter()
    for si in range(0, len(passages), args.shard_size):
        chunk = passages[si:si + args.shard_size]
        words, chars, out = {}, {}, []

        def add_word(w, syl=None, ndefs=5):
            if w in words:
                return
            es = cedict.get(w, [])
            py = syl or (es[0]['py'] if es else lazy_pinyin(w, style=Style.TONE))
            entry = {'py': py, 'defs': pick_defs(es, py)[:ndefs] if es else []}
            trad = es[0]['t'] if es else S2T.convert(w)
            if trad != w:
                entry['t'] = trad
            if w in hsk:
                entry['hsk'] = hsk[w]
            words[w] = entry

        for p in chunk:
            sentences, levels, missing, engines = [], [], [], set()
            for s in p['sents']:
                tokens = []
                for t, tr in zip(s['toks'], s['trad']):
                    tok = {'w': t['w'], 'kind': t['kind']}
                    if tr != t['w']:
                        tok['t'] = tr
                    if t['kind'] in ('word', 'char'):
                        tok['py'] = ' '.join(t['syl'])
                        add_word(t['w'], t['syl'])
                        levels.append(hsk.get(t['w'], 7))
                    tokens.append(tok)
                en, engine = cache.get(hashlib.sha1(s['s'].encode('utf8')).hexdigest(), ('', None))
                if en:
                    engines.add(engine)
                else:
                    missing.append(s['s'])
                sentences.append({'s': s['s'], 't': ''.join(s['trad']), 'en': en, 'tokens': tokens})
            beyond = sum(1 for l in levels if l >= 7) / len(levels)
            advanced = sum(1 for l in levels if l >= 5) / len(levels)
            level_counts['translated' if not missing else 'untranslated'] += 1
            source = {'type': 'wikipedia', 'title': p['title'], 'url': p['url'], 'license': LICENSE}
            if engines:
                source['translation'] = 'Argos (offline machine translation)' if 'argos' in engines else 'Claude'
            out.append({'id': p['id'], 'source': source,
                        'stats': {'tokens': len(levels), 'beyondHsk': round(beyond, 3), 'hsk5plus': round(advanced, 3)},
                        'sentences': sentences})
            if missing:
                pending.append({'id': p['id'], 'sentences': [s['s'] for s in p['sents']]})

        for w in list(words):
            for c in w:
                if c in chars or not CJK.match(c):
                    continue
                m = []
                for e in cedict.get(c, []):
                    m += [d for d in e['defs'] if d not in m]
                rel = sorted(candidates.get(c, ()), key=rank)[:6]
                chars[c] = {'m': '; '.join(m[:4]), 'words': rel}
                for r in rel:
                    add_word(r, ndefs=2)

        name = f'shard-{len(shards):03d}.json'
        (OUT / name).write_text(json.dumps({'passages': out, 'words': words, 'chars': chars},
                                           ensure_ascii=False, separators=(',', ':')), encoding='utf8')
        shards.append({'file': name, 'count': len(out)})

    (OUT / 'index.json').write_text(json.dumps({'source': 'zh.wikipedia.org featured articles (典范条目)',
                                                'license': LICENSE, 'count': len(passages), 'shards': shards},
                                               ensure_ascii=False, indent=1), encoding='utf8')
    with (RAW / 'wiki/pending.jsonl').open('w', encoding='utf8') as f:
        for p in pending:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')

    size = sum((OUT / s['file']).stat().st_size for s in shards) / 1e6
    print(f'{len(passages)} passages in {len(shards)} shards ({size:.1f} MB); rejected: {dict(rejected)}')
    print(f'translation: {dict(level_counts)}; pending written for {len(pending)} passages')


if __name__ == '__main__':
    main()
