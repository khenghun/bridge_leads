"""
Opening-lead Monte-Carlo simulator.

For a given opening leader's hand + contract, generate many deals consistent with
the user's constraints on the three unseen hands, double-dummy solve each, and rank
every candidate opening lead by Matchpoints and IMPs.

Adapted from bridge_ai/solver/mce_defense_sim.py, trimmed to the opening-lead case
(no cards played yet, dummy not visible — only the leader's hand is known).

Deal sampling lives in `engine.sampling` and the DDS calls in
`engine.dds_runtime`; both are shared with the contract calculator.
"""

import random
from collections import defaultdict

from endplay.types import Deal, Player, Denom

from .. import scoring
from ..dds_runtime import solve_all
from ..deal_generator import PLAYERS as DG_PLAYERS
from ..sampling import (
    build_known_and_constraints, check_hcp_feasibility, generate_layouts,
    hand_to_cards,
)

PLAYER_LETTER = {Player.north: 'N', Player.east: 'E', Player.south: 'S', Player.west: 'W'}
LETTER_PLAYER = {v: k for k, v in PLAYER_LETTER.items()}
STRAIN_DENOM = {'C': Denom.clubs, 'D': Denom.diamonds, 'H': Denom.hearts,
                'S': Denom.spades, 'N': Denom.nt}


def simulate_opening_lead(leader_hand, level, strain, declarer,
                          vul='none', penalty='none', constraints=None,
                          num_simulations=50, max_attempts_factor=1000, seed=None,
                          max_samples=10):
    """
    Args:
        leader_hand:  the opening leader's 13 cards, as a PBN string ('S.H.D.C')
                      or a list of endplay cards.
        level:        contract level 1-7.
        strain:       'N','S','H','D','C'.
        declarer:     declarer seat letter 'N','E','S','W'.
        vul:          'none' | 'both' | 'ns' | 'ew'.
        penalty:      'none' | 'doubled' | 'redoubled'.
        constraints:  dict keyed by the OTHER players' letters:
                        {'hcp': {'S': (min,max), ...},
                         'suit_length': {'S': {'H': (min,max)}, ...},
                         'shapes': {'S': [ {suit:(min,max)}, ... ]},  # OR of terms
                        'quality': {'S': {'H': 'good'}},  # at most one, total
                         'fixed_cards': {'N': ['SA', ...]}}
        num_simulations: target number of solved deals.
        seed: if given, deals are generated from a private random.Random(seed)
              for reproducible, thread-safe results (same inputs -> same output,
              which also makes the call cacheable). None = nondeterministic.
        max_samples: per candidate lead, retain up to this many example deals in
              which that lead *defeats* the contract (for the UI to display).

    Returns:
        {
          'num_simulations': int,
          'leads': [ {card, defense_tricks, declarer_tricks, defeat_rate,
                      matchpoints, imps}, ... ]  # sorted best-first by IMPs
          'best_mp':  card,
          'best_imp': card,
          'samples': { card: [ {layout: {seat: 'S.H.D.C'}, declarer_tricks,
                                defense_tricks}, ... up to max_samples ] },
          'deals': { 'cards': [card, ...],   # fixed candidate-lead order
                     'records': [ {layout: {seat: 'S.H.D.C'},
                                   tricks: [declarer_tricks per card],
                                   scores: [leader score per card]},
                                  ... one per simulated deal ] },
        }
    """
    strain = strain.upper()
    declarer = declarer.upper()
    leader_letter = DG_PLAYERS[(DG_PLAYERS.index(declarer) + 1) % 4]  # LHO of declarer
    leader_player = LETTER_PLAYER[leader_letter]
    denom = STRAIN_DENOM[strain]

    leader_cards = (hand_to_cards(leader_hand)
                    if isinstance(leader_hand, str) else list(leader_hand))
    if len(leader_cards) != 13:
        raise ValueError(f"Leader hand must have 13 cards, got {len(leader_cards)}")

    known, hcp, suit_length, acceptors, quality = build_known_and_constraints(
        leader_letter, leader_cards, constraints)
    check_hcp_feasibility(known, hcp)

    # --- Phase 1: generate deals ---
    rng = random.Random(seed) if seed is not None else random
    deal_layouts = generate_layouts(known, hcp, suit_length, acceptors, quality,
                                    num_simulations, rng=rng,
                                    max_attempts_factor=max_attempts_factor)
    deals = []
    for layout in deal_layouts:
        deal = Deal('N:' + ' '.join(layout[p] for p in DG_PLAYERS))
        deal.trump = denom
        deal.first = leader_player   # leader is on lead for trick 1
        deals.append(deal)

    if not deals:
        return {'num_simulations': 0, 'leads': [], 'best_mp': None,
                'best_imp': None, 'samples': {},
                'deals': {'cards': [], 'records': []}}

    # --- Phase 2: batch DDS solve (multithreaded, in <=200-board chunks) ---
    board_results = solve_all(deals)

    # --- Phase 3: collect leader-side scores per candidate lead ---
    # leader_scores[card] = [leader_score_per_deal, ...]
    leader_scores = defaultdict(list)
    tricks_by_card = defaultdict(list)   # card -> declarer tricks per deal, aligned
    declarer_tricks_sum = defaultdict(int)
    defeat_count = defaultdict(int)
    deal_count = defaultdict(int)
    samples = defaultdict(list)   # card -> example deals it defeats (capped)
    contract_tricks_needed = 6 + level

    for i, board in enumerate(board_results):
        for card, defense_tricks in board:
            card_str = str(card)
            declarer_tricks = 13 - defense_tricks
            dscore = scoring.declarer_score(
                level, strain, declarer, declarer_tricks, vul=vul, penalty=penalty)
            leader_scores[card_str].append(-dscore)  # leader = defender perspective
            tricks_by_card[card_str].append(declarer_tricks)
            declarer_tricks_sum[card_str] += declarer_tricks
            deal_count[card_str] += 1
            if declarer_tricks < contract_tricks_needed:
                defeat_count[card_str] += 1
                if len(samples[card_str]) < max_samples:
                    samples[card_str].append({
                        'layout': deal_layouts[i],
                        'declarer_tricks': declarer_tricks,
                        'defense_tricks': defense_tricks,
                    })

    # Per-deal matrix for the frontend's pairwise lead comparison. Every
    # candidate lead must have been solved on every deal or the columns
    # below would silently misalign — fail loudly instead.
    cards = list(leader_scores)
    for c in cards:
        if len(leader_scores[c]) != len(deals) or len(tricks_by_card[c]) != len(deals):
            raise RuntimeError(
                f"DDS returned {len(leader_scores[c])} results for lead {c}, "
                f"expected one per deal ({len(deals)})")
    deals_out = {
        'cards': cards,
        'records': [
            {'layout': deal_layouts[i],
             'tricks': [tricks_by_card[c][i] for c in cards],
             'scores': [leader_scores[c][i] for c in cards]}
            for i in range(len(deals))
        ],
    }

    mp = scoring.aggregate(leader_scores, mode='matchpoints')
    imp = scoring.aggregate(leader_scores, mode='imps')

    leads = []
    for card in leader_scores:
        n = deal_count[card]
        leads.append({
            'card': card,
            'defense_tricks': (13 * n - declarer_tricks_sum[card]) / n,
            'declarer_tricks': declarer_tricks_sum[card] / n,
            'defeat_rate': defeat_count[card] / n,
            'matchpoints': mp[card],
            'imps': imp[card],
        })

    leads.sort(key=lambda r: r['imps'], reverse=True)
    best_imp = max(leads, key=lambda r: r['imps'])['card'] if leads else None
    best_mp = max(leads, key=lambda r: r['matchpoints'])['card'] if leads else None

    return {
        'num_simulations': len(deals),
        'leads': leads,
        'best_mp': best_mp,
        'best_imp': best_imp,
        'samples': dict(samples),
        'deals': deals_out,
    }
