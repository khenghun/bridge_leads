"""Play-solver request/response models.

The shared vocabulary (seats, strains, vulnerability, `Constraints`, the `Card`
pattern) comes from `app.common.schemas`; this module adds the play solver's own
payloads.

The API takes **structured state, never a LIN string** — LIN is parsed in the
browser, and the request carries the four hands, the contract and the play so
far. That is what makes every call stateless and cacheable.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic.types import conint
from typing_extensions import Annotated

from app.common.schemas import Card, Constraints, Penalty, Seat, Strain, Vul

Method = Annotated[str, Field(pattern=r'^(single_dummy|double_dummy)$')]
Role = Annotated[str, Field(pattern=r'^(declarer|defender)$')]

RANKS = 'AKQJT98765432'
SEATS = ('N', 'E', 'S', 'W')


def _validate_hands(hands: dict[str, str]) -> dict[str, str]:
    """Four PBN hands, 13 cards each, 52 distinct cards between them."""
    missing = [s for s in SEATS if s not in hands]
    if missing:
        raise ValueError(f"hands is missing seat(s): {', '.join(missing)}")
    seen: dict[str, str] = {}
    for seat in SEATS:
        parts = (hands[seat] or '').split('.')
        if len(parts) != 4:
            raise ValueError(
                f"{seat}'s hand must be PBN 'spades.hearts.diamonds.clubs' "
                "(4 dot-separated suits).")
        total = 0
        for holding, suit in zip(parts, 'SHDC'):
            for rank in holding:
                if rank not in RANKS:
                    raise ValueError(f"invalid rank {rank!r} in {seat}'s hand")
                card = suit + rank
                if card in seen:
                    raise ValueError(
                        f"{card} appears in both {seen[card]}'s and {seat}'s "
                        "hand — a card can only be in one hand.")
                seen[card] = seat
            total += len(holding)
        if total != 13:
            raise ValueError(f"{seat}'s hand must have 13 cards, got {total}")
    return {s: hands[s] for s in SEATS}


class PlayStateRequest(BaseModel):
    """The board plus the play so far — shared by both solve endpoints."""
    hands: dict[Seat, str] = Field(
        description="The whole deal: {N,E,S,W: 'spades.hearts.diamonds.clubs'}")
    level: conint(ge=1, le=7)
    strain: Strain
    declarer: Seat
    vul: Vul = 'none'
    penalty: Penalty = 'none'
    play: list[Card] = Field(
        default_factory=list,
        description="Cards played from the opening lead onwards, in order")
    method: Method = 'single_dummy'
    num_deals: conint(ge=5, le=100) = 20
    constraints: Constraints = Field(default_factory=Constraints)

    @field_validator('hands')
    @classmethod
    def _hands_are_a_deal(cls, v):
        return _validate_hands(v)


class AnalyzeRequest(PlayStateRequest):
    seat: Seat = Field(description="Whose decisions to grade (dummy is rejected)")


class PositionRequest(PlayStateRequest):
    """Same state without `seat`: grade whoever is on play after `play`."""


class PlayOption(BaseModel):
    card: str                       # endplay input form, e.g. 'HK'
    tricks: float                   # mean tricks for the graded side
    success_rate: float             # make rate (declarer) / defeat rate (defender)


class Decision(BaseModel):
    index: int                      # index into `play`
    trick: int                      # 1-based
    position: int                   # 0-3, seat order within the trick
    hand: str                       # the seat the card came from (dummy for declarer)
    card: str
    forced: bool                    # only one legal card; not solved
    actual_tricks: Optional[float]
    best_tricks: Optional[float]
    diff: Optional[float]           # actual - best
    status: str                     # optimal | good | suboptimal | forced
    options: list[PlayOption]       # best first
    best_cards: list[str]


class AnalysisSummary(BaseModel):
    decisions: int
    graded: int
    optimal: int
    good: int
    suboptimal: int
    total_trick_loss: float
    avg_trick_loss: float


class AnalyzeResponse(BaseModel):
    seat: str
    role: Role
    visible: list[str]
    tricks_needed: int              # for the graded side
    decisions: list[Decision]
    summary: AnalysisSummary
    method: str
    num_deals: int


class PositionResponse(BaseModel):
    to_play: str
    role: Role
    view: str                       # whose eyes; declarer when dummy is on play
    visible: list[str]
    trick: int
    index: int
    forced: bool
    legal_cards: list[str]
    tricks_won: dict[str, int]      # {'NS': n, 'EW': n}
    tricks_needed: int
    options: list[PlayOption]
    method: str
    num_deals: int                  # deals actually sampled (1 for double_dummy)


class HealthResponse(BaseModel):
    status: str
