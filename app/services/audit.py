"""Append-only who/what/when/why log. Every mutating action in the override
and inference services writes here; entries are never updated or deleted.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.tables import AuditLog


def write_audit_log(
    session: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    before_json: dict | None = None,
    after_json: dict | None = None,
    reason: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_json=before_json,
        after_json=after_json,
        reason=reason,
    )
    session.add(entry)
    session.flush()
    return entry
