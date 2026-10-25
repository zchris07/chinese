"""Download the dictionaries the passage pipeline needs (not committed: large raw data).

    python scripts/wiki/download.py
"""
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parents[2] / 'data/raw'
FILES = {
    'cedict/cedict.txt.gz': 'https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz',  # CC BY-SA 4.0
    'hsk/complete.json': 'https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/main/complete.json',  # MIT
}

for rel, url in FILES.items():
    dest = RAW / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, timeout=120, headers={'User-Agent': 'JadeMandarinPilot/0.1'})
    r.raise_for_status()
    dest.write_bytes(r.content)
    print(f'{rel}: {len(r.content) / 1e6:.1f} MB')
