from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.tables import Profile, User


def get_user_or_404(session: Session, user_id: str) -> User:
    user = session.query(User).filter_by(external_id=user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown user_id '{user_id}'")
    return user


def get_latest_profile_or_404(session: Session, user: User) -> Profile:
    profile = (
        session.query(Profile).filter_by(user_id=user.id).order_by(Profile.version.desc()).first()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail=f"User '{user.external_id}' has no ingested profile yet")
    return profile
