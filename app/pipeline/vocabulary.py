"""Curated lookup tables shared by the normalize/signals/candidates stages.

These are intentionally small and hand-curated rather than learned. Per the
architecture notes this is the deterministic "floor" of the matching
strategy -- cheap, explainable, and correct when it hits. Growing this table
from real override data (an admin correcting "Sr BI Analyst" repeatedly)
is exactly the kind of active-learning loop called out as future work in the
README; it is a business decision, not a code problem, so it isn't
implemented here.
"""

from __future__ import annotations

# Token -> expansion, applied on whole, whitespace-delimited tokens after
# punctuation stripping. Keep keys lowercase; values may be multi-word.
ABBREVIATIONS: dict[str, str] = {
    "sr": "senior",
    "jr": "junior",
    "mgr": "manager",
    "vp": "vice president",
    "svp": "senior vice president",
    "cto": "chief technology officer",
    "cpo": "chief product officer",
    "ceo": "chief executive officer",
    "swe": "software engineer",
    "sde": "software engineer",
    "bi": "business intelligence",
    "cs": "customer success",
    "csm": "customer success manager",
    "eng": "engineering",
    "ops": "operations",
    "hr": "human resources",
    "qa": "quality assurance",
    "pm": "product manager",
    "revops": "revenue operations",
    "devops": "developer operations",
    "admin": "administrator",
}

# Trailing/leading level suffixes that are noise for text matching but a weak
# seniority signal (handled separately in signals.py).
LEVEL_SUFFIXES = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}

# A title consisting of exactly one of these words (after normalization, with
# seniority words like "senior"/"lead" stripped) is too generic to trust
# alone -- e.g. "Analyst", "Manager". Not the same as a vanity title; a
# generic title is plausible for many roles, just underspecified.
GENERIC_TITLE_WORDS = {
    "analyst",
    "manager",
    "specialist",
    "coordinator",
    "associate",
    "lead",
    "director",
    "consultant",
    "engineer",
}

# Titles that carry no functional information at all and should be treated
# like an empty title for matching purposes, while being called out
# explicitly in the explanation.
VANITY_TITLE_WORDS = {"ninja", "rockstar", "guru", "wizard", "hero", "evangelist"}

# Ordered seniority ladder (low -> high). Each level lists trigger words
# looked for as whole tokens in a normalized title/manager-title string.
SENIORITY_LADDER: list[tuple[str, int, list[str]]] = [
    ("intern", 0, ["intern", "internship"]),
    ("junior", 1, ["junior", "associate"]),
    ("mid", 2, []),  # default when no other level word is found
    ("senior", 3, ["senior", "sr"]),
    ("staff", 4, ["staff", "principal", "lead"]),
    ("manager", 5, ["manager", "mgr", "head"]),
    ("director", 6, ["director"]),
    ("vp", 7, ["vice president", "vp", "svp"]),
    ("executive", 8, ["chief", "ceo", "cto", "cpo", "president"]),
]

# Maps a catalog `seniority` value to the ladder levels considered a match.
ROLE_SENIORITY_TO_LEVELS: dict[str, list[str]] = {
    "Mid": ["junior", "mid"],
    "Senior": ["senior", "staff"],
    "Manager": ["manager", "director"],
}

# Group-name substring -> function hint. Matched with `in`, so keep specific.
GROUP_FUNCTION_HINTS: dict[str, str] = {
    "tableau": "analytics",
    "looker": "analytics",
    "data-team": "analytics",
    "aws-admin": "infra",
    "oncall": "infra",
    "engineering": "engineering",
    "gainsight": "customer_success",
    "cs-team": "customer_success",
    "jira-admin": "product",
    "product-team": "product",
    "salesforce-admin": "revops_sales",
}

# Groups that describe employment type rather than function.
EMPLOYMENT_TYPE_GROUPS: dict[str, str] = {
    "contractors": "contractor",
    "contractor": "contractor",
}

# Function hint -> free-text keywords used to match that hint against a
# role's department/job_family/keywords. Also used to scan free text
# (manager title, notes) for a function hint directly.
FUNCTION_KEYWORDS: dict[str, list[str]] = {
    "analytics": ["data", "analytics", "bi", "insights", "reporting"],
    "infra": ["infrastructure", "platform", "devops", "cloud", "kubernetes"],
    "engineering": ["engineering", "software", "platform", "backend", "frontend", "technology"],
    "product": ["product", "roadmap", "strategy"],
    "customer_success": ["customer success", "customer experience", "renewal", "adoption"],
    "revops_sales": ["revenue operations", "revops", "sales operations", "sales", "pipeline", "forecast", "crm"],
    "operations": ["operations"],
}

# Ignored when building the free-text keyword bag (stage 2) -- too common to
# carry any functional signal on their own.
STOPWORDS = {"of", "the", "and", "for", "team", "staff", "all", "a", "an"}
