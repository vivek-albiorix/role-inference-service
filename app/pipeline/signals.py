"""Stage 2 -- Extract signals.

Turns the normalized profile into structured features that can be weighed
against the role catalog. This decouples "what we know about the person"
from "how we match it to a role" (candidates.py / scoring.py) -- signals
here have no notion of the catalog at all.
"""

from __future__ import annotations

from app.pipeline.normalize import clean_text, contains_phrase
from app.pipeline.types import NormalizedProfile, SignalBundle
from app.pipeline.vocabulary import (
    EMPLOYMENT_TYPE_GROUPS,
    FUNCTION_KEYWORDS,
    GROUP_FUNCTION_HINTS,
    SENIORITY_LADDER,
    STOPWORDS,
)

# Groups that describe an org-wide catch-all rather than any function --
# present on almost everyone, so they carry no discriminating signal.
_NON_FUNCTIONAL_GROUPS = {"all-staff", "contractors", "contractor"}


def _seniority_from_title(title_normalized: str | None) -> tuple[str | None, str | None]:
    if title_normalized is None:
        return None, None
    # Highest level first, so "senior staff engineer" resolves to "staff".
    for level_name, _rank, trigger_words in reversed(SENIORITY_LADDER):
        if any(contains_phrase(title_normalized, w) for w in trigger_words):
            return level_name, "title"
    # Title exists but names no explicit level -- assume the catalog default.
    return "mid", "title"


def best_function_hint(text: str | None) -> str | None:
    """Picks the function whose matched keyword phrase is longest (most
    specific), so "sales operations" beats a bare "operations" match.
    Public: also used by candidates.py to classify a *role's* function."""
    if not text:
        return None
    best_function, best_phrase_len = None, 0
    for function, keywords in FUNCTION_KEYWORDS.items():
        for keyword in keywords:
            if contains_phrase(text, keyword) and len(keyword.split()) > best_phrase_len:
                best_function, best_phrase_len = function, len(keyword.split())
    return best_function


def _group_function_hints(groups_normalized: list[str]) -> set[str]:
    hints: set[str] = set()
    for group in groups_normalized:
        for marker, hint in GROUP_FUNCTION_HINTS.items():
            if marker in group:
                hints.add(hint)
    return hints


def _employment_type_hint(groups_normalized: list[str]) -> str | None:
    for group in groups_normalized:
        for marker, hint in EMPLOYMENT_TYPE_GROUPS.items():
            if marker in group:
                return hint
    return None


def _keyword_bag(*texts: str | None) -> set[str]:
    bag: set[str] = set()
    for text in texts:
        if not text:
            continue
        bag.update(word for word in text.split() if word not in STOPWORDS)
    return bag


def extract_signals(profile: NormalizedProfile) -> SignalBundle:
    seniority_level, seniority_source = _seniority_from_title(profile.title_normalized)

    group_hints = _group_function_hints(profile.groups_normalized)
    meaningful_groups = [g for g in profile.groups_normalized if g not in _NON_FUNCTIONAL_GROUPS]

    # Include both the abbreviation-expanded and the raw-cleaned form of
    # text fields: the catalog's own `keywords` lists use abbreviations
    # (e.g. "bi"), which our expansion step (Sr -> Senior, BI -> Business
    # Intelligence) would otherwise erase from the bag entirely.
    keyword_bag = _keyword_bag(
        profile.title_normalized,
        clean_text(profile.title_raw),
        profile.department_normalized,
        clean_text(profile.department_raw),
        profile.notes_normalized,
        profile.manager_title_normalized,
    )

    present: set[str] = set()
    if not profile.title_is_empty:
        present.add("title")
    if profile.department_normalized:
        present.add("department")
    if profile.manager_title_normalized:
        present.add("manager")
    if profile.skills_normalized:
        present.add("skills")
    if meaningful_groups:
        present.add("groups")
    if keyword_bag:
        present.add("keywords")
    if seniority_level:
        present.add("seniority")

    return SignalBundle(
        seniority_level=seniority_level,
        seniority_source=seniority_source,
        department_normalized=profile.department_normalized,
        manager_function_hint=best_function_hint(profile.manager_title_normalized),
        skills=set(profile.skills_normalized),
        groups=set(profile.groups_normalized),
        group_function_hints=group_hints,
        employment_type_hint=_employment_type_hint(profile.groups_normalized),
        keyword_bag=keyword_bag,
        notes_function_hint=best_function_hint(profile.notes_normalized),
        location_normalized=profile.location_normalized,
        present_signals=present,
    )
