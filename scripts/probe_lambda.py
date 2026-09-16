#!/usr/bin/env python
"""One strict Expert-opponents decision through a play API, with the judge
backend's counters before and after — the play v1.5 acceptance probe
(checks/play.md P-1.5-2):

    python scripts/probe_lambda.py --api https://bridge-play.icycookie.xyz
    python scripts/probe_lambda.py --api http://127.0.0.1:8001 --decision 24

Board 17 (1NT by West), West's decision at the given play index (default 12,
the ♦3 at trick 4), 40 deals, strict, escalation off so the sample is the
base 40 and the run is short. Prints the grade, the expert counts and the
backend counters; on a `lambda` backend the difference in `invocations` /
`remote_items` says how much went remote and `fallback_groups` /
`sha_mismatch` must stay at zero. The grade is the same whichever backend
answers — that is the seam's contract.
"""
import argparse
import json
import time
import urllib.request

HANDS = {'N': '9872.K85.AJ542.5', 'E': 'QJ6.A632.KQ.J976',
         'S': 'KT3.JT7.87.KQ843', 'W': 'A54.Q94.T963.AT2'}
PLAY = ('S9 SJ SK S5  ST S4 S2 SQ  C6 C4 CT C5  D3 D5 DQ D7  H2 HT HQ HK '
        'S8 S6 S3 SA  H4 H8 H3 H7  S7 C7 C3 C2  DA DK D8 D6  DJ').split()
COUNTERS = ('invocations', 'remote_items', 'remote_layouts', 'fallback_groups',
            'errors', 'sha_mismatch', 'remote_seconds')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--api', default='http://127.0.0.1:8001')
    ap.add_argument('--decision', type=int, default=12)
    ap.add_argument('--deals', type=int, default=40)
    ap.add_argument('--json', action='store_true', help='print the full result as JSON')
    args = ap.parse_args()
    base = args.api.rstrip('/')

    def get(path):
        with urllib.request.urlopen(base + path, timeout=1800) as r:
            return json.load(r)

    def post(path, body):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=1800) as r:
            return json.load(r)

    before = get('/api/play/debug/judge')
    body = {'hands': HANDS, 'level': 1, 'strain': 'N', 'declarer': 'W', 'play': PLAY,
            'seat': 'W', 'method': 'single_dummy', 'num_deals': args.deals,
            'expert_opponents': True, 'expert': {'strict': True},
            'escalation': None, 'decisions': [args.decision]}
    t0 = time.perf_counter()
    out = post('/api/play/analyze', body)
    seconds = round(time.perf_counter() - t0, 1)
    after = get('/api/play/debug/judge')
    d = out['decisions'][0]

    if args.json:
        print(json.dumps({'seconds': seconds, 'decision': d, 'before': before,
                          'after': after}, indent=1))
        return
    x = d['expert'] or {}
    print(f"{args.api}: backend {after.get('kind')}"
          + (f" ({after.get('function')}, G={after.get('group_size')}, K={after.get('concurrency')})"
             if after.get('kind') == 'lambda' else ''))
    print(f"decision {d['index']} {d['card']}: {d['status']}, "
          f"{d['actual_tricks']} / {d['best_tricks']} tricks, best {'/'.join(d['best_cards'])}, "
          f"{seconds} s")
    print(f"expert: sampled {x.get('sampled')}, consistent {x.get('consistent')}, "
          f"judged {x.get('judged')}, memo hits {x.get('memo_hits')}, inference {x.get('inference')}")
    if after.get('kind') == 'lambda':
        delta = {k: round(after.get(k, 0) - before.get(k, 0), 2) for k in COUNTERS}
        print('remote this run: ' + ', '.join(f'{k} {v}' for k, v in delta.items()))
        if after.get('last_error'):
            print('last error:', after['last_error'])


if __name__ == '__main__':
    main()
