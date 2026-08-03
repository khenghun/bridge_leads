"""Optimal-contract request/response models.

Shared vocabulary (seats, strains, `Constraints`, `DealRecord`) lives in
`app.common.schemas`.

Note the deal range is 50–500 rather than the lead tool's 100–1000: a full DD
table costs roughly 5x a single lead solve.
"""

from typing import Optional

from pydantic import BaseModel, Field
from pydantic.types import conint

from ..common.schemas import Constraints, DealRecord, Seat, Strain, Vul


class ContractRequest(BaseModel):
    hand: str = Field(description="Your own 13 cards, PBN 'S.H.D.C'")
    seat: Seat = 'S'
    vul: Vul = 'none'
    num_deals: conint(ge=50, le=500) = 150
    strains: list[Strain] = Field(default_factory=lambda: ['N', 'S', 'H', 'D', 'C'])
    constraints: Constraints = Field(default_factory=Constraints)


class CandidateResult(BaseModel):
    key: str                        # '4S-S'
    label: str                      # '4♠' / '♠ partscore'
    level: int
    strain: str
    declarer: str
    kind: str                       # part | game | slam | grand
    tricks_needed: int
    make_rate: float
    mean_tricks: float
    mean_score: float
    fail_mean_score: Optional[float]    # None when it never failed
    seat_delta: float                   # mean tricks, this declarer vs partner


class OpponentStats(BaseModel):
    opps_game_rate: float
    par_competitive_rate: Optional[float]   # None when strains were excluded


class ContractDealsMatrix(BaseModel):
    candidates: list[str]           # candidate keys, fixed order
    records: list[DealRecord]       # one per simulated deal, in generation order


class ContractResponse(BaseModel):
    num_deals: int
    seat: str
    partner: str
    vul: str
    candidates: list[CandidateResult]
    default_benchmark: Optional[str]
    opponents: OpponentStats
    deals: ContractDealsMatrix
