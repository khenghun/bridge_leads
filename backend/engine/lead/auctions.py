"""
Predefined auction demos.

Each named auction maps to a contract + declarer + a predefined constraint set on
the unseen hands, built on the disjunctive shapes from `engine.shapes` /
`engine.shape_parser`. Selecting one in the UI auto-fills the contract and the
constraint editor so a user sees the simulator respond to a standard sequence
without entering constraints by hand.

Shapes are stored as text in the mini-language (the same form the UI accepts) so
the preset is human-readable and round-trips through the parser. `constraints()`
returns the engine-ready dict (shapes parsed to terms).

For now there is a single demo: a standard 15-17 1NT opening raised straight to
3NT. South opens 1NT (so South is declarer, North dummy); the opening leader is
West.
"""

from ..shape_parser import parse_shapes

# South: 15-17 balanced, allowing a 5-card major or a 6-card minor (6322).
_SOUTH_1NT = ("(2-4s,2-4h,2-5d,2-5c) or (5h,2-3s,2-4d,2-4c) "
              "or (5s,2-3h,2-4d,2-4c) or (6c,2-3s,2-3h,2-3d) "
              "or (6d,2-3s,2-3h,2-3c)")

# North: 10-14, >=2 in each suit, minors <=6, majors <=3, except an exact 4333
# with a 4-card major.
_NORTH_3NT = "(2-3s,2-3h,2-6d,2-6c) or (4s,3h,3d,3c) or (4h,3s,3d,3c)"

AUCTIONS = {
    '1NT (S) – 3NT (N)': {
        'contract': '3NT',
        'declarer': 'S',
        'hcp': {'S': (15, 17), 'N': (10, 14)},
        'shapes_text': {'S': _SOUTH_1NT, 'N': _NORTH_3NT},
        'note': ('Standard 15–17 1NT opening, direct raise to game. '
                 'South declares; West leads.'),
    },
    # Same hand shapes as the 1NT auction — only the HCP ranges differ.
    '2NT (S) – 3NT (N)': {
        'contract': '3NT',
        'declarer': 'S',
        'hcp': {'S': (20, 21), 'N': (4, 10)},
        'shapes_text': {'S': _SOUTH_1NT, 'N': _NORTH_3NT},
        'note': ('Standard 20–21 2NT opening, direct raise to game. '
                 'South declares; West leads.'),
    },
}


def auction_names():
    """Names of the available demo auctions, in registry order."""
    return list(AUCTIONS)


def get_auction(name):
    """Raw preset dict for a named auction (KeyError if unknown)."""
    return AUCTIONS[name]


def constraints(name):
    """Engine-ready constraints dict for a named auction.

    Parses each seat's `shapes_text` into terms and pairs it with the HCP
    ranges, ready to hand to `simulate_opening_lead`.
    """
    a = AUCTIONS[name]
    shapes = {seat: parse_shapes(text)
              for seat, text in a['shapes_text'].items()}
    return {'hcp': {seat: tuple(rng) for seat, rng in a['hcp'].items()},
            'shapes': shapes}
