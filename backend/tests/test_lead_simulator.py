"""
Regression tests for engine.lead_simulator.

The simulator is randomised and leans on the endplay double-dummy solver, so we
keep deal counts tiny and assert structural invariants rather than exact numbers.
"""

import random

import pytest

from engine.lead import simulate_opening_lead
from engine.sampling import hand_to_cards, hand_list_to_str as _hand_list_to_str

# A fixed 13-card leader hand (PBN: spades.hearts.diamonds.clubs).
LEADER = "AK872.Q95.J98.Q4"


# --------------------------------------------------------------------------
# PBN <-> card-list helpers
# --------------------------------------------------------------------------
def test_hand_to_cards_parses_pbn():
    cards = hand_to_cards(LEADER)
    assert len(cards) == 13
    assert 'SA' in cards and 'SK' in cards
    assert 'HQ' in cards
    assert 'CQ' in cards and 'C4' in cards


def test_hand_to_cards_empty():
    assert hand_to_cards("") == []


def test_hand_list_to_str_sorts_high_to_low():
    cards = ['S2', 'SA', 'SK', 'H5']
    # spades sorted A,K,2; only hearts has the 5
    assert _hand_list_to_str(cards) == "AK2.5.."


def test_pbn_roundtrip():
    assert _hand_list_to_str(hand_to_cards(LEADER)) == LEADER


# --------------------------------------------------------------------------
# simulate_opening_lead
# --------------------------------------------------------------------------
def test_rejects_wrong_hand_size():
    with pytest.raises(ValueError):
        simulate_opening_lead("AKQ.123..", level=3, strain='N', declarer='S')


def test_result_shape_and_invariants():
    random.seed(2024)
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=5,
    )
    assert result['num_simulations'] == 5

    leads = result['leads']
    # One candidate lead per card in the leader's hand.
    assert len(leads) == 13

    cards = {lead['card'] for lead in leads}
    assert len(cards) == 13                      # all distinct

    for lead in leads:
        assert 0 <= lead['declarer_tricks'] <= 13
        assert 0 <= lead['defense_tricks'] <= 13
        # tricks split between the two sides
        assert lead['declarer_tricks'] + lead['defense_tricks'] == pytest.approx(13)
        assert 0.0 <= lead['defeat_rate'] <= 1.0
        assert 0.0 <= lead['matchpoints'] <= 100.0

    assert result['best_mp'] in cards
    assert result['best_imp'] in cards


def test_leads_sorted_best_first_by_imps():
    random.seed(5)
    result = simulate_opening_lead(
        leader_hand=LEADER, level=4, strain='S', declarer='S',
        num_simulations=5,
    )
    imps = [lead['imps'] for lead in result['leads']]
    assert imps == sorted(imps, reverse=True)


def test_constraints_are_honoured_in_simulation():
    # Force declarer (South) to a strong NT range; the sim must still produce deals.
    random.seed(9)
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        constraints={'hcp': {'S': (15, 17)}},
        num_simulations=3,
    )
    assert result['num_simulations'] == 3
    assert len(result['leads']) == 13


def test_seed_makes_results_reproducible():
    # Same inputs + same seed -> identical leads/metrics (what makes the app's
    # cached wrapper sound).
    kw = dict(leader_hand=LEADER, level=3, strain='N', declarer='S',
              num_simulations=20, seed=7)
    r1 = simulate_opening_lead(**kw)
    r2 = simulate_opening_lead(**kw)
    assert [l['card'] for l in r1['leads']] == [l['card'] for l in r2['leads']]
    for a, b in zip(r1['leads'], r2['leads']):
        assert a['imps'] == pytest.approx(b['imps'])
        assert a['matchpoints'] == pytest.approx(b['matchpoints'])


def test_dds_batching_crosses_chunk_boundary(monkeypatch):
    # Shrink the DDS batch size so a handful of deals span several chunks; the
    # result must be identical in shape to a single-batch run (guards the
    # MAXNOOFBOARDS chunking path against regressing to the slow fallback).
    import engine.dds_runtime as dds
    monkeypatch.setattr(dds, '_BOARD_BATCH', 2)
    random.seed(123)
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=5,
    )
    assert result['num_simulations'] == 5
    assert len(result['leads']) == 13


def test_shapes_constraint_runs_end_to_end():
    # The South 15-17 1NT shape disjunction (balanced / 5-card major / 6m) plus
    # an HCP range. The sim must produce deals and a full lead table.
    south_1nt = [
        {'S': (2, 4), 'H': (2, 4), 'D': (2, 5), 'C': (2, 5)},
        {'H': (5, 5), 'S': (2, 3), 'D': (2, 4), 'C': (2, 4)},
        {'S': (5, 5), 'H': (2, 3), 'D': (2, 4), 'C': (2, 4)},
        {'C': (6, 6), 'S': (2, 3), 'H': (2, 3), 'D': (2, 3)},
        {'D': (6, 6), 'S': (2, 3), 'H': (2, 3), 'C': (2, 3)},
    ]
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        constraints={'hcp': {'S': (15, 17)}, 'shapes': {'S': south_1nt}},
        num_simulations=5, seed=11,
    )
    assert result['num_simulations'] == 5
    assert len(result['leads']) == 13


def test_shapes_constraint_actually_filters_shapes():
    # Force South to a 6-card-club shape; verify the generated South hands obey
    # it. We reach into _build_known_and_constraints + generate_deal directly so
    # we can inspect the dealt hands (the public sim only returns leads).
    from engine.sampling import build_known_and_constraints as _build_known_and_constraints
    from engine.deal_generator import generate_deal

    six_clubs = [{'C': (6, 6), 'S': (2, 3), 'H': (2, 3), 'D': (2, 3)}]
    leader_cards = hand_to_cards(LEADER)
    # leader for declarer S is W; constrain S (declarer).
    known, hcp, suit_length, acceptors, _quality = _build_known_and_constraints(
        'W', leader_cards, {'shapes': {'S': six_clubs}})
    assert 'S' in acceptors

    rng = random.Random(3)
    seen = 0
    for _ in range(40):
        hands = generate_deal(known, hcp, suit_length, rng=rng,
                              acceptors=acceptors)
        if hands is None:
            continue
        seen += 1
        clubs = sum(1 for c in hands['S'] if c[0] == 'C')
        assert clubs == 6
    assert seen > 0


def test_samples_capped_and_consistent():
    # Every sample under a lead must be a deal that lead actually defeats, the
    # leader's hand must match LEADER, and no card exceeds max_samples.
    random.seed(31)
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=30, max_samples=4,
    )
    samples = result['samples']
    assert isinstance(samples, dict)
    contract_tricks = 6 + 3
    for card, deals in samples.items():
        assert len(deals) <= 4                       # capped
        for s in deals:
            assert s['declarer_tricks'] < contract_tricks   # truly defeated
            assert s['declarer_tricks'] + s['defense_tricks'] == 13
            # leader sits West (LHO of South); their hand is the fixed leader hand
            assert s['layout']['W'] == LEADER
            assert set(s['layout']) == {'N', 'E', 'S', 'W'}


def test_samples_present_for_defeating_leads():
    # A lead with a non-zero defeat rate must have at least one sample deal.
    random.seed(7)
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=25,
    )
    for lead in result['leads']:
        if lead['defeat_rate'] > 0:
            assert result['samples'].get(lead['card'])


# --------------------------------------------------------------------------
# per-deal matrix (result['deals'])
# --------------------------------------------------------------------------
def test_deals_matrix_shape_and_alignment():
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=5, seed=0,
    )
    deals = result['deals']
    # Same candidate leads as the aggregate table, one record per deal.
    assert set(deals['cards']) == {l['card'] for l in result['leads']}
    assert len(deals['records']) == result['num_simulations']
    for rec in deals['records']:
        assert len(rec['tricks']) == len(deals['cards'])
        assert len(rec['scores']) == len(deals['cards'])
        assert set(rec['layout']) == {'N', 'E', 'S', 'W'}
        # leader sits West (LHO of South); their hand is the fixed leader hand
        assert rec['layout']['W'] == LEADER


def test_deals_matrix_consistent_with_aggregates():
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=8, seed=1,
    )
    deals = result['deals']
    n = result['num_simulations']
    contract_tricks = 6 + 3
    for lead in result['leads']:
        k = deals['cards'].index(lead['card'])
        col = [rec['tricks'][k] for rec in deals['records']]
        assert sum(col) / n == pytest.approx(lead['declarer_tricks'])
        defeats = sum(1 for t in col if t < contract_tricks)
        assert defeats / n == pytest.approx(lead['defeat_rate'])


def test_deals_matrix_scores_match_scoring_oracle():
    from engine import scoring
    result = simulate_opening_lead(
        leader_hand=LEADER, level=4, strain='H', declarer='N',
        vul='both', penalty='doubled', num_simulations=3, seed=2,
    )
    deals = result['deals']
    for rec in deals['records']:
        for k in range(len(deals['cards'])):
            expected = -scoring.declarer_score(
                4, 'H', 'N', rec['tricks'][k], vul='both', penalty='doubled')
            assert rec['scores'][k] == expected


def test_deals_matrix_score_monotonic_in_tricks():
    # Within one deal, fewer declarer tricks must mean a strictly better
    # (higher) leader score.
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=5, seed=3,
    )
    for rec in result['deals']['records']:
        pairs = sorted(zip(rec['tricks'], rec['scores']))
        for (t1, s1), (t2, s2) in zip(pairs, pairs[1:]):
            if t1 < t2:
                assert s1 > s2
            else:
                assert s1 == s2


def test_samples_are_subset_of_deals_matrix():
    # Every sample deal must appear in the matrix with the same layout and the
    # same (contract-defeating) trick count for its lead.
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        num_simulations=20, seed=4, max_samples=5,
    )
    deals = result['deals']
    contract_tricks = 6 + 3
    for card, samples in result['samples'].items():
        k = deals['cards'].index(card)
        for s in samples:
            assert s['declarer_tricks'] < contract_tricks
            assert any(rec['layout'] == s['layout']
                       and rec['tricks'][k] == s['declarer_tricks']
                       for rec in deals['records'])


def test_impossible_hcp_minimums_raise():
    # Two seats each demanding 25+ HCP needs >=50; the deck holds 40, so the
    # feasibility shortcut raises before any generation is attempted.
    with pytest.raises(ValueError, match="No way to meet the HCP constraints"):
        simulate_opening_lead(
            leader_hand=LEADER, level=3, strain='N', declarer='S',
            constraints={'hcp': {'N': (25, 40), 'E': (25, 40)}},
            num_simulations=3,
        )


def test_leader_hcp_counts_toward_minimums():
    # LEADER holds 12 HCP; seat minimums of 15+15 push the total to 42 > 40.
    # (Each seat alone is satisfiable — only the sum is impossible.)
    with pytest.raises(ValueError, match="total 42 HCP"):
        simulate_opening_lead(
            leader_hand=LEADER, level=3, strain='N', declarer='S',
            constraints={'hcp': {'N': (15, 40), 'S': (15, 40)}},
            num_simulations=3,
        )


def test_impossible_hcp_maximums_raise():
    # LEADER holds 12 HCP; capping all other seats at 5 allows at most 27 of
    # the deck's 40 HCP to be dealt.
    with pytest.raises(ValueError, match="No way to meet the HCP constraints"):
        simulate_opening_lead(
            leader_hand=LEADER, level=3, strain='N', declarer='S',
            constraints={'hcp': {'N': (0, 5), 'E': (0, 5), 'S': (0, 5)}},
            num_simulations=3,
        )


def test_fixed_cards_over_seat_max_raise():
    # North is fixed with 7 HCP of cards but capped at 4.
    with pytest.raises(ValueError, match="No way to meet the HCP constraints"):
        simulate_opening_lead(
            leader_hand=LEADER, level=3, strain='N', declarer='S',
            constraints={'hcp': {'N': (0, 4)},
                         'fixed_cards': {'N': ['DA', 'CK']}},
            num_simulations=3,
        )


def test_tight_but_feasible_hcp_still_runs():
    # Minimums total exactly 40 (12 leader + 28 spread) — feasible, must not raise.
    result = simulate_opening_lead(
        leader_hand=LEADER, level=3, strain='N', declarer='S',
        constraints={'hcp': {'N': (10, 10), 'E': (8, 8), 'S': (10, 10)}},
        num_simulations=2, seed=0,
    )
    assert result['num_simulations'] > 0
