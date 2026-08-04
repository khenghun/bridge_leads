"""Pydantic types shared by both tools' request/response models.

These mirror the loose dict contracts the `engine` uses, adding validation at the
HTTP edge: seat/strain/vul enums, HCP 0–40, suit lengths 0–13.
"""

from typing_extensions import Annotated

from pydantic import BaseModel, Field
from pydantic.types import conint

Seat = Annotated[str, Field(pattern=r'^[NESW]$')]
Strain = Annotated[str, Field(pattern=r'^[NSHDC]$')]
Suit = Annotated[str, Field(pattern=r'^[SHDC]$')]
Vul = Annotated[str, Field(pattern=r'^(none|both|ns|ew)$')]
Penalty = Annotated[str, Field(pattern=r'^(none|doubled|redoubled)$')]
Quality = Annotated[str, Field(pattern=r'^(good|poor)$')]
# endplay card form: suit letter then rank, 'T' for ten (SA, HK, DT, C2).
Card = Annotated[str, Field(pattern=r'^[SHDC][AKQJT98765432]$')]

Hcp = conint(ge=0, le=40)
Length = conint(ge=0, le=13)
HcpRange = tuple[Hcp, Hcp]
LengthRange = tuple[Length, Length]


class Constraints(BaseModel):
    """Constraints on the three hands the user cannot see.

    `shapes` values are the disjunctive shape mini-language *text* (same syntax
    the old UI accepted); the service parses them with `engine.shape_parser`.

    `quality` grades one seat's one suit by its top honours ('good' = 2 of AKQ
    or 3 of AKQJT, 'poor' = worse). At most **one** entry across the whole dict
    is accepted — it models the single player who described a suit in the
    auction; the engine raises on more (surfaced as 422).

    `fixed_cards` pins named cards into an unseen hand ('E holds ♥AK'), the one
    constraint the length/HCP/quality vocabulary cannot express. Cards are in
    endplay form (`HA`, `DT`); a card may appear only once across the whole
    table and may not duplicate one of your own.
    """
    hcp: dict[Seat, HcpRange] = Field(default_factory=dict)
    suit_length: dict[Seat, dict[Suit, LengthRange]] = Field(default_factory=dict)
    shapes: dict[Seat, str] = Field(default_factory=dict)
    quality: dict[Seat, dict[Suit, Quality]] = Field(default_factory=dict)
    fixed_cards: dict[Seat, list[Card]] = Field(default_factory=dict)


class DealRecord(BaseModel):
    """One simulated deal: the layout plus one entry per candidate, aligned to
    the matrix's candidate list."""
    layout: dict[str, str]          # {seat: 'S.H.D.C'}
    tricks: list[int]               # declarer tricks per candidate
    scores: list[int]               # score per candidate, in the tool's perspective


class ShapeValidateRequest(BaseModel):
    text: str
    seat: str | None = None         # advisory only; not validated


class ShapeValidateResponse(BaseModel):
    ok: bool
    terms_count: int
    warnings: list[str]
