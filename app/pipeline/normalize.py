"""Stage 1 -- Normalize.

Pure, deterministic, side-effect free: turns messy provider strings into a
clean feature set while keeping the raw values alongside (never overwrite,
since audit/display need the original). Every later stage assumes clean
input, so this is the stage every other stage's correctness depends on.
"""

from __future__ import annotations

import re
import unicodedata

from app.models.schemas import SSOProfileIn
from app.pipeline.types import NormalizedProfile
from app.pipeline.vocabulary import (
    ABBREVIATIONS,
    GENERIC_TITLE_WORDS,
    LEVEL_SUFFIXES,
    SENIORITY_LADDER,
    VANITY_TITLE_WORDS,
)

_SENIORITY_TRIGGER_WORDS = {word for _, _, words in SENIORITY_LADDER for word in words}


def contains_phrase(text: str, phrase: str) -> bool:
    """Whole-word/phrase substring check (avoids matching "senior" inside
    some longer unrelated word)."""
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def clean_text(raw: str | None) -> str | None:
    """Lowercase, unicode-fold, strip punctuation, collapse whitespace."""
    if raw is None or not raw.strip():
        return None
    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    folded = folded.lower()
    folded = re.sub(r"[^a-z0-9\s]", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded or None


def _expand_tokens(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(ABBREVIATIONS.get(token, token).split())
    return expanded


def normalize_and_expand(raw: str | None) -> str | None:
    """Clean + abbreviation-expand a generic free-text field (department,
    manager title, notes)."""
    cleaned = clean_text(raw)
    if cleaned is None:
        return None
    expanded = _expand_tokens(cleaned.split())
    return " ".join(expanded) if expanded else None


def _is_title_generic(tokens: list[str]) -> bool:
    remaining = [t for t in tokens if t not in _SENIORITY_TRIGGER_WORDS]
    if not remaining:
        # Title was *only* a seniority/level word (e.g. "Lead", "Manager")
        # -- no functional information at all.
        return True
    if len(remaining) == 1 and remaining[0] in GENERIC_TITLE_WORDS:
        return True
    return False


def normalize_title(raw: str | None) -> tuple[str | None, bool, bool, bool]:
    """Returns (normalized_title, is_empty, is_generic, has_vanity_word)."""
    cleaned = clean_text(raw)
    if cleaned is None:
        return None, True, False, False

    tokens = cleaned.split()
    while tokens and tokens[-1] in LEVEL_SUFFIXES:
        tokens.pop()

    has_vanity = any(t in VANITY_TITLE_WORDS for t in tokens)
    expanded = _expand_tokens(tokens)
    is_generic = _is_title_generic(expanded)
    normalized = " ".join(expanded) if expanded else None
    return normalized, normalized is None, is_generic, has_vanity


def normalize_list(raw: list[str]) -> list[str]:
    return [item.strip().lower() for item in raw if item and item.strip()]


def normalize_profile(profile: SSOProfileIn) -> NormalizedProfile:
    title_normalized, title_is_empty, title_is_generic, title_has_vanity = normalize_title(
        profile.title
    )

    return NormalizedProfile(
        external_id=profile.user_id,
        source=profile.source,
        display_name=profile.display_name,
        title_raw=profile.title,
        title_normalized=title_normalized,
        title_is_empty=title_is_empty,
        title_is_generic=title_is_generic,
        title_has_vanity=title_has_vanity,
        department_raw=profile.department,
        department_normalized=normalize_and_expand(profile.department),
        manager_title_raw=profile.manager_title,
        manager_title_normalized=normalize_and_expand(profile.manager_title),
        skills_raw=list(profile.skills),
        skills_normalized=normalize_list(profile.skills),
        groups_raw=list(profile.groups),
        groups_normalized=normalize_list(profile.groups),
        location_raw=profile.location,
        location_normalized=clean_text(profile.location),
        notes_raw=profile.notes,
        notes_normalized=normalize_and_expand(profile.notes),
    )
