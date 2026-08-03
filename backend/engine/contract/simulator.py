"""
Optimal-contract Monte-Carlo calculator.

Mirror image of the opening-lead simulator: instead of fixing the contract and
ranking leads, we fix our own hand plus what the auction told us about the
unseen hands and rank the *contracts* our side could be in.

Pipeline:
  1. Sample deals consistent with the constraints (`engine.sampling` — the same
     exact sampler the lead tool uses; only our own seat is known in full).
  2. Double-dummy **table** per deal (`engine.dds_runtime.calc_tables`): tricks
     for all 5 strains x all 4 declarers in one solve, ~5x the cost of a single
     lead solve but it prices every candidate contract at once.
  3. Score each candidate contract on each deal (pure arithmetic from step 2)
     and summarise: make rate, mean tricks, mean score, mean score when it fails.

We declare and are assumed undoubled, with the opponents defending double-dummy.
The MP/IMP ranking is deliberately *not* computed here: the response carries the
per-deal score matrix, so the frontend re-ranks instantly when the user switches
scoring mode or picks a different benchmark contract.
"""

import random
from collections import defaultdict

from endplay.types import Deal, Player, Denom, Penalty
from endplay.dds import par

from .. import scoring
from ..dds_runtime import calc_tables
from ..deal_generator import PLAYERS as DG_PLAYERS
from ..sampling import (
    build_known_and_constraints, check_hcp_feasibility, generate_layouts,
    hand_to_cards,
)
from . import candidates as cand

STRAIN_DENOM = {'C': Denom.clubs, 'D': Denom.diamonds, 'H': Denom.hearts,
                'S': Denom.spades, 'N': Denom.nt}
LETTER_PLAYER = {'N': Player.north, 'E': Player.east,
                 'S': Player.south, 'W': Player.west}
PLAYER_LETTER = {v: k for k, v in LETTER_PLAYER.items()}


def partner_of(seat):
    return DG_PLAYERS[(DG_PLAYERS.index(seat) + 2) % 4]


def _opponents_of(seat):
    return [DG_PLAYERS[(DG_PLAYERS.index(seat) + 1) % 4],
            DG_PLAYERS[(DG_PLAYERS.index(seat) + 3) % 4]]


def _opponent_stats(tables, our_seats, vul, full_table):
    """Context columns derived from the same DD tables, for free.

    - `opps_game_rate`: share of deals where the opponents can make a game
      (double-dummy) in some strain.
    - `par_competitive_rate`: share of deals where the par contract belongs to
      the opponents or is a doubled sacrifice by us — i.e. deals where the
      auction would not be ours alone, so the constructive ranking is standing
      on shakier ground. Only computable from a complete DD table, so it is
      None when the user excluded strains.
    """
    opps = [s for s in DG_PLAYERS if s not in our_seats]
    n = len(tables)
    if not n:
        return {'opps_game_rate': 0.0, 'par_competitive_rate': None}

    game_deals = 0
    for table in tables:
        for strain, game_level in cand.GAME_LEVEL.items():
            denom = STRAIN_DENOM[strain]
            if any(table[denom, LETTER_PLAYER[s]] >= 6 + game_level for s in opps):
                game_deals += 1
                break

    par_rate = None
    if full_table:
        dealer = LETTER_PLAYER[our_seats[0]]
        competitive = 0
        for table in tables:
            for contract in par(table, scoring.VUL_MAP[vul], dealer):
                theirs = PLAYER_LETTER[contract.declarer] in opps
                our_sacrifice = (not theirs
                                 and contract.penalty == Penalty.doubled
                                 and contract.result < 0)
                if theirs or our_sacrifice:
                    competitive += 1
                break           # par contracts are equivalent; one is enough
        par_rate = competitive / n

    return {'opps_game_rate': game_deals / n, 'par_competitive_rate': par_rate}


def simulate_contracts(hand, seat='S', vul='none', constraints=None,
                       num_deals=150, strains=cand.STRAINS, seed=None,
                       max_attempts_factor=1000):
    """
    Args:
        hand:        our own 13 cards, PBN 'S.H.D.C' or a list of endplay cards.
        seat:        the seat we sit in ('N','E','S','W'); partner is opposite.
        vul:         'none' | 'both' | 'ns' | 'ew'.
        constraints: same dict the lead simulator takes, keyed by the letters of
                     the three hands we cannot see (partner + both opponents):
                       {'hcp': {'N': (10,14)},
                        'suit_length': {'N': {'S': (5,5)}},
                        'shapes': {'N': [ {suit:(min,max)}, ... ]},
                        'quality': {'N': {'S': 'good'}},   # at most one, total
                        'fixed_cards': {'E': ['SA', ...]}}
        num_deals:   target number of solved deals.
        strains:     strains to consider; excluding some skips them in the DDS
                     table solve (dropping both minors is ~40% faster).
        seed:        private random.Random(seed) — reproducible and thread-safe.

    Returns:
        {
          'num_deals': int, 'seat': str, 'partner': str, 'vul': str,
          'candidates': [ {key, label, level, strain, declarer, kind,
                           tricks_needed, make_rate, mean_tricks, mean_score,
                           fail_mean_score, seat_delta}, ... ],
          'default_benchmark': key,      # highest-EV candidate, by mean score
          'opponents': {opps_game_rate, par_competitive_rate},
          'deals': {'candidates': [key, ...],
                    'records': [ {layout: {seat: 'S.H.D.C'},
                                  tricks: [declarer tricks per candidate],
                                  scores: [our score per candidate]}, ... ]},
        }
    """
    seat = seat.upper()
    if seat not in DG_PLAYERS:
        raise ValueError(f"unknown seat {seat!r}")
    partner = partner_of(seat)
    strains = [s.upper() for s in strains]

    our_cards = hand_to_cards(hand) if isinstance(hand, str) else list(hand)
    if len(our_cards) != 13:
        raise ValueError(f"Your hand must have 13 cards, got {len(our_cards)}")

    contracts = cand.enumerate_candidates(strains, declarers=(seat, partner))

    known, hcp, suit_length, acceptors, quality = build_known_and_constraints(
        seat, our_cards, constraints)
    check_hcp_feasibility(known, hcp)

    # --- Phase 1: generate deals ---
    rng = random.Random(seed) if seed is not None else random
    layouts = generate_layouts(known, hcp, suit_length, acceptors, quality,
                               num_deals, rng=rng,
                               max_attempts_factor=max_attempts_factor)
    if not layouts:
        return {'num_deals': 0, 'seat': seat, 'partner': partner, 'vul': vul,
                'candidates': [], 'default_benchmark': None,
                'opponents': {'opps_game_rate': 0.0, 'par_competitive_rate': None},
                'deals': {'candidates': [], 'records': []}}

    deals = [Deal('N:' + ' '.join(layout[p] for p in DG_PLAYERS)) for layout in layouts]

    # --- Phase 2: one DD table per deal (5 strains x 4 declarers) ---
    exclude = [STRAIN_DENOM[s] for s in cand.STRAINS if s not in strains]
    tables = calc_tables(deals, exclude=exclude)
    if len(tables) != len(deals):
        raise RuntimeError(
            f"DDS returned {len(tables)} tables for {len(deals)} deals")

    # --- Phase 3: tricks and scores per candidate ---
    # Tricks depend only on (strain, declarer), so solve that lookup once per
    # deal and let the four levels in a strain share it.
    tricks_by_seat_strain = defaultdict(list)     # (strain, declarer) -> per deal
    for table in tables:
        for strain in strains:
            denom = STRAIN_DENOM[strain]
            for declarer in (seat, partner):
                tricks_by_seat_strain[(strain, declarer)].append(
                    table[denom, LETTER_PLAYER[declarer]])

    n = len(deals)
    keys = [c['key'] for c in contracts]
    tricks_by_key = {}
    scores_by_key = {}
    for c in contracts:
        tricks = tricks_by_seat_strain[(c['strain'], c['declarer'])]
        # We are declaring, so the declarer's score IS our score (no sign flip,
        # unlike the lead simulator where we defend).
        score_for = {t: scoring.declarer_score(c['level'], c['strain'],
                                               c['declarer'], t, vul=vul)
                     for t in set(tricks)}
        tricks_by_key[c['key']] = tricks
        scores_by_key[c['key']] = [score_for[t] for t in tricks]

    mean_tricks_by_seat_strain = {
        k: sum(v) / n for k, v in tricks_by_seat_strain.items()
    }

    out_candidates = []
    for c in contracts:
        tricks = tricks_by_key[c['key']]
        scores = scores_by_key[c['key']]
        made = sum(1 for t in tricks if t >= c['tricks_needed'])
        failed = [i for i, t in enumerate(tricks) if t < c['tricks_needed']]
        other = partner if c['declarer'] == seat else seat
        out_candidates.append({
            **c,
            'make_rate': made / n,
            'mean_tricks': mean_tricks_by_seat_strain[(c['strain'], c['declarer'])],
            'mean_score': sum(scores) / n,
            'fail_mean_score': (sum(scores[i] for i in failed) / len(failed)
                                if failed else None),
            # How much the choice of declarer is worth in this strain (mean
            # tricks, this seat minus the other) — the UI flags a big gap.
            'seat_delta': (mean_tricks_by_seat_strain[(c['strain'], c['declarer'])]
                           - mean_tricks_by_seat_strain[(c['strain'], other)]),
        })

    # Default benchmark: the highest-EV contract, i.e. the best mean raw score
    # over every candidate. Mean score is the one candidate-set-independent
    # number we have, so the zero point does not move when the candidate list
    # changes; and when a slam really is the EV-max spot, saying so beats
    # measuring everything against a game nobody should be in.
    default_benchmark = (max(out_candidates, key=lambda c: c['mean_score'])['key']
                         if out_candidates else None)

    return {
        'num_deals': n,
        'seat': seat,
        'partner': partner,
        'vul': vul,
        'candidates': out_candidates,
        'default_benchmark': default_benchmark,
        'opponents': _opponent_stats(tables, (seat, partner), vul,
                                     full_table=len(strains) == len(cand.STRAINS)),
        'deals': {
            'candidates': keys,
            'records': [
                {'layout': layouts[i],
                 'tricks': [tricks_by_key[k][i] for k in keys],
                 'scores': [scores_by_key[k][i] for k in keys]}
                for i in range(n)
            ],
        },
    }
