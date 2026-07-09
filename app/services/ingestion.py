"""Provider-shaped payload -> canonical profile, persisted as a new,
append-only Profile version.

All 8 assignment sample payloads already arrive in the canonical
`SSOProfileIn` shape, so this is currently a pass-through plus versioning.
A real Okta/Entra/Google adapter (translating `jobTitle` vs `profile.title`
vs nested `organizations[]` into this shape) would slot in here without
touching anything downstream.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.schemas import SSOProfileIn
from app.models.tables import Profile, User
from app.pipeline.normalize import normalize_profile


def ingest_profile(session: Session, payload: SSOProfileIn) -> tuple[User, Profile]:
    user = session.query(User).filter_by(external_id=payload.user_id).one_or_none()
    if user is None:
        user = User(external_id=payload.user_id, source=payload.source, display_name=payload.display_name)
        session.add(user)
        session.flush()
    else:
        user.source = payload.source
        if payload.display_name:
            user.display_name = payload.display_name

    latest_version = (
        session.query(func.max(Profile.version)).filter_by(user_id=user.id).scalar() or 0
    )
    normalized = normalize_profile(payload)

    profile = Profile(
        user_id=user.id,
        version=latest_version + 1,
        source=payload.source,
        raw_json=payload.model_dump(),
        normalized_json=normalized.model_dump(),
    )
    session.add(profile)
    session.flush()
    return user, profile
