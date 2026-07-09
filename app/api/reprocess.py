from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models.schemas import ReprocessRequestIn, ReprocessStartedOut, ReprocessStatusOut
from app.services import reprocess_service

router = APIRouter(tags=["reprocess"])


@router.post("/reprocess", response_model=ReprocessStartedOut, status_code=202)
def start_reprocess(payload: ReprocessRequestIn, background_tasks: BackgroundTasks) -> ReprocessStartedOut:
    """Starts bulk re-inference as a background task and returns
    immediately -- standing in for the event-driven worker a real
    catalog/org change would trigger at scale (see README). With
    `respect_pins=True` (default), users with an active *pinned* override
    are skipped entirely. Poll GET /reprocess/status for progress/results.

    Only one job runs at a time (in-memory tracker, see
    services/reprocess_service.py) -- a second request while one is running
    gets 409 rather than corrupting the running job's state."""
    if not reprocess_service.try_start_job():
        raise HTTPException(status_code=409, detail="A reprocess job is already running")
    background_tasks.add_task(reprocess_service.run_reprocess_job, payload.respect_pins, payload.reason)
    return ReprocessStartedOut(status="started")


@router.get("/reprocess/status", response_model=ReprocessStatusOut)
def get_reprocess_status() -> ReprocessStatusOut:
    status = reprocess_service.get_status()
    return ReprocessStatusOut(**status.__dict__)
