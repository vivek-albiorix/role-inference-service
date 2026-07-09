from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.config import settings
from app.models.schemas import RoleIn
from app.models.tables import Role
from app.pipeline.types import CatalogRole
from app.services.audit import write_audit_log

_ROLE_ID_PATTERN = re.compile(r"role_(\d+)")


def load_catalog_roles(session: Session) -> list[CatalogRole]:
    rows = session.query(Role).order_by(Role.role_id).all()
    return [CatalogRole.model_validate(row) for row in rows]


def _next_role_id(session: Session) -> str:
    """Continues the seed catalog's `role_NNN` numbering rather than a slug
    or UUID, so admin-created roles look identical to seeded ones. Scans all
    existing ids for the highest numeric suffix instead of counting rows,
    so it stays correct even if a role_id doesn't fit the pattern or ids
    aren't contiguous."""
    highest = 0
    for (role_id,) in session.query(Role.role_id).all():
        match = _ROLE_ID_PATTERN.fullmatch(role_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"role_{highest + 1:03d}"


def create_role(session: Session, payload: RoleIn, actor: str) -> Role:
    """Adds a new role to the Work Architecture catalog. Existing users are
    left untouched -- a new role only affects future inference runs (or a
    manual re-infer/reprocess), never retroactively rewrites a stored
    Mapping. Stamped with the current global `catalog_version`; bumping that
    version to reflect a real catalog revision is a manual config change
    today (see README's known limitations -- no bitemporal role_versions
    table yet)."""
    role = Role(
        role_id=_next_role_id(session),
        role_name=payload.role_name,
        department=payload.department,
        job_family=payload.job_family,
        seniority=payload.seniority,
        skills=payload.skills,
        keywords=payload.keywords,
        catalog_version=settings.catalog_version,
    )
    session.add(role)
    session.flush()
    write_audit_log(
        session,
        actor=actor,
        action="role.created",
        entity_type="role",
        entity_id=role.role_id,
        after_json={
            "role_name": role.role_name,
            "department": role.department,
            "job_family": role.job_family,
            "seniority": role.seniority,
        },
    )
    session.flush()
    return role
