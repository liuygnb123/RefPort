"""Download model."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from litsearch.models._mixins import TimestampMixin

if TYPE_CHECKING:
    from litsearch.models.paper import Paper


class DownloadStatus(StrEnum):
    pending = "pending"
    downloaded = "downloaded"
    failed = "failed"
    skipped = "skipped"


class Download(TimestampMixin, SQLModel, table=True):
    __tablename__ = "downloads"

    id: int | None = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id")
    status: DownloadStatus = Field(default=DownloadStatus.pending)
    source: str | None = Field(default=None)
    source_url: str | None = Field(default=None)
    pdf_url: str | None = Field(default=None)
    attempted_urls: str | None = Field(default=None)
    file_path: str | None = Field(default=None)
    sha256: str | None = Field(default=None)
    size_bytes: int | None = Field(default=None)
    mime_type: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
    error: str | None = Field(default=None)

    paper: "Paper" = Relationship(back_populates="downloads")
