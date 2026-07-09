"""Runs the pipeline orchestrator and persists its result.

This is the seam the architecture notes call out: `POST /profiles` calls
this synchronously today because the dataset is tiny, but a bulk/background
path (queue consumer reacting to a `ProfileUpdated` event) would call the
exact same function -- the pipeline itself has no idea which path invoked
it.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.schemas import InferenceResultOut, SSOProfileIn
from app.models.tables import InferenceRun, Mapping, Override, Profile, User
from app.pipeline.orchestrator import run_inference
from app.services.audit import write_audit_log
from app.services.catalog import load_catalog_roles


def run_and_persist_inference(session: Session, user: User, profile: Profile, actor: str) -> InferenceRun:
    roles = load_catalog_roles(session)
    profile_in = SSOProfileIn(**profile.raw_json)
    result = run_inference(profile_in, roles)

    run = InferenceRun(
        user_id=user.id,
        profile_version=profile.version,
        catalog_version=settings.catalog_version,
        chosen_role_id=result.inferred_role_id,
        confidence=result.confidence,
        band=result.band,
        candidates_json=[c.model_dump() for c in result.ranked_candidates],
        explanation_json=result.explanation.model_dump(),
        signals_json=result.signals.model_dump(mode="json"),
        llm_used=result.llm_used,
        llm_degraded=result.llm_degraded,
        engine_version=settings.engine_version,
        prompt_version=settings.prompt_version,
    )
    session.add(run)
    session.flush()

    _update_mapping(session, user, run)
    write_audit_log(
        session,
        actor=actor,
        action="inference.completed",
        entity_type="user",
        entity_id=user.external_id,
        after_json={"role_id": run.chosen_role_id, "confidence": run.confidence, "band": run.band},
    )
    return run


def _update_mapping(session: Session, user: User, run: InferenceRun) -> Mapping:
    """Effective role = active override's role, if one exists, else this
    run's chosen role. An inference run is always stored and always
    recomputes this projection -- even under an active override -- so
    overrides never block the underlying model from being compared against
    (drift detection), they just win the effective-role assignment."""
    active_override = session.query(Override).filter_by(user_id=user.id, active=True).one_or_none()
    if active_override:
        effective_role_id, source, confidence = active_override.role_id, "overridden", None
    else:
        effective_role_id, source, confidence = run.chosen_role_id, "inferred", run.confidence

    mapping = session.get(Mapping, user.id)
    if mapping is None:
        mapping = Mapping(
            user_id=user.id,
            effective_role_id=effective_role_id,
            source=source,
            confidence=confidence,
            catalog_version=run.catalog_version,
        )
        session.add(mapping)
    else:
        mapping.effective_role_id = effective_role_id
        mapping.source = source
        mapping.confidence = confidence
        mapping.catalog_version = run.catalog_version
    session.flush()
    return mapping


def build_inference_result_out(run: InferenceRun, user_external_id: str) -> InferenceResultOut:
    role_name = None
    if run.chosen_role_id:
        match = next((c for c in run.candidates_json if c["role_id"] == run.chosen_role_id), None)
        role_name = match["role_name"] if match else run.chosen_role_id

    explanation = run.explanation_json
    return InferenceResultOut(
        run_id=run.id,
        user_id=user_external_id,
        profile_version=run.profile_version,
        catalog_version=run.catalog_version,
        inferred_role=role_name,
        role_id=run.chosen_role_id,
        confidence=run.confidence,
        band=run.band,
        explanation=explanation["human_readable"],
        signals=explanation["signals"],
        alternative_roles=explanation["alternative_roles"],
        signals_used=explanation["signals_used"],
        positive_evidence=explanation["positive_evidence"],
        negative_evidence=explanation["negative_evidence"],
        why_winner_won=explanation.get("why_winner_won"),
        missing_information=explanation["missing_information"],
        llm_used=run.llm_used,
        llm_degraded=run.llm_degraded,
        engine_version=run.engine_version,
        prompt_version=run.prompt_version,
        created_at=run.created_at,
    )
