"""Wire format for the play solver's remote judge backend (play v1.5).

A judgement's verdict is a pure function of its memo key — the context (deal,
contract, play, constraints, settings, inner cap), the play index, the judging
view, that seat's holding and the card — because the inner sample is seeded
from those values (`expert._seeded`, which hashes their `repr`). So a worker
anywhere can judge a batch and return verdicts bit-identical to the local
path, *provided it rebuilds the inputs exactly*: JSON has no tuples, and a
context key whose tuples came back as lists would seed every judgement
differently without any error. `pack` / `unpack` therefore tag tuples on the
wire and restore them on the way back, and the round trip is the identity
(`unpack(pack(x)) == x`, types included) — pinned by `tests/test_play_wire.py`.

The request and response shapes here are shared by the worker
(`worker/handler.py`, which decodes a request and encodes verdicts) and the
client (`app_play/worker_client.py`, the reverse). Both directions live in
the engine so neither side can drift from the other. Nothing here imports a
cloud SDK.
"""

from __future__ import annotations

from dataclasses import asdict

from ..version import engine_sha
from .expert import ExpertSettings, OpponentDecision, Verdict

_TUPLE = '__tuple__'


def pack(value):
    """`value` as JSON-safe data: tuples become `{"__tuple__": [...]}`,
    everything else is copied structurally. Dict keys must be strings."""
    if isinstance(value, tuple):
        return {_TUPLE: [pack(v) for v in value]}
    if isinstance(value, list):
        return [pack(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f'wire dict keys must be str, got {k!r}')
            out[k] = pack(v)
        return out
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f'cannot pack {type(value).__name__} for the wire')


def unpack(value):
    """The inverse of `pack`."""
    if isinstance(value, dict):
        if len(value) == 1 and _TUPLE in value:
            return tuple(unpack(v) for v in value[_TUPLE])
        return {k: unpack(v) for k, v in value.items()}
    if isinstance(value, list):
        return [unpack(v) for v in value]
    return value


# --- judge -------------------------------------------------------------------

def judge_request(items, *, level, strain, declarer, play, all_constraints,
                  settings, inner_cap, context_key) -> dict:
    """One `judge` request for `items` (`[(layout_hands, OpponentDecision), ...]`)
    and the judging kwargs `expert.judge_items` takes."""
    return {
        'op': 'judge',
        'engine_sha': engine_sha(),
        'level': level,
        'strain': strain,
        'declarer': declarer,
        'play': list(play),
        'all_constraints': pack(all_constraints or {}),
        'settings': asdict(settings),
        'inner_cap': inner_cap,
        'context_key': pack(context_key),
        'items': [{'layout': dict(layout), 'decision': pack(asdict(decision))}
                  for layout, decision in items],
    }


def judge_inputs(request: dict):
    """`(items, kwargs)` for `expert.judge_items` from a `judge` request."""
    items = [(item['layout'], OpponentDecision(**unpack(item['decision'])))
             for item in request['items']]
    kwargs = dict(
        level=request['level'],
        strain=request['strain'],
        declarer=request['declarer'],
        play=list(request['play']),
        all_constraints=unpack(request['all_constraints']),
        settings=ExpertSettings(**request['settings']),
        inner_cap=request['inner_cap'],
        context_key=unpack(request['context_key']),
    )
    return items, kwargs


def judge_response(results) -> dict:
    """`results` (`[(Verdict, [seconds per inner wave]), ...]`, index-aligned
    with the request's items) as the response body."""
    return {'verdicts': [{**asdict(v), 'costs': list(costs)} for v, costs in results]}


def judge_results(response: dict, count: int):
    """The inverse of `judge_response`; `count` is the request's item count,
    so a short or long answer is refused rather than misaligned."""
    rows = response.get('verdicts')
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError(f'judge response has {len(rows) if isinstance(rows, list) else "no"} '
                         f'verdicts for {count} items')
    out = []
    for row in rows:
        costs = [float(c) for c in row.get('costs', [])]
        fields = {k: row[k] for k in ('consistent', 'gap', 'n', 'sigma', 'reason')}
        out.append((Verdict(**fields), costs))
    return out


# --- trace -------------------------------------------------------------------

def trace_request(layouts, strain, declarer, play) -> dict:
    return {
        'op': 'trace',
        'engine_sha': engine_sha(),
        'strain': strain,
        'declarer': declarer,
        'play': list(play),
        'layouts': [dict(L) for L in layouts],
    }


def trace_inputs(request: dict):
    return (request['layouts'], request['strain'], request['declarer'],
            list(request['play']))


def trace_response(traces) -> dict:
    return {'traces': [list(t) for t in traces]}


def trace_results(response: dict, count: int):
    rows = response.get('traces')
    if not isinstance(rows, list) or len(rows) != count:
        raise ValueError(f'trace response has {len(rows) if isinstance(rows, list) else "no"} '
                         f'traces for {count} layouts')
    return [[int(v) for v in t] for t in rows]
