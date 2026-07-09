"""Stage 6 -- Compute confidence.

A calibrated, decomposed number, not a raw score or an LLM's self-reported
certainty. Confidence is the routing signal for human attention: it gates
auto-apply vs. review vs. refusing to guess (see `band_for`).
"""

from __future__ import annotations

from app.config import settings
from app.pipeline.types import ConfidenceResult, SignalContribution

# The full set of signal categories a "well-covered" profile could have.
# Coverage is fraction-present, not fraction-supporting -- it measures how
# much evidence we had to work with, independent of what it said.
_REFERENCE_SIGNALS = {"title", "department", "skills", "groups", "manager", "keywords", "seniority"}


def compute_coverage(present_signals: set[str]) -> float:
    return len(present_signals & _REFERENCE_SIGNALS) / len(_REFERENCE_SIGNALS)


def compute_agreement(winner_contributions: list[SignalContribution]) -> float:
    if not winner_contributions:
        return 0.0
    supporting = sum(1 for c in winner_contributions if c.supports)
    return supporting / len(winner_contributions)


def compute_conflict_penalty(winner_contributions: list[SignalContribution]) -> float:
    total_weight = sum(c.weight for c in winner_contributions)
    if total_weight == 0:
        return 0.0
    contradicting_weight = sum(c.weight for c in winner_contributions if not c.supports)
    return settings.penalty_conflict_max * (contradicting_weight / total_weight)


def compute_missing_penalty(present_signals: set[str]) -> float:
    return settings.penalty_missing_title if "title" not in present_signals else 0.0


def compute_stale_penalty(winner_contributions: list[SignalContribution]) -> float:
    """Penalizes a decision resting only on indirect/structural evidence
    (manager, groups) with no direct title/department support."""

    def supports(signal_name: str) -> bool:
        contribution = next((c for c in winner_contributions if c.signal == signal_name), None)
        return bool(contribution and contribution.supports)

    direct_evidence = supports("title") or supports("department")
    indirect_evidence = supports("manager") or supports("groups")
    if not direct_evidence and indirect_evidence:
        return settings.penalty_manager_derived
    return 0.0


def band_for(confidence: float) -> str:
    if confidence >= settings.band_high:
        return "high"
    if confidence >= settings.band_medium:
        return "medium"
    if confidence >= settings.band_low:
        return "low"
    return "very_low"


def compute_confidence(
    present_signals: set[str],
    top_score: float,
    margin: float,
    winner_contributions: list[SignalContribution],
) -> ConfidenceResult:
    s_top = max(0.0, min(top_score, 1.0))
    s_margin = max(0.0, min(margin, 1.0))
    c_coverage = compute_coverage(present_signals)
    a_agreement = compute_agreement(winner_contributions)

    raw = (
        settings.confidence_w_top * s_top
        + settings.confidence_w_margin * s_margin
        + settings.confidence_w_coverage * c_coverage
        + settings.confidence_w_agreement * a_agreement
    )

    p_conflict = compute_conflict_penalty(winner_contributions)
    p_missing = compute_missing_penalty(present_signals)
    p_stale = compute_stale_penalty(winner_contributions)

    confidence = raw * (1 - p_conflict) * (1 - p_missing) * (1 - p_stale)
    confidence = max(0.0, min(confidence, 1.0))

    return ConfidenceResult(
        confidence=confidence,
        band=band_for(confidence),
        s_top=s_top,
        s_margin=s_margin,
        c_coverage=c_coverage,
        a_agreement=a_agreement,
        p_conflict=p_conflict,
        p_missing=p_missing,
        p_stale=p_stale,
    )
