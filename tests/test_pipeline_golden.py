"""End-to-end pipeline regression tests against the 8 assignment sample
users. Assertions are deliberately band/top-candidate based rather than
pinned to exact confidence floats -- tuning a signal weight shouldn't break
this suite unless it changes the actual decision. Run with no OPENAI_API_KEY
set (the default in CI/dev) so Stage 5 always exercises the deterministic
stub fallback -- this keeps the suite hermetic while still covering the
ambiguity-escalation code path itself.
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.models.schemas import SSOProfileIn
from app.pipeline.catalog import load_catalog_roles, load_sample_sso_profiles
from app.pipeline.orchestrator import run_inference

ROLES = load_catalog_roles()
PROFILES_BY_ID = {p["user_id"]: p for p in load_sample_sso_profiles()}


@pytest.fixture(autouse=True)
def _no_llm_api_key(monkeypatch):
    # Deterministic regardless of the local environment's .env.
    monkeypatch.setattr(settings, "openai_api_key", None)


def _infer(user_id: str):
    profile = SSOProfileIn(**PROFILES_BY_ID[user_id])
    return run_inference(profile, ROLES)


def test_usr_001_sr_bi_analyst_maps_to_senior_data_analyst():
    result = _infer("usr_001")
    assert result.inferred_role_id == "role_001"  # Senior Data Analyst, not the Mid-level Data Analyst
    assert result.band in {"high", "medium"}


def test_usr_002_platform_engineer_ii_maps_to_platform_engineer():
    result = _infer("usr_002")
    assert result.inferred_role_id == "role_006"
    assert result.band in {"high", "medium", "low"}


def test_usr_003_customer_outcomes_lead_generalizes_to_customer_success_manager():
    """Title doesn't literally contain 'customer success' -- department,
    manager, and group signals should still carry this to the right role."""
    result = _infer("usr_003")
    assert result.inferred_role_id == "role_007"


def test_usr_004_product_strategy_manager_is_genuinely_ambiguous_and_escalates_to_llm():
    """Product Manager vs Senior Product Manager should be tight enough
    that the deterministic margin falls below the ambiguity threshold."""
    result = _infer("usr_004")
    assert result.inferred_role_id in {"role_003", "role_004"}
    assert result.llm_degraded is True  # stub ran since no API key is configured
    top_two = result.ranked_candidates[:2]
    assert {c.role_id for c in top_two} == {"role_003", "role_004"}


def test_usr_005_revenue_operations_specialist_maps_to_revenue_operations_manager():
    result = _infer("usr_005")
    assert result.inferred_role_id == "role_009"


def test_usr_006_generic_analyst_with_conflicting_notes_is_honestly_ambiguous():
    """Generic title, vague department, no skills, and notes suggesting a
    recent transfer -- the system should refuse to guess rather than force
    a confident-sounding wrong answer."""
    result = _infer("usr_006")
    assert result.inferred_role_id is None
    assert result.band == "very_low"
    assert "review" in result.explanation.human_readable.lower()


def test_usr_007_lead_in_engineering_is_low_confidence_and_flags_generic_title():
    """'Lead' alone in Engineering with ML/data skills is plausible for
    multiple roles -- should not be assigned with high confidence, and the
    explanation should call out that the title was too generic to rely on."""
    result = _infer("usr_007")
    assert result.band in {"low", "very_low"}
    assert "generic" in result.explanation.human_readable.lower()


def test_usr_008_empty_profile_refuses_to_infer():
    result = _infer("usr_008")
    assert result.inferred_role_id is None
    assert result.confidence == 0.0
    assert result.band == "very_low"
    assert len(result.explanation.missing_information) >= 3


@pytest.mark.parametrize("user_id", list(PROFILES_BY_ID.keys()))
def test_pipeline_never_crashes_on_any_sample_profile(user_id):
    result = _infer(user_id)
    assert result.band in {"high", "medium", "low", "very_low"}
    assert 0.0 <= result.confidence <= 1.0
