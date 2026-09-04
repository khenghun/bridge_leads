"""Expert opponents — a layout filter for the play grader (play solver v1.3).

Ordinary grading samples the hands the graded seat could not see, consistent
with the cards already played. This module adds a second condition: *on this
layout, every earlier play by an opponent was a best play given what that
opponent could see at the time* — judged by a Monte-Carlo from the opponent's
own view, one level of recursion inside the grader's Monte-Carlo. The layout
where East held the last diamond and a ruff was available is rejected, because
on it East, looking at East's hand, dummy and the play so far, would have found
the ruff. Design: `docs/play/v1.3-expert-opponents-plan.md`.

The pieces, in the order the outer loop uses them:

- `opponent_decisions(layout_hands, ...)` — for one sampled layout, every
  earlier index at which an opponent of the graded view had a real choice
  (two or more *equivalence classes* of legal cards; touching cards are one
  choice), with the holding the *judging* seat had at that moment on this
  layout (declarer's for a play from dummy).
- `dd_costs(trace, ...)` — from an `analyse_plays` trace of the real line on
  the layout, which of those cards lost a double-dummy trick on it. Those are
  the **suspects**; a card that lost nothing is accepted without a judgement
  (the fast-accept). `strict` judges every decision instead.
- `judge(...)` — the recursive single-dummy verdict on one suspect: sample the
  hands hidden from the opponent, price every legal card on each deal, and
  reject only if some alternative is *shown* better than the card played by
  more than the tolerance — a paired-difference test whose confidence margin
  shrinks with the inner sample (`Verdict`). Memoised on the judging seat's
  holding, since dummy, the play and the constraints are the same for every
  layout — that holding is everything the verdict depends on.
- `expert_layouts(...)` — the outer loop: draw, trace, judge latest-first with
  early exit, stop at `num_deals` accepted, fall back to the unfiltered pool
  when nothing survives.

Perspective, three times over: `analyse_plays` values are **declarer** tricks;
`grader._solve` returns **declarer** tricks per card; an opponent's "best" is
best for **the opponent's side**. Each conversion happens in exactly one
function here (`dd_costs`, `_side_tricks`).
"""

from __future__ import annotations

import hashlib
import math
import random
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from ..dds_runtime import DDS_THREADS, analyse_plays, solve_all
from .state import SEATS, SUITS, RANKS, card_sort_key, next_seat, walk

INNER_BATCH = 5         # smallest sequential step of the inner judgement
# First inner batch fills the DDS thread pool, then the step doubles each
# round. DDS parallelises across boards *within* one call, so tiny batches
# leave the pool idle (measured: 16 threads gained nothing at 5 boards/call).
# Most judgements run to the cap anyway — few large calls beat many small
# ones. At the prod thread cap (4) this equals the old fixed-5 first step.
INNER_FIRST = max(INNER_BATCH, DDS_THREADS)
INNER_FLOOR = 8         # smallest inner cap, whatever the ratio says
SD_FLOOR = 0.3          # a tiny all-alike sample may not claim certainty
SIGMA_PLANNING = 0.6    # sd of the paired difference, used only for reporting
POOL_MIN = 5            # smallest top-up round of outer layouts
MEMO_ENTRIES = 20000


@dataclass(frozen=True)
class ExpertSettings:
    """The toggle's knobs; defaults are the plan's. `strict` disables the
    double-dummy fast-accept so every opponent decision gets the inner
    judgement (needed to catch a play that worked on the actual layout but
    was wrong single-dummy)."""
    inner_ratio: float = 0.5
    tolerance: float = 0.10
    confidence: float = 2.0
    budget: int = 20
    strict: bool = False
    depth: int = 1

    def inner_cap(self, num_deals: int) -> int:
        return max(INNER_FLOOR, int(round(self.inner_ratio * num_deals)))

    def key(self) -> tuple:
        return (self.inner_ratio, self.tolerance, self.confidence,
                self.budget, self.strict, self.depth)


@dataclass
class OpponentDecision:
    index: int              # play index j
    seat: str               # who held the cards (dummy for declarer's plays from dummy)
    view: str               # whose eyes judge it (declarer for dummy)
    card: str               # the card actually played
    # The judging seat's remaining cards at j on this layout, sorted: the one
    # input to the verdict that varies between layouts. For a play from dummy
    # that is DECLARER's hand, not dummy's — dummy is public and identical on
    # every layout, so keying on it (play v1.3 did) reused one arbitrary
    # layout's verdict for all of them.
    holding: tuple


@dataclass
class Verdict:
    consistent: bool
    gap: float              # best alternative's mean advantage over the card played (tricks)
    n: int                  # inner deals used
    sigma: float            # sd of that alternative's paired difference
    reason: str             # 'clear' | 'shown-worse' | 'cap' | 'no-alternative' | 'infeasible'


@dataclass
class ExpertStats:
    sampled: int = 0        # outer layouts examined (accepted + rejected)
    consistent: int = 0     # layouts graded on
    traced: int = 0         # layouts that went through the DD trace
    judged: int = 0         # inner judgements actually run (memo misses)
    memo_hits: int = 0
    inference: str = 'filtered'     # 'filtered' | 'none' (nothing survived) | 'trivial' (nothing to judge)
    sigmas: list = field(default_factory=list)

    def threshold(self, settings: ExpertSettings, inner_cap: int) -> float:
        """The nominal rejection threshold `tol0 + z * sigma / sqrt(M)` at the
        planning sd (0.6) — stable across decisions; the observed sd is
        reported beside it."""
        return round(settings.tolerance
                     + settings.confidence * SIGMA_PLANNING / math.sqrt(inner_cap), 3)

    def as_dict(self, settings: ExpertSettings, inner_cap: int) -> dict:
        sigma = round(sum(self.sigmas) / len(self.sigmas), 3) if self.sigmas else None
        return {
            'sampled': self.sampled, 'consistent': self.consistent,
            'traced': self.traced, 'judged': self.judged, 'memo_hits': self.memo_hits,
            'threshold': self.threshold(settings, inner_cap),
            'sigma': sigma,
            'inference': self.inference,
        }


class VerdictMemo:
    """A bounded, thread-safe memo of judgements. The key already names the
    deal, the settings and the constraints, so one memo serves every request
    of a process (the whole-table flow's per-seat calls, chunked requests)."""

    def __init__(self, max_entries: int = MEMO_ENTRIES):
        self._d: OrderedDict = OrderedDict()
        self._max = max_entries
        self._lock = threading.Lock()
        # Evidence for ordering suspects, keyed on the memo key minus the
        # holding — "playing this card at this index": how often it was found
        # inconsistent across the holdings judged so far, and what a fresh
        # judgement of it costs. Never evicted; a few hundred entries per hand.
        self.rejections: dict = {}      # rate key -> [inconsistent, judged]
        self.costs: dict = {}           # rate key -> [seconds, judgements]

    @staticmethod
    def rate_key(key):
        if len(key) != 5:               # a foreign key (tests); no evidence kept
            return key
        ctx, index, view, holding, card = key
        return (ctx, index, view, card)

    def get(self, key):
        with self._lock:
            v = self._d.get(key)
            if v is not None:
                self._d.move_to_end(key)
            return v

    def put(self, key, verdict: Verdict) -> None:
        with self._lock:
            self._d[key] = verdict
            self._d.move_to_end(key)
            while len(self._d) > self._max:
                self._d.popitem(last=False)
            r = self.rejections.setdefault(self.rate_key(key), [0, 0])
            r[0] += 0 if verdict.consistent else 1
            r[1] += 1

    def note_cost(self, key, seconds: float) -> None:
        with self._lock:
            c = self.costs.setdefault(self.rate_key(key), [0.0, 0])
            c[0] += seconds
            c[1] += 1

    def priority(self, key) -> float:
        """How much a fresh judgement of `key` is expected to save per second:
        its estimated rejection probability over its measured cost. Unseen
        plays get an even prior and the cheapest cost measured so far (later
        positions solve faster, and exploring is how the rates get learnt),
        so the first waves still run latest-first."""
        with self._lock:
            rk = self.rate_key(key)
            rej, tot = self.rejections.get(rk, (0, 0))
            p = (rej + 1) / (tot + 2)
            c = self.costs.get(rk)
            if c and c[1]:
                cost = c[0] / c[1]
            else:
                measured = [v[0] / v[1] for v in self.costs.values() if v[1]]
                cost = min(measured) if measured else 1.0
            return p / max(cost, 1e-6)

    def clear(self) -> None:
        with self._lock:
            self._d.clear()
            self.rejections.clear()
            self.costs.clear()

    def __len__(self) -> int:
        return len(self._d)


MEMO = VerdictMemo()


# --- who had a choice, and what it cost double-dummy -------------------------

def opponents_of(view: str, declarer: str) -> frozenset:
    """Seats whose plays the `view` seat judges: both defenders for declarer's
    side, declarer *and dummy* (declarer's decisions) for a defender. A
    defender's partner is never judged — their cards are signals."""
    dummy = next_seat(declarer, 2)
    if view in (declarer, dummy):
        return frozenset(s for s in SEATS if s not in (declarer, dummy))
    return frozenset((declarer, dummy))


def equivalence_classes(legal, completed_cards) -> int:
    """Number of distinct choices among `legal` cards: cards of one suit whose
    intervening ranks have all gone in *completed* tricks are one choice.
    Cards on the table in the current trick still separate ranks (holding 79
    over a led 8, the 7 and the 9 are different plays)."""
    gone = set(completed_cards)
    classes = 0
    by_suit: dict[str, list[str]] = {}
    for c in legal:
        by_suit.setdefault(c[0], []).append(c)
    for suit, cards in by_suit.items():
        ranks = sorted((RANKS.index(c[1]) for c in cards))
        classes += 1
        for a, b in zip(ranks, ranks[1:]):
            between = [suit + RANKS[r] for r in range(a + 1, b)]
            if not all(x in gone for x in between):
                classes += 1
    return classes


def opponent_decisions(layout_hands, strain, declarer, play, upto, view) -> list[OpponentDecision]:
    """Every index `j < upto` at which an opponent of `view` had a real choice
    **on this layout**, latest first. Legality and equivalence depend on the
    hand the opponent holds here, so this is computed per layout (a replay of
    at most 52 cards, pure Python).

    The opening lead (index 0) is exempt — ruled 2026-09-04. Leads are the
    Opening Lead Simulator's problem and are chosen with dummy unseen, so the
    lead is not second-guessed here either. It was also the filter's weakest
    inference at by far the highest price: judged from the leader's view it
    is a full-deal solve over three hidden hands (~0.27 s per layout against
    0.04–0.09 s for any later play), about half the cost of every declarer
    decision, and it rejected one layout in twenty."""
    opp = opponents_of(view, declarer)
    dummy = next_seat(declarer, 2)
    out = []
    for position, card in walk(layout_hands, strain, declarer, play[:upto]):
        seat = position.to_play
        if seat not in opp or position.index == 0:
            continue        # the opening lead is never judged (see the docstring)
        hand = position.remaining[seat]
        led = position.led_suit
        legal = [c for c in hand if c[0] == led] if led else list(hand)
        if led and not legal:
            legal = list(hand)
        if len(legal) < 2:
            continue
        completed = [c for t in position.tricks for c in t.cards]
        if equivalence_classes(legal, completed) < 2:
            continue
        judge_seat = declarer if seat == dummy else seat
        out.append(OpponentDecision(
            index=position.index, seat=seat, view=judge_seat, card=card,
            holding=tuple(sorted(position.remaining[judge_seat], key=card_sort_key))))
    out.reverse()
    return out


def dd_costs(trace, decisions, declarer) -> dict[int, int]:
    """Double-dummy tricks each opponent card cost its own side on the traced
    layout: `trace[j]` is declarer's tricks before the card at `j`,
    `trace[j+1]` after it. A defender's card that raised declarer's count, or
    a declarer-side card that lowered it, cost that many."""
    dummy = next_seat(declarer, 2)
    out = {}
    for d in decisions:
        before, after = trace[d.index], trace[d.index + 1]
        out[d.index] = (before - after) if d.seat in (declarer, dummy) else (after - before)
    return out


# --- the inner judgement ----------------------------------------------------

def _side_tricks(declarer_tricks: float, seat: str, declarer: str) -> float:
    return declarer_tricks if seat in (declarer, next_seat(declarer, 2)) else 13 - declarer_tricks


def _slice_constraints(constraints, seats) -> dict:
    """The user's per-seat constraints restricted to `seats` (the ones hidden
    from the judging view)."""
    out = {}
    for block, per_seat in (constraints or {}).items():
        kept = {s: v for s, v in (per_seat or {}).items() if s in seats}
        if kept:
            out[block] = kept
    return out


def _seeded(*parts) -> random.Random:
    h = hashlib.blake2b(repr(parts).encode(), digest_size=8).digest()
    return random.Random(int.from_bytes(h, 'big'))


def judge(layout_hands, decision, *, level, strain, declarer, play,
          all_constraints, settings, inner_cap, context_key, memo,
          stats=None, deals_hint=None) -> Verdict:
    """Was `decision.card` a best play for its side, judged from
    `decision.view`'s eyes on this layout? Memoised on the holding."""
    key = (context_key, decision.index, decision.view, decision.holding, decision.card)
    hit = memo.get(key)
    if hit is not None:
        if stats is not None:
            stats.memo_hits += 1
        return hit
    verdict = _judge_fresh(layout_hands, decision, level=level, strain=strain,
                           declarer=declarer, play=play, all_constraints=all_constraints,
                           settings=settings, inner_cap=inner_cap,
                           context_key=context_key, memo=memo, deals_hint=deals_hint)
    memo.put(key, verdict)
    if stats is not None:
        stats.judged += 1
        stats.sigmas.append(verdict.sigma)
    return verdict


class _SeqTest:
    """The sequential paired-difference rule, fed one wave of per-board values
    at a time. Rejects only when some alternative's LCB `mean − z·se` clears
    the tolerance; compares per-card means over common inner deals, so a
    coin-flip guess is a tie, never a blunder."""

    def __init__(self, decision, declarer, settings):
        self.actual = decision.card
        self.sign = 1 if decision.view in (declarer, next_seat(declarer, 2)) else -1
        self.z, self.tol = settings.confidence, settings.tolerance
        self.per_card: dict[str, list[float]] = {}
        self.n = 0
        self.gap, self.sigma = 0.0, SD_FLOOR

    def feed(self, per_board, batch_len):
        """Digest one wave; a Verdict to stop early, None to keep sampling."""
        for card, values in per_board.items():
            self.per_card.setdefault(card, []).extend(values)
        self.n += batch_len
        n = self.n
        mine = self.per_card.get(self.actual)
        if not mine:
            return Verdict(True, 0.0, n, SD_FLOOR, 'no-alternative')
        worst_lcb, all_under = -math.inf, True
        self.gap, self.sigma = 0.0, SD_FLOOR
        for card, theirs in self.per_card.items():
            if card == self.actual or len(theirs) != len(mine):
                continue
            diffs = [self.sign * (t - m) for t, m in zip(theirs, mine)]
            mean = sum(diffs) / n
            var = sum((d - mean) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
            sd = max(math.sqrt(var), SD_FLOOR)
            se = sd / math.sqrt(n)
            if mean > self.gap:
                self.gap, self.sigma = mean, sd
            worst_lcb = max(worst_lcb, mean - self.z * se)
            if mean + self.z * se >= self.tol:
                all_under = False
        if worst_lcb == -math.inf:
            return Verdict(True, 0.0, n, SD_FLOOR, 'no-alternative')
        if worst_lcb > self.tol:
            return Verdict(False, round(self.gap, 3), n, round(self.sigma, 3),
                           'shown-worse')
        if all_under:
            return Verdict(True, round(self.gap, 3), n, round(self.sigma, 3), 'clear')
        return None

    def cap(self):
        return Verdict(True, round(self.gap, 3), self.n, round(self.sigma, 3), 'cap')


def _prep(layout_hands, decision, *, level, strain, declarer, play,
          all_constraints, settings, inner_cap, context_key, memo):
    """The judgement's position and inner layouts, or an immediate Verdict."""
    from . import grader  # lazy: grader imports this module

    view = decision.view
    position = grader._position_on(layout_hands, strain, declarer, play[:decision.index])
    hidden = [s for s in SEATS if s not in grader.visible_seats(position, view)]
    constraints = _slice_constraints(all_constraints, hidden)
    rng = _seeded(context_key, decision.index, view, decision.holding)
    try:
        if settings.depth > 1:
            deeper = ExpertSettings(**{**settings.__dict__, 'depth': settings.depth - 1})
            layouts, _ = expert_layouts(
                position, view, constraints, all_constraints, inner_cap, deeper, rng,
                level=level, context_key=context_key + ('d', decision.index), memo=memo)
        else:
            layouts = grader._sample_layouts(position, view, constraints, inner_cap, rng)
    except ValueError:
        # The opponent's own view cannot be sampled under the user's
        # constraints — nothing to judge them against.
        return Verdict(True, 0.0, 0, SD_FLOOR, 'infeasible')
    return position, layouts


def _judge_fresh(layout_hands, decision, *, level, strain, declarer, play,
                 all_constraints, settings, inner_cap, context_key, memo,
                 deals_hint) -> Verdict:
    from . import grader  # lazy: grader imports this module

    prep = _prep(layout_hands, decision, level=level, strain=strain,
                 declarer=declarer, play=play, all_constraints=all_constraints,
                 settings=settings, inner_cap=inner_cap,
                 context_key=context_key, memo=memo)
    if isinstance(prep, Verdict):
        return prep
    position, layouts = prep
    test = _SeqTest(decision, declarer, settings)
    start, step = 0, INNER_FIRST
    while start < len(layouts):
        batch = layouts[start:start + step]
        start += len(batch)
        step *= 2
        _, _, _, per_board = grader._solve(position, batch, level)
        v = test.feed(per_board, len(batch))
        if v is not None:
            return v
    return test.cap()


def _judge_batch(items, *, level, strain, declarer, play, all_constraints,
                 settings, inner_cap, context_key, memo, stats) -> dict:
    """Judge many memo-missed decisions together.

    Each item runs the same sequential rule on the same seeded inner sample as
    a lone `judge` call — verdicts are identical — but every wave's deals go
    to DDS in one aggregated call. Small per-judgement batches leave the DDS
    thread pool idle (measured: 12 ms/board at 5 boards/call vs 3.5 at 64);
    aggregation is the v1.4 performance plan's step 3.

    `items` is `[(memo key, layout_hands, decision), ...]`; returns
    `{key: Verdict}`, memoising and counting each fresh verdict in `stats`.
    """
    from . import grader  # lazy: grader imports this module

    verdicts: dict = {}
    live = []
    for key, L, d in items:
        prep = _prep(L, d, level=level, strain=strain, declarer=declarer,
                     play=play, all_constraints=all_constraints, settings=settings,
                     inner_cap=inner_cap, context_key=context_key, memo=memo)
        if isinstance(prep, Verdict):
            verdicts[key] = prep
            continue
        position, layouts = prep
        test = _SeqTest(d, declarer, settings)
        if not layouts:
            verdicts[key] = test.cap()
            continue
        live.append({'key': key, 'position': position, 'layouts': layouts,
                     'test': test, 'start': 0, 'step': INNER_FIRST})

    while live:
        deals, spans = [], []
        for it in live:
            batch = it['layouts'][it['start']:it['start'] + it['step']]
            it['start'] += len(batch)
            it['step'] *= 2
            spans.append((it, len(batch)))
            deals.extend(grader._build_deal(layout, it['position']) for layout in batch)
        t0 = time.perf_counter()
        boards = solve_all(deals)
        per_board_s = (time.perf_counter() - t0) / max(len(deals), 1)
        i, still = 0, []
        for it, count in spans:
            per_board = grader._collect(it['position'], boards[i:i + count])
            i += count
            memo.note_cost(it['key'], per_board_s * count)
            v = it['test'].feed(per_board, count)
            if v is not None:
                verdicts[it['key']] = v
            elif it['start'] < len(it['layouts']):
                still.append(it)
            else:
                verdicts[it['key']] = it['test'].cap()
        live = still

    for key, v in verdicts.items():
        memo.put(key, v)
        stats.judged += 1
        stats.sigmas.append(v.sigma)
    return verdicts


def _resolve(plan, ctx, settings, memo, stats, judge_kwargs) -> list[bool]:
    """One bool per `(layout, suspects)` of `plan`: consistent with expert play
    or not. A layout is consistent iff *every* suspect's verdict is, and each
    verdict is a pure function of its memo key (seeded per key), so the
    answer does not depend on which suspects are looked at or in what order —
    only the cost does. Hence: consult the memo for all suspects first (a
    remembered rejection settles the layout for free), and judge the rest one
    per wave, picking for each still-open layout the suspect with the best
    expected saving per second (`VerdictMemo.priority`) — the fresh verdicts
    of one wave update both the memo and that ordering for the next. Every
    wave's judgements go to DDS together (`_judge_batch`); nothing past a
    layout's rejection is ever judged.

    Depth > 1 (recursive expert judgements) keeps the simple one-at-a-time
    path through `judge`, since its inner sampling recurses into this loop."""
    def key_of(d):
        return (ctx, d.index, d.view, d.holding, d.card)

    if settings.depth != 1:
        out = []
        for L, suspects in plan:
            ok = True
            for d in suspects:
                v = judge(L, d, stats=stats, **judge_kwargs)
                if not v.consistent:
                    ok = False
                    break
            out.append(ok)
        return out

    verdict: list = [None] * len(plan)
    alive = []                          # (plan index, layout, pending suspects)
    for i, (L, suspects) in enumerate(plan):
        pending = []
        for d in suspects:
            v = memo.get(key_of(d))
            if v is None:
                pending.append(d)
                continue
            stats.memo_hits += 1
            if not v.consistent:
                verdict[i] = False
                break
        if verdict[i] is None:
            if pending:
                alive.append((i, L, pending))
            else:
                verdict[i] = True

    while alive:
        wave: dict = {}
        picks = []
        for i, L, pending in alive:
            d = max(pending, key=lambda d: memo.priority(key_of(d)))
            picks.append(d)
            wave.setdefault(key_of(d), (L, d))
        _judge_batch([(k, L, d) for k, (L, d) in wave.items()], stats=stats,
                     **judge_kwargs)
        still = []
        for (i, L, pending), d in zip(alive, picks):
            rest = []
            for x in pending:
                v = memo.get(key_of(x))
                if v is None:
                    rest.append(x)
                    continue
                if x is not d:
                    stats.memo_hits += 1     # settled by another layout's wave
                if not v.consistent:
                    verdict[i] = False
                    break
            if verdict[i] is None:
                if rest:
                    still.append((i, L, rest))
                else:
                    verdict[i] = True
        alive = still
    return verdict


# --- the outer loop ---------------------------------------------------------

def expert_layouts(position, view, constraints, all_constraints, num_deals,
                   settings, rng, *, level, context_key, memo=None):
    """Layouts for grading `position` through `view`'s eyes, each consistent
    with expert play by `view`'s opponents so far. Returns
    `(layouts, ExpertStats)`; on zero survivors the unfiltered pool with
    `inference='none'`."""
    from . import grader  # lazy: grader imports this module

    memo = memo if memo is not None else MEMO
    stats = ExpertStats()
    n = num_deals
    inner_cap = settings.inner_cap(num_deals)
    play = list(position.history)
    i = position.index
    strain, declarer = position.strain, position.declarer
    ctx = (context_key, settings.key(), inner_cap)

    accepted: list = []
    pool_all: list = []
    drawn = 0
    limit = settings.budget * n
    while len(accepted) < n and drawn < limit:
        # Draw only the deficit: every drawn layout is traced, and the trace
        # (one DDS line analysis from trick one) is the dominant cost.
        want = min(max(n - len(accepted), POOL_MIN), limit - drawn)
        pool = grader._sample_layouts(position, view, constraints, want, rng)
        if not pool:
            break
        drawn += len(pool)
        pool_all.extend(pool)

        decisions = [opponent_decisions(L, strain, declarer, play, i, view) for L in pool]
        if not any(decisions):
            accepted.extend(pool[:n - len(accepted)])
            stats.sampled = len(accepted)
            continue

        if settings.strict:
            costs = [None] * len(pool)
        else:
            deals = [grader._build_deal(L, grader._position_on(L, strain, declarer, []))
                     for L in pool]
            traces = analyse_plays(deals, [play[:i]] * len(pool))
            stats.traced += len(pool)
            costs = [dd_costs(t, ds, declarer) for t, ds in zip(traces, decisions)]

        # Resolve the round's verdicts wavefront-by-suspect-depth: judge the
        # k-th unresolved suspect of every still-alive layout together (their
        # inner deals share big DDS calls), drop layouts as a suspect rejects,
        # then move to depth k+1. Like the one-at-a-time path, nothing past a
        # layout's first rejection is ever judged — batching every suspect up
        # front tripled the fresh-judgement count on the board-7 benchmark.
        plan = []
        for L, ds, cost in zip(pool, decisions, costs):
            suspects = ds if cost is None else [d for d in ds if cost[d.index] > 0]
            plan.append((L, suspects))

        verdicts = _resolve(plan, ctx, settings, memo, stats, judge_kwargs=dict(
            level=level, strain=strain, declarer=declarer, play=play,
            all_constraints=all_constraints, settings=settings,
            inner_cap=inner_cap, context_key=ctx, memo=memo))

        for (L, _), ok in zip(plan, verdicts):
            if len(accepted) >= n:
                break
            stats.sampled += 1
            if ok:
                accepted.append(L)

    if not accepted:
        stats.inference = 'none'
        stats.consistent = 0
        return pool_all[:n], stats
    if stats.traced == 0 and stats.judged == 0 and stats.memo_hits == 0:
        stats.inference = 'trivial'
    stats.consistent = len(accepted)
    return accepted, stats
