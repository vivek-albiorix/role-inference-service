from app.pipeline.candidates import score_role
from app.pipeline.types import CatalogRole, SignalBundle


def _role(**overrides) -> CatalogRole:
    defaults = dict(
        role_id="role_001",
        role_name="Senior Data Analyst",
        department="Data",
        job_family="Analytics",
        seniority="Senior",
        skills=["SQL", "Python", "Dashboarding"],
        keywords=["analytics", "bi", "reporting", "insights"],
    )
    defaults.update(overrides)
    return CatalogRole(**defaults)


def test_title_contribution_scores_exact_match_highly():
    role = _role()
    signals = SignalBundle(present_signals={"title"})
    contributions = score_role(signals, "senior data analyst", False, False, role)
    title_contrib = next(c for c in contributions if c.signal == "title")
    assert title_contrib.score > 0.9
    assert title_contrib.supports is True


def test_title_contribution_dropped_when_not_present():
    role = _role()
    signals = SignalBundle(present_signals=set())
    contributions = score_role(signals, None, False, False, role)
    assert contributions == []


def test_vanity_title_scores_zero():
    role = _role()
    signals = SignalBundle(present_signals={"title"})
    contributions = score_role(signals, "growth ninja", False, True, role)
    title_contrib = next(c for c in contributions if c.signal == "title")
    assert title_contrib.score == 0.0


def test_skills_overlap_fraction():
    role = _role(skills=["SQL", "Python", "Dashboarding", "Stakeholder Communication"])
    signals = SignalBundle(present_signals={"skills"}, skills={"sql", "python"})
    contributions = score_role(signals, None, False, False, role)
    skills_contrib = next(c for c in contributions if c.signal == "skills")
    assert skills_contrib.score == 0.5  # 2 of 4 role skills matched


def test_seniority_mismatch_scores_low_but_present():
    role = _role(seniority="Mid")
    signals = SignalBundle(present_signals={"seniority"}, seniority_level="senior")
    contributions = score_role(signals, None, False, False, role)
    seniority_contrib = next(c for c in contributions if c.signal == "seniority")
    assert seniority_contrib.score < 0.5
    assert seniority_contrib.supports is False


def test_department_fuzzy_match():
    role = _role(department="Data")
    signals = SignalBundle(present_signals={"department"}, department_normalized="data insights")
    contributions = score_role(signals, None, False, False, role)
    dept_contrib = next(c for c in contributions if c.signal == "department")
    assert dept_contrib.score >= 0.6


def test_keywords_overlap_catches_abbreviation_style_catalog_keywords():
    role = _role(keywords=["analytics", "bi", "reporting"])
    signals = SignalBundle(present_signals={"keywords"}, keyword_bag={"senior", "bi", "analyst"})
    contributions = score_role(signals, None, False, False, role)
    kw_contrib = next(c for c in contributions if c.signal == "keywords")
    assert "bi" in kw_contrib.detail
    assert kw_contrib.score > 0
