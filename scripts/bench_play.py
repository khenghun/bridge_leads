#!/usr/bin/env python
"""Benchmark one or more boards of a LIN file through the play API, per decision.

    ../.venv/Scripts/python.exe scripts/bench_play.py docs/play/board7.lin --qx o7 c7 \
        [--api http://localhost:8001] [--deals 100] [--expert] [--strict] \
        [--seats N,E,W] [--out-dir docs/play/bench] [--machine dev-laptop]

For every requested board it grades declarer and both defenders **one decision
per request** (the UI's request pattern), records the wall-clock and the expert
stats of every decision, and writes per board:

    <out-dir>/<lin-stem>-<qx>-<mode><deals>.json   machine-readable, retestable
    <out-dir>/<lin-stem>-<qx>-<mode><deals>.md     human summary

The JSON pins everything another implementation needs to reproduce the run:
the exact request template (the API is seeded — seed=0 — so results are
deterministic), every decision's grade/diff/imp_diff/options, and the timings.

Timings are only *cold* if the API process is fresh: both the result cache and
the expert verdict memo are process-level and survive across requests. Restart
the API (uvicorn app_play.main:app --port 8001) before a timing rerun.
Development tool — the API itself never takes LIN; segments are parsed here
with the same reader `measure_expert.py` / `scan_lin.py` use.
"""
import argparse
import json
import os
import platform
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_expert import parse_lin  # noqa: E402
from scan_lin import segments         # noqa: E402

SEATS = ['N', 'E', 'S', 'W']
RANKS = 'AKQJT98765432'


def play_players(declarer, strain, play):
    """The seat that played each card of `play`, by replaying trick order."""
    leader = SEATS[(SEATS.index(declarer) + 1) % 4]
    trump = None if strain == 'N' else strain
    players = []
    for i in range(0, len(play), 4):
        trick = play[i:i + 4]
        for k in range(len(trick)):
            players.append(SEATS[(SEATS.index(leader) + k) % 4])
        if len(trick) == 4:
            led = trick[0][0]
            best = 0
            for k in range(1, 4):
                a, b = trick[k], trick[best]
                if a[0] == b[0]:
                    if RANKS.index(a[1]) < RANKS.index(b[1]):
                        best = k
                elif a[0] == trump:
                    best = k
            leader = SEATS[(SEATS.index(leader) + best) % 4]
    return players


def post(api, body, timeout=1800):
    req = urllib.request.Request(api + '/api/play/analyze', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def dds_stats(api):
    """The API's cumulative DDS counters (None if the endpoint is missing)."""
    try:
        with urllib.request.urlopen(api + '/api/play/debug/dds', timeout=10) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001 — older API without the endpoint
        return None


def bench_board(api, qx, board, seg, args):
    hands, contract, declarer, vul, penalty, play = parse_lin(seg)
    if not contract or not play:
        print(f'{qx}: passed out or no play, skipped', flush=True)
        return None
    level, strain = contract
    dummy = SEATS[(SEATS.index(declarer) + 2) % 4]
    players = play_players(declarer, strain, play)
    seats = args.seats or [declarer] + [s for s in SEATS if s not in (declarer, dummy)]

    template = {'hands': hands, 'level': level, 'strain': strain, 'declarer': declarer,
                'vul': vul, 'penalty': penalty, 'play': play,
                'method': 'single_dummy', 'num_deals': args.deals,
                'constraints': {'hcp': {}, 'suit_length': {}, 'shapes': {},
                                'quality': {}, 'fixed_cards': {}}}
    if args.expert or args.strict:
        template['expert_opponents'] = True
        template['expert'] = {'strict': bool(args.strict)}

    mode = ('strict' if args.strict else 'expert' if args.expert else 'plain')
    result = {
        'meta': {
            'lin': Path(args.lin).name, 'qx': qx, 'board': board,
            'contract': f'{level}{strain}', 'declarer': declarer, 'vul': vul,
            'penalty': penalty, 'cards_played': len(play),
            'mode': mode, 'num_deals': args.deals, 'api': args.api,
            'request_template': {k: v for k, v in template.items()},
            'machine': args.machine, 'cpu_count': os.cpu_count(),
            'python': platform.python_version(),
            # The API's own thread cap (its env, not this script's), when the
            # API exposes it; 0 means DDS auto-detected every core.
            'dds_threads': (dds_stats(args.api) or {}).get('threads'),
            'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        },
        'seats': {},
    }

    t_board = time.perf_counter()
    for seat in seats:
        mine = [j for j, p in enumerate(players)
                if p == seat or (seat == declarer and p == dummy)]
        rows, summary, role = [], None, None
        dds_before = dds_stats(args.api)
        t_seat = time.perf_counter()
        for j in mine:
            body = dict(template, seat=seat, decisions=[j])
            t0 = time.perf_counter()
            r = post(args.api, body)
            elapsed = time.perf_counter() - t0
            role = r['role']
            summary = r['summary']  # summary of the subset; totals rebuilt below
            for d in r['decisions']:
                rows.append({
                    'index': d['index'], 'trick': d['trick'], 'hand': d['hand'],
                    'card': d['card'], 'forced': d['forced'], 'status': d['status'],
                    'diff': d['diff'], 'imp_diff': d['imp_diff'],
                    'score_diff': d['score_diff'],
                    'best_cards': d['best_cards'], 'options': d['options'],
                    'expert': d['expert'], 'sample': d.get('sample'),
                    'elapsed_s': round(elapsed, 3),
                })
            print(f"  {qx} {seat} j={j:2d} T{rows[-1]['trick']:2d} "
                  f"{rows[-1]['hand']} {rows[-1]['card']} "
                  f"{rows[-1]['status']:>10s} {elapsed:6.1f}s", flush=True)
        seat_time = time.perf_counter() - t_seat
        graded = [d for d in rows if not d['forced'] and d['diff'] is not None]
        agg = {
            'decisions': len(rows), 'graded': len(graded),
            'optimal': sum(1 for d in graded if d['status'] == 'optimal'),
            'good': sum(1 for d in graded if d['status'] == 'good'),
            'suboptimal': sum(1 for d in graded if d['status'] == 'suboptimal'),
            'total_trick_loss': round(-sum(min(d['diff'], 0) for d in graded), 3),
            'total_imp_loss': round(-sum(min(d['imp_diff'] or 0, 0) for d in graded), 3),
            'marginal': sum(1 for d in graded if d.get('sample') and not d['sample']['firm']),
            'escalated': sum(1 for d in graded if d.get('sample') and d['sample']['escalated']),
            'total_time_s': round(seat_time, 1),
            'mean_s_per_graded': round(seat_time / max(len(graded), 1), 2),
            'max_decision_s': max((d['elapsed_s'] for d in rows), default=0.0),
        }
        dds_after = dds_stats(args.api)
        if dds_before is not None and dds_after is not None:
            agg['dds'] = {name: {k: round(dds_after[name][k] - dds_before[name][k], 3)
                                 for k in ('calls', 'boards', 'seconds')}
                          for name in dds_after if isinstance(dds_after[name], dict)}
        ex = [d['expert'] for d in rows if d.get('expert')]
        if ex:
            agg['expert_totals'] = {
                k: sum(e[k] for e in ex)
                for k in ('sampled', 'consistent', 'traced', 'judged', 'memo_hits')}
        result['seats'][seat] = {'role': role, 'summary': agg, 'decisions': rows}
    result['meta']['total_time_s'] = round(time.perf_counter() - t_board, 1)
    return result


def to_markdown(res):
    m = res['meta']
    lines = [f"# Bench {m['lin']} {m['qx']} ({m['board']}) — {m['contract']} by "
             f"{m['declarer']}, vul {m['vul']}, mode {m['mode']}, "
             f"{m['num_deals']} deals",
             '',
             f"Machine {m['machine']} ({m['cpu_count']} cpus, python {m['python']}, "
             f"DDS threads {m.get('dds_threads', '?')}), {m['timestamp']}. "
             f"Total {m['total_time_s']} s.", '']
    for seat, s in res['seats'].items():
        a = s['summary']
        lines.append(f"## {seat} ({s['role']}) — {a['optimal']}✓/{a['good']}~/"
                     f"{a['suboptimal']}✗ of {a['graded']}, "
                     f"{a['total_trick_loss']:.2f} tricks · "
                     f"{a['total_imp_loss']:.2f} IMPs lost — "
                     f"{a['total_time_s']} s ({a['mean_s_per_graded']} s/graded, "
                     f"max {a['max_decision_s']} s)")
        if 'marginal' in a or 'escalated' in a:
            lines.append(f"sample: {a.get('marginal', 0)} marginal, "
                         f"{a.get('escalated', 0)} escalated (deals marked * not optimal, "
                         f"† not firm; '?' = not firm)")
        if 'expert_totals' in a:
            e = a['expert_totals']
            lines.append(f"expert: sampled {e['sampled']}, consistent {e['consistent']}, "
                         f"traced {e['traced']}, judged {e['judged']}, "
                         f"memo hits {e['memo_hits']}")
        lines.append('')
        lines.append('| j | T | hand | card | status | diff ± se | IMPs ± se | deals | s | sampled→kept | judged (memo) |')
        lines.append('| - | - | - | - | - | - | - | - | - | - | - |')
        for d in s['decisions']:
            e = d.get('expert') or {}
            sm = d.get('sample') or {}
            ex = (f"{e['sampled']}→{e['consistent']}" if e else '')
            ju = (f"{e['judged']} ({e['memo_hits']})" if e else '')
            diff = '' if d['diff'] is None else f"{d['diff']:+.2f}"
            imp = '' if d['imp_diff'] is None else f"{d['imp_diff']:+.2f}"
            if sm:
                diff += f" ± {sm['se_tricks']:.2f}"
                imp += f" ± {sm['se_imps']:.2f}"
            status = d['status'] + (' ?' if sm and not sm['firm'] else '')
            mark = {'status': '*', 'band': '†'}.get(sm.get('trigger'), '') if sm else ''
            deals = (f"{sm['deals']}{mark}" if sm else '')
            lines.append(f"| {d['index']} | {d['trick']} | {d['hand']} | {d['card']} "
                         f"| {status} | {diff} | {imp} | {deals} | {d['elapsed_s']} "
                         f"| {ex} | {ju} |")
        lines.append('')
    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lin')
    ap.add_argument('--qx', nargs='+', required=True)
    # 127.0.0.1, not localhost: on Windows, localhost resolves IPv6 first and
    # pays a ~2 s connect fallback per request, which would swamp the timings.
    ap.add_argument('--api', default='http://127.0.0.1:8001')
    ap.add_argument('--deals', type=int, default=100)
    ap.add_argument('--expert', action='store_true')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--seats', type=lambda s: s.split(','), default=None)
    ap.add_argument('--out-dir', default='docs/play/bench')
    ap.add_argument('--machine', default='dev-laptop')
    args = ap.parse_args()

    text = Path(args.lin).read_text(encoding='utf-8', errors='replace')
    segs = {qx: (board, seg) for qx, board, seg in segments(text)}
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = ('strict' if args.strict else 'expert' if args.expert else 'plain')
    for qx in args.qx:
        board, seg = segs[qx]
        print(f'== {qx} ({board}) {mode} {args.deals} deals', flush=True)
        res = bench_board(args.api, qx, board, seg, args)
        if res is None:
            continue
        stem = f"{Path(args.lin).stem}-{qx}-{mode}{args.deals}"
        (out_dir / f'{stem}.json').write_text(json.dumps(res, indent=1), encoding='utf-8')
        (out_dir / f'{stem}.md').write_text(to_markdown(res), encoding='utf-8')
        print(f"== {qx} done in {res['meta']['total_time_s']} s → {out_dir / stem}.json/.md",
              flush=True)


if __name__ == '__main__':
    main()
