"""
Opening-lead Monte-Carlo simulator.

For a given opening leader's hand + contract, generate many deals consistent with
the user's constraints on the three unseen hands, double-dummy solve each, and rank
every candidate opening lead by Matchpoints and IMPs.

Adapted from bridge_ai/solver/mce_defense_sim.py, trimmed to the opening-lead case
(no cards played yet, dummy not visible — only the leader's hand is known).
"""

import os
import random
from collections import defaultdict

import endplay._dds as _dds
from endplay.types import Deal, Player, Denom
from endplay.dds import solve_board, solve_all_boards

# DDS's batch solver (SolveAllBoardsBin) multithreads across CPU cores, but its
# board array is capped at MAXNOOFBOARDS (200). Passing more raises, so we feed
# it in batches of this size to keep the fast, parallel path.
_DDS_BATCH = _dds.MAXNOOFBOARDS

# Cap DDS worker threads. DDS otherwise grabs every core and allocates memory
# per thread — bad on a shared/public box with concurrent users. Override with
# the BRIDGE_DDS_THREADS env var (0 = let DDS auto-detect all cores).
_DDS_THREADS = int(os.environ.get('BRIDGE_DDS_THREADS') or min(os.cpu_count() or 1, 4))
if _DDS_THREADS > 0:
    _dds.SetMaxThreads(_DDS_THREADS)

from .deal_generator import generate_deal, PLAYERS as DG_PLAYERS, calculate_hcp
from .honor_sampler import ExactDealSampler
from .shapes import compile_shapes
from . import scoring

# If the exact sampler's shape-rejection step throws away this many draws
# without producing a single deal, the shape constraints are pathologically
# tight for plain rejection; switch to the legacy steered generator (its
# distribution is approximate, but it fills suit minimums during placement).
_EXACT_FALLBACK_ATTEMPTS = 3000

SUIT_ORDER = ['S', 'H', 'D', 'C']
SORT_RANK = {r: i for i, r in enumerate('AKQJT98765432')}
PLAYERS_LIST = [Player.north, Player.east, Player.south, Player.west]
PLAYER_LETTER = {Player.north: 'N', Player.east: 'E', Player.south: 'S', Player.west: 'W'}
LETTER_PLAYER = {v: k for k, v in PLAYER_LETTER.items()}
STRAIN_DENOM = {'C': Denom.clubs, 'D': Denom.diamonds, 'H': Denom.hearts,
                'S': Denom.spades, 'N': Denom.nt}


def _solve_all(deals):
    """Double-dummy solve every deal, in MAXNOOFBOARDS-sized batches.

    Each batch goes through DDS's multithreaded SolveAllBoardsBin; if a batch
    errors we fall back to solving its boards one at a time so a single bad
    deal can't sink the whole run.
    """
    results = []
    for i in range(0, len(deals), _DDS_BATCH):
        batch = deals[i:i + _DDS_BATCH]
        try:
            results.extend(solve_all_boards(batch))
        except Exception:
            results.extend(solve_board(d) for d in batch)
    return results


def hand_to_cards(hand_str):
    """PBN hand string 'S.H.D.C' -> list of endplay cards (suit+rank)."""
    if not hand_str:
        return []
    cards = []
    for suit_chars, suit in zip(hand_str.split('.'), SUIT_ORDER):
        for rank in suit_chars:
            cards.append(suit + rank)
    return cards


def _hand_list_to_str(cardlist):
    """List of cards -> PBN hand string (suits high-to-low)."""
    suits = {'S': [], 'H': [], 'D': [], 'C': []}
    for card in cardlist:
        if len(card) == 2:
            suits[card[0]].append(card[1])
    for s in SUIT_ORDER:
        suits[s].sort(key=lambda r: SORT_RANK.get(r, 99))
    return '.'.join(''.join(suits[s]) for s in SUIT_ORDER)


def _merge_box(box, env):
    """Intersect a per-suit (min,max) box with an envelope (tighter bound wins).
    `box` bounds may be None (unbounded); `env` bounds are concrete ints."""
    merged = dict(box)
    for s, (lo, hi) in env.items():
        elo, ehi = box.get(s, (None, None))
        mlo = lo if elo is None else max(lo, elo)
        mhi = hi if ehi is None else min(hi, ehi)
        merged[s] = (mlo, mhi)
    return merged


def _build_known_and_constraints(leader_letter, leader_cards, constraints):
    """Translate the public constraint dict (keyed by player letter) into the
    deal_generator's format. Returns (known_hands, hcp, suit_length, acceptors).

    Disjunctive `shapes` are compiled into (a) an envelope merged into the
    per-suit bounds to keep generation efficient, and (b) acceptor predicates
    that reject finished hands matching no term."""
    constraints = constraints or {}
    known = {leader_letter: list(leader_cards)}

    # fixed_cards merge into known hands
    for p, cards in (constraints.get('fixed_cards') or {}).items():
        known.setdefault(p, [])
        known[p] = list(known[p]) + [c for c in cards if c not in known[p]]

    hcp = dict(constraints.get('hcp') or {})
    suit_length = {p: dict(v) for p, v in (constraints.get('suit_length') or {}).items()}

    acceptors = {}
    for p, terms in (constraints.get('shapes') or {}).items():
        if not terms:
            continue
        env, predicate = compile_shapes(terms)
        suit_length[p] = _merge_box(suit_length.get(p, {}), env)
        acceptors[p] = predicate

    return known, hcp, suit_length, acceptors


def _check_hcp_feasibility(known, hcp):
    """The deck holds exactly 40 HCP. Raise ValueError when the per-seat HCP
    bounds (combined with each seat's known cards) can never sum to 40 —
    otherwise generation would grind through every attempt and find nothing."""
    min_total = 0
    max_total = 0
    for p in DG_PLAYERS:
        fixed_cards = known.get(p, [])
        fixed = calculate_hcp(fixed_cards)
        lo, hi = hcp.get(p, (None, None))
        lo = 0 if lo is None else lo
        hi = 40 if hi is None else hi
        if fixed > hi:
            raise ValueError(
                f"No way to meet the HCP constraints: {p}'s known cards already "
                f"hold {fixed} HCP, above the {hi} HCP maximum.")
        if len(fixed_cards) == 13:
            hi = fixed          # a fully-known hand contributes exactly its HCP
        min_total += max(lo, fixed)
        max_total += hi
    if min_total > 40:
        raise ValueError(
            f"No way to meet the HCP constraints: the seat minimums (including "
            f"known cards) total {min_total} HCP, but the deck holds only 40.")
    if max_total < 40:
        raise ValueError(
            f"No way to meet the HCP constraints: the seat maximums allow only "
            f"{max_total} HCP in total, but all 40 HCP in the deck must be dealt.")


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

    known, hcp, suit_length, acceptors = _build_known_and_constraints(
        leader_letter, leader_cards, constraints)
    _check_hcp_feasibility(known, hcp)

    # --- Phase 1: generate deals ---
    # Exact sampler: uniform over all HCP-consistent deals (DP over honor
    # value classes), with suit/shape constraints applied by rejection. Falls
    # back to the legacy steered generator if shapes reject everything.
    rng = random.Random(seed) if seed is not None else random
    sampler = ExactDealSampler(known, hcp, suit_length, acceptors or None)
    if sampler.total == 0:
        raise ValueError(
            "No way to meet the HCP constraints: no arrangement of the unseen "
            "honor cards satisfies every seat's HCP range.")
    use_exact = True
    deals = []
    deal_layouts = []            # parallel to `deals`: {seat: 'S.H.D.C'} per deal
    attempts = 0
    max_attempts = num_simulations * max_attempts_factor
    while len(deals) < num_simulations and attempts < max_attempts:
        attempts += 1
        if use_exact:
            hands = sampler.sample(rng)
            if hands is None and not deals and attempts >= _EXACT_FALLBACK_ATTEMPTS:
                use_exact = False
        else:
            hands = generate_deal(known, hcp, suit_length, max_attempts=1000, rng=rng,
                                  acceptors=acceptors or None)
        if hands is None:
            continue
        layout = {p: _hand_list_to_str(hands[p]) for p in DG_PLAYERS}
        pbn = 'N:' + ' '.join(layout[p] for p in DG_PLAYERS)
        deal = Deal(pbn)
        deal.trump = denom
        deal.first = leader_player   # leader is on lead for trick 1
        deals.append(deal)
        deal_layouts.append(layout)

    if not deals:
        return {'num_simulations': 0, 'leads': [], 'best_mp': None,
                'best_imp': None, 'samples': {}}

    # --- Phase 2: batch DDS solve (multithreaded, in <=200-board chunks) ---
    board_results = _solve_all(deals)

    # --- Phase 3: collect leader-side scores per candidate lead ---
    # leader_scores[card] = [leader_score_per_deal, ...]
    leader_scores = defaultdict(list)
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
    }
