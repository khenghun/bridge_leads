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
  choice), with the holding that opponent had at that moment on this layout.
- `dd_costs(trace, ...)` — from an `analyse_plays` trace of the real line on
  the layout, which of those cards lost a double-dummy trick on it. Those are
  the **suspects**; a card that lost nothing is accepted without a judgement
  (the fast-accept). `strict` judges every decision instead.
- `judge(...)` — the recursive single-dummy verdict on one suspect: sample the
  hands hidden from the opponent, price every legal card on each deal, and
  reject only if some alternative is *shown* better than the card played by
  more than the tolerance — a paired-difference test whose confidence margin
  shrinks with the inner sample (`Verdict`). Memoised on the opponent's
  holding, since dummy, the play and the constraints are the same for every
  layout.
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
from collections import OrderedDict
from dataclasses import dataclass, field

from ..dds_runtime import analyse_plays
from .state import SEATS, SUITS, RANKS, card_sort_key, next_seat, walk

INNER_BATCH = 5         # inner deals solved per sequential step
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
    holding: tuple          # the seat's remaining cards at j on this layout, sorted


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

    def clear(self) -> None:
        with self._lock:
            self._d.clear()

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
    at most 52 cards, pure Python)."""
    opp = opponents_of(view, declarer)
    dummy = next_seat(declarer, 2)
    out = []
    for position, card in walk(layout_hands, strain, declarer, play[:upto]):
        seat = position.to_play
        if seat not in opp:
            continue
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
        out.append(OpponentDecision(
            index=position.index, seat=seat,
            view=declarer if seat == dummy else seat, card=card,
            holding=tuple(sorted(hand, key=card_sort_key))))
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


def _judge_fresh(layout_hands, decision, *, level, strain, declarer, play,
                 all_constraints, settings, inner_cap, context_key, memo,
                 deals_hint) -> Verdict:
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

    actual = decision.card
    sign = 1 if view in (declarer, next_seat(declarer, 2)) else -1
    per_card: dict[str, list[float]] = {}
    n = 0
    z, tol = settings.confidence, settings.tolerance
    gap, sigma = 0.0, SD_FLOOR
    for start in range(0, len(layouts), INNER_BATCH):
        batch = layouts[start:start + INNER_BATCH]
        _, _, counts, per_board = grader._solve(position, batch, level)
        for card, values in per_board.items():
            per_card.setdefault(card, []).extend(values)
        n += len(batch)
        mine = per_card.get(actual)
        if not mine:
            return Verdict(True, 0.0, n, SD_FLOOR, 'no-alternative')
        worst_lcb, all_under, gap, sigma = -math.inf, True, 0.0, SD_FLOOR
        for card, theirs in per_card.items():
            if card == actual or len(theirs) != len(mine):
                continue
            diffs = [sign * (t - m) for t, m in zip(theirs, mine)]
            mean = sum(diffs) / n
            var = sum((d - mean) ** 2 for d in diffs) / (n - 1) if n > 1 else 0.0
            sd = max(math.sqrt(var), SD_FLOOR)
            se = sd / math.sqrt(n)
            if mean > gap:
                gap, sigma = mean, sd
            worst_lcb = max(worst_lcb, mean - z * se)
            if mean + z * se >= tol:
                all_under = False
        if worst_lcb == -math.inf:
            return Verdict(True, 0.0, n, SD_FLOOR, 'no-alternative')
        if worst_lcb > tol:
            return Verdict(False, round(gap, 3), n, round(sigma, 3), 'shown-worse')
        if all_under:
            return Verdict(True, round(gap, 3), n, round(sigma, 3), 'clear')
    return Verdict(True, round(gap, 3), n, round(sigma, 3), 'cap')


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

        for L, ds, cost in zip(pool, decisions, costs):
            if len(accepted) >= n:
                break
            stats.sampled += 1
            suspects = ds if cost is None else [d for d in ds if cost[d.index] > 0]
            ok = True
            for d in suspects:
                v = judge(L, d, level=level, strain=strain, declarer=declarer, play=play,
                          all_constraints=all_constraints, settings=settings,
                          inner_cap=inner_cap, context_key=ctx, memo=memo, stats=stats)
                if not v.consistent:
                    ok = False
                    break
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
