#!/usr/bin/env python
"""Measure the expert filter's wave structure per decision: how many outer
rounds (`_sample_layouts` calls), how many judge waves (backend `judge`
calls), and how wide each wave is. Runs the engine in-process through a
counting `JudgeBackend` — the structure is what a remote backend would see,
since the local and remote paths run the same `_resolve` loop.

    ../.venv/Scripts/python.exe scripts/measure_waves.py docs/play/board7.lin --qx o7 \
        --seat E --deals 100 --strict [--decisions 8,12]

Why: play v1.5's sequential bench (docs/play/bench/board7-o7-strict100-prod-lambda.md)
showed the defender seats 1.2–1.5× slower through Lambda than on a 16-thread
laptop, diagnosed as narrow waves — every wave pays an invoke round trip, so
width is wall clock. This script is the measurement that diagnosis asked for.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.play import grader, expert                           # noqa: E402
from engine.play.expert import ExpertSettings, VerdictMemo, LocalBackend  # noqa: E402
from measure_expert import parse_lin                              # noqa: E402
from scan_lin import segments                                     # noqa: E402
from bench_play import play_players                               # noqa: E402

SEATS = ['N', 'E', 'S', 'W']


class CountingBackend(LocalBackend):
    """LocalBackend that records every wave's width and every trace slice."""

    def __init__(self):
        super().__init__()
        self.waves = []      # item counts, in order
        self.traces = []     # layout counts, in order
        self.rounds = 0

    def judge(self, items, **kwargs):
        self.waves.append(len(items))
        return super().judge(items, **kwargs)

    def trace(self, layouts, strain, declarer, play):
        self.traces.append(len(layouts))
        return super().trace(layouts, strain, declarer, play)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lin')
    ap.add_argument('--qx', required=True)
    ap.add_argument('--seat', required=True)
    ap.add_argument('--deals', type=int, default=100)
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--decisions', help='comma-separated play indices (default: all of the seat)')
    ap.add_argument('--escalate', action='store_true', help='default ×3 escalation (off by default)')
    ap.add_argument('--json', help='write per-decision rows here')
    ap.add_argument('--width', type=int, default=1,
                    help='backend width (1 = local, no over-draw; 256 = the Lambda client)')
    args = ap.parse_args()

    text = Path(args.lin).read_text(encoding='utf-8')
    seg = next(s for q, _, s in segments(text) if q == args.qx)
    hands, contract, declarer, vul, penalty, play = parse_lin(seg)
    level, strain = contract
    dummy = SEATS[(SEATS.index(declarer) + 2) % 4]
    players = play_players(declarer, strain, play)
    seat = args.seat
    mine = [j for j, p in enumerate(players) if p == seat or (seat == declarer and p == dummy)]
    if args.decisions:
        mine = [int(x) for x in args.decisions.split(',')]

    backend = CountingBackend()
    backend.width = args.width
    memo = VerdictMemo()
    settings = ExpertSettings(strict=args.strict)
    escalation = grader.EscalationSettings() if args.escalate else None

    # Count outer rounds by wrapping the sampler the outer loop calls.
    real_sample = grader._sample_layouts
    draws = []

    def counting_sample(position, view, constraints, num_deals, rng):
        draws.append(num_deals)
        return real_sample(position, view, constraints, num_deals, rng)
    grader._sample_layouts = counting_sample

    print(f'{args.qx}: {level}{strain} by {declarer}, seat {seat}, {len(play)} cards, '
          f'{"strict" if args.strict else "expert"} {args.deals} deals, '
          f'DDS threads {expert.DDS_THREADS}, width {args.width}', flush=True)
    print(f'{"j":>3} {"T":>2} card {"status":>10} {"secs":>6} {"rounds":>6} {"waves":>5} '
          f'{"items":>6} {"w/round":>7} {"mean w":>6} {"max w":>5} {"w<=4":>5} '
          f'{"samp":>5} {"kept":>4} {"judged":>6} {"hits":>5}', flush=True)
    rows = []
    for j in mine:
        backend.waves, backend.traces, draws[:] = [], [], []
        t0 = time.perf_counter()
        res = grader.grade_play(hands, level, strain, declarer, play, seat,
                                num_deals=args.deals, seed=0, vul=vul, penalty=penalty,
                                expert=settings, memo=memo, decisions=[j],
                                escalation=escalation, judge_backend=backend)
        dt = time.perf_counter() - t0
        d = res['decisions'][0]
        waves = list(backend.waves)
        items = sum(waves)
        ex = d.get('expert') or {}
        row = {
            'index': j, 'trick': d['trick'], 'card': d['card'], 'status': d['status'],
            'forced': d['forced'], 'secs': round(dt, 2),
            'rounds': len(draws), 'draws': list(draws),
            'waves': len(waves), 'items': items, 'widths': waves,
            'traces': list(backend.traces),
            'sampled': ex.get('sampled'), 'consistent': ex.get('consistent'),
            'judged': ex.get('judged'), 'memo_hits': ex.get('memo_hits'),
            'carried': ex.get('carried'),
        }
        rows.append(row)
        nw = max(len(waves), 1)
        print(f"{j:3d} {d['trick']:2d} {d['card']:>4} {d['status']:>10} {dt:6.1f} "
              f"{len(draws):6d} {len(waves):5d} {items:6d} "
              f"{len(waves) / max(len(draws), 1):7.1f} {items / nw:6.1f} "
              f"{max(waves, default=0):5d} {sum(1 for w in waves if w <= 4):5d} "
              f"{ex.get('sampled') or 0:5d} {ex.get('consistent') or 0:4d} "
              f"{ex.get('judged') or 0:6d} {ex.get('memo_hits') or 0:5d}", flush=True)

    total = sum(r['secs'] for r in rows)
    print(f'\nseat {seat}: {total:.1f} s, {sum(r["rounds"] for r in rows)} rounds, '
          f'{sum(r["waves"] for r in rows)} waves, {sum(r["items"] for r in rows)} items', flush=True)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
