"""Orchestrator -- runs stages 1-7 in order and assembles a PipelineResult.

Stateless coordinator: it owns *when* each stage runs (including the
short-circuit around Stage 5) but not *how* any stage works. Pure function
of (profile, catalog) -> PipelineResult; no DB access happens here, so it's
testable without a database and the service layer decides how to persist
the result (see app/services/inference_service.py).

Also times each stage with time.perf_counter() -- observability, not a
performance-critical measurement -- so the persisted InferenceRun (and the
API response) can show exactly where time went, and in particular isolate
the one stage (5, LLM disambiguation) whose latency is network-bound and
variable rather than sub-millisecond and deterministic like the rest.
"""

from __future__ import annotations

import time

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


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def run_inference(profile: SSOProfileIn, roles: list[CatalogRole]) -> PipelineResult:
    timings: dict[str, float] = {}

    # Stage 1
    t0 = time.perf_counter()
    normalized = normalize_profile(profile)
    timings["1_normalize"] = _elapsed_ms(t0)

    # Stage 2
    t0 = time.perf_counter()
    signals = extract_signals(normalized)
    timings["2_signals"] = _elapsed_ms(t0)

    roles_by_id = {role.role_id: role for role in roles}

    # Stage 3
    t0 = time.perf_counter()
    contributions_by_role = generate_candidates(
        signals, normalized.title_normalized, normalized.title_is_generic, normalized.title_has_vanity, roles
    )
    timings["3_candidates"] = _elapsed_ms(t0)

    # Stage 4
    t0 = time.perf_counter()
    ranked = rank_candidates(contributions_by_role, roles_by_id)
    margin = compute_margin(ranked)
    timings["4_scoring"] = _elapsed_ms(t0)

    # Stage 5 -- only when the deterministic layers haven't already agreed
    viable = [c for c in ranked if c.score > 0]
    llm_used = False
    llm_degraded = False
    llm_cached = False
    llm_note: str | None = None

    if len(viable) >= 2 and margin < settings.ambiguity_margin_threshold:
        t0 = time.perf_counter()
        shortlist = viable[:_LLM_SHORTLIST_SIZE]
        llm_result = disambiguate(shortlist, normalized, signals)
        timings["5_llm_disambiguation"] = _elapsed_ms(t0)
        llm_used = llm_result.used
        llm_degraded = llm_result.degraded
        llm_cached = llm_result.cached
        llm_note = llm_result.rationale
        if llm_result.chosen_role_id not in ("none", ranked[0].role_id):
            chosen = next(c for c in ranked if c.role_id == llm_result.chosen_role_id)
            ranked.remove(chosen)
            ranked.insert(0, chosen)
            margin = compute_margin(ranked)

    winner = ranked[0] if ranked and ranked[0].score > 0 else None

    # Stage 6
    t0 = time.perf_counter()
    if winner:
        confidence = compute_confidence(signals.present_signals, winner.score, margin, winner.contributions)
    else:
        confidence = compute_confidence(set(), 0.0, 0.0, [])
    timings["6_confidence"] = _elapsed_ms(t0)

    assigned = winner is not None and confidence.band != "very_low"

    # Stage 7
    t0 = time.perf_counter()
    explanation = build_explanation(normalized, signals, ranked, roles_by_id, confidence, assigned, llm_note)
    timings["7_explanation"] = _elapsed_ms(t0)

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
        llm_cached=llm_cached,
        stage_timings_ms=timings,
    )
