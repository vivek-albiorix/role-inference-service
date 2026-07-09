from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_user_or_404
from app.db import get_session
from app.models.schemas import AuditLogOut, HistoryItemOut
from app.models.tables import AuditLog
from app.services.views import build_history

router = APIRouter(tags=["history"])


@router.get("/users/{user_id}/history", response_model=list[HistoryItemOut])
def get_user_history(user_id: str, session: Session = Depends(get_session)) -> list[HistoryItemOut]:
    user = get_user_or_404(session, user_id)
    return build_history(session, user)


@router.get("/audit", response_model=list[AuditLogOut])
def get_audit_log(
    entity_type: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    session: Session = Depends(get_session),
) -> list[AuditLogOut]:
    query = session.query(AuditLog)
    if entity_type:
        query = query.filter_by(entity_type=entity_type)
    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [AuditLogOut.model_validate(row) for row in rows]
