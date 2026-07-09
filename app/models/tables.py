"""SQLAlchemy ORM tables.

Mirrors the shape in the architecture notes, scoped down for a single tenant:
Role (catalog) -> User -> Profile (versioned, append-only) -> InferenceRun
(immutable) -> Override (append-only) -> Mapping (materialized effective role)
-> AuditLog (append-only). Profiles, inference runs, and overrides are never
mutated in place; Mapping is the only row that gets updated, and it can always
be rebuilt from the append-only tables above it.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Role(Base):
    """Canonical Work Architecture catalog entry."""

    __tablename__ = "roles"

    role_id: Mapped[str] = mapped_column(String, primary_key=True)
    role_name: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, nullable=False)
    job_family: Mapped[str] = mapped_column(String, nullable=False)
    seniority: Mapped[str] = mapped_column(String, nullable=False)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class User(Base):
    """A person, identified by a provider-agnostic external id."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    profiles: Mapped[list["Profile"]] = relationship(back_populates="user", order_by="Profile.version")


class Profile(Base):
    """A versioned, append-only snapshot of a raw SSO payload."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    ingested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped[User] = relationship(back_populates="profiles")


class InferenceRun(Base):
    """An immutable record of one inference pipeline execution."""

    __tablename__ = "inference_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    chosen_role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.role_id"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String, nullable=False)
    candidates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    explanation_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    signals_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    llm_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_degraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    engine_version: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )


class Override(Base):
    """A human decision, layered over inference rather than replacing it.

    Reset never deletes a row -- it flips `active` to False so the full
    override history (who, when, why) stays intact for audit purposes.
    """

    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.role_id"), nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Mapping(Base):
    """Materialized read model: the current effective role for a user.

    effective_role = active override's role, if one exists, else the most
    recent inference run's chosen role. Always rebuildable from the
    append-only tables above -- this table exists purely for fast reads.
    """

    __tablename__ = "mappings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    effective_role_id: Mapped[str | None] = mapped_column(ForeignKey("roles.role_id"), nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)  # 'inferred' | 'overridden'
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    catalog_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class AuditLog(Base):
    """Append-only who/what/when/why record for every mutating action."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
