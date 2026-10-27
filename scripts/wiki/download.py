"""Download the dictionaries and corpora the pool pipeline needs (not committed: large raw data).

    python scripts/wiki/download.py
"""
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parents[2] / 'data/raw'
FILES = {
    'cedict/cedict.txt.gz': 'https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz',  # CC BY-SA 4.0
    'hsk/complete.json': 'https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/complete.json',  # MIT
    # Tatoeba (CC BY 2.0 FR): Mandarin sentences, English sentences, and the translation links between them
    'tatoeba/cmn_sentences.tsv.bz2': 'https://downloads.tatoeba.org/exports/per_language/cmn/cmn_sentences.tsv.bz2',
    'tatoeba/eng_sentences.tsv.bz2': 'https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2',
    'tatoeba/cmn-eng_links.tsv.bz2': 'https://downloads.tatoeba.org/exports/per_language/cmn/cmn-eng_links.tsv.bz2',
}

for rel, url in FILES.items():
    dest = RAW / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=120, headers={'User-Agent': 'JadeMandarinPilot/0.1'})
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f'{rel}: {len(r.content) / 1e6:.1f} MB')
