"""Thread-safety of the service cache: concurrent identical requests must
simulate only once (dogpile protection), and a failed leader must not wedge
the waiters."""

import threading
import time

import pytest

from app.lead import service
from app.lead.schemas import SimulateRequest


def _request() -> SimulateRequest:
    return SimulateRequest(
        leader_hand='T.KT932.Q2.T9843', level=3, strain='N', declarer='S',
        num_simulations=100,
    )


@pytest.fixture(autouse=True)
def clean_cache():
    service._cache.clear()
    yield
    service._cache.clear()


def test_concurrent_identical_requests_simulate_once(monkeypatch):
    calls = []

    def slow_fake(**kwargs):
        calls.append(1)
        time.sleep(0.2)                     # long enough for all threads to pile up
        return {'num_simulations': kwargs['num_simulations'], 'leads': []}

    monkeypatch.setattr(service, 'simulate_opening_lead', slow_fake)

    results = []
    threads = [threading.Thread(target=lambda: results.append(
        service.run_simulation(_request()))) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1                  # one leader; seven cache-served followers
    assert len(results) == 8
    assert all(r['num_simulations'] == 100 for r in results)


def test_failed_leader_releases_waiters(monkeypatch):
    attempts = []

    def flaky_fake(**kwargs):
        attempts.append(1)
        time.sleep(0.1)
        if len(attempts) == 1:
            raise RuntimeError('boom')
        return {'num_simulations': kwargs['num_simulations'], 'leads': []}

    monkeypatch.setattr(service, 'simulate_opening_lead', flaky_fake)

    outcomes = []

    def worker():
        try:
            outcomes.append(('ok', service.run_simulation(_request())))
        except RuntimeError:
            outcomes.append(('err', None))

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The first leader fails; a waiter takes over and succeeds, the rest are
    # served from cache. Nobody hangs.
    assert len(outcomes) == 4
    assert sum(1 for kind, _ in outcomes if kind == 'err') == 1
    assert all(r['num_simulations'] == 100 for kind, r in outcomes if kind == 'ok')
    assert not service._cache.inflight         # no leaked in-flight entries
