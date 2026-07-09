"""Read-model assembly for API responses. Pulls together Mapping, Override,
Profile, and Role rows into the DTOs clients consume -- kept separate from
the write-path services (ingestion/inference_service/override_service) so
each side can change independently.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models.schemas import EffectiveRoleOut, HistoryItemOut, UserDetailOut, UserSummaryOut
from app.models.tables import InferenceRun, Mapping, Override, Profile, Role, User
from app.pipeline.confidence import band_for


def _effective_role_out(
    session: Session, mapping: Mapping | None, active_override: Override | None
) -> EffectiveRoleOut:
    override_reason = active_override.reason if active_override else None
    if mapping is None or mapping.effective_role_id is None:
        source = mapping.source if mapping else "inferred"
        return EffectiveRoleOut(
            role_id=None,
            role_name=None,
            source=source,
            confidence=None,
            band=None,
            override_reason=override_reason if source == "overridden" else None,
        )

    role = session.get(Role, mapping.effective_role_id)
    band = band_for(mapping.confidence) if mapping.source == "inferred" and mapping.confidence is not None else None
    return EffectiveRoleOut(
        role_id=mapping.effective_role_id,
        role_name=role.role_name if role else None,
        source=mapping.source,
        confidence=mapping.confidence,
        band=band,
        override_reason=override_reason if mapping.source == "overridden" else None,
    )


def build_user_summary(session: Session, user: User) -> UserSummaryOut:
    mapping = session.get(Mapping, user.id)
    latest_profile = (
        session.query(Profile).filter_by(user_id=user.id).order_by(Profile.version.desc()).first()
    )
    active_override = session.query(Override).filter_by(user_id=user.id, active=True).one_or_none()

    title = latest_profile.raw_json.get("title") if latest_profile else None
    department = latest_profile.raw_json.get("department") if latest_profile else None

    return UserSummaryOut(
        user_id=user.external_id,
        display_name=user.display_name,
        title=title,
        department=department,
        effective_role=_effective_role_out(session, mapping, active_override),
        override_active=active_override is not None,
        override_pinned=bool(active_override and active_override.pinned),
    )


def build_user_detail(session: Session, user: User) -> UserDetailOut:
    summary = build_user_summary(session, user)
    latest_run = (
        session.query(InferenceRun).filter_by(user_id=user.id).order_by(InferenceRun.created_at.desc()).first()
    )
    return UserDetailOut(
        **summary.model_dump(),
        latest_inference_run_id=latest_run.id if latest_run else None,
        catalog_version=settings.catalog_version,
    )


def _role_name(session: Session, role_id: str | None) -> str | None:
    if role_id is None:
        return None
    role = session.get(Role, role_id)
    return role.role_name if role else role_id


def build_history(session: Session, user: User) -> list[HistoryItemOut]:
    items: list[HistoryItemOut] = []

    runs = session.query(InferenceRun).filter_by(user_id=user.id).order_by(InferenceRun.created_at.desc()).all()
    for run in runs:
        items.append(
            HistoryItemOut(
                type="inference",
                at=run.created_at,
                role_id=run.chosen_role_id,
                role_name=_role_name(session, run.chosen_role_id),
                confidence=run.confidence,
                band=run.band,
            )
        )

    overrides = session.query(Override).filter_by(user_id=user.id).order_by(Override.created_at.desc()).all()
    for override in overrides:
        items.append(
            HistoryItemOut(
                type="override",
                at=override.created_at,
                role_id=override.role_id,
                role_name=_role_name(session, override.role_id),
                pinned=override.pinned,
                by=override.created_by,
                reason=override.reason,
            )
        )

    items.sort(key=lambda item: item.at, reverse=True)
    return items
