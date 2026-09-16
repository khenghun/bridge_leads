"""The judge backend seam (play v1.5): the wire codec, and a backend that
pushes every judgement and trace through JSON must grade bit-identically to
the in-process one."""

import json
import random

import pytest

from engine.play import grader, state, wire
from engine.play.expert import (
    LOCAL, ExpertSettings, VerdictMemo, Verdict, judge_items, opponent_decisions,
)
from tests.test_play_expert import ENDING_HANDS, ENDING_PLAY, HANDS, PLAY, west_holdings


# --- pack / unpack ------------------------------------------------------------

def test_pack_unpack_is_the_identity_types_included():
    value = {
        'hcp': {'E': (8, 12), 'W': (None, 5)},
        'shapes': {'N': [{'S': (4, 4), 'H': (0, 13)}]},
        'fixed_cards': {'S': ['SA', 'HK']},
        'ctx': (('{"N": "x"}', 3, 'N', 'S', ('SA', 'S2'), '{}'), (0.5, 0.1, 2.0, 20, True, 1), 8),
        'holding': ('C2', 'D3'),
        'flags': [True, False, None, 1.5, 'T'],
        'empty': ((), [], {}),
    }
    back = wire.unpack(json.loads(json.dumps(wire.pack(value))))
    assert back == value
    # Equality alone would pass a list for a tuple; the seeds hash `repr`.
    assert repr(back) == repr(value)


def test_pack_refuses_what_the_wire_cannot_carry():
    with pytest.raises(TypeError):
        wire.pack({1: 'int key'})
    with pytest.raises(TypeError):
        wire.pack({'x': {'S', 'H'}})


# --- judge / trace requests --------------------------------------------------

def _board17_judge_inputs(settings=ExpertSettings(strict=True), inner_cap=8):
    """A real judge batch: West's suspects on the actual board-17 layout at
    the position before index 12, judged from their own views."""
    play = list(PLAY)
    ck = grader._context_key(HANDS, 1, 'N', 'W', play, {})
    ctx = (ck, settings.key(), inner_cap)
    decisions = opponent_decisions(HANDS, 'N', 'W', play, 12, 'W')
    assert decisions, 'the fixture must give West something to judge'
    items = [(dict(HANDS), d) for d in decisions]
    kwargs = dict(level=1, strain='N', declarer='W', play=play, all_constraints={},
                  settings=settings, inner_cap=inner_cap, context_key=ctx)
    return items, kwargs


def test_a_judge_request_round_trips_its_inputs_exactly():
    items, kwargs = _board17_judge_inputs()
    req = json.loads(json.dumps(wire.judge_request(items, **kwargs)))
    assert req['op'] == 'judge' and len(req['engine_sha']) == 12
    back_items, back_kwargs = wire.judge_inputs(req)
    assert back_items == items
    assert back_kwargs == kwargs
    assert repr(back_kwargs['context_key']) == repr(kwargs['context_key'])
    assert isinstance(back_kwargs['settings'], ExpertSettings)
    assert all(isinstance(d.holding, tuple) for _, d in back_items)


def test_a_judge_response_round_trips_and_refuses_misalignment():
    results = [(Verdict(True, 0.05, 8, 0.3, 'cap'), [0.01, 0.02]),
               (Verdict(False, 0.9, 5, 0.31, 'shown-worse'), [0.005])]
    resp = json.loads(json.dumps(wire.judge_response(results)))
    assert wire.judge_results(resp, 2) == results
    with pytest.raises(ValueError, match='verdicts'):
        wire.judge_results(resp, 3)
    with pytest.raises(ValueError, match='verdicts'):
        wire.judge_results({}, 2)


def test_a_trace_request_round_trips():
    layouts = [dict(HANDS), dict(ENDING_HANDS)]
    req = json.loads(json.dumps(wire.trace_request(layouts, 'N', 'W', PLAY[:5])))
    assert wire.trace_inputs(req) == (layouts, 'N', 'W', list(PLAY[:5]))
    resp = json.loads(json.dumps(wire.trace_response([[7, 7, 6], [8, 8, 8]])))
    assert wire.trace_results(resp, 2) == [[7, 7, 6], [8, 8, 8]]
    with pytest.raises(ValueError, match='traces'):
        wire.trace_results(resp, 1)


# --- a backend through the wire is the local backend ---------------------------

class WireBackend:
    """Every call serialised to JSON and back, then judged in this process —
    the shape of the remote path without the network. Counts calls."""

    kind = 'wire'

    def __init__(self):
        self.judge_calls = 0
        self.trace_calls = 0

    def judge(self, items, **kwargs):
        self.judge_calls += 1
        req = json.loads(json.dumps(wire.judge_request(items, **kwargs)))
        back_items, back_kwargs = wire.judge_inputs(req)
        resp = json.loads(json.dumps(wire.judge_response(judge_items(back_items, **back_kwargs))))
        return wire.judge_results(resp, len(items))

    def trace(self, layouts, strain, declarer, play):
        self.trace_calls += 1
        req = json.loads(json.dumps(wire.trace_request(layouts, strain, declarer, play)))
        resp = json.loads(json.dumps(wire.trace_response(LOCAL.trace(*wire.trace_inputs(req)))))
        return wire.trace_results(resp, len(layouts))


def test_judge_items_through_the_wire_gives_the_same_verdicts():
    items, kwargs = _board17_judge_inputs()
    local = judge_items(items, **kwargs)
    remote = WireBackend().judge(items, **kwargs)
    assert [v for v, _ in remote] == [v for v, _ in local]
    assert [len(c) for _, c in remote] == [len(c) for _, c in local]   # same inner waves


def stable(decisions):
    """Graded decisions minus the counters that depend on wall-clock time:
    `judged` / `memo_hits` (suspect priority learns from measured seconds, so
    two identical local runs can differ by a judgement) and `sigma` (the
    mean over the judged verdicts). Grades, layouts examined and layouts
    accepted must match exactly."""
    out = []
    for d in decisions:
        d = dict(d)
        if d.get('expert'):
            d['expert'] = {k: v for k, v in d['expert'].items()
                           if k not in ('judged', 'memo_hits', 'sigma')}
        out.append(d)
    return out


@pytest.mark.parametrize('strict', [False, True])
def test_grade_play_through_the_wire_is_bit_identical(strict):
    kw = dict(num_deals=8, seed=0, expert=ExpertSettings(strict=strict), decisions=[10, 12])
    local = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', memo=VerdictMemo(), **kw)
    backend = WireBackend()
    remote = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', memo=VerdictMemo(),
                               judge_backend=backend, **kw)
    assert stable(remote['decisions']) == stable(local['decisions'])
    assert backend.judge_calls > 0
    assert (backend.trace_calls > 0) == (not strict)


def test_the_ending_is_filtered_the_same_through_the_wire():
    hands, play = ENDING_HANDS, ENDING_PLAY + ['D2']
    position = state.replay(hands, 'N', 'S', play)
    out = {}
    for name, backend in (('local', None), ('wire', WireBackend())):
        layouts, stats = grader.expert_layouts(
            position, 'S', {}, {}, 12, ExpertSettings(strict=True), random.Random(0),
            level=3, context_key=('ending', 0), memo=VerdictMemo(), backend=backend)
        out[name] = (layouts, stats.sampled, stats.consistent)
    assert out['wire'] == out['local']
    for held in west_holdings(out['wire'][0], play):
        assert not {'SA', 'SK'} <= held


def test_grade_position_accepts_a_judge_backend():
    backend = WireBackend()
    r = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:12], num_deals=6, seed=0,
                              expert=ExpertSettings(strict=True), memo=VerdictMemo(),
                              judge_backend=backend)
    assert r['expert']['consistent'] > 0 and backend.judge_calls > 0
