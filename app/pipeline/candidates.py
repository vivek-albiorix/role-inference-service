"""Stage 3 -- Generate candidates.

Recall-oriented: for every role in the (small) catalog, compute a per-signal
sub-score against the profile's signal bundle. This never decides a winner
-- it produces evidence. Stage 4 (scoring.py) fuses that evidence into a
ranked list. Cheap enough to brute-force all roles at this catalog size;
at a larger catalog this is where an ANN/BM25 shortlist step would slot in
before scoring (see README "what changes at scale").
"""

from __future__ import annotations

from rapidfuzz import fuzz

from app.config import settings
from app.pipeline.normalize import contains_phrase
from app.pipeline.signals import best_function_hint
from app.pipeline.types import CatalogRole, SignalBundle, SignalContribution
from app.pipeline.vocabulary import ROLE_SENIORITY_TO_LEVELS


def _role_function(role: CatalogRole) -> str | None:
    text = f"{role.department} {role.job_family} {' '.join(role.keywords)}".lower()
    return best_function_hint(text)


def _title_contribution(signals: SignalBundle, title_normalized: str, is_generic: bool, has_vanity: bool, role: CatalogRole) -> SignalContribution:
    if has_vanity:
        return SignalContribution(
            signal="title",
            detail=f"Title contains a vanity/placeholder word -- ignored for matching",
            score=0.0,
            weight=settings.weight_title,
            supports=False,
        )
    ratio_name = fuzz.token_sort_ratio(title_normalized, role.role_name.lower()) / 100
    ratio_family = fuzz.partial_ratio(title_normalized, role.job_family.lower()) / 100
    score = max(ratio_name, 0.6 * ratio_family)
    if is_generic:
        score *= 0.5
    score = min(max(score, 0.0), 1.0)
    detail = f"Title '{title_normalized}' vs role name '{role.role_name}' (similarity {ratio_name:.2f})"
    return SignalContribution(
        signal="title", detail=detail, score=score, weight=settings.weight_title, supports=score >= 0.5
    )


def _department_contribution(department_normalized: str, role: CatalogRole) -> SignalContribution:
    role_dept = role.department.lower()
    score = max(
        fuzz.partial_ratio(department_normalized, role_dept) / 100,
        fuzz.token_sort_ratio(department_normalized, role_dept) / 100,
    )
    detail = f"Department '{department_normalized}' vs role department '{role.department}' (similarity {score:.2f})"
    return SignalContribution(
        signal="department", detail=detail, score=score, weight=settings.weight_department, supports=score >= 0.6
    )


def _skills_contribution(skills: set[str], role: CatalogRole) -> SignalContribution | None:
    role_skills = {s.lower() for s in role.skills}
    if not role_skills:
        return None
    matched = {
        rs for rs in role_skills if rs in skills or any(fuzz.ratio(rs, us) > 90 for us in skills)
    }
    score = len(matched) / len(role_skills)
    detail = (
        f"Skills overlap: {', '.join(sorted(matched)) or 'none'} ({len(matched)}/{len(role_skills)} of role's skills)"
    )
    return SignalContribution(
        signal="skills", detail=detail, score=score, weight=settings.weight_skills, supports=score >= 0.3
    )


def _groups_contribution(signals: SignalBundle, role: CatalogRole) -> SignalContribution:
    role_function = _role_function(role)
    matched = bool(role_function and role_function in signals.group_function_hints)
    if matched:
        score = 1.0
    elif signals.group_function_hints:
        score = 0.15  # groups present but none point at this role's function
    else:
        score = 0.0
    detail = f"Group hints {sorted(signals.group_function_hints) or 'none'} vs role function '{role_function}'"
    return SignalContribution(
        signal="groups", detail=detail, score=score, weight=settings.weight_groups, supports=matched
    )


def _manager_contribution(signals: SignalBundle, role: CatalogRole) -> SignalContribution:
    role_function = _role_function(role)
    matched = bool(signals.manager_function_hint and signals.manager_function_hint == role_function)
    if matched:
        score = 1.0
    elif signals.manager_function_hint:
        score = 0.2
    else:
        score = 0.0
    detail = f"Manager function hint '{signals.manager_function_hint}' vs role function '{role_function}'"
    return SignalContribution(
        signal="manager", detail=detail, score=score, weight=settings.weight_manager, supports=matched
    )


def _keywords_contribution(keyword_bag: set[str], role: CatalogRole) -> SignalContribution | None:
    role_keywords = [k.lower() for k in role.keywords]
    if not role_keywords:
        return None
    bag_text = " ".join(sorted(keyword_bag))
    matched = [k for k in role_keywords if contains_phrase(bag_text, k)]
    score = len(matched) / len(role_keywords)
    detail = f"Keyword overlap: {', '.join(matched) or 'none'} ({len(matched)}/{len(role_keywords)} of role's keywords)"
    return SignalContribution(
        signal="keywords", detail=detail, score=score, weight=settings.weight_keywords, supports=score >= 0.25
    )


def _seniority_contribution(signals: SignalBundle, role: CatalogRole) -> SignalContribution:
    allowed_levels = ROLE_SENIORITY_TO_LEVELS.get(role.seniority, [])
    matched = signals.seniority_level in allowed_levels
    score = 1.0 if matched else 0.2
    detail = f"Seniority '{signals.seniority_level}' vs role seniority '{role.seniority}'"
    return SignalContribution(
        signal="seniority", detail=detail, score=score, weight=settings.weight_seniority, supports=matched
    )


def score_role(
    signals: SignalBundle, title_normalized: str | None, title_is_generic: bool, title_has_vanity: bool, role: CatalogRole
) -> list[SignalContribution]:
    """All per-signal contributions for one role, limited to signal
    categories actually present & trusted on this profile."""
    contributions: list[SignalContribution] = []

    if "title" in signals.present_signals and title_normalized:
        contributions.append(
            _title_contribution(signals, title_normalized, title_is_generic, title_has_vanity, role)
        )
    if "department" in signals.present_signals and signals.department_normalized:
        contributions.append(_department_contribution(signals.department_normalized, role))
    if "skills" in signals.present_signals:
        contribution = _skills_contribution(signals.skills, role)
        if contribution:
            contributions.append(contribution)
    if "groups" in signals.present_signals:
        contributions.append(_groups_contribution(signals, role))
    if "manager" in signals.present_signals:
        contributions.append(_manager_contribution(signals, role))
    if "keywords" in signals.present_signals:
        contribution = _keywords_contribution(signals.keyword_bag, role)
        if contribution:
            contributions.append(contribution)
    if "seniority" in signals.present_signals:
        contributions.append(_seniority_contribution(signals, role))

    return contributions


def generate_candidates(
    signals: SignalBundle,
    title_normalized: str | None,
    title_is_generic: bool,
    title_has_vanity: bool,
    roles: list[CatalogRole],
) -> dict[str, list[SignalContribution]]:
    """Returns {role_id: contributions} for every catalog role -- the raw
    evidence Stage 4 will fuse into ranked, weighted scores."""
    return {
        role.role_id: score_role(signals, title_normalized, title_is_generic, title_has_vanity, role)
        for role in roles
    }
