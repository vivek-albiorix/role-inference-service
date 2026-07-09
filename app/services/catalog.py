from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.tables import Role
from app.pipeline.types import CatalogRole


def load_catalog_roles(session: Session) -> list[CatalogRole]:
    rows = session.query(Role).order_by(Role.role_id).all()
    return [CatalogRole.model_validate(row) for row in rows]
