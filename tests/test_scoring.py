from app.models.schemas import SSOProfileIn
from app.pipeline.candidates import generate_candidates
from app.pipeline.catalog import load_catalog_roles
from app.pipeline.normalize import normalize_profile
from app.pipeline.scoring import combine_score, compute_margin, rank_candidates
from app.pipeline.signals import extract_signals
from app.pipeline.types import CatalogRole, SignalContribution


def test_combine_score_renormalizes_over_present_weights():
    contributions = [
        SignalContribution(signal="title", detail="", score=1.0, weight=0.3, supports=True),
        SignalContribution(signal="department", detail="", score=0.0, weight=0.2, supports=False),
    ]
    # weighted = 1.0*0.3 + 0.0*0.2 = 0.3, total_weight = 0.5 -> 0.6
    assert combine_score(contributions) == 0.6


def test_combine_score_empty_contributions_is_zero():
    assert combine_score([]) == 0.0


def test_rank_candidates_sorts_descending():
    roles_by_id = {
        "a": CatalogRole(
            role_id="a", role_name="A", department="D", job_family="F", seniority="Mid", skills=[], keywords=[]
        ),
        "b": CatalogRole(
            role_id="b", role_name="B", department="D", job_family="F", seniority="Mid", skills=[], keywords=[]
        ),
    }
    contributions_by_role = {
        "a": [SignalContribution(signal="title", detail="", score=0.4, weight=1.0, supports=False)],
        "b": [SignalContribution(signal="title", detail="", score=0.9, weight=1.0, supports=True)],
    }
    ranked = rank_candidates(contributions_by_role, roles_by_id)
    assert [c.role_id for c in ranked] == ["b", "a"]


def test_compute_margin_between_top_two():
    class Dummy:
        def __init__(self, score):
            self.score = score

    assert abs(compute_margin([Dummy(0.9), Dummy(0.6)]) - 0.3) < 1e-9


def test_compute_margin_single_candidate_is_unambiguous():
    class Dummy:
        def __init__(self, score):
            self.score = score

    assert compute_margin([Dummy(0.5)]) == 1.0


def test_full_deterministic_pipeline_ranks_senior_over_mid_for_usr_001():
    """Integration sanity check across normalize -> signals -> candidates ->
    scoring using the real catalog: 'Sr BI Analyst' in the Data org with
    SQL/Looker/Python should rank Senior Data Analyst above the (otherwise
    lexically similar) Data Analyst, because seniority and richer skills
    corroborate the 'senior' qualifier."""
    profile = SSOProfileIn(
        user_id="usr_001",
        title="Sr BI Analyst",
        department="Data & Insights",
        manager_title="Director of Analytics",
        groups=["tableau-users", "data-team", "all-staff"],
        skills=["SQL", "Looker", "Python"],
        location="New York",
    )
    normalized = normalize_profile(profile)
    signals = extract_signals(normalized)
    roles = load_catalog_roles()
    contributions_by_role = generate_candidates(
        signals, normalized.title_normalized, normalized.title_is_generic, normalized.title_has_vanity, roles
    )
    roles_by_id = {r.role_id: r for r in roles}
    ranked = rank_candidates(contributions_by_role, roles_by_id)

    assert ranked[0].role_id == "role_001"  # Senior Data Analyst
    senior_rank = next(i for i, c in enumerate(ranked) if c.role_id == "role_001")
    mid_rank = next(i for i, c in enumerate(ranked) if c.role_id == "role_002")
    assert senior_rank < mid_rank


def test_full_deterministic_pipeline_handles_empty_profile_gracefully():
    """usr_008: nearly empty profile. Should not error, and should produce
    a very low top score since almost no signals are present."""
    profile = SSOProfileIn(user_id="usr_008", groups=["contractors"])
    normalized = normalize_profile(profile)
    signals = extract_signals(normalized)
    roles = load_catalog_roles()
    contributions_by_role = generate_candidates(
        signals, normalized.title_normalized, normalized.title_is_generic, normalized.title_has_vanity, roles
    )
    roles_by_id = {r.role_id: r for r in roles}
    ranked = rank_candidates(contributions_by_role, roles_by_id)

    assert all(c.score == 0.0 for c in ranked)  # no present signals at all
