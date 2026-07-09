import json

import pytest

from app.config import settings
from app.pipeline.llm_disambiguate import disambiguate
from app.pipeline.types import NormalizedProfile, ScoredCandidate, SignalBundle


def _profile() -> NormalizedProfile:
    return NormalizedProfile(
        external_id="usr_007",
        source="unknown",
        display_name="Priya Nair",
        title_raw="Lead",
        title_normalized="lead",
        title_is_empty=False,
        title_is_generic=True,
        title_has_vanity=False,
        department_raw="Engineering",
        department_normalized="engineering",
        manager_title_raw="CTO",
        manager_title_normalized="chief technology officer",
        skills_raw=["Python", "SQL", "Machine Learning"],
        skills_normalized=["python", "sql", "machine learning"],
        groups_raw=["engineering", "all-staff"],
        groups_normalized=["engineering", "all-staff"],
        location_raw="Bangalore",
        location_normalized="bangalore",
        notes_raw=None,
        notes_normalized=None,
    )


def _shortlist() -> list[ScoredCandidate]:
    return [
        ScoredCandidate(role_id="role_005", role_name="Software Engineer", contributions=[], score=0.55),
        ScoredCandidate(role_id="role_010", role_name="Engineering Manager", contributions=[], score=0.52),
    ]


@pytest.fixture(autouse=True)
def _no_api_key_by_default(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)


def test_disambiguate_stub_when_no_api_key():
    result = disambiguate(_shortlist(), _profile(), SignalBundle())
    assert result.used is False
    assert result.degraded is True
    assert result.chosen_role_id == "role_005"  # top deterministic candidate
    assert "no OPENAI_API_KEY" in result.rationale


def test_disambiguate_stub_on_empty_shortlist():
    result = disambiguate([], _profile(), SignalBundle())
    assert result.degraded is True
    assert result.chosen_role_id == "none"


def test_disambiguate_uses_real_client_when_key_present(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    class _Message:
        content = json.dumps({"chosen_id": "role_010", "rationale": "Manager-level function keywords in the evidence."})

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            return _Response()

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        def __init__(self, api_key):
            self.chat = _Chat()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)

    result = disambiguate(_shortlist(), _profile(), SignalBundle())
    assert result.used is True
    assert result.degraded is False
    assert result.chosen_role_id == "role_010"


def test_disambiguate_falls_back_to_stub_when_llm_returns_invalid_id(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    class _Message:
        content = json.dumps({"chosen_id": "role_999_not_in_shortlist", "rationale": "oops"})

    class _Choice:
        message = _Message()

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            return _Response()

    class _Chat:
        completions = _Completions()

    class _FakeClient:
        def __init__(self, api_key):
            self.chat = _Chat()

    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)
    monkeypatch.setattr(settings, "llm_max_retries", 0)

    result = disambiguate(_shortlist(), _profile(), SignalBundle())
    assert result.used is False
    assert result.degraded is True
    assert result.chosen_role_id == "role_005"  # fell back to top deterministic candidate
