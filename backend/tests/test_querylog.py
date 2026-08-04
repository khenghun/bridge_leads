"""The query log: timestamp + tool + request body, one row per simulation.

The important properties are that it is **off by default** (so dev runs and
this test suite write nothing) and that it can **never break a request** — a
broken log should cost you the log, not the app.
"""

import json
import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient

from app.common.querylog import QueryLog
from app.common import querylog as querylog_module
from app.contract import service as contract_service
from app.lead import service as lead_service
from app.main import app

client = TestClient(app)

LEADER = 'T.KT932.Q2.T9843'
OWN = 'AKQ82.AQ5.J98.Q4'


@pytest.fixture
def logdb(tmp_path, monkeypatch):
    """Point the app's singleton at a throwaway database for one test."""
    path = tmp_path / 'queries.db'
    monkeypatch.setattr(querylog_module, 'QUERY_LOG', QueryLog(str(path)))
    lead_service._cache.clear()
    contract_service._cache.clear()
    yield path
    lead_service._cache.clear()
    contract_service._cache.clear()


def rows(path):
    with sqlite3.connect(str(path)) as conn:
        return conn.execute('SELECT ts, tool, payload FROM queries ORDER BY id').fetchall()


# --- configuration ---------------------------------------------------------

def test_disabled_without_a_path(tmp_path):
    """No BRIDGE_QUERY_LOG means no file and no writes."""
    qlog = QueryLog(None)
    assert not qlog.enabled
    qlog.record('lead', {'a': 1})            # must not raise
    assert list(tmp_path.iterdir()) == []


def test_the_apps_default_singleton_is_off_in_tests():
    """The suite must not be writing to a real log as a side effect."""
    assert not querylog_module.QUERY_LOG.enabled


def test_creates_the_file_and_its_parent_directory(tmp_path):
    path = tmp_path / 'nested' / 'dir' / 'queries.db'
    qlog = QueryLog(str(path))
    assert qlog.enabled and path.exists()


def test_reopening_an_existing_log_appends(tmp_path):
    path = tmp_path / 'queries.db'
    QueryLog(str(path)).record('lead', {'n': 1})
    QueryLog(str(path)).record('contract', {'n': 2})
    assert [r[1] for r in rows(path)] == ['lead', 'contract']


# --- writing ---------------------------------------------------------------

def test_records_timestamp_tool_and_payload(tmp_path):
    path = tmp_path / 'queries.db'
    QueryLog(str(path)).record('lead', {'leader_hand': LEADER, 'level': 3})
    (ts, tool, payload), = rows(path)
    assert tool == 'lead'
    assert json.loads(payload) == {'leader_hand': LEADER, 'level': 3}
    # ISO-8601 UTC, e.g. 2026-08-04T13:22:05Z — sorts chronologically as text.
    assert len(ts) == 20 and ts[4] == '-' and ts[10] == 'T' and ts.endswith('Z')


def test_survives_a_payload_json_cannot_serialise(tmp_path):
    path = tmp_path / 'queries.db'
    QueryLog(str(path)).record('lead', {'when': object()})
    (_, _, payload), = rows(path)
    assert 'object at 0x' in payload          # default=str, not a crash


def test_concurrent_writes_all_land(tmp_path):
    """Requests run in Starlette's threadpool, so writes are concurrent."""
    qlog = QueryLog(str(tmp_path / 'queries.db'))
    threads = [threading.Thread(target=qlog.record, args=('lead', {'i': i}))
               for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(rows(tmp_path / 'queries.db')) == 40


# --- failure is never the caller's problem ---------------------------------

def test_an_unusable_path_disables_logging_instead_of_raising(tmp_path):
    blocker = tmp_path / 'not-a-dir'
    blocker.write_text('')
    qlog = QueryLog(str(blocker / 'queries.db'))   # parent is a file
    assert not qlog.enabled
    qlog.record('lead', {'a': 1})                  # must not raise


def test_a_write_failure_does_not_propagate(tmp_path, monkeypatch):
    qlog = QueryLog(str(tmp_path / 'queries.db'))

    def boom(*a, **k):
        raise sqlite3.OperationalError('disk I/O error')

    monkeypatch.setattr(qlog, '_connect', boom)
    qlog.record('lead', {'a': 1})                  # must not raise


def test_a_broken_log_does_not_break_a_simulation(tmp_path, monkeypatch):
    broken = QueryLog(str(tmp_path / 'queries.db'))
    monkeypatch.setattr(broken, '_connect', lambda: (_ for _ in ()).throw(OSError('nope')))
    monkeypatch.setattr(querylog_module, 'QUERY_LOG', broken)
    lead_service._cache.clear()
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100, 'constraints': {},
    })
    assert r.status_code == 200, r.text
    lead_service._cache.clear()


# --- through the API -------------------------------------------------------

def test_lead_endpoint_logs_the_request(logdb):
    body = {'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
            'num_simulations': 100, 'constraints': {}}
    assert client.post('/api/simulate', json=body).status_code == 200
    (_, tool, payload), = rows(logdb)
    assert tool == 'lead'
    logged = json.loads(payload)
    assert logged['leader_hand'] == LEADER and logged['level'] == 3


def test_contract_endpoint_logs_the_request(logdb):
    body = {'hand': OWN, 'seat': 'S', 'vul': 'none', 'num_deals': 50}
    assert client.post('/api/contract/simulate', json=body).status_code == 200
    (_, tool, payload), = rows(logdb)
    assert tool == 'contract'
    assert json.loads(payload)['hand'] == OWN


def test_a_rejected_query_is_still_logged(logdb):
    """422s are the interesting ones — what did someone ask for that failed?"""
    r = client.post('/api/simulate', json={
        'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
        'num_simulations': 100,
        'constraints': {'hcp': {'N': [30, 40], 'E': [30, 40]}},   # impossible
    })
    assert r.status_code == 422
    (_, tool, _), = rows(logdb)
    assert tool == 'lead'


def test_a_cached_repeat_is_logged_again(logdb):
    """The second run is served from cache, but the user still asked."""
    body = {'leader_hand': LEADER, 'level': 3, 'strain': 'N', 'declarer': 'S',
            'num_simulations': 100, 'constraints': {}}
    client.post('/api/simulate', json=body)
    client.post('/api/simulate', json=body)
    assert len(rows(logdb)) == 2
