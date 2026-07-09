"""Orchestrator -- runs stages 1-7 in order and assembles a PipelineResult.

Stateless coordinator: it owns *when* each stage runs (including the
short-circuit around Stage 5) but not *how* any stage works. Pure function
of (profile, catalog) -> PipelineResult; no DB access happens here, so it's
testable without a database and the service layer decides how to persist
the result (see app/services/inference_service.py).
"""

from __future__ import annotations

from app.config import settings
from app.models.schemas import SSOProfileIn
from app.pipeline.candidates import generate_candidates
from app.pipeline.confidence import compute_confidence
from app.pipeline.explain import build_explanation
from app.pipeline.llm_disambiguate import disambiguate
from app.pipeline.normalize import normalize_profile
from app.pipeline.scoring import compute_margin, rank_candidates
from app.pipeline.signals import extract_signals
from app.pipeline.types import CatalogRole, PipelineResult

# How many top candidates are offered to the LLM when escalating.
_LLM_SHORTLIST_SIZE = 3


def run_inference(profile: SSOProfileIn, roles: list[CatalogRole]) -> PipelineResult:
    # Stage 1
    normalized = normalize_profile(profile)
    # Stage 2
    signals = extract_signals(normalized)

    roles_by_id = {role.role_id: role for role in roles}

    # Stage 3
    contributions_by_role = generate_candidates(
        signals, normalized.title_normalized, normalized.title_is_generic, normalized.title_has_vanity, roles
    )
    # Stage 4
    ranked = rank_candidates(contributions_by_role, roles_by_id)
    margin = compute_margin(ranked)

    # Stage 5 -- only when the deterministic layers haven't already agreed
    viable = [c for c in ranked if c.score > 0]
    llm_used = False
    llm_degraded = False
    llm_note: str | None = None

    if len(viable) >= 2 and margin < settings.ambiguity_margin_threshold:
        shortlist = viable[:_LLM_SHORTLIST_SIZE]
        llm_result = disambiguate(shortlist, normalized, signals)
        llm_used = llm_result.used
        llm_degraded = llm_result.degraded
        llm_note = llm_result.rationale
        if llm_result.chosen_role_id not in ("none", ranked[0].role_id):
            chosen = next(c for c in ranked if c.role_id == llm_result.chosen_role_id)
            ranked.remove(chosen)
            ranked.insert(0, chosen)
            margin = compute_margin(ranked)

    winner = ranked[0] if ranked and ranked[0].score > 0 else None

    # Stage 6
    if winner:
        confidence = compute_confidence(signals.present_signals, winner.score, margin, winner.contributions)
    else:
        confidence = compute_confidence(set(), 0.0, 0.0, [])

    assigned = winner is not None and confidence.band != "very_low"

    # Stage 7
    explanation = build_explanation(normalized, signals, ranked, roles_by_id, confidence, assigned, llm_note)

    return PipelineResult(
        inferred_role_id=winner.role_id if assigned and winner else None,
        inferred_role_name=winner.role_name if assigned and winner else None,
        confidence=confidence.confidence,
        band=confidence.band,
        ranked_candidates=ranked,
        explanation=explanation,
        signals=signals,
        llm_used=llm_used,
        llm_degraded=llm_degraded,
    )
