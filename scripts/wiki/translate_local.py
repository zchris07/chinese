"""Free offline translation of pending sentences with Argos Translate (no API key).

Reads data/raw/wiki/pending.jsonl (written by scripts/pool/build_pool.py) and appends each new
translation to data/raw/wiki/translations.jsonl as it goes, so it can be stopped
and resumed. Re-run build_pool.py afterwards to merge.

    pip install argostranslate
    python scripts/wiki/translate_local.py            # all pending
    python scripts/wiki/translate_local.py --limit 20 # first 20 passages
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import argostranslate.package as pkg
import argostranslate.translate as tr

ROOT = Path(__file__).resolve().parents[2]
PENDING = ROOT / 'data/raw/wiki/pending.jsonl'
CACHE = ROOT / 'data/raw/wiki/translations.jsonl'
ENGINE = 'argos'


def key(zh):
    return hashlib.sha1(zh.encode('utf8')).hexdigest()


def ensure_model():
    if any(l.code == 'zh' for l in tr.get_installed_languages()):
        return
    pkg.update_package_index()
    p = next(x for x in pkg.get_available_packages() if x.from_code == 'zh' and x.to_code == 'en')
    pkg.install_from_path(p.download())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='only the first N passages')
    args = ap.parse_args()

    ensure_model()
    done = set()
    if CACHE.exists():
        done = {json.loads(l)['key'] for l in CACHE.open(encoding='utf8')}
    passages = [json.loads(l) for l in PENDING.open(encoding='utf8')] if PENDING.exists() else []
    if args.limit:
        passages = passages[:args.limit]
    todo = list(dict.fromkeys(s for p in passages for s in p['sentences'] if key(s) not in done))
    print(f'{len(todo)} sentences to translate from {len(passages)} passages')

    start = time.time()
    with CACHE.open('a', encoding='utf8') as f:
        for i, zh in enumerate(todo, 1):
            en = tr.translate(zh, 'zh', 'en').strip()
            f.write(json.dumps({'key': key(zh), 'zh': zh, 'en': en, 'engine': ENGINE}, ensure_ascii=False) + '\n')
            f.flush()
            if i % 100 == 0:
                rate = (time.time() - start) / i
                print(f'  {i}/{len(todo)}  ~{rate * (len(todo) - i) / 60:.0f} min left')
    print('done. Now re-run: python scripts/pool/build_pool.py')


if __name__ == '__main__':
    main()
