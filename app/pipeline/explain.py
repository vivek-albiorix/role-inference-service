"""Stage 7 -- Generate explanation.

Assembled entirely from the real Stage 3/4 evidence and the Stage 6
confidence breakdown -- never a free-form LLM narrative standing alone, so
what's shown can never contradict the numbers behind it. If Stage 5 ran, its
rationale is folded in as one more input, not as the source of truth.
"""

from __future__ import annotations

from app.pipeline.candidates import role_function
from app.pipeline.types import (
    AlternativeRoleItem,
    CatalogRole,
    ConfidenceResult,
    ExplanationBundle,
    NormalizedProfile,
    ScoredCandidate,
    SignalBundle,
    SignalEvidenceItem,
)

_MAX_ALTERNATIVES = 2

_MISSING_SIGNAL_MESSAGES = {
    "title": "No title provided.",
    "department": "No department on file.",
    "manager": "No manager on file -- could not corroborate via team.",
    "skills": "No skills listed.",
    "groups": "No functionally-informative group memberships (only generic/org-wide groups, if any).",
}


def _missing_information(signals: SignalBundle) -> list[str]:
    return [msg for key, msg in _MISSING_SIGNAL_MESSAGES.items() if key not in signals.present_signals]


def _notes_conflict_note(signals: SignalBundle, winner_role: CatalogRole | None) -> str | None:
    if not signals.notes_function_hint or winner_role is None:
        return None
    if signals.notes_function_hint != role_function(winner_role):
        return (
            f"Free-text notes hint at a '{signals.notes_function_hint}' background, which doesn't "
            f"clearly match the assigned role's function -- treated as weak, tie-breaking evidence only."
        )
    return None


def _why_lost(winner: ScoredCandidate, alternative: ScoredCandidate) -> str:
    winner_by_signal = {c.signal: c.score for c in winner.contributions}
    alt_by_signal = {c.signal: c.score for c in alternative.contributions}
    gaps = [
        (signal, winner_by_signal[signal] - alt_by_signal.get(signal, 0.0))
        for signal in winner_by_signal
        if signal in alt_by_signal
    ]
    if gaps:
        signal, gap = max(gaps, key=lambda item: item[1])
        if gap > 0.05:
            return f"Weaker {signal} match than {winner.role_name} ({alt_by_signal[signal]:.2f} vs {winner_by_signal[signal]:.2f})."
    return f"Lower combined score than {winner.role_name} ({alternative.score:.2f} vs {winner.score:.2f})."


def _why_winner_won(winner: ScoredCandidate) -> str | None:
    supporting = sorted((c for c in winner.contributions if c.supports), key=lambda c: c.weight, reverse=True)
    if not supporting:
        return None
    top_two = supporting[:2]
    joined = " and ".join(c.signal for c in top_two)
    return f"{joined.capitalize()} jointly point to {winner.role_name}."


def _human_readable(
    winner: ScoredCandidate | None,
    confidence: ConfidenceResult,
    assigned: bool,
    normalized: NormalizedProfile,
    notes_conflict: str | None,
) -> str:
    if not assigned or winner is None:
        return (
            f"Confidence is too low ({confidence.confidence:.2f}, band '{confidence.band}') to assign a role "
            "automatically -- this profile needs human review rather than a guess."
        )
    caveats = []
    if normalized.title_is_generic:
        caveats.append("the title alone was too generic to rely on")
    if normalized.title_has_vanity:
        caveats.append("the title was a vanity/placeholder word and was ignored")
    if notes_conflict:
        caveats.append("notes hint at a possibly conflicting background")
    caveat_str = f" ({'; '.join(caveats)})" if caveats else ""
    return (
        f"Mapped to {winner.role_name} ({confidence.band} confidence, {confidence.confidence:.2f}){caveat_str}. "
        f"{_why_winner_won(winner) or ''}"
    ).strip()


def build_explanation(
    normalized: NormalizedProfile,
    signals: SignalBundle,
    ranked: list[ScoredCandidate],
    roles_by_id: dict[str, CatalogRole],
    confidence: ConfidenceResult,
    assigned: bool,
    llm_note: str | None = None,
) -> ExplanationBundle:
    winner = ranked[0] if ranked and ranked[0].score > 0 else None
    winner_role = roles_by_id.get(winner.role_id) if winner else None

    signals_used: list[SignalEvidenceItem] = []
    positive_evidence: list[str] = []
    negative_evidence: list[str] = []
    if winner:
        for c in winner.contributions:
            signals_used.append(SignalEvidenceItem(signal=c.signal, value=c.detail, weight=c.weight, supports=c.supports))
            (positive_evidence if c.supports else negative_evidence).append(c.detail)

    notes_conflict = _notes_conflict_note(signals, winner_role)
    if notes_conflict:
        negative_evidence.append(notes_conflict)

    missing_information = _missing_information(signals)
    if llm_note:
        missing_information.append(f"LLM disambiguation note: {llm_note}")

    alternatives = [c for c in ranked[1 : 1 + _MAX_ALTERNATIVES] if winner]
    alternative_roles = [
        AlternativeRoleItem(
            role=alt.role_name,
            role_id=alt.role_id,
            confidence=round(alt.score, 2),
            why_lost=_why_lost(winner, alt) if winner else None,
        )
        for alt in alternatives
    ]

    return ExplanationBundle(
        human_readable=_human_readable(winner, confidence, assigned, normalized, notes_conflict),
        signals=[c.detail for c in (winner.contributions if winner else [])],
        signals_used=signals_used,
        positive_evidence=positive_evidence,
        negative_evidence=negative_evidence,
        alternative_roles=alternative_roles,
        why_winner_won=_why_winner_won(winner) if winner else None,
        missing_information=missing_information,
    )
