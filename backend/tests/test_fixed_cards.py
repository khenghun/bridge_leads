"""The `fixed_cards` constraint: named cards pinned into an unseen hand.

Covers the three layers it passes through — request normalisation
(`app.common.constraints`), hand-aware validation (`engine.sampling`), and the
end-to-end effect on both simulators, which is that every sampled deal really
does contain the pinned cards in the named seat.
"""

import pytest
from fastapi.testclient import TestClient

from app.common.constraints import SimulationError, build_constraints, build_fixed_cards
from app.contract import service as contract_service
from app.lead import service as lead_service
from app.main import app
from engine.contract import simulate_contracts
from engine.lead import simulate_opening_lead
from engine.sampling import (
    build_known_and_constraints, check_length_feasibility, hand_to_cards,
    resolve_fixed_cards,
)

client = TestClient(app)

LEADER = 'T.KT932.Q2.T9843'          # declarer S -> leader is W
OWN = 'AKQ82.AQ5.J98.Q4'


@pytest.fixture(autouse=True)
def clean_caches():
    lead_service._cache.clear()
    contract_service._cache.clear()
    yield
    lead_service._cache.clear()
    contract_service._cache.clear()


def suit_of(pbn_hand, suit):
    """The ranks a PBN hand ('S.H.D.C') holds in one suit."""
    return pbn_hand.split('.')['SHDC'.index(suit)]


# --- request normalisation -------------------------------------------------

def test_build_fixed_cards_normalises():
    got = build_fixed_cards({'N': ['ha', ' hk ', 'd10']})
    assert got == {'N': ['HA', 'HK', 'DT']}


def test_build_fixed_cards_drops_empty_seats():
    assert build_fixed_cards({'N': []}) == {}
    assert build_fixed_cards(None) == {}


def test_build_constraints_passes_fixed_cards_through():
    out = build_constraints({'fixed_cards': {'E': ['HA', 'HK']}})
    assert out['fixed_cards'] == {'E': ['HA', 'HK']}


def test_build_constraints_omits_empty_fixed_cards():
    assert 'fixed_cards' not in build_constraints({'hcp': {'N': [10, 14]}})


@pytest.mark.parametrize('spec, msg', [
    ({'N': ['XA']}, 'not a card'),
    ({'N': ['H1']}, 'not a card'),
    ({'N': ['H']}, 'not a card'),
    ({'N': ['HA', 'HA']}, 'twice'),
    ({'N': ['HA'], 'E': ['HA']}, 'only be in one hand'),
    ({'N': [f'{s}{r}' for s in 'SHDC' for r in 'AKQJ']}, 'a hand holds 13'),
])
def test_build_fixed_cards_rejects(spec, msg):
    with pytest.raises(SimulationError, match=msg):
        build_fixed_cards(spec)


# --- hand-aware validation -------------------------------------------------

def test_resolve_fixed_cards_returns_normalised_dict():
    got = resolve_fixed_cards({'N': ['HA', 'HQ']}, 'W', hand_to_cards(LEADER))
    assert got == {'N': ['HA', 'HQ']}


def test_resolve_fixed_cards_rejects_own_seat():
    with pytest.raises(ValueError, match='not your own'):
        resolve_fixed_cards({'W': ['HA']}, 'W', hand_to_cards(LEADER))


def test_resolve_fixed_cards_rejects_unknown_seat():
    with pytest.raises(ValueError, match='unknown seat'):
        resolve_fixed_cards({'X': ['HA']}, 'W', hand_to_cards(LEADER))


def test_resolve_fixed_cards_rejects_card_we_hold():
    # The leader holds HK, so no other seat can.
    with pytest.raises(ValueError, match='already in your own hand'):
        resolve_fixed_cards({'N': ['HK']}, 'W', hand_to_cards(LEADER))


def test_resolve_fixed_cards_rejects_card_claimed_twice():
    with pytest.raises(ValueError, match='only be in one hand'):
        resolve_fixed_cards({'N': ['HA'], 'E': ['HA']}, 'W', hand_to_cards(LEADER))


def test_pinned_cards_join_the_known_hands():
    known, *_ = build_known_and_constraints(
        'W', hand_to_cards(LEADER), {'fixed_cards': {'N': ['HA', 'HQ']}})
    assert set(known['N']) == {'HA', 'HQ'}
    assert len(known['W']) == 13


# --- feasibility pre-checks ------------------------------------------------

def test_length_check_rejects_more_pinned_cards_than_the_suit_maximum():
    known = {'N': ['H2', 'H3', 'H4']}
    with pytest.raises(ValueError, match='H maximum is 2'):
        check_length_feasibility(known, {'N': {'H': (0, 2)}})


def test_length_check_rejects_minimums_that_no_longer_fit():
    # 12 pinned spades leave one free slot, but the minimums ask for two cards.
    known = {'N': ['S' + r for r in 'AKQJT98765432'[:12]]}
    with pytest.raises(ValueError, match='room for only 1'):
        check_length_feasibility(known, {'N': {'H': (1, 13), 'D': (1, 13)}})


def test_length_check_passes_when_the_cards_fit():
    check_length_feasibility({'N': ['HA', 'HK']}, {'N': {'H': (5, 6)}})


# --- end to end: the deals really contain the cards ------------------------

def test_lead_simulator_pins_the_cards_into_every_deal():
    res = simulate_opening_lead(
        LEADER, 3, 'N', 'S', constraints={'fixed_cards': {'N': ['HA', 'HQ']}},
        num_simulations=40, seed=0)
    assert res['num_simulations'] == 40
    for record in res['deals']['records']:
        hearts = suit_of(record['layout']['N'], 'H')
        assert 'A' in hearts and 'Q' in hearts


def test_contract_simulator_pins_the_cards_into_every_deal():
    res = simulate_contracts(
        OWN, seat='S', constraints={'fixed_cards': {'N': ['HK', 'DA', 'DK']}},
        num_deals=20, seed=0)
    assert res['num_deals'] == 20
    for record in res['deals']['records']:
        assert 'K' in suit_of(record['layout']['N'], 'H')
        assert set('AK') <= set(suit_of(record['layout']['N'], 'D'))


def test_pinned_cards_compose_with_hcp_and_quality():
    """Pinned honours are counted by the HCP bounds and by the quality DP, not
    layered on afterwards — so a seat given HA+HK has at least those 7 HCP and
    a 'good' heart suit comes for free."""
    res = simulate_opening_lead(
        LEADER, 3, 'N', 'S', num_simulations=30, seed=0,
        constraints={'fixed_cards': {'N': ['HA', 'HQ']},
                     'hcp': {'N': (12, 15)},
                     'quality': {'N': {'H': 'good'}}})
    assert res['num_simulations'] == 30
    hcp_values = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}
    for record in res['deals']['records']:
        hand = record['layout']['N']
        points = sum(hcp_values.get(r, 0) for r in hand.replace('.', ''))
        assert 12 <= points <= 15
        assert set('AQ') <= set(suit_of(hand, 'H'))


def test_pinned_cards_contradicting_the_hcp_maximum_raise():
    with pytest.raises(ValueError, match='above the 5 HCP maximum'):
        simulate_opening_lead(
            LEADER, 3, 'N', 'S', num_simulations=5, seed=0,
            constraints={'fixed_cards': {'N': ['HA', 'HQ']}, 'hcp': {'N': (0, 5)}})


def test_pinned_cards_contradicting_the_quality_grade_raise():
    with pytest.raises(ValueError, match='No way to meet the constraints'):
        simulate_opening_lead(
            LEADER, 3, 'N', 'S', num_simulations=5, seed=0,
            constraints={'fixed_cards': {'N': ['HA', 'HQ']},
                         'quality': {'N': {'H': 'poor'}}})


# --- API -------------------------------------------------------------------

def _lead(constraints):
    return client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'vul': 'none', 'penalty': 'none', 'num_simulations': 100,
        'constraints': constraints,
    })


def _contract(constraints):
    return client.post('/api/contract/simulate', json={
        'hand': OWN, 'seat': 'S', 'vul': 'none', 'num_deals': 50,
        'constraints': constraints,
    })


def test_lead_api_accepts_fixed_cards():
    r = _lead({'fixed_cards': {'N': ['HA', 'HQ']}})
    assert r.status_code == 200, r.text
    for record in r.json()['deals']['records']:
        assert set('AQ') <= set(suit_of(record['layout']['N'], 'H'))


def test_contract_api_accepts_fixed_cards():
    r = _contract({'fixed_cards': {'N': ['SJ', 'ST']}})
    assert r.status_code == 200, r.text
    for record in r.json()['deals']['records']:
        assert set('JT') <= set(suit_of(record['layout']['N'], 'S'))


@pytest.mark.parametrize('constraints', [
    {'fixed_cards': {'N': ['HK']}},                     # leader already holds HK
    {'fixed_cards': {'W': ['C2']}},                     # W is the leader's own seat
    {'fixed_cards': {'N': ['HA'], 'E': ['HA']}},        # same card twice
    {'fixed_cards': {'N': ['ZZ']}},                     # not a card (Pydantic)
])
def test_lead_api_rejects_bad_fixed_cards(constraints):
    assert _lead(constraints).status_code == 422


def test_contract_api_rejects_card_from_our_own_hand():
    r = _contract({'fixed_cards': {'N': ['SA']}})       # our hand has SA
    assert r.status_code == 422
    assert 'already in your own hand' in r.json()['detail']


def test_fixed_cards_are_part_of_the_cache_key():
    """Two runs differing only in the pinned cards must not share a result."""
    a = _lead({'fixed_cards': {'N': ['HA']}}).json()
    b = _lead({'fixed_cards': {'E': ['HA']}}).json()
    assert a['deals']['records'][0]['layout'] != b['deals']['records'][0]['layout']
