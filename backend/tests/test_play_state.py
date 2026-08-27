"""Pure replay: trick winners, legality, and the bookkeeping the grader stands on.

Board 17 (a real BBO hand from the source project) is the fixture — 1NT by West,
North on lead, nine complete tricks recorded plus a lead to the tenth. It
exercises the interesting cases on its own: three seats show out of spades at
trick 8, and the recorded play ends mid-trick.
"""

import pytest

from engine.play import state

# 1N by W. Dealer N. Opening leader N.
HANDS = {
    'N': '9872.K85.AJ542.5',
    'E': 'QJ6.A632.KQ.J976',
    'S': 'KT3.JT7.87.KQ843',
    'W': 'A54.Q94.T963.AT2',
}
PLAY = (
    'S9 SJ SK S5 '     # 1: S wins
    'ST S4 S2 SQ '     # 2: E wins
    'C6 C4 CT C5 '     # 3: W wins
    'D3 D5 DQ D7 '     # 4: E wins
    'H2 HT HQ HK '     # 5: N wins
    'S8 S6 S3 SA '     # 6: W wins
    'H4 H8 H3 H7 '     # 7: N wins
    'S7 C7 C3 C2 '     # 8: N wins (E, S and W all show out of spades)
    'DA DK D8 D6 '     # 9: N wins
    'DJ'               # 10: N leads
).split()


# --- trick_winner -----------------------------------------------------------

def test_highest_in_led_suit_wins():
    assert state.trick_winner(['S9', 'SJ', 'SK', 'S5'], 'N', None) == 'S'


def test_trump_beats_side_suit():
    assert state.trick_winner(['SA', 'SK', 'H2', 'S3'], 'N', 'H') == 'S'


def test_higher_trump_wins():
    assert state.trick_winner(['SA', 'H2', 'H5', 'S3'], 'N', 'H') == 'S'


def test_off_suit_does_not_win():
    # DA is neither the suit led nor a trump.
    assert state.trick_winner(['S9', 'DA', 'S5', 'S3'], 'N', 'H') == 'N'


def test_notrump_ignores_the_would_be_trump():
    # W leads S9, N discards HA, E plays ST, S plays S3 -> the ten wins.
    assert state.trick_winner(['S9', 'HA', 'ST', 'S3'], 'W', None) == 'E'
    # ...and the same trick in hearts is won by the ace.
    assert state.trick_winner(['S9', 'HA', 'ST', 'S3'], 'W', 'H') == 'N'


def test_trick_winner_wants_four_cards():
    with pytest.raises(ValueError):
        state.trick_winner(['S9', 'SJ'], 'N', None)


# --- replay -----------------------------------------------------------------

def test_initial_position():
    pos = state.replay(HANDS, 'N', 'W')
    assert pos.declarer == 'W' and pos.dummy == 'E'
    assert pos.opening_leader == 'N' and pos.to_play == 'N'
    assert pos.trump is None
    assert pos.index == 0 and pos.trick_number == 1
    assert pos.tricks_won == {'NS': 0, 'EW': 0}
    assert all(len(pos.remaining[s]) == 13 for s in state.SEATS)


def test_after_trick_one():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:4])
    assert pos.index == 4 and pos.trick_number == 2
    assert pos.to_play == 'S' and pos.trick_leader == 'S'      # SK won it
    assert pos.tricks_won == {'NS': 1, 'EW': 0}
    assert pos.declarer_tricks_won == 0                        # W/E won nothing
    assert pos.tricks[0].winner == 'S'
    assert pos.current_trick == []


def test_mid_trick():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:2])
    assert pos.current_trick == ['S9', 'SJ']
    assert pos.to_play == 'S'
    assert pos.led_suit == 'S'
    assert pos.remaining_tricks == 13


def test_final_position():
    pos = state.replay(HANDS, 'N', 'W', PLAY)
    assert pos.index == 37
    assert pos.completed_tricks == 9 and pos.trick_number == 10
    assert pos.tricks_won == {'NS': 5, 'EW': 4}
    assert pos.declarer_tricks_won == 4          # W is declarer, so E-W's four
    assert pos.remaining_tricks == 4
    assert pos.to_play == 'E'
    assert not pos.complete


def test_remaining_and_played_cards_partition_the_hand():
    pos = state.replay(HANDS, 'N', 'W', PLAY)
    for seat in state.SEATS:
        assert sorted(pos.remaining[seat] + pos.played_by[seat]) == sorted(
            pos.original[seat])
    assert pos.remaining_layout()['N'] == '.5.42.'


def test_declarer_tricks_won_is_the_declarer_side_not_ns():
    """N-S are the defenders here; the two must not be confused."""
    pos = state.replay(HANDS, 'N', 'W', PLAY)
    assert pos.tricks_won['EW'] == pos.declarer_tricks_won


def test_show_outs_recorded():
    pos = state.replay(HANDS, 'N', 'W', PLAY)
    assert pos.show_outs['E'] == {'S'}
    assert pos.show_outs['S'] == {'S'}
    assert pos.show_outs['W'] == {'S'}
    assert pos.show_outs['N'] == set()


def test_show_out_appears_only_once_the_discard_is_played():
    before = state.replay(HANDS, 'N', 'W', PLAY[:29])   # E has not discarded yet
    assert before.show_outs['E'] == set()
    after = state.replay(HANDS, 'N', 'W', PLAY[:30])
    assert after.show_outs['E'] == {'S'}


def test_trump_contract_tracks_ruffs():
    pos = state.replay(HANDS, 'H', 'W', ['S9', 'SJ', 'SK', 'S5'])
    assert pos.trump == 'H'
    assert pos.tricks[0].winner == 'S'


# --- legality ---------------------------------------------------------------

def test_legal_cards_is_the_whole_hand_on_lead():
    pos = state.replay(HANDS, 'N', 'W')
    assert len(state.legal_cards(pos)) == 13


def test_legal_cards_must_follow_suit():
    pos = state.replay(HANDS, 'N', 'W', ['S9'])
    assert state.legal_cards(pos) == ['SQ', 'SJ', 'S6']      # E's spades only


def test_legal_cards_is_the_whole_hand_when_void():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:29])           # S7 led, E has no spade
    assert len(state.legal_cards(pos)) == 6


def test_card_not_in_hand_names_the_index():
    # HK belongs to North; East is on turn at play[1].
    with pytest.raises(ValueError, match=r'play\[1\].*does not hold'):
        state.replay(HANDS, 'N', 'W', ['S9', 'HK'])


def test_card_held_by_someone_else():
    with pytest.raises(ValueError, match=r'play\[0\]'):
        state.replay(HANDS, 'N', 'W', ['SA'])                # SA is West's, N is on lead


def test_revoke_is_rejected():
    with pytest.raises(ValueError, match=r'play\[1\].*follow suit'):
        state.replay(HANDS, 'N', 'W', ['S9', 'HA'])


def test_discard_allowed_once_void():
    pos = state.replay(HANDS, 'N', 'W', PLAY[:30])
    assert pos.played_by['E'][-1] == 'C7'


def test_bad_card_syntax():
    with pytest.raises(ValueError, match=r'play\[0\]'):
        state.replay(HANDS, 'N', 'W', ['XY'])


def test_ten_is_normalised():
    pos = state.replay(HANDS, 'N', 'W', ['s9', 'sJ', 'sk', 's5'])
    assert pos.tricks[0].cards == ['S9', 'SJ', 'SK', 'S5']


def test_play_longer_than_the_deal():
    with pytest.raises(ValueError, match='52'):
        state.replay(HANDS, 'N', 'W', PLAY * 2)


# --- hand validation --------------------------------------------------------

def test_missing_seat():
    with pytest.raises(ValueError, match='missing seat'):
        state.replay({k: v for k, v in HANDS.items() if k != 'E'}, 'N', 'W')


def test_wrong_card_count():
    bad = dict(HANDS, N='987.K85.AJ542.5')
    with pytest.raises(ValueError, match='12 cards'):
        state.replay(bad, 'N', 'W')


def test_duplicate_card_across_hands():
    bad = dict(HANDS, N='9872.K85.AJ542.5', S='KT3.JT7.87.KQ842')
    with pytest.raises(ValueError, match='can only be in one hand'):
        state.replay(bad, 'N', 'W')


def test_bad_strain_and_declarer():
    with pytest.raises(ValueError, match='strain'):
        state.replay(HANDS, 'X', 'W')
    with pytest.raises(ValueError, match='declarer'):
        state.replay(HANDS, 'N', 'X')


# --- walk -------------------------------------------------------------------

def test_walk_yields_one_position_per_card():
    steps = list(state.walk(HANDS, 'N', 'W', PLAY))
    assert len(steps) == len(PLAY)
    for i, (pos, card) in enumerate(steps):
        assert pos.index == i
        assert card == PLAY[i]
        assert card in state.legal_cards(pos)


def test_walk_positions_alternate_seats_within_a_trick():
    steps = list(state.walk(HANDS, 'N', 'W', PLAY[:4]))
    assert [p.to_play for p, _ in steps] == ['N', 'E', 'S', 'W']
    assert [len(p.current_trick) for p, _ in steps] == [0, 1, 2, 3]
