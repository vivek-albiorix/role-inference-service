"""Loads the Work Architecture catalog JSON into pipeline-local CatalogRole
objects. Used by the seed script (to populate the `roles` table) and
directly by tests that want to exercise the pipeline against the real
catalog without spinning up a database.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.pipeline.types import CatalogRole

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_WORK_ARCHITECTURE_PATH = _DATA_DIR / "work_architecture.json"
_SAMPLE_PROFILES_PATH = _DATA_DIR / "sample_sso_profiles.json"


def load_catalog_roles() -> list[CatalogRole]:
    raw = json.loads(_WORK_ARCHITECTURE_PATH.read_text())
    return [CatalogRole(**entry) for entry in raw]


def load_sample_sso_profiles() -> list[dict]:
    return json.loads(_SAMPLE_PROFILES_PATH.read_text())
