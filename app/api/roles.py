from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models.schemas import RoleIn, RoleOut
from app.models.tables import Role
from app.services.catalog import create_role

router = APIRouter(tags=["roles"])


@router.get("/roles", response_model=list[RoleOut])
def list_roles(session: Session = Depends(get_session)) -> list[RoleOut]:
    rows = session.query(Role).order_by(Role.role_id).all()
    return [RoleOut.model_validate(row) for row in rows]


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role_endpoint(payload: RoleIn, session: Session = Depends(get_session)) -> RoleOut:
    """Admin-authored addition to the Work Architecture catalog -- see
    services/catalog.py::create_role for the reasoning on catalog_version,
    server-generated role_id, and why existing users aren't retroactively
    touched. role_id is computed from existing rows, not client-supplied, so
    there's no admin-facing duplicate to reject -- the only way this can
    still collide is two requests computing the same next id concurrently,
    handled below rather than left to crash as an unhandled 500."""
    role = create_role(session, payload, actor="admin")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="role_id collision from a concurrent request -- please retry")
    return RoleOut.model_validate(role)
