"""The play grader — one Monte-Carlo pipeline, parameterised by the *view* seat.

The question a play solver answers is "what was the best card **given what this
player could see**?", so the two hands the player could not see are sampled and
every candidate card is double-dummy solved on each sample. That is the same
pipeline the opening-lead and contract tools run, executed once per decision
instead of once per hand — which is why the deal source
(`engine.sampling.generate_layouts`) and the solver (`engine.dds_runtime`) are
the shared ones, not private copies.

Visibility, exactly:

- **Declarer** sees declarer + dummy; the two defenders are sampled. Declarer's
  decisions include the cards played from dummy.
- **A defender** sees their own hand + dummy; declarer and partner are sampled —
  except at the opening lead, where dummy is not yet faced, so only the
  leader's own 13 cards are known.

A sampled deal must be consistent with the play so far, so the unseen seats
carry two inferred constraints, ANDed with the user's: every card such a seat
has already played is pinned with `fixed_cards`, and a seat that **showed out**
of a suit has that suit's length pinned to the number of cards it played in it.
If the user's constraints contradict the play, the merge raises `ValueError`.

`method='double_dummy'` skips sampling entirely and grades against the actual
deal — hindsight, one board per decision.

**Expert opponents** (`expert=ExpertSettings(...)`) adds a second condition on
every sampled deal: the opponents' earlier plays must have been best plays
given what they could see — `engine.play.expert`, which judges each suspect
card by a Monte-Carlo from that opponent's own view. `expert_constraints` are
the user's constraints on *all four* seats (the auction was public), sliced per
judging view; `decisions` restricts `grade_play` to some play indices so a
slow analysis can be fetched trick by trick.
"""

import json
import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass

from endplay.types import Deal, Denom, Player

from ..dds_runtime import solve_all
from ..scoring import declarer_score, imps
from ..sampling import (
    LayoutStream, build_known_and_constraints, check_hcp_feasibility,
    check_length_feasibility, generate_layouts,
)
from .expert import ExpertSettings, expert_layouts
from .state import (
    SEATS, SUITS, Position, card_sort_key, legal_cards, next_seat, replay, walk,
)

STRAIN_DENOM = {'C': Denom.clubs, 'D': Denom.diamonds, 'H': Denom.hearts,
                'S': Denom.spades, 'N': Denom.nt}
LETTER_PLAYER = {'N': Player.north, 'E': Player.east,
                 'S': Player.south, 'W': Player.west}
SYMBOL_SUIT = {'♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C'}

METHODS = ('single_dummy', 'double_dummy')

# Classification of a decision by `diff = actual - best` tricks for the graded
# side. The source's thresholds, kept as-is.
OPTIMAL_BAND = 0.1
GOOD_BAND = -0.3


def card_to_str(card) -> str:
    """endplay's unicode card ('♠K') -> the project's input form ('SK')."""
    text = str(card)
    return SYMBOL_SUIT.get(text[0], text[0]) + text[1:]


def classify(diff: float, is_best: bool) -> str:
    """`optimal` | `good` | `suboptimal` for a trick difference."""
    if is_best or abs(diff) < OPTIMAL_BAND:
        return 'optimal'
    if diff >= GOOD_BAND:
        return 'good'
    return 'suboptimal'


# IMP demotion thresholds: a card that gives up this much in IMPs cannot wear
# a better badge than the one named, whatever the trick count said.
IMP_GOOD = 0.5          # >= this many IMPs given up: at most "good"
IMP_SUBOPTIMAL = 2.0    # >= this many: "suboptimal"


def classify_with_imps(diff: float, is_best: bool, imp_diff=None) -> str:
    """`classify` by tricks, then demoted by the IMP cost.

    Tricks alone misread the play that costs almost nothing on average but
    swings a game or slam on the deals where it matters: 0.05 tricks and a
    full IMP both come from "one deal in twenty goes down". The trick
    thresholds are unchanged (v1.0 grades stay comparable); the IMP cost can
    only lower a badge, never raise one, and the trick-best card is always
    optimal because its IMP cost is zero by construction.
    """
    status = classify(diff, is_best)
    if is_best or imp_diff is None:
        return status
    lost = -imp_diff
    if lost >= IMP_SUBOPTIMAL:
        return 'suboptimal'
    if lost >= IMP_GOOD and status == 'optimal':
        return 'good'
    return status


# Sample-size confidence (v1.4, `docs/play/v1.4-sample-size-plan.md`). A grade
# is a mean over sampled deals of the per-deal difference between the card
# played and the best card, and the solve already returns every card's trick
# count on every board — so the grade's standard error is free, and a grade
# that is in doubt can be extended with more deals rather than redrawn.
Z_BAND = 2.0                        # the band on a grade: diff ± Z_BAND · se
ESCALATION_CAP = {'plain': 600, 'expert': 300}


@dataclass
class EscalationSettings:
    """Re-grade a decision on `factor` × the base deal count when its base
    grade is not clearly optimal: status not `optimal`, or band not firm.
    The base sample is kept and extended; the extra layouts come from a stream
    seeded per decision, so no other decision's draw moves. `max_deals` caps
    the escalated count; None means the mode's default (600 plain, 300
    expert — the expert cost per deal is an order of magnitude higher)."""
    factor: int = 3
    max_deals: int | None = None

    def target(self, num_deals: int, expert_on: bool) -> int:
        cap = self.max_deals or ESCALATION_CAP['expert' if expert_on else 'plain']
        return max(num_deals, min(self.factor * num_deals, cap))


def _escalation_settings(escalation):
    """`None`, an `EscalationSettings`, or a dict of its fields."""
    if escalation is None or isinstance(escalation, EscalationSettings):
        return escalation
    return EscalationSettings(**escalation)


def _stream_rng(seed, index: int, tag: str):
    """A private rng for one decision's extra draws — the pre-scan or the
    escalation — so the seat's main stream (and every other decision's
    sample) is exactly what it is without them."""
    return random.Random(f'{seed}/{index}/{tag}') if seed is not None else random


def _se(values) -> float:
    n = len(values)
    return statistics.pstdev(values) / math.sqrt(n) if n > 1 else 0.0


def is_firm(diff, is_best, imp_diff, se_tricks, se_imps, z=Z_BAND) -> bool:
    """Whether every corner of the band `diff ± z·se_tricks` × `imp_diff ±
    z·se_imps` classifies as the point estimate does — the status would not
    change on a re-draw within the band. `is_best` holds only at the centre:
    a card that ties the best card at the point estimate is not taken to be
    best at the band's edge."""
    status = classify_with_imps(diff, is_best, imp_diff)
    for a in (-1, 0, 1):
        for b in (-1, 0, 1):
            corner = classify_with_imps(
                round(diff + a * z * se_tricks, 3), is_best and a == 0,
                None if imp_diff is None else round(imp_diff + b * z * se_imps, 2))
            if corner != status:
                return False
    return True


def _sample_stats(per_board, card, best, sign, scoring, diff, is_best, imp_diff,
                  trigger=None):
    """The grade's own uncertainty: the standard error of the paired per-deal
    difference `card − best`, in tricks and in IMPs, and whether the status
    is firm within `Z_BAND` of it. `trigger` names why the sample was
    extended (`status` / `band`), None when it was not. None if the card
    has no boards."""
    a, b = per_board.get(card), per_board.get(best)
    if not a or not b or len(a) != len(b):
        return None
    d = [sign * (x - y) for x, y in zip(a, b)]
    di = [imps(sign * (scoring.score(x) - scoring.score(y))) for x, y in zip(a, b)]
    se_tricks, se_imps = _se(d), _se(di)
    return {
        'deals': len(d),
        'se_tricks': round(se_tricks, 3),
        'se_imps': round(se_imps, 2),
        'firm': is_firm(diff, is_best, imp_diff, se_tricks, se_imps),
        'escalated': trigger is not None,
        'trigger': trigger,
    }


def _assess(options, per_board, played, sign, scoring, trigger=None):
    """The card `played` against the best card: the decision record's
    fields and its `sample` block (None when the card has no boards)."""
    by_card = {o['card']: o for o in options}
    best = options[0]['tricks'] if options else None
    best_cards = [o['card'] for o in options
                  if best is not None and abs(o['tricks'] - best) < 0.01]
    mine = by_card.get(played)
    fields = {
        'best_cards': best_cards,
        'best_tricks': best,
        'actual_tricks': mine['tricks'] if mine else None,
    }
    if mine is None or best is None:
        return fields, None
    diff = round(mine['tricks'] - best, 3)
    is_best = played in best_cards
    fields.update({
        'diff': diff,
        'best_score': options[0].get('score'),
        'actual_score': mine.get('score'),
        'score_diff': (round(mine['score'] - options[0]['score'], 1)
                       if 'score' in mine else None),
        'imp_diff': mine.get('imps'),
        'status': classify_with_imps(diff, is_best, mine.get('imps')),
    })
    sample = _sample_stats(per_board, played, options[0]['card'], sign, scoring,
                           diff, is_best, mine.get('imps'), trigger)
    return fields, sample


def _doubt_reason(options, per_board, played, sign, scoring):
    """The escalation trigger: why the card played does not read clearly
    optimal — `status` (not optimal) or `band` (not firm) — or None."""
    fields, sample = _assess(options, per_board, played, sign, scoring)
    if fields.get('status') is None:
        return None
    if fields['status'] != 'optimal':
        return 'status'
    if sample is not None and not sample['firm']:
        return 'band'
    return None


def _position_sample(options, per_board, sign, scoring, deals):
    """For a position (no card played): the best card against the runner-up;
    `firm` when the best card is ahead by more than the band."""
    if len(options) < 2:
        return {'deals': deals, 'se_tricks': 0.0, 'se_imps': 0.0,
                'firm': True, 'escalated': False, 'trigger': None}
    best, second = options[0]['card'], options[1]['card']
    d = [sign * (x - y) for x, y in zip(per_board[second], per_board[best])]
    di = [imps(sign * (scoring.score(x) - scoring.score(y)))
          for x, y in zip(per_board[second], per_board[best])]
    se_tricks, se_imps = _se(d), _se(di)
    margin = sum(d) / len(d) if d else 0.0
    return {'deals': deals, 'se_tricks': round(se_tricks, 3), 'se_imps': round(se_imps, 2),
            'firm': margin + Z_BAND * se_tricks < 0, 'escalated': False, 'trigger': None}


def visible_seats(position: Position, view: str) -> list[str]:
    """The seats whose 13 cards the `view` seat can see at this position."""
    if view in position.declarer_side:
        return [position.declarer, position.dummy]
    if position.index == 0:
        return [view]                   # opening lead: dummy is not yet faced
    return [view, position.dummy]


def view_for(position: Position, seat: str) -> str:
    """Whose eyes we grade through when `seat` is on play (dummy -> declarer)."""
    return position.declarer if seat == position.dummy else seat


def role_of(position: Position, seat: str) -> str:
    return 'declarer' if seat in position.declarer_side else 'defender'


# --- inferring what the play reveals ---------------------------------------

def infer_constraints(position: Position, view: str, constraints=None) -> dict:
    """User constraints AND what the play has already shown about unseen seats.

    Returns a constraint dict in the engine's public format, ready for
    `sampling.build_known_and_constraints` with `own_seat=view`. The other
    visible hand (dummy, or declarer when grading from dummy's side) is passed
    as 13 pinned cards, which `sampling` merges into `known_hands` — the same
    treatment the user's own hand gets.
    """
    constraints = constraints or {}
    visible = visible_seats(position, view)
    unseen = [s for s in SEATS if s not in visible]

    for seat in visible:
        for block in ('hcp', 'suit_length', 'shapes', 'quality', 'fixed_cards'):
            if (constraints.get(block) or {}).get(seat):
                raise ValueError(
                    f"{seat}'s hand is visible to {view} at this point, so it "
                    "cannot be constrained — constrain only the hidden seats "
                    f"({', '.join(unseen)}).")

    out = {k: v for k, v in constraints.items() if k not in ('fixed_cards', 'suit_length')}

    # Pinned cards: the other visible hand in full, plus every card an unseen
    # seat has already played.
    fixed = {seat: list(cards)
             for seat, cards in (constraints.get('fixed_cards') or {}).items()
             if cards}
    for seat in visible:
        if seat != view:
            fixed[seat] = list(position.original[seat])
    for seat in unseen:
        played = position.played_by[seat]
        if played:
            merged = list(fixed.get(seat, []))
            merged += [c for c in played if c not in merged]
            fixed[seat] = merged
    if fixed:
        out['fixed_cards'] = fixed

    # Show-outs: a seat that failed to follow suit holds exactly the cards of
    # that suit it has already played — no more, no fewer.
    lengths = {seat: dict(bounds)
               for seat, bounds in (constraints.get('suit_length') or {}).items()
               if bounds}
    for seat in unseen:
        for suit in sorted(position.show_outs[seat], key=SUITS.index):
            shown = sum(1 for c in position.played_by[seat] if c[0] == suit)
            box = lengths.setdefault(seat, {})
            lo, hi = box.get(suit, (None, None))
            lo = shown if lo is None else max(lo, shown)
            hi = shown if hi is None else min(hi, shown)
            if lo > hi:
                raise ValueError(
                    f"{seat} showed out of {suit} after playing {shown}, but the "
                    f"constraints ask for {box[suit][0]}-{box[suit][1]} {suit}.")
            box[suit] = (lo, hi)
    if lengths:
        out['suit_length'] = lengths
    return out


# --- the solve --------------------------------------------------------------

def _sampler_inputs(position, view, constraints):
    """The sampler's inputs for deals consistent with what `view` can see and
    with the play so far; raises `ValueError` when they are infeasible."""
    merged = infer_constraints(position, view, constraints)
    known, hcp, suit_length, acceptors, quality = build_known_and_constraints(
        view, position.original[view], merged)
    check_hcp_feasibility(known, hcp)
    check_length_feasibility(known, suit_length)
    return known, hcp, suit_length, acceptors, quality


def _sample_layouts(position, view, constraints, num_deals, rng):
    """Deals consistent with what `view` can see and with the play so far."""
    layouts = generate_layouts(*_sampler_inputs(position, view, constraints),
                               num_deals, rng=rng)
    if not layouts:
        raise ValueError(
            "No deals could be generated that fit both your constraints and the "
            "cards already played.")
    return layouts


def _layout_stream(position, view, constraints, num_deals, rng) -> LayoutStream:
    """`_sample_layouts` taken lazily: the same `num_deals` layouts in the
    same order, drawn as the caller asks for them (`take(k)`). The expert
    judgement stops early on most samples, so it never draws the rest."""
    return LayoutStream(*_sampler_inputs(position, view, constraints), num_deals, rng=rng)


def _position_on(layout_hands, strain, declarer, play) -> Position:
    """The position after `play` on a (sampled or real) layout."""
    return replay(layout_hands, strain, declarer, play)


# DDS's board encoding (endplay's `_dds.deal`): hands N/E/S/W = 0..3, suits
# S/H/D/C = 0..3, a suit holding is a bitmask with rank r (2..14) at bit r,
# and a card on the table is (suit index, rank 2..14).
_SEAT_INDEX = {s: i for i, s in enumerate(SEATS)}
_SUIT_INDEX = {s: i for i, s in enumerate(SUITS)}
_RANK_VALUE = {r: 14 - i for i, r in enumerate('AKQJT98765432')}
_RANK_BIT = {r: 1 << v for r, v in _RANK_VALUE.items()}
_RANKS_BY_BIT = tuple(_RANK_BIT.items())


def _build_deal(layout, position):
    """The DDS board for `layout` at `position`: each seat's dealt cards minus
    what it has played, the trick on the table, its leader, and the strain.

    Written straight into endplay's `Deal` struct rather than parsed from PBN
    and replayed card by card — the play solver builds tens of thousands of
    boards per graded decision, and that path was ~5% of a strict decision.
    A layout is consistent with the play by construction (played cards are
    pinned when sampling); a card the layout does not hold raises, as the
    replay did.
    """
    deal = Deal()
    data = deal._data
    data.trump = STRAIN_DENOM[position.strain]
    data.first = LETTER_PLAYER[position.trick_leader]
    for k, card in enumerate(position.current_trick):
        data.currentTrickSuit[k] = _SUIT_INDEX[card[0]]
        data.currentTrickRank[k] = _RANK_VALUE[card[1]]
    remain = data.remainCards
    for seat in SEATS:
        hand = layout[seat]
        holdings = remain[_SEAT_INDEX[seat]]
        if isinstance(hand, str):
            for si, chars in enumerate(hand.split('.')):
                mask = 0
                for ch in chars:
                    mask |= _RANK_BIT[ch]
                holdings[si] = mask
        else:
            masks = [0, 0, 0, 0]
            for card in hand:
                masks[_SUIT_INDEX[card[0]]] |= _RANK_BIT[card[1]]
            for si in range(4):
                holdings[si] = masks[si]
        for card in position.played_by[seat]:
            si, bit = _SUIT_INDEX[card[0]], _RANK_BIT[card[1]]
            if not holdings[si] & bit:
                raise ValueError(f"{seat} played {card} but does not hold it on this layout")
            holdings[si] &= ~bit
    return deal


def _solve(position, layouts, level):
    """One batched DDS call for the whole sample set at this position.

    `solve_board` prices every legal card of the player on play at once, so one
    board per sampled deal is all that is needed — and one lock acquisition per
    decision, not per card.

    Returns `(totals, successes, count)` keyed by card, in **declarer** tricks.
    """
    per_board = _solve_boards(position, layouts)
    totals, makes, counts = _tally(per_board, level)
    return totals, makes, counts, per_board


def _solve_boards(position, layouts):
    """`layouts` at `position` solved in one DDS batch -> per-board tricks."""
    return _collect(position, solve_all(
        [_build_deal(layout, position) for layout in layouts]))


def _tally(per_board, level):
    """Per-card totals / makes / counts from the per-board trick counts."""
    needed = level + 6
    totals = defaultdict(float)
    makes = defaultdict(int)
    counts = defaultdict(int)
    for name, values in per_board.items():
        counts[name] = len(values)
        totals[name] = float(sum(values))
        makes[name] = sum(1 for t in values if t >= needed)
    return totals, makes, counts


def _collect(position, boards):
    """Solved `boards` at `position` -> {card: declarer tricks per board}.

    Split out of `_solve` so the expert filter can aggregate many judgements'
    boards into one DDS call and convert each judgement's slice separately.
    """
    legal = set(legal_cards(position))
    won = position.declarer_tricks_won
    remaining = position.remaining_tricks
    on_declarer_side = position.to_play in position.declarer_side
    per_board = defaultdict(list)     # card -> declarer tricks on each board
    for board in boards:
        # Read DDS's futureTricks directly: `cards` entries of (suit, rank,
        # equals-mask, score); a score of -1 is an unplayable slot. The
        # equals mask names the touching cards DDS folded into that entry.
        # (endplay's iterator builds a Card object per card — measured at 4%
        # of a strict decision.)
        fut = board._data
        for k in range(fut.cards):
            tricks = fut.score[k]
            if tricks == -1:
                continue
            # DDS reports future tricks for the side **on play**; convert to
            # declarer tricks, then add the tricks already in the bag.
            declarer_tricks = (won + tricks if on_declarer_side
                               else won + (remaining - tricks))
            suit = SUITS[fut.suit[k]]
            holding = (1 << fut.rank[k]) | fut.equals[k]
            for rank, bit in _RANKS_BY_BIT:
                if holding & bit:
                    name = suit + rank
                    if name in legal:
                        per_board[name].append(declarer_tricks)
    return per_board


class Scoring:
    """The contract's scoring context, so a trick count can be priced.

    `score(declarer_tricks)` is the duplicate score for **declarer**; the grader
    flips the sign for a defender's view. Memoised per trick count because a
    position prices at most 14 distinct outcomes, however many deals it samples.
    """

    def __init__(self, level, strain, declarer, vul='none', penalty='none'):
        self.level, self.strain, self.declarer = level, strain, declarer
        self.vul, self.penalty = vul or 'none', penalty or 'none'
        self._cache = {}

    def score(self, declarer_tricks):
        t = int(round(declarer_tricks))
        if t not in self._cache:
            self._cache[t] = declarer_score(
                self.level, self.strain, self.declarer, t, self.vul, self.penalty)
        return self._cache[t]


def _options(position, view, totals, makes, counts, per_board=None, scoring=None):
    """Per-card means, in the *graded side's* perspective, best first.

    Ranking is by expected tricks (then success rate). When `scoring` is given,
    each option also carries its mean duplicate `score` for the graded side and
    `imps`: the mean, over the sampled deals, of the IMP swing between this card
    and the **trick-best** card on the same deal — a per-deal conversion, so a
    single game swing is not averaged away.
    """
    graded_is_declarer = view in position.declarer_side
    sign = 1 if graded_is_declarer else -1
    out = []
    for card, n in counts.items():
        if not n:
            continue
        declarer_tricks = totals[card] / n
        tricks = declarer_tricks if graded_is_declarer else 13 - declarer_tricks
        rate = makes[card] / n
        out.append({
            'card': card,
            'tricks': round(tricks, 3),
            'success_rate': round(rate if graded_is_declarer else 1 - rate, 3),
        })
    out.sort(key=lambda o: (-o['tricks'], -o['success_rate'], card_sort_key(o['card'])))
    if scoring is not None and per_board and out:
        best = per_board[out[0]['card']]
        best_scores = [sign * scoring.score(t) for t in best]
        for o in out:
            mine = [sign * scoring.score(t) for t in per_board[o['card']]]
            o['score'] = round(sum(mine) / len(mine), 1)
            o['imps'] = round(
                sum(imps(a - b) for a, b in zip(mine, best_scores)) / len(mine), 2)
    return out


def _layouts(position, view, level, method, num_deals, constraints, rng, expert,
             all_constraints, context_key, memo, start=None, stats=None,
             base_deals=None):
    """The deals a grade rests on: the real one, the expert-filtered sample,
    or the plain sample. Returns `(layouts, ExpertStats | None)`."""
    if method == 'double_dummy':
        return [position.layout()], None
    if expert is not None:
        return expert_layouts(
            position, view, constraints, all_constraints or {}, num_deals, expert,
            rng, level=level, context_key=context_key, memo=memo,
            start=start, stats=stats, base_deals=base_deals)
    return _sample_layouts(position, view, constraints, num_deals, rng), None


def _grade(position, view, level, method, num_deals, constraints, rng,
           scoring=None, expert=None, all_constraints=None, context_key=None,
           memo=None, escalation=None, played=None, seed=None):
    """Price every legal card at `position` through `view`'s eyes.

    Returns `(options, per_board, deals_used, expert_stats, trigger)` —
    `trigger` is why the sample was extended (`status`, `band`) or None;
    `expert_stats` is None unless expert opponents are on (and sampling).

    With `escalation` and the card `played`, a base grade that is in doubt
    (`_in_doubt`: not optimal, or not firm within the band) is **extended**
    to `escalation.target` deals — the base layouts stay and more are drawn
    from the decision's own stream. (A third trigger — the unfiltered
    grade at the base count as a second opinion under expert opponents —
    was built, measured and dropped 2026-09-08: every extension it caused
    on the benchmarks ended firm optimal, at ~70 % of the added time.)
    The expert filter's inner cap stays at the base count throughout, so every earlier verdict is a memo hit and the
    escalated sample is from the same population as the base one."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    layouts, st = _layouts(position, view, level, method, num_deals, constraints,
                           rng, expert, all_constraints, context_key, memo)
    per_board = _solve_boards(position, layouts)
    options = _options(position, view, *_tally(per_board, level), per_board, scoring)
    trigger = None
    expert_on = expert is not None and method != 'double_dummy'
    if (escalation is not None and played is not None and scoring is not None
            and method != 'double_dummy'):
        sign = 1 if view in position.declarer_side else -1
        target = escalation.target(num_deals, expert_on)
        if target > len(layouts):
            trigger = _doubt_reason(options, per_board, played, sign, scoring)
        if trigger is not None:
            more = _stream_rng(seed, position.index, 'more')
            if expert_on and st is not None and st.inference != 'none':
                grown, st = _layouts(
                    position, view, level, method, target, constraints, more, expert,
                    all_constraints, context_key, memo, start=layouts, stats=st,
                    base_deals=num_deals)
                new = grown[len(layouts):]
            else:
                new = _sample_layouts(position, view, constraints,
                                      target - len(layouts), more)
                grown = layouts + new
            if new:
                for card, values in _solve_boards(position, new).items():
                    per_board[card].extend(values)
                layouts = grown
                options = _options(position, view, *_tally(per_board, level),
                                   per_board, scoring)
            else:
                trigger = None
    stats = st.as_dict(expert, expert.inner_cap(num_deals)) if st is not None else None
    return options, per_board, len(layouts), stats, trigger


def _context_key(hands, level, strain, declarer, play, all_constraints):
    """Names everything a judgement verdict depends on besides the opponent's
    holding — the memo key's fixed part."""
    return (json.dumps(hands, sort_keys=True), level, strain, declarer, tuple(play),
            json.dumps(all_constraints or {}, sort_keys=True, default=list))


def tricks_needed_for(role: str, level: int) -> int:
    """Tricks the graded side needs: the contract for declarer, one more than
    the contract concedes for the defence."""
    return level + 6 if role == 'declarer' else 13 - (level + 6) + 1


# --- public entry points ----------------------------------------------------

def grade_position(hands, level, strain, declarer, play=(), *,
                   method='single_dummy', num_deals=40, constraints=None,
                   expert=None, expert_constraints=None, memo=None,
                   seed=None, vul='none', penalty='none'):
    """Grade the legal cards for whoever is on play, from that player's view.

    The interactive primitive: no `seat`, `play` is simply the history up to the
    position of interest. When dummy is on play the view is declarer's, since
    declarer chooses dummy's cards.
    """
    position = replay(hands, strain, declarer, play)
    if position.complete:
        raise ValueError("the play is complete — there is no card left to choose.")

    to_play = position.to_play
    view = view_for(position, to_play)
    role = role_of(position, to_play)
    legal = legal_cards(position)
    rng = random.Random(seed) if seed is not None else random

    forced = len(legal) == 1
    scoring = Scoring(level, strain, position.declarer, vul, penalty)
    expert = _expert_settings(expert)
    ctx = _context_key(hands, level, strain, declarer, list(play), expert_constraints)
    options, per_board, sampled, stats, _ = ([], {}, 0, None, False) if forced else _grade(
        position, view, level, method, num_deals, constraints, rng, scoring,
        expert=expert, all_constraints=expert_constraints, context_key=ctx, memo=memo)
    sign = 1 if view in position.declarer_side else -1
    sample = None if forced else _position_sample(options, per_board, sign, scoring, sampled)

    return {
        'to_play': to_play,
        'role': role,
        'view': view,
        'visible': visible_seats(position, view),
        'trick': position.trick_number,
        'index': position.index,
        'forced': forced,
        'legal_cards': legal,
        'tricks_won': position.tricks_won,
        'tricks_needed': tricks_needed_for(role, level),
        'options': options,
        'method': method,
        'num_deals': sampled,
        'expert': stats,
        'sample': sample,
    }


def _expert_settings(expert):
    """`None`, an `ExpertSettings`, or a dict of its fields."""
    if expert is None or isinstance(expert, ExpertSettings):
        return expert
    return ExpertSettings(**expert)


def grade_play(hands, level, strain, declarer, play, seat, *,
               method='single_dummy', num_deals=40, constraints=None, seed=None,
               vul='none', penalty='none', expert=None, expert_constraints=None,
               decisions=None, memo=None, escalation=None):
    """Grade every decision `seat` made in the recorded play.

    For declarer that includes the cards played from dummy; dummy itself makes
    no decisions and is rejected. `actual_tricks` / `best_tricks` are for the
    **graded side** (13 - declarer tricks for a defender), and `success_rate` is
    the make rate for declarer, the defeat rate for a defender.

    Each decision is also priced: `actual_score` / `best_score` are mean
    duplicate scores for the graded side under `vul` / `penalty`, `score_diff`
    their difference in points, and `imp_diff` the mean per-deal IMP swing of
    the card played against the best card (≤ 0, like `diff`). So an overtrick
    given away in 3NT and a game let through both read "−1 trick" but price
    very differently. The status badge is classified on tricks and then
    demoted by the IMP cost (`classify_with_imps`).

    `decisions`, when given, is the set of play indices to grade — the others
    are left out of the result entirely (the caller merges chunks); the
    summary then covers the chunk. `expert` turns on the expert-opponents
    filter (`engine.play.expert`) and each graded decision carries its
    sampling counts under `expert`.

    Every graded decision also carries `sample`: the deals it rests on, the
    standard error of its diff in tricks and IMPs, and `firm` — whether the
    status holds across the ±2σ band. `escalation` (an `EscalationSettings`
    or its dict) re-grades a decision in doubt on more deals (`_grade`);
    `summary.marginal` counts the graded decisions still not firm.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    seat = (seat or '').upper()
    if seat not in SEATS:
        raise ValueError(f"seat must be N/E/S/W, got {seat!r}")
    dummy = next_seat((declarer or '').upper(), 2)
    if seat == dummy:
        raise ValueError(
            f"{seat} is dummy and makes no decisions — declarer plays dummy's "
            "cards. Grade the declarer instead.")

    # Validate the whole play before spending a single DDS call on it.
    final = replay(hands, strain, declarer, play)
    role = role_of(final, seat)
    graded_seats = final.declarer_side if role == 'declarer' else {seat}
    rng = random.Random(seed) if seed is not None else random
    scoring = Scoring(level, strain, final.declarer, vul, penalty)
    expert = _expert_settings(expert)
    escalation = _escalation_settings(escalation)
    ctx = _context_key(hands, level, strain, declarer, list(play), expert_constraints)
    wanted = None if decisions is None else set(decisions)
    sign = 1 if seat in final.declarer_side else -1

    decisions = []
    for position, card in walk(hands, strain, declarer, play):
        if position.to_play not in graded_seats:
            continue
        if wanted is not None and position.index not in wanted:
            continue
        legal = legal_cards(position)
        record = {
            'index': position.index,
            'trick': position.trick_number,
            'position': len(position.current_trick),
            'hand': position.to_play,
            'card': card,
            'forced': len(legal) == 1,
            'actual_tricks': None,
            'best_tricks': None,
            'diff': None,
            'actual_score': None,
            'best_score': None,
            'score_diff': None,
            'imp_diff': None,
            'status': 'forced',
            'options': [],
            'best_cards': [],
            'expert': None,
            'sample': None,
        }
        if not record['forced']:
            options, per_board, _, stats, trigger = _grade(
                position, seat, level, method, num_deals, constraints, rng, scoring,
                expert=expert, all_constraints=expert_constraints, context_key=ctx,
                memo=memo, escalation=escalation, played=card, seed=seed)
            record['expert'] = stats
            record['options'] = options
            fields, sample = _assess(options, per_board, card, sign, scoring, trigger)
            record.update(fields)
            record['sample'] = sample
        decisions.append(record)

    graded = [d for d in decisions if not d['forced'] and d['diff'] is not None]
    loss = sum(max(0.0, -d['diff']) for d in graded)
    score_loss = sum(max(0.0, -d['score_diff']) for d in graded)
    imp_loss = sum(max(0.0, -d['imp_diff']) for d in graded)
    summary = {
        'decisions': len(decisions),
        'graded': len(graded),
        'optimal': sum(1 for d in graded if d['status'] == 'optimal'),
        'good': sum(1 for d in graded if d['status'] == 'good'),
        'suboptimal': sum(1 for d in graded if d['status'] == 'suboptimal'),
        'marginal': sum(1 for d in graded if d['sample'] and not d['sample']['firm']),
        'total_trick_loss': round(loss, 2),
        'avg_trick_loss': round(loss / len(graded), 3) if graded else 0.0,
        'total_score_loss': round(score_loss, 1),
        'total_imp_loss': round(imp_loss, 2),
    }

    return {
        'seat': seat,
        'role': role,
        'visible': ([final.declarer, final.dummy] if role == 'declarer'
                    else [seat, final.dummy]),
        'tricks_needed': tricks_needed_for(role, level),
        'decisions': decisions,
        'summary': summary,
        'method': method,
        'num_deals': 1 if method == 'double_dummy' else num_deals,
        'expert': expert.__dict__ if expert is not None else None,
        'escalation': escalation.__dict__ if escalation is not None else None,
    }
