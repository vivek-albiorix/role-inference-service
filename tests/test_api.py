"""API-level lifecycle tests: ingest -> infer -> override -> reset ->
reprocess. Each test gets an isolated, file-backed SQLite database (not the
dev database) via a dependency override, seeded with the real catalog.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_session
from app.main import app
from app.models.tables import Role
from app.pipeline.catalog import load_catalog_roles

SARAH_PAYLOAD = {
    "user_id": "usr_001",
    "display_name": "Sarah Chen",
    "title": "Sr BI Analyst",
    "department": "Data & Insights",
    "manager_title": "Director of Analytics",
    "groups": ["tableau-users", "data-team", "all-staff"],
    "skills": ["SQL", "Looker", "Python"],
    "location": "New York",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_session():
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr("app.main.init_db", lambda: None)  # avoid touching the dev DB file

    session = testing_session_local()
    for r in load_catalog_roles():
        session.add(
            Role(
                role_id=r.role_id,
                role_name=r.role_name,
                department=r.department,
                job_family=r.job_family,
                seniority=r.seniority,
                skills=r.skills,
                keywords=r.keywords,
                catalog_version=1,
            )
        )
    session.commit()
    session.close()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_roles_endpoint_returns_seeded_catalog(client):
    response = client.get("/api/roles")
    assert response.status_code == 200
    assert len(response.json()) == 10


def test_ingest_profile_triggers_inference(client):
    response = client.post("/api/profiles", json=SARAH_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "usr_001"
    assert body["profile_version"] == 1

    inference = client.get("/api/users/usr_001/inference").json()
    assert inference["inferred_role"] == "Senior Data Analyst"
    assert inference["role_id"] == "role_001"


def test_reingesting_creates_a_new_profile_version(client):
    client.post("/api/profiles", json=SARAH_PAYLOAD)
    response = client.post("/api/profiles", json={**SARAH_PAYLOAD, "title": "Senior BI Analyst"})
    assert response.json()["profile_version"] == 2


def test_override_lifecycle_set_pin_reset(client):
    client.post("/api/profiles", json=SARAH_PAYLOAD)

    override_response = client.patch(
        "/api/users/usr_001/override",
        json={"role_id": "role_002", "pinned": True, "reason": "Acting generalist", "created_by": "admin"},
    )
    assert override_response.status_code == 200
    assert override_response.json()["role_id"] == "role_002"
    assert override_response.json()["pinned"] is True

    detail = client.get("/api/users/usr_001").json()
    assert detail["effective_role"]["role_id"] == "role_002"
    assert detail["effective_role"]["source"] == "overridden"
    assert detail["override_active"] is True
    assert detail["override_pinned"] is True

    reset_response = client.delete("/api/users/usr_001/override")
    assert reset_response.status_code == 204

    detail_after_reset = client.get("/api/users/usr_001").json()
    assert detail_after_reset["effective_role"]["role_id"] == "role_001"
    assert detail_after_reset["effective_role"]["source"] == "inferred"
    assert detail_after_reset["override_active"] is False


def test_reprocess_skips_users_with_active_pinned_override(client):
    client.post("/api/profiles", json=SARAH_PAYLOAD)
    client.patch(
        "/api/users/usr_001/override",
        json={"role_id": "role_002", "pinned": True, "created_by": "admin"},
    )

    result = client.post("/api/reprocess", json={"scope": "all", "respect_pins": True}).json()
    assert result["processed_count"] == 0
    assert result["user_ids_skipped"] == ["usr_001"]

    # Effective role is still the override after reprocess.
    detail = client.get("/api/users/usr_001").json()
    assert detail["effective_role"]["role_id"] == "role_002"


def test_reprocess_still_runs_inference_for_unpinned_override(client):
    client.post("/api/profiles", json=SARAH_PAYLOAD)
    client.patch(
        "/api/users/usr_001/override",
        json={"role_id": "role_002", "pinned": False, "created_by": "admin"},
    )

    result = client.post("/api/reprocess", json={"scope": "all", "respect_pins": True}).json()
    assert result["processed_count"] == 1

    # A fresh InferenceRun exists, but the (unpinned, still-active) override
    # still wins the effective role.
    history = client.get("/api/users/usr_001/history").json()
    assert sum(1 for item in history if item["type"] == "inference") == 2
    detail = client.get("/api/users/usr_001").json()
    assert detail["effective_role"]["role_id"] == "role_002"


def test_override_with_unknown_role_returns_404(client):
    client.post("/api/profiles", json=SARAH_PAYLOAD)
    response = client.patch(
        "/api/users/usr_001/override",
        json={"role_id": "role_999", "created_by": "admin"},
    )
    assert response.status_code == 404


def test_unknown_user_returns_404(client):
    assert client.get("/api/users/usr_ghost").status_code == 404
    assert client.get("/api/users/usr_ghost/inference").status_code == 404


def test_audit_log_records_override_and_inference_actions(client):
    client.post("/api/profiles", json=SARAH_PAYLOAD)
    client.patch(
        "/api/users/usr_001/override",
        json={"role_id": "role_002", "created_by": "admin", "reason": "test"},
    )
    audit = client.get("/api/audit").json()
    actions = [entry["action"] for entry in audit]
    assert "inference.completed" in actions
    assert "override.created" in actions
