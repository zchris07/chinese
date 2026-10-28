"""Build the sentence pool the app draws from: data/build/pool/{index.json, <tier>-NNN.json}.

Three sources, each sentence analysed the same way (words, pinyin, traditional, definitions, tier):
  1. grammar examples   data/merged/hsk_merged.csv  (type=example, from the Language Player sheet)
  2. Tatoeba pairs       data/raw/tatoeba/*  (human translations, CC BY 2.0 FR; a random sample per tier)
  3. Wikipedia sentences data/raw/wiki/articles.jsonl + translations.jsonl (cached Argos translations)
     Only translated sentences ship. The rest are queued in data/raw/wiki/pending.jsonl for
     scripts/wiki/translate_local.py; re-run this script afterwards.

Word data (HSK 3.0 level, part of speech, definitions) comes from the merged CSV; anything it lacks
falls back to CC-CEDICT. Tier = how much of the sentence stays inside HSK 3.0 bands (see tier_of).

    python scripts/merge/build_merged.py     # once, or after editing the sheets
    python scripts/pool/build_pool.py
"""
import argparse
import bz2
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import jieba
from pypinyin import Style, lazy_pinyin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from wiki.process import (CJK, T2S, good_paragraph, kind_of, load_cedict, paragraphs, pick_defs,  # noqa: E402
                          split_sentences, strip_tone, tokenize, traditional)

RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/build/pool'
TIERS = ['simple', 'ordinary', 'complex', 'advanced', 'scholar']
SCHOLAR = TIERS.index('scholar')  # every Wikipedia sentence, whatever its vocabulary
BEYOND = 8  # level given to words that are not in the HSK 3.0 list
COVER = 0.9  # share of words that must sit inside a band for the sentence to belong to it
POS = {'N': 'noun', 'V': 'verb', 'Adj': 'adjective', 'Adv': 'adverb', 'M': 'measure word', 'Conj': 'conjunction',
       'Pron': 'pronoun', 'Prep': 'preposition', 'Aux': 'auxiliary verb', 'Num': 'numeral', 'Intj': 'interjection',
       'Suffix': 'suffix', 'Prefix': 'prefix', 'Phonetic': 'phonetic'}
LICENSE_WIKI = 'CC BY-SA 4.0'


def normalize_zh(s):
    """No spaces; full-width punctuation (but leave 1,000 / 3.14 / 10:30 alone)."""
    s = re.sub(r'\s+', '', s)
    for a, b in ((',', '，'), (':', '：'), (';', '；'), ('?', '？'), ('!', '！')):
        s = re.sub(rf'(?<!\d){re.escape(a)}(?!\d)', b, s)
    return s


def band(level):
    """HSK 3.0 level -> tier index: 1-2 simple, 3-4 ordinary, 5-6 complex, 7-9 or unlisted advanced."""
    return 0 if level <= 2 else 1 if level <= 4 else 2 if level <= 6 else 3


def tier_of(levels):
    """Smallest tier that contains at least COVER of the sentence's words."""
    if not levels:
        return 0
    bands = [band(l) for l in levels]
    for t in range(4):
        if sum(1 for b in bands if b <= t) / len(bands) >= COVER:
            return t
    return 3


def pos_text(code):
    return '/'.join(POS.get(p, p.lower()) for p in code.split('/')) if code else ''


# ---------- lexicon (merged CSV) ----------
def loose(py):
    return strip_tone(re.sub(r"[\s'\-]", '', py)).replace('ü', 'v')


def load_lexicon():
    lex = defaultdict(list)
    for r in csv.DictReader(open(ROOT / 'data/merged/hsk_merged.csv', encoding='utf-8-sig')):
        if r['type'] != 'word':
            continue
        lex[r['simplified']].append({
            'py': r['pinyin'], 'key': loose(r['pinyin']), 't': r['traditional'], 'pos': pos_text(r['pos']),
            'defs': [d for d in r['definition'].split(' | ') if d], 'hsk': int(r['hsk3_level']) if r['hsk3_level'] else None,
            'freq': int(r['frequency_rank']) if r['frequency_rank'] else 10 ** 6,
        })
    return lex


def is_proper(w, cedict):
    """Names (美国, 李) should not make a sentence harder: CC-CEDICT capitalises proper-noun readings."""
    es = cedict.get(w, [])
    return bool(es) and all(e['py'][0][:1].isupper() or (e['defs'] and e['defs'][0].startswith('surname')) for e in es)


def token_level(w, syl, lex, cedict):
    """HSK 3.0 level of a token; None for names. Unlisted compounds (这个, 不是) take the level of their parts."""
    e = lookup(lex, w, syl)
    if e and e['hsk']:
        return e['hsk']
    if is_proper(w, cedict):
        return None
    if len(w) > 1:
        levels, i = [], 0
        while i < len(w):
            for j in range(len(w), i, -1):
                hit = lex.get(w[i:j])
                lv = min((x['hsk'] for x in hit if x['hsk']), default=None) if hit else None
                if lv:
                    levels.append(lv)
                    i = j
                    break
            else:
                return BEYOND
        return max(levels)
    return BEYOND


def lookup(lex, w, syl):
    es = lex.get(w)
    if not es:
        return None
    key = loose(''.join(syl))
    return next((e for e in es if e['key'] == key), None) or min(es, key=lambda e: e['hsk'] or 99)


# ---------- sentence sources ----------
def sentence_ok(s, min_cjk=6, max_cjk=80):
    n = len(s)
    cjk = len(CJK.findall(s))
    return (min_cjk <= cjk <= max_cjk and cjk / n >= 0.8 and s.endswith(('。', '！', '？', '”', '」', '』'))
            and s.count('（') == s.count('）') and s.count('“') == s.count('”') and s.count('「') == s.count('」')
            and not re.search(r'[A-Za-z]{4,}|\d{5,}', s))


def grammar_examples():
    out = []
    for r in csv.DictReader(open(ROOT / 'data/merged/hsk_merged.csv', encoding='utf-8-sig')):
        if r['type'] != 'example' or not r['example_zh'] or not r['example_en']:
            continue
        zh = r['example_zh'].strip()
        if len(CJK.findall(zh)) < 4 or not zh.endswith(('。', '！', '？', '”', ')', '）')):
            continue  # fragments such as 五个学生 or 十一点十分
        code = r['textbook_code']
        level = 7 if code.startswith('7-9') else int(code.split('.')[0])
        src = {'type': 'grammar', 'title': r['structure'], 'code': code, 'license': 'Language Player grammar chart (third-party course material)'}
        if r['lesson_url']:
            src['url'] = r['lesson_url']
        if r['translation_source'].startswith('sheet-machine'):
            src['translation'] = 'Machine translation (unreviewed)'
        out.append({'id': r['id'], 's': zh, 'en': r['example_en'], 'floor': band(level), 'source': src})
    return out


def tatoeba_sentences(args):
    """Mandarin sentences that have a human English translation (CC BY 2.0 FR)."""
    base = RAW / 'tatoeba'
    if not (base / 'cmn_sentences.tsv.bz2').exists():
        return []
    cmn = {}
    for line in bz2.open(base / 'cmn_sentences.tsv.bz2', 'rt', encoding='utf8'):
        i, _, text = line.rstrip('\n').split('\t')
        text = T2S.convert(text).strip()
        if sentence_ok(text, min_cjk=3, max_cjk=45):
            cmn[i] = text
    links = {}
    for line in bz2.open(base / 'cmn-eng_links.tsv.bz2', 'rt', encoding='utf8'):
        a, b = line.split()
        if a in cmn:
            links.setdefault(a, b)
    wanted = set(links.values())
    eng = {}
    for line in bz2.open(base / 'eng_sentences.tsv.bz2', 'rt', encoding='utf8'):
        i, _, text = line.rstrip('\n').split('\t')
        if i in wanted:
            eng[i] = text.strip()
    out = []
    for i, e in links.items():
        if e in eng:
            out.append({'id': f'tatoeba-{i}', 's': cmn[i], 'en': eng[e], 'floor': 0,
                        'source': {'type': 'tatoeba', 'title': f'Tatoeba #{i}', 'url': f'https://tatoeba.org/en/sentences/show/{i}',
                                   'license': 'CC BY 2.0 FR'}})
    return out


def wiki_sentences(args, rng):
    cache_file = RAW / 'wiki/translations.jsonl'
    cache = {}
    if cache_file.exists():
        cache = {r['key']: (r['en'], r.get('engine', 'claude')) for r in map(json.loads, cache_file.open(encoding='utf8'))}
    out, seen, rejected = [], set(), Counter()
    articles = RAW / 'wiki/articles.jsonl'
    if not articles.exists():
        return out, rejected
    for line in articles.open(encoding='utf8'):
        art = json.loads(line)
        taken = 0
        paras = paragraphs(art['text'])
        rng.shuffle(paras)
        for p in paras:
            for s in split_sentences(p):
                h = hashlib.sha1(s.encode('utf8')).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                if not sentence_ok(s):
                    rejected['not a clean sentence'] += 1
                    continue
                en, engine = cache.get(h, ('', None))
                if taken >= args.per_article:
                    rejected['article quota'] += 1
                    continue
                taken += 1
                src = {'type': 'wikipedia', 'title': T2S.convert(art['title']), 'url': art['url'], 'license': LICENSE_WIKI}
                if en:
                    src['translation'] = 'Argos (offline machine translation)' if engine == 'argos' else 'Claude'
                out.append({'id': f"wiki-{art['pageid']}-{h[:6]}", 's': s, 'en': en, 'floor': 0, 'source': src})
    return out, rejected


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per-article', type=int, default=25, help='max Wikipedia sentences per article')
    ap.add_argument('--tatoeba-cap', type=int, default=700, help='max Tatoeba sentences kept per tier')
    ap.add_argument('--shard-size', type=int, default=150)
    ap.add_argument('--max-unknown', type=float, default=0.02, help='max share of characters missing from CC-CEDICT')
    ap.add_argument('--allow-untranslated', action='store_true', help='ship sentences without an English translation')
    ap.add_argument('--seed', type=int, default=11)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    cedict = load_cedict()
    lex = load_lexicon()
    for w, es in lex.items():  # keep HSK words whole when jieba segments
        if len(w) > 1 and jieba.get_FREQ(w) is None:
            jieba.add_word(w, freq=3000)

    wiki, rejected = wiki_sentences(args, rng)
    gram = grammar_examples()
    tat = tatoeba_sentences(args)
    print(f'{len(gram)} grammar examples, {len(tat)} Tatoeba pairs, {len(wiki)} Wikipedia sentences; Wikipedia rejected: {dict(rejected)}')

    pool, dropped = [], Counter()
    for item in gram + wiki + tat:
        item['s'] = normalize_zh(item['s'])
        toks = tokenize(item['s'], cedict)
        hz = [c for t in toks for c in t['w'] if CJK.match(c)]
        if sum(1 for c in hz if c not in cedict) / max(1, len(hz)) > args.max_unknown:
            dropped['unknown characters'] += 1
            continue
        levels = []
        for t in toks:
            if t['kind'] in ('word', 'char'):
                lv = token_level(t['w'], t['syl'], lex, cedict)
                if lv:
                    levels.append(lv)
        tier = SCHOLAR if item['source']['type'] == 'wikipedia' else max(item['floor'], tier_of(levels))
        item.update(toks=toks, trad=traditional(toks), tier=tier)
        pool.append(item)
    print('dropped:', dict(dropped))

    # Tatoeba is huge and easy: keep a random sample per tier so it does not drown the other sources.
    keep = []
    rng.shuffle(pool)
    taken = Counter()
    for it in pool:
        if it['source']['type'] == 'tatoeba':
            if taken[it['tier']] >= args.tatoeba_cap:
                continue
            taken[it['tier']] += 1
        keep.append(it)
    pool = keep

    # Wikipedia sentences still waiting for an English translation.
    todo = [it for it in pool if not it['en']]
    rng.shuffle(todo)
    with (RAW / 'wiki/pending.jsonl').open('w', encoding='utf8') as f:
        for it in todo:
            f.write(json.dumps({'id': it['id'], 'tier': TIERS[it['tier']], 'sentences': [it['s']]}, ensure_ascii=False) + '\n')
    print(f'{len(todo)} sentences waiting for translation (by tier: ' + str({TIERS[t]: sum(1 for it in todo if it["tier"] == t) for t in range(len(TIERS))}) + ')')
    if not args.allow_untranslated:
        pool = [it for it in pool if it['en']]

    corpus_freq = Counter(t['w'] for it in pool for t in it['toks'] if t['kind'] in ('word', 'char'))
    candidates = defaultdict(set)
    for w in set(corpus_freq) | set(lex):
        if len(w) > 1 and (w in cedict or w in lex):
            for c in set(w):
                candidates[c].add(w)

    def rank(w):
        es = lex.get(w, [])
        return (min((e['hsk'] or 9 for e in es), default=9), -corpus_freq.get(w, 0), min((e['freq'] for e in es), default=10 ** 6))

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*.json'):
        old.unlink()
    index = {'shardSize': args.shard_size, 'tiers': {}, 'sources': dict(Counter(it['source']['type'] for it in pool))}
    for ti, tier in enumerate(TIERS):
        group = [it for it in pool if it['tier'] == ti]
        rng.shuffle(group)
        files = []
        for si in range(0, len(group), args.shard_size):
            chunk = group[si:si + args.shard_size]
            words, chars, sents = {}, {}, []

            def add_word(w, syl=None, ndefs=5):
                if w in words:
                    return
                e = lookup(lex, w, syl or [])
                es = cedict.get(w, [])
                py = syl or (e['py'].split() if e and ' ' in e['py'] else None) or (es[0]['py'] if es else lazy_pinyin(w, style=Style.TONE))
                if len(py) != len(w):
                    py = es[0]['py'] if es and len(es[0]['py']) == len(w) else lazy_pinyin(w, style=Style.TONE)
                defs = (e['defs'] if e and e['defs'] else (pick_defs(es, py) if es else []))[:ndefs]
                entry = {'py': py, 'defs': defs}
                trad = (e['t'] if e and e['t'] else (es[0]['t'] if es else '')) or w
                if trad != w:
                    entry['t'] = trad
                if e and e['hsk']:
                    entry['hsk'] = e['hsk']
                if e and e['pos']:
                    entry['pos'] = e['pos']
                words[w] = entry

            for it in chunk:
                tokens = []
                for t, tr in zip(it['toks'], it['trad']):
                    tok = {'w': t['w'], 'kind': t['kind']}
                    if tr != t['w']:
                        tok['t'] = tr
                    if t['kind'] in ('word', 'char'):
                        tok['py'] = ' '.join(t['syl'])
                        add_word(t['w'], t['syl'])
                    tokens.append(tok)
                sents.append({'id': it['id'], 's': it['s'], 't': ''.join(it['trad']), 'en': it['en'],
                              'source': it['source'], 'tokens': tokens})

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

            name = f'{tier}-{len(files):03d}.json'
            (OUT / name).write_text(json.dumps({'sentences': sents, 'words': words, 'chars': chars},
                                               ensure_ascii=False, separators=(',', ':')), encoding='utf8')
            files.append(name)
        index['tiers'][tier] = {'count': len(group), 'files': files}

    (OUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding='utf8')
    size = sum(p.stat().st_size for p in OUT.glob('*.json')) / 1e6
    by_src = Counter((TIERS[it['tier']], it['source']['type']) for it in pool)
    print(f'{len(pool)} sentences, {size:.1f} MB')
    for tier in TIERS:
        print(f"  {tier:9s} {index['tiers'][tier]['count']:5d}  (grammar {by_src[(tier, 'grammar')]}, tatoeba {by_src[(tier, 'tatoeba')]}, wikipedia {by_src[(tier, 'wikipedia')]})")


if __name__ == '__main__':
    main()
