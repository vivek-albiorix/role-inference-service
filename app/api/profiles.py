from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.schemas import ProfileIngestedOut, SSOProfileIn
from app.services.ingestion import ingest_profile
from app.services.inference_service import run_and_persist_inference

router = APIRouter(tags=["profiles"])


@router.post("/profiles", response_model=ProfileIngestedOut, status_code=201)
def create_profile(payload: SSOProfileIn, session: Session = Depends(get_session)) -> ProfileIngestedOut:
    """Ingests an SSO payload as a new, versioned Profile snapshot and
    synchronously runs inference. Synchronous because the dataset here is
    tiny; `run_and_persist_inference` is the seam a background worker would
    call instead at real scale (see README)."""
    user, profile = ingest_profile(session, payload)
    run = run_and_persist_inference(session, user, profile, actor="system:ingestion")
    session.commit()
    return ProfileIngestedOut(user_id=user.external_id, profile_version=profile.version, inference_run_id=run.id)
