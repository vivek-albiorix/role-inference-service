"""Background bulk reprocessing.

`POST /api/reprocess` used to run this inline and block the request until
every user was re-inferred -- fine for 8 users, not a real "background"
behavior. This module makes it genuinely non-blocking: the endpoint starts
a FastAPI BackgroundTask and returns immediately; `GET /api/reprocess/status`
polls for progress/results.

State is a single in-process, in-memory job record -- lost on restart, not
shared across workers, and only one job can run at a time. That's the real
limitation to be honest about: the seam for a production version is a queue
+ worker pool (the actual per-user work, `run_and_persist_inference`,
already doesn't care who calls it -- see services/inference_service.py).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app import db as db_module
from app.models.tables import Override, Profile, User
from app.services.inference_service import run_and_persist_inference


@dataclass
class ReprocessJobStatus:
    state: str = "idle"  # idle | running | completed | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    processed_count: int = 0
    skipped_pinned_count: int = 0
    user_ids_processed: list[str] = field(default_factory=list)
    user_ids_skipped: list[str] = field(default_factory=list)
    error: str | None = None


_lock = threading.Lock()
_status = ReprocessJobStatus()


def get_status() -> ReprocessJobStatus:
    with _lock:
        return ReprocessJobStatus(**_status.__dict__)


def reset_for_tests() -> None:
    """Test-only: force the tracker back to idle. Needed because this is
    module-level state shared across the whole test process -- without a
    reset between tests, one test starting a job (or simulating one running,
    to exercise the 409 path) would leak "running" into every test after
    it."""
    global _status
    with _lock:
        _status = ReprocessJobStatus()


def try_start_job() -> bool:
    """Returns False (caller should reject with 409) if a job is already
    running -- this in-memory tracker only ever represents one job at a
    time, so a second concurrent bulk reprocess would corrupt its state."""
    global _status
    with _lock:
        if _status.state == "running":
            return False
        _status = ReprocessJobStatus(state="running", started_at=datetime.now(timezone.utc))
        return True


def run_reprocess_job(respect_pins: bool, reason: str | None) -> None:
    """Entry point for the FastAPI BackgroundTask. Opens its own DB session
    -- the request's session may already be closed by the time this runs,
    since background tasks execute after the response has been sent.

    Looks up `db_module.SessionLocal` at call time (not `from app.db import
    SessionLocal` at module import time) specifically so tests can
    monkeypatch `app.db.SessionLocal` to the isolated per-test engine and
    have this background task honor it -- otherwise it would silently write
    to the real dev database instead of the test's temp SQLite file, which
    is exactly what happened before this was fixed (caught by actually
    running the tests, not assumed)."""
    session = db_module.SessionLocal()
    processed: list[str] = []
    skipped: list[str] = []
    try:
        users = session.query(User).order_by(User.external_id).all()
        for user in users:
            active_override = session.query(Override).filter_by(user_id=user.id, active=True).one_or_none()
            if respect_pins and active_override and active_override.pinned:
                skipped.append(user.external_id)
                continue

            profile = (
                session.query(Profile).filter_by(user_id=user.id).order_by(Profile.version.desc()).first()
            )
            if profile is None:
                continue

            actor = f"system:reprocess({reason or 'unspecified'})"
            run_and_persist_inference(session, user, profile, actor=actor)
            session.commit()
            processed.append(user.external_id)

        with _lock:
            _status.state = "completed"
            _status.finished_at = datetime.now(timezone.utc)
            _status.processed_count = len(processed)
            _status.skipped_pinned_count = len(skipped)
            _status.user_ids_processed = processed
            _status.user_ids_skipped = skipped
    except Exception as exc:  # noqa: BLE001 -- background task; must record failure, not raise into the void
        session.rollback()
        with _lock:
            _status.state = "failed"
            _status.finished_at = datetime.now(timezone.utc)
            _status.error = str(exc)
    finally:
        session.close()
