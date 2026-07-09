"""Central, tunable configuration for the inference pipeline.

Kept as one importable object (not scattered constants) so weights and thresholds
are easy to find, easy to override in tests, and easy to promote to per-tenant
config later without touching pipeline code.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- External services -------------------------------------------------
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # --- Persistence ---------------------------------------------------------
    database_url: str = "sqlite:///./role_inference.db"

    # --- Versioning (pinned onto every InferenceRun for reproducibility) -----
    engine_version: str = "1.0.0"
    prompt_version: str = "disambiguate-v1"
    catalog_version: int = 1

    # --- Stage 4: signal weights (renormalized over signals actually present
    # on a given profile, so partial profiles are scored on less evidence
    # rather than zeroed out) ------------------------------------------------
    weight_title: float = 0.32
    weight_department: float = 0.20
    weight_skills: float = 0.16
    weight_groups: float = 0.13
    weight_manager: float = 0.10
    weight_keywords: float = 0.05
    weight_location: float = 0.02
    weight_seniority: float = 0.02

    # --- Stage 5: when to escalate to the LLM ---------------------------------
    # If the gap between the top and second candidate's score is smaller than
    # this, the deterministic layers haven't produced a clear winner.
    ambiguity_margin_threshold: float = 0.08
    llm_max_retries: int = 2

    # --- Stage 6: confidence formula weights (raw = w1*S_top + w2*S_margin +
    # w3*C_coverage + w4*A_agreement) ------------------------------------------
    confidence_w_top: float = 0.35
    confidence_w_margin: float = 0.30
    confidence_w_coverage: float = 0.20
    confidence_w_agreement: float = 0.15

    # Penalties (multiplicative, each in [0, 1] as the *amount subtracted*)
    penalty_missing_title: float = 0.4
    penalty_conflict_max: float = 0.3
    penalty_manager_derived: float = 0.2

    # --- Confidence bands ------------------------------------------------------
    band_high: float = 0.85
    band_medium: float = 0.60
    band_low: float = 0.40


settings = Settings()
