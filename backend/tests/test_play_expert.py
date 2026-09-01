"""Expert opponents (play v1.3): the layout filter and its pieces.

Three kinds of test:

- **Unit** — equivalence classes, who judges whom, the double-dummy trace's
  sign convention, the sequential paired-difference rule (with a synthetic
  solver, so the statistics are exact and no DDS runs).
- **A constructed 3-card ending** — West, holding ♠AK ♥2 over dummy's ♠Q ♥AK,
  led the ♥2 instead of cashing the spades. From West's own view that costs a
  trick on *every* layout, so a layout on which West held ♠AK must be
  rejected, and one on which West held only small cards must be kept: the
  filter's whole point, checked on survivors. The 40 cards before the ending
  are generated (random legal filler play) so the fixture is a full deal.
- **Integration** — `grade_play` / `grade_position` with the toggle: counts,
  the memo, chunked `decisions`, budget exhaustion, the trivial case.
"""

import random

import pytest

from engine.play import grader, state
from engine.play.expert import (
    ExpertSettings, Verdict, VerdictMemo, dd_costs, equivalence_classes,
    expert_layouts, judge, opponent_decisions, opponents_of,
)
from engine.dds_runtime import analyse_plays

# Board 17 (1N by W, N leads) — the grader tests' fixture.
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

ALL_CARDS = [s + r for s in 'SHDC' for r in 'AKQJT98765432']


# --- a full deal around a 3-card ending -------------------------------------
#
# 3NT by South. Declarer's side holds every filler winner (seven clubs in dummy,
# the top diamonds, ♥KQ), so nothing a defender does in the first ten tricks
# can cost their side a trick on any layout: the defence's tricks (♥A, a long
# heart, ♠AK) come whenever they are taken. West's scripted plays are the
# natural ones — the ♥J from AJT987 at trick 1, small hearts on the club run,
# the ♥A on the ♥K (ducking would be squeezed), the ♥T to hold the lead —
# and the scripted declarer lets that ♥T win (declarer's own choice; the
# graded seat is never judged). That leaves this ending with West on lead:
#
#         N: ♠Q ♦AK
#   W: ♠AK ♦2        E: ♠5 ♦43
#         S: ♠JT ♦Q
#
# West leads the ♦2 (index 40). From West's own view — ♠AK ♦2 over dummy's
# ♠Q ♦AK — that costs a trick on *every* layout: cashing the spades takes two,
# the diamond lead lets dummy score ♦AK and then the ♠Q loses only one. So a
# sampled layout on which West held ♠AK must be rejected, while one on which
# West's two unknown cards are small (♠5 ♦3 ♦4) must survive.
ENDING_HANDS = {
    'N': 'Q.KQ3.AK.AKQJT98',
    'E': '987654.42.543.76',
    'S': 'JT32.65.QJT9876.',
    'W': 'AK.AJT987.2.5432',
}
ENDING_PLAY = (
    'HJ HQ H2 H5   CA C6 D6 C2   CK C7 D7 C3   CQ S4 D8 C4 '     # W leads; N wins 1-4
    'CJ S6 D9 C5   CT S7 DT H7   C9 S8 DJ H8   C8 S9 S2 H9 '     # N wins 5-8
    'HK H4 H6 HA   HT H3 D5 S3'                                  # W wins 9 and 10
).split()


@pytest.fixture(scope='module')
def blunder():
    hands, play = ENDING_HANDS, ENDING_PLAY + ['D2']       # index 40: West's blunder
    final = state.replay(hands, 'N', 'S', play)             # legal, and the ending is as drawn
    assert final.remaining_layout() == {'N': 'Q..AK.', 'E': '5..43.', 'S': 'JT..Q.', 'W': 'AK...'}
    assert final.to_play == 'N'
    return hands, play


def west_holdings(layouts, played):
    """West's unplayed cards on each layout, as sets."""
    out = []
    for L in layouts:
        cards = set(state.hand_to_cards(L['W'])) - set(played)
        out.append(cards)
    return out


# --- unit: who had a choice -------------------------------------------------

def test_touching_cards_are_one_choice():
    assert equivalence_classes(['S7', 'S3'], completed_cards=['S6', 'S5', 'S4']) == 1
    assert equivalence_classes(['S7', 'S3'], completed_cards=['S6', 'S5']) == 2


def test_a_card_on_the_table_still_separates_ranks():
    # Holding 79 over a led 8: the 8 is in the current trick, not a completed one.
    assert equivalence_classes(['S9', 'S7'], completed_cards=[]) == 2


def test_different_suits_are_different_choices():
    assert equivalence_classes(['S2', 'H2'], completed_cards=[]) == 2


def test_opponents_of_each_view():
    assert opponents_of('W', 'W') == frozenset({'N', 'S'})       # declarer judges both defenders
    assert opponents_of('E', 'W') == frozenset({'N', 'S'})       # dummy's view is declarer's
    assert opponents_of('N', 'W') == frozenset({'W', 'E'})       # a defender judges declarer + dummy
    assert opponents_of('S', 'W') == frozenset({'W', 'E'})


def test_opponent_decisions_are_the_defenders_choices_latest_first():
    ds = opponent_decisions(HANDS, 'N', 'W', PLAY, upto=12, view='W')
    assert [d.index for d in ds] == sorted((d.index for d in ds), reverse=True)
    assert all(d.seat in ('N', 'S') and d.view == d.seat for d in ds)
    assert 0 in {d.index for d in ds}          # the opening lead was a choice
    # index 2: South followed ♠K from KT3 — three spades, a real choice
    by_index = {d.index: d for d in ds}
    assert by_index[2].card == 'SK' and {'SK', 'ST', 'S3'} <= set(by_index[2].holding)
    assert len(by_index[2].holding) == 13         # the whole hand at that moment, the memo key


def test_a_defenders_partner_is_never_judged():
    ds = opponent_decisions(HANDS, 'N', 'W', PLAY, upto=20, view='N')
    assert {d.seat for d in ds} <= {'W', 'E'}
    assert all(d.view == 'W' for d in ds)      # dummy's cards are declarer's decisions


def test_dd_cost_sign_for_each_side():
    """On the real Board 17 deal dummy's ♥2 at index 16 cost declarer a trick:
    the trace drops 8 -> 7 after it, which is a cost of 1 for the declaring
    side and would be a *gain* for a defender."""
    pos = state.replay(HANDS, 'N', 'W', [])
    trace = analyse_plays([grader._build_deal(HANDS, pos)], [PLAY[:20]])[0]
    assert trace[16] == 8 and trace[17] == 7
    ds = opponent_decisions(HANDS, 'N', 'W', PLAY, upto=20, view='N')
    costs = dd_costs(trace, ds, 'W')
    assert costs[16] == 1
    for d in ds:
        assert costs[d.index] >= 0


# --- unit: the sequential rule, with a synthetic solver ----------------------

def _synthetic_judge(monkeypatch, per_deal, settings=ExpertSettings(), n_layouts=15):
    """Run `judge` on Board 17 index 2 (South's ♠K) with `_solve` replaced by a
    function returning fixed per-board declarer tricks per card from
    `per_deal(k) -> {card: tricks}`."""
    calls = {'n': 0}

    def fake_sample(position, view, constraints, num_deals, rng):
        return [HANDS] * num_deals

    def fake_solve(position, layouts, level):
        per_board = {}
        for _ in layouts:
            k = calls['n']
            calls['n'] += 1
            for card, tricks in per_deal(k).items():
                per_board.setdefault(card, []).append(tricks)
        counts = {c: len(v) for c, v in per_board.items()}
        return {}, {}, counts, per_board

    monkeypatch.setattr(grader, '_sample_layouts', fake_sample)
    monkeypatch.setattr(grader, '_solve', fake_solve)
    ds = opponent_decisions(HANDS, 'N', 'W', PLAY, upto=4, view='W')
    d = next(x for x in ds if x.index == 2)
    v = judge(HANDS, d, level=1, strain='N', declarer='W', play=PLAY,
              all_constraints={}, settings=settings, inner_cap=n_layouts,
              context_key=('t',), memo=VerdictMemo())
    return v, calls['n']


def test_a_coin_flip_is_a_tie_not_a_blunder(monkeypatch):
    # South is a defender: fewer declarer tricks is better for South. ♠K and
    # ♠T come to the same thing half the time each way — a pure guess.
    v, used = _synthetic_judge(monkeypatch, lambda k: {'SK': 7 + k % 2, 'ST': 8 - k % 2, 'S3': 8})
    assert v.consistent and v.reason == 'cap' and used == 15


def test_a_clear_alternative_is_shown_worse_quickly(monkeypatch):
    # ♠T always beats ♠K by a full trick for the defence.
    v, used = _synthetic_judge(monkeypatch, lambda k: {'SK': 8, 'ST': 7, 'S3': 8})
    assert not v.consistent and v.reason == 'shown-worse'
    assert used == 5 and v.gap == 1.0            # settled on the first batch


def test_the_played_card_being_best_settles_early(monkeypatch):
    v, used = _synthetic_judge(monkeypatch, lambda k: {'SK': 7, 'ST': 8, 'S3': 8})
    assert v.consistent and v.reason == 'clear' and used == 5


def test_a_gap_inside_the_noise_is_kept_at_the_cap(monkeypatch):
    # ♠T better on one deal in five: mean gap 0.2, above tol0 but not shown.
    v, used = _synthetic_judge(monkeypatch, lambda k: {'SK': 8, 'ST': 7 if k % 5 == 0 else 8, 'S3': 8})
    assert v.consistent and v.reason == 'cap' and used == 15
    assert 0.15 < v.gap < 0.25


def test_a_gap_inside_the_noise_is_rejected_with_a_larger_sample(monkeypatch):
    # The same 0.2 gap at M = 200 clears tol0 + 2*se (se ~ 0.03).
    v, _ = _synthetic_judge(monkeypatch, lambda k: {'SK': 8, 'ST': 7 if k % 5 == 0 else 8, 'S3': 8},
                            n_layouts=200)
    assert not v.consistent and v.reason == 'shown-worse'


def test_strictness_knobs_change_the_verdict(monkeypatch):
    lenient = ExpertSettings(tolerance=0.9)
    v, _ = _synthetic_judge(monkeypatch, lambda k: {'SK': 8, 'ST': 7, 'S3': 8}, settings=lenient)
    assert v.consistent                          # a whole trick is within a 0.9 margin... plus noise


def test_verdicts_are_memoised():
    memo = VerdictMemo()
    ds = opponent_decisions(HANDS, 'N', 'W', PLAY, upto=4, view='W')
    d = next(x for x in ds if x.index == 2)
    kw = dict(level=1, strain='N', declarer='W', play=PLAY, all_constraints={},
              settings=ExpertSettings(), inner_cap=8, context_key=('m',), memo=memo)
    a = judge(HANDS, d, **kw)
    assert len(memo) == 1
    b = judge(HANDS, d, **kw)
    assert a is b


def test_memo_is_bounded():
    memo = VerdictMemo(max_entries=3)
    for i in range(5):
        memo.put(('k', i), Verdict(True, 0, 0, 0.3, 'clear'))
    assert len(memo) == 3 and memo.get(('k', 0)) is None and memo.get(('k', 4))


# --- the constructed ending ----------------------------------------------------

def _ending_survivors(blunder, settings, num_deals=30, seed=0):
    hands, play = blunder
    position = state.replay(hands, 'N', 'S', play)      # trick 11, dummy to play
    assert position.to_play == 'N' and position.index == 41
    layouts, stats = expert_layouts(
        position, 'S', {}, {}, num_deals, settings, random.Random(seed),
        level=3, context_key=('ending', seed), memo=VerdictMemo())
    return layouts, stats, play


@pytest.mark.parametrize('strict', [False, True])
def test_layouts_where_west_held_the_top_spades_are_rejected(blunder, strict):
    layouts, stats, play = _ending_survivors(blunder, ExpertSettings(strict=strict))
    assert stats.inference == 'filtered' and stats.consistent == len(layouts) > 0
    for held in west_holdings(layouts, play):
        assert not {'SA', 'SK'} <= held, held
    # ...and the filter did reject something: the unfiltered sampler deals
    # West ♠AK on a fair share of layouts, so more were examined than kept.
    assert stats.sampled > stats.consistent


def test_the_unfiltered_sample_does_deal_west_the_top_spades(blunder):
    hands, play = blunder
    position = state.replay(hands, 'N', 'S', play)
    layouts = grader._sample_layouts(position, 'S', {}, 60, random.Random(0))
    assert any({'SA', 'SK'} <= h for h in west_holdings(layouts, play))


def test_fast_accept_never_runs_a_judgement_on_a_costless_layout(blunder):
    """In default mode a layout on which the ♥2 lost nothing double-dummy is
    accepted without an inner sample; strict judges every one."""
    _, fast, _ = _ending_survivors(blunder, ExpertSettings())
    _, strict, _ = _ending_survivors(blunder, ExpertSettings(strict=True))
    assert fast.traced > 0 and strict.traced == 0
    assert strict.judged + strict.memo_hits >= strict.sampled       # one per examined layout at least
    assert fast.judged + fast.memo_hits < fast.sampled               # most passed on the trace alone


def test_budget_exhaustion_falls_back_to_the_unfiltered_pool(blunder):
    """Pin ♠AK into West's hand: every layout is the blunder layout, nothing
    survives, and the grader gets the unfiltered pool with the marker."""
    hands, play = blunder
    position = state.replay(hands, 'N', 'S', play)
    pinned = {'fixed_cards': {'W': ['SA', 'SK']}}
    layouts, stats = expert_layouts(
        position, 'S', pinned, pinned, 10, ExpertSettings(budget=3), random.Random(1),
        level=3, context_key=('none',), memo=VerdictMemo())
    assert stats.inference == 'none' and stats.consistent == 0
    assert len(layouts) == 10


# --- integration through the grader -------------------------------------------

def test_grade_play_reports_expert_counts_per_decision():
    memo = VerdictMemo()
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', num_deals=8, seed=0,
                            expert=ExpertSettings(), memo=memo, decisions=[1, 3])
    assert [d['index'] for d in res['decisions']] == [1, 3]
    assert res['expert'] == ExpertSettings().__dict__
    for d in res['decisions']:
        e = d['expert']
        assert e['consistent'] == 8 and e['sampled'] >= 8 and e['traced'] >= 8
        assert e['inference'] == 'filtered'
        assert e['threshold'] == pytest.approx(0.10 + 2.0 * 0.6 / 8 ** 0.5, abs=1e-3)
    assert len(memo) > 0


def test_expert_settings_accept_a_dict():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY[:8], 'N', num_deals=8, seed=0,
                            expert={'strict': True, 'tolerance': 0.2}, memo=VerdictMemo())
    assert res['expert']['strict'] is True and res['expert']['tolerance'] == 0.2


def test_the_opening_lead_has_nothing_to_judge():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY[:1], 'N', num_deals=8, seed=0,
                            expert=ExpertSettings(), memo=VerdictMemo())
    lead = res['decisions'][0]
    assert lead['index'] == 0 and lead['expert']['inference'] == 'trivial'
    assert lead['expert']['traced'] == 0 and lead['expert']['judged'] == 0


def test_grade_position_carries_expert_stats():
    res = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:8], num_deals=8, seed=0,
                                expert=ExpertSettings(), memo=VerdictMemo())
    assert res['expert']['consistent'] == 8
    plain = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:8], num_deals=8, seed=0)
    assert plain['expert'] is None


def test_decisions_chunk_returns_only_those_indices():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', num_deals=5, seed=0,
                            decisions=[1, 3, 5])
    assert [d['index'] for d in res['decisions']] == [1, 3, 5]
    assert res['summary']['decisions'] == 3


def test_expert_grading_is_deterministic():
    kw = dict(num_deals=8, seed=0, expert=ExpertSettings(), decisions=[10, 12])
    a = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', memo=VerdictMemo(), **kw)
    b = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', memo=VerdictMemo(), **kw)
    assert a['decisions'] == b['decisions']
