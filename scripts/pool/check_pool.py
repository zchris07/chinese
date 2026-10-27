"""Validate data/build/pool: every token resolves in the shard's word table, every character in its
character table, every related word exists, and every sentence has what the UI shows.

    python scripts/pool/check_pool.py
"""
import json
import re
import sys
from pathlib import Path

POOL = Path(__file__).resolve().parents[2] / 'data/build/pool'
CJK = re.compile(r'[㐀-䶿一-鿿]')
index = json.loads((POOL / 'index.json').read_text(encoding='utf8'))
errors, n = [], 0
for tier, info in index['tiers'].items():
    count = 0
    for f in info['files']:
        shard = json.loads((POOL / f).read_text(encoding='utf8'))
        words, chars = shard['words'], shard['chars']
        count += len(shard['sentences'])
        for s in shard['sentences']:
            n += 1
            if not s['en']:
                errors.append(f"{s['id']}: no English")
            if ''.join(t['w'] for t in s['tokens']) != s['s']:
                errors.append(f"{s['id']}: tokens do not rebuild the sentence")
            for t in s['tokens']:
                if t['kind'] in ('word', 'char'):
                    e = words.get(t['w'])
                    if not e:
                        errors.append(f"{s['id']}: {t['w']} missing from words")
                    elif len(t['py'].split()) != len(t['w']):
                        errors.append(f"{s['id']}: {t['w']} has {len(t['py'].split())} syllables")
                    for c in t['w']:
                        if CJK.match(c) and c not in chars:
                            errors.append(f"{s['id']}: {c} missing from chars")
        for c, info_c in chars.items():
            for r in info_c['words']:
                if r not in words:
                    errors.append(f'{f}: related word {r} of {c} missing from words')
    if count != info['count']:
        errors.append(f"{tier}: index says {info['count']}, shards hold {count}")
print(f'{n} sentences checked, {len(errors)} problems')
for e in errors[:30]:
    print(' ', e)
sys.exit(1 if errors else 0)
