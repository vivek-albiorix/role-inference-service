"""Lightweight evaluation harness: scores inference quality against a small,
hand-labeled test set (eval/labels.json).

This is deliberately not a substitute for real calibration against
production override data (see README "What I'd build next") -- it's a
sanity-check regression harness, small enough to hand-label and reason
about directly. Two metrics, because this system is explicitly allowed (and
expected) to abstain:

- Resolved-case accuracy: for profiles with a clear expected role, did the
  pipeline pick it?
- Correct-abstention rate: for profiles labeled genuinely ambiguous/empty,
  did the pipeline correctly refuse to guess (band == very_low) rather than
  produce a confident-sounding wrong answer?

Usage: python eval/eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import SSOProfileIn  # noqa: E402
from app.pipeline.catalog import load_catalog_roles, load_sample_sso_profiles  # noqa: E402
from app.pipeline.orchestrator import run_inference  # noqa: E402

LABELS_PATH = Path(__file__).resolve().parent / "labels.json"


def main() -> None:
    roles = load_catalog_roles()
    profiles_by_id = {p["user_id"]: p for p in load_sample_sso_profiles()}
    labels = json.loads(LABELS_PATH.read_text())

    resolved_total = resolved_correct = 0
    abstain_total = abstain_correct = 0
    rows: list[tuple[str, str | None, str | None, str, str]] = []

    for label in labels:
        user_id = label["user_id"]
        profile = SSOProfileIn(**profiles_by_id[user_id])
        result = run_inference(profile, roles)
        expected = label["expected_role_id"]

        if expected is None:
            abstain_total += 1
            correct = result.inferred_role_id is None
            abstain_correct += int(correct)
            outcome = "abstained (correct)" if correct else f"guessed {result.inferred_role_id} (should have abstained)"
        else:
            resolved_total += 1
            correct = result.inferred_role_id == expected
            resolved_correct += int(correct)
            outcome = "match" if correct else f"got {result.inferred_role_id}, expected {expected}"

        rows.append((user_id, expected, result.inferred_role_id, result.band, outcome))

    print(f"{'user_id':<10} {'expected':<12} {'inferred':<12} {'band':<10} outcome")
    for user_id, expected, inferred, band, outcome in rows:
        print(f"{user_id:<10} {str(expected):<12} {str(inferred):<12} {band:<10} {outcome}")

    print()
    if resolved_total:
        print(f"Resolved-case accuracy:   {resolved_correct}/{resolved_total} ({resolved_correct / resolved_total:.0%})")
    if abstain_total:
        print(f"Correct-abstention rate:  {abstain_correct}/{abstain_total} ({abstain_correct / abstain_total:.0%})")


if __name__ == "__main__":
    main()
