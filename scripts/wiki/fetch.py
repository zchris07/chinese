"""Fetch a random sample of zh.wikipedia featured articles (典范条目) as plain text.

Output: data/raw/wiki/articles.jsonl, one {pageid, title, url, text} per line.
Re-running skips articles already fetched.

    python scripts/wiki/fetch.py --count 350
"""
import argparse
import json
import random
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'data/raw/wiki/articles.jsonl'
API = 'https://zh.wikipedia.org/w/api.php'
HEADERS = {'User-Agent': 'JadeMandarinPilot/0.1 (language-learning prototype; zchris0783@gmail.com)'}
CATEGORY = 'Category:典范条目'


def api(**params):
    params.update(action='query', format='json', formatversion=2)
    for attempt in range(5):
        r = requests.get(API, params=params, headers=HEADERS, timeout=60)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def category_members():
    titles, cont = [], {}
    while True:
        d = api(list='categorymembers', cmtitle=CATEGORY, cmlimit=500, cmnamespace=0, **cont)
        titles += [m['title'] for m in d['query']['categorymembers']]
        if 'continue' not in d:
            return titles
        cont = {'cmcontinue': d['continue']['cmcontinue']}


def extract(title):
    d = api(titles=title, prop='extracts|info', inprop='url', explaintext=1,
            exsectionformat='wiki', variant='zh-cn')
    page = d['query']['pages'][0]
    return {'pageid': page.get('pageid'), 'title': page['title'],
            'url': page.get('fullurl'), 'text': page.get('extract', '')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=350)
    ap.add_argument('--seed', type=int, default=7)
    args = ap.parse_args()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if OUT.exists():
        done = {json.loads(l)['title'] for l in OUT.open(encoding='utf8')}

    titles = category_members()
    print(f'{len(titles)} featured articles; {len(done)} already fetched')
    random.Random(args.seed).shuffle(titles)
    todo = [t for t in titles[:args.count] if t not in done]

    with OUT.open('a', encoding='utf8') as f:
        for i, t in enumerate(todo, 1):
            art = extract(t)
            if art['text']:
                f.write(json.dumps(art, ensure_ascii=False) + '\n')
            if i % 25 == 0:
                print(f'  {i}/{len(todo)}')
            time.sleep(0.3)
    print('done')


if __name__ == '__main__':
    main()
