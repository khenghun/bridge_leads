"""AWS Lambda handler for the play solver's worker function.

Play v1.5 (docs/play/v1.5-lambda-strict-plan.md) fans the expert filter's
judgements out to Lambda. The worker is the backend image with this handler
(the Dockerfile's `worker` target, started by `awslambdaric`), so it runs the
very engine the API runs; every request carries `engine_sha` and a mismatch is
refused. Dispatch is on the event's `op`:

- `echo`    — returns the payload with timestamps; measures invoke round trips.
- `health`  — proves the DDS `.so` loads under the Lambda runtime and reports
              the figures the client must agree with (engine sha, DDS threads,
              the inner schedule's first step). `schedule_ok` is the parity
              assertion the plan asks for: the first inner batch must be 5.
- `bench`   — solves `boards` random deals and reports the per-board speed,
              the spike's per-vCPU measurement (`seed` makes it repeatable).

The `judge` and `trace` operations arrive with the judge-backend seam
(plan step 1); until then the worker is the spike's measuring instrument.
No AWS SDK is imported here — the worker only answers.
"""

import os
import platform
import time

from endplay.dealer import generate_deal

from engine import dds_runtime
from engine.play.expert import INNER_FIRST
from engine.version import engine_sha

FUNCTION_NAME = 'bridge-play-worker'
EXPECTED_INNER_FIRST = 5   # the value every regression pin was taken at

_BOOT = time.time()
_INVOCATIONS = 0


class WorkerError(Exception):
    """Raised for a request the worker will not serve; Lambda reports it as a
    function error, which the client treats as "judge this group locally"."""


def handler(event, context=None):
    """Lambda entry point (`worker.handler.handler`)."""
    global _INVOCATIONS
    _INVOCATIONS += 1
    event = event or {}
    op = event.get('op')
    if op is None:
        raise WorkerError("missing 'op'")
    fn = _OPS.get(op)
    if fn is None:
        raise WorkerError(f"unknown op {op!r}; one of {sorted(_OPS)}")
    if op not in ('echo', 'health'):
        _check_sha(event)
    started = time.perf_counter()
    result = fn(event)
    result.update({
        'op': op,
        'seconds': round(time.perf_counter() - started, 4),
        'invocation': _INVOCATIONS,
        'cold': _INVOCATIONS == 1,
    })
    return result


def _check_sha(event):
    want = event.get('engine_sha')
    have = engine_sha()
    if want != have:
        raise WorkerError(f'sha_mismatch: request {want!r}, worker {have!r}')


def _echo(event):
    return {'received_at': time.time(), 'payload': event.get('payload')}


def _health(event):
    # One tiny solve: if the bundled DDS `.so` (and libgomp1) is missing, this
    # is where it fails.
    t0 = time.perf_counter()
    board = dds_runtime.solve_all([generate_deal(seed=1)])[0]
    solve_ms = (time.perf_counter() - t0) * 1000
    return {
        'ok': True,
        'function': os.environ.get('AWS_LAMBDA_FUNCTION_NAME', FUNCTION_NAME),
        'engine_sha': engine_sha(),
        'dds_threads': dds_runtime.DDS_THREADS,
        'inner_first': INNER_FIRST,
        'schedule_ok': INNER_FIRST == EXPECTED_INNER_FIRST,
        'solve_ms': round(solve_ms, 1),
        'solve_cards': len(list(board)),
        'python': platform.python_version(),
        'endplay': _endplay_version(),
        'cpu_count': os.cpu_count(),
        'memory_mb': _int_env('AWS_LAMBDA_FUNCTION_MEMORY_SIZE'),
        'region': os.environ.get('AWS_REGION'),
        'uptime_s': round(time.time() - _BOOT, 1),
        'dds_stats': dds_runtime.stats(),
    }


def _bench(event):
    boards = int(event.get('boards', 50))
    if not 1 <= boards <= 2000:
        raise WorkerError('boards must be 1..2000')
    seed = int(event.get('seed', 0))
    t0 = time.perf_counter()
    deals = [generate_deal(seed=seed + i) for i in range(boards)]
    deal_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    results = dds_runtime.solve_all(deals)
    solve_s = time.perf_counter() - t0
    return {
        'boards': boards,
        'seed': seed,
        'deal_s': round(deal_s, 3),
        'solve_s': round(solve_s, 3),
        'ms_per_board': round(solve_s * 1000 / boards, 2),
        'dds_threads': dds_runtime.DDS_THREADS,
        'checksum': sum(max(t for _, t in r) for r in results),
    }


def _endplay_version():
    try:
        from importlib.metadata import version
        return version('endplay')
    except Exception:
        return None


def _int_env(name):
    v = os.environ.get(name)
    return int(v) if v and v.isdigit() else None


_OPS = {'echo': _echo, 'health': _health, 'bench': _bench}
