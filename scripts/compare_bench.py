#!/usr/bin/env python
"""The v1.4 accuracy gate: compare a candidate bench run against a baseline.

    ../.venv/Scripts/python.exe scripts/compare_bench.py \
        docs/play/bench/board7-o7-strict100.json candidate.json

Per decision: status must match; the numbers must agree within the noise the
two runs themselves report — |d(diff)| <= 2·sqrt(se1² + se2²) in tricks and
the same in IMPs (the v1.4 `sample` block; both runs must carry it), else
the older fixed bands: 0.05 tricks and max(0.5, 25% of the baseline
magnitude) — big-swing decisions carry proportionally more IMP variance. Status changes are listed with
their numbers so a borderline call can be shown to be borderline (the decided
gate: RNG draw-order changes are fine, results must be within noise of the
right one; a borderline flip is documented and the baseline re-committed
alongside the change). Prints the per-seat timing comparison either way.
Exit code 1 when anything is listed.
"""
import json
import sys

base = json.load(open(sys.argv[1]))
cand = json.load(open(sys.argv[2]))

fails, warns = [], []
for seat, bs in base['seats'].items():
    cs = cand['seats'].get(seat)
    if cs is None:
        fails.append(f'{seat}: missing in candidate')
        continue
    bd = {d['index']: d for d in bs['decisions']}
    cd = {d['index']: d for d in cs['decisions']}
    for j, b in bd.items():
        c = cd.get(j)
        if c is None:
            fails.append(f'{seat} j={j}: missing')
            continue
        if b['status'] != c['status']:
            fails.append(f"{seat} j={j} T{b['trick']} {b['card']}: status "
                         f"{b['status']} -> {c['status']} "
                         f"(diff {b['diff']} -> {c['diff']}, "
                         f"imp {b['imp_diff']} -> {c['imp_diff']})")
        bs_, cs_ = b.get('sample'), c.get('sample')
        if bs_ and cs_:
            checks = [('diff', 2 * (bs_['se_tricks'] ** 2 + cs_['se_tricks'] ** 2) ** 0.5),
                      ('imp_diff', 2 * (bs_['se_imps'] ** 2 + cs_['se_imps'] ** 2) ** 0.5)]
        else:
            checks = [('diff', 0.05)]
            if b['imp_diff'] is not None:
                checks.append(('imp_diff', max(0.5, 0.25 * abs(b['imp_diff']))))
        for k, tol in checks:
            if b[k] is not None and c[k] is not None and abs(b[k] - c[k]) > tol:
                warns.append(f"{seat} j={j} {b['card']}: {k} "
                             f"{b[k]} -> {c[k]} (tol {round(tol, 2)})")
    ba, ca = bs['summary'], cs['summary']
    print(f"{seat}: {ba['optimal']}/{ba['good']}/{ba['suboptimal']} -> "
          f"{ca['optimal']}/{ca['good']}/{ca['suboptimal']}  "
          f"imp_loss {ba['total_imp_loss']} -> {ca['total_imp_loss']}  "
          f"time {ba['total_time_s']}s -> {ca['total_time_s']}s "
          f"({ba['total_time_s'] / max(ca['total_time_s'], 0.001):.1f}x)")

print(f"\ntotal {base['meta']['total_time_s']}s -> {cand['meta']['total_time_s']}s "
      f"({base['meta']['total_time_s'] / cand['meta']['total_time_s']:.1f}x)")
if fails:
    print('\nSTATUS CHANGES / MISSING:')
    for f in fails:
        print(' ', f)
if warns:
    print('\nNUMERIC DRIFT PAST TOLERANCE:')
    for w in warns:
        print(' ', w)
if not fails and not warns:
    print('\nGATE PASSED: statuses identical, numbers within tolerance.')
sys.exit(1 if (fails or warns) else 0)
