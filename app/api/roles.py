from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.schemas import RoleOut
from app.models.tables import Role

router = APIRouter(tags=["roles"])


@router.get("/roles", response_model=list[RoleOut])
def list_roles(session: Session = Depends(get_session)) -> list[RoleOut]:
    rows = session.query(Role).order_by(Role.role_id).all()
    return [RoleOut.model_validate(row) for row in rows]
