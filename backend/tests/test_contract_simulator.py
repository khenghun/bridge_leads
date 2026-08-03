"""
Regression tests for engine.contract.simulator.

The simulator is randomised and leans on the endplay double-dummy solver, so we
keep deal counts tiny and assert structural invariants, plus two things that
would silently corrupt every ranking if they broke:

  1. the DD **table** is a new trick oracle for this project — cross-check it
     against `solve_board`, the oracle the lead simulator already trusts;
  2. we DECLARE here, so a made game must score +620, not -620 (the lead
     simulator's perspective is the opposite one).
"""

import pytest
from endplay.types import Deal, Denom, Player
from endplay.dds import solve_board

from engine import scoring
from engine.contract import simulate_contracts
from engine.contract.simulator import STRAIN_DENOM, LETTER_PLAYER, partner_of
from engine.deal_generator import PLAYERS, calculate_hcp
from engine.sampling import hand_to_cards

# A strong balanced South hand: 3NT/4♠ territory opposite a normal partner.
OUR_HAND = "AKQ82.AQ5.J98.Q4"


def _sim(**kwargs):
    kwargs.setdefault('seat', 'S')
    kwargs.setdefault('num_deals', 12)
    kwargs.setdefault('seed', 0)
    return simulate_contracts(OUR_HAND, **kwargs)


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------
def test_returns_every_candidate_for_both_declarers():
    r = _sim()
    assert r['num_deals'] == 12
    assert r['seat'] == 'S' and r['partner'] == 'N'
    assert len(r['candidates']) == 40
    assert {c['declarer'] for c in r['candidates']} == {'N', 'S'}


def test_deal_matrix_is_aligned():
    r = _sim()
    keys = r['deals']['candidates']
    assert keys == [c['key'] for c in r['candidates']]
    assert len(r['deals']['records']) == r['num_deals']
    for rec in r['deals']['records']:
        assert len(rec['tricks']) == len(keys)
        assert len(rec['scores']) == len(keys)
        assert set(rec['layout']) == set(PLAYERS)


def test_our_hand_is_fixed_in_every_deal():
    r = _sim()
    for rec in r['deals']['records']:
        assert rec['layout']['S'] == OUR_HAND


def test_is_deterministic_under_a_seed():
    a, b = _sim(), _sim()
    assert a['candidates'] == b['candidates']
    assert a['deals'] == b['deals']
    assert a['default_benchmark'] == b['default_benchmark']


# --------------------------------------------------------------------------
# the numbers
# --------------------------------------------------------------------------
def test_scores_are_from_our_side_perspective():
    """We declare: a made contract scores positive for us."""
    r = _sim(vul='none')
    keys = r['deals']['candidates']
    by_key = {c['key']: c for c in r['candidates']}
    for rec in r['deals']['records']:
        for i, key in enumerate(keys):
            c = by_key[key]
            expected = scoring.declarer_score(
                c['level'], c['strain'], c['declarer'], rec['tricks'][i], vul='none')
            assert rec['scores'][i] == expected
            if rec['tricks'][i] >= c['tricks_needed']:
                assert rec['scores'][i] > 0


def test_game_bonus_shows_up_at_the_game_level():
    """4♠ making exactly, non-vul = 420; the ♠ partscore on the same tricks = 170."""
    r = _sim(vul='none')
    keys = r['deals']['candidates']
    game = keys.index('4S-S')
    part = keys.index('1S-S')
    for rec in r['deals']['records']:
        if rec['tricks'][game] == 10:
            assert rec['scores'][game] == 420
            assert rec['scores'][part] == 170
            break
    else:
        pytest.skip("no deal in this sample took exactly 10 spade tricks")


def test_dd_table_agrees_with_solve_board():
    """Cross-check the table oracle against the per-board solver: with best
    defense, declarer takes 13 - (best defensive lead's trick count)."""
    r = _sim(num_deals=3)
    keys = r['deals']['candidates']
    idx = keys.index('4S-S')
    for rec in r['deals']['records']:
        deal = Deal('N:' + ' '.join(rec['layout'][p] for p in PLAYERS))
        deal.trump = STRAIN_DENOM['S']
        deal.first = LETTER_PLAYER['W']          # LHO of declarer South leads
        board = solve_board(deal)
        declarer_tricks = 13 - max(t for _card, t in board)
        assert rec['tricks'][idx] == declarer_tricks


def test_make_rate_and_mean_tricks_match_the_matrix():
    r = _sim()
    keys = r['deals']['candidates']
    n = r['num_deals']
    for c in r['candidates']:
        col = [rec['tricks'][keys.index(c['key'])] for rec in r['deals']['records']]
        assert c['make_rate'] == pytest.approx(
            sum(1 for t in col if t >= c['tricks_needed']) / n)
        assert c['mean_tricks'] == pytest.approx(sum(col) / n)


def test_default_benchmark_is_the_highest_ev_contract():
    r = _sim()
    by_key = {c['key']: c for c in r['candidates']}
    bench = by_key[r['default_benchmark']]
    assert bench['mean_score'] == max(c['mean_score'] for c in r['candidates'])


def test_a_strong_pair_lands_on_game():
    """21 HCP opposite a balanced 10-14: 3NT should be the benchmark and make
    on the large majority of deals."""
    r = _sim(num_deals=25, constraints={
        'hcp': {'N': (10, 14)},
        'shapes': {'N': [{'S': (2, 4), 'H': (2, 4), 'D': (2, 5), 'C': (2, 5)}]},
    })
    by_key = {c['key']: c for c in r['candidates']}
    assert by_key[r['default_benchmark']]['kind'] == 'game'
    assert by_key['3N-S']['make_rate'] > 0.7


# --------------------------------------------------------------------------
# constraints, strains, errors
# --------------------------------------------------------------------------
def test_partner_constraints_actually_bind():
    r = _sim(num_deals=10, constraints={
        'hcp': {'N': (10, 12)},
        'suit_length': {'N': {'H': (5, 6)}},
    })
    for rec in r['deals']['records']:
        north = hand_to_cards(rec['layout']['N'])
        assert 10 <= calculate_hcp(north) <= 12
        assert 5 <= len(rec['layout']['N'].split('.')[1]) <= 6


def test_excluding_strains_drops_them_and_par():
    r = _sim(strains=['S', 'N'])
    assert {c['strain'] for c in r['candidates']} == {'S', 'N'}
    assert len(r['candidates']) == 16
    # par needs a complete DD table, so it is withheld rather than wrong
    assert r['opponents']['par_competitive_rate'] is None
    assert 0.0 <= r['opponents']['opps_game_rate'] <= 1.0


def test_full_run_reports_par_stats():
    r = _sim()
    opps = r['opponents']
    assert 0.0 <= opps['opps_game_rate'] <= 1.0
    assert 0.0 <= opps['par_competitive_rate'] <= 1.0


def test_seat_delta_is_antisymmetric():
    r = _sim()
    by_key = {c['key']: c for c in r['candidates']}
    for c in r['candidates']:
        other = partner_of(c['declarer'])
        mirror = by_key[f"{c['level']}{c['strain']}-{other}"]
        assert c['seat_delta'] == pytest.approx(-mirror['seat_delta'])


def test_rejects_a_bad_hand_and_seat():
    with pytest.raises(ValueError, match='13 cards'):
        simulate_contracts('AKQ.AQ5.J98.Q4', seat='S', num_deals=2, seed=0)
    with pytest.raises(ValueError, match='unknown seat'):
        simulate_contracts(OUR_HAND, seat='X', num_deals=2, seed=0)


def test_impossible_constraints_raise():
    # Partner cannot hold 30 HCP when we already hold 21 of the deck's 40.
    with pytest.raises(ValueError, match='HCP'):
        _sim(constraints={'hcp': {'N': (30, 40)}})
