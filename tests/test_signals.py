from app.models.schemas import SSOProfileIn
from app.pipeline.normalize import normalize_profile
from app.pipeline.signals import extract_signals


def _signals_for(**kwargs) -> tuple:
    profile = SSOProfileIn(user_id="usr_test", **kwargs)
    normalized = normalize_profile(profile)
    return normalized, extract_signals(normalized)


def test_seniority_extracted_from_title():
    _, signals = _signals_for(title="Sr BI Analyst")
    assert signals.seniority_level == "senior"
    assert signals.seniority_source == "title"


def test_seniority_defaults_to_mid_when_title_present_without_level_word():
    _, signals = _signals_for(title="Data Analyst")
    assert signals.seniority_level == "mid"


def test_seniority_none_when_no_title():
    _, signals = _signals_for()
    assert signals.seniority_level is None
    assert "seniority" not in signals.present_signals


def test_manager_function_hint_prefers_more_specific_phrase():
    _, signals = _signals_for(manager_title="Director of Sales Operations")
    assert signals.manager_function_hint == "revops_sales"


def test_manager_function_hint_handles_cto_abbreviation():
    _, signals = _signals_for(manager_title="CTO")
    assert signals.manager_function_hint == "engineering"


def test_group_function_hints_and_employment_type():
    _, signals = _signals_for(groups=["tableau-users", "data-team", "all-staff", "contractors"])
    assert "analytics" in signals.group_function_hints
    assert signals.employment_type_hint == "contractor"


def test_all_staff_alone_does_not_count_as_a_present_group_signal():
    _, signals = _signals_for(groups=["all-staff"])
    assert "groups" not in signals.present_signals


def test_notes_function_hint_flags_sales_background():
    _, signals = _signals_for(notes="Transferred from Sales team 3 months ago")
    assert signals.notes_function_hint == "revops_sales"


def test_empty_profile_has_minimal_present_signals():
    _, signals = _signals_for(groups=["contractors"])
    assert signals.present_signals == set()
    assert signals.employment_type_hint == "contractor"
