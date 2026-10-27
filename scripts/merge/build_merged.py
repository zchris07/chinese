"""Merge hsk30 + the two Google Sheets + CC-CEDICT into one CSV.

Reads   data/raw/hsk30/hsk30.csv, hsk30-grammar.csv   (primary reference, MIT)
        data/raw/hsk_vocab.xlsx, hsk_grammar.xlsx     (original sheets)
        data/raw/corrections.csv                      (audited fixes to sheet cells)
        data/raw/cedict/cedict.txt.gz, data/raw/hsk/complete.json  (python scripts/wiki/download.py)
Writes  data/merged/hsk_merged.csv, data/merged/merge_report.md

One row per word form (type=word), per HSK 3.0 grammar point (type=grammar) and per
grammar-sheet example (type=example). See COLUMNS. Run:

    python scripts/merge/build_merged.py
"""
import csv
import gzip
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from pypinyin import Style, lazy_pinyin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from wiki.process import clean_defs, tone_mark  # noqa: E402

RAW = ROOT / 'data/raw'
OUT = ROOT / 'data/merged'
CJK = re.compile(r'[㐀-䶿一-鿿]')
LEVEL_NUM = {'1': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7-9': 7}

COLUMNS = [
    'id', 'type', 'simplified', 'traditional', 'pinyin', 'pos', 'definition', 'classifiers',
    'hsk3_level', 'hsk2_level', 'frequency_rank', 'hsk30_id',
    'grammar_no', 'grammar_group', 'grammar_category', 'grammar_details',
    'textbook_code', 'structure', 'pattern', 'gloss',
    'example_zh', 'example_en', 'translation_source', 'lesson_url',
    'sheet_definition', 'source', 'license', 'notes',
]


# ---------- helpers ----------
def loose(py):
    """Pinyin key: no tones, spaces, hyphens, apostrophes or brackets; ü -> v."""
    s = unicodedata.normalize('NFD', py.lower().replace('ü', 'v').replace('u:', 'v'))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", '', s.replace('v', 'ü').replace('ü', 'v'))


def toned_key(py):
    return re.sub(r"[\s'\-()·]", '', py.lower())


def numbered_to_marks(py):
    return ' '.join(tone_mark(s) for s in py.split())


def level_value(v):
    return LEVEL_NUM.get(str(v).strip())


def clean_example(zh):
    zh = re.sub(r'(?<=[㐀-鿿，。！？、：；”」）]) +(?=[㐀-鿿，。！？、：；“「（])', '', zh.strip())
    if CJK.search(zh):
        zh = zh.replace('?', '？').replace('!', '！').replace(',', '，')
        zh = re.sub(r'(?<=[㐀-鿿])\.$', '。', zh)
    return zh


# ---------- sources ----------
def load_cedict():
    """simplified -> [{t, py(marks, spaced), key, defs, cl}]"""
    entries = defaultdict(list)
    line_re = re.compile(r'^(\S+) (\S+) \[([^\]]+)\] /(.*)/$')
    with gzip.open(RAW / 'cedict/cedict.txt.gz', 'rt', encoding='utf8') as f:
        for line in f:
            m = line_re.match(line.strip())
            if not m or line.startswith('#'):
                continue
            trad, simp, py, defs = m.groups()
            raw = defs.split('/')
            cl = []
            for d in raw:
                if d.startswith('CL:'):
                    cl += [re.sub(r'\[[^\]]*\]', '', x).split('|')[-1] for x in d[3:].split(',')]
            entries[simp].append({'t': trad, 'py': ' '.join(tone_mark(s) for s in py.split()),
                                  'key': loose(py), 'defs': clean_defs(raw), 'cl': cl})
    return entries


def pick_entries(cedict, simp, py):
    es = cedict.get(simp, [])
    want = loose(py)
    exact = [e for e in es if e['key'] == want]
    return exact, es


def load_hsk30_vocab():
    """Expand rows whose real forms live in the Variants JSON (e.g. 爸爸|爸, 第（第二）)."""
    forms = []
    for r in csv.DictReader(open(RAW / 'hsk30/hsk30.csv', encoding='utf8')):
        level = level_value(r['Level'])
        variants = []
        if r['Variants'].strip():
            try:
                variants = json.loads(r['Variants'])
            except json.JSONDecodeError:
                variants = []
        if variants:
            for i, v in enumerate(variants, 1):
                forms.append({'id': f"{r['ID']}.{i}", 'hsk30_id': r['ID'], 's': v['Simplified'], 't': v.get('Traditional', ''),
                              'py': v['Pinyin'], 'pos': v.get('POS', ''), 'level': level})
        else:
            forms.append({'id': r['ID'], 'hsk30_id': r['ID'], 's': r['Simplified'], 't': r['Traditional'],
                          'py': r['Pinyin'], 'pos': r['POS'], 'level': level})
    return forms


def load_sheet_vocab():
    ws = openpyxl.load_workbook(RAW / 'hsk_vocab.xlsx').worksheets[0]
    rows = []
    for i, (lvl, w, py, d) in enumerate(ws.iter_rows(min_row=2, max_col=4, values_only=True), 2):
        if w:
            rows.append({'row': i, 'level': int(lvl), 'w': str(w).strip(), 'py': str(py).strip(), 'd': str(d or '').strip()})
    return rows


def load_frequency():
    freq = {}
    for e in json.load(open(RAW / 'hsk/complete.json', encoding='utf8')):
        if e.get('frequency'):
            freq[e['simplified']] = e['frequency']
    return freq


def load_corrections():
    out = {}
    path = RAW / 'corrections.csv'
    if path.exists():
        for r in csv.DictReader(open(path, encoding='utf8')):
            out[(r['source_id'], r['field'])] = r
    return out


# ---------- words ----------
def build_words(cedict, freq, report):
    forms = load_hsk30_vocab()
    sheet = load_sheet_vocab()
    by_word = defaultdict(list)
    for r in sheet:
        by_word[r['w']].append(r)
    used = set()
    rows = []
    for f in forms:
        exact, allv = pick_entries(cedict, f['s'], f['py'])
        chosen = exact or allv[:1]
        defs = []
        cl = []
        for e in chosen:
            defs += [d for d in e['defs'] if d not in defs]
            cl += [c for c in e['cl'] if c not in cl]
        trad = f['t'] or (chosen[0]['t'] if chosen else '')
        # sheet row for the same word; with several readings prefer the one whose pinyin matches
        cands = [r for r in by_word.get(f['s'], []) if r['row'] not in used]
        hit = next((r for r in cands if loose(r['py']) == loose(f['py'])), cands[0] if len(cands) == 1 else None)
        notes = []
        if hit:
            used.add(hit['row'])
            if not defs and hit['d']:
                defs = [hit['d']]
                notes.append('definition taken from the vocab sheet (CC-CEDICT has only cross-references)')
        elif by_word.get(f['s']):
            notes.append('sheet has this word but with a different reading')
        if not chosen:
            notes.append('not in CC-CEDICT')
        elif not exact:
            notes.append('reading not matched in CC-CEDICT; used first entry')
        rows.append({
            'id': 'w-' + f['id'], 'type': 'word', 'simplified': f['s'], 'traditional': trad, 'pinyin': f['py'],
            'pos': f['pos'], 'definition': ' | '.join(defs[:8]), 'classifiers': ','.join(cl),
            'hsk3_level': f['level'], 'hsk2_level': hit['level'] if hit else '', 'frequency_rank': freq.get(f['s'], ''),
            'hsk30_id': f['hsk30_id'], 'sheet_definition': hit['d'] if hit else '',
            'source': 'hsk30' + ('+hsk2-sheet' if hit else ''), 'license': 'MIT (hsk30); CC BY-SA 4.0 (CC-CEDICT)',
            'notes': '; '.join(notes),
        })
    # sheet words that hsk30 does not list (mostly HSK 2.0 words dropped or restructured in 3.0)
    extra = [r for r in sheet if r['row'] not in used]
    for r in extra:
        exact, allv = pick_entries(cedict, r['w'], numbered_to_marks(r['py']))
        chosen = exact or allv[:1]
        defs, cl = [], []
        for e in chosen:
            defs += [d for d in e['defs'] if d not in defs]
            cl += [c for c in e['cl'] if c not in cl]
        notes = ['not in the HSK 3.0 list (hsk30); kept from the HSK 2.0 sheet']
        if not chosen:
            notes.append('not in CC-CEDICT')
        rows.append({
            'id': f"v2-{r['row']}", 'type': 'word', 'simplified': r['w'],
            'traditional': chosen[0]['t'] if chosen else '', 'pinyin': chosen[0]['py'] if chosen else numbered_to_marks(r['py']),
            'definition': ' | '.join(defs[:8]), 'classifiers': ','.join(cl), 'hsk3_level': '', 'hsk2_level': r['level'],
            'frequency_rank': freq.get(r['w'], ''), 'sheet_definition': r['d'], 'source': 'hsk2-sheet',
            'license': 'CC BY-SA 4.0 (CC-CEDICT); sheet terms unknown', 'notes': '; '.join(notes),
        })
    report['forms'] = len(forms)
    report['sheet_rows'] = len(sheet)
    report['sheet_matched'] = len(used)
    report['sheet_extra'] = len(extra)
    report['no_cedict'] = sum(1 for r in rows if 'not in CC-CEDICT' in r['notes'])
    report['extra_by_level'] = dict(sorted(Counter(r['level'] for r in extra).items()))
    return rows


# ---------- grammar ----------
def structure_pinyin(structure):
    """Pinyin for the Chinese runs of a structure; placeholders (V, N, #) and punctuation stay as written."""
    out = []
    for run in re.findall(r'[㐀-鿿]+|[^㐀-鿿]+', structure):
        if CJK.match(run):
            out.append(''.join(lazy_pinyin(run, style=Style.TONE)))
        else:
            out.append(run.strip().replace('／', '/') or '')
    return re.sub(r'\s+', ' ', ' '.join(o for o in out if o)).strip()



def load_hsk30_grammar():
    return list(csv.DictReader(open(RAW / 'hsk30/hsk30-grammar.csv', encoding='utf8')))


def _items(text):
    parts = re.split(r'[、；，,（）()/／+＋\s…。：:“”"*]+', text)
    return {re.sub(r'\d+', '', p) for p in parts if p}


def match_points(structure, level, points):
    """Heuristic link from a sheet structure to an hsk30 grammar point (None if not confident).

    Every Chinese token of the structure must appear in the point's content/details: a single
    character must equal one listed item exactly, a longer token may appear anywhere in the text.
    """
    toks = re.findall(r'[㐀-鿿]+', structure)
    if not toks:
        return None, 0
    norm = lambda x: re.sub(r'[\s…。，,*]+', '', x)
    whole = [p for p in points if len(norm(structure)) >= 2 and norm(structure) == norm(p['Content'])]
    if whole:
        return min(whole, key=lambda p: abs(LEVEL_NUM.get(p['Level'], 7) - level)), len(whole)
    scored = []
    for p in points:
        text = p['Content'] + ' ' + p['Details']
        items = _items(text)
        if all((t in items) if len(t) == 1 else (t in text) for t in toks):
            scored.append((sum(len(t) for t in toks), -abs(LEVEL_NUM.get(p['Level'], 7) - level), p))
    if not scored:
        return None, 0
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2], len(scored)


def build_grammar(corrections, report):
    points = load_hsk30_grammar()
    rows = []
    for p in points:
        rows.append({
            'id': f"g-{p['No']}", 'type': 'grammar', 'hsk3_level': LEVEL_NUM.get(p['Level'], ''), 'grammar_no': p['No'],
            'grammar_group': p['Group'], 'grammar_category': p['Category'], 'grammar_details': p['Details'],
            'structure': p['Content'].replace('\n', ' '), 'source': 'hsk30', 'license': 'MIT (hsk30)',
        })

    ws = openpyxl.load_workbook(RAW / 'hsk_grammar.xlsx').worksheets[0]
    stats = Counter()
    for rown, r in enumerate(ws.iter_rows(min_row=2, max_col=10, values_only=True), 2):
        sid, code, structure, pattern, _py, gloss, example, _formula, trans, url = r
        if not code:
            continue
        sid = str(int(sid)) if sid is not None else f'row{rown}'
        code = str(code)
        advanced = code.startswith('7-9')
        appendix = '.A' in code
        notes = []
        structure = (structure or '').strip()
        # 7-9 glosses are =IFERROR(DUMMYFUNCTION("GOOGLETRANSLATE(...)"),"cached text"): keep the cached text
        gloss = str(gloss or '')
        if gloss.startswith('='):
            m = re.search(r'\),"((?:[^"]|"")*)"\)$', gloss)
            gloss = m.group(1).replace('""', '"') if m else ''
        if gloss.startswith('#'):
            gloss = ''
        zh = clean_example(str(example or ''))
        en = str(trans if trans is not None else '').strip()
        if zh == '-':
            zh = ''
            notes.append('example missing in sheet')
        if en == '-':
            en = ''
        if zh.startswith('也*') or ('*' in zh):
            notes.append(f'example cell held pattern text ({zh}), not a sentence')
            zh = ''
        for field, key in (('example_zh', 'zh'), ('example_en', 'en'), ('structure', 'st'), ('gloss', 'gl')):
            c = corrections.get((sid, field))
            if c:
                old = {'zh': zh, 'en': en, 'st': structure, 'gl': gloss}[key]
                notes.append(f"corrected {field}: was '{old}' ({c['reason']})")
                if key == 'zh':
                    zh = c['new_value']
                elif key == 'en':
                    en = c['new_value']
                elif key == 'st':
                    structure = c['new_value']
                else:
                    gloss = c['new_value']
        sheet_level = 7 if advanced else int(code.split('.')[0])
        point, n = (None, 0) if (appendix or not structure) else match_points(structure, sheet_level, points)
        stats['linked' if point else 'unlinked'] += 1
        if ws.cell(rown, 2).fill.fill_type and ws.cell(rown, 2).fill.fgColor.rgb == 'FFC9DAF8':
            notes.append('highlighted in the source sheet (meaning unknown)')
        rows.append({
            'id': f'x-{sid}', 'type': 'example', 'hsk3_level': '', 'hsk2_level': '',
            'grammar_no': point['No'] if point else '', 'grammar_group': point['Group'] if point else '',
            'grammar_category': point['Category'] if point else '', 'grammar_details': point['Details'] if point else '',
            'textbook_code': code, 'structure': structure, 'pattern': (pattern or '').strip(),
            'pinyin': structure_pinyin(structure),
            'gloss': gloss, 'example_zh': zh, 'example_en': en,
            'translation_source': 'sheet-machine (7-9 band, unreviewed)' if advanced else 'sheet-human',
            'lesson_url': (url or '').strip(), 'source': 'language-player-grammar-sheet',
            'license': 'unknown (third-party course material)',
            'notes': '; '.join(notes + ([f'grammar link is a heuristic match ({n} candidates)'] if point else [])),
        })
    report['grammar_points'] = len(points)
    report['examples'] = sum(1 for r in rows if r['type'] == 'example')
    report['example_stats'] = dict(stats)
    return rows


# ---------- main ----------
def main():
    report = {}
    cedict = load_cedict()
    freq = load_frequency()
    corrections = load_corrections()
    rows = build_words(cedict, freq, report) + build_grammar(corrections, report)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / 'hsk_merged.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='raise')
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in COLUMNS})

    types = Counter(r['type'] for r in rows)
    ex_rows = [r for r in rows if r['type'] == 'example']
    md = [
        '# Merge report', '',
        f"Rows: {len(rows)} ({dict(types)}).", '',
        '## Words',
        f"- hsk30 word forms (after expanding variants): {report['forms']}",
        f"- vocab-sheet rows: {report['sheet_rows']}; matched to an hsk30 form: {report['sheet_matched']}; "
        f"not in hsk30 (kept as extra rows): {report['sheet_extra']} (by sheet level {report['extra_by_level']})",
        f"- rows with no CC-CEDICT entry: {report['no_cedict']}", '',
        '## Grammar',
        f"- hsk30 grammar points: {report['grammar_points']}",
        f"- sheet examples: {report['examples']}; linked to an hsk30 point by heuristic: {report['example_stats'].get('linked', 0)}; "
        f"unlinked (usage notes, appendix, or ambiguous): {report['example_stats'].get('unlinked', 0)}",
        f"- examples without a Chinese sentence: {sum(1 for r in ex_rows if not r['example_zh'])}",
        f"- examples with a correction applied: {sum(1 for r in ex_rows if 'corrected' in r['notes'])}", '',
    ]
    (OUT / 'merge_report.md').write_text('\n'.join(md), encoding='utf8')
    print('\n'.join(md))


if __name__ == '__main__':
    main()
