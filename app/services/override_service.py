"""Human decisions, layered over inference rather than replacing it.

Setting an override never deletes or mutates a prior one -- it deactivates
it (active=False) and appends a new row, so the full override history stays
intact for audit. Resetting reverts the effective role to the latest
inference run, re-enabling automatic reprocessing.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.schemas import OverrideIn
from app.models.tables import InferenceRun, Mapping, Override, User
from app.services.audit import write_audit_log


def set_override(session: Session, user: User, payload: OverrideIn) -> Override:
    previous = session.query(Override).filter_by(user_id=user.id, active=True).one_or_none()
    before_role_id = previous.role_id if previous else None
    if previous:
        previous.active = False

    override = Override(
        user_id=user.id,
        role_id=payload.role_id,
        pinned=payload.pinned,
        reason=payload.reason,
        created_by=payload.created_by,
        active=True,
    )
    session.add(override)
    session.flush()

    mapping = session.get(Mapping, user.id)
    if mapping is None:
        mapping = Mapping(user_id=user.id, effective_role_id=override.role_id, source="overridden", confidence=None, catalog_version=0)
        session.add(mapping)
    else:
        mapping.effective_role_id = override.role_id
        mapping.source = "overridden"
        mapping.confidence = None

    write_audit_log(
        session,
        actor=payload.created_by,
        action="override.created",
        entity_type="user",
        entity_id=user.external_id,
        before_json={"role_id": before_role_id},
        after_json={"role_id": override.role_id, "pinned": override.pinned},
        reason=payload.reason,
    )
    session.flush()
    return override


def reset_override(session: Session, user: User, actor: str) -> bool:
    """Returns False (a no-op) if there was no active override to reset --
    reset is idempotent rather than an error."""
    active = session.query(Override).filter_by(user_id=user.id, active=True).one_or_none()
    if active is None:
        return False
    active.active = False

    latest_run = (
        session.query(InferenceRun)
        .filter_by(user_id=user.id)
        .order_by(InferenceRun.created_at.desc())
        .first()
    )
    mapping = session.get(Mapping, user.id)
    if mapping is not None:
        if latest_run:
            mapping.effective_role_id = latest_run.chosen_role_id
            mapping.source = "inferred"
            mapping.confidence = latest_run.confidence
            mapping.catalog_version = latest_run.catalog_version
        else:
            mapping.effective_role_id = None
            mapping.source = "inferred"
            mapping.confidence = None

    write_audit_log(
        session,
        actor=actor,
        action="override.reset",
        entity_type="user",
        entity_id=user.external_id,
        before_json={"role_id": active.role_id},
        after_json={"role_id": latest_run.chosen_role_id if latest_run else None},
    )
    session.flush()
    return True
