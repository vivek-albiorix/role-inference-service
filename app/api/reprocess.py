from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.schemas import ReprocessRequestIn, ReprocessResultOut
from app.models.tables import Override, Profile, User
from app.services.inference_service import run_and_persist_inference

router = APIRouter(tags=["reprocess"])


@router.post("/reprocess", response_model=ReprocessResultOut)
def reprocess(payload: ReprocessRequestIn, session: Session = Depends(get_session)) -> ReprocessResultOut:
    """Bulk re-infer every user, standing in for the event-driven worker a
    real catalog/org change would trigger at scale (see README). With
    `respect_pins=True` (default), users with an active *pinned* override
    are skipped entirely -- their standing decision is a deliberate
    "don't touch," so there's no reason to spend a pipeline run confirming
    it. Active but unpinned overrides still get a fresh InferenceRun (for
    drift comparison); the override still wins the effective role."""
    users = session.query(User).order_by(User.external_id).all()
    processed: list[str] = []
    skipped: list[str] = []

    for user in users:
        active_override = session.query(Override).filter_by(user_id=user.id, active=True).one_or_none()
        if payload.respect_pins and active_override and active_override.pinned:
            skipped.append(user.external_id)
            continue

        profile = (
            session.query(Profile).filter_by(user_id=user.id).order_by(Profile.version.desc()).first()
        )
        if profile is None:
            continue

        actor = f"system:reprocess({payload.reason or 'unspecified'})"
        run_and_persist_inference(session, user, profile, actor=actor)
        processed.append(user.external_id)

    session.commit()
    return ReprocessResultOut(
        processed_count=len(processed),
        skipped_pinned_count=len(skipped),
        user_ids_processed=processed,
        user_ids_skipped=skipped,
    )
