"""Sample-size confidence and escalation (play v1.4,
`docs/play/v1.4-sample-size-plan.md`).

- every graded decision carries a `sample` block: the deals it rests on, the
  standard error of its diff in tricks and IMPs, and whether the status is
  firm across the ±2σ band;
- a decision in doubt (not optimal, or not firm) is re-graded on `factor` ×
  the deals, by *extending* the base sample from the decision's own stream —
  so every other decision's draw, and the base draw itself, is untouched;
- with expert opponents on, the extension re-uses the accepted layouts
  unexamined and the inner cap stays at the base count; the expert grade's
  own doubt is the only trigger (an unfiltered second opinion was measured
  and dropped).
"""

import random

import pytest

from engine.play import grader, state
from engine.play.expert import ExpertSettings, VerdictMemo, expert_layouts
from engine.play.grader import EscalationSettings, is_firm

from test_play_grader import HANDS, PLAY
from test_play_expert import ENDING_HANDS, ENDING_PLAY


# --- the standard error and the band -----------------------------------------

class _Flat:
    """A scoring stub: one point per trick, so IMPs mirror tricks."""
    def score(self, tricks):
        return tricks * 100


def test_se_is_zero_when_the_card_played_is_best_on_every_deal():
    per_board = {'HA': [7, 8, 7, 9], 'HK': [7, 8, 7, 9]}
    s = grader._sample_stats(per_board, 'HK', 'HA', 1, _Flat(), 0.0, True, 0.0)
    assert s == {'deals': 4, 'se_tricks': 0.0, 'se_imps': 0.0,
                 'firm': True, 'escalated': False, 'trigger': None}


def test_se_of_a_coin_is_root_pq_over_n():
    # played loses one trick on half the deals: sd 0.5, se 0.5/sqrt(4) = 0.25
    per_board = {'HA': [8, 8, 8, 8], 'HK': [7, 8, 7, 8]}
    s = grader._sample_stats(per_board, 'HK', 'HA', 1, _Flat(), -0.5, False, -1.5)
    assert s['deals'] == 4
    assert s['se_tricks'] == pytest.approx(0.25)
    assert s['se_imps'] > 0
    assert s['firm'] is False        # -0.5 ± 0.5 crosses the -0.3 line


def test_defender_sign_flips_the_difference():
    # declarer tricks: the defender's card played lets one more through on
    # every deal, so from the defender's side diff is -1 on every deal: se 0
    per_board = {'HA': [7, 7, 7], 'HK': [8, 8, 8]}
    s = grader._sample_stats(per_board, 'HK', 'HA', -1, _Flat(), -1.0, False, -3.0)
    assert s['se_tricks'] == 0.0 and s['firm'] is True


def test_firm_needs_every_corner_of_the_band_to_agree():
    assert is_firm(-0.05, False, -0.05, 0.01, 0.01)          # optimal, tight
    assert not is_firm(-0.05, False, -0.05, 0.05, 0.05)      # reaches -0.15: good
    assert is_firm(-0.2, False, -0.2, 0.03, 0.03)            # good either side
    assert not is_firm(-0.2, False, -0.2, 0.06, 0.03)        # -0.32: suboptimal
    assert is_firm(-0.2, False, -0.2, 0.03, 0.2)             # -0.6 IMPs cannot demote a good
    assert is_firm(-0.5, False, -3.0, 0.05, 0.4)             # suboptimal all round
    assert is_firm(-0.5, False, -1.9, 0.05, 0.1)             # suboptimal by tricks whatever the IMPs
    assert not is_firm(-0.05, False, -1.8, 0.01, 0.2)        # good -> suboptimal on the IMP axis


def test_a_best_card_at_the_centre_is_not_best_at_the_edge():
    # a near-tie card: optimal because it is 'best' at the point estimate,
    # but at the band's edge it is a plain -0.2 card
    assert not is_firm(-0.005, True, 0.0, 0.1, 0.1)
    assert is_firm(0.0, True, 0.0, 0.0, 0.0)


# --- grade_play: sample block, marginal count, escalation --------------------

def _grade(escalation, **kw):
    return grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'N', method='single_dummy',
                             num_deals=10, seed=0, escalation=escalation, **kw)


def test_every_graded_decision_carries_a_sample_block():
    res = _grade(None)
    for d in res['decisions']:
        if d['forced']:
            assert d['sample'] is None
        else:
            s = d['sample']
            assert s['deals'] == 10 and s['escalated'] is False
            assert s['se_tricks'] >= 0 and s['se_imps'] >= 0
            assert isinstance(s['firm'], bool)
    assert res['escalation'] is None
    assert res['summary']['marginal'] == sum(
        1 for d in res['decisions'] if d['sample'] and not d['sample']['firm'])


def test_double_dummy_has_a_sample_of_one_and_is_firm():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'N', method='double_dummy',
                            escalation=EscalationSettings())
    for d in res['decisions']:
        if not d['forced']:
            assert d['sample'] == {'deals': 1, 'se_tricks': 0.0, 'se_imps': 0.0,
                                   'firm': True, 'escalated': False, 'trigger': None}
    assert res['escalation'] is not None        # echoed, though nothing to do


def test_escalation_target_is_factor_times_deals_under_the_cap():
    e = EscalationSettings(factor=3)
    assert e.target(100, expert_on=False) == 300
    assert e.target(200, expert_on=False) == 600
    assert e.target(200, expert_on=True) == 300
    assert EscalationSettings(factor=3, max_deals=250).target(100, False) == 250
    assert EscalationSettings(factor=2).target(40, True) == 80
    assert e.target(500, expert_on=False) == 600       # up to the cap
    assert e.target(700, expert_on=False) == 700       # never below the base


def test_decisions_in_doubt_are_extended_and_the_rest_are_untouched():
    base = _grade(None)
    esc = _grade(EscalationSettings(factor=3))
    assert esc['escalation'] == {'factor': 3, 'max_deals': None}
    escalated = [d for d in esc['decisions'] if d['sample'] and d['sample']['escalated']]
    assert escalated, 'Board 17 has decisions in doubt at 10 deals'
    for b, e in zip(base['decisions'], esc['decisions']):
        assert b['index'] == e['index']
        if b['forced']:
            continue
        # the base grade decided the trigger: escalated iff in doubt at 10 deals
        in_doubt = b['status'] != 'optimal' or not b['sample']['firm']
        assert e['sample']['escalated'] == in_doubt
        if in_doubt:
            assert e['sample']['deals'] == 30
            assert e['sample']['trigger'] == ('status' if b['status'] != 'optimal' else 'band')
        else:
            # not a draw moved: bit-identical to the run without escalation
            assert e['sample']['trigger'] is None
            assert e['sample']['deals'] == 10
            assert e['options'] == b['options'] and e['diff'] == b['diff']


def test_the_base_draw_is_untouched_by_an_extension(monkeypatch):
    """An escalated decision's base layouts are exactly the un-escalated
    decision's, and the extension is a second draw from its own stream."""
    draws = []
    real = grader._sample_layouts

    def spy(position, view, constraints, num_deals, rng):
        layouts = real(position, view, constraints, num_deals, rng)
        draws.append((position.index, layouts))
        return layouts

    monkeypatch.setattr(grader, '_sample_layouts', spy)
    _grade(None)
    base = dict(draws)                       # one draw per decision
    draws.clear()
    esc = _grade(EscalationSettings(factor=3))
    by_index = {}
    for index, layouts in draws:
        by_index.setdefault(index, []).append(layouts)
    escalated = [d['index'] for d in esc['decisions'] if d['sample'] and d['sample']['escalated']]
    assert escalated
    for index, calls in by_index.items():
        assert calls[0] == base[index]       # the base draw, bit for bit
        if index in escalated:
            assert len(calls) == 2 and len(calls[1]) == 20
            assert calls[1][0] not in calls[0]
        else:
            assert len(calls) == 1


def test_escalation_is_deterministic():
    a = _grade(EscalationSettings(factor=3))
    b = _grade(EscalationSettings(factor=3))
    assert a == b


def test_escalation_accepts_a_dict_like_the_api_sends():
    res = _grade({'factor': 2, 'max_deals': 15})
    assert res['escalation'] == {'factor': 2, 'max_deals': 15}
    for d in res['decisions']:
        if d['sample'] and d['sample']['escalated']:
            assert d['sample']['deals'] == 15


# --- expert mode: extension reuses the accepted pool, inner cap stays --------

def _ending():
    hands, play = ENDING_HANDS, ENDING_PLAY + ['D2']
    position = state.replay(hands, 'N', 'S', play)
    return position, play


def test_start_layouts_are_not_re_examined():
    position, _ = _ending()
    settings = ExpertSettings()
    memo = VerdictMemo()
    first, st = expert_layouts(position, 'S', {}, {}, 12, settings, random.Random(0),
                               level=3, context_key=('x', 0), memo=memo)
    assert st.consistent == len(first) == 12
    examined = st.sampled
    grown, st2 = expert_layouts(position, 'S', {}, {}, 12, settings, random.Random(1),
                                level=3, context_key=('x', 0), memo=VerdictMemo(),
                                start=first, stats=st, base_deals=12)
    assert grown == first and st2 is st
    assert st.sampled == examined and st.consistent == 12  # nothing drawn, nothing judged again


def test_an_extension_leads_with_the_base_and_keeps_the_inner_cap():
    position, _ = _ending()
    settings = ExpertSettings()
    memo = VerdictMemo()
    first, st = expert_layouts(position, 'S', {}, {}, 12, settings, random.Random(0),
                               level=3, context_key=('x', 0), memo=memo)
    grown, st2 = expert_layouts(position, 'S', {}, {}, 36, settings, random.Random(7),
                                level=3, context_key=('x', 0), memo=memo,
                                start=first, stats=st, base_deals=12)
    assert grown[:12] == first and len(grown) == 36
    assert st2.consistent == 36 and st2.sampled >= 36
    cap = settings.inner_cap(12)
    assert cap != settings.inner_cap(36)
    # every verdict of both passes was judged at the base pass's inner cap
    assert memo._d and all(key[0][2] == cap for key in memo._d)


def test_a_carried_pool_is_capped_at_the_decisions_own_count():
    position, play = _ending()
    settings = ExpertSettings()
    memo = VerdictMemo()
    ctx = (('x', 0), settings.key(), settings.inner_cap(6))
    pool_key = (ctx, 'S', '{}')
    # a previous decision (index 40) that was escalated left a big pool
    big, _ = expert_layouts(position, 'S', {}, {}, 30, settings, random.Random(0),
                            level=3, context_key=('x', 0), memo=VerdictMemo())
    memo.pool_put(pool_key, 40, big)
    _, st = expert_layouts(position, 'S', {}, {}, 6, settings, random.Random(0),
                           level=3, context_key=('x', 0), memo=memo)
    assert st.carried <= 6


def test_expert_mode_escalates_on_its_own_grade_only(monkeypatch):
    """The trigger is consulted once per decision, on the expert grade —
    no unfiltered pre-scan, no second sample drawn to decide it."""
    calls = []
    real = grader._doubt_reason

    def spy(options, per_board, played, sign, scoring):
        calls.append(len(next(iter(per_board.values()))))
        return real(options, per_board, played, sign, scoring)

    monkeypatch.setattr(grader, '_doubt_reason', spy)
    hands, play = ENDING_HANDS, ENDING_PLAY + ['D2']
    res = grader.grade_play(hands, 3, 'N', 'S', play, 'S', method='single_dummy',
                            num_deals=8, seed=0, expert={'strict': False},
                            escalation=EscalationSettings(factor=2),
                            decisions=[41] if False else None)
    graded = [d for d in res['decisions'] if not d['forced']]
    assert graded
    # consulted exactly once per graded decision, on the 8-deal expert
    # sample, never on an extended one and never on a plain pre-scan
    assert len(calls) == len(graded) and all(n == 8 for n in calls)
    for d in graded:
        assert d['sample']['deals'] in (8, 16)
        assert d['expert']['consistent'] == d['sample']['deals'] or d['expert']['inference'] == 'none'
        assert d['sample']['trigger'] in (None, 'status', 'band')
        assert (d['sample']['trigger'] is not None) == d['sample']['escalated']
