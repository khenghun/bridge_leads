"""Play-solver request/response models.

The shared vocabulary (seats, strains, vulnerability, `Constraints`, the `Card`
pattern) comes from `app.common.schemas`; this module adds the play solver's own
payloads.

The API takes **structured state, never a LIN string** — LIN is parsed in the
browser, and the request carries the four hands, the contract and the play so
far. That is what makes every call stateless and cacheable.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.types import confloat, conint
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


class ExpertOptions(BaseModel):
    """Expert opponents (v1.3): sampled layouts must be consistent with the
    opponents' earlier plays being best plays given what they could see.
    Defaults mirror `engine.play.expert.ExpertSettings`."""
    inner_ratio: confloat(ge=0.1, le=1.0) = 0.5
    tolerance: confloat(ge=0.0, le=1.0) = 0.10
    confidence: confloat(ge=1.0, le=4.0) = 2.0
    budget: conint(ge=5, le=50) = 20
    strict: bool = False
    depth: conint(ge=1, le=2) = 1


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
    num_deals: conint(ge=5, le=200) = 40
    constraints: Constraints = Field(default_factory=Constraints)
    expert_opponents: bool = False
    expert: Optional[ExpertOptions] = Field(
        default=None,
        description="Expert-opponents settings; only read when expert_opponents is on")
    expert_constraints: Optional[Constraints] = Field(
        default=None,
        description="The user's constraints on all four seats (the auction was "
                    "public), sliced per opponent view when judging their plays")

    @field_validator('hands')
    @classmethod
    def _hands_are_a_deal(cls, v):
        return _validate_hands(v)

    @model_validator(mode='after')
    def _expert_defaults(self):
        if self.expert_opponents and self.expert is None:
            self.expert = ExpertOptions()
        if not self.expert_opponents:
            self.expert = None
            self.expert_constraints = None
        return self


class AnalyzeRequest(PlayStateRequest):
    seat: Seat = Field(description="Whose decisions to grade (dummy is rejected)")
    decisions: Optional[list[conint(ge=0, le=51)]] = Field(
        default=None,
        description="Play indices to grade in this call (a chunk of a slow "
                    "analysis); omitted = every decision of the seat")


class PositionRequest(PlayStateRequest):
    """Same state without `seat`: grade whoever is on play after `play`."""


class PlayOption(BaseModel):
    card: str                       # endplay input form, e.g. 'HK'
    tricks: float                   # mean tricks for the graded side
    success_rate: float             # make rate (declarer) / defeat rate (defender)
    score: float                    # mean duplicate score for the graded side
    imps: float                     # mean per-deal IMP swing vs the best card (<= 0 for best)


class ExpertStats(BaseModel):
    sampled: int                    # layouts examined
    consistent: int                 # layouts graded on
    traced: int                     # layouts that went through the double-dummy trace
    carried: int = 0                # layouts carried over from the seat's previous decision
    judged: int                     # inner judgements run (memo hits excluded)
    memo_hits: int = 0              # judgements answered from the memo
    threshold: float                # rejects plays shown at least this many tricks worse
    sigma: Optional[float]          # observed sd of the paired difference, if any judgement ran
    inference: str                  # filtered | none | trivial


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
    actual_score: Optional[float]   # mean duplicate score of the card played
    best_score: Optional[float]     # ... and of the best card
    score_diff: Optional[float]     # points, actual - best
    imp_diff: Optional[float]       # mean per-deal IMPs, actual - best (<= 0)
    status: str                     # optimal | good | suboptimal | forced
    options: list[PlayOption]       # best first
    best_cards: list[str]
    expert: Optional[ExpertStats] = None


class AnalysisSummary(BaseModel):
    decisions: int
    graded: int
    optimal: int
    good: int
    suboptimal: int
    total_trick_loss: float
    avg_trick_loss: float
    total_score_loss: float         # points given up across graded decisions
    total_imp_loss: float           # IMPs given up across graded decisions


class AnalyzeResponse(BaseModel):
    seat: str
    role: Role
    visible: list[str]
    tricks_needed: int              # for the graded side
    decisions: list[Decision]
    summary: AnalysisSummary
    method: str
    num_deals: int
    expert: Optional[ExpertOptions] = None


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
    expert: Optional[ExpertStats] = None


class HealthResponse(BaseModel):
    status: str
