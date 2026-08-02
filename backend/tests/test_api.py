"""API-level tests (FastAPI TestClient). Small `num_simulations` for speed;
seed is fixed at 0 inside the service, so results are deterministic."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# A fixed leader hand used across simulate tests.
LEADER = 'T.KT932.Q2.T9843'


def test_health():
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.json() == {'status': 'ok'}


def test_auctions_lists_presets():
    r = client.get('/api/auctions')
    assert r.status_code == 200
    names = [a['name'] for a in r.json()['auctions']]
    assert any('1NT' in n for n in names)
    assert any('2NT' in n for n in names)
    first = r.json()['auctions'][0]
    assert set(first) == {'name', 'contract', 'declarer', 'hcp', 'shapes_text', 'note'}


def test_validate_shape_ok():
    r = client.post('/api/validate/shape', json={'text': '(5s,2-3h,2-4d,2-4c) or (4h,3s,3d,3c)'})
    assert r.status_code == 200
    body = r.json()
    assert body['ok'] and body['terms_count'] == 2
    assert body['warnings'] == []


def test_validate_shape_rejects_garbage():
    r = client.post('/api/validate/shape', json={'text': 'not a shape'})
    assert r.status_code == 422


def test_validate_shape_feasibility_warning():
    # Minimum lengths total > 13 -> impossible term (warning, not an error).
    r = client.post('/api/validate/shape', json={'text': '(5s,5h,5d,5c)'})
    assert r.status_code == 200
    assert r.json()['warnings']


def test_simulate_basic():
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
    })
    assert r.status_code == 200
    body = r.json()
    assert body['num_simulations'] > 0
    assert body['leads']                       # non-empty, ranked
    assert body['best_mp'] and body['best_imp']
    assert body['leader'] == 'W'               # LHO of South
    assert body['meta'] == {'level': 3, 'strain': 'N', 'declarer': 'S'}
    # Every candidate lead comes from the leader's actual holding (13 cards).
    assert len(body['leads']) <= 13
    # Leads are sorted best-first by IMPs.
    imps = [ld['imps'] for ld in body['leads']]
    assert imps == sorted(imps, reverse=True)
    # Per-deal matrix: one record per deal, columns aligned to `cards`.
    deals = body['deals']
    assert set(deals['cards']) == {ld['card'] for ld in body['leads']}
    assert len(deals['records']) == body['num_simulations']
    first = deals['records'][0]
    assert set(first) == {'layout', 'tricks', 'scores'}
    assert len(first['tricks']) == len(deals['cards'])
    assert len(first['scores']) == len(deals['cards'])


def test_simulate_with_shape_constraint():
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {
            'hcp': {'S': [15, 17]},
            'shapes': {'S': '(2-4s,2-4h,2-5d,2-5c) or (5h,2-3s,2-4d,2-4c)'},
        },
    })
    assert r.status_code == 200
    assert r.json()['num_simulations'] > 0


def test_simulate_with_suit_quality():
    """The weak-two shape this feature exists for: partner shows 6 good hearts."""
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {
            'hcp': {'N': [5, 10]},
            'suit_length': {'N': {'H': [6, 6]}},
            'quality': {'N': {'H': 'good'}},
        },
    })
    assert r.status_code == 200
    assert r.json()['num_simulations'] == 100


def test_simulate_rejects_two_quality_constraints():
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {'quality': {'N': {'H': 'good'}, 'E': {'S': 'good'}}},
    })
    assert r.status_code == 422
    assert 'Only one suit-quality' in r.json()['detail']


def test_simulate_rejects_bad_quality_value():
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {'quality': {'N': {'H': 'solid'}}},
    })
    assert r.status_code == 422


def test_simulate_rejects_unreachable_quality():
    # The leader holds AK of spades and N is capped at 2 HCP, so N can never
    # hold a good spade suit -> a clear 422 rather than an empty result.
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {'hcp': {'N': [0, 2]}, 'quality': {'N': {'S': 'good'}}},
    })
    assert r.status_code == 422
    assert 'good S suit' in r.json()['detail']


def test_simulate_deterministic():
    payload = {
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
    }
    a = client.post('/api/simulate', json=payload).json()
    b = client.post('/api/simulate', json=payload).json()
    assert a['best_imp'] == b['best_imp']
    assert [ld['imps'] for ld in a['leads']] == [ld['imps'] for ld in b['leads']]


def test_simulate_rejects_short_hand():
    r = client.post('/api/simulate', json={
        'leader_hand': 'T.KT932.Q2.T984',       # 12 cards
        'level': 3, 'strain': 'N', 'declarer': 'S', 'num_simulations': 100,
    })
    assert r.status_code == 422


def test_simulate_rejects_impossible_hcp():
    # LEADER holds 5 HCP; N>=20 and S>=20 pushes the minimum total past the
    # deck's 40 HCP -> 422 with a human-readable message, not a hang.
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {'hcp': {'N': [20, 40], 'S': [20, 40]}},
    })
    assert r.status_code == 422
    assert 'No way to meet the HCP constraints' in r.json()['detail']


def test_simulate_rejects_bad_shape():
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {'shapes': {'S': 'garbage'}},
    })
    assert r.status_code == 422


def test_simulate_rejects_bad_contract_level():
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 8, 'strain': 'N', 'declarer': 'S',
    })
    assert r.status_code == 422       # pydantic: level <= 7
