from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.api.deps import get_user_or_404
from app.db import get_session
from app.models.schemas import OverrideIn, OverrideOut
from app.models.tables import Role
from app.services.override_service import reset_override, set_override

router = APIRouter(tags=["overrides"])


@router.patch("/users/{user_id}/override", response_model=OverrideOut)
def create_override(
    user_id: str, payload: OverrideIn, session: Session = Depends(get_session)
) -> OverrideOut:
    user = get_user_or_404(session, user_id)
    if session.get(Role, payload.role_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown role_id '{payload.role_id}'")
    override = set_override(session, user, payload)
    session.commit()
    return OverrideOut.model_validate(override)


@router.delete("/users/{user_id}/override", status_code=204)
def delete_override(user_id: str, session: Session = Depends(get_session)) -> Response:
    user = get_user_or_404(session, user_id)
    reset_override(session, user, actor="admin")
    session.commit()
    return Response(status_code=204)
