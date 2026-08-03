"""API tests for POST /api/contract/simulate (FastAPI TestClient)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.contract import service

client = TestClient(app)

HAND = 'AKQ82.AQ5.J98.Q4'


@pytest.fixture(autouse=True)
def clean_cache():
    service._cache.clear()
    yield
    service._cache.clear()


def _post(**overrides):
    body = {'hand': HAND, 'seat': 'S', 'vul': 'none', 'num_deals': 50}
    body.update(overrides)
    return client.post('/api/contract/simulate', json=body)


def test_simulate_happy_path():
    res = _post(constraints={'hcp': {'N': [10, 14]},
                             'shapes': {'N': '(2-4s, 2-4h, 2-5d, 2-5c)'}})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data['num_deals'] == 50
    assert data['seat'] == 'S' and data['partner'] == 'N'
    assert len(data['candidates']) == 40
    assert data['default_benchmark'] in {c['key'] for c in data['candidates']}
    assert len(data['deals']['records']) == 50
    assert data['deals']['candidates'] == [c['key'] for c in data['candidates']]
    assert all(rec['layout']['S'] == HAND for rec in data['deals']['records'])


def test_strain_subset_is_honoured():
    res = _post(strains=['N', 'S'])
    assert res.status_code == 200, res.text
    data = res.json()
    assert {c['strain'] for c in data['candidates']} == {'N', 'S'}
    assert data['opponents']['par_competitive_rate'] is None


def test_identical_requests_are_cached():
    first = _post()
    second = _post()
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


def test_bad_hand_is_422():
    res = _post(hand='AKQ8.AQ5.J98.Q4')          # 12 cards
    assert res.status_code == 422
    assert '13 cards' in res.json()['detail']


def test_impossible_constraints_are_422():
    res = _post(constraints={'hcp': {'N': [30, 40]}})
    assert res.status_code == 422
    assert 'HCP' in res.json()['detail']


def test_bad_shape_text_is_422():
    res = _post(constraints={'shapes': {'N': '5=3=3=oops'}})
    assert res.status_code == 422
    assert 'shape constraint' in res.json()['detail']


def test_validation_rejects_out_of_range_deals_and_seats():
    assert _post(num_deals=10).status_code == 422        # below the 50 floor
    assert _post(num_deals=5000).status_code == 422
    assert _post(seat='X').status_code == 422


def test_two_quality_constraints_are_422():
    res = _post(constraints={'quality': {'N': {'S': 'good'}, 'E': {'H': 'good'}}})
    assert res.status_code == 422
    assert 'one suit-quality' in res.json()['detail']


def test_lead_endpoint_still_works_alongside():
    """Both routers are mounted; the lead tool's path is unchanged."""
    res = client.post('/api/simulate', json={
        'leader_hand': 'T.KT932.Q2.T9843', 'level': 3, 'strain': 'N',
        'declarer': 'S', 'num_simulations': 100,
    })
    assert res.status_code == 200, res.text
    assert res.json()['num_simulations'] == 100
