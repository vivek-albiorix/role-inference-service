from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Bring the database up to the latest schema via Alembic.

    Runs `alembic upgrade head` programmatically so app startup and
    `scripts/seed.py` exercise the same migration path a real deploy would,
    rather than a `create_all` shortcut that bypasses migration history.
    Idempotent -- a no-op if already at head. Tests deliberately don't go
    through this: they call `Base.metadata.create_all` directly against a
    throwaway per-test SQLite file for speed and isolation (see
    `tests/test_api.py`), since ephemeral test databases have no migration
    history worth managing.
    """
    from alembic import command
    from alembic.config import Config

    from app.models import tables  # noqa: F401 -- registers ORM classes before any metadata use

    cfg = Config(str(_ALEMBIC_INI))
    command.upgrade(cfg, "head")


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
