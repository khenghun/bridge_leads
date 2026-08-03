"""The candidate contracts a pair can choose between.

Why 20 and not 70 (7 levels x 5 strains x 2 declarers):

Undoubled, a contract's score depends only on the **tricks taken** and whether
the level bid reaches game — overtricks score at the same rate as bid tricks
(1♠ taking 8 tricks = 2♠ taking 8 tricks = 110). So within a strain, every
partscore level scores identically when it makes, and the *lowest* one never
scores less (3♠ down one is -50 where 1♠ was +110). A partscore is therefore
one decision, not three, and per strain there are exactly four distinct
decisions:

    partscore (1-level)  |  game (3NT / 4M / 5m)  |  small slam  |  grand slam

5 strains x 4 = 20 contracts, each evaluated with either partner as declarer.
That is also why the ranked table never fills up with 4♠/3♠/2♠ near-duplicates.
"""

# Bidding-table order: NT first, then spades down to clubs.
STRAINS = ['N', 'S', 'H', 'D', 'C']

# The level at which a contract in each strain earns the game bonus.
GAME_LEVEL = {'N': 3, 'S': 4, 'H': 4, 'D': 5, 'C': 5}

PART_LEVEL = 1
KINDS = ('part', 'game', 'slam', 'grand')

SUIT_SYMBOL = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}


def levels_for(strain):
    """[(level, kind), ...] — the four decision-relevant contracts in `strain`."""
    return [
        (PART_LEVEL, 'part'),
        (GAME_LEVEL[strain], 'game'),
        (6, 'slam'),
        (7, 'grand'),
    ]


def key(level, strain, declarer):
    """Stable identifier used as the matrix column name, e.g. '4S-N'."""
    return f'{level}{strain}-{declarer}'


def label(level, strain, kind):
    """Human label. Partscores are shown as '♠ partscore' rather than '1♠',
    because every partscore level in the strain scores the same."""
    strain_text = 'NT' if strain == 'N' else SUIT_SYMBOL[strain]
    if kind == 'part':
        return f'{strain_text} partscore'
    return f'{level}{strain_text}'


def enumerate_candidates(strains=STRAINS, declarers=('N', 'S')):
    """Ordered candidate list: strain (bidding-table order) x level, each seat.

    Returns dicts of {key, label, level, strain, declarer, kind, tricks_needed}.
    """
    unknown = [s for s in strains if s not in GAME_LEVEL]
    if unknown:
        raise ValueError(f"unknown strain(s) {unknown}")
    if not strains:
        raise ValueError("at least one strain must be considered")

    out = []
    for strain in [s for s in STRAINS if s in strains]:
        for level, kind in levels_for(strain):
            for declarer in declarers:
                out.append({
                    'key': key(level, strain, declarer),
                    'label': label(level, strain, kind),
                    'level': level,
                    'strain': strain,
                    'declarer': declarer,
                    'kind': kind,
                    'tricks_needed': 6 + level,
                })
    return out
