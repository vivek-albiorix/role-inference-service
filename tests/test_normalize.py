from app.models.schemas import SSOProfileIn
from app.pipeline.normalize import clean_text, normalize_profile, normalize_title


def test_clean_text_folds_unicode_and_strips_punctuation():
    assert clean_text("Bergström") == "bergstrom"
    assert clean_text("Sr. BI-Analyst!") == "sr bi analyst"
    assert clean_text(None) is None
    assert clean_text("   ") is None


def test_normalize_title_expands_abbreviations_and_strips_level_suffix():
    normalized, is_empty, is_generic, has_vanity = normalize_title("Sr BI Analyst")
    assert normalized == "senior business intelligence analyst"
    assert is_empty is False
    assert is_generic is False
    assert has_vanity is False

    normalized, *_ = normalize_title("Platform Engineer II")
    assert normalized == "platform engineer"


def test_normalize_title_flags_generic_and_empty():
    _, _, is_generic, _ = normalize_title("Analyst")
    assert is_generic is True

    _, _, is_generic, _ = normalize_title("Lead")
    assert is_generic is True  # title is *only* a seniority word

    normalized, is_empty, is_generic, has_vanity = normalize_title(None)
    assert normalized is None
    assert is_empty is True


def test_normalize_title_flags_vanity():
    _, _, _, has_vanity = normalize_title("Growth Ninja")
    assert has_vanity is True


def test_normalize_profile_preserves_raw_alongside_normalized():
    profile = SSOProfileIn(
        user_id="usr_001",
        title="Sr BI Analyst",
        department="Data & Insights",
        manager_title="Director of Analytics",
        groups=["Tableau-Users", "Data-Team"],
        skills=["SQL", "Looker", "Python"],
        location="New York",
    )
    normalized = normalize_profile(profile)

    assert normalized.title_raw == "Sr BI Analyst"
    assert normalized.title_normalized == "senior business intelligence analyst"
    assert normalized.department_normalized == "data insights"
    assert normalized.manager_title_normalized == "director of analytics"
    assert normalized.groups_normalized == ["tableau-users", "data-team"]
    assert normalized.skills_normalized == ["sql", "looker", "python"]


def test_normalize_profile_handles_empty_profile():
    profile = SSOProfileIn(user_id="usr_008", groups=["contractors"])
    normalized = normalize_profile(profile)

    assert normalized.title_is_empty is True
    assert normalized.department_normalized is None
    assert normalized.skills_normalized == []
    assert normalized.groups_normalized == ["contractors"]
