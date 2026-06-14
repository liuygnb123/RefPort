"""Browser collection session models."""

from enum import StrEnum

from sqlmodel import Field, SQLModel

from litsearch.models._mixins import TimestampMixin


class BrowserPlatform(StrEnum):
    google_scholar = "google_scholar"
    cnki = "cnki"
    wos = "wos"
    scopus = "scopus"
    ieee = "ieee"
    generic = "generic"


class BrowserSessionStatus(StrEnum):
    started = "started"
    snapshotted = "snapshotted"
    parsed = "parsed"
    imported = "imported"
    blocked_manual_action_required = "blocked_manual_action_required"
    failed = "failed"


class BrowserLoginState(StrEnum):
    authenticated = "authenticated"
    login_required = "login_required"
    blocked_manual_action_required = "blocked_manual_action_required"
    unknown = "unknown"


class BrowserSession(TimestampMixin, SQLModel, table=True):
    __tablename__ = "browser_sessions"

    id: int | None = Field(default=None, primary_key=True)
    platform: str = Field(index=True)
    entry_url: str
    status: str = Field(default=BrowserSessionStatus.started.value, index=True)
    login_state: str = Field(default=BrowserLoginState.unknown.value, index=True)
    error: str | None = Field(default=None)


class BrowserSnapshotRecord(TimestampMixin, SQLModel, table=True):
    __tablename__ = "browser_snapshots"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="browser_sessions.id", index=True)
    url: str
    title: str | None = Field(default=None)
    html_path: str
    screenshot_path: str | None = Field(default=None)
    login_state: str = Field(default=BrowserLoginState.unknown.value, index=True)
    blocked_reason: str | None = Field(default=None)


class BrowserImport(TimestampMixin, SQLModel, table=True):
    __tablename__ = "browser_imports"

    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="browser_sessions.id", index=True)
    snapshot_id: int | None = Field(default=None, foreign_key="browser_snapshots.id", index=True)
    paper_id: int = Field(foreign_key="papers.id", index=True)
    action: str = Field(default="upserted")
