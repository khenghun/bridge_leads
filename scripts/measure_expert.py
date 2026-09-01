#!/usr/bin/env python
"""Measure the expert-opponents filter (play v1.3) on the six example hands.

    ../.venv/Scripts/python.exe scripts/measure_expert.py [--deals 20] [--strict] [--only board17-1nt]

For every example and every gradeable seat it grades the whole play with the
toggle off and on and prints, per seat: wall-clock, layouts examined vs kept,
how many inner judgements ran (and how many came from the memo), the observed
sd of the paired difference (the plan's sigma, planning figure 0.6), and how
the grades moved. The numbers this exists to pin down: the suspect fraction,
the memo hit rate, sigma, and the cost per seat — see the plan's
"Implementation order", step 1.

Reads the LIN text straight out of `frontend/src/apps/play/examples.ts` with a
deliberately small LIN reader (dealer, hands, auction -> contract/declarer,
`pc|` cards) that mirrors `frontend/src/lib/lin.ts`. Development tool only —
the API never takes LIN.
"""
import argparse
import re
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from engine.play import grader                      # noqa: E402
from engine.play.expert import ExpertSettings, VerdictMemo   # noqa: E402

CLOCKWISE = ['N', 'E', 'S', 'W']
DEALER = {'1': 'S', '2': 'W', '3': 'N', '4': 'E'}
BBO_ORDER = ['S', 'W', 'N', 'E']
RANKS = 'AKQJT98765432'


def examples():
    src = (ROOT / 'frontend/src/apps/play/examples.ts').read_text(encoding='utf-8')
    out = []
    for m in re.finditer(r"id:\s*\"([^\"]+)\",\s*title:\s*\"([^\"]+)\",.*?lin:\s*\(((?:\s*'[^']*'\s*\+?)+)\)", src, re.S):
        lin = ''.join(re.findall(r"'([^']*)'", m.group(3)))
        out.append((m.group(1), m.group(2), lin))
    return out


def parse_hand(text):
    suits = {'S': [], 'H': [], 'D': [], 'C': []}
    cur = None
    for ch in text.upper():
        if ch in suits:
            cur = ch
        elif cur and ch in RANKS:
            suits[cur].append(ch)
    return suits


def parse_lin(lin):
    fields = re.findall(r'([a-zA-Z]{1,3})\|([^|]*)\|', lin)
    md = next(v for k, v in fields if k.lower() == 'md')
    dealer = DEALER.get(md[0], 'N')
    raw = md[1:].split(',')
    hands = {}
    for seat, text in zip(BBO_ORDER, raw):
        if text.strip():
            hands[seat] = parse_hand(text)
    missing = [s for s in CLOCKWISE if s not in hands]
    if missing:
        used = {su: {r for h in hands.values() for r in h[su]} for su in 'SHDC'}
        hands[missing[0]] = {su: [r for r in RANKS if r not in used[su]] for su in 'SHDC'}
    pbn = {s: '.'.join(''.join(sorted(hands[s][su], key=RANKS.index)) for su in 'SHDC')
           for s in CLOCKWISE}
    sv = next((v.lower() for k, v in fields if k.lower() == 'sv'), 'o')
    vul = {'n': 'ns', 'e': 'ew', 'b': 'both'}.get(sv, 'none')
    bids = [v.replace('!', '').strip().upper() for k, v in fields if k.lower() == 'mb']
    start = CLOCKWISE.index(dealer)
    auction = [(CLOCKWISE[(start + i) % 4], b) for i, b in enumerate(bids)]
    contract, declarer, penalty = None, None, 'none'
    for player, b in auction:
        if b in ('P', 'PASS', '-'):
            continue
        if b in ('D', 'X', 'DBL'):
            penalty = 'doubled'
        elif b in ('R', 'XX', 'RDBL'):
            penalty = 'redoubled'
        else:
            contract = (int(b[0]), 'N' if b[1] == 'N' else b[1])
            penalty = 'none'
            side = {'N', 'S'} if player in 'NS' else {'E', 'W'}
            declarer = next(p for p, bb in auction
                            if p in side and bb not in ('P', 'PASS', '-', 'D', 'X', 'DBL', 'R', 'XX', 'RDBL')
                            and bb[1:] == b[1:])
    play = [v.upper().replace('10', 'T') for k, v in fields if k.lower() == 'pc']
    play = [c[0] + c[1] for c in play]
    return pbn, contract, declarer, vul, penalty, play


def seats_to_grade(declarer):
    dummy = CLOCKWISE[(CLOCKWISE.index(declarer) + 2) % 4]
    return [s for s in CLOCKWISE if s != dummy]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--deals', type=int, default=20)
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--only')
    args = ap.parse_args()
    settings = ExpertSettings(strict=args.strict)

    grand = {'time': 0.0, 'sampled': 0, 'kept': 0, 'judged': 0, 'hits': 0, 'sigmas': [],
             'changed': 0, 'graded': 0, 'none': 0}
    for ex_id, title, lin in examples():
        if args.only and args.only != ex_id:
            continue
        hands, contract, declarer, vul, penalty, play = parse_lin(lin)
        level, strain = contract
        print(f'\n== {title}  ({level}{strain} by {declarer}, {len(play)} cards, vul {vul})')
        memo = VerdictMemo()
        for seat in seats_to_grade(declarer):
            base = grader.grade_play(hands, level, strain, declarer, play, seat,
                                     num_deals=args.deals, seed=0, vul=vul, penalty=penalty)
            t = time.perf_counter()
            res = grader.grade_play(hands, level, strain, declarer, play, seat,
                                    num_deals=args.deals, seed=0, vul=vul, penalty=penalty,
                                    expert=settings, memo=memo)
            dt = time.perf_counter() - t
            ex = [d['expert'] for d in res['decisions'] if d['expert']]
            sampled = sum(e['sampled'] for e in ex)
            kept = sum(e['consistent'] for e in ex)
            judged = sum(e['judged'] for e in ex)
            hits = sum(e['memo_hits'] for e in ex)
            sig = [e['sigma'] for e in ex if e['sigma'] is not None]
            none = sum(1 for e in ex if e['inference'] == 'none')
            by_index = {d['index']: d for d in base['decisions']}
            changed = sum(1 for d in res['decisions']
                          if d['expert'] and by_index[d['index']]['status'] != d['status'])
            print(f"  {seat} ({res['role']:8}): {dt:6.1f}s  decisions {len(ex):2}  "
                  f"examined {sampled:4} kept {kept:3} ({kept / max(sampled, 1):.0%})  "
                  f"judged {judged:4} memo-hits {hits:4}  "
                  f"sigma {statistics.mean(sig) if sig else float('nan'):.2f}  "
                  f"grades changed {changed}  no-survivor {none}  "
                  f"loss {base['summary']['total_trick_loss']:.2f}->{res['summary']['total_trick_loss']:.2f} tricks")
            grand['time'] += dt
            grand['sampled'] += sampled
            grand['kept'] += kept
            grand['judged'] += judged
            grand['hits'] += hits
            grand['sigmas'] += sig
            grand['changed'] += changed
            grand['graded'] += len(ex)
            grand['none'] += none
        print(f'  memo entries after this hand: {len(memo)}')

    g = grand
    print(f"\n== TOTAL  deals={args.deals} strict={args.strict}: {g['time']:.0f}s over {g['graded']} decisions "
          f"({g['time'] / max(g['graded'], 1):.1f}s each); examined {g['sampled']} kept {g['kept']} "
          f"({g['kept'] / max(g['sampled'], 1):.0%}); judged {g['judged']} memo-hits {g['hits']} "
          f"(hit rate {g['hits'] / max(g['judged'] + g['hits'], 1):.0%}); "
          f"sigma mean {statistics.mean(g['sigmas']) if g['sigmas'] else float('nan'):.2f} "
          f"median {statistics.median(g['sigmas']) if g['sigmas'] else float('nan'):.2f}; "
          f"grades changed {g['changed']}; no-survivor decisions {g['none']}")


if __name__ == '__main__':
    main()
