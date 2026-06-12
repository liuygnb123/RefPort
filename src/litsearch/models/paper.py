"""Paper model."""

from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from litsearch.models._mixins import TimestampMixin

if TYPE_CHECKING:
    from litsearch.models.author import PaperAuthor
    from litsearch.models.download import Download
    from litsearch.models.library import LibraryItem, PaperTag
    from litsearch.models.source import PaperSource
    from litsearch.models.venue import Venue


class Paper(TimestampMixin, SQLModel, table=True):
    __tablename__ = "papers"

    id: int | None = Field(default=None, primary_key=True)
    title: str
    title_normalized: str | None = Field(default=None, index=True)
    doi: str | None = Field(default=None)
    doi_normalized: str | None = Field(default=None, index=True)
    publication_year: int | None = Field(default=None)
    abstract: str | None = Field(default=None)
    venue_id: int | None = Field(default=None, foreign_key="venues.id")

    venue: Optional["Venue"] = Relationship(back_populates="papers")
    authors: list["PaperAuthor"] = Relationship(back_populates="paper")
    sources: list["PaperSource"] = Relationship(back_populates="paper")
    downloads: list["Download"] = Relationship(back_populates="paper")
    library_item: Optional["LibraryItem"] = Relationship(back_populates="paper")
    tags: list["PaperTag"] = Relationship(back_populates="paper")
