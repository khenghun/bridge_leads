"""The play solver's Lambda worker handler (worker/handler.py), called in-process."""

import pytest

from engine.version import engine_sha
from worker import handler as w


def test_engine_sha_is_stable_and_short():
    assert engine_sha() == engine_sha()
    assert len(engine_sha()) == 12
    int(engine_sha(), 16)


def test_health_proves_dds_and_reports_parity_figures():
    r = w.handler({'op': 'health'})
    assert r['ok'] and r['op'] == 'health'
    assert r['engine_sha'] == engine_sha()
    assert r['solve_cards'] > 0 and r['solve_ms'] > 0
    assert r['inner_first'] == max(5, r['dds_threads'])
    assert r['schedule_ok'] == (r['inner_first'] == 5)
    assert r['dds_stats']['solve']['boards'] >= 1


def test_echo_returns_payload_without_sha():
    r = w.handler({'op': 'echo', 'payload': {'n': 1}})
    assert r['payload'] == {'n': 1} and r['received_at'] > 0
    assert r['seconds'] >= 0 and r['invocation'] >= 1


def test_bench_is_repeatable():
    a = w.handler({'op': 'bench', 'boards': 3, 'seed': 7, 'engine_sha': engine_sha()})
    b = w.handler({'op': 'bench', 'boards': 3, 'seed': 7, 'engine_sha': engine_sha()})
    assert a['boards'] == 3 and a['ms_per_board'] > 0
    assert a['checksum'] == b['checksum']


def test_bench_refuses_sha_mismatch_and_bad_sizes():
    with pytest.raises(w.WorkerError, match='sha_mismatch'):
        w.handler({'op': 'bench', 'boards': 1, 'engine_sha': 'nope'})
    with pytest.raises(w.WorkerError, match='boards'):
        w.handler({'op': 'bench', 'boards': 0, 'engine_sha': engine_sha()})


def test_unknown_or_missing_op():
    with pytest.raises(w.WorkerError, match='unknown op'):
        w.handler({'op': 'judge'})
    with pytest.raises(w.WorkerError, match="missing 'op'"):
        w.handler({})
