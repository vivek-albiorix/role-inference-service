"""Pydantic DTOs for the API boundary.

Deliberately kept separate from app/models/tables.py (the ORM layer) so the
wire contract can evolve independently of storage -- e.g. we can reshape a
response without a migration, or reshape a table without breaking clients.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------


class SSOProfileIn(BaseModel):
    """Canonical shape this service accepts.

    Real Okta/Entra/Google payloads differ (`jobTitle` vs `profile.title` vs
    nested `organizations[]`); a thin per-provider adapter in
    `app/services/ingestion.py` is the seam where that translation would
    happen. All 8 assignment sample payloads already arrive in this shape,
    so that adapter is currently a pass-through plus light source-detection.
    """

    user_id: str
    display_name: str | None = None
    title: str | None = None
    department: str | None = None
    manager_title: str | None = None
    groups: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    notes: str | None = None
    source: Literal["okta", "entra", "google", "unknown"] = "unknown"


class ProfileIngestedOut(BaseModel):
    user_id: str
    profile_version: int
    inference_run_id: int


# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: str
    role_name: str
    department: str
    job_family: str
    seniority: str
    skills: list[str]
    keywords: list[str]


# --------------------------------------------------------------------------
# Inference result / explanation
# --------------------------------------------------------------------------


class SignalEvidence(BaseModel):
    signal: str
    value: Any
    weight: float
    supports: bool


class AlternativeRole(BaseModel):
    role: str
    role_id: str
    confidence: float
    why_lost: str | None = None


class InferenceResultOut(BaseModel):
    """Shape follows the assignment's example output (inferred_role,
    confidence, explanation, signals, alternative_roles) and extends it with
    the structured, evidence-based fields from the architecture notes so an
    admin can drill into exactly why a decision was made.
    """

    run_id: int
    user_id: str
    profile_version: int
    catalog_version: int

    inferred_role: str | None
    role_id: str | None
    confidence: float
    band: Literal["high", "medium", "low", "very_low"]
    explanation: str
    signals: list[str]
    alternative_roles: list[AlternativeRole]

    signals_used: list[SignalEvidence]
    positive_evidence: list[str]
    negative_evidence: list[str]
    why_winner_won: str | None
    missing_information: list[str]

    llm_used: bool
    llm_degraded: bool
    engine_version: str
    prompt_version: str
    created_at: dt.datetime


# --------------------------------------------------------------------------
# Users / mappings
# --------------------------------------------------------------------------


class EffectiveRoleOut(BaseModel):
    role_id: str | None
    role_name: str | None
    source: Literal["inferred", "overridden"]
    confidence: float | None
    band: str | None = None


class UserSummaryOut(BaseModel):
    user_id: str
    display_name: str | None
    title: str | None
    department: str | None
    effective_role: EffectiveRoleOut
    override_active: bool
    override_pinned: bool


class UserDetailOut(UserSummaryOut):
    latest_inference_run_id: int | None
    catalog_version: int


# --------------------------------------------------------------------------
# Overrides
# --------------------------------------------------------------------------


class OverrideIn(BaseModel):
    role_id: str
    pinned: bool = True
    reason: str | None = None
    created_by: str = "admin"


class OverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_id: str
    pinned: bool
    reason: str | None
    created_by: str
    created_at: dt.datetime
    active: bool


# --------------------------------------------------------------------------
# History / audit
# --------------------------------------------------------------------------


class HistoryItemOut(BaseModel):
    type: Literal["inference", "override"]
    at: dt.datetime
    role_id: str | None
    role_name: str | None
    confidence: float | None = None
    band: str | None = None
    pinned: bool | None = None
    by: str | None = None
    reason: str | None = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: str
    before_json: dict | None
    after_json: dict | None
    reason: str | None
    created_at: dt.datetime


# --------------------------------------------------------------------------
# Reprocessing
# --------------------------------------------------------------------------


class ReprocessRequestIn(BaseModel):
    scope: Literal["all"] = "all"
    reason: str | None = None
    respect_pins: bool = True


class ReprocessResultOut(BaseModel):
    processed_count: int
    skipped_pinned_count: int
    user_ids_processed: list[str]
    user_ids_skipped: list[str]
