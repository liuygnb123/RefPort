"""Search run model."""

from enum import StrEnum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from litsearch.models._mixins import TimestampMixin

if TYPE_CHECKING:
    from litsearch.models.paper import Paper


class SearchRunStatus(StrEnum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class SearchRun(TimestampMixin, SQLModel, table=True):
    __tablename__ = "search_runs"

    id: int | None = Field(default=None, primary_key=True)
    query: str
    sources: str
    status: SearchRunStatus = Field(default=SearchRunStatus.pending)
    started_at: str | None = Field(default=None)
    finished_at: str | None = Field(default=None)
    errors: str | None = Field(default=None)

    results: list["SearchResultItem"] = Relationship(back_populates="search_run")


class SearchResultItem(TimestampMixin, SQLModel, table=True):
    __tablename__ = "search_result_items"

    id: int | None = Field(default=None, primary_key=True)
    search_run_id: int = Field(foreign_key="search_runs.id")
    paper_id: int = Field(foreign_key="papers.id")
    source: str = Field(index=True)
    rank: int
    score: float | None = Field(default=None)

    search_run: SearchRun = Relationship(back_populates="results")
    paper: "Paper" = Relationship()
