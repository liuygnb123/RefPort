"""Author and paper-author link models."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from litsearch.models._mixins import TimestampMixin, utc_now

if TYPE_CHECKING:
    from litsearch.models.paper import Paper


class Author(TimestampMixin, SQLModel, table=True):
    __tablename__ = "authors"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    name_normalized: str | None = Field(default=None, index=True)
    orcid: str | None = Field(default=None, index=True)

    papers: list["PaperAuthor"] = Relationship(back_populates="author")


class PaperAuthor(SQLModel, table=True):
    __tablename__ = "paper_authors"

    id: int | None = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id")
    author_id: int = Field(foreign_key="authors.id")
    author_order: int
    created_at: datetime = Field(default_factory=utc_now, nullable=False)

    paper: "Paper" = Relationship(back_populates="authors")
    author: Author = Relationship(back_populates="papers")
