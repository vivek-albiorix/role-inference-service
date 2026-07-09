from app.pipeline.confidence import band_for, compute_confidence
from app.pipeline.types import SignalContribution


def _contribution(signal, score, weight, supports):
    return SignalContribution(signal=signal, detail=signal, score=score, weight=weight, supports=supports)


def test_band_thresholds():
    assert band_for(0.9) == "high"
    assert band_for(0.85) == "high"
    assert band_for(0.7) == "medium"
    assert band_for(0.5) == "low"
    assert band_for(0.1) == "very_low"


def test_high_coverage_full_agreement_yields_high_confidence():
    contributions = [
        _contribution("title", 0.95, 0.32, True),
        _contribution("department", 1.0, 0.20, True),
        _contribution("skills", 0.8, 0.16, True),
        _contribution("manager", 1.0, 0.10, True),
    ]
    present = {"title", "department", "skills", "manager", "groups", "keywords", "seniority"}
    result = compute_confidence(present, top_score=0.9, margin=0.4, winner_contributions=contributions)
    assert result.confidence > 0.7
    assert result.band in {"high", "medium"}


def test_empty_profile_yields_zero_confidence_and_very_low_band():
    result = compute_confidence(set(), top_score=0.0, margin=0.0, winner_contributions=[])
    assert result.confidence == 0.0
    assert result.band == "very_low"


def test_missing_title_applies_penalty():
    contributions = [_contribution("department", 1.0, 0.20, True)]
    with_title = compute_confidence({"title", "department"}, 0.8, 0.3, contributions)
    without_title = compute_confidence({"department"}, 0.8, 0.3, contributions)
    assert without_title.confidence < with_title.confidence
    assert without_title.p_missing > 0
    assert with_title.p_missing == 0


def test_conflicting_signals_reduce_confidence():
    supporting = [
        _contribution("title", 0.9, 0.32, True),
        _contribution("department", 0.9, 0.20, True),
    ]
    conflicting = [
        _contribution("title", 0.9, 0.32, True),
        _contribution("department", 0.1, 0.20, False),  # department contradicts the winner
    ]
    good = compute_confidence({"title", "department"}, 0.9, 0.3, supporting)
    bad = compute_confidence({"title", "department"}, 0.9, 0.3, conflicting)
    assert bad.confidence < good.confidence
    assert bad.p_conflict > 0


def test_manager_derived_only_decision_is_penalized_as_stale():
    contributions = [
        _contribution("manager", 1.0, 0.10, True),
        _contribution("groups", 1.0, 0.13, True),
    ]
    result = compute_confidence({"manager", "groups"}, 0.6, 0.3, contributions)
    assert result.p_stale > 0
