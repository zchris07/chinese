"""Translate pending passage sentences to English with the Claude Message Batches API.

process.py writes data/raw/wiki/pending.jsonl (passages whose sentences have no
cached translation). This script submits one batch request per passage, waits,
and appends results to data/raw/wiki/translations.jsonl ({key, zh, en}).
Re-run process.py afterwards to merge translations into the build.

Needs Anthropic credentials (ANTHROPIC_API_KEY or an `ant auth login` profile).

    python scripts/wiki/translate.py            # submit, wait, collect
    python scripts/wiki/translate.py --limit 20 # small trial run first
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

ROOT = Path(__file__).resolve().parents[2]
PENDING = ROOT / 'data/raw/wiki/pending.jsonl'
CACHE = ROOT / 'data/raw/wiki/translations.jsonl'

SYSTEM = (
    'You translate Simplified Chinese encyclopedia sentences into natural, accurate English '
    'for language learners. Translate each sentence on its own so it lines up with the '
    'Chinese, but use the surrounding sentences for context. Keep names in their usual '
    'English form. Return exactly one translation per input sentence, in order.'
)


def key(zh):
    return hashlib.sha1(zh.encode('utf8')).hexdigest()


def schema(n):
    return {
        'type': 'object',
        'properties': {
            'translations': {'type': 'array', 'items': {'type': 'string'}, 'minItems': n, 'maxItems': n},
        },
        'required': ['translations'],
        'additionalProperties': False,
    }


def build_request(passage, model):
    numbered = '\n'.join(f'{i + 1}. {s}' for i, s in enumerate(passage['sentences']))
    return Request(
        custom_id=passage['id'],
        params=MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=8000,
            output_config={'effort': 'low', 'format': {'type': 'json_schema', 'schema': schema(len(passage['sentences']))}},
            system=SYSTEM,
            messages=[{'role': 'user', 'content': f'Translate these {len(passage["sentences"])} sentences:\n\n{numbered}'}],
        ),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', default='claude-opus-5-5')
    ap.add_argument('--limit', type=int, default=0, help='only send the first N passages')
    args = ap.parse_args()

    passages = [json.loads(l) for l in PENDING.open(encoding='utf8')] if PENDING.exists() else []
    if args.limit:
        passages = passages[:args.limit]
    if not passages:
        print('nothing pending')
        return
    by_id = {p['id']: p for p in passages}

    client = anthropic.Anthropic()
    batch = client.messages.batches.create(requests=[build_request(p, args.model) for p in passages])
    print(f'batch {batch.id}: {len(passages)} passages')

    while batch.processing_status != 'ended':
        time.sleep(30)
        batch = client.messages.batches.retrieve(batch.id)
        c = batch.request_counts
        print(f'  {batch.processing_status}: {c.processing} processing, {c.succeeded} done, {c.errored} errored')

    ok = failed = 0
    with CACHE.open('a', encoding='utf8') as f:
        for res in client.messages.batches.results(batch.id):
            p = by_id[res.custom_id]
            if res.result.type != 'succeeded':
                failed += 1
                print(f'  {res.custom_id}: {res.result.type}')
                continue
            msg = res.result.message
            if msg.stop_reason == 'refusal':
                failed += 1
                print(f'  {res.custom_id}: refused')
                continue
            text = next((b.text for b in msg.content if b.type == 'text'), '')
            out = json.loads(text)['translations']
            if len(out) != len(p['sentences']):
                failed += 1
                print(f'  {res.custom_id}: got {len(out)} translations for {len(p["sentences"])} sentences')
                continue
            for zh, en in zip(p['sentences'], out):
                f.write(json.dumps({'key': key(zh), 'zh': zh, 'en': en.strip()}, ensure_ascii=False) + '\n')
            ok += 1
    print(f'translated {ok} passages, {failed} failed. Now re-run: python scripts/wiki/process.py')


if __name__ == '__main__':
    main()
