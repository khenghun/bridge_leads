"""The play grader: DDS perspective, visibility, inferred constraints, determinism.

Two fixtures:

- `HANDS` / `PLAY` — Board 17 (1NT by West), a real recorded hand with show-outs
  and forced plays. Used for the walk-the-whole-play behaviour.
- `WIDE_OPEN` — a constructed 3NT where West holds ♥AKQJT against 11 top tricks.
  Double-dummy the answer is not a matter of taste: a heart lead beats it, any
  other lead does not. That makes it a usable oracle for "the grader picks the
  obviously best card" and for the declarer/defender trick flip.

Deal counts are kept small (5-10) on purpose — these tests exercise plumbing,
not statistics, and every extra deal is a DDS solve per decision.
"""

import random

import pytest

from engine.play import grader, state

# --- Board 17: 1N by W, N on lead ------------------------------------------
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

# --- Constructed 3NT by S; W leads. W's hearts are five cashing tricks, S/N
#     hold eleven top tricks in the other three suits.
WIDE_OPEN = {
    'N': 'T98.765.JT9.T987',
    'E': '765.432.8765.654',
    'S': 'AKQJ.98.AKQ.AKQJ',
    'W': '432.AKQJT.432.32',
}


# --- helpers ----------------------------------------------------------------

def test_card_to_str_undoes_endplays_unicode():
    assert grader.card_to_str('♠K') == 'SK'
    assert grader.card_to_str('♦T') == 'DT'


def test_classify_thresholds():
    assert grader.classify(-0.5, is_best=True) == 'optimal'
    assert grader.classify(0.0, False) == 'optimal'
    assert grader.classify(-0.05, False) == 'optimal'
    assert grader.classify(-0.2, False) == 'good'
    assert grader.classify(-0.3, False) == 'good'
    assert grader.classify(-0.9, False) == 'suboptimal'


def test_tricks_needed_is_per_side():
    assert grader.tricks_needed_for('declarer', 3) == 9
    assert grader.tricks_needed_for('defender', 3) == 5
    assert grader.tricks_needed_for('declarer', 1) == 7
    assert grader.tricks_needed_for('defender', 1) == 7


# --- double_dummy on a known deal ------------------------------------------

def test_double_dummy_picks_the_only_winning_lead():
    """W must cash hearts; double dummy says so without ambiguity."""
    res = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', [], method='double_dummy')
    assert res['to_play'] == 'W' and res['role'] == 'defender'
    assert res['num_deals'] == 1
    best = res['options'][0]
    assert best['card'][0] == 'H'
    assert best['tricks'] == 5.0            # five heart tricks, contract down one
    assert best['success_rate'] == 1.0      # defeat rate for a defender
    # Every heart is equally good, and nothing else is.
    tops = [o['card'] for o in res['options'] if o['tricks'] == 5.0]
    assert set(tops) == {'HA', 'HK', 'HQ', 'HJ', 'HT'}


def test_double_dummy_tricks_are_whole_numbers():
    res = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:4], method='double_dummy')
    assert res['options']
    for opt in res['options']:
        assert opt['tricks'] == int(opt['tricks'])
        assert opt['success_rate'] in (0.0, 1.0)


def test_defender_perspective_flips_the_trick_count():
    """The same position, priced for each side, must sum to 13."""
    lead = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', [], method='double_dummy')
    after = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', ['HA'],
                                  method='double_dummy')
    assert after['to_play'] == 'N' and after['view'] == 'S'   # dummy plays, declarer decides
    assert after['role'] == 'declarer'
    # W cashed the ace: declarer is held to 8, the defence to 5, either way round.
    assert lead['options'][0]['tricks'] == 5.0
    assert max(o['tricks'] for o in after['options']) == 8.0


def test_declarer_success_rate_is_the_make_rate():
    res = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', ['HA'],
                                method='double_dummy')
    # 8 tricks is one short of 3NT, so nothing dummy can play makes it.
    assert all(o['success_rate'] == 0.0 for o in res['options'])


# --- single_dummy shape ------------------------------------------------------

def test_single_dummy_return_shape():
    res = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:4],
                                method='single_dummy', num_deals=8, seed=0)
    assert res['num_deals'] == 8
    assert res['to_play'] == 'S'
    assert res['role'] == 'defender'
    assert res['view'] == 'S'
    assert res['visible'] == ['S', 'E']           # own hand + dummy
    assert res['tricks_won'] == {'NS': 1, 'EW': 0}
    assert set(res['legal_cards']) == set(o['card'] for o in res['options'])
    for opt in res['options']:
        assert 0.0 <= opt['tricks'] <= 13.0
        assert 0.0 <= opt['success_rate'] <= 1.0
    tricks = [o['tricks'] for o in res['options']]
    assert tricks == sorted(tricks, reverse=True)  # best first


def test_options_only_contain_legal_cards():
    res = grader.grade_position(HANDS, 1, 'N', 'W', ['S9'],
                                method='single_dummy', num_deals=5, seed=1)
    assert sorted(o['card'] for o in res['options']) == sorted(['SQ', 'SJ', 'S6'])


def test_deterministic_with_a_seed():
    kw = dict(method='single_dummy', num_deals=6, seed=0)
    a = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:8], **kw)
    b = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:8], **kw)
    assert a == b


def test_complete_play_has_nothing_left_to_choose():
    with pytest.raises(ValueError, match='complete'):
        grader.grade_position(WIDE_OPEN, 3, 'N', 'S', _full_play(),
                              method='double_dummy')


def test_no_play_at_all_grades_nothing_for_a_seat_yet_to_play():
    res = grader.grade_play(WIDE_OPEN, 3, 'N', 'S', [], 'S',
                            method='double_dummy')
    assert res['decisions'] == []
    assert res['summary'] == {'decisions': 0, 'graded': 0, 'optimal': 0,
                              'good': 0, 'suboptimal': 0,
                              'total_trick_loss': 0.0, 'avg_trick_loss': 0.0,
                              'total_score_loss': 0.0, 'total_imp_loss': 0.0}


def _full_play():
    """A legal 52-card play of WIDE_OPEN: each seat follows suit, lowest first."""
    play = []
    pos = state.replay(WIDE_OPEN, 'N', 'S', play)
    while not pos.complete:
        play.append(state.legal_cards(pos)[-1])
        pos = state.replay(WIDE_OPEN, 'N', 'S', play)
    return play


# --- visibility --------------------------------------------------------------

def test_opening_lead_hides_dummy():
    pos = state.replay(HANDS, 'N', 'W', [])
    assert grader.visible_seats(pos, 'N') == ['N']
    after = state.replay(HANDS, 'N', 'W', ['S9'])
    assert grader.visible_seats(after, 'S') == ['S', 'E']


def test_declarer_always_sees_dummy():
    pos = state.replay(HANDS, 'N', 'W', [])
    assert grader.visible_seats(pos, 'W') == ['W', 'E']
    assert grader.visible_seats(pos, 'E') == ['W', 'E']


def test_opening_lead_samples_dummy():
    """At trick 1 the leader has not seen dummy, so dummy must vary."""
    pos = state.replay(HANDS, 'N', 'W', [])
    layouts = grader._sample_layouts(pos, 'N', None, 12, random.Random(0))
    assert len(layouts) == 12
    assert all(layout['N'] == '9872.K85.AJ542.5' for layout in layouts)
    assert len({layout['E'] for layout in layouts}) > 1
    # The actual dummy is one candidate among many, not a given.
    assert sum(1 for lay in layouts if lay['E'] == HANDS['E']) < len(layouts)


def test_after_the_lead_dummy_is_pinned():
    pos = state.replay(HANDS, 'N', 'W', ['S9'])
    layouts = grader._sample_layouts(pos, 'S', None, 6, random.Random(0))
    assert all(layout['E'] == HANDS['E'] for layout in layouts)
    assert all(layout['S'] == HANDS['S'] for layout in layouts)
    assert len({layout['W'] for layout in layouts}) > 1


# --- inferred constraints ----------------------------------------------------

def test_played_cards_are_pinned_into_unseen_hands():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:8])
    inferred = grader.infer_constraints(pos, 'N')
    assert set(inferred['fixed_cards']['W']) == {'S5', 'S4'}
    assert set(inferred['fixed_cards']['S']) == {'SK', 'ST'}
    # Dummy is visible to N, so it goes in whole rather than card by card.
    assert set(inferred['fixed_cards']['E']) == set(state.hand_to_cards(HANDS['E']))


def test_show_out_caps_the_suit_length():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:32])       # trick 8 complete
    inferred = grader.infer_constraints(pos, 'N')
    assert inferred['suit_length']['W']['S'] == (3, 3)
    assert inferred['suit_length']['S']['S'] == (3, 3)


def test_show_out_constraint_actually_binds_the_sampler():
    """Every sampled layout must give the shown-out seats exactly the spades
    they played — nothing else could have produced that discard."""
    pos = state.replay(HANDS, 'N', 'W', PLAY[:32])
    layouts = grader._sample_layouts(pos, 'N', None, 10, random.Random(0))
    assert len(layouts) == 10
    for layout in layouts:
        w_spades = layout['W'].split('.')[0]
        s_spades = layout['S'].split('.')[0]
        assert sorted(w_spades) == sorted('A54'), layout
        assert sorted(s_spades) == sorted('KT3'), layout
        # ...and every card those seats played is where the play says it was.
        for seat, cards in (('W', ['CT', 'C2', 'SA']), ('S', ['C4', 'C3', 'HT'])):
            hand = set(state.hand_to_cards(layout[seat]))
            assert set(cards) <= hand, (seat, layout[seat])


def test_user_constraints_are_anded_with_the_play():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:8])
    inferred = grader.infer_constraints(pos, 'N', {'hcp': {'W': (12, 14)}})
    assert inferred['hcp'] == {'W': (12, 14)}
    assert 'W' in inferred['fixed_cards']


def test_constraint_contradicting_a_show_out_raises():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:32])
    with pytest.raises(ValueError, match='showed out'):
        grader.infer_constraints(pos, 'N', {'suit_length': {'W': {'S': (4, 5)}}})


def test_constraint_on_a_visible_seat_raises():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:8])
    with pytest.raises(ValueError, match='visible'):
        grader.infer_constraints(pos, 'N', {'hcp': {'E': (10, 12)}})


def test_pinning_a_card_someone_else_played_raises():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:8])
    with pytest.raises(ValueError, match='can only be in one hand'):
        grader._sample_layouts(pos, 'N', {'fixed_cards': {'S': ['S5']}}, 4,
                               random.Random(0))


def test_impossible_hcp_constraint_raises():
    pos = state.replay(HANDS, 'N', 'W', [])
    with pytest.raises(ValueError, match='HCP'):
        grader._sample_layouts(pos, 'N', {'hcp': {'E': (30, 40), 'S': (30, 40)}},
                               4, random.Random(0))


# --- grade_play --------------------------------------------------------------

def test_grade_play_declarer_covers_dummys_cards():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', method='double_dummy')
    assert res['seat'] == 'W' and res['role'] == 'declarer'
    assert res['visible'] == ['W', 'E']
    assert res['tricks_needed'] == 7
    hands = {d['hand'] for d in res['decisions']}
    assert hands == {'W', 'E'}                       # declarer and dummy
    assert res['summary']['decisions'] == len(res['decisions']) == 18


def test_grade_play_defender_only_grades_that_seat():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'N', method='double_dummy')
    assert res['role'] == 'defender' and res['visible'] == ['N', 'E']
    assert {d['hand'] for d in res['decisions']} == {'N'}
    assert res['summary']['decisions'] == 10         # N played 10 cards


def test_grade_play_decision_fields():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'N', method='double_dummy')
    first = res['decisions'][0]
    assert first['index'] == 0 and first['trick'] == 1 and first['position'] == 0
    assert first['card'] == 'S9' and first['hand'] == 'N'
    assert first['status'] in ('optimal', 'good', 'suboptimal')
    assert first['diff'] == pytest.approx(
        first['actual_tricks'] - first['best_tricks'], abs=1e-6)
    assert first['card'] in [o['card'] for o in first['options']]
    assert first['best_cards']
    assert first['best_tricks'] == max(o['tricks'] for o in first['options'])


def test_forced_decisions_are_reported_not_solved():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', method='double_dummy')
    forced = [d for d in res['decisions'] if d['forced']]
    assert forced, 'Board 17 has singleton-follow positions for E-W'
    for d in forced:
        assert d['status'] == 'forced'
        assert d['options'] == [] and d['best_cards'] == []
        assert d['actual_tricks'] is None and d['diff'] is None
        pos = state.replay(HANDS, 'N', 'W', PLAY[:d['index']])
        assert len(state.legal_cards(pos)) == 1
    assert res['summary']['graded'] + len(forced) == res['summary']['decisions']


def test_grade_position_reports_forced_without_solving():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', method='double_dummy')
    index = next(d['index'] for d in res['decisions'] if d['forced'])
    at = grader.grade_position(HANDS, 1, 'N', 'W', PLAY[:index],
                               method='single_dummy', num_deals=100)
    assert at['forced'] is True
    assert at['options'] == [] and at['num_deals'] == 0
    assert len(at['legal_cards']) == 1


def test_summary_counts_add_up():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'N',
                            method='single_dummy', num_deals=5, seed=0)
    s = res['summary']
    assert s['optimal'] + s['good'] + s['suboptimal'] == s['graded']
    assert s['total_trick_loss'] >= 0
    assert s['avg_trick_loss'] == pytest.approx(
        s['total_trick_loss'] / s['graded'], abs=0.01)
    assert res['num_deals'] == 5


def test_grade_play_is_deterministic_with_a_seed():
    kw = dict(method='single_dummy', num_deals=5, seed=0)
    a = grader.grade_play(HANDS, 1, 'N', 'W', PLAY[:12], 'N', **kw)
    b = grader.grade_play(HANDS, 1, 'N', 'W', PLAY[:12], 'N', **kw)
    assert a == b


def test_grading_dummy_is_rejected():
    with pytest.raises(ValueError, match='dummy'):
        grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'E', method='double_dummy')


def test_bad_method_is_rejected():
    with pytest.raises(ValueError, match='method'):
        grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'N', method='triple_dummy')


def test_malformed_play_is_rejected_before_any_solving():
    with pytest.raises(ValueError, match=r'play\[1\]'):
        grader.grade_play(HANDS, 1, 'N', 'W', ['S9', 'HK'], 'N',
                          method='double_dummy')


def test_no_play_yet_grades_the_opening_lead_only():
    res = grader.grade_play(WIDE_OPEN, 3, 'N', 'S', ['HA'], 'W',
                            method='double_dummy')
    assert len(res['decisions']) == 1
    d = res['decisions'][0]
    assert d['card'] == 'HA'
    assert d['status'] == 'optimal'          # the one lead that beats 3NT
    assert d['actual_tricks'] == 5.0


# --- v1.2: cost in points and IMPs ------------------------------------------

def test_options_are_priced_in_points_and_imps_from_the_defenders_view():
    """WIDE_OPEN, W on lead, nobody vul: a heart lead beats 3NT (+50 for the
    defence), anything else lets it make with two overtricks (-460). The swing
    between them is 510 points = 11 IMPs, charged per deal against the best."""
    res = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', [], method='double_dummy')
    by_card = {o['card']: o for o in res['options']}
    assert by_card['HA']['score'] == 50.0
    assert by_card['HA']['imps'] == 0.0
    assert by_card['S2']['score'] == -460.0
    assert by_card['S2']['imps'] == -11.0


def test_vulnerability_changes_the_price_not_the_tricks():
    flat = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', [], method='double_dummy')
    vul = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', [], method='double_dummy',
                                vul='ns')
    f = {o['card']: o for o in flat['options']}
    v = {o['card']: o for o in vul['options']}
    assert f['S2']['tricks'] == v['S2']['tricks']
    # Vulnerable: down one is +100 to the defence, 3NT+2 is -660; 760 = 13 IMPs.
    assert v['HA']['score'] == 100.0
    assert v['S2']['score'] == -660.0
    assert v['S2']['imps'] == -13.0


def test_declarer_view_prices_from_declarers_side():
    """After W cashes the ace, declarer is held to 8: every dummy card scores
    -50 for declarer and none is an IMP swing against another."""
    res = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', ['HA'], method='double_dummy')
    assert res['role'] == 'declarer'
    assert {o['score'] for o in res['options']} == {-50.0}
    assert {o['imps'] for o in res['options']} == {0.0}


def test_doubled_contracts_are_priced_doubled():
    """The price comes from engine.scoring (endplay), so check against it."""
    from engine.scoring import declarer_score
    res = grader.grade_position(WIDE_OPEN, 3, 'N', 'S', [], method='double_dummy',
                                penalty='doubled')
    by_card = {o['card']: o for o in res['options']}
    # Defender's view: the negative of declarer's score.
    assert by_card['HA']['score'] == -declarer_score(3, 'N', 'S', 8, 'none', 'doubled')
    assert by_card['S2']['score'] == -declarer_score(3, 'N', 'S', 11, 'none', 'doubled')
    assert by_card['HA']['score'] == 100.0        # 3NTx down one, not vul
    assert by_card['S2']['score'] == -750.0       # 3NTx+2 not vul: 200+300+50+2x100


def test_grade_play_decision_and_summary_carry_costs():
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', method='double_dummy')
    graded = [d for d in res['decisions'] if not d['forced']]
    assert graded
    for d in graded:
        assert d['best_score'] is not None and d['actual_score'] is not None
        assert d['score_diff'] == pytest.approx(d['actual_score'] - d['best_score'], abs=0.11)
        assert d['imp_diff'] <= 0
        played = next(o for o in d['options'] if o['card'] == d['card'])
        assert d['imp_diff'] == played['imps']
        assert d['options'][0]['imps'] == 0.0            # the best card is the datum
    for d in res['decisions']:
        if d['forced']:
            assert d['imp_diff'] is None and d['score_diff'] is None
    s = res['summary']
    assert s['total_imp_loss'] == pytest.approx(
        sum(max(0.0, -d['imp_diff']) for d in graded), abs=0.01)
    assert s['total_score_loss'] >= 0
    # A trick lost that does not change the result costs no IMPs; one that does
    # costs something — so the two totals need not move together.
    assert s['total_trick_loss'] >= 0


def test_status_is_demoted_by_imps_but_never_promoted():
    c = grader.classify_with_imps
    # Trick thresholds alone, IMPs quiet: unchanged from classify.
    assert c(-0.05, False, 0.0) == 'optimal'
    assert c(-0.2, False, 0.0) == 'good'
    assert c(-0.5, False, 0.0) == 'suboptimal'
    # The 7NT case: a twentieth of a trick, a whole IMP -> good, not optimal.
    assert c(-0.05, False, -1.0) == 'good'
    # Two IMPs or more is suboptimal whatever the tricks said.
    assert c(-0.05, False, -2.0) == 'suboptimal'
    assert c(-0.2, False, -2.5) == 'suboptimal'
    # Just under the thresholds: nothing happens.
    assert c(-0.05, False, -0.49) == 'optimal'
    assert c(-0.2, False, -1.99) == 'good'
    # The best card is optimal by definition; no IMP data means no demotion.
    assert c(0.0, True, 0.0) == 'optimal'
    assert c(-0.05, False, None) == 'optimal'


def test_grade_play_status_reflects_imps(monkeypatch):
    """Grade the constructed 3NT with W leading a spade: one trick short of
    beating it double-dummy would read 'suboptimal' either way, so check the
    plumbing on the numbers instead — the recorded status must equal
    classify_with_imps of the recorded diff and imp_diff."""
    res = grader.grade_play(HANDS, 1, 'N', 'W', PLAY, 'W', method='double_dummy')
    for d in res['decisions']:
        if d['forced']:
            continue
        assert d['status'] == grader.classify_with_imps(
            d['diff'], d['card'] in d['best_cards'], d['imp_diff'])
