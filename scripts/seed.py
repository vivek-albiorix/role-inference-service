"""Seeds the Work Architecture catalog and the 8 assignment sample SSO
profiles into the database, running inference for each so the admin page
and API have real data immediately after `uvicorn app.main:app` starts.

Safe to re-run: skips roles and users that already exist rather than
duplicating them.

Usage: python scripts/seed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, init_db  # noqa: E402
from app.models.schemas import SSOProfileIn  # noqa: E402
from app.models.tables import Role, User  # noqa: E402
from app.pipeline.catalog import load_catalog_roles, load_sample_sso_profiles  # noqa: E402
from app.services.ingestion import ingest_profile  # noqa: E402
from app.services.inference_service import run_and_persist_inference  # noqa: E402


def seed_roles(session) -> int:
    existing_ids = {row.role_id for row in session.query(Role.role_id).all()}
    added = 0
    for role in load_catalog_roles():
        if role.role_id in existing_ids:
            continue
        session.add(
            Role(
                role_id=role.role_id,
                role_name=role.role_name,
                department=role.department,
                job_family=role.job_family,
                seniority=role.seniority,
                skills=role.skills,
                keywords=role.keywords,
                catalog_version=1,
            )
        )
        added += 1
    session.commit()
    return added


def seed_sample_users(session) -> int:
    existing_ids = {row.external_id for row in session.query(User.external_id).all()}
    added = 0
    for payload in load_sample_sso_profiles():
        if payload["user_id"] in existing_ids:
            continue
        profile_in = SSOProfileIn(**payload)
        user, profile = ingest_profile(session, profile_in)
        run_and_persist_inference(session, user, profile, actor="system:seed")
        session.commit()
        added += 1
    return added


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        roles_added = seed_roles(session)
        users_added = seed_sample_users(session)
        print(f"Seeded {roles_added} new role(s), {users_added} new sample user(s).")
        print(
            f"Total roles: {session.query(Role).count()}, "
            f"total users: {session.query(User).count()}"
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
