"""The play solver's remote judge backend: judgements and traces fanned out to
the `bridge-play-worker` Lambda (play v1.5, docs/play/v1.5-lambda-strict-plan.md).

`LambdaBackend` implements `engine.play.expert.JudgeBackend`. A wave's memo
misses arrive as one `judge` call; the client partitions them into groups of
`group_size`, invokes the function once per group from a thread pool of
`concurrency` workers, and returns the verdicts index-aligned. Traces are
sliced `trace_slice` layouts per invoke the same way. Any group that fails —
a network error, a timeout, a function error, an engine-sha mismatch after a
half-deployed API/worker pair — is judged **locally** through `LocalBackend`,
so an outage degrades to today's speed and never to a wrong answer (a verdict
is a pure function of its inputs, wherever it runs). Counters for the debug
endpoint say how much went remote and how often the fallback fired.

This is the one module that knows about AWS, and it sits in `app_play`, not
the engine: the engine stays free of cloud imports, and `boto3` is imported
lazily on the first call so tests (and a `local` deployment) never need it.
`from_env()` builds the backend the play compose file configures:

    BRIDGE_JUDGE_BACKEND     local | lambda            (default local)
    BRIDGE_WORKER_FUNCTION   function name             (default bridge-play-worker)
    BRIDGE_WORKER_GROUP      judgements per invoke     (default 4)
    BRIDGE_WORKER_CONCURRENCY invokes in flight        (default 64)
    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION — boto3's own

The invoke user can call this one function and nothing else (deploy/provision.md
§9 step 5); no identifier from the AWS account appears in the repo.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from engine.play import wire
from engine.play.expert import LOCAL, LocalBackend

log = logging.getLogger('bridge.play.worker')

DEFAULT_FUNCTION = 'bridge-play-worker'
DEFAULT_GROUP = 4
DEFAULT_CONCURRENCY = 64
DEFAULT_TRACE_SLICE = 200       # one DDS AnalyseAllPlays call per slice on the worker
INVOKE_TIMEOUT = 70             # s; the function's own timeout is 60


class WorkerError(Exception):
    """The function ran and refused or failed the request (Lambda's
    `FunctionError`); the message is the worker's."""


class LambdaBackend:
    kind = 'lambda'

    def __init__(self, function=DEFAULT_FUNCTION, *, group_size=DEFAULT_GROUP,
                 concurrency=DEFAULT_CONCURRENCY, trace_slice=DEFAULT_TRACE_SLICE,
                 client=None, local: LocalBackend = LOCAL):
        self.function = function
        self.group_size = max(1, int(group_size))
        self.concurrency = max(1, int(concurrency))
        self.trace_slice = max(1, int(trace_slice))
        # Judgements a wave can carry in one trip of the pool: the outer
        # loop over-draws layouts to fill it (`expert.round_size`).
        self.width = self.group_size * self.concurrency
        self.local = local
        self._client = client               # a boto3 Lambda client, or a stand-in
        self._client_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=self.concurrency,
                                        thread_name_prefix='judge-lambda')
        self._lock = threading.Lock()
        self.counters = {
            'invocations': 0, 'remote_items': 0, 'remote_layouts': 0,
            'fallback_groups': 0, 'fallback_items': 0, 'fallback_layouts': 0,
            'errors': 0, 'sha_mismatch': 0, 'remote_seconds': 0.0,
            'last_error': None,
        }

    # --- JudgeBackend -----------------------------------------------------------

    def judge(self, items, **kwargs) -> list:
        groups = [items[i:i + self.group_size] for i in range(0, len(items), self.group_size)]
        futures = [self._pool.submit(self._judge_group, g, kwargs) for g in groups]
        out = []
        for f in futures:
            out.extend(f.result())
        return out

    def trace(self, layouts, strain, declarer, play) -> list:
        slices = [layouts[i:i + self.trace_slice]
                  for i in range(0, len(layouts), self.trace_slice)]
        futures = [self._pool.submit(self._trace_slice, s, strain, declarer, play)
                   for s in slices]
        out = []
        for f in futures:
            out.extend(f.result())
        return out

    def stats(self) -> dict:
        with self._lock:
            return {'kind': self.kind, 'function': self.function,
                    'group_size': self.group_size, 'concurrency': self.concurrency,
                    'width': self.width, 'trace_slice': self.trace_slice, **self.counters}

    # --- one group / one slice ---------------------------------------------------

    def _judge_group(self, group, kwargs):
        try:
            body = self._invoke(wire.judge_request(group, **kwargs))
            results = wire.judge_results(body, len(group))
        except Exception as e:
            self._fallback(e, items=len(group))
            return self.local.judge(group, **kwargs)
        with self._lock:
            self.counters['remote_items'] += len(group)
        return results

    def _trace_slice(self, layouts, strain, declarer, play):
        try:
            body = self._invoke(wire.trace_request(layouts, strain, declarer, play))
            traces = wire.trace_results(body, len(layouts))
        except Exception as e:
            self._fallback(e, layouts=len(layouts))
            return self.local.trace(layouts, strain, declarer, play)
        with self._lock:
            self.counters['remote_layouts'] += len(layouts)
        return traces

    def _fallback(self, error, *, items=0, layouts=0):
        with self._lock:
            c = self.counters
            c['errors'] += 1
            c['fallback_groups'] += 1
            c['fallback_items'] += items
            c['fallback_layouts'] += layouts
            if 'sha_mismatch' in str(error):
                c['sha_mismatch'] += 1
            c['last_error'] = f'{type(error).__name__}: {error}'[:300]
            n = c['errors']
        # Every failure is a local fallback, so a dead function would log once
        # per group; keep it to the first and then every hundredth.
        if n == 1 or n % 100 == 0:
            log.warning('play worker fallback #%d (%s) — judged locally', n, error)

    # --- the invoke ------------------------------------------------------------

    def _invoke(self, payload: dict) -> dict:
        t0 = time.perf_counter()
        client = self._get_client()
        resp = client.invoke(FunctionName=self.function,
                             Payload=json.dumps(payload).encode())
        raw = resp['Payload'].read()
        body = json.loads(raw) if raw else {}
        with self._lock:
            self.counters['invocations'] += 1
            self.counters['remote_seconds'] += time.perf_counter() - t0
        if resp.get('FunctionError'):
            msg = body.get('errorMessage', raw[:300]) if isinstance(body, dict) else raw[:300]
            raise WorkerError(str(msg))
        if not isinstance(body, dict):
            raise WorkerError(f'unexpected worker reply: {raw[:100]!r}')
        return body

    def _get_client(self):
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    import boto3                                  # lazy: local mode never needs it
                    from botocore.config import Config
                    self._client = boto3.client('lambda', config=Config(
                        connect_timeout=5, read_timeout=INVOKE_TIMEOUT,
                        retries={'max_attempts': 2},
                        max_pool_connections=self.concurrency))
        return self._client


def from_env(environ=None):
    """The backend the environment asks for: `LocalBackend` unless
    `BRIDGE_JUDGE_BACKEND=lambda`. Raises on an unknown value rather than
    silently running local."""
    env = os.environ if environ is None else environ
    kind = (env.get('BRIDGE_JUDGE_BACKEND') or 'local').strip().lower()
    if kind == 'local':
        return LOCAL
    if kind == 'lambda':
        return LambdaBackend(
            env.get('BRIDGE_WORKER_FUNCTION') or DEFAULT_FUNCTION,
            group_size=int(env.get('BRIDGE_WORKER_GROUP') or DEFAULT_GROUP),
            concurrency=int(env.get('BRIDGE_WORKER_CONCURRENCY') or DEFAULT_CONCURRENCY))
    raise ValueError(f"BRIDGE_JUDGE_BACKEND must be 'local' or 'lambda', got {kind!r}")
