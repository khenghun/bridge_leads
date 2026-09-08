#!/usr/bin/env python
"""Sampling noise of the play grader (v1.4 sample-size plan, 2026-09-08).

    ../.venv/Scripts/python.exe scripts/measure_noise.py seeds [qx] [index] [plain|expert|strict] [N,N...] [seeds]
    ../.venv/Scripts/python.exe scripts/measure_noise.py census [N]

`seeds`: one decision (default c7 South's T9 D6, play index 34) graded cold
at several seeds and deal counts, printing each run's diff, its own paired
standard error (sd of played-minus-best per deal over sqrt n), the IMP
equivalents, and the seed-to-seed spread -- the measurement behind
`docs/play/v1.4-sample-size-plan.md`.

`census`: every graded seat of the three benchmark boards, plain, seed 0,
one rng per seat as `grade_play` draws: which decisions are not optimal,
which are marginal (a 2-sigma band on tricks or IMPs crossing a status
line), i.e. which an escalation would re-grade on more deals.

Engine-direct (no API); 16 DDS threads unless BRIDGE_DDS_THREADS says otherwise.
"""
import math
import os
import random
import statistics
import sys
import time

os.environ.setdefault('BRIDGE_DDS_THREADS', '16')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from measure_expert import parse_lin  # noqa: E402
from scan_lin import segments         # noqa: E402
from engine.play import grader        # noqa: E402
from engine.play.state import replay, legal_cards, next_seat  # noqa: E402
from engine.play.expert import ExpertSettings, VerdictMemo, expert_layouts  # noqa: E402
from engine.scoring import imps       # noqa: E402

SEATS = 'NESW'
Z = 2.0


def board(fn, qx):
    text = open(os.path.join(ROOT, 'docs/play', fn), encoding='utf-8').read()
    seg = next(s for q, _, s in segments(text) if q == qx)
    return parse_lin(seg)


def lin_for(qx):
    return 'board7.lin' if qx in ('o7', 'c7') else 'board14.lin'


def paired(per_board, card, best, sign, sc):
    """Mean and se of the per-deal paired difference played - best, in
    tricks and IMPs, plus how many deals the played card is worse / better on."""
    d = [sign * (a - b) for a, b in zip(per_board[card], per_board[best])]
    di = [imps(sign * (sc.score(a) - sc.score(b)))
          for a, b in zip(per_board[card], per_board[best])]
    n = len(d)
    return (sum(d) / n, statistics.pstdev(d) / math.sqrt(n),
            sum(di) / n, statistics.pstdev(di) / math.sqrt(n),
            sum(1 for x in d if x < 0), sum(1 for x in d if x > 0), n)


def seeds_cmd(argv):
    qx = argv[0] if len(argv) > 0 else 'c7'
    index = int(argv[1]) if len(argv) > 1 else 34
    mode = argv[2] if len(argv) > 2 else 'plain'
    Ns = [int(x) for x in argv[3].split(',')] if len(argv) > 3 else [100, 400]
    seeds = list(range(int(argv[4]))) if len(argv) > 4 else list(range(10))
    hands, (level, strain), declarer, vul, penalty, play = board(lin_for(qx), qx)
    position = replay(hands, strain, declarer, play[:index])
    view = grader.view_for(position, position.to_play)
    card = play[index]
    sign = 1 if view in position.declarer_side else -1
    sc = grader.Scoring(level, strain, position.declarer, vul, penalty)
    ctx = grader._context_key(hands, level, strain, declarer, play, None)
    print(f'{qx} index {index}: T{position.trick_number} {position.to_play} plays {card}, '
          f'view {view}, mode {mode}')
    for N in Ns:
        print(f'\n== N={N}')
        diffs = []
        for seed in seeds:
            rng = random.Random(seed)
            t0 = time.perf_counter()
            if mode == 'plain':
                layouts = grader._sample_layouts(position, view, None, N, rng)
                extra = ''
            else:
                st = ExpertSettings(strict=(mode == 'strict'))
                layouts, ex = expert_layouts(position, view, None, {}, N, st, rng,
                                             level=level, context_key=ctx, memo=VerdictMemo())
                extra = (f' sampled {ex.sampled} kept {ex.consistent} judged {ex.judged} '
                         f'{ex.inference}')
            _, _, _, pb = grader._solve(position, layouts, level)
            means = {c: sum(v) / len(v) for c, v in pb.items() if v}
            best = max(means, key=lambda c: sign * means[c])
            mean, se, im, ise, worse, better, n = paired(pb, card, best, sign, sc)
            diffs.append(mean)
            print(f'seed {seed}: diff {mean:+.3f} se {se:.3f} imps {im:+.2f} se {ise:.2f} n {n}'
                  f'  worse-on {worse} better-on {better}  best {best}'
                  f'  {time.perf_counter() - t0:.1f}s{extra}')
        print(f'across seeds: mean {statistics.mean(diffs):+.3f}  sd {statistics.pstdev(diffs):.3f}'
              f'  min {min(diffs):+.3f} max {max(diffs):+.3f}')


def census_cmd(argv):
    N = int(argv[0]) if argv else 100
    boards = [('board7.lin', 'o7'), ('board7.lin', 'c7'), ('board14.lin', 'c14')]
    tot = {'graded': 0, 'not_optimal': 0, 'marginal': 0, 'either': 0, 'zero': 0}
    for fn, qx in boards:
        hands, (level, strain), declarer, vul, penalty, play = board(fn, qx)
        dummy = next_seat(declarer, 2)
        sc = grader.Scoring(level, strain, declarer, vul, penalty)
        for seat in [declarer] + [s for s in SEATS if s not in (declarer, dummy)]:
            graded_seats = {declarer, dummy} if seat == declarer else {seat}
            rng = random.Random(0)
            rows = []
            for position, card in grader.walk(hands, strain, declarer, play):
                if position.to_play not in graded_seats or len(legal_cards(position)) == 1:
                    continue
                layouts = grader._sample_layouts(position, seat, None, N, rng)
                _, _, _, pb = grader._solve(position, layouts, level)
                sign = 1 if seat in position.declarer_side else -1
                means = {c: sum(v) / len(v) for c, v in pb.items() if v}
                best = max(means, key=lambda c: sign * means[c])
                diff, se, im, ise, _, _, n = paired(pb, card, best, sign, sc)
                is_best = abs(diff) < 0.01
                status = grader.classify_with_imps(round(diff, 3), is_best, round(im, 2))
                corners = {grader.classify_with_imps(round(diff + a * Z * se, 3),
                                                     is_best and a == 0,
                                                     round(im + b * Z * ise, 2))
                           for a in (-1, 0, 1) for b in (-1, 0, 1)}
                rows.append((position.index, position.trick_number, position.to_play, card,
                             status, diff, se, im, ise, len(corners) > 1))
            g = len(rows)
            no = sum(1 for r in rows if r[4] != 'optimal')
            mg = sum(1 for r in rows if r[9])
            ei = sum(1 for r in rows if r[4] != 'optimal' or r[9])
            zero = sum(1 for r in rows if r[6] == 0)
            for k, v in zip(('graded', 'not_optimal', 'marginal', 'either', 'zero'),
                            (g, no, mg, ei, zero)):
                tot[k] += v
            print(f'{qx} {seat}: graded {g}, not optimal {no}, marginal {mg}, '
                  f'escalate {ei}, se=0 {zero}')
            for r in rows:
                if r[4] != 'optimal' or r[9]:
                    print(f'   j{r[0]:2d} T{r[1]:2d} {r[2]} {r[3]} {r[4]:>10s} '
                          f'{r[5]:+.2f}±{r[6]:.2f}  {r[7]:+.2f}±{r[8]:.2f} IMPs'
                          f'{"  marginal" if r[9] else ""}')
    print(tot)


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'seeds'
    (census_cmd if cmd == 'census' else seeds_cmd)(sys.argv[2:])
