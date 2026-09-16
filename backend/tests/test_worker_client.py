"""`app_play.worker_client.LambdaBackend` against a stand-in Lambda: the
worker handler called in-process behind a fake boto3 client, so the whole
remote path — request encoding, invoke, function errors, decoding, grouping,
fallback — runs without the network or boto3."""

import io
import json
import random

import pytest

from app_play import worker_client
from app_play.worker_client import LambdaBackend, from_env
from engine.play import grader, state
from engine.play.expert import LOCAL, ExpertSettings, VerdictMemo, judge_items
from engine.version import engine_sha
from tests.test_play_wire import HANDS, PLAY, _board17_judge_inputs, stable
from worker import handler as w


class FakeLambda:
    """A boto3 Lambda client whose function is the worker handler. `fail`
    decides per call: raise (transport error) or return a FunctionError."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail or (lambda n, payload: None)

    def invoke(self, FunctionName, Payload):
        payload = json.loads(Payload)
        self.calls.append(payload)
        n = len(self.calls)
        mode = self.fail(n, payload)
        if mode == 'raise':
            raise ConnectionError('boom')
        if mode == 'error':
            body = {'errorMessage': 'sha_mismatch: request "x", worker "y"',
                    'errorType': 'WorkerError'}
            return {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'Payload': io.BytesIO(json.dumps(body).encode())}
        try:
            body = w.handler(payload)
        except w.WorkerError as e:
            return {'StatusCode': 200, 'FunctionError': 'Unhandled',
                    'Payload': io.BytesIO(json.dumps(
                        {'errorMessage': str(e), 'errorType': 'WorkerError'}).encode())}
        return {'StatusCode': 200, 'Payload': io.BytesIO(json.dumps(body).encode())}


def backend(fail=None, **kw):
    fake = FakeLambda(fail)
    return LambdaBackend('fn', client=fake, **kw), fake


# --- judge ---------------------------------------------------------------------

def test_judge_groups_items_and_returns_them_index_aligned():
    items, kwargs = _board17_judge_inputs()
    assert len(items) >= 3
    b, fake = backend(group_size=2)
    remote = b.judge(items, **kwargs)
    local = judge_items(items, **kwargs)
    assert [v for v, _ in remote] == [v for v, _ in local]
    assert len(fake.calls) == (len(items) + 1) // 2
    assert all(c['op'] == 'judge' and c['engine_sha'] == engine_sha() for c in fake.calls)
    s = b.stats()
    assert s['invocations'] == len(fake.calls) and s['remote_items'] == len(items)
    assert s['fallback_groups'] == 0 and s['remote_seconds'] > 0


def test_a_failed_group_is_judged_locally_and_the_rest_remotely():
    items, kwargs = _board17_judge_inputs()
    b, fake = backend(fail=lambda n, p: 'raise' if n == 1 else None, group_size=1)
    remote = b.judge(items, **kwargs)
    assert [v for v, _ in remote] == [v for v, _ in judge_items(items, **kwargs)]
    s = b.stats()
    assert s['fallback_groups'] == 1 and s['fallback_items'] == 1
    assert s['remote_items'] == len(items) - 1
    assert 'ConnectionError' in s['last_error']


def test_a_function_error_counts_a_sha_mismatch_and_falls_back():
    items, kwargs = _board17_judge_inputs()
    b, fake = backend(fail=lambda n, p: 'error', group_size=len(items))
    remote = b.judge(items, **kwargs)
    assert [v for v, _ in remote] == [v for v, _ in judge_items(items, **kwargs)]
    s = b.stats()
    assert s['invocations'] == 1 and s['sha_mismatch'] == 1 and s['fallback_groups'] == 1
    assert s['remote_items'] == 0


def test_a_short_answer_is_refused_not_misaligned():
    items, kwargs = _board17_judge_inputs()

    class Short(FakeLambda):
        def invoke(self, FunctionName, Payload):
            r = super().invoke(FunctionName, Payload)
            body = json.loads(r['Payload'].read())
            body['verdicts'] = body['verdicts'][:-1]
            return {'StatusCode': 200, 'Payload': io.BytesIO(json.dumps(body).encode())}

    b = LambdaBackend('fn', client=Short(), group_size=len(items))
    remote = b.judge(items, **kwargs)
    assert [v for v, _ in remote] == [v for v, _ in judge_items(items, **kwargs)]
    assert b.stats()['fallback_groups'] == 1


# --- trace ---------------------------------------------------------------------

def test_trace_is_sliced_and_equals_local():
    position = state.replay(HANDS, 'N', 'W', PLAY[:9])
    layouts = [dict(HANDS)] + grader._sample_layouts(position, 'W', {}, 4, random.Random(2))
    b, fake = backend(trace_slice=2)
    assert b.trace(layouts, 'N', 'W', PLAY[:9]) == LOCAL.trace(layouts, 'N', 'W', PLAY[:9])
    assert len(fake.calls) == 3 and all(c['op'] == 'trace' for c in fake.calls)
    assert b.stats()['remote_layouts'] == 5


def test_a_failed_trace_slice_falls_back_locally():
    position = state.replay(HANDS, 'N', 'W', PLAY[:9])
    layouts = grader._sample_layouts(position, 'W', {}, 3, random.Random(3))
    b, _ = backend(fail=lambda n, p: 'raise' if n == 2 else None, trace_slice=1)
    assert b.trace(layouts, 'N', 'W', PLAY[:9]) == LOCAL.trace(layouts, 'N', 'W', PLAY[:9])
    assert b.stats()['fallback_layouts'] == 1 and b.stats()['remote_layouts'] == 2


# --- the whole grade through the fake Lambda -----------------------------------

@pytest.mark.parametrize('strict', [False, True])
def test_grade_play_through_the_lambda_backend_is_bit_identical(strict):
    kw = dict(num_deals=8, seed=0, expert=ExpertSettings(strict=strict), decisions=[10, 12])
    local = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', memo=VerdictMemo(), **kw)
    b, fake = backend(group_size=3)
    remote = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', memo=VerdictMemo(),
                               judge_backend=b, **kw)
    assert stable(remote['decisions']) == stable(local['decisions'])
    assert b.stats()['fallback_groups'] == 0 and b.stats()['invocations'] > 0
    ops = {c['op'] for c in fake.calls}
    assert ops == ({'judge'} if strict else {'judge', 'trace'})


# --- configuration -------------------------------------------------------------

def test_from_env_defaults_to_local_and_builds_lambda_on_request():
    assert from_env({}) is LOCAL
    assert from_env({'BRIDGE_JUDGE_BACKEND': 'local'}) is LOCAL
    b = from_env({'BRIDGE_JUDGE_BACKEND': 'lambda', 'BRIDGE_WORKER_GROUP': '6',
                  'BRIDGE_WORKER_CONCURRENCY': '10'})
    assert isinstance(b, LambdaBackend)
    assert b.function == worker_client.DEFAULT_FUNCTION
    assert b.group_size == 6 and b.concurrency == 10
    assert b.stats()['kind'] == 'lambda' and b.stats()['invocations'] == 0
    with pytest.raises(ValueError, match='BRIDGE_JUDGE_BACKEND'):
        from_env({'BRIDGE_JUDGE_BACKEND': 'cloud'})


def test_the_service_uses_the_configured_backend(monkeypatch):
    """`run_analysis` grades through `service.JUDGE_BACKEND`."""
    from app_play import service
    from app_play.schemas import AnalyzeRequest
    b, fake = backend()
    monkeypatch.setattr(service, 'JUDGE_BACKEND', b)
    service.clear_cache()
    req = AnalyzeRequest(hands=HANDS, level=1, strain='N', declarer='W', play=PLAY,
                         seat='W', num_deals=6, decisions=[10], expert_opponents=True,
                         expert={'strict': True})
    out = service.run_analysis(req)
    assert out['decisions'][0]['expert']['consistent'] > 0
    assert fake.calls and b.stats()['remote_items'] > 0
    service.clear_cache()


def test_the_debug_endpoint_reports_the_backend():
    from fastapi.testclient import TestClient
    from app_play.main import app
    r = TestClient(app).get('/api/play/debug/judge')
    assert r.status_code == 200 and r.json()['kind'] == 'local'
