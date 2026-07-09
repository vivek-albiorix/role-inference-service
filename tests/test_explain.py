from app.pipeline.confidence import compute_confidence
from app.pipeline.explain import build_explanation
from app.pipeline.types import CatalogRole, NormalizedProfile, ScoredCandidate, SignalBundle, SignalContribution


def _role(role_id, name, department="Data", job_family="Analytics", keywords=None) -> CatalogRole:
    return CatalogRole(
        role_id=role_id,
        role_name=name,
        department=department,
        job_family=job_family,
        seniority="Senior",
        skills=[],
        keywords=keywords or ["analytics"],
    )


def _profile(**overrides) -> NormalizedProfile:
    defaults = dict(
        external_id="usr_test",
        source="unknown",
        display_name="Test User",
        title_raw="Sr BI Analyst",
        title_normalized="senior business intelligence analyst",
        title_is_empty=False,
        title_is_generic=False,
        title_has_vanity=False,
        department_raw="Data & Insights",
        department_normalized="data insights",
        manager_title_raw="Director of Analytics",
        manager_title_normalized="director of analytics",
        skills_raw=["SQL"],
        skills_normalized=["sql"],
        groups_raw=[],
        groups_normalized=[],
        location_raw=None,
        location_normalized=None,
        notes_raw=None,
        notes_normalized=None,
    )
    defaults.update(overrides)
    return NormalizedProfile(**defaults)


def test_explanation_for_confident_winner_includes_positive_evidence_and_why_winner_won():
    winner = ScoredCandidate(
        role_id="role_001",
        role_name="Senior Data Analyst",
        score=0.9,
        contributions=[
            SignalContribution(signal="title", detail="Title matches well", score=0.9, weight=0.32, supports=True),
            SignalContribution(signal="department", detail="Department matches", score=0.9, weight=0.20, supports=True),
        ],
    )
    runner_up = ScoredCandidate(
        role_id="role_002",
        role_name="Data Analyst",
        score=0.5,
        contributions=[
            SignalContribution(signal="title", detail="Weaker title match", score=0.5, weight=0.32, supports=False),
            SignalContribution(signal="department", detail="Department matches", score=0.9, weight=0.20, supports=True),
        ],
    )
    ranked = [winner, runner_up]
    roles_by_id = {"role_001": _role("role_001", "Senior Data Analyst"), "role_002": _role("role_002", "Data Analyst")}
    signals = SignalBundle(present_signals={"title", "department"})
    confidence = compute_confidence(signals.present_signals, winner.score, 0.4, winner.contributions)

    explanation = build_explanation(_profile(), signals, ranked, roles_by_id, confidence, assigned=True)

    assert "Senior Data Analyst" in explanation.human_readable
    assert len(explanation.positive_evidence) == 2
    assert explanation.why_winner_won is not None
    assert len(explanation.alternative_roles) == 1
    assert explanation.alternative_roles[0].role_id == "role_002"
    assert explanation.alternative_roles[0].why_lost is not None


def test_explanation_when_not_assigned_says_needs_review():
    signals = SignalBundle(present_signals=set())
    confidence = compute_confidence(set(), 0.0, 0.0, [])
    explanation = build_explanation(_profile(title_is_empty=True, title_normalized=None), signals, [], {}, confidence, assigned=False)

    assert "review" in explanation.human_readable.lower()
    assert explanation.alternative_roles == []


def test_explanation_flags_notes_conflict_as_negative_evidence():
    winner = ScoredCandidate(
        role_id="role_009",
        role_name="Revenue Operations Manager",
        score=0.6,
        contributions=[
            SignalContribution(signal="department", detail="Department matches", score=0.6, weight=0.20, supports=True),
        ],
    )
    roles_by_id = {"role_009": _role("role_009", "Revenue Operations Manager", department="Revenue Operations", job_family="Operations", keywords=["revops", "revenue"])}
    signals = SignalBundle(present_signals={"department"}, notes_function_hint="engineering")
    confidence = compute_confidence(signals.present_signals, winner.score, 0.4, winner.contributions)

    explanation = build_explanation(_profile(), signals, [winner], roles_by_id, confidence, assigned=True)

    assert any("notes" in item.lower() for item in explanation.negative_evidence)


def test_missing_information_lists_absent_signal_categories():
    signals = SignalBundle(present_signals={"title"})
    confidence = compute_confidence(signals.present_signals, 0.5, 0.3, [])
    explanation = build_explanation(_profile(), signals, [], {}, confidence, assigned=False)

    assert any("department" in msg.lower() for msg in explanation.missing_information)
    assert any("manager" in msg.lower() for msg in explanation.missing_information)
