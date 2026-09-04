"""The grader's direct DDS struct paths must equal endplay's reference paths.

`_build_deal` writes the board struct straight from the layout and position,
and `_collect` reads DDS's futureTricks arrays directly; both replaced
endplay's PBN-parse-and-replay / Card-iterator code for speed (play v1.4).
A wrong bit here would silently skew every grade, so each is pinned against
the reference implementation on many random positions.
"""
import random

from endplay.types import Deal

from engine.play import grader
from engine.play.state import SEATS, replay

FULL = {'N': 'AK8.Q95.J982.Q43', 'E': 'QJT9.K84.KQ7.J97',
        'S': '7652.AJT7.A6.AK2', 'W': '43.632.T543.T865'}


def _random_play(hands, strain, declarer, rng, n):
    """A random legal line of `n` cards on `hands`."""
    play = []
    for _ in range(n):
        pos = replay(hands, strain, declarer, play)
        play.append(rng.choice(grader.legal_cards(pos)))
    return play


def _reference_deal(layout, position):
    deal = Deal('N:' + ' '.join(layout[s] for s in SEATS))
    deal.trump = grader.STRAIN_DENOM[position.strain]
    deal.first = grader.LETTER_PLAYER[position.opening_leader]
    for card in position.history:
        deal.play(card)
    return deal


def _reference_collect(position, boards):
    legal = set(grader.legal_cards(position))
    won = position.declarer_tricks_won
    remaining = position.remaining_tricks
    on_declarer_side = position.to_play in position.declarer_side
    out = {}
    for board in boards:
        for card, tricks in board:
            name = grader.card_to_str(card)
            if name not in legal:
                continue
            out.setdefault(name, []).append(
                won + tricks if on_declarer_side else won + (remaining - tricks))
    return out


def _struct(deal):
    """The DDS-visible content of a board: endplay's replay leaves the suit of
    a cleared trick slot behind (DDS ignores a slot whose rank is 0), so the
    table is compared as (suit, rank) pairs of the occupied slots only."""
    d = deal._data
    table = [(d.currentTrickSuit[k], d.currentTrickRank[k])
             for k in range(3) if d.currentTrickRank[k]]
    return (d.trump, d.first, table, [list(d.remainCards[h]) for h in range(4)])


def test_direct_deal_struct_matches_the_replayed_deal():
    rng = random.Random(7)
    for strain in ('N', 'S', 'H', 'D', 'C'):
        for declarer in SEATS:
            for n in (0, 1, 2, 3, 4, 7, 13, 26, 40, 51):
                play = _random_play(FULL, strain, declarer, rng, n)
                pos = replay(FULL, strain, declarer, play)
                mine = grader._build_deal(FULL, pos)
                ref = _reference_deal(FULL, pos)
                assert _struct(mine) == _struct(ref), (strain, declarer, play)


def test_dds_solves_direct_and_replayed_boards_identically():
    rng = random.Random(3)
    positions = []
    for n in (0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 14, 22, 33, 45):
        play = _random_play(FULL, 'H', 'W', rng, n)
        positions.append(replay(FULL, 'H', 'W', play))
    mine = grader.solve_all([grader._build_deal(FULL, p) for p in positions])
    ref = grader.solve_all([_reference_deal(FULL, p) for p in positions])
    for pos, a, b in zip(positions, mine, ref):
        assert grader._collect(pos, [a]) == grader._collect(pos, [b])
        assert list(a) == list(b)


def test_direct_deal_struct_accepts_card_lists_too():
    pos = replay(FULL, 'N', 'S', ['H2', 'H5', 'H4', 'H7'])
    as_lists = {s: pos.original[s] for s in SEATS}
    assert bytes(grader._build_deal(as_lists, pos)._data) == \
        bytes(grader._build_deal(FULL, pos)._data)


def test_a_layout_missing_a_played_card_is_rejected():
    pos = replay(FULL, 'N', 'S', ['H2', 'H5', 'H4', 'H7'])
    wrong = dict(FULL, W='43.632.T543.T865'.replace('2', '7'))   # West no longer holds the ♥2
    try:
        grader._build_deal(wrong, pos)
    except ValueError as e:
        assert 'H2' in str(e)
    else:
        raise AssertionError('expected a ValueError')


def test_direct_collect_matches_the_iterator_collect():
    rng = random.Random(11)
    for n in (0, 1, 2, 5, 9, 14, 27, 38, 47):
        play = _random_play(FULL, 'N', 'S', rng, n)
        pos = replay(FULL, 'N', 'S', play)
        layouts = grader._sample_layouts(pos, grader.view_for(pos, pos.to_play), {}, 6, rng)
        boards = grader.solve_all([grader._build_deal(L, pos) for L in layouts])
        assert dict(grader._collect(pos, boards)) == _reference_collect(pos, boards)
