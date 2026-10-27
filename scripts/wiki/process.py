"""Text helpers shared by the sentence-pool pipeline (scripts/pool/build_pool.py, scripts/merge/build_merged.py).

CC-CEDICT loading and pinyin tone marks, Wikipedia text cleaning and sentence splitting,
jieba + dictionary tokenisation, traditional conversion, and reading-aware definitions.
Not run directly.
"""
import gzip
import re
import unicodedata
from collections import defaultdict
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
