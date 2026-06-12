"""Library state and tag models."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint

from litsearch.models._mixins import TimestampMixin, utc_now

if TYPE_CHECKING:
    from litsearch.models.paper import Paper


class LibraryStatus(StrEnum):
    unread = "unread"
    reading = "reading"
    read = "read"
    excluded = "excluded"


class LibraryItem(TimestampMixin, SQLModel, table=True):
    __tablename__ = "library_items"

    id: int | None = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id", unique=True)
    status: LibraryStatus = Field(default=LibraryStatus.unread)
    favorite: bool = Field(default=False)
    rating: int | None = Field(default=None)
    notes: str | None = Field(default=None)

    paper: "Paper" = Relationship(back_populates="library_item")


class Tag(TimestampMixin, SQLModel, table=True):
    __tablename__ = "tags"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    name_normalized: str = Field(unique=True, index=True)

    papers: list["PaperTag"] = Relationship(back_populates="tag")


class PaperTag(SQLModel, table=True):
    __tablename__ = "paper_tags"
    __table_args__ = (UniqueConstraint("paper_id", "tag_id"),)

    id: int | None = Field(default=None, primary_key=True)
    paper_id: int = Field(foreign_key="papers.id")
    tag_id: int = Field(foreign_key="tags.id")
    created_at: datetime = Field(default_factory=utc_now, nullable=False)

    paper: "Paper" = Relationship(back_populates="tags")
    tag: Tag = Relationship(back_populates="papers")
