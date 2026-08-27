"""Pure replay of a recorded play sequence — no DDS, no sampling.

Given the four hands, the strain and declarer, and the cards played from the
opening lead onwards, this module reconstructs the position at any point: whose
turn it is, what is left in each hand, who won which trick, and which seats have
shown out of which suits.

Everything here is deliberately framework- *and* endplay-free. `endplay.Deal.play`
happily accepts a revoke (it only removes the card from the hand), so the
legality checks a recorded hand needs — the card is in the hand on turn, and it
follows suit when able — live here instead. A malformed play raises `ValueError`
naming the play index, which the HTTP layer surfaces as a 422.

Card format is endplay's `suit+rank` (`SA`, `HK`, `DT`, `C2`), matching the rest
of the project; PBN hand strings are `spades.hearts.diamonds.clubs`.
"""

from dataclasses import dataclass, field

SEATS = ['N', 'E', 'S', 'W']
SUITS = 'SHDC'
RANKS = 'AKQJT98765432'
STRAINS = 'NSHDC'

# Higher is better. 'A' -> 12 ... '2' -> 0.
RANK_VALUE = {r: len(RANKS) - 1 - i for i, r in enumerate(RANKS)}
SUIT_INDEX = {s: i for i, s in enumerate(SUITS)}


def next_seat(seat: str, n: int = 1) -> str:
    """The seat `n` places clockwise from `seat` (1 = LHO, 2 = partner)."""
    return SEATS[(SEATS.index(seat) + n) % 4]


def card_sort_key(card: str):
    """Sort cards suit-major (S H D C), high rank first — the order hands read in."""
    return (SUIT_INDEX.get(card[0], 9), -RANK_VALUE.get(card[1], -1))


def parse_card(card, where: str = 'card') -> str:
    """Normalise and validate one card ('h10' -> 'HT'). Raises ValueError."""
    text = (card or '')
    if not isinstance(text, str):
        raise ValueError(f"{where}: {card!r} is not a card")
    text = text.strip().upper().replace('10', 'T')
    if len(text) != 2 or text[0] not in SUITS or text[1] not in RANKS:
        raise ValueError(
            f"{where}: {card!r} is not a card — use the endplay form, suit then "
            "rank, e.g. 'HA' or 'DT'.")
    return text


def hand_to_cards(pbn: str) -> list[str]:
    """PBN hand string 'S.H.D.C' -> list of cards. Validates ranks and count."""
    parts = (pbn or '').split('.')
    if len(parts) != 4:
        raise ValueError(
            f"{pbn!r} is not a PBN hand — expected "
            "'spades.hearts.diamonds.clubs' (4 dot-separated suits).")
    cards = []
    for holding, suit in zip(parts, SUITS):
        if len(set(holding)) != len(holding):
            raise ValueError(f"{pbn!r} repeats a rank within one suit")
        for rank in holding:
            if rank not in RANKS:
                raise ValueError(f"invalid rank {rank!r} in {pbn!r}")
            cards.append(suit + rank)
    return cards


def cards_to_hand(cards) -> str:
    """List of cards -> PBN hand string (suits high-to-low)."""
    holdings = {s: [] for s in SUITS}
    for card in cards:
        holdings[card[0]].append(card[1])
    for s in SUITS:
        holdings[s].sort(key=lambda r: -RANK_VALUE[r])
    return '.'.join(''.join(holdings[s]) for s in SUITS)


def parse_hands(hands) -> dict[str, list[str]]:
    """Validate the four hands. Returns `{seat: [card, ...]}`.

    Requires all four seats, 13 cards each, and 52 distinct cards — a deal that
    fails any of those cannot be replayed or sampled around."""
    if not isinstance(hands, dict):
        raise ValueError("hands must be a mapping of seat -> PBN hand")
    out = {}
    seen = {}
    for seat in SEATS:
        if seat not in hands:
            raise ValueError(f"hands is missing seat {seat}")
        cards = (hand_to_cards(hands[seat]) if isinstance(hands[seat], str)
                 else [parse_card(c, f'{seat} hand') for c in hands[seat]])
        if len(cards) != 13:
            raise ValueError(f"{seat} has {len(cards)} cards; a hand holds 13.")
        for card in cards:
            if card in seen:
                raise ValueError(
                    f"{card} appears in both {seen[card]}'s and {seat}'s hand — "
                    "a card can only be in one hand.")
            seen[card] = seat
        out[seat] = cards
    extra = [s for s in hands if s not in SEATS]
    if extra:
        raise ValueError(f"unknown seat(s) in hands: {', '.join(sorted(extra))}")
    return out


def trick_winner(cards, leader: str, trump) -> str:
    """Who won a completed trick.

    `cards` are the four cards in play order starting from `leader`; `trump` is
    a suit letter or None for notrump. The highest trump wins, else the highest
    card of the suit led."""
    if len(cards) != 4:
        raise ValueError(f"a trick has 4 cards, got {len(cards)}")
    led = cards[0][0]
    best_i, best_rank, best_trump = 0, RANK_VALUE[cards[0][1]], cards[0][0] == trump
    for i in range(1, 4):
        suit, rank = cards[i][0], RANK_VALUE[cards[i][1]]
        is_trump = trump is not None and suit == trump
        if is_trump and not best_trump:
            best_i, best_rank, best_trump = i, rank, True
        elif is_trump == best_trump and suit == (trump if best_trump else led):
            if rank > best_rank:
                best_i, best_rank = i, rank
    return next_seat(leader, best_i)


@dataclass(frozen=True)
class Trick:
    leader: str
    cards: list[str]        # in play order, starting from `leader`
    winner: str


@dataclass(frozen=True)
class Position:
    """A snapshot of the hand at one point in the play.

    `index` is the number of cards played, so it doubles as the index into the
    play list of the card that is about to be chosen."""
    strain: str                             # 'N','S','H','D','C'
    trump: str | None                       # None in notrump
    declarer: str
    dummy: str
    opening_leader: str
    index: int
    history: list[str]                      # every card played so far, in order
    original: dict[str, list[str]]          # the 13 cards each seat was dealt
    remaining: dict[str, list[str]]         # what each seat still holds
    played_by: dict[str, list[str]]         # what each seat has played
    show_outs: dict[str, set[str]]          # seat -> suits it has shown out of
    tricks: list[Trick]                     # completed tricks
    trick_leader: str                       # who led the current trick
    current_trick: list[str] = field(default_factory=list)

    # -- derived -----------------------------------------------------------
    @property
    def to_play(self) -> str:
        return next_seat(self.trick_leader, len(self.current_trick))

    @property
    def declarer_side(self) -> frozenset:
        return frozenset({self.declarer, self.dummy})

    @property
    def led_suit(self) -> str | None:
        return self.current_trick[0][0] if self.current_trick else None

    @property
    def completed_tricks(self) -> int:
        return len(self.tricks)

    @property
    def remaining_tricks(self) -> int:
        """Tricks still to be won, counting the one in progress."""
        return 13 - len(self.tricks)

    @property
    def trick_number(self) -> int:
        """1-based number of the trick in progress (14 once the hand is over)."""
        return len(self.tricks) + 1

    @property
    def declarer_tricks_won(self) -> int:
        side = self.declarer_side
        return sum(1 for t in self.tricks if t.winner in side)

    @property
    def tricks_won(self) -> dict[str, int]:
        ns = sum(1 for t in self.tricks if t.winner in ('N', 'S'))
        return {'NS': ns, 'EW': len(self.tricks) - ns}

    @property
    def complete(self) -> bool:
        return self.index >= 52

    def layout(self) -> dict[str, str]:
        """The full deal as PBN hand strings, as dealt."""
        return {s: cards_to_hand(self.original[s]) for s in SEATS}

    def remaining_layout(self) -> dict[str, str]:
        return {s: cards_to_hand(self.remaining[s]) for s in SEATS}


def legal_cards(position: Position) -> list[str]:
    """The cards the seat on play may legally choose, in hand order."""
    hand = position.remaining[position.to_play]
    led = position.led_suit
    if led is not None:
        following = [c for c in hand if c[0] == led]
        if following:
            return sorted(following, key=card_sort_key)
    return sorted(hand, key=card_sort_key)


def _states(hands, strain: str, declarer: str, play):
    """Yield a Position before each card of `play`, then the final Position."""
    strain = (strain or '').upper()
    declarer = (declarer or '').upper()
    if strain not in STRAINS:
        raise ValueError(f"strain must be one of {STRAINS}, got {strain!r}")
    if declarer not in SEATS:
        raise ValueError(f"declarer must be N/E/S/W, got {declarer!r}")

    trump = None if strain == 'N' else strain
    dummy = next_seat(declarer, 2)
    opening_leader = next_seat(declarer, 1)

    original = parse_hands(hands)
    remaining = {s: list(cs) for s, cs in original.items()}
    played_by = {s: [] for s in SEATS}
    show_outs = {s: set() for s in SEATS}
    tricks: list[Trick] = []
    history: list[str] = []
    trick_leader = opening_leader
    current: list[str] = []

    cards = [parse_card(c, f'play[{i}]') for i, c in enumerate(play or [])]
    if len(cards) > 52:
        raise ValueError(f"a hand is 52 cards; the play has {len(cards)}")

    def snapshot() -> Position:
        return Position(
            strain=strain, trump=trump, declarer=declarer, dummy=dummy,
            opening_leader=opening_leader, index=len(history),
            history=list(history),
            original={s: list(cs) for s, cs in original.items()},
            remaining={s: list(cs) for s, cs in remaining.items()},
            played_by={s: list(cs) for s, cs in played_by.items()},
            show_outs={s: set(v) for s, v in show_outs.items()},
            tricks=list(tricks), trick_leader=trick_leader,
            current_trick=list(current))

    for i, card in enumerate(cards):
        pos = snapshot()
        yield pos
        seat = pos.to_play
        if card not in remaining[seat]:
            raise ValueError(
                f"play[{i}]: it is {seat}'s turn but {seat} does not hold {card}.")
        if current:
            led = current[0][0]
            if card[0] != led and any(c[0] == led for c in remaining[seat]):
                raise ValueError(
                    f"play[{i}]: {seat} played {card} but must follow suit — "
                    f"{seat} still holds {led}.")
            if card[0] != led:
                show_outs[seat].add(led)
        remaining[seat].remove(card)
        played_by[seat].append(card)
        history.append(card)
        current.append(card)
        if len(current) == 4:
            winner = trick_winner(current, trick_leader, trump)
            tricks.append(Trick(trick_leader, list(current), winner))
            trick_leader = winner
            current = []

    yield snapshot()


def replay(hands, strain: str, declarer: str, play=()) -> Position:
    """Replay `play` onto `hands` and return the resulting position.

    Raises ValueError (naming the play index) on a card that is not in the hand
    on turn or that fails to follow suit."""
    position = None
    for position in _states(hands, strain, declarer, play):
        pass
    return position


def walk(hands, strain: str, declarer: str, play=()):
    """Yield `(position_before_the_card, card)` for every card of `play`."""
    states = _states(hands, strain, declarer, play)
    for card in [parse_card(c, f'play[{i}]') for i, c in enumerate(play or [])]:
        yield next(states), card
    # Drain the generator so the final snapshot's bookkeeping (and any late
    # validation error) still runs.
    for _ in states:
        pass
