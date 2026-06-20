"""
Scoring — duplicate-bridge score (via endplay) + MP/IMP aggregation.

The raw contract score is computed by endplay's Contract.score(vul); we never
hand-roll the score tables. This module only:
  1. wraps endplay to turn (contract, declarer tricks, vul) into a declarer score
  2. aggregates candidate-lead scores across simulated deals as Matchpoints or IMPs

Perspective: the opening leader is a DEFENDER, so a lead is better when the
declarer's score is LOWER. We score from the leader's side as -declarer_score.
"""

from endplay.types import Contract, Penalty, Vul

# Standard IMP scale: index = IMPs awarded for a score difference >= threshold.
_IMP_THRESHOLDS = [
    20, 50, 90, 130, 170, 220, 270, 320, 370, 430, 500, 600, 750, 900,
    1100, 1300, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000,
]

PENALTY_MAP = {
    'none': Penalty.passed,
    'doubled': Penalty.doubled,
    'redoubled': Penalty.redoubled,
}

VUL_MAP = {
    'none': Vul.none,
    'both': Vul.both,
    'ns': Vul.ns,
    'ew': Vul.ew,
}


def imps(diff):
    """Convert a raw score difference (points) to IMPs on the standard scale."""
    sign = 1 if diff >= 0 else -1
    diff = abs(diff)
    awarded = 0
    for i, threshold in enumerate(_IMP_THRESHOLDS, start=1):
        if diff < threshold:
            break
        awarded = i
    return sign * awarded


def declarer_score(level, strain, declarer, declarer_tricks, vul='none', penalty='none'):
    """
    Declarer's duplicate score for a contract given the tricks they took.

    level:           1-7
    strain:          'N','S','H','D','C'
    declarer:        'N','E','S','W'
    declarer_tricks: total tricks won by declarer's side (0-13)
    vul:             'none' | 'both' | 'ns' | 'ew'
    penalty:         'none' | 'doubled' | 'redoubled'
    """
    denom = 'NT' if strain.upper() == 'N' else strain.upper()
    contract = Contract(f"{level}{denom}{declarer}")
    contract.penalty = PENALTY_MAP[penalty]
    contract.result = declarer_tricks - (6 + level)   # signed over/undertricks
    return contract.score(VUL_MAP[vul])


def aggregate(lead_scores, mode='imps'):
    """
    Rank candidate leads from per-deal leader-side scores.

    Args:
        lead_scores: dict {lead_card: [leader_score_per_deal, ...]}.
                     All leads must share the same number/order of deals.
        mode: 'matchpoints' or 'imps'.

    Returns:
        dict {lead_card: metric}. Higher = better.
          matchpoints -> average MP% (0..100), each lead compared head-to-head
                         against the other candidate leads on the same deal.
          imps        -> average IMPs vs the per-deal datum (mean of all
                         candidate leads' scores on that deal).
    """
    leads = list(lead_scores)
    if not leads:
        return {}
    num_deals = len(next(iter(lead_scores.values())))
    if num_deals == 0:
        return {lead: 0.0 for lead in leads}

    if mode == 'matchpoints':
        totals = {lead: 0.0 for lead in leads}
        comparisons = max(len(leads) - 1, 1)
        for d in range(num_deals):
            for a in leads:
                sa = lead_scores[a][d]
                mp = 0.0
                for b in leads:
                    if a is b:
                        continue
                    sb = lead_scores[b][d]
                    if sa > sb:
                        mp += 1.0
                    elif sa == sb:
                        mp += 0.5
                totals[a] += mp / comparisons
        return {lead: 100.0 * totals[lead] / num_deals for lead in leads}

    # imps vs per-deal datum
    totals = {lead: 0.0 for lead in leads}
    for d in range(num_deals):
        datum = sum(lead_scores[lead][d] for lead in leads) / len(leads)
        for lead in leads:
            totals[lead] += imps(lead_scores[lead][d] - datum)
    return {lead: totals[lead] / num_deals for lead in leads}
