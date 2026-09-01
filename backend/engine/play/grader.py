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
"""

import random
from collections import defaultdict

from endplay.types import Deal, Denom, Player

from ..dds_runtime import solve_all
from ..scoring import declarer_score, imps
from ..sampling import (
    build_known_and_constraints, check_hcp_feasibility, check_length_feasibility,
    generate_layouts,
)
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

def _sample_layouts(position, view, constraints, num_deals, rng):
    """Deals consistent with what `view` can see and with the play so far."""
    merged = infer_constraints(position, view, constraints)
    known, hcp, suit_length, acceptors, quality = build_known_and_constraints(
        view, position.original[view], merged)
    check_hcp_feasibility(known, hcp)
    check_length_feasibility(known, suit_length)
    layouts = generate_layouts(known, hcp, suit_length, acceptors, quality,
                               num_deals, rng=rng)
    if not layouts:
        raise ValueError(
            "No deals could be generated that fit both your constraints and the "
            "cards already played.")
    return layouts


def _build_deal(layout, position):
    deal = Deal('N:' + ' '.join(layout[s] for s in SEATS))
    deal.trump = STRAIN_DENOM[position.strain]
    deal.first = LETTER_PLAYER[position.opening_leader]
    for card in position.history:
        deal.play(card)
    return deal


def _solve(position, layouts, level):
    """One batched DDS call for the whole sample set at this position.

    `solve_board` prices every legal card of the player on play at once, so one
    board per sampled deal is all that is needed — and one lock acquisition per
    decision, not per card.

    Returns `(totals, successes, count)` keyed by card, in **declarer** tricks.
    """
    deals = [_build_deal(layout, position) for layout in layouts]
    boards = solve_all(deals)

    legal = set(legal_cards(position))
    won = position.declarer_tricks_won
    remaining = position.remaining_tricks
    on_declarer_side = position.to_play in position.declarer_side
    needed = level + 6

    totals = defaultdict(float)
    makes = defaultdict(int)
    counts = defaultdict(int)
    per_board = defaultdict(list)     # card -> declarer tricks on each board
    for board in boards:
        for card, tricks in board:
            name = card_to_str(card)
            if name not in legal:
                continue
            # DDS reports future tricks for the side **on play**; convert to
            # declarer tricks, then add the tricks already in the bag.
            declarer_tricks = (won + tricks if on_declarer_side
                               else won + (remaining - tricks))
            totals[name] += declarer_tricks
            counts[name] += 1
            per_board[name].append(declarer_tricks)
            if declarer_tricks >= needed:
                makes[name] += 1
    return totals, makes, counts, per_board


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


def _grade(position, view, level, method, num_deals, constraints, rng,
           scoring=None):
    """Price every legal card at `position` through `view`'s eyes."""
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    if method == 'double_dummy':
        layouts = [position.layout()]
    else:
        layouts = _sample_layouts(position, view, constraints, num_deals, rng)
    totals, makes, counts, per_board = _solve(position, layouts, level)
    return (_options(position, view, totals, makes, counts, per_board, scoring),
            len(layouts))


def tricks_needed_for(role: str, level: int) -> int:
    """Tricks the graded side needs: the contract for declarer, one more than
    the contract concedes for the defence."""
    return level + 6 if role == 'declarer' else 13 - (level + 6) + 1


# --- public entry points ----------------------------------------------------

def grade_position(hands, level, strain, declarer, play=(), *,
                   method='single_dummy', num_deals=20, constraints=None,
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
    options, sampled = ([], 0) if forced else _grade(
        position, view, level, method, num_deals, constraints, rng, scoring)

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
    }


def grade_play(hands, level, strain, declarer, play, seat, *,
               method='single_dummy', num_deals=20, constraints=None, seed=None,
               vul='none', penalty='none'):
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

    decisions = []
    for position, card in walk(hands, strain, declarer, play):
        if position.to_play not in graded_seats:
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
        }
        if not record['forced']:
            options, _ = _grade(position, seat, level, method, num_deals,
                                constraints, rng, scoring)
            by_card = {o['card']: o for o in options}
            best = options[0]['tricks'] if options else None
            best_cards = [o['card'] for o in options
                          if best is not None and abs(o['tricks'] - best) < 0.01]
            played = by_card.get(card, {})
            actual = played.get('tricks')
            record['options'] = options
            record['best_cards'] = best_cards
            record['best_tricks'] = best
            record['actual_tricks'] = actual
            if actual is not None and best is not None:
                diff = round(actual - best, 3)
                record['diff'] = diff
                record['best_score'] = options[0]['score']
                record['actual_score'] = played['score']
                record['score_diff'] = round(played['score'] - options[0]['score'], 1)
                record['imp_diff'] = played['imps']
                record['status'] = classify_with_imps(
                    diff, card in best_cards, played['imps'])
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
    }
