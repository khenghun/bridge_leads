#!/usr/bin/env python
"""Replay the run-apps / checks pins for the built-in Board 17 example through
a running play API, the way the UI requests them:

    ../.venv/Scripts/python.exe scripts/pin_example.py [--api http://127.0.0.1:8001] [--no-expert] [--dry]

- plain: E/W (one request, West, single dummy, 40 deals)
- expert: West, 60 deals, one request per decision (forced ones included),
  the default expert block and empty expert constraints, in index order.

Prints the seat summary, the IMP/point totals, the expert seat line
(graded on X of Y) and the v1.4 sample counts (marginal / escalated). Start
the API with `BRIDGE_DDS_THREADS=4` to reproduce the checks' pins — expert
verdicts depend on the thread count through the inner batch schedule.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from measure_expert import parse_lin  # noqa: E402
from bench_play import play_players   # noqa: E402

SEATS = ['N', 'E', 'S', 'W']


def example_lin(example_id='board17-1nt'):
    text = (ROOT / 'frontend/src/apps/play/examples.ts').read_text(encoding='utf-8')
    block = text[text.index(f'id: "{example_id}"'):]
    block = block[:block.index('},')]
    m = re.search(r'lin:\s*\(([\s\S]*?)\)\s*,', block)
    parts = re.findall(r"""'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)\"""", m.group(1))
    return ''.join((a or b).encode().decode('unicode_escape') for a, b in parts)


def post(api, body, timeout=1800):
    req = urllib.request.Request(api + '/api/play/analyze', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def report(label, decisions, body_note=''):
    graded = [d for d in decisions if not d['forced']]
    opt = sum(d['status'] == 'optimal' for d in graded)
    good = sum(d['status'] == 'good' for d in graded)
    sub = sum(d['status'] == 'suboptimal' for d in graded)
    tricks = -sum(min(d['diff'], 0) for d in graded)
    imp = -sum(min(d['imp_diff'] or 0, 0) for d in graded)
    pts = -sum(min(d['score_diff'] or 0, 0) for d in graded)
    marginal = sum(1 for d in graded if d.get('sample') and not d['sample']['firm'])
    esc = sum(1 for d in graded if d.get('sample') and d['sample']['escalated'])
    ex = [d['expert'] for d in decisions if d.get('expert')]
    line = ''
    if ex:
        line = (f"; graded on {sum(e['consistent'] for e in ex)} of "
                f"{sum(e['sampled'] for e in ex)} sampled, threshold {ex[0]['threshold']}")
    print(f"{label}: {opt}/{good}/{sub} of {len(graded)} graded ({len(decisions) - len(graded)} forced), "
          f"{tricks:.2f} tricks · {imp:.2f} IMPs ({pts:.0f} points); "
          f"{marginal} marginal, {esc} escalated{line}{body_note}")
    for d in graded:
        s = d.get('sample') or {}
        print(f"   j{d['index']:2d} T{d['trick']:2d} {d['hand']} {d['card']} {d['status']:>10s}"
              f"{' ?' if s and not s['firm'] else '  '} {d['diff']:+.2f}±{s.get('se_tricks', 0):.2f}"
              f" {d['imp_diff']:+.2f}±{s.get('se_imps', 0):.2f} IMPs  deals {s.get('deals', '?')}"
              f"{'*' if s.get('escalated') else ''}"
              + (f"  {d['expert']['consistent']}/{d['expert']['sampled']}" if d.get('expert') else ''))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--api', default='http://127.0.0.1:8001')
    ap.add_argument('--no-expert', action='store_true')
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--no-escalation', action='store_true')
    ap.add_argument('--example', default='board17-1nt', help='examples.ts id')
    ap.add_argument('--seats', default=None, help='plain seats to grade, e.g. E,N,S (default W)')
    ap.add_argument('--deals', type=int, default=40)
    args = ap.parse_args()
    hands, (level, strain), declarer, vul, penalty, play = parse_lin(example_lin(args.example))
    print(f'{args.example}: {level}{strain} by {declarer}, vul {vul}, {len(play)} cards')
    if args.dry:
        return
    empty = {'hcp': {}, 'suit_length': {}, 'shapes': {}, 'quality': {}, 'fixed_cards': {}}
    base = {'hands': hands, 'level': level, 'strain': strain, 'declarer': declarer,
            'vul': vul, 'penalty': penalty, 'play': play, 'method': 'single_dummy',
            'constraints': empty}
    if args.no_escalation:
        base['escalation'] = None
    swings = []
    for seat in (args.seats.split(',') if args.seats else ['W']):
        r = post(args.api, dict(base, seat=seat, num_deals=args.deals))
        report(f'plain {seat} {args.deals}', r['decisions'])
        swings += [(d['imp_diff'], d['diff'], seat, d) for d in r['decisions']
                   if not d['forced'] and d['diff'] is not None and d['diff'] < 0]
    if args.seats:
        swings.sort(key=lambda x: (x[0], x[1]))
        print('swings (by IMPs):')
        for imp, diff, seat, d in swings:
            print(f"   T{d['trick']} {seat} ({d['hand']}) {d['card']} {imp:+.2f} IMPs {diff:+.2f} tricks {d['status']}")
    if args.no_expert or args.seats:
        return
    dummy = SEATS[(SEATS.index(declarer) + 2) % 4]
    players = play_players(declarer, strain, play)
    mine = [j for j, p in enumerate(players) if p in (declarer, dummy)]
    decisions = []
    for j in mine:
        r = post(args.api, dict(base, seat='W', num_deals=60, expert_opponents=True,
                                expert={'inner_ratio': 0.5, 'tolerance': 0.1, 'confidence': 2.0,
                                        'budget': 20, 'strict': False, 'depth': 1},
                                expert_constraints=empty, decisions=[j]))
        decisions.extend(r['decisions'])
    report('expert W 60', decisions, f' ({len(mine)} requests)')


if __name__ == '__main__':
    main()
