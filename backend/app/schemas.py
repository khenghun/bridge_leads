"""Pydantic request/response models.

These mirror the loose dict contracts the `engine` uses (see
`engine.lead_simulator.simulate_opening_lead`), adding validation at the HTTP
edge: seat/strain/vul enums, HCP 0–40, suit lengths 0–13, level 1–7, and the
100–1000 deal range the old Streamlit slider enforced.
"""

from typing import Optional
from typing_extensions import Annotated

from pydantic import BaseModel, Field
from pydantic.types import conint

Seat = Annotated[str, Field(pattern=r'^[NESW]$')]
Strain = Annotated[str, Field(pattern=r'^[NSHDC]$')]
Suit = Annotated[str, Field(pattern=r'^[SHDC]$')]
Vul = Annotated[str, Field(pattern=r'^(none|both|ns|ew)$')]
Penalty = Annotated[str, Field(pattern=r'^(none|doubled|redoubled)$')]

Hcp = conint(ge=0, le=40)
Length = conint(ge=0, le=13)
HcpRange = tuple[Hcp, Hcp]
LengthRange = tuple[Length, Length]


class Constraints(BaseModel):
    """Constraints on the three unseen (non-leader) seats.

    `shapes` values are the disjunctive shape mini-language *text* (same syntax
    the old UI accepted); the service parses them with `engine.shape_parser`.
    """
    hcp: dict[Seat, HcpRange] = Field(default_factory=dict)
    suit_length: dict[Seat, dict[Suit, LengthRange]] = Field(default_factory=dict)
    shapes: dict[Seat, str] = Field(default_factory=dict)


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
    leader: str
    meta: SimulateMeta


class ShapeValidateRequest(BaseModel):
    text: str
    seat: Optional[str] = None      # advisory only; not validated


class ShapeValidateResponse(BaseModel):
    ok: bool
    terms_count: int
    warnings: list[str]


class AuctionSummary(BaseModel):
    name: str
    contract: str
    declarer: str
    hcp: dict[str, tuple[int, int]]
    shapes_text: dict[str, str]
    note: str


class AuctionsResponse(BaseModel):
    auctions: list[AuctionSummary]
