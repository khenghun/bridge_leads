#!/usr/bin/env python
"""Scan every board of a multi-board BBO LIN file through the play API.

    ../.venv/Scripts/python.exe scripts/scan_lin.py path/to/match.lin [--api http://localhost:8001]
        [--deals 40] [--expert] [--out report.md]

For each `qx|` segment with a contract and a recorded play it grades declarer
and both defenders (the app's "whole table") with the given settings and
prints one block per board: contract, result string from `rs|` when present,
per-seat grades and losses, and the costliest decisions. Development tool —
the API itself never takes LIN; the segment is parsed here with the same
small reader `measure_expert.py` uses.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_expert import parse_lin  # noqa: E402

SEATS = ['N', 'E', 'S', 'W']


def segments(text):
    """(qx id, board label, segment text) for every qx| block."""
    parts = re.split(r'(?=qx\|)', text)
    out = []
    for p in parts:
        m = re.match(r'qx\|([^|]*)\|', p)
        if not m:
            continue
        board = re.search(r'ah\|([^|]*)\|', p)
        out.append((m.group(1), board.group(1) if board else m.group(1), p))
    return out


def post(api, body):
    req = urllib.request.Request(api + '/api/play/analyze', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lin')
    ap.add_argument('--api', default='http://localhost:8001')
    ap.add_argument('--deals', type=int, default=40)
    ap.add_argument('--expert', action='store_true')
    ap.add_argument('--out')
    args = ap.parse_args()

    text = Path(args.lin).read_text(encoding='utf-8', errors='replace')
    results = re.search(r'rs\|([^|]*)\|', text)
    rs = results.group(1).split(',') if results else []
    lines = [f'# Scan of `{Path(args.lin).name}` — {args.deals} deals, single dummy'
             + (', expert opponents' if args.expert else '') + '\n']
    totals = {'boards': 0, 'decisions': 0, 'graded': 0, 'sub': 0, 'imps': 0.0, 'time': 0.0}
    for k, (qx, board, seg) in enumerate(segments(text)):
        try:
            hands, contract, declarer, vul, penalty, play = parse_lin(seg)
        except Exception as e:  # noqa: BLE001 — a segment that does not parse is reported, not fatal
            lines.append(f'## {board} ({qx}) — could not parse: {e}\n')
            continue
        rs_here = rs[k] if k < len(rs) else ''
        if not contract or not declarer:
            lines.append(f'## {board} ({qx}) — passed out ({rs_here})\n')
            continue
        if not play:
            lines.append(f'## {board} ({qx}) — {rs_here}: no play recorded\n')
            continue
        level, strain = contract
        dummy = SEATS[(SEATS.index(declarer) + 2) % 4]
        seats = [declarer] + [s for s in SEATS if s not in (declarer, dummy)]
        head = f'## {board} ({qx}) — {level}{"NT" if strain == "N" else strain}{"x" if penalty == "doubled" else "xx" if penalty == "redoubled" else ""} by {declarer}, vul {vul}, {len(play)} cards' + (f', result {rs_here}' if rs_here else '')
        lines.append(head + '\n')
        lines.append('| Seat | Role | Graded | ✓ / ~ / ✗ | Tricks lost | IMPs lost | Worst |')
        lines.append('| --- | --- | --- | --- | --- | --- | --- |')
        t0 = time.perf_counter()
        for seat in seats:
            body = {'hands': hands, 'level': level, 'strain': strain, 'declarer': declarer,
                    'vul': vul, 'penalty': penalty, 'play': play, 'seat': seat,
                    'method': 'single_dummy', 'num_deals': args.deals,
                    'constraints': {'hcp': {}, 'suit_length': {}, 'shapes': {}, 'quality': {}, 'fixed_cards': {}}}
            if args.expert:
                body['expert_opponents'] = True
            try:
                r = post(args.api, body)
            except Exception as e:  # noqa: BLE001
                lines.append(f'| {seat} | — | error: {e} | | | | |')
                continue
            s = r['summary']
            worst = None
            for d in r['decisions']:
                if d['imp_diff'] is not None and (worst is None or d['imp_diff'] < worst['imp_diff']):
                    worst = d
            wtxt = '—'
            if worst and worst['imp_diff'] < -0.005:
                wtxt = f"T{worst['trick']} {worst['hand']} {worst['card']} ({worst['imp_diff']:+.2f} IMPs, {worst['diff']:+.2f} tricks, {worst['status']})"
            lines.append(f"| {seat} | {r['role']} | {s['graded']} | {s['optimal']} / {s['good']} / {s['suboptimal']} "
                         f"| {s['total_trick_loss']:.2f} | {s['total_imp_loss']:.2f} | {wtxt} |")
            totals['decisions'] += s['decisions']
            totals['graded'] += s['graded']
            totals['sub'] += s['suboptimal']
            totals['imps'] += s['total_imp_loss']
        totals['boards'] += 1
        totals['time'] += time.perf_counter() - t0
        lines.append('')
        print(head, f'({time.perf_counter() - t0:.1f}s)', flush=True)
    lines.append(f"\n**{totals['boards']} boards, {totals['graded']} graded decisions, "
                 f"{totals['sub']} suboptimal, {totals['imps']:.1f} IMPs given up in all, "
                 f"{totals['time']:.0f} s.**\n")
    report = '\n'.join(lines)
    if args.out:
        Path(args.out).write_text(report, encoding='utf-8')
        print('report:', args.out)
    else:
        print(report)


if __name__ == '__main__':
    main()
