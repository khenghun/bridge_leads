"""HTTP contract for the play solver (`app_play.main:app`).

Same shape as `tests/test_api.py`: a TestClient, the real engine behind it, and
small deal counts so the suite stays fast. `double_dummy` is used wherever the
test is about plumbing rather than sampling — it is one solve per decision.
"""

import pytest
from fastapi.testclient import TestClient

from app_play import service
from app_play.main import app

client = TestClient(app)

# Board 17: 1N by W, N on lead, nine tricks recorded plus the lead to the tenth.
HANDS = {
    'N': '9872.K85.AJ542.5',
    'E': 'QJ6.A632.KQ.J976',
    'S': 'KT3.JT7.87.KQ843',
    'W': 'A54.Q94.T963.AT2',
}
PLAY = (
    'S9 SJ SK S5  ST S4 S2 SQ  C6 C4 CT C5  D3 D5 DQ D7  H2 HT HQ HK '
    'S8 S6 S3 SA  H4 H8 H3 H7  S7 C7 C3 C2  DA DK D8 D6  DJ'
).split()

BOARD = {'hands': HANDS, 'level': 1, 'strain': 'N', 'declarer': 'W'}


@pytest.fixture(autouse=True)
def _fresh_cache():
    service.clear_cache()
    yield
    service.clear_cache()


def analyze(**overrides):
    return client.post('/api/play/analyze', json={**BOARD, 'play': PLAY,
                                                  'method': 'double_dummy',
                                                  **overrides})


def position(**overrides):
    return client.post('/api/play/position', json={**BOARD, 'play': PLAY[:4],
                                                   'method': 'double_dummy',
                                                   **overrides})


# --- health ------------------------------------------------------------------

def test_health():
    r = client.get('/api/play/health')
    assert r.status_code == 200
    assert r.json() == {'status': 'ok'}


# --- analyze -----------------------------------------------------------------

def test_analyze_declarer():
    r = analyze(seat='W')
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['seat'] == 'W'
    assert body['role'] == 'declarer'
    assert body['visible'] == ['W', 'E']
    assert body['tricks_needed'] == 7
    assert body['method'] == 'double_dummy'
    assert len(body['decisions']) == 18          # W's nine cards plus dummy's nine
    assert {d['hand'] for d in body['decisions']} == {'W', 'E'}
    s = body['summary']
    assert s['decisions'] == len(body['decisions'])
    assert s['optimal'] + s['good'] + s['suboptimal'] == s['graded']


def test_analyze_defender_single_dummy():
    r = analyze(seat='N', method='single_dummy', num_deals=5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['role'] == 'defender'
    assert body['visible'] == ['N', 'E']
    assert body['num_deals'] == 5
    assert {d['hand'] for d in body['decisions']} == {'N'}
    graded = [d for d in body['decisions'] if not d['forced']]
    assert graded
    for d in graded:
        assert d['card'] in [o['card'] for o in d['options']]
        assert d['best_tricks'] == max(o['tricks'] for o in d['options'])
        assert d['status'] in ('optimal', 'good', 'suboptimal')


def test_analyze_forced_decisions_carry_no_options():
    body = analyze(seat='W').json()
    forced = [d for d in body['decisions'] if d['forced']]
    assert forced
    for d in forced:
        assert d['status'] == 'forced'
        assert d['options'] == []
        assert d['actual_tricks'] is None


def test_analyze_accepts_constraints_on_hidden_seats():
    r = analyze(seat='W', method='single_dummy', num_deals=5,
                play=PLAY[:4], constraints={'hcp': {'N': [8, 14]}})
    assert r.status_code == 200, r.text


def test_analyze_is_cached_and_deterministic():
    first = analyze(seat='N', method='single_dummy', num_deals=5).json()
    second = analyze(seat='N', method='single_dummy', num_deals=5).json()
    assert first == second


def test_analyze_with_no_play_yet():
    r = analyze(seat='N', play=[])
    assert r.status_code == 200
    assert r.json()['decisions'] == []


# --- position ----------------------------------------------------------------

def test_position_endpoint():
    r = position()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['to_play'] == 'S'                # S won trick 1 and leads trick 2
    assert body['role'] == 'defender'
    assert body['view'] == 'S'
    assert body['visible'] == ['S', 'E']
    assert body['trick'] == 2 and body['index'] == 4
    assert body['tricks_won'] == {'NS': 1, 'EW': 0}
    assert body['forced'] is False
    assert body['num_deals'] == 1                # double_dummy
    assert sorted(body['legal_cards']) == sorted(o['card'] for o in body['options'])
    tricks = [o['tricks'] for o in body['options']]
    assert tricks == sorted(tricks, reverse=True)


def test_position_at_the_opening_lead_hides_dummy():
    r = position(play=[])
    assert r.status_code == 200
    body = r.json()
    assert body['to_play'] == 'N' and body['visible'] == ['N']
    assert len(body['legal_cards']) == 13


def test_position_when_dummy_is_on_play_is_graded_for_declarer():
    r = position(play=PLAY[:8])                  # E won trick 2 and leads trick 3
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['to_play'] == 'E'                # dummy holds the cards...
    assert body['view'] == 'W'                   # ...but declarer chooses them
    assert body['role'] == 'declarer'
    assert body['visible'] == ['W', 'E']


def test_position_single_dummy():
    r = position(method='single_dummy', num_deals=5)
    assert r.status_code == 200, r.text
    assert r.json()['num_deals'] == 5


# --- 422s ---------------------------------------------------------------------

def test_malformed_play_is_422():
    r = analyze(seat='N', play=['S9', 'HK'])     # HK is North's; East is on turn
    assert r.status_code == 422
    assert 'play[1]' in r.text


def test_revoke_is_422():
    r = analyze(seat='N', play=['S9', 'HA'])     # East holds spades but pitched
    assert r.status_code == 422
    assert 'follow suit' in r.json()['detail']


def test_grading_dummy_is_422():
    r = analyze(seat='E')
    assert r.status_code == 422
    assert 'dummy' in r.json()['detail']


def test_constraint_on_a_visible_seat_is_422():
    r = analyze(seat='W', constraints={'hcp': {'E': [10, 12]}})
    assert r.status_code == 422
    assert 'visible' in r.json()['detail']


def test_constraint_on_own_seat_is_422():
    r = analyze(seat='N', method='single_dummy', num_deals=5,
                constraints={'suit_length': {'N': {'S': [4, 4]}}})
    assert r.status_code == 422


def test_duplicate_card_across_hands_is_422():
    bad = dict(HANDS, S='KT3.JT7.87.KQ842', N='9872.K85.AJ542.5')
    r = client.post('/api/play/analyze',
                    json={**BOARD, 'hands': bad, 'play': [], 'seat': 'N'})
    assert r.status_code == 422
    assert 'one hand' in r.text


def test_short_hand_is_422():
    bad = dict(HANDS, N='987.K85.AJ542.5')
    r = client.post('/api/play/analyze',
                    json={**BOARD, 'hands': bad, 'play': [], 'seat': 'S'})
    assert r.status_code == 422


def test_bad_card_in_play_is_422():
    r = analyze(seat='N', play=['XX'])
    assert r.status_code == 422


def test_bad_seat_is_422():
    r = analyze(seat='Z')
    assert r.status_code == 422


def test_bad_method_is_422():
    r = analyze(seat='N', method='triple_dummy')
    assert r.status_code == 422


def test_num_deals_out_of_range_is_422():
    assert analyze(seat='N', method='single_dummy', num_deals=2).status_code == 422
    assert analyze(seat='N', method='single_dummy', num_deals=500).status_code == 422


def test_position_on_a_complete_play_is_422():
    play = list(PLAY)
    from engine.play import state
    pos = state.replay(HANDS, 'N', 'W', play)
    while not pos.complete:
        play.append(state.legal_cards(pos)[-1])
        pos = state.replay(HANDS, 'N', 'W', play)
    r = position(play=play)
    assert r.status_code == 422
    assert 'complete' in r.json()['detail']


# --- query log ----------------------------------------------------------------

def test_simulations_are_logged_before_they_run(tmp_path, monkeypatch):
    from app.common import querylog
    db = tmp_path / 'queries.db'
    monkeypatch.setattr(querylog, 'QUERY_LOG', querylog.QueryLog(str(db)))
    analyze(seat='E')                     # a 422 — still worth logging
    analyze(seat='W')
    import sqlite3
    rows = sqlite3.connect(db).execute(
        'SELECT tool FROM queries').fetchall()
    assert [r[0] for r in rows] == ['play', 'play']


def test_validate_shape_is_served_for_the_shared_constraints_editor():
    """The shared ConstraintsEditor posts to /api/validate/shape as it types;
    the play app must answer at the same path the lead app does."""
    r = client.post('/api/validate/shape', json={'text': '(5s,2-3h,2-4d,2-4c)'})
    assert r.status_code == 200, r.text
    assert r.json()['ok'] is True
    r = client.post('/api/validate/shape', json={'text': '((('})
    assert r.status_code == 422


# --- v1.2: costs in the payload ---------------------------------------------

def test_analyze_response_carries_scores_and_imps():
    r = analyze(seat='W')
    assert r.status_code == 200
    body = r.json()
    s = body['summary']
    assert s['total_imp_loss'] >= 0 and s['total_score_loss'] >= 0
    graded = [d for d in body['decisions'] if not d['forced']]
    assert graded
    for d in graded:
        assert d['imp_diff'] <= 0
        assert d['best_score'] is not None
        assert all('score' in o and 'imps' in o for o in d['options'])
        assert d['options'][0]['imps'] == 0.0
    forced = [d for d in body['decisions'] if d['forced']]
    assert all(d['imp_diff'] is None and d['score_diff'] is None for d in forced)


def test_vulnerability_reaches_the_grader_and_the_cache_key():
    """Same position, different vulnerability: same tricks, different prices —
    and two distinct cache entries, not one served twice."""
    # 1NT making scores the same at any vulnerability, so use a position that
    # ends in undertricks: the constructed 3NT where West's hearts beat it.
    wide = {'N': 'T98.765.JT9.T987', 'E': '765.432.8765.654',
            'S': 'AKQJ.98.AKQ.AKQJ', 'W': '432.AKQJT.432.32'}
    a = position(hands=wide, level=3, declarer='S', play=[], vul='none').json()
    b = position(hands=wide, level=3, declarer='S', play=[], vul='both').json()
    ta = [o['tricks'] for o in a['options']]
    tb = [o['tricks'] for o in b['options']]
    assert ta == tb
    sa = [o['score'] for o in a['options']]
    sb = [o['score'] for o in b['options']]
    assert sa != sb


# --- expert opponents (v1.3) and chunked decisions ---------------------------

def test_expert_settings_are_ignored_when_the_toggle_is_off():
    r = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                expert={'strict': True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['expert'] is None
    assert all(d['expert'] is None for d in body['decisions'])


def test_expert_toggle_fills_defaults_and_reports_counts():
    r = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                expert_opponents=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['expert'] == {'inner_ratio': 0.5, 'tolerance': 0.1, 'confidence': 2.0,
                              'budget': 20, 'strict': False, 'depth': 1}
    graded = [d for d in body['decisions'] if not d['forced']]
    assert graded
    for d in graded:
        e = d['expert']
        assert e['consistent'] == 5 and e['sampled'] >= 5
        assert e['inference'] in ('filtered', 'trivial')
        assert e['threshold'] > 0.1


def test_expert_settings_change_the_cache_key():
    a = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                expert_opponents=True).json()
    b = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                expert_opponents=True, expert={'strict': True}).json()
    c = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8]).json()
    assert b['expert']['strict'] is True and a['expert']['strict'] is False
    assert c['expert'] is None
    # strict traces nothing; the default traces every examined layout
    assert all(d['expert']['traced'] == 0 for d in b['decisions'] if d['expert'])
    assert any(d['expert']['traced'] > 0 for d in a['decisions'] if d['expert'])


def test_expert_constraints_cover_all_four_seats():
    """Constraints on the graded seat's own hand are rejected in `constraints`
    but welcome in `expert_constraints` — they describe what the opponents
    knew from the auction."""
    r = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                constraints={'hcp': {'N': [8, 14]}})
    assert r.status_code == 422
    r = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                expert_opponents=True,
                expert_constraints={'hcp': {'N': [8, 14], 'W': [15, 17]}})
    assert r.status_code == 200, r.text


def test_expert_option_bounds_are_validated():
    for bad in ({'tolerance': 2}, {'confidence': 0.5}, {'budget': 100},
                {'depth': 3}, {'inner_ratio': 0}):
        r = analyze(seat='N', method='single_dummy', num_deals=5, play=PLAY[:8],
                    expert_opponents=True, expert=bad)
        assert r.status_code == 422, bad


def test_decisions_chunk_returns_only_those_indices():
    r = analyze(seat='W', decisions=[1, 3, 5])
    assert r.status_code == 200, r.text
    body = r.json()
    assert [d['index'] for d in body['decisions']] == [1, 3, 5]
    assert body['summary']['decisions'] == 3


def test_decisions_chunks_are_cached_separately():
    a = analyze(seat='W', decisions=[1, 3]).json()
    b = analyze(seat='W', decisions=[5]).json()
    whole = analyze(seat='W').json()
    merged = {d['index']: d for d in a['decisions'] + b['decisions']}
    for d in whole['decisions']:
        if d['index'] in merged:
            assert merged[d['index']] == d


def test_position_endpoint_takes_the_expert_toggle():
    r = position(method='single_dummy', num_deals=5, play=PLAY[:8],
                 expert_opponents=True)
    assert r.status_code == 200, r.text
    assert r.json()['expert']['consistent'] == 5
