"""Stage 5 -- LLM disambiguation.

Only invoked by the orchestrator when the deterministic layers haven't
produced a clear winner (top1/top2 margin below threshold). The model
chooses among a shortlist the matching engine already produced -- it can
never invent a role, which is the anti-hallucination guardrail: the
`chosen_id` field is enum-constrained to the shortlist's role_ids plus
"none". If no API key is configured, or the call fails validation after
retries, a deterministic stub takes over so the pipeline always completes.
"""

from __future__ import annotations

import json
import logging

from app.config import settings
from app.pipeline.types import LLMDisambiguationResult, NormalizedProfile, ScoredCandidate, SignalBundle

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a role classifier for an enterprise employee directory. Choose EXACTLY ONE "
    "role id from the provided candidate list that best matches the evidence. You may NOT "
    "invent a role id that is not listed. If none of the candidates genuinely fit the "
    'evidence, return "none". Base your rationale only on the evidence given.'
)


def _stub_result(shortlist: list[ScoredCandidate], reason: str) -> LLMDisambiguationResult:
    if not shortlist:
        return LLMDisambiguationResult(
            chosen_role_id="none",
            rationale=f"LLM disambiguation unavailable ({reason}); no candidates to fall back to.",
            used=False,
            degraded=True,
        )
    return LLMDisambiguationResult(
        chosen_role_id=shortlist[0].role_id,
        rationale=f"LLM disambiguation unavailable ({reason}); used the top deterministic candidate instead.",
        used=False,
        degraded=True,
    )


def _evidence_block(normalized: NormalizedProfile, signals: SignalBundle) -> str:
    lines: list[str] = []
    if normalized.title_raw:
        lines.append(f'- title: "{normalized.title_raw}"')
    if normalized.department_raw:
        lines.append(f'- department: "{normalized.department_raw}"')
    if normalized.manager_title_raw:
        lines.append(f'- manager title: "{normalized.manager_title_raw}"')
    if normalized.skills_normalized:
        lines.append(f"- skills: {', '.join(normalized.skills_normalized)}")
    if normalized.groups_normalized:
        lines.append(f"- groups: {', '.join(normalized.groups_normalized)}")
    if normalized.notes_raw:
        lines.append(f'- notes: "{normalized.notes_raw}"')
    return "\n".join(lines) if lines else "(no structured evidence available)"


def _response_schema(shortlist: list[ScoredCandidate]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["chosen_id", "rationale"],
        "properties": {
            "chosen_id": {"type": "string", "enum": [c.role_id for c in shortlist] + ["none"]},
            "rationale": {"type": "string", "maxLength": 400},
        },
    }


def disambiguate(
    shortlist: list[ScoredCandidate],
    normalized: NormalizedProfile,
    signals: SignalBundle,
) -> LLMDisambiguationResult:
    if not shortlist:
        return _stub_result([], reason="empty shortlist")

    if not settings.openai_api_key:
        return _stub_result(shortlist, reason="no OPENAI_API_KEY configured")

    try:
        from openai import OpenAI  # imported lazily so the package is optional at runtime

        client = OpenAI(api_key=settings.openai_api_key)
    except Exception as exc:  # noqa: BLE001 -- any client construction failure falls back to the stub
        return _stub_result(shortlist, reason=f"could not initialize OpenAI client ({exc})")

    candidates_desc = "\n".join(f"  {c.role_id} -> {c.role_name}" for c in shortlist)
    user_prompt = (
        f"Candidates:\n{candidates_desc}\n\nEvidence:\n{_evidence_block(normalized, signals)}\n\n"
        "Return JSON only, matching the schema."
    )
    valid_ids = {c.role_id for c in shortlist} | {"none"}

    last_error: Exception | None = None
    for _attempt in range(settings.llm_max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                temperature=0,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "role_choice",
                        "schema": _response_schema(shortlist),
                        "strict": True,
                    },
                },
            )
            parsed = json.loads(response.choices[0].message.content)
            chosen_id = parsed["chosen_id"]
            rationale = parsed["rationale"]
            if chosen_id not in valid_ids:
                raise ValueError(f"LLM returned an id outside the shortlist: {chosen_id!r}")
            return LLMDisambiguationResult(chosen_role_id=chosen_id, rationale=rationale, used=True, degraded=False)
        except Exception as exc:  # noqa: BLE001 -- broad on purpose, we always have a fallback
            last_error = exc
            logger.warning("LLM disambiguation attempt failed: %s", exc)

    return _stub_result(shortlist, reason=f"LLM call failed after retries ({last_error})")
