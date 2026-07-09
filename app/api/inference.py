from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_latest_profile_or_404, get_user_or_404
from app.db import get_session
from app.models.schemas import InferenceResultOut, InferRequestIn
from app.models.tables import InferenceRun
from app.services.inference_service import build_inference_result_out, run_and_persist_inference

router = APIRouter(tags=["inference"])


@router.post("/infer", response_model=InferenceResultOut)
def force_infer(payload: InferRequestIn, session: Session = Depends(get_session)) -> InferenceResultOut:
    """Re-runs inference for a user who already has at least one ingested
    profile. Always stores a fresh InferenceRun (even under an active
    override) so the underlying model can be compared against the
    standing human decision -- see services/inference_service.py."""
    user = get_user_or_404(session, payload.user_id)
    profile = get_latest_profile_or_404(session, user)
    run = run_and_persist_inference(session, user, profile, actor="admin:manual_infer")
    session.commit()
    return build_inference_result_out(run, user.external_id)


@router.get("/users/{user_id}/inference", response_model=InferenceResultOut)
def get_latest_inference(user_id: str, session: Session = Depends(get_session)) -> InferenceResultOut:
    user = get_user_or_404(session, user_id)
    run = (
        session.query(InferenceRun)
        .filter_by(user_id=user.id)
        .order_by(InferenceRun.created_at.desc())
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail=f"No inference runs yet for '{user_id}'")
    return build_inference_result_out(run, user.external_id)
