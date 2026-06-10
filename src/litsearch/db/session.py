"""Database engine and Alembic helpers."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlmodel import Session

from litsearch.config import Settings
from litsearch.exceptions import DatabaseError


def sqlite_path_from_url(db_url: str) -> Path | None:
    """Return local path for sqlite URLs, if applicable."""

    if not db_url.startswith("sqlite:"):
        return None
    if db_url.endswith(":memory:"):
        return None
    if db_url.startswith("sqlite:////"):
        return Path(db_url.removeprefix("sqlite:///"))
    if db_url.startswith("sqlite:///"):
        return Path(db_url.removeprefix("sqlite:///"))
    return None


def create_db_engine(settings: Settings):
    """Create a SQLAlchemy engine for the configured database."""

    connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
    return create_engine(settings.db_url, connect_args=connect_args)


def alembic_config(settings: Settings) -> Config:
    """Build Alembic configuration with the current database URL."""

    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "src/litsearch/db/migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.db_url)
    return cfg


def init_database(settings: Settings) -> str:
    """Create database directory and run Alembic migrations."""

    db_path = sqlite_path_from_url(settings.db_url)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        command.upgrade(alembic_config(settings), "head")
    except Exception as exc:  # pragma: no cover - defensive wrapper
        raise DatabaseError(f"Failed to initialize database: {exc}") from exc

    engine = create_db_engine(settings)
    with Session(engine) as session:
        revision = session.exec(text("select version_num from alembic_version")).one()[0]
    return str(revision)
