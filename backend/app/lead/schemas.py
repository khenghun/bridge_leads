"""Opening-lead request/response models.

Shared vocabulary (seats, strains, `Constraints`, `DealRecord`) lives in
`app.common.schemas`; this module adds what only the lead tool returns.
"""

from typing import Optional

from pydantic import BaseModel, Field
from pydantic.types import conint

from ..common.schemas import Constraints, DealRecord, Penalty, Seat, Strain, Vul


class SimulateRequest(BaseModel):
    leader_hand: str = Field(description="Opening leader's 13 cards, PBN 'S.H.D.C'")
    level: conint(ge=1, le=7)
    strain: Strain
    declarer: Seat
    vul: Vul = 'none'
    penalty: Penalty = 'none'
    num_simulations: conint(ge=100, le=1000) = 500
    constraints: Constraints = Field(default_factory=Constraints)


class LeadResult(BaseModel):
    card: str
    defense_tricks: float
    declarer_tricks: float
    defeat_rate: float
    matchpoints: float
    imps: float


class SampleDeal(BaseModel):
    layout: dict[str, str]          # {seat: 'S.H.D.C'}
    declarer_tricks: int
    defense_tricks: int


class DealsMatrix(BaseModel):
    cards: list[str]                # candidate leads in symbol form ('♥Q'), fixed order
    records: list[DealRecord]       # one per simulated deal, in generation order


class SimulateMeta(BaseModel):
    level: int
    strain: str
    declarer: str


class SimulateResponse(BaseModel):
    num_simulations: int
    leads: list[LeadResult]
    best_mp: Optional[str]
    best_imp: Optional[str]
    samples: dict[str, list[SampleDeal]]
    deals: DealsMatrix
    leader: str
    meta: SimulateMeta


class AuctionSummary(BaseModel):
    name: str
    contract: str
    declarer: str
    hcp: dict[str, tuple[int, int]]
    shapes_text: dict[str, str]
    note: str


class AuctionsResponse(BaseModel):
    auctions: list[AuctionSummary]
