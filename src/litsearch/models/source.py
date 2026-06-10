"""Paper source model."""

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from litsearch.models._mixins import TimestampMixin

if TYPE_CHECKING:
    from litsearch.models.paper import Paper


class PaperSource(TimestampMixin, SQLModel, table=True):
    __tablename__ = "paper_sources"

    id: int | None = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id")
    source: str = Field(index=True)
    source_paper_id: str | None = Field(default=None)
    source_url: str | None = Field(default=None)
    raw_json: str | None = Field(default=None)

    paper: "Paper" = Relationship(back_populates="sources")
