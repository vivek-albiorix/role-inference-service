"""Typed data structures passed between pipeline stages.

Kept as Pydantic models (not plain dicts) so each stage has a validated,
self-documenting contract -- consistent with the DTOs at the API boundary,
just scoped to the pipeline's internal use.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CatalogRole(BaseModel):
    """A pipeline-local view of a Work Architecture role. Deliberately not
    the SQLAlchemy `Role` model -- the pipeline never imports the ORM, so it
    stays testable with plain objects and storage-agnostic."""

    model_config = {"from_attributes": True}

    role_id: str
    role_name: str
    department: str
    job_family: str
    seniority: str
    skills: list[str]
    keywords: list[str]


class NormalizedProfile(BaseModel):
    """Output of Stage 1 (normalize). Raw values are preserved alongside
    normalized ones so nothing is silently lost for audit/display."""

    external_id: str
    source: str
    display_name: str | None

    title_raw: str | None
    title_normalized: str | None
    title_is_empty: bool
    title_is_generic: bool
    title_has_vanity: bool

    department_raw: str | None
    department_normalized: str | None

    manager_title_raw: str | None
    manager_title_normalized: str | None

    skills_raw: list[str]
    skills_normalized: list[str]

    groups_raw: list[str]
    groups_normalized: list[str]

    location_raw: str | None
    location_normalized: str | None

    notes_raw: str | None
    notes_normalized: str | None


class SignalBundle(BaseModel):
    """Output of Stage 2 (extract signals): structured features pulled out
    of the normalized profile, ready to be weighed against the catalog."""

    seniority_level: str | None = None
    seniority_source: str | None = None  # 'title' | 'manager_title' | None

    department_normalized: str | None = None

    manager_function_hint: str | None = None

    skills: set[str] = Field(default_factory=set)

    groups: set[str] = Field(default_factory=set)
    group_function_hints: set[str] = Field(default_factory=set)
    employment_type_hint: str | None = None

    keyword_bag: set[str] = Field(default_factory=set)
    # Natural left-to-right concatenation of the same source text (title,
    # department, notes, manager title) preserving word order -- unlike
    # keyword_bag (an unordered set), this supports matching multi-word
    # catalog keywords like "engineering manager" or "team lead".
    keyword_text: str = ""

    notes_function_hint: str | None = None

    location_normalized: str | None = None

    # Which signal categories are actually present & trusted on this
    # profile. Drives both scoring renormalization and confidence coverage.
    present_signals: set[str] = Field(default_factory=set)


class SignalContribution(BaseModel):
    """One signal's evidence for/against a single candidate role."""

    signal: str
    detail: str
    score: float  # 0..1, how strongly this signal points to this role
    weight: float  # this signal's configured weight
    supports: bool  # score above a "meaningfully supports" threshold


class ScoredCandidate(BaseModel):
    """Output of Stages 3+4: a role with its per-signal evidence and the
    fused weighted score used for ranking."""

    role_id: str
    role_name: str
    contributions: list[SignalContribution]
    score: float  # weighted, renormalized sum in [0, 1]


class LLMDisambiguationResult(BaseModel):
    """Output of Stage 5. `used=False` means the deterministic stub ran
    instead of a real model call (no API key, or the call failed/was
    invalid after retries) -- `degraded` mirrors that for persistence."""

    chosen_role_id: str  # a shortlist role_id, or "none"
    rationale: str
    used: bool
    degraded: bool


class ConfidenceResult(BaseModel):
    """Output of Stage 6: the calibrated confidence number decomposed into
    its inputs, so the explanation can show its work rather than asserting
    a bare float."""

    confidence: float
    band: str
    s_top: float
    s_margin: float
    c_coverage: float
    a_agreement: float
    p_conflict: float
    p_missing: float
    p_stale: float


class SignalEvidenceItem(BaseModel):
    signal: str
    value: str
    weight: float
    supports: bool


class AlternativeRoleItem(BaseModel):
    role: str
    role_id: str
    confidence: float
    why_lost: str | None = None


class ExplanationBundle(BaseModel):
    """Output of Stage 7. Assembled entirely from stage 3/4 evidence (plus
    an optional LLM rationale note) -- never free-form LLM prose standing
    on its own, so it can never contradict the structured fields."""

    human_readable: str
    signals: list[str]
    signals_used: list[SignalEvidenceItem]
    positive_evidence: list[str]
    negative_evidence: list[str]
    alternative_roles: list[AlternativeRoleItem]
    why_winner_won: str | None
    missing_information: list[str]


class PipelineResult(BaseModel):
    """Final output of the orchestrator: everything the service layer needs
    to persist an InferenceRun and build an API response. Pure data -- no
    DB access happens inside the pipeline package."""

    inferred_role_id: str | None
    inferred_role_name: str | None
    confidence: float
    band: str
    ranked_candidates: list[ScoredCandidate]
    explanation: ExplanationBundle
    signals: SignalBundle
    llm_used: bool
    llm_degraded: bool
