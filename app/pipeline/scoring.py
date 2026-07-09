"""Stage 4 -- Score & rank candidates.

Fuses per-signal sub-scores (Stage 3) into one weighted score per role,
renormalized over whichever signals are actually present so a profile with
fewer signals is scored on less evidence rather than punished to zero.
Also computes the top1/top2 margin that Stage 5 uses to decide whether the
deterministic layers already agree.
"""

from __future__ import annotations

from app.pipeline.types import CatalogRole, ScoredCandidate, SignalContribution


def combine_score(contributions: list[SignalContribution]) -> float:
    total_weight = sum(c.weight for c in contributions)
    if total_weight == 0:
        return 0.0
    weighted = sum(c.score * c.weight for c in contributions)
    return weighted / total_weight


def rank_candidates(
    contributions_by_role: dict[str, list[SignalContribution]],
    roles_by_id: dict[str, CatalogRole],
) -> list[ScoredCandidate]:
    scored = [
        ScoredCandidate(
            role_id=role_id,
            role_name=roles_by_id[role_id].role_name,
            contributions=contributions,
            score=combine_score(contributions),
        )
        for role_id, contributions in contributions_by_role.items()
    ]
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored


def compute_margin(ranked: list[ScoredCandidate]) -> float:
    """Gap between the top and second candidate. A wide margin means the
    deterministic layers already agree; a narrow one is genuine ambiguity."""
    if len(ranked) < 2:
        return 1.0
    return ranked[0].score - ranked[1].score
